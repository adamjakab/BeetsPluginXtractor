#  Copyright: Copyright (c) 2020., Adam Jakab
#
#  Author: Adam Jakab <adam at jakab dot pro>
#  Created: 3/13/20, 12:17 AM
#  License: See LICENSE.txt

import json
import os

from confuse import Subview

_module_path = os.path.dirname(__file__)

"""Checklist from Acousticbrainz plugin: 
ITEM
bpm                         OK
initial_key                 X ???

ATTRIBUTE:
average_loudness            OK
beets_count                 OK (extra)
chords_changes_rate         X
chords_key                  X
chords_number_rate          X
chords_scale                X
danceable                   OK
danceability                OK (extra)
gender                      OK (!!!)
genre_rosamerica            OK
key_strength                X
mood_acoustic               OK
mood_aggressive             OK
mood_electronic             OK
mood_happy                  OK
mood_party                  OK
mood_relaxed                OK
mood_sad                    OK
rhythm                      X
tonal                       X
voice_instrumental          OK
"""


def extract_from_output(output_path, target_map: Subview):
    """extracts data from the low level json file as mapped out in the `low_level_targets` configuration key
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
