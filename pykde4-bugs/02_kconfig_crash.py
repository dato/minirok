#! /usr/bin/env python

"""Using KConfig crashes the application.

http://www.riverbankcomputing.com/pipermail/pyqt/2008-January/018232.html
"""

import sys

from PyKDE4 import kdeui, kdecore

class MainWindow(kdeui.KMainWindow):
    def __init__ (self, *args):
        kdeui.KMainWindow.__init__(self, *args)
        kdecore.KGlobal.config().group('Foo').writeEntry('a', 'b')
        print '=== syncing now ===' # not reached
        kdecore.KGlobal.config().sync()

def main():
    kdecore.KCmdLineArgs.init(sys.argv, 'test', '', kdecore.ki18n('test'), '1.0')
    application = kdeui.KApplication()
    main_window = MainWindow()
    main_window.show()
    application.exec_()

if __name__ == '__main__':
    main()
