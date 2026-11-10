# scriptt 0.2.0: the harness

Each message to an agent is a demand for computation. This harness has a small decision model, **d1**, decide
which computations a message demands, before Claude reads it. You see the decision, and you drag to disagree.

It is 2 files in a folder `.scriptt/` of your project. Python 3.14 or later, standard library only.

- `world.py` is the whitelist: classes of text, things that have a name, and functions between classes.
  A message can demand only a function that is there. The docstrings are the questions that d1 answers.
- `harness.py` is everything else: 2 hooks for Claude Code, the installer, and a local page.

## Install

```bash
curl -fsSL https://scriptt.ai/install.sh | sh
```

It makes `.scriptt/` with `harness.py`, `world.py` and `SKILL.md`, adds 2 hooks to `.claude/settings.local.json`
and the skill to `.claude/skills/scriptt/`. From a clone: `cp -r hook .scriptt && python3.14 .scriptt/harness.py install`.

Then say where d1 is, in `.scriptt/config.json`:

```json
{"url": "http://127.0.0.1:8791/v1/systemone", "body": {"model": "d1-2B-MLX-8bit"}, "block": false}
```

- `url`: a System One endpoint (`.../v1/systemone`, questions as a dict) or a CoreAI endpoint (`.../v1/decide`, questions as a list).
- `key` or `key_file`: a Bearer token, if the endpoint needs one.
- `body`: fields that go into each request, for example the model.
- `block`: `true` lets the Stop hook send back a reply that does none of what the message demanded.

**The public release of the d1 model is pending.** `tests/systemone_local.py` is a 30-line System One endpoint for
a Mac that has an MLX build of d1-2B. With no d1 the hooks print 1 line on stderr and Claude goes on.

## What it does

**UserPromptSubmit.** The message gets the brand `Asked`. Then 2 requests to d1:

1. A yes/no question for each function of the world: "Does the message ask the reader to *docstring*?"
   A function with 0.5 or more is demanded.
2. For each parameter of a demanded function (a hole of a class): if the message contains the name of a thing
   of that class, code fills the hole. If not, d1 gets a yes/no question for each named thing of the class.
   If none has 0.5, the hole stays open. d1 also points at the words that ask for each function.

Claude receives:

```
scriptt: d1 read this message as a demand for these computations of the world (.scriptt/world.py).
- delete(notebook=Notebook "the old cells") -> Notebook   [d1 0.99, from "old cells"]
A "?" is a hole that the message does not fill. If this reading is wrong, say so in 1 line.
```

**Stop.** The reply gets the brand `Written`. For each demand of the last message, d1 answers: "The message asks
the reader to *docstring*. Does the reply do it, or say that it is done?" The answers go in the log. With
`"block": true`, a reply that does none of the demands is sent back once.

**The log.** `events.jsonl` is the only state: 1 line for each event, with each probability that d1 gave.

**The page.** `python3.14 .scriptt/harness.py serve` shows the log on `http://127.0.0.1:8787`. Drag a function
to the other side, or a named thing into a hole, and press Save. Claude receives your reading with your next message.
[scriptt.ai](https://scriptt.ai) shows the same page with the recorded events of this repository.

## Test

```bash
python3.14 tests/test_harness.py
```

It runs 36 events of a real conversation through the harness with the recorded answers of the real d1-2b, and
compares each record with `tests/recorded.json`. `--record config.json` asks a real d1 again and also writes
`web/site/data.js`, the data of the page.

## What is measured, and what is not

- `tests/recorded.json` has the answers of d1-2b (MLX, on a Mac) of 9 Nov 2026, not hand-written answers.
- For 19 messages a person wrote which classes the message wants. d1 has the same set for 7. Counted by class:
  19 in both readings, 9 only in the person's, 11 only in d1's. The person's reading is 1 reading, not the truth.
- The reply check sent back 1 of 13 real replies when it must send back none, and it sent back the 1 reply that
  does not do the work ("Why do you want that?").
- The world in `world.py` was made for that 1 conversation. Write your own.
- d1 points at words badly: 4 wordings of "which words are a *class*" found words for 4 to 15 of 38 hand-marked
  ranges. So the harness gives d1 yes/no questions over the things that the world lists, and uses words for display only.
