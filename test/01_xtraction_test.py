import json
import os
import sqlite3
import stat
import sys
import threading
import wave
from unittest.mock import patch

import yaml
from confuse import ConfigError
from beets import context, plugins
from beets.dbcore import types
from beets.library import Item
from beets.util import cached_classproperty
from beetsplug.xtractor.command import XtractorCommand
from mediafile import MediaFile

from test.helper import TestHelper, Assertions, PLUGIN_NAME

FIELD_PREFIX = "xtractor_"
BPM_BEHAVIORS = ["force", "if_empty", "if_similar", "never"]

DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "beetsplug", "xtractor", "config_default.yml")

# What the fake extractor reports for every file (it has no model for `genre_electronic`)
EXTRACTOR_OUTPUT = {
    "rhythm": {"bpm": 127.6, "danceability": 1.25, "beats_count": 512},
    "lowlevel": {"average_loudness": 0.8},
    "tonal": {"key_edma": {"key": "C#", "scale": "minor", "strength": 0.7}},
    "highlevel": {
        "danceability": {"all": {"danceable": 0.9}},
        "gender": {"value": "male", "all": {"male": 0.8, "female": 0.2}},
        "genre_rosamerica": {"value": "roc", "probability": 0.6},
        "tonal_atonal": {"value": "tonal"},
        "timbre": {"value": "dark"},
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


class ItemTypesTest(TestHelper, Assertions):
    """Test the field types derived from the configured targets.
    """

    def _default_config(self):
        with open(DEFAULT_CONFIG_PATH) as f:
            return yaml.safe_load(f)

    def _default_targets(self):
        cfg = self._default_config()
        return {**cfg["low_level_targets"], **cfg["high_level_targets"]}

    def test_fields_are_not_prefixed_by_default(self):
        self.assertEqual("", self._default_config()["field_prefix"])
        self.assertEqual("", self.config[PLUGIN_NAME]["field_prefix"].get())
        self.assertIn("bpm", self._default_targets())
        for fld in self._default_targets():
            self.assertFalse(fld.startswith(FIELD_PREFIX), msg="Hardcoded prefix: {}".format(fld))

    def test_item_types_are_prefixed(self):
        self.config[PLUGIN_NAME]["field_prefix"] = FIELD_PREFIX
        plugin = plugins.find_plugins()[0]

        item_types = plugin._build_item_types()

        self.assertEqual({FIELD_PREFIX + fld for fld in self._default_targets()}, set(item_types))
        self.assertEqual(types.INTEGER, item_types["xtractor_bpm"])
        self.assertEqual(types.STRING, item_types["xtractor_gender"])
        self.assertIsInstance(item_types["xtractor_danceability"], types.Float)
        for fld in item_types:
            self.assertNotIn(fld, Item._fields)

    def test_additional_fields_are_optional(self):
        cfg = self._default_config()
        additional = {
            "low_level_targets": ["key_edma", "key_edma_scale"],
            "high_level_targets": ["tonal_atonal", "timbre", "genre_rosamerica_probability",
                                   "genre_electronic", "genre_electronic_probability"],
        }

        for map_key, fields in additional.items():
            for fld in fields:
                self.assertIn(fld, cfg[map_key])
                self.assertFalse(cfg[map_key][fld].get("required", False), msg=fld)

    def test_empty_prefix_in_user_configuration(self):
        self.config[PLUGIN_NAME]["field_prefix"] = None
        plugin = plugins.find_plugins()[0]

        self.assertEqual(set(self._default_targets()), set(plugin._build_item_types()))
        self.assertEqual("", XtractorCommand(self.config[PLUGIN_NAME]).cfg_field_prefix)

    def test_bpm_is_forced_by_default(self):
        self.assertEqual("force", self._default_config()["prefix_bpm_behavior"])
        self.assertEqual(2, self._default_config()["prefix_bpm_max_difference"])

    def test_unknown_bpm_behavior_is_rejected(self):
        self.config[PLUGIN_NAME]["prefix_bpm_behavior"] = "sometimes"

        with self.assertRaises(ConfigError):
            XtractorCommand(self.config[PLUGIN_NAME])

    def test_item_types_are_built_from_the_default_configuration(self):
        plugin = plugins.find_plugins()[0]
        type_names = {types.INTEGER: "integer", types.STRING: "string"}

        self.assertEqual(set(self._default_targets()), set(plugin.item_types))
        for fld, target in self._default_targets().items():
            item_type = plugin.item_types[fld]
            if target["type"] == "float":
                self.assertIsInstance(item_type, types.Float, msg=fld)
            else:
                self.assertEqual(target["type"], type_names.get(item_type), msg=fld)

    def test_item_types_follow_user_defined_targets(self):
        self.config[PLUGIN_NAME]["low_level_targets"]["my_key"] = {"path": "tonal.key_key", "type": "string"}
        self.config[PLUGIN_NAME]["high_level_targets"]["my_count"] = {"path": "rhythm.count", "type": "integer"}
        plugin = plugins.find_plugins()[0]

        item_types = plugin._build_item_types()

        self.assertEqual(types.STRING, item_types["my_key"])
        self.assertEqual(types.INTEGER, item_types["my_count"])
        self.assertEqual(set(self._default_targets()) | {"my_key", "my_count"}, set(item_types))

    def test_item_types_default_to_float(self):
        self.config[PLUGIN_NAME]["low_level_targets"]["my_untyped"] = {"path": "tonal.whatever"}
        self.config[PLUGIN_NAME]["low_level_targets"]["my_unknown"] = {"path": "tonal.whatever", "type": "tuple"}
        plugin = plugins.find_plugins()[0]

        item_types = plugin._build_item_types()

        self.assertIsInstance(item_types["my_untyped"], types.Float)
        self.assertIsInstance(item_types["my_unknown"], types.Float)

    def test_item_types_are_known_to_beets(self):
        self.assertEqual(types.INTEGER, Item._types["beats_count"])
        self.assertEqual(types.STRING, Item._types["mood_mirex"])
        self.assertIsInstance(Item._types["danceable"], types.Float)


class XtractionTest(TestHelper, Assertions):
    """Test the analysis with a fake extractor on a library stored on disk.
    """

    def setUp(self):
        super().setUp()
        workdir = self.mkdtemp()
        self.output_dir = os.path.join(workdir, "output")
        os.makedirs(self.output_dir)
        self.extractor_input_log = os.path.join(workdir, "extractor_inputs")

        self.extractor_path = os.path.join(workdir, "fake_extractor")
        self._write_extractor(EXTRACTOR_OUTPUT)

        self.config[PLUGIN_NAME]["essentia_extractor"] = self.extractor_path
        self.config[PLUGIN_NAME]["output_path"] = self.output_dir
        self.config[PLUGIN_NAME]["write"] = False
        self.config[PLUGIN_NAME]["quiet"] = True

    def _write_extractor(self, output):
        with open(self.extractor_path, "w") as f:
            f.write("#!{}\n".format(sys.executable))
            f.write("import sys\n")
            f.write("with open({!r}, 'a') as path_file:\n".format(self.extractor_input_log))
            f.write("    path_file.write(sys.argv[1])\n")
            f.write("    path_file.write('\\n')\n")
            f.write("with open(sys.argv[2], 'w') as out:\n")
            f.write("    out.write({!r})\n".format(json.dumps(output)))
        os.chmod(self.extractor_path, os.stat(self.extractor_path).st_mode | stat.S_IXUSR)

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

    def test_threaded_extraction_writes_tags_and_preserves_relative_paths(self):
        paths = [
            os.path.join(os.fsdecode(self.libdir), "album", "track{}.wav".format(i))
            for i in range(2)
        ]
        for path in paths:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with wave.open(path, "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(8000)
                audio.writeframes(b"\x00\x00" * 8000)
            self.lib.add(Item(path=os.fsencode(path), title="track"))

        relative_paths = ["album/track0.wav", "album/track1.wav"]
        self.assertEqual(relative_paths, self._stored_paths())
        cmd = self._create_command(threads=2)
        cmd.cfg_write = True

        cmd.xtract()

        with open(self.extractor_input_log) as path_file:
            extracted_paths = set(path_file.read().splitlines())
        self.assertEqual(set(paths), extracted_paths)
        for path in paths:
            self.assertEqual(128, MediaFile(path).bpm)
        self.assertEqual(relative_paths, self._stored_paths())

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

    def test_zero_values_are_stored(self):
        self._write_extractor({**EXTRACTOR_OUTPUT, "lowlevel": {"average_loudness": 0.0}})
        self._add_items(1)
        cmd = self._create_command()

        cmd.xtract()

        with sqlite3.connect(os.fsdecode(self.lib.path)) as conn:
            rows = conn.execute(
                "select value from item_attributes where key = 'average_loudness'").fetchall()
        self.assertEqual(1, len(rows))
        self.assertEqual(0.0, float(rows[0][0]))

        # A required field with a falsy value does not make the item unprocessed
        cmd.find_items_to_analyse()
        self.assertEqual(0, len(cmd.items_to_analyse))

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
            self.assertEqual("C#", item.get("key_edma"))
            self.assertEqual("minor", item.get("key_edma_scale"))
            self.assertEqual("tonal", item.get("tonal_atonal"))
            self.assertEqual("dark", item.get("timbre"))
            self.assertEqual("roc", item.get("genre_rosamerica"))
            self.assertEqual(0.6, item.get("genre_rosamerica_probability"))
            # Values missing in the output of the extractor are skipped
            self.assertIsNone(item.get("genre_electronic"))
            self.assertIsNone(item.get("genre_electronic_probability"))

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
