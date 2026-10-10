#  Copyright: Copyright (c) 2020., Adam Jakab
#
#  Author: Adam Jakab <adam at jakab dot pro>
#  Created: 3/13/20, 12:17 AM
#  License: See LICENSE.txt

import os

from beets.plugins import BeetsPlugin
from beets.dbcore import types
from beets.library import Item
from confuse import ConfigSource, load_yaml
from beetsplug.xtractor import helper
from beetsplug.xtractor.command import XtractorCommand


class XtractorPlugin(BeetsPlugin):
    _default_plugin_config_file_name_ = 'config_default.yml'
    _target_types = {
        'float': types.Float(6),
        'integer': types.INTEGER,
        'string': types.STRING,
    }

    def __init__(self):
        super(XtractorPlugin, self).__init__()
        config_file_path = os.path.join(os.path.dirname(__file__), self._default_plugin_config_file_name_)
        source = ConfigSource(load_yaml(config_file_path) or {}, config_file_path)
        self.config.add(source)
        self.item_types = self._build_item_types()

        # @todo: activate this to store the attributes in media files
        # field = mediafile.MediaField(
        #     mediafile.MP3DescStorageStyle(u'danceability'), mediafile.StorageStyle(u'danceability')
        # )
        # self.add_media_field('danceability', field)
        #
        # field = mediafile.MediaField(
        #     mediafile.MP3DescStorageStyle(u'beats_count'), mediafile.StorageStyle(u'beats_count')
        # )
        # self.add_media_field('beats_count', field)

    def _build_item_types(self):
        """registers the type of each field defined in the
        `low_level_targets` / `high_level_targets` configuration keys
        """
        prefix = helper.get_field_prefix(self.config)
        item_types = {}
        for map_key in ["low_level_targets", "high_level_targets"]:
            if not self.config[map_key].exists():
                continue
            for fld, target in self.config[map_key].flatten().items():
                target_type = self._target_types.get((target or {}).get("type"))
                # Fields of beets itself (like `bpm`) already have their type
                if target_type and prefix + fld not in Item._fields:
                    item_types[prefix + fld] = target_type

        return item_types

    def commands(self):
        return [XtractorCommand(self.config)]
