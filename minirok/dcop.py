#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import qt
import dcopexport

import minirok

##

class Player(dcopexport.DCOPExObj):
    def __init__(self):
        dcopexport.DCOPExObj.__init__(self, 'player')

        for method, action in [
                ('play', 'action_play'),
                ('pause', 'action_pause'),
                ('playPause', 'action_play_pause'),
                ('stop', 'action_stop'),
                ('next', 'action_next'),
                ('previous', 'action_previous'),
        ]:
            self.addMethod('void %s()' % method, self.get_action(action))

        self.addMethod('QString nowPlaying()', lambda: qt.QString('FIXME'))

        # TODO Stop after current

    @staticmethod
    def get_action(action_name):
        """Returns the activate() method of a named action."""
        action = minirok.Globals.action_collection.action(action_name)
        if action is None:
            minirok.logger.critical('action %r not found', action_name)
            return lambda: None
        else:
            return action.activate
