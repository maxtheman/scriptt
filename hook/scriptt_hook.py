#!/usr/bin/env python3
"""The scriptt hook for Claude Code. It reads one event as JSON on stdin and prints its answer as JSON on stdout.

UserPromptSubmit   reads your message into a typed template, and tells Claude what the message wants and supplies
Stop               reads Claude's reply the same way, and compares it with what the message wanted

Environment:
  SCRIPTT_D1_URL       a System One endpoint, for example http://127.0.0.1:8790 (no default)
  SCRIPTT_D1_MODEL     the model name to send (default d1-2B-MLX-8bit)
  SCRIPTT_D1_KEY       an API key, if the endpoint needs one
  SCRIPTT_D1_ANSWERS   a JSON file of recorded answers, used in place of an endpoint (tests and the demo)
  SCRIPTT_HOOK_HOME    where the hook writes its state and events.jsonl (default ~/.claude/scriptt-hook)
  SCRIPTT_HOOK_BLOCK   set to 1 to stop Claude from ending a turn while a wanted part has no reply
With no endpoint and no recorded answers the hook records the event and prints nothing.
"""

import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import d1 as d1_module
import program


def d1_from_environment():
    if path := os.environ.get("SCRIPTT_D1_ANSWERS"):
        return d1_module.recorded(json.loads(pathlib.Path(path).read_text()))
    if url := os.environ.get("SCRIPTT_D1_URL"):
        return d1_module.system_one(url, os.environ.get("SCRIPTT_D1_MODEL", "d1-2B-MLX-8bit"), os.environ.get("SCRIPTT_D1_KEY", ""))
    return None


def context_for_claude(r):
    lines = ["scriptt hook: this message, read as types."]
    wanted = [f"{s['wants']} (the result of {s['state'][7:]}, from \"{s['words']}\")" if "wants" in s else f"{s['class']} \"{s['words']}\"" for s in r["slots"] if s["state"] != "given"]
    given = [f"{s['class']} \"{s['words']}\"" for s in r["slots"] if s["state"] == "given"]
    lines.append("wanted: " + ("; ".join(wanted) or "nothing was found"))
    lines.append("given: " + ("; ".join(given) or "nothing was found"))
    lines.append("not typed: " + " | ".join(text.strip() for text in r["not typed"]))
    return "\n".join(lines)


def handle(event, d1):
    home = pathlib.Path(os.environ.get("SCRIPTT_HOOK_HOME", pathlib.Path.home() / ".claude/scriptt-hook"))
    home.mkdir(parents=True, exist_ok=True)
    name = event.get("hook_event_name")
    who, text = {"UserPromptSubmit": ("user", event.get("prompt")), "Stop": ("assistant", event.get("last_assistant_message"))}.get(name, (None, None))
    if not text:
        return None
    state_file = home / f"{event.get('session_id', 'session')}.json"
    record = {"event": name, "who": who, "text": text, "d1": d1 is not None}
    answer = None
    if d1 is not None:
        typed, log = program.read(text, who, d1)
        r = program.result(typed)
        record |= r | {"questions": log}
        if who == "user":
            state_file.write_text(json.dumps({"holes": r["holes"], "text": text}))
            answer = {"hookSpecificOutput": {"hookEventName": name, "additionalContext": context_for_claude(r)}}
        elif state_file.exists():
            wanted = json.loads(state_file.read_text())["holes"]
            supplied = {slot["class"] for slot in r["slots"]}
            record["supplies"] = {hole: hole in supplied for hole in wanted}
            missing = sorted({hole for hole in wanted if hole not in supplied})
            if missing and os.environ.get("SCRIPTT_HOOK_BLOCK") == "1" and not event.get("stop_hook_active"):
                answer = {"decision": "block", "reason": "scriptt hook: the message wanted these and the reply has none of them: " + ", ".join(missing)}
    record["answer"] = answer
    with (home / "events.jsonl").open("a") as events:
        events.write(json.dumps(record) + "\n")
    return answer


def load_config():
    """Settings can also be in config.json in the hook's home: {"SCRIPTT_D1_URL": "...", ...}. The environment wins."""
    config = pathlib.Path(os.environ.get("SCRIPTT_HOOK_HOME", pathlib.Path.home() / ".claude/scriptt-hook")) / "config.json"
    if config.exists():
        for name, value in json.loads(config.read_text()).items():
            os.environ.setdefault(name, str(value))


if __name__ == "__main__":
    try:
        load_config()
        answer = handle(json.load(sys.stdin), d1_from_environment())
    except Exception as error:  # a hook must not break the session: say what failed and let Claude go on
        print(f"scriptt hook: {type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(0)
    if answer is not None:
        print(json.dumps(answer))
