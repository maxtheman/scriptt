---
hide:
  - navigation
---

<div class="hero" markdown>

# scriptt

<p class="tagline">Make every solved problem AI intuition you own</p>

</div>

Frontier models solve problems well, and they will keep doing so. scriptt is a harness that keeps you in the
loop. It turns each solution into AI intuition. AI intuition is a fast answer from a small local model. You take it with you from one chat to the next.

Today, each AI starts each task from zero. It spends the same effort to solve a problem again, even when it
solved that problem before.

!!! warning "Pre-alpha, version 0.1.0"
    Only the world works today: the facts, their types, and the knowledge graph that links them. The harness is
    in development. It is not part of this release. This package, `scriptt`, is the world. The harness is the
    package `world-harness`.

## The goal

The goal is a stand-alone harness for programmers. The harness will do 3 things.

1. **It puts agent attention first.** It gives the attention of the agent to the parts of a task that need it.
2. **It breaks each task into small parts.** **System One models** do this step. A System One model is a
   decision model. It gives typed answers with probabilities in 1 pass, without generating text.
   [The approach](#the-approach) gives their measured times.
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
2. A small local model learns the answer. The small model is a System One model. TypeSafe named this class of
   decision model after the fast **System 1** of Kahneman [^kahneman] [^jev]. The Clef models of Cloudflare
   answer in the same request shape [^clef]. Clairic, also from Cloudflare, is a System One model that extracts
   fields from text [^clairic].
3. The next time, the small model answers. The frontier model works only on the parts that are new.

The table gives the measured times of the System One models that the harness uses.

| Model | Machine | Time |
|---|---|---|
| [d1-2B](https://huggingface.co/LiquidAI/d1-2B) | Apple M4 Pro, MLX fp16 | 89 ms for 1 question. 369 ms for 16 questions in 1 pass. |
| [d1-Omni-2B](https://huggingface.co/LiquidAI/d1-Omni-2B) | Apple M4 Pro, MLX fp16 | 88 ms for 1 question. 379 ms for 16 questions in 1 pass. |

Each time is the median of 20 calls to the local CoreAI service on an Apple M4 Pro, measured on 3 Nov 2026.
The time includes the HTTP call.

[^kahneman]: Daniel Kahneman. [*Thinking, Fast and Slow*](https://en.wikipedia.org/wiki/Thinking,_Fast_and_Slow). Farrar, Straus and Giroux, 2011.
[^jev]: Diogo Almeida. [Introducing System One Models & Jev](https://typesafe.ai/blog/introducing-system-one-models-and-jev). TypeSafe AI blog, 15 Sep 2026.
[^clef]: Michelle Chen, Alex Reneau and Kevin Flansburg. [Introducing Clef: our open-source decision models,
    and new RL fine-tuning platform](https://blog.cloudflare.com/clef-decision-models/). Cloudflare blog, 1 Oct 2026.
[^clairic]: Cloudflare. [Introducing Clairic, a new System One class of extraction models](https://blog.cloudflare.com/clairic-extraction-model). Cloudflare
    blog, 19 Oct 2026.

## The world works today

A **world** keeps what the harness learns as an asset that you own. You can read, test and keep it when you
change the AI model. It has 3 parts.

| Part | What it is | In a to-do app |
|---|---|---|
| fact | 1 statement with its source and its dates. | The task "Send the report" is done from 3 Nov. |
| type | The fields of 1 kind of fact. A reference links a fact to a different fact. | A task has an id, a title and a done flag. |
| function | A Python function in your code that reads a view of the facts and gives an answer. | The open tasks on a date. |

The world keeps the types and the facts in a log. The references link the facts into a **knowledge graph**.
Your functions are Python code next to the world.

| Part | Status in 0.1.0 |
|---|---|
| Facts, types, references and views | works |
| [What was true, and what you knew](time-travel.md) | works |
| Goals, sentences from t-strings, SQL | works |
| Charts (`scriptt-charts`) | works |
| The harness: agent attention, task breakdown, domain learning | in development, not in this release |

## A world in 1 example

The code makes a to-do world with 3 tasks. Then it marks 1 task done and asks which tasks are open on 4 Nov.

--8<-- "docs/examples/home.py:example"

--8<-- "output:home/example"

The report is done from 3 Nov. Thus on 4 Nov the world has 2 open tasks. The
[quickstart](quickstart.md) explains each line.

<div class="grid cards" markdown>

-   **[Quickstart](quickstart.md)**

    1 type, 3 tasks, 7 steps.

-   **[Tutorial: a to-do app](tutorial-todo.md)**

    1 world that grows from 1 type to lists, due dates, rules and functions, in 14 steps.

-   **[What was true, and what you knew](time-travel.md)**

    The 2 dates of each fact, and the 4 answers that they give.

-   **[Mental model](mental-model.md)**

    The words of the library, and 4 questions before you start.

-   **[API reference](reference/index.md)**

    Every call, with its arguments and an example from the to-do app.

-   **[Changelog](changelog.md)**

    The changes in each version.

</div>

## What the library gives you

| Feature | Description |
|---|---|
| Types | A type is a Python class. A field marked `Key` names the thing. Your editor completes the field names. |
| A log of facts | Each `add` writes 1 entry at the end of the log. The log never changes an entry. |
| Views | `on(date)` gives the facts that are true on a date. A function reads a view and gives an answer. |
| [What was true, and what you knew](time-travel.md) | `known(time)` gives the facts that you had at a time. You can see an old answer again and find the cause of a change. |
| Methods of the facts | `where`, `arrange`, `count_by`, `group_by` and `join` give new tables from the facts of a view. |
| Goals | A goal is a rule and the number of facts that must agree with it. Example: every open task has a due date. `check` gives the result, and `result.failing` gives the facts that do not agree. |
| References | A field marked `Ref` contains the key of a different fact. `problems` finds each reference to a fact that does not exist. |
| Sentences | `say` writes a sentence from a Python t-string, with each fact named by its type and key. Example: "task t2". |
| SQL | `sql` runs 1 DuckDB query on the facts of a view. |
| Charts | The package `scriptt-charts` draws your facts as Vega-Lite, Altair, HTML or a table. Example: a bar for each list with its count of open tasks. |

## Install

`scriptt` needs Python 3.14 or later. It is not on PyPI yet. Clone
[github.com/maxtheman/scriptt](https://github.com/maxtheman/scriptt), then add it to your project.

```bash
git clone https://github.com/maxtheman/scriptt
uv add ./scriptt
```

| Package | Contents | In this release |
|---|---|---|
| `scriptt` | The world: the log, the views, goals, `say` and `sql`. Import it as `scriptt.world`. | yes |
| `scriptt-charts` | Charts of your facts. Import it as `scriptt.charts`. | yes |
| `world-harness` | The harness that grows a world as you talk to it. | no |
