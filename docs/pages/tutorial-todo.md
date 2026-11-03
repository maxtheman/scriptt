# Tutorial: a to-do app

This tutorial grows 1 world for a to-do app in 14 steps. It starts with 1 type and 1 task. At the end the log
has 2 lists and 5 tasks, and the app has 1 goal and 2 functions. Do the [quickstart](quickstart.md) first.

!!! success "Real output"
    The code on this page is one script, [`todo.py`](examples/todo.py). The documentation build runs the
    script. Each output on this page comes from that run.

--8<-- "docs/examples/todo.py:setup"

## 1. One type gives one table

--8<-- "docs/examples/todo.py:one_type"

--8<-- "output:todo/one_type"

The world has 1 type and 1 fact. `facts(Task)` gives the facts of the type as a table, with 1 column for each
field. This `add` has no `true_from`. Thus the task is true for all time.

## 2. The world gets a new type

A to-do app keeps tasks in lists. The next code adds the type `TodoList` to the same world. It also declares
`Task` again, with 3 more fields.

--8<-- "docs/examples/todo.py:lists"

--8<-- "output:todo/lists"

- `TodoList` is a type with 1 field. Its key is the name of the list. Example: `home`.
- `Status` is an enum. A field of an enum type accepts only its values: `open` and `done`.
- `list: Ref[TodoList] | None = None` is a **reference**. It contains the key of a `TodoList`. Example: the
  value `"home"` points to the list `home`.
- `due: dt.date | None = None` is an optional date. A task with no due date has `None`.

Each new field has a default. Thus the task `t1` of step 1 is still a valid task. The table writes `None` as
`none`.

## 3. Add the tasks

--8<-- "docs/examples/todo.py:add"

--8<-- "output:todo/add"

The loop adds 4 tasks. Each task is true from 2 Nov, and you got each task at 09:00 on 2 Nov. The task `t1`
already exists. Thus this `add` gives `t1` a new version, with a list and a due date.

## 4. A done task is a new version

--8<-- "docs/examples/todo.py:done"

--8<-- "output:todo/done"

`milk.but(status=Status.DONE)` gives a copy of the task `t1` with a new status. The copy has the same key. Thus
`add` writes it as a new version of `t1`. The old versions stay in the log.

| View | Status of `t1` | Cause |
|---|---|---|
| `todo.on("2 Nov 2026")` | open | The done version is true from 3 Nov. |
| `todo.on("3 Nov 2026")` | done | The done version is true on 3 Nov. |

## 5. The log keeps each version

--8<-- "docs/examples/todo.py:history"

--8<-- "output:todo/history"

`history` gives each entry of the log for 1 fact. `entry.body` is the fields of the fact as a dictionary. `map`
makes 1 row from each entry. `Row(list=..., status=...)` makes 1 table row with the columns that you name.

| Output line | Meaning |
|---|---|
| 2 | The task of step 1. It has no list and no status field, and no true-from date. |
| 3 | The version of step 3. It has the list `home` and the status `open`, true from 2 Nov. |
| 4 | The done version. It is true from 3 Nov. You got it at 18:30 on 3 Nov. |

## 6. A reference to a list that does not exist

The next task points to the list `shop`. The world has no list with that name.

--8<-- "docs/examples/todo.py:mistake"

--8<-- "output:todo/mistake"

`problems` gives each reference that points to no fact. The row names the rule, the fact, the field and the
value.

## 7. Retract a mistake

--8<-- "docs/examples/todo.py:retract"

--8<-- "output:todo/retract"

To **retract** a fact is to mark it as a mistake. `retract` writes 1 more entry to the log. A view that knows
the retraction leaves the task out. Thus the view of 3 Nov has 0 problems. A view with an earlier `known` time
still shows `t5`.

## 8. End a task

You do not need the room after 4 Nov. Thus you end the task "Book the room" on 5 Nov.

--8<-- "docs/examples/todo.py:end"

--8<-- "output:todo/end"

To **end** a fact is to give the date on which it stops being true. The view of 4 Nov has 4 tasks. The view of
5 Nov has 3 tasks. An ended fact stays true in each view before its end date.

## 9. The functions of the app

--8<-- "docs/examples/todo.py:functions"

--8<-- "output:todo/functions"

The app has 2 functions. Each function reads a view and gives `Facts[Task]`.

| Function | Gives | Result on 5 Nov |
|---|---|---|
| `open_tasks` | The tasks with the status `open`. | `t2` and `t4` |
| `overdue` | The open tasks with a due date before the date of the view. | `t2`, due on 4 Nov |

`overdue` calls `open_tasks`. `view.on_date` is the date of the view. A function can call a different function
of the app.

## 10. Count the open tasks of each list

--8<-- "docs/examples/todo.py:count"

--8<-- "output:todo/count"

`count_by` counts the facts in each group. The argument name `list` becomes the name of the column. The column
`n` gives the count.

## 11. A rule for every task

--8<-- "docs/examples/todo.py:goal"

--8<-- "output:todo/goal"

A **goal** is a rule and the number of facts that must agree with it. With `every=True` the number is every
task of the view. The view of 5 Nov has 3 tasks. `check` tests the goal on the view.

- Line 1 is the result. "(2 of 3)" shows that 2 of the 3 tasks agree. Thus the goal is not met.
- `result.failing` gives the task that does not agree. The task `t4` is open and has no due date.

## 12. What changed between 2 dates

--8<-- "docs/examples/todo.py:changes"

--8<-- "output:todo/changes"

The `-` operator gives the changes from the view of 2 Nov to the view of 5 Nov.

- `changes.removed` gives the facts of the earlier view that the later view does not have. The task `t3`
  ended on 5 Nov.
- `changes.changed` gives each fact with a new version. `fields` gives the fields that changed. The status of
  `t1` went from `open` to `done`.

## 13. A sentence for the person

--8<-- "docs/examples/todo.py:say"

--8<-- "output:todo/say"

`say` writes a fact by its type and its key. Thus `late[0]` becomes "task t2".

## 14. A question in SQL

--8<-- "docs/examples/todo.py:sql"

--8<-- "output:todo/sql"

`sql` runs 1 DuckDB query on the facts of the view. `{Task}` in the t-string becomes a table of the tasks.
`status` is a DuckDB enum. Thus `ORDER BY status` uses the order of `Status`: `open`, then `done`.

## Summary

- Give each kind of thing a type. Mark the fields that name the thing with `Key`.
- Add a type to the world when the app needs it. Give each new field a default.
- Write a change as a new version with `but`. The log keeps each version.
- Use `retract` for a mistake. Use `end` for a fact that stops being true.
- Put each question of the app in a function that reads a view.
- Use a goal for a rule that each fact must agree with.

Next: [What was true, and what you knew](time-travel.md).
