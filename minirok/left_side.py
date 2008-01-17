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

        # self.tree_search = tree_view.TreeViewSearchLineWidget(None, None??, 'tree search')
        self.combo_toolbar = kdeui.KToolBar(None)
        # self.tree_view = tree_view.TreeView(None, 'tree view')

        layout = QtGui.QVBoxLayout()
        # layout.addWidget(self.tree_search)
        layout.addWidget(self.combo_toolbar)
        # layout.addWidget(self.tree_view)
        self.setLayout(layout)

        self.path_combo = MyComboBox(self.combo_toolbar)
        self.combo_toolbar.addWidget(self.path_combo)
        self.combo_toolbar.setIconDimensions(16)
        self.combo_toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)
        # self.combo_toolbar.setItemAutoSized(0) # XXX-KDE4 should be stretchabe or however it's called

        self.action_refresh = util.create_action('action_refresh_tree_view',
                # 'Refresh tree view', self.tree_view.slot_refresh, 'view-refresh', 'F5')
                'Refresh tree view', lambda: XXX_KDE4.self.tree_view.slot_refresh, 'view-refresh', 'F5')
        self.combo_toolbar.addAction(self.action_refresh)

        self.action_focus_path_combo = util.create_action('action_path_combo_focus',
                'Focus path combobox', self.path_combo.slot_focus, shortcut='Alt+O')

        return # XXX-KDE4

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

            # XXX-KDE4 Check this other way, which was merged from threaded_io
            # This can't go in the MyComboBox constructor because the signals
            # are not connected yet at that time. Also, it's in a QTimer
            # because now that the TreeView works with a threaded worker, the
            # 0ms timers triggered from there seemed to be taking precedence
            # over the one creating the KListViewSearchLineWidget, thus making
            # that widget only appear after the worker had finished.
            #XXX qt.QTimer.singleShot(0, lambda:
            #XXX         self.path_combo.emit(
            #XXX             qt.SIGNAL('returnPressed(const QString &)'),
            #XXX             self.path_combo.currentText()))
        else:
            text = 'Enter a directory here'
            width = self.path_combo.fontMetrics().width(text)
            self.path_combo.setCurrentText(text)
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

        # XXX-KDE4
        # config = minirok.Globals.config(self.CONFIG_SECTION)
        # urls = config.readPathListEntry(self.CONFIG_HISTORY_OPTION)
        # self.setURLs(urls)

        self.connect(self, QtCore.SIGNAL('urlActivated(const KUrl &)'),
                self.slot_url_changed)

        self.connect(self, QtCore.SIGNAL('returnPressed(const QString &)'),
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
        return # XXX-KDE4
        config = minirok.Globals.config(self.CONFIG_SECTION)
        config.writePathEntry(self.CONFIG_HISTORY_OPTION, self.urls())
