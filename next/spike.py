# /// script
# requires-python = ">=3.14"
# dependencies = ["marimo==0.25.2"]
# ///
"""The 1.6 spike: harness.py 0.1.6 beside scriptt16.py, unit by unit, on 1 message, with the real d1.

    python -m marimo edit next/spike.py        (from the repository)

Each unit shows the code of both versions and what each gives for the message. The 1.6 code is next/scriptt16.py, with next/world.py
as its world and agree.py for its types. The only wording that 1.6 adds for d1 is JOIN, and it is not measured.
"""

import marimo

__generated_with = "0.25.2"
app = marimo.App(width="full")


@app.cell
def _():
    import html
    import importlib.util
    import inspect
    import json
    import pathlib
    import sys
    import tempfile
    import types

    import marimo as mo

    here = pathlib.Path(__file__).resolve().parent
    sys.path[:0] = [str(here), str(here.parent / ".scriptt")]
    import agree
    import harness
    import scriptt16

    def module_from(path: pathlib.Path, name: str):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    world = scriptt16.load(module_from(here / "world.py", "world16"))

    def table(rows: list):
        return mo.ui.table(rows, selection=None, pagination=False)

    def code_of(*functions) -> str:
        return "```python\n" + "\n\n".join(inspect.getsource(f) for f in functions) + "\n```"

    def beside(before, after):
        """2 things side by side: 0.1.6 on the left, 1.6 on the right."""
        box = lambda title, thing: mo.vstack([mo.md(f"**{title}**"), thing])
        return mo.hstack([box("0.1.6", before), box("1.6", after)], widths="equal", align="start")

    def code_beside(before: list, after: list):
        scroll = lambda functions: mo.Html(f'<div style="max-height:340px;overflow:auto;font-size:12px">{mo.md(code_of(*functions)).text}</div>')
        return beside(scroll(before), scroll(after))

    return (
        agree,
        beside,
        code_beside,
        harness,
        html,
        json,
        mo,
        pathlib,
        scriptt16,
        table,
        tempfile,
        types,
        world,
    )


@app.cell
def _(harness, mo):
    log = harness.history()
    typed_in_the_app = [line["text"] for line in log if line["event"] == "UserPromptSubmit" and line["session"].startswith("app-") and len(line["text"]) > 200]
    message = mo.ui.text_area(value=typed_in_the_app[-1], rows=8, full_width=True)
    join = mo.ui.switch(value=True, label="1.6: d1 decides whether 2 neighbouring sentences are 1 request")
    mo.vstack([mo.md("# The 1.6 spike: before and after, unit by unit\nThe message is your last long one. Edit it and click outside: both versions run again with the real d1."), message, join])
    return join, log, message


@app.cell
def _(harness, join, json, log, message, pathlib, scriptt16, tempfile, world):
    def before(text: str) -> dict:
        """0.1.6: the hook itself, with a log of its own. It gives the record that it writes and the block that Claude receives."""
        requests, real_log = [], harness.LOG

        def d1(state, questions):
            requests.append(state)
            return harness.d1(state, questions)

        with tempfile.TemporaryDirectory() as folder:
            harness.LOG = pathlib.Path(folder) / "events.jsonl"
            try:
                answer = harness.handle({"hook_event_name": "UserPromptSubmit", "session_id": "spike", "prompt": text}, d1)
                record = json.loads(harness.LOG.read_text().splitlines()[-1])
            finally:
                harness.LOG = real_log
        return {"text": text, "record": record, "block": answer["hookSpecificOutput"]["additionalContext"], "requests": len(requests)}

    def after(text: str, join: bool) -> scriptt16.Reading:
        """1.6: read(), with the replies that are in the log before this message."""
        sent = next((n for n, line in enumerate(log) if line.get("text") == text), len(log))
        replies = [line["text"] for line in log[:sent] if line["event"] == "Stop"][-8:]
        return scriptt16.read(text, world, replies, lambda state, asked: harness.put(harness.d1, state, asked), join)

    old = before(message.value)
    new = after(message.value, join.value)
    return new, old


@app.cell
def _(agree, harness, html, scriptt16):
    # Drawing, shared by both sides. Each thing of the world has 1 colour, for a value in the text and for a hole that takes it.
    palette = ["#5b9cf5", "#e5a33a", "#b07fe0", "#4fb8b0", "#e77fb3", "#8bc34a", "#ff8a65", "#9fa8da"]
    colour_of = dict(zip([*harness.describe()["types"], "int", "Path", "str", "Words", "Problem"], palette * 2))
    GRID = "display:grid;grid-template-columns:minmax(0,5fr) 200px minmax(0,5fr);gap:12px"

    def chip(words, thing: str) -> str:
        return f'<span title="{html.escape(thing)}" style="background:{colour_of.get(thing, "#bbb")};color:#111;border-radius:3px;padding:0 3px">{html.escape(str(words))}</span>'

    def open_hole(name: str, written: str, thing: str, optional: bool) -> str:
        look = "opacity:.45;" if optional else ""
        return f'{name}=<span style="{look}border:1.5px dashed {colour_of.get(thing, "#bbb")};border-radius:3px;padding:0 4px">{html.escape(written)}</span>'

    def words_with(text: str, start: int, end: int, marks: list) -> str:
        """The text from start to end, with each mark (start, end, thing) in it as a chip. Marks that overlap an earlier one are left out."""
        out, at = "", start
        for a, b, thing in sorted(marks):
            if start <= a and b <= end and a >= at:
                out += html.escape(text[at:a]) + chip(text[a:b], thing)
                at = b
        return out + html.escape(text[at:end])

    def bars(shares: dict, chosen: str, count: int = 3) -> str:
        rows = ""
        for name in sorted(shares, key=shares.get, reverse=True)[:count]:
            shade = "currentColor" if name == chosen else "rgba(128,128,128,.45)"
            rows += (f'<div style="display:flex;align-items:center;gap:6px;font:12px ui-monospace,monospace"><span style="width:62px;text-align:right">{name}</span>'
                     f'<span style="display:inline-block;height:8px;width:{shares[name] * 100:.0f}px;background:{shade}"></span>{shares[name]:.2f}</div>')
        return rows

    thing_of = lambda t: scriptt16.positions(t)[2].__name__ if not scriptt16.is_hole(scriptt16.positions(t)[2]) else "_"
    shown = agree.show
    return GRID, bars, chip, open_hole, shown, thing_of, words_with


@app.cell
def _(code_beside, harness, scriptt16):
    code_beside([harness.signature, harness.kind, harness.describe], [scriptt16.load, scriptt16.tree])
    return


@app.cell
def _(beside, harness, json, mo, scriptt16, shown, table, types, world):
    def world_before() -> list:
        return [{"function": name, "holes": f["holes"], "returns": f["returns"]} for name, f in harness.describe()["functions"].items()]

    def world_after() -> list:
        return [{"function": f.name, "holes": {path: shown(t) for path, t in f.holes.items()}, "result": shown(f.result)} for f in world.functions.values()]

    FAULTY = 'import enum\nclass Surface(enum.Enum):\n    "what the user looks at"\n    PAGE = "the page"\n\ndef show(surface: Many[Many[Surface]]) -> Surface:\n    "show something"\n\ndef build(code) -> Later[Surface]:\n    "write code"\n\ndef test(surface: Surface) -> Later:\n    "test something"\n\ndef save(surface: Sufrace) -> Surface:\n    "save something"\n'

    def faults_of(source: str) -> dict:
        """The same faulty world.py in both versions."""
        module = types.ModuleType("faulty")
        module.__file__ = "world.py"
        exec(compile(source, "world.py", "exec"), vars(module))
        try:
            old = [harness.signature(f) for f in vars(module).values() if isinstance(f, types.FunctionType)] and "no fault found"
        except Exception as fault:
            old = f"{type(fault).__name__}: {fault}"
        return {"0.1.6": old, "1.6": scriptt16.load(module).faults}

    found = faults_of(FAULTY)
    mo.vstack([
        beside(table(world_before()), table(world_after())),
        mo.md(f"**A hole as the page and the mod get it.** 0.1.6: a spelling. 1.6: `propose.proposal.solves` as a tree:\n```json\n{json.dumps(scriptt16.tree(world.functions['propose'].holes['proposal.solves']))}\n```"),
        mo.md(f"**A `world.py` with 4 faults:**\n```python\n{FAULTY}```"),
        beside(mo.md(f"`{found['0.1.6']}`"), mo.md("\n".join(f"- `{fault}`" for fault in found["1.6"]))),
    ])
    return


@app.cell
def _(code_beside, harness, scriptt16):
    code_beside([harness.parts_of], [scriptt16.places, scriptt16.written, scriptt16.proposed, scriptt16.phrases, scriptt16.unfold])
    return


@app.cell
def _(beside, new, old, scriptt16, table):
    def phrases_before(result: dict) -> list:
        text = result["text"]
        return [{"brand": "Asked", "words": text[part["start"]:part["end"]]} for part in result["record"]["parts"]]

    def phrases_after(reading) -> list:
        return [{"brand": phrase.brand.__name__, "its start is set by": phrase.starts_by or "the log", "words": reading.text[phrase.start:phrase.end].strip()} for phrase in scriptt16.innermost(reading.message)]

    beside(table(phrases_before(old)), table(phrases_after(new)))
    return


@app.cell
def _(mo):
    mo.md("""
    ## Unit 3: values
    **0.1.6** keeps the longest match at each place and stores its type as a name. **1.6** keeps every match, and each value has a type expression:
    `Now[Asked[Surface]]` is 1 `Surface` that the user named, `Now[Written[Surface]]` is one that stands in a quoted reply.
    """)
    return


@app.cell
def _(code_beside, harness, scriptt16):
    code_beside([harness.places], [scriptt16.stands, scriptt16.values])
    return


@app.cell
def _(beside, new, old, scriptt16, shown, table):
    def values_before(result: dict) -> list:
        return [{"words": piece["words"], "type": piece["type"], "value": piece["value"], "found by": piece["by"]} for piece in result["record"]["pieces"]]

    def values_after(reading) -> list:
        return [{"words": reading.text[value.start:value.end], "type": shown(value.type), "value": scriptt16.say(value, reading.text)} for value in reading.values]

    beside(table(values_before(old)), table(values_after(new)))
    return


@app.cell
def _(mo):
    mo.md("""
    ## Units 4 and 5: what a phrase asks for, and its holes
    **0.1.6**: d1 chooses a function name. `chosen()` then applies 2 thresholds, and a hole takes the first value of its type in the same sentence, or stays open.
    **1.6**: code builds 1 term for each function, with each hole filled by a value of the phrase whose type fits (`agree.match`). d1 chooses among those terms,
    `none` and `nothing`, and the largest share wins. The phrase gets the result type of its term. For each hole still open, code lists every candidate whose type fits:
    the phrase's own words, values given earlier, quoted replies, results of earlier terms. d1 chooses 1 or `none`. A brand in the hole's type keeps the wrong source out.
    """)
    return


@app.cell
def _(code_beside, harness, scriptt16):
    code_beside([harness.chosen, harness.read], [scriptt16.fits, scriptt16.candidate, scriptt16.choose, scriptt16.candidates, scriptt16.fill, scriptt16.read])
    return


@app.cell
def _(
    GRID,
    agree,
    bars,
    beside,
    chip,
    mo,
    new,
    old,
    open_hole,
    scriptt16,
    shown,
    thing_of,
    words_with,
):
    def drawn_before(result: dict) -> str:
        text, record, rows = result["text"], result["record"], ""
        marks = [(piece["start"], piece["end"], piece["type"]) for piece in record["pieces"]]
        for n, part in enumerate(record["parts"]):
            calls = ""
            for demand in record["demands"]:
                if demand["part"] == n:
                    holes = ", ".join(f'{path}={chip(hole["value"], hole["type"].replace(" | None", ""))}' if hole["value"] else open_hole(path, hole["type"], hole["type"].replace(" | None", ""), "None" in hole["type"]) for path, hole in demand["parameters"].items())
                    calls += f'<div style="font:13px ui-monospace,monospace"><b>{demand["function"]}</b>({holes})</div>'
            faded = "opacity:.5;" if part["choice"] == "nothing" else ""
            rows += f'<div style="{GRID};padding:6px 0;border-top:1px solid rgba(128,128,128,.25);{faded}"><div>{words_with(text, part["start"], part["end"], marks)}</div><div>{bars(part["scores"], part["choice"])}</div><div>{calls}</div></div>'
        return rows

    def drawn_after(reading) -> str:
        text = reading.text
        marks = [(value.start, value.end, thing_of(value.type)) for value in reading.values]

        def row(phrase) -> str:
            if phrase.inside:
                return "".join(phrase.inside)
            words = words_with(text, phrase.start, phrase.end, marks)
            type_shown = f'<code style="font-size:12px">{shown(phrase.type)}</code>'
            if phrase.brand is agree.Written:
                return f'<div style="margin:4px 0;padding:4px 8px;border-left:4px solid rgba(128,128,128,.6);background:rgba(128,128,128,.12)"><div style="{GRID}"><div style="opacity:.75">{words}</div><div>{type_shown}</div><div></div></div></div>'
            if not phrase.choice:
                return f"<div>{words}</div>"
            term = ""
            if phrase.term:
                holes = []
                for path, filled in phrase.term.holes.items():
                    said = f' <span style="opacity:.55;font-size:.8em">{type(filled.value).__name__.lower()} {filled.choice.shares[filled.choice.best]:.2f}</span>' if filled.value is not None and filled.choice else ""
                    holes.append(f"{path}={chip(scriptt16.say(filled.value, text)[:60], thing_of(filled.type))}{said}" if filled.value is not None
                                 else open_hole(path, shown(filled.type), thing_of(filled.type), scriptt16.positions(filled.type)[0] is agree.Maybe))
                term = f'<b>{phrase.term.function.name}</b>({", ".join(holes)})'
            faded = "opacity:.5;" if phrase.choice.best == "nothing" else ""
            return (f'<div style="{GRID};padding:6px 0;border-top:1px solid rgba(128,128,128,.25);{faded}"><div>{words}</div>'
                    f'<div>{type_shown}{bars(phrase.choice.shares, phrase.choice.best, 2)}</div><div style="font:13px ui-monospace,monospace">{term}</div></div>')

        return scriptt16.fold(row, reading.message)

    beside(mo.Html(f'<div style="line-height:1.6;font-size:14px">{drawn_before(old)}</div>'), mo.Html(f'<div style="line-height:1.6;font-size:14px">{drawn_after(new)}</div>'))
    return


@app.cell
def _(mo, new, table):
    def asked_of_d1(reading) -> list:
        rows = []
        for request in reading.requests:
            for key, question in request["asked"].items():
                answer = request["answers"][key]
                shares = answer.get("probabilities")
                rows.append({"d1 saw": request["state"], "question": question["instructions"], "options": [option["description"][:60] for option in question.get("options", [])],
                             "answer": max(shares, key=shares.get) if shares else answer.get("value"), "share": round(max(shares.values()) if shares else answer["p_true"], 2)})
        return rows

    mo.vstack([mo.md("**Each request of 1.6 to d1**: what it saw, the question, the options, the answer. The options of a hole are numbered: 0 is the first candidate."), table(asked_of_d1(new))])
    return


@app.cell
def _(code_beside, harness, scriptt16):
    code_beside([harness.handle], [scriptt16.record, scriptt16.Phrase, scriptt16.Term, scriptt16.Filled, scriptt16.Value, scriptt16.Choice])
    return


@app.cell
def _(beside, json, mo, new, old, scriptt16):
    def record_before(result: dict) -> dict:
        """The first part that asks, with its demands."""
        record = result["record"]
        n = next((n for n, part in enumerate(record["parts"]) if part["demands"]), 0)
        return {"parts": [record["parts"][n] | {"scores": "..."}], "demands": [demand for demand in record["demands"] if demand["part"] == n]}

    def record_after(reading) -> dict:
        """The first phrase that asks."""
        def first(phrase):
            if "inside" in phrase:
                return next((found for found in map(first, phrase["inside"]) if found), None)
            return phrase | {"shares": "..."} if "term" in phrase else None

        return first(scriptt16.record(reading)["phrases"]) or {}

    as_json = lambda data: mo.md(f"```json\n{json.dumps(data, indent=1)}\n```")
    beside(as_json(record_before(old)), as_json(record_after(new)))
    return


@app.cell
def _(beside, code_beside, mo, new, old, scriptt16):
    mo.vstack([code_beside([], [scriptt16.block, scriptt16.written_out, scriptt16.say]),
               beside(mo.md(f"```\n{old['block']}\n```"), mo.md(f"```\n{scriptt16.block(new)}\n```"))])
    return


@app.cell
def _(harness, pathlib, scriptt16, table):
    def wordings() -> list:
        """Each wording that is written by hand, from the source of harness.py, and which version sends it to d1 for a message."""
        source = pathlib.Path(harness.__file__).read_text().splitlines()
        used_by_1_6 = {"WHAT", "ELSE", "NAMES"}
        rows = []
        for name in ("WHAT", "ELSE", "NAMES", "SAYS", "WHICH", "IS", "WITH", "REFERS", "REFER", "DID", "ANSWERED"):
            line = next(line for line in source if line.startswith(name + " = "))
            rows.append({"wording": line.split(" = ", 1)[1].split("  #")[0][:150], "0.1.6": "yes", "1.6": "yes" if name in used_by_1_6 else "no", "measured": "yes"})
        rows.append({"wording": '"the text names none of these"', "0.1.6": "yes", "1.6": "yes", "measured": "yes"})
        rows.append({"wording": repr(scriptt16.JOIN), "0.1.6": "no", "1.6": "yes", "measured": "no"})
        return rows

    table(wordings())
    return


@app.cell
def _(agree, mo, new, old, scriptt16, table):
    def counts(result: dict, reading) -> list:
        phrases = scriptt16.innermost(reading.message)
        record = result["record"]
        asking = [phrase for phrase in phrases if phrase.term]
        must_old = [hole for demand in record["demands"] for hole in demand["parameters"].values() if "None" not in hole["type"]]
        must_new = [filled for phrase in asking for filled in phrase.term.holes.values() if scriptt16.positions(filled.type)[0] is not agree.Maybe]
        again = scriptt16.fold(lambda phrase: "".join(phrase.inside) or reading.text[phrase.start:phrase.end], reading.message) == reading.text
        return [
            {"": "phrases", "0.1.6": len(record["parts"]), "1.6": len(phrases)},
            {"": "with a type expression", "0.1.6": 0, "1.6": sum(phrase.type is not None for phrase in phrases)},
            {"": "that ask for a function", "0.1.6": sum(bool(part["demands"]) for part in record["parts"]), "1.6": len(asking)},
            {"": "where d1 abstains", "0.1.6": sum(part["hole"] is not None for part in record["parts"]), "1.6": sum(bool(phrase.choice) and phrase.choice.best == "none" for phrase in phrases)},
            {"": "quotes of earlier replies, kept out of the asks", "0.1.6": 0, "1.6": sum(phrase.brand is agree.Written for phrase in phrases)},
            {"": "holes that must be filled", "0.1.6": len(must_old), "1.6": len(must_new)},
            {"": "of those, filled", "0.1.6": sum(hole["value"] is not None for hole in must_old), "1.6": sum(filled.value is not None for filled in must_new)},
            {"": "requests to d1", "0.1.6": result["requests"], "1.6": len(reading.requests)},
            {"": "the phrases folded into text are the message", "0.1.6": "".join(piece if isinstance(piece, str) else piece["words"] for piece in record["template"]) == result["text"], "1.6": again},
        ]

    mo.vstack([mo.md("## Side by side, in numbers"), table(counts(old, new))])
    return


if __name__ == "__main__":
    app.run()
