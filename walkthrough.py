# /// script
# requires-python = ">=3.14"
# dependencies = ["marimo==0.25.2"]
# ///
"""1 message through the search of the harness, step by step. Each cell calls 1 function of harness.py and shows what it returns.

    python -m marimo edit walkthrough.py        (from the repository, with marimo 0.25 or later on Python 3.14 or later)

The notebook uses the harness of this folder (.scriptt/, after an install) with its world, its log and its d1.
With no install it uses the example in scriptt/, and the cells that ask d1 need a config.json there.
"""

import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium")


@app.cell
def _():
    import html
    import pathlib
    import sys

    import marimo as mo

    here = pathlib.Path(__file__).resolve().parent
    installed = here / ".scriptt"
    sys.path.insert(0, str(installed if installed.exists() else here / "scriptt"))
    import harness

    def table(rows: list):
        """Rows (a list of dicts) as a table."""
        return mo.ui.table(rows, selection=None, pagination=False)

    return harness, html, mo, table


@app.cell
def _(harness, mo):
    typed_in_the_app = [line for line in harness.history() if line["event"] == "UserPromptSubmit" and line["session"].startswith("app-")]
    last = typed_in_the_app[-1]["text"] if typed_in_the_app else "Oh, can you please get rid of the old cells? Then wire up 3 of them."
    message = mo.ui.text_area(value=last, rows=8, full_width=True)
    mo.vstack([mo.md("## The message\nChange it, and every cell below runs again."), message])
    return message, typed_in_the_app


@app.cell
def _(mo):
    mo.md("""
    ## The world
    `world.py` lists the functions that a message can ask for. Each function has a **domain** (its holes, each with a type),
    an **arity** (how many holes) and a **range** (the type of its result). `describe()` reads them from the file.
    """)
    return


@app.cell
def _(harness, table):
    world = harness.describe()

    def functions_of(world: dict) -> list:
        rows = []
        for name, f in world["functions"].items():
            rows.append({"function": name, "asks the reader to": f["asks"], "domain": f["holes"], "arity": len(f["holes"]), "range": f["returns"]})
        return rows

    table(functions_of(world))
    return (world,)


@app.cell
def _(world):
    world
    return


@app.cell
def _(table, world):
    def types_of(world: dict) -> list:
        rows = []
        for name, tp in world["types"].items():
            made_of = {"sum of": tp["sum"]} if "sum" in tp else {"product of": tp["fields"]}
            rows.append({"type": name, "is": tp["doc"]} | made_of)
        return rows

    table(types_of(world))
    return


@app.cell
def _(mo):
    mo.md("""
    ## Step 1: parts
    Code cuts the message into parts with 1 regular expression: a part is a sentence. Each part keeps its place in the text.
    """)
    return


@app.cell
def _(harness, message, table):
    text = harness.Asked(message.value)

    spans = harness.parts_of(text)
    table([{"part": n + 1, "start": start, "end": end, "words": text[start:end]} for n, (start, end) in enumerate(spans)])
    return (text,)


@app.cell
def _(mo):
    mo.md("""
    ## Step 2: pieces
    A piece is a place in the text where a value of a type of the world stands. `places()` finds them by code. It has
    1 case for each type constructor (sum type, union, list, product type, `int`, `Path`) and calls itself for the types inside.
    """)
    return


@app.cell
def _(harness, table, text):
    def found_by_code(text: str) -> list:
        """Each place that places() finds, for each type of a hole of the world, and for int and Path."""
        hole_types = [tp for f in harness.FUNCTIONS.values() for tp in harness.signature(f)[0].values()]
        rows = []
        for tp in [*hole_types, int, harness.pathlib.Path]:
            for start, end, type_name, value in harness.places(tp, text):
                row = {"start": start, "end": end, "words": text[start:end], "type": type_name, "value": value}
                if row not in rows:
                    rows.append(row)
        return sorted(rows, key=lambda row: row["start"])

    table(found_by_code(text))
    return


@app.cell
def _(mo):
    mo.md("""
    ## Steps 3 to 6: the search, with d1
    `read()` is the whole search. This cell gives it a d1 that also keeps each request, so that the cells below can show them.
    """)
    return


@app.cell
def _(harness, text, typed_in_the_app):
    requests = []

    def d1_and_keep(state, questions):
        answers = harness.d1(state, questions)
        requests.append({"state": state, "questions": questions, "answers": answers})
        return answers

    earlier = [line for line in typed_in_the_app if line["text"] != text]
    template, demands, parts, pieces, shares = harness.read(text, d1_and_keep, earlier)
    return demands, parts, pieces, requests, template


@app.cell
def _(mo):
    mo.md("""
    **Step 3: the choice.** For each part alone, d1 makes 1 choice among the functions of the world, `none` (something else)
    and `nothing`. `chosen()` turns d1's shares into the choice. Every part has one. A choice is a label for the sentence, and no type.
    """)
    return


@app.cell
def _(parts, table, text):
    def choices_of(parts: list) -> list:
        rows = []
        for n, part in enumerate(parts):
            by_share = sorted(part["scores"], key=part["scores"].get, reverse=True)
            rows.append({"part": n + 1, "choice": part["choice"], "share": part["scores"][part["choice"]],
                         "the next 2": [name for name in by_share if name != part["choice"]][:2], "words": text[part["start"]:part["end"]]})
        return rows

    table(choices_of(parts))
    return


@app.cell
def _(mo):
    mo.md("""
    **Steps 4 and 5: pieces fill holes.** A hole takes a piece of its type in its own part, and d1 checks it (`to`).
    Words such as "it" can stand for an earlier piece (`of`). A piece with no `to` has a type, and no call takes it.
    """)
    return


@app.cell
def _(pieces, table):
    table([{"id": piece["id"], "part": piece["part"] + 1, "words": piece["words"], "type": piece["type"], "value": piece["value"],
            "found by": piece["by"], "to": piece["to"], "of": piece["of"]} for piece in pieces])
    return


@app.cell
def _(mo):
    mo.md("""
    **Step 6: the calls.** Each ask is built as a Python call with `ast`. `...` is an open hole, and Claude is told its type.
    """)
    return


@app.cell
def _(demands, harness, table):
    calls = [{"part": demand["part"] + 1, "call": harness.call(demand, demands), "share": demand["p"]} for demand in demands]
    table(calls)
    return


@app.cell
def _(mo):
    mo.md("""
    ## The string
    A line under a sentence: it has a function. A dashed line: d1 abstains. No line: `nothing`.
    A coloured word is a piece, and the colour is its type. Every other word of the message has no type.
    """)
    return


@app.cell
def _(html, mo, parts, pieces, text, world):
    palette = ["#5b9cf5", "#e5a33a", "#b07fe0", "#4fb8b0", "#e77fb3", "#8bc34a", "#ff8a65", "#90a4ae", "#ffd54f"]
    colour_of = dict(zip([*world["types"], "int", "Path", "str", "bool"], palette * 2))
    line_under = {"none": "2px dashed #888", "nothing": "none"}

    def chip(words: str, type_name: str) -> str:
        return f'<span title="{type_name}" style="background:{colour_of.get(type_name, "#ccc")};color:#111;border-radius:3px;padding:0 3px">{html.escape(words)}</span>'

    def drawn(start: int, end: int) -> str:
        """The text from start to end, with each piece in it as a chip."""
        out, at = "", start
        for piece in pieces:
            if start <= piece["start"] < end:
                out += html.escape(text[at:piece["start"]]) + chip(piece["words"], piece["type"])
                at = piece["end"]
        return out + html.escape(text[at:end])

    def the_string() -> str:
        """The whole message: each part with its line and its choice after it."""
        out, at = "", 0
        for part in parts:
            label = " + ".join(part["demands"]) or part["choice"]
            share = part["scores"][part["choice"]]
            out += html.escape(text[at:part["start"]])
            out += f'<span style="border-bottom:{line_under.get(part["choice"], "2px solid currentColor")}">{drawn(part["start"], part["end"])}</span>'
            out += f'<code style="opacity:.6;font-size:.8em"> {label} {share:.2f}</code>'
            at = part["end"]
        return out + html.escape(text[at:])

    typed = sum(piece["end"] - piece["start"] for piece in pieces)
    with_a_function = sum(part["choice"] not in ("none", "nothing") for part in parts)
    legend = " ".join(chip(name, name) for name in colour_of if any(piece["type"] == name for piece in pieces))
    mo.Html(f'<div style="white-space:pre-wrap;line-height:2">{the_string()}</div><p>{legend}</p>'
            f"<p>{typed} of {len(text)} characters are in a typed piece. {with_a_function} of {len(parts)} parts have a function.</p>")
    return


@app.cell
def _(mo):
    mo.md("""
    ## Each request to d1
    In order. The state is what d1 saw. Each question has d1's answer beside it.
    """)
    return


@app.cell
def _(requests, table):
    def short(answer: dict):
        """What d1 answered: the option with the largest share for a choice, else the value."""
        if "probabilities" in answer:
            return max(answer["probabilities"], key=answer["probabilities"].get)
        return answer.get("value")

    def asked(requests: list) -> list:
        rows = []
        for request in requests:
            for id, question in request["questions"].items():
                answer = request["answers"][id]
                rows.append({"state": request["state"], "question": question["instructions"], "kind of answer": question["type"],
                             "answer": short(answer), "share": answer.get("p_true", answer.get("confidence"))})
        return rows

    table(asked(requests))
    return


@app.cell
def _(mo):
    mo.md("""
    ## The message as a template
    A t-string template with 1 slot for each part. Its pieces joined are the text.
    """)
    return


@app.cell
def _(table, template):
    def slots_of(template) -> list:
        rows = []
        for piece in template:
            if isinstance(piece, str):
                rows.append({"is": "text between parts", "words": piece})
            else:
                rows.append({"is": piece.expression, "words": piece.format_spec})
        return rows

    table(slots_of(template))
    return


@app.cell
def _(mo):
    mo.md("""
    ## The concepts of computer science
    Which ones the harness uses, where in `harness.py`, and how or why not.
    """)
    return


@app.cell
def _(harness, table):
    concepts = [
        ("sum type", "yes", "places", "an Enum of world.py. Code finds each member's name in the text, and d1 chooses 1 member or none"),
        ("product type", "yes", "holes", "a dataclass of world.py. Each field is a hole of its own, with a path such as only.region"),
        ("type constructor", "yes", "places", "union, list, optional, product, sum: places, holes, to_ask, leaves and expression have 1 case for each"),
        ("recursion on the structure of a type", "yes", "holes", "each of those functions calls itself for the types inside"),
        ("typed hole", "yes", "expression", "a parameter that nothing fills is ... in the call, and Claude gets its type"),
        ("brand: a tag on a text that says who produced it", "yes", "Asked", "Asked, Written, Observed. The line that receives a text gives the brand"),
        ("template", "yes", "REFERS", "each question to d1 is a t-string with slots, and the message is a Template with 1 slot for each part"),
        ("abstention", "yes", "chosen", "the option none: d1 can say that no function of the world fits"),
        ("domain and range of a function", "partly", "signature", "both are read. The range is used in 1 place: a hole can take the result of another ask of the same part"),
        ("arity and co-arity", "partly", "signature", "arity is the number of holes. Co-arity is always 1: a function has 1 result type"),
        ("composition of functions across sentences", "no", "read", "tried and removed after 2 trials: it built calls that no sentence asked for"),
        ("the type of a sentence", "no", "chosen", "a sentence gets a choice. It is no term with a type, so sentences do not compose"),
        ("subtyping, type variables, generic functions", "no", "leaves", "a piece fits a hole when the type names are equal"),
        ("higher kinds", "no", "kind", "agreed: none. kind() here is only the name of a type"),
        ("search with backtracking, unification", "no", "read", "a hole takes the first free piece of its type. When d1 rejects it, the next is not tried"),
        ("a cut of the message that follows the types", "no", "parts_of", "the cut is by sentence. No other unit was compared with it"),
    ]
    table([{"concept": concept, "used": used, "where": where, "is in harness.py": hasattr(harness, where), "how, or why not": why} for concept, used, where, why in concepts])
    return


if __name__ == "__main__":
    app.run()
