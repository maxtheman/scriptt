"""The acceptance criteria of next: seven checks, each shown to pass a good case and to reject a broken one.

Each criterion of the spec (Part 4.2, C1 to C7) has one check function. The runner applies the
same check function twice:

1. To the positive case, which the engine produces end to end with the model: the real d1 by
   default. No reading is pinned: d1 decides every choice that it decides in use. Every message is
   read on the product path, ``turns.start_turn`` (``product_reading``), as the hook and the
   notebook read it: with join on, so that d1 decides whether neighbouring sentences are one phrase.
2. To the deliberate failure control, which the engine produces with one old rule put back for
   that run only (``put_back``): the old ``taken_by`` rule of ``derivations``, the old greedy
   ``Many``, the old producers of depth 0 and the old ``ungrounded`` of spans only, a load that
   ignores the corrections or a hook that reads the reading before them, the old check of the
   reply alone, and the old gate of bits alone. For C1 one control is a reading with one
   obligation marked as nothing. C1 and C2 also read their messages with the old join wording
   (``OLD_JOIN``), which joined a sentence that asks for its own action into the one before it.

A row passes only if the check holds on the positive case. It caught the deliberate failure only
if the same check rejects the control. The checklist of each criterion (the obligations, bindings
and states that it expects) is written in this file, never derived from ``scriptt16.read``: a
parser that drops a phrase cannot drop it from its own checklist. If d1 does not answer, a row is
BLOCKED.

    python3.14 next/acceptance.py
"""

import ast
import contextlib
import dataclasses
import pathlib
import shutil
import sys
import tempfile
import types
import typing

HERE = pathlib.Path(__file__).resolve().parent
for needed in (str(HERE.parent / ".scriptt"), str(HERE)):
    if needed not in sys.path:
        sys.path.insert(0, needed)

import agree  # noqa: E402
import harness as shipped  # noqa: E402
import scriptt16  # noqa: E402
import turns  # noqa: E402
from agree import MANY, Applied, Base, Brand, Member, Product, Sum, Type, is_subtype, show  # noqa: E402
from scriptt16 import Application, Choice, Constant, Limits, Reading, Record, Several  # noqa: E402

PASS, FAIL, UNVERIFIED, BLOCKED = "PASS", "FAIL", "UNVERIFIED", "BLOCKED"
"""The results of a criterion."""

type Decided = tuple[bool, str]
"""What a check function returns: whether the criterion holds, and the evidence that it saw."""


@dataclasses.dataclass(frozen=True)
class Criterion:
    """One acceptance criterion, with what its check saw on the positive case and on the control.

    Attributes:
        id: The identifier, C1 to C7.
        requirement: The words of the requirement, and where they come from.
        passing_outcome: What must observably be true.
        check: What the check function decides, and what the control is.
        evidence: What the check saw: terms, shares, states and gate fields, for
            the positive case and for the control.
        result: "PASS" if the check holds on the positive case, "FAIL" if it
            does not, "BLOCKED" if d1 did not answer. "UNVERIFIED" is not used
            by any check of this file.
        caught_deliberate_failure: True only if the same check rejected the
            deliberate failure control.
    """

    id: str
    requirement: str
    passing_outcome: str
    check: str
    evidence: str
    result: str
    caught_deliberate_failure: bool


# ---- Helpers ------------------------------------------------------------------------


def real_model() -> scriptt16.Model:
    """Returns the real d1 of .scriptt/config.json."""
    return lambda state, questions: shipped.put(shipped.d1, state, questions)


def unreachable(model: scriptt16.Model) -> str | None:
    """Returns why the model does not answer one question, or None if it answers."""
    try:
        model("Hello.", {"q": {"type": "boolean", "instructions": "Is this a greeting?"}})
    except OSError as error:
        return f"{type(error).__name__}: {error}"
    return None


def world_of(source: str, folder: pathlib.Path) -> agree.World:
    """Loads a world from the text of a world.py file, with the folder that its paths name."""
    module = types.ModuleType("world")
    module.__file__ = str(folder / "world.py")
    exec(compile(source, "world.py", "exec"), vars(module))
    return agree.load(module, folder)


def folder_world() -> agree.World:
    """Loads next/world.py, the world of this folder, with the folder of the repository for its paths."""
    return world_of((HERE / "world.py").read_text(), HERE.parent)


def without_functions(source: str, kept: set[str]) -> str:
    """Returns a world.py text with every function not named in ``kept`` taken out."""
    lines = source.splitlines(keepends=True)
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef) and node.name not in kept:
            source = source.replace("".join(lines[node.lineno - 1:node.end_lineno]), "")
    return source


@contextlib.contextmanager
def put_back(module: types.ModuleType, name: str, old: object) -> typing.Iterator[None]:
    """Puts an old definition in place of one name of a module for the length of a run, and restores it after."""
    current = getattr(module, name)
    setattr(module, name, old)
    try:
        yield
    finally:
        setattr(module, name, current)


OLD_JOIN = "Is the second text part of the same request as the first text?"
"""The join wording before 2026-11-10. With the real d1 it joined "Redesign the mod." and "Then show me
the mod, redesigned." (0.84), so the product path lost an obligation that a reading with join off kept."""


def product_reading(text: str, world: agree.World, model: scriptt16.Model, limits: Limits,
                    prompts: scriptt16.Prompts = scriptt16.Prompts()) -> Reading:
    """Reads a message on the product path: ``turns.start_turn``, as the hook and the notebook read it (join on)."""
    return turns.start_turn(text, world, [], model, prompts=prompts, limits=limits).reading


def phrase_holding(reading: Reading, words: str) -> scriptt16.Phrase | None:
    """Returns the innermost phrase of a reading whose span holds the given words of the message, or None."""
    start = reading.text.find(words)
    if start < 0:
        return None
    return next((phrase for phrase in scriptt16.innermost(reading.message) if phrase.start <= start and start + len(words) <= phrase.end), None)


def choice_of(phrase: scriptt16.Phrase | None) -> str:
    """Returns the choice of d1 for a phrase with its share, such as "redesign 0.71"."""
    if phrase is None or phrase.choice is None:
        return "no choice"
    return f"{phrase.choice.best} {phrase.choice.shares.get(phrase.choice.best, 0.0):.2f}"


def decisions_of(reading: Reading, template: str) -> list[str]:
    """Returns each decision of d1 of one wording in a reading, as the option that won and its share.

    For a ``many_is`` decision: the words in quote marks of the question, and the share of yes.
    """
    found: list[str] = []
    for request in reading.requests:
        for decision in request["decisions"]:
            if decision["template"] != template:
                continue
            if decision["p_true"] is not None:
                parts = decision["instructions"].split('"')
                found.append(f"{parts[1] if len(parts) > 2 else decision['key']!r} yes {decision['p_true']:.3f}")
            else:
                shares = decision["probabilities"] or {}
                labels = {option["id"]: option["description"] for option in decision["options"]}
                best = max(shares, key=shares.get)
                found.append(f"{labels.get(best, best)} {shares[best]:.2f}")
    return found


def is_named(term: scriptt16.Term | None, words: str) -> bool:
    """Decides whether a term is the constant of the member of a sum type with these words."""
    return isinstance(term, Constant) and isinstance(term.value, Member) and term.value.words == words


def attempt(run: typing.Callable[[], object]) -> object:
    """Runs a step and returns its value, or the refusal of the engine as "error: ..." text.

    An ``OSError`` (d1 did not answer) is not caught: the row is BLOCKED.
    """
    try:
        return run()
    except (ValueError, TypeError, KeyError) as error:
        return f"error: {type(error).__name__}: {error}"


@dataclasses.dataclass(frozen=True)
class Controls:
    """Several broken runs of one criterion, each with one old rule put back. The control is caught only if the check rejects each run.

    Attributes:
        runs: The outcome of each broken run, by what was put back.
    """

    runs: dict[str, object]


def judged(identifier: str, requirement: str, passing_outcome: str, check: str,
           decide: typing.Callable[[object], Decided], positive: typing.Callable[[], object], control: typing.Callable[[], object]) -> Criterion:
    """Applies one check function to the positive case and to the control.

    Args:
        identifier: C1 to C7.
        requirement: The requirement.
        passing_outcome: What must observably be true.
        check: What the check decides.
        decide: The check function.
        positive: Produces the positive case, end to end.
        control: Produces the deliberate failure control: one outcome, or ``Controls``.

    Returns:
        The criterion: PASS if ``decide`` holds on the positive case, and
        ``caught_deliberate_failure`` True if ``decide`` rejects the control
        (every run of ``Controls``). BLOCKED if d1 did not answer.
    """
    try:
        holds, seen = decide(positive())
        broken = control()
        if isinstance(broken, Controls):
            decided = {label: decide(outcome) for label, outcome in broken.runs.items()}
            control_holds = any(one for one, _ in decided.values())
            control_seen = " ".join(f"[{label}] {words}" for label, (_, words) in decided.items())
        else:
            control_holds, control_seen = decide(broken)
    except OSError as error:
        return Criterion(identifier, requirement, passing_outcome, check, f"d1 did not answer: {type(error).__name__}: {error}", BLOCKED, False)
    evidence = f"POSITIVE: {seen} || CONTROL: {control_seen}"
    return Criterion(identifier, requirement, passing_outcome, check, evidence, PASS if holds else FAIL, not control_holds)


# ---- C1: all obligations represented --------------------------------------------------

C1_MESSAGE = "Redesign the mod. Then show me the mod, redesigned. Test the search too."
C1_CLAUSES = (("Redesign the mod.", "redesign"), ("Then show me the mod, redesigned.", "show"), ("Test the search too.", "test"))
"""The checklist of C1, written by hand: each clause of the message and the function it asks for."""


def obligations_held(reading: Reading, clauses: tuple[tuple[str, str], ...] = C1_CLAUSES) -> Decided:
    """The check of C1: each clause of the checklist is held by a phrase whose term applies its function.

    The number of ``Application`` terms in the reading must be the number of clauses, so a clause
    that is joined into another phrase, dropped, or read as nothing or none fails the check.
    """
    holds, seen = True, []
    for words, function in clauses:
        phrase = phrase_holding(reading, words)
        term = phrase.term if phrase else None
        got = term.function.name if isinstance(term, Application) else (phrase.choice.best if phrase and phrase.choice else "no term")
        holds &= got == function
        seen.append(f"{words!r} -> {scriptt16.say(term, reading.text) if term else got} ({choice_of(phrase)})")
    applications = sum(isinstance(phrase.term, Application) for phrase in scriptt16.innermost(reading.message))
    holds &= applications == len(clauses)
    return holds, "; ".join(seen) + f"; {applications} Application terms for {len(clauses)} clauses"


def marked_nothing(reading: Reading, words: str) -> Reading:
    """Returns a reading with the phrase that holds the words marked as asking for nothing: the C1 control."""
    phrase = phrase_holding(reading, words)
    marked = dataclasses.replace(phrase, choice=Choice(phrase.choice.shares if phrase.choice else {}, "nothing"), term=None)
    return turns.with_phrase(reading, marked)


def criterion_obligations(model: scriptt16.Model, limits: Limits) -> Criterion:
    """C1: the real reading of the three-clause message, and the control with "Test the search too." marked as nothing."""
    world = folder_world()
    read: list[Reading] = []
    positive = lambda: read[0] if read else read.append(product_reading(C1_MESSAGE, world, model, limits)) or read[0]
    control = lambda: Controls({"\"Test the search too.\" marked nothing": marked_nothing(positive(), "Test the search too."),
                                "the old join wording": product_reading(C1_MESSAGE, world, model, limits, scriptt16.Prompts(join=OLD_JOIN))})
    return judged(
        "C1",
        f'All obligations represented (spec Part 4.2, C1): "{C1_MESSAGE}"',
        "3 Application terms (redesign, show, test), one for each clause, with 0 dropped clauses.",
        "obligations_held: for each clause of a hand-written checklist, the phrase that holds its words has an Application of the "
        "named function, and the reading has exactly 3 Application terms. The message is read on the product path "
        "(turns.start_turn, join on), so a clause joined into the phrase before it fails. Controls, each rejected: the same reading "
        "with \"Test the search too.\" marked nothing, and the message read on the product path with the old join wording.",
        obligations_held,
        positive,
        control,
    )


# ---- C2: entity and version identity -------------------------------------------------

C2_ORIGINAL = ("Redesign the mod. Then show the original mod.", "Then show the original mod.")
C2_VERSION = ("Redesign the mod. Then show me the mod, redesigned.", "Then show me the mod, redesigned.")


def versions_bound(readings: tuple[Reading, Reading]) -> Decided:
    """The check of C2: "the original mod" binds show.subject to the constant 'the mod', and "the mod,
    redesigned" binds it to the application of redesign to 'the mod'."""
    original, version = readings
    first, second = phrase_holding(original, C2_ORIGINAL[1]), phrase_holding(version, C2_VERSION[1])
    shown = lambda phrase: phrase.term.arguments.get("subject") if phrase and isinstance(phrase.term, Application) and phrase.term.function.name == "show" else None
    to_original, to_version = shown(first), shown(second)
    is_version = isinstance(to_version, Application) and to_version.function.name == "redesign" and is_named(to_version.arguments.get("surface"), "the mod")
    holds = is_named(to_original, "the mod") and is_version
    seen = (f"{C2_ORIGINAL[1]!r} -> {scriptt16.say(first.term, original.text) if first and first.term else choice_of(first)} (which: {decisions_of(original, 'which')}); "
            f"{C2_VERSION[1]!r} -> {scriptt16.say(second.term, version.text) if second and second.term else choice_of(second)} (which: {decisions_of(version, 'which')})")
    return holds, seen


def taken_by(current: typing.Callable) -> typing.Callable:
    """Returns ``derivations`` with the old ``taken_by`` rule: a constant that an earlier application took is left out."""
    def derivations(goal: Type, environment: scriptt16.Environment, world: agree.World, depth: int, applying: agree.Function | None = None) -> list:
        found = current(goal, environment, world, depth, applying)
        versions = [term for term in found if isinstance(term, Application)]
        taken = lambda constant: any(isinstance(argument, Constant) and (argument.type, argument.value) == (constant.type, constant.value)
                                     for version in versions for argument in version.arguments.values())
        return [term for term in found if not (isinstance(term, Constant) and taken(term))]
    return derivations


def criterion_versions(model: scriptt16.Model, limits: Limits) -> Criterion:
    """C2: both messages read end to end; the control reads them with the old taken_by rule."""
    world = folder_world()
    both = lambda prompts=scriptt16.Prompts(): tuple(product_reading(text, world, model, limits, prompts) for text, _ in (C2_ORIGINAL, C2_VERSION))

    def control() -> Controls:
        with put_back(scriptt16, "derivations", taken_by(scriptt16.derivations)):
            taken = both()
        return Controls({"old taken_by rule": taken, "the old join wording": both(scriptt16.Prompts(join=OLD_JOIN))})
    return judged(
        "C2",
        f'Entity vs. version identity (spec Part 4.2, C2): "{C2_ORIGINAL[0]}" and "{C2_VERSION[0]}"',
        "show.subject is Constant(Surface, MOD) for \"the original mod\", and Application(redesign, surface='the mod') for \"the mod, redesigned\".",
        "versions_bound: the show term of each second phrase has the expected subject, by its structure. Both messages are read on "
        "the product path (turns.start_turn, join on), so the second sentence must stay its own phrase. Controls, each rejected: both "
        "messages read with the old taken_by rule of derivations put back, and both read with the old join wording.",
        versions_bound, both, control,
    )


# ---- C3: negation in Many[T] -------------------------------------------------------------

C3_MESSAGE = "Compare the mod, not the page."
C3_INCLUDED = ("the mod",)
"""The checklist of C3: the only surfaces that compare must take."""


def negation_kept(reading: Reading, included: tuple[str, ...] = C3_INCLUDED) -> Decided:
    """The check of C3: the phrase is compare, and its Many argument holds exactly the included surfaces."""
    phrase = scriptt16.innermost(reading.message)[0]
    term = phrase.term
    surfaces = term.arguments.get("surfaces") if isinstance(term, Application) and term.function.name == "compare" else None
    holds = isinstance(surfaces, Several) and len(surfaces.terms) == len(included) and all(is_named(one, words) for one, words in zip(surfaces.terms, included))
    reads = scriptt16.say(term, reading.text) if term else choice_of(phrase)
    return holds, f"{reads} ({choice_of(phrase)}); many_is: {decisions_of(reading, 'many_is') or 'not asked'}"


def greedy(current: typing.Callable) -> typing.Callable:
    """Returns ``solve`` with the old greedy rule for ``Many[T]``: every term of the phrase that fits is taken, and d1 is not asked."""
    def solve(goal: Type, environment: scriptt16.Environment, search: scriptt16.Search, state: str, role: str, applying: agree.Function, depth: int) -> scriptt16.Term:
        if isinstance(goal, Applied) and goal.constructor == MANY:
            given = [term for term in environment.local if scriptt16.fills(term, goal.argument)]
            if given:
                return Several(goal.argument, tuple(given))
        return current(goal, environment, search, state, role, applying, depth)
    return solve


def criterion_negation(model: scriptt16.Model, limits: Limits) -> Criterion:
    """C3: the message read end to end; the control reads it with the old greedy Many."""
    world = folder_world()
    reading = lambda: product_reading(C3_MESSAGE, world, model, limits)

    def control() -> Reading:
        with put_back(scriptt16, "solve", greedy(scriptt16.solve)):
            return reading()
    return judged(
        "C3",
        f'Negation in Many[T] (spec Part 4.2, C3): "{C3_MESSAGE}"',
        "compare(surfaces=['the mod']): the page is mentioned and not included.",
        "negation_kept: the term is compare and its surfaces are exactly ['the mod'], by structure; read on the product path "
        "(turns.start_turn, join on). Control: the message read with the old greedy Many rule of solve put back.",
        negation_kept, reading, control,
    )


# ---- C4: intermediate and opaque composition -----------------------------------------------

CELL_WORLD = '''
import pathlib, typing

Words = typing.NewType("Words", str)
Asked = typing.NewType("Asked", Words)
Written = typing.NewType("Written", Words)
Observed = typing.NewType("Observed", Words)

class Cell(typing.NamedTuple):
    "a cell of a notebook"
    notebook: pathlib.Path
    number: int

def open_cell(cell: Cell) -> Observed:
    "open a cell of a notebook and read what it shows"

def summarize(observation: Observed) -> Written:
    "summarize what something shows"
'''
"""A world in which a Cell is never a span: open_cell can only be offered as an intermediate argument built from its fields."""

TOKEN_WORLD = '''
import typing

Words = typing.NewType("Words", str)
Asked = typing.NewType("Asked", Words)
Written = typing.NewType("Written", Words)
Observed = typing.NewType("Observed", Words)
Token = typing.NewType("Token", str)

def login() -> Token:
    "log in and get a token"

def fetch(token: Token) -> Observed:
    "fetch the data"
'''
"""A world with an opaque Token that no span can name: only login gives one."""

C4_CELL = "Summarize what cell 3 of notes.md shows."
C4_TOKEN = "Fetch the data."


def composed(outcomes: tuple[object, object]) -> Decided:
    """The check of C4: summarize(observation=open_cell(cell=Cell(notebook='notes.md', number=3))) and fetch(token=login()).

    Each outcome is a reading, or the refusal of the engine as text.
    """
    cell_reading, token_reading = outcomes
    seen: list[str] = []
    cell_holds = token_holds = False
    if isinstance(cell_reading, Reading):
        term = scriptt16.innermost(cell_reading.message)[0].term
        inner = term.arguments.get("observation") if isinstance(term, Application) and term.function.name == "summarize" else None
        record = inner.arguments.get("cell") if isinstance(inner, Application) and inner.function.name == "open_cell" else None
        fields = record.fields if isinstance(record, Record) and record.product.name == "Cell" else {}
        notebook, number = fields.get("notebook"), fields.get("number")
        cell_holds = (isinstance(notebook, Constant) and notebook.value == pathlib.Path("notes.md") and isinstance(number, Constant) and number.value == 3)
        seen.append(f"{C4_CELL!r} at depth {cell_reading.limits.depth} -> {scriptt16.say(term, cell_reading.text) if term else choice_of(scriptt16.innermost(cell_reading.message)[0])}")
    else:
        seen.append(f"{C4_CELL!r} -> {cell_reading}")
    if isinstance(token_reading, Reading):
        term = scriptt16.innermost(token_reading.message)[0].term
        token = term.arguments.get("token") if isinstance(term, Application) and term.function.name == "fetch" else None
        token_holds = isinstance(token, Application) and token.function.name == "login" and token.arguments == {}
        seen.append(f"{C4_TOKEN!r} -> {scriptt16.say(term, token_reading.text) if term else choice_of(scriptt16.innermost(token_reading.message)[0])} (the Token world loads with no fault)")
    else:
        seen.append(f"{C4_TOKEN!r} -> {token_reading}")
    return cell_holds and token_holds, "; ".join(seen)


def depth_zero_producers(goal: Type, environment: scriptt16.Environment, world: agree.World, depth: int) -> bool:
    """The old rule for the parameter of a producer: a term at depth 0 must exist, so a record built from its fields never counts."""
    return bool(scriptt16.derivations(goal, environment, world, 0))


def span_only_ungrounded(world: agree.World) -> list[str]:
    """The old ``ungrounded``: a parameter is satisfiable only if a span of a message can have its type; producers do not count."""
    texts = (world.types.get("Asked"), world.types.get("Written"))

    def grounds(expression: Type) -> bool:
        match expression:
            case Applied(argument=argument):
                return grounds(argument)
            case Product(fields=fields):
                return all(grounds(field) for _, field in fields)
            case Sum(alternatives=alternatives):
                return any(isinstance(alternative, Member) or grounds(alternative) for alternative in alternatives)
            case Base(python=python):
                return python in (int, pathlib.Path) or any(text and is_subtype(text, expression) for text in texts)
        return any(text and is_subtype(text, expression) for text in texts)
    return [f"{function.name}.{name}: no span of a message can have the type {show(parameter)}"
            for function in world.functions.values() for name, parameter in function.parameters if not grounds(parameter)]


def criterion_composition(model: scriptt16.Model, limits: Limits) -> Criterion:
    """C4: both worlds read end to end at depth 2; the control with the old producer rule and the old ungrounded."""
    deep = dataclasses.replace(limits, depth=2)

    def both() -> tuple[object, object]:
        with tempfile.TemporaryDirectory() as name:
            folder = pathlib.Path(name)
            (folder / "notes.md").write_text("# notes\n")
            cell = attempt(lambda: product_reading(C4_CELL, world_of(CELL_WORLD, folder), model, deep))
            token = attempt(lambda: product_reading(C4_TOKEN, world_of(TOKEN_WORLD, folder), model, deep))
            return cell, token

    def control() -> Controls:
        with put_back(scriptt16, "can_synthesize", depth_zero_producers):
            producers = both()
        with put_back(scriptt16, "ungrounded", span_only_ungrounded):
            spans = both()
        return Controls({"old producer rule, depth 0": producers, "old ungrounded, spans only": spans})
    return judged(
        "C4",
        "Intermediate and opaque composition (spec Part 4.2, C4): open_cell(Cell(notebook='notes.md', number=3)) as an intermediate argument "
        "at depth=2; a world with login() -> Token and fetch(token: Token) loads and synthesizes fetch(token=login())",
        f"\"{C4_CELL}\" reads as summarize(observation=open_cell(cell=Cell(notebook='notes.md', number=3))) and \"{C4_TOKEN}\" as fetch(token=login()).",
        "composed: both terms, by structure (the number is the int 3); read on the product path (turns.start_turn). Controls, each rejected: both read with the old producer rule (a "
        "parameter needs a term at depth 0) put back, and both read with the old ungrounded (spans only) put back.",
        composed, both, control,
    )


# ---- C5: inline correction round trip to the hook ----------------------------------------------

C5_TURNS = ("Redesign the mod.", "Show it.")
C5_CORRECTION = (1, "subject", "'the mod'")
"""The correction of C5: phrase 1 of turn 2, the place show.subject, set to the original mod."""
C5_DELIVERED = "1. show(subject='the mod')"
"""The start of the first line that the hook must send after the correction."""


def round_trip(outcome: dict) -> Decided:
    """The check of C5: the hook sends the corrected binding after a save and a reload, and undo restores the block before it.

    The block before the correction must not already have the binding, or a stale block could not be told apart.
    """
    first_line = lambda block: block.splitlines()[0] if isinstance(block, str) and block and not block.startswith("error:") else str(block)
    holds = (outcome["kind"] in ("parser_override", "candidate_injected") and not first_line(outcome["before"]).startswith(C5_DELIVERED)
             and first_line(outcome["delivered"]).startswith(C5_DELIVERED) and outcome["undone"] == outcome["before"])
    seen = (f"before: {first_line(outcome['before'])!r} (which: {outcome['which']}); correction {outcome['kind']} to {C5_CORRECTION[2]}; "
            f"hook after reload: {first_line(outcome['delivered'])!r}; undo then reload gives the block before: {outcome['undone'] == outcome['before']}"
            + (f" ({outcome['undone']})" if str(outcome["undone"]).startswith("error:") else "") + f"; log: {outcome['log']}")
    return holds, seen


def corrected_round_trip(model: scriptt16.Model, limits: Limits) -> dict:
    """Reads two turns, corrects turn 2, saves it to the log of a temporary folder, and reads back what the hook sends.

    The folder is a temporary copy: next/world.py as its .scriptt/world.py, and its own
    .scriptt/events.jsonl. The log of the repository is never written.
    """
    repository_log = HERE.parent / ".scriptt" / "events.jsonl"
    size = repository_log.stat().st_size if repository_log.exists() else None
    with tempfile.TemporaryDirectory() as name:
        folder = pathlib.Path(name)
        (folder / ".scriptt").mkdir()
        shutil.copy(HERE / "world.py", folder / ".scriptt" / "world.py")
        world = turns.world_of_folder(folder)
        log = folder / ".scriptt" / "events.jsonl"
        first = turns.start_turn(C5_TURNS[0], world, [], model, limits=limits)
        trace = turns.start_turn(C5_TURNS[1], world, [], model, context_in=first.context_out, limits=limits)
        before = turns.block_of(trace)
        phrase, path, choice = C5_CORRECTION
        corrected = turns.correct(trace, phrase, path, choice)
        saved = turns.save(corrected)
        delivered = attempt(lambda: turns.hook_block(folder))

        def undone() -> str:
            restored = turns.undo(turns.load(log, world))
            turns.save(restored, log)
            return turns.hook_block(folder)
        after_undo = attempt(undone)
        lines = len(turns.trace_lines(log))
        untouched = (repository_log.stat().st_size if repository_log.exists() else None) == size
        where = (f"saved to <temporary folder>/.scriptt/events.jsonl ({saved == log}), {lines} trace lines; "
                 f"the repository's .scriptt/events.jsonl unchanged: {untouched}")
        return {"before": before, "kind": corrected.corrections[-1].kind, "delivered": delivered, "undone": after_undo, "log": where,
                "which": decisions_of(trace.reading, "which")}


def criterion_round_trip(model: scriptt16.Model, limits: Limits) -> Criterion:
    """C5: a correction saved and reloaded through the hook; the controls are a load that ignores corrections and a stale hook."""
    def control() -> Controls:
        with put_back(turns, "applied_correction", lambda trace, correction, world: trace):
            ignored = corrected_round_trip(model, limits)
        with put_back(turns, "block_of", lambda trace: scriptt16.block(trace.history[0] if trace.history else trace.reading)):
            stale = corrected_round_trip(model, limits)
        return Controls({"load that ignores corrections": ignored, "hook that reads the reading before them": stale})
    return judged(
        "C5",
        f"Inline correction round trip to the hook (spec Part 4.2, C5): turns {list(C5_TURNS)}, correction {C5_CORRECTION}",
        f"After the correction is saved to .scriptt/events.jsonl and reloaded, the hook block starts {C5_DELIVERED!r}; undo restores the block before.",
        "round_trip: the correction kind, the first line of hook_block after the reload, and undo after a reload. The log is the "
        ".scriptt/events.jsonl of a temporary folder (a copy with its own .scriptt/), never the repository's. Controls, each rejected: "
        "the same run with load ignoring the corrections, and with the hook reading the reading before them.",
        round_trip, lambda: corrected_round_trip(model, limits), control,
    )


# ---- C6: execution-backed completion check -----------------------------------------------------

C6_MESSAGE = "Build the world. Build the tests."
C6_CALLS = ("build(code='the world')", "build(code='the tests')")
"""The checklist of C6, written by hand: the two calls that the message asks for."""
C6_TURNS = (("I built the world.", ({"path": "next/world.py"},), ("DONE", "OPEN")), ("I built both.", (), ("UNVERIFIED", "UNVERIFIED")))
"""Each reply, its executions, and the state that each call of the checklist must get."""

type Outcome = tuple[str, str, float]
"""One checked item: the call, the name of its state, and the share of d1."""


def completion_states(outcome: tuple[list[str], list[list[Outcome]]]) -> Decided:
    """The check of C6: the reading has the two calls of the checklist, and each reply gives each call its required state."""
    calls, checked = outcome
    holds = tuple(calls) == C6_CALLS
    seen = [f"reads as {calls}"]
    for (reply, executions, wanted), items in zip(C6_TURNS, checked):
        states = {call: state for call, state, _ in items}
        got = tuple(states.get(call, "missing") for call in C6_CALLS)
        holds &= got == wanted and len(items) == len(C6_CALLS)
        seen.append(f"{reply!r} with {len(executions)} executions -> " + ", ".join(f"{call} {state} {share:.3f}" for call, state, share in items))
    return holds, "; ".join(seen)


def reply_only_check(reading: Reading, reply: str, model: scriptt16.Model, executions: typing.Sequence = (), prompts: scriptt16.Prompts | None = None,
                     limits: Limits = Limits()) -> list[Outcome]:
    """The old check: one wording for every call of a function, the reply alone, and PROMISED for an undone Later term."""
    questions: dict[str, scriptt16.YesNo] = {}
    subjects: dict[str, scriptt16.Phrase] = {}
    for phrase in scriptt16.innermost(reading.message):
        if not isinstance(phrase.term, Application):
            continue
        items = [scriptt16.say(one, reading.text) for argument in phrase.term.arguments.values() if isinstance(argument, Several) for one in argument.terms]
        for item in items or [None]:
            key = f"{phrase.start} {item}"
            questions[key] = scriptt16.YesNo(scriptt16.rendered(shipped.DID(phrase.term.function.asks + (f": {item}" if item else ""))))
            subjects[key] = phrase
    if not questions:
        return []
    shares = scriptt16.ask_all(model, f"MESSAGE:\n{reading.text}\n\nREPLY:\n{reply}", questions)
    found: list[Outcome] = []
    for key, phrase in subjects.items():
        result = scriptt16.type_of(phrase.term)
        unfinished = "PROMISED" if isinstance(result, Applied) and result.constructor == agree.LATER else "OPEN"
        found.append((scriptt16.say(phrase.term, reading.text), "DONE" if shares[key] >= limits.yes else unfinished, round(shares[key], 3)))
    return found


def outcomes_of(checked: list) -> list[Outcome]:
    """Returns checked items as outcomes: a ``scriptt16.Checked`` by its call and state, an outcome as it is."""
    return [(one.call, one.state.name, one.share) if isinstance(one, scriptt16.Checked) else one for one in checked]


def criterion_completion(model: scriptt16.Model, limits: Limits) -> Criterion:
    """C6: the message read end to end and checked against two replies; the control checks with the old reply-only check."""
    world = folder_world()
    reading = product_reading(C6_MESSAGE, world, model, limits)

    def run() -> tuple[list[str], list[list[Outcome]]]:
        return scriptt16.reads_as(reading), [outcomes_of(scriptt16.check(reading, reply, model, executions, limits=limits)) for reply, executions, _ in C6_TURNS]

    def control() -> tuple[list[str], list[list[Outcome]]]:
        with put_back(scriptt16, "check", reply_only_check):
            return run()
    return judged(
        "C6",
        f'Execution-backed completion check (spec Part 4.2, C6): "{C6_MESSAGE}"',
        "\"I built the world.\" with executions=[{'path': 'next/world.py'}]: build('the world') DONE and build('the tests') OPEN; "
        "\"I built both.\" with executions=[]: both UNVERIFIED.",
        "completion_states: the reading (product path, turns.start_turn, join on) has the two hand-written calls, and each reply gives "
        "each call its required state. "
        "Control: the same reading checked with the old reply-only check put back.",
        completion_states, run, control,
    )


# ---- C7: capability-preserving world gate -----------------------------------------------------

C7_KEPT = {"follow"}
"""The proposed world.py keeps only follow: redesign and every other function are deleted."""
C7_LOST = "'Redesign the mod.' phrase 1: approved redesign(surface='the mod')"
"""The obligation that the gate must report as lost."""
C7_LOGGED = ("Redesign the mod.", "Nice work today.", "Thanks, that looks good.", "Nice.", "OK, thanks!", "Good morning.", "That works for me.",
             "Follow this rule from now on: no regex.", "Follow this rule: never push without asking.")
"""The messages of the log that the gates replay."""


def capability_kept(outcome: tuple[scriptt16.Gate, str]) -> Decided:
    """The check of C7: the gate rejects the proposed world and names the lost redesign obligation."""
    decision, remark = outcome
    holds = not decision.accepted and any(lost.startswith(C7_LOST) for lost in decision.lost)
    bits = "None" if decision.mean_bits is None else f"{decision.mean_bits:.3f}"
    return holds, (f"accepted={decision.accepted}, lost={decision.lost[:2]}{' ...' if len(decision.lost) > 2 else ''} ({len(decision.lost)} lost), "
                   f"mean_bits={bits}, decision_count={decision.decision_count}, unresolved_holes={decision.unresolved_holes}, "
                   f"preserved_obligations={decision.preserved_obligations}, world_hash={decision.world_hash}; {remark}")


def bits_only_gate(proposed: agree.World, golden_cases: list, logged_lines: list[dict], model: scriptt16.Model,
                   prompts: scriptt16.Prompts = scriptt16.Prompts(), limits: Limits = Limits()) -> scriptt16.Gate:
    """The old gate: it accepts a world if the average bits per decision on the log do not go up. It reads no approved case."""
    average = lambda found: sum(found) / len(found) if found else 0.0
    current_bits = average([one for line in logged_lines for one in scriptt16.recorded_bits(line)])
    hashes = (scriptt16.world_hash(proposed), scriptt16.prompts_hash(prompts))
    faults = proposed.faults + scriptt16.ungrounded(proposed)
    if faults:
        return scriptt16.Gate(False, faults, [], None, 0, 0, 0, *hashes)
    replayed: list[float] = []
    for line in logged_lines:
        reading = scriptt16.read(line["text"], proposed, [], model, False, limits, scriptt16.recorded_phrases(line, proposed), prompts)
        replayed += scriptt16.recorded_bits(scriptt16.record(reading))
    return scriptt16.Gate(average(replayed) <= current_bits, [], [], average(replayed), len(replayed), 0, 0, *hashes)


def criterion_gate(model: scriptt16.Model, limits: Limits) -> Criterion:
    """C7: the proposed world with only follow, gated on golden.json; the control gates it with the old bits-only gate."""
    world = folder_world()
    proposed = world_of(without_functions((HERE / "world.py").read_text(), C7_KEPT), HERE.parent)
    golden = scriptt16.golden(HERE / "golden.json")
    lines = [scriptt16.record(product_reading(text, world, model, limits)) for text in C7_LOGGED]
    current = sum(one for line in lines for one in scriptt16.recorded_bits(line)) / max(1, sum(len(scriptt16.recorded_bits(line)) for line in lines))
    lobotomized = product_reading("Redesign the mod.", proposed, model, limits)
    remark = (f"with only follow, \"Redesign the mod.\" reads as {choice_of(scriptt16.innermost(lobotomized.message)[0])}; "
              f"the log's mean bits with the current world {current:.3f}")
    run = lambda: (scriptt16.gate(proposed, golden, lines, model, limits=limits), remark)

    def control() -> tuple[scriptt16.Gate, str]:
        with put_back(scriptt16, "gate", bits_only_gate):
            return run()
    return judged(
        "C7",
        "Capability-preserving world gate (spec Part 4.2, C7): a proposed world.py that deletes redesign (only follow kept)",
        f"gate() against next/golden.json rejects it and reports {C7_LOST!r} as lost, whatever d1's confidence.",
        f"capability_kept: Gate.accepted is False and Gate.lost names the redesign obligation; {len(golden)} golden cases, each read as "
        f"the product reads it (join on), "
        f"{len(C7_LOGGED)} logged lines. Control: the same proposal gated with the old bits-only gate put back.",
        capability_kept, run, control,
    )


# ---- The runner ---------------------------------------------------------------------------------

CRITERIA = (criterion_obligations, criterion_versions, criterion_negation, criterion_composition, criterion_round_trip, criterion_completion, criterion_gate)
"""The function of each criterion, C1 to C7, in order."""


def run_acceptance(model: scriptt16.Model | None = None, limits: Limits | None = None) -> list[Criterion]:
    """Runs the seven criteria.

    Args:
        model: The decision model. None means the real d1 of .scriptt/config.json.
        limits: The numbers that the search uses. None means ``Limits()``.

    Returns:
        One criterion for each of C1 to C7. If the model does not answer, every
        row is BLOCKED. A row whose run raises an ``OSError`` is BLOCKED.
    """
    model = model or real_model()
    limits = limits or Limits()
    down = unreachable(model)
    found: list[Criterion] = []
    for run in CRITERIA:
        identifier = f"C{len(found) + 1}"
        if down:
            found.append(Criterion(identifier, run.__doc__.split(":")[0], "", "", f"d1 did not answer: {down}", BLOCKED, False))
            continue
        try:
            found.append(run(model, limits))
        except OSError as error:
            found.append(Criterion(identifier, run.__doc__.split(":")[0], "", "", f"d1 did not answer: {type(error).__name__}: {error}", BLOCKED, False))
        except Exception as error:  # a run that breaks is a failed row, with the error as its evidence
            found.append(Criterion(identifier, run.__doc__.split(":")[0], "", "", f"the run raised {type(error).__name__}: {error}", FAIL, False))
    return found


def table(criteria: list[Criterion]) -> str:
    """Returns the acceptance table: one row for each criterion, with its result, its control and its evidence."""
    rows = ["| ID | Result | Caught deliberate failure | Requirement | Evidence |", "|---|---|---|---|---|"]
    for one in criteria:
        cell = lambda words: words.replace("|", "/").replace("\n", " ")
        rows.append(f"| {one.id} | {one.result} | {one.caught_deliberate_failure} | {cell(one.requirement)} | {cell(one.evidence)} |")
    return "\n".join(rows)


def accepted(criteria: list[Criterion]) -> bool:
    """Decides whether every row passed and caught its deliberate failure."""
    return len(criteria) == len(CRITERIA) and all(one.result == PASS and one.caught_deliberate_failure for one in criteria)


if __name__ == "__main__":
    found = run_acceptance()
    print(table(found))
    sys.exit(0 if accepted(found) else 1)
