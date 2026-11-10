# /// script
# requires-python = ">=3.14"
# dependencies = ["marimo==0.25.2"]
#
# [tool.marimo.display]
# cell_output = "below"
# ///
"""A message comes in. What happens next?

One message goes through four parts, from top to bottom:

1. The closed type system that world.py defines.
2. Lexical grounding: the message becomes phrases and typed constants.
3. Type-directed synthesis: the terms that fill each hole, and the choice of d1.
4. Interpretation: the phrases fold into the drawing, the lines for Claude, the log and the reply check.

Each cell that shows a function calls it from next/agree.py, next/scriptt16.py or next/turns.py,
and shows its source as the module has it, read with inspect.getsource. The
notebook holds no copy of the engine, so it always runs the real one.

    python -m marimo edit next/notebook.py        (from the repository)
"""

import marimo

__generated_with = "0.25.2"
app = marimo.App(width="full")


@app.cell
def _():
    import dataclasses
    import difflib
    import html
    import inspect
    import json
    import pathlib
    import sys
    import types

    import marimo as mo

    here: pathlib.Path = pathlib.Path(__file__).resolve().parent
    sys.path[:0] = [str(here), str(here.parent / ".scriptt")]
    import agree
    import harness
    import scriptt16
    import turns
    from agree import CONSTRUCTORS, LATER, MANY, MAYBE, Applied, Arrow, Base, Brand, Constructor, Function, Kind, Member, Product, Star, Sum, Type, World, duplicates, is_subtype, kind_of, show, single_use
    from scriptt16 import (
        Application, Checked, Constant, Empty, Environment, Gate, Hole, Limits, Phrase, Reading, Record, Search, Several, Term,
        derivations, fills, fold, grounded, innermost, places, proposed, say, solve, type_of, written,
    )
    return


@app.cell
def _():
    def source_view(*functions: object) -> mo.Html:
        """Shows the source of engine functions, read-only and folded, as the modules have it.

        Args:
            functions: The functions or methods to show.

        Returns:
            One closed accordion with a read-only code view of each function.
        """
        return mo.accordion({f"source: {function.__module__}.{function.__qualname__}": mo.ui.code_editor(inspect.getsource(function), language="python", disabled=True) for function in functions})
    return


@app.cell
def _():
    """The world of the folder. Edit it: every cell below runs again."""
    world_source = mo.ui.code_editor(value=(here / "world.py").read_text(), language="python", min_height=220)
    world_source
    return


@app.cell
def _():
    """PART 1: THE CLOSED TYPE SYSTEM. agree.load builds every type of world.py and lists each fault with its line. The search refuses a world with a fault."""
    _module = types.ModuleType("world")
    _module.__file__ = str(here / "world.py")
    exec(compile(world_source.value, "world.py", "exec"), vars(_module))
    world: World = agree.load(_module)
    mo.vstack([source_view(agree.load, scriptt16.ungrounded), {"faults": world.faults + scriptt16.ungrounded(world)} | {name: type(one).__name__ for name, one in world.types.items()}])
    return


@app.cell
def _():
    """FUNCTION. Each function of the world has typed parameters and a typed result."""
    {function.name: f"({', '.join(f'{name}: {show(parameter)}' for name, parameter in function.parameters)}) -> {show(function.result)}" for function in world.functions.values()}
    return


@app.cell
def _():
    """RULES OF A WORLD. Two functions may share parameter types and a result type (increase and decrease), and a type may protect one boundary (Proposal on propose). So duplicates and single_use only ask a question of the person who reviews world.py: agree.load lists their findings in world.warnings, and the search runs all the same."""
    mo.vstack([source_view(duplicates, single_use), {"warnings": world.warnings, "faults": world.faults}])
    return


@app.cell
def _():
    """KIND. The type of a type. A type has kind *. A type constructor has kind * -> *. kind_of refuses a constructor applied to the wrong kind."""
    surface: Sum = world.types["Surface"]


    def kind_or_refusal(expression: Type | Constructor) -> str:
        """Returns the kind of an expression as text, or the reason that kind_of refuses it."""
        try:
            return show(kind_of(expression))
        except TypeError as refusal:
            return str(refusal)


    mo.vstack([source_view(kind_of), {
        "Surface": kind_or_refusal(surface),
        "Many": kind_or_refusal(MANY),
        "Many[Surface]": kind_or_refusal(Applied(MANY, surface)),
        "Many[Maybe]": kind_or_refusal(Applied(MANY, MAYBE)),
    }])
    return


@app.cell
def _():
    """BRAND. A typing.NewType in world.py: a new nominal type over an existing type. is_subtype makes a brand a subtype of the type it wraps, and keeps two brands apart."""
    brands: dict[str, Brand] = {name: one for name, one in world.types.items() if isinstance(one, Brand)}

    mo.vstack([source_view(is_subtype), {name: show(brand.of) for name, brand in brands.items()}, {
        "Asked is a subtype of Words": is_subtype(brands["Asked"], brands["Words"]),
        "Written is a subtype of Words": is_subtype(brands["Written"], brands["Words"]),
        "Written is a subtype of Asked": is_subtype(brands["Written"], brands["Asked"]),
    }])
    return


@app.cell
def _():
    """SUM TYPE. One of several alternatives. An Enum is a sum of members with no fields. A union is a sum of types."""
    subject: Sum = world.types["Subject"]
    [member.words for member in surface.alternatives], [show(alternative) for alternative in subject.alternatives], is_subtype(surface, subject), is_subtype(brands["Words"], subject)
    return


@app.cell
def _():
    """PRODUCT TYPE. One value for each field. A field can have any type of the world, so products nest. This lists the product types of the world above."""
    {name: {field: show(field_type) for field, field_type in one.fields} for name, one in world.types.items() if isinstance(one, Product)}
    return


@app.cell
def _():
    """TYPE CONSTRUCTOR. Takes a type and gives a type. Each has its own rule in the search (part 3)."""
    {constructor.name: (show(constructor.kind), constructor.describes) for constructor in CONSTRUCTORS.values()}, [show(Applied(constructor, surface)) for constructor in CONSTRUCTORS.values()]
    return


@app.cell
def _():
    """PART 2: LEXICAL GROUNDING. One message, and one earlier reply that the log holds. Edit either: every cell below runs again."""
    earlier_reply = mo.ui.text_area(value="Not verified. The row draws in the code font, and the jiggle is a slant.", rows=2, full_width=True, label="An earlier reply.")
    message = mo.ui.text_area(value='Redesign the mod. Then show me the mod, redesigned. Test the search too. "The row draws in the code font, and the jiggle is a slant." What did you mean by that?', rows=4, full_width=True, label="A message comes in.")
    mo.vstack([earlier_reply, message])
    return


@app.cell
def _():
    text: str = message.value
    replies: list[str] = [earlier_reply.value]
    limits: Limits = Limits()

    mo.vstack([source_view(places), [text[start:end] for start, end in places(text)]])
    return


@app.cell
def _():
    """Which words did an earlier reply already have? Those words get the brand Written."""

    quotes: list[tuple[int, int]] = written(text, replies, limits.run)
    mo.vstack([source_view(written), [text[start:end] for start, end in quotes]])
    return


@app.cell
def _():
    """Where can a phrase start?"""

    starts: dict[int, str] = proposed(text)
    mo.vstack([source_view(proposed), [(rule, text[start:start + 30]) for start, rule in sorted(starts.items())]])
    return


@app.cell
def _():
    """UNFOLD and FUNCTOR. unfold grows the phrases with one function. It uses Phrase.map, which applies a function inside a phrase and keeps the phrase. As in read, d1 decides with the join wording whether a sentence only adds detail to the one before it; then the two are one phrase."""


    def model(state: str, questions: dict[str, dict]) -> dict[str, dict]:
        """Sends questions about one state to the real d1."""
        return harness.put(harness.d1, state, questions)


    unfolded: Phrase = scriptt16.phrases(text, replies[-limits.replies:], world, scriptt16.same_request_of(model, scriptt16.Prompts()), limits)
    phrases: list[Phrase] = innermost(unfolded)
    mo.vstack([source_view(scriptt16.unfold, Phrase.map, scriptt16.phrases, scriptt16.same_request_of), [(phrase.brand.name, phrase.starts_by, text[phrase.start:phrase.end].strip()) for phrase in phrases]])
    return


@app.cell
def _():
    """GROUNDING. stands turns a span of text into a constant term with a type of the world."""

    constants: list[Constant] = grounded(text, world)
    mo.vstack([source_view(scriptt16.stands, grounded), [(text[constant.start:constant.end], show(constant.type)) for constant in constants]])
    return


@app.cell
def _():
    """PART 3: TYPE-DIRECTED SYNTHESIS. Take one phrase of the user."""
    _asked = {f"{index}: {text[phrase.start:phrase.end].strip()[:90]}": index for index, phrase in enumerate(phrases) if phrase.brand == world.types["Asked"]}
    chosen = mo.ui.dropdown(_asked, value=list(_asked)[min(2, len(_asked) - 1)], full_width=True, label="A phrase of the user.")
    chosen
    return


@app.cell
def _():
    """The environment of the phrase: the terms that can fill its holes. Local terms come from the phrase. Context terms come from before it.

    This is the environment that read itself builds and hands to choose. The cell starts the turn with turns.start_turn, which calls scriptt16.read; it records the argument of each call of scriptt16.choose while read runs, and builds no environment of its own. It reads as the hook reads: join on, so d1 decides whether neighbouring sentences are one phrase, with the same join decision as part 2."""
    _environments: dict[int, Environment] = {}
    _choose = scriptt16.choose

    def _recording(phrase: Phrase, environment: Environment, search: Search) -> Phrase:
        _environments[phrase.start] = environment
        return _choose(phrase, environment, search)

    scriptt16.choose = _recording
    try:
        read_trace: turns.Trace = turns.start_turn(text, world, replies, model, limits=limits)
    finally:
        scriptt16.choose = _choose
    reading: Reading = read_trace.reading
    chosen_phrase: Phrase = innermost(reading.message)[chosen.value]
    environment: Environment = _environments[chosen_phrase.start]
    mo.vstack([source_view(turns.start_turn, scriptt16.read), {"local": [f"{say(term, text)} : {show(type_of(term))}" for term in environment.local], "context": [f"{say(term, text)} : {show(type_of(term))}" for term in environment.context]}])
    return


@app.cell
def _():
    """d1 chooses the function that the phrase asks for. Each parameter of that function is now a hole with a type."""
    largest_shares: list[tuple[str, float]] = sorted(chosen_phrase.choice.shares.items(), key=lambda option: -option[1])[:4]
    asked_function: Function | None = world.functions.get(chosen_phrase.choice.best)
    mo.vstack([source_view(scriptt16.choose), (largest_shares, {name: show(parameter) for name, parameter in asked_function.parameters} if asked_function else "no function")])
    return


@app.cell
def _():
    """HOLE. derivations lists every well-typed term for a hole. The original value and a version of it that an earlier phrase made are both in the list: d1 chooses by the words of the phrase.

    This calls derivations on the type of each parameter, as it is. For a sum of types, such as Subject, the list has the terms of every alternative: solve decomposes the sum into one alternative, which d1 chooses, only when no term fits the whole sum. For Maybe[T], Many[T] and a product type, solve applies its own rule first and calls derivations on the inner types, so the list for the parameter type itself can be empty while solve still finds a term (explain(subject: Maybe[Words]) is one)."""
    mo.vstack([source_view(derivations), {name: [f"{say(term, text)} : {show(type_of(term))}" for term in derivations(parameter, environment, world, limits.depth, asked_function)]
     for name, parameter in (asked_function.parameters if asked_function else ())}])
    return


@app.cell
def _():
    """solve applies the rule for the type of the hole and asks d1 when several terms fit. This is the term of the phrase, and its type."""
    mo.vstack([source_view(solve, scriptt16.applied), (say(chosen_phrase.term, text), show(type_of(chosen_phrase.term))) if chosen_phrase.term else chosen_phrase.choice.best])
    return


@app.cell
def _():
    """Every question that the search sent to d1 for the whole message: what d1 read, the question, the options, and the option with the largest share."""
    [(request["state"][:60], question["instructions"], [option["description"][:40] for option in question.get("options", [])],
      max(request["answers"][key]["probabilities"], key=request["answers"][key]["probabilities"].get) if "probabilities" in request["answers"][key] else request["answers"][key]["p_true"])
     for request in reading.requests for key, question in request["asked"].items()]
    return


@app.cell
def _():
    """PART 4: INTERPRETATION. FOLD collapses the phrases with one function. Each output below is one fold of the same reading."""

    mo.vstack([source_view(fold),     fold(lambda phrase: "".join(phrase.inside) or text[phrase.start:phrase.end], reading.message) == text])
    return


@app.cell
def _():
    """THE TRACE OF THE TURN. turns.start_turn gave one Trace: context[n], the wordings, the hash of the world, the reading, the corrections, the executions and context[n+1]. The notebook holds it in a state, so that a correction below, an Undo or an edited wording replaces it, and every view of it runs again."""
    get_trace, set_trace = mo.state(read_trace)
    get_binding_note, set_binding_note = mo.state("")
    return


@app.cell
def _():
    trace: turns.Trace = get_trace()
    current: Reading = trace.reading
    mo.md(f"Turn {trace.turn} · world `{trace.world_hash}` · wordings `{scriptt16.prompts_hash(trace.prompts)}` · {len(trace.corrections)} correction(s) · {len(current.requests)} request(s) to d1")
    return


@app.cell
def _():
    COLOURS: list[str] = ["#5b9cf5", "#e5a33a", "#b07fe0", "#4fb8b0", "#e77fb3", "#8bc34a", "#ff8a65", "#9fa8da"]


    def drawn(reading: Reading, context: tuple[turns.Entity, ...] = ()) -> mo.Html:
        """Folds a reading into one paragraph: the message as it was written, with its terms marked in place.

        Args:
            reading: The reading.
            context: The entities of earlier turns that the reading could name.

        Returns:
            The message as running text. A phrase that asks starts with its number,
            the same number as in the lines for Claude, and its function. A constant
            that fills a hole is marked once, where it stands, with the hole and the
            type. A constant that fills no hole is underlined, with its type on
            hover. A quote of an earlier reply is grey and has its number too.
            After the phrase come only the holes that the phrase itself does not
            fill: one that a term from before the phrase fills, with the number of
            that phrase (or of the quote, or the identifier of the entity of an
            earlier turn), and one that is open, with the reason that it is open.
            A type has the colour of the type of the world inside it: Later[Surface]
            and Observed[Surface] have the colour of Surface.
        """
        text = reading.text
        names = list(world.types)
        phrases_in_order = innermost(reading.message)
        number = lambda term: next((chr(0x278A + index) for index, phrase in enumerate(phrases_in_order) if phrase.term is term and isinstance(term, Application)), "")
        quotes = [(phrase.start, phrase.end, chr(0x278A + index)) for index, phrase in enumerate(phrases_in_order) if phrase.brand and phrase.brand.name == "Written"]
        quoted = lambda term: next((mark for start, end, mark in quotes if isinstance(term, Constant) and term.origin == "Written" and start <= term.start < end), "")
        from_before = lambda term: next((entity for entity in context if entity.term == term), None)

        def colour(expression: Type) -> str:
            match expression:
                case Applied(argument=inner):
                    return colour(inner)
                case Brand(of=inner) if world.types.get(expression.name) != expression:
                    return colour(inner)
            return COLOURS[names.index(expression.name) % len(COLOURS)] if getattr(expression, "name", "") in names else "#999"

        def filled(words: str, hole: str, expression: Type) -> str:
            label = f"{hole} ∶ {show(expression)}" if hole else show(expression)
            return f'<span style="background:{colour(expression)};color:#111;border-radius:4px;padding:1px 5px">{html.escape(words)} <small>: {html.escape(label)}</small></span>'

        def unfilled(words: str, expression: Type) -> str:
            return f'<span title="{html.escape(show(expression))}" style="border-bottom:1.5px dotted {colour(expression)}">{html.escape(words)}</span>'

        def socket(content: str, expression: Type, is_open: bool, title: str = "") -> str:
            border = "dashed" if is_open else "solid"
            return f' <span title="{html.escape(title)}" style="border:1.5px {border} {colour(expression)};border-radius:4px;padding:1px 5px"><small>{content}</small></span>'

        def leaves(term: Term, path: str) -> list[tuple[str, Term]]:
            """Returns each part of a term with the path of its hole. An earlier term and a new application are parts of their own."""
            match term:
                case Record(fields=fields):
                    return [found for name, field in fields.items() for found in leaves(field, f"{path}.{name}")]
                case Several(terms=terms):
                    return [found for one in terms for found in leaves(one, path)]
                case Application(arguments=arguments) if not number(term) and not from_before(term):
                    return [(path, term)] + [found for name, argument in arguments.items() for found in leaves(argument, f"{path}.{name}")]
            return [(path, term)]

        def phrase_drawn(phrase: Phrase) -> str:
            words = text[phrase.start:phrase.end]
            if phrase.inside:
                return "".join(phrase.inside)
            if phrase.brand and phrase.brand.name == "Written":
                mark = next(mark for start, _, mark in quotes if start == phrase.start)
                lead = words[:len(words) - len(words.lstrip())]
                return f'{html.escape(lead)}<span style="background:rgba(128,128,128,.18);font-style:italic"><b style="font-style:normal">{mark}</b> {html.escape(words.lstrip())}</span>'
            if not isinstance(phrase.term, Application):
                return f'<span style="opacity:.55">{html.escape(words)}</span>'
            parts = [found for name, argument in phrase.term.arguments.items() for found in leaves(argument, name)]
            whole = (phrase.start, phrase.end)
            here = {(part.start, part.end): path for path, part in parts if isinstance(part, Constant) and not from_before(part) and phrase.start <= part.start and (part.start, part.end) != whole}
            share = phrase.choice.shares[phrase.choice.best]
            title = html.escape(f"{share:.2f} ➔ {show(type_of(phrase.term))}")
            lead = words[:len(words) - len(words.lstrip())]
            drawn_words = html.escape(lead) + f'<b title="{title}">{number(phrase.term)} {phrase.term.function.name}</b> <small>➔ {html.escape(show(type_of(phrase.term)))}</small> '
            position = phrase.start + len(lead)
            for constant in reading.constants:
                if position <= constant.start and constant.end <= phrase.end:
                    hole = here.get((constant.start, constant.end))
                    spoken = text[constant.start:constant.end]
                    drawn_words += html.escape(text[position:constant.start]) + (filled(spoken, hole, constant.type) if hole else unfilled(spoken, constant.type))
                    position = constant.end
            drawn_words += html.escape(text[position:phrase.end].rstrip())
            for path, part in parts:
                entity = from_before(part)
                match part:
                    case _ if entity:
                        drawn_words += socket(f"{path} ↩ {entity.id} {html.escape(say(part, entity.text))}", type_of(part), False, "from an earlier turn")
                    case Hole(type=expression, reason=reason):
                        drawn_words += socket(f"◻ {path}: {html.escape(show(expression))} · {reason}", expression, True, "open hole: " + reason)
                    case Application() if number(part):
                        drawn_words += socket(f"{path} ↩ {number(part)} {html.escape(say(part, text))}", type_of(part), False)
                    case Application(function=function):
                        drawn_words += socket(f"{path} = {function.name}(…)", type_of(part), False)
                    case Constant() if quoted(part):
                        drawn_words += socket(f"{path} ↩ {quoted(part)}", part.type, False, "the quote of an earlier reply")
                    case Constant(start=start) if start < phrase.start:
                        drawn_words += socket(f"{path} ↩ {html.escape(say(part, text))}", part.type, False)
                    case Constant(start=start, end=end) if (start, end) == whole:
                        drawn_words += socket(f"{path} = these words", part.type, False)
            return drawn_words + html.escape(text[phrase.start + len(words.rstrip()):phrase.end])

        return mo.Html(f'<div style="line-height:2.3;white-space:pre-wrap">{scriptt16.fold(phrase_drawn, reading.message)}</div>')
    return


@app.cell
def _():
    """THE READING, DRAWN. The message in reading order, with the corrected reading of the trace: each phrase that asks, its function and the type it returns, the holes that the phrase fills in place, the holes that a term from before fills, and each open hole with its reason."""
    drawn(current, trace.context_in)
    return


@app.cell
def _():
    """BINDING. Choose a place, the function of a phrase or one of its holes, and what stands there: a candidate that turns.candidates offers, or a value you type (a candidate the search did not offer). Apply calls turns.correct, with d1 to fill the holes of a new function; Undo calls turns.undo. The drawing above, the lines for Claude and the corrections below follow at once."""

    def places_in(term: Term, path: str) -> list[tuple[str, Term]]:
        """Returns each named place inside a term, with what stands there. A Many place is one place."""
        match term:
            case Application(arguments=inner) | Record(fields=inner):
                return [found for name, part in inner.items() for found in [(f"{path}.{name}" if path else name, part), *places_in(part, f"{path}.{name}" if path else name)]]
        return []

    def place_label(number: int, path: str | None, part: Term | None, phrase: Phrase) -> str:
        if path is None:
            return f"{number}. function: {phrase.choice.best if phrase.choice else 'none'}"
        state = f"◻ open ({part.reason})" if isinstance(part, Hole) else say(part, current.text)[:60]
        return f"{number}. {phrase.term.function.name} · {path} = {state}"

    _places: dict[str, tuple[int, str | None]] = {}
    for _number, _phrase in enumerate(innermost(current.message), 1):
        if _phrase.brand != world.types["Asked"] or not _phrase.choice:
            continue
        _places[place_label(_number, None, None, _phrase)] = (_number, None)
        for _path, _part in (places_in(_phrase.term, "") if _phrase.term else []):
            _places[place_label(_number, _path, _part, _phrase)] = (_number, _path)
    _first_open = next((label for label in _places if "◻ open" in label), next(iter(_places)))
    place_choice = mo.ui.dropdown(_places, value=_first_open, full_width=True, label="A place: the function of a phrase, or a hole.")
    place_choice
    return


@app.cell
def _():
    _number, _path = place_choice.value
    _offered: list[str] = turns.candidates(trace, _number, _path)
    _goal = turns.place(trace, _number, _path)[1] if _path else None
    _many = isinstance(_goal, Applied) and _goal.constructor == MANY
    _standing = say(turns.place(trace, _number, _path)[0], current.text) if _path else (turns.phrase_of(trace, _number).choice.best if turns.phrase_of(trace, _number).choice else None)
    if _many:
        candidate_choice = mo.ui.multiselect(_offered, label=f"Candidates for {show(_goal)} (choose any)", full_width=True)
    else:
        candidate_choice = mo.ui.dropdown(_offered, value=_standing if _standing in _offered else (_offered[0] if _offered else None), label="A candidate" + (f" for {show(_goal)}" if _goal else ": a function of the world"), full_width=True)
    typed_value = mo.ui.text(label="or type a value that the search did not offer", full_width=True)

    def _apply(_: object) -> None:
        typed = typed_value.value.strip()
        choice = typed if typed else (list(candidate_choice.value) if _many else candidate_choice.value)
        if not _many and choice == _standing:
            set_binding_note(f"{choice} already stands there: choose another candidate, or type a value.")
            return
        try:
            set_trace(turns.correct(get_trace(), _number, _path, choice, model))
            set_binding_note("")
        except (ValueError, TypeError) as refusal:
            set_binding_note(str(refusal))

    def _undo(_: object) -> None:
        try:
            set_trace(turns.undo(get_trace()))
            set_binding_note("")
        except ValueError as refusal:
            set_binding_note(str(refusal))

    apply_button = mo.ui.button(label="Apply", kind="success", on_click=_apply)
    undo_button = mo.ui.button(label="Undo", on_click=_undo)
    mo.vstack([source_view(turns.candidates, turns.correct, turns.undo), candidate_choice, typed_value, mo.hstack([apply_button, undo_button], justify="start")])
    return


@app.cell
def _():
    """The lines that Claude receives: turns.block_of the trace, which is scriptt16.block of the corrected reading. Below them, each correction of the trace."""
    _note = get_binding_note()
    _rows = [{"kind": correction.kind, "phrase": correction.phrase, "path": correction.path,
              "before": (correction.before or {}).get("reads") or (correction.before or {}).get("choice") or ("wordings" if correction.kind == "prompt_edited" else ""),
              "after": (correction.after or {}).get("reads") or (correction.after or {}).get("choice") or ("wordings" if correction.kind == "prompt_edited" else ""),
              "at": correction.at} for correction in trace.corrections]
    mo.vstack([
        *([mo.callout(mo.plain_text(_note), kind="danger")] if _note else []),
        mo.plain_text(turns.block_of(trace)),
        mo.md("**Corrections**") if _rows else mo.md("_No correction yet._"),
        *([mo.ui.table(_rows, selection=None)] if _rows else []),
    ])
    return


@app.cell
def _():
    """d1 PROMPT BUILDER. The six wordings that d1 receives, with the slots that each may name. Edit any of them and press the button: turns.with_prompts reads the message again with them and logs a prompt_edited correction (Undo above brings the old reading back). A wording that names a slot it does not have is refused with the reason."""
    _names: list[str] = [field.name for field in dataclasses.fields(scriptt16.Prompts)]
    wordings = mo.md("\n\n".join("{" + name + "}" for name in _names)).batch(**{
        name: mo.ui.text_area(value=getattr(read_trace.prompts, name), rows=2, full_width=True,
                              label=f"{name} · slots: {', '.join('{' + slot + '}' for slot in scriptt16.Prompts.SLOTS[name]) or 'none'}")
        for name in _names})
    reread_button = mo.ui.run_button(label="Read again with these wordings", kind="success")
    mo.vstack([source_view(scriptt16.Prompts.render, turns.with_prompts), wordings, reread_button])
    return


@app.cell
def _():
    mo.stop(not reread_button.value)
    try:
        _edited = scriptt16.Prompts(**wordings.value)
        if _edited == get_trace().prompts:
            _said = mo.callout(mo.md("No wording differs from the wordings of the current reading."), kind="info")
        else:
            set_trace(turns.with_prompts(get_trace(), _edited, model))
            _said = mo.callout(mo.md("d1 read the message again with the edited wordings."), kind="success")
    except ValueError as refusal:
        _said = mo.callout(mo.plain_text(str(refusal)), kind="danger")
    _said
    return


@app.cell
def _():
    """DECISION INSPECTOR. Every decision of d1 for the current reading: what d1 read (state), the wording it came from (template), the rendered instructions, and each option with its share and its bits, -log2 p. A share of yes is one option, "yes"."""

    def phrase_number(state: str) -> int | None:
        """Returns the number of the phrase that a request read: the last line of its state."""
        last = state.split("\n")[-1]
        return next((number for number, phrase in enumerate(innermost(current.message), 1) if current.text[phrase.start:phrase.end].strip() == last), None)

    def option_rows(decision: dict) -> list[tuple[str, str, float]]:
        """Returns (id, description, share) for each option of a decision, the largest share first."""
        if decision["probabilities"] is not None:
            described = {option["id"]: option["description"] for option in decision["options"]}
            return sorted(((key, described.get(key, ""), share) for key, share in decision["probabilities"].items()), key=lambda row: -row[2])
        return [("yes", "", decision["p_true"]), ("no", "", 1 - decision["p_true"])]

    decisions: list[dict] = [decision | {"state": request["state"], "phrase": phrase_number(request["state"])} for request in current.requests for decision in request["decisions"]]
    mo.ui.table([{"phrase": decision["phrase"], "state": decision["state"], "template": decision["template"], "instructions": decision["instructions"],
                  "options": "; ".join(f"{key} {share:.2f} ({scriptt16.bits(share):.2f} bits)" + (f" = {description[:40]}" if description and key != description else "") for key, description, share in option_rows(decision)[:6])}
                 for decision in decisions], selection=None, page_size=8)
    return


@app.cell
def _():
    """The request of the place chosen in BINDING above: the decisions of d1 for that phrase, for its function (what) or for that hole (which, many_is)."""
    _number, _path = place_choice.value
    _role = _path.split(".")[-1].replace("_", " ") if _path else None
    _mine = [decision for decision in decisions if decision["phrase"] == _number]
    if _path is None:
        _shown = [decision for decision in _mine if decision["template"] == "what"]
    else:
        _holes = [decision for decision in _mine if decision["template"] != "what"]
        _shown = [decision for decision in _holes if _role in decision["instructions"]] or _holes

    def _bar(key: str, description: str, share: float) -> str:
        return (f'<div style="display:flex;gap:8px;align-items:center;font-size:13px"><code style="min-width:150px">{html.escape(key[:24])}</code>'
                f'<div style="width:180px;background:rgba(128,128,128,.15)"><div style="width:{share * 100:.0f}%;background:#5b9cf5;height:10px"></div></div>'
                f'<span style="min-width:110px">{share:.3f} · {scriptt16.bits(share):.2f} bits</span><span style="opacity:.7">{html.escape(description[:80]) if description != key else ""}</span></div>')

    mo.Html("".join(f'<div style="margin:6px 0 12px"><div><b>{html.escape(decision["template"])}</b> · state: <code>{html.escape(decision["state"])}</code></div>'
                    f'<div style="margin:4px 0"><i>{html.escape(decision["instructions"])}</i></div>{"".join(_bar(*row) for row in option_rows(decision))}</div>'
                    for decision in _shown) or "<i>d1 was not asked about this place: one candidate, or none, so the search took it without a question.</i>")
    return


@app.cell
def _():
    """BEFORE AND AFTER AN EDITED WORDING. For the latest prompt_edited correction: the share of each decision of d1 before and after (decisions match by what d1 read, their wording and their order), and the lines for Claude before and after."""
    _edits = [index for index, correction in enumerate(trace.corrections) if correction.kind == "prompt_edited"]
    if not _edits:
        _shown = mo.md("_No wording edited yet. Edit a wording above and press the button._")
    else:
        _before = trace.history[_edits[-1]]
        _after = trace.history[_edits[-1] + 1] if _edits[-1] + 1 < len(trace.history) else trace.reading

        def _keyed(reading: Reading) -> dict[tuple, dict]:
            counted: dict[tuple, int] = {}
            found: dict[tuple, dict] = {}
            for request in reading.requests:
                for decision in request["decisions"]:
                    base = (request["state"], decision["template"])
                    counted[base] = counted.get(base, 0) + 1
                    found[(*base, counted[base])] = decision

            return found

        def _best(decision: dict | None) -> tuple[str, float] | None:
            if decision is None:
                return None
            if decision["probabilities"] is not None:
                key = max(decision["probabilities"], key=decision["probabilities"].get)
                return key, decision["probabilities"][key]
            return "yes", decision["p_true"]

        def _share_of(decision: dict | None, key: str) -> float | None:
            if decision is None:
                return None
            if decision["probabilities"] is not None:
                return decision["probabilities"].get(key)
            return decision["p_true"] if key == "yes" else None

        _old, _new = _keyed(_before), _keyed(_after)
        _rows = []
        for _key in dict.fromkeys([*_old, *_new]):
            _was, _now = _best(_old.get(_key)), _best(_new.get(_key))
            _now_of_was = _share_of(_new.get(_key), _was[0]) if _was else None
            _rows.append({"phrase": _key[0].split("\n")[-1][:50], "template": _key[1], "before": f"{_was[0]} {_was[1]:.3f}" if _was else "not asked",
                          "after": f"{_now[0]} {_now[1]:.3f}" if _now else "not asked",
                          "share of the former answer": f"{_was[1]:.3f} → {_now_of_was:.3f} ({_now_of_was - _was[1]:+.3f})" if _now_of_was is not None else ""})
        _diff = "\n".join(difflib.unified_diff(scriptt16.block(_before).splitlines(), scriptt16.block(_after).splitlines(), "before", "after", lineterm="")) or "The lines for Claude did not change."
        _changed = [name for name in _before.prompts.as_dict() if getattr(_before.prompts, name) != getattr(_after.prompts, name)]
        _shown = mo.vstack([mo.md(f"Edited wording(s): **{', '.join(_changed) or 'none'}**"), mo.ui.table(_rows, selection=None, page_size=10), mo.plain_text(_diff)])
    _shown
    return


@app.cell
def _():
    """CONTEXT[n+1]. The entities that this turn leaves in scope for the next one (turns.next_context): each with its identifier, its term, its origin and the entity it is a version of. The last column names each open hole of this reading that the entity could fill."""
    _open = [(number, path, hole) for number, phrase in enumerate(innermost(current.message), 1) for path, hole in scriptt16.holes_of(phrase.term)]
    mo.vstack([source_view(turns.next_context), mo.ui.table([{
        "id": entity.id, "term": say(entity.term, entity.text), "type": show(type_of(entity.term)), "turn": entity.turn, "origin": entity.origin, "version_of": entity.version_of or "",
        "can fill": ", ".join(f"{number}. {path}" for number, path, hole in _open if fills(entity.term, turns.element_of(hole.type))),
    } for entity in trace.context_out], selection=None)])
    return


@app.cell
def _():
    """THE NEXT TURN. A second message, read with prior_context = the context[n+1] above, so that "it" can name a result of this turn."""
    next_message = mo.ui.text(value="Show it.", full_width=True, label="The next message.")
    next_message
    return


@app.cell
def _():
    next_trace: turns.Trace = turns.start_turn(next_message.value, world, replies, model, context_in=trace.context_out, limits=limits)
    mo.vstack([drawn(next_trace.reading, next_trace.context_in), mo.plain_text(turns.block_of(next_trace))])
    return


@app.cell
def _():
    """The line of the log. Each type keeps its structure, and `decisions` has every answer of d1."""
    log_line: dict = scriptt16.record(current)
    log_line
    return


@app.cell
def _():
    """The reply comes, and the executions of the turn: one JSON record a line, such as {"kind": "file_diff", "path": "next/world.py"} or {"kind": "command", "cmd": "pytest", "exit_code": 0}. check gives each item one state: DONE (the reply says it is done and, for a Later or Observed result, an execution shows it), UNVERIFIED (the reply says so, and no execution shows it), OPEN (the reply does not say so) or BLOCKED (an execution for it failed). Empty the executions to see UNVERIFIED."""
    reply = mo.ui.text_area(value="I redesigned the mod and showed it to you.", rows=2, full_width=True, label="The reply.")
    executions_text = mo.ui.text_area(value='{"kind": "file_modified", "path": "mod/hooks/row.tsx", "detail": "redesigned the mod: new layout and colours"}', rows=3, full_width=True, label="The executions of the turn.")
    mo.vstack([reply, executions_text])
    return


@app.cell
def _():
    _executions: list[dict] = []
    _refusals: list[str] = []
    for _line in executions_text.value.splitlines():
        if _line.strip():
            try:
                _executions.append(json.loads(_line))
            except json.JSONDecodeError as refusal:
                _refusals.append(f"{_line!r}: {refusal}")
    checked: list[Checked] = scriptt16.check(current, reply.value, model, _executions, limits=limits)
    mo.vstack([*([mo.callout(mo.plain_text("\n".join(_refusals)), kind="danger")] if _refusals else []),
               mo.ui.table([{"call": one.call, "item": one.item or "", "state": one.state.name, "share": round(one.share, 3), "evidence": "; ".join(one.evidence)} for one in checked], selection=None)])
    return


@app.cell
def _():
    """THE GATE FOR A CHANGE OF THE WORLD. Edit the world at the top, then press the button. The edited world reads each approved case of golden.json, and the gate fails if any phrase reads otherwise than approved, if more holes stay open, or if the world has a fault. The line of the log above is replayed on its own phrases for the diagnostic bits only: d1 can be sure of a wrong reading."""
    replay = mo.ui.run_button(label="Check the edited world against the approved cases")
    replay
    return


@app.cell
def _():
    mo.stop(not replay.value)
    decision: Gate = scriptt16.gate(world, scriptt16.golden(here / "golden.json"), [log_line], model, current.prompts, limits)
    decision
    return


@app.cell
def _():
    """THE ACCEPTANCE REPORT. Seven criteria; each check must pass its positive case and reject a deliberate failure. The report runs the real d1 several dozen times, so it waits for the button."""
    acceptance_run = mo.ui.run_button(label="Run the acceptance report")
    acceptance_run
    return


@app.cell
def _():
    mo.stop(not acceptance_run.value, mo.md("_Press the button to run the seven criteria._"))
    import acceptance
    criteria: list = acceptance.run_acceptance(model=model, limits=limits)
    mo.vstack([
        mo.ui.table([{"id": one.id, "requirement": one.requirement, "result": one.result, "caught_deliberate_failure": one.caught_deliberate_failure,
                      "passing_outcome": one.passing_outcome, "check": one.check, "evidence": one.evidence} for one in criteria], selection=None),
        mo.plain_text(acceptance.table(criteria)),
    ])
    return


if __name__ == "__main__":
    app.run()
