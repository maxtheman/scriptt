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
import hashlib
import json
import math
import pathlib
import string
import typing
import unicodedata
import uuid

import harness as shipped
from agree import LATER, MANY, MAYBE, Applied, Base, Brand, Function, Member, Product, Sum, Type, World, is_subtype, show, tree

type Model = typing.Callable[[str, dict[str, dict]], dict[str, dict]]
"""The decision model d1: takes a state and questions, returns one answer for each question."""

JOIN = "Does the second text only add detail to the request of the first text, without asking the reader to do something more?"
"""Whether the second of two neighbouring sentences only continues the request of the first.

A sentence that asks for an action of its own must stay its own phrase: joining it drops an
obligation. Measured with the real d1-2b on 2026-11-10, asked alone as ``read`` asks it, on 48
written pairs (26 in which the second sentence asks for its own action, 22 in which it only adds
detail), at ``Limits.yes``: the first wording, "Is the second text part of the same request as the
first text?", joined 19 of the 26 (it gave 0.84 to "Redesign the mod." and "Then show me the mod,
redesigned.") and split 6 of the 22; this wording joins 2 of the 26 and splits 5 of the 22. A
second rule, to join only if the ``what`` wording reads the second sentence alone as no function,
split all 22: d1 reads a fragment such as "The one in the pane." as show (0.43).
"""

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


@dataclasses.dataclass(frozen=True)
class Prompts:
    """The six wordings that d1 receives. Slots are str.format names.

    The defaults of what and which are the wordings of the shipped harness,
    so that the default record sends d1 the same text as 0.1.6 for them.
    many_is asks whether the message asks for the value and does not leave
    it out: the shipped wording ("are the words ... the {role} for that?")
    took "the page" in "Compare the mod, not the page." (yes 0.545 with the
    real d1; 0.228 with this wording). did names the call and the phrase;
    evidence is new. A person may edit any wording; a
    wording may leave out a slot, but it may not name a slot that the wording
    does not have.

    Attributes:
        join: Whether the second of two neighbouring sentences only adds detail
            to the request of the first, and asks for no action of its own. No slots.
        what: Which function a phrase asks for. No slots.
        which: Which candidate fills a hole. Slots: {asks}, the docstring of the
            function; {role}, the name of the hole in words.
        many_is: Whether one candidate belongs in a ``Many`` hole. Slots: {asks},
            {role} and {value}, the candidate as it reads, with no quote marks
            around a constant (see ``plain``): the wording adds its own.
        did: Whether the prose of a reply says that it did what one item of a
            phrase asks. Slots: {asks}, the docstring of the function (with the
            item of a ``Many`` argument or a field of a record); {call}, the term
            as it reads; {phrase}, the words of the phrase. The executions
            are judged apart, by ``evidence``: a reply that only says it is done
            is UNVERIFIED, not DONE.
        evidence: Whether one execution record of the turn is work on one item.
            Slots: {asks}, {call} and {phrase}, as for ``did``. The sixth
            wording: ``check`` asks it only when the types of the world cannot
            decide the match (see ``matches``).
    """

    join: str = JOIN
    what: str = shipped.WHAT
    which: str = "The text asks the reader to {asks}. Which {role} does the text name for that?"
    many_is: str = 'The message asks the reader to {asks}. Is "{value}" one of the {role} that the message asks for, and not one that it leaves out?'
    did: str = 'The message asks the reader to {asks} ({call} for "{phrase}"). Does the reply say that this is done?'
    evidence: str = 'Does this record change or run the thing that {call} names ("{phrase}")?'

    SLOTS = {"join": (), "what": (), "which": ("asks", "role"), "many_is": ("asks", "value", "role"), "did": ("asks", "call", "phrase"), "evidence": ("asks", "call", "phrase")}
    """The slots that each wording may name."""

    def __post_init__(self) -> None:
        for name in self.SLOTS:
            slots_of(name, getattr(self, name))

    def render(self, name: str, **slots: str) -> str:
        """Returns one wording with its slots filled.

        Args:
            name: The name of the wording: join, what, which, many_is, did or evidence.
            **slots: The value of each slot that the wording may name.

        Returns:
            The text that d1 receives.

        Raises:
            ValueError: If the wording names a slot that it does not have.
        """
        template = getattr(self, name)
        slots_of(name, template)
        return template.format(**slots)

    def as_dict(self) -> dict[str, str]:
        """Returns each wording by its name, in the order of the fields."""
        return {field.name: getattr(self, field.name) for field in dataclasses.fields(self)}


def slots_of(name: str, template: str) -> list[str]:
    """Returns the slots that one wording names, and checks them.

    Args:
        name: The name of the wording, a key of ``Prompts.SLOTS``.
        template: The text of the wording.

    Returns:
        The slot names, in the order that the wording names them.

    Raises:
        ValueError: If the wording is not a valid str.format text, or names a
            slot that is not one of its allowed slots (an empty or numbered
            slot, or a slot with an attribute or an index, also counts as unknown).
    """
    allowed = Prompts.SLOTS[name]
    try:
        parsed = list(string.Formatter().parse(template))
    except ValueError as error:
        raise ValueError(f"the {name} wording is not a valid template ({error}); write a literal brace as {{{{ or }}}}") from None
    named = [field for _, field, _, _ in parsed if field is not None]
    for field in named:
        if field not in allowed:
            listed = ", ".join("{" + slot + "}" for slot in allowed) or "none"
            raise ValueError(f"the {name} wording names the slot {{{field}}}, which it does not have; its slots are: {listed}")
    return named


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
        origin: Who first gave the value: "Asked" for the text of the user,
            "Written" for a quote of a reply, "Observed" for the output of a
            process. The brand of the phrase that the value stands in. None if
            the search does not know.
        adopted_by: The words of the phrase of the user that adopts the value as
            its own, after d1 confirmed that the phrase refers to it. A
            ``Written`` quote that the user adopts can fill an ``Asked`` hole,
            and keeps its origin. None if no phrase adopted it.
    """

    type: Type
    value: Member | int | pathlib.Path | str
    start: int
    end: int
    origin: str | None = None
    adopted_by: str | None = None


@dataclasses.dataclass(frozen=True)
class Application:
    """A function of the world applied to one term for each parameter.

    Attributes:
        function: The function.
        arguments: The term for each parameter, by name.
        origin: The brand of the phrase that asks for the application: "Asked"
            for a phrase of the user. None for an application inside another term.
        adopted_by: The words of the phrase of the user that adopts the
            application as its own. None if no phrase adopted it.
    """

    function: Function
    arguments: dict[str, "Term"]
    origin: str | None = None
    adopted_by: str | None = None


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
        reason: Why the hole is open. "no_candidate": the search had no term
            for the hole, and larger limits would give none. "model_abstained":
            d1 saw every term that the search had and chose none of them.
            "search_bound": candidates existed beyond ``limits.depth`` or
            ``limits.offered``, so the right term may be missing:
            ``limits.offered`` dropped terms that d1 never saw, or one more
            nested application would give more terms. This reason wins over the
            other two.
    """

    type: Type
    reason: str = "no_candidate"


type Term = Constant | Application | Record | Several | Empty | Hole


def type_of(term: Term) -> Type:
    """Returns the type of a term.

    The application of a function to an argument that waits has the type
    ``Later`` of the result of the function: the application can run only after
    the argument is there. An argument waits if its type is ``Later[T]``, or if
    it is a record with a field that waits, or several terms of which one waits.
    The rule applies at every depth, so a ``Later`` term inside a record inside
    a list inside an argument makes the application wait.
    """
    match term:
        case Application(function, arguments):
            waits = any(has_later(argument) for argument in arguments.values())
            already_later = isinstance(function.result, Applied) and function.result.constructor == LATER
            return Applied(LATER, function.result) if waits and not already_later else function.result
        case Record(product=product):
            return product
        case Several(element=element):
            return Applied(MANY, element)
    return term.type


def has_later(term: Term) -> bool:
    """Decides whether a term holds a value that comes only after more work.

    Returns:
        True if the type of the term is ``Later[T]``, or if a part of the term
        holds such a value: an argument of an application, a field of a record,
        or one of several terms, at any depth.
    """
    match term:
        case Application(arguments=parts) | Record(fields=parts):
            inside = any(has_later(part) for part in parts.values())
        case Several(terms=terms):
            inside = any(has_later(one) for one in terms)
        case _:
            inside = False
    if inside:
        return True
    given = term.function.result if isinstance(term, Application) else type_of(term)
    return isinstance(given, Applied) and given.constructor == LATER


def fills(term: Term, goal: Type) -> bool:
    """Decides whether a term can fill a hole.

    Args:
        term: The term.
        goal: The type of the hole.

    Returns:
        True if the type of the term is a subtype of the goal. Also True if the
        term has the type ``Later[T]`` and ``T`` is a subtype of the goal: the
        value fills the hole when it is there. Also True if the goal is a
        provenance over ``T``, such as ``Asked[Surface]``, the term has that
        provenance by its authority, and its type without its provenance is a
        subtype of ``T``: a Surface that the user names fills ``Asked[Surface]``.
    """
    given = type_of(term)
    if is_subtype(given, goal):
        return True
    if isinstance(given, Applied) and given.constructor == LATER and is_subtype(given.argument, goal):
        return True
    if isinstance(goal, Brand) and goal.bare is not None and authority(term) == goal.name:
        unbranded = given.of if isinstance(given, Brand) and given.bare is not None else given
        return is_subtype(unbranded, goal.of)
    return False


def authority(term: Term) -> str | None:
    """Returns the provenance by which a term stands now.

    A term that a phrase of the user adopted stands as ``Asked``, whatever its
    origin. Every other term stands by its origin.
    """
    if getattr(term, "adopted_by", None):
        return "Asked"
    return getattr(term, "origin", None)


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
        origins: The number of the phrase that each term of the context came
            from, counted from 1 in the order of the message, by the term as it
            reads. d1 sees the number in the label of an option.
        phrases: The text of each phrase before this one, in the order of the
            message: phrase number n is ``phrases[n - 1]``.
    """

    local: tuple[Term, ...]
    context: tuple[Term, ...]
    origins: tuple[tuple[str, int], ...] = ()
    phrases: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class Search:
    """What every step of the synthesis for one message needs.

    Attributes:
        text: The message.
        world: The world.
        model: The decision model.
        limits: The numbers that the search uses.
        prompts: The wordings that d1 receives.
    """

    text: str
    world: World
    model: Model
    limits: Limits
    prompts: Prompts


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


def plain(term: Term, text: str) -> str:
    """Returns a term as ``say`` does, but a constant as its words alone, with no quote marks.

    A wording that puts the candidate in its own quote marks takes this form,
    so that d1 reads "the mod" and not "'the mod'".
    """
    match term:
        case Constant(value=Member(words=words)):
            return words
        case Constant(value=str(words)):
            return " ".join(words.split())
        case Constant(value=value):
            return str(value)
    return say(term, text)


def derivations(goal: Type, environment: Environment, world: World, depth: int, applying: Function | None = None) -> list[Term]:
    """Enumerates the terms that can fill a hole, by two of the five rules.

    * Constant: every term of the environment whose type fits the goal. An
      earlier application that took a value and gives a value that fits the
      goal is listed, and so is the value itself: "Redesign the mod. Then show
      the original mod." and "... Then show the redesigned mod." name different
      terms, and d1 chooses by the words of the phrase.
    * Application: every function of the world whose result fits the goal and
      whose required parameters each can be synthesized with ``depth - 1``
      nested applications (``can_synthesize``: a product by its fields, which
      uses no depth). A function with no parameters needs nothing and is
      listed. A function whose parameters are all ``Maybe`` is not listed: the
      phrase gives nothing that asks for it. The parameters of the application
      are holes. The function that has the hole is excluded, and so is a
      function that the list already has a term of.

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

    if depth > 0:
        for function in world.functions.values():
            if function == applying or any(isinstance(term, Application) and term.function == function for term in found):
                continue
            application = Application(function, {name: Hole(parameter) for name, parameter in function.parameters})
            required = [parameter for _, parameter in function.parameters if not (isinstance(parameter, Applied) and parameter.constructor == MAYBE)]
            needs_nothing = not function.parameters
            supported = needs_nothing or (bool(required) and all(can_synthesize(parameter, environment, world, depth - 1) for parameter in required))
            if supported and fills(application, goal):
                found.append(application)
    distinct: dict[str, Term] = {}
    for term in found:
        distinct.setdefault(say(term, ""), term)
    return list(distinct.values())


def origin(term: Term, environment: Environment) -> int | None:
    """Returns the number of the earlier phrase that a term comes from, or None for a term of this phrase or a new call."""
    if any(term is local for local in environment.local):
        return None
    return dict(environment.origins).get(say(term, ""))


def labelled(term: Term, offered: list[Term], environment: Environment, text: str) -> str:
    """Returns an option for d1: the term as it reads, and what kind of term it is.

    The label separates a value from a version of it that an earlier phrase
    made, so d1 can choose by the words of the phrase. It is built from the
    kind of the term, the number of its phrase and the other offered terms,
    never from the words of a message:

    * A term that an earlier phrase asked for: "the result of
      redesign(surface='the mod') in phrase 1".
    * A constant that such a result took as an argument: "the original 'the
      mod'".
    * Any other constant: "'the mod' (as named in this phrase)" or "'the mod'
      (as named in phrase 1)".
    * An application that the search proposes: "redesign(surface=...) (a new
      call)".
    """
    reads = say(term, text)[:200]
    number = origin(term, environment)
    if isinstance(term, Application):
        return f"{reads} (a new call)" if number is None else f"the result of {reads} in phrase {number}"
    if isinstance(term, Constant):
        same = lambda argument: isinstance(argument, Constant) and (argument.type, argument.value) == (term.type, term.value)
        versions = [other for other in offered if isinstance(other, Application) and origin(other, environment) is not None and any(same(argument) for argument in other.arguments.values())]
        if versions:
            return f"the original {reads}"
        return f"{reads} (as named in this phrase)" if number is None else f"{reads} (as named in phrase {number})"
    return reads if number is None else f"{reads} (from phrase {number})"


def can_synthesize(goal: Type, environment: Environment, world: World, depth: int) -> bool:
    """Decides whether ``solve`` can build a term for a hole, without asking d1.

    It follows the rules of ``solve``: a product needs a term for each field,
    and uses no depth. A sum of types needs one alternative. ``Maybe[T]`` can
    stay empty, so it always can. ``Many[T]`` and ``Later[T]`` need a term for
    ``T``. Every type can also take a term that ``derivations`` lists: a
    constant of the environment, or a function of the world with ``depth``
    nested applications still allowed.

    Args:
        goal: The type of the hole.
        environment: The terms that are available.
        world: The world.
        depth: The number of nested applications that are still allowed.

    Returns:
        True if a term can be built.
    """
    if derivations(goal, environment, world, depth):
        return True
    match goal:
        case Product(fields=fields):
            return all(can_synthesize(field, environment, world, depth) for _, field in fields)
        case Sum(alternatives=alternatives):
            return any(not isinstance(alternative, Member) and can_synthesize(alternative, environment, world, depth) for alternative in alternatives)
        case Applied(constructor=constructor) if constructor == MAYBE:
            return True
        case Applied(argument=inner):
            return can_synthesize(inner, environment, world, depth)
    return False


def solve(goal: Type, environment: Environment, search: Search, state: str, role: str, applying: Function, depth: int) -> Term:
    """Synthesizes a term for a hole, by the rule for the type of the hole.

    * A product type: one term for each field (product introduction).
    * A sum of types: if terms of the alternatives are at hand, d1 chooses
      among those terms, as for every other type. Else d1 chooses one
      alternative that has a term, and the search synthesizes that alternative
      (sum introduction).
    * ``Maybe[T]``: a term for ``T``, or ``Empty`` if no term exists.
    * ``Many[T]``: the terms for ``T`` that the phrase itself gives and that d1
      accepts: d1 answers for each one whether the phrase takes it, so "Compare
      the mod, not the page." keeps only the mod. A mention is not an
      inclusion. If the phrase gives no term, or d1 accepts none of its terms,
      every earlier term for ``T`` that d1 accepts.
    * Every other type: the terms that ``derivations`` enumerates. One term is
      taken as it is. With several terms, d1 chooses one, or none: each option
      is labelled by ``labelled``, and d1 reads the earlier phrases that the
      offered terms come from before this phrase. With no term for a sum of
      members, d1 chooses one member, or none.

    Each ``Hole`` that solve returns has a reason. "no_candidate": no term was
    there to offer. "model_abstained": d1 saw every term and chose "none", or
    answered no for every item of a ``Many``. "search_bound": the
    limits cut terms, so the right term may be missing: more terms existed
    than ``limits.offered``, or one more allowed nested application would give
    more terms. The third reason wins over the other two, because with a cut
    neither "there was no term" nor "d1 refused every term" is known.

    Args:
        goal: The type of the hole.
        environment: The terms that are available.
        search: The message, the world, the model and the limits.
        state: The text that d1 reads: the phrase.
        role: The name of the hole, in words.
        applying: The function that has the hole.
        depth: The number of nested applications that are still allowed.

    Returns:
        The term. A ``Hole`` of the goal type, with its reason, if the search
        found no term or d1 chose none.
    """
    world, text, limits, asks = search.world, search.text, search.limits, applying.asks

    def open_hole(otherwise: str, listed: int | None = None) -> Hole:
        # listed: the number of terms before limits.offered cut the list, if a list was cut.
        listed_now = len(derivations(goal, environment, world, depth, applying))
        deeper = len(derivations(goal, environment, world, depth + 1, applying)) > listed_now
        over_offer = listed is not None and listed > limits.offered
        return Hole(goal, "search_bound" if deeper or over_offer else otherwise)

    which = search.prompts.render("which", asks=asks, role=role)
    match goal:
        case Product(fields=fields):
            return Record(goal, {name: solve(field, environment, search, state, name.replace("_", " "), applying, depth) for name, field in fields})
        case Applied(constructor=constructor, argument=inner) if constructor == MAYBE:
            term = solve(inner, environment, search, state, role, applying, depth)
            return Empty(goal) if isinstance(term, Hole) else term
        case Applied(constructor=constructor, argument=inner) if constructor == MANY:
            given = [term for term in environment.local if fills(term, inner)]
            earlier = [term for term in environment.context if fills(term, inner)]
            refused = False
            for listed in (given, earlier):
                candidates = listed[:limits.offered]
                if not candidates:
                    continue
                questions = {str(index): YesNo(search.prompts.render("many_is", asks=asks, value=plain(term, text)[:200], role=role)) for index, term in enumerate(candidates)}
                shares = ask_all(search.model, state, questions)
                accepted = tuple(term for index, term in enumerate(candidates) if shares[str(index)] >= limits.yes)
                if accepted:
                    return Several(inner, accepted)
                refused = True
            truncated = len(given) > limits.offered or len(earlier) > limits.offered
            return Hole(goal, "search_bound" if truncated else "model_abstained" if refused else "no_candidate")
        case Sum(alternatives=alternatives) if not any(isinstance(alternative, Member) for alternative in alternatives) and not derivations(goal, environment, world, depth, applying):
            possible = [alternative for alternative in alternatives if isinstance(alternative, Product) or derivations(alternative, environment, world, depth, applying)]
            if not possible:
                return open_hole("no_candidate")
            chosen = possible[0]
            if len(possible) > 1:
                options = {show(alternative): getattr(alternative, "describes", "") or show(alternative) for alternative in possible}
                choice = ask_all(search.model, state, {"which": OneOf(which, options | {"none": NONE_OF_THESE})})["which"]
                if choice.best == "none":
                    return open_hole("model_abstained")
                chosen = next(alternative for alternative in possible if show(alternative) == choice.best)
            term = solve(chosen, environment, search, state, role, applying, depth)
            return Hole(goal, term.reason) if isinstance(term, Hole) else term
    listed = [*adoptions(goal, environment, search, state), *derivations(goal, environment, world, depth, applying)]
    offered = listed[:limits.offered]
    members = [alternative for alternative in goal.alternatives if isinstance(alternative, Member)] if isinstance(goal, Sum) else []
    if not offered and members:
        options = {member.name: member.words for member in members} | {"none": NONE_OF_THESE}
        choice = ask_all(search.model, state, {"which": OneOf(which, options)})["which"]
        chosen_member = next((member for member in members if member.name == choice.best), None)
        return Constant(goal, chosen_member, -1, -1) if chosen_member else open_hole("model_abstained")
    if not offered:
        return open_hole("no_candidate")
    chosen_term = offered[0]
    if len(offered) > 1:
        options = {str(index): labelled(term, offered, environment, text) for index, term in enumerate(offered)}
        # d1 reads the earlier phrases that the offered terms come from, then this phrase: "it" needs its referent.
        sources = sorted({number for term in offered if (number := origin(term, environment)) is not None})
        shown = "\n".join([*(environment.phrases[number - 1] for number in sources), state])
        choice = ask_all(search.model, shown, {"which": OneOf(which, options | {"none": NONE_OF_THESE})})["which"]
        if choice.best == "none":
            return open_hole("model_abstained", len(listed))
        chosen_term = offered[int(choice.best)]
    if isinstance(chosen_term, Application) and any(isinstance(argument, Hole) for argument in chosen_term.arguments.values()):
        return applied(chosen_term.function, environment, search, state, depth - 1)
    return chosen_term


def adoptions(goal: Type, environment: Environment, search: Search, state: str) -> list[Term]:
    """Offers each earlier quote of a reply that the phrase adopts as the user's own words.

    A quote of a reply has the origin ``Written`` and cannot fill an ``Asked``
    hole by its type. "Keep to that from now on" makes the quote a rule of the
    user. No list of words finds "that": d1 answers, for each word of the
    phrase, whether that word means the quote, with the wording of
    ``harness.REFERS``. A quote that d1 says one word means is adopted.

    Args:
        goal: The type of the hole.
        environment: The terms that are available.
        search: The message, the world, the model and the limits.
        state: The words of the phrase that has the hole.

    Returns:
        Each adopted quote, with ``adopted_by`` set to the words of the phrase.
        Empty if the goal is no ``Asked`` provenance, if no earlier quote would
        fill it, or if d1 says no word of the phrase means any quote.
    """
    if not (isinstance(goal, Brand) and goal.bare is not None and goal.name == "Asked"):
        return []
    quotes = [term for term in environment.context
              if isinstance(term, Constant) and term.origin == "Written" and not term.adopted_by and fills(dataclasses.replace(term, adopted_by=state), goal)]
    quotes = quotes[:search.limits.offered]
    words = list(dict.fromkeys(state[start:end] for start, end in places(state) if state[start].isalnum()))
    if not quotes or not words:
        return []
    meaning = lambda term: term.value.words if isinstance(term.value, Member) else " ".join(str(term.value).split())
    adopted: list[Term] = []
    for quote in quotes:
        questions = {str(index): YesNo(rendered(shipped.REFERS(word, meaning(quote)))) for index, word in enumerate(words)}
        shares = ask_all(search.model, f"{meaning(quote)}\n{state}", questions)
        if max(shares.values()) >= search.limits.yes:
            adopted.append(dataclasses.replace(quote, adopted_by=state))
    return adopted


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
    choice = ask_all(search.model, state, {"what": OneOf(search.prompts.render("what"), options)})["what"]
    if choice.best not in search.world.functions:
        return dataclasses.replace(phrase, choice=choice)
    term = applied(search.world.functions[choice.best], environment, search, state, search.limits.depth)
    return dataclasses.replace(phrase, choice=choice, term=dataclasses.replace(term, origin=phrase.brand.name if phrase.brand else None))


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
        prompts: The wordings that d1 received, so that the reading can run again.
        limits: The numbers that the search used, so that the reading can run again.
    """

    id: str
    text: str
    message: Phrase
    constants: list[Constant]
    requests: list[dict]
    prompts: Prompts = Prompts()
    limits: Limits = Limits()


def ungrounded(world: World) -> list[str]:
    """Lists each parameter whose type neither a span of a message nor a function of the world can give.

    ``stands`` grounds a sum of members, ``int`` and ``pathlib.Path``. The words
    of a phrase ground ``Asked``, ``Written`` and the types that these are
    subtypes of. A function of the world gives its result type, and through
    ``Later[T]`` also ``T``, so ``produce() -> Token`` makes a parameter of type
    ``Token`` satisfiable. A function counts only once each of its own
    parameters is satisfiable: the search starts from the functions with no
    parameter and the types that spans ground, and adds functions until no more
    can be added. So a function that only feeds itself does not count. A
    product needs each field, and a sum one alternative.
    """
    texts = (world.types.get("Asked"), world.types.get("Written"))
    given: list[Type] = []

    def produced(expression: Type) -> bool:
        for result in given:
            if is_subtype(result, expression):
                return True
            if isinstance(result, Applied) and result.constructor == LATER and is_subtype(result.argument, expression):
                return True
        return False

    def grounds(expression: Type) -> bool:
        if produced(expression):
            return True
        match expression:
            case Applied(argument=argument):
                return grounds(argument)
            case Product(fields=fields):
                return all(grounds(field) for _, field in fields)
            case Sum(alternatives=alternatives):
                return any(isinstance(alternative, Member) or grounds(alternative) for alternative in alternatives)
            case Base(python=python):
                return python in (int, pathlib.Path) or any(text and is_subtype(text, expression) for text in texts)
            case Brand(name=name, of=wrapped, bare=bare) if bare is not None and wrapped != bare and name in ("Asked", "Written"):
                return grounds(wrapped)  # a constant in a phrase of that brand has that origin: Asked[Surface] is a Surface that the user names
        return any(text and is_subtype(text, expression) for text in texts)

    waiting_functions = list(world.functions.values())
    added = True
    while added:
        added = False
        for function in list(waiting_functions):
            if all(grounds(parameter) for _, parameter in function.parameters):
                given.append(function.result)
                waiting_functions.remove(function)
                added = True

    faults: list[str] = []
    for function in world.functions.values():
        faults += [f"{function.name}.{name}: no span of a message can have the type {show(parameter)}, and no function of the world gives it"
                   for name, parameter in function.parameters if not grounds(parameter)]
    return faults


def world_hash(world: World) -> str:
    """Returns a hash of the schema of a world, the same for the same types and functions.

    The hash covers the tree of every type, and the name, the docstring, the
    parameters and the result of every function, in a canonical JSON dump. It
    leaves out the lines of world.py and the folder, so that a moved comment or
    a moved folder keeps the hash.
    """
    functions = {name: {"asks": function.asks, "parameters": [[parameter, tree(one)] for parameter, one in function.parameters], "result": tree(function.result)}
                 for name, function in world.functions.items()}
    dump = {"types": {name: tree(one) for name, one in world.types.items()}, "functions": functions, "faults": world.faults}
    return hashlib.sha256(json.dumps(dump, sort_keys=True).encode()).hexdigest()[:16]


def prompts_hash(prompts: Prompts) -> str:
    """Returns a hash of the five wordings: of ``dataclasses.asdict(prompts)`` as canonical JSON."""
    return hashlib.sha256(json.dumps(dataclasses.asdict(prompts), sort_keys=True).encode()).hexdigest()[:16]


def template_of(key: str, question: dict) -> str:
    """Returns the name of the wording that a question of the search was rendered from.

    The search names its questions by key: "join", "what" and "which" are the
    keys of those wordings, and a yes-or-no question under any other key is a
    ``many_is`` question about one candidate of a ``Many`` hole.
    """
    if key in ("join", "what", "which"):
        return key
    return "many_is" if question.get("type") == "boolean" else key


def request_entry(state: str, asked: dict[str, dict], answers: dict[str, dict], world_digest: str, prompts_digest: str) -> dict:
    """Returns the record of one request to d1, with the full context of each decision.

    Args:
        state: The text that d1 read.
        asked: The questions as d1 received them, by key.
        answers: The answers of d1, by key.
        world_digest: The ``world_hash`` of the world that the search ran on.
        prompts_digest: The ``prompts_hash`` of the wordings that d1 received.

    Returns:
        A dict with ``state``, ``asked`` and ``answers`` as d1 sent and received
        them, the two hashes, and ``decisions``: for each key, the key, the
        name of the wording, the rendered instructions, the options (id and
        description), and the probabilities or the share of yes.
    """
    decisions = [{"key": key, "template": template_of(key, question), "instructions": question["instructions"], "options": question.get("options", []),
                  "probabilities": answers.get(key, {}).get("probabilities"), "p_true": answers.get(key, {}).get("p_true")} for key, question in asked.items()]
    return {"state": state, "asked": asked, "answers": answers, "world_hash": world_digest, "prompts_hash": prompts_digest, "decisions": decisions}


def environment_of(phrase: Phrase, earlier: list[Phrase], constants: list[Constant], text: str, prior_context: typing.Sequence = ()) -> Environment:
    """Returns the terms that are available to one phrase of a message.

    Args:
        phrase: The phrase.
        earlier: The phrases of the message before it, with their terms, in order.
        constants: The constant terms that the message gives.
        text: The message.
        prior_context: The entities of earlier turns, the nearest first:
            objects with a ``term`` and the ``text`` of their message
            (``turns.Entity``), or terms.

    Returns:
        The environment. Its local terms are the constants of the phrase, then
        the words of the phrase (always last). Its context is, the nearest
        first: for each earlier phrase from the last, its term, its constants
        from last to first and its words; then the terms of earlier turns. Its
        phrases are the message of each earlier turn that an entity names, the
        oldest first, then the earlier phrases of this message; ``origins``
        numbers each term of the context by those phrases, so an entity of an
        earlier turn is labelled by the message of its turn.
    """
    shown: list[str] = []
    origins: dict[str, int] = {}
    for entity in reversed(tuple(prior_context)):
        source = getattr(entity, "text", "")
        if source:
            if source not in shown:
                shown.append(source)
            origins[say(getattr(entity, "term", entity), "")] = shown.index(source) + 1
    context: list[Term] = [getattr(entity, "term", entity) for entity in prior_context]
    given_by = lambda one: one.brand.name if one.brand else None  # a constant and the words of a phrase have the brand of the phrase as origin
    for done in earlier:
        local = [dataclasses.replace(constant, origin=given_by(done)) for constant in constants if done.start <= constant.start < done.end]
        words = Constant(done.brand, text[done.start:done.end].strip(), done.start, done.end, given_by(done))
        # The nearest term comes first: the term of the phrase, its constants from last to first, then its words.
        made_here = [*([done.term] if done.term else []), *reversed(local), *([words] if words.value else [])]
        context = [*made_here, *context]
        shown.append(text[done.start:done.end].strip())
        origins |= {say(term, ""): len(shown) for term in made_here}
    local = [dataclasses.replace(constant, origin=given_by(phrase)) for constant in constants if phrase.start <= constant.start < phrase.end]
    words = Constant(phrase.brand, text[phrase.start:phrase.end].strip(), phrase.start, phrase.end, given_by(phrase))
    return Environment((*local, words), tuple(context), tuple(origins.items()), tuple(shown))


def same_request_of(model: Model, prompts: Prompts = Prompts()) -> typing.Callable[[str, str], float]:
    """Returns the join decision that ``read`` hands to ``phrases``.

    Args:
        model: The decision model.
        prompts: The wordings; the join wording is the question.

    Returns:
        A function of two neighbouring sentences that returns the share of yes of
        d1 to the join wording, with the two sentences on two lines as the state.
    """
    def same_request(first: str, second: str) -> float:
        state = "\n".join([first.strip(), second.strip()])
        return ask_all(model, state, {"join": YesNo(prompts.render("join"))})["join"]
    return same_request


def read(
    text: str,
    world: World,
    replies: list[str],
    model: Model,
    join: bool = True,
    limits: Limits = Limits(),
    message: Phrase | None = None,
    prompts: Prompts = Prompts(),
    *,
    prior_context: typing.Sequence = (),
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
        prompts: The wordings that d1 receives.
        prior_context: The entities of earlier turns, the nearest first: objects
            with a ``term`` (``turns.Entity``), or terms. They seed the context,
            so that a phrase can name a value or a result of an earlier turn.

    Returns:
        The reading of the message. Each entry of ``requests`` is a
        ``request_entry``.

    Raises:
        ValueError: If the world has a fault, or a parameter that no span of a
            message can fill. The search runs only on a world with no fault.
    """
    problems = world.faults + ungrounded(world)
    if problems:
        raise ValueError("the search does not run on a world with faults: " + "; ".join(problems))
    requests: list[dict] = []
    digests = (world_hash(world), prompts_hash(prompts))

    def recorded(state: str, asked: dict[str, dict]) -> dict[str, dict]:
        answers = model(state, asked)
        requests.append(request_entry(state, asked, answers, *digests))
        return answers

    search = Search(text, world, recorded, limits, prompts)
    message = message or phrases(text, replies[-limits.replies:], world, same_request_of(recorded, prompts) if join else None, limits)
    constants = grounded(text, world)
    finished: dict[int, Phrase] = {}
    for phrase in innermost(message):
        environment = environment_of(phrase, list(finished.values()), constants, text, prior_context)
        if phrase.brand == world.types["Asked"] and environment.local[-1].value:
            done = choose(phrase, environment, search)
        else:
            done = phrase
        finished[phrase.start] = done
    with_terms = fold(lambda phrase: phrase if phrase.inside else finished[phrase.start], message)
    return Reading(uuid.uuid4().hex, text, with_terms, constants, requests, prompts, limits)


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
    line |= {name: getattr(term, name) for name in ("origin", "adopted_by") if getattr(term, name, None)}
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
    return line | {"hole": True, "reason": term.reason}


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
        quotes of earlier replies, and each open hole with its type and the
        reason that it is open.
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
            open_holes += [f"{number}. {phrase.term.function.name}.{path}: {show(hole.type)} ({hole.reason})" for path, hole in holes_of(phrase.term)]
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
    """The state of one thing that a message asked for, after a reply and the executions of the turn.

    A ``Later[...]`` term is never promised by default: what the turn shows decides.
    """

    DONE = "done"
    UNVERIFIED = "claimed, with no execution that shows it"
    OPEN = "not done"
    BLOCKED = "blocked: an execution for it failed"


@dataclasses.dataclass(frozen=True)
class Execution:
    """One side effect recorded during a turn, apart from the prose of the reply.

    Attributes:
        kind: What happened: "command", "test", "file_modified", "file_created",
            "file_diff", or "error" for a record that reports a failure.
        subject: The command line, or the path of the file.
        exit_code: The exit code of a command or a test. None if it has none.
        detail: More of the record: its output or its error, if any.
    """

    kind: str
    subject: str
    exit_code: int | None = None
    detail: str = ""

    PATH_KINDS = ("file_modified", "file_created", "file_diff")
    """The kinds whose subject is a path."""

    @property
    def failed(self) -> bool:
        """True if the record reports an explicit failure: a non-zero exit code, or an error record."""
        return self.kind == "error" or self.exit_code not in (None, 0)

    def described(self) -> str:
        """Returns the record as d1 reads it."""
        code = "" if self.exit_code is None else f" (exit code {self.exit_code})"
        detail = f"\n{self.detail[:300]}" if self.detail else ""
        return f"{self.kind}: {self.subject}{code}{detail}"


def execution_of(given: "Execution | dict") -> Execution:
    """Returns one execution record as an ``Execution``.

    Args:
        given: An ``Execution``, or a dict as a hook records it, such as
            ``{"path": ...}`` (a modified file), ``{"kind": "file_diff", "path": ...}``,
            ``{"kind": "command", "cmd": ..., "exit_code": 0}`` or
            ``{"kind": "error", "detail": ...}``. A dict with an "error" key is an
            error record whatever its kind.

    Returns:
        The execution.
    """
    if isinstance(given, Execution):
        return given
    subject = given.get("path") or given.get("cmd") or given.get("subject") or ""
    kind = "error" if given.get("error") else given.get("kind") or ("file_modified" if "path" in given else "command" if "cmd" in given else "record")
    detail = given.get("detail") or given.get("error") or given.get("output") or ""
    return Execution(kind, str(subject), given.get("exit_code"), str(detail))


@dataclasses.dataclass(frozen=True)
class Checked:
    """The check of a reply against one item of a term: the term, one term of a
    ``Many`` argument, or one field of a record.

    Attributes:
        function: The name of the function of the term.
        item: The part of the term that this check is about, as it reads. None
            if the check is about the whole term.
        state: The state after the reply and the executions.
        share: The share of d1 that the reply says that it is done.
        call: The whole term, as it reads.
        phrase: The words of the phrase that asked for it.
        evidence: Each execution that matched the item, with how it matched:
            by its path, or by the share of d1.
    """

    function: str
    item: str | None
    state: State
    share: float
    call: str = ""
    phrase: str = ""
    evidence: tuple[str, ...] = ()


def items_of(term: Application, text: str) -> list[tuple[str | None, Term]]:
    """Splits a term into the items that a check covers one by one.

    Each term of a ``Many`` argument is an item, and so is each field of a
    record argument (a ``Many`` field gives one item for each of its terms). A
    record inside a field stays one item: its fields name one thing together,
    as the notebook and the number of a cell do.

    Args:
        term: The term of a phrase.
        text: The message.

    Returns:
        Each item as it reads, with its term. One item ``(None, term)`` if the
        term has no ``Many`` argument and no record.
    """
    found: list[tuple[str | None, Term]] = []
    for argument in term.arguments.values():
        match argument:
            case Several(terms=terms):
                found += [(say(one, text), one) for one in terms]
            case Record(fields=fields):
                for name, field in fields.items():
                    parts = field.terms if isinstance(field, Several) else (field,)
                    found += [(f"{name}={say(one, text)}", one) for one in parts]
    return found or [(None, term)]


def needs_evidence(expression: Type) -> bool:
    """Decides whether a term of this type is done only when an execution shows it.

    Args:
        expression: The type of the term.

    Returns:
        True if the type mentions ``Later`` or the brand ``Observed``, at any depth.
    """
    match expression:
        case Applied(constructor=constructor, argument=argument):
            return constructor == LATER or needs_evidence(argument)
        case Brand(name=name, of=inner):
            return name == "Observed" or needs_evidence(inner)
        case Sum(name=name, alternatives=alternatives) if not name:
            return any(needs_evidence(alternative) for alternative in alternatives if not isinstance(alternative, Member))
        case Product(fields=fields):
            return any(needs_evidence(field) for _, field in fields)
    return False


def paths_in(term: Term) -> list[pathlib.Path]:
    """Returns every path constant inside a term."""
    match term:
        case Constant(value=pathlib.Path() as path):
            return [path]
        case Application(arguments=inner) | Record(fields=inner):
            return [path for part in inner.values() for path in paths_in(part)]
        case Several(terms=terms):
            return [path for part in terms for path in paths_in(part)]
    return []


def same_file(named: pathlib.Path, recorded: str) -> bool:
    """Decides whether a path of a message and the path of an execution name one file.

    The two are compared part by part: they are one file if one path ends with
    all the parts of the other, so that "next/world.py" in a message and the
    absolute path that a hook records are the same file.
    """
    first, second = pathlib.PurePath(named).parts, pathlib.PurePath(recorded).parts
    shorter, longer = sorted((first, second), key=len)
    return bool(shorter) and longer[len(longer) - len(shorter):] == shorter


def matches(term: Term, execution: Execution) -> bool | None:
    """Decides by the types of the world whether an execution is evidence for an item.

    A path is a type of the world. If the item has a path constant and the
    execution has a path, the two paths decide. Every other pair, such as a
    member of a sum type and a file, or any term and a command, has no rule in
    the types: the answer is None, and d1 decides with the ``evidence`` wording.

    Args:
        term: The term of the item.
        execution: The execution.

    Returns:
        True or False if the types decide, else None.
    """
    named = paths_in(term)
    if not named or execution.kind not in Execution.PATH_KINDS:
        return None
    return any(same_file(path, execution.subject) for path in named)


def check(
    reading: Reading,
    reply: str,
    model: Model,
    executions: typing.Sequence["Execution | dict"] = (),
    prompts: Prompts | None = None,
    limits: Limits = Limits(),
) -> list[Checked]:
    """Checks a reply and the executions of the turn against each item of a reading.

    For each item, d1 answers the ``did`` wording, with the call and the words
    of the phrase, and reads the message and the reply. Then
    each execution is matched with each item: by the types of the world where
    they decide (``matches``), else by d1 with the ``evidence`` wording, whose
    state is the one execution and whose question names the call and the phrase.

    The state of an item:

    * BLOCKED if the last execution that matches it failed (a non-zero exit
      code, or an error record).
    * OPEN if the share of d1 is below ``limits.yes``.
    * UNVERIFIED if the share is enough but the type of the term mentions
      ``Observed`` or ``Later`` and no execution that succeeded matches it.
    * DONE otherwise.

    Args:
        reading: The reading of the message.
        reply: The reply.
        model: The decision model.
        executions: What ran or changed during the turn, as ``Execution``
            records or as dicts (see ``execution_of``).
        prompts: The wordings that d1 receives. None means the wordings of the reading.
        limits: The numbers that the search uses.

    Returns:
        One check for each item, in the order of the message.
    """
    prompts = prompts or reading.prompts
    records = [execution_of(one) for one in executions]
    questions: dict[str, YesNo] = {}
    evidence_questions: dict[str, YesNo] = {}
    subjects: dict[str, tuple[Phrase, str | None, Term]] = {}
    for phrase in innermost(reading.message):
        if not isinstance(phrase.term, Application):
            continue
        call, words = say(phrase.term, reading.text), reading.text[phrase.start:phrase.end].strip()
        for item, part in items_of(phrase.term, reading.text):
            key = f"{phrase.start} {item}"
            asks = phrase.term.function.asks + (f": {item}" if item else "")
            questions[key] = YesNo(prompts.render("did", asks=asks, call=call, phrase=words))
            if records:
                evidence_questions[key] = YesNo(prompts.render("evidence", asks=asks, call=call, phrase=words))
            subjects[key] = (phrase, item, part)
    if not questions:
        return []
    shares = ask_all(model, f"MESSAGE:\n{reading.text}\n\nREPLY:\n{reply}", questions)

    matched: dict[str, list[tuple[Execution, str]]] = {key: [] for key in subjects}
    for execution in records:
        undecided: dict[str, YesNo] = {}
        for key, (_, _, part) in subjects.items():
            decided = matches(part, execution)
            if decided is None:
                undecided[key] = evidence_questions[key]
            elif decided:
                matched[key].append((execution, "by its path"))
        if undecided:
            answers = ask_all(model, f"EXECUTION:\n{execution.described()}", undecided)
            for key, share in answers.items():
                if share >= limits.yes:
                    matched[key].append((execution, f"d1 {share:.2f}"))

    checked: list[Checked] = []
    for key, (phrase, item, _) in subjects.items():
        found = matched[key]
        if found and found[-1][0].failed:
            state = State.BLOCKED
        elif shares[key] < limits.yes:
            state = State.OPEN
        elif needs_evidence(type_of(phrase.term)) and not any(not execution.failed for execution, _ in found):
            state = State.UNVERIFIED
        else:
            state = State.DONE
        evidence = tuple(f"{execution.kind}: {execution.subject} ({how})" for execution, how in found)
        call, words = say(phrase.term, reading.text), reading.text[phrase.start:phrase.end].strip()
        checked.append(Checked(phrase.term.function.name, item, state, round(shares[key], 3), call, words, evidence))
    return checked


# ---- The gate for a change of the world or of the wordings ----------------------


@dataclasses.dataclass(frozen=True)
class Case:
    """One approved regression case: a message and what each of its phrases must read as.

    Attributes:
        message: The message.
        expected: The ``say`` text of the term of each phrase, in order. "nothing"
            or "none" for a phrase that d1 must read as no function, and "quote"
            for a quote of an earlier reply.
        replies: The earlier replies that the message may quote.
        holes: The number of open holes that the approved reading has.
        join: If True, d1 decides whether neighbouring sentences are one request,
            as the product path (``turns.start_turn`` and the hook) reads every
            message. A case is approved with the reading of the product path,
            so it is True unless the case is about a later stage of the search.
        note: Why the case is in the set.
    """

    message: str
    expected: tuple[str, ...]
    replies: tuple[str, ...] = ()
    holes: int = 0
    join: bool = True
    note: str = ""


def golden(file: pathlib.Path) -> list[Case]:
    """Loads the approved regression cases from a JSON file such as next/golden.json. A case with no "join" is read with join on."""
    data = json.loads(pathlib.Path(file).read_text())
    return [Case(one["message"], tuple(one["expected"]), tuple(one.get("replies", ())), one.get("holes", 0), one.get("join", True), one.get("note", "")) for one in data["cases"]]


def reads_as(reading: Reading) -> list[str]:
    """Returns what each phrase of a reading reads as, in the terms of ``Case.expected``."""
    return [say(phrase.term, reading.text) if phrase.term else phrase.choice.best if phrase.choice else "quote" for phrase in innermost(reading.message)]


@dataclasses.dataclass(frozen=True)
class Gate:
    """The decision about a proposed change of world.py or of the wordings.

    Attributes:
        accepted: True if the proposed world has no fault, every approved case
            reads as it was approved, and no more holes stay open.
        faults: The faults of the proposed world.
        lost: Each phrase of an approved case that now reads otherwise: an
            obligation that is gone, bound to another term, or invented.
        mean_bits: The average bits per decision of d1 on the approved cases and
            the logged lines, with the proposed world. Diagnostic only: d1 can be
            sure of a wrong reading. None if nothing was replayed.
        decision_count: The number of decisions of d1 in that average.
        unresolved_holes: The open holes on the approved cases, with the proposed world.
        preserved_obligations: The terms of the approved cases that read as approved.
        world_hash: The hash of the proposed world.
        prompts_hash: The hash of the wordings.
    """

    accepted: bool
    faults: list[str]
    lost: list[str]
    mean_bits: float | None
    decision_count: int
    unresolved_holes: int
    preserved_obligations: int
    world_hash: str
    prompts_hash: str


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


def gate(
    proposed: World,
    golden_cases: list[Case],
    logged_lines: list[dict],
    model: Model,
    prompts: Prompts = Prompts(),
    limits: Limits = Limits(),
) -> Gate:
    """Decides whether a proposed change of world.py or of the wordings is accepted.

    The approved cases decide; the bits of d1 do not. A proposed world that
    reads "Redesign the mod." as nothing, with d1 as sure as before, loses an
    obligation and is rejected.

    Args:
        proposed: The world with the change.
        golden_cases: The approved regression cases (see ``golden``).
        logged_lines: Lines of the log in form 4, from ``record``. They are
            replayed on their own phrases for the diagnostic bits only: a logged
            reading was never approved.
        model: The decision model.
        prompts: The wordings to read with.
        limits: The numbers that the search uses.

    Returns:
        The decision. It is rejected if the proposed world has a fault (with no
        call to d1), if any phrase of an approved case reads otherwise than
        approved, or if more holes stay open than in the approved readings.
    """
    hashes = (world_hash(proposed), prompts_hash(prompts))
    faults = proposed.faults + ungrounded(proposed)
    if faults:
        return Gate(False, faults, [], None, 0, 0, 0, *hashes)
    lost: list[str] = []
    replayed: list[float] = []
    holes = preserved = 0
    for case in golden_cases:
        reading = read(case.message, proposed, list(case.replies), model, case.join, limits, prompts=prompts)
        got = reads_as(reading)
        replayed += recorded_bits(record(reading))
        holes += sum(len(holes_of(phrase.term)) for phrase in innermost(reading.message))
        if len(got) != len(case.expected):
            lost.append(f"{case.message!r}: {len(case.expected)} phrases approved, {len(got)} read: {got}")
        for number, (wanted, now) in enumerate(zip(case.expected, got), 1):
            if wanted != now:
                lost.append(f"{case.message!r} phrase {number}: approved {wanted}, now {now}")
            elif wanted not in ("nothing", "none", "quote"):
                preserved += 1
    for line in logged_lines:
        reading = read(line["text"], proposed, [], model, False, limits, recorded_phrases(line, proposed), prompts)
        replayed += recorded_bits(record(reading))
    baseline = sum(case.holes for case in golden_cases)
    accepted = not lost and holes <= baseline
    mean = sum(replayed) / len(replayed) if replayed else None
    return Gate(accepted, [], lost, mean, len(replayed), holes, preserved, *hashes)
