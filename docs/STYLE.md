# Writing style and terms

The pages use Simplified Technical English (ASD-STE100): 1 idea in each sentence, 25 words or fewer, the present
tense, the active voice, no idioms, no contractions, and 1 word for 1 thing. `docs/build.py` measures each page and
stops the build if fewer than 80% of its sentences have 25 words or fewer, or if a page uses a word from the last
column below.

| Term | Meaning | Do not use |
|---|---|---|
| world | The types, the log and the functions of 1 domain. | knowledge base |
| type | The fields of 1 kind of fact. A Python class that inherits from `Fact`. | schema |
| fact | 1 typed statement with its source and its dates. It cannot change. | item, entry (for a fact) |
| function | A Python function that reads a view and gives an answer. | skill, tool |
| task | 1 thing to do in the to-do app of the examples. | todo item |
| log | Every fact that you added, in the sequence that you added them. | history (for the log) |
| entry | 1 row of the log: a fact added, ended, retracted, joined or renamed. | record |
| view | The facts true on 1 date, of those known by 1 time. | snapshot |
| true from | The date from which a fact is true. | valid time |
| known | The time at which you got a fact. | |
| version | A later fact with the same key. In `scriptt.world.versions` it is also 1 git commit. | revision |
| AI model | A program such as Claude that writes text. | LLM |

## Words of the docstrings of scriptt-charts

In the docstrings of `scriptt-charts`, an *item* is 1 thing that a chart draws: a fact, a row or any other value. The
pages do not use the word.

