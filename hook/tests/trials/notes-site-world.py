"""THE WORLD of notes-site: a folder of short markdown notes (notes/*.md, each with a title line and a Tags: line)
that build.py turns into a static index.html.

- A sum type (an Enum) is a fixed list of things that exist and have a name.
- A function is something a message can demand. Its docstring completes: "Does the message ask the reader to <docstring>?"
  Each parameter is a hole that the message must fill. The bodies are not written: the reader of the message does the work.
"""

import enum
import pathlib


class Note(enum.Enum):
    """one of the notes in notes/"""

    BIKE_CHAIN = "bike chain"
    COFFEE = "coffee"
    COMPOST = "compost"
    KNOTS = "knots"
    SOURDOUGH = "sourdough"
    TOMATOES = "tomatoes"
    SHARPENING_KNIVES = "sharpening knives"
    PATCHING_A_TYRE = "patching a tyre"
    OILING_A_CHAIN = "oiling a chain"


class Tag(enum.Enum):
    """a tag that a note carries on its Tags: line"""

    BIKE = "bike"
    REPAIR = "repair"
    KITCHEN = "kitchen"
    DRINK = "drink"
    GARDEN = "garden"
    SOIL = "soil"
    CAMPING = "camping"
    ROPE = "rope"
    BREAD = "bread"
    VEGETABLES = "vegetables"


class Output(enum.Enum):
    """a file that build.py makes"""

    INDEX = "index.html"


def build_site() -> pathlib.Path:
    """build or rebuild index.html from the notes with build.py"""


def add_note(title: str, tags: str) -> Note:
    """add a new note to notes/ with a title and tags"""


def edit_note(note: Note) -> Note:
    """edit or rewrite the text of a note"""


def delete_note(note: Note) -> Note:
    """delete or remove a note"""


def tag_note(note: Note, tag: Tag) -> Note:
    """put a tag on a note, or take it off"""


def list_notes(tag: Tag | None = None) -> list[Note]:
    """list or show the notes, perhaps only those with a tag"""


def check_page(output: Output) -> bool:
    """check the built page by reading its HTML: the list, the tags, the filter box"""


def change_page(what: str) -> Output:
    """change how the page looks or behaves: the filter, the tag clicks, the style"""


def write_file(path: pathlib.Path) -> pathlib.Path:
    """write a file that is not a note, such as a report or an interview"""


def export_notes(path: pathlib.Path | None = None) -> pathlib.Path:
    """export all the notes as one zip file"""
