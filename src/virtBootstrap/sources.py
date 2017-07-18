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

import select
import shutil
import getpass
import os
import logging
from subprocess import CalledProcessError, PIPE, Popen

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
            utils.safe_untar(self.path, dest)

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


class DockerSource(object):
    """
    Extract files from Docker image
    """

    # pylint: disable=too-many-instance-attributes
    def __init__(self, **kwargs):
        """
        Bootstrap root filesystem from Docker registry

        @param uri: Address of source registry
        @param username: Username to access source registry
        @param password: Password to access source registry
        @param fmt: Format used to store image [dir, qcow2]
        @param not_secure: Do not require HTTPS and certificate verification
        @param no_cache: Whether to store downloaded images or not
        @param progress: Instance of the progress module
        """

        self.url = self.gen_valid_uri(kwargs['uri'])
        self.username = kwargs['username']
        self.password = kwargs['password']
        self.output_format = kwargs['fmt']
        self.insecure = kwargs['not_secure']
        self.no_cache = kwargs['no_cache']
        self.progress = kwargs['progress'].update_progress
        self.images_dir = utils.get_image_dir(self.no_cache)
        self.manifest = None
        self.layers = []

        if self.username and not self.password:
            self.password = getpass.getpass()

        self.retrieve_layers_info()

    def retrieve_layers_info(self):
        """
        Retrive manifest from registry and get layers' digest,
        sum_type, size and file_path in a list.
        """
        self.manifest = utils.get_image_details(self.url, raw=True,
                                                insecure=self.insecure,
                                                username=self.username,
                                                password=self.password)

        for layer in self.manifest['layers']:
            sum_type, layer_sum = layer['digest'].split(':')
            file_path = os.path.join(self.images_dir, layer_sum + '.tar')
            self.layers.append([sum_type, layer_sum, file_path, layer['size']])

    def gen_valid_uri(self, uri):
        """
        Generate Docker URI in format accepted by skopeo.
        """
        registry = uri.netloc
        image = uri.path

        # Convert "docker:///<image>" to "docker://<image>"
        if not registry and image.startswith('/'):
            image = image[1:]

        # Convert "docker://<image>/" to "docker://<image>"
        elif image.endswith('/'):
            image = image[:-1]

        return "docker://" + registry + image

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
            output = utils.read_async(stdout[0]).strip().split('\n')
            for line in output:
                line_split = line.split()
                if len(line_split) > 2:  # Avoid short lines
                    if utils.is_new_layer_message(line):
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
                    elif utils.is_layer_config_message(line):
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
        d_size, d_format = utils.str2float(line_split[0]), line_split[1]
        t_size, t_format = utils.str2float(line_split[3]), line_split[4]

        if d_size and t_size:
            downloaded_size = utils.size_to_bytes(d_size, d_format)
            total_size = utils.size_to_bytes(t_size, t_format)
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
        utils.make_async(proc.stdout)
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
                    and utils.checksum(path, sum_type, sum_expected)):
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
                utils.untar_layers(self.layers, dest, self.progress)
            elif self.output_format == 'qcow2':
                self.progress("Extracting container layers into qcow2 images",
                              value=50, logger=logger)
                utils.extract_layers_in_qcow2(self.layers, dest, self.progress)
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
            if self.no_cache and self.images_dir != utils.DEFAULT_IMG_DIR:
                shutil.rmtree(self.images_dir)
