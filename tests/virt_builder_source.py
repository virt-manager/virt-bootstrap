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
Tests which aim to exercise the extraction of root file system from disk image
created with virt-builder.

Brief description of these tests:
1. Create dummy root file system on raw disk image.
2. Create index file of local repository for virt-builder.
3. Call bootstrap() with modified virt-builder commnad to use local repository
   as source.
4. Check the result.
"""

import copy
import platform
import os
import shutil
import tempfile
import unittest
import subprocess

import guestfs

from . import virt_bootstrap
from . import mock
from . import DEFAULT_FILE_MODE
from . import ROOTFS_TREE
from . import Qcow2ImageAccessor
from . import NOT_ROOT


# pylint: disable=invalid-name, too-many-instance-attributes
class TestVirtBuilderSource(Qcow2ImageAccessor):
    """
    Test cases for virt-builder source.
    """

    def create_local_repository(self):
        """
        Create raw disk image with dummy root file system and index file which
        contains the metadata used by virt-builder.
        """
        g = guestfs.GuestFS(python_return_dict=True)
        g.disk_create(
            self.image['path'],
            format=self.image['format'],
            size=self.image['size']
        )
        g.add_drive(
            self.image['path'],
            readonly=False,
            format=self.image['format']
        )
        g.launch()
        g.mkfs('ext2', '/dev/sda')
        g.mount('/dev/sda', '/')
        for user in self.rootfs_tree:
            usr_uid = self.rootfs_tree[user]['uid']
            usr_gid = self.rootfs_tree[user]['gid']

            for member in self.rootfs_tree[user]['dirs']:
                dir_name = '/' + member
                g.mkdir_p(dir_name)
                g.chown(usr_uid, usr_gid, dir_name)

            for member in self.rootfs_tree[user]['files']:
                if isinstance(member, tuple):
                    m_name, m_permissions, m_data = member
                    file_name = '/' + m_name
                    g.write(file_name, m_data)
                    g.chmod(m_permissions & 0o777, file_name)
                else:
                    file_name = '/' + member
                    g.touch(file_name)
                    g.chmod(DEFAULT_FILE_MODE & 0o777, file_name)

                g.chown(usr_uid, usr_gid, file_name)

        # Create index file
        with open(self.repo_index, 'w') as index_file:
            index_file.write(
                '[{template}]\n'
                'name=Test\n'
                'arch={arch}\n'
                'file={filename}\n'  # Relative (not real) path must be used.
                'format={format}\n'
                'expand=/dev/sda\n'
                'size={size}\n'.format(**self.image)
                # The new line at the end of the index file is required.
                # Otherwise, virt-builder will return "syntax error".
            )

    def setUp(self):
        self.rootfs_tree = copy.deepcopy(ROOTFS_TREE)

        self.fmt = None
        self.uid_map = None
        self.gid_map = None
        self.root_password = None
        self.checked_members = set()

        self.dest_dir = tempfile.mkdtemp('_bootstrap_dest')
        self.repo_dir = tempfile.mkdtemp('_local_builder_repo')
        # Set permissions for tmp directories to avoid
        # "Permission denied" errors from Libvirt.
        os.chmod(self.repo_dir, 0o755)
        os.chmod(self.dest_dir, 0o755)
        self.repo_index = os.path.join(self.repo_dir, 'index')

        self.image = {
            'template': 'test',
            'filename': 'test.img',
            'path': os.path.join(self.repo_dir, 'test.img'),
            'format': 'raw',
            'size': (1 * 1024 * 1024),
            'arch': platform.processor(),
        }
        self.create_local_repository()

    def mocked_run_builder(self, cmd):
        """
        Modify the virt-builder command to use the dummy disk image
        and capture the 'stdout'.
        """
        subprocess.check_call(
            cmd + [
                '--source',
                'file://%s' % self.repo_index,
                '--no-check-signature',
                '--no-cache'
            ],
            stdout=subprocess.PIPE
        )

    def tearDown(self):
        """
        Clean up
        """
        shutil.rmtree(self.repo_dir)
        shutil.rmtree(self.dest_dir)

    def call_bootstrap(self):
        """
        Mock out run_builder() with mocked_run_builder() and
        call bootstrap() method from virtBootstrap.
        """
        # By default virt-builder sets random root password which leads to
        # modification in /etc/shadow file. If we don't test this we simplify
        # the test by not adding shadow file in our dummy root file system.
        if not self.root_password:
            self.rootfs_tree['root']['files'] = ['etc/hosts', 'etc/fstab']

        target = ('virtBootstrap.sources.VirtBuilderSource.run_builder')
        with mock.patch(target) as m_run_builder:
            m_run_builder.side_effect = self.mocked_run_builder

            virt_bootstrap.bootstrap(
                progress_cb=mock.Mock(),
                uri='virt-builder://%s' % self.image['template'],
                dest=self.dest_dir,
                fmt=self.fmt,
                gid_map=self.gid_map,
                uid_map=self.uid_map,
                root_password=self.root_password
            )

    def test_dir_extract_rootfs(self):
        """
        Ensures that the root file system is extracted correctly.
        """
        self.fmt = 'dir'
        self.call_bootstrap()
        self.check_rootfs(skip_ownership=NOT_ROOT)

    @unittest.skipIf(NOT_ROOT, "Root privileges required")
    def test_dir_ownership_mapping(self):
        """
        Ensures that UID/GID mapping is applied to extracted root file system.
        """
        self.fmt = 'dir'
        self.gid_map = [[1000, 2000, 10], [0, 1000, 10], [500, 500, 10]]
        self.uid_map = [[1000, 2000, 10], [0, 1000, 10], [500, 500, 10]]
        self.call_bootstrap()
        self.apply_mapping()
        self.check_rootfs()

    def test_dir_setting_root_password(self):
        """
        Ensures that password for root is set correctly.
        """
        self.root_password = 'my secret root password'
        self.fmt = 'dir'
        self.call_bootstrap()
        self.validate_shadow_file()

    def test_qcow2_build_image(self):
        """
        Ensures that the root file system is copied correctly within single
        partition qcow2 image.
        """
        self.fmt = 'qcow2'
        self.call_bootstrap()
        self.check_qcow2_images(self.get_image_path())

    def test_qcow2_ownership_mapping(self):
        """
        Ensures that UID/GID mapping is applied in qcow2 image "layer-1.qcow2".
        """
        self.fmt = 'qcow2'
        self.gid_map = [[1000, 2000, 10], [0, 1000, 10], [500, 500, 10]]
        self.uid_map = [[1000, 2000, 10], [0, 1000, 10], [500, 500, 10]]
        self.call_bootstrap()
        self.apply_mapping()
        self.check_qcow2_images(self.get_image_path(1))

    def test_qcow2_setting_root_password(self):
        """
        Ensures that the root password is set in the shadow file of
        "layer-1.qcow2"
        """
        self.fmt = 'qcow2'
        self.root_password = "My secret password"
        self.call_bootstrap()
        self.check_image = self.validate_shadow_file_in_image
        self.check_qcow2_images(self.get_image_path())
