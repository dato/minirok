#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007-2008 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import os
import time
import threading

import qt
import gst
import gobject

import minirok

gobject.threads_init()

##

class State:
    """This class holds the possible values for engine status."""
    PLAYING = object()
    STOPPED = object()
    PAUSED  = object()

##

class GStreamerEngine(threading.Thread):
    SINK = 'alsasink'

    PLUGINS = {
            'flac': [ '.flac' ],
            'mad': [ '.mp3', ],
            'musepack': [ '.mpc', '.mp+', ],
            'vorbis': [ '.ogg' ],
    }

    class QObject(qt.QObject):
        # The Engine class it's a thread; in Qt3, sending signals accross
        # threads is not supported, so the Engine will send custom events to
        # this class, and this class will emit the signals instead. Other parts
        # of the code will transparently connect() to this interface instead of
        # directly to the Engine object.

        STATUS_CHANGED = qt.QEvent.User + 1
        END_OF_STREAM  = qt.QEvent.User + 2
        SEEK_FINISHED  = qt.QEvent.User + 3

        def customEvent(self, event):
            t = event.type()
            data = event.data()

            if t == self.STATUS_CHANGED:
                self.emit(qt.PYSIGNAL('status_changed'), (data,))

            elif t == self.END_OF_STREAM:
                self.emit(qt.PYSIGNAL('end_of_stream'), (data,))

            elif t == self.SEEK_FINISHED:
                self.emit(qt.PYSIGNAL('seek_finished'), ())

            else:
                minirok.logger.error('unknown custom event: %d', t)

    ##

    def __init__(self):
        threading.Thread.__init__(self)
        self.setDaemon(True)

        self._qobject = self.QObject()
        self.exit_engine = threading.Event() # join() sets this

        self._supported_extensions = []
        for plugin, extensions in self.PLUGINS.items():
            if gst.registry_get_default().find_plugin(plugin) is not None:
                self._supported_extensions.extend(extensions)

        self.uri = None
        self._status = State.STOPPED
        self.bin = gst.element_factory_make('playbin')
        self.bin.set_property('video-sink', None)
        try:
            device = gst.parse_launch(self.SINK)
        except gobject.GError:
            pass
        else:
            self.bin.set_property('audio-sink', device)

        bus = self.bin.get_bus()
        bus.add_signal_watch()
        bus.connect('message::eos', self._message_eos)
        bus.connect('message::error', self._message_error)
        bus.connect('message::async-done', self._message_async_done)

        self.time_fmt = gst.Format(gst.FORMAT_TIME)
        self.seek_pending = False

    def run(self):
        loop = gobject.MainLoop()
        context = loop.get_context()
        while not self.exit_engine.isSet():
            context.iteration(True)

    def join(self, timeout=None):
        """Call Thread.join(), setting self.exit_engine first."""
        self.exit_engine.set()
        threading.Thread.join(self, timeout)

    ##

    def connect(self, signal, slot):
        qt.QObject.connect(self._qobject, signal, slot)

    ##

    def _set_status(self, value):
        if value != self._status:
            self._status = value
            event = qt.QCustomEvent(self.QObject.STATUS_CHANGED)
            event.setData(value)
            qt.QApplication.postEvent(self._qobject, event)

    status = property(lambda self: self._status, _set_status)

    ##

    def can_play(self, path):
        """Return True if the engine can play the given file.

        This is done by looking at the extension of the file.
        """
        prefix, extension = os.path.splitext(path)
        return extension.lower() in self._supported_extensions

    ##

    def play(self, path):
        self.uri = 'file://' + os.path.abspath(path)
        self.bin.set_property('uri', self.uri)
        self.bin.set_state(gst.STATE_NULL)
        self.bin.set_state(gst.STATE_PLAYING)
        self.status = State.PLAYING

    def pause(self, paused=True):
        if paused:
            self.bin.set_state(gst.STATE_PAUSED)
            self.status = State.PAUSED
        else:
            self.bin.set_state(gst.STATE_PLAYING)
            self.status = State.PLAYING

    def stop(self):
        self.bin.set_state(gst.STATE_NULL)
        self.status = State.STOPPED

    def get_position(self):
        """Returns the current position as an int in seconds."""
        try:
            return int(round(self.bin.query_position(self.time_fmt)[0] / gst.SECOND))
        except gst.QueryError:
            return 0

    def set_position(self, seconds):
        """Seek to the given position in the current track.

        This method does not block; "seek_finished" will be emitted
        after the seek has been performed.
        """
        self.seek_pending = True
        self.bin.seek_simple(self.time_fmt, gst.SEEK_FLAG_FLUSH |
                gst.SEEK_FLAG_KEY_UNIT, seconds * gst.SECOND)
        # self.bin.get_state(gst.CLOCK_TIME_NONE) # block until done

    ##

    def _message_eos(self, bus, message):
        self.bin.set_state(gst.STATE_NULL)
        self.status = State.STOPPED
        event = qt.QCustomEvent(self.QObject.END_OF_STREAM)
        event.setData(self.uri)
        qt.QApplication.postEvent(self._qobject, event)

    def _message_error(self, bus, message):
        error, debug_info = message.parse_error()
        minirok.logger.warning('engine error: %s (%s)', error, self.uri)
        self._message_eos(bus, message)

    def _message_async_done(self, bus, message):
        if self.seek_pending:
            self.seek_pending = False
            qt.QApplication.postEvent(self._qobject,
                    qt.QCustomEvent(self.QObject.SEEK_FINISHED))

##

Engine = GStreamerEngine
