---
name: scriptt-hook
description: Install, check, use or remove the scriptt hook, which reads each user message into a typed template (what the message wants and what it supplies) and compares the reply with it. Use when the user mentions the scriptt hook, typed messages, holes in a message, "the world" file, or when a prompt arrives with a block that starts "scriptt hook:".
---

# The scriptt hook

The hook is one Python script, `scriptt_hook.py`. Claude Code runs it at two events.

- **UserPromptSubmit.** It reads the user's message. Each range of the message gets a class from the world (`world.py`).
  A range with a value in the world is *given*. A range with only a class is a *hole*: the message wants it.
  A verb that names a function of the world wants the result of that function. You then receive a block of context
  that starts with `scriptt hook: this message, read as types.` and has three lines: `wanted`, `given`, `not typed`.
- **Stop.** It reads your reply the same way and checks that the reply has something of each wanted class.
  With `SCRIPTT_HOOK_BLOCK=1` it stops the turn from ending when a wanted class is missing, and says which.

## When you see the block

- Treat each `wanted` entry as a part that your reply must supply. Answer every one, in the user's words where you can.
- `not typed` is the part of the message that the hook could not type. Read it yourself; the hook did not.
- If an entry is wrong, say so to the user in one line. Do not work around it without telling them.

## Before you start work in a project: check it, install it, or remove it

1. **Check.** Look for `scriptt_hook.py` in the `hooks` of `~/.claude/settings.json`, or for the plugin `scriptt-hook`.
   The hook writes `~/.claude/scriptt-hook/events.jsonl`; a recent line there means it runs.
2. **Install, if it is missing and the user wants it.** Ask first. Then follow `README.md` beside this skill's plugin:
   either load the folder as a plugin (`claude --plugin-dir <path to hook>`) or add the two entries to `settings.json`.
   It needs Python 3.14 or later; set `SCRIPTT_PYTHON` to that interpreter if `python3` is older.
3. **Remove, if the user does not want it.** Delete the two entries (or disable the plugin) and delete
   `~/.claude/scriptt-hook/`. Nothing else is installed.

Never change the user's `settings.json` without their OK.

## The model

The hook asks a d1 model one kind of question: a `text` read ("Which words are <the description of a class>?").
The public release of the d1 model is pending. Until then the hook works with any server that has a System One
endpoint (`SCRIPTT_D1_URL`), or with recorded answers (`SCRIPTT_D1_ANSWERS`). With neither, it records the event
and prints nothing, so it never blocks a session.

## The world

`world.py` is the only place where classes, named things and functions are defined. To teach the hook a new thing,
add a class with a one-line docstring (the docstring is the question that d1 is asked), or a name, or a function
between classes. Do not invent a class in a reply: propose the line for `world.py` and let the user decide.
