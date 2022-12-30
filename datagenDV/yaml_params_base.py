"""
MIT License

Copyright (c) Microsoft Corporation.

Author: jonathan.george@microsoft.com
"""

from ruamel.yaml.comments import CommentedMap
from ruamel.yaml import SafeConstructor
from copy import deepcopy
from enum import Enum
import dataclasses
import traceback
from datagenDV import ParamsBase


def field(default, dir='in_out', **kwargs):
  """Wrapper for dataclasses.field(). Dir sets the direction for loading and unloading"""
  assert dir in ('in_out', 'in', 'out'), f"Invalid dir '{dir}'"
  if dir=='in':
    return in_only_field(default, **kwargs)
  elif dir=='out':
    return out_only_field(default, **kwargs)
  elif dir=='in_out':
    return yml_field(default, **kwargs)


def yml_field(default, **kwargs):
    """In/out yaml parameter. Loads from yaml, outputs to yaml"""
    if callable(default):
        return dataclasses.field(init=True, default_factory=default, **kwargs)
    else:
        check_immutable(default)
        return dataclasses.field(init=True, default=default, **kwargs)

#out only yaml parameter.
def out_only_field(default, **kwargs):
    """out only yaml parameter. Outputs to yaml when to_yaml is called. Excluded from constructor"""
    if callable(default):
        return dataclasses.field(init=False, default_factory=default, **kwargs)
    else:
        check_immutable(default)
        return dataclasses.field(init=False, default=default, **kwargs)

#in only yaml parameter.
def in_only_field(default, **kwargs):
    """in only yaml parameter. Excluded when to_yaml is called"""
    if callable(default):
        return dataclasses.field(init=True, default_factory=default, metadata={'yml_dump_excluded':True}, **kwargs)
    else:
        check_immutable(default)
        return dataclasses.field(init=True, default=default, metadata={'yml_dump_excluded':True}, **kwargs)

def check_immutable(init_val):
    if not isinstance(init_val, (str, int, bool, float, tuple, Enum)) and init_val is not None:
        print(f"WARNING: passed in a mutable init_val of {init_val} with type {type(init_val)}.")
        print("  Python init values are shared on all instances leading to unintended value sharing")
        print("  Suggested fix is passing in a factory function to create a new instance instead")
        print(f"    default=lambda:{init_val}")
        print(traceback.print_stack())

def convert_enum(x):
    return x.name if isinstance(x, Enum ) else x

class YAMLParamsBase(ParamsBase):
    """
    Base command class for yaml loaded classes
    Using Python Dataclasses is recommended

    """
    @classmethod
    def to_yaml(cls,dumper,data):
        new_data = deepcopy(data)
        #Get the varibables of object without built in functions
        vars_dir = [x for x in vars(new_data)]
        if dataclasses.is_dataclass(cls):
            yml_dump_excluded_fields = [field.name for field in dataclasses.fields(cls) if field.metadata.get('yml_dump_excluded',False)]
        else:
            yml_dump_excluded_fields = []

        for var_name in vars_dir:
            var_val = new_data.__dict__[var_name]
            #Do not dump private variables or None or field is _yml_in_field
            if var_val == None or var_name.startswith('_') or  var_name in yml_dump_excluded_fields:
                del new_data.__dict__[var_name]
            elif isinstance(var_val, list):
                if len(var_val) == 0: #Do not dump if it is an empty list
                    del new_data.__dict__[var_name]
                #handle lists of enums
                new_data.__dict__[var_name] = list(map( convert_enum, var_val))
            else:
                #Convert any enums
                new_data.__dict__[var_name] = convert_enum(var_val)
        #The ! tag gets dropped by default due to issues with further scripts
        yaml_tag = '!'#u'!' + cls.__name__
        return dumper.represent_yaml_object(yaml_tag, new_data, cls)

    @classmethod
    def from_yaml(cls, loader, node):
        if not isinstance(node, dict):
            node  = SafeConstructor.construct_mapping(loader, node, deep=True)
        node.pop("DatagenClass", None)
        return cls( **dict(node) )



