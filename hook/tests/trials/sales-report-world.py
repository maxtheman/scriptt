"""THE WORLD for the sales-report folder: the whitelist. A message can demand only what is in this file.

- A sum type (an Enum) is a fixed list of things that exist and have a name. Its docstring says what they are.
- A product type (a dataclass) is several things at once. Each field is a hole of its own.
- A function is a computation that a message can demand. Its docstring is the question that d1 answers:
  "Does the message ask the reader to <docstring>?" Each parameter is a hole that the message must fill.
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


class Region(enum.Enum):
    """the sales regions"""

    NORTH = "north"
    SOUTH = "south"
    EAST = "east"
    WEST = "west"


class Product(enum.Enum):
    """the products that are sold"""

    DESK = "desk"
    CHAIR = "chair"
    LAMP = "lamp"
    SHELF = "shelf"


class Grouping(enum.Enum):
    """the ways to group revenue"""

    BY_MONTH = "by month"
    BY_REGION = "by region"
    BY_PRODUCT = "by product"


class Artifact(enum.Enum):
    """the files of this project"""

    SALES = "sales.csv"
    SCRIPT = "report.py"
    REPORT = "report.md"
    REJECTS = "the bad rows"


@dataclasses.dataclass(frozen=True)
class Slice:
    """a slice of the sales: a region, a product, or both"""

    region: Region | None = None
    product: Product | None = None


def find_bad_rows(path: pathlib.Path) -> list:
    """find the bad rows in the sales file and say why each is bad"""


def sum_revenue(grouping: Grouping, only: Slice | None = None) -> dict:
    """sum the revenue (units times unit price) of the good rows, grouped"""


def write_report(path: pathlib.Path) -> pathlib.Path:
    """write or rebuild the report file"""


def verify(what: str) -> bool:
    """check the numbers by a second method"""


def show(artifact: Artifact) -> str:
    """show, print or read out a file of the project"""


def explain() -> str:
    """explain something, or say why, how or what"""


def answer() -> bool:
    """confirm or deny something, with a yes or a no"""


def write_interview(path: pathlib.Path) -> pathlib.Path:
    """write the interview, the feedback on scriptt"""


def extend(what: str) -> None:
    """add classes or functions to the world"""
