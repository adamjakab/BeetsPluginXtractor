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

plg_ns = {}
about_path = convert_path('beetsplug/xtractor/about.py')
with open(about_path) as about_file:
    exec(about_file.read(), plg_ns)

# Setup
setup(
    name=plg_ns['__PACKAGE_NAME__'],
    version=plg_ns['__version__'],
    description=plg_ns['__PACKAGE_DESCRIPTION__'],
    author=plg_ns['__author__'],
    author_email=plg_ns['__email__'],
    url=plg_ns['__PACKAGE_URL__'],
    license='MIT',
    long_description=README,
    long_description_content_type='text/markdown',
    platforms='ALL',

    include_package_data=True,
    test_suite='test',
    packages=['beetsplug.xtractor'],

    python_requires='>=3.6',

    install_requires=[
        'beets>=1.4.9',
        'PyYAML'
    ],

    tests_require=[
        'pytest', 'nose', 'coverage',
        'mock', 'six', 'yaml',
    ],

    # Extras needed during testing
    extras_require={
        'tests': [],
    },

    classifiers=[
        'Topic :: Multimedia :: Sound/Audio',
        'License :: OSI Approved :: MIT License',
        'Environment :: Console',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
    ],
)
