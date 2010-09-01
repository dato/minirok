#! /usr/bin/env python
## Hey, Python: encoding=utf-8
#
# Copyright (c) 2007-2008, 2010 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import minirok

from PyKDE4 import kdeui
from PyQt4 import QtCore, QtGui

from minirok import (
    playlist,
    proxy,
)

##

class RightSide(QtGui.QWidget):

    def __init__(self, parent, main_window):
        QtGui.QWidget.__init__(self, parent)

        self.proxy = playlist.Proxy()
        self.playlist = playlist.Playlist()
        self.playlist_view = playlist.PlaylistView(self)

        self.stretchtoolbar = QtGui.QWidget()
        self.playlist_search = proxy.LineWidget()
        self.toolbar = kdeui.KToolBar('playlistToolBar', main_window,
                                      QtCore.Qt.BottomToolBarArea)

        self.proxy.setFilterKeyColumn(-1)  # All.
        self.proxy.setSourceModel(self.playlist)
        self.playlist_view.setModel(self.proxy)
        self.playlist_search.searchLine().setProxyModel(self.proxy)

        self.toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)
        self.playlist.selection_model = (
            self.playlist_view.selectionModel())  # "..."

        vlayout = QtGui.QVBoxLayout()
        vlayout.setSpacing(0)
        vlayout.setContentsMargins(4, 4, 4, 0)
        vlayout.addWidget(self.playlist_search)
        vlayout.addWidget(self.playlist_view)
        vlayout.addWidget(self.stretchtoolbar)
        self.setLayout(vlayout)

        hlayout = QtGui.QHBoxLayout()
        hlayout.addStretch()
        hlayout.addWidget(self.toolbar)
        hlayout.setContentsMargins(0, 0, 0, 0)
        self.stretchtoolbar.setLayout(hlayout)

        self.connect(self.playlist_search.searchLine(),
                     QtCore.SIGNAL('returnPressed(const QString &)'),
                     self.slot_play_first_visible)

        minirok.Globals.playlist = self.playlist

    def slot_play_first_visible(self, string):
        if len(unicode(string).strip()) > 0:
            index = self.proxy.index(0, 0)
            self.proxy.slot_activate_index(index)
