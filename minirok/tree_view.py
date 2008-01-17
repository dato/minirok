#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007-2008 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import os
import re

from PyQt4 import QtGui, QtCore
from PyKDE4 import kdeui

import minirok
from minirok import drag, engine, util

##

class TreeView(QtGui.QTreeWidget):

    def __init__(self, *args):
        QtGui.QTreeWidget.__init__(self, *args)
        self.root = None
        self.populating = False
        self.empty_directories = set()
        self.automatically_opened = set()

        self.timer = QtCore.QTimer(self)
        self.timer.setSingleShot(True)

        self.worker = util.ThreadedWorker(_my_listdir, self.timer)
        self.worker.start()

        self.header().hide()
        # XXX-KDE4
        # self.setDragEnabled(True)
        # self.setSelectionModeExt(kdeui.KListView.Extended)

        self.connect(self.timer, QtCore.SIGNAL('timeout()'), self.slot_populate_done)

        self.connect(self, QtCore.SIGNAL('itemActivated(QTreeWidgetItem *, int)'),
                self.slot_append_selected)

    ##

    def selected_files(self):
        """Returns a list of the selected files (reading directory contents)."""
        def _add_item(item):
            if not item.isVisible():
                return

            if not item.IS_DIR:
                if item.path not in files:
                    files.append(item.path)
                return

            item.populate()

            child = item.firstChild()
            while child:
                _add_item(child)
                child = child.nextSibling()

        files = []

        for item in self.selectedItems():
            _add_item(item)

        return files

    def visible_files(self):
        files = []
        iterator = qt.QListViewItemIterator(self,
                                            qt.QListViewItemIterator.Visible)

        item = iterator.current()
        while item:
            if not item.IS_DIR:
                files.append(item.path)
            iterator += 1
            item = iterator.current()

        return files

    ##

    def slot_append_selected(self, item):
        minirok.Globals.playlist.add_files(self.selected_files())

    def slot_append_visible(self, search_string):
        if not unicode(search_string).strip():
            return

        playlist_was_empty = bool(minirok.Globals.playlist.childCount() == 0)
        minirok.Globals.playlist.add_files(self.visible_files())

        if (playlist_was_empty
                and minirok.Globals.engine.status == engine.State.STOPPED):
            minirok.Globals.action_collection.action('action_play').activate()

    ##

    def slot_show_directory(self, directory):
        """Changes the TreeView root to the specified directory.
        
        If directory is the current root and there is no ongoing scan, a simple
        refresh will be performed instead.
        """
        if directory != self.root or self.populating:
            # Not refreshing
            self.clear()
            self.populating = False
            self.empty_directories.clear()
            self.automatically_opened.clear()
            self.setUpdatesEnabled(True) # can be unset if not finished populating
            self.root = directory

        _populate_tree(self.invisibleRootItem(), self.root)
        self.timer.start(0)

    def slot_refresh(self):
        self.slot_show_directory(self.root)

    def slot_populate_done(self):
        def _directory_children(parent):
            return _get_children(parent, lambda x: x.IS_DIR)

        if not self.populating:
            self.populating = True
            self.setUpdatesEnabled(False)
            self.emit(QtCore.SIGNAL('scan_in_progress'), True)
            self.worker.queue_many(_directory_children(self))
            return

        done = self.worker.pop_done()

        if done:
            for item, directory_contents in done:
                _populate_cache[item.path] = directory_contents
                item.populate()
                self.worker.queue_many(_directory_children(item))

        if self.worker.is_empty():
            self.timer.stop()
            self.populating = False
            self.setUpdatesEnabled(True)
            self.repaint()
            for item in self.empty_directories:
                (item.parent() or self).takeItem(item)
                del item # necessary?
            self.empty_directories.clear()
            self.emit(QtCore.SIGNAL('scan_in_progress'), False)

    def slot_search_finished(self, null_search):
        """Open the visible items, closing items opened in the previous search.

        Non-toplevel items with more than 5 children will not be opened.
        If null_search is True, no items will be opened at all.
        """
        # make a list of selected and its parents, in order not to close them
        selected = set()
        iterator = qt.QListViewItemIterator(self,
                                            qt.QListViewItemIterator.Selected)
        item = first_selected = iterator.current()
        while item:
            selected.add(item)
            parent = item.parent()
            while parent:
                selected.add(parent)
                parent = parent.parent()
            iterator += 1
            item = iterator.current()

        for item in self.automatically_opened - selected:
            item.setOpen(False)

        self.automatically_opened &= selected # not sure this is a good idea

        if null_search:
            self.ensureItemVisible(first_selected)
            return

        ##

        is_visible = lambda x: x.isVisible()
        pending = _get_children(self, is_visible)
        toplevel_count = len(pending)
        i = 0
        while pending:
            i += 1
            item = pending.pop(0)
            visible_children = _get_children(item, is_visible)
            if ((i <= toplevel_count or len(visible_children) <= 5)
                    and not item.isOpen()):
                item.setOpen(True)
                self.automatically_opened.add(item)
            pending.extend(x for x in visible_children if x.isExpandable())

    ##

    def startDrag(self):
        """Create a FileListDrag object for the selecte files."""
        # XXX If a regular variable is used instead of self.drag_obj,
        # things go very bad (crash or double-free from libc).
        self.drag_obj = drag.FileListDrag(self.selected_files(), self)
        self.drag_obj.dragCopy()

##

class TreeViewItem(QtGui.QTreeWidgetItem):

    IS_DIR = 0 # TODO Use QTreeWidgetItem::type() instead?

    def __init__(self, parent, path):
        self.path = path

        dirname, self.filename = os.path.split(path)
        QtGui.QTreeWidgetItem.__init__(self, parent,
                [ util.unicode_from_path(self.filename) ])

        # optimization for TreeViewSearchLine.itemMatches() below
        root = self.treeWidget().root
        rel_path = re.sub('^%s/*' % re.escape(root), '', path)
        self.unicode_rel_path = util.unicode_from_path(rel_path)

    def compare(self, other, column, asc):
        # XXX-KDE4 TODO
        """Sorts directories before files, and by filename after that."""
        return other.IS_DIR - self.IS_DIR or cmp(self.filename, other.filename)


class FileItem(TreeViewItem):
    pass


class DirectoryItem(TreeViewItem):

    IS_DIR = 1

    def __init__(self, parent, path):
        TreeViewItem.__init__(self, parent, path)
        self._mtime = -1
        self._populated = False
        self.setExpandable(True)

    def populate(self):
        """Populate the entry with children, one level deep.
        
        This method will only re-read directory contents from the filesystem
        if the mtime of the directory is different to the mtime when they were
        last read.
        """
        try:
            mtime = os.stat(self.path).st_mtime
        except OSError, e:
            minirok.logger.warn('cout not stat: %s', e)
            return
        else:
            if self._mtime != mtime:
                self._mtime = mtime
                self._populated = False
            else:
                return

        if not self._populated:
            _populate_tree(self, self.path)
            self._populated = True

    ##

    def setOpen(self, opening):
        if not self._populated:
            self.populate()

        if not self.childCount():
            self.setExpandable(False)
            return

        TreeViewItem.setOpen(self, opening)

##

class TreeViewSearchLine(kdeui.KListViewSearchLine):
    """Class to perform matches against a TreeViewItem.

    The itemMatches() method is overriden to make a match against the full
    relative path (with respect to the TreeView root directory) of the items,
    plus the patter is split in words and all have to match (instead of having
    to match *in the same order*, as happes in the standard KListViewSearchLine.

    When the user stops typing, a search_finished(bool empty_search) signal is
    emitted.
    """
    def __init__(self, *args):
        kdeui.KListViewSearchLine.__init__(self, *args)
        self.string = None
        self.regexes = []
        self.timer = qt.QTimer(self, 'tree search line timer')
        self.timer.setSingleShot(True)

        self.connect(self.timer, qt.SIGNAL('timeout()'),
                self.slot_emit_search_finished)

    def slot_emit_search_finished(self):
        self.emit(QtCore.SIGNAL('search_finished'), self.string is None)

    ##

    def updateSearch(self, string_):
        string_ = unicode(string_).strip()
        if string_:
            if string_ != self.string:
                self.string = string_
                self.regexes = [ re.compile(re.escape(pat), re.I | re.U)
                                               for pat in string_.split() ]
        else:
            self.string = None

        kdeui.KListViewSearchLine.updateSearch(self, string_)
        self.timer.start(400)

    def itemMatches(self, item, string_):
        # We don't need to do anything with the string_ parameter here because
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

class TreeViewSearchLineWidget(kdeui.KListViewSearchLineWidget):
    """Same as super class, but with a TreeViewSearchLine widget."""

    def createSearchLine(self, klistview):
        return TreeViewSearchLine(self, klistview)

    ##

    def slot_scan_in_progress(self, scanning):
        """Disables itself with an informative tooltip while scanning."""
        if scanning:
            qt.QToolTip.add(self,
                    'Search disabled while reading directory contents')
        else:
            qt.QToolTip.remove(self)

        self.setEnabled(not scanning)

##

_populate_cache = {}

def _populate_tree(parent, directory):
    """A helper function to populate either a TreeView or a DirectoryItem.
    
    If parent already contains children, it will be just refreshed, keeping as
    many existing children as possible.

    It updates TreeView's empty_directories set as appropriate.
    """
    prune_this_parent = True
    directory_contents = _populate_cache.get(directory, None)

    if directory_contents is None:
        # Get contents of directory from the filesystem
        # print 'W: foo'
        try:
            directory_contents = os.listdir(directory)
        except OSError, e:
            minirok.logger.warn('could not list directory: %s', e)
            return

    files = set(directory_contents)

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
            parent.takeItem(mapping[k])

        # Do not re-add items already in the tree view
        files -= common

    # Pointer to the parent QTreeWidget, for empty_directories
    treewidget = parent.treeWidget()

    for filename in files:
        path = os.path.join(directory, filename)
        if os.path.isdir(path):
            item = DirectoryItem(parent, path)
            treewidget.empty_directories.add(item)
        elif minirok.Globals.engine.can_play(path):
            FileItem(parent, path)
            prune_this_parent = False

    if not prune_this_parent:
        while parent:
            treewidget.empty_directories.discard(parent)
            parent = parent.parent()

def _get_children(toplevel, filter_func=None):
    """Returns a filtered list of all direct children of toplevel.
    
    :param filter_func: Only include children for which this function returns
        true. If None, all children will be returned.
    """
    return [ item for item in map(toplevel.child, range(toplevel.childCount()))
                if filter_func is None or filter_func(item) ]

def _my_listdir(item):
    return [ unicode(x).encode(minirok.filesystem_encoding)
                for x in qt.QDir(item.path).entryList() if x not in ('.', '..') ]
