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
import copy
import dataclasses
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "scriptt")]
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
        case Record(fields=fields):  # a candidate built from its fields, or a record that is a member of a Many
            template = all(isinstance(one, Hole) and not one.reason for one in fields.values())
            return X.New(term.product.name) if template else {name: neutral(one, index) for name, one in fields.items()}
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
        return X.Obligation(span, X.UNRESOLVED, {}, None, term.reason, brand, None, None, place, term.number)
    values = {path: neutral(one, index) for path, one in scriptt16.bindings(term).items()}
    return X.Obligation(span, term.function.name, values, X.PENDING if scriptt16.pending(term) else X.AVAILABLE, None, brand,
                        scriptt16.complete(term), scriptt16.ready(reading, term), place, term.number)


TAGS = {scriptt16.NONE: X.ABSTAIN, scriptt16.NOTHING: X.NO_REQUEST}


def project_choice(decision: dict, index: dict[int, int]):
    """Projects the choice that the engine recorded in a decision."""
    chosen = decision["chosen"]
    if decision["by"] == "model" and chosen is None:
        return X.INVALID
    if isinstance(chosen, list):
        return tuple(neutral(one, index) for one in chosen)
    if isinstance(chosen, str):
        return ({"none": X.REJECT, "absent": X.ABSENT} if decision["function"] else TAGS).get(chosen, chosen)
    return chosen if isinstance(chosen, float) else neutral(chosen, index)


def project_decisions(reading) -> list[X.Decision]:
    """Projects every recorded decision: d1's about an operation, a binding or the grouping of phrases, and the rules'."""
    index, found = index_of(reading), []
    for decision in reading.decisions:
        asked, answers = decision["asked"], decision["answers"] if isinstance(decision["answers"], dict) else {}
        offered = [neutral(one, index) for one in decision["offered"]]
        questions = tuple((question["instructions"], tuple(one["description"] for one in question.get("options", []))) for question in asked.values())
        scores = ()
        for key, question in asked.items():
            if question["type"] == "boolean":
                share = scriptt16.answer(scriptt16.YesNo(question["instructions"]), answers.get(key))
                scores += ((offered[int(key)] if key.isdigit() else X.ABSENT if key == "absent" else key, share),)
            else:
                choice = scriptt16.answer(scriptt16.OneOf(question["instructions"], {one["id"]: one["description"] for one in question["options"]}), answers.get(key))
                named = lambda key: offered[int(key)] if key.isdigit() else ({"none": X.REJECT, "absent": X.ABSENT} if decision["function"] else TAGS).get(key, key)
                scores += tuple((named(one), share) for one, share in choice.shares.items())
                if not decision["function"]:
                    offered = [TAGS.get(one["id"], one["id"]) for one in question["options"]]
        found.append(X.Decision(index.get(id(by_number(reading, decision["operation"]))), decision["path"], decision["by"], tuple(offered), project_choice(decision, index),
                                tuple(neutral(one, index) for one in decision["cut"]), decision["state"], questions, scores, decision["rule"]))
    return found


def by_number(reading, number):
    """Returns the operation of a reading with this number, or None."""
    return next((term for _, term in scriptt16.obligations(reading) if term.number == number), None) if number is not None else None


def project_correction(reading, correction: dict) -> X.Correction:
    """Projects a correction; its value is the saved term record."""
    index = index_of(reading)
    value = correction["value"]
    if "ref" in value:
        shown = X.Ref(index.get(id(by_number(reading, int(value["ref"])))))
    elif "constant" in value:
        shown = X.Lit(value["type"], value["constant"])
    else:
        shown = X.Hole(value.get("hole"), value.get("reason"))
    return X.Correction(index.get(id(by_number(reading, correction["operation"]))), correction["path"], shown, correction["status"], correction["reason"])


def projected(reading) -> dict:
    """Returns the reading's keys of a step: obligations, passages, decisions, diagnostics and corrections."""
    index = index_of(reading)
    entries = scriptt16.obligations(reading)
    return {"obligations": [project_obligation(reading, phrase, term, index) for phrase, term in entries],
            "passages": [X.Passage(*at(reading, phrase)[:1], phrase.brand.name, "user" if phrase.quotes is None else f"reply {phrase.quotes}", relation, at(reading, phrase)[1])
                         for phrase, relation in scriptt16.passages(reading)],
            "decisions": project_decisions(reading),
            "diagnostics": [(index.get(id(by_number(reading, number))), path, rule) for number, path, rule in scriptt16.diagnostics(reading)],
            "corrections": [project_correction(reading, one) for one in reading.corrections]}


# ---- The stand-in d1 -------------------------------------------------------------


class Standin:
    """d1 answering by meaning from a case's script, choosing only by what d1 receives.

    From a question it learns which phrase, operation and path it is about (the
    phrase is the state; the operation is the docstring in the wording; the
    path is the role). It chooses an option only by its description, with
    ``expected.option_for``. A scripted value that no description says gets an
    out-of-set answer; ABSTAIN, NO_REQUEST, REJECT and ABSENT pick the options
    the engine declares for them.

    Args:
        script: The answers of the run.
        world: The oracle's world spec in which the script's function names exist.
    """

    def __init__(self, script: dict, world: X.World, current: agree.World | None = None):
        self.script, self.world, self.calls, self.requests, self.asked, self.responses = script, world, 0, [], {}, []
        self.current = current  # the engine's world now: a question's operation is named by its docstring there

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
        phrase, answers = self.phrase(state), {}
        functions = {" ".join(f.asks.split()): name for name, f in self.current.functions.items()} if self.current else {text: name for name, text in X.docstrings(self.world).items()}
        for key, question in asked.items():
            instructions = " ".join(question["instructions"].split())
            descriptions = tuple(one["description"] for one in question.get("options", []))
            ids = [one["id"] for one in question.get("options", [])]
            declared = {X.ABSTAIN: scriptt16.ELSE[scriptt16.NONE], X.NO_REQUEST: scriptt16.ELSE[scriptt16.NOTHING], X.REJECT: scriptt16.NONE_OF_THESE, X.ABSENT: scriptt16.ABSENT}
            pick = lambda want: ids[descriptions.index(declared[want])] if want in declared and declared[want] in descriptions else (
                ids[found] if (found := X.option_for(want, descriptions, self.script.get("refers"), self.world)) is not None else None)
            also = instructions.startswith("The text asks the reader to ") and instructions.endswith(". Does it also ask the reader to do something else?")
            if instructions == scriptt16.shipped.WHAT or also:
                if not also and state in self.asked:   # the first question about a phrase again: another reading of the message
                    self.asked = {}
                since = self.asked[state] = self.asked.get(state, -1) + 1
                ops = self.script["ops"].get(phrase, X.NO_REQUEST)
                named = [{X.ABSTAIN: scriptt16.ELSE[scriptt16.NONE]}.get(one) or X.docstrings(self.world).get(one, "") for one in (ops if isinstance(ops, tuple) else (ops,))[:since]]
                if also and instructions.removeprefix("The text asks the reader to ").removesuffix(". Does it also ask the reader to do something else?") != "; ".join(named):
                    answers[key] = {"probabilities": {"not offered": 1.0}}  # the question does not say what was already chosen
                    continue
                want = (ops[since] if since < len(ops) else X.NO_REQUEST) if isinstance(ops, tuple) else (ops if since == 0 else X.NO_REQUEST)
            else:
                about = instructions.removeprefix("The text asks the reader to ").removeprefix("The message asks the reader to ")
                function = next((name for text, name in functions.items() if about.startswith(text + ".")), None)
                left_out = instructions.partition(". Does the text leave out the ")[2].removesuffix(" on purpose?")
                role = instructions.partition(". Which ")[2].removesuffix(" does the text name for that?") or left_out or instructions.rpartition('" the ')[2].removesuffix(" for that?")
                path = next((path for (_, name, path) in self.script["binds"] if name == function and path.rsplit(".", 1)[-1].replace("_", " ") == role), role)
                if function is None:  # a question about a reply, or about two sentences
                    answers[key] = {"p_true": self.script.get("judge", 0.1)}
                    continue
                want = self.script["binds"].get((phrase, function, path), X.REJECT)
                if question["type"] == "boolean" and left_out:  # the absence question of a Many
                    answers[key] = {"p_true": 0.9 if want == X.ABSENT else 0.1}
                    continue
                if question["type"] == "boolean":
                    members = want if isinstance(want, tuple) else ()
                    answers[key] = {"p_true": 0.9 if any(X.option_for(one, (instructions,), self.script.get("refers"), self.world, whole=False) == 0 for one in members) else 0.1}
                    continue
            if isinstance(want, X.Malformed):
                answers |= self.malformed(key, want, ids)
                continue
            chosen = pick(want)
            answers[key] = self.shares(ids, chosen) if chosen is not None else {"probabilities": {"not offered": 1.0}}
        self.responses.append(json.dumps([state, asked, answers], sort_keys=True))
        given = lambda key: answers.get(key, {}).get("probabilities", answers.get(key, {}).get("p_true")) if isinstance(answers.get(key), dict) else None
        self.requests += [X.Request(state, question["instructions"], tuple(one["description"] for one in question.get("options", [])), given(key)) for key, question in asked.items()]
        return answers

    @staticmethod
    def malformed(key: str, want: X.Malformed, ids: list[str]) -> dict:
        """Returns a malformed answer: an id not offered, no entry, or a share that is no number."""
        if not ids:  # a yes/no question
            return {"missing": {}, "not_numbers": {key: {"p_true": "high"}}, "nan": {key: {"p_true": float("nan")}}, "infinite": {key: {"p_true": float("inf")}},
                    "negative": {key: {"p_true": -0.5}}, "out_of_range": {key: {"p_true": 1.5}}}.get(want.kind, {key: {"p_true": 1.5}})
        rest = {one: 0.0 for one in ids[1:]}
        return {"out_of_set": {key: {"probabilities": {"frobnicate": 1.0}}}, "missing": {}, "not_numbers": {key: {"probabilities": {ids[0]: "high"}}},
                "nan": {key: {"probabilities": {ids[0]: float("nan")} | rest}}, "infinite": {key: {"probabilities": {ids[0]: float("inf")} | rest}},
                "negative": {key: {"probabilities": {ids[0]: 1.5, ids[-1]: -0.5}}}, "out_of_range": {key: {"probabilities": {ids[0]: 1.5} | rest}},
                "unnormalized": {key: {"probabilities": {ids[0]: 0.5} | rest}}}[want.kind]

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


def faithful(reading) -> list[str]:
    """Returns each d1 decision of a reading as the stand-in would have captured it: the state, the questions and the answers."""
    return [json.dumps([one["state"], one["asked"], one["answers"]], sort_keys=True) for one in reading.decisions if one["by"] == "model"]


def fidelity(observed: dict) -> list[str]:
    """Every saved d1 decision must be a request and response that the stand-in actually captured, scores included."""
    return [f"{label}/{step_label}: a saved decision's answers differ from what d1 returned: {one[:160]}"
            for label, observation in observed.items() for step_label, step in observation["steps"].items() for one in step.get("unfaithful", [])]


def rendered(reading) -> str:
    """Returns the reading as the display shows it: each obligation by say()."""
    return "; ".join(scriptt16.say(term) if isinstance(term, Application) else f"? ({term.reason})" for _, term in scriptt16.obligations(reading))


def named(name: str, world: agree.World):
    """Returns a type by its name in a world, or the Python base type of that name when the world does not use it."""
    return world.types.get(name) or agree.Base(name, {"int": int, "str": str}[name])


def term_of(value, reading, world: agree.World, place, path: str = ""):
    """Converts a neutral value of an edit, a law or an artifact to an engine term of this reading. ``place`` is the type of its place, or None."""
    entries = [term for _, term in scriptt16.obligations(reading)] if reading else []
    match value:
        case X.Lit(type=name, value=words):
            kind = named(name, world) if name in ("int", "str") else scriptt16.type_named(name, world)
            same = [one for one in (reading.constants if reading else []) if lit(one) == value]
            if same:
                return same[0]
            if isinstance(kind, agree.Sum):
                return next((one for one in scriptt16.members(kind) if one.value.words == words), Constant(kind, words, -1, -1))  # a non-member stays a non-member
            return Constant(kind, pathlib.Path(words) if name == "Path" else words, -1, -1)
        case X.Passage(brand=brand, at=(start, end)):
            return Constant(world.types[brand], reading.text[start:end], start, end)
        case dict():  # a record that is a member of a Many
            product = place.argument if place else None
            return Record(product, {field: term_of(one, reading, world, dict(product.fields).get(field)) for field, one in value.items()})
        case X.Nothing(type=name):
            return Empty(named(name, world))
        case X.Members(type=name, values=values):
            return Several(named(name, world), tuple(term_of(one, reading, world, None) for one in values))
        case X.Ref(obligation=number):
            return entries[number] if number < len(entries) else Application(next(iter(world.functions.values())), {}, None)
        case X.Hole(type=name, reason=reason):
            return Hole(world.types[name], reason)
        case "EMPTY_LIST":
            return Several(place.argument, ())
        case "EMPTY":
            return Empty(place)
        case tuple():
            terms = tuple(term_of(one, reading, world, place) if isinstance(one, dict) else term_of(one, reading, world, None) for one in value)
            return Several(place.argument if place else scriptt16.type_of(terms[0]), terms)
    raise ValueError(f"no engine term for {value!r}")


def edited(reading, world, change: X.Edit, correction: bool = False):
    """Applies one neutral edit through the engine. Returns the draft and its neutral diagnostics."""
    entries = [term for _, term in scriptt16.obligations(reading)]
    if change.obligation is None:  # a function applied to a value: the place is the function's parameter
        name, _, parameter = change.path.partition(".")
        target, place = None, dict(world.functions[name].parameters).get(parameter) if name in world.functions else None
    else:
        target = entries[change.obligation]
        try:
            place = scriptt16.place_type(target, change.path)
        except (KeyError, AttributeError):
            place = None  # no such place: the engine's diagnostic says so
    value = None if change.op == "remove" else Hole(place, "cleared") if change.op == "clear" else term_of(change.value, reading, world, place, change.path)
    draft, found = scriptt16.edit(reading, getattr(target, "number", None), change.path, value, correction, world)
    index = index_of(draft)
    return draft, [(index.get(id(by_number(draft, number))), path, rule) for number, path, rule in found]


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
        model, store = Standin(inputs.script, inputs.world, world), folder / "store.jsonl"
        current, preview, corpus, readings = None, None, [], []
        for label, action in inputs.actions:
            calls, lines, asked, step = model.calls, len(scriptt16.saved(store)), len(model.requests), {}
            try:
                kind = action[0]
                if kind == "read":
                    readings = [scriptt16.read(text, world, list(inputs.replies), model, join=False) for text in inputs.messages]
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
                            current, found = scriptt16.save(current, store)
                        step |= {"accepted": not found, "diagnostics": found} | ({"record": scriptt16.saved(store)[-1], "world_export": agree.world_record(world)} if not found else {})
                    except OSError:
                        step["accepted"] = False
                elif kind in ("reload", "restore"):
                    if kind == "restore":
                        loaded, found = scriptt16.restore(store, action[1], world)
                    else:
                        loaded, found = scriptt16.load(scriptt16.saved(store)[-1], world_from(action[1], folder)[0] if len(action) > 1 else world)
                    step["diagnostics"] = found
                    current = loaded or current
                    step["rendered"] = rendered(current)
                elif kind == "load":
                    current, _ = scriptt16.save(current, store)
                    loaded, found = scriptt16.load(X.mutated(scriptt16.saved(store)[-1], action[1]), world)
                    step["diagnostics"] = [(index_of(loaded).get(id(by_number(loaded, number))) if loaded else None, path, rule) for number, path, rule in found]
                    step |= {key: value for key, value in projected(loaded).items() if key != "diagnostics"} if loaded else {}
                    current = loaded or current
                elif kind == "draft_from":
                    opened, _ = scriptt16.load(scriptt16.saved(store)[action[1] - 1], world)
                    draft, found = edited(opened, world, action[2])
                    step |= {"accepted": not found, "diagnostics": found}
                    current = draft if not found else current
                elif kind == "validate":
                    _, name, given = action
                    function = world.functions[name]
                    places = dict(function.parameters)
                    arguments = {}
                    for path, value in given.items():  # a dotted path is a field of a record argument
                        first, _, field = path.partition(".")
                        if field and isinstance(places.get(first), agree.Product):
                            record = arguments.setdefault(first, Record(places[first], {}))
                            record.fields[field] = term_of(value, None, world, dict(places[first].fields).get(field))
                        else:
                            arguments[path] = term_of(value, None, world, places.get(path))
                    application = Application(function, arguments, 0)
                    built = scriptt16.Reading("law", "", scriptt16.Phrase(0, 0, world.types["Asked"], terms=(application,)), [], [], agree.identity(world))
                    found = scriptt16.diagnostics(built)
                    shown = built
                    if not found:
                        fresh = folder / f"law-{label}.jsonl"
                        scriptt16.save(built, fresh)
                        shown, found = scriptt16.load(scriptt16.saved(fresh)[-1], world)
                        step["writes_law"] = 1
                    step |= {"diagnostics": [(0, path, rule) for _, path, rule in found], "obligations": projected(shown)["obligations"]}
                elif kind == "inspect":
                    entries = [term for _, term in scriptt16.obligations(current)]
                    step["inspected"] = scriptt16.inspect(current, entries[action[1]].number, action[2])
                elif kind in ("rerun", "change_world"):
                    world, source = world_from(action[1], folder) if kind == "change_world" else (world, source)
                    model.current = world
                    if kind == "rerun" and len(action) > 1:
                        model.script = action[1]
                    current = scriptt16.rerun(scriptt16.saved(store)[-1], world, model)
                elif kind == "restyle":
                    # The display of a reading calls say() (the notebook's tables, d1's option texts). The restyle patches
                    # it to another format, saves and reloads under the patch, and reports what the display then shows;
                    # record() and load() do not call say(), so the meaning cannot change with it.
                    plain_say = scriptt16.say
                    scriptt16.say = lambda term: plain_say(term).replace("(", " ← ").replace("=", ": ").rstrip(")")
                    try:
                        current, _ = scriptt16.load(json.loads(json.dumps(scriptt16.record(current))), world)
                        step["rendered"] = rendered(current)
                    finally:
                        scriptt16.say = plain_say
                elif kind == "check":
                    _, reply, artifacts, criteria = action
                    entries = [term for _, term in scriptt16.obligations(current)]
                    instance = lambda one: entries[one.instance].number if one.instance is not None and one.instance < len(entries) else None
                    given = [scriptt16.Artifact(one.operation, {path: term_of(value, current, world, None, path) for path, value in one.bindings.items()}, instance(one)) for one in artifacts]
                    origin = {id(engine): one for engine, one in zip(given, artifacts)}
                    index = index_of(current)
                    phrases = {id(term): phrase for phrase, term in scriptt16.obligations(current)}
                    rules = [(name, lambda term, artifact, test=test: test(index[id(term)], project_obligation(current, phrases[id(term)], term, index), origin[id(artifact)])) for name, _, test in criteria]
                    current, verdict, _ = scriptt16.check(current, reply, given, rules, model)
                    numbers = {term.number: number for number, term in enumerate(entries)}
                    step |= {"checks": [X.Check(numbers[one.obligation], None, one.criterion, one.outcome, one.evidence) for one in current.fulfillment], "verdict": verdict}
                elif kind == "propose_world":
                    proposed, proposed_source = world_from(action[1], folder)
                    proposer = Standin(action[2], action[1], proposed)
                    decided = scriptt16.gate(proposed_source, folder, corpus, proposer, world, source, migrations=tuple(action[3]) if len(action) > 3 else ())
                    calls -= proposer.calls
                    model.requests += proposer.requests
                    world, source, corpus = decided.world, decided.source, decided.lines
                    model.current = world
                    step["world_change"] = {"activated": decided.activated, "verdict": decided.verdict, "regressions": decided.regressions, "migrated": decided.migrated,
                                            "faults": [(declared, rule) for declared, rule, _ in decided.faults], "draft": proposed_source, "active_world": decided.source}
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
            if current is not None and "decisions" in step:
                step["unfaithful"] = [one for one in faithful(current) if one not in model.responses]
            step["requests"] = model.requests[asked:]
            step["model_calls"] = model.calls - calls
            step["writes"] = len(scriptt16.saved(store)) - lines + step.pop("writes_law", 0)
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
    assert agree.tree(world.functions["redesign"].result) == {"constructor": "Later", "of": {"sum": "Surface", "alternatives": [{"member": "PAGE", "words": "the page", "type": {"brand": "Asked", "of": {"brand": "Words", "of": {"base": "str"}}}}, {"member": "MOD", "words": "the mod", "type": {"brand": "Asked", "of": {"brand": "Words", "of": {"base": "str"}}}}]}}
    untyped = world_of('import enum, typing\nAsked = typing.NewType("Asked", str)\nclass Surface(enum.Enum):\n    "x"\n    PAGE = "the page"\n    MOD: Asked = "the mod"\n\ndef show(surface) -> Surface:\n    pass\n')
    assert [(name, rule) for name, rule, _ in untyped.faults] == [("Surface", "missing"), ("show", "missing"), ("show", "missing")], untyped.faults
    assert agree.identity(world) == agree.identity(world_of(WORLD)) != agree.identity(world_of(WORLD + X.PAINT_WORLD.extra))
    assert agree.identity(world) != agree.identity(world_of(WORLD.replace('PAGE: Asked = "the page"', 'PAGE: Written = "the page"')))  # provenance of a member is part of the world


def test_faults():
    """Each kind of error in world.py maps to its rule; same signatures and one-use types are no faults (C12); the option bound is a fault."""
    faults = lambda source: [(name, rule) for name, rule, _ in world_of(source).faults]
    assert faults(WORLD + '\ndef paint(surface: Surface) -> Later[Surface]:\n    "paint it"\n') == []
    assert faults(WORLD + '\ntype Many = int\n') == [("Many", "name")]
    assert faults(WORLD + '\ndef lost(thing: Thing) -> Surface:\n    "x"\n') == [("lost", "name")]
    assert faults(WORLD + '\n@dataclasses.dataclass\nclass Loop:\n    "x"\n    next: Loop\n') == [("Loop", "type")]
    assert faults(WORLD + '\ndef odd(surface: Surface + 1) -> Surface:\n    "x"\n') == [("odd", "type")]
    many = lambda count: "".join(f'\ndef f{number}(surface: Surface) -> Written:\n    "x"\n' for number in range(count))
    assert faults(WORLD + many(22)) == [] and faults(WORLD + many(23)) == [("world.py", "name")]  # 8 + 22 functions and d1's 2 other answers fill 32 options


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


TARGETS = '\nclass File(typing.NamedTuple):\n    "a file"\n    path: pathlib.Path\n\ntype Target = File | Cell\n\ndef inspect_target(target: Target) -> Observed:\n    "inspect a file or a cell"\n'


def test_synthesis():
    """Rules the cases do not reach: a product inside a product, a sum of two products, and a member typed Asked inside a quote."""
    with tempfile.TemporaryDirectory() as folder:
        (pathlib.Path(folder) / "notes.md").write_text("x")
        there = world_of(WORLD + TARGETS, pathlib.Path(folder))
        text = "Review cell 3 of notes.md."
        model = Standin(world=X.World(files=("notes.md",)), script=X.script({text: "review"}, {(text, "review", "review.cell.notebook"): X.NOTES, (text, "review", "review.cell.number"): X.THREE, (text, "review", "review.evidence"): (X.Lit("Asked", text),)}))
        reading = scriptt16.read(text, there, [], model, join=False)
        [(_, term)] = scriptt16.obligations(reading)
        assert scriptt16.say(term) == "review(review=Review(cell=Cell(notebook='notes.md', number='3'), evidence=['Review cell 3 of notes.md.']))", scriptt16.say(term)
        text = "Inspect cell 3 of notes.md."
        model = Standin(world=X.World(extra=TARGETS, files=("notes.md",)), script=X.script({text: "inspect_target"}, {(text, "inspect_target", "target"): X.New("Cell"), (text, "inspect_target", "target.notebook"): X.NOTES, (text, "inspect_target", "target.number"): X.THREE}))
        reading = scriptt16.read(text, there, [], model, join=False)
        assert scriptt16.say(scriptt16.obligations(reading)[0][1]) == "inspect_target(target=Cell(notebook='notes.md', number='3'))"
    reply = "The mod is what I look at and change, and nothing else is."
    text = '"The mod is what I look at and change" Explain.'
    surfaces = world_of(WORLD.replace("Maybe[Words]", "Maybe[Surface]"))
    model = Standin(X.script({"Explain.": "explain"}), X.MAYBE_SURFACE)
    reading = scriptt16.read(text, surfaces, [reply], model, join=False)
    assert [one.start for one in reading.constants] == [1] and reading.decisions[-1]["offered"] == [], reading.decisions[-1]["offered"]  # the quoted "mod" is not offered


def test_record_shape():
    """The saved record has the documented shape: references as {"ref": n}, several operations in one phrase, a Several of references, decisions with a path."""
    case, run = X.CASE["C16"], X.CASE["C16"].runs[0]
    with tempfile.TemporaryDirectory() as name:
        world, _ = world_from(run.world, pathlib.Path(name))
        model = Standin(run.script, run.world)
        reading = scriptt16.read(run.messages[0], world, [], model, join=False)
        line = json.loads(json.dumps(scriptt16.record(reading)))
        [phrase] = line["phrases"]
        assert [term["function"] for term in phrase["terms"]] == ["redesign", "show"] and phrase["terms"][1]["arguments"]["subject"] == {"ref": "0"}
        assert phrase["terms"][1]["parameters"] == {"subject": "Subject"} and phrase["terms"][0]["arguments"]["surface"]["type"] == "Surface"  # declared place apart from the value's type
        assert phrase["terms"][1]["judgments"] == {"valid": True, "diagnostics": [], "complete": True, "pending": True, "deferred": False, "ready": False}
        exported = json.loads(json.dumps(agree.world_record(world)))
        assert exported["identity"] == line["world"] and exported["types"]["Surface"]["kind"] == "*" and exported["constructors"]["Many"]["kind"] == "* -> *"
        assert exported["types"]["Surface"]["alternatives"][0]["type"]["brand"] == "Asked" and exported["functions"]["show"]["parameters"] == [["subject", agree.tree(world.types["Subject"])]]
        assert {"form", "id", "text", "source", "world", "base", "phrases", "constants", "decisions", "corrections"} == set(line)  # no fulfillment: no check ran
        assert all({"by", "rule", "state", "asked", "answers", "function", "operation", "path", "offered", "cut", "chosen"} <= set(one) for one in line["decisions"])
        shared = X.CASE["C17"].runs[1]
        model = Standin(shared.script, shared.world)
        line = scriptt16.record(scriptt16.read(shared.messages[0], world, [], model, join=False))
        assert {"ref": "0"} in line["phrases"][2]["terms"][0]["arguments"]["surfaces"]["several"]
        either = world_of(WORLD + '\ndef pick(thing: Surface | pathlib.Path) -> Written:\n    "pick one"\n', pathlib.Path(name))
        holed = scriptt16.read("Pick one.", either, [], Standin(X.script({"Pick one.": "pick"}), X.World(extra='\ndef pick(thing: Surface | pathlib.Path) -> Written:\n    "pick one"\n')), join=False)
        again, found = scriptt16.load(json.loads(json.dumps(scriptt16.record(holed))), either)
        assert found == [] and agree.show(again.message.terms[0].arguments["thing"].type) == "Surface | Path"  # an unnamed union reloads by its name
        assert case.id == "C16"


def test_specimen():
    """The specimen end to end through the public API: read, validate, edit, save, reload, validate again; no d1 call after the read."""
    with tempfile.TemporaryDirectory() as name:
        folder = pathlib.Path(name)
        world, _ = world_from(X.World("next"), folder)
        run = X.CASE["C15"].runs[0]
        model = Standin(run.script, run.world)
        reading = scriptt16.read(X.SPECIMEN, world, [], model, join=False)
        assert scriptt16.diagnostics(reading) == [] and [term.function.name for _, term in scriptt16.obligations(reading)] == ["redesign", "show", "test"]
        redesign, show, _ = [term for _, term in scriptt16.obligations(reading)]
        assert show.arguments["subject"] is redesign
        mod = next(one for one in reading.constants if lit(one) == X.MOD)
        draft, found = scriptt16.edit(reading, show.number, "subject", mod)
        assert found == [] and show.arguments["subject"] is redesign  # the base is untouched
        draft, _ = scriptt16.save(draft, folder / "store.jsonl")
        calls = model.calls
        loaded, found = scriptt16.load(scriptt16.saved(folder / "store.jsonl")[-1], world)
        assert found == [] and scriptt16.diagnostics(loaded) == [] and scriptt16.meaning(loaded) == scriptt16.meaning(draft) and model.calls == calls
        assert [term.function.name for _, term in scriptt16.obligations(loaded)] == ["redesign", "show", "test"]
        seen = scriptt16.inspect(reading, show.number, "subject")
        assert seen["term"] is redesign and seen["type"] == "Subject" and seen["definition"] == show.function.asks and seen["decision"]["chosen"] is redesign
        # Readiness: redesign can start and its result comes later; show waits on it.
        assert (scriptt16.ready(reading, redesign), scriptt16.deferred(redesign), scriptt16.ready(reading, show), scriptt16.deferred(show)) == (True, True, False, False)
        # Acceptance survives a rerun in which d1 prefers the original binding, and is invalidated with a reason when it cannot hold.
        accepted, faults = scriptt16.edit(reading, show.number, "subject", mod, correction=True)
        line = json.loads(json.dumps(scriptt16.record(accepted)))
        again = scriptt16.rerun(line, world, Standin(run.script, run.world, world))
        assert faults == [] and scriptt16.say(scriptt16.obligations(again)[1][1]) == "show(subject='the mod')" and again.corrections[0]["status"] == "retained"
        without = world_of((HERE / "world.py").read_text().replace('    MOD: Asked = "the mod"\n', ""), folder)
        gone = scriptt16.rerun(line, without, Standin(run.script, run.world, without))
        assert gone.corrections[0]["status"] == "invalidated" and "subject" in gone.corrections[0]["reason"] and scriptt16.say(scriptt16.obligations(gone)[1][1]) != "show(subject='the mod')"
        # A function applied to a value through edit: a new operation with a new number in the value's phrase; no other number changes.
        tested, faults = scriptt16.edit(reading, None, "test.subject", mod, correction=True, world=world)
        numbers = [term.number for _, term in scriptt16.obligations(tested)]
        assert faults == [] and numbers == [0, 3, 1, 2] and scriptt16.say(scriptt16.obligations(tested)[1][1]) == "test(subject='the mod')", (faults, numbers)
        assert [term.number for _, term in scriptt16.obligations(reading)] == [0, 1, 2]  # the base is untouched
        assert scriptt16.edit(reading, None, "test.nothing", mod, world=world)[1] == [(None, "nothing", "extra")]
        assert scriptt16.edit(reading, None, "redesign.surface", next(one for one in reading.constants if lit(one) == X.SEARCH), world=world)[1] == [(None, "surface", "type")]
        kept = scriptt16.rerun(json.loads(json.dumps(scriptt16.record(tested))), world, Standin(run.script, run.world, world))
        assert [scriptt16.say(term) for _, term in scriptt16.obligations(kept)][1] == "test(subject='the mod')" and kept.corrections[0]["status"] == "retained"
        dropped = scriptt16.rerun(json.loads(json.dumps(scriptt16.record(tested))), without, Standin(run.script, run.world, without))
        assert dropped.corrections[0]["status"] == "invalidated" and "test" in dropped.corrections[0]["reason"] and len(scriptt16.obligations(dropped)) == 3
        test_world = world_of(WORLD, folder)
        small = scriptt16.read("Redesign the mod.", test_world, [], Standin(X.told(X.REDESIGN_SHOW[:1]), X.World(), test_world), join=False)
        compared, faults = scriptt16.edit(small, None, "compare.surfaces", small.constants[0], world=test_world)
        assert faults == [] and scriptt16.say(scriptt16.obligations(compared)[1][1]) == "compare(surfaces=['the mod'])"  # one value for a Many becomes a collection of it
        checked, verdict, judgment = scriptt16.check(loaded, "I did all three.", [], [("evidence", lambda term, artifact: True)], Standin(X.script({}, judge=0.99), X.World("next")))
        checks = checked.fulfillment
        assert verdict == X.UNVERIFIED and {one.claim for one in checks} == {0.99} and "I did all three." in judgment["state"]  # a confident claim is kept, and is no evidence


def test_rules():
    """Rules that the cases allow either way, pinned to the engine's declared choice, each with the reading that shows it."""
    with tempfile.TemporaryDirectory() as name:
        folder = pathlib.Path(name)
        test = world_of(WORLD, folder)
        read = lambda text, script, world=test: scriptt16.read(text, world, [], Standin(script, X.World(), world), join=False)
        # A hole with nothing in scope says "no candidate"; a bound that cut candidates says "bounded".
        unknown = read("Compare them.", X.script({"Compare them.": "compare"}))
        assert scriptt16.obligations(unknown)[0][1].arguments["surfaces"].reason == "no candidate"
        bounded = scriptt16.read(X.BOUNDED_TEXT, world_from(X.World("next"), folder)[0], [], Standin(X.script({X.BOUNDED_TEXT: "show"}), X.World("next")), join=False)
        assert scriptt16.obligations(bounded)[0][1].arguments["subject"].reason == "bounded"
        # A single candidate of a Many is still d1's to choose.
        no_producer = world_of(WORLD.replace("def redesign(surface: Surface) -> Later[Surface]:", "def redesign(surface: Surface) -> Later[Written]:"), folder)
        one = read("Compare the mod.", X.script({"Compare the mod.": "compare"}), no_producer)
        assert [len(one_decision["offered"]) for one_decision in one.decisions if one_decision["path"] == "surfaces"] == [1]
        # A quote of a reply is words in scope: a Maybe[Words] place is offered it.
        quoted = scriptt16.read('"These seven words are the entire earlier reply." What do you mean?', test, [X.QUOTE], Standin(X.script({"What do you mean?": "explain"}), X.World(), test), join=False)
        assert any(isinstance(term, Constant) and term.type.name == "Written" for one in quoted.decisions for term in one["offered"])
        # A hole whose type has the wrong kind is a kind fault.
        redesign = scriptt16.obligations(unknown)[0][1]
        assert scriptt16.edit(unknown, redesign.number, "surfaces", Hole(agree.MANY, "cleared"))[1] == [(redesign.number, "surfaces", "kind")]
        # Members of a Many are compared as a set.
        members = scriptt16.members(test.types["Surface"])
        assert scriptt16.value_of(Several(test.types["Surface"], tuple(members)), {}) == scriptt16.value_of(Several(test.types["Surface"], tuple(reversed(members))), {})
        # A new operation gets the largest number plus one, also after an edit removed one.
        nested = read("Show me the mod, redesigned.", X.script({"Show me the mod, redesigned.": "show"}, {("Show me the mod, redesigned.", "show", "subject"): X.New("redesign"), ("Show me the mod, redesigned.", "redesign", "surface"): X.MOD}))
        _, show = [term for _, term in scriptt16.obligations(nested)]
        flat, _ = scriptt16.edit(nested, show.number, "subject", nested.constants[0])
        applied, faults = scriptt16.edit(flat, None, "redesign.surface", flat.constants[0], world=test)
        assert faults == [] and sorted(term.number for _, term in scriptt16.obligations(applied)) == [1, 2], [term.number for _, term in scriptt16.obligations(applied)]
        # A corrected value that the changed world's place no longer accepts is invalidated.
        base = read("Redesign the mod. Then show it.", X.told(X.REDESIGN_SHOW))
        redesign_op, show_op = [term for _, term in scriptt16.obligations(base)]
        corrected, _ = scriptt16.edit(base, show_op.number, "subject", base.constants[0], correction=True)
        narrower = world_of(WORLD.replace("def show(subject: Subject) -> Subject:", "def show(subject: pathlib.Path) -> Subject:"), folder)
        again = scriptt16.rerun(json.loads(json.dumps(scriptt16.record(corrected))), narrower, Standin(X.told(X.REDESIGN_SHOW), X.World(), narrower))
        assert again.corrections[0]["status"] == "invalidated" and "subject" in again.corrections[0]["reason"], again.corrections


def test_review_0249f2b():
    """The six counterexamples of the review of 0249f2b, each beside its positive control."""
    with tempfile.TemporaryDirectory() as name:
        folder = pathlib.Path(name)
        test = world_of(WORLD, folder)
        read = lambda text, script, world=test, spec=X.World(): scriptt16.read(text, world, [], Standin(script, spec, world), join=False)
        reading = read("Redesign the mod.", X.told(X.REDESIGN_SHOW[:1]))
        mod = reading.constants[0]
        [(_, redesign)] = scriptt16.obligations(reading)
        # 1. A new operation comes only from the reading's own world.
        other = world_of(WORLD + '\ndef audit_extra(surface: Surface) -> Written:\n    "audit it"\n', folder)
        assert scriptt16.edit(reading, None, "audit_extra.surface", mod, world=other)[1] == [(None, "surface", "identity")]
        assert scriptt16.edit(reading, None, "show.subject", mod, world=test)[1] == []
        # 2. An inserted operation's reference must still mean what it meant on rerun.
        inserted, faults = scriptt16.edit(reading, None, "show.subject", redesign, correction=True, world=test)
        line = json.loads(json.dumps(scriptt16.record(inserted)))
        kept = scriptt16.rerun(line, test, Standin(X.told(X.REDESIGN_SHOW[:1]), X.World(), test))
        assert faults == [] and kept.corrections[0]["status"] == "retained" and [scriptt16.say(term) for _, term in scriptt16.obligations(kept)] == ["redesign(surface='the mod')", "show(subject=redesign(surface='the mod'))"]
        moved = scriptt16.rerun(line, test, Standin(X.script({"Redesign the mod.": "show"}, {("Redesign the mod.", "show", "subject"): X.MOD}), X.World(), test))
        assert moved.corrections[0]["status"] == "invalidated" and "redesign" in moved.corrections[0]["reason"] and len(scriptt16.obligations(moved)) == 1, moved.corrections
        # 3. The members of a union include the members of its sums: offered to a hole, inhabiting it, loading as it.
        subject = test.types["Subject"]
        assert [lit(one).value for one in scriptt16.members(subject)] == ["the page", "the mod"]
        shown = read("Show it.", X.script({"Show it.": "show"}))
        assert [len(one["offered"]) for one in shown.decisions if one["path"] == "subject"] == [2]
        assert scriptt16.inhabits(scriptt16.members(test.types["Surface"])[1].value, subject) and not scriptt16.inhabits(99, subject)
        assert scriptt16.term_from({"constant": "the mod", "type": "Subject"}, test, {}).value.name == "MOD"
        # 4. A reference to no operation inside a record or a collection is a diagnostic, not a crash.
        compared = read("Redesign the mod. Compare it with the page.", X.told(X.CASE["C10"].runs[1].expect["read"]["obligations"]))
        line = json.loads(json.dumps(scriptt16.record(compared)))
        assert scriptt16.load(line, test)[1] == []
        line["phrases"][1]["terms"][0]["arguments"]["surfaces"]["several"] = [{"ref": "99"} if "ref" in one else one for one in line["phrases"][1]["terms"][0]["arguments"]["surfaces"]["several"]]
        assert scriptt16.load(line, test)[1] == [(1, "surfaces", "reference")]
        boxes = world_of(X.world_source(X.BOX_WORLD), folder)
        packed = read("Redesign the mod. Pack it in a box.", X.told(X.CASE["C10"].runs[0].expect["read"]["obligations"]), boxes, X.BOX_WORLD)
        line = json.loads(json.dumps(scriptt16.record(packed)))
        assert scriptt16.load(line, boxes)[1] == []
        line["phrases"][1]["terms"][0]["arguments"]["box"]["fields"]["surface"] = {"ref": "99"}
        loaded, found = scriptt16.load(line, boxes)
        assert found == [(1, "box.surface", "reference")] and not scriptt16.complete(scriptt16.obligations(loaded)[1][1])
        # 5. A value with no place in the text joins a phrase only when one is given.
        page = scriptt16.members(test.types["Surface"])[0]
        assert scriptt16.edit(reading, None, "redesign.surface", page, world=test)[1] == [(None, "surface", "phrase")]
        placed, faults = scriptt16.edit(reading, None, "redesign.surface", page, world=test, phrase=(0, len(reading.text)))
        assert faults == [] and scriptt16.say(scriptt16.obligations(placed)[1][1]) == "redesign(surface='the page')"
        # 6. A parameter the function does not declare is extra, also past a parameter.
        assert scriptt16.edit(reading, None, "redesign.bad_param", mod, world=test)[1] == [(None, "bad_param", "extra")]
        assert scriptt16.edit(reading, None, "redesign.surface.colour", mod, world=test)[1] == [(None, "surface.colour", "extra")]
        assert scriptt16.edit(reading, None, "no_such.surface", mod, world=test)[1] == [(None, "surface", "name")]


def test_final_review():
    """The final review's counterexamples of 0249f2b, each beside its positive control."""
    with tempfile.TemporaryDirectory() as name:
        folder = pathlib.Path(name)
        test = world_of(WORLD, folder)
        read = lambda text, script, world=test: scriptt16.read(text, world, [], Standin(script, X.World(), world), join=False)
        again = lambda reading, world=test: scriptt16.load(json.loads(json.dumps(scriptt16.record(reading))), world)
        # A1. Every unresolved operation of a phrase survives save and load, in its place.
        text = "Email an accountant, redesign the mod and book a flight."
        three = read(text, X.script({text: (X.ABSTAIN, "redesign", X.ABSTAIN)}, {(text, "redesign", "surface"): X.MOD}))
        loaded, found = again(three)
        assert found == [] and [type(term).__name__ for _, term in scriptt16.obligations(loaded)] == ["Unresolved", "Application", "Unresolved"] == [type(term).__name__ for _, term in scriptt16.obligations(three)]
        # A2. Two operations with one number do not load.
        shown = read("Redesign the mod. Then show it.", X.told(X.REDESIGN_SHOW))
        line = json.loads(json.dumps(scriptt16.record(shown)))
        assert scriptt16.load(line, test)[1] == []
        line["phrases"][1]["terms"][0]["id"] = "0"
        assert scriptt16.load(line, test) == (None, [(None, None, "identity")])
        # A3, A4. The gate compares what a function means, and a corpus line under another world is a regression, not a crash.
        accepted = json.loads(json.dumps(scriptt16.record(read("Redesign the mod.", X.told(X.REDESIGN_SHOW[:1])))))
        model = Standin(X.told(X.REDESIGN_SHOW[:1]), X.World(), test)
        assert scriptt16.gate(WORLD + '\ndef paint(surface: Surface) -> Observed:\n    "paint it"\n', folder, [accepted], model, test, WORLD).activated
        deleting = WORLD.replace('"change how it looks"', '"delete it permanently"')
        assert scriptt16.gate(deleting, folder, [accepted], Standin(X.told(X.REDESIGN_SHOW[:1]), X.World(), world_of(deleting, folder)), test, WORLD).regressions == [(0, 0)]
        elsewhere = dict(accepted, world="another world")
        assert scriptt16.gate(WORLD + '\ndef paint(surface: Surface) -> Observed:\n    "paint it"\n', folder, [elsewhere], model, test, WORLD).regressions == [(0, None)]
        # A5. A saved check is kept only for the reading it judged; an edit clears it.
        checked, _, _ = scriptt16.check(shown, "", [], [("evidence", lambda term, artifact: False)], model)
        assert again(checked)[0].fulfillment == checked.fulfillment and scriptt16.edit(checked, 1, "subject", shown.constants[0])[0].fulfillment is None
        forged = json.loads(json.dumps(scriptt16.record(checked)))
        forged["fulfillment"] = [{"obligation": 7, "criterion": "x", "outcome": "PASS", "evidence": 0, "claim": 1.0}]
        assert scriptt16.load(forged, test)[0].fulfillment is None
        # A6. A restored snapshot is a draft over the latest one: it can be saved; a draft from an old snapshot cannot.
        store = folder / "store.jsonl"
        first, _ = scriptt16.save(shown, store)
        second, _ = scriptt16.save(scriptt16.edit(first, 1, "subject", shown.constants[0])[0], store)
        restored, _ = scriptt16.restore(store, 1, test)
        assert scriptt16.save(restored, store)[1] == [] and scriptt16.save(scriptt16.load(scriptt16.saved(store)[0], test)[0], store)[1] == [(None, None, "stale")]
        # A7. A bare record is no collection of records.
        many_cells = world_of(WORLD + '\ndef open_cells(cells: Many[Cell]) -> Observed:\n    "open several cells"\n', folder)
        cell = Record(many_cells.types["Cell"], {"notebook": Constant(many_cells.types["Path"], pathlib.Path("notes.md"), -1, -1), "number": Constant(many_cells.types["int"], 3, -1, -1)})
        assert scriptt16.checked({"cells": cell}, dict(many_cells.functions["open_cells"].parameters)) == [("cells", "type")]
        assert scriptt16.checked({"cells": Several(many_cells.types["Cell"], (cell,))}, dict(many_cells.functions["open_cells"].parameters)) == []
        # A8. A function is not applied inside a quote: a quote asks nothing.
        quote = '"I compared the page and the mod for you today." Thanks.'
        quoted = scriptt16.read(quote, test, [X.QUOTED], Standin(X.script({}), X.World(), test), join=False)
        in_quote = next(one for one in quoted.constants if lit(one) == X.MOD and one.start < 50)
        assert scriptt16.edit(quoted, None, "redesign.surface", in_quote, world=test)[1] == [(None, "surface", "phrase")]
        mine = read("Thanks for the mod.", X.script({}))
        assert scriptt16.edit(mine, None, "redesign.surface", mine.constants[0], world=test)[1] == []
        # A10. One failing artifact about an operation fails it, whatever another says.
        redesign = scriptt16.obligations(shown)[0][1]
        good, bad = (scriptt16.Artifact("redesign", dict(scriptt16.bindings(redesign)), redesign.number) for _ in range(2))
        outcome = lambda artifacts: [(one.outcome, one.evidence) for one in scriptt16.check(shown, "", artifacts, [("works", lambda term, artifact: artifact is good)], model)[0].fulfillment][0]
        assert outcome([good]) == (X.PASS, 0) and outcome([bad, good]) == (X.FAIL, 0)
        # A11. A constant's span must say its value.
        moved = json.loads(json.dumps(scriptt16.record(shown)))
        assert scriptt16.load(moved, test)[1] == []
        moved["phrases"][0]["terms"][0]["arguments"]["surface"]["at"] = [0, 8]
        assert scriptt16.load(moved, test)[1] == [(0, "surface", "identity")]
        outside = dict(moved)
        outside["phrases"][0]["terms"][0]["arguments"]["surface"]["at"] = [999, 1005]
        assert scriptt16.load(outside, test)[1] == [(0, "surface", "identity")]
        # B. A function is never its own new argument; a brand's words inhabit it; a requested operation stays requested after a later edit; a correction keeps which of its phrase's operations it is.
        assert not any(isinstance(term, Application) and term.number is None and term.function.name == "redesign"
                       for one in read("Redesign the mod.", X.told(X.REDESIGN_SHOW[:1])).decisions if one["path"] == "surface" for term in one["offered"])
        assert scriptt16.inhabits("hello", test.types["Asked"]) and not scriptt16.inhabits(5, test.types["Asked"])
        base = read("Redesign the mod.", X.told(X.REDESIGN_SHOW[:1]))
        asked, _ = scriptt16.edit(base, None, "show.subject", base.constants[0], correction=True, world=test)
        changed, _ = scriptt16.edit(asked, 1, "subject", scriptt16.obligations(asked)[0][1])
        assert [one["requested"] for one in changed.corrections] == [True]
        rerun = scriptt16.rerun(json.loads(json.dumps(scriptt16.record(changed))), test, Standin(X.told(X.REDESIGN_SHOW[:1]), X.World(), test))
        assert [scriptt16.say(term) for _, term in scriptt16.obligations(rerun)] == ["redesign(surface='the mod')", "show(subject=redesign(surface='the mod'))"]
        two = "Show the mod and the page."
        script = X.script({two: "show"}, {(two, "show", "subject"): X.MOD})
        one = read(two, script)
        both, _ = scriptt16.edit(one, None, "show.subject", next(one_ for one_ in one.constants if lit(one_) == X.PAGE), world=test)  # a second show in the phrase, by edit
        corrected, faults = scriptt16.edit(both, 1, "subject", next(one_ for one_ in one.constants if lit(one_) == X.MOD), correction=True)
        assert faults == [] and corrected.corrections[0]["of"] == 2
        one_show = scriptt16.rerun(json.loads(json.dumps(scriptt16.record(corrected))), test, Standin(script, X.World(), test))
        assert one_show.corrections[0]["status"] == "invalidated" and "show" in one_show.corrections[0]["reason"]  # the phrase now asks for 1 show where it had 2
        single, _ = scriptt16.edit(one, 0, "subject", next(one_ for one_ in one.constants if lit(one_) == X.PAGE), correction=True)
        kept = scriptt16.rerun(json.loads(json.dumps(scriptt16.record(single))), test, Standin(script, X.World(), test))
        assert kept.corrections[0]["status"] == "retained" and scriptt16.say(scriptt16.obligations(kept)[0][1]) == "show(subject='the page')"
        # B. A whole collection beyond the bound is recorded as cut.
        extra = "".join(f'\ndef gather{index}(surface: Surface) -> Many[Observed]:\n    "gather notes {index}"\n' for index in range(9)) + '\ndef summarize(notes: Many[Observed]) -> Written:\n    "summarize notes"\n'
        gathered = scriptt16.read("Summarize the mod.", world_of(WORLD + extra, folder), [], Standin(X.script({"Summarize the mod.": "summarize"}), X.World(extra=extra), world_of(WORLD + extra, folder)), join=False)
        assert [len(one["cut"]) for one in gathered.decisions if one["path"] == "notes"][:1] == [1]


def test_same_words_once():
    """The live d1 answered "also" with the same function again for the same words; it is not offered again without a new value, and a repeat is the same request.

    The model below always picks redesign when it is offered, else "nothing more", and for a hole the first value of the
    text it has not picked in that phrase.
    """
    test = world_of(WORLD)
    picked: list[tuple[str, str]] = []
    def always(state, asked):
        answers = {}
        for key, question in asked.items():
            ids = {one["description"]: one["id"] for one in question.get("options", [])}
            fresh = [text for text in ids if text.startswith("'") and (state, text) not in picked]
            picked.extend((state, text) for text in fresh[:1] if key == "which")
            pick = ids.get("change how it looks") or ids.get(scriptt16.ELSE[scriptt16.NOTHING]) if key in ("what", "also") else ids.get((fresh or [""])[0], ids.get(scriptt16.NONE_OF_THESE))
            answers[key] = Standin.shares(list(ids.values()), pick) if ids else {"p_true": 0.9 if key == "0" else 0.1}
        return answers
    once = scriptt16.read("Redesign the mod. Show the page.", test, [], always, join=False)
    assert [scriptt16.say(term) for _, term in scriptt16.obligations(once)] == ["redesign(surface='the mod')", "redesign(surface='the page')"]
    twice = scriptt16.read("Redesign the mod and the page.", test, [], always, join=False)
    assert [term.function.name for _, term in scriptt16.obligations(twice)] == ["redesign", "redesign"]  # a second value in the phrase still allows a second redesign
    offered = [[one["description"] for one in decision["asked"]["also"]["options"]] for decision in once.decisions if "also" in decision["asked"]]
    assert offered and all("change how it looks" not in one for one in offered)  # no value left for another redesign: it is not offered
    def live_like(state, asked):  # as the live d1 answered "Test the search too.": test, then research of its result, again and again
        answers = {}
        for key, question in asked.items():
            ids = [one["id"] for one in question.get("options", [])]
            want = {"what": "test", "also": "research"}.get(key, "0")
            answers[key] = Standin.shares(ids, want if want in ids else scriptt16.NOTHING)
        return answers
    tested = scriptt16.read("Test the search too.", world_of((HERE / "world.py").read_text()), [], live_like, join=False)
    assert [scriptt16.say(term) for _, term in scriptt16.obligations(tested)] == ["test(subject='the search')", "research(topic=test(subject='the search'))"]  # the repeat is the same request


def test_chosen_rule():
    """The operation questions use the 0.1.6 rule (scriptt16.chosen), with the shares the live d1 gave for "Redesign the mod."."""
    test = world_of((HERE / "world.py").read_text())
    def model(also: dict):
        def answer(state, asked):
            found = {}
            for key, question in asked.items():
                ids = [one["id"] for one in question.get("options", [])]
                given = {"what": {"redesign": 0.72, scriptt16.NONE: 0.11, "build": 0.09}, "also": also}.get(key, {"0": 0.86, "none": 0.14})
                rest = (1 - sum(share for one, share in given.items() if one in ids)) / max(1, len([one for one in ids if one not in given]))
                found[key] = {"probabilities": {one: given.get(one, rest) for one in ids}}
            return found
        return answer
    names = lambda also: [scriptt16.say(term) if isinstance(term, Application) else f"? {term.reason}" for _, term in scriptt16.obligations(scriptt16.read("Redesign the mod.", test, [], model(also), join=False))]
    assert names({"build": 0.34, scriptt16.NONE: 0.29, scriptt16.NOTHING: 0.10}) == ["redesign(surface='the mod')"]  # a weak argmax is nothing more
    assert names({"research": 0.8, scriptt16.NONE: 0.05, scriptt16.NOTHING: 0.05}) == ["redesign(surface='the mod')", "research(topic='Redesign the mod.')"]  # a strong second function
    assert names({scriptt16.NONE: 0.52, "delegate": 0.17, scriptt16.NOTHING: 0.06})[1] == "? rejected"  # (none) at half or more: a request outside the world
    shares = lambda pairs: scriptt16.Choice(pairs, max(pairs, key=pairs.get))
    assert (scriptt16.chosen(shares({"build": 0.4, scriptt16.NONE: 0.3, scriptt16.NOTHING: 0.1})), scriptt16.chosen(shares({"build": 0.41, scriptt16.NONE: 0.3, scriptt16.NOTHING: 0.1}))) == (scriptt16.NOTHING, "build")
    assert scriptt16.chosen(shares({"build": 0.5, scriptt16.NONE: 0.5})) == scriptt16.NONE and scriptt16.chosen(scriptt16.Choice({}, None)) is None


UNIT_TESTS = [test_chosen_rule, test_same_words_once, test_final_review, test_review_0249f2b, test_rules, test_kinds, test_types, test_faults, test_grounding, test_synthesis, test_record_shape, test_specimen]


# ---- Laws over the real next/world.py -------------------------------------------------
#
# Each law is a plain loop over what next/world.py declares. The right inhabitants are
# generated from each declaration; the wrong ones contradict it. Nothing here asks d1
# except through the stand-in, and nothing compares an engine judgment with itself.


def inhabitants(kind, world: agree.World) -> list:
    """Returns terms built from a declared type alone: each one is a value of that type."""
    match kind:
        case agree.Applied(constructor=constructor, argument=inner) if constructor == agree.MAYBE:
            return [Empty(kind)] + inhabitants(inner, world)
        case agree.Applied(constructor=constructor, argument=inner) if constructor == agree.MANY:
            return [Several(inner, ()), *[Several(inner, (one,)) for one in inhabitants(inner, world)[:1]]]
        case agree.Applied(argument=inner):
            return inhabitants(inner, world)
        case agree.Sum(alternatives=alternatives):
            return [Constant(kind, one, -1, -1) for one in alternatives if isinstance(one, agree.Member)] + [found for one in alternatives if not isinstance(one, agree.Member) for found in inhabitants(one, world)]
        case agree.Product(fields=fields):
            return [Record(kind, {name: inhabitants(field, world)[0] for name, field in fields})]
        case agree.Base(python=python) if python is int:
            return [Constant(kind, 3, -1, -1)]
        case agree.Base(python=python) if python is pathlib.Path:
            return [Constant(kind, pathlib.Path("world.py"), -1, -1)]
    return [Constant(kind, "some words", -1, -1)]


def enums_in(kind) -> set[str]:
    """Returns the names of the enums that a declared type admits, read from its declaration."""
    match kind:
        case agree.Applied(argument=inner) | agree.Brand(of=inner):
            return enums_in(inner)
        case agree.Sum(name=name, alternatives=alternatives):
            return ({name} if any(isinstance(one, agree.Member) for one in alternatives) else set()) | {found for one in alternatives if not isinstance(one, agree.Member) for found in enums_in(one)}
    return set()


def law_values(world: agree.World) -> list[str]:
    """Every generated value of a parameter's type validates there and survives record and load with its meaning;
    a member of another enum, a non-member, and constructor values of another type are rejected."""
    found = []
    enums = {name: one for name, one in world.types.items() if isinstance(one, agree.Sum) and any(isinstance(m, agree.Member) for m in one.alternatives)}
    count = 0
    for function in world.functions.values():
        for name, kind in function.parameters:
            rights = inhabitants(kind, world)
            wrongs = [Constant(one, 99, -1, -1) for one in enums.values()]
            wrongs += [scriptt16.members(one)[0] for other, one in enums.items() if other not in enums_in(kind)]
            wrongs += [Empty(agree.Applied(agree.MAYBE, world.types["int"] if "int" in world.types else agree.Base("int", int)))]
            wrongs += [Several(agree.Base("int", int), ())] + ([Several(world.types["Words"], (scriptt16.members(enums["Surface"])[0],))] if "Surface" in enums else [])
            for value, right in [(one, True) for one in rights] + [(one, False) for one in wrongs if not (isinstance(kind, agree.Applied) and kind.constructor == agree.MANY and isinstance(one, Several) and not one.terms and agree.show(one.element) == agree.show(kind.argument))]:
                count += 1
                faults = [one for one in scriptt16.checked({name: value}, {name: kind}) if one[0] == name]
                if bool(faults) == right:
                    found.append(f"{function.name}.{name}: {scriptt16.say(value)} of {agree.show(scriptt16.type_of(value))} {'rejected' if right else 'accepted'}: {faults}")
                elif right:
                    record = json.loads(json.dumps(scriptt16.term_record(value, set())))
                    if scriptt16.value_of(scriptt16.term_from(record, world, {}), {}) != scriptt16.value_of(value, {}):
                        found.append(f"{function.name}.{name}: {scriptt16.say(value)} changed meaning through record and load")
    return found + ([] if count > 50 else [f"only {count} values were tried"])


def law_composition(world: agree.World) -> list[str]:
    """An existing result of every function stays a candidate wherever its declared result type is wanted, whole collections and optionals included."""
    found = []
    extended = agree.loads((HERE / "world.py").read_text() + '\ndef summarize(findings: Many[Observed]) -> Written:\n    "summarize findings"\n'
                           '\ndef keep(found: Maybe[Path]) -> Written:\n    "keep it"\n'.replace("Maybe[Path]", "Maybe[pathlib.Path]"), world.folder)
    for producer in extended.functions.values():
        result = Application(producer, {name: Hole(kind) for name, kind in producer.parameters}, 0)
        for consumer in extended.functions.values():
            for name, kind in consumer.parameters:
                wanted = scriptt16.later(producer.result) and agree.show(producer.result.argument) == agree.show(kind) or agree.show(producer.result) == agree.show(kind)
                if not wanted or consumer == producer:
                    continue
                search = scriptt16.Search("", extended, lambda state, asked: {}, scriptt16.Limits(), [], iter(range(1, 99)))
                scriptt16.solve(kind, scriptt16.Environment((), (result,)), search, "", name, consumer, 1)
                if not any(one is result for decision in search.decisions for one in decision["offered"]):
                    found.append(f"{producer.name}'s result ({agree.show(producer.result)}) is not offered to {consumer.name}.{name}")
    return found + ([] if "summarize" in extended.functions else ["the aggregate consumer did not load"])


def law_identity(world: agree.World) -> list[str]:
    """Evidence, corrections, readiness, the gate, d1's answers, the world, the source and the store keep identity."""
    found = []
    with tempfile.TemporaryDirectory() as name:
        folder = pathlib.Path(name)
        test = world_of(WORLD, folder)
        twice = "Redesign the mod. Redesign the mod again."
        model = Standin(X.script({"Redesign the mod.": "redesign", "Redesign the mod again.": "redesign"}, {("Redesign the mod.", "redesign", "surface"): X.MOD, ("Redesign the mod again.", "redesign", "surface"): X.MOD}), X.World(), test)
        reading = scriptt16.read(twice, test, [], model, join=False)
        first, second = [term for _, term in scriptt16.obligations(reading)]
        mod = next(one for one in reading.constants if lit(one) == X.MOD)
        always = [("evidence", lambda term, artifact: True)]
        outcomes = [one.outcome for one in scriptt16.check(reading, "", [scriptt16.Artifact("redesign", {"surface": mod})], always, model)[0].fulfillment]
        if X.PASS in outcomes:
            found.append(f"one artifact without an operation fulfilled two identical operations: {outcomes}")
        outcomes = [one.outcome for one in scriptt16.check(reading, "", [scriptt16.Artifact("redesign", {"surface": mod}, second.number)], always, model)[0].fulfillment]
        if outcomes != [X.UNVERIFIED, X.PASS]:
            found.append(f"an artifact naming the second operation gave {outcomes}")
        # A correction keeps its source occurrence when a rerun adds an operation in an earlier phrase.
        text = "Show the mod. Show the page."
        binds = {("Show the mod.", "show", "subject"): X.MOD, ("Show the page.", "show", "subject"): X.PAGE}
        model = Standin(X.script({"Show the mod.": "show", "Show the page.": "show"}, binds), X.World(), test)
        reading = scriptt16.read(text, test, [], model, join=False)
        _, page_show = [term for _, term in scriptt16.obligations(reading)]
        draft, faults = scriptt16.edit(reading, page_show.number, "subject", next(one for one in reading.constants if lit(one) == X.MOD), correction=True)
        more = Standin(X.script({"Show the mod.": ("show", "show"), "Show the page.": "show"}, binds), X.World(), test)
        again = scriptt16.rerun(json.loads(json.dumps(scriptt16.record(draft))), test, more)
        shown = [(again.text[phrase.start:phrase.end].strip(), scriptt16.say(term)) for phrase, term in scriptt16.obligations(again)]
        if faults or shown[-1] != ("Show the page.", "show(subject='the mod')") or again.corrections[0]["status"] != "retained":
            found.append(f"a correction moved after a rerun: {shown}, {again.corrections}")
        # An invalid correction is not recorded; a correction of an unknown operation is refused.
        if scriptt16.edit(reading, page_show.number, "subject", Hole(test.types["Cell"], "cleared"), correction=True)[0].corrections or scriptt16.edit(reading, 99, "subject", mod, correction=True)[1] != [(99, "subject", "reference")]:
            found.append("an invalid correction was recorded")
        # Readiness of a consumer needs a valid producer.
        model = Standin(X.told(X.REDESIGN_SHOW), X.World(), test)
        reading = scriptt16.read("Redesign the mod. Then show it.", test, [], model, join=False)
        redesign, show = [term for _, term in scriptt16.obligations(reading)]
        broken = copy.deepcopy(reading)
        broken_redesign = [term for _, term in scriptt16.obligations(broken)][0]
        broken_redesign.arguments["surface"] = Constant(test.types["Surface"], 99, -1, -1)
        if scriptt16.sound(broken, [term for _, term in scriptt16.obligations(broken)][1]):
            found.append("a consumer of an invalid producer is sound")
        # The gate sees a change of result type and pending, unless the change is migrated.
        line = json.loads(json.dumps(scriptt16.record(reading)))
        later = WORLD.replace("def redesign(surface: Surface) -> Later[Surface]:", "def redesign(surface: Surface) -> Surface:")
        proposer = Standin(X.told(X.REDESIGN_SHOW), X.World(), world_of(later, folder))
        if scriptt16.gate(later, folder, [line], proposer, test, WORLD).activated or not scriptt16.gate(later, folder, [line], proposer, test, WORLD, migrations=((0, 0), (0, 1))).activated:
            found.append("the gate let a Later result become plain without a migration, or refused the migration")
        # d1's malformed shares are invalid answers.
        question = scriptt16.OneOf("q", {"0": "a", "1": "b"})
        for shares in ({"0": float("nan"), "1": 0.5}, {"0": float("inf"), "1": 0.0}, {"0": -0.5, "1": 1.5}, {"0": 0.5, "1": 0.2}):
            if scriptt16.answer(question, {"probabilities": shares}).best is not None:
                found.append(f"the shares {shares} were accepted")
        if any(scriptt16.answer(scriptt16.YesNo("q"), {"p_true": value}) is not None for value in (1.5, -0.1, float("nan"))):
            found.append("a p_true out of range was accepted")
        # The world's identity holds the provenance of its members; a changed source text is reported; a stale draft is not saved.
        if agree.identity(test) == agree.identity(world_of(WORLD.replace('MOD: Asked = "the mod"', 'MOD: Written = "the mod"'), folder)):
            found.append("a member's provenance is not part of the world's identity")
        tampered = dict(line, text=line["text"].replace("mod", "pod"))
        if scriptt16.load(tampered, test)[1] != [(None, None, "identity")]:
            found.append("a saved reading with another source text loaded as the same reading")
        store = folder / "store.jsonl"
        base, _ = scriptt16.save(reading, store)
        one, _ = scriptt16.edit(base, show.number, "subject", mod)
        two, _ = scriptt16.edit(base, show.number, "subject", Hole(test.types["Subject"], "cleared"))
        scriptt16.save(one, store)
        if scriptt16.save(two, store)[1] != [(None, None, "stale")]:
            found.append("a draft from a superseded snapshot was saved")
    return found


def head_hashes() -> dict[str, str | None]:
    """Returns the sha256 of each snapshot file as committed at HEAD, or None for a file that is not committed."""
    found = {}
    for name in X.SNAPSHOT_FILES:
        blob = subprocess.run(["git", "-C", str(HERE.parent), "show", f"HEAD:{name}"], capture_output=True)
        found[name] = hashlib.sha256(blob.stdout).hexdigest() if blob.returncode == 0 else None
    return found


LAW_CONTROLS = (
    ("values", "a constant of any value inhabits its type", "inhabits", lambda original: lambda value, kind: True),
    ("composition", "a whole collection or optional is never a candidate", "candidates",
     lambda original: lambda goal, *rest: [] if isinstance(goal, agree.Applied) and goal.constructor in (agree.MANY, agree.MAYBE) else original(goal, *rest)),
    ("identity", "an artifact is about every operation with its function and arguments", "about", lambda original: lambda application, artifact, index: artifact.function == application.function.name),
)

LAWS = {"values": law_values, "composition": law_composition, "identity": law_identity}

# What each law establishes, for the coverage report of the inventory.
LAW_COVERS = {"values": ("I2", "I6", "C11"), "composition": ("I4", "C07", "C09"), "identity": ("I5", "I3", "I7", "I9", "C17", "C18", "C19", "C20", "C22", "R1")}


def coverage(results: dict[str, list[str]]) -> list[tuple[str, str, list[str], list[str]]]:
    """Returns, for each requirement of the inventory, the checks of this run that test it and the ones that failed.

    This is accounting, not a verdict on the English requirement: a requirement is
    established only as far as its linked cases, controls and laws test it.
    """
    rows = {row["invariant"]: row["checks"] for row in X.INVARIANT_TABLE}
    found = []
    for one in X.REQUIREMENTS:
        if one["kind"] == "invariant":
            linked = rows[one["id"]]
        elif one["kind"] == "wrong implementation":
            linked = [one["id"]]
        elif one["kind"] in ("record", "process"):
            linked = [key for key in one["checked_by"].split(", ") if key in X.CASE]
        else:
            linked = [one["id"]]
        linked += [f"law {law}" for law, covers in LAW_COVERS.items() if one["id"] in covers]
        found.append((one["id"], one["kind"], linked, [key for key in linked if results.get(key, ["not run"])]))
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
    ("W1", "always accept gate changes", "C02", "gate", lambda original: lambda source, folder, lines, model, active, active_source, limits=scriptt16.Limits():
        scriptt16.Gate(True, X.PASS, [], [], agree.loads(source, folder), source, lines), "world change expected"),
    ("W2", "drop an unresolved obligation", "C01", "obligations", lambda original: lambda reading: [one for one in original(reading) if not isinstance(one[1], Unresolved)], "expected 1 obligations"),
    ("W3", "include every local Many item", "C03", "solve", every_local, "binding surfaces"),
    ("W4", "ignore nested pending dependencies", "C10", "pending", lambda original: lambda term: isinstance(term, Application) and scriptt16.later(term.function.result), "status: expected 'pending'"),
    ("W5", "duplicate a shared result", "C15", "term_record", lambda original: lambda term, written: original(term, set()), "expected 3 obligations"),
    ("W7", "store answers other than d1's", "C22", "ask", lambda original: lambda *args: (lambda result: (result[1].__setitem__("answers", json.loads(json.dumps(result[1]["answers"]).replace("0.9", "0.8"))), result)[1])(original(*args)),
     "answers differ from what d1 returned"),
    ("W6", "certify all repeated operations from one generic reply", "C20", "check", lambda original: lambda *args, **keys: (lambda found: (
        dataclasses.replace(found[0], fulfillment=[dataclasses.replace(one, outcome=X.PASS) if (one.claim or 0) >= 0.5 else one for one in found[0].fulfillment]), X.PASS, found[2]))(original(*args, **keys)),
     "obligation 1 'evidence'"),
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
    committed = head_hashes()
    for name, sha in provenance["files"].items():
        print(f"  {'committed at HEAD' if committed.get(name) == sha else 'NOT AS COMMITTED' if committed.get(name) else 'not in git (not imported)'}: {name}")
    for name, path in loaded.items():
        print(f"  imported {name:<14} {pathlib.Path(path).resolve()}  sha256 {hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()}")
    failures: list[str] = []
    failures += [f"{name} was imported from {path}, outside {X.DECLARED_ROOT}" for name, path in loaded.items() if not pathlib.Path(path).resolve().is_relative_to(X.DECLARED_ROOT)]
    imported = [pathlib.Path(path).resolve().relative_to(HERE.parent).as_posix() for path in loaded.values() if pathlib.Path(path).resolve().is_relative_to(HERE.parent)]
    failures += [f"L4: {name} is imported but differs from HEAD (the tested tree is not the commit)" for name in imported
                 if name in committed and committed[name] != hashlib.sha256((HERE.parent / name).read_bytes()).hexdigest()]
    failures += [f"L4: {name} is imported but not committed" for name in imported if subprocess.run(["git", "-C", str(HERE.parent), "cat-file", "-e", f"HEAD:{name}"]).returncode]

    for test in UNIT_TESTS:
        try:
            test()
            print("passed", test.__name__)
        except Exception as error:
            failures.append(f"{test.__name__}: {type(error).__name__}: {error}")
            print("FAILED", test.__name__, error)

    observed, results = {}, {}
    for case in X.CASES + X.LAWS:
        observed[case.id] = observed_case(case)
        found = results[case.id] = X.PREDICATES[case.id](observed[case.id]) + fidelity(observed[case.id])
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
        found = X.PREDICATES[case_id](wrong_observation) if wrong_observation is not None else found
        caught = [line for line in found if diagnostic in line]
        print(f"  projection {key:<5} {'caught' if caught else 'MISSED'}: {words} -> {(caught or found or [''])[0][:140]}")
        failures += [] if caught else [f"projection control {key} ({words}) not caught: {found[:3]}"]

    engine = {}
    for key, words, case_id, name, value, diagnostic in ENGINE_CONTROLS:
        with patched(name, value):
            engine[key] = observed_case(X.CASE[case_id])
        found = X.PREDICATES[case_id](engine[key]) + fidelity(engine[key])
        caught = [line for line in found if diagnostic in line]
        results[key] = [] if caught else [f"{key} not caught"]
        print(f"  engine {key} {'caught' if caught else 'MISSED'}: {words} (scriptt16.{name} patched) -> {(caught or found or [''])[0][:160]}")
        failures += [] if caught else [f"engine control {key} ({words}) not caught: {found[:3]}"]

    for key, check in X.LOCATION_PREDICATES.items():
        found = results[key] = X.l4(provenance, X.snapshot()["files"]) if key == "L4" else check(provenance)
        failures += found
        print(f"{key} {'pass' if not found else found}")

    world = world_from(X.World("next"), HERE.parent)[0]
    for law, check in LAWS.items():
        found = results[f"law {law}"] = check(world)
        failures += found
        print(f"law {law}: {'holds' if not found else found}")

    for law, words, name, value in LAW_CONTROLS:
        with patched(name, value):
            found = LAWS[law](world)
        print(f"  law control {'caught' if found else 'MISSED'}: {words} (scriptt16.{name} patched) -> {(found or [''])[0][:140]}")
        failures += [] if found else [f"law control {law}: {words} not caught"]

    print("coverage of the requirement inventory: which checks of this run test each requirement (accounting, not a verdict on its words)")
    for key, kind, linked, failed in coverage(results):
        print(f"  {key:<4} {kind:<20} " + (f"tested by {', '.join(linked)}" + (f"; FAILED: {failed}" if failed else "") if linked else "not tested by this run: checked by the final report"))
    table = [row | {"observed": "not tested by this run" if not row["checks"] else "pass: " + ", ".join(row["checks"]) if not any(results.get(key) for key in row["checks"]) else
                    {key: results[key][:2] for key in row["checks"] if results.get(key)}} for row in X.INVARIANT_TABLE]
    for row in table:
        print(f"  {row['invariant']}: {row['observed']}")
    print("INVARIANT_TABLE " + json.dumps(table))

    print("deferred, not tested by this run: project-wide object navigation (which actual notebook a phrase means); identity of an object across messages; live d1 (every model answer here is the stand-in's)")
    print("the laws are structural checks over next/world.py and its declarations; they are no evaluation of the real d1")
    status = subprocess.run(["git", "-C", str(HERE.parent), "status", "--porcelain", "--untracked-files=all"], capture_output=True, text=True).stdout
    dirty = [line[3:] for line in status.splitlines()]  # any change or untracked file in the worktree, which could shadow a module
    if dirty:
        failures.append(f"not final: uncommitted {dirty}")
    print(f"receipt: {'FINAL' if not failures else 'NOT FINAL'}: engine commit {provenance['commit']}, expectations version {X.ORACLE_VERSION}"
          + (f", uncommitted {dirty}" if dirty else ", engine and expectations committed"))
    print(f"{len(X.CASES)} cases, {len(X.NEGATIVE_CONTROLS)} projection controls, {len(ENGINE_CONTROLS)} engine controls, {len(UNIT_TESTS)} unit tests, {len(X.LAWS)} oracle laws, {len(LAWS)} engine laws: "
          + ("all passed" if not failures else f"{len(failures)} FAILURES"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
