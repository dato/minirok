#! /usr/bin/env python

"""http://www.riverbankcomputing.com/pipermail/pyqt/2007-August/016865.html"""

import sys

import qt
import kdeui
import kdecore

def main():
    application = kdecore.KApplication(sys.argv, 'test app')
    main_window = MainWindow(None, 'main window')
    main_window.show()
    application.exec_loop()

class MainWindow(kdeui.KMainWindow):
    def __init__ (self, *args):
        kdeui.KMainWindow.__init__(self, *args)

        self.global_accel = kdecore.KGlobalAccel(self)
        self.global_accel.insert('action', 'Action', '', kdecore.KShortcut('Ctrl+Alt+U'),
                kdecore.KShortcut(), self.slot_action)

        self.global_accel.updateConnections()

    def slot_action(self):
        print "Inside slot_action()"

if __name__ == '__main__':
    main()
