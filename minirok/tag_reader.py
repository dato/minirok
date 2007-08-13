#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import sys
import threading

##

class TagReader(threading.Thread):
    """Reads tags from files in a pending queue."""

    def __init__(self):
        threading.Thread.__init__(self)
        self.setDaemon(True)

        self._queue = []
        self._lock = threading.Lock()
        self._pending = threading.Event()

    ##

    def lock(self):
        self._pending.clear() # prevents stagnation
        self._lock.acquire()

    def unlock(self):
        self._lock.release()
        self._pending.set()

    def queue(self, item):
        self._queue.insert(0, item)

    def queue_empty(self):
        return len(self._queue) == 0

    def dequeue(self, item):
        try:
            self._queue.remove(item)
        except ValueError:
            pass

    def clear_queue(self):
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
                print >>sys.stderr, 'minirok: error: TagReader thread: %s' % e
                self._lock.release()
                continue
            self._lock.release()
