"""Build the documentation pages: run every example and case, then put their code, their
output and a diagram of
their types into the pages. Output: docs/_build/*.md.

Directives in a page:
    --8<-- "docs/examples/quickstart.py:declare"   a marked section of a file   (#
    [start:declare] ... # [end:declare])
    --8<-- "docs/examples/todo.py"                  a whole file
    --8<-- "output:quickstart/on"                   the output of an example up to the
    line `@@on`
    --8<-- "types:docs/examples/todo.py"            a Mermaid class diagram of the types
    in a file
    --8<-- "md:CHANGELOG.md"                        a Markdown file as it is
"""

import annotationlib
import enum
import importlib
import importlib.util
import inspect
import json
import re
import subprocess
import sys
import types
from pathlib import Path

from scriptt.world import Fact, diagram

from docs import hover

ROOT = Path(__file__).resolve().parents[1]
PAGES, BUILD = ROOT / "docs" / "pages", ROOT / "docs" / "_build"


def run(path: Path) -> str:
    module = ".".join(path.relative_to(ROOT).with_suffix("").parts)
    done = subprocess.run(
        [sys.executable, "-m", module], cwd=ROOT, capture_output=True, text=True
    )
    if done.returncode != 0:
        raise SystemExit(f"{path} failed:\n{done.stderr[-3000:]}")
    return done.stdout


for example in sorted(
    (ROOT / "docs" / "examples").glob("*.py")
):  # every shown section has an end
    text = example.read_text()
    for name in re.findall(r"^# \[start:(\w+)\]$", text, flags=re.M):
        if f"# [end:{name}]" not in text:
            raise SystemExit(
                f"{example.name}: section {name!r} has no '# [end:{name}]'"
            )

OUTPUT: dict[str, str] = {}
for example in sorted((ROOT / "docs" / "examples").glob("*.py")):
    text, start = run(example), 0
    for match in re.finditer(r"^@@(\w+)\n", text, flags=re.M):
        OUTPUT[f"{example.stem}/{match.group(1)}"] = text[
            start : match.start()
        ].rstrip()
        start = match.end()
# `sql` on every type of every example world, so a type that DuckDB cannot keep stops
# the build (the pages show sql on 1 type).
SQL_CHECK = """
import importlib, sys
from scriptt.world import Fact, World
example = importlib.import_module(sys.argv[1])
worlds = [v for v in vars(example).values() if isinstance(v, World)]
kinds = [v for v in vars(example).values() if isinstance(v, type)
         and issubclass(v, Fact) and v is not Fact and v.__module__ == example.__name__]
for world in worlds:
    for kind in kinds:
        if kind in world._types.values():
            world.sql(t"FROM {kind} SELECT count() AS n")
"""
for example in sorted((ROOT / "docs" / "examples").glob("*.py")):
    if example.stem != "__init__":
        done = subprocess.run(
            [sys.executable, "-c", SQL_CHECK, f"docs.examples.{example.stem}"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if done.returncode != 0:
            raise SystemExit(
                f"sql() fails on docs/examples/{example.name}:\n{done.stderr[-2000:]}"
            )


def types_diagram(path: Path) -> str:
    """The `diagram` of the Fact types declared in a file (keys, `Ref` arrows,
    subtypes), as a Mermaid block."""
    module = importlib.import_module(
        ".".join(path.relative_to(ROOT).with_suffix("").parts)
    )
    kinds = [
        v
        for v in vars(module).values()
        if isinstance(v, type)
        and issubclass(v, Fact)
        and v is not Fact
        and v.__module__ == module.__name__
    ]
    return "```mermaid\n" + diagram(*kinds) + "\n```"


def _valid(name: str, spec: dict) -> None:
    """Stop the build if a chart is not valid Vega-Lite: Altair (from
    scriptt-charts[altair]) checks it against the schema."""
    import altair as alt

    kind = next((k for k in ("vconcat", "hconcat", "layer") if k in spec), "")
    try:
        {
            "vconcat": alt.VConcatChart,
            "hconcat": alt.HConcatChart,
            "layer": alt.LayerChart,
        }.get(kind, alt.Chart).from_dict(spec).to_dict()
    except Exception as error:
        raise SystemExit(
            f"{name}: the chart is not valid Vega-Lite: {str(error)[:600]}"
        ) from None


def indented(match: re.Match) -> str:
    """An include inside a note (`??? note`) is indented as deep as its line, so it
    stays inside the note."""
    pad, target = match.group(1), match.group(2)
    text = include(re.match(r"(.*)", target))  # type: ignore[arg-type]
    return "\n".join(pad + line if line else line for line in text.splitlines())


def include(match: re.Match) -> str:
    target = match.group(1)
    if target.startswith("output:"):
        return "```text\n" + OUTPUT[target.removeprefix("output:")] + "\n```"
    if target.startswith(
        "chart:"
    ):  # an example printed a chart: Vega-Lite JSON, or Mermaid text from a real run
        text = OUTPUT[target.removeprefix("chart:")]
        if text.lstrip().startswith("{"):
            _valid(target, json.loads(text))
            return "```vega-lite\n" + text + "\n```"
        return "```mermaid\n" + text + "\n```"
    if target.startswith(
        "vega:"
    ):  # an example printed chart.json() at @@name and chart.table() at @@name_table
        name = target.removeprefix("vega:")
        try:
            spec = json.loads(OUTPUT[name])
        except json.JSONDecodeError as error:
            raise SystemExit(
                f"{name}: the output is not 1 Vega-Lite spec ({error}); print only "
                f"chart.json() in the section"
            )
        _valid(name, spec)
        table = "\n".join(
            "    " + line
            for line in ("```text\n" + OUTPUT[name + "_table"] + "\n```").splitlines()
        )
        return (
            "```vega-lite\n"
            + OUTPUT[name]
            + '\n```\n\n??? note "The data of this chart"\n'
            + table
        )
    if target.startswith("types:"):
        return types_diagram(ROOT / target.removeprefix("types:"))
    if target.startswith("md:"):  # a Markdown file as it is, such as CHANGELOG.md
        return (ROOT / target.removeprefix("md:")).read_text()
    path, _, section = target.partition(":")
    text = (ROOT / path).read_text()
    if section:
        text = text.split(f"# [start:{section}]\n")[1].split(f"# [end:{section}]")[0]
    hover.block(ROOT / path, text)
    return "```python\n" + text.rstrip() + "\n```"


NAV = (ROOT / "docs" / "mkdocs.yml").read_text().split("\nnav:\n")[1]
NAV_FILES = re.findall(
    r"^\s+- (?:[^:\n]+: )?(\S+\.md)\s*$", NAV, flags=re.M
)  # every page of the site, in order
NAV_PAGES = [
    f for f in NAV_FILES if not f.startswith("reference/")
]  # a page in docs/pages that the nav does not list is not built

FILLER = (
    "simply",
    "just",
    "basically",
    "of course",
    "escape hatch",
    "this page runs",
    "everything on these pages runs",
)
ALLOWED = ("mental model",)  # a page name that holds a banned word


def stem_pattern(word: str) -> str:
    """A regex for a word, its stems (plural, past tense, -ing) and its hyphen or space
    variants: `valid time` also gives `valid-time`."""
    *first, last = word.lower().split()
    if last.endswith("y"):
        ending = re.escape(last[:-1]) + "(?:y|ies)"
    else:
        base = next(
            (
                last[: -len(suffix)]
                for suffix in ("ing", "ed", "es", "s", "e")
                if last.endswith(suffix) and len(last) > len(suffix) + 3
            ),
            last,
        )
        ending = re.escape(base) + "(?:s|es|ed|ing|e|d)?"
    return r"\b" + "".join(re.escape(w) + r"[\s-]+" for w in first) + ending + r"\b"


def banned_words() -> dict[str, re.Pattern]:
    """The words of the "Do not use" column of the term table in docs/STYLE.md. A word
    that is also a term (`entry`) is allowed."""
    rows = [
        [c.strip() for c in line.strip().strip("|").split("|")]
        for line in (ROOT / "docs" / "STYLE.md").read_text().splitlines()
        if line.startswith("|")
    ]
    rows = [
        r for r in rows if len(r) == 3 and r[0] != "Term" and not set(r[0]) <= {"-"}
    ]
    terms = {r[0].lower() for r in rows}
    words = [
        re.sub(r"\s*\(.*\)", "", item).strip().lower()
        for r in rows
        for item in r[2].split(",")
    ]
    return {
        w: re.compile(stem_pattern(w), re.I) for w in words if w and w not in terms
    } | {w: re.compile(stem_pattern(w), re.I) for w in FILLER}


BANNED = banned_words()


def prose_of(text: str) -> str:
    """The text a reader reads: no code blocks, no code spans, no link targets, no
    directives."""
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", "", text)
    text = re.sub(r"\]\([^)]*\)", "]", text)
    text = "\n".join(
        line for line in text.splitlines() if not line.startswith("--8<--")
    )
    for phrase in ALLOWED:
        text = re.sub(phrase, "", text, flags=re.I)
    return text


def style(text: str) -> tuple[float, list[str], list[str]]:
    """The share of sentences with 25 words or fewer (table cells and bullets count),
    the long sentences, and the banned words used."""
    prose = prose_of(text)
    pieces: list[str] = []
    for line in prose.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "!!!", "???", "|--", "|:--")):
            continue
        if stripped.startswith("|"):
            pieces += [c.strip() for c in stripped.strip("|").split("|")]
        else:
            pieces.append(re.sub(r"^(?:[-*]|\d+\.)\s+", "", stripped))
    sentences = [
        s
        for s in re.split(
            r"(?<=[.!?])\s+",
            " ".join(p if p.endswith((".", "!", "?")) else p + "." for p in pieces),
        )
        if len(s.split()) > 2
    ]
    long = [s for s in sentences if len(s.split()) > 25]
    heads = "\n".join(l for l in prose.splitlines() if l.startswith("#"))
    found = [
        w
        for w, pattern in BANNED.items()
        if pattern.search(prose) or pattern.search(heads)
    ]
    return (
        ((len(sentences) - len(long)) / len(sentences) if sentences else 1.0),
        long,
        found,
    )


def docstring_markdown(doc: str) -> str:
    """A Google-style docstring as Markdown: each section label in bold, each argument
    as a bullet, code blocks kept."""
    sections, listed, out, section = (
        "Args|Arguments|Returns|Yields|Raises|Attributes|Example|Examples|Note|Notes",
        ("Args", "Arguments", "Raises", "Attributes", "Yields"),
        [],
        "",
    )
    for line in doc.splitlines():
        if found := re.fullmatch(rf"({sections}):\s*", line):
            section = found.group(1)
            out += ["", f"**{section}:**", ""]
            continue
        if section and (line.startswith("    ") or not line.strip()):
            line = line[4:]
        elif section:
            section = ""
        item = re.match(r"^(\*{0,2}[\w.]+)(?: \([^)]*\))?: (.*)$", line)
        if section in listed and item:
            out.append(f"- `{item.group(1)}`: {item.group(2)}")
        elif section in listed and line.strip():
            out.append("  " + line.strip())
        else:
            out.append(line)
    return "\n".join(out).strip()


def resolve(path: str) -> object:
    parts = path.split(".")
    for cut in range(len(parts), 0, -1):
        try:
            found: object = importlib.import_module(".".join(parts[:cut]))
        except ModuleNotFoundError:
            continue
        for name in parts[cut:]:
            found = getattr(found, name)
        return found
    raise SystemExit(f"reference: cannot find {path}")


def signature_of(name: str, obj: object) -> str:
    try:
        string = annotationlib.Format.STRING
        shown = str(inspect.signature(obj, annotation_format=string))  # type: ignore[arg-type]
        shown = re.sub(
            r"<function .*? at 0x[0-9a-f]+>", "a function", shown
        )  # a default function has no stable text: its address changes
        return name + re.sub(
            r"(: |-> )'([^']*)'", r"\1\2", shown
        )  # the annotations are text: show them without quotes
    except TypeError, ValueError, NameError:
        return name


def entry_markdown(path: str, level: int) -> str:
    """One object of the API reference in plain Markdown: its name, its signature, its
    docstring, and its public members."""
    obj, short = resolve(path), path.split(".")[-1]
    doc = (
        inspect.getdoc(obj)
        if not isinstance(obj, type(importlib))
        else (obj.__doc__ or "")
    )
    head = "#" * level + f" {short}\n\n"
    if (inspect.isclass(obj) or inspect.isfunction(obj)) and "(_" not in signature_of(
        short, obj
    ):
        head += "```python\n" + signature_of(short, obj) + "\n```\n\n"
    text = (
        head
        + (
            docstring_markdown(doc or "")
            if isinstance(doc, str)
            and (
                inspect.isclass(obj)
                or inspect.isfunction(obj)
                or inspect.ismodule(obj)
                or "\n" in doc
                or len(doc) < 600
            )
            else ""
        )
        + "\n\n"
    )
    if inspect.ismodule(obj):
        names = getattr(obj, "__all__", None) or [
            n
            for n, v in vars(obj).items()
            if not n.startswith("_") and getattr(v, "__module__", "") == obj.__name__
        ]
        return text + "".join(entry_markdown(f"{path}.{n}", level + 1) for n in names)
    if inspect.isclass(obj):
        if issubclass(obj, enum.Enum):
            text += (
                "".join(
                    f"- `{m}` = `{v.value!r}`\n" for m, v in obj.__members__.items()
                )
                + "\n"
            )
        for name, member in obj.__dict__.items():
            public = not name.startswith("_") or name in (
                "__describe__",
                "__sub__",
                "__add__",
            )
            if public and isinstance(
                member, (types.FunctionType, classmethod, staticmethod, property)
            ):
                function = getattr(obj, name)
                member_doc = (
                    inspect.getdoc(
                        member.fget if isinstance(member, property) else function
                    )
                    or ""
                )
                kind = "property" if isinstance(member, property) else ""
                call = (
                    ""
                    if isinstance(member, property)
                    else "\n```python\n"
                    + signature_of(f"{short}.{name}", function)
                    + "\n```\n"
                )
                head = (
                    f"{'#' * (level + 1)} {short}.{name}{f' ({kind})' if kind else ''}"
                )
                text += f"{head}\n{call}\n{docstring_markdown(member_doc)}\n\n"
    return text


def reference_markdown(page: Path) -> str:
    """A reference page without mkdocstrings: each `::: name` line becomes the name, the
    signature and the docstring."""
    out: list[str] = []
    for line in page.read_text().splitlines():
        if line.startswith("    ") and out and out[-1].startswith("<!--"):
            continue  # the options of the `:::` line
        if found := re.fullmatch(r":::\s+([\w.]+)", line):
            out.append(entry_markdown(found.group(1), 2).rstrip() + "\n<!--options-->")
        else:
            out.append(line)
    return "\n".join(out).replace("\n<!--options-->", "")


BUILD.mkdir(exist_ok=True)
for folder in ("reference", "reference-md", "assets", "examples"):
    (BUILD / folder).mkdir(exist_ok=True)
for page in sorted(
    (ROOT / "docs" / "reference").glob("*.md")
):  # the API reference: mkdocstrings fills it from the docstrings
    (BUILD / "reference" / page.name).write_text(page.read_text())
    (BUILD / "reference-md" / page.name).write_text(
        reference_markdown(page)
    )  # the same page as plain Markdown, for the notebook
for asset in sorted((ROOT / "docs" / "assets").glob("*")):
    (BUILD / "assets" / asset.name).write_text(asset.read_text())
for folder, root in (
    ("examples", ROOT / "docs" / "examples"),
):  # pages link to the code
    for source in sorted(root.glob("*.py")):
        (BUILD / folder / source.name).write_text(source.read_text())

failed = []
for name in NAV_PAGES:
    page = PAGES / name
    text = page.read_text()
    (BUILD / name).write_text(
        re.sub(r'^( *)--8<-- "([^"]+)"$', indented, text, flags=re.M)
    )
    share, long, banned = style(text)
    print(
        f"built {name}: {share:.0%} of sentences have 25 words or fewer"
        + (f"; banned words: {banned}" if banned else "")
    )
    for sentence in long:
        print(f"    long ({len(sentence.split())} words): {sentence[:110]}")
    if share < 0.8 or banned:
        failed.append(name)

(BUILD / "assets" / "hover.json").write_text(
    json.dumps({"tips": hover.TIPS, "blocks": hover.BLOCKS})
)  # the hover text of each code block (docs/hover.py), for the site and the notebook


def undefined_names(page: Path) -> list[str]:
    """The names that a page's code uses before any code shown on that page defines
    them. The shown sections are joined in page order, as a reader reads them."""
    shown = []
    for target in re.findall(
        r'^\s*--8<-- "([^":]+\.py):(\w+)"$', page.read_text(), re.M
    ):
        text = (ROOT / target[0]).read_text()
        shown.append(
            text.split(f"# [start:{target[1]}]\n")[1].split(f"# [end:{target[1]}]")[0]
        )
    if not shown:
        return []
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--isolated",
            "--target-version",
            "py314",
            "--select",
            "F821",
            "--output-format",
            "json",
            "--stdin-filename",
            "page.py",
            "-",
        ],
        input="\n".join(shown),
        capture_output=True,
        text=True,
    )
    return sorted(
        {found["message"].split("`")[1] for found in json.loads(done.stdout or "[]")}
    )


for name in NAV_PAGES:
    if missing := undefined_names(PAGES / name):
        failed.append(
            f"{name} (code uses names that no shown code defines: {', '.join(missing)})"
        )

home = (PAGES / "index.md").read_text()  # the home page lists every page of the nav
unlisted = [  # the reference index lists the reference pages
    f
    for f in NAV_FILES
    if f != "index.md" and f"({f})" not in home and not f.startswith("reference/")
]
if unlisted:
    failed.append(f"index.md (it does not list: {', '.join(unlisted)})")
if failed:
    raise SystemExit(f"style check failed (docs/STYLE.md): {', '.join(failed)}")
