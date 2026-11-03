# World

## Example data

The examples use this data and the names `todo`, `today` and `tasks`.

```python
import datetime as dt
from enum import StrEnum
from string.templatelib import Template

from scriptt.world import Fact, Goal, Key, Log, Ref, Row, World


class TodoList(Fact):
    name: Key[str]


class Status(StrEnum):
    OPEN = "open"
    DONE = "done"


class Task(Fact):
    id: Key[str]
    list: Ref[TodoList]
    title: str
    status: Status = Status.OPEN
    due: dt.date | None = None

    def __describe__(self) -> Template:  # how say() names a task
        return t"task {self.id}"


class Note(Fact):
    task: Key[Ref[Task]]
    text: str


todo = World.new(TodoList, Task, Note)
for name in ["home", "work"]:
    todo.add(
        TodoList(name=name),
        source="me",
        true_from="2 Nov 2026",
        known="2 Nov 2026 09:00",
    )
for key, home, title, due, true_from, known in [
    ("t1", "home", "Buy milk", dt.date(2026, 11, 3), "2 Nov 2026", "2 Nov 2026 09:00"),
    (
        "t2",
        "work",
        "Send the report",
        dt.date(2026, 11, 4),
        "2 Nov 2026",
        "2 Nov 2026 09:00",
    ),
    (
        "t3",
        "work",
        "Book the room",
        dt.date(2026, 11, 6),
        "2 Nov 2026",
        "2 Nov 2026 09:00",
    ),
    ("t4", "home", "Call the plumber", None, "2 Nov 2026", "2 Nov 2026 09:00"),
    (
        "t5",
        "home",
        "Water the plants",
        dt.date(2026, 11, 4),
        "2 Nov 2026",
        "2 Nov 2026 09:00",
    ),
    (
        "t6",
        "home",
        "Pay the rent",
        dt.date(2026, 11, 5),
        "3 Nov 2026",
        "3 Nov 2026 12:00",
    ),
]:
    todo.add(
        Task(id=key, list=home, title=title, due=due),
        source="me",
        true_from=true_from,
        known=known,
    )
for task, text in [("t1", "Oat milk"), ("t2", "Use the new template")]:
    todo.add(
        Note(task=task, text=text),
        source="me",
        true_from="2 Nov 2026",
        known="2 Nov 2026 09:00",
    )
milk = todo.on("2 Nov 2026").one(Task, id="t1")
todo.add(
    milk.but(status=Status.DONE),
    source="me",
    true_from="3 Nov 2026",
    known="3 Nov 2026 18:30",
)

today = todo.on("4 Nov 2026")
tasks = today.facts(Task)
```

::: scriptt.world.World
    options:
      members: ["on_date", "known_time", "until_date"]

## Make a world

::: scriptt.world.World
    options:
      show_root_heading: false
      heading_level: 3
      members: ["open", "new", "size"]

## Write to the log

::: scriptt.world.World
    options:
      show_root_heading: false
      heading_level: 3
      members: ["add", "end", "retract", "same", "map", "place", "rename"]

## Views

::: scriptt.world.World
    options:
      show_root_heading: false
      heading_level: 3
      members: ["on", "known", "at", "during", "steps", "suppose"]

## Read facts

::: scriptt.world.World
    options:
      show_root_heading: false
      heading_level: 3
      members: ["facts", "one", "get"]

## Read the log

::: scriptt.world.World
    options:
      show_root_heading: false
      heading_level: 3
      members: ["history", "origin"]

## References, kinds and problems

::: scriptt.world.World
    options:
      show_root_heading: false
      heading_level: 3
      members: ["problems", "about", "parents", "children", "ancestors", "descendants", "conflicts", "mapped"]

## Compare views

::: scriptt.world.World
    options:
      show_root_heading: false
      heading_level: 3
      members: ["__sub__"]

## Goals

::: scriptt.world.World
    options:
      show_root_heading: false
      heading_level: 3
      members: ["check"]

## SQL and export

::: scriptt.world.World
    options:
      show_root_heading: false
      heading_level: 3
      members: ["sql", "relation", "frame", "export"]
