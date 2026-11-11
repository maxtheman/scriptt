# Board 5: what is built, how to check it

Page: `web/site/index.html` + `web/site/board.js` (one Dragology `DraggableRenderer`, SVG). Acceptance: `notes/ACCEPTANCE.md`.
Audit: `web/site/audit.js`, driven by `web/audit-run.mjs` (headless Chrome over CDP: every pointer and key event is a trusted
browser input event). Runs: `web/site/audits/board5/run*.json`, screenshots in `web/site/audits/board5/shots/`.

```
node web/audit-run.mjs --accept --shots web/site/audits/board5/shots 8c7eae08 ffe36f28 2086c1e0 adf412fe a32bfced
```

`--accept` accepts one retag on the first reading through `/accept`, reloads `/readings` to check the store, then undoes it with
`/restore` (by keyboard, `z`). Without it nothing is saved; every other change is an `/edit` preview, cancelled.

## Shape

- The message once, in reading order. Words are the engine's words (`scriptt16.places`, mirrored for layout only), each piece of
  `pieces` is a link: underline coloured by what its kind is (type, constructed type, function, `(none)`, null), dashed for
  constructed types and null, thin when `sure` is false; its kind written above the words when there is room, a dot when not.
- Each operation: a bracket under its phrase and, after the phrase, `fn(place: slot, …) → Result`. Slots: `⇠` (the words in
  the text), member words (a world member), `↩ fn` (a reference to an earlier operation's result), `▢ T · reason` (a hole),
  `∅ T` (empty). `ƒ ▢ reason` = an unresolved request. A red dot = not complete; `⧗` pending; `⏲` deferred.
- The right column is the page of what is open (a link, a type, a function, an operation, a place) and is empty otherwise:
  no permanent world panel (NEVER-AGAIN C10). A type's page: `T : kind`, its docstring (world_record `describes`), brand
  chain (`⊂`), alternatives (`|`), members (`∋ n`), `Many/Maybe/Later[T]`, the functions that take it (`→ ƒ`) and return it
  (`ƒ →`), and `＋ ⊘` where world editing would go (not built in the engine). Every chip there can be dragged.
- Pasted text (`<pasted_content>` blocks, `>` lines, written replies) is italic on a tint; code fences are monospace.

## Every drag is a Dragology spec

- Words (grab a link; its kind floats as a translucent chip): `d.reactTo(verdicts known, …)` of `d.closest` over
  `d.dropTarget`s (the rail's places, the places in view the engine has not refused and the rail does not hide, each line of
  every link in view) `.whenFar(unlink)`, `.withFloating()`. Dropped on words = those words get this kind (adjacent words in the
  same phrase = the link widens over both); on a place = `/edit {constant, type, at}` where the type is the words' own kind when
  it is a type of the world, else the place's declared type (under Maybe/Many/Later, its argument); far = `(none)`.
- Handles of the open link: `d.closest` over the word boundaries ±12 words; widen = retag the wider span, narrow = the words
  let go become `(none)`.
- Types, constructed types (`Many/Maybe/Later[T]` on a type page), d1's options, functions: onto words (retag).
  Constructors (`Later : * -> *`) onto words wrap the words' kind. Functions onto `ƒ ▢` = a new operation (`number: null`).
- Members onto places (`at: [-1,-1]`), results (an operation's name) onto places (`{ref}`), a filled place's value onto another
  place, or far = cleared (`{hole, reason: "cleared"}`).
- The scroll bar is `d.vary` on the scroll position.
- A custom modifier, `drafted`, draws the engine's `/edit` draft for whatever state the spec chose, and redraws when the answer
  arrives; a refused state drops as no change and shows the engine's codes. When a drag starts, one `POST /edits`
  (`drafts: false`) asks the engine about every place of the reading and every word the thing could retag. Until it answers the
  rail shows `… n`; then it lists every place the engine accepts, `✓ fn #id.place : Type`, on rows growing up to half the view,
  and counts the refused (`✕ n`); places in the text carry ✓/✕ and words a dashed ✓/✕ outline. The targets are rebuilt then
  (`d.reactTo`), so refused places are not targets. A refusal in the dock names the rule, the place with its declared type,
  and what was offered.
- Keyboard: arrows move between links; Enter opens; Space picks up; arrows cycle the same options (each previewed); Enter drops;
  Escape cancels; `]` `[` `{` `}` widen/narrow; Tab switches to the right column; `a` accepts, `z` undoes.

## Known limits

- A single `/edit` (the draft under the pointer) takes 0.22–0.85 s; place verdicts come in one `/edits` request (lead's
  engine 8266fec).
- Nesting of two function spans inside one phrase and world editing: not in the engine; not drawn, not faked.
- A press during a page change (~300 ms spring) can land on the fading previous drawing. The renderer is not remounted to hide
  this (NEVER-AGAIN A6); the audit waits 450 ms after a page change, a person's pace.
- Not tested by the audit: the reading picker (the audit picks the reading through the page API), dark mode, narrow widths,
  `/rerun`, the scroll bar (`d.vary`), pulling a filled place's value away (cleared), a value moved from one place to
  another, the pointer drag of a d1 option, double Accept, a stale snapshot (`⟳`), wheel scrolling of the page column.
- While a thing is held the view cannot scroll (a Dragology drag holds one state); the rail is the way to reach places
  out of view. Beyond half the view of rows it counts `+n` (not reached on the five prompts: at most 22 places).
- Holes and `ƒ ▢` are drop places, not things to pick up. The key in the header is a key, not a control.
- Operation chips sit inline after their phrase. Max said "It's not plugs and sockets embedded in text"; NEVER-AGAIN C24
  makes this an open decision for Max.
