#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007-2008 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import time

from PyQt4 import QtCore
try:
    import lastfm.client
    _has_lastfm_client = True
except ImportError:
    import lastfm
    _has_lastfm_client = False

import minirok
from minirok import engine, util

##

class LastfmSubmitter(QtCore.QObject, util.HasGUIConfig):
    """An object that takes care of submiting played tracks to Last.fm.

    It relies on the Playlist.new_track signal. Upon receiving it, it starts a
    QTimer object at the appropriate time. If the playing enging pauses, the
    timer is paused accordingly.
    """
    def __init__(self):
        QtCore.QObject.__init__(self)
        util.HasGUIConfig.__init__(self)

        self.data = None
        self.timer = util.QTimerWithPause(self)

        if _has_lastfm_client:
            self.lastfm_client = lastfm.client.Client('minirok')
        else:
            self.spool_path = lastfm.config.Config('lastfmsubmitd').spool_path

        self.apply_preferences()

    def apply_preferences(self):
        if minirok.Globals.preferences.enable_lastfm:
            func = self.connect
        else:
            # Grrr, self.disconnect() without arguments does not work
            # XXX-KDE4 Check whether this is still the case in PyQt4.
            func = self.disconnect

        func(minirok.Globals.playlist, QtCore.SIGNAL('new_track'),
                self.slot_new_track)

        func(minirok.Globals.engine, QtCore.SIGNAL('status_changed'),
                self.slot_engine_status_changed)

        func(self.timer, QtCore.SIGNAL('timeout()'), self.slot_submit)

    def slot_new_track(self):
        all_tags = minirok.Globals.playlist.get_current_tags()
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
            if _has_lastfm_client:
                self.lastfm_client.submit(self.data)
            else:
                lastfm.submit([self.data], self.spool_path)
            self.data = None
