#! /bin/bash

# If $DEBIAN_PREFIX exists, it will be prepended to all locations.
# This is used when building the Debian package.

set -e

##

if ! kde-config 2>/dev/null; then
    echo >&2 "ERROR: could not find kde-config."
    exit 1
fi

##

PREFIX=`kde-config --prefix`
BIN=`kde-config --expandvars --install exe`
APPS=`kde-config --expandvars --install data`
ICONS=`kde-config --expandvars --install icon`
CONFIG=`kde-config --expandvars --install config`
DESKTOP=`kde-config --expandvars --install xdgdata-apps`
KHOTKEYS="$APPS/khotkeys"
KCONF_UPDATE="$APPS/kconf_update"

##

install_file () {
    # path/file path/dir -> path/dir/file
    install_file2 "$1" "$2/`basename $1`"
}

install_file2 () {
    # path/file path/dir/file2 -> path/dir/file2
    install -D -m `mode $1` "$1" "${DEBIAN_PREFIX%%/}/${2##/}"
}

install_symlink () {
    DEST="${DEBIAN_PREFIX%%/}/${2##/}"
    mkdir -p "`dirname $DEST`"
    ln -sf "$1" "$DEST"
}

##

install_icons () {
    for size in 16 22 32 48 64 128; do
    	install_file2 icons/hi${size}-app-minirok.png \
		      "$ICONS/hicolor/${size}x${size}/minirok.png"
    done
}

install_package () {
    for p in minirok.py minirok/*.py; do
    	install_file "$p" "$PREFIX/share/minirok/`dirname $p`"
    done
}

##

mode () {
    if [ -x "$1" ]; then
    	echo 755
    else
    	echo 644
    fi
}

##

case "$1" in
    install)
	install_icons
	install_package
	install_file config/minirokrc "$CONFIG"
	install_file config/minirok.desktop "$DESKTOP"
	install_file config/minirok.khotkeys "$KHOTKEYS"
	install_file config/khotkeys_minirok.upd "$KCONF_UPDATE"
	install_symlink "$PREFIX/share/minirok/minirok.py" "$BIN/minirok"
	;;

    *)
	echo "Doing nothing, please pass 'install' as the first argument."
	;;
esac
