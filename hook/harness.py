#!/usr/bin/env python3
"""The scriptt harness, version 0.1.1. 1 file, beside world.py. Python 3.14 or later, standard library only.

Claude Code runs it as a hook, with 1 event as JSON on stdin:
  UserPromptSubmit   d1 decides which computations of the world the message demands. Claude receives them.
  Stop               d1 checks the reply against each demand. With "block": true in config.json, a reply that does none of them is sent back.
You run it for the rest:
  python harness.py install        add the 2 hooks and the skill to .claude/ of the folder above this one
  python harness.py serve [port]   show the events on a page where you drag to disagree

Everything is beside this file: world.py (the whitelist), config.json (where d1 is), events.jsonl (the log).
"""

import inspect
import json
import pathlib
import sys
import typing
import urllib.request
from string.templatelib import Interpolation, Template

HOME = pathlib.Path(__file__).resolve().parent
LOG = HOME / "events.jsonl"
sys.path.insert(0, str(HOME))
import world

CLASSES = {name: cls for name, cls in vars(world).items() if isinstance(cls, type) and issubclass(cls, str)}
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


def holes(name: str) -> dict:
    """The parameters of a function of the world, with the class of each. They are the holes that a message must fill."""
    return {parameter: cls for parameter, cls in typing.get_type_hints(FUNCTIONS[name]).items() if parameter != "return"}


def read(text: Asked, ask) -> tuple[Template, list, dict]:
    """The search, in 2 requests to d1. d1 gets yes/no questions only where the world lists the options.
    1. For each function of the world: does the message demand it? d1 decides.
    2. For each hole of a demanded function (a parameter): the named thing of its class that the message contains (code, no model),
       or else the named thing that d1 says the message refers to. With neither, the hole stays open. The search stops there."""
    yes = ask(text, {name: {"type": "boolean", "instructions": f"Does the message ask the reader to {f.__doc__}?"} for name, f in FUNCTIONS.items()})
    p = {name: round(yes[name]["p_true"], 3) for name in FUNCTIONS}
    demanded = [name for name in FUNCTIONS if p[name] >= 0.5]
    needed = {cls: sorted(world.NAMED.get(cls, ()), key=len, reverse=True) for name in demanded for cls in holes(name).values()}
    said = {cls: next((text[at:at + len(thing)] for thing in things if (at := text.lower().find(thing)) >= 0), None) for cls, things in needed.items()}
    found = ask(text, {name: {"type": "text", "instructions": f"Which words ask the reader to {FUNCTIONS[name].__doc__}?"} for name in demanded}
                | {f"{cls.__name__}: {thing}": {"type": "boolean", "instructions": f"Does the message refer to {thing} ({cls.__doc__})?"} for cls, things in needed.items() if not said[cls] for thing in things}) if demanded else {}

    def fill(cls) -> dict:
        """What fills a hole of this class: words of the message that name a thing, or the thing that d1 chose, or nothing."""
        if said[cls]:
            return {"class": cls.__name__, "thing": said[cls].lower(), "words": said[cls], "by": "the words"}
        chosen = max(((found[f"{cls.__name__}: {thing}"]["p_true"], thing) for thing in needed[cls]), default=(0, None))
        return {"class": cls.__name__, "thing": chosen[1] if chosen[0] >= 0.5 else None, "words": None, "by": f"d1 {chosen[0]:.2f}" if chosen[0] >= 0.5 else None}

    words = {name: text[text.find(a["text"]):][:len(a["text"])] for name in demanded if (a := found[name])["found"] >= 0.5 and a["text"] and a["text"] in text}
    demands = [{"function": name, "p": p[name], "returns": typing.get_type_hints(FUNCTIONS[name])["return"].__name__, "words": words.get(name),
                "parameters": {parameter: fill(cls) for parameter, cls in holes(name).items()}} for name in demanded]
    slots = sorted([(text.find(w), FUNCTIONS[name], name, w) for name, w in words.items()] + [(text.find(w), cls(w), cls.__name__, w) for cls, w in said.items() if w], key=lambda slot: (slot[0], -len(slot[3])))
    parts, at = [], 0
    for start, value, label, w in slots:  # the message as a template: the words that were found become typed slots
        if start >= at:
            parts += [str(text[at:start]), Interpolation(value, label, None, w)]
            at = start + len(w)
    return Template(*parts, str(text[at:])), demands, p


def call(demand: dict) -> str:
    arguments = (f'{parameter}={hole["class"]} "{hole["thing"]}"' if hole["thing"] else f'{parameter}={hole["class"]} ?' for parameter, hole in demand["parameters"].items())
    return f'{demand["function"]}({", ".join(arguments)}) -> {demand["returns"]}'


def handle(event: dict, ask=d1) -> dict | None:
    """1 event in, the answer for Claude Code out. The log is the only state: each event is 1 line of events.jsonl."""
    text = RECEIVED[event["hook_event_name"]](event)
    log = [json.loads(line) for line in LOG.read_text().splitlines()] if LOG.exists() else []
    mine = [record for record in log if record["session"] == event.get("session_id")]
    asked = [n for n, record in enumerate(mine) if record["event"] == "UserPromptSubmit"]
    record, answer = {"event": event["hook_event_name"], "session": event.get("session_id"), "brand": type(text).__name__, "text": text}, None
    match text:
        case Asked():
            template, demands, p = read(text, ask)
            record |= {"demands": demands, "p": p, "template": [part if isinstance(part, str) else {"words": part.format_spec, "is": part.expression} for part in template]}
            lines = ["scriptt: d1 read this message as a demand for these computations of the world (.scriptt/world.py)."]
            lines += [f'- {call(d)}   [d1 {d["p"]:.2f}' + (f', from "{d["words"]}"]' if d["words"] else "]") for d in demands] or ["- none of the functions of the world"]
            lines += ['A "?" is a hole that the message does not fill. If this reading is wrong, say so in 1 line.'] * bool(demands)
            corrections = {r["text"]: r for r in mine[asked[-1]:] if r["event"] == "Disagree"} if asked else {}  # the last one for each message
            lines += [f'The user corrected the reading of "{r["text"][:80]}": it demands {", ".join(r["demands"]) or "nothing"}. ' + ", ".join(f'{cls} is "{thing}"' if thing else f"{cls} is open" for cls, thing in r["things"].items()) for r in corrections.values()]
            answer = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "\n".join(lines)}}
        case Written() if asked and (demands := mine[asked[-1]]["demands"]):
            state = f"MESSAGE:\n{mine[asked[-1]]['text']}\n\nREPLY:\n{text}"
            done = ask(state, {d["function"]: {"type": "boolean", "instructions": f"The message asks the reader to {FUNCTIONS[d['function']].__doc__}. Does the reply do it, or say that it is done?"} for d in demands if d["function"] in FUNCTIONS})
            record["checks"] = {name: round(a["p_true"], 3) for name, a in done.items()}
            if max(record["checks"].values(), default=1) < 0.5 and config().get("block") and not event.get("stop_hook_active"):
                answer = {"decision": "block", "reason": "scriptt: the reply does none of what the message demanded: " + ", ".join(call(d) for d in demands)}
    with LOG.open("a") as file:
        file.write(json.dumps(record | {"answer": answer}) + "\n")
    return answer


def describe() -> dict:
    """The world as data, for the page."""
    return {"classes": {name: cls.__doc__ for name, cls in CLASSES.items()}, "named": {cls.__name__: sorted(names) for cls, names in world.NAMED.items()},
            "functions": {name: {"asks": f.__doc__, "returns": typing.get_type_hints(f)["return"].__name__, "parameters": {k: cls.__name__ for k, cls in holes(name).items()}} for name, f in FUNCTIONS.items()}}


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
                events = [json.loads(line) for line in LOG.read_text().splitlines()] if LOG.exists() else []
                return self.reply(json.dumps({"world": describe(), "events": events}).encode(), "application/json")
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
            correction = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            record = {"event": "Disagree", "session": correction["session"], "text": correction["text"], "demands": [name for name in correction["demands"] if name in FUNCTIONS], "things": correction.get("things", {})}
            with LOG.open("a") as file:
                file.write(json.dumps(record) + "\n")
            self.reply(b"{}", "application/json")

        def log_message(self, *args):
            pass

    print(f"http://127.0.0.1:{port}")
    HTTPServer(("127.0.0.1", port), Page).serve_forever()


if __name__ == "__main__":
    match sys.argv[1:]:
        case ["install"]:
            install()
        case ["serve", *port]:
            serve(int(port[0]) if port else 8787)
        case _:
            try:
                answer = handle(json.load(sys.stdin))
            except Exception as error:  # a hook must not stop the session: say what failed and let Claude go on
                sys.exit(print(f"scriptt: {type(error).__name__}: {error}", file=sys.stderr))
            if answer is not None:
                print(json.dumps(answer))
