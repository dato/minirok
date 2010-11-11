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
        self.mox = mox.Mox()
        self.stubs = mox.stubout.StubOutForTesting()

    def tearDown(self):
        self.mox.UnsetStubs()
        self.stubs.UnsetAll()
        self.stubs.SmartUnsetAll()
