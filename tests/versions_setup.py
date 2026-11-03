"""Setup for the scriptt.world.versions examples: a temporary git and DVC project.

Its 1 step writes results/score.json.
"""

import subprocess, tempfile
from pathlib import Path

from scriptt.world.versions import Project, Result


class ModelScore(Result, path="results/score.json"):
    model: str
    right: int


root = Path(tempfile.mkdtemp())
for cmd in (
    ["git", "init", "-q"],
    ["git", "config", "user.email", "t@example.com"],
    ["git", "config", "user.name", "Test"],
    ["git", "config", "commit.gpgsign", "false"],
):
    subprocess.run(cmd, cwd=root, check=True)
(root / "score.py").write_text(
    "import yaml\n"
    "from pathlib import Path\n"
    "n = yaml.safe_load(Path('params.yaml').read_text())['journals']\n"
    "Path('results').mkdir(exist_ok=True)\n"
    "Path('results/score.json').write_text("
    '\'{"model": "baseline", "right": %d}\' % n)\n'
)
(root / "params.yaml").write_text("journals: 4\n")
(root / "dvc.yaml").write_text(
    "stages:\n"
    "  score:\n"
    "    cmd: python score.py\n"
    "    deps: [score.py]\n"
    "    params: [journals]\n"
    "    outs:\n"
    "      - results/score.json:\n"
    "          cache: false\n"
)
from dvc.repo import Repo

Repo.init(str(root), no_scm=False).close()
project = Project(root)
import os

os.chdir(root)
project.run()
project.keep(
    "first run",
    "dvc.yaml",
    "params.yaml",
    "score.py",
    "results/score.json",
    ".dvc",
    ".dvcignore",
)
