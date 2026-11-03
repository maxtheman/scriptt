"""Forms for the shape of the data and not only its values. `tree` shows things under
things with totals. `graph` shows
things and the typed links between them. `timeline` shows when each version of a thing
was true and when it was known."""

import datetime as dt
import math
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from ._chart import SERIES, Chart, Marks, marked_line, rows_of, tooltip
from ._parts import Flag, Scope, figures, plain

INDENT = "·  "  # a visible mark for each level: a renderer may drop leading spaces
MUTED, EDGE, UP, DOWN = "#8a8984", "#b4b2a9", SERIES[0], SERIES[1]


def tree[T](
    items: Iterable[T],
    *,
    title: str,
    scope: Scope,
    label: Callable[[T], object],
    parent: Callable[[T], object | None],
    value: Callable[[T], float | None] | None = None,
    root: str | None = None,
    rollup: bool = True,
    unit: str = "",
    show: Callable[[float], str] = figures,
    summary: str = "",
    n: Callable[[T], int | None] | None = None,
    trace: Callable[[T], Any] | None = None,
    flag: Flag[T] | None = None,
    note: Callable[[T], str | None] | None = None,
    detail: Mapping[str, Callable[[T], Any]] | None = None,
    traces: Mapping[str, Callable[[T], Any]] | None = None,
) -> Chart:
    """Things under things, each with the total of everything under it. Read it from the
    top down. A child is indented
    under its parent. Its bar is its own value plus the values under it.

    The chart adds a parent that is not one of the items (a list that contains tasks).
    That parent has no value of its own.

    Args:
        items: The things.
        title: The question the chart answers.
        scope: What the chart covers and leaves out.
        label: The name of a thing. Names must be unique. A name that repeats is an
            error. A loop is also an error.
        parent: The name of the thing directly above it, or None for a top thing.
        value: The value of a thing (minutes of work). The default counts each thing
            as 1. Then a bar is the count under it.
        root: The name of 1 top thing that contains every thing with no parent ("all
            tasks"). None draws no root.
        rollup: True means a bar is the thing's value plus the values under it (minutes
            of a list). False means a bar is the thing's
            own value (the minutes of 1 task). Then only a root shows a total.
        unit: The title of the value axis.
        show: How a total is written in its label.
        summary: A sentence shown above the chart.
        n: The count behind an item's value. It is shown next to the value.
        trace: The source and known time of an item's value. It is a `Trace`, a World
            API `Origin` or a World API `Entry`.
        flag: A rule that marks some items with ⚑. The subtitle gives the rule and the
            count it marks.
        note: A short note shown next to an item.
        detail: More values for the tooltip and the table view.
        traces: The traces of an item's other values, by name.

    Returns:
        The chart. Its table lists each thing with its depth, own value and total.

    Example:
        ```python
        from types import SimpleNamespace as Task
        from scriptt.charts import Scope, tree

        items = [
            Task(title="Buy milk", list="home", minutes=15),
            Task(title="Send the report", list="work", minutes=45),
        ]
        tree(
            items,
            title="Where does the time go?",
            scope=Scope("the to-do list of 4 Nov 2026"),
            label=lambda i: i.title,
            parent=lambda i: i.list,
            value=lambda i: i.minutes,
        )
        ```
    """
    marks = Marks(n, trace, flag, note, detail or {}, traces or {})
    items = list(items)
    names = [figures(label(i)) for i in items]
    if len(set(names)) != len(names):
        raise ValueError(
            f"tree needs 1 name for each thing; these repeat: "
            f"{', '.join(sorted({x for x in names if names.count(x) > 1}))}"
        )
    if root is not None and root in names:
        raise ValueError(
            f"the root {root!r} is also an item; give the root another name, or leave "
            f"root out"
        )
    own = {figures(label(i)): (value(i) if value else 1) for i in items}
    up = {
        figures(label(i)): (figures(p) if (p := parent(i)) is not None else None)
        for i in items
    }
    for p in [p for p in up.values() if p is not None and p not in up]:
        up[p], own[p] = None, None  # a parent that is not an item
    if root is not None:
        up = {k: (root if v is None and k != root else v) for k, v in up.items()} | {
            root: None
        }
        own.setdefault(root, None)
    down: dict[str | None, list[str]] = {}
    for child, p in up.items():
        down.setdefault(p, []).append(child)
    totals: dict[str, float] = {}
    depth_of: dict[str, int] = {}
    for name in up:  # each depth once, from the parent's depth
        chain = []
        node: str | None = name
        while node is not None and node not in depth_of:
            if (
                node in chain
            ):  # a thing under itself, through its parents, cannot be drawn
                raise ValueError(
                    f"tree has a loop: "
                    f"{' → '.join(chain[chain.index(node) :] + [node])}"
                )
            chain.append(node)
            node = up.get(node)
        base = depth_of[node] if node is not None else -1
        for k, item in enumerate(reversed(chain)):
            depth_of[item] = base + 1 + k
    for name in sorted(
        up, key=lambda x: -depth_of[x]
    ):  # deepest first, so each total is ready for its parent
        totals[name] = (own[name] or 0) + sum(totals[c] for c in down.get(name, []))
    if not rollup:  # each bar is its own value; the root keeps the total of everything
        totals = {
            name: (totals[name] if name == root else (own[name] or 0))
            for name in totals
        }

    def total(name: str) -> float:
        return totals[name]

    order: list[tuple[str, int]] = []

    stack = [
        (top, 0) for top in sorted(down.get(None, []), key=lambda c: total(c))
    ]  # the largest is popped first
    while stack:
        name, depth = stack.pop()
        order.append((name, depth))
        stack += [
            (c, depth + 1) for c in sorted(down.get(name, []), key=lambda c: total(c))
        ]
    made = {
        r["item"]: r
        for r in rows_of(
            items,
            label,
            {},
            marks,
            computed=frozenset({"depth", "own", "total", "under"}),
        )
    }
    rows = []
    for rank, (name, depth) in enumerate(order):
        row = made.get(name) or {
            "item": name,
            "label": name,
            "flagged": False,
            "n": None,
            "note": "",
            "source": None,
            "known": None,
            "_thing": name,
        }
        under = len(down.get(name, []))
        row |= {
            "rank": rank,
            "depth": depth,
            "own": own[name],
            "total": total(name),
            "under": under,
            "label": INDENT * max(depth - 1, 0)
            + ("└ " if depth else "")
            + row["label"],
        }
        empty = (
            own[name] is None
            and value is not None
            and (not under or not rollup)
            and name != root
        )  # no value of its own: not drawn as 0
        bits = (
            ["no value" if empty else show(row["total"])]
            + ([f"{under} directly under it"] if under else [])
            + _shared(row)
        )
        row["text"] = " · ".join(bits)
        rows.append(row)
    top = max((r["total"] for r in rows), default=1) or 1
    y = {
        "field": "label",
        "type": "nominal",
        "sort": [r["label"] for r in rows],
        "title": None,
        "axis": {"labels": False, "ticks": False},
    }
    x = {
        "field": "total",
        "type": "quantitative",
        "title": unit or None,
        "scale": {"domain": [0, top * 1.8]},
    }
    layers = [
        {
            "mark": {
                "type": "text",
                "align": "left",
                "color": "#0b0b0b",
                "limit": 240,
            },  # the names, indented: an axis would align them right
            "encoding": {"x": {"value": -250}, "y": y, "text": {"field": "label"}},
        },
        {
            "mark": {"type": "bar", "cornerRadiusEnd": 4, "height": {"band": 0.66}},
            "encoding": {
                "x": x,
                "y": y,
                "color": {
                    "condition": {"test": "datum.depth == 0", "value": SERIES[0]},
                    "value": "#86b6ef",
                },
                "tooltip": tooltip(rows, "total", "own", "depth", "under"),
            },
        },
        {
            "mark": {"type": "text", "align": "left", "dx": 5, "color": "#52514e"},
            "encoding": {"x": x, "y": y, "text": {"field": "text"}},
        },
    ]
    view = {
        "data": {"values": rows},
        "width": 500,
        "height": max(60, 22 * len(rows)),
        "layer": layers,
    }
    return Chart(
        title,
        view,
        scope,
        tuple(rows),
        (
            "item",
            "depth",
            "own",
            "total",
            "under",
            "n",
            "note",
            "source",
            "known",
            *marks.columns(),
        ),
        summary,
        marked_line(marks, [r for r in rows if "_thing" in r], None),
    )


def graph[T](
    edges: Iterable[T],
    *,
    title: str,
    scope: Scope,
    source: Callable[[T], object],
    target: Callable[[T], object],
    label: Callable[[T], str | None] | None = None,
    weight: Callable[[T], float | None] | None = None,
    sign: Callable[[T], int] | None = None,
    kind: Callable[[str], str] | None = None,
    summary: str = "",
    n: Callable[[T], int | None] | None = None,
    trace: Callable[[T], Any] | None = None,
    flag: Flag[T] | None = None,
    note: Callable[[T], str | None] | None = None,
    detail: Mapping[str, Callable[[T], Any]] | None = None,
    traces: Mapping[str, Callable[[T], Any]] | None = None,
) -> Chart:
    """Things and the typed links between them, as nodes and arrows. The layout reads
    left to right. A thing stands
    to the right of the things that link to it. A chain of steps then reads in order.

    Args:
        edges: The links. Each gives its 2 ends.
        title: The question the chart answers.
        scope: What the chart covers and leaves out.
        source: The thing a link starts at.
        target: The thing a link ends at.
        label: The kind of link, written at its middle. For example "raises", "triggers"
            or "scored with".
        weight: The strength of a link (a confidence or a count of people). The chart
            scales the line width to the strongest link.
        sign: +1 or -1 for a link that raises or lowers. The 2 signs get 2 colours and a
            legend.
        kind: The kind of a thing, from its name. For example "task" or "note".
            Each kind gets a colour and a legend.
        summary: A sentence shown above the chart.
        n: The count behind a link. It is shown in its tooltip.
        trace: The source and known time of a link. It is a `Trace`, a World API
            `Origin` or a World API `Entry`.
        flag: A rule that marks some links with ⚑ at their middle. The subtitle gives
            the rule and the count.
        note: A short note on a link, in its tooltip.
        detail: More values for the tooltip and the table view.
        traces: The traces of a link's other values, by name.

    Returns:
        The chart. Its table lists each link with the columns from, to, kind and weight.

    Example:
        ```python
        from types import SimpleNamespace as Link
        from scriptt.charts import Scope, graph

        links = [Link(before="Book the room", after="Send the report", sign=1, size=2)]
        graph(
            links,
            title="Which task waits for which?",
            scope=Scope("6 tasks"),
            source=lambda k: k.before,
            target=lambda k: k.after,
            label=lambda k: "unlocks" if k.sign > 0 else "blocks",
            weight=lambda k: k.size,
            sign=lambda k: k.sign,
        )
        ```
    """
    marks = Marks(n, trace, flag, note, detail or {}, traces or {})
    edges = list(edges)
    ends = [(figures(source(e)), figures(target(e))) for e in edges]
    nodes = list(dict.fromkeys(x for pair in ends for x in pair))
    place = _layers(nodes, ends)
    rows = rows_of(
        edges,
        lambda e: f"{figures(source(e))} → {figures(target(e))}",
        {
            "kind of link": label or (lambda e: None),
            "weight": weight or (lambda e: None),
            "sign": sign or (lambda e: 1),
        },
        marks,
        computed=frozenset(
            {
                "from",
                "to",
                "x",
                "y",
                "x2",
                "y2",
                "width",
                "dir",
                "mid",
                "angle",
                "mx",
                "my",
            }
        ),
    )
    heaviest = (
        max((abs(r["weight"]) for r in rows if r["weight"] is not None), default=0) or 1
    )
    for (a, b), row in zip(ends, rows):
        (x, y), (x2, y2) = place[a], place[b]
        row |= {
            "from": a,
            "to": b,
            "x": x,
            "y": y,
            "x2": x2,
            "y2": y2,
            "mx": (x + x2) / 2,
            "my": (y + y2) / 2,
            "width": 1.5 + 4 * abs(row["weight"] or 0.1 * heaviest) / heaviest,
            "dir": "raises" if (row["sign"] or 1) > 0 else "lowers",
            "mid": ("⚑ " if row["flagged"] else "") + (row["kind of link"] or ""),
        }
    node_rows = [
        {
            "node": name,
            "x": place[name][0],
            "y": place[name][1],
            "kind": kind(name) if kind else "thing",
        }
        for name in nodes
    ]
    kinds = list(dict.fromkeys(r["kind"] for r in node_rows))
    signed = sign is not None
    hide = {"axis": None, "scale": {"padding": 30}}
    x, y = (
        {"type": "quantitative"} | hide,
        {
            "type": "quantitative",
            "scale": {"reverse": True, "padding": 30},
            "axis": None,
        },
    )
    edge_colour = (
        {
            "field": "dir",
            "type": "nominal",
            "scale": {"domain": ["raises", "lowers"], "range": [UP, DOWN]},
            "legend": {"title": None},
        }
        if signed
        else {"value": EDGE}
    )
    layers = [
        {
            "data": {"values": rows},
            "mark": {"type": "rule", "opacity": 0.85},
            "encoding": {
                "x": {"field": "x"} | x,
                "y": {"field": "y"} | y,
                "x2": {"field": "x2"},
                "y2": {"field": "y2"},
                "strokeWidth": {
                    "field": "width",
                    "type": "quantitative",
                    "scale": None,
                },
                "color": edge_colour,
                "tooltip": [{"field": "from"}, {"field": "to"}]
                + tooltip(rows, "kind of link", "weight")[1:],
            },
        },
        {
            "data": {"values": rows},
            "transform": [
                {"calculate": "datum.x2 - (datum.x2 - datum.x) * 0.12", "as": "ax"},
                {"calculate": "datum.y2 - (datum.y2 - datum.y) * 0.12", "as": "ay"},
            ],
            "mark": {
                "type": "point",
                "shape": "triangle-right",
                "filled": True,
                "size": 70,
                "color": "#52514e",
            },
            "encoding": {
                "x": {"field": "ax"} | x,
                "y": {"field": "ay"} | y,
                "angle": {"field": "angle", "type": "quantitative", "scale": None},
            },
        },
        {
            "data": {"values": rows},
            "transform": [{"filter": "datum.mid != ''"}],
            "mark": {"type": "text", "fontSize": 10, "color": "#52514e", "dy": -10},
            "encoding": {
                "x": {"field": "mx"} | x,
                "y": {"field": "my"} | y,
                "text": {"field": "mid"},
            },
        },
        {
            "data": {"values": node_rows},
            "mark": {
                "type": "point",
                "filled": True,
                "size": 260,
                "stroke": "#fcfcfb",
                "strokeWidth": 2,
            },
            "encoding": {
                "x": {"field": "x"} | x,
                "y": {"field": "y"} | y,
                "color": {
                    "field": "kind",
                    "type": "nominal",
                    "scale": {
                        "domain": kinds,
                        "range": list(SERIES[2 : 2 + len(kinds)]) or [SERIES[2]],
                    },  # not the link colours
                    "legend": {"title": None} if kind else None,
                },
                "tooltip": [{"field": "node"}, {"field": "kind"}],
            },
        },
        {
            "data": {"values": node_rows},
            "mark": {
                "type": "text",
                "align": "center",
                "dy": -15,
                "fontSize": 11,
                "color": "#0b0b0b",
                "limit": 180,
            },
            "encoding": {
                "x": {"field": "x"} | x,
                "y": {"field": "y"} | y,
                "text": {"field": "node"},
            },
        },
    ]
    columns = max(int(p[0]) for p in place.values()) + 1 if place else 1
    rows_per = max(
        (sum(1 for p in place.values() if int(p[0]) == c) for c in range(columns)),
        default=1,
    )
    width, height = max(320, 220 * columns), max(120, 56 * rows_per)
    x_px, y_px = (
        width / max(columns - 1, 1),
        height / max(rows_per - 1, 1),
    )  # pixels for 1 step of each axis
    # the arrow head points along the link as drawn, so the angle uses pixels, not data
    # units
    for row in rows:
        row["angle"] = math.degrees(
            math.atan2((row["y2"] - row["y"]) * y_px, (row["x2"] - row["x"]) * x_px)
        )
    view = {
        "width": width,
        "height": height,
        "layer": layers,
        "resolve": {
            "scale": {"color": "independent"},
            "legend": {"color": "independent"},
        },
    }  # link colours and node colours are 2 scales
    return Chart(
        title,
        view,
        scope,
        tuple(rows),
        (
            "from",
            "to",
            "kind of link",
            "weight",
            "note",
            "n",
            "source",
            "known",
            *marks.columns(),
        ),
        summary,
        marked_line(marks, rows, None),
    )


def timeline[T](
    items: Iterable[T],
    *,
    title: str,
    scope: Scope,
    lane: Callable[[T], object],
    start: Callable[[T], dt.date | None],
    end: Callable[[T], dt.date | None],
    known: Callable[[T], dt.date | dt.datetime | None] | None = None,
    label: Callable[[T], object] | None = None,
    thing: Callable[[T], object] | None = None,
    until: dt.date | None = None,
    summary: str = "",
    n: Callable[[T], int | None] | None = None,
    trace: Callable[[T], Any] | None = None,
    flag: Flag[T] | None = None,
    note: Callable[[T], str | None] | None = None,
    detail: Mapping[str, Callable[[T], Any]] | None = None,
    traces: Mapping[str, Callable[[T], Any]] | None = None,
) -> Chart:
    """When each version of a thing was true. The chart draws bars in 1 lane for each
    thing. A mark shows where each version
    became known. A version known after it started shows the gap. The mark sits to the
    right of the bar's start.

    Args:
        items: The versions. For a World API fact these are the entries of
            `view.history(fact)`. An `end` entry stops the
            version before it and the chart does not draw it. A `retract` entry marks
            the thing's versions "retracted later".
        title: The question the chart answers.
        scope: What the chart covers and leaves out.
        lane: The thing a version belongs to. Each thing has 1 lane.
        start: The first day the version is true. None means before the chart starts.
        end: The day it stops. None means it stops where the next version of the same
            thing starts, or it is still true and
            the bar runs to `until`.
        thing: What a version is a version of (a role and not the person who has it).
            The default is the entry's
            identity for World API entries. For other versions it is the lane. 2 things
            in 1 lane can both be true at once.
        known: The time the version became known (a diamond).
        label: The text on the bar (the value of the version).
        until: The last day on the chart. The default is the latest date in the data.
        summary: A sentence shown above the chart.
        n: The count behind a version. It is shown in its tooltip.
        trace: The source and known time of a version. It is a `Trace`, a World API
            `Origin` or a World API `Entry`.
        flag: A rule that marks some versions with ⚑. The subtitle gives the rule and
            the count.
        note: A short note on a version, after its label.
        detail: More values for the tooltip and the table view.
        traces: The traces of a version's other values, by name.

    Returns:
        The chart. Its table lists each version with the columns lane, start, end and
        known.

    Example:
        ```python
        import datetime as dt
        from types import SimpleNamespace as Entry
        from scriptt.charts import Scope, timeline

        t1 = [
            Entry(
                true_from=dt.date(2026, 11, 2),
                true_until=dt.date(2026, 11, 3),
                known=dt.date(2026, 11, 2),
                body={"status": "open"},
            )
        ]
        timeline(
            t1,
            title="When was each status true?",
            scope=Scope("the history of task t1"),
            lane=lambda e: "t1",
            start=lambda e: e.true_from,
            end=lambda e: e.true_until,
            known=lambda e: e.known,
            label=lambda e: e.body["status"],
        )
        ```
    """
    marks = Marks(n, trace, flag, note, detail or {}, traces or {})
    items = list(items)
    if (
        thing is None
    ):  # a log entry belongs to its fact (identity); any other item to its lane
        thing = lambda i: getattr(i, "identity", None) or lane(i)  # noqa: E731
    order = {
        id(i): n for n, i in enumerate(items)
    }  # the order of the items: of the log, for `history`
    stops = [
        i for i in items if _op(i) == "end"
    ]  # an `end` entry of `history` stops the version before it
    retracts = [(figures(thing(i)), order[id(i)]) for i in items if _op(i) == "retract"]
    items = [i for i in items if _op(i) not in ("end", "retract", "same", "rename")]
    rows = rows_of(
        items,
        lambda i: lane(i),
        {
            "begins": start,
            "ends": end,
            "known_at": known or (lambda i: None),
            "value": label or (lambda i: None),
        },
        marks,
        computed=frozenset({"lane", "from", "to", "open"}),
    )
    dates = [d for r in rows for d in (r["begins"], r["ends"], r["known_at"]) if d]
    latest = max(dates, default=None)
    last = (
        plain(until)
        if until
        else (
            plain(dt.date.fromisoformat(latest[:10]) + dt.timedelta(days=7))
            if latest
            else None
        )
    )  # open bars show a week past the data
    first = min(dates, default=None)
    for item, row in zip(items, rows):
        row["_lane"], row["_pos"] = figures(lane(item)), order[id(item)]
        row["_of"] = figures(thing(item))
    starts: dict[str, list[Any]] = {}
    for row in rows:
        if row["begins"]:
            starts.setdefault(row["_of"], []).append(row["begins"])
    for (
        row
    ) in rows:  # a version with no end stops where the next version of its thing starts
        later = [
            b for b in starts.get(row["_of"], []) if row["begins"] and b > row["begins"]
        ]
        if row["ends"] is None and later:
            row["ends"] = min(later)
    for item in stops:
        of, stop = (
            figures(thing(item)),
            plain(getattr(item, "true_until", None) or end(item)),
        )
        for row in rows:
            if (
                row["_of"] == of
                and stop
                and (row["begins"] is None or row["begins"] < stop)
                and (row["ends"] is None or row["ends"] > stop)
            ):
                row["ends"] = stop
    for row in (
        rows
    ):  # a retract cuts the versions written before it, not a version added after it
        if any(of == row["_of"] and at > row["_pos"] for of, at in retracts):
            row["note"] = (
                row["note"] + "; " if row["note"] else ""
            ) + "retracted later: never true"
    for item, row in zip(items, rows):
        name = row["_lane"]
        row |= {
            "lane": name,
            "from": row["begins"] or first,
            "to": row["ends"] or last,
            "open": row["ends"] is None,
        }
        bits = (
            (["⚑"] if row["flagged"] else [])
            + ([figures(label(item))] if label else [])
            + _shared(row)
        )
        row["text"] = " · ".join(b for b in bits if b)
    for row in rows:  # a lane is marked if any of its versions is
        if any(r["flagged"] for r in rows if r["_lane"] == row["_lane"]):
            row["lane"] = "⚑ " + row["_lane"]
    order = list(dict.fromkeys(r["lane"] for r in rows))
    y = {"field": "lane", "type": "nominal", "sort": order, "title": None}
    xs = {
        "type": "temporal",
        "title": None,
        "axis": {"format": "%-d %b", "labelAngle": 0, "labelOverlap": True},
    }
    layers = [
        {
            "mark": {
                "type": "bar",
                "height": {"band": 0.5},
                "cornerRadius": 3,
                "color": "#86b6ef",
                "stroke": "#fcfcfb",
                "strokeWidth": 2,
            },
            "encoding": {
                "x": {"field": "from"} | xs,
                "x2": {"field": "to"},
                "y": y,
                "tooltip": tooltip(rows, "begins", "ends", "known_at", "value"),
            },
        },
        {
            "transform": [{"filter": "datum.known_at != null"}],
            "mark": {
                "type": "point",
                "shape": "diamond",
                "filled": True,
                "size": 90,
                "color": SERIES[1],
                "stroke": "#fcfcfb",
                "strokeWidth": 1.5,
            },
            "encoding": {
                "x": {"field": "known_at"} | xs,
                "y": y,
                "tooltip": [{"field": "item"}, {"field": "known_at", "title": "known"}],
            },
        },
        {
            "mark": {
                "type": "text",
                "align": "left",
                "dx": 4,
                "dy": -11,
                "fontSize": 10,
                "color": "#52514e",
            },
            "encoding": {
                "x": {"field": "from"} | xs,
                "y": y,
                "text": {"field": "text"},
            },
        },
    ]
    view = {
        "data": {"values": rows},
        "width": 560,
        "height": max(60, 40 * len(order)),
        "layer": layers,
    }
    return Chart(
        title,
        view,
        scope,
        tuple(rows),
        (
            "item",
            "begins",
            "ends",
            "known_at",
            "value",
            "note",
            "n",
            "source",
            "known",
            *marks.columns(),
        ),
        summary
        + (" " if summary else "")
        + "Bar: true from start to end. ◆: the time it became known."
        if known
        else summary,
        marked_line(marks, rows, None),
    )


def _layers(
    nodes: list[str], ends: list[tuple[str, str]]
) -> dict[str, tuple[float, float]]:
    """A left-to-right layout. A node's column is 1 more than the deepest node that
    links to it (a loop stops the walk).
    Then 4 passes forward and back order each column by the mean row of its neighbours.
    """
    into: dict[str, list[str]] = {n: [] for n in nodes}
    for a, b in ends:
        if a != b:
            into[b].append(a)
    column: dict[str, int] = {}

    def depth(node: str, seen: frozenset[str]) -> int:
        if node in column:
            return column[node]
        parents = [p for p in into[node] if p not in seen]
        column[node] = (
            0 if not parents else 1 + max(depth(p, seen | {node}) for p in parents)
        )
        return column[node]

    for node in nodes:
        depth(node, frozenset())
    out_of: dict[str, list[str]] = {n: [] for n in nodes}
    for a, b in ends:
        if a != b:
            out_of[a].append(b)
    last = max(column.values(), default=0)
    rows: dict[str, float] = {}
    for c in range(last + 1):
        for i, n in enumerate(n for n in nodes if column[n] == c):
            rows[n] = float(i)

    def sweep(order: range, near: dict[str, list[str]]) -> None:
        # each column in the order of the mean row of its neighbours (fewer crossings)
        for c in order:
            here = [n for n in nodes if column[n] == c]
            here.sort(
                key=lambda n: (
                    sum(rows[m] for m in near[n]) / len(near[n]) if near[n] else rows[n]
                )
            )
            for i, n in enumerate(here):
                rows[n] = float(i)

    for _ in range(4):
        sweep(range(1, last + 1), into)
        sweep(range(last - 1, -1, -1), out_of)
    return {n: (float(column[n]), rows[n]) for n in nodes}


def _op(item: Any) -> str | None:
    """The kind of a World API log entry (for example `add` or `end`), or None for any
    other item."""
    op = getattr(item, "op", None)
    return str(getattr(op, "value", op)) if op is not None else None


def _shared(row: dict[str, Any]) -> list[str]:
    return ([f"n={row['n']}"] if row.get("n") is not None else []) + (
        [row["note"]] if row.get("note") else []
    )
