# scriptt

scriptt draws, on each message that you type in the Claude desktop app, what the local decision model d1 read the message as. The harness (`.scriptt/harness.py`) reads the message against your world (`.scriptt/world.py`) and writes the reading to `.scriptt/events.jsonl`. The mod runs the harness when you send a message and attaches its block for Claude.

## The row of your message

The row shows your message as you typed it, in the code font. Each piece of it that has a type of the world (a member of a sum type, a number, a path) is in the colour of that type. After each part (sentence) is its tag: the functions that it asks for, or d1's choice when it asks for none, with d1's score. Nothing moves. Under the message is 1 button, `scriptt`.

Press `scriptt` to turn on drag mode. Press it again to turn it off.

- The things that can move slant back and forth.
- Each part shows its calls, such as `redesign(surface=the page#1)`. A hole that is filled shows its value in the colour of its type. An open hole shows the name of its type.
- A piece that a hole takes, and the hole, show the same number (`#1`). A piece that stands for another piece shows both numbers: `it#2=#1`.
- The world is under the message: its functions on 1 row, then 1 row for each sum type, its name and its members, then 1 row of the other types.
- With the pointer on a function or a type of the world, the line under the world shows its docstring.

What you can move:

- A function onto a part: the part asks for it. From one part onto another: it moves. Onto the world: the part does not ask for it.
- A piece, a member of the world, or the value of a hole into a hole of the same type: it fills the hole.
- The value of a hole onto the world: the hole is open.
- A type of the world onto a function of a part: that function's hole of that type is added, open. A thing dropped on a function fills such a hole.

While you drag, the holes that can take the thing are underlined, and the line under the world shows what the drop will record, as `harness.py reading` takes it. Over a place that cannot take it, the line is empty and the thing turns to the error colour. A tap picks a thing and a second tap drops it, the same as a drag.

Each drop goes to `.scriptt/events.jsonl` through `harness.py reading`, and Claude receives it with your next message. The tag of the part turns to the success colour when the log took it. When it did not, the part goes back, its tag turns to the error colour, and the status line under the prompt says why. When d1's check of Claude's reply says a function was not done, that function is struck through in drag mode.

If the harness or d1 does not run, the row stays as the app draws it and the status line says why.

## What is not done

- The mod has not been seen in the desktop app. The tests run against the test kit. They do not show that the app sends pointer events to a message row, or that the code font lines up with the cells that the pointer events name.
- Until the row gets its first pointer event, drag mode draws its things as buttons: press a thing, then press where it goes.
- The mod reads the length of a text as its width in cells. Wide characters (emoji, Chinese) put the pointer off from the thing under it.
- Product types are not in the world rows. Their holes are shown by path, as `rewrite(change.code=Code)`.
- What a piece stands for (`of`) is shown and cannot be changed.
- The terminal draws the row the same way. VS Code and the mobile app have no `Client`: they draw the message as the app does, with no reading.

## Install

In a terminal session of Claude Code:

```
/plugin install scriptt --marketplace maxtheman/scriptt
```

In the desktop app: click + next to the prompt box, then Plugins, Add marketplace with `maxtheman/scriptt`, then Add plugin.

## Setup

The folder of the session, or a folder above it, needs `.scriptt/harness.py` and `.scriptt/world.py`, and Python 3.14. The mod uses the nearest one. The mod tries `python3.14`, then `/opt/homebrew/bin/python3.14`, then `/usr/local/bin/python3.14`.

## Files

- `hooks/register.tsx`: the hooks module. It runs the harness, keeps the readings, and records each drop.
- `hooks/row.tsx`: the surface module that draws the row and handles the pointer.
- `types/index.d.ts`: the record, the user's reading, and what the mod keeps for the session.

## Tests

`claude plugin test <this folder>` runs `hooks/register.test.tsx`.
