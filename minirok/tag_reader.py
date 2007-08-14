#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import threading
import minirok

##

class TagReader(threading.Thread):
    """Reads tags from files in a pending queue."""

    def __init__(self):
        threading.Thread.__init__(self)
        self.setDaemon(True)

        self._queue = []
        self._lock = threading.Lock()
        self._pending = threading.Event()
        self._locked = False

    ##

    def lock(self):
        self._pending.clear() # prevents stagnation
        self._lock.acquire()
        self._locked = True

    def unlock(self):
        self._lock.release()
        self._pending.set()
        self._locked = False

    def queue(self, item):
        assert self._locked
        self._queue.insert(0, item)

    def queue_empty(self):
        return len(self._queue) == 0

    def dequeue(self, item):
        assert self._locked
        try:
            self._queue.remove(item)
        except ValueError:
            pass

    def clear_queue(self):
        assert self._locked
        self._queue[:] = []

    ##

    def run(self):
        while True:
            self._pending.wait()
            if len(self._queue) == 0:
                self._pending.clear()
                continue
            self._lock.acquire()
            try:
                item = self._queue.pop()
                # TODO do something with item
            except Exception, e:
                minirok.logger.error('unexpected exception: %s', e)
                self._lock.release()
                continue
            self._lock.release()
