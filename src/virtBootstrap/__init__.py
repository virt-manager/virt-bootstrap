# -*- coding: utf-8 -*-
# Authors:
#    Radostin Stoyanov <rstoyanov1@gmail.com>

# Copyright (c) 2017 Radostin Stoyanov

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

r"""
The virtBootstrap module provides an easy way to setup the root file system for
Libvirt-LXC containers.

This module exports the method bootstrap() which takes the following arguments:


    uri
        This parameter takes a string of source URI.

        Supported URI formats:
        --------------------------------------
        - File (tarball)
            /path/to/local/rootfs.tar.xz
            file://path/to/local/rootfs.tar.xz

        - Docker registry (skopeo)
            docker://ubuntu:latest
            docker://docker.io/fedora
            docker://privateregistry:5000/image

        - virt-builder
            virt-builder://fedora-25
            virt-builder://ubuntu-16.04
        --------------------------------------
        * If Docker registry is not specified "docker.io" is used.


    dest
        This parameter takes a string which represents absolute or real path of
        destination directory where the root file system will be extract or
        qcow2 images will be stored.


    fmt (optional)
        This parameter takes a string which represents the output format for
        the root file system. Possible values are:
            - dir (default)
            - qcow2


    username (optional)
        This parameter takes a string which represents the username used to
        access Docker source registry. See also "password" and "not_secure".

        If this parameter is specified and the "password" is ommited password
        prompt will be issued.

        *See https://docs.docker.com/registry/deploying/#restricting-access


    password (optional)
        This parameter takes a string which represents the password used to
        access Docker source registry.

        *See https://docs.docker.com/registry/deploying/#restricting-access


    root_password (optional)
        This parameter takes a string which represents root password.
        This string is hashed and inserted into /etc/shadow file of the
        extracted root file system.
        If the output format is "qcow2" the modification of /etc/shadow are
        applied in additional qcow2 disk image with backing file set to the
        last layer.

        *The /etc/shadow file must already exist in the rootfs of the container
        image and have "root" user entry.


    uid_map (optional)
        This parameter takes a list of lists which represents the translation
        map for UID. See also "gid_map".

        Format:
        [[<start>, <target>, <count>]]
        Example:
        [[0, 1000, 10], [500, 1500, 10]]
        This will map the UID: 0-9 to 1000-1009 and 500-509 to 1500-1509

        *When the output format is "dir" (fmt="dir") this option is available
        only for privileged users.


    gid_map (optional)
        This parameter is used to map group ownership of files in the
        extracted rootfs. It works in a similar way as "uid_map".


    not_secure (optional)
        This parameter takes a boolean which indicates whether HTTPS errors
        will be ignored. Default value is False.

        *See "--src-tls-verify" from "skopeo copy".
        https://www.mankier.com/1/skopeo#skopeo_copy


    no_cache (optional)
        This parameter takes a boolean which indicates whether the downloaded
        Docker images will be discarded after the root file system was
        extracted.

        By default downloaded images are stored in:
            /var/cache/virt-bootstrap/docker_images/
        for non-root users:
            ~/.cache/share/virt-bootstrap/docker_images/


    progress_cb (optional)
        This parameter takes a function which is called every time when the
        progress information is updated. Only one parameter passed to the
        called function - a dictionary with keys 'status' and 'value'.

    Examples:
        {'status': 'Checking cached layers', 'value': 0}
        {'status': 'Downloading layer (1/1)', 'value': 12.82051282051282}


Usage Examples

    import virtBootstrap

    # Bootstrap latest Ubuntu container image from docker.io
    virtBootstrap.bootstrap(uri='docker://ubuntu', dest='/tmp/foo')

    # Bootstrap Fedora 25 container image from docker.io
    virtBootstrap.bootstrap(
        uri='docker://registry.fedoraproject.org/fedora:25',
        dest='/tmp/bar'
    )

    # Set password for root
    virtBootstrap.bootstrap(
        uri='docker://fedora',
        dest='/tmp/foo',
        root_password='secret'
    )

    # Convert Ubuntu container image to qcow2 disk image using backing chains
    virtBootstrap.bootstrap(
        uri='docker://ubuntu',
        dest='/tmp/foo',
        fmt='qcow2'
    )

    # Bootstrap root file system from image stored in private registry
    virtBootstrap.bootstrap(
        uri='docker://localhost:5000/opensuse',
        dest='/tmp/foo',
        username='testuser',
        password='testpassoword',
        not_secure=True
    )

    # Apply UID/GID mapping (root privileges required).
    virtBootstrap.bootstrap(
        uri='docker://ubuntu',
        dest='/tmp/foo',
        uid_map=[[0,1000,10]],
        gid_map=[[0,1000,10]]
    )

    # Use progress callback to print the current progress to stdout
    def show(prog): print(prog)

    virtBootstrap.bootstrap(
        uri='docker://ubuntu',
        dest='/tmp/foo',
        progress_cb=show
    )

Note:
    You don't necessarily need to be root when using virt-bootstrap with
    "qcow2" output format, however, for "dir" format there are some drawbacks:
        1. Mapping UID/GID is not supported for unprivileged users.
        2. All extracted files will be owned by the current unprivileged user.
 """

from virtBootstrap.virt_bootstrap import bootstrap
from virtBootstrap.virt_bootstrap import __version__
