---
name: scriptt
description: Use when a prompt arrives with a block that starts "scriptt:", or when the user mentions scriptt, the harness, the world file, demands, holes, or wants to install, check, search, change or remove scriptt in a folder.
---

# scriptt

`.scriptt/harness.py` reads each message of the user before you do. It cuts the message into parts (sentences) and asks a small
decision model, d1, which functions of `.scriptt/world.py` each part asks for. You receive 1 line for each part that asks:

```
scriptt: d1 read this message against .scriptt/world.py. Parts: 5. Parts that ask for something: 3.
1. delete(notebook=Notebook('the old cells')) 0.98   "Oh, can you please get rid of the old cells?"
3. implement(questions=..., cells=3) 0.71   "Then wire up 3 of them."
4. ?  d1 abstains: no function of the world fits. The closest is write 0.21.   "Also, send the summary to my accountant by Friday."
d1 says your last reply did not do: implement ("Then wire up 3 of them."). Check that against your reply.
The user says that "I never liked them." asks for nothing. d1 said otherwise.
```

The number of a line is the number of the part in the message. A part that asks for nothing has no line.

## What to do with the block

- **Each numbered line is 1 ask.** Do each one, or say in 1 line why you do not. Use the list to check your reply before you end
  the turn: no ask may be left without a word.
- **Each call is a Python expression.** `Notebook('the old cells')` is a named thing of the world that the words contain.
  A call inside a call is the result of another ask of the same message.
- **The number after a call** is the share that d1 gave this function for that part alone. d1 makes 1 choice among all
  functions of the world, "something else" and "nothing". A part where "nothing" wins has no line. It is no proof. d1 reads 1 sentence at a time: read the quoted words yourself before you act.
- **`...` is an open hole.** The message does not say which thing. Take it from the conversation, or ask for that 1 thing.
- **"(d1: the part names no Note)"** after a call: the function needs a thing of that type, and the part names none. Either
  the thing is new, or the function is the wrong one for this part. Read the part before you act, above all before you delete.
- **`?` is an abstention.** d1 chose "something else": the part asks for something, and the world has no function for it. If the part is a real ask,
  do it, and propose the line to add to `.scriptt/world.py`. If it is a rule or a remark, follow it and add nothing.
  "The closest is" names the function that came nearest: if it is the right one, its docstring needs the user's words.
- **"= value" after a call:** the world gives that function a body, and the harness ran it. The value is observed.
- **"d1 says your last reply did not do: ..."** d1 gave under 0.2 that your reply did it. That is d1's check of its own
  reading: if the reading was wrong, the line is wrong too. Check it against your last reply. If it is true, do the work now.
- **"The user says that ..."** is the user's own reading of a part. It replaces d1's.
- If the block is wrong, say so in 1 line and go on with what the message says.

## The world, 1 for each folder

`.scriptt/world.py` is the whitelist of that folder. A message can ask only for a function that is in it.

- A function with a 1-line docstring is something the user asks for here. d1 reads the docstring as the rest of the sentence
  "The text asks the reader to ...". So write it that way, in the user's own words.
- A parameter is a hole. Its type says how it is filled: an `Enum` lists the named things (its values are the words the user
  says), `int` and `pathlib.Path` are read from the words, `str` and `bool` are asked of d1, a dataclass has 1 hole for each
  field, and `X | None` may stay open. A hole is filled from the words of its own part only.
- A change of `world.py` is used from the next message on. A block that came before the change was read with the old world.
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
