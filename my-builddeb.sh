#! /bin/sh

set -e

##

BUILDDIR="../build-area"

UPSTREAM_VERSION=$(dpkg-parsechangelog |
    	    	   sed -rne 's/^Version: (.*)-[^-]+$/\1/p')
UPSTREAM_TARBALL="../tarballs/minirok-$UPSTREAM_VERSION.tar.gz"
DEBIAN_TARBALL="$BUILDDIR/minirok_$UPSTREAM_VERSION.orig.tar.gz"

if [ ! -e "$UPSTREAM_TARBALL" ]; then
    echo >&2 "Upstream tarball does not exist, aborting."
    exit 1
fi

if [ ! -e "$DEBIAN_TARBALL" ]; then
    ln -sf "$UPSTREAM_TARBALL" "$DEBIAN_TARBALL"
else
    cmp "$UPSTREAM_TARBALL" "$DEBIAN_TARBALL"
fi

##

EXPORT_DIR="export"
UNPACK_DIR="minirok-$UPSTREAM_VERSION"

rm -rf "$BUILDDIR/$EXPORT_DIR"
bzr export "$BUILDDIR/$EXPORT_DIR"

cd "$BUILDDIR"
rm -rf "$UNPACK_DIR"
tar xf "`basename $DEBIAN_TARBALL`"
mv "$EXPORT_DIR/debian" "$UNPACK_DIR"
rm -rf "$EXPORT_DIR"
cd "$UNPACK_DIR"
debuild && cd .. && rm -rf "$UNPACK_DIR"
