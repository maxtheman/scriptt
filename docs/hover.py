"""Hover text for the code blocks of the pages, as an IDE shows it: the signature or the
type
of each name, the first sentence of its docstring, and the file and line that define it.

jedi reads each file as an editor does (static analysis, no run). The build calls
`block(path, text)` for each code block it puts into a page, and writes `hover.json`:

    {"tips": [text, ...], "blocks": {key: [[line, column, length, tip], ...]}}

`key(text)` names a block by its text, so the site (assets/hover.js) and the notebook
find the tips of a block from the code that they show. Lines and columns count from 0.
"""

import functools
import io
import keyword
import re
import tokenize
from pathlib import Path

import jedi
from jedi.api.classes import Name

ROOT = Path(__file__).resolve().parents[1]
PROJECT = jedi.Project(ROOT)
TIPS: list[str] = []
BLOCKS: dict[str, list[list[int]]] = {}


def key(text: str) -> str:
    """FNV-1a (32 bit) over the UTF-16 code units of the text, as JavaScript reads a
    string."""
    value = 0x811C9DC5
    data = text.rstrip().encode("utf-16-le")
    for i in range(0, len(data), 2):
        value = (
            (value ^ int.from_bytes(data[i : i + 2], "little")) * 0x01000193
        ) & 0xFFFFFFFF
    return f"{value:08x}"


def _first_sentence(doc: str) -> str:
    text = " ".join(doc.strip().split("\n\n")[0].split())
    found = re.match(r"(.+?[.!?])(\s|$)", text)
    sentence = found.group(1) if found else text
    return sentence if len(sentence) <= 200 else sentence[:197] + "..."


def _where(name: Name) -> str:
    if name.module_path is None or name.line is None or name.in_builtin_module():
        return ""
    path = Path(name.module_path)
    shown = path.relative_to(ROOT) if path.is_relative_to(ROOT) else Path(path.name)
    return f"defined in {shown}:{name.line}"


def _tip(script: jedi.Script, word: str, line: int, column: int) -> str:
    """The hover text of the name at (line, column), or "" for a builtin or an unknown
    name."""
    found = script.infer(line, column)
    if not found or found[0].in_builtin_module():
        return ""
    thing = found[0]
    signatures = thing.get_signatures()
    if thing.type in ("function", "class") and signatures:
        owner = thing.full_name.rsplit(".", 2)[-2] if thing.type == "function" else ""
        head = (
            ("class " if thing.type == "class" else "")
            + (f"{owner}." if owner and owner[0].isupper() else "")
            + signatures[0].to_string()
        )
    elif thing.type == "module":
        head = f"module {thing.full_name}"
    elif thing.type == "instance" and thing.name == word:  # an enum member
        head = thing.full_name.removeprefix(f"{thing.module_name}.")
    elif thing.type == "instance":
        head = f"{word}: {thing.name}"
    else:
        head = f"{word}: {thing.type}"
    lines = [head, _first_sentence(thing.docstring(raw=True))]
    defined = script.goto(line, column, follow_imports=True)
    if defined:
        lines.append(_where(defined[0]))
    return "\n".join(part for part in lines if part)


@functools.cache
def _file(path: Path, text: str) -> dict[tuple[int, int], tuple[int, str]]:
    """Each name of a file at its (line, column), counted from 1 and 0, with its hover
    text."""
    script = jedi.Script(text, path=path, project=PROJECT)
    out: dict[tuple[int, int], tuple[int, str]] = {}
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type != tokenize.NAME or keyword.iskeyword(token.string):
            continue
        line, column = token.start
        try:
            tip = _tip(script, token.string, line, column)
        except AttributeError, TypeError, ValueError:
            # jedi cannot read every place in a t-string: that name gets no tip
            continue
        if tip:
            out[(line, column)] = (len(token.string), tip)
    return out


def block(path: Path, text: str) -> None:
    """Record the tips of 1 code block: `text` is a part of the file at `path`."""
    whole = path.read_text()
    first = (
        whole[: whole.index(text)].count("\n") + 1
    )  # the file line of the block's line 0
    last = first + text.count("\n")
    rows = []
    for (line, column), (length, tip) in sorted(_file(path, whole).items()):
        if first <= line <= last:
            if tip not in INDEX:
                INDEX[tip] = len(TIPS)
                TIPS.append(tip)
            rows.append([line - first, column, length, INDEX[tip]])
    BLOCKS[key(text)] = rows


INDEX: dict[str, int] = {}
