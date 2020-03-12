#  Copyright: Copyright (c) 2020., Adam Jakab
#
#  Author: Adam Jakab <adam at jakab dot pro>
#  Created: 3/13/20, 12:17 AM
#  License: See LICENSE.txt
#
#  Author: Adam Jakab <adam at jakab dot pro>
#  Created: 3/12/20, 11:42 PM
#  License: See LICENSE.txt


from beets.plugins import BeetsPlugin
from beets.util import cpu_count

from beetsplug.xtractor.command import EssentiaExtractorCommand


class EssentiaExtractorPlugin(BeetsPlugin):
    def __init__(self):
        super(EssentiaExtractorPlugin, self).__init__()
        self.config.add({
            'auto': False,
            'dry-run': False,
            'write': True,
            'threads': cpu_count(),
            'force': False,
            'quiet': False
        })

    def commands(self):
        return [EssentiaExtractorCommand(self.config)]
