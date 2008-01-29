#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007-2008 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import os
import stat

from PyKDE4 import kdecore
from PyQt4 import QtGui, QtCore

import minirok
from minirok import util

##

class FileListDrag(QtGui.QDrag):

    MIME_TYPE = 'text/x-minirok-track-list'

    def __init__(self, files, parent):
        """Constructs a QDrag object from a python list of str paths."""
        nfiles = len(files)
        QtGui.QDrag.__init__(self, parent)

        if nfiles > 0:
            mimedata = QtCore.QMimeData()
            kurllist = kdecore.KUrl.List(map(util.unicode_from_path, files))
            kurllist.populateMimeData(mimedata)

            # flag to signal that the QMimeData comes from ourselves
            mimedata.setData(self.MIME_TYPE, 'True')

            # display a "tooltip" with the number of tracks
            text = '%d track%s' % (nfiles, nfiles > 1 and 's' or '')
            metrics = parent.fontMetrics()
            width = metrics.width(text)
            height = metrics.height()
            ascent = metrics.ascent()

            self.pixmap = QtGui.QPixmap(width+4, height) # self needed
            self.pixmap.fill(parent, 0, 0)
            painter = QtGui.QPainter(self.pixmap)
            painter.drawText(2, ascent+1, text)

            self.setMimeData(mimedata)
            self.setPixmap(self.pixmap)

##

def mimedata_playable_files(mimedata):
    """Return a list of playable stuff from a QMimeData object.

    The QMimeData object must haveUrls(). Files that the engine can't play
    will not be included, and directories will be read and all its files
    included.

    However, if the QMimeData comes from Minirok itself (as determined by
    the presence of FileListDrag.MIME_TYPE, all URLs will be considered to
    be files (and not directories) that the engine can play.
    """
    assert mimedata.hasUrls(), 'You tried to drop something without URLs.'
    urls = kdecore.KUrl.List.fromMimeData(mimedata)

    if mimedata.hasFormat(FileListDrag.MIME_TYPE):
        return map(util.kurl_to_path, urls)
    else:
        files = []
        def append_path(path):
            try:
                mode = os.stat(path).st_mode
            except OSError, e:
                minirok.logger.warn('ignoring dropped %r: %s' % (path, e))
                return

            if stat.S_ISDIR(mode):
                try:
                    contents = sorted(os.listdir(path))
                except OSError, e:
                    minirok.logger.warn('could not list directory %r: %s', e)
                else:
                    for entry in contents:
                        append_path(os.path.join(path, entry))
            elif (stat.S_ISREG(mode)
                    and minirok.Globals.engine.can_play(path)
                    and path not in files):
                files.append(path)

        for url in urls:
            append_path(util.kurl_to_path(url))

        return files
