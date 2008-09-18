#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007-2008 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import re

from PyKDE4 import kdeui
from PyQt4 import QtGui, QtCore

import minirok
from minirok import util
try:
    from minirok.ui import options1
except ImportError:
    from minirok.ui.error import options1
    minirok.logger.warn('compiled files under ui/ missing')

##

class Preferences(kdeui.KConfigSkeleton):
    def __init__(self, *args):
        kdeui.KConfigSkeleton.__init__(self, *args)

        self.setCurrentGroup('General')
        self._enable_lastfm = self.addItemBool(
                'EnableLastfm', False, minirok._has_lastfm)

        self.setCurrentGroup('Playlist')
        self._tag_regex_value = QtCore.QString()
        self._tags_from_regex = self.addItemBool('TagsFromRegex', False, False)
        self._tag_regex = self.addItemString('TagRegex', self._tag_regex_value, '')
        self._tag_regex_mode = self.addItemInt('TagRegexMode', 0, 0)

        self.readConfig()

    @property
    def enable_lastfm(self):
        return self._enable_lastfm.property().toBool()

    @property
    def tags_from_regex(self):
        return self._tags_from_regex.property().toBool()

    @property
    def tag_regex(self):
        return util.kurl_to_path(self._tag_regex_value)

    @property
    def tag_regex_mode(self):
        _dict = {
                0: 'Always',
                1: 'OnRegexFail',
                2: 'Never',
        }
        key, okp = self._tag_regex_mode.property().toInt()

        if not okp:
            key = -1 # ensure KeyError is raised below

        try:
            return _dict[key]
        except KeyError:
            minirok.logger.error('invalid value for TagRegexMode: %s',
                    self._tag_regex_mode.property().toString())
            return _dict[0]

##

class Dialog(kdeui.KConfigDialog):
    def __init__(self, parent, name, preferences):
        kdeui.KConfigDialog.__init__(self, parent, name, preferences)
        self.setButtons(kdeui.KDialog.ButtonCode(kdeui.KDialog.Ok |
                        kdeui.KDialog.Apply | kdeui.KDialog.Cancel))

        self.general_page = GeneralPage(self, preferences)
        self.general_page_item = self.addPage(self.general_page, 'General')
        self.general_page_item.setIcon(kdeui.KIcon('minirok'))

    def check_valid_regex(self):
        regex = util.kurl_to_path(self.general_page.kcfg_TagRegex.text())
        try:
            re.compile(regex)
        except re.error, e:
            msg = 'The introduced regular expression is not valid:\n%s' % e
            kdeui.KMessageBox.error(self, msg, 'Invalid regular expression')
            return False
        else:
            return True

    ##

    def slotButtonClicked(self, button):
        if (button not in (kdeui.KDialog.Ok, kdeui.KDialog.Apply)
                or self.check_valid_regex()):
            kdeui.KConfigDialog.slotButtonClicked(self, button)

##

class GeneralPage(QtGui.QWidget, options1.Ui_Page):
    def __init__(self, parent, preferences):
        QtGui.QWidget.__init__(self, parent)
        self.setupUi(self)

        if getattr(self, 'NO_UI', False):
            # This Ui_Page comes from ui/error.py.
            return

        ##

        self.connect(self.kcfg_TagsFromRegex, QtCore.SIGNAL('toggled(bool)'),
                self.slot_tags_from_regex_toggled)

        self.slot_tags_from_regex_toggled(preferences.tags_from_regex)

        ##

        if not minirok._has_lastfm:
            self.kcfg_EnableLastfm.setToolTip(
                    'Feature disabled because lastfmsubmitd is not available')

        self.kcfg_EnableLastfm.setEnabled(minirok._has_lastfm)

    def slot_tags_from_regex_toggled(self, checked):
        self.regexInfoGroup.setEnabled(checked)
