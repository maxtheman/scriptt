# Board 4 brief (from the lead, 10 Nov 2026)

You build board 4 of scriptt in this worktree (`~/Documents/scriptt-ui-4`, branch `ui/board-4`, forked from board 3's
working state). Max has not yet seen one build that does the core thing. He wants it in v4.

## The core thing, in Max's words

"The rejected thing needs to have a way for the user to do something useful with it. So if I click on that, what
happens? Can I drag in a type that's useful? Can I then retag different parts of the sentence this flexibly using drag
and drop? That's the entire thing that we're trying to build."

"I want to drag arbitrary words into a span. I want to click on it and drag things from the world into the span. This
is me wanting to revisit a d1 decision. It's not anything new." And: "Or maybe a synthesized type, but either way those
should be allowable."

So: every place (an open or rejected hole, or a filled place) is a d1 decision the user can revisit. The user revisits it
by dropping a value into it. Allowed values:
- arbitrary words or a span of words from the message (adjust the span by dragging its ends, or by keyboard);
- an existing member from the world (e.g. "the page" of Surface), with no span in the text;
- a synthesized value: the result of another operation (a reference `{"ref": id}`), or a record built from its fields.

Nothing new is added to the world. The drop replaces d1's choice through the engine.

## How it must work (engine path only)

1. Clicking a rejected/open hole shows what d1 was offered and rejected (from the record's `decisions` for that
   operation and path), the place's declared type (`parameters` on the application; structure in `worlds.json`), and
   invites a drag: words, world members and synthesized values that fit.
2. While a value is held over a place, the ENGINE previews the drop (POST /edit {reading, number, path, value}; returns
   the draft and diagnostics) and the whole consequence is visible before release. A refused drop says why, from the
   engine's diagnostics. Release stages it; accept (POST /accept) saves it as the user's correction; cancel restores.
   Verified by the lead: dropping the span "there's clear UI feedback from hover states" into `follow#1.rule` as
   `{"constant": <words>, "type": "Asked", "at": [start, end]}` previews with no diagnostics.
3. Retag flexibly: drag a span or value from one place to another place; drag a function from the world onto a phrase
   (POST /edit with number null and path "function.parameter" adds an operation through the engine).
4. Visible affordances at rest, without cluttering reading: phrase boundaries, which phrases carry a request and which
   carry none, open holes with their reason in words, what can be picked up.
5. Keyboard parity for all of the above (board 3's independent audit failed keyboard use and provenance; fix both).

Engine status (commit 84518de, in the lab): /edit answers a value that does not fit with the engine's diagnostics in a
normal 200 body (e.g. `[[0, "surface", "type"]]`, `"reference"` for a missing operation); a world member with no span
(`{"constant": "the page", "type": "Surface", "at": [-1, -1]}`) previews as d1's choice replaced, and d1's original
decision stays in `decisions` so you can show both side by side. Value forms: a constant `{constant, type, at}`, a
reference `{"ref": "n"}`, a cleared hole `{"hole": T, "reason": "cleared"}`, or null to remove. Report anything else the
engine needs instead of working around it in the page.

## What Max saw in board 3 (screens in web/notes/screens/)

On his real 1,636-character prompt the text looks like one passage with "incomplete" at the top; nothing at rest shows
what is clickable; clicking the rejected hole `follow#1.rule ? rejected` did nothing visible; clicking a word
("answers") says "No meaning of its own is recorded for this word", which reads as the board having nothing to offer.
Phrase boundaries and request-free phrases are invisible; operations stack above the paragraph; pasted text from an
earlier reply reads as his words (the engine recognises a quote only when the log holds that reply). "Incomplete" means
an open place (a hole with a reason); say that in words.

## Keep from board 3

One representation (no duplicated text); every edit through the engine; progressive disclosure; stand-in vs live scores
labelled.

## Priors to read

`UI-SPEC.md`, `web/notes/FEEDBACK-SESSION.md`, `web/notes/AUDIT-OF-V10.md`, `web/site/audits/AUDIT-INDEPENDENT.txt`,
`/Users/max/Documents/scriptt-design-review-2026-11-10/ui-audit-board-current/REVIEW.md`, and the independent review of
board 3 at `~/Documents/scriptt-ui-3/web/notes/REVIEW-OF-V3.md` when it appears.

## Lab

`cd ~/Documents/scriptt-ui-4/lab && python3.14 .scriptt/harness.py serve 2791` (normally already running), page
http://127.0.0.1:2791/index.html, same origin as the engine endpoints (GET /readings, /worlds, /log; POST /edit,
/accept, /restore, /rerun; see lab/.scriptt/harness.py serve()/posted()). `lab/refresh.sh` pulls newer engine files
(restart the server after). The store holds Max's 48 real prompts read with the real d1 (40 to 13,727 characters):
test on those first, not the three-sentence specimen. /rerun calls the live d1 on 127.0.0.1:8765: fine to call, never
restart or reconfigure that service.

## Acceptance

Write it first from this brief. Headline: Max's three questions — click the rejected hole and something useful happens;
drag a useful value (words, a world member, a synthesized value) into it; retag different parts of a sentence flexibly
by drag and drop — all through the engine, by pointer and by keyboard, on at least five real long prompts. Never loosen
criteria; test with real pointer and keyboard events in the browser; store audit runs with the build; have an
independent sub-agent check before you report. Report with screenshots of exactly those three things on a real prompt.

## Rules

Touch only `web/` (and `lab/` locally). Never edit `web/site/engine/` or the engine; if it needs a change, say exactly
what. No deploy, no push. Never touch ports 8765 or 2746. Commit on `ui/board-4` with plain messages.
