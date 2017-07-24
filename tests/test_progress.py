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
Unit tests for methods defined in virtBootstrap.progress
"""

from tests import unittest
from tests import mock
from tests import progress


# pylint: disable=invalid-name
class TestFileSource(unittest.TestCase):
    """
    Test cases for Progress module
    """

    ###################################
    # Tests for: __init__()
    ###################################
    def test_progress_init(self):
        """
        Ensures that __init__() assigns the collback value to instance
        variable and creates dictionary with 'status', 'value' keys.
        """
        callback = mock.Mock()
        test_instance = progress.Progress(callback)
        for key in ['status', 'value']:
            self.assertIn(key, test_instance.progress)
        self.assertIs(callback, test_instance.callback)

    ###################################
    # Tests for: get_progress()
    ###################################
    def test_get_progress(self):
        """
        Ensures that get_progress() returns copy of the progress dictionary
        which has the same keys and values.
        """
        test_instance = progress.Progress()
        test_result = test_instance.get_progress()
        self.assertIsNot(test_instance.progress, test_result)
        self.assertDictEqual(test_instance.progress, test_result)

    ###################################
    # Tests for: update_progress()
    ###################################
    def test_update_progress_creates_log_record(self):
        """
        Ensures that update_progress() creates log record with info level
        and pass the status value as message.
        """
        test_instance = progress.Progress()
        logger = mock.Mock()
        status = "Test"
        test_instance.update_progress(status=status, logger=logger)
        logger.info.assert_called_once_with(status)

    def test_update_progress_update_status_and_value(self):
        """
        Ensures that update_progress() creates log record with info level
        and pass the status value as message.
        """
        test_instance = progress.Progress()
        test_instance.progress = {'status': '', 'value': 0}
        new_status = 'Test'
        new_value = 100
        new_progress = {'status': new_status, 'value': new_value}
        test_instance.update_progress(status=new_status, value=new_value)
        self.assertDictEqual(test_instance.progress, new_progress)

    def test_update_progress_update_raise_logger_error(self):
        """
        Ensures that update_progress() raise ValueError when creating
        log record has failed.
        """
        msg = 'test'
        test_instance = progress.Progress()
        logger = mock.Mock()
        logger.info.side_effect = Exception(msg)
        with self.assertRaises(ValueError) as err:
            test_instance.update_progress(logger=logger)
        self.assertIn(msg, str(err.exception))

    def test_update_progress_update_raise_callback_error(self):
        """
        Ensures that update_progress() raise ValueError when calling
        callback failed.
        """
        msg = 'test'
        callback = mock.Mock()
        callback.side_effect = Exception(msg)
        test_instance = progress.Progress(callback)
        with self.assertRaises(ValueError) as err:
            test_instance.update_progress('foo', 'bar')
        self.assertIn(msg, str(err.exception))
