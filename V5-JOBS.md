# Next board: jobs, and the pieces from boards 3 and 4 that do them (lead, 10 Nov 2026, evening)

Max, verbatim: "the rejected thing needs to have a way for the user to do something useful with it… Can I drag in a
type that's useful? Can I then retag different parts of the sentence this flexibly using drag and drop? That's the
entire thing that we're trying to build." And: "I want to drag arbitrary words into a span… drag things from the world
into the span. This is me wanting to revisit a D1 decision." "Or maybe a synthesized type, but either way those should
be allowable." On words d1 types with low confidence: "that's a sign to both agent and user that there's misalignment."

## What changed in the engine (repair commit d73d670, receipt FINAL)

Every word of a message now has a kind. A saved reading has `pieces`: `[{start, end, kind, share, sure, by}]`.
- `kind` is a type of the world (`"Concept"`), a function (`"redesign"`), `"(none)"`, or null for an invalid d1 answer.
- `share` is d1's smallest share over the piece's words. `sure` means share ≥ 0.5. `by` is `"model"` or `"user"`.
- Neighbouring words of one phrase with the same kind form one piece.
- The kind questions are kept in `decisions`, each with `path: "kind"`, `phrase: [s, e]`, `asked` (one question per
  word with every option), `answers` (d1's shares for every option) and `chosen` (one kind per word).

Retag through the engine:
- **Preview:** `POST /edit {reading, path: "kind", at: [start, end], value: KIND}` returns `{draft, diagnostics}`.
- **Save:** `POST /accept` takes the same body and saves the retag as the user's correction.
- **Allowed KIND values:** a world type, a type built with a constructor (`"Later[Surface]"`, `"Many[Code]"`,
  `"Maybe[Words]"`), a function, or `"(none)"`.
- **Diagnostics:** `kind` (no such type or function; nothing new enters the world), `place` (not whole words of the
  text), `identity` (another world).
- **Overlaps:** a retag cuts the pieces it overlaps; their words outside the retag keep their own kind.
- **Rerun:** a retag is kept, or marked invalidated with the reason when the world no longer has the kind.

The hook tells the agent which words have no sure kind, so it asks the user rather than substituting.

Lab: `~/Documents/scriptt-ui-4/lab-kinds` (git-excluded), serve on :2801 when the typing run finishes.
- Max's 48 real prompts are read with the real d1, and every word is typed.
- The world (`.scriptt/world.py`) adds Max's own vocabulary: Concept (type, hole, function, constructor, brand, kind,
  term…), Text, Agent, Step, Verdict and Time. Every old function stays.
- `.scriptt/world-before.py` is the old world. The readings typed under it are earlier snapshots, kept for comparison.

## Jobs the board must support, each traced to Max's five problems and to what went wrong in the Fable threads

| # | Job | Problem | Seen in the threads | Engine | Board 3/4 has it |
|---|---|---|---|---|---|
| J1 | See every word's kind at rest: what the system thinks each word is | 2.2, 2.4, 3 | "these are just strings… They need to be typed"; "how would you take a look at all of this text and start typing it?" (Fable: "This step was run on no text") | `pieces` | no |
| J2 | See where it is unsure, and how much: a count of unsure words, and each unsure piece marked | 2, 3, 5.1 | Max: low confidence is the sign of misalignment | `sure`, `share`, hook line | no |
| J3 | Retag any words: select arbitrary words (drag their ends, or by keyboard), drop a kind onto them: a world type, a constructed type (Later[…], Many[…], Maybe[…]), a function, or none | 2.4, 4, 5 | "sometimes I'm talking about types… higher kinded types or maybe variables or maybe brands"; Fable chose "the five goal types" by hand | `retag`, `/edit path kind` | no |
| J4 | Revisit a d1 decision at a place: drop words, a world member or a result into an open, rejected or filled place | 3, 4 | "the rejected thing needs a way for the user to do something useful with it" | `/edit` | board 4 |
| J5 | See what d1 was offered for any decision, with its shares, including the kind question of a word (top options) | 3 | "allow me to introspect how they got to their answer" | `decisions` | board 4 (places only) |
| J6 | Preview the whole consequence before saving; accept as my correction; cancel back to the base | 3, 4 | "change the context that got into a specific answer to get a different one" | `/edit`, `/accept` | board 4 |
| J7 | Corrections survive a rerun, or say why not | 2.5, 4 | "always lost"; "early errors compound" | `rerun` | board 4 (button) |
| J8 | No new words: offered kinds come only from the world; a kind outside it is refused with the engine's reason | 5.2 | Fable introduced `UNUSED_GIVEN`, `NOT_DEMANDED`, "mixed list", "second reader" | diagnostic `kind` | n/a |
| J9 | Tell Max's words from pasted agent text | 3.2 | "his original words are hard to separate from LM specs" | `brand`, `quotes` | board 3 styling |
| J10 | Evidence per request: PASS / FAIL / UNVERIFIED at the phrase | 4, 5.1 | "an 'x-style' reproduction"; "I don't totally trust that process" | `fulfillment`, `/log` | board 3 (F6) |

Not covered, said plainly:
- Problem 1 (asking many times and triangulating) has no job here.
- Which actual object a word means across messages is not represented.
- Live-d1 accuracy is not measured.

## Pieces to keep

- **From board 3:** the text appears once, in reading order, with nothing duplicated. Progressive disclosure. Pasted
  text styled apart from Max's words. Evidence shown at the phrase.
- **From board 4:**
  - drop into places through `/edit`;
  - the staged before→after strip, with accept and cancel;
  - keyboard pick-up (Space), move, drop (Enter);
  - the world panel with members, functions and results;
  - the structure gutter, and the open-places row naming each reason in words.

## What to add (the core of this version)

1. **The kind layer at rest.**
   - Each piece gets a quiet underline coloured by its kind.
   - A small kind label shows on hover or focus, never inline clutter.
   - Unsure pieces get a visible dotted mark.
   - A banner says "N of M pieces have no sure kind in this world", and each piece in it is a link to its words.
   - "(none)" pieces stay plain. A null kind (invalid answer) is marked as such.
2. **Select arbitrary words.**
   - Drag across words, or click a piece and drag its ends.
   - By keyboard: Shift+←/→ extends the selection by whole words.
3. **The world panel lists kinds you can pick up:**
   - every type (with its description),
   - every constructor applied to a type you choose (Later, Many, Maybe: pick a constructor, then drop a type into it,
     to make e.g. `Later[Surface]`),
   - every function,
   - "(none)".
4. **Drop a kind on the selection.** While a kind is held over the selection, preview it with
   `POST /edit {path: "kind"}`, then accept or cancel. A refusal shows the engine's diagnostic in words.
5. **Clicking a piece shows d1's kind question for its words:** the top options with their shares, labelled as d1's
   live scores.
6. **Keyboard parity** for all of the above.

## Acceptance (write it before building; never loosen)

Headline, on at least five of Max's real long prompts in the kinds lab:
- (a) every word visibly has a kind or "(none)", and unsure words are marked and counted;
- (b) select words d1 marked unsure, drop a world type onto them, preview, accept, reload: the piece shows `by: user`
  and the correction is in the store;
- (c) the same with a constructed type, `Later[Surface]`;
- (d) a kind outside the world is refused with the engine's reason;
- (e) a rejected place still takes a dropped value (J4);
- (f) all of the above by keyboard alone.

Test with real pointer and keyboard events. Store the audit runs with the build. Have an independent sub-agent check
before reporting. Report with screenshots of (a), (b), (c) on a real prompt.

## Rules (unchanged)

- Touch only `web/` and the labs.
- Never edit the engine. If it needs a change, say exactly what.
- No deploy, no push.
- Never touch ports 8765 or 2746.
- Commit on `ui/board-4` with plain messages.
