# Review notes for the next rewrite (10 Nov 2026)

This worktree, `~/Documents/scriptt-next` on branch `next/rewrite`, holds the rewrite of `next/` made on 10 Nov
between 14:15 and 16:30. `~/Documents/scriptt-release` (branch `release/hook-site`) is untouched and still holds the
code as it stood at 14:15.

## What to compare

| Commit | What it holds |
|---|---|
| `dcbce02` | `scriptt-release` exactly as it stood at 14:15, uncommitted reorganisation included. The two design reviews of 10 Nov read this code: their source hashes match `next/agree.py`, `next/scriptt16.py` and `next/test_scriptt16.py` here. |
| the next commit | The rewrite: `next/` (agree, scriptt16, world, notebook, tests, and the new turns.py, acceptance.py and golden.json), `scriptt/harness.py` (Stop hook, `/preview-prompts`) and `web/site/index.html` (one paragraph in drag mode, Many holes, Undo, prompt inspector). |

`git diff dcbce02 next/rewrite` shows the whole rewrite. Branch `next/rewrite-steps` keeps the step-by-step history in
which it was built (one merge per piece of work); it starts from the 14:15 code alone, so its commits are not ancestors
of this branch.

`.scriptt/` is git-ignored (`.git/info/exclude`). Its `harness.py` here carries the same code changes as
`scriptt/harness.py`; next imports it as `shipped`.

## How to run

```bash
cd ~/Documents/scriptt-next/next && python3.14 test_scriptt16.py
```

Runs 28 unit tests (stand-in d1), then the 7-row acceptance table C1–C7 against the real d1 on 127.0.0.1:8765.

## Known open findings (from an independent verification run, 10 Nov 16:30, against this code)

The tests pass and every acceptance row catches the engine regression it targets, but these defects remain:

1. With the real d1, a second sentence is often bound to the first sentence's value: "Test the harness. Test the
   hook." reads as `test('the harness')` twice. The `which` question shows earlier phrases and the current one without
   marking which is current. No acceptance row or golden case covers it.
2. Joining merges lists of instructions into one phrase (each new sentence is compared with everything already
   merged), so a six-sentence definition of done became one obligation.
3. The real hook never uses next: UserPromptSubmit still reads in form 3, Stop keys checks by function name and
   ignores executions; `turns.hook_block` is never called by the harness.
4. Matching executions to items is weak (a passing test command is not matched to `build('the tests')`; an edit to an
   unrelated file can make `show(...)` DONE). C6 does not guard which item an execution belongs to.
5. `Many` stops asking about earlier referents once a local value is accepted ("compare it with the page" drops "it").
6. C7 does not test the gate's open-hole rule; C6 passes on margins of 0.33–0.48 against 0.5.
7. Wordings drift: `REFERS` is outside `Prompts`; the page's default wordings differ from the engine's; the 48-pair
   join measurement is not in the repository.
8. Golden cases have no prior context; the gate compares open holes as one total across cases.
9. Notebook: the acceptance report and prompt editor wait for a button; the next-turn cell ignores edited wordings;
   the place dropdown resets after Apply.

Also still true here, from the design review and the second critique of the 14:15 code:

- `none` and `nothing` are still terminal answers: such a phrase has no term, and `check()` gives it no item.
- A function named `none` loads with no fault.
- A message that is one whole quote raises ValueError in `unfold`.
- A shared result is written into the log as a copied tree, with no identity.
- `Member.type` is not used when grounding.
- `record()` leaves out the constants that fill no hole.
- Production code grew from about 806 to about 2,070 code lines (`agree.py`, `scriptt16.py`, `turns.py`,
  `acceptance.py`; blanks, comments and docstrings not counted). The repair brief of 10 Nov
  (`~/Documents/scriptt-design-review-2026-11-10/repair-next-prompt.md`) asks for the smallest code and prefers a
  net reduction.

Spec deviations made on measurement: the `did` wording (the spec's wording scored 9/16 on the C6 judgements, the one
used scores 16/16), a sixth wording `evidence`, and new `join` and `many_is` wordings (gated on `next/golden.json`).
