"""THE WORLD: every class that a slot of a text can have, the things that have a name, and the functions between classes.

This file grows as texts are loaded. The docstring of a class is what d1 is asked for.
"""


class Action(str):
    """an action that the reader is told to do"""


class Explanation(str):
    """an explanation that is asked for or given"""


class Answer(str):
    """a yes or a no that is asked for or given"""


class Notebook(str):
    """the notebook, or cells of it"""


class Code(str):
    """code: a program, a function, a lambda, a template"""


class Types(str):
    """types or classes that the code defines"""


class Questions(str):
    """the questions that are sent to d1"""


class Concepts(str):
    """concepts of computer science"""


class Model(str):
    """the d1 model"""


class Message(str):
    """a message, or several messages and replies"""


class World(str):
    """the world: the classes and functions that exist"""


class File(str):
    """a file on disk"""


class Helper(str):
    """another agent that does part of the work"""


CLASSES = [Action, Explanation, Answer, Notebook, Code, Types, Questions, Concepts, Model, Message, World, File, Helper]

# Things in the world that have a name. Words that are not here do not point at an existing thing.
NAMED = {
    Notebook: {"the old cells", "these cells", "this notebook", "this whole notebook", "this version"},
    Code: {"the functions", "t-strings", "t strings", "the template"},
    Types: {"result types", "the type of the result", "demand", "the roles", "classes", "the types"},
    Questions: {"all ten of these"},
    Concepts: {"the computer science concepts"},
    Model: {"d1", "the model", "this model"},
    Message: {"the message", "the messages", "the entire message", "all of my messages to you and your replies"},
    World: {"the world"},
    Helper: {"a sonnet agent"},
}


# Functions of the world. Each goes from classes of the world to a class of the world. The bodies are not written.
def restate(questions: Questions, concepts: Concepts) -> Explanation: ...
def implement(questions: Questions) -> Notebook: ...
def mock(model: Model) -> Model: ...
def delete(notebook: Notebook) -> Notebook: ...
def solve(types: Types, message: Message) -> Code: ...
def rewrite(notebook: Notebook, code: Code) -> Notebook: ...


# The words that name each function.
ACTIONS = {"restate": restate, "implement": implement, "mock": mock, "mock d1": mock, "get rid of": delete, "delete": delete, "solve": solve, "rewrite": rewrite}


def make(cls, words, who):
    """A value of the class for these words, or the class itself when the world has none (a hole)."""
    if cls is Action:
        return ACTIONS.get(words.lower(), cls)
    if who == "assistant":  # a reply supplies what it says
        return cls(words)
    return cls(words) if words.lower() in NAMED.get(cls, ()) else cls


def describe():
    """The world as plain data, for the website and for a reader."""
    import typing

    functions = {}
    for function in dict.fromkeys(ACTIONS.values()):
        hints = typing.get_type_hints(function)
        functions[function.__name__] = {
            "returns": hints.pop("return").__name__,
            "parameters": {name: cls.__name__ for name, cls in hints.items()},
            "words": sorted(words for words, f in ACTIONS.items() if f is function),
        }
    return {
        "classes": {cls.__name__: cls.__doc__ for cls in CLASSES},
        "named": {cls.__name__: sorted(names) for cls, names in NAMED.items()},
        "functions": functions,
    }
