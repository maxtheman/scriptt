"""`Facts` is a collection with verbs after dplyr. It has these verbs.

- where
- mutate
- map
- arrange
- group_by and summarise
- join

Each verb gives a new collection. Nothing changes in place.
"""

import re
from collections.abc import Callable, Iterable, Iterator
from typing import Any, overload

from dataclasses import dataclass, fields as dataclass_fields, is_dataclass

from pydantic import BaseModel


_NONE_OPERAND = re.compile(
    r"(not supported between instances of|unsupported operand type\(s\) for [^:]+:) "
    r".*'NoneType'"
)


def _missing(value: Any) -> bool:
    return value is None or (isinstance(value, float) and value != value)


def _or_missing(function: Callable[[Any], Any], item: Any, missing: Any) -> Any:
    """`function(item)` when it works. It gives `missing` when it fails because it
    compared or added None (for example `None > 10`
    or `None - 2.5`). It raises any other error. Examples are `len(None)` and
    `None.lower()`."""
    try:
        return function(item)
    except TypeError as error:
        if _NONE_OPERAND.search(str(error)):
            return missing
        raise


class Row:
    """A plain set of named fields. `mutate`, `map` and `summarise` make rows. You can
    also make one.

    Read a field as an attribute such as `row.task`. A row cannot change. Two rows with
    the same fields are equal.

    Args:
        **values: The fields of the row as keyword arguments.

    Raises:
        AttributeError: You read a field that the row does not have or you try to set a
            field.

    Example:
        ```python
        from scriptt.world import Row

        row = Row(task="t1", hours=1.5)
        row.task  # -> 't1'
        row.fields()  # -> {'task': 't1', 'hours': 1.5}
        ```
    """

    __slots__ = ("_values",)

    def __init__(self, **values: Any) -> None:
        object.__setattr__(self, "_values", values)

    def __getattr__(self, name: str) -> Any:
        try:
            return self._values[name]
        except KeyError:
            raise AttributeError(
                f"this row has no field {name!r}; it has {', '.join(self._values)}"
            ) from None

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("a Row cannot change")

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Row) and self._values == other._values

    def __hash__(self) -> int:
        return hash(tuple(self._values.items()))

    def __repr__(self) -> str:
        return "Row(" + ", ".join(f"{k}={v!r}" for k, v in self._values.items()) + ")"

    def fields(self) -> dict[str, Any]:
        """Give the fields of the row as a dictionary.

        Returns:
            A new dictionary from field name to value in the order of the row.

        Example:
            ```python
            from scriptt.world import Row

            list(Row(task="t1", hours=1.5).fields())  # -> ['task', 'hours']
            ```
        """
        return dict(self._values)


def _fields(item: Any) -> dict[str, Any]:
    if hasattr(item, "__table__"):
        return item.__table__()
    if is_dataclass(item) and not isinstance(item, type):
        return {f.name: getattr(item, f.name) for f in dataclass_fields(item)}
    match item:
        case Row():
            return item.fields()
        case BaseModel():
            return {name: getattr(item, name) for name in type(item).model_fields}
        case tuple():
            return {f"{i}": v for i, v in enumerate(item)}
        case _:
            return {"value": item}


def _cell(value: Any) -> str:
    from ._say import describe

    return describe(value)


@dataclass(frozen=True, slots=True)
class Pair[L, R]:
    """Two elements that `join` or `left_join` matched.

    Attributes:
        left: The element from the collection that you called `join` on.
        right: The element from the other collection. With `left_join` it is `None` when
            no element matched.

    Example:
        ```python
        open_tasks = tasks.where(status=Status.OPEN)
        pairs = today.facts(Note).join(
            open_tasks, on=lambda note, task: note.task == task.id
        )
        sorted((pair.left.text, pair.right.title) for pair in pairs)
        # -> [('Use the new template', 'Send the report')]
        ```
    """

    left: L
    right: R


class Facts[T]:
    """An ordered collection of facts or of rows. It has dplyr-style verbs. Get one from
    `World.facts`.

    Each verb gives a new collection and leaves this one as it was. You can also do
    these things with a `Facts`.

    - Iterate it.
    - Take its `len`.
    - Index it with a number.
    - Slice it.
    - Compare two with `==`.

    Printing a `Facts` shows `table()`.

    Args:
        items: The elements in order. The default is an empty collection.

    Example:
        ```python
        from scriptt.world import Facts

        tasks.count()  # -> 6
        Facts([3, 1, 2]).arrange(lambda n: n).first()  # -> 1
        tasks[0].list in {"home", "work"}  # -> True
        ```
    """

    def __init__(self, items: Iterable[T] = ()) -> None:
        self._items: tuple[T, ...] = tuple(items)

    def __iter__(self) -> Iterator[T]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    @overload
    def __getitem__(self, index: int) -> T: ...
    @overload
    def __getitem__(self, index: slice) -> Facts[T]: ...

    def __getitem__(self, index: int | slice) -> T | Facts[T]:
        return (
            Facts(self._items[index])
            if isinstance(index, slice)
            else self._items[index]
        )

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Facts) and self._items == other._items

    def __add__(self, other: Facts[T]) -> Facts[T]:
        """Join two collections. The result has the elements of this one and then the
        elements of the other.

        Args:
            other: The collection to add after this one.

        Returns:
            A new collection. Neither input changes.

        Example:
            ```python
            both = tasks.where(list="home") + tasks.where(list="work")
            both.count()  # -> 6
            ```
        """
        return Facts(self._items + other._items)

    # filter
    # ----------------------------------------------------------------------------------
    def where(
        self, rule: Callable[[T], object] | None = None, /, **equal: Any
    ) -> Facts[T]:
        """Keep the elements for which `rule` is true and every `field=value` is true.

        An element whose rule uses a missing value (`None` in `t.due > cutoff`) is not
        kept. This is as in dplyr's `filter`.
        Any other error in the rule is raised.

        Args:
            rule: A function that takes 1 element and gives a true or false value. The
                default `None` means no rule.
            **equal: Fields that must equal a value. An example is
                `status=Status.OPEN`. The default is none.

        Returns:
            A new collection with the elements that agree. They keep their order.

        Example:
            ```python
            open_tasks = tasks.where(status=Status.OPEN)
            open_tasks.where(lambda t: t.list == "home").count()  # -> 3
            ```
        """

        def keep(item: T) -> bool:
            return (rule is None or bool(_or_missing(rule, item, False))) and all(
                getattr(item, k) == v for k, v in equal.items()
            )

        return Facts(i for i in self._items if keep(i))

    def where_known[V](
        self,
        value: Callable[[T], V | None],
        rule: Callable[[V], object] = lambda v: True,
    ) -> Facts[T]:
        """Keep the elements whose `value` is not `None` and agrees with `rule`.

        The rule gets the value with `None` taken out. So a type checker accepts it.

        Args:
            value: A function that takes 1 element and gives a value or `None`.
            rule: A function that takes that value and gives a true or false value. The
                default keeps every element that has a value.

        Returns:
            A new collection with the elements that agree. They keep their order.

        Example:
            ```python
            tasks.where_known(lambda t: t.due, lambda due: due.day > 4).count()
            # -> 2
            ```
        """
        return Facts(
            i
            for i in self._items
            if (v := value(i)) is not None and not _missing(v) and rule(v)
        )

    def arrange(self, by: Callable[[T], Any], *, descending: bool = False) -> Facts[T]:
        """Put the elements in order of a value. Elements whose value is `None` come
        last. This is as in dplyr.

        Args:
            by: A function that takes 1 element and gives the value to sort by.
            descending: Whether the largest value comes first. The default `False` means
                the smallest value comes first.

        Returns:
            A new collection in the new order.

        Example:
            ```python
            tasks.arrange(lambda t: t.id, descending=True)[0].title  # -> 'Pay the rent'
            ```
        """
        keyed = [
            (None if _missing(k := by(i)) else k, i) for i in self._items
        ]  # the key is read once; NaN counts as missing
        known = sorted(
            ((k, i) for k, i in keyed if k is not None),
            key=lambda pair: pair[0],
            reverse=descending,
        )
        return Facts([i for _, i in known] + [i for k, i in keyed if k is None])

    def first(self) -> T | None:
        """Give the first element. It is `None` if the collection is empty.

        Returns:
            The first element or `None`.

        Example:
            ```python
            tasks.arrange(lambda t: t.title).first().title  # -> 'Book the room'
            tasks.where(list="school").first()  # -> None
            ```
        """
        return self._items[0] if self._items else None

    def one(self) -> T:
        """Give the only element of the collection.

        Returns:
            The element.

        Raises:
            LookupError: The collection has no element or has 2 or more.

        Example:
            ```python
            tasks.where(title="Buy milk").one().list  # -> 'home'
            ```
        """
        if len(self._items) != 1:
            raise LookupError(f"expected 1 item, found {len(self._items)}")
        return self._items[0]

    # reshape
    # ----------------------------------------------------------------------------------

    def mutate(self, **new: Callable[[T], Any]) -> Facts[Row]:
        """Add fields that you compute from each element. Each element becomes a `Row`
        with its old fields and the new ones.

        A new field with the name of an old field replaces it. This is as in dplyr. A
        value that you compute from a missing value
        (`None`) is `None`.

        Args:
            **new: For each new field, a function that takes 1 element and gives the
                value.

        Returns:
            A new collection of rows.

        Example:
            ```python
            milk = tasks.where(title="Buy milk")
            milk.mutate(shout=lambda t: t.title.upper()).one().shout  # -> 'BUY MILK'
            ```
        """
        return Facts(
            Row(
                **(
                    _fields(i)
                    | {name: _or_missing(f, i, None) for name, f in new.items()}
                )
            )
            for i in self._items
        )

    def map[U](self, function: Callable[[T], U]) -> Facts[U]:
        """Give a new collection of the results of a function on each element.

        Args:
            function: A function that takes 1 element and gives any value.

        Returns:
            A new collection of the results, in order.

        Example:
            ```python
            tasks.where(title="Buy milk").map(lambda t: t.title.upper()).one()
            # -> 'BUY MILK'
            ```
        """
        return Facts(function(i) for i in self._items)

    # reduce
    # ----------------------------------------------------------------------------------
    def count(self) -> int:
        """Count the elements.

        Returns:
            The number of elements.

        Example:
            ```python
            tasks.count()  # -> 6
            ```
        """
        return len(self._items)

    def distinct[U](self, value: Callable[[T], U]) -> Facts[U]:
        """Give the different values of a function. They are in the order that you first
        see them.

        Args:
            value: A function that takes 1 element and gives a value that can be a
                dictionary key.

        Returns:
            A new collection of the different values.

        Example:
            ```python
            tasks.distinct(lambda t: t.list).count()  # -> 2
            ```
        """
        return Facts(dict.fromkeys(value(i) for i in self._items))

    def sum[N: (int, float)](self, value: Callable[[T], N | None]) -> N:
        """Add the values of a function over the elements. An element whose value is
        `None` adds nothing.

        Args:
            value: A function that takes 1 element and gives a number or `None`.

        Returns:
            The total. It is 0 for an empty collection.

        Example:
            ```python
            tasks.where(list="work").sum(lambda t: t.due.day)  # -> 10
            ```
        """
        total: Any = 0
        for item in self._items:
            if not _missing(v := value(item)):
                total += v
        return total

    def mean(self, value: Callable[[T], float | None]) -> float | None:
        """Give the mean of the values of a function. An element whose value is `None`
        is left out.

        Args:
            value: A function that takes 1 element and gives a number or `None`.

        Returns:
            The mean. It is `None` if no element has a value.

        Example:
            ```python
            tasks.where(list="work").mean(lambda t: t.due.day)  # -> 5.0
            tasks.where(list="school").mean(lambda t: t.due.day)  # -> None
            ```
        """
        values = [
            v for i in self._items if (v := value(i)) is not None and not _missing(v)
        ]
        return sum(values) / len(values) if values else None

    def max(self, value: Callable[[T], Any]) -> Any:
        """Give the largest value of a function. An element whose value is `None` is
        left out.

        Args:
            value: A function that takes 1 element and gives a value that can be
                compared or `None`.

        Returns:
            The largest value. It is `None` if no element has a value.

        Example:
            ```python
            tasks.max(lambda t: len(t.title))  # -> 16
            ```
        """
        values = [
            v for i in self._items if (v := value(i)) is not None and not _missing(v)
        ]
        return max(values) if values else None

    def min(self, value: Callable[[T], Any]) -> Any:
        """Give the smallest value of a function. An element whose value is `None` is
        left out.

        Args:
            value: A function that takes 1 element and gives a value that can be
                compared or `None`.

        Returns:
            The smallest value. It is `None` if no element has a value.

        Example:
            ```python
            tasks.min(lambda t: len(t.title))  # -> 8
            ```
        """
        values = [
            v for i in self._items if (v := value(i)) is not None and not _missing(v)
        ]
        return min(values) if values else None

    def top(self, n: int, by: Callable[[T], Any]) -> Facts[T]:
        """Keep the `n` elements with the largest value. Elements whose value is `None`
        come last.

        Args:
            n: How many elements to keep.
            by: A function that takes 1 element and gives the value to rank by.

        Returns:
            A new collection of at most `n` elements. The largest comes first.

        Example:
            ```python
            [t.title for t in tasks.top(2, by=lambda t: len(t.title))]
            # -> ['Call the plumber', 'Water the plants']
            ```
        """
        if n < 0:
            raise ValueError(f"top takes a count of 0 or more, not {n}")
        keyed = [(None if _missing(k := by(i)) else k, i) for i in self._items]
        return Facts(
            [
                i
                for _, i in sorted(
                    keyed,
                    key=lambda pair: (
                        pair[0] is not None,
                        pair[0] if pair[0] is not None else 0,
                    ),
                    reverse=True,
                )[:n]
            ]
        )

    def count_by(self, **by: Callable[[T], Any]) -> Facts[Row]:
        """Count the elements in each group. The largest group comes first.

        Args:
            **by: A name and a function for each grouping value. The function takes 1
                element and gives the value.

        Returns:
            A collection of rows. Each row has the grouping values and `n`. `n` is the
            count.

        Example:
            ```python
            rows = tasks.count_by(status=lambda t: t.status)
            [(row.status.value, row.n) for row in rows]
            # -> [('open', 5), ('done', 1)]
            ```
        """
        if "n" in by:
            raise ValueError("count_by names its count n; give the group another name")
        return (
            self.group_by(**by)
            .summarise(n=lambda g: g.count())
            .arrange(lambda r: r.n, descending=True)
        )

    def group_by(self, **by: Callable[[T], Any]) -> Groups[T]:
        """Put the elements in groups by one value or more. Then call `summarise` to
        make 1 row for each group.

        Args:
            **by: A name and a function for each grouping value. The function takes 1
                element and gives the value.

        Returns:
            A `Groups` object. You can iterate it or call `summarise` on it.

        Example:
            ```python
            groups = tasks.group_by(list=lambda t: t.list)
            rows = groups.summarise(
                n=lambda g: g.count(), last=lambda g: g.max(lambda t: t.id)
            )
            sorted((row.list, row.n, row.last) for row in rows)
            # -> [('home', 4, 't6'), ('work', 2, 't3')]
            ```
        """
        groups: dict[tuple, list[T]] = {}
        for item in self._items:
            groups.setdefault(tuple(f(item) for f in by.values()), []).append(item)
        return Groups(tuple(by), {k: Facts(v) for k, v in groups.items()})

    # combine
    # ----------------------------------------------------------------------------------
    def join[U](
        self, other: Iterable[U], on: Callable[[T, U], bool]
    ) -> Facts[Pair[T, U]]:
        """Match each element of this collection with each element of another collection
        when a rule is true.

        Args:
            other: The other collection. Any iterable works.
            on: A function that takes 1 element of this collection and 1 of the other.
                It gives a true or false value.

        Returns:
            A collection of `Pair` objects in the order of this collection. An element
            with no partner gives no pair.

        Example:
            ```python
            open_tasks = tasks.where(status=Status.OPEN)
            pairs = today.facts(Note).join(
                open_tasks, on=lambda note, task: note.task == task.id
            )
            pairs.count()  # -> 1
            ```
        """
        others = tuple(other)
        return Facts(Pair(a, b) for a in self._items for b in others if on(a, b))

    def left_join[U](
        self, other: Iterable[U], on: Callable[[T, U], bool]
    ) -> Facts[Pair[T, U | None]]:
        """Match elements as `join` does. Keep an element that has no partner.

        Args:
            other: The other collection. Any iterable works.
            on: A function that takes 1 element of this collection and 1 of the other.
                It gives a true or false value.

        Returns:
            A collection of `Pair` objects. An element with no partner gives
            `Pair(element, None)`.

        Example:
            ```python
            open_tasks = tasks.where(status=Status.OPEN)
            pairs = today.facts(Note).left_join(
                open_tasks, on=lambda note, task: note.task == task.id
            )
            sorted((pair.left.task, pair.right is None) for pair in pairs)
            # -> [('t1', True), ('t2', False)]
            ```
        """
        others, out = tuple(other), []
        for a in self._items:
            matched = [Pair(a, b) for b in others if on(a, b)]
            out += matched or [Pair(a, None)]
        return Facts(out)

    # show
    # ----------------------------------------------------------------------------------
    def __repr__(self) -> str:
        return self.table()

    def table(self, limit: int = 20) -> str:
        """Write the elements as an aligned text table. `repr` and `print` of a `Facts`
        call this.

        Args:
            limit: The most rows to show. The default is 20. A last line tells how many
                more rows exist.

        Returns:
            The table as text. An empty collection gives "(no items)".

        Example:
            ```python
            print(tasks.table(limit=2))
            ```
        """
        if not self._items:
            return "(no items)"
        rows = [_fields(i) for i in self._items[:limit]]
        names = list(dict.fromkeys(n for r in rows for n in r))
        cells = [[_cell(r.get(n, "")) for n in names] for r in rows]
        width = [max(len(n), *(len(c[j]) for c in cells)) for j, n in enumerate(names)]
        line = lambda values: "  ".join(
            v.ljust(w) for v, w in zip(values, width)
        ).rstrip()  # noqa: E731
        more = (
            [f"... {len(self._items) - limit} more"] if len(self._items) > limit else []
        )
        return "\n".join([line(names), *(line(c) for c in cells), *more])


class Groups[T]:
    """The groups that `Facts.group_by` makes. Do not call the constructor. Use
    `group_by`.

    Iterate it to get `(values, facts)` for each group. `values` is a tuple of the
    grouping values.
    """

    def __init__(self, names: tuple[str, ...], groups: dict[tuple, Facts[T]]) -> None:
        self._names, self._groups = names, groups

    def __iter__(self) -> Iterator[tuple[tuple, Facts[T]]]:
        return iter(self._groups.items())

    def summarise(self, **values: Callable[[Facts[T]], Any]) -> Facts[Row]:
        """Make 1 row for each group. The row has its grouping values and one or more
        summary values.

        Args:
            **values: A name and a function for each summary. The function takes the
                `Facts` of 1 group and gives a value.

        Returns:
            A collection of rows in the order that the groups first appear.

        Example:
            ```python
            by_list = tasks.group_by(list=lambda t: t.list)
            rows = by_list.summarise(titles=lambda g: g.sum(lambda t: len(t.title)))
            sorted((row.list, row.titles) for row in rows)
            # -> [('home', 52), ('work', 28)]
            ```
        """
        clash = set(values) & set(self._names)
        if clash:
            raise ValueError(
                f"{', '.join(sorted(clash))} names a group and a summary; give the "
                f"summary another name"
            )
        return Facts(
            Row(**dict(zip(self._names, key)), **{n: f(g) for n, f in values.items()})
            for key, g in self._groups.items()
        )
