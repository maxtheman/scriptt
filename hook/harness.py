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

import ast
import dataclasses
import datetime
import enum
import hashlib
import inspect
import json
import math
import pathlib
import re
import sys
import textwrap
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

FUNCTIONS = dict(inspect.getmembers(world, inspect.isfunction))  # world.py is the whitelist: each function in it, by name
FUNCTIONS = {name: FUNCTIONS[name] for name in vars(world) if name in FUNCTIONS}  # in the order of the file


class By(enum.StrEnum):
    """How a thing was found. A sum type: each value in a record is 1 of these."""

    MESSAGE = "the message"  # d1 said yes with the message as the state, and yes with the part alone
    PART = "the part"  # d1 said yes with the part alone, after the message gave too little for this function
    WORDS = "the words"  # code found the value in the words
    RESULT = "the result of"  # another demanded function returns this type
    D1 = "d1"  # d1 chose the value


class Brand(str):
    """A text, with who produced it. The line that receives a text gives it its brand. d1 chooses no brand."""

    def __getitem__(self, key):
        return type(self)(super().__getitem__(key))  # a part of a text has the brand of the text


class Asked(Brand):
    """text that the user supplied"""


class Written(Brand):
    """text that the assistant composed"""


class Observed(Brand):
    """text that a run of code produced"""


def received(event: dict) -> Brand:
    """The text of an event, with its brand. The key that holds the text says who produced it."""
    match event:
        case {"prompt": str(text)}:
            return Asked(text)
        case {"last_assistant_message": str(text)}:
            return Written(text)
    raise ValueError("an event with no text")


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
        record = record | {"form": 2, "parts": [], "demands": [d | {"part": None, "by": By.MESSAGE} for d in record.get("demands", [])]}
    return record | {"form": FORM}


def history() -> list:
    return [migrate(json.loads(line)) for line in LOG.read_text().splitlines()] if LOG.exists() else []


def kind(tp) -> str:
    return tp.__name__ if isinstance(tp, type) else str(tp).replace("pathlib._local.", "").replace("world.", "")  # a class by its name, a union as written


# ---- What d1 is asked. A question is a template. A slot of it is a thing of the world or words of the message. ----
def say(value) -> str:
    """The words for 1 slot of a question: the docstring of a function or a type, the name of a member, or the words themselves."""
    match value:
        case types.FunctionType() | type():
            return value.__doc__
        case enum.Enum():
            return value.value
    return str(value)


yes = lambda question: {"type": "boolean", "instructions": "".join(piece if isinstance(piece, str) else say(piece.value) for piece in question)}
words = lambda question: yes(question) | {"type": "text"}

# The wordings, in 1 place. Each was compared with others on recorded messages and on 2 trial folders, with the real d1-2b (README.md).
ASKS = lambda where: t"Does {where} ask the reader to do, make, change or answer something?"
PART = lambda part: f'this part of the message ("{part[:300]}")'
WHAT = "What does this text ask the reader to do?"
REFERS = lambda member, tp: t"Does the message refer to {member} ({tp})?"
SAYS = lambda name: t"Does the message say: {name}?"
WHICH = lambda name: t"Which words of the message say the {name}?"
IS = lambda value, name, f: t'The message asks the reader to {f}. In the message, are the words "{value}" the {name} for that?'
WITH = lambda f, g: t"Does the message ask the reader to {f} with the result of this: {g}?"
DID = lambda f: t"The message asks the reader to {f}. Does the reply do it, or say that it is done?"
ANSWERED = lambda part: t'The message says: "{part}". Does the reply respond to that?'


def put(ask, state: str, questions: dict) -> dict:
    """Ask d1 questions that have any keys (a function, a pair, a path). d1 sees numbers. It returns {key: answer}."""
    keys, answers = list(questions), {}
    for start in range(0, len(keys), 32):  # d1 takes 32 questions in 1 request
        answers |= ask(state, {f"q{n}": questions[keys[n]] for n in range(start, min(start + 32, len(keys)))})
    return {key: answers[f"q{n}"] for n, key in enumerate(keys)}


# ---- Holes, by type constructor. Each function below has 1 case for each constructor of a type and calls itself for the types inside. ----
def holes(tp, path: str) -> list:
    """The holes of a parameter, as (path, type): the parameter, or for a product type (a dataclass) the holes of each field."""
    if dataclasses.is_dataclass(tp):
        return [hole for field, inner in typing.get_type_hints(tp).items() for hole in holes(inner, f"{path}.{field}")]
    return [(path, tp)]


def signature(f) -> tuple[dict, type]:
    """The holes of a function of the world, as {path: type}, and the type of its result."""
    hints = typing.get_type_hints(f)
    return dict(hole for parameter, tp in hints.items() if parameter != "return" for hole in holes(tp, parameter)), hints["return"]


def in_words(tp, text: str) -> str | None:
    """The value for a hole of this type that the text contains, found by code. None when it contains none."""
    match tp:
        case enum.EnumType():  # a sum type: the member whose name is in the text, the longest name first
            return next((m.value for m in sorted(tp, key=lambda m: -len(m.value)) if m.value in text.lower()), None)
        case types.UnionType():  # a sum of types: the first that the text fills
            return next((value for inner in typing.get_args(tp) if (value := in_words(inner, text))), None)
        case types.GenericAlias() if typing.get_origin(tp) is list:  # several of 1 type: each member that the text names
            inner, = typing.get_args(tp)
            return ", ".join(m.value for m in inner if m.value in text.lower()) or None if isinstance(inner, enum.EnumType) else in_words(inner, text)
        case type() if tp is int:
            return (found := re.search(r"\b\d+\b", text)) and found[0]
        case type() if tp is pathlib.Path:
            return (found := re.search(r"(?:[~.]{0,2}/)?[\w.-]+(?:/[\w.-]+)+|\b[\w-]+\.[a-z]{1,5}\b", text)) and found[0].rstrip(".")
    return None


def to_ask(tp, name: str) -> dict:
    """The questions for d1 about a hole that code did not fill, as {the value that a yes means, or "" for a text read: question}."""
    match tp:
        case enum.EnumType():
            return {m.value: yes(REFERS(m, tp)) for m in tp}
        case types.UnionType() | types.GenericAlias():
            return {value: q for inner in typing.get_args(tp) for value, q in to_ask(inner, name).items()}
        case type() if tp is bool:
            return {"yes": yes(SAYS(name))}
        case type() if tp is str:
            return {"": words(WHICH(name))}
    return {}


class Hole(Brand):
    """a part of a message that asks for something, and no function of the world fits it"""


def parts_of(text: str) -> list:
    """The text cut into parts by code, no model: its sentences. Each part is (start, end) in the text, so no word loses its place."""
    spans, start = [], None
    for a, b in (match.span() for match in re.finditer(r"\S(?:[^.?!\n]|[.?!](?=\S))*[.?!]*", text)):
        start = a if start is None else start
        if b - start >= 6:  # a list number such as "1." is no part of its own: it belongs to the part after it
            spans += [(start, b)] * (not re.fullmatch(r"</?[\w:-]+[^>]*>", text[start:b]))  # a wrapper tag is no part
            start = None
    return spans + ([(start, len(text.rstrip()))] if start is not None else [])


def read(text: Asked, ask) -> tuple[Template, list, list, dict]:
    """The search. Every decision is d1's, and every option is from the world or from the message.
    1. For each part, with the message as the state: does the part ask the reader for something? A part that does not is plain text.
    2. For each part that asks, with the part alone as the state: 1 choice among the functions of the world and "none".
       The part demands each function that gets a quarter or more. If "none" gets the most, d1 abstains: the part is a Hole,
       and Claude is told to fill it, with the closest function beside it.
    3. For each hole of a demanded function, by its type: a value in the words of the part (code), or the result of another
       demand of the message that returns this type, or the value that d1 chooses. Else the hole stays open.
    4. d1 checks each value that code found, and each result that code put in a hole. A value that d1 rejects leaves the hole open.
    Two trial agents and the recorded messages decided these rules: see README.md, "What was tried".
    The template that read returns is the whole message: "".join of its pieces is the text."""
    spans = parts_of(text)
    quoted = [text[a:b] for a, b in spans]  # each part is a part of the message: brand Asked
    asking = put(ask, text, {n: yes(ASKS(PART(part))) for n, part in enumerate(quoted)})
    options = [{"id": name, "description": f.__doc__} for name, f in FUNCTIONS.items()] + [{"id": "none", "description": "none of these, or the text asks for nothing"}]
    scores = {n: put(ask, part, {0: {"type": "choice", "instructions": say(WHAT), "options": options}})[0]["probabilities"] for n, part in enumerate(quoted) if asking[n]["p_true"] >= 0.5}
    found = [{"function": name, "p": round(q, 3), "by": By.PART, "part": n} for n, chosen in scores.items() if max(chosen, key=chosen.get) != "none"
             for name, q in chosen.items() if name != "none" and q >= 0.25]
    p = {name: round(max((chosen[name] for chosen in scores.values()), default=0.0), 3) for name in FUNCTIONS}

    wanted = {(n, path): tp for n, d in enumerate(found) for path, tp in signature(FUNCTIONS[d["function"]])[0].items()}
    said = {key: in_words(tp, quoted[found[key[0]]["part"]]) for key, tp in wanted.items()}
    made = {key: next((d["function"] for m, d in enumerate(found) if m != key[0] and getattr(tp, "__module__", "") == "world" and signature(FUNCTIONS[d["function"]])[1] is tp), None)
            for key, tp in wanted.items() if not said[key]}
    role = lambda key: (FUNCTIONS[found[key[0]]["function"]], key[1].split(".")[-1].replace("_", " "))
    told = put(ask, text, {(key, value): q for key, tp in wanted.items() if not said[key] and not made[key] for value, q in to_ask(tp, role(key)[1]).items()}
               | {(key, None): yes(IS(said[key], role(key)[1], role(key)[0])) for key in wanted if said[key]}
               | {(key, None): yes(WITH(role(key)[0], FUNCTIONS[made[key]])) for key in wanted if made.get(key)})

    def fill(key, tp) -> dict:
        hole = {"type": kind(tp), "value": None, "by": None}
        check = round(told[key, None]["p_true"], 3) if (key, None) in told else None
        if said[key] or made.get(key):  # code found it. d1 checks it, and a value that d1 rejects leaves the hole open.
            value, by = (said[key], By.WORDS) if said[key] else (made[key], By.RESULT)
            return hole | {"value": value, "by": by, "d1": check} if check >= 0.5 else hole | {"rejected": value, "d1": check}
        answers = {value: a for (other, value), a in told.items() if other == key and value is not None}
        if "" in answers:  # a text read: the words that d1 points at, if the message has them
            a = answers[""]
            return hole | {"value": a["text"], "by": By.D1, "d1": round(a["found"], 3)} if a["found"] >= 0.5 and a["text"] and a["text"] in text and len(a["text"]) <= 60 else hole
        best = max(answers, key=lambda value: answers[value]["p_true"], default=None)
        return hole | {"value": best, "by": By.D1, "d1": round(answers[best]["p_true"], 3)} if best is not None and answers[best]["p_true"] >= 0.5 else hole

    demands = [d | {"returns": kind(signature(FUNCTIONS[d["function"]])[1]), "words": quoted[d["part"]],
                    "parameters": {path: fill((n, path), tp) for path, tp in signature(FUNCTIONS[d["function"]])[0].items()}} for n, d in enumerate(found)]
    parts = [{"start": a, "end": b, "asks": round(asking[n]["p_true"], 3), "demands": [d["function"] for d in demands if d["part"] == n],
              "hole": round(scores[n]["none"], 3) if n in scores and not any(d["part"] == n for d in demands) else None,
              "scores": {name: round(q, 3) for name, q in scores.get(n, {}).items()}} for n, (a, b) in enumerate(spans)]
    pieces, at = [], 0
    for part, said_here in zip(parts, quoted):  # the whole message as a template: a part that demands or abstains is a slot, the rest is plain text
        if part["demands"] or part["hole"] is not None:
            value = tuple(FUNCTIONS[name] for name in part["demands"]) or Hole
            pieces += [str(text[at:part["start"]]), Interpolation(value, " + ".join(part["demands"]) or "?", None, said_here)]
            at = part["end"]
    return Template(*pieces, str(text[at:])), demands, parts, p


def expression(demand: dict, demands: list, seen: tuple = ()) -> ast.Call:
    """A demand as a Python call. A value from the words is a constant or a member of its sum type. The result of another
    demand is that demand's call, inside this one. An open hole is `...`."""
    f = FUNCTIONS[demand["function"]]

    def value(tp, path: str) -> ast.expr | None:
        hole = demand["parameters"].get(path, {})
        match tp:
            case type() if dataclasses.is_dataclass(tp):  # a product type: 1 argument for each field
                return ast.Call(ast.Name(tp.__name__), [], [ast.keyword(field, v) for field, inner in typing.get_type_hints(tp).items() if (v := value(inner, f"{path}.{field}"))])
            case types.UnionType() if not hole.get("value"):  # T | None with nothing found: the argument is left out
                return None if type(None) in typing.get_args(tp) else ast.Constant(...)
            case types.GenericAlias() if hole.get("value") and hole.get("by") != By.RESULT:  # several of 1 type: a list of them
                inner, = typing.get_args(tp)
                return ast.List([ast.Call(ast.Name(kind(inner)), [ast.Constant(one)], []) for one in hole["value"].split(", ")])
            case types.UnionType() | types.GenericAlias():
                tp = next(inner for inner in typing.get_args(tp) if inner is not type(None))
        if hole.get("by") == By.RESULT:  # another demand of the message makes this value
            other = next(d for d in demands if d["function"] == hole["value"])
            return expression(other, demands, (*seen, demand["function"])) if other["function"] not in seen else ast.Constant(...)
        if not hole.get("value"):
            return ast.Constant(...)  # an open hole
        constant = ast.Constant(int(hole["value"]) if tp is int else hole["value"] == "yes" if tp is bool else hole["value"])
        return constant if tp in (int, str, bool) else ast.Call(ast.Name(kind(tp)), [constant], [])

    return ast.Call(ast.Name(f.__name__), [], [ast.keyword(name, v) for name, tp in typing.get_type_hints(f).items() if name != "return" and (v := value(tp, name))])


def call(demand: dict, demands: list) -> str:
    return ast.unparse(expression(demand, demands))


def run(demand: dict, demands: list) -> str | None:
    """The result of a demand, if the world gives its function a body and the message fills every hole. The text has the brand
    Observed: code produced it. A function with no body is work for the reader, and run() leaves it."""
    tree = expression(demand, demands)
    body = ast.parse(textwrap.dedent(inspect.getsource(FUNCTIONS[demand["function"]]))).body[0].body
    written = [node for node in body if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant))]  # a docstring or ... is no body
    still_open = [node for node in ast.walk(tree) if isinstance(node, ast.Constant) and node.value is ...]
    if not written or still_open:
        return None
    try:
        return Observed(repr(eval(compile(ast.fix_missing_locations(ast.Expression(tree)), "<demand>", "eval"), vars(world) | {"Path": pathlib.Path}))[:300])
    except Exception as error:  # the world's own code failed: say so, and let the reader do the work
        return Observed(f"{type(error).__name__}: {error}"[:300])


def handle(event: dict, ask=d1) -> dict | None:
    """1 event in, the answer for Claude Code out. The log is the only state: each event is 1 line of events.jsonl."""
    text = received(event)
    mine = [record for record in history() if record["session"] == event.get("session_id")]
    asked = [n for n, record in enumerate(mine) if record["event"] == "UserPromptSubmit"]
    record, answer = stamp() | {"event": event["hook_event_name"], "session": event.get("session_id"), "brand": type(text).__name__, "text": text}, None
    match text:
        case Asked():
            template, demands, parts, p = read(text, ask)
            demands = [d | {"python": call(d, demands)} | ({"result": result} if (result := run(d, demands)) else {}) for d in demands]
            record |= {"demands": demands, "parts": parts, "p": p, "template": [piece if isinstance(piece, str) else {"words": piece.format_spec, "is": piece.expression} for piece in template]}
            asking = [(n, part, [d for d in demands if d["part"] == n]) for n, part in enumerate(parts) if part["demands"] or part["hole"]]
            lines = [f"scriptt: d1 read this message against .scriptt/world.py. Parts: {len(parts)}. Parts that ask for something: {len(asking)}."]
            for n, part, found in asking:  # 1 line for each part that asks for something: what it demands, how sure d1 is, and its first words
                near = max(((q, name) for name, q in part["scores"].items() if name != "none"), default=(0, ""))
                what = " + ".join(d["python"] + f" {d['p']:.2f}" + (f" = {d['result']}" if d.get("result") else "") for d in found) or f"?  d1 abstains: no function of the world fits. The closest is {near[1]} {near[0]:.2f}."
                lines += [f'{n + 1}. {what}   "{text[part["start"]:part["end"]][:90]}"']
            lines += [f"-. {d['python']} {d['p']:.2f}   (the message as a whole)" for d in demands if d["part"] is None]
            if any(part["hole"] for part in parts):
                lines += ['For each "?": say in 1 line what the part asks, do it, and propose the line to add to .scriptt/world.py.']
            if any("..." in d["python"] for d in demands):
                lines += ["An argument that is ... is a hole that the message does not fill. Fill it from the conversation, or ask for that 1 thing."]
            if any(d.get("result") for d in demands):
                lines += ['"= value" after a call: the world gives that function a body, and the harness ran it. The value is observed.']
            if asked:  # what came after the last message: the reply check, and the corrections of the user (the last one for each message)
                after = mine[asked[-1]:]
                before = mine[asked[-1]]  # the message before this one, and d1's check of the reply to it. Only what d1 is sure of.
                missed = [f'{d["function"]} ("{d["words"][:60]}")' for r in after[-1:] if r["event"] == "Stop" for d in before["demands"] if r.get("checks", {}).get(d["function"], 1) < 0.2]
                lines += [f"d1 says your last reply did not do: {', '.join(missed)}. Check that against your reply."] * bool(missed)
                for r in {(r["text"], r["part"]): r for r in after if r["event"] == "Disagree"}.values():  # the last reading of each part
                    things = "".join(f', {path} is "{value}"' if value else f", {path} is open" for path, value in r["things"].items())
                    lines += [f'The user says that "{r["words"][:90]}" asks for {" + ".join(r["demands"]) or "nothing"}{things}. d1 said otherwise.']
            answer = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "\n".join(lines)}}
        case Written() if asked and ((last := mine[asked[-1]])["demands"] or any(part["hole"] for part in last["parts"])):
            state = f"MESSAGE:\n{last['text']}\n\nREPLY:\n{text}"
            questions = {d["function"]: yes(DID(FUNCTIONS[d["function"]])) for d in last["demands"] if d["function"] in FUNCTIONS}
            questions |= {f"part {n + 1}": yes(ANSWERED(last["text"][part["start"]:part["end"]][:300])) for n, part in enumerate(last["parts"]) if part["hole"]}
            done = put(ask, state, questions)
            record["checks"] = {id: round(a["p_true"], 3) for id, a in done.items()}
            demanded = [q for id, q in record["checks"].items() if id in FUNCTIONS]  # a reply goes back only when it does none of the demanded functions
            if max(demanded, default=1) < 0.5 and config().get("block") and not event.get("stop_hook_active"):
                answer = {"decision": "block", "reason": "scriptt: d1 says the reply does none of what the message asked: " + ", ".join(questions)}
    with LOG.open("a") as file:
        file.write(json.dumps(record | {"answer": answer}) + "\n")
    return answer


def describe() -> dict:
    """The world as data, for the page and the mod: each function, and each type of the world that a signature reaches."""
    def reach(tp) -> dict:
        match tp:
            case enum.EnumType():
                return {tp.__name__: {"sum": [m.value for m in tp], "doc": tp.__doc__}}
            case type() if dataclasses.is_dataclass(tp):
                inner = typing.get_type_hints(tp)
                return {tp.__name__: {"product": {field: kind(t) for field, t in inner.items()}, "doc": tp.__doc__}} | {k: v for t in inner.values() for k, v in reach(t).items()}
            case types.UnionType() | types.GenericAlias():
                return {k: v for t in typing.get_args(tp) for k, v in reach(t).items()}
        return {}

    hints = {name: typing.get_type_hints(f) for name, f in FUNCTIONS.items()}
    return {"types": {k: v for h in hints.values() for tp in h.values() for k, v in reach(tp).items()},
            "functions": {name: {"asks": f.__doc__, "returns": kind(signature(f)[1]), "holes": {path: kind(tp) for path, tp in signature(f)[0].items()}} for name, f in FUNCTIONS.items()}}


def install():
    """Add the 2 hooks to .claude/settings.local.json of the folder above this one, copy the skill, and write config.json if there is none."""
    settings = HOME.parent / ".claude" / "settings.local.json"
    settings.parent.mkdir(exist_ok=True)
    data = json.loads(settings.read_text()) if settings.exists() else {}
    hook = {"hooks": [{"type": "command", "command": f'"{sys.executable}" "{HOME / "harness.py"}"', "timeout": 60}]}
    for name in ("UserPromptSubmit", "Stop"):  # the 2 events of Claude Code that carry a text
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
    """Print each part of each logged message that has all these words in its text or among its functions. "?" finds the parts
    that d1 abstained on, each with the closest function. A line that was read with another world.py than the one now is marked."""
    now = stamp()["world"]
    for record in history():
        for n, part in enumerate(record.get("parts", [])):
            tags = part["demands"] + ["?"] * (part["hole"] is not None)
            said = " ".join(record["text"][part["start"]:part["end"]].split())
            if tags and all(word in tags or (word != "?" and word.lower() in said.lower()) for word in words):
                near = max(((q, name) for name, q in part.get("scores", {}).items() if name != "none"), default=None)
                closest = f"  closest: {near[1]} {near[0]:.2f}" if near and part["hole"] is not None else ""
                print(f'{record["at"][:16]}  {record["session"][:8]}  part {n + 1}  [{" + ".join(tags)}]{closest}{"  (an older world.py)" * (record["world"] != now)}  {said[:160]}')


if __name__ == "__main__":
    match sys.argv[1:]:
        case ["install"]:
            install()
        case ["find", *words]:
            find(words)
        case ["reading"]:  # the user's reading of 1 part, as JSON on stdin (the mod sends it)
            reading(json.load(sys.stdin))
        case ["world"]:  # the world as JSON (the mod and the page list its functions)
            print(json.dumps(describe()))
        case ["serve", *port]:
            serve(int(port[0]) if port else 8787)
        case _:
            try:
                answer = handle(json.load(sys.stdin))
            except Exception as error:  # a hook must not stop the session: say what failed and let Claude go on
                sys.exit(print(f"scriptt: {type(error).__name__}: {error}", file=sys.stderr))
            if answer is not None:
                print(json.dumps(answer))
