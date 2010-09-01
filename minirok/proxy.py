#! /usr/bin/env python
## Hey, Python: encoding=utf-8
#
# Copyright (c) 2008, 2010 Adeodato Simó (dato@net.com.org.es)
# Licensed under the terms of the MIT license.

import minirok

import re

from PyQt4 import QtGui

from minirok import (
    util,
)

##

class Model(QtGui.QSortFilterProxyModel):
    """A proxy model that makes multi-word match.

    Can be nicely used with a LineWidget below. Matches will be done like this:

      * patterns will be matched against sourceModel.data(self.filterRole())
        (for the column given with filterKeyColumn(), or all columns if < 0)

      * patterns will be split into words, and an item will match if it
        matches (either as full words or subwords) *all* the words in pattern,
        in any order.
    """
    def __init__(self, parent=None):
        QtGui.QSortFilterProxyModel.__init__(self, parent)

        self.pattern = None
        self.regexes = []

    def setPattern(self, pattern):
        pystring = unicode(pattern).strip()

        if pystring:
            if pystring != self.pattern:
                self.pattern = pystring
                self.regexes = [re.compile(re.escape(pat), re.I | re.U)
                                for pat in pystring.split()]
        else:
            self.pattern = None

        self.invalidateFilter()

    def filterAcceptsRow(self, row, parent):
        if self.pattern is None:
            return True
        else:
            text = u''
            role = self.filterRole()
            model = self.sourceModel()

            c = self.filterKeyColumn()
            if c >= 0:
                columns = [c]
            else:
                columns = range(model.columnCount(parent))

            for c in columns:
                index = model.index(row, c, parent)
                data = index.data(role)
                text += unicode(data.toString())

            for regex in self.regexes:
                if not regex.search(text):
                    return False
            else:
                return True

##

def _map(method):
    """Decorator to invoke a method in sourceModel(), mapping one index."""
    def wrapper(self, index):
        index = self.mapToSource(index)
        return getattr(self.sourceModel(), method.func_name)(index)
    return wrapper

def _map_many(method):
    """Decorator to invoke a method in sourceModel(), mapping a list of indexes.
    """
    def wrapper(self, indexes):
        indexes = map(self.mapToSource, indexes)
        return getattr(self.sourceModel(), method.func_name)(indexes)
    return wrapper

##

class LineWidget(QtGui.QWidget):

    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self, parent)

        self._label = QtGui.QLabel('S&earch: ', self)
        self._searchLine = self.createSearchLine()

        self._searchLine.show()
        self._label.setBuddy(self._searchLine)
        self._label.show()

        layout = QtGui.QHBoxLayout(self)
        layout.setSpacing(0)
        layout.setMargin(0)
        layout.addWidget(self._label)
        layout.addWidget(self._searchLine)

        self.setFocusProxy(self._searchLine)

    def searchLine(self):
        return self._searchLine

    def createSearchLine(self):
        return Line(self)

##

class Line(util.DelayedLineEdit):
    def __init__(self, parent=None):
        self._model = None
        util.DelayedLineEdit.__init__(self, parent)

        self.connect(self,
                     self.SIGNAL,
                     lambda text: self._model.setPattern(text))

    def setProxyModel(self, model):
        assert isinstance(model, Model), \
            'proxy.Line only works with proxy.Model'
        self._model = model
