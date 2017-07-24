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
Unit tests for functions defined in virtBootstrap.virt-bootstrap
"""

from tests import unittest
from tests import mock
from tests import virt_bootstrap
from tests import sources


# pylint: disable=invalid-name
class TestVirtBootstrap(unittest.TestCase):
    """
    Test cases for virt_bootstrap module
    """

    ###################################
    # Tests for: get_source(source_type)
    ###################################
    def test_get_invaid_source_type_should_fail(self):
        """
        Ensures that get_source() throws an Exception when invalid source
        name was specified.
        """
        with self.assertRaises(Exception) as source:
            virt_bootstrap.get_source('invalid')
        self.assertIn('invalid', str(source.exception))

    def test_get_docker_source(self):
        """
        Ensures that get_source() returns DockerSource when source name
        "docker" is requested.
        """
        self.assertIs(virt_bootstrap.get_source('docker'),
                      sources.DockerSource)

    def test_get_file_source(self):
        """
        Ensures that get_source() returns FileSource when source name
        "file" is requested.
        """
        self.assertIs(virt_bootstrap.get_source('file'),
                      sources.FileSource)

    ###################################
    # Tests for: mapping_uid_gid()
    ###################################
    def test_mapping_uid_gid(self):
        """
        Ensures that mapping_uid_gid() calls map_id() with
        correct parameters.
        """
        dest = '/path'
        calls = [
            {  # Call 1
                'dest': dest,
                'uid': [[0, 1000, 10]],
                'gid': [[0, 1000, 10]]
            },
            {  # Call 2
                'dest': dest,
                'uid': [],
                'gid': [[0, 1000, 10]]
            },
            {  # Call 3
                'dest': dest,
                'uid': [[0, 1000, 10]],
                'gid': []
            },
            {  # Call 4
                'dest': dest,
                'uid': [[0, 1000, 10], [500, 500, 10]],
                'gid': [[0, 1000, 10]]
            }
        ]

        expected_calls = [
            # Expected from call 1
            mock.call(dest, [0, 1000, 10], [0, 1000, 10]),
            # Expected from call 2
            mock.call(dest, None, [0, 1000, 10]),
            # Expected from call 3
            mock.call(dest, [0, 1000, 10], None),
            # Expected from call 4
            mock.call(dest, [0, 1000, 10], [0, 1000, 10]),
            mock.call(dest, [500, 500, 10], None)

        ]
        with mock.patch('virtBootstrap.virt_bootstrap.map_id') as m_map_id:
            for args in calls:
                virt_bootstrap.mapping_uid_gid(args['dest'],
                                               args['uid'],
                                               args['gid'])

        m_map_id.assert_has_calls(expected_calls)

    ###################################
    # Tests for: map_id()
    ###################################
    @mock.patch('os.path.realpath')
    def test_map_id(self, m_realpath):
        """
        Ensures that the UID/GID mapping applies to all files
        and directories in root file system.
        """
        root_path = '/root'
        files = ['foo1', 'foo2']
        m_realpath.return_value = root_path

        map_uid = [0, 1000, 10]
        map_gid = [0, 1000, 10]
        new_id = 'new_id'

        expected_calls = [
            mock.call('/root', new_id, new_id),
            mock.call('/root/foo1', new_id, new_id),
            mock.call('/root/foo2', new_id, new_id)
        ]

        with mock.patch.multiple('os',
                                 lchown=mock.DEFAULT,
                                 lstat=mock.DEFAULT,
                                 walk=mock.DEFAULT) as mocked:

            mocked['walk'].return_value = [(root_path, [], files)]
            mocked['lstat']().st_uid = map_uid[0]
            mocked['lstat']().st_gid = map_gid[0]

            get_map_id = 'virtBootstrap.virt_bootstrap.get_map_id'
            with mock.patch(get_map_id) as m_get_map_id:
                m_get_map_id.return_value = new_id
                virt_bootstrap.map_id(root_path, map_uid, map_gid)

        mocked['lchown'].assert_has_calls(expected_calls)

    ###################################
    # Tests for: get_mapping_opts()
    ###################################
    def test_get_mapping_opts(self):
        """
        Ensures that get_mapping_opts() returns correct options for
        mapping value.
        """
        test_values = [
            {
                'mapping': [0, 1000, 10],
                'expected_result': {'first': 0, 'last': 10, 'offset': 1000},
            },
            {
                'mapping': [0, 1000, 10],
                'expected_result': {'first': 0, 'last': 10, 'offset': 1000},
            },
            {
                'mapping': [500, 1500, 1],
                'expected_result': {'first': 500, 'last': 501, 'offset': 1000},
            },
            {
                'mapping': [-1, -1, -1],
                'expected_result': {'first': 0, 'last': 1, 'offset': 0},
            }
        ]

        for test in test_values:
            res = virt_bootstrap.get_mapping_opts(test['mapping'])
            self.assertEqual(test['expected_result'], res)

    ###################################
    # Tests for: get_map_id()
    ###################################
    def test_get_map_id(self):
        """
        Ensures that get_map_id() returns correct UID/GID mapping value.
        """
        test_values = [
            {
                'old_id': 0,
                'mapping': [0, 1000, 10],
                'expected_result': 1000
            },
            {
                'old_id': 5,
                'mapping': [0, 500, 10],
                'expected_result': 505
            },
            {
                'old_id': 10,
                'mapping': [0, 100, 10],
                'expected_result': -1
            },
        ]
        for test in test_values:
            opts = virt_bootstrap.get_mapping_opts(test['mapping'])
            res = virt_bootstrap.get_map_id(test['old_id'], opts)
            self.assertEqual(test['expected_result'], res)

    ###################################
    # Tests for: parse_idmap()
    ###################################
    def test_parse_idmap(self):
        """
        Ensures that parse_idmap() returns correct UID/GID mapping value.
        """
        test_values = [
            {
                'mapping': ['0:1000:10', '0:100:10'],
                'expected_result': [[0, 1000, 10], [0, 100, 10]],
            },
            {
                'mapping': ['0:1000:10'],
                'expected_result': [[0, 1000, 10]],
            },
            {
                'mapping': ['500:1500:1'],
                'expected_result': [[500, 1500, 1]],
            },
            {
                'mapping': ['-1:-1:-1'],
                'expected_result': [[-1, -1, -1]],
            },
            {
                'mapping': [],
                'expected_result': None,
            }
        ]
        for test in test_values:
            res = virt_bootstrap.parse_idmap(test['mapping'])
            self.assertEqual(test['expected_result'], res)

    def test_parse_idmap_raise_exception_on_invalid_mapping_value(self):
        """
        Ensures that parse_idmap() raise ValueError on mapping value.
        """
        with self.assertRaises(ValueError):
            virt_bootstrap.parse_idmap(['invalid'])

    ###################################
    # Tests for: bootstrap()
    ###################################
    def test_bootsrap_creates_directory_if_does_not_exist(self):
        """
        Ensures that bootstrap() creates destination directory if
        it does not exists.
        """
        src, dest = 'foo', 'bar'
        with mock.patch.multiple(virt_bootstrap,
                                 get_source=mock.DEFAULT,
                                 os=mock.DEFAULT) as mocked:
            mocked['os'].path.exists.return_value = False
            virt_bootstrap.bootstrap(src, dest)
            mocked['os'].path.exists.assert_called_once_with(dest)
            mocked['os'].makedirs.assert_called_once_with(dest)

    def test_bootstrap_exit_if_dest_is_invalid(self):
        """
        Ensures that bootstrap() exits with code 1 when the destination
        path exists but it is not directory.
        """
        src, dest = 'foo', 'bar'
        with mock.patch.multiple(virt_bootstrap,
                                 get_source=mock.DEFAULT,
                                 os=mock.DEFAULT,
                                 logger=mock.DEFAULT,
                                 sys=mock.DEFAULT) as mocked:
            mocked['os'].path.exists.return_value = True
            mocked['os'].path.isdir.return_value = False
            virt_bootstrap.bootstrap(src, dest)
            mocked['os'].path.isdir.assert_called_once_with(dest)
            mocked['sys'].exit.assert_called_once_with(1)

    def test_bootsrap_exit_if_no_write_access_on_dest(self):
        """
        Ensures that bootstrap() exits with code 1 when the current user
        has not write permissions on the destination folder.
        """
        src, dest = 'foo', 'bar'
        with mock.patch.multiple(virt_bootstrap,
                                 get_source=mock.DEFAULT,
                                 os=mock.DEFAULT,
                                 logger=mock.DEFAULT,
                                 sys=mock.DEFAULT) as mocked:
            mocked['os'].path.exists.return_value = True
            mocked['os'].path.isdir.return_value = True
            mocked['os'].access.return_value = False
            virt_bootstrap.bootstrap(src, dest)
            mocked['os'].access.assert_called_once_with(dest,
                                                        mocked['os'].W_OK)
            mocked['sys'].exit.assert_called_once_with(1)

    def test_bootstrap_use_file_source_if_none_was_specified(self):
        """
        Ensures that bootstrap() calls get_source() with argument
        'file' when source format is not specified.
        """
        src, dest = 'foo', 'bar'
        with mock.patch.multiple(virt_bootstrap,
                                 get_source=mock.DEFAULT,
                                 os=mock.DEFAULT,
                                 sys=mock.DEFAULT) as mocked:
            virt_bootstrap.bootstrap(src, dest)
            mocked['get_source'].assert_called_once_with('file')

    def test_bootstrap_successful_call(self):
        """
        Ensures that bootstrap() creates source instance and calls the
        unpack method with destination path as argument.
        """
        src, dest = 'foo', 'bar'
        with mock.patch.multiple(virt_bootstrap,
                                 get_source=mock.DEFAULT,
                                 os=mock.DEFAULT,
                                 sys=mock.DEFAULT) as mocked:
            mocked['os'].path.exists.return_value = True
            mocked['os'].path.isdir.return_value = True
            mocked['os'].access.return_value = True
            mocked_source = mock.Mock()
            mocked_unpack = mock.Mock()
            mocked_source.return_value.unpack = mocked_unpack
            mocked['get_source'].return_value = mocked_source
            virt_bootstrap.bootstrap(src, dest)
            # sys.exit should not be called
            mocked['sys'].exit.assert_not_called()
            mocked_source.assert_called_once()
            mocked_unpack.assert_called_once_with(dest)

    def test_bootstrap_all_params_are_passed_to_source_instance(self):
        """
        Ensures that bootstrap() is passing all arguments to newly created
        source instance.
        """
        params_list = ['dest', 'fmt', 'username', 'password', 'root_password',
                       'not_secure', 'no_cache', 'progress_cb']
        params = {param: param for param in params_list}

        for kw_param in params_list:
            params[kw_param] = kw_param

        with mock.patch.multiple(virt_bootstrap,
                                 get_source=mock.DEFAULT,
                                 os=mock.DEFAULT,
                                 urlparse=mock.DEFAULT,
                                 progress=mock.DEFAULT,
                                 utils=mock.DEFAULT,
                                 sys=mock.DEFAULT) as mocked:
            mocked['os'].path.exists.return_value = True
            mocked['os'].path.isdir.return_value = True
            mocked['os'].access.return_value = True

            mocked['progress'].Progress.return_value = params['progress_cb']

            mocked_source = mock.Mock()
            mocked_unpack = mock.Mock()
            mocked_source.return_value.unpack = mocked_unpack
            mocked['get_source'].return_value = mocked_source

            mocked_uri = mock.Mock()
            mocked['urlparse'].return_value = mocked_uri
            params['uri'] = mocked_uri

            virt_bootstrap.bootstrap(**params)
            # sys.exit should not be called
            mocked['sys'].exit.assert_not_called()

            mocked_source.assert_called_once()
            mocked_unpack.assert_called_once_with(params['dest'])

            called_with_args, called_with_kwargs = mocked_source.call_args
            self.assertEqual(called_with_args, ())

            del params['dest']
            del params['root_password']
            params['progress'] = params.pop('progress_cb')
            for kwarg in params:
                self.assertEqual(called_with_kwargs[kwarg], params[kwarg])

    def test_if_bootstrap_calls_set_root_password(self):
        """
        Ensures that bootstrap() calls set_root_password() when the argument
        root_password is specified.
        """
        src, fmt, dest, root_password = 'foo', 'fmt', 'bar', 'root_password'
        with mock.patch.multiple(virt_bootstrap,
                                 get_source=mock.DEFAULT,
                                 os=mock.DEFAULT,
                                 utils=mock.DEFAULT,
                                 sys=mock.DEFAULT) as mocked:
            mocked['os'].path.exists.return_value = True
            mocked['os'].path.isdir.return_value = True
            mocked['os'].access.return_value = True

            virt_bootstrap.bootstrap(src, dest,
                                     fmt=fmt,
                                     root_password=root_password)

            mocked['utils'].set_root_password.assert_called_once_with(
                fmt, dest, root_password)

    def test_if_bootstrap_calls_set_mapping_uid_gid(self):
        """
        Ensures that bootstrap() calls mapping_uid_gid() when the argument
        uid_map or gid_map is specified.
        """
        src, dest, uid_map, gid_map = 'foo', 'bar', 'id', 'id'
        expected_calls = [
            mock.call('bar', None, 'id'),
            mock.call('bar', 'id', None),
            mock.call('bar', 'id', 'id')
        ]

        with mock.patch.multiple(virt_bootstrap,
                                 get_source=mock.DEFAULT,
                                 os=mock.DEFAULT,
                                 mapping_uid_gid=mock.DEFAULT,
                                 utils=mock.DEFAULT,
                                 sys=mock.DEFAULT) as mocked:
            mocked['os'].path.exists.return_value = True
            mocked['os'].path.isdir.return_value = True
            mocked['os'].access.return_value = True

            virt_bootstrap.bootstrap(src, dest, gid_map=gid_map)
            virt_bootstrap.bootstrap(src, dest, uid_map=uid_map)
            virt_bootstrap.bootstrap(src, dest,
                                     uid_map=uid_map, gid_map=gid_map)
        mocked['mapping_uid_gid'].assert_has_calls(expected_calls)

    ###################################
    # Tests for: set_logging_conf()
    ###################################
    def test_if_logging_level_format_handler_are_set(self):
        """
        Ensures that set_logging_conf() sets log level and adds new stream
        handler with formatting.
        """
        with mock.patch('virtBootstrap.virt_bootstrap.logging') as m_logging:
            mocked_stream_hdlr = mock.Mock()
            m_logger = mock.Mock()
            m_logging.getLogger.return_value = m_logger
            m_logging.StreamHandler.return_value = mocked_stream_hdlr
            virt_bootstrap.set_logging_conf()
            m_logging.getLogger.assert_called_once_with('virtBootstrap')
            mocked_stream_hdlr.setFormatter.assert_called_once()
            m_logger.addHandler.assert_called_once_with(mocked_stream_hdlr)
            m_logger.setLevel.assert_called_once()


if __name__ == '__main__':
    unittest.main(exit=False)
