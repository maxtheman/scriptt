"""RETIRED on 10 Nov 2026. This test ran the 36 events of tests/events.json through the form-3 parser of harness.py 0.1.6
(parts_of, places, read, migrate, reading) with the recorded answers of the real d1-2b, and compared with tests/recorded.json.

Why: harness.py now reads with scriptt16.read and writes form-5 lines; the functions it tested are gone.
tests/events.json and tests/recorded.json stay as data: the recorded conversation and d1-2b's answers to the old questions.

Where the current answers live:
  next/test_harness_hook.py   the hooks end to end: install, prompt, Stop with transcript evidence, send-backs, serve
  next/test_scriptt16.py      the reader against every acceptance case
  tests/live/prompt.json      1 prompt through the real d1, with every request and response

The full text is in git history: git show 8e1fe55ests/test_harness.py
"""

raise SystemExit(__doc__)
