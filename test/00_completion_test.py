#  Copyright: Copyright (c) 2020., Adam Jakab
#
#  Author: Adam Jakab <adam at jakab dot pro>
#  Created: 3/12/20, 11:42 PM
#  License: See LICENSE.txt
import re

from test.helper import TestHelper, Assertions, PLUGIN_NAME, PLUGIN_SHORT_NAME, PLUGIN_SHORT_DESCRIPTION, capture_stdout


class CompletionTest(TestHelper, Assertions):
    """Test invocation of ``beet goingrunning`` with this plugin.
    Only ensures that command does not fail.
    """

    def test_application(self):
        with capture_stdout() as out:
            self.runcli()

        expected = "{0} \\({1}\\) +?{2}".format(
            re.escape(PLUGIN_NAME),
            re.escape(PLUGIN_SHORT_NAME),
            re.escape(PLUGIN_SHORT_DESCRIPTION)
        )

        self.assertRegex(out.getvalue(), expected)

    def test_application_plugin_list(self):
        with capture_stdout() as out:
            self.runcli("version")

        self.assertIn("plugins: {0}".format(PLUGIN_NAME), out.getvalue())

