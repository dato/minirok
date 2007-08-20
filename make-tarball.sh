#! /bin/sh

set -e

PRUNE_FROM_TARBALL="debian make-tarball.sh"

##

if [ ! -e NEWS ]; then
    echo >&2 "Script must run in the toplevel directory."
    exit 1
fi

##

for arg in "$@"; do
    if [ "$arg" = "-f" ]; then
    	FORCE=yes
    fi
done

##

LINE=$(head -1 NEWS)
VERSION=$(echo "$LINE" | awk '{print $1}')
DATE=$(echo "$LINE" | awk '{print $2}')

if ! echo "$DATE" | egrep -q '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'; then
    if [ -z "$FORCE" ]; then
    	echo >&2 "Use -f to create a tarball of an unreleased version."
	exit 1
    else
    	APPEND_TO_VER="~`date +%Y-%m-%d`"
    fi
fi

##

TMP_DIR=$(env TMPDIR= mktemp -d -p ../tarballs)
EXPORT_VERSION="minirok-$VERSION$APPEND_TO_VER"
EXPORT_DIR="$TMP_DIR/$EXPORT_VERSION"

bzr export "$EXPORT_DIR"

( # subshell to preserve old $CWD
cd "$EXPORT_DIR"
make -s -C minirok/ui >/dev/null
rm -r $PRUNE_FROM_TARBALL

cd ..
tar czf "../$EXPORT_VERSION.tar.gz" "$EXPORT_VERSION"
)

##

rm -r "$EXPORT_DIR"
rmdir "$TMP_DIR"
