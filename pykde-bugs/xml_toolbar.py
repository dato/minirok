#! /usr/bin/env python

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
        self.vbox = MyVBox(self)

class MyVBox(qt.QVBox, kdeui.KXMLGUIClient):
    def __init__(self, parent):
        qt.QVBox.__init__(self, parent)
        kdeui.KXMLGUIClient.__init__(self)
        self.toolbar = kdeui.KToolBar(self, 'toolbar')

        # This assert succeeds...
        assert 'actionCollection' in dir(self)

        # ... but this does not:
        print hasattr(self, 'actionCollection')

        # XXX ... and this obviously dies with AttributeError
        # Using super() instead of calling each constructor does not help
        ac = self.actionCollection()

        kdeui.KAction('Action 1', kdecore.KShortcut.null(), self.noop, ac, 'action1')
        kdeui.KAction('Action 2', kdecore.KShortcut.null(), self.noop, ac, 'action2')
        kdeui.KAction('Action 3', kdecore.KShortcut.null(), self.noop, ac, 'action3')

        self.setXMLFile('/tmp/xml_toolbar.rc');
        self.createGUI()

    def createGUI(self):
        builder = kdeui.KXMLGUIBuilder(self)
        factory = kdeui.KXMLGUIFactory(builder, self)
        factory.addClient(self)

    def noop(self):
        pass

if __name__ == '__main__':
    main()

