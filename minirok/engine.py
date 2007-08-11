#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

class MockEngine(object):

    def __init__(self):
        self._status = 'stop'

    def play(self):
        self._status = 'play'
        print self._status

    def stop(self):
        self._status = 'stop'
        print self._status

    def pause(self):
        self._status = 'pause'
        print self._status

    def play_pause(self):
        if self._status == 'pause' or self._status == 'stop':
            self._status = 'play'
        else:
            self._status = 'pause'
        print self._status

    def next(self):
        print 'next'

    def previous(self):
        print 'previous'

##

Engine = MockEngine
