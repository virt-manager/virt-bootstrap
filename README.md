virt-bootstrap is a tool providing an easy way to setup the root
file system for libvirt-based containers.

It allows to use either a tarball containing the file system or
an image on a docker registry and unpacks it either as a folder
or in a qcow2 image with backing chains to mimic the docker layers.

Dependencies
------------

 * python 2 or 3
 * skopeo
 * virt-sandbox
 * libguestfs python binding
 * python passlib module
 * python mock module (for tests only)

Hacking
-------

To test changes without installing the package in your machine,
use the run script. For example to run virt-bootstrap, use a command
like the following one:

    ./run src/virtBootstrap/virt_bootstrap.py --help

The following commands will be useful for anyone writing patches:

    ./setup.py test      # Run local unit test suite
    ./setup.py pylint    # Run a pylint script against the codebase

Any patches shouldn't change the output of 'test' or 'pylint'. The 'pylint' requires `pylint` and `pycodestyle` to be installed.

If [coverage](https://pypi.python.org/pypi/coverage/) is installed, you can generate report using:

    coverage run --source=virtBootstrap ./setup.py test
    coverage report
