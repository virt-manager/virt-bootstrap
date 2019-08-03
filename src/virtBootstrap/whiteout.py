# -*- coding: utf-8 -*-
# Authors: Radostin Stoyanov <rstoyanov1@gmail.com>
#
# Copyright (c) 2019 Radostin Stoyanov
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
Whiteouts are files with a special meaning for a layered filesystem.
They should not be extracted in the destination directory.

Whiteout prefix (.wh.) followed by a filename means that the file
has been removed.
"""

import logging
import os
import shutil
import tarfile


PREFIX = ".wh."
METAPREFIX = PREFIX + PREFIX
OPAQUE = METAPREFIX + ".opq"

# pylint: disable=invalid-name
logger = logging.getLogger(__name__)


def apply_whiteout_changes(tar_file, dest_dir):
    """
    Process files with whiteout prefix and apply
    changes in destination folder.
    """
    for path in get_whiteout_files(tar_file):
        basename = os.path.basename(path)
        dirname = os.path.dirname(path)
        dirname = os.path.join(dest_dir, dirname)

        process_whiteout(dirname, basename)


def get_whiteout_files(filepath):
    """
    Return a list of whiteout files from tar file
    """
    whiteout_files = []
    with tarfile.open(filepath) as tar:
        for path in tar.getnames():
            if os.path.basename(path).startswith(PREFIX):
                whiteout_files.append(path)
    return whiteout_files


def process_whiteout(dirname, basename):
    """
    Process a whiteout file:

    .wh.PATH     : PATH should be deleted
    .wh..wh..opq : all children (including sub-directories and all
                   descendants) of the folder containing this file
                   should be removed

    When a folder is first created in a layer an opq file will be
    generated. In such case, there is nothing to remove we can simply
    ignore the opque whiteout file.
    """
    if basename == OPAQUE:
        if os.path.isdir(dirname):
            shutil.rmtree(dirname)
            os.makedirs(dirname)
    elif not basename.startswith(METAPREFIX):
        target = os.path.join(dirname, basename[len(PREFIX):])
        if os.path.isfile(target):
            os.remove(target)
        elif os.path.isdir(target):
            shutil.rmtree(target)
        else:
            logger.error("%s is not a file or directory", target)
