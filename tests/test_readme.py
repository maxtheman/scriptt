"""The example of README.md runs and prints the text that the README shows under it."""

import re
import subprocess
import sys
from pathlib import Path

README = Path(__file__).resolve().parents[1] / "README.md"


def test_readme_example(tmp_path: Path) -> None:
    text = README.read_text()
    code = re.search(r"## Example\n\n```python\n(.*?)```", text, re.S)
    shown = re.search(r"The example prints:\n\n```text\n(.*?)```", text, re.S)
    assert code and shown, "README.md has no example or no output under it"
    script = tmp_path / "readme.py"
    script.write_text(code.group(1))
    done = subprocess.run(
        [sys.executable, str(script)], cwd=tmp_path, capture_output=True, text=True
    )
    assert done.returncode == 0, done.stderr[-3000:]
    assert done.stdout == shown.group(1)
