# Acceptance criteria for Board v11 (written before the build; never loosened)

Sources: UI-SPEC.md (US), Max's words in FEEDBACK-SESSION.md (F-n.m), the v10 audit (A-n), the interaction contract (IC),
the task brief (T). Every probe is run in the built-in browser against `index.html` served from `web/site`, using
**real pointer events** (`pointerdown`/`pointermove`/`pointerup` dispatched at element coordinates, with the target found by
`document.elementFromPoint` at the pointer position), through Dragology's own drop targets. A probe may read the DOM and
`engine/*.json`. A probe may NOT: call app internals to set state, remount, write localStorage, or compare a value with
the same constant the page computed it from. Every "outcome" is read from the page after the drop (text of the place,
data attributes, the judgment mark), and, where the engine has an answer, compared with the engine's file.
Output of each run is stored in `web/site/audits/vNN-run.txt` next to the build.

## A. Data (T1, US "data source", A-7)
- A01 The page loads `engine/readings.json` and `engine/worlds.json` by fetch; the reading list has as many entries as the file (38 when written, 52 after the engine data was regenerated at 0249f2b), the first shown is the specimen "Redesign the mod. Then show it. Test the search too." (probe: network log has both URLs; picker lists 38; first text equals the engine's first text).
- A02 No type name, member name, function name or phrase text is hard-coded in the page source: every name drawn on the board is found in the loaded JSON (probe: collect all text drawn on the board for all 38 readings; each token is in the reading text, the world JSON, a fixed UI vocabulary list of at most 25 words that is printed by the probe, or a number).
- A03 For all 38 readings, every phrase is drawn, every term's id is drawn, every constant `at` span is the exact substring `text[at[0]:at[1]]` (probe: loop all readings through the picker's own control, read the DOM).
- A04 Kinds of missing are four different marks with their reasons in words: hole (reason text: rejected / no candidate / bounded / cleared), empty (Maybe), empty list (Many), unresolved phrase with its reason (probe on readings 12, 13, 19, 20, 34, 35 and the one with `several: []` if present; the four marks have distinct `data-missing` values and distinct stroke dash patterns).

## B. Every piece is a draggable thing (F-2.1, F-4.1, T4, A-2)
- B01 Every word of the message, every value chip, every place (filled or open), every operation block, every reference, every type node and every function node in the world graph answers a real pointer press-and-move by starting a Dragology drag (probe: for each such element in readings 0, 7, 10, 20, press at its centre, move 24 px, observe the dragged ghost exists, release; count elements that fail = 0).
- B02 No element with text has `pointer-events: none`, and the number of text-bearing board elements without a grab is 0 (probe counts from the DOM after a full page load, for 5 readings).

## C. Dragging a word moves what it is tagged with, not the word (F-3, T)
- C01 After dragging the word "the mod" onto an argument place and releasing, the word is still at its original coordinates (±1 px) and the message text is unchanged (probe: bounding rect before and after).
- C02 Dragging a constant word onto an argument place whose declared type accepts it binds it there: the place's drawn value equals the word, and the reading's state shows `constant` with the same `at` (probe: specimen, drag "the search" onto `show.subject`; place text becomes "the search"; the engine file's analogous result is the reading with case "specimen, show rebound to the original mod by an edit" (index 37 when written, 51 now); probe 37-equivalence: drag "the mod" onto `show.subject`, then compare the resulting place value and the flags with that engine reading's `show` term).
- C03 Dropping a word onto a place whose declared type does not accept it is refused: the reading is unchanged after release, and a reason naming the declared type and the word's type is shown (probe: specimen, drag "the search" (Code) onto `redesign.surface` (Surface)).
- C04 Dragging a place's value far away from every place clears it to a hole with reason "cleared"; the hole is drawn as a hole (US "kinds of missing").
- C05 Dragging an open hole onto a word (the other direction) fills it with that word's constant, if accepted (tagging both ways, F-4.2.1 context).
- C06 Dragging an operation block (or the first word of its phrase) onto a place that accepts its result creates a reference to it (identity, not a copy): the place shows the reference to the same operation id, and the operation count does not change (probe: counts before and after).
- C07 Dragging a function from the world graph onto a word, a value or a reference that its parameter accepts creates a new operation with a NEW id, the existing ids are unchanged; it is labelled provisional (T6, US "apply a function").

## D. Impact before commitment (T2, Max's central complaint)
- D01 While a piece is held (pointer down and moved, not released), every place that accepts it is marked "accepts" and every other place carries a refusal reason, visible without releasing (probe: hold "the mod"; read marks on all places of the reading; counts accept + refuse = number of places).
- D02 While held over an accepting place, the board shows the whole consequence before release: the new value in the place AND the changed judgment marks of every affected operation AND a one-line diff naming each changed place/operation (probe: hold "the mod" over `show.subject`; the preview's show-term shows no reference and a ready mark; the diff line mentions show.subject; release after reading; the final state equals the previewed one).
- D03 While held over nothing (far from every place), the reading shown is the base reading (nothing is previewed), and releasing leaves it unchanged (probe: compare serialized DOM state before and after).
- D04 What can be held is re-ranked: while holding a typed thing, the functions/types of the world graph that take it are in a group at the top (their y is smaller than every non-taking one), and move back on release (probe: y positions).
- D05 Holding a type in the world graph lights every function port that takes it, every function that returns it, and every place in the reading with that declared type; nothing changes on release (probe).
- D06 Holding a function in the world graph lights the words/values/references that its parameters accept (from `parameters` in worlds.json) and marks refusals with the reason.

## E. Click shows possible actions and why (T2)
- E01 Clicking a value chip opens a panel with: its place (operation id + path), declared type, kind, the type's definition (sum alternatives / product fields / brand chain), and a list of every place in the reading with accepted/refused and the reason (probe: click "the mod" in the specimen; the panel lists all 3 places; `redesign.surface` accepted/current, `show.subject` accepted, `test.subject` accepted; for "the search" `redesign.surface` refused with a reason).
- E02 Every action offered in the panel is also available as the same drag (and gives the same resulting reading), and every refused entry has a reason text (probe: click the action, read the result; compare with the drag's result).
- E03 Clicking a reference opens: the operation it refers to, the original value it can be rebound to, and its pending/ready judgment from the record; the rebinding actions exist and work (specimen: rebind show.subject to the original mod gives the engine edit reading's flags).
- E04 Clicking an operation shows its function's signature from the world (parameters with declared types and the result), the function's doc (`asks`), whether it is pending (engine `judgments.pending`) or has open holes, and what each pending/ready/complete flag is derived from; engine flags are shown as the engine's, edited ones as provisional.
- E05 Clicking a type name shows its definition, its kind, brand chain, constructors applied, the functions that accept it and the ones that return it; following any listed name replaces the panel with that thing's panel, with a Back control (probe: follow 3 links, back 3 times, return to the first).
- E06 Clicking a hole shows its reason in words, the candidates that fit its declared type (words and references), and the decisions recorded for that place (offered, cut, chosen, with d1's probabilities) when any exist.

## F. Interrelation (T3, F-4.2)
- F01 The world graph is built from the loaded world: one node per type, one per function, with one edge per parameter and one per result, one per brand-wrap, sum alternative and product field (probe: edge count equals the count computed independently by a script from worlds.json, for every world in worlds.json (6 when written, 9 now), via changing reading).
- F02 Each function node shows a port per parameter, with the parameter's name and declared type name.
- F03 Sum and product types are shown as such (a fork to alternatives / a box of fields) when the type is selected; brands as a wrap chain; kinds (`*`, `* -> *`) are shown for types and constructors (Many, Maybe, Later), with the constructor's `describes`.
- F04 Hovering or holding anything lights its counterpart in the message and the world: hovering the place `show.subject` lights the operation `show`, the phrase text, the type `Subject` and the reference's source op; hovering a word lights its phrase, op, place and type (probe: set of lit elements after pointermove).
- F05 A reference is drawn as an arc from the place to its source operation with the same id on both ends; two operations of the same function have different ids and are never merged (reading 5).
- F06 Pending vs ready is a mark on the operation (from the record's `judgments`), identical in all readings to the engine's flags for untouched operations (probe: compare for all readings, all ops). Since the regenerated engine data, `deferred` (own result is Later) is a separate flag: pending, deferred, ready are drawn as: open / waits / ready, with `later` and a dashed result chip for deferred.
- F07 Doc strings: function `asks` and type definitions reachable by click.

## G. Reading the record, steps, history (US "step through decisions")
- G01 A decision scrubber steps through `decisions` of the reading; each step highlights the text it concerns (phrase/op/place) and shows its exact question, options and answer with probabilities (probe: readings 0 and 7, step to the end and back; step count equals `decisions.length`; the rule decisions (reading 7) say "rule" and show the rule text).
- G02 Undo and Redo always visible; one undo reverses a drop (probe: drop, undo, compare state; redo).
- G03 Corrections made on the page are kept as a draft list (with operation, path, value, status "provisional") and survive a reload of the page (the page stores the draft; the probe reloads by `location.reload()` and reads the list).

## H. Minimal text and typography (F-1, T5, A-8)
- H01 The main view contains no sentence of more than 6 words that is not data (the message text, a decision's question, reasons from the engine) (probe: list all text nodes on the main view in 5 readings; each is either data from JSON or at most 6 words).
- H02 No text smaller than 12 px (computed font-size of every text element on the board).
- H03 Spacing is on an 8 px grid for rows and block heights (probe: y of every row `data-row` is a multiple of 8 relative to the board top).
- H04 No text overlaps other text on the board in any reading (pairwise bounding boxes of text elements, tolerance 0).
- H05 The long reading (34 or 35) fits in the width without horizontal scroll at 1280 and at 1024.

## I. Honesty
- I01 Everything the page derives itself (accepts, pending, complete, ready after an edit; the new operation) carries a visible "provisional" mark and `data-provisional="1"`; engine-owned values do not (probe: after the specimen rebind, the edited show term's flags carry the mark and the untouched `test` term does not).
- I02 The provisional recomputation is cross-checked against the engine: for every operation of every reading it reproduces the engine's complete/pending/deferred/ready flags, and the specimen rebind (C02) reproduces the engine's edit reading exactly (probe prints both, any mismatch is reported as a failure and shown in the run output, not hidden).
- I03 Things the engine does not yet provide (applying a function, world edits, save to the engine, project-wide object identity) are labelled, not faked.

## J. Every case (added after Max's message "simulate all of the different cases and interactions ... what each is supposed to do versus what it actually does"; adds items, loosens none)
- J01 For 10 readings chosen to cover each kind (specimen, shared result, record, several, through result, many of records, unresolved hole, empty list, reshape, chain), for up to 8 movable pieces per reading (value, operation, function, parameter label, place, word), up to 2 accepted and 1 refused target (sampling reduced from 16 readings / 22 pieces / 3+2 targets before any run reached J01, because the full set takes over an hour of real drags): a real drag held over an accepted target shows the same reading that the drop commits; a drop on an accepted target changes the reading (except a place dragged onto itself); a drop on a refused target changes nothing, previews nothing, and has a reason of more than 5 characters. At least 100 drags.
- J02 No script error or unhandled rejection occurs during the whole run.

## K. The ten questions about one word (added after Max asked for them with click counts, before v12 was audited; adds items, loosens none)
Word: "the mod" in the specimen. One click on the word opens its card. Each of K01..K09 is answered by that single click (the probe counts clicks); K10 by two. Answers must come from the record and the world, compared with the engine files where the engine has the number.
- K01 What is it tagged as: the type as a link, and its kind.
- K02 Which operation and argument place use it: both as links.
- K03 Whether that operation is ready / waiting / deferred, as the engine's flags say.
- K04 What the model was asked and answered about it: the probability of the chosen option and of the alternative, equal to the record's `answers`.
- K05 What else is in its type: the members are drawn in the world graph (all of them) with no further click.
- K06 Which functions take it: exactly the functions whose declared parameters contain its type (computed independently from worlds.json).
- K07 Where it can go and why: the places that accept it, each with its reason.
- K08 What it could be retagged as: the types with a member of these words, or the statement that only its own type has them (half: engine data has no word in two types).
- K09 How to extend or shrink what it covers: each option checked against the world's members and refused with the reason when the words are not a member (half: engine data has no longer member).
- K10 How a word that is not yet a value becomes one: add it to a type (a labelled world draft), 2 clicks; then it is a value that a real drag binds into a place.

## L. Long markdown (claimed from v15; added after Max asked for long texts)
The fixture is built only from the engine's readings of one world (`?stress`, also present under `?audit`): texts, phrases, constants and operations are theirs, shifted and renumbered, joined with markdown headings and bullets.
- L01 976 characters, 30 operations: every operation is drawn, no two texts overlap, the board is more than two viewports tall.
- L02 Markdown markers (#, ##, -) are words of their own, each on its own line at the left edge.
- L03 After scrolling 2000 px the world graph is still in view beside the reading.
- L04 A real drag deep in the long message ("the mod" onto a Subject place that is visible) changes that place.

## M. Visual language, constructors, marks, replay (claimed from v15; from Max's message about boxes that carry no information, the unusable `x`, `*`, `.`, Many/Maybe/Later, and meaningless shapes)
- M01 A constructor is dragged onto a type: it shows the expression (Many[Surface]), every type of the right kind accepts, the other constructors are refused with the kind rule, releasing opens the expression card and changes nothing.
- M02 In a world where a function takes Many[Surface], the functions lit and the parameters listed equal worlds.json.
- M03 Shape is the structure (base, brand, sum, product differ; Words and Asked share one), colour is what the thing is made of (str-made types share a colour; Path and int differ from it and each other), functions are arrows no type uses.
- M04 The port (`cell : Cell`), the kind mark and the structure mark each open a card with the data (record fields; same-kind types and constructors; the alternatives).
- M05 An outline appears only where something is missing: a filled place has none, a hole has a dashed one.
- M06 Replay plays the recorded decisions in order; what is not yet decided is ghosted; Show all clears it.

## Scoring
Each lettered item counts one: 65 items from v15 (A4 B2 C7 D6 E6 F7 G3 H5 I3 J2 K10 L4 M6), 55 before. The denominator is stated on each run. A criterion passes only when its whole sentence is verified by the probe; a probe covering part of a sentence is recorded as partial (0.5) and says which part is missing. The independent review of the probes (a sub-agent that read the specs, the criteria and audit.js) is stored in web/site/audits/ with each run; its verdicts, not the probes' own PASS lines, give the honest score.
