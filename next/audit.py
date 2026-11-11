"""RETIRED on 10 Nov 2026. This file listed the statuses of 53 findings of an audit of the shipped harness.

Why: its claims no longer describe the code. It cited functions that do not exist (fill, candidates in
its old sense, fits, own, values, Value), a test that does not exist (test_faults), dated itself 11 Nov,
and marked fixed several findings that the review of 10 Nov reproduced as present (F21, F23, F25, F28,
F38, F39). Keeping it beside the repaired reader would be a second, conflicting account.

Where the current answers live:
  next/expected.py        the requirement inventory, the 22 cases and their predicates (the oracle)
  next/test_scriptt16.py  runs every case, the wrong implementations and the location checks
  scriptt16.py docstring  the states and transitions of the reader

The full text is in git history: git show dcbce02:next/audit.py
"""

raise SystemExit(__doc__)
