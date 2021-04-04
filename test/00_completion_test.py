#  Copyright: Copyright (c) 2020., Adam Jakab
#
#  Author: Adam Jakab <adam at jakab dot pro>
#  Created: 3/12/20, 11:42 PM
#  License: See LICENSE.txt

from beetsplug.xtractor import about

from test.helper import TestHelper, Assertions, \
    PLUGIN_NAME, PLUGIN_SHORT_DESCRIPTION, \
    PACKAGE_NAME, PACKAGE_TITLE, PLUGIN_VERSION, \
    capture_log

plg_log_ns = 'beets.{}'.format(PLUGIN_NAME)


class CompletionTest(TestHelper, Assertions):
    """Test invocation of the plugin and basic package health.
    """

    def test_about_descriptor_file(self):
        self.assertTrue(hasattr(about, "__author__"))
        self.assertTrue(hasattr(about, "__email__"))
        self.assertTrue(hasattr(about, "__copyright__"))
        self.assertTrue(hasattr(about, "__license__"))
        self.assertTrue(hasattr(about, "__version__"))
        self.assertTrue(hasattr(about, "__status__"))
        self.assertTrue(hasattr(about, "__PACKAGE_TITLE__"))
        self.assertTrue(hasattr(about, "__PACKAGE_NAME__"))
        self.assertTrue(hasattr(about, "__PACKAGE_DESCRIPTION__"))
        self.assertTrue(hasattr(about, "__PACKAGE_URL__"))
        self.assertTrue(hasattr(about, "__PLUGIN_NAME__"))
        self.assertTrue(hasattr(about, "__PLUGIN_ALIAS__"))
        self.assertTrue(hasattr(about, "__PLUGIN_SHORT_DESCRIPTION__"))

    def test_application(self):
        output = self.runcli()
        self.assertIn(PLUGIN_NAME, output)
        self.assertIn(PLUGIN_SHORT_DESCRIPTION, output)

    def test_application_plugin_list(self):
        output = self.runcli("version")
        self.assertIn("plugins: {0}".format(PLUGIN_NAME), output)

    def test_run_plugin(self):
        with capture_log(plg_log_ns) as logs:
            self.runcli(PLUGIN_NAME)
        self.assertIn("xtractor: No items to process", "\n".join(logs))

    def test_plugin_version(self):
        with capture_log(plg_log_ns) as logs:
            self.runcli(PLUGIN_NAME, "--version")

        versioninfo = "{pt}({pn}) plugin for Beets: v{ver}".format(
            pt=PACKAGE_TITLE,
            pn=PACKAGE_NAME,
            ver=PLUGIN_VERSION
        )
        self.assertIn(versioninfo, "\n".join(logs))
