#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007-2008 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import os

from PyQt4 import QtCore
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
        self.combo_toolbar = kdeui.KToolBar(self, 'combo toolbar')
        self.tree_view = tree_view.TreeView(self, 'tree view')

        self.path_combo = MyComboBox(self.combo_toolbar, 'path combo')
        self.combo_toolbar.insertWidget(0, 0, self.path_combo)
        self.combo_toolbar.setItemAutoSized(0)
        self.combo_toolbar.setIconSize(16)

        self.action_refresh = kdeui.KAction('Refresh tree view', 'reload',
                kdecore.KShortcut('F5'), self.tree_view.slot_refresh,
                minirok.Globals.action_collection, 'action_refresh')
        self.action_refresh.plug(self.combo_toolbar)

        self.action_focus_path_combo = kdeui.KAction('Focus path combo',
                kdecore.KShortcut('Alt+O'), self.path_combo.slot_focus,
                minirok.Globals.action_collection, 'action_path_combo_focus')

        # the widgets in KListViewSearchLineWidget are created via a slot fired
        # by a QTimer::singleShot(0ms), so the contained KListViewSearchLine
        # widget cannot be accessed until then; have to use a QTimer as well.
        # Thanks to Peter Rockai for the hint.
        qt.QTimer.singleShot(0, lambda:
                self.tree_search.searchLine().setListView(self.tree_view))

        qt.QTimer.singleShot(0, lambda:
                self.connect(self.tree_search.searchLine(),
                             QtCore.SIGNAL('search_finished'),
                             self.tree_view.slot_search_finished))

        qt.QTimer.singleShot(0, lambda:
                self.connect(self.tree_search.searchLine(),
                             qt.SIGNAL('returnPressed(const QString &)'),
                             self.tree_view.slot_append_visible))

        self.connect(self.tree_view, QtCore.SIGNAL('scan_in_progress'),
                self.tree_search.slot_scan_in_progress)

        self.connect(self.path_combo, QtCore.SIGNAL('new_directory_selected'),
                self.tree_view.slot_show_directory)

        ##

        if self.path_combo.currentText():
            # This can't go in the MyComboBox constructor because the signals
            # are not connected yet at that time.
            self.path_combo.emit(qt.SIGNAL('returnPressed(const QString &)'),
                    self.path_combo.currentText())
        else:
            text = 'Enter a directory here'
            width = self.path_combo.fontMetrics().width(text)
            self.path_combo.setCurrentText(text)
            self.path_combo.setMinimumWidth(width + 30) # add pixels for arrow

##

class MyComboBox(kfile.KURLComboBox, util.HasConfig):
    """A KURLComboBox that saves the introduced directories in the config."""

    CONFIG_SECTION = 'Tree View'
    CONFIG_HISTORY_OPTION = 'History'

    def __init__(self, parent, name):
        kfile.KURLComboBox.__init__(self, kfile.KURLComboBox.Directories,
                True, parent, 'path combo') # True: read-write
        util.HasConfig.__init__(self)

        self.completion_object = kio.KURLCompletion(kio.KURLCompletion.DirCompletion)
        self.setCompletionObject(self.completion_object)

        config = minirok.Globals.config(self.CONFIG_SECTION)
        urls = config.readPathListEntry(self.CONFIG_HISTORY_OPTION)
        self.setURLs(urls)

        self.connect(self, qt.SIGNAL('urlActivated(const KURL &)'),
                self.slot_url_changed)

        self.connect(self, qt.SIGNAL('returnPressed(const QString &)'),
                self.slot_url_changed)

    def set_url(self, url):
        """Public function to set an URL in the combo box.

        Using this function rather than setCurrentText() saves you from having
        to manually emit an urlActivated() or similar signal.
        """
        self.setCurrentText(url)
        self.slot_url_changed(url)

    def slot_focus(self):
        self.setFocus()
        self.lineEdit().selectAll()

    def slot_url_changed(self, url):
        if isinstance(url, kdecore.KURL):
            # We can only store QStrings
            url = url.pathOrURL()

        directory = util.kurl_to_path(url)

        if os.path.isdir(directory):
            urls = self.urls()
            urls.remove(url)
            urls.prepend(url)
            self.setURLs(urls, kfile.KURLComboBox.RemoveBottom)

        self.emit(QtCore.SIGNAL('new_directory_selected'), directory)

    def slot_save_config(self):
        config = minirok.Globals.config(self.CONFIG_SECTION)
        config.writePathEntry(self.CONFIG_HISTORY_OPTION, self.urls())
