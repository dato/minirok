#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007-2008 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import os

from PyKDE4 import kdecore
from PyQt4 import QtGui, QtCore

import minirok
from minirok import util

##

class FileListDrag(QtGui.QDrag):

    def __init__(self, files, parent):
        """Constructs a QDrag object from a python list of str paths."""
        nfiles = len(files)
        QtGui.QDrag.__init__(self, parent)

        if nfiles > 0:
            mimedata = QtCore.QMimeData()
            kurllist = kdecore.KUrl.List(map(util.unicode_from_path, files))
            kurllist.populateMimeData(mimedata)

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

    @staticmethod
    def file_list(event):
        """Return a list of the file paths encoded in this event.

        Files that the engine can't play will not be included; if the event is
        an instance of FileListDrag, though, the list will be assumed to be
        filtered already.

        Directories will be read and all its files included.
        """
        files = []
        all_playable = isinstance(event, FileListDrag)

        urls = kdecore.KURL.List()
        kdecore.KURLDrag.decode(event, urls)

        def append_path(path):
            if os.path.isdir(path):
                try:
                    contents = sorted(os.listdir(path))
                except OSError, e:
                    minirok.logger.warn('could not list directory: %s', e)
                else:
                    for file_ in contents:
                        append_path(os.path.join(path, file_))
            elif ((all_playable or minirok.Globals.engine.can_play(path))
                    and path not in files):
                files.append(path)

        for url in urls:
            append_path(util.kurl_to_path(url))

        return files
