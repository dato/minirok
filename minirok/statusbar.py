#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007-2008 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

from PyQt4 import QtGui, QtCore
from PyKDE4 import kdeui, kdecore

import minirok
from minirok import engine, util
from minirok.playlist import RepeatMode

##

class StatusBar(kdeui.KStatusBar):

    SLIDER_PRESSED = object()
    SLIDER_MOVED = object()
    SLIDER_RELEASED = object()

    def __init__(self, *args):
        kdeui.KStatusBar.__init__(self, *args)

        self.seek_to = None

        self.timer = util.QTimerWithPause(self)
        self.blink_timer = QtCore.QTimer(self)
        self.blink_timer_flag = True # used in slot_blink()

        self.repeat = RepeatLabel(self)
        self.random = RandomLabel(self)
        self.slider = QtGui.QSlider(QtCore.Qt.Horizontal, self)
        self.label1 = TimeLabel(self)
        self.label2 = NegativeTimeLabel(self)

        self.slider.setTracking(False)
        self.slider.setMaximumWidth(150)
        self.slider.setFocusPolicy(QtCore.Qt.NoFocus)

        self.addPermanentWidget(self.repeat, 0)
        self.addPermanentWidget(self.random, 0)
        self.addPermanentWidget(self.label1, 0)
        self.addPermanentWidget(self.slider, 0)
        self.addPermanentWidget(self.label2, 0)

        self.slot_stop()

        self._connect_timer() # this has a method 'cause we do it several times

        self.connect(self.blink_timer, QtCore.SIGNAL('timeout()'), self.slot_blink)

        self.connect(self.slider, QtCore.SIGNAL('sliderPressed()'),
                lambda: self.handle_slider_event(self.SLIDER_PRESSED))

        self.connect(self.slider, QtCore.SIGNAL('sliderMoved(int)'),
                lambda x: self.handle_slider_event(self.SLIDER_MOVED, x))

        self.connect(self.slider, QtCore.SIGNAL('sliderReleased()'),
                lambda: self.handle_slider_event(self.SLIDER_RELEASED))

        self.connect(minirok.Globals.playlist, QtCore.SIGNAL('new_track'),
                self.slot_start)

        self.connect(minirok.Globals.engine, QtCore.SIGNAL('status_changed'),
                self.slot_engine_status_changed)

        self.connect(minirok.Globals.engine, QtCore.SIGNAL('seek_finished'),
                self.slot_engine_seek_finished)

        # Actions
        self.action_next_repeat_mode = util.create_action('action_next_repeat_mode',
                'Change repeat mode', self.repeat.mousePressEvent,
                QtGui.QIcon(util.get_png('repeat_track_small')), 'Ctrl+T')

        self.action_toggle_random_mode = util.create_action('action_toggle_random_mode',
                'Toggle random mode', self.random.mousePressEvent,
                QtGui.QIcon(util.get_png('random_small')), 'Ctrl+R')

    def slot_update(self):
        self.elapsed = minirok.Globals.engine.get_position()
        self.remaining = self.length - self.elapsed
        self.slider.setValue(self.elapsed)
        self.label1.set_time(self.elapsed)
        self.label2.set_time(self.remaining) # XXX what if length was unset

    def slot_start(self):
        tags = minirok.Globals.playlist.get_current_tags()
        self.length = tags.get('Length', 0)
        self.slider.setRange(0, self.length)
        self.timer.start(1000)
        self.slider.setEnabled(True)
        self.slot_update()

    def slot_stop(self):
        self.timer.stop()
        self.blink_timer.stop()
        self.slider.setEnabled(False)
        self.length = self.elapsed = self.remaining = 0
        self.slot_update()

    def slot_engine_status_changed(self, new_status):
        if new_status == engine.State.PAUSED:
            self.timer.pause()
            self.blink_timer.start(750)
        elif new_status == engine.State.PLAYING:
            self.timer.resume()
            self.blink_timer.stop()
        elif new_status == engine.State.STOPPED:
            self.slot_stop()

    def slot_blink(self):
        self.blink_timer_flag = not self.blink_timer_flag

        if self.blink_timer_flag:
            self.label1.set_time(self.elapsed)
            self.label2.set_time(self.remaining)
        else:
            self.label1.clear()
            self.label2.clear()

    def slot_engine_seek_finished(self):
        self._connect_timer()

    def handle_slider_event(self, what, value=None):
        if what is self.SLIDER_PRESSED:
            # I'm using a disconnect/connect pair here because using
            # pause/resume resulted in slot_update() getting called many
            # seconds after resume(). Weird.
            self._connect_timer(disconnect=True)
        elif what is self.SLIDER_MOVED:
            self.seek_to = value
            self.label1.set_time(value)
            self.label2.set_time(self.length - value)
        elif what is self.SLIDER_RELEASED:
            if self.seek_to is not None:
                minirok.Globals.engine.set_position(self.seek_to)
                self.seek_to = None
        else:
            minirok.logger.warn('unknown slider event %r', what)

    def _connect_timer(self, disconnect=False):
        f = disconnect and self.disconnect or self.connect
        f(self.timer, QtCore.SIGNAL('timeout()'), self.slot_update)

##

class TimeLabel(QtGui.QLabel):

    PREFIX = ' '

    def __init__(self, *args):
        QtGui.QLabel.__init__(self, *args)
        self.setFont(kdeui.KGlobalSettings.fixedFont())
        self.setSizePolicy(QtGui.QSizePolicy.Maximum, QtGui.QSizePolicy.Fixed)

    def set_time(self, seconds):
        self.setText('%s%s' % (self.PREFIX, util.fmt_seconds(seconds)))
        self.setFixedSize(self.sizeHint()) # make the label.clear() above DTRT

class NegativeTimeLabel(TimeLabel):

    PREFIX = '-'

##

class MultiIconLabel(QtGui.QLabel, util.HasConfig):
    """A clickable label that shows a series of icons.

    The label automatically changes the icon on click, and then emits a
    QtCore.SIGNAL('clicked(int)').
    """
    CONFIG_SECTION = 'Statusbar'
    CONFIG_OPTION = None

    def __init__(self, parent, icons=None, tooltips=[]):
        """Initialize the label.

        :param icons: a list of QPixmaps over which to iterate.
        :param tooltips: tooltips associated with each icon/state.
        """
        QtGui.QLabel.__init__(self, parent)
        util.HasConfig.__init__(self)
        self.connect(self, QtCore.SIGNAL('clicked(int)'), self.slot_clicked)

        if icons is not None:
            self.icons = list(icons)
        else:
            self.icons = [ QtGui.QPixmap() ]

        self.tooltips = list(tooltips)
        self.tooltips += [ None ] * (len(self.icons) - len(self.tooltips))

        if self.CONFIG_OPTION is not None:
            config = kdecore.KGlobal.config().group(self.CONFIG_SECTION)
            value = util.kurl_to_path(config.readEntry(self.CONFIG_OPTION, '0'))
            try:
                self.state = int(value) - 1
            except ValueError:
                minirok.logger.warning('invalid value %r for %s', value,
                        self.CONFIG_OPTION)
                self.state = -1
        else:
            self.state = -1

        self.mousePressEvent(None)

    def mousePressEvent(self, event=None):
        self.state += 1

        if self.state >= len(self.icons):
            self.state = 0

        self.setPixmap(self.icons[self.state])

        tooltip = self.tooltips[self.state]

        if tooltip is not None:
            self.setToolTip(tooltip)
        else:
            self.setToolTip('')

        self.emit(QtCore.SIGNAL('clicked(int)'), self.state)

    def slot_clicked(self, state):
        raise NotImplementedError, \
            'MultiIconLabel.slot_clicked must be reimplemented in subclasses.'

    def slot_save_config(self):
        if self.CONFIG_OPTION is not None:
            config = kdecore.KGlobal.config().group(self.CONFIG_SECTION)
            config.writeEntry(self.CONFIG_OPTION, QtCore.QVariant(self.state))

class RepeatLabel(MultiIconLabel):
    CONFIG_OPTION = 'RepeatMode'

    STATES = {
            0: RepeatMode.NONE,
            1: RepeatMode.TRACK,
            2: RepeatMode.PLAYLIST,
    }

    def __init__(self, parent):
        icons = [
                kdeui.KIcon('go-bottom').pixmap(16,
                    QtGui.QIcon.Active, QtGui.QIcon.Off),
                util.get_png('repeat_track_small'),
                util.get_png('repeat_playlist_small'),
        ]
        tooltips = [
                'Repeat: Off',
                'Repeat: Track',
                'Repeat: Playlist',
        ]
        MultiIconLabel.__init__(self, parent, icons, tooltips)

    def slot_clicked(self, state):
        minirok.Globals.playlist.repeat_mode = self.STATES[state]

class RandomLabel(MultiIconLabel):
    CONFIG_OPTION = 'RandomMode'

    def __init__(self, parent):
        icons = [
                kdeui.KIcon('go-next').pixmap(16,
                    QtGui.QIcon.Active, QtGui.QIcon.Off),
                util.get_png('random_small'),
        ]
        tooltips = [
                'Random mode: Off',
                'Random mode: On',
        ]
        MultiIconLabel.__init__(self, parent, icons, tooltips)

    def slot_clicked(self, state):
        minirok.Globals.playlist.random_mode = bool(state)
