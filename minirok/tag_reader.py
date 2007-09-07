#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import qt
import mutagen
import mutagen.mp3
import mutagen.easyid3

import minirok

##

class TagReader(qt.QObject):
    """Reads tags from files in a pending queue."""

    def __init__(self):
        qt.QObject.__init__(self)

        self.timer = qt.QTimer(self, 'tag reader timer')
        self.connect(self.timer, qt.SIGNAL('timeout()'), self.update_one)

        self._queue = []

    ##

    def queue(self, item):
        self._queue.append(item)
        if len(self._queue) == 1:
            self.timer.start(0, False) # False: not one-shot

    def dequeue(self, item):
        try:
            self._queue.remove(item)
        except ValueError:
            pass

        if len(self._queue) == 0:
            self.timer.stop()

    def clear_queue(self):
        self._queue[:] = []
        self.timer.stop()

    ##

    def update_one(self):
        item = self._queue.pop(0)

        if len(self._queue) == 0:
            self.timer.stop()

        tags = self.tags(item.path)

        if tags:
            item.update_tags(tags)
            item.update_display()

    ##

    @staticmethod
    def tags(path):
        """Return a dict with the tags read from the given path.

        Tags that will be read: Track, Artist, Album, Title, Length. Any of
        these may be not present in the returned dict.
        """
        try:
            info = mutagen.File(path)
            if isinstance(info, mutagen.mp3.MP3):
                # EasyID3 does not include the .info part, which contains
                # the length; so save it from the MP3 object.
                dot_info = info.info
                info = mutagen.easyid3.EasyID3(path)
                info.info = dot_info
            if info is None:
                raise Exception, 'mutagen.File() returned None'
        except Exception, e:
            # Er, note that not only the above raise is catched here, since
            # mutagen.File() can raise exceptios as well. Wasn't obvious when I
            # revisited this code.
            if path in str(e): # mutagen normally includes the path itself
                msg = 'could not read tags: %s' % e
            else:
                msg = 'could not read tags from %s: %s' % (path, e)
            minirok.logger.warning(msg)
            return {}

        tags = {}

        for column in [ 'Track', 'Artist', 'Album', 'Title' ]:
            if column == 'Track':
                tag = 'tracknumber'
            else:
                tag = column.lower()

            try:
                tags[column] = info[tag][0]
            except ValueError:
                minirok.logger.warn('invalid tag %r for %s', tag, type(info))
            except KeyError:
                # tag is not present
                pass

        try:
            tags['Length'] = round(info.info.length)
        except AttributeError:
            pass

        return tags
