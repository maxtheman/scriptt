---
name: scriptt
description: Use when a prompt arrives with a block that starts "scriptt:", when a turn is sent back with a "scriptt:" reason, or when the user mentions scriptt, the harness, the world file, obligations, holes, or wants to install, check, search, change or remove scriptt in a folder.
---

# scriptt

`.scriptt/harness.py` reads each message of the user before you do. `scriptt16.py` (the reader) reads it against
`.scriptt/world.py`, the closed type system of this folder, with a small decision model, d1. d1 chooses which functions
of the world each phrase asks for and which value fills each parameter; rules ground the values that the words name
(members of a sum type, numbers, paths that exist here). Every reading is saved to `.scriptt/events.jsonl`. You receive:

```
scriptt: d1 read this message against .scriptt/world.py (reading 7198f8a8). Obligations: 5.
#0 redesign(surface='the mod') -> Later[Surface]  (pending)   "Redesign the mod."   evidence: a file written
#1 show(subject=#0) -> Subject  (pending)   "Then show it."   evidence: no evidence of a turn can show it
#2 ?   "Also send the summary to my accountant."
#3 test(subject=...) -> Observed   "And test whatever else changed."   evidence: a command that runs and exits 0
#4 explain(subject=None) -> Written   "Why did it break?"   evidence: d1 judges your reply (a judgment, not execution evidence)
Declared in world.py:
  def redesign(surface: Surface) -> Later[Surface]   change how the page or the interface looks, or how its information is ordered
  def show(subject: Subject) -> Subject   show or open something so that the user can see it
  def test(subject: Subject) -> Observed   test or verify that something works
  def explain(subject: Maybe[Words]) -> Written   explain or answer something: say why, how or what, or confirm or deny it
  Surface = 'the page' | 'the site' | 'the mod'
Open holes, each a ... above. Fill each from the conversation, or ask for that 1 thing:
  #3 test.subject: Subject, d1 chose none of the candidates
Unresolved requests, each a ? above: no function of world.py fits (#2 d1 chose none of the candidates).
  For each: say in 1 line what it asks, do it, and propose the function to add to .scriptt/world.py.
At the end of the turn each obligation is checked: work by evidence only (the commands you ran, the files you wrote; your words are not evidence of work), an answer or a rule by d1's judgment of your reply.
```

## What to do with the block

- **Each `#n` line is 1 obligation**: an operation that the quoted words ask for. Do each one, or say in 1 line why not.
- **A call is the operation with its values.** `'the mod'` is a member of a sum type that the words name; `#0` is the
  result of obligation 0 (here: show what the redesign made). `None` is a deliberate absence that d1 answered.
- **`-> T` is the declared result type.** `(pending)`: its value waits on work not done yet (a `Later` result, or an
  input that is one). Do the work it waits on first.
- **`...` is an open hole**, listed under "Open holes" with its type and why: d1 chose none of the candidates, nothing
  before it has that type, or a limit cut the candidates. Take the thing from the conversation, or ask for that 1 thing.
- **`?` is an unresolved request**: the words ask for something and no function of the world fits. If it is a real ask,
  do it and propose the function to add to `.scriptt/world.py`. If it is a rule or a remark, follow it and add nothing.
- **"Declared in world.py"** are the signatures and the docstrings that d1 read, and the words of the sum types.
- **"Words with no sure kind"** are words for which d1 found no type of the world with a share of 0.5 or more. If
  they matter to the request, ask the user what they are, or propose the types to add to `.scriptt/world.py`.
- d1 can be wrong. Read the quoted words yourself before you act, above all before you delete. If the block is wrong,
  say so in 1 line and go on with what the message says.

## The check at the end of the turn

When you stop, each obligation is checked. Work is checked by evidence from the transcript, never by your reply's
words: each command you ran with its exit code, and each file you wrote or edited (the last run of a command and the
last write of a file count). Each obligation's `evidence:` says what counts for it:

- an obligation that binds a path: a write of that file, or a command that names it;
- else a result that holds `Observed` (a test, research): a command that ran; it passes with exit code 0;
- else a result that is a `Path` or `Later[...]` of no text (a change, a redesign, a save): a file written that exists;
- a result that is words (`Written`, `Words`: an explanation, an answer) or `None` (a rule to follow) is done in the
  reply itself: d1 judges your reply against the call. That is a judgment, shown as "d1 judged", not execution
  evidence: PASS when d1 says done, else UNVERIFIED. Its exact question and answer are kept;
- anything else, and every `?`, stays UNVERIFIED.

Each obligation gets PASS, FAIL (a command about it failed, or a write did not hold) or UNVERIFIED. With
`"block": true` in `.scriptt/config.json`, a turn is sent back, with a reason that starts "scriptt:", only for an
obligation that is FAIL, or UNVERIFIED with a result that needs work; at most 2 times for 1 message. An answer that
d1 did not judge done, and a `?`, are not sent back. When you get it: do the work that is missing, or say in 1 line
why it cannot be shown. Saying the work is done does not count. The results are saved with the reading.

## The world, 1 for each folder

`.scriptt/world.py` is the type system of that folder. A message can ask only for a function that is in it.

- A function's 1-line docstring completes "The text asks the reader to ...": write it in the user's own words.
- Each parameter is a hole with a type: an `Enum` lists the named things (its values are the words, annotated
  `Asked`), `pathlib.Path` is a path that exists here, `int` is digits, a union is one of several, a dataclass has a
  field for each, `Many[T]` is several, `Maybe[T]` may be deliberately absent, `Later[T]` waits on work.
- `Words`, `Asked`, `Written` and `Observed` are the brands of text; `Asked` and `Written` must stay.
- A world with a fault is not used: the block lists the faults instead. `python3.14 .scriptt/harness.py world` shows the world.
- A change of `world.py` is used from the next message on; each reading names the world it was read against.
- Keep it small: the 5 to 10 things the user really asks for here. `find "?"` lists the unresolved requests: each is a
  candidate for a new function.

## Commands

```
python3.14 .scriptt/harness.py install        2 hooks and this skill, into .claude/ of the folder
python3.14 .scriptt/harness.py find WORDS     the phrases of the readings that have these words or this function
python3.14 .scriptt/harness.py find "?"       the unresolved requests
python3.14 .scriptt/harness.py world          the world as JSON
python3.14 .scriptt/harness.py serve          the readings on http://127.0.0.1:8787, with the engine's edit, accept and restore
```

- `.scriptt/events.jsonl`: every snapshot of every reading (form 5). `.scriptt/hooks.jsonl`: which session sent which
  reading, the replies, the evidence, the outcomes and the send-backs. `.scriptt/worlds/`: each world a reading used.
  A log of the old harness (form 3) is moved to `events-form3.jsonl`.
- d1 is set in `.scriptt/config.json`. With no d1 the hooks print 1 line on stderr and you go on.
- To remove scriptt: delete the 2 `harness.py` entries from `.claude/settings.local.json`, then `.claude/skills/scriptt/` and `.scriptt/`.
