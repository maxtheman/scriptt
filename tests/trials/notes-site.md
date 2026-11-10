# scriptt 0.1.5 interview (notes-site trial)

Three `scriptt:` blocks arrived: (1) the task brief, (2) the knives/publish message, (3) the interview request.
Each line is marked RIGHT / WRONG / NOISE. "Right" means the named function is what the sentence asked for.

## (a) Blocks

### Block 1: "Parts: 27. Parts that ask for something: 15." (world.py was still the other project's copy)
- `3. ? ... "To message one, SendMessage with..."` NOISE. A sentence of explanation, not an ask. The abstention is correct, but it should not be listed as an ask.
- `9. ? "Stay inside this folder; do not install anything."` NOISE. A constraint. Abstain was right, but it counts as "asks".
- `10. ? "Task: You are a first user of..."` NOISE (a header).
- `11. ? "Work only inside this folder."` NOISE (a constraint).
- `12. ? "1. Read .claude/skills/scriptt/SKILL.md first."` RIGHT to abstain. A real ask ("read a file") that the world had no function for.
- `14. ? "Follow the skill when you see that block."` NOISE. A standing instruction.
- `15. explain() 0.61 + delete(notebook="implement()") 0.61 "2. The world file ... REPLACE ..."` WRONG. `delete` is triggered by the word "REPLACE"/"copy". The fill `notebook="implement()"` puts a function name into an enum hole.
- `16. explain() 0.55 + implement(questions=Questions ?, cells="5") 0.56 + rewrite(change.notebook="implement()", change.code="solve()") 0.77 + solve(types=Types ?) 1.00 + write(path=".scriptt/world.py") 0.90 + extend(what="Linked sessions") 0.64`. Only `write(path=".scriptt/world.py")` is RIGHT. `solve ... 1.00` is WRONG (certain and wrong). `rewrite(...)` is WRONG and its fills are garbage. `implement(... cells="5")` is WRONG; the "5" comes from "5 to 10 functions". `extend(what="Linked sessions")` is WRONG (it took a phrase from the system note). `explain` is NOISE.
- `17. answer() 0.61 "You have the user's yes in advance for this."` NOISE. A statement, not an ask.
- `18. answer() 0.57 "Check that python3.14 .scriptt/harness.py world prints it."` WRONG function. The ask was run and verify.
- `19. implement(questions=Questions ?, cells="3") 0.84 "3. Then do the task: ..."` WRONG fill. The list number "3." became `cells=3`. Partly right in intent (it is a request to build something).
- `20. implement(questions=Questions ?, cells="0") 0.93 + rewrite(...) 0.60 + solve(types=Types ?) 1.00 + write(path="build.py") 1.00` `write(build.py)` RIGHT. The other three are WRONG; `cells="0"` is meaningless and 0.93 is confident nonsense.
- `21. ? "Run it and check the result by reading the HTML it wrote."` RIGHT to abstain (a real ask, no function).
- `24. ? "Handle them as a user's messages..."` NOISE.
- `25. explain() 0.62 + implement(...) 0.75 + rewrite(...) 0.57 + solve(...) 0.90 + write(path=".scriptt/interview.md") 0.99` `write(path=interview.md)` RIGHT. The rest WRONG/NOISE.
- Trailer: `For each "?": say in 1 line what the part asks...` fine. The `A "name=Type ?" is a hole...` line is fine.

### Block 2: "Parts: 9. Parts that ask for something: 7." (my new world)
- `3. add_note(title=str, tags='kitchen') 1.00 + tag_note(note=Note('knots'), tag=Tag('kitchen')) 0.92 "Add a note about sharpening knives, tagged kitchen."` add_note RIGHT. It got `tags='kitchen'` right but `title=str` was left as the bare type name, i.e. unfilled; I filled it. tag_note WRONG: it combined "knives" with the next sentence's "knots" and invented a tag action on a note that did not exist yet.
- `4. tag_note(note=Note('knots'), tag=Tag('repair')) 1.00 + change_page(what=str) 0.67 "Then put the tag repair on the knots note."` tag_note RIGHT, and a perfect fill. change_page WRONG (the 0.67 is below the 0.7 line the skill itself warns about).
- `5. build_site() 0.86 + change_page(what=str) 0.78 "Rebuild the page and check it."` build_site RIGHT. change_page WRONG (the phrase "the page"). check_page was the right second function and was missed.
- `6. check_page(output=change_page(what=str)) 0.52 + change_page(what=str) 0.96 "Can the filter box also match tags?"` change_page RIGHT (0.96). `check_page(output=change_page(...))` WRONG and malformed: a function nested as an enum value. Also the real answer was "it already does", so the ask was a question.
- `7. ? "And publish it to my website when it works."` RIGHT abstain. It is a real ask, and one I should not just do (external, no target given).
- `8. ? "Which note is the longest?"` RIGHT abstain (a question about the folder).
- `9. change_page(what=str) 0.69 "</cross-session-message>"` NOISE. This is the wrapper tag of the message, not something the user said.
- `d1 says your last reply did not do: part 3, part 9, part 12, part 14, part 24.` WRONG. It used the part numbers of block 1 on a reply to block 2 (parts 12, 14, 24 do not exist here; part 9 is the closing tag).

### Block 3: "Parts: 5. Parts that ask for something: 3." (this message)
- `2. ? "Now the interview, please."` RIGHT abstain / the ask is real. The world had no function for it.
- `3. edit_note(note=Note) 0.97 + list_notes() 1.00 "Write .scriptt/interview.md as point 5..."` WRONG, both. `edit_note` is certain (0.97) because of "Write ... .md"; `list_notes()` at 1.00 is for "quote each scriptt: block". Both are confidently wrong. The right function is a "write a file" one, which my world lacks. The old world had `write(path)`, and it was right 3 of 3 times.
- `4. ? "Also run ... find "?" and ... find note ..."` RIGHT abstain (a real ask, no function).

## (b) A time the block made me do something I would have missed
Never, for the substantive work. The one near case: block 2 said `tag_note(...knots, repair) 1.00`. I had already read that sentence and would have done it. The "For each ?" rule did force me to say out loud that publishing and "which note is longest" were not covered, but I would have answered the question anyway and I refused to publish for reasons that were not from the block (the folder-only rule). The block never added an ask I had overlooked. It only listed the same asks, several of them wrongly.

## (c) What confused me (exact words)
- SKILL.md: "Under 0.7 it is often wrong: read the quoted words yourself." But the 1.00 and 0.97 lines were wrong too (`solve(types=Types ?) 1.00`, `list_notes() 1.00`, `change_page ... 0.96` on a correct one). The confidence number does not separate right from wrong, and the skill implies it does.
- SKILL.md: "Each numbered line is 1 ask. Do each one, or say in 1 line why you do not." With 4 wrong functions on one sentence I had no way to know which was meant, and this is a lot of lines to answer.
- The block shows `title=str` and `what=str` as if they were filled values. The skill says an open hole is shown as `name=Type ?`, but for a built-in `str` it printed `title=str` with no `?`. I could not tell an open hole from a filled one. The trailer in block 2 says 'An argument that is a type, as in name=Type, is a hole', which differs from the skill's wording `name=Type ?`.
- "d1 says your last reply did not do: part 3, part 9, part 12, part 14, part 24." Part numbers refer to a different message than the one I answered.
- "Parts that ask for something: 15" in block 1 counted many sentences that are constraints, so the headline number says nothing.
- The skill says "a block that starts `scriptt:` arrives with the message". It arrives in a hook-context section after the message; with a message pasted from another session it also parsed the wrapper tag as a part.

## (d) What I changed in world.py, and whether d1 found my functions
The inherited world was about notebooks, cells and d1 itself, and none of it fit. I replaced it with 3 enums (`Note` with six notes, `Tag` with ten, `Output` with `index.html`) and 8 functions: `build_site`, `add_note`, `edit_note`, `delete_note`, `tag_note`, `list_notes`, `check_page`, `change_page`. Later I added `SHARPENING_KNIVES` to `Note`.
Did d1 find them? Partly.
- Found and correct: `add_note` (1.00), `tag_note` (1.00, a perfect fill with enum values from the words), `build_site` (0.86), `change_page` for the filter sentence.
- Found but spurious: `tag_note` on the sharpening sentence, `change_page` on three sentences that did not ask for it, `check_page(output=change_page(..))`.
- Missed: `check_page` for "Rebuild the page and check it".
- Block 3: it chose `edit_note`/`list_notes` for "write interview.md". I did not have a "write a file" function, so my world did not cover this ask.
- It never found what I did not define (read a file, run a command, publish, answer a question). Those became `?`, which is correct.
The enum filling works well when the sentence contains the words (`Note('knots')`, `Tag('repair')`, `tags='kitchen'`).

## `find` output, and whether it would help me later
- `find "?"` printed 13 lines, 3 from this session's own meta text (e.g. "Stay inside this folder; do not install anything.", "Work only inside this folder.") and the rest real. Real candidates: "Run it and check the result...", "And publish it to my website...", "Which note is the longest?", "Now the interview, please.", "Also run `...find "?"`...". As a list of functions to add, it would help me somewhat, but about half of it is instructions that should never become functions, and it cannot tell them apart. The 120-char cut makes the last line unreadable. No count per phrase, no suggestion of a function name.
- `find note` printed 7 lines. It matches the word in the logged part text and also the quoted-text prefix of the task ("Task: You are a first user..."), not just my notes; the line for part 19 matched because the sentence said "notes/". It gave me the asks about notes in time order with their function tags, which is useful for "what did the user ask about notes before", but it is a text grep with a function-name tag, no results from the notes themselves. I would not use it to find things in the notes folder; `grep -r` does that better.

## (e) What I would change first
1. Make sentence selection reject non-asks before function matching: constraints ("Stay inside..."), explanations, wrapper tags like `</cross-session-message>`, and list numbers ("1.", "3.") must not become `cells=3`. Most noise came from here.
2. Stop printing more than one function for a sentence unless they are both clearly asked; a 1.00 wrong answer next to a 0.9 right one is worse than one answer.
3. Fix the confidence number: it says 1.00 for wrong calls. Either calibrate or remove it, and fix the skill claim about 0.7.
4. Show open `str` holes as `title=? (str)` so I can see what is filled.
5. Number "d1 says your last reply did not do" lines against the last block, not an older one.

## (f) Score for "I would keep this on": 2 / 5
Reason: the enum fills were exact where the user's words named a thing (`knots`, `repair`, `kitchen`), and the log gives a way to find unmet asks later. But the block was wrong or noise on roughly half of its lines, gave 1.00 to wrong calls, and never showed me an ask I would have missed. Reading and rejecting it cost more than it saved. It could become a 4 if non-asks were filtered and the confidence were true; as it stands I would keep the log and turn the block off.

# Round 2

Block that came with the round 2 message ("Parts: 8. Parts that ask for something: 7."):

- `2. ? d1 abstains: no function of the world fits. The closest is change_page 0.04. "The harness in this folder was changed because of it (...)"` RIGHT. A remark, not an ask; I followed it (re-read the skill) and added nothing.
- `3. tag_note(note=Note('coffee'), tag=Tag('drink')) 0.95 "Round 2, as a user: Take the tag drink off the coffee note."` RIGHT, with perfect fills. (The docstring says "put a tag on a note, or take it off", so d1 had to guess the direction; it did not matter because the words said "off".)
- `4. add_note(title=..., tags=...) 0.99 "Add a note about patching a tyre, tagged bike and repair."` RIGHT. `...` marks both holes as open and I filled them: title "Patching a tyre", tags bike, repair. Good, this is the display fix I asked for.
- `5. build_site() 0.93 "Rebuild the page."` RIGHT.
- `6. change_page(what=...) 0.65 "Does the tag click still work after that?"` WRONG function. It is a check (`check_page` exists in the world), and the ask is a question. 0.65 is, at least, low. I tested it in headless Chrome: clicking `repair` shows Bike chain, Knots, Patching a tyre; clicking again shows all 8; typing "tyre" shows 1; typing "drink" shows 0 (the coffee note lost the tag, as expected).
- `7. ? d1 abstains ... The closest is change_page 0.03. "Then print the page as a PDF for me."` RIGHT abstain, and a real ask. I did it with local headless Chrome into `index.pdf` in this folder (73,576 bytes). Proposed line: `def print_pdf(output: Output) -> pathlib.Path: """print the built page as a PDF"""`. Not added; no yes from a user.
- `8. edit_note(note=tag_note(note=Note('coffee'), tag=Tag('drink'))) 0.87 "After you have done that, add a section "Round 2" to .scriptt/interview.md: ..."` WRONG. `edit_note` is the wrong function for a file that is not a note, and the hole is filled with the result of the part 3 call (the nesting from "after you have done that"). It makes no sense, and 0.87 is high. It is the same mistake as block 3 (the world lacks a "write a file" function), now with nesting.

## Which changes did I notice, and did they fix my complaint?
- **Calls are real expressions (`Note('coffee')`, `Tag('drink')`).** Helps; unambiguous. No complaint fixed, just clearer.
- **Open holes print as `...` (`title=..., tags=...`).** FIXED my complaint (c): I can now tell open from filled. Before, `title=str` looked filled.
- **Abstentions print "The closest is change_page 0.04."** Partly fixed. It tells me the abstention is firm (0.03 and 0.04), which is useful. It does not name what the sentence is.
- **"d1 says your last reply did not do" now quotes the part text and names the function.** Not triggered in this block, so I can't say. The wording is better than the old part numbers.
- **The number is now defined as a share among all functions and "none".** Partly fixed; the skill no longer claims "<0.7 is often wrong". But 0.87 and 0.95/0.99 are still shown, and 0.87 was wrong.
- **Rule/remark is told apart from a real ask in the skill ("If it is a rule or a remark, follow it and add nothing").** I used it for part 2. Fixed in the skill text, but the block still lists the remark as an ask line, so the header still counts it ("7 asks": really 5 asks and 1 remark... I count 3, 4, 5, 7, 8 as asks, 6 as a question).
- **Wrapper tag noise (`</cross-session-message>`) is gone** this time, and no list-number holes (`cells=3`) appeared. FIXED.
- Nothing is in the log about whether the sentence-level `d1` still read each sentence alone (part 8 shows it does not understand "after you have done that").

## What is still wrong
1. A question about the page ("Does the tag click still work after that?") went to `change_page` instead of `check_page`; wrong function and still counted as an ask.
2. "Write/add to a file" is wrongly sent to the note functions (`edit_note`, `list_notes`) whenever the world has no file-writing function, at 0.87 to 1.00. If the world has no match the harness should abstain, as it did for the PDF. A confidence share does not help here. A threshold or a "none" share that is high enough would.
3. Nesting: `edit_note(note=tag_note(...))` fills a hole with the call of another part just because the sentence says "after you have done that". It's worse than an open hole.
4. The header "Parts that ask for something: 7" counts the remark in part 2 and the question in part 6.
5. Two of the world edits I made before the message (adding PATCHING_A_TYRE etc.) must be done by hand each time a note is added; an Enum of the notes in a folder goes stale. Not the tool's fault, but a folder-derived enum would fit this world.

## New score: 3 / 5
Up from 2. The fixes I asked for (open holes visible, no wrapper-tag or list-number noise, the number explained, the abstention comment) made the block much more readable, and 5 of 7 lines were right, including three exact fills. The two wrong lines were both confident-looking (0.87) or on a question, and the one on the file-writing ask repeats the failure from round 1. I would still read the block, not rely on it; I'd keep it on if the file-write miss went away.

# Round 3

Block for this message, word for word ("Parts: 15. Parts that ask for something: 7."):

```
6. ?  d1 abstains: no function of the world fits. The closest is list_notes 0.17.   "`harness.py world` says "fields" for a product type."
7. add_note(title='oiling a chain', tags='bike') 0.98   "Round 3, as a user: Add a note about oiling a chain, tagged bike."
8. tag_note(note=Note('coffee'), tag=Tag('repair')) 0.99   "Put the tag repair on the coffee note."
9. delete_note(note=...) 0.82   "That was a joke, take it off again."
10. build_site() 0.93   "Rebuild the page."
11. change_page(what='page dark') 0.96   "Then make the page dark."
13. edit_note(note=...) 0.86   "After you have done that, add a section "Round 3" to `.scriptt/interview.md`: the block yo"
```

## Right and wrong
- 6: WRONG to be in the block at all. It is a remark about the harness (a description of a change), not an ask. The "remark gets no line" fix did not catch it; it came out as an abstention instead. NOISE.
- 7: RIGHT. Both holes filled from the words (title "oiling a chain", tags "bike").
- 8: RIGHT. Exact fills.
- 9: WRONG and dangerous. "take it off again" means remove the tag I just added; d1 chose `delete_note` (delete a whole note) at 0.82, with an open hole. If I had followed it I would have deleted a note. The docstring of `tag_note` says "or take it off", and d1 still did not pick it.
- 10: RIGHT.
- 11: RIGHT (change_page, what='page dark').
- 13: WRONG. `edit_note(note=...)` for writing the interview file: the same miss as rounds 1 and 2 (my world has no write-a-file function; the near function is picked instead of abstaining). It is at least no longer nested.
- Not in the block, and fine: "I like the tag list as it is" (a constraint, correctly no line), "That was a joke" is split into part 9 by itself and the earlier part has no line.
- "Put the tag repair on the coffee note" then "take it off again": the net effect is nothing. I made no change to coffee.md (kitchen only) and say so. I did not run it twice because the pair cancels out; I kept the tag list as it was, and added dark CSS only.

## What I did
Added notes/oiling-a-chain.md (bike). Rebuilt: 9 notes. Page is dark: `color-scheme:dark`, background #15171a, text #e6e6e6, dark input; `.tag` styles untouched.

## Round-2 faults: fixed?
1. Question sent to change_page instead of check_page: not tested this time (no question in this message). UNKNOWN.
2. File-write ask sent to a note function at high confidence: NOT FIXED (part 13, 0.86).
3. Nesting a call into a hole from another part: FIXED. Part 9 and 13 show `note=...` open holes, not a call from another part.
4. Header counts remarks and questions as asks: PARTLY. 7 lines: 6 is a remark about the harness and is still counted. The part about "the tag list as it is" got no line, good.
5. Stale Note enum: NOT FIXED, and not the tool's job. I added OILING_A_CHAIN by hand.
New fault: part 9, "take it off" read as delete_note at 0.82 (a destructive wrong function).

## Score: 3 / 5
Same as round 2. Fills are good (7, 8, 11) and nesting is gone, but a destructive wrong call (9) and the file-write miss (13) remain, and the remark still got a line.

## The 1 thing to change next
Make d1 abstain when the best function is not above "none" by a margin, so a sentence with no matching function (write a file) is `?` and not `edit_note 0.86`. Part 9 would also then pick or abstain, not delete.

# Round 4

Block for this message, word for word ("Parts: 12. Parts that ask for something: 5."):

```
3. tag_note(note=..., tag=...) 0.37  (d1: the part names no Note)  (d1: the part names no Tag)   "A call whose part names no thing of a needed type carries "(d1: the part names no Note)": "
5. delete_note(note=Note('patching a tyre')) 0.99   "Round 4, as a user: Delete the note about patching a tyre."
7. tag_note(note=Note('coffee'), tag=Tag('bike')) 0.99   "Put the tag bike on the coffee note."
8. ?  d1 abstains: no function of the world fits. The closest is list_notes 0.06.   "Then export all notes as 1 zip file."
10. edit_note(note=...) 0.91  (d1: the part names no Note)   "After that, add a section "Round 4" to `.scriptt/interview.md`: the block word for word, r"
d1 says your last reply did not do: delete_note ("That was a joke, take it off again."). Check that against your reply.
```

## Right and wrong
- 3: WRONG/NOISE. A sentence describing the harness ("A call whose part names no thing...") quoted in the message, read as a tag_note ask. The "(d1: the part names no Note)" note is correct, but the line should not exist: 0.37 is the remark case that round 3's change was meant to remove (it is a remark with quotes of the tool's own output).
- 5: RIGHT. Fill exact. Done by moving the file to `.trash/` in this folder (not erased).
- 7: RIGHT. coffee.md now has `Tags: kitchen, bike`.
- 8: RIGHT abstain, and a real ask. Done with Python's zipfile: `notes.zip`, 8 notes. Added `export_notes` to world.py.
- 10: WRONG function (the file is not a note), but this time the line says "(d1: the part names no Note)", which told me at once it was wrong. Useful. Added `write_file` to world.py, as the message allowed.
- "Is the page still dark?" and "Do not touch the tag list." got no line. Right for the second (constraint). For the first it is a question that I would have wanted a line for (check_page); a miss, but small. Answer: yes, `color-scheme:dark` is still in index.html, and the tag buttons are unchanged (checked by grep).
- "d1 says your last reply did not do: delete_note ("That was a joke, take it off again.")" WRONG. The sentence asked to remove a tag, not delete a note. delete_note was the round-3 wrong call and was right not to be done. I said so in round 3. Useful to see it quoted with the text, but it is d1 repeating its own error as a demand, and the skill says d1 "is sure". Risky: a hasty reader would delete a note.

## Round-3 faults: fixed?
1. Weak/remark lines about the tool get no line: PARTLY. Part 3 is a quoted remark and still got a line (0.37).
2. Write-a-file asks go to a note function: PARTLY. Part 10 still picks edit_note (0.91), but the "(d1: the part names no Note)" flag shows it is wrong. I added write_file; whether d1 finds it will show next message.
3. Destructive wrong call (delete_note on "take it off"): not tested again directly, but d1 re-raised it in the "did not do" line. Still dangerous there.
4. Stale Note enum: still manual (I removed nothing; the deleted tyre note remains in the enum).

## Score: 4 / 5
Four of five numbered lines were useful, fills were exact, the "(d1: the part names no Note)" flag is the best change so far because it tells me to ignore a line. The "did not do: delete_note" nag and the remark with a line (3) are what stop it being a 5.

## Keep scriptt on in this folder? Yes
The flags and open/filled holes now make the block cheap to check, and the log lets me find unmet asks (export, write file), which I turned into world functions.
