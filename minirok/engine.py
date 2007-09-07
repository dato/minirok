#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007 Adeodato Simó (dato@net.com.org.es)
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

class GStreamerEngine(qt.QObject, threading.Thread):
    SINK = 'alsasink'

    PLUGINS = {
            'flac': [ '.flac' ],
            'mad': [ '.mp3', ],
            'musepack': [ '.mpc', '.mp+', ],
            'vorbis': [ '.ogg' ],
    }

    def __init__(self):
        qt.QObject.__init__(self)
        threading.Thread.__init__(self)
        self.setDaemon(True)

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

        self.time_fmt = gst.Format(gst.FORMAT_TIME)

    def run(self):
        loop = gobject.MainLoop()
        context = loop.get_context()
        while True:
            context.iteration(True)

    ##

    def _set_status(self, value):
        if value != self._status:
            self._status = value
            self.emit(qt.PYSIGNAL('status_changed'), (value,))

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
        """Start playing "path", returning its length in seconds."""
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
            return int(round(self.bin.query_position(self.time_fmt)[0] / 1000000000))
        except gst.QueryError:
            return 0

    ##

    def _message_eos(self, bus, message):
        self.bin.set_state(gst.STATE_NULL)
        self.status = State.STOPPED
        self.emit(qt.PYSIGNAL('end_of_stream'), (self.uri,))

    def _message_error(self, bus, message):
        error, debug_info = message.parse_error()
        minirok.logger.warning('engine error: %s (%s)', error, self.uri)
        self._message_eos(bus, message)

##

Engine = GStreamerEngine
