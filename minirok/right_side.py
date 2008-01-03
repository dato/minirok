#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import qt
import kdeui

import minirok
from minirok import playlist

##

class RightSide(qt.QVBox):

    def __init__(self, *args):
        qt.QVBox.__init__(self, *args)

        self.setSpacing(2)

        self.playlist_search = PlaylistSearchLineWidget(None, self, 'playlist search')
        self.playlist = playlist.Playlist(self, 'playlist')
        self.toolbar = kdeui.KToolBar(self, 'playlist toolbar')

        # see comment in LeftSide.__init__ about this
        qt.QTimer.singleShot(0, lambda:
                self.playlist_search.searchLine().setListView(self.playlist))

        qt.QTimer.singleShot(0, lambda:
                self.connect(self.playlist_search.searchLine(),
                             qt.SIGNAL('returnPressed(const QString &)'),
                             self.playlist.slot_play_first_visible))

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

class PlaylistSearchLine(kdeui.KListViewSearchLine):
    """A search line that calls Playlist.slot_list_changed when a search finishes."""

    def __init__(self, *args):
        kdeui.KListViewSearchLine.__init__(self, *args)
        self.timer = qt.QTimer(self, 'playlist search line timer')
        self.timer.setSingleShot(True)
        self.connect(self.timer, qt.SIGNAL('timeout()'),
                lambda: minirok.Globals.playlist.slot_list_changed())

    def updateSearch(self, *args):
        kdeui.KListViewSearchLine.updateSearch(self, *args)
        self.timer.start(400)

class PlaylistSearchLineWidget(kdeui.KListViewSearchLineWidget):
    """Same as super class, but with a PlaylistSearchLine widget."""

    def createSearchLine(self, klistview):
        return PlaylistSearchLine(self, klistview)
