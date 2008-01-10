#! /usr/bin/env python

"""Text in the menu bar is not shown with the Oxygen theme.

http://www.riverbankcomputing.com/pipermail/pyqt/2008-January/018164.html
"""

import sys

from PyKDE4 import kdeui, kdecore

class MainWindow(kdeui.KMainWindow):
    def __init__ (self, *args):
        kdeui.KMainWindow.__init__(self, *args)
        self.menuBar().addMenu('&File')

def main():
    kdecore.KCmdLineArgs.init(sys.argv, 'test', '', kdecore.ki18n('test'), '1.0')
    application = kdeui.KApplication()
    main_window = MainWindow()
    main_window.show()
    application.exec_()

if __name__ == '__main__':
    main()

