"""The page "What was true, and what you knew": 1 task done on 3 Nov and written down
on 4 Nov, asked about on 4 dates and times."""

# [start:setup]
import datetime as dt

from scriptt.world import Fact, Facts, Key, Row, World, say


class Task(Fact):
    id: Key[str]
    title: str
    done: bool = False


todo = World.new(Task)
report = Task(id="t2", title="Send the report")
todo.add(report, source="me", true_from="2 Nov 2026", known="2 Nov 2026 09:00")
todo.add(
    report.but(done=True),
    source="me",
    true_from="3 Nov 2026",
    known="4 Nov 2026 10:00",
)
# [end:setup]

# [start:grid]
answers = []
for on, known in [
    ("2 Nov 2026", "2 Nov 2026 18:00"),
    ("3 Nov 2026", "3 Nov 2026 18:00"),
    ("3 Nov 2026", "4 Nov 2026 18:00"),
    ("4 Nov 2026", "4 Nov 2026 18:00"),
]:
    task = todo.on(on).known(known).one(Task, id="t2")
    answers.append(Row(on=on, known=known, done=task.done))
print(Facts(answers))
# [end:grid]
print("@@grid")

# [start:history]
print(
    todo.history(report).map(
        lambda entry: Row(
            done=entry.body["done"],
            true_from=entry.true_from,
            known=entry.known,
        )
    )
)
# [end:history]
print("@@history")

# [start:timeline]
events: list[tuple[dt.datetime, str, str]] = []
for entry in todo.history(report):
    state = "done" if entry.body["done"] else "open"
    if entry.true_from:
        start = dt.datetime.combine(entry.true_from, dt.time())
        events.append((start, say(t"{entry.true_from:%-d %b}"), f"{state} is true"))
    when = say(t"{entry.known:%-d %b %Hh%M}")
    events.append((entry.known.replace(tzinfo=None), when, f"you write down {state}"))
print("timeline")
for _, label, text in sorted(events):
    print(f"    {label} : {text}")
# [end:timeline]
print("@@timeline")
