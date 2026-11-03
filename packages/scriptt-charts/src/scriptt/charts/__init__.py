"""Charts for World API results, in a separate package. A chart answers 1 question and
shows its evidence. It shows the
count behind each value (`n`) and where each value came from (`trace`). It shows what
the data covers and leaves out
(`Scope`), a rule that marks some items (`Flag`) and notes. A reader can change an
assumption on the chart (`Choice`).

The forms for values are:

- `ranked` (items with their share of a total)
- `ranges` (low to high with a middle and a point)
- `over_time` (values over dates)
- `views` (2 or 3 named views of the same items)
- `members` (items against groups)
- `flows` (moves between categories)
- `side_by_side` (2 charts of the same items)

The forms for the shape of the data are:

- `tree` (things under things, with totals)
- `graph` (things and typed links)
- `timeline` (versions of things as lanes, with the time each became known)

Each form gives a `Chart`. A `Chart` renders to Vega-Lite (`chart.json()`), to Altair
(`chart.altair()` with the extra `scriptt-charts[altair]`), to HTML (`chart.html()`) or
to a plain table (`chart.table()`).

Numbers and dates are written as the World API writes them. A `trace` may give a World
API `Origin` or `Entry`. The
chart reads their `source` and `known`.
"""

from ._chart import Chart, side_by_side
from ._chart import Marks as Marks  # importable, not in __all__
from ._forms import flows, members, money, over_time, ranges, ranked, views
from ._parts import Choice, Flag, Scope, Target, Trace, figures
from ._shapes import graph, timeline, tree

__all__ = [
    "Chart",
    "Choice",
    "Flag",
    "Scope",
    "Target",
    "Trace",
    "figures",
    "flows",
    "graph",
    "members",
    "money",
    "over_time",
    "ranges",
    "ranked",
    "side_by_side",
    "timeline",
    "tree",
    "views",
]
