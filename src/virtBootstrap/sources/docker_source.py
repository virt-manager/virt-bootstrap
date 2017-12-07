# -*- coding: utf-8 -*-
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
DockerSource aim is to download container image from Docker registry and
extract the layers of root file system into destination directory or qcow2
image with backing chains.
"""

import select
import shutil
import getpass
import os
import logging
import subprocess

from virtBootstrap import utils


# pylint: disable=invalid-name
# Create logger
logger = logging.getLogger(__name__)


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
        @param uid_map: Mappings for UID of files in rootfs
        @param gid_map: Mappings for GID of files in rootfs
        @param root_password: Root password to set in rootfs
        @param fmt: Format used to store image [dir, qcow2]
        @param not_secure: Do not require HTTPS and certificate verification
        @param no_cache: Whether to store downloaded images or not
        @param progress: Instance of the progress module

        Note: uid_map and gid_map have the format:
            [[<start>, <target>, <count>], [<start>, <target>, <count>] ...]
        """

        # Check if skopeo is installed
        if not utils.is_installed('skopeo'):
            raise RuntimeError('skopeo is not installed')

        self.url = self.gen_valid_uri(kwargs['uri'])
        self.username = kwargs.get('username', None)
        self.password = kwargs.get('password', None)
        self.uid_map = kwargs.get('uid_map', [])
        self.gid_map = kwargs.get('gid_map', [])
        self.root_password = kwargs.get('root_password', None)
        self.output_format = kwargs.get('fmt', utils.DEFAULT_OUTPUT_FORMAT)
        self.insecure = kwargs.get('not_secure', False)
        self.no_cache = kwargs.get('no_cache', False)
        self.progress = kwargs['progress'].update_progress
        self.images_dir = utils.get_image_dir(self.no_cache)
        self.manifest = None
        self.layers = []
        self.checksums = []

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

        if self.manifest['schemaVersion'] == 1:
            layers_list = self.manifest['fsLayers'][::-1]
            digest_field = 'blobSum'
        elif self.manifest['schemaVersion'] == 2:
            layers_list = self.manifest['layers']
            digest_field = 'digest'
        else:
            raise ValueError('Unsupported manifest schema.')

        for layer in layers_list:
            # Store checksums of layers
            layer_digest = layer[digest_field]
            sum_type, layer_sum = layer_digest.split(':')
            self.checksums.append([sum_type, layer_sum])

            # Store file path and size of each layer
            file_path = os.path.join(self.images_dir, layer_sum + '.tar')
            layer_size = layer.get('size', None)
            self.layers.append([file_path, layer_size])

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
        if image.endswith('/'):
            image = image[:-1]

        return "docker://" + registry + image

    def download_image(self):
        """
        Download image layers using "skopeo copy".
        """

        if self.no_cache:
            dest_dir = self.images_dir
        else:
            dest_dir = utils.get_image_dir(no_cache=True)

        # Note: we don't want to expose --src-cert-dir to users as
        #       they should place the certificates in the system
        #       folders for broader enablement
        skopeo_copy = ["skopeo", "copy", self.url, "dir:" + dest_dir]

        if self.insecure:
            skopeo_copy.append('--src-tls-verify=false')
        if self.username:
            skopeo_copy.append('--src-creds={}:{}'.format(self.username,
                                                          self.password))
        self.progress("Downloading container image", value=0, logger=logger)
        # Run "skopeo copy" command
        self.read_skopeo_progress(skopeo_copy)

        if not self.no_cache:
            os.remove(os.path.join(dest_dir, "manifest.json"))
            os.remove(os.path.join(dest_dir, "version"))
            utils.copytree(dest_dir, self.images_dir)
            shutil.rmtree(dest_dir)

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

        @param current_l: Number of currently downloaded layer
        @param total_l: Total number of layers
        @param line_split: A list with format:
                [<d_size>, <d_format>, '/', <t_size>, <t_format>, <progress>]
            Example:
                ['5.92', 'MB', '/', '44.96', 'MB', '[===>-----------------]']
        """

        if not (len(line_split) > 4 and isinstance(line_split, list)):
            return

        d_size, d_format = utils.str2float(line_split[0]), line_split[1]
        t_size, t_format = utils.str2float(line_split[3]), line_split[4]

        if d_size and t_size:
            downloaded_size = utils.size_to_bytes(d_size, d_format)
            total_size = utils.size_to_bytes(t_size, t_format)
            if downloaded_size and total_size:
                try:
                    frac = float(1) / total_l
                    downloaded = float(downloaded_size) / total_size
                    layer_frac = float(max(0, current_l - 1)) / total_l

                    progress = 50 * (layer_frac + (frac * downloaded))

                    self.progress(value=progress)
                except Exception:
                    pass  # Ignore failures

    def read_skopeo_progress(self, cmd):
        """
        Parse the output from skopeo copy to track download progress.
        """
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )

        # Without `make_async`, `fd.read` in `read_async` blocks.
        utils.make_async(proc.stdout)
        if not self.parse_output(proc):
            raise subprocess.CalledProcessError(proc.returncode, ' '.join(cmd))

    def validate_image_layers(self):
        """
        Check if layers of container image exist in image_dir
        and have valid hash sum.
        """
        self.progress("Checking cached layers", value=0, logger=logger)
        for index, checksum in enumerate(self.checksums):
            path = self.layers[index][0]
            sum_type, sum_expected = checksum

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

                img = utils.BuildImage(
                    layers=self.layers,
                    dest=dest,
                    progress=self.progress
                )
                img.create_base_layer()
                img.create_backing_chains()
                img.set_root_password(self.root_password)
                if self.uid_map or self.gid_map:
                    logger.info("Mapping UID/GID")
                    utils.map_id_in_image(
                        len(self.layers),  # Number of layers
                        dest,
                        self.uid_map,
                        self.gid_map,
                        (self.root_password is None)  # Create new disk?
                    )

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
