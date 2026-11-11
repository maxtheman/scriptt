"""Reads the demo message (web/site/board/demo/message.txt) with the real d1, against web/site/board/demo/world.py, and
writes the one saved reading that scriptt.ai/board/?demo starts from: web/site/board/demo/events.jsonl.

    python3.14 web/make_demo.py CONFIG.json

CONFIG.json is a .scriptt/config.json that names a d1 endpoint. The page then runs the engine itself, in Pyodide; only this
first reading needs d1.
"""

import json
import pathlib
import shutil
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEMO = ROOT / "web/site/board/demo"

with tempfile.TemporaryDirectory() as temporary:
    home = pathlib.Path(temporary) / ".scriptt"
    home.mkdir()
    for source in (ROOT / "scriptt/harness.py", ROOT / "next/agree.py", ROOT / "next/scriptt16.py", DEMO / "world.py"):
        shutil.copyfile(source, home / source.name)
    shutil.copyfile(sys.argv[1], home / "config.json")
    sys.path.insert(0, str(home))
    import harness  # noqa: E402
    text = (DEMO / "message.txt").read_text().strip()
    answer = harness.prompt({"session_id": "demo", "prompt": text}, harness.d1)
    lines = (home / "events.jsonl").read_text().splitlines()
    (DEMO / "events.jsonl").write_text(lines[-1] + "\n")
    print(answer["hookSpecificOutput"]["additionalContext"])
