#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007-2009 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import re

from PyKDE4 import kdeui
from PyQt4 import QtGui, QtCore

import minirok
from minirok import scrobble, util
try:
    from minirok.ui import options1
except ImportError:
    from minirok.ui.error import options1
    minirok.logger.warn('compiled files under ui/ missing')

##

class Preferences(kdeui.KConfigSkeleton):
    def __init__(self, *args):
        kdeui.KConfigSkeleton.__init__(self, *args)

        self.setCurrentGroup('Playlist')
        self._tag_regex_value = QtCore.QString()
        self._tags_from_regex = self.addItemBool('TagsFromRegex', False, False)
        self._tag_regex = self.addItemString('TagRegex', self._tag_regex_value, '')
        self._tag_regex_mode = self.addItemInt('TagRegexMode', 0, 0)

        self.lastfm = LastfmPreferences(self)
        self.readConfig()

    @property
    def tags_from_regex(self):
        return self._tags_from_regex.value()

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
        key = self._tag_regex_mode.value()

        try:
            return _dict[key]
        except KeyError:
            minirok.logger.error('invalid value for TagRegexMode: %s',
                    self._tag_regex_mode.property().toString())
            return _dict[0]

##

class LastfmPreferences(object):

    def __init__(self, skel):
        skel.setCurrentGroup('Last.fm')

        self._user = QtCore.QString()
        self._pass = QtCore.QString()
        self._hs_url = QtCore.QString()

        self._enable = skel.addItemBool('EnableLastfm', False, False)
        self._user_item = skel.addItemString('LastfmUser', self._user, '')
        self._pass_item = skel.addItemString('LastfmPassword', self._pass, '')
        self._server = skel.addItemInt('LastfmServer', 0, 0)
        self._hs_url_item = skel.addItemString('LastfmURL', self._hs_url, '')

    @property
    def enable(self):
        return self._enable.value()

    @property
    def user(self):
        return str(self._user)

    @property
    def password(self):
        return str(self._pass)

    @property
    def server(self):
        index = self._server.value()
        return scrobble.Server.get_all_values()[index]

    @property
    def handshake_url(self):
        return str(self._hs_url)

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
        if (button in (kdeui.KDialog.Ok, kdeui.KDialog.Apply)
                and not hasattr(options1.Ui_Page, 'NO_UI')
                and not self.check_valid_regex()):
            pass # Don't let the button close the dialog.
        else:
            kdeui.KConfigDialog.slotButtonClicked(self, button)

##

class GeneralPage(QtGui.QWidget, options1.Ui_Page):
    def __init__(self, parent, preferences):
        QtGui.QWidget.__init__(self, parent)
        self.setupUi(self)

        if getattr(self, 'NO_UI', False):
            # This Ui_Page comes from ui/error.py.
            return

        self.kcfg_LastfmServer.addItems(scrobble.Server.get_all_values())

        self.connect(self.kcfg_TagsFromRegex, QtCore.SIGNAL('toggled(bool)'),
                self.slot_tags_from_regex_toggled)

        self.connect(self.kcfg_EnableLastfm, QtCore.SIGNAL('toggled(bool)'),
                self.slot_enable_lastfm_toggled)

        self.connect(self.kcfg_LastfmServer,
                QtCore.SIGNAL('currentIndexChanged(const QString &)'),
                self.slot_lastfm_server_changed)

        self.slot_enable_lastfm_toggled(preferences.lastfm.enable)
        self.slot_tags_from_regex_toggled(preferences.tags_from_regex)
        self.slot_lastfm_server_changed(preferences.lastfm.server)

    def slot_enable_lastfm_toggled(self, checked):
        self.lastfmFrame.setEnabled(checked)

    def slot_tags_from_regex_toggled(self, checked):
        self.regexInfoGroup.setEnabled(checked)

    def slot_lastfm_server_changed(self, server):
        # TODO: do something fancy and show the URL that'll be used for !Other?
        self.kcfg_LastfmURL.setEnabled(str(server) == scrobble.Server.Other)
