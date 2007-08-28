#! /usr/bin/env python

"""http://www.riverbankcomputing.com/pipermail/pyqt/2007-August/017052.html"""

import sys

import kdeui
import kdecore

def main():
    kdecore.KCmdLineArgs.init(sys.argv, 'test', 'test', 'test', '1.0')
    application = kdecore.KApplication()
    main_window = MainWindow()
    main_window.show()
    application.exec_loop()

class MainWindow(kdeui.KMainWindow):
    def saveProperties(self, config):
        config.writeEntry('foo.py', 'bar.py')

if __name__ == '__main__':
    main()
