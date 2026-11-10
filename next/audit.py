"""The 53 findings of the audit of the shipped harness (11 Nov 2026), each with where scriptt16.py stands on it.

    python3.14 next/audit.py

"fixed": the 0.1.6 code cannot have the fault, and the named function or test shows it. "partly": part of it is covered.
"present": the 0.1.6 code has the same fault. "not built": 0.1.6 has no code yet for the unit that the finding is in
(the hook, the log, corrections, old forms, find, the page, the mod), so the finding stands for the day that unit is written.
"""

FINDINGS = [
    (1, "the choice of a part falls through to nothing when no rule fires", "fixed", "choose(): the largest share wins, and none and nothing are answers of their own"),
    (2, "the life of a message ends at the last record of the session", "not built", "the log"),
    (3, "several Stops after 1 message, and only the last counts", "not built", "the hook"),
    (4, "a message is identified by its text", "partly", "Reading.id is in the record; nothing uses it yet, and the notebook still finds a message by its text"),
    (5, "the first reference word claims the open hole before d1 answers", "fixed", "no list of reference words: fill() offers d1 every candidate that fits the hole"),
    (6, "a reference is tried against the first open hole only", "fixed", "fill() goes through every open hole"),
    (7, "a reference with no piece of the hole's type is asked against any type", "fixed", "candidates(): fits() decides each candidate by type"),
    (8, "the mod invents 1 session id and keeps it", "not built", "the mod"),
    (9, "the mod takes the last line of the log as its own", "not built", "the mod"),
    (10, "the Path pattern takes abbreviations, URLs and names with a dot", "fixed", "stands(): a path is words that name something under the folder (test_values)"),
    (11, "a str that d1 reads is placed at its first place in the whole message", "fixed", "d1 points at no words: a hole takes a phrase, which has its place"),
    (12, "a correction reaches Claude once and is shown as saved for good", "not built", "corrections"),
    (13, "short sentences join the next one, also across a paragraph break", "fixed", "proposed(): no rule of length; a blank line is a start that d1 does not join"),
    (14, "what a drop records differs between the row, the page and the harness", "not built", "the mod and the page"),
    (15, "not done has 3 thresholds", "fixed", "Limits.yes is the only one, and check() gives a named State"),
    (16, "a piece rejected for 1 hole is not offered to the next hole", "fixed", "no rejection step: own() gives a value to the first hole it fits, and fill() offers every candidate"),
    (17, "a hole can be rejected and filled with the same value", "fixed", "a hole is filled once, by own() or by 1 answer of d1"),
    (18, "the world changes while a message is read", "partly", "load() makes 1 frozen World that read() uses; its hash is not in the record"),
    (19, "the last line of the log is trusted to be whole", "not built", "the log"),
    (20, "a correction written while the next message is read is never reported", "not built", "corrections"),
    (21, "a union hole keeps no type of its value", "partly", "a Value has its type expression; record() writes the hole's type and the value's words, and leaves out the value's own type"),
    (22, "a bool hole cannot be False", "present", "no bool value is found or asked for: a bool hole stays open"),
    (23, "d1 takes at most 32 options, and nothing counts them", "partly", "load() counts functions and members; fill() cuts candidates to Limits.offered; alternatives are not counted"),
    (24, "equal pieces at the same place: the type depends on the hash seed", "fixed", "values(): things in the order of world.py; every match is kept"),
    (25, "names of the world collide with names of the harness", "fixed", "load() lists a type named like a constructor and a function named none or nothing (test_faults)"),
    (26, "a value has no type in the record", "partly", "the hole's type is a tree; the value is still words"),
    (27, "a member value is found only between word boundaries", "fixed", "stands(): a member stands where its words and signs stand one after the other; no pattern"),
    (28, "the result of a function is looked up by name across the message", "partly", "a hole holds the Term itself; record() names it by its function only"),
    (29, "rules written 2 or 3 times that have drifted", "not built", "the mod and the page"),
    (30, "the status line, fault and interpreter are 1-slot states in the mod", "not built", "the mod"),
    (31, "a drop that changes 2 parts is saved as 2 lines", "not built", "the mod and the page"),
    (32, "a failed read leaves the old reading on the new message", "not built", "the mod"),
    (33, "reading() assumes the message and the part exist", "not built", "corrections"),
    (34, "a correction is not checked against the world", "not built", "corrections"),
    (35, "migrate() changes the form number and leaves form 1 keys", "not built", "old forms"),
    (36, "at names a message, with 1 second of resolution", "partly", "Reading.id; nothing uses it yet"),
    (37, "find lists only parts that have a tag", "not built", "find"),
    (38, "the template gives the same value to an abstained part and a nothing part", "fixed", "a phrase that d1 abstains on has the type _[_[_]], one that gives words has Now[Asked[Words]]"),
    (39, "a sum type of the world that refers to itself", "fixed", "load() lists it as a fault (test_faults)"),
    (40, "the local page is fetched from scriptt.ai when the folder has no copy", "not built", "the page"),
    (41, "the kind of an event is decided twice", "not built", "the hook"),
    (42, "events with no session_id share 1 session", "not built", "the hook"),
    (43, "the kind of endpoint is decided by the end of the URL", "not built", "the 0.1.6 code calls d1 through harness.put of the shipped harness"),
    (44, "d1's answers are read by key with no check of their shape", "present", "choose(), fill() and check() read probabilities and p_true directly"),
    (45, "threads write shared lists in the walkthrough and the test", "fixed", "read() asks d1 1 request after the other"),
    (46, "the hooks and the mod can both read 1 message", "not built", "the hook and the mod"),
    (47, "the Stop event shape", "not built", "the hook"),
    (48, "the atoms carry shape tags with no migration", "not built", "the mod"),
    (49, "the 60 s budget of a hook", "not built", "the hook"),
    (50, "the brand of a text is lost on load and on every string method", "fixed", "the brand is a field of a Phrase and a place of each type expression, and record() writes it"),
    (51, "a reference can bring a value from an older world", "not built", "the log: a hole takes nothing from an earlier message yet"),
    (52, "install() removes every hook entry that mentions harness.py", "not built", "the installer"),
    (53, "dead branches kept for old forms", "not built", "old forms"),
]

if __name__ == "__main__":
    for state in ("fixed", "partly", "present", "not built"):
        rows = [row for row in FINDINGS if row[2] == state]
        print(f"\n{state}: {len(rows)}")
        for number, finding, _, where in rows:
            print(f"  F{number} {finding}\n      {where}")
