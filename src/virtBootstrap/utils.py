# -*- coding: utf-8 -*-
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
import subprocess
import sys
import tempfile
import logging

import passlib.hosts

try:
    import guestfs
except ImportError:
    raise RuntimeError('Python bindings for libguestfs are not installed')


# pylint: disable=invalid-name
# Create logger
logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_FORMAT = 'dir'
# Default virtual size of qcow2 image
DEF_QCOW2_SIZE = '5G'
DEF_BASE_IMAGE_SIZE = 5 * 1024 * 1024 * 1024

if os.geteuid() == 0:
    LIBVIRT_CONN = "lxc:///"
    DEFAULT_IMG_DIR = "/var/cache/virt-bootstrap/docker_images"
else:
    LIBVIRT_CONN = "qemu:///session"
    if 'XDG_CACHE_HOME' in os.environ:
        DEFAULT_IMG_DIR = os.environ['XDG_CACHE_HOME']
    else:
        DEFAULT_IMG_DIR = os.environ['HOME'] + '/.cache'
    DEFAULT_IMG_DIR += '/virt-bootstrap/docker_images'

# Set temporary directory
tmp_dir = os.environ.get('VIRTBOOTSTRAP_TMPDIR', '/tmp')
if not os.path.exists(tmp_dir):
    os.makedirs(tmp_dir)
tempfile.tempdir = tmp_dir


class BuildImage(object):
    """
    Use guestfs-python to create qcow2 disk images.
    """

    def __init__(self, layers, dest, progress):
        """
        @param tar_files: Tarballs to be converted to qcow2 images
        @param dest: Directory where the qcow2 images will be created
        @param progress: Instance of the progress module

        Note: uid_map and gid_map have the format:
            [[<start>, <target>, <count>], [<start>, <target>, <count>] ...]
        """
        self.g = guestfs.GuestFS(python_return_dict=True)
        self.layers = layers
        self.nlayers = len(layers)
        self.dest = dest
        self.progress = progress
        self.qcow2_files = []

    def create_base_layer(self, fmt='qcow2', size=DEF_BASE_IMAGE_SIZE):
        """
        Create and format qcow2 disk image which represnts the base layer.
        """
        self.qcow2_files = [os.path.join(self.dest, 'layer-0.qcow2')]
        self.progress("Creating base layer", logger=logger)
        self.g.disk_create(self.qcow2_files[0], fmt, size)
        self.g.add_drive(self.qcow2_files[0], format=fmt)
        self.g.launch()
        self.progress("Formating disk image", logger=logger)
        self.g.mkfs("ext3", '/dev/sda')
        self.extract_layer(0, '/dev/sda')
        # Shutdown qemu instance to avoid hot-plugging of devices.
        self.g.shutdown()

    def create_backing_chains(self):
        """
        Convert other layers to qcow2 images linked as backing chains.
        """
        for i in range(1, self.nlayers):
            self.qcow2_files.append(
                os.path.join(self.dest, 'layer-%d.qcow2' % i)
            )
            self.progress(
                "Creating image (%d/%d)" % (i + 1, self.nlayers),
                logger=logger
            )
            self.g.disk_create(
                filename=self.qcow2_files[i],
                format='qcow2',
                size=-1,
                backingfile=self.qcow2_files[i - 1],
                backingformat='qcow2'
            )
            self.g.add_drive(self.qcow2_files[i], format='qcow2')
            self.g.launch()

            devices = self.g.list_devices()
            self.extract_layer(i, devices[0])
            self.g.shutdown()

    def extract_layer(self, index, dev):
        """
        Extract tarball of layer to device
        """
        tar_file, tar_size = self.layers[index]
        log_layer_extract(
            tar_file, tar_size, index + 1, self.nlayers, self.progress
        )
        self.tar_in(dev, tar_file)

    def tar_in(self, dev, tar_file):
        """
        Common pattern used to tar-in archive into image
        """
        self.g.mount(dev, '/')
        # Restore extended attributes, SELinux contexts and POSIX ACLs
        # from tar file.
        self.g.tar_in(tar_file, '/', get_compression_type(tar_file),
                      xattrs=True, selinux=True, acls=True)
        self.g.umount('/')

    def set_root_password(self, root_password):
        """
        Set root password within new layer
        """
        if not root_password:
            return

        self.progress("Setting root password", logger=logger)
        img_file = os.path.join(self.dest, 'layer-%s.qcow2' % self.nlayers)
        self.g.disk_create(
            filename=img_file,
            format='qcow2',
            size=-1,
            backingfile=self.qcow2_files[-1],
            backingformat='qcow2'
        )
        self.g.add_drive(img_file, format='qcow2')
        self.g.launch()
        self.g.mount('/dev/sda', '/')
        success = False
        if self.g.is_file('/etc/shadow'):
            shadow_content = self.g.read_file('/etc/shadow')
            if hasattr(shadow_content, 'decode'):
                shadow_content = shadow_content.decode('utf-8')
            shadow_content = shadow_content.split('\n')
            if shadow_content:
                # Note: 'shadow_content' is a list, pass-by-reference is used
                set_password_in_shadow_content(shadow_content, root_password)
                self.g.write('/etc/shadow', '\n'.join(shadow_content))
                success = True
            else:
                logger.error('shadow file is empty')
        else:
            logger.error('shadow file was not found')

        self.g.umount('/')
        self.g.shutdown()

        if not success:
            self.progress("Removing root password layer", logger=logger)
            os.remove(img_file)


def get_compression_type(tar_file):
    """
    Get compression type of tar file.
    """
    # Get mime type of archive
    mime_tar_file = get_mime_type(tar_file)
    logger.debug("Detected mime type of archive: %s", mime_tar_file)

    compression_fmts = {
        'x-gzip': 'gzip',
        'gzip': 'gzip',
        'x-xz': 'xz',
        'x-bzip2': 'bzip2',
        'x-compress': 'compress',
        'x-lzop': 'lzop'
    }

    # Check if tarball is compressed
    mime_type, mime_subtype = mime_tar_file.split('/')
    if mime_type == 'application' and mime_subtype in compression_fmts:
        return compression_fmts[mime_subtype]
    return None


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

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    output, err = proc.communicate()

    if output:
        logger.debug("Stdout:\n%s", output.decode('utf-8'))
    if err:
        logger.debug("Stderr:\n%s", err.decode('utf-8'))

    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd_str)


def safe_untar(src, dest):
    """
    Extract tarball within LXC container for safety.
    """
    virt_sandbox = ['virt-sandbox',
                    '-c', LIBVIRT_CONN,
                    '--name=bootstrap_%s' % os.getpid(),
                    '-m', 'host-bind:/mnt=' + dest]  # Bind destination folder

    # Compression type is auto detected from tar
    # Exclude files under /dev to avoid "Cannot mknod: Operation not permitted"
    # Note: Here we use --absolute-names flag to get around the error message
    # "Cannot open: Permission denied" when symlynks are extracted, with the
    # qemu:/// driver. This flag must not be used outside virt-sandbox.
    params = ['--', '/bin/tar', 'xf', src, '-C', '/mnt', '--exclude', 'dev/*',
              '--overwrite', '--absolute-names']
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


def log_layer_extract(tar_file, tar_size, current, total, progress):
    """
    Create log message on layer extract.
    """
    msg = 'Extracting layer (%s/%s) with size: %s' % (
        current,
        total,
        bytes_to_size(tar_size or os.path.getsize(tar_file))
    )
    progress(msg, logger=logger)
    logger.debug('Untar layer: %s', tar_file)


def untar_layers(layers_list, dest_dir, progress):
    """
    Untar each of layers from container image.
    """
    nlayers = len(layers_list)
    for index, layer in enumerate(layers_list):
        tar_file, tar_size = layer
        log_layer_extract(tar_file, tar_size, index + 1, nlayers, progress)

        # Extract layer tarball into destination directory
        safe_untar(tar_file, dest_dir)

        # Update progress value
        progress(value=(float(index + 1) / nlayers * 50) + 50)


def get_mime_type(path):
    """
    Get the mime type of a file.
    """
    proc = subprocess.Popen(
        ["/usr/bin/file", "--mime-type", path],
        stdout=subprocess.PIPE
    )
    proc.wait()
    with proc.stdout as output:
        return output.read().decode('utf-8').split()[1]


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
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    output, error = proc.communicate()
    if error:
        raise ValueError("Image could not be retrieved:",
                         error.decode('utf-8'))
    return json.loads(output.decode('utf-8'))


def is_new_layer_message(line):
    """
    Return T/F whether a line in skopeo's progress is indicating
    start the process of new image layer.
    """
    return line.startswith('Copying blob') or line.startswith('Skipping fetch')


def is_layer_config_message(line):
    """
    Return T/F indicating whether the message from skopeo copies the manifest
    file.
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


def set_password_in_shadow_content(shadow_content, password, user='root'):
    """
    Find a user the content of shadow file and set a hash of the password.
    """
    for index, line in enumerate(shadow_content):
        if line.startswith(user):
            line_split = line.split(':')
            line_split[1] = passlib.hosts.linux_context.hash(password)
            shadow_content[index] = ':'.join(line_split)
            break
    return shadow_content


def set_root_password_in_rootfs(rootfs, password):
    """
    Set password on the root user within root filesystem
    """
    shadow_file = os.path.join(rootfs, "etc/shadow")

    shadow_file_permissions = os.stat(shadow_file)[0]
    # Set read-write permissions to shadow file
    os.chmod(shadow_file, 0o666)
    try:
        with open(shadow_file) as orig_file:
            shadow_content = orig_file.read().split('\n')

        new_content = set_password_in_shadow_content(shadow_content, password)

        with open(shadow_file, "w") as new_file:
            new_file.write('\n'.join(new_content))

    except Exception:
        raise

    finally:
        # Restore original permissions
        os.chmod(shadow_file, shadow_file_permissions)


def write_progress(prog):
    """
    Write progress output to console
    """
    # Get terminal width
    try:
        terminal_width = int(
            subprocess.Popen(
                ["stty", "size"],
                stdout=subprocess.PIPE
            ).stdout.read().decode('utf-8').split()[1]
        )
    except Exception:
        terminal_width = 80
    # Prepare message
    msg = "\rStatus: %s, Progress: %.2f%%" % (prog['status'], prog['value'])
    # Fill with whitespace and return cursor at the begging
    msg = "%s\r" % msg.ljust(terminal_width)
    # Write message to console
    sys.stdout.write(msg)
    sys.stdout.flush()


# The implementation for remapping ownership of all files inside a
# container's rootfs is inspired by the tool uidmapshift:
#
# Original author: Serge Hallyn <serge.hallyn@ubuntu.com>
# Original license: GPLv2
# http://bazaar.launchpad.net/%7Eserge-hallyn/+junk/nsexec/view/head:/uidmapshift.c

def get_map_id(old_id, opts):
    """
    Calculate new map_id.
    """
    if old_id >= opts['first'] and old_id < opts['last']:
        return old_id + opts['offset']
    return -1


def get_mapping_opts(mapping):
    """
    Get range options from UID/GID mapping
    """
    start = mapping[0] if mapping[0] > -1 else 0
    target = mapping[1] if mapping[1] > -1 else 0
    count = mapping[2] if mapping[2] > -1 else 1

    opts = {
        'first': start,
        'last': start + count,
        'offset': target - start
    }
    return opts


def map_id(path, map_uid, map_gid):
    """
    Remapping ownership of all files inside a container's rootfs.

    map_gid and map_uid: Contain integers in a list with format:
        [<start>, <target>, <count>]
    """
    if map_uid:
        uid_opts = get_mapping_opts(map_uid)
    if map_gid:
        gid_opts = get_mapping_opts(map_gid)

    for root, _ignore, files in os.walk(os.path.realpath(path)):
        for name in [root] + files:
            file_path = os.path.join(root, name)

            stat_info = os.lstat(file_path)
            old_uid = stat_info.st_uid
            old_gid = stat_info.st_gid

            new_uid = get_map_id(old_uid, uid_opts) if map_uid else -1
            new_gid = get_map_id(old_gid, gid_opts) if map_gid else -1
            os.lchown(file_path, new_uid, new_gid)


def guestfs_walk(rootfs_tree, g, path='/'):
    """
    File system walk for guestfs
    """
    stat = g.lstat(path)
    rootfs_tree[path] = {'uid': stat['uid'], 'gid': stat['gid']}
    for member in g.ls(path):
        m_path = os.path.join(path, member)
        if g.is_dir(m_path):
            guestfs_walk(rootfs_tree, g, m_path)
        else:
            stat = g.lstat(m_path)
            rootfs_tree[m_path] = {'uid': stat['uid'], 'gid': stat['gid']}


def apply_mapping_in_image(uid, gid, rootfs_tree, g):
    """
    Apply mapping of new ownership
    """
    if uid:
        uid_opts = get_mapping_opts(uid)
    if gid:
        gid_opts = get_mapping_opts(gid)

    for member in rootfs_tree:
        old_uid = rootfs_tree[member]['uid']
        old_gid = rootfs_tree[member]['gid']

        new_uid = get_map_id(old_uid, uid_opts) if uid else -1
        new_gid = get_map_id(old_gid, gid_opts) if gid else -1
        if new_uid != -1 or new_gid != -1:
            g.lchown(new_uid, new_gid, os.path.join('/', member))


def map_id_in_image(nlayers, dest, map_uid, map_gid, new_disk=True):
    """
    Create additional layer in which UID/GID mipping is applied.

    map_gid and map_uid have the format:
        [[<start>, <target>, <count>], [<start>, <target>, <count>], ...]
    """

    g = guestfs.GuestFS(python_return_dict=True)
    last_layer = os.path.join(dest, "layer-%d.qcow2" % (nlayers - 1))
    additional_layer = os.path.join(dest, "layer-%d.qcow2" % nlayers)
    # Add the last layer as readonly
    g.add_drive_opts(last_layer, format='qcow2', readonly=True)
    if new_disk:
        # Create the additional layer
        g.disk_create(
            filename=additional_layer,
            format='qcow2',
            size=-1,
            backingfile=last_layer,
            backingformat='qcow2'
        )
    g.add_drive(additional_layer, format='qcow2')
    g.launch()
    g.mount('/dev/sda', '/')
    rootfs_tree = dict()
    guestfs_walk(rootfs_tree, g)
    g.umount('/')
    g.mount('/dev/sdb', '/')

    balance_uid_gid_maps(map_uid, map_gid)
    for uid, gid in zip(map_uid, map_gid):
        apply_mapping_in_image(uid, gid, rootfs_tree, g)

    g.umount('/')
    g.shutdown()


def balance_uid_gid_maps(uid_map, gid_map):
    """
    Make sure the UID/GID list of mappings have the same length.
    """
    len_diff = len(uid_map) - len(gid_map)

    if len_diff < 0:
        uid_map += [None] * abs(len_diff)
    elif len_diff > 0:
        gid_map += [None] * len_diff


def mapping_uid_gid(dest, uid_map, gid_map):
    """
    Mapping ownership for each uid_map and gid_map.
    """
    balance_uid_gid_maps(uid_map, gid_map)
    for uid, gid in zip(uid_map, gid_map):
        map_id(dest, uid, gid)


def is_installed(program):
    """
    Try to find executable listed in the PATH env variable.

    Returns the complete filename or None if not found.
    """
    for path in os.environ["PATH"].split(os.pathsep):
        exec_file = os.path.join(path, program)
        if os.path.isfile(exec_file) and os.access(exec_file, os.X_OK):
            return exec_file
    return None
