# Changelog

All notable changes to `scriptt` and `scriptt-charts` are in this file. The two packages have the same version
and are released together. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). The
versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html): before 1.0.0, a change that breaks
code bumps the minor number, and any other change bumps the patch number.

## [Unreleased]

### Fixed

- A `sql` error names each table as the `{Type}` that made it, instead of the temporary table (`night#4`).
- A `sql` query that names a fact type without braces gets the fix in the error: "Write {Night} for the table
  of the type Night".
- `to_text` writes a large or a small float with an exponent (`1e+16`), and `parse` reads it back.

## [0.1.0] - 2026-11-02

The first public release, a pre-alpha. Only the world works: the facts, their types and the knowledge graph
that links them. The harness is not part of it. The distributions are `scriptt` and `scriptt-charts`. Import them as
`scriptt.world` and `scriptt.charts`.

### Added

- `World.new` and `World.open` make a world: a log of facts in a DuckDB table. Nothing in the log is changed or
  removed.
- A type of fact is a subclass of `Fact`, a frozen Pydantic model. `Key[...]` marks the fields that name a thing.
  `Ref[T]` holds the key of another fact.
- `add` records a fact with its source, the date it is true from and the time you knew it. `end` and `retract`
  record that a fact stopped or was wrong.
- `on(date)` gives the facts that were true on a date. `known(time)` gives what the log held at a time.
- `later - earlier` gives what changed between two views. `suppose(...)` gives what would change.
- The verbs of a view follow dplyr: `where`, `arrange`, `top`, `mutate`, `group_by` and `summarise`,
  `count_by`, `join`, `left_join`, `map`.
- `Goal` checks a rule with a number to reach. `view.problems(*goals)` gives each broken reference and each fact
  that fails a goal.
- `say(t"...")` makes a sentence from a t-string. It shows each value with its source. `when()` reads a date from
  text and refuses a date that has two meanings.
- `sql` runs one DuckDB `SELECT`, `PIVOT`, `UNPIVOT` or `EXPLAIN` over the facts of a view. `export` writes them
  to files.
- `scriptt.world.versions` reads results kept with git and DVC (the `versions` extra).
- The docs build a to-do app, starting with 1 type. Each output on the pages comes from a run of the
  example scripts.
- `scriptt-charts`: charts that show their evidence (counts, sources, scope, flags, assumptions) as Vega-Lite,
  Altair, HTML or a table.

[Unreleased]: https://github.com/maxtheman/scriptt/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/maxtheman/scriptt/releases/tag/v0.1.0
