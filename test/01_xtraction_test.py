import json
import os
import sqlite3
import stat
import sys
import threading
from unittest.mock import patch

from beets import context
from beets.library import Item
from beetsplug.xtractor.command import XtractorCommand

from test.helper import TestHelper, Assertions, PLUGIN_NAME

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


class XtractionTest(TestHelper, Assertions):
    """Test the analysis with a fake extractor on a library stored on disk.
    """

    def setUp(self):
        super().setUp()
        workdir = self.mkdtemp()
        self.output_dir = os.path.join(workdir, "output")
        os.makedirs(self.output_dir)

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
