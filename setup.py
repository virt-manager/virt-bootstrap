#!/usr/bin/env python
# -*- coding: utf-8; -*-

"""
Setup script used for building, testing, and installing modules
based on setuptools.
"""

import codecs
import os
import sys
import subprocess
import setuptools


def read(fname):
    """
    Utility function to read the text file.
    """
    path = os.path.join(os.path.dirname(__file__), fname)
    with codecs.open(path, encoding='utf-8') as fobj:
        return fobj.read()


class CheckPylint(setuptools.Command):
    """
    Check python source files with pylint and pycodestyle.
    """

    user_options = [('errors-only', 'e', 'only report errors')]
    description = "Check code using pylint and pycodestyle"

    def initialize_options(self):
        """
        Initialize the options to default values.
        """
        # pylint: disable=attribute-defined-outside-init
        self.errors_only = False

    def finalize_options(self):
        """
        Check final option values.
        """
        pass

    def run(self):
        """
        Call pycodestyle and pylint here.
        """

        res = 0
        files = ' '.join(["setup.py", "src/virtBootstrap/*.py", "tests/*.py"])
        output_format = "colorized" if sys.stdout.isatty() else "text"

        print(">>> Running pycodestyle ...")
        cmd = "pycodestyle "
        if (subprocess.call(cmd + files, shell=True) != 0):
            res = 1

        print(">>> Running pylint ...")
        args = ""
        if self.errors_only:
            args = "-E"
        cmd = "pylint %s --output-format=%s " % (args, format(output_format))
        if (subprocess.call(cmd + files, shell=True) != 0):
            res = 1

        sys.exit(res)


setuptools.setup(
    name='virt-bootstrap',
    version='0.1.0',
    author='Cedric Bosdonnat',
    author_email='cbosdonnat@suse.com',
    description='Container bootstrapping tool',
    license="GPLv3",
    long_description=read('README.md'),
    url='https://github.com/virt-manager/virt-bootstrap',
    # What does your project relate to?
    keywords='virtualization container rootfs',
    package_dir={"": "src"},
    packages=setuptools.find_packages('src'),
    test_suite='tests',
    entry_points={
        'console_scripts': [
            'virt-bootstrap=virtBootstrap.virt_bootstrap:main',
        ]
    },
    classifiers=[
        # How mature is this project? Common values are
        #   3 - Alpha
        #   4 - Beta
        #   5 - Production/Stable
        'Development Status :: 3 - Alpha',

        # Indicate who your project is intended for
        'Intended Audience :: System Administrators',
        'Intended Audience :: Developers',

        # Pick your license as you wish (should match "license" above)
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',

        # Specify the Python versions you support here. In particular, ensure
        # that you indicate whether you support Python 2, Python 3 or both.
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6'

    ],
    cmdclass={
        'pylint': CheckPylint
    },

    tests_require=['mock>=2.0'],

    extras_require={
        'dev': [
            'pylint',
            'pycodestyle'
        ]
    }
)
