---
name: scriptt
description: Use when a prompt arrives with a block that starts "scriptt:", or when the user mentions scriptt, the harness, the world file, demands, holes, or wants to install, check, change or remove the scriptt hooks.
---

# scriptt

`.scriptt/harness.py` runs at 2 events. It asks a small decision model, d1, yes/no questions about the text.

- **UserPromptSubmit.** d1 decides which functions of `.scriptt/world.py` the message demands. You receive a block:

  ```
  scriptt: d1 read this message as a demand for these computations of the world (.scriptt/world.py).
  - delete(notebook=Notebook "the old cells") -> Notebook   [d1 0.98, from "get rid of the old cells"]
  - rewrite(notebook=Notebook ?, code=Code ?) -> Notebook   [d1 0.61]
  A "?" is a hole that the message does not fill. If this reading is wrong, say so in 1 line.
  ```

- **Stop.** d1 checks your reply against each demand. With `"block": true` in `.scriptt/config.json`, a reply that
  does none of them comes back to you with the list.

## When you see the block

- Each line is a computation that the user wants done. Do each one, or say in 1 line why you do not.
- The number is d1's probability. Below 0.7 d1 is often wrong: check the line against the message before you act on it.
- A `?` is a hole. Fill it from the conversation if you can. If you cannot, ask the user for that 1 thing.
- A line that starts "The user corrected the reading" is the user's own reading. It replaces d1's.
- If the block is wrong, say so in 1 line and go on with what the message says. Do not work around it silently.

## The world

`.scriptt/world.py` is the whitelist: classes of text, things that have a name, and functions between classes.
A message can demand only a function that is there. To teach the harness something, propose the line for
`world.py` (a function with a 1-line docstring, a class, or a name) and let the user decide. Do not edit it unasked.

## Install, check, show, remove

- Check: a recent line in `.scriptt/events.jsonl` means the hooks run.
- Install: `python3.14 .scriptt/harness.py install`. It adds 2 hooks to `.claude/settings.local.json` and this skill
  to `.claude/skills/scriptt/`. Ask the user first. d1 is set in `.scriptt/config.json`.
- Show: `python3.14 .scriptt/harness.py serve` opens the events on `http://127.0.0.1:8787`. The user drags a
  function in or out of a message there to disagree with d1.
- Remove: delete the 2 `harness.py` entries from `.claude/settings.local.json`, then `.claude/skills/scriptt/` and `.scriptt/`.
