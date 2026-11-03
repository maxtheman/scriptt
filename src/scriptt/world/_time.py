"""Dates and times. `when` reads a date, a datetime and ISO 8601 text. It also reads
words such as "8 Oct 2026" or "yesterday"."""

import datetime as dt
import re
from enum import Enum

import dateparser

type Moment = dt.date | dt.datetime | str
"""A date or a time, in any of 3 forms: a `datetime.date`, a `datetime.datetime`, or
text.

Text can be ISO 8601 ("2026-10-08"), or words such as "8 Oct 2026", "10 Oct 2026 22:02"
or "yesterday".
Every date argument of the library takes a `Moment` and reads it with `when`.
"""


class Step(Enum):
    """The distance between 2 views in a series. `World.steps` takes a `Step`.

    Example:
        ```python
        from scriptt.world import Step

        views = today.steps(Step.DAY, 3)
        [view.on_date.isoformat() for view in views]
        # -> ['2026-11-04', '2026-11-05', '2026-11-06']
        ```
    """

    DAY = "day"
    """One calendar day."""
    WEEK = "week"
    """7 days."""
    MONTH = "month"
    """One calendar month. A day that the later month does not have moves to the last
    day of that month."""


def _parse(value: str, base: dt.datetime | None) -> dt.datetime:
    """The moment that text names. It has a time zone if the text has one."""
    text = value.strip()
    if re.fullmatch(r"\d{4}", text):
        raise ValueError(f"{value!r} is a year: write a day, such as 1 Jan {text}")
    if month := re.fullmatch(r"(\d{4})-(\d{1,2})", text):
        return dt.datetime(
            int(month[1]), int(month[2]), 1
        )  # a month means its first day; month 13 is an error
    if re.fullmatch(r"[\d.eE+-]+", text) and not re.fullmatch(
        r"\d{4}-\d{1,2}(-\d{1,2})?|\d{8}", text
    ):
        raise ValueError(
            f"{value!r} is a number, not a date: write 2026-10-08 or 8 Oct 2026"
        )
    if iso_day := re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", text):  # 2026-1-5 too
        try:
            return dt.datetime(int(iso_day[1]), int(iso_day[2]), int(iso_day[3]))
        except ValueError as error:
            raise ValueError(f"{value!r} is not a date: {error}") from None
    if re.match(
        r"\d{4}-\d{1,2}-\d{1,2}", text
    ):  # ISO-shaped text is ISO, or an error: never a guess
        try:
            return dt.datetime.fromisoformat(text)
        except ValueError as error:
            raise ValueError(f"{value!r} is not a date: {error}") from None
    try:
        return dt.datetime.fromisoformat(text)
    except ValueError:
        pass
    if year_first := re.fullmatch(r"(\d{4})[/.](\d{1,2})[/.](\d{1,2})", text):
        return dt.datetime(int(year_first[1]), int(year_first[2]), int(year_first[3]))
    if (
        (numeric := re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})", text))
        and int(numeric[1]) <= 12
        and int(numeric[2]) <= 12
    ):
        raise ValueError(
            f"{value!r} could be day/month or month/day: write 2026-10-08 or 8 Oct 2026"
        )
    parsed = dateparser.parse(
        text,
        settings={
            "DATE_ORDER": "DMY",
            "RELATIVE_BASE": base or dt.datetime.now(),
            "PREFER_DAY_OF_MONTH": "first",
        },
    )
    if parsed is None:
        raise ValueError(
            f"not a date: {value!r}. Write 2026-10-08, 8 Oct 2026, 10 Oct 2026 22:02 "
            f"or yesterday; "
            f"a number-only date is read day first"
        )
    return parsed


def _utc(moment: dt.datetime) -> dt.datetime:
    return moment.astimezone(dt.UTC).replace(tzinfo=None) if moment.tzinfo else moment


def when(value: Moment, *, base: dt.datetime | None = None) -> dt.datetime:
    """Read a moment and give a `datetime.datetime` with no time zone. Use it for the
    `known` argument and for any other time.

    ISO 8601 text is read first, so "2026-10-08" is always 8 Oct. Text with a time zone
    is changed to UTC. This makes 2 times
    from 2 zones compare correctly. Text with no zone is taken as written. Give every
    `known` time in 1 zone or with its zone.

    - "2026/10/08" and "2026.10.08" are year first too. "2026-10" is 1 Oct.
    - A date with no time gives midnight.
    - dateparser reads other text. Examples are "8 Oct 2026", "10 Oct 2026 22:02" and
    "yesterday".

    Args:
        value: The moment. Give a `datetime.datetime`, a `datetime.date` or text. A
            `datetime` with a time zone is changed to UTC.
        base: The time that relative text such as "yesterday" counts from. The default
            `None` means now.

    Returns:
        The moment as a `datetime.datetime` with no time zone.

    Raises:
        ValueError: The text is not a date. This includes a bare year ("2026"). It also
            includes ISO-shaped text that is not a date
            ("2026-13-01") and a number-only date that could be day/month or month/day
            ("8/10/2026").
        TypeError: `value` is not a date, a datetime or text.

    Example:
        ```python
        from scriptt.world import when

        when("2 Nov 2026")  # -> datetime.datetime(2026, 11, 2, 0, 0)
        when("2 Nov 2026 09:00")  # -> datetime.datetime(2026, 11, 2, 9, 0)
        when("2026-11-02T09:00-07:00")  # -> datetime.datetime(2026, 11, 2, 16, 0)
        ```
    """
    match value:
        case dt.datetime():
            return _utc(value)
        case dt.date():
            return dt.datetime.combine(value, dt.time())
        case str():
            return _utc(_parse(value, base))
    raise TypeError(f"not a date: {value!r}")


def day(value: Moment | None) -> dt.date | None:
    """A calendar day as written. true_from, true_until and `on` use it. A time zone
    does not move the day.
    So "2026-11-02T22:02-07:00" is 2 Nov."""
    match value:
        case None:
            return None
        case dt.datetime():
            return value.date()
        case dt.date():
            return value
        case str():
            return _parse(value, None).date()
    raise TypeError(f"not a date: {value!r}")


def end_of(value: Moment) -> dt.datetime:
    """A time for `known`. A date with no time of day means the end of that day. So
    `known("12 Oct")` and
    `known("yesterday")` include all of that day. "12 Oct 2026 14.30" and
    "2026-10-12T15" keep their time."""
    moment = when(value)
    if isinstance(value, dt.datetime):
        return moment
    if isinstance(value, dt.date):
        return moment.replace(hour=23, minute=59, second=59, microsecond=999999)
    relative_day = re.fullmatch(
        r"\s*(today|yesterday|tomorrow|(last|next|this) \w+|\d+ (days?|weeks?) ago)\s*",
        value,
        re.I,
    )
    has_time = re.search(
        r"T\d|\d:\d|\d\.\d\d\b|\d\s*[ap]\.?m\b|\b(noon|midnight|now|ago|hours?|minutes?)\b",
        value,
        re.I,
    )
    if (
        relative_day or not has_time
    ):  # no time of day in the text; an explicit "00:00" keeps its time
        return moment.replace(hour=23, minute=59, second=59, microsecond=999999)
    return moment


def step(start: dt.date, by: Step, n: int) -> dt.date:
    match by:
        case Step.DAY:
            return start + dt.timedelta(days=n)
        case Step.WEEK:
            return start + dt.timedelta(weeks=n)
        case Step.MONTH:
            month = start.month - 1 + n
            year, month = start.year + month // 12, month % 12 + 1
            last = (
                dt.date(year + (month == 12), month % 12 + 1, 1) - dt.timedelta(days=1)
            ).day
            return dt.date(year, month, min(start.day, last))
