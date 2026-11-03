"""The World is an append-only log of facts. It has views of the log on a date and at a
time."""

import datetime as dt
import inspect
import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from string.templatelib import Interpolation, Template
import types
from typing import TYPE_CHECKING, Any, ClassVar, Self, Union, get_args, get_origin

import duckdb

if TYPE_CHECKING:
    import polars as pl

from ._store import Row as _StoreRow, Store

from ._fact import Fact, Key, _plain, _shown
from ._say import say
from ._facts import Facts, Row
from ._time import Moment, Step, day, end_of, step, when


class Op(Enum):
    """What 1 entry of the log does. Read it from `Entry.op`."""

    # the fact is true from true_from (until true_until, or until the next version)
    ADD = "add"
    """The fact is true from `true_from`, until `true_until` or until the next version.
    """
    # the fact stops being true on a date; views before that date still see it
    END = "end"
    """The fact stops being true on a date. Views before that date still see it."""
    # the fact was never true; views known before the retract still see it
    RETRACT = "retract"
    """The fact was never true. Views that you knew before the retract still see it."""
    SAME = "same"  # 2 facts are 1 thing
    """Two facts are 1 thing."""
    RENAME = "rename"  # a field of a type has a new name
    """A field of a type has a new name."""


class Match(Enum):
    """The kind of a mapping between 2 terms after SKOS. `World.map` takes a `Match`.

    Example:
        ```python
        from scriptt.world import Match

        Match.NARROWER.value  # -> 'narrower'
        ```
    """

    EXACT = "exact"
    """The 2 terms mean the same."""
    CLOSE = "close"
    """The 2 terms mean nearly the same."""
    BROADER = "broader"
    """The second term is wider than the first."""
    NARROWER = "narrower"
    """The second term is narrower than the first."""
    RELATED = "related"
    """The 2 terms are related in some other way."""


class Mapping(Fact):
    """A fact that says that a term in 1 word list maps to a term in another word list.
    `World.map` adds one.

    Attributes:
        a: The term in the first word list. Part of the key.
        b: The term in the other word list. Part of the key.
        match: The kind of the mapping.
    """

    a: Key[str]
    b: Key[str]
    match: Match


class Rel(Enum):
    """The kind of link between a thing and the thing above it. `World.place` takes a
    `Rel`.

    Example:
        ```python
        from scriptt.world import Rel

        Rel.IS_A.value  # -> 'is a'
        ```
    """

    PART_OF = "part of"
    """The thing is a part of the parent: a task is in a list, a note is under a task.
    """
    IS_A = "is a"
    """The thing is a kind of the parent: a senior software engineer is a software
    engineer."""


class Under(Fact):
    """A fact that says that a thing is directly under a parent by 1 kind of link.
    `World.place` adds one.

    A thing has 1 parent for each kind of link. A later `place` of the same child and
    kind replaces the parent.

    Attributes:
        child: The thing. Part of the key.
        rel: The kind of link. Part of the key.
        parent: The thing directly above it.
    """

    child: Key[str]
    rel: Key[Rel]
    parent: str


@dataclass(frozen=True, slots=True)
class Entry:
    """1 entry of the log. It has 3 times.

    - When the fact is true.
    - When you got it.
    - When you wrote it.

    `World.history` gives the entries of a fact. `World.facts` gives facts and not
    entries.

    Attributes:
        seq: The position of the entry in the log. The first entry is 1.
        op: What the entry does.
        type_name: The name of the type of the fact, from `Fact.type_name`.
        identity: The key values of the fact, as JSON text.
        body: The fields of the fact as a dictionary. It is empty for an end or a
            retract. It contains `same_as` for a same
            entry and `old` and `new` for a rename entry.
        true_from: The first day on which the fact is true, or `None` for all time
            before `true_until`.
        true_until: The day on which the fact stops being true or `None` if it has no
            end. This day is not included.
        known: The time at which you got the fact.
        written: The time at which the entry went into the log.
        source: The text that says where the entry came from.

    Example:
        ```python
        report = today.one(Task, id="t2")
        entry = today.history(report)[0]
        entry.op.value, entry.source  # -> ('add', 'me')
        ```
    """

    seq: int
    op: Op
    type_name: str
    identity: str
    body: dict[str, Any]
    true_from: dt.date | None
    true_until: dt.date | None
    known: dt.datetime
    written: dt.datetime
    source: str

    def fact[T: Fact](self, of: type[T]) -> T:
        """Read the body of an add entry as a fact.

        Args:
            of: The type of the fact.

        Returns:
            The fact, checked by the type `of`.

        Raises:
            pydantic.ValidationError: The body does not fit the type. This is the case
                for an end entry or a retract entry or a same entry.

        Example:
            ```python
            report = today.one(Task, id="t2")
            today.history(report)[0].fact(Task) == report  # -> True
            ```
        """
        return of.model_validate(self.body)

    def __describe__(self) -> Template:
        """Give the t-string that `say` uses for this entry. It says what the entry did
        and when you got the fact and where from.

        Returns:
            A t-string. An example is "added on 2 Nov 2026, 09:00 from me,
            true from 2 Nov 2026".

        Example:
            ```python
            from scriptt.world import say

            report = today.one(Task, id="t2")
            say(t"{today.history(report)[0]}")
            # -> 'added on 2 Nov 2026, 09:00 from me, true from 2 Nov 2026'
            ```
        """
        what = {
            Op.ADD: "added",
            Op.END: "ended",
            Op.RETRACT: "retracted",
            Op.SAME: "joined",
            Op.RENAME: "renamed",
        }[self.op]
        return t"{what} on {self.known} from {self.source}, true from {self.true_from}"


@dataclass(frozen=True, slots=True)
class Origin[T: Fact, V]:
    """The value of 1 field of 1 fact and the log entry that wrote that value.
    `World.origin` makes it.

    Attributes:
        fact: The fact.
        field: The name of the field.
        value: The value of the field.
        entry: The entry of the log that wrote this value.

    Example:
        ```python
        report = today.one(Task, id="t2")
        origin = today.origin(report, lambda t: t.title)
        origin.value, origin.entry.source  # -> ('Send the report', 'me')
        ```
    """

    fact: T
    field: str
    value: V
    entry: Entry

    def __describe__(self) -> Template:
        """Give the t-string that `say` uses for this origin. It has the value and the
        field and the time you got it and the source.

        Returns:
            A t-string. An example is "Send the report, the title known on 2 Nov
            2026, 09:00 from me".

        Example:
            ```python
            from scriptt.world import say

            report = today.one(Task, id="t2")
            say(t"{today.origin(report, lambda t: t.title)}")
            # -> 'Send the report, the title known on 2 Nov 2026, 09:00 from me'
            ```
        """
        return (
            t"{self.value}, the {type(self.fact).label(self.field)} known on "
            t"{self.entry.known} from {self.entry.source}"
        )


class _Probe:
    """Records the field that a function such as `lambda f: f.p` reads."""

    def __init__(self) -> None:
        self.names: list[str] = []

    def __getattr__(self, name: str) -> _Probe:
        self.names.append(name)
        return self


@dataclass(frozen=True, slots=True)
class Change[T: Fact]:
    """One fact that changed between 2 views. It has how it was and how it is.

    Attributes:
        before: The fact in the earlier view.
        after: The fact in the later view.
    """

    before: T
    after: T

    def fields(self) -> dict[str, tuple[Any, Any]]:
        """Give the fields that changed.

        Returns:
            A dictionary from field name to `(before, after)`. A field that did not
            change is not in it.

        Example:
            ```python
            note = today.one(Note, task="t2")
            change = (today.suppose(add=[note.but(text="Done")]) - today).changed[0]
            change.fields()  # -> {'text': ('Use the new template', 'Done')}
            ```
        """
        return {
            n: (getattr(self.before, n), getattr(self.after, n))
            for n in type(self.after).model_fields
            if getattr(self.before, n) != getattr(self.after, n)
        }

    def __repr__(self) -> str:
        what = ", ".join(
            f"{n} {_shown(a)} -> {_shown(b)}" for n, (a, b) in self.fields().items()
        )
        key = ", ".join(str(getattr(v, "value", v)) for v in self.after.identity)
        return f"{type(self.after).__name__}({key}): {what}"


@dataclass(frozen=True, slots=True)
class Changes[T: Fact]:
    """The difference `later - earlier` between 2 views. `World.__sub__` makes it.

    `bool(changes)` is true if anything differs. Printing it shows one mark for each
    fact.

    - `+` for an added fact.
    - `-` for a removed fact.
    - `~` for a changed fact.

    Attributes:
        added: The facts that only the later view has.
        removed: The facts that only the earlier view has.
        changed: The facts that are in both views with different fields, as `Change`
            objects.
    """

    added: Facts[T]
    removed: Facts[T]
    changed: Facts[Change[T]]
    kinds: tuple[
        type[Fact], ...
    ] = ()  # the types of the 2 views: a field name is checked against them

    def of[U: Fact](self, kind: type[U]) -> Changes[U]:
        """Keep only the changes to facts of 1 type.

        Args:
            kind: The type of fact.

        Returns:
            A new `Changes` that contains only facts of `kind`. They are typed as
            `kind`.

        Example:
            ```python
            later, earlier = today, todo.on("4 Nov 2026").known("2 Nov 2026 09:00")
            (later - earlier).of(Task).added.count()  # -> 1
            ```
        """
        return Changes(
            Facts(f for f in self.added if isinstance(f, kind)),
            Facts(f for f in self.removed if isinstance(f, kind)),
            Facts(
                Change(c.before, c.after)
                for c in self.changed
                if isinstance(c.before, kind) and isinstance(c.after, kind)
            ),
            tuple(k for k in self.kinds if issubclass(k, kind)) or (kind,),
        )

    def where(
        self, rule: Callable[[T], object] | None = None, /, **equal: Any
    ) -> Changes[T]:
        """Keep only the changes whose fact agrees. The fact after the change counts for
        a changed fact.

        Args:
            rule: A function that takes a fact and gives a true or false value. The
                default `None` means no rule.
            **equal: Fields that must equal a value. An example is
                `source=Source.OWNER`. A fact without the field does not agree.

        Returns:
            A new `Changes`.

        Example:
            ```python
            later, earlier = today, todo.on("4 Nov 2026").known("2 Nov 2026 09:00")
            (later - earlier).of(Task).where(list="home").added.count()  # -> 1
            ```
        """
        kinds = self.kinds or tuple(
            {
                type(f)
                for f in [*self.added, *self.removed, *(c.after for c in self.changed)]
            }
        )
        unknown = [
            k for k in equal if kinds and not any(k in t.model_fields for t in kinds)
        ]
        if (
            unknown
        ):  # checked against the types, not against the facts that happen to be here
            raise AttributeError(
                f"no type of these changes has the field {', '.join(unknown)}; the "
                f"types are {', '.join(t.__name__ for t in kinds)}"
            )
        keep = lambda f: (
            (rule is None or rule(f))
            and all(getattr(f, k, _NOTHING) == v for k, v in equal.items())
        )  # noqa: E731
        return Changes(
            self.added.where(keep),
            self.removed.where(keep),
            self.changed.where(lambda c: keep(c.after)),
            self.kinds,
        )

    def __bool__(self) -> bool:
        return bool(len(self.added) or len(self.removed) or len(self.changed))

    def __repr__(self) -> str:
        lines = [f"+ {f!r}" for f in self.added] + [f"- {f!r}" for f in self.removed]
        lines += [f"~ {c!r}" for c in self.changed]
        return "\n".join(lines) or "(no changes)"


@dataclass(frozen=True, slots=True)
class Conflict:
    """A field on which the members of 1 thing disagree after `World.same`.

    Attributes:
        identity: The key values of the thing as a tuple.
        field: The name of the field.
        values: The different values that the members give. It has 2 values or more.
    """

    identity: tuple
    field: str
    values: tuple[Any, ...]


@dataclass(frozen=True, slots=True)
class Problem:
    """1 problem that `World.problems` found. It is a fact that breaks a rule.

    Attributes:
        rule: The rule in words. This is the goal's name or "Task.list points to a
            TodoList".
        fact: The fact that breaks it. It is None when the rule is about the whole view
            (a count goal not met).
        field: The field at fault, or None.
        value: The value at fault, or None.
        message: What is wrong in 1 sentence.
    """

    rule: str
    fact: Fact | None
    field: str | None
    value: Any
    message: str

    def __table__(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "fact": self.fact,
            "field": self.field,
            "value": self.value,
        }

    def __describe__(self) -> Template:
        return t"{self.message}"


@dataclass(frozen=True)
class Goal[T: Fact]:
    """A rule over the facts of 1 type and a number to reach. `World.check` tests it.
    `view.steps(...).map(lambda v: v.check(goal))` tests it on several days.

    There are 3 kinds of goal:

    - A count goal (the default) needs at least `at_least` facts that agree with `rule`.
    - A sum goal (`total` is set) needs the sum of `total` over the facts that agree to
    be at least `at_least`.
    - An every goal (`every=True`) needs every fact to agree. The result lists the facts
    that do not.

    `rule` takes the fact or the fact and the view. A rule with 2 parameters can read
    other types from the view.

    Attributes:
        name: A short name for the goal. It shows in the result.
        of: The type of fact that the goal tests.
        rule: A function that takes a fact (or a fact and a view) and gives a true or
            false value. The default accepts every fact.
        at_least: The number to reach. The default is 1.
        total: A function that takes a fact and gives a number or `None`. The default
            `None` means count the facts.
        every: Whether every fact must agree. The default is `False`.
        by: The day by which the goal must be met. The default `None` means no day. A
            check after this day is `late`.

    Example:
        ```python
        open_at_home = Goal(
            "at least 3 open tasks at home",
            Task,
            lambda t: t.list == "home" and t.status == Status.OPEN,
            at_least=3,
        )
        today.check(open_at_home).met  # -> True
        ```
    """

    name: str
    of: type[T]
    rule: Callable[..., bool] = lambda fact: True
    at_least: float = 1
    total: Callable[[T], float | None] | None = None
    every: bool = False
    by: dt.date | None = None


@dataclass(frozen=True, slots=True)
class GoalResult[T: Fact]:
    """The result of one check of a goal on one date. `World.check` makes it.

    Attributes:
        goal: The name of the goal.
        on: The date of the view that was checked.
        met: Whether the goal is met.
        found: The count or the sum that the facts give. For an every goal it is the
            number of facts that agree.
        needed: The number to reach. For an every goal it is the number of facts of the
            type.
        late: Whether the view's date is after the `by` day of the goal.
        failing: The facts that do not agree with the rule.
    """

    goal: str
    on: dt.date
    met: bool
    found: int | float
    needed: int | float
    late: bool
    failing: Facts[T]

    def __table__(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "on": self.on,
            "met": self.met,
            "found": self.found,
            "needed": self.needed,
            "late": self.late,
        }

    def __repr__(self) -> str:
        return say(
            t"{self.goal} on {self.on}: {'met' if self.met else 'not met'} "
            t"({self.found} of {self.needed}){' late' if self.late else ''}"
        )


_WHAT_IF_SEQ = 10**12
_NOTHING = object()  # a field a fact does not have: equal to no value
_FAR = dt.datetime.max.replace(microsecond=0)


def _entry(row: _StoreRow) -> Entry:
    return Entry(
        row.seq,
        Op(row.op),
        row.type_name,
        row.identity,
        row.body,
        row.true_from,
        row.true_until,
        row.known,
        row.written,
        row.source,
    )


def _row(entry: Entry) -> _StoreRow:
    return _StoreRow(
        entry.seq,
        entry.op.value,
        entry.type_name,
        entry.identity,
        entry.body,
        entry.true_from,
        entry.true_until,
        entry.known,
        entry.written,
        entry.source,
    )


def _identity(of: type[Fact], values: Iterable[Any]) -> str:
    return json.dumps(
        [
            getattr(v, "value", v)
            if isinstance(v, Enum)
            else str(v)
            if isinstance(v, dt.date)
            else v
            for v in values
        ]
    )


def _target(fact: Fact | type[Fact], key: dict[str, Any]) -> tuple[type[Fact], str]:
    """The pair `(type, identity)` from a fact or from a type and its key fields."""
    if isinstance(fact, Fact):
        return type(fact), _identity(type(fact), fact.identity)
    missing = set(fact.key_fields()) - set(key)
    if missing:
        raise KeyError(
            f"{fact.__name__}: give the key fields {', '.join(sorted(missing))}"
        )
    return fact, _identity(fact, (key[n] for n in fact.key_fields()))


def _refs_or_none(of: type[Fact]) -> dict[str, type[Fact]]:
    """The `Ref` fields of a type. It is none if they cannot be read. `problems` reports
    that type."""
    try:
        return of.refs()
    except TypeError, NameError:
        return {}


def _each(value: Any) -> tuple[Any, ...]:
    """The keys in a `Ref` field. A field gives no key or 1 key or each key of a "
    "list."""
    return (
        ()
        if value is None
        else tuple(value)
        if isinstance(value, (tuple, list))
        else (value,)
    )


def _term(value: Any) -> str:
    return str(getattr(value, "value", value))


@dataclass(frozen=True)
class World:
    """A log of facts and a view of it on 1 date with what you knew at 1 time. Every
    view of 1 log shares that log.

    Make a world with `World.new` or `World.open`. Do not call the constructor. Writing
    calls such as `add` and `end` and `retract`
    add to the log. Every other call gives a new view or an answer. It does not change
    the log.

    A view has 3 fields. You can read them. These calls make views with other values.

    - `on`
    - `known`
    - `at`
    - `during`
    - `steps`

    Attributes:
        on_date: The day of the view. The default is today. In a `during` window this is
            the first day.
        known_time: The latest time that the view knows. The default `None` means every
            entry of the log.
        until_date: The end of a `during` window. This day is not in the window. The
            default `None` means the window is the single day `on_date`.

    Example:
        ```python
        from scriptt.world import World

        todo = World.new(TodoList, Task)
        todo.add(
            Task(id="t9", list="home", title="Buy tea"),
            source="me",
            true_from="2 Nov 2026",
        )
        todo.on("2 Nov 2026").one(Task, id="t9").title  # -> 'Buy tea'
        ```
    """

    _store: Store = field(default_factory=Store, repr=False)
    _types: dict[str, type[Fact]] = field(default_factory=dict, repr=False)
    on_date: dt.date = field(default_factory=dt.date.today)
    known_time: dt.datetime | None = None
    until_date: dt.date | None = None
    _supposed: tuple[Entry, ...] = field(default=(), repr=False)
    _cache: dict = field(default_factory=dict, repr=False, compare=False)
    _tables_made: ClassVar[int] = 0

    @classmethod
    def open(
        cls, path: str | Path, *types: type[Fact], on: Moment | None = None
    ) -> World:
        """Open a world that is kept in a DuckDB file. An existing file keeps its log.
        So you read it again.

        Args:
            path: The path of the DuckDB file. A new file is made if it does not exist.
            *types: The types of fact that the file contains. `export` and `later -
                earlier` read the types that you name here or that you add later.
            on: The day of the first view. The default `None` means today.

        Returns:
            A world. Its `size` is the number of entries already in the file.

        Example:
            ```python
            import pathlib
            import tempfile
            from scriptt.world import World

            path = pathlib.Path(tempfile.mkdtemp()) / "tasks.duckdb"
            kept = World.open(path, Task)
            kept.add(Task(id="t9", list="home", title="Buy tea"), source="me")
            kept.size  # -> 1
            ```
        """
        world = cls(Store(path), on_date=day(on) or dt.date.today())
        for t in (*types, Mapping, Under):
            world._types[t.type_name()] = t
        return world

    @classmethod
    def new(cls, *types: type[Fact], on: Moment | None = None) -> World:
        """Make a world that is kept in memory. The log is lost when the program ends.
        Use `World.open` to keep it.

        Args:
            *types: The types of fact that the world contains. `export` and `later -
                earlier` read the types that you name here or that you add later.
            on: The day of the first view. The default `None` means today.

        Returns:
            A new empty world. The built-in types `Mapping` and `Under` are always
            included.

        Example:
            ```python
            from scriptt.world import World

            fresh = World.new(TodoList, Task, on="2 Nov 2026")
            fresh.size  # -> 0
            fresh.on_date  # -> datetime.date(2026, 11, 2)
            ```
        """
        world = cls(on_date=day(on) or dt.date.today())
        for t in (*types, Mapping, Under):
            world._types[t.type_name()] = t
        return world

    @property
    def size(self) -> int:
        """The number of entries in the log.

        Each of these calls adds 1 entry.

        - `add`
        - `end`
        - `retract`
        - `same`
        - `map`
        - `place`
        - `rename`

        A supposed change is not an entry.

        Example:
            ```python
            todo.size  # -> 11
            ```
        """
        return self._store.count()

    # O3 write
    # ----------------------------------------------------------------------------------
    def _write(
        self,
        op: Op,
        of: type[Fact],
        identity: str,
        body: dict,
        source: str,
        true_from: Moment | None = None,
        true_until: Moment | None = None,
        known: Moment | None = None,
    ) -> Self:
        self._types[of.type_name()] = (
            of  # the newest declaration of a type is the one that reads the log
        )
        now = dt.datetime.now()
        self._store.append(
            _StoreRow(
                0,
                op.value,
                of.type_name(),
                identity,
                body,
                day(true_from),
                day(true_until),
                when(known) if known is not None else now,
                now,
                source,
            )
        )
        return self

    def add(
        self,
        fact: Fact,
        *,
        source: str,
        true_from: Moment | None = None,
        true_until: Moment | None = None,
        true_on: Moment | None = None,
        known: Moment | None = None,
        once: bool = False,
    ) -> Self:
        """Add a fact to the log. Give where it came from and when it is true and known.

        Use `true_from` and `true_until` for a period. Use `true_on` for 1 day. A fact
        with none of them is true for all time.
        A new add with the same key is a new version of the fact. `Forward[...]` fields
        may not move back.

        Args:
            fact: The fact to add.
            source: Text that says where the fact came from. It is not optional.
            true_from: The first day on which the fact is true. The default `None` means
                the fact has always been true.
            true_until: The day on which the fact stops being true. This day is not
                included. The default `None` means no end.
            true_on: One day on which the fact is true. It sets `true_from` to that day
                and `true_until` to the next day.
                The default is `None`.
            known: The time at which you got the fact. The default `None` means now.
            once: Whether to do nothing if this source already gave this version with
                the same dates. The default is
                `False`. Use `True` so that you can read a file again without adding its
                facts twice.

        Returns:
            The same world. So you can chain calls.

        Raises:
            ValueError: A date or time in the text form that `when` refuses. An example
                is "8/10/2026".
            ValueError: A `Forward[...]` field of the fact is earlier in the enum than
                in the last version.

        Example:
            ```python
            listed = World.new(Task)
            listed.add(
                Task(id="t9", list="home", title="Buy tea"),
                source="me",
                true_from="2 Nov 2026",
                known="2 Nov 2026 09:00",
            )
            listed.add(
                Task(id="t9", list="home", title="Buy tea"),
                source="me",
                true_from="2 Nov 2026",
                known="2 Nov 2026 09:00",
                once=True,
            )
            listed.size  # -> 1
            listed.on("2 Nov 2026").get(Task, id="t9").title  # -> 'Buy tea'
            ```
        """
        of = type(fact)
        if true_on is not None:
            true_from = on_day = day(true_on)
            true_until = on_day + dt.timedelta(days=1) if on_day else None
        ident, body = _identity(of, fact.identity), fact.model_dump(mode="json")
        mine = (
            [
                _entry(r)
                for r in self._store.entries(
                    kind=of.type_name(), identity=ident, known=_FAR
                )
            ]
            if once or of.forward_fields()
            else []
        )  # the log is read only for `once` and for `Forward` fields
        if once and any(
            e.op is Op.ADD
            and e.source == source
            and e.body == body
            and (e.true_from, e.true_until) == (day(true_from), day(true_until))
            for e in mine
        ):
            return self
        last = next((e for e in reversed(mine) if e.op is Op.ADD), None)
        if last is not None:
            previous = of.model_validate(last.body)
            for name in of.forward_fields():
                order = list(_plain(of.model_fields[name].annotation)[0])
                before, after = getattr(previous, name), getattr(fact, name)
                if order.index(after) < order.index(before):
                    raise ValueError(
                        f"{of.__name__} {fact.identity}: {name} cannot go back from "
                        f"{before.value} to {after.value}"
                    )
        return self._write(
            Op.ADD, of, ident, body, source, true_from, true_until, known
        )

    def end(
        self,
        fact: Fact | type[Fact],
        /,
        *,
        on: Moment,
        source: str,
        known: Moment | None = None,
        **key: Any,
    ) -> Self:
        """Say that a fact stops being true on a day. Views before that day still see
        it.

        An end cuts the versions that start before it. An `add` from the end day on
        starts a new period.

        Args:
            fact: A fact or the type of the fact. If you give a type, also give the key
                fields as keyword arguments.
            on: The day on which the fact stops being true. This day is not included.
            source: Text that says where this information came from.
            known: The time at which you got this information. The default `None` means
                now.
            **key: The key fields of the fact when `fact` is a type.

        Returns:
            The same world.

        Raises:
            ValueError: A date or time in the text form that `when` refuses. An example
                is "8/10/2026".
            KeyError: `fact` is a type and you did not give all of its key fields.

        Example:
            ```python
            listed = World.new(Task)
            listed.add(
                Task(id="t9", list="home", title="Buy tea"),
                source="me",
                true_from="2 Nov 2026",
            )
            listed.end(Task, id="t9", on="4 Nov 2026", source="me: not needed")
            listed.on("3 Nov 2026").get(Task, id="t9").title  # -> 'Buy tea'
            listed.on("4 Nov 2026").get(Task, id="t9")  # -> None
            ```
        """
        of, ident = _target(fact, key)
        return self._write(Op.END, of, ident, {}, source, None, on, known)

    def retract(
        self,
        fact: Fact | type[Fact],
        /,
        *,
        source: str,
        known: Moment | None = None,
        **key: Any,
    ) -> Self:
        """Say that a fact was never true. Views that you knew before the retract still
        see it.

        The log keeps the fact and adds a retract entry.

        Args:
            fact: A fact or the type of the fact. If you give a type, also give the key
                fields as keyword arguments.
            source: Text that says where this information came from.
            known: The time at which you got this information. The default `None` means
                now.
            **key: The key fields of the fact when `fact` is a type.

        Returns:
            The same world.

        Raises:
            KeyError: `fact` is a type and you did not give all of its key fields.

        Example:
            ```python
            listed = World.new(Task)
            listed.add(
                Task(id="t9", list="home", title="Buy tea"),
                source="me",
                known="2 Nov 2026 20:00",
            )
            listed.retract(
                Task,
                id="t9",
                source="me: typed by mistake",
                known="2 Nov 2026 21:00",
            )
            listed.on("3 Nov 2026").get(Task, id="t9")  # -> None
            listed.known("2 Nov 2026 20:30").on("3 Nov 2026").get(
                Task, id="t9"
            ).title  # -> 'Buy tea'
            listed.size  # -> 2
            ```
        """
        of, ident = _target(fact, key)
        return self._write(Op.RETRACT, of, ident, {}, source, known=known)

    # O5, O6, O7, O12
    # ----------------------------------------------------------------------------------
    def same(
        self, a: Fact, b: Fact, *, source: str, known: Moment | None = None
    ) -> Self:
        """Say that 2 facts are 1 thing.

        The thing keeps the identity of the fact that joined first. Its fields merge.
        The newest value that is not `None`
        wins. A later `same` that repeats or reverses a join changes nothing. Use
        `conflicts` to see fields that disagree.

        Args:
            a: The first fact.
            b: The second fact. It must have the same type as `a`.
            source: Text that says where this information came from.
            known: The time at which you got this information. The default `None` means
                now.

        Returns:
            The same world.

        Raises:
            TypeError: `a` and `b` are not facts of 1 type.

        Example:
            ```python
            lists = World.new(Task)
            a = Task(id="t9", list="home", title="Buy tea")
            b = Task(id="t10", list="home", title="Get tea")
            lists.add(a, source="me", true_from="2 Nov 2026").add(
                b, source="me", true_from="2 Nov 2026"
            )
            lists.same(a, b, source="me: one task")
            lists.on("2 Nov 2026").facts(Task).count()  # -> 1
            ```
        """
        if type(a) is not type(b):
            raise TypeError("same() needs 2 facts of 1 type")
        return self._write(
            Op.SAME,
            type(a),
            _identity(type(b), b.identity),
            {"same_as": _identity(type(a), a.identity)},
            source,
            known=known,
        )

    def map(
        self,
        a: Any,
        b: Any,
        match: Match,
        *,
        source: str,
        true_from: Moment | None = None,
        known: Moment | None = None,
    ) -> Self:
        """Say that a term in 1 word list maps to a term in another.

        This adds a `Mapping` fact. Read the mappings of a term with `mapped`.

        Args:
            a: The term in the first word list. An enum member uses its value.
            b: The term in the other word list.
            match: The kind of the mapping.
            source: Text that says where this information came from.
            true_from: The first day on which the mapping is true. The default `None`
                means always.
            known: The time at which you got this information. The default `None` means
                now.

        Returns:
            The same world.

        Example:
            ```python
            from scriptt.world import Match, World

            terms = World.new()
            terms.map("shopping", "errands", Match.NARROWER, source="me")
            terms.mapped("shopping").count()  # -> 1
            ```
        """
        return self.add(
            Mapping(a=_term(a), b=_term(b), match=match),
            source=source,
            true_from=true_from,
            known=known,
        )

    def place(
        self,
        child: Any,
        *,
        under: Any,
        source: str,
        rel: Rel = Rel.PART_OF,
        true_from: Moment | None = None,
        true_until: Moment | None = None,
        known: Moment | None = None,
    ) -> Self:
        """Say that a thing is directly under a parent. The thing is a part of the
        parent (the default) or a kind of the parent (`rel=Rel.IS_A`).

        This adds an `Under` fact. A thing has 1 parent for each kind of link. A later
        `place` of the same child and
        kind replaces the parent. Read the tree with these calls.

        - `parents`
        - `children`
        - `ancestors`
        - `descendants`

        Args:
            child: The thing. An enum member uses its value.
            under: The parent.
            rel: The kind of link. The default is `Rel.PART_OF`.
            source: Text that says where this information came from.
            true_from: The first day on which the place is true. The default `None`
                means always.
            true_until: The day on which it stops. This day is not included. The default
                `None` means no end.
            known: The time at which you got this information. The default `None` means
                now.

        Returns:
            The same world.

        Raises:
            ValueError: A date or time in the text form that `when` refuses. An example
                is "8/10/2026".

        Example:
            ```python
            tree = World.new()
            tree.place("Buy milk", under="Groceries", source="me")
            tree.parents("Buy milk").first()  # -> 'Groceries'
            ```
        """
        return self.add(
            Under(child=_term(child), rel=rel, parent=_term(under)),
            source=source,
            true_from=true_from,
            true_until=true_until,
            known=known,
        )

    def rename(
        self,
        of: type[Fact],
        *,
        old: str,
        new: str,
        source: str,
        known: Moment | None = None,
    ) -> Self:
        """Say that a field of a type now has a new name. Earlier entries are read with
        the new name.

        Declare the new field on the type first.

        Args:
            of: The type with the new field already declared.
            old: The old name of the field.
            new: The new name of the field.
            source: Text that says where this information came from.
            known: The time at which you got this information. The default `None` means
                now.

        Returns:
            The same world.

        Raises:
            KeyError: The type has no field with the new name.

        Example:
            ```python
            class Chore(Fact, name="chore"):
                id: Key[str]
                hours: float


            class ChoreNow(Fact, name="chore"):
                id: Key[str]
                minutes: float


            chores = World.new(Chore)
            chores.add(Chore(id="t9", hours=1.5), source="me")
            chores.rename(ChoreNow, old="hours", new="minutes", source="me: new name")
            chores.get(ChoreNow, id="t9").minutes  # -> 1.5
            ```
        """
        if new not in of.model_fields:
            raise KeyError(
                f"{of.__name__} has no field {new!r}: declare the new field on the "
                f"type first"
            )
        return self._write(
            Op.RENAME, of, "*", {"old": old, "new": new}, source, known=known
        )

    # O9 views
    # ----------------------------------------------------------------------------------
    def on(self, date: Moment) -> World:
        """Give a view of the world on a day.

        The view keeps the facts that are true on that day. It does not change what the
        view knows.

        Args:
            date: The day. A time of day is ignored. A time zone does not move the day.

        Returns:
            A new view of the same log.

        Raises:
            ValueError: A date or time in the text form that `when` refuses. An example
                is "8/10/2026".

        Example:
            ```python
            todo.on("2 Nov 2026").facts(Task).count()  # -> 5
            todo.on("4 Nov 2026").facts(Task).count()  # -> 6
            ```
        """
        return replace(self, _cache={}, on_date=day(date), until_date=None)

    def known(self, time: Moment) -> World:
        """Give a view that knows only what you knew by a time.

        Args:
            time: The time. A date with no time of day means the end of that day.

        Returns:
            A new view of the same log. Its `known_time` is the time.

        Raises:
            ValueError: A date or time in the text form that `when` refuses. An example
                is "8/10/2026".

        Example:
            ```python
            view = todo.on("4 Nov 2026").known("2 Nov 2026 09:00")
            view.facts(Task).count()  # -> 5
            ```
        """
        return replace(self, _cache={}, known_time=end_of(time))

    def at(self, date: Moment) -> World:
        """Give the world as you saw it on a day. It has the facts true on that day and
        known by the end of it.

        Args:
            date: The day.

        Returns:
            A new view of the same log.

        Raises:
            ValueError: A date or time in the text form that `when` refuses. An example
                is "8/10/2026".

        Example:
            ```python
            todo.at("4 Nov 2026").known_time
            # -> datetime.datetime(2026, 11, 4, 23, 59, 59, 999999)
            ```
        """
        view = self.on(date)
        return view.known(view.on_date)

    def during(self, start: Moment, until: Moment) -> World:
        """Give a window of days. A fact is in the view if it was true on any day of the
        window.

        The window starts on `start` and ends before `until`. A fact with 2 versions in
        the window is seen once. It shows its latest
        version. `history` gives every version.

        Args:
            start: The first day of the window.
            until: The day after the last day of the window. This day is not in the
                window.

        Returns:
            A new view of the same log.

        Raises:
            ValueError: A date or time in the text form that `when` refuses. An example
                is "8/10/2026".

        Example:
            ```python
            listed = World.new(Task)
            listed.add(
                Task(id="t9", list="home", title="Buy tea"),
                source="me",
                true_from="2 Nov 2026",
            )
            listed.end(Task, id="t9", on="4 Nov 2026", source="me: not needed")
            listed.add(
                Task(id="t9", list="home", title="Buy more tea"),
                source="me: again",
                true_from="10 Nov 2026",
            )
            listed.during("3 Nov 2026", "11 Nov 2026").get(Task, id="t9").title
            # -> 'Buy more tea'
            ```
        """
        return replace(self, _cache={}, on_date=day(start), until_date=day(until))

    def steps(self, by: Step, count: int, *, known_too: bool = False) -> Facts[World]:
        """Give a series of views from this view's day. There is one view for each step.

        Args:
            by: The distance between the views.
            count: The number of views. The first view is on this view's day.
            known_too: Whether each view knows only what you knew by the end of its day.
                The default `False` means each view
                keeps the `known_time` of this view.

        Returns:
            A collection of `count` views.

        Raises:
            ValueError: A date or time in the text form that `when` refuses. An example
                is "8/10/2026".

        Example:
            ```python
            from scriptt.world import Step

            views = todo.on("2 Nov 2026").steps(Step.DAY, 3)
            [view.facts(Task).count() for view in views]  # -> [5, 6, 6]
            ```
        """
        views = [
            replace(self, _cache={}, on_date=step(self.on_date, by, n), until_date=None)
            for n in range(count)
        ]
        return Facts(v.known(v.on_date) if known_too else v for v in views)

    # O11
    # ----------------------------------------------------------------------------------
    def suppose(
        self,
        *,
        add: Iterable[Fact] = (),
        true_from: Moment | None = None,
        end: Iterable[Fact] = (),
        retract: Iterable[Fact] = (),
    ) -> World:
        """Give a view with changes that the log does not keep.

        A supposed fact wins over every logged fact. A supposed end uses the day of this
        view. Ask what would differ with
        `supposed - today`.

        Args:
            add: Facts to add. The default is none.
            true_from: The first day on which the added facts are true. The default
                `None` means always.
            end: Facts to end on this view's day. The default is none.
            retract: Facts that were never true. The default is none.

        Returns:
            A new view. The log does not change.

        Example:
            ```python
            report = today.one(Task, id="t2")
            done = today.suppose(add=[report.but(status=Status.DONE)])
            done.one(Task, id="t2").status.value  # -> 'done'
            today.one(Task, id="t2").status.value  # -> 'open'
            ```
        """
        add, end, retract = (
            list(add),
            list(end),
            list(retract),
        )  # each is read twice below
        seq = _WHAT_IF_SEQ + len(self._supposed)
        rows = [
            Entry(
                seq + n,
                Op.ADD,
                type(f).type_name(),
                _identity(type(f), f.identity),
                f.model_dump(mode="json"),
                day(true_from),
                None,
                dt.datetime.max,
                dt.datetime.max,
                "supposed",
            )
            for n, f in enumerate(add)
        ]
        for f in add:
            self._types.setdefault(type(f).type_name(), type(f))
        rows += [
            Entry(
                seq + len(rows) + n,
                Op.END,
                type(f).type_name(),
                _identity(type(f), f.identity),
                {},
                None,
                self.on_date,
                dt.datetime.max,
                dt.datetime.max,
                "supposed",
            )
            for n, f in enumerate(end)
        ]
        rows += [
            Entry(
                seq + len(rows) + n,
                Op.RETRACT,
                type(f).type_name(),
                _identity(type(f), f.identity),
                {},
                None,
                None,
                dt.datetime.max,
                dt.datetime.max,
                "supposed",
            )
            for n, f in enumerate(retract)
        ]
        return replace(self, _cache={}, _supposed=self._supposed + tuple(rows))

    # reads
    # ----------------------------------------------------------------------------------
    def _limit(self) -> dt.datetime:
        return self.known_time or _FAR

    def _root(self, kind: str) -> Callable[[str], str]:
        """`same` entries of 1 type in the order made. Each group answers under its
        oldest identity."""
        parent: dict[str, str] = {}

        def root(ident: str) -> str:
            while ident in parent:
                ident = parent[ident]
            return ident

        for e in self._store.entries(kind=kind, ops=("same",), known=self._limit()):
            a, b = root(e.body["same_as"]), root(e.identity)
            if a != b:
                parent[b] = a
        return root

    def _versions(self, of: type[Fact]) -> dict[str, tuple[Entry, dict]]:
        """The version true in this view for each identity (cached for each view until
        the log grows)."""
        token = ("versions", of, self._store.count())
        if token not in self._cache:
            self._cache[token] = self._read_versions(of)
        return self._cache[token]

    def _read_versions(self, of: type[Fact]) -> dict[str, tuple[Entry, dict]]:
        """The version true in this view for each identity before `same` merges (1 SQL
        query from _store.VERSIONS)."""
        renames = [
            e.body
            for e in self._store.entries(
                kind=of.type_name(), ops=("rename",), known=self._limit()
            )
        ]
        rows = self._store.versions(
            kind=of.type_name(),
            lo=self.on_date,
            hi=self.until_date or self.on_date + dt.timedelta(days=1),
            known=self._limit(),
            supposed=tuple(
                _row(e) for e in self._supposed if e.type_name == of.type_name()
            ),
        )
        out: dict[str, tuple[Entry, dict]] = {}
        for row in rows:
            body = dict(row.body)
            for change in renames:
                if change["old"] in body:
                    body[change["new"]] = body.pop(change["old"])
            out[row.identity] = (_entry(row), body)
        return out

    def _current[T: Fact](self, of: type[T]) -> dict[str, tuple[Entry, T]]:
        """1 fact for each thing. `same` merges fields with the newest first. A None
        never hides a value. Cached for each
        view until the log grows."""
        token = (
            of,
            self._store.count(),
        )  # the class (2 classes may read 1 type name) and the log as the file has it
        if token not in self._cache:
            self._cache[token] = self._merge(of)
        return self._cache[token]

    def _merge[T: Fact](self, of: type[T]) -> dict[str, tuple[Entry, T]]:
        versions, root = self._versions(of), self._root(of.type_name())
        grouped: dict[str, list[tuple[Entry, dict]]] = {}
        for ident, item in versions.items():
            grouped.setdefault(root(ident), []).append(item)
        out = {}
        for group, items in grouped.items():
            items.sort(key=lambda it: (it[0].known, it[0].seq), reverse=True)
            merged: dict[str, Any] = {}
            for _, body in items:
                for name, value in body.items():
                    if merged.get(name) is None and value is not None:
                        merged[name] = value
            own = next((body for e, body in items if e.identity == group), None)
            if own is not None:
                merged |= {name: own[name] for name in of.key_fields()}
            out[group] = (items[0][0], of.model_validate(merged))
        return out

    def facts[T: Fact](self, of: type[T]) -> Facts[T]:
        """Give every fact of 1 type that is true in this view.

        Args:
            of: The type of fact.

        Returns:
            A collection of facts with 1 fact for each thing. Versions merge as `same`
            says. A type that other types subclass
            (`class Chore(Task)`) also gives the facts of those types.

        Example:
            ```python
            today.facts(Task).count()  # -> 6
            today.facts(Note).count()  # -> 2
            ```
        """
        kinds = list(
            dict.fromkeys([of, *(t for t in self._types.values() if issubclass(t, of))])
        )  # the type, then its subtypes
        return Facts(f for kind in kinds for _, f in self._current(kind).values())  # pyright: ignore[reportArgumentType]

    def one[T: Fact](self, of: type[T], **key: Any) -> T:
        """Give 1 fact by its key fields. The fact must exist in this view.

        Args:
            of: The type of fact.
            **key: A value for every key field of the type.

        Returns:
            The fact.

        Raises:
            LookupError: No fact of this type with this key is true in this view. Use
                `get` to get `None` instead.
            KeyError: You did not give all the key fields.

        Example:
            ```python
            today.one(Task, id="t2").title  # -> 'Send the report'
            ```
        """
        if (found := self.get(of, **key)) is None:
            raise LookupError(
                say(
                    t"no {of.__name__} with "
                    t"{', '.join(f'{k} {v!r}' for k, v in key.items())} on "
                    t"{self.on_date}"
                )
            )
        return found

    def get[T: Fact](self, of: type[T], **key: Any) -> T | None:
        """Give 1 fact by its key fields. It is `None` if the fact is not true in this
        view.

        Args:
            of: The type of fact.
            **key: A value for every key field of the type.

        Returns:
            The fact or `None`.

        Raises:
            KeyError: You did not give all the key fields.

        Example:
            ```python
            today.get(Task, id="t99")  # -> None
            ```
        """
        missing, unknown = (
            set(of.key_fields()) - set(key),
            set(key) - set(of.key_fields()),
        )
        if missing or unknown:
            wrong = (
                f"give the key fields {', '.join(sorted(missing))}"
                if missing
                else f"{', '.join(sorted(unknown))} is not a key field"
            )
            raise KeyError(
                f"{of.__name__}: {wrong}; the key fields are "
                f"{', '.join(of.key_fields())}"
            )
        ident = _identity(of, (key[n] for n in of.key_fields()))
        for kind in [of] + [
            t
            for t in dict.fromkeys(self._types.values())
            if issubclass(t, of) and t is not of
        ]:  # subtypes too, as `facts` does
            if (
                found := self._current(kind).get(self._root(kind.type_name())(ident))
            ) is not None:
                # a subtype of T is a T
                return found[1]  # pyright: ignore[reportReturnType]
        return None

    def history(self, fact: Fact) -> Facts[Entry]:
        """Give every entry of the log for 1 fact with all 3 times. The oldest entry
        comes first.

        The entries are those that the view knows. Supposed changes are at the end.

        Args:
            fact: A fact. Its type and key choose the entries.

        Returns:
            A collection of `Entry` objects.

        Example:
            ```python
            listed = World.new(Task)
            listed.add(Task(id="t9", list="home", title="Buy tea"), source="me")
            listed.add(Task(id="t9", list="home", title="Buy tea x2"), source="me: x2")
            probe = Task(id="t9", list="", title="")
            [entry.source for entry in listed.history(probe)]
            # -> ['me', 'me: x2']
            ```
        """
        of = type(fact)
        ident = _identity(of, fact.identity)
        logged = [
            _entry(r)
            for r in self._store.entries(
                kind=of.type_name(), identity=ident, known=self._limit()
            )
        ]
        return Facts(
            logged
            + [
                e
                for e in self._supposed
                if e.type_name == of.type_name() and e.identity == ident
            ]
        )

    def origin[T: Fact, V](self, fact: T, field: Callable[[T], V]) -> Origin[T, V]:
        """Say where 1 value of a fact came from. Give the value and the entry of the
        log that wrote it.

        For a fact of this view, the entry is the one that wrote the version that this
        view shows. After `same` it is
        the entry of the member that gave the value. Give a changed copy to find when
        another value was written. An example is
        `view.origin(fact.but(p=0.5), lambda f: f.p)`. Then the entry is the first of
        the last run of entries that give it.

        Args:
            fact: The fact.
            field: A function that reads exactly 1 field of the fact. An example is
                `lambda p: p.amount`.

        Returns:
            An `Origin`.

        Raises:
            ValueError: The function does not read exactly 1 field of the fact.
            LookupError: No entry of the log gives the fact this value.

        Example:
            ```python
            report = today.one(Task, id="t2")
            today.origin(report, lambda t: t.title).entry.known
            # -> datetime.datetime(2026, 11, 2, 9, 0)
            ```
        """
        probe = _Probe()
        try:
            # the probe stands in for the fact, to learn the field name
            field(probe)  # pyright: ignore[reportArgumentType]
        except TypeError:
            probe.names = []
        if len(probe.names) != 1 or probe.names[0] not in type(fact).model_fields:
            raise ValueError(
                "give a function that reads 1 field of the fact: lambda f: f.p"
            )
        of, name, value = type(fact), probe.names[0], field(fact)
        written = fact.model_dump(mode="json")[name]
        root = self._root(of.type_name())
        group = root(_identity(of, fact.identity))
        members = sorted(
            (
                (e, body)
                for i, (e, body) in self._versions(of).items()
                if root(i) == group
            ),
            key=lambda m: (m[0].known, m[0].seq),
            reverse=True,
        )
        for (
            entry,
            body,
            # the version this view shows: after `same`, the newest member with a value
        ) in members:
            if body.get(name) is not None:
                if body[name] == written:
                    return Origin(fact, name, value, entry)
                break
        if (
            written is None
            and members
            and all(body.get(name) is None for _, body in members)
        ):  # the shown version has no value
            return Origin(fact, name, value, members[0][0])
        found, run = (
            None,
            None,
            # another value (a changed copy): the first entry of its last run
        )
        idents = {i for i in self._versions(of) if root(i) == group} | {
            _identity(of, fact.identity)
        }
        entries = sorted(
            (
                _entry(r)
                for i in idents
                for r in self._store.entries(
                    kind=of.type_name(), identity=i, ops=("add",), known=self._limit()
                )
            ),
            key=lambda e: (e.known, e.seq),
        )
        for entry in entries:
            run = (run or entry) if entry.body.get(name) == written else None
            found = run or found
        if found is None:
            raise LookupError(
                say(t"no entry of the log gives {fact} the {of.label(name)} {value}")
            )
        return Origin(fact, name, value, found)

    def conflicts(self, of: type[Fact]) -> Facts[Conflict]:
        """Give the fields on which the members of 1 thing disagree after `same`.

        Args:
            of: The type of fact.

        Returns:
            A collection of `Conflict` objects, 1 for each field that has 2 values or
            more.

        Example:
            ```python
            lists = World.new(Task)
            a = Task(id="t9", list="home", title="Buy tea")
            b = Task(id="t10", list="home", title="Get tea")
            lists.add(a, source="me").add(b, source="me").same(
                a, b, source="me: one task"
            )
            lists.conflicts(Task)[0].values  # -> ('Buy tea', 'Get tea')
            ```
        """
        versions, root = self._versions(of), self._root(of.type_name())
        groups: dict[str, list[dict]] = {}
        for ident, (_, body) in versions.items():
            groups.setdefault(root(ident), []).append(body)
        out = []
        for group, bodies in groups.items():
            for name in (n for n in of.model_fields if n not in of.key_fields()):
                values = tuple(
                    dict.fromkeys(
                        json.dumps(b.get(name))
                        for b in bodies
                        if b.get(name) is not None
                    )
                )
                if len(values) > 1:
                    out.append(
                        Conflict(
                            tuple(json.loads(group)),
                            name,
                            tuple(json.loads(v) for v in values),
                        )
                    )
        return Facts(out)

    def mapped(self, term: Any, match: Match | None = None) -> Facts[Mapping]:
        """Give the mappings from a term in either direction.

        Args:
            term: The term. An enum member uses its value.
            match: The kind of mapping to keep. The default `None` means every kind.

        Returns:
            A collection of `Mapping` facts.

        Example:
            ```python
            from scriptt.world import Match, World

            terms = World.new()
            terms.map("shopping", "errands", Match.NARROWER, source="me")
            terms.mapped("errands", Match.NARROWER)[0].a  # -> 'shopping'
            ```
        """
        t = _term(term)
        return self.facts(Mapping).where(
            lambda m: (m.a == t or m.b == t) and (match is None or m.match == match)
        )

    def parents(self, thing: Any, rel: Rel = Rel.PART_OF) -> Facts[str]:
        """Give the direct parent of a thing.

        Args:
            thing: The thing. An enum member uses its value.
            rel: The kind of link to follow. The default is `Rel.PART_OF`.

        Returns:
            A collection of 0 or 1 text value.

        Example:
            ```python
            tree = World.new()
            tree.place("Buy milk", under="Groceries", source="me")
            list(tree.parents("Buy milk"))  # -> ['Groceries']
            ```
        """
        t = _term(thing)
        return self.facts(Under).where(child=t, rel=rel).map(lambda p: p.parent)

    def children(self, thing: Any, rel: Rel = Rel.PART_OF) -> Facts[str]:
        """Give the things that are directly under a thing.

        Args:
            thing: The parent. An enum member uses its value.
            rel: The kind of link to follow. The default is `Rel.PART_OF`.

        Returns:
            A collection of text values.

        Example:
            ```python
            tree = World.new()
            tree.place("Buy milk", under="Groceries", source="me")
            list(tree.children("Groceries"))  # -> ['Buy milk']
            ```
        """
        t = _term(thing)
        return self.facts(Under).where(parent=t, rel=rel).map(lambda p: p.child)

    def ancestors(self, thing: Any, rel: Rel = Rel.PART_OF) -> Facts[str]:
        """Give the parent of a thing and the parent of that parent and so on. The
        nearest comes first.

        Args:
            thing: The thing. An enum member uses its value.
            rel: The kind of link to follow. The default is `Rel.PART_OF`.

        Returns:
            A collection of text values. It stops if the tree has a loop.

        Example:
            ```python
            tree = World.new()
            tree.place("Buy milk", under="Groceries", source="me")
            tree.place("Groceries", under="Shopping", source="me")
            list(tree.ancestors("Buy milk"))
            # -> ['Groceries', 'Shopping']
            ```
        """
        up, seen, current = (
            {p.child: p.parent for p in self.facts(Under).where(rel=rel)},
            [],
            _term(thing),
        )
        while current in up and up[current] not in seen:
            current = up[current]
            seen.append(current)
        return Facts(seen)

    def descendants(self, thing: Any, rel: Rel = Rel.PART_OF) -> Facts[str]:
        """Give every thing under a thing at any depth. The nearest come first.

        Args:
            thing: The parent. An enum member uses its value.
            rel: The kind of link to follow. The default is `Rel.PART_OF`.

        Returns:
            A collection of text values.

        Example:
            ```python
            tree = World.new()
            tree.place("Buy milk", under="Groceries", source="me")
            tree.place("Groceries", under="Shopping", source="me")
            list(tree.descendants("Shopping"))
            # -> ['Groceries', 'Buy milk']
            ```
        """
        down: dict[str, list[str]] = {}
        for p in self.facts(Under).where(rel=rel):
            down.setdefault(p.parent, []).append(p.child)
        out, queue = [], [_term(thing)]
        while queue:
            for c in down.get(queue.pop(0), []):
                if c not in out:
                    out.append(c)
                    queue.append(c)
        return Facts(out)

    def problems(self, *goals: Goal) -> Facts[Problem]:
        """Give every problem in this view. A problem is one of these.

        - A `Ref` field that points to no fact.
        - A thing that `place` puts under itself.
        - A fact that a goal fails.

        A `Ref` problem is found for every type in the world with no setup. A goal adds
        its own rule. A goal with
        `every=True` gives 1 problem for each fact that fails it. A count or sum goal
        that is not met gives 1 problem.

        Args:
            *goals: Rules to check as well. A rule such as "at most 1 employer at a
                time" is a goal with `every=True`.

        Returns:
            A collection of problems. The `Ref` problems come first. An empty collection
            means no problem.

        Example:
            ```python
            from scriptt.world import Fact, Key, Ref, World


            class TodoList(Fact):
                name: Key[str]


            class Task(Fact):
                id: Key[str]
                list: Ref[TodoList]
                title: str


            lists = World.new(TodoList, Task)
            lists.add(TodoList(name="home"), source="me")
            lists.add(Task(id="t1", list="home", title="Buy milk"), source="me").add(
                Task(id="t2", list="work", title="Send the report"), source="me"
            )
            [p.message for p in lists.problems()]
            # -> ["task t2: list 'work' is not the key of any TodoList."]
            ```
        """
        out: list[Problem] = []
        for of in dict.fromkeys(self._types.values()):
            try:
                pointers = of.refs()
            except (
                TypeError,
                NameError,
            ) as error:  # a Ref to a type that is not defined, or that has 2 key fields
                out.append(
                    Problem(
                        f"{of.__name__} has a Ref that cannot be read",
                        None,
                        None,
                        None,
                        say(t"{of.__name__}: {error}"),
                    )
                )
                continue
            for name, target in pointers.items():
                keys = self._keys(target)
                for fact in self.facts(of).where(
                    lambda f: type(f) is of
                ):  # a subtype's facts are checked once, as their own type
                    for value in _each(getattr(fact, name)):
                        if str(value) not in keys:
                            rule = f"{of.__name__}.{name} points to a {target.__name__}"
                            out.append(
                                Problem(
                                    rule,
                                    fact,
                                    name,
                                    value,
                                    say(
                                        t"{fact}: {name} {value!r} is not the key of "
                                        t"any {target.__name__}."
                                    ),
                                )
                            )
        # a thing that is, through its parents, under itself: 1 problem for each loop
        for rel in Rel:
            up, reported = (
                {u.child: u.parent for u in self.facts(Under).where(rel=rel)},
                set(),
            )
            for start in up:
                seen, node = [start], up[start]
                while node in up and node not in seen:
                    seen.append(node)
                    node = up[node]
                if node == start and not reported & set(seen):
                    reported |= set(seen)
                    way = (
                        "directly"
                        if len(seen) == 1
                        else say(t"through {' → '.join(seen[1:])}")
                    )
                    out.append(
                        Problem(
                            f"no thing is {rel.value} itself",
                            None,
                            "parent",
                            start,
                            say(t"{start} is {rel.value} itself, {way}."),
                        )
                    )
        for goal in goals:
            result = self.check(goal)
            if goal.every:
                out += [
                    Problem(
                        goal.name,
                        f,
                        None,
                        None,
                        say(t"{f} fails the rule '{goal.name}'."),
                    )
                    for f in result.failing
                ]
            elif not result.met:
                out.append(
                    Problem(
                        goal.name,
                        None,
                        None,
                        result.found,
                        say(
                            t"'{goal.name}' is not met: {result.found} of "
                            t"{result.needed}."
                        ),
                    )
                )
        return Facts(out)

    def _key_of(self, of: type[Fact]) -> dict[str, str]:
        """The value of the first key field for each identity of a type in this view
        (this includes those merged by `same`)."""
        return {i: str(json.loads(i)[0]) for i in self._versions(of)}

    def _keys(self, of: type[Fact]) -> set[str]:
        """The key values that a `Ref` to this type may contain. They are every identity
        of the type and of its subtypes in this view,
        whether `same` merged them or not."""
        return {
            k
            for kind in dict.fromkeys(self._types.values())
            if issubclass(kind, of)
            for k in self._key_of(kind).values()
        } | set(self._key_of(of).values())

    def about(self, fact: Fact, hops: int = 1) -> Facts[Fact]:
        """Give the fact and every fact that points to it with a `Ref` field. This gives
        "everything about this thing".

        Args:
            fact: The fact. An example is a list.
            hops: How many references to follow back. 2 also gives the facts that point
                to those facts (the notes
                of the tasks of a list). The default is 1.

        Returns:
            A collection with the fact first. Then come the facts that point to it. They
            come type by type. A `Ref` to a type
            it subclasses counts too.

        Example:
            ```python
            from scriptt.world import Fact, Key, Ref, World


            class TodoList(Fact):
                name: Key[str]


            class Task(Fact):
                id: Key[str]
                list: Ref[TodoList]
                title: str


            lists = World.new(TodoList, Task)
            lists.add(TodoList(name="home"), source="me")
            lists.add(Task(id="t1", list="home", title="Buy milk"), source="me").add(
                Task(id="t2", list="work", title="Send the report"), source="me"
            )
            lists.about(lists.one(TodoList, name="home")).count()
            # -> 2: the list and its task
            ```
        """
        found: list[Fact] = [fact]
        seen = {
            (type(fact), fact.identity)
        }  # a fact is the same fact in any view, so it is seen by type and key
        pointers = [
            (of, name, target)
            for of in dict.fromkeys(self._types.values())
            for name, target in _refs_or_none(of).items()
        ]
        index: dict[
            tuple[type, str], dict[str, list[Fact]]
        ] = {}  # (type, field) -> key -> facts that have it: built once
        for of, name, _ in pointers:
            table: dict[str, list[Fact]] = {}
            for f in self.facts(of):
                if type(f) is of:
                    for key in _each(getattr(f, name)):
                        table.setdefault(str(key), []).append(f)
            index[(of, name)] = table
        groups: dict[
            type, dict[str, set[str]]
        ] = {}  # type -> group -> the keys of its members (after `same`)

        def keys_of(near: Fact) -> set[str]:
            kind = type(near)
            if kind not in groups:
                root, table = self._root(kind.type_name()), {}
                for ident, key in self._key_of(kind).items():
                    table.setdefault(root(ident), set()).add(key)
                groups[kind] = table
            group = self._root(kind.type_name())(_identity(kind, near.identity))
            return groups[kind].get(group, {str(getattr(near, kind.key_fields()[0]))})

        edge = [fact]
        for _ in range(hops):
            reached: list[Fact] = []
            for near in edge:
                names = keys_of(near)
                for of, name, target in pointers:
                    if isinstance(near, target):
                        for key in names:
                            for f in index[(of, name)].get(key, []):
                                if (type(f), f.identity) not in seen:
                                    seen.add((type(f), f.identity))
                                    reached.append(f)
            found += reached
            edge = reached
        return Facts(found)

    # O10
    # ----------------------------------------------------------------------------------
    def check[T: Fact](self, goal: Goal[T]) -> GoalResult[T]:
        """Test a goal in this view.

        Args:
            goal: The goal. The second parameter of a rule with 2 parameters is this
                view.

        Returns:
            A `GoalResult`. It says whether the goal is met. It also lists the facts
            that fail the rule.

        Example:
            ```python
            has_note = Goal(
                "every task has a note",
                Task,
                lambda t, view: view.get(Note, task=t.id) is not None,
                every=True,
            )
            result = today.check(has_note)
            result.met, sorted(t.id for t in result.failing)
            # -> (False, ['t3', 't4', 't5', 't6'])
            ```
        """
        two = len(inspect.signature(goal.rule).parameters) == 2
        facts = self.facts(goal.of)
        agree = facts.where(lambda f: goal.rule(f, self) if two else goal.rule(f))
        failing = facts.where(lambda f: f not in agree)
        if goal.every:
            found, needed, met = len(agree), len(facts), not len(failing)
        else:
            found = agree.sum(goal.total) if goal.total else len(agree)
            needed, met = goal.at_least, found >= goal.at_least
        return GoalResult(
            goal.name,
            self.on_date,
            met,
            found,
            needed,
            bool(goal.by and self.on_date > goal.by),
            failing,
        )

    # O13
    # ----------------------------------------------------------------------------------
    def __sub__(self, earlier: World) -> Changes[Fact]:
        """Compare 2 views as `later - earlier`. Give the facts that the later view adds
        or removes or changes.

        Args:
            earlier: The view to compare with. It must share the log or at least use the
                same types.

        Returns:
            A `Changes` object.

        Example:
            ```python
            earlier = todo.on("4 Nov 2026").known("2 Nov 2026 09:00")
            changes = today - earlier
            changes.added.count(), changes.removed.count()  # -> (1, 0)
            ```
        """
        added, removed, changed = [], [], []
        for of in self._types.values():
            new, old = self._current(of), earlier._current(of)
            added += [f for k, (_, f) in sorted(new.items()) if k not in old]
            removed += [f for k, (_, f) in sorted(old.items()) if k not in new]
            changed += [
                Change(old[k][1], f)
                for k, (_, f) in sorted(new.items())
                if k in old and old[k][1] != f
            ]
        return Changes(
            Facts(added),
            Facts(removed),
            Facts(changed),
            tuple(dict.fromkeys(self._types.values())),
        )

    # O14 and the escape hatch
    # ----------------------------------------------------------------------------------
    def frame(self, of: type[Fact]) -> pl.DataFrame:
        """Give the facts of 1 type as a Polars DataFrame. It has 1 row for each fact.
        This needs the extra `scriptt[frames]`.

        Args:
            of: The type of fact.

        Raises:
            ModuleNotFoundError: Polars is not installed.

        Example:
            ```python
            today.frame(Note).shape  # -> (2, 2)
            ```
        """
        import polars as pl

        return pl.DataFrame(
            [f.model_dump(mode="json") for f in self.facts(of)],
            infer_schema_length=None,
        )

    def export(self, folder: str | Path) -> Facts[Path]:
        """Write 1 Parquet file for each type that has facts in this view.

        Each file is named after the type. An example is `task.parquet`.

        Args:
            folder: The folder for the files. It is made if it does not exist.

        Returns:
            A collection of the paths of the files.

        Example:
            ```python
            import pathlib
            import tempfile

            files = today.export(pathlib.Path(tempfile.mkdtemp()))
            sorted(path.name for path in files)
            # -> ['note.parquet', 'task.parquet', 'todolist.parquet']
            ```
        """
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        out = []
        for of in self._types.values():
            if not len(self.facts(of)):
                continue
            path = folder / f"{of.type_name()}.parquet"
            self.relation(of).write_parquet(str(path))
            out.append(path)
        return Facts(out)

    def relation(self, of: type[Fact]) -> duckdb.DuckDBPyRelation:
        """Give the facts of 1 type in this view as a DuckDB relation with typed
        columns. An enum field is a DuckDB ENUM.

        Each call makes its own table. So a relation keeps its rows when you make
        another view.

        Args:
            of: The type of fact.

        Returns:
            A `duckdb.DuckDBPyRelation`.

        Example:
            ```python
            len(today.relation(Task))  # -> 6
            ```
        """
        return self._store.con.table(self._table(of))

    def sql(self, query: Template) -> Facts[Row]:
        """Run SQL for a question that the verbs do not cover. Give the query as a
        t-string.

        `{Task}` names the typed table of a fact type in this view. `{Log}` names the
        log. Every other `{value}` is sent as a
        parameter and is never pasted into the query. Only 1 SELECT or PIVOT or UNPIVOT
        or EXPLAIN runs. So the log cannot change.
        DuckDB can still read local files (`read_csv` and `read_text`). Write `{Log}`
        and do not write `log`. The plain table contains
        every entry. This includes entries that the view does not know yet.

        Args:
            query: A t-string. A value in it takes no format and no conversion.

        Returns:
            A collection of rows with 1 for each row of the result. The column names are
            the field names.

        Raises:
            TypeError: `query` is not a t-string.
            ValueError: A value has a format or a conversion or the text is not 1 SELECT
                or PIVOT or UNPIVOT or EXPLAIN.

        Example:
            ```python
            limit = dt.date(2026, 11, 4)
            rows = today.sql(
                t"FROM {Task} SELECT title, due WHERE due > {limit} ORDER BY due DESC"
            )
            rows[0].title  # -> 'Book the room'
            ```
        """
        if not isinstance(query, Template):
            raise TypeError(
                'give the query as a t-string: view.sql(t"FROM {Task} SELECT ... '
                'WHERE due > {limit}")'
            )
        text, params, made, con = "", [], [], self._store.con
        try:
            return self._run(query, text, params, made)
        except duckdb.Error as error:
            raise self._explained(error, made) from None
        finally:
            for name in made:
                con.execute(f"DROP TABLE IF EXISTS {name}")

    def _run(
        self, query: Template, text: str, params: list, made: list[str]
    ) -> Facts[Row]:
        for part in query:
            if not isinstance(part, Interpolation):
                text += part
                continue
            if part.format_spec or part.conversion:
                raise ValueError(
                    f"{{{part.expression}}}: a value in sql() is a bound parameter; it "
                    f"takes no format"
                )
            value = part.value
            if isinstance(value, type) and issubclass(value, Fact):
                made.append(self._table(value))
                text += made[-1]
            elif value is Log:
                text, params = (
                    text + "(FROM log WHERE known <= ?)",
                    params + [self._limit()],
                )  # the log as this view knows it
            else:
                text, params = (
                    text + "?",
                    params + [value.value if isinstance(value, Enum) else value],
                )
        con = self._store.con
        kinds = [statement.type for statement in con.extract_statements(text)]
        pivot = kinds == [
            duckdb.StatementType.MULTI
        ] and text.lstrip().upper().startswith(("PIVOT", "UNPIVOT"))
        if not pivot and kinds not in (
            [duckdb.StatementType.SELECT],
            [duckdb.StatementType.EXPLAIN],
        ):
            raise ValueError(
                f"sql() runs 1 SELECT, PIVOT, UNPIVOT or EXPLAIN (a PIVOT must start "
                f"the text); this text has "
                f"{', '.join(k.name for k in kinds)}"
            )
        cur = con.execute(text, params)
        names = [c[0] for c in cur.description]
        return Facts(Row(**dict(zip(names, r))) for r in cur.fetchall())

    def _explained(self, error: duckdb.Error, made: list[str]) -> duckdb.Error:
        """The DuckDB error of a `sql` query, in the words of the query. Each temporary
        table shows as the `{Type}` that made it. A type of the view that the query
        names without braces gets the fix."""
        message = str(error)
        for name in made:
            plain = name.strip('"').replace('""', '"')
            kind = self._types.get(plain.rsplit("#", 1)[0])
            shown = "{" + (kind.__name__ if kind else plain) + "}"
            message = message.replace(name, shown).replace(plain, shown)
        if found := re.search(r"Table with name (\S+) does not exist", message):
            named = found.group(1).strip('"').lower()
            kind = next(
                (
                    k
                    for k in self._types.values()
                    if named in (k.__name__.lower(), k.type_name())
                ),
                None,
            )
            if kind is not None:
                message = "\n".join(
                    line for line in message.splitlines() if not line.startswith("Did")
                )
                message += (
                    f"\nWrite {{{kind.__name__}}} for the table of the type "
                    f"{kind.__name__}: sql() takes a t-string, and {{{kind.__name__}}} "
                    f"becomes the table of its facts in this view."
                )
        return type(error)(message)

    def _table(self, of: type[Fact]) -> str:
        """The quoted name of a new temporary table with the facts of 1 type in this
        view. Enum fields are ENUM columns."""
        self._types.setdefault(of.type_name(), of)
        con, World._tables_made = self._store.con, World._tables_made + 1
        name = '"' + f"{of.type_name()}#{World._tables_made}".replace('"', '""') + '"'
        columns = {n: _sql_type(f.annotation) for n, f in of.model_fields.items()}
        con.execute(
            f"CREATE TEMP TABLE {name} ("
            + ", ".join(f'"{n}" {t}' for n, t in columns.items())
            + ")"
        )
        rows = [
            [_cell(dumped[n], columns[n]) for n in columns]
            for f in self.facts(of)
            for dumped in [f.model_dump(mode="json")]
        ]  # 1 dump a fact
        if rows:
            con.executemany(
                f"INSERT INTO {name} VALUES ({', '.join('?' * len(columns))})", rows
            )
        return name


class Log:
    """The name of the table of every log entry in `World.sql`. Write `{Log}` in the
    query t-string.

    The table has these columns.

    - `seq`
    - `op`
    - `type_name`
    - `identity`
    - `body`
    - `true_from`
    - `true_until`
    - `known`
    - `written`
    - `source`

    The `body` column contains the fact. So `body.amount::DOUBLE` reads one field.

    Example:
        ```python
        kind = Task.type_name()
        rows = today.sql(t"FROM {Log} SELECT count(*) AS n WHERE type_name = {kind}")
        rows[0].n  # -> 7
        ```
    """


def _cell(value: Any, kind: str = "") -> Any:
    if kind == "JSON" or isinstance(value, dict):
        return json.dumps(value)
    return list(value) if isinstance(value, (list, tuple, set, frozenset)) else value


def _sql_type(annotation: Any) -> str:
    plain, _ = _plain(annotation)
    args = [a for a in get_args(plain) if a is not Ellipsis]
    if (
        get_origin(plain) in (tuple, list, set, frozenset) and len(set(args)) == 1
    ):  # a list of 1 type is a DuckDB list
        return _sql_type(args[0]) + "[]"
    if get_origin(plain) in (
        tuple,
        list,
        set,
        frozenset,
        Union,
        types.UnionType,
    ):  # mixed types: JSON text DuckDB can read
        return "JSON"
    if get_origin(plain) is dict or plain is dict:
        return "JSON"
    if isinstance(plain, type) and issubclass(plain, Enum):
        return (
            "ENUM("
            + ", ".join("'" + str(m.value).replace("'", "''") + "'" for m in plain)
            + ")"
        )
    return {
        int: "BIGINT",
        float: "DOUBLE",
        bool: "BOOLEAN",
        dt.date: "DATE",
        dt.datetime: "TIMESTAMP",
    }.get(plain, "VARCHAR")
