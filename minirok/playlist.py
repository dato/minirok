#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import os
import re
import sys
import errno

import qt
import kdeui
import kdecore

import minirok
from minirok import drag, engine, tag_reader, util

##

class Playlist(kdeui.KListView, util.HasConfig, util.HasGUIConfig):
    # This is the value self.current_item has whenver just the first item on
    # the playlist should be used. Only set to this value when the playlist
    # contains items!
    FIRST_ITEM = object()

    def __init__(self, *args):
        kdeui.KListView.__init__(self, *args)
        util.HasConfig.__init__(self)
        util.HasGUIConfig.__init__(self)

        self.queue = []
        self.columns = Columns(self)
        self.stop_mode = StopMode.NONE
        self.random_queue = util.RandomOrderedList()
        self.tag_reader = tag_reader.TagReader()

        # these have a property() below
        self._stop_after = None
        self._repeat_mode = RepeatMode.NONE
        self._random_mode = False
        self._current_item = None
        self._currently_playing = None

        self._currently_playing_taken = False

        self.setSorting(-1)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setAllColumnsShowFocus(True)
        self.setSelectionModeExt(kdeui.KListView.Extended)

        self.header().installEventFilter(self)

        self.connect(self, qt.SIGNAL('dropped(QDropEvent *, QListViewItem *)'),
                self.slot_accept_drop)

        self.connect(self, qt.SIGNAL('returnPressed(QListViewItem *)'),
                self.slot_new_current_item)

        self.connect(self, qt.SIGNAL('doubleClicked(QListViewItem *, const QPoint &, int)'),
                self.slot_new_current_item)

        self.connect(self, qt.SIGNAL('mouseButtonPressed(int, QListViewItem *, const QPoint &, int)'),
                self.slot_mouse_button_pressed)

        self.connect(self, qt.SIGNAL('moved()'), self.slot_list_changed)

        self.connect(self, qt.PYSIGNAL('list_changed'), self.slot_list_changed)

        self.connect(minirok.Globals.engine, qt.PYSIGNAL('status_changed'),
                self.slot_engine_status_changed)

        self.connect(minirok.Globals.engine, qt.PYSIGNAL('end_of_stream'),
                self.slot_engine_end_of_stream)

        self.init_actions()
        self.apply_preferences()
        self.load_saved_playlist()

    ##

    def init_actions(self):
        ac = minirok.Globals.action_collection

        self.action_play = kdeui.KAction('Play', 'player_play',
                kdecore.KShortcut.null(), self.slot_play, ac, 'action_play')

        self.action_pause = kdeui.KToggleAction('Pause', 'player_pause',
                kdecore.KShortcut.null(), self.slot_pause, ac, 'action_pause')

        self.action_play_pause = kdeui.KToggleAction('Play/Pause', 'player_play',
                kdecore.KShortcut('Ctrl+P'), self.slot_play_pause, ac, 'action_play_pause')

        self.action_stop = StopAction('Stop', 'player_stop',
                kdecore.KShortcut('Ctrl+O'), self.slot_stop, ac, 'action_stop')

        self.action_next = kdeui.KAction('Next', 'player_end',
                kdecore.KShortcut('Ctrl+N'), self.slot_next, ac, 'action_next')

        self.action_previous = kdeui.KAction('Previous', 'player_start',
                kdecore.KShortcut('Ctrl+I'), self.slot_previous, ac, 'action_previous')

        self.action_clear = kdeui.KAction('Clear playlist', 'view_remove',
                kdecore.KShortcut('Ctrl+L'), self.slot_clear, ac, 'action_clear_playlist')

        self.action_toggle_stop_after_current = kdeui.KAction('Stop after current',
                'player_stop', kdecore.KShortcut('Ctrl+K'),
                self.slot_toggle_stop_after_current, ac, 'action_toggle_stop_after_current')

    def column_index(self, col_name):
        try:
            return self.columns.index(col_name)
        except Columns.NoSuchColumn:
            minirok.logger.critical('column %r not found', col_name)
            sys.exit(1)

    ##

    def _set_stop_after(self, value):
        update = lambda: \
                self._stop_after is not None and self._stop_after.repaint()

        update()
        self._stop_after = value
        update()

        if value is None:
            self.stop_mode = StopMode.NONE

    stop_after = property(lambda self: self._stop_after, _set_stop_after)

    def _set_repeat_mode(self, value):
        self._repeat_mode = value # TODO Check it's a valid value?
        self.emit(qt.PYSIGNAL('list_changed'), ())

    repeat_mode = property(lambda self: self._repeat_mode, _set_repeat_mode)

    def _set_random_mode(self, value):
        self._random_mode = bool(value)
        self.emit(qt.PYSIGNAL('list_changed'), ())

    random_mode = property(lambda self: self._random_mode, _set_random_mode)

    def _set_current_item(self, value):
        def set_current(current):
            if self.current_item not in (self.FIRST_ITEM, None):
                if current:
                    self.ensureItemVisible(self.current_item)
                self.current_item.set_current(current)
                self.current_item.repaint()

        set_current(False)

        if not (value is self.FIRST_ITEM and self.childCount() == 0):
            self._current_item = value
            try:
                self.random_queue.remove(value)
            except ValueError:
                pass
        else:
            self._current_item = None

        set_current(True)
        self.emit(qt.PYSIGNAL('list_changed'), ())

    current_item = property(lambda self: self._current_item, _set_current_item)

    def _get_currently_playing(self):
        """Return a dict of the tags of the currently played track, or None."""
        if self._currently_playing is not None:
            return self._currently_playing._tags # XXX Private member!
        else:
            return None

    def _set_currently_playing(self, item):
        def set_playing(value):
            if self._currently_playing not in (self.FIRST_ITEM, None):
                self._currently_playing.set_playing(value)
                self._currently_playing.repaint()

        set_playing(False)
        self._currently_playing = item
        self._currently_playing_taken = False
        set_playing(True)

    currently_playing = property(_get_currently_playing, _set_currently_playing)

    ##

    def slot_list_changed(self):
        if self.childCount() == 0:
            self._current_item = None # can't use the property here
            self.action_next.setEnabled(False)
            self.action_clear.setEnabled(False)
            self.action_previous.setEnabled(False)
        else:
            if self.current_item is None:
                self._current_item = self.FIRST_ITEM
            if self.current_item is self.FIRST_ITEM:
                current = self.firstChild()
            else:
                current = self.current_item
            self.action_clear.setEnabled(True)
            self.action_previous.setEnabled(bool(current.itemAbove()))
            self.action_next.setEnabled(bool(self.queue
                    or self.repeat_mode == RepeatMode.PLAYLIST
                    or ((self.random_mode and self.random_queue)
                        or (not self.random_mode and current.itemBelow()))))

        self.slot_engine_status_changed(minirok.Globals.engine.status)

    def slot_engine_status_changed(self, new_status):
        if new_status == engine.State.STOPPED:
            self.action_stop.setEnabled(False)
            self.action_pause.setEnabled(False)
            self.action_pause.setChecked(False)
            self.action_play.setEnabled(bool(self.current_item))
            self.action_play_pause.setChecked(False)
            self.action_play_pause.setIcon('player_play')
            self.action_play_pause.setEnabled(bool(self.current_item))

        elif new_status == engine.State.PLAYING:
            self.action_stop.setEnabled(True)
            self.action_pause.setEnabled(True)
            self.action_pause.setChecked(False)
            self.action_play_pause.setChecked(False)
            self.action_play_pause.setIcon('player_pause')

        elif new_status == engine.State.PAUSED:
            self.action_pause.setChecked(True)
            self.action_play_pause.setChecked(True)

    ##

    def slot_accept_drop(self, event, prev_item):
        if event.source() != self.viewport(): # XXX
            files = drag.FileListDrag.file_list(event)
            self.add_files(files, prev_item)

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
        self.emit(qt.PYSIGNAL('list_changed'), ())

    def remove_items(self, items):
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

        self.emit(qt.PYSIGNAL('list_changed'), ())

    def slot_new_current_item(self, item):
        self.maybe_populate_random_queue()
        self.current_item = item
        self.slot_play()

    def slot_play_first_visible(self, search_string):
        if not unicode(search_string).strip():
            return
        self.current_item = qt.QListViewItemIterator(self,
                qt.QListViewItemIterator.Visible).current()
        self.slot_play()

    ##

    def slot_play(self):
        if self.current_item is not None:
            if self.current_item is self.FIRST_ITEM:
                if self.queue:
                    self.current_item = self.queue_pop(0)
                else:
                    self.current_item = self.my_first_child()

            self.currently_playing = self.current_item
            minirok.Globals.engine.play(self.current_item.path)

            if self.current_item._tags['Length'] is None:
                tags = tag_reader.TagReader.tags(self.current_item.path)
                self.current_item.update_tags({'Length': tags.get('Length', 0)})
                self.current_item.update_display()

            self.emit(qt.PYSIGNAL('new_track'), ())

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
                next = self.current_item.itemBelow()

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
            previous = self.current_item.itemAbove()
            if previous is not None:
                self.current_item = previous
                if minirok.Globals.engine.status != engine.State.STOPPED:
                    self.slot_play()

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

    def slot_mouse_button_pressed(self, button, item, qpoint, column):
        if button != qt.Qt.RightButton or not item:
            return

        popup = kdeui.KPopupMenu()
        popup.setCheckable(True)

        selected_items = self.selected_items()

        if not selected_items: # what gives?
            selected_items = [ item ]
        else:
            assert item in selected_items

        if len(selected_items) == 1:
            popup.insertItem('Enqueue track', 0)
            popup.setItemChecked(0, bool(item in self.queue))
        else:
            popup.insertItem('Enqueue/Dequeue tracks', 0)

        popup.insertItem('Stop playing after this track', 1)
        popup.setItemChecked(1, bool(item == self.stop_after))

        popup.insertItem('Crop tracks', 2)

        selected = popup.exec_loop(qt.QCursor.pos())

        if selected == 0:
            for item in selected_items:
                self.toggle_enqueued(item)
        elif selected == 1:
            self.toggle_stop_after(item)
        elif selected == 2:
            self.remove_items(self.unselected_items())

    def slot_toggle_stop_after_current(self):
        self.toggle_stop_after(self._currently_playing or self.current_item)

    def toggle_stop_after(self, item):
        if item in (self.FIRST_ITEM, None):
            return

        if item == self.stop_after:
            self.stop_after = None
        else:
            self.stop_after = item
            self.stop_mode = StopMode.AFTER_ONE

    def toggle_enqueued(self, item, only_dequeue=False):
        try:
            index = self.queue.index(item)
        except ValueError:
            if only_dequeue:
                # XXX this implicitly skips the emit() below, which is what we
                # want (so that not every removed item triggers a list_changed
                # signal), but feels very dirty.
                return
            self.queue.append(item)
            if self.stop_mode == StopMode.AFTER_QUEUE:
                self.stop_after = item # this repaints
            else:
                item.repaint()
        else:
            item = self.queue_pop(index)
            if (index == len(self.queue) # not len-1, 'coz we already popped()
                    and self.stop_mode == StopMode.AFTER_QUEUE):
                try:
                    self.stop_after = self.queue[-1]
                except IndexError:
                    self.stop_after = None
                    self.stop_mode = StopMode.AFTER_QUEUE

        self.emit(qt.PYSIGNAL('list_changed'), ())

    def queue_pop(self, index):
        """Pops an item from self.queue, and repaints the necessary items."""
        try:
            popped = self.queue.pop(index)
        except IndexError:
            minirok.logger.warn('invalid index %r in queue_pop()', index)
        else:
            for item in [ popped ] + self.queue[index:]:
                item.repaint()

            return popped

    def my_first_child(self):
        """Return the first item to be played, honouring random_mode."""
        if self.random_mode:
            if not self.random_queue:
                self.maybe_populate_random_queue()
            return self.random_queue.pop(0)
        else:
            return self.firstChild()

    def maybe_populate_random_queue(self):
        if not self.random_queue:
            item = self.firstChild()
            while item:
                self.random_queue.append(item)
                item = item.nextSibling()

    def select_items_helper(self, iterator_flags):
        """Return a list of items that match iterator_flags."""
        iterator = qt.QListViewItemIterator(self, iterator_flags)

        items = []
        while iterator.current():
            items.append(iterator.current())
            iterator += 1

        return items

    def selected_items(self):
        return self.select_items_helper(qt.QListViewItemIterator.Selected)

    def unselected_items(self):
        return self.select_items_helper(qt.QListViewItemIterator.Unselected)

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
        else:
            self._regex = None
            self._regex_mode = 'Always'

    ##

    def slot_save_config(self):
        """Saves the current playlist."""
        items = []
        item = self.firstChild()

        while item:
            items.append(item.path)
            item = item.nextSibling()

        try:
            playlist = file(self.saved_playlist_path(), 'w')
        except IOError, e:
            minirok.logger.error('could not save playlist: %s', e)
        else:
            playlist.write('\0'.join(items))
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
                self.add_files_untrusted(files)

        self.slot_list_changed()

    @staticmethod
    def saved_playlist_path():
        appdata = str(kdecore.KGlobal.dirs().saveLocation('appdata'))
        return os.path.join(appdata, 'saved_playlist.txt')

    ##

    def add_files(self, files, prev_item=None):
        """Add the given files to the playlist, after prev_item.

        If prev_item is None, files will be added at the end of the playlist.
        """
        if prev_item is None:
            prev_item = self.lastItem()
        for f in files:
            prev_item = self.add_file(f, prev_item)
        self.emit(qt.PYSIGNAL('list_changed'), ())

    def add_files_untrusted(self, files, clear_playlist=False):
        """Add to the playlist those files that are playable."""
        if clear_playlist:
            self.slot_clear()

        def _can_play_with_warning(path):
            if minirok.Globals.engine.can_play(path):
                if os.path.isfile(path):
                    return True
                else:
                    if not os.path.exists(path):
                        minirok.logger.warn('skipping nonexistent file %s', path)
                    else:
                        minirok.logger.warn('skipping non regular file %s', path)
                    return False
            else:
                minirok.logger.warn('skipping unplayable file/extension %s',
                        os.path.basename(path))
                return False

        self.add_files(filter(_can_play_with_warning, files))

    def add_file(self, file_, prev_item):
        tags = self.tags_from_filename(file_)
        if len(tags) == 0 or tags.get('Title', None) is None:
            regex_failed = True
            dirname, filename = os.path.split(file_)
            tags['Title'] = util.unicode_from_path(filename)
        else:
            regex_failed = False

        if (self._currently_playing_taken
                and self._currently_playing is not None
                and self._currently_playing.path == file_):
            item = self._currently_playing
            self.insertItem(item)
            item.moveItem(prev_item)
            self.current_item = item
            self.currently_playing = item # unsets _currently_playing_taken
        else:
            item = PlaylistItem(file_, self, prev_item, tags)
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

    def setColumnWidth(self, col, width):
        self.header().setResizeEnabled(bool(width), col) # Qt does not do this for us
        return kdeui.KListView.setColumnWidth(self, col, width)

    def takeItem(self, item):
        if item == self._currently_playing:
            self._currently_playing_taken = True
        return kdeui.KListView.takeItem(self, item)

    def acceptDrag(self, event):
        if drag.FileListDrag.canDecode(event):
            return True
        else:
            return kdeui.KListView.acceptDrag(self, event)

    def eventFilter(self, object_, event):
        # TODO Avoid so many calls to viewport(), type(), button(), ... ?

        if (object_ == self.header()
                and event.type() == qt.QEvent.MouseButtonPress
                and event.button() == qt.QEvent.RightButton):

            # Creates a menu for hiding/showing columns
            self.columns.exec_popup(event.globalPos())

            return True

        # Handle Ctrl+MouseClick: RightButton: enqueue, MidButton: stop after
        if (object_ == self.viewport()
                and event.type() == qt.QEvent.MouseButtonPress
                and event.state() == qt.Qt.ControlButton):
            item = self.itemAt(event.pos())
            if item is not None:
                if event.button() == qt.QEvent.MidButton:
                    self.toggle_stop_after(item)
                elif event.button() == qt.QEvent.RightButton:
                    self.toggle_enqueued(item)
                elif event.button() == qt.QEvent.LeftButton:
                    kdeui.KListView.eventFilter(self, object_, event)
            return True

        # Play/Pause when middle-click on the current playing track
        if (object_ == self.viewport()
                and event.type() == qt.QEvent.MouseButtonPress
                and event.button() == qt.QEvent.MidButton
                and self.itemAt(event.pos()) == self.current_item):
            self.slot_pause()
            return True

        return kdeui.KListView.eventFilter(self, object_, event)

    def keyPressEvent(self, event):
        if event.key() == qt.QEvent.Key_Delete:
            self.remove_items(self.selected_items())
        else:
            return kdeui.KListView.keyPressEvent(self, event)

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

    NOW = 0
    AFTER_CURRENT = 1
    AFTER_QUEUE = 2

    def __init__(self, *args):
        kdeui.KToolBarPopupAction.__init__(self, *args)
        self.popup_menu = self.popupMenu()

        self.popup_menu.insertTitle('Stop')
        self.popup_menu.insertItem('Now', self.NOW)
        self.popup_menu.insertItem('After current', self.AFTER_CURRENT)
        self.popup_menu.insertItem('After queue', self.AFTER_QUEUE)

        self.connect(self.popup_menu, qt.SIGNAL('aboutToShow()'), self.slot_prepare)
        self.connect(self.popup_menu, qt.SIGNAL('activated(int)'), self.slot_activated)

    def slot_prepare(self):
        playlist = minirok.Globals.playlist

        self.popup_menu.setItemChecked(self.AFTER_CURRENT,
                playlist.stop_mode == StopMode.AFTER_ONE and
                playlist.stop_after == playlist._currently_playing)
        self.popup_menu.setItemChecked(self.AFTER_QUEUE,
                playlist.stop_mode == StopMode.AFTER_QUEUE)

    def slot_activated(self, selected):
        playlist = minirok.Globals.playlist

        if selected == self.NOW:
            minirok.Globals.action_collection.action('action_stop').activate()

        elif selected == self.AFTER_CURRENT:
            playlist.slot_toggle_stop_after_current()

        elif selected == self.AFTER_QUEUE:
            if playlist.stop_mode == StopMode.AFTER_QUEUE:
                playlist.stop_after = None
            else:
                playlist.stop_after = None # clear possible AFTER_ONE mode
                playlist.stop_mode = StopMode.AFTER_QUEUE
                if playlist.queue:
                    playlist.stop_after = playlist.queue[-1]

##

class PlaylistItem(kdeui.KListViewItem):

    ALLOWED_TAGS = [ 'Track', 'Artist', 'Album', 'Title', 'Length' ]

    def __init__(self, path, parent, prev_item, tags={}):
        kdeui.KListViewItem.__init__(self, parent, prev_item)

        self.path = path
        self.playlist = parent

        self._is_current = False
        self._is_playing = False

        self._tags = dict((tag, None) for tag in self.ALLOWED_TAGS)
        self.update_tags(tags)
        self.update_display()

    def set_current(self, value=True):
        self._is_current = bool(value)

    def set_playing(self, value=True):
        self._is_playing = bool(value)

    ##

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

    def update_display(self):
        for column in Columns.DEFAULT_ORDER:
            text = self._tags[column]
            if text is not None:
                if column == 'Length':
                    text = util.fmt_seconds(text)
                index = self.playlist.column_index(column)
                self.setText(index, text)

    ##

    def paintCell(self, painter, colorgrp, column, width, align):
        """Draws a border for the current item, and the playing item in italics."""
        if self._is_playing:
            painter.font().setItalic(True)

        kdeui.KListViewItem.paintCell(
                self, painter, colorgrp, column, width, align)

        if self._is_current:
            # We use the superclass method here because Playlist.columns
            # is something else.
            num_columns = kdeui.KListView.columns(self.playlist)
            prev_width = 0
            full_width = 0
            for c in range(num_columns):
                w = self.playlist.columnWidth(c)
                full_width += w
                if c < column:
                    prev_width += w

            self.paintFocus(painter, colorgrp,
                            qt.QRect(qt.QPoint(-prev_width, 0),
                                     qt.QSize(full_width, self.height())))

        # Now draw an ellipse with the stop after track icon and queue
        # position. Code comes from Amarok's PlaylistItem::paintCell().
        draw_stop = bool(self == self.playlist.stop_after)
        try:
            queue_pos = str(self.playlist.queue.index(self) + 1)
        except ValueError:
            queue_pos = None

        if ((draw_stop or queue_pos)
                and self.playlist.header().mapToIndex(column) == 0):

            e_width = 16
            e_margin = 2
            e_height = self.height() - e_margin*2

            if draw_stop:
                stop_pixmap = util.get_png('black_tiny_stop')
                s_width = stop_pixmap.width()
                s_height = stop_pixmap.height()
            else:
                s_width = s_height = 0

            if queue_pos:
                q_width = painter.fontMetrics().width(queue_pos)
                q_height = painter.fontMetrics().height()
            else:
                q_width = q_height = 0

            items_width = s_width + q_width

            painter.setBrush(colorgrp.highlight())
            painter.setPen(colorgrp.highlight().dark())
            painter.drawEllipse(width - items_width - e_width/2, e_margin, e_width, e_height)
            painter.drawRect(width - items_width, e_margin, items_width, e_height)
            painter.setPen(colorgrp.highlight())
            painter.drawLine(width - items_width, e_margin+1, width - items_width, e_height)

            x = width - items_width - e_margin

            if draw_stop:
                y = e_height / 2 - s_height / 2 + e_margin
                painter.drawPixmap(x, y, stop_pixmap)
                x += s_width + e_margin/2

            if queue_pos:
                painter.setPen(colorgrp.highlightedText())
                painter.drawText(x, 0, width-x, q_height, qt.Qt.AlignCenter, queue_pos)

    def paintFocus(self, painter, colorgrp, qrect):
        """Only allows focus to be painted in the current item."""
        if not self._is_current:
            return
        else:
            kdeui.KListViewItem.paintFocus(self, painter, colorgrp, qrect)

##

class Columns(util.HasConfig):

    DEFAULT_ORDER = [ 'Track', 'Artist', 'Album', 'Title', 'Length' ]
    DEFAULT_WIDTH = {
            'Track': 50,
            'Artist': 200,
            'Album': 200,
            'Title': 300,
            'Length': 75,
    }

    # The configuration for Playlist Columns has three options:
    #   * Order: a list specifying the order in which the columns must be
    #     displayed; should contain all known columns, but if some are missing,
    #     they will be added at the end
    #   * Visible: a list of the columns that should be displayed; order of
    #     this list is not relevant
    #   * Width: a list of "ColumnName:Width" pairs, specifying the width of
    #     each column. Important: no width here should be zero!, even if the
    #     column is not visible. Pairs with width set to 0 will be ignored.
    CONFIG_SECTION = 'Playlist Columns'
    CONFIG_ORDER_OPTION = 'Order'
    CONFIG_WIDTH_OPTION = 'Width'
    CONFIG_VISIBLE_OPTION = 'Visible'

    class NoSuchColumn(Exception):
        pass

    def __init__(self, playlist):
        util.HasConfig.__init__(self)
        config = minirok.Globals.config(self.CONFIG_SECTION)

        def _read_list_entry(option):
            return map(str, config.readListEntry(option))

        ##

        if config.hasKey(self.CONFIG_ORDER_OPTION):
            self._order = _read_list_entry(self.CONFIG_ORDER_OPTION)
            # self._order must contain all available columns, so ensure that
            for c in self.DEFAULT_ORDER:
                if c not in self._order:
                    self._order.append(c)
        else:
            self._order = self.DEFAULT_ORDER

        ##

        if config.hasKey(self.CONFIG_VISIBLE_OPTION):
            self._visible = _read_list_entry(self.CONFIG_VISIBLE_OPTION)
        else:
            self._visible = self.DEFAULT_ORDER

        ##

        configured_width = self.DEFAULT_WIDTH.copy()

        if config.hasKey(self.CONFIG_WIDTH_OPTION):
            for pair in _read_list_entry(self.CONFIG_WIDTH_OPTION):
                name, width = pair.split(':', 1)
                name = name.strip()
                try:
                    width = int(width)
                except ValueError:
                    minirok.logger.error('invalid width %r for column %s',
                            width, name)
                else:
                    if width != 0:
                        configured_width[name] = width

        self._width = [ configured_width[c] for c in self._order ]

        ##

        for index, name in enumerate(self._order):
            playlist.addColumn(name, 1) # width=1 to enfore WidthMode: Manual
            if name in self._visible:
                playlist.setColumnWidth(index, self._width[index])
            else:
                playlist.setColumnWidth(index, 0)
            if name == 'Track':
                playlist.setColumnAlignment(index, qt.Qt.AlignHCenter)
            elif name == 'Length':
                playlist.setColumnAlignment(index, qt.Qt.AlignRight)

        self.playlist = playlist

    ##

    def index(self, name):
        try:
            return self._order.index(name)
        except ValueError:
            raise self.NoSuchColumn(name)

    def exec_popup(self, position):
        popup = kdeui.KPopupMenu()
        popup.setCheckable(True)

        for i, column in enumerate(self._order):
            pos = self.playlist.header().mapToIndex(i)
            popup.insertItem(column, i, pos)
            popup.setItemChecked(i, bool(self.playlist.columnWidth(i)))

        selected = popup.exec_loop(position)

        if self.playlist.columnWidth(selected) != 0:
            self.playlist.setColumnWidth(selected, 0)
        else:
            self.playlist.setColumnWidth(selected, self._width[selected])

    ##

    def slot_save_config(self):
        config = minirok.Globals.config(self.CONFIG_SECTION)
        header = self.playlist.header()
        order = []
        width = []
        visible = []
        for i, name in enumerate(self._order):
            order.append(self._order[header.mapToSection(i)])
            w = self.playlist.columnWidth(i)
            if w != 0:
                visible.append(name)
                width.append('%s:%d' % (name, w))
        config.writeEntry(self.CONFIG_ORDER_OPTION, order)
        config.writeEntry(self.CONFIG_WIDTH_OPTION, width)
        config.writeEntry(self.CONFIG_VISIBLE_OPTION, visible)
