#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import sys
import kdecore

import minirok
import minirok.dcop
import minirok.engine
import minirok.main_window
import minirok.lastfm_submit

##

def main():
    about_data = kdecore.KAboutData(
            minirok.__appname__,
            minirok.__progname__,
            minirok.__version__,
            minirok.__description__,
            kdecore.KAboutData.License_Custom,
            minirok.__copyright__,
            "", # extra text
            minirok.__homepage__,
            minirok.__bts__)

    about_data.setLicenseText(minirok.__license__)
    about_data.setCustomAuthorText('',
            'Please report bugs to <a href="%s">%s</a>.<br>'
            'See README.Bugs for instructions.' %
             (minirok.__bts__, minirok.__bts__))

    for author in minirok.__authors__:
        about_data.addAuthor(*author)

    for person in minirok.__thanksto__:
        about_data.addCredit(*person)

    kdecore.KCmdLineArgs.init(sys.argv, about_data)

    minirok.Globals.engine = minirok.engine.Engine()
    minirok.Globals.engine.start()

    application = kdecore.KApplication()
    main_window = minirok.main_window.MainWindow()

    application.dcopClient().registerAs('minirok', False) # False: do not add PID
    player = minirok.dcop.Player()

    lastfm_submitter = minirok.lastfm_submit.LastfmSubmitter()

    main_window.show()
    application.exec_loop()
