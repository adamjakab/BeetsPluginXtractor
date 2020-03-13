#  Copyright: Copyright (c) 2020., Adam Jakab
#
#  Author: Adam Jakab <adam at jakab dot pro>
#  Created: 3/13/20, 12:17 AM
#  License: See LICENSE.txt

import json
import os

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
