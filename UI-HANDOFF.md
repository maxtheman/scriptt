# UI handoff: the data the board will receive (draft, 10 Nov 2026)

This worktree (`~/Documents/scriptt-ui`, branch `ui/board`) is for the interface: `web/` (the Dragology page,
`web/site/index.html`) and `mod/` (the Claude desktop mod). It starts from branch `next/rewrite`, so it already has
the page work of 10 Nov: one paragraph in drag mode, Many holes, Undo, and the d1 prompt inspector.

The engine (`next/`) is being repaired in a separate worktree, `~/Documents/scriptt-repair` (branch `next/repair`).
Do not edit `next/` here. When the repair is done, the lead integrates it with this branch. Until then, build against
the shape below through ONE adapter function (record line in, board state out), and test it on hand-written sample
lines in that shape. The final shape will be handed over with the repair; expect field names to change, not the ideas.

## What one saved reading will hold (planned)

- `text`: the message, and the identity of the world it was read against (a hash).
- `phrases`: the source grouping as a tree (start, end, brand: `Asked` / `Written`), each leaf with:
  - the raw d1 choice as metadata (scores of every option); `none` / `nothing` are metadata only, never the meaning;
  - its term, or an explicit unresolved obligation when the operation is unknown (the phrase stays, typed by its
    brand; nothing is dropped);
- terms, recursive, one of:
  - `Constant` — type (as a tree), the typed value, its span in the text;
  - `Application` — a stable id, the function, one term per argument;
  - `Record` — a product type with one term per field;
  - `Several` — the members of a `Many[T]` (an explicit empty list is different from a hole);
  - `Empty` — a deliberate absence for `Maybe[T]`;
  - `Hole` — a known type that is still open, with the reason (no candidate / search bound / d1 declined);
  - a reference to an earlier result as `{"ref": id}` — the same result, not a copy (identical-looking operations
    keep separate ids);
- `constants`: every grounded span in the message, bound or not (so any of them can be dragged into a hole);
- `decisions`: every d1 question with its state, instructions, options (id + description), answers, and the phrase
  and argument path it was about; automatic bindings and limits are recorded too;
- `corrections`: each explicit user edit (phrase, path, before, after), kept on rerun or marked invalidated with a
  reason — never silently overwritten;
- validation diagnostics for a rejected edit (the prior reading stays);
- fulfillment per obligation and per bound argument: PASS / FAIL / UNVERIFIED with the evidence used.

## Edits the engine will offer (plain functions)

Read, validate, edit (one change to one place, returns the new reading or diagnostics; the prior reading is
untouched, so a preview is just the returned value and cancel restores the original), save (append a line; a failed
save keeps the draft), load (latest or an earlier snapshot). The board should call these instead of computing its own
legal moves; its drag targets come from the engine's candidates for a place.

## The target experience

`/Users/max/Documents/scriptt-design-review-2026-11-10/interaction-contract.md` (and `charts/`) describes the
intended editor: ordinary English at rest, click/hover to inspect, drag to propose with a whole-state preview, an
explicit unresolved hole, save/reload/undo, a rejected drop explained. It is a proposed contract, not all approved.

## Rules

- Touch only `web/` and `mod/` (and this note). Nothing under `next/`.
- Do not deploy (no `cf` / `wrangler` deploy, nothing live) and do not push. Max previews first.
- Never restart anything on port 8765 (the d1 service). Never touch port 2746 (Max's open notebook).
