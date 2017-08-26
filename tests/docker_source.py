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
"""

import unittest

from . import mock
from . import sources


# pylint: disable=invalid-name
class TestDockerSource(unittest.TestCase):
    """
    Unit tests for DockerSource
    """
    ###################################
    # Tests for: retrieve_layers_info()
    ###################################
    def _mock_retrieve_layers_info(self, manifest, kwargs):
        """
        This method is gather common test pattern used in the following
        two test cases which aim to return an instance of the class
        DockerSource with some util functions being mocked.
        """
        with mock.patch.multiple('virtBootstrap.utils',
                                 get_image_details=mock.DEFAULT,
                                 get_image_dir=mock.DEFAULT) as m_utils:

            m_utils['get_image_details'].return_value = manifest
            m_utils['get_image_dir'].return_value = '/images_path'

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

        manifest = {'schemaVersion': 2, 'layers': []}
        (src_instance,
         m_uri, m_utils) = self._mock_retrieve_layers_info(manifest,
                                                           src_kwargs)

        kwargs = {
            'insecure': src_instance.insecure,
            'username': src_instance.username,
            'password': src_instance.password,
            'raw': True
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
            'schemaVersion': 1,
            'fsLayers': [
                {'blobSum': 'sha256:75c416ea'},
                {'blobSum': 'sha256:c6ff40b6'},
                {'blobSum': 'sha256:a7050fc1'}
            ]
        }

        expected_result = [
            ['sha256', 'a7050fc1', '/images_path/a7050fc1.tar', None],
            ['sha256', 'c6ff40b6', '/images_path/c6ff40b6.tar', None],
            ['sha256', '75c416ea', '/images_path/75c416ea.tar', None]
        ]

        with mock.patch('os.path.getsize') as m_getsize:
            m_getsize.return_value = None
            src_instance = self._mock_retrieve_layers_info(manifest, kwargs)[0]
        self.assertEqual(src_instance.layers, expected_result)

    def test_retrieve_layers_info_schema_version_2(self):
        """
        Ensures that retrieve_layers_info() extracts the layers' information
        from manifest with schema version 2 a list with format:
            ["digest", "sum_type", "file_path", "size"].
        """
        kwargs = {
            'uri': '',
            'progress': mock.Mock()
        }

        manifest = {
            'schemaVersion': 2,
            "layers": [
                {"size": 47103294, "digest": "sha256:75c416ea"},
                {"size": 814, "digest": "sha256:c6ff40b6"},
                {"size": 513, "digest": "sha256:a7050fc1"}
            ]
        }

        expected_result = [
            ['sha256', '75c416ea', '/images_path/75c416ea.tar', 47103294],
            ['sha256', 'c6ff40b6', '/images_path/c6ff40b6.tar', 814],
            ['sha256', 'a7050fc1', '/images_path/a7050fc1.tar', 513]
        ]

        src_instance = self._mock_retrieve_layers_info(manifest, kwargs)[0]
        self.assertEqual(src_instance.layers, expected_result)

    def test_retrieve_layers_info_raise_error_on_invalid_schema_version(self):
        """
        Ensures that retrieve_layers_info() calls get_image_details()
        with all passed arguments.
        """
        kwargs = {
            'uri': '',
            'progress': mock.Mock()
        }

        manifest = {'schemaVersion': 3}
        with self.assertRaises(ValueError):
            self._mock_retrieve_layers_info(manifest, kwargs)
