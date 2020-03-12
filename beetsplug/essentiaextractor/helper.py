#  Copyright: Copyright (c) 2020., Adam Jakab
#
#  Author: Adam Jakab <adam at jakab dot pro>
#  Created: 3/12/20, 11:42 PM
#  License: See LICENSE.txt
#
#  Author: Adam Jakab <adam at jakab dot pro>
#  Created: 3/12/20, 4:15 PM
#  License: See LICENSE.txt

import hashlib
import json
import os
import sys
import tempfile

from beets.library import Item

_module_path = os.path.dirname(__file__)

"""Checklist from Acousticbrainz plugin: 

average_loudness            X
bpm                         OK
chords_changes_rate         X
chords_key                  X
chords_number_rate          X
chords_scale                X
danceable                   OK
gender                      OK (!!!)
genre_rosamerica            OK
initial_key                 X
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
voice_instrumental          X
"""


def extract_high_level_data(output_path):
    data = {}

    if os.path.isfile(output_path):
        with open(output_path, "r") as json_file:
            audiodata = json.load(json_file)
            if "highlevel" in audiodata:
                highlevel = audiodata["highlevel"]

                if "danceability" in highlevel:
                    data['danceable'] = float(highlevel["danceability"]["all"]["danceable"])
                else:
                    raise KeyError("No 'danceability' data for: {}".format(output_path))

                if "gender" in highlevel:
                    data['gender'] = highlevel["gender"]["value"]
                    data['is_male'] = float(highlevel["gender"]["all"]["male"])
                    data['is_female'] = float(highlevel["gender"]["all"]["female"])
                else:
                    raise KeyError("No 'gender' data for: {}".format(output_path))

                if "genre_rosamerica" in highlevel:
                    data['genre_rosamerica'] = highlevel["genre_rosamerica"]["value"]
                else:
                    raise KeyError("No 'genre_rosamerica' data for: {}".format(output_path))

                if "voice_instrumental" in highlevel:
                    data['voice_instrumental'] = highlevel["voice_instrumental"]["value"]
                    data['is_voice'] = float(highlevel["voice_instrumental"]["all"]["voice"])
                    data['is_instrumental'] = float(highlevel["voice_instrumental"]["all"]["instrumental"])
                else:
                    raise KeyError("No 'voice_instrumental' data for: {}".format(output_path))

                if "mood_acoustic" in highlevel:
                    data['mood_acoustic'] = float(highlevel["mood_acoustic"]["all"]["acoustic"])
                else:
                    raise KeyError("No 'mood_acoustic' data for: {}".format(output_path))

                if "mood_aggressive" in highlevel:
                    data['mood_aggressive'] = float(highlevel["mood_aggressive"]["all"]["aggressive"])
                else:
                    raise KeyError("No 'mood_aggressive' data for: {}".format(output_path))

                if "mood_electronic" in highlevel:
                    data['mood_electronic'] = float(highlevel["mood_electronic"]["all"]["electronic"])
                else:
                    raise KeyError("No 'mood_electronic' data for: {}".format(output_path))

                if "mood_happy" in highlevel:
                    data['mood_happy'] = float(highlevel["mood_happy"]["all"]["happy"])
                else:
                    raise KeyError("No 'mood_happy' data for: {}".format(output_path))

                if "mood_party" in highlevel:
                    data['mood_party'] = float(highlevel["mood_party"]["all"]["party"])
                else:
                    raise KeyError("No 'mood_party' data for: {}".format(output_path))

                if "mood_relaxed" in highlevel:
                    data['mood_relaxed'] = float(highlevel["mood_relaxed"]["all"]["relaxed"])
                else:
                    raise KeyError("No 'mood_relaxed' data for: {}".format(output_path))

                if "mood_sad" in highlevel:
                    data['mood_sad'] = float(highlevel["mood_sad"]["all"]["sad"])
                else:
                    raise KeyError("No 'mood_sad' data for: {}".format(output_path))

            else:
                raise KeyError("No high level data for: {}".format(output_path))
    else:
        raise FileNotFoundError("Output file({}) not found!".format(output_path))

    return data


def extract_low_level_data(output_path):
    data = {}

    if os.path.isfile(output_path):
        with open(output_path, "r") as json_file:
            audiodata = json.load(json_file)
            if "rhythm" in audiodata and "bpm" in audiodata["rhythm"]:
                bpm = round(float(audiodata["rhythm"]["bpm"]))
                data['bpm'] = bpm
            else:
                raise AttributeError("No Bpm data for: {}".format(output_path))
    else:
        raise FileNotFoundError("Output file({}) not found!".format(output_path))

    return data


def _get_extraction_output_path():
    extraction_output_path = os.path.join(tempfile.gettempdir(), "ee")

    if not os.path.isdir(extraction_output_path):
        os.makedirs(extraction_output_path)

    return extraction_output_path


def get_output_path_for_item(item: Item, clear=False, suffix=""):
    input_path = get_input_path_for_item(item)
    output_file = hashlib.md5(input_path.encode('utf-8')).hexdigest()
    output_file += ".{}".format(suffix) if suffix else ""
    output_file += ".json"
    output_path = os.path.join(_get_extraction_output_path(), output_file)

    if os.path.isfile(output_path) and clear:
        os.unlink(output_path)

    return output_path


def get_input_path_for_item(item: Item):
    input_path = item.get("path").decode("utf-8")

    if not os.path.isfile(input_path):
        raise FileNotFoundError("Input file({}) not found!".format(input_path))

    return input_path


def get_extractor_path_svm():
    extractor_folder = os.path.join(_module_path, "extractors")
    extractors_by_platform = {
        "darwin": "osx_x86_64_streaming_extractor_music_svm",
    }
    if not sys.platform in extractors_by_platform:
        raise NotImplementedError("There is no extractor for your platform({})!".format(sys.platform))

    extractor_path = os.path.join(extractor_folder, extractors_by_platform[sys.platform])

    if not os.path.isfile(extractor_path):
        raise FileNotFoundError("Extractor({}) not found!".format(extractor_path))

    return extractor_path


def get_extractor_path():
    extractor_folder = os.path.join(_module_path, "extractors")
    extractors_by_platform = {
        "darwin": "osx_x86_64_streaming_extractor_music",
        "linux": "linux_x86_64_streaming_extractor_music",
        "win32": "win_i686_streaming_extractor_music.exe",
    }
    if not sys.platform in extractors_by_platform:
        raise NotImplementedError("There is no extractor for your platform({})!".format(sys.platform))

    extractor_path = os.path.join(extractor_folder, extractors_by_platform[sys.platform])

    if not os.path.isfile(extractor_path):
        raise FileNotFoundError("Extractor({}) not found!".format(extractor_path))

    return extractor_path


def get_extractor_profile_path_svm():
    profile_folder = _module_path
    profile_path = os.path.join(profile_folder, "extractor_profile_svm.yml")

    if not os.path.isfile(profile_path):
        raise FileNotFoundError("Extractor profile({}) not found!".format(profile_path))

    return profile_path


def get_extractor_profile_path():
    profile_folder = _module_path
    profile_path = os.path.join(profile_folder, "extractor_profile.yml")

    if not os.path.isfile(profile_path):
        raise FileNotFoundError("Extractor profile({}) not found!".format(profile_path))

    return profile_path
