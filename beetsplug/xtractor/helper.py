#  Copyright: Copyright (c) 2020., Adam Jakab
#  Author: Adam Jakab <adam at jakab dot pro>
#  License: See LICENSE.txt

import json
import logging
import os

from confuse import Subview

# Get values as: plg_ns['__PLUGIN_NAME__']
plg_ns = {}
about_path = os.path.join(os.path.dirname(__file__), u'about.py')
with open(about_path) as about_file:
    exec(about_file.read(), plg_ns)

__logger__ = logging.getLogger(
    'beets.{plg}'.format(plg=plg_ns['__PLUGIN_NAME__']))


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
