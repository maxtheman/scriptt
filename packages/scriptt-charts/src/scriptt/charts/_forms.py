"""The forms of chart. Each form takes any items and functions that read them. Each form
gives a `Chart`.

Every form takes the same shared options:

- `n` (the count behind each value)
- `trace` (its source and known time)
- `flag` (a rule that marks items)
- `note` (a note next to an item)
- `detail` (more values for the tooltip)

With `choice=Choice(...)` the argument `items` is a function of the choice value. The
reader picks the value on the
chart.
"""

import datetime as dt
import json
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from ._chart import (
    SERIES,
    Chart,
    Marks,
    each_choice,
    filtered,
    marked_line,
    rows_of,
    tooltip,
)
from ._chart import order as _order
from ._parts import Choice, Flag, Scope, Target, figures, plain

type Items[T] = Iterable[T] | Callable[[Any], Iterable[T]]
LIGHT_BLUE, GREY_CELL, MUTED = "#9ec5f4", "#f0efec", "#8a8984"


def money(value: float | None) -> str:
    """A dollar amount for a label. An amount below $10,000 has cents. For example
    money(14.0) -> "$14.00" and money(12500.0) -> "$12,500"."""
    if value is None or value != value:
        return "no value"
    sign, value = (
        "-" if value < 0 else "",
        abs(float(value)),
    )  # a whole number of dollars still reads "$500,000"
    return f"{sign}${value:,.2f}" if value < 10_000 else f"{sign}${figures(value)}"


def ranked[T](
    items: Items[T],
    *,
    title: str,
    scope: Scope,
    label: Callable[[T], object],
    value: Callable[[T], float | None],
    unit: str = "",
    show: Callable[[float], str] = figures,
    missing: Callable[[T], str | None] | None = None,
    target: Target | None = None,
    shares: bool = True,
    summary: str | Mapping[Any, str] = "",
    choice: Choice | None = None,
    n: Callable[[T], int | None] | None = None,
    trace: Callable[[T], Any] | None = None,
    flag: Flag[T] | None = None,
    note: Callable[[T], str | None] | None = None,
    detail: Mapping[str, Callable[[T], Any]] | None = None,
    traces: Mapping[str, Callable[[T], Any]] | None = None,
) -> Chart:
    """Items in order of a value. Each item has its share of the total and the
    cumulative share.

    An item with no value is listed at the end as "no value" and with the reason that
    `missing` gives. The total
    does not count it and the chart does not draw it as 0.

    Args:
        items: The items. A function of the choice value that gives the items also
            works.
        title: The question the chart answers.
        scope: What the chart covers and leaves out.
        label: The name of an item.
        value: The value of an item, or None if it has none.
        unit: The title of the value axis. For example "dollars".
        show: How a value is written in its label (`money` for dollars).
        missing: The reason an item has no value.
        target: A target line on the value axis (with its status).
        shares: False if the items are not parts of 1 whole (plans or scenarios). Then
            no share is shown.
        summary: A sentence above the chart. 1 sentence for each choice value also
            works.
        choice: An assumption the reader can change.
        n: The count behind an item's value. It is shown next to the value.
        trace: The source and known time of an item's value. It is a `Trace`, a World
            API `Origin` or a World API `Entry`.
        flag: A rule that marks some items with ⚑. The subtitle gives the rule and the
            count it marks.
        note: A short note shown next to an item.
        detail: More values for the tooltip and the table view. For example `{"sales":
            lambda p: p.sales}`.
        traces: The traces of an item's other values by name. Each gives "<name> source"
            and "<name> known".

    Returns:
        The chart. Its table view lists each item with its value, share and cumulative
        share.

    Example:
        ```python
        from scriptt.charts import Scope, ranked
        from types import SimpleNamespace as Task

        items = [
            Task(title="Buy milk", minutes=15),
            Task(title="Send the report", minutes=45),
        ]
        ranked(
            items,
            title="Which tasks take the most time?",
            scope=Scope("the to-do list of 4 Nov 2026"),
            label=lambda t: t.title,
            value=lambda t: t.minutes,
            unit="minutes",
        )
        ```
    """
    marks = Marks(n, trace, flag, note, detail or {}, traces or {})
    rows: list[dict[str, Any]] = []
    chosen = each_choice(items, choice)  # items are read once: a generator works
    for picked, group in chosen:
        made = rows_of(
            group,
            label,
            {"value": value},
            marks,
            picked,
            frozenset({"share %", "so far %", "missing"}),
        )
        why = [missing(i) if missing else None for i in group]
        present = sorted(
            (r for r in made if r["value"] is not None), key=lambda r: -r["value"]
        )
        if shares and any(r["value"] < 0 for r in present):
            raise ValueError(
                "ranked shows shares of a total, so a value cannot be below 0; give "
                "shares=False"
            )
        total, running = sum(r["value"] for r in present), 0.0
        for rank, row in enumerate(present):
            running += row["value"]
            row |= {
                "rank": rank,
                "share %": round(100 * row["value"] / total, 1)
                if total and shares
                else None,
                "so far %": round(100 * running / total, 1)
                if total and shares
                else None,
            }
            parts = [show(row["value"])] + (
                [
                    f"{_percent(row['share %'])} of total, {_percent(row['so far %'])} "
                    f"so far"
                ]
                if total and shares
                else []
            )
            row["text"] = " · ".join(parts + _shared_text(row))
        for rank, (row, reason) in enumerate(
            ((r, w) for r, w in zip(made, why) if r["value"] is None),
            start=len(present),
        ):
            row |= {
                "rank": rank,
                "missing": reason or "no value",
                "text": " · ".join(
                    ["no value" + (f": {reason}" if reason else "")] + _shared_text(row)
                ),
            }
        rows += present + [r for r in made if r["value"] is None]
    top = max((r["value"] for r in rows if r["value"] is not None), default=1) or 1
    count = max(len(g) for _, g in chosen)
    y = {
        "field": "label",
        "type": "nominal",
        "sort": _order(rows, choice),
        "title": None,
    }
    x = {
        "field": "value",
        "type": "quantitative",
        "title": unit or None,
        "scale": {"domain": [0, top * 1.9]},
        "axis": {"tickCount": 5},
    }
    layers: list[dict[str, Any]] = [
        {
            "transform": [{"filter": "datum.value != null"}],
            "mark": {
                "type": "bar",
                "cornerRadiusEnd": 4,
                "height": {"band": 0.66},
                "color": SERIES[0],
            },
            "encoding": {
                "x": x,
                "y": y,
                "tooltip": tooltip(rows, "value", "share %", "so far %"),
            },
        },
        {
            "mark": {"type": "text", "align": "left", "dx": 5, "color": "#52514e"},
            "encoding": {
                "x": {
                    "field": "value",
                    "type": "quantitative",
                    "scale": {"domain": [0, top * 1.9]},
                },
                "y": y,
                "text": {"field": "text"},
            },
        },
    ]
    layers[1]["transform"] = [
        {"calculate": "datum.value == null ? 0 : datum.value", "as": "value"}
    ]
    layers += _target_layers(target, axis="x")
    view = filtered(
        {
            "data": {"values": rows},
            "width": 560,
            "height": max(60, 24 * count),
            "layer": layers,
        },
        choice,
    )
    marked = " · ".join(
        x
        for x in (
            marked_line(marks, rows, choice),
            f"Target: {target.text()}" if target else "",
        )
        if x
    )
    return Chart(
        title,
        view,
        scope,
        tuple(rows),
        (
            "item",
            "value",
            "share %",
            "so far %",
            "missing",
            "n",
            "note",
            "source",
            "known",
            *marks.columns(),
        ),
        summary,
        marked,
        choice,
    )


def ranges[T](
    items: Items[T],
    *,
    title: str,
    scope: Scope,
    label: Callable[[T], object],
    low: Callable[[T], float | dt.date | None],
    high: Callable[[T], float | dt.date | None],
    mid: Callable[[T], float | dt.date | None] | None = None,
    point: Callable[[T], float | dt.date | None] | None = None,
    range_name: str = "low to high",
    mid_name: str = "middle",
    point_name: str = "value",
    unit: str = "",
    order: Callable[[T], Any] | None = None,
    summary: str | Mapping[Any, str] = "",
    choice: Choice | None = None,
    n: Callable[[T], int | None] | None = None,
    trace: Callable[[T], Any] | None = None,
    flag: Flag[T] | None = None,
    note: Callable[[T], str | None] | None = None,
    detail: Mapping[str, Callable[[T], Any]] | None = None,
    traces: Mapping[str, Callable[[T], Any]] | None = None,
) -> Chart:
    """For each item, a range from low to high. Each range has a middle and a point. The
    values may be numbers or dates.
    With dates the range is 2 dates of 1 item, such as true from and known. Its label
    gives the gap in days.

    An item with no low or high has no range. The chart still draws its middle and
    point.

    Args:
        items: The items. A function of the choice value that gives the items also
            works.
        title: The question the chart answers.
        scope: What the chart covers and leaves out.
        label: The name of an item.
        low: The low end of the range (a number or a date).
        high: The high end of the range.
        mid: A middle value. The chart draws it as a tick.
        point: A second measure of the same unit. The chart draws it as a diamond (an
            ask against a sold range).
        range_name: The name of the range in the legend.
        mid_name: The name of the middle tick in the legend.
        point_name: The name of the point in the legend.
        unit: The title of the value axis.
        order: The sort key of the items. The default is the order given.
        summary: A sentence shown above the chart. A dict with 1 sentence for each
            choice value also works.
        choice: An assumption the reader can change. Then `items` is a function of its
            value.
        n: The count behind an item's value. It is shown next to the value.
        trace: The source and known time of an item's value. It is a `Trace`, a World
            API `Origin` or a World API `Entry`.
        flag: A rule that marks some items with ⚑. The subtitle gives the rule and the
            count it marks.
        note: A short note shown next to an item.
        detail: More values for the tooltip and the table view. For example `{"sales":
            lambda p: p.sales}`.
        traces: The traces of an item's other values by name. Each gives "<name> source"
            and "<name> known".

    Returns:
        The chart.

    Example:
        ```python
        from types import SimpleNamespace as Guess
        from scriptt.charts import Scope, ranges

        guesses = [Guess(title="Send the report", low=30, high=90, best=45, runs=10)]
        ranges(
            guesses,
            title="Which time guesses can I trust?",
            scope=Scope("62 finished tasks"),
            label=lambda g: g.title,
            low=lambda g: g.low,
            high=lambda g: g.high,
            mid=lambda g: g.best,
            n=lambda g: g.runs,
        )
        ```
    """
    marks = Marks(n, trace, flag, note, detail or {}, traces or {})
    rows: list[dict[str, Any]] = []
    sample = None
    chosen = each_choice(items, choice)  # items are read once: a generator works
    for picked, group in chosen:
        group = sorted(group, key=order) if order else group
        made = rows_of(
            group,
            label,
            {
                "low": low,
                "high": high,
                "mid": mid or (lambda i: None),
                "point": point or (lambda i: None),
            },
            marks,
            picked,
        )
        for rank, (item, row) in enumerate(zip(group, made)):
            sample = sample or next(
                (
                    v
                    for v in (low(item), high(item), mid(item) if mid else None)
                    if v is not None
                ),
                None,
            )
            ends = [
                row[k] for k in ("high", "point", "mid", "low") if row[k] is not None
            ]
            row |= {"rank": rank, "end": max(ends) if ends else None}
            gap = _days(low(item), high(item))
            row["text"] = " · ".join(
                ([_gap(gap)] if gap is not None else []) + _shared_text(row)
            )
        rows += made
    temporal = isinstance(sample, dt.date)
    kind = "temporal" if temporal else "quantitative"
    count = max(len(g) for _, g in chosen)
    y = {
        "field": "label",
        "type": "nominal",
        "sort": _order(rows, choice),
        "title": None,
    }
    names = [range_name] + ([mid_name] if mid else []) + ([point_name] if point else [])
    paint = {
        range_name: LIGHT_BLUE,
        mid_name: SERIES[0],
        point_name: SERIES[1],
    }  # each mark keeps its colour
    colour = {
        "field": "part",
        "type": "nominal",
        "scale": {"domain": names, "range": [paint[n] for n in names]},
        "legend": {"title": None},
    }

    def part(name: str) -> dict[str, Any]:
        return {
            "calculate": json.dumps(name),
            "as": "part",
        }  # the mark's name, as a field the colour scale reads

    tip = tooltip(rows, "low", "high", "mid", "point")
    x_axis = {"type": kind, "title": unit or None} | (
        {"axis": {"format": "%-d %b %Y", "labelOverlap": True, "tickCount": "month"}}
        if temporal
        else {"scale": {"zero": False}}
    )
    layers: list[dict[str, Any]] = [
        {
            "transform": [
                {"filter": "datum.low != null && datum.high != null"},
                part(range_name),
            ],
            "mark": {"type": "rule", "strokeWidth": 4, "strokeCap": "round"},
            "encoding": {
                "x": {"field": "low"} | x_axis,
                "x2": {"field": "high"},
                "y": y,
                "color": colour,
                "tooltip": tip,
            },
        },
    ]
    if mid:
        layers.append(
            {
                "transform": [{"filter": "datum.mid != null"}, part(mid_name)],
                "mark": {"type": "tick", "thickness": 3, "size": 16},
                "encoding": {
                    "x": {"field": "mid", "type": kind},
                    "y": y,
                    "color": colour,
                    "tooltip": tip,
                },
            }
        )
    if point:
        layers.append(
            {
                "transform": [{"filter": "datum.point != null"}, part(point_name)],
                "mark": {
                    "type": "point",
                    "shape": "diamond",
                    "filled": True,
                    "size": 110,
                    "stroke": "#fcfcfb",
                    "strokeWidth": 2,
                },
                "encoding": {
                    "x": {"field": "point", "type": kind},
                    "y": y,
                    "color": colour,
                    "tooltip": tip,
                },
            }
        )
    layers.append(
        {
            "transform": [{"filter": "datum.end != null"}],
            "mark": {"type": "text", "align": "left", "dx": 8, "color": "#52514e"},
            "encoding": {
                "x": {"field": "end", "type": kind},
                "y": y,
                "text": {"field": "text"},
            },
        }
    )
    view = filtered(
        {
            "data": {"values": rows},
            "width": 520,
            "height": max(60, 24 * count),
            "layer": layers,
        },
        choice,
    )
    return Chart(
        title,
        view,
        scope,
        tuple(rows),
        (
            "item",
            "low",
            "mid",
            "high",
            "point",
            "n",
            "note",
            "source",
            "known",
            *marks.columns(),
        ),
        summary,
        marked_line(marks, rows, choice),
        choice,
    )


def over_time[T](
    items: Items[T],
    *,
    title: str,
    scope: Scope,
    x: Callable[[T], dt.date | dt.datetime],
    series: Mapping[str, Callable[[T], float | None]],
    unit: str = "",
    steps: bool = False,
    partial_from: dt.date | dt.datetime | None = None,
    dates: Mapping[str, dt.date | dt.datetime | None] | None = None,
    target: Target | None = None,
    date_format: str = "%-d %b",
    notes_on: str | None = None,
    summary: str | Mapping[Any, str] = "",
    choice: Choice | None = None,
    n: Callable[[T], int | None] | None = None,
    trace: Callable[[T], Any] | None = None,
    flag: Flag[T] | None = None,
    note: Callable[[T], str | None] | None = None,
    detail: Mapping[str, Callable[[T], Any]] | None = None,
    traces: Mapping[str, Callable[[T], Any]] | None = None,
    counts: Mapping[str, Callable[[T], int | None]] | None = None,
) -> Chart:
    """1 or more values over dates. Each series is named at its last point.

    Args:
        items: 1 item for each date. A function of the choice value that gives them also
            works.
        title: The question the chart answers.
        scope: What the chart covers and leaves out.
        x: The date or time of an item.
        series: For each series name, its value for an item. None means no point on that
            date.
        unit: The title of the value axis.
        steps: True if a value stays the same until the next date (a step line). False
            for a straight line between points.
        partial_from: Dates from here on are a partial period (the month is not over).
            The chart shades and labels them.
        dates: Named dates drawn as vertical lines. For example `{"deadline":
            dt.date(2026, 12, 8)}`. A date that is None is not drawn.
        target: A target line on the value axis.
        date_format: The format of the date labels on the axis.
        counts: The count behind each series' value by series name. For example `{"with
            a pay range": lambda m: m.paid}`. A
            series with no entry uses `n`.
        notes_on: The series whose points carry the notes and the ⚑ marks. By default
            the chart draws an item's note once
            on the first series that has a value for it.
        summary: A sentence shown above the chart. A dict with 1 sentence for each
            choice value also works.
        choice: An assumption the reader can change. Then `items` is a function of its
            value.
        n: The count behind an item's value. It is shown next to the value.
        trace: The source and known time of an item's value. It is a `Trace`, a World
            API `Origin` or a World API `Entry`.
        flag: A rule that marks some items with ⚑. The subtitle gives the rule and the
            count it marks.
        detail: More values for the tooltip and the table view. For example `{"sales":
            lambda p: p.sales}`.
        traces: The traces of an item's other values by name. Each gives "<name> source"
            and "<name> known".
        note: A short note. The chart draws it at its point.

    Returns:
        The chart.

    Example:
        ```python
        import datetime as dt
        from types import SimpleNamespace as Month
        from scriptt.charts import Scope, over_time

        months = [
            Month(month=dt.date(2026, 9, 1), added=60),
            Month(month=dt.date(2026, 10, 1), added=70),
        ]
        over_time(
            months,
            title="Do I add more tasks each month?",
            scope=Scope("the to-do list, 2 months"),
            x=lambda m: m.month,
            series={"added": lambda m: m.added},
            partial_from=dt.date(2026, 10, 1),
        )
        ```
    """
    marks = Marks(n, trace, flag, note, detail or {}, traces or {})
    rows: list[dict[str, Any]] = []
    chosen = each_choice(items, choice)  # items are read once: a generator works
    for picked, group in chosen:
        noted = (
            [False] * len(group)
            # an item's note and ⚑ are drawn once: on `notes_on`, else its first series
            # with a value
        )
        for name, read in series.items():
            made = rows_of(
                group,
                lambda i: x(i),
                {"x": x, "value": read},
                marks,
                picked,
                frozenset({"series", "last", "_noted"}),
            )
            for index, (item, row) in enumerate(zip(group, made)):
                row["series"] = name
                if counts and name in counts:
                    row["n"] = counts[name](item)
                row["_noted"] = (
                    not noted[index]
                    and row["value"] is not None
                    and (notes_on is None or name == notes_on)
                )
                noted[index] = noted[index] or row["_noted"]
            made = [
                r for r in made if r["value"] is not None
            ]  # an item with no value in a series has no row in it
            last = max((r["x"] for r in made if r["value"] is not None), default=None)
            for row in made:
                row["last"] = row["x"] == last and row["value"] is not None
                row["text"] = " · ".join(_shared_text(row))
            rows += made
    names = list(series)
    colour = {
        "field": "series",
        "type": "nominal",
        "scale": {"domain": names, "range": list(SERIES[: len(names)])},
        "legend": {"title": None} if len(names) > 1 else None,
    }
    xs_all = sorted({r["x"] for r in rows if r.get("x")})
    span = (
        (
            dt.date.fromisoformat(xs_all[-1][:10])
            - dt.date.fromisoformat(xs_all[0][:10])
        ).days
        if len(xs_all) > 1
        else 0
    )
    step = (
        None
        if "%H" in date_format
        else "day"
        if span <= 14
        else "week"
        if span <= 90
        else "month"
        if span <= 800
        else "year"
    )  # by the span
    xs = {
        "field": "x",
        "type": "temporal",
        "title": None,
        "axis": {"format": date_format, "labelAngle": 0}
        | ({"tickCount": step} if step else {}),
    }  # 1 label for each day or month
    ys = {"field": "value", "type": "quantitative", "title": unit or None}
    tip = [
        {"field": "series"},
        {"field": "x", "type": "temporal", "format": "%-d %b %Y %H:%M"},
    ] + tooltip(rows, "value")[1:]
    layers: list[dict[str, Any]] = []
    if partial_from is not None:
        end = max((r["x"] for r in rows), default=plain(partial_from))
        layers.append(
            {
                "data": {
                    "values": [
                        {"a": plain(partial_from), "b": end, "t": "partial period"}
                    ]
                },
                "layer": [
                    {
                        "mark": {"type": "rect", "color": "#8a8984", "opacity": 0.12},
                        "encoding": {
                            "x": {"field": "a", "type": "temporal"},
                            "x2": {"field": "b"},
                        },
                    },
                    {
                        "mark": {
                            "type": "text",
                            "align": "left",
                            "baseline": "top",
                            "dx": 4,
                            "dy": 4,
                            "color": MUTED,
                        },
                        "encoding": {
                            "x": {"field": "a", "type": "temporal"},
                            "y": {"value": 0},
                            "text": {"field": "t"},
                        },
                    },
                ],
            }
        )
    layers += [
        {
            "transform": [{"filter": "datum.value != null"}],
            "mark": {
                "type": "line",
                "strokeWidth": 2,
                "interpolate": "step-after" if steps else "linear",
            },
            "encoding": {"x": xs, "y": ys, "color": colour},
        },
        {
            "transform": [{"filter": "datum.value != null"}],
            "mark": {
                "type": "point",
                "filled": True,
                "size": 64,
                "stroke": "#fcfcfb",
                "strokeWidth": 2,
            },
            "encoding": {"x": xs, "y": ys, "color": colour, "tooltip": tip},
        },
        {
            "transform": [{"filter": "datum.last"}],
            "mark": {"type": "text", "align": "left", "dx": 7, "color": "#52514e"},
            "encoding": {"x": xs, "y": ys, "text": {"field": "series"}},
        },
        {
            "transform": [
                {"filter": "datum._noted && (datum.note != '' || datum.flagged)"}
            ],
            "mark": {
                "type": "text",
                "align": "left",
                "dx": 7,
                "dy": -10,
                "color": "#52514e",
                "fontStyle": "italic",
            },
            "encoding": {"x": xs, "y": ys, "text": {"field": "_mark"}},
        },
    ]
    layers[-1]["transform"].insert(
        0, {"calculate": f"(datum.flagged ? '⚑ ' : '') + datum.note", "as": "_mark"}
    )
    for name, when in (dates or {}).items():
        if when is None:
            continue
        layers.append(
            {
                "data": {"values": [{"d": plain(when), "t": name}]},
                "layer": [
                    {
                        "mark": {"type": "rule", "strokeDash": [4, 3], "color": MUTED},
                        "encoding": {"x": {"field": "d", "type": "temporal"}},
                    },
                    {
                        "mark": {
                            "type": "text",
                            "align": "left",
                            "baseline": "top",
                            "dx": 4,
                            "dy": 16,
                            "color": MUTED,
                        },
                        "encoding": {
                            "x": {"field": "d", "type": "temporal"},
                            "y": {"value": 0},
                            "text": {"field": "t"},
                        },
                    },
                ],
            }
        )
    layers += _target_layers(target, axis="y")
    view = {"data": {"values": rows}, "width": 560, "height": 260, "layer": layers}
    if choice is not None:
        for layer in layers:
            if "data" not in layer:
                layer["transform"] = [
                    {"filter": f"datum.choice == {choice.name}"}
                ] + layer.get("transform", [])
    rows.sort(
        key=lambda r: (
            r.get("choice") is None,
            str(r.get("choice")),
            r["series"],
            str(r["x"]),
        )
    )  # the table reads by date
    marked = " · ".join(
        x
        for x in (
            marked_line(marks, rows, choice),
            f"Target: {target.text()}" if target else "",
        )
        if x
    )
    return Chart(
        title,
        view,
        scope,
        tuple(rows),
        ("series", "x", "value", "n", "note", "source", "known", *marks.columns()),
        summary,
        marked,
        choice,
    )


def views[T](
    items: Items[T],
    *,
    title: str,
    scope: Scope,
    label: Callable[[T], object],
    views: Mapping[str, Callable[[T], float | None]],
    unit: str = "",
    show: Callable[[float], str] = figures,
    domain: tuple[float, float] | None = None,
    order: Callable[[T], Any] | None = None,
    summary: str | Mapping[Any, str] = "",
    choice: Choice | None = None,
    n: Callable[[T], int | None] | None = None,
    trace: Callable[[T], Any] | None = None,
    flag: Flag[T] | None = None,
    note: Callable[[T], str | None] | None = None,
    detail: Mapping[str, Callable[[T], Any]] | None = None,
    traces: Mapping[str, Callable[[T], Any]] | None = None,
) -> Chart:
    """2 or 3 named views of the same items side by side. The chart draws a point for
    each view and joins the points by a
    line. Name each view with its date or its assumption. For example "as planned on
    1 Nov 2026", "now (4 Nov 2026)"
    or "if I finish early".

    Args:
        items: The items. A function of the choice value that gives the items also
            works.
        title: The question the chart answers.
        scope: What the chart covers and leaves out.
        label: The name of an item.
        views: For each view name, the item's value in that view. None means not in that
            view.
        unit: The title of the value axis.
        show: How a value is written in the label at the right.
        domain: The value axis from low to high. For example `(0, 1)` for probabilities.
            The default starts at 0 and
            leaves room for the labels.
        order: The sort key of the items. The default is the order given.
        summary: A sentence shown above the chart. A dict with 1 sentence for each
            choice value also works.
        choice: An assumption the reader can change. Then `items` is a function of its
            value.
        n: The count behind an item's value. It is shown next to the value.
        trace: The source and known time of an item's value. It is a `Trace`, a World
            API `Origin` or a World API `Entry`.
        flag: A rule that marks some items with ⚑. The subtitle gives the rule and the
            count it marks.
        note: A short note shown next to an item.
        detail: More values for the tooltip and the table view. For example `{"sales":
            lambda p: p.sales}`.
        traces: The traces of an item's other values by name. Each gives "<name> source"
            and "<name> known".

    Returns:
        The chart. The label at the right gives each view's value.

    Example:
        ```python
        from types import SimpleNamespace as Plan
        from scriptt.charts import Scope, views

        plans = [Plan(task="Book the room", planned=30, now=50)]
        views(
            plans,
            title="Did any time guess change after the work?",
            scope=Scope("5 tasks"),
            label=lambda p: p.task,
            views={"as planned": lambda p: p.planned, "now": lambda p: p.now},
        )
        ```
    """
    if len(views) > 3:
        raise ValueError(
            "views shows 2 or 3 views; use small multiples (side_by_side) for more"
        )
    marks = Marks(n, trace, flag, note, detail or {}, traces or {})
    names = list(views)
    items_rows: list[dict[str, Any]] = []
    long: list[dict[str, Any]] = []
    chosen = each_choice(items, choice)  # items are read once: a generator works
    for picked, group in chosen:
        group = sorted(group, key=order) if order else group
        made = rows_of(group, label, dict(views), marks, picked)
        for rank, row in enumerate(made):
            values = [row[v] for v in names if row[v] is not None]
            row |= {
                "rank": rank,
                "lo": min(values) if values else None,
                "hi": max(values) if values else None,
            }
            row["text"] = " · ".join(
                [
                    " → ".join(
                        show(row[v]) if row[v] is not None else "none" for v in names
                    )
                ]
                + _shared_text(row)
            )
            for v in names:
                long.append(
                    {
                        k: row[k]
                        for k in (
                            "item",
                            "label",
                            "rank",
                            "choice",
                            "n",
                            "note",
                            "source",
                            "known",
                        )
                        if k in row
                    }
                    | {"view": v, "value": row[v]}
                )
        items_rows += made
    count = max(len(g) for _, g in chosen)
    y = {
        "field": "label",
        "type": "nominal",
        "sort": _order(items_rows, choice),
        "title": None,
    }
    top = max((r["hi"] for r in items_rows if r["hi"] is not None), default=1)
    x = {
        "type": "quantitative",
        "title": unit or None,
        "scale": {"domain": list(domain) if domain else [0, top * 1.9]},
    }
    width = (
        560 if domain is None else 340
    )  # with a fixed domain, the labels go in a column of their own
    colour = {
        "field": "view",
        "type": "nominal",
        "scale": {"domain": names, "range": list(SERIES[: len(names)])},
        "legend": {"title": None},
    }
    pick = [{"filter": f"datum.choice == {choice.name}"}] if choice else []
    layers = [
        {
            "data": {"values": items_rows},
            "transform": pick + [{"filter": "datum.lo != null"}],
            "mark": {"type": "rule", "color": "#c3c2b7", "strokeWidth": 2},
            "encoding": {"x": {"field": "lo"} | x, "x2": {"field": "hi"}, "y": y},
        },
        {
            "data": {"values": long},
            "transform": pick + [{"filter": "datum.value != null"}],
            "mark": {
                "type": "point",
                "filled": True,
                "size": 90,
                "stroke": "#fcfcfb",
                "strokeWidth": 2,
            },
            "encoding": {
                "x": {"field": "value"} | x,
                "y": y,
                "color": colour,
                "tooltip": [{"field": "item"}, {"field": "view"}, {"field": "value"}]
                + [
                    {"field": f}
                    for f in ("n", "source", "known", "note")
                    if any(r.get(f) not in (None, "") for r in long)
                ],
            },
        },
        {
            "data": {"values": items_rows},
            "transform": pick
            + [{"calculate": "datum.hi == null ? 0 : datum.hi", "as": "end"}],
            "mark": {"type": "text", "align": "left", "dx": 9, "color": "#52514e"},
            "encoding": (
                {"x": {"value": width + 12}} if domain else {"x": {"field": "end"} | x}
            )
            | {"y": y, "text": {"field": "text"}},
        },
    ]
    view = {"width": width, "height": max(60, 26 * count), "layer": layers}
    return Chart(
        title,
        view,
        scope,
        tuple(items_rows),
        ("item", *names, "n", "note", "source", "known", *marks.columns()),
        summary,
        marked_line(marks, items_rows, choice),
        choice,
    )


def members[T](
    items: Items[T],
    *,
    title: str,
    scope: Scope,
    label: Callable[[T], object],
    groups: Mapping[str, Callable[[T], Any]],
    missing_text: str = "missing",
    target: Target | None = None,
    column_width: int = 130,
    summary: str | Mapping[Any, str] = "",
    choice: Choice | None = None,
    n: Callable[[T], int | None] | None = None,
    trace: Callable[[T], Any] | None = None,
    flag: Flag[T] | None = None,
    note: Callable[[T], str | None] | None = None,
    detail: Mapping[str, Callable[[T], Any]] | None = None,
    traces: Mapping[str, Callable[[T], Any]] | None = None,
) -> Chart:
    """A grid of items against groups. A cell shows the item's value in that group or
    "missing". Use it to see
    which items are in which groups and where a part is missing.

    Args:
        items: The items. A function of the choice value that gives the items also
            works.
        title: The question the chart answers.
        scope: What the chart covers and leaves out.
        label: The name of an item.
        groups: For each group name, the item's value in that group. A value is missing
            if it is None, False, "" or an empty list.
            A value of 0 is shown as 0.
        missing_text: The text of a missing cell.
        target: A goal for the grid with its status, such as "every task has a
            note". The chart shows it under the title.
        column_width: The width of each column in pixels. Widen it for long cell text.
        summary: A sentence shown above the chart. A dict with 1 sentence for each
            choice value also works.
        choice: An assumption the reader can change. Then `items` is a function of its
            value.
        n: The count behind an item's value. It is shown next to the value.
        trace: The source and known time of an item's value. It is a `Trace`, a World
            API `Origin` or a World API `Entry`.
        flag: A rule that marks some items with ⚑. The subtitle gives the rule and the
            count it marks.
        note: A short note shown next to an item.
        detail: More values for the tooltip and the table view. For example `{"sales":
            lambda p: p.sales}`.
        traces: The traces of an item's other values by name. Each gives "<name> source"
            and "<name> known".

    Returns:
        The chart. A subtitle line counts the items in each group.

    Example:
        ```python
        from types import SimpleNamespace as Task
        from scriptt.charts import Scope, members

        tasks = [Task(id="t1", notes=1), Task(id="t3", notes=0)]
        count_notes = lambda t: t.notes
        members(
            tasks,
            title="Does every task have a note?",
            scope=Scope("6 tasks"),
            label=lambda t: t.id,
            groups={"notes": lambda t: count_notes(t) or None},
        )
        ```
    """
    marks = Marks(n, trace, flag, note, detail or {}, traces or {})
    rows: list[dict[str, Any]] = []
    cells: list[dict[str, Any]] = []
    names = list(groups)
    chosen = each_choice(items, choice)  # items are read once: a generator works
    for picked, group in chosen:
        made = rows_of(group, label, {g: f for g, f in groups.items()}, marks, picked)
        for rank, row in enumerate(made):
            row["rank"] = rank
            for g in names:
                value = row[g]
                present = (
                    value is not None
                    and value is not False
                    and value != []
                    and value != ""
                )  # 0 is a value
                cell = {
                    k: row.get(k)
                    for k in (
                        "item",
                        "label",
                        "rank",
                        "choice",
                        "note",
                        "source",
                        "known",
                    )
                }
                if f"{g} source" in row:  # a column with its own trace
                    cell |= {"source": row[f"{g} source"], "known": row[f"{g} known"]}
                cells.append(
                    cell
                    | {
                        "group": g,
                        "present": present,
                        "text": _cell_text(value) if present else missing_text,
                    }
                )
        rows += made
    counts = {
        g: sum(
            c["present"]
            for c in cells
            if c["group"] == g
            and (choice is None or c["choice"] == plain(choice.default))
        )
        for g in names
    }
    shown = len(
        [r for r in rows if choice is None or r.get("choice") == plain(choice.default)]
    )
    y = {
        "field": "label",
        "type": "nominal",
        "sort": _order(rows, choice),
        "title": None,
    }
    x = {
        "field": "group",
        "type": "nominal",
        "sort": names,
        "title": None,
        "axis": {"orient": "top", "labelAngle": 0, "labelLimit": 160},
    }
    tip = [
        {"field": "item"},
        {"field": "group"},
        {"field": "text", "title": "value"},
    ] + [
        {"field": f}
        for f in ("source", "known", "note")
        if any(c.get(f) not in (None, "") for c in cells)
    ]
    layers = [
        {
            "mark": {
                "type": "rect",
                "stroke": "#fcfcfb",
                "strokeWidth": 2,
                "cornerRadius": 3,
            },
            "encoding": {
                "x": x,
                "y": y,
                "color": {
                    "field": "present",
                    "type": "nominal",
                    "scale": {"domain": [True, False], "range": ["#cde2fb", GREY_CELL]},
                    "legend": None,
                },
                "tooltip": tip,
            },
        },
        {
            "mark": {"type": "text", "fontSize": 11},
            "encoding": {
                "x": x,
                "y": y,
                "text": {"field": "text"},
                "color": {
                    "condition": {"test": "datum.present", "value": "#0b0b0b"},
                    "value": MUTED,
                },
            },
        },
    ]
    count = max(len(g) for _, g in chosen)
    view = filtered(
        {
            "data": {"values": cells},
            "width": max(240, column_width * len(names)),
            "height": max(60, 30 * count),
            "layer": layers,
        },
        choice,
    )
    layers[1]["mark"]["limit"] = (
        column_width - 8
    )  # cell text longer than its column ends with "…"; the tooltip has it all
    line = "Present in each column: " + ", ".join(
        f"{g} {counts[g]} of {shown}" for g in names
    )
    marked = " · ".join(
        x
        for x in (
            marked_line(marks, rows, choice),
            f"Goal: {target.text()}" if target else "",
        )
        if x
    )
    return Chart(
        title,
        view,
        scope,
        tuple(rows),
        ("item", *names, "note", "source", "known", *marks.columns()),
        summary if summary else line,
        marked,
        choice,
    )


def flows[T](
    items: Iterable[T],
    *,
    title: str,
    scope: Scope,
    source: Callable[[T], object],
    target: Callable[[T], object],
    n: Callable[[T], int] = lambda item: 1,
    least: int = 2,
    singles: str | None = None,
    unit: str = "count",
    summary: str = "",
) -> Chart:
    """How many items moved from 1 category to another. Flows below `least` are put
    together in 1 row. A single
    move is then counted but not drawn as a finding.

    Args:
        items: The moves.
        title: The question the chart answers.
        scope: What the chart covers and leaves out.
        source: The category a move starts in.
        target: The category a move ends in.
        n: The count of 1 move (default 1).
        least: The smallest flow drawn on its own row.
        singles: The name of the row that contains the smaller flows. The default says
            the size. For example "flows of 1" or
            "flows under 3".
        unit: The title of the value axis.
        summary: A sentence above the chart.

    Returns:
        A `ranked` chart of the flows. The counts add up to the number of moves.

    Example:
        ```python
        from types import SimpleNamespace as Move
        from scriptt.charts import Scope, flows

        moves = [
            Move(before="home", after="work"),
            Move(before="work", after="home"),
        ]
        flows(
            moves,
            title="Where do tasks move?",
            scope=Scope("2 to 4 Nov 2026"),
            source=lambda m: m.before,
            target=lambda m: m.after,
        )
        ```
    """
    totals: dict[tuple[str, str], int] = {}
    for item in items:
        key = (figures(source(item)), figures(target(item)))
        totals[key] = totals.get(key, 0) + n(item)
    big = [
        (f"{a} → {b}", count, 1) for (a, b), count in totals.items() if count >= least
    ]
    small = [count for count in totals.values() if count < least]
    if small:
        name = singles or ("flows of 1" if least == 2 else f"flows under {least}")
        big.append((f"{name} ({len(small)} flows)", sum(small), len(small)))
    return ranked(
        big,
        title=title,
        scope=scope,
        label=lambda f: f[0],
        value=lambda f: f[1],
        unit=unit,
        summary=summary,
        detail={"flows": lambda f: f[2]},
    )


def _target_layers(target: Target | None, *, axis: str) -> list[dict[str, Any]]:
    if target is None:
        return []
    other = "y" if axis == "x" else "x"
    kind = "temporal" if isinstance(target.value, dt.date) else "quantitative"
    datum = {"datum": plain(target.value), "type": kind}
    text_pos = (
        {other: {"value": -6}} if axis == "x" else {other: {"value": 4}}
    )  # above the plot, clear of the bar labels
    return [
        {
            "mark": {
                "type": "rule",
                "color": "#d03b3b",
                "strokeDash": [6, 4],
                "strokeWidth": 1.5,
            },
            "encoding": {axis: datum},
        },
        {
            "mark": {
                "type": "text",
                "align": "left",
                "baseline": "bottom",
                "dx": 4,
                "dy": -2,
                "color": "#d03b3b",
                "fontWeight": 600,
            },
            "encoding": {axis: datum, **text_pos, "text": {"value": target.text()}},
        },
    ]


def _gap(days: int) -> str:
    return (
        "same day" if days == 0 else f"{days} day" if abs(days) == 1 else f"{days} days"
    )


def _percent(value: float) -> str:
    return "<1%" if 0 < value < 1 else f"{value:.0f}%"


def _shared_text(row: dict[str, Any]) -> list[str]:
    return ([f"n={row['n']}"] if row.get("n") is not None else []) + (
        [row["note"]] if row.get("note") else []
    )


def _cell_text(value: Any) -> str:
    match value:
        case True:
            return "yes"
        case list() | tuple():
            return ", ".join(figures(v) for v in value)
    return figures(value)


def _days(a: Any, b: Any) -> int | None:
    if isinstance(a, dt.date) and isinstance(b, dt.date):
        a = a.date() if isinstance(a, dt.datetime) else a
        b = b.date() if isinstance(b, dt.datetime) else b
        return (b - a).days
    return None
