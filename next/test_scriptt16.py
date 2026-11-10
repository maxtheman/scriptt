"""Tests of agree.py and scriptt16.py with a stand-in d1.

Each test sets the answers of d1, so the tests check the type system and the
rules of the search. They do not measure the real d1.

    python3.14 next/test_scriptt16.py
"""

import pathlib
import sys
import tempfile
import types

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / ".scriptt")]
import agree
import scriptt16

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
            wanted = next((choice for start, choice in table.items() if state.startswith(start)), None)
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
    world = world_of(WORLD + '\nclass Colour(enum.Enum):\n    "a colour"\n    RED: Asked = "red"\n\ndef paint(surface: Surface) -> Later[Surface]:\n    "paint it"\n\ndef tint(colour: Colour) -> Written:\n    "tint it"\n')
    assert any("paint: the same parameter types and result type as redesign" in fault for fault in world.faults), world.faults
    assert any("Colour: 1 function uses this type (tint), and a custom type needs 2" in fault for fault in world.faults), world.faults
    same = world_of(WORLD + '\nclass Pair(typing.NamedTuple):\n    "a pair"\n    notebook: pathlib.Path\n    number: int\n')
    assert any("Pair: the same structure as Cell" in fault for fault in same.faults), same.faults


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
    assert terms_of(reading) == ["show(subject='the mod')"] and offered == ["'the mod'", "redesign(surface=...)", "the text names none of these"]
    # Function application inside one phrase: d1 chooses the application, and its parameter takes the constant.
    assert terms_of(read("Show me the mod, redesigned.", standin({"Show": "show"}, {"Show": "redesign(surface=...)"}))) == ["show(subject=redesign(surface='the mod'))"]

    # Function application across phrases. The earlier term is the current version of the mod, so a later mention of
    # the mod, by name or by "it", takes that term. d1 gets no question about the hole.
    for second in ("Then show the mod.", "Then show it."):
        reading = read("Redesign the mod. " + second, standin({"Redesign": "redesign", "Then": "show"}))
        assert terms_of(reading) == ["redesign(surface='the mod')", "show(subject=redesign(surface='the mod'))"] and len(reading.requests) == 2
        assert agree.show(scriptt16.type_of(scriptt16.innermost(reading.message)[1].term)) == "Later[Subject]"  # a term with a Later argument is Later

    # Many: the hole takes every term of its type that the phrase gives.
    assert terms_of(read("Compare the page and the mod.", standin({"Compare": "compare"}))) == ["compare(surfaces=['the page', 'the mod'])"]
    # Many: the phrase gives none, so d1 answers yes or no for each earlier term.
    assert terms_of(read("Look at the page and the mod. Compare them.", standin({"Compare": "compare"}, yes=("the page", "the mod")))) == ["nothing", "compare(surfaces=['the mod', 'the page'])"]

    # d1 chooses none: the hole stays open. d1 abstains on the function: the phrase has no term.
    reading = read("Show the mod and the page.", standin({"Show": "show"}))
    assert terms_of(reading) == ["show(subject=...)"] and scriptt16.holes_of(scriptt16.innermost(reading.message)[0].term)[0][0] == "subject"
    assert terms_of(read("Email my accountant.", standin({"Email": "none"}))) == ["none"]
    # Sum of members with no constant in the message: d1 chooses a member, or none.
    assert terms_of(read("Redesign what I look at in the app.", standin({"Redesign": "redesign"}, {"Redesign": "the mod"}))) == ["redesign(surface='the mod')"]
    assert terms_of(read("Redesign it.", standin({"Redesign": "redesign"}))) == ["redesign(surface=...)"]

    # Brand: a hole of type Asked takes the words of the user, and the subtype rule excludes a quote of a reply.
    reply = "Until then I use only these ten words, each in its own exact sense."
    reading = read('"I use only these ten words, each in its own exact sense." Keep to that from now on.', standin({"Keep": "follow"}), [reply])
    assert terms_of(reading)[1] == "follow(rule='Keep to that from now on.')" and len(reading.requests) == 1
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
        reading = scriptt16.read("Review cell 3 of notes.md.", there, [], standin({"Review": "review"}), join=False)
        assert terms_of(reading) == ["review(review=Review(cell=Cell(notebook='notes.md', number='3'), evidence=['Review cell 3 of notes.md.']))"]
        # Sum of types: terms of two alternatives are at hand, so d1 chooses among the terms themselves.
        reading = scriptt16.read("Show notes.md, not the mod.", there, [], standin({"Show": "show"}, {"Show": "notes.md"}), join=False)
        offered = [option["description"] for option in reading.requests[1]["asked"]["which"]["options"]]
        assert terms_of(reading) == ["show(subject='notes.md')"] and offered[:2] == ["'notes.md'", "'the mod'"], offered
        # Sum of types, in the world of this folder: the phrase names a Code and an earlier phrase a Surface. The Code is offered as a term.
        reading = scriptt16.read("Redesign the mod. Test the search too.", world_of((HERE / "world.py").read_text()), [], standin({"Redesign": "redesign", "Test": "test"}, {"Test": "the search"}), join=False)
        assert terms_of(reading) == ["redesign(surface='the mod')", "test(subject='the search')"], terms_of(reading)
        # Sum of two products: d1 chooses the alternative, and the fields of that product become holes.
        either = world_of(WORLD + '\nclass File(typing.NamedTuple):\n    "a file"\n    path: pathlib.Path\n\ntype Target = File | Cell\n\ndef inspect_target(target: Target) -> Observed:\n    "inspect a file or a cell"\n\ndef open_file(file: File) -> Observed:\n    "open a file"\n', pathlib.Path(folder))
        reading = scriptt16.read("Inspect cell 3 of notes.md.", either, [], standin({"Inspect": "inspect_target"}, {"Inspect": "a cell of a notebook"}), join=False)
        assert terms_of(reading) == ["inspect_target(target=Cell(notebook='notes.md', number='3'))"], terms_of(reading)

    # A world with a fault, or with a parameter that no span can fill, is refused.
    for faulty in (WORLD + '\ndef paint(surface: Surface) -> Later[Surface]:\n    "paint it"\n', WORLD + '\nVersion = typing.NewType("Version", str)\n\ndef release(version: Version) -> Later[Words]:\n    "release it"\n'):
        try:
            scriptt16.read("Show the mod.", world_of(faulty), [], standin({}), join=False)
            raise AssertionError("the search ran on a world with a fault")
        except ValueError as refusal:
            assert "paint" in str(refusal) or "release.version: no span of a message can have the type Version" in str(refusal)


def test_interpretation():
    world = world_of(WORLD)
    reading = scriptt16.read("Redesign the mod. Compare the page and the mod. Then show the docs. Thanks.", world, [], standin({"Redesign": "redesign", "Compare": "compare", "Then": "show"}), join=False)
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
        "3. show.subject: Subject",
    ]
    checked = scriptt16.check(reading, "I compared the page. Nothing else yet.", standin({}, yes=("compare several of them: 'the page'",)))
    assert [(one.function, one.item, one.state) for one in checked] == [
        ("redesign", None, scriptt16.State.PROMISED),
        ("compare", "'the page'", scriptt16.State.DONE),
        ("compare", "'the mod'", scriptt16.State.OPEN),
        ("show", None, scriptt16.State.OPEN),
    ]


def test_gate():
    world = world_of(WORLD)
    sure = standin({"Redesign": "redesign", "Follow": "follow"})
    lines = [scriptt16.record(scriptt16.read(text, world, [], sure, join=False)) for text in ("Redesign the mod. Thanks.", "Follow this rule.")]
    assert all(line["decisions"] for line in lines) and scriptt16.recorded_phrases(lines[0], world).inside[1].start == 18  # the log has every answer and every phrase

    def counting(model: scriptt16.Model, count: list[int]) -> scriptt16.Model:
        def counted(state: str, asked: dict[str, dict]) -> dict[str, dict]:
            count.append(len(asked))
            return model(state, asked)
        return counted

    def split(state: str, asked: dict[str, dict]) -> dict[str, dict]:
        """A d1 that divides its shares evenly when the world has a function named paint."""
        answers = sure(state, asked)
        for key, question in asked.items():
            options = [option["id"] for option in question.get("options", [])]
            if "paint" in options:
                answers[key] = {"probabilities": {option: 1 / len(options) for option in options}}
        return answers

    # A change that adds a fault is rejected, and d1 is not asked.
    asked: list[int] = []
    decision = scriptt16.gate(world_of(WORLD + '\ndef paint(surface: Surface) -> Later[Surface]:\n    "paint it"\n'), lines, counting(sure, asked))
    assert not decision.accepted and decision.proposed_bits is None and "paint" in decision.faults[0] and asked == []
    # A change that makes d1 split its shares is rejected. The same change is accepted if d1 stays as sure.
    wider = world_of(WORLD + '\ndef paint(surface: Surface) -> Observed:\n    "paint it"\n')
    rejected = scriptt16.gate(wider, lines, split)
    assert not rejected.accepted and rejected.proposed_bits > rejected.current_bits
    asked = []
    assert scriptt16.gate(wider, lines, counting(sure, asked)).accepted
    assert len(asked) == 3  # one function choice for each of the 3 phrases: the current world is not run again, and no join is asked


if __name__ == "__main__":
    tests = [test_kinds, test_types, test_world_rules, test_grounding, test_synthesis, test_interpretation, test_gate]
    for test in tests:
        test()
        print("passed", test.__name__)
    print(len(tests), "tests passed")
