#  Copyright: Copyright (c) 2020., Adam Jakab
#
#  Author: Adam Jakab <adam at jakab dot pro>
#  Created: 3/13/20, 12:17 AM
#  License: See LICENSE.txt

import os

from beets.plugins import BeetsPlugin
from beets.dbcore import types
from confuse import ConfigSource, load_yaml
from beetsplug.xtractor.command import XtractorCommand


class XtractorPlugin(BeetsPlugin):
    _default_plugin_config_file_name_ = 'config_default.yml'

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
        """Build the `item_types` mapping beets uses to know the data type of
        each flexible attribute this plugin writes (e.g. for `-f`/`-F`
        formatting and typed queries like `danceable::0.5..1`).

        - Field names are taken from `low_level_targets`/`high_level_targets`.
        - Apply field_rename so types are registered under the actual attribute
          name (not the config key); otherwise the real field remains untyped
          while the renamed key is typed but unused.
        - Defaults to float when a target has no explicit `type`.
        """
        type_map = {
            'float': types.Float(6),
            'integer': types.INTEGER,
            'string': types.STRING,
        }
        cfg = self.config.flatten()
        renames = cfg.get('field_rename') or {}
        item_types = {}
        for map_key in ['low_level_targets', 'high_level_targets']:
            if not self.config[map_key].exists():
                continue
            target_map = self.config[map_key]
            for fld in target_map:
                type_str = target_map[fld]['type'].as_str() if target_map[fld]['type'].exists() else 'float'
                beets_type = type_map.get(type_str, types.Float(6))
                field_name = renames.get(fld, fld)
                item_types[field_name] = beets_type
        return item_types

    def commands(self):
        return [XtractorCommand(self.config)]
