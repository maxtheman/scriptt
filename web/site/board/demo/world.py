"""The world of this folder: the closed type system that a message is read against.

Every type that the search uses is defined here. ``Many``, ``Maybe`` and
``Later`` are the type constructors of the type system. Python does not evaluate
annotations, so this file names them with no import.
"""

import enum
import pathlib
import typing

Words = typing.NewType("Words", str)
Asked = typing.NewType("Asked", Words)
Written = typing.NewType("Written", Words)
Observed = typing.NewType("Observed", Words)


class Surface(enum.Enum):
    """what the user looks at"""

    PAGE: Asked = "the page"
    SITE: Asked = "the site"
    WEBSITE: Asked = "the website"
    UI: Asked = "the ui"
    MOD: Asked = "the mod"
    PANE: Asked = "the pane"
    VISUALIZATION: Asked = "the visualization"


class Code(enum.Enum):
    """the code of scriptt"""

    HARNESS: Asked = "the harness"
    HOOK: Asked = "the hook"
    SEARCH: Asked = "the search"
    WORLD: Asked = "the world"
    TESTS: Asked = "the tests"
    SKILL: Asked = "the skill"
    NOTEBOOK: Asked = "the notebook"


class Concept(enum.Enum):
    """an idea of the type system: a type, a hole, a function, a constructor, a brand, a kind or a term"""

    TYPE: Asked = "type"
    TYPES: Asked = "types"
    HOLE: Asked = "hole"
    HOLES: Asked = "holes"
    FUNCTION: Asked = "function"
    FUNCTIONS: Asked = "functions"
    CONSTRUCTOR: Asked = "constructor"
    CONSTRUCTORS: Asked = "constructors"
    BRAND: Asked = "brand"
    KIND: Asked = "kind"
    TERM: Asked = "term"
    PRODUCT: Asked = "product"
    SUM: Asked = "sum"
    NEWTYPE: Asked = "newtype"
    SIGNATURE: Asked = "signature"


class Text(enum.Enum):
    """a piece of the conversation's text: a message, a phrase, a sentence, a word or a pasted reply"""

    MESSAGE: Asked = "the message"
    PHRASE: Asked = "the phrase"
    SENTENCE: Asked = "the sentence"
    TEXT: Asked = "the text"
    WORDS: Asked = "the words"
    REPLY: Asked = "the reply"
    PASTED: Asked = "pasted"


class Agent(enum.Enum):
    """who does the work: an agent, a model, a session or a person"""

    CLAUDE: Asked = "claude"
    D1: Asked = "d1"
    SPARK: Asked = "spark"
    AGENT: Asked = "the agent"
    SESSION: Asked = "the session"
    SUBAGENT: Asked = "a sub agent"
    MODEL: Asked = "the model"
    ENGINEER: Asked = "engineer"


class Step(enum.Enum):
    """a step of reading a message: grounding, synthesis, folding, unfolding, typing or choosing"""

    GROUNDING: Asked = "grounding"
    SYNTHESIS: Asked = "synthesis"
    UNFOLD: Asked = "unfold"
    FOLD: Asked = "fold"
    TYPING: Asked = "typing"
    COMPOSITION: Asked = "composition"


class Verdict(enum.Enum):
    """how something went or reads: it works, or it is wrong, vague, confusing or missing"""

    WORKS: Asked = "works"
    WRONG: Asked = "wrong"
    VAGUE: Asked = "vague"
    CONFUSED: Asked = "confused"
    MISSING: Asked = "missing"


class Time(enum.Enum):
    """when something happens or how long it takes"""

    NOW: Asked = "now"
    TODAY: Asked = "today"
    LATER: Asked = "later"
    BEFORE: Asked = "before"
    NEXT: Asked = "next"


type Subject = Surface | Code | pathlib.Path


def explain(subject: Maybe[Words]) -> Written:
    """explain or answer something: say why, how or what, or confirm or deny it"""


def research(topic: Words) -> Many[Observed]:
    """look something up, or find inspiration or sources"""


def redesign(surface: Surface) -> Later[Surface]:
    """change how the page or the interface looks, or how its information is ordered"""


def build(code: Code) -> Later[Code]:
    """write or change code"""


def release(version: Maybe[Words]) -> Later[Words]:
    """release, deploy, push, tag, or change a version number"""


def delegate(helper: Words) -> Later[Written]:
    """have another agent, a sub agent or a new session do part of the work"""


def show(subject: Subject) -> Subject:
    """show or open something so that the user can see it"""


def test(subject: Subject) -> Observed:
    """test or verify that something works"""


def follow(rule: Asked) -> None:
    """follow a rule about how to work or what to avoid, from now on"""


def save(path: Maybe[pathlib.Path]) -> pathlib.Path:
    """save or store data so that it can be found later"""


def propose(idea: Words) -> Later[Asked]:
    """propose an idea and wait for the user's yes or no"""
