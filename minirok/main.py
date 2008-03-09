#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007-2008 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import sys
import minirok

from PyQt4 import QtGui
from PyKDE4 import kdeui, kdecore

##

def main():
    _ = kdecore.ki18n
    emptyloc = kdecore.KLocalizedString()

    about_data = kdecore.KAboutData(
            minirok.__appname__,
            "", # catalog name
            _(minirok.__progname__),
            minirok.__version__,
            _(minirok.__description__),
            kdecore.KAboutData.License_Custom,
            _(minirok.__copyright__),
            emptyloc, # extra text
            minirok.__homepage__,
            minirok.__bts__)

    about_data.setLicenseText(_(minirok.__license__))
    about_data.setCustomAuthorText(emptyloc,
            _('Please report bugs to <a href="%s">%s</a>.<br>'
            'See README.Bugs for instructions.' %
             (minirok.__bts__, minirok.__bts__)))

    for name, task, email in minirok.__authors__:
        about_data.addAuthor(_(name), _(task), email)

    for name, task, email, webpage in minirok.__thanksto__:
        about_data.addCredit(_(name), _(task), email, webpage)

    options = kdecore.KCmdLineOptions()
    options.add('a')
    options.add('append', _('Try to append files to an existing Minirok instance'))
    options.add('+[files]', _('Files to load into the playlist'))

    kdecore.KCmdLineArgs.init(sys.argv, about_data)
    kdecore.KCmdLineArgs.addCmdLineOptions(options)

    args = kdecore.KCmdLineArgs.parsedArgs()
    count = args.count()
    files = []

    if count > 0:
        from minirok import util
        for i in range(count):
            files.append(util.kurl_to_path(args.url(i)))
        if (args.isSet('append') and
                append_to_remote_minirok_successful(files)):
            sys.exit(0)

    ##

    # These imports happen here rather than at the top level because if gst
    # gets imported before the above KCmdLineArgs.init() call, it steals our
    # --help option
    from minirok import engine, main_window as mw # XXX-KDE4 dcop dropped

    minirok.Globals.engine = engine.Engine()
    application = kdeui.KApplication()
    main_window = mw.MainWindow()

    # See the "Known bugs" section in README.Bugs
    if QtGui.QApplication.style().objectName() == 'oxygen':
        QtGui.QApplication.setStyle('Plastique')

    # XXX-KDE4
    # application.dcopClient().registerAs('minirok', False) # False: do not add PID
    # player = dcop.Player()

    if minirok._has_lastfm:
        from minirok import lastfm_submit
        lastfm_submitter = lastfm_submit.LastfmSubmitter()

    if files:
        minirok.Globals.playlist.add_files_untrusted(files, clear_playlist=True)

    ##

    if main_window.canBeRestored(1):
        main_window.restore(1, False) # False: do not force show()
    else:
        main_window.show()

    application.exec_()

##

def append_to_remote_minirok_successful(files):
    from subprocess import Popen, PIPE
    cmdline = [ 'dcop', 'minirok' ]

    try:
        p = Popen(cmdline, stdout=PIPE, stderr=PIPE)
    except OSError:
        return False
    else:
        status = p.wait()
        if status != 0:
            minirok.logger.warn('could not contact an existing Minirok instance')
            return False

    cmdline.extend(['player', 'appendToPlaylist', '['] + files + [']'])
    return not Popen(cmdline).wait()
