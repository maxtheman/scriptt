# /// script
# requires-python = ">=3.14"
# dependencies = ["marimo==0.25.2"]
#
# [tool.marimo.display]
# cell_output = "below"
# ///
"""One message through the repaired reader, by its public API only.

"Redesign the mod. Then show it. Test the search too." is read against
next/world.py, validated, inspected, edited (show rebound to the original mod),
saved, reloaded and validated again. Every table below is computed by
agree.py and scriptt16.py; the cells that show an algorithm show its source
with inspect.getsource, so there is no second copy of any rule here.

d1 here is the test stand-in, answering from a fixed script, so the notebook
runs offline and the same every time. What the real d1 would answer is not
measured here (unverified).

    python -m marimo edit next/notebook.py        (from the repository; not on port 2746)
"""

import marimo

__generated_with = "0.25.2"
app = marimo.App(width="full")


@app.cell
def _():
    import inspect
    import json
    import pathlib
    import sys
    import tempfile

    import marimo as mo

    here: pathlib.Path = pathlib.Path(__file__).resolve().parent
    sys.path[:0] = [str(here), str(here.parent / "scriptt")]
    import agree
    import expected
    import scriptt16
    from test_scriptt16 import Standin
    return


@app.cell
def _():
    """THE WORLD. agree.loads builds every type of world.py. A fault refuses a declaration."""
    world_text: str = (here / "world.py").read_text()
    world: agree.World = agree.loads(world_text, here.parent)
    {
        "faults": world.faults,
        "types": {name: {"is": type(one).__name__, "kind": agree.show(agree.kind_of(one)), "definition": agree.tree(one)} for name, one in world.types.items()},
        "functions": {f.name: f"({', '.join(f'{p}: {agree.show(t)}' for p, t in f.parameters)}) -> {agree.show(f.result)}   {f.asks}" for f in world.functions.values()},
        "constructors": {c.name: c.describes for c in agree.CONSTRUCTORS.values()},
    }
    return


@app.cell
def _():
    """HOW A HOLE IS FILLED: the candidates, then d1's choice. The source as it runs."""
    mo.md("\n\n".join(f"```python\n{inspect.getsource(getattr(scriptt16, name))}```" for name in ("candidates", "solve", "made")))
    return


@app.cell
def _():
    """THE SPECIMEN AND d1's ANSWERS. The stand-in answers each question by its phrase, operation and path."""
    text: str = expected.SPECIMEN
    MOD, SEARCH = expected.MOD, expected.SEARCH
    answers: dict = expected.script(
        {"Redesign the mod.": "redesign", "Then show it.": "show", "Test the search too.": "test"},
        {("Redesign the mod.", "redesign", "surface"): MOD, ("Then show it.", "show", "subject"): expected.Ref(0), ("Test the search too.", "test", "subject"): SEARCH},
        refers={0: ("redesign", ("the mod",))})
    d1 = Standin(answers, expected.World("next"))
    reading: scriptt16.Reading = scriptt16.read(text, world, [], d1, join=False, watch=d1.watch)
    json.loads(json.dumps(scriptt16.record(reading)))["phrases"]
    return


@app.cell
def _():
    """VALIDATE AND JUDGE. Validity, completeness, availability and readiness are separate judgments, each derived."""
    def judged(one_reading: scriptt16.Reading) -> list[dict]:
        return [{"number": term.number, "phrase": one_reading.text[phrase.start:phrase.end].strip(), "brand": phrase.brand.name,
                 "operation": term.function.name if isinstance(term, scriptt16.Application) else "unresolved: " + term.reason,
                 "bindings": {path: f"{scriptt16.say(value)} : {agree.show(scriptt16.type_of(value))}" for path, value in scriptt16.bindings(term).items()} if isinstance(term, scriptt16.Application) else {},
                 "result": agree.show(term.function.result) if isinstance(term, scriptt16.Application) else None,
                 "pending": scriptt16.pending(term) if isinstance(term, scriptt16.Application) else None,
                 "complete": scriptt16.complete(term) if isinstance(term, scriptt16.Application) else None,
                 "ready": scriptt16.ready(one_reading, term) if isinstance(term, scriptt16.Application) else None}
                for phrase, term in scriptt16.obligations(one_reading)]

    {"diagnostics": scriptt16.diagnostics(reading), "obligations": judged(reading),
     "passages": [(reading.text[p.start:p.end].strip(), relation) for p, relation in scriptt16.passages(reading)]}
    return


@app.cell
def _():
    """THE DECISIONS, as recorded: by d1 or by a declared rule; what d1 read, what it was asked, what it was offered, what the bound cut, what it answered and what was chosen."""
    [{"by": one["by"], "rule": one["rule"], "operation": one["operation"], "path": one["path"], "state": one["state"], "chosen": one["chosen"] if not hasattr(one["chosen"], "__dataclass_fields__") else scriptt16.say(one["chosen"]),
      "questions": [(q["instructions"], [o["description"] for o in q.get("options", [])]) for q in one["asked"].values()],
      "offered": [scriptt16.say(term) for term in one["offered"]], "cut": [scriptt16.say(term) for term in one["cut"]], "answers": one["answers"]}
     for one in reading.decisions]
    return


@app.cell
def _():
    """INSPECT show.subject: its term, its type, the function's definition and the decision. Nothing changes and d1 is not asked."""
    show_number: int = scriptt16.obligations(reading)[1][1].number
    inspected: dict = scriptt16.inspect(reading, show_number, "subject")
    {"term": scriptt16.say(inspected["term"]), "is the result of": inspected["term"].number, "type": inspected["type"], "definition": inspected["definition"],
     "offered": [scriptt16.say(term) for term in inspected["decision"]["offered"]], "d1 chose": inspected["decision"]["answers"]}
    return


@app.cell
def _():
    """EDIT: rebind show to the original mod. The draft is a new reading; the base is untouched, so cancelling is keeping the base."""
    original_mod = next(one for one in reading.constants if scriptt16.say(one) == "'the mod'")
    draft, edit_faults = scriptt16.edit(reading, show_number, "subject", original_mod)
    {"draft diagnostics": edit_faults, "draft": judged(draft), "base still": judged(reading)[1]["bindings"],
     "a rejected edit (a hole of type Words where Subject is wanted)": scriptt16.edit(reading, show_number, "subject", scriptt16.Hole(world.types["Words"], "cleared"))[1]}
    return


@app.cell
def _():
    """SAVE, RELOAD, VALIDATE AGAIN. The record is form 5: references are {"ref": id}, decisions keep their path. Reload asks d1 nothing."""
    store: pathlib.Path = pathlib.Path(tempfile.mkdtemp()) / "store.jsonl"
    scriptt16.save(draft, store)
    calls_before: int = d1.calls
    loaded, load_faults = scriptt16.load(scriptt16.saved(store)[-1], world)
    {"load diagnostics": load_faults, "diagnostics after reload": scriptt16.diagnostics(loaded), "same meaning": scriptt16.meaning(loaded) == scriptt16.meaning(draft),
     "redesign kept once, show rebound": judged(loaded), "d1 calls during reload": d1.calls - calls_before,
     "record": json.loads(store.read_text().splitlines()[-1])["phrases"]}
    return


@app.cell
def _():
    """CHECK a reply. A reply's words are no evidence: with no artifact every obligation is UNVERIFIED, whatever d1 says the reply claims."""
    checks, verdict, judgment = scriptt16.check(loaded, "I redesigned the mod, showed it and tested the search.", [], [("evidence", lambda term, artifact: False)], d1)
    {"verdict": verdict, "checks": [(one.obligation, one.criterion, one.outcome, one.claim) for one in checks], "d1 read": judgment["state"] if judgment else None}
    return


if __name__ == "__main__":
    app.run()
