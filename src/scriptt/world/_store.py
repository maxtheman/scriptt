"""The log is kept in DuckDB 2.0. Each entry is 1 row. The fact itself is a VARIANT
value. 1 SQL query over the log
(window functions and QUALIFY) picks the version of each fact that is true in a view."""

import datetime as dt
import json
import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import duckdb

SCHEMA = """
CREATE TABLE IF NOT EXISTS log (
    seq BIGINT PRIMARY KEY,
    op VARCHAR NOT NULL,          -- add | end | retract | same | rename
    type_name VARCHAR NOT NULL,
    identity VARCHAR NOT NULL,    -- the key values, as JSON text
    body VARIANT,                 -- the fact, or the details of a same or rename entry
    true_from DATE,
    true_until DATE,
    known TIMESTAMP NOT NULL,
    written TIMESTAMP NOT NULL,
    source VARCHAR NOT NULL
)"""

# The version of each fact that is true in a view: of the entries known by $known (and
# the supposed ones), drop
# everything before the last retract; keep the latest version for each start date; a
# version runs until its own end,
# the next start, or the first `end` entry dated after its start (or on its start day,
# if written after the add). So an
# end cuts the versions that start before it, and an add from the end day on begins a
# new period. Keep the versions that overlap [$lo, $hi), and
# of those the latest start, in the order the facts first entered the log (whatever the
# view knows). Entries are
# ordered by their known time, so a back-filled entry with an earlier known time counts
# as written earlier. A supposed add with no start replaces every
# logged version; logged ends do not cut a supposed add, supposed ends do.
VERSIONS = """
WITH src AS (
    FROM log SELECT * WHERE type_name = $kind AND known <= $known
    UNION ALL BY NAME
    FROM supposed SELECT * WHERE type_name = $kind
),
firsts AS (FROM log SELECT identity, min(seq) AS first_seq WHERE type_name = $kind GROUP
BY ALL),
k AS (FROM src LEFT JOIN firsts USING (identity)
      SELECT src.*, row_number() OVER (PARTITION BY identity ORDER BY known, seq) AS
      pos, coalesce(firsts.first_seq, src.seq) AS first_seq
      WHERE op IN ('add', 'end', 'retract')),
cut AS (FROM k SELECT identity, max(pos) AS rpos WHERE op = 'retract' GROUP BY ALL),
kept AS (FROM k LEFT JOIN cut USING (identity) SELECT k.* WHERE k.pos >
coalesce(cut.rpos, 0)),
override AS (FROM kept SELECT identity, max(pos) AS opos WHERE op = 'add' AND seq >=
1000000000000 AND true_from IS NULL GROUP BY ALL),
adds AS (FROM kept LEFT JOIN override USING (identity)
         SELECT kept.*, override.opos IS NOT NULL OR kept.seq >= 1000000000000 AS
         overridden
         WHERE op = 'add' AND (override.opos IS NULL OR kept.pos = override.opos)
         QUALIFY row_number() OVER (PARTITION BY identity, true_from ORDER BY pos DESC)
         = 1),
ends AS (FROM kept SELECT identity, true_until AS ended, pos AS epos, seq >=
1000000000000 AS supposed_end WHERE op = 'end'),
periods AS (FROM adds SELECT *, lead(true_from) OVER (PARTITION BY identity ORDER BY
true_from NULLS FIRST) AS next_start),
stops AS (FROM periods p
          SELECT p.*, nullif(least(coalesce(p.true_until, DATE '9999-12-31'),
          coalesce(p.next_start, DATE '9999-12-31'),
                                   coalesce((FROM ends e SELECT min(e.ended)
                                             WHERE e.identity = p.identity AND (NOT
                                             p.overridden OR e.supposed_end)
                                               AND (e.ended > coalesce(p.true_from, DATE
                                               '0001-01-01')
                                                    OR (e.ended = p.true_from AND e.epos
                                                    > p.pos))), DATE '9999-12-31')),
                           DATE '9999-12-31') AS stop)
FROM stops
SELECT seq, identity, body::JSON AS body, true_from, true_until, known, written, source
WHERE coalesce(true_from, DATE '0001-01-01') < $hi AND (stop IS NULL OR $lo < stop)
QUALIFY row_number() OVER (PARTITION BY identity ORDER BY true_from DESC NULLS LAST) = 1
ORDER BY first_seq
"""


@dataclass(frozen=True, slots=True)
class Row:
    """1 entry of the log as Python values."""

    seq: int
    op: str
    type_name: str
    identity: str
    body: dict[str, Any]
    true_from: dt.date | None
    true_until: dt.date | None
    known: dt.datetime
    written: dt.datetime
    source: str


def _json(value: Any) -> str:
    return json.dumps(
        value, default=lambda v: v.value if isinstance(v, Enum) else str(v)
    )


class Store:
    """The log table in 1 DuckDB database, in memory or in a file. Each thread gets its
    own cursor on the database, with its own temporary tables. So views and forks of 1
    log run in several threads at once: DuckDB runs their queries in parallel."""

    def __init__(self, path: str | Path | None = None) -> None:
        self._database = duckdb.connect(str(path) if path else ":memory:")
        self._database.execute(SCHEMA)
        self._local = threading.local()
        self._writing = threading.Lock()
        counted = self.con.execute("SELECT count() FROM log").fetchone()
        self.size = counted[0] if counted else 0

    @property
    def con(self) -> duckdb.DuckDBPyConnection:
        """This thread's cursor. A DuckDB connection object is not safe to share
        between threads, and the table of supposed entries belongs to 1 cursor."""
        cursor = getattr(self._local, "cursor", None)
        if cursor is None:
            cursor = self._local.cursor = self._database.cursor()
            cursor.execute(
                "CREATE TEMP TABLE IF NOT EXISTS supposed AS FROM log LIMIT 0"
            )
        return cursor

    def append(self, row: Row) -> None:
        """Add 1 entry. Its seq is 1 more than the largest in the file. This stops a
        collision between 2 handles on 1 file. 1 thread writes at a time."""
        with self._writing:
            self._append(row)

    def _append(self, row: Row) -> None:
        self.con.execute(
            "INSERT INTO log SELECT coalesce(max(seq), 0) + 1, $1, $2, $3, "
            "$4::JSON::VARIANT, $5, $6, $7, $8, $9 FROM log",
            [
                row.op,
                row.type_name,
                row.identity,
                _json(row.body),
                row.true_from,
                row.true_until,
                row.known,
                row.written,
                row.source,
            ],
        )
        self.size += 1

    def count(self) -> int:
        """The number of entries in the file now. This includes entries that another
        handle wrote."""
        counted = self.con.execute("SELECT count() FROM log").fetchone()
        return counted[0] if counted else 0

    def _rows(self, query: str, params: dict[str, Any]) -> list[Row]:
        out = []
        for (
            seq,
            op,
            kind,
            ident,
            body,
            tf,
            tu,
            known,
            written,
            source,
        ) in self.con.execute(query, params).fetchall():
            out.append(
                Row(
                    seq,
                    op,
                    kind,
                    ident,
                    json.loads(body) if body else {},
                    tf,
                    tu,
                    known,
                    written,
                    source,
                )
            )
        return out

    def entries(
        self,
        *,
        kind: str,
        identity: str | None = None,
        ops: tuple[str, ...] = (),
        known: dt.datetime,
    ) -> list[Row]:
        """The entries of 1 type (and 1 identity) that are known by `known`. They are in
        the order that they were written."""
        where = ["type_name = $kind", "known <= $known"]
        params: dict[str, Any] = {"kind": kind, "known": known}
        if identity is not None:
            where.append("identity = $identity")
            params["identity"] = identity
        if ops:
            where.append("list_contains($ops, op)")
            params["ops"] = list(ops)
        return self._rows(
            f"FROM log SELECT seq, op, type_name, identity, body::JSON, true_from, "
            f"true_until, known, written, source "
            f"WHERE {' AND '.join(where)} ORDER BY known, seq",
            params,
        )

    def versions(
        self,
        *,
        kind: str,
        lo: dt.date,
        hi: dt.date,
        known: dt.datetime,
        supposed: tuple[Row, ...],
    ) -> list[Row]:
        """The version of each fact of 1 type that is true on [lo, hi) and known by
        `known`."""
        self.con.execute("DELETE FROM supposed")
        for row in supposed:
            self.con.execute(
                "INSERT INTO supposed VALUES ($1, $2, $3, $4, $5::JSON::VARIANT, $6, "
                "$7, $8, $9, $10)",
                [
                    row.seq,
                    row.op,
                    row.type_name,
                    row.identity,
                    _json(row.body),
                    row.true_from,
                    row.true_until,
                    row.known,
                    row.written,
                    row.source,
                ],
            )
        result = []
        for seq, ident, body, tf, tu, known_at, written, source in self.con.execute(
            VERSIONS, {"kind": kind, "known": known, "lo": lo, "hi": hi}
        ).fetchall():
            result.append(
                Row(
                    seq,
                    "add",
                    kind,
                    ident,
                    json.loads(body),
                    tf,
                    tu,
                    known_at,
                    written,
                    source,
                )
            )
        return result
