#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007-2009 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

from __future__ import with_statement

import re
import time
import socket
import urllib
import hashlib
import httplib
import urlparse
import threading

from PyQt4 import QtCore

import minirok
from minirok import engine, util

# TODO: Quitting Minirok while playing will not submit the current track, even
# the required playing time has passed.
# TODO: Spool directory, of course...
# TODO: Preferences dialog: get password (KWallet yes or no?), server, etc.

##

HANDSHAKE_URL = 'http://post.audioscrobbler.com:80/' # TODO: needs to be configurable
PROTOCOL_VERSION = '1.2.1'
CLIENT_IDENTIFIER = 'mrk'

TRACK_MIN_LENGTH = 30
TRACK_SUBMIT_SECONDS = 240
TRACK_SUBMIT_PERCENT = 0.5

SOURCE_USER = 'P'
SOURCE_BROADCAST = 'R'
SOURCE_PERSONALIZED = 'E'
SOURCE_LASTFM = 'L'
SOURCE_UNKNOWN = 'U'

MAX_FAILURES = 3
MAX_SLEEP_MINUTES = 120
MAX_TRACKS_AT_ONCE = 50

##

class Submission(object):

    class RequiredDataMissing(Exception):
        pass

    class TrackTooShort(Exception):
        pass

    def __init__(self, tag_dict):
        """Create a Submission object from a dict of tags.

        tag_dict should be a dictionary as returned by get_current_tags() in
        the global Playlist object, i.e. contain 'Title', 'Artist', etc.
        """
        if not all(tag_dict[x] for x in ['Title', 'Artist', 'Length']):
            raise self.RequiredDataMissing()

        elif tag_dict['Length'] < TRACK_MIN_LENGTH:
            raise self.TrackTooShort()

        self.length = tag_dict['Length']
        self.start_time = int(time.time())

        self.param = {
            'm': '',
            'r': '',
            'o': SOURCE_USER,
            'l': str(self.length),
            'i': str(self.start_time),
            'n': util.ensure_utf8(tag_dict['Track']),
            't': util.ensure_utf8(tag_dict['Title']),
            'b': util.ensure_utf8(tag_dict['Album']),
            'a': util.ensure_utf8(tag_dict['Artist']),
        }

    def get_params(self, i=0):
        return dict(('%s[%d]' % (k, i), v) for k, v in self.param.items())

    def get_now_playing_params(self):
        return dict((k, self.param[k]) for k in list('atblnm'))

##

class HandshakeFatalError(Exception):
    pass

##

class Request(object):
    def __init__(self, url, params):
        self.body = []
        self.error = None
        self.failed = False

        url = urlparse.urlparse(url)
        conn = httplib.HTTPConnection(url.netloc)
        try:
            conn.request('POST', url.path, urllib.urlencode(params),
                    { 'Content-Type': 'application/x-www-form-urlencoded' })
        except socket.error, e:
            self.failed = True
            self.error = e.args[1] # Thank you for not providing e.message
        else:
            resp = conn.getresponse()

            if resp.status != httplib.OK:
                self.failed = True
                self.error = resp.reason
            else:
                self.body = resp.read().rstrip('\n').split('\n')

                if not self.body:
                    self.failed = True
                    self.error = 'no response received from server'
                elif self.body[0].split()[0] != 'OK':
                    self.failed = True
                    self.error = re.sub(r'^FAILED\s+', '', self.body[0])

class HandshakeRequest(Request):
    def __init__(self, url, params):
        super(HandshakeRequest, self).__init__(url, params)

        if self.failed:
            if re.search(r'^(BANNED|BADAUTH|BADTIME)', self.error):
                raise HandshakeFatalError(self.error)
        elif len(self.body) != 4:
            self.failed = True
            self.error = 'unexpected response from scrobbler server:\n%r' % (
                            self.body,)

##

class Scrobbler(QtCore.QObject, threading.Thread):

    def __init__(self):
        QtCore.QObject.__init__(self)
        threading.Thread.__init__(self)
        self.setDaemon(True)

        self.session_key = None
        self.scrobble_url = None
        self.now_playing_url = None

        self.failure_count = 0
        self.pause_duration = 1 # minutes
        self.scrobble_queue = []
        self.current_track = None

        self.mutex = threading.Condition()
        self.timer = util.QTimerWithPause()
        self.timer.setSingleShot(True)

        util.CallbackRegistry.register_apply_prefs(self.apply_preferences)
        self.apply_preferences() # Connect signals/slots

        ## XXX This is in place until I update the preferences dialog
        import os
        from ConfigParser import SafeConfigParser
        parser = SafeConfigParser()
        parser.read([ os.path.expanduser('~/.lastfmsubmitd/conf') ])
        self.password_hash = hashlib.md5(parser.get('account', 'password')).hexdigest()

    def slot_new_track(self):
        self.timer.stop()
        self.current_track = None
        tags = minirok.Globals.playlist.get_current_tags()

        try:
            self.current_track = Submission(tags)
        except Submission.RequiredDataMissing, e:
            minirok.logger.info('track missing required tags, not scrobbling')
        except Submission.TrackTooShort, e:
            minirok.logger.info('track shorter than %d seconds, '
                                'not scrobbling', TRACK_MIN_LENGTH)
        else:
            runtime = min(TRACK_SUBMIT_SECONDS,
                          self.current_track.length * TRACK_SUBMIT_PERCENT)
            self.timer.start(runtime * 1000)

        with self.mutex:
            self.mutex.notify()

    def slot_engine_status_changed(self, new_status):
        if new_status == engine.State.PAUSED:
            self.timer.pause()
        elif new_status == engine.State.PLAYING:
            self.timer.resume()
        elif new_status == engine.State.STOPPED:
            self.timer.stop()
            self.current_track = None
            with self.mutex:
                self.mutex.notify()

    def slot_timer_timeout(self):
        with self.mutex:
            self.scrobble_queue.append(self.current_track)
            self.current_track = None
            minirok.logger.debug('track queued for scrobbling') # XXX

    ##

    def run(self):
        while True:
            if self.session_key is None:
                try:
                    self.do_handshake()
                except HandshakeFatalError, e:
                    minirok.logger.error('aborting scrobbler: %s', e)
                    return

            with self.mutex:
                self.mutex.wait()
                current_track = self.current_track
                scrobble_tracks = sorted(self.scrobble_queue,
                                         key=lambda t: t.start_time)
                if not (current_track or scrobble_tracks):
                    continue
                else:
                    self.scrobble_queue[:] = [] # We may return them later

            ##

            if current_track is not None:
                params = { 's': self.session_key }
                params.update(current_track.get_now_playing_params())

                req = Request(self.now_playing_url, params)

                if req.failed:
                    minirok.logger.info(
                        'could not send "now playing" information: %s', req.error)
                    if req.error.startswith('BADSESSION'):
                        self.session_key = None # Trigger re-handshake
                    else:
                        self.failure_count += 1
                        if self.failure_count >= MAX_FAILURES:
                            self.session_key = None
                else:
                    minirok.logger.debug('sent "now playing" information successfully') # XXX

            ##

            failed_index = None

            for start in range(0, len(scrobble_tracks), MAX_TRACKS_AT_ONCE):
                params = { 's': self.session_key }
                tracks = scrobble_tracks[start:start+MAX_TRACKS_AT_ONCE]

                for i, track in enumerate(tracks):
                    params.update(track.get_params(i))

                req = Request(self.scrobble_url, params)

                if req.failed:
                    failed_index = start
                    if req.error.startswith('BADSESSION'):
                        self.session_key = None # Trigger re-handshake
                    else:
                        minirok.logger.info('scrobbling %d track(s) failed: %s',
                                            len(tracks), req.error)
                        self.failure_count += 1
                        if self.failure_count >= MAX_FAILURES:
                            self.session_key = None
                    break # Do not remove without changing the extend() below
                else:
                    minirok.logger.debug('scrobbled %d track(s) successfully', len(scrobble_tracks)) # XXX

            if failed_index is not None:
                with self.mutex:
                    self.scrobble_queue.extend(scrobble_tracks[failed_index:])

    def do_handshake(self):
        while True:
            now = str(int(time.time()))
            params = {
                'hs': 'true',
                'p': PROTOCOL_VERSION,
                'c': CLIENT_IDENTIFIER,
                'v': minirok.__version__,
                'u': 'dato',
                't': now,
                'a': hashlib.md5(self.password_hash + now).hexdigest(),
            }
            req = HandshakeRequest(HANDSHAKE_URL, params)

            if req.failed:
                minirok.logger.info('scrobbler handshake failed (%s), '
                    'retrying in %d minute(s)', req.error, self.pause_duration)
                self.sleep(self.pause_duration * 60)
                if self.pause_duration < MAX_SLEEP_MINUTES:
                    self.pause_duration = min(MAX_SLEEP_MINUTES,
                                              self.pause_duration * 2)
            else:
                self.failure_count = 0
                self.pause_duration = 1
                self.session_key = req.body[1]
                self.scrobble_url = req.body[3]
                self.now_playing_url = req.body[2]
                minirok.logger.debug('scrobbling handshake successful') # XXX
                break

    ##

    def apply_preferences(self):
        # TODO: what if there's a queue and we get disabled?
        if minirok.Globals.preferences.enable_lastfm:
            func = self.connect
        else:
            func = self.disconnect

        func(minirok.Globals.playlist, QtCore.SIGNAL('new_track'),
                self.slot_new_track)

        func(minirok.Globals.engine, QtCore.SIGNAL('status_changed'),
                self.slot_engine_status_changed)

        func(self.timer, QtCore.SIGNAL('timeout()'), self.slot_timer_timeout)
