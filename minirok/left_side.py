#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007-2010 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import minirok

import os

from PyKDE4 import kdecore, kdeui, kio
from PyQt4 import QtCore, QtGui

from minirok import (
    tree_view,
    util,
)

##

class LeftSide(QtGui.QWidget):

    def __init__(self, *args):
        QtGui.QWidget.__init__(self, *args)

        self.tree_view = tree_view.TreeView()
        self.tree_search = QtGui.QWidget(self)
        self.combo_toolbar = kdeui.KToolBar(None)

        layout = QtGui.QVBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(4, 4, 4, 0)
        layout.addWidget(self.tree_search)
        layout.addWidget(self.combo_toolbar)
        layout.addWidget(self.tree_view)
        self.setLayout(layout)

        self.button_action = 'Enable'
        self.search_button = QtGui.QPushButton(self.button_action)
        self.search_widget = tree_view.TreeViewSearchLineWidget()
        self.search_widget.setEnabled(False)

        layout2 = QtGui.QHBoxLayout()
        layout2.setSpacing(0)
        layout2.setContentsMargins(0, 0, 0, 0)
        layout2.addWidget(self.search_widget)
        layout2.addWidget(self.search_button)
        self.tree_search.setLayout(layout2)

        self.path_combo = MyComboBox(self.combo_toolbar)
        self.combo_toolbar.addWidget(self.path_combo)
        self.combo_toolbar.setIconDimensions(16)
        self.combo_toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)
        # XXX-KDE4: This should be "stretchabe" or however it's called.
        # self.combo_toolbar.setItemAutoSized(0)

        self.action_refresh = util.create_action(
            'action_refresh_tree_view', 'Refresh tree view',
            self.tree_view.slot_refresh, 'view-refresh', 'F5')
        self.combo_toolbar.addAction(self.action_refresh)

        self.action_focus_path_combo = util.create_action(
            'action_path_combo_focus', 'Focus path combobox',
            self.path_combo.slot_focus, shortcut='Alt+O')

        ##

        self.search_widget.searchLine().setTreeWidget(self.tree_view)

        self.connect(self.tree_view,
                     QtCore.SIGNAL('scan_in_progress'),
                     self.slot_tree_view_does_scan)

        self.connect(self.search_button,
                     QtCore.SIGNAL('clicked(bool)'),
                     self.slot_do_button)

        self.connect(self.search_widget.searchLine(),
                     QtCore.SIGNAL('search_finished'),
                     self.tree_view.slot_search_finished)

        self.connect(self.search_widget.searchLine(),
                     QtCore.SIGNAL('returnPressed(const QString &)'),
                     self.tree_view.slot_append_visible)

        self.connect(self.path_combo,
                     QtCore.SIGNAL('new_directory_selected'),
                     self.tree_view.slot_show_directory)

        ##

        if self.path_combo.currentText():
            # This can't go in the MyComboBox constructor because the signals
            # are not connected yet at that time.
            self.path_combo.slot_set_url(self.path_combo.currentText())
        else:
            text = 'Enter a directory here'
            width = self.path_combo.fontMetrics().width(text)
            self.path_combo.setEditText(text)
            self.path_combo.setMinimumWidth(width + 30)  # Add pixels for arrow.

    ##

    def slot_tree_view_does_scan(self, scanning):
        negated = not scanning
        self.search_button.setHidden(negated)
        self.search_widget.setEnabled(negated)
        self.search_button.setEnabled(scanning)
        self.button_action = self.tree_view.recurse and 'Stop scan' or 'Enable'
        self.search_button.setText(self.button_action)
        if scanning:
            self.search_widget.setToolTip(
                'Search disabled while reading directory contents')
        else:
            self.search_widget.setToolTip('')


    def slot_do_button(self):
        enable = (self.button_action == 'Enable')
        self.button_action = enable and 'Stop scan' or 'Enable'
        self.search_button.setText(self.button_action)
        if not enable:
            self.search_widget.setToolTip('')
        self.tree_view.recurse = enable

##

class MyComboBox(kio.KUrlComboBox):
    """A KURLComboBox that saves the introduced directories in the config."""

    CONFIG_SECTION = 'Tree View'
    CONFIG_HISTORY_OPTION = 'History'

    def __init__(self, parent):
        kio.KUrlComboBox.__init__(
            self, kio.KUrlComboBox.Directories, True, parent)
        util.CallbackRegistry.register_save_config(self.save_config)

        self.completion_object = kio.KUrlCompletion(
            kio.KUrlCompletion.DirCompletion)
        self.setCompletionObject(self.completion_object)

        config = kdecore.KGlobal.config().group(self.CONFIG_SECTION)
        urls = config.readPathEntry(self.CONFIG_HISTORY_OPTION,
                                    QtCore.QStringList())
        self.setUrls(urls)

        self.connect(self,
                     QtCore.SIGNAL('urlActivated(const KUrl &)'),
                     self.slot_set_url)

        self.connect(self,
                     QtCore.SIGNAL('returnPressed(const QString &)'),
                     self.slot_set_url)

    def slot_focus(self):
        self.setFocus()
        self.lineEdit().selectAll()

    def slot_set_url(self, url):
        if isinstance(url, kdecore.KUrl):
            # We can only store QStrings.
            url = url.pathOrUrl()

        directory = os.path.expanduser(util.kurl_to_path(url))

        if os.path.isdir(directory):
            urls = self.urls()
            urls.removeAll(url)
            urls.prepend(url)
            self.setUrls(urls, kio.KUrlComboBox.RemoveBottom)

        self.emit(QtCore.SIGNAL('new_directory_selected'), directory)

    def save_config(self):
        config = kdecore.KGlobal.config().group(self.CONFIG_SECTION)
        config.writePathEntry(self.CONFIG_HISTORY_OPTION, self.urls())
