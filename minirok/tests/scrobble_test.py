#! /usr/bin/env python
## Hey, Python: encoding=utf-8
#
# Copyright (c) 2010, 2011 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import errno
import itertools
import os
import StringIO
import subprocess
import time

from minirok import (
    scrobble,
    tests,
)

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
