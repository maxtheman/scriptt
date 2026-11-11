# Board 5 acceptance criteria

Written from `BRIEF.md` and `notes/MAX-FEEDBACK.md` before any board 5 code. They are never loosened. Each check has an
id that `web/site/audit.js` reports. A check passes only when the audit runs it in the browser on the lab
(http://127.0.0.1:2801) with real pointer and keyboard events (`PointerEvent`/`KeyboardEvent` dispatched at the
on-screen coordinates of the element, `elementsFromPoint` deciding the target), on at least five of Max's long prompts
(the longest readings that carry `pieces`). The runs are stored in `web/site/audits/`.

## Headline (from the brief), each by pointer AND by keyboard, on five long prompts

- **A. One wiki page.** The message is drawn once, in reading order, and every piece of `pieces` is a link (piped:
  the words as written, the target = its kind: a world type, a constructed type, a function, or `(none)`). Every
  operation is a function span covering its phrase, its argument spans inside it; references nest
  (`show(↩redesign)`). Opening a link (click / Enter) shows that thing's page from `worlds.json` (kind, brand chain,
  alternatives/members, fields, constructor applications, docstring, functions that take it and that return it) and
  its d1 data (for a word's kind: the state sent, the instructions, every option with its probability; for an
  operation's place: the decision's options, chosen, cut).
  - A1 the text rendered equals `reading.text` (one copy; nothing else in the text layer).
  - A2 one link per piece, its target = `piece.kind`.
  - A3 one function span per operation, around its phrase; each place drawn inside it; holes distinct by reason.
  - A4 opening a type link shows its world page; opening a function shows its signature; both from `worlds.json`.
  - A5 the opened link shows the d1 kind decision for its words (options and probabilities).
- **B. Retag by dragging** (the words never move):
  - B1 widen a link: drag its end handle over the next word(s); the speculative state under the pointer is the engine's
    `/edit {path:"kind", at, value}` draft.
  - B2 narrow a link the same way.
  - B3 drop a world type onto words, picked up from the page of the thing in hand (brief change of 10 Nov: no permanent
    world column; this replaces "from the world column or a type page", it does not loosen it).
  - B4 drop a constructed type (`Later[Surface]`, `Many[…]`, `Maybe[…]`) onto words.
  - B5 the whole consequence (every piece the retag cuts or adds) is drawn before release; after release: Accept /
    Cancel. Cancel restores the base exactly.
  - B6 after Accept and a reload of `/readings`, the latest snapshot has the correction (`corrections[].path=="kind"`)
    and the piece `by:"user"`.
- **C. A rejected or open place takes something:** a hole (`{hole, reason}`) or an unresolved request accepts
  - C1 dropped words (`{constant, type, at}`),
  - C2 a world member (`at: [-1,-1]`),
  - C3 a result (`{ref}`),
  each previewed by `/edit` and answered (staged or refused with the engine's diagnostic code shown).
- **D. Linking while dragging.** While a thing is held, the places the engine accepts it in are marked and brought
  near (a rail in view); places the engine refuses are marked refused and are not drop targets.
  - D1 the marks come from `/edit` verdicts, not from page logic.
  - D2 the accepting places are reachable without scrolling.
- **E. Undo after accept:** `/restore` of the snapshot before the accept; the reading is back, and it is in the store.
- **F. No agent prose.** The page has headers, glyphs, chrome and data (words of the message, names and docstrings of
  `world.py`, d1's records, the engine's diagnostic codes). No sentence written by the page.
  - F1 the audit lists every text node outside the message and the world/d1 data; none is a sentence.

## Dragology (the most failed requirement)

- G1 `vendor/dragology-0.2.0.iife.js` is loaded and the board is one `DraggableRenderer`.
- G2 `board.js` registers no `pointerdown/pointermove/pointerup/mousedown/mousemove/mouseup/dragstart/drop` listener
  (audit greps the source and fails the build).
- G3 every drag in the audit goes through Dragology: its `dragologyOnDrag` spec is a `d.closest` of `d.dropTarget`s /
  states, with `whenFar` for pulling out (unbind with no trash can), and `d.reactTo` so the speculative state is the
  engine's draft as it arrives.
- G4 everything drawn as a thing can be picked up (words, kind labels, handles, places, values, results, types,
  constructed types, members, functions). Dropping where nothing happens returns to the base, visibly (whenFar).

## Severity 2

- H1 the message appears once (no second copy of any phrase anywhere on the page).
- H2 every symbol is data with an inspection: `:`(classification), `→`(result), `|`(alternatives), `[ ]`(constructor),
  `↩`(reference), `*`/`* -> *`(kind). No decorative boxes; no unexplained numbers.
- H3 world structure from the thing in hand: inputs/outputs, sums/products, brand chain, docstrings, kinds;
  Many/Maybe/Later usable as draggable constructed types; relations drawn as a graph from the data.
- H4 world editing: the place where it would go is shown, marked not built (a glyph, no sentence), nothing faked.
- H5 long text: the five long prompts (≥ 850 characters), pasted/quoted text and code styled apart.
- H6 all of the data for a piece is reachable when opened (piece record, decision record, place record).

## Keyboard (parity with the pointer, same `/edit` bodies)

- K1 arrows move between links; Enter opens; Space picks up; arrows cycle the drop states (each previewed by the
  engine); Enter drops; Escape cancels.
- K2 `]`/`[` widen/narrow the end of the focused link, `}`/`{` its start, previewed then staged.
- K3 a type, constructed type, member or function can be picked up from the keyboard and dropped on words / places.
- K4 Accept and Undo by keyboard (`a`, `z`).

## NEVER-AGAIN (`notes/NEVER-AGAIN.md`), folded in on 10 Nov after it arrived mid-build

Added, never loosening anything above. How each applicable item is checked (audit id, or the independent review):

- A1/A4/B1 every drag in the audit is trusted Chrome input (CDP `Input.dispatchMouseEvent`) through Dragology's handlers;
  no probe calls page functions to move things (the page API is used only to wait and to name the reading).
- A2/A3 targets are taken from what is drawn, re-found by id before each gesture; links are compared with the server's
  `/readings` record of the snapshot the page names (A0, A2, B5, B6, E), never with the page's own copy; the rail's ✓/✕ is
  compared with the engine's `/edit` answer asked by the audit itself (D1).
- A5/A15/A16 criteria above are not loosened; the score reported is the independent review's verdicts, not the PASS count.
- A6/A7 no page hook for the audit, no `?audit` mode. (The board renderer is keyed by reading only.)
- A10/A23 the audit never touches browser storage; a save is proven by `/readings` after `/accept` (B6).
- A12/A13 Max's real long prompts (1,844–13,727 chars) with `<pasted_content>` and code; no fixture.
- A14 every run stored (`web/site/audits/board5/run*.json`, screenshots).
- A20 untested branches are listed in the report.
- A21 the only accept is undone by `/restore` in the same run (E); the store's latest is the pre-accept record.
- B1 G2 (no own pointer/mouse/drag listener; source grep).
- B3 pulling away (whenFar) unbinds; no trash target.
- B9 the whole consequence before release (B5); B10/B16 the rail gathers every place of the reading on screen while held.
- B12/B13 refusals show the engine's rule, the place and its declared type, and what was offered (`✕ type  f.p : T ⟵ v : U`).
- B14 one `/edits` request for a held thing's places, not one `/edit` each.
- B17 words carry their own kind as type when it is a world type, else the place's declared inner type; the engine decides.
- C1 the message once; C2 no prose (F); C4/C5 every glyph in the header key and inspectable; C10 no permanent world panel:
  the right column is empty until a thing is opened; C21 no text under 12 px; text colours ≥ 3:1 against the paper.
- D1 nothing about fit, validity or readiness computed in the page; D10 viewing never writes; D11 options shown with their own
  probabilities, never assumed equal; D19 world editing shown disabled (`＋ ⊘`); D20 a preview that refers to an incomplete
  operation shows `● complete ✕`.
- Not applicable / open: playback and search visualisation (C20, D12: not built); C24 (chips embedded in text vs. chain) is an
  open decision for Max.
