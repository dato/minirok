#! /usr/bin/env python
## Hey, Python: encoding=utf-8
#
# Copyright (c) 2010, 2011 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import minirok

import BaseHTTPServer
import errno
import functools
import httplib
import itertools
import os
import shutil
import StringIO
import subprocess
import sys
import threading
import time
import urlparse

from PyQt4 import QtCore

import mox
import nose.plugins

from minirok import (
    engine,
    playlist,
    scrobble,
    tests,
    util,
)

##

MOCK_HS_URL = 'http://does.not.resolve/scrobble'

class MockLastfmPreferences(object):

    def __init__(self, enable=True, user='testu', password='testp',
                 server=scrobble.Server.Other, handshake_url=MOCK_HS_URL):
        self.enable = enable
        self.user = user
        self.password = password
        self.server = server
        self.handshake_url = handshake_url

##

class SubmissionClassTest(tests.BaseTest):

    def testRequiredTags(self):
        self.assertRaises(scrobble.Submission.RequiredDataMissing,
                          scrobble.Submission, {})

        self.assertRaises(scrobble.Submission.RequiredDataMissing,
                          scrobble.Submission, {'Title': 'a', 'Artist': 'b'})

        self.assertRaises(scrobble.Submission.RequiredDataMissing,
                          scrobble.Submission,
                          {'Title': 'a', 'Artist': '', 'Length': 180})

    def testMinTrackLength(self):
        self.assertRaises(scrobble.Submission.TrackTooShort,
                          scrobble.Submission,
                          {'Title': 'a', 'Artist': 'b', 'Length': 29})

        # The following should not raise.
        scrobble.Submission({'Title': 'a', 'Artist': 'b', 'Length': 30,
                             'Album': '', 'Track': '7'})

    def testTrackNumberOrAlbumNotRequired(self):
        # The following should not raise.
        scrobble.Submission({'Title': 'a', 'Artist': 'b', 'Length': 180})

    def testParams(self):
        tags = {
            'Title': 'Anda',
            'Artist': 'Jorge Drexler',
            'Track': '6',
            'Album': 'Mira que eres canalla, Aute',
            'Length': 237,
        }
        now = time.time()
        submission = scrobble.Submission(tags)

        params = submission.get_params(7)
        submission_time = int(params.pop('i[7]'))

        self.assertDictEqual(
            {'m[7]': '', 'r[7]': '', 'o[7]': 'P', 'l[7]': '237',
             't[7]': 'Anda', 'a[7]': 'Jorge Drexler', 'n[7]': '6',
             'b[7]': 'Mira que eres canalla, Aute'}, params)

        self.assertAlmostEqual(now, submission_time, delta=5)

    def testNowPlayingParams(self):
        tags = {
            'Title': 'Anda',
            'Artist': 'Jorge Drexler',
            'Track': '6',
            'Album': 'Mira que eres canalla, Aute',
            'Length': 237,
        }
        submission = scrobble.Submission(tags)
        np_params = submission.get_now_playing_params()

        self.assertDictEqual(
            {'m': '', 'l': '237', 'n': '6', 't': 'Anda', 'a': 'Jorge Drexler',
             'b': 'Mira que eres canalla, Aute'}, np_params)

    def testParamsHandleNonAsciiCorrectly(self):
        tags = {
            'Title': 'N\xc3\xbd Batter\xc3\xad',  # UTF-8
            'Artist': 'Sigur R\xf3s',             # ISO-8859-1
            'Album': u'\xc1g\xe6tis Byrjun',      # Unicode
            'Length': 493,
        }

        submission = scrobble.Submission(tags)
        params = submission.get_params()
        params.pop('i[0]')
        np_params = submission.get_now_playing_params()

        self.assertDictEqual(
            {'m[0]': '', 'r[0]': '', 'o[0]': 'P', 'l[0]': '493',
             't[0]': 'Ný Batterí', 'a[0]': 'Sigur Rós',
             'b[0]': 'Ágætis Byrjun', 'n[0]': ''}, params)

        self.assertDictEqual(
            {'m': '', 'l': '493', 'n': '', 't': 'Ný Batterí',
             'a': 'Sigur Rós', 'b': 'Ágætis Byrjun'}, np_params)

    def testSerializeDeserializeOk(self):
        tags = {
            'Title': 'Anda',
            'Artist': 'Jorge Drexler',
            'Track': '6',
            'Album': 'Mira que eres canalla, Aute',
            'Length': 237,
        }
        submission = scrobble.Submission(tags)
        params = submission.get_params()
        serialize_output = submission.serialize()
        new_submission_obj = scrobble.Submission.deserialize(serialize_output)

        self.assertDictEqual(params, new_submission_obj.get_params())

    def testDeserializeJsonOk(self):
        # If our serialization format changes, a non-backwards compatible change
        # in deserialize() will break this test.
        json_input = ('{"m": "", "n": "6", "o": "P", "l": "237", "r": "", '
                      '"i": "1288900046", "a": "Jorge Drexler", "t": "Anda", '
                      '"b": "Mira que eres canalla, Aute"}')
        submission = scrobble.Submission.deserialize(json_input)

        self.assertDictEqual(
            {'m[0]': '', 'r[0]': '', 'o[0]': 'P', 'l[0]': '237', 'n[0]': '6',
             'i[0]': '1288900046', 't[0]': 'Anda', 'a[0]': 'Jorge Drexler',
             'b[0]': 'Mira que eres canalla, Aute'},
            submission.get_params())

        self.assertEqual(237, submission.length)
        self.assertEqual(1288900046, submission.start_time)

    def testDeserializeRubbishReturnsNone(self):
        self.assertIsNone(scrobble.Submission.deserialize('{rubbish'))

    def testDeserializeRequiresStrictSetOfDictKeys(self):
        self.assertIsNone(scrobble.Submission.deserialize(
            '{"m": "", "r": "", "o": "", "l": "", "i": "", "n": "",'
            '"t": "", "b": "", "a": "", "extra_key": "rejected"}'))

        self.assertIsNone(scrobble.Submission.deserialize(
            '{"m": "", "r": "", "o": "", "l": "", "i": "", "n": ""}'))

##

class RequestClassTest(tests.BaseTest):

    CONTENT_TYPE = {'Content-Type': 'application/x-www-form-urlencoded'}

    def setUp(self):
        super(RequestClassTest, self).setUp()
        self.mox.StubOutClassWithMocks(scrobble.httplib, 'HTTPConnection')

    def testPortInUrlAndPathHonored(self):
        conn = scrobble.httplib.HTTPConnection('dev.example.org:8080')
        (conn.request('POST', '/submit.cgi', '', self.CONTENT_TYPE).
         AndRaise(self.TerminateEarly()))

        self.mox.ReplayAll()
        self.assertRaises(self.TerminateEarly, scrobble.Request,
                          'http://dev.example.org:8080/submit.cgi', {})
        self.mox.VerifyAll()

    def testUrlParamsProperlyEncodedAndPassed(self):
        conn = scrobble.httplib.HTTPConnection('example.org')
        # This may be flaky, is it relying in dict keys order below?
        (conn.request('POST', '', 'a=1+2%2F3&b=0', self.CONTENT_TYPE).
         AndRaise(self.TerminateEarly()))

        self.mox.ReplayAll()
        self.assertRaises(self.TerminateEarly, scrobble.Request,
                          'http://example.org', {'a': '1 2/3', 'b': 0})
        self.mox.VerifyAll()

    def testSocketErrorResultsInFailure(self):
        conn = scrobble.httplib.HTTPConnection('example.org')
        (conn.request('POST', '/', '', self.CONTENT_TYPE).
         AndRaise(scrobble.socket.error(1, 'foo')))

        self.mox.ReplayAll()
        req = scrobble.Request('http://example.org/', {})
        self.assertTrue(req.failed)
        self.assertEqual('foo', req.error)
        self.mox.VerifyAll()

    def testHttpErrorResultsInFailure(self):
        conn = scrobble.httplib.HTTPConnection('example.org')
        conn.request('POST', '/', '', self.CONTENT_TYPE)
        response = conn.getresponse().AndReturn(
            self.mox.CreateMock(scrobble.httplib.HTTPResponse))
        response.status = scrobble.httplib.NOT_FOUND
        response.reason = 'we could not find what you requested!'

        self.mox.ReplayAll()
        req = scrobble.Request('http://example.org/', {})
        self.assertTrue(req.failed)
        self.assertEqual('we could not find what you requested!', req.error)
        self.mox.VerifyAll()

    def testSocketErrorInGetResponseHandled(self):
        conn = scrobble.httplib.HTTPConnection('example.org')
        conn.request('POST', '/', '', self.CONTENT_TYPE)
        conn.getresponse().AndRaise(scrobble.socket.error(1, 'bar'))

        self.mox.ReplayAll()
        req = scrobble.Request('http://example.org/', {})
        self.assertTrue(req.failed)
        self.assertEqual('bar', req.error)
        self.mox.VerifyAll()

    def testEmptyBodyResultsInFailure(self):
        conn = scrobble.httplib.HTTPConnection('example.org')
        conn.request('POST', '/', '', self.CONTENT_TYPE)
        response = conn.getresponse().AndReturn(
            self.mox.CreateMock(scrobble.httplib.HTTPResponse))
        response.status = scrobble.httplib.OK
        response.read().AndReturn('')

        self.mox.ReplayAll()
        req = scrobble.Request('http://example.org/', {})
        self.assertTrue(req.failed)
        self.assertEqual('no response received from server', req.error)
        self.mox.VerifyAll()

    def testSocketErrorInResponseReadHandled(self):
        conn = scrobble.httplib.HTTPConnection('example.org')
        conn.request('POST', '/', '', self.CONTENT_TYPE)
        response = conn.getresponse().AndReturn(
            self.mox.CreateMock(scrobble.httplib.HTTPResponse))
        response.status = scrobble.httplib.OK
        response.read().AndRaise(scrobble.socket.error(1, 'baz'))

        self.mox.ReplayAll()
        req = scrobble.Request('http://example.org/', {})
        self.assertTrue(req.failed)
        self.assertEqual('baz', req.error)
        self.mox.VerifyAll()

    def testOkInAnswerResultsInSuccess(self):
        conn = scrobble.httplib.HTTPConnection('example.org')
        conn.request('POST', '/', '', self.CONTENT_TYPE)
        response = conn.getresponse().AndReturn(
            self.mox.CreateMock(scrobble.httplib.HTTPResponse))
        response.status = scrobble.httplib.OK
        response.read().AndReturn(
            'OK Submission processed successfully\nBYE')

        self.mox.ReplayAll()
        req = scrobble.Request('http://example.org/', {})
        self.assertFalse(req.failed)
        self.assertEqual(['OK Submission processed successfully', 'BYE'],
                         req.body)
        self.mox.VerifyAll()

    def testOnlyOkInAnswerResultsInSuccess(self):
        conn = scrobble.httplib.HTTPConnection('example.org')
        conn.request('POST', '/', '', self.CONTENT_TYPE)
        response = conn.getresponse().AndReturn(
            self.mox.CreateMock(scrobble.httplib.HTTPResponse))
        response.status = scrobble.httplib.OK
        response.read().AndReturn('OK')

        self.mox.ReplayAll()
        req = scrobble.Request('http://example.org/', {})
        self.assertFalse(req.failed)
        self.assertEqual(['OK'], req.body)
        self.mox.VerifyAll()

    def testAnythingElseResultsInFailure(self):
        conn = scrobble.httplib.HTTPConnection('example.org')
        conn.request('POST', '/', '', self.CONTENT_TYPE)
        response = conn.getresponse().AndReturn(
            self.mox.CreateMock(scrobble.httplib.HTTPResponse))
        response.status = scrobble.httplib.OK
        response.read().AndReturn("FAILED We don't like you")

        self.mox.ReplayAll()
        req = scrobble.Request('http://example.org/', {})
        self.assertTrue(req.failed)
        self.assertEqual(["FAILED We don't like you"], req.body)
        self.assertEqual("We don't like you", req.error)
        self.mox.VerifyAll()

##

class HandshakeRequestClassTest(RequestClassTest):

    def setUp(self):
        super(HandshakeRequestClassTest, self).setUp()

        # We play nasty here, and we re-execute all tests in RequestClassTest
        # against HandshakeRequest, since more of their semantics are shared and
        # we want to ensure the subclassing has been done properly. Only the two
        # tests noted below are skipped.
        self.stubs.Set(scrobble, 'Request', scrobble.HandshakeRequest)

    def testOkInAnswerResultsInSuccess(self):
        """Do not inherit this test from base class."""
        pass

    def testOnlyOkInAnswerResultsInSuccess(self):
        """Do not inherit this test from base class."""
        pass

    def testBannedInResponseResultsInFatalError(self):
        conn = scrobble.httplib.HTTPConnection('example.org')
        conn.request('POST', '/', '', self.CONTENT_TYPE)
        response = conn.getresponse().AndReturn(
            self.mox.CreateMock(scrobble.httplib.HTTPResponse))
        response.status = scrobble.httplib.OK
        response.read().AndReturn("BANNED We really don't like you")

        self.mox.ReplayAll()
        self.assertRaisesRegexp(
            scrobble.HandshakeFatalError, r"BANNED We really don't like you",
            scrobble.Request, 'http://example.org/', {})
        self.mox.VerifyAll()

    def testBadtimeInResponseResultsInFatalError(self):
        conn = scrobble.httplib.HTTPConnection('example.org')
        conn.request('POST', '/', '', self.CONTENT_TYPE)
        response = conn.getresponse().AndReturn(
            self.mox.CreateMock(scrobble.httplib.HTTPResponse))
        response.status = scrobble.httplib.OK
        response.read().AndReturn('BADTIME')

        self.mox.ReplayAll()
        self.assertRaisesRegexp(
            scrobble.HandshakeFatalError, 'BADTIME',
            scrobble.Request, 'http://example.org/', {})
        self.mox.VerifyAll()

    def testWrongNumberOfResponseLinesResultsInFailure(self):
        conn = scrobble.httplib.HTTPConnection('example.org')
        conn.request('POST', '/', '', self.CONTENT_TYPE)
        response = conn.getresponse().AndReturn(
            self.mox.CreateMock(scrobble.httplib.HTTPResponse))
        response.status = scrobble.httplib.OK
        response.read().AndReturn("""OK
                                     your_session_key
                                     http://your.scrobble.url
                                     http://your.now-playing.url
                                     http://your.insidious.extra.url""")

        self.mox.ReplayAll()
        req = scrobble.Request('http://example.org/', {})
        self.assertTrue(req.failed)
        self.assertRegexpMatches(req.error,
            '^unexpected response from scrobbler server')
        self.mox.VerifyAll()

##

class _ProcInfoCommonTest(tests.BaseTest):
    """Common tests for ProcInfo tests."""

    def setUp(self):
        super(_ProcInfoCommonTest, self).setUp()
        self.proc = subprocess.Popen(['sleep', '3600'])

    def tearDown(self):
        super(_ProcInfoCommonTest, self).tearDown()
        try:
            os.kill(self.proc.pid, 9)
        except OSError, e:
            if e.errno != errno.ESRCH:
                raise

    def testEndToEnd(self):
        info = scrobble.ProcInfo(self.proc.pid)
        json = info.serialize()
        fileobj = StringIO.StringIO(json)
        newinfo = scrobble.ProcInfo.load_from_fileobj(fileobj)

        self.assertTrue(newinfo.isRunning())
        self.proc.kill()
        self.proc.wait()
        self.assertFalse(newinfo.isRunning())

    def testEndToEndPsutilGoesAway(self):
        info = scrobble.ProcInfo(self.proc.pid)
        json = info.serialize()
        fileobj = StringIO.StringIO(json)
        self.stubs.Set(scrobble, '_has_psutil', False)
        newinfo = scrobble.ProcInfo.load_from_fileobj(fileobj)

        self.assertTrue(newinfo.isRunning())
        self.proc.kill()
        self.proc.wait()
        self.assertFalse(newinfo.isRunning())

    def testSamePidDifferentCommandLine(self):
        info = scrobble.ProcInfo()
        info.data['pid'] = self.proc.pid
        self.assertEqual(bool(info.isRunning()), not scrobble._has_psutil)

    def testPidThatDoesNotExist(self):
        info = scrobble.ProcInfo(0x7fffffff)
        self.assertFalse(info.isRunning())

    def testDeserializeErrorConditions(self):
        for json in ['{ "bogus": "yes", ', '{ "version": "1.2" }',
                     '{ "version": "1.0" }', '{ "version": 1.1", "pid": "1" }']:
            self.assertIsNone(
                scrobble.ProcInfo.load_from_fileobj(StringIO.StringIO(json)))


class ProcInfoDefaultTest(_ProcInfoCommonTest):
    """Test ProcInfo with the current value of scrobble._has_psutil."""


class ProcessInfoNoPsutilTest(_ProcInfoCommonTest):
    """Test ProcInfo with scrobble._has_psutil set to False."""

    def setUp(self):
        super(ProcessInfoNoPsutilTest, self).setUp()
        # We cannot force testing with _has_psutil set to its opposite value,
        # since that would not work if psutil is in fact not installed. The best
        # we can do is set it to False, increasing coverage when running the
        # tests with psutil installed.
        self.stubs.Set(scrobble, '_has_psutil', False)

##

class ScrobblerTest(tests.BaseTest):

    def setUp(self):
        super(ScrobblerTest, self).setUp()
        self.create_empty_globals()

        self._data = os.path.join(os.environ['KDEHOME'], 'share/apps',
                                  os.path.basename(sys.argv[0]))
        self._spool = os.path.join(self._data, 'scrobble')

        # Some tests in this class only interact with Scrobbler.__init__(), or
        # its indivual methods; others, on the contrary, need to let the
        # Scrobbler thread run (i.e., call scrobbler.start()), in which case we
        # must ensure we don't verify mocks before the thread has run through
        # them. What we do is have a threading.Event on which we wait() before
        # verifying mocks, and have the last mock call call its set() as a side
        # effect.
        self._event = threading.Event()

    def tearDown(self):
        super(ScrobblerTest, self).tearDown()
        shutil.rmtree(self._data, ignore_errors=True)

    def wait(self):
        self._event.wait()

    def stopWaiting(self, *unused_args):
        self._event.set()

    def testSpoolDirectoryCreated(self):
        self.assertFalse(os.path.exists(self._spool))
        scrobbler = scrobble.Scrobbler()
        self.assertTrue(os.path.isdir(self._spool))
        self.assertEqual(self._spool, scrobbler.spool)

    def testOsErrorCaughtWhenCreatingSpool(self):
        self.assertFalse(os.path.exists(self._spool))
        old_mode = os.stat(self._data).st_mode
        try:
            os.chmod(self._data, 0400)
            scrobbler = scrobble.Scrobbler()
            self.assertIsNone(scrobbler.spool)
            self.assertFalse(os.path.exists(self._spool))
        finally:
            os.chmod(self._data, old_mode)

    def testUnwritableSpoolResultsInNoSpool(self):
        os.mkdir(self._spool)
        os.chmod(self._spool, 0400)
        scrobbler = scrobble.Scrobbler()
        self.assertIsNone(scrobbler.spool)
        self.assertTrue(os.path.isdir(self._spool))

    def testNoLockFileHandledOk(self):
        os.mkdir(self._spool)
        lock_file = os.path.join(self._data, 'scrobble.lock')
        scrobbler = scrobble.Scrobbler()

        self.assertTrue(os.path.isfile(lock_file))
        self.assertEqual(
            os.getpid(),
            scrobble.ProcInfo.load_from_fileobj(open(lock_file)).data['pid'])

    def testRunningProcessWithLocksDoesNotOverwriteOrSubmit(self):
        os.mkdir(self._spool)
        lock_file = os.path.join(self._data, 'scrobble.lock')
        prev_lock = '{"version": "1.0", "pid": 1}\n'
        track = scrobble.Submission({'Title': 't1', 'Artist': 'a1',
                                     'Length': 75})

        with open(lock_file, 'w') as f:
            f.write(prev_lock)

        with open(os.path.join(self._spool, 'track1'), 'w') as f:
            f.write(track.serialize())

        scrobbler = scrobble.Scrobbler()
        self.assertEqual(0, len(scrobbler.scrobble_queue))
        self.assertEqual(prev_lock, open(lock_file).read())

    def testUnreadableLockRaisesIOError(self):
        os.mkdir(self._spool)
        lock_file = os.path.join(self._data, 'scrobble.lock')
        open(lock_file, 'w').write('gibberish')
        os.chmod(lock_file, 0)
        self.assertRaises(IOError, scrobble.Scrobbler)

    def testLockFileDeletedAtExit(self):
        os.mkdir(self._spool)
        lock_file = os.path.join(self._data, 'scrobble.lock')
        scrobbler = scrobble.Scrobbler()

        self.assertTrue(os.path.isfile(lock_file))
        util.CallbackRegistry.save_config_all()
        self.assertFalse(os.path.exists(lock_file))

    def testLockFileDeletionErrorDoesNotRaise(self):
        os.mkdir(self._spool)
        lock_file = os.path.join(self._data, 'scrobble.lock')
        scrobbler = scrobble.Scrobbler()

        self.assertTrue(os.path.isfile(lock_file))
        os.unlink(lock_file)
        util.CallbackRegistry.save_config_all()

    def testApplyPreferencesCallbackTriggersHandshake(self):
        self.mox.StubOutWithMock(scrobble.Scrobbler, 'do_handshake')

        scrobbler = scrobble.Scrobbler()
        minirok.Globals.preferences.lastfm = MockLastfmPreferences()

        scrobbler.start()
        scrobbler.do_handshake().WithSideEffects(self.stopWaiting)

        self.mox.ReplayAll()
        util.CallbackRegistry.apply_preferences_all()
        self.wait()
        self.mox.VerifyAll()

    def testHandshakeFatalErrorExitsThread(self):
        minirok.Globals.preferences.lastfm = MockLastfmPreferences()

        scrobbler = scrobble.Scrobbler()

        self.mox.StubOutWithMock(scrobbler, 'do_handshake')
        (scrobbler.do_handshake().
         WithSideEffects(self.stopWaiting).
         AndRaise(scrobble.HandshakeFatalError()))

        self.mox.ReplayAll()
        scrobbler.start()
        self.wait()

        # We've injected the stopWait() side-effect in do_handshake(). After
        # that, pymox still has to raise the exception, and the scrobbler.py
        # code catch it, do a call to logging.error(), and then return. We need,
        # hence, to do some old-fashined waiting...
        for _ in range(10):
            if scrobbler.isAlive():
                time.sleep(0.1)
            else:
                break
        else:
            self.fail('scrobbler did not finish <1s after HandshakeFatalError')

        self.mox.VerifyAll()

    def testDoHandshakeParamsAndFatalErrorPropagated(self):
        minirok.Globals.preferences.lastfm = MockLastfmPreferences()
        scrobbler = scrobble.Scrobbler()

        self.mox.StubOutWithMock(scrobble, 'time')
        self.mox.StubOutWithMock(scrobble, 'HandshakeRequest')

        scrobble.time.time().AndReturn(123.45)
        params = {
            'hs': 'true',
            'p': '1.2.1',
            'c': 'mrk',
            'v': minirok.__version__,
            'u': 'testu',
            't': '123',
            'a': 'cd831b8c5f4b31ae8e62dbd61411ba1b',
        }

        (scrobble.HandshakeRequest(
            MOCK_HS_URL,
            tests.AssertOk(self.assertDictEqual, params)).
         AndRaise(scrobble.HandshakeFatalError('foo')))

        self.mox.ReplayAll()
        self.assertRaisesRegexp(scrobble.HandshakeFatalError, 'foo',
                                scrobbler.do_handshake)
        self.mox.VerifyAll()

    def testDoHandshakeWithErrorsAndWaiting(self):
        self.mox.StubOutWithMock(scrobble, 'time')
        self.mox.StubOutClassWithMocks(scrobble, 'HandshakeRequest')

        minirok.Globals.preferences.lastfm = MockLastfmPreferences()
        scrobbler = scrobble.Scrobbler()

        for i in range(7):
            scrobble.time.time().AndReturn(i * 100)
            handshake_request = scrobble.HandshakeRequest(MOCK_HS_URL,
                                                          mox.IgnoreArg())
            handshake_request.failed = True
            handshake_request.error = 'FAILED Transient failure.'
            scrobble.time.sleep(60 * 2 ** i)

        scrobble.time.time().AndReturn(700)
        handshake_request = scrobble.HandshakeRequest(MOCK_HS_URL,
                                                      mox.IgnoreArg())
        handshake_request.failed = True
        handshake_request.error = 'FAILED Transient failure.'
        scrobble.time.sleep(60 * 120)

        scrobble.time.time().AndReturn(800)
        handshake_request = scrobble.HandshakeRequest(MOCK_HS_URL,
                                                      mox.IgnoreArg())
        handshake_request.failed = False
        handshake_request.body = ['OK',
                                  'your session key',
                                  'your.now_playing.url',
                                  'your.scrobble.url']

        # We'll call do_handshake() a second time to verify that the pause
        # duration is reset:
        scrobble.time.time().AndReturn(900)
        handshake_request = scrobble.HandshakeRequest(MOCK_HS_URL,
                                                      mox.IgnoreArg())
        handshake_request.failed = True
        handshake_request.error = 'FAILED Transient failure.'
        scrobble.time.sleep(60)

        scrobble.time.time().AndReturn(1000)
        handshake_request = scrobble.HandshakeRequest(MOCK_HS_URL,
                                                      mox.IgnoreArg())
        handshake_request.failed = False
        handshake_request.body = ['OK',
                                  'your session key',
                                  'your.now_playing.url',
                                  'your.scrobble.url']

        self.mox.ReplayAll()
        scrobbler.do_handshake()
        scrobbler.do_handshake()
        self.mox.VerifyAll()

    def testDoHandshakeCanHandleOutOfOrderConfigChange(self):
        # This tests that we wouldn't block even if the preferences update came
        # whilst do_handshake() was not waiting for it. (Initially, a Condition
        # object, and not a Semaphore, was used, which created potential
        # deadlock.)
        minirok.Globals.preferences.lastfm = MockLastfmPreferences()
        scrobbler = scrobble.Scrobbler()

        failed_request = self.mox.CreateMock(scrobble.HandshakeRequest)
        failed_request.failed = True
        failed_request.error = 'BADAUTH'

        succeeds_request = self.mox.CreateMock(scrobble.HandshakeRequest)
        succeeds_request.failed = False
        succeeds_request.body = ['OK',
                                 'your session key',
                                 'your.now_playing.url',
                                 'your.scrobble.url']

        self.mox.StubOutWithMock(scrobble, 'time')
        self.mox.StubOutWithMock(scrobble, 'HandshakeRequest')

        scrobble.time.time().AndReturn(123)
        scrobble.time.time().AndReturn(456)

        def UpdateConfig(unused_hs_url, unused_params):
            # This obviously happens out of order because this test is
            # single-threaded, hence do_handshake() cannot be busy blocked
            # whilst executing this.
            minirok.Globals.preferences.lastfm.user = 'user2'
            scrobbler.apply_preferences()

        (scrobble.HandshakeRequest(MOCK_HS_URL,
                                   mox.ContainsKeyValue('u', 'testu')).
         WithSideEffects(UpdateConfig).AndReturn(failed_request))

        (scrobble.HandshakeRequest(
            MOCK_HS_URL,
            mox.And(mox.ContainsKeyValue('t', '456'),
                    mox.ContainsKeyValue('u', 'user2'))).
         AndReturn(succeeds_request))

        self.mox.ReplayAll()
        scrobbler.do_handshake()
        self.mox.VerifyAll()

    def testDoHandshakeHandlesBadAuthByExpectingConfigChange(self):
        # We want to black-box test for the self.configured.wait() call here,
        # so we cannot call do_handshake() from the main thread, as we do in
        # testDoHandshakeHandlesBadAuthByExpectingConfigChange, because that
        # would block us. Will do the start()/wait() dance.
        minirok.Globals.preferences.lastfm = MockLastfmPreferences()
        scrobbler = scrobble.Scrobbler()

        handshake_request = self.mox.CreateMock(scrobble.HandshakeRequest)
        handshake_request.failed = True
        handshake_request.error = 'BADAUTH'

        self.mox.StubOutWithMock(scrobble, 'time')
        self.mox.StubOutWithMock(scrobble, 'HandshakeRequest')

        scrobble.time.time().AndReturn(123)
        (scrobble.HandshakeRequest(MOCK_HS_URL,
                                   mox.ContainsKeyValue('u', 'testu')).
         WithSideEffects(self.stopWaiting).AndReturn(handshake_request))

        self.mox.ReplayAll()
        scrobbler.start()
        self.wait()
        self.mox.VerifyAll()
        self.mox.ResetAll()

        minirok.Globals.preferences.lastfm.user = 'user2'
        scrobble.time.time().AndReturn(456)

        (scrobble.HandshakeRequest(
            MOCK_HS_URL,
            mox.And(mox.ContainsKeyValue('t', '456'),
                    mox.ContainsKeyValue('u', 'user2'))).
         WithSideEffects(self.stopWaiting).AndReturn(handshake_request))

        self._event.clear()
        self.mox.ReplayAll()
        scrobbler.apply_preferences()
        self.wait()
        self.mox.VerifyAll()

    def testSpoolFilesScrobbledOnStartPlusStaleLockFile(self):
        minirok.Globals.preferences.lastfm = MockLastfmPreferences()

        os.mkdir(self._spool)
        lock_file = os.path.join(self._data, 'scrobble.lock')
        prev_lock = ('{"version": "1.1", "pid": 2147483647,'
                     ' "cmdline": "gibberish"}\n')

        with open(lock_file, 'w') as f:
            f.write(prev_lock)

        self.mox.StubOutWithMock(scrobble, 'time')
        scrobble.time.time().AndReturn(100)
        scrobble.time.time().AndReturn(200)
        scrobble.time.time().AndReturn(300)

        self.mox.ReplayAll()

        def create_track(i, fname):
            track = scrobble.Submission({'Title': 't%d' % i,
                                         'Artist': 'a%d' % i,
                                         'Length': 75})

            with open(os.path.join(self._spool, fname), 'w') as f:
                f.write(track.serialize())

        create_track(1, 'a')
        create_track(2, 'c')
        create_track(3, 'b')  # Swap file name sorting order between tracks 2
                              # and 3 to verify scrobble.py sorts them by time.

        # Create a bogus file.
        with open(os.path.join(self._spool, 'x'), 'w') as f:
            f.write('{ "t": "blah", ')

        # Create an incomplete file.
        with open(os.path.join(self._spool, 'y'), 'w') as f:
            f.write('{ "a": "Moo" }')

        # Create an unreadable file.
        z = os.path.join(self._spool, 'z')
        with open(z, 'w') as f:
            f.write("doesn't matter")

        os.chmod(z, 0)

        scrobbler = scrobble.Scrobbler()
        self.assertEqual(3, len(scrobbler.scrobble_queue))
        self.assertTrue(os.path.isfile(lock_file))
        self.assertNotEqual(prev_lock, open(lock_file).read())

        with open(lock_file) as f:
            self.assertTrue(scrobble.ProcInfo.load_from_fileobj(f).isRunning())

        self.mox.UnsetStubs()  # Free scrobble.time.
        self.mox.StubOutClassWithMocks(scrobble, 'HandshakeRequest')

        handshake_request = scrobble.HandshakeRequest(MOCK_HS_URL,
                                                      mox.IgnoreArg())
        handshake_request.failed = False
        handshake_request.body = ['OK',
                                  'your session key',
                                  'your.now_playing.url',
                                  'your.scrobble.url']

        params = {
            's': 'your session key',
            'm[0]': '', 'm[1]': '', 'm[2]': '',
            'r[0]': '', 'r[1]': '', 'r[2]': '',
            'b[0]': '', 'b[1]': '', 'b[2]': '',
            'n[0]': '', 'n[1]': '', 'n[2]': '',
            'o[0]': 'P', 'o[1]': 'P', 'o[2]': 'P',
            'l[0]': '75', 'l[1]': '75', 'l[2]': '75',
            'i[0]': '100', 'i[1]': '200', 'i[2]': '300',
            't[0]': 't1', 't[1]': 't2', 't[2]': 't3',
            'a[0]': 'a1', 'a[1]': 'a2', 'a[2]': 'a3',
        }

        scrobble_request = self.mox.CreateMock(scrobble.Request)
        scrobble_request.failed = False
        self.mox.StubOutWithMock(scrobble, 'Request')

        (scrobble.Request('your.scrobble.url',
                          tests.AssertOk(self.assertDictEqual, params)).
         WithSideEffects(self.stopWaiting).AndReturn(scrobble_request))

        self.mox.ReplayAll()
        scrobbler.start()
        self.wait()
        self.mox.VerifyAll()

    def testWriteTrackToSpool(self):
        scrobbler = scrobble.Scrobbler()
        track = scrobble.Submission({'Title': 't1', 'Artist': 'a1',
                                     'Length': 75})
        base_path = os.path.join(self._spool, str(track.start_time))

        for l in ['', 'a', 'b', 'c']:
            open(os.path.join(base_path + l), 'w').write(l)

        self.assertEqual(base_path + 'd',
                         scrobbler.write_track_to_spool(track))

        self.assertEqual(track.serialize(),
                         open(base_path + 'd').read())

        for l in ['', 'a', 'b', 'c']:
            self.assertEqual(l, open(base_path + l).read())

    def testWriteTrackToSpoolExhausted(self):
        scrobbler = scrobble.Scrobbler()
        track = scrobble.Submission({'Title': 't1', 'Artist': 'a1',
                                     'Length': 75})
        base_path = os.path.join(self._spool, str(track.start_time))

        for l in [''] + list('abcdefghijklmnopqrstuvwxyz'):
            open(base_path + l, 'w').write(l)

        self.assertIsNone(scrobbler.write_track_to_spool(track))

    def testWriteTrackToSpoolOtherIOError(self):
        scrobbler = scrobble.Scrobbler()
        new_spool = os.path.join(self._spool, 'x')
        scrobbler.spool = new_spool
        track = scrobble.Submission({'Title': 't1', 'Artist': 'a1',
                                     'Length': 75})

        os.mkdir(new_spool)
        os.chmod(new_spool, 0)
        try:
            self.assertRaises(OSError, scrobbler.write_track_to_spool, track)
        finally:
            os.rmdir(new_spool)

    def testTimeoutSlotDoesNothingIfNotAlive(self):
        scrobbler = scrobble.Scrobbler()
        self.mox.StubOutWithMock(scrobbler, 'write_track_to_spool')

        self.mox.ReplayAll()
        self.assertFalse(scrobbler.isAlive())
        scrobbler.slot_timer_timeout()
        self.mox.VerifyAll()  # write_track_to_spool() not called.

    def testTimeoutSlotHandlesSpoolFailure(self):
        scrobbler = scrobble.Scrobbler()
        self.mox.StubOutWithMock(scrobbler, 'write_track_to_spool')

        scrobbler.start()
        self.assertTrue(scrobbler.isAlive())

        track = scrobbler.current_track = object()
        scrobbler.write_track_to_spool(track).AndReturn(None)

        self.mox.ReplayAll()
        scrobbler.slot_timer_timeout()
        self.mox.VerifyAll()

##

def save_query(f):
    @functools.wraps(f)
    def wrapper(self, req):
        l = int(req.headers['Content-Length'])
        q = req.rfile.read(l)
        self.queries.append((req.path, q))
        try:
            return f(self, req)
        finally:
            self.newquery.release()
    return wrapper

class ScrobblerLargeTest(tests.BaseTest):

    # TODO: better checks for the body of handshake/now-playing/scrobble
    # queries.

    def setUp(self):
        super(ScrobblerLargeTest, self).setUp()
        self.create_empty_globals()
        self.session_key_counter = 0
        self.queries = []
        self.newquery = threading.Semaphore(0)

    def assertHandshakeOk(self, path, query):
        d = urlparse.parse_qs(query)
        self.assertEqual('/hs', path)
        self.assertEqual('true', d['hs'][0])

    @save_query
    def reply_handshake_ok(self, req):
        self.session_key_counter += 1
        req.send_response(200)
        req.end_headers()
        req.wfile.write(
            '\n'.join(['OK',
                       'session_key_%d' % self.session_key_counter,
                       'http://localhost:%d/np' % req.server.server_port,
                       'http://localhost:%d/submit' % req.server.server_port]))

    @save_query
    def reply_bad_session(self, req):
        req.send_response(200)
        req.end_headers()
        req.wfile.write('BADSESSION')

    @save_query
    def reply_ok(self, req):
        req.send_response(200)
        req.end_headers()
        req.wfile.write('OK')

    @save_query
    def reply_failed(self, req):
        req.send_response(200)
        req.end_headers()
        req.wfile.write('FAILED Transient failure.')

    def no_query_expected(self, req):
        l = int(req.headers['Content-Length'])
        q = req.rfile.read(l)
        self.queries.append(('UNEXPECTED REQUEST TO ' + req.path, q))

    @nose.plugins.attrib.attr(large=True)
    def test(self):
        self.stubs.Set(scrobble, 'TRACK_MIN_LENGTH', 10)

        server = MockHttpServer(post_replies=[self.reply_handshake_ok])
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.setDaemon(True)
        server_thread.start()

        minirok.Globals.preferences.lastfm = MockLastfmPreferences(
            handshake_url='http://localhost:%d/hs' % server.server_port)

        scrobbler = scrobble.Scrobbler()
        scrobbler.start()

        self.newquery.acquire()
        path, query = self.queries.pop(0)
        self.assertHandshakeOk(path, query)

        def new_track(i, l, no_incl_key=None):
            d = {'Title': 't%d' % i, 'Artist': 'a%d' % i, 'Length': l}
            if no_incl_key is not None:
                d.pop(no_incl_key.capitalize())
            minirok.Globals.playlist.currently_playing = (
                playlist.PlaylistItem('/none', d))
            minirok.Globals.playlist.emit(QtCore.SIGNAL('new_track'))

        # We're going to test several error conditions about the tracks
        # themselves (see tracks 3 and 4 below), but we also want to check the
        # logic of failure handling in the scrobbler. For the first and second
        # failures, no action is taken by the scrobbler until the "next event"
        # happen, so we create two tracks right away to increase the failure
        # count to 2.
        server.extend_replies('POST', [self.reply_failed])
        new_track(1, 20)
        self.newquery.acquire()
        self.queries.pop(0)

        server.extend_replies('POST', [self.reply_failed])
        new_track(2, 15)
        self.newquery.acquire()
        self.queries.pop(0)

        server.extend_replies('POST', [self.no_query_expected])
        new_track(3, 5)  # Too short, should not interact with the server.
        new_track(4, 10, no_incl_key='Artist')  # Incomplete metadata.
        self.assertEqual([], self.queries)
        server.drop_front_query('POST')

        # With our next transient failure, failure count reaches 3 and a
        # handshake is performed (and the /np request sent again immediately
        # after that). This second request fails with BADSESSION, which triggers
        # another handshake. Finally, the third /np requests succeeds.
        server.extend_replies('POST', [self.reply_failed,
                                       self.reply_handshake_ok,
                                       self.reply_bad_session,
                                       self.reply_handshake_ok,
                                       self.reply_ok])
        new_track(5, 10)
        self.newquery.acquire()
        self.queries.pop(0)  # First "now playing", let's ignore it.

        self.newquery.acquire()
        self.queries.pop(0)  # First handshake, ditto.

        self.newquery.acquire()
        _, np2 = self.queries.pop(0)

        self.newquery.acquire()
        path, hs2 = self.queries.pop(0)
        self.assertHandshakeOk(path, hs2)

        self.newquery.acquire()
        path, np3 = self.queries.pop(0)

        d2 = urlparse.parse_qs(np2)
        d3 = urlparse.parse_qs(np3)

        self.assertEqual('/np', path)
        self.assertEqual('session_key_2', d2.pop('s')[0])
        self.assertEqual('session_key_3', d3.pop('s')[0])
        self.assertDictEqual(d2, d3)

        # Now we simulate a "player stop" after 5.5 seconds of playing the above
        # track; however, there's been a 2.5 second pause, so the track should
        # *not* be scrobbled.
        #
        # We do our "sleeping" with a QTimer + QEventLoop so that timeouts &
        # signals in the Scrobbler thread continue to work; a time.sleep() would
        # prevent them from being delivered. (N.B.: In the pause/play/stop
        # sleeps, it would be okay because there are no timeouts happen in the
        # scrobbler; however, below we do have timeouts happening in the
        # scrobbler, so we just use the same method every time.)
        timer = QtCore.QTimer()
        timer.setSingleShot(True)
        event_loop = QtCore.QEventLoop()
        event_loop.connect(timer, QtCore.SIGNAL('timeout()'), event_loop.quit)

        server.extend_replies('POST', [self.no_query_expected])

        for delay, status in [(1500, engine.State.PAUSED),
                              (2500, engine.State.PLAYING),
                              (1500, engine.State.STOPPED)]:
            timer.start(delay)
            event_loop.exec_()
            minirok.Globals.engine.emit(
                QtCore.SIGNAL('status_changed'), status)

        time.sleep(0.3)  # XXX
        self.assertEqual([], self.queries)
        server.drop_front_query('POST')

        # Now we let the track play for 5.5 seconds allright. The first
        # "no_query_expected" is because the scrobble should not be submitted
        # when 0.5 * track_time passes, but when the playing *stops*.
        server.extend_replies('POST', [self.reply_ok,
                                       self.no_query_expected])
        new_track(5, 10)

        self.newquery.acquire()
        path, np = self.queries.pop(0)
        self.assertEqual('/np', path)

        timer.start(5500)
        event_loop.exec_()
        self.assertEqual([], self.queries)
        server.drop_front_query('POST')

        # We force stuff a bit here, to test the "3 failures -> handshake" logic
        # *when scrobbling*. We cheat a bit, calling event.set() after the first
        # two failures.
        server.extend_replies('POST', [self.reply_failed,
                                       self.reply_failed,
                                       self.reply_failed,
                                       self.reply_handshake_ok,
                                       self.reply_bad_session,
                                       self.reply_handshake_ok,
                                       self.reply_ok])
        minirok.Globals.engine.emit(
            QtCore.SIGNAL('status_changed'), engine.State.STOPPED)

        for i in range(5):
            self.newquery.acquire()
            self.queries.pop(0)
            if i < 2:
                with scrobbler.mutex:
                    scrobbler.event.set()

        self.newquery.acquire()
        self.queries.pop(0)  # Handshake.

        self.newquery.acquire()
        path, query = self.queries.pop(0)
        self.assertEqual('/submit', path)

##

class MockHttpServer(BaseHTTPServer.HTTPServer):
    """Mock HTTP server, driven by callables handed out in the constructor."""

    def __init__(self, post_replies=None):
        BaseHTTPServer.HTTPServer.__init__(self, ('localhost', 0),
                                           self.RequestHandler)
        self._mock_replies = {
            'POST':  post_replies or [],
        }

    def extend_replies(self, command, extra_replies):
        self._mock_replies[command].extend(extra_replies)

    def drop_front_query(self, command):
        self._mock_replies[command].pop(0)

    class RequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):

        def log_request(code=None, size=None):
            pass

        def generic_handler(self):
            self.server._mock_replies[self.command].pop(0)(self)

        do_POST = generic_handler
