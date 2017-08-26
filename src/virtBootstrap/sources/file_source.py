# Authors: Cedric Bosdonnat <cbosdonnat@suse.com>
#
# Copyright (C) 2017 SUSE, Inc.
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
FileSource aim is to extract root filesystem from tar archive to destination
directory or qcow2 image.
"""

import os
import logging

from virtBootstrap import utils


# pylint: disable=invalid-name
# Create logger
logger = logging.getLogger(__name__)


class FileSource(object):
    """
    Extract root filesystem from file.
    """
    def __init__(self, **kwargs):
        """
        Bootstrap root filesystem from tarball

        @param uri: Path to tar archive file.
        @param fmt: Format used to store image [dir, qcow2]
        @param progress: Instance of the progress module
        """
        self.path = kwargs['uri'].path
        self.output_format = kwargs.get('fmt', utils.DEFAULT_OUTPUT_FORMAT)
        self.progress = kwargs['progress'].update_progress

    def unpack(self, dest):
        """
        Safely extract root filesystem from tarball

        @param dest: Directory path where the files to be extraced
        """

        if not os.path.isfile(self.path):
            raise Exception('Invalid file source "%s"' % self.path)

        layer = [[self.path, os.path.getsize(self.path)]]
        if self.output_format == 'dir':
            self.progress("Extracting files into destination directory",
                          value=0, logger=logger)
            utils.untar_layers(layer, dest, self.progress)

        elif self.output_format == 'qcow2':
            # Remove the old path
            file_name = os.path.basename(self.path)
            qcow2_file = os.path.realpath('{}/{}.qcow2'.format(dest,
                                                               file_name))

            self.progress("Extracting files into qcow2 image", value=0,
                          logger=logger)
            utils.create_qcow2(self.path, qcow2_file)
        else:
            raise Exception("Unknown format:" + self.output_format)

        self.progress("Extraction completed successfully!", value=100,
                      logger=logger)
        logger.info("Files are stored in: " + dest)
