#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007-2008 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

from PyQt4 import QtGui, QtCore
from PyKDE4 import kio, kdecore

import minirok
from minirok import engine, proxy, tree_view, util

##

class LeftSide(QtGui.QWidget):

    def __init__(self, *args):
        QtGui.QWidget.__init__(self, *args)

        self.path_combo = MyComboBox(self)
        self.search_foo = QtGui.QWidget(self)
        self.tree_view = tree_view.TreeView(self)

        layout = QtGui.QVBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(4, 4, 4, 0)
        layout.addWidget(self.search_foo)
        layout.addWidget(self.path_combo)
        layout.addWidget(self.tree_view)
        self.setLayout(layout)

        self.search_widget = proxy.LineWidget()
        self.button_action = 'Enable'
        self.search_button = QtGui.QPushButton(self.button_action)

        self.search_widget.setEnabled(False)
        self.search_button.setEnabled(False)

        layout2 = QtGui.QHBoxLayout()
        layout2.setSpacing(0)
        layout2.setContentsMargins(0, 0, 0, 0)
        layout2.addWidget(self.search_widget)
        layout2.addWidget(self.search_button)
        self.search_foo.setLayout(layout2)

        self.tree = tree_view.Model()
        self.proxy = tree_view.Proxy()
        self.proxy.setSourceModel(self.tree)
        self.tree_view.setModel(self.proxy)
        self.search_widget.searchLine().setProxyModel(self.proxy)

        self.action_reload = util.create_action('action_reload_tree_view',
                'Reload tree view', self.tree.slot_reload, 'view-refresh', 'F5')

        self.action_focus_path_combo = util.create_action('action_path_combo_focus',
                'Focus path combobox', self.path_combo.slot_focus, shortcut='Alt+O')

        ##

        self.connect(self.tree, QtCore.SIGNAL('scan_in_progress'),
                self.slot_model_does_scan)

        self.connect(self.search_button, QtCore.SIGNAL('clicked(bool)'),
                self.slot_do_button)

        self.connect(self.path_combo, QtCore.SIGNAL('change_url'),
                self.tree.slot_change_url)

        self.connect(self.search_widget.searchLine(),
                QtCore.SIGNAL('returnPressed(const QString &)'),
                self.slot_append_visible)

        # XXX-KDE4
        # self.connect(self.search_widget.searchLine(),
        #         QtCore.SIGNAL('search_finished'),
        #         self.tree.slot_search_finished)

        ##

        if self.path_combo.currentText():
            # This can't go in the MyComboBox constructor because the signals
            # are not connected yet at that time.
            self.path_combo.slot_set_url(self.path_combo.currentText())
        else:
            text = 'Enter a directory here'
            width = self.path_combo.fontMetrics().width(text)
            self.path_combo.setEditText(text)
            self.path_combo.setMinimumWidth(width + 30) # add pixels for arrow

    def slot_model_does_scan(self, scanning):
        negated = not scanning
        self.search_button.setHidden(negated)
        self.search_widget.setEnabled(negated)
        self.search_button.setEnabled(scanning)
        self.button_action = self.tree.recurse and 'Stop scan' or 'Enable'
        self.search_button.setText(self.button_action)

    def slot_do_button(self):
        enable = (self.button_action == 'Enable')
        self.tree.recurse = enable
        self.button_action = enable and 'Stop scan' or 'Enable'
        self.search_button.setText(self.button_action)

    def slot_append_visible(self, string):
        if not unicode(string).strip():
            # no-op if no filter active
            return

        playlist_was_empty = (minirok.Globals.playlist.rowCount() == 0)

        parent = QtCore.QModelIndex()
        indexes = [ self.proxy.index(row, 0, parent)
                        for row in range(self.proxy.rowCount()) ]

        files = map(util.kurl_to_path, self.proxy.urls_from_indexes(indexes))
        minirok.Globals.playlist.add_files(files)

        if (playlist_was_empty
                and minirok.Globals.engine.status == engine.State.STOPPED):
            minirok.Globals.action_collection.action('action_play').trigger()

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
            # We can't store KUrls directly
            url = url.url()

        urls = self.urls()
        urls.removeAll(url)
        urls.prepend(url)
        self.setUrls(urls, kio.KUrlComboBox.RemoveBottom)

        # XXX emitting a kurl crashes here
        self.emit(QtCore.SIGNAL('change_url'), url)

    def slot_save_config(self):
        self.config = kdecore.KGlobal.config()
        self.config.group(self.CONFIG_SECTION).writePathEntry(
                            self.CONFIG_HISTORY_OPTION, self.urls())
