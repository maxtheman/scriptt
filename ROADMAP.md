# scriptt roadmap

Not in this release (0.2.0). Each item says what it is for and the smallest version that would do it.

## Training d1 from your own corrections

d1 is a 2B model, so the point is to train it on what you correct.
- **Already done:** every saved reading keeps each question d1 was asked, its options, d1's scores and your correction.
- **Prompts as data.** Move the question wordings (`WHAT`, `JOIN`, `ALSO`, `LEFT_OUT`, `KIND`) from the code into a file that each reading records, so you can edit them.
- **Re-ask.** `POST /ask {reading, decision, instructions?, options?}` asks the live d1 one decision again with an edited prompt and saves nothing. The board shows the scores before and after.
- **Export.** `GET /examples` gives one example per decision (prompt, options, d1's answer, your label when you corrected it), ready for CoreAI's training jobs.
- **Board:** edit a decision's prompt in place, re-ask, compare.

## Disagreements between you and the agent about what words are

- **Type the agent's replies too.** The Stop hook runs the same kind pass over the agent's reply (`scriptt16.typed` works on any text).
- **Show disagreements.** The board marks the words where your kind and the agent's kind differ, for example a type against a type constructor.
- **Settle them by behaviour.** Drop each reading into places: the engine shows which places accept each (kinds: `*` against `* -> *`).

## Changing the world from the board

- A world edit (add a member, a type or a function) proposed from the board goes through `gate`, which already keeps accepted meaning safe.
- The board shows its impact on saved readings before you accept it.

## Reading

- **Nested function spans in one phrase.** Give each piece its operation and path, so the board can draw `show(redesign(the mod))` as nested links.
- **Which actual object a word means across messages** ("the notebook" as one object, not just a member of `Code`).
- **Better kinds for every word.** On Max's 60 real prompts d1 gives no kind to 76–85% of words. Measure, then train (above).

## Not addressed yet

- **Asking several times and comparing** (problem 1 in the original notes): sample several readings or replies and show where they differ.
- **Time and effort:** estimate how long a request will take, and what to delegate to whom.
