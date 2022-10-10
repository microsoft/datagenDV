#!/usr/bin/env python
######################################################
#
#   ctypes_helper.py
#
#MIT License
#
#Copyright (c) Microsoft Corporation.
#
#Author: jonathan.george@microsoft.com
#
######################################################

import re
import ctypes
import collections
from enum import Enum, EnumMeta
import dataclasses


#                             (ctype,            std C type,   python type, python->ctype default lookup )
ctype_stdc_python_lookup = [(ctypes.c_bool,      "_Bool",             bool,       True    ),
                              (ctypes.c_char,    "char",              int,        False   ),
                              (ctypes.c_wchar_p, "const char*",       str,        True    ),
                              (ctypes.c_ubyte,   "unsigned char",     int,        False   ),
                              (ctypes.c_uint8,   "unsigned char",     int,        False   ),
                              (ctypes.c_byte,    "char",              int,        False   ),
                              (ctypes.c_int8,    "char",              int,        False   ),
                              (ctypes.c_ushort,  "unsigned short",    int,        False   ),
                              (ctypes.c_uint16,  "unsigned short",    int,        False   ),
                              (ctypes.c_short,   "short",             int,        False   ),
                              (ctypes.c_int16,   "short",             int,        False   ),
                              (ctypes.c_uint,    "unsigned int",      int,        False   ),
                              (ctypes.c_uint32,  "unsigned int",      int,        False   ),
                              (ctypes.c_int,     "int",               int,        False   ),
                              (ctypes.c_int32,   "int",               int,        False   ),
                              (ctypes.c_ulong,   "unsigned long",     int,        False   ),
                              (ctypes.c_uint64,  "unsigned long",     int,        False   ),
                              (ctypes.c_long,    "long",              int,        True    ),
                              (ctypes.c_int64,   "long",              int,        True    ),
                              (ctypes.c_size_t,  "size_t",            int,        False   ),
                              (ctypes.c_float,   "float",             float,      True    )]

def get_ctype_name(klass):
    return re.split("'|\.", repr(klass))[-2]

ctype2stdc    = { get_ctype_name(x[0]):x[1] for x in ctype_stdc_python_lookup }
stdc2ctype    = { x[1]:x[0] for x in ctype_stdc_python_lookup }
# ctypename2ctype = { get_ctype_name(x[0]):x[0] for x in ctype_stdc_python_lookup }
python2ctype    = { x[2]:x[0] for x in ctype_stdc_python_lookup if x[3] is True }
ctype2python    = { x[0]:x[2] for x in ctype_stdc_python_lookup }



def ctype2stdc_helper(var, klass):
    stdc = "";
    inst = var;

    klass = re.split("'|\.", klass)[-2]

    if "_Array_" in klass:
        ctype, size = re.split("_Array_", klass)
        stdc, inst = ctype2stdc_helper(var, "<class 'ctypes.%s'>" % ctype)
        inst = inst + '[%s]' % size
    elif klass in ctype2stdc:
        stdc = ctype2stdc[klass]
    else:
        # Assume this is C/C++ struct or typedef
        stdc = klass;

    return stdc, inst;


def CtypeToODict(klasses, use_hfields=False):
    # Generate C header for specified ctypes class
    odict = collections.OrderedDict()
    for klass in klasses:
        klstype, klsinst = ctype2stdc_helper( "", repr(klass) )
        odict[klstype] = collections.OrderedDict()
        if hasattr(klass,'_pack_'):
            odict[klstype]['pack'] = klass._pack_
        odict[klstype]['fields'] = collections.OrderedDict()
        fields = klass._hfields_ if use_hfields else klass._fields_
        for f in fields:
            variable, datatype = f[0:2]
            if type(datatype) in [Enum, EnumMeta]: #enum field dumping support
                stdc = datatype.__name__
                inst = variable
                if len(f) == 3: #If is an array of enum type
                    inst += f'[{f[2]}]'
            else:
                stdc, inst = ctype2stdc_helper( variable, repr(datatype) )
            odict[klstype]['fields'][inst] = stdc

    return odict

#use_hfields provides a "no type checking" way to generate headers
def write_ctype_structs(fh, ctype_structs, use_hfields=False):

    structures = CtypeToODict(ctype_structs, use_hfields)
    for struct, contents in structures.items():
        if 'pack' in contents:
            fh.write("#pragma pack(push, %d)\n" % contents['pack'])
        fh.write("typedef struct %s {\n" % struct);

        for (variable, datatype) in contents['fields'].items():
            fh.write("   %-15s %s;\n" % (datatype, variable) )

        fh.write("} %s, *P%s;\n" % (struct, struct))
        if 'pack' in contents:
            fh.write("#pragma pack(pop)\n")
        fh.write("\n")

def write_enum_type_defs(fh, enums):
    for enum_class in enums:
        fh.write("\n")
        fh.write("typedef enum {\n")
        enum_vals = []
        for enum_val in list(enum_class):
            enum_vals.append(f"  {enum_val.name} = {enum_val.value}")

        fh.write(",\n".join(enum_vals))
        fh.write("\n")

        fh.write(f"}} {enum_class.__name__};\n")

        fh.write("\n")


def write_defines(fh, defines):
    fh.write("\n")
    define_lines = [f"#define {name} ( {val} ) \n" for name,val in defines.items() ]
    fh.write("".join(define_lines))
    fh.write("\n")
    
    
def _create_ctype_class(name, base, fields, pack=None):
    class CtypesStruct(base):
        _fields_ = fields
        if pack is not None:
          _pack_ = pack
    CtypesStruct.__name__ = name
    return CtypesStruct

def _convert_hfields_to_fields(hfields):
  fields = []
  for field in hfields:
    if issubclass(field[1], Enum):
      fields.append( (field[0], ctypes.c_uint32))
    else:
      fields.append(field)
  return fields


def write_ctype_obj_binary(datagen_obj, filename):
  """
  Writes out a binary files of the data provided.
  Requires datagen_obj to have called generate_hfields to define _hfields_.
  datagen_obj must also be a "dataclass" class.
  Currently there is limited nesting support. 
  Character pointers and pointers in general are not supported. 
  """
  assert hasattr(datagen_obj, "_hfields_"), "Datagen objects which use ctypes should first call generate_hfields() before calling "
  assert dataclasses.is_dataclass(datagen_obj), "Must pass in a dataclasses object"
  
  FrameData_ctype = _create_ctype_class(f'{datagen_obj.__class__.__name__}_ctypes', ctypes.Structure,
                           _convert_hfields_to_fields(datagen_obj._hfields_))
  myFrame_dict = {dc_field.name: getattr(datagen_obj,dc_field.name) for dc_field in dataclasses.fields(datagen_obj) }
  myFrame_ctype = FrameData_ctype(**myFrame_dict)
  with open(filename, 'wb') as fh:
    fh.write(myFrame_ctype)