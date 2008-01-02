#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import os
import re
import time
import random

import qt
import kdecore

import minirok

##

def kurl_to_path(kurl):
    """Convert a KURL or QString to a str in the local filesystem encoding.

    For KURLs, the leading file:// prefix will be stripped if present.
    """
    if isinstance(kurl, kdecore.KURL):
        kurl = kurl.pathOrURL()

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

    for path in [ str(kdecore.locate('appdata', os.path.join('images', name))),
            os.path.join(os.path.dirname(__file__), '..', 'images', name) ]:
        if os.path.exists(path):
            break

    return _png_cache.setdefault(name, qt.QPixmap(path, 'PNG'))

_png_cache = {}

##

class HasConfig(object):
    """A class that connects its slot_save_config to kApp.shutDown()"""

    def __init__(self):
        qt.QObject.connect(kdecore.KApplication.kApplication(),
                qt.SIGNAL('shutDown()'), self.slot_save_config)

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

class QTimerWithPause(qt.QTimer):
    """A QTimer with pause() and resume() methods.

    Idea taken from:
        http://www.riverbankcomputing.com/pipermail/pyqt/2004-July/008325.html

    Note that, unlike in QTimer, the single_shot argument of start() defaults
    to True.
    """
    def __init__(self, *args):
        qt.QTimer.__init__(self, *args)
        self.duration = 0
        self.finished = True
        self.recur_time = None
        self.start_time = 0

        self.connect(self, qt.SIGNAL('timeout()'), self.slot_timer_finished)

    def start(self, msecs, single_shot=True):
        if not single_shot:
            self.recur_time = msecs
        else:
            self.recur_time = None
        self._start(msecs)

    def pause(self):
        if self.isActive():
            self.stop()
            elapsed = time.time() - self.start_time
            self.start_time -= elapsed
            self.duration -= int(elapsed*1000)

    def resume(self):
        if not self.finished and not self.isActive():
            self._start(self.duration)

    ##

    def _start(self, msecs):
        self.finished = False
        self.duration = msecs
        self.start_time = time.time()
        # We always start ourselves in single-shot mode, and restart if
        # necessary in slot_timer_finished()
        qt.QTimer.start(self, msecs, True)

    def slot_timer_finished(self):
        if self.recur_time is not None:
            self._start(self.recur_time)
        else:
            # This prevents resume() on a finished timer from restarting it
            self.finished = True

##

class RandomOrderedList(list):
    """A list where append() inserts items at a random position."""

    def append(self, item):
        self.insert(random.randrange(len(self)+1), item)

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

class ThreadedWorker(qt.QThread):
    """A thread that performs a given action on items in a queue.
    
    The thread consumes items from a queue, and stores pairs (item, result)
    in a "done" queue. Whenever there are done items, the thread fires off a
    QTimer, received in the constructor.
    """
    # XXX More generic would be to accept a callback function instead of a timer.
    def __init__(self, function, timer=None):
        """Create a worker.

        :param function: The function to invoke on each item.

        :param timer: The QTimer object to start to start whenever there are
            done items. The timer will always be started with 0ms, and in
            single-shot mode.
        """
        qt.QThread.__init__(self)

        self._done = []
        self._queue = []
        self._mutex = qt.QMutex() # for _queue
        self._mutex2 = qt.QMutex() # for _done
        self._pending = qt.QWaitCondition()

        self.timer = timer
        self.function = function

    ##

    @needs_lock('_mutex')
    def queue(self, item):
        self._queue.append(item)
        self._pending.wakeAll()

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
                try:
                    # We just don't pop() the item here, because after calling
                    # self.function(), we'll want to check that the item is still
                    # in the queue (that is, that the queue was not cleared in the
                    # meantime).
                    item = self._queue[0]
                finally:
                    self._mutex.unlock()
            except IndexError:
                self._pending.wait()
                continue

            result = self.function(item)

            self._mutex.lock()
            try:
                if item in self._queue:
                    self._queue.remove(item)
                else:
                    continue
            finally:
                self._mutex.unlock()

            self._mutex2.lock()
            try:
                self._done.append((item, result))
            finally:
                self._mutex2.unlock()

            if self.timer is not None:
                self.timer.start(0, True) # True: single-shot
