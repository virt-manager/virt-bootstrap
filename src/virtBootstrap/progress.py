# -*- coding: utf-8 -*-
# Authors:
#   Cedric Bosdonnat <cbosdonnat@suse.com>
#   Radostin Stoyanov <rstoyanov1@gmail.com>
#
# Copyright (c) 2017 Radostin Stoyanov
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
Store the progress of virt-bootstrap
"""


class Progress(object):
    """
    Store progress status and value of virt-bootstrap and
    inform callback method about change.
    """

    def __init__(self, callback=None):
        """
        If callback method is passed it will be called when the progress
        value has been changed.
        """
        self.progress = {'status': '', 'value': 0}
        self.callback = callback

    def get_progress(self):
        """
        Return "state" and "value" of the progress in python dictionary.
        """
        return self.progress.copy()

    def update_progress(self, status=None, value=None, logger=None):
        """
        Set status/value and call the callback method if available.
        Log information message if logger instance was passed.

        @param status: String representing the current state of virt-bootstrap.
        @param value: The new progress value of virt-bootstrap.
        @param logger: Reference to logger. If passed info message with
                       including the status will be logged.
        """
        # Note: We do not validate the values stored in progress
        if isinstance(status, str):
            self.progress['status'] = status
        if isinstance(value, (float, int)):
            self.progress['value'] = value

        try:
            if logger is not None:
                logger.info(status)
            if self.callback is not None:
                self.callback(self.get_progress())
        except Exception as err:
            raise ValueError("Progress update has failed.", err)
