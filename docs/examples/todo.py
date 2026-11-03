"""The tutorial "Build a to-do app": 1 type and 1 task at the start. Then the same world
gets lists, done tasks, due dates, mistakes, rules, changes and the functions of the
app.
"""

# Step 2 declares Task again, with more fields. The page shows each declaration.
# pyright: reportRedeclaration=false

# [start:setup]
import datetime as dt
from enum import StrEnum

from scriptt.world import Fact, Facts, Goal, Key, Ref, Row, World, say

# [end:setup]


# [start:one_type]
class Task(Fact):
    id: Key[str]
    title: str


todo = World.new(Task)
todo.add(Task(id="t1", title="Buy milk"), source="me", known="2 Nov 2026 09:00")
print(todo.facts(Task))
# [end:one_type]
print("@@one_type")


# [start:lists]
class TodoList(Fact):
    name: Key[str]


class Status(StrEnum):
    OPEN = "open"
    DONE = "done"


class Task(Fact):
    id: Key[str]
    title: str
    list: Ref[TodoList] | None = None
    status: Status = Status.OPEN
    due: dt.date | None = None


todo.add(TodoList(name="home"), source="me", known="2 Nov 2026 09:00")
todo.add(TodoList(name="work"), source="me", known="2 Nov 2026 09:00")
print(todo.facts(Task))
# [end:lists]
print("@@lists")

# [start:add]
for id, list, title, due in [
    ("t1", "home", "Buy milk", dt.date(2026, 11, 3)),
    ("t2", "work", "Send the report", dt.date(2026, 11, 4)),
    ("t3", "work", "Book the room", dt.date(2026, 11, 6)),
    ("t4", "home", "Call the plumber", None),
]:
    todo.add(
        Task(id=id, list=list, title=title, due=due),
        source="me",
        true_from="2 Nov 2026",
        known="2 Nov 2026 09:00",
    )
print(todo.on("2 Nov 2026").facts(Task))
# [end:add]
print("@@add")

# [start:done]
milk = todo.on("2 Nov 2026").one(Task, id="t1")
todo.add(
    milk.but(status=Status.DONE),
    source="me",
    true_from="3 Nov 2026",
    known="3 Nov 2026 18:30",
)
print(todo.on("2 Nov 2026").one(Task, id="t1").status)
print(todo.on("3 Nov 2026").one(Task, id="t1").status)
# [end:done]
print("@@done")

# [start:history]
print(
    todo.history(milk).map(
        lambda entry: Row(
            list=entry.body.get("list"),
            status=entry.body.get("status"),
            true_from=entry.true_from,
            known=entry.known,
        )
    )
)
# [end:history]
print("@@history")

# [start:mistake]
todo.add(
    Task(id="t5", list="shop", title="Buy a lamp"),
    source="me",
    true_from="3 Nov 2026",
    known="3 Nov 2026 19:00",
)
print(todo.on("3 Nov 2026").problems())
# [end:mistake]
print("@@mistake")

# [start:retract]
todo.retract(Task, id="t5", source="me", known="3 Nov 2026 19:05")
print(todo.on("3 Nov 2026").problems().count())
# [end:retract]
print("@@retract")

# [start:end]
todo.end(Task, id="t3", on="5 Nov 2026", source="me", known="4 Nov 2026 16:00")
print(todo.on("4 Nov 2026").facts(Task).count())
print(todo.on("5 Nov 2026").facts(Task))
# [end:end]
print("@@end")


# [start:functions]
def open_tasks(view: World) -> Facts[Task]:
    """The tasks that are open on the date of the view."""
    return view.facts(Task).where(lambda task: task.status == Status.OPEN)


def overdue(view: World) -> Facts[Task]:
    """The open tasks whose due date is before the date of the view."""
    day = view.on_date
    return open_tasks(view).where(lambda task: task.due is not None and task.due < day)


print(overdue(todo.on("5 Nov 2026")))
# [end:functions]
print("@@functions")

# [start:count]
print(open_tasks(todo.on("5 Nov 2026")).count_by(list=lambda task: task.list))
# [end:count]
print("@@count")

# [start:goal]
every_due = Goal(
    "every open task has a due date",
    Task,
    lambda task: task.status == Status.DONE or task.due is not None,
    every=True,
)
result = todo.on("5 Nov 2026").check(every_due)
print(result)
print(result.failing)
# [end:goal]
print("@@goal")

# [start:changes]
changes = todo.on("5 Nov 2026") - todo.on("2 Nov 2026")
print(changes.removed)
print(
    Facts(
        Row(task=say(t"{change.after}"), field=field, before=before, after=after)
        for change in changes.changed
        for field, (before, after) in change.fields().items()
    )
)
# [end:changes]
print("@@changes")

# [start:say]
view = todo.on("5 Nov 2026")
late = overdue(view)
print(
    say(
        t"On {view.on_date} you have {open_tasks(view).count()} open tasks. "
        t"{late.count()} is late: {late[0]}."
    )
)
# [end:say]
print("@@say")

# [start:sql]
print(
    view.sql(
        t"""SELECT status, count(*) AS tasks
        FROM {Task} GROUP BY status ORDER BY status"""
    )
)
# [end:sql]
print("@@sql")
