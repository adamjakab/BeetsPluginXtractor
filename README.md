[![Coverage Status](https://coveralls.io/repos/github/adamjakab/BeetsPluginXtractor/badge.svg?branch=master)](https://coveralls.io/github/adamjakab/BeetsPluginXtractor?branch=master)
[![PyPi](https://img.shields.io/pypi/v/beets-xtractor.svg)](https://pypi.org/project/beets-xtractor/)
[![PyPI pyversions](https://img.shields.io/pypi/pyversions/beets-xtractor.svg)](https://pypi.org/project/beets-xtractor/)
[![MIT license](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE.txt)

# Xtractor (Beets Plugin)

The *beets-xtractor* plugin lets you, through the use of the [Essentia](https://essentia.upf.edu/index.html) extractors,
to obtain low and high level musical information from your songs.

Currently, the following attributes are extracted for each library item:
`bpm`, `danceability`, `beats_count`, `average_loudness`,  `danceable`, `gender`, `is_male`, `is_female`,
`genre_rosamerica`, `voice_instrumental`, `is_voice`, `is_instrumental`, `mood_acoustic`,
`mood_aggressive`, `mood_electronic`, `mood_happy`, `mood_sad`, `mood_party`, `mood_relaxed`, `mood_mirex`,
`mood_mirex_cluster_1`, `mood_mirex_cluster_2`, `mood_mirex_cluster_3`, `mood_mirex_cluster_4`, `mood_mirex_cluster_5`

## Installation
The plugin can be installed via:

```shell script
$ pip install beets-xtractor
```
and activated the usual way by adding `xtractor` to the list of plugins in your configuration:

```yaml
plugins:
    - xtractor
```

### Install the Essentia extractors

You will also need the `streaming_extractor_music` binary extractor from the [Essentia project](#credits). You will need
to compile this extractor yourself.
The [official installation documentation](https://essentia.upf.edu/installing.html#compiling-essentia-from-source)
is somewhat complex but with some cross searching on the internet you will make it. If you are stuck you can use
the [Issue tracker](https://github.com/adamjakab/BeetsPluginXtractor/issues). Make sure you compile it with Gaia
support (`--with-gaia`) otherwise will not be able to use the high level models.

### Download the SVM models

The second extractor uses prebuilt trained models for prediction. You need to download these from
here: [SVM Models](https://essentia.upf.edu/svm_models/). I suggest that you download the more recent beta5 version.
This means that your binaries must match this version. Put the downloaded models in any folder from which they can be
accessed.

### Precompiled packages

If you happen to use Linux to run beets, the MusicPlayerPlus project provides pre-compiled packages that were split out from the main project and can be downloaded separately here: https://github.com/doctorfree/mpplus-essentia/releases.

The package contains a precompiled extractor binary as well as the fitting SVM models (as of writing 2.1 beta5).

`mpplus-essentia` provides the files you need for your beets configuration as `/usr/bin/essentia_streaming_extractor_music` and `/usr/share/mpplus-essentia/svm_models/*.history`

## Configuration
All your configuration will need to go under the `xtractor` key. This is what your configuration should look like:

```yaml
xtractor:
    auto: no
    dry-run: no
    write: yes
    threads: 1
    force: no
    quiet: no
    keep_output: yes
    keep_profiles: no
    output_path: /mnt/data/xtraction_data
    essentia_extractor: /mnt/data/extractors/beta5/streaming_extractor_music
    extractor_profile:
        highlevel:
            svm_models:
                - /mnt/data/extractors/beta5/svm_models/danceability.history
                - /mnt/data/extractors/beta5/svm_models/gender.history
                - /mnt/data/extractors/beta5/svm_models/genre_rosamerica.history
                - /mnt/data/extractors/beta5/svm_models/mood_acoustic.history
                - /mnt/data/extractors/beta5/svm_models/mood_aggressive.history
                - /mnt/data/extractors/beta5/svm_models/mood_electronic.history
                - /mnt/data/extractors/beta5/svm_models/mood_happy.history
                - /mnt/data/extractors/beta5/svm_models/mood_sad.history
                - /mnt/data/extractors/beta5/svm_models/mood_party.history
                - /mnt/data/extractors/beta5/svm_models/mood_relaxed.history
                - /mnt/data/extractors/beta5/svm_models/voice_instrumental.history
                - /mnt/data/extractors/beta5/svm_models/moods_mirex.history
```

First of all, you will need adjust all paths. Put the path of the extractor binary in `essentia_extractor` and
substitute the location of the SVM models with your local path under the `svm_models` section. Finally, set
the `output_path` to indicate where the extracted data files will be stored. If you do not set this, a temporary path
will be used.

**Note on shell tilde expansion**:  Please note that you cannot use shell expansion on the `svm_models` (i.e.: do not use `~` for your home folder).
The entire section of `extractor_profile` is passed as-is to the essentia extractor binary and it will not do tilde expansion on your paths.
The rest of the path keys such as `essentia_extractor` and `output_path` are used by the plugin itself and it will take
care of expanding the tilde symbol (`~`) to the home directory of the user running the script.

By default both `keep_output` and `keep_profile` options are set to `no`. This means that after extraction (and the
storage of the important information) the profile files used to pass to the extractors, and the json files created by
the extractors will be deleted. There are various reasons you might want to keep these files. One is for debugging
purposes. Another is to see what else is in these files (there is a lot) and maybe to use them with some other projects
of yours. Lastly, you might want to keep these because the plugin only extracts data if these files are not present. If
you store them, on a successive extraction, the plugin will skip the extraction and use these files (they are named
by `mb_trackid`) - speeding up the process a lot.

The `force` option instructs the plugin to execute on items which already have the required properties.

The `threads` option sets the number of concurrent executions. By default this is set to 1.
If you remove this option or if you set it to 0 the number of CPU cores present on your machine will be used.
The extraction is quite a CPU intensive process so there might be cases when you want to limit it to just 1.

The `write` option instructs the plugin to write the extracted attributes to the media file right away. Note that only `bpm` is actually written to the media file, all the other attributes are flex attributes and are only stored in the database.

The `dry-run` option shows what would be done without actually doing it.

**NOTE**: Please note that the `auto` option is not yet implemented. For now you will have to call the xtractor plugin manually.


## Usage

Invoke the plugin as:

    $ beet xtractor [options] [QUERY...]
    
For a more verbose reporting use the `-v` flag on `beet`:

    $ beet -v xtractor [options] [QUERY...]
    
The plugin has also got a shorthand `xt` so you can also invoke it like this:

    $ beet xt [options] [QUERY...]


The following command line options are available:

**--dry-run [-d]**: Only show what would be done - displays the extracted values but does not store them in the library.

**--write [-w]**: Write the values (bpm only) to the media files.

**--threads=THREADS [-t THREADS]**: The number of concurrently running executions.

**--force [-f]**: Force the analysis of all items (skip attribute checks).

**--count-only [-c]**: Show the number of items to be processed and exit. Extraction will not be executed.

**--quiet [-q]**: Run without any output.

**--version [-v]**: Display the version number of the plugin. Useful when you need to report some issue and you have to state the version of the plugin you are using.

These command line options will override those specified in the configuration file.


## Issues
- If something is not working as expected please use the Issue tracker.
- If the documentation is not clear please use the Issue tracker.
- If you have a feature request please use the Issue tracker.
- In any other situation please use the Issue tracker.


## Other plugins by the same author

- [beets-goingrunning](https://github.com/adamjakab/BeetsPluginGoingRunning)
- [beets-xtractor](https://github.com/adamjakab/BeetsPluginXtractor)
- [beets-yearfixer](https://github.com/adamjakab/BeetsPluginYearFixer)
- [beets-autofix](https://github.com/adamjakab/BeetsPluginAutofix)
- [beets-describe](https://github.com/adamjakab/BeetsPluginDescribe)
- [beets-bpmanalyser](https://github.com/adamjakab/BeetsPluginBpmAnalyser)
- [beets-template](https://github.com/adamjakab/BeetsPluginTemplate)


## Credits
Essentia is an open-source C++ library with Python bindings for audio analysis and audio-based music information retrieval. It is released under the Affero GPLv3 license and is also available under proprietary license upon request. This plugin is just a mere wrapper around this library. [Learn more about the Essentia project](http://essentia.upf.edu)


## References
- [Essentia](https://essentia.upf.edu/index.html)
- [SVM Models](https://essentia.upf.edu/svm_models/)
- [Essentia Licensing](https://essentia.upf.edu/licensing_information.html)
- [MTG Github - Music Technology Group](https://github.com/MTG)
- [Acousticbrainz Downloads](https://acousticbrainz.org/download)


## Final Remarks
Enjoy!

