# API reference

These pages are made from the docstrings of the 2 packages.

| Page | Import | Contents |
|---|---|---|
| [World](world.md) | `from scriptt.world import World` | the log and its views: write, view, read, compare, goals, SQL, export |
| [Facts and rows](facts.md) | `from scriptt.world import Facts, Row, Pair, Groups` | the collection and its dplyr verbs |
| [Fact types](fact.md) | `from scriptt.world import Fact, Key, Ref, Forward` | the base class of a type of fact, and the field marks (`Key`, `Ref` and `Forward` are type aliases) |
| [The log](log.md) | `from scriptt.world import Entry, Origin, Op, Change, Changes, Conflict, Match, Mapping, Under, Rel, Problem, Log` | the entries of the log and the results made from them |
| [Goals](goals.md) | `from scriptt.world import Goal, GoalResult, Step` | rules with a number to reach, checked on 1 date or a series |
| [Text and dates](text.md) | `from scriptt.world import say, describe, significant, relative, when, Moment, diagram` | sentences from t-strings; dates from text; `Moment`, the type of a date argument |
| [Versions](versions.md) | `from scriptt.world.versions import Project, Result` | results kept with git and DVC (extra `scriptt[versions]`) |
| [Charts](charts.md) | `from scriptt.charts import ranked, Scope` | the separate package `scriptt-charts` |
