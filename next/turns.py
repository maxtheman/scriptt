"""Turns: the context that carries from one message to the next, and the trace of one turn.

One turn of an agent maps ``context[n]`` and a message to ``context[n+1]`` and
the executions of the turn. A ``Trace`` holds the whole turn in one record: the
entities in scope before it, the wordings that d1 received, the hash of the
world, the reading of the message, the corrections of the user, the executions
and the entities in scope after it. ``save`` appends a trace to the log as one
JSON line, and ``load`` rebuilds it, so that the hook sends the corrected
reading.
"""

import ast
import dataclasses
import datetime
import json
import pathlib
import types
import typing

import agree
import scriptt16
from agree import CONSTRUCTORS, Applied, Base, Function, Member, Product, Sum, Type, World, is_subtype
from scriptt16 import Application, Choice, Constant, Empty, Hole, Limits, Phrase, Prompts, Reading, Record, Several, Term

KINDS = ("parser_override", "candidate_injected", "request_edited", "prompt_edited")
"""The kinds of a correction."""

TRACE_FORM = "trace 1"
"""The form of a trace line of the log. Change it when a key changes its meaning."""


# ---- Entities: context[n] ---------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Entity:
    """A value in scope across turns: a grounded span, or the term that a phrase asked for.

    Attributes:
        id: A stable identifier: ``t<turn>:<start>-<end>`` for a span of the
            message of that turn, ``t<turn>:p<number>`` for the term of phrase
            ``number`` (counted as ``scriptt16.block`` counts).
        term: The term.
        turn: The turn that first named the entity.
        version_of: The identifier of the entity that this one changes, or None.
            The application of a function whose result can stand where one of
            its arguments stood is a version of that argument: redesign(surface=
            'the mod') is a version of the entity 'the mod'.
        origin: The brand of the text that named it: "Asked", "Written" or "Observed".
        text: The message of the turn that named it, which the places of its
            spans index.
    """

    id: str
    term: Term
    turn: int
    version_of: str | None
    origin: str
    text: str = dataclasses.field(default="", compare=False)


def unwrapped(expression: Type) -> Type:
    """Returns a type without an outer ``Later``: the type of the value when it is there."""
    return expression.argument if isinstance(expression, Applied) and expression.constructor == agree.LATER else expression


def same_value(first: Term, second: Term) -> bool:
    """Decides whether two terms name the same value: equal terms, or constants with one type and one value."""
    if first == second:
        return True
    return isinstance(first, Constant) and isinstance(second, Constant) and (first.type, first.value) == (second.type, second.value)


def next_context(context_in: tuple[Entity, ...], reading: Reading, turn: int) -> tuple[Entity, ...]:
    """Returns ``context[n+1]``: the entities of ``context[n]`` and the new entities of a reading.

    Args:
        context_in: The entities before the turn, the nearest first.
        reading: The reading of the message of the turn.
        turn: The number of the turn.

    Returns:
        The entities, the nearest first. The constants that the message grounds
        come in the order of the message, then the term of each phrase. Each new
        entity goes in front, so the last phrase is nearest. A constant whose
        type and value an earlier entity already has is that entity: it moves to
        the front and keeps its identifier. The term of a phrase is a new
        entity, and a version of the entity of an argument when the result of
        its function can stand where that argument stood.
    """
    text = reading.text
    entities = list(context_in)
    phrases = scriptt16.innermost(reading.message)
    brand_at = lambda place: next((phrase.brand.name for phrase in phrases if phrase.brand and phrase.start <= place < phrase.end), "Asked")

    def front(entity: Entity) -> None:
        entities[:] = [entity, *(other for other in entities if other.id != entity.id)]

    def entity_of(term: Term) -> Entity | None:
        return next((entity for entity in entities if same_value(entity.term, term)), None)

    for constant in reading.constants:
        known = entity_of(constant)
        front(known or Entity(f"t{turn}:{constant.start}-{constant.end}", constant, turn, None, brand_at(constant.start), text))
    for number, phrase in enumerate(phrases, 1):
        if phrase.term is None:
            continue
        version_of = None
        if isinstance(phrase.term, Application):
            result = unwrapped(phrase.term.function.result)
            for argument in phrase.term.arguments.values():
                known = entity_of(argument)
                if known and is_subtype(result, unwrapped(scriptt16.type_of(argument))):
                    version_of = known.id
                    break
        front(Entity(f"t{turn}:p{number}", phrase.term, turn, version_of, phrase.brand.name if phrase.brand else "Asked", text))
    return tuple(entities)


# ---- Executions ---------------------------------------------------------------


Execution = scriptt16.Execution
"""One side effect recorded during a turn (defined in scriptt16, where check() uses it)."""


@dataclasses.dataclass(frozen=True)
class Correction:
    """One change that the user made to the reading of a turn.

    Attributes:
        kind: "parser_override" (the choice was among the candidates that the
            search offered), "candidate_injected" (a value that the search did
            not offer: a gap of the search or of grounding), "request_edited"
            (the user changed the function that a phrase asks for, or added or
            removed one), or "prompt_edited" (the user edited a wording and d1
            ran again).
        phrase: The number of the phrase, as ``scriptt16.block`` counts. None for "prompt_edited".
        path: The place inside the term of the phrase, as ``scriptt16.holes_of``
            names it (``"subject"``, ``"review.cell"``). None for the function of
            the phrase, and for "prompt_edited".
        before: What stood there before, as data that JSON holds.
        after: What stands there now, as data that JSON holds.
        at: The time of the correction, in ISO 8601 with the time zone.
    """

    kind: str
    phrase: int | None
    path: str | None
    before: dict | None
    after: dict | None
    at: str


@dataclasses.dataclass(frozen=True)
class Trace:
    """One turn: ``context[n]`` and a message in, ``context[n+1]`` and executions out.

    Attributes:
        turn: The number of the turn.
        context_in: The entities in scope before the turn, the nearest first.
        prompts: The wordings that d1 received.
        world_hash: The ``scriptt16.world_hash`` of the world of the turn.
        reading: The reading of the message, with every correction applied.
        corrections: The corrections, in order.
        executions: The side effects of the turn.
        context_out: The entities in scope after the turn, from ``next_context``.
        replies: The earlier replies that the search compared with the message.
        history: The reading before each correction, so that ``undo`` restores it.
        world: The world of the turn. Not saved: ``load`` takes it.
    """

    turn: int
    context_in: tuple[Entity, ...]
    prompts: Prompts
    world_hash: str
    reading: Reading
    corrections: tuple[Correction, ...]
    executions: tuple[Execution, ...]
    context_out: tuple[Entity, ...]
    replies: tuple[str, ...] = ()
    history: tuple[Reading, ...] = dataclasses.field(default=(), compare=False)
    world: World | None = dataclasses.field(default=None, compare=False, repr=False)


def start_turn(
    text: str,
    world: World,
    replies: list[str],
    model: scriptt16.Model,
    context_in: tuple[Entity, ...] = (),
    prompts: Prompts = Prompts(),
    limits: Limits = Limits(),
    turn: int | None = None,
    executions: tuple[Execution, ...] = (),
    join: bool = True,
) -> Trace:
    """Reads the message of a turn with the context of earlier turns.

    Args:
        text: The message.
        world: The world.
        replies: The earlier replies in the log.
        model: The decision model.
        context_in: ``context[n]``: the ``context_out`` of the turn before, the nearest first.
        prompts: The wordings that d1 receives.
        limits: The numbers that the search uses.
        turn: The number of the turn. None means one more than the largest turn in ``context_in``.
        executions: The side effects of the turn, if they are known already.
        join: If True, d1 decides whether two neighbouring sentences are one
            request, as ``scriptt16.read`` does. If False, each sentence is a
            phrase of its own.

    Returns:
        The trace of the turn, with no correction.
    """
    turn = turn if turn is not None else max((entity.turn for entity in context_in), default=0) + 1
    reading = scriptt16.read(text, world, list(replies), model, join, limits=limits, prompts=prompts, prior_context=context_in)
    return Trace(turn, tuple(context_in), prompts, scriptt16.world_hash(world), reading, (), tuple(executions),
                 next_context(tuple(context_in), reading, turn), tuple(replies), (), world)


def with_executions(trace: Trace, executions: typing.Iterable[Execution]) -> Trace:
    """Returns the trace with more side effects recorded."""
    return dataclasses.replace(trace, executions=(*trace.executions, *executions))


def phrase_of(trace: Trace, number: int) -> Phrase:
    """Returns phrase ``number`` of the reading, counted from 1 as ``scriptt16.block`` counts."""
    phrases = scriptt16.innermost(trace.reading.message)
    if not 1 <= number <= len(phrases):
        raise ValueError(f"the message has phrases 1 to {len(phrases)}, not {number}")
    return phrases[number - 1]


def place(trace: Trace, number: int, path: str) -> tuple[Term, Type, Function, int]:
    """Finds a place inside the term of a phrase.

    Args:
        trace: The trace.
        number: The number of the phrase.
        path: The names from the term of the phrase to the place, joined by dots.

    Returns:
        The term at the place, the type of the place, the function whose
        parameter holds the place, and the number of nested applications that
        are still allowed there.

    Raises:
        ValueError: If the phrase has no term, or the path names no place.
    """
    term = phrase_of(trace, number).term
    if term is None:
        raise ValueError(f"phrase {number} asks for nothing, so it has no place {path!r}; correct its function first")
    depth = trace.reading.limits.depth
    goal: Type | None = None
    applying: Function | None = None
    for name in path.split("."):
        match term:
            case Application(function, arguments) if name in arguments:
                if applying is not None:
                    depth -= 1
                applying, goal, term = function, dict(function.parameters)[name], arguments[name]
            case Record(product, fields) if name in fields:
                goal, term = dict(product.fields)[name], fields[name]
            case _:
                raise ValueError(f"phrase {number} has no place {path!r}: {scriptt16.say(term, '')} has nothing named {name!r}")
    return term, goal, applying, depth


def replaced(term: Term, names: list[str], new: Term) -> Term:
    """Returns a term with the term at a path replaced."""
    if not names:
        return new
    head, rest = names[0], names[1:]
    match term:
        case Application(function, arguments):
            return Application(function, arguments | {head: replaced(arguments[head], rest, new)})
        case Record(product, fields):
            return Record(product, fields | {head: replaced(fields[head], rest, new)})
    raise ValueError(f"no place {head!r} inside {scriptt16.say(term, '')}")


def with_phrase(reading: Reading, new: Phrase) -> Reading:
    """Returns the reading with one innermost phrase replaced, found by its start."""
    message = scriptt16.fold(lambda phrase: phrase if phrase.inside else (new if phrase.start == new.start else phrase), reading.message)
    return dataclasses.replace(reading, message=message)


def environment_at(trace: Trace, number: int) -> scriptt16.Environment:
    """Returns the terms available to phrase ``number``, as the search had them."""
    phrases = scriptt16.innermost(trace.reading.message)
    return scriptt16.environment_of(phrases[number - 1], phrases[:number - 1], trace.reading.constants, trace.reading.text, trace.context_in)


def element_of(goal: Type) -> Type:
    """Returns the type of one value of a place: ``T`` for ``Maybe[T]`` and ``Many[T]``."""
    if isinstance(goal, Applied) and goal.constructor in (agree.MAYBE, agree.MANY):
        return goal.argument
    return goal


def offered_terms(trace: Trace, number: int, path: str) -> list[Term]:
    """Returns every term that could fill a place: what ``derivations`` offers, then the members of a sum."""
    _, goal, applying, depth = place(trace, number, path)
    goal = element_of(goal)
    terms = scriptt16.derivations(goal, environment_at(trace, number), trace.world, depth, applying)
    members = [alternative for alternative in goal.alternatives if isinstance(alternative, Member)] if isinstance(goal, Sum) else []
    shown = {scriptt16.say(term, "") for term in terms}
    return terms + [Constant(goal, member, -1, -1) for member in members if repr(member.words) not in shown]


def candidates(trace: Trace, phrase: int, path: str | None) -> list[str]:
    """Lists what could stand at a place of a phrase.

    Args:
        trace: The trace.
        phrase: The number of the phrase, as ``scriptt16.block`` counts.
        path: The place inside the term of the phrase. None for the function of the phrase.

    Returns:
        For a place, the ``say`` text of every term that could fill it: the
        terms that ``derivations`` offers, then each member of a sum of members
        that is not among them. For the function, the name of every function of
        the world, then "nothing".
    """
    if path is None:
        return [*trace.world.functions, "nothing"]
    return [scriptt16.say(term, trace.reading.text) for term in offered_terms(trace, phrase, path)]


def typed_constant(words: str, goal: Type, folder: pathlib.Path) -> Constant | None:
    """Turns words that the user supplies into a constant of a type, by the grounding rules.

    Args:
        words: The words.
        goal: The type of the place.
        folder: The folder of the world, for a path.

    Returns:
        A constant whose span would be all of ``words`` by ``scriptt16.stands``,
        for the goal or for one of its alternatives; or a constant of the goal
        itself if the goal takes words (a brand over ``str``, or ``str``). None
        if the words name no value of the goal. The constant has no place in
        the message: start and end are -1.
    """
    expression = element_of(goal)
    if len(words) >= 2 and words[0] == words[-1] and words[0] in "'\"":
        words = ast.literal_eval(words)  # the value as ``say`` writes it, in quote marks
    for constant in scriptt16.stands(expression, words, folder):
        if (constant.start, constant.end) == (0, len(words)):
            return Constant(constant.type, constant.value, -1, -1)
    if isinstance(expression, Sum):
        for alternative in expression.alternatives:
            if not isinstance(alternative, Member):
                found = typed_constant(words, alternative, folder)
                if found:
                    return found
    if is_subtype(expression, Base("str", str)) or (isinstance(expression, Base) and expression.python is str):
        return Constant(expression, words, -1, -1)
    return None


def now() -> str:
    """Returns the time now, in ISO 8601 with the time zone."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def recorder(trace: Trace, model: scriptt16.Model, requests: list[dict]) -> scriptt16.Model:
    """Returns the model, recording each request as ``scriptt16.read`` records it."""
    digests = (trace.world_hash, scriptt16.prompts_hash(trace.reading.prompts))

    def recorded(state: str, asked: dict[str, dict]) -> dict[str, dict]:
        answers = model(state, asked)
        requests.append(scriptt16.request_entry(state, asked, answers, *digests))
        return answers
    return recorded


def filled(trace: Trace, number: int, term: Term, depth: int, model: scriptt16.Model | None, requests: list[dict]) -> Term:
    """Fills the holes of a chosen application, as ``scriptt16.solve`` does, if a model is given."""
    if model is None or not isinstance(term, Application) or not any(isinstance(argument, Hole) for argument in term.arguments.values()):
        return term
    phrase = phrase_of(trace, number)
    search = scriptt16.Search(trace.reading.text, trace.world, recorder(trace, model, requests), trace.reading.limits, trace.reading.prompts)
    state = trace.reading.text[phrase.start:phrase.end].strip()
    return scriptt16.applied(term.function, environment_at(trace, number), search, state, depth)


def corrected(trace: Trace, reading: Reading, correction: Correction) -> Trace:
    """Returns the trace with a new reading and one more correction, and ``context_out`` again."""
    return dataclasses.replace(trace, reading=reading, corrections=(*trace.corrections, correction), history=(*trace.history, trace.reading),
                               context_out=next_context(trace.context_in, reading, trace.turn), prompts=reading.prompts)


def correct(trace: Trace, phrase: int, path: str | None, choice: str | Term | list, model: scriptt16.Model | None = None) -> Trace:
    """Applies a correction of the user to one place of a reading.

    Args:
        trace: The trace.
        phrase: The number of the phrase, as ``scriptt16.block`` counts.
        path: The place inside the term of the phrase. None for the function of the phrase.
        choice: For the function: the name of a function of the world, or
            "nothing". For a place: the ``say`` text of a candidate, a term, or
            words that name a value of the type of the place. For a ``Many``
            place, a list of these.
        model: The decision model. If given, the holes of a chosen function
            or application are filled by the search, as d1 decides. If None,
            they stay open holes.

    Returns:
        The trace with the reading rebuilt at that place, so that
        ``scriptt16.block`` shows the new binding. The correction is
        "request_edited" for the function; "parser_override" if every chosen
        term was among the candidates, and "candidate_injected" otherwise.

    Raises:
        ValueError: If the choice names no function, or no value of the type of the place.
        TypeError: If a chosen term does not fill the place.
    """
    old = phrase_of(trace, phrase)
    text = trace.reading.text
    requests: list[dict] = []
    if path is None:
        if choice != "nothing" and choice not in trace.world.functions:
            raise ValueError(f"{choice!r} is no function of the world, nor 'nothing'")
        term = None
        if choice != "nothing":
            function = trace.world.functions[choice]
            term = filled(trace, phrase, Application(function, {name: Hole(parameter) for name, parameter in function.parameters}), trace.reading.limits.depth, model, requests)
        shares = old.choice.shares if old.choice else {choice: 1.0}
        new = dataclasses.replace(old, choice=Choice(shares, choice), term=term)
        before = {"choice": old.choice.best if old.choice else None, "term": scriptt16.term_record(old.term, text) if old.term else None}
        after = {"choice": choice, "term": scriptt16.term_record(term, text) if term else None}
        kind = "request_edited"
    else:
        current, goal, _, depth = place(trace, phrase, path)
        offered = offered_terms(trace, phrase, path)
        by_words = {scriptt16.say(term, text): term for term in offered}
        injected = False

        def chosen(one: str | Term) -> Term:
            nonlocal injected
            if isinstance(one, str):
                if one in by_words:
                    return filled(trace, phrase, by_words[one], depth - 1, model, requests)
                term = typed_constant(one, goal, trace.world.folder)
                if term is None:
                    raise ValueError(f"{one!r} is no candidate for {path} and names no value of {agree.show(goal)}; the candidates are {list(by_words)}")
            else:
                term = one
            if not any(same_value(term, candidate) for candidate in offered):
                injected = True
            return term

        many = isinstance(goal, Applied) and goal.constructor == agree.MANY
        if many:
            new_term: Term = Several(goal.argument, tuple(chosen(one) for one in (choice if isinstance(choice, list) else [choice])))
        else:
            new_term = chosen(choice)
        wanted = goal.argument if many else goal
        for one in (new_term.terms if many else (new_term,)):
            if not scriptt16.fills(one, element_of(wanted) if not many else wanted):
                raise TypeError(f"{scriptt16.say(one, text)} has the type {agree.show(scriptt16.type_of(one))}, which does not fill {path}: {agree.show(goal)}")
        new = dataclasses.replace(old, term=replaced(old.term, path.split("."), new_term))
        before, after = scriptt16.term_record(current, text), scriptt16.term_record(new_term, text)
        kind = "candidate_injected" if injected else "parser_override"
    reading = with_phrase(trace.reading, new)
    reading = dataclasses.replace(reading, requests=[*reading.requests, *requests])
    return corrected(trace, reading, Correction(kind, phrase, path, before, after, now()))


def undo(trace: Trace) -> Trace:
    """Returns the trace without its last correction, with the reading as it was before it.

    Raises:
        ValueError: If the trace has no correction.
    """
    if not trace.corrections:
        raise ValueError("the trace has no correction to undo")
    reading = trace.history[-1]
    return dataclasses.replace(trace, reading=reading, corrections=trace.corrections[:-1], history=trace.history[:-1],
                               context_out=next_context(trace.context_in, reading, trace.turn), prompts=reading.prompts)


def with_prompts(trace: Trace, prompts: Prompts, model: scriptt16.Model) -> Trace:
    """Reads the message again with edited wordings, and logs a "prompt_edited" correction.

    The phrases of the reading are kept, so d1 gets no join question, unless
    the join wording changed: then the message is cut again. The new reading
    replaces the old one, so a correction before this one no longer shows in
    it; ``undo`` brings the old reading back.

    Args:
        trace: The trace.
        prompts: The edited wordings.
        model: The decision model.

    Returns:
        The trace with the new reading.
    """
    old = trace.reading
    message = None if prompts.join != old.prompts.join else scriptt16.fold(lambda phrase: phrase if phrase.inside else dataclasses.replace(phrase, choice=None, term=None), old.message)
    reading = scriptt16.read(old.text, trace.world, list(trace.replies), model, limits=old.limits, message=message, prompts=prompts, prior_context=trace.context_in)
    reading = dataclasses.replace(reading, id=old.id)
    correction = Correction("prompt_edited", None, None, {"prompts": dataclasses.asdict(old.prompts)}, {"prompts": dataclasses.asdict(prompts), "reading": reading_record(reading)}, now())
    return corrected(trace, reading, correction)


def block_of(trace: Trace) -> str:
    """Returns the lines that Claude receives for the turn: ``scriptt16.block`` of the corrected reading."""
    return scriptt16.block(trace.reading)


# ---- Persistence ----------------------------------------------------------------


def phrase_tree(phrase: Phrase, text: str) -> dict:
    """Converts a phrase and its inner phrases to data that JSON holds, with the exact shares of d1."""
    line: dict = {"start": phrase.start, "end": phrase.end, "brand": phrase.brand.name if phrase.brand else None, "starts_by": phrase.starts_by}
    if phrase.inside:
        line["inside"] = [phrase_tree(inner, text) for inner in phrase.inside]
    if phrase.choice:
        line["choice"] = {"best": phrase.choice.best, "shares": phrase.choice.shares}
    if phrase.term is not None:
        line["term"] = scriptt16.term_record(phrase.term, text)
    return line


def reading_record(reading: Reading) -> dict:
    """Converts a reading to data that JSON holds and ``reading_from_record`` rebuilds.

    The dict is ``scriptt16.record`` of the reading (form 4, for the readers of
    the log) with the phrases as ``phrase_tree`` gives them, the constants, the
    requests, the limits and the wordings.
    """
    return scriptt16.record(reading) | {
        "message": phrase_tree(reading.message, reading.text),
        "constants": [scriptt16.term_record(constant, reading.text) for constant in reading.constants],
        "requests": reading.requests,
        "limits": dataclasses.asdict(reading.limits),
        "prompts": dataclasses.asdict(reading.prompts),
    }


BASES = {"int": int, "str": str, "Path": pathlib.Path, "bool": bool, "NoneType": type(None)}
"""The Python type of each base type that a type tree can name."""


def type_from_tree(shape: dict, world: World) -> Type:
    """Rebuilds a type from its ``agree.tree``, with the types of the world.

    Raises:
        ValueError: If the tree names a type that the world does not have.
    """
    if "constructor" in shape:
        return Applied(CONSTRUCTORS[shape["constructor"]], type_from_tree(shape["of"], world))
    name = next(shape[key] for key in ("sum", "product", "brand", "base") if key in shape)
    if name in world.types:
        return world.types[name]
    if "sum" in shape and not name:
        return Sum("", tuple(type_from_tree(alternative, world) for alternative in shape["alternatives"]))
    if "base" in shape and name in BASES:
        return Base(name, BASES[name])
    raise ValueError(f"the log names the type {name}, which the world does not have")


def subterms(term: Term) -> list[Term]:
    """Returns a term and every term inside it."""
    match term:
        case Application(arguments=inner) | Record(fields=inner):
            return [term, *(found for one in inner.values() for found in subterms(one))]
        case Several(terms=terms):
            return [term, *(found for one in terms for found in subterms(one))]
    return [term]


def term_from_record(record: dict, world: World, text: str, known: typing.Sequence[Term] = ()) -> Term:
    """Rebuilds a term from ``scriptt16.term_record``: its inverse.

    Args:
        record: The record of the term.
        world: The world that the term was built in.
        text: The message whose places the spans of the term index.
        known: Terms already rebuilt, such as the entities of earlier turns. A
            record that is the record of one of them, or of a term inside one,
            gives that term, so that a term carried from an earlier turn comes
            back whole.

    Returns:
        The term, with the origin and the adoption that the record holds. A span keeps its words from ``text`` when they read as the
        record reads; a span of another message, or a value that d1 chose,
        takes its value from the record.

    Raises:
        ValueError: If the record names a function or a type that the world does not have.
    """
    for candidate in (found for term in known for found in subterms(term)):
        if scriptt16.term_record(candidate, "") == record:
            return candidate
    expression = type_from_tree(record["type"], world)
    rebuilt = lambda inner: term_from_record(inner, world, text, known)
    if "constant" in record:
        start, end = record["constant"]
        shown = ast.literal_eval(record["reads"])
        if isinstance(expression, Sum):
            value = next((member for member in expression.alternatives if isinstance(member, Member) and member.words == shown), None)
            if value is None:
                raise ValueError(f"the sum {expression.name} has no member {shown!r}")
        elif isinstance(expression, Base) and expression.python is int:
            value = int(shown)
        elif isinstance(expression, Base) and expression.python is pathlib.Path:
            value = pathlib.Path(shown)
        else:
            span = text[start:end].strip() if 0 <= start <= end <= len(text) else None
            value = span if span is not None and " ".join(span.split()) == shown else shown
        return Constant(expression, value, start, end, record.get("origin"), record.get("adopted_by"))
    if "function" in record:
        if record["function"] not in world.functions:
            raise ValueError(f"the log names the function {record['function']}, which the world does not have")
        arguments = {name: rebuilt(inner) for name, inner in record["arguments"].items()}
        return Application(world.functions[record["function"]], arguments, record.get("origin"), record.get("adopted_by"))
    if "fields" in record:
        return Record(expression, {name: rebuilt(inner) for name, inner in record["fields"].items()})
    if "several" in record:
        return Several(expression.argument, tuple(rebuilt(inner) for inner in record["several"]))
    if "empty" in record:
        return Empty(expression)
    reason = {"reason": record["reason"]} if "reason" in record and "reason" in {field.name for field in dataclasses.fields(Hole)} else {}
    return Hole(expression, **reason)


def phrase_from_tree(line: dict, world: World, text: str, known: typing.Sequence[Term]) -> Phrase:
    """Rebuilds a phrase from ``phrase_tree``."""
    inside = tuple(phrase_from_tree(inner, world, text, known) for inner in line.get("inside", ()))
    choice = Choice(line["choice"]["shares"], line["choice"]["best"]) if "choice" in line else None
    term = term_from_record(line["term"], world, text, known) if "term" in line else None
    return Phrase(line["start"], line["end"], world.types.get(line["brand"]) if line["brand"] else None, inside, line["starts_by"], choice, term)


def reading_from_record(line: dict, world: World, known: typing.Sequence[Term] = ()) -> Reading:
    """Rebuilds a reading from ``reading_record``."""
    text = line["text"]
    constants = [term_from_record(constant, world, text) for constant in line["constants"]]
    return Reading(line["id"], text, phrase_from_tree(line["message"], world, text, (*constants, *known)), constants, line["requests"],
                   Prompts(**line["prompts"]), Limits(**line["limits"]))


def entity_record(entity: Entity) -> dict:
    """Converts an entity to data that JSON holds."""
    return {"id": entity.id, "turn": entity.turn, "version_of": entity.version_of, "origin": entity.origin, "text": entity.text,
            "term": scriptt16.term_record(entity.term, entity.text)}


def entities_from_records(lines: list[dict], world: World, known: typing.Sequence[Term] = ()) -> tuple[Entity, ...]:
    """Rebuilds entities from ``entity_record``. An entity whose term is inside an earlier one shares that term."""
    rebuilt: list[Entity] = []
    for line in lines:
        term = term_from_record(line["term"], world, line["text"], (*known, *(entity.term for entity in rebuilt)))
        rebuilt.append(Entity(line["id"], term, line["turn"], line["version_of"], line["origin"], line["text"]))
    return tuple(rebuilt)


def default_log(world: World) -> pathlib.Path:
    """Returns the log of the folder of a world: ``.scriptt/events.jsonl``."""
    return world.folder / ".scriptt" / "events.jsonl"


def trace_record(trace: Trace) -> dict:
    """Converts a trace to one line of the log.

    The reading is saved as it was before every correction, and each
    correction with what it changed, so that ``load`` rebuilds the corrected
    reading by applying the corrections in order. ``block`` is what the hook
    sent for the corrected reading, for a reader of the log; ``load`` does not use it.
    """
    base = trace.history[0] if trace.history else trace.reading
    return {
        "form": TRACE_FORM,
        "turn": trace.turn,
        "world_hash": trace.world_hash,
        "prompts": dataclasses.asdict(trace.prompts),
        "prompts_hash": scriptt16.prompts_hash(trace.prompts),
        "replies": list(trace.replies),
        "context_in": [entity_record(entity) for entity in trace.context_in],
        "reading": reading_record(base),
        "corrections": [dataclasses.asdict(correction) for correction in trace.corrections],
        "executions": [dataclasses.asdict(execution) for execution in trace.executions],
        "context_out": [entity_record(entity) for entity in trace.context_out],
        "block": block_of(trace),
    }


def save(trace: Trace, file: pathlib.Path | str | None = None) -> pathlib.Path:
    """Appends a trace to the log as one JSON line.

    Args:
        trace: The trace.
        file: The log. None means ``.scriptt/events.jsonl`` of the folder of the world.

    Returns:
        The path of the log.
    """
    path = pathlib.Path(file) if file is not None else default_log(trace.world)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as log:
        log.write(json.dumps(trace_record(trace), ensure_ascii=False) + "\n")
    return path


def applied_correction(trace: Trace, correction: Correction, world: World) -> Trace:
    """Applies one recorded correction to a rebuilt trace, from what the correction recorded."""
    known = tuple(entity.term for entity in trace.context_in)
    text = trace.reading.text
    if correction.kind == "prompt_edited":
        reading = reading_from_record(correction.after["reading"], world, known)
        return corrected(trace, reading, correction)
    old = phrase_of(trace, correction.phrase)
    after = correction.after
    if correction.path is None:
        term = term_from_record(after["term"], world, text, (*trace.reading.constants, *known)) if after["term"] else None
        shares = old.choice.shares if old.choice else {after["choice"]: 1.0}
        new = dataclasses.replace(old, choice=Choice(shares, after["choice"]), term=term)
    else:
        term = term_from_record(after, world, text, (*trace.reading.constants, *known))
        new = dataclasses.replace(old, term=replaced(old.term, correction.path.split("."), term))
    return corrected(trace, with_phrase(trace.reading, new), correction)


def trace_from_record(line: dict, world: World) -> Trace:
    """Rebuilds a trace from one line of the log, applying its corrections in order.

    Raises:
        ValueError: If the line is not a trace line, or its world hash is not the hash of ``world``.
    """
    if line.get("form") != TRACE_FORM:
        raise ValueError(f"the line has the form {line.get('form')!r}, not {TRACE_FORM!r}")
    if line["world_hash"] != scriptt16.world_hash(world):
        raise ValueError(f"the trace was read with the world {line['world_hash']}, and this world is {scriptt16.world_hash(world)}")
    context_in = entities_from_records(line["context_in"], world)
    known = tuple(entity.term for entity in context_in)
    reading = reading_from_record(line["reading"], world, known)
    executions = tuple(Execution(**execution) for execution in line["executions"])
    trace = Trace(line["turn"], context_in, reading.prompts, line["world_hash"], reading, (), executions,
                  next_context(context_in, reading, line["turn"]), tuple(line["replies"]), (), world)
    for correction in line["corrections"]:
        trace = applied_correction(trace, Correction(**correction), world)
    return trace


def trace_lines(file: pathlib.Path | str) -> list[dict]:
    """Returns every trace line of a log, in order. Lines of other forms are left out."""
    path = pathlib.Path(file)
    if not path.exists():
        return []
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [line for line in lines if line.get("form") == TRACE_FORM]


def load(file: pathlib.Path | str, world: World, turn: int | None = None) -> Trace:
    """Rebuilds the latest saved trace of a log, or the latest of one turn.

    Args:
        file: The log.
        world: The world that the trace was read with.
        turn: The turn to load. None means the last trace line of the log.

    Returns:
        The trace, with every correction applied in order.

    Raises:
        ValueError: If the log has no trace line (of that turn).
    """
    lines = [line for line in trace_lines(file) if turn is None or line["turn"] == turn]
    if not lines:
        raise ValueError(f"{file} has no trace line" + (f" of turn {turn}" if turn is not None else ""))
    return trace_from_record(lines[-1], world)


def world_of_folder(folder: pathlib.Path) -> World:
    """Loads the world beside the log of a folder: ``.scriptt/world.py``, with the folder for its paths."""
    source = folder / ".scriptt" / "world.py"
    module = types.ModuleType("world")
    module.__file__ = str(source)
    exec(compile(source.read_text(), str(source), "exec"), vars(module))
    return agree.load(module, folder)


def hook_block(folder: pathlib.Path | str, world: World | None = None) -> str:
    """Returns what the hook sends: the block of the latest saved trace of a folder.

    Args:
        folder: The folder. The log is its ``.scriptt/events.jsonl``.
        world: The world of the trace. None means ``.scriptt/world.py`` of the folder.

    Returns:
        ``block_of`` the trace that ``load`` rebuilds, with every correction applied.
    """
    folder = pathlib.Path(folder)
    world = world or world_of_folder(folder)
    return block_of(load(folder / ".scriptt" / "events.jsonl", world))
