"""Read the recorded messages with a real d1 and compare its ranges with the recorded (hand-written) ones.

    SCRIPTT_D1_URL=http://127.0.0.1:8791 python tests/try_d1.py

It writes tests/d1_real.json. It does not change the recorded events.
"""

import json
import os
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
import d1
import program

ask = d1.system_one(os.environ["SCRIPTT_D1_URL"], os.environ.get("SCRIPTT_D1_MODEL", "d1-2B-MLX-8bit"))
rows, started = [], time.time()
for path in sorted((HERE / "events").glob("*.json")):
    case = json.loads(path.read_text())
    if case["input"]["hook_event_name"] != "UserPromptSubmit":
        continue
    typed, log = program.read(case["input"]["prompt"], "user", ask)
    r = program.result(typed)
    gold = {(cls, words) for cls, many in case["d1_answers"].items() for words in many}
    real = {(slot["class"], slot["words"]) for slot in r["slots"]}
    rows.append({"event": path.stem, "gold slots": len(gold), "d1 slots": len(real), "same class and same words": len(gold & real),
                 "holes": r["holes"], "gold holes": case.get("expected_holes"), "reads": len(log), "d1": sorted(real), "gold": sorted(gold)})
    print(path.stem, "gold", len(gold), "d1", len(real), "same", len(gold & real), "holes equal", r["holes"] == case.get("expected_holes"), flush=True)
total = {k: sum(row[k] for row in rows) for k in ("gold slots", "d1 slots", "same class and same words", "reads")}
total["messages with the gold holes"] = sum(row["holes"] == row["gold holes"] for row in rows)
total["messages"] = len(rows)
total["seconds"] = round(time.time() - started, 1)
(HERE / "d1_real.json").write_text(json.dumps({"total": total, "messages": rows}, indent=1))
print(total)
