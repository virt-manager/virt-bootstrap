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
import tempfile
import getpass
import os
import logging
from subprocess import call, check_call

# default_image_dir - Path where Docker images (tarballs) will be stored
if os.geteuid() == 0:
    virt_sandbox_connection = "lxc:///"
    default_image_dir = "/var/lib/virt-bootstrap/docker_images"
else:
    virt_sandbox_connection = "qemu:///session"
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


def safe_untar(src, dest):
    # Extract tarball in LXC container for safety
    virt_sandbox = ['virt-sandbox',
                    '-c', virt_sandbox_connection,
                    '-m', 'host-bind:/mnt=' + dest]  # Bind destination folder

    # Compression type is auto detected from tar
    # Exclude files under /dev to avoid "Cannot mknod: Operation not permitted"
    params = ['--', '/bin/tar', 'xf', src, '-C', '/mnt', '--exclude', 'dev/*']
    if call(virt_sandbox + params) != 0:
        logging.error(_('virt-sandbox exit with non-zero code. '
                        'Please check if "libvirtd" is running.'))


class FileSource:
    def __init__(self, url, *args):
        self.path = url.path

    def unpack(self, dest):
        '''
        Safely extract root filesystem from tarball

        @param dest: Directory path where the files to be extraced
        '''
        safe_untar(self.path, dest)


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

            check_call(cmd)

            # Get the layers list from the manifest
            mf = open("%s/manifest.json" % images_dir, "r")
            manifest = json.load(mf)

            # Layers are in order - root layer first
            # Reference:
            # https://github.com/containers/image/blob/master/image/oci.go#L100
            for layer in manifest['layers']:
                sum_type, sum_value = layer['digest'].split(':')
                layer_file = "%s/%s.tar" % (images_dir, sum_value)
                print('layer_file: (%s) %s' % (sum_type, layer_file))

                # Verify the checksum
                if not checksum(layer_file, sum_type, sum_value):
                    raise Exception("Digest not matching: " + layer['digest'])

                # untar layer into dest
                safe_untar(layer_file, dest)

        except Exception:
            raise

        finally:
            # Clean up
            if self.no_cache:
                shutil.rmtree(tmp_dest)
