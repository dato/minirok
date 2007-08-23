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

##

class StatusBar(kdeui.KStatusBar):

    def __init__(self, *args):
        kdeui.KStatusBar.__init__(self, *args)

        self.timer = util.QTimerWithPause(self, 'statusbar timer')

        self.slider = qt.QSlider(qt.Qt.Horizontal, self, 'track position')
        self.label1 = TimeLabel(self, 'left statusbar label')
        self.label2 = NegativeTimeLabel(self, 'right statusbar label')

        self.slider.setEnabled(False) # FIXME
        self.slider.setMaximumWidth(150)
        self.slider.setFocusPolicy(qt.QWidget.NoFocus)

        self.addWidget(self.label1, 0, True) # True: permanent (right-aligned)
        self.addWidget(self.slider, 0, True) # 0 stretch (minimum space on resize)
        self.addWidget(self.label2, 0, True)

        self.slot_stop()

        self.connect(self.timer, qt.SIGNAL('timeout()'), self.slot_update)

        self.connect(minirok.Globals.playlist, qt.PYSIGNAL('new_track'),
                self.slot_start)

        self.connect(minirok.Globals.playlist, qt.PYSIGNAL('end_of_stream'),
                self.slot_stop)

        self.connect(minirok.Globals.engine, qt.PYSIGNAL('status_changed'),
                self.slot_engine_status_changed)

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
        self.length = self.elapsed = self.remaining = 0
        self.slot_update()

    def slot_engine_status_changed(self, new_status):
        if new_status == engine.State.PAUSED:
            self.timer.pause()
        elif new_status == engine.State.PLAYING:
            self.timer.resume()
        elif new_status == engine.State.STOPPED:
            self.slot_stop()

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
