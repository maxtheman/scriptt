---
name: scriptt
description: Use when a prompt arrives with a block that starts "scriptt:", or when the user mentions scriptt, the harness, the world file, demands, holes, or wants to install, check, search, change or remove scriptt in a folder.
---

# scriptt

`.scriptt/harness.py` reads each message of the user before you do. It cuts the message into parts (sentences) and asks a small
decision model, d1, which functions of `.scriptt/world.py` each part asks for. You receive 1 line for each part that asks:

```
scriptt: d1 read this message against .scriptt/world.py. Parts: 5. Parts that ask for something: 3.
1. delete(notebook="the old cells") 0.98   "Oh, can you please get rid of the old cells?"
3. implement(questions=Questions ?) 0.71   "Then wire up all ten."
4. ?  no function of the world fits (d1 abstains)   "Also, send the summary to my accountant by Friday."
d1 says your last reply did not do: implement.
The user says that "I never liked them." asks for nothing. d1 said otherwise.
```

## What to do with the block

- **Each numbered line is 1 ask.** Do each one, or say in 1 line why you do not. Use the list to check your reply before you end
  the turn: no ask may be left without a word.
- **The number after a call** is how sure d1 is. Under 0.7 it is often wrong: read the quoted words yourself.
- **`name=Type ?` is an open hole.** The message does not say which thing. Take it from the conversation, or ask for that 1 thing.
- **`?` alone is an abstention.** The part asks for something, and the world has no function for it. Say in 1 line what the part
  asks, do it, and propose the line to add to `.scriptt/world.py`. Add it when the user says yes.
- **"d1 says your last reply did not do: ..."** Check that claim against your last reply. If it is true, do the work now.
- **"The user says that ..."** is the user's own reading of a part. It replaces d1's.
- If the block is wrong, say so in 1 line and go on with what the message says.

## The world, 1 for each folder

`.scriptt/world.py` is the whitelist of that folder. A message can ask only for a function that is in it.

- A function with a 1-line docstring is something the user asks for here. d1 is asked: "Does the message ask the reader to
  <docstring>?" So write the docstring as the rest of that sentence, in the user's own words.
- A parameter is a hole. Its type says how it is filled: an `Enum` lists the named things (its values are the words the user
  says), `int` and `pathlib.Path` are read from the words, `str` and `bool` are asked of d1, a dataclass has 1 hole for each
  field, and `X | None` may stay open.
- Keep it small: the 5 to 10 things the user really asks for in this folder. `python3.14 .scriptt/harness.py find "?"` lists
  the parts that d1 abstained on. Each one is a candidate for a new function.

## Commands

```
python3.14 .scriptt/harness.py install        2 hooks and this skill, into .claude/ of the folder
python3.14 .scriptt/harness.py find WORDS     the logged parts that have these words or this function
python3.14 .scriptt/harness.py find "?"       the parts that d1 abstained on
python3.14 .scriptt/harness.py world          the world as JSON
python3.14 .scriptt/harness.py serve          the log as a page on http://127.0.0.1:8787, where the user drags to disagree
```

- The log is `.scriptt/events.jsonl`, 1 line for each event. Each line has `form` (the form of the line), `harness` (its
  version), `world` (a hash of world.py as it was) and `at` (the time). A recent line means the hooks run.
- d1 is set in `.scriptt/config.json`. With no d1 the hooks print 1 line on stderr and you go on.
- To remove scriptt: delete the 2 `harness.py` entries from `.claude/settings.local.json`, then `.claude/skills/scriptt/` and `.scriptt/`.
