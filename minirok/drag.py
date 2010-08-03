#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007-2008, 2010 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import minirok

import os
import stat

from PyKDE4 import kdecore
from PyQt4 import QtCore, QtGui

from minirok import (
    util,
)

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

            self.pixmap = QtGui.QPixmap(width+4, height)  # "self" needed here.
            self.pixmap.fill(parent, 0, 0)
            painter = QtGui.QPainter(self.pixmap)
            painter.drawText(2, ascent+1, text)

            self.setMimeData(mimedata)
            self.setPixmap(self.pixmap)
