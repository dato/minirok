#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import time

import qt
import lastfm

import minirok
from minirok import engine, util

##

class LastfmSubmitter(qt.QObject, util.HasGUIConfig):
    """An object that takes care of submiting played tracks to Last.fm.

    It relies on the Playlist.new_track signal. Upon receiving it, it starts a
    QTimer object at the appropriate time. If the playing enging pauses, the
    timer is paused accordingly.
    """
    def __init__(self):
        qt.QObject.__init__(self)
        util.HasGUIConfig.__init__(self)

        self.data = None
        self.timer = util.QTimerWithPause(self, 'lastfm timer')
        self.config = lastfm.config.Config('lastfmsubmitd')

        self.apply_preferences()

    def apply_preferences(self):
        if minirok.Globals.preferences.enable_lastfm:
            func = self.connect
        else:
            # Grrr, self.disconnect() without arguments does not work
            func = self.disconnect

        func(minirok.Globals.playlist, qt.PYSIGNAL('new_track'),
                self.slot_new_track)

        func(minirok.Globals.engine, qt.PYSIGNAL('status_changed'),
                self.slot_engine_status_changed)

        func(self.timer, qt.SIGNAL('timeout()'), self.slot_submit)

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
