#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007-2008 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

from PyKDE4 import kdeui
from PyQt4 import QtGui, QtCore

import minirok
from minirok import playlist, util

##

class RightSide(QtGui.QWidget):

    def __init__(self, parent, main_window):
        QtGui.QWidget.__init__(self, parent)

        self.playlist = playlist.Playlist()
        self.stretchtoolbar = QtGui.QWidget()
        self.playlistview = playlist.PlaylistView(self.playlist)
        self.toolbar = kdeui.KToolBar('playlistToolBar', main_window,
                                                QtCore.Qt.BottomToolBarArea)
        # XXX-KDE4
        # self.playlist_search = PlaylistSearchLineWidget(None, self.playlist)

        vlayout = QtGui.QVBoxLayout()
        vlayout.setSpacing(0)
        vlayout.setContentsMargins(4, 4, 4, 0)
        # vlayout.addWidget(self.playlist_search)
        vlayout.addWidget(self.playlistview)
        vlayout.addWidget(self.stretchtoolbar)
        self.setLayout(vlayout)

        hlayout = QtGui.QHBoxLayout()
        hlayout.addStretch()
        hlayout.addWidget(self.toolbar)
        hlayout.setContentsMargins(0, 0, 0, 0)
        self.stretchtoolbar.setLayout(hlayout)

        self.toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)

        # XXX-KDE4
        # self.connect(self.playlist_search.searchLine(),
                # QtCore.SIGNAL('returnPressed(const QString &)'),
                # self.playlist.slot_play_first_visible)

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
