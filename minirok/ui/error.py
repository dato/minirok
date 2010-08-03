#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2008 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

from PyQt4 import QtGui

class Ui(object):

    NO_UI = True

    def setupUi(self, widget):
        self.vboxlayout = QtGui.QVBoxLayout(widget)
        self.vboxlayout.addWidget(QtGui.QLabel("""\
You are running Minirok from the source branch
without having compiled the UI files. Please run
`make ui` in the top level directory.

You will need pykdeuic4, from the python-kde4-dev
package.
"""))

class options1:
    Ui_Page = Ui
