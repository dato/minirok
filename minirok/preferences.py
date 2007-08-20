#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import re

import qt
import kdeui
import kdecore

import minirok
from minirok import util
try:
    from minirok.ui import options1
except ImportError:
    import sys
    class options1:
        class Page:
            pass
    print >>sys.stderr, '''\
You are running Minirok from the source branch without having compiled the UI
files: the preferences dialog will not work. You can compile them by running
`make -C minirok/ui` (you will need kdepyuic, from the python-kde3-dev package.'''

##

class Preferences(kdecore.KConfigSkeleton):
    def __init__(self, *args):
        kdecore.KConfigSkeleton.__init__(self, *args)

        self.setCurrentGroup('Appearance')
        self._use_amarok_classic_theme = self.addItemBool('UseAmarokClassicTheme', True)

        self.setCurrentGroup('General')
        self._enable_lastfm = self.addItemBool('EnableLastfm', minirok._has_lastfm)

        self.setCurrentGroup('Playlist')
        self._tag_regex_value = qt.QString()
        self._tags_from_regex = self.addItemBool('TagsFromRegex', False)
        self._tag_regex = self.addItemString('TagRegex', self._tag_regex_value, '')
        self._tag_regex_mode = self.addItemInt('TagRegexMode', 0)

        self.readConfig()

    @property
    def use_amarok_classic_theme(self):
        return self._use_amarok_classic_theme[0].value()

    @property
    def enable_lastfm(self):
        return self._enable_lastfm[0].value()

    @property
    def tags_from_regex(self):
        return self._tags_from_regex[0].value()

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
        key = self._tag_regex_mode[0].value()
        try:
            return _dict[key]
        except KeyError:
            minirok.logger.error('invalid value for TagRegexMode: %d', key)
            return _dict[0]

##

class Dialog(kdeui.KConfigDialog):
    def __init__(self, parent, name, preferences):
        kdeui.KConfigDialog.__init__(self, parent, name, preferences,
                kdeui.KDialogBase.IconList, kdeui.KDialogBase.Ok |
                kdeui.KDialogBase.Apply | kdeui.KDialogBase.Cancel)
        self.general_page = GeneralPage(self, preferences)
        self.addPage(self.general_page, 'General', 'minirok')

    def check_valid_regex(self):
        regex = util.kurl_to_path(self.general_page.kcfg_TagRegex.text())
        try:
            re.compile(regex)
            return True
        except re.error, e:
            msg = 'The introduced regular expression is not valid:\n%s' % e
            dialog = kdeui.KDialogBase(self, 'bad regex dialog', True, # modal
                        'Invalid regular expression', kdeui.KDialogBase.Ok,
                         kdeui.KDialogBase.Ok, False) # False: no separator
            page = dialog.makeVBoxMainWidget()
            label = qt.QLabel(msg, page)
            dialog.show()
            return False

    ##

    def slotOk(self):
        if self.check_valid_regex():
            return kdeui.KConfigDialog.slotOk(self)

    def slotApply(self):
        if self.check_valid_regex():
            return kdeui.KConfigDialog.slotApply(self)

##

class GeneralPage(options1.Page):
    def __init__(self, parent, preferences):
        options1.Page.__init__(self, parent)

        ##
        
        self.connect(self.kcfg_TagsFromRegex, qt.SIGNAL('toggled(bool)'),
                self.slot_tags_from_regex_toggled)

        self.slot_tags_from_regex_toggled(preferences.tags_from_regex)

        ##

        if not minirok._has_lastfm:
            qt.QToolTip.add(self.kcfg_EnableLastfm,
                    'Feature disabled because lastfmsubmitd is not installed')

        self.kcfg_EnableLastfm.setEnabled(minirok._has_lastfm)

    def slot_tags_from_regex_toggled(self, checked):
        self.regexInfoGroup.setEnabled(checked)
