# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2018-2019 Fetch.AI Limited
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#
# ------------------------------------------------------------------------------
"""This module contains the protocol generator."""

import itertools
import logging
import os
import re
from datetime import date
from os import path
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from aea.configurations.base import (
    ProtocolSpecification,
    ProtocolSpecificationParseError,
)

MESSAGE_IMPORT = "from aea.protocols.base import Message"
SERIALIZER_IMPORT = "from aea.protocols.base import Serializer"

PATH_TO_PACKAGES = "packages"
INIT_FILE_NAME = "__init__.py"
PROTOCOL_YAML_FILE_NAME = "protocol.yaml"
MESSAGE_DOT_PY_FILE_NAME = "message.py"
DIALOGUE_DOT_PY_FILE_NAME = "dialogues.py"
CUSTOM_TYPES_DOT_PY_FILE_NAME = "custom_types.py"
SERIALIZATION_DOT_PY_FILE_NAME = "serialization.py"

CUSTOM_TYPE_PATTERN = "ct:[A-Z][a-zA-Z0-9]*"
SPECIFICATION_PRIMITIVE_TYPES = ["pt:bytes", "pt:int", "pt:float", "pt:bool", "pt:str"]
PYTHON_PRIMITIVE_TYPES = [
    "bytes",
    "int",
    "float",
    "bool",
    "str",
    "FrozenSet",
    "Tuple",
    "Dict",
    "Union",
    "Optional",
]
BASIC_FIELDS_AND_TYPES = {
    "name": str,
    "author": str,
    "version": str,
    "license": str,
    "description": str,
}
PYTHON_TYPE_TO_PROTO_TYPE = {
    "bytes": "bytes",
    "int": "int32",
    "float": "float",
    "bool": "bool",
    "str": "string",
}
RESERVED_NAMES = {"body", "message_id", "dialogue_reference", "target", "performative"}

logger = logging.getLogger(__name__)


def _copyright_header_str(author: str) -> str:
    """
    Produce the copyright header text for a protocol.

    :param author: the author of the protocol.
    :return: The copyright header text.
    """
    copy_right_str = (
        "# -*- coding: utf-8 -*-\n"
        "# ------------------------------------------------------------------------------\n"
        "#\n"
    )
    copy_right_str += "#   Copyright {} {}\n".format(date.today().year, author)
    copy_right_str += (
        "#\n"
        '#   Licensed under the Apache License, Version 2.0 (the "License");\n'
        "#   you may not use this file except in compliance with the License.\n"
        "#   You may obtain a copy of the License at\n"
        "#\n"
        "#       http://www.apache.org/licenses/LICENSE-2.0\n"
        "#\n"
        "#   Unless required by applicable law or agreed to in writing, software\n"
        '#   distributed under the License is distributed on an "AS IS" BASIS,\n'
        "#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.\n"
        "#   See the License for the specific language governing permissions and\n"
        "#   limitations under the License.\n"
        "#\n"
        "# ------------------------------------------------------------------------------\n"
    )
    return copy_right_str


def _to_camel_case(text: str) -> str:
    """
    Convert a text in snake_case format into the CamelCase format

    :param text: the text to be converted.
    :return: The text in CamelCase format.
    """
    return "".join(word.title() for word in text.split("_"))


def _camel_case_to_snake_case(text: str) -> str:
    """
    Convert a text in CamelCase format into the snake_case format

    :param text: the text to be converted.
    :return: The text in CamelCase format.
    """
    return re.sub(r"(?<!^)(?=[A-Z])", "_", text).lower()


def _is_composition_type_with_custom_type(content_type: str) -> bool:
    """
    Evaluate whether the content_type is a composition type (FrozenSet, Tuple, Dict) and contains a custom type as a sub-type.

    :param: the content type
    :return: Boolean result
    """
    if content_type.startswith("Optional"):
        sub_type = _get_sub_types_of_compositional_types(content_type)[0]
        result = _is_composition_type_with_custom_type(sub_type)
    elif content_type.startswith("Union"):
        sub_types = _get_sub_types_of_compositional_types(content_type)
        result = False
        for sub_type in sub_types:
            if _is_composition_type_with_custom_type(sub_type):
                result = True
                break
    elif content_type.startswith("Dict"):
        sub_type_1 = _get_sub_types_of_compositional_types(content_type)[0]
        sub_type_2 = _get_sub_types_of_compositional_types(content_type)[1]

        result = (sub_type_1 not in PYTHON_TYPE_TO_PROTO_TYPE.keys()) or (
            sub_type_2 not in PYTHON_TYPE_TO_PROTO_TYPE.keys()
        )
    elif content_type.startswith("FrozenSet") or content_type.startswith("Tuple"):
        sub_type = _get_sub_types_of_compositional_types(content_type)[0]
        result = sub_type not in PYTHON_TYPE_TO_PROTO_TYPE.keys()
    else:
        result = False
    return result


def _get_sub_types_of_compositional_types(compositional_type: str) -> tuple:
    """
    Extract the sub-types of compositional types.

    This method handles both specification types (e.g. pt:set[], pt:dict[]) as well as python types (e.g. FrozenSet[], Union[]).

    :param compositional_type: the compositional type string whose sub-types are to be extracted.
    :return: tuple containing all extracted sub-types.
    """
    sub_types_list = list()
    if compositional_type.startswith("Optional") or compositional_type.startswith(
        "pt:optional"
    ):
        sub_type1 = compositional_type[
            compositional_type.index("[") + 1 : compositional_type.rindex("]")
        ].strip()
        sub_types_list.append(sub_type1)
    if (
        compositional_type.startswith("FrozenSet")
        or compositional_type.startswith("pt:set")
        or compositional_type.startswith("pt:list")
    ):
        sub_type1 = compositional_type[
            compositional_type.index("[") + 1 : compositional_type.rindex("]")
        ].strip()
        sub_types_list.append(sub_type1)
    if compositional_type.startswith("Tuple"):
        sub_type1 = compositional_type[
            compositional_type.index("[") + 1 : compositional_type.rindex("]")
        ].strip()
        sub_type1 = sub_type1[:-5]
        sub_types_list.append(sub_type1)
    if compositional_type.startswith("Dict") or compositional_type.startswith(
        "pt:dict"
    ):
        sub_type1 = compositional_type[
            compositional_type.index("[") + 1 : compositional_type.index(",")
        ].strip()
        sub_type2 = compositional_type[
            compositional_type.index(",") + 1 : compositional_type.rindex("]")
        ].strip()
        sub_types_list.extend([sub_type1, sub_type2])
    if compositional_type.startswith("Union") or compositional_type.startswith(
        "pt:union"
    ):
        inside_union = compositional_type[
            compositional_type.index("[") + 1 : compositional_type.rindex("]")
        ].strip()
        while inside_union != "":
            if inside_union.startswith("Dict") or inside_union.startswith("pt:dict"):
                sub_type = inside_union[: inside_union.index("]") + 1].strip()
                rest_of_inside_union = inside_union[
                    inside_union.index("]") + 1 :
                ].strip()
                if rest_of_inside_union.find(",") == -1:
                    # it is the last sub-type
                    inside_union = rest_of_inside_union.strip()
                else:
                    # it is not the last sub-type
                    inside_union = rest_of_inside_union[
                        rest_of_inside_union.index(",") + 1 :
                    ].strip()
            elif inside_union.startswith("Tuple"):
                sub_type = inside_union[: inside_union.index("]") + 1].strip()
                rest_of_inside_union = inside_union[
                    inside_union.index("]") + 1 :
                ].strip()
                if rest_of_inside_union.find(",") == -1:
                    # it is the last sub-type
                    inside_union = rest_of_inside_union.strip()
                else:
                    # it is not the last sub-type
                    inside_union = rest_of_inside_union[
                        rest_of_inside_union.index(",") + 1 :
                    ].strip()
            else:
                if inside_union.find(",") == -1:
                    # it is the last sub-type
                    sub_type = inside_union.strip()
                    inside_union = ""
                else:
                    # it is not the last sub-type
                    sub_type = inside_union[: inside_union.index(",")].strip()
                    inside_union = inside_union[inside_union.index(",") + 1 :].strip()
            sub_types_list.append(sub_type)
    return tuple(sub_types_list)


def _ct_specification_type_to_python_type(specification_type: str) -> str:
    """
    Convert a custom specification type into its python equivalent.

    :param specification_type: a protocol specification data type
    :return: The equivalent data type in Python
    """
    python_type = specification_type[3:]
    return python_type


def _pt_specification_type_to_python_type(specification_type: str) -> str:
    """
    Convert a primitive specification type into its python equivalent.

    :param specification_type: a protocol specification data type
    :return: The equivalent data type in Python
    """
    python_type = specification_type[3:]
    return python_type


def _pct_specification_type_to_python_type(specification_type: str) -> str:
    """
    Convert a primitive collection specification type into its python equivalent.

    :param specification_type: a protocol specification data type
    :return: The equivalent data type in Python
    """
    element_type = _get_sub_types_of_compositional_types(specification_type)[0]
    element_type_in_python = _specification_type_to_python_type(element_type)
    if specification_type.startswith("pt:set"):
        python_type = "FrozenSet[{}]".format(element_type_in_python)
    else:
        python_type = "Tuple[{}, ...]".format(element_type_in_python)
    return python_type


def _pmt_specification_type_to_python_type(specification_type: str) -> str:
    """
    Convert a primitive mapping specification type into its python equivalent.

    :param specification_type: a protocol specification data type
    :return: The equivalent data type in Python
    """
    element_types = _get_sub_types_of_compositional_types(specification_type)
    element1_type_in_python = _specification_type_to_python_type(element_types[0])
    element2_type_in_python = _specification_type_to_python_type(element_types[1])
    python_type = "Dict[{}, {}]".format(
        element1_type_in_python, element2_type_in_python
    )
    return python_type


def _mt_specification_type_to_python_type(specification_type: str) -> str:
    """
    Convert a 'pt:union' specification type into its python equivalent.

    :param specification_type: a protocol specification data type
    :return: The equivalent data type in Python
    """
    sub_types = _get_sub_types_of_compositional_types(specification_type)
    python_type = "Union["
    for sub_type in sub_types:
        python_type += "{}, ".format(_specification_type_to_python_type(sub_type))
    python_type = python_type[:-2]
    python_type += "]"
    return python_type


def _optional_specification_type_to_python_type(specification_type: str) -> str:
    """
    Convert a 'pt:optional' specification type into its python equivalent.

    :param specification_type: a protocol specification data type
    :return: The equivalent data type in Python
    """
    element_type = _get_sub_types_of_compositional_types(specification_type)[0]
    element_type_in_python = _specification_type_to_python_type(element_type)
    python_type = "Optional[{}]".format(element_type_in_python)
    return python_type


def _specification_type_to_python_type(specification_type: str) -> str:
    """
    Convert a data type in protocol specification into its Python equivalent.

    :param specification_type: a protocol specification data type
    :return: The equivalent data type in Python
    """
    if specification_type.startswith("pt:optional"):
        python_type = _optional_specification_type_to_python_type(specification_type)
    elif specification_type.startswith("pt:union"):
        python_type = _mt_specification_type_to_python_type(specification_type)
    elif specification_type.startswith("ct:"):
        python_type = _ct_specification_type_to_python_type(specification_type)
    elif specification_type in SPECIFICATION_PRIMITIVE_TYPES:
        python_type = _pt_specification_type_to_python_type(specification_type)
    elif specification_type.startswith("pt:set"):
        python_type = _pct_specification_type_to_python_type(specification_type)
    elif specification_type.startswith("pt:list"):
        python_type = _pct_specification_type_to_python_type(specification_type)
    elif specification_type.startswith("pt:dict"):
        python_type = _pmt_specification_type_to_python_type(specification_type)
    else:
        raise ProtocolSpecificationParseError(
            "Unsupported type: '{}'".format(specification_type)
        )
    return python_type


def _union_sub_type_to_protobuf_variable_name(
    content_name: str, content_type: str
) -> str:
    """
    Given a content of type union, create a variable name for its sub-type for protobuf.

    :param content_name: the name of the content
    :param content_type: the sub-type of a union type
    :return: The variable name
    """
    if content_type.startswith("FrozenSet"):
        sub_type = _get_sub_types_of_compositional_types(content_type)[0]
        expanded_type_str = "set_of_{}".format(sub_type)
    elif content_type.startswith("Tuple"):
        sub_type = _get_sub_types_of_compositional_types(content_type)[0]
        expanded_type_str = "list_of_{}".format(sub_type)
    elif content_type.startswith("Dict"):
        sub_type_1 = _get_sub_types_of_compositional_types(content_type)[0]
        sub_type_2 = _get_sub_types_of_compositional_types(content_type)[1]
        expanded_type_str = "dict_of_{}_{}".format(sub_type_1, sub_type_2)
    else:
        expanded_type_str = content_type

    protobuf_variable_name = "{}_type_{}".format(content_name, expanded_type_str)

    return protobuf_variable_name


def _python_pt_or_ct_type_to_proto_type(content_type: str) -> str:
    """
    Convert a PT or CT from python to their protobuf equivalent.

    :param content_type: the python type
    :return: The protobuf equivalent
    """
    if content_type in PYTHON_TYPE_TO_PROTO_TYPE.keys():
        proto_type = PYTHON_TYPE_TO_PROTO_TYPE[content_type]
    else:
        proto_type = content_type
    return proto_type


def _is_valid_content_name(content_name: str) -> bool:
    return content_name not in RESERVED_NAMES


def _includes_custom_type(content_type: str) -> bool:
    """
    Evaluate whether a content type is a custom type or has a custom type as a sub-type.
    :return: Boolean result
    """
    if content_type.startswith("Optional"):
        sub_type = _get_sub_types_of_compositional_types(content_type)[0]
        result = _includes_custom_type(sub_type)
    elif content_type.startswith("Union"):
        sub_types = _get_sub_types_of_compositional_types(content_type)
        result = False
        for sub_type in sub_types:
            if _includes_custom_type(sub_type):
                result = True
                break
    elif (
        content_type.startswith("FrozenSet")
        or content_type.startswith("Tuple")
        or content_type.startswith("Dict")
        or content_type in PYTHON_TYPE_TO_PROTO_TYPE.keys()
    ):
        result = False
    else:
        result = True
    return result


class ProtocolGenerator:
    """This class generates a protocol_verification package from a ProtocolTemplate object."""

    def __init__(
        self,
        protocol_specification: ProtocolSpecification,
        output_path: str = ".",
        path_to_protocol_package: Optional[str] = None,
    ) -> None:
        """
        Instantiate a protocol generator.

        :param protocol_specification: the protocol specification object
        :param output_path: the path to the location in which the protocol module is to be generated.
        :return: None
        """
        self.protocol_specification = protocol_specification
        self.protocol_specification_in_camel_case = _to_camel_case(
            self.protocol_specification.name
        )
        self.output_folder_path = os.path.join(output_path, protocol_specification.name)
        self.path_to_protocol_package = (
            path_to_protocol_package + self.protocol_specification.name
            if path_to_protocol_package is not None
            else "{}.{}.protocols.{}".format(
                PATH_TO_PACKAGES,
                self.protocol_specification.author,
                self.protocol_specification.name,
            )
        )

        self._imports = {
            "Set": True,
            "Tuple": True,
            "cast": True,
            "FrozenSet": False,
            "Dict": False,
            "Union": False,
            "Optional": False,
        }

        self._speech_acts = dict()  # type: Dict[str, Dict[str, str]]
        self._all_performatives = list()  # type: List[str]
        self._all_unique_contents = dict()  # type: Dict[str, str]
        self._all_custom_types = list()  # type: List[str]
        self._custom_custom_types = dict()  # type: Dict[str, str]

        # dialogue config
        self._initial_performative = ""
        self._reply = dict()  # type: Dict[str, List[str]]

        self._roles = list()  # type: List[str]
        self._end_states = list()  # type: List[str]

        self.indent = ""

        try:
            self._setup()
        except Exception:
            raise

    def _setup(self) -> None:
        """
        Extract all relevant data structures from the specification.

        :return: None
        """
        all_performatives_set = set()
        all_custom_types_set = set()

        for (
            performative,
            speech_act_content_config,
        ) in self.protocol_specification.speech_acts.read_all():
            all_performatives_set.add(performative)
            self._speech_acts[performative] = {}
            for content_name, content_type in speech_act_content_config.args.items():
                # check content's name is valid
                if not _is_valid_content_name(content_name):
                    raise ProtocolSpecificationParseError(
                        "Invalid name for content '{}' of performative '{}'. This name is reserved.".format(
                            content_name, performative,
                        )
                    )

                # determine necessary imports from typing
                if len(re.findall("pt:set\\[", content_type)) >= 1:
                    self._imports["FrozenSet"] = True
                if len(re.findall("pt:dict\\[", content_type)) >= 1:
                    self._imports["Dict"] = True
                if len(re.findall("pt:union\\[", content_type)) >= 1:
                    self._imports["Union"] = True
                if len(re.findall("pt:optional\\[", content_type)) >= 1:
                    self._imports["Optional"] = True

                # specification type --> python type
                pythonic_content_type = _specification_type_to_python_type(content_type)

                # check composition type does not include custom type
                if _is_composition_type_with_custom_type(pythonic_content_type):
                    raise ProtocolSpecificationParseError(
                        "Invalid type for content '{}' of performative '{}'. A custom type cannot be used in the following composition types: [pt:set, pt:list, pt:dict].".format(
                            content_name, performative,
                        )
                    )

                self._all_unique_contents[content_name] = pythonic_content_type
                self._speech_acts[performative][content_name] = pythonic_content_type
                if content_type.startswith("ct:"):
                    all_custom_types_set.add(pythonic_content_type)

        # sort the sets
        self._all_performatives = sorted(all_performatives_set)
        self._all_custom_types = sorted(all_custom_types_set)

        # "XXX" custom type --> "CustomXXX"
        self._custom_custom_types = {
            pure_custom_type: "Custom" + pure_custom_type
            for pure_custom_type in self._all_custom_types
        }

        # Dialogue attributes
        if (
            self.protocol_specification.dialogue_config != {}
            and self.protocol_specification.dialogue_config is not None
        ):
            self._reply = self.protocol_specification.dialogue_config["reply"]
            roles_set = self.protocol_specification.dialogue_config["roles"]  # type: ignore
            self._roles = sorted(roles_set, reverse=True)
            self._end_states = self.protocol_specification.dialogue_config["end_states"]  # type: ignore

            # infer initial performative
            set_of_all_performatives = set(self._reply.keys())
            set_of_all_replies = set()
            for _, list_of_replies in self._reply.items():
                set_of_replies = set(list_of_replies)
                set_of_all_replies.update(set_of_replies)
            initial_performative_set = set_of_all_performatives.difference(
                set_of_all_replies
            )
            initial_performative_list = list(initial_performative_set)
            if len(initial_performative_list) != 1:
                raise ProtocolSpecificationParseError(
                    "Invalid reply structure. There must be a single speech-act which is not a valid reply to any other speech-acts so it can be designated as the inital speech-act. Found {} of such speech-acts in the specification".format(
                        len(initial_performative_list),
                    )
                )
            else:
                initial_performative = initial_performative_list[0].upper()

            self._initial_performative = initial_performative

    def _change_indent(self, number: int, mode: str = None) -> None:
        """
        Update the value of 'indent' global variable.

        This function controls the indentation of the code produced throughout the generator.

        There are two modes:
        - Setting the indent to a desired 'number' level. In this case, 'mode' has to be set to "s".
        - Updating the incrementing/decrementing the indentation level by 'number' amounts. In this case 'mode' is None.

        :param number: the number of indentation levels to set/increment/decrement
        :param mode: the mode of indentation change
        :return: None
        """
        if mode and mode == "s":
            if number >= 0:
                self.indent = number * "    "
            else:
                raise ValueError("Error: setting indent to be a negative number.")
        else:
            if number >= 0:
                for _ in itertools.repeat(None, number):
                    self.indent += "    "
            else:
                if abs(number) <= len(self.indent) / 4:
                    self.indent = self.indent[abs(number) * 4 :]
                else:
                    raise ValueError(
                        "Not enough spaces in the 'indent' variable to remove."
                    )

    def _import_from_typing_module(self) -> str:
        """
        Manage import statement for the typing package.

        :return: import statement for the typing package
        """
        ordered_packages = [
            "Dict",
            "FrozenSet",
            "Optional",
            "Set",
            "Tuple",
            "Union",
            "cast",
        ]
        import_str = "from typing import "
        for package in ordered_packages:
            if self._imports[package]:
                import_str += "{}, ".format(package)
        import_str = import_str[:-2]
        return import_str

    def _import_from_custom_types_module(self) -> str:
        """
        Manage import statement from custom_types module

        :return: import statement for the custom_types module
        """
        import_str = ""
        if len(self._all_custom_types) == 0:
            pass
        else:
            for custom_class in self._all_custom_types:
                import_str += "from {}.custom_types import {} as Custom{}\n".format(
                    self.path_to_protocol_package, custom_class, custom_class,
                )
            import_str = import_str[:-1]
        return import_str

    def _performatives_str(self) -> str:
        """
        Generate the performatives instance property string, a set containing all valid performatives of this protocol.

        :return: the performatives set string
        """
        performatives_str = "{"
        for performative in self._all_performatives:
            performatives_str += '"{}", '.format(performative)
        performatives_str = performatives_str[:-2]
        performatives_str += "}"
        return performatives_str

    def _performatives_enum_str(self) -> str:
        """
        Generate the performatives Enum class.

        :return: the performatives Enum string
        """
        enum_str = self.indent + "class Performative(Enum):\n"
        self._change_indent(1)
        enum_str += self.indent + '"""Performatives for the {} protocol."""\n\n'.format(
            self.protocol_specification.name
        )
        for performative in self._all_performatives:
            enum_str += self.indent + '{} = "{}"\n'.format(
                performative.upper(), performative
            )
        enum_str += "\n"
        enum_str += self.indent + "def __str__(self):\n"
        self._change_indent(1)
        enum_str += self.indent + '"""Get the string representation."""\n'
        enum_str += self.indent + "return self.value\n"
        self._change_indent(-1)
        enum_str += "\n"
        self._change_indent(-1)

        return enum_str

    def _check_content_type_str(self, content_name: str, content_type: str) -> str:
        """
        Produce the checks of elements of compositional types.

        :param content_name: the name of the content to be checked
        :param content_type: the type of the content to be checked
        :return: the string containing the checks.
        """
        check_str = ""
        if content_type.startswith("Optional["):
            optional = True
            check_str += self.indent + 'if self.is_set("{}"):\n'.format(content_name)
            self._change_indent(1)
            check_str += self.indent + "expected_nb_of_contents += 1\n"
            content_type = _get_sub_types_of_compositional_types(content_type)[0]
            check_str += self.indent + "{} = cast({}, self.{})\n".format(
                content_name, self._to_custom_custom(content_type), content_name
            )
            content_variable = content_name
        else:
            optional = False
            content_variable = "self." + content_name
        if content_type.startswith("Union["):
            element_types = _get_sub_types_of_compositional_types(content_type)
            unique_standard_types_set = set()
            for typing_content_type in element_types:
                if typing_content_type.startswith("FrozenSet"):
                    unique_standard_types_set.add("frozenset")
                elif typing_content_type.startswith("Tuple"):
                    unique_standard_types_set.add("tuple")
                elif typing_content_type.startswith("Dict"):
                    unique_standard_types_set.add("dict")
                else:
                    unique_standard_types_set.add(typing_content_type)
            unique_standard_types_list = sorted(unique_standard_types_set)
            check_str += self.indent
            check_str += "assert "
            for unique_type in unique_standard_types_list:
                check_str += "type({}) == {} or ".format(
                    content_variable, self._to_custom_custom(unique_type)
                )
            check_str = check_str[:-4]
            check_str += ", \"Invalid type for content '{}'. Expected either of '{}'. Found '{{}}'.\".format(type({}))\n".format(
                content_name,
                [
                    unique_standard_type
                    for unique_standard_type in unique_standard_types_list
                ],
                content_variable,
            )
            if "frozenset" in unique_standard_types_list:
                check_str += self.indent + "if type({}) == frozenset:\n".format(
                    content_variable
                )
                self._change_indent(1)
                check_str += self.indent + "assert (\n"
                self._change_indent(1)
                frozen_set_element_types_set = set()
                for element_type in element_types:
                    if element_type.startswith("FrozenSet"):
                        frozen_set_element_types_set.add(
                            _get_sub_types_of_compositional_types(element_type)[0]
                        )
                frozen_set_element_types = sorted(frozen_set_element_types_set)
                for frozen_set_element_type in frozen_set_element_types:
                    check_str += (
                        self.indent
                        + "all(type(element) == {} for element in {}) or\n".format(
                            self._to_custom_custom(frozen_set_element_type),
                            content_variable,
                        )
                    )
                check_str = check_str[:-4]
                check_str += "\n"
                self._change_indent(-1)
                if len(frozen_set_element_types) == 1:
                    check_str += (
                        self.indent
                        + "), \"Invalid type for elements of content '{}'. Expected ".format(
                            content_name
                        )
                    )
                    for frozen_set_element_type in frozen_set_element_types:
                        check_str += "'{}'".format(
                            self._to_custom_custom(frozen_set_element_type)
                        )
                    check_str += '."\n'
                else:
                    check_str += (
                        self.indent
                        + "), \"Invalid type for frozenset elements in content '{}'. Expected either ".format(
                            content_name
                        )
                    )
                    for frozen_set_element_type in frozen_set_element_types:
                        check_str += "'{}' or ".format(
                            self._to_custom_custom(frozen_set_element_type)
                        )
                    check_str = check_str[:-4]
                    check_str += '."\n'
                self._change_indent(-1)
            if "tuple" in unique_standard_types_list:
                check_str += self.indent + "if type({}) == tuple:\n".format(
                    content_variable
                )
                self._change_indent(1)
                check_str += self.indent + "assert (\n"
                self._change_indent(1)
                tuple_element_types_set = set()
                for element_type in element_types:
                    if element_type.startswith("Tuple"):
                        tuple_element_types_set.add(
                            _get_sub_types_of_compositional_types(element_type)[0]
                        )
                tuple_element_types = sorted(tuple_element_types_set)
                for tuple_element_type in tuple_element_types:
                    check_str += (
                        self.indent
                        + "all(type(element) == {} for element in {}) or \n".format(
                            self._to_custom_custom(tuple_element_type), content_variable
                        )
                    )
                check_str = check_str[:-4]
                check_str += "\n"
                self._change_indent(-1)
                if len(tuple_element_types) == 1:
                    check_str += (
                        self.indent
                        + "), \"Invalid type for tuple elements in content '{}'. Expected ".format(
                            content_name
                        )
                    )
                    for tuple_element_type in tuple_element_types:
                        check_str += "'{}'".format(
                            self._to_custom_custom(tuple_element_type)
                        )
                    check_str += '."\n'
                else:
                    check_str += (
                        self.indent
                        + "), \"Invalid type for tuple elements in content '{}'. Expected either ".format(
                            content_name
                        )
                    )
                    for tuple_element_type in tuple_element_types:
                        check_str += "'{}' or ".format(
                            self._to_custom_custom(tuple_element_type)
                        )
                    check_str = check_str[:-4]
                    check_str += '."\n'
                self._change_indent(-1)
            if "dict" in unique_standard_types_list:
                check_str += self.indent + "if type({}) == dict:\n".format(
                    content_variable
                )
                self._change_indent(1)
                check_str += (
                    self.indent
                    + "for key_of_{}, value_of_{} in {}.items():\n".format(
                        content_name, content_name, content_variable
                    )
                )
                self._change_indent(1)
                check_str += self.indent + "assert (\n"
                self._change_indent(1)
                dict_key_value_types = dict()
                for element_type in element_types:
                    if element_type.startswith("Dict"):
                        dict_key_value_types[
                            _get_sub_types_of_compositional_types(element_type)[0]
                        ] = _get_sub_types_of_compositional_types(element_type)[1]
                for element1_type in sorted(dict_key_value_types.keys()):
                    check_str += (
                        self.indent
                        + "(type(key_of_{}) == {} and type(value_of_{}) == {}) or\n".format(
                            content_name,
                            self._to_custom_custom(element1_type),
                            content_name,
                            self._to_custom_custom(dict_key_value_types[element1_type]),
                        )
                    )
                check_str = check_str[:-4]
                check_str += "\n"
                self._change_indent(-1)

                if len(dict_key_value_types) == 1:
                    check_str += (
                        self.indent
                        + "), \"Invalid type for dictionary key, value in content '{}'. Expected ".format(
                            content_name
                        )
                    )
                    for key in sorted(dict_key_value_types.keys()):
                        check_str += "'{}', '{}'".format(key, dict_key_value_types[key])
                    check_str += '."\n'
                else:
                    check_str += (
                        self.indent
                        + "), \"Invalid type for dictionary key, value in content '{}'. Expected ".format(
                            content_name
                        )
                    )
                    for key in sorted(dict_key_value_types.keys()):
                        check_str += "'{}','{}' or ".format(
                            key, dict_key_value_types[key]
                        )
                    check_str = check_str[:-4]
                    check_str += '."\n'
                self._change_indent(-2)
        elif content_type.startswith("FrozenSet["):
            # check the type
            check_str += (
                self.indent
                + "assert type({}) == frozenset, \"Invalid type for content '{}'. Expected 'frozenset'. Found '{{}}'.\".format(type({}))\n".format(
                    content_variable, content_name, content_variable
                )
            )
            element_type = _get_sub_types_of_compositional_types(content_type)[0]
            check_str += self.indent + "assert all(\n"
            self._change_indent(1)
            check_str += self.indent + "type(element) == {} for element in {}\n".format(
                self._to_custom_custom(element_type), content_variable
            )
            self._change_indent(-1)
            check_str += (
                self.indent
                + "), \"Invalid type for frozenset elements in content '{}'. Expected '{}'.\"\n".format(
                    content_name, element_type
                )
            )
        elif content_type.startswith("Tuple["):
            # check the type
            check_str += (
                self.indent
                + "assert type({}) == tuple, \"Invalid type for content '{}'. Expected 'tuple'. Found '{{}}'.\".format(type({}))\n".format(
                    content_variable, content_name, content_variable
                )
            )
            element_type = _get_sub_types_of_compositional_types(content_type)[0]
            check_str += self.indent + "assert all(\n"
            self._change_indent(1)
            check_str += self.indent + "type(element) == {} for element in {}\n".format(
                self._to_custom_custom(element_type), content_variable
            )
            self._change_indent(-1)
            check_str += (
                self.indent
                + "), \"Invalid type for tuple elements in content '{}'. Expected '{}'.\"\n".format(
                    content_name, element_type
                )
            )
        elif content_type.startswith("Dict["):
            # check the type
            check_str += (
                self.indent
                + "assert type({}) == dict, \"Invalid type for content '{}'. Expected 'dict'. Found '{{}}'.\".format(type({}))\n".format(
                    content_variable, content_name, content_variable
                )
            )
            element_type_1 = _get_sub_types_of_compositional_types(content_type)[0]
            element_type_2 = _get_sub_types_of_compositional_types(content_type)[1]
            # check the keys type then check the values type
            check_str += (
                self.indent
                + "for key_of_{}, value_of_{} in {}.items():\n".format(
                    content_name, content_name, content_variable
                )
            )
            self._change_indent(1)
            check_str += self.indent + "assert (\n"
            self._change_indent(1)
            check_str += self.indent + "type(key_of_{}) == {}\n".format(
                content_name, self._to_custom_custom(element_type_1)
            )
            self._change_indent(-1)
            check_str += (
                self.indent
                + "), \"Invalid type for dictionary keys in content '{}'. Expected '{}'. Found '{{}}'.\".format(type(key_of_{}))\n".format(
                    content_name, element_type_1, content_name
                )
            )

            check_str += self.indent + "assert (\n"
            self._change_indent(1)
            check_str += self.indent + "type(value_of_{}) == {}\n".format(
                content_name, self._to_custom_custom(element_type_2)
            )
            self._change_indent(-1)
            check_str += (
                self.indent
                + "), \"Invalid type for dictionary values in content '{}'. Expected '{}'. Found '{{}}'.\".format(type(value_of_{}))\n".format(
                    content_name, element_type_2, content_name
                )
            )
            self._change_indent(-1)
        else:
            check_str += (
                self.indent
                + "assert type({}) == {}, \"Invalid type for content '{}'. Expected '{}'. Found '{{}}'.\".format(type({}))\n".format(
                    content_variable,
                    self._to_custom_custom(content_type),
                    content_name,
                    content_type,
                    content_variable,
                )
            )
        if optional:
            self._change_indent(-1)
        return check_str

    def _message_class_str(self) -> str:
        """
        Produce the content of the Message class.

        :return: the message.py file content
        """
        self._change_indent(0, "s")

        # Header
        cls_str = _copyright_header_str(self.protocol_specification.author) + "\n"

        # Module docstring
        cls_str += (
            self.indent
            + '"""This module contains {}\'s message definition."""\n\n'.format(
                self.protocol_specification.name
            )
        )

        # Imports
        cls_str += self.indent + "import logging\n"
        cls_str += self.indent + "from enum import Enum\n"
        cls_str += self._import_from_typing_module() + "\n\n"
        cls_str += self.indent + "from aea.configurations.base import ProtocolId\n"
        cls_str += MESSAGE_IMPORT + "\n"
        if self._import_from_custom_types_module() != "":
            cls_str += "\n" + self._import_from_custom_types_module() + "\n"
        else:
            cls_str += self._import_from_custom_types_module()
        cls_str += (
            self.indent
            + '\nlogger = logging.getLogger("aea.packages.{}.protocols.{}.message")\n'.format(
                self.protocol_specification.author, self.protocol_specification.name
            )
        )
        cls_str += self.indent + "\nDEFAULT_BODY_SIZE = 4\n"

        # Class Header
        cls_str += self.indent + "\n\nclass {}Message(Message):\n".format(
            self.protocol_specification_in_camel_case
        )
        self._change_indent(1)
        cls_str += self.indent + '"""{}"""\n\n'.format(
            self.protocol_specification.description
        )

        # Class attributes
        cls_str += self.indent + 'protocol_id = ProtocolId("{}", "{}", "{}")\n'.format(
            self.protocol_specification.author,
            self.protocol_specification.name,
            self.protocol_specification.version,
        )
        for custom_type in self._all_custom_types:
            cls_str += "\n"
            cls_str += self.indent + "{} = Custom{}\n".format(custom_type, custom_type)

        # Performatives Enum
        cls_str += "\n" + self._performatives_enum_str()

        # __init__
        cls_str += self.indent + "def __init__(\n"
        self._change_indent(1)
        cls_str += self.indent + "self,\n"
        cls_str += self.indent + "performative: Performative,\n"
        cls_str += self.indent + 'dialogue_reference: Tuple[str, str] = ("", ""),\n'
        cls_str += self.indent + "message_id: int = 1,\n"
        cls_str += self.indent + "target: int = 0,\n"
        cls_str += self.indent + "**kwargs,\n"
        self._change_indent(-1)
        cls_str += self.indent + "):\n"
        self._change_indent(1)
        cls_str += self.indent + '"""\n'
        cls_str += self.indent + "Initialise an instance of {}Message.\n\n".format(
            self.protocol_specification_in_camel_case
        )
        cls_str += self.indent + ":param message_id: the message id.\n"
        cls_str += self.indent + ":param dialogue_reference: the dialogue reference.\n"
        cls_str += self.indent + ":param target: the message target.\n"
        cls_str += self.indent + ":param performative: the message performative.\n"
        cls_str += self.indent + '"""\n'
        cls_str += self.indent + "super().__init__(\n"
        self._change_indent(1)
        cls_str += self.indent + "dialogue_reference=dialogue_reference,\n"
        cls_str += self.indent + "message_id=message_id,\n"
        cls_str += self.indent + "target=target,\n"
        cls_str += (
            self.indent
            + "performative={}Message.Performative(performative),\n".format(
                self.protocol_specification_in_camel_case
            )
        )
        cls_str += self.indent + "**kwargs,\n"
        self._change_indent(-1)
        cls_str += self.indent + ")\n"
        cls_str += self.indent + "self._performatives = {}\n".format(
            self._performatives_str()
        )
        self._change_indent(-1)

        # Instance properties
        cls_str += self.indent + "@property\n"
        cls_str += self.indent + "def valid_performatives(self) -> Set[str]:\n"
        self._change_indent(1)
        cls_str += self.indent + '"""Get valid performatives."""\n'
        cls_str += self.indent + "return self._performatives\n\n"
        self._change_indent(-1)
        cls_str += self.indent + "@property\n"
        cls_str += self.indent + "def dialogue_reference(self) -> Tuple[str, str]:\n"
        self._change_indent(1)
        cls_str += self.indent + '"""Get the dialogue_reference of the message."""\n'
        cls_str += (
            self.indent
            + 'assert self.is_set("dialogue_reference"), "dialogue_reference is not set."\n'
        )
        cls_str += (
            self.indent
            + 'return cast(Tuple[str, str], self.get("dialogue_reference"))\n\n'
        )
        self._change_indent(-1)
        cls_str += self.indent + "@property\n"
        cls_str += self.indent + "def message_id(self) -> int:\n"
        self._change_indent(1)
        cls_str += self.indent + '"""Get the message_id of the message."""\n'
        cls_str += (
            self.indent + 'assert self.is_set("message_id"), "message_id is not set."\n'
        )
        cls_str += self.indent + 'return cast(int, self.get("message_id"))\n\n'
        self._change_indent(-1)
        cls_str += self.indent + "@property\n"
        cls_str += (
            self.indent + "def performative(self) -> Performative:  # noqa: F821\n"
        )
        self._change_indent(1)
        cls_str += self.indent + '"""Get the performative of the message."""\n'
        cls_str += (
            self.indent
            + 'assert self.is_set("performative"), "performative is not set."\n'
        )
        cls_str += (
            self.indent
            + 'return cast({}Message.Performative, self.get("performative"))\n\n'.format(
                self.protocol_specification_in_camel_case
            )
        )
        self._change_indent(-1)
        cls_str += self.indent + "@property\n"
        cls_str += self.indent + "def target(self) -> int:\n"
        self._change_indent(1)
        cls_str += self.indent + '"""Get the target of the message."""\n'
        cls_str += self.indent + 'assert self.is_set("target"), "target is not set."\n'
        cls_str += self.indent + 'return cast(int, self.get("target"))\n\n'
        self._change_indent(-1)

        for content_name in sorted(self._all_unique_contents.keys()):
            content_type = self._all_unique_contents[content_name]
            cls_str += self.indent + "@property\n"
            cls_str += self.indent + "def {}(self) -> {}:\n".format(
                content_name, self._to_custom_custom(content_type)
            )
            self._change_indent(1)
            cls_str += (
                self.indent
                + '"""Get the \'{}\' content from the message."""\n'.format(
                    content_name
                )
            )
            if not content_type.startswith("Optional"):
                cls_str += (
                    self.indent
                    + 'assert self.is_set("{}"), "\'{}\' content is not set."\n'.format(
                        content_name, content_name
                    )
                )
            cls_str += self.indent + 'return cast({}, self.get("{}"))\n\n'.format(
                self._to_custom_custom(content_type), content_name
            )
            self._change_indent(-1)

        # check_consistency method
        cls_str += self.indent + "def _is_consistent(self) -> bool:\n"
        self._change_indent(1)
        cls_str += (
            self.indent
            + '"""Check that the message follows the {} protocol."""\n'.format(
                self.protocol_specification.name
            )
        )
        cls_str += self.indent + "try:\n"
        self._change_indent(1)
        cls_str += (
            self.indent
            + "assert type(self.dialogue_reference) == tuple, \"Invalid type for 'dialogue_reference'. Expected 'tuple'. Found '{}'.\""
            ".format(type(self.dialogue_reference))\n"
        )
        cls_str += (
            self.indent
            + "assert type(self.dialogue_reference[0]) == str, \"Invalid type for 'dialogue_reference[0]'. Expected 'str'. Found '{}'.\""
            ".format(type(self.dialogue_reference[0]))\n"
        )
        cls_str += (
            self.indent
            + "assert type(self.dialogue_reference[1]) == str, \"Invalid type for 'dialogue_reference[1]'. Expected 'str'. Found '{}'.\""
            ".format(type(self.dialogue_reference[1]))\n"
        )
        cls_str += (
            self.indent
            + "assert type(self.message_id) == int, \"Invalid type for 'message_id'. Expected 'int'. Found '{}'.\""
            ".format(type(self.message_id))\n"
        )
        cls_str += (
            self.indent
            + "assert type(self.target) == int, \"Invalid type for 'target'. Expected 'int'. Found '{}'.\""
            ".format(type(self.target))\n\n"
        )

        cls_str += self.indent + "# Light Protocol Rule 2\n"
        cls_str += self.indent + "# Check correct performative\n"
        cls_str += (
            self.indent
            + "assert type(self.performative) == {}Message.Performative".format(
                self.protocol_specification_in_camel_case
            )
        )
        cls_str += (
            ", \"Invalid 'performative'. Expected either of '{}'. Found '{}'.\".format("
        )
        cls_str += "self.valid_performatives, self.performative"
        cls_str += ")\n\n"

        cls_str += self.indent + "# Check correct contents\n"
        cls_str += (
            self.indent + "actual_nb_of_contents = len(self.body) - DEFAULT_BODY_SIZE\n"
        )
        cls_str += self.indent + "expected_nb_of_contents = 0\n"
        counter = 1
        for performative, contents in self._speech_acts.items():
            if counter == 1:
                cls_str += self.indent + "if "
            else:
                cls_str += self.indent + "elif "
            cls_str += "self.performative == {}Message.Performative.{}:\n".format(
                self.protocol_specification_in_camel_case, performative.upper(),
            )
            self._change_indent(1)
            nb_of_non_optional_contents = 0
            for content_type in contents.values():
                if not content_type.startswith("Optional"):
                    nb_of_non_optional_contents += 1

            cls_str += self.indent + "expected_nb_of_contents = {}\n".format(
                nb_of_non_optional_contents
            )
            for content_name, content_type in contents.items():
                cls_str += self._check_content_type_str(content_name, content_type)
            counter += 1
            self._change_indent(-1)

        cls_str += "\n"
        cls_str += self.indent + "# Check correct content count\n"
        cls_str += (
            self.indent + "assert expected_nb_of_contents == actual_nb_of_contents, "
            '"Incorrect number of contents. Expected {}. Found {}"'
            ".format(expected_nb_of_contents, actual_nb_of_contents)\n\n"
        )

        cls_str += self.indent + "# Light Protocol Rule 3\n"
        cls_str += self.indent + "if self.message_id == 1:\n"
        self._change_indent(1)
        cls_str += (
            self.indent
            + "assert self.target == 0, \"Invalid 'target'. Expected 0 (because 'message_id' is 1). Found {}.\".format(self.target)\n"
        )
        self._change_indent(-1)
        cls_str += self.indent + "else:\n"
        self._change_indent(1)
        cls_str += (
            self.indent + "assert 0 < self.target < self.message_id, "
            "\"Invalid 'target'. Expected an integer between 1 and {} inclusive. Found {}.\""
            ".format(self.message_id - 1, self.target,)\n"
        )
        self._change_indent(-2)
        cls_str += self.indent + "except (AssertionError, ValueError, KeyError) as e:\n"
        self._change_indent(1)
        cls_str += self.indent + "logger.error(str(e))\n"
        cls_str += self.indent + "return False\n\n"
        self._change_indent(-1)
        cls_str += self.indent + "return True\n"

        return cls_str

    def _valid_replies_str(self):
        """
        Generate the `valid replies` dictionary.

        :return: the `valid replies` dictionary string
        """
        valid_replies_str = self.indent + "VALID_REPLIES = {\n"
        self._change_indent(1)
        for performative in sorted(self._reply.keys()):
            valid_replies_str += (
                self.indent
                + "{}Message.Performative.{}: frozenset(".format(
                    self.protocol_specification_in_camel_case, performative.upper()
                )
            )
            if len(self._reply[performative]) > 0:
                valid_replies_str += "\n"
                self._change_indent(1)
                valid_replies_str += self.indent + "["
                for reply in self._reply[performative]:
                    valid_replies_str += "{}Message.Performative.{}, ".format(
                        self.protocol_specification_in_camel_case, reply.upper()
                    )
                valid_replies_str = valid_replies_str[:-2]
                valid_replies_str += "]\n"
                self._change_indent(-1)
            valid_replies_str += self.indent + "),\n"

        self._change_indent(-1)
        valid_replies_str += (
            self.indent
            + "}}  # type: Dict[{}Message.Performative, FrozenSet[{}Message.Performative]]\n".format(
                self.protocol_specification_in_camel_case,
                self.protocol_specification_in_camel_case,
            )
        )
        return valid_replies_str

    def _end_state_enum_str(self) -> str:
        """
        Generate the end state Enum class.

        :return: the end state Enum string
        """
        enum_str = self.indent + "class EndState(Dialogue.EndState):\n"
        self._change_indent(1)
        enum_str += (
            self.indent
            + '"""This class defines the end states of a {} dialogue."""\n\n'.format(
                self.protocol_specification.name
            )
        )
        tag = 0
        for end_state in self._end_states:
            enum_str += self.indent + "{} = {}\n".format(end_state.upper(), tag)
            tag += 1
        self._change_indent(-1)
        return enum_str

    def _agent_role_enum_str(self) -> str:
        """
        Generate the agent role Enum class.

        :return: the agent role Enum string
        """
        enum_str = self.indent + "class AgentRole(Dialogue.Role):\n"
        self._change_indent(1)
        enum_str += (
            self.indent
            + '"""This class defines the agent\'s role in a {} dialogue."""\n\n'.format(
                self.protocol_specification.name
            )
        )
        for role in self._roles:
            enum_str += self.indent + '{} = "{}"\n'.format(role.upper(), role)
        self._change_indent(-1)
        return enum_str

    def _dialogue_class_str(self) -> str:
        """
        Produce the content of the Message class.

        :return: the message.py file content
        """
        self._change_indent(0, "s")

        # Header
        cls_str = _copyright_header_str(self.protocol_specification.author) + "\n"

        # Module docstring
        cls_str += self.indent + '"""\n'
        cls_str += (
            self.indent
            + "This module contains the classes required for {} dialogue management.\n\n".format(
                self.protocol_specification.name
            )
        )
        cls_str += (
            self.indent
            + "- DialogueLabel: The dialogue label class acts as an identifier for dialogues.\n"
        )
        cls_str += (
            self.indent
            + "- Dialogue: The dialogue class maintains state of a dialogue and manages it.\n"
        )
        cls_str += (
            self.indent
            + "- Dialogues: The dialogues class keeps track of all dialogues.\n"
        )
        cls_str += self.indent + '"""\n\n'

        # Imports
        cls_str += self.indent + "from abc import ABC\n"
        cls_str += self.indent + "from enum import Enum\n"
        cls_str += self.indent + "from typing import Dict, FrozenSet, cast\n\n"
        cls_str += (
            self.indent
            + "from aea.helpers.dialogue.base import Dialogue, DialogueLabel, Dialogues\n"
        )
        cls_str += self.indent + "from aea.mail.base import Address\n"
        cls_str += self.indent + "from aea.protocols.base import Message\n\n"
        cls_str += self.indent + "from {}.message import {}Message\n".format(
            self.path_to_protocol_package, self.protocol_specification_in_camel_case,
        )

        # Constants
        cls_str += self.indent + "\n"
        cls_str += self.indent + self._valid_replies_str()
        cls_str += self.indent + "\n"

        # Class Header
        cls_str += "\nclass {}Dialogue(Dialogue):\n".format(
            self.protocol_specification_in_camel_case
        )
        self._change_indent(1)
        cls_str += (
            self.indent
            + '"""The {} dialogue class maintains state of a dialogue and manages it."""\n'.format(
                self.protocol_specification.name
            )
        )

        # Enums
        cls_str += "\n" + self._agent_role_enum_str()
        cls_str += "\n" + self._end_state_enum_str()
        cls_str += "\n"

        # is_valid method
        cls_str += self.indent + "def is_valid(self, message: Message) -> bool:\n"
        self._change_indent(1)
        cls_str += self.indent + '"""\n'
        cls_str += (
            self.indent
            + "Check whether 'message' is a valid next message in the dialogue.\n\n"
        )
        cls_str += (
            self.indent
            + "These rules capture specific constraints designed for dialogues which are instances of a concrete sub-class of this class.\n"
        )
        cls_str += (
            self.indent
            + "Override this method with your additional dialogue rules.\n\n"
        )
        cls_str += self.indent + ":param message: the message to be validated\n"
        cls_str += self.indent + ":return: True if valid, False otherwise\n"
        cls_str += self.indent + '"""\n'
        cls_str += self.indent + "return True\n\n"
        self._change_indent(-1)

        # initial_performative method
        cls_str += (
            self.indent
            + "def initial_performative(self) -> {}Message.Performative:\n".format(
                self.protocol_specification_in_camel_case
            )
        )
        self._change_indent(1)
        cls_str += self.indent + '"""\n'
        cls_str += (
            self.indent
            + "Get the performative which the initial message in the dialogue must have.\n\n"
        )
        cls_str += self.indent + ":return: the performative of the initial message\n"
        cls_str += self.indent + '"""\n'
        cls_str += self.indent + "return {}Message.Performative.{}\n\n".format(
            self.protocol_specification_in_camel_case, self._initial_performative
        )
        self._change_indent(-1)

        # get_replies method
        cls_str += (
            self.indent + "def get_replies(self, performative: Enum) -> FrozenSet:\n"
        )
        self._change_indent(1)
        cls_str += self.indent + '"""\n'
        cls_str += (
            self.indent
            + "Given a 'performative', return the list of performatives which are its valid replies in a {} dialogue\n\n".format(
                self.protocol_specification.name
            )
        )
        cls_str += self.indent + ":param performative: the performative in a message\n"
        cls_str += self.indent + ":return: list of valid performative replies\n"
        cls_str += self.indent + '"""\n'
        cls_str += (
            self.indent
            + "performative = cast({}Message.Performative, performative)\n".format(
                self.protocol_specification_in_camel_case
            )
        )
        cls_str += (
            self.indent
            + "assert performative in VALID_REPLIES, \"this performative '{}' is not supported\".format(performative)\n"
        )
        cls_str += self.indent + "return VALID_REPLIES[performative]\n\n"
        self._change_indent(-2)
        cls_str += self.indent + "\n"

        # stats class
        cls_str += self.indent + "class {}DialogueStats(object):\n".format(
            self.protocol_specification_in_camel_case
        )
        self._change_indent(1)
        cls_str += (
            self.indent
            + '"""Class to handle statistics on {} dialogues."""\n\n'.format(
                self.protocol_specification.name
            )
        )
        cls_str += self.indent + "def __init__(self) -> None:\n"
        self._change_indent(1)
        cls_str += self.indent + '"""Initialize a StatsManager."""\n'
        cls_str += self.indent + "self._self_initiated = {\n"
        self._change_indent(1)
        for end_state in self._end_states:
            cls_str += self.indent + "{}Dialogue.EndState.{}: 0,\n".format(
                self.protocol_specification_in_camel_case, end_state.upper()
            )
        self._change_indent(-1)
        cls_str += self.indent + "}}  # type: Dict[{}Dialogue.EndState, int]\n".format(
            self.protocol_specification_in_camel_case
        )
        cls_str += self.indent + "self._other_initiated = {\n"
        self._change_indent(1)
        for end_state in self._end_states:
            cls_str += self.indent + "{}Dialogue.EndState.{}: 0,\n".format(
                self.protocol_specification_in_camel_case, end_state.upper()
            )
        self._change_indent(-1)
        cls_str += (
            self.indent
            + "}}  # type: Dict[{}Dialogue.EndState, int]\n\n".format(
                self.protocol_specification_in_camel_case
            )
        )
        self._change_indent(-1)
        cls_str += self.indent + "@property\n"
        cls_str += (
            self.indent
            + "def self_initiated(self) -> Dict[{}Dialogue.EndState, int]:\n".format(
                self.protocol_specification_in_camel_case
            )
        )
        self._change_indent(1)
        cls_str += (
            self.indent
            + '"""Get the stats dictionary on self initiated dialogues."""\n'
        )
        cls_str += self.indent + "return self._self_initiated\n\n"
        self._change_indent(-1)
        cls_str += self.indent + "@property\n"
        cls_str += (
            self.indent
            + "def other_initiated(self) -> Dict[{}Dialogue.EndState, int]:\n".format(
                self.protocol_specification_in_camel_case
            )
        )
        self._change_indent(1)
        cls_str += (
            self.indent
            + '"""Get the stats dictionary on other initiated dialogues."""\n'
        )
        cls_str += self.indent + "return self._other_initiated\n\n"
        self._change_indent(-1)
        cls_str += self.indent + "def add_dialogue_endstate(\n"
        self._change_indent(1)
        cls_str += (
            self.indent
            + "self, end_state: {}Dialogue.EndState, is_self_initiated: bool\n".format(
                self.protocol_specification_in_camel_case
            )
        )
        self._change_indent(-1)
        cls_str += self.indent + ") -> None:\n"
        self._change_indent(1)
        cls_str += self.indent + '"""\n'
        cls_str += self.indent + "Add dialogue endstate stats.\n\n"
        cls_str += self.indent + ":param end_state: the end state of the dialogue\n"
        cls_str += (
            self.indent
            + ":param is_self_initiated: whether the dialogue is initiated by the agent or the opponent\n\n"
        )
        cls_str += self.indent + ":return: None\n"
        cls_str += self.indent + '"""\n'
        cls_str += self.indent + "if is_self_initiated:\n"
        self._change_indent(1)
        cls_str += self.indent + "self._self_initiated[end_state] += 1\n"
        self._change_indent(-1)
        cls_str += self.indent + "else:\n"
        self._change_indent(1)
        cls_str += self.indent + "self._other_initiated[end_state] += 1\n"
        self._change_indent(-3)
        cls_str += self.indent + "\n\n"

        # dialogues class
        cls_str += self.indent + "class {}Dialogues(Dialogues, ABC):\n".format(
            self.protocol_specification_in_camel_case
        )
        self._change_indent(1)
        cls_str += (
            self.indent
            + '"""This class keeps track of all {} dialogues."""\n\n'.format(
                self.protocol_specification.name
            )
        )
        cls_str += self.indent + "def __init__(self, agent_address: Address) -> None:\n"
        self._change_indent(1)
        cls_str += self.indent + '"""\n'
        cls_str += self.indent + "Initialize dialogues.\n\n"
        cls_str += (
            self.indent
            + ":param agent_address: the address of the agent for whom dialogues are maintained\n"
        )
        cls_str += self.indent + ":return: None\n"
        cls_str += self.indent + '"""\n'
        cls_str += (
            self.indent + "Dialogues.__init__(self, agent_address=agent_address)\n"
        )
        cls_str += self.indent + "self._dialogue_stats = {}DialogueStats()\n\n".format(
            self.protocol_specification_in_camel_case
        )
        self._change_indent(-1)
        cls_str += self.indent + "@property\n"
        cls_str += (
            self.indent
            + "def dialogue_stats(self) -> {}DialogueStats:\n".format(
                self.protocol_specification_in_camel_case
            )
        )
        self._change_indent(1)
        cls_str += self.indent + '"""\n'
        cls_str += self.indent + "Get the dialogue statistics.\n\n"
        cls_str += self.indent + ":return: dialogue stats object\n"
        cls_str += self.indent + '"""\n'
        cls_str += self.indent + "return self._dialogue_stats\n\n"
        self._change_indent(-1)
        cls_str += self.indent + "def create_dialogue(\n"
        cls_str += (
            self.indent
            + self.indent
            + "self, dialogue_label: DialogueLabel, role: Dialogue.Role,\n"
        )
        cls_str += self.indent + ") -> {}Dialogue:\n".format(
            self.protocol_specification_in_camel_case
        )
        self._change_indent(1)
        cls_str += self.indent + '"""\n'
        cls_str += self.indent + "Create an instance of fipa dialogue.\n\n"
        cls_str += (
            self.indent + ":param dialogue_label: the identifier of the dialogue\n"
        )
        cls_str += (
            self.indent
            + ":param role: the role of the agent this dialogue is maintained for\n\n"
        )
        cls_str += self.indent + ":return: the created dialogue\n"
        cls_str += self.indent + '"""\n'
        cls_str += self.indent + "dialogue = {}Dialogue(\n".format(
            self.protocol_specification_in_camel_case
        )
        cls_str += (
            self.indent
            + self.indent
            + "dialogue_label=dialogue_label, agent_address=self.agent_address, role=role\n"
        )
        cls_str += self.indent + ")\n"
        cls_str += self.indent + "return dialogue\n"
        self._change_indent(-2)
        cls_str += self.indent + "\n"

        return cls_str

    def _custom_types_module_str(self) -> str:
        """
        Produces the contents of the custom_types module, containing classes corresponding to every custom type in the protocol specification.

        :return: the custom_types.py file content
        """
        self._change_indent(0, "s")

        # Header
        cls_str = _copyright_header_str(self.protocol_specification.author) + "\n"

        # Module docstring
        cls_str += '"""This module contains class representations corresponding to every custom type in the protocol specification."""\n'

        if len(self._all_custom_types) == 0:
            return cls_str

        # class code per custom type
        for custom_type in self._all_custom_types:
            cls_str += self.indent + "\n\nclass {}:\n".format(custom_type)
            self._change_indent(1)
            cls_str += (
                self.indent
                + '"""This class represents an instance of {}."""\n\n'.format(
                    custom_type
                )
            )
            cls_str += self.indent + "def __init__(self):\n"
            self._change_indent(1)
            cls_str += self.indent + '"""Initialise an instance of {}."""\n'.format(
                custom_type
            )
            cls_str += self.indent + "raise NotImplementedError\n\n"
            self._change_indent(-1)
            cls_str += self.indent + "@staticmethod\n"
            cls_str += (
                self.indent
                + 'def encode({}_protobuf_object, {}_object: "{}") -> None:\n'.format(
                    _camel_case_to_snake_case(custom_type),
                    _camel_case_to_snake_case(custom_type),
                    custom_type,
                )
            )
            self._change_indent(1)
            cls_str += self.indent + '"""\n'
            cls_str += (
                self.indent
                + "Encode an instance of this class into the protocol buffer object.\n\n"
            )
            cls_str += (
                self.indent
                + "The protocol buffer object in the {}_protobuf_object argument must be matched with the instance of this class in the '{}_object' argument.\n\n".format(
                    _camel_case_to_snake_case(custom_type),
                    _camel_case_to_snake_case(custom_type),
                )
            )
            cls_str += (
                self.indent
                + ":param {}_protobuf_object: the protocol buffer object whose type corresponds with this class.\n".format(
                    _camel_case_to_snake_case(custom_type)
                )
            )
            cls_str += (
                self.indent
                + ":param {}_object: an instance of this class to be encoded in the protocol buffer object.\n".format(
                    _camel_case_to_snake_case(custom_type)
                )
            )
            cls_str += self.indent + ":return: None\n"
            cls_str += self.indent + '"""\n'
            cls_str += self.indent + "raise NotImplementedError\n\n"
            self._change_indent(-1)

            cls_str += self.indent + "@classmethod\n"
            cls_str += (
                self.indent
                + 'def decode(cls, {}_protobuf_object) -> "{}":\n'.format(
                    _camel_case_to_snake_case(custom_type), custom_type,
                )
            )
            self._change_indent(1)
            cls_str += self.indent + '"""\n'
            cls_str += (
                self.indent
                + "Decode a protocol buffer object that corresponds with this class into an instance of this class.\n\n"
            )
            cls_str += (
                self.indent
                + "A new instance of this class must be created that matches the protocol buffer object in the '{}_protobuf_object' argument.\n\n".format(
                    _camel_case_to_snake_case(custom_type)
                )
            )
            cls_str += (
                self.indent
                + ":param {}_protobuf_object: the protocol buffer object whose type corresponds with this class.\n".format(
                    _camel_case_to_snake_case(custom_type)
                )
            )
            cls_str += (
                self.indent
                + ":return: A new instance of this class that matches the protocol buffer object in the '{}_protobuf_object' argument.\n".format(
                    _camel_case_to_snake_case(custom_type)
                )
            )
            cls_str += self.indent + '"""\n'
            cls_str += self.indent + "raise NotImplementedError\n\n"
            self._change_indent(-1)

            cls_str += self.indent + "def __eq__(self, other):\n"
            self._change_indent(1)
            cls_str += self.indent + "raise NotImplementedError\n"
            self._change_indent(-2)
        return cls_str

    def _encoding_message_content_from_python_to_protobuf(
        self, content_name: str, content_type: str,
    ) -> str:
        """
        Produce the encoding of message contents for the serialisation class.

        :param content_name: the name of the content to be encoded
        :param content_type: the type of the content to be encoded
        :return: the encoding string
        """
        encoding_str = ""
        if content_type in PYTHON_TYPE_TO_PROTO_TYPE.keys():
            encoding_str += self.indent + "{} = msg.{}\n".format(
                content_name, content_name
            )
            encoding_str += self.indent + "performative.{} = {}\n".format(
                content_name, content_name
            )
        elif content_type.startswith("FrozenSet") or content_type.startswith("Tuple"):
            encoding_str += self.indent + "{} = msg.{}\n".format(
                content_name, content_name
            )
            encoding_str += self.indent + "performative.{}.extend({})\n".format(
                content_name, content_name
            )
        elif content_type.startswith("Dict"):
            encoding_str += self.indent + "{} = msg.{}\n".format(
                content_name, content_name
            )
            encoding_str += self.indent + "performative.{}.update({})\n".format(
                content_name, content_name
            )
        elif content_type.startswith("Union"):
            sub_types = _get_sub_types_of_compositional_types(content_type)
            for sub_type in sub_types:
                sub_type_name_in_protobuf = _union_sub_type_to_protobuf_variable_name(
                    content_name, sub_type
                )
                encoding_str += self.indent + 'if msg.is_set("{}"):\n'.format(
                    sub_type_name_in_protobuf
                )
                self._change_indent(1)
                encoding_str += self.indent + "performative.{}_is_set = True\n".format(
                    sub_type_name_in_protobuf
                )
                encoding_str += self._encoding_message_content_from_python_to_protobuf(
                    sub_type_name_in_protobuf, sub_type
                )
                self._change_indent(-1)
        elif content_type.startswith("Optional"):
            sub_type = _get_sub_types_of_compositional_types(content_type)[0]
            if not sub_type.startswith("Union"):
                encoding_str += self.indent + 'if msg.is_set("{}"):\n'.format(
                    content_name
                )
                self._change_indent(1)
                encoding_str += self.indent + "performative.{}_is_set = True\n".format(
                    content_name
                )
            encoding_str += self._encoding_message_content_from_python_to_protobuf(
                content_name, sub_type
            )
            if not sub_type.startswith("Union"):
                self._change_indent(-1)
        else:
            encoding_str += self.indent + "{} = msg.{}\n".format(
                content_name, content_name
            )
            encoding_str += self.indent + "{}.encode(performative.{}, {})\n".format(
                content_type, content_name, content_name
            )
        return encoding_str

    def _decoding_message_content_from_protobuf_to_python(
        self,
        performative: str,
        content_name: str,
        content_type: str,
        variable_name_in_protobuf: Optional[str] = "",
    ) -> str:
        """
        Produce the decoding of message contents for the serialisation class.

        :param performative: the performative to which the content belongs
        :param content_name: the name of the content to be decoded
        :param content_type: the type of the content to be decoded
        :param no_indents: the number of indents based on the previous sections of the code
        :return: the decoding string
        """
        decoding_str = ""
        variable_name = (
            content_name
            if variable_name_in_protobuf == ""
            else variable_name_in_protobuf
        )
        if content_type in PYTHON_TYPE_TO_PROTO_TYPE.keys():
            decoding_str += self.indent + "{} = {}_pb.{}.{}\n".format(
                content_name,
                self.protocol_specification.name,
                performative,
                variable_name,
            )
            decoding_str += self.indent + 'performative_content["{}"] = {}\n'.format(
                content_name, content_name
            )
        elif content_type.startswith("FrozenSet"):
            decoding_str += self.indent + "{} = {}_pb.{}.{}\n".format(
                content_name,
                self.protocol_specification.name,
                performative,
                content_name,
            )
            decoding_str += self.indent + "{}_frozenset = frozenset({})\n".format(
                content_name, content_name
            )
            decoding_str += (
                self.indent
                + 'performative_content["{}"] = {}_frozenset\n'.format(
                    content_name, content_name
                )
            )
        elif content_type.startswith("Tuple"):
            decoding_str += self.indent + "{} = {}_pb.{}.{}\n".format(
                content_name,
                self.protocol_specification.name,
                performative,
                content_name,
            )
            decoding_str += self.indent + "{}_tuple = tuple({})\n".format(
                content_name, content_name
            )
            decoding_str += (
                self.indent
                + 'performative_content["{}"] = {}_tuple\n'.format(
                    content_name, content_name
                )
            )
        elif content_type.startswith("Dict"):
            decoding_str += self.indent + "{} = {}_pb.{}.{}\n".format(
                content_name,
                self.protocol_specification.name,
                performative,
                content_name,
            )
            decoding_str += self.indent + "{}_dict = dict({})\n".format(
                content_name, content_name
            )
            decoding_str += (
                self.indent
                + 'performative_content["{}"] = {}_dict\n'.format(
                    content_name, content_name
                )
            )
        elif content_type.startswith("Union"):
            sub_types = _get_sub_types_of_compositional_types(content_type)
            for sub_type in sub_types:
                sub_type_name_in_protobuf = _union_sub_type_to_protobuf_variable_name(
                    content_name, sub_type
                )
                decoding_str += self.indent + "if {}_pb.{}.{}_is_set:\n".format(
                    self.protocol_specification.name,
                    performative,
                    sub_type_name_in_protobuf,
                )
                self._change_indent(1)
                decoding_str += self._decoding_message_content_from_protobuf_to_python(
                    performative=performative,
                    content_name=content_name,
                    content_type=sub_type,
                    variable_name_in_protobuf=sub_type_name_in_protobuf,
                )
                self._change_indent(-1)
        elif content_type.startswith("Optional"):
            sub_type = _get_sub_types_of_compositional_types(content_type)[0]
            if not sub_type.startswith("Union"):
                decoding_str += self.indent + "if {}_pb.{}.{}_is_set:\n".format(
                    self.protocol_specification.name, performative, content_name
                )
                self._change_indent(1)
                # no_indents += 1
            decoding_str += self._decoding_message_content_from_protobuf_to_python(
                performative, content_name, sub_type
            )
            if not sub_type.startswith("Union"):
                self._change_indent(-1)
        else:
            decoding_str += self.indent + "pb2_{} = {}_pb.{}.{}\n".format(
                variable_name,
                self.protocol_specification.name,
                performative,
                variable_name,
            )
            decoding_str += self.indent + "{} = {}.decode(pb2_{})\n".format(
                content_name, content_type, variable_name,
            )
            decoding_str += self.indent + 'performative_content["{}"] = {}\n'.format(
                content_name, content_name
            )
        return decoding_str

    def _to_custom_custom(self, content_type: str) -> str:
        """
        Evaluate whether a content type is a custom type or has a custom type as a sub-type.
        :return: Boolean result
        """
        new_content_type = content_type
        if _includes_custom_type(content_type):
            for custom_type in self._all_custom_types:
                new_content_type = new_content_type.replace(
                    custom_type, self._custom_custom_types[custom_type]
                )
        return new_content_type

    def _serialization_class_str(self) -> str:
        """
        Produce the content of the Serialization class.

        :return: the serialization.py file content
        """
        self._change_indent(0, "s")

        # Header
        cls_str = _copyright_header_str(self.protocol_specification.author) + "\n"

        # Module docstring
        cls_str += (
            self.indent
            + '"""Serialization module for {} protocol."""\n\n'.format(
                self.protocol_specification.name
            )
        )

        # Imports
        cls_str += self.indent + "from typing import Any, Dict, cast\n\n"
        cls_str += MESSAGE_IMPORT + "\n"
        cls_str += SERIALIZER_IMPORT + "\n\n"
        cls_str += self.indent + "from {} import (\n    {}_pb2,\n)\n".format(
            self.path_to_protocol_package, self.protocol_specification.name,
        )
        for custom_type in self._all_custom_types:
            cls_str += (
                self.indent
                + "from {}.custom_types import (\n    {},\n)\n".format(
                    self.path_to_protocol_package, custom_type,
                )
            )
        cls_str += self.indent + "from {}.message import (\n    {}Message,\n)\n".format(
            self.path_to_protocol_package, self.protocol_specification_in_camel_case,
        )

        # Class Header
        cls_str += self.indent + "\n\nclass {}Serializer(Serializer):\n".format(
            self.protocol_specification_in_camel_case,
        )
        self._change_indent(1)
        cls_str += (
            self.indent
            + '"""Serialization for the \'{}\' protocol."""\n\n'.format(
                self.protocol_specification.name,
            )
        )

        # encoder
        cls_str += self.indent + "def encode(self, msg: Message) -> bytes:\n"
        self._change_indent(1)
        cls_str += self.indent + '"""\n'
        cls_str += self.indent + "Encode a '{}' message into bytes.\n\n".format(
            self.protocol_specification_in_camel_case,
        )
        cls_str += self.indent + ":param msg: the message object.\n"
        cls_str += self.indent + ":return: the bytes.\n"
        cls_str += self.indent + '"""\n'
        cls_str += self.indent + "msg = cast({}Message, msg)\n".format(
            self.protocol_specification_in_camel_case
        )
        cls_str += self.indent + "{}_msg = {}_pb2.{}Message()\n".format(
            self.protocol_specification.name,
            self.protocol_specification.name,
            self.protocol_specification_in_camel_case,
        )
        cls_str += self.indent + "{}_msg.message_id = msg.message_id\n".format(
            self.protocol_specification.name
        )
        cls_str += self.indent + "dialogue_reference = msg.dialogue_reference\n"
        cls_str += (
            self.indent
            + "{}_msg.dialogue_starter_reference = dialogue_reference[0]\n".format(
                self.protocol_specification.name
            )
        )
        cls_str += (
            self.indent
            + "{}_msg.dialogue_responder_reference = dialogue_reference[1]\n".format(
                self.protocol_specification.name
            )
        )
        cls_str += self.indent + "{}_msg.target = msg.target\n\n".format(
            self.protocol_specification.name
        )
        cls_str += self.indent + "performative_id = msg.performative\n"
        counter = 1
        for performative, contents in self._speech_acts.items():
            if counter == 1:
                cls_str += self.indent + "if "
            else:
                cls_str += self.indent + "elif "
            cls_str += "performative_id == {}Message.Performative.{}:\n".format(
                self.protocol_specification_in_camel_case, performative.upper()
            )
            self._change_indent(1)
            cls_str += (
                self.indent
                + "performative = {}_pb2.{}Message.{}_Performative()  # type: ignore\n".format(
                    self.protocol_specification.name,
                    self.protocol_specification_in_camel_case,
                    performative.title(),
                )
            )
            for content_name, content_type in contents.items():
                cls_str += self._encoding_message_content_from_python_to_protobuf(
                    content_name, content_type
                )
            cls_str += self.indent + "{}_msg.{}.CopyFrom(performative)\n".format(
                self.protocol_specification.name, performative
            )

            counter += 1
            self._change_indent(-1)
        cls_str += self.indent + "else:\n"
        self._change_indent(1)
        cls_str += (
            self.indent
            + 'raise ValueError("Performative not valid: {}".format(performative_id))\n\n'
        )
        self._change_indent(-1)

        cls_str += self.indent + "{}_bytes = {}_msg.SerializeToString()\n".format(
            self.protocol_specification.name, self.protocol_specification.name
        )
        cls_str += self.indent + "return {}_bytes\n\n".format(
            self.protocol_specification.name
        )
        self._change_indent(-1)

        # decoder
        cls_str += self.indent + "def decode(self, obj: bytes) -> Message:\n"
        self._change_indent(1)
        cls_str += self.indent + '"""\n'
        cls_str += self.indent + "Decode bytes into a '{}' message.\n\n".format(
            self.protocol_specification_in_camel_case,
        )
        cls_str += self.indent + ":param obj: the bytes object.\n"
        cls_str += self.indent + ":return: the '{}' message.\n".format(
            self.protocol_specification_in_camel_case
        )
        cls_str += self.indent + '"""\n'
        cls_str += self.indent + "{}_pb = {}_pb2.{}Message()\n".format(
            self.protocol_specification.name,
            self.protocol_specification.name,
            self.protocol_specification_in_camel_case,
        )
        cls_str += self.indent + "{}_pb.ParseFromString(obj)\n".format(
            self.protocol_specification.name
        )
        cls_str += self.indent + "message_id = {}_pb.message_id\n".format(
            self.protocol_specification.name
        )
        cls_str += (
            self.indent
            + "dialogue_reference = ({}_pb.dialogue_starter_reference, {}_pb.dialogue_responder_reference)\n".format(
                self.protocol_specification.name, self.protocol_specification.name
            )
        )
        cls_str += self.indent + "target = {}_pb.target\n\n".format(
            self.protocol_specification.name
        )
        cls_str += (
            self.indent
            + 'performative = {}_pb.WhichOneof("performative")\n'.format(
                self.protocol_specification.name
            )
        )
        cls_str += (
            self.indent
            + "performative_id = {}Message.Performative(str(performative))\n".format(
                self.protocol_specification_in_camel_case
            )
        )
        cls_str += (
            self.indent + "performative_content = dict()  # type: Dict[str, Any]\n"
        )
        counter = 1
        for performative, contents in self._speech_acts.items():
            if counter == 1:
                cls_str += self.indent + "if "
            else:
                cls_str += self.indent + "elif "
            cls_str += "performative_id == {}Message.Performative.{}:\n".format(
                self.protocol_specification_in_camel_case, performative.upper()
            )
            self._change_indent(1)
            if len(contents.keys()) == 0:
                cls_str += self.indent + "pass\n"
            else:
                for content_name, content_type in contents.items():
                    cls_str += self._decoding_message_content_from_protobuf_to_python(
                        performative, content_name, content_type
                    )
            counter += 1
            self._change_indent(-1)
        cls_str += self.indent + "else:\n"
        self._change_indent(1)
        cls_str += (
            self.indent
            + 'raise ValueError("Performative not valid: {}.".format(performative_id))\n\n'
        )
        self._change_indent(-1)

        cls_str += self.indent + "return {}Message(\n".format(
            self.protocol_specification_in_camel_case,
        )
        self._change_indent(1)
        cls_str += self.indent + "message_id=message_id,\n"
        cls_str += self.indent + "dialogue_reference=dialogue_reference,\n"
        cls_str += self.indent + "target=target,\n"
        cls_str += self.indent + "performative=performative,\n"
        cls_str += self.indent + "**performative_content\n"
        self._change_indent(-1)
        cls_str += self.indent + ")\n"
        self._change_indent(-2)

        return cls_str

    def _content_to_proto_field_str(
        self, content_name: str, content_type: str, tag_no: int,
    ) -> Tuple[str, int]:
        """
        Convert a message content to its representation in a protocol buffer schema.

        :param content_name: the name of the content
        :param content_type: the type of the content
        :param content_type: the tag number
        :return: the content in protocol buffer schema
        """
        entry = ""

        if content_type.startswith("FrozenSet") or content_type.startswith(
            "Tuple"
        ):  # it is a <PCT>
            element_type = _get_sub_types_of_compositional_types(content_type)[0]
            proto_type = _python_pt_or_ct_type_to_proto_type(element_type)
            entry = self.indent + "repeated {} {} = {};\n".format(
                proto_type, content_name, tag_no
            )
            tag_no += 1
        elif content_type.startswith("Dict"):  # it is a <PMT>
            key_type = _get_sub_types_of_compositional_types(content_type)[0]
            value_type = _get_sub_types_of_compositional_types(content_type)[1]
            proto_key_type = _python_pt_or_ct_type_to_proto_type(key_type)
            proto_value_type = _python_pt_or_ct_type_to_proto_type(value_type)
            entry = self.indent + "map<{}, {}> {} = {};\n".format(
                proto_key_type, proto_value_type, content_name, tag_no
            )
            tag_no += 1
        elif content_type.startswith("Union"):  # it is an <MT>
            sub_types = _get_sub_types_of_compositional_types(content_type)
            for sub_type in sub_types:
                sub_type_name = _union_sub_type_to_protobuf_variable_name(
                    content_name, sub_type
                )
                content_to_proto_field_str, tag_no = self._content_to_proto_field_str(
                    sub_type_name, sub_type, tag_no
                )
                entry += content_to_proto_field_str
        elif content_type.startswith("Optional"):  # it is an <O>
            sub_type = _get_sub_types_of_compositional_types(content_type)[0]
            content_to_proto_field_str, tag_no = self._content_to_proto_field_str(
                content_name, sub_type, tag_no
            )
            entry = content_to_proto_field_str
            entry += self.indent + "bool {}_is_set = {};\n".format(content_name, tag_no)
            tag_no += 1
        else:  # it is a <CT> or <PT>
            proto_type = _python_pt_or_ct_type_to_proto_type(content_type)
            entry = self.indent + "{} {} = {};\n".format(
                proto_type, content_name, tag_no
            )
            tag_no += 1
        return entry, tag_no

    def _protocol_buffer_schema_str(self) -> str:
        """
        Produce the content of the Protocol Buffers schema.

        :return: the protocol buffers schema content
        """
        self._change_indent(0, "s")

        # heading
        proto_buff_schema_str = self.indent + 'syntax = "proto3";\n\n'
        proto_buff_schema_str += self.indent + "package fetch.aea.{};\n\n".format(
            self.protocol_specification_in_camel_case
        )
        proto_buff_schema_str += self.indent + "message {}Message{{\n\n".format(
            self.protocol_specification_in_camel_case
        )
        self._change_indent(1)

        # custom types
        if (
            (len(self._all_custom_types) != 0)
            and (self.protocol_specification.protobuf_snippets is not None)
            and (self.protocol_specification.protobuf_snippets != "")
        ):
            proto_buff_schema_str += self.indent + "// Custom Types\n"
            for custom_type in self._all_custom_types:
                proto_buff_schema_str += self.indent + "message {}{{\n".format(
                    custom_type
                )
                self._change_indent(1)

                # formatting and adding the custom type protobuf entry
                specification_custom_type = "ct:" + custom_type
                proto_part = self.protocol_specification.protobuf_snippets[
                    specification_custom_type
                ]
                number_of_new_lines = proto_part.count("\n")
                if number_of_new_lines != 0:
                    formatted_proto_part = proto_part.replace(
                        "\n", "\n" + self.indent, number_of_new_lines - 1
                    )
                else:
                    formatted_proto_part = proto_part
                proto_buff_schema_str += self.indent + formatted_proto_part
                self._change_indent(-1)

                proto_buff_schema_str += self.indent + "}\n\n"
            proto_buff_schema_str += "\n"

        # performatives
        proto_buff_schema_str += self.indent + "// Performatives and contents\n"
        for performative, contents in self._speech_acts.items():
            proto_buff_schema_str += self.indent + "message {}_Performative{{".format(
                performative.title()
            )
            self._change_indent(1)
            tag_no = 1
            if len(contents) == 0:
                proto_buff_schema_str += "}\n\n"
                self._change_indent(-1)
            else:
                proto_buff_schema_str += "\n"
                for content_name, content_type in contents.items():
                    (
                        content_to_proto_field_str,
                        tag_no,
                    ) = self._content_to_proto_field_str(
                        content_name, content_type, tag_no
                    )
                    proto_buff_schema_str += content_to_proto_field_str
                self._change_indent(-1)
                proto_buff_schema_str += self.indent + "}\n\n"
        proto_buff_schema_str += "\n"
        # self._change_indent(-1)

        # meta-data
        proto_buff_schema_str += self.indent + "// Standard {}Message fields\n".format(
            self.protocol_specification_in_camel_case
        )
        proto_buff_schema_str += self.indent + "int32 message_id = 1;\n"
        proto_buff_schema_str += (
            self.indent + "string dialogue_starter_reference = 2;\n"
        )
        proto_buff_schema_str += (
            self.indent + "string dialogue_responder_reference = 3;\n"
        )
        proto_buff_schema_str += self.indent + "int32 target = 4;\n"
        proto_buff_schema_str += self.indent + "oneof performative{\n"
        self._change_indent(1)
        tag_no = 5
        for performative in self._all_performatives:
            proto_buff_schema_str += self.indent + "{}_Performative {} = {};\n".format(
                performative.title(), performative, tag_no
            )
            tag_no += 1
        self._change_indent(-1)
        proto_buff_schema_str += self.indent + "}\n"
        self._change_indent(-1)

        proto_buff_schema_str += self.indent + "}\n"
        return proto_buff_schema_str

    def _protocol_yaml_str(self) -> str:
        """
        Produce the content of the protocol.yaml file.

        :return: the protocol.yaml content
        """
        protocol_yaml_str = "name: {}\n".format(self.protocol_specification.name)
        protocol_yaml_str += "author: {}\n".format(self.protocol_specification.author)
        protocol_yaml_str += "version: {}\n".format(self.protocol_specification.version)
        protocol_yaml_str += "description: {}\n".format(
            self.protocol_specification.description
        )
        protocol_yaml_str += "license: {}\n".format(self.protocol_specification.license)
        protocol_yaml_str += "aea_version: '{}'\n".format(
            self.protocol_specification.aea_version
        )
        protocol_yaml_str += "fingerprint: {}\n"
        protocol_yaml_str += "fingerprint_ignore_patterns: []\n"
        protocol_yaml_str += "dependencies:\n"
        protocol_yaml_str += "    protobuf: {}\n"

        return protocol_yaml_str

    def _init_str(self) -> str:
        """
        Produce the content of the __init__.py file.

        :return: the __init__.py content
        """
        init_str = _copyright_header_str(self.protocol_specification.author)
        init_str += "\n"
        init_str += '"""This module contains the support resources for the {} protocol."""\n'.format(
            self.protocol_specification.name
        )

        return init_str

    def _generate_file(self, file_name: str, file_content: str) -> None:
        """
        Create a protocol file.

        :return: None
        """
        pathname = path.join(self.output_folder_path, file_name)

        with open(pathname, "w") as file:
            file.write(file_content)

    def generate(self) -> None:
        """
        Create the protocol package with Message, Serialization, __init__, protocol.yaml files.

        :return: None
        """
        # Create the output folder
        output_folder = Path(self.output_folder_path)
        if not output_folder.exists():
            os.mkdir(output_folder)

        # Generate the protocol files
        self._generate_file(INIT_FILE_NAME, self._init_str())
        self._generate_file(PROTOCOL_YAML_FILE_NAME, self._protocol_yaml_str())
        self._generate_file(MESSAGE_DOT_PY_FILE_NAME, self._message_class_str())
        if (
            self.protocol_specification.dialogue_config is not None
            and self.protocol_specification.dialogue_config != {}
        ):
            self._generate_file(DIALOGUE_DOT_PY_FILE_NAME, self._dialogue_class_str())
        if len(self._all_custom_types) > 0:
            self._generate_file(
                CUSTOM_TYPES_DOT_PY_FILE_NAME, self._custom_types_module_str()
            )
        self._generate_file(
            SERIALIZATION_DOT_PY_FILE_NAME, self._serialization_class_str()
        )
        self._generate_file(
            "{}.proto".format(self.protocol_specification.name),
            self._protocol_buffer_schema_str(),
        )

        # Warn if specification has custom types
        if len(self._all_custom_types) > 0:
            incomplete_generation_warning_msg = "The generated protocol is incomplete, because the protocol specification contains the following custom types: {}. Update the generated '{}' file with the appropriate implementations of these custom types.".format(
                self._all_custom_types, CUSTOM_TYPES_DOT_PY_FILE_NAME
            )
            logger.warning(incomplete_generation_warning_msg)

        # Compile protobuf schema
        cmd = "protoc -I={} --python_out={} {}/{}.proto".format(
            self.output_folder_path,
            self.output_folder_path,
            self.output_folder_path,
            self.protocol_specification.name,
        )
        os.system(cmd)  # nosec
