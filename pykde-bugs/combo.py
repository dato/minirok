#! /usr/bin/env python

import sys

import kio
import kfile
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

        self.combo = kfile.KURLComboBox(kfile.KURLComboBox.Directories, True, self, 'combo')
        self.combo.setCompletionObject(kio.KURLCompletion(kio.KURLCompletion.DirCompletion))

if __name__ == '__main__':
    main()

