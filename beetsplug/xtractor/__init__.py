#  Copyright: Copyright (c) 2020., Adam Jakab
#
#  Author: Adam Jakab <adam at jakab dot pro>
#  Created: 3/13/20, 12:17 AM
#  License: See LICENSE.txt

from beets.plugins import BeetsPlugin
from beets.util import cpu_count

from beetsplug.xtractor.command import XtractorCommand


class XtractorPlugin(BeetsPlugin):
    def __init__(self):
        super(XtractorPlugin, self).__init__()
        self.config.add({
            'auto': False,
            'dry-run': False,
            'write': True,
            'threads': cpu_count(),
            'force': False,
            'quiet': False
        })

    def commands(self):
        return [XtractorCommand(self.config)]
