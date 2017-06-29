#!/usr/bin/env python
# Authors: Cedric Bosdonnat <cbosdonnat@suse.com>
#
# Copyright (C) 2017 SUSE, Inc.
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
Main executable file which process input arguments
and calls corresponding methods on appropriate object.
"""

import argparse
import gettext
import sys
import os
from textwrap import dedent
from logging import getLogger, DEBUG, INFO, WARNING, error
from subprocess import CalledProcessError, Popen, PIPE
try:
    from urlparse import urlparse
except ImportError:
    from urllib.parse import urlparse

from virtBootstrap import sources


gettext.bindtextdomain("virt-bootstrap", "/usr/share/locale")
gettext.textdomain("virt-bootstrap")
try:
    gettext.install("virt-bootstrap",
                    localedir="/usr/share/locale",
                    codeset='utf-8')
except IOError:
    try:
        import __builtin__
        # pylint: disable=undefined-variable
        __builtin__.__dict__['_'] = unicode
    except ImportError:
        import builtin
        builtin.__dict__['_'] = str


def get_source(args):
    """
    Get object which match the source type
    """
    url = urlparse(args.uri)
    scheme = url.scheme

    if scheme == "":
        scheme = 'file'

    try:
        class_name = "%sSource" % scheme.capitalize()
        clazz = getattr(sources, class_name)
        return clazz(url, args)
    except Exception:
        raise Exception("Invalid image URI scheme: '%s'" % url.scheme)


def set_root_password(rootfs, password):
    """
    Set password on the root user in rootfs
    """
    users = 'root:%s' % password
    args = ['chpasswd', '-R', rootfs]
    chpasswd = Popen(args, stdin=PIPE)
    chpasswd.communicate(input=users)
    if chpasswd.returncode != 0:
        raise CalledProcessError(chpasswd.returncode, cmd=args, output=None)


def bootstrap(args):
    """
    Get source object and call unpack method
    """
    # Set log level
    logger = getLogger()
    logger.setLevel(DEBUG if args.debug else WARNING if args.quiet else INFO)

    source = get_source(args)
    if not os.path.exists(args.dest):
        os.makedirs(args.dest)
    elif not os.path.isdir(args.dest):  # Show error if not directory
        error("Destination path '%s' is not directory.", args.dest)
        sys.exit(1)
    elif not os.access(args.dest, os.W_OK):  # Check write permissions
        error("No write permissions on destination path '%s'", args.dest)
        sys.exit(1)

    source.unpack(args.dest)

    if args.root_password is not None:
        set_root_password(args.dest, args.root_password)


def main():
    parser = argparse.ArgumentParser(
        description=_("Container bootstrapping tool"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=dedent(_('''
                            Example supported URI formats:
                            ----------------------------------------
                              docker://ubuntu:latest
                              docker://docker.io/fedora
                              docker://privateregistry:5000/image
                              file:///path/to/local/rootfs.tar.xz
                            ----------------------------------------

                        ''')))
    parser.add_argument("uri",
                        help=_("URI of container image"))
    parser.add_argument("dest",
                        help=_("Destination folder"
                               "where image files to be extracted"))
    parser.add_argument("--not-secure", action='store_true',
                        help=_("Ignore HTTPS errors"))
    parser.add_argument("-u", "--username", default=None,
                        help=_("Username to use"
                               "to connect to the source registry"))
    parser.add_argument("-p", "--password", default=None,
                        help=_("Password to use"
                               "to connect to the source registry"))
    parser.add_argument("--root-password", default=None,
                        help=_("Root password to set in the created rootfs"))
    parser.add_argument("--no-cache", action="store_true",
                        help=_("Do not store downloaded Docker images"))
    parser.add_argument("-f", "--format", default='dir',
                        choices=['dir', 'qcow2'],
                        help=_("Format to be used for the root filesystem"))
    parser.add_argument("-d", "--debug", action="store_true",
                        help=_("Show debug messages"))
    parser.add_argument("-q", "--quiet", action="store_true",
                        help=_("Suppresses messages notifying about"
                               "current state or actions of virt-bootstrap"))
    # TODO add UID / GID mapping parameters

    try:
        args = parser.parse_args()

        # do the job here!
        bootstrap(args)

        sys.exit(0)
    except KeyboardInterrupt:
        sys.exit(0)
    except ValueError as err:
        sys.stderr.write("%s: %s\n" % (sys.argv[0], err))
        sys.stderr.flush()
        sys.exit(1)


if __name__ == '__main__':
    sys.exit(main())
