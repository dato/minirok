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
from minirok import drag, engine, proxy, tag_reader, util

##

class Playlist(QtCore.QAbstractTableModel):
    # This is the value self.current_item has whenver just the first item on
    # the playlist should be used. Only set to this value when the playlist
    # contains items!
    FIRST_ITEM = object()

    RoleQueuePosition    = Qt.UserRole + 1
    RoleQueryIsCurrent   = Qt.UserRole + 2
    RoleQueryIsPlaying   = Qt.UserRole + 3
    RoleQueryIsStopAfter = Qt.UserRole + 4

    def __init__(self, parent=None):
        QtCore.QAbstractTableModel.__init__(self, parent)
        util.CallbackRegistry.register_save_config(self.save_config)
        util.CallbackRegistry.register_apply_prefs(self.apply_preferences)

        # Core model stuff
        self._itemlist = []
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

        # XXX This is dataChanged() abuse: there are a bunch of places in which
        # the model wants to say: "my state (but not my data) changed somehow,
        # you may want to redraw your visible parts if you're paying attention
        # to state". I don't know of a method in the view that will do that
        # (redisplay the visible part calling with the appropriate drawRow()
        # and Delegate.paint() calls, without needing to refetch data()), so
        # I'm abusing dataChanged(0, 1) for this purpose, which seems to work!
        self.connect(self, QtCore.SIGNAL('repaint_needed'),
                            lambda: self.my_emit_dataChanged(0, 1))

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
        ret = None
        row = index.row()
        column = index.column()

        if (not index.isValid()
                or row > self._row_count
                or column > self._column_count):
            ret = None

        elif role == Qt.DisplayRole:
            ret = QtCore.QString(self._itemlist[row].tag_by_index(column) or '')

        elif role == Qt.TextAlignmentRole:
            c = PlaylistItem.ALLOWED_TAGS[column]
            if c == 'Track':
                ret = Qt.AlignHCenter
            elif c == 'Length':
                ret = Qt.AlignRight

        elif role == self.RoleQueuePosition:
            ret = self._itemlist[row].queue_position or 0

        elif role == self.RoleQueryIsCurrent:
            ret = self._itemlist[row] is self.current_item

        elif role == self.RoleQueryIsPlaying:
            ret = self._itemlist[row] is self.currently_playing

        elif role == self.RoleQueryIsStopAfter:
            ret = self._itemlist[row] is self.stop_after

        if ret is not None:
            return QtCore.QVariant(ret)
        else:
            return QtCore.QVariant()

    def headerData(self, section, orientation, role):
        if (role == Qt.DisplayRole and orientation == Qt.Horizontal):
            return QtCore.QVariant(
                    QtCore.QString(PlaylistItem.ALLOWED_TAGS[section]))
        else:
            return QtCore.QVariant()

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

            self.undo_stack.beginMacro('move ' + _n_tracks_str(len(rows)))
            try:
                removecmd = RemoveItemsCmd(self, rows, do_queue=False)
                InsertItemsCmd(self, row, removecmd.get_items(), do_queue=False)
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

    """Adding and removing items to _itemlist.

    (NB: No other function should modify _itemlist directly.)
    """

    def insert_items(self, position, items):
        # if currently_playing is absent, we'll check whether
        # it's getting re-added in this call
        current_item = None
        if (self.current_item in (None, self.FIRST_ITEM)
                and self.currently_playing is not None):
            playing_path = self.currently_playing.path
        else:
            playing_path = None

        try:
            nitems = len(items)
            for item in self._itemlist[position:]:
                item.position += nitems
            for i, item in enumerate(items):
                item.position = position + i
                if (playing_path is not None
                        and playing_path == item.path):
                    current_item = item
                    playing_path = None
            self.beginInsertRows(QtCore.QModelIndex(),
                                 position, position + nitems - 1)
            self._itemlist[position:0] = items
            self._row_count += nitems
        finally:
            self.endInsertRows()

        self.random_queue.extend(x for x in items if not x.already_played)
        self.tag_reader.queue_many(x for x in items if x.needs_tag_reader)

        self.emit(QtCore.SIGNAL('list_changed'))

        if current_item is not None:
            self.current_item = self.currently_playing = current_item

    def remove_items(self, position, amount):
        items = self._itemlist[position:position+amount]

        for item in items:
            if item.needs_tag_reader:
                self.tag_reader.dequeue(item)
            if not item.already_played:
                try:
                    self.random_queue.remove(item)
                except ValueError:
                    pass
            if item is self.current_item:
                self.current_item = self.FIRST_ITEM

            item.position = None

        for item in self._itemlist[position+amount:]:
            item.position -= amount

        try:
            self.beginRemoveRows(QtCore.QModelIndex(),
                                 position, position + amount - 1)
            self._itemlist[position:position+amount] = []
            self._row_count -= amount
        finally:
            self.endRemoveRows()

        self.emit(QtCore.SIGNAL('list_changed'))
        return items

    def clear_itemlist(self):
        self.current_item = None
        self.random_queue[:] = []
        self.tag_reader.clear_queue()

        items = self._itemlist[:]
        self._row_count = 0
        self._itemlist[:] = []
        self.reset()

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
                self.slot_play_pause, 'media-playback-start', 'Ctrl+P', 'Ctrl+Alt+P',
                factory=kdeui.KToggleAction)

        # The following actions have their global shortcut set to the empty
        # string. This allows the user to configure a global shortcut for these
        # actions, without us having to provide a default one (and polluting
        # the global shortcut namespace).
        self.action_stop = util.create_action('action_stop', 'Stop',
                self.slot_stop, 'media-playback-stop', 'Ctrl+O', '',
                factory=StopAction)

        self.action_next = util.create_action('action_next', 'Next',
                self.slot_next, 'media-skip-forward', 'Ctrl+N', '')

        self.action_previous = util.create_action('action_previous', 'Previous',
                self.slot_previous, 'media-skip-backward', 'Ctrl+I', '')

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

        # Undo/Redo action handling: this is tricky. We would want for the
        # actions in the toolbar to be QAction objects as returned by
        # createUndoAction() and createRedoAction(), because these do enable
        # and disable themselves as appropriate depending on where there's
        # stuff to undo or redo, which is nice. However, placing these in the
        # toolbar directly makes kdelibs emit a warning, so we do with a couple
        # KActions that watch the QActions and enable and disable themselves
        # when necessary. The KActions are needed anyway to have configurable
        # shortcuts for these actions, since the KDE shortcuts dialog doesn't
        # support configuring QAction shortcuts.
        self.undo_kaction = util.create_action('action_playlist_undo',
                'Undo', self.undo_stack.undo, 'edit-undo',
                kdeui.KStandardShortcut.shortcut(kdeui.KStandardShortcut.Undo))

        self.redo_kaction = util.create_action('action_playlist_redo',
                'Redo', self.undo_stack.redo, 'edit-redo',
                kdeui.KStandardShortcut.shortcut(kdeui.KStandardShortcut.Redo))

        self.undo_qaction = self.undo_stack.createUndoAction(self)
        self.redo_qaction = self.undo_stack.createRedoAction(self)

        self.connect(self.undo_qaction, QtCore.SIGNAL('changed()'),
            lambda: self.adjust_kaction_from_qaction(self.undo_kaction,
                                                     self.undo_qaction))

        self.connect(self.redo_qaction, QtCore.SIGNAL('changed()'),
            lambda: self.adjust_kaction_from_qaction(self.redo_kaction,
                                                     self.redo_qaction))

        self.adjust_kaction_from_qaction(self.undo_kaction, self.undo_qaction)
        self.adjust_kaction_from_qaction(self.redo_kaction, self.redo_qaction)

    ##

    """Properties."""

    def _set_stop_after(self, value):
        self._stop_after = value

        if value is None:
            self.stop_mode = StopMode.NONE

        self.emit(QtCore.SIGNAL('repaint_needed'))

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
        if not (value is self.FIRST_ITEM and self._row_count == 0):
            self._current_item = value
            try:
                self.random_queue.remove(value)
            except ValueError:
                pass
        else:
            self._current_item = None

        self.emit(QtCore.SIGNAL('list_changed'))
        self.emit(QtCore.SIGNAL('repaint_needed'))

        if self.current_item not in (self.FIRST_ITEM, None):
            self.emit(QtCore.SIGNAL('scroll_needed'),
                    self.index(self.current_item.position, 0))

    current_item = property(lambda self: self._current_item, _set_current_item)

    def _set_currently_playing(self, item):
        self._currently_playing = item
        self.emit(QtCore.SIGNAL('repaint_needed'))

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
                current = self.current_item.position
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

    """Other slots."""

    def slot_clear(self):
        ClearItemlistCmd(self)

    def slot_activate_index(self, index): # proxy reimplements this too
        self.maybe_populate_random_queue()
        self.current_item = self._itemlist[index.row()]
        self.slot_play()

    def slot_toggle_stop_after_current(self):
        current = self.currently_playing or self.current_item

        if current not in (self.FIRST_ITEM, None):
            self.toggle_stop_after_item(current)

    def slot_update_tags(self):
        rows = []

        for item, tags in self.tag_reader.pop_done():
            item.update_tags(tags)
            item.needs_tag_reader = False
            rows.append(item.position)

        if rows:
            self.my_emit_dataChanged(min(rows), max(rows))

    ##

    """Actions."""

    def slot_play(self):
        if self.current_item is not None:
            if self.current_item is self.FIRST_ITEM:
                if self.queue:
                    self.current_item = self.queue_popfront()
                else:
                    self.current_item = self.my_first_child()

            self.currently_playing = self.current_item
            self.currently_playing.already_played = True
            minirok.Globals.engine.play(self.current_item.path)

            if self.current_item.tags()['Length'] is None:
                tags = tag_reader.TagReader.tags(self.current_item.path)
                self.current_item.update_tags({'Length': tags.get('Length', 0)})
                self.my_emit_dataChanged(self.current_item.position)

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
                next = self.queue_popfront()
            elif self.random_mode:
                try:
                    next = self.random_queue.pop(0)
                except IndexError:
                    next = None
                    self.maybe_populate_random_queue()
            elif self.current_item is self.FIRST_ITEM:
                next = self.my_first_child()
            else:
                index = self.current_item.position + 1
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
            index = self.current_item.position - 1
            if index >= 0:
                self.current_item = self._itemlist[index]
                if minirok.Globals.engine.status != engine.State.STOPPED:
                    self.slot_play()

    def slot_engine_end_of_stream(self):
        finished_item = self.currently_playing
        self.currently_playing = None

        if finished_item is self.stop_after:
            self.stop_after = None
            self.slot_next(force_play=False)
        elif self.repeat_mode == RepeatMode.TRACK:
            # This can't be in slot_next() because the next button should move
            # to the next track *even* with repeat_mode == TRACK.
            self.slot_play()
        else:
            self.slot_next(force_play=True)

    ##

    """Methods for the view (proxy model reimplements these)."""

    def toggle_stop_after(self, index):
        assert index.isValid()
        self.toggle_stop_after_item(self._itemlist[index.row()])

    def toggle_enqueued(self, index):
        assert index.isValid()
        self.toggle_enqueued_many_items([ self._itemlist[index.row()] ])

    def toggle_enqueued_many(self, indexes):
        self.toggle_enqueued_many_items([ self._itemlist[x.row()] for x in indexes ])

    def removeItemsCmd(self, indexes):
        RemoveItemsCmd(self, [ x.row() for x in indexes ])

    ##

    def toggle_stop_after_item(self, item):
        if item == self.stop_after:
            self.stop_after = None
        else:
            self.stop_after = item
            self.stop_mode = StopMode.AFTER_ONE

    def toggle_enqueued_many_items(self, items, preserve_stop_after=False):
        """Toggle a list of items from being in the queue.

        If :param preserve_stop_after: is True, stop_after will not be touched.
            (This is mostly useful when dequeueing for playing what may be the
            last item in the queue, see queue_popfront() below.)
        """
        # items to queue, and items to dequeue
        enqueue = [ item for item in items if not item.queue_position ]
        dequeue = [ item for item in items if item.queue_position ]

        if dequeue:
            indexes = sorted(item.queue_position - 1 for item in dequeue)

            chunks = util.contiguous_chunks(indexes)
            chunks.append((len(self.queue), 0)) # fake chunk at the end

            # Now this is simple (at least compared to what was here before):
            # starting after each removal chunk, and until the beginning of the
            # next one, we substract the cumulative amount of removed items.
            accum = 0
            for i, (index, amount) in enumerate(chunks[:-1]):
                accum += amount
                until = sum(chunks[i+1])
                for item in self.queue[index+amount:until]:
                    item.queue_position -= accum

            for index in reversed(indexes):
                item = self.queue.pop(index)
                item.queue_position = None

        if enqueue:
            size = len(self.queue)
            self.queue.extend(enqueue)
            for i, item in enumerate(enqueue):
                item.queue_position = size+i+1

        if (not preserve_stop_after
                and self.stop_mode == StopMode.AFTER_QUEUE):
            if not self.queue:
                self.stop_after = None
                self.stop_mode = StopMode.AFTER_QUEUE
            elif self.queue[-1] is not self.stop_after:
                self.stop_after = self.queue[-1]

        self.emit(QtCore.SIGNAL('list_changed'))
        self.emit(QtCore.SIGNAL('repaint_needed'))

    def queue_popfront(self):
        """Convenience function to dequeue and return the first item from the queue."""
        try:
            popped = self.queue[0]
        except IndexError:
            minirok.logger.warn('queue_popfront() called on an empty queue')
        else:
            self.toggle_enqueued_many_items([ popped ], preserve_stop_after=True)
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
            for item in self._itemlist:
                self.already_played = False

    ##

    def apply_preferences(self):
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
                assert self._regex_mode in ['Always', 'OnRegexFail', 'Never']
        else:
            self._regex = None
            self._regex_mode = 'Always'

    ##

    def save_config(self):
        """Saves the current playlist."""
        paths = (item.path for item in self._itemlist)

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

        item = PlaylistItem(path, tags)

        if self._regex_mode == 'Always' or (regex_failed
                and self._regex_mode == 'OnRegexFail'):
            item.needs_tag_reader = True
        else:
            item.needs_tag_reader = False

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

    def adjust_kaction_from_qaction(self, kaction, qaction):
        kaction.setToolTip(qaction.text())
        kaction.setEnabled(qaction.isEnabled())

##

class Proxy(proxy.Model):

    def __init__(self, parent=None):
        proxy.Model.__init__(self, parent)
        self.scroll_index = None

    def setSourceModel(self, model):
        proxy.Model.setSourceModel(self, model)

        self.connect(model, QtCore.SIGNAL('scroll_needed'),
                self.slot_scroll_needed)

        # XXX dataChanged() abuse here too...
        self.connect(model, QtCore.SIGNAL('repaint_needed'),
            lambda: self.emit(QtCore.SIGNAL(
                'dataChanged(const QModelIndex &, const QModelIndex &)'),
                    self.index(0, 0), self.index(1, self.columnCount())))

    def setPattern(self, pattern):
        proxy.Model.setPattern(self, pattern)
        self.emit_scroll_needed()

    def slot_scroll_needed(self, index):
        self.scroll_index = index
        self.emit_scroll_needed()

    def emit_scroll_needed(self):
        if self.scroll_index is not None:
            mapped = self.mapFromSource(self.scroll_index)
            if mapped.isValid():
                self.emit(QtCore.SIGNAL('scroll_needed'), mapped)

    ##

    @proxy._map
    def toggle_enqueued(self, index):
        pass

    @proxy._map
    def toggle_stop_after(self, index):
        pass

    @proxy._map
    def slot_activate_index(self, index):
        pass

    @proxy._map_many
    def removeItemsCmd(self, indexes):
        pass

    @proxy._map_many
    def toggle_enqueued_many(self, indexes):
        pass

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

    def __init__(self, parent=None):
        QtGui.QTreeView.__init__(self, parent)

        self.setHeader(Columns(self))
        self.setRootIsDecorated(False)
        self.setDropIndicatorShown(True)
        self.setAllColumnsShowFocus(True)
        self.setDragDropMode(self.DragDrop)
        self.setSelectionBehavior(self.SelectRows)
        self.setSelectionMode(self.ExtendedSelection)

        self.action_queue_tracks = util.create_action(
                'action_enqueue_dequeue_selected', 'Enqueue/dequeue selection',
                self.slot_enqueue_dequeue_selected, None, 'Ctrl+E')

    def setModel(self, playlist):
        QtGui.QTreeView.setModel(self, playlist)
        self.header().setup_from_config()

        for c in range(playlist.columnCount()):
            if playlist.headerData(c, Qt.Horizontal,
                    Qt.DisplayRole).toString() == 'Track':
                self.track_delegate = PlaylistTrackDelegate()
                self.setItemDelegateForColumn(c, self.track_delegate)
                break
        else:
            minirok.logger.error('index for Track column not found :-?')

        self.connect(self, QtCore.SIGNAL('activated(const QModelIndex &)'),
                playlist.slot_activate_index)

        self.connect(playlist, QtCore.SIGNAL('scroll_needed'),
                                lambda index: self.scrollTo(index))

    ##

    def uniqSelectedIndexes(self):
        return set(x for x in self.selectedIndexes() if x.column() == 0)

    def unselectedIndexes(self):
        model = self.model()
        all = set(range(model.rowCount()))
        selected = set(x.row() for x in self.selectedIndexes())
        return [ model.index(x, 0) for x in  all - selected ]

    ##

    def drawRow(self, painter, styleopt, index):
        if index.data(Playlist.RoleQueryIsPlaying).toBool():
            # XXX This does not work with at least Qt 4.5
            styleopt = QtGui.QStyleOptionViewItem(styleopt) # make a copy
            styleopt.font.setItalic(True)

        QtGui.QTreeView.drawRow(self, painter, styleopt, index)

        if index.data(Playlist.RoleQueryIsCurrent).toBool():
            painter.save()
            r = styleopt.rect
            w = sum(self.columnWidth(x) for x in range(self.header().count()))
            painter.setPen(styleopt.palette.highlight().color())
            painter.drawRect(r.x(), r.y(), w-1, r.height()-1)
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
            self.model().removeItemsCmd(self.uniqSelectedIndexes())
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
                self.model().toggle_enqueued(index)
            elif button & Qt.MidButton:
                self.model().toggle_stop_after(index)
            else:
                return QtGui.QTreeView.mousePressEvent(self, event)

        elif keymod != Qt.NoModifier: # Eat them up
            return QtGui.QTreeView.mousePressEvent(self, event)

        elif button & Qt.MidButton:
            if index.data(Playlist.RoleQueryIsPlaying).toBool():
                minirok.Globals.action_collection.action('action_pause').trigger()

        elif button & Qt.RightButton:
            QtGui.QTreeView.mousePressEvent(self, event)

            menu = kdeui.KMenu(self)
            selected_indexes = self.uniqSelectedIndexes()

            assert len(selected_indexes) > 0 # or maybe use itemAt()

            if len(selected_indexes) == 1:
                enqueue_action = menu.addAction('Enqueue track')
                if index.data(Playlist.RoleQueuePosition).toInt()[0] > 0:
                    enqueue_action.setCheckable(True)
                    enqueue_action.setChecked(True)
            else:
                enqueue_action = menu.addAction('Enqueue/Dequeue tracks')

            stop_after_action = menu.addAction('Stop playing after this track')

            if index.data(Playlist.RoleQueryIsStopAfter).toBool():
                stop_after_action.setCheckable(True)
                stop_after_action.setChecked(True)

            crop_action = menu.addAction('Crop tracks')

            ##

            selected_action = menu.exec_(event.globalPos())

            if selected_action == enqueue_action:
                self.model().toggle_enqueued_many(sorted(selected_indexes))
            elif selected_action == stop_after_action:
                self.model().toggle_stop_after(index)
            elif selected_action == crop_action:
                self.model().removeItemsCmd(self.unselectedIndexes())

        else:
            return QtGui.QTreeView.mousePressEvent(self, event)

    ##

    def slot_enqueue_dequeue_selected(self):
        self.model().toggle_enqueued_many(sorted(self.uniqSelectedIndexes()))

##

class PlaylistItem(object):

    # This class should be considered sort of private to the model

    ALLOWED_TAGS = [ 'Track', 'Artist', 'Album', 'Title', 'Length' ]

    def __init__(self, path, tags=None):
        self.path = path

        self._tags = dict((tag, None) for tag in self.ALLOWED_TAGS)

        if tags is not None:
            self.update_tags(tags)

        # these are maintained up to date by the model
        self.position = None
        self.queue_position = None
        self.already_played = False
        self.needs_tag_reader = True

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

        queue_pos = index.data(Playlist.RoleQueuePosition).toInt()[0]
        draw_stop = index.data(Playlist.RoleQueryIsStopAfter).toBool()

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
                s_width = 1 # Seems to prevent an artifact
                s_height = 0

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

class Columns(QtGui.QHeaderView):

    # We use a single configuration option, which contains the order in which
    # columns are to be displayed, their width, and whether they are hidden or
    # not.
    CONFIG_SECTION = 'Playlist'
    CONFIG_OPTION = 'Columns'
    DEFAULT_COLUMNS = [
        ('Track', 60, 1), ('Artist', 200, 1),
        ('Album', 200, 0), ('Title', 275, 1), ('Length', 60, 1)
    ]

    def __init__(self, parent):
        QtGui.QHeaderView.__init__(self, Qt.Horizontal, parent)
        util.CallbackRegistry.register_save_config(self.save_config)

        self.setMovable(True)
        self.setStretchLastSection(False)
        self.setDefaultAlignment(Qt.AlignLeft)
        self.setContextMenuPolicy(Qt.CustomContextMenu)

        self.connect(self,
                QtCore.SIGNAL('customContextMenuRequested(const QPoint&)'),
                self.exec_popup)

    def sorted_column_names(self):
        names = []
        model = self.model()
        for c in range(model.columnCount()):
            names.append(model.headerData(c, Qt.Horizontal, Qt.DisplayRole).toString())

        return map(str, names)

    def setup_from_config(self):
        """Read config, sanitize it, and apply.

        NOTE: this code can't be in __init__, because at that time there is not
        a model/view associated with the object.
        """
        config = kdecore.KGlobal.config().group(self.CONFIG_SECTION)
        columns = []
        model_columns = self.sorted_column_names()
        unseen_columns = set(model_columns)

        if config.hasKey(self.CONFIG_OPTION):
            warn = minirok.logger.warn
            entries = map(str, config.readEntry(
                                self.CONFIG_OPTION, QtCore.QStringList()))

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
                    unseen_columns.remove(name)
                except KeyError:
                    warn('skipping unknown or duplicated column: %r', name)
                    continue

                columns.append((name, width, visible))

        if unseen_columns:
            missing = [ d for d in self.DEFAULT_COLUMNS
                             if d[0] in unseen_columns ]
            warn('these columns could not be found in config, '
                 'creating from defaults: %s', ', '.join(d[0] for d in missing))
            columns.extend(missing)

        ##

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

    def save_config(self):
        entries = [None] * self.count()

        for logical, name in enumerate(self.sorted_column_names()):
            visible = int(not self.isSectionHidden(logical))
            if not visible:
                # gross, but sectionSize() would return 0 otherwise :-(
                self.setSectionHidden(logical, False)
            width = self.sectionSize(logical)
            entry = '%s:%d:%d' % (name, width, visible)
            entries[self.visualIndex(logical)] = entry

        config = kdecore.KGlobal.config().group(self.CONFIG_SECTION)
        config.writeEntry(self.CONFIG_OPTION, entries)

##

"""Undoable commands to modify the contents of the playlist.

Note that they will add themselves to the model's QUndoStack.
"""

class AlterItemlistMixin(object):
    """Common functionality to make changes to the item list.

    This class offers methods to insert and remove items from the list. Each
    operation saves state, so that calling the reverse operation without any
    arguments just undoes it.

    In both cases, there is housekeeping of the playlist's queue, removing
    items from it when removing, and restoring the previous state on insertion.
    This can be disabled by passing "do_queue=False" to __init__.
    """
    def __init__(self, model, do_queue=True):
        self.items = {}
        self.chunks = []
        self.queuepos = {}
        self.current_item = None

        self.model = model
        self.do_queue = do_queue

    ##

    def insert_items(self, items=None):
        """Insert items into the playlist.

        :param items: should be a dict like:

            { pos1: itemlist1, pos2: itemlist2, ... }

        The items will be inserted in *ascending* order by position.
        If items is None, self.items will be used.
        """
        if items is None:
            items = self.items

        for position, items in sorted(items.iteritems()):
            self.model.insert_items(position, items)

        # Restore the current item, if we have one *and* the playlist doesn't
        if (self.current_item is not None
                and self.model.current_item in (None, Playlist.FIRST_ITEM)):
            self.model.current_item = self.current_item

        if self.do_queue:
            # TODO Think whether to invalidate these queue positions if the
            # queue changes between a removal and its undo.
            for pos, amount in util.contiguous_chunks(self.queuepos.keys()):
                items = [ self.queuepos[x] for x in range(pos, pos+amount) ]
                tail = self.model.queue[pos-1:]
                self.model.toggle_enqueued_many_items(tail + items)
                self.model.toggle_enqueued_many_items(tail)

    def remove_items(self, chunks=None):
        """Remove items from the playlist.

        :param chunks: should be a list like:

            [ (pos1, amount1), (pos2, amount2), ... ]

        The items will be removed in *descending* order by position.
        If chunks is None, self.chunks will be used, and if empty, it will be
        calculated first from self.items.

        This method will fills self.items in the format explained in
        insert_items() above.
        """
        if chunks is None:
            if self.chunks:
                chunks = self.chunks
            else:
                chunks = self.chunks = sorted((row, len(items))
                            for row, items in self.items.iteritems())

        self.items.clear()
        self.queuepos.clear()

        if self.model.current_item is not Playlist.FIRST_ITEM:
            self.current_item = self.model.current_item

        for position, amount in reversed(chunks):
            self.items[position] = self.model.remove_items(position, amount)

        if self.do_queue:
            for itemlist in self.items.itervalues():
                self.queuepos.update((item.queue_position, item)
                        for item in itemlist if item.queue_position)

            if self.queuepos:
                self.model.toggle_enqueued_many_items(self.queuepos.values())

    ##

    def get_items(self):
        """Return an ordered list of all items belonging to this command."""
        result = []
        for position, items in sorted(self.items.iteritems()):
            result.extend(items)
        return result


class InsertItemsCmd(QtGui.QUndoCommand, AlterItemlistMixin):
    """Command to insert a list of items at a certain position."""

    def __init__(self, model, position, items, do_queue=True):
        QtGui.QUndoCommand.__init__(self, 'insert ' + _n_tracks_str(len(items)))
        AlterItemlistMixin.__init__(self, model, do_queue)

        if items:
            self.items = { position: items }
            self.model.undo_stack.push(self)

    undo = AlterItemlistMixin.remove_items
    redo = AlterItemlistMixin.insert_items


class RemoveItemsCmd(QtGui.QUndoCommand, AlterItemlistMixin):
    """Command to remove a list of rows from the playlist."""

    def __init__(self, model, rows, do_queue=True):
        """Create the command.

        :param rows: A possibly unsorted/non-contiguous list of rows to remove.
        """
        QtGui.QUndoCommand.__init__(self, 'remove ' + _n_tracks_str(len(rows)))
        AlterItemlistMixin.__init__(self, model, do_queue)

        if rows:
            self.chunks = util.contiguous_chunks(rows)
            self.model.undo_stack.push(self)

    undo = AlterItemlistMixin.insert_items
    redo = AlterItemlistMixin.remove_items


class ClearItemlistCmd(QtGui.QUndoCommand, AlterItemlistMixin):
    """Command to completely clear the playlist.

    This command offers a more efficient implementation of remove_items than
    the mixin (uses the model's clear_itemlist), and handles the queue more
    efficiently.
    """
    def __init__(self, model):
        QtGui.QUndoCommand.__init__(self, 'clear playlist')
        AlterItemlistMixin.__init__(self, model)
        self.model.undo_stack.push(self)

    def remove_items(self):
        self.items.clear()
        self.queuepos.clear()

        if self.model.current_item is not Playlist.FIRST_ITEM:
            self.current_item = self.model.current_item

        self.items[0] = self.model.clear_itemlist()

        if self.do_queue:
            # iterate over model's queue directly, since we are
            # dequeueing *everything*
            self.queuepos.update((item.queue_position, item)
                    for item in self.model.queue)

            if self.queuepos:
                self.model.toggle_enqueued_many_items(self.queuepos.values())

    undo = AlterItemlistMixin.insert_items
    redo = remove_items

##

def _n_tracks_str(amount):
    """Return '1 track' if amount is 1 else '$amount tracks'."""
    if amount == 1:
        return '1 track'
    else:
        return '%d tracks' % (amount,)
