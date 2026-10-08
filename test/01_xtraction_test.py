#  Copyright: Copyright (c) 2020., Adam Jakab
#  Author: Adam Jakab <adam at jakab dot pro>
#  License: See LICENSE.txt

import json
import os
import sqlite3
import stat
import sys
import threading
from unittest.mock import patch

import yaml
from confuse import ConfigError
from beets import context, plugins
from beets.dbcore import types
from beets.library import Item
from beets.util import cached_classproperty

from beetsplug.xtractor.command import XtractorCommand

from test.helper import TestHelper, Assertions, PLUGIN_NAME

FIELD_PREFIX = "xtractor_"
BPM_BEHAVIORS = ["force", "if_empty", "if_similar", "never"]

DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "beetsplug", "xtractor", "config_default.yml")

# What the fake extractor reports for every file
EXTRACTOR_OUTPUT = {
    "rhythm": {"bpm": 127.6, "danceability": 1.25, "beats_count": 512},
    "lowlevel": {"average_loudness": 0.0},
    "highlevel": {
        "danceability": {"all": {"danceable": 0.9}},
        "gender": {"value": "male", "all": {"male": 0.8, "female": 0.2}},
        "genre_rosamerica": {"value": "roc"},
        "voice_instrumental": {"value": "voice", "all": {"voice": 0.7, "instrumental": 0.3}},
        "mood_acoustic": {"all": {"acoustic": 0.1}},
        "mood_aggressive": {"all": {"aggressive": 0.2}},
        "mood_electronic": {"all": {"electronic": 0.3}},
        "mood_happy": {"all": {"happy": 0.4}},
        "mood_sad": {"all": {"sad": 0.5}},
        "mood_party": {"all": {"party": 0.6}},
        "mood_relaxed": {"all": {"relaxed": 0.7}},
        "moods_mirex": {"value": "Cluster3", "all": {
            "Cluster1": 0.1, "Cluster2": 0.2, "Cluster3": 0.4, "Cluster4": 0.2, "Cluster5": 0.1}},
    },
}


def _load_default_config():
    with open(DEFAULT_CONFIG_PATH) as f:
        return yaml.safe_load(f)


class DefaultConfigTest(TestHelper, Assertions):
    """Test the default configuration and the field types derived from it.
    """

    def _targets(self):
        cfg = _load_default_config()
        return list(cfg["low_level_targets"]) + list(cfg["high_level_targets"])

    def test_fields_are_not_prefixed_by_default(self):
        cfg = _load_default_config()

        self.assertEqual("", cfg["field_prefix"])
        self.assertIn(cfg["prefix_bpm_behavior"], BPM_BEHAVIORS)
        self.assertIn("bpm", cfg["low_level_targets"])
        for fld in self._targets():
            self.assertFalse(fld.startswith(FIELD_PREFIX), msg="Hardcoded prefix: {}".format(fld))

    def test_item_types_are_built_from_the_configuration(self):
        plugin = plugins.find_plugins()[0]

        # `bpm` is a field of beets itself and must keep its own type
        self.assertEqual(set(self._targets()) - {"bpm"}, set(plugin.item_types))
        self.assertEqual(types.INTEGER, plugin.item_types["beats_count"])
        self.assertEqual(types.STRING, plugin.item_types["gender"])
        self.assertIsInstance(plugin.item_types["danceability"], types.Float)

    def test_item_types_are_prefixed(self):
        self.config[PLUGIN_NAME]["field_prefix"] = FIELD_PREFIX
        plugin = plugins.find_plugins()[0]

        item_types = plugin._build_item_types()

        self.assertEqual({FIELD_PREFIX + fld for fld in self._targets()}, set(item_types))
        self.assertEqual(types.INTEGER, item_types["xtractor_bpm"])
        for fld in item_types:
            self.assertNotIn(fld, Item._fields)

    def test_item_types_follow_user_defined_targets(self):
        self.config[PLUGIN_NAME]["low_level_targets"]["my_key_strength"] = {
            "path": "tonal.key_strength", "type": "float"}
        self.config[PLUGIN_NAME]["low_level_targets"]["my_untyped"] = {"path": "tonal.whatever"}
        plugin = plugins.find_plugins()[0]

        item_types = plugin._build_item_types()

        self.assertIsInstance(item_types["my_key_strength"], types.Float)
        self.assertNotIn("my_untyped", item_types)
        self.assertIn("danceability", item_types)

    def test_unknown_bpm_behavior_is_rejected(self):
        self.config[PLUGIN_NAME]["prefix_bpm_behavior"] = "sometimes"

        with self.assertRaises(ConfigError):
            XtractorCommand(self.config[PLUGIN_NAME])


class XtractionTest(TestHelper, Assertions):
    """Test the analysis with a fake extractor on a library stored on disk.
    """

    def setUp(self):
        super().setUp()
        workdir = self.mkdtemp()
        self.output_dir = os.path.join(workdir, "output")
        os.makedirs(self.output_dir)

        self.extractor_path = os.path.join(workdir, "fake_extractor")
        with open(self.extractor_path, "w") as f:
            f.write("#!{}\n".format(sys.executable))
            f.write("import sys\n")
            f.write("with open(sys.argv[2], 'w') as out:\n")
            f.write("    out.write({!r})\n".format(json.dumps(EXTRACTOR_OUTPUT)))
        os.chmod(self.extractor_path, os.stat(self.extractor_path).st_mode | stat.S_IXUSR)

        self.config[PLUGIN_NAME]["essentia_extractor"] = self.extractor_path
        self.config[PLUGIN_NAME]["output_path"] = self.output_dir
        self.config[PLUGIN_NAME]["write"] = False
        self.config[PLUGIN_NAME]["quiet"] = True

    def _add_items(self, count):
        for i in range(count):
            path = os.path.join(os.fsdecode(self.libdir), "album", "track{}.flac".format(i))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb"):
                pass
            self.lib.add(Item(path=path.encode(), title="track{}".format(i)))

    def _use_prefix(self, bpm_behavior=None):
        self.config[PLUGIN_NAME]["field_prefix"] = FIELD_PREFIX
        if bpm_behavior:
            self.config[PLUGIN_NAME]["prefix_bpm_behavior"] = bpm_behavior

        # beets reads the configuration before it loads the plugin, the tests set the prefix afterwards
        plugin = plugins.find_plugins()[0]
        plugin.item_types = plugin._build_item_types()
        cached_classproperty.cache.clear()
        self.addCleanup(cached_classproperty.cache.clear)

    def _create_command(self, threads=1):
        cmd = XtractorCommand(self.config[PLUGIN_NAME])
        cmd.lib = self.lib
        cmd.query = []
        cmd.cfg_threads = threads
        return cmd

    def _set_bpm(self, bpm):
        item = self.lib.items().get()
        item.bpm = bpm
        item.store()

    def _stored_paths(self):
        with sqlite3.connect(os.fsdecode(self.lib.path)) as conn:
            return sorted(os.fsdecode(row[0]) for row in conn.execute("select path from items"))

    def test_worker_threads_inherit_the_music_dir_context(self):
        self._add_items(4)
        cmd = self._create_command(threads=2)
        seen = []

        def record(item):
            seen.append((threading.current_thread() is threading.main_thread(),
                         context.get_music_dir(), os.fspath(item.filepath)))

        cmd._execute_on_each_items(self.lib.items(), record)

        self.assertEqual(4, len(seen))
        for is_main_thread, music_dir, filepath in seen:
            self.assertFalse(is_main_thread)
            self.assertEqual(self.lib.directory, music_dir)
            self.assertTrue(os.path.isabs(filepath), msg="Relative path in worker: {}".format(filepath))
            self.assertIsFile(filepath)

    def test_threaded_analysis_stores_fields(self):
        self._add_items(3)
        self.assertEqual(["album/track0.flac", "album/track1.flac", "album/track2.flac"], self._stored_paths())

        self._create_command(threads=3).xtract()

        items = list(self.lib.items())
        self.assertEqual(3, len(items))
        for item in items:
            self.assertEqual(128, item.get("bpm"))
            self.assertEqual(512, item.get("beats_count"))
            self.assertEqual(1.25, item.get("danceability"))
            self.assertEqual(0.9, item.get("danceable"))
            self.assertEqual("male", item.get("gender"))
            self.assertEqual("Cluster3", item.get("mood_mirex"))
            self.assertEqual(0.4, item.get("mood_mirex_cluster_3"))
            self.assertIsNone(item.get("xtractor_bpm"))

        # The paths must stay relative to the library directory
        self.assertEqual(["album/track0.flac", "album/track1.flac", "album/track2.flac"], self._stored_paths())

    def test_threaded_analysis_stores_prefixed_fields(self):
        self._use_prefix(bpm_behavior="never")
        self._add_items(3)

        self._create_command(threads=3).xtract()

        items = list(self.lib.items())
        self.assertEqual(3, len(items))
        for item in items:
            self.assertEqual(128, item.get("xtractor_bpm"))
            self.assertEqual(512, item.get("xtractor_beats_count"))
            self.assertEqual(1.25, item.get("xtractor_danceability"))
            self.assertEqual("male", item.get("xtractor_gender"))
            self.assertEqual(0.4, item.get("xtractor_mood_mirex_cluster_3"))
            # The fields owned by beets and other plugins are left alone
            self.assertEqual(0, item.get("bpm"))
            self.assertIsNone(item.get("danceability"))
            self.assertIsNone(item.get("gender"))

    def test_bpm_behavior_with_prefix(self):
        # The fake extractor reports 128: 126 is within the allowed difference of 2, 125 and 90 are not
        expectations = {
            "force": {0: 128, 126: 128, 125: 128, 90: 128},
            "if_empty": {0: 128, 126: 126, 125: 125, 90: 90},
            "if_similar": {0: 128, 126: 128, 125: 125, 90: 90},
            "never": {0: 0, 126: 126, 125: 125, 90: 90},
        }
        self.assertEqual(set(BPM_BEHAVIORS), set(expectations))
        self._add_items(1)

        for behavior, cases in expectations.items():
            for existing_bpm, expected_bpm in cases.items():
                with self.subTest(behavior=behavior, existing_bpm=existing_bpm):
                    self._use_prefix(bpm_behavior=behavior)
                    self._set_bpm(existing_bpm)
                    cmd = self._create_command()
                    cmd.cfg_force = True

                    cmd.xtract()

                    item = self.lib.items().get()
                    self.assertEqual(expected_bpm, item.get("bpm"))
                    self.assertEqual(128, item.get("xtractor_bpm"))

    def test_bpm_max_difference_is_configurable(self):
        self._use_prefix(bpm_behavior="if_similar")
        self.config[PLUGIN_NAME]["prefix_bpm_max_difference"] = 40
        self._add_items(1)
        self._set_bpm(90)

        self._create_command().xtract()

        self.assertEqual(128, self.lib.items().get().get("bpm"))

    def test_bpm_behavior_is_ignored_without_prefix(self):
        self._add_items(1)

        for behavior in BPM_BEHAVIORS:
            with self.subTest(behavior=behavior):
                self.config[PLUGIN_NAME]["prefix_bpm_behavior"] = behavior
                self._set_bpm(90)
                cmd = self._create_command()
                cmd.cfg_force = True

                cmd.xtract()

                self.assertEqual(128, self.lib.items().get().get("bpm"))

    def test_bpm_reaches_the_media_file_only_when_updated(self):
        self._add_items(1)
        self._set_bpm(90)
        written = []

        def try_write(item, path=None, **kwargs):
            written.append(item.bpm)
            return True

        for behavior, expected_bpm in [("never", 90), ("force", 128)]:
            self._use_prefix(bpm_behavior=behavior)
            cmd = self._create_command()
            cmd.cfg_force = True
            cmd.cfg_write = True
            with patch.object(Item, "try_write", try_write):
                cmd.xtract()

            self.assertEqual(expected_bpm, written[-1])

    def test_zero_values_are_stored(self):
        self._add_items(1)

        self._create_command().xtract()

        with sqlite3.connect(os.fsdecode(self.lib.path)) as conn:
            rows = conn.execute(
                "select value from item_attributes where key = 'average_loudness'").fetchall()
        self.assertEqual(1, len(rows))
        self.assertEqual(0.0, float(rows[0][0]))

    def test_analysed_items_are_not_selected_again(self):
        self._add_items(2)
        cmd = self._create_command(threads=2)

        cmd.find_items_to_analyse()
        self.assertEqual(2, len(cmd.items_to_analyse))

        cmd.xtract()

        cmd.find_items_to_analyse()
        self.assertEqual(0, len(cmd.items_to_analyse))

        cmd.cfg_force = True
        cmd.find_items_to_analyse()
        self.assertEqual(2, len(cmd.items_to_analyse))

    def test_prefixed_fields_decide_what_is_analysed(self):
        self._add_items(2)
        self._create_command().xtract()

        # Values stored without the prefix do not count for a prefixed setup
        self._use_prefix()
        cmd = self._create_command(threads=2)
        cmd.find_items_to_analyse()
        self.assertEqual(2, len(cmd.items_to_analyse))

        cmd.xtract()

        cmd.find_items_to_analyse()
        self.assertEqual(0, len(cmd.items_to_analyse))

    def test_threaded_write_gets_the_absolute_path(self):
        self._add_items(2)
        cmd = self._create_command(threads=2)
        cmd.cfg_write = True
        written = []

        def try_write(item, path=None, **kwargs):
            written.append((path, context.get_music_dir(), item.path))
            return True

        with patch.object(Item, "try_write", try_write):
            cmd.xtract()

        self.assertEqual(2, len(written))
        for path, music_dir, item_path in written:
            self.assertTrue(os.path.isabs(path))
            self.assertIsFile(path)
            self.assertEqual(self.lib.directory, music_dir)
            self.assertTrue(os.path.isabs(item_path))

    def test_dry_run_stores_nothing(self):
        self._add_items(1)
        cmd = self._create_command()
        cmd.cfg_dry_run = True

        cmd.xtract()

        item = self.lib.items().get()
        self.assertEqual(0, item.get("bpm"))
        self.assertIsNone(item.get("danceable"))

    def test_output_and_profile_are_removed_by_default(self):
        self._add_items(1)

        self._create_command().xtract()

        self.assertEqual([], os.listdir(self.output_dir))
