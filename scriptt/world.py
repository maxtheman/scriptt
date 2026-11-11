"""The world of this folder: the closed type system that each message to Claude here is read against. Edit it to fit your work.

- A brand (``typing.NewType``) is text with who produced it. ``Asked`` (the user's words) and ``Written`` (a reply's
  words) must stay: the reader uses them. ``Observed`` is text that a run of code produced.
- A sum type (an ``Enum``) lists the named things of this folder. Each member's value is the words that name it in a
  message, and its annotation is the brand of those words (``Asked``).
- A union (``type Subject = Part | pathlib.Path``) is one of several types.
- A product type (a dataclass, a ``NamedTuple``, a ``TypedDict``) is several values at once.
- A function is something a message can ask for. d1 reads its docstring as the rest of "The text asks the reader to ...".
  Each parameter is a hole, filled by a value of its type from the message or the result of an earlier request.
- ``Many[T]`` is several values, ``Maybe[T]`` a value or a deliberate absence, ``Later[T]`` a value that waits on work
  not done yet. They need no import.
- A ``pathlib.Path`` is a path that the message names and that exists in this folder; an ``int`` is digits.

At the end of a turn the harness checks each request (see harness.py). Work needs evidence from the transcript: one
that binds a path takes the writes of that file and the commands that name it; one whose result holds ``Observed``
takes the commands run; one whose result is a ``Path`` or ``Later`` of no text (``Later[Subject]``) takes the files
written. A result that is words (``Written``, ``Words``) or ``None`` is judged by d1 against the reply: a judgment, not
execution evidence.
Keep it small: the 5 to 10 things that the user really asks for in this folder.
"""

import enum
import pathlib
import typing

Words = typing.NewType("Words", str)
Asked = typing.NewType("Asked", Words)
Written = typing.NewType("Written", Words)
Observed = typing.NewType("Observed", Words)


class Part(enum.Enum):
    """a part of this project"""

    CODE: Asked = "the code"
    TESTS: Asked = "the tests"
    DOCS: Asked = "the docs"
    PAGE: Asked = "the page"


type Subject = Part | pathlib.Path


def explain(subject: Maybe[Words]) -> Written:
    """explain or answer something: say why, how or what, or confirm or deny it"""


def research(topic: Words) -> Many[Observed]:
    """look something up, or find inspiration or sources"""


def change(subject: Subject) -> Later[Subject]:
    """write or change code, a file or a page"""


def test(subject: Subject) -> Observed:
    """test or verify that something works"""


def show(subject: Subject) -> Subject:
    """show or open something so that the user can see it"""


def save(path: Maybe[pathlib.Path]) -> pathlib.Path:
    """save or store data so that it can be found later"""


def follow(rule: Asked) -> None:
    """follow a rule about how to work or what to avoid, from now on"""


def propose(idea: Words) -> Later[Asked]:
    """propose an idea and wait for the user's yes or no"""
