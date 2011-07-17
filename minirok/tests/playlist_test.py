#! /usr/bin/env python
## Hey, Python: encoding=utf-8
#
# Copyright (c) 2011 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import minirok

import contextlib
import errno
import os
import shutil
import sys
import tempfile
import threading

from PyQt4 import QtCore, QtTest

import mox

from minirok import (
    engine,
    playlist,
    preferences,
    tests,
    util,
)

Qt = QtCore.Qt
QTest = QtTest.QTest

##

class MockEngine(QtCore.QObject):

  PLAY_CALLED = 'PLAY_CALLED'
  STOP_CALLED = 'STOP_CALLED'
  PAUSE_CALLED = 'PAUSE_CALLED'

  def __init__(self, vrfy_callback):
    QtCore.QObject.__init__(self)
    self._status = engine.State.STOPPED

    # Rather than use a "record/replay/verify" model, this mock object verifies
    # each call it receives via a callback. This allows the tests to check that
    # each UI action maps to exactly the expected calls in the engine, and not
    # more. See below for a longer explanation.
    self.__vrfy_callback = vrfy_callback

  @property
  def status(self):
    return self._status

  @status.setter
  def status(self, value):
    if value != self._status:
      self._status = value
      self.emit(QtCore.SIGNAL('status_changed'), value)

  def play(self, path):
    self.status = engine.State.PLAYING
    self.__vrfy_callback((self.PLAY_CALLED, path))

  def pause(self, do_pause):
    self.status = (engine.State.PAUSED if do_pause
                   else engine.State.PLAYING)
    self.__vrfy_callback((self.PAUSE_CALLED, do_pause))

  def stop(self):
    self.status = engine.State.STOPPED
    self.__vrfy_callback((self.STOP_CALLED,))

  def can_play_path(self, path):
    return path.lower().endswith('.mp3')

##

class PlaylistUiTest(tests.BaseTest):
  """Tests for playlist that use the UI.

  Explanation of how the custom mocking system works
  ==================================================

  Each action is wrapped in a "with" block stating what is expected:

    with self.expect((MockEngine.PLAY_CALLED, self.files[0])):
      ac['action_play'].trigger()

  This works by:

    1. adding to self.engine_calls the expected call (or calls)
    2. executing the code block
    3. a call to the mock engine will be performed, which ultimately results in
       a call to the "verify_engine_call" method (that method is the mock's
       verify callback, see the mock definition for details)
    4. verify_engine_call checks that the expected call was performed

  One important factor is that (4) actually doesn't *verify* it with assert
  methods, but rather just indicates what should be checked. This is because
  that method runs in the Qt thread and not in the tests thread--failed asserts
  there would not result in a test suite failure (since the raised exceptions
  would be in another thread, the test suite runner cannot notice them). The set
  of checks/asserts to run is communicated via self.assert_calls.
  """

  def setUp(self):
    super(PlaylistUiTest, self).setUp()

    tests.BaseTest.create_qapp()

    self.engine_calls = []
    self.assert_calls = []
    self.lock = threading.Lock()
    self.semaphore = threading.Semaphore(0)

    self.engine = MockEngine(self.verify_engine_call)

    minirok.Globals.engine = self.engine
    minirok.Globals.preferences = preferences.Preferences()
    minirok.Globals.action_collection = tests.MockActionCollection()

    self.model = playlist.Playlist()
    self.view = playlist.PlaylistView()
    self.view.setModel(self.model)

    self.model.selection_model = (
        self.view.selectionModel())  # XXX See right_side.py.

    # TODO(dato): do not use an absolute path here.
    self.files = ['/home/dato/soft/minirok/minirok/tests/data/%s.mp3' % x
                  for x in ('car', 'churchwalking', 'storm', 'shower')]

    self.playlist_file = os.path.join(os.environ['KDEHOME'],
                                      'share/apps/minirok/saved_playlist.txt')

  def tearDown(self):
    super(PlaylistUiTest, self).tearDown()
    self.view.hide()

    try:
      os.unlink(self.playlist_file)
    except OSError, e:
      if e.errno != errno.ENOENT:
        raise

    with self.lock:
      # Nothing should be left in the "expected" state:
      self.assertEqual(0, len(self.engine_calls))
      # This will typically be empty, except if some unexpected calls to the
      # engine were performed, in which case it could contain a "self.fail".
      for call in self.assert_calls:
        call()

  """Verify/expect machinery."""

  def verify_engine_call(self, actual):
    try:
      with self.lock:
        expected = self.engine_calls.pop(0)
    except IndexError:
      call = lambda: self.fail('unexpected event in engine: %s' % (actual,))
    else:
      call = lambda: self.assertEqual(expected, actual)
    finally:
      with self.lock:
        self.assert_calls.append(call)
      self.semaphore.release()

  @contextlib.contextmanager
  def expect(self, *expected_calls):
    with self.lock:
      self.engine_calls.extend(expected_calls)

    yield

    # The ability of not blocking is needed for blocks that expect no calls.
    # There's the race-condition-du-jour here (we would proceed before that
    # unexpected call has been performed), but tearDown() has last-minute code
    # for that.
    self.semaphore.acquire(blocking=bool(expected_calls))

    with self.lock:
      self.assertEqual(0, len(self.engine_calls))
      assert_calls = self.assert_calls[:]
      self.assert_calls[:] = []

    for call in assert_calls:
      call()

  def click(self, row, button=Qt.LeftButton, modifier=Qt.NoModifier):
      QTest.mouseClick(self.view.viewport(), button, modifier,
                       self.view.visualRect(self.model.index(row, 0)).center())

  def end_of_stream(self):
    self.engine.status = engine.State.STOPPED
    self.engine.emit(QtCore.SIGNAL('end_of_stream'))

  def testSimplePlaylistActions(self):
    ac = minirok.Globals.action_collection
    self.model.add_files(self.files)

    # Start playing (must play track 0).
    with self.expect((MockEngine.PLAY_CALLED, self.files[0])):
      ac['action_play_pause'].trigger()

    # Normal end of stream: track 1 follows.
    with self.expect((MockEngine.PLAY_CALLED, self.files[1])):
      self.end_of_stream()

    # Trying out pause.
    with self.expect((MockEngine.PAUSE_CALLED, True)):
      ac['action_pause'].trigger()

    with self.expect((MockEngine.PAUSE_CALLED, False)):
      ac['action_play_pause'].trigger()

    # Continue playing with track 2.
    with self.expect((MockEngine.PLAY_CALLED, self.files[2])):
      self.end_of_stream()

    # Trying "next" action.
    with self.expect((MockEngine.PLAY_CALLED, self.files[3])):
      ac['action_next'].trigger()

    # "Previous" action whilst playing (must continue playing).
    with self.expect((MockEngine.PLAY_CALLED, self.files[2])):
      ac['action_previous'].trigger()

    # "Stop".
    with self.expect((MockEngine.STOP_CALLED,)):
      ac['action_stop'].trigger()

    # "Previous" while stopped: doesn't play (i.e., no expected calls).
    with self.expect():
      ac['action_previous'].trigger()

    # And, finally, "clear playlist".
    self.assertNotEqual(0, len(self.model._itemlist))
    ac['action_clear_playlist'].trigger()
    self.assertEqual(0, len(self.model._itemlist))

  def testSpecialPlaylistActionsWithClicks(self):
    ac = minirok.Globals.action_collection
    self.model.add_files(self.files)

    # Start playing track 2.
    with self.expect((MockEngine.PLAY_CALLED, self.files[2])):
      self.click(2)

    # Enqueue tracks 3 and 1; change to playing track 0.
    with self.expect((MockEngine.PLAY_CALLED, self.files[0])):
      self.click(3, Qt.RightButton, Qt.ControlModifier)
      self.click(1, Qt.RightButton, Qt.ControlModifier)
      self.click(0)

    # Now track 3 should play.
    with self.expect((MockEngine.PLAY_CALLED, self.files[3])):
      self.end_of_stream()

    # Exercise "stop after this track".
    with self.expect():
      self.click(1, Qt.MidButton, Qt.ControlModifier)  # Track 1 on.
      self.click(1, Qt.MidButton, Qt.ControlModifier)  # Track 1 off.
      self.click(3, Qt.MidButton, Qt.ControlModifier)  # Track 3 on.
      self.click(2, Qt.MidButton, Qt.ControlModifier)  # Track 2 on, 3 off.

    # Track 1 should play.
    with self.expect((MockEngine.PLAY_CALLED, self.files[1])):
      self.end_of_stream()

    # After track 1, track 2 should play.
    with self.expect((MockEngine.PLAY_CALLED, self.files[2])):
      self.end_of_stream()

    # Nothing else should be played because track 2 is "stop after this track".
    with self.expect():
      self.end_of_stream()

    # But current item should be track 3.
    with self.expect((MockEngine.PLAY_CALLED, self.files[3])):
      ac['action_play'].trigger()
      self.end_of_stream()

  def testRandomMode(self):
    self.stubs.Set(util.random, 'shuffle', lambda x: x.reverse())  # :)

    ac = minirok.Globals.action_collection
    self.files = ['/nonexistent/%s.mp3' % x for x in range(6)]
    self.model.add_files(self.files)

    with self.expect((MockEngine.PLAY_CALLED, self.files[5])):
      self.model.random_mode = True
      ac['action_play'].trigger()

    self.click(1, Qt.RightButton, Qt.ControlModifier)
    self.click(3, Qt.RightButton, Qt.ControlModifier)

    for i in [1, 3, 4, 2, 0]:
      with self.expect((MockEngine.PLAY_CALLED, self.files[i])):
        self.end_of_stream()

    with self.expect():
      self.end_of_stream()

  def testRepeatMode(self):
    ac = minirok.Globals.action_collection
    self.model.add_files(self.files[0:2])

    with self.expect((MockEngine.PLAY_CALLED, self.files[0])):
      ac['action_play'].trigger()

    self.model.repeat_mode = playlist.RepeatMode.TRACK

    with self.expect((MockEngine.PLAY_CALLED, self.files[0])):
      self.end_of_stream()

    self.model.repeat_mode = playlist.RepeatMode.PLAYLIST

    with self.expect((MockEngine.PLAY_CALLED, self.files[1]),
                     (MockEngine.PLAY_CALLED, self.files[0]),
                     (MockEngine.PLAY_CALLED, self.files[1])):
      self.end_of_stream()
      self.end_of_stream()
      self.end_of_stream()

    self.model.repeat_mode = playlist.RepeatMode.NONE

    with self.expect():
      self.end_of_stream()

  def testRemovalAndUndoPreservesQueueAndStopAfter(self):
    ac = minirok.Globals.action_collection
    self.files = ['/nonexistent/%s.mp3' % x for x in range(8)]
    self.model.add_files(self.files)

    # Play/stop the third item so that it becomes the "current" item and we can
    # verify that property gets preserved on Undo.
    with self.expect((MockEngine.PLAY_CALLED, self.files[2]),
                     (MockEngine.STOP_CALLED,)):
      self.click(2)
      ac['action_stop'].trigger()

    with self.expect():
      self.click(5, Qt.RightButton, Qt.ControlModifier)
      self.click(4, Qt.RightButton, Qt.ControlModifier)
      self.click(3, Qt.MidButton, Qt.ControlModifier)

    _queue = self.model.queue[:]
    _all_items = self.model._itemlist[:]
    _stop_after = self.model._stop_after
    _current_item = self.model._current_item

    self.assertEqual(self.files[2], _current_item.path)
    self.assertEqual(self.files[3], _stop_after.path)
    self.assertEqual(self.files, [item.path for item in _all_items])
    self.assertEqual(self.files[5:3:-1], [item.path for item in _queue])

    with self.expect():
      QTest.keyPress(self.view.viewport(), Qt.Key_Down, Qt.ShiftModifier)
      QTest.keyPress(self.view.viewport(), Qt.Key_Down, Qt.ShiftModifier)
      QTest.keyPress(self.view.viewport(), Qt.Key_Down, Qt.ShiftModifier)
      QTest.keyPress(self.view.viewport(), Qt.Key_Delete)

    # TODO(dato): not sure why _stop_after is not None here.
    self.assertEqual(self.model.FIRST_ITEM, self.model._current_item)
    self.assertEqual(0, len(self.model.queue))
    self.assertEqual(self.files[0:2] + self.files[6:8],
                     [item.path for item in self.model._itemlist])

    with self.expect():
      ac['action_playlist_undo'].trigger()

    self.assertEqual(_queue, self.model.queue)
    self.assertEqual(_all_items, self.model._itemlist)
    self.assertEqual(_stop_after, self.model._stop_after)
    self.assertEqual(_current_item, self.model._current_item)

  def testActionPlayStartsWithQueueIfPresent(self):
    ac = minirok.Globals.action_collection
    self.model.add_files(self.files)

    # Enqueue track 3: it should play first.
    with self.expect((MockEngine.PLAY_CALLED, self.files[3])):
      self.click(3, Qt.RightButton, Qt.ControlModifier)
      ac['action_play'].trigger()
      self.end_of_stream()

  def testMiddleButtonWithoutModifiersPauses(self):
    ac = minirok.Globals.action_collection
    self.model.add_files(self.files)

    with self.expect((MockEngine.PLAY_CALLED, self.files[0])):
      ac['action_play'].trigger()

    with self.expect((MockEngine.PAUSE_CALLED, True)):
      self.click(0, Qt.MidButton)

  def testAddItemsDetectsCurrentlyPlayingPath(self):
    ac = minirok.Globals.action_collection
    self.model.add_files(self.files[0:1])

    with self.expect((MockEngine.PLAY_CALLED, self.files[0])):
      ac['action_play'].trigger()
      ac['action_clear_playlist'].trigger()

    self.model.add_files([self.files[i] for i in (1, 0, 2, 0, 3)])

    # The *first* item whose path matched should be the current item (hence,
    # track 2 is next, and not 3, as per above).
    with self.expect((MockEngine.PLAY_CALLED, self.files[2])):
      self.end_of_stream()

  def testActionStopPlayingAfterCurrent(self):
    ac = minirok.Globals.action_collection
    self.model.add_files(self.files)

    with self.expect((MockEngine.PLAY_CALLED, self.files[0])):
      ac['action_play'].trigger()
      ac['action_toggle_stop_after_current'].trigger()
      self.end_of_stream()

  def testClearAndAddFilesContinuesWithFirstNewFile(self):
    ac = minirok.Globals.action_collection
    self.model.add_files(self.files[0:1])

    with self.expect((MockEngine.PLAY_CALLED, self.files[0])):
      ac['action_play'].trigger()
      ac['action_clear_playlist'].trigger()

    self.model.add_files(self.files[1:])

    with self.expect((MockEngine.PLAY_CALLED, self.files[1])):
      self.end_of_stream()

  def testSavePlaylistToFile(self):
    self.model.add_files(['/a.mp3', '/b.mp3', '/c\nd.mp3'])
    self.model.save_config()

    with open(self.playlist_file) as f:
      self.assertEqual('/a.mp3\0/b.mp3\0/c\nd.mp3', f.read())

  def testLoadPlaylistFromFile(self):
    tmpdir = tempfile.mkdtemp(prefix='minirok_test.')
    files = [os.path.join(tmpdir, x) for x in ('moo.mp3', 'xxx', 'baz\nx.mp3')]

    for x in files:
      open(x, 'w').close()

    with open(self.playlist_file, 'w') as f:
      f.write('\0'.join(files))

    self.model.load_saved_playlist()
    self.assertEqual(2, len(self.model._itemlist))
    self.assertEqual('moo.mp3', os.path.basename(self.model._itemlist[0].path))
    self.assertEqual('baz\nx.mp3',
                     os.path.basename(self.model._itemlist[1].path))

    shutil.rmtree(tmpdir)

  def testEmptySavedPlaylist(self):
    open(self.playlist_file, 'w').close()
    self.model.load_saved_playlist()
    self.assertEqual(0, len(self.model._itemlist))

  def testTagsReadCorrectly(self):
    self.model.add_files(self.files[0:1])

    while self.model._itemlist[0].needs_tag_reader:
      QTest.qWait(50)

    tags = self.model._itemlist[0].tags()
    self.assertEqual('Car', tags['Title'])
    self.assertEqual('Mercedes A', tags['Artist'])

  def testTagRegexModeNeverReadTags(self):
    p = minirok.Globals.preferences
    p._tags_from_regex.setValue(True)
    p._tag_regex_mode.setValue(2)
    p._tag_regex.setValue(r'.*/(?P<artist>.*) - (?P<title>.+)\.mp3$')

    tmpdir = tempfile.mkdtemp(prefix='minirok_test.')
    my_files = [os.path.join(tmpdir, x)
                for x in ('John Doe - Random Song.mp3',
                          'Regex Fails Song.mp3',
                          ' - Empty Artist Song.mp3')]

    for i, path in enumerate(my_files):
      os.symlink(self.files[i], path)

    self.model.apply_preferences()
    self.model.add_files(my_files)
    my_tags = [item.tags() for item in self.model._itemlist]

    self.assertEqual('John Doe', my_tags[0]['Artist'])
    self.assertEqual('Random Song', my_tags[0]['Title'])
    self.assertEqual('Regex Fails Song.mp3', my_tags[1]['Title'])
    self.assertEqual('', my_tags[2]['Artist'])
    self.assertEqual('Empty Artist Song', my_tags[2]['Title'])

  def testBogusRegexForTags(self):
    p = minirok.Globals.preferences
    p._tags_from_regex.setValue(True)
    p._tag_regex_mode.setValue(2)
    p._tag_regex.setValue(r'.*/(.+')

    self.mox.StubOutWithMock(minirok.logger, 'error')
    minirok.logger.error(
        mox.Func(lambda x: x.startswith('invalid regular expression')),
        mox.IgnoreArg(), mox.IgnoreArg())

    self.mox.ReplayAll()
    self.model.apply_preferences()
    self.mox.VerifyAll()
