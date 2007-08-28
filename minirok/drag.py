#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import os
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

        Directories will be read and all its files included.
        """
        files = []
        all_playable = isinstance(event, FileListDrag)

        urls = kdecore.KURL.List()
        kdecore.KURLDrag.decode(event, urls)

        def append_path(path):
            if os.path.isdir(path):
                try:
                    contents = sorted(os.listdir(path))
                except OSError, e:
                    minirok.logger.warn('could not list directory: %s', e)
                else:
                    for file_ in contents:
                        append_path(os.path.join(path, file_))
            elif ((all_playable or minirok.Globals.engine.can_play(path))
                    and path not in files):
                files.append(path)

        for url in urls:
            append_path(util.kurl_to_path(url))

        return files
