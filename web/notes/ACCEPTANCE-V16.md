# Acceptance criteria for the third board (written before the build; never loosened)

Source: the task brief of this session (the loop, the seven findings, the provenance note). Each criterion is tested with real
pointer / keyboard events in the browser against the lab engine (`lab/`, port 2781), and the run is stored in `web/site/audits/`.
A criterion is PASS only if the audit run shows the observed values; "not tested" is not PASS.

## L. The loop (one engine path for drag and for keyboard/menu)
- L1 Select an occurrence (a bound word, a place, an operation, a phrase) by click and by keyboard (Tab to it, Enter).
- L2 Moving a value to a place (drag with the pointer; Space-pick-up, move, Enter with the keyboard; "Move to" in the selection menu) makes exactly one POST /edit, and the page shows the engine's `draft` and `diagnostics`; nothing is saved (GET /readings is unchanged).
- L3 The preview shows the WHOLE consequence from the engine's draft: every operation whose arguments or judgments (valid, complete, pending, ready) differ from the base, each as before -> after; and the engine's diagnostics when it refuses. A refusal leaves the base on screen.
- L4 Cancel (button, Escape) restores the base exactly (same DOM text, no POST /accept); the store is unchanged.
- L5 Accept makes exactly one POST /accept with the same body as the preview; the page then shows the engine's saved reading; reload (a fresh GET /readings) shows the same reading with the correction recorded (corrections non-empty).
- L6 Rerun makes POST /rerun; the page shows each correction as retained or invalidated, with the engine's reason, at the place it concerns; the reading shown is the engine's saved one.
- L7 Restore (POST /restore) of an earlier snapshot is available and shown.
- L8 A stale or failed save keeps the draft on screen and shows the error (tested by an accept after the store changed).

## F. The seven findings
- F1 No edit is computed in the page: no localStorage / sessionStorage writes (checked), every state change in the reading is a response of /edit, /accept, /restore, /rerun. The page does not compute fit, validity, readiness or pending.
- F2 One representation: the source text appears once, in order, and each word of it occurs once as visible text in the page's reading layer (no operations table, no world graph, no repeated words). Operation names, place names and types are properties attached to their phrase/word, not a second sentence. Checked by counting occurrences of each source word in the reading layer.
- F3 Labels say exactly what the engine says at the level it says it: the page never says a word "is tagged" an operation; "then" belongs to a phrase read as `show`; a word with no record of its own meaning says so ("no meaning of its own is recorded; it is part of the phrase"). A candidate offered elsewhere is shown separately from the current binding.
- F4 One compatibility rule: every "fits here / does not fit" mark is an engine verdict from /edit (diagnostics empty or not). The page contains no type-compatibility function. Word menu and type menu give the same answer for the same pair (tested: both ask the same /edit).
- F5 Progressive disclosure: selecting opens a small card with one line of identity and a list of relationships, all closed; opening one reveals only that one; the card is never taller than 40% of the viewport on open (measured).
- F6 Evidence at the text: a recorded Stop check (from /log lines and `fulfillment`) is shown at the phrase/operation it concerns with PASS / FAIL / UNVERIFIED, its evidence (ran/wrote, exit), the prose judgment labelled "d1 judged", and for an unverified release the reason; recorded decisions are reachable at their text; decision scores are labelled as fixture inputs of a stand-in d1 (never "confidence").
- F7 Every semantic object is reachable by Tab with an accessible name; every relationship link is a button or link; every drag has the keyboard path of L1-L2; Escape cancels at every level; focus returns to the object after the card closes.

## P. Provenance and honesty
- P1 Scores labelled as recorded fixture/stand-in inputs, not live-model evidence.
- P2 What is not implemented is stated in the page or in the report, not hidden.
