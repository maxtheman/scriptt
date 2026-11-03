"""`diagram` makes a Mermaid class diagram from fact types."""

import types as pytypes
from typing import Any, Literal, TypeAliasType, Union, get_args, get_origin

from ._fact import Fact, Ref


def diagram(*kinds: type[Fact]) -> str:
    """Draw fact types as a Mermaid class diagram. Each type shows its fields. A `+`
    stands before each key field.
    An arrow goes from each `Ref` field to the type it points to. An arrow also goes
    from a subtype to the type it extends.

    Args:
        *kinds: The types to draw. An arrow is drawn only between types that you give.

    Returns:
        The diagram as Mermaid text for a `mermaid` code block or for `marimo.mermaid`.

    Example:
        ```python
        from scriptt.world import Fact, Key, Ref, diagram


        class TodoList(Fact):
            name: Key[str]


        class Task(Fact):
            id: Key[str]
            list: Ref[TodoList]


        print(diagram(TodoList, Task))
        # classDiagram
        #   class TodoList {
        #     +name str
        #   }
        #   ...
        #   Task --> TodoList : list
        ```
    """
    lines = ["classDiagram"]
    pointers = {}
    # resolves a Ref to a type declared later in the file; a Ref that cannot be read
    # draws no arrow
    for kind in kinds:
        try:
            pointers[kind] = kind.refs()
        except TypeError, NameError:
            pointers[kind] = {}
    for kind in kinds:
        lines.append(f"  class {kind.__name__} {{")
        lines += [
            f"    {'+' if name in kind.key_fields() else '-'}{name} "
            f"{_show(info.annotation)}"
            for name, info in kind.model_fields.items()
        ]
        lines.append("  }")
    for kind in kinds:
        lines += [
            f"  {kind.__name__} --> {target.__name__} : {name}"
            for name, target in pointers[kind].items()
            if target in kinds
        ]
        lines += [
            f"  {base.__name__} <|-- {kind.__name__}"
            for base in kind.__bases__
            if base in kinds
        ]
    return "\n".join(lines)


def _show(annotation: Any) -> str:
    """A short name for a field type. The names include:

    - `str`
    - `Status`
    - `date`
    - `str or none`
    - `list of str`
    - `ref to TodoList`
    """
    origin, args = get_origin(annotation), get_args(annotation)
    if origin in (Union, pytypes.UnionType):
        shown = [_show(a) for a in args if a is not type(None)]
        return " or ".join(shown) + (" or none" if type(None) in args else "")
    if origin is Ref:
        return f"ref to {args[0].__name__}"
    if origin is not None and isinstance(origin, TypeAliasType):
        return ("forward " if origin.__name__ == "Forward" else "") + _show(args[0])
    if origin is Literal:
        return " or ".join(repr(a) for a in args)
    if origin is dict:
        return f"map of {_show(args[0])} to {_show(args[1])}"
    if origin in (tuple, list):
        return f"list of {_show(args[0])}"
    return getattr(annotation, "__name__", str(annotation))
