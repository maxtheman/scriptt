"""`Chart` is 1 chart as data. It renders to:

- a Vega-Lite spec (no dependency)
- an Altair chart (with the extra `altair`)
- a standalone HTML page
- a plain table of its rows
"""

import datetime as dt
import html
import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from ._parts import Choice, Flag, Scope, Trace, figures, plain

SCHEMA = "https://vega.github.io/schema/vega-lite/v5.json"

# The reference palette (light surface): categorical slots in fixed order, and text
# inks. A flag never uses a colour:
# it puts a mark on the item's label, so it reads in any colour vision and in print.
SERIES = (
    "#2a78d6",
    "#eb6834",
    "#1baf7a",
    "#eda100",
    "#e87ba4",
    "#008300",
    "#6250d6",
    "#e34948",
)
SURFACE, INK, INK_2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8984", "#e8e7e3"
FLAG_MARK = "⚑"
RESERVED = {
    "item",
    "label",
    "flagged",
    "n",
    "note",
    "source",
    "known",
    "rank",
    "text",
    "choice",
    "end",
    "lo",
    "hi",
    "series",
    "group",
    "present",
    "part",
}  # field names of a chart row; a value name must not be one of these

CONFIG: dict[str, Any] = {
    "background": SURFACE,
    "font": "Inter, system-ui, -apple-system, sans-serif",
    "view": {"stroke": None},
    "padding": {"left": 4, "right": 16, "top": 8, "bottom": 8},
    "axis": {
        "labelColor": INK_2,
        "titleColor": INK_2,
        "gridColor": GRID,
        "domainColor": "#c3c2b7",
        "tickColor": "#c3c2b7",
        "labelFontSize": 11,
        "titleFontSize": 11,
        "titleFontWeight": "normal",
        "labelLimit": 340,
    },
    "legend": {
        "labelColor": INK_2,
        "titleColor": INK_2,
        "orient": "top",
        "labelFontSize": 11,
        "symbolSize": 80,
        "labelLimit": 360,
    },
    "title": {
        "anchor": "start",
        "fontSize": 15,
        "fontWeight": 600,
        "color": INK,
        "subtitleColor": INK_2,
        "subtitleFontSize": 12,
        "subtitlePadding": 6,
        "offset": 14,
    },
    "range": {"category": list(SERIES)},
    "text": {"color": INK_2, "fontSize": 11},
}


@dataclass(frozen=True, slots=True)
class Chart:
    """1 chart. It has a title and a Vega-Lite view. It also has a scope and the rows
    that it draws. Make it with a
    form such as `ranked` or `flows`. Do not build it by hand.

    Attributes:
        title: The question the chart answers.
        view: The Vega-Lite view. It has no title, config or parameters.
        scope: What the chart covers and leaves out.
        rows: The rows the chart draws (for the table view). Each row is a dict of plain
            values.
        columns: The columns of the table view in order.
        summary: A sentence shown above the chart, or 1 sentence for each value of the
            choice.
        marked: The line that explains the flag mark, or "".
        choice: The assumption the reader can change, or None.
    """

    title: str
    view: dict[str, Any]
    scope: Scope
    rows: tuple[dict[str, Any], ...] = ()
    columns: tuple[str, ...] = ()
    summary: str | Mapping[Any, str] = ""
    marked: str = ""
    choice: Choice | None = None
    width: int = 560

    def __post_init__(self) -> None:
        if not isinstance(self.summary, str) and self.choice is None:
            raise TypeError(
                "a summary for each choice value needs choice=Choice(...); give 1 "
                "sentence otherwise"
            )

    def vega_lite(self) -> dict[str, Any]:
        """The full Vega-Lite spec. It has a schema and a theme. It also has the title
        with the scope, the control of the choice and the view."""
        lines = [self.summary] if isinstance(self.summary, str) and self.summary else []
        lines += [self.scope.text()] + ([self.marked] if self.marked else [])
        spec: dict[str, Any] = {
            "$schema": SCHEMA,
            "config": CONFIG,
            "title": {"text": self.title, "subtitle": _wrap(lines)},
        }
        if self.choice is None:
            return spec | self.view
        spec["params"] = [self.choice.control()]
        top = (
            []
            if isinstance(self.summary, str)
            else [_said(self.summary, self.choice, self.width)]
        )
        return spec | {"vconcat": top + [self.view], "spacing": 6}

    def resized(self, width: int | None = None, height: int | None = None) -> Chart:
        """A copy of the chart with a new width or height in pixels (the plot area
        without the labels).

        Args:
            width: The new width. None keeps the width. For `side_by_side` this is the
                width of each chart.
            height: The new height. None keeps the height.

        Returns:
            The new chart. The chart itself does not change.
        """
        size = ({"width": width} if width else {}) | (
            {"height": height} if height else {}
        )
        view = self.view | (
            {"hconcat": [v | size for v in self.view["hconcat"]]}
            if "hconcat" in self.view
            else size
        )
        return replace(self, view=view, width=width or self.width)

    def json(self) -> str:
        """The Vega-Lite spec as JSON text for a page or a file."""
        return json.dumps(self.vega_lite(), ensure_ascii=False, default=str)

    def altair(self) -> Any:
        """An Altair chart of the same spec (needs `scriptt-charts[altair]`)."""
        # the optional extra scriptt-charts[altair]
        import altair as alt  # pyright: ignore[reportMissingImports]

        spec = self.vega_lite()
        kind = next((k for k in ("vconcat", "hconcat", "layer") if k in spec), "")
        return {
            "vconcat": alt.VConcatChart,
            "hconcat": alt.HConcatChart,
            "layer": alt.LayerChart,
        }.get(kind, alt.Chart).from_dict(spec)

    def html(self) -> str:
        """A standalone HTML page that draws the chart with vega-embed from a CDN."""
        spec = self.json().replace(
            "<", "\\u003c"
        )  # no text in the data can close the script
        return (
            "<!doctype html><meta charset='utf-8'><title>"
            + html.escape(self.title)
            + "</title><div id='chart'></div>"
            "<script src='https://cdn.jsdelivr.net/npm/vega@5.30.0'></script>"
            "<script src='https://cdn.jsdelivr.net/npm/vega-lite@5.21.0'></script>"
            "<script src='https://cdn.jsdelivr.net/npm/vega-embed@6.26.0'></script>"
            f"<script>vegaEmbed('#chart', {spec}, {{actions: false}});</script>"
        )

    def table(self) -> str:
        """The chart as plain text for a reader who cannot see it. The text gives the
        title and the summary. It gives the
        scope and the flag rule with its count. It gives the target with its status and
        the assumption. The rows follow.
        ⚑ in the first column marks a flagged row. With a choice, the rows are those of
        its default value."""
        rows = [
            r
            for r in self.rows
            if self.choice is None or r.get("choice") == plain(self.choice.default)
        ]
        columns = (["flag"] if any(r.get("flagged") for r in rows) else []) + [
            c for c in self.columns if any(r.get(c) not in (None, "") for r in rows)
        ]
        cells = [
            [
                FLAG_MARK
                if c == "flag" and r.get("flagged")
                else ""
                if c == "flag"
                else _cell(r.get(c))
                for c in columns
            ]
            for r in rows
        ]
        width = [
            max([len(c)] + [len(row[i]) for row in cells])
            for i, c in enumerate(columns)
        ]
        said = (
            self.summary
            if isinstance(self.summary, str)
            else self.summary.get(self.choice.default if self.choice else None, "")
        )
        head = [self.title, said, self.scope.text(), self.marked]
        head += (
            [f"{self.choice.label} (assumption): {figures(self.choice.default)}"]
            if self.choice
            else []
        )
        lines = [h for h in head if h] + [""]
        lines += ["  ".join(c.ljust(w) for c, w in zip(columns, width))]
        lines += [
            "  ".join(v.ljust(w) for v, w in zip(row, width)).rstrip() for row in cells
        ]
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.table()


def side_by_side(title: str, *charts: Chart, summary: str = "") -> Chart:
    """2 or more charts of the same items next to each other. Each chart has its own
    value axis. Use it for 2 measures
    of different units (pay and people). Never use 2 scales on 1 axis.

    Args:
        title: The question the charts answer together.
        *charts: The charts. The scope of the first chart is the scope of all charts.
            The charts may share 1 assumption
            (`Choice`). 2 different assumptions are an error.
        summary: A sentence shown above the charts.

    Returns:
        1 chart that contains the others.
    """
    choices = {c.choice.name: c.choice for c in charts if c.choice is not None}
    if len(choices) > 1:
        raise ValueError(
            f"side_by_side takes charts with 1 choice at most; these have "
            f"{', '.join(choices)}"
        )
    views = [
        c.view
        | {
            "title": {
                "text": c.title,
                "fontSize": 12,
                "fontWeight": 600,
                "color": INK_2,
                "anchor": "start",
            }
        }
        for c in charts
    ]
    marked = " · ".join(dict.fromkeys(c.marked for c in charts if c.marked))
    return Chart(
        title,
        {"hconcat": views, "spacing": 24},
        charts[0].scope,
        sum((c.rows for c in charts), ()),
        tuple(dict.fromkeys(col for c in charts for col in c.columns)),
        summary,
        marked,
        next(iter(choices.values()), None),
    )


# ---- rows: what every form shares
# ----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Marks[T]:
    """The options that every form takes for each item. The attributes below list them.

    Attributes:
        n: The number of things behind the item's value, or None. The chart shows it.
        trace: The source and known time of the item's value. It is a `Trace`, an
            `Origin` or an `Entry`. None means no trace.
        flag: A rule that marks some items, or None.
        note: A short note shown next to the item, or None.
        detail: More values shown in the tooltip and the table view. For example
            `{"sales": lambda p: p.sales}`.
        traces: The traces of the other values of an item, by name. For example
            `{"title": lambda r: view.origin(r.task, lambda t: t.title)}` gives
            the fields "title source" and "title known". In `members` a name is a
            column and each cell takes its trace.
    """

    n: Callable[[T], int | None] | None = None
    trace: Callable[[T], Any] | None = None
    flag: Flag[T] | None = None
    note: Callable[[T], str | None] | None = None
    detail: Mapping[str, Callable[[T], Any]] = field(default_factory=dict)
    traces: Mapping[str, Callable[[T], Any]] = field(default_factory=dict)

    def columns(self) -> tuple[str, ...]:
        """The table columns of the details and the other traces."""
        return (
            *self.detail,
            *(f"{name} {part}" for name in self.traces for part in ("source", "known")),
        )


def rows_of[T](
    items: Iterable[T],
    label: Callable[[T], object],
    values: Mapping[str, Callable[[T], Any]],
    marks: Marks[T],
    choice: Any = None,
    computed: frozenset[str] = frozenset(),
) -> list[dict[str, Any]]:
    """1 row for each item. The row has its label (with the flag mark), its values and
    the shared fields."""
    clash = (set(values) & RESERVED) | (
        set(marks.detail) & (RESERVED | set(values) | computed)
    )  # `computed`: what the form adds
    if clash:
        raise ValueError(
            f"these names are used by the chart itself: {', '.join(sorted(clash))}; "
            f"rename the view, group, series or detail"
        )
    out, seen = [], dict[str, int]()
    for item in items:
        flagged = bool(marks.flag and marks.flag.test(item))
        trace = Trace.of(marks.trace(item)) if marks.trace else None
        name = figures(label(item))
        seen[name] = seen.get(name, 0) + 1
        name = (
            name if seen[name] == 1 else f"{name} ({seen[name]})"
        )  # 2 items with 1 name get 2 rows
        row = {
            "item": name,
            "label": f"{FLAG_MARK} {name}" if flagged else name,
            "flagged": flagged,
        }
        row |= {k: plain(f(item)) for k, f in values.items()}
        row |= {
            "n": marks.n(item) if marks.n else None,
            "note": (marks.note(item) if marks.note else None) or "",
            "source": trace.source if trace else None,
            "known": figures(trace.known) if trace and trace.known else None,
        }
        row |= {k: plain(f(item)) for k, f in marks.detail.items()}
        for key, read in marks.traces.items():
            other = Trace.of(read(item))
            row |= {
                f"{key} source": other.source if other else None,
                f"{key} known": figures(other.known) if other and other.known else None,
            }
        row["_thing"] = (
            figures(marks.flag.per(item)) if marks.flag and marks.flag.per else name
        )
        if choice is not None:
            row["choice"] = plain(choice)
        out.append(row)
    return out


def order(rows: Sequence[dict[str, Any]], choice: Choice | None) -> list[str]:
    """The labels in the order of their rank. Those of the default choice come first and
    any others follow. A sort by
    a field is lost when the layers have different data, so Vega-Lite sorts a layered
    axis by this list."""
    first = [
        r for r in rows if choice is None or r.get("choice") == plain(choice.default)
    ]
    ranked = sorted(first, key=lambda r: r.get("rank", 0)) + sorted(
        (r for r in rows if r not in first), key=lambda r: r.get("rank", 0)
    )
    return list(dict.fromkeys(r["label"] for r in ranked))


def marked_line[T](
    marks: Marks[T], rows: Sequence[dict[str, Any]], choice: Choice | None
) -> str:
    """The subtitle line that explains the flag mark and gives the count that it "
    "marks."""
    if marks.flag is None:
        return ""
    shown = [
        r for r in rows if choice is None or r.get("choice") == plain(choice.default)
    ]
    things = {r["_thing"] for r in shown}
    flagged = {r["_thing"] for r in shown if r["flagged"]}
    return f"{FLAG_MARK} marks {marks.flag.rule} ({len(flagged)} of {len(things)})"


def tooltip(rows: Sequence[dict[str, Any]], *fields: str) -> list[dict[str, Any]]:
    """The tooltip. It shows the item and the given fields. It shows the shared fields
    that have a value in some row."""
    shared = [
        f
        for f in ("n", "source", "known", "note")
        if any(r.get(f) not in (None, "") for r in rows)
    ]
    extra = [
        k
        for k in (rows[0] if rows else {})
        if k
        not in {
            "item",
            "label",
            "flagged",
            "choice",
            "rank",
            "text",
            "n",
            "source",
            "known",
            "note",
            "end",
            "lo",
            "hi",
            "missing",
            *fields,
        }
        and not k.startswith("_")
    ]
    return [{"field": "item", "title": "item"}] + [
        {"field": f} for f in [*fields, *extra, *shared]
    ]


def each_choice[T](
    items: Iterable[T] | Callable[[Any], Iterable[T]], choice: Choice | None
) -> list[tuple[Any, list[T]]]:
    """The items for each value of the choice. Without a choice there is 1 group with
    the value None."""
    if choice is None:
        if callable(items):
            raise TypeError("items is a function of a choice: give choice=Choice(...)")
        return [(None, list(items))]
    if not callable(items):
        raise TypeError(
            "with a choice, give items as a function of the choice value: lambda fee: "
            "..."
        )
    return [(value, list(items(value))) for value in choice.values]


def filtered(view: dict[str, Any], choice: Choice | None) -> dict[str, Any]:
    """The view with only the rows of the picked choice value."""
    if choice is None:
        return view
    return view | {
        "transform": [{"filter": f"datum.choice == {choice.name}"}]
        + view.get("transform", [])
    }


def _said(summary: Mapping[Any, str], choice: Choice, width: int) -> dict[str, Any]:
    rows = [
        {"choice": plain(v), "text": "\n".join(_wrap([t], width // 7))}
        for v, t in summary.items()
    ]
    lines = max((r["text"].count("\n") + 1 for r in rows), default=1)
    return {
        "data": {"values": rows},
        "transform": [{"filter": f"datum.choice == {choice.name}"}],
        "width": width,
        "height": 17 * lines,
        "mark": {
            "type": "text",
            "align": "left",
            "baseline": "top",
            "fontSize": 13,
            "color": INK,
            "lineBreak": "\n",
            "lineHeight": 17,
        },
        "encoding": {"text": {"field": "text"}, "x": {"value": 0}, "y": {"value": 0}},
    }


def _wrap(lines: list[str], width: int = 100) -> list[str]:
    out = []
    for line in lines:
        words, current = line.split(), ""
        for word in words:
            if current and len(current) + len(word) + 1 > width:
                out.append(current)
                current = word
            else:
                current = f"{current} {word}".strip()
        out.append(current)
    return out


def _cell(value: Any) -> str:
    if isinstance(value, float):
        return figures(value)
    if (
        isinstance(value, str)
        and len(value) >= 10
        and value[4] == "-"
        and value[7] == "-"
    ):  # an ISO date in the data
        try:
            when = dt.datetime.fromisoformat(value)
            return figures(when if when.time() != dt.time() else when.date())
        except ValueError:
            return value
    return "" if value is None else str(value)
