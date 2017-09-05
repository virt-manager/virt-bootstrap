#!/usr/bin/env python
# -*- coding: utf-8; -*-
# Authors: Cedric Bosdonnat <cbosdonnat@suse.com>
# Authors: Radostin Stoyanov <rstoyanov1@gmail.com>
#
# Copyright (C) 2017 SUSE, Inc.
# Copyright (C) 2017 Radostin Stoyanov
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
Setup script used for building, testing, and installing modules
based on setuptools.
"""

import codecs
import os
import re
import sys
import subprocess
import time
import setuptools
from setuptools.command.install import install
from setuptools.command.sdist import sdist

# pylint: disable=import-error, wrong-import-position
sys.path.insert(0, 'src')  # noqa: E402
import virtBootstrap


def read(fname):
    """
    Utility function to read the text file.
    """
    path = os.path.join(os.path.dirname(__file__), fname)
    with codecs.open(path, encoding='utf-8') as fobj:
        return fobj.read()


class PostInstallCommand(install):
    """
    Post-installation commands.
    """
    def run(self):
        """
        Post install script
        """
        cmd = [
            'pod2man',
            '--center=Container bootstrapping tool',
            '--name=VIRT-BOOTSTRAP',
            '--release=%s' % virtBootstrap.__version__,
            'man/virt-bootstrap.pod',
            'man/virt-bootstrap.1'
        ]
        if subprocess.call(cmd) != 0:
            raise RuntimeError("Building man pages has failed")
        install.run(self)


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


# SdistCommand is reused from the libvirt python binding (GPLv2+)
class SdistCommand(sdist):
    """
    Custom sdist command, generating a few files.
    """
    user_options = sdist.user_options

    description = "Update AUTHORS and ChangeLog; build sdist-tarball."

    def gen_authors(self):
        """
        Generate AUTHOS file out of git log
        """
        fdlog = os.popen("git log --pretty=format:'%aN <%aE>'")
        authors = []
        for line in fdlog:
            line = "   " + line.strip()
            if line not in authors:
                authors.append(line)

        authors.sort(key=str.lower)

        with open('AUTHORS.in', 'r') as fd1, open('AUTHORS', 'w') as fd2:
            for line in fd1:
                fd2.write(line.replace('@AUTHORS@', "\n".join(authors)))

    def gen_changelog(self):
        """
        Generate ChangeLog file out of git log
        """
        cmd = "git log '--pretty=format:%H:%ct %an  <%ae>%n%n%s%n%b%n'"
        fd1 = os.popen(cmd)
        fd2 = open("ChangeLog", 'w')

        for line in fd1:
            match = re.match(r'([a-f0-9]+):(\d+)\s(.*)', line)
            if match:
                timestamp = time.gmtime(int(match.group(2)))
                fd2.write("%04d-%02d-%02d %s\n" % (timestamp.tm_year,
                                                   timestamp.tm_mon,
                                                   timestamp.tm_mday,
                                                   match.group(3)))
            else:
                if re.match(r'Signed-off-by', line):
                    continue
                fd2.write("    " + line.strip() + "\n")

        fd1.close()
        fd2.close()

    def run(self):
        if not os.path.exists("build"):
            os.mkdir("build")

        if os.path.exists(".git"):
            try:
                self.gen_authors()
                self.gen_changelog()

                sdist.run(self)

            finally:
                files = ["AUTHORS",
                         "ChangeLog"]
                for item in files:
                    if os.path.exists(item):
                        os.unlink(item)
        else:
            sdist.run(self)


setuptools.setup(
    name='virt-bootstrap',
    version=virtBootstrap.__version__,
    author='Cedric Bosdonnat',
    author_email='cbosdonnat@suse.com',
    description='Container bootstrapping tool',
    license="GPLv3+",
    long_description=read('README.md'),
    url='https://github.com/virt-manager/virt-bootstrap',
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
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: System Administrators',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)',  # noqa: 501
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 3',

    ],
    cmdclass={
        'install': PostInstallCommand,
        'pylint': CheckPylint,
        'sdist': SdistCommand
    },

    data_files=[
        ("share/man/man1", ['man/virt-bootstrap.1'])
    ],

    tests_require=['mock>=2.0'],

    extras_require={
        'dev': [
            'pylint',
            'pycodestyle'
        ]
    }
)
