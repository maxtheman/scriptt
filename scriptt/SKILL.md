---
name: scriptt
description: Use when a prompt arrives with a block that starts "scriptt:", or when the user mentions scriptt, the harness, the world file, demands, holes, or wants to install, check, search, change or remove scriptt in a folder.
---

# scriptt

`.scriptt/harness.py` reads each message of the user before you do. It cuts the message into parts (sentences) and asks a small
decision model, d1, which functions of `.scriptt/world.py` each part asks for. Code finds the pieces of the message: each place
where a typed thing of the world stands (a member of a sum type, a number, a path). It puts each piece in a hole of a function, and
d1 checks it. You receive 1 line for each part that asks, 1 line for the parts that ask for nothing, and the holes that stay open:

```
scriptt: d1 read this message against .scriptt/world.py. Parts: 5. Parts that ask for something: 3.
1. rewrite(change=Change(notebook=Notebook('the old cells'), code=...)) 0.81   "Rewrite the old cells."
3. delete(notebook=Notebook('the old cells')) 0.86 ["them" = Notebook('the old cells') (part 1)]   "Then delete them."
4. ?  d1 abstains: no function of the world fits. The closest is write 0.21.   "Also, send the summary to my accountant by Friday."
Nothing: 2, 5 [Code('t-strings')].
For each "?": say in 1 line what the part asks, do it, and propose the line to add to .scriptt/world.py.
d1 says your last reply did not do: delete ("Then delete them."). Check that against your reply.
The user says that "I never liked them." asks for nothing. d1 said otherwise.
Open holes, each a ... above. Fill each from the conversation, or ask for that 1 thing:
1. rewrite.change.code: Code   "Rewrite the old cells."
```

The number of a line is the number of the part in the message. Every part is on a line: its own, or the "Nothing:" line.

## What to do with the block

- **Each numbered line is 1 ask.** Do each one, or say in 1 line why you do not. Use the list to check your reply before you end
  the turn: no ask may be left without a word.
- **"Nothing:"** lists the parts where d1 chose "nothing": a remark, a reason, a rule or a greeting. They ask for no work. Read
  them anyway: a rule there still holds.
- **Each call is a Python expression.** `Notebook('the old cells')` is a named thing of the world that the words contain.
  A call inside a call is the result of another ask of the same part.
- **The number after a call** is the share that d1 gave this function for that part alone. d1 makes 1 choice among all
  functions of the world, "something else" and "nothing". It is no proof. d1 reads 1 sentence at a time: read the quoted words yourself before you act.
- **`[...]` after a call or a part number** lists the pieces of that part that no hole takes, as Python (`Code('t-strings')`, `3`,
  `Path('notes.md')`), and each reference in the part.
- **A reference** such as `"them" = Notebook('the old cells') (part 1)`: the words "them" stand for the piece of part 1. Code took the
  nearest piece before the words, of the type of the open hole (or of any type when no hole is open), and d1 said yes at 0.8 or more.
  "(an earlier message)": the piece is from an earlier message of this session. A reference can be wrong: read the words.
- **`...` is an open hole.** The message does not say which thing. The last lines of the block list each one as
  `part. function.hole: type` with the words of the part. Take the thing from the conversation, or ask for that 1 thing.
  A hole of type `X | None` may stay open and is not listed.
- **"(d1: the part names no Note)"** after a call: the function needs a thing of that type, and the part names none. Either
  the thing is new, or the function is the wrong one for this part. Read the part before you act, above all before you delete.
- **`?` is an abstention.** d1 chose "something else": the part asks for something, and the world has no function for it. If the part is a real ask,
  do it, and propose the line to add to `.scriptt/world.py`. If it is a rule or a remark, follow it and add nothing.
  "The closest is" names the function that came nearest: if it is the right one, its docstring needs the user's words.
- **"= value" after a call:** the world gives that function a body, and the harness ran it. The value is observed.
- **"d1 says your last reply did not do: ..."** d1 gave under 0.2 that your reply did it. That is d1's check of its own
  reading: if the reading was wrong, the line is wrong too. Check it against your last reply. If it is true, do the work now.
- **"The user says that ..."** is the user's own reading of a part. It replaces d1's. `delete.notebook is "these cells"` says
  which thing fills that hole. `delete.notebook is open` says that the hole is open: ask for the thing, or take it from the conversation.
- If the block is wrong, say so in 1 line and go on with what the message says.

## The world, 1 for each folder

`.scriptt/world.py` is the whitelist of that folder. A message can ask only for a function that is in it.

- A function with a 1-line docstring is something the user asks for here. d1 reads the docstring as the rest of the sentence
  "The text asks the reader to ...". So write it that way, in the user's own words.
- A parameter is a hole. Its type says how it is filled: an `Enum` lists the named things (its values are the words the user
  says), `int` and `pathlib.Path` are read from the words, `str` and `bool` are asked of d1, a dataclass has 1 hole for each
  field, and `X | None` may stay open. A hole is filled from the words of its own part, or by a reference ("it", "them") to a
  piece that the message or the session named before.
- A change of `world.py` is used from the next message on. A block that came before the change was read with the old world.
- Keep it small: the 5 to 10 things the user really asks for in this folder. `python3.14 .scriptt/harness.py find "?"` lists
  the parts that d1 abstained on. Each one is a candidate for a new function.

## Commands

```
python3.14 .scriptt/harness.py install        2 hooks and this skill, into .claude/ of the folder
python3.14 .scriptt/harness.py find WORDS     the logged parts that have these words, this function, or a piece of this type or value
python3.14 .scriptt/harness.py find "?"       the parts that d1 abstained on
python3.14 .scriptt/harness.py world          the world as JSON
python3.14 .scriptt/harness.py serve          the log as a page on http://127.0.0.1:8787, where the user drags to disagree
```

- The log is `.scriptt/events.jsonl`, 1 line for each event. Each line has `form` (the form of the line), `harness` (its
  version), `world` (a hash of world.py as it was) and `at` (the time). A recent line means the hooks run.
- d1 is set in `.scriptt/config.json`. With no d1 the hooks print 1 line on stderr and you go on.
- To remove scriptt: delete the 2 `harness.py` entries from `.claude/settings.local.json`, then `.claude/skills/scriptt/` and `.scriptt/`.
