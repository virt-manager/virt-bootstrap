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
Tests which aim is to exercise creation of root file system with DockerSource.

To avoid fetching network resources we mock out the functions:
- utils.get_image_details(): Returns manifest content
- utils.get_image_dir(): Returns the directory which contains the tar files

Description:
1. Create dummy image layers (tar files).
2. Generate manifest content.
3. Mock out get_image_details() and get_image_dir().
4. Call bootstrap().
5. Check the result.
"""

import copy
import os
import subprocess
import unittest
import guestfs

from . import mock
from . import sources
from . import virt_bootstrap
from . import BuildTarFiles
from . import ImageAccessor
from . import Qcow2ImageAccessor
from . import NOT_ROOT


# pylint: disable=invalid-name
class CreateLayers(object):
    """
    Create tar files to mimic image layers and generate manifest content.
    """
    def __init__(self, initial_tar_file, initial_rootfs_tree, dest_dir):
        """
        Create dummy tar files used as image layers.

        The variables:
        - layers: Store a lists of paths to created archives.
        - layers_rootfs: Store self.rootfs_tree value used to generate tarball.
        """
        self.layers = [initial_tar_file]
        self.layers_rootfs = [copy.deepcopy(initial_rootfs_tree)]

        tar_builder = BuildTarFiles(dest_dir)
        tar_builder.rootfs_tree['root']['dirs'] = []
        tar_builder.rootfs_tree['root']['files'] = [
            ('etc/foo/bar', 0o644, "This should be overwritten")
        ]

        self.layers.append(tar_builder.create_tar_file())
        self.layers_rootfs.append(copy.deepcopy(tar_builder.rootfs_tree))

        tar_builder.rootfs_tree['root']['files'] = [
            ('etc/foo/bar', 0o644, "Content of etc/foo/bar"),
            ('bin/foobar', 0o755, "My executable script")
        ]
        self.layers.append(tar_builder.create_tar_file())
        self.layers_rootfs.append(copy.deepcopy(tar_builder.rootfs_tree))

    def get_layers_rootfs(self):
        """
        Return root file systems used to create layers.
        """
        return self.layers_rootfs

    def generate_manifest(self):
        """
        Generate Manifest content for layers.
        """
        return {
            "schemaVersion": 2,
            "Layers": [
                "sha256:" + os.path.basename(layer).split('.')[0]
                for layer in self.layers
            ]
        }


class TestDirDockerSource(ImageAccessor):
    """
    Ensures that all layers extracted correctly in destination folder.
    """

    def call_bootstrap(self, manifest):
        """
        Mock get_image_details() and get_image_dir() and call the function
        virt_bootstrap.bootstrap() with root_password value.
        """
        with mock.patch.multiple('virtBootstrap.utils',
                                 get_image_details=mock.DEFAULT,
                                 get_image_dir=mock.DEFAULT) as mocked:

            mocked['get_image_details'].return_value = manifest
            mocked['get_image_dir'].return_value = self.tar_dir

            virt_bootstrap.bootstrap(
                progress_cb=mock.Mock(),
                uri='docker://foo',
                fmt='dir',
                uid_map=self.uid_map,
                gid_map=self.gid_map,
                dest=self.dest_dir,
                root_password=self.root_password
            )

    def test_dir_extract_rootfs(self):
        """
        Ensures that all layers were extracted correctly.
        """
        layers = CreateLayers(self.tar_file, self.rootfs_tree, self.tar_dir)
        self.call_bootstrap(layers.generate_manifest())
        layers_rootfs = layers.get_layers_rootfs()
        for rootfs_tree in layers_rootfs[::-1]:
            self.rootfs_tree = rootfs_tree
            self.check_rootfs(skip_ownership=(os.geteuid != 0))

    @unittest.skipIf(NOT_ROOT, "Root privileges required")
    def test_dir_ownership_mapping(self):
        """
        Ensures that the UID/GID mapping was applied correctly to extracted
        root file system of all layers.
        """
        self.uid_map = [[1000, 2000, 10], [0, 1000, 10], [500, 500, 10]]
        self.gid_map = [[1000, 2000, 10], [0, 1000, 10], [500, 500, 10]]
        layers = CreateLayers(self.tar_file, self.rootfs_tree, self.tar_dir)
        self.call_bootstrap(layers.generate_manifest())
        layers_rootfs = layers.get_layers_rootfs()
        for rootfs_tree in layers_rootfs[::-1]:
            self.rootfs_tree = rootfs_tree
            self.apply_mapping()
            self.check_rootfs()

    def test_dir_setting_root_password(self):
        """
        Ensures that the root password is set correctly.
        """
        layers = CreateLayers(self.tar_file, self.rootfs_tree, self.tar_dir)
        self.root_password = "My secret root password"
        self.call_bootstrap(layers.generate_manifest())
        self.validate_shadow_file()


class TestQcow2DockerSource(Qcow2ImageAccessor):
    """
    Ensures that the conversion of tar files to qcow2 image with backing chains
    works as expected.
    """
    def get_image_info(self, image_path):
        """
        Wrapper around "qemu-img info" used to information about disk image.
        """
        cmd = ['qemu-img', 'info', image_path]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        output, _ignore = proc.communicate()
        return output.decode('utf-8').split('\n')

    def call_bootstrap(self):
        """
        Generate tar files which mimic container layers and manifest content.
        Mock get_image_details() and get_image_dir() and call the function
        virt_bootstrap.bootstrap() for qcow2 format.
        Return the root file systems used to generate the tar archives.
        """
        layers = CreateLayers(self.tar_file, self.rootfs_tree, self.tar_dir)
        manifest = layers.generate_manifest()

        with mock.patch.multiple('virtBootstrap.utils',
                                 get_image_details=mock.DEFAULT,
                                 get_image_dir=mock.DEFAULT) as mocked:

            mocked['get_image_details'].return_value = manifest
            mocked['get_image_dir'].return_value = self.tar_dir

            virt_bootstrap.bootstrap(
                progress_cb=mock.Mock(),
                uri='docker://foobar',
                dest=self.dest_dir,
                fmt='qcow2',
                uid_map=self.uid_map,
                gid_map=self.gid_map,
                root_password=self.root_password
            )

        return layers.get_layers_rootfs()

    def test_qcow2_build_image(self):
        """
        Ensures that the root file system is copied correctly to single
        partition qcow2 image and layers are converted correctly to qcow2
        images.
        """
        layers_rootfs = self.call_bootstrap()

        ###################
        # Check base layer
        ###################
        base_layer_path = self.get_image_path()
        img_format = self.get_image_info(base_layer_path)[1]
        self.assertEqual(img_format, 'file format: qcow2')
        images = [base_layer_path]
        ###########################
        # Check backing chains
        ###########################
        for i in range(1, len(layers_rootfs)):
            img_path = self.get_image_path(i)
            # img_info contains the output of "qemu-img info"
            img_info = self.get_image_info(img_path)
            self.assertEqual(
                img_info[1],
                'file format: qcow2',
                'Invalid qcow2 disk image: %s' % img_path
            )
            backing_file = self.get_image_path(i - 1)
            self.assertEqual(
                img_info[5],
                'backing file: %s' % backing_file,
                "Incorrect backing file for: %s\n"
                "Expected: %s\n"
                "Found: %s" % (img_info, backing_file, img_info[5])
            )
            images.append(img_path)
        ###############################
        # Check extracted files/folders
        ###############################
        g = guestfs.GuestFS(python_return_dict=True)
        for path in images:
            g.add_drive_opts(path, readonly=True)
        g.launch()
        devices = g.list_filesystems()
        for dev, rootfs in zip(sorted(devices), layers_rootfs):
            self.rootfs_tree = rootfs
            g.mount(dev, '/')
            self.check_image(g)
            g.umount('/')
        g.shutdown()

    def test_qcow2_ownership_mapping(self):
        """
        Ensures that UID/GID mapping works correctly for qcow2 conversion.
        """
        self.uid_map = [[1000, 2000, 10], [0, 1000, 10], [500, 500, 10]]
        self.gid_map = [[1000, 2000, 10], [0, 1000, 10], [500, 500, 10]]
        layers_rootfs = self.call_bootstrap()

        g = guestfs.GuestFS(python_return_dict=True)
        g.add_drive_opts(
            self.get_image_path(len(layers_rootfs)),
            readonly=True
        )

        g.launch()
        for rootfs in layers_rootfs[::-1]:
            self.rootfs_tree = rootfs
            self.apply_mapping()
            g.mount('/dev/sda', '/')
            self.check_image(g)
            g.umount('/')
        g.shutdown()

    def test_qcow2_setting_root_password(self):
        """
        Ensures that the root password is set in the last qcow2 image.
        """
        self.root_password = "My secret password"
        layers_rootfs = self.call_bootstrap()

        g = guestfs.GuestFS(python_return_dict=True)
        g.add_drive_opts(
            self.get_image_path(len(layers_rootfs)),
            readonly=True
        )
        g.launch()
        g.mount('/dev/sda', '/')
        self.validate_shadow_file_in_image(g)
        g.umount('/')
        g.shutdown()


class TestDockerSource(unittest.TestCase):
    """
    Unit tests for DockerSource
    """
    ###################################
    # Tests for: retrieve_layers_info()
    ###################################
    def _mock_retrieve_layers_info(self, manifest, kwargs):
        """
        This method is gather common test pattern used in the following cases
        which aim is to return an instance of the class DockerSource with
        get_image_details() and get_image_dir() being mocked.
        """
        with mock.patch.multiple('virtBootstrap.utils',
                                 get_image_details=mock.DEFAULT,
                                 is_installed=mock.DEFAULT,
                                 get_image_dir=mock.DEFAULT) as m_utils:

            m_utils['get_image_details'].return_value = manifest
            m_utils['get_image_dir'].return_value = '/images_path'
            m_utils['is_installed'].return_value = True

            patch_method = 'virtBootstrap.sources.DockerSource.gen_valid_uri'
            with mock.patch(patch_method) as m_uri:
                src_instance = sources.DockerSource(**kwargs)
        return (src_instance, m_uri, m_utils)

    def test_retrieve_layers_info_pass_arguments_to_get_image_details(self):
        """
        Ensures that retrieve_layers_info() calls get_image_details()
        with all passed arguments.
        """
        src_kwargs = {
            'uri': '',
            'progress': mock.Mock()
        }

        manifest = {'schemaVersion': 2, 'Layers': ['sha256:a7050fc1']}

        with mock.patch('os.path.isfile') as m_isfile:
            m_isfile.return_value = True
            result = self._mock_retrieve_layers_info(manifest, src_kwargs)

        src_instance, m_uri, m_utils = result

        kwargs = {
            'insecure': src_instance.insecure,
            'username': src_instance.username,
            'password': src_instance.password,
            'raw': False
        }
        m_utils['get_image_details'].assert_called_once_with(m_uri(), **kwargs)

    def test_retrieve_layers_info_schema_version_1(self):
        """
        Ensures that retrieve_layers_info() extracts the layers' information
        from manifest with schema version 1 a list with format:
            ["digest", "sum_type", "file_path", "size"].
        """
        kwargs = {
            'uri': '',
            'progress': mock.Mock()
        }

        manifest = {
            'schemaVersion': 2,
            'Layers': [
                'sha256:a7050fc1',
                'sha256:c6ff40b6',
                'sha256:75c416ea'
            ]
        }

        expected_result = [
            ['/images_path/a7050fc1.tar', None],
            ['/images_path/c6ff40b6.tar', None],
            ['/images_path/75c416ea.tar', None]
        ]

        with mock.patch('os.path.getsize') as m_getsize, \
                mock.patch('os.path.isfile') as m_isfile:
            m_getsize.return_value = None
            m_isfile.side_effect = lambda x: x.endswith(".tar")
            src_instance = self._mock_retrieve_layers_info(manifest, kwargs)[0]
        self.assertEqual(src_instance.layers, expected_result)
