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
from datagenDV.ctypes_helper import python2ctype, ctype2python


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

class YAMLParamsBase():
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

    #################################
    #Header file generation functions
    #################################

    @classmethod
    def generate_hfields(cls, clist_info_lookup={}):
        """
        Called before passing the struct class to DatagenBase.write_outputs()
        clist_info_lookup is a dictionary lookup between the field name a tuple of the type and maximum array size
        """
        assert(dataclasses.is_dataclass(cls)), "This function requires the subclass usees dataclass fields to provide typehints"
        if '_hfields_' not in vars(cls):
            cls._hfields_ = []
        for field in dataclasses.fields(cls):
            #Check if field is already defined in hfields, is private or _yml_in_field subclass
            if field.name in [hfield[0] for hfield in cls._hfields_] or \
                    field.name.startswith('_') or field.metadata.get('yml_dump_excluded',False):
                continue
            if issubclass(field.type, list):
                assert(field.name in clist_info_lookup), \
                    f"{field.name} not found in c list lookup. Please setup clist_info_lookup for this field before calling generate_hfields()"
                list_type, list_size = clist_info_lookup[field.name]
                if issubclass(list_type,Enum): #custom enum handling for ctypes
                    cls._hfields_.append( (field.name, list_type, list_size) )
                else:
                    list_ctype = cls.ctype_field_lookup(list_type)
                    cls._hfields_.append( (field.name, list_ctype * list_size) )
            else:
                ctype = cls.ctype_field_lookup(field.type)
                cls._hfields_.append( (field.name, ctype) )


    @classmethod
    def ctype_field_lookup(cls, field_type):
        """Looks up the given field type and tries to lookup the appropriate ctype for it"""
        if issubclass(field_type,(YAMLParamsBase,Enum)):
            return field_type
        if field_type in python2ctype:
            return python2ctype[field_type]
        if field_type in ctype2python:
            return field_type
        assert False, f"Failed to lookup the field_type for {field_type}. see ctypes_helper.py for supported types"

    def __post_init__(self):
        """
        Requires using dataclasses
        Post init function for subclasses which use dataclasses to call
        Converts enum parameters from strings to their appropriate type
        Adds type checks for dataclasses fields
        """
        if not dataclasses.is_dataclass(self):
            return
        for field in dataclasses.fields(self):
            #Ensure that all dataclass fields show up in vars
            if field.name not in vars(self):
                setattr(self, field.name, getattr(self, field.name))
            if field.type is Ellipsis:
                continue
            value = getattr(self, field.name)
            #Convert Enums types from string to their enum value
            if issubclass(field.type, Enum) and isinstance(value,str):
                setattr(self, field.name, field.type[value])
            #Check other types for match
            elif not isinstance(value, field.type) and value is not None:
                if field.type in ctype2python:
                    if not isinstance(value,ctype2python[field.type]):
                        raise ValueError(f'{type(self)} : Expected {field.name} with ctype {field.type} to be {ctype2python[field.type]}, '
                                    f'got {type(value)}')
                else:
                    raise ValueError(f'{type(self)} : Expected {field.name} to be {field.type}, '
                                    f'got {type(value)}')


