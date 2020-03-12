#  Copyright: Copyright (c) 2020., Adam Jakab
#
#  Author: Adam Jakab <adam at jakab dot pro>
#  Created: 3/13/20, 12:17 AM
#  License: See LICENSE.txt

import logging
from concurrent import futures
from optparse import OptionParser
from subprocess import Popen, PIPE

from beets.library import Library as BeatsLibrary
from beets.ui import Subcommand, decargs

import beetsplug.xtractor.helper as bpmHelper

# Module methods
log = logging.getLogger('beets.xtractor')


class XtractorCommand(Subcommand):
    config = None
    lib = None
    query = None
    parser = None

    cfg_auto = False
    cfg_dry_run = False
    cfg_write = True
    cfg_threads = 1
    cfg_force = False
    cfg_quiet = False

    def __init__(self, cfg):
        self.config = cfg.flatten()

        self.cfg_auto = self.config.get("auto")
        self.cfg_dry_run = self.config.get("dry-run")
        self.cfg_write = self.config.get("write")
        self.cfg_threads = self.config.get("threads")
        self.cfg_force = self.config.get("force")
        self.cfg_version = False
        self.cfg_quiet = self.config.get("quiet")

        self.parser = OptionParser(usage='%prog [options] [QUERY...]')

        self.parser.add_option(
            '-d', '--dry-run',
            action='store_true', dest='dryrun', default=self.cfg_dry_run,
            help=u'[default: {}] display the bpm values but do not update the '
                 u'library items'.format(
                self.cfg_dry_run)
        )

        self.parser.add_option(
            '-w', '--write',
            action='store_true', dest='write', default=self.cfg_write,
            help=u'[default: {}] write the bpm values to the media '
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
            name='xtractor',
            help=u'get more out of your songs...',
            aliases=["xt"]
        )

    def func(self, lib: BeatsLibrary, options, arguments):
        self.cfg_dry_run = options.dryrun
        self.cfg_write = options.write
        self.cfg_threads = options.threads
        self.cfg_force = options.force
        self.cfg_version = options.version
        self.cfg_quiet = options.quiet

        self.lib = lib
        self.query = decargs(arguments)

        if options.version:
            self.show_version_information()
            return

        self.analyse_songs()

    def show_version_information(self):
        from beetsplug.xtractor.version import __version__
        self._say(
            "Bpm Analyser(beets-xtractor) plugin for Beets: v{0}".format(__version__))

    def analyse_songs(self):
        # Setup the query
        query = self.query
        # todo: this does not make sense anymore (just like the name of the plugin)
        if not self.cfg_force:
            query_element = "bpm:0"
            query.append(query_element)

        # Get the library items
        # @todo: implement an option so that user can decide to limit the number of items per run
        items = self.lib.items(self.query)

        self.execute_on_items(items, self._run_full_analysis, msg='Low-level analysis...')
        # self.execute_on_items(items, self._run_analysis_low_level, msg='Low-level analysis...')
        # self.execute_on_items(items, self._run_analysis_high_level, msg='High-level analysis...')
        # self.execute_on_items(items, self._run_write_to_item, msg='Writing to files...')

    def _run_full_analysis(self, item):
        self._run_analysis_low_level(item)
        self._run_analysis_high_level(item)
        self._run_write_to_item(item)

    def _run_write_to_item(self, item):
        if not self.cfg_dry_run:
            if self.cfg_write:
                item.try_write()

    def _run_analysis_high_level(self, item):
        try:
            extractor_path = bpmHelper.get_extractor_path_svm()
            input_path = bpmHelper.get_output_path_for_item(item, clear=False, suffix="low")
            output_path = bpmHelper.get_output_path_for_item(item, clear=True, suffix="high")
            profile_path = bpmHelper.get_extractor_profile_path_svm()
        except FileNotFoundError as e:
            self._say("File not found: {0}".format(e))
            return
        except NotImplementedError as e:
            self._say("Not implemented: {0}".format(e))
            return

        self._say("Running high-level analysis: {0}".format(input_path))
        self._run_essentia_extractor(extractor_path, input_path, output_path, profile_path)

        try:
            audiodata = bpmHelper.extract_high_level_data(output_path)
        except FileNotFoundError as e:
            self._say("File not found: {0}".format(e))
            return
        except KeyError as e:
            self._say("Attribute not present: {0}".format(e))
            return

        if not self.cfg_dry_run:
            item['danceable'] = audiodata['danceable']
            item['gender'] = audiodata['gender']
            item['genre_rosamerica'] = audiodata['genre_rosamerica']
            item['voice_instrumental'] = audiodata['voice_instrumental']
            item['mood_acoustic'] = audiodata['mood_acoustic']
            item['mood_aggressive'] = audiodata['mood_aggressive']
            item['mood_electronic'] = audiodata['mood_electronic']
            item['mood_happy'] = audiodata['mood_happy']
            item['mood_party'] = audiodata['mood_party']
            item['mood_relaxed'] = audiodata['mood_relaxed']
            item['mood_sad'] = audiodata['mood_sad']
            item.store()

    def _run_analysis_low_level(self, item):
        try:
            extractor_path = bpmHelper.get_extractor_path()
            input_path = bpmHelper.get_input_path_for_item(item)
            output_path = bpmHelper.get_output_path_for_item(item, clear=True, suffix="low")
            profile_path = bpmHelper.get_extractor_profile_path()
        except FileNotFoundError as e:
            self._say("File not found: {0}".format(e))
            return
        except NotImplementedError as e:
            self._say("Not implemented: {0}".format(e))
            return

        self._say("Running low-level analysis: {0}".format(input_path))
        self._run_essentia_extractor(extractor_path, input_path, output_path, profile_path)

        try:
            audiodata = bpmHelper.extract_low_level_data(output_path)
        except FileNotFoundError as e:
            self._say("File not found: {0}".format(e))
            return
        except AttributeError as e:
            self._say("Attribute not present: {0}".format(e))
            return

        if not self.cfg_dry_run:
            item['bpm'] = audiodata['bpm']
            item.store()

    def _run_essentia_extractor(self, extractor_path, input_path, output_path, profile_path):
        log.debug("Extractor: {0}".format(extractor_path))
        log.debug("Input: {0}".format(input_path))
        log.debug("Output: {0}".format(output_path))
        log.debug("Profile: {0}".format(profile_path))

        proc = Popen([extractor_path, input_path, output_path, profile_path], stdout=PIPE, stderr=PIPE)
        stdout, stderr = proc.communicate()

        # self._say("EE-OUT: {0}".format(stdout.decode()))
        # self._say("EE-ERR: {0}".format(stderr.decode()))

    def execute_on_items(self, items, func, msg=None):
        total = len(items)
        finished = 0
        with futures.ThreadPoolExecutor(max_workers=self.cfg_threads) as e:
            for _ in e.map(func, items):
                finished += 1
                # todo: show a progress bar (--progress-only option)

    def _say(self, msg):
        if not self.cfg_quiet:
            log.info(msg)
        else:
            log.debug(msg)
