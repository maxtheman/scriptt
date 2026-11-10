# tests

```bash
python3.14 tests/test_harness.py
```

It runs 36 events of a real conversation through the harness with the recorded answers of the real d1-2b, and
compares each record with `tests/recorded.json`. It checks that every part has a choice, that the pieces are sorted
and do not overlap, and that each hole filled by a piece names the piece and the piece names the hole. With a stand-in
d1 it checks a reference across 2 messages ("Look at the old cells." then "Delete them."), a reference that d1 rejects,
a reading with the keys `delete.notebook`, and `migrate()` of a line of form 1 and of form 2.
`--record config.json` asks a real d1 again and also writes `web/site/data.js`, the data of the page.

| File | What it is |
|---|---|
| `test_harness.py` | the test |
| `events.json` | 36 events of 1 hour of a real conversation between Max and a Claude session. For 19 messages, `gold` lists the types that the message wants. A Claude session wrote `gold` by hand. No person checked it. |
| `recorded.json` | each answer of the real d1-2b to those events, each line that the harness wrote, and the comparison with `gold` |
| `systemone_local.py` | a small endpoint for a d1 model on a Mac, for testing |
| `trials/` | 2 trials: the interview of each agent, with each block word for word, and the `world.py` that it wrote |

## What was measured

All numbers are from the real d1-2b (MLX, on a Mac), 9 and 10 Nov 2026.

- **Recorded conversation.** For 19 messages a Claude session wrote by hand which types the message wants (`gold`). d1 has the same set
  for 8. Counted by type: 19 in both readings, 9 only in `gold`, 11 only in d1's. `gold` is
  1 reading, and no person checked it. The world of that conversation is `scriptt/world.py`.
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
- **References (0.1.6).** The search proposed 79 pairs of words ("it", "that", ...) and the nearest piece before them,
  in the 19 recorded messages. A Claude subagent marked 11 as right, 66 as wrong, and left 2 out. No person checked the marks. Each wording, with the share
  at which a yes counts, and how many it keeps (right of 11, wrong of 66):

  | wording | 0.5 | 0.7 | 0.8 | 0.9 |
  |---|---|---|---|---|
  | A `In the last sentence, does "it" mean the mod?` | 11, 29 | 10, 8 | 9, 4 | 3, 0 |
  | B `In the last sentence, does the word "it" stand for "the mod"?` | 10, 21 | 9, 9 | 5, 3 | 3, 1 |
  | C `Does "it" in the last sentence refer back to "the mod", named earlier?` | 11, 27 | 11, 12 | 10, 4 | 5, 1 |
  | D choice between the mod and "something else" | 11, 25 | 9, 9 | 9, 4 | 2, 0 |
  | E the words in brackets in the state, `In the last sentence, does [it] mean the mod?` | 10, 19 | 10, 8 | 9, 1 | 3, 0 |
  | F brackets, `Does [it] in the last sentence refer back to "the mod", named earlier?` | 11, 24 | 11, 11 | 11, 4 | 7, 1 |
  | G brackets, `In the last sentence, is [it] another name for the mod?` | 7, 9 | 3, 2 | 2, 0 | 1, 0 |

  The harness uses E at 0.8. A 1-choice question among up to 8 earlier pieces and "none" was also tried on the 44
  pairs in parts that ask: alone it chose 3 right and 4 wrong (options "none of these") or 7 right and 14 to 16 wrong
  ("something else, or nothing"). Followed by E at 0.8 it kept 7 right and 1 wrong, the same as the nearest piece
  followed by E. So the harness asks E of the nearest piece only.
- **d1 points at words badly.** 4 wordings of "which words are a *type*" returned words for 4 to 15 of 38 ranges
  that a Claude session had marked, and 2 to 8 of those overlapped the marked range. The state was always the whole
  message. A short state and a choice among candidate ranges were not tried. So d1 gets choices over what the world lists, and a text read is used for a `str` hole only.
