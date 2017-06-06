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
import os


# default_image_dir - Path where Docker images (tarballs) will be stored
if os.geteuid() == 0:
    default_image_dir = "/var/lib/virt-bootstrap/docker_images"
else:
    default_image_dir = \
        os.environ['HOME'] + "/.local/share/virt-bootstrap/docker_images"


def checksum(path, sum_type, sum_expected):
    algorithm = getattr(hashlib, sum_type)
    try:
        fd = open(path, 'rb')
        content = fd.read()
        fd.close()

        actual = algorithm(content).hexdigest()
        return actual == sum_expected
    except Exception:
        return False


class FileSource:
    def __init__(self, url, *args):
        self.path = url.path

    def unpack(self, dest):
        # We assume tar is intelligent enough to find out
        # the compression type to use and to strip leading '/',
        # not sure if this is safe enough
        subprocess.check_call(["tar", "xf", self.path, "-C", dest])


class DockerSource:
    def __init__(self, url, username, password, insecure, no_cache):
        self.registry = url.netloc
        self.image = url.path
        self.username = username
        self.password = password
        self.insecure = insecure
        self.no_cache = no_cache
        if self.image and not self.image.startswith('/'):
            self.image = '/' + self.image
        self.url = "docker://" + self.registry + self.image

    def unpack(self, dest):

        if self.no_cache:
            tmp_dest = tempfile.mkdtemp('virt-bootstrap')
            images_dir = tmp_dest
        else:
            if not os.path.exists(default_image_dir):
                os.makedirs(default_image_dir)
            images_dir = default_image_dir

        try:
            # Run skopeo copy into a tmp folder
            # Note: we don't want to expose --src-cert-dir to users as
            #       they should place the certificates in the system
            #       folders for broader enablement
            cmd = ["skopeo", "copy",
                   self.url,
                   "dir:%s" % images_dir]
            if self.insecure:
                cmd.append('--src-tls-verify=false')
            if self.username:
                if not self.password:
                    self.password = getpass.getpass()
                cmd.append('--src-creds=%s:%s' % (self.username,
                                                  self.password))

            subprocess.check_call(cmd)

            # Get the layers list from the manifest
            mf = open("%s/manifest.json" % images_dir, "r")
            manifest = json.load(mf)

            # FIXME We suppose the layers are ordered, is this true?
            for layer in manifest['layers']:
                sum_type, sum_value = layer['digest'].split(':')
                layer_file = "%s/%s.tar" % (images_dir, sum_value)
                print('layer_file: (%s) %s' % (sum_type, layer_file))

                # Verify the checksum
                if not checksum(layer_file, sum_type, sum_value):
                    raise Exception("Digest not matching: " + layer['digest'])

                # untar layer into dest
                subprocess.check_call(["tar", "xf", layer_file, "-C", dest])

        except Exception:
            raise

        finally:
            # Clean up
            if self.no_cache:
                shutil.rmtree(tmp_dest)
