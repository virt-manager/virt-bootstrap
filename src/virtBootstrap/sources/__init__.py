# -*- coding: utf-8 -*-
# Authors:
#    Radostin Stoyanov <rstoyanov1@gmail.com>

# Copyright (c) 2017 Radostin Stoyanov

#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.

#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.

#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
Class definitions which process container images and extract the root
file system to destination directory or convert them to qcow2 disk images with
backing chains.
"""

from virtBootstrap.sources.file_source import FileSource
from virtBootstrap.sources.docker_source import DockerSource
from virtBootstrap.sources.virt_builder_source import VirtBuilderSource
