# -*- coding: utf-8 -*-
# Authors: Radostin Stoyanov <rstoyanov1@gmail.com>
#
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
VirtBuilderSource aim is to extract the root file system from VM image
build with virt-builder from template.
"""

import os
import logging
import subprocess
import tempfile

import guestfs
from virtBootstrap import utils


# pylint: disable=invalid-name
# Create logger
logger = logging.getLogger(__name__)


class VirtBuilderSource(object):
    """
    Extract root file system from image build with virt-builder.
    """
    def __init__(self, **kwargs):
        """
        Create container rootfs by building VM from virt-builder template
        and extract the rootfs.

        @param uri: Template name
        @param fmt: Format used to store the output [dir, qcow2]
        @param uid_map: Mappings for UID of files in rootfs
        @param gid_map: Mappings for GID of files in rootfs
        @param root_password: Root password to set in rootfs
        @param progress: Instance of the progress module
        """
        # Parsed URIs:
        # - "virt-builder:///<template>"
        # - "virt-builder://<template>"
        # - "virt-builder:/<template>"
        self.template = kwargs['uri'].netloc or kwargs['uri'].path[1:]
        self.output_format = kwargs.get('fmt', utils.DEFAULT_OUTPUT_FORMAT)
        self.uid_map = kwargs.get('uid_map', [])
        self.gid_map = kwargs.get('gid_map', [])
        self.root_password = kwargs.get('root_password', None)
        self.progress = kwargs['progress'].update_progress

    def build_image(self, output_file):
        """
        Build VM from virt-builder template
        """
        cmd = ['virt-builder', self.template,
               '-o', output_file,
               '--no-network',
               '--delete', '/dev/*',
               '--delete', '/boot/*',
               # Comment out all lines in fstab
               '--edit', '/etc/fstab:s/^/#/']
        if self.root_password is not None:
            cmd += ['--root-password', "password:%s" % self.root_password]
        self.run_builder(cmd)

    def run_builder(self, cmd):
        """
        Execute virt-builder command
        """
        subprocess.check_call(cmd)

    def unpack(self, dest):
        """
        Build image and extract root file system

        @param dest: Directory path where output files will be stored.
        """

        with tempfile.NamedTemporaryFile(prefix='bootstrap_') as tmp_file:
            if self.output_format == 'dir':
                self.progress("Building image", value=0, logger=logger)
                self.build_image(tmp_file.name)
                self.progress("Extracting rootfs", value=50, logger=logger)
                g = guestfs.GuestFS(python_return_dict=True)
                g.add_drive_opts(tmp_file.name, readonly=False, format='raw')
                g.launch()

                # Get the device with file system
                root_dev = g.inspect_os()
                if not root_dev:
                    raise Exception("No file system was found")
                g.mount(root_dev[0], '/')

                # Extract file system to destination directory
                g.copy_out('/', dest)

                g.umount('/')
                g.shutdown()

                self.progress("Extraction completed successfully!",
                              value=100, logger=logger)
                logger.info("Files are stored in: %s", dest)

            elif self.output_format == 'qcow2':
                output_file = os.path.join(dest, 'layer-0.qcow2')

                self.progress("Building image", value=0, logger=logger)
                self.build_image(tmp_file.name)

                self.progress("Extracting rootfs", value=50, logger=logger)
                g = guestfs.GuestFS(python_return_dict=True)
                g.add_drive_opts(tmp_file.name, readonly=True, format='raw')
                # Create qcow2 disk image
                g.disk_create(
                    filename=output_file,
                    format='qcow2',
                    size=os.path.getsize(tmp_file.name)
                )
                g.add_drive_opts(output_file, readonly=False, format='qcow2')
                g.launch()
                # Get the device with file system
                root_dev = g.inspect_os()
                if not root_dev:
                    raise Exception("No file system was found")
                output_dev = g.list_devices()[1]
                # Copy the file system to the new qcow2 disk
                g.copy_device_to_device(root_dev[0], output_dev, sparse=True)
                g.shutdown()

                # UID/GID mapping
                if self.uid_map or self.gid_map:
                    logger.info("Mapping UID/GID")
                    utils.map_id_in_image(1, dest, self.uid_map, self.gid_map)

                self.progress("Extraction completed successfully!", value=100,
                              logger=logger)
                logger.info("Image is stored in: %s", output_file)

            else:
                raise Exception("Unknown format:" + self.output_format)
