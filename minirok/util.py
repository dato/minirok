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
        return '%d:%02d' % (seconds/60, seconds%60)
    else:
        return '%d:%02d:%02d' % (seconds/3600, (seconds%3600)/60, seconds%60)

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
