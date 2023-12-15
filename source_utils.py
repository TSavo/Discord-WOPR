import inspect
import dataclasses
from types import NoneType

from typing import Optional, Type, Any, Set, List, Dict, Tuple, ForwardRef
import typing


def unwrap_type(t: Type) -> Type:
    """
    Unwrap a type by recursively following any type aliases until a concrete type is reached.
    """
    if isinstance(t, ForwardRef):
        return t.__forward_arg__
    if hasattr(t, "__origin__"):
        if t.__origin__ in (list, List):
            return List[unwrap_type(t.__args__[0])]
        elif t.__origin__ in (dict, Dict):
            return Dict[unwrap_type(t.__args__[0]), unwrap_type(t.__args__[1])]
        elif t.__origin__ in (set, Set):
            return Set[unwrap_type(t.__args__[0])]
        elif t.__origin__ in (tuple, Tuple):
            return type(tuple(unwrap_type(arg) for arg in t.__args__))
    return t

def get_type_from_typehint(typehint : str) -> Type:
    try:
        return unwrap_type(eval(typehint))
    except:
        eval("import " + typehint.split("[")[-1].split("]")[0])
        return unwrap_type(eval(typehint))
    
def get_dependent_classes(t: Type, seen: Set[Type] = None) -> Set[Type]:
    """
    Recursively walk the fields of a type and return a set of all dependent classes.
    """
    if seen is None:
        seen = set()

    t = unwrap_type(t)
    if t in [None, True, False, int, float, str, bytes, bytearray]:
        return set()
    if t in seen:
        return set()

    seen.add(t)

    if dataclasses.is_dataclass(t):

        fields = t.__dataclass_fields__.values()
        type_hints = typing.get_type_hints(t)
        return set.union(seen, *[get_dependent_classes(type_hints[field.name], seen) for field in fields])
    elif hasattr(t, "__args__"):
        seen.remove(t)
        return set.union(seen, *[get_dependent_classes(arg, seen) for arg in t.__args__])
    elif t in [None, NoneType, True, False, bool, int, float, str, bytes, bytearray, list, dict, tuple, set, frozenset]:
        seen.remove(t)
        return set()
    else:
        return set([t])
    
def get_source(my_cls : Type) -> str:
    source = ""
    for x in get_dependent_classes(my_cls):
        source += str(inspect.getsource(x))
    return source
    
import yaml
import dataclasses
from typing import Any, TypeVar, Type, get_type_hints

T = TypeVar('T')

def from_yaml(yaml_str: str, cls: Type[T]) -> T:
    def convert_to_class(data: Any, cls: Type[T]) -> T:
        if dataclasses.is_dataclass(cls):
            type_hints = get_type_hints(cls)
            kwargs = {}
            for field_name, field_type in type_hints.items():
                if field_name in data:
                    field_value = data[field_name]
                    if dataclasses.is_dataclass(field_type) or isinstance(field_type, type):
                        kwargs[field_name] = convert_to_class(field_value, field_type)
                    elif getattr(field_type, "__origin__", None) is dict:
                        kwargs[field_name] = {k: convert_to_class(v, field_type.__args__[1]) for k, v in field_value.items()}
                    elif getattr(field_type, "__origin__", None) is list:
                        kwargs[field_name] = [convert_to_class(item, field_type.__args__[0]) for item in field_value]
                    else:
                        kwargs[field_name] = field_value
            return cls(**kwargs)
        elif isinstance(data, list):
            return [convert_to_class(item, cls.__args__[0]) for item in data]
        else:
            return data

    parsed_data = yaml.safe_load(yaml_str)
    if isinstance(parsed_data, list):
        return [convert_to_class(item, cls) for item in parsed_data]
    return convert_to_class(parsed_data, cls)

