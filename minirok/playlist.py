#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007-2008 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import os
import re
import errno

from PyQt4.QtCore import Qt
from PyQt4 import QtGui, QtCore
from PyKDE4 import kdeui, kdecore

import minirok
from minirok import drag, engine, tag_reader, util

##

class Playlist(QtCore.QAbstractTableModel, util.HasConfig):#, util.HasGUIConfig):
    # This is the value self.current_item has whenver just the first item on
    # the playlist should be used. Only set to this value when the playlist
    # contains items!
    FIRST_ITEM = object()

    def __init__(self, *args):
        QtCore.QAbstractTableModel.__init__(self, *args)
        util.HasConfig.__init__(self)
        # util.HasGUIConfig.__init__(self)

        # Core model stuff
        self._itemlist = []
        self._itemdict = {} # { item: position, ... }
        self._row_count = 0
        self._empty_model_index = QtCore.QModelIndex()
        self._column_count = len(PlaylistItem.ALLOWED_TAGS)

        self.queue = []
        self.visualizer_rect = None
        self.stop_mode = StopMode.NONE
        self.tag_reader = tag_reader.TagReader()
        self.random_queue = util.RandomOrderedList()

        self.tag_reader.start()

        # these have a property() below
        self._stop_after = None
        self._repeat_mode = RepeatMode.NONE
        self._random_mode = False
        self._current_item = None
        self._currently_playing = None

        self._currently_playing_taken = False

        self.connect(self, QtCore.SIGNAL('list_changed'), self.slot_list_changed)

        self.connect(self.tag_reader, QtCore.SIGNAL('items_ready'),
                self.slot_update_tags)

        self.connect(minirok.Globals.engine, QtCore.SIGNAL('status_changed'),
                self.slot_engine_status_changed)

        self.connect(minirok.Globals.engine, QtCore.SIGNAL('end_of_stream'),
                self.slot_engine_end_of_stream)

        self.init_actions()
        self.init_undo_stack()
        self.apply_preferences()
        self.load_saved_playlist()

    ##

    """Model functions."""

    def rowCount(self, parent=None):
        if parent is None or parent == self._empty_model_index:
            return self._row_count
        else:
            return 0 # as per QAbstractItemModel::rowCount docs

    def columnCount(self, parent=None):
        return self._column_count

    def data(self, index, role):
        row = index.row()
        column = index.column()

        if (role != Qt.DisplayRole
                or not index.isValid()
                or row > self._row_count
                or column > self._column_count):
            return QtCore.QVariant()
        else:
            return QtCore.QVariant(QtCore.QString(
                        self._itemlist[row].tag_by_index(column) or ''))

    def headerData(self, section, orientation, role):
        if (role == Qt.DisplayRole and orientation == Qt.Horizontal):
            return QtCore.QVariant(
                    QtCore.QString(PlaylistItem.ALLOWED_TAGS[section]))
        else:
            return QtCore.QVariant()

    ##

    """Methods used by the view, header, and delegate."""

    def sorted_column_names(self):
        return PlaylistItem.ALLOWED_TAGS[:]

    def row_is_stop_after(self, row):
        assert 0 <= row < self._row_count
        return self._itemlist[row] is self.stop_after

    def row_is_current(self, row):
        assert 0 <= row < self._row_count
        return self._itemlist[row] is self.current_item

    def row_is_playing(self, row):
        assert 0 <= row < self._row_count
        return self._itemlist[row] is self.currently_playing

    def row_queue_position(self, row):
        if not self.queue:
            return 0
        else:
            assert 0 <= row < self._row_count
            try:
                return self.queue.index(self._itemlist[row]) + 1
            except ValueError:
                return 0

    ## 

    """Drag and drop functions."""

    PLAYLIST_DND_MIME_TYPE = 'application/x-minirok-playlist-dnd'

    def supportedDropActions(self):
        return Qt.CopyAction | Qt.MoveAction

    def mimeTypes(self):
        types = QtCore.QStringList()
        types.append('text/uri-list')
        types.append(self.PLAYLIST_DND_MIME_TYPE)
        return types

    def flags(self, index):
        if index.isValid():
            return (Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled)
        else:
            return Qt.ItemIsDropEnabled

    def mimeData(self, indexes):
        """Encodes a list of the rows in indexes."""
        mimedata = QtCore.QMimeData()
        bytearray = QtCore.QByteArray()
        datastream = QtCore.QDataStream(bytearray, QtCore.QIODevice.WriteOnly)
        rows = set(x.row() for x in indexes)
        datastream.writeUInt32(len(rows))
        for row in rows:
            datastream.writeUInt32(row)
        mimedata.setData(self.PLAYLIST_DND_MIME_TYPE, bytearray)
        return mimedata

    def dropMimeData(self, mimedata, action, row, column, index):
        if mimedata.hasUrls():
            files = map(util.kurl_to_path,
                            kdecore.KUrl.List.fromMimeData(mimedata))

            if not mimedata.hasFormat(drag.FileListDrag.MIME_TYPE):
                # Drop does not come from ourselves, so:
                files = util.playable_from_untrusted(files, warn=False)

            if (QtGui.QApplication.keyboardModifiers() & Qt.ControlModifier):
                row = -1

            self.add_files(files, position=row)
            return True

        elif mimedata.hasFormat(self.PLAYLIST_DND_MIME_TYPE):
            bytearray = mimedata.data(self.PLAYLIST_DND_MIME_TYPE)
            datastream = QtCore.QDataStream(bytearray, QtCore.QIODevice.ReadOnly)
            rows = set(datastream.readUInt32()
                        for x in range(datastream.readUInt32()))

            if row < 0:
                row = self._row_count

            # now, we remove items after the drop, so...
            row -= len(filter(lambda r: r <= row, rows))

            self.undo_stack.beginMacro('')
            try:
                InsertItemsCmd(self, row, RemoveItemsCmd(self, rows).get_items())
            finally:
                self.undo_stack.endMacro()

            # restore the selection: better UI experience
            top = self.index(row, 0, QtCore.QModelIndex())
            bottom = self.index(row + len(rows) - 1, 0, QtCore.QModelIndex())
            self.selection_model.select(QtGui.QItemSelection(top, bottom),
                    QtGui.QItemSelectionModel.Rows
                    | QtGui.QItemSelectionModel.ClearAndSelect)
            self.selection_model.setCurrentIndex(
                    min(rows) > row and top or bottom, # \o/
                    QtGui.QItemSelectionModel.Rows
                    | QtGui.QItemSelectionModel.NoUpdate)
            return True

        else:
            return False

    ##

    """Adding and removing *items*.
    
    This updates both _itemlist and _itemdict. No other functions should modify
    these two variables.
    """

    def insert_items(self, position, items):
        try:
            nitems = len(items)
            if position < self._row_count: # not appending
                for item, row in self._itemdict.iteritems():
                    if row >= position:
                        self._itemdict[item] += nitems
            self._itemdict.update((item, position+i)
                    for i, item in enumerate(items))
            self.beginInsertRows(QtCore.QModelIndex(),
                                 position, position + nitems - 1)
            self._itemlist[position:0] = items
            self._row_count += nitems
        finally:
            self.endInsertRows()

        self.emit(QtCore.SIGNAL('list_changed'))

    def remove_items(self, position, amount):
        items = self._itemlist[position:position+amount]
        try:
            for item in items:
                del self._itemdict[item]
            if position + amount <= self._row_count: # not tail removal
                for item, row in self._itemdict.iteritems():
                    if row > position:
                        self._itemdict[item] -= amount
            self.beginRemoveRows(QtCore.QModelIndex(),
                                 position, position + amount - 1)
            self._itemlist[position:position+amount] = []
            self._row_count -= amount
        finally:
            self.endRemoveRows()

        self.emit(QtCore.SIGNAL('list_changed'))
        return items

    ##

    """Initialization."""

    def init_actions(self):
        self.action_play = util.create_action('action_play', 'Play',
                self.slot_play, 'media-playback-start')

        self.action_pause = util.create_action('action_pause', 'Pause',
                self.slot_pause, 'media-playback-pause', factory=kdeui.KToggleAction)

        self.action_play_pause = util.create_action('action_play_pause', 'Play/Pause',
                self.slot_play_pause, 'media-playback-start', 'Ctrl+P',# 'Ctrl+Alt+P',
                factory=kdeui.KToggleAction)

        self.action_stop = util.create_action('action_stop', 'Stop',
                self.slot_stop, 'media-playback-stop', 'Ctrl+O',# 'Ctrl+Alt+I,O',
                factory=StopAction)

        self.action_next = util.create_action('action_next', 'Next',
                self.slot_next, 'media-skip-forward', 'Ctrl+N')#, 'Ctrl+Alt+I,N')

        self.action_previous = util.create_action('action_previous', 'Previous',
                self.slot_previous, 'media-skip-backward', 'Ctrl+I')#, 'Ctrl+Alt+I,P')

        # Note: the icon here is named minirok_foo-bar and not minirok-foo-bar,
        # because if it isn't found, minirok-* seems to select the minirok.png
        # icon automatically. And I'd rather have the "unknown icon" icon instead.
        self.action_clear = util.create_action('action_clear_playlist', 'Clear playlist',
                self.slot_clear, 'minirok_playlist-clear', 'Ctrl+L')

        self.action_toggle_stop_after_current = util.create_action(
                'action_toggle_stop_after_current', 'Stop after current',
                self.slot_toggle_stop_after_current, 'media-playback-stop',
                'Ctrl+K')#, 'Ctrl+I+K')

    def init_undo_stack(self):
        self.undo_stack = QtGui.QUndoStack(self)

        self.undo_action = self.undo_stack.createUndoAction(self)
        self.redo_action = self.undo_stack.createRedoAction(self)

        self.undo_action.setIcon(kdeui.KIcon('edit-undo'))
        self.redo_action.setIcon(kdeui.KIcon('edit-redo'))

        ac = minirok.Globals.action_collection
        ac.addAction('action_playlist_undo', self.undo_action)
        ac.addAction('action_playlist_redo', self.redo_action)

        # Now, we need this for the shortcuts to be configurable...
        # Note: not using KStandardAction.undo()/redo(), because they'll want
        # to appear in the main toolbar, and we want that one to be empty.
        self.undo_kaction = util.create_action('kaction_playlist_undo',
                'Undo', self.undo_stack.undo, 'edit-undo',
                kdeui.KStandardShortcut.shortcut(kdeui.KStandardShortcut.Undo))
        self.redo_kaction = util.create_action('kaction_playlist_redo',
                'Redo', self.undo_stack.redo, 'edit-redo',
                kdeui.KStandardShortcut.shortcut(kdeui.KStandardShortcut.Redo))

    ##

    """Properties."""

    def _set_stop_after(self, value):
        rows = []

        def dry():
            """Don't repeat yourself."""
            if self._stop_after is not None:
                rows.append(self._itemdict[self._stop_after])

        dry()
        self._stop_after = value
        dry()

        if value is None:
            self.stop_mode = StopMode.NONE

        if rows:
            self.my_emit_dataChanged(
                    rows[0], rows[-1], PlaylistItem.TRACK_COLUMN_INDEX)

    stop_after = property(lambda self: self._stop_after, _set_stop_after)

    def _set_repeat_mode(self, value):
        self._repeat_mode = value # TODO Check it's a valid value?
        self.emit(QtCore.SIGNAL('list_changed'))

    repeat_mode = property(lambda self: self._repeat_mode, _set_repeat_mode)

    def _set_random_mode(self, value):
        self._random_mode = bool(value)
        self.emit(QtCore.SIGNAL('list_changed'))

    random_mode = property(lambda self: self._random_mode, _set_random_mode)

    def _set_current_item(self, value):
        rows = []

        def dry():
            if self._current_item not in (self.FIRST_ITEM, None):
                rows.append(self._itemdict[self._current_item])

        dry()

        if not (value is self.FIRST_ITEM and self._row_count == 0):
            self._current_item = value
            try:
                self.random_queue.remove(value)
            except ValueError:
                pass
        else:
            self._current_item = None

        dry()

        self.emit(QtCore.SIGNAL('list_changed'))
        self.my_emit_dataChanged(rows[0], rows[-1]) # XXX if rows?

    current_item = property(lambda self: self._current_item, _set_current_item)

    def _set_currently_playing(self, item):
        rows = []

        def dry():
            if self._currently_playing not in (self.FIRST_ITEM, None):
                rows.append(self._itemdict[self._currently_playing])

        dry()
        self._currently_playing = item
        self._currently_playing_taken = False # XXX-KDE4 Needed?
        dry()

        self.my_emit_dataChanged(rows[0], rows[-1]) # XXX if rows?

    currently_playing = property(lambda self: self._currently_playing, _set_currently_playing)

    ##

    """Maintain the state of actions current."""

    def slot_list_changed(self):
        if self._row_count == 0:
            self._current_item = None # can't use the property here
            self.action_next.setEnabled(False)
            self.action_clear.setEnabled(False)
            self.action_previous.setEnabled(False)
        else:
            if self.current_item is None:
                self._current_item = self.FIRST_ITEM
            if self.current_item is self.FIRST_ITEM:
                current = 0
            else:
                current = self._itemdict[self.current_item]
            self.action_clear.setEnabled(True)
            self.action_previous.setEnabled(current > 0)
            self.action_next.setEnabled(bool(self.queue
                    or self.repeat_mode == RepeatMode.PLAYLIST
                    or (self.random_mode and self.random_queue)
                    or (not self.random_mode and current+1 < self._row_count)))

        self.slot_engine_status_changed(minirok.Globals.engine.status)

    def slot_engine_status_changed(self, new_status):
        if new_status == engine.State.STOPPED:
            self.action_stop.setEnabled(False)
            self.action_pause.setEnabled(False)
            self.action_pause.setChecked(False)
            self.action_play.setEnabled(self._row_count > 0)
            self.action_play_pause.setChecked(False)
            self.action_play_pause.setEnabled(self._row_count > 0)
            self.action_play_pause.setIcon(kdeui.KIcon('media-playback-start'))

        elif new_status == engine.State.PLAYING:
            self.action_stop.setEnabled(True)
            self.action_pause.setEnabled(True)
            self.action_pause.setChecked(False)
            self.action_play_pause.setChecked(False)
            self.action_play_pause.setIcon(kdeui.KIcon('media-playback-pause'))

        elif new_status == engine.State.PAUSED:
            self.action_pause.setChecked(True)
            self.action_play_pause.setChecked(True)

    ##

    # XXX-KDE4 TODO
    def slot_clear(self):
        self.queue[:] = []
        self.random_queue[:] = []
        self.tag_reader.clear_queue()

        if self._currently_playing not in (self.FIRST_ITEM, None):
            # We don't want the currently playing item to be deleted,
            # because it breaks actions upon it, eg. stop().
            self.takeItem(self._currently_playing)

        if self.stop_after is not None:
            if (self.stop_mode == StopMode.AFTER_ONE
                    and self.stop_after != self._currently_playing):
                self.stop_after = None
            elif self.stop_mode == StopMode.AFTER_QUEUE:
                self._stop_after = None # don't touch stop_mode

        self.clear()
        self.emit(QtCore.SIGNAL('list_changed'))

    # XXX-KDE4 TODO
    def xxx_kde4_remove_items(self, items):
        if not items:
            return

        for item in items:
            self.takeItem(item)
            self.tag_reader.dequeue(item)
            self.toggle_enqueued(item, only_dequeue=True)
            try:
                self.random_queue.remove(item)
            except ValueError:
                pass
            if item == self.current_item:
                self.current_item = self.FIRST_ITEM
            if item != self._currently_playing:
                del item # maybe memory gets freed even without this?

        self.emit(QtCore.SIGNAL('list_changed'))

    # XXX-KDE4 TODO
    def slot_activate_index(self, index):
        self.maybe_populate_random_queue()
        self.current_item = item
        self.slot_play()

    # XXX-KDE4 TODO
    def slot_play_first_visible(self, search_string):
        if not unicode(search_string).strip():
            return
        self.current_item = qt.QListViewItemIterator(self,
                qt.QListViewItemIterator.Visible).current()
        self.slot_play()

    def slot_update_tags(self):
        rows = []

        for item, tags in self.tag_reader.pop_done():
            item.update_tags(tags)
            rows.append(self._itemdict[item])

        if rows:
            rows.sort()
            self.my_emit_dataChanged(rows[0], rows[-1])

    ##

    """Actions."""

    def slot_play(self):
        if self.current_item is not None:
            if self.current_item is self.FIRST_ITEM:
                if self.queue:
                    self.current_item = self.queue_pop(0)
                else:
                    self.current_item = self.my_first_child()

            self.currently_playing = self.current_item
            minirok.Globals.engine.play(self.current_item.path)

            if self.current_item.tags()['Length'] is None:
                tags = tag_reader.TagReader.tags(self.current_item.path)
                self.current_item.update_tags({'Length': tags.get('Length', 0)})
                self.my_emit_dataChanged(self._itemdict[self.current_item])

            self.emit(QtCore.SIGNAL('new_track'))

    def slot_pause(self):
        e = minirok.Globals.engine
        if e.status == engine.State.PLAYING:
            e.pause(True)
        elif e.status == engine.State.PAUSED:
            e.pause(False)

    def slot_play_pause(self):
        if minirok.Globals.engine.status == engine.State.STOPPED:
            self.slot_play()
        else:
            self.slot_pause()

    def slot_stop(self):
        if minirok.Globals.engine.status != engine.State.STOPPED:
            self.currently_playing = None
            minirok.Globals.engine.stop()

    def slot_next(self, force_play=False):
        if self.current_item is not None:
            if self.queue:
                next = self.queue_pop(0)
            elif self.random_mode:
                try:
                    next = self.random_queue.pop(0)
                except IndexError:
                    next = None
                    self.maybe_populate_random_queue()
            elif self.current_item is self.FIRST_ITEM:
                next = self.my_first_child()
            else:
                index = self._itemdict[self.current_item] + 1
                if index < self._row_count:
                    next = self._itemlist[index]
                else:
                    next = None

            if next is None and self.repeat_mode is RepeatMode.PLAYLIST:
                next = self.my_first_child()

            if next is None:
                if self.random_mode:
                    self.current_item = self.random_queue[0]
                else:
                    self.current_item = self.FIRST_ITEM
            else:
                self.current_item = next
                if (force_play
                    or minirok.Globals.engine.status != engine.State.STOPPED):
                    self.slot_play()

    def slot_previous(self):
        if self.current_item not in (self.FIRST_ITEM, None):
            index = self._itemdict[self.current_item] - 1
            if index >= 0:
                self.current_item = self._itemlist[index]
                if minirok.Globals.engine.status != engine.State.STOPPED:
                    self.slot_play()

    # XXX-KDE4 TODO
    def slot_engine_end_of_stream(self, uri):
        self.currently_playing = None

        if (self.stop_mode == StopMode.AFTER_ONE or
                (self.stop_mode == StopMode.AFTER_QUEUE and not self.queue)):
            if self.stop_after is not None:
                if self.stop_after.path == re.sub('^file://', '', uri):
                    self.stop_after = None
                    self.slot_next(force_play=False)
                    return
            elif self.stop_mode == StopMode.AFTER_ONE: # AFTER_QUEUE is ok
                minirok.logger.warn(
                        'BUG: stop_after is None with stop_mode = AFTER_ONE')

        if self.repeat_mode == RepeatMode.TRACK:
            # This can't be in slot_next() because the next button should move
            # to the next track *even* with repeat_mode == TRACK.
            self.slot_play()
        else:
            self.slot_next(force_play=True)

    ##

    def slot_toggle_stop_after_current(self):
        current = self.currently_playing or self.current_item

        if current not in (self.FIRST_ITEM, None):
            self.toggle_stop_after(self._itemdict[current])

    def toggle_stop_after(self, row):
        assert 0 <= row < self._row_count

        item = self._itemlist[row]

        if item == self.stop_after:
            self.stop_after = None
        else:
            self.stop_after = item
            self.stop_mode = StopMode.AFTER_ONE

    def toggle_enqueued(self, row, only_dequeue=False):
        assert 0 <= row < self._row_count

        item = self._itemlist[row]
        try:
            index = self.queue.index(item)
        except ValueError:
            if only_dequeue:
                return # do not emit list_changed
            self.queue.append(item)
            if self.stop_mode == StopMode.AFTER_QUEUE:
                self.stop_after = item # this repaints
            else:
                self.my_emit_dataChanged(row, row,
                        PlaylistItem.TRACK_COLUMN_INDEX)
        else:
            item = self.queue_pop(index)
            if (index == len(self.queue) # not len-1, 'coz we already popped()
                    and self.stop_mode == StopMode.AFTER_QUEUE):
                try:
                    self.stop_after = self.queue[-1]
                except IndexError:
                    self.stop_after = None
                    self.stop_mode = StopMode.AFTER_QUEUE

        self.emit(QtCore.SIGNAL('list_changed'))

    def queue_pop(self, index):
        """Pops an item from self.queue, and repaints the necessary items."""
        try:
            popped = self.queue.pop(index)
        except IndexError:
            minirok.logger.warn('invalid index %r in queue_pop()', index)
        else:
            rows = map(self._itemdict.get, [ popped ] + self.queue[index:])
            rows.sort()
            self.my_emit_dataChanged(rows[0], rows[-1],
                                     PlaylistItem.TRACK_COLUMN_INDEX)

            return popped

    def my_first_child(self):
        """Return the first item to be played, honouring random_mode."""
        if self.random_mode:
            self.maybe_populate_random_queue()
            return self.random_queue.pop(0)
        else:
            return self._itemlist[0]

    def maybe_populate_random_queue(self):
        if not self.random_queue:
            self.random_queue.extend(self._itemlist)

    ##

    # XXX-KDE4 TODO
    def apply_preferences(self):
        self._regex = None
        self._regex_mode = 'Always'
        return # XXX-KDE4

        prefs = minirok.Globals.preferences

        if prefs.tags_from_regex:
            try:
                self._regex = re.compile(prefs.tag_regex)
            except re.error, e:
                minirok.logger.error('invalid regular expresion %s: %s',
                        prefs.tag_regex, e)
                self._regex = None
                self._regex_mode = 'Always'
            else:
                self._regex_mode = prefs.tag_regex_mode
        else:
            self._regex = None
            self._regex_mode = 'Always'

    ##

    def slot_save_config(self):
        """Saves the current playlist."""
        paths = [ item.path for item in self._itemlist ]

        try:
            playlist = file(self.saved_playlist_path(), 'w')
        except IOError, e:
            minirok.logger.error('could not save playlist: %s', e)
        else:
            playlist.write('\0'.join(paths))
            playlist.close()

    def load_saved_playlist(self):
        try:
            playlist = file(self.saved_playlist_path())
        except IOError, e:
            if e.errno == errno.ENOENT:
                pass
            else:
                minirok.logger.warning('error opening saved playlist: %s', e)
        else:
            files = re.split(r'\0+', playlist.read())
            if files != ['']: # empty saved playlist
                # add_files_untrusted() will use InsertItemsCmd, and here
                # that wouldn't be appropriate: cook up the code ourselves.
                self.insert_items(0, map(self.create_item,
                    util.playable_from_untrusted(files, warn=True)))

        self.slot_list_changed()

    @staticmethod
    def saved_playlist_path():
        appdata = str(kdecore.KGlobal.dirs().saveLocation('appdata'))
        return os.path.join(appdata, 'saved_playlist.txt')

    ##

    def add_files(self, files, position=-1):
        """Add the given files to the playlist at a given position.

        If position is < 0, files will be added at the end of the playlist.
        """
        if position < 0:
            position = self._row_count

        if files:
            items = map(self.create_item, files)
            InsertItemsCmd(self, position, items)

    def add_files_untrusted(self, files, clear_playlist=False):
        """Add to the playlist those files that exist and are playable."""
        if clear_playlist:
            self.slot_clear()

        self.add_files(util.playable_from_untrusted(files, warn=True))

    def create_item(self, path):
        tags = self.tags_from_filename(path)
        if len(tags) == 0 or tags.get('Title', None) is None:
            regex_failed = True
            dirname, filename = os.path.split(path)
            tags['Title'] = util.unicode_from_path(filename)
        else:
            regex_failed = False

        if (self._currently_playing_taken
                and False # XXX-KDE4
                and self._currently_playing is not None
                and self._currently_playing.path == file_):
            item = self._currently_playing
            self.insertItem(item)
            item.moveItem(prev_item)
            self.current_item = item
            self.currently_playing = item # unsets _currently_playing_taken
        else:
            item = PlaylistItem(path, tags)
            self.random_queue.append(item)

        assert self._regex_mode in ['Always', 'OnRegexFail', 'Never']

        if self._regex_mode == 'Always' or (regex_failed
                and self._regex_mode == 'OnRegexFail'):
            self.tag_reader.queue(item)

        return item

    def tags_from_filename(self, path):
        if self._regex is None:
            return {}
        else:
            match = self._regex.search(path)
            if match is None:
                return {}

        tags = {}

        for group, match in match.groupdict().items():
            group = group.capitalize()
            if group in PlaylistItem.ALLOWED_TAGS and match is not None:
                tags[group] = util.unicode_from_path(match)

        return tags

    ##

    # XXX-KDE4 TODO
    def setColumnWidth(self, col, width):
        self.header().setResizeEnabled(bool(width), col) # Qt does not do this for us
        return kdeui.KListView.setColumnWidth(self, col, width)

    # XXX-KDE4 TODO
    def takeItem(self, item):
        if item == self._currently_playing:
            self._currently_playing_taken = True
        return kdeui.KListView.takeItem(self, item)

    # XXX-KDE4 TODO
    def contentsDragMoveEvent(self, event):
        if (not (kdecore.KApplication.kApplication().keyboardMouseState()
                    & qt.Qt.ControlButton)
                or not drag.FileListDrag.canDecode(event)):
            if self.visualizer_rect is not None:
                self.viewport().repaint(self.visualizer_rect, True)
                self.visualizer_rect = None
            return kdeui.KListView.contentsDragMoveEvent(self, event)
        else:
            try:
                self.cleanDropVisualizer()
                self.setDropVisualizer(False)
                rect = self.drawDropVisualizer(None, None, self.lastChild())
                if rect != self.visualizer_rect:
                    self.visualizer_rect = rect
                    brush = qt.QBrush(qt.Qt.Dense4Pattern)
                    painter = qt.QPainter(self.viewport())
                    painter.fillRect(self.visualizer_rect, brush)
                return kdeui.KListView.contentsDragMoveEvent(self, event)
            finally:
                self.setDropVisualizer(True)

    ##

    """Misc. helpers."""

    def my_emit_dataChanged(self, row1, row2=None, column=None):
        """Emit dataChanged() between sorted([row1, row2]).

        If :param row2: is None, it will default to row1.
        If :param column: is not None, only include that column in the signal.
        """
        if row2 is None:
            row2 = row1
        elif row1 > row2:
            row1, row2 = row2, row1

        if column is None:
            col1 = 0
            col2 = self.columnCount() - 1
        else:
            col1 = col2 = column

        self.emit(QtCore.SIGNAL(
                    'dataChanged(const QModelIndex &, const QModelIndex &)'),
                    self.index(row1, col1), self.index(row2, col2))

    ##

    def get_current_tags(self):
        """Return the tags of the currently played item, if any."""
        if self.currently_playing is not None:
            return self.currently_playing.tags()
        else:
            return {}

##

class RepeatMode:
    NONE = object()
    TRACK = object()
    PLAYLIST = object()

class StopMode:
    NONE = object()
    AFTER_ONE = object()
    AFTER_QUEUE = object()

class StopAction(kdeui.KToolBarPopupAction):

    def __init__(self, *args):
        kdeui.KToolBarPopupAction.__init__(self, kdeui.KIcon(), "", None)

        menu = self.menu()
        menu.addTitle('Stop')

        self.action_now = menu.addAction('Now')
        self.action_after_current = menu.addAction('After current')
        self.action_after_queue = menu.addAction('After queue')

        self.connect(menu, QtCore.SIGNAL('aboutToShow()'), self.slot_prepare)
        self.connect(menu, QtCore.SIGNAL('triggered(QAction *)'), self.slot_activated)

    def slot_prepare(self):
        playlist = minirok.Globals.playlist

        if (playlist.stop_mode == StopMode.AFTER_ONE
                and playlist.stop_after == playlist.currently_playing):
            self.action_after_current.setCheckable(True)
            self.action_after_current.setChecked(True)
        else:
            self.action_after_current.setCheckable(False)

        if playlist.stop_mode == StopMode.AFTER_QUEUE:
            self.action_after_queue.setCheckable(True)
            self.action_after_queue.setChecked(True)
        else:
            self.action_after_queue.setCheckable(False)

    def slot_activated(self, action):
        playlist = minirok.Globals.playlist

        if action is self.action_now:
            self.trigger()

        elif action is self.action_after_current:
            playlist.slot_toggle_stop_after_current()

        elif action is self.action_after_queue:
            if playlist.stop_mode == StopMode.AFTER_QUEUE:
                playlist.stop_after = None
            else:
                playlist.stop_after = None # clear possible AFTER_ONE mode
                playlist.stop_mode = StopMode.AFTER_QUEUE
                if playlist.queue:
                    playlist.stop_after = playlist.queue[-1]

##

class PlaylistView(QtGui.QTreeView):

    def __init__(self, playlist):
        QtGui.QTreeView.__init__(self)

        self.setModel(playlist)
        self.setRootIsDecorated(False)
        self.setDropIndicatorShown(True)
        self.setAllColumnsShowFocus(True)
        self.setDragDropMode(self.DragDrop)
        self.setSelectionBehavior(self.SelectRows)
        self.setSelectionMode(self.ExtendedSelection)

        columns = Columns(self)
        self.setHeader(columns)
        columns.setup_from_config()

        self.track_delegate = PlaylistTrackDelegate()
        self.setItemDelegateForColumn(
                self.model().sorted_column_names().index('Track'),
                self.track_delegate)

        self.connect(self, QtCore.SIGNAL('activated(const QModelIndex &)'),
                playlist.slot_activate_index)

        # ok, this is a bit gross
        playlist.selection_model = self.selectionModel()

    ##

    def selected_rows(self):
        # The set is needed here because there is an index per row/column
        return set(x.row() for x in self.selectedIndexes())

    def unselected_rows(self):
        selected = self.selected_rows()
        all = set(range(self.model().rowCount()))
        return all - selected

    ##

    def drawRow(self, painter, styleopt, index):
        row = index.row()
        model = self.model()

        if model.row_is_playing(row):
            styleopt = QtGui.QStyleOptionViewItem(styleopt) # make a copy
            styleopt.font.setItalic(True)

        QtGui.QTreeView.drawRow(self, painter, styleopt, index)

        if model.row_is_current(row):
            painter.save()
            r = styleopt.rect
            painter.setPen(styleopt.palette.highlight().color())
            painter.drawRect(r.x(), r.y(), r.width(), r.height())
            painter.restore()

    def startDrag(self, actions):
        # Override this function to loose the ugly pixmap provided by Qt
        indexes = self.selectedIndexes()
        if len(indexes) > 0:
            mimedata = self.model().mimeData(indexes)
            drag = QtGui.QDrag(self)
            drag.setMimeData(mimedata)
            drag.setPixmap(QtGui.QPixmap(1, 1))
            drag.exec_(actions)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete:
            event.accept()
            RemoveItemsCmd(self.model(), self.selected_rows())
        else:
            return QtGui.QTreeView.keyPressEvent(self, event)

    def mousePressEvent(self, event):
        button = event.button()
        keymod = QtGui.QApplication.keyboardModifiers()
        index = self.indexAt(event.pos())

        # TODO: accept event?

        if not index.isValid():
            # click on viewport
            self.clearSelection()

        elif keymod & Qt.ControlModifier:
            if button & Qt.RightButton:
                self.model().toggle_enqueued(index.row())
            elif button & Qt.MidButton:
                self.model().toggle_stop_after(index.row())
            else:
                return QtGui.QTreeView.mousePressEvent(self, event)

        elif button & Qt.MidButton:
            if self.model().row_is_playing(index.row()):
                self.model().slot_pause()

        elif button & Qt.RightButton:
            QtGui.QTreeView.mousePressEvent(self, event)

            menu = kdeui.KMenu(self)
            selected_rows = self.selected_rows()
            assert len(selected_rows) > 0 # or maybe use itemAt()

            if len(selected_rows) == 1:
                enqueue_action = menu.addAction('Enqueue track')
                if self.model().row_queue_position(index.row()) > 0:
                    enqueue_action.setCheckable(True)
                    enqueue_action.setChecked(True)
            else:
                enqueue_action = menu.addAction('Enqueue/Dequeue tracks')

            stop_after_action = menu.addAction('Stop playing after this track')

            if index.model().row_is_stop_after(index.row()):
                stop_after_action.setCheckable(True)
                stop_after_action.setChecked(True)

            crop_action = menu.addAction('Crop tracks')

            ##

            selected_action = menu.exec_(event.globalPos())

            if selected_action == enqueue_action:
                model = self.model()
                for row in selected_rows:
                    model.toggle_enqueued(row)
            elif selected_action == stop_after_action:
                self.model().toggle_stop_after(index.row())
            elif selected_action == crop_action:
                RemoveItemsCmd(self.model(), self.unselected_rows())

        else:
            return QtGui.QTreeView.mousePressEvent(self, event)

##

class PlaylistItem(object):

    # This class should be considered sort of private to the model

    ALLOWED_TAGS = [ 'Track', 'Artist', 'Album', 'Title', 'Length' ]

    TRACK_COLUMN_INDEX = 0 # used by the model

    def __init__(self, path, tags=None):
        self.path = path

        # XXX-KDE4
        # self._is_current = False
        # self._is_playing = False

        self._tags = dict((tag, None) for tag in self.ALLOWED_TAGS)

        if tags is not None:
            self.update_tags(tags)

    # XXX-KDE4 TODO
    def set_current(self, value=True):
        self._is_current = bool(value)

    # XXX-KDE4 TODO
    def set_playing(self, value=True):
        self._is_playing = bool(value)

    ##

    def tags(self):
        return self._tags.copy()

    def tag_text(self, tag):
        value = self._tags[tag]

        if tag == 'Length' and value is not None:
            return util.fmt_seconds(value)
        else:
            return value

    def tag_by_index(self, index):
        return self.tag_text(self.ALLOWED_TAGS[index])

    def update_tags(self, tags):
        for tag, value in tags.items():
            if tag not in self._tags:
                minirok.logger.warn('unknown tag %s', tag)
                continue
            if tag == 'Track':
                try:
                    # remove leading zeroes
                    value = str(int(value))
                except ValueError:
                    pass
            elif tag == 'Length':
                try:
                    value = int(value)
                except ValueError:
                    minirok.logger.warn('invalid length: %r', value)
                    continue

            self._tags[tag] = value

    ##

    # XXX-KDE4 TODO
    def paintFocus(self, painter, colorgrp, qrect):
        """Only allows focus to be painted in the current item."""
        if not self._is_current:
            return
        else:
            kdeui.KListViewItem.paintFocus(self, painter, colorgrp, qrect)

##

class PlaylistTrackDelegate(QtGui.QItemDelegate):
    """Paints the track number and the "stop after/queue pos" ellipse.
    
    Code originally comes from PlaylistItem::paintCell() in Amarok 1.4.
    """

    def paint(self, painter, option, index):
        QtGui.QItemDelegate.paint(self, painter, option, index)

        draw_stop = index.model().row_is_stop_after(index.row())
        queue_pos = index.model().row_queue_position(index.row())

        if draw_stop or queue_pos:
            painter.save()
            painter.translate(option.rect.x(), option.rect.y())

            width = option.rect.width()
            height = option.rect.height()

            e_width = 16
            e_margin = 2
            e_height = height - e_margin*2

            if draw_stop:
                s_width = 8
                s_height = 8
            else:
                s_width = s_height = 0

            if queue_pos:
                queue_pos = str(queue_pos)
                q_width = painter.fontMetrics().width(queue_pos)
                q_height = painter.fontMetrics().height()
            else:
                q_width = q_height = 0

            items_width = s_width + q_width

            painter.setBrush(option.palette.highlight())
            painter.setPen(option.palette.highlight().color().dark())
            painter.drawEllipse(width - items_width - e_width/2, e_margin, e_width, e_height)
            painter.drawRect(width - items_width, e_margin, items_width+1, e_height)
            painter.setPen(option.palette.highlight().color())
            painter.drawLine(width - items_width, e_margin+1, width - items_width, e_height+1)

            x = width - items_width - e_margin

            if draw_stop:
                y = e_height / 2 - s_height / 2 + e_margin
                painter.setBrush(QtGui.QColor(0, 0, 0))
                painter.drawRect(x, y, s_width, s_height)
                x += s_width + e_margin/2

            if queue_pos:
                painter.setPen(option.palette.highlightedText().color())
                painter.drawText(x, 0, width-x, q_height, Qt.AlignCenter, queue_pos)

            painter.restore()

##

class Columns(QtGui.QHeaderView, util.HasConfig):

    # We use a single configuration option, which contains the order in which
    # columns are to be displayed, their width, and whether they are hidden or
    # not.
    CONFIG_SECTION = 'Playlist'
    CONFIG_OPTION = 'Columns'
    CONFIG_OPTION_DEFAULT = \
            'Track:50:1,Artist:200:1,Album:200:0,Title:300:1,Length:75:1'

    def __init__(self, parent):
        QtGui.QHeaderView.__init__(self, Qt.Horizontal, parent)
        util.HasConfig.__init__(self)

        self.setMovable(True)
        self.setStretchLastSection(False)
        self.setDefaultAlignment(Qt.AlignLeft)
        self.setContextMenuPolicy(Qt.CustomContextMenu)

        self.connect(self,
                QtCore.SIGNAL('customContextMenuRequested(const QPoint&)'),
                self.exec_popup)

    def setup_from_config(self):
        """Read config, sanitize it, and apply."""

        class FakeConfingUntilPyKDE4Fixed:
            def hasKey(self, key):
                return False

        config = FakeConfingUntilPyKDE4Fixed()
        # config = kdecore.KGlobal.config().group(self.CONFIG_SECTION)

        if config.hasKey(self.CONFIG_OPTION):
            entries = map(str, config.readListEntry(self.CONFIG_OPTION)) # XXX-KDE4
        else:
            entries = self.CONFIG_OPTION_DEFAULT.split(',')

        columns = []
        warn = minirok.logger.warn
        known_columns = set(self.model().sorted_column_names())

        for entry in entries:
            try:
                name, width, visible = entry.split(':', 2)
            except ValueError:
                warn('skipping invalid entry in column config: %r', entry)
                continue

            try:
                width = int(width)
            except ValueError:
                warn('invalid column width for %s: %r', name, width)
                continue

            # TODO Maybe this one ought to be more flexible
            try:
                visible = bool(int(visible))
            except ValueError:
                warn('invalid visibility value for %s: %r', name, visible)
                continue
                    
            try:
                known_columns.remove(name)
            except KeyError:
                warn('skipping unknown or duplicated column: %r', name)
                continue

            columns.append((name, width, visible))

        if len(known_columns) > 0:
            defaults = dict((x.split(':')[0], map(int, x.split(':')[1:]))
                                for x in self.CONFIG_OPTION_DEFAULT.split(','))
            for c in known_columns:
                warn('column %s missing in config, adding with default values', c)
                width, visible = defaults[c]
                columns.append((c, width, visible))

        ##

        model_columns = self.model().sorted_column_names()

        for visual, (name, width, visible) in enumerate(columns):
            logical = model_columns.index(name)
            current = self.visualIndex(logical)

            if current != visual:
                self.moveSection(current, visual)

            self.resizeSection(logical, width)
            self.setSectionHidden(logical, not visible)

    ##

    def exec_popup(self, position):
        model = self.model()
        menu = kdeui.KMenu(self)
        menu.addTitle('Columns')

        for i in range(model.columnCount()):
            logindex = self.logicalIndex(i)
            name = model.headerData(logindex,
                    Qt.Horizontal, Qt.DisplayRole).toString()
            action = menu.addAction(name)
            action.setCheckable(True)
            action.setData(QtCore.QVariant(logindex))
            action.setChecked(not self.isSectionHidden(logindex))

        selected_action = menu.exec_(self.mapToGlobal(position))

        if selected_action is not None:
            hide = not selected_action.isChecked()
            column = selected_action.data().toInt()[0]
            self.setSectionHidden(column, hide)

    ##

    def slot_save_config(self):
        entries = [None] * self.count()

        for logical, name in enumerate(self.model().sorted_column_names()):
            width = self.sectionSize(logical) # TODO BUG: returns 0 if hidden
            visible = int(not self.isSectionHidden(logical))
            entry = '%s:%d:%d' % (name, width, visible)
            entries[self.visualIndex(logical)] = entry

        return # XXX-KDE4

        config = kdecore.KGlobal.config().group(self.CONFIG_SECTION)
        config.writeEntry(self.CONFIG_OPTION, entries)

##

"""Undoable commands to modify the contents of the playlist.

Note that they will add themselves to the model's QUndoStack.
"""

class InsertItemsCmd(QtGui.QUndoCommand):
    """Command to insert a list of items at a certain position."""

    def __init__(self, model, position, items):
        QtGui.QUndoCommand.__init__(self)

        self.model = model
        self.position = position
        self.items = items

        if len(items) > 0:
            self.model.undo_stack.push(self)

    def undo(self):
        self.items = self.model.remove_items(self.position, len(self.items))

    def redo(self):
        self.model.insert_items(self.position, self.items)


class RemoveItemsCmd(QtGui.QUndoCommand):
    """Command to remove a possibly not contiguous list of rows."""

    def __init__(self, model, rows):
        QtGui.QUndoCommand.__init__(self)

        self.model = model
        self.items = {}
        self.chunks = self.contiguous_chunks(rows)

        if len(rows) > 0:
            self.model.undo_stack.push(self)

    def undo(self):
        for position, items in sorted(self.items.items()):
            self.model.insert_items(position, items)

    def redo(self):
        for position, amount in reversed(self.chunks):
            self.items[position] = self.model.remove_items(position, amount)

    def get_items(self):
        """Return a list of all items removed by this command."""
        result = []
        for position, items in sorted(self.items.items()):
            result.extend(items)
        return result

    def contiguous_chunks(self, intlist):
        """Calculate a list of contiguous areas in a possibly unsorted list.

        >>> removecmd.contiguous_chunks([2, 9, 3, 5, 8, 1])
        [ (1, 3), (5, 1), (8, 2) ]
        """
        if len(intlist) == 0:
            return []

        mylist = sorted(intlist)
        result = [ [mylist[0], 1] ]

        for x in mylist[1:]:
            if x == sum(result[-1]):
                result[-1][1] += 1
            else:
                result.append([x, 1])

        return map(tuple, result)
