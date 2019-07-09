# Virt Bootstrap News

## Release 1.1.1 (Jul 9, 2019)

 * Don't expose the root password via command line
 * Set SElinux file context of destination folder
 * Use absolute destination path
 * safe-untar: Inherit SElinux context
 * don't allow overwriting of the root partition

## Release 1.1.0 (May 31, 2018)

 * safe_untar: check for permissions to set attribs
 * docker source, support blobs without .tar extension
 * docker-source, preserve extended file attributes
 * docker-source, get list of layers without `--raw`
 * docker-source, void skopeo copy in cache
 * Show error when guestfs-python or skopeo is not installed
 * pylint cleanups

## Release 1.0.0 (Sep 07, 2017)

 * Initial release
