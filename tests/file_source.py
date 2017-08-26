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
Regression tests which aim to exercise the creation of root file system
with FileSource.
"""

import unittest

from . import mock
from . import virt_bootstrap
from . import ImageAccessor
from . import Qcow2ImageAccessor
from . import NOT_ROOT


# pylint: disable=invalid-name
class TestDirFileSource(ImageAccessor):
    """
    Ensures that files from rootfs tarball are extracted correctly.
    """
    def call_bootstrap(self):
        """
        Execute the bootstrap() method of virt_bootstrap.
        """
        virt_bootstrap.bootstrap(
            uri=self.tar_file,
            dest=self.dest_dir,
            fmt='dir',
            progress_cb=mock.Mock(),
            uid_map=self.uid_map,
            gid_map=self.gid_map,
            root_password=self.root_password
        )

    def test_dir_extract_rootfs(self):
        """
        Extract rootfs from each dummy tarfile.
        """
        self.call_bootstrap()
        self.check_rootfs(skip_ownership=NOT_ROOT)

    @unittest.skipIf(NOT_ROOT, "Root privileges required")
    def test_dir_ownership_mapping(self):
        """
        Ensures that UID/GID mapping for extracted root file system are applied
        correctly.
        """
        self.uid_map = [[1000, 2000, 10], [0, 1000, 10], [500, 500, 10]]
        self.gid_map = [[1000, 2000, 10], [0, 1000, 10], [500, 500, 10]]
        self.call_bootstrap()
        self.apply_mapping()
        self.check_rootfs()

    def test_dir_setting_root_password(self):
        """
        Ensures that the root password is set correctly when FileSource is used
        with fmt='dir'.
        """
        self.root_password = 'my secret root password'
        self.call_bootstrap()
        self.validate_shadow_file()


class TestQcow2FileSource(Qcow2ImageAccessor):
    """
    Test cases for the class FileSource used with qcow2 output format.
    """

    def call_bootstrap(self):
        """
        Execute the bootstrap method from virtBootstrap.
        """
        virt_bootstrap.bootstrap(
            uri=self.tar_file,
            dest=self.dest_dir,
            fmt='qcow2',
            progress_cb=mock.Mock(),
            uid_map=self.uid_map,
            gid_map=self.gid_map,
            root_password=self.root_password
        )

    def test_qcow2_extract_rootfs(self):
        """
        Ensures root file system of tar archive is converted to single
        partition qcow2 image.
        """
        self.call_bootstrap()
        self.check_qcow2_images(self.get_image_path())

    def test_qcow2_ownership_mapping(self):
        """
        Ensures that UID/GID mapping works correctly for qcow2 conversion.
        """
        self.uid_map = [[1000, 2000, 10], [0, 1000, 10], [500, 500, 10]]
        self.gid_map = [[1000, 2000, 10], [0, 1000, 10], [500, 500, 10]]
        self.call_bootstrap()
        self.apply_mapping()
        self.check_qcow2_images(self.get_image_path(1))
