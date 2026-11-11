"""The closed type system of a world.

A world.py file defines every type that the search can use:

* A base type is a Python type such as ``str``, ``int`` or ``pathlib.Path``.
* A brand is a ``typing.NewType``. It gives an existing type a new nominal
  identity, so ``Asked`` and ``Written`` are different types although both wrap
  ``Words``.
* A sum type is one of several alternatives: an ``Enum`` (each member is an
  alternative with no fields) or a union ``A | B``.
* A product type is several values at once: a dataclass, a ``NamedTuple`` or a
  ``TypedDict``.
* A type constructor takes a type and gives a type: ``Many``, ``Maybe`` and
  ``Later`` (their meanings are in ``MANY``, ``MAYBE`` and ``LATER``;
  ``Later`` is no runtime future).
* A function has typed parameters and a typed result.

This module builds those types from the annotations of world.py, checks the
kind of every type expression, and decides subtyping. It works on types only:
scriptt16.py handles the text of a message.
"""

import annotationlib
import ast
import dataclasses
import enum
import hashlib
import inspect
import json
import pathlib
import types as python_types
import typing


# ---- Kinds ------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Star:
    """The kind of a type that has values, such as ``Surface`` or ``Many[Surface]``."""


@dataclasses.dataclass(frozen=True)
class Arrow:
    """The kind of a type constructor.

    Attributes:
        argument: The kind that the constructor takes.
        result: The kind that the constructor gives.
    """

    argument: "Kind"
    result: "Kind"


type Kind = Star | Arrow


# ---- Types ------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Base:
    """A Python type that the world uses as it is.

    Attributes:
        name: The name of the type, such as "int" or "Path".
        python: The Python type.
    """

    name: str
    python: type


@dataclasses.dataclass(frozen=True)
class Brand:
    """A nominal type over an existing type, defined with ``typing.NewType``.

    Attributes:
        name: The name of the brand.
        of: The type that the brand wraps. A brand is a subtype of it.
    """

    name: str
    of: "Type"


@dataclasses.dataclass(frozen=True)
class Member:
    """One alternative of a sum type that has no fields: a member of an Enum.

    Attributes:
        name: The name of the member.
        words: The text of the member: the words that name it in a message.
        type: The type of that text.
        python: The Enum member.
    """

    name: str
    words: str
    type: "Type"
    python: enum.Enum = dataclasses.field(compare=False)


@dataclasses.dataclass(frozen=True)
class Sum:
    """A type whose value is one of several alternatives.

    Attributes:
        name: The name of the type.
        alternatives: The alternatives: members with no fields, or types.
        describes: The docstring of the type.
    """

    name: str
    alternatives: tuple["Member | Type", ...]
    describes: str = ""


@dataclasses.dataclass(frozen=True)
class Product:
    """A type whose value has one value for each field.

    Attributes:
        name: The name of the type.
        fields: The name and the type of each field.
        describes: The docstring of the type.
    """

    name: str
    fields: tuple[tuple[str, "Type"], ...]
    describes: str = ""


@dataclasses.dataclass(frozen=True)
class Constructor:
    """A type constructor: it takes a type and gives a type.

    Attributes:
        name: The name of the constructor.
        kind: The kind of the constructor.
        describes: What a type that the constructor gives states about its values.
    """

    name: str
    kind: Arrow
    describes: str


@dataclasses.dataclass(frozen=True)
class Applied:
    """A type constructor applied to a type, such as ``Many[Surface]``.

    Attributes:
        constructor: The constructor.
        argument: The type that the constructor is applied to.
    """

    constructor: Constructor
    argument: "Type"


type Type = Base | Brand | Sum | Product | Applied

MANY = Constructor("Many", Arrow(Star(), Star()), "a collection of values in one reading; zero values is an explicit empty collection, not a hole")
MAYBE = Constructor("Maybe", Arrow(Star(), Star()), "deliberate optionality: one value, or a deliberate absence that d1 answered")
LATER = Constructor("Later", Arrow(Star(), Star()), "a value that depends on work not yet done: an unavailable dependency, not a scheduled computation")
CONSTRUCTORS: dict[str, Constructor] = {constructor.name: constructor for constructor in (MANY, MAYBE, LATER)}

MAXIMUM_OPTIONS = 32
"""The largest number of options that d1 accepts in one choice."""


@dataclasses.dataclass(frozen=True)
class Function:
    """A function of the world.

    Attributes:
        name: The name of the function.
        asks: The docstring of the function. d1 reads it as an option.
        parameters: The name and the type of each parameter.
        result: The type of the result.
        line: The line of world.py where the function starts.
    """

    name: str
    asks: str
    parameters: tuple[tuple[str, Type], ...]
    result: Type
    line: int


@dataclasses.dataclass(frozen=True)
class World:
    """The type system of a folder, loaded once from world.py.

    Attributes:
        types: Every type of the world, by name.
        functions: The functions that loaded with no fault, by name.
        faults: Each fault of world.py, as (declaration, rule, text with its place).
            The rule is "kind", "type", "missing" or "name". A world with a fault is
            rejected: the search runs only on a world with no fault.
        folder: The folder that holds the paths that a message names.
    """

    types: dict[str, Type]
    functions: dict[str, Function]
    faults: list[tuple[str, str, str]]
    folder: pathlib.Path


def show(expression: Type | Constructor | Member | Kind) -> str:
    """Returns a type, a constructor, a member or a kind as text."""
    match expression:
        case Star():
            return "*"
        case Arrow(argument, result):
            return f"{show(argument)} -> {show(result)}"
        case Applied(constructor, argument):
            return f"{constructor.name}[{show(argument)}]"
        case Sum(name="", alternatives=alternatives):
            return " | ".join(show(alternative) for alternative in alternatives)
    return expression.name


def kind_of(expression: Type | Constructor) -> Kind:
    """Returns the kind of a type or of a type constructor.

    Args:
        expression: A type or a type constructor.

    Returns:
        ``Star`` for a type. The arrow kind of a constructor. For an applied
        constructor, the kind that the constructor gives.

    Raises:
        TypeError: If a constructor is applied to something whose kind differs
            from the kind that the constructor takes.
    """
    match expression:
        case Constructor(kind=kind):
            return kind
        case Applied(constructor, argument):
            if kind_of(argument) != constructor.kind.argument:
                raise TypeError(f"{constructor.name} takes a type of kind {show(constructor.kind.argument)}, and {show(argument)} has kind {show(kind_of(argument))}")
            return constructor.kind.result
    return Star()


def is_subtype(given: Type, wanted: Type) -> bool:
    """Decides whether a value of one type can stand where another type is wanted.

    Args:
        given: The type of the value.
        wanted: The type of the place.

    Returns:
        True if the types are equal, if ``given`` is a brand over a subtype of
        ``wanted``, if ``wanted`` is a sum with an alternative that ``given`` is
        a subtype of, or if both apply the same constructor to types that are
        in this relation.
    """
    if given == wanted:
        return True
    if isinstance(wanted, Sum) and any(not isinstance(alternative, Member) and is_subtype(given, alternative) for alternative in wanted.alternatives):
        return True
    if isinstance(given, Brand):
        return is_subtype(given.of, wanted)
    if isinstance(given, Applied) and isinstance(wanted, Applied) and given.constructor == wanted.constructor:
        return is_subtype(given.argument, wanted.argument)
    return False


def tree(expression: Type | Member) -> dict:
    """Converts a type to data that keeps its structure, for the log and for a page.

    Args:
        expression: A type, or a member of a sum type.

    Returns:
        A nested dict. An applied constructor has its argument inside it, a sum
        has its alternatives, a product has its fields, and a brand has the
        type that it wraps.
    """
    match expression:
        case Applied(constructor, argument):
            return {"constructor": constructor.name, "of": tree(argument)}
        case Sum(name, alternatives):
            return {"sum": name, "alternatives": [tree(alternative) for alternative in alternatives]}
        case Product(name, fields):
            return {"product": name, "fields": {field: tree(field_type) for field, field_type in fields}}
        case Brand(name, wrapped):
            return {"brand": name, "of": tree(wrapped)}
        case Member(name, words, kind):
            return {"member": name, "words": words, "type": tree(kind)}
    return {"base": expression.name}


def load(module: object, folder: pathlib.Path | None = None) -> World:
    """Loads the type system of a folder from its world.py module.

    Reads the definitions in the order of the file. Reads each annotation as
    text, so a world can name ``Many``, ``Maybe`` and ``Later`` with no import.

    Args:
        module: The imported world.py module.
        folder: The folder that holds the paths that a message names. Defaults
            to the folder above the folder of world.py.

    Returns:
        The world. Each fault of world.py is listed in ``World.faults`` with its
        place, and the definition that has the fault is left out.
    """
    file_name = pathlib.Path(module.__file__).name
    types: dict[str, Type] = {}
    functions: dict[str, Function] = {}
    faults: list[tuple[str, str, str]] = []
    rules = {TypeError: "kind", NameError: "name", KeyError: "name", SyntaxError: "type", ValueError: "type"}
    text_format = annotationlib.Format.STRING

    def named(python_type: object) -> Type:
        """Returns the type of a Python type that an annotation names."""
        name = getattr(python_type, "__name__", repr(python_type))
        if name not in types:
            if not isinstance(python_type, type):
                raise NameError(f"{name} is no type of this world")
            types[name] = Base(name, python_type)
        return types[name]

    def built(node: ast.expr) -> Type | Constructor:
        """Builds the type or the constructor that one node of an annotation states."""
        match node:
            case ast.Constant(value=None):
                return named(type(None))
            case ast.BinOp(op=ast.BitOr(), left=left, right=ast.Constant(value=None)):
                return applied(MAYBE, built(left))
            case ast.BinOp(op=ast.BitOr()):
                alternatives: list[Type] = []
                for side in (node.left, node.right):
                    part = built(side)
                    if kind_of(part) != Star():
                        raise TypeError(f"{show(part)} has kind {show(kind_of(part))}, and an alternative of a union needs kind *")
                    alternatives += part.alternatives if isinstance(part, Sum) and not part.name else [part]
                return Sum("", tuple(alternatives))
            case ast.Subscript(value=head, slice=argument):
                constructor = built(head)
                if not isinstance(constructor, Constructor):
                    raise TypeError(f"{show(constructor)} has kind * and takes no argument")
                return applied(constructor, built(argument))
            case ast.Name(id=name) if name in CONSTRUCTORS:
                return CONSTRUCTORS[name]
            case ast.Name(id=name) if name in types:
                return types[name]
            case ast.Name() | ast.Attribute():
                return named(eval(compile(ast.Expression(node), file_name, "eval"), vars(module)))
        raise SyntaxError(f"no type expression: {ast.unparse(node)}")

    def applied(constructor: Constructor, argument: Type | Constructor) -> Applied:
        made = Applied(constructor, argument)
        kind_of(made)
        return made

    def type_of(annotation: str) -> Type:
        """Builds the type of an annotation and checks that its kind is ``Star``."""
        made = built(ast.parse(annotation, mode="eval").body)
        if kind_of(made) != Star():
            raise TypeError(f"{show(made)} has kind {show(kind_of(made))} and needs an argument")
        return made

    for name, value in vars(module).items():
        place = f"{file_name}:{getattr(value, '__firstlineno__', '')} {name}".replace(": ", " ")
        is_own_class = isinstance(value, type) and value.__module__ == module.__name__
        is_brand = hasattr(value, "__supertype__")
        is_alias = isinstance(value, typing.TypeAliasType)
        is_function = inspect.isfunction(value) and value.__module__ == module.__name__
        if not (is_own_class or is_brand or is_alias or is_function):
            continue
        if name in CONSTRUCTORS:
            faults.append((name, "name", f"{place}: the type system already has a constructor with this name"))
            continue
        try:
            if is_brand:
                wrapped = value.__supertype__
                types[name] = Brand(name, types[wrapped.__name__] if hasattr(wrapped, "__supertype__") else named(wrapped))
            elif is_alias:
                made = type_of(annotationlib.call_evaluate_function(value.evaluate_value, text_format))
                types[name] = dataclasses.replace(made, name=name) if isinstance(made, Sum) else made
            elif is_own_class and isinstance(value, enum.EnumType):
                annotations = annotationlib.get_annotations(value, format=text_format)
                untyped = [member for member in value if member.name not in annotations]
                if untyped:
                    faults += [(name, "missing", f"{place}.{member.name}: no type for the text {member.value!r}") for member in untyped]
                    continue
                members = tuple(Member(member.name, member.value, type_of(annotations[member.name]), member) for member in value)
                types[name] = Sum(name, members, value.__doc__ or "")
            elif is_own_class:
                annotations = annotationlib.get_annotations(value, format=text_format)
                if name in annotations.values():
                    raise ValueError("this type contains itself")
                types[name] = Product(name, tuple((field, type_of(annotation)) for field, annotation in annotations.items()), value.__doc__ or "")
            else:
                place = f"{file_name}:{value.__code__.co_firstlineno} {name}"
                annotations = annotationlib.get_annotations(value, format=text_format)
                parameters = inspect.signature(value, annotation_format=text_format).parameters
                untyped = [parameter for parameter in [*parameters, "return"] if parameter not in annotations]
                faults += [(name, "missing", f"{place}: no type for {parameter}") for parameter in untyped]
                if not value.__doc__:
                    faults.append((name, "missing", f"{place}: no docstring"))
                if untyped or not value.__doc__:
                    continue
                typed = tuple((parameter, type_of(annotations[parameter])) for parameter in parameters)
                functions[name] = Function(name, value.__doc__, typed, type_of(annotations["return"]), value.__code__.co_firstlineno)
        except tuple(rules) as fault:
            faults.append((name, next(rule for kind, rule in rules.items() if isinstance(fault, kind)), f"{place}: {fault}"))
    if len(functions) + 2 > MAXIMUM_OPTIONS:
        faults.append((file_name, "name", f"{file_name}: {len(functions)} functions, and d1 chooses among at most {MAXIMUM_OPTIONS - 2} and its 2 answers that are no function"))
    return World(types, functions, faults, folder or pathlib.Path(module.__file__).resolve().parent.parent)


def loads(source: str, folder: pathlib.Path) -> World:
    """Loads a world from the text of a world.py file, with ``folder`` as the folder of its paths."""
    module = python_types.ModuleType("world")
    module.__file__ = str(folder / "world.py")
    exec(compile(source, "world.py", "exec"), vars(module))
    return load(module, folder)


def identity(world: World) -> str:
    """Returns a hash of the declarations of a world: its types and its functions, with their docstrings.

    A saved reading names the world it was read against by this hash.
    """
    declared = [[name, tree(one)] for name, one in world.types.items()]
    declared += [[f.name, f.asks, [[name, tree(one)] for name, one in f.parameters], tree(f.result)] for f in world.functions.values()]
    return hashlib.sha256(json.dumps(declared).encode()).hexdigest()[:16]


def world_record(world: World) -> dict:
    """Converts a world to data that JSON can hold: its identity, each type with its kind and docstring, each constructor, each function. A record names its world by the identity."""
    return {"identity": identity(world),
            "types": {name: tree(one) | {"kind": show(kind_of(one)), "describes": getattr(one, "describes", "")} for name, one in world.types.items()},
            "constructors": {name: {"kind": show(one.kind), "describes": one.describes} for name, one in CONSTRUCTORS.items()},
            "functions": {f.name: {"asks": f.asks, "parameters": [[name, tree(one)] for name, one in f.parameters], "result": tree(f.result)} for f in world.functions.values()}}
