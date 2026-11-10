# The scriptt hook

A Claude Code hook that reads each message as a typed template.

- A message is a demand for a computation. The hook finds the ranges of the message that stand for something,
  and assigns each one a class from **the world** (`world.py`).
- A range that the world has a value for is **given**. A range with only a class is a **hole**: the message
  wants it. A verb that names a function of the world wants the result of that function.
- When Claude stops, the hook reads the reply the same way and checks that it has something of each wanted class.

**The public release of the d1 model is pending.** The hook asks a d1 model for ranges of text. Until the
release, connect it to any System One endpoint (below) or run it with recorded answers. With neither, the hook
records the event and prints nothing.

## Files

- `scriptt_hook.py`: the script that Claude Code runs: one event as JSON on stdin, its answer as JSON on stdout
- `world.py`: the classes, the things that have a name, and the functions between classes
- `program.py`: `read` (the two loops) and `result`
- `d1.py`: a System One endpoint, or recorded answers
- `tests/`: 36 recorded events and the answer each one must give
- `skills/scriptt-hook/SKILL.md`, `hooks/hooks.json`, `.claude-plugin/plugin.json`: the same hook as a Claude Code plugin with a skill

It needs Python 3.14 or later (it uses t-string templates) and only the standard library.

## Events

### UserPromptSubmit

Reads `prompt` and `session_id`. For each class of the world it asks d1 "Which words are <the docstring of the
class>?" again and again until d1 finds no more. It prints:

```json
{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "scriptt hook: this message, read as types.\nwanted: Notebook (the result of delete, from \"get rid of\")\ngiven: Notebook \"the old cells\"\nnot typed: Oh, can you please | ?"}}
```

Claude receives the `additionalContext` with the message.

### Stop

Reads `last_assistant_message`, `session_id` and `stop_hook_active`. It reads the reply the same way and compares
its classes with what the last message wanted. By default it prints nothing. With `SCRIPTT_HOOK_BLOCK=1`, and when
a wanted class is missing, it prints:

```json
{"decision": "block", "reason": "scriptt hook: the message wanted these and the reply has none of them: Notebook"}
```

It never blocks when `stop_hook_active` is true, so it cannot loop.

Every event is also written to `events.jsonl` in `SCRIPTT_HOOK_HOME`, with its slots, its holes and each question
that d1 was asked. The website shows these records.

## Install

As a plugin:

```bash
claude --plugin-dir /path/to/scriptt-release/hook
```

Or in `~/.claude/settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "python3 /path/to/hook/scriptt_hook.py", "timeout": 60}]}],
    "Stop": [{"hooks": [{"type": "command", "command": "python3 /path/to/hook/scriptt_hook.py", "timeout": 60}]}]
  }
}
```

## Connect a d1 model

Set these in the environment that Claude Code runs in:

- `SCRIPTT_D1_URL`: a System One endpoint, for example `http://127.0.0.1:8790`
- `SCRIPTT_D1_MODEL`: the model name to send (default `d1-2B-MLX-8bit`)
- `SCRIPTT_D1_KEY`: an API key, sent as a Bearer token, if the endpoint needs one
- `SCRIPTT_D1_ANSWERS`: a JSON file of recorded answers `{"ClassName": ["words", ...]}`, used in place of an endpoint
- `SCRIPTT_HOOK_HOME`: where the hook writes its state and `events.jsonl` (default `~/.claude/scriptt-hook`)
- `SCRIPTT_HOOK_BLOCK`: `1` to let the Stop event block
- `SCRIPTT_PYTHON`: the Python 3.14+ interpreter for the plugin's hooks (default `python3`)

A System One endpoint is any server that answers this request:

```
POST {SCRIPTT_D1_URL}/v1/systemone
{"model": "d1-2B-MLX-8bit", "state": "<the text>", "questions": {"q": {"type": "text", "instructions": "Which words are the notebook, or cells of it?"}}}
```

with

```json
{"answers": {"q": {"type": "text", "text": "the old cells", "span": [29, 42], "found": 0.9}}}
```

`span` is a range of `state`. `found` is a probability or a boolean; the hook counts 0.5 or more as found.
One question returns one range, so the hook asks again with the found words blanked out.

For a test on a Mac that has an MLX build of d1-2B, `tests/systemone_local.py` is a 30-line endpoint.

## Test

```bash
python3 tests/test_hook.py
```

It runs the 36 recorded events through the hook in order, each with its recorded d1 answers, and compares the
output with the recorded one. It also checks that each message has the holes that were written down for it.
`python3 tests/test_hook.py --record` writes the outputs of the current code into the event files.

`tests/try_d1.py` reads the same messages with a real d1 and writes `tests/d1_real.json`: for each message, the
ranges that d1 found beside the recorded ones.

## What is recorded and what is real

- The 34 first events are one hour of a real conversation. Their d1 answers were written by hand, by the same
  agent that wrote the expected results. So the tests show that the program works end to end with perfect
  answers. They do not show how well d1 reads.
- The comparison is by class: "the reply has an Explanation" does not check that it is the right explanation.
- The world in `world.py` was made for that one conversation.
