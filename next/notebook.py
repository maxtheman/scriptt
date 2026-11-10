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

Each cell that shows a function has the function as it is in next/agree.py or
next/scriptt16.py, copied word for word.

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
    import json
    import pathlib
    import sys
    import types
    import typing
    import unicodedata

    import marimo as mo

    here: pathlib.Path = pathlib.Path(__file__).resolve().parent
    sys.path[:0] = [str(here), str(here.parent / ".scriptt")]
    import agree
    import harness
    import scriptt16
    from agree import CONSTRUCTORS, LATER, MANY, MAYBE, Applied, Arrow, Base, Brand, Constructor, Function, Kind, Member, Product, Star, Sum, Type, World, mentions, show
    from scriptt16 import (
        Application, Checked, Constant, Empty, Environment, Gate, Hole, Limits, Phrase, Reading, Record, Search, Several, Term,
        chunks, fills, innermost, say, type_of,
    )
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
    {"faults": world.faults + scriptt16.ungrounded(world)} | {name: type(one).__name__ for name, one in world.types.items()}
    return


@app.cell
def _():
    """FUNCTION. Each function of the world has typed parameters and a typed result."""
    {function.name: f"({', '.join(f'{name}: {show(parameter)}' for name, parameter in function.parameters)}) -> {show(function.result)}" for function in world.functions.values()}
    return


@app.cell
def _():
    """RULES OF A WORLD. agree.load lists a fault for two functions with the same parameter types and result type, for two types with the same structure, and for an Enum or a product type that fewer than two functions use."""


    def duplicates(types: dict[str, Type], functions: dict[str, Function], file_name: str) -> list[str]:
        """Lists each function and each type that has the same structure as an earlier one.

        Two functions with the same parameter types and the same result type fit the
        same holes, so the types cannot separate them. Two product types with the
        same fields, or two sum types with the same alternatives, are one type
        under two names.

        Args:
            types: The types of the world, by name.
            functions: The functions of the world, by name.
            file_name: The name of the world file, for the faults.

        Returns:
            One fault for each duplicate. A brand is excluded: two brands over the
            same type are different types by definition.
        """
        faults: list[str] = []
        seen_signatures: dict[tuple, str] = {}
        for function in functions.values():
            signature = (tuple(parameter for _, parameter in function.parameters), function.result)
            if signature in seen_signatures:
                faults.append(f"{file_name}:{function.line} {function.name}: the same parameter types and result type as {seen_signatures[signature]}")
            seen_signatures.setdefault(signature, function.name)
        seen_structures: dict[tuple, str] = {}
        for name, expression in types.items():
            if not isinstance(expression, Sum | Product) or expression.name != name:
                continue
            structure = expression.fields if isinstance(expression, Product) else tuple(alternative.words if isinstance(alternative, Member) else alternative for alternative in expression.alternatives)
            if structure in seen_structures:
                faults.append(f"{file_name} {name}: the same structure as {seen_structures[structure]}")
            seen_structures.setdefault(structure, name)
        return faults


    def single_use(types: dict[str, Type], functions: dict[str, Function], file_name: str) -> list[str]:
        """Lists each Enum and each product type that fewer than two functions use.

        Args:
            types: The types of the world, by name.
            functions: The functions of the world, by name.
            file_name: The name of the world file, for the faults.

        Returns:
            One fault for each such type. A function uses a type if a parameter or
            the result has the type, or has it inside.
        """
        faults: list[str] = []
        for name, expression in types.items():
            is_enum = isinstance(expression, Sum) and any(isinstance(alternative, Member) for alternative in expression.alternatives)
            if not (is_enum or isinstance(expression, Product)):
                continue
            users = [function.name for function in functions.values() if any(mentions(used, expression) for used in (*(parameter for _, parameter in function.parameters), function.result))]
            if len(users) < 2:
                faults.append(f"{file_name} {name}: {len(users)} function uses this type ({', '.join(users) or 'none'}), and a custom type needs 2. Use Words, Path or int.")
        return faults


    duplicates(world.types, world.functions, "world.py"), single_use(world.types, world.functions, "world.py")
    return


@app.cell
def _():
    """KIND. The type of a type. A type has kind *. A type constructor has kind * -> *. kind_of refuses a constructor applied to the wrong kind."""
    surface: Sum = world.types["Surface"]


    def kind_of(expression: Type | Constructor) -> Kind:
        """Returns the kind of a type or of a type constructor.

        Args:
            expression: A type or a type constructor.

        Returns:
            ``Star`` for a type. The arrow kind of a constructor. For an applied
            constructor, the kind that the constructor gives.

        Raises:
            TypeError: If a constructor is applied to something whose kind differs
                from the kind that the constructor takes.
        """
        match expression:
            case Constructor(kind=kind):
                return kind
            case Applied(constructor, argument):
                if kind_of(argument) != constructor.kind.argument:
                    raise TypeError(f"{constructor.name} takes a type of kind {show(constructor.kind.argument)}, and {show(argument)} has kind {show(kind_of(argument))}")
                return constructor.kind.result
        return Star()


    def kind_or_refusal(expression: Type | Constructor) -> str:
        """Returns the kind of an expression as text, or the reason that kind_of refuses it."""
        try:
            return show(kind_of(expression))
        except TypeError as refusal:
            return str(refusal)


    {
        "Surface": kind_or_refusal(surface),
        "Many": kind_or_refusal(MANY),
        "Many[Surface]": kind_or_refusal(Applied(MANY, surface)),
        "Many[Maybe]": kind_or_refusal(Applied(MANY, MAYBE)),
    }
    return


@app.cell
def _():
    """BRAND. A typing.NewType in world.py: a new nominal type over an existing type. is_subtype makes a brand a subtype of the type it wraps, and keeps two brands apart."""
    brands: dict[str, Brand] = {name: one for name, one in world.types.items() if isinstance(one, Brand)}


    def is_subtype(given: Type, wanted: Type) -> bool:
        """Decides whether a value of one type can stand where another type is wanted.

        Args:
            given: The type of the value.
            wanted: The type of the place.

        Returns:
            True if the types are equal, if ``given`` is a brand over a subtype of
            ``wanted``, if ``wanted`` is a sum with an alternative that ``given`` is
            a subtype of, or if both apply the same constructor to types that are
            in this relation.
        """
        if given == wanted:
            return True
        if isinstance(wanted, Sum) and any(not isinstance(alternative, Member) and is_subtype(given, alternative) for alternative in wanted.alternatives):
            return True
        if isinstance(given, Brand):
            return is_subtype(given.of, wanted)
        if isinstance(given, Applied) and isinstance(wanted, Applied) and given.constructor == wanted.constructor:
            return is_subtype(given.argument, wanted.argument)
        return False


    {name: show(brand.of) for name, brand in brands.items()}, {
        "Asked is a subtype of Words": is_subtype(brands["Asked"], brands["Words"]),
        "Written is a subtype of Words": is_subtype(brands["Written"], brands["Words"]),
        "Written is a subtype of Asked": is_subtype(brands["Written"], brands["Asked"]),
    }
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


    def places(text: str) -> list[tuple[int, int]]:
        """Returns the place of each word and each sign of a text.

        A sign between two letters or digits belongs to the word, as in "t-strings",
        "d1's" and "world.py".
        """
        found: list[tuple[int, int]] = []
        word_start: int | None = None
        for index, character in enumerate(text):
            joins_word = word_start is not None and character in "-'’._" and text[index + 1:index + 2].isalnum()
            if character.isalnum() or joins_word:
                word_start = index if word_start is None else word_start
                continue
            if word_start is not None:
                found.append((word_start, index))
                word_start = None
            if not character.isspace():
                found.append((index, index + 1))
        if word_start is not None:
            found.append((word_start, len(text)))
        return found


    [text[start:end] for start, end in places(text)]
    return


@app.cell
def _():
    """Which words did an earlier reply already have? Those words get the brand Written."""


    def written(text: str, replies: list[str], least: int) -> list[tuple[int, int]]:
        """Finds the parts of a message that quote an earlier reply.

        Compares the message with the replies in the log. Asks no model.

        Args:
            text: The message.
            replies: The earlier replies.
            least: The number of consecutive words that the message must share with
                a reply for the run to count as a quote.

        Returns:
            The start and the end of each quote, in order. A quote includes the
            opening sign and the closing signs that touch it.
        """
        word_places = places(text)
        word_indexes = [index for index, (start, _) in enumerate(word_places) if text[start].isalnum()]
        normal = lambda word: word.lower().replace("’", "'")
        message_words = [normal(text[slice(*word_places[index])]) for index in word_indexes]
        category = lambda index: unicodedata.category(text[word_places[index][0]])
        touches = lambda before, after: word_places[before][1] == word_places[after][0]
        opens = lambda index: category(index) in ("Ps", "Pi") or text[word_places[index][0]] in "\"'`*"

        runs: list[tuple[int, int]] = []
        for reply in replies:
            reply_words = [normal(reply[start:end]) for start, end in places(reply) if reply[start].isalnum()]
            matcher = difflib.SequenceMatcher(None, message_words, reply_words, autojunk=False)
            for block in matcher.get_matching_blocks():
                if block.size < least:
                    continue
                first = word_indexes[block.a]
                last = word_indexes[block.a + block.size - 1]
                while first > 0 and opens(first - 1) and touches(first - 1, first):
                    first -= 1
                while last + 1 < len(word_places) and category(last + 1).startswith("P") and touches(last, last + 1):
                    last += 1
                runs.append((word_places[first][0], word_places[last][1]))

        merged: list[tuple[int, int]] = []
        for start, end in sorted(runs):
            if merged and start <= merged[-1][1] + 1:
                merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
            else:
                merged.append((start, end))
        return merged


    quotes: list[tuple[int, int]] = written(text, replies, limits.run)
    [text[start:end] for start, end in quotes]
    return


@app.cell
def _():
    """Where can a phrase start?"""


    def proposed(text: str) -> dict[int, str]:
        """Proposes each place where a phrase can start.

        Three rules propose a start, in this order: a blank line, a list item, and
        the end of a sentence. A rule proposes only a place that no earlier rule took.

        Args:
            text: The message.

        Returns:
            The rule that proposes each place, by the place of the first character of the phrase.
        """
        starts: dict[int, str] = {}
        line_start = 0
        after_blank_line = False
        for line in text.splitlines(keepends=True):
            words = line.split(maxsplit=1)
            first_character = line_start + len(line) - len(line.lstrip())
            if words and after_blank_line and first_character:
                starts.setdefault(first_character, "a blank line")
            is_bullet = bool(words) and words[0] in ("-", "*")
            is_number = bool(words) and words[0][:-1].isdigit() and words[0][-1] in ".)"
            if len(words) == 2 and (is_bullet or is_number):
                starts.setdefault(first_character, "a list item")
            after_blank_line = not words
            line_start += len(line)

        word_places = places(text)
        for index, (start, end) in enumerate(word_places[:-1]):
            if text[start:end] not in (".", "?", "!", "…"):
                continue
            for following in range(index + 1, len(word_places)):
                follows_space = word_places[following][0] > word_places[following - 1][1]
                if follows_space or text[word_places[following][0]].isalnum():
                    starts.setdefault(word_places[following][0], "after " + text[start:end])
                    break
        return starts


    starts: dict[int, str] = proposed(text)
    [(rule, text[start:start + 30]) for start, rule in sorted(starts.items())]
    return


@app.cell
def _():
    """UNFOLD and FUNCTOR. unfold grows the phrases with one function. It uses Phrase.map, which applies a function inside a phrase and keeps the phrase."""


    def unfold(cut: typing.Callable[[Phrase], Phrase], phrase: Phrase) -> Phrase:
        """Grows the phrases of a message from one phrase.

        Args:
            cut: A function that gives one phrase its inner phrases.
            phrase: The phrase to start from.

        Returns:
            The phrase with ``cut`` applied to it and to every phrase inside it.

        Raises:
            ValueError: If ``cut`` returns an inner phrase that is as long as the
                phrase that holds it. Every inner phrase must be shorter, which
                guarantees that the unfold ends.
        """
        grown = cut(phrase)
        if any(inner.end - inner.start >= phrase.end - phrase.start for inner in grown.inside):
            raise ValueError(f"a cut returned an inner phrase as long as its phrase: {phrase}")
        return grown.map(lambda inner: unfold(cut, inner))


    def model(state: str, questions: dict[str, dict]) -> dict[str, dict]:
        """Sends questions about one state to the real d1."""
        return harness.put(harness.d1, state, questions)


    unfolded: Phrase = scriptt16.phrases(text, replies, world, None, limits)
    phrases: list[Phrase] = innermost(unfolded)
    [(phrase.brand.name, phrase.starts_by, text[phrase.start:phrase.end].strip()) for phrase in phrases]
    return


@app.cell
def _():
    """GROUNDING. stands turns a span of text into a constant term with a type of the world."""


    def stands(expression: Type, text: str, folder: pathlib.Path) -> list[Constant]:
        """Finds each span of a text that names a value of a type.

        The search uses these constants as the atomic terms of a message.

        Args:
            expression: A sum type with members, ``int`` or ``pathlib.Path``.
            text: The text.
            folder: The folder that holds the paths that the text names.

        Returns:
            One constant for each span. A member of a sum type stands where its
            words stand, word for word. A number stands where the characters are
            decimal digits. A path stands where the characters name a file or a
            folder that exists under ``folder``. Every other type has no rule and
            gives no constant.
        """
        found: list[Constant] = []
        match expression:
            case Sum(alternatives=alternatives):
                word_places = places(text)
                text_words = [text[start:end].lower() for start, end in word_places]
                for member in alternatives:
                    if not isinstance(member, Member):
                        continue
                    member_words = [member.words[start:end].lower() for start, end in places(member.words)]
                    for index in range(len(text_words) - len(member_words) + 1):
                        if text_words[index:index + len(member_words)] == member_words:
                            found.append(Constant(expression, member, word_places[index][0], word_places[index + len(member_words) - 1][1]))
            case Base(python=python) if python is int:
                found = [Constant(expression, int(text[start:end]), start, end) for start, end in chunks(text) if text[start:end].isdecimal()]
            case Base(python=python) if python is pathlib.Path:
                for start, end in chunks(text):
                    characters = text[start:end]
                    if ("/" in characters or "." in characters) and (folder / characters).exists():
                        found.append(Constant(expression, pathlib.Path(characters), start, end))
        return found


    constants: list[Constant] = sorted((constant for expression in world.types.values() for constant in stands(expression, text, world.folder)), key=lambda constant: constant.start)
    [(text[constant.start:constant.end], show(constant.type)) for constant in constants]
    return


@app.cell
def _():
    """PART 3: TYPE-DIRECTED SYNTHESIS. Take one phrase of the user."""
    _asked = {f"{index}: {text[phrase.start:phrase.end].strip()[:90]}": index for index, phrase in enumerate(phrases) if phrase.brand == world.types["Asked"]}
    chosen = mo.ui.dropdown(_asked, value=list(_asked)[1] if len(_asked) > 1 else next(iter(_asked)), full_width=True, label="A phrase of the user.")
    chosen
    return


@app.cell
def _():
    """The environment of the phrase: the terms that can fill its holes. Local terms come from the phrase. Context terms come from before it."""
    reading: Reading = scriptt16.read(text, world, replies, model, False, limits)
    chosen_phrase: Phrase = innermost(reading.message)[chosen.value]
    earlier_phrases: list[Phrase] = innermost(reading.message)[:chosen.value]


    def environment_of(phrase: Phrase, earlier: list[Phrase]) -> Environment:
        """Builds the environment of a phrase.

        Args:
            phrase: The phrase.
            earlier: The phrases before it, with their terms.

        Returns:
            The constants and the words of the phrase as local terms. The terms,
            the constants and the words of the earlier phrases as context, the
            nearest first.
        """
        words_of = lambda one: Constant(one.brand, text[one.start:one.end].strip(), one.start, one.end)
        constants_of = lambda one: [constant for constant in reading.constants if one.start <= constant.start < one.end]
        context: list[Term] = []
        for one in earlier:
            context = [*([one.term] if one.term else []), *reversed(constants_of(one)), words_of(one), *context]
        return Environment((*constants_of(phrase), words_of(phrase)), tuple(context))


    environment: Environment = environment_of(chosen_phrase, earlier_phrases)
    {"local": [f"{say(term, text)} : {show(type_of(term))}" for term in environment.local], "context": [f"{say(term, text)} : {show(type_of(term))}" for term in environment.context]}
    return


@app.cell
def _():
    """d1 chooses the function that the phrase asks for. Each parameter of that function is now a hole with a type."""
    largest_shares: list[tuple[str, float]] = sorted(chosen_phrase.choice.shares.items(), key=lambda option: -option[1])[:4]
    asked_function: Function | None = world.functions.get(chosen_phrase.choice.best)
    largest_shares, {name: show(parameter) for name, parameter in asked_function.parameters} if asked_function else "no function"
    return


@app.cell
def _():
    """HOLE. derivations lists every well-typed term for a hole. An earlier term that changed a value stands for that value from then on."""


    def derivations(goal: Type, environment: Environment, world: World, depth: int, applying: Function | None = None) -> list[Term]:
        """Enumerates the terms that can fill a hole, by two of the five rules.

        * Constant: every term of the environment whose type fits the goal. If an
          earlier application took a value as an argument and gives a value that
          fits the goal, that application is the current version of the value: it
          is listed, and the constant with the same value is left out. "Redesign
          the mod. Then show the mod." shows the redesigned mod.
        * Application: every function of the world whose result fits the goal and
          whose required parameters each have a constant in the environment. The
          parameters of the application are holes. The function that has the hole
          is excluded, and so is a function that the list already has a term of.

        The other three rules (product, sum and type constructor) decompose the
        goal, and ``solve`` applies them.

        Args:
            goal: The type of the hole.
            environment: The terms that are available.
            world: The world.
            depth: The number of nested applications that are still allowed.
            applying: The function that has the hole, if any.

        Returns:
            The terms, the nearest first, then the applications. Two terms that read
            the same are one term.
        """
        found: list[Term] = [term for term in (*environment.local, *environment.context) if fills(term, goal)]
        versions = [term for term in found if isinstance(term, Application)]
        taken_by = lambda constant: any(argument == constant or (isinstance(argument, Constant) and (argument.type, argument.value) == (constant.type, constant.value))
                                        for version in versions for argument in version.arguments.values())
        found = [term for term in found if not (isinstance(term, Constant) and taken_by(term))]
        if depth > 0:
            for function in world.functions.values():
                if function == applying or any(isinstance(term, Application) and term.function == function for term in found):
                    continue
                application = Application(function, {name: Hole(parameter) for name, parameter in function.parameters})
                required = [parameter for _, parameter in function.parameters if not (isinstance(parameter, Applied) and parameter.constructor == MAYBE)]
                supported = bool(required) and all(derivations(parameter, environment, world, 0) for parameter in required)
                if supported and fills(application, goal):
                    found.append(application)
        distinct: dict[str, Term] = {}
        for term in found:
            distinct.setdefault(say(term, ""), term)
        return list(distinct.values())


    {name: [f"{say(term, text)} : {show(type_of(term))}" for term in derivations(parameter.alternatives[0] if isinstance(parameter, Sum) and not parameter.name == "" and not isinstance(parameter.alternatives[0], Member) else parameter, environment, world, limits.depth, asked_function)]
     for name, parameter in (asked_function.parameters if asked_function else ())}
    return


@app.cell
def _():
    """solve applies the rule for the type of the hole and asks d1 when several terms fit. This is the term of the phrase, and its type."""
    (say(chosen_phrase.term, text), show(type_of(chosen_phrase.term))) if chosen_phrase.term else chosen_phrase.choice.best
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


    def fold(combine: typing.Callable[[Phrase], object], phrase: Phrase) -> object:
        """Collapses the phrases of a message to one result.

        Args:
            combine: A function that turns one phrase into a result. The phrase that
                it receives has a result at each inner place.
            phrase: The phrase to collapse.

        Returns:
            The result of ``combine`` for the phrase.
        """
        return combine(phrase.map(lambda inner: fold(combine, inner)))


    fold(lambda phrase: "".join(phrase.inside) or text[phrase.start:phrase.end], reading.message) == text
    return


@app.cell
def _():
    COLOURS: list[str] = ["#5b9cf5", "#e5a33a", "#b07fe0", "#4fb8b0", "#e77fb3", "#8bc34a", "#ff8a65", "#9fa8da"]


    def drawn(reading: Reading) -> mo.Html:
        """Folds a reading into one paragraph: the message as it was written, with its terms marked in place.

        Args:
            reading: The reading.

        Returns:
            The message as running text. A phrase that asks starts with its number,
            the same number as in the lines for Claude, and its function. A constant
            that fills a hole is marked once, where it stands, with the hole and the
            type. A constant that fills no hole is underlined, with its type on
            hover. After the phrase come only the holes
            that the phrase itself does not fill: one that a term from before the
            phrase fills, with the number of that phrase, and one that is open. A
            quote of an earlier reply is grey.
        """
        text = reading.text
        names = list(world.types)
        phrases_in_order = innermost(reading.message)
        number = lambda term: next((chr(0x278A + index) for index, phrase in enumerate(phrases_in_order) if phrase.term is term and isinstance(term, Application)), "")

        def colour(expression: Type) -> str:
            return COLOURS[names.index(expression.name) % len(COLOURS)] if getattr(expression, "name", "") in names else "#999"

        def filled(words: str, hole: str, expression: Type) -> str:
            label = f"{hole} ∶ {show(expression)}" if hole else show(expression)
            return f'<span style="background:{colour(expression)};color:#111;border-radius:4px;padding:1px 5px">{html.escape(words)} <small>: {html.escape(label)}</small></span>'

        def unfilled(words: str, expression: Type) -> str:
            return f'<span title="{html.escape(show(expression))}" style="border-bottom:1.5px dotted {colour(expression)}">{html.escape(words)}</span>'

        def socket(content: str, expression: Type, is_open: bool) -> str:
            border = "dashed" if is_open else "solid"
            return f' <span style="border:1.5px {border} {colour(expression)};border-radius:4px;padding:1px 5px"><small>{content}</small></span>'

        def leaves(term: Term, path: str) -> list[tuple[str, Term]]:
            """Returns each part of a term with the path of its hole. An earlier term and a new application are parts of their own."""
            match term:
                case Record(fields=fields):
                    return [found for name, field in fields.items() for found in leaves(field, f"{path}.{name}")]
                case Several(terms=terms):
                    return [found for one in terms for found in leaves(one, path)]
                case Application(arguments=arguments) if not number(term):
                    return [(path, term)] + [found for name, argument in arguments.items() for found in leaves(argument, f"{path}.{name}")]
            return [(path, term)]

        def phrase_drawn(phrase: Phrase) -> str:
            words = text[phrase.start:phrase.end]
            if phrase.inside:
                return "".join(phrase.inside)
            if phrase.brand and phrase.brand.name == "Written":
                return f'<span style="background:rgba(128,128,128,.18);font-style:italic">{html.escape(words)}</span>'
            if not isinstance(phrase.term, Application):
                return f'<span style="opacity:.55">{html.escape(words)}</span>'
            parts = [found for name, argument in phrase.term.arguments.items() for found in leaves(argument, name)]
            whole = (phrase.start, phrase.end)
            here = {(part.start, part.end): path for path, part in parts if isinstance(part, Constant) and phrase.start <= part.start and (part.start, part.end) != whole}
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
                match part:
                    case Hole(type=expression):
                        drawn_words += socket(f"◻ {path}: {html.escape(show(expression))}", expression, True)
                    case Application() if number(part):
                        drawn_words += socket(f"{path} ↩ {number(part)} {html.escape(say(part, text))}", type_of(part), False)
                    case Application(function=function):
                        drawn_words += socket(f"{path} = {function.name}(…)", type_of(part), False)
                    case Constant(start=start) if start < phrase.start:
                        drawn_words += socket(f"{path} ↩ {html.escape(say(part, text))}", part.type, False)
                    case Constant(start=start, end=end) if (start, end) == whole:
                        drawn_words += socket(f"{path} = these words", part.type, False)
            return drawn_words + html.escape(text[phrase.start + len(words.rstrip()):phrase.end])

        return mo.Html(f'<div style="line-height:2.3;white-space:pre-wrap">{scriptt16.fold(phrase_drawn, reading.message)}</div>')


    drawn(reading)
    return


@app.cell
def _():
    """The lines that Claude receives."""
    mo.plain_text(scriptt16.block(reading))
    return


@app.cell
def _():
    """The line of the log. Each type keeps its structure, and `decisions` has every answer of d1."""
    log_line: dict = scriptt16.record(reading)
    log_line
    return


@app.cell
def _():
    """The reply comes. check gives each term a named state. A term of type Later[...] that is not done yet is promised."""
    reply = mo.ui.text_area(value="I redesigned the mod and showed it to you.", rows=2, full_width=True, label="The reply.")
    reply
    return


@app.cell
def _():
    checked: list[Checked] = scriptt16.check(reading, reply.value, model, limits)
    [(one.function, one.item, one.state.value, one.share) for one in checked]
    return


@app.cell
def _():
    """THE GATE FOR A CHANGE OF THE WORLD. Edit the world at the top, then press the button. The current bits come from the line of the log above, so the world as it was is not run again. The edited world is run on the phrases that the log has."""
    replay = mo.ui.run_button(label="Replay the message with the edited world")
    replay
    return


@app.cell
def _():
    mo.stop(not replay.value)
    _on_disk = types.ModuleType("world_on_disk")
    _on_disk.__file__ = str(here / "world.py")
    exec(compile((here / "world.py").read_text(), "world.py", "exec"), vars(_on_disk))
    recorded_line: dict = scriptt16.record(scriptt16.read(text, agree.load(_on_disk), replies, model, False, limits))
    decision: Gate = scriptt16.gate(world, [recorded_line], model, limits)
    decision
    return


if __name__ == "__main__":
    app.run()
