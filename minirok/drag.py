#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import kdecore

import minirok
from minirok import util

##

class FileListDrag(kdecore.KURLDrag):

    def __init__(self, files, parent):
        """Constructs a KURLDrag object from a python list of str paths."""
        urls = kdecore.KURL.List()
        for path in files:
            url = kdecore.KURL()
            url.setPath(util.unicode_from_path(path))
            urls.append(url)
        kdecore.KURLDrag.__init__(self, urls, parent, 'drag object')

    @staticmethod
    def file_list(event):
        """Return a list of the file paths encoded in this event.
        
        Files that the engine can't play will not be included; if the event is
        an instance of FileListDrag, though, the list will be assumed to be
        filtered already.
        """
        files = []
        all_playable = isinstance(event, FileListDrag)

        urls = kdecore.KURL.List()
        kdecore.KURLDrag.decode(event, urls)

        for url in urls:
            path = util.kurl_to_path(url)
            if not (all_playable or minirok.Globals.engine.can_play(path)):
                continue
            else:
                files.append(path)

        return files
