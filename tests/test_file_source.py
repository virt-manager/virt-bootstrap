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
Unit tests for methods defined in virtBootstrap.sources.FileSource
"""

from tests import unittest
from tests import mock
from tests import sources


# pylint: disable=invalid-name
class TestFileSource(unittest.TestCase):
    """
    Test cases for FileSource
    """

    ###################################
    # Tests for: __init__()
    ###################################
    def test_argument_assignment(self):
        """
        Ensures that __init__() assigns the arguments' values to instance
        variables.
        """
        kwargs = {'uri': mock.Mock(),
                  'fmt': 'dir',
                  'progress': mock.Mock()}

        src_instance = sources.FileSource(**kwargs)

        test_values = {
            src_instance.path: kwargs['uri'].path,
            src_instance.output_format: kwargs['fmt'],
            src_instance.progress: kwargs['progress'].update_progress
        }
        for value in test_values:
            self.assertIs(value, test_values[value])

    ###################################
    # Tests for: unpack()
    ###################################
    def test_unpack_invalid_source_raise_exception(self):
        """
        Ensures that unpack() throws an Exception when called with
        invalid file source.
        """
        m_self = mock.Mock(spec=sources.FileSource)
        m_self.path = 'foo'
        with mock.patch('os.path.isfile') as m_isfile:
            m_isfile.return_value = False
            with self.assertRaises(Exception) as err:
                sources.FileSource.unpack(m_self, 'bar')
        self.assertIn('Invalid file source', str(err.exception))

    def test_unpack_to_dir(self):
        """
        Ensures that unpack() calls safe_untar() when the output format
        is set to 'dir'.
        """
        m_self = mock.Mock(spec=sources.FileSource)
        m_self.progress = mock.Mock()
        m_self.path = 'foo'
        m_self.output_format = 'dir'
        dest = 'bar'

        with mock.patch('os.path.isfile') as m_isfile:
            m_isfile.return_value = True
            with mock.patch('virtBootstrap.utils.safe_untar') as m_untar:
                sources.FileSource.unpack(m_self, dest)

        m_untar.assert_called_once_with(m_self.path, dest)

    def test_unpack_to_qcow2(self):
        """
        Ensures that unpack() calls create_qcow2() when the output
        format is set to 'qcow2'.
        """
        m_self = mock.Mock(spec=sources.FileSource)
        m_self.progress = mock.Mock()
        m_self.path = 'foo'
        m_self.output_format = 'qcow2'
        dest = 'bar'
        qcow2_file_path = 'foobar'

        with mock.patch.multiple('os.path',
                                 isfile=mock.DEFAULT,
                                 realpath=mock.DEFAULT) as mocked:

            mocked['isfile'].return_value = True
            mocked['realpath'].return_value = qcow2_file_path
            with mock.patch('virtBootstrap.utils.create_qcow2') as m_qcow2:
                sources.FileSource.unpack(m_self, dest)

        m_qcow2.assert_called_once_with(m_self.path, qcow2_file_path)

    def _unpack_raise_error_test(self,
                                 output_format,
                                 side_effect=None,
                                 patch_method=None,
                                 msg=None):
        """
        This method is gather common test pattern used in the following
        three test cases.
        """
        m_self = mock.Mock(spec=sources.FileSource)
        m_self.progress = mock.Mock()
        m_self.path = 'foo'
        m_self.output_format = output_format
        dest = 'bar'

        with mock.patch.multiple('os.path',
                                 isfile=mock.DEFAULT,
                                 realpath=mock.DEFAULT) as m_path:
            m_path['isfile'].return_value = True
            with self.assertRaises(Exception) as err:
                if patch_method:
                    with mock.patch(patch_method) as mocked_method:
                        mocked_method.side_effect = side_effect
                        sources.FileSource.unpack(m_self, dest)
                else:
                    sources.FileSource.unpack(m_self, dest)
        if msg:
            self.assertEqual(msg, str(err.exception))

    def test_unpack_invalid_format_raise_exception(self):
        """
        Ensures that unpack() throws an Exception when called with
        invalid output format.
        """
        self._unpack_raise_error_test('foo', msg='Unknown format:foo')

    def test_unpack_raise_error_if_untar_fail(self):
        """
        Ensures that unpack() throws an Exception when safe_untar()
        fails.
        """
        msg = 'Caught untar failure'
        patch_method = 'virtBootstrap.utils.safe_untar'
        self._unpack_raise_error_test(output_format='dir',
                                      side_effect=Exception(msg),
                                      patch_method=patch_method,
                                      msg=msg)

    def test_unpack_raise_error_if_extract_in_qcow2_fail(self):
        """
        Ensures that unpack() throws an Exception when create_qcow2()
        fails.
        """
        msg = 'Caught extract_layers_in_qcow2 failure'
        patch_method = 'virtBootstrap.utils.create_qcow2'
        self._unpack_raise_error_test(output_format='qcow2',
                                      side_effect=Exception(msg),
                                      patch_method=patch_method,
                                      msg=msg)
