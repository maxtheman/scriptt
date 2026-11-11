# Board 5 brief (from the lead, 10 Nov 2026, confirmed by Max)

This file is the brief. `V4-BRIEF.md` and `V5-JOBS.md` were removed from this branch; their history is on
`ui/board-4`.

**Where you work:**
- Worktree: `~/Documents/scriptt-ui-5`, branch `ui/board-5`, forked from board 4's last commit (a66d351).
- Board 4's page is your starting code: `web/site/board.js`, `index.html`, `audit.js`. Keep what works and replace the
  rest.

**Read these first:**
- `notes/MAX-FEEDBACK.md`: every message Max typed into the four board sessions, verbatim. This is the authority over
  anything below that disagrees with it.
- `notes/FIRST-PROTOTYPE-NOTES.md`: his notes on the first three prototypes.
- `notes/NEVER-AGAIN.md`: every failure of boards 1–4, with evidence. Each one is a requirement. Your acceptance
  criteria and your independent check must cover every applicable item.
- `UI-SPEC.md`.
- `/Users/max/Documents/scriptt-design-review-2026-11-10/interaction-contract.md`.

## The shape: the message as a wiki page over the world's ontology

Max: "treating this kind of like a wiki or an ontology is really great and the types and the kinds can form the
hyperlinks… it's like if every single span was piped and also some spans actually represent functions and maybe there's
even nesting of functional spans."

- **Every span is a piped link** (as in a wiki, `[[Type|the words]]`). The words stay as written. The link goes to
  their type or kind: its members, alternatives, fields, brand, constructor, docstring, and the functions that take it
  or return it.
- **Some spans are functions.** The words that ask for an operation link to the function (its signature). The spans of
  its arguments sit inside that span.
- **Function spans nest:** `show(redesign(the mod))`.
- **Retagging is re-piping:** drop a different target onto words, or widen and narrow the words a link covers.

## What Max liked (keep these; build on them)

- **From the first prototypes:**
  - "Highlighting multiple items in place."
  - Different types inside `Subject`.
  - "Showing how the prompt is compiled and what is sent to d1."
  - "I like being able to drag things together to show they are related in some way."
  - "I like the state reset. I like the derivation. I like the sockets."
- **From board 1:**
  - "The plug and socket chain is definitely the direction that I want to go in, but everything needs to be part of a
    chain."
  - "The UI should just be a different tab."
  - "I like that the highlighting works now."
  - "I like the actions being prominent and being the only thing to work on."
  - "I really like the stuff down below" (the lower section). "I do like the grouping in this section."
  - "There's a lot of good stuff in the three sections and how they interact."

  What failed on board 1: how the sections relate, the impact of a move, a confirm state, and two copies of the text.
- **From board 2:**
  - "You're moving in the right direction."
  - The type marks (`x`, `*`, `.`): "Nice that you pull them out."
  - Many, Maybe and Later: "It's great those are there… I think they're actually quite powerful" (they must follow the
    same rules as everything else, and be usable).
  - "Honestly, I think you're really close."
  - Asking another agent for advice and inspiration: "I think that worked pretty well."
- **From the board 3 and 4 reviews (the lead's), already in board 4's code:**
  - the text once, in reading order;
  - progressive disclosure;
  - every edit through the engine: preview, accept and cancel, with the before→after strip;
  - keyboard pick-up;
  - pasted text styled apart from Max's words.
  - Not board 4's permanent world panel. Max rejected a permanent palette or separate data panel (`notes/NEVER-AGAIN.md`
    C10). World members, types and functions are reached from the thing in hand, through its link page, and brought
    near while you drag.
- **Pieces Max approved last week, outside these boards:**
  - **The Cmd-D inspector:** "Ok, it's working!", "This is much better". Look at values in place of prose.
    `~/Documents/local-ai-workers/experiments/python-types/tools/inspector.py`.
  - **The replay page's tags:** "The tags are great… I love that". And the core workflow chart: "I really like this core
    workflow chart". `~/Documents/scriptt-lab/viz/replay.html`, `loop.html`.
- **Inspirations he named:**
  - Dragology's own examples (permutation-lab, animate-algebra-tree; `whenFar`, `d.between`, speculative states);
  - Ink & Switch Potluck (plain text stays plain; computation happens quietly in place) and Embark;
  - Graspable Math (the terms are the objects you handle);
  - Descript ("if this was Descript, how would the UI look?").

  Look at the real examples before claiming a library can't do something. Max caught that once: "I don't think that's
  true."

## Dragology: every drag goes through it (the most failed requirement)

Max: "by far… people keep failing to use the Dragology library… You can drag it anywhere, but it doesn't do anything when
you drag it most places and it doesn't speculatively render… I bet you we've rolled our own three times."

They did. Board 4 vendors `web/site/vendor/dragology-0.2.0.iife.js` but never loads it, and drags with its own document
`pointerdown`/`pointermove` handlers (`web/site/board.js:610`, `:626`).

- **Load Dragology and use it for every drag.** No hand-written pointer, mouse or HTML5 drag handlers for moving
  things.
- **Model the board as Dragology states.** Each possible drop is a state the library renders speculatively while you
  drag:
  - `d.between` / `d.closest` over the candidate states;
  - `d.dropTarget` for places;
  - `whenFar` for pulling something out into open space (an unbind, no trash can).

  The page shows the engine's draft for the state under the pointer.
- **Every drag does something everywhere:** snap to a place, re-pipe words, widen or narrow a link, or pull out with
  `whenFar`. Nothing should be draggable to a spot where nothing happens with no visible reason.
- **Reference:** the released board, `~/Documents/scriptt-release/web/public/index.html`, already uses Dragology:
  - `<script src="vendor/dragology-0.2.0.iife.js">`, at line 131;
  - `dragologyOnDrag`, `whenFar`, at line 379.

  Upstream library and examples (permutation-lab, animate-algebra-tree): https://github.com/declarative-dragging/dragology.
  Read the examples before deciding something can't be done.
- **The audit fails the build** if `board.js` registers its own pointer, mouse or drag listeners for moving things, or
  if a drag test does not go through Dragology's drop targets with real pointer events.

## Jobs, by severity

### Severity 1: the thing itself, never delivered

1. **Retag by dragging.** Change which words a tag covers and what they are tagged with. The words stay where they are.
   - "Dragging the words isn't about moving the position of the word… We're dragging the sorts of things the words are
     tagged with and what is being tagged."
   - "You can't change how wide a tag is… If I drag 'rewrite' into 'this version' nothing happens."
   - "Can I drag in a type that's useful? Can I then retag different parts of the sentence this flexibly?"
   - "Or maybe a synthesized type, but either way those should be allowable." (a type built with Later, Many or Maybe)
   - "Every piece of text needs to be draggable."
2. **A rejected or open place takes something useful.** You can drop words, a world member or a result into it. This
   is revisiting d1's decision: "I want to drag arbitrary words into a span… drag things from the world into the span."
3. **Linking while dragging.** Grabbing something shows what accepts it, and those places come close.
   - "If I grab a string, which things take strings."
   - "Re-rank the things as you grab them, so anything that you can actually drag to is on one page."
   - "There is no linking of states between the dragging we are doing and any of the types or other objects in the
     world. That's a big part of why Draggable is interesting at all."
4. **The impact shows before you let go, with confirm and undo.**
   - "It's not clear when you're moving something what the impact of that will be or when you click on something what
     the potential actions are and why."
   - "The states don't move in a way that makes sense based on where I'm dragging."
   - "I can't easily undo actions and the zones are tough to get."

### Severity 2: hard requirements broken repeatedly

5. **No text from you.** "Minimal text from you, if any. Headers can be okay… headers and icons and usual chrome."
6. **The message appears once.** "I don't like that the text is duplicated."
7. **Every symbol carries meaning and can be used.**
   - "The zero one and two and shapes are all still pretty meaningless."
   - "What are these four question marks trying to say?"
   - "Everything is in boxes and the boxes don't contribute any additional information."
   - Never mix up path, function and int.
8. **The world's structure, inspectable from the thing in hand:**
   - function inputs and outputs;
   - sum and product types, and what a type inherits from or is made of;
   - docstrings, kinds and brands;
   - Many, Maybe and Later as usable objects;
   - the world's relations drawn from the data, never as a linear chain.
9. **Change the world.** "There is no way that I can change anything in the world." The engine does not do this yet.
   Show where it would go, and state that it is not built. Never fake it in the page.
10. **Real text:** long markdown, pasted text and code. Test on Max's long prompts, never the three-sentence specimen.
11. **All of the data for every piece.** "You don't expose all of the data for every piece." This includes what was
    sent to d1 and d1's options and scores for a decision or a word's tag, shown when opened.

### Severity 3: quality

12. **The top ten questions** Max might have about one word, each answered in few clicks. Write the ten first, and
    count the clicks.
13. **Typography and gestalt:** contrast, repetition, alignment, placement, grouping like with like.
14. **Show the search in the same visual language.**

Not asked for, so don't add it: counting unsure words on the page.

## The engine you build on (never edit it; ask the lead for changes)

The engine is repair commit d73d670, receipt FINAL. Lab files are in `~/Documents/scriptt-ui-4/lab-kinds`. It is served
at http://127.0.0.1:2801/index.html, and its `.scriptt/site` links to THIS worktree's `web/site`.

- **Data:** Max's real prompts (40 to 13,727 characters) read with the real d1, under a world (`.scriptt/world.py`)
  that adds his own vocabulary: Concept (type, hole, function, constructor, brand, kind, term…), Text, Agent, Step,
  Verdict, Time.
- **The re-read is still running.** A background run is re-reading the prompts under that world, so the store grows for
  a while. Don't touch its scripts, its store or its server; use the latest snapshot of each reading.
- **Endpoints:**
  - GET `/readings`, `/worlds`, `/log`.
  - POST `/edit` and `/accept` with `{reading, number, path, value, phrase?}`: places and new operations
    (`path: "function.parameter"`, number null).
  - POST `/restore`, `/rerun`.
  - See `harness.py serve()`.
- **Every word's kind:** each saved reading has `pieces: [{start, end, kind, share, sure, by}]`.
  - `kind` is a world type, a function, `"(none)"`, or null for an invalid d1 answer.
  - The kind questions are in `decisions` with `path: "kind"`, together with d1's shares for every option.
- **Retag:** POST `/edit` or `/accept` with `{reading, path: "kind", at: [start, end], value: KIND}`.
  - KIND is a world type, a constructed type such as `"Later[Surface]"`, a function, or `"(none)"`.
  - Diagnostics: `kind` (not in the world), `place` (not whole words), `identity`.
  - A retag cuts the pieces it overlaps. It survives a rerun, or is marked invalidated with the reason.
- **Nesting:** an operation covers its phrase; its constants have their own spans (`at`); a reference `{"ref": id}`
  points to an earlier operation. So nesting through references and one level within a phrase can be drawn now.
- **What the engine does not give yet:**
  - nesting of two function spans inside one phrase;
  - world editing.

  If you need either, tell the lead exactly what record you need. Don't compute meaning in the page.

## Acceptance (write it first from this brief; never loosen it)

Headline, on at least five of Max's real long prompts, each by pointer and by keyboard:
- (a) The message reads as one wiki page. Every span links to its type, kind or function. Opening a link shows that
  thing's page from the world, and its d1 data.
- (b) Retag by dragging:
  - widen or narrow the words a link covers;
  - drop a world type onto words;
  - drop a constructed type (`Later[Surface]`) onto words.

  Each one previews through the engine with the whole consequence visible before release, then accept or cancel. After
  accepting and reloading, the store has the correction.
- (c) A rejected place takes a dropped word, world member and result.
- (d) While a thing is held, only the places that accept it are highlighted and brought near, by the engine's verdict.
- (e) Undo after accept.
- (f) No sentence of agent-written prose on the page. Headers, icons and chrome only.

Test with real pointer and keyboard events in the browser. Store the audit runs with the build. Before you report, have
an independent sub-agent check against `notes/MAX-FEEDBACK.md` and this brief. Report with screenshots of (a), (b) and
(c) on a real prompt.

## Rules

- Touch only `web/`, `notes/` and this brief.
- Never edit the engine (`next/`, `scriptt/`, `web/site/engine/`), the lab's scripts, or its store.
- No deploy, no push, no hooks installed anywhere.
- Never touch ports 8765 or 2746.
- Commit on `ui/board-5` with plain messages.
- When you're blocked on an engine change, message the lead with the exact record you need.
