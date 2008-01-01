#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import qt
import kdeui
import kdecore

import minirok
from minirok import engine, util
from minirok.playlist import RepeatMode

##

class StatusBar(kdeui.KStatusBar):

    def __init__(self, *args):
        kdeui.KStatusBar.__init__(self, *args)

        self.timer = util.QTimerWithPause(self, 'statusbar timer')
        self.blink_timer = qt.QTimer(self, 'statusbar blink timer')
        self.blink_timer_flag = True # used in slot_blink()

        self.repeat = RepeatLabel(self)
        self.random = RandomLabel(self)
        self.slider = qt.QSlider(qt.Qt.Horizontal, self, 'track position')
        self.label1 = TimeLabel(self, 'left statusbar label')
        self.label2 = NegativeTimeLabel(self, 'right statusbar label')

        self.slider.setEnabled(False) # FIXME
        self.slider.setMaximumWidth(150)
        self.slider.setFocusPolicy(qt.QWidget.NoFocus)

        # True: permanent (right-aligned); 0: stretch (minimum space on resize)
        self.addWidget(self.repeat, 0, True)
        self.addWidget(self.random, 0, True)
        self.addWidget(self.label1, 0, True)
        self.addWidget(self.slider, 0, True)
        self.addWidget(self.label2, 0, True)

        self.slot_stop()

        self.connect(self.timer, qt.SIGNAL('timeout()'), self.slot_update)

        self.connect(self.blink_timer, qt.SIGNAL('timeout()'), self.slot_blink)

        self.connect(minirok.Globals.playlist, qt.PYSIGNAL('new_track'),
                self.slot_start)

        self.connect(minirok.Globals.engine, qt.PYSIGNAL('status_changed'),
                self.slot_engine_status_changed)

        # Actions
        self.action_next_repeat_mode = kdeui.KAction('Change repeat mode',
                qt.QIconSet(util.get_png('repeat_track_small')),
                kdecore.KShortcut('Ctrl+T'), self.repeat.mousePressEvent,
                minirok.Globals.action_collection, 'action_next_repeat_mode')

        self.action_toggle_random_mode = kdeui.KAction('Toggle random mode',
                qt.QIconSet(util.get_png('random_small')),
                kdecore.KShortcut('Ctrl+R'), self.random.mousePressEvent,
                minirok.Globals.action_collection, 'action_toggle_random_mode')

    def slot_update(self):
        self.elapsed = minirok.Globals.engine.get_position()
        self.remaining = self.length - self.elapsed
        self.slider.setValue(self.elapsed)
        self.label1.set_time(self.elapsed)
        self.label2.set_time(self.remaining) # XXX what if length was unset

    def slot_start(self):
        self.length = minirok.Globals.playlist.currently_playing['Length'] or 0
        self.slider.setRange(0, self.length)
        self.timer.start(1000, False) # False: not single-shot
        self.slot_update()

    def slot_stop(self):
        self.timer.stop()
        self.blink_timer.stop()
        self.length = self.elapsed = self.remaining = 0
        self.slot_update()

    def slot_engine_status_changed(self, new_status):
        if new_status == engine.State.PAUSED:
            self.timer.pause()
            self.blink_timer.start(750, False) # False: not single-shot
        elif new_status == engine.State.PLAYING:
            self.timer.resume()
            self.blink_timer.stop()
        elif new_status == engine.State.STOPPED:
            self.slot_stop()

    def slot_blink(self):
        self.blink_timer_flag = not self.blink_timer_flag

        if self.blink_timer_flag:
            self.label1.update()
            self.label2.update()
        else:
            self.label1.erase()
            self.label2.erase()

##

class TimeLabel(qt.QLabel):

    PREFIX = ' '

    def __init__(self, *args):
        qt.QLabel.__init__(self, *args)
        self.setFont(kdecore.KGlobalSettings.fixedFont())
        self.setSizePolicy(qt.QSizePolicy.Maximum, qt.QSizePolicy.Fixed)

    def set_time(self, seconds):
        self.setText('%s%s' % (self.PREFIX, util.fmt_seconds(seconds)))

class NegativeTimeLabel(TimeLabel):

    PREFIX = '-'

##

class MultiIconLabel(qt.QLabel, util.HasConfig):
    """A clickable label that shows a series of icons.

    The label automatically changes the icon on click, and then emits a
    qt.PYSIGNAL('clicked(int)').
    """
    CONFIG_SECTION = 'Statusbar'
    CONFIG_OPTION = None

    def __init__(self, parent, icons=None, tooltips=[]):
        """Initialize the label.

        :param icons: a list of QPixmaps over which to iterate.
        :param tooltips: tooltips associated with each icon/state.
        """
        qt.QLabel.__init__(self, parent)
        util.HasConfig.__init__(self)
        self.connect(self, qt.PYSIGNAL('clicked(int)'), self.slot_clicked)

        if icons is not None:
            self.icons = list(icons)
        else:
            self.icons = [ qt.QPixmap() ]

        self.tooltips = list(tooltips)
        self.tooltips += [ None ] * (len(self.icons) - len(self.tooltips))

        if self.CONFIG_OPTION is not None:
            config = minirok.Globals.config(self.CONFIG_SECTION)
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
            qt.QToolTip.add(self, tooltip)
        else:
            qt.QToolTip.remove(self)

        self.emit(qt.PYSIGNAL('clicked(int)'), (self.state,))

    def slot_clicked(self, state):
        raise NotImplementedError, \
            'MultiIconLabel.slot_clicked must be reimplemented in subclasses.'

    def slot_save_config(self):
        if self.CONFIG_OPTION is not None:
            config = minirok.Globals.config(self.CONFIG_SECTION)
            config.writeEntry(self.CONFIG_OPTION, self.state)

class RepeatLabel(MultiIconLabel):
    CONFIG_OPTION = 'RepeatMode'

    STATES = {
            0: RepeatMode.NONE,
            1: RepeatMode.TRACK,
            2: RepeatMode.PLAYLIST,
    }

    def __init__(self, parent):
        icons = [
                kdecore.SmallIcon('bottom'),
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
                kdecore.SmallIcon('forward'),
                util.get_png('random_small'),
        ]
        tooltips = [
                'Random mode: Off',
                'Random mode: On',
        ]
        MultiIconLabel.__init__(self, parent, icons, tooltips)

    def slot_clicked(self, state):
        minirok.Globals.playlist.random_mode = bool(state)
