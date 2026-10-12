#  Copyright: Copyright (c) 2020., Adam Jakab
#
#  Author: Adam Jakab <adam at jakab dot pro>
#  Created: 3/12/20, 11:42 PM
#  License: See LICENSE.txt

import os
import sqlite3
from unittest.mock import patch

from beets.library import Library, Item
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

    def test_get_input_path_for_item_with_absolute_path(self):
        path = self.lib_path(b"absolute.flac")
        with open(path, "wb"):
            pass

        item = Item(path=path)
        cmd = XtractorCommand(self.config[PLUGIN_NAME])
        cmd.lib = self.lib

        self.assertEqual(os.path.normpath(path.decode()), os.path.normpath(cmd._get_input_path_for_item(item)))

    def test_get_input_path_for_item_uses_library_backed_filepath(self):
        tempdir = self.mkdtemp()
        library_dir = os.path.join(tempdir, "music")
        db_path = os.path.join(tempdir, "library.db")
        relative_path = os.path.join("nested", "library.flac")
        absolute_path = os.path.join(library_dir, relative_path)

        os.makedirs(os.path.dirname(absolute_path), exist_ok=True)
        with open(absolute_path, "wb"):
            pass

        lib = Library(db_path, library_dir)
        item = Item(path=absolute_path.encode())
        lib.add(item)
        stored_item = list(lib.items())[0]
        with sqlite3.connect(db_path) as conn:
            stored_path = conn.execute("select path from items").fetchone()[0]

        cmd = XtractorCommand(self.config[PLUGIN_NAME])
        cmd.lib = lib

        self.assertEqual(relative_path, os.fsdecode(stored_path))
        self.assertEqual(
            os.path.normpath(absolute_path),
            os.path.normpath(cmd._get_input_path_for_item(stored_item)),
        )

    def test_get_input_path_for_item_resolves_relative_public_filepath_against_library_dir(self):
        relative_path = os.path.join("nested", "relative.flac")
        absolute_path = os.path.join(os.fsdecode(self.lib.directory), relative_path)
        os.makedirs(os.path.dirname(absolute_path), exist_ok=True)
        with open(absolute_path, "wb"):
            pass

        item = Item(path=relative_path.encode())
        cmd = XtractorCommand(self.config[PLUGIN_NAME])
        cmd.lib = self.lib

        self.assertEqual(
            os.path.normpath(absolute_path),
            os.path.normpath(cmd._get_input_path_for_item(item)),
        )

    def test_run_full_analysis_resolves_input_path_once(self):
        item = Item(path=b"ignored.flac")
        cmd = XtractorCommand(self.config[PLUGIN_NAME])
        cmd.cfg_write = True
        cmd.config["keep_output"] = False

        with patch.object(cmd, "_get_input_path_for_item", return_value="/tmp/song.flac") as get_input_path:
            with patch.object(cmd, "_run_analysis", return_value=True) as run_analysis:
                with patch.object(cmd, "_run_write_to_item") as run_write:
                    with patch.object(cmd, "_get_output_path_for_item", return_value="/tmp/output.json") as get_output:
                        with patch("os.path.isfile", return_value=False):
                            cmd.run_full_analysis(item)

        get_input_path.assert_called_once_with(item)
        run_analysis.assert_called_once_with(item, "/tmp/song.flac")
        run_write.assert_called_once_with(item, "/tmp/song.flac")
        get_output.assert_called_once_with(item, "/tmp/song.flac")

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
