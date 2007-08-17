#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import os
import re
import threading

import qt
import kdeui

import minirok
from minirok import drag, util

##

class TreeView(kdeui.KListView):

    def __init__(self, *args):
        kdeui.KListView.__init__(self, *args)
        self.root = None
        self.timer = qt.QTimer(self, 'tree_view_timer')
        self.iterator = None

        self.addColumn('')
        self.header().hide()

        self.setDragEnabled(True)
        self.setRootIsDecorated(True)
        self.setSelectionModeExt(kdeui.KListView.Extended)

        # Initially the tree view was populated in a separated thread, but
        # that didn't work out nicely because you cannot do UI calls in
        # threads other than the main thread. Now, we use a QTimer object to
        # periodically call a function that just reads one directory and
        # creates its KListViewItems. The timer starts with 0 msecs, which
        # means it will get called whenever there are no pending events to
        # process.
        self.connect(self.timer, qt.SIGNAL('timeout()'), self.slot_populate_one)

    ##

    def selected_files(self):
        """Returns a list of the selected files (reading directory contents)."""
        def _add_item(item):
            if not item.isVisible():
                return

            if not item.IS_DIR:
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

    ##

    def slot_show_directory(self, directory):
        """Changes the TreeView root to the specified directory."""
        self.clear()
        self.setUpdatesEnabled(True) # can be unset if not finished populating
        self.root = util.kurl_to_path(directory)
        _populate_tree(self, self.root)
        self.timer.start(0, False) # False: not one-shot

    def slot_populate_one(self):
        if self.iterator is None:
            self.setUpdatesEnabled(False)
            self.emit(qt.PYSIGNAL('scan_in_progress'), (True,))
            self.iterator = qt.QListViewItemIterator(self)

        item = self.iterator.current()

        if item is not None:
            item.populate()
            self.iterator += 1
        else:
            self.timer.stop()
            self.iterator = None
            self.setUpdatesEnabled(True)
            self.repaint()
            self.emit(qt.PYSIGNAL('scan_in_progress'), (False,))

    ##

    def startDrag(self):
        """Create a FileListDrag object for the selecte files."""
        # XXX If a regular variable is used instead of self.drag_obj,
        # things go very bad (crash or double-free from libc).
        self.drag_obj = drag.FileListDrag(self.selected_files(), self)
        self.drag_obj.dragCopy()

##

class TreeViewItem(kdeui.KListViewItem):

    IS_DIR = 0

    def __init__(self, parent, path):
        self.path = path
        self.root = parent.root
        self.rel_path = re.sub('^%s/*' % re.escape(self.root), '', path)
        self.dirname, self.filename = os.path.split(path)
        kdeui.KListViewItem.__init__(self, parent,
                util.unicode_from_path(self.filename))

    def populate(self):
        pass

    def compare(self, other, column, asc):
        """Sorts directories before files, and by filename after that."""
        return other.IS_DIR - self.IS_DIR or cmp(self.filename, other.filename)

class FileItem(TreeViewItem):

    HARD_CODED_REGEX = re.compile(r'^(?:(?P<track>\d+)_)?(?:(?P<artist>.+?) - )?(?P<title>.+)\.(?P<ext>\w{3,})')

    def D__init__(self, parent, path):
        TreeViewItem.__init__(self, parent, path)
        m = self.HARD_CODED_REGEX.search(self.filename)
        if m:
            # self.groups = m.groupdict()
            self.setText(0, util.unicode_from_path(m.group('title')))

class DirectoryItem(TreeViewItem):

    IS_DIR = 1

    def __init__(self, parent, path):
        TreeViewItem.__init__(self, parent, path)
        self._populated = False
        self.setExpandable(True)

    def populate(self):
        """Populate the entry with children, one level deep."""
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
    """

    # XXX The regex matches are done in unicode, that is, the rel_path of
    # FileItem objects is converted with util.unicode_from_path. Would it be
    # better (more efficient?) to encode string_ to filesystem_encoding instead?

    # TODO I think it would be nice to automatically open all search results,
    # or something similar (to recursively open clicked top level items).

    def __init__(self, *args):
        kdeui.KListViewSearchLine.__init__(self, *args)
        self.string = None
        self.regexes = []

    def itemMatches(self, item, string_):
        string_ = unicode(string_).strip()
        if string_:
            if string_ != self.string:
                self.string = string_
                self.regexes = [ re.compile(re.escape(pat), re.I)
                                               for pat in string_.split() ]
        else:
            return True

        try:
            item_text = util.unicode_from_path(item.rel_path)
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

def _populate_tree(parent, directory):
    """A helper function to populate either a TreeView or a DirectoryItem."""
    try:
        files = os.listdir(directory)
    except OSError, e:
        minirok.logger.warn('could not list directory: %s', e)
        return

    for filename in files:
        path = os.path.join(directory, filename)
        if os.path.isdir(path):
            DirectoryItem(parent, path)
        else:
            FileItem(parent, path)
