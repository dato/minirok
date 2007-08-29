#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import os
import re

import qt
import kdeui

import minirok
from minirok import drag, engine, util

##

class TreeView(kdeui.KListView):

    def __init__(self, *args):
        kdeui.KListView.__init__(self, *args)
        self.root = None
        self.timer = qt.QTimer(self, 'tree view timer')
        self.iterator = None
        self.automatically_opened = set()

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

        self.connect(self, qt.SIGNAL('doubleClicked(QListViewItem *, const QPoint &, int)'),
                self.slot_append_selected)

        self.connect(self, qt.SIGNAL('returnPressed(QListViewItem *)'),
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

    def slot_show_directory(self, directory):
        """Changes the TreeView root to the specified directory."""
        self.clear()
        self.automatically_opened.clear()
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

        def _visible_children(toplevel):
            visible_children = []
            item = toplevel.firstChild()
            while item:
                if item.isVisible():
                    visible_children.append(item)
                item = item.nextSibling()
            return visible_children

        pending = _visible_children(self)
        toplevel_count = len(pending)
        i = 0
        while pending:
            i += 1
            item = pending.pop(0)
            visible_children = _visible_children(item)
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

class TreeViewItem(kdeui.KListViewItem):

    IS_DIR = 0

    def __init__(self, parent, path):
        self.path = path
        self.root = parent.root
        self.rel_path = re.sub('^%s/*' % re.escape(self.root), '', path)
        # optimization for TreeViewSearchLine.itemMatches() below
        self.unicode_rel_path = util.unicode_from_path(self.rel_path)

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

    When the user stops typing, a search_finished(bool empty_search) signal is
    emitted.
    """
    def __init__(self, *args):
        kdeui.KListViewSearchLine.__init__(self, *args)
        self.string = None
        self.regexes = []
        self.timer = qt.QTimer(self, 'tree search line timer')

        self.connect(self.timer, qt.SIGNAL('timeout()'),
                self.slot_emit_search_finished)

    def slot_emit_search_finished(self):
        self.emit(qt.PYSIGNAL('search_finished'), (self.string is None,))

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
        self.timer.start(400, True) # True: single-shot

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
        elif minirok.Globals.engine.can_play(path):
            FileItem(parent, path)
