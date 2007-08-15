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

        self.playlist_search = kdeui.KListViewSearchLineWidget(None, self, 'playlist search')
        self.playlist = playlist.Playlist(self, 'playlist')
        self.toolbar = kdeui.KToolBar(self, 'playlist toolbar')

        # see comment in LeftSide.__init__ about this
        qt.QTimer.singleShot(0, lambda:
                self.playlist_search.searchLine().setListView(self.playlist))

        # populate the toolbar
        self.toolbar.setFullSize(True)
        self.toolbar.insertWidget(0, 0, qt.QWidget(self.toolbar))
        self.toolbar.setItemAutoSized(0)
        self.playlist.action_previous.plug(self.toolbar)
        self.playlist.action_play_pause.plug(self.toolbar)
        self.playlist.action_stop.plug(self.toolbar)
        self.playlist.action_next.plug(self.toolbar)
        self.toolbar.insertLineSeparator(-1, -1)
        self.playlist.action_clear.plug(self.toolbar)

        minirok.Globals.playlist = self.playlist
