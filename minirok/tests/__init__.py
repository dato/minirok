#! /usr/bin/env python
## Hey, Python: encoding=utf-8
#
# Copyright (c) 2010, 2011 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

"""Common code for all Minirok tests."""

import minirok

import atexit
import logging
import os
import shutil
import sys
import tempfile

from PyQt4 import QtCore, QtGui

import mox
import unittest2

from minirok import (
    engine,
    playlist,
    preferences,
)

##

def setup_package():
    minirok.logger.setLevel(logging.DEBUG)

##

class BaseTest(unittest2.TestCase):
    """Base class for all Minirok tests."""

    QAPP = None

    def setUp(self):
        class TerminateEarly:
            """Exception for terminating tested code early.

            This exception only exists in running tests, and hence cannot be
            caught by tested code by name, ensuring it'll always terminate
            running code unless they do a blanket "except:" statement.

            It doesn't inherit from Exception to go over "except Exception", but
            can't inherit from object either, since new-style classes can only
            be raised if they inherit from BaseException.
            """

        self.mox = mox.Mox()
        self.stubs = mox.stubout.StubOutForTesting()
        self.TerminateEarly = TerminateEarly

    def tearDown(self):
        self.mox.UnsetStubs()
        self.stubs.UnsetAll()
        self.stubs.SmartUnsetAll()

    @staticmethod
    def create_qapp():
        if BaseTest.QAPP is None:
            tmpdir = tempfile.mkdtemp(prefix='minirok_test.')
            atexit.register(shutil.rmtree, tmpdir)

            # This more or less mimics main() from:
            #   http://websvn.kde.org/*checkout*/trunk/KDE/kdelibs/kdecore/util/qtest_kde.h?revision=1098959
            os.environ['KDEHOME'] = os.path.join(tmpdir, 'kdehome')
            os.environ['XDG_DATA_HOME'] = os.path.join(tmpdir, 'xdg/local')
            os.environ['XDG_CONFIG_HOME'] = os.path.join(tmpdir, 'xdg/config')
            os.environ['KDE_SKIP_KDERC'] = '1'
            os.environ['LC_ALL'] = 'en_US.UTF-8'
            os.environ.pop('KDE_COLOR_DEBUG', None)

            # It seems this doesn't work (not in setup_package either).
            #
            # configdir = os.path.join(os.environ['KDEHOME'], 'share/config')
            # os.makedirs(configdir)
            #
            # with open(os.path.join(configdir, 'kdebugrc'), 'w') as f:
            #     f.write('DisableAll=false\n\n[129]\nInfoOutput=2\n')

            BaseTest.QAPP = QtGui.QApplication(sys.argv)

    def create_empty_globals(self):
        self.create_qapp()
        minirok.Globals.engine = engine.Engine()
        minirok.Globals.action_collection = MockActionCollection()
        minirok.Globals.preferences = preferences.Preferences()
        minirok.Globals.playlist = playlist.Playlist()

##

class AssertOk(mox.Comparator):

    def __init__(self, assert_method, *args):
        self._assert_method = assert_method
        self._args = args

    def equals(self, rhs):
        self._assert_method(*(self._args + (rhs,)))
        return True

##

class MockActionCollection(QtCore.QObject):

    def addAction(self, unused_name, unused_action):
        pass
