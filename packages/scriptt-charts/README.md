# scriptt-charts

Charts that show their evidence: the count behind each value, where each value came from and when it was known, what
the data covers and leaves out, rules that mark items, and assumptions that the reader can change.

```python
from types import SimpleNamespace as List

from scriptt.charts import Scope, ranked

lists = [List(name="home", open=1), List(name="work", open=2)]
shown = ranked(
    lists,
    title="Which list has the most open tasks?",
    scope=Scope("the to-do lists on 5 Nov 2026"),
    label=lambda row: row.name,
    value=lambda row: row.open,
    unit="tasks",
)
shown.json()  # the Vega-Lite spec
shown.table()  # the rows as text
shown.altair()  # an Altair chart: needs the extra scriptt-charts[altair]
```

Forms: `ranked`, `ranges`, `over_time`, `views`, `members`, `flows`, `side_by_side`, `tree`, `graph`, `timeline`. The
package needs only `scriptt` (for the text of numbers and dates); Altair is an optional extra.
