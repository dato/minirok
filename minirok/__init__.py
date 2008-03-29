#! /usr/bin/env python
## vim: fileencoding=utf-8
#
# Copyright (c) 2007-2008 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import os
import sys
import logging

##

filesystem_encoding = sys.getfilesystemencoding()

##

__appname__     = 'minirok'
__progname__    = 'Minirok'
__version__     = '2.0~dev'
__description__ = 'A small music player written in Python'
__copyright__   = 'Copyright (c) 2007-2008 Adeodato Simó'
__homepage__    = 'http://chistera.yi.org/~adeodato/code/minirok'
__bts__         = 'http://bugs.debian.org'
__authors__     = [
        ('Adeodato Simó', '', 'dato@net.com.org.es'),
]
__thanksto__    = [
        # ('Name', 'Task', 'Email', 'Webpage'),
        ('The Amarok developers', 'For their design and ideas, which I copied.\n'
         'And their code, which I frequently also copied.', '', 'http://amarok.kde.org'),
]

__license__ = '''\
Minirok is Copyright (c) 2007-2008 Adeodato Simó, and licensed under the
terms of the MIT license:

  Permission is hereby granted, free of charge, to any person obtaining
  a copy of this software and associated documentation files (the
  "Software"), to deal in the Software without restriction, including
  without limitation the rights to use, copy, modify, merge, publish,
  distribute, sublicense, and/or sell copies of the Software, and to
  permit persons to whom the Software is furnished to do so, subject to
  the following conditions:

  The above copyright notice and this permission notice shall be included
  in all copies or substantial portions of the Software.

  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
  EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
  MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
  IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
  CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
  TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
  SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.'''

##

def _minirok_logger():
    levelname = os.environ.get('MINIROK_DEBUG_LEVEL', 'warning')
    level = getattr(logging, levelname.upper(), None)

    if not isinstance(level, int):
        bogus_debug_level = True
        level = logging.WARNING
    else:
        bogus_debug_level = False

    fmt = 'minirok: %(levelname)s: %(message)s'

    stderr = logging.StreamHandler(sys.stderr)
    stderr.setFormatter(logging.Formatter(fmt))

    logger = logging.getLogger('minirok')
    logger.setLevel(level)
    logger.addHandler(stderr)

    if bogus_debug_level:
        logger.warn('invalid value for MINIROK_DEBUG_LEVEL: %r', levelname)

    return logger

logger = _minirok_logger()

del _minirok_logger

##

_do_exit = False
_not_found = []

try:
    import PyQt4
except ImportError:
    _do_exit = True
    _not_found.append('PyQt')

try:
    from PyKDE4 import (
        kio,
        kdeui, # used below
        kdecore,
    )
except ImportError, e:
    _do_exit = True
    _not_found.append('PyKDE (error was: %s)' % e)

try:
    import mutagen
except ImportError:
    _do_exit = True
    _not_found.append('Mutagen')

try:
    # Do not import gst instead of pygst here, or gst will eat our --help
    import pygst
    pygst.require('0.10')
except ImportError:
    _do_exit = True
    _not_found.append('GStreamer Python bindings')
except pygst.RequiredVersionError:
    _do_exit = True
    _not_found.append('GStreamer Python bindings (>= 0.10)')

try:
    import lastfm
    _has_lastfm = True
except ImportError:
    _has_lastfm = False

if _not_found:
    print >>sys.stderr, ('''\
The following required libraries could not be found on your system:

%s

See the "Requirements" section in the README file for details about where to
obtain these dependencies, or how to install them from your distribution.''' %
    ('\n'.join('    * %s' % s for s in _not_found)))

if _do_exit:
    sys.exit(1)

del _do_exit
del _not_found

##

class Globals(object):
    """Singleton object to hold pointers to various pieces of the program.

    See the __slots__ variable for a list of available attributes.
    """

    __slots__ = [
            'engine',
            'playlist',
            'preferences',
            'action_collection',
    ]

Globals = Globals()
