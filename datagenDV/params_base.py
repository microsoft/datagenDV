"""
MIT License

Copyright (c) Microsoft Corporation.

Author: jonathan.george@microsoft.com
"""
import dataclasses
from enum import Enum
from datagenDV.ctypes_helper import python2ctype, ctype2python


class ParamsBase():
    """
    Base command class for datagen parameter classes
    Using Python Dataclasses is recommended
    """
    
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
    
    #################################
    #C Header file generation functions
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
        if issubclass(field_type,(ParamsBase,Enum)):
            return field_type
        if field_type in python2ctype:
            return python2ctype[field_type]
        if field_type in ctype2python:
            return field_type
        assert False, f"Failed to lookup the field_type for {field_type}. see ctypes_helper.py for supported types"
