#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import qt
import kdeui
import kdecore

import minirok
from minirok import engine, left_side, right_side

##

class MainWindow(kdeui.KMainWindow):

    def __init__ (self, *args):
        kdeui.KMainWindow.__init__(self, *args)

        minirok.Globals.engine = engine.Engine() # XXX move to main.py?
        minirok.Globals.action_collection = self.actionCollection()

        self.main_view = qt.QSplitter(self, 'main view')
        self.left_side = left_side.LeftSide(self.main_view, 'left side')
        self.right_side = right_side.RightSide(self.main_view, 'right side')

        self.setCentralWidget(self.main_view)

        self.init_actions()
        self.init_menus()
        self.init_systray()
        self.init_global_accel()

        # We only want the app to exit if Quit was called from the systray icon
        # or from the File menu, not if the main window was closed. Use a flag
        # so that slot_really_quit() and queryClose() know what to do.
        self._flag_really_quit = False

    ##

    def init_actions(self):
        ac = self.actionCollection()

        # File menu
        self.action_quit = kdeui.KStdAction.quit(self.slot_really_quit, ac)

        # Settings menu
        self.action_shortcuts = kdeui.KStdAction.keyBindings(
                self.slot_configure_shortcuts, ac)
        self.action_shortcuts.setShortcutConfigurable(False)

        self.action_global_shortcuts = kdeui.KStdAction.keyBindings(
                self.slot_configure_global_shortcuts, ac, 'action_global_shortcuts')
        self.action_global_shortcuts.setShortcutConfigurable(False)
        self.action_global_shortcuts.setText('Configure &Global Shortcuts...')

        # XXX This needs the KXML framework, but it does not work in PyKDE, see
        # see pykde-bugs/xml_toolbar.py.
        # self.action_configure_toolbars = kdeui.KStdAction.configureToolbars(
        #         self.slot_configure_toolbars, ac)
        # self.action_configure_toolbars.setShortcutConfigurable(False)

        self.action_preferences = kdeui.KStdAction.preferences(
                self.slot_preferences, ac)
        self.action_preferences.setShortcutConfigurable(False)

        # Help menu
        self.action_about = kdeui.KStdAction.aboutApp(
                kdeui.KAboutApplication(self, 'about', False).show, ac)
        self.action_about.setShortcutConfigurable(False)

    def init_menus(self):
        file_menu = qt.QPopupMenu(self)
        self.action_quit.plug(file_menu)
        self.menuBar().insertItem('&File', file_menu)

        settings_menu = qt.QPopupMenu(self)
        self.action_shortcuts.plug(settings_menu)
        # self.action_global_shortcuts.plug(settings_menu)
        # self.action_configure_toolbars.plug(settings_menu)
        self.action_preferences.plug(settings_menu)
        self.menuBar().insertItem('&Settings', settings_menu)

        help_menu = qt.QPopupMenu(self)
        self.action_about.plug(help_menu)
        self.menuBar().insertItem('&Help', help_menu)

    def init_systray(self):
        self.systray = kdeui.KSystemTray(self)
        self.systray.setPixmap(self.systray.loadIcon('minirok'))
        self.systray.connect(self.systray, qt.SIGNAL('quitSelected()'),
            self.slot_really_quit)
        self.systray.show()

    def init_global_accel(self):
        # XXX Using global accels crash PyKDE applications. :-(
        # http://www.riverbankcomputing.com/pipermail/pyqt/2007-August/016865.html
        # self.global_accel = kdecore.KGlobalAccel(self)
        # self.global_accel.insert('play', 'Play', '', kdecore.KShortcut('Ctrl+Alt+U'),
        #         kdecore.KShortcut.null(), self.engine.play)
        # self.global_accel.updateConnections()
        pass

    ##

    def slot_really_quit(self):
        self._flag_really_quit = True
        self.close()

    def slot_configure_shortcuts(self):
        kdeui.KKeyDialog.configure(self.actionCollection())

    def slot_configure_global_shortcuts(self):
        kdeui.KKeyDialog.configure(self.global_accel, True, self)

    def slot_preferences(self):
        pass

    ##

    def queryClose(self):
        self.hide()
        return self._flag_really_quit
