# UI specification (10 Nov 2026, revised)

This replaces the earlier version of this file. It is checked against real saved readings from the repaired engine:
`web/site/engine/readings.json` (38 form-5 lines written by the engine's `record()`, repair commit 82c8e34, each
tagged with its case) and `web/site/engine/worlds.json` (`agree.world_record()` for each world hash). The lead
regenerates both when the engine changes; never edit them by hand.

## What exists, and where it comes from

| Data | What it represents | Where the UI gets it |
|---|---|---|
| Source and phrases | The words, their positions, grouping, origin (`brand`: the user's words / a quoted reply) | the saved reading: `text`, `phrases[i]` `start`, `end`, `brand`, `quotes` |
| Terms and bindings | Requested operations, their inputs, nested records and lists, missing inputs, references to earlier operations | the saved reading: `phrases[i].terms`, `unresolved`; values `constant`/`at`, `several`, `fields`, `empty`, `hole`/`reason`, `{"ref": id}` |
| World definitions | What each operation accepts and returns; type alternatives, fields, brands, constructors, kinds | `worlds.json[reading.world]` = `agree.world_record()`: `identity`, `types` (each `tree` + `kind`), `constructors` (`kind`, `describes`), `functions` (`asks`, `parameters` as `[name, tree]`, `result`) |
| Decisions and corrections | What was considered, chosen or excluded (with d1's scores), and what the user changed | the saved reading: `decisions` (`by`, `rule`, `state`, `asked`, `answers`, `function`, `operation`, `path`, `offered`, `cut`, `chosen`), `corrections` (`operation`, `function`, `phrase`, `path`, `others`, `value`, `refers`, `status`, `reason`) |
| Separate judgments | Valid, complete, pending; whether evidence satisfies a criterion | each application's `judgments` (`valid`, `diagnostics`, `complete`, `pending`, `ready`), written by the engine; fulfillment = `check()`'s results, only when a check has run (not saved in readings yet) |

Types in the record are names (`"Surface"`, `"Later[Surface]"`); their structure is in the world serialization, once.
Each application carries `parameters`: each argument place's declared type name (e.g. `show` → `{"subject": "Subject"}`),
so "what fits here" never comes from the current value. The page must never compute meaning itself (what fits, what is pending, what is valid): it reads the engine's
output, or asks the engine.

## The data source (do first)

- Load `web/site/engine/readings.json` (engine-written, form 5). Delete hand-written readings and the form-4 samples.
  One record format in the repo: form 5.
- Drive the world from `web/site/engine/worlds.json` (live now), not a hand-made world (`WORLD0`).

## Interactions: what is selected, what is followed, what changes, what is checked

| Interaction | Exact thing selected | Relationship followed | Operation that changes it | Validated and saved |
|---|---|---|---|---|
| Hover a word | the span `[start, end]` of a constant or phrase | its enclosing phrase and the operation(s) of that phrase | none (view only) | nothing |
| Click a value ("the mod") | the constant `{constant, type, at}` | the argument place that holds it (`operation id` + `path`), its type, and the type's kind and definition in the world | none (view only) | nothing |
| Click an argument place | operation id + path | the declared type (what fits), the current value (what is here), and the decision for that place: offered, chosen, rejected, cut, with d1's scores | preview another candidate → engine `edit(reading, operation, path, value)`; accept it → engine `correct(...)` | `edit` validates and returns a draft + diagnostics (a preview; the base stays untouched; cancel = keep the base). `correct` records the user's accepted choice, so a model rerun keeps it or invalidates it with a reason. Save appends; a save from a stale base is refused |
| Click a reference (`{"ref": id}`) | the place that holds the reference | the operation it refers to (same result, not a copy) | rebind it to the original value or another candidate → `edit` | as above; rebinding never creates a second operation |
| Click an operation | the operation id | its function's signature in the world (parameters and result types), its places, whether it is pending (waits on a referenced operation) or has open holes | clear or set its places → `edit` | as above |
| Click a type name | the type's name | its definition in the world (members / alternatives / fields / brand and what it wraps / constructor and kind), and the functions whose parameters accept it or whose result is it | none in this repair (world editing is a separate, gated operation) | nothing |
| Apply a function to a thing | the thing (a constant, or `{"ref": id}`) and a world function's parameter | the parameter whose declared type accepts the thing (from `worlds.json`) | engine `edit(reading, None, "function.parameter", value)` to preview; `correct(...)` to accept (coming with the repair, in scope) | the engine builds the new operation with a NEW stable id (existing ids never change), the thing in that place and cleared holes elsewhere, validates it, and refuses with the reason when the type does not fit; base untouched; an accepted one survives a rerun or is invalidated with a reason |
| Step through decisions | a decision index | the text it concerns and its exact question, options and answer | none (view only) | nothing |

## Kinds of missing (show each distinctly, with its reason in words)

- `{"hole": T, "reason": ...}`: `rejected` (d1 declined every candidate), `no candidate` (nothing in scope fits),
  `bounded` (the search bound cut candidates), `invalid answer` (d1's reply was malformed), `cleared` (the user
  cleared it).
- `{"empty": T}`: a deliberate absence (Maybe), needs a recorded absence decision.
- `{"several": [], ...}`: an explicit empty list (Many), different from a hole.
- `phrases[i].unresolved` `{id, reason}`: a request whose operation is unknown; it stays visible as owed work, never
  "nothing" or "none".

## Known limits (do not present as hidden data)

- Operation ids are stable identities, not positions: a new operation gets a new id and nothing is renumbered; order on
  the page comes from the phrases, never from the id.
- `judgments.ready` is changing meaning to "can start now" (valid, complete, no input waiting on a pending result); a
  separate judgment will say the operation's own result is deferred (`Later`). `redesign(mod)` can start with its result
  deferred; `show(redesign(mod))` waits. The repair report gives the final names.
- A reference's source word is not separately represented: "it" is part of its phrase; the argument place holds
  `{"ref": 0}`. Highlight the phrase, not a word.
- Project-wide navigation — "which actual notebook is this", every mention of that same object across messages —
  needs object identity the engine does not have: "the notebook" is a recognized member of `Code`, not an identified
  notebook object. Within one reading, and the same declared member across saved readings, are available; anything
  beyond that is additional engine work, not decoration.
- Fulfillment is not in a reading unless a check ran, and it is per obligation and criterion, not per argument.

## Design suggestions (not requirements)

Arcs for references, outlines per kind of missing, a pending mark, a decision scrubber, ghosts with scores: these are
suggestions. The requirement is progressive disclosure of the relationships above through the text: ordinary English
at rest, then hover, click, expand (interaction contract,
`/Users/max/Documents/scriptt-design-review-2026-11-10/interaction-contract.md`).

## The immediate demonstration

One real engine reading plus its matching world: "Redesign the mod. Then show it." Follow "the mod" to its argument
place (`redesign.surface`), its declared type (`Surface`), its kind (`*`), the reference from `show.subject` to
operation 0, and the functions that accept a `Surface`. Preview rebinding `show.subject` to the original mod with
`edit` (draft + diagnostics), cancel (the base is back), then accept it with `correct`, save, reload (the same
reading), and rerun with the model preferring the original binding: the accepted correction is retained. Still
unfinished and shown as such: project-wide object navigation (which actual notebook; identity across messages).
