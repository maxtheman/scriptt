"""THE WORLD: the whitelist. A message can demand only what is in this file. Edit it to fit your work.

- A sum type (an Enum) is a fixed list of things that exist and have a name. Its docstring says what they are.
- A product type (a dataclass) is several things at once. Each field is a hole of its own.
- A function is a computation that a message can demand. Its docstring is the question that d1 answers:
  "Does the message ask the reader to <docstring>?" Each parameter is a hole that the message must fill.
  A parameter can be a sum type, a product type, a built-in (str, int, bool, pathlib.Path), or a union of these.
  The bodies are not written: the reader of the message does the work.

How a hole is filled, by its type:
  a sum type   the member whose name the words contain (code). If none: d1 answers yes or no for each member.
  int, Path    the first number or path in the words (code).
  str          the words that d1 points at.
  bool         d1 answers yes or no.
A hole that nothing fills stays open, and Claude is told.
"""

import dataclasses
import enum
import pathlib


class Notebook(enum.Enum):
    """the notebook, or cells of it"""

    OLD_CELLS = "the old cells"
    THESE_CELLS = "these cells"
    THIS = "this notebook"
    WHOLE = "this whole notebook"
    VERSION = "this version"


class Code(enum.Enum):
    """code: a program, a function, a lambda, a template"""

    FUNCTIONS = "the functions"
    T_STRINGS = "t-strings"
    T_STRINGS_SPOKEN = "t strings"
    TEMPLATE = "the template"


class Types(enum.Enum):
    """types or classes that the code defines"""

    RESULT_TYPES = "result types"
    RESULT_TYPE = "the type of the result"
    DEMAND = "demand"
    ROLES = "the roles"
    CLASSES = "classes"
    TYPES = "the types"


class Questions(enum.Enum):
    """the questions that are sent to d1"""

    ALL_TEN = "all ten of these"


class Concepts(enum.Enum):
    """concepts of computer science"""

    CS = "the computer science concepts"


class Model(enum.Enum):
    """the d1 model"""

    D1 = "d1"
    THE_MODEL = "the model"
    THIS_MODEL = "this model"


@dataclasses.dataclass(frozen=True)
class Change:
    """a change of the notebook: which cells, and the code to put there"""

    notebook: Notebook
    code: Code


def explain() -> str:
    """explain something, or say why, how or what"""


def restate(questions: Questions, concepts: Concepts) -> str:
    """restate something in other terms"""


def answer() -> bool:
    """confirm or deny something, with a yes or a no"""


def implement(questions: Questions, cells: int | None = None) -> Notebook:
    """implement something in the notebook"""


def delete(notebook: Notebook) -> Notebook:
    """delete or get rid of cells of the notebook"""


def rewrite(change: Change) -> Notebook:
    """rewrite the notebook or a cell of it"""


def mock(model: Model) -> Model:
    """mock the d1 model"""


def solve(types: Types) -> Code:
    """write or change code"""


def write(path: pathlib.Path) -> pathlib.Path:
    """write a file"""


def extend(what: str) -> None:
    """add classes or functions to the world"""
