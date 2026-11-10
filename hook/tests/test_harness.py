"""Run the 36 recorded events through the harness with the recorded answers of the real d1-2b, and compare.

    python3.14 tests/test_harness.py                        compare with tests/recorded.json
    python3.14 tests/test_harness.py --record config.json   ask the real d1 again, and write tests/recorded.json and web/site/data.js

tests/events.json: the events of 1 hour of a real conversation. "gold" is what a person wrote that the message wants (classes).
tests/recorded.json: each answer of d1, each record that the harness wrote, and the comparison of d1 with "gold".
"""

import ast
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
        mine = {"session": EVENTS[0]["input"]["session_id"], "text": EVENTS[0]["input"]["prompt"], "part": 0, "demands": [], "things": {}}
        harness.reading(mine)  # the user says: part 1 of message 1 asks for nothing. The next message of the session must carry it.
        said = harness.handle(EVENTS[0]["input"], ask)["hookSpecificOutput"]["additionalContext"]
        assert "The user says that" in said and "asks for nothing" in said, said
        return [{k: v for k, v in harness.migrate(json.loads(line)).items() if k != "at"} for line in harness.LOG.read_text().splitlines()][:len(EVENTS)]


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
        assert record["form"] == harness.FORM and record["harness"] == harness.VERSION and len(record["world"]) == 12
        if record["event"] == "UserPromptSubmit":  # the template is the whole message, and each part keeps its place in the text
            assert "".join(piece if isinstance(piece, str) else piece["words"] for piece in record["template"]) == record["text"]
            assert all(record["text"][part["start"]:part["end"]].strip() for part in record["parts"])
        for demand in record.get("demands", []):
            assert demand["function"] in harness.FUNCTIONS and (demand["words"] or "") in record["text"]
            assert demand["part"] is None or demand["function"] in record["parts"][demand["part"]]["demands"]
            for hole in demand["parameters"].values():
                assert hole["by"] in (None, *harness.By) and (hole["by"] != harness.By.WORDS or hole["value"].lower() in record["text"].lower())
            ast.parse(demand["python"], mode="eval")  # each demand is a Python expression
    assert records[-1]["answer"]["decision"] == "block" and records[-2]["answer"]["hookSpecificOutput"]
    counted = {"function": "count", "parameters": {"notebook": {"type": "Notebook", "value": "the old cells", "by": harness.By.WORDS}}}
    assert harness.call(counted, [counted]) == "count(notebook=Notebook('the old cells'))" and harness.run(counted, [counted]) == "5"  # a body runs
    assert harness.run(counted | {"parameters": {"notebook": {"type": "Notebook", "value": None, "by": None}}}, []) is None  # an open hole: no run
    assert isinstance(harness.run(counted, [counted]), harness.Observed) and harness.run({"function": "explain", "parameters": {}}, []) is None  # no body: no run
    old = {"event": "UserPromptSubmit", "session": "s", "text": "x", "demands": [{"function": "delete", "p": 0.9}]}  # a line of 0.1.1
    assert harness.migrate(old)["demands"][0]["part"] is None and harness.migrate(old)["form"] == harness.FORM


if __name__ == "__main__":
    if sys.argv[1:2] == ["--record"]:
        answers, where = {}, json.loads(pathlib.Path(sys.argv[2]).read_text())
        records = run(lambda state, questions: answers.setdefault(key(state, questions), harness.d1(state, questions, lambda: where)))
        RECORDED.write_text(json.dumps({"measure": measure(records), "records": records, "answers": answers}, indent=1) + "\n")
        site = HERE.parent.parent / "web" / "site" / "data.js"
        site.write_text("const DATA = " + json.dumps({"world": harness.describe(), "events": records, "measure": measure(records)}) + ";\n")
        answers = dict(answers)
        print("recorded", len(records), "events and", len(answers), "requests to d1")
    test_recorded()
    print(len(EVENTS), "events, the same as recorded.", json.loads(RECORDED.read_text())["measure"])
