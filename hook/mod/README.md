# scriptt

scriptt draws, on each message that you type in the Claude desktop app, what the local decision model d1 read the message as: 1 line for each part (sentence) of the message, and after the part's words the functions of your world (`.scriptt/world.py`) that the part asks for. A part that asks for something that no function fits shows `?`.

## What you can do

- Put the pointer on an item: the words beside it say what a press will record.
- Press a function: your reading is that the part does not ask for it. The item stays, struck through. Press it again to put it back.
- Pick from `?`: your reading is that the part asks for nothing, or for the function that you pick. Each option gives the function's name and its docstring.
- Press the count (`3 of 5`): each ask gains d1's probability and how d1 found it, and the functions that no part asks for are listed, struck through.

The words of the message cannot be pressed. Each reading goes to `.scriptt/events.jsonl` through `harness.py reading`, and Claude receives it with your next message. If the harness or d1 does not run, the message row stays as the app draws it and the status line under the prompt says why.

## Install

In a terminal session of Claude Code:

```
/plugin install scriptt --marketplace maxtheman/scriptt
```

In the desktop app: click + next to the prompt box, then Plugins, Add marketplace with `maxtheman/scriptt`, then Add plugin.

## Setup

The folder of the session, or a folder above it, needs `.scriptt/harness.py` and `.scriptt/world.py`, and Python 3.14. The mod uses the nearest one. The mod tries `python3.14`, then `/opt/homebrew/bin/python3.14`, then `/usr/local/bin/python3.14`.

## Tests

`claude plugin test <this folder>` runs `hooks/register.test.tsx`.
