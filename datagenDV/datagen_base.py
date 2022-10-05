"""
MIT License

Copyright (c) Microsoft Corporation.

Author: jonathan.george@microsoft.com
"""
#Libary Imports
import argparse
from ruamel.yaml import YAML, MappingNode
from ruamel.yaml.constructor import SafeConstructor

import sys, os
import random
import re
import shutil

from datagenDV import ctypes_helper

class DatagenBase():
    """
    Base class for datagen scripts

    Covers common functionality for loading params, yaml ect.
    Can generate C headers

    usage:
    <script> <input YAML file name> <output YAML file name>
    """

    def __init__(self, description="Datagen Base class "):
        self.args = None
        self.yaml = YAML()
        self.yaml.Constructor = DatagenConstructor
        self.suite = None #test yaml input object
        self.datagen_types_header = """
//
// Auto-generated file - do not hand-edit
//
#ifndef __DATAGEN_TYPES_H__
#define __DATAGEN_TYPES_H__
"""
        self.datagen_types_footer = "#endif // __DATAGEN_TYPES_H__\n"

        self.clean()
        self.parse_args(description)
        self.setup()

    def parse_args(self, description):
        parser = argparse.ArgumentParser(description=description)
        parser.add_argument('input_yaml', type=str, help='input YAML file')
        parser.add_argument('output_yaml', type=str, help='output YAML file')
        parser.add_argument('--header_path', type=str, help='header path', default=".")
        parser.add_argument('--seed', type=str, help='header path', default=None)

        self.args = parser.parse_args()
        self.header_path = self.args.header_path

        if self.args.seed is not None:
          random.seed(self.args.seed)

    def parse_yaml(self):
        """
        Loads input_yaml file into self.suite
        Classes should be specified in YAML with 'DatagenClass' field
        Classes should be registered with self.yaml.register_class before calling
        """
        #Check the parameters passed in if they are valid
        if not os.path.isfile(self.args.input_yaml):
            print(f"ERROR: input_yaml is not a valid path {self.args.input_yaml}")
            sys.exit(1)

        #Open the yaml file into lines and convert DatagenClass fields into yml tags
        yaml_lines = open(self.args.input_yaml).readlines()
        yaml_text = "".join(yaml_lines)

        self.yaml_dict = self.yaml.load(yaml_text)


        # Initialize random number generator
        # using global suite seed

    def write_outputs(self, structs = [], enums = [], defines = {} ):
        if structs or enums or defines:
            with open( os.path.join(self.header_path,"datagen_types.h") , "w") as fh:
                fh.write(self.datagen_types_header)
                ctypes_helper.write_defines(fh, defines)
                ctypes_helper.write_enum_type_defs(fh, enums)
                ctypes_helper.write_ctype_structs(fh, structs, use_hfields=True)
                fh.write(self.datagen_types_footer)

        # Dump the updated parameters back out
        with open(self.args.output_yaml, 'w') as output_yaml_fp:
            self.yaml.dump(self.yaml_dict,output_yaml_fp, transform=lambda s: s.replace('!', '') )

class DatagenConstructor(SafeConstructor):
    """ Custom Construtor to treat DatagenClass as a class tag"""
    def construct_object(self, node, deep=False):
        if isinstance(node, MappingNode):
            data = super().construct_mapping(node, deep)
            assert isinstance(data, dict)
            if "DatagenClass" in data:
                tag = '!'+ data["DatagenClass"]
                assert tag in self.yaml_constructors, \
                    f"{data['DatagenClass']} is not registered with yaml loader. Missing register_class({data['DatagenClass']}) or mispelled in yml "
                #Calls the classes from_yaml
                return self.yaml_constructors[tag](self, data)
        return super().construct_object(node, deep)
