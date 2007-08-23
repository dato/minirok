#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import qt
import kdeui
import kdecore

import minirok
from minirok import left_side, preferences, right_side, statusbar, util

##

class MainWindow(kdeui.KMainWindow, util.HasGUIConfig):

    def __init__ (self, *args):
        kdeui.KMainWindow.__init__(self, *args)
        util.HasGUIConfig.__init__(self)

        minirok.Globals.action_collection = self.actionCollection()
        minirok.Globals.preferences = preferences.Preferences()

        self.main_view = qt.QSplitter(self, 'main view')
        self.left_side = left_side.LeftSide(self.main_view, 'left side')
        self.right_side = right_side.RightSide(self.main_view, 'right side')
        self.statusbar = statusbar.StatusBar(self, 'statusbar')

        self.init_actions()
        self.init_menus()
        self.init_systray()
        self.init_global_accel()
        self.apply_preferences()

        self.setCentralWidget(self.main_view)
        self.setAutoSaveSettings()

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

        # Other
        self.action_toggle_window = kdeui.KAction('Show/Hide window',
                kdecore.KShortcut.null(), self.slot_toggle_window, ac,
                'action_toggle_window')

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
        self.systray = Systray(self)
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

    def apply_preferences(self):
        if not minirok.Globals.preferences.use_amarok_classic_theme:
            alternate_bg_color = \
                    kdecore.KGlobalSettings.alternateBackgroundColor()
            self.unsetPalette()
        else:
            # This comes from amarok/App::applyColorScheme().
            # QColor(0xRRGGBB) does not seem to work, though.
            blue = qt.QColor(32, 32, 80) # 0x202050
            grey = qt.QColor(215, 215, 239) # 0xD7D7EF
            alternate_bg_color = qt.QColor(57, 64, 98)
            group = qt.QColorGroup(qt.QApplication.palette().active())

            group.setColor(qt.QColorGroup.Base, blue)
            group.setColor(qt.QColorGroup.Text, qt.Qt.white)
            group.setColor(qt.QColorGroup.Foreground, grey)
            group.setColor(qt.QColorGroup.Background, alternate_bg_color)

            group.setColor(qt.QColorGroup.Button, alternate_bg_color)
            group.setColor(qt.QColorGroup.ButtonText, grey)
            group.setColor(qt.QColorGroup.Highlight, qt.Qt.white)
            group.setColor(qt.QColorGroup.HighlightedText, blue)

            # this one is for the disabled "Search" test in the tree_search
            group.setColor(qt.QColorGroup.Light, qt.Qt.black)

            self.setPalette(qt.QPalette(group, group, group))

        for lv in self.queryList('KListView'):
            lv.setAlternateBackground(alternate_bg_color)

    ##

    def slot_really_quit(self):
        self._flag_really_quit = True
        self.close()

    def slot_configure_shortcuts(self):
        kdeui.KKeyDialog.configure(self.actionCollection())

    def slot_configure_global_shortcuts(self):
        kdeui.KKeyDialog.configure(self.global_accel, True, self)

    def slot_preferences(self):
        if kdeui.KConfigDialog.showDialog('preferences dialog'):
            return
        else:
            dialog = preferences.Dialog(self, 'preferences dialog',
                minirok.Globals.preferences)
            self.connect(dialog, qt.SIGNAL('settingsChanged()'),
                    util.HasGUIConfig.settings_changed)
            dialog.show()

    def slot_toggle_window(self):
        w_id = self.winId()
        w_info = kdecore.KWin.windowInfo(w_id)
        current_desktop = kdecore.KWin.currentDesktop()

        if not w_info.isOnDesktop(current_desktop) or w_info.isMinimized():
            kdecore.KWin.setOnDesktop(w_id, current_desktop)
            kdecore.KWin.activateWindow(w_id)
            self.setShown(True)
        else:
            self.setShown(not self.isShown())

    ##

    def queryClose(self):
        self.hide()
        return self._flag_really_quit

##

class Systray(kdeui.KSystemTray):
    """A KSysTray class that calls Play/Pause on middle button clicks."""

    def __init__(self, *args):
        kdeui.KSystemTray.__init__(self, *args)
        self.setPixmap(self.loadIcon('minirok'))
        self.installEventFilter(self)

    def eventFilter(self, object_, event):
        if (object_ == self
                and event.type() == qt.QEvent.MouseButtonPress
                and event.button() == qt.QEvent.MidButton):
            minirok.Globals.action_collection.action('action_play_pause').activate()
            return True

        return kdeui.KSystemTray.eventFilter(self, object_, event)
