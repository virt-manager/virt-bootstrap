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
Unit tests for functions defined in virtBootstrap.utils
"""
import unittest
from . import utils


# pylint: disable=invalid-name
class TestUtils(unittest.TestCase):
    """
    Ensures that functions defined in the utils module of virtBootstrap
    work as expected.
    """
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

        proc = utils.subprocess.Popen(
            ["echo"],
            stdout=utils.subprocess.PIPE
        )
        pipe = proc.stdout

        fd = pipe.fileno()
        F_GETFL = utils.fcntl.F_GETFL
        O_NONBLOCK = utils.os.O_NONBLOCK

        self.assertFalse(utils.fcntl.fcntl(fd, F_GETFL) & O_NONBLOCK)
        utils.make_async(fd)
        self.assertTrue(utils.fcntl.fcntl(fd, F_GETFL) & O_NONBLOCK)
        proc.wait()
        pipe.close()

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
