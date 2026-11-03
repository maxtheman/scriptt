# scriptt

**Make every solved problem AI intuition you own**

![A screen recording of the harness in 6 steps. 1: You type: make a world for my runs, each run has a day, a distance in km and the minutes it took. The code model writes the type Run. 2: You type 3 runs in plain words: 5 km in 31 minutes, 8 km in 50 minutes and 3 km in 17 minutes. The world has 3 runs. 3: You ask how far you have run in total. The decision model plans the answer from World API calls and answers 16 km. 4: You type keep it. A tested function goes into the world and shows under learned by talking. 5: You ask for your total distance in other words. The plan calls the kept function. 6: You ask on which day your pace was fastest, in minutes per km. No call fits, so the decision model and the code model work together and answer 5.667 minutes per km.](https://scriptt.ai/harness-smoke.gif)

*The harness in development, on a world of runs: 1 type, 3 facts and 2 functions, made by talking. The harness is not part of this release.*

Frontier models solve problems well, and they will keep doing so. scriptt is a harness that keeps you in the
loop. It turns each solution into AI intuition. AI intuition is a fast answer from a small local model. You take it with you from one chat to the next.

Today, each AI starts each task from zero. It spends the same effort to solve a problem again, even when it
solved that problem before.

> **Pre-alpha, version 0.1.0.** Only the world works today: the facts, their types, and the knowledge graph that
> links them. The harness is in development. It is not part of this release. This package, `scriptt`, is the
> world. The harness is the package `world-harness`.

## The goal

The goal is a stand-alone harness for programmers. The harness will do 3 things.

1. **It puts agent attention first.** It gives the attention of the agent to the parts of a task that need it.
2. **It breaks each task into small parts.** System One models do this step. A System One model is a decision
   model. It gives typed answers with probabilities in 1 pass, without generating text
   ([TypeSafe, 2026](https://typesafe.ai/blog/introducing-system-one-models-and-jev), [Cloudflare Clef, 2026](https://blog.cloudflare.com/clef-decision-models/)).
   Cloudflare also has a System One model that extracts fields from text ([Clairic, 2026](https://blog.cloudflare.com/clairic-extraction-model)).
3. **It learns your domain as you use it.** Each thing that it learns becomes a fact or a function in the world,
   instead of a line in a chat or a prompt.

| What you get | How the harness gives it |
|---|---|
| You get back into the flow of programming. | The harness does the small parts. You stay on the code. |
| You understand what each model does, and why. | Each step and its cause are facts in the world. You can read each fact and correct it. |
| You pay for fewer tokens. | A solved problem becomes reusable scaffolding: types and functions in the world. No model solves it again. |
| Lower-cost and local models can do the work. | Each part of a task is small. A small model can do a small part. |

## The approach

The harness will turn each problem that a frontier model solves into AI intuition. A small local model then
gives the same answer fast, at low cost, each time.

1. A frontier model solves a problem 1 time. The harness keeps the solution as facts and functions in the world.
2. A small local model learns the answer. The small model is a System One model, named after the fast System 1 ([Kahneman, 2011](https://en.wikipedia.org/wiki/Thinking,_Fast_and_Slow)).
3. The next time, the small model answers. The frontier model works only on the parts that are new.

| Local System One model | Machine | Measured time |
|---|---|---|
| [d1-2B](https://huggingface.co/LiquidAI/d1-2B) | Apple M4 Pro, MLX fp16 | 89 ms for 1 question. 369 ms for 16 questions in 1 pass. |
| [d1-Omni-2B](https://huggingface.co/LiquidAI/d1-Omni-2B) | Apple M4 Pro, MLX fp16 | 88 ms for 1 question. 379 ms for 16 questions in 1 pass. |

Each time is the median of 20 calls to the local CoreAI service on an Apple M4 Pro, measured on 3 Nov 2026.
The time includes the HTTP call.

## The world works today

A world keeps what the harness learns as an asset that you own. You can read, test and keep it when you change
the AI model. It has 3 parts.

| Part | What it is | In a to-do app |
|---|---|---|
| fact | 1 statement with its source and its dates. | The task "Send the report" is done from 3 Nov. |
| type | The fields of 1 kind of fact. A reference links a fact to a different fact. | A task has an id, a title and a done flag. |
| function | A Python function in your code that reads a view of the facts and gives an answer. | The open tasks on a date. |

The world keeps the types and the facts in a log. The references link the facts into a knowledge graph. Your
functions are Python code next to the world.

## Example

```python
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
print(open_tasks(todo.on("3 Nov 2026").known("3 Nov 2026 18:00")))
```

The example prints:

```text
id  title        done
t1  Buy milk     no
t3  Book a room  no
id  title            done
t1  Buy milk         no
t2  Send the report  no
t3  Book a room      no
```

The report is done from 3 Nov. Thus on 4 Nov the world has 2 open tasks. You wrote down the done report at
10:00 on 4 Nov. Thus at 18:00 on 3 Nov you knew of 3 open tasks.

## What it gives you

- A type is a Python class. A field marked `Key` names the thing.
- Each `add` writes 1 entry at the end of a log. The log never changes an entry.
- `on(date)` gives the facts that are true on a date. `known(time)` gives what you knew at a time.
- The verbs `where`, `arrange`, `count_by`, `group_by` and `join` work on the facts of a view.
- A goal is a rule and the number of facts that must agree with it.
- `say` writes a sentence from a Python t-string.
- `sql` runs a DuckDB query on the facts of a view.
- The package `scriptt-charts` draws the results as Vega-Lite, Altair, HTML or a table.

## Install

`scriptt` needs Python 3.14 or later. It is not on PyPI yet. Clone
[github.com/maxtheman/scriptt](https://github.com/maxtheman/scriptt), then add it to your project:

```bash
git clone https://github.com/maxtheman/scriptt
uv add ./scriptt
```

## Docs

The docs are at <https://scriptt.ai/docs/>.

- [Quickstart](https://scriptt.ai/docs/quickstart/): 1 type, 3 tasks, 7 steps.
- [Tutorial: a to-do app](https://scriptt.ai/docs/tutorial-todo/): lists, due dates, mistakes, rules and
  functions.
- [What was true, and what you knew](https://scriptt.ai/docs/time-travel/): the 2 dates of each fact.
- [API reference](https://scriptt.ai/docs/reference/): every call with its arguments and an example.

## Develop

The workspace uses [uv](https://docs.astral.sh/uv/) and [mise](https://mise.jdx.dev/).

```bash
mise install && mise run sync
```

| Task | What it does |
|---|---|
| `mise run check` | Runs ruff and pyright. |
| `mise run test` | Runs the example in each docstring and in this README. |
| `mise run docs` | Runs every example, then builds the docs site into `site/`. |
| `mise run build` | Builds the wheel and the source archive of each package into `dist/`. |

[RELEASING.md](RELEASING.md) gives the steps to release a version. [CHANGELOG.md](CHANGELOG.md) gives the
changes.
