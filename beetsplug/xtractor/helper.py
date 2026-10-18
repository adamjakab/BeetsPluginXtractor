#  Copyright: Copyright (c) 2020., Adam Jakab
#  Author: Adam Jakab <adam at jakab dot pro>
#  License: See LICENSE.txt

import json
import logging
import os

from confuse import ConfigError, Subview

# Get values as: plg_ns['__PLUGIN_NAME__']
plg_ns = {}
about_path = os.path.join(os.path.dirname(__file__), u'about.py')
with open(about_path) as about_file:
    exec(about_file.read(), plg_ns)

__logger__ = logging.getLogger(
    'beets.{plg}'.format(plg=plg_ns['__PLUGIN_NAME__']))


CANONICAL_UPDATE_POLICIES = ["force", "if_empty", "if_similar", "never"]
CANONICAL_TYPES = ["integer", "float", "string"]
NUMERIC_TYPES = ["integer", "float"]


def get_field_prefix(config: Subview):
    return config["field_prefix"].get() or ""


def get_canonical_targets(config: Subview):
    """collects the `canonical` settings of the targets in
    `low_level_targets` / `high_level_targets`, keyed by the target name
    """
    canonical_targets = {}
    for map_key in ["low_level_targets", "high_level_targets"]:
        target_map = config[map_key]
        for fld in target_map:
            canonical = target_map[fld]["canonical"]
            if not canonical.exists():
                continue

            value_type = target_map[fld]["type"].get()
            if value_type not in CANONICAL_TYPES:
                raise ConfigError("{}.{}.canonical: only available for the types {}".format(
                    map_key, fld, ", ".join(CANONICAL_TYPES)))

            update_policy = canonical["update_policy"].as_choice(CANONICAL_UPDATE_POLICIES) \
                if canonical["update_policy"].exists() else "force"
            max_difference = None
            if value_type in NUMERIC_TYPES:
                max_difference = parse_max_difference(canonical["max_difference"]) \
                    if canonical["max_difference"].exists() else (0, False)
            elif update_policy == "if_similar" or canonical["max_difference"].exists():
                raise ConfigError("{}.{}.canonical: if_similar and max_difference need a numeric type".format(
                    map_key, fld))

            canonical_targets[fld] = {
                "field": canonical["field"].as_str() if canonical["field"].exists() else fld,
                "update_policy": update_policy,
                "max_difference": max_difference,
            }

    return canonical_targets


def parse_max_difference(max_difference: Subview):
    """returns an absolute difference as a number and a relative one
    (like "4%") as a fraction of the extracted value, e.g. ("4%" -> 0.04, True)
    """
    value = max_difference.get()
    relative = isinstance(value, str) and value.strip().endswith("%")
    try:
        number = float(value.strip()[:-1]) / 100 if relative else max_difference.as_number()
    except ValueError:
        number = None
    if isinstance(number, bool) or number is None or number < 0:
        raise ConfigError("{}: must be a positive number or a percentage like 4%, not {!r}".format(
            max_difference.name, value))

    return number, relative


def get_max_difference(canonical, extracted_value):
    """the allowed difference to the extracted value for `if_similar`"""
    number, relative = canonical["max_difference"]
    return abs(extracted_value) * number if relative else number


def extract_from_output(output_path, target_map: Subview):
    """extracts data from the json file as mapped out in the
    `low_level_targets` / `high_level_targets` configuration keys
    """
    data = {}

    if os.path.isfile(output_path):
        with open(output_path, "r") as json_file:
            audiodata = json.load(json_file)
            for key in target_map.keys():
                try:
                    val = extract_value_from_audiodata(audiodata, target_map[key])
                except AttributeError:
                    val = None

                data[key] = val
    else:
        raise FileNotFoundError("Output file({}) not found!".format(output_path))

    return data


def extract_value_from_audiodata(audiodata, target_map_item: Subview):
    path: str = target_map_item["path"].as_str()
    value_type = target_map_item["type"].as_str()
    path_parts = path.split(".")
    for part in path_parts:
        if not part in audiodata:
            raise AttributeError("No path '{}' found in audiodata".format(path))
        audiodata = audiodata[part]

    if value_type == "string":
        value = str(audiodata)
    elif value_type == "float":
        value = float(audiodata)
    elif value_type == "integer":
        value = int(round(float(audiodata)))
    else:
        value = audiodata

    return value


def asciify_file_content(file_path):
    if os.path.isfile(file_path):
        with open(file_path, 'r', encoding="utf-8") as content_file:
            content_orig = content_file.read()

        content_enc = content_orig.encode('ascii', 'ignore').decode('ascii')
        if content_orig != content_enc:
            with open(file_path, 'w', encoding="ascii") as content_file:
                content_file.write(content_enc)


def say(msg, log_only=True, is_error=False):
    _level = logging.DEBUG
    _level = _level if log_only else logging.INFO
    _level = _level if not is_error else logging.ERROR
    __logger__.log(level=_level, msg=msg)
