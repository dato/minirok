#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007-2008 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import os
import re
import stat
import time
import random

from PyQt4 import QtGui, QtCore
from PyKDE4 import kdeui, kdecore

import minirok

##

def kurl_to_path(kurl):
    """Convert a KURL or QString to a str in the local filesystem encoding.

    For KURLs, the leading file:// prefix will be stripped if present.
    """
    if isinstance(kurl, kdecore.KUrl):
        kurl = kurl.pathOrUrl()

    return unicode(kurl).encode(minirok.filesystem_encoding)

def unicode_from_path(path):
    """Convert from the filesystem encoding to unicode."""
    if isinstance(path, unicode):
        return path
    else:
        try:
            return unicode(path, minirok.filesystem_encoding)
        except UnicodeDecodeError:
            minirok.logger.warning('cannot convert %r to %s', path,
                    minirok.filesystem_encoding)
            return unicode(path, minirok.filesystem_encoding, 'replace')

def fmt_seconds(seconds):
    """Convert a number of seconds to m:ss or h:mm:ss notation."""
    try:
        seconds = int(seconds)
    except ValueError:
        minirok.logger.warn('invalid int passed to fmt_seconds(): %r', seconds)
        return seconds

    if seconds < 3600:
        return '%d:%02d' % (seconds//60, seconds%60)
    else:
        return '%d:%02d:%02d' % (seconds//3600, (seconds%3600)//60, seconds%60)

def get_png(name):
    """Return a QPixmap of the named PNG file under $APPDATA/images.

    If it does not exist in $APPDATA/images, it will be assumed Minirok is
    running from source, and it'll be searched in `dirname __file__`/../images.

    Pixmaps are cached.
    """
    if not re.search(r'\.png$', name):
        name += '.png'

    try:
        return _png_cache[name]
    except KeyError:
        pass

    for path in [ str(kdecore.KStandardDirs.locate('appdata', os.path.join('images', name))),
            os.path.join(os.path.dirname(__file__), '..', 'images', name) ]:
        if os.path.exists(path):
            break
    else:
        minirok.logger.warn('could not find %s', name)

    return _png_cache.setdefault(name, QtGui.QPixmap(path, 'PNG'))

_png_cache = {}

def create_action(name, text, slot, icon=None, shortcut=None,
                        global_shortcut=None, factory=kdeui.KAction):
    """Helper to create KAction objects."""
    action = factory(None)
    action.setText(text)

    QtCore.QObject.connect(action, QtCore.SIGNAL('triggered(bool)'), slot)
    minirok.Globals.action_collection.addAction(name, action)

    if icon is not None:
        action.setIcon(kdeui.KIcon(icon))

    if shortcut is not None:
        action.setShortcut(kdeui.KShortcut(shortcut),
                # XXX-KDE4 ../pykde4-bugs/01_kaction_setShortcut_requires_two_arguments.py
                kdeui.KAction.ShortcutType(kdeui.KAction.ActiveShortcut | kdeui.KAction.DefaultShortcut))

    if global_shortcut is not None:
        action.setGlobalShortcut(kdeui.KShortcut(global_shortcut),
                # XXX-KDE4 here too
                kdeui.KAction.ShortcutType(kdeui.KAction.ActiveShortcut | kdeui.KAction.DefaultShortcut))

    return action

def playable_from_untrusted(files, warn=False):
    """Filter a list of untrusted paths to only include playable files.

    This method takes a list of paths, and drops from it files that do not
    exist or the engine can't play. Directories will be read and all its files
    included as appropriate.

    :param warn: If True, emit a warning for each skipped file, stating the
            reason; if False, debug() statements will be emitted instead.
    """
    result = []

    if warn:
        warn = minirok.logger.warn
    else:
        warn = minirok.logger.debug

    def append_path(path):
        try:
            mode = os.stat(path).st_mode
        except OSError, e:
            warn('skipping %r: %s', path, e.strerror)
            return

        if stat.S_ISDIR(mode):
            try:
                contents = sorted(os.listdir(path))
            except OSError, e:
                warn('skipping %r: %s', path, e.strerror)
            else:
                for entry in contents:
                    append_path(os.path.join(path, entry))
        elif stat.S_ISREG(mode):
            if minirok.Globals.engine.can_play_path(path):
                if path not in result:
                    result.append(path)
            else:
                warn('skipping %r: not a playable format', path)
        else:
            warn('skipping %r: not a regular file', path)

    for f in files:
        append_path(f)

    return result

##

class HasConfig(object):
    """A class that connects its slot_save_config to kApp.aboutToQuit()."""

    def __init__(self):
        QtCore.QObject.connect(kdeui.KApplication.kApplication(),
                QtCore.SIGNAL('aboutToQuit()'), self.slot_save_config)

    def slot_save_config(self):
        raise NotImplementedError, \
            "slot_save_config must be reimplemented in %s" % self.__class__

##

class HasGUIConfig(object):
    """Class to keep track of objects that should re-read its config after
       changes in the preferences dialog. Their apply_preferences() method
       is called.
    """

    OBJECTS = []

    def __init__(self):
        self.OBJECTS.append(self)

    @staticmethod
    def settings_changed():
        for object_ in HasGUIConfig.OBJECTS:
            object_.apply_preferences()

##

class QTimerWithPause(QtCore.QObject):
    """A QTimer with pause() and resume() methods.

    Note that we don't inherit from QTimer, and we just offer a limited
    interface: start(msecs), stop(), pause(), resume(), and setSingleShot().
    The timeout() signal is emitted as normal.
    """
    def __init__(self, *args):
        QtCore.QObject.__init__(self, *args)

        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self.connect(self._timer, QtCore.SIGNAL('timeout()'), self._slot_timeout)

        self._running = False
        self._duration = None # duration as given to start()
        self._remaining = None # what's pending, considering pauses()
        self._start_time = None # time we last _started()
        self._single_shot = False

    ##

    def start(self, msecs):
        self._duration = self._remaining = msecs
        self._start()

    def stop(self):
        self._remaining = self._duration
        self._timer.stop()

    def pause(self):
        if self._timer.isActive():
            self._timer.stop()
            elapsed = time.time() - self._start_time
            self._remaining -= int(elapsed*1000)

    def resume(self):
        if (self._running
                and not self._timer.isActive()):
            self._start()

    def setSingleShot(self, value):
        self._single_shot = bool(value)

    ##

    def _start(self):
        self._running = True
        self._start_time = time.time()
        self._timer.start(self._remaining)

    def _slot_timeout(self):
        self._running = False
        self._remaining = self._duration
        self.emit(QtCore.SIGNAL('timeout()'))

        if not self._single_shot:
            self._start()

##

class RandomOrderedList(list):
    """A list where append() inserts items at a random position."""

    def append(self, item):
        self.insert(random.randrange(len(self)+1), item)

    def extend(self, seq):
        # FIXME Uuuh, yeah, this implementation is buggy (because items coming
        # via extend() are not mixed with the already existing items...)
        seq = list(seq)
        random.shuffle(seq)
        list.extend(self, seq)

##

def needs_lock(mutex_name):
    """Helper decorator for ThreadedWorker."""
    def decorator(function):
        def wrapper(self, *args):
            mutex = getattr(self, mutex_name)
            mutex.lock()
            try:
                return function(self, *args)
            finally:
                mutex.unlock()
        return wrapper
    return decorator

##

class ThreadedWorker(QtCore.QThread):
    """A thread that performs a given action on items in a queue.

    The thread consumes items from a queue, and stores pairs (item, result)
    in a "done" queue. Whenever there are done items, the thread emits a
    "items_ready" signal.
    """
    def __init__(self, function, timer=None):
        """Create a worker.

        :param function: The function to invoke on each item.
        """
        QtCore.QThread.__init__(self)

        self._done = []
        self._queue = []
        self._mutex = QtCore.QMutex() # for _queue
        self._mutex2 = QtCore.QMutex() # for _done
        self._pending = QtCore.QWaitCondition()

        self.function = function

    ##

    @needs_lock('_mutex')
    def queue(self, item):
        self._queue.append(item)
        self._pending.wakeAll()

    @needs_lock('_mutex')
    def queue_many(self, items):
        self._queue.extend(items)
        if len(self._queue) > 0:
            self._pending.wakeAll()

    @needs_lock('_mutex')
    @needs_lock('_mutex2')
    def is_empty(self):
        """Returns True if both queues are empty."""
        return len(self._queue) == 0 and len(self._done) == 0

    @needs_lock('_mutex')
    def dequeue(self, item):
        try:
            self._queue.remove(item)
        except ValueError:
            pass

    @needs_lock('_mutex')
    @needs_lock('_mutex2')
    def clear_queue(self):
        self._done[:] = []
        self._queue[:] = []

    @needs_lock('_mutex2')
    def pop_done(self):
        done = self._done[:]
        self._done[:] = []
        return done

    ##

    def run(self):
        while True:
            self._mutex.lock()
            try:
                while True:
                    try:
                        # We just don't pop() the item here, because after
                        # calling self.function(), we'll want to check that the
                        # item is still in the queue (that is, that the queue
                        # was not cleared in the meantime).
                        item = self._queue[0]
                    except IndexError:
                        self._pending.wait(self._mutex) # unlocks and re-locks
                    else:
                        break
            finally:
                self._mutex.unlock()

            result = self.function(item)

            self._mutex.lock()
            try:
                try:
                    self._queue.remove(item)
                except ValueError:
                    continue
            finally:
                self._mutex.unlock()

            self._mutex2.lock()
            try:
                self._done.append((item, result))
            finally:
                self._mutex2.unlock()

            self.emit(QtCore.SIGNAL('items_ready'))

##

class SearchLineWithReturnKey(kdeui.KTreeWidgetSearchLine):
    """A search line that doesn't forward Return key to its QTreeWidget."""

    def event(self, event):
        # Do not let KTreeWidgetSearchLine eat our return key
        if (event.type() == QtCore.QEvent.KeyPress
                and (event.key() == QtCore.Qt.Key_Enter
                    or event.key() == QtCore.Qt.Key_Return)):
            return kdeui.KLineEdit.event(self, event)
        else:
            return kdeui.KTreeWidgetSearchLine.event(self, event)

##

class DelayedLineEdit(kdeui.KLineEdit):
    """Emits a text changed signal once the user is done writing.

    This class emits a "delayed_text_changed" signal once some time
    has passed since the last key press from the user.
    """

    DELAY = 300 # ms
    SIGNAL = QtCore.SIGNAL('delayed_text_changed')

    def __init__(self, parent=None):
        kdeui.KLineEdit.__init__(self, parent)
        self._queued_signals = 0
        self.setClearButtonShown(True)

        self.connect(self, QtCore.SIGNAL('textChanged(const QString &)'),
                self._queue_signal)

    def _queue_signal(self, text):
        self._queued_signals += 1
        QtCore.QTimer.singleShot(self.DELAY, self._emit_signal)

    def _emit_signal(self):
        if self._queued_signals > 1:
            self._queued_signals -= 1
        else:
            self._queued_signals = 0
            self.emit(self.SIGNAL, QtCore.QString(self.text()))
