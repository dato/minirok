#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import qt
import minirok

##

class TagReader(qt.QObject):
    """Reads tags from files in a pending queue."""

    def __init__(self):
        qt.QObject.__init__(self)

        self.timer = qt.QTimer(self, 'tag reader timer')
        self.connect(self.timer, qt.SIGNAL('timeout()'), self.update_one)

        self._queue = []

    ##

    def queue(self, item):
        self._queue.append(item)
        if len(self._queue) == 1:
            self.timer.start(0, False) # False: not one-shot

    def dequeue(self, item):
        try:
            self._queue.remove(item)
        except ValueError:
            pass

        if len(self._queue) == 0:
            self.timer.stop()

    def clear_queue(self):
        self._queue[:] = []
        self.timer.stop()

    ##

    def update_one(self):
        item = self._queue.pop(0)
        if len(self._queue) == 0:
            self.timer.stop()
        # do something with item
