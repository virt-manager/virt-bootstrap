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
Unit tests for methods defined in virtBootstrap.sources.DockerSource
"""

from tests import unittest
from tests import mock
from tests import sources

try:
    from urlparse import urlparse
except ImportError:
    from urllib.parse import urlparse


# pylint: disable=invalid-name
# pylint: disable=too-many-public-methods
class TestDockerSource(unittest.TestCase):
    """
    Test cases for DockerSource
    """
    def _mock_docker_source(self):
        """
        This method returns an instance of Mock object
        that acts as the specification for the DockerSource.
        """
        m_self = mock.Mock(spec=sources.DockerSource)
        m_self.progress = mock.Mock()
        m_self.no_cache = False
        m_self.url = "docker://test"
        m_self.images_dir = "/images_path"
        m_self.insecure = True
        m_self.username = 'user'
        m_self.password = 'password'
        m_self.layers = [
            ['sha256', '75c416ea', '/images_path/75c416ea.tar', ''],
            ['sha256', 'a7050fc1', '/images_path/a7050fc1.tar', '']
        ]
        return m_self

    ###################################
    # Tests for: __init__()
    ###################################
    def test_argument_assignment(self):
        """
        Ensures that __init__() assigns the arguments' values to instance
        variables.
        """
        kwargs = {'uri': '',
                  'fmt': 'dir',
                  'not_secure': False,
                  'no_cache': False,
                  'progress': mock.Mock(),
                  'username': 'username',
                  'password': 'password'}

        with mock.patch('virtBootstrap.utils'
                        '.get_image_dir') as m_get_image_dir:
            with mock.patch.multiple('virtBootstrap.sources.DockerSource',
                                     retrieve_layers_info=mock.DEFAULT,
                                     gen_valid_uri=mock.DEFAULT) as mocked:
                src_instance = sources.DockerSource(**kwargs)

        test_values = {
            src_instance.url: mocked['gen_valid_uri'].return_value,
            src_instance.progress: kwargs['progress'].update_progress,
            src_instance.username: kwargs['username'],
            src_instance.password: kwargs['password'],
            src_instance.output_format: kwargs['fmt'],
            src_instance.no_cache: kwargs['no_cache'],
            src_instance.insecure: kwargs['not_secure'],
            src_instance.images_dir: m_get_image_dir()
        }
        for value in test_values:
            self.assertIs(value, test_values[value])

    def test_source_password_is_required_if_username_specifed(self):
        """
        Ensures that __init__() calls getpass() to request password
        when username is specified and password is not.
        """
        test_password = 'secret'

        kwargs = {arg: '' for arg
                  in ['uri', 'fmt', 'not_secure', 'password', 'no_cache']}
        kwargs['progress'] = mock.Mock()
        kwargs['username'] = 'test'

        with mock.patch('virtBootstrap.utils.get_image_dir'):
            with mock.patch('virtBootstrap.sources.getpass') as m_getpass:
                m_getpass.getpass.return_value = test_password
                with mock.patch.multiple('virtBootstrap.sources.DockerSource',
                                         retrieve_layers_info=mock.DEFAULT,
                                         gen_valid_uri=mock.DEFAULT):
                    src_instance = sources.DockerSource(**kwargs)

        m_getpass.getpass.assert_called_once()
        self.assertIs(test_password, src_instance.password)

    ###################################
    # Tests for: retrieve_layers_info()
    ###################################
    def _mock_retrieve_layers_info(self, manifest, kwargs):
        """
        This method is gather common test pattern used in the following
        two test cases.
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
        src_kwargs = {'uri': '',
                      'fmt': 'dir',
                      'not_secure': False,
                      'no_cache': False,
                      'progress': mock.Mock(),
                      'username': 'username',
                      'password': 'password'}

        manifest = {'schemaVersion': 2, 'layers': []}
        (src_instance,
         m_uri, m_utils) = self._mock_retrieve_layers_info(manifest,
                                                           src_kwargs)

        kwargs = {arg: getattr(src_instance, arg)
                  for arg in ['insecure', 'username', 'password']}
        kwargs['raw'] = True
        m_utils['get_image_details'].assert_called_once_with(m_uri(), **kwargs)

    def test_retrieve_layers_info_schema_version_1(self):
        """
        Ensures that retrieve_layers_info() extracts the layers' information
        from manifest with schema version 1 a list with format:
            ["digest", "sum_type", "file_path", "size"].
        """
        args = ['uri', 'fmt', 'not_secure', 'password', 'username', 'no_cache']
        kwargs = {arg: arg for arg in args}
        kwargs['progress'] = mock.Mock()

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

        src_instance = self._mock_retrieve_layers_info(manifest, kwargs)[0]
        self.assertEqual(src_instance.layers, expected_result)

    def test_retrieve_layers_info_schema_version_2(self):
        """
        Ensures that retrieve_layers_info() extracts the layers' information
        from manifest with schema version 2 a list with format:
            ["digest", "sum_type", "file_path", "size"].
        """
        args = ['uri', 'fmt', 'not_secure', 'password', 'username', 'no_cache']
        kwargs = {arg: arg for arg in args}
        kwargs['progress'] = mock.Mock()

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
        args = ['uri', 'fmt', 'not_secure', 'password', 'username', 'no_cache']
        kwargs = {arg: arg for arg in args}
        kwargs['progress'] = mock.Mock()

        manifest = {'schemaVersion': 3}
        with self.assertRaises(ValueError):
            self._mock_retrieve_layers_info(manifest, kwargs)

    ###################################
    # Tests for: gen_valid_uri()
    ###################################
    def test_gen_valid_uri(self):
        """
        Validates the output of gen_valid_uri() for some test cases.
        """
        m_self = self._mock_docker_source()
        test_values = {
            'docker:///repo': 'docker://repo',
            'docker:/repo': 'docker://repo',
            'docker://repo/': 'docker://repo',
            'docker://repo/image/': 'docker://repo/image',
            'docker:///repo/image/': 'docker://repo/image',
        }
        for uri in test_values:
            uri_obj = urlparse(uri)
            result = sources.DockerSource.gen_valid_uri(m_self, uri_obj)
            expected = test_values[uri]
            self.assertEqual(result, expected)

    ###################################
    # Tests for: download_image()
    ###################################
    def test_download_image(self):
        """
        Ensures that download_image() calls read_skopeo_progress() with
        expected skopeo copy command and removes tha leftover manifest file.
        """
        m_self = self._mock_docker_source()
        m_self.read_skopeo_progress = mock.Mock()
        manifest_path = "%s/manifest.json" % m_self.images_dir
        with mock.patch('os.remove') as m_remove:
            sources.DockerSource.download_image(m_self)

        expected_call = ["skopeo", "copy", m_self.url,
                         "dir:" + m_self.images_dir,
                         '--src-tls-verify=false',
                         '--src-creds={}:{}'.format(m_self.username,
                                                    m_self.password)]
        m_self.read_skopeo_progress.assert_called_once_with(expected_call)
        m_remove.assert_called_once_with(manifest_path)

    ###################################
    # Tests for: parse_output()
    ###################################
    def test_parse_output_return_false_on_fail(self):
        """
        Ensures that parse_output() returns False when process call
        exits with non-zero code.
        """
        m_self = mock.Mock(spec=sources.DockerSource)
        m_self.layers = []
        m_proc = mock.Mock()
        m_proc.returncode = 1
        self.assertFalse(sources.DockerSource.parse_output(m_self, m_proc))

    def test_parse_output(self):
        """
        Ensures that parse_output() recognises processing of different
        layers from the skopeo's output.
        """
        m_self = self._mock_docker_source()
        m_proc = mock.Mock()
        m_proc.poll.return_value = None
        m_proc.returncode = 0
        test_values = '\n'.join([
            'Skipping fetch of repeat blob sha256:c6ff40',
            'Copying blob sha256:75c416ea735c4',
            '40.00 MB / 44.92 MB [======================>------]',
            'Copying config sha256:d355ed35',
            '40.00 MB / 44.92 MB [======================>------]'
        ])

        expected_progress_calls = [
            mock.call("Downloading layer (1/2)"),
            mock.call("Downloading layer (2/2)"),
        ]

        with mock.patch('select.select') as m_select:
            m_select.return_value = [[test_values], [], []]
            with mock.patch('virtBootstrap.utils.read_async') as m_read_async:
                m_read_async.return_value = test_values
                self.assertTrue(sources.DockerSource.parse_output(m_self,
                                                                  m_proc))
        m_select.assert_called_once_with([m_proc.stdout], [], [])
        m_read_async.assert_called_once_with(test_values)
        m_self.progress.assert_has_calls(expected_progress_calls)
        m_self.update_progress_from_output.assert_called_once()
        m_proc.wait.assert_called_once()

    ###################################
    # Tests for: update_progress_from_output()
    ###################################
    def _mock_update_progress_from_output(self, test_values):
        """
        This method is gather common test pattern used in the following
        two test cases.
        """
        m_self = self._mock_docker_source()
        test_method = sources.DockerSource.update_progress_from_output
        for line in test_values:
            test_method(m_self, line.split(), 1, len(test_values))

        return m_self.progress.call_args_list

    def test_update_progress_from_output(self):
        """
        Ensures that update_progress_from_output() recognises the current
        downloaded size, the total layer's size and calculates correct
        percentage value.
        """
        test_values = [
            '500.00 KB / 4.00 MB [======>------]',
            '25.00 MB / 24.10 MB [======>------]',
            '40.00 MB / 50.00 MB [======>------]',
        ]
        expected_values = [2, 17.33, 13.33]

        calls = self._mock_update_progress_from_output(test_values)
        for call, expected in zip(calls, expected_values):
            self.assertAlmostEqual(call[1]['value'], expected, places=1)

    def test_update_progress_from_output_ignore_failures(self):
        """
        Ensures that update_progress_from_output() ignores invalid lines
        from skopeo's output.
        """
        test_values = [
            'a ',
            '1 ' * 5,
            '500.00 MB / 0.00 MB [======>------]',
            '00.00 MB / 00.00 MB [======>------]',
        ]
        self._mock_update_progress_from_output(test_values)

    ###################################
    # Tests for: read_skopeo_progress()
    ###################################
    def _mock_read_skopeo_progress(self, test_cmd, parse_output_return):
        """
        This method is gather common test pattern used in the following
        two test cases.
        """
        m_self = mock.Mock(spec=sources.DockerSource)
        m_self.parse_output.return_value = parse_output_return
        with mock.patch.multiple('virtBootstrap.sources',
                                 Popen=mock.DEFAULT,
                                 PIPE=mock.DEFAULT) as mocked:
            with mock.patch('virtBootstrap.utils.make_async') as m_make_async:
                sources.DockerSource.read_skopeo_progress(m_self, test_cmd)

        return (mocked, m_make_async)

    def test_read_skopeo_progress(self):
        """
        Ensures that read_skopeo_progress() calls make_async() with
        the stdout pipe of skopeo's process.
        """
        test_cmd = 'test'
        mocked, m_make_async = self._mock_read_skopeo_progress(test_cmd, True)

        mocked['Popen'].assert_called_once_with(test_cmd,
                                                stdout=mocked['PIPE'],
                                                stderr=mocked['PIPE'],
                                                universal_newlines=True)
        m_make_async.assert_called_once_with(mocked['Popen']().stdout)

    def test_read_skopeo_progress_raise_error(self):
        """
        Ensures that read_skopeo_progress() raise CalledProcessError
        when parse_output() returns false.
        """
        with self.assertRaises(sources.CalledProcessError):
            self._mock_read_skopeo_progress('test', False)

    ###################################
    # Tests for: validate_image_layers()
    ###################################
    def _mock_validate_image_layers(self,
                                    checksum_return,
                                    path_exists_return,
                                    expected_result,
                                    check_calls=False):
        """
        This method is gather common test pattern used in the following
        three test cases.
        """
        m_self = self._mock_docker_source()

        with mock.patch('os.path.exists') as m_path_exists:
            with mock.patch('virtBootstrap.utils.checksum') as m_checksum:
                m_checksum.return_value = checksum_return
                m_path_exists.return_value = path_exists_return
                result = sources.DockerSource.validate_image_layers(m_self)
                self.assertEqual(result, expected_result)

        if check_calls:
            path_exists_expected_calls = []
            checksum_expected_calls = []
            # Generate expected calls
            for sum_type, hash_sum, path, _ignore in m_self.layers:
                path_exists_expected_calls.append(mock.call(path))
                checksum_expected_calls.append(
                    mock.call(path, sum_type, hash_sum))

            m_path_exists.assert_has_calls(path_exists_expected_calls)
            m_checksum.assert_has_calls(checksum_expected_calls)

    def test_validate_image_layers_should_return_true(self):
        """
        Ensures that validate_image_layers() returns True when:
        - checksum() returns True for all layers
        - the file path of all layers exist
        - all layers are validated
        """
        self._mock_validate_image_layers(True, True, True, True)

    def test_validate_image_layers_return_false_if_path_not_exist(self):
        """
        Ensures that validate_image_layers() returns False when
        checksum() returns False.
        """
        self._mock_validate_image_layers(False, True, False)

    def test_validate_image_layers_return_false_if_checksum_fail(self):
        """
        Ensures that validate_image_layers() returns False when
        the file path of layer does not exist.
        """
        self._mock_validate_image_layers(True, False, False)

    ###################################
    # Tests for: fetch_layers()
    ###################################
    def _mock_fetch_layers(self, validate_return):
        """
        This method is gather common test pattern used in the following
        two test cases.
        """
        m_self = mock.Mock(spec=sources.DockerSource)
        m_self.validate_image_layers.return_value = validate_return
        sources.DockerSource.fetch_layers(m_self)
        return m_self

    def test_fetch_layers_should_call_download_image(self):
        """
        Ensures that fetch_layers() calls download_image()
        when validate_image_layers() returns False.
        """
        m_self = self._mock_fetch_layers(False)
        m_self.download_image.assert_called_once()

    def test_fetch_layers_should_not_call_download_image(self):
        """
        Ensures that fetch_layers() does not call download_image()
        when validate_image_layers() returns True.
        """
        m_self = self._mock_fetch_layers(True)
        m_self.download_image.assert_not_called()

    ###################################
    # Tests for: unpack()
    ###################################
    def _unpack_test_fmt(self, output_format, patch_method=None,
                         side_effect=None, m_self=None):
        """
        This method is gather common test pattern used in the following
        two test cases.
        """
        m_self = m_self if m_self else self._mock_docker_source()
        m_self.output_format = output_format
        dest = 'foo'

        if patch_method:
            with mock.patch(patch_method) as mocked:
                if side_effect:
                    mocked.side_effect = side_effect
                sources.DockerSource.unpack(m_self, dest)

            mocked.assert_called_once_with(m_self.layers, dest,
                                           m_self.progress)
        else:
            sources.DockerSource.unpack(m_self, dest)

        m_self.fetch_layers.assert_called_once()

    def test_unpack_dir_format(self):
        """
        Ensures that unpack() calls untar_layers() when the output format
        is set to 'dir'.
        """
        self._unpack_test_fmt('dir', 'virtBootstrap.utils.untar_layers')

    def test_unpack_qcow2_format(self):
        """
        Ensures that unpack() calls extract_layers_in_qcow2() when the
        output format is set to 'qcow2'.
        """
        self._unpack_test_fmt('qcow2',
                              'virtBootstrap.utils.extract_layers_in_qcow2')

    def unpack_raise_error_test(self,
                                output_format,
                                patch_method,
                                side_effect=None,
                                msg=None):
        """
        This method is gather common test pattern used in the following
        four test cases.
        """
        with self.assertRaises(Exception) as err:
            self._unpack_test_fmt(output_format, patch_method,
                                  side_effect)
        if msg:
            self.assertEqual(msg, str(err.exception))

    def test_unpack_raise_error_for_unknown_format(self):
        """
        Ensures that unpack() throws an Exception when called with
        invalid output format.
        """
        msg = 'Unknown format:foo'
        self.unpack_raise_error_test('foo', None, None, msg)

    def test_unpack_raise_error_if_untar_fail(self):
        """
        Ensures that unpack() throws an Exception when untar_layers()
        fails.
        """
        msg = 'Caught untar failure'
        side_effect = Exception(msg)
        patch_method = 'virtBootstrap.utils.untar_layers'
        self.unpack_raise_error_test('dir', patch_method, side_effect, msg)

    def test_unpack_raise_error_if_extract_in_qcow2_fail(self):
        """
        Ensures that unpack() throws an Exception when
        extract_layers_in_qcow2() fails.
        """
        msg = 'Caught extract_layers_in_qcow2 failure'
        side_effect = Exception(msg)
        patch_method = 'virtBootstrap.utils.extract_layers_in_qcow2'
        self.unpack_raise_error_test('qcow2', patch_method, side_effect, msg)

    def test_unpack_no_cache_clean_up(self):
        """
        Ensures that unpack() removes the folder which stores tar archives
        of image layers when no_cache is set to True.
        """
        output_formats = ['dir', 'qcow2']
        patch_methods = [
            'virtBootstrap.utils.untar_layers',
            'virtBootstrap.utils.extract_layers_in_qcow2'
        ]
        for fmt, patch_mthd in zip(output_formats, patch_methods):
            m_self = self._mock_docker_source()
            m_self.no_cache = True
            with mock.patch('virtBootstrap.sources.shutil.rmtree') as m_shutil:
                self._unpack_test_fmt(fmt, patch_mthd, m_self=m_self)
            m_shutil.assert_called_once_with(m_self.images_dir)

    def test_unpack_no_cache_clean_up_on_failure(self):
        """
        Ensures that unpack() removes the folder which stores tar archives
        of image layers when no_cache is set to True and exception was
        raised.
        """
        m_self = self._mock_docker_source()
        m_self.no_cache = True
        with self.assertRaises(Exception):
            with mock.patch('shutil.rmtree') as m_rmtree:
                self._unpack_test_fmt('foo', None, m_self=m_self)
        m_rmtree.assert_called_once_with(m_self.images_dir)
