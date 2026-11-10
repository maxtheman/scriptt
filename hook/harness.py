#!/usr/bin/env python3
"""The scriptt harness. 1 file, beside world.py. Python 3.14 or later, standard library only.

Claude Code runs it as a hook, with 1 event as JSON on stdin:
  UserPromptSubmit   d1 decides which computations of the world the message demands. Claude receives them.
  Stop               d1 checks the reply against each demand. With "block": true in config.json, a reply that does none of them is sent back.
You run it for the rest:
  python harness.py install        add the 2 hooks and the skill to .claude/ of the folder above this one
  python harness.py serve [port]   show the events on a page where you drag to disagree
  python harness.py find WORDS     the parts of every logged message that have these words or this function. find "?" lists the
                                   parts that d1 abstained on: the candidates for a new line of world.py

Everything is beside this file: world.py (the whitelist), config.json (where d1 is), events.jsonl (the log).
"""

import dataclasses
import datetime
import enum
import hashlib
import inspect
import json
import pathlib
import re
import sys
import types
import typing
import urllib.request
from string.templatelib import Interpolation, Template

VERSION = "0.1.5"  # of the harness
FORM = 2  # of a line of events.jsonl. Change it when a key changes its meaning, and add the step to migrate().
HOME = pathlib.Path(__file__).resolve().parent
LOG = HOME / "events.jsonl"
sys.path.insert(0, str(HOME))
import world

TYPES = {name: tp for name, tp in vars(world).items() if isinstance(tp, type) and tp.__module__ == "world"}  # the sum types and the product types
FUNCTIONS = {name: f for name, f in vars(world).items() if inspect.isfunction(f)}


class Brand(str):
    """A text, with who produced it. The line that receives a text gives it its brand. d1 chooses no brand."""

    def __getitem__(self, key):
        return type(self)(super().__getitem__(key))  # a part of a text has the brand of the text


class Asked(Brand):
    """text that the user supplied"""


class Written(Brand):
    """text that the assistant composed"""


RECEIVED = {"UserPromptSubmit": lambda event: Asked(event["prompt"]), "Stop": lambda event: Written(event["last_assistant_message"])}


def config() -> dict:
    return json.loads((HOME / "config.json").read_text())


def d1(state: str, questions: dict, config=config) -> dict:
    """Ask d1 the questions {id: question} about the state. It returns {id: answer}. config.json says where d1 is."""
    config = config()
    key = config.get("key") or ("key_file" in config and pathlib.Path(config["key_file"]).expanduser().read_text().strip())
    listed = config["url"].endswith("/decide")  # CoreAI takes a list of questions with ids. A System One endpoint takes a dict.
    body = config.get("body", {}) | {"state": state, "questions": [{"id": id} | q for id, q in questions.items()] if listed else questions}
    request = urllib.request.Request(config["url"], json.dumps(body).encode(), {"Content-Type": "application/json"} | ({"Authorization": f"Bearer {key}"} if key else {}))
    with urllib.request.urlopen(request, timeout=30) as reply:
        answers = json.load(reply)["answers"]
    return {answer["id"]: answer for answer in answers} if listed else answers


def stamp() -> dict:
    """The start of each line of the log: the form of the line, the harness, the world as it was (a hash of world.py), and the time."""
    return {"form": FORM, "harness": VERSION, "world": hashlib.sha1((HOME / "world.py").read_bytes()).hexdigest()[:12], "at": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")}


def migrate(record: dict) -> dict:
    """A line of the log in the current form. Form 1 (0.1.1) had no parts: its demands were found for the whole message."""
    if record.get("form", 1) < 2 and record["event"] == "UserPromptSubmit":
        record = record | {"form": 2, "parts": [], "demands": [d | {"part": None, "by": "the message"} for d in record.get("demands", [])]}
    return record | {"form": FORM}


def history() -> list:
    return [migrate(json.loads(line)) for line in LOG.read_text().splitlines()] if LOG.exists() else []


def kind(tp) -> str:
    return tp.__name__ if isinstance(tp, type) else str(tp).replace("pathlib._local.", "")  # a class by its name, a union as written


def holes(name: str) -> dict:
    """The holes of a function of the world, as {path: type}: each parameter, and for a product type (a dataclass) each of its fields."""
    def leaves(path, tp):
        if dataclasses.is_dataclass(tp):
            return [leaf for field, inner in typing.get_type_hints(tp).items() for leaf in leaves(f"{path}.{field}", inner)]
        return [(path, tp)]

    return dict(leaf for parameter, tp in typing.get_type_hints(FUNCTIONS[name]).items() if parameter != "return" for leaf in leaves(parameter, tp))


def in_words(tp, words: str) -> str | None:
    """The value for a hole of this type that the words contain, found by code. None when they contain none."""
    match tp:
        case enum.EnumType():  # a sum type: the member whose name is in the words, the longest name first
            return next((words[at:at + len(m.value)].lower() for m in sorted(tp, key=lambda m: -len(m.value)) if (at := words.lower().find(m.value)) >= 0), None)
        case types.UnionType():  # a sum of types: the first that the words fill
            return next((value for inner in typing.get_args(tp) if (value := in_words(inner, words))), None)
        case type() if tp is int:
            return (found := re.search(r"\b\d+\b", words)) and found[0]
        case type() if tp is pathlib.Path:
            return (found := re.search(r"(?:[~.]{0,2}/)?[\w.-]+(?:/[\w.-]+)+|\b[\w-]+\.[a-z]{1,5}\b", words)) and found[0]
    return None


def to_ask(tp, parameter: str) -> dict:
    """The questions for d1 about a hole of this type that code did not fill: {the value that a yes means, or "" for a text read: question}."""
    match tp:
        case enum.EnumType():
            return {m.value: {"type": "boolean", "instructions": f"Does the message refer to {m.value} ({tp.__doc__})?"} for m in tp}
        case types.UnionType():
            return {value: q for inner in typing.get_args(tp) for value, q in to_ask(inner, parameter).items()}
        case type() if tp is bool:
            return {"yes": {"type": "boolean", "instructions": f"Does the message say: {parameter.replace('_', ' ')}?"}}
        case type() if tp is str:
            return {"": {"type": "text", "instructions": f"Which words of the message say the {parameter.replace('_', ' ')}?"}}
    return {}


class Hole(Brand):
    """a part of a message that asks for something, and no function of the world fits it"""


def parts_of(text: str) -> list:
    """The text cut into parts by code, no model: its sentences. Each part is (start, end) in the text, so no word loses its place."""
    spans, start = [], None
    for a, b in (match.span() for match in re.finditer(r"\S(?:[^.?!\n]|[.?!](?=\S))*[.?!]*", text)):
        start = a if start is None else start
        if b - start >= 6:  # a list number such as "1." is no part of its own: it belongs to the part after it
            spans.append((start, b))
            start = None
    return spans + ([(start, len(text.rstrip()))] if start is not None else [])


def read(text: Asked, ask) -> tuple[Template, list, list, dict]:
    """The search. d1 gets yes/no and choice questions only, over options that the world or the message lists.
    1. Coarse: for each function of the world, does the whole message demand it?
    2. Where: for each demanded function, which part of the message asks for it? (a choice among the parts, or none)
    3. Fine: for each part that no function claimed, does the part ask for something? If yes, each function again, on that part alone.
       If no function fits, d1 abstains and the part is a Hole. Claude is told to fill it.
    4. For each parameter of a demanded function: the named thing of its class that the words contain (code), or else the named
       thing that d1 chooses, or else the parameter stays open.
    The search stops there. The template that it returns is the whole message: "".join of its parts is the text."""
    yes_no = lambda words: {"type": "boolean", "instructions": words}
    spans = parts_of(text)
    quoted = [text[a:b] for a, b in spans]  # each part is a part of the message: brand Asked
    whole = ask(text, {name: yes_no(f"Does the message ask the reader to {f.__doc__}?") for name, f in FUNCTIONS.items()})
    p = {name: round(whole[name]["p_true"], 3) for name in FUNCTIONS}
    found = [{"function": name, "p": p[name], "by": "the message", "part": None} for name in FUNCTIONS if p[name] >= 0.5]
    if found and len(spans) > 1:
        options = [{"id": f"part{n}", "description": part[:200]} for n, part in enumerate(quoted)] + [{"id": "none", "description": "no part of the message asks for this"}]
        where = ask(text, {d["function"]: {"type": "choice", "instructions": f"Which part of the message asks the reader to {FUNCTIONS[d['function']].__doc__}?", "options": options} for d in found})
        for d in found:
            d["part"] = None if where[d["function"]]["value"] == "none" else int(where[d["function"]]["value"][4:])
    for d in found if len(spans) == 1 else []:  # a message of 1 part: that part asks for each of them
        d["part"] = 0
    rest = [n for n in range(len(spans)) if n not in {d["part"] for d in found}]
    asks = ask(text, {f"part{n}": yes_no(f'Does this part of the message ask the reader to do, make, change or answer something? The part: "{quoted[n][:300]}"') for n in rest}) if rest else {}
    abstained = {}
    for n in rest:
        if asks[f"part{n}"]["p_true"] >= 0.5:
            alone = ask(quoted[n], {name: yes_no(f"Does this text ask the reader to {f.__doc__}?") for name, f in FUNCTIONS.items()})
            fits = [{"function": name, "p": round(alone[name]["p_true"], 3), "by": "the part", "part": n} for name in FUNCTIONS if alone[name]["p_true"] >= 0.5]
            found += fits
            if not fits:
                abstained[n] = round(asks[f"part{n}"]["p_true"], 3)

    # 4. The holes. First by code, in the words of the part and then of the message. Then 1 request to d1 for the holes that are left.
    said = {(n, path): next((value for words in ([quoted[d["part"]]] if d["part"] is not None else []) + [text] if (value := in_words(tp, words))), None)
            for n, d in enumerate(found) for path, tp in holes(d["function"]).items()}
    left = {(n, path, value): q for n, d in enumerate(found) for path, tp in holes(d["function"]).items() if not said[n, path] for value, q in to_ask(tp, path.split(".")[-1]).items()}
    told = ask(text, {f"{n} {path} {value}": q for (n, path, value), q in left.items()}) if left else {}

    def fill(n: int, path: str, tp) -> dict:
        if said[n, path]:
            return {"type": kind(tp), "value": said[n, path], "by": "the words"}
        answers = {value: told[f"{n} {path} {value}"] for (m, other, value) in left if (m, other) == (n, path)}
        if "" in answers:  # a text read: the words that d1 points at, if the message has them
            a = answers[""]
            return {"type": kind(tp), "value": a["text"], "by": f"d1 {a['found']:.2f}"} if a["found"] >= 0.5 and a["text"] and a["text"] in text else {"type": kind(tp), "value": None, "by": None}
        best = max(answers, key=lambda value: answers[value]["p_true"], default=None)
        sure = best is not None and answers[best]["p_true"] >= 0.5
        return {"type": kind(tp), "value": best if sure else None, "by": f"d1 {answers[best]['p_true']:.2f}" if sure else None}

    demands = [d | {"returns": kind(typing.get_type_hints(FUNCTIONS[d["function"]])["return"]), "words": quoted[d["part"]] if d["part"] is not None else None,
                    "parameters": {path: fill(n, path, tp) for path, tp in holes(d["function"]).items()}} for n, d in enumerate(found)]
    parts = [{"start": a, "end": b, "demands": [d["function"] for d in demands if d["part"] == n], "hole": abstained.get(n)} for n, (a, b) in enumerate(spans)]
    pieces, at = [], 0
    for part, words in zip(parts, quoted):  # the whole message as a template: a part that demands or abstains is a slot, the rest is plain text
        if part["demands"] or part["hole"]:
            value = tuple(FUNCTIONS[name] for name in part["demands"]) or Hole
            pieces += [str(text[at:part["start"]]), Interpolation(value, " + ".join(part["demands"]) or "?", None, words)]
            at = part["end"]
    return Template(*pieces, str(text[at:])), demands, parts, p


def call(demand: dict) -> str:
    arguments = (f'{path}="{hole["value"]}"' if hole["value"] else f'{path}={hole["type"]} ?' for path, hole in demand["parameters"].items() if hole["value"] or "None" not in hole["type"])
    return f'{demand["function"]}({", ".join(arguments)})'


def handle(event: dict, ask=d1) -> dict | None:
    """1 event in, the answer for Claude Code out. The log is the only state: each event is 1 line of events.jsonl."""
    text = RECEIVED[event["hook_event_name"]](event)
    mine = [record for record in history() if record["session"] == event.get("session_id")]
    asked = [n for n, record in enumerate(mine) if record["event"] == "UserPromptSubmit"]
    record, answer = stamp() | {"event": event["hook_event_name"], "session": event.get("session_id"), "brand": type(text).__name__, "text": text}, None
    match text:
        case Asked():
            template, demands, parts, p = read(text, ask)
            record |= {"demands": demands, "parts": parts, "p": p, "template": [piece if isinstance(piece, str) else {"words": piece.format_spec, "is": piece.expression} for piece in template]}
            asking = [(n, part, [d for d in demands if d["part"] == n]) for n, part in enumerate(parts) if part["demands"] or part["hole"]]
            lines = [f"scriptt: d1 read this message against .scriptt/world.py. Parts: {len(parts)}. Parts that ask for something: {len(asking)}."]
            for n, part, found in asking:  # 1 line for each part that asks for something: what it demands, how sure d1 is, and its first words
                what = " + ".join(call(d) + f" {d['p']:.2f}" for d in found) or "?  no function of the world fits (d1 abstains)"
                lines += [f'{n + 1}. {what}   "{text[part["start"]:part["end"]][:90]}"']
            lines += [f"-. {call(d)} {d['p']:.2f}   (the message as a whole)" for d in demands if d["part"] is None]
            if any(part["hole"] for part in parts):
                lines += ['For each "?": say in 1 line what the part asks, do it, and propose the line to add to .scriptt/world.py.']
            if any(not hole["value"] and "None" not in hole["type"] for d in demands for hole in d["parameters"].values()):
                lines += ['A "name=Type ?" is a hole that the message does not fill. Fill it from the conversation, or ask for that 1 thing.']
            if asked:  # what came after the last message: the reply check, and the corrections of the user (the last one for each message)
                after = mine[asked[-1]:]
                lines += [f"d1 says your last reply did not do: {', '.join(name for name, q in r['checks'].items() if q < 0.5)}." for r in after if r["event"] == "Stop" and any(q < 0.5 for q in r.get("checks", {}).values())][-1:]
                for r in {(r["text"], r["part"]): r for r in after if r["event"] == "Disagree"}.values():  # the last reading of each part
                    things = "".join(f', {path} is "{value}"' if value else f", {path} is open" for path, value in r["things"].items())
                    lines += [f'The user says that "{r["words"][:90]}" asks for {" + ".join(r["demands"]) or "nothing"}{things}. d1 said otherwise.']
            answer = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "\n".join(lines)}}
        case Written() if asked and ((last := mine[asked[-1]])["demands"] or any(part["hole"] for part in last["parts"])):
            state = f"MESSAGE:\n{last['text']}\n\nREPLY:\n{text}"
            questions = {d["function"]: f"The message asks the reader to {FUNCTIONS[d['function']].__doc__}. Does the reply do it, or say that it is done?" for d in last["demands"] if d["function"] in FUNCTIONS}
            questions |= {f"part {n + 1}": f'The message says: "{last["text"][part["start"]:part["end"]][:300]}". Does the reply respond to that?' for n, part in enumerate(last["parts"]) if part["hole"]}
            done = ask(state, {id: {"type": "boolean", "instructions": words} for id, words in questions.items()})
            record["checks"] = {id: round(a["p_true"], 3) for id, a in done.items()}
            demanded = [q for id, q in record["checks"].items() if id in FUNCTIONS]  # a reply goes back only when it does none of the demanded functions
            if max(demanded, default=1) < 0.5 and config().get("block") and not event.get("stop_hook_active"):
                answer = {"decision": "block", "reason": "scriptt: d1 says the reply does none of what the message asked: " + ", ".join(questions)}
    with LOG.open("a") as file:
        file.write(json.dumps(record | {"answer": answer}) + "\n")
    return answer


def describe() -> dict:
    """The world as data, for the page."""
    def shape(tp) -> dict:
        match tp:
            case enum.EnumType():
                return {"sum": [m.value for m in tp], "doc": tp.__doc__}
            case _:
                return {"product": {field: kind(inner) for field, inner in typing.get_type_hints(tp).items()}, "doc": tp.__doc__}

    return {"types": {name: shape(tp) for name, tp in TYPES.items()},
            "functions": {name: {"asks": f.__doc__, "returns": kind(typing.get_type_hints(f)["return"]), "holes": {path: kind(tp) for path, tp in holes(name).items()}} for name, f in FUNCTIONS.items()}}


def install():
    """Add the 2 hooks to .claude/settings.local.json of the folder above this one, copy the skill, and write config.json if there is none."""
    settings = HOME.parent / ".claude" / "settings.local.json"
    settings.parent.mkdir(exist_ok=True)
    data = json.loads(settings.read_text()) if settings.exists() else {}
    hook = {"hooks": [{"type": "command", "command": f'"{sys.executable}" "{HOME / "harness.py"}"', "timeout": 60}]}
    for name in RECEIVED:
        entries = data.setdefault("hooks", {}).setdefault(name, [])
        entries[:] = [entry for entry in entries if "harness.py" not in json.dumps(entry)] + [hook]
    settings.write_text(json.dumps(data, indent=2) + "\n")
    if (HOME / "SKILL.md").exists():  # the skill tells Claude what the harness sends and how to answer it
        (settings.parent / "skills" / "scriptt").mkdir(parents=True, exist_ok=True)
        (settings.parent / "skills" / "scriptt" / "SKILL.md").write_text((HOME / "SKILL.md").read_text())
    if not (HOME / "config.json").exists():
        (HOME / "config.json").write_text(json.dumps({"url": "http://127.0.0.1:8791/v1/systemone", "body": {"model": "d1-2B-MLX-8bit"}, "block": False}, indent=2) + "\n")
    print(f"hooks are in {settings}\nd1 is set in {HOME / 'config.json'}")


def serve(port: int):
    """The page, on this computer only. GET /data is the world and the log. POST /disagree adds 1 line to the log."""
    from http.server import BaseHTTPRequestHandler, HTTPServer

    site = next((folder for folder in (HOME / "site", HOME.parent / "web" / "site") if folder.exists()), None)

    class Page(BaseHTTPRequestHandler):
        def reply(self, body: bytes, kind: str):
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            name = self.path.split("?")[0].strip("/") or "index.html"
            if name == "data":
                return self.reply(json.dumps({"world": describe(), "events": history()}).encode(), "application/json")
            try:
                if site and (site / name).resolve().is_relative_to(site.resolve()) and (site / name).is_file():
                    body = (site / name).read_bytes()
                else:  # no copy of the page on this computer: the public one
                    body = urllib.request.urlopen("https://scriptt.ai/" + urllib.request.quote(name), timeout=30).read()
            except OSError:
                return self.send_error(404)
            self.reply(body, {"html": "text/html; charset=utf-8", "js": "text/javascript"}.get(name.rsplit(".", 1)[-1], "text/plain"))

        def do_POST(self):
            if self.path != "/disagree" or self.headers.get("Origin", f"http://127.0.0.1:{port}") not in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
                return self.send_error(403)
            reading(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.reply(b"{}", "application/json")

        def log_message(self, *args):
            pass

    print(f"http://127.0.0.1:{port}")
    HTTPServer(("127.0.0.1", port), Page).serve_forever()


def reading(mine: dict) -> None:
    """Add the user's own reading of 1 part of 1 message to the log. Claude receives it with the next message of that session.
    mine = {"session", "text", "part": its number from 0, "demands": [function names], "things": {hole path: value}}"""
    message = next(r for r in reversed(history()) if r["event"] == "UserPromptSubmit" and r["session"] == mine["session"] and r["text"] == mine["text"])
    part = message["parts"][mine["part"]]
    record = stamp() | {"event": "Disagree", "session": mine["session"], "text": mine["text"], "part": mine["part"], "words": mine["text"][part["start"]:part["end"]],
                        "demands": [name for name in mine["demands"] if name in FUNCTIONS], "things": mine.get("things", {})}
    with LOG.open("a") as file:
        file.write(json.dumps(record) + "\n")


def find(words: list) -> None:
    """Print each part of each logged message that has all these words in its text or among its functions. "?" finds the parts that d1 abstained on."""
    for record in history():
        for n, part in enumerate(record.get("parts", [])):
            tags = part["demands"] + ["?"] * bool(part["hole"])
            said = record["text"][part["start"]:part["end"]]
            if tags and all(word.lower() in said.lower() or word in tags for word in words):
                print(f'{record["at"][:16]}  {record["session"][:8]}  part {n + 1}  [{" + ".join(tags)}]  {said[:120]}')


if __name__ == "__main__":
    match sys.argv[1:]:
        case ["install"]:
            install()
        case ["find", *words]:
            find(words)
        case ["reading"]:  # the user's reading of 1 part, as JSON on stdin (the mod sends it)
            reading(json.load(sys.stdin))
        case ["serve", *port]:
            serve(int(port[0]) if port else 8787)
        case _:
            try:
                answer = handle(json.load(sys.stdin))
            except Exception as error:  # a hook must not stop the session: say what failed and let Claude go on
                sys.exit(print(f"scriptt: {type(error).__name__}: {error}", file=sys.stderr))
            if answer is not None:
                print(json.dumps(answer))
