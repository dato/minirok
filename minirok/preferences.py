#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import qt
import kdeui
import kdecore

import minirok
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

        self.readConfig()

    @property
    def use_amarok_classic_theme(self):
        return self._use_amarok_classic_theme[0].value()

    @property
    def enable_lastfm(self):
        return self._enable_lastfm[0].value()

##

class Dialog(kdeui.KConfigDialog):
    def __init__(self, parent, name, preferences):
        kdeui.KConfigDialog.__init__(self, parent, name, preferences,
                kdeui.KDialogBase.IconList, kdeui.KDialogBase.Ok |
                kdeui.KDialogBase.Apply | kdeui.KDialogBase.Cancel)
        self.addPage(GeneralPage(self), 'General', 'minirok')

##

class GeneralPage(options1.Page):
    def __init__(self, *args):
        options1.Page.__init__(self, *args)

        if not minirok._has_lastfm:
            qt.QToolTip.add(self.kcfg_EnableLastfm,
                    'Feature disabled because lastfmsubmitd is not installed')

        self.kcfg_EnableLastfm.setEnabled(minirok._has_lastfm)

