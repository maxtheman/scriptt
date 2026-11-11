# Ten builds of the board, each one scored, criticised and improved

Brief: Max's request is one text-first editor in which the message itself is made of typed, manipulable pieces
(`UI-HANDOFF.md`, `interaction-contract.md`, and the handoff of the stopped prototype: R01 to R48).
Goal set for this session: ten builds, each better than the last, meeting all of those criteria.

How "better" is measured: `web/site/audit.js` holds 32 probes, one per criterion (C01 to C32), each mapped to the
requests it comes from. Open any snapshot with `?audit` and run `await AUDIT()` in the console. A probe reads the page like a
user does (the DOM, clicks, keys) and fails when the thing is absent. A score is the number of probes that pass.
Snapshots are `web/site/versions/vNN.html` (serve `web/site` and open `/versions/vNN.html?audit`; they are not part of the built site).

What the probes cannot see is written under each build, from looking at the page.

| Build | Score | What changed |
|---|---|---|
| v00 | 5/32 | the page as it stood (3cca462) |
| v01 | 17/32 | marks you can name |
| v02 | 20/32 | no palette; click opens one panel; one `transitions()` function |
| v03 | 25/37 | every phrase is one chain of interlocking blocks; a press never changes the reading |
| v04 | 27/37 | tabs (Board, d1, Install), no prose, Undo and Redo always visible |
| v05 | 30/37 | follow a relation and go back, type definitions, d1's options at their place |
| v06 | 32/39 | no Edit gate; every word is a thing to pick up; a span of words grounds as a value; long sample |
| v07 | 36/41 | the world on the board, live-linked by type; tagging both ways |
| v08 | 37/42 | the world can be changed (members, functions, types), previewed, one Undo for everything |
| v09 | 41/44 (not rerun in full) | every record behind every piece, refused drops explained, corrections kept and read again |
| v10 | 46/48 | the world as a typed graph, type structure (sum, product), doc strings, re-rank while holding, arrows, informative labels, typography, tag width |

The probe count grew from 32 to 48 as Max's feedback added criteria, so a score is only comparable with the builds next to it. v00 scored 5/32 on the first audit.


## Critique of v00 (5/32)

- The message is whole at rest and in Edit (C01, C02), keys work (C13), the width fits (C23), the recorded messages draw (C29). Everything else fails.
- A permanent palette of 41 pieces (functions, types, members) sits under the paragraph in Edit. It shows every value a second time (7 duplicates) and is the "independent data panel" that Max rejected (R15, R16).
- No mark names its role. Type is a color only, and 3 of the 9 colors (yellow, pink, mint) fail 3:1 as borders. Hovering says nothing except for operations.
- A click does nothing. There is no panel, no way to follow a type, no reason for a refusal, no history, no Play.
- The mode button says the product name, not what it does.
- Long authored sentences sit in the inspector.
- Plug and notch: operations and places are different shapes that do not join (the failure Max showed in `03-pieces-do-not-fit.png`).

## v01 · marks you can name (17/32)

Change: every mark has a role (value, operation, place, reference, unresolved, phrase), a hover label made from its data, and a stable id.
A type is a glyph plus a color (6 shapes by 12 colors), the border is always the neutral ink, so 3:1 holds.
An operation ends in a plug, its places begin with the matching socket and chain to each other. A reference carries the id of the operation
that produced it, so two operations of the same function stay two (the sample with two `implement`s), and hovering one lights the other.
An Empty, an empty list and a hole are three different frames. An unresolved phrase keeps its brand and its reason. Tokens cite their source. The button says Edit.

Critique of v01:
- The palette is still there (C03, C30), and nothing happens on a click (C07 to C11).
- The plug fits the socket in the picture, but a place that wraps onto the next line leaves its plug in the air.
- The Edit paragraph is cramped: chips are 28 px tall on a 28 px line, and the `#n` badges touch the line above.
- A value that sits in a place of its own part is now drawn as `questions #1`. It reads, but the `#1` is the only link to the word.

## v02 · nothing until you point (20/32, in progress)

Change: the permanent palette is gone (C03, C30). A click on a thing selects it and opens one panel under the paragraph, drawn in the same renderer:
what it is (type, source, what it holds, which operation it belongs to, why it is open), then the edits it offers. Drag, keys and the panel all read
`transitions(ev, st, ref)`. Pulling a value or an operation far away does what Dragology's `whenFar` does (unlink, clear, remove); there is no trash box.

Found while building (real bugs the audit exposed, not in v00):
- Dragology blends the props of one element between two states and throws on a string that differs (aria-label). Ids now carry their content, labels are stable, what changes goes in `data-`.
- `data-path` is the library's own attribute: using it for the argument name broke bounds lookup. Renamed `data-arg`.
- The keyboard "held" outline had no height for a piece (NaN rect). Fixed.
- A press on a chip that has a grab lands on the lifted grab group, not the chip: `data-ref` goes on both.

Open at this point:
- Pressing a value in the sample with two `implement`s can throw `dropTarget: could not compute bounds for element "h-d1-implement.questions"`, and the renderer then stops drawing the panel until reload. Not understood yet. C07 and C11 fail because of it.
- Following a relation, the panel's Back, type definitions (C09, C10), decisions at their place (C28), refusals (C14), history (C18, C19), Play (C20), prose (C21), markdown (C25), map (C26) are not built yet.

## What Max said after v05, v08 and how v10 answers it (all in v10)

Max's words are in `FEEDBACK-SESSION.md`. Each point, and where it went:

- Text duplicated, unclear what to drag: the panel no longer repeats the thing, the world no longer lists members next to the message (members show only in a type's structure, where they can be dragged), a held thing draws an arrow to each place that takes it, and refused places say why.
- Functions typed with inputs and outputs, and "if I grab a string, what takes strings": the world is a typed graph (types left, functions with a port for each input, the types they give right, a curve for each use). Grabbing or selecting a type lights its curves and the ports that take it.
- What `Code` is made of, sum and product: selecting a type draws a fork to its members (sum) or a box of its fields (product), with what it is part of, what makes it, what takes it.
- Doc strings: shown for functions (`asks`) and types (`doc`).
- Re-rank while holding: the functions that take what is held come first in the graph (the layout depends on what is held).
- Labels like "→ ❷": every action now names the operation or the place (`→ ➋ implement.questions`).
- The world is not a chain: it is a graph from the data; the chains are the message and the panel.
- Typography: a rhythm of 8 px units (blocks 40 px, rows 12, chains 28), 16 px text and 13 px notation set on the cap height, quiet borders for words and strong ones for typed things.
- Words: dropped on a tag they make it wider (refused with a reason when the new words are not a member of the type); the panel also offers + and − for each end.

Deferred, with the reason and the way in:
- Kinds as first-class (`Type → Type` for `Many`, `Maybe`, `Later`): the readings that the engine saves today carry `Many[T]` and `Maybe[T]` only as type names inside a place. The board shows them there. When the engine sends type-level terms, a constructor will be a block with a slot (`Many[ ]`) and a kind line, drawn like the other blocks.
- Brands (`Asked`, `Written`, `Observed` over `Words`): shown on each phrase (`data-brand`, the tag, the panel). The world has no brand declarations to draw yet; when `world.py` is sent with them they become a fork under a `Words` node, like a sum.
- Folding and unfolding of nested phrases: the saved readings are flat (one level of phrases). A phrase group will fold to its first words and unfold to its chains; no fold control is drawn until there is a group to fold.
- Regrouping phrases (split, merge, move a boundary): this is the engine's job (the contract lists it under source and grouping: it must re-anchor or invalidate). The board will send the request as a correction; it does not fake a regrouping.
