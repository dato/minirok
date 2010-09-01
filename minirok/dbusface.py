#! /usr/bin/env python
## Hey, Python: encoding=utf-8
#
# Copyright (c) 2007-2008, 2010 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import minirok

import dbus
import dbus.service

from minirok import (
    util,
)

##

DBUS_SERVICE_NAME = 'org.kde.minirok'

##

class Player(dbus.service.Object):

    def __init__(self):
        dbus.service.Object.__init__(self, dbus.SessionBus(), '/Player')

    @staticmethod
    def get_action(action_name):
        """Returns the trigger method of a named action."""
        action = minirok.Globals.action_collection.action(action_name)
        if action is None:
            minirok.logger.error('action %r not found', action_name)
            return lambda: None
        else:
            return action.trigger
    ##

    decorator = dbus.service.method(DBUS_SERVICE_NAME)
    decorator_as = dbus.service.method(DBUS_SERVICE_NAME, 'as')
    decorator_s_s = dbus.service.method(DBUS_SERVICE_NAME, 's', 's')

    @decorator
    def Play(self):
        self.get_action('action_play')()

    @decorator
    def Pause(self):
        self.get_action('action_pause')()

    @decorator
    def PlayPause(self):
        self.get_action('action_play_pause')()

    @decorator
    def Stop(self):
        self.get_action('action_stop')()

    @decorator
    def Next(self):
        self.get_action('action_next')()

    @decorator
    def Previous(self):
        self.get_action('action_previous')()

    @decorator
    def StopAfterCurrent(self):
        self.get_action('action_toggle_stop_after_current')()

    @decorator_as
    def AppendToPlaylist(self, paths):
        files = map(util.kurl_to_path, paths)
        minirok.Globals.playlist.add_files_untrusted(files)

    @decorator_s_s
    def NowPlaying(self, format=None):
        tags = minirok.Globals.playlist.get_current_tags()

        if not tags:
            formatted = ''
        else:
            if format is not None:
                try:
                    formatted = format % tags
                except (KeyError, ValueError, TypeError), e:
                    formatted = '>> Error when formatting string: %s' % e
            else:
                title = tags['Title']
                artist = tags['Artist']
                if artist is not None:
                    formatted = u'%s - %s' % (artist, title)
                else:
                    formatted = title

        return formatted
