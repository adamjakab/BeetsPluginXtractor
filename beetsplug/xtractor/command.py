#  Copyright: Copyright (c) 2020., Adam Jakab
#  Author: Adam Jakab <adam at jakab dot pro>
#  License: See LICENSE.txt

import hashlib
import json
import os
import multiprocessing
import tempfile
from concurrent import futures
from optparse import OptionParser
from subprocess import Popen, PIPE

import yaml
from beets import dbcore
from beets.library import Library, Item, parse_query_string
from beets.ui import Subcommand, decargs
from confuse import Subview
from beetsplug.xtractor import helper


class XtractorCommand(Subcommand):
    config: Subview = None

    lib = None
    query = None
    parser = None

    items_to_analyse = None

    cfg_auto = False
    cfg_dry_run = False
    cfg_write = True
    cfg_threads = 1
    cfg_force = False
    cfg_quiet = False

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

        self.parser = OptionParser(
            usage='beet {plg} [options] [QUERY...]'.format(
                plg=helper.plg_ns['__PLUGIN_NAME__']
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
            name=helper.plg_ns['__PLUGIN_NAME__'],
            aliases=[helper.plg_ns['__PLUGIN_ALIAS__']] if
            helper.plg_ns['__PLUGIN_ALIAS__'] else [],
            help=helper.plg_ns['__PLUGIN_SHORT_DESCRIPTION__']
        )

    def func(self, lib: Library, options, arguments):
        self.cfg_dry_run = options.dryrun
        self.cfg_write = options.write
        self.cfg_threads = options.threads
        self.cfg_force = options.force
        self.cfg_version = options.version
        self.cfg_count_only = options.count_only
        self.cfg_quiet = options.quiet

        # Auto Thread Count
        if self.cfg_threads == 0:
            self.cfg_threads = multiprocessing.cpu_count()
            self._say("Adjusting max threads to CPU count: {0}".format(self.cfg_threads), True)

        self.lib = lib
        self.query = decargs(arguments)

        if options.version:
            self.show_version_information()
            return

        self.xtract()

    def xtract(self):
        self.find_items_to_analyse()
        self._say("Number of items to be processed: {}".format(len(self.items_to_analyse)), False)

        # Count only and exit
        if self.cfg_count_only:
            return

        # Run tasks on selected items
        self._execute_on_each_items(self.items_to_analyse, self.run_full_analysis)

        # Delete profiles (if config wants)
        if self.config["keep_profiles"].exists() and not self.config["keep_profiles"].get():
            os.unlink(self._get_extractor_profile_path())

    def find_items_to_analyse(self):
        # Parse the incoming query
        parsed_query, parsed_sort = parse_query_string(" ".join(self.query), Item)
        combined_query = parsed_query

        # Add unprocessed items query
        if not self.cfg_force:
            # Set up the query for unprocessed items
            subqueries = []
            target_maps = ["low_level_targets", "high_level_targets"]
            for map_key in target_maps:
                target_map = self.config[map_key]
                for fld in target_map:
                    if target_map[fld]["required"].exists() and target_map[fld]["required"].get(bool):
                        fast = fld in Item._fields
                        query_item = dbcore.query.MatchQuery(fld, None, fast=fast)
                        subqueries.append(query_item)

            unprocessed_items_query = dbcore.query.OrQuery(subqueries)
            combined_query = dbcore.query.AndQuery([parsed_query, unprocessed_items_query])

        self._say("Combined query: {}".format(combined_query))

        # Get the library items
        self.items_to_analyse = self.lib.items(combined_query, parsed_sort)
        if len(self.items_to_analyse) == 0:
            self._say("No items to process")
            return

    def run_full_analysis(self, item):
        self._run_analysis(item)
        self._run_write_to_item(item)

        # Delete output files (if config wants)
        if self.config["keep_output"].exists() and not self.config["keep_output"].get():
            output_path = self._get_output_path_for_item(item)
            if os.path.isfile(output_path):
                os.unlink(output_path)

    def _run_write_to_item(self, item):
        if not self.cfg_dry_run:
            if self.cfg_write:
                item.try_write()

    def _run_analysis(self, item):
        try:
            extractor_path = self._get_extractor_path()
            input_path = self._get_input_path_for_item(item)
            output_path = self._get_output_path_for_item(item)
            profile_path = self._get_extractor_profile_path()
        except ValueError as e:
            self._say("Value error: {0}".format(e))
            return
        except KeyError as e:
            self._say("Configuration error: {0}".format(e))
            return
        except FileNotFoundError as e:
            self._say("File not found error: {0}".format(e))
            return

        self._say("Running analysis for: {0}".format(input_path))
        self._run_essentia_extractor(extractor_path, input_path, output_path, profile_path)

        # Extract low level targets
        try:
            audiodata_low = helper.extract_from_output(output_path, self.config["low_level_targets"])
        except FileNotFoundError as e:
            self._say("File not found: {0}".format(e))
            return

        # Extract high level targets
        try:
            audiodata_high = helper.extract_from_output(output_path, self.config["high_level_targets"])
        except FileNotFoundError as e:
            self._say("File not found: {0}".format(e))
            return

        # Merge audio data
        audiodata = {**audiodata_low, **audiodata_high}
        self._say("Audiodata: {}".format(audiodata))

        # Update and Store Item
        if not self.cfg_dry_run:
            for attr in audiodata.keys():
                if audiodata.get(attr):
                    setattr(item, attr, audiodata.get(attr))
            item.store()

    def _run_essentia_extractor(self, extractor_path, input_path, output_path, profile_path):
        if os.path.isfile(output_path):
            self._say("Output exists: {0}".format(output_path))
            return

        self._say("Extractor: {0}".format(extractor_path))
        self._say("Input: {0}".format(input_path))
        self._say("Output: {0}".format(output_path))
        self._say("Profile: {0}".format(profile_path))

        cmd_and_args = [extractor_path, input_path, output_path, profile_path]
        self._say("Executing: {0}".format(' '.join(f'"{a}"' for a in cmd_and_args)))
        proc = Popen(cmd_and_args, stdout=PIPE, stderr=PIPE)
        stdout, stderr = proc.communicate()

        self._say("The process exited with code: {0}".format(proc.returncode))
        self._say("Process stdout: {0}".format(stdout.decode()))
        self._say("Process stderr: {0}\n".format(stderr.decode()))

        # Make sure file is encoded correctly
        # Sometimes media files have funky tags
        helper.asciify_file_content(output_path)

    def _execute_on_each_items(self, items, func):
        total = len(items)
        finished = 0
        with futures.ThreadPoolExecutor(max_workers=self.cfg_threads) as e:
            if total and not self.cfg_quiet:
                self._show_progress(finished, total)
            for _ in e.map(func, items):
                finished += 1
                if not self.cfg_quiet:
                    self._show_progress(finished, total)

    def _show_progress(self, done, total):
        print('Finished: [%d/%d]\r' % (done, total), end="")

    def _get_output_path_for_item(self, item: Item):
        identifier = item.get("mb_trackid")
        if not identifier or '/' in identifier:
            input_path = self._get_input_path_for_item(item)
            identifier = hashlib.md5(input_path.encode('utf-8')).hexdigest()

        output_file = "{id}.{ext}".format(
            id=identifier,
            ext="json"
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
            output_path = os.path.join(tempfile.gettempdir(),
                                       helper.plg_ns['__PLUGIN_NAME__'])
            if not os.path.isdir(output_path):
                os.makedirs(output_path)

        return output_path

    def _get_extractor_profile_path(self):
        profile_key = "extractor_profile"
        profile_filename = "profile.yml"
        profile_path = os.path.join(self._get_extraction_output_path(), profile_filename)

        if not os.path.isfile(profile_path):
            # Generate profile file
            if not self.config[profile_key].exists():
                raise KeyError("Key '{}' is not defined".format(profile_key))

            profile_content = self.config[profile_key].flatten()
            profile_content = json.loads(json.dumps(profile_content))
            # Override outputFormat (we only handle json for now)
            profile_content["outputFormat"] = "json"

            f = open(profile_path, 'w+')
            yaml.dump(profile_content, f, allow_unicode=True)

            if not os.path.isfile(profile_path):
                raise FileNotFoundError("Extractor profile({}) not created!".format(profile_path))

        return profile_path

    def _get_extractor_path(self):
        extractor_key = "essentia_extractor"
        if not self.config[extractor_key].exists():
            raise KeyError("Key '{}' is not defined".format(extractor_key))

        extractor_path = self.config[extractor_key].as_filename()

        if not os.path.isfile(extractor_path):
            raise FileNotFoundError("Extractor({}) is not found!".format(
                extractor_path))

        return extractor_path

    def show_version_information(self):
        self._say("{pt}({pn}) plugin for Beets: v{ver}".format(
            pt=helper.plg_ns['__PACKAGE_TITLE__'],
            pn=helper.plg_ns['__PACKAGE_NAME__'],
            ver=helper.plg_ns['__version__']
        ), log_only=False)

    @staticmethod
    def _say(msg, log_only=True, is_error=False):
        helper.say(msg, log_only, is_error)
