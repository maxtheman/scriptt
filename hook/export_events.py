"""Run the recorded events through the hook and write them, with the world, into the website.

    python export_events.py

It replaces the text between /*DATA-START*/ and /*DATA-END*/ in ../web/site/index.html.
"""

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE / "tests"))
import test_hook
import world

_, events = test_hook.run_all()
data = f"const WORLD = {json.dumps(world.describe())};\nconst EVENTS = {json.dumps(events)};\n"
(HERE / "tests" / "events.js").write_text(data)
page = HERE.parent / "web" / "site" / "index.html"
text = page.read_text()
if "/*DATA-START*/" in text:
    head, rest = text.split("/*DATA-START*/", 1)
    page.write_text(head + "/*DATA-START*/\n" + data + "/*DATA-END*/" + rest.split("/*DATA-END*/", 1)[1])
    print("wrote", len(events), "events into", page)
else:
    print("no /*DATA-START*/ marker in", page, "- wrote tests/events.js only")
