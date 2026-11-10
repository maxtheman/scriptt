"""Tests of agree.py and scriptt16.py with a stand-in d1.

Each test sets the answers of d1, so the tests check the type system and the
rules of the search. They do not measure the real d1.

    python3.14 next/test_scriptt16.py
"""

import ast
import dataclasses
import inspect
import json
import pathlib
import sys
import tempfile
import types

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / ".scriptt")]
import acceptance
import agree
import harness as shipped
import scriptt16
import turns

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
    module = types.ModuleType("test_world")
    module.__file__ = str(folder / "world.py")
    exec(compile(source, "world.py", "exec"), vars(module))
    return agree.load(module, folder)


def standin(what: dict[str, str], which: dict[str, str] | None = None, yes: tuple[str, ...] = ()) -> scriptt16.Model:
    """Returns a d1 whose answers the test sets.

    Args:
        what: The function that a phrase asks for, by the first words of the phrase.
        which: Words of the option to choose for a hole, by the first words of the phrase.
        yes: A yes-or-no question gets a yes if its text or its state contains one of these.

    Returns:
        A model. It chooses "nothing" for a phrase with no entry in ``what``, and
        "none" for a hole with no entry in ``which``.
    """
    def model(state: str, asked: dict[str, dict]) -> dict[str, dict]:
        answers = {}
        for key, question in asked.items():
            if question["type"] == "boolean":
                answers[key] = {"p_true": 0.9 if any(words in question["instructions"] or words in state for words in yes) else 0.1}
                continue
            table = what if key == "what" else (which or {})
            phrase = state.splitlines()[-1] if key != "what" else state  # a hole question can carry earlier phrases before the phrase
            wanted = next((choice for start, choice in table.items() if phrase.startswith(start)), None)
            default = "nothing" if key == "what" else "none"
            pick = next((option["id"] for option in question["options"] if wanted and (option["id"] == wanted or wanted in option["description"])), default)
            identifiers = [option["id"] for option in question["options"]]
            answers[key] = {"probabilities": {identifier: 0.9 if identifier == pick else 0.1 / (len(identifiers) - 1) for identifier in identifiers}}
        return answers
    return model


def terms_of(reading: scriptt16.Reading) -> list[str | None]:
    """Returns the term of each phrase as text, or the choice of d1 for a phrase with no term."""
    return [scriptt16.say(phrase.term, reading.text) if phrase.term else phrase.choice.best if phrase.choice else None for phrase in scriptt16.innermost(reading.message)]


def test_kinds():
    world = world_of(WORLD)
    surface = world.types["Surface"]
    assert agree.kind_of(surface) == agree.Star() and agree.kind_of(agree.MANY) == agree.Arrow(agree.Star(), agree.Star())
    assert agree.kind_of(agree.Applied(agree.MANY, surface)) == agree.Star()
    faulty = world_of('import enum, typing\nAsked = typing.NewType("Asked", str)\nclass Surface(enum.Enum):\n    "x"\n    PAGE: Asked = "the page"\n\ndef one(surface: Many[Maybe]) -> Surface:\n    "x"\n\ndef two(surface: Surface[int]) -> Surface:\n    "x"\n\ndef three(surface: Surface) -> Later:\n    "x"\n')
    assert faulty.functions == {}
    assert ["Maybe has kind * -> *" in faulty.faults[0], "Surface has kind * and takes no argument" in faulty.faults[1], "Later has kind * -> * and needs an argument" in faulty.faults[2]] == [True] * 3, faulty.faults
    # Each side of a union must have kind *. Many | int is a fault with its line, in a parameter and in a type alias,
    # and the search refuses the world. Many[Surface] | int is a valid union.
    source = WORLD + '\ntype Odd = int | Later\n\ndef paint(surface: Many | int) -> Written:\n    "paint it"\n\ndef count(surfaces: Many[Surface] | int) -> Written:\n    "count them"\n'
    unions = world_of(source)
    line = source.splitlines().index("def paint(surface: Many | int) -> Written:") + 1
    assert "paint" not in unions.functions and "Odd" not in unions.types and "count" in unions.functions, unions.faults
    assert any(fault.startswith(f"world.py:{line} paint:") and "Many has kind * -> *" in fault for fault in unions.faults), unions.faults
    assert any("Odd" in fault and "Later has kind * -> *" in fault for fault in unions.faults), unions.faults
    try:
        scriptt16.read("Paint the mod.", unions, [], standin({"Paint": "paint"}), join=False)
        raise AssertionError("read() ran on a world with an ill-kinded union")
    except ValueError as error:
        assert "Many has kind * -> *" in str(error), error


def test_types():
    world = world_of(WORLD)
    assert world.faults == [], world.faults
    kinds_of_type = {name: type(one).__name__ for name, one in world.types.items()}
    assert kinds_of_type["Asked"] == "Brand" and kinds_of_type["Surface"] == "Sum" and kinds_of_type["Subject"] == "Sum" and kinds_of_type["Cell"] == "Product" and kinds_of_type["Review"] == "Product"
    asked, written, words, surface, subject = (world.types[name] for name in ("Asked", "Written", "Words", "Surface", "Subject"))
    assert agree.is_subtype(asked, words) and agree.is_subtype(written, words)  # a brand is a subtype of what it wraps
    assert not agree.is_subtype(written, asked) and not agree.is_subtype(words, asked)  # two brands over one type are different types
    assert agree.is_subtype(surface, subject) and not agree.is_subtype(asked, subject)  # a sum takes each of its alternatives
    assert agree.is_subtype(agree.Applied(agree.MANY, asked), agree.Applied(agree.MANY, words))
    assert {name: agree.show(one) for name, one in world.functions["review"].parameters} == {"review": "Review"}
    assert agree.tree(world.functions["redesign"].result) == {"constructor": "Later", "of": {"sum": "Surface", "alternatives": [{"member": "PAGE", "words": "the page"}, {"member": "MOD", "words": "the mod"}]}}
    untyped = world_of('import enum, typing\nAsked = typing.NewType("Asked", str)\nclass Surface(enum.Enum):\n    "x"\n    PAGE = "the page"\n    MOD: Asked = "the mod"\n\ndef show(surface) -> Surface:\n    pass\n')
    assert ["no type for the text 'the page'" in untyped.faults[0], "no type for surface" in untyped.faults[1], "no docstring" in untyped.faults[2]] == [True] * 3, untyped.faults


def test_world_rules():
    # A duplicate signature and a custom type with one user are warnings, not faults: the world loads whole.
    world = world_of(WORLD + '\nclass Colour(enum.Enum):\n    "a colour"\n    RED: Asked = "red"\n\ndef paint(surface: Surface) -> Later[Surface]:\n    "paint it"\n\ndef tint(colour: Colour) -> Written:\n    "tint it"\n')
    assert world.faults == [] and {"paint", "tint"} <= set(world.functions) and "Colour" in world.types, world.faults
    assert any("paint: the same parameter types and result type as redesign" in warning for warning in world.warnings), world.warnings
    assert any("Colour: 1 function uses this type (tint)" in warning for warning in world.warnings), world.warnings
    assert any(warning.endswith("Are these aliases, accidental duplication, or meaningfully different operations?") for warning in world.warnings), world.warnings
    assert any(warning.endswith("would Words, Path or int do?") for warning in world.warnings), world.warnings
    same = world_of(WORLD + '\nclass Pair(typing.NamedTuple):\n    "a pair"\n    notebook: pathlib.Path\n    number: int\n')
    assert same.faults == [] and any("Pair: the same structure as Cell" in warning for warning in same.warnings), (same.faults, same.warnings)
    assert world_of(WORLD).warnings == []

    # The search runs on such a world: two functions with one signature and different behaviour, and a type that one
    # function uses. d1 tells brighten from dim by their docstrings.
    world = world_of(WORLD + '\nclass Colour(enum.Enum):\n    "a colour"\n    RED: Asked = "red"\n\ndef tint(colour: Colour) -> Written:\n    "tint it"\n\ndef brighten(surface: Surface) -> Written:\n    "make it lighter"\n\ndef dim(surface: Surface) -> Written:\n    "make it darker"\n')
    assert world.faults == [] and len(world.warnings) == 2, (world.faults, world.warnings)
    model = standin({"Brighten": "brighten", "Dim": "dim", "Tint": "tint"}, {"Brighten": "'the mod'", "Dim": "'the mod'", "Tint": "red"})
    read = lambda text: terms_of(scriptt16.read(text, world, [], model, join=False))
    assert [read("Brighten the mod."), read("Dim the mod."), read("Tint the page red.")] == [["brighten(surface='the mod')"], ["dim(surface='the mod')"], ["tint(colour='red')"]]


def test_grounding():
    world = world_of(WORLD)
    text = 'Redesign the mod. "The row draws in the code font, and the jiggle is a slant." Is that still true? Then show it.\n\nThanks.'
    reply = "Not verified. The row draws in the code font, and the jiggle is a slant. Nothing else."
    message = scriptt16.phrases(text, [reply], world)
    inner = scriptt16.innermost(message)
    assert [phrase.brand.name for phrase in inner] == ["Asked", "Written", "Asked", "Asked", "Asked"]
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
    world = world_of(WORLD)
    read = lambda text, model, replies=(): scriptt16.read(text, world, list(replies), model, join=False)

    # One term fits the hole: the search takes it, and d1 gets no question about the hole.
    reading = read("Follow this rule.", standin({"Follow": "follow"}))
    assert terms_of(reading) == ["follow(rule='Follow this rule.')"] and len(reading.requests) == 1
    # Two terms fit the hole: the constant, and an application that gives a Surface. d1 chooses.
    reading = read("Show the mod.", standin({"Show": "show"}, {"Show": "'the mod'"}))
    offered = [option["description"] for option in reading.requests[1]["asked"]["which"]["options"]]
    assert terms_of(reading) == ["show(subject='the mod')"] and offered == ["'the mod' (as named in this phrase)", "redesign(surface=...) (a new call)", "the text names none of these"], offered
    # Function application inside one phrase: d1 chooses the application, and its parameter takes the constant.
    assert terms_of(read("Show me the mod, redesigned.", standin({"Show": "show"}, {"Show": "redesign(surface=...)"}))) == ["show(subject=redesign(surface='the mod'))"]

    # Function application across phrases. The earlier application and the mod itself are both offered, by name or by
    # "it", and d1 chooses between the original and the redesigned mod.
    for second in ("Then show the mod.", "Then show it."):
        reading = read("Redesign the mod. " + second, standin({"Redesign": "redesign", "Then": "show"}, {"Then": "redesign("}))
        assert terms_of(reading) == ["redesign(surface='the mod')", "show(subject=redesign(surface='the mod'))"] and len(reading.requests) == 3
        offered = sorted(option["description"] for option in reading.requests[2]["asked"]["which"]["options"])
        assert offered == ["the original 'the mod'", "the result of redesign(surface='the mod') in phrase 1", "the text names none of these"], offered
        assert reading.requests[2]["state"] == "Redesign the mod.\n" + second  # d1 reads the phrase that the result comes from
        assert agree.show(scriptt16.type_of(scriptt16.innermost(reading.message)[1].term)) == "Later[Subject]"  # a term with a Later argument is Later

    # Many: the phrase gives two terms of its type, and d1 accepts each of them.
    assert terms_of(read("Compare the page and the mod.", standin({"Compare": "compare"}, yes=('"the page"', '"the mod"')))) == ["compare(surfaces=['the page', 'the mod'])"]
    # Many: the phrase gives none, so d1 answers yes or no for each earlier term.
    assert terms_of(read("Look at the page and the mod. Compare them.", standin({"Compare": "compare"}, yes=("the page", "the mod")))) == ["nothing", "compare(surfaces=['the mod', 'the page'])"]

    # d1 chooses none: the hole stays open. d1 abstains on the function: the phrase has no term.
    reading = read("Show the mod and the page.", standin({"Show": "show"}))
    assert terms_of(reading) == ["show(subject=...)"] and scriptt16.holes_of(scriptt16.innermost(reading.message)[0].term)[0][0] == "subject"
    assert terms_of(read("Email my accountant.", standin({"Email": "none"}))) == ["none"]
    # Sum of members with no constant in the message: d1 chooses a member, or none.
    assert terms_of(read("Redesign what I look at in the app.", standin({"Redesign": "redesign"}, {"Redesign": "the mod"}))) == ["redesign(surface='the mod')"]
    assert terms_of(read("Redesign it.", standin({"Redesign": "redesign"}))) == ["redesign(surface=...)"]

    # Brand: a hole of type Asked takes the words of the user, and the subtype rule excludes a quote of a reply. The
    # quote is offered for adoption, and d1 says no word of the phrase means it, so it stays out (adoption: test_provenance).
    reply = "Until then I use only these ten words, each in its own exact sense."
    reading = read('"I use only these ten words, each in its own exact sense." Keep to that from now on.', standin({"Keep": "follow"}), [reply])
    assert terms_of(reading)[1] == "follow(rule='Keep to that from now on.')" and len(reading.requests) == 2
    assert all("In the last sentence, does [" in question["instructions"] for question in reading.requests[1]["asked"].values())
    # Maybe: a hole of type Maybe[Words] can take the quote, because Written is a subtype of Words.
    reading = read('"I use only these ten words, each in its own exact sense." What do you mean?', standin({"What": "explain"}, {"What": "ten words"}), [reply])
    assert "ten words" in terms_of(reading)[1]
    # Maybe: with no term, the hole is empty and the call leaves it out.
    assert terms_of(scriptt16.read("Explain.", world_of(WORLD.replace("Maybe[Words]", "Maybe[Surface]")), [], standin({"Explain": "explain"}), join=False)) == ["explain()"]

    with tempfile.TemporaryDirectory() as folder:
        (pathlib.Path(folder) / "notes.md").write_text("x")
        there = world_of(WORLD, pathlib.Path(folder))
        # Product: one term for each field.
        assert terms_of(scriptt16.read("Open cell 3 of notes.md.", there, [], standin({"Open": "open_cell"}), join=False)) == ["open_cell(cell=Cell(notebook='notes.md', number='3'))"]
        # Product inside a product: the rule applies at every depth.
        reading = scriptt16.read("Review cell 3 of notes.md.", there, [], standin({"Review": "review"}, yes=("Review cell",)), join=False)
        assert terms_of(reading) == ["review(review=Review(cell=Cell(notebook='notes.md', number='3'), evidence=['Review cell 3 of notes.md.']))"]
        # Sum of types: terms of two alternatives are at hand, so d1 chooses among the terms themselves.
        reading = scriptt16.read("Show notes.md, not the mod.", there, [], standin({"Show": "show"}, {"Show": "notes.md"}), join=False)
        offered = [option["description"] for option in reading.requests[1]["asked"]["which"]["options"]]
        assert terms_of(reading) == ["show(subject='notes.md')"] and offered[:2] == ["'notes.md' (as named in this phrase)", "'the mod' (as named in this phrase)"], offered
        # Sum of types, in the world of this folder: the phrase names a Code and an earlier phrase a Surface. The Code is offered as a term.
        reading = scriptt16.read("Redesign the mod. Test the search too.", world_of((HERE / "world.py").read_text()), [], standin({"Redesign": "redesign", "Test": "test"}, {"Test": "the search"}), join=False)
        assert terms_of(reading) == ["redesign(surface='the mod')", "test(subject='the search')"], terms_of(reading)
        # Sum of two products: d1 chooses the alternative, and the fields of that product become holes.
        either = world_of(WORLD + '\nclass File(typing.NamedTuple):\n    "a file"\n    path: pathlib.Path\n\ntype Target = File | Cell\n\ndef inspect_target(target: Target) -> Observed:\n    "inspect a file or a cell"\n\ndef open_file(file: File) -> Observed:\n    "open a file"\n', pathlib.Path(folder))
        reading = scriptt16.read("Inspect cell 3 of notes.md.", either, [], standin({"Inspect": "inspect_target"}, {"Inspect": "a cell of a notebook"}), join=False)
        assert terms_of(reading) == ["inspect_target(target=Cell(notebook='notes.md', number='3'))"], terms_of(reading)

    # A world with a fault, or with a parameter that no span can fill, is refused.
    for faulty in (WORLD + '\ndef paint(surface: Many | int) -> Later[Surface]:\n    "paint it"\n', WORLD + '\nVersion = typing.NewType("Version", str)\n\ndef release(version: Version) -> Later[Words]:\n    "release it"\n'):
        try:
            scriptt16.read("Show the mod.", world_of(faulty), [], standin({}), join=False)
            raise AssertionError("the search ran on a world with a fault")
        except ValueError as refusal:
            assert "paint" in str(refusal) or "release.version: no span of a message can have the type Version" in str(refusal)


def test_interpretation():
    world = world_of(WORLD)
    reading = scriptt16.read("Redesign the mod. Compare the page and the mod. Then show the docs. Thanks.", world, [], standin({"Redesign": "redesign", "Compare": "compare", "Then": "show"}, yes=('"the page"', '"the mod"')), join=False)
    record = scriptt16.record(reading)
    first = record["phrases"]["inside"][0]
    assert record["form"] == 4 and len(record["id"]) == 32 and "demands" not in record and first["choice"] == "redesign"
    assert first["term"]["function"] == "redesign" and first["term"]["type"]["constructor"] == "Later"
    assert first["term"]["arguments"]["surface"]["constant"] == [9, 16] and first["term"]["arguments"]["surface"]["type"]["sum"] == "Surface"
    assert scriptt16.block(reading).splitlines() == [
        '1. redesign(surface=\'the mod\') -> Later[Surface]  0.90   "Redesign the mod."',
        '2. compare(surfaces=[\'the page\', \'the mod\']) -> Written  0.90   "Compare the page and the mod."',
        '3. show(subject=...) -> Subject  0.90   "Then show the docs."',
        "Words that ask for nothing: 4.",
        "Open holes:",
        "3. show.subject: Subject (model_abstained)",
    ]
    checked = scriptt16.check(reading, "I compared the page. Nothing else yet.", standin({}, yes=("compare several of them: 'the page'",)))
    assert [(one.function, one.item, one.state) for one in checked] == [
        ("redesign", None, scriptt16.State.OPEN),  # a Later term that the reply does not do is open: nothing is promised by default
        ("compare", "'the page'", scriptt16.State.DONE),  # Written needs no execution
        ("compare", "'the mod'", scriptt16.State.OPEN),
        ("show", None, scriptt16.State.OPEN),
    ]
    assert checked[1].call == "compare(surfaces=['the page', 'the mod'])" and checked[1].phrase == "Compare the page and the mod." and checked[1].evidence == ()


def old_gate(proposed: agree.World, lines: list[dict], model: scriptt16.Model, limits: scriptt16.Limits = scriptt16.Limits()) -> bool:
    """The gate before approved cases, copied as it was: it accepts a world if the average bits per decision do not go up."""
    average = lambda found: sum(found) / len(found) if found else 0.0
    current_bits = average([one for line in lines for one in scriptt16.recorded_bits(line)])
    if proposed.faults + scriptt16.ungrounded(proposed):
        return False
    replayed: list[float] = []
    for line in lines:
        reading = scriptt16.read(line["text"], proposed, [], model, False, limits, scriptt16.recorded_phrases(line, proposed))
        replayed += scriptt16.recorded_bits(scriptt16.record(reading))
    return average(replayed) <= current_bits


def without_functions(source: str, kept: set[str] | None = None, dropped: set[str] = frozenset()) -> str:
    """Returns a world.py text with some of its functions taken out.

    Args:
        source: The text of world.py.
        kept: If given, every function not named here is taken out.
        dropped: The functions to take out.
    """
    lines = source.splitlines(keepends=True)
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef) and (node.name in dropped or (kept is not None and node.name not in kept)):
            source = source.replace("".join(lines[node.lineno - 1:node.end_lineno]), "")
    return source


def test_gate():
    world = world_of(WORLD)
    sure = standin({"Redesign": "redesign", "Follow": "follow"})
    lines = [scriptt16.record(scriptt16.read(text, world, [], sure, join=False)) for text in ("Redesign the mod. Thanks.", "Follow this rule.")]
    assert all(line["decisions"] for line in lines) and scriptt16.recorded_phrases(lines[0], world).inside[1].start == 18  # the log has every answer and every phrase
    cases = [scriptt16.Case("Redesign the mod. Thanks.", ("redesign(surface='the mod')", "nothing")), scriptt16.Case("Follow this rule.", ("follow(rule='Follow this rule.')",))]

    def counting(model: scriptt16.Model, count: list[int]) -> scriptt16.Model:
        def counted(state: str, asked: dict[str, dict]) -> dict[str, dict]:
            count.append(len(asked))
            return model(state, asked)
        return counted

    # The same world reads every approved case as approved: accepted, with the diagnostics filled.
    kept = scriptt16.gate(world, cases, lines, sure)
    assert kept.accepted and kept.lost == [] and kept.faults == [] and kept.preserved_obligations == 2 and kept.unresolved_holes == 0, kept
    assert kept.decision_count == 6 and kept.mean_bits is not None and kept.world_hash == scriptt16.world_hash(world) and len(kept.prompts_hash) == 16
    assert kept.prompts_hash != scriptt16.gate(world, cases, lines, sure, scriptt16.Prompts(what="What is asked?")).prompts_hash

    # A change that adds a fault is rejected, and d1 is not asked.
    asked: list[int] = []
    decision = scriptt16.gate(world_of(WORLD + '\ndef paint(surface: Many | int) -> Later[Surface]:\n    "paint it"\n'), cases, lines, counting(sure, asked))
    assert not decision.accepted and decision.mean_bits is None and "paint" in decision.faults[0] and asked == []

    # The lobotomized world: redesign is gone and d1 reads "Redesign the mod." as nothing with the same 0.90, so the
    # bits do not go up. The approved case loses its obligation and the gate rejects the world.
    lobotomized = world_of(without_functions(WORLD, dropped={"redesign"}))
    rejected = scriptt16.gate(lobotomized, cases, lines, sure)
    assert not rejected.accepted and rejected.lost == ["'Redesign the mod. Thanks.' phrase 1: approved redesign(surface='the mod'), now nothing"], rejected.lost
    assert rejected.mean_bits <= kept.mean_bits  # d1 is as sure as before: the bits alone cannot see the loss
    # Control: the old bits-only gate accepts the same world.
    assert old_gate(lobotomized, lines, sure)

    # More open holes than the approved readings have: rejected, though every phrase reads as approved.
    holed = [scriptt16.Case("Redesign it.", ("redesign(surface=...)",), holes=0)]
    assert not scriptt16.gate(world, holed, [], standin({"Redesign": "redesign"})).accepted
    assert scriptt16.gate(world, [dataclasses.replace(holed[0], holes=1)], [], standin({"Redesign": "redesign"})).accepted

    # An invented obligation is a misbinding too: "nothing" is an approved value.
    eager = standin({"Redesign": "redesign", "Follow": "follow", "Thanks": "follow"})
    assert scriptt16.gate(world, cases, [], eager).lost == ["'Redesign the mod. Thanks.' phrase 2: approved nothing, now follow(rule=...)"]

    # An approved case is read as the product reads it: with join on. A d1 that joins every pair of sentences makes
    # "Redesign the mod. Thanks." one phrase, and the gate sees it. Control: the same case marked join off is not read with
    # join, so the gate cannot see what the product path does to it.
    joining = standin({"Redesign": "redesign", "Follow": "follow"}, yes=(scriptt16.JOIN,))
    assert cases[0].join and scriptt16.gate(world, cases, [], joining).lost == ["'Redesign the mod. Thanks.': 2 phrases approved, 1 read: [\"redesign(surface='the mod')\"]"]
    assert scriptt16.gate(world, [dataclasses.replace(cases[0], join=False)], [], joining).accepted
    pinned = json.loads((HERE / "golden.json").read_text())["cases"]
    assert all(one["join"] is True for one in pinned) and all(case.join for case in scriptt16.golden(HERE / "golden.json"))

    # golden.json loads, and holds the cases the gate reads.
    golden = scriptt16.golden(HERE / "golden.json")
    assert {"Redesign the mod.", "Redesign the mod. Then show the original mod."} <= {case.message for case in golden}
    assert all(case.expected for case in golden)


def test_union_kinds():
    # Every path that builds a union checks the kind of each side: A | None, None | A, a nested union, a field of a
    # product, an Enum member, and a provenance applied to a constructor.
    source = WORLD + (
        '\ndef a(x: Many | None) -> Written:\n    "a"\n'
        '\ndef b(x: None | Later) -> Written:\n    "b"\n'
        '\ndef c(x: Maybe[Many | int] | None) -> Written:\n    "c"\n'
        '\nclass Pair(typing.NamedTuple):\n    "p"\n    x: Many | None\n'
        '\nclass Odd(enum.Enum):\n    "o"\n    ONE: Maybe | None = "one"\n'
        '\ndef d(x: Asked[Many]) -> Written:\n    "d"\n'
        '\ndef e(x: Asked[Surface] | None) -> Written:\n    "e"\n'
        '\ndef f(x: Surface | None) -> Written:\n    "f"\n')
    world = world_of(source)
    for name, side in (("a", "Many"), ("b", "Later"), ("c", "Many"), ("Pair", "Many"), ("Odd", "Maybe")):
        assert any(f" {name}" in fault and f"{side} has kind * -> *, and each side of | needs kind *" in fault for fault in world.faults), (name, world.faults)
    assert any(" d:" in fault and "Asked takes a type of kind *, and Many has kind * -> *" in fault for fault in world.faults), world.faults
    # Controls: well-kinded unions on the same paths load.
    assert {"e", "f"} <= set(world.functions) and not {"a", "b", "c", "d"} & set(world.functions) and len(world.faults) == 6, world.faults
    assert agree.show(world.functions["e"].parameters[0][1]) == "Maybe[Asked[Surface]]"


def test_provenance():
    world = world_of(WORLD + '\ntype Subject2 = Surface | pathlib.Path\n\ndef inspect(surface: Surface) -> Later[Observed[Surface]]:\n    "look at it"\n\ndef keep(surface: Asked[Surface]) -> None:\n    "keep it as it is"\n')
    assert world.faults == [], world.faults
    words, asked, written, observed, surface, subject = (world.types[name] for name in ("Words", "Asked", "Written", "Observed", "Surface", "Subject"))
    asked_surface, written_surface, observed_surface = (agree.Brand(name, surface, words) for name in ("Asked", "Written", "Observed"))
    asked_subject = agree.Brand("Asked", subject, words)
    # The bare name is the provenance over Words, and the subscript builds the same provenance over any type.
    assert asked == agree.Brand("Asked", words, words) and world.functions["keep"].parameters[0][1] == asked_surface
    assert world.functions["inspect"].result == agree.Applied(agree.LATER, observed_surface)
    assert [agree.show(one) for one in (asked, asked_surface, world.functions["inspect"].result)] == ["Asked", "Asked[Surface]", "Later[Observed[Surface]]"]
    assert agree.kind_of(asked_surface) == agree.Star() and agree.tree(asked_surface)["brand"] == "Asked" and agree.tree(asked_surface)["of"]["sum"] == "Surface"
    # Asked[Words] written out is the bare Asked.
    assert world_of(WORLD + '\ndef g(x: Asked[Words]) -> None:\n    "g"\n').functions["g"].parameters[0][1] == asked
    # A provenance is a subtype of what it wraps, and covariant; two provenances are disjoint.
    assert agree.is_subtype(asked_surface, surface) and agree.is_subtype(observed_surface, surface) and agree.is_subtype(observed_surface, subject)
    assert agree.is_subtype(asked_surface, asked_subject) and not agree.is_subtype(asked_subject, asked_surface)
    assert not agree.is_subtype(asked_surface, written_surface) and not agree.is_subtype(written_surface, asked_surface)
    assert not agree.is_subtype(written, asked) and not agree.is_subtype(surface, asked_surface) and not agree.is_subtype(asked_surface, asked)
    assert agree.is_subtype(agree.Applied(agree.LATER, observed_surface), agree.Applied(agree.LATER, surface))

    # fills: a Surface that a phrase of the user names fills an Asked[Surface] hole; the same Surface quoted from a
    # reply does not; a value of type Observed[Surface] fills a Surface hole, also as Later.
    mod = next(member for member in surface.alternatives if member.name == "MOD")
    named = scriptt16.Constant(surface, mod, 0, 7, "Asked")
    quoted = scriptt16.Constant(surface, mod, 0, 7, "Written")
    assert scriptt16.fills(named, asked_surface) and not scriptt16.fills(quoted, asked_surface) and not scriptt16.fills(named, written_surface)
    assert scriptt16.fills(scriptt16.Constant(observed_surface, mod, 0, 7), surface)
    looked = scriptt16.Application(world.functions["inspect"], {"surface": scriptt16.Hole(observed_surface)})
    assert scriptt16.fills(looked, surface) and scriptt16.fills(looked, subject) and not scriptt16.fills(looked, words)

    # The search: constants get the brand of their phrase as origin, and an Asked[Surface] hole takes the user's Surface.
    reading = scriptt16.read("Keep the mod.", world, [], standin({"Keep": "keep"}), join=False)
    term = scriptt16.innermost(reading.message)[0].term
    assert scriptt16.say(term, reading.text) == "keep(surface='the mod')" and term.origin == "Asked" and term.arguments["surface"].origin == "Asked"
    assert scriptt16.term_record(term, reading.text)["arguments"]["surface"]["origin"] == "Asked"
    # Control: a mod named only inside a quote of a reply does not fill it, and d1 says no word refers to the quote.
    reply = "I will leave the mod exactly as it is for now, nothing else."
    reading = scriptt16.read('"leave the mod exactly as it is for now" Keep it.', world, [reply], standin({"Keep": "keep"}), join=False)
    assert terms_of(reading)[1] == "keep(surface=...)", terms_of(reading)

    # Adoption: d1 says that "that" means the quote, so the quote fills the Asked hole, keeps its origin Written, and
    # names the phrase that adopted it. With every other word d1 says no.
    reply = "Until then I use only these ten words, each in its own exact sense."
    text = '"I use only these ten words, each in its own exact sense." Keep to that from now on.'
    refers_that = standin({"Keep": "follow"}, {"Keep": "I use only"}, yes=("does [that] mean",))
    reading = scriptt16.read(text, world, [reply], refers_that, join=False)
    rule = scriptt16.innermost(reading.message)[1].term.arguments["rule"]
    assert terms_of(reading)[1] == "follow(rule='\"I use only these ten words, each in its own exact sense.\"')", terms_of(reading)
    assert rule.origin == "Written" and rule.adopted_by == "Keep to that from now on." and agree.show(rule.type) == "Written"
    asked_words = reading.requests[1]["asked"]
    assert [question["instructions"] for question in asked_words.values()][2] == 'In the last sentence, does [that] mean "I use only these ten words, each in its own exact sense."?'
    assert reading.requests[1]["state"].endswith("\nKeep to that from now on.")
    # Control: the same message where d1 says no for every word. The quote is not adopted, and the rule is the user's words.
    reading = scriptt16.read(text, world, [reply], standin({"Keep": "follow"}, {"Keep": "I use only"}), join=False)
    rule = scriptt16.innermost(reading.message)[1].term.arguments["rule"]
    assert terms_of(reading)[1] == "follow(rule='Keep to that from now on.')" and rule.origin == "Asked" and rule.adopted_by is None
    # Control: a hole that is not Asked asks no REFERS question; explain takes the quote by its type, unadopted.
    reading = scriptt16.read('"I use only these ten words, each in its own exact sense." What did you mean by that?', world, [reply], standin({"What": "explain"}, {"What": "ten words"}, yes=("does [that] mean",)), join=False)
    assert not any("In the last sentence" in question["instructions"] for request in reading.requests for question in request["asked"].values())
    assert scriptt16.innermost(reading.message)[1].term.arguments["subject"].adopted_by is None


def test_real_world():
    world = world_of((HERE / "world.py").read_text())
    assert world.faults == [] and scriptt16.ungrounded(world) == [], (world.faults, scriptt16.ungrounded(world))
    proposal = world.types["Proposal"]
    assert isinstance(proposal, agree.Product) and [name for name, _ in proposal.fields] == ["idea", "solves", "evidence"]
    assert isinstance(world.types["Problem"], agree.Sum) and agree.show(world.functions["propose"].parameters[0][1]) == "Proposal"
    # The search builds a Proposal record for propose, and its Many[Problem] field takes the problem that d1 accepts.
    for accepted, solves in ((('"the crash"',), ["'the crash'"]), ((), None)):  # many_is gives d1 the plain words in quote marks
        reading = scriptt16.read("Propose a fix for the crash.", world, [], standin({"Propose": "propose"}, yes=accepted), join=False)
        record = scriptt16.innermost(reading.message)[0].term.arguments["proposal"]
        assert isinstance(record, scriptt16.Record) and record.product == proposal, record
        field = record.fields["solves"]
        assert (field.terms and [scriptt16.say(one, reading.text) for one in field.terms]) if solves else isinstance(field, scriptt16.Hole), field
        if solves:
            assert [scriptt16.say(one, reading.text) for one in field.terms] == solves and field.terms[0].origin == "Asked"


def instructions_sent(prompts_render, model) -> list[tuple[str, str]]:
    """Reads and checks a set of messages that asks d1 every one of the five wordings.

    Args:
        prompts_render: The function that renders a wording, as Prompts.render does.
        model: The stand-in d1.

    Returns:
        Each question that d1 received, as (the key of the question, its instructions), in order.
    """
    world = world_of(WORLD)
    original = scriptt16.Prompts.render
    scriptt16.Prompts.render = prompts_render
    sent: list[tuple[str, str]] = []

    def recording(state: str, asked: dict[str, dict]) -> dict[str, dict]:
        sent.extend((key, question["instructions"]) for key, question in asked.items())
        return model(state, asked)
    try:
        for text in ("Redesign the mod. Compare the page and the mod. Then show the docs. Thanks.", "Look at the page and the mod. Compare them.", "Show the mod and the page.", "Show it, notes.md or the mod."):
            reading = scriptt16.read(text, world, [], recording, join=True)
            from_requests = [(key, question["instructions"]) for request in reading.requests for key, question in request["asked"].items()]
            assert from_requests == sent[len(sent) - len(from_requests):]  # Reading.requests records what d1 received
            scriptt16.check(reading, "I compared the page. Nothing else yet.", recording)
    finally:
        scriptt16.Prompts.render = original
    return sent


def test_prompts():
    model = standin({"Redesign": "redesign", "Compare": "compare", "Then": "show", "Show": "show"}, yes=('"the page"',))

    def baseline(self, name: str, **slots: str) -> str:
        """The wordings as the baseline rendered them: straight from the shipped harness."""
        return {
            "join": lambda: scriptt16.JOIN,
            "what": lambda: shipped.WHAT,
            "which": lambda: scriptt16.rendered(shipped.NAMES(slots["role"], slots["asks"])),
            # Changed on purpose from shipped.IS: the shipped wording took "the page" in "Compare the mod, not the page."
            # with the real d1 (C3 of the acceptance table); this one asks whether the message leaves the value out.
            "many_is": lambda: 'The message asks the reader to {asks}. Is "{value}" one of the {role} that the message asks for, and not one that it leaves out?'.format(**slots),
            # Changed on purpose from shipped.DID: the default did names the call and the phrase (so two calls of one
            # function get two questions), and asks whether the reply says it is done; executions are judged apart.
            "did": lambda: 'The message asks the reader to {asks} ({call} for "{phrase}"). Does the reply say that this is done?'.format(**slots),
        }[name]()

    # With the default Prompts, d1 receives the same instructions, byte for byte, as from the shipped wordings for
    # join, what and which, and the deliberate new wordings for many_is and did.
    expected, got = instructions_sent(baseline, model), instructions_sent(scriptt16.Prompts.render, model)
    assert got == expected, [pair for pair in zip(expected, got) if pair[0] != pair[1]][:3]
    defaults = scriptt16.Prompts()
    assert {defaults.join, defaults.what} <= {instructions for _, instructions in got}  # every wording is asked
    for start in ("The text asks the reader to", "The message asks the reader to compare several of them. Is \"the page\" one of the surfaces", "The message asks the reader to compare several of them: 'the page' (compare(surfaces=['the page']) for \"Compare the page and the mod.\"). Does the reply"):
        assert any(instructions.startswith(start) for _, instructions in got), start
    assert list(defaults.as_dict()) == ["join", "what", "which", "many_is", "did", "evidence"]

    # An edited wording reaches d1, and the reading keeps it so that it can run again.
    world = world_of(WORLD)
    edited = scriptt16.Prompts(what="Which function does this text call for?", did="Did the reply run {call} for [{phrase}]?")
    seen: list[str] = []

    def recording(state: str, asked: dict[str, dict]) -> dict[str, dict]:
        seen.extend(question["instructions"] for question in asked.values())
        return model(state, asked)
    reading = scriptt16.read("Redesign the mod.", world, [], recording, join=False, prompts=edited)
    assert seen == ["Which function does this text call for?"] and reading.prompts == edited and reading.limits == scriptt16.Limits()
    assert [request["asked"]["what"]["instructions"] for request in reading.requests] == ["Which function does this text call for?"]
    scriptt16.check(reading, "Done.", recording)  # no prompts given: the wordings of the reading
    assert seen[-1] == "Did the reply run redesign(surface='the mod') for [Redesign the mod.]?", seen[-1]
    scriptt16.check(reading, "Done.", recording, prompts=scriptt16.Prompts())
    assert seen[-1] == 'The message asks the reader to change how it looks (redesign(surface=\'the mod\') for "Redesign the mod."). Does the reply say that this is done?', seen[-1]

    # A wording may leave out a slot, but an unknown slot is refused by name, with the allowed ones.
    assert scriptt16.Prompts(which="Which one fits?").render("which", asks="x", role="y") == "Which one fits?"
    for name, wording, words in (("which", "Which {thing} for {asks}?", "{thing}"), ("join", "Same {asks}?", "none"), ("did", "Did it {0}?", "{0}"), ("many_is", "Is {item.x} in?", "{item.x}"), ("what", "What {", "valid template")):
        try:
            scriptt16.Prompts(**{name: wording})
            raise AssertionError(f"the wording {wording!r} was accepted")
        except ValueError as refusal:
            assert words in str(refusal) and name in str(refusal), str(refusal)
    try:
        scriptt16.Prompts(did="Did it {asks} as {verb}?")
        raise AssertionError("unknown slot accepted")
    except ValueError as refusal:
        assert str(refusal) == "the did wording names the slot {verb}, which it does not have; its slots are: {asks}, {call}, {phrase}", str(refusal)



def engine_copies(notebook_source: str) -> list[str]:
    """Lists each function of agree.py and scriptt16.py that a notebook carries a copy of.

    Args:
        notebook_source: The text of the notebook.

    Returns:
        One finding for each top-level engine function whose ``def name(`` line
        is in the notebook, and one for each function of the notebook, at any
        depth and under any name, whose body is the body of an engine function.
        A docstring is left out of the comparison.
    """
    def body(function: ast.FunctionDef) -> str:
        statements = function.body
        if statements and isinstance(statements[0], ast.Expr) and isinstance(statements[0].value, ast.Constant) and isinstance(statements[0].value.value, str):
            statements = statements[1:]
        return "".join(ast.dump(statement) for statement in statements)

    engine: dict[str, str] = {}
    for module in (agree, scriptt16):
        for node in ast.parse(pathlib.Path(module.__file__).read_text()).body:
            if isinstance(node, ast.FunctionDef):
                engine[f"{module.__name__}.{node.name}"] = body(node)
    findings = [f"def line of {name}" for name in engine if f"def {name.split('.')[1]}(" in notebook_source]
    bodies = {engine_body: name for name, engine_body in engine.items() if engine_body}
    for node in ast.walk(ast.parse(notebook_source)):
        if isinstance(node, ast.FunctionDef) and body(node) in bodies:
            findings.append(f"body of {bodies[body(node)]} in the notebook function {node.name}")
    return findings


def test_notebook_single_source():
    notebook = (HERE / "notebook.py").read_text()
    assert engine_copies(notebook) == [], engine_copies(notebook)
    # Controls: a cell that copies an engine function is found, and so is a copy under another name.
    copied = notebook + "\n\n" + inspect.getsource(agree.kind_of)
    assert "def line of agree.kind_of" in engine_copies(copied) and "body of agree.kind_of in the notebook function kind_of" in engine_copies(copied)
    renamed = notebook + "\n\n" + inspect.getsource(scriptt16.derivations).replace("def derivations(", "def terms_for(", 1)
    assert engine_copies(renamed) == ["body of scriptt16.derivations in the notebook function terms_for"], engine_copies(renamed)


TOKEN = '\nToken = typing.NewType("Token", str)\n\ndef consume(token: Token) -> Written:\n    "use a token"\n'


def test_producers():
    """A parameter type that no span grounds is satisfiable if a function of the world gives it."""
    # Positive: produce() gives Token, so consume loads, reads, and its hole takes the application of produce.
    world = world_of(WORLD + TOKEN + '\ndef produce() -> Token:\n    "make a new token"\n')
    assert world.faults == [] and scriptt16.ungrounded(world) == [], scriptt16.ungrounded(world)
    reading = scriptt16.read("Use the token.", world, [], standin({"Use": "consume"}), join=False)
    assert terms_of(reading) == ["consume(token=produce())"], terms_of(reading)
    # Through Later: a function that gives Later[Token] also grounds Token.
    assert scriptt16.ungrounded(world_of(WORLD + TOKEN + '\ndef mint(surface: Surface) -> Later[Token]:\n    "mint a token"\n')) == []
    # A producer with a parameter: login takes the words of the phrase, and its Token feeds fetch.
    logged = world_of(WORLD + '\nToken = typing.NewType("Token", str)\n\ndef login(user: Words) -> Token:\n    "log in"\n\ndef fetch(token: Token) -> Observed:\n    "fetch the data"\n')
    assert logged.faults == [] and scriptt16.ungrounded(logged) == []
    assert terms_of(scriptt16.read("Fetch the data as max.", logged, [], standin({"Fetch": "fetch"}), join=False)) == ["fetch(token=login(user='Fetch the data as max.'))"]
    # Controls: with no producer, or with a producer that only feeds itself, Token is ungrounded and read refuses.
    for faulty in (WORLD + TOKEN, WORLD + TOKEN + '\ndef renew(token: Token) -> Token:\n    "renew a token"\n'):
        faults = scriptt16.ungrounded(world_of(faulty))
        assert any(fault.startswith("consume.token: no span of a message can have the type Token") for fault in faults), faults
        try:
            scriptt16.read("Use the token.", world_of(faulty), [], standin({"Use": "consume"}), join=False)
            raise AssertionError("the search ran on a world with an ungrounded parameter")
        except ValueError:
            pass


def test_versions():
    """The original value and the earlier application that changed it are both offered; d1 chooses by the words."""
    world = world_of(WORLD)
    told = {"Redesign": "redesign", "Then": "show"}
    original = scriptt16.read("Redesign the mod. Then show the original mod.", world, [], standin(told, {"Then": "the original"}), join=False)
    redesigned = scriptt16.read("Redesign the mod. Then show the redesigned mod.", world, [], standin(told, {"Then": "redesign("}), join=False)
    assert terms_of(original) == ["redesign(surface='the mod')", "show(subject='the mod')"], terms_of(original)
    assert terms_of(redesigned) == ["redesign(surface='the mod')", "show(subject=redesign(surface='the mod'))"], terms_of(redesigned)
    # Control: the constant 'the mod' must be among the terms derivations lists after an application used it. The
    # deleted taken_by rule left it out, so "the original mod" could not be expressed.
    phrase = scriptt16.innermost(original.message)[0]
    environment = scriptt16.Environment((), (phrase.term, *scriptt16.grounded("Redesign the mod.", world)))
    listed = [scriptt16.say(term, "") for term in scriptt16.derivations(world.types["Subject"], environment, world, 1, world.functions["show"])]
    assert listed == ["redesign(surface='the mod')", "'the mod'"], listed


def test_many_inclusion():
    """A mention is not an inclusion: d1 answers for each local term whether the phrase takes it."""
    world = world_of(WORLD)
    model = standin({"Compare": "compare"}, yes=('"the mod"',))
    reading = scriptt16.read("Compare the mod, not the page.", world, [], model, join=False)
    assert terms_of(reading) == ["compare(surfaces=['the mod'])"], terms_of(reading)
    asked = reading.requests[1]["asked"]
    assert sorted(question["type"] for question in asked.values()) == ["boolean", "boolean"]  # one question for each local term
    # Control: the blind rule took every local mention and gave ['the mod', 'the page']; the assertion above rejects it.
    assert terms_of(reading) != ["compare(surfaces=['the mod', 'the page'])"]
    # One local term gets the same question, and d1 can refuse it.
    single = scriptt16.read("Compare the mod.", world, [], model, join=False)
    assert terms_of(single) == ["compare(surfaces=['the mod'])"] and len(single.requests[1]["asked"]) == 1
    assert terms_of(scriptt16.read("Compare the mod.", world, [], standin({"Compare": "compare"}), join=False)) == ["compare(surfaces=...)"]
    # d1 refuses every local term and no earlier term exists: the hole is open because d1 abstained.
    refused = scriptt16.read("Compare the mod, not the page.", world, [], standin({"Compare": "compare"}), join=False)
    assert [(path, hole.reason) for path, hole in scriptt16.holes_of(scriptt16.innermost(refused.message)[0].term)] == [("surfaces", "model_abstained")]
    # No term at all: no candidate.
    empty = scriptt16.read("Compare them.", world, [], standin({"Compare": "compare"}), join=False)
    assert [hole.reason for _, hole in scriptt16.holes_of(scriptt16.innermost(empty.message)[0].term)] == ["no_candidate"]


def test_nested_later():
    """type_of finds Later inside a list, inside a record and inside a nested application."""
    world = world_of(WORLD)
    surface, cell = world.types["Surface"], world.types["Cell"]
    mod = scriptt16.Constant(surface, next(member for member in surface.alternatives if member.name == "MOD"), 0, 7)
    redesigned = scriptt16.Application(world.functions["redesign"], {"surface": mod})
    page = scriptt16.Constant(surface, next(member for member in surface.alternatives if member.name == "PAGE"), 0, 8)
    in_list = scriptt16.Application(world.functions["compare"], {"surfaces": scriptt16.Several(surface, (redesigned, page))})
    assert agree.show(scriptt16.type_of(in_list)) == "Later[Written]"  # the old rule looked only at the type of the argument: Written
    number_type = dict(cell.fields)["number"]
    counted = agree.Function("count", "count it", (), agree.Applied(agree.LATER, number_type), 0)
    notebook = scriptt16.Constant(dict(cell.fields)["notebook"], pathlib.Path("notes.md"), 0, 8)
    in_record = scriptt16.Application(world.functions["open_cell"], {"cell": scriptt16.Record(cell, {"notebook": notebook, "number": scriptt16.Application(counted, {})})})
    assert agree.show(scriptt16.type_of(in_record)) == "Later[Observed]"
    nested = scriptt16.Application(world.functions["show"], {"subject": scriptt16.Application(world.functions["show"], {"subject": redesigned})})
    assert agree.show(scriptt16.type_of(nested)) == "Later[Subject]"
    # Control: with no Later inside, the type stays the result type.
    plain = scriptt16.Application(world.functions["open_cell"], {"cell": scriptt16.Record(cell, {"notebook": notebook, "number": notebook})})
    assert agree.show(scriptt16.type_of(plain)) == "Observed"


def test_depth():
    """A producer whose own parameter needs a producer is offered only when the depth allows one more application."""
    with tempfile.TemporaryDirectory() as folder:
        (pathlib.Path(folder) / "notes.md").write_text("x")
        source = WORLD + TOKEN + '\ndef issue(observation: Observed) -> Token:\n    "issue a token for what was seen"\n'
        world = world_of(source, pathlib.Path(folder))
        assert world.faults == [] and scriptt16.ungrounded(world) == []
        text, model = "Use a token for cell 3 of notes.md.", standin({"Use": "consume"})
        deep = scriptt16.read(text, world, [], model, join=False, limits=scriptt16.Limits(depth=2))
        assert terms_of(deep) == ["consume(token=issue(observation=open_cell(cell=Cell(notebook='notes.md', number='3'))))"], terms_of(deep)
        # Control: at depth 1 the producer of the Token is not offered, and the hole says that the depth cut it.
        shallow = scriptt16.read(text, world, [], model, join=False, limits=scriptt16.Limits(depth=1))
        assert terms_of(shallow) == ["consume(token=...)"], terms_of(shallow)
        assert [hole.reason for _, hole in scriptt16.holes_of(scriptt16.innermost(shallow.message)[0].term)] == ["search_bound"]
        # An intermediate record: open_cell is offered for an Observed hole because Cell can be built from its fields.
        noted = world_of(WORLD + '\ndef note(observation: Observed) -> Written:\n    "note what was seen"\n', pathlib.Path(folder))
        reading = scriptt16.read("Note what cell 3 of notes.md shows.", noted, [], standin({"Note": "note"}), join=False)
        assert terms_of(reading) == ["note(observation=open_cell(cell=Cell(notebook='notes.md', number='3')))"], terms_of(reading)
        # Control: with no number in the message the record cannot be built, and open_cell is not offered.
        reading = scriptt16.read("Note what notes.md shows.", noted, [], standin({"Note": "note"}), join=False)
        assert terms_of(reading) == ["note(observation=...)"], terms_of(reading)


def test_hole_reasons():
    """Each open hole says why it is open."""
    world = world_of(WORLD)
    reason = lambda reading: [hole.reason for _, hole in scriptt16.holes_of(scriptt16.innermost(reading.message)[0].term)]
    assert reason(scriptt16.read("Show the docs.", world, [], standin({"Show": "show"}), join=False)) == ["no_candidate"]
    assert reason(scriptt16.read("Show the mod and the page.", world, [], standin({"Show": "show"}), join=False)) == ["model_abstained"]
    # Three terms fit and two are offered: d1 chose none, but the third was never seen.
    assert reason(scriptt16.read("Show the mod and the page.", world, [], standin({"Show": "show"}), join=False, limits=scriptt16.Limits(offered=2))) == ["search_bound"]
    assert reason(scriptt16.read("Redesign it.", world, [], standin({"Redesign": "redesign"}), join=False)) == ["model_abstained"]
    # Holes compare by type and reason, and a hole made with no reason has the reason no_candidate.
    subject = world.types["Subject"]
    assert scriptt16.Hole(subject) == scriptt16.Hole(subject, "no_candidate") != scriptt16.Hole(subject, "model_abstained")
    assert scriptt16.say(scriptt16.Hole(subject, "model_abstained"), "") == "..."


def test_context_across_turns():
    world = world_of(WORLD)
    model = standin({"Redesign": "redesign", "Show": "show"}, {"Show it.": "the result of redesign"})
    first = turns.start_turn("Redesign the mod.", world, [], model)
    by_id = {entity.id: entity for entity in first.context_out}
    assert list(by_id) == ["t1:p1", "t1:9-16"] and by_id["t1:p1"].version_of == "t1:9-16" and by_id["t1:9-16"].origin == "Asked", by_id
    # Turn 2 names the redesigned mod by "it": the entity of turn 1 fills the hole, as the same term.
    second = turns.start_turn("Show it.", world, [], model, context_in=first.context_out)
    term = scriptt16.innermost(second.reading.message)[0].term
    assert second.turn == 2 and scriptt16.say(term, "") == "show(subject=redesign(surface='the mod'))" and term.arguments["subject"] is by_id["t1:p1"].term
    # d1 saw the message of turn 1 and the term labelled as its result, not as a new call.
    which = second.reading.requests[1]
    assert which["state"] == "Redesign the mod.\nShow it." and "the result of redesign(surface='the mod') in phrase 1" in [option["description"] for option in which["asked"]["which"]["options"]], which
    # show gives a Subject, which cannot stand where a Surface stood: a new entity, not a version.
    assert [(entity.id, entity.version_of) for entity in second.context_out][:1] == [("t2:p1", None)] and len(second.context_out) == 3
    # Controls: with no context the hole stays open; with bare terms (no message) d1 is told it is a new call.
    alone = scriptt16.innermost(turns.start_turn("Show it.", world, [], model).reading.message)[0].term
    assert isinstance(alone.arguments["subject"], scriptt16.Hole), scriptt16.say(alone, "")
    bare = scriptt16.read("Show it.", world, [], model, join=False, prior_context=[entity.term for entity in first.context_out])
    assert "redesign(surface='the mod') (a new call)" in [option["description"] for option in bare.requests[1]["asked"]["which"]["options"]]
    # join=False keeps each sentence a phrase of its own and asks d1 no join question; the default asks it.
    joined = standin({"Redesign": "redesign", "Show": "show"}, yes=(scriptt16.JOIN,))
    apart = turns.start_turn("Redesign the mod. Then show the mod.", world, [], joined, join=False)
    assert len(scriptt16.innermost(apart.reading.message)) == 2 and "join" not in {decision["template"] for request in apart.reading.requests for decision in request["decisions"]}
    together = turns.start_turn("Redesign the mod. Then show the mod.", world, [], joined)
    assert len(scriptt16.innermost(together.reading.message)) == 1 and together.reading.requests[0]["decisions"][0]["template"] == "join"


def test_decision_records():
    world = world_of(WORLD)
    reading = scriptt16.read("Show the mod.", world, [], standin({"Show": "show"}, {"Show": "'the mod'"}), join=False)
    assert [request["asked"] and request["answers"] for request in reading.requests]  # the keys that callers read are kept
    decisions = [decision for request in reading.requests for decision in request["decisions"]]
    assert [decision["template"] for decision in decisions] == ["what", "which"] and decisions[0]["instructions"] == scriptt16.Prompts().what
    assert decisions[1]["options"][0]["id"] == "0" and decisions[1]["probabilities"]["0"] == 0.9 and decisions[1]["p_true"] is None
    assert all(request["world_hash"] == scriptt16.world_hash(world) and request["prompts_hash"] == scriptt16.prompts_hash(scriptt16.Prompts()) for request in reading.requests)
    many = scriptt16.read("Look at the page and the mod. Compare them.", world, [], standin({"Compare": "compare"}, yes=("the page",)), join=False)
    assert {decision["template"] for request in many.requests for decision in request["decisions"]} == {"what", "many_is"}
    # The hashes are stable, and each changes with what it covers (controls).
    assert scriptt16.world_hash(world_of(WORLD)) == scriptt16.world_hash(world) and scriptt16.prompts_hash(scriptt16.Prompts()) == scriptt16.prompts_hash(scriptt16.Prompts())
    assert scriptt16.world_hash(world_of(WORLD.replace('"show it"', '"show it to the user"'))) != scriptt16.world_hash(world)
    assert scriptt16.prompts_hash(scriptt16.Prompts(what="Which function?")) != scriptt16.prompts_hash(scriptt16.Prompts())


def test_corrections_round_trip():
    with tempfile.TemporaryDirectory() as name:
        folder = pathlib.Path(name)
        (folder / "notes.md").write_text("x")
        (folder / ".scriptt").mkdir()
        (folder / ".scriptt" / "world.py").write_text(WORLD)
        world, log = world_of(WORLD, folder), folder / ".scriptt" / "events.jsonl"
        model = standin({"Redesign": "redesign", "Show": "show"}, {"Show it.": "the result of redesign"})
        first = turns.start_turn("Redesign the mod.", world, [], model)
        trace = turns.start_turn("Show it.", world, [], model, context_in=first.context_out)
        original = turns.block_of(trace)
        assert original.startswith("1. show(subject=redesign(surface='the mod'))"), original
        assert {"'the mod'", "redesign(surface='the mod')"} <= set(turns.candidates(trace, 1, "subject")) and "show" in turns.candidates(trace, 1, None)

        # parser_override: the user drags the original mod into the hole.
        overridden = turns.correct(trace, 1, "subject", "'the mod'")
        delivers = lambda block: block.splitlines()[0].startswith("1. show(subject='the mod') -> Subject")
        assert overridden.corrections[-1].kind == "parser_override" and delivers(turns.block_of(overridden)) and not delivers(original)
        assert overridden.context_out[0].id == "t2:p1" and scriptt16.say(overridden.context_out[0].term, "") == "show(subject='the mod')"  # context[n+1] follows the correction
        turns.save(overridden)  # the default log of the folder
        loaded = turns.load(log, world)
        assert delivers(turns.block_of(loaded)) and delivers(turns.hook_block(folder)) and loaded.reading.message == overridden.reading.message
        assert loaded.context_in == trace.context_in and loaded.context_out == overridden.context_out and [c.kind for c in loaded.corrections] == ["parser_override"]

        # Controls: a load that ignored the corrections, and a hook that sent the reading before them, both fail the check.
        original_apply, original_block = turns.applied_correction, turns.block_of
        try:
            turns.applied_correction = lambda trace, correction, world: trace
            assert not delivers(turns.hook_block(folder))
        finally:
            turns.applied_correction = original_apply
        try:
            turns.block_of = lambda trace: scriptt16.block(trace.history[0] if trace.history else trace.reading)
            assert not delivers(turns.hook_block(folder))
        finally:
            turns.block_of = original_block
        assert delivers(turns.hook_block(folder))

        # undo restores the reading, and the restored trace survives a reload.
        restored = turns.undo(loaded)
        assert turns.block_of(restored) == original and restored.corrections == ()
        turns.save(restored, log)
        assert turns.hook_block(folder) == original and turns.load(log, world).reading.message == trace.reading.message
        assert turns.load(log, world, turn=2).corrections == () and len(turns.trace_lines(log)) == 2

        # candidate_injected: a value that the search did not offer, typed by the grounding rules.
        injected = turns.correct(trace, 1, "subject", "notes.md")
        assert injected.corrections[-1].kind == "candidate_injected" and turns.block_of(injected).startswith("1. show(subject='notes.md') -> Subject")
        injected = turns.with_executions(injected, [turns.Execution("command", "open notes.md", 0)])
        turns.save(injected, log)
        again = turns.load(log, world)
        assert turns.block_of(again) == turns.block_of(injected) and again.reading.message == injected.reading.message and again.executions == injected.executions
        assert turns.undo(again).reading.message == trace.reading.message
        quoted = turns.correct(trace, 1, "subject", "'the page'")  # a member as say() writes it, which the search did not offer
        assert quoted.corrections[-1].kind == "candidate_injected" and turns.block_of(quoted).startswith("1. show(subject='the page')")
        for wrong, error in (("the docs", ValueError), (scriptt16.Constant(world.types["Words"], "x", -1, -1), TypeError)):
            try:
                turns.correct(trace, 1, "subject", wrong)
                raise AssertionError(f"{wrong!r} was accepted for show.subject")
            except error:
                pass

        # request_edited: the user changes the function, with no model (an open hole) and with d1 filling it.
        edited = turns.correct(trace, 1, None, "redesign")
        assert edited.corrections[-1].kind == "request_edited" and turns.block_of(edited).splitlines()[0].startswith("1. redesign(surface=...)")
        filled = turns.correct(trace, 1, None, "redesign", model=standin({}, {"Show it.": "the original"}))
        assert turns.block_of(filled).startswith("1. redesign(surface='the mod')"), turns.block_of(filled)
        removed = turns.correct(trace, 1, None, "nothing")
        assert "Words that ask for nothing: 1." in turns.block_of(removed)
        turns.save(filled, log)
        assert turns.load(log, world).reading.message == filled.reading.message

        # prompt_edited: d1 runs again with the edited wording; the log keeps the wordings, and undo restores.
        wording = scriptt16.Prompts(what="Which function does this text call for?")
        prompted = turns.with_prompts(trace, wording, model)
        assert prompted.corrections[-1].kind == "prompt_edited" and prompted.reading.requests[0]["asked"]["what"]["instructions"] == wording.what
        turns.save(prompted, log)
        line = turns.trace_lines(log)[-1]
        assert line["prompts"] == dataclasses.asdict(wording) and line["prompts_hash"] == scriptt16.prompts_hash(wording)
        back = turns.load(log, world)
        assert back.prompts == wording and back.reading.message == prompted.reading.message and turns.undo(back).reading.prompts == scriptt16.Prompts()

        # A trace does not load against another world (control for the world hash).
        try:
            turns.load(log, world_of(WORLD.replace('"show it"', '"show it to the user"'), folder))
            raise AssertionError("a trace loaded against another world")
        except ValueError as refusal:
            assert "world" in str(refusal)


def judge(*rules: tuple[str, str, float]) -> scriptt16.Model:
    """Returns a d1 for yes-or-no questions whose answers the test sets.

    Args:
        rules: Each (words of the instructions, words of the state, share). The
            first rule whose words are both in the question gives the share; a
            question that no rule matches gets 0.1.
    """
    def model(state: str, asked: dict[str, dict]) -> dict[str, dict]:
        return {key: {"p_true": next((share for wording, seen, share in rules if wording in question["instructions"] and seen in state), 0.1)} for key, question in asked.items()}
    return model


def recorded(model: scriptt16.Model, sent: list[tuple[str, dict]]) -> scriptt16.Model:
    """Returns the model, recording each request that it receives."""
    def recording(state: str, asked: dict[str, dict]) -> dict[str, dict]:
        sent.append((state, asked))
        return model(state, asked)
    return recording


def old_check(reading: scriptt16.Reading, reply: str, model: scriptt16.Model, limits: scriptt16.Limits = scriptt16.Limits()) -> list[tuple[str, str | None, str, float]]:
    """The check before executions, copied as it was, with the wording that it sent: (function, item, state, share)."""
    old_did = "The message asks the reader to {asks}. Does the reply do it, or say that it is done?"
    questions: dict[str, scriptt16.YesNo] = {}
    subjects: dict[str, tuple[scriptt16.Phrase, str | None]] = {}
    for phrase in scriptt16.innermost(reading.message):
        if not isinstance(phrase.term, scriptt16.Application):
            continue
        items = [scriptt16.say(one, reading.text) for argument in phrase.term.arguments.values() if isinstance(argument, scriptt16.Several) for one in argument.terms]
        for item in items or [None]:
            key = f"{phrase.start} {item}"
            questions[key] = scriptt16.YesNo(old_did.format(asks=phrase.term.function.asks + (f": {item}" if item else "")))
            subjects[key] = (phrase, item)
    shares = scriptt16.ask_all(model, f"MESSAGE:\n{reading.text}\n\nREPLY:\n{reply}", questions)
    found = []
    for key, (phrase, item) in subjects.items():
        result = scriptt16.type_of(phrase.term)
        unfinished = "PROMISED" if isinstance(result, agree.Applied) and result.constructor == agree.LATER else "OPEN"
        found.append((phrase.term.function.name, item, "DONE" if shares[key] >= limits.yes else unfinished, round(shares[key], 3)))
    return found


def test_check_items():
    """Each item of a reading is one question that names its call and its phrase; a record splits into its fields."""
    world = world_of(WORLD)
    reading = scriptt16.read("Redesign the mod. Redesign the page.", world, [], standin({"Redesign": "redesign"}, {"Redesign": "the page"}), join=False)
    assert terms_of(reading) == ["redesign(surface='the mod')", "redesign(surface='the page')"], terms_of(reading)
    sent: list[tuple[str, dict]] = []
    checked = scriptt16.check(reading, "I redesigned the mod.", recorded(judge(("'the mod'", "", 0.9)), sent))
    questions = [question["instructions"] for question in sent[0][1].values()]
    assert len(questions) == 2 and questions[0] != questions[1] and "redesign(surface='the mod')" in questions[0] and '"Redesign the page."' in questions[1], questions
    assert [(one.call, one.phrase, one.state) for one in checked] == [("redesign(surface='the mod')", "Redesign the mod.", scriptt16.State.UNVERIFIED), ("redesign(surface='the page')", "Redesign the page.", scriptt16.State.OPEN)]
    # Control: the old check sent one wording for both calls, so d1 could not tell them apart, and the open one was promised.
    old_sent: list[tuple[str, dict]] = []
    old = old_check(reading, "I redesigned the mod.", recorded(judge(("'the mod'", "", 0.9)), old_sent))
    old_questions = [question["instructions"] for question in old_sent[0][1].values()]
    assert old_questions[0] == old_questions[1] and [state for _, _, state, _ in old] == ["PROMISED", "PROMISED"]

    with tempfile.TemporaryDirectory() as folder:
        (pathlib.Path(folder) / "notes.md").write_text("x")
        there = world_of(WORLD, pathlib.Path(folder))
        reading = scriptt16.read("Review cell 3 of notes.md.", there, [], standin({"Review": "review"}, yes=("Review cell",)), join=False)
        checked = scriptt16.check(reading, "Reviewed.", judge(("review a cell: cell=", "", 0.9)))
        assert [(one.item, one.state) for one in checked] == [("cell=Cell(notebook='notes.md', number='3')", scriptt16.State.UNVERIFIED), ("evidence='Review cell 3 of notes.md.'", scriptt16.State.OPEN)], checked
        # Control: the old check left the record whole: one question for the review.
        assert [item for _, item, _, _ in old_check(reading, "Reviewed.", judge())] == [None]


def test_check_executions():
    """The types of the world match a path; d1 matches every other execution; a failed one blocks its item."""
    with tempfile.TemporaryDirectory() as folder:
        (pathlib.Path(folder) / "notes.md").write_text("x")
        world = world_of(WORLD, pathlib.Path(folder))
        reading = scriptt16.read("Open cell 3 of notes.md.", world, [], standin({"Open": "open_cell"}), join=False)
        says_done = ("open a cell", "REPLY", 0.9)
        # The record splits into its fields. A path of the message and the path of a file the turn changed: the types
        # decide for the notebook field, and only the number field gets an evidence question.
        for given in ({"path": folder + "/notes.md"}, {"kind": "file_diff", "path": "notes.md"}, scriptt16.Execution("file_created", "notes.md")):
            sent: list[tuple[str, dict]] = []
            notebook, number = scriptt16.check(reading, "I opened it.", recorded(judge(says_done), sent), [given])
            recorded_as = scriptt16.execution_of(given)
            assert (notebook.item, notebook.state, notebook.evidence) == ("notebook='notes.md'", scriptt16.State.DONE, (f"{recorded_as.kind}: {recorded_as.subject} (by its path)",)), notebook
            assert number.item == "number='3'" and number.state == scriptt16.State.UNVERIFIED
            assert len(sent) == 2 and len(sent[1][1]) == 1  # one evidence question: the number, which has no path
        # Control: another file is no evidence for the notebook, decided by the paths with no question, though d1 says yes to every evidence question.
        sent = []
        notebook, _ = scriptt16.check(reading, "I opened it.", recorded(judge(says_done, ("", "EXECUTION", 0.9)), sent), [{"path": "other.md"}])
        assert notebook.state == scriptt16.State.UNVERIFIED and notebook.evidence == () and len(sent[1][1]) == 1
        # Observed with no executions at all: unverified. A reply that says nothing: open, whatever ran.
        assert [one.state for one in scriptt16.check(reading, "I opened it.", judge(says_done))] == [scriptt16.State.UNVERIFIED] * 2
        assert [one.state for one in scriptt16.check(reading, "Hello.", judge(), [{"path": "notes.md"}])] == [scriptt16.State.OPEN] * 2

    world = world_of(WORLD)
    reading = scriptt16.read("Redesign the mod.", world, [], standin({"Redesign": "redesign"}), join=False)
    claims = ("change how it looks", "REPLY", 0.9)
    shows = ("Does this record change or run the thing that redesign(surface='the mod') names", "mod/row.tsx", 0.8)
    # No path in the term: d1 decides with the evidence wording, whose state is the one execution and whose question names the call.
    sent = []
    [one] = scriptt16.check(reading, "I redesigned the mod.", recorded(judge(claims, shows), sent), [{"kind": "file_modified", "path": "mod/row.tsx"}, {"path": "web/site/index.html"}])
    assert one.state == scriptt16.State.DONE and one.evidence == ("file_modified: mod/row.tsx (d1 0.80)",), one
    assert [state for state, _ in sent[1:]] == ["EXECUTION:\nfile_modified: mod/row.tsx", "EXECUTION:\nfile_modified: web/site/index.html"]
    assert "redesign(surface='the mod')" in next(iter(sent[1][1].values()))["instructions"]
    # Control: d1 says the file is not that work, and the claim stays unverified.
    [one] = scriptt16.check(reading, "I redesigned the mod.", judge(claims), [{"path": "web/site/index.html"}])
    assert one.state == scriptt16.State.UNVERIFIED and one.evidence == ()
    # A command of the item that failed blocks it, even when the reply says it is done; the same command with exit code 0 is evidence.
    build = ("names", "npm run build-mod", 0.8)
    failed = {"kind": "command", "cmd": "npm run build-mod", "exit_code": 1}
    assert [one.state for one in scriptt16.check(reading, "I redesigned the mod.", judge(claims, build), [failed])] == [scriptt16.State.BLOCKED]
    assert [one.state for one in scriptt16.check(reading, "I redesigned the mod.", judge(claims, build), [failed, failed | {"exit_code": 0}])] == [scriptt16.State.DONE]
    assert [one.state for one in scriptt16.check(reading, "I redesigned the mod.", judge(claims, ("names", "error", 0.8)), [{"kind": "error", "detail": "the mod did not load"}])] == [scriptt16.State.BLOCKED]
    # Control: a failure that d1 does not match with the item does not block it.
    assert [one.state for one in scriptt16.check(reading, "I redesigned the mod.", judge(claims), [failed])] == [scriptt16.State.UNVERIFIED]
    assert scriptt16.execution_of({"kind": "command", "cmd": "pytest", "exit_code": 0}) == scriptt16.Execution("command", "pytest", 0)
    assert scriptt16.execution_of({"path": "next/agree.py"}).kind == "file_modified" and scriptt16.execution_of({"cmd": "ls", "error": "no such file"}).failed


def real_d1() -> scriptt16.Model | None:
    """Returns the real d1 of .scriptt/config.json, or None if it does not answer."""
    model = lambda state, questions: shipped.put(shipped.d1, state, questions)
    try:
        model("Hello.", {"q": {"type": "boolean", "instructions": "Is this a greeting?"}})
    except OSError:
        return None
    return model


def folder_world() -> agree.World:
    """Loads next/world.py, the world of this folder."""
    return world_of((HERE / "world.py").read_text(), HERE.parent)


def test_execution_check_real_d1():
    """C6 with the real d1, with the reading pinned so that this test measures the check alone; every check question
    goes to the real d1. The acceptance runner (acceptance.criterion_completion) reads the message unpinned."""
    model = real_d1()
    if model is None:
        print("skipped test_execution_check_real_d1: the real d1 does not answer")
        return
    world = folder_world()

    def pinned(state: str, asked: dict[str, dict]) -> dict[str, dict]:
        answers = model(state, asked)
        for key, question in asked.items():
            options = [option["id"] for option in question.get("options", [])]
            if key == "what":
                answers[key] = {"probabilities": {option: float(option == "build") for option in options}}
            elif key == "which":
                named = next(option["id"] for option in question["options"] if "(as named in this phrase)" in option["description"])
                answers[key] = {"probabilities": {option: float(option == named) for option in options}}
        return answers
    reading = scriptt16.read("Build the world. Build the tests.", world, [], pinned, join=False)
    assert terms_of(reading) == ["build(code='the world')", "build(code='the tests')"], terms_of(reading)

    def holds(first: tuple[str, str], second: tuple[str, str]) -> bool:
        """The C6 criterion on the states of the two calls, for the two replies."""
        return first == ("DONE", "OPEN") and second == ("UNVERIFIED", "UNVERIFIED")
    one = scriptt16.check(reading, "I built the world.", model, [{"path": "next/world.py"}])
    both = scriptt16.check(reading, "I built both.", model, [])
    print("  C6 real d1:", [(c.call, c.state.name, c.share, c.evidence) for c in one + both])
    assert holds(tuple(c.state.name for c in one), tuple(c.state.name for c in both)), (one, both)
    # Control: the old check, with the real d1, asks both calls one question (d1 answers it twice, so the shares can
    # differ in the last digit), gives them one state, and the C6 criterion rejects its states.
    sent: list[tuple[str, dict]] = []
    old_one, old_both = old_check(reading, "I built the world.", recorded(model, sent)), old_check(reading, "I built both.", model)
    print("  C6 old check:", old_one + old_both)
    assert len({question["instructions"] for question in sent[0][1].values()}) == 1 and old_one[0][2] == old_one[1][2]
    assert not holds(tuple(state for _, _, state, _ in old_one), tuple(state for _, _, state, _ in old_both))


def test_gate_real_d1():
    """C7 with the real d1: a world.py with redesign deleted (only follow kept) loses "Redesign the mod." and is
    rejected. Control: the old bits-only gate accepts it, because d1 is as sure of the remarks without the other functions."""
    model = real_d1()
    if model is None:
        print("skipped test_gate_real_d1: the real d1 does not answer")
        return
    world, source = folder_world(), (HERE / "world.py").read_text()
    texts = ("Redesign the mod.", "Nice work today.", "Thanks, that looks good.", "Nice.", "OK, thanks!", "Good morning.", "That works for me.", "Follow this rule from now on: no regex.", "Follow this rule: never push without asking.")
    lines = [scriptt16.record(turns.start_turn(text, world, [], model).reading) for text in texts]  # the log holds what the product read
    golden = scriptt16.golden(HERE / "golden.json")
    kept = scriptt16.gate(world, golden, lines, model)
    assert kept.accepted, kept.lost  # the world as it is reads every approved case as approved
    lobotomized = world_of(without_functions(source, kept={"follow"}), HERE.parent)
    decision = scriptt16.gate(lobotomized, golden, lines, model)
    print("  C7 real d1:", decision.accepted, decision.lost[:1], "mean bits", round(decision.mean_bits, 3), "against", round(kept.mean_bits, 3))
    assert not decision.accepted and "'Redesign the mod.' phrase 1: approved redesign(surface='the mod'), now none" in decision.lost, decision.lost
    assert old_gate(lobotomized, lines, model)  # control: the old gate accepts the same world
    # The world with only redesign deleted is rejected too; the old gate rejects it on this log as well (its bits go up).
    assert not scriptt16.gate(world_of(without_functions(source, dropped={"redesign"}), HERE.parent), golden, lines, model).accepted


def test_join_real_d1():
    """The product path (turns.start_turn, join on) with the real d1: a sentence that asks for its own action stays its
    own phrase, and a sentence that only adds detail joins the one before it. Control: the old join wording joins
    "Then show me the mod, redesigned." into "Redesign the mod.", and the gate on golden.json rejects that wording."""
    model = real_d1()
    if model is None:
        print("skipped test_join_real_d1: the real d1 does not answer")
        return
    world = folder_world()
    count = lambda text, prompts=scriptt16.Prompts(): len(scriptt16.innermost(turns.start_turn(text, world, [], model, prompts=prompts).reading.message))
    separate = {"Redesign the mod. Then show me the mod, redesigned. Test the search too.": 3, "Redesign the mod. Then show the original mod.": 2,
                "Build the world. Build the tests.": 2}
    assert {text: count(text) for text in separate} == separate
    assert count("Show the mod. The one in the pane.") == 1  # the second sentence only says which mod
    old = scriptt16.Prompts(join=acceptance.OLD_JOIN)
    assert count("Redesign the mod. Then show me the mod, redesigned. Test the search too.", old) < 3  # control
    golden = scriptt16.golden(HERE / "golden.json")
    assert scriptt16.gate(world, golden, [], model).accepted
    rejected = scriptt16.gate(world, golden, [], model, old)
    print("  join wording: the old wording loses", rejected.lost[:1])
    assert not rejected.accepted and any("Then show me the mod, redesigned. Test the search too.'" in lost for lost in rejected.lost), rejected.lost


def stop_hook_run(checks: dict[str, float], stops: int, block: bool = True) -> list[dict | None]:
    """Drives the Stop hook of the harness on recorded events.

    Args:
        checks: The share of d1 for each demanded function.
        stops: The number of Stop events after the message.
        block: The "block" setting of config.json.

    Returns:
        The answer of the hook to each Stop event.
    """
    with tempfile.TemporaryDirectory() as folder:
        log, config = shipped.LOG, shipped.config
        shipped.LOG, shipped.config = pathlib.Path(folder) / "events.jsonl", lambda: {"block": block}
        try:
            demands = [{"function": name, "words": name, "parameters": {}} for name in checks]
            message = {"form": 3, "event": "UserPromptSubmit", "session": "s", "brand": "Asked", "text": "Build the code. Test the page.", "demands": demands, "parts": [], "pieces": []}
            shipped.LOG.write_text(json.dumps(message) + "\n")

            def ask(state: str, questions: dict) -> dict:
                return {key: {"p_true": next(share for name, share in checks.items() if shipped.FUNCTIONS[name].__doc__ in question["instructions"])} for key, question in questions.items()}
            return [shipped.handle({"hook_event_name": "Stop", "session_id": "s", "last_assistant_message": "Done.", "stop_hook_active": n > 0}, ask) for n in range(stops)]
        finally:
            shipped.LOG, shipped.config = log, config


def test_stop_hook():
    """The Stop hook sends a reply back when it misses any demanded function, at most twice for one message."""
    answers = stop_hook_run({"build": 0.9, "test": 0.1}, 3)
    assert [bool(answer) for answer in answers] == [True, True, False], answers
    assert "test" in answers[0]["reason"] and "build" not in answers[0]["reason"].split("does not do:")[1]
    # Control: the old rule blocked only when the reply did none of them: max(0.9, 0.1) >= 0.5 passes this reply.
    assert not max([0.9, 0.1]) < 0.5
    assert stop_hook_run({"build": 0.9, "test": 0.8}, 1) == [None]  # every demand done: no block
    assert stop_hook_run({"build": 0.9, "test": 0.1}, 1, block=False) == [None]  # "block" off: no block
    # The two copies of the harness are one code: the same syntax tree, apart from docstrings.
    def code(file: pathlib.Path) -> str:
        tree = ast.parse(file.read_text())
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if isinstance(body, list) and body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                node.body = body[1:] or [ast.Pass()]
        return ast.dump(tree)
    assert code(HERE.parent / "scriptt" / "harness.py") == code(HERE.parent / ".scriptt" / "harness.py")


def test_acceptance_checks():
    """Each check function of the acceptance runner holds on a good reading and rejects the broken one, with a stand-in d1."""
    world = folder_world()
    # C1: three clauses, three applications. Controls: one clause marked nothing, and two clauses joined into one phrase.
    told = {"Redesign": "redesign", "Then": "show", "Test": "test"}
    product = lambda text, model: acceptance.product_reading(text, world, model, scriptt16.Limits())  # join on, as the rows read
    reading = product(acceptance.C1_MESSAGE, standin(told))
    assert acceptance.obligations_held(reading)[0], acceptance.obligations_held(reading)
    assert not acceptance.obligations_held(acceptance.marked_nothing(reading, "Test the search too."))[0]
    joined = product(acceptance.C1_MESSAGE, standin(told, yes=(scriptt16.JOIN,)))
    assert len(scriptt16.innermost(joined.message)) == 1 and not acceptance.obligations_held(joined)[0]

    # C2: the original and the version. Control: the old taken_by rule forces the version on "the original mod".
    picks = standin({"Redesign": "redesign", "Then": "show"}, {"Then show the original": "the original", "Then show me": "the result of redesign"})
    both = lambda: tuple(product(text, picks) for text, _ in (acceptance.C2_ORIGINAL, acceptance.C2_VERSION))
    assert acceptance.versions_bound(both())[0], acceptance.versions_bound(both())
    with acceptance.put_back(scriptt16, "derivations", acceptance.taken_by(scriptt16.derivations)):
        broken = both()
    assert not acceptance.versions_bound(broken)[0] and scriptt16.derivations.__name__ == "derivations" and scriptt16.derivations.__module__ == "scriptt16"

    # C3: d1 says yes only for the mod. Control: the old greedy Many takes the page too, and asks d1 nothing.
    compare = lambda: product(acceptance.C3_MESSAGE, standin({"Compare": "compare"}, yes=('"the mod"',)))
    assert acceptance.negation_kept(compare())[0]
    with acceptance.put_back(scriptt16, "solve", acceptance.greedy(scriptt16.solve)):
        assert terms_of(compare()) == ["compare(surfaces=['the mod', 'the page'])"] and not acceptance.negation_kept(compare())[0]

    # C4 and C5 run whole, with their controls, on the stand-in.
    for criterion in (acceptance.criterion_composition(standin({"Summarize": "summarize", "Fetch": "fetch"}), scriptt16.Limits()),
                      acceptance.criterion_round_trip(standin({"Redesign": "redesign", "Show": "show"}, {"Show it.": "the result of redesign"}), scriptt16.Limits())):
        assert criterion.result == acceptance.PASS and criterion.caught_deliberate_failure, criterion
    # C5 with a stand-in that already binds the original mod: the correction changes nothing visible, so the row fails.
    same = acceptance.criterion_round_trip(standin({"Redesign": "redesign", "Show": "show"}, {"Show it.": "the original"}), scriptt16.Limits())
    assert same.result == acceptance.FAIL, same

    # C6 on fixed states: the new states hold; the old check's states (one state for both calls, PROMISED) and a missing call fail.
    calls = list(acceptance.C6_CALLS)
    good = [[(calls[0], "DONE", 0.9), (calls[1], "OPEN", 0.2)], [(call, "UNVERIFIED", 0.9) for call in calls]]
    assert acceptance.completion_states((calls, good))[0]
    assert not acceptance.completion_states((calls, [[(call, "DONE", 0.7) for call in calls], [(call, "DONE", 0.9) for call in calls]]))[0]
    assert not acceptance.completion_states((calls, [[(calls[0], "DONE", 0.9), (calls[1], "PROMISED", 0.2)], good[1]]))[0]
    assert not acceptance.completion_states((["none", calls[1]], [good[0][1:], good[1][1:]]))[0]

    # C7 on fixed gates: rejected with the lost obligation holds; the old gate's acceptance fails, and so does a rejection for another reason.
    gate = lambda accepted, lost: (scriptt16.Gate(accepted, [], lost, 0.3, 21, 0, 1, "w", "p"), "")
    assert acceptance.capability_kept(gate(False, [acceptance.C7_LOST + ", now none"]))[0]
    assert not acceptance.capability_kept(gate(True, []))[0] and not acceptance.capability_kept(gate(False, ["'Nice work today.' phrase 1: approved nothing, now none"]))[0]

    # d1 that does not answer: every row is BLOCKED, never PASS, and the table is not accepted.
    def down(state: str, asked: dict[str, dict]) -> dict[str, dict]:
        raise ConnectionRefusedError("d1 is down")
    blocked = acceptance.run_acceptance(down)
    assert [one.result for one in blocked] == [acceptance.BLOCKED] * 7 and not acceptance.accepted(blocked) and len(acceptance.table(blocked).splitlines()) == 9


def run_acceptance() -> bool:
    """Runs the acceptance criteria C1 to C7 with the real d1 and prints the table.

    Returns:
        True if every row is PASS and caught its deliberate failure.
    """
    criteria = acceptance.run_acceptance()
    print(acceptance.table(criteria))
    return acceptance.accepted(criteria)


if __name__ == "__main__":
    tests = [test_kinds, test_types, test_world_rules, test_grounding, test_synthesis, test_interpretation, test_gate, test_prompts,
             test_notebook_single_source, test_producers, test_versions, test_many_inclusion, test_nested_later, test_depth, test_hole_reasons,
             test_union_kinds, test_provenance, test_real_world, test_context_across_turns, test_decision_records,
             test_corrections_round_trip, test_check_items, test_check_executions, test_stop_hook, test_execution_check_real_d1,
             test_gate_real_d1, test_join_real_d1, test_acceptance_checks]
    for test in tests:
        test()
        print("passed", test.__name__)
    print(len(tests), "tests passed")
    sys.exit(0 if run_acceptance() else 1)
