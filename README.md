# scriptt 0.1.6

Each message that you send to a coding agent asks it to do things. scriptt has a small decision model, **d1**, read
your message before Claude does. d1 decides which functions of a list that you wrote each sentence asks for. Claude
receives that reading with your message. You see it on your own message, and you can correct it.

The list is `world.py`, the **world** of a folder: its types and its functions. A message can ask only for a function
that is in it.

You write:

```
Sum the revenue by product for the west region only. Put both in the report.
```

Claude receives your message and this block:

```
scriptt: d1 read this message against .scriptt/world.py. Parts: 2. Parts that ask for something: 2.
1. sum_revenue(grouping=Grouping('by product'), only=Slice(region=Region('west'))) 0.77   "Sum the revenue by product for the west region only."
2. write_report(path=...) 0.74   "Put both in the report."
Open holes, each a ... above. Fill each from the conversation, or ask for that 1 thing:
2. write_report.path: Path   "Put both in the report."
```

This is the output of the real d1-2b with the world in `tests/trials/sales-report-world.py`.

A **hole** is a parameter of a function. `...` is a hole that the message does not fill. The number is the share that
d1 gave the function for that sentence.

**The public release of the d1 model is pending.** Until then scriptt needs an endpoint for d1 that you have. With no
d1, each hook prints 1 line on stderr and Claude goes on.

## Install

In the folder of your project. Python 3.14 or later, standard library only.

```bash
curl -fsSL https://scriptt.ai/install.sh | sh
```

It writes 3 files to `.scriptt/` (`harness.py`, `world.py`, `SKILL.md`), adds 2 hooks to
`.claude/settings.local.json`, and copies the skill to `.claude/skills/scriptt/`. An existing `.scriptt/world.py` is
kept. From a clone: `cp -r scriptt .scriptt && python3.14 .scriptt/harness.py install`.

[scriptt.ai](https://scriptt.ai) has a prompt that you paste into a coding agent. The agent does the setup and
proposes a `world.py` for your project.

Then say where d1 is, in `.scriptt/config.json`:

```json
{"url": "http://127.0.0.1:8791/v1/systemone", "body": {"model": "d1-2B-MLX-8bit"}, "block": false}
```

- `url`: a System One endpoint (`.../v1/systemone`, questions as a dict) or a CoreAI endpoint (`.../v1/decide`, questions as a list).
- `key` or `key_file`: a Bearer token, if the endpoint needs one.
- `body`: fields that go into each request, for example the model.
- `block`: `true` lets the Stop hook send back a reply that does none of what the message asked.



In the Claude desktop app, a mod draws d1's reading on each message that you type: see [mod/](mod/README.md).

## This repository

| Folder | What it holds |
|---|---|
| [scriptt/](scriptt/) | The 3 files that the installer puts in `.scriptt/`, and nothing else. `harness.py` is the whole harness (1 file). `world.py` is an example world. `SKILL.md` tells Claude what to do with the block. |
| [mod/](mod/README.md) | The mod for the Claude desktop app. It is installed apart, as a plugin. |
| [tests/](tests/README.md) | The test, a recorded conversation with d1's recorded answers, 2 trials, and what was measured. |
| [walkthrough.py](walkthrough.py) | A marimo notebook that runs 1 message through the search, step by step, and shows what each step returns. Start here to read the code. |
| [web/](web/) | The page at scriptt.ai. `sh web/build.sh` builds it into `web/public/`. `(cd web && npx cf deploy)` deploys it. |

To read the code: `scriptt/world.py`, then in `scriptt/harness.py` the wordings of the questions (`WHAT` to
`ANSWERED`), `parts_of()`, `read()` (the search) and `handle()` (the log line and the block).

## The world

```python
class Region(enum.Enum):
    """a sales region"""
    NORTH = "north"          # the value is the word that you say
    WEST = "west"

@dataclasses.dataclass(frozen=True)
class Slice:
    """a part of the data"""
    region: Region | None = None

def sum_revenue(grouping: Grouping, only: Slice | None = None) -> Table:
    """sum the revenue"""    # completes the sentence "The text asks the reader to ..."

def count_rows(path: pathlib.Path) -> int:
    """count the rows of a file"""
    return len(path.read_text().splitlines())   # a function with a body is run by the harness, and Claude gets the result
```

## The search

**UserPromptSubmit.** The message gets the brand `Asked`. Code cuts it into parts (sentences). The message is kept
whole as a t-string template: each part is 1 slot, and the pieces of the template joined are the text.

1. For each part, with the part alone as the state, d1 makes 1 choice among the functions of the world,
   "something else" and "nothing". If 1 function gets more than those 2 options together, the part asks for that
   function and for each other function that gets 0.25 or more. Else, if "something else" gets 0.5 or more, d1
   abstains: the line is `?`, with the closest function. Else the choice is "nothing". Each part has its `choice`.
2. Pieces, from the smallest typed things up. A piece is a place in the message where a value of a type stands, found
   by code: the name of a member of a sum type, a number, a path. The search walks each type that a signature of the
   world reaches, by its constructor, and calls itself for the types inside: each member of a sum type, each type of a
   union, the type of a list, each field of a product type. `int` and `pathlib.Path` are always searched. Pieces do
   not overlap: the longest wins. A part that asks for nothing has its pieces too.
3. Each parameter of a function is a hole. A hole takes the first free piece of its type in its own part. The demand
   with the larger share takes first, and a piece fills 1 hole (a `list` hole takes each piece of its type). If no
   piece fits, the hole can take the result of another function that the same part asks for and that returns this
   type. Else d1 chooses 1 member of the sum type or "none", reads the words for a `str`, or answers yes or no for a `bool`.
4. d1 checks each piece that code put in a hole, and each result. A value that d1 rejects leaves the hole open, and
   the piece stays in the record with no hole.
5. References. In a part that asks for something, the words "it", "them", "that", "this", "these", "those", "both" and
   "the same" can stand for a piece named before. Code takes the nearest piece before the words: in the message, then
   in the earlier messages of the session. The piece must have the type of an open hole of the part, or any type when
   no hole of the part is open. d1 sees the sentence of that piece, then this sentence with the words in brackets, and
   answers "In the last sentence, does [it] mean the mod?". At 0.8 or more the words are a piece with `of`, and the
   piece fills the open hole. Else the hole stays open.
6. Each ask is built as a Python expression with `ast`. If the world gives the function a body and no hole is open,
   the harness evaluates the expression. The result has the brand `Observed`.

Claude receives 1 line for each part that asks, 1 line for the parts that ask for nothing, and the holes that stay open:

```
scriptt: d1 read this message against .scriptt/world.py. Parts: 2. Parts that ask for something: 2.
1. explain() 0.94 [Types('result types'), "it" = Types('result types') (part 1)]   "Why is result types defined the way it is here?"
2. explain() 0.87 ["this" = Types('result types') (part 1)]   "What is this supposed to be accomplishing?"
```

```
scriptt: d1 read this message against .scriptt/world.py. Parts: 4. Parts that ask for something: 2.
1. rewrite(change=Change(notebook=Notebook('this version'), code=...)) 0.90 [Code('t strings'), Code('the template')]   "Go ahead and rewrite this version to use T strings And the template, yeah."
4. implement(questions=...) 0.34  (d1: the part names no Questions) + solve(types=...) 0.27  (d1: the part names no Types)   "We're compiling this to a program."
Nothing: 2, 3.
Open holes, each a ... above. Fill each from the conversation, or ask for that 1 thing:
1. rewrite.change.code: Code   "Go ahead and rewrite this version to use T strings And the template, yeah."
4. implement.questions: Questions   "We're compiling this to a program."
4. solve.types: Types   "We're compiling this to a program."
```

`[...]` lists the pieces of a part that no hole takes, and its references. In the second block d1 rejected
`Code('t strings')` for the hole `change.code` (0.37), so the hole is open and the piece is listed. `SKILL.md` tells
Claude what to do with each kind of line.

**Stop.** The reply gets the brand `Written`. For each function that the last message asked for, d1 answers: "The
message asks the reader to *docstring*. Does the reply do it, or say that it is done?" The answers go in the log.
With `"block": true`, a reply that does none of them is sent back once.

**Your reading.** `python3.14 .scriptt/harness.py serve` shows the log on `http://127.0.0.1:8787`. Drag a function
onto a part or back to the tray, or a named thing into a hole, and press Save. In the desktop app, the mod does the
same with a press on your own message. Claude receives your reading with your next message.

## The log

`events.jsonl` is the only state: 1 line for each event. Each line starts with:

- `form`: the form of the line. It is 3 now. `migrate()` in `harness.py` reads a line of form 1 or 2: a part gets
  its `choice` from its shares, and the line gets `"pieces": []`.
- `harness`: the version that wrote the line.
- `world`: a hash of `world.py` as it was.
- `at`: the time, UTC.

A message line (form 3) has:

- `parts`: start, end, `scores` (the share of each option), `choice` (a function, "none" or "nothing"), `demands`
  (the functions), `hole` (the share of "none" when d1 abstains), `asks`.
- `pieces`, sorted by start, with no overlap: `id`, `part`, `start`, `end`, `words`, `type` (a type of the world, or
  `int`, `Path`, `str`), `value`, `by`, `to` (`{"demand": n, "path": "..."}`, the hole that takes the piece, or null)
  and `of` (for a reference: `{"piece": id}` in this message, or `{"at": "...", "piece": id}` in the earlier line with
  that `at`; else null). A reference has `d1`, the share of d1's yes.
- `demands`: function, share, part, `parameters` (for each hole path: type, value, `by`, d1's check, and `piece`, the
  id of the piece that fills it), the Python expression, the result.
- `template`: the message, 1 slot for each part, with what the part is.

Your reading of 1 part is a "Disagree" line: `{"session", "text", "part", "demands": [...], "things": {"delete.notebook":
"these cells", "rewrite.change.code": null}}`. A key of `things` is `<function>.<hole path>`. null: the hole is open.
`python3.14 .scriptt/harness.py reading` takes it as JSON on stdin.

```
python3.14 .scriptt/harness.py find WORDS     the logged parts that have these words, this function, or a piece of this type or value
python3.14 .scriptt/harness.py find "?"       the parts that d1 abstained on: candidates for a new function
python3.14 .scriptt/harness.py world          the world as JSON
```

## What is not done

- A part is 1 sentence, cut by 1 regular expression (`parts_of()`). No other unit was compared with it. A sentence
  with 2 asks gets 1 choice. A quote of someone's words is cut and read as if you asked it.
- A sentence gets a choice: a function, "none" or "nothing". It gets no type. Only the pieces inside it have a type,
  and in a long message most words are in no piece. Sentences do not compose into 1 program.
- A part is 1 sentence. A reference ("it", "them") can take a piece of an earlier sentence or message, but only if the
  piece is the nearest one of the type, and only if d1 says yes at 0.8 or more. "Make sure it literally works in claude
  desktop." after a message that names the mod: `test()` has no hole, so "it" takes the nearest piece of any type
  (`Code('the world')` in that session), and d1 said no (0.35). The mod was further back: the choice among earlier
  pieces chose it (0.55), and then E said no (0.25). A function `test(surface: Surface)` would make the mod the
  nearest piece of the type.
- The words of a reference are a fixed list in `REFER`. "the one", "the other", "him" and "her" are not on it.
- A reference names the earlier message by its `at`. 2 lines of the log with the same `at` (1 second) cannot be told apart.
- A hole takes the first free piece of its type in its part, and d1 checks only that one. If d1 rejects it, the next
  piece of that type is not tried.
- A piece fills 1 hole. If 2 functions of 1 part need the same thing, the second gets the result of the first or stays open.
- A `str` that d1 reads is a piece only if it overlaps no other piece. A `list` hole names only its first piece in `piece`.
- A line of form 1 or 2 has no pieces after `migrate()`, so a reference cannot reach it.
- When the world has no function for an ask, d1 can choose a near function at a high share (`edit_note` 0.86 for
  a file that is no note). The cure is a function in `world.py`. `find "?"` does not list these parts.
- The share is not a probability that the line is right. It is not calibrated.
- Each part costs 1 request to d1, each ask 1 or 2 more, and each reference 1 more.
  The harness sends 8 requests at a time. This d1 answers them 1 after the other.
- A function of the world is run only if it has a body. Give a body only to a function that reads.
