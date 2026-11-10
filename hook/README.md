# scriptt 0.1.5: the harness

Each message to an agent is a demand for computation. This harness has a small decision model, **d1**, decide
which functions of your world each part of a message asks for, before Claude reads it. You see the decision, and
you can disagree with it.

It is 2 files in a folder `.scriptt/` of your project. Python 3.14 or later, standard library only.

- `world.py` is the whitelist of the folder: sum types (an `enum.Enum`), product types (a dataclass), and functions.
  A message can ask only for a function that is there. Each folder has its own.
- `harness.py` is everything else: 2 hooks for Claude Code, the search, the log, the installer, and a local page.

## Install

```bash
curl -fsSL https://scriptt.ai/install.sh | sh
```

It makes `.scriptt/` with `harness.py`, `world.py` and `SKILL.md`, adds 2 hooks to `.claude/settings.local.json`
and the skill to `.claude/skills/scriptt/`. From a clone: `cp -r hook .scriptt && python3.14 .scriptt/harness.py install`.
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

**The public release of the d1 model is pending.** With no d1 the hooks print 1 line on stderr and Claude goes on.

In the Claude desktop app, a mod (`hook/mod/`) draws d1's reading on each message that you type. In a terminal
session of Claude Code: `/plugin install scriptt --marketplace maxtheman/scriptt`.

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
whole as a t-string template: each part that asks is 1 slot, and the pieces joined are the text.

1. For each part, with the part alone as the state, d1 makes 1 choice among the functions of the world,
   "something else" and "nothing". If 1 function gets more than those 2 options together, the part asks for each
   function that gets 0.25 or more. Else, if "something else" gets 0.5 or more, d1 abstains: the line is `?`, with
   the closest function. Else the part is plain text and gets no line.
2. Each parameter of a function is a hole. It is filled by the constructor of its type, and the functions that do
   it call themselves for the types inside: a member of a sum type whose words the part contains, an `int`, a
   `pathlib.Path`, each field of a product type, each type of a union, each member of a list. If code finds no
   value, the hole can take the result of another function that the same part asks for and that returns this type.
   Else d1 chooses 1 member of the sum type or "none", reads the words for a `str`, or answers yes or no for a `bool`.
3. d1 checks each value that code found, and each result that code put in a hole. A value that d1 rejects leaves
   the hole open.
4. Each ask is built as a Python expression with `ast`. If the world gives the function a body and no hole is open,
   the harness evaluates the expression. The result has the brand `Observed`.

Claude receives:

```
scriptt: d1 read this message against .scriptt/world.py. Parts: 14. Parts that ask for something: 5.
7. sum_revenue(grouping=Grouping('by product'), only=Slice(region=Region('west'))) 0.72   "Sum the revenue by product for the west region only."
8. ?  d1 abstains: no function of the world fits. The closest is sum_revenue 0.08.   "Which product sold the least?"
9. write_report(path=...) 0.74   "Put both in the report."
```

`...` is a hole that the part does not fill. `SKILL.md` tells Claude what to do with each kind of line.

**Stop.** The reply gets the brand `Written`. For each function that the last message asked for, d1 answers: "The
message asks the reader to *docstring*. Does the reply do it, or say that it is done?" The answers go in the log.
With `"block": true`, a reply that does none of them is sent back once.

**Your reading.** `python3.14 .scriptt/harness.py serve` shows the log on `http://127.0.0.1:8787`. Drag a function
onto a part or back to the tray, or a named thing into a hole, and press Save. In the desktop app, the mod does the
same with a press on your own message. Claude receives your reading with your next message.

## The log

`events.jsonl` is the only state: 1 line for each event. Each line starts with:

- `form`: the form of the line. It is 2 now. `migrate()` in `harness.py` reads a line of form 1.
- `harness`: the version that wrote the line.
- `world`: a hash of `world.py` as it was.
- `at`: the time, UTC.

A message line has `parts` (start, end, the share of each option, the functions), `demands` (function, share,
parameters with value and source, the Python expression, the result) and `template`.

```
python3.14 .scriptt/harness.py find WORDS     the logged parts that have these words or this function
python3.14 .scriptt/harness.py find "?"       the parts that d1 abstained on: candidates for a new function
python3.14 .scriptt/harness.py world          the world as JSON
```

## Test

```bash
python3.14 tests/test_harness.py
```

It runs 36 events of a real conversation through the harness with the recorded answers of the real d1-2b, and
compares each record with `tests/recorded.json`. `--record config.json` asks a real d1 again and also writes
`web/site/data.js`, the data of the page.

## What was tried

All numbers are from the real d1-2b (MLX, on a Mac), 9 and 10 Nov 2026.

- **Recorded conversation.** For 19 messages a person wrote which types the message wants. d1 has the same set
  for 8. Counted by type: 19 in both readings, 9 only in the person's, 10 only in d1's. The person's reading is
  1 reading. The world of that conversation is `world.py` here.
- **2 trial folders.** 2 Claude Sonnet sessions each got an empty folder and a task (a sales report from a CSV, a
  notes site), wrote their own `world.py`, worked with the block, and scored it from 1 to 5 after each round.
  The harness was changed after each round with what they wrote. Sales report: 2, 3, 3.5, 4. Notes site: 2, 3, 3, 4.
  After round 4 both said that they would keep scriptt on in the folder. Their interviews, with each block word
  for word, and the `world.py` that each wrote are in `tests/trials/`.
  Still wrong in round 4: a sentence about the reply format read as `answer()` 0.55, a quoted remark read as
  `tag_note` 0.37, and `edit_note` 0.91 for a file that is no note.
- **Rules that the trials removed.** A yes/no question for each function, with the whole message as the state:
  several functions for 1 sentence, and 1.00 on wrong calls. A yes/no "does this part ask for something" before
  the choice: it dropped real questions. A hole filled from the whole message: it took a thing that another
  sentence names. A result of another part put in a hole: calls inside calls that no sentence asks for. The
  sentence before as context for the choice: it changed right choices to "something else".
- **d1 points at words badly.** 4 wordings of "which words are a *type*" found words for 4 to 15 of 38 hand-marked
  ranges. So d1 gets choices over what the world lists, and a text read is used for a `str` hole only.

## What is not done

- A part is 1 sentence. A sentence that needs the sentence before it ("take it off again") is read alone. In a
  trial d1 chose `delete_note` at 0.82 for that sentence. The line then says "(d1: the part names no Note)".
- When the world has no function for an ask, d1 can choose a near function at a high share (`edit_note` 0.86 for
  a file that is no note). The cure is a function in `world.py`. `find "?"` does not list these parts.
- The share is not a probability that the line is right. It is not calibrated.
- Each part costs 1 request to d1, and each ask 1 or 2 more. A message of 15 parts with 10 asks took 3.0 seconds.
  The harness sends 8 requests at a time. This d1 answers them 1 after the other, so that saved 0.4 seconds.
- A function of the world is run only if it has a body. Give a body only to a function that reads.
