"""Check that a release tag matches the packages: `release_check.py v0.1.0`.

The check fails when a package has a different version, when CHANGELOG.md has no section
for the version, or when a package has no license.
"""

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = [
    ROOT / "pyproject.toml",
    ROOT / "packages" / "scriptt-charts" / "pyproject.toml",
]


def problems(tag: str) -> list[str]:
    version = tag.removeprefix("v")
    found = []
    for path in PACKAGES:
        project = tomllib.loads(path.read_text())["project"]
        if project["version"] != version:
            found.append(
                f"{project['name']} has version {project['version']}, not {version}"
            )
        if "license" not in project:
            found.append(
                f"{project['name']} has no license in {path.relative_to(ROOT)}"
            )
    changelog = (ROOT / "CHANGELOG.md").read_text()
    if not re.search(
        rf"^## \[{re.escape(version)}\] - \d{{4}}-\d{{2}}-\d{{2}}$", changelog, re.M
    ):
        found.append(f"CHANGELOG.md has no line '## [{version}] - YYYY-MM-DD'")
    return found


if __name__ == "__main__":
    if len(sys.argv) != 2 or not re.fullmatch(r"v\d+\.\d+\.\d+", sys.argv[1]):
        raise SystemExit("usage: release_check.py vX.Y.Z")
    if found := problems(sys.argv[1]):
        raise SystemExit("\n".join(found))
    print(f"{sys.argv[1]}: versions, changelog and licenses match")
