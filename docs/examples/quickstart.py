"""The Quickstart page: 1 type, 3 tasks, 1 task done, 2 questions, 1 function and 1
sentence."""

# [start:declare]
from scriptt.world import Fact, Facts, Key, World, say


class Task(Fact):
    id: Key[str]
    title: str
    done: bool = False


# [end:declare]

# [start:add]
todo = World.new(Task)
for id, title in [("t1", "Buy milk"), ("t2", "Send the report"), ("t3", "Book a room")]:
    todo.add(
        Task(id=id, title=title),
        source="me",
        true_from="2 Nov 2026",
        known="2 Nov 2026 09:00",
    )
# [end:add]

# [start:on]
print(todo.on("2 Nov 2026").facts(Task))
# [end:on]
print("@@on")

# [start:done]
report = todo.on("2 Nov 2026").one(Task, id="t2")
todo.add(
    report.but(done=True),
    source="me",
    true_from="3 Nov 2026",
    known="4 Nov 2026 10:00",
)
print(todo.on("3 Nov 2026").facts(Task))
# [end:done]
print("@@done")

# [start:known]
print(todo.on("3 Nov 2026").known("3 Nov 2026 18:00").facts(Task))
# [end:known]
print("@@known")


# [start:function]
def open_tasks(view: World) -> Facts[Task]:
    """The tasks that are not done on the date of the view."""
    return view.facts(Task).where(lambda task: not task.done)


print(open_tasks(todo.on("4 Nov 2026")))
# [end:function]
print("@@function")

# [start:say]
today = todo.on("4 Nov 2026")
print(say(t"On {today.on_date} you have {open_tasks(today).count()} open tasks."))
# [end:say]
print("@@say")
