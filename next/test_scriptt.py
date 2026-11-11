"""The tests of scriptt: the engine, the hooks of an install in a temporary folder, and the local server.

    python3.14 next/test_scriptt.py

d1 is a scripted stand-in (``Scripted``) that answers each question by the option descriptions it is given, as the real
d1 receives them. It answers behind an HTTP endpoint in the shape of CoreAI's /v1/decide, and harness.py runs as Claude Code
runs it: a process with one event on stdin.
"""

import http.server
import json
import math
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
import scriptt16  # noqa: E402

PYTHON = sys.executable
WORLD = agree.loads((HERE / "world.py").read_text(), ROOT)
TEXT = "Redesign the mod. Test the search too."
ALSO = scriptt16.ALSO.rpartition("}")[2]


class Scripted:
    """A stand-in d1. ``wants`` maps a sentence to what it asks for: function names, member or text words, "ref:f" for the
    result of an earlier f, "none" for a request no function fits, "absent" for an argument left out on purpose.
    ``kinds`` maps words to a kind and its share; other words get (none) at 0.9. ``judge`` answers whether a reply did a request.
    """

    def __init__(self, wants: dict[str, set[str]], kinds: dict[str, tuple[str, float]] | None = None, judge: float = 0.1, broken: float | None = None):
        self.wants, self.kinds, self.judge, self.broken, self.calls = wants, kinds or {}, judge, broken, 0
        self.functions = {" ".join(f.asks.split()): name for name, f in WORLD.functions.items()}

    def __call__(self, state: str, questions: dict) -> dict:
        self.calls += 1
        want = next((value for key, value in self.wants.items() if key in state or state in key), set())
        answers = {}
        for key, question in questions.items():
            text = question["instructions"]
            if question["type"] == "boolean":
                answers[key] = {"p_true": self.judge if text.startswith("The message asks the reader to") else 0.0}
                continue
            ids = [one["id"] for one in question["options"]]
            seen = [" ".join(one["description"].split()) for one in question["options"]]
            if text.startswith(scriptt16.KIND.partition("{")[0]):
                kind, share = self.kinds.get(text.split('"')[1], (scriptt16.NONE, 0.9))
                answers[key] = {"probabilities": {kind: share} | ({scriptt16.NONE: 1 - share} if kind != scriptt16.NONE and share < 1 else {})}
                continue
            if self.broken is not None:
                answers[key] = {"probabilities": {ids[0]: self.broken}}
                continue
            def said(description: str) -> bool:
                return (self.functions.get(description) in want and not text.endswith(ALSO)) or description.strip("'\"") in want \
                    or any(one.startswith("ref:") and description.startswith(one[4:] + "(") for one in want) \
                    or ("none" in want and description == scriptt16.ELSE[scriptt16.NONE] and not text.endswith(ALSO)) or ("absent" in want and description == scriptt16.ABSENT)
            fallback = [scriptt16.ELSE[scriptt16.NOTHING], scriptt16.NONE_OF_THESE]
            chosen = next((ids[n] for n, one in enumerate(seen) if said(one)), None) or next((ids[seen.index(one)] for one in fallback if one in seen), ids[0])
            answers[key] = {"probabilities": {chosen: 1.0}}
        return answers


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


def strict(line: str) -> dict:
    """Parses a line as JSON with no NaN or Infinity."""
    return json.loads(line, parse_constant=lambda name: (_ for _ in ()).throw(ValueError(f"{name} is not JSON")))


def installed(folder: pathlib.Path) -> pathlib.Path:
    """Puts the shipped files in folder/.scriptt as install.sh does, with next/world.py as the user's own world, and runs harness.py install."""
    home = folder / ".scriptt"
    home.mkdir(parents=True)
    shutil.copyfile(HERE / "world.py", home / "world.py")
    for source in (ROOT / "scriptt/harness.py", ROOT / "scriptt/SKILL.md", HERE / "agree.py", HERE / "scriptt16.py"):
        shutil.copyfile(source, home / source.name)
    done = subprocess.run([PYTHON, str(home / "harness.py"), "install"], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    assert (home / "world.py").read_text() == (HERE / "world.py").read_text(), "the install replaced the user's world"
    return home


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


def test_worlds() -> None:
    for path in (HERE / "world.py", ROOT / "scriptt/world.py"):
        world = agree.loads(path.read_text(), ROOT)
        assert not world.faults and {"Asked", "Written", "Observed"} <= world.types.keys(), (path, world.faults)
    broken = agree.loads((HERE / "world.py").read_text() + "\n\ndef twice(x: Nowhere) -> None:\n    \"\"\"do it twice\"\"\"\n", ROOT)
    assert broken.faults, "an unknown type is no fault"


def test_engine() -> None:
    """A reference keeps the result it names, an unknown request stays unresolved, an edit is a draft, a correction survives a rerun, every word has a kind."""
    text = "Redesign the mod. Then show it. Also order a pizza."
    model = Scripted({"Redesign the mod.": {"redesign", "the mod"}, "Then show it.": {"show", "ref:redesign"}, "Also order a pizza.": {"none"}}, {"mod": ("Surface", 0.8)})
    reading = scriptt16.typed(scriptt16.read(text, WORLD, [], model), WORLD, model)
    entries = [term for _, term in scriptt16.obligations(reading)]
    redesign, show, pizza = entries
    assert redesign.function.name == "redesign" and scriptt16.say(redesign) == "redesign(surface='the mod')"
    assert show.function.name == "show" and show.arguments["subject"] is redesign, "the reference is a copy, not the result"
    assert isinstance(pizza, scriptt16.Unresolved), pizza
    assert scriptt16.pending(show) and not scriptt16.ready(reading, show) and scriptt16.ready(reading, redesign)
    assert scriptt16.diagnostics(reading) == []

    with tempfile.TemporaryDirectory() as temporary:
        store = pathlib.Path(temporary) / "events.jsonl"
        saved, _ = scriptt16.save(reading, store)
        line = strict(store.read_text())
        loaded, found = scriptt16.load(line, WORLD)
        again = scriptt16.record(loaded)
        assert not found and all(again[key] == line[key] for key in ("text", "world", "phrases", "constants", "decisions", "corrections", "pieces")), "load does not give back what was saved"

        mod = redesign.arguments["surface"]
        draft, found = scriptt16.edit(loaded, show.number, "subject", mod)
        assert not found and scriptt16.record(loaded) == scriptt16.record(scriptt16.load(line, WORLD)[0]), "an edit changed the base"
        wrong, found = scriptt16.edit(loaded, redesign.number, "surface", scriptt16.Constant(WORLD.types["Code"], "the search", 0, 0))
        assert found and found[0][2] == "type", found
        corrected, found = scriptt16.edit(loaded, show.number, "subject", mod, correction=True)
        assert not found and corrected.corrections[0]["status"] == "retained"
        scriptt16.save(corrected, store)
        again = scriptt16.rerun(scriptt16.saved(store)[-1], WORLD, model)
        assert [one["status"] for one in again.corrections] == ["retained"] and scriptt16.say(scriptt16.obligations(again)[1][1]) == "show(subject='the mod')"

    pieces = reading.pieces
    assert " ".join(text[one["start"]:one["end"]] for one in pieces).split() == [text[a:b] for a, b in scriptt16.chunks(text)]
    assert [one["sure"] for one in pieces if text[one["start"]:one["end"]] == "mod"] == [True]
    start = text.index("show it")
    for kind, rule in (("Nope", "kind"), ("Later", "kind"), ("Later[Surface]", None), ("show", None), (scriptt16.NONE, None)):
        _, found = scriptt16.retag(reading, start, start + 7, kind, WORLD)
        assert (found[0][2] if found else None) == rule, (kind, found)
    assert scriptt16.retag(reading, start + 1, start + 4, "Code", WORLD)[1] == [(None, "kind", "place")]
    retagged, _ = scriptt16.retag(reading, start, start + 7, "Later[Surface]", WORLD)
    assert reading.pieces != retagged.pieces and not reading.corrections, "the base changed"
    with tempfile.TemporaryDirectory() as temporary:
        store = pathlib.Path(temporary) / "events.jsonl"
        scriptt16.save(retagged, store)
        line = scriptt16.saved(store)[-1]
        again = scriptt16.rerun(line, WORLD, model)
        assert [one for one in again.pieces if one["by"] == "user"] == [{"start": start, "end": start + 7, "kind": "Later[Surface]", "share": None, "sure": True, "by": "user"}]
        lost = scriptt16.rerun(line | {"corrections": [one | {"kind": "Gone[Surface]"} for one in line["corrections"]]}, WORLD, model)
        assert [(one["status"], one["reason"]) for one in lost.corrections] == [("invalidated", "Gone[Surface] is no type or function of this world")]


def test_broken_answers() -> None:
    """A NaN or an infinite share from d1 is diagnosed, and the saved line is still JSON."""
    for value in (math.nan, math.inf):
        reading = scriptt16.read("Redesign the mod.", WORLD, [], Scripted({}, broken=value), join=False)
        with tempfile.TemporaryDirectory() as temporary:
            store = pathlib.Path(temporary) / "events.jsonl"
            scriptt16.save(reading, store)
            loaded, _ = scriptt16.load(strict(store.read_text()), WORLD)
            assert any(rule == "model_answer" for _, _, rule in scriptt16.diagnostics(loaded)), scriptt16.diagnostics(loaded)


def test_hooks_and_server() -> None:
    model = Scripted({"Redesign the mod.": {"redesign", "the mod"}, "Test the search too.": {"test", "the search"}},
                     {"mod": ("Surface", 0.8), "the": (scriptt16.NONE, 0.45), "too": (scriptt16.NONE, 0.45)})
    server, url = endpoint(model)
    with tempfile.TemporaryDirectory() as temporary:
        folder = pathlib.Path(temporary)
        home = installed(folder)
        settings = json.loads((folder / ".claude/settings.local.json").read_text())
        assert all(any("harness.py" in json.dumps(entry) for entry in settings["hooks"][name]) for name in ("UserPromptSubmit", "Stop"))
        (home / "config.json").write_text(json.dumps({"url": url, "block": True}))

        def prompt(session: str) -> tuple[str, dict]:
            said = hook(home, {"hook_event_name": "UserPromptSubmit", "session_id": session, "prompt": TEXT})["hookSpecificOutput"]["additionalContext"]
            line = strict((home / "events.jsonl").read_text().splitlines()[-1])
            assert line["form"] == 5 and line["text"] == TEXT and line["world"] == agree.identity(WORLD) and scriptt16.load(line, WORLD)[0]
            return said, line

        said, line = prompt("s1")
        for words in ("#0 redesign(surface='the mod') -> Later[Surface]", "#1 test(subject='the search') -> Observed", "evidence: a file written", "Words with no sure kind in world.py"):
            assert words in said, (words, said)

        # A command ran for test, no file was written for redesign: blocked twice, then let go.
        ran = transcript(folder, "ran", TEXT, [("Bash", "python3.14 -m unittest", 0), "I redesigned the mod and tested the search."])
        stop = {"hook_event_name": "Stop", "session_id": "s1", "transcript_path": ran, "last_assistant_message": "Done."}
        seen = []
        for _ in range(3):
            answer = hook(home, stop)
            record = last_stop(home)
            seen.append((answer and answer["decision"], record["blocks"], [one["outcome"] for one in record["outcomes"]]))
        assert seen == [("block", 1, ["UNVERIFIED", "PASS"]), ("block", 2, ["UNVERIFIED", "PASS"]), (None, 2, ["UNVERIFIED", "PASS"])], seen
        # Prose is no evidence. Evidence for both passes. A failing command fails its request.
        prompt("s2")
        answer = hook(home, {"hook_event_name": "Stop", "session_id": "s2", "transcript_path": transcript(folder, "words", TEXT, ["Both are done and pass."])})
        assert answer["decision"] == "block" and {one["outcome"] for one in last_stop(home)["outcomes"]} == {"UNVERIFIED"}
        prompt("s3")
        assert hook(home, {"hook_event_name": "Stop", "session_id": "s3", "transcript_path": transcript(folder, "both", TEXT, [("Write", "mod.css"), ("Bash", "python3.14 -m unittest", 0)])}) is None
        prompt("s4")
        answer = hook(home, {"hook_event_name": "Stop", "session_id": "s4", "transcript_path": transcript(folder, "failing", TEXT, [("Write", "mod.css"), ("Bash", "python3.14 -m unittest", 1)])})
        assert answer["decision"] == "block" and [one["outcome"] for one in last_stop(home)["outcomes"]] == ["PASS", "FAIL"]

        (home / "site/board").mkdir(parents=True)
        (home / "site/board/index.html").write_text("<p>the board</p>")
        served = subprocess.Popen([PYTHON, str(home / "harness.py"), "serve", "8799"], stdout=subprocess.PIPE, text=True)
        try:
            served.stdout.readline()
            get = lambda path: json.load(urllib.request.urlopen(f"http://127.0.0.1:8799/{path}"))
            post = lambda path, body: json.load(urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:8799/{path}", json.dumps(body).encode(), {"Content-Type": "application/json"})))
            page = urllib.request.urlopen("http://127.0.0.1:8799/?reading=abc")
            assert page.url.endswith("/board/?reading=abc") and page.read() == b"<p>the board</p>", page.url
            readings, worlds = get("readings"), get("worlds")
            assert worlds[line["world"]]["types"]["Surface"]["describes"] == "what the user looks at"
            clear = {"reading": line["id"], "number": 0, "path": "surface", "value": {"hole": "Surface", "reason": "cleared"}}
            assert post("edit", clear)["diagnostics"] == [] and len(get("readings")) == len(readings), "a preview saved something"
            wrong = post("edit", clear | {"value": {"constant": "the ui", "type": "Code", "at": [20, 26]}})
            assert wrong["draft"] is None and [0, "surface", "type"] in wrong["diagnostics"]
            member = post("edit", clear | {"value": {"constant": "the page", "type": "Surface", "at": [-1, -1]}})
            assert member["diagnostics"] == [] and any(one["chosen"] and one["chosen"].get("constant") == "the mod" for one in member["draft"]["decisions"] if one["path"] == "surface"), "d1's decision is lost"
            many = [clear, clear | {"value": {"constant": "the ui", "type": "Code", "at": [20, 26]}}, {"path": "kind", "at": [0, 8], "value": "Later[Surface]"}, {"path": "kind", "at": [0, 8], "value": "Nope"}]
            batch = post("edits", {"reading": line["id"], "edits": many, "drafts": False})
            assert [one["diagnostics"] for one in batch["results"]] == [post("edit", one | {"reading": line["id"]})["diagnostics"] for one in many]
            accepted = post("accept", clear)
            assert accepted["diagnostics"] == [] and accepted["saved"]["corrections"] and len(get("readings")) == len(readings) + 1
            rerun = post("rerun", {"reading": line["id"]})
            assert [one["status"] for one in rerun["corrections"]] == ["retained"], rerun
            first = 1 + next(n for n, one in enumerate(readings) if one["id"] == line["id"])
            assert post("restore", {"snapshot": first})["saved"]["corrections"] == []
            rebound = urllib.request.Request("http://127.0.0.1:8799/log", headers={"Host": "evil.example:8799"})
            try:
                urllib.request.urlopen(rebound)
                raise AssertionError("a page on another host name can read the log")
            except urllib.error.HTTPError as error:
                assert error.code == 403
            refused = urllib.request.Request("http://127.0.0.1:8799/edit", json.dumps(clear).encode(), {"Origin": "https://example.com"})
            try:
                urllib.request.urlopen(refused)
                raise AssertionError("a page from another origin can edit")
            except urllib.error.HTTPError as error:
                assert error.code == 403
        finally:
            served.terminate()
    server.shutdown()


def test_judged() -> None:
    """A request whose result is words is judged by d1 against the reply: a judgment, never execution evidence."""
    with tempfile.TemporaryDirectory() as temporary:
        folder = pathlib.Path(temporary)
        home = installed(folder)
        for session, judge, outcome in (("done", 0.9, [("PASS", "d1 judged")]), ("not done", 0.1, [("UNVERIFIED", None)])):
            server, url = endpoint(Scripted({"Explain the search.": {"explain", "absent"}}, judge=judge))
            (home / "config.json").write_text(json.dumps({"url": url, "block": True}))
            hook(home, {"hook_event_name": "UserPromptSubmit", "session_id": session, "prompt": "Explain the search."})
            reply = "The search ranks the candidates by type."
            answer = hook(home, {"hook_event_name": "Stop", "session_id": session, "transcript_path": transcript(folder, session, "Explain the search.", [reply]), "last_assistant_message": reply})
            record = last_stop(home)
            server.shutdown()
            assert answer is None and record["evidence"] == [] and [(one["outcome"], one["by"]) for one in record["outcomes"]] == outcome, record


if __name__ == "__main__":
    for test in (test_worlds, test_engine, test_broken_answers, test_hooks_and_server, test_judged):
        test()
        print("passed", test.__name__)
