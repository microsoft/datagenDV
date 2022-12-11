"""
MIT License

Copyright (c) Microsoft Corporation.

Author: jonathan.george@microsoft.com

Decorator and helper function for pyvsc yaml params classes

"""
import vsc
from vsc import constraint
import dataclasses

def rand_field(rand_type, *args):
    assert callable(rand_type), "rand_type must be a callable class. \
        User is expected to pass in the class for the factory plus the arguments to call it"
    return dataclasses.field(init=False, repr=False, default_factory=lambda:rand_type(*args), metadata={'yml_dump_excluded':True})


def rand_dataclass(cls):
  cls = dataclasses.dataclass(cls)
  cls = rand_YML_override(cls)
  cls = vsc.randobj(cls)
  return cls

def rand_YML_override(cls):
    """
    rand_YML_override is a class decorator
    It provides constraints to tie input values into the random constraints.
    Expects randomized fields to use a "rand_" prefix and the suffix to match a non-randomized field name

    If a non_rand_field is not None, then the randomized field will tied to that value
    If a non_rand_field is None, then the random value will be copied back during post_randomize
    """

    @constraint
    def yaml_input_constraints(self):
        """
        Constrains each rand_ field to the "non_rand" field
        """
        for rand_field_name in [field_name for field_name in vars(self).keys() if field_name.startswith('rand_')]:
            rand_field = getattr(self, rand_field_name)
            non_rand_field = getattr(self, rand_field_name.split('rand_')[1])
            if non_rand_field is not None:
                rand_field == non_rand_field

    def post_randomize(self):
        """
        For each rand_ field, we copy back the values after completing the randomization
        As part of this, we cast the values back to their denoted types using the dataclass typehints
        """
        assert(dataclasses.is_dataclass(self)), \
            "This function requires the subclass usees dataclass fields to provide typehints"
        for rand_field_name in [field_name for field_name in vars(self).keys() if field_name.startswith('rand_')]:
            non_rand_name = rand_field_name.split('rand_')[1]
            assert non_rand_name in vars(self).keys(), \
                f"Missing {non_rand_name} field in {type(self)}. \n\
                This base class expects that random fields are prefixed with rand_ and suffix matches with a non_randomized field"
            non_rand_field_val = getattr(self, non_rand_name)
            if non_rand_field_val is None:
                rand_field_val = getattr(self, rand_field_name)
                non_rand_type = [field.type for field in dataclasses.fields(self) if field.name == non_rand_name][0]
                assert non_rand_type is not Ellipsis, \
                    f"{non_rand_name} must provide field type via the dataclass field to cast to non_rand "
                casted_val = non_rand_type(rand_field_val)
                setattr(self, non_rand_name, casted_val)

    setattr(cls, 'yaml_input_constraints', yaml_input_constraints)

    #Handles calling user class implementation of post_randomize before the decorator's
    class_impl = getattr(cls, 'post_randomize', None)
    if class_impl is not None:
        def post_randomize_final(self):
            class_impl(self)
            post_randomize(self)
        setattr(cls, 'post_randomize', post_randomize_final)
    else:
        setattr(cls, 'post_randomize', post_randomize)
    return cls