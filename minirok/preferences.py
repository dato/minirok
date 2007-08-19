#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import qt
import kdeui
import kdecore

import minirok
from minirok.ui import options1

##

class Preferences(kdecore.KConfigSkeleton):
    def __init__(self, *args):
        kdecore.KConfigSkeleton.__init__(self, *args)

        self.setCurrentGroup('Appearance')
        self._use_amarok_classic_theme = self.addItemBool('UseAmarokClassicTheme', True)

        self.setCurrentGroup('General')
        self._enable_lastfm = self.addItemBool('EnableLastfm', minirok._has_lastfm)

        self.readConfig()

    @property
    def use_amarok_classic_theme(self):
        return self._use_amarok_classic_theme[0].value()

    @property
    def enable_lastfm(self):
        return self._enable_lastfm[0].value()

##

class Dialog(kdeui.KConfigDialog):
    def __init__(self, *args):
        kdeui.KConfigDialog.__init__(self, *args)
        self.addPage(GeneralPage(self), 'General', 'minirok')

##

class GeneralPage(options1.Page):
    def __init__(self, *args):
        options1.Page.__init__(self, *args)
