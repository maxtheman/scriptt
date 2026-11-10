"""The search of scriptt 0.1.6: type-directed synthesis over the world of a folder.

The world (``agree.World``) is a closed type system. Reading a message means
building well-typed terms from it:

1. Lexical grounding. The message unfolds into phrases, and each span of text
   that names a value of a type of the world becomes a constant term.
2. Synthesis. For each phrase of the user, d1 chooses the function that the
   phrase asks for. Each parameter of that function is a hole with a type, and
   five rules build the terms that can fill a hole of that type: a constant from
   the environment, a product from its fields, a sum from one alternative, a
   type constructor by its own rule, and the application of a function.
3. Scoring. ``derivations`` returns only well-typed terms. ``solve`` asks d1 to
   choose one when ``derivations`` returns several.
4. Interpretation. The phrases fold into the lines for Claude, the line of the
   log and the check of a reply.
"""

import dataclasses
import difflib
import enum
import math
import pathlib
import typing
import unicodedata
import uuid

import harness as shipped
from agree import LATER, MANY, MAYBE, Applied, Base, Brand, Function, Member, Product, Sum, Type, World, is_subtype, show, tree

type Model = typing.Callable[[str, dict[str, dict]], dict[str, dict]]
"""The decision model d1: takes a state and questions, returns one answer for each question."""

JOIN = "Is the second text part of the same request as the first text?"
"""The one wording that 0.1.6 adds. It has no measurement yet."""

NONE_OF_THESE = "the text names none of these"
"""The description of the option that d1 chooses when no term fills a hole."""


@dataclasses.dataclass(frozen=True)
class Limits:
    """The numbers that the search uses. None of them has a measurement yet.

    Attributes:
        run: The number of consecutive words that an earlier reply must share
            with the message for the run to count as a quote of that reply.
        replies: The number of earlier replies that the search compares with the message.
        offered: The largest number of terms that d1 receives for one hole.
        depth: The largest number of function applications inside one argument.
        yes: The smallest share at which a yes of d1 counts.
    """

    run: int = 6
    replies: int = 8
    offered: int = 8
    depth: int = 1
    yes: float = 0.5


# ---- Questions for d1 -------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class YesNo:
    """A question that d1 answers with the share of yes.

    Attributes:
        instructions: The question.
    """

    instructions: str


@dataclasses.dataclass(frozen=True)
class OneOf:
    """A question that d1 answers by choosing one option.

    Attributes:
        instructions: The question.
        options: The description of each option, by its identifier.
    """

    instructions: str
    options: dict[str, str]


@dataclasses.dataclass(frozen=True)
class Choice:
    """The answer of d1 to a OneOf question.

    Attributes:
        shares: The share that d1 gave each option, by its identifier.
        best: The identifier of the option with the largest share.
    """

    shares: dict[str, float]
    best: str


def rendered(template: object) -> str:
    """Returns the text of a wording of the shipped harness, with its slots filled."""
    return shipped.yes(template)["instructions"]


def ask_all(model: Model, state: str, questions: dict[str, YesNo | OneOf]) -> dict[str, Choice | float]:
    """Sends several questions about one state to d1 in one request.

    Args:
        model: The decision model.
        state: The text that d1 reads.
        questions: The questions, each under a key.

    Returns:
        One answer under each key: a Choice for a OneOf question, and the share
        of yes for a YesNo question.
    """
    sent: dict[str, dict] = {}
    for key, question in questions.items():
        match question:
            case OneOf(instructions, options):
                listed = [{"id": identifier, "description": description} for identifier, description in options.items()]
                sent[key] = {"type": "choice", "instructions": instructions, "options": listed}
            case YesNo(instructions):
                sent[key] = {"type": "boolean", "instructions": instructions}
    received = model(state, sent)
    answers: dict[str, Choice | float] = {}
    for key, question in questions.items():
        if isinstance(question, OneOf):
            shares = received[key]["probabilities"]
            answers[key] = Choice(shares, max(shares, key=shares.get))
        else:
            answers[key] = received[key]["p_true"]
    return answers


# ---- Terms ------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Constant:
    """A value that the message gives: a span of text with a type of the world.

    Attributes:
        type: The type of the value.
        value: The value: a member of a sum type, a number, a path, or the words of a phrase.
        start: The place of its first character in the message. -1 if d1 chose
            the value and the message has no span for it.
        end: The place after its last character.
    """

    type: Type
    value: Member | int | pathlib.Path | str
    start: int
    end: int


@dataclasses.dataclass(frozen=True)
class Application:
    """A function of the world applied to one term for each parameter.

    Attributes:
        function: The function.
        arguments: The term for each parameter, by name.
    """

    function: Function
    arguments: dict[str, "Term"]


@dataclasses.dataclass(frozen=True)
class Record:
    """A value of a product type: one term for each field.

    Attributes:
        product: The product type.
        fields: The term for each field, by name.
    """

    product: Product
    fields: dict[str, "Term"]


@dataclasses.dataclass(frozen=True)
class Several:
    """A value of ``Many[T]``: every term of type ``T`` that the hole takes.

    Attributes:
        element: The type ``T``.
        terms: The terms.
    """

    element: Type
    terms: tuple["Term", ...]


@dataclasses.dataclass(frozen=True)
class Empty:
    """A value of ``Maybe[T]`` with no value in it.

    Attributes:
        type: The type ``Maybe[T]``.
    """

    type: Type


@dataclasses.dataclass(frozen=True)
class Hole:
    """A place in a term where a term of a known type is missing.

    Attributes:
        type: The type of the missing term.
    """

    type: Type


type Term = Constant | Application | Record | Several | Empty | Hole


def type_of(term: Term) -> Type:
    """Returns the type of a term.

    The application of a function to an argument of type ``Later[T]`` has the
    type ``Later`` of the result of the function: the application can run only
    after the argument is there.
    """
    match term:
        case Application(function, arguments):
            waits = any(isinstance(type_of(argument), Applied) and type_of(argument).constructor == LATER for argument in arguments.values())
            already_later = isinstance(function.result, Applied) and function.result.constructor == LATER
            return Applied(LATER, function.result) if waits and not already_later else function.result
        case Record(product=product):
            return product
        case Several(element=element):
            return Applied(MANY, element)
    return term.type


def fills(term: Term, goal: Type) -> bool:
    """Decides whether a term can fill a hole.

    Args:
        term: The term.
        goal: The type of the hole.

    Returns:
        True if the type of the term is a subtype of the goal. Also True if the
        term has the type ``Later[T]`` and ``T`` is a subtype of the goal: the
        value fills the hole when it is there.
    """
    given = type_of(term)
    if is_subtype(given, goal):
        return True
    return isinstance(given, Applied) and given.constructor == LATER and is_subtype(given.argument, goal)


# ---- Part 2: lexical grounding ----------------------------------------------


@dataclasses.dataclass(frozen=True)
class Phrase[Inner]:
    """A phrase of the message, with what stands at each place inside it.

    Phrase is a functor: ``map`` applies a function to each inner place and
    keeps the phrase. ``unfold`` and ``fold`` build on ``map``.

    Attributes:
        start: The place of its first character in the message.
        end: The place after its last character.
        brand: The brand of the text of the phrase. None for the whole message,
            which can hold phrases of several brands.
        inside: What stands at each inner place.
        starts_by: The rule that set the start of the phrase.
        choice: The answer of d1 about what the phrase asks for.
        term: The term that the phrase asks for.
    """

    start: int
    end: int
    brand: Brand | None
    inside: tuple[Inner, ...] = ()
    starts_by: str = ""
    choice: Choice | None = None
    term: Term | None = None

    def map(self, function: typing.Callable) -> "Phrase":
        """Returns the phrase with the function applied to each inner place."""
        return dataclasses.replace(self, inside=tuple(function(inner) for inner in self.inside))


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


def innermost(phrase: Phrase) -> list[Phrase]:
    """Returns the phrases that hold no other phrase, in the order of the message."""
    if not phrase.inside:
        return [phrase]
    return [found for inner in phrase.inside for found in innermost(inner)]


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


def chunks(text: str) -> list[tuple[int, int]]:
    """Returns the place of each run of characters between white space, without the signs around it."""
    found: list[tuple[int, int]] = []
    run_start: int | None = None
    for index, character in enumerate(text + " "):
        if not character.isspace():
            run_start = index if run_start is None else run_start
        elif run_start is not None:
            run = text[run_start:index]
            words = run.strip("`*\"'“”‘’()[]").rstrip(".,;:!?")
            if words:
                start = run_start + run.index(words)
                found.append((start, start + len(words)))
            run_start = None
    return found


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


def phrases(
    text: str,
    replies: list[str],
    world: World,
    same_request: typing.Callable[[str, str], float] | None = None,
    limits: Limits = Limits(),
) -> Phrase:
    """Unfolds a message into its phrases.

    The first cut separates the quotes of earlier replies from the text of the
    user. The second cut separates the text of the user at each proposed start.
    The world names the brand of each: ``Written`` for a quote of a reply, and
    ``Asked`` for the text of the user.

    Args:
        text: The message.
        replies: The earlier replies in the log.
        world: The world.
        same_request: A function that returns the share of d1 that two
            neighbouring phrases are one request. If given, d1 decides every
            start that the end of a sentence proposed. A blank line, a list item
            and the edge of a quote always start a phrase.
        limits: The numbers that the search uses.

    Returns:
        The message as one phrase, with its phrases inside it.
    """
    asked, quoted = world.types["Asked"], world.types["Written"]
    quotes = written(text, replies, limits.run)
    starts = proposed(text)

    def cut(phrase: Phrase) -> Phrase:
        if phrase.brand is None and quotes:
            edges = sorted({phrase.start, phrase.end, *(edge for quote in quotes for edge in quote)})
            parts: list[Phrase] = []
            for start, end in zip(edges, edges[1:]):
                if (start, end) in quotes:
                    parts.append(Phrase(start, end, quoted, starts_by="the log"))
                elif text[start:end].strip():
                    rule = "the phrase before it ends" if start else "the first word"
                    parts.append(Phrase(start, end, asked, starts_by=rule))
            # White space between two phrases belongs to the phrase after it.
            joined = [dataclasses.replace(parts[0], start=phrase.start)]
            for part in parts[1:]:
                joined.append(dataclasses.replace(part, start=joined[-1].end))
            joined[-1] = dataclasses.replace(joined[-1], end=phrase.end)
            return dataclasses.replace(phrase, inside=tuple(joined))
        if phrase.brand == quoted:
            return phrase
        inner_starts = sorted(start for start in starts if phrase.start < start < phrase.end and text[phrase.start:start].strip())
        edges = [phrase.start, *inner_starts, phrase.end]
        first_rule = phrase.starts_by or "the first word"
        sentences = [Phrase(start, end, asked, starts_by=starts.get(start, first_rule)) for start, end in zip(edges, edges[1:])]
        if same_request:
            kept = sentences[:1]
            for sentence in sentences[1:]:
                previous = kept[-1]
                proposed_by_sentence_end = sentence.starts_by.startswith("after")
                if proposed_by_sentence_end and same_request(text[previous.start:previous.end], text[sentence.start:sentence.end]) >= limits.yes:
                    kept[-1] = dataclasses.replace(previous, end=sentence.end)
                else:
                    kept.append(sentence)
            sentences = kept
        return dataclasses.replace(phrase, brand=phrase.brand or asked, inside=tuple(sentences) if len(sentences) > 1 else ())

    return unfold(cut, Phrase(0, len(text), None))


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


def grounded(text: str, world: World) -> list[Constant]:
    """Returns every constant term that the text of a message gives, in the order of the message."""
    found = [constant for expression in world.types.values() for constant in stands(expression, text, world.folder)]
    return sorted(found, key=lambda constant: (constant.start, -constant.end))


# ---- Part 3: type-directed synthesis ----------------------------------------


@dataclasses.dataclass(frozen=True)
class Environment:
    """The terms that are available to fill a hole of one phrase.

    Attributes:
        local: The terms that the phrase itself gives: its constants, and its own words.
        context: The terms from before the phrase, the nearest first: earlier
            constants, the words of earlier phrases, and the terms that earlier
            phrases ask for.
    """

    local: tuple[Term, ...]
    context: tuple[Term, ...]


@dataclasses.dataclass(frozen=True)
class Search:
    """What every step of the synthesis for one message needs.

    Attributes:
        text: The message.
        world: The world.
        model: The decision model.
        limits: The numbers that the search uses.
    """

    text: str
    world: World
    model: Model
    limits: Limits


def say(term: Term | None, text: str) -> str:
    """Returns a term as a call that a person can read.

    Args:
        term: The term.
        text: The message.

    Returns:
        A constant as its words in quote marks, an application as a call, a
        record as its product with its fields, several terms as a list, and a
        hole as ``...``. An empty ``Maybe`` is left out of the call around it.
    """
    match term:
        case Constant(value=Member(words=words)):
            return repr(words)
        case Constant(value=str(words)):
            return repr(" ".join(words.split()))
        case Constant(value=value):
            return repr(str(value))
        case Application(function, arguments):
            shown = ", ".join(f"{name}={say(argument, text)}" for name, argument in arguments.items() if not isinstance(argument, Empty))
            return f"{function.name}({shown})"
        case Record(product, fields):
            return f"{product.name}({', '.join(f'{name}={say(field, text)}' for name, field in fields.items())})"
        case Several(terms=terms):
            return f"[{', '.join(say(one, text) for one in terms)}]"
    return "..."


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


def solve(goal: Type, environment: Environment, search: Search, state: str, role: str, applying: Function, depth: int) -> Term:
    """Synthesizes a term for a hole, by the rule for the type of the hole.

    * A product type: one term for each field (product introduction).
    * A sum of types: if terms of the alternatives are at hand, d1 chooses
      among those terms, as for every other type. Else d1 chooses one
      alternative that has a term, and the search synthesizes that alternative
      (sum introduction).
    * ``Maybe[T]``: a term for ``T``, or ``Empty`` if no term exists.
    * ``Many[T]``: every term for ``T`` that the phrase itself gives. If the
      phrase gives none, every earlier term for ``T`` that d1 accepts.
    * Every other type: the terms that ``derivations`` enumerates. One term is
      taken as it is. With several terms, d1 chooses one, or none. With no term
      for a sum of members, d1 chooses one member, or none.

    Args:
        goal: The type of the hole.
        environment: The terms that are available.
        search: The message, the world, the model and the limits.
        state: The text that d1 reads: the phrase.
        role: The name of the hole, in words.
        applying: The function that has the hole.
        depth: The number of nested applications that are still allowed.

    Returns:
        The term. A ``Hole`` of the goal type if the search found no term or d1
        chose none.
    """
    world, text, limits, asks = search.world, search.text, search.limits, applying.asks
    which = rendered(shipped.NAMES(role, asks))
    match goal:
        case Product(fields=fields):
            return Record(goal, {name: solve(field, environment, search, state, name.replace("_", " "), applying, depth) for name, field in fields})
        case Applied(constructor=constructor, argument=inner) if constructor == MAYBE:
            term = solve(inner, environment, search, state, role, applying, depth)
            return Empty(goal) if isinstance(term, Hole) else term
        case Applied(constructor=constructor, argument=inner) if constructor == MANY:
            given = [term for term in environment.local if fills(term, inner)]
            if given:
                return Several(inner, tuple(given))
            earlier = [term for term in environment.context if fills(term, inner)][:limits.offered]
            if not earlier:
                return Hole(goal)
            questions = {str(index): YesNo(rendered(shipped.IS(say(term, text)[:200], role, asks))) for index, term in enumerate(earlier)}
            shares = ask_all(search.model, state, questions)
            accepted = tuple(term for index, term in enumerate(earlier) if shares[str(index)] >= limits.yes)
            return Several(inner, accepted) if accepted else Hole(goal)
        case Sum(alternatives=alternatives) if not any(isinstance(alternative, Member) for alternative in alternatives) and not derivations(goal, environment, world, depth, applying):
            possible = [alternative for alternative in alternatives if isinstance(alternative, Product) or derivations(alternative, environment, world, depth, applying)]
            if not possible:
                return Hole(goal)
            chosen = possible[0]
            if len(possible) > 1:
                options = {show(alternative): getattr(alternative, "describes", "") or show(alternative) for alternative in possible}
                choice = ask_all(search.model, state, {"which": OneOf(which, options | {"none": NONE_OF_THESE})})["which"]
                if choice.best == "none":
                    return Hole(goal)
                chosen = next(alternative for alternative in possible if show(alternative) == choice.best)
            term = solve(chosen, environment, search, state, role, applying, depth)
            return Hole(goal) if isinstance(term, Hole) else term
    offered = derivations(goal, environment, world, depth, applying)[:limits.offered]
    members = [alternative for alternative in goal.alternatives if isinstance(alternative, Member)] if isinstance(goal, Sum) else []
    if not offered and members:
        options = {member.name: member.words for member in members} | {"none": NONE_OF_THESE}
        choice = ask_all(search.model, state, {"which": OneOf(which, options)})["which"]
        chosen_member = next((member for member in members if member.name == choice.best), None)
        return Constant(goal, chosen_member, -1, -1) if chosen_member else Hole(goal)
    if not offered:
        return Hole(goal)
    chosen_term = offered[0]
    if len(offered) > 1:
        options = {str(index): say(term, text)[:200] for index, term in enumerate(offered)}
        choice = ask_all(search.model, state, {"which": OneOf(which, options | {"none": NONE_OF_THESE})})["which"]
        if choice.best == "none":
            return Hole(goal)
        chosen_term = offered[int(choice.best)]
    if isinstance(chosen_term, Application) and any(isinstance(argument, Hole) for argument in chosen_term.arguments.values()):
        return applied(chosen_term.function, environment, search, state, depth - 1)
    return chosen_term


def applied(function: Function, environment: Environment, search: Search, state: str, depth: int) -> Application:
    """Applies a function: synthesizes one term for each parameter (function application)."""
    arguments = {name: solve(parameter, environment, search, state, name.replace("_", " "), function, depth) for name, parameter in function.parameters}
    return Application(function, arguments)


def choose(phrase: Phrase, environment: Environment, search: Search) -> Phrase:
    """Asks d1 which function a phrase asks for, and synthesizes its term.

    d1 chooses one option among the functions of the world, "none" and
    "nothing". The option with the largest share is the choice.

    Args:
        phrase: A phrase of the user.
        environment: The terms that are available to the phrase.
        search: The message, the world, the model and the limits.

    Returns:
        The phrase with its choice. If d1 chooses a function, the phrase has the
        term of that function, with each parameter synthesized. If d1 chooses
        "nothing", the phrase gives words and has no term. If d1 chooses "none",
        d1 abstains: the phrase asks for something that no function fits.
    """
    state = search.text[phrase.start:phrase.end].strip()
    options = {name: function.asks for name, function in search.world.functions.items()} | shipped.ELSE
    choice = ask_all(search.model, state, {"what": OneOf(shipped.WHAT, options)})["what"]
    if choice.best not in search.world.functions:
        return dataclasses.replace(phrase, choice=choice)
    term = applied(search.world.functions[choice.best], environment, search, state, search.limits.depth)
    return dataclasses.replace(phrase, choice=choice, term=term)


@dataclasses.dataclass(frozen=True)
class Reading:
    """The result of the search for one message.

    Attributes:
        id: An identifier of the reading. A reply check or a correction can name
            the message by it.
        text: The message.
        message: The message as one phrase, with its phrases and their terms inside it.
        constants: The constant terms that the message gives.
        requests: Each request that the search sent to d1, with the state, the
            questions and the answers.
    """

    id: str
    text: str
    message: Phrase
    constants: list[Constant]
    requests: list[dict]


def ungrounded(world: World) -> list[str]:
    """Lists each parameter whose type no span of a message can have.

    ``stands`` grounds a sum of members, ``int`` and ``pathlib.Path``. The words
    of a phrase ground ``Asked``, ``Written`` and the types that these are
    subtypes of. A parameter of any other base type or brand can never be filled.
    """
    texts = (world.types.get("Asked"), world.types.get("Written"))
    faults: list[str] = []

    def grounds(expression: Type) -> bool:
        match expression:
            case Applied(argument=argument):
                return grounds(argument)
            case Product(fields=fields):
                return all(grounds(field) for _, field in fields)
            case Sum(alternatives=alternatives):
                return any(isinstance(alternative, Member) or grounds(alternative) for alternative in alternatives)
            case Base(python=python):
                return python in (int, pathlib.Path) or any(text and is_subtype(text, expression) for text in texts)
        return any(text and is_subtype(text, expression) for text in texts)

    for function in world.functions.values():
        faults += [f"{function.name}.{name}: no span of a message can have the type {show(parameter)}" for name, parameter in function.parameters if not grounds(parameter)]
    return faults


def read(
    text: str,
    world: World,
    replies: list[str],
    model: Model,
    join: bool = True,
    limits: Limits = Limits(),
    message: Phrase | None = None,
) -> Reading:
    """Runs the search on one message.

    Args:
        text: The message.
        world: The world.
        replies: The replies in the log from before the message.
        model: The decision model.
        join: If True, d1 decides whether two neighbouring sentences are one request.
        limits: The numbers that the search uses.
        message: The phrases of the message, if a record of the log already has
            them. The search then makes no new cut and asks d1 no join question.

    Returns:
        The reading of the message.

    Raises:
        ValueError: If the world has a fault, or a parameter that no span of a
            message can fill. The search runs only on a world with no fault.
    """
    problems = world.faults + ungrounded(world)
    if problems:
        raise ValueError("the search does not run on a world with faults: " + "; ".join(problems))
    requests: list[dict] = []

    def recorded(state: str, asked: dict[str, dict]) -> dict[str, dict]:
        answers = model(state, asked)
        requests.append({"state": state, "asked": asked, "answers": answers})
        return answers

    def same_request(first: str, second: str) -> float:
        state = "\n".join([first.strip(), second.strip()])
        return ask_all(recorded, state, {"join": YesNo(JOIN)})["join"]

    search = Search(text, world, recorded, limits)
    message = message or phrases(text, replies[-limits.replies:], world, same_request if join else None, limits)
    constants = grounded(text, world)
    finished: dict[int, Phrase] = {}
    context: list[Term] = []
    for phrase in innermost(message):
        words = Constant(phrase.brand, text[phrase.start:phrase.end].strip(), phrase.start, phrase.end)
        local = [constant for constant in constants if phrase.start <= constant.start < phrase.end]
        if phrase.brand == world.types["Asked"] and words.value:
            done = choose(phrase, Environment((*local, words), tuple(context)), search)
        else:
            done = phrase
        finished[phrase.start] = done
        # The nearest term comes first: the term of this phrase, its constants from last to first, then its words.
        context = [*([done.term] if done.term else []), *reversed(local), *([words] if words.value else []), *context]
    with_terms = fold(lambda phrase: phrase if phrase.inside else finished[phrase.start], message)
    return Reading(uuid.uuid4().hex, text, with_terms, constants, requests)


# ---- Part 4: interpretation -------------------------------------------------


def holes_of(term: Term | None, path: str = "") -> list[tuple[str, Hole]]:
    """Returns each open hole inside a term, with the path to it."""
    match term:
        case Hole():
            return [(path, term)]
        case Application(arguments=inner) | Record(fields=inner):
            return [found for name, argument in inner.items() for found in holes_of(argument, f"{path}.{name}" if path else name)]
        case Several(terms=terms):
            return [found for one in terms for found in holes_of(one, path)]
    return []


def term_record(term: Term, text: str) -> dict:
    """Converts a term to data that JSON can hold, with the type of each part as a tree."""
    line: dict = {"type": tree(type_of(term)), "reads": say(term, text)}
    match term:
        case Constant(start=start, end=end):
            return line | {"constant": [start, end]}
        case Application(function, arguments):
            return line | {"function": function.name, "arguments": {name: term_record(argument, text) for name, argument in arguments.items()}}
        case Record(fields=fields):
            return line | {"fields": {name: term_record(field, text) for name, field in fields.items()}}
        case Several(terms=terms):
            return line | {"several": [term_record(one, text) for one in terms]}
        case Empty():
            return line | {"empty": True}
    return line | {"hole": True}


def record(reading: Reading) -> dict:
    """Converts a reading to one line of the log, in form 4.

    Args:
        reading: The reading.

    Returns:
        A dict that JSON can hold. The phrases nest as they do in the message.
        Each phrase has its place, its brand, the choice of d1, and its term.
        ``decisions`` has every answer of d1 for the message.
    """
    text = reading.text

    def phrase_record(phrase: Phrase) -> dict:
        line = {"start": phrase.start, "end": phrase.end, "brand": phrase.brand.name if phrase.brand else None}
        if phrase.inside:
            return line | {"inside": list(phrase.inside)}
        line["starts_by"] = phrase.starts_by
        if phrase.choice:
            line |= {"choice": phrase.choice.best, "shares": {name: round(share, 3) for name, share in phrase.choice.shares.items()}}
        if phrase.term:
            line["term"] = term_record(phrase.term, text)
        return line

    decisions = [{"asked": key, "shares": answer.get("probabilities"), "yes": answer.get("p_true")}
                 for request in reading.requests for key, answer in request["answers"].items()]
    return {"form": 4, "id": reading.id, "text": text, "phrases": fold(phrase_record, reading.message), "decisions": decisions}


def block(reading: Reading) -> str:
    """Returns the lines that Claude receives with a message.

    Args:
        reading: The reading of the message.

    Returns:
        One line for each phrase that asks, with its term, the type of what must
        come back, and the share of d1. Then the phrases that give words, the
        quotes of earlier replies, and each open hole with its type.
    """
    text = reading.text
    lines: list[str] = []
    open_holes: list[str] = []
    gives_words: list[str] = []
    quotes: list[str] = []
    for number, phrase in enumerate(innermost(reading.message), 1):
        words = " ".join(text[phrase.start:phrase.end].split())[:90]
        if phrase.term:
            share = phrase.choice.shares[phrase.choice.best]
            lines.append(f'{number}. {say(phrase.term, text)} -> {show(type_of(phrase.term))}  {share:.2f}   "{words}"')
            open_holes += [f"{number}. {phrase.term.function.name}.{path}: {show(hole.type)}" for path, hole in holes_of(phrase.term)]
        elif phrase.choice and phrase.choice.best == "none":
            lines.append(f'{number}. ?  d1 abstains: no function of the world fits.   "{words}"')
        elif phrase.brand and phrase.brand.name == "Written":
            quotes.append(str(number))
        elif words:
            gives_words.append(str(number))
    if gives_words:
        lines.append(f"Words that ask for nothing: {', '.join(gives_words)}.")
    if quotes:
        lines.append(f"Your own earlier words, quoted: {', '.join(quotes)}.")
    if open_holes:
        lines += ["Open holes:", *open_holes]
    return "\n".join(lines)


class State(enum.Enum):
    """The state of one thing that a message asked for, after a reply."""

    DONE = "done"
    OPEN = "not done"
    PROMISED = "promised: the result may come after more work"


@dataclasses.dataclass(frozen=True)
class Checked:
    """The check of a reply against one term, or one term of a ``Many`` argument.

    Attributes:
        function: The name of the function of the term.
        item: The term of a ``Many`` argument that this check is about, as it
            reads. None if the check is about the whole term.
        state: The state after the reply.
        share: The share of d1 that the reply does it.
    """

    function: str
    item: str | None
    state: State
    share: float


def check(reading: Reading, reply: str, model: Model, limits: Limits = Limits()) -> list[Checked]:
    """Checks a reply against each term of a reading.

    d1 answers, for each term, whether the reply does it. The search checks a
    ``Many`` argument term by term, so that the check covers every item.

    Args:
        reading: The reading of the message.
        reply: The reply.
        model: The decision model.
        limits: The numbers that the search uses.

    Returns:
        One check for each term, or for each term of a ``Many`` argument. If the
        reply does it, the state is DONE. Otherwise the type of the term
        decides: a ``Later[...]`` term is PROMISED, and every other term is OPEN.
    """
    questions: dict[str, YesNo] = {}
    subjects: dict[str, tuple[Phrase, str | None]] = {}
    for phrase in innermost(reading.message):
        if not isinstance(phrase.term, Application):
            continue
        items = [say(one, reading.text) for argument in phrase.term.arguments.values() if isinstance(argument, Several) for one in argument.terms]
        for item in items or [None]:
            key = f"{phrase.start} {item}"
            asks = phrase.term.function.asks + (f": {item}" if item else "")
            questions[key] = YesNo(rendered(shipped.DID(asks)))
            subjects[key] = (phrase, item)
    if not questions:
        return []
    shares = ask_all(model, f"MESSAGE:\n{reading.text}\n\nREPLY:\n{reply}", questions)
    checked: list[Checked] = []
    for key, (phrase, item) in subjects.items():
        result = type_of(phrase.term)
        unfinished = State.PROMISED if isinstance(result, Applied) and result.constructor == LATER else State.OPEN
        state = State.DONE if shares[key] >= limits.yes else unfinished
        checked.append(Checked(phrase.term.function.name, item, state, round(shares[key], 3)))
    return checked


# ---- The gate for a change of the world ---------------------------------------


@dataclasses.dataclass(frozen=True)
class Gate:
    """The decision about a proposed change of world.py.

    Attributes:
        accepted: True if the proposed world has no fault and d1 needs no more
            bits per decision with it than the log records for the current world.
        current_bits: The average bits per decision in the log.
        proposed_bits: The average bits per decision with the proposed world.
            None if the proposed world has a fault and was not replayed.
        faults: The faults of the proposed world.
    """

    accepted: bool
    current_bits: float
    proposed_bits: float | None
    faults: list[str]


def bits(share: float) -> float:
    """Returns the bits of one decision: ``-log2`` of the share of the answer that d1 chose."""
    return -math.log2(max(share, 1e-9))


def recorded_bits(line: dict) -> list[float]:
    """Returns the bits of each decision in one line of the log.

    A join decision is excluded. It does not depend on the world, and a replay
    takes the phrases from the log and makes no join decision.
    """
    found: list[float] = []
    for decision in line["decisions"]:
        if decision["asked"] == "join":
            continue
        shares = decision["shares"]
        found.append(bits(max(shares.values()) if shares else max(decision["yes"], 1 - decision["yes"])))
    return found


def recorded_phrases(line: dict, world: World) -> Phrase:
    """Rebuilds the phrases of a message from one line of the log, with no term."""
    def rebuilt(phrase: dict) -> Phrase:
        inside = tuple(rebuilt(inner) for inner in phrase.get("inside", ()))
        return Phrase(phrase["start"], phrase["end"], world.types.get(phrase["brand"]), inside, phrase.get("starts_by", ""))
    return rebuilt(line["phrases"])


def gate(proposed: World, lines: list[dict], model: Model, limits: Limits = Limits()) -> Gate:
    """Decides whether a proposed change of world.py is accepted.

    The log already has the answers of d1 for the current world, so the current
    world is not run again. The proposed world is run on the phrases that the
    log has, so d1 gets no join question.

    Args:
        proposed: The world with the change.
        lines: Lines of the log in form 4, from ``record``.
        model: The decision model.
        limits: The numbers that the search uses.

    Returns:
        The decision. A proposed world with a fault is rejected with no replay.
        Otherwise the change is rejected if the average bits per decision go up.
    """
    average = lambda found: sum(found) / len(found) if found else 0.0
    current_bits = average([one for line in lines for one in recorded_bits(line)])
    faults = proposed.faults + ungrounded(proposed)
    if faults:
        return Gate(False, current_bits, None, faults)
    replayed: list[float] = []
    for line in lines:
        reading = read(line["text"], proposed, [], model, False, limits, recorded_phrases(line, proposed))
        replayed += recorded_bits(record(reading))
    return Gate(average(replayed) <= current_bits, current_bits, average(replayed), [])
