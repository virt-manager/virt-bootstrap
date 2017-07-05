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

import errno
import fcntl
import hashlib
import json
import select
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


def format_number(number):
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

    return(fmt % (number or 0, symbols[depth]))


def log_layer_extract(layer, current, total, progress):
    """
    Create log message on layer extract.
    """
    sum_type, sum_value, layer_file, layer_size = layer
    progress("Extracting layer (%s/%s) with size: %s"
             % (current, total, format_number(layer_size)), logger=logger)
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


def size_to_bytes(string, fmt):
    """
    Convert human readable formats to bytes.
    """
    formats = {'B': 0, 'KB': 1, 'MB': 2, 'GB': 3, 'TB': 4}
    return (string * pow(1024, formats[fmt.upper()]) if fmt in formats
            else False)


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


class FileSource(object):
    """
    Extract root filesystem from file.
    """
    def __init__(self, **kwargs):
        self.path = kwargs['uri'].path
        self.output_format = kwargs['fmt']
        self.progress = kwargs['progress'].update_progress

    def unpack(self, dest):
        """
        Safely extract root filesystem from tarball

        @param dest: Directory path where the files to be extraced
        """

        if not os.path.isfile(self.path):
            raise Exception('Invalid file source "%s"' % self.path)

        if self.output_format == 'dir':
            self.progress("Extracting files into destination directory",
                          value=0, logger=logger)
            safe_untar(self.path, dest)

        elif self.output_format == 'qcow2':
            # Remove the old path
            file_name = os.path.basename(self.path)
            qcow2_file = os.path.realpath('{}/{}.qcow2'.format(dest,
                                                               file_name))

            self.progress("Extracting files into qcow2 image", value=0,
                          logger=logger)
            create_qcow2(self.path, qcow2_file)
        else:
            raise Exception("Unknown format:" + self.output_format)

        self.progress("Extraction completed successfully!", value=100,
                      logger=logger)
        logger.info("Files are stored in: " + dest)


class DockerSource(object):
    """
    Extract files from Docker image
    """

    # pylint: disable=too-many-instance-attributes
    def __init__(self, **kwargs):
        """
        Bootstrap root filesystem from Docker registry

        @param url: Address of source registry
        @param username: Username to access source registry
        @param password: Password to access source registry
        @param fmt: Format used to store image [dir, qcow2]
        @param insecure: Do not require HTTPS and certificate verification
        @param no_cache: Whether to store downloaded images or not
        @param progress: Instance of the progress module
        """

        self.username = kwargs['username']
        self.password = kwargs['password']
        self.output_format = kwargs['fmt']
        self.insecure = kwargs['not_secure']
        self.no_cache = kwargs['no_cache']
        self.progress = kwargs['progress'].update_progress

        if self.username and not self.password:
            self.password = getpass.getpass()

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
        self.manifest = get_image_details(self.url, raw=True,
                                          insecure=self.insecure,
                                          username=self.username,
                                          password=self.password)

        # Get layers' digest, sum_type, size and file_path in a list
        self.layers = []
        for layer in self.manifest['layers']:
            sum_type, layer_sum = layer['digest'].split(':')
            file_path = os.path.join(self.images_dir, layer_sum + '.tar')
            self.layers.append([sum_type, layer_sum, file_path, layer['size']])

    def download_image(self):
        """
        Download image layers using "skopeo copy".
        """
        # Note: we don't want to expose --src-cert-dir to users as
        #       they should place the certificates in the system
        #       folders for broader enablement
        skopeo_copy = ["skopeo", "copy", self.url, "dir:" + self.images_dir]

        if self.insecure:
            skopeo_copy.append('--src-tls-verify=false')
        if self.username:
            skopeo_copy.append('--src-creds={}:{}'.format(self.username,
                                                          self.password))
        self.progress("Downloading container image", value=0, logger=logger)
        # Run "skopeo copy" command
        self.read_skopeo_progress(skopeo_copy)
        # Remove the manifest file as it is not needed
        os.remove(os.path.join(self.images_dir, "manifest.json"))

    def parse_output(self, proc):
        """
        Read stdout from skopeo's process asynchconosly.
        """
        current_layer, total_layers_num = 0, len(self.layers)

        # Process the output until the process terminates
        while proc.poll() is None:
            # Wait for data to become available
            stdout = select.select([proc.stdout], [], [])[0]
            # Split output into line
            output = read_async(stdout[0]).strip().split('\n')
            for line in output:
                if line:  # is not empty
                    line_split = line.split()
                    if is_new_layer_message(line):
                        current_layer += 1
                        self.progress("Downloading layer (%s/%s)"
                                      % (current_layer, total_layers_num))
                    # Use the single slash between layer's "downloaded" and
                    # "total size" in the output to recognise progress message
                    elif line_split[2] == '/':
                        self.update_progress_from_output(line_split,
                                                         current_layer,
                                                         total_layers_num)

                    # Stop parsing when manifest is copied.
                    elif is_layer_config_message(line):
                        break
            else:
                continue  # continue if the inner loop didn't break
            break

        if proc.poll() is None:
            proc.wait()  # Wait until the process is finished
        return proc.returncode == 0

    def update_progress_from_output(self, line_split, current_l, total_l):
        """
        Parse a line from skopeo's output to extract the downloaded and
        total size of image layer.

        Calculate percentage and update the progress of virt-bootstrap.
        """
        d_size, d_format = str2float(line_split[0]), line_split[1]
        t_size, t_format = str2float(line_split[3]), line_split[4]

        if d_size and t_size:
            downloaded_size = size_to_bytes(d_size, d_format)
            total_size = size_to_bytes(t_size, t_format)
            if downloaded_size and total_size:
                try:
                    self.progress(value=(50
                                         * downloaded_size / total_size
                                         * float(current_l)/total_l))
                except Exception:
                    pass  # Ignore failures

    def read_skopeo_progress(self, cmd):
        """
        Parse the output from skopeo copy to track download progress.
        """
        proc = Popen(cmd, stdout=PIPE, stderr=PIPE, universal_newlines=True)

        # Without `make_async`, `fd.read` in `read_async` blocks.
        make_async(proc.stdout)
        if not self.parse_output(proc):
            raise CalledProcessError(cmd, proc.stderr.read())

    def validate_image_layers(self):
        """
        Check if layers of container image exist in image_dir
        and have valid hash sum.
        """
        self.progress("Checking cached layers", value=0, logger=logger)
        for sum_type, sum_expected, path, _ignore in self.layers:
            logger.debug("Checking layer: %s", path)
            if not (os.path.exists(path)
                    and checksum(path, sum_type, sum_expected)):
                return False
        return True

    def fetch_layers(self):
        """
        Retrieve layers of container image.
        """
        # Check if layers have been downloaded
        if not self.validate_image_layers():
            self.download_image()

    def unpack(self, dest):
        """
        Extract image files from Docker image

        @param dest: Directory path where the files to be extraced
        """
        try:
            # Layers are in order - root layer first
            # Reference:
            # https://github.com/containers/image/blob/master/image/oci.go#L100
            self.fetch_layers()

            # Unpack to destination directory
            if self.output_format == 'dir':
                self.progress("Extracting container layers", value=50,
                              logger=logger)
                untar_layers(self.layers, dest, self.progress)
            elif self.output_format == 'qcow2':
                self.progress("Extracting container layers into qcow2 images",
                              value=50, logger=logger)
                extract_layers_in_qcow2(self.layers, dest, self.progress)
            else:
                raise Exception("Unknown format:" + self.output_format)

        except Exception:
            raise

        else:
            self.progress("Download and extract completed!", value=100,
                          logger=logger)
            logger.info("Files are stored in: " + dest)

        finally:
            # Clean up
            if self.no_cache and self.images_dir != DEFAULT_IMG_DIR:
                shutil.rmtree(self.images_dir)
