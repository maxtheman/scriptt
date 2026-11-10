"""Run the 36 recorded events through the harness with the recorded answers of the real d1-2b, and compare.

    python3.14 tests/test_harness.py                        compare with tests/recorded.json
    python3.14 tests/test_harness.py --record config.json   ask the real d1 again, and write tests/recorded.json and web/site/data.js

tests/events.json: the events of 1 hour of a real conversation. "gold" is what a person wrote that the message wants (classes).
tests/recorded.json: each answer of d1, each record that the harness wrote, and the comparison of d1 with "gold".
"""

import hashlib
import json
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
import harness

EVENTS = json.loads((HERE / "events.json").read_text())
RECORDED = HERE / "recorded.json"


def run(ask) -> list:
    with tempfile.TemporaryDirectory() as folder:
        harness.LOG, harness.config = pathlib.Path(folder) / "events.jsonl", lambda: {"block": True}
        for event in EVENTS:
            harness.handle(event["input"], ask)
        return [json.loads(line) for line in harness.LOG.read_text().splitlines()]


def measure(records: list) -> dict:
    """d1 against the person: for each message, the classes that the demanded functions return, beside "gold"."""
    rows = [{"wants": sorted({d["returns"] for d in record["demands"]}), "gold": event["gold"]} for event, record in zip(EVENTS, records) if "gold" in event]
    count = lambda f: sum(len(f(set(row["wants"]), set(row["gold"]))) for row in rows)
    return {"messages": len(rows), "same set": sum(row["wants"] == row["gold"] for row in rows),
            "classes in both": count(set.__and__), "only the person": count(lambda d, g: g - d), "only d1": count(set.__sub__)}


def key(state, questions) -> str:
    return hashlib.sha1(json.dumps([state, questions], sort_keys=True).encode()).hexdigest()


def test_recorded():
    recorded = json.loads(RECORDED.read_text())
    records = run(lambda state, questions: recorded["answers"][key(state, questions)])
    assert records == recorded["records"], "the records differ from tests/recorded.json"
    assert measure(records) == recorded["measure"]
    for record in records:
        for demand in record.get("demands", []):
            assert demand["function"] in harness.FUNCTIONS and (demand["words"] or "") in record["text"]
            for hole in demand["parameters"].values():
                assert hole["thing"] is None or hole["thing"] in harness.world.NAMED[harness.CLASSES[hole["class"]]]
    assert records[-1]["answer"]["decision"] == "block" and records[-2]["answer"]["hookSpecificOutput"]


if __name__ == "__main__":
    if sys.argv[1:2] == ["--record"]:
        answers, where = {}, json.loads(pathlib.Path(sys.argv[2]).read_text())
        records = run(lambda state, questions: answers.setdefault(key(state, questions), harness.d1(state, questions, lambda: where)))
        RECORDED.write_text(json.dumps({"measure": measure(records), "records": records, "answers": answers}, indent=1) + "\n")
        site = HERE.parent.parent / "web" / "site" / "data.js"
        site.write_text("const DATA = " + json.dumps({"world": harness.describe(), "events": records, "measure": measure(records)}) + ";\n")
        print("recorded", len(records), "events and", len(answers), "requests to d1")
    test_recorded()
    print(len(EVENTS), "events, the same as recorded.", json.loads(RECORDED.read_text())["measure"])
