"""Small dataclass serializer and type checks, with no coercion or dependencies."""
from dataclasses import fields, is_dataclass
import math
from types import UnionType
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints


def matches(value, annotation):
    if annotation is Any:
        return True
    origin, args = get_origin(annotation), get_args(annotation)
    if origin in (Union, UnionType):
        return any(matches(value, member) for member in args)
    if origin is Literal:
        return any(type(value) is type(member) and value == member for member in args)
    if origin is list:
        return isinstance(value, list) and all(matches(item, args[0]) for item in value)
    if origin is dict:
        return isinstance(value, dict) and all(matches(key, args[0]) and matches(item, args[1])
                                              for key, item in value.items())
    if annotation in (int, bool, str, type(None)):
        return type(value) is annotation
    if annotation is float:
        return type(value) in (int, float) and math.isfinite(value)
    return isinstance(value, annotation)


def serialize(value):
    if is_dataclass(value):
        return {field.name: serialize(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, dict):
        return {key: serialize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [serialize(item) for item in value]
    return value


class Model:
    def __post_init__(self):
        hints = get_type_hints(type(self))
        for field in fields(self):
            if not matches(getattr(self, field.name), hints[field.name]):
                raise ValueError(f"Invalid {type(self).__name__}.{field.name}")

    def to_dict(self):
        return serialize(self)
