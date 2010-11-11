#! /usr/bin/env python
## Hey, Python: encoding=utf-8
#
# Copyright (c) 2010 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import itertools
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
