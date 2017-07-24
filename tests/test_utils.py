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
Unit tests for functions defined in virtBootstrap.utils
"""

from tests import unittest
from tests import mock
from tests import utils
try:
    # pylint: disable=redefined-builtin
    from importlib import reload
except ImportError:
    pass


# pylint: disable=invalid-name
# pylint: disable=too-many-public-methods
class TestUtils(unittest.TestCase):
    """
    Ensures that functions defined in the utils module of virtBootstrap
    work as expected.
    """

    ###################################
    # Tests for: checksum()
    ###################################
    def test_utils_checksum_return_false_on_invalid_hash(self):
        """
        Ensures that checksum() returns False if the actual and expected
        hash sum of file are not equal.
        """
        with mock.patch.multiple(utils,
                                 open=mock.DEFAULT,
                                 logger=mock.DEFAULT,
                                 hashlib=mock.DEFAULT) as mocked:
            path, sum_type, sum_expected = '/foo', 'sha256', 'bar'
            mocked['hashlib'].sha256.hexdigest.return_value = False
            self.assertFalse(utils.checksum(path, sum_type, sum_expected))

    def test_utils_checksum_return_false_if_file_could_not_be_opened(self):
        """
        Ensures that checksum() returns False if the file to be checked
        cannot be open for read.
        """
        with mock.patch.multiple(utils,
                                 open=mock.DEFAULT,
                                 logger=mock.DEFAULT,
                                 hashlib=mock.DEFAULT) as mocked:
            mocked['open'].side_effect = IOError()
            self.assertFalse(utils.checksum('foo', 'sha256', 'bar'))

    def test_utils_checksum_return_true_on_valid_hash(self):
        """
        Ensures that checksum() returns True when the actual and expected
        hash sum of file are equal.
        """
        with mock.patch.multiple(utils,
                                 open=mock.DEFAULT,
                                 logger=mock.DEFAULT,
                                 hashlib=mock.DEFAULT) as mocked:
            path, sum_type, sum_expected = '/foo', 'sha256', 'bar'
            mocked['hashlib'].sha256.return_value.hexdigest.return_value \
                = sum_expected
            self.assertTrue(utils.checksum(path, sum_type, sum_expected))

    ###################################
    # Tests for: execute()
    ###################################
    def test_utils_execute_logging_on_successful_proc_call(self):
        """
        Ensures that execute() creates log record of cmd, stdout and stderr
        when the exit code of process is 0.
        """
        with mock.patch.multiple(utils,
                                 logger=mock.DEFAULT,
                                 Popen=mock.DEFAULT) as mocked:
            cmd = ['foo']
            output, err = 'test_out', 'test_err'

            mocked['Popen'].return_value.returncode = 0
            (mocked['Popen'].return_value
             .communicate.return_value) = (output.encode(), err.encode())

            utils.execute(cmd)
            mocked['logger'].debug.assert_any_call("Call command:\n%s", cmd[0])
            mocked['logger'].debug.assert_any_call("Stdout:\n%s", output)
            mocked['logger'].debug.assert_any_call("Stderr:\n%s", err)

    def test_utils_execute_raise_error_on_unsuccessful_proc_call(self):
        """
        Ensures that execute() raise CalledProcessError exception when the
        exit code of process is not 0.
        """
        with mock.patch('virtBootstrap.utils.Popen') as m_popen:
            m_popen.return_value.returncode = 1
            m_popen.return_value.communicate.return_value = (b'output', b'err')
            with self.assertRaises(utils.CalledProcessError):
                utils.execute(['foo'])

    ###################################
    # Tests for: safe_untar()
    ###################################
    def test_utils_safe_untar_calls_execute(self):
        """
        Ensures that safe_untar() calls execute with virt-sandbox
        command to extract source files to destination folder.
        Test for users with EUID 0 and 1000.
        """
        with mock.patch('virtBootstrap.utils.os.geteuid') as m_geteuid:
            for uid in [0, 1000]:
                m_geteuid.return_value = uid
                reload(utils)
                with mock.patch('virtBootstrap.utils.execute') as m_execute:
                    src, dest = 'foo', 'bar'
                    utils.safe_untar('foo', 'bar')
                    cmd = ['virt-sandbox',
                           '-c', utils.LIBVIRT_CONN,
                           '-m', 'host-bind:/mnt=' + dest,
                           '--',
                           '/bin/tar', 'xf', src,
                           '-C', '/mnt',
                           '--exclude', 'dev/*']
                    m_execute.assert_called_once_with(cmd)

    ###################################
    # Tests for: bytes_to_size()
    ###################################
    def test_utils_bytes_to_size(self):
        """
        Validates the output of bytes_to_size() for some test cases.
        """
        test_values = {
            0: '0', 1: '1', 512: '512', 1000: '0.98 KiB', 1024: '1 KiB',
            4096: '4 KiB', 5120: '5 KiB', 10 ** 10: '9.31 GiB'
        }
        for value in test_values:
            self.assertEqual(utils.bytes_to_size(value), test_values[value])

    ###################################
    # Tests for: size_to_bytes()
    ###################################
    def test_utils_size_to_bytes(self):
        """
        Validates the output of size_to_bytes() for some test cases.
        """
        test_values = [1, '0']
        test_formats = ['TB', 'GB', 'MB', 'KB', 'B']
        expected_output = [1099511627776, 1073741824, 1048576, 1024, 1,
                           0, 0, 0, 0, 0]
        i = 0
        for value in test_values:
            for fmt in test_formats:
                self.assertEqual(utils.size_to_bytes(value, fmt),
                                 expected_output[i])
                i += 1

    ###################################
    # Tests for: log_layer_extract()
    ###################################
    def test_utils_log_layer_extract(self):
        """
        Ensures that log_layer_extract() updates the progress and creates
        log record with debug level.
        """
        m_progress = mock.Mock()
        layer = ['sum_type', 'sum_value', 'layer_file', 'layer_size']
        with mock.patch.multiple(utils, logger=mock.DEFAULT,
                                 bytes_to_size=mock.DEFAULT) as mocked:
            utils.log_layer_extract(layer, 'foo', 'bar', m_progress)
        mocked['bytes_to_size'].assert_called_once_with('layer_size')
        mocked['logger'].debug.assert_called_once()
        m_progress.assert_called_once()

    ###################################
    # Tests for: get_mime_type()
    ###################################
    @mock.patch('virtBootstrap.utils.Popen')
    def test_utils_get_mime_type(self, m_popen):
        """
        Ensures that get_mime_type() returns the detected MIME type
        of /usr/bin/file.
        """
        path = "foo"
        mime = "application/x-gzip"
        stdout = ('%s: %s' % (path, mime)).encode()
        m_popen.return_value.stdout.read.return_value = stdout
        self.assertEqual(utils.get_mime_type(path), mime)
        m_popen.assert_called_once_with(["/usr/bin/file", "--mime-type", path],
                                        stdout=utils.PIPE)

    ###################################
    # Tests for: untar_layers()
    ###################################
    def test_utils_untar_all_layers_in_order(self):
        """
        Ensures that untar_layers() iterates through all passed layers
        in order.
        """
        layers = ['l1', 'l2', 'l3']
        layers_list = [['', '', layer] for layer in layers]
        dest_dir = '/foo'
        expected_calls = [mock.call(layer, dest_dir) for layer in layers]
        with mock.patch.multiple(utils,
                                 safe_untar=mock.DEFAULT,
                                 log_layer_extract=mock.DEFAULT) as mocked:
            utils.untar_layers(layers_list, dest_dir, mock.Mock())
        mocked['safe_untar'].assert_has_calls(expected_calls)

    ###################################
    # Tests for: create_qcow2()
    ###################################
    def _apply_test_to_create_qcow2(self, expected_calls, *args):
        """
        This method contains common test pattern used in the next two
        test cases.
        """
        with mock.patch.multiple(utils,
                                 execute=mock.DEFAULT,
                                 logger=mock.DEFAULT,
                                 get_mime_type=mock.DEFAULT) as mocked:
            mocked['get_mime_type'].return_value = 'application/x-gzip'
            utils.create_qcow2(*args)
        mocked['execute'].assert_has_calls(expected_calls)

    def test_utils_create_qcow2_base_layer(self):
        """
        Ensures that create_qcow2() creates base layer when
        backing_file = None.
        """
        tar_file = 'foo'
        layer_file = 'bar'
        size = '5G'
        backing_file = None

        expected_calls = [
            mock.call(["qemu-img", "create", "-f", "qcow2", layer_file, size]),

            mock.call(['virt-format',
                       '--format=qcow2',
                       '--partition=none',
                       '--filesystem=ext3',
                       '-a', layer_file]),

            mock.call(['guestfish',
                       '-a', layer_file,
                       '-m', '/dev/sda',
                       'tar-in', tar_file, '/', 'compress:gzip'])
        ]

        self._apply_test_to_create_qcow2(expected_calls, tar_file, layer_file,
                                         backing_file, size)

    def test_utils_create_qcow2_layer_with_backing_chain(self):
        """
        Ensures that create_qcow2() creates new layer with backing chains
        when backing_file is specified.
        """
        tar_file = 'foo'
        layer_file = 'bar'
        backing_file = 'base'
        size = '5G'

        expected_calls = [
            mock.call(['qemu-img', 'create',
                       '-b', backing_file,
                       '-f', 'qcow2',
                       layer_file, size]),

            mock.call(['guestfish',
                       '-a', layer_file,
                       '-m', '/dev/sda',
                       'tar-in', tar_file, '/', 'compress:gzip'])
        ]

        self._apply_test_to_create_qcow2(expected_calls, tar_file, layer_file,
                                         backing_file, size)

    ###################################
    # Tests for: extract_layers_in_qcow2()
    ###################################
    def test_utils_if_all_layers_extracted_in_order_in_qcow2(self):
        """
        Ensures that extract_layers_in_qcow2() iterates through all
        layers in order.
        """
        layers = ['l1', 'l2', 'l3']
        layers_list = [['', '', layer] for layer in layers]
        dest_dir = '/foo'

        # Generate expected calls
        expected_calls = []
        qcow2_backing_file = None
        for index, layer in enumerate(layers):
            qcow2_layer_file = dest_dir + "/layer-%s.qcow2" % index
            expected_calls.append(
                mock.call(layer, qcow2_layer_file, qcow2_backing_file))
            qcow2_backing_file = qcow2_layer_file

        # Mocking out and execute
        with mock.patch.multiple(utils,
                                 create_qcow2=mock.DEFAULT,
                                 log_layer_extract=mock.DEFAULT) as mocked:
            utils.extract_layers_in_qcow2(layers_list, dest_dir, mock.Mock())

        # Check actual calls
        mocked['create_qcow2'].assert_has_calls(expected_calls)

    ###################################
    # Tests for: get_image_dir()
    ###################################
    def test_utils_getimage_dir(self):
        """
        Ensures that get_image_dir() returns path to DEFAULT_IMG_DIR
        if the no_cache argument is set to False and create it if
        does not exist.
        """
        # Perform this test for UID 0 and 1000
        for uid in [0, 1000]:
            with mock.patch('os.geteuid') as m_geteuid:
                m_geteuid.return_value = uid
                reload(utils)
                with mock.patch('os.makedirs') as m_makedirs:
                    with mock.patch('os.path.exists') as m_path_exists:
                        m_path_exists.return_value = False
                        self.assertEqual(utils.get_image_dir(False),
                                         utils.DEFAULT_IMG_DIR)
            m_makedirs.assert_called_once_with(utils.DEFAULT_IMG_DIR)

    @mock.patch('tempfile.mkdtemp')
    def test_utils_getimage_dir_no_cache(self, m_mkdtemp):
        """
        Ensures that get_image_dir() returns temporary file path created
        by tempfile.mkdtemp.
        """
        m_mkdtemp.return_value = 'foo'
        self.assertEqual(utils.get_image_dir(True), 'foo')
        m_mkdtemp.assert_called_once()

    ###################################
    # Tests for: get_image_details()
    ###################################
    @mock.patch('virtBootstrap.utils.Popen')
    def test_utils_get_image_details_raise_error_on_fail(self, m_popen):
        """
        Ensures that get_image_details() throws ValueError exception
        when stderr from skopeo is provided.
        """
        src = 'docker://foo'
        m_popen.return_value.communicate.return_value = [b'', b'Error']
        with self.assertRaises(ValueError):
            utils.get_image_details(src)

    @mock.patch('virtBootstrap.utils.Popen')
    def test_utils_get_image_details_return_json_obj_on_success(self, m_popen):
        """
        Ensures that get_image_details() returns python dictionary which
        represents the data provided from stdout of skopeo when stderr
        is not present.
        """
        src = 'docker://foo'
        json_dict = {'foo': 'bar'}
        stdout = utils.json.dumps(json_dict).encode()
        m_popen.return_value.communicate.return_value = [stdout, '']
        self.assertDictEqual(utils.get_image_details(src), json_dict)

    def test_utils_get_image_details_all_argument_passed(self):
        """
        Ensures that get_image_details() pass all argument values to
        skopeo inspect.
        """
        src = 'docker://foo'
        raw, insecure = True, True
        username, password = 'user', 'password'
        cmd = ['skopeo', 'inspect', src,
               '--raw',
               '--tls-verify=false',
               "--creds=%s:%s" % (username, password)]

        with mock.patch.multiple(utils,
                                 Popen=mock.DEFAULT,
                                 PIPE=mock.DEFAULT) as mocked:
            mocked['Popen'].return_value.communicate.return_value = [b'{}',
                                                                     b'']
            utils.get_image_details(src, raw, insecure, username, password)

        mocked['Popen'].assert_called_once_with(cmd,
                                                stdout=mocked['PIPE'],
                                                stderr=mocked['PIPE'])

    ###################################
    # Tests for: is_new_layer_message()
    ###################################
    def test_utils_is_new_layer_message(self):
        """
        Ensures that is_new_layer_message() returns True when message
        from the skopeo's stdout indicates processing of new layer
        and False otherwise.
        """

        valid_msgs = [
            "Copying blob sha256:be232718519c940b04bc57",
            "Skipping fetch of repeat blob sha256:75c416ea735c42a4a0b2"
        ]

        invalid_msgs = [
            'Copying config sha256', 'test', ''
        ]

        for msg in valid_msgs:
            self.assertTrue(utils.is_new_layer_message(msg))
        for msg in invalid_msgs:
            self.assertFalse(utils.is_new_layer_message(msg))

    ###################################
    # Tests for: is_layer_config_message()
    ###################################
    def test_utils_is_layer_config_message(self):
        """
        Ensures that is_layer_config_message() returns True when message
        from the skopeo's stdout indicates processing of manifest file
        of container image and False otherwise.
        """
        invalid_msgs = [
            "Copying blob sha256:be232718519c940b04bc57",
            "Skipping fetch of repeat blob sha256:75c416ea735c42a4a0b2",
            ''
        ]

        valid_msg = 'Copying config sha256:d355ed3537e94e76389fd78b7724'

        self.assertTrue(utils.is_layer_config_message(valid_msg))
        for msg in invalid_msgs:
            self.assertFalse(utils.is_layer_config_message(msg))

    ###################################
    # Tests for: make_async()
    ###################################
    def test_utils_make_async(self):
        """
        Ensures that make_async() sets O_NONBLOCK flag on PIPE.
        """

        pipe = utils.Popen(["echo"], stdout=utils.PIPE).stdout
        fd = pipe.fileno()
        F_GETFL = utils.fcntl.F_GETFL
        O_NONBLOCK = utils.os.O_NONBLOCK

        self.assertFalse(utils.fcntl.fcntl(fd, F_GETFL) & O_NONBLOCK)
        utils.make_async(fd)
        self.assertTrue(utils.fcntl.fcntl(fd, F_GETFL) & O_NONBLOCK)

    ###################################
    # Tests for: read_async()
    ###################################
    def test_utils_read_async_successful_read(self):
        """
        Ensures that read_async() calls read() of passed file descriptor.
        """
        m_fd = mock.MagicMock()
        utils.read_async(m_fd)
        m_fd.read.assert_called_once()

    def test_utils_read_async_return_empty_str_on_EAGAIN_error(self):
        """
        Ensures that read_async() ignores EAGAIN errors and returns
        empty string.
        """
        m_fd = mock.MagicMock()
        m_fd.read.side_effect = IOError(utils.errno.EAGAIN, '')
        self.assertEqual(utils.read_async(m_fd), '')

    def test_utils_read_async_raise_errors(self):
        """
        Ensures that read_async() does not ignore IOError which is different
        than EAGAIN and throws an exception.
        """
        m_fd = mock.MagicMock()
        m_fd.read.side_effect = IOError()
        with self.assertRaises(IOError):
            utils.read_async(m_fd)

    ###################################
    # Tests for: str2float()
    ###################################
    def test_utils_str2float(self):
        """
        Validates the output of str2float() for some test cases.
        """
        test_values = {'1': 1.0, 'test': None, '0': 0.0, '1.25': 1.25}
        for test in test_values:
            self.assertEqual(utils.str2float(test), test_values[test])

    ###################################
    # Tests for: set_root_password_in_rootfs()
    ###################################
    def test_utils_set_root_password_in_rootfs_restore_permissions(self):
        """
        Ensures that set_root_password_in_rootfs() restore shadow
        file permissions after edit.
        """
        permissions = 700
        rootfs_path = '/foo'
        shadow_file = '%s/etc/shadow' % rootfs_path

        m_open = mock.mock_open(read_data='')
        with mock.patch('virtBootstrap.utils.open', m_open, create=True):
            with mock.patch('virtBootstrap.utils.os') as m_os:
                m_os.stat.return_value = [permissions]
                m_os.path.join.return_value = shadow_file
                utils.set_root_password_in_rootfs(rootfs_path, 'password')

        expected_calls = [
            mock.call.path.join(rootfs_path, 'etc/shadow'),
            mock.call.stat(shadow_file),
            mock.call.chmod(shadow_file, 438),
            mock.call.chmod(shadow_file, permissions)
        ]
        m_os.assert_has_calls(expected_calls)

    def test_utils_set_root_password_in_rootfs_restore_permissions_fail(self):
        """
        Ensures that set_root_password_in_rootfs() restore shadow file
        permissions in case of failure.
        """
        permissions = 700
        rootfs_path = '/foo'
        shadow_file = '%s/etc/shadow' % rootfs_path

        m_open = mock.mock_open(read_data='')
        with mock.patch('virtBootstrap.utils.open', m_open, create=True):
            with mock.patch('virtBootstrap.utils.os') as m_os:
                m_os.stat.return_value = [permissions]
                m_os.path.join.return_value = shadow_file

                with self.assertRaises(Exception):
                    m_open.side_effect = Exception
                    utils.set_root_password_in_rootfs(rootfs_path, 'password')

        expected_calls = [
            mock.call.path.join(rootfs_path, 'etc/shadow'),
            mock.call.stat(shadow_file),
            mock.call.chmod(shadow_file, 438),
            mock.call.chmod(shadow_file, permissions)
        ]
        m_os.assert_has_calls(expected_calls)

    def test_utils_set_root_password_in_rootfs_store_hash(self):
        """
        Ensures that set_root_password_in_rootfs() stores the hashed
        root password in shadow file.
        """
        rootfs_path = '/foo'
        password = 'secret'
        initial_value = '!locked'
        hashed_password = 'hashed_password'
        shadow_content = '\n'.join([
            "root:%s::0:99999:7:::",
            "bin:*:17004:0:99999:7:::"
            "daemon:*:17004:0:99999:7:::",
            "adm:*:17004:0:99999:7:::"
        ])

        m_open = mock.mock_open(read_data=shadow_content % initial_value)
        with mock.patch('virtBootstrap.utils.open', m_open, create=True):
            with mock.patch('virtBootstrap.utils.os'):
                with mock.patch('passlib.hosts.linux_context.hash') as m_hash:
                    m_hash.return_value = hashed_password
                    utils.set_root_password_in_rootfs(rootfs_path, password)

        m_hash.assert_called_once_with(password)
        m_open().write.assert_called_once_with(shadow_content
                                               % hashed_password)

    ###################################
    # Tests for: set_root_password_in_image()
    ###################################
    @mock.patch('virtBootstrap.utils.execute')
    def test_utils_set_root_password_in_image(self, m_execute):
        """
        Ensures that set_root_password_in_image() calls virt-edit
        with correct arguments.
        """
        image, password = 'foo', 'password'
        password_hash = ('$6$rounds=656000$PaQ/H4c/k8Ix9YOM$'
                         'cyD47r9PtAE2LhnkpdbVzsiQbM0/h2S/1Bv'
                         'u/sXqUtCg.3Ijp7TQy/8tEVstxMy5k5v4mh'
                         'CGFqnVv7S6wd.Ah/')

        expected_call = [
            'virt-edit',
            '-a', image, '/etc/shadow',
            '-e', 's,^root:.*?:,root:%s:,' % utils.re.escape(password_hash)]

        hash_function = 'virtBootstrap.utils.passlib.hosts.linux_context.hash'
        with mock.patch(hash_function) as m_hash:
            m_hash.return_value = password_hash
            utils.set_root_password_in_image(image, password)

        m_execute.assert_called_once_with(expected_call)

    ###################################
    # Tests for: set_root_password()
    ###################################
    @mock.patch('virtBootstrap.utils.set_root_password_in_rootfs')
    def test_utils_set_root_password_dir(self, m_set_root_password_in_rootfs):
        """
        Ensures that set_root_password() calls set_root_password_in_rootfs()
        when the format is set to "dir".
        """
        fmt, dest, root_password = 'dir', 'dest', 'root_password'
        utils.set_root_password(fmt, dest, root_password)

        m_set_root_password_in_rootfs.assert_called_once_with(
            dest, root_password
        )

    @mock.patch('virtBootstrap.utils.set_root_password_in_image')
    def test_utils_set_root_password_qcow2(self, m_set_root_password_in_image):
        """
        Ensures that set_root_password() calls set_root_password_in_image()
        when the format is set to "qcow2" with the path to the last
        extracted layer.
        """
        fmt, dest, root_password = 'qcow2', 'dest', 'root_password'
        layers = ['layer-0.qcow2', 'layer-1.qcow2']

        with mock.patch('os.listdir') as m_listdir:
            m_listdir.return_value = layers
            utils.set_root_password(fmt, dest, root_password)

        m_set_root_password_in_image.assert_called_once_with(
            utils.os.path.join(dest, max(layers)),
            root_password
        )

    ###################################
    # Tests for: write_progress()
    ###################################
    def test_utils_write_progress_fill_terminal_width(self):
        """
        Ensures that write_progress() outputs a message with length
        equal to terminal width and last symbol '\r'.
        """
        terminal_width = 120
        prog = {'status': 'status', 'value': 0}
        with mock.patch.multiple(utils,
                                 Popen=mock.DEFAULT,
                                 PIPE=mock.DEFAULT,
                                 sys=mock.DEFAULT) as mocked:

            (mocked['Popen'].return_value.stdout
             .read.return_value) = ("20 %s" % terminal_width).encode()

            utils.write_progress(prog)

        mocked['Popen'].assert_called_once_with(["stty", "size"],
                                                stdout=mocked['PIPE'])
        output_message = mocked['sys'].stdout.write.call_args[0][0]
        mocked['sys'].stdout.write.assert_called_once()
        self.assertEqual(len(output_message), terminal_width + 1)
        self.assertEqual(output_message[-1], '\r')

    def test_utils_write_progress_use_default_term_width_on_failure(self):
        """
        Ensures that write_progress() outputs a message with length equal
        to default terminal width (80) when the detecting terminal width
        has failed.
        """
        default_terminal_width = 80
        prog = {'status': 'status', 'value': 0}
        with mock.patch.multiple(utils, Popen=mock.DEFAULT,
                                 sys=mock.DEFAULT) as mocked:
            mocked['Popen'].side_effect = Exception()
            utils.write_progress(prog)

        self.assertEqual(len(mocked['sys'].stdout.write.call_args[0][0]),
                         default_terminal_width + 1)
        mocked['sys'].stdout.write.assert_called_once()


if __name__ == '__main__':
    unittest.main(exit=False)
