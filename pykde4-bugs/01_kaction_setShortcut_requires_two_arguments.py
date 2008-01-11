#! /usr/bin/env python

"""Default value for second argument of KAction.setShortcut() does not work.

http://www.riverbankcomputing.com/pipermail/pyqt/2008-January/018206.html
"""

from PyKDE4 import kdeui

action = kdeui.KAction(None)
action.setShortcut(kdeui.KShortcut('Ctrl+F'))
