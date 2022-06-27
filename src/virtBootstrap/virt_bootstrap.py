#!/usr/bin/env python
# -*- coding: utf-8 -*-
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
import logging
import sys
import os
from textwrap import dedent
try:
    from urlparse import urlparse
except ImportError:
    from urllib.parse import urlparse

from virtBootstrap import sources
from virtBootstrap import progress
from virtBootstrap import utils


__version__ = "1.1.1"


gettext.bindtextdomain("virt-bootstrap", "/usr/share/locale")
gettext.textdomain("virt-bootstrap")
try:
    gettext.install("virt-bootstrap",
                    localedir="/usr/share/locale")
except IOError:
    try:
        import __builtin__
        # pylint: disable=undefined-variable
        __builtin__.__dict__['_'] = unicode
    except ImportError:
        import builtin
        builtin.__dict__['_'] = str

# pylint: disable=invalid-name
# Create logger
logger = logging.getLogger('virtBootstrap.virt_bootstrap')


def get_source(source_type):
    """
    Get object which match the source type
    """
    try:
        class_name = "%sSource" % source_type.title().replace('-', '')
        clazz = getattr(sources, class_name)
        return clazz
    except Exception:
        raise Exception("Invalid image URL scheme: '%s'" % source_type)


def parse_idmap(idmap):
    """
    Parse user input to 'start', 'target' and 'count' values.

    Example:
        ['0:1000:10', '500:500:10']
    is converted to:
        [[0, 1000, 10], [500, 500, 10]]
    """
    if not isinstance(idmap, list) or idmap == []:
        return None
    try:
        idmap_list = []
        for x in idmap:
            start, target, count = x.split(':')
            idmap_list.append([int(start), int(target), int(count)])

        return idmap_list
    except Exception:
        raise ValueError("Invalid UID/GID mapping value: %s" % idmap)


# pylint: disable=too-many-arguments
def bootstrap(uri, dest,
              fmt=utils.DEFAULT_OUTPUT_FORMAT,
              username=None,
              password=None,
              root_password=None,
              uid_map=None,
              gid_map=None,
              not_secure=False,
              no_cache=False,
              progress_cb=None):
    """
    Get source object and call unpack method
    """
    if fmt == 'dir' and os.geteuid() != 0:
        if uid_map or gid_map:
            raise ValueError("UID/GID mapping with 'dir' format is "
                             "allowed only for root.")
        logger.warning("All extracted files will be owned by the current "
                       "unprivileged user.")

    # Get instance of progress storing module
    prog = progress.Progress(progress_cb)

    uri = urlparse(uri)
    source = get_source(uri.scheme or 'file')
    dest = os.path.abspath(dest)

    if not os.path.exists(dest):
        os.makedirs(dest)
    elif dest == "/":  # Don't overwrite root
        logger.error("Unpack to root directory is not allowed")
        sys.exit(1)
    elif not os.path.isdir(dest):  # Show error if not directory
        logger.error("Destination path '%s' is not directory.", dest)
        sys.exit(1)
    elif not os.access(dest, os.W_OK):  # Check write permissions
        logger.error("No write permissions on destination path '%s'", dest)
        sys.exit(1)

    if utils.is_selinux_enabled():
        logger.debug("Setting file SELinux security context")
        if not utils.chcon(dest, "container_file_t"):
            logger.error("Can't set SElinux context on destination path '%s'",
                         dest)
            sys.exit(1)

    if uid_map is None:
        uid_map = []

    if gid_map is None:
        gid_map = []

    if root_password:
        if root_password.startswith('file:'):
            root_password_file = root_password[len('file:'):]
            logger.debug("Reading root password from file %s",
                         root_password_file)
            with open(root_password_file) as pwdfile:
                root_password = pwdfile.readline().rstrip("\n\r")
        else:
            logger.warning(_("Passing the root_password directly via command "
                             "line is deprecated and using the 'file:' "
                             "selector is the recommended way to use this "
                             "option."))

    source(uri=uri,
           fmt=fmt,
           username=username,
           password=password,
           uid_map=uid_map,
           gid_map=gid_map,
           root_password=root_password,
           not_secure=not_secure,
           no_cache=no_cache,
           progress=prog).unpack(dest)

    if fmt == "dir":
        if root_password is not None:
            logger.info("Setting password of the root account")
            utils.set_root_password_in_rootfs(dest, root_password)

        if uid_map or gid_map:
            logger.info("Mapping UID/GID")
            utils.mapping_uid_gid(dest, uid_map, gid_map)


def set_logging_conf(loglevel=None):
    """
    Set format and logging level
    """
    # Get logger
    module_logger = logging.getLogger('virtBootstrap')

    # Create console handler
    console_handler = logging.StreamHandler()

    # Set logging format
    log_format = ('%(levelname)-8s: %(message)s')
    console_handler.setFormatter(logging.Formatter(log_format))

    # Add the handlers to logger
    module_logger.addHandler(console_handler)

    # Set logging level
    module_logger.setLevel(loglevel or logging.INFO)


def main():
    parser = argparse.ArgumentParser(
        description=_("Container bootstrapping tool"),
        conflict_handler='resolve',
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

    # pylint: disable=protected-access
    parser._positionals.title = 'ARGUMENTS'
    parser._optionals.title = 'OPTIONS'

    parser.add_argument(
        "URI", help=_("Source URI")
    )
    parser.add_argument(
        "DEST", help=_("Destination folder")
    )
    parser.add_argument(
        '--version',
        help=_("Print the version"),
        action='version',
        version='%(prog)s ' + __version__
    )
    parser.add_argument(
        "-f", "--format",
        help=_('Output format of the root filesystem. '
               'Allowed values are "dir" (default) and "qcow2".'),
        default=utils.DEFAULT_OUTPUT_FORMAT,
        choices=['dir', 'qcow2'],
        metavar=''
    )
    parser.add_argument(
        "--root-password",
        help=_("Set root password"),
        default=None,
        metavar=''
    )
    parser.add_argument(
        "--no-cache",
        help=_("Do not store downloaded Docker images"),
        action="store_true"
    )
    parser.add_argument(
        "-d", "--debug",
        help=_("Show debug messages"),
        action="store_const",
        dest="loglevel",
        const=logging.DEBUG
    )
    parser.add_argument(
        "-q", "--quiet",
        help=_("Don't print progress messages"),
        action="store_const",
        dest="loglevel",
        const=logging.WARNING
    )
    parser.add_argument(
        "--status-only",
        help=_("Show only progress information"),
        action="store_const",
        const=utils.write_progress
    )

    # Authentication arguments
    auth_group = parser.add_argument_group(
        title='AUTHENTICATION',
        description='Credentials used to authenticte to '
                    'Docker source registry.'
    )
    auth_group.add_argument(
        "-u", "--username",
        help=_("Use USERNAME to access source registry"),
        default=None,
        metavar='USERNAME'
    )
    auth_group.add_argument("-u", help="", default=None, metavar='USERNAME')
    auth_group.add_argument(
        "-p", "--password",
        help=_("Use PASSWORD to access source registry"),
        default=None,
        metavar='PASSWORD'
    )
    auth_group.add_argument("-p", help="", default=None, metavar='PASSWORD')
    auth_group.add_argument(
        "--not-secure",
        help=_("Ignore HTTPS errors"),
        action='store_true'
    )

    # Ownership mapping arguments
    idmap_group = parser.add_argument_group(
        title='UID/GID mapping',
        description='Remapping ownership of all files inside rootfs.\n'
        'These arguments can be specified multiple times.\n'
        'Format:\t<start>:<target>:<count>\n'
        'Example:\t--idmap 500:1500:10 --idmap 0:1000:10'
    )
    idmap_group.add_argument(
        "--uidmap",
        help=_("Map UIDs"),
        default=None,
        action='append',
        metavar=''
    )
    idmap_group.add_argument(
        "--gidmap",
        help=_("Map GIDs"),
        default=None,
        action='append',
        metavar=''
    )
    idmap_group.add_argument(
        "--idmap",
        help=_("Map both UIDs/GIDs"),
        default=None,
        action='append',
        metavar=''
    )

    try:
        args = parser.parse_args()

        if not args.status_only:
            # Configure logging lovel/format
            set_logging_conf(args.loglevel)

        uid_map = parse_idmap(args.idmap) if args.idmap else []
        gid_map = list(uid_map) if args.idmap else []
        if args.uidmap:
            uid_map += parse_idmap(args.uidmap)
        if args.gidmap:
            gid_map += parse_idmap(args.gidmap)

        # do the job here!
        bootstrap(uri=args.URI,
                  dest=args.DEST,
                  fmt=args.format,
                  username=args.username,
                  password=args.password,
                  root_password=args.root_password,
                  uid_map=uid_map,
                  gid_map=gid_map,
                  not_secure=args.not_secure,
                  no_cache=args.no_cache,
                  progress_cb=args.status_only)

        sys.exit(0)
    except KeyboardInterrupt:
        sys.exit(0)
    except ValueError as err:
        sys.stderr.write("%s: %s\n" % (sys.argv[0], err))
        sys.stderr.flush()
        sys.exit(1)


if __name__ == '__main__':
    sys.exit(main())
