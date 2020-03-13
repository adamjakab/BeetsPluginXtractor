#  Copyright: Copyright (c) 2020., Adam Jakab
#
#  Author: Adam Jakab <adam at jakab dot pro>
#  Created: 3/13/20, 12:17 AM
#  License: See LICENSE.txt

import pathlib
from distutils.util import convert_path

from setuptools import setup

# The directory containing this file
HERE = pathlib.Path(__file__).parent

# The text of the README file
README = (HERE / "README.md").read_text()

main_ns = {}
ver_path = convert_path('beetsplug/xtractor/version.py')
with open(ver_path) as ver_file:
    exec(ver_file.read(), main_ns)

# Setup
setup(
    name='beets-xtractor',
    version=main_ns['__version__'],
    description='A beets plugin for getting something more out of your music...',
    author='Adam Jakab',
    author_email='adam@jakab.pro',
    url='https://github.com/adamjakab/BeetsPluginEssentiaExtractor',
    license='MIT',
    long_description=README,
    long_description_content_type='text/markdown',
    platforms='ALL',

    include_package_data=True,
    test_suite='test',

    packages=['beetsplug.xtractor'],

    install_requires=[
        'beets>=1.4.9',
        'confuse',
        'PyYAML'
    ],

    tests_require=[
        'pytest',
        'nose',
        'coverage',
        'mock',
        'six'
    ],

    classifiers=[
        'Topic :: Multimedia :: Sound/Audio',
        'License :: OSI Approved :: MIT License',
        'Environment :: Console',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
    ],
)
