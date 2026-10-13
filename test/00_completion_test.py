#  Copyright: Copyright (c) 2020., Adam Jakab
#
#  Author: Adam Jakab <adam at jakab dot pro>
#  Created: 3/12/20, 11:42 PM
#  License: See LICENSE.txt

from unittest.mock import patch

from beets.library import Item
from beetsplug.xtractor import about
from beetsplug.xtractor.command import XtractorCommand

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
        self.assertIn("No items to process", "\n".join(logs))

    def test_plugin_version(self):
        with capture_log(plg_log_ns) as logs:
            self.runcli(PLUGIN_NAME, "--version")

        versioninfo = "{pt}({pn}) plugin for Beets: v{ver}".format(
            pt=PACKAGE_TITLE,
            pn=PACKAGE_NAME,
            ver=PLUGIN_VERSION
        )
        self.assertIn(versioninfo, "\n".join(logs))

    def test_run_full_analysis_skips_write_when_analysis_fails(self):
        item = Item(path=b"ignored.flac")
        cmd = XtractorCommand(self.config[PLUGIN_NAME])

        with patch.object(cmd, "_get_input_path_for_item", return_value="/tmp/song.flac"):
            with patch.object(cmd, "_run_analysis", return_value=False) as run_analysis:
                with patch.object(cmd, "_run_write_to_item") as run_write:
                    cmd.run_full_analysis(item)

        run_analysis.assert_called_once_with(item, "/tmp/song.flac")
        run_write.assert_not_called()

    def test_run_full_analysis_skips_analysis_and_write_for_missing_file(self):
        item = Item(path=b"missing.flac")
        cmd = XtractorCommand(self.config[PLUGIN_NAME])

        with patch.object(cmd, "_get_input_path_for_item", side_effect=FileNotFoundError("missing")):
            with patch.object(cmd, "_run_analysis") as run_analysis:
                with patch.object(cmd, "_run_write_to_item") as run_write:
                    cmd.run_full_analysis(item)

        run_analysis.assert_not_called()
        run_write.assert_not_called()
