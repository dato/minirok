#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import time

import qt
import lastfm

import minirok
from minirok import engine

##

class LastfmSubmitter(qt.QObject):
    """An object that takes care of submiting played tracks to Last.fm.

    It relies on the Playlist.new_track signal. Upon receiving it, it starts a
    QTimer object at the appropriate time. If the playing enging pauses, the
    timer is paused accordingly.
    """
    def __init__(self):
        qt.QObject.__init__(self)

        self.data = None
        self.timer = QTimerWithPause(self, 'lastfm_timer')
        self.config = lastfm.config.Config('lastfmsubmitd')

        self.connect(minirok.Globals.playlist,
                qt.PYSIGNAL('new_track'), self.slot_new_track)

        self.connect(minirok.Globals.engine,
                qt.PYSIGNAL('status_changed'), self.slot_engine_status_changed)

        self.connect(self.timer, qt.SIGNAL('timeout()'), self.slot_submit)

    def slot_new_track(self):
        all_tags = minirok.Globals.playlist.currently_playing
        self.data = dict((k.lower(), v) for k, v in all_tags.items()
                                        if k in ['Title', 'Artist', 'Length'])

        if None in self.data.values():
            minirok.logger.debug('lastfm: not submitting incomplete data %r',
                    self.data)
            return

        length = self.data['length']

        if length < lastfm.MIN_LEN or length > lastfm.MAX_LEN:
            minirok.logger.debug(
                    'lastfm: not submitting %r due to out of limits length',
                    self.data)
            return
        else:
            submit_at = min(lastfm.SUB_SECONDS, length * lastfm.SUB_PERCENT)

        self.timer.start(submit_at*1000)

    def slot_engine_status_changed(self, new_status):
        if new_status == engine.State.PAUSED:
            self.timer.pause()
        elif new_status == engine.State.PLAYING:
            self.timer.resume()
        elif new_status == engine.State.STOPPED:
            self.timer.stop()
            self.data = None

    def slot_submit(self):
        if self.data is not None:
            self.data['time'] = time.gmtime()
            lastfm.submit([self.data], self.config.spool_path)
            self.data = None

##

class QTimerWithPause(qt.QTimer):
    """A QTimer with pause() and resume() methods.

    Idea taken from:
        http://www.riverbankcomputing.com/pipermail/pyqt/2004-July/008325.html
    """
    def __init__(self, *args):
        qt.QTimer.__init__(self, *args)
        self.duration = 0
        self.finished = True
        self.start_time = 0

        self.connect(self, qt.SIGNAL('timeout()'), self.slot_timer_finished)

    def start(self, msecs):
        self.finished = False
        self.duration = msecs
        self.start_time = time.time()
        qt.QTimer.start(self, msecs, True) # True: single-shot

    def pause(self):
        if self.isActive():
            self.stop()
            elapsed = time.time() - self.start_time
            self.start_time -= elapsed
            self.duration -= int(elapsed*1000)

    def resume(self):
        if not self.finished and not self.isActive():
            self.start(self.duration)

    def slot_timer_finished(self):
        # This prevents resume() on a finished timer from restarting it
        self.finished = True
