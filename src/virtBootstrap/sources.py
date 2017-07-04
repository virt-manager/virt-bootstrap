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
Class definitions which process container image or
archive from source and unpack them in destination directory.
"""

import hashlib
import json
import shutil
import tempfile
import getpass
import os
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
        return actual == sum_expected
    except Exception:
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


def get_layer_info(digest, image_dir):
    """
    Get checksum type/value and path to corresponding tarball.
    """
    sum_type, sum_value = digest.split(':')
    layer_file = "{}/{}.tar".format(image_dir, sum_value)
    return (sum_type, sum_value, layer_file)


def untar_layers(layers_list, image_dir, dest_dir):
    """
    Untar each of layers from container image.
    """
    for index, layer in enumerate(layers_list):
        logger.info("Extracting layer (%s/%s)", index+1, len(layers_list))

        sum_type, sum_value, layer_file = get_layer_info(layer['digest'],
                                                         image_dir)
        logger.debug('Untar layer file: (%s) %s', sum_type, layer_file)

        # Verify the checksum
        if not checksum(layer_file, sum_type, sum_value):
            raise Exception("Digest not matching: " + layer['digest'])

        # Extract layer tarball into destination directory
        safe_untar(layer_file, dest_dir)


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


def extract_layers_in_qcow2(layers_list, image_dir, dest_dir):
    """
    Extract docker layers in qcow2 images with backing chains.
    """
    qcow2_backing_file = None

    for index, layer in enumerate(layers_list):
        logger.info("Extracting layer (%s/%s)", index+1, len(layers_list))

        # Get layer file information
        sum_type, sum_value, tar_file = get_layer_info(layer['digest'],
                                                       image_dir)

        logger.debug('Untar layer file: (%s) %s', sum_type, tar_file)

        # Verify the checksum
        if not checksum(tar_file, sum_type, sum_value):
            raise Exception("Digest not matching: " + layer['digest'])

        # Name format for the qcow2 image
        qcow2_layer_file = "{}/layer-{}.qcow2".format(dest_dir, index)
        # Create the image layer
        create_qcow2(tar_file, qcow2_layer_file, qcow2_backing_file)
        # Keep the file path for the next layer
        qcow2_backing_file = qcow2_layer_file


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


def get_image_details(src, raw=False):
    """
    Return details of container image from "skopeo inspect" commnad.
    """
    cmd = ['skopeo', 'inspect', src]
    if raw:
        cmd.append('--raw')
    proc = Popen(cmd, stdout=PIPE, stderr=PIPE)
    output, error = proc.communicate()
    if error:
        raise ValueError("Image could not be retrieved:", error)
    return json.loads(output)


class FileSource(object):
    """
    Extract root filesystem from file.
    """
    def __init__(self, **kwargs):
        self.path = kwargs['uri'].path
        self.output_format = kwargs['fmt']

    def unpack(self, dest):
        """
        Safely extract root filesystem from tarball

        @param dest: Directory path where the files to be extraced
        """

        if not os.path.isfile(self.path):
            raise Exception('Invalid file source "%s"' % self.path)

        if self.output_format == 'dir':
            logger.info("Extracting files into destination directory")
            safe_untar(self.path, dest)

        elif self.output_format == 'qcow2':
            # Remove the old path
            file_name = os.path.basename(self.path)
            qcow2_file = os.path.realpath('{}/{}.qcow2'.format(dest,
                                                               file_name))

            logger.info("Extracting files into qcow2 image")
            create_qcow2(self.path, qcow2_file)
        else:
            raise Exception("Unknown format:" + self.output_format)

        logger.info("Extraction completed successfully!")
        logger.info("Files are stored in: " + dest)


class DockerSource(object):
    """
    Extract files from Docker image
    """

    def __init__(self, **kwargs):
        """
        Bootstrap root filesystem from Docker registry

        @param url: Address of source registry
        @param username: Username to access source registry
        @param password: Password to access source registry
        @param fmt: Format used to store image [dir, qcow2]
        @param insecure: Do not require HTTPS and certificate verification
        @param no_cache: Whether to store downloaded images or not
        """

        self.username = kwargs['username']
        self.password = kwargs['password']
        self.output_format = kwargs['fmt']
        self.insecure = kwargs['not_secure']
        self.no_cache = kwargs['no_cache']

        registry = kwargs['uri'].netloc
        image = kwargs['uri'].path

        # Convert "docker:///<image>" to "docker://<image>"
        if not registry and image.startswith('/'):
            image = image[1:]

        # Convert "docker://<image>/" to "docker://<image>"
        elif image.endswith('/'):
            image = image[:-1]

        self.url = "docker://" + registry + image
        self.images_dir = get_image_dir(self.no_cache)
        # Retrive manifest from registry
        self.manifest = get_image_details(self.url, raw=True)

    def unpack(self, dest):
        """
        Extract image files from Docker image

        @param dest: Directory path where the files to be extraced
        """
        try:
            # Run skopeo copy into a tmp folder
            # Note: we don't want to expose --src-cert-dir to users as
            #       they should place the certificates in the system
            #       folders for broader enablement
            skopeo_copy = ["skopeo", "copy", self.url, "dir:" + self.images_dir]

            if self.insecure:
                skopeo_copy.append('--src-tls-verify=false')
            if self.username:
                if not self.password:
                    self.password = getpass.getpass()
                skopeo_copy.append('--src-creds={}:{}'.format(self.username,
                                                              self.password))
            # Run "skopeo copy" command
            execute(skopeo_copy)

            # Remove the manifest file as it is not needed
            os.remove(os.path.join(self.images_dir, "manifest.json"))

            # Layers are in order - root layer first
            # Reference:
            # https://github.com/containers/image/blob/master/image/oci.go#L100
            if self.output_format == 'dir':
                logger.info("Extracting container layers")
                untar_layers(self.manifest['layers'], self.images_dir, dest)
            elif self.output_format == 'qcow2':
                logger.info("Extracting container layers into qcow2 images")
                extract_layers_in_qcow2(self.manifest['layers'],
                                        self.images_dir, dest)
            else:
                raise Exception("Unknown format:" + self.output_format)

        except Exception:
            raise

        else:
            logger.info("Download and extract completed!")
            logger.info("Files are stored in: " + dest)

        finally:
            # Clean up
            if self.no_cache and self.images_dir != DEFAULT_IMG_DIR:
                shutil.rmtree(self.images_dir)
