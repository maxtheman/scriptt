#!/usr/bin/env python3
"""The scriptt harness. 1 file, beside world.py. Python 3.14 or later, standard library only.

Claude Code runs it as a hook, with 1 event as JSON on stdin:
  UserPromptSubmit   d1 decides which computations of the world each part of the message demands, and code maps the typed
                     pieces of the message into their holes. Claude receives the reading, and the holes that stay open.
  Stop               d1 checks the reply against each demand. With "block": true in config.json, a reply that does none of them is sent back.
You run it for the rest:
  python harness.py install        add the 2 hooks and the skill to .claude/ of the folder above this one
  python harness.py serve [port]   show the events on a page where you drag to disagree
  python harness.py find WORDS     the parts of every logged message that have these words, this function, or a piece of this type
                                   or value. find "?" lists the parts that d1 abstained on: the candidates for a new line of world.py

Everything is beside this file: world.py (the whitelist), config.json (where d1 is), events.jsonl (the log).
"""

import ast
import concurrent.futures
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

VERSION = "0.1.6"  # of the harness
FORM = 3  # of a line of events.jsonl. Change it when a key changes its meaning, and add the step to migrate().
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
    PIECE = "the piece"  # the words stand for a piece that the session named before, and d1 said yes


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
    """A line of the log in the current form. Form 1 (0.1.1) had no parts: its demands were found for the whole message.
    Form 2 (0.1.5) had no choice in a part and no pieces."""
    if record.get("form", 1) < 2 and record["event"] == "UserPromptSubmit":
        record = record | {"form": 2, "parts": [], "demands": [d | {"part": None, "by": By.MESSAGE} for d in record.get("demands", [])]}
    if record.get("form", 1) < 3 and record["event"] == "UserPromptSubmit":
        record = record | {"parts": [part | {"choice": chosen(part["scores"]) if "scores" in part else (part["demands"] or ["none" if part["hole"] is not None else "nothing"])[0]}
                                     for part in record["parts"]], "pieces": []}  # the first lines of 0.1.5 have no scores
    return record | {"form": FORM}


def chosen(scores: dict) -> str:
    """The choice for 1 part, from d1's shares: the function with the largest share if it gets more than "none" and "nothing"
    together. Else "none" (d1 abstains) if "none" gets half or more. Else "nothing"."""
    top = max((name for name in scores if name not in ELSE), key=scores.get, default=None)
    return top if top and scores[top] > scores["none"] + scores["nothing"] else "none" if scores["none"] >= 0.5 else "nothing"


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

# The wordings, in 1 place. Each was compared with others on recorded messages and on 2 trial folders, with the real d1-2b (tests/README.md of the repository).
WHAT = "What does this text ask the reader to do?"
ELSE = {"none": "something else that it asks the reader to do or to answer", "nothing": "nothing: it is a remark, a reason, a rule or a greeting"}  # the 2 options that are no function
NAMES = lambda name, f: t"The text asks the reader to {f}. Which {name} does the text name for that?"
SAYS = lambda name: t"Does the text say: {name}?"
WHICH = lambda name: t"Which words of the text say the {name}?"
IS = lambda value, name, f: t'The message asks the reader to {f}. In the message, are the words "{value}" the {name} for that?'
WITH = lambda f, g: t"Does the message ask the reader to {f} with the result of this: {g}?"
REFERS = lambda word, value: t"In the last sentence, does [{word}] mean {value}?"  # the state: the sentence that names the value, then the sentence with [the words]
REFER = r"\b(?:it|them|that|this|these|those|both|the same)\b"  # words that stand for a thing named before: the only list of words in the harness
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
    """The holes of a parameter, as (path, type): the parameter, or for a product type (a dataclass) the holes of each field.
    The function calls itself for each field, and for the product type inside a union."""
    if dataclasses.is_dataclass(tp):
        return [hole for field, inner in typing.get_type_hints(tp).items() for hole in holes(inner, f"{path}.{field}")]
    product = next((inner for inner in typing.get_args(tp) if dataclasses.is_dataclass(inner)), None) if isinstance(tp, types.UnionType) else None
    return holes(product, path) if product else [(path, tp)]  # T | None with a product type T: the holes of T


def signature(f) -> tuple[dict, type]:
    """The holes of a function of the world, as {path: type}, and the type of its result."""
    hints = typing.get_type_hints(f)
    return dict(hole for parameter, tp in hints.items() if parameter != "return" for hole in holes(tp, parameter)), hints["return"]


def places(tp, text: str) -> list:
    """Each place in the text where a value of this type stands, found by code, as (start, end, type, value). The function
    calls itself for the types inside a union, a list and a product type. A str or a bool has no place that code can find."""
    match tp:
        case enum.EnumType():  # a sum type: each place of the name of each member
            return [(m.start(), m.end(), kind(tp), member.value) for member in tp for m in re.finditer(rf"\b{re.escape(member.value)}\b", text, re.I)]
        case types.UnionType() | types.GenericAlias():
            return [place for inner in typing.get_args(tp) for place in places(inner, text)]
        case type() if dataclasses.is_dataclass(tp):
            return [place for inner in typing.get_type_hints(tp).values() for place in places(inner, text)]
        case type() if tp is int:  # a number. No part of a version such as 0.1.6 or of a time such as 05:15, and no list number such as "2. "
            return [(m.start(), m.end(), "int", m[0]) for m in re.finditer(r"(?<![\w.:])\d+(?!\w|[.:]\d|\.\s)", text)]
        case type() if tp is pathlib.Path:
            return [(m.start(), m.start() + len(m[0].rstrip(".")), "Path", m[0].rstrip(".")) for m in re.finditer(r"(?:[~.]{0,2}/)?[\w.-]+(?:/[\w.-]+)+|\b[\w-]+\.[a-z]{1,5}\b", text)]
    return []


leaves = lambda tp: {leaf for inner in typing.get_args(tp) for leaf in leaves(inner)} if isinstance(tp, types.UnionType | types.GenericAlias) else {kind(tp)}  # the types that a piece for this hole can have


def to_ask(tp, name: str, f) -> dict:
    """The questions for d1 about a hole that code did not fill, as {key: question}. The key is the value that a yes means,
    or "" for a text read, or a sum type for 1 choice among its members and "none"."""
    match tp:
        case enum.EnumType():
            return {tp: {"type": "choice", "instructions": yes(NAMES(name, f))["instructions"], "options": [{"id": m.value, "description": m.value} for m in tp] + [{"id": "none", "description": "the text names none of these"}]}}
        case types.UnionType() | types.GenericAlias():
            return {value: q for inner in typing.get_args(tp) for value, q in to_ask(inner, name, f).items()}
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


def read(text: Asked, ask, before: list = ()) -> tuple[Template, list, list, list, dict]:
    """The search. Every decision is d1's, and every option is from the world or from the message.
    1. For each part, with the part alone as the state: 1 choice among the functions of the world, "something else" and "nothing".
       If 1 function gets more than those 2 together, the part demands each function that gets a quarter or more.
       Else, if "something else" gets half or more, d1 abstains: the part is a Hole, and Claude is told to fill it, with the closest function beside it.
       Else the part is plain text: a remark, a reason, a rule or a greeting.
    2. Pieces, from the smallest typed things up: code finds each place in the message where a value of a type of the world
       (or an int or a Path) stands. Pieces do not overlap: the longest wins.
    3. For each hole of a demanded function, by its type: a free piece of that type in the part (the surest demand takes first),
       or the result of another demand of the same part that returns this type, or the value that d1 chooses. Else the hole is open.
    4. d1 checks each piece that code put in a hole, and each result. A value that d1 rejects leaves the hole open.
    5. Words that stand for a thing named before ("it", "them"): the nearest piece before them, in the message, then in the earlier
       messages of the session (before), of the type of an open hole of the part, or of any type. d1 checks it. A yes is a piece with "of",
       and it fills the hole, in place of a member that d1 chose from the part alone.
    Two trial agents and the recorded messages decided these rules: see tests/README.md of the repository.
    The template that read returns is the whole message, 1 slot for each part: "".join of its pieces is the text."""
    spans = parts_of(text)
    quoted = [text[a:b] for a, b in spans]  # each part is a part of the message: brand Asked
    options = [{"id": name, "description": f.__doc__} for name, f in FUNCTIONS.items()] + [{"id": id, "description": words} for id, words in ELSE.items()]
    together = concurrent.futures.ThreadPoolExecutor(8).map  # 1 request for each part, 8 at a time
    scores = dict(enumerate(together(lambda part: put(ask, part, {0: {"type": "choice", "instructions": say(WHAT), "options": options}})[0]["probabilities"], quoted)))
    choice = {n: chosen(scores[n]) for n in scores}
    found = [{"function": name, "p": round(q, 3), "by": By.PART, "part": n} for n, scored in scores.items() if choice[n] not in ELSE
             for name, q in scored.items() if name not in ELSE and (q >= 0.25 or name == choice[n])]
    p = {name: round(max((scored[name] for scored in scores.values()), default=0.0), 3) for name in FUNCTIONS}

    part_of = lambda at: next((n for n, (a, b) in enumerate(spans) if a <= at < b), None)
    apart = lambda a, b: all(b <= piece["start"] or piece["end"] <= a for piece in pieces)  # the words overlap no piece
    piece = lambda a, b, tp, value, by, **more: {"id": None, "part": part_of(a), "start": a, "end": b, "words": text[a:b], "type": tp, "value": value, "by": by, "to": None, "of": None} | more
    pieces = []
    for a, b, tp, value in sorted({place for tp in [*(tp for f in FUNCTIONS.values() for tp in signature(f)[0].values()), int, pathlib.Path] for place in places(tp, text)}, key=lambda place: place[0] - place[1]):
        pieces += [piece(a, b, tp, value, By.WORDS)] * (apart(a, b) and part_of(a) is not None)  # the longest first

    wanted = {(n, path): tp for n, d in enumerate(found) for path, tp in signature(FUNCTIONS[d["function"]])[0].items()}
    said = {}
    for key in sorted(wanted, key=lambda key: -found[key[0]]["p"]):  # the surest demand takes a piece first. A piece fills 1 hole, and a list hole takes each.
        free = [one for one in sorted(pieces, key=lambda one: one["start"]) if one["part"] == found[key[0]]["part"] and one["type"] in leaves(wanted[key]) and not any(one in taken for taken in said.values())]
        said[key] = free[:None if typing.get_origin(wanted[key]) is list else 1]
    value = lambda key: ", ".join(one["value"] for one in said[key])
    made = {key: next((d["function"] for m, d in enumerate(found) if m != key[0] and d["part"] == found[key[0]]["part"] and getattr(tp, "__module__", "") == "world" and signature(FUNCTIONS[d["function"]])[1] is tp), None)
            for key, tp in wanted.items() if not said[key]}
    role = lambda key: (FUNCTIONS[found[key[0]]["function"]], key[1].split(".")[-1].replace("_", " "))
    open_ = {(key, value): q for key, tp in wanted.items() if not said[key] and not made[key] for value, q in to_ask(tp, role(key)[1], role(key)[0]).items()}
    told = put(ask, text, {(key, None): yes(IS(value(key), role(key)[1], role(key)[0])) for key in wanted if said[key]}
               | {(key, None): yes(WITH(role(key)[0], FUNCTIONS[made[key]])) for key in wanted if made.get(key)})
    for filled in together(lambda n: put(ask, quoted[n], {k: q for k, q in open_.items() if found[k[0][0]]["part"] == n}), {found[key[0]]["part"] for key, _ in open_}):
        told |= filled  # d1 fills a hole from the part alone: a thing that another sentence names is no argument here

    def fill(key, tp) -> dict:
        hole = {"type": kind(tp), "value": None, "by": None}
        check = round(told[key, None]["p_true"], 3) if (key, None) in told else None
        if said[key] or made.get(key):  # code found it. d1 checks it, and a value that d1 rejects leaves the hole open.
            filled, by = (value(key), By.WORDS) if said[key] else (made[key], By.RESULT)
            for one in said[key] * (check >= 0.5):
                one["to"] = {"demand": key[0], "path": key[1]}
            return hole | {"value": filled, "by": by, "d1": check} if check >= 0.5 else hole | {"rejected": filled, "d1": check}
        answers = {value: a for (other, value), a in told.items() if other == key and value is not None}
        if "" in answers:  # a text read: the words that d1 points at, if the message has them. They are a piece if they overlap none.
            a, at = answers[""], text.find(answers[""]["text"] or "\0")
            if a["found"] < 0.5 or at < 0 or len(a["text"]) > 60:
                return hole
            pieces.extend([piece(at, at + len(a["text"]), "str", a["text"], By.D1, d1=round(a["found"], 3), to={"demand": key[0], "path": key[1]})] * apart(at, at + len(a["text"])))
            return hole | {"value": a["text"], "by": By.D1, "d1": round(a["found"], 3)}
        share = {value: a["p_true"] for value, a in answers.items() if "p_true" in a} | {m: q for a in answers.values() for m, q in a.get("probabilities", {}).items() if m != "none"}
        best = max(share, key=share.get, default=None)  # a yes, or the member that d1 chose in its sum type
        hole |= {"names_none": round(q, 3) for a in answers.values() if (q := a.get("probabilities", {}).get("none", 0)) >= 0.5}  # d1: the part names no member of the sum type
        return hole | {"value": best, "by": By.D1, "d1": round(share[best], 3)} if best is not None and share[best] >= 0.5 else hole

    demands = [d | {"returns": kind(signature(FUNCTIONS[d["function"]])[1]), "words": quoted[d["part"]],
                    "parameters": {path: fill((n, path), tp) for path, tp in signature(FUNCTIONS[d["function"]])[0].items()}} for n, d in enumerate(found)]

    asks, holes_open = [], [key for key in wanted if demands[key[0]]["parameters"][key[1]]["value"] is None or demands[key[0]]["parameters"][key[1]]["by"] == By.D1 and "str" not in leaves(wanted[key])]  # open, or a member that d1 guessed from the part alone
    for word in (word for word in re.finditer(REFER, text, re.I) if choice.get(part_of(word.start()), "nothing") != "nothing" and apart(*word.span())):
        n, (a, b) = part_of(word.start()), spans[part_of(word.start())]
        key = next((key for key in holes_open if found[key[0]]["part"] == n and all(key != k for _, k, *_ in asks)), None)
        nearest = lambda types: [(one, quoted[one["part"]], {"piece": one}) for one in sorted(pieces, key=lambda one: -one["start"]) if one["end"] <= word.start() and one["type"] in types(one)] + [
            (one, r["text"][r["parts"][one["part"]]["start"]:r["parts"][one["part"]]["end"]], {"at": r["at"], "piece": one["id"]}) for r in reversed(before) for one in reversed(r.get("pieces", [])) if one["type"] in types(one)]
        key, candidates = (key, near) if key and (near := nearest(lambda one: leaves(wanted[key]))) else (None, nearest(lambda one: {one["type"]}))  # the type of the open hole, else any type
        for one, where, of in candidates[:1]:  # the nearest piece. d1 sees its sentence, then this one with the words in brackets.
            state = (where + "\n") * (where != quoted[n]) + text[a:word.start()] + f"[{word[0]}]" + text[word.end():b]
            asks += [(word, key, one, of, state, yes(REFERS(word[0], one["value"])))]
    for (word, key, one, of, *_), a in zip(asks, together(lambda asked: put(ask, asked[-2], {0: asked[-1]})[0], asks)):
        if a["p_true"] >= 0.8:  # d1 says yes: the words are a piece that stands for the other one, and it fills the open hole. 0.8: see tests/README.md of the repository
            pieces.append(piece(*word.span(), one["type"], one["value"], By.PIECE, d1=round(a["p_true"], 3), to=key and {"demand": key[0], "path": key[1]}, of=of))
            if key:
                demands[key[0]]["parameters"][key[1]] = {k: v for k, v in demands[key[0]]["parameters"][key[1]].items() if k != "names_none"} | {"value": one["value"], "by": By.PIECE, "d1": round(a["p_true"], 3)}

    pieces.sort(key=lambda one: one["start"])
    for n, one in enumerate(pieces):  # each piece gets its number, and each hole that a piece fills names it
        one["id"] = n
        if one["to"]:
            demands[one["to"]["demand"]]["parameters"][one["to"]["path"]].setdefault("piece", n)
        if one["of"] and "at" not in one["of"]:  # a reference in this message: the piece that it stands for is before it, and has its number
            one["of"] = {"piece": one["of"]["piece"]["id"]}
    parts = [{"start": a, "end": b, "asks": round(1 - scores[n]["nothing"], 3), "choice": choice[n], "demands": [d["function"] for d in demands if d["part"] == n],
              "hole": round(scores[n]["none"], 3) if choice[n] == "none" else None,
              "scores": {name: round(q, 3) for name, q in scores[n].items()}} for n, (a, b) in enumerate(spans)]
    slots, at = [], 0
    for part, said_here in zip(parts, quoted):  # the whole message as a template: each part is a slot, and what is between the parts is plain text
        slots += [str(text[at:part["start"]]), Interpolation(tuple(FUNCTIONS[name] for name in part["demands"]) or Hole, " + ".join(part["demands"]) or {"none": "?"}.get(part["choice"], part["choice"]), None, said_here)]
        at = part["end"]
    return Template(*slots, str(text[at:])), demands, parts, pieces, p


def expression(demand: dict, demands: list, seen: tuple = ()) -> ast.Call:
    """A demand as a Python call. A value from the words is a constant or a member of its sum type. The result of another
    demand is that demand's call, inside this one. An open hole is `...`."""
    f = FUNCTIONS[demand["function"]]

    def value(tp, path: str) -> ast.expr | None:
        hole = demand["parameters"].get(path, {})
        match tp:
            case type() if dataclasses.is_dataclass(tp):  # a product type: 1 argument for each field
                return ast.Call(ast.Name(tp.__name__), [], [ast.keyword(field, v) for field, inner in typing.get_type_hints(tp).items() if (v := value(inner, f"{path}.{field}"))])
            case types.UnionType() if (product := next((inner for inner in typing.get_args(tp) if dataclasses.is_dataclass(inner)), None)):
                made = value(product, path)  # T | None with a product type T: left out when the message fills no field of it
                return None if type(None) in typing.get_args(tp) and all(isinstance(k.value, ast.Constant) and k.value.value is ... for k in made.keywords) else made
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
            template, demands, parts, pieces, p = read(text, ask, [mine[n] for n in asked])
            demands = [d | {"python": call(d, demands)} | ({"result": result} if (result := run(d, demands)) else {}) for d in demands]
            record |= {"demands": demands, "parts": parts, "pieces": pieces, "p": p, "template": [piece if isinstance(piece, str) else {"words": piece.format_spec, "is": piece.expression} for piece in template]}
            literal = lambda one: (f'"{one["words"]}" = ' if one["of"] else "") + (str(int(one["value"])) if one["type"] == "int" else repr(one["value"]) if one["type"] == "str" else f"{one['type']}({one['value']!r})") + (
                "" if not one["of"] else " (an earlier message)" if "at" in one["of"] else f" (part {pieces[one['of']['piece']]['part'] + 1})")  # a piece as Python, and a reference with its words and where its piece is
            named = lambda n: "".join(f" [{', '.join(map(literal, free))}]" for free in [[one for one in pieces if one["part"] == n and (one["to"] is None or one["of"])]] if free)
            lines = [f"scriptt: d1 read this message against .scriptt/world.py. Parts: {len(parts)}. Parts that ask for something: {sum(part['choice'] != 'nothing' for part in parts)}."]
            for n, part in enumerate(parts):  # 1 line for each part that asks for something: what it demands, how sure d1 is, the pieces that no hole takes, and its first words
                if part["choice"] != "nothing":
                    near = max(((q, name) for name, q in part["scores"].items() if name not in ELSE), default=(0, ""))
                    unnamed = lambda d: "".join(f"  (d1: the part names no {hole['type']})" for hole in d["parameters"].values() if hole.get("names_none") and "None" not in hole["type"])
                    what = " + ".join(d["python"] + f" {d['p']:.2f}" + (f" = {d['result']}" if d.get("result") else "") + unnamed(d) for d in demands if d["part"] == n) or f"?  d1 abstains: no function of the world fits. The closest is {near[1]} {near[0]:.2f}."
                    lines += [f'{n + 1}. {what}{named(n)}   "{text[part["start"]:part["end"]][:90]}"']
            quiet = [f"{n + 1}{named(n)}" for n, part in enumerate(parts) if part["choice"] == "nothing"]
            lines += [f"Nothing: {', '.join(quiet)}."] * bool(quiet)
            lines += [f"-. {d['python']} {d['p']:.2f}   (the message as a whole)" for d in demands if d["part"] is None]
            if any(part["hole"] for part in parts):
                lines += ['For each "?": say in 1 line what the part asks, do it, and propose the line to add to .scriptt/world.py.']
            if any(d.get("result") for d in demands):
                lines += ['"= value" after a call: the world gives that function a body, and the harness ran it. The value is observed.']
            if asked:  # what came after the last message: the reply check, and the corrections of the user (the last one for each message)
                after = mine[asked[-1]:]
                before = mine[asked[-1]]  # the message before this one, and d1's check of the reply to it. Only what d1 is sure of.
                missed = [f'{d["function"]} ("{d["words"][:60]}")' for r in after[-1:] if r["event"] == "Stop" for d in before["demands"] if r.get("checks", {}).get(d["function"], 1) < 0.2
                          and not any(hole.get("names_none") and "None" not in hole["type"] for hole in d["parameters"].values())]  # a call that d1 itself marked is no ask to repeat
                lines += [f"d1 says your last reply did not do: {', '.join(missed)}. Check that against your reply."] * bool(missed)
                for r in {(r["text"], r["part"]): r for r in after if r["event"] == "Disagree"}.values():  # the last reading of each part
                    things = "".join(f', {path} is "{value}"' if value else f", {path} is open" for path, value in r["things"].items())
                    lines += [f'The user says that "{r["words"][:90]}" asks for {" + ".join(r["demands"]) or "nothing"}{things}. d1 said otherwise.']
            gaps = [f'{d["part"] + 1}. {d["function"]}.{path}: {hole["type"]}   "{d["words"][:90]}"' for d in demands for path, hole in d["parameters"].items() if hole["value"] is None and "None" not in hole["type"]]
            lines += ["Open holes, each a ... above. Fill each from the conversation, or ask for that 1 thing:", *gaps] * bool(gaps)
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
                return {tp.__name__: {"fields": {field: kind(t) for field, t in inner.items()}, "doc": tp.__doc__}} | {k: v for t in inner.values() for k, v in reach(t).items()}
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
    mine = {"session", "text", "part": its number from 0, "demands": [function names], "things": {"<function>.<hole path>": value, or None for an open hole}}"""
    message = next(r for r in reversed(history()) if r["event"] == "UserPromptSubmit" and r["session"] == mine["session"] and r["text"] == mine["text"])
    part = message["parts"][mine["part"]]
    record = stamp() | {"event": "Disagree", "session": mine["session"], "text": mine["text"], "part": mine["part"], "words": mine["text"][part["start"]:part["end"]],
                        "demands": [name for name in mine["demands"] if name in FUNCTIONS], "things": {key: value for key, value in mine.get("things", {}).items() if key.split(".")[0] in FUNCTIONS}}
    with LOG.open("a") as file:
        file.write(json.dumps(record) + "\n")


def find(words: list) -> None:
    """Print each part of each logged message that has all these words in its text, among its functions, among the types of its
    pieces or in their values. "?" finds the parts
    that d1 abstained on, each with the closest function. A line that was read with another world.py than the one now is marked."""
    now = stamp()["world"]
    for record in history():
        for n, part in enumerate(record.get("parts", [])):
            tags = part["demands"] + ["?"] * (part["hole"] is not None) + [one["type"] for one in record["pieces"] if one["part"] == n]
            said = " ".join(record["text"][part["start"]:part["end"]].split())
            values = " ".join(one["value"] for one in record["pieces"] if one["part"] == n)  # a reference matches by the value that it stands for
            if tags and all(word in tags or (word != "?" and word.lower() in f"{said} {values}".lower()) for word in words):
                near = max(((q, name) for name, q in part.get("scores", {}).items() if name not in ELSE), default=None)
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
