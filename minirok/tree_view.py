#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007-2009 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import os
import re
import stat

from PyQt4 import QtGui, QtCore
from PyKDE4 import kdeui, kdecore

import minirok
from minirok import drag, engine, util

##

class TreeView(QtGui.QTreeWidget):

    CONFIG_SECTION = 'Tree View'
    CONFIG_RECURSE_OPTION = 'RecurseScan'

    def __init__(self, *args):
        QtGui.QTreeWidget.__init__(self, *args)
        self.root = None
        self.populating = False
        self.populate_pending = None
        self.empty_directories = set()
        self.automatically_opened = set()

        self.timer = QtCore.QTimer(self)

        # Recursing the tree to enable the search widget is configurable;
        # the LeftSide communicates with us via the "recurse" property.
        config = kdecore.KGlobal.config().group(self.CONFIG_SECTION)
        self._recurse = config.readEntry(
                self.CONFIG_RECURSE_OPTION, QtCore.QVariant(False)).toBool()

        util.CallbackRegistry.register_save_config(self.save_config)

        ##

        self.header().hide()
        self.setDragDropMode(self.DragOnly)
        self.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)

        self.connect(self.timer, QtCore.SIGNAL('timeout()'),
                self.slot_populate_done)

        self.connect(self,
                QtCore.SIGNAL('itemActivated(QTreeWidgetItem *, int)'),
                self.slot_append_selected)

        self.connect(self, QtCore.SIGNAL('itemExpanded(QTreeWidgetItem *)'),
                lambda item: item.repopulate())

    ##

    def _set_recurse(self, value):
        if self._recurse ^ value:
            self._recurse = bool(value)
            if self._recurse:
                self.timer.start(0)
                self.emit(QtCore.SIGNAL('scan_in_progress'), True)
            else:
                self.timer.stop()

    recurse = property(lambda self: self._recurse, _set_recurse)

    ##

    def selected_files(self):
        """Returns a list of the selected files (reading directory contents)."""
        def _add_item(item):
            if item.IS_DIR:
                item.repopulate() # meh, I don't like stat()'ing from here
                for child in _get_children(item):
                    _add_item(child)
            else:
                if item.path not in files:
                    files.append(item.path)

        files = []

        for item in self.selectedItems():
            _add_item(item)

        return files

    def visible_files(self):
        files = []
        iterator = QtGui.QTreeWidgetItemIterator(self,
                            QtGui.QTreeWidgetItemIterator.NotHidden)

        item = iterator.value()
        while item:
            if not item.IS_DIR:
                files.append(item.path)
            iterator += 1
            item = iterator.value()

        return files

    ##

    def slot_append_selected(self, item):
        if item is not None: # maybe overzealous here
            minirok.Globals.playlist.add_files(self.selected_files())

    def slot_append_visible(self, search_string):
        if not unicode(search_string).strip():
            return

        playlist_was_empty = bool(minirok.Globals.playlist.rowCount() == 0)
        minirok.Globals.playlist.add_files(self.visible_files())

        if (playlist_was_empty
                and minirok.Globals.engine.status == engine.State.STOPPED):
            minirok.Globals.action_collection.action('action_play').trigger()

    ##

    def slot_show_directory(self, directory):
        """Changes the TreeView root to the specified directory.

        If directory is the current root and there is no ongoing scan, a simple
        refresh will be performed instead.
        """
        if directory != self.root or self.populating:
            # Not refreshing
            self.clear()
            self.populate_pending = None
            self.setSortingEnabled(False) # dog slow otherwise
            self.empty_directories.clear()
            self.automatically_opened.clear()
            self.root = directory

        def _directory_children(parent):
            return _get_children(parent, lambda x: x.IS_DIR)

        self.populating = True
        _populate_tree(self.invisibleRootItem(), self.root)
        self.sortItems(0, QtCore.Qt.AscendingOrder) # (¹)

        self.populate_pending = _directory_children(self.invisibleRootItem())

        if self._recurse:
            self.timer.start(0)
            self.emit(QtCore.SIGNAL('scan_in_progress'), True)

        # (¹) There seems to be a bug somewhere, that if setSortingEnabled(True)
        # is called, without calling some function like sortItems() where the
        # SortOrder is specified, you get Descending by default. Beware.

    def slot_refresh(self):
        self.slot_show_directory(self.root)

    def slot_populate_done(self):
        def _directory_children(parent):
            return _get_children(parent, lambda x: x.IS_DIR)

        try:
            item = self.populate_pending.pop(0)
        except IndexError:
            self.timer.stop()
            self.populating = False
            self.setSortingEnabled(True)
            for item in self.empty_directories:
                (item.parent() or self.invisibleRootItem()).removeChild(item)
                del item # necessary?
            self.empty_directories.clear()
            self.emit(QtCore.SIGNAL('scan_in_progress'), False)
        else:
            _populate_tree(item, item.path)
            self.populate_pending.extend(_directory_children(item))

    def slot_search_finished(self, null_search):
        """Open the visible items, closing items opened in the previous search.

        Non-toplevel items with more than 5 children will not be opened.
        If null_search is True, no items will be opened at all.
        """
        # make a list of selected and its parents, in order not to close them
        selected = set()
        iterator = QtGui.QTreeWidgetItemIterator(self,
                            QtGui.QTreeWidgetItemIterator.Selected)
        item = first_selected = iterator.value()
        while item:
            selected.add(item)
            parent = item.parent()
            while parent:
                selected.add(parent)
                parent = parent.parent()
            iterator += 1
            item = iterator.value()

        for item in self.automatically_opened - selected:
            item.setExpanded(False)

        self.automatically_opened &= selected # keep them to close later

        if null_search:
            self.scrollToItem(first_selected)
            return

        ##

        is_visible = lambda x: not x.isHidden()
        pending = _get_children(self.invisibleRootItem(), is_visible)
        toplevel_count = len(pending)
        i = 0
        while pending:
            i += 1
            item = pending.pop(0)
            visible_children = _get_children(item, is_visible)
            if ((i <= toplevel_count or len(visible_children) <= 5)
                    and not item.isExpanded()):
                item.setExpanded(True)
                self.automatically_opened.add(item)
            pending.extend(x for x in visible_children if x.IS_DIR)

    ##

    def startDrag(self, action):
        dragobj = drag.FileListDrag(self.selected_files(), self)
        dragobj.exec_(action)

    ##

    def save_config(self):
        config = kdecore.KGlobal.config().group(self.CONFIG_SECTION)
        config.writeEntry(self.CONFIG_RECURSE_OPTION,
                            QtCore.QVariant(self._recurse))

##

class TreeViewItem(QtGui.QTreeWidgetItem):

    IS_DIR = 0 # TODO Use QTreeWidgetItem::type() instead?

    def __init__(self, path, root):
        self.path = path
        dirname, self.filename = os.path.split(path)

        # Note that we don't pass a parent here, because I've found that
        # to be slow. Instead, we always construct parentless items, and
        # add them to the parent with addChildren() in _populate_tree().
        QtGui.QTreeWidgetItem.__init__(self,
                [ util.unicode_from_path(self.filename) ])

        # optimization for TreeViewSearchLine.itemMatches() below
        rel_path = re.sub('^%s/*' % re.escape(root), '', path)
        self.unicode_rel_path = util.unicode_from_path(rel_path)

    def __lt__(self, other):
        """Sorts directories before files, and by filename after that."""
        return (other.IS_DIR, self.filename) < (self.IS_DIR, other.filename)


class FileItem(TreeViewItem):
    pass


class DirectoryItem(TreeViewItem):

    IS_DIR = 1

    def __init__(self, path, root):
        TreeViewItem.__init__(self, path, root)
        self.setChildIndicatorPolicy(QtGui.QTreeWidgetItem.ShowIndicator)

    def repopulate(self):
        """Force a repopulation of this item."""
        _populate_tree(self, self.path, force_refresh=True)

        if not self.childCount():
            self.setChildIndicatorPolicy(QtGui.QTreeWidgetItem.DontShowIndicator)
        else:
            self.setChildIndicatorPolicy(QtGui.QTreeWidgetItem.ShowIndicator)

        self.sortChildren(0, QtCore.Qt.AscendingOrder)

##

class TreeViewSearchLine(util.SearchLineWithReturnKey):
    """Class to perform matches against a TreeViewItem.

    The itemMatches() method is overriden to make a match against the full
    relative path (with respect to the TreeView root directory) of the items,
    plus the pattern is split in words and all have to match (instead of having
    to match *in the same order*, as happens in the standard KListViewSearchLine.

    When the user stops typing, a search_finished(bool empty_search) signal is
    emitted.
    """
    def __init__(self, *args):
        util.SearchLineWithReturnKey.__init__(self, *args)
        self.string = None
        self.regexes = []
        self.timer = QtCore.QTimer(self)
        self.timer.setSingleShot(True)

        self.connect(self.timer, QtCore.SIGNAL('timeout()'),
                self.slot_emit_search_finished)

    def slot_emit_search_finished(self):
        self.emit(QtCore.SIGNAL('search_finished'), self.string is None)

    ##

    def updateSearch(self, string):
        # http://www.riverbankcomputing.com/pipermail/pyqt/2008-January/018314.html
        if not isinstance(string, QtCore.QString):
            return kdeui.KTreeWidgetSearchLine.updateSearch(self, string)

        pystring = unicode(string).strip()
        if pystring:
            if pystring != self.string:
                self.string = pystring
                self.regexes = [ re.compile(re.escape(pat), re.I | re.U)
                                               for pat in pystring.split() ]
        else:
            self.string = None

        kdeui.KTreeWidgetSearchLine.updateSearch(self, string)
        self.timer.start(400)

    def itemMatches(self, item, string):
        # We don't need to do anything with the string parameter here because
        # self.string and self.regexes are always set in updateSearch() above.
        if self.string is None:
            return True

        try:
            item_text = item.unicode_rel_path
        except AttributeError:
            item_text = unicode(item.text(0))

        for regex in self.regexes:
            if not regex.search(item_text):
                return False
        else:
            return True


class TreeViewSearchLineWidget(kdeui.KTreeWidgetSearchLineWidget):
    """Same as super class, but with a TreeViewSearchLine widget."""

    def createSearchLine(self, qtreewidget):
        return TreeViewSearchLine(self, qtreewidget)

##

def _get_children(toplevel, filter_func=None):
    """Returns a filtered list of all direct children of toplevel.

    :param filter_func: Only include children for which this function returns
        true. If None, all children will be returned.
    """
    return [ item for item in map(toplevel.child, range(toplevel.childCount()))
                if filter_func is None or filter_func(item) ]

def _populate_tree(parent, directory, force_refresh=False):
    """A helper function to populate either a TreeView or a DirectoryItem.

    When populating, this function sets parent.mtime, and when invoked later on
    the same parent, it will return immediately if the mtime of directory is
    not different. If it is different, a refresh will be performed, keeping as
    many existing children as possible.

    It updates TreeView's empty_directories set as appropriate.
    """
    _my_listdir(directory)
    mtime, contents = _my_listdir_cache[directory]

    if mtime == getattr(parent, 'mtime', None):
        return
    else:
        parent.mtime = mtime
        prune_this_parent = True
        files = set(contents.keys())

    # Check filesystem contents against existing children
    # TODO What's up with prune_this_parent when refreshing.
    children = _get_children(parent)
    if children:
        # map { basename: item }, to compare with files
        mapping = dict((i.filename, i) for i in children)
        keys = set(mapping.keys())
        common = files & keys

        # Remove items no longer found in the filesystem
        for k in keys - common:
            parent.removeChild(mapping[k])

        # Do not re-add items already in the tree view
        files -= common

    # Pointer to the parent QTreeWidget, for empty_directories
    treewidget = parent.treeWidget()

    items = []
    for filename in files:
        path = os.path.join(directory, filename)
        if stat.S_ISDIR(contents[filename].st_mode):
            item = DirectoryItem(path, treewidget.root)
            treewidget.empty_directories.add(item)
        elif minirok.Globals.engine.can_play_path(path):
            item = FileItem(path, treewidget.root)
            prune_this_parent = False
        else:
            continue
        items.append(item)

    if items:
        parent.addChildren(items)

    if not prune_this_parent:
        while parent:
            treewidget.empty_directories.discard(parent)
            parent = parent.parent()

# This is a dict like:
# { path: (mtime, { entry1: stat_struct, entry2: stat_struct, ... }), ... }
_my_listdir_cache = {}

def _my_listdir(path):
    """Read directory contents, storing results in a dictionary cache.

    When invoked over a previously read directory, its contents will only be
    re-read from the filesystem if the mtime is different to the mtime the last
    time the contents were read.
    """
    try:
        mtime = os.stat(path).st_mtime
    except OSError, e:
        minirok.logger.warn('could not stat %r: %s', path, e.strerror)
        _my_listdir_cache.setdefault(path, (None, {}))
        return

    if mtime == _my_listdir_cache.get(path, (None, None))[0]:
        return

    try:
        contents = os.listdir(path)
    except OSError, e:
        minirok.logger.warn('could not listdir %r: %s', path, e.strerror)
        _my_listdir_cache.setdefault(path, (None, {}))
        return

    d = {}
    for entry in contents:
        try:
            entryp = os.path.join(path, entry)
            d[entry] = os.stat(entryp)
        except OSError, e:
            minirok.logger.warn('could not access %r: %s', entryp, e.strerror)

    _my_listdir_cache[path] = (mtime, d)
