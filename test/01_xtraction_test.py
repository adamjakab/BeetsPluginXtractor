import json
import os
import sqlite3
import stat
import sys
import threading
import wave

import yaml
from beets import context, plugins
from beets.dbcore import types
from beets.library import Item
from beetsplug.xtractor.command import XtractorCommand
from mediafile import MediaFile

from test.helper import TestHelper, Assertions, PLUGIN_NAME

DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "beetsplug", "xtractor", "config_default.yml")

# What the fake extractor reports for every file
EXTRACTOR_OUTPUT = {
    "rhythm": {"bpm": 127.6, "danceability": 1.25, "beats_count": 512},
    "lowlevel": {"average_loudness": 0.8},
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


class ItemTypesTest(TestHelper, Assertions):
    """Test the field types derived from the configured targets.
    """

    def _default_targets(self):
        with open(DEFAULT_CONFIG_PATH) as f:
            cfg = yaml.safe_load(f)
        return {**cfg["low_level_targets"], **cfg["high_level_targets"]}

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

    def _create_command(self, threads=1):
        cmd = XtractorCommand(self.config[PLUGIN_NAME])
        cmd.lib = self.lib
        cmd.query = []
        cmd.cfg_threads = threads
        return cmd

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

        # The paths must stay relative to the library directory
        self.assertEqual(["album/track0.flac", "album/track1.flac", "album/track2.flac"], self._stored_paths())
