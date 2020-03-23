#  Copyright: Copyright (c) 2020., Adam Jakab
#
#  Author: Adam Jakab <adam at jakab dot pro>
#  Created: 3/13/20, 12:17 AM
#  License: See LICENSE.txt

import os

from beets.plugins import BeetsPlugin
from beets.util.confit import ConfigSource, load_yaml

from beetsplug.xtractor.command import XtractorCommand


class XtractorPlugin(BeetsPlugin):
    _default_plugin_config_file_name_ = 'config_default.yml'

    def __init__(self):
        super(XtractorPlugin, self).__init__()
        config_file_path = os.path.join(os.path.dirname(__file__), self._default_plugin_config_file_name_)
        source = ConfigSource(load_yaml(config_file_path) or {}, config_file_path)
        self.config.add(source)

    def commands(self):
        return [XtractorCommand(self.config)]
