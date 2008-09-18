#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007-2008 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import os

from PyQt4 import QtGui, QtCore
from PyKDE4 import kio, kdeui, kdecore

import minirok
from minirok import left_side, preferences, right_side, statusbar, util

##

class MainWindow(kdeui.KXmlGuiWindow, util.HasConfig):

    CONFIG_SECTION = 'MainWindow'
    CONFIG_OPTION_SPLITTER_STATE = 'splitterState'

    def __init__ (self, *args):
        kdeui.KXmlGuiWindow.__init__(self, *args)
        util.HasConfig.__init__(self)

        minirok.Globals.action_collection = self.actionCollection()
        minirok.Globals.preferences = preferences.Preferences()

        self.main_view = QtGui.QSplitter(self)
        self.left_side = left_side.LeftSide(self.main_view)
        self.right_side = right_side.RightSide(self.main_view, main_window=self)

        self.statusbar = statusbar.StatusBar(self)
        self.setStatusBar(self.statusbar)

        config = kdecore.KGlobal.config().group(self.CONFIG_SECTION)
        value = config.readEntry(self.CONFIG_OPTION_SPLITTER_STATE,
                                    QtCore.QVariant(QtCore.QByteArray()))
        self.main_view.restoreState(value.toByteArray())

        self.init_systray()
        self.init_actions()

        self.setHelpMenuEnabled(False)
        self.setCentralWidget(self.main_view)
        # self.setAutoSaveSettings() # XXX-KDE4 I don't think this is needed anymore: Check

        # If a minirokui.rc file exists in the standard location, do
        # not specify one for setupGUI(), else specify one if available.
        has_std_rc = bool(unicode(kdecore.KStandardDirs.locate(
                                            'appdata', 'minirokui.rc')))

        args = [ self.StandardWindowOption(
            self.ToolBar | self.Keys | self.Save | self.Create) # StatusBar out
        ]

        if not has_std_rc:
            local_rc = os.path.join(
                    os.path.dirname(minirok.__path__[0]), 'config/minirokui.rc')
            if os.path.isfile(local_rc):
                args.append(local_rc)

        self.setupGUI(*args)

        # We only want the app to exit if Quit was called from the systray icon
        # or from the File menu, not if the main window was closed. Use a flag
        # so that slot_really_quit() and queryClose() know what to do.
        self._flag_really_quit = False

    ##

    def init_actions(self):
        actionCollection = self.actionCollection()

        # File menu
        self.action_open_directory = util.create_action('action_open_directory',
                'Open directory...', self.slot_open_directory, 'document-open-folder', 'Ctrl+F')

        self.action_quit = kdeui.KStandardAction.quit(self.slot_really_quit,
                actionCollection)

        # Help menu
        self.action_about = kdeui.KStandardAction.aboutApp(
                kdeui.KAboutApplicationDialog(None, self).show, actionCollection)
        self.action_about.setShortcutConfigurable(False)

        # Other
        self.action_toggle_window = util.create_action('action_toggle_window',
                'Show/Hide window', self.systray.toggleActive, global_shortcut='Ctrl+Alt+M')

        self.action_preferences = kdeui.KStandardAction.preferences(
                self.slot_preferences, actionCollection)
        self.action_preferences.setShortcutConfigurable(False)

    def init_systray(self):
        self.systray = Systray(self)
        self.systray.connect(self.systray, QtCore.SIGNAL('quitSelected()'),
            self.slot_really_quit)
        self.systray.show()

    ##

    def slot_open_directory(self):
        """Open a dialog to select a directory, and set it in the tree view."""
        # NOTE: Not using KFileDialog.getExistingDirectory() here, because
        # it pops up just a tree view which I don't find very useable.
        # XXX The "current" variable here crashes if we don't make a copy.
        current = QtCore.QString(self.left_side.path_combo.urls().first())
        dialog = kio.KFileDialog(kdecore.KUrl(current), 'Directories', self)
        dialog.setCaption('Open directory')
        dialog.setMode(kio.KFile.Directory)
        dialog.exec_()
        directory = dialog.selectedFile()
        if directory:
            self.left_side.path_combo.slot_set_url(directory)

    def slot_really_quit(self):
        self._flag_really_quit = True
        self.close()

    def slot_preferences(self):
        if kdeui.KConfigDialog.showDialog('preferences dialog'):
            return
        else:
            dialog = preferences.Dialog(self, 'preferences dialog',
                minirok.Globals.preferences)
            self.connect(dialog,
                    QtCore.SIGNAL('settingsChanged(const QString &)'),
                    util.HasGUIConfig.settings_changed)
            dialog.show()

    def slot_save_config(self):
        config = kdecore.KGlobal.config().group(self.CONFIG_SECTION)
        config.writeEntry(self.CONFIG_OPTION_SPLITTER_STATE, self.main_view.saveState())

    ##

    def queryClose(self):
        finishing_session = kdeui.KApplication.kApplication().sessionSaving()
        if not finishing_session:
            # We want to save the shown/hidden status on session quit
            self.hide()
        return self._flag_really_quit or finishing_session

    def saveProperties(self, config):
        config.writeEntry('docked', bool(self.isHidden()))

    def readProperties(self, config):
        self.setShown(not config.readBoolEntry('docked', False))

##

class Systray(kdeui.KSystemTrayIcon):
    """A KSystemTrayIcon class that calls Play/Pause on middle button clicks.

    It will also show the currently played track in its tooltip.
    """
    def __init__(self, *args):
        kdeui.KSystemTrayIcon.__init__(self, *args)
        self.setIcon(self.loadIcon('minirok'))
        self.installEventFilter(self)

        self.connect(self,
                QtCore.SIGNAL('activated(QSystemTrayIcon::ActivationReason)'),
                self.slot_activated)

    def slot_activated(self, reason):
        # NB: Filtering for middle button clicks in eventFilter() below does
        # not seem to work.
        if reason == QtGui.QSystemTrayIcon.MiddleClick:
            minirok.Globals.action_collection.action('action_play_pause').trigger()

    def eventFilter(self, object_, event):
        if (object_ == self
                and event.type() == QtCore.QEvent.ToolTip):
            tags = minirok.Globals.playlist.get_current_tags()
            if tags:
                title = tags.get('Title') or ''
                artist = tags.get('Artist') or ''
                if artist and title:
                    artist += ' - '
                if artist or title:
                    QtGui.QToolTip.showText(event.globalPos(), artist + title)
            return True

        return kdeui.KSystemTrayIcon.eventFilter(self, object_, event)
