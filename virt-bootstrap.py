#!/usr/bin/python
# Authors: Cedric Bosdonnat <cbosdonnat@suse.com>
#
# Copyright (C) 2017 SUSE, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#

import argparse
import gettext
import subprocess
import sys
import os
try:
    from urlparse import urlparse
except ImportError:
    from urllib.parse import urlparse

import sources


gettext.bindtextdomain("virt-bootstrap", "/usr/share/locale")
gettext.textdomain("virt-bootstrap")
try:
    gettext.install("virt-bootstrap",
                    localedir="/usr/share/locale",
                    unicode=False,
                    codeset = 'utf-8')
except IOError:
    import __builtin__
    __builtin__.__dict__['_'] = unicode


def get_source(args):
    url = urlparse(args.uri)
    scheme = url.scheme

    if scheme == "":
        scheme = 'file'

    try:
        class_name = "%sSource" % scheme.capitalize()
        clazz = getattr(sources, class_name)
        return clazz(url, args.username, args.password, args.not_secure)
    except Exception:
        raise Exception("Invalid image URI scheme: '%s'" % url.scheme)

def set_root_password(rootfs, password):
    users = 'root:%s' % password
    args = ['chpasswd', '-R', rootfs]
    p = subprocess.Popen(args, stdin=subprocess.PIPE)
    p.communicate(input=users)
    if p.returncode != 0:
        raise subprocess.CalledProcessError(p.returncode, cmd=args, output=None)

def bootstrap(args):
    source = get_source(args)
    os.makedirs(args.dest)
    source.unpack(args.dest)

    if args.root_password is not None:
        set_root_password(args.dest, args.root_password)

def main():
    parser = argparse.ArgumentParser(description=_("Container bootstrapping tool"),
                                     epilog=_("""

Example supported URI formats:

  docker:///ubuntu?tag=15.04
  docker://username:password@index.docker.io/private/image
  docker://privateregistry:5000/image
  virt-builder:///opensuse-42.1
  file:///path/to/local/rootfs.tar.xz
"""))
    parser.add_argument("uri",
                        help=_("Prepare and start a container from a given image"))
    parser.add_argument("dest",
                        help=_("Destination folder of the root file system to be created"))
    parser.add_argument("--not-secure", action='store_true',
                        help=_("Ignore HTTPS errors"))
    parser.add_argument("-u","--username", default=None,
                        help=_("Username to use to connect to the source"))
    parser.add_argument("-p","--password", default=None,
                        help=_("Password to use to connect to the source"))
    parser.add_argument("--root-password", default=None,
                        help=_("Root password to set in the created rootfs"))
    # TODO add --format [qcow2,dir] parameter
    # TODO add UID / GID mapping parameters

    try:
        args = parser.parse_args()

        # do the job here!
        bootstrap(args)

        sys.exit(0)
    except KeyboardInterrupt as e:
        sys.exit(0)
    except ValueError as e:
        for line in e:
            for l in line:
                sys.stderr.write("%s: %s\n" % (sys.argv[0], l))
        sys.stderr.flush()
        sys.exit(1)

if __name__ == '__main__':
   sys.exit(main())
