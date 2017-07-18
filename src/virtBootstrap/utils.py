# Authors:
#   Cedric Bosdonnat <cbosdonnat@suse.com>
#   Radostin Stoyanov <rstoyanov1@gmail.com>
#
# Copyright (C) 2017 SUSE, Inc.
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
Module which contains utility functions used by virt-bootstrap.
"""

import errno
import fcntl
import hashlib
import json
import os
import sys
import tempfile
import logging

from subprocess import CalledProcessError, PIPE, Popen

# pylint: disable=invalid-name
# Create logger
logger = logging.getLogger(__name__)
# Default virtual size of qcow2 image
DEF_QCOW2_SIZE = '5G'
if os.geteuid() == 0:
    LIBVIRT_CONN = "lxc:///"
    DEFAULT_IMG_DIR = "/var/lib/virt-bootstrap/docker_images"
else:
    LIBVIRT_CONN = "qemu:///session"
    DEFAULT_IMG_DIR = os.environ['HOME']
    DEFAULT_IMG_DIR += "/.local/share/virt-bootstrap/docker_images"


def checksum(path, sum_type, sum_expected):
    """
    Validate file using checksum.
    """
    algorithm = getattr(hashlib, sum_type)
    try:
        handle = open(path, 'rb')
        content = handle.read()
        handle.close()

        actual = algorithm(content).hexdigest()
        if not actual == sum_expected:
            logger.warning("File '%s' has invalid hash sum.\nExpected: %s\n"
                           "Actual: %s", path, sum_expected, actual)
            return False
        return True
    except Exception as err:
        logger.warning("Error occured while validating "
                       "the hash sum of file: %s\n%s", path, err)
        return False


def execute(cmd):
    """
    Execute command and log debug message.
    """
    cmd_str = ' '.join(cmd)
    logger.debug("Call command:\n%s", cmd_str)

    proc = Popen(cmd, stdout=PIPE, stderr=PIPE)
    output, err = proc.communicate()

    if output:
        logger.debug("Stdout:\n%s", output)
    if err:
        logger.debug("Stderr:\n%s", err)

    if proc.returncode != 0:
        raise CalledProcessError(proc.returncode, cmd_str)


def safe_untar(src, dest):
    """
    Extract tarball within LXC container for safety.
    """
    virt_sandbox = ['virt-sandbox',
                    '-c', LIBVIRT_CONN,
                    '-m', 'host-bind:/mnt=' + dest]  # Bind destination folder

    # Compression type is auto detected from tar
    # Exclude files under /dev to avoid "Cannot mknod: Operation not permitted"
    params = ['--', '/bin/tar', 'xf', src, '-C', '/mnt', '--exclude', 'dev/*']
    execute(virt_sandbox + params)


def bytes_to_size(number):
    """
    Turn numbers into human-readable metric-like numbers
    """
    symbols = ['', 'KiB', 'MiB', 'GiB']
    step = 1024.0
    thresh = 999
    depth = 0
    max_depth = len(symbols) - 1

    while number > thresh and depth < max_depth:
        depth = depth + 1
        number = number / step

    if int(number) == float(number):
        fmt = '%i %s'
    else:
        fmt = '%.2f %s'

    return(fmt % (number or 0, symbols[depth])).strip()


def size_to_bytes(number, fmt):
    """
    Convert human readable formats to bytes.
    """
    formats = {'B': 0, 'KB': 1, 'MB': 2, 'GB': 3, 'TB': 4}
    return (int(number) * pow(1024, formats[fmt.upper()]) if fmt in formats
            else False)


def log_layer_extract(layer, current, total, progress):
    """
    Create log message on layer extract.
    """
    sum_type, sum_value, layer_file, layer_size = layer
    progress("Extracting layer (%s/%s) with size: %s"
             % (current, total, bytes_to_size(layer_size)), logger=logger)
    logger.debug('Untar layer: (%s:%s) %s', sum_type, sum_value, layer_file)


def untar_layers(layers_list, dest_dir, progress):
    """
    Untar each of layers from container image.
    """
    nlayers = len(layers_list)
    for index, layer in enumerate(layers_list):
        log_layer_extract(layer, index + 1, nlayers, progress)
        layer_file = layer[2]

        # Extract layer tarball into destination directory
        safe_untar(layer_file, dest_dir)

        # Update progress value
        progress(value=(float(index + 1) / nlayers * 50) + 50)


def get_mime_type(path):
    """
        Get the mime type of a file.
    """
    return Popen(["/usr/bin/file", "--mime-type", path],
                 stdout=PIPE).communicate()[0].split()[1]


def create_qcow2(tar_file, layer_file, backing_file=None, size=DEF_QCOW2_SIZE):
    """
    Create qcow2 image from tarball.
    """
    qemu_img_cmd = ["qemu-img", "create", "-f", "qcow2", layer_file, size]

    if not backing_file:
        logger.info("Creating base qcow2 image")
        execute(qemu_img_cmd)

        logger.info("Formatting qcow2 image")
        execute(['virt-format',
                 '--format=qcow2',
                 '--partition=none',
                 '--filesystem=ext3',
                 '-a', layer_file])
    else:
        # Add backing chain
        qemu_img_cmd.insert(2, "-b")
        qemu_img_cmd.insert(3, backing_file)

        logger.info("Creating qcow2 image with backing chain")
        execute(qemu_img_cmd)

    # Get mime type of archive
    mime_tar_file = get_mime_type(tar_file)
    logger.debug("Detected mime type of archive: %s", mime_tar_file)

    # Extract tarball using "tar-in" command from libguestfs
    tar_in_cmd = ["guestfish",
                  "-a", layer_file,
                  '-m', '/dev/sda',
                  'tar-in', tar_file, "/"]

    compression_fmts = {'x-gzip': 'gzip', 'gzip': 'gzip',
                        'x-xz': 'xz',
                        'x-bzip2': 'bzip2',
                        'x-compress': 'compress',
                        'x-lzop': 'lzop'}

    # Check if tarball is compressed
    mime_parts = mime_tar_file.split('/')
    if mime_parts[0] == 'application' and \
       mime_parts[1] in compression_fmts:
        tar_in_cmd.append('compress:' + compression_fmts[mime_parts[1]])

    # Execute virt-tar-in command
    execute(tar_in_cmd)


def extract_layers_in_qcow2(layers_list, dest_dir, progress):
    """
    Extract docker layers in qcow2 images with backing chains.
    """
    qcow2_backing_file = None

    nlayers = len(layers_list)
    for index, layer in enumerate(layers_list):
        log_layer_extract(layer, index + 1, nlayers, progress)
        tar_file = layer[2]

        # Name format for the qcow2 image
        qcow2_layer_file = "{}/layer-{}.qcow2".format(dest_dir, index)
        # Create the image layer
        create_qcow2(tar_file, qcow2_layer_file, qcow2_backing_file)
        # Keep the file path for the next layer
        qcow2_backing_file = qcow2_layer_file

        # Update progress value
        progress(value=(float(index + 1) / nlayers * 50) + 50)


def get_image_dir(no_cache=False):
    """
    Get the directory where image layers are stored.

    @param no_cache: Boolean, indicates whether to use temporary directory
    """
    if no_cache:
        return tempfile.mkdtemp('virt-bootstrap')

    if not os.path.exists(DEFAULT_IMG_DIR):
        os.makedirs(DEFAULT_IMG_DIR)

    return DEFAULT_IMG_DIR


def get_image_details(src, raw=False,
                      insecure=False, username=False, password=False):
    """
    Return details of container image from "skopeo inspect" commnad.
    """
    cmd = ['skopeo', 'inspect', src]
    if raw:
        cmd.append('--raw')
    if insecure:
        cmd.append('--tls-verify=false')
    if username and password:
        cmd.append("--creds=%s:%s" % (username, password))
    proc = Popen(cmd, stdout=PIPE, stderr=PIPE)
    output, error = proc.communicate()
    if error:
        raise ValueError("Image could not be retrieved:", error)
    return json.loads(output)


def is_new_layer_message(line):
    """
    Return T/F whether a line in skopeo's progress is indicating
    start the process of new image layer.

    Reference:
    - https://github.com/containers/image/blob/master/copy/copy.go#L464
    - https://github.com/containers/image/blob/master/copy/copy.go#L459
    """
    return line.startswith('Copying blob') or line.startswith('Skipping fetch')


def is_layer_config_message(line):
    """
    Return T/F indicating whether the message from skopeo copies the manifest
    file.

    Reference:
    - https://github.com/containers/image/blob/master/copy/copy.go#L414
    """
    return line.startswith('Copying config')


def make_async(fd):
    """
    Add the O_NONBLOCK flag to a file descriptor.
    """
    fcntl.fcntl(fd, fcntl.F_SETFL,
                fcntl.fcntl(fd, fcntl.F_GETFL) | os.O_NONBLOCK)


def read_async(fd):
    """
    Read some data from a file descriptor, ignoring EAGAIN errors
    """
    try:
        return fd.read()
    except IOError as e:
        if e.errno != errno.EAGAIN:
            raise
        else:
            return ''


def str2float(element):
    """
    Convert string to float or return None.
    """
    try:
        return float(element)
    except ValueError:
        return None


def write_progress(prog):
    """
    Write progress output to console
    """
    # Get terminal width
    try:
        terminal_width = int(Popen(["stty", "size"], stdout=PIPE).stdout
                             .read().split()[1])
    except Exception:
        terminal_width = 80
    # Prepare message
    msg = "\rStatus: %s, Progress: %.2f%%" % (prog['status'], prog['value'])
    # Fill with whitespace and return cursor at the begging
    msg = "%s\r" % msg.ljust(terminal_width)
    # Write message to console
    sys.stdout.write(msg)
    sys.stdout.flush()
