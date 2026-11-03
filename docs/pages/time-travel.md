# What was true, and what you knew

Each fact in a world has 2 dates. This page uses 1 task to show the 4 answers that the 2 dates give.

!!! success "Real output"
    The code on this page is one script, [`time_travel.py`](examples/time_travel.py). The documentation build
    runs the script. Each output on this page comes from that run.

## The 2 dates

| Date | Meaning | Argument of `add` | Question that it answers |
|---|---|---|---|
| true from | The date from which the fact is true. | `true_from` | What was true on a date? |
| known | The time at which you got the fact. | `known` | What did you know at a time? |

The 2 dates are often different. Example: you sent the report on 3 Nov. You marked the task done on 4 Nov at
10:00. Thus the done version is true from 3 Nov, and you knew it from 4 Nov at 10:00.

## The example

--8<-- "docs/examples/time_travel.py:setup"

The world has 2 versions of the task `t2`. The first version is open. The second version is done.

--8<-- "chart:time_travel/timeline"

The timeline shows the 4 dates and times of the 2 entries, from left to right. Each entry has a date on which it
becomes true and a time at which you write it down. The done version becomes true on 3 Nov, 1 day before you
write it down.

## 1. Ask on 4 dates and times

--8<-- "docs/examples/time_travel.py:grid"

--8<-- "output:time_travel/grid"

`todo.on(on).known(known)` gives the view of 1 date, limited to the facts that you got by 1 time.
`Facts(answers)` makes a table from the list of rows.

| Output line | Meaning |
|---|---|
| 1 | On 2 Nov the task was open. |
| 2 | On the evening of 3 Nov you thought that the task was open. You wrote down the done version at 10:00 on 4 Nov. |
| 3 | Line 3 asks about the same date 1 day later. Now you know that the task was done on 3 Nov. |
| 4 | On 4 Nov the task is done. |

Lines 2 and 3 ask about the same date. They give different answers, because the second answer uses a fact that
you got later.

## 2. See the entries of the log

--8<-- "docs/examples/time_travel.py:history"

--8<-- "output:time_travel/history"

`history` gives each entry of the log for 1 fact. Each entry has its 2 dates. The log also keeps `written`, the
time of the `add` call. The log never changes an entry.
Thus you can ask the same question again on a later day and get the old answer.

## When to use each date

| You want to know | Use |
|---|---|
| The tasks that are open today | `todo.on("today")` |
| The tasks that were open on a past date, with all that you know now | `todo.on("3 Nov 2026")` |
| The answer that you got at a past time | `todo.on("3 Nov 2026").known("3 Nov 2026 18:00")` |
| The cause of a change in an answer | The entries of `history`, with their `known` times |

## Limits

- A true-from date has no time of day.
- A fact with no true-from date is true for all time.
- A fact with no `known` time has the time of the `add` call.
