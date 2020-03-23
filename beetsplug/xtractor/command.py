#  Copyright: Copyright (c) 2020., Adam Jakab
#
#  Author: Adam Jakab <adam at jakab dot pro>
#  Created: 3/13/20, 12:17 AM
#  License: See LICENSE.txt
import hashlib
import json
import logging
import os
import tempfile
from concurrent import futures
from optparse import OptionParser
from subprocess import Popen, PIPE

import yaml
from beets import dbcore
from beets.library import Library, Item, parse_query_string
from beets.ui import Subcommand, decargs
from confuse import Subview

from beetsplug.xtractor import helper as bpmHelper

# Module methods
log = logging.getLogger('beets.xtractor')

# The plugin
__PLUGIN_NAME__ = u'xtractor'
__PLUGIN_SHORT_NAME__ = u'xt'
__PLUGIN_SHORT_DESCRIPTION__ = u'get more out of your music...'


class XtractorCommand(Subcommand):
    config: Subview = None

    lib = None
    query = None
    parser = None

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

        self.parser = OptionParser(usage='%prog [options] [QUERY...]')

        self.parser.add_option(
            '-d', '--dry-run',
            action='store_true', dest='dryrun', default=self.cfg_dry_run,
            help=u'[default: {}] display the bpm values but do not update the library items'.format(
                self.cfg_dry_run)
        )

        self.parser.add_option(
            '-w', '--write',
            action='store_true', dest='write', default=self.cfg_write,
            help=u'[default: {}] write the bpm values to the media files'.format(
                self.cfg_write)
        )

        self.parser.add_option(
            '-t', '--threads',
            action='store', dest='threads', type='int',
            default=self.cfg_threads,
            help=u'[default: {}] the number of threads to run in parallel'.format(
                self.cfg_threads)
        )

        self.parser.add_option(
            '-f', '--force',
            action='store_true', dest='force', default=self.cfg_force,
            help=u'[default: {}] force analysis of items with non-zero bpm values'.format(self.cfg_force)
        )

        self.parser.add_option(
            '-c', '--count-only',
            action='store_true', dest='count_only', default=self.cfg_count_only,
            help=u'[default: {}] Show the number of items to be processed'.format(self.cfg_count_only)
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
            name=__PLUGIN_NAME__,
            help=__PLUGIN_SHORT_DESCRIPTION__,
            aliases=[__PLUGIN_SHORT_NAME__]
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
        # Parse the incoming query
        parsed_query, parsed_sort = parse_query_string(" ".join(self.query), Item)
        combined_query = parsed_query

        # Add unprocessed items query = "bpm:0 , gender::^$"
        if not self.cfg_force:
            # Set up the query for unprocessed items
            unprocessed_items_query = dbcore.query.OrQuery(
                [
                    # LOW
                    # dbcore.query.NoneQuery(u'average_loudness', fast=False),
                    dbcore.query.MatchQuery(u'average_loudness', None, fast=False),
                    dbcore.query.NumericQuery(u'bpm', u'0'),
                    dbcore.query.MatchQuery(u'danceability', None, fast=False),
                    dbcore.query.MatchQuery(u'beats_count', None, fast=False),

                    # HIGH
                    dbcore.query.MatchQuery(u'danceable', None, fast=False),
                    dbcore.query.MatchQuery(u'gender', None, fast=False),
                    dbcore.query.MatchQuery(u'genre_rosamerica', None, fast=False),
                    dbcore.query.MatchQuery(u'voice_instrumental', None, fast=False),

                    dbcore.query.MatchQuery(u'mood_acoustic', None, fast=False),
                    dbcore.query.MatchQuery(u'mood_aggressive', None, fast=False),
                    dbcore.query.MatchQuery(u'mood_electronic', None, fast=False),
                    dbcore.query.MatchQuery(u'mood_happy', None, fast=False),
                    dbcore.query.MatchQuery(u'mood_party', None, fast=False),
                    dbcore.query.MatchQuery(u'mood_relaxed', None, fast=False),
                    dbcore.query.MatchQuery(u'mood_sad', None, fast=False),
                ]
            )
            combined_query = dbcore.query.AndQuery([parsed_query, unprocessed_items_query])

        log.debug("Combined query: {}".format(combined_query))

        # Get the library items
        library_items = self.lib.items(combined_query, parsed_sort)
        if len(library_items) == 0:
            self._say("No items to process")
            return

        # Count only and exit
        if self.cfg_count_only:
            self._say("Number of items to be processed: {}".format(len(library_items)))
            return

        # Limit the number of items per run (0 means no limit)
        items = []
        for item in library_items:
            items.append(item)
            if self.cfg_items_per_run != 0 and len(items) >= self.cfg_items_per_run:
                break

        self._say("Number of items selected: {}".format(len(items)))
        self._execute_on_each_items(items, self._run_full_analysis)

        # Delete profiles (if config wants)
        if self.config["keep_profiles"].exists() and not self.config["keep_profiles"].get():
            os.unlink(self._get_extractor_profile_path("low"))
            os.unlink(self._get_extractor_profile_path("high"))

    def _run_full_analysis(self, item):
        self._run_analysis_low_level(item)
        self._run_analysis_high_level(item)
        self._run_write_to_item(item)

        # Delete output files (if config wants)
        if self.config["keep_output"].exists() and not self.config["keep_output"].get():
            output_path = self._get_output_path_for_item(item, suffix="low")
            if os.path.isfile(output_path):
                os.unlink(output_path)
            output_path = self._get_output_path_for_item(item, suffix="high")
            if os.path.isfile(output_path):
                os.unlink(output_path)

    def _run_write_to_item(self, item):
        if not self.cfg_dry_run:
            if self.cfg_write:
                item.try_write()

    def _run_analysis_high_level(self, item):
        try:
            extractor_path = self._get_extractor_path(level="high")
            input_path = self._get_output_path_for_item(item, suffix="low")
            output_path = self._get_output_path_for_item(item, suffix="high")
            profile_path = self._get_extractor_profile_path(level="high")
        except ValueError as e:
            self._say("Value error: {0}".format(e))
            return
        except KeyError as e:
            self._say("Configuration error: {0}".format(e))
            return
        except FileNotFoundError as e:
            self._say("File not found error: {0}".format(e))
            return

        self._say("Running high-level analysis: {0}".format(input_path))
        self._run_essentia_extractor(extractor_path, input_path, output_path, profile_path)

        try:
            target_map = self.config["high_level_targets"]
            audiodata = bpmHelper.extract_from_output(output_path, target_map)
        except FileNotFoundError as e:
            self._say("File not found: {0}".format(e))
            return
        except KeyError as e:
            self._say("Attribute not present: {0}".format(e))
            return

        print(audiodata)

        if not self.cfg_dry_run:
            for attr in audiodata.keys():
                if audiodata.get(attr):
                    setattr(item, attr, audiodata.get(attr))
            item.store()

    def _run_analysis_low_level(self, item):
        try:
            extractor_path = self._get_extractor_path(level="low")
            input_path = self._get_input_path_for_item(item)
            output_path = self._get_output_path_for_item(item, suffix="low")
            profile_path = self._get_extractor_profile_path(level="low")
        except ValueError as e:
            self._say("Value error: {0}".format(e))
            return
        except KeyError as e:
            self._say("Configuration error: {0}".format(e))
            return
        except FileNotFoundError as e:
            self._say("File not found error: {0}".format(e))
            return

        self._say("Running low-level analysis: {0}".format(input_path))
        self._run_essentia_extractor(extractor_path, input_path, output_path, profile_path)

        try:
            target_map = self.config["low_level_targets"]
            audiodata = bpmHelper.extract_from_output(output_path, target_map)

        except FileNotFoundError as e:
            self._say("File not found: {0}".format(e))
            return
        except AttributeError as e:
            self._say("Attribute not present: {0}".format(e))
            return

        if not self.cfg_dry_run:
            for attr in audiodata.keys():
                if audiodata.get(attr):
                    setattr(item, attr, audiodata.get(attr))
            item.store()

    def _run_essentia_extractor(self, extractor_path, input_path, output_path, profile_path):
        if os.path.isfile(output_path):
            log.debug("Output exists: {0}".format(output_path))
            return

        log.debug("Extractor: {0}".format(extractor_path))
        log.debug("Input: {0}".format(input_path))
        log.debug("Output: {0}".format(output_path))
        log.debug("Profile: {0}".format(profile_path))

        proc = Popen([extractor_path, input_path, output_path, profile_path], stdout=PIPE, stderr=PIPE)
        stdout, stderr = proc.communicate()

        log.debug("The process exited with code: {0}".format(proc.returncode))
        log.debug("Process stdout: {0}".format(stdout.decode()))
        log.debug("Process stderr: {0}".format(stderr.decode()))

    def _execute_on_each_items(self, items, func):
        total = len(items)
        finished = 0
        with futures.ThreadPoolExecutor(max_workers=self.cfg_threads) as e:
            for _ in e.map(func, items):
                finished += 1
                # todo: show a progress bar (--progress-only option)

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
            raise FileNotFoundError("Input file({}) not found!".format(input_path))

        return input_path

    def _get_extraction_output_path(self):
        if self.config["output_path"].exists():
            if not os.path.isdir(self.config["output_path"].as_filename()):
                raise FileNotFoundError(
                    "Output path({}) does not exist!".format(self.config["output_path"].as_filename()))

            output_path = self.config["output_path"].as_filename()
        else:
            output_path = os.path.join(tempfile.gettempdir(), __PLUGIN_NAME__)
            if not os.path.isdir(output_path):
                os.makedirs(output_path)

        return output_path

    def _get_extractor_profile_path(self, level):
        if level not in ("low", "high"):
            raise ValueError("Profile level must be either 'low' or 'high'. Given: {}".format(level))

        profile_key = "{}_level_profile".format(level)
        profile_filename = "{}.yml".format(profile_key)
        profile_path = os.path.join(self._get_extraction_output_path(), profile_filename)

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
                raise FileNotFoundError("Extractor profile({}) not created!".format(profile_path))

        return profile_path

    def _get_extractor_path(self, level):
        if level not in ("low", "high"):
            raise ValueError("Extractor level must be either 'low' or 'high'. Given: {}".format(level))

        extractor_key = "{}_level_extractor".format(level)
        if not self.config[extractor_key].exists():
            raise KeyError("Key '{}' is not defined".format(extractor_key))

        extractor_path = self.config[extractor_key].as_filename()

        if not os.path.isfile(extractor_path):
            raise FileNotFoundError("Extractor({}) is not found!".format(extractor_path))

        return extractor_path

    def show_version_information(self):
        from beetsplug.xtractor.version import __version__
        self._say(
            "Xtractor(beets-{0}) plugin for Beets: v{1}".format(__PLUGIN_NAME__, __version__))

    def _say(self, msg):
        if not self.cfg_quiet:
            log.info(msg)
        else:
            log.debug(msg)
