# scriptt

scriptt draws, on each message that you type in the Claude desktop app, what the local decision model d1 read the message as. The harness (`.scriptt/harness.py`) reads the message against your world (`.scriptt/world.py`) with the reader `scriptt16.py`, saves the reading to `.scriptt/events.jsonl` (form 5) and names its session in `.scriptt/hooks.jsonl`. The mod runs the harness when you send a message, attaches its block for Claude, and draws the latest snapshot of that reading. It computes no meaning of its own.

## The row of your message

The row shows your message as you typed it, in the code font. Each value of it that has a type of the world (a member of a sum type, a number, a path that exists) is in the colour of that type. After each phrase is its tag: each obligation that it asks for, as `#0 redesign`, with the outcome of the check at the end of the turn once there is one (`PASS`, `FAIL`, `UNVERIFIED`); `#2 ?` for a request no function fits; `nothing`; or `quote` for a quote of an earlier reply. Under the message are a link, `open the board for this message` (the page of `harness.py serve` on `http://localhost:8787/?reading=<id>`), and 1 button, `scriptt`.

Press `scriptt` to turn on drag mode. Press it again to turn it off.

- The things that can move slant back and forth.
- Each phrase shows its calls, such as `show(subject=#0)`: a value in the colour of its type, the result of obligation 0 as `#0`, a deliberate absence as `None`, an open hole as the name of its type. A value of the message and the hole that takes it show the same number (`#1`).
- A call that FAILed the check is struck through.
- The world is under the message: its functions on 1 row, then 1 row for each sum type, its name and its members, then 1 row of the other types.

What you can move:

- A value of the message or a member of the world into a hole whose type takes it (a union takes each of its alternatives): it fills the hole.
- The value of a hole onto the world: the hole is cleared.

Each drop goes to the engine as a correction, through `harness.py post /accept` (what POST /accept of `harness.py serve` answers): the engine checks it against the types of the world and saves a new snapshot, and the row draws that snapshot. The tag of the phrase turns to the success colour when the engine took it. When it did not, the phrase goes back, its tag turns to the error colour, and the status line under the prompt says why, with the engine's diagnostics.

If the harness or d1 does not run, the row stays as the app draws it and the status line says why.

## What is not done

- The mod has not been seen in the desktop app. The tests run against the test kit with a form-5 line that the engine wrote.
- Moving a function onto or off a phrase is refused with a status line: it is not a correction the engine takes yet (the engine's new-operation edit needs a value for a parameter).
- The mod runs no check at the end of a turn: it reads the outcomes that the Stop hook of the harness saved (that hook reads the transcript, which the mod does not have). With no Stop hook installed in the folder, no outcomes are drawn.
- With the hooks installed by `harness.py install` too, a message typed in the app is read twice: once by the mod, once by the hook.
- The board link needs `harness.py serve` running.
- Until the row gets its first pointer event, drag mode draws its things as buttons: press a thing, then press where it goes.
- The mod reads the length of a text as its width in cells. Wide characters (emoji, Chinese) put the pointer off from the thing under it.
- VS Code and the mobile app have no `Client`: they draw the message as the app does, with no reading.

## Install

In a terminal session of Claude Code:

```
/plugin marketplace add maxtheman/scriptt
/plugin install scriptt@scriptt
```

In the desktop app: click + next to the prompt box, then Plugins, Add marketplace with `maxtheman/scriptt`, then Add plugin.

## Setup

The folder of the session, or a folder above it, needs `.scriptt/` as the installer leaves it (`harness.py`, `agree.py`, `scriptt16.py`, `world.py`), and Python 3.14. The mod uses the nearest one. The mod tries `python3.14`, then `/opt/homebrew/bin/python3.14`, then `/usr/local/bin/python3.14`.

## Files

- `hooks/register.tsx`: the hooks module. It runs the harness, keeps the readings, turns a form-5 line into what the row draws, and sends each drop to the engine.
- `hooks/row.tsx`: the surface module that draws the row and handles the pointer.
- `types/index.d.ts`: the form-5 line, the world record, a change, and what the mod keeps for the session.

## Tests

`claude plugin test <this folder>` runs `hooks/register.test.tsx`.
