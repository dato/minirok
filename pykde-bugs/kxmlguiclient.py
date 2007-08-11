#! /usr/bin/env python

"""This script demonstrates that multiple inheritance with KXMLGUIClient does not work."""

import qt
import kdeui

class MyClient1(kdeui.KXMLGUIClient):
    def __init__(self):
        super(MyClient1, self).__init__()

class MyClient2(kdeui.KXMLGUIClient, qt.QObject):
    def __init__(self):
        super(MyClient2, self).__init__()

class MyClient3(qt.QObject, kdeui.KXMLGUIClient):
    def __init__(self):
        super(MyClient3, self).__init__()

print hasattr(MyClient1(), 'actionCollection') # True

print hasattr(MyClient2(), 'actionCollection') # True
print hasattr(MyClient2(), 'connect')          # False

print hasattr(MyClient3(), 'actionCollection') # False
print hasattr(MyClient3(), 'connect')          # True
