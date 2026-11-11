# Independent review of board 3 (10 Nov 2026)

Reviewed: `~/Documents/scriptt-ui-3`, branch `ui/board-3`. HEAD was `42de58b` when the review started and moved to
`778cf12` ("fixes from the independent audit") while it ran. The drag accept loop (screenshots 01–06) ran on a page
loaded from `42de58b`; screenshot 01 still shows the old "stand-in d1" banner. Everything after that ran on fresh
loads of `778cf12`: the keyboard loop, the refused drag, the cards, the Stop check and the long prompts. Between the
two commits the drag, preview and accept code changed only in focus handling and labels. Engine: `harness.py serve 2781`
over the lab store (95 readings, 48 of them Max's real prompts). Built-in browser, tab of my own, viewport 800×876.
I edited no files in the worktree except this one and `web/notes/review-v3/*.png`. I did not touch ports 8765 or 2746.
The engine's own `/rerun` calls d1 on 8765, as configured in `lab/.scriptt/config.json`.

**Store side effects, undone.** My changes went to readings `c723e2…`, the C15 specimen as read by d1, and `2ed6b3…`.
Each change was 1 accept by drag, 1 accept by keyboard, 2 reruns, and restores (#13, #109, #111, #13). Each of the two
readings' latest snapshot is again identical to the latest before the review. I compared every field except the
snapshot/base ids, for all 95 readings: 0 differ. The store is append-only, so 8 extra snapshot lines remain (lines
112–119, 111 → 119). `hooks.jsonl` is unchanged.

**Already in the store before this review.** The builder's runs left reading `2ed6b3` with a semantically wrong
correction at its latest snapshot. That correction rebinds `test.subject` to "the mod", so "Test the search too"
tests the mod. "the search" is no longer an object there (screenshot 12). I restored that state as I found it. Max
should know it is there.

## Verdict

Board 3 is the first build where the loop is real. One representation of the text, edited only through the engine.
Select, `/edit` preview, whole diff, cancel, `/accept`, reload, `/rerun` retained: I checked all of it in the network
log and the store, by pointer drag and by keyboard. No `localStorage` or `sessionStorage` is used, and the duplicate
parse is gone. Those are the two biggest problems of the last review, and both are fixed. The rest has not caught up.
It is still a three-sentence demo that technically renders 13,727 characters. Two things break at that size. First,
the text structure: the parse is attached to phrase starts, not to the words. Operation chips and their sockets pile
up at the left edge of each phrase, and whole sentences or paragraphs become one grey "value" brick. Second, the long
prompts become a 21,000-px ruled page with no way to find the operations, holes or unresolved requests in it. What the
user can do is still only rebinding a place: no span, phrase, retag, new-operation or world edit. Max's
complaints 2 and 4.5 still hold: "can't change anything in the world", "can't change how wide a tag is", "every piece
of text needs to be draggable". The "Legos made of types" are boxes of whole sentences, plus operation stickers
placed beside them, not attached to them.

## What works (short)

- **Engine-only edits.** Each pick-up sends one `POST /edit` per place; drop or Enter commits that place's preview.
  `POST /accept` happens only on Accept. There is no page-side fit rule (screenshot 03; network log: `/edit` ×3 then
  `/accept`). Storage keys after the loop: `[]`.
- **Preview shows the whole engine consequence as a diff.** For example: `show.subject: "the mod" → the result of
  redesign`, `show · pending false → true`, `show · ready true → false`. Changed pieces are outlined in the text. Cancel
  restores the base and the store does not move (111 lines before and after the cancel).
- **Reload and rerun.** The reload showed the same reading (snapshot 2 of 2, 1 correction, socket `show#1.subject ←
  redesign ✎`). The rerun card said `show.subject: retained` (screenshot 06). This held by drag and by keyboard.
- **Refusals keep the base.** "the search" dropped on `redesign.surface` gives "Refused by the engine … rule 'type' …
  The base reading is still what the text shows" (screenshot 10).
- **Keyboard parity for the pick/drop path.** Tab to the operation, Space (picks up), Tab to the place, Enter (preview),
  Escape (cancel; focus returns to the place), Enter on Accept (saves). The place card's "fill with" list goes through
  the same `/edit` path.
- **Progressive cards.** A card is one heading plus 2–5 relationship rows, and one row opens at a time (screenshots 09,
  11).
- **Stop-check evidence.** It is shown at the operation when the snapshot has one: `test ready | FAIL` → "evidence
  (execution): ran `pytest -q tests/search` → exit 1" (screenshot 13).
- **Reasons for missing values are visible.** Holes show `? rejected`, `? bounded` and `? no candidate` in red dotted
  sockets.

## Ranked problems

### 1. The parse is attached to phrase starts, not to the words, so the text does not read as Lego

**Evidence.**
- In the specimen, the phrase "Redesign the mod. Then show it." is one phrase with two operations. Both chips,
  `redesign → Later[Surface] ready` and `show → Subject ready`, sit before the word "Redesign". Nothing is attached to
  "show" or "it" (screenshot 01).
- After the rebind, the socket `show#1.subject ← redesign` also lands before "Redesign", about 40 characters from "it",
  the word it stands for (screenshots 03, 05).
- In the real prompts, the engine binds whole sentences and paragraphs as constants. `explain.subject` = "Why the
  Notebook Is Hard to Read (and How to Reorganize It) The notebook is hard to follow…" becomes a single grey brick the
  full width of the column. 16 of the 26 values in the 8,825-character prompt are longer than 80 characters (up to
  416), and the longest prompt behaves the same way (screenshots 14, 16, 19, 21).
- The result is not "text made of typed pieces". It is grey boxes with an operation sticker above them. Pasted code
  inside a brick loses its code styling (screenshot 21: `def explain(subject: Maybe[Words]) -> …` in serif).

**Direction for v4.**
- Put each operation's mark on the span the engine actually used. At minimum, put it on the phrase's verb span, the
  first token of the phrase. Put a reference's mark at the end of its phrase, not at its start.
- Render a long constant as a tinted run of the text with a thin edge, not as a padded box. The text keeps its flow;
  the type and place label appear on hover or focus.
- Where the engine gives no word-level span (spec: "A reference's source word is not separately represented"), say so
  once in the card. Do not move the mark to the left edge instead.

### 2. Large prompts are not usable: no overview, no way to find the structure, the visual noise grows with length

**Evidence.** Six real prompts opened. I did not measure `e67414`; screenshot 19 shows it.

| Prompt | Characters | Page height | Operations | Phrases | Holes | Unresolved |
|---|---|---|---|---|---|---|
| `ffe36f` (longest) | 13,727 | 21,286 px | 49 | 132 | 20 | 12 |
| `2086c1` | 8,825 | 12,793 px | 40 | 91 | 9 | 4 |
| `a32bfc` | 2,175 | 3,862 px | 15 | | 6 | 0 |
| `12390a` | 1,758 | 2,899 px | 12 | | 5 | 9 |
| `e67414` | 1,161 | — | — | — | — | — |

- In `ffe36f`, the holes are spread from y=2,464 to y=20,965. The first screen of `2086c1` shows no operation at all,
  only ruled lines (screenshot 18).
- `font: 22px/2.5` plus a phrase underline repeated on every line (`box-decoration-break: clone`) turns every page into
  ruled notebook paper. Phrase boundaries disappear, and a screen holds about 9 lines (screenshot 15).
- Picking up a value in `ffe36f` takes 4.0 s and 48 `/edit` calls. It marks 21 places as fitting across 21,000 px. The
  user cannot see them or get to them. Max (4.2.6): "anything that you can actually drag to is on one page".
- The reading picker is an unsorted list of 95 entries, truncated at 48 characters, with no length, date or kind.
- Arc arrows only work at specimen size. In long prompts they cross many lines of text and end inside other bricks
  (screenshots 14, 20).

**Direction for v4.**
- Add a thin, always-visible gutter or minimap beside the text with one tick per operation, hole and unresolved request.
  Clicking a tick scrolls to it, and the same ticks are reachable by keyboard (next hole: `]`, next unresolved: `u`).
- While carrying, list the fitting places as a compact group beside the gutter, each a valid drop target with its
  phrase excerpt.
- Line height 1.7, an underline only under the selected or hovered phrase, and a gap between phrases instead of a rule.
- Draw an arc only for the selected object, and only if both ends are on screen. Otherwise show a jump link.

### 3. "Every piece is pick-up-able" and "change the world, the spans, the tags" are still absent

**Evidence.**
- Only `.val` (constants) and `.op` (results) can be dragged (`data-drag`). Words, places, holes, unresolved requests,
  types and phrases cannot.
- The only edit the page can make is "put this value or result in that place", plus "Clear this place".
- The spec's live transition `edit(reading, None, "function.parameter", value)` (apply a function to a thing, which
  creates a new operation) is not called anywhere in `board.js`. Neither is removing an operation, adjusting a span or
  phrase, nor any world draft.
- Max's §2 ("no way that I can change anything in the world"), §4.5 ("can't change how wide a tag is… If I drag
  'rewrite' into 'this version' nothing happens") and §3 ("dragging the sorts of things the words are tagged with")
  all still hold.

**Direction for v4.** Add one more transition, not five: drop a word or value onto a world function (from the type card
or the operation card) to create a new operation through `edit(None, "fn.param", value)`. The preview, cancel and
accept path is the same as today. Show span and world edits as visibly disabled, with the reason "engine has no
transition yet". Do not leave them silently absent.

### 4. The interaction lacks feedback where it matters: why something is refused, what fits, where focus goes

**Evidence.**
- A refusal says only `engine rule "type"` (screenshot 10). It does not say "Code given, Surface required". The
  engine's diagnostic is `[op, path, rule]`, and the page does not add the two types it already has (the carried
  value's `type`, the place's `parameters`).
- While carrying, the fit verdict is only in `title` (a tooltip) and a thin green outline. A refused place is 55%
  opacity with a hairline strike-through that is barely visible (screenshot 07). The place's `aria-label` still says
  "Enter to inspect" during a carry, so a screen reader hears no verdict.
- "fill with" lists `✓ "the mod" fits` for the place that already holds "the mod". `fillList` does not mark "already
  here", unlike `useList`. `✕ the result of test` says only "refused", with no reason.
- After Accept, focus drops to `<body>` (checked: `document.activeElement` = body). A keyboard user loses their place.
- The header says "previewing" during a refusal.
- Rerun gives no busy state: the button stays enabled and only the status line changes.
- "Earlier snapshots" is restore-only. Looking at an old snapshot (for example the one with the Stop check) means
  writing a new snapshot to the store. Snapshot numbers are store-wide (`#109`) while the header counts per reading
  ("snapshot 12 of 12").

**Direction for v4.**
- Give every verdict in words at the target: "fits", "already here", "refused: needs Surface, this is Code".
- Put the verdict in the accessible name during a carry.
- After Accept, return focus to the changed place.
- Add a read-only "view snapshot n" mode that does not write.

### 5. Kinds of state share glyphs and colours; operation chips outweigh the words

**Evidence.**
- Unresolved requests are drawn with the operation-chip class (`.op`, solid black border, bold monospace): `? rejected
  ? rejected ? bounded`. They repeat three per phrase on many real prompts (screenshot 19), with no phrase quote or
  decision in their card ("The engine could not make this an operation: rejected.").
- Holes use the same `?` glyph in a dotted pill. Two different kinds of missing (an owed request versus an empty
  argument) share one symbol. Max's §4.3.1 asked for "?" to carry more information.
- Amber means four things: `waits`, `UNVERIFIED`, "changed in preview" and the provenance notes. Green means three:
  `ready`, `PASS` and "fits".
- `test → Observed | ready | FAIL` puts a green "ready" beside a red "FAIL" at equal weight (screenshot 13).
- Chips are bold monospace with 1.5px black borders. Values are 1.5px black-bordered boxes. The serif words are the
  lightest thing on the page, the opposite of the contract's "ordinary English at rest".
- Three typefaces (serif text, monospace chips, sans card text) compete in one line.

**Direction for v4.**
- At rest, show operations as a small superscript verb label in muted ink, not a bordered chip.
- Give one hue to "needs attention" (hole or unresolved), each kind with its own distinct shape.
- Give one hue to the active transaction (selection, preview, fit), and show readiness and Stop outcomes only in the
  card or on focus.
- Give an unresolved request a card with its phrase text and the decision that rejected it.

### 6. Provenance of scores: honest in wording, but live scores are never labelled live

**Evidence.**
- Every score row says "recorded d1 score; its source (live or stand-in) is not written in the record". This covers
  the 48 real prompts read by the live d1 and the snapshots my reruns just made through `config.json` → `:8765/v1/decide`.
- The page still guesses "stand-in fixture score?" from the shape of the numbers (`scoreRows`, 0.9 plus an equal rest).
  The page is inferring provenance.
- The rerun card says "made by the d1 service configured for the harness". That contradicts the "not written in the
  record" line on the same reading.
- "+5 more options, each 1.7%" assumes the remaining options are equal. In the long-prompt hole, 89 + 3 + 2 + 5×1.7 >
  100, so they are not.
- Candidate lists print raw JSON for nested applications (`{"id":null,"function":"redesign",…}`).

**Direction for v4.** This is an engine request: write `by: {model, url, at}` on each decision (rerun and hook readings
know it). Then label "live d1 (d1-2b, 10 Nov)" against "stand-in fixture" from the record, and delete the shape
heuristic. Print the top 3 options plus "N others, total X%". Render nested candidates as `redesign(surface: ?)`.

### 7. The type view is still thin, and the one compatibility relation the page computes is narrower than its label

**Evidence.**
- The Surface card shows `kind *`, the sum of 7 members, and "places of this type here: redesign.surface"
  (screenshot 11). That list comes from the page comparing type names exactly (`typeCard` → `placeType(op,p) === name`).
  So `show.subject : Subject`, which accepts a Surface, is missing. That is the same symptom as the previous review's
  finding 4, now with a disclaimer underneath.
- The card lists no world functions that accept or return Surface (contract: "the functions whose parameters accept
  it or whose result is it"). There is no link from a sum member to its uses, and `*` is not explained.
- Max §3 ("showing how the world relates to each other… not visualized at all") and §4.2.1 ("if I grab a string,
  which things take strings") hold for the world. Inside one message they are partly answered by the carry marks.

**Direction for v4.** Rename the list "places declared exactly Surface". Add "accepted by" from one engine call, the
same `/edit` probe or a batch endpoint, never a page rule. List the world functions with their signatures, and make
each one a drop target (see 3).

### 8. Fulfillment is invisible at rest in the current store

**Evidence.** No reading's latest snapshot carries `fulfillment`: any edit clears it, and the builder's runs left the
only checked reading at an edited snapshot. To see Stop evidence, I had to restore #109, which wrote to the store, then
restore #111 back. There is no PASS and no "d1 judged" prose case in the store, so those branches are untested.

**Direction for v4.** Keep the last Stop check visible as "applied to snapshot n, may be stale" after an edit, instead
of hiding it. Ask the lead for one PASS and one prose-judgment Stop line in the store.

## Findings the build had to fix (the seven)

| # | Finding | Status | Evidence |
|---|---|---|---|
| 1 | Edits through the engine only | Fixed | `/edit`, `/accept`, `/rerun` and `/restore` only; no storage; no fit rule in JS. One page-side relation remains: the type card's exact-name list (P7). |
| 2 | One representation | Fixed for duplication | No second copy of the text. Operation names are printed beside their verbs. Placement is wrong (P1). |
| 3 | Labels faithful to level | Partly fixed | The word card says "No meaning of its own is recorded… the engine reads whole phrases". The value card shows the current binding ("bound at"), with the candidate history under it. At rest, operation chips at the phrase start read as word labels (P1). |
| 4 | One compatibility rule | Mostly fixed | Fit comes from `/edit` verdicts. The type card still computes its own narrower list (P7). |
| 5 | Progressive disclosure | Fixed | Small cards, one row opens at a time. Cards cover the text below the anchor (screenshots 09, 13), and opened rows scroll inside a 40vh box. |
| 6 | Decisions, Stop evidence, d1 judgments, fulfillment at the text | Partial | Decisions are in place and operation cards. Stop outcomes appear on the chips when present, but never at rest in this store (P8). The prose-judgment branch is untested. |
| 7 | Keyboard for every semantic object and drag | Partial | Operations, values, places and unresolved requests are Tab stops; words only by arrow keys. Pick, drop, cancel and accept all work by keyboard. Nothing jumps between objects of one kind (P2). Focus is lost after Accept. Verdicts are not announced (P4). |
| — | Fixture vs live labels | Not met | Live scores are never labelled live; the page guesses "fixture" from the shape (P6). |

## Max's earlier complaints (FEEDBACK-SESSION.md §1–5)

| Complaint | Status |
|---|---|
| §1 "everything needs to be part of a chain… not plugs and sockets embedded in text" | Not met. Board 3 deliberately embeds chips and sockets in the text. That follows the later spec, but conflicts with this remark. The decision should be made explicitly with Max. |
| §1 "least amount of text… no LLM generated text and states" | Mostly met at rest. One status line. The cards still carry explanatory prose ("What may be used at a place is asked of the engine…"). |
| §1 Undo is hard | Better: Cancel and Escape before accepting; Restore after. Undo after accepting means a store-wide snapshot number. |
| §2 "every piece of text needs to be draggable" | Still holds (P3). |
| §2 Drag state linked to types and world objects | Partly: fit marks come from the engine. The world (types, functions) does not respond to a drag (P7). |
| §2 "You don't expose all the data for every piece" | Mostly met through the cards (decisions, signature, judgments, Stop). |
| §2 "no way I can change anything in the world" | Still holds. |
| §2 "test on longer pieces of text" | They render without overlap, but they are not usable (P2). |
| §3 Dragging changes tags, not positions | Rebinding places only. No retagging, no tag width. |
| §4.1 Duplicated text | Fixed. |
| §4.1.1 "unclear what you're supposed to drag" | Better: grab cursor on chips and values. Nothing marks what a drag will do before the pick-up. |
| §4.2.1 Function inputs and outputs; "which things take strings" | Signature in the operation card. The carry marks answer it per message. Not shown for the world. |
| §4.2.2 / 4.2.5 "inherits from… sum or product types" | Sum members shown. Product fields and brands shown only if declared. No "made of" or "used by". |
| §4.2.3 Kinds, brands, folding | Kind shown as a raw `*`. Brand shown with a "not evidence" note. Folding absent and not explained. |
| §4.2.4 Docstrings | The function's `asks` is shown in the signature row. Type docstrings absent. |
| §4.2.6 Re-rank drop targets onto one page | Still holds (P2). |
| §4.3.1 Question marks that carry information | Partly: the reason follows the "?". The same glyph covers holes and unresolved requests (P5). |
| §4.3.2 World as a linear plug | Moot: no world view at all now. |
| §4.4 Spacing and typography | Still holds (P2, P5): line height 2.5, a rule under every line, three typefaces, heavy chips. |
| §4.5 Changing tag width; drag "rewrite" onto "this version" | Still holds (P3). |

## Gestalt and typography

- **Contrast.** Body ink `#16181d` on `#fbfbfa` and muted `#566070` are both fine. Problems:
  - A refused fit target at 55% opacity on muted text falls below 3:1.
  - The red `#a3201c` hole text in 13px monospace is legible but heavy.
  - Chips and value borders (1.5px black) out-contrast the text itself.
- **Repetition.** Good: one chip style, one socket style, one card style. Bad:
  - The same style serves different meanings (P5).
  - The underline is repeated on every line until it means nothing.
- **Alignment.** Chips are pushed to `vertical-align: .55em` while values sit on the baseline, with 8px padding plus
  borders, so the lines of a paragraph sit at ragged heights.
  - List numbers ("1.") are separated from their text by chips (screenshot 20).
  - Value bricks keep a blank band at the bottom where the place label sits (screenshot 14).
- **Proximity.** This is the main failure (P1). Related things (operation, socket, the word it reads) are separated.
  Unrelated things (two phrases' chips, a hole socket and the next phrase) sit together at the left edge.
- **Grouping.** A phrase is drawn as an underline. A value is drawn as a box. Two phrases in one line look like one
  group. A box around a whole paragraph groups more than the meaning does.
- **Overlap.** The card always opens below its anchor and covers the following text. With the preview card open in
  the specimen, the third phrase, which the preview concerns, is hidden. The snapshot list opens at the top left and
  covers the first lines.

## What v4 should prioritise (simpler, not bigger)

1. **Marks on the words, not at phrase starts.** Put each operation's label on its verb span and each reference's
   socket at its own position. Draw long constants as tinted text, not boxes. Use line height 1.7 and underline only
   the selected phrase. No new features until the specimen and the 13,727-character prompt both read as text.
2. **A structure gutter for long prompts.** Show one tick per operation, hole and unresolved request, clickable and
   reachable by keyboard. Gather the fitting targets there while carrying.
3. **One new transition: apply a function to a thing.** Drop a word or value onto a world function to call
   `edit(None, "fn.param", value)`, through the same preview, cancel and accept path. The type card becomes where you
   go to change something, not just a description.
4. **Verdicts in words at the target.** "fits", "already here", "refused: needs Surface, this is Code". Put them in
   the accessible name too, and return focus to the changed place after Accept.
5. **Provenance from the record.** Ask the engine to write the model and source on each decision. Label live and
   fixture scores from that, remove the guessing heuristic, and keep the last Stop check visible (marked stale) after
   an edit.

## Screenshots (web/notes/review-v3/)

| File | What it shows |
|---|---|
| 01-specimen-at-rest | C15 as read by d1: both `redesign` and `show` chips before "Redesign"; `test` chip mid-line; "the mod" box with two place labels. |
| 02-drag-carrying | Pointer drag of the `redesign` chip: status "asking the engine which places take it…". |
| 03-drag-preview | Engine preview card with 3 diff lines. The socket `show#1.subject ← redesign` lands before "Redesign". The card hides the third phrase. |
| 04-cancel | After Cancel: the base is back, "Cancelled: the base reading is unchanged." |
| 05-accepted | After Accept: snapshot 2 of 2, 1 correction, ✎ mark. |
| 06-rerun-retained | Rerun card: `show.subject: retained`. |
| 07-keyboard-carry | Space on `redesign`: two thin green fit outlines; the refused place is barely dimmer. |
| 08-keyboard-preview | Enter on the place: the same preview, focus on Accept. |
| 09-place-card-d1 | Place card with d1's recorded question and scores (90/5/3%) and the "source not written" label. |
| 10-refused | Drag of "the search" onto `redesign.surface`: refused, `engine rule "type"` with no types named. |
| 11-type-card | Surface: kind `*`, sum of 7 members, "places of this type here: redesign.surface" (misses `show.subject`). |
| 12-specimen-2ed6-latest | The `2ed6b3` latest as the builder left it: "the search" is plain text because of the leftover correction; arcs cross the chips. |
| 13-stop-check | Snapshot #109 restored temporarily: `test ready | FAIL`, evidence `pytest -q tests/search → exit 1`. |
| 14-longest-top | 13,727-character prompt, top: arcs spanning screens; heading plus sentence as one value box; `? rejected`/`? bounded` chips. |
| 15-longest-code | The same prompt: code lines, each underlined, large blank gaps. |
| 16-longest-hole | Orphan hole socket `build#21.code ? rejected` above a paragraph-sized value brick. |
| 17-longest-carry | Carrying a paragraph-sized value: fit marks scattered; `follow → NoneType`. |
| 18-8825-top | 8,825-character prompt: first screen is ruled lines and no operation. |
| 19-e674-unresolved | Repeated `explain → Written ready` chips and `? rejected ? rejected ? bounded` triples; sentence-sized boxes. |
| 20-a32b-arcs | List numbers separated from their text by chips; an arc ending inside a brick. |
| 21-1239-code-in-brick | Pasted Python signatures inside a value brick, rendered in serif; triple `?` chips. |
