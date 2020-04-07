#  Copyright: Copyright (c) 2020., Adam Jakab
#  Author: Adam Jakab <adam at jakab dot pro>
#  License: See LICENSE.txt
import os
import pickle
from datetime import datetime
from optparse import OptionParser

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

    def __init__(self, config):
        self.config = config

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

        # push to ab

        # create high-level data if our push has been done more than 30
        # minutes ago

        # {'id': 1, 'mb_trackid': 'dc54022e-67f9-48e6-9855-c2785964ab1a',
        # 'ab_count': 0, 'ab_check': None, 'needs_processing': False},
        # self._say("REGISTRY: {}".format(self.registry))

        # Done
        self.store_registry()

    def update_from_ab_server(self):
        processable = [item for item in self.registry if
                       item["needs_processing"] and item["ab_count"] > 0]
        if len(processable) == 0:
            return

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
        offset = 0
        while offset is not None and offset < len(self.registry):
            data, offset = common.get_ab_check_data(self.registry, offset)
            if data:
                for mbid in data.keys():
                    regitem = self.get_registry_item('mb_trackid', mbid)
                    if regitem:
                        count = int(data[mbid]["count"])
                        regitem.update({
                            "ab_count": count,
                            "ab_check": int(datetime.now().timestamp())
                        })

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
            "needs_processing": False
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
