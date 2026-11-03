"""Run the ```python block of every `Example:` section in the docstrings of
`scriptt.world` and `scriptt.charts`. A line `expr  # -> value` checks that repr(expr)
or str(expr) is value.

Each block runs in its own process and folder, after the setup module of its file:
versions_setup.py for `scriptt.world.versions`, examples_setup.py for every other file.
"""

import ast
import inspect
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
SOURCES = [
    ROOT / "src" / "scriptt" / "world",
    ROOT / "packages" / "scriptt-charts" / "src" / "scriptt" / "charts",
]
CHECK = (  # a class of the example script prints as __main__.Name; the docs show Name
    "def __chk(v, c):\n"
    "    r, s = (x.replace('__main__.', '') for x in (repr(v), str(v)))\n"
    "    assert c in (r, s), f'example says {c!r} but the code gives {v!r}'\n"
)


def checked(code: str) -> str:
    """The code with each `expr  # -> value` line made into a check."""
    lines, edits = code.split("\n"), []
    for node in ast.parse(code).body:
        if not isinstance(node, ast.Expr) or node.end_lineno is None:
            continue
        if found := re.search(r"\s+# -> (.*)$", lines[node.end_lineno - 1]):
            body = "\n".join(lines[node.lineno - 1 : node.end_lineno])
            body = body[: body.rindex(found.group(0))]
            edits.append(
                (
                    node.lineno - 1,
                    node.end_lineno,
                    f"__chk(({body.strip()}), {found.group(1)!r})",
                )
            )
    for start, end, new in reversed(edits):
        lines[start:end] = [new]
    return CHECK + "\n".join(lines) if edits else code


def docstrings(file: Path):
    """(name, docstring) of the module, each class, each function, each type alias."""
    tree = ast.parse(file.read_text())

    def walk(node: ast.AST, prefix: str):
        yield prefix, node
        for child in getattr(node, "body", []):
            if isinstance(child, (ast.ClassDef, ast.FunctionDef)):
                yield from walk(
                    child, f"{prefix}.{child.name}" if prefix else child.name
                )

    for name, node in walk(tree, ""):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
            yield name or "module", ast.get_docstring(node)
    for alias, doc in zip(tree.body, tree.body[1:]):
        if (
            isinstance(alias, ast.TypeAlias)
            and isinstance(doc, ast.Expr)
            and isinstance(doc.value, ast.Constant)
            and isinstance(doc.value.value, str)
        ):
            yield alias.name.id, inspect.cleandoc(doc.value.value)


def examples() -> list:
    return list(_examples())


def _examples():
    for source in SOURCES:
        for file in sorted(source.glob("*.py")):
            setup = "versions_setup" if file.stem == "versions" else "examples_setup"
            for name, doc in docstrings(file):
                if not doc or "Example:" not in doc:
                    continue
                section = doc.split("Example:", 1)[1]
                for n, block in enumerate(
                    re.findall(r"```python\n(.*?)```", section, re.S)
                ):
                    code = f"from {setup} import *\n" + checked(textwrap.dedent(block))
                    yield pytest.param(code, id=f"{source.name}.{file.stem}.{name}.{n}")


@pytest.mark.parametrize("code", examples())
def test_example(code: str, tmp_path: Path) -> None:
    script = tmp_path / "example.py"
    script.write_text(code)
    done = subprocess.run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(TESTS)},
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert done.returncode == 0, done.stderr[-3000:]
