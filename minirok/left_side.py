#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007-2008 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import os

from PyQt4 import QtGui, QtCore
from PyKDE4 import kio, kdeui, kdecore

import minirok
from minirok import tree_view, util

##

class LeftSide(QtGui.QWidget):

    def __init__(self, *args):
        QtGui.QWidget.__init__(self, *args)

        self.tree_view = tree_view.TreeView()
        self.combo_toolbar = kdeui.KToolBar(None)
        self.tree_search = tree_view.TreeViewSearchLineWidget()

        layout = QtGui.QVBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.tree_search)
        layout.addWidget(self.combo_toolbar)
        layout.addWidget(self.tree_view)
        self.setLayout(layout)

        self.path_combo = MyComboBox(self.combo_toolbar)
        self.combo_toolbar.addWidget(self.path_combo)
        self.combo_toolbar.setIconDimensions(16)
        self.combo_toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)
        # self.combo_toolbar.setItemAutoSized(0) # XXX-KDE4 should be stretchabe or however it's called

        self.action_refresh = util.create_action('action_refresh_tree_view',
                'Refresh tree view', self.tree_view.slot_refresh, 'view-refresh', 'F5')
        self.combo_toolbar.addAction(self.action_refresh)

        self.action_focus_path_combo = util.create_action('action_path_combo_focus',
                'Focus path combobox', self.path_combo.slot_focus, shortcut='Alt+O')

        ##

        self.tree_search.searchLine().setTreeWidget(self.tree_view)

        self.connect(self.tree_search.searchLine(),
                QtCore.SIGNAL('search_finished'),
                self.tree_view.slot_search_finished)

        self.connect(self.tree_search.searchLine(),
                QtCore.SIGNAL('returnPressed(const QString &)'),
                self.tree_view.slot_append_visible)

        self.connect(self.tree_view, QtCore.SIGNAL('scan_in_progress'),
                self.tree_search.slot_scan_in_progress)

        self.connect(self.path_combo, QtCore.SIGNAL('new_directory_selected'),
                self.tree_view.slot_show_directory)

        ##

        if self.path_combo.currentText():
            # This can't go in the MyComboBox constructor because the signals
            # are not connected yet at that time.
            self.path_combo.emit(QtCore.SIGNAL('returnPressed(const QString &)'),
                    self.path_combo.currentText())
        else:
            text = 'Enter a directory here'
            width = self.path_combo.fontMetrics().width(text)
            self.path_combo.setEditText(text)
            self.path_combo.setMinimumWidth(width + 30) # add pixels for arrow

##

class MyComboBox(kio.KUrlComboBox, util.HasConfig):
    """A KURLComboBox that saves the introduced directories in the config."""

    CONFIG_SECTION = 'Tree View'
    CONFIG_HISTORY_OPTION = 'History'

    def __init__(self, parent):
        kio.KUrlComboBox.__init__(self, kio.KUrlComboBox.Directories, True, parent)
        util.HasConfig.__init__(self)

        self.completion_object = kio.KUrlCompletion(kio.KUrlCompletion.DirCompletion)
        self.setCompletionObject(self.completion_object)

        self.config = kdecore.KGlobal.config()
        urls = self.config.group(self.CONFIG_SECTION).readPathEntry(
                            self.CONFIG_HISTORY_OPTION, QtCore.QStringList())
        self.setUrls(urls)

        self.connect(self, QtCore.SIGNAL('urlActivated(const KUrl &)'),
                self.slot_set_url)

        self.connect(self, QtCore.SIGNAL('returnPressed(const QString &)'),
                self.slot_set_url)

    def slot_focus(self):
        self.setFocus()
        self.lineEdit().selectAll()

    def slot_set_url(self, url):
        if isinstance(url, kdecore.KUrl):
            # We can only store QStrings
            url = url.pathOrUrl()

        directory = util.kurl_to_path(url)

        if os.path.isdir(directory):
            urls = self.urls()
            urls.removeAll(url)
            urls.prepend(url)
            self.setUrls(urls, kio.KUrlComboBox.RemoveBottom)

        self.emit(QtCore.SIGNAL('new_directory_selected'), directory)

    def slot_save_config(self):
        self.config = kdecore.KGlobal.config()
        self.config.group(self.CONFIG_SECTION).writePathEntry(
                            self.CONFIG_HISTORY_OPTION, self.urls())
