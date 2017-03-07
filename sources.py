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

import hashlib
import json
import shutil
import subprocess
import tempfile
import getpass

def checksum(path, sum_type, sum_expected):
    algorithm = getattr(hashlib, sum_type)
    try:
        fd = open(path, 'rb')
        content = fd.read()
        fd.close()

        actual = algorithm(content).hexdigest()
        return actual == sum_expected
    except:
        return False


class FileSource:
    def __init__(self, url, insecure):
        self.path = url.path

    def unpack(dest):
        # We assume tar is intelligent enough to find out
        # the compression type to use and to strip leading '/',
        # not sure if this is safe enough
        subprocess.check_call(["tar", "-C", dest, "xf", self.path])

class DockerSource:
    def __init__(self, url, username, password, insecure):
        self.registry = url.netloc
        self.image = url.path
        self.username = username
        self.password = password
        self.insecure = insecure
        if self.image.startswith('/'):
            self.image = self.image[1:]

    def unpack(self, dest):
        tmpDest = tempfile.mkdtemp('virt-bootstrap')

        try:
            # Run skopeo copy into a tmp folder
            # Note: we don't want to expose --src-cert-dir to users as
            #       they should place the certificates in the system
            #       folders for broader enablement
            cmd = ["skopeo", "copy",
                   "docker://%s/%s" % (self.registry, self.image),
                   "dir:/%s" % tmpDest]
            if self.insecure:
                cmd.append('--src-tls-verify=false')
            if self.username:
                if not self.password:
                    self.password = getpass.getpass()
                cmd.append('--src-creds=%s:%s' % (self.username, self.password))


            subprocess.check_call(cmd)

            # Get the layers list from the manifest
            mf = open("%s/manifest.json" % tmpDest, "r")
            manifest = json.load(mf)

            # FIXME We suppose the layers are ordered, is this true?
            for layer in manifest['layers']:
                sum_type, sum_value = layer['digest'].split(':')
                layer_file = "%s/%s.tar" % (tmpDest, sum_value)
                print 'layer_file: (%s) %s' % (sum_type, layer_file)

                # Verify the checksum
                if not checksum(layer_file, sum_type, sum_value):
                    raise Exception("Digest not matching: %s" % layer['digest'])

                # untar layer into dest
                subprocess.check_call(["tar", "xf", layer_file, "-C", dest])

        except:
            shutil.rmtree(tmpDest)
            raise

        shutil.rmtree(tmpDest)

