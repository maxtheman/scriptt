"""The example on the home page: 3 tasks, 1 task done, 1 function. The README shows the
same code."""

# [start:example]
from scriptt.world import Fact, Facts, Key, World


class Task(Fact):
    id: Key[str]
    title: str
    done: bool = False


todo = World.new(Task)
for id, title in [("t1", "Buy milk"), ("t2", "Send the report"), ("t3", "Book a room")]:
    todo.add(
        Task(id=id, title=title),
        source="me",
        true_from="2 Nov 2026",
        known="2 Nov 2026 09:00",
    )

report = todo.on("2 Nov 2026").one(Task, id="t2")
todo.add(
    report.but(done=True),
    source="me",
    true_from="3 Nov 2026",
    known="4 Nov 2026 10:00",
)


def open_tasks(view: World) -> Facts[Task]:
    """The tasks that are not done on the date of the view."""
    return view.facts(Task).where(lambda task: not task.done)


print(open_tasks(todo.on("4 Nov 2026")))
# [end:example]
print("@@example")
