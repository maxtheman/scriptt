# Quickstart

This page adds 3 tasks of a to-do list to a world. It marks 1 task done, asks 2 questions, writes 1 function
and writes 1 sentence.

!!! success "Real output"
    The code on this page is one script, [`quickstart.py`](examples/quickstart.py). The documentation build
    runs the script. Each output on this page comes from that run.

## 1. Declare a type

--8<-- "docs/examples/quickstart.py:declare"

- A **type** gives the fields of 1 kind of fact. Here the type is `Task`. A task has an id, a title and a done
  flag.
- A **fact** is 1 statement of a type, with its source and its dates. Example: the task `t1` has the title
  "Buy milk".
- `Key[str]` marks the **key**. The key names the thing that a fact is about. A later task with the same id is
  a new version of the same task.
- `done: bool = False` gives a default. A new task is open.

## 2. Add 3 tasks

--8<-- "docs/examples/quickstart.py:add"

`World.new(Task)` makes an empty **world** for the type `Task`. A world keeps facts in a **log**. Each `add`
writes 1 entry at the end of the log. Each `add` has 3 more arguments.

| Argument | Meaning | Value here |
|---|---|---|
| `source` | Where the fact came from. | `"me"` |
| `true_from` | The date from which the fact is true. | 2 Nov 2026 |
| `known` | The time at which you got the fact. | 2 Nov 2026 at 09:00 |

## 3. Ask what is true on a date

--8<-- "docs/examples/quickstart.py:on"

--8<-- "output:quickstart/on"

`on` gives a **view**. A view contains the facts that are true on 1 date. It is a `World` object that reads the
same log. `facts(Task)` gives the tasks of the view as a table. On 2 Nov all 3 tasks are open.

## 4. Mark a task done

--8<-- "docs/examples/quickstart.py:done"

--8<-- "output:quickstart/done"

- `one(Task, id="t2")` gives the task with the key `t2`.
- `but(done=True)` gives a copy of the task with 1 field changed. A fact never changes. A copy with the same
  key is a new **version** of the task.
- The report was done on 3 Nov. You wrote it down on 4 Nov at 10:00. Thus `true_from` is 3 Nov and `known` is
  4 Nov at 10:00.

| Output line | Meaning |
|---|---|
| 2 | The task `t1` is open. |
| 3 | The task `t2` is done from 3 Nov. The view of 3 Nov shows the new version. |
| 4 | The task `t3` is open. |

## 5. Ask what you knew at a time

--8<-- "docs/examples/quickstart.py:known"

--8<-- "output:quickstart/known"

`known` limits a view to the facts that you got by a time. At 18:00 on 3 Nov you did not have the new version.
Thus the report is open in this view. The page [What was true, and what you knew](time-travel.md) shows the 2
dates in more detail.

## 6. Write a function

--8<-- "docs/examples/quickstart.py:function"

--8<-- "output:quickstart/function"

A **function** reads a view and gives an answer. `open_tasks` keeps the tasks for which `not task.done` is
true. `where` takes the rule as a Python function. `Facts[Task]` is the type of the result. Your editor
completes its fields, and your type checker checks it.

## 7. Write a sentence

--8<-- "docs/examples/quickstart.py:say"

--8<-- "output:quickstart/say"

`say` fills a Python t-string. A **t-string** is a string with the prefix `t`, new in Python 3.14. It keeps
each `{value}` apart from the text. `say` writes each date as "4 Nov 2026" and each fact by its type and key.

## Next

| Page | Contents |
|---|---|
| [Tutorial: a to-do app](tutorial-todo.md) | Lists, due dates, mistakes, rules, changes and the functions of a to-do app. |
| [What was true, and what you knew](time-travel.md) | The 2 dates of a fact and the 4 answers that they give. |
| [Mental model](mental-model.md) | The words of the library, and 4 questions before you start. |
