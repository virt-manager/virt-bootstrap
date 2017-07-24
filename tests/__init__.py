"""
    Test suite for virt-bootstrap

    Authors: Radostin Stoyanov <rstoyanov1@gmail.com>

    Copyright (C) 2017 Radostin Stoyanov

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import sys
import unittest

try:
    import mock
except ImportError:
    import unittest.mock as mock

sys.path += '../src'  # noqa: E402

# pylint: disable=import-error
from virtBootstrap import virt_bootstrap
from virtBootstrap import sources
from virtBootstrap import progress
from virtBootstrap import utils

__all__ = ['unittest', 'mock',
           'virt_bootstrap', 'sources', 'progress', 'utils']
