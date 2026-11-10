"""THE WORLD: the whitelist. A message can demand only what is in this file.

- A class is a kind of text. Its docstring is what d1 is asked for: "Which words are <docstring>?"
- NAMED lists the things that exist and have a name. Words that are not here do not point at an existing thing.
- A function is a computation that a message can demand. Its docstring is what d1 is asked:
  "Does the message ask the reader to <docstring>?" Its parameters are the holes that the message must fill.
  The bodies are not written: the reader of the message does the work.

Edit this file to fit your work. The harness reads it again for each message.
"""


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


def explain() -> Explanation:
    """explain something, or say why, how or what"""


def restate(questions: Questions, concepts: Concepts) -> Explanation:
    """restate something in other terms"""


def answer() -> Answer:
    """confirm or deny something, with a yes or a no"""


def implement(questions: Questions) -> Notebook:
    """implement something in the notebook"""


def delete(notebook: Notebook) -> Notebook:
    """delete or get rid of cells of the notebook"""


def rewrite(notebook: Notebook, code: Code) -> Notebook:
    """rewrite the notebook or a cell of it"""


def mock(model: Model) -> Model:
    """mock the d1 model"""


def solve(types: Types, message: Message) -> Code:
    """write or change code"""


def write(message: Message) -> File:
    """write a file"""


def extend(world: World) -> World:
    """add classes or functions to the world"""
