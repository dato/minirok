#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import os
import re
import sys

import qt
import kdeui
import kdecore

import minirok
from minirok import drag, engine, tag_reader, util

##

class Playlist(kdeui.KListView):
    # TODO Save the playlist

    # If CONFIG_REGEX_OPTION exists, it will be matched against the full path
    # and the PlaylistItem will have its tags initially filled with the
    # resulting match groups.
    # TODO This config options should be re-read when after updates via the
    # Preferences dialog.
    CONFIG_SECTION = 'Playlist'
    CONFIG_REGEX_OPTION = 'TagRegex'
    CONFIG_READ_TAGS_OPTION = 'ReadTags'
    CONFIG_READ_TAGS_VALUES = [ 'Always', 'Never', 'OnRegexFail' ]

    # This is the value self.current_item has whenver just the first item on
    # the playlist should be used. Only set to this value when the playlist
    # contains items!
    FIRST_ITEM = object()

    def __init__(self, *args):
        kdeui.KListView.__init__(self, *args)

        self.columns = Columns(self)
        self._current_item = None # has a property() below
        self._currently_playing = None # ditto.

        self.tag_reader = tag_reader.TagReader()
        self.tag_reader.start()

        self.setSorting(-1)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setAllColumnsShowFocus(True)
        self.setSelectionModeExt(kdeui.KListView.Extended)

        self.header().installEventFilter(self)

        self.connect(self, qt.SIGNAL('dropped(QDropEvent *, QListViewItem *)'),
                self.slot_accept_drop)

        self.connect(self, qt.SIGNAL('doubleClicked(QListViewItem *, const QPoint &, int)'),
                self.slot_new_current_item)

        self.connect(self, qt.SIGNAL('returnPressed(QListViewItem *)'),
                self.slot_new_current_item)

        self.connect(self, qt.PYSIGNAL('list_changed'), self.slot_list_changed)

        self.connect(minirok.Globals.engine, qt.PYSIGNAL('status_changed'),
                self.slot_engine_status_changed)

        self.connect(minirok.Globals.engine, qt.PYSIGNAL('end_of_stream'),
                self.slot_engine_end_of_stream)

        self.init_actions()

        # TODO Read the saved playlist here
        self.slot_list_changed()
        self.slot_read_config()

    ##

    def init_actions(self):
        ac = minirok.Globals.action_collection

        self.action_play = kdeui.KAction('Play', 'player_play',
                kdecore.KShortcut.null(), self.slot_play, ac, 'action_play')

        self.action_pause = kdeui.KToggleAction('Pause', 'player_pause',
                kdecore.KShortcut.null(), self.slot_pause, ac, 'action_pause')

        self.action_play_pause = kdeui.KToggleAction('Play/Pause', 'player_play',
                kdecore.KShortcut('Ctrl+P'), self.slot_play_pause, ac, 'action_play_pause')

        self.action_stop = kdeui.KAction('Stop', 'player_stop',
                kdecore.KShortcut('Ctrl+O'), self.slot_stop, ac, 'action_stop')

        self.action_next = kdeui.KAction('Next', 'player_end',
                kdecore.KShortcut('Ctrl+N'), self.slot_next, ac, 'action_next')

        self.action_previous = kdeui.KAction('Previous', 'player_start',
                kdecore.KShortcut('Ctrl+I'), self.slot_previous, ac, 'action_previous')

        self.action_clear = kdeui.KAction('Clear playlist', 'view_remove',
                kdecore.KShortcut('Ctrl+L'), self.slot_clear, ac, 'action_clear_playlist')

    def column_index(self, col_name):
        try:
            return self.columns.index(col_name)
        except Columns.NoSuchColumn:
            minirok.logger.critical('column %r not found', col_name)
            sys.exit(1)

    ##

    @property
    def currently_playing(self):
        """Return a dict of the tags of the currently played track, or None."""
        if self._currently_playing is not None:
            return self._currently_playing._tags # XXX Private member!
        else:
            return None

    def _set_current_item(self, value):
        self.__current_track_marker(self.current_item, unset=True)
        if not (value is self.FIRST_ITEM and self.childCount() == 0):
            self._current_item = value
        else:
            self._current_item = None
        self.__current_track_marker(self.current_item, unset=False)
        self.emit(qt.PYSIGNAL('list_changed'), ())

    current_item = property(lambda self: self._current_item, _set_current_item)

    # XXX This is a gross hack until I code something better
    def __current_track_marker(self, item, unset=False):
        if item in (self.FIRST_ITEM, None):
            return
        text = str(item.text(self.column_index('Track')))
        if not unset:
            text = '%s >>' % text
        else:
            text = re.sub(r' \>\>$', '', text)
        item.setText(self.column_index('Track'), text)

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
            self.action_next.setEnabled(bool(current.itemBelow()))
            self.action_previous.setEnabled(bool(current.itemAbove()))

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
            self.tag_reader.lock()
            try:
                for f in drag.FileListDrag.file_list(event):
                    prev_item = self.add_file(f, prev_item)
            finally:
                self.tag_reader.unlock()
            self.emit(qt.PYSIGNAL('list_changed'), ())

    def slot_clear(self):
        if not self.tag_reader.queue_empty():
            self.tag_reader.lock()
            try:
                self.tag_reader.clear_queue()
            finally:
                self.tag_reader.unlock()
        self.clear()
        self.emit(qt.PYSIGNAL('list_changed'), ())

    def slot_remove_selected(self): # not connected, but hey
        iterator = qt.QListViewItemIterator(self,
                qt.QListViewItemIterator.Selected)

        # Iterating through the iterator, calling takeItem() on each
        # iterator.current() does not work: not all items get removed.
        # Make a list of the selected items first, and iterate over it.
        items = []
        while iterator.current():
            items.append(iterator.current())
            iterator += 1

        if not items:
            return

        self.tag_reader.lock()
        try:
            for item in items:
                self.tag_reader.dequeue(item)
                self.takeItem(item)
                if item == self.current_item:
                    self.current_item = self.FIRST_ITEM
        finally:
            self.tag_reader.unlock()

        self.emit(qt.PYSIGNAL('list_changed'), ())

    def slot_new_current_item(self, item):
        self.current_item = item
        self.slot_play()

    ##

    def slot_play(self):
        if self.current_item is not None:
            if self.current_item is self.FIRST_ITEM:
                self.current_item = self.firstChild()
            self._currently_playing = self.current_item
            minirok.Globals.engine.play(self.current_item.path)

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
            self._currently_playing = None
            minirok.Globals.engine.stop()

    def slot_next(self, force_play=False):
        if self.current_item is not None:
            if self.current_item is self.FIRST_ITEM:
                next = self.firstChild()
            else:
                next = self.current_item.itemBelow()
            if next is None:
                self.current_item = self.FIRST_ITEM
            else:
                self.current_item = next
                if (force_play
                    or minirok.Globals.engine.status != engine.State.STOPPED):
                    self.slot_play()

    def slot_previous(self):
        if (self.current_item is not None 
                and self.current_item is not self.FIRST_ITEM):
            previous = self.current_item.itemAbove()
            if previous is not None:
                self.current_item = previous
                if minirok.Globals.engine.status != engine.State.STOPPED:
                    self.slot_play()

    def slot_engine_end_of_stream(self, *args):
        # TODO Check stop after track
        self._currently_playing = None
        self.slot_next(force_play=True)

    ##

    def slot_read_config(self):
        config = minirok.Globals.config(self.CONFIG_SECTION)
        self._regex = unicode(config.readEntry(self.CONFIG_REGEX_OPTION, '')) or None

        if self._regex is not None:
            try:
                self._regex = re.compile(self._regex)
            except re.error, e:
                minirok.logger.error('invalid regular expresion %s: %s',
                        self._regex, e)
                self._read_tags = 'Always'
            else:
                self._read_tags = str(config.readEntry(
                        self.CONFIG_READ_TAGS_OPTION, 'Always'))
        else:
            self._read_tags = 'Always'

        if self._read_tags not in self.CONFIG_READ_TAGS_VALUES:
            minirok.logger.error('invalid value %r for %s', self._read_tags,
                    self.CONFIG_READ_TAGS_OPTION)
            self._read_tags = 'Always'

    ##

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

    def add_file(self, file_, prev_item):
        prefix, extension = os.path.splitext(file_)
        if extension.lower() \
                not in minirok.Globals.engine.supported_extensions:
            # minirok.logger.debug('skipping unsupported file format %s', file_)
            return prev_item

        tags = self.tags_from_filename(file_)
        if len(tags) == 0 or tags.get('Title', None) is None:
            regex_failed = True
            dirname, filename = os.path.split(file_)
            tags['Title'] = util.unicode_from_path(filename)
        else:
            regex_failed = False

        item = PlaylistItem(file_, self, prev_item, tags)

        if self._read_tags == 'Always' or (regex_failed
                and self._read_tags == 'OnRegexFail'):
            self.tag_reader.queue(prev_item)

        return item

    ##

    def setColumnWidth(self, col, width):
        self.header().setResizeEnabled(bool(width), col) # Qt does not do this for us
        return kdeui.KListView.setColumnWidth(self, col, width)

    def acceptDrag(self, event):
        if drag.FileListDrag.canDecode(event):
            return True
        else:
            return kdeui.KListView.acceptDrag(self, event)

    def eventFilter(self, object_, event):
        if (object_ == self.header()
                and event.type() == qt.QEvent.MouseButtonPress
                and event.button() == qt.QEvent.RightButton):

            # Creates a menu for hiding/showing columns
            self.columns.exec_popup(event.globalPos())

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
            self.slot_remove_selected()
        else:
            return kdeui.KListView.keyPressEvent(self, event)

##

class PlaylistItem(kdeui.KListViewItem):

    ALLOWED_TAGS = [ 'Track', 'Artist', 'Album', 'Title', 'Length' ]

    def __init__(self, path, parent, prev_item, tags={}):
        kdeui.KListViewItem.__init__(self, parent, prev_item)

        self.path = path
        self.playlist = parent

        self._tags = dict((tag, None) for tag in self.ALLOWED_TAGS)
        self.update_tags(tags)
        self.update_display()

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
                    text = '%d:%02d' % (text/60, text%60)
                index = self.playlist.column_index(column)
                self.setText(index, text)

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
        minirok.logger.debug('finished Columns.slot_save_config')
