#!/usr/bin/env python3
"""The scriptt harness: the hooks of Claude Code over the reader in scriptt16.py. Python 3.14 or later, standard library only.

Beside it in .scriptt/: agree.py (the type system), scriptt16.py (the reader), world.py (the world of this folder),
SKILL.md, config.json (where d1 is), events.jsonl (each reading as a form-5 line, every snapshot), hooks.jsonl (which
session sent which reading, the replies, the evidence and the blocks) and worlds/ (each world a reading was read against).

Claude Code runs it as a hook, with 1 event as JSON on stdin:
  UserPromptSubmit   scriptt16.read reads the message against world.py with d1, saves the reading, and Claude
                     receives each obligation with its call, the declared types, the open holes and the unresolved requests.
  Stop               the evidence of the turn, from the transcript only (commands with their exit codes, files written),
                     goes to scriptt16.check. The reply's words are never evidence. With "block": true in config.json a turn
                     with an obligation that is not PASS is sent back, at most 2 times for 1 message.
You run it for the rest:
  python harness.py install        add the 2 hooks and the skill to .claude/ of the folder above this one
  python harness.py serve [port]   the page, the readings, the worlds and the log, and the engine's edit, accept and restore
  python harness.py find WORDS     the phrases of every reading that have these words or this function; "?" finds the unresolved
  python harness.py world          the world as JSON (agree.world_record)
  python harness.py post /accept   what POST /accept of serve answers, with the body on stdin (also /edit, /restore, /rerun): the mod's way in

Which evidence is about which obligation (the harness's rule; scriptt16.check then applies the engine's own: an artifact
names a function and its values, and counts only for the 1 obligation that has exactly those):
  an obligation that binds a path takes the writes of that file and the commands whose text names it;
  else one whose result holds Observed (text that a run of code produced) takes every command that ran;
  else one whose result is a Path or Later[T] of no text T (work on the folder) takes every file written.
  An obligation whose result is words (Written, Words) or None (a rule to follow) is fulfilled in the reply: d1 judges the reply
  against its call with the engine's DID wording, kept as a judgment with its exact inputs, never as execution evidence;
  PASS at Limits.yes or more, else UNVERIFIED. Anything else, and every unresolved request, stays UNVERIFIED.
With "block": true, a turn goes back only for an obligation that is FAIL, or UNVERIFIED with a result that is no words.
The last run of each command and the last write of each file count. A command passes with exit code 0, a write when the file exists.
"""

import dataclasses
import json
import pathlib
import re
import sys
import urllib.request

VERSION = "0.2.0"
HOME = pathlib.Path(__file__).resolve().parent
STORE = HOME / "events.jsonl"
LOG = HOME / "hooks.jsonl"
WORLDS = HOME / "worlds"
BLOCKS = 2  # the most times that 1 message sends a turn back

# ---- The wordings that scriptt16 asks d1 with. Each was compared with others with the real d1-2b (tests/README.md). ----
WHAT = "What does this text ask the reader to do?"
ELSE = {"none": "something else that it asks the reader to do or to answer", "nothing": "nothing: it is a remark, a reason, a rule or a greeting"}
NAMES = lambda name, f: t"The text asks the reader to {f}. Which {name} does the text name for that?"
IS = lambda value, name, f: t'The message asks the reader to {f}. In the message, are the words "{value}" the {name} for that?'
DID = lambda f: t"The message asks the reader to {f}. Does the reply do it, or say that it is done?"


def yes(question) -> dict:
    """A yes/no question for d1 from a wording: its text with each slot filled."""
    return {"type": "boolean", "instructions": "".join(piece if isinstance(piece, str) else str(piece.value) for piece in question)}


sys.modules.setdefault("harness", sys.modules[__name__])  # run as a hook, this file is __main__: scriptt16 imports it as harness
sys.path.insert(0, str(HOME) if (HOME / "scriptt16.py").exists() else str(HOME.parent / "next"))  # installed: beside it; in the repository: next/, the 1 copy
import agree  # noqa: E402
import scriptt16  # noqa: E402


def config() -> dict:
    return json.loads((HOME / "config.json").read_text())


def d1(state: str, questions: dict, config=config) -> dict:
    """Asks d1 the questions {id: question} about the state, at most 32 in 1 request. Returns {id: answer}. config.json says where d1 is."""
    config = config()
    key = config.get("key") or ("key_file" in config and pathlib.Path(config["key_file"]).expanduser().read_text().strip())
    listed = config["url"].endswith("/decide")  # CoreAI takes a list of questions with ids. A System One endpoint takes a dict.
    answers, ids = {}, list(questions)
    for start in range(0, len(ids), 32):
        some = {id: questions[id] for id in ids[start:start + 32]}
        body = config.get("body", {}) | {"state": state, "questions": [{"id": id} | q for id, q in some.items()] if listed else some}
        request = urllib.request.Request(config["url"], json.dumps(body).encode(), {"Content-Type": "application/json"} | ({"Authorization": f"Bearer {key}"} if key else {}))
        with urllib.request.urlopen(request, timeout=30) as reply:
            got = json.load(reply)["answers"]
        answers |= {answer["id"]: answer for answer in got} if listed else got
    return answers


# ---- The files beside this one ----
def lines(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def note(line: dict) -> None:
    import datetime
    with LOG.open("a") as file:
        file.write(json.dumps({"at": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"), "harness": VERSION} | line) + "\n")


def store() -> pathlib.Path:
    """The store of readings. A log of the old harness (form 3) is moved aside once, so that every line is form 5."""
    if STORE.exists() and any(line.get("form") != 5 for line in lines(STORE)):
        STORE.rename(HOME / "events-form3.jsonl")
    return STORE


def world(identity: str | None = None) -> agree.World:
    """The world of this folder now, or the world with this identity that a reading was read against."""
    source = (WORLDS / f"{identity}.py").read_text() if identity and (WORLDS / f"{identity}.py").exists() else (HOME / "world.py").read_text()
    return agree.loads(source, HOME.parent)


def latest(reading: str) -> dict | None:
    """The last snapshot of a reading in the store."""
    return next((line for line in reversed(scriptt16.saved(store())) if line["id"] == reading), None)


# ---- What Claude receives ----
REASONS = {"rejected": "d1 chose none of the candidates", "no candidate": "nothing before it in the message has this type",
           "bounded": "d1 rejected the candidates it was offered and a limit cut the others", "invalid answer": "d1's answer was malformed",
           "cleared": "cleared by an edit", "dangling reference": "it named an operation that does not exist", "invalid saved value": "the saved value had the wrong type"}


def call(term, top: bool = True) -> str:
    """A term as a call. The result of another obligation is its number, an open hole is ..., a deliberate absence is None."""
    match term:
        case scriptt16.Application(number=number) if not top and number is not None:
            return f"#{number}"
        case scriptt16.Application(function=function, arguments=arguments):
            return f"{function.name}({', '.join(f'{name}={call(one, False)}' for name, one in arguments.items())})"
        case scriptt16.Record(product=product, fields=fields):
            return f"{product.name}({', '.join(f'{name}={call(one, False)}' for name, one in fields.items())})"
        case scriptt16.Several(terms=terms):
            return f"[{', '.join(call(one, False) for one in terms)}]"
        case scriptt16.Empty():
            return "None"
        case scriptt16.Hole():
            return "..."
    return scriptt16.say(term)


def declared(kind) -> str:
    """A type of the world with what it holds: the words of each member, or its alternatives."""
    if isinstance(kind, agree.Sum) and kind.name:
        return f"{kind.name} = " + " | ".join(repr(one.words) if isinstance(one, agree.Member) else agree.show(one) for one in kind.alternatives)
    return ""


def values(term: scriptt16.Application) -> list:
    """Every value that an operation binds, with the members of each collection."""
    return [inner for one in scriptt16.bindings(term).values() for inner in (one.terms if isinstance(one, scriptt16.Several) else (one,))]


def takes(term: scriptt16.Application) -> tuple[set[str], set[str]]:
    """The evidence that can be about an operation: the paths that it binds, else the kinds ("ran", "wrote") that its result admits."""
    paths = {str(one.value) for one in values(term) if isinstance(one, scriptt16.Constant) and isinstance(one.value, pathlib.Path)}
    if paths:
        return paths, {"ran", "wrote"}
    result, inner = term.function.result, []
    parts = [result]
    while parts:
        one = parts.pop()
        inner.append(one)
        parts += [one.argument] if isinstance(one, agree.Applied) else [alt for alt in one.alternatives if not isinstance(alt, agree.Member)] if isinstance(one, agree.Sum) else [one.of] if isinstance(one, agree.Brand) else []
    observed = any(isinstance(one, agree.Brand) and one.name == "Observed" for one in inner)
    text = lambda one: text(one.of) if isinstance(one, agree.Brand) else isinstance(one, agree.Base) and one.python is str
    worked = (isinstance(result, agree.Base) and result.python is pathlib.Path) or (isinstance(result, agree.Applied) and result.constructor == agree.LATER and not text(result.argument))
    return set(), ({"ran"} if observed else set()) | ({"wrote"} if worked else set())


def words(term: scriptt16.Application) -> bool:
    """Decides whether an operation's result is words (Written, Words) or None (a rule to follow): its fulfilment is in the reply."""
    text = lambda one: one.name != "Observed" and text(one.of) if isinstance(one, agree.Brand) else isinstance(one, agree.Base) and one.python in (str, type(None))
    return text(term.function.result)  # Observed is words too, but a run of code produced them: that is execution


def needs(term) -> str:
    if isinstance(term, scriptt16.Unresolved):
        return "no evidence can show it"
    if words(term):
        return "d1 judges your reply (a judgment, not execution evidence)"
    paths, kinds = takes(term)
    if paths:
        return "a write of " + " or ".join(sorted(paths)) + ", or a command that names it"
    return {frozenset({"ran"}): "a command that runs and exits 0", frozenset({"wrote"}): "a file written", frozenset({"ran", "wrote"}): "a command that exits 0 or a file written"}.get(frozenset(kinds), "no evidence of a turn can show it")


def render(reading: scriptt16.Reading) -> str:
    """The reading for Claude: each obligation with its call and its words, the declared types, the open holes, the unresolved requests."""
    found = scriptt16.obligations(reading)
    terms = [term for _, term in found]
    lines_ = [f"scriptt: d1 read this message against .scriptt/world.py (reading {reading.id[:8]}). Obligations: {len(terms)}."]
    for phrase, term in found:
        words = " ".join(reading.text[phrase.start:phrase.end].split())[:100]
        if isinstance(term, scriptt16.Unresolved):
            lines_.append(f'#{term.number} ?   "{words}"')
        else:
            pending = "  (pending)" if scriptt16.pending(term) else ""
            lines_.append(f'#{term.number} {call(term)} -> {agree.show(term.function.result)}{pending}   "{words}"   evidence: {needs(term)}')
    functions = {term.function.name: term.function for term in terms if isinstance(term, scriptt16.Application)}
    if functions:
        lines_.append("Declared in world.py:")
        lines_ += [f"  def {f.name}({', '.join(f'{name}: {agree.show(kind)}' for name, kind in f.parameters)}) -> {agree.show(f.result)}   {' '.join(f.asks.split())}" for f in functions.values()]
        named = {agree.show(kind): text for f in functions.values() for _, kind in f.parameters if (text := declared(kind))}
        lines_ += [f"  {text}" for text in named.values()]
    holes = [f"  #{term.number} {term.function.name}.{path}: {agree.show(one.type)}, {REASONS.get(one.reason, one.reason)}"
             for term in terms if isinstance(term, scriptt16.Application) for path, one in scriptt16.bindings(term).items() if isinstance(one, scriptt16.Hole)]
    if holes:
        lines_ += ["Open holes, each a ... above. Fill each from the conversation, or ask for that 1 thing:", *holes]
    unresolved = [term for term in terms if isinstance(term, scriptt16.Unresolved)]
    if unresolved:
        lines_ += ["Unresolved requests, each a ? above: no function of world.py fits (" + ", ".join(f"#{one.number} {REASONS.get(one.reason, one.reason)}" for one in unresolved) + ").",
                   "  For each: say in 1 line what it asks, do it, and propose the function to add to .scriptt/world.py."]
    unsure = [reading.text[one["start"]:one["end"]] for one in reading.pieces or [] if not one["sure"]]
    if unsure:  # d1 found no sure kind in world.py for these words: the world may not hold what the user means
        lines_.append(f"Words with no sure kind in world.py ({len(unsure)} of {len(reading.pieces)} pieces): " + "; ".join(" ".join(one.split())[:40] for one in unsure[:12])
                      + ". If they matter, ask what they are, or propose types for .scriptt/world.py.")
    faults = scriptt16.diagnostics(reading)
    if faults:
        lines_.append("Diagnostics: " + "; ".join(f"#{number} {path or ''} {rule}".replace("  ", " ") for number, path, rule in faults))
    if not terms:
        lines_.append("The message asks for no operation of the world.")
    else:
        lines_.append("At the end of the turn each obligation is checked: work by evidence only (the commands you ran, the files you wrote; your words are not evidence of work), an answer or a rule by d1's judgment of your reply.")
    return "\n".join(lines_)


# ---- The evidence of a turn ----
def evidence(transcript: str | None, prompt: str) -> list[dict]:
    """The commands run (with exit codes) and the files written or edited, after the message in the transcript, the last of each."""
    try:
        entries = [entry for entry in map(json.loads, filter(str.strip, pathlib.Path(transcript).read_text().splitlines())) if entry.get("type") in ("user", "assistant") and not entry.get("isSidechain")]
    except (OSError, TypeError, ValueError):
        return []
    blocks = lambda entry: entry.get("message", {}).get("content") if isinstance(entry.get("message", {}).get("content"), list) else [{"type": "text", "text": entry.get("message", {}).get("content") or ""}]
    said = lambda entry: "".join(block.get("text", "") for block in blocks(entry) if block.get("type") == "text").strip()
    asked = [n for n, entry in enumerate(entries) if entry["type"] == "user" and not any(block.get("type") == "tool_result" for block in blocks(entry))]
    start = next((n for n in reversed(asked) if said(entries[n]) == prompt.strip()), asked[-1] if asked else -1)
    uses, results = {}, {}
    for entry in entries[start + 1:]:
        for block in blocks(entry):
            if block.get("type") == "tool_use":
                uses[block["id"]] = (block.get("name"), block.get("input") or {})
            elif block.get("type") == "tool_result":
                content = block.get("content")
                text = content if isinstance(content, str) else "".join(one.get("text", "") for one in content or [] if isinstance(one, dict))
                results[block.get("tool_use_id")] = (bool(block.get("is_error")), text)
    found = {}
    for id, (name, given) in uses.items():
        if id not in results:
            continue  # it never finished
        error, text = results[id]
        if name == "Bash" and given.get("command"):
            code = re.match(r"Exit code (\d+)", text)
            found["ran", given["command"]] = {"ran": given["command"], "exit": int(code[1]) if code else 1 if error else 0}
        elif name in ("Write", "Edit", "MultiEdit", "NotebookEdit") and (path := given.get("file_path") or given.get("notebook_path")):
            found.pop(("wrote", path), None)
            found["wrote", path] = {"wrote": path, "ok": not error}
    return list(found.values())


def about(term: scriptt16.Application, item: dict, folder: pathlib.Path) -> bool:
    """Decides by the rule of this file whether an item of evidence can be about an operation."""
    paths, kinds = takes(term)
    if paths:
        return ("wrote" in item and pathlib.Path(item["wrote"]).resolve() in {(folder / one).resolve() for one in paths}) or ("ran" in item and any(one in item["ran"] for one in paths))
    return ("ran" if "ran" in item else "wrote") in kinds


def holds(item: dict, folder: pathlib.Path) -> bool:
    return item["exit"] == 0 if "ran" in item else item["ok"] and (folder / item["wrote"]).exists()


# ---- The hooks ----
def prompt(event: dict, model) -> dict:
    session, text = event.get("session_id"), event["prompt"]
    source = (HOME / "world.py").read_text()
    here = agree.loads(source, HOME.parent)
    if here.faults:
        said = "scriptt: .scriptt/world.py has faults, so this message was not read. Fix them (python3.14 .scriptt/harness.py world):\n" + "\n".join(f"  {text}" for _, _, text in here.faults)
        return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": said}}
    replies = [line["reply"] for line in lines(LOG) if line.get("session") == session and line.get("reply")][-scriptt16.Limits().replies:]
    reading = scriptt16.typed(scriptt16.read(text, here, replies, model), here, model)
    reading, _ = scriptt16.save(reading, store())
    WORLDS.mkdir(exist_ok=True)
    if not (WORLDS / f"{reading.world}.py").exists():
        (WORLDS / f"{reading.world}.py").write_text(source)
    note({"event": "UserPromptSubmit", "session": session, "reading": reading.id, "snapshot": reading.base, "world": reading.world})
    return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": render(reading)}}


def stop(event: dict, model) -> dict | None:
    session, reply = event.get("session_id"), event.get("last_assistant_message") or ""
    mine = [line for line in lines(LOG) if line.get("session") == session]
    asked = next((line for line in reversed(mine) if line["event"] == "UserPromptSubmit"), None)
    line, answer = {"event": "Stop", "session": session, "reply": reply}, None
    saved = asked and latest(asked["reading"])
    reading = saved and scriptt16.load(saved, world(saved["world"]))[0]
    if reading:
        folder = HOME.parent
        items = evidence(event.get("transcript_path"), reading.text)
        state = f"MESSAGE:\n{reading.text}\n\nREPLY:\n{reply}"  # the state and the wording of check's own question to d1
        spoken = {term.number: term for _, term in scriptt16.obligations(reading) if isinstance(term, scriptt16.Application) and words(term)}
        questions = {f"did {number}": yes(DID(f"{term.function.asks}: {scriptt16.say(term)}")) for number, term in spoken.items()}
        given = model(state, questions) if questions else {}
        judgments = []
        for number in spoken:
            answer_ = given.get(f"did {number}") if isinstance(given, dict) else None
            share = scriptt16.answer(scriptt16.YesNo(questions[f"did {number}"]["instructions"]), answer_)
            judgments.append({"obligation": number, "state": state, "instructions": questions[f"did {number}"]["instructions"], "options": None, "answer": answer_, "share": share,
                              "done": share is not None and share >= scriptt16.Limits().yes})
        known = {(state, questions[key]["instructions"]): given.get(key) for key in questions if isinstance(given, dict)}

        def once(state_: str, asked: dict) -> dict:  # check asks the same question again: it gets the answer that d1 already gave
            new = {key: q for key, q in asked.items() if (state_, q["instructions"]) not in known}
            got = model(state_, new) if new else {}
            return {key: known[state_, q["instructions"]] if (state_, q["instructions"]) in known else got.get(key) for key, q in asked.items()}

        artifacts, of = [], {}
        for item in items + [{"judged": one["obligation"]} for one in judgments if one["done"]]:
            for _, term in scriptt16.obligations(reading):
                if isinstance(term, scriptt16.Application) and (term.number == item["judged"] if "judged" in item else not words(term) and about(term, item, folder)):
                    artifacts.append(artifact := scriptt16.Artifact(term.function.name, scriptt16.bindings(term)))
                    of[id(artifact)] = item
        criterion = lambda term, artifact: "judged" in of[id(artifact)] or holds(of[id(artifact)], folder)  # a judgment artifact exists only for a done
        reading, verdict, _ = scriptt16.check(reading, reply, artifacts, [("evidence", criterion)], once)
        reading, _ = scriptt16.save(reading, store())
        terms = {term.number: term for _, term in scriptt16.obligations(reading)}
        executable = lambda number: isinstance(terms[number], scriptt16.Application) and not words(terms[number])
        sent_back = [one for one in reading.fulfillment if one.outcome == scriptt16.FAIL or (one.outcome == scriptt16.UNVERIFIED and executable(one.obligation))]
        blocks = sum(1 for one in mine if one["event"] == "Stop" and one.get("reading") == reading.id and one.get("blocked"))
        blocked = bool(config().get("block")) and bool(sent_back) and blocks < BLOCKS
        line |= {"reading": reading.id, "snapshot": reading.base, "evidence": items, "judgments": judgments,
                 "artifacts": [[artifact.function, {path: call(one, False) for path, one in artifact.arguments.items()}, {"judged": of[id(artifact)]["judged"]} if "judged" in of[id(artifact)] else items.index(of[id(artifact)])] for artifact in artifacts],
                 "verdict": verdict, "outcomes": [{"obligation": one.obligation, "outcome": one.outcome, "evidence": one.evidence, "claim": one.claim,
                                                   "by": None if one.evidence is None else "d1 judged" if "judged" in of[id(artifacts[one.evidence])] else "execution"} for one in reading.fulfillment],
                 "blocked": blocked, "blocks": blocks + blocked}
        if blocked:
            failed = lambda one: (lambda item: f"`{item['ran'][:80]}` exited {item['exit']}" if "ran" in item else f"the write of {item['wrote']} did not hold")(of[id(artifacts[one.evidence])])
            open_ = [f"#{one.obligation} {call(terms[one.obligation])} {one.outcome}: " + (failed(one) if one.outcome == scriptt16.FAIL else f"needs {needs(terms[one.obligation])}") for one in sent_back]
            answer = {"decision": "block", "reason": f"scriptt: by the evidence of this turn, {len(open_)} of {len(terms)} obligations are not done (send-back {blocks + 1} of {BLOCKS}). "
                                                     "Your words are not evidence of work; a command that ran or a file that was written is.\n" + "\n".join(open_) + "\nDo each one, or say in 1 line why you do not."}
    note(line)
    return answer


def handle(event: dict, model=d1) -> dict | None:
    """1 event in, the answer for Claude Code out."""
    match event.get("hook_event_name"):
        case "UserPromptSubmit":
            return prompt(event, model)
        case "Stop":
            return stop(event, model)
    return None


# ---- The commands ----
def install():
    """Add the 2 hooks to .claude/settings.local.json of the folder above this one, copy the skill, and write config.json if there is none."""
    settings = HOME.parent / ".claude" / "settings.local.json"
    settings.parent.mkdir(exist_ok=True)
    data = json.loads(settings.read_text()) if settings.exists() else {}
    hook = {"hooks": [{"type": "command", "command": f'"{sys.executable}" "{HOME / "harness.py"}"', "timeout": 120}]}
    for name in ("UserPromptSubmit", "Stop"):
        entries = data.setdefault("hooks", {}).setdefault(name, [])
        entries[:] = [entry for entry in entries if "harness.py" not in json.dumps(entry)] + [hook]
    settings.write_text(json.dumps(data, indent=2) + "\n")
    if (HOME / "SKILL.md").exists():
        (settings.parent / "skills" / "scriptt").mkdir(parents=True, exist_ok=True)
        (settings.parent / "skills" / "scriptt" / "SKILL.md").write_text((HOME / "SKILL.md").read_text())
    if not (HOME / "config.json").exists():
        (HOME / "config.json").write_text(json.dumps({"url": "http://127.0.0.1:8791/v1/systemone", "body": {"model": "d1-2B-MLX-8bit"}, "block": False}, indent=2) + "\n")
    store()
    faults = world().faults
    print(f"hooks are in {settings}\nd1 is set in {HOME / 'config.json'}" + "".join(f"\nworld.py fault: {text}" for _, _, text in faults))


# ---- The engine's edits, for serve and for the mod ----
plain = lambda found: [list(one) for one in found]


def edited(body: dict, correction: bool) -> tuple:
    saved = latest(body["reading"])
    here = world(saved["world"])
    reading, found = scriptt16.load(saved, here)
    if reading is None:
        return None, found
    if body["path"] == "kind":  # the user's kind for the words at [start, end]: a type, a constructed type, a function or "(none)"
        return scriptt16.retag(reading, *body["at"], body["value"], here)
    made_by = {term.number: term for _, term in scriptt16.obligations(reading) if isinstance(term, scriptt16.Application)}
    try:
        value = None if body.get("value") is None else scriptt16.term_from(body["value"], here, made_by)
    except LookupError:  # a value that no type, member or operation of the world holds: the engine's own rule, the base kept
        return None, [(body.get("number"), body["path"], "reference" if "ref" in body["value"] else "type")]
    return scriptt16.edit(reading, body.get("number"), body["path"], value, correction, here, tuple(body["phrase"]) if body.get("phrase") else None)


def posted(path: str, body: dict) -> dict:
    """The engine's edit, accept and restore over the store, for serve and for `harness.py post PATH` (the mod)."""
    match path:
        case "/edit":
            draft, found = edited(body, False)
            return {"draft": draft and scriptt16.record(draft), "diagnostics": plain(found)}
        case "/accept":
            draft, found = edited(body, True)
            if draft and not found:
                draft, found = scriptt16.save(draft, store())
            return {"saved": latest(body["reading"]) if not found else None, "diagnostics": plain(found)}
        case "/restore":
            chosen = scriptt16.saved(store())[int(body["snapshot"]) - 1]
            reading, found = scriptt16.restore(store(), int(body["snapshot"]), world(chosen["world"]))
            if reading is not None:
                reading, found = scriptt16.save(reading, store())
            return {"saved": latest(chosen["id"]) if reading is not None and not found else None, "diagnostics": plain(found)}
        case "/rerun":  # read the saved source again with d1 and re-apply each correction: retained, or invalidated with its reason
            lines_ = scriptt16.saved(store())
            chosen = lines_[int(body["snapshot"]) - 1] if body.get("snapshot") else latest(body["reading"])
            again = scriptt16.rerun(chosen, world(chosen["world"]), d1)
            again = dataclasses.replace(again, id=chosen["id"], base=latest(chosen["id"])["snapshot"])  # a new snapshot of the same reading
            again, found = scriptt16.save(again, store())
            return {"saved": latest(chosen["id"]) if not found else None, "corrections": again.corrections, "diagnostics": plain(found + scriptt16.diagnostics(again))}
    raise LookupError(path)


def serve(port: int):
    """The page and the engine, on this computer only. Every meaning comes from scriptt16; the server only moves records.

    GET  /readings   every snapshot in the store (form 5)        GET /worlds   agree.world_record of each world, by identity
    GET  /log        hooks.jsonl                                 GET /<file>   the page
    POST /edit       {reading, number, path, value, phrase?} -> {draft, diagnostics}; nothing is saved
                     {reading, path: "kind", at: [start, end], value: a kind} gives those words that kind (scriptt16.retag)
    POST /accept     the same, as a correction; saved when it has no diagnostics -> {saved, diagnostics}
    POST /restore    {snapshot: n from 1} -> {saved, diagnostics}: the n-th snapshot becomes the latest
    POST /rerun      {reading} or {snapshot: n from 1} -> {saved, corrections, diagnostics}: the source read again with d1,
                     each correction retained or invalidated with its reason, saved as a new snapshot of that reading
    The page is HOME/site if it exists (a lab folder can link it to a board's web/site), else web/site beside this folder.
    A value is a term as a record writes it ({"constant", "type", "at"}, {"ref"}, {"hole", "reason"}, ...), or null to remove the binding.
    """
    from http.server import BaseHTTPRequestHandler, HTTPServer

    site = next((folder for folder in (HOME / "site", HOME.parent / "web" / "site") if folder.exists()), None)
    class Page(BaseHTTPRequestHandler):
        def reply(self, body: bytes, kind: str = "application/json", status: int = 200):
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            name = self.path.split("?")[0].strip("/") or "index.html"
            data = {"readings": lambda: scriptt16.saved(store()), "log": lambda: lines(LOG),
                    "worlds": lambda: {one.stem: agree.world_record(world(one.stem)) for one in sorted(WORLDS.glob("*.py"))} | {agree.identity(world()): agree.world_record(world())}}
            if name in data:
                return self.reply(json.dumps(data[name]()).encode())
            try:
                if site and (site / name).resolve().is_relative_to(site.resolve()) and (site / name).is_file():
                    body = (site / name).read_bytes()
                else:  # no copy of the page on this computer: the public one
                    body = urllib.request.urlopen("https://scriptt.ai/" + urllib.request.quote(name), timeout=30).read()
            except OSError:
                return self.send_error(404)
            self.reply(body, {"html": "text/html; charset=utf-8", "js": "text/javascript"}.get(name.rsplit(".", 1)[-1], "text/plain"))

        def do_POST(self):
            if self.headers.get("Origin", f"http://127.0.0.1:{port}") not in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
                return self.send_error(403)
            try:
                answer = posted(self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            except (LookupError, ValueError, TypeError, IndexError, AttributeError) as error:
                return self.reply(json.dumps({"error": f"{type(error).__name__}: {error}"}).encode(), status=400)
            self.reply(json.dumps(answer).encode())

        def log_message(self, *args):
            pass

    print(f"http://127.0.0.1:{port}", flush=True)
    HTTPServer(("127.0.0.1", port), Page).serve_forever()


def find(words: list) -> None:
    """Print each phrase of the latest snapshot of each reading that has all these words in its text or among its functions. "?" finds the unresolved."""
    readings = {line["id"]: line for line in scriptt16.saved(store())}
    for line in readings.values():
        for phrase in line["phrases"]:
            tags = [term["function"] for term in phrase["terms"]] + ["?"] * len(phrase["unresolved"])
            said = " ".join(line["text"][phrase["start"]:phrase["end"]].split())
            if tags and all(word in tags or (word != "?" and word.lower() in said.lower()) for word in words):
                print(f'{line["id"][:8]}  [{" + ".join(tags)}]  {said[:160]}')


if __name__ == "__main__":
    match sys.argv[1:]:
        case ["install"]:
            install()
        case ["find", *words]:
            find(words)
        case ["world"]:
            print(json.dumps(agree.world_record(world())))
        case ["post", path]:  # the body as JSON on stdin, the answer as JSON on stdout: what POST path of serve answers
            print(json.dumps(posted(path, json.load(sys.stdin))))
        case ["serve", *port]:
            serve(int(port[0]) if port else 8787)
        case _:
            try:
                answer = handle(json.load(sys.stdin))
            except Exception as error:  # a hook must not stop the session: say what failed and let Claude go on
                sys.exit(print(f"scriptt: {type(error).__name__}: {error}", file=sys.stderr))
            if answer is not None:
                print(json.dumps(answer))
