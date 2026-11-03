"""World API records facts with their source and their dates. Ask what was true on any
date. Ask what you knew on any date.

Import the names that you need from `world`:

```python
from scriptt.world import World, Fact, Key, Forward, Goal, Step, Match, when
```

Make a world with `World.new` or `World.open`. Declare each type of fact as a subclass
of `Fact`.
"""

from ._diagram import diagram
from ._fact import Fact, Forward, Key, Ref
from ._facts import Facts, Groups, Pair, Row
from ._say import describe, relative, say, significant
from ._time import Moment as Moment  # importable, not in __all__
from ._time import Step, when
from ._world import (
    Change,
    Changes,
    Conflict,
    Entry,
    Goal,
    GoalResult,
    Log,
    Mapping as Mapping,  # importable, not in __all__
    Match,
    Op,
    Origin,
    Problem,
    Rel,
    Under,
    World,
)

__all__ = [
    "Change",
    "Changes",
    "Conflict",
    "Entry",
    "Fact",
    "Facts",
    "Forward",
    "Goal",
    "GoalResult",
    "Groups",
    "Key",
    "Log",
    "Match",
    "Op",
    "Origin",
    "Pair",
    "Problem",
    "Ref",
    "Rel",
    "Under",
    "Row",
    "Step",
    "World",
    "describe",
    "diagram",
    "relative",
    "say",
    "significant",
    "when",
]
