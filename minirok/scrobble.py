#! /usr/bin/env python
## Hey, Python: encoding=utf-8
#
# Copyright (c) 2007-2011 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

"""Last.fm scrobbling support.

See <http://www.last.fm/api/submissions>.
"""

from __future__ import with_statement

import minirok

import errno
import hashlib
import httplib
import os
import re
import socket
import string
import threading
import time
import urllib
import urlparse

try:
    import json
except ImportError:
    import simplejson as json

try:
    import psutil
except ImportError:
    _has_psutil = False
else:
    _has_psutil = True

from PyQt4 import QtCore
from PyKDE4 import kdecore

from minirok import (
    engine,
    util,
)

# TODO: Quitting Minirok while playing will not submit the current track until
# the next time Minirok starts (via the spool).

# TODO: Use KWallet for the password?

##

Server = util.Enum('Last.fm', 'Libre.fm', 'Other')
ServerURL = {
    Server.Lastfm: 'http://post.audioscrobbler.com:80/',
    Server.Librefm: 'http://turtle.libre.fm:80/',
}

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

APPDATA_SCROBBLE = 'scrobble'
APPDATA_SCROBBLE_LOCK = 'scrobble.lock'

##

class Submission(object):

    class RequiredDataMissing(Exception):
        pass

    class TrackTooShort(Exception):
        pass

    def __init__(self, tag_dict):
        """Create a Submission object from a dict of tags.

        Args:
          tag_dict: a dictionary as returned by Playlist.get_current_tags(),
            i.e., containing 'Title', 'Artist', etc.

        Raises:
          Submission.RequiredDataMissing: if any of Title, Artist, or Length are
            not present or empty in tag_dict.
          Submission.TrackTooShort: if tag_dict['Length'] is smaller than
            scrobble.TRACK_MIN_LENGTH.
        """
        if not all(tag_dict.get(x) for x in ['Title', 'Artist', 'Length']):
            raise self.RequiredDataMissing()
        elif tag_dict['Length'] < TRACK_MIN_LENGTH:
            raise self.TrackTooShort()

        self.length = tag_dict['Length']
        self.start_time = int(time.time())

        self.param = {
            'm': '',  # MusicBrainz ID, which we don't support.
            'r': '',  # User rating (love/ban/skip), which we don't support.
            'o': SOURCE_USER,
            'l': str(self.length),
            'i': str(self.start_time),
            't': util.ensure_utf8(tag_dict['Title']),
            'a': util.ensure_utf8(tag_dict['Artist']),
            'b': util.ensure_utf8(tag_dict.get('Album', '')),
            'n': util.ensure_utf8(tag_dict.get('Track', '')),
        }

    def get_params(self, i=0):
        """Return a dict suitable for a scrobbling submission to Last.fm.

        Args:
          i: the index to use for this track: m[i], r[i], etc.
        """
        return dict(('%s[%d]' % (k, i), v) for k, v in self.param.items())

    def get_now_playing_params(self):
        """Return a dict suitable for a "now playing" submission to Last.fm."""
        return dict((k, self.param[k]) for k in list('atblnm'))

    def serialize(self):
        # TODO(dato): update this format to include a version number.
        return json.dumps(self.param, indent=4)

    @classmethod
    def deserialize(cls, string):
        """Construct a Submission object from a string returned by serialize().

        Args:
          string: a string previously returned by serialize(), typically in
            JSON format.

        Returns:
          a Submission object mathing the originally serialized object, or None
          if string could not be parsed as a valid serialization of a
          Submission object.
        """
        try:
            decoded_json = json.loads(string)
        except ValueError, e:
            return None
        else:
            decoded_json = dict((k.encode('utf-8'), v.encode('utf-8'))
                                for k, v in decoded_json.iteritems())

        if set(decoded_json.keys()) == set('mrolintba'):
            obj = cls.__new__(cls)
            obj.param = decoded_json
            obj.length = int(decoded_json['l'])
            obj.start_time = int(decoded_json['i'])
            return obj
        else:
            return None

##

class HandshakeFatalError(Exception):
    pass

##

class Request(object):
    """A request class, doing some error parsing.

    Creating a Request object will immediately perform the request against the
    specified URL. If it failed, the "failed" attribute will be True, and
    "error" will contain any descriptive error message that could be obtained.

    Error conditions include:

      - socket.error
      - HTTP errors (status codes other than 200)
      - empty response from the server
      - first word of the response not being "OK"
    """
    def __init__(self, url, params):
        self.body = []
        self.error = None
        self.failed = False

        url = urlparse.urlparse(url)
        conn = httplib.HTTPConnection(url.netloc)  # Includes host and port.
        try:
            conn.request(
                'POST', url.path, urllib.urlencode(params),
                {'Content-Type': 'application/x-www-form-urlencoded'})
        except socket.error, e:
            self.failed = True
            self.error = e.args[1]  # No e.message available.
        else:
            resp = conn.getresponse()

            if resp.status != httplib.OK:
                self.failed = True
                self.error = resp.reason
            else:
                self.body = resp.read().rstrip('\n').split('\n')

                if not any(self.body):
                    self.failed = True
                    self.error = 'no response received from server'
                elif self.body[0].split()[0] != 'OK':
                    self.failed = True
                    self.error = re.sub(r'^FAILED\s+', '', self.body[0])


class HandshakeRequest(Request):
    """A class to perform the handshake, detecting fatal error.

    In addition to all the possible failures in the part class, this subclass:

      - raises HandshakeFatalError() if the response from the server starts with
        the words BANNED or BADTIME. These are failure modes that cannot be
        fixed without user intervention.

      - sets "failed" to true if the response from the server is not exactly 4
        lines long ("OK", session_key, scrobble_url, now_playing_url).
    """
    def __init__(self, url, params):
        super(HandshakeRequest, self).__init__(url, params)

        if self.failed:
            if re.search(r'^(BANNED|BADTIME)', self.error):
                raise HandshakeFatalError(self.error)
        elif len(self.body) != 4:
            self.failed = True
            self.error = 'unexpected response from scrobbler server:\n%r' % (
                self.body,)

##

class ProcInfo(object):

    def __init__(self, pid=None):
        if pid is None:
            pid = os.getpid()

        d = self.data = {}

        if not _has_psutil:
            d['pid'] = pid
            d['version'] = '1.0'
        else:
            d['pid'] = pid
            d['version'] = '1.1'
            try:
                d['cmdline'] = psutil.Process(pid).cmdline
            except psutil.NoSuchProcess:
                d['version'] = '1.0'

    def serialize(self):
        return json.dumps(self.data, indent=4)

    def isRunning(self):
        if self.data['version'] == '1.0':
            try:
                os.kill(self.data['pid'], 0)
            except OSError, e:
                return (False if e.errno == errno.ESRCH
                        else True)  # ESRCH: no such PID.
            else:
                return True
        elif self.data['version'] == '1.1':
            try:
                proc = psutil.Process(self.data['pid'])
            except psutil.NoSuchProcess:
                return False
            else:
                return proc.cmdline == self.data['cmdline']

    @classmethod
    def load_from_fileobj(cls, fileobj):
        try:
            param = json.load(fileobj)
        except ValueError:
            return None
        else:
            version = param.get('version', None)

            if version == '1.0':
                keys = ['version', 'pid']
            elif version == '1.1':
                if _has_psutil:
                    keys = ['version', 'pid', 'cmdline']
                else:  # Downgrade format.
                    param['version'] = '1.0'
                    keys = ['version', 'pid']
            else:
                return None

            obj = cls.__new__(cls)
            try:
                obj.data = dict((k, param[k]) for k in keys)
            except KeyError:
                return None
            else:
                return obj

##

class Scrobbler(QtCore.QObject, threading.Thread):

    def __init__(self):
        QtCore.QObject.__init__(self)
        threading.Thread.__init__(self)
        self.setDaemon(True)

        self.user = None
        self.password_hash = None
        self.handshake_url = None

        self.session_key = None
        self.scrobble_url = None
        self.now_playing_url = None

        self.failure_count = 0
        self.pause_duration = 1  # minutes
        self.scrobble_queue = []
        self.current_track = None
        self.track_to_spool_file = {}

        self.mutex = threading.Lock()
        self.event = threading.Event()
        self.timer = util.QTimerWithPause()
        self.configured = threading.BoundedSemaphore()
        self.timer.setSingleShot(True)

        util.CallbackRegistry.register_apply_prefs(self.apply_preferences)
        self.apply_preferences()   # Connect signals/slots, read user/passwd.
        self.configured.acquire()  # Force block if initial config is faulty.

        appdata = str(kdecore.KGlobal.dirs().saveLocation('appdata'))
        do_queue = False
        self.spool = os.path.join(appdata, APPDATA_SCROBBLE)

        # Spool directory handling: create it if it doesn't exist...
        if not os.path.isdir(self.spool):
            try:
                os.mkdir(self.spool)
            except OSError, e:
                minirok.logger.error('could not create scrobbling spool: %s', e)
                self.spool = None
        # ... else ensure it is readable and writable.
        elif not os.access(self.spool, os.R_OK | os.W_OK):
            minirok.logger.error('scrobbling spool is not readable/writable')
            self.spool = None
        # If not, we try to assess whether this Minirok instance should try to
        # submit the existing entries, if any. Supposedly, the Last.fm server
        # has some support for detecting duplicate submissions, but we're
        # adviced not to rely on it (<4A7FECF7.5030100@last.fm>), so we use a
        # lock file to signal that some Minirok process is taking care of the
        # submissions from the spool directory. (This scheme, I realize,
        # doesn't get all corner cases right, but will have to suffice for now.
        # For example, if Minirok A starts, then Minirok B starts, and finally
        # Minirok A quits and Minirok C starts, Minirok B and C will end up
        # both trying to submit B's entries that haven't been able to be
        # submitted yet. There's also the race-condition-du-jour, of course.)
        else:
            scrobble_lock = os.path.join(appdata, APPDATA_SCROBBLE_LOCK)
            try:
                lockfile = open(scrobble_lock)
            except IOError, e:
                if e.errno == errno.ENOENT:
                    do_queue = True
                else:
                    raise
            else:
                proc = ProcInfo.load_from_fileobj(lockfile)

                if proc and proc.isRunning():
                    minirok.logger.info(
                        'Minirok already running (pid=%d), '
                        'not scrobbling existing items', proc.data['pid'])
                else:
                    do_queue = True

        if do_queue:
            self.lock_file = scrobble_lock

            with open(self.lock_file, 'w') as lock:
                lock.write(ProcInfo().serialize())

            for fname in os.listdir(self.spool):
                path = os.path.join(self.spool, fname)
                try:
                    track = Submission.deserialize(open(path).read())
                except IOError, e:
                    minirok.logger.warn(
                        'could not read spooled track from %r', path)
                else:
                    if track is not None:
                        self.scrobble_queue.append(track)
                        self.track_to_spool_file[track] = path

            self.scrobble_queue.sort(key=lambda t: t.start_time)
        else:
            self.lock_file = None

        util.CallbackRegistry.register_save_config(self.cleanup)

    def cleanup(self):
        if self.lock_file is not None:
            try:
                os.unlink(self.lock_file)
            except:
                pass

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
            self.event.set()

    def slot_engine_status_changed(self, new_status):
        if new_status == engine.State.PAUSED:
            self.timer.pause()
        elif new_status == engine.State.PLAYING:
            self.timer.resume()
        elif new_status == engine.State.STOPPED:
            self.timer.stop()
            self.current_track = None
            with self.mutex:
                self.event.set()

    def slot_timer_timeout(self):
        if not self.isAlive():
            # Abort this function if the scrobbling thread is not running; this
            # happens if we received a BANNED or BADTIME from the server. In
            # such cases, it's probably not a bad idea not to write anything to
            # disk. (Well, supposedly there's precious data we could save in
            # the case of BANNED, and submit it again with a fixed version, hm.)
            return

        with self.mutex:
            self.scrobble_queue.append(self.current_track)

            if self.spool is not None:
                path = self.write_track_to_spool(self.current_track)

                if path is None:
                    minirok.logger.warn(
                        'could not create file in scrobbling spool')
                else:
                    self.track_to_spool_file[self.current_track] = path

            self.current_track = None
            minirok.logger.debug('track queued for scrobbling')  # XXX.

    def write_track_to_spool(self, track):
        path = os.path.join(self.spool, str(track.start_time))

        for x in [''] + list(string.ascii_lowercase):
            try:
                f = util.creat_excl(path + x)
            except OSError, e:
                if e.errno != errno.EEXIST:
                    raise
            else:
                f.write(track.serialize())
                f.flush()  # Otherwise write() syscall happens after fsync().
                os.fsync(f.fileno())
                f.close()
                return path + x

    ##

    def run(self):
        if self.user is None:
            # We're not configured to run, so we hang on here.
            self.configured.acquire()

        if self.scrobble_queue: # Any tracks loaded from spool?
            with self.mutex:
                self.event.set()

        while True:
            if self.session_key is None:
                try:
                    self.do_handshake()
                except HandshakeFatalError, e:
                    minirok.logger.error('aborting scrobbler: %s', e)
                    return

            self.event.wait()

            with self.mutex:
                self.event.clear()
                current_track = self.current_track

            ##

            while self.scrobble_queue:
                params = {'s': self.session_key}

                with self.mutex:
                    tracks = self.scrobble_queue[0:MAX_TRACKS_AT_ONCE]

                for i, track in enumerate(tracks):
                    params.update(track.get_params(i))

                req = Request(self.scrobble_url, params)

                if req.failed:
                    if req.error.startswith('BADSESSION'):
                        self.session_key = None  # Trigger re-handshake.
                    else:
                        minirok.logger.info('scrobbling %d track(s) failed: %s',
                                            len(tracks), req.error)
                        self.failure_count += 1
                        if self.failure_count >= MAX_FAILURES:
                            self.session_key = None
                    break
                else:
                    minirok.logger.debug('scrobbled %d track(s) successfully',
                                         len(tracks))  # XXX.

                    for t in tracks:
                        try:
                            os.unlink(self.track_to_spool_file.pop(t))
                        except KeyError:
                            pass
                        except OSError, e:
                            if e.errno != errno.ENOENT:
                                raise

                    with self.mutex:
                        self.scrobble_queue[0:len(tracks)] = []

            ##

            if current_track is not None and self.session_key is not None:
                params = {'s': self.session_key}
                params.update(current_track.get_now_playing_params())

                req = Request(self.now_playing_url, params)

                if req.failed:
                    minirok.logger.info(
                        'could not send "now playing" information: %s',
                        req.error)
                    if req.error.startswith('BADSESSION'):
                        self.session_key = None  # Trigger re-handshake.
                    else:
                        self.failure_count += 1
                        if self.failure_count >= MAX_FAILURES:
                            self.session_key = None
                else:
                    minirok.logger.debug(
                        'sent "now playing" information successfully')  # XXX.

            ##

            if self.session_key is None:
                # Ensure we retry pending actions as soon as we've successfully
                # handshaked again.
                with self.mutex:
                    self.event.set()

    def do_handshake(self):
        while True:
            now = str(int(time.time()))
            params = {
                'hs': 'true',
                'p': PROTOCOL_VERSION,
                'c': CLIENT_IDENTIFIER,
                'v': minirok.__version__,
                'u': self.user,
                't': now,
                'a': hashlib.md5(self.password_hash + now).hexdigest(),
            }
            req = HandshakeRequest(self.handshake_url, params)

            if req.failed:
                if re.search(r'^BADAUTH', req.error):
                    minirok.logger.warn(
                        'scrobbler handshake failed: bad password')
                    self.configured.acquire()
                else:
                    minirok.logger.info(
                        'scrobbler handshake failed (%s), retrying in '
                        '%d minute(s)', req.error, self.pause_duration)
                    time.sleep(self.pause_duration * 60)
                    if self.pause_duration < MAX_SLEEP_MINUTES:
                        self.pause_duration = min(MAX_SLEEP_MINUTES,
                                                  self.pause_duration * 2)
            else:
                self.failure_count = 0
                self.pause_duration = 1
                self.session_key = req.body[1]
                self.scrobble_url = req.body[3]
                self.now_playing_url = req.body[2]
                minirok.logger.debug('scrobbling handshake successful')  # XXX.
                break

    ##

    def apply_preferences(self):
        # TODO: what if there's a queue and we get disabled?
        prefs = minirok.Globals.preferences.lastfm

        if prefs.enable:
            connect_or_disconnect = self.connect
            self.user = prefs.user
            # TODO: The password is stored in plain in the configuration file..
            self.password_hash = hashlib.md5(prefs.password).hexdigest()
            try:
                self.handshake_url = ServerURL[prefs.server]
            except KeyError:
                self.handshake_url = prefs.handshake_url
            self.session_key = None
            try:
                self.configured.release()
            except ValueError:
                pass
        else:
            connect_or_disconnect = self.disconnect

        connect_or_disconnect(minirok.Globals.playlist,
                              QtCore.SIGNAL('new_track'),
                              self.slot_new_track)

        connect_or_disconnect(minirok.Globals.engine,
                              QtCore.SIGNAL('status_changed'),
                              self.slot_engine_status_changed)

        connect_or_disconnect(self.timer,
                              QtCore.SIGNAL('timeout()'),
                              self.slot_timer_timeout)
