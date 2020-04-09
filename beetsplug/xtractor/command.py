#  Copyright: Copyright (c) 2020., Adam Jakab
#  Author: Adam Jakab <adam at jakab dot pro>
#  License: See LICENSE.txt
import hashlib
import json
import os
import pickle
import tempfile
from datetime import datetime
from optparse import OptionParser
from subprocess import Popen, PIPE

import yaml
from beets import dbcore
from beets.library import Library, Item
from beets.ui import Subcommand, decargs
from beets.util.confit import Subview, LazyConfig
from beetsplug.xtractor import common


class XtractorCommand(Subcommand):
    config: Subview = None

    lib = None
    query = None
    parser = None

    registry = []
    max_pickle_life_hrs = 1

    cfg_auto = False
    cfg_dry_run = False
    cfg_write = True
    cfg_threads = 1
    cfg_force = False
    cfg_quiet = False
    cfg_items_per_run = 0

    extractor_sha = None

    def __init__(self, config):
        self.config = config

        self._calculate_extractor_sha("low")

        cfg = self.config.flatten()
        self.cfg_auto = cfg.get("auto")
        self.cfg_dry_run = cfg.get("dry-run")
        self.cfg_write = cfg.get("write")
        self.cfg_threads = cfg.get("threads")
        self.cfg_force = cfg.get("force")
        self.cfg_version = False
        self.cfg_count_only = False
        self.cfg_quiet = cfg.get("quiet")
        self.cfg_items_per_run = cfg.get("items_per_run")

        self.parser = OptionParser(
            usage='beet {plg} [options] [QUERY...]'.format(
                plg=common.plg_ns['__PLUGIN_NAME__']
            ))

        self.parser.add_option(
            '-d', '--dry-run',
            action='store_true', dest='dryrun', default=self.cfg_dry_run,
            help=u'[default: {}] only show what would be done'
                 u'library items'.format(
                self.cfg_dry_run)
        )

        self.parser.add_option(
            '-w', '--write',
            action='store_true', dest='write', default=self.cfg_write,
            help=u'[default: {}] write the extracted values (bpm) to the media '
                 u'files'.format(
                self.cfg_write)
        )

        self.parser.add_option(
            '-t', '--threads',
            action='store', dest='threads', type='int',
            default=self.cfg_threads,
            help=u'[default: {}] the number of threads to run in '
                 u'parallel'.format(
                self.cfg_threads)
        )

        self.parser.add_option(
            '-f', '--force',
            action='store_true', dest='force', default=self.cfg_force,
            help=u'[default: {}] force analysis of items with non-zero bpm '
                 u'values'.format(
                self.cfg_force)
        )

        self.parser.add_option(
            '-c', '--count-only',
            action='store_true', dest='count_only', default=self.cfg_count_only,
            help=u'[default: {}] Show the number of items to be '
                 u'processed'.format(
                self.cfg_count_only)
        )

        self.parser.add_option(
            '-q', '--quiet',
            action='store_true', dest='quiet', default=self.cfg_quiet,
            help=u'[default: {}] mute all output'.format(self.cfg_quiet)
        )

        self.parser.add_option(
            '-v', '--version',
            action='store_true', dest='version', default=self.cfg_version,
            help=u'show plugin version'
        )

        # Keep this at the end
        super(XtractorCommand, self).__init__(
            parser=self.parser,
            name=common.plg_ns['__PLUGIN_NAME__'],
            aliases=[common.plg_ns['__PLUGIN_ALIAS__']] if
            common.plg_ns['__PLUGIN_ALIAS__'] else [],
            help=common.plg_ns['__PLUGIN_SHORT_DESCRIPTION__']
        )

    def func(self, lib: Library, options, arguments):
        self.cfg_dry_run = options.dryrun
        self.cfg_write = options.write
        self.cfg_threads = options.threads
        self.cfg_force = options.force
        self.cfg_version = options.version
        self.cfg_count_only = options.count_only
        self.cfg_quiet = options.quiet

        self.lib = lib
        self.query = decargs(arguments)

        if options.version:
            self.show_version_information()
            return

        self.xtract()

    def xtract(self):
        self.setup_registry()

        if len(self.registry) == 0:
            self._say("No items in registry")
            return

        self._say("Number of items in registry: {}".
                  format(len(self.registry)), log_only=False)

        # # Count only and exit
        if self.cfg_count_only:
            return

        self.update_registry_ab_counts()
        self.update_registry_item_status()

        # update from ab - remove low and high level json files for processed
        self.update_from_ab_server()

        # extract low level data
        self.update_low_from_extractor()

        # push to ab
        self.submit_low_to_ab()

        # create high-level data if our push has been done more than 30
        # minutes ago

        # {'id': 1, 'mb_trackid': 'dc54022e-67f9-48e6-9855-c2785964ab1a',
        # 'ab_count': 0, 'ab_check': None, 'needs_processing': False,
        # 'has_low_level_json': False},
        self._say("REGISTRY: {}".format(self.registry))

        # Done
        self.store_registry()

    def submit_low_to_ab(self):
        processables = [item for item in self.registry if
                        item["mb_trackid"] and
                        item["needs_processing"] and
                        item["has_low_level_json"]]
        if len(processables) == 0:
            return

        self._say("Pushing to AB: {}".format(len(processables)))

        for regitem in processables:
            item = self.get_item_by_itemid(regitem["id"])
            json_path = self._get_output_path_for_item(item, suffix="low")
            res = common.submit_low_level_data_to_ab(regitem, json_path,
                                                     self.extractor_sha)
            if res:
                self._say("Submission success!")
                ts = int(datetime.now().timestamp())
                regitem["ab_submitted"] = ts

    def update_low_from_extractor(self):
        processables = [item for item in self.registry if
                        item["needs_processing"] and
                        not item["has_low_level_json"]
                        ]
        if len(processables) == 0:
            return

        self._say("Low level extraction needed: {}".format(len(processables)))

        for regitem in processables:
            item = self.get_item_by_itemid(regitem["id"])
            res = self._run_analysis_low_level(item)
            if res:
                regitem["has_low_level_json"] = True

    def _run_analysis_low_level(self, item):
        try:
            extractor_path = self._get_extractor_path(level="low")
            input_path = self._get_input_path_for_item(item)
            output_path = self._get_output_path_for_item(item, suffix="low")
            profile_path = self._get_extractor_profile_path(level="low")
        except ValueError as e:
            self._say("Value error: {0}".format(e))
            return False
        except KeyError as e:
            self._say("Configuration error: {0}".format(e))
            return False
        except FileNotFoundError as e:
            self._say("File not found error: {0}".format(e))
            return False

        self._say("Running low-level analysis: {0}".format(input_path))
        self._run_essentia_extractor(extractor_path, input_path, output_path,
                                     profile_path)

        try:
            target_map = self.config["low_level_targets"]
            audiodata = common.extract_from_json_file(output_path, target_map)
            self._say("Audiodata(Low): {}".format(audiodata))
        except FileNotFoundError as e:
            self._say("File not found: {0}".format(e))
            return False

        if not self.cfg_dry_run:
            for attr in audiodata.keys():
                if audiodata.get(attr):
                    setattr(item, attr, audiodata.get(attr))
            item.store()

        return True

    def update_from_ab_server(self):
        processables = [item for item in self.registry if
                        item["needs_processing"] and
                        item["ab_count"] > 0]
        if len(processables) == 0:
            return

        offset = 0
        max_items = 25
        while offset < len(processables):
            subset = processables[offset:offset + max_items]
            low_level_data = common.get_ab_low_high_level_data(subset,
                                                               "low-level")
            high_level_data = common.get_ab_low_high_level_data(subset,
                                                                "high-level")
            offset += max_items
            if low_level_data and high_level_data:
                for regitem in subset:
                    mbid = regitem['mb_trackid']
                    ab_data_low = low_level_data[mbid]["0"]
                    ab_data_high = high_level_data[mbid]["0"]
                    audiodata = {}
                    audiodata.update(
                        common.extract_from_output(
                            ab_data_low, self.config["low_level_targets"])
                    )
                    audiodata.update(
                        common.extract_from_output(
                            ab_data_high, self.config["high_level_targets"])
                    )
                    self._say("Audiodata(Low+High): {}".format(audiodata))

                    if audiodata and not self.cfg_dry_run:
                        item = self.get_item_by_itemid(regitem["id"])
                        for attr in audiodata.keys():
                            if audiodata.get(attr):
                                setattr(item, attr, audiodata.get(attr))
                        item.store()
                        regitem["needs_processing"] = False
                        self.delete_output_files_for_item(item)

    def delete_output_files_for_item(self, item: Item):
        # Delete output files (if config wants)
        if self.config["keep_output"].exists() and not \
                self.config["keep_output"].get(bool):

            output_path = self._get_output_path_for_item(item, suffix="low")
            if os.path.isfile(output_path):
                self._say("Deleting: {}".format(output_path))
                os.unlink(output_path)
            else:
                self._say("Nothing to delete: {}".format(output_path))

            output_path = self._get_output_path_for_item(item, suffix="high")
            if os.path.isfile(output_path):
                self._say("Deleting: {}".format(output_path))
                os.unlink(output_path)
            else:
                self._say("Nothing to delete: {}".format(output_path))

    def update_registry_item_status(self):
        for regitem in self.registry:
            library_item: Item = self.get_item_by_itemid(regitem["id"])
            if library_item:
                regitem["needs_processing"] = \
                    self.item_needs_processing(library_item)

    def item_needs_processing(self, item: Item):
        answer = False

        target_maps = ["low_level_targets", "high_level_targets"]

        for map_key in target_maps:
            if answer:
                break
            target_map = self.config[map_key]
            for fld in target_map:
                if target_map[fld]["required"].exists() \
                        and target_map[fld]["required"].get(bool):
                    if not item.get(fld):
                        answer = True
                        break

        return answer

    def update_registry_ab_counts(self):
        max_hours = 24
        ts = int(datetime.now().timestamp())
        max_ts_diff = max_hours * 60 * 60

        processables = []
        for regitem in self.registry:
            if regitem["mb_trackid"]:
                if not regitem["ab_check"] \
                        or ts - regitem["ab_check"] > max_ts_diff:
                    processables.append(regitem)

        if len(processables) == 0:
            return

        offset = 0
        max_items = 25
        while offset < len(processables):
            subset = processables[offset:offset + max_items]
            data = common.get_ab_check_count_data(subset)
            offset += max_items

            for regitem in subset:
                fresh_data = {"ab_check": ts}
                if data:
                    mbid = regitem['mb_trackid']
                    if mbid in data:
                        count = int(data[mbid]["count"])
                        fresh_data.update({
                            "ab_count": count,
                        })

                regitem.update(fresh_data)

    def setup_registry(self):
        self.restore_registry()
        if self.registry:
            self._say("Registry was restored from pickle jar.")
            return

        # Select all in 'albumartist' order
        query = dbcore.query.TrueQuery()
        sort = dbcore.query.FixedFieldSort("albumartist", ascending=True)
        items = self.lib.items(query, sort)

        for item in items:
            record = self.get_default_record()
            record.update({
                "id": item.get("id"),
                "mb_trackid": item.get("mb_trackid"),
            })
            self.registry.append(record)

    @staticmethod
    def get_default_record():
        return {
            "id": None,
            "mb_trackid": None,
            "ab_count": 0,
            "ab_check": None,
            "needs_processing": False,
            "has_low_level_json": False,
            "ab_submitted": None
        }

    def get_registry_item(self, fld, val):
        answer = None

        for regitem in self.registry:
            if fld in regitem:
                if regitem[fld] == val:
                    answer = regitem
                    break

        return answer

    def get_item_by_itemid(self, itemid):
        answer = None

        query = dbcore.query.NumericQuery('id', str(itemid))
        items = self.lib.items(query)
        if len(items) == 1:
            answer = items.get()

        return answer

    def _run_essentia_extractor(self, extractor_path, input_path, output_path,
                                profile_path):
        if os.path.isfile(output_path):
            self._say("Output exists: {0}".format(output_path))
            return

        self._say("Extractor: {0}".format(extractor_path))
        self._say("Input: {0}".format(input_path))
        self._say("Output: {0}".format(output_path))
        self._say("Profile: {0}".format(profile_path))

        proc = Popen([extractor_path, input_path, output_path, profile_path],
                     stdout=PIPE, stderr=PIPE)
        stdout, stderr = proc.communicate()

        self._say("The process exited with code: {0}".format(proc.returncode))
        self._say("Process stdout: {0}".format(stdout.decode()))
        self._say("Process stderr: {0}".format(stderr.decode()))

        # Make sure file is encoded correctly (sometimes media files have
        # funky tags)
        common.asciify_file_content(output_path)

    def _get_output_path_for_item(self, item: Item, suffix=""):
        identifier = item.get("mb_trackid")
        if not identifier:
            input_path = self._get_input_path_for_item(item)
            identifier = hashlib.md5(input_path.encode('utf-8')).hexdigest()

        output_file = "{id}{sfx}{ext}".format(
            id=identifier,
            sfx=".{}".format(suffix) if suffix else "",
            ext=".json"
        )

        return os.path.join(self._get_extraction_output_path(), output_file)

    def _get_input_path_for_item(self, item: Item):
        input_path = item.get("path").decode("utf-8")

        if not os.path.isfile(input_path):
            raise FileNotFoundError(
                "Input file({}) not found!".format(input_path))

        return input_path

    def _get_extraction_output_path(self):
        if self.config["output_path"].exists():
            if not os.path.isdir(self.config["output_path"].as_filename()):
                raise FileNotFoundError(
                    "Output path({}) does not exist!".format(
                        self.config["output_path"].as_filename()))

            output_path = self.config["output_path"].as_filename()
        else:
            output_path = os.path.join(tempfile.gettempdir(),
                                       common.plg_ns['__PLUGIN_NAME__'])
            if not os.path.isdir(output_path):
                os.makedirs(output_path)

        return output_path

    def _get_extractor_profile_path(self, level):
        if level not in ("low", "high"):
            raise ValueError(
                "Profile level must be either 'low' or 'high'. Given: {}".
                    format(level))

        profile_key = "{}_level_profile".format(level)
        profile_filename = "{}.yml".format(profile_key)
        profile_path = os.path.join(self._get_extraction_output_path(),
                                    profile_filename)

        if not os.path.isfile(profile_path):
            # Generate profile file
            if not self.config[profile_key].exists():
                raise KeyError("Key '{}' is not defined".format(profile_key))

            profile_content = self.config[profile_key].flatten()
            profile_content = json.loads(json.dumps(profile_content))
            # Override outputFormat (we only hande json for now)
            profile_content["outputFormat"] = "json"

            f = open(profile_path, 'w+')
            yaml.dump(profile_content, f, allow_unicode=True)

            if not os.path.isfile(profile_path):
                raise FileNotFoundError(
                    "Extractor profile({}) not created!".format(profile_path))

        return profile_path

    def _get_extractor_path(self, level):
        if level not in ("low", "high"):
            raise ValueError(
                "Extractor level must be either 'low' or 'high'. Given: {}".
                    format(level))

        extractor_key = "{}_level_extractor".format(level)
        if not self.config[extractor_key].exists():
            raise KeyError("Key '{}' is not defined".format(extractor_key))

        extractor_path = self.config[extractor_key].as_filename()

        if not os.path.isfile(extractor_path):
            raise FileNotFoundError("Extractor({}) is not found!".format(
                extractor_path))

        return extractor_path

    def _calculate_extractor_sha(self, level):
        if level not in ("low", "high"):
            raise ValueError(
                "Extractor level must be either 'low' or 'high'. Given: {}".
                    format(level))

        # Calculate extractor hash.
        xpath = self._get_extractor_path(level)
        self.extractor_sha = hashlib.sha1()
        with open(xpath, 'rb') as extractor:
            self.extractor_sha.update(extractor.read())
        self.extractor_sha = self.extractor_sha.hexdigest()

    def restore_registry(self):
        self.registry = []
        registry_storage_file = self.get_store_registry_file_path()
        if not os.path.isfile(registry_storage_file):
            self._say("No pickle jar was found.")
            return

        with open(registry_storage_file, 'rb') as fh:
            jar = pickle.load(fh)

        ts = int(datetime.now().timestamp())
        max_ts_diff = self.max_pickle_life_hrs * 60 * 60
        if "timestamp" in jar and ts - jar["timestamp"] <= max_ts_diff:
            self.registry = jar["pickles"]

    def store_registry(self):
        registry_storage_file = self.get_store_registry_file_path()

        jar = {
            "timestamp": int(datetime.now().timestamp()),
            "pickles": self.registry
        }

        with open(registry_storage_file, 'wb') as fh:
            pickle.dump(jar, fh)

    @staticmethod
    def get_store_registry_file_path():
        config_dir = LazyConfig(u'beets').config_dir()
        pickle_file = "{}-registry.pickle". \
            format(common.plg_ns['__PLUGIN_NAME__'])
        return os.path.join(config_dir, pickle_file)

    def show_version_information(self):
        self._say("{pt}({pn}) plugin for Beets: v{ver}".format(
            pt=common.plg_ns['__PACKAGE_TITLE__'],
            pn=common.plg_ns['__PACKAGE_NAME__'],
            ver=common.plg_ns['__version__']
        ), log_only=False)

    @staticmethod
    def _say(msg, log_only=True, is_error=False):
        common.say(msg, log_only, is_error)
