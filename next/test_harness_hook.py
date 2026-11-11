"""The shipped hooks end to end: an install in a temporary folder, Claude Code's hook events, and the stand-in d1.

    python3.14 next/test_harness_hook.py            stand-in d1 only
    python3.14 next/test_harness_hook.py --live     also 1 prompt through the real d1 of .scriptt/config.json (CoreAI on 127.0.0.1:8765);
                                                    its event, answer, form-5 line and every request and response go to tests/live/

The folder gets the 5 shipped files as web/build.sh ships them (harness.py, agree.py, scriptt16.py, SKILL.md, and world.py
unless the folder has one: here it has next/world.py, which the install must leave as it is). The stand-in d1 of
test_scriptt16.py answers behind an HTTP endpoint in the shape of CoreAI's /v1/decide, and harness.py runs as Claude Code
runs it: a process with 1 event on stdin.
"""

import hashlib
import http.server
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path[:0] = [str(HERE), str(ROOT / "scriptt")]
import agree  # noqa: E402
import expected as X  # noqa: E402
import scriptt16  # noqa: E402
from test_scriptt16 import Standin  # noqa: E402

PYTHON = sys.executable
TEXT = "Redesign the mod. Test the search too."
SCRIPT = X.script({"Redesign the mod.": "redesign", "Test the search too.": "test"},
                  {("Redesign the mod.", "redesign", "surface"): X.MOD, ("Test the search too.", "test", "subject"): X.SEARCH})


def strict(line: str) -> dict:
    """Parses a line as JSON with no NaN or Infinity."""
    return json.loads(line, parse_constant=lambda name: (_ for _ in ()).throw(ValueError(f"{name} is not JSON")))


def endpoint(model) -> tuple[http.server.HTTPServer, str]:
    """Serves a model as CoreAI's /v1/decide: {state, questions: [{id, ...}]} -> {answers: [{id, ...}]}."""
    class Decide(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            answers = model(body["state"], {one["id"]: {k: v for k, v in one.items() if k != "id"} for one in body["questions"]})
            sent = json.dumps({"answers": [{"id": id} | answer for id, answer in answers.items()]}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(sent)))
            self.end_headers()
            self.wfile.write(sent)

        def log_message(self, *args):
            pass
    server = http.server.HTTPServer(("127.0.0.1", 0), Decide)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}/v1/decide"


def installed(folder: pathlib.Path, own_world: str | None) -> pathlib.Path:
    """Puts the shipped files in folder/.scriptt as install.sh does, and runs harness.py install."""
    home = folder / ".scriptt"
    home.mkdir(parents=True)
    if own_world is not None:
        (home / "world.py").write_text(own_world)
    for source in (ROOT / "scriptt/harness.py", ROOT / "scriptt/SKILL.md", ROOT / "next/agree.py", ROOT / "next/scriptt16.py", ROOT / "scriptt/world.py"):
        if source.name != "world.py" or not (home / "world.py").exists():
            shutil.copyfile(source, home / source.name)
    done = subprocess.run([PYTHON, str(home / "harness.py"), "install"], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return home


def shipped(home: pathlib.Path) -> None:
    """The installed harness imports the engine from beside it, and those files are next/agree.py and next/scriptt16.py as committed at HEAD."""
    probe = "import sys, hashlib, pathlib; sys.argv = ['x', 'world']; import harness, agree, scriptt16; print(' '.join(f'{pathlib.Path(m.__file__).resolve()}={hashlib.sha256(pathlib.Path(m.__file__).read_bytes()).hexdigest()}' for m in (harness, agree, scriptt16)))"
    done = subprocess.run([PYTHON, "-c", probe], cwd=home, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    for one in done.stdout.split():
        path, sha = one.split("=")
        assert pathlib.Path(path).parent == home.resolve(), f"{path} is imported from outside the install"
        source = ROOT / ("scriptt" if pathlib.Path(path).name == "harness.py" else "next") / pathlib.Path(path).name
        committed = subprocess.run(["git", "-C", str(ROOT), "show", f"HEAD:{source.relative_to(ROOT)}"], capture_output=True).stdout
        state = "committed at HEAD" if hashlib.sha256(committed).hexdigest() == sha else "NOT AS COMMITTED"
        assert hashlib.sha256(source.read_bytes()).hexdigest() == sha, f"{path} differs from {source}"
        print(f"  shipped {pathlib.Path(path).name:<13} = {source.relative_to(ROOT)}  sha256 {sha[:16]}  {state}")


def hook(home: pathlib.Path, event: dict) -> dict | None:
    done = subprocess.run([PYTHON, str(home / "harness.py")], input=json.dumps(event), capture_output=True, text=True, timeout=300)
    assert done.returncode == 0 and not done.stderr, done.stderr
    return json.loads(done.stdout) if done.stdout.strip() else None


def transcript(folder: pathlib.Path, name: str, prompt: str, steps: list) -> str:
    """A transcript in Claude Code's shape: the prompt, then for each step a tool call and its result, or a text of the reply."""
    entries = [{"type": "user", "message": {"role": "user", "content": prompt}}]
    for n, step in enumerate(steps):
        match step:
            case ("Bash", command, code):
                entries += [{"type": "assistant", "message": {"content": [{"type": "tool_use", "id": f"t{n}", "name": "Bash", "input": {"command": command}}]}},
                            {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": f"t{n}", "is_error": code != 0, "content": f"Exit code {code}\nboom" if code else "ok"}]}}]
            case ("Write", path):
                (folder / path).write_text("x")
                entries += [{"type": "assistant", "message": {"content": [{"type": "tool_use", "id": f"t{n}", "name": "Write", "input": {"file_path": str(folder / path), "content": "x"}}]}},
                            {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": f"t{n}", "content": "written"}]}}]
            case str(words):
                entries += [{"type": "assistant", "message": {"content": [{"type": "text", "text": words}]}}]
    path = folder / f"{name}.jsonl"
    path.write_text("".join(json.dumps(one) + "\n" for one in entries))
    return str(path)


def last_stop(home: pathlib.Path) -> dict:
    return [json.loads(line) for line in (home / "hooks.jsonl").read_text().splitlines()][-1]


def test_hooks() -> None:
    world_source = (HERE / "world.py").read_text()
    server, url = endpoint(Standin(SCRIPT, X.World("next")))
    with tempfile.TemporaryDirectory() as temporary:
        folder = pathlib.Path(temporary)
        home = installed(folder, world_source)
        assert (home / "world.py").read_text() == world_source, "the install replaced the user's world"
        shipped(home)
        settings = json.loads((folder / ".claude/settings.local.json").read_text())
        assert all(any("harness.py" in json.dumps(entry) for entry in settings["hooks"][name]) for name in ("UserPromptSubmit", "Stop"))
        assert (folder / ".claude/skills/scriptt/SKILL.md").read_text() == (ROOT / "scriptt/SKILL.md").read_text()
        (home / "config.json").write_text(json.dumps({"url": url, "block": True}))
        world = agree.loads(world_source, folder)

        def prompt(session: str) -> tuple[str, dict]:
            said = hook(home, {"hook_event_name": "UserPromptSubmit", "session_id": session, "prompt": TEXT})["hookSpecificOutput"]["additionalContext"]
            line = strict((home / "events.jsonl").read_text().splitlines()[-1])
            assert line["form"] == 5 and line["text"] == TEXT and line["world"] == agree.identity(world)
            reading, found = scriptt16.load(line, world)
            assert reading is not None and not found, found
            return said, line

        # 1. A prompt writes a valid form-5 line and returns the reading.
        said, line = prompt("s1")
        print("prompt, additionalContext:\n" + "\n".join("  " + one for one in said.splitlines()))
        for words in ("#0 redesign(surface='the mod') -> Later[Surface]", "#1 test(subject='the search') -> Observed", "def redesign(surface: Surface) -> Later[Surface]", "evidence: a file written"):
            assert words in said, words
        assert (home / "worlds" / f"{line['world']}.py").read_text() == world_source

        # 2. Evidence for 1 of 2 obligations (a command ran: test) blocks, blocks again, then passes: at most 2 send-backs.
        ran = transcript(folder, "ran", TEXT, [("Bash", "python3.14 -m unittest", 0), "I redesigned the mod and tested the search."])
        stop = {"hook_event_name": "Stop", "session_id": "s1", "transcript_path": ran, "last_assistant_message": "I redesigned the mod and tested the search."}
        seen, reasons = [], []
        for _ in range(3):
            answer = hook(home, stop)
            reasons.append(answer and answer["reason"])
            record = last_stop(home)
            seen.append((answer and answer["decision"], record["verdict"], record["blocks"], [one["outcome"] for one in record["outcomes"]]))
        print("stop with a command run, 3 times:", seen)
        print("  reason of the first send-back:\n  " + reasons[0].replace("\n", "\n  "))
        assert seen == [("block", "UNVERIFIED", 1, ["UNVERIFIED", "PASS"]), ("block", "UNVERIFIED", 2, ["UNVERIFIED", "PASS"]), (None, "UNVERIFIED", 2, ["UNVERIFIED", "PASS"])], seen
        saved = strict((home / "events.jsonl").read_text().splitlines()[-1])
        assert saved["id"] == line["id"] and [one["outcome"] for one in saved["fulfillment"]] == ["UNVERIFIED", "PASS"], "the check is not saved with the reading"

        # 3. Prose only is no evidence: the reply says both are done, and nothing passes.
        prompt("s2")
        words = transcript(folder, "words", TEXT, ["Done: I redesigned the mod and ran the tests for the search. Both pass."])
        answer = hook(home, {"hook_event_name": "Stop", "session_id": "s2", "transcript_path": words, "last_assistant_message": "Done: both pass."})
        record = last_stop(home)
        print("stop with prose only:", record["verdict"], [one["outcome"] for one in record["outcomes"]], "\n  reason:", answer["reason"].replace("\n", "\n  "))
        assert answer["decision"] == "block" and record["evidence"] == [] and {one["outcome"] for one in record["outcomes"]} == {"UNVERIFIED"}

        # 4. Evidence for both passes at once; a failing command fails its obligation.
        prompt("s3")
        both = transcript(folder, "both", TEXT, [("Write", "mod.css"), ("Bash", "python3.14 -m unittest", 0)])
        assert hook(home, {"hook_event_name": "Stop", "session_id": "s3", "transcript_path": both}) is None and last_stop(home)["verdict"] == "PASS"
        prompt("s4")
        failing = transcript(folder, "failing", TEXT, [("Write", "mod.css"), ("Bash", "python3.14 -m unittest", 1)])
        answer = hook(home, {"hook_event_name": "Stop", "session_id": "s4", "transcript_path": failing})
        assert answer["decision"] == "block" and [one["outcome"] for one in last_stop(home)["outcomes"]] == ["PASS", "FAIL"] and "exited 1" in answer["reason"]
        print("stop with both: PASS, no block; with a failing command:", [one["outcome"] for one in last_stop(home)["outcomes"]])

        # 5. serve: the readings, the worlds, and the engine's edit, accept and restore.
        served = subprocess.Popen([PYTHON, str(home / "harness.py"), "serve", "8799"], stdout=subprocess.PIPE, text=True)
        try:
            served.stdout.readline()
            get = lambda path: json.load(urllib.request.urlopen(f"http://127.0.0.1:8799/{path}"))
            post = lambda path, body: json.load(urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:8799/{path}", json.dumps(body).encode(), {"Content-Type": "application/json"})))
            readings, worlds = get("readings"), get("worlds")
            assert all(one["form"] == 5 for one in readings) and line["world"] in worlds and worlds[line["world"]]["identity"] == line["world"]
            clear = {"reading": line["id"], "number": 0, "path": "surface", "value": {"hole": "Surface", "reason": "cleared"}}
            draft = post("edit", clear)
            assert draft["diagnostics"] == [] and draft["draft"]["phrases"][0]["terms"][0]["arguments"]["surface"] == {"hole": "Surface", "reason": "cleared"}
            assert len(get("readings")) == len(readings), "an edit saved something"
            bad = post("edit", clear | {"value": {"constant": "the search", "type": "Code", "at": [33, 43]}})
            assert bad["draft"] and bad["diagnostics"], bad
            accepted = post("accept", clear)
            assert accepted["diagnostics"] == [] and accepted["saved"]["corrections"] and len(get("readings")) == len(readings) + 1
            first = 1 + next(n for n, one in enumerate(readings) if one["id"] == line["id"])
            restored = post("restore", {"snapshot": first})
            assert restored["diagnostics"] == [] and restored["saved"]["corrections"] == [] and restored["saved"]["id"] == line["id"]
            print(f"serve: {len(readings)} readings, {len(worlds)} world(s); edit gave a draft, a wrong-typed edit gave {bad['diagnostics']}, accept saved a correction, restore saved snapshot {first}")
        finally:
            served.terminate()
    server.shutdown()


def test_judged() -> None:
    """A request whose result is words is judged by d1 against the reply, kept as a judgment with its inputs, never as execution evidence."""
    explain = "Explain the search."
    with tempfile.TemporaryDirectory() as temporary:
        folder = pathlib.Path(temporary)
        home = installed(folder, (HERE / "world.py").read_text())
        for session, (text, ops, binds, judge) in {"done": (explain, "explain", X.ABSENT, 0.9), "not done": (explain, "explain", X.ABSENT, 0.1),
                                                   "build, prose": ("Redesign the mod.", "redesign", X.MOD, 0.9)}.items():
            server, url = endpoint(Standin(X.script({text: ops}, {(text, ops, "subject" if ops == "explain" else "surface"): binds}, judge=judge), X.World("next")))
            (home / "config.json").write_text(json.dumps({"url": url, "block": True}))
            said = hook(home, {"hook_event_name": "UserPromptSubmit", "session_id": session, "prompt": text})["hookSpecificOutput"]["additionalContext"]
            reply = "The search ranks the candidates by type, then asks d1." if ops == "explain" else "I redesigned the mod."
            answer = hook(home, {"hook_event_name": "Stop", "session_id": session, "transcript_path": transcript(folder, session, text, [reply]), "last_assistant_message": reply})
            record = last_stop(home)
            server.shutdown()
            outcomes = [(one["outcome"], one["by"]) for one in record["outcomes"]]
            print(f"{session}: {outcomes}, send-back {bool(answer)}, judgments {[(one['obligation'], one['share'], one['done']) for one in record['judgments']]}")
            if ops == "explain":
                assert "evidence: d1 judges your reply (a judgment, not execution evidence)" in said, said
                judgment, = record["judgments"]
                assert judgment["state"] == f"MESSAGE:\n{text}\n\nREPLY:\n{reply}" and judgment["instructions"].startswith("The message asks the reader to explain") and judgment["answer"]["p_true"] == judge and judgment["share"] == judge
                assert record["evidence"] == [] and answer is None, "a word result judged by d1 is sent back"
                assert outcomes == ([("PASS", "d1 judged")] if judge >= 0.5 else [("UNVERIFIED", None)]), outcomes
            else:
                assert record["judgments"] == [] and outcomes == [("UNVERIFIED", None)] and answer["decision"] == "block" and "needs a file written" in answer["reason"]
        saved = [strict(line) for line in (home / "events.jsonl").read_text().splitlines()]
        assert [one["fulfillment"][0]["outcome"] for one in saved if "fulfillment" in one] == ["PASS", "UNVERIFIED", "UNVERIFIED"]


def test_non_finite() -> None:
    """A NaN in d1's raw answer is kept as the string "NaN": the line is JSON, and load still diagnoses the answer."""
    world = agree.loads((HERE / "world.py").read_text(), ROOT)
    for kind in ("nan", "infinite"):
        reading = scriptt16.read("Redesign the mod.", world, [], Standin(X.script({"Redesign the mod.": X.Malformed(kind)}), X.World("next")), join=False)
        with tempfile.TemporaryDirectory() as temporary:
            store = pathlib.Path(temporary) / "events.jsonl"
            scriptt16.save(reading, store)
            line = strict(store.read_text())
            loaded, _ = scriptt16.load(line, world)
            assert (0, None, "model_answer") in scriptt16.diagnostics(loaded), scriptt16.diagnostics(loaded)
            print(f"{kind}: the saved line is JSON; raw answer {json.dumps(line['decisions'][0]['answers'])}; load diagnoses model_answer")


def test_starter_world() -> None:
    world = agree.loads((ROOT / "scriptt/world.py").read_text(), ROOT)
    assert not world.faults and {"Asked", "Written", "Observed"} <= world.types.keys(), world.faults
    print("the shipped world.py loads with no fault:", ", ".join(world.functions))


def live() -> None:
    """1 prompt through the real d1 (never restarts or configures the service), kept with every request and response."""
    config = json.loads((ROOT / ".scriptt/config.json").read_text())
    import harness  # the wordings and the client of scriptt/harness.py, with the real config
    exchanges = []

    def real(state: str, questions: dict) -> dict:
        answers = harness.d1(state, questions, config=lambda: config)
        exchanges.append({"state": state, "questions": questions, "answers": answers})
        return answers
    server, url = endpoint(real)
    with tempfile.TemporaryDirectory() as temporary:
        folder = pathlib.Path(temporary)
        home = installed(folder, (HERE / "world.py").read_text())
        (home / "config.json").write_text(json.dumps({"url": url, "block": True}))  # the hook asks the recorder, the recorder asks the real d1
        event = {"hook_event_name": "UserPromptSubmit", "session_id": "live", "prompt": TEXT}
        answer = hook(home, event)
        line = strict((home / "events.jsonl").read_text().splitlines()[-1])
    server.shutdown()
    out = ROOT / "tests/live/prompt.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"label": "live: the real d1 of .scriptt/config.json", "d1": {k: v for k, v in config.items() if k != "key"}, "event": event,
                               "answer": answer, "line": line, "exchanges": exchanges}, indent=1) + "\n")
    print(f"LIVE ({config['url']}, {len(exchanges)} requests), saved to {out.relative_to(ROOT)}:\n" + "\n".join("  " + one for one in answer["hookSpecificOutput"]["additionalContext"].splitlines()))


if __name__ == "__main__":
    test_starter_world()
    test_non_finite()
    test_hooks()
    test_judged()
    if "--live" in sys.argv:
        live()
    print("all hook tests passed")
