#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import qt
import kio
import kfile
import kdeui
import kdecore

import minirok
from minirok import tree_view, util

##

class LeftSide(qt.QVBox):

    def __init__(self, *args):
        qt.QVBox.__init__(self, *args)

        self.setSpacing(2)

        self.tree_search = tree_view.TreeViewSearchLineWidget(None, self, 'tree search')
        self.path_combo = MyComboBox(self, 'path combo')
        self.tree_view = tree_view.TreeView(self, 'tree view')

        # the widgets in KListViewSearchLineWidget are created via a slot fired
        # by a QTimer::singleShot(0ms), so the contained KListViewSearchLine
        # widget cannot be accessed until then; have to use a QTimer as well.
        # Thanks to Peter Rockai for the hint.
        qt.QTimer.singleShot(0, lambda:
                self.tree_search.searchLine().setListView(self.tree_view))

        self.action_focus_path_combo = kdeui.KAction('Focus path combo',
                kdecore.KShortcut('Alt+O'), self.path_combo.slot_focus,
                minirok.Globals.action_collection, 'action_path_combo_focus')

        ##

        self.connect(self.tree_view, qt.PYSIGNAL('scanInProgress'),
                self.tree_search.slot_scan_in_progress)

        self.connect(self.path_combo, qt.SIGNAL('urlActivated(const KURL &)'),
                self.tree_view.slot_show_directory)

        self.connect(self.path_combo, qt.SIGNAL('urlActivated(const KURL &)'),
                self.path_combo.slot_url_changed)

        self.connect(self.path_combo, qt.SIGNAL('returnPressed(const QString &)'),
                self.tree_view.slot_show_directory)

        self.connect(self.path_combo, qt.SIGNAL('returnPressed(const QString &)'),
                self.path_combo.slot_url_changed)

        ##

        if self.path_combo.currentText():
            # This can't go in the MyComboBox constructor because the TreeView
            # does not exist yet.
            self.path_combo.emit(qt.SIGNAL('returnPressed(const QString &)'),
                    (self.path_combo.currentText(),))

##

class MyComboBox(kfile.KURLComboBox, util.HasConfig):
    """A KURLComboBox that saves the introduced directories in the config."""

    CONFIG_SECTION = 'Tree View'
    CONFIG_HISTORY_OPTION = 'History'

    def __init__(self, parent, name):
        kfile.KURLComboBox.__init__(self, kfile.KURLComboBox.Directories,
                True, parent, 'path combo') # True: read-write
        util.HasConfig.__init__(self)

        self.setCompletionObject(kio.KURLCompletion(kio.KURLCompletion.DirCompletion)) # does not work :(
        self.setInsertionPolicy(qt.QComboBox.AtTop)

        config = minirok.Globals.config(self.CONFIG_SECTION)
        urls = config.readPathListEntry(self.CONFIG_HISTORY_OPTION)
        self.setURLs(urls)

    def slot_focus(self):
        self.setFocus()
        self.lineEdit().selectAll()

    def slot_url_changed(self, url):
        # FIXME? if the user introduces a non-existant path, the first of the
        # present URLs get selected instead (but not opened)
        if isinstance(url, kdecore.KURL):
            # we need a QString
            url = url.isLocalFile() and url.path() or url.prettyURL()
        urls = self.urls()
        urls.remove(url)
        urls.prepend(url)
        self.setURLs(urls, kfile.KURLComboBox.RemoveBottom)

    def slot_save_config(self):
        config = minirok.Globals.config(self.CONFIG_SECTION)
        config.writePathEntry(self.CONFIG_HISTORY_OPTION, self.urls())
