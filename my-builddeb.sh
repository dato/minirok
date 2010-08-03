#! /bin/sh

set -e

cd "`dirname $0`"

##

DIST=$(dpkg-parsechangelog | awk '/^Distribution:/ { print $2 }')
UPSTREAM_VERSION=$(dpkg-parsechangelog |
    	    	   sed -rne 's/^Version: (.*)-[^-]+$/\1/p')

if [ "$DIST" = "UNRELEASED" ]; then
    echo >&2 "Building a tmp package, as per changelog"
    TMP_UPSTREAM_VERSION="$UPSTREAM_VERSION~r`git rev-list HEAD | wc -l`"
    sed -i -e "1s/ ($UPSTREAM_VERSION-/ ($TMP_UPSTREAM_VERSION-/" debian/changelog
    fakeroot debian/rules clean binary
    sed -i -e "1s/ ($TMP_UPSTREAM_VERSION-/ ($UPSTREAM_VERSION-/" debian/changelog
    rm -f ../packages/minirok_$UPSTREAM_VERSION~r*deb
    mv ../minirok_$TMP_UPSTREAM_VERSION-1_all.deb ../packages
    echo http://chistera.yi.org/~dato/code/minirok/packages/minirok_$TMP_UPSTREAM_VERSION-1_all.deb
    exit 0
fi

##

BUILDDIR="../build-area"
UNPACK_DIR="minirok-$UPSTREAM_VERSION"
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

rm -rf "$BUILDDIR/debian"
git archive HEAD debian | tar xC "$BUILDDIR"

cd "$BUILDDIR"
rm -rf "$UNPACK_DIR"
tar xf "`basename $DEBIAN_TARBALL`"
mv debian "$UNPACK_DIR"
cd "$UNPACK_DIR"
debuild && cd .. && rm -rf "$UNPACK_DIR"
