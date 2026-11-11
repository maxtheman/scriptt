"""Tests of agree.py and scriptt16.py with a stand-in d1, against the independent oracle in expected.py.

The stand-in answers by meaning, from each case's script, so the tests check
the type system, the search and the transitions. They do not measure the real d1.

    cd next && python3.14 test_scriptt16.py

The run prints where it ran and what it imported, runs the unit tests, every
case of expected.py through ``observe``, the oracle's wrong projections over
the observed results, the six wrong implementations as scoped monkeypatches of
the engine, and the location checks. It exits non-zero on any failure.
"""

import contextlib
import dataclasses
import json
import os
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / ".scriptt")]
import agree
import expected as X
import scriptt16
from scriptt16 import Application, Constant, Empty, Hole, Record, Several, Unresolved

WORLD = '''
import dataclasses, enum, pathlib, typing

Words = typing.NewType("Words", str)
Asked = typing.NewType("Asked", Words)
Written = typing.NewType("Written", Words)
Observed = typing.NewType("Observed", Words)

class Surface(enum.Enum):
    "what the user looks at"
    PAGE: Asked = "the page"
    MOD: Asked = "the mod"

class Cell(typing.NamedTuple):
    "a cell of a notebook"
    notebook: pathlib.Path
    number: int

@dataclasses.dataclass
class Review:
    "a review of a cell, with the evidence"
    cell: Cell
    evidence: Many[Words]

type Subject = Surface | pathlib.Path

def redesign(surface: Surface) -> Later[Surface]:
    "change how it looks"

def show(subject: Subject) -> Subject:
    "show it"

def compare(surfaces: Many[Surface]) -> Written:
    "compare several of them"

def open_cell(cell: Cell) -> Observed:
    "open a cell"

def review(review: Review) -> Later[Written]:
    "review a cell"

def follow(rule: Asked) -> None:
    "follow a rule"

def approve(review: Review) -> Asked:
    "approve a review"

def explain(subject: Maybe[Words]) -> Written:
    "explain something"
'''


def world_of(source: str, folder: pathlib.Path = HERE) -> agree.World:
    """Loads a world from the text of a world.py file."""
    return agree.loads(source, folder)


# ---- The adapter: engine data in, the oracle's neutral form out -------------------


def lit(constant: Constant) -> X.Lit:
    """Returns a constant as a neutral literal."""
    value = constant.value
    return X.Lit(agree.show(constant.type), value.words if isinstance(value, agree.Member) else value if isinstance(value, int) else str(value))


def neutral(term, index: dict[int, int] | None):
    """Projects a term. A result is Ref by identity (``index``), or by its number while a reading is being built (``index`` None)."""
    match term:
        case Constant():
            return lit(term)
        case Application():
            if term.number is None and (index is None or id(term) not in index):
                return X.New(term.function.name)
            return X.Ref(index.get(id(term), -1) if index is not None else term.number)  # -1: an operation that is no obligation of the reading
        case Record():
            return X.New(term.product.name)
        case Several(terms=terms):
            return tuple(neutral(one, index) for one in terms) if terms else X.EMPTY_LIST
        case Empty():
            return X.EMPTY
    return X.Hole(agree.show(term.type), term.reason)


def index_of(reading) -> dict[int, int]:
    """Returns the obligation index of each operation object of a reading, by identity."""
    return {id(term): number for number, (_, term) in enumerate(scriptt16.obligations(reading))}


def at(reading, phrase) -> tuple[str, tuple[int, int]]:
    """Returns the stripped text of a phrase and its characters in the message."""
    text = reading.text[phrase.start:phrase.end]
    start = phrase.start + len(text) - len(text.lstrip())
    return text.strip(), (start, start + len(text.strip()))


def project_obligation(reading, phrase, term, index) -> X.Obligation:
    """Projects one obligation from the engine's own judgments."""
    (span, place), brand = at(reading, phrase), phrase.brand.name
    if isinstance(term, Unresolved):
        return X.Obligation(span, X.UNRESOLVED, {}, None, term.reason, brand, None, None, place)
    values = {path: neutral(one, index) for path, one in scriptt16.bindings(term).items()}
    return X.Obligation(span, term.function.name, values, X.PENDING if scriptt16.pending(term) else X.AVAILABLE, None, brand,
                        scriptt16.complete(term), scriptt16.ready(reading, term), place)


TAGS = {scriptt16.NONE: X.ABSTAIN, scriptt16.NOTHING: X.NO_REQUEST}


def project_decisions(reading) -> list[X.Decision]:
    """Projects every recorded request of d1: about an operation, a binding, or the grouping of phrases."""
    index, found = index_of(reading), []
    by_number = {term.number: number for number, (_, term) in enumerate(scriptt16.obligations(reading))}
    for request in reading.requests:
        asked, answers = request["asked"], request["answers"] if isinstance(request["answers"], dict) else {}
        keys = list(asked)
        offered = [neutral(one, index) for one in request["offered"]]
        questions = tuple((asked[key]["instructions"], tuple(one["description"] for one in asked[key].get("options", []))) for key in keys)
        if asked[keys[0]]["type"] == "boolean":
            shares = {key: scriptt16.answer(scriptt16.YesNo(asked[key]["instructions"]), answers.get(key)) for key in keys}
            named = (lambda key: offered[int(key)]) if offered else (lambda key: key)
            chosen = X.INVALID if None in shares.values() else tuple(named(key) for key in keys if shares[key] >= scriptt16.Limits().yes)
            scores = tuple((named(key), share) for key, share in shares.items())
        else:
            question = asked[keys[0]]
            choice = scriptt16.answer(scriptt16.OneOf(question["instructions"], {one["id"]: one["description"] for one in question["options"]}), answers.get(keys[0]))
            named = lambda key: offered[int(key)] if key.isdigit() else ({"none": X.REJECT, "absent": X.ABSENT} if request["function"] else TAGS).get(key, key)
            chosen = X.INVALID if choice.best is None else named(choice.best)
            scores = tuple((named(key), share) for key, share in choice.shares.items())
            if not request["function"]:
                offered = [TAGS.get(one["id"], one["id"]) for one in question["options"]]
        found.append(X.Decision(by_number.get(request["operation"]), request["path"], "model", tuple(offered), chosen,
                                tuple(neutral(one, index) for one in request["cut"]), request["state"], questions, scores))
    return found


def project_correction(reading, correction: dict) -> X.Correction:
    """Projects a correction; its value is the saved term record."""
    by_number = {term.number: number for number, (_, term) in enumerate(scriptt16.obligations(reading))}
    value = correction["value"]
    if "ref" in value:
        shown = X.Ref(by_number.get(int(value["ref"])))
    elif "constant" in value:
        shown = X.Lit(value["type"], value["constant"])
    else:
        shown = X.Hole(value.get("hole"), value.get("reason"))
    return X.Correction(by_number.get(correction["operation"]), correction["path"], shown, correction["status"], correction["reason"])


def projected(reading) -> dict:
    """Returns the reading's keys of a step: obligations, passages, decisions, diagnostics and corrections."""
    index = index_of(reading)
    entries = scriptt16.obligations(reading)
    by_number = {term.number: number for number, (_, term) in enumerate(entries)}
    return {"obligations": [project_obligation(reading, phrase, term, index) for phrase, term in entries],
            "passages": [X.Passage(*at(reading, phrase)[:1], phrase.brand.name, "user" if phrase.quotes is None else f"reply {phrase.quotes}", relation, at(reading, phrase)[1])
                         for phrase, relation in scriptt16.passages(reading)],
            "decisions": project_decisions(reading),
            "diagnostics": [(by_number.get(number), path, rule) for number, path, rule in scriptt16.diagnostics(reading)],
            "corrections": [project_correction(reading, one) for one in reading.corrections]}


# ---- The stand-in d1 -------------------------------------------------------------


class Standin:
    """d1 answering by meaning from a case's script. It sees each request's candidates through ``watch``."""

    def __init__(self, script: dict):
        self.script, self.watch, self.calls, self.requests = script, [], 0, []

    def phrase(self, state: str) -> str:
        """Looks a phrase up: exact; else the longest scripted phrase inside it; else the shortest that holds it."""
        known = set(self.script["ops"]) | {key[0] for key in self.script["binds"]}
        if state in known:
            return state
        within = sorted((one for one in known if one in state), key=len, reverse=True)
        holding = sorted((one for one in known if state in one), key=len)
        return (within or holding or [state])[0]

    def __call__(self, state: str, asked: dict) -> dict:
        self.calls += 1
        self.requests += [X.Request(state, question["instructions"], tuple(one["description"] for one in question.get("options", []))) for question in asked.values()]
        request = next((one for one in reversed(self.watch) if one["asked"] is asked), None)
        phrase, answers = self.phrase(state), {}
        for key, question in asked.items():
            if key.startswith("did ") or key == "join":
                answers[key] = {"p_true": self.script.get("judge", 0.1)}
                continue
            ids = [one["id"] for one in question.get("options", [])]
            if key in ("what", "also"):
                asked_before = [one for one in self.watch if one["state"] == state and set(one["asked"]) & {"what", "also"} and one is not request]
                since = 0 if key == "what" else len(asked_before) - max((place for place, one in enumerate(asked_before) if "what" in one["asked"]), default=len(asked_before))
                ops = self.script["ops"].get(phrase, X.NO_REQUEST)
                want = (ops[since] if since < len(ops) else X.NO_REQUEST) if isinstance(ops, tuple) else (ops if since == 0 else X.NO_REQUEST)
                if isinstance(want, X.Malformed):
                    answers |= self.malformed(key, want, ids)
                    continue
                pick = {X.ABSTAIN: scriptt16.NONE, X.NO_REQUEST: scriptt16.NOTHING}.get(want, want)
                answers[key] = self.shares(ids, pick if pick in ids else scriptt16.NOTHING)
                continue
            want = self.script["binds"].get((phrase, request["function"], request["path"]), X.REJECT)
            offered = [neutral(one, None) for one in request["offered"]]
            if isinstance(want, X.Malformed):
                answers |= self.malformed(key, want, ids)
                continue
            if question["type"] == "boolean":
                answers[key] = {"p_true": 0.9 if isinstance(want, tuple) and offered[int(key)] in want else 0.1}
            else:
                pick = "absent" if want == X.ABSENT else str(offered.index(want)) if want in offered else "none"
                answers[key] = self.shares(ids, pick)
        return answers

    @staticmethod
    def malformed(key: str, want: X.Malformed, ids: list[str]) -> dict:
        """Returns a malformed answer: an id not offered, no entry, or a share that is no number."""
        return {"out_of_set": {key: {"probabilities": {"frobnicate": 1.0}}}, "missing": {}, "not_numbers": {key: {"probabilities": {(ids or ["yes"])[0]: "high"}}}}[want.kind]

    @staticmethod
    def shares(ids: list[str], pick: str) -> dict:
        return {"probabilities": {one: 0.9 if one == pick else 0.1 / (len(ids) - 1) for one in ids}}


# ---- observe(): one run of a case ----------------------------------------------------


def world_from(spec: X.World, folder: pathlib.Path) -> tuple[agree.World, str]:
    """Builds the world of a run in a folder from the oracle's frozen base, and returns it with its source."""
    source = X.world_source(spec)
    for name in spec.files:
        (folder / name).write_text("")
    return world_of(source, folder), source


def term_of(value, reading, world: agree.World, application: Application, path: str):
    """Converts a neutral value of an edit or an artifact to an engine term of this reading."""
    entries = [term for _, term in scriptt16.obligations(reading)]
    match value:
        case X.Lit(type=name, value=words):
            kind = world.types[name]
            same = [one for one in reading.constants if lit(one) == value]
            if same:
                return same[0]
            if isinstance(kind, agree.Sum):
                return next(one for one in scriptt16.members(kind) if one.value.words == words)
            return Constant(kind, pathlib.Path(words) if name == "Path" else words, -1, -1)
        case X.Ref(obligation=number):
            return entries[number] if number < len(entries) else Application(next(iter(world.functions.values())), {}, None)
        case X.Hole(type=name, reason=reason):
            return Hole(world.types[name], reason)
        case "EMPTY_LIST":
            return Several(scriptt16.place_type(application, path).argument, ())
        case "EMPTY":
            return Empty(scriptt16.place_type(application, path))
        case tuple():
            terms = tuple(term_of(one, reading, world, application, path) for one in value)
            return Several(scriptt16.place_type(application, path).argument if application else scriptt16.type_of(terms[0]), terms)
    raise ValueError(f"no engine term for {value!r}")


def edited(reading, world, change: X.Edit, correction: bool = False):
    """Applies one neutral edit through the engine. Returns the draft and its neutral diagnostics."""
    entries = [term for _, term in scriptt16.obligations(reading)]
    target = entries[change.obligation]
    value = None if change.op == "remove" else Hole(scriptt16.place_type(target, change.path), "cleared") if change.op == "clear" else term_of(change.value, reading, world, target, change.path)
    draft, found = (scriptt16.correct if correction else scriptt16.edit)(reading, target.number, change.path, value)
    by_number = {term.number: number for number, term in enumerate(entries)}
    return draft, [(by_number.get(number), path, rule) for number, path, rule in found]


@contextlib.contextmanager
def read_only(store: pathlib.Path):
    """Makes the store's write raise: the failure injection of a save."""
    store.touch()
    store.chmod(0o444)
    try:
        yield
    finally:
        store.chmod(0o644)


def observe(inputs: X.Inputs) -> dict:
    """Runs one run's inputs on the engine and returns its neutral observation (the contract is in expected.observe)."""
    with tempfile.TemporaryDirectory() as name:
        folder = pathlib.Path(name)
        world, source = world_from(inputs.world, folder)
        observation = {"world_faults": [(declared, rule) for declared, rule, _ in world.faults], "world_functions": sorted(world.functions), "steps": {}}
        model, store = Standin(inputs.script), folder / "store.jsonl"
        current, preview, corpus, readings = None, None, [], []
        for label, action in inputs.actions:
            calls, lines, asked, step = model.calls, len(scriptt16.saved(store)), len(model.requests), {}
            try:
                kind = action[0]
                if kind == "read":
                    readings = [scriptt16.read(text, world, list(inputs.replies), model, join=False, watch=model.watch) for text in inputs.messages]
                    corpus += [scriptt16.record(one) for one in readings]
                    current = readings[-1] if readings else current
                    step["error"] = None
                elif kind in ("preview", "stage", "correct"):
                    draft, found = edited(current, world, action[1], kind == "correct")
                    step |= {"accepted": not found, "diagnostics": found}
                    if not found:
                        step |= {key: value for key, value in projected(draft).items() if key != "diagnostics"}
                        if kind == "preview":
                            preview = draft
                        else:
                            current = draft
                elif kind == "cancel":
                    preview = None
                elif kind in ("save", "save_fail"):
                    try:
                        with read_only(store) if kind == "save_fail" else contextlib.nullcontext():
                            scriptt16.save(current, store)
                        step |= {"accepted": True, "record": scriptt16.saved(store)[-1]}
                    except OSError:
                        step["accepted"] = False
                elif kind in ("reload", "restore"):
                    line = scriptt16.saved(store)[action[1] - 1 if kind == "restore" else -1]
                    loaded, found = scriptt16.load(line, world_from(action[1], folder)[0] if kind == "reload" and len(action) > 1 else world)
                    step["diagnostics"] = found
                    current = loaded or current
                elif kind == "inspect":
                    entries = [term for _, term in scriptt16.obligations(current)]
                    step["inspected"] = scriptt16.inspect(current, entries[action[1]].number, action[2])
                elif kind in ("rerun", "change_world"):
                    world, source = world_from(action[1], folder) if kind == "change_world" else (world, source)
                    current = scriptt16.rerun(scriptt16.saved(store)[-1], world, model, watch=model.watch)
                elif kind == "restyle":
                    plain_say = scriptt16.say
                    scriptt16.say = lambda term, text="": plain_say(term, text).upper()
                    try:
                        current, _ = scriptt16.load(json.loads(json.dumps(scriptt16.record(current))), world)
                    finally:
                        scriptt16.say = plain_say
                elif kind == "check":
                    _, reply, artifacts, criteria = action
                    entries = [term for _, term in scriptt16.obligations(current)]
                    given = [scriptt16.Artifact(one.operation, {path: term_of(value, current, world, None, path) for path, value in one.bindings.items()}, one.value, one.probe) for one in artifacts]
                    origin = {id(engine): one for engine, one in zip(given, artifacts)}
                    index = index_of(current)
                    phrases = {id(term): phrase for phrase, term in scriptt16.obligations(current)}
                    rules = [(name, lambda term, artifact, test=test: test(project_obligation(current, phrases[id(term)], term, index), origin[id(artifact)])) for name, _, test in criteria]
                    checks, verdict, _ = scriptt16.check(current, reply, given, rules, model)
                    by_number = {term.number: number for number, term in enumerate(entries)}
                    step |= {"checks": [X.Check(by_number[one.obligation], None, one.criterion, one.outcome, one.evidence) for one in checks], "verdict": verdict}
                elif kind == "propose_world":
                    proposer = Standin(action[2])
                    proposed_source = world_from(action[1], folder)[1]
                    decided = scriptt16.gate(proposed_source, folder, corpus, proposer, world, source, watch=proposer.watch)
                    calls -= proposer.calls
                    model.requests += proposer.requests
                    world, source = decided.world, decided.source
                    step["world_change"] = {"activated": decided.activated, "verdict": decided.verdict, "regressions": decided.regressions,
                                            "faults": [(declared, rule) for declared, rule, _ in decided.faults], "draft": decided.draft, "active_world": decided.source}
                shown = preview if kind == "preview" and preview is not None and step.get("accepted") else current
                if current is not None and "obligations" not in step:
                    step |= {key: value for key, value in projected(shown).items() if key not in step}
                if kind == "read" and len(readings) > 1:
                    step["decisions"] = [one for reading in readings for one in project_decisions(reading)]
                if kind in ("check", "propose_world"):
                    step.pop("decisions", None)  # these steps ask about a reply or a world, not about the reading
            except Exception as error:  # an exception is an observation; the run goes on
                step["error"] = type(error).__name__
                step["message"] = str(error)[:300]
            step["requests"] = model.requests[asked:]
            step["model_calls"] = model.calls - calls
            step["writes"] = len(scriptt16.saved(store)) - lines
            observation["steps"][label] = step
        return observation


# ---- Unit tests that the cases do not cover -----------------------------------------


def test_kinds():
    world = world_of(WORLD)
    surface = world.types["Surface"]
    assert agree.kind_of(surface) == agree.Star() and agree.kind_of(agree.MANY) == agree.Arrow(agree.Star(), agree.Star())
    assert agree.kind_of(agree.Applied(agree.MANY, surface)) == agree.Star()
    faulty = world_of('import enum, typing\nAsked = typing.NewType("Asked", str)\nclass Surface(enum.Enum):\n    "x"\n    PAGE: Asked = "the page"\n\ndef one(surface: Many[Maybe]) -> Surface:\n    "x"\n\ndef two(surface: Surface[int]) -> Surface:\n    "x"\n\ndef three(surface: Surface) -> Later:\n    "x"\n\ntype Broken = Many | int\n')
    assert faulty.functions == {}
    assert [(name, rule) for name, rule, _ in faulty.faults] == [("one", "kind"), ("two", "kind"), ("three", "kind"), ("Broken", "kind")], faulty.faults
    assert ["Maybe has kind * -> *" in faulty.faults[0][2], "Surface has kind * and takes no argument" in faulty.faults[1][2], "Later has kind * -> * and needs an argument" in faulty.faults[2][2]] == [True] * 3


def test_types():
    world = world_of(WORLD)
    assert world.faults == [], world.faults
    kinds_of_type = {name: type(one).__name__ for name, one in world.types.items()}
    assert kinds_of_type["Asked"] == "Brand" and kinds_of_type["Surface"] == "Sum" and kinds_of_type["Subject"] == "Sum" and kinds_of_type["Cell"] == "Product" and kinds_of_type["Review"] == "Product"
    asked, written, words, surface, subject = (world.types[name] for name in ("Asked", "Written", "Words", "Surface", "Subject"))
    assert agree.is_subtype(asked, words) and agree.is_subtype(written, words)  # a brand is a subtype of what it wraps
    assert not agree.is_subtype(written, asked) and not agree.is_subtype(words, asked)  # two brands over one type are different types
    assert agree.is_subtype(surface, subject) and not agree.is_subtype(asked, subject)  # a sum takes each of its alternatives
    assert agree.tree(world.functions["redesign"].result) == {"constructor": "Later", "of": {"sum": "Surface", "alternatives": [{"member": "PAGE", "words": "the page"}, {"member": "MOD", "words": "the mod"}]}}
    untyped = world_of('import enum, typing\nAsked = typing.NewType("Asked", str)\nclass Surface(enum.Enum):\n    "x"\n    PAGE = "the page"\n    MOD: Asked = "the mod"\n\ndef show(surface) -> Surface:\n    pass\n')
    assert [(name, rule) for name, rule, _ in untyped.faults] == [("Surface", "missing"), ("show", "missing"), ("show", "missing")], untyped.faults
    assert agree.identity(world) == agree.identity(world_of(WORLD)) != agree.identity(world_of(WORLD + X.PAINT_WORLD.extra))


def test_advice():
    """Same signatures and one-use types are advice for a person, never faults (C12)."""
    world = world_of(WORLD + '\nclass Colour(enum.Enum):\n    "a colour"\n    RED: Asked = "red"\n\ndef paint(surface: Surface) -> Later[Surface]:\n    "paint it"\n\ndef tint(colour: Colour) -> Written:\n    "tint it"\n')
    assert world.faults == []
    assert any("paint: the same parameter types and result type as redesign" in one for one in agree.duplicates(world.types, world.functions, "world.py"))
    assert any("Colour: 1 function uses this type (tint)" in one for one in agree.single_use(world.types, world.functions, "world.py"))
    assert [(name, rule) for name, rule, _ in world_of(WORLD + '\ntype Many = int\n').faults] == [("Many", "name")]


def test_grounding():
    world = world_of(WORLD)
    text = 'Redesign the mod. "The row draws in the code font, and the jiggle is a slant." Is that still true? Then show it.\n\nThanks.'
    reply = "Not verified. The row draws in the code font, and the jiggle is a slant. Nothing else."
    message = scriptt16.phrases(text, [reply], world)
    inner = scriptt16.innermost(message)
    assert [phrase.brand.name for phrase in inner] == ["Asked", "Written", "Asked", "Asked", "Asked"] and inner[1].quotes == 0
    assert text[inner[1].start:inner[1].end].strip() == '"The row draws in the code font, and the jiggle is a slant."'
    assert [phrase.starts_by for phrase in inner[2:]] == ["the phrase before it ends", "after ?", "a blank line"]
    assert scriptt16.fold(lambda phrase: "".join(phrase.inside) or text[phrase.start:phrase.end], message) == text
    joined = scriptt16.innermost(scriptt16.phrases(text, [reply], world, lambda first, second: 0.9 if second.startswith("Then show") else 0.1))
    assert len(joined) == 4 and text[joined[2].start:joined[2].end].strip() == "Is that still true? Then show it."
    with tempfile.TemporaryDirectory() as folder:
        (pathlib.Path(folder) / "notes.md").write_text("x")
        there = world_of(WORLD, pathlib.Path(folder))
        given = "Open cell 3 of notes.md, then the page. Version 1.6 of report.md is missing."
        assert [(given[constant.start:constant.end], agree.show(constant.type)) for constant in scriptt16.grounded(given, there)] == [("3", "int"), ("notes.md", "Path"), ("the page", "Surface")]


def test_synthesis():
    """Rules the cases do not reach: a product inside a product, a sum of two products, and a member typed Asked inside a quote."""
    with tempfile.TemporaryDirectory() as folder:
        (pathlib.Path(folder) / "notes.md").write_text("x")
        there = world_of(WORLD + '\nclass File(typing.NamedTuple):\n    "a file"\n    path: pathlib.Path\n\ntype Target = File | Cell\n\ndef inspect_target(target: Target) -> Observed:\n    "inspect a file or a cell"\n', pathlib.Path(folder))
        text = "Review cell 3 of notes.md."
        model = Standin(X.script({text: "review"}, {(text, "review", "review.cell.notebook"): X.NOTES, (text, "review", "review.cell.number"): X.THREE, (text, "review", "review.evidence"): (X.Lit("Asked", text),)}))
        reading = scriptt16.read(text, there, [], model, join=False, watch=model.watch)
        [(_, term)] = scriptt16.obligations(reading)
        assert scriptt16.say(term) == "review(review=Review(cell=Cell(notebook='notes.md', number='3'), evidence=['Review cell 3 of notes.md.']))", scriptt16.say(term)
        text = "Inspect cell 3 of notes.md."
        model = Standin(X.script({text: "inspect_target"}, {(text, "inspect_target", "target"): X.New("Cell"), (text, "inspect_target", "target.notebook"): X.NOTES, (text, "inspect_target", "target.number"): X.THREE}))
        reading = scriptt16.read(text, there, [], model, join=False, watch=model.watch)
        assert scriptt16.say(scriptt16.obligations(reading)[0][1]) == "inspect_target(target=Cell(notebook='notes.md', number='3'))"
    reply = "The mod is what I look at and change, and nothing else is."
    text = '"The mod is what I look at and change" Explain.'
    model = Standin(X.script({"Explain.": "explain"}))
    reading = scriptt16.read(text, world_of(WORLD.replace("Maybe[Words]", "Maybe[Surface]")), [reply], model, join=False, watch=model.watch)
    assert [one.start for one in reading.constants] == [1] and model.watch[-1]["offered"] == [], model.watch[-1]["offered"]  # the quoted "mod" is not offered


def test_record_shape():
    """The saved record has the documented shape: references as {"ref": n}, several operations in one phrase, a Several of references, decisions with a path."""
    case, run = X.CASE["C16"], X.CASE["C16"].runs[0]
    with tempfile.TemporaryDirectory() as name:
        world, _ = world_from(run.world, pathlib.Path(name))
        model = Standin(run.script)
        reading = scriptt16.read(run.messages[0], world, [], model, join=False, watch=model.watch)
        line = json.loads(json.dumps(scriptt16.record(reading)))
        [phrase] = line["phrases"]
        assert [term["function"] for term in phrase["terms"]] == ["redesign", "show"] and phrase["terms"][1]["arguments"]["subject"] == {"ref": "0"}
        assert {"form", "id", "text", "world", "phrases", "constants", "decisions", "corrections"} == set(line)
        assert all({"state", "asked", "answers", "function", "operation", "path", "offered", "cut"} <= set(one) for one in line["decisions"])
        shared = X.CASE["C17"].runs[1]
        model = Standin(shared.script)
        line = scriptt16.record(scriptt16.read(shared.messages[0], world, [], model, join=False, watch=model.watch))
        assert {"ref": "0"} in line["phrases"][2]["terms"][0]["arguments"]["surfaces"]["several"]
        assert case.id == "C16"


def test_specimen():
    """The specimen end to end through the public API: read, validate, edit, save, reload, validate again; no d1 call after the read."""
    with tempfile.TemporaryDirectory() as name:
        folder = pathlib.Path(name)
        world, _ = world_from(X.World("next"), folder)
        run = X.CASE["C15"].runs[0]
        model = Standin(run.script)
        reading = scriptt16.read(X.SPECIMEN, world, [], model, join=False, watch=model.watch)
        assert scriptt16.diagnostics(reading) == [] and [term.function.name for _, term in scriptt16.obligations(reading)] == ["redesign", "show", "test"]
        redesign, show, _ = [term for _, term in scriptt16.obligations(reading)]
        assert show.arguments["subject"] is redesign
        mod = next(one for one in reading.constants if lit(one) == X.MOD)
        draft, found = scriptt16.edit(reading, show.number, "subject", mod)
        assert found == [] and show.arguments["subject"] is redesign  # the base is untouched
        scriptt16.save(draft, folder / "store.jsonl")
        calls = model.calls
        loaded, found = scriptt16.load(scriptt16.saved(folder / "store.jsonl")[-1], world)
        assert found == [] and scriptt16.diagnostics(loaded) == [] and scriptt16.meaning(loaded) == scriptt16.meaning(draft) and model.calls == calls
        assert [term.function.name for _, term in scriptt16.obligations(loaded)] == ["redesign", "show", "test"]


UNIT_TESTS = [test_kinds, test_types, test_advice, test_grounding, test_synthesis, test_record_shape, test_specimen]


# ---- The requirement inventory, read and checked by the repaired machinery ---------------

INVENTORY_WORLD = '''
import typing
Words = typing.NewType("Words", str)
Asked = typing.NewType("Asked", Words)
Written = typing.NewType("Written", Words)
Observed = typing.NewType("Observed", Words)

def meet(requirement: Asked) -> Observed:
    "meet this requirement of the brief"
'''


def meeting(state: str, asked: dict) -> dict:
    """A stand-in d1 for the inventory: every sentence asks to meet a requirement, with its own words; nothing more."""
    answers = {}
    for key, question in asked.items():
        ids = [one["id"] for one in question.get("options", [])]
        pick = {"what": "meet", "also": scriptt16.NOTHING}.get(key, "0" if "0" in ids else ids[-1] if ids else None)
        answers[key] = Standin.shares(ids, pick) if ids else {"p_true": 0.1}
    return answers


def inventory(results: dict[str, list[str]]) -> list[tuple[str, str, str, int]]:
    """Reads each requirement of expected.REQUIREMENTS as a message and checks its obligations against the run's evidence.

    The evidence of a requirement is a behaviour check: the diagnostics of the predicates
    that test it, expected to be empty. A process requirement has no evidence here.

    Returns:
        (id, kind, verdict, number of obligations) for each requirement.
    """
    world = world_of(INVENTORY_WORLD)
    rows = {row["invariant"]: row["checks"] for row in X.INVARIANT_TABLE}
    found = []
    for one in X.REQUIREMENTS:
        reading = scriptt16.read(one["words"], world, [], meeting, join=False)
        if one["kind"] == "invariant":
            keys = rows[one["id"]]
        elif one["kind"] == "record":
            keys = one["checked_by"].split(", ")
        elif one["kind"] == "process":
            keys = [one["checked_by"]] if one["checked_by"] in results else []
        else:
            keys = [one["id"]]
        observed = [line for key in keys for line in results.get(key, [f"{key}: no result in this run"])]
        artifacts = [scriptt16.Artifact("meet", scriptt16.bindings(term), one["id"], X.Probe("predicates", tuple(keys), [], observed))
                     for _, term in scriptt16.obligations(reading)] if keys else []
        _, verdict, _ = scriptt16.check(reading, "", artifacts, [("evidence", lambda term, artifact: artifact.probe.observed == artifact.probe.expected)], meeting)
        found.append((one["id"], one["kind"], verdict, len(scriptt16.obligations(reading))))
    return found


# ---- The six wrong implementations, as scoped monkeypatches of the engine -------------


@contextlib.contextmanager
def patched(name: str, value):
    """Replaces one function of scriptt16 for the length of a block."""
    original = getattr(scriptt16, name)
    setattr(scriptt16, name, value(original))
    try:
        yield
    finally:
        setattr(scriptt16, name, original)


def every_local(original):
    """W3: a Many takes every local term that fits, without asking d1."""
    def solve(goal, environment, search, state, path, applying, depth):
        if isinstance(goal, agree.Applied) and goal.constructor == agree.MANY:
            return Several(goal.argument, tuple(term for term in environment.local if scriptt16.fills(term, goal.argument)))
        return original(goal, environment, search, state, path, applying, depth)
    return solve


ENGINE_CONTROLS = (
    ("W1", "always accept gate changes", "C02", "gate", lambda original: lambda source, folder, lines, model, active, active_source, limits=scriptt16.Limits(), watch=None:
        scriptt16.Gate(True, X.PASS, [], [], source, agree.loads(source, folder), source), "world change expected"),
    ("W2", "drop an unresolved obligation", "C01", "obligations", lambda original: lambda reading: [one for one in original(reading) if not isinstance(one[1], Unresolved)], "expected 1 obligations"),
    ("W3", "include every local Many item", "C03", "solve", every_local, "binding surfaces"),
    ("W4", "ignore nested pending dependencies", "C10", "pending", lambda original: lambda term: isinstance(term, Application) and scriptt16.later(term.function.result), "status: expected 'pending'"),
    ("W5", "duplicate a shared result", "C15", "term_record", lambda original: lambda term, written: original(term, set()), "expected 3 obligations"),
    ("W6", "certify all repeated operations from one generic reply", "C20", "check", lambda original: lambda *args, **keys: (lambda found: (
        [dataclasses.replace(one, outcome=X.PASS) if (one.claim or 0) >= 0.5 else one for one in found[0]], X.PASS, found[2]))(original(*args, **keys)), "obligation 1 'evidence'"),
)


# Wrong projections of the oracle that are written for another allowed variant, with the reason they cannot apply here.
NOT_APPLICABLE = {"C05g": "it turns the decision of Empty-by-rule into a rejection; with nothing in scope this engine asks d1 and leaves Hole(no candidate) on a rejection, which the case allows"}


def observed_case(case: X.Case) -> dict:
    """Observes every run of a case."""
    return {run.label: observe(run.inputs()) for run in case.runs}


def main() -> int:
    provenance = X.snapshot()
    print(f"working path: {provenance['worktree']}\ncommit: {provenance['commit']}\noracle version: {X.ORACLE_VERSION}")
    for name, sha in provenance["files"].items():
        print(f"  sha256 {sha}  {name}")
    loaded = {"agree": agree.__file__, "scriptt16": scriptt16.__file__, "harness": scriptt16.shipped.__file__, "expected": X.__file__, "test_scriptt16": __file__}
    for name, path in loaded.items():
        print(f"  imported {name:<14} {pathlib.Path(path).resolve()}")
    failures: list[str] = []
    failures += [f"{name} was imported from {path}, outside {X.DECLARED_ROOT}" for name, path in loaded.items() if not pathlib.Path(path).resolve().is_relative_to(X.DECLARED_ROOT)]

    for test in UNIT_TESTS:
        try:
            test()
            print("passed", test.__name__)
        except Exception as error:
            failures.append(f"{test.__name__}: {type(error).__name__}: {error}")
            print("FAILED", test.__name__, error)

    observed, results = {}, {}
    for case in X.CASES:
        observed[case.id] = observed_case(case)
        found = results[case.id] = X.PREDICATES[case.id](observed[case.id])
        failures += found
        print(f"{case.id} {'pass' if not found else 'FAIL'}: {case.words}" + "".join(f"\n    {line}" for line in found))

    for key, words, case_id, wrong, diagnostic in X.NEGATIVE_CONTROLS:
        try:
            wrong_observation = wrong(observed[case_id])
        except (KeyError, IndexError) as error:
            wrong_observation, found = None, [f"the wrong projection does not apply to the observation: {error!r}"]
        if key in NOT_APPLICABLE:
            print(f"  projection {key:<5} not applicable: {words} ({NOT_APPLICABLE[key]})")
            continue
        if wrong_observation == observed[case_id]:
            print(f"  projection {key:<5} not applicable: {words} (it leaves this engine's observation unchanged: an allowed variant)")
            continue
        found = X.PREDICATES[case_id](wrong_observation) if wrong_observation is not None else found
        caught = [line for line in found if diagnostic in line]
        print(f"  projection {key:<5} {'caught' if caught else 'MISSED'}: {words} -> {(caught or found or [''])[0][:140]}")
        failures += [] if caught else [f"projection control {key} ({words}) not caught: {found[:3]}"]

    for key, words, case_id, name, value, diagnostic in ENGINE_CONTROLS:
        with patched(name, value):
            found = X.PREDICATES[case_id](observed_case(X.CASE[case_id]))
        caught = [line for line in found if diagnostic in line]
        results[key] = [] if caught else [f"{key} not caught"]
        print(f"  engine {key} {'caught' if caught else 'MISSED'}: {words} (scriptt16.{name} patched) -> {(caught or found or [''])[0][:160]}")
        failures += [] if caught else [f"engine control {key} ({words}) not caught: {found[:3]}"]

    for key, check in X.LOCATION_PREDICATES.items():
        found = results[key] = X.l4(provenance, X.snapshot()["files"]) if key == "L4" else check(provenance)
        failures += found
        print(f"{key} {'pass' if not found else found}")

    judged = inventory(results)
    print(f"requirement inventory read by the reader and checked against this run's evidence ({len(judged)} items):")
    for verdict in (X.PASS, X.FAIL, X.UNVERIFIED):
        print(f"  {verdict}: {[f'{key} ({obligations})' for key, _, one, obligations in judged if one == verdict]}")
    table = [row | {"observed": "pass: " + ", ".join(row["checks"]) if not any(results.get(key) for key in row["checks"]) else
                    {key: results[key][:2] for key in row["checks"] if results.get(key)}} for row in X.INVARIANT_TABLE]
    for row in table:
        print(f"  {row['invariant']}: {row['observed']}")
    print("INVARIANT_TABLE " + json.dumps(table))

    print(f"{len(X.CASES)} cases, {len(X.NEGATIVE_CONTROLS)} projection controls, {len(ENGINE_CONTROLS)} engine controls, {len(UNIT_TESTS)} unit tests: "
          + ("all passed" if not failures else f"{len(failures)} FAILURES"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
