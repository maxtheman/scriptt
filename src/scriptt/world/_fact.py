"""Facts: your types. A fact is a frozen Pydantic model. `Key[...]` marks the fields
that identify it.
`Forward[...]` marks an enum field whose value may only move forward in the order that
the enum declares its members.
"""

import datetime as dt
import json
import re
import types
from enum import Enum
from functools import cache
from string.templatelib import Template
from typing import (
    Annotated,
    Any,
    ClassVar,
    Literal,
    Self,
    TypeAliasType,
    Union,
    get_args,
    get_origin,
)

from lark import Lark, Token, Tree, UnexpectedInput
from pydantic import BaseModel, ConfigDict, ValidationError
from returns.result import Failure, Result, Success

from ._say import describe, significant
from ._time import when


class _Mark:
    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:
        return self.name


_KEY, _FORWARD, _REF = _Mark("Key"), _Mark("Forward"), _Mark("Ref")

type Key[T] = Annotated[T, _KEY]
"""Mark a field as part of the key of a fact: `id: Key[str]`.

The key fields identify the fact. Two facts of 1 type with the same key values are 2
versions of 1 thing. A type
with no `Key` field uses its first field as the key. `Key[T]` works with `| None` too.

Example:
    ```python
    from scriptt.world import Fact, Key

    class Reminder(Fact):
        list: Key[str]
        title: Key[str]
        minutes: int

    Reminder.key_fields()   # -> ('list', 'title')
    ```
"""

type Ref[T] = Annotated[str, _REF]
"""Mark a text field that contains the key of a fact of another type: `list:
Ref[TodoList]`.

The value is the key of the other fact (the other type has 1 key field). A list of keys
works too:
`candidates: tuple[Ref[Print], ...]`. `World.problems` reports a `Ref` that points
to no fact, `World.about` follows `Ref` fields back to a fact, and `diagram` draws them
as arrows. `Ref` works inside
`Key[...]` and with `| None`.

Example:
    ```python
    from scriptt.world import Fact, Key, Ref

    class TodoList(Fact):
        name: Key[str]

    class Task(Fact):
        id: Key[str]
        list: Ref[TodoList]

    Task.refs()   # -> {'list': <class 'TodoList'>}
    ```
"""

type Forward[T] = Annotated[T, _FORWARD]
"""Mark an enum field whose value may only move forward, in the order that the enum
declares its members:
`state: Forward[State]`.

`World.add` refuses a new version of a fact that moves the field back.

Example:
    ```python
    from enum import StrEnum
    from scriptt.world import Fact, Forward, Key

    class Stage(StrEnum):
        PLANNED = "planned"
        STARTED = "started"
        FINISHED = "finished"

    class Project(Fact):
        id: Key[str]
        stage: Forward[Stage]

    Project.forward_fields()   # -> ('stage',)
    ```
"""


def _marks(annotation: Any) -> set[_Mark]:
    """The marks on a field, such as `Key[str]` or `Forward[State]`. This includes marks
    inside `... | None`."""
    found: set[_Mark] = set()
    if get_origin(annotation) in (Union, types.UnionType):
        for arg in get_args(annotation):
            found |= _marks(arg)
    elif (origin := get_origin(annotation)) is not None and isinstance(
        origin, TypeAliasType
    ):
        found |= {
            m for m in get_args(origin.__value__)[1:] if isinstance(m, _Mark)
        } | _marks(get_args(annotation)[0])
    return found


def _plain(annotation: Any) -> tuple[Any, bool]:
    """The value type of a field without `| None` and without `Key[...]` or
    `Forward[...]`. The second value tells whether None is allowed."""
    optional = False
    if get_origin(annotation) in (Union, types.UnionType):
        args = [a for a in get_args(annotation) if a is not type(None)]
        annotation, optional = args[0], len(args) < len(get_args(annotation))
    while (origin := get_origin(annotation)) is not None and isinstance(
        origin, TypeAliasType
    ):
        annotation = (
            str if origin is Ref else get_args(annotation)[0]
        )  # a Ref stores the other fact's key, as text
    return annotation, optional


def _target(annotation: Any) -> type | None:
    """The type that a `Ref[...]` field points to. This includes a `Ref[...]` inside
    `Key[...]` and `| None`. It is None if there is no `Ref[...]`."""
    if get_origin(annotation) in (Union, types.UnionType):
        targets = {t for a in get_args(annotation) if (t := _target(a)) is not None}
        if len(targets) > 1:
            raise TypeError(
                f"a field points to 1 type; this one names "
                f"{', '.join(sorted(t.__name__ for t in targets))}"
            )
        return next(iter(targets), None)
    if get_origin(annotation) in (tuple, list) and get_args(
        annotation
    ):  # a list of references
        return _target(get_args(annotation)[0])
    if (origin := get_origin(annotation)) is not None and isinstance(
        origin, TypeAliasType
    ):
        return (
            get_args(annotation)[0]
            if origin is Ref
            else _target(get_args(annotation)[0])
        )
    return None


def _choices(annotation: Any) -> list[str] | None:
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return [str(m.value) for m in annotation]
    if get_origin(annotation) is Literal:
        return [str(v) for v in get_args(annotation)]
    return None


def _shown(value: Any) -> str:
    """1 field value in a repr. Text and enums are quoted. A float has its significant
    figures only."""
    match value:
        case Enum():
            return repr(value.value)
        case float():
            return significant(value, grouping=False)
        case _:
            return repr(value)


_WORD = re.compile(r"[A-Za-z0-9_.%+-]+")


class Fact(BaseModel):
    """The base class of a type of fact. Declare fields as on any Pydantic model.

    A fact is frozen. It cannot change after you make it. Use `but` to make a changed
    copy. Mark the fields that identify
    the fact with `Key[...]`. Mark an enum field that may only move forward with
    `Forward[...]`.

    The log names a type by `type_name()`. The default is the class name in lower case.
    Write
    `class NoteBefore(Fact, name="note")` to use another name. Then 2 classes can
    describe 1 type before and after a change.

    Example:
        ```python
        from scriptt.world import Fact, Key


        class Task(Fact):
            id: Key[str]
            title: str


        Task(id="t9", title="Buy tea")
        ```
    """

    model_config = ConfigDict(frozen=True)
    _name: ClassVar[str | None] = None

    def __init_subclass__(cls, name: str | None = None, **kwargs: Any) -> None:
        """Read the `name=` option of a subclass. An example is `class NoteBefore(Fact,
        name="note")`.

        Args:
            name: The name that the log uses for the type. The default `None` means the
                class name in lower case.
        """
        super().__init_subclass__(**kwargs)
        cls._name = name

    @classmethod
    def __pydantic_init_subclass__(cls, name: str | None = None, **kwargs: Any) -> None:
        super().__pydantic_init_subclass__(**kwargs)

    @classmethod
    def type_name(cls) -> str:
        """Give the name that the log uses for this type.

        Returns:
            The `name=` option of the class. If there is none, the class name in lower
            case.

        Example:
            ```python
            Task.type_name()  # -> 'task'
            ```
        """
        return cls._name or cls.__name__.lower()

    @classmethod
    def key_fields(cls) -> tuple[str, ...]:
        """Give the names of the key fields.

        Returns:
            The fields marked `Key[...]` in declaration order. A type with no mark gives
            its first field.

        Example:
            ```python
            Task.key_fields()  # -> ('id',)
            Note.key_fields()  # -> ('task',)
            ```
        """
        marked = tuple(
            n for n, f in cls.model_fields.items() if _KEY in _marks(f.annotation)
        )
        return marked or (next(iter(cls.model_fields)),)

    @classmethod
    def refs(cls) -> dict[str, type[Fact]]:
        """Give the fields marked `Ref[...]` and the type that each one points to.

        Returns:
            A dict from field name to type in declaration order.

        Example:
            ```python
            from scriptt.world import Fact, Key, Ref


            class TodoList(Fact):
                name: Key[str]


            class Task(Fact):
                id: Key[str]
                list: Ref[TodoList]


            Task.refs()  # -> {'list': <class 'TodoList'>}
            ```
        """
        if not cls.__pydantic_complete__:
            cls.model_rebuild(
                force=True
            )  # a Ref to a type declared later in the file is resolved now
        found = {
            n: t
            for n, f in cls.model_fields.items()
            if (t := _target(f.annotation)) is not None
        }
        for name, target in found.items():
            if len(target.key_fields()) != 1:
                raise TypeError(
                    f"{cls.__name__}.{name}: a Ref points to a type with 1 key field; "
                    f"{target.__name__} has {', '.join(target.key_fields())}"
                )
        return found

    @classmethod
    def forward_fields(cls) -> tuple[str, ...]:
        """Give the names of the fields that may only move forward.

        Returns:
            The fields marked `Forward[...]` in declaration order. It is an empty tuple
            if there is no such field.

        Example:
            ```python
            Task.forward_fields()  # -> ()
            ```
        """
        return tuple(
            n for n, f in cls.model_fields.items() if _FORWARD in _marks(f.annotation)
        )

    def but(self, **changes: Any) -> Self:
        """Make a copy of the fact with some fields changed. The type checks the copy
        again.

        Args:
            **changes: The fields to change as keyword arguments.

        Returns:
            A new fact of the same type. The first fact does not change.

        Raises:
            pydantic.ValidationError: A new value does not fit its field or a rule of
                the type fails.

        Example:
            ```python
            plants = today.one(Task, id="t5")
            plants.but(title="Water the garden").title  # -> 'Water the garden'
            plants.title  # -> 'Water the plants'
            ```
        """
        unknown = set(changes) - set(type(self).model_fields)
        if unknown:
            raise TypeError(
                f"{type(self).__name__} has no field {', '.join(sorted(unknown))}; its "
                f"fields are {', '.join(type(self).model_fields)}"
            )
        return type(self).model_validate(self.model_dump() | changes)

    def __repr__(self) -> str:
        fields = (f"{n}={_shown(getattr(self, n))}" for n in type(self).model_fields)
        return f"{type(self).__name__}({', '.join(fields)})"

    __str__ = __repr__

    def __describe__(self) -> Template:
        """Give the t-string that `say` uses to name this fact. It has the type and the
        key. An example is "note t1".

        A type can define its own `__describe__` that returns a different t-string.

        Returns:
            A t-string.

        Example:
            ```python
            from scriptt.world import say

            say(t"{today.one(Note, task='t1')}")  # -> 'note t1'
            ```
        """
        key = ", ".join(describe(v) for v in self.identity)
        return t"{self.type_name()} {key}"

    @classmethod
    def label(cls, field: str) -> str:
        """Give the words for 1 field in text.

        Args:
            field: The name of a field of the type.

        Returns:
            The `description` of the field (`p: float =
            Field(description="probability")`). If there is none, it is the name with
            each underscore as a space.

        Raises:
            KeyError: The type has no such field.

        Example:
            ```python
            Task.label("title")  # -> 'title'
            ```
        """
        return cls.model_fields[field].description or field.replace("_", " ")

    @property
    def identity(self) -> tuple:
        """The values of the key fields as a tuple.

        2 facts with the same identity are 2 versions of 1 thing.

        Example:
            ```python
            today.one(Task, id="t5").identity  # -> ('t5',)
            ```
        """
        return tuple(getattr(self, n) for n in self.key_fields())

    # O2 -------------------------------------------------------------------------------
    @classmethod
    def check(cls, data: dict[str, Any]) -> Result[Self, str]:
        """Make a fact from a dictionary or give the first reason that the data does not
        make one.

        Rules are Pydantic validators on the type. The constructor raises an error. This
        method does not.

        Args:
            data: The fields as a dictionary from field name to value.

        Returns:
            `Success(fact)` or `Failure(reason)`. The reason is the field and the first
            error as text. `Success` and
            `Failure` come from the library `returns`.

        Example:
            ```python
            data = {"id": "t9", "list": "home", "title": "Buy tea", "due": "soon"}
            Task.check(data).failure()
            # -> 'due: Input should be a valid date or datetime, input is too short'
            Task.check(data | {"due": "2026-11-05"}).unwrap().due.day  # -> 5
            ```
        """
        if not isinstance(data, dict):
            return Failure(
                f"{cls.__name__}.check takes a dict of field names and values, not "
                f"{type(data).__name__}"
            )
        unknown = set(data) - set(cls.model_fields)
        if unknown:
            return Failure(
                f"{', '.join(sorted(unknown))}: {cls.__name__} has no such field; its "
                f"fields are {', '.join(cls.model_fields)}"
            )
        try:
            return Success(cls.model_validate(data))
        except ValidationError as error:
            first = error.errors()[0]
            return Failure(
                f"{'.'.join(map(str, first['loc'])) or cls.__name__}: {first['msg']}"
            )

    # O4 -------------------------------------------------------------------------------
    @classmethod
    def grammar(cls) -> str:
        """Give a Lark grammar for 1 line of text of the form `<type> field=value ...`.
        `parse` uses it.

        The grammar comes from the fields of the type. The fields may come in any order.
        An enum or Literal field accepts
        only its values. A date may be ISO text (2026-10-08) or quoted text.

        Returns:
            The grammar as text in Lark syntax.

        Example:
            ```python
            Task.grammar().splitlines()[0]
            # -> 'start: "task" (f_id | f_list | f_title | f_status | f_due)*'
            ```
        """
        rules, terms = [], []
        for name, info in cls.model_fields.items():
            annotation, _ = _plain(info.annotation)
            if (choices := _choices(annotation)) is not None:
                term = f"V_{name.upper()}"
                terms.append(
                    f"{term}: "
                    + " | ".join(
                        json.dumps(c if _WORD.fullmatch(c) else json.dumps(c))
                        for c in choices
                    )
                )
            elif get_origin(annotation) in (tuple, list):
                term = "LIST"
            elif annotation in (dt.date, dt.datetime):
                term = "DATE | DATETIME | ESCAPED_STRING"
            elif annotation is bool:
                term = "BOOL"
            elif annotation is int:
                term = "SIGNED_INT"
            elif annotation is float:
                term = "PERCENT_OR_NUMBER"
            else:
                term = "ESCAPED_STRING"
            rules.append(f'f_{name}: "{name}=" ({term})')
        start = (
            f'start: "{cls.type_name()}" ('
            + " | ".join(f"f_{n}" for n in cls.model_fields)
            + ")*"
        )
        return "\n".join(
            [
                start,
                *rules,
                *terms,
                r"DATETIME: /\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?/",
                r"DATE: /\d{4}-\d{2}-\d{2}/",
                'BOOL: "true" | "false"',
                r"PERCENT_OR_NUMBER: /-?\d+(\.\d+)?([eE][+-]?\d+)?%?/",
                r'LIST: /\[\s*("([^"\\]|\\.)*"\s*(,\s*"([^"\\]|\\.)*"\s*)*)?\]/',
                "%import common.ESCAPED_STRING",
                "%import common.SIGNED_INT",
                "%import common.WS",
                "%ignore WS",
            ]
        )

    @classmethod
    def parse(cls, line: str) -> Result[Self, str]:
        """Read 1 line of text as a fact or give the reason that it is not one.

        The line is the type name and then `field=value` pairs. A text value is in
        double quotes. A number can be a percent.
        70% is 0.7. A wrong value gives the field and the values that it accepts.

        Args:
            line: The line of text. Spaces at the start and the end do not matter.

        Returns:
            `Success(fact)` or `Failure(reason)` from the library `returns`.

        Example:
            ```python
            Task.parse(
                'task id="t9" list="home" title="Buy tea" status=done'
            ).unwrap().status.value  # -> 'done'
            Task.parse(
                'task id="t9" list="home" title="Buy tea" status=waiting'
            ).failure()  # -> 'status must be one of: open, done'
            ```
        """
        try:
            tree = _parser(cls).parse(line.strip())
        except UnexpectedInput as error:
            return Failure(_explain(cls, line.strip(), error.column))
        data: dict[str, Any] = {}
        for child in tree.children:
            assert isinstance(child, Tree) and isinstance(child.children[0], Token)
            name, token = str(child.data).removeprefix("f_"), child.children[0]
            if name in data:
                return Failure(f"{name} is given twice")
            raw = str(token)
            match token.type:
                case "ESCAPED_STRING":
                    value = json.loads(raw)
                    annotation, _ = _plain(cls.model_fields[name].annotation)
                    data[name] = (
                        when(value).date()
                        if annotation is dt.date
                        else when(value)
                        if annotation is dt.datetime
                        else value
                    )
                case "BOOL":
                    data[name] = raw == "true"
                case "LIST":
                    data[name] = json.loads(raw)
                case "PERCENT_OR_NUMBER" if raw.endswith("%"):
                    data[name] = float(raw[:-1]) / 100
                case _ if token.type.startswith("V_") and raw.startswith('"'):
                    data[name] = json.loads(raw)
                case _:
                    data[name] = raw
        return cls.check(data)

    def to_text(self) -> str:
        """Write the fact as 1 line of text. `parse` reads the line back into this fact.

        A field that is `None` is left out.

        Returns:
            The line. An example is `task id="t5" list="home"
            title="Water the plants" status=open due=2026-11-04`.

        Example:
            ```python
            plants = today.one(Task, id="t5")
            plants.to_text()[:24]  # -> 'task id="t5" list="home"'
            Task.parse(plants.to_text()).unwrap() == plants  # -> True
            ```
        """
        out = [self.type_name()]
        for name, value in self.model_dump(mode="json").items():
            if value is None:
                continue
            annotation, _ = _plain(type(self).model_fields[name].annotation)
            if isinstance(value, bool):
                text = str(value).lower()
            elif isinstance(value, list):
                text = json.dumps(value, ensure_ascii=False)
            elif isinstance(value, int | float) or annotation in (dt.date, dt.datetime):
                text = str(value)
            elif _choices(annotation) is not None:
                text = value if _WORD.fullmatch(value) else json.dumps(value)
            else:
                text = json.dumps(value)
            out.append(f"{name}={text}")
        return " ".join(out)


def _explain(of: type[Fact], line: str, column: int) -> str:
    """Why a line is not a fact of type `of`. It names the field at the place where the
    grammar stopped and says what the field permits."""
    before = line[: max(column - 1, 0)]
    if not line.startswith(of.type_name()):
        return f"a {of.__name__} line starts with {of.type_name()!r}"
    names = re.findall(r"(\w+)=", before + line[max(column - 1, 0) :].split(" ", 1)[0])
    field = next((n for n in reversed(names) if n in of.model_fields), None)
    if field is None:
        return (
            f"write each field as name=value; the fields of {of.__name__} are "
            f"{', '.join(of.model_fields)}"
        )
    annotation, _ = _plain(of.model_fields[field].annotation)
    if (choices := _choices(annotation)) is not None:
        return f"{field} must be one of: {', '.join(choices)}"
    kind = {
        dt.date: 'a date (2026-10-08 or "8 Oct 2026")',
        dt.datetime: "a date and time",
        int: "a whole number",
        float: "a number (70% is 0.7)",
        bool: "true or false",
    }.get(annotation, "text in double quotes")
    if get_origin(annotation) in (tuple, list):
        kind = 'a list such as ["a", "b"]'
    return f"{field} must be {kind}"


@cache
def _parser(of: type[Fact]) -> Lark:
    return Lark(of.grammar(), start="start")
