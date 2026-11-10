"""From a text to a typed template. Standard library only, Python 3.14 or later (t-string templates).

    typed, log = read(text, who, d1)     the two loops
    result(typed)                        the slots, the holes, the words with no type

`d1` is any function (state, cls) -> {"found": bool, "span": [start, end]}. See d1.py.
"""

import typing
from string.templatelib import Interpolation, Template

import world

MAX_READS = 8  # for one class in one text; a real model can return the same range again and again


def prompt(cls):
    # The d1-2B cards word a `text` question as one short question. The model adds its own last line:
    # "Read the text from the state, or nothing if it is absent." One question returns one range.
    return f"Which words are {cls.__doc__}?"


def read(text, who, d1):
    state, slots, log = text, [], []
    for cls in world.CLASSES:  # one loop for each class of the world
        for _ in range(MAX_READS):  # ask again until d1 finds no more
            answer = d1(state, cls)
            log.append({"class": cls.__name__, "prompt": prompt(cls), "found": bool(answer.get("found")), "span": answer.get("span")})
            start, end = answer.get("span") or (0, 0)
            if not answer.get("found") or not 0 <= start < end <= len(text) or not state[start:end].strip("_ \n"):
                break
            words = text[start:end]
            slots.append((start, end, words, world.make(cls, words, who), cls))
            state = state[:start] + "_" * (end - start) + state[end:]  # d1 does not see these words again
    parts, at = [], 0
    for start, end, words, value, cls in sorted(slots, key=lambda slot: slot[0]):
        if start < at:  # a real model can return a range that overlaps an earlier one: skip it
            continue
        parts += [text[at:start], Interpolation(value, cls.__name__, None, words)]
        at = end
    return Template(*parts, text[at:]), log


def result(typed):
    """What the program reads from the template: each slot, the classes of the holes, the words with no type."""
    slots, holes, at = [], [], 0
    for part in typed:
        if isinstance(part, str):
            at += len(part)
            continue
        words = part.format_spec
        if isinstance(part.value, type):  # a class with no value: a hole
            state = "hole"
            holes.append(part.value.__name__)
        elif callable(part.value):  # a function of the world: its result is wanted
            state = "action " + part.value.__name__
            holes.append(typing.get_type_hints(part.value)["return"].__name__)
        else:
            state = "given"
        slots.append({"start": at, "end": at + len(words), "words": words, "class": part.expression, "state": state})
        if state.startswith("action"):
            slots[-1]["wants"] = holes[-1]
        at += len(words)
    return {"slots": slots, "holes": sorted(holes), "not typed": [s for s in typed.strings if s.strip()]}
