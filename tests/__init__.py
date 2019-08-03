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
Test suite for virt-bootstrap
"""

import copy
import hashlib
import io
import os
import shutil
import sys
import tarfile
import tempfile
import unittest
import passlib.hosts

import guestfs

try:
    import mock
except ImportError:
    import unittest.mock as mock

sys.path.insert(0, '../src')  # noqa: E402

# pylint: disable=import-error, wrong-import-position
from virtBootstrap import virt_bootstrap
from virtBootstrap import sources
from virtBootstrap import progress
from virtBootstrap import utils

__all__ = ['virt_bootstrap', 'sources', 'progress', 'utils']


DEFAULT_FILE_MODE = 0o755
SHADOW_FILE_MODE = 0o600
NOT_ROOT = (os.geteuid() != 0)

ROOTFS_TREE = {
    'root': {
        'uid': 0,
        'gid': 0,
        'dirs': [
            'bin', 'etc', 'home', 'lib', 'opt', 'root', 'run', 'sbin',
            'srv', 'tmp', 'usr', 'var'
        ],
        'files': [
            'etc/hosts',
            'etc/fstab',
            (
                'etc/shadow',
                SHADOW_FILE_MODE,
                'root:*::0:99999:7:::'
            )
        ]
    },
    'user1': {
        'uid': 500,
        'gid': 500,
        'dirs': ['home/user1'],
        'files': [
            ('home/user1/test_file', 0o644, 'test data')
        ]
    },

    'user2': {
        'uid': 1000,
        'gid': 1000,
        'dirs': [
            'home/user2',
            'home/user2/test_dir'
        ],
        'files': [
            'home/user2/test_dir/test_file'
        ]
    }
}


# pylint: disable=invalid-name,too-many-arguments
class BuildTarFiles(object):
    """
    Create dummy tar files used for testing.
    """

    def __init__(self, tar_dir, rootfs_tree=None):
        """
        Create dummy tar files
        """
        self.tar_dir = tar_dir
        self.rootfs_tree = rootfs_tree or copy.deepcopy(ROOTFS_TREE)

    def create_tar_file(self):
        """
        Use temporary name to create uncompressed tarball with dummy file
        system. Get checksum of the content and rename the file to
        "<checksum>.tar". In this way, we can easily generate manifest for
        Docker image and provide it to virt-bootstrap.
        """
        filepath = tempfile.mkstemp(dir=self.tar_dir)[1]
        with tarfile.open(filepath, 'w') as tar:
            self.create_user_dirs(tar)
        # Get sha256 checksum of the archive
        with open(filepath, 'rb') as file_handle:
            file_hash = hashlib.sha256(file_handle.read()).hexdigest()
        # Rename the archive to <checksum>.tar
        new_filepath = os.path.join(self.tar_dir, "%s.tar" % file_hash)
        os.rename(filepath, new_filepath)
        os.chmod(new_filepath, 0o644)
        return new_filepath

    def create_user_dirs(self, tar_handle):
        """
        Create root file system tree in tar archive.
        """
        tar_members = [
            ['dirs', tarfile.DIRTYPE],
            ['files', tarfile.REGTYPE],
        ]

        for user in self.rootfs_tree:
            for members, tar_type in tar_members:
                self.create_tar_members(
                    tar_handle,
                    self.rootfs_tree[user][members],
                    tar_type,
                    uid=self.rootfs_tree[user]['uid'],
                    gid=self.rootfs_tree[user]['gid']
                )

    def create_tar_members(self, tar_handle, members, m_type, uid=0, gid=0):
        """
        Add members to tar file.
        """
        for member_name in members:
            member_data = ''
            permissions = DEFAULT_FILE_MODE
            if isinstance(member_name, tuple):
                if len(member_name) == 3:
                    member_data = member_name[2]
                member_name, permissions = member_name[:2]
            data_encoded = member_data.encode('utf-8')

            t_info = tarfile.TarInfo(member_name)
            t_info.type = m_type
            t_info.mode = permissions
            t_info.uid = uid
            t_info.gid = gid
            t_info.size = len(data_encoded)

            tar_handle.addfile(t_info, io.BytesIO(data_encoded))


class ImageAccessor(unittest.TestCase):
    """
    The purpose of this class is to gather methods used to verify content
    of extracted root file system. This class can be exteded for different
    test cases.
    """
    def setUp(self):
        """
        Set initial values, create temporary directories and tar archive which
        contains dummy root file system.
        """
        self.dest_dir = tempfile.mkdtemp('_bootstrap_dest')
        self.tar_dir = tempfile.mkdtemp('_bootstrap_tarfiles')
        # Set permissions of temporary directories to avoid "Permission denied"
        # error from Libvirt.
        os.chmod(self.dest_dir, 0o755)
        os.chmod(self.tar_dir, 0o755)
        self.uid_map = []
        self.gid_map = []
        self.root_password = None
        self.checked_members = set()
        self.rootfs_tree = copy.deepcopy(ROOTFS_TREE)
        # Create tar archive
        self.tar_file = BuildTarFiles(self.tar_dir).create_tar_file()

    def tearDown(self):
        """
        Clean up.
        """
        shutil.rmtree(self.dest_dir)
        shutil.rmtree(self.tar_dir)

    def apply_mapping(self):
        """
        This method applies UID/GID mapping to all users defined in
        self.rootfs_tree.
        """

        for user in self.rootfs_tree:
            user_uid = self.rootfs_tree[user]['uid']
            user_gid = self.rootfs_tree[user]['gid']

            if self.uid_map:
                for start, target, count in self.uid_map:
                    if user_uid >= start and user_uid <= start + count:
                        diff = user_uid - start
                        self.rootfs_tree[user]['uid'] = target + diff

            if self.gid_map:
                for start, target, count in self.gid_map:
                    if user_gid >= start and user_gid <= start + count:
                        diff = user_gid - start
                        self.rootfs_tree[user]['gid'] = target + diff

    def check_rootfs(self, skip_ownership=False):
        """
        Check if the root file system was extracted correctly.
        """
        existence_check_func = {
            'files': os.path.isfile,
            'dirs': os.path.isdir
        }
        for user in self.rootfs_tree:
            for m_type in existence_check_func:
                self.check_rootfs_members(
                    user,
                    m_type,
                    existence_check_func[m_type],
                    skip_ownership
                )

    def check_rootfs_members(self, user, members, check_existence,
                             skip_ownership=False):
        """
        Verify permissions, ownership and content of files or
        directories in extracted root file system.

        @param user: user name defined in self.rootfs_tree.
        @param members: The string 'dirs' or 'files'.
        @param check_existence: Function used to check the existence of member.
        @param skip_ownership: Boolean whether to skip ownership check.
        """
        user_uid = self.rootfs_tree[user]['uid']
        user_gid = self.rootfs_tree[user]['gid']

        for member_name in self.rootfs_tree[user][members]:
            member_data = ''
            # Unpack member if tuple. Allow to be specified permissions and
            # data for each file.
            permissions = DEFAULT_FILE_MODE
            if isinstance(member_name, tuple):
                if len(member_name) == 3:
                    member_data = member_name[2]
                member_name, permissions = member_name[:2]

            # Skip already checked members. E.g. when multiple layers were
            # extracted we want to check only the latest version of file.
            if member_name in self.checked_members:
                continue
            else:
                self.checked_members.add(member_name)

            #########################
            # Assertion functions
            #########################
            member_path = os.path.join(self.dest_dir, member_name)
            self.assertTrue(
                check_existence(member_path),
                'Member was not extracted: %s' % member_path
            )
            stat = os.stat(member_path)

            self.validate_file_mode(member_path, stat.st_mode, permissions)

            if not skip_ownership:
                self.validate_file_ownership(
                    member_path, stat.st_uid, stat.st_gid, user_uid, user_gid
                )

            if member_data:
                with open(member_path, 'r') as content:
                    file_content = content.read()

                self.assertEqual(
                    member_data, file_content,
                    'Incorrect file content: %s\n'
                    'Found: %s\n'
                    'Expected: %s' % (member_path, file_content, member_data)
                )

    def validate_shadow_file(self):
        """
        Ensure that the extracted /etc/shadow file has correct ownership,
        permissions and contains valid hash of the root password.
        """
        shadow_path = os.path.join(self.dest_dir, 'etc/shadow')

        self.assertTrue(
            os.path.isfile(shadow_path),
            'Does not exist: %s' % shadow_path
        )
        stat = os.stat(shadow_path)

        self.validate_file_mode(shadow_path, stat.st_mode, SHADOW_FILE_MODE)

        if not NOT_ROOT:
            self.validate_file_ownership(
                shadow_path,
                stat.st_uid, stat.st_gid,
                self.rootfs_tree['root']['uid'],
                self.rootfs_tree['root']['gid']
            )

        with open(shadow_path, 'r') as content:
            shadow_content = content.readlines()
        if not shadow_content:
            raise Exception("File is empty: %s" % shadow_path)
        self.validate_shadow_hash(shadow_content)

    def validate_shadow_hash(self, shadow_content):
        """
        Validate root password hash of shadow file.

        Note: For simplicity we assume that the first line of /etc/shadow
        contains the root entry.
        """

        if self.root_password.startswith('file:'):
            with open(self.root_password[len('file:'):]) as pwdfile:
                self.root_password = pwdfile.readline().rstrip("\n\r")

        self.assertTrue(
            passlib.hosts.linux_context.verify(
                self.root_password,
                shadow_content[0].split(':')[1]
            ),
            "Invalid root password hash."
        )

    def validate_file_mode(self, member_name, mode, expected):
        """
        Verify permissions of rootfs member.
        """
        self.assertEqual(
            mode & 0o777, expected, 'Incorrect permissions: %s' % member_name
        )

    def validate_file_ownership(self, member_name, uid, gid,
                                expected_uid, expected_gid):
        """
        Validate UID/GID of rootfs member.
        """
        self.assertEqual(
            uid, expected_uid,
            "Incorrect UID: %s\n"
            "Found: %s\n"
            "Expected: %s" % (member_name, uid, expected_uid)
        )
        self.assertEqual(
            gid, expected_gid,
            "Incorrect GID: %s\n"
            "Found: %s\n"
            "Expected: %s" % (member_name, gid, expected_gid,)
        )


class Qcow2ImageAccessor(ImageAccessor):
    """
    This class gathers methods for verification of root file system content
    within extracted qcow2 image.
    """

    def validate_shadow_file_in_image(self, g):
        """
        Ensures that /etc/shadow file of disk image has correct permission,
        ownership and contains valid hash of the root password.
        """
        self.assertTrue(
            g.is_file('/etc/shadow'),
            "Shadow file does not exist"
        )

        stat = g.stat('/etc/shadow')

        self.validate_file_mode('/etc/shadow', stat['mode'], SHADOW_FILE_MODE)

        self.validate_file_ownership(
            '/etc/shadow',
            stat['uid'], stat['gid'],
            self.rootfs_tree['root']['uid'],
            self.rootfs_tree['root']['gid']
        )

        self.validate_shadow_hash(g.cat('/etc/shadow').split('\n'))

    def check_image_content(self, g, user, members, check_existence):
        """
        Verify the existence, permissions and ownership of members in qcow2
        image.

        @param g: guestfs handle
        @param user: Name of user defined in self.rootfs_tree
        @param members: The string 'dirs' or 'files'.
        @param check_existence: Function to confirm existence of member.
        """
        permissions = DEFAULT_FILE_MODE
        user_uid = self.rootfs_tree[user]['uid']
        user_gid = self.rootfs_tree[user]['gid']

        for member_name in self.rootfs_tree[user][members]:
            # Get specified permissions of file.
            if isinstance(member_name, tuple):
                member_name, permissions = member_name[:2]

            # Skip already checked files.
            if member_name in self.checked_members:
                continue
            else:
                self.checked_members.add(member_name)

            # When using guestfs all names should start with '/'
            if not member_name.startswith('/'):
                member_name = '/' + member_name

            self.assertTrue(
                check_existence(member_name),
                "Member was not found: %s" % member_name
            )
            stat = g.stat(member_name)

            self.validate_file_mode(member_name, stat['mode'], permissions)

            self.validate_file_ownership(
                member_name, stat['uid'], stat['gid'], user_uid, user_gid
            )

    def check_image(self, g):
        """
        Check the presence of files and folders in qcow2 image.
        """
        for user in self.rootfs_tree:
            self.check_image_content(g, user, 'dirs', g.is_dir)
            self.check_image_content(g, user, 'files', g.is_file)

    def check_qcow2_image(self, image_path):
        """
        Ensures that qcow2 images contain all files.
        """
        g = guestfs.GuestFS(python_return_dict=True)
        g.add_drive_opts(image_path, readonly=True)
        g.launch()
        g.mount('/dev/sda', '/')
        self.check_image(g)
        g.umount('/')
        g.shutdown()

    def get_image_path(self, n=0):
        """
        Returns the path of stored qcow2 image.
        """
        return os.path.join(self.dest_dir, "layer-%d.qcow2" % n)

    def check_qcow2_images(self, image_path):
        """
        Ensures that qcow2 images contain all files.
        """
        g = guestfs.GuestFS(python_return_dict=True)
        g.add_drive_opts(image_path, readonly=True)
        g.launch()
        g.mount('/dev/sda', '/')
        self.check_image(g)
        g.umount('/')
        g.shutdown()
