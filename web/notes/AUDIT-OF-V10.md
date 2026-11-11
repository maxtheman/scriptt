# Independent audit of the v10 board and its audit.js (10 Nov 2026, condensed)

An independent sub-agent of the previous UI session checked audit.js (49 probes) and the page (v10, commit 43dc3a5)
against the specifications. Verdicts on 103 items: 16 covered, 48 weak, 6 mismatched, 33 missing. Max's own judgement
of v10: "it doesn't feel like 43 out of 48 to me ... it feels like 28 out of 48."

## The eight worst problems
1. No probe drags. audit.js has no pointermove and no elementFromPoint; "drops" go through keyboard hold()/applyAct(),
   never through Dragology's dropTarget, so hit zones and overlap are never tested. A word equal to a world member emits
   target `wm-…` with no element of that id (the unexplained "could not compute bounds" error).
2. Self-selected populations: C12 only counts elements already `.grab`; open holes, panel chips, doc text and badges
   have no grab ("every piece draggable"). C03 checks ids that no longer exist.
3. Tautologies: C15 (/\S{8}/ matches the word "unresolved"), C31 (two attributes set to the same constant), C11 (panel
   built from transitions() compared with transitions()), C32 (static title), C44 (compares with the page's own
   rawOf()), C24 (the string "cite:").
4. Sentence does not match code: C39 "words can be dragged" calls applyAct on one span; C41 "both ways" tests one way;
   C47 "grabbing a type" calls select; C26 passes for any two nodes sharing data-type; C05 shapes not unique per type.
5. Criteria loosened between versions (git): C32 hover -> static title; C09 crumbs >= 2 -> >= 1; C22 button limit
   5 -> 7 -> 10; C42 board DOM -> WORLD data; C30 and C33 allow-lists.
6. Hooks that hide bugs: remount() "for the audit" added right after an unexplained bounds error; click() remounts and
   waits; show() sets state directly so Prev/Next are never tested; C01 sorts words before comparing so order is
   untested; C18 deletes localStorage of the browser it runs in.
7. Fixtures, not the specimen: six hand-written readings in a world with no Surface, Later or brands, while
   web/site/engine/ holds 38 real form-5 readings and a worlds file with kinds, constructors and brand chains — the
   page and the audit ignored them; the acceptance specimen never ran. The deferral of kinds and brands was justified
   with "the world has no brand declarations", which worlds.json contradicts.
8. Play invented a sequence (strips the final reading) instead of replaying recorded decisions, and disabled dragging
   while playing. Prose checks scanned only part of the page; 10–11 px text exists.

## Missing entirely
R06 zero hard-coded types (the page hard-codes str/int/Path/bool), R07/R08 Dragology use, R22 phrase tree, R44 every
piece draggable, F1e the invisible-rect dispute, "inherits from", spacing and typography; and from the contract:
kinds/constructors/notation, operation add/remove/replace, record and list field edits, reference rebind and cycle
rejection, pending/complete status, world-change impact preview, corrections invalidated with a reason, fulfillment,
none/nothing as metadata only, engine-supplied moves (the page computes its own with litTypeFor/takes/refusals),
snapshots, and the specimen run.

## Score history
CRITIQUES.md rows v03–v10 were all written in one edit at 17:37; no audit output was stored; gains came partly from
probes added in the same commit as the feature they pass and partly from loosened criteria; about nine passes are
vacuous.
