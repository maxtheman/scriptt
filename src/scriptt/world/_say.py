"""Text from t-strings. `say(t"...")` shows each value by what it is.

- A fact shows its own description (`__describe__` is a t-string). Without one it shows
its type and key.
- A number shows its significant figures only (`{x:.3}` asks for 3). So
0.30000000000000004 shows as 0.3.
- A date with a format shows that format. So `{day:%-d %b}` gives "8 Oct".
- A date shows as "8 Oct 2026".
- A date and time shows as "10 Oct 2026, 22:02".
- A time span shows as "3 days".
- An enum shows its value.
- A log entry shows what it says. It also shows when you got it and where from.
- A list of values shows as "a, b and c".
"""

import datetime as dt
import math
from collections.abc import Iterable
from enum import Enum
from string.templatelib import Interpolation, Template
from typing import Any


def significant(
    value: float, digits: int | None = None, *, grouping: bool = True
) -> str:
    """Write a number with its significant figures only, and with no float noise.

    - `digits` gives at most that number of significant figures.
    - Without `digits`, a value that is exact to 0 or 1 or 2 decimals keeps them. Any
    other value shows 4 significant figures.
    - A value under 0.0001 is written with an exponent. An example is 1.5e-09.

    Args:
        value: The number.
        digits: The most significant figures to show. The default `None` means the rules
            above.
        grouping: Whether to put a comma between thousands. The default is `True`. Use
            `False` for a repr.

    Returns:
        The number as text.

    Example:
        ```python
        from scriptt.world import significant

        significant(276.85)  # -> '276.85'
        significant(2.5266666)  # -> '2.527'
        significant(0.19166, 2)  # -> '0.19'
        significant(12345678.0)  # -> '12,345,678'
        significant(12345678.0, grouping=False)  # -> '12345678'
        ```
    """
    if digits is not None and digits < 1:
        raise ValueError(f"significant figures must be 1 or more, not {digits}")
    if value == 0 or not math.isfinite(value):
        return "0" if value == 0 else str(value)
    if abs(value) < 1e-4:
        return f"{value:.{digits or 4}g}"
    comma = "," if grouping else ""
    if digits is None:
        for places in (0, 1, 2):
            scaled = value * 10**places
            if abs(scaled) < 1e15 and abs(scaled - round(scaled)) < 1e-6:
                return f"{value:{comma}.{places}f}"
        digits = 4
    magnitude = math.floor(math.log10(abs(value)))
    rounded = round(value, digits - 1 - magnitude)
    if magnitude >= digits - 1:
        return f"{int(round(rounded)):{comma}}"
    return f"{rounded:{comma}.{max(digits - 1 - magnitude, 0)}f}".rstrip("0").rstrip(
        "."
    )


def relative(
    earlier_or_later: dt.date | dt.datetime | None,
    reference: dt.date | dt.datetime | None,
) -> str:
    """Say how a date stands to a reference date. An example is "3 days before".

    Only the calendar day counts. A time of day is ignored. A fact that is true for all
    time has no start date. If
    either date is `None`, the text says that the time is not known.

    Args:
        earlier_or_later: The date to describe. A `datetime.date` or `datetime.datetime`
            or `None`.
        reference: The date to compare with. A `datetime.date` or `datetime.datetime` or
            `None`.

    Returns:
        One of these texts.

        - "3 days before"
        - "1 day after"
        - "on the same day as"
        - "at a time not known relative to"

    Example:
        ```python
        import datetime as dt
        from scriptt.world import relative

        relative(dt.date(2026, 11, 2), dt.date(2026, 11, 4))  # -> '2 days before'
        relative(dt.date(2026, 11, 4), dt.date(2026, 11, 4))
        # -> 'on the same day as'
        relative(None, dt.date(2026, 11, 4))  # -> 'at a time not known relative to'
        ```
    """
    if earlier_or_later is None or reference is None:
        return "at a time not known relative to"
    a = (
        earlier_or_later.date()
        if isinstance(earlier_or_later, dt.datetime)
        else earlier_or_later
    )
    b = reference.date() if isinstance(reference, dt.datetime) else reference
    days = (a - b).days
    if days == 0:
        return "on the same day as"
    unit = "day" if abs(days) == 1 else "days"
    return f"{abs(days)} {unit} {'before' if days < 0 else 'after'}"


def describe(value: Any, spec: str = "") -> str:
    """Write 1 value as text by what it is. `say` calls this for each value of a
    t-string.

    A value with a `__describe__` method uses it. The other values follow these rules.

    - A number shows its significant figures.
    - A date shows as "8 Oct 2026".
    - An enum shows its value.
    - A list shows as "a, b and c".
    - Any other value uses `format`.

    Args:
        value: The value to write.
        spec: The format that follows the colon in `{value:spec}`. The default is an
            empty text. It means no format.
            A number takes `.3` for 3 significant figures. A date takes a `strftime`
            format. Text takes `58` to pad it to 58 characters.

    Returns:
        The text of the value.

    Example:
        ```python
        import datetime as dt
        from scriptt.world import describe

        describe(1.5000000001)  # -> '1.5'
        describe(dt.date(2026, 11, 2))  # -> '2 Nov 2026'
        describe(["a", "b", "c"])  # -> 'a, b and c'
        describe(True)  # -> 'yes'
        describe(Status.DONE)  # -> 'done'
        ```
    """
    match value:
        case Template():
            return say(value)
        case _ if hasattr(value, "__describe__"):
            return say(value.__describe__())
        case bool():
            return "yes" if value else "no"
        case Enum():
            return str(value.value)
        case float():
            return significant(
                value, int(spec.lstrip(".")) if spec.lstrip(".").isdigit() else None
            )
        case int() if spec.lstrip(".").isdigit():
            return significant(float(value), int(spec.lstrip(".")), grouping=False)
        case int():
            return (
                format(value, spec) if spec else str(value)
            )  # a year or an id has no comma; {n:,} asks for one
        case dt.timedelta():
            return _span(value)
        case dt.date() if spec:
            return format(value, spec)
        case dt.datetime():
            return (
                f"{value:%-d %b %Y, %H:%M}"
                if value.time() != dt.time()
                else f"{value:%-d %b %Y}"
            )
        case dt.date():
            return f"{value:%-d %b %Y}"
        case None:
            return "none"
        case str():
            return format(value, spec) if spec else value
        case list() | tuple() | set() | frozenset():
            return _join([describe(v, spec) for v in value])
        case _ if isinstance(value, Iterable) and hasattr(value, "count"):
            return _join([describe(v, spec) for v in value])
    return format(value, spec) if spec else str(value)


def _span(value: dt.timedelta) -> str:
    """A time span in its 2 largest whole units.

    - "3 days"
    - "23 hours 59 minutes"
    - "1 day 1 hour"
    - "5 seconds"
    """
    left, parts = abs(round(value.total_seconds())), []
    for size, unit in ((86_400, "day"), (3_600, "hour"), (60, "minute"), (1, "second")):
        if left >= size and len(parts) < 2:
            amount, left = divmod(left, size)
            parts.append(f"{amount} {unit}{'' if amount == 1 else 's'}")
        elif parts:
            # 2 units next to each other only: "1 day 1 hour", never "1 day 5 seconds"
            break
    text = " ".join(parts) or "0 seconds"
    return f"minus {text}" if value.total_seconds() < 0 and parts else text


def _join(parts: list[str]) -> str:
    return (
        "none"
        if not parts
        else parts[0]
        if len(parts) == 1
        else ", ".join(parts[:-1]) + " and " + parts[-1]
    )


def say(template: Template) -> str:
    """Make text from a t-string. Each value shows by what it is, as `describe`
    explains.

    A conversion `!r` in the t-string gives the `repr` of the value. A format after a
    colon goes to `describe`.

    Args:
        template: A Python 3.14 t-string. An example is `t"{fact} came out {outcome}"`.

    Returns:
        The text.

    Example:
        ```python
        from scriptt.world import say

        report = today.one(Task, id="t2")
        say(t"Today, {report} is {report.status}.")
        # -> 'Today, task t2 is open.'
        say(t"The mean is {17.490000000001:.3}.")  # 'The mean is 17.5.'
        ```
    """
    out = []
    for part in template:
        if isinstance(part, Interpolation):
            value = part.value
            if part.conversion == "r":
                out.append(repr(value))
            else:
                out.append(describe(value, part.format_spec))
        else:
            out.append(part)
    return "".join(out)
