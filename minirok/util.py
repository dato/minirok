#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import sys

import qt
import kdecore

import minirok

##

def kurl_to_path(kurl):
    """Convert a KURL or QString to a str in the local filesystem encoding.

    For KURLs, the leading file:// prefix will be stripped if present.
    """
    if isinstance(kurl, kdecore.KURL):
        kurl = kurl.pathOrURL()

    return unicode(kurl).encode(minirok.filesystem_encoding)

def unicode_from_path(path):
    """Convert from the filesystem encoding to unicode."""
    if isinstance(path, unicode):
        return path
    else:
        try:
            return unicode(path, minirok.filesystem_encoding)
        except UnicodeDecodeError:
            # XXX use logging?
            print >>sys.stderr, ('minirok: warning: cannot convert %r to %s' %
                    (path, minirok.filesystem_encoding))
            return unicode(path, minirok.filesystem_encoding, 'replace')

##

class HasConfig(object):
    """A class that connects its slot_save_config to kApp.shutDown()"""

    def __init__(self):
        qt.QObject.connect(kdecore.KApplication.kApplication(),
                qt.SIGNAL('shutDown()'), self.slot_save_config)

    def slot_save_config(self):
        raise NotImplementedError, \
            "slot_save_config must be reimplemented in %s" % self.__class__
