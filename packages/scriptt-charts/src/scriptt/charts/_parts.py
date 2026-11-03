"""Every chart shares these parts. Each part is a frozen dataclass.

- the scope note
- the trace to a source
- a flag with its rule
- a target line
- a choice (an assumption that the reader can change)
"""

import datetime as dt
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from scriptt.world import describe


@dataclass(frozen=True, slots=True)
class Trace:
    """Where a shown value came from. It has its source and the time that the value was
    known.

    Attributes:
        source: The name of the source. For example "my to-do list".
        known: The time the value was known. None means that the value is not known.

    Example:
        ```python
        import datetime as dt
        from scriptt.charts import Trace

        Trace("my to-do list", dt.datetime(2026, 11, 2, 9, 0))
        ```
    """

    source: str
    known: dt.datetime | None = None

    @classmethod
    def of(cls, value: Any) -> Trace | None:
        """A trace from a `Trace`, a World API `Origin` (it has `.entry`), a World API
        `Entry` (it has `.source` and
        `.known`) or None. It reads these attributes. Any object that has them works.

        Args:
            value: The object to read.

        Returns:
            The trace. It is None if `value` is None.

        Raises:
            TypeError: If `value` has neither `.entry` nor `.source`.
        """
        match value:
            case None | Trace():
                return value
            case _ if hasattr(value, "entry"):
                return cls.of(value.entry)
            case _ if hasattr(value, "source"):
                return cls(str(value.source), getattr(value, "known", None))
        raise TypeError(f"cannot trace {value!r}: give a Trace, an Origin or an Entry")


@dataclass(frozen=True, slots=True)
class Scope:
    """What the chart covers and what it leaves out and why. Every chart needs one. A
    chart without its scope can
    be read as more than the data shows.

    Attributes:
        covers: The data in words. This is the date window and the sample. For example
            "the to-do list of 4 Nov 2026, 5 of the 6 tasks".
        left_out: The number of items left out for each reason. For example `{"no due
            date": 1}`.

    Example:
        ```python
        from scriptt.charts import Scope

        Scope(
            "the to-do list of 4 Nov 2026",
            left_out={"tasks with no due date": 1},
        )
        ```
    """

    covers: str
    left_out: Mapping[str, int] = field(default_factory=dict)

    def text(self) -> str:
        """The scope as 1 line. It gives what the scope covers and then each reason with
        its count."""
        if not self.left_out:
            return self.covers
        return (
            self.covers
            + ". Left out: "
            + "; ".join(f"{n} {reason}" for reason, n in self.left_out.items())
        )


@dataclass(frozen=True, slots=True)
class Flag[T]:
    """A rule that marks some items. The chart shows the rule in words and the count of
    marked items.

    Attributes:
        rule: The rule in words. For example "fewer than 5 sales".
        test: A function that is true for an item the rule marks.
        per: What the count counts when several items show 1 thing. For example
            `per=lambda v: v.task` counts tasks and not
            versions. None counts items.

    Example:
        ```python
        from types import SimpleNamespace as Task
        from scriptt.charts import Flag

        Flag[Task]("under 30 minutes", lambda t: t.minutes < 30)
        ```
    """

    rule: str
    test: Callable[[T], bool]
    per: Callable[[T], object] | None = None


@dataclass(frozen=True, slots=True)
class Target:
    """A target value drawn as a line. It has a label and a status.

    Attributes:
        value: The target on the value axis (a number or a date).
        label: The target in words. For example "10 tasks done".
        met: True if met. False if not met. None if the status depends on a choice.

    Example:
        ```python
        from scriptt.charts import Target

        Target(10, "10 tasks done", met=False)
        ```
    """

    value: float | dt.date
    label: str
    met: bool | None = None

    def text(self) -> str:
        """The label with its status. For example "10 tasks done: not met"."""
        return (
            self.label
            if self.met is None
            else f"{self.label}: {'met' if self.met else 'not met'}"
        )


@dataclass(frozen=True, slots=True)
class Choice[V]:
    """An assumption that the reader can change on the chart, such as a fee or a pace.
    The chart is made for each
    value. A control picks the value to show. The control is labelled as an assumption.

    Attributes:
        name: A short name with no spaces for use inside the chart. For example "hours".
        values: The values the reader can pick. Rising numbers that are evenly spaced
            give a slider. Other values give buttons.
        default: The value shown first. It must be in `values`.
        label: The assumption in words. For example "hours of work per day".

    Example:
        ```python
        from scriptt.charts import Choice

        Choice(
            "hours",
            values=(2, 3, 4, 5, 6, 8),
            default=4,
            label="hours of work per day",
        )
        ```
    """

    name: str
    values: tuple[V, ...]
    default: V
    label: str

    def __post_init__(self) -> None:
        if self.default not in self.values:
            raise ValueError(
                f"the default {self.default!r} is not one of the values of "
                f"{self.name!r}"
            )
        if not self.name.isidentifier():
            raise ValueError(
                f"a choice name has letters, digits and _ only: {self.name!r}"
            )

    def control(self) -> dict[str, Any]:
        """The Vega-Lite parameter with its control. The control is a slider for evenly
        spaced numbers and radio buttons for other values."""
        label = f"{self.label} (assumption) "
        numbers = [
            v
            for v in self.values
            if isinstance(v, (int, float)) and not isinstance(v, bool)
        ]
        steps = {round(b - a, 9) for a, b in zip(numbers, numbers[1:])}
        if (
            len(numbers) == len(self.values)
            and len(steps) == 1
            and numbers == sorted(numbers)
        ):
            bind = {
                "input": "range",
                "min": numbers[0],
                "max": numbers[-1],
                "step": steps.pop(),
                "name": label,
            }
        else:
            bind = {
                "input": "radio",
                "options": [plain(v) for v in self.values],
                "name": label,
            }
        return {"name": self.name, "value": plain(self.default), "bind": bind}


def plain(value: Any) -> Any:
    """A value in a form that JSON can store. An enum becomes its value. A date becomes
    ISO text. A tuple becomes a list."""
    match value:
        case Enum():
            return plain(value.value)
        case dt.datetime() | dt.date():
            return value.isoformat()
        case tuple() | list():
            return [plain(v) for v in value]
        case float() if value != value or value in (
            float("inf"),
            float("-inf"),
        ):  # NaN and infinity are not JSON
            return None
    return value


def figures(value: Any) -> str:
    """A value as text for a label, written as `world.describe` writes it. A number has
    only its significant figures.
    A date reads "8 Oct 2026". A missing value is "no value"."""
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return (
            "no value"
            if value is None or value != value
            else ("infinite" if value > 0 else "minus infinite")
        )
    return describe(value)
