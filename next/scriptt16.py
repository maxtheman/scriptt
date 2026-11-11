"""The reader of scriptt next: type-directed synthesis over the world of a folder.

The world (``agree.World``) is a closed type system. Reading a message means
building well-typed terms from it:

1. Lexical grounding. The message unfolds into phrases, and each span of text
   that names a value of a type of the world becomes a constant term. The
   phrases form a flat grouping: quotes of earlier replies, then sentences;
   ``proposed`` labels where each starts. Shared references between terms are
   the links between phrases.
2. Synthesis. For each phrase of the user, d1 chooses the operations that the
   phrase asks for (a function, "none": no function fits, or "nothing": a
   remark, a reason, a rule or a greeting). Each parameter of a function is a
   hole with a type. ``candidates`` lists the terms that fit it: values and
   results in scope, new applications of other functions, and a record built
   from its fields. d1 chooses among them, or none of them, even when there is
   one; d1's choice is what licenses a new application.
3. Judgments, each derived, none stored as a flag: ``diagnostics`` (validity),
   ``complete`` (no hole at any depth), ``pending`` (a Later result at any
   depth) and ``check`` (fulfillment against supplied evidence).

What is a model judgment and what is a rule
--------------------------------------------
d1 decides: the operations of a phrase, every binding (also of a single
candidate), each member of a Many, the absence of a Maybe, and whether two
sentences are one request. Rules decide: grounding of spans, the candidate
lists and their order, the bound ``Limits.offered`` (the excess is recorded as
cut), a record built from its fields when no whole value is in scope, a hole
with reason "no candidate" when nothing fits (no question), and every
judgment above. Every decision is kept in ``Reading.decisions`` with its
state, questions, options, answers, phrase, operation, path, offered and cut
candidates.

States and transitions
----------------------
The API is plain functions over ``Reading``; a reading is never changed in place.

* ``read(text, world, replies, model)`` -> a reading (the current reading).
  ``diagnostics(reading)`` judges it; an invalid model answer gives an
  unresolved operation or a hole with reason "invalid answer" and a diagnostic.
* ``inspect(reading, number, path)`` -> the term, its type, the definition and
  the decision at that place. View only.
* ``edit(reading, number, path, value)`` -> ``(draft, diagnostics)``. The draft
  is a new reading; with diagnostics the caller keeps the base. A preview is
  this returned value; cancelling it is keeping the base. ``value`` None
  removes the binding; ``Hole(place_type(...), "cleared")`` clears it.
* ``correct(reading, number, path, value)`` is an edit that is also kept in
  ``Reading.corrections``.
* ``save(reading, store)`` appends ``record(reading)`` to a file. If the write
  fails it raises, and the caller still holds the draft.
* ``saved(store)`` lists the snapshots; ``load(line, world)`` -> ``(reading,
  diagnostics)`` rebuilds one without asking d1, or reports an identity
  mismatch when the world differs. Restoring is loading an earlier snapshot.
* ``rerun(line, world, model)`` reads the saved source again and re-applies
  each correction, or marks it invalidated with the reason.
* ``gate(source, folder, lines, model, active, active_source)`` proposes a
  world: faults, an empty corpus, or an accepted obligation changed, lost or
  added keep the active world and its corpus; the caller keeps its draft.
  An activated world returns the corpus read again under it.
* ``check(reading, reply, artifacts, criteria, model)`` -> one outcome per
  obligation and criterion, from evidence only, and a verdict.

Out of scope: running operations, the old browser board, teaching d1 from
corrections and changing world.py automatically.
"""

import copy
import dataclasses
import difflib
import hashlib
import itertools
import json
import math
import pathlib
import typing
import unicodedata
import uuid

import harness as shipped
from agree import CONSTRUCTORS, LATER, MANY, MAYBE, Applied, Base, Brand, Function, Member, Product, Star, Sum, Type, World, identity, is_subtype, kind_of, loads, show

type Model = typing.Callable[[str, dict[str, dict]], dict[str, dict]]
"""The decision model d1: takes a state and questions, returns one answer for each question."""

JOIN = "Is the second text part of the same request as the first text?"
ALSO = "The text asks the reader to {done}. Does it also ask the reader to do something else?"
NONE_OF_THESE = "the text names none of these"
ABSENT = "the text leaves it out on purpose"
LEFT_OUT = "The text asks the reader to {asks}. Does the text leave out the {role} on purpose?"
"""Wordings that 0.1.6 and this repair add. None has a measurement with the real d1."""

PASS, FAIL, UNVERIFIED = "PASS", "FAIL", "UNVERIFIED"

NONE, NOTHING = "(none)", "(nothing)"
ELSE = {NONE: shipped.ELSE["none"], NOTHING: shipped.ELSE["nothing"]}
"""The two answers of an operation question that are no function: d1's legacy "none" and "nothing",
with ids that no function name can take, so no declaration of the world can turn an abstention into a call."""


@dataclasses.dataclass(frozen=True)
class Limits:
    """The numbers that the search uses. None of them has a measurement yet.

    Attributes:
        run: The number of consecutive words that an earlier reply must share
            with the message for the run to count as a quote of that reply.
        replies: The number of earlier replies that the search compares with the message.
        offered: The largest number of candidates that d1 receives for one hole; the rest are recorded as cut.
        depth: The largest number of function applications inside one argument.
        yes: The smallest share at which a yes of d1 counts.
        operations: The largest number of operations that one phrase can ask for.
    """

    run: int = 6
    replies: int = 8
    offered: int = 8
    depth: int = 1
    yes: float = 0.5
    operations: int = 3


# ---- Questions for d1 -------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class YesNo:
    """A question that d1 answers with the share of yes."""

    instructions: str


@dataclasses.dataclass(frozen=True)
class OneOf:
    """A question that d1 answers by choosing one option, by its identifier."""

    instructions: str
    options: dict[str, str]


@dataclasses.dataclass(frozen=True)
class Choice:
    """The answer of d1 to a OneOf question.

    Attributes:
        shares: The share that d1 gave each option, by its identifier.
        best: The identifier with the largest share. None if the answer was
            missing, malformed or named an option that was not offered.
    """

    shares: dict[str, float]
    best: str | None


def rendered(template: object) -> str:
    """Returns the text of a wording of the shipped harness, with its slots filled."""
    return shipped.yes(template)["instructions"]


def answer(question: YesNo | OneOf, received: object) -> Choice | float | None:
    """Validates one answer of d1. Returns a Choice, a share of yes, or None (YesNo) / best None (OneOf) if it is invalid."""
    if isinstance(question, OneOf):
        shares = received.get("probabilities") if isinstance(received, dict) else None
        valid = isinstance(shares, dict) and shares and set(shares) <= set(question.options) and all(share(one) for one in shares.values()) and abs(sum(shares.values()) - 1) < 0.01
        return Choice(shares, max(shares, key=shares.get)) if valid else Choice({}, None)
    found = received.get("p_true") if isinstance(received, dict) else None
    return found if share(found) else None


def share(value: object) -> bool:
    """Decides whether a value is a share: a finite number from 0 to 1."""
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1


def decided(search: "Search", about: dict) -> dict:
    """Records one decision of the search and returns it, for the caller to complete with its choice.

    A decision is a dict: by ("model" or "rule"), rule (the declared rule of a
    decision by rule), state, asked (each question as sent), answers (d1's raw
    answers), function and path of the hole, operation (its number once it
    exists), offered and cut (the candidates), and chosen: a candidate, a list
    of candidates for a Many, a function name, "absent", "none", the two ids
    of ``ELSE``, or None for an invalid answer.
    """
    decision = {"by": "model", "rule": "", "state": "", "asked": {}, "answers": None, "function": None, "operation": None, "path": None, "offered": [], "cut": [], "chosen": None} | about
    search.decisions.append(decision)
    return decision


def ask(search: "Search", state: str, questions: dict[str, YesNo | OneOf], about: dict) -> tuple[dict[str, Choice | float | None], dict]:
    """Sends several questions about one state to d1 in one request, and records it as a decision.

    Returns:
        The validated answer under each key, and the decision, whose ``chosen`` the caller sets.
    """
    sent: dict[str, dict] = {}
    for key, question in questions.items():
        if isinstance(question, OneOf):
            sent[key] = {"type": "choice", "instructions": question.instructions, "options": [{"id": one, "description": text} for one, text in question.options.items()]}
        else:
            sent[key] = {"type": "boolean", "instructions": question.instructions}
    decision = decided(search, about | {"state": state, "asked": sent})
    decision["answers"] = received = search.model(state, sent)
    return {key: answer(question, received.get(key) if isinstance(received, dict) else None) for key, question in questions.items()}, decision



# ---- Terms ------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Constant:
    """A value that the message gives: a span of text with a type of the world.

    Attributes:
        type: The type of the value.
        value: The value: a member of a sum type, a number, a path, or the words of a phrase.
        start: The place of its first character in the message. -1 for a member
            that d1 may choose and the message has no span for.
        end: The place after its last character.
    """

    type: Type
    value: Member | int | pathlib.Path | str
    start: int
    end: int


@dataclasses.dataclass(frozen=True, eq=False)
class Application:
    """A function of the world applied to one term for each parameter: one operation instance.

    Equality is identity: two applications that read the same are two operations.

    Attributes:
        function: The function.
        arguments: The term for each parameter, by name.
        number: The place of this operation among the obligations of its reading,
            the same through save and load; a reference to its result is the same
            object in memory and ``{"ref": number}`` in a record. None for a
            candidate that d1 has not chosen yet.
    """

    function: Function
    arguments: dict[str, "Term"]
    number: int | None = None


@dataclasses.dataclass(frozen=True)
class Record:
    """A value of a product type: one term for each field."""

    product: Product
    fields: dict[str, "Term"]


@dataclasses.dataclass(frozen=True)
class Several:
    """A value of ``Many[T]``: the terms chosen for it. No term is an explicit empty collection."""

    element: Type
    terms: tuple["Term", ...]


@dataclasses.dataclass(frozen=True)
class Empty:
    """A value of ``Maybe[T]`` that d1 answered is deliberately absent."""

    type: Type


@dataclasses.dataclass(frozen=True)
class Hole:
    """A place in a term where a term of a known type is missing.

    Attributes:
        type: The type of the missing term.
        reason: "rejected" (d1 chose none of the candidates), "no candidate"
            (nothing in scope fits), "bounded" (d1 rejected the candidates it was
            offered, and the bound cut others), "invalid answer" (d1's answer
            was malformed) or "cleared" (an edit). Empty in a candidate template.
    """

    type: Type
    reason: str = ""


type Term = Constant | Application | Record | Several | Empty | Hole


@dataclasses.dataclass(frozen=True)
class Unresolved:
    """An operation that a phrase asks for and that no function of the world gives: no term, no guessed type.

    Attributes:
        number: Its place among the obligations of the reading.
        reason: "rejected" (d1 answered that no function fits) or "invalid answer".
    """

    number: int
    reason: str


def type_of(term: Term) -> Type:
    """Returns the declared type of a term. Whether it waits on work is ``pending``, not its type."""
    match term:
        case Application(function=function):
            return function.result
        case Record(product=product):
            return product
        case Several(element=element):
            return Applied(MANY, element)
    return term.type


def later(expression: Type) -> bool:
    """Returns True for a type ``Later[T]``."""
    return isinstance(expression, Applied) and expression.constructor == LATER


def fills(term: Term, goal: Type) -> bool:
    """Decides whether a term can fill a hole: its type, or T of its Later[T], is a subtype of the goal."""
    given = type_of(term)
    return is_subtype(given, goal) or (later(given) and is_subtype(given.argument, goal))


def inside(term: Term) -> list[Term]:
    """Returns the terms directly inside a term."""
    match term:
        case Application(arguments=parts) | Record(fields=parts):
            return list(parts.values())
        case Several(terms=terms):
            return list(terms)
    return []


def pending(term: Term) -> bool:
    """Decides whether a term's value is not available yet: an application whose own result is deferred, or anything holding a pending value at any depth."""
    return deferred(term) or waiting(term)


def deferred(term: Term) -> bool:
    """Decides whether an operation's own result comes later: its declared result is Later."""
    return isinstance(term, Application) and later(term.function.result)


def waiting(term: Term) -> bool:
    """Decides whether a term holds an input that is not available yet, at any depth."""
    return any(pending(part) for part in inside(term))


def complete(term: Term) -> bool:
    """Decides whether a term has no hole and no missing argument or field at any depth, through the operations it refers to."""
    places = dict(term.function.parameters) if isinstance(term, Application) else dict(term.product.fields) if isinstance(term, Record) else {}
    given = term.arguments if isinstance(term, Application) else term.fields if isinstance(term, Record) else {}
    return not isinstance(term, Hole) and places.keys() <= given.keys() and all(complete(part) for part in inside(term))


def sound(reading: "Reading", term: Application) -> bool:
    """Decides whether an operation is valid and complete, with every operation it refers to valid too."""
    faulty = {one[0] for one in diagnostics(reading)}
    return complete(term) and not any(one.number in faulty for one in operations(term, set()))


def ready(reading: "Reading", term: Application) -> bool:
    """Decides whether an operation can start now: sound, with no input that is not available yet.

    Its own result may still come later (``deferred``): redesign(mod) can start,
    and show(redesign(mod)) must wait. Readiness is not fulfillment.
    """
    return sound(reading, term) and not waiting(term)


# ---- Part 2: lexical grounding ----------------------------------------------


@dataclasses.dataclass(frozen=True)
class Phrase[Inner]:
    """A phrase of the message, with what stands at each place inside it.

    Phrase is a functor: ``map`` applies a function to each inner place and
    keeps the phrase. ``unfold`` and ``fold`` build on ``map``.

    Attributes:
        start: The place of its first character in the message.
        end: The place after its last character.
        brand: The brand of the text of the phrase. None for a whole message
            that holds phrases of several brands.
        inside: What stands at each inner place.
        starts_by: The rule that set the start of the phrase.
        quotes: For a quote, the index of the earlier reply it quotes.
        terms: The operations that the phrase asks for, in the order d1 named
            them: applications, or an unresolved operation. Empty for a quote,
            and for a phrase that d1 answered asks for nothing (its relation
            to the request is context).
    """

    start: int
    end: int
    brand: typing.Any
    inside: tuple[Inner, ...] = ()
    starts_by: str = ""
    quotes: int | None = None
    terms: tuple[Application | Unresolved, ...] = ()

    def map(self, function: typing.Callable) -> "Phrase":
        """Returns the phrase with the function applied to each inner place."""
        return dataclasses.replace(self, inside=tuple(function(inner) for inner in self.inside))


def unfold(cut: typing.Callable[[Phrase], Phrase], phrase: Phrase) -> Phrase:
    """Grows the phrases of a message from one phrase.

    Raises:
        ValueError: If ``cut`` returns an inner phrase that is as long as the
            phrase that holds it, which guarantees that the unfold ends.
    """
    grown = cut(phrase)
    if any(inner.end - inner.start >= phrase.end - phrase.start for inner in grown.inside):
        raise ValueError(f"a cut returned an inner phrase as long as its phrase: {phrase}")
    return grown.map(lambda inner: unfold(cut, inner))


def fold(combine: typing.Callable[[Phrase], object], phrase: Phrase) -> object:
    """Collapses the phrases of a message to one result, from the innermost out."""
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


def written(text: str, replies: list[str], least: int) -> list[tuple[int, int, int]]:
    """Finds the parts of a message that quote an earlier reply.

    Compares the message with the replies in the log. Asks no model.

    Args:
        text: The message.
        replies: The earlier replies.
        least: The number of consecutive words that the message must share with
            a reply for the run to count as a quote.

    Returns:
        The start and the end of each quote, and the index of the reply it
        quotes, in order. A quote includes the opening sign and the closing
        signs that touch it.
    """
    word_places = places(text)
    word_indexes = [index for index, (start, _) in enumerate(word_places) if text[start].isalnum()]
    normal = lambda word: word.lower().replace("’", "'")
    message_words = [normal(text[slice(*word_places[index])]) for index in word_indexes]
    category = lambda index: unicodedata.category(text[word_places[index][0]])
    touches = lambda before, after: word_places[before][1] == word_places[after][0]
    opens = lambda index: category(index) in ("Ps", "Pi") or text[word_places[index][0]] in "\"'`*"

    runs: list[tuple[int, int, int]] = []
    for number, reply in enumerate(replies):
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
            runs.append((word_places[first][0], word_places[last][1], number))

    merged: list[tuple[int, int, int]] = []
    for start, end, number in sorted(runs):
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]), merged[-1][2])
        else:
            merged.append((start, end, number))
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
    ``Asked`` for the text of the user. A message that is one whole quote is one
    Written phrase.

    Args:
        text: The message.
        replies: The earlier replies in the log, the oldest first.
        world: The world.
        same_request: A function that returns the share of d1 that two
            neighbouring phrases are one request. If given, d1 decides every
            start that the end of a sentence proposed.
        limits: The numbers that the search uses.

    Returns:
        The message as one phrase, with its phrases inside it.
    """
    asked, quoted = world.types["Asked"], world.types["Written"]
    compared = replies[-limits.replies:]
    quotes = {(start, end): len(replies) - len(compared) + reply for start, end, reply in written(text, compared, limits.run)}
    starts = proposed(text)

    def cut(phrase: Phrase) -> Phrase:
        if phrase.brand is None and quotes:
            edges = sorted({phrase.start, phrase.end, *(edge for quote in quotes for edge in quote)})
            parts: list[Phrase] = []
            for start, end in zip(edges, edges[1:]):
                if (start, end) in quotes:
                    parts.append(Phrase(start, end, quoted, starts_by="the log", quotes=quotes[(start, end)]))
                elif text[start:end].strip():
                    parts.append(Phrase(start, end, asked, starts_by="the phrase before it ends" if start else "the first word"))
            # White space between two phrases belongs to the phrase after it.
            joined = [dataclasses.replace(parts[0], start=phrase.start)]
            for part in parts[1:]:
                joined.append(dataclasses.replace(part, start=joined[-1].end))
            joined[-1] = dataclasses.replace(joined[-1], end=phrase.end)
            return cut(joined[0]) if len(joined) == 1 else dataclasses.replace(phrase, inside=tuple(joined))
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
        local: The terms that the phrase itself gives: the results of its earlier
            operations, its constants, and its own words.
        context: The terms from before the phrase, the nearest first: earlier
            results, constants and words.
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
        decisions: Every decision of the search, d1's and the rules', in order.
        numbers: The numbers of the obligations, in the order they are made.
    """

    text: str
    world: World
    model: Model
    limits: Limits
    decisions: list[dict]
    numbers: typing.Iterator[int]


def say(term: Term | None) -> str:
    """Returns a term as a call that a person can read. Display only: never used to compare terms."""
    match term:
        case Constant(value=Member(words=words)):
            return repr(words)
        case Constant(value=str(words)):
            return repr(" ".join(words.split()))
        case Constant(value=value):
            return repr(str(value))
        case Application(function, arguments):
            shown = ", ".join(f"{name}={say(argument)}" for name, argument in arguments.items() if not isinstance(argument, Empty))
            return f"{function.name}({shown})"
        case Record(product, fields):
            return f"{product.name}({', '.join(f'{name}={say(field)}' for name, field in fields.items())})"
        case Several(terms=terms):
            return f"[{', '.join(say(one) for one in terms)}]"
    return "..."


def candidates(goal: Type, environment: Environment, world: World, depth: int, applying: Function | None = None) -> list[Term]:
    """Enumerates the terms that can fill a hole of a type.

    * Every term in scope whose type fits: the phrase's own first, then the
      earlier ones, the nearest first. An earlier result and the original value
      it was made from are both listed: compatibility proves no replacement.
    * A new application of every other function whose result fits and whose
      required parameters each have a value in scope. It is only a candidate:
      d1's choice of it is what licenses the work.
    * For a product type, or a product alternative of a sum, a record to build
      from its fields.

    The order is the order of this list; the bound ``Limits.offered`` cuts its end.
    """
    found: list[Term] = []
    for term in (*environment.local, *environment.context):
        # A constant is a value: the same member, number or path at two places in the text is one candidate.
        same = isinstance(term, Constant) and any(isinstance(one, Constant) and (one.type, one.value) == (term.type, term.value) for one in found)
        if fills(term, goal) and not same:
            found.append(term)
    in_scope = lambda wanted: any(fills(term, wanted) for term in (*environment.local, *environment.context))
    if depth > 0:
        for function in world.functions.values():
            required = [parameter for _, parameter in function.parameters if not (isinstance(parameter, Applied) and parameter.constructor == MAYBE)]
            template = Application(function, {name: Hole(parameter) for name, parameter in function.parameters})
            if function != applying and required and fills(template, goal) and all(in_scope(parameter) for parameter in required):
                found.append(template)
    products = [goal] if isinstance(goal, Product) else [one for one in getattr(goal, "alternatives", ()) if isinstance(one, Product)]
    return found + [Record(product, {name: Hole(field) for name, field in product.fields}) for product in products]


def members(goal: Type) -> list[Constant]:
    """Returns each member of a sum, and of the sums among its alternatives, as a constant of its own sum with no span."""
    alternatives = getattr(goal, "alternatives", ())
    return [Constant(goal, one, -1, -1) for one in alternatives if isinstance(one, Member)] + [found for one in alternatives if isinstance(one, Sum) for found in members(one)]


def solve(goal: Type, environment: Environment, search: Search, state: str, path: str, applying: Function, depth: int) -> Term:
    """Synthesizes a term for a hole, and asks d1 to choose it.

    * ``Many[T]``: a whole collection in scope is offered first (d1 chooses it
      or none). Else d1 answers yes or no for each candidate of T, and whether
      the text leaves the collection out on purpose, in one request. The yes
      candidates are the collection; a deliberate leaving out is an explicit
      empty collection; neither is a rejected hole. With no candidate in scope
      the hole has reason "no candidate", by rule.
    * ``Maybe[T]``: d1 chooses a whole optional value or a candidate of T, the
      absence option (``Empty``) or none of them (a hole). d1 is asked even
      with no candidate in scope.
    * Every other type: d1 chooses a candidate or none of them, even when there
      is one. A record with no whole value in scope is built from its fields
      with no question. A sum of members with no candidate offers its members.

    Returns:
        The term; a ``Hole`` of the goal type with its reason if there is none.
    """
    limits, role = search.limits, path.rsplit(".", 1)[-1].replace("_", " ")
    many = isinstance(goal, Applied) and goal.constructor == MANY
    optional = isinstance(goal, Applied) and goal.constructor == MAYBE
    inner = goal.argument if many or optional else goal
    whole = candidates(goal, environment, search.world, depth, applying) if many or optional else []  # values of the constructed type itself
    found = candidates(inner, environment, search.world, depth, applying)
    about = {"function": applying.name, "path": path, "state": state}
    if many and whole:
        answers, decision = ask(search, state, {"which": OneOf(rendered(shipped.NAMES(role, applying.asks)), {str(index): say(term)[:200] for index, term in enumerate(whole[:limits.offered])} | {"none": NONE_OF_THESE})},
                                about | {"offered": whole[:limits.offered], "cut": whole[limits.offered:]})
        best = answers["which"].best
        decision["chosen"] = whole[int(best)] if best and best.isdigit() else best
        if best is None:
            return Hole(goal, "invalid answer")
        if best != "none":
            return made(whole[int(best)], environment, search, state, path, applying, depth)
    found = (whole if optional else []) + found
    if not many and not optional and len(found) == 1 and isinstance(found[0], Record):
        decided(search, about | {"by": "rule", "rule": "a record with no whole value in scope is built from its fields", "offered": found, "chosen": found[0]})
        return made(found[0], environment, search, state, path, applying, depth)
    found = found or ([] if many or optional else members(inner))
    if not found and not optional:
        decided(search, about | {"by": "rule", "rule": "nothing in scope fits the hole, so nobody is asked", "chosen": "none"})
        return Hole(goal, "no candidate")
    offered, cut = found[:limits.offered], found[limits.offered:]
    about |= {"offered": offered, "cut": cut}
    rejected = "bounded" if cut else "rejected" if found else "no candidate"
    if many:
        questions = {str(index): YesNo(rendered(shipped.IS(say(term)[:200], role, applying.asks))) for index, term in enumerate(offered)}
        shares, decision = ask(search, state, questions | {"absent": YesNo(LEFT_OUT.format(asks=applying.asks, role=role))}, about)
        if None in shares.values():
            return Hole(goal, "invalid answer")
        decision["chosen"] = [term for index, term in enumerate(offered) if shares[str(index)] >= limits.yes] or ("absent" if shares["absent"] >= limits.yes else "none")
        if isinstance(decision["chosen"], str):
            return Several(inner, ()) if decision["chosen"] == "absent" else Hole(goal, rejected)
        return Several(inner, tuple(made(term, environment, search, state, path, applying, depth) for term in decision["chosen"]))
    options = {str(index): say(term)[:200] for index, term in enumerate(offered)} | ({"absent": ABSENT} if optional else {}) | {"none": NONE_OF_THESE}
    answers, decision = ask(search, state, {"which": OneOf(rendered(shipped.NAMES(role, applying.asks)), options)}, about)
    best = answers["which"].best
    decision["chosen"] = offered[int(best)] if best and best.isdigit() else best
    if best is None:
        return Hole(goal, "invalid answer")
    if best in ("absent", "none"):
        return Empty(goal) if best == "absent" else Hole(goal, rejected)
    return made(offered[int(best)], environment, search, state, path, applying, depth)


def made(term: Term, environment: Environment, search: Search, state: str, path: str, applying: Function, depth: int) -> Term:
    """Returns a chosen candidate as a term: a new application or a record is synthesized; a value in scope is itself."""
    if isinstance(term, Application) and term.number is None:
        return applied(term.function, environment, search, state, depth - 1)
    if isinstance(term, Record) and all(isinstance(field, Hole) and not field.reason for field in term.fields.values()):
        return Record(term.product, {name: solve(field, environment, search, state, f"{path}.{name}", applying, depth) for name, field in term.product.fields})
    return term


def applied(function: Function, environment: Environment, search: Search, state: str, depth: int) -> Application:
    """Applies a function: synthesizes one term for each parameter, then numbers the operation and its decisions."""
    first = len(search.decisions)
    arguments = {name: solve(parameter, environment, search, state, name, function, depth) for name, parameter in function.parameters}
    application = Application(function, arguments, next(search.numbers))
    for decision in search.decisions[first:]:
        if decision["operation"] is None:
            decision["operation"] = application.number
    return application


def choose(phrase: Phrase, environment: Environment, search: Search) -> Phrase:
    """Asks d1 which operations a phrase asks for, and synthesizes each.

    The first question offers every function, "none" (something that no
    function fits) and "nothing" (a remark, a reason, a rule or a greeting).
    After each operation, function or not, d1 is asked whether the phrase also
    asks for something else. A function the phrase already asked for is
    offered again only if the phrase gives a value for one of its places that
    it has not taken; an answer that still repeats an operation of the phrase
    with the same values is the same request again: the phrase asks for no
    more, and that decision names no operation. (Two unknown operations in a
    row stay two: nothing tells them apart.) "none" gives an unresolved operation, and the
    asking goes on; an invalid answer gives one and ends it. Past
    ``Limits.operations``, one more answer that is not "nothing" is kept as an
    unresolved operation with reason "bounded". A later operation can use the
    results of an earlier one.
    """
    state = search.text[phrase.start:phrase.end].strip()
    terms: list[Application | Unresolved] = []
    results: list[Application] = []
    meant = lambda term: (term.function.name, {path: meant_value(one) for path, one in bindings(term).items()}) if isinstance(term, Application) else None


    def again(function: Function) -> bool:
        """Decides whether a function the phrase already asked for could apply once more: the phrase gives a value for one of its places that it has not taken."""
        taken = [meant_value(value) for term in terms if isinstance(term, Application) and term.function == function for value in bindings(term).values()]
        places = [kind.argument if isinstance(kind, Applied) and kind.constructor in (MAYBE, MANY) else kind for _, kind in function.parameters]
        return any(fills(one, kind) and meant_value(one) not in taken for kind in places for one in environment.local)

    meant_value = lambda one: value_of(one, {id(made): made.number for made in results})
    while True:
        done = [term.function.asks if isinstance(term, Application) else ELSE[NONE] for term in terms]
        key = "also" if terms else "what"
        asked_for = {term.function.name for term in terms if isinstance(term, Application)}
        functions = {name: function.asks for name, function in search.world.functions.items() if name not in asked_for or again(function)}
        answers, decision = ask(search, state, {key: OneOf(ALSO.format(done="; ".join(done)) if done else shipped.WHAT, functions | ELSE)}, {})
        decision["chosen"] = best = chosen(answers[key])
        if best == NOTHING:
            break
        if len(terms) == search.limits.operations:
            term = Unresolved(next(search.numbers), "bounded")
        elif best in search.world.functions:
            term = applied(search.world.functions[best], Environment((*reversed(results), *environment.local), environment.context), search, state, search.limits.depth)
        else:
            term = Unresolved(next(search.numbers), "invalid answer" if best is None else "rejected")
        if isinstance(term, Application) and meant(term) in [meant(one) for one in terms]:
            break  # the same operation with the same values: the same request again, so the phrase asks for no more
        decision["operation"] = term.number
        terms.append(term)
        results += [one for one in operations(term, {id(one) for one in results}) if isinstance(one, Application)]
        if best is None or len(terms) > search.limits.operations:
            break
    return dataclasses.replace(phrase, terms=tuple(terms))


def chosen(choice: Choice) -> str | None:
    """Decides an operation question from d1's shares, by the rule of the 0.1.6 harness (measured there on recorded messages).

    A function counts only if its share is greater than "(none)" and "(nothing)"
    together; else "(none)" (a request outside the world) if its share is at
    least one half; else "(nothing)". None for an invalid answer. The same rule
    decides the first question of a phrase and every "also".
    """
    if choice.best is None:
        return None
    shares = choice.shares
    top = max((name for name in shares if name not in ELSE), key=shares.get, default=None)
    if top and shares[top] > shares.get(NONE, 0) + shares.get(NOTHING, 0):
        return top
    return NONE if shares.get(NONE, 0) >= 0.5 else NOTHING


def operations(term: Application | Unresolved | Term, seen: set[int]) -> list[Application | Unresolved]:
    """Returns the operations inside a term and the term itself, each once, an input before the operation that consumes it."""
    if id(term) in seen:
        return []
    found = [one for part in inside(term) for one in operations(part, seen)]
    if isinstance(term, Application | Unresolved):
        seen.add(id(term))
        found.append(term)
    return found


@dataclasses.dataclass(frozen=True)
class Reading:
    """The result of the search for one message.

    Attributes:
        id: An identifier of the reading.
        text: The message.
        message: The message as one phrase, with its phrases and their operations inside it.
        constants: Every constant that the message gives, bound or not.
        decisions: Each decision of the search, d1's and the rules' (see ``decided``).
        world: The identity of the world it was read against (``agree.identity``).
        corrections: Each accepted manual binding: operation, function, phrase,
            path, others, value (as a term record), refers, status ("retained"
            or "invalidated") and reason.
        base: The snapshot of the store that this reading was loaded from or saved as; None for a new reading.
        fulfillment: The outcomes of the last ``check``, or None if none ran since the last edit.
    """

    id: str
    text: str
    message: Phrase
    constants: list[Constant]
    decisions: list[dict]
    world: str
    corrections: list[dict] = dataclasses.field(default_factory=list)
    base: str | None = None
    fulfillment: list | None = None


def read(text: str, world: World, replies: list[str], model: Model, join: bool = True, limits: Limits = Limits(),
         message: Phrase | None = None) -> Reading:
    """Runs the search on one message.

    Args:
        text: The message.
        world: The world.
        replies: The replies in the log from before the message, the oldest first.
        model: The decision model.
        join: If True, d1 decides whether two neighbouring sentences are one request.
        limits: The numbers that the search uses.
        message: The phrases of the message, if a record already has them.
            The search then makes no new cut and asks d1 no join question.

    Raises:
        ValueError: If the world has a fault.
    """
    if world.faults:
        raise ValueError("the search does not run on a world with faults: " + "; ".join(text for _, _, text in world.faults))
    search = Search(text, world, model, limits, [], itertools.count())

    def same_request(first: str, second: str) -> float:
        answers, decision = ask(search, "\n".join([first.strip(), second.strip()]), {"join": YesNo(JOIN)}, {})
        decision["chosen"] = answers["join"]
        return answers["join"] or 0.0

    message = message or phrases(text, replies, world, same_request if join else None, limits)
    constants = grounded(text, world)
    finished: dict[int, Phrase] = {}
    context: list[Term] = []
    seen: set[int] = set()
    for phrase in innermost(message):
        words = Constant(phrase.brand, text[phrase.start:phrase.end].strip(), phrase.start, phrase.end)
        # A member typed Asked stands only in a phrase whose brand is Asked: a quote cannot supply it.
        local = [one for one in constants if phrase.start <= one.start < phrase.end and (not isinstance(one.value, Member) or is_subtype(phrase.brand, one.value.type))]
        done = choose(phrase, Environment((*local, words), tuple(context)), search) if phrase.brand == world.types["Asked"] and words.value else phrase
        finished[phrase.start] = done
        results = [one for term in done.terms for one in operations(term, seen) if isinstance(one, Application)]
        context = [*reversed(results), *reversed(local), *([words] if words.value else []), *context]
    with_terms = fold(lambda phrase: phrase if phrase.inside else finished[phrase.start], message)
    return Reading(uuid.uuid4().hex, text, with_terms, constants, search.decisions, identity(world))


# ---- Part 4: judgments over a reading ----------------------------------------


def obligations(reading: Reading) -> list[tuple[Phrase, Application | Unresolved]]:
    """Returns every operation that the message asks for, with its phrase, nested ones included, each once.

    The order is the order of the phrases; within a phrase an operation comes
    after the operations whose results it consumes. Its index is its ``number``.
    """
    seen: set[int] = set()
    return [(phrase, one) for phrase in innermost(reading.message) for term in phrase.terms for one in operations(term, seen)]


def passages(reading: Reading) -> list[tuple[Phrase, str]]:
    """Returns each phrase that asks for no operation, with its relation to the request: a quote, or context."""
    return [(phrase, "quote" if phrase.quotes is not None else "context") for phrase in innermost(reading.message)
            if not phrase.terms and reading.text[phrase.start:phrase.end].strip()]


def bindings(term: Application | Record, prefix: str = "") -> dict[str, Term]:
    """Returns the term at each argument path, with the fields of a record at dotted paths."""
    found: dict[str, Term] = {}
    for name, value in (term.arguments if isinstance(term, Application) else term.fields).items():
        found |= bindings(value, f"{prefix}{name}.") if isinstance(value, Record) else {prefix + name: value}
    return found


def place_type(application: Application, path: str) -> Type:
    """Returns the type of the place at a path of an application: a parameter, or a field of a record in it."""
    first, *fields = path.split(".")
    goal = dict(application.function.parameters)[first]
    for field in fields:
        goal = dict(goal.fields)[field]
    return goal


def fits(term: Term, goal: Type, path: str) -> list[tuple[str, str]]:
    """Checks one term against the type of its place, recursively. Returns (path, rule) for each fault."""
    inner = goal.argument if isinstance(goal, Applied) and goal.constructor in (MAYBE, MANY) else goal
    match term:
        case Hole(type=given):
            try:
                kind = kind_of(given)
            except TypeError:
                kind = None
            return [] if kind == Star() and is_subtype(given, goal) else [(path, "type" if kind == Star() else "kind")]
        case Empty(type=given):
            return [] if isinstance(goal, Applied) and goal.constructor == MAYBE and is_subtype(given, goal) else [(path, "type")]
        case Several(element=element, terms=terms):
            if not (isinstance(goal, Applied) and goal.constructor == MANY and is_subtype(element, inner)):
                return [(path, "type")]
            return [found for one in terms for found in fits(one, element, path + "[]")]
        case Constant(type=given, value=value) if not inhabits(value, given):
            return [(path, "type")]
        case Record(product=product, fields=fields):
            whole = goal.argument if isinstance(goal, Applied) and goal.constructor == MAYBE else goal  # a record is no collection
            return checked(fields, dict(product.fields), path + ".") if is_subtype(product, whole) else [(path, "type")]
    optional = isinstance(goal, Applied) and goal.constructor == MAYBE
    return [] if fills(term, goal) or (optional and fills(term, inner)) else [(path, "type")]


def inhabits(value: object, kind: Type) -> bool:
    """Decides whether a constant's value is a value of its own type: a member of its sum, an int, a path, or words."""
    match kind:
        case Sum():
            return any(one.value == value for one in members(kind))
        case Base(python=python) if python in (int, pathlib.Path):
            return type(value) is python or isinstance(value, pathlib.PurePath) and python is pathlib.Path
        case Brand() | Base():
            return isinstance(value, str) and kind_of_words(kind)
    return False


def kind_of_words(kind: Type) -> bool:
    """Decides whether a type is str or a brand over it."""
    return kind.python is str if isinstance(kind, Base) else kind_of_words(kind.of)


def checked(values: dict[str, Term], places: dict[str, Type], prefix: str = "") -> list[tuple[str, str]]:
    """Checks the arguments of an application or the fields of a record: each place once, no other key, each of its type."""
    found = [(prefix + name, "missing") for name in places if name not in values]
    found += [(prefix + name, "extra") for name in values if name not in places]
    return found + [one for name in values if name in places for one in fits(values[name], places[name], prefix + name)]


def validate(reading: Reading) -> list[tuple[int, str, str]]:
    """The one validation judgment of a reading: (operation number, path, rule) for each fault.

    Checks each operation's arguments: missing, extra, type and kind, at every
    depth of records and collections, and that each constant's span in the text
    says its value ("identity"). References are checked where a term can
    get one: by ``edit``, and by ``load`` for a reference to no operation.
    """
    found = []
    for _, term in obligations(reading):
        if isinstance(term, Application):
            found += [(term.number, path, rule) for path, rule in checked(term.arguments, dict(term.function.parameters))]
            found += [(term.number, path, "identity") for path, value in bindings(term).items() for one in (value.terms if isinstance(value, Several) else (value,))
                      if isinstance(one, Constant) and one.start >= 0 and not says(reading.text[one.start:one.end], one.value)]
    return found


def says(text: str, value: object) -> bool:
    """Decides whether a span of the text says a constant's value: its member words, number, path or words."""
    words = value.words if isinstance(value, Member) else str(value)
    return " ".join(text.split()).lower() == " ".join(words.split()).lower()


def diagnostics(reading: Reading) -> list[tuple[int | None, str | None, str]]:
    """Returns the validation faults of a reading, and each place where d1's answer was invalid ("model_answer")."""
    found: list[tuple[int | None, str | None, str]] = validate(reading)
    for _, term in obligations(reading):
        if isinstance(term, Unresolved) and term.reason == "invalid answer":
            found.append((term.number, None, "model_answer"))
        elif isinstance(term, Application):
            found += [(term.number, path, "model_answer") for path, value in bindings(term).items() if isinstance(value, Hole) and value.reason == "invalid answer"]
    return found


def inspect(reading: Reading, number: int, path: str) -> dict:
    """Returns what stands at a place, its type, the definition of its function, and the decision about it. Changes nothing."""
    term = next(one for _, one in obligations(reading) if one.number == number)
    return {"term": bindings(term).get(path), "type": show(place_type(term, path)), "definition": term.function.asks,
            "decision": next((one for one in reading.decisions if (one["operation"], one["path"]) == (number, path)), None)}


# ---- Part 5: edits, records and the store -------------------------------------


def edit(reading: Reading, number: int | None, path: str, value: Term | None, correction: bool = False, world: World | None = None,
         phrase: tuple[int, int] | None = None) -> tuple[Reading, list[tuple[int, str, str]]]:
    """Proposes one change at one place of an operation, and validates the whole proposed reading.

    The base reading is not changed: the draft is a copy that keeps every shared
    reference and every decision. A value may refer only to an operation made
    before the one it is placed in.

    With ``number`` None, the edit asks for a new operation: ``path`` is
    "function.parameter" of ``world``, the value fills that parameter (one value
    for a Many becomes a collection of it), every other parameter is a cleared
    hole, and the operation joins the phrase that the value comes from, after
    its operations, with a new number. Its number is an identity, not a place:
    no other number changes.

    Args:
        reading: The base reading.
        number: The operation, or None for a new one.
        path: The argument, or a field at a dotted path; "function.parameter" for a new operation.
        value: The new term (from the base reading or new), or None to remove the binding.
        correction: True to keep the edit as an accepted manual correction (a
            new operation: as the user's request). A valid edit at a place that
            has a correction replaces it either way.
        world: The world, for a new operation; it must be the reading's own.
        phrase: (start, end) of the phrase a new operation joins, for a value with no place in the text.

    Returns:
        The draft and its diagnostics. With diagnostics the edit is rejected and
        the caller keeps the base.
    """
    copies: dict = {}
    draft = dataclasses.replace(copy.deepcopy(reading, copies), fulfillment=None)  # an edit makes an earlier check stale
    value = copy.deepcopy(value, copies)
    asked = number is None
    if asked:
        draft, number, rule = requested(draft, path, value, world, phrase)
        if number is None:
            return draft, [(None, path.partition(".")[2], rule)]
        path = rule
        value = bindings(by_number(draft, number))[path]
    entries = [term for _, term in obligations(draft)]
    target = next((term for term in entries if term.number == number), None)
    if isinstance(target, Unresolved):
        return draft, [(number, path, "unresolved")]
    if target is None:
        return draft, [(None if asked else number, path, "reference")]
    earlier = {id(term) for term in entries[:entries.index(target)]}
    referred = [one for one in ([value] if value is not None else []) for one in operations(one, set()) if isinstance(one, Application)]
    if any(id(one) not in earlier for one in referred):
        return draft, [(None if asked else number, path, "reference")]
    try:
        holder, last = place(target, path)
    except (KeyError, AttributeError):
        return draft, [(None if asked else number, path, "missing")]
    if value is None:
        holder.pop(last, None)
    else:
        holder[last] = value
    found = [(None if asked and one[0] == number else one[0], *one[1:]) for one in validate(draft)]  # a refused new operation has no number
    if not found and (correction or any((one["operation"], one["path"]) == (number, path) for one in draft.corrections)):
        corrected(draft, number, path, value, asked)  # a later edit at a corrected place is the correction now
    return draft, found


def requested(draft: Reading, path: str, value: Term, world: World | None, at: tuple[int, int] | None) -> tuple[Reading, int | None, str]:
    """Adds a new operation that a value is given to, as ``edit`` describes.

    Returns the draft, its number and parameter; or the draft, None and the
    rule that refuses it: "identity" (a world other than the reading's),
    "name" (no such function), "extra" (no such parameter), "phrase" (the value
    has no place in the text and no phrase was given).
    """
    name, _, parameter = path.partition(".")
    if world is None or identity(world) != draft.world:
        return draft, None, "identity"
    function = world.functions.get(name)
    kind = dict(function.parameters).get(parameter) if function else None
    pairs = obligations(draft)
    source = value.terms[0] if isinstance(value, Several) and value.terms else value
    phrase = next((one for one in innermost(draft.message) if [one.start, one.end] == list(at or ())), None) or next((one for one, term in pairs if term is source), None) or next(
        (one for one in innermost(draft.message) if isinstance(source, Constant) and one.start <= source.start < one.end), None)
    if isinstance(source, Application) and not any(term is source for _, term in pairs):
        return draft, None, "reference"
    if kind is not None and isinstance(kind, Applied) and kind.constructor == MANY and not isinstance(value, Several) and fills(value, kind.argument):
        value = Several(kind.argument, (value,))
    if kind is not None and fits(value, kind, parameter):
        return draft, None, "type"
    if function is None or kind is None or phrase is None or phrase.brand.name != "Asked":  # only the user's own words ask, as in read
        return draft, None, "name" if function is None else "extra" if kind is None else "phrase"
    new = Application(function, {one: value if one == parameter else Hole(other, "cleared") for one, other in function.parameters}, max((term.number for _, term in pairs), default=-1) + 1)
    message = fold(lambda one: dataclasses.replace(one, terms=one.terms + (new,)) if (one.start, one.end, one.inside) == (phrase.start, phrase.end, ()) else one, draft.message)
    return dataclasses.replace(draft, message=message), new.number, parameter


def place(application: Application, path: str) -> tuple[dict, str]:
    """Returns the dict that holds the place at a path of an application, and its key there (KeyError if a record on the way is missing)."""
    *outer, last = path.split(".")
    holder = application.arguments
    for name in outer:
        holder = holder[name].fields
    return holder, last


def corrected(draft: Reading, number: int, path: str, value: Term | None, asked: bool = False) -> None:
    """Keeps the correction at a place of a draft, replacing one already there; None removes it.

    It records where the corrected operation stands in the source (its phrase,
    and which of that phrase's operations of its function it is), the
    value as a term record and, for each operation that the
    value refers to, what that operation meant, so that a rerun can tell
    whether the correction still names the same place and the same result.
    """
    pairs = obligations(draft)
    entries = [term for _, term in pairs]
    meanings = meaning(draft)
    asked = asked or any(one.get("requested") for one in draft.corrections if (one["operation"], one["path"]) == (number, path))
    draft.corrections[:] = [one for one in draft.corrections if (one["operation"], one["path"]) != (number, path)]
    if value is not None:
        phrase, target = next((phrase, term) for phrase, term in pairs if term.number == number)
        refers = [[term.number, term.function.name, meanings[entries.index(term)]] for term in operations(value, set()) if term in entries]
        peers = [term for one, term in pairs if one is phrase and isinstance(term, Application) and term.function == target.function]
        draft.corrections.append(plain({"operation": number, "function": target.function.name, "phrase": [phrase.start, phrase.end], "path": path,
                                        "ordinal": peers.index(target), "of": len(peers), "value": term_record(value, {term.number for term in entries}),
                                        "refers": refers, "requested": asked,
                                        "status": "retained", "reason": ""}))


def plain(data: object) -> object:
    """Returns data as JSON gives it back, so that a saved meaning and a computed one compare equal."""
    return json.loads(json.dumps(data))


def finite(data: object) -> object:
    """Returns data with each number that JSON cannot hold (NaN, an infinity, from a malformed raw answer of d1) as the
    string JSON's own extension writes for it, so a line is valid JSON and the answer still reads as no share."""
    match data:
        case float() if not math.isfinite(data):
            return "NaN" if data != data else "Infinity" if data > 0 else "-Infinity"
        case dict():
            return {key: finite(value) for key, value in data.items()}
        case list() | tuple():
            return [finite(value) for value in data]
    return data


def term_record(term: Term, written: set[int], judged: dict[int, dict] | None = None) -> dict:
    """Converts a term to data that JSON can hold, in the shape of the saved record.

    An application is ``{"id", "function", "arguments", "type", "parameters"}``
    (``parameters``: the declared type of each argument place), with the
    engine's ``judgments`` of it when ``judged`` has them; an application
    already written is ``{"ref": id}``. A value is ``{"constant":
    value, "type", "at"}``, ``{"several": [...], "type"}``, ``{"fields": {...},
    "type"}``, ``{"empty": type}`` or ``{"hole": type, "reason"}``. Types are written by name.
    """
    if isinstance(term, Application) and term.number in written:
        return {"ref": str(term.number)}
    kind = show(type_of(term))
    match term:
        case Constant(value=value, start=start, end=end):
            return {"constant": value.words if isinstance(value, Member) else value if isinstance(value, int) else str(value), "type": kind, "at": [start, end]}
        case Application(function=function, arguments=arguments, number=number):
            if number is not None:
                written.add(number)
            line = {"id": None if number is None else str(number), "function": function.name, "type": kind,
                    "parameters": {name: show(one) for name, one in function.parameters}, "arguments": {name: term_record(one, written, judged) for name, one in arguments.items()}}
            return line | ({"judgments": judged[number]} if judged and number in judged else {})
        case Record(fields=fields):
            return {"fields": {name: term_record(one, written, judged) for name, one in fields.items()}, "type": kind}
        case Several(terms=terms):
            return {"several": [term_record(one, written, judged) for one in terms], "type": kind}
        case Empty():
            return {"empty": kind}
    return {"hole": kind, "reason": term.reason}


def record(reading: Reading) -> dict:
    """Converts a reading to one line of the store (form 5): everything ``load`` needs, with no copied subtree.

    Keys: form, id, text, world (``agree.identity``), phrases (each innermost
    phrase in order: start, end, brand, starts_by, quotes, terms: its
    applications, each with the declared type of each place and the engine's
    judgments at save time: valid, diagnostics, complete, pending (its value
    is not available yet), deferred (its own result comes later), ready (it
    can start now), which ``load`` does not read: it judges again; and
    unresolved: each unresolved operation with its place among the phrase's
    operations), constants
    (every grounded span), decisions (every decision, d1's and the rules',
    with its path, its candidates and its choice as term records) and corrections.
    """
    written: set[int] = set()
    found = diagnostics(reading)
    judged = {term.number: {"valid": not any(one[0] == term.number for one in found), "diagnostics": [list(one[1:]) for one in found if one[0] == term.number],
                            "complete": complete(term), "pending": pending(term), "deferred": deferred(term), "ready": ready(reading, term)}
              for _, term in obligations(reading) if isinstance(term, Application)}
    phrases_line = []
    for phrase in innermost(reading.message):
        phrases_line.append({"start": phrase.start, "end": phrase.end, "brand": phrase.brand.name, "starts_by": phrase.starts_by, "quotes": phrase.quotes,
                             "terms": [term_record(term, written, judged) for term in phrase.terms if isinstance(term, Application)],
                             "unresolved": [{"id": str(term.number), "reason": term.reason, "place": place} for place, term in enumerate(phrase.terms) if isinstance(term, Unresolved)]})
    chosen = lambda value: [term_record(one, written) for one in value] if isinstance(value, list) else term_record(value, written) if isinstance(value, Constant | Application | Record | Several | Empty | Hole) else value
    decisions = [one | {"offered": [term_record(term, written) for term in one["offered"]], "cut": [term_record(term, written) for term in one["cut"]], "chosen": chosen(one["chosen"])}
                 for one in reading.decisions]
    return finite({"form": 5, "id": reading.id, "text": reading.text, "source": hashlib.sha256(reading.text.encode()).hexdigest()[:16], "world": reading.world, "base": reading.base, "phrases": phrases_line,
             "constants": [term_record(one, written) for one in reading.constants], "decisions": decisions, "corrections": reading.corrections}
            | ({"fulfillment": [dataclasses.asdict(one) for one in reading.fulfillment]} if reading.fulfillment is not None else {}))


def type_named(name: str, world: World) -> Type:
    """Rebuilds a type from its name as ``agree.show`` writes it."""
    if name in world.types:
        return world.types[name]
    head, bracket, rest = name.partition("[")
    if bracket and head in CONSTRUCTORS and name.endswith("]"):
        return Applied(CONSTRUCTORS[head], type_named(rest[:-1], world))
    if " | " in name:
        return Sum("", tuple(type_named(one, world) for one in name.split(" | ")))
    raise LookupError(f"{name} is no type of this world")


def term_from(line: dict, world: World, made_by: dict[int, Application], dangling: list | None = None, at: tuple = (None, ""), expected: Type | None = None) -> Term:
    """Rebuilds a term from its record. A reference becomes the same object as the operation it names.

    A reference to no operation made before it, at any depth, is a hole of its
    place's type with reason "dangling reference", noted in ``dangling`` as
    (operation, path, "reference"); ``at`` and ``expected`` say where it stands.

    Raises:
        LookupError: If the world has no such type, member or function, or a reference dangles and no list takes it.
    """
    if "ref" in line:
        number = int(line["ref"]) if str(line["ref"]).isdigit() else None
        if number in made_by or dangling is None or expected is None:
            return made_by[number]
        dangling.append((*at, "reference"))
        return Hole(expected, "dangling reference")
    if "function" in line:
        number = None if line["id"] is None else int(line["id"])
        function = world.functions[line["function"]]
        places = dict(function.parameters)
        arguments = {name: term_from(one, world, made_by, dangling, (number, name), places.get(name)) for name, one in line["arguments"].items()}
        application = Application(function, arguments, number)
        if number is not None:
            made_by[number] = application
        return application
    kind = type_named(line.get("type") or line.get("empty") or line.get("hole"), world)
    if "constant" in line:
        value = line["constant"]
        if isinstance(kind, Sum):
            value = next((one.value for one in members(kind) if one.value.words == value), None)
            if value is None:
                raise LookupError(f"{line['constant']} is no member of {kind.name}")
        elif kind.name == "Path":
            value = pathlib.Path(value)
        return Constant(kind, value, *line.get("at", (-1, -1)))
    if "fields" in line:
        return Record(kind, {name: term_from(one, world, made_by, dangling, (at[0], f"{at[1]}.{name}"), dict(kind.fields).get(name)) for name, one in line["fields"].items()})
    if "several" in line:
        return Several(kind.argument, tuple(term_from(one, world, made_by, dangling, at, kind.argument) for one in line["several"]))
    return Empty(kind) if "empty" in line else Hole(kind, line["reason"])


def recorded_phrases(line: dict, world: World, made_by: dict[int, Application] | None = None, dangling: list | None = None) -> Phrase:
    """Rebuilds the phrases of a record; with ``made_by``, their operations too, else none."""
    found = []
    for phrase in line["phrases"]:
        terms = () if made_by is None else tuple(term_from(one, world, made_by, dangling) for one in phrase["terms"])
        for one in phrase["unresolved"] if made_by is not None else ():  # each unresolved operation at its place among the phrase's operations
            terms = terms[:one["place"]] + (Unresolved(int(one["id"]), one["reason"]),) + terms[one["place"]:]
        found.append(Phrase(phrase["start"], phrase["end"], world.types[phrase["brand"]], (), phrase["starts_by"], phrase["quotes"], terms))
    return found[0] if len(found) == 1 else Phrase(0, len(line["text"]), None, tuple(found))


def load(line: dict, world: World) -> tuple[Reading | None, list[tuple[None, None, str]]]:
    """Rebuilds a saved reading with the same identities, bindings, unresolved state and decisions. Asks d1 nothing.

    Returns:
        The reading and the diagnostics of ``validate``; or None and an
        "identity" diagnostic if the record was read against another world, or
        a "reference" diagnostic if it refers to no operation.
    """
    if line["world"] != identity(world) or line["source"] != hashlib.sha256(line["text"].encode()).hexdigest()[:16]:
        return None, [(None, None, "identity")]
    made_by: dict[int, Application] = {}
    dangling: list[tuple[int, str, str]] = []
    rebuilt = lambda value: [term_from(one, world, made_by, dangling) for one in value] if isinstance(value, list) else term_from(value, world, made_by, dangling) if isinstance(value, dict) else value
    message = recorded_phrases(line, world, made_by, dangling)
    try:
        decisions = [one | {"offered": rebuilt(one["offered"]), "cut": rebuilt(one["cut"]), "chosen": rebuilt(one["chosen"])} for one in line["decisions"]]
    except KeyError:  # a decision's candidate names no operation
        return None, [(None, None, "reference")]
    reading = Reading(line["id"], line["text"], message, rebuilt(line["constants"]), decisions, line["world"], [dict(one) for one in line["corrections"]], line.get("snapshot"),
                      [Checked(**one) for one in line["fulfillment"]] if "fulfillment" in line else None)
    numbers = [term.number for _, term in obligations(reading)]
    if len(set(numbers)) != len(numbers):  # two operations with one number: no reference can be trusted
        return None, [(None, None, "identity")]
    found = validate(reading)
    if found or dangling or any(one.obligation not in numbers for one in reading.fulfillment or ()):
        reading = dataclasses.replace(reading, fulfillment=None)  # a saved check of another reading is not this reading's
    for number, path, rule in found:
        if rule in ("type", "kind"):  # a saved value of the wrong type is not trusted: its place becomes a hole
            holder, last = place(by_number(reading, number), path)
            holder[last] = Hole(place_type(by_number(reading, number), path), "invalid saved value")
    return reading, found + dangling


def by_number(reading: Reading, number: int) -> Application | None:
    """Returns the operation of a reading with this number."""
    return next((term for _, term in obligations(reading) if term.number == number), None)


def save(reading: Reading, store: pathlib.Path) -> tuple[Reading, list[tuple[None, None, str]]]:
    """Appends the record of a reading to the store as a new snapshot, and returns the reading with that snapshot as its base.

    A draft made from an earlier snapshot of the same reading than the store's
    latest is not saved: it returns the draft and a "stale" diagnostic.

    Raises:
        OSError: If the write fails; the caller keeps its draft.
    """
    earlier = [line["snapshot"] for line in saved(store) if line["id"] == reading.id]
    if earlier and earlier[-1] != reading.base:
        return reading, [(None, None, "stale")]
    line = record(reading) | {"snapshot": uuid.uuid4().hex}
    with store.open("a") as file:
        file.write(json.dumps(line, allow_nan=False) + "\n")
    return dataclasses.replace(reading, base=line["snapshot"]), []


def restore(store: pathlib.Path, snapshot: int, world: World) -> tuple[Reading | None, list]:
    """Loads the n-th snapshot (from 1) as the current reading: a new draft over the store's latest snapshot, so it can be saved."""
    lines = saved(store)
    reading, found = load(lines[snapshot - 1], world)
    latest = [line["snapshot"] for line in lines if line["id"] == lines[snapshot - 1]["id"]][-1]
    return (dataclasses.replace(reading, base=latest) if reading else None), found


def saved(store: pathlib.Path) -> list[dict]:
    """Returns every snapshot in the store, the oldest first."""
    return [json.loads(line) for line in store.read_text().splitlines()] if store.exists() else []


def rerun(line: dict, world: World, model: Model, limits: Limits = Limits()) -> Reading:
    """Reads the source of a saved reading again with its phrases, and re-applies its corrections.

    A correction whose operation, value, place, or referred result no longer
    holds is kept with status "invalidated" and the reason; it never yields
    silently to d1.
    """
    reading = read(line["text"], world, [], model, False, limits, recorded_phrases(line, world))
    for correction in line["corrections"]:
        status, reason = "retained", ""
        try:
            pairs = obligations(reading)
            entries = [term for _, term in pairs]
            made_by = {term.number: term for term in entries if isinstance(term, Application)}
            for number, function, before in correction["refers"]:  # the result a correction names must still mean what it meant
                now = plain(meaning(reading)[entries.index(made_by[number])]) if number in made_by else None
                if now != before:
                    raise LookupError(f"{correction['path']} referred to {function}, whose meaning changed from {before} to {now}")
            if correction.get("requested"):  # the user asked for this operation: give the value to the function again
                try:
                    value = term_from(correction["value"], world, made_by)
                except LookupError as error:
                    raise LookupError(f"the requested {correction['function']} of {correction['path']} no longer applies: {str(error).strip(chr(39))}")
                draft, found = edit(reading, None, f"{correction['function']}.{correction['path']}", value, world=world, phrase=tuple(correction["phrase"]))
                if found:
                    raise LookupError(f"the requested {correction['function']} of {correction['path']} no longer applies ({found})")
                reading, correction = draft, correction | {"operation": max(term.number for _, term in obligations(draft))}
                reading.corrections.append(correction | {"status": status, "reason": reason})
                continue
            here = [term for phrase, term in pairs if [phrase.start, phrase.end] == correction["phrase"] and isinstance(term, Application)]
            same = [term for term in here if term.function.name == correction["function"]]
            if not same:
                now = " and ".join(term.function.name for term in here) or "no operation"
                raise LookupError(f"{correction['function']} became {now} in its phrase, so the correction of {correction['path']} no longer applies")
            if len(same) != correction["of"]:
                raise LookupError(f"its phrase now asks for {len(same)} {correction['function']} where it asked for {correction['of']}, so the correction of {correction['path']} has no one place")
            target = same[correction["ordinal"]]
            try:
                value = term_from(correction["value"], world, made_by)
            except LookupError as error:
                raise LookupError(f"{correction['path']}: {str(error).strip(chr(39))}")
            draft, found = edit(reading, target.number, correction["path"], value)
            if found:
                raise LookupError(f"{correction['path']}: the corrected value no longer fits ({found})")
            reading, correction = draft, correction | {"operation": target.number}
        except LookupError as error:
            status, reason = "invalidated", str(error).strip("'\"")
        reading.corrections[:] = [one for one in reading.corrections if (one["operation"], one["path"]) != (correction["operation"], correction["path"])]
        reading.corrections.append(correction | {"status": status, "reason": reason})
    return dataclasses.replace(reading, base=line.get("snapshot"))


def value_of(term: Term, index: dict[int, int]) -> object:
    """Returns a bound value as comparable data: a constant by its type and value (not its span or display),
    a result by its obligation index, a record by its fields, a hole by its type and reason."""
    match term:
        case Constant(type=kind, value=Member(words=words)) | Constant(type=kind, value=words):
            return (show(kind), str(words))
        case Application():
            return ("ref", index.get(id(term)))
        case Record(product=product, fields=fields):
            return ("record", product.name, tuple(sorted((name, repr(value_of(one, index))) for name, one in fields.items())))
        case Several(terms=terms):
            return ("several", tuple(sorted(repr(value_of(one, index)) for one in terms)))
        case Empty():
            return ("empty",)
    return ("hole", show(term.type), term.reason)


def meaning(reading: Reading) -> list[tuple]:
    """Returns each obligation as comparable data: its function with its docstring and parameter types, result type, whether it is pending, and the value at each path; or its unresolved reason."""
    entries = [term for _, term in obligations(reading)]
    index = {id(term): number for number, term in enumerate(entries)}
    return [("unresolved", term.reason) if isinstance(term, Unresolved) else (term.function.name, term.function.asks, [[name, show(kind)] for name, kind in term.function.parameters],
                                                                              show(term.function.result), pending(term), {path: value_of(one, index) for path, one in bindings(term).items()})
            for term in entries]


@dataclasses.dataclass(frozen=True)
class Gate:
    """The decision about a proposed world.

    Attributes:
        activated: True only if the proposed world has no fault, the corpus is
            not empty, and every accepted obligation keeps its operation and
            bindings, and no obligation is added.
        verdict: PASS, FAIL (a fault or a regression) or UNVERIFIED (no corpus).
        regressions: (line, obligation) of each accepted obligation that changed, disappeared or was added, and not migrated.
        migrated: The changes that the caller accepted explicitly.
        faults: The faults of the proposed world.
        world: The active world after the decision.
        source: The source of the active world after the decision.
        lines: The corpus for the active world: the lines read again under it if it was activated, else the lines given.
    """

    activated: bool
    verdict: str
    regressions: list[tuple[int, int]]
    migrated: list[tuple[int, int]]
    faults: list[tuple[str, str, str]]
    world: World
    source: str
    lines: list[dict]


def gate(source: str, folder: pathlib.Path, lines: list[dict], model: Model, active: World, active_source: str, limits: Limits = Limits(),
         migrations: tuple = ()) -> Gate:
    """Decides whether a proposed world.py becomes active: it must keep every accepted meaning of the corpus.

    Each saved reading is read again under the proposed world with its own
    phrases and corrections, and compared obligation by obligation with the
    accepted one: function, result type, pending, every binding and every
    reason. A change is a regression unless the caller names it in
    ``migrations`` as (line, obligation): an explicit decision to accept it.
    d1's confidence plays no part.
    """
    proposed = loads(source, folder)
    if proposed.faults or not lines:
        return Gate(False, FAIL if proposed.faults else UNVERIFIED, [], [], proposed.faults, active, active_source, lines)
    regressions, reread = [], []
    for number, line in enumerate(lines):
        again = rerun(line, proposed, model, limits)
        accepted = load(line, active)[0]
        if accepted is None:  # the accepted line does not load under the active world: nothing can be compared
            regressions.append((number, None))
            continue
        before, after = meaning(accepted), meaning(again)
        regressions += [(number, index) for index in range(max(len(before), len(after))) if index >= len(before) or index >= len(after) or after[index] != before[index]]
        reread.append(plain(record(again)))
    migrated, regressions = [one for one in regressions if one in migrations], [one for one in regressions if one not in migrations]
    if regressions:
        return Gate(False, FAIL, regressions, migrated, [], active, active_source, lines)
    return Gate(True, PASS, [], migrated, [], proposed, source, reread)


# ---- Part 6: fulfillment -------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Artifact:
    """Supplied evidence about one exact operation.

    The criteria judge what it shows; the engine only decides which operation it is about.

    Attributes:
        function: The function of the operation.
        arguments: The term at each argument path, as ``bindings`` gives them.
        operation: The number of the operation it is evidence for. Without
            it, the artifact is about an operation only if exactly one
            obligation has this function and these arguments: two identical
            operations are two pieces of work.
    """

    function: str
    arguments: dict[str, Term]
    operation: int | None = None


@dataclasses.dataclass(frozen=True)
class Checked:
    """One criterion-specific outcome for one obligation.

    Attributes:
        obligation: The operation number.
        criterion: The name of the criterion.
        outcome: PASS (every artifact about this sound operation meets it),
            FAIL (one about it does not) or UNVERIFIED (no artifact is about it
            alone, or the operation is unresolved, invalid or incomplete).
        evidence: The index of the artifact that decided, or None.
        claim: d1's share that the reply says it is done: a judgment kept
            beside the outcome, never evidence.
    """

    obligation: int
    criterion: str
    outcome: str
    evidence: int | None
    claim: float | None


def about(application: Application, artifact: Artifact, index: dict[int, int]) -> bool:
    """Decides whether an artifact could be about this operation: the same function, the same value at each path, and its number if it names one."""
    given = {path: value_of(one, index) for path, one in artifact.arguments.items()}
    return (artifact.function == application.function.name and given == {path: value_of(one, index) for path, one in bindings(application).items()}
            and artifact.operation in (None, application.number))


def check(reading: Reading, reply: str, artifacts: list[Artifact], criteria: list[tuple[str, typing.Callable]], model: Model, limits: Limits = Limits()) -> tuple[Reading, str, dict]:
    """Checks a reply and its evidence against every obligation of a reading, unresolved ones included.

    d1 is asked once whether the reply says each exact operation (its call,
    with its arguments) is done; that share is kept as a claim. Outcomes come
    only from the criteria applied to artifacts about that operation.

    Returns:
        The reading with the outcomes as its ``fulfillment`` (saved with it),
        the verdict (PASS only if every outcome is PASS; FAIL if any is FAIL;
        else UNVERIFIED) and the request to d1.
    """
    entries = [term for _, term in obligations(reading)]
    index = {id(term): number for number, term in enumerate(entries)}
    search = Search(reading.text, None, model, limits, [], itertools.count())
    asked = {f"did {term.number}": YesNo(rendered(shipped.DID(f"{term.function.asks}: {say(term)}"))) for term in entries if isinstance(term, Application)}
    claims, judgment = ask(search, f"MESSAGE:\n{reading.text}\n\nREPLY:\n{reply}", asked, {}) if asked else ({}, None)
    found: list[Checked] = []
    concerns = {place: [term for term in entries if isinstance(term, Application) and about(term, artifact, index)] for place, artifact in enumerate(artifacts)}
    for term in entries:
        mine = [place for place, terms in concerns.items() if terms == [term] and sound(reading, term)]
        for name, criterion in criteria:
            failed = [place for place in mine if not criterion(term, artifacts[place])]
            outcome, evidence = (FAIL, failed[0]) if failed else (PASS, mine[0]) if mine else (UNVERIFIED, None)
            found.append(Checked(term.number, name, outcome, evidence, claims.get(f"did {term.number}")))
    outcomes = {one.outcome for one in found}
    verdict = FAIL if FAIL in outcomes else PASS if outcomes == {PASS} else UNVERIFIED
    return dataclasses.replace(reading, fulfillment=found), verdict, judgment

