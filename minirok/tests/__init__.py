#! /usr/bin/env python
## Hey, Python: encoding=utf-8
#
# Copyright (c) 2010 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

"""Common code for all Minirok tests."""

import minirok

import mox
import unittest2

##

class BaseTest(unittest2.TestCase):
    """Base class for all Minirok tests."""

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
