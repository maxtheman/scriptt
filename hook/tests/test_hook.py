"""Run each recorded event through the hook, in order, and compare the answer with the recorded one.

    python tests/test_hook.py            compare
    python tests/test_hook.py --record   write the answers of this run into the event files

Each file in tests/events/ has: "input" (the event JSON that Claude Code sends), "d1_answers" (recorded answers of
d1 for that text), "expected_output" (what the hook must print) and, for a message, "expected_holes".
"""

import json
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).parent
HOOK = HERE.parent / "scriptt_hook.py"


def run_all(record=False):
    failures = []
    with tempfile.TemporaryDirectory() as home:
        for path in sorted((HERE / "events").glob("*.json")):
            case = json.loads(path.read_text())
            answers = pathlib.Path(home) / "answers.json"
            answers.write_text(json.dumps(case["d1_answers"]))
            environment = os.environ | {"SCRIPTT_HOOK_HOME": home, "SCRIPTT_D1_ANSWERS": str(answers), "SCRIPTT_HOOK_BLOCK": "1"}
            done = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(case["input"]), capture_output=True, text=True, env=environment)
            output = json.loads(done.stdout) if done.stdout.strip() else None
            if done.returncode != 0 or done.stderr:
                failures.append(f"{path.name}: exit {done.returncode}, stderr {done.stderr.strip()}")
            if record:
                case["expected_output"] = output
                path.write_text(json.dumps(case, indent=1))
            elif output != case.get("expected_output"):
                failures.append(f"{path.name}: the output differs from the recorded one")
        events = [json.loads(line) for line in (pathlib.Path(home) / "events.jsonl").read_text().splitlines()]
    for path, event in zip(sorted((HERE / "events").glob("*.json")), events):
        case = json.loads(path.read_text())
        if "expected_holes" in case and event["holes"] != case["expected_holes"]:
            failures.append(f"{path.name}: holes {event['holes']}, expected {case['expected_holes']}")
        used = {slot["words"] for slot in event["slots"]}
        unused = [w for words in case["d1_answers"].values() for w in words if w not in used]
        if unused:
            failures.append(f"{path.name}: recorded answers that the hook did not use: {unused}")
    return failures, events


def test_recorded_events():
    failures, _ = run_all()
    assert not failures, "\n".join(failures)


if __name__ == "__main__":
    failures, events = run_all(record="--record" in sys.argv)
    print(f"{len(events)} events, {len(failures)} failures")
    print("\n".join(failures))
    sys.exit(1 if failures else 0)
