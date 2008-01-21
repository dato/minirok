#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007-2008 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

from PyKDE4 import kdeui
from PyQt4 import QtGui, QtCore

import minirok
from minirok import util # XXX-KDE4 playlist

##

class RightSide(QtGui.QWidget):

    def __init__(self, *args):
        QtGui.QWidget.__init__(self, *args)

        # self.playlist = playlist.Playlist()
        # self.toolbar = kdeui.KToolBar(None)
        self.playlist = QtGui.QTreeWidget() # XXX-KDE4
        self.playlist_search = PlaylistSearchLineWidget(None, self.playlist)

        layout = QtGui.QVBoxLayout()
        layout.setSpacing(0)
        layout.addWidget(self.playlist_search)
        layout.addWidget(self.playlist)
        # layout.addWidget(self.toolbar)
        self.setLayout(layout)

        self.connect(self.playlist_search.searchLine(),
                QtCore.SIGNAL('returnPressed(const QString &)'),
                lambda: self.playlist.slot_play_first_visible) # XXX-KDE4 lambda

        return # XXX-KDE4

        # populate the toolbar
        self.toolbar.setFullSize(True)
        self.toolbar.setMovingEnabled(False) # this erases the border...
        self.toolbar.insertWidget(0, 0, qt.QWidget(self.toolbar))
        self.toolbar.setItemAutoSized(0)
        self.playlist.action_previous.plug(self.toolbar)
        self.playlist.action_play_pause.plug(self.toolbar)
        self.playlist.action_stop.plug(self.toolbar)
        self.playlist.action_next.plug(self.toolbar)
        self.toolbar.insertLineSeparator(-1, -1)
        self.playlist.action_clear.plug(self.toolbar)

        minirok.Globals.playlist = self.playlist

##

class PlaylistSearchLine(util.SearchLineWithReturnKey):
    """A search line that calls Playlist.slot_list_changed when a search finishes."""

    def __init__(self, parent, playlist):
        util.SearchLineWithReturnKey.__init__(self, parent, playlist)
        self.timer = QtCore.QTimer(self)
        self.timer.setSingleShot(True)
        self.connect(self.timer, QtCore.SIGNAL('timeout()'),
                lambda: playlist.slot_list_changed) # XXX-KDE4 lambda

    def updateSearch(self, *args):
        util.SearchLineWithReturnKey.updateSearch(self, *args)
        self.timer.start(400)


class PlaylistSearchLineWidget(kdeui.KTreeWidgetSearchLineWidget):
    """Same as super class, but with a PlaylistSearchLine widget."""

    def createSearchLine(self, qtreewidget):
        return PlaylistSearchLine(self, qtreewidget)
