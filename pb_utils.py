#! /usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
Created on Fri Jun 12 15:50:11 2020

@author: Macrobull
"""

from __future__ import division, unicode_literals # absolute_import(utils)

from io import StringIO, TextIOBase


### helper classes ###


class StreamReader:
    r"""simple prototxt stream splitter"""

    def __init__(self, stream:TextIOBase):
        self.stream = stream

    def __iter__(self)->'Iterator':
        while True:
            data = self.read_one()
            if not data:
                break

            yield data

    def read_one(self)->str:
        r"""read one parsible field / block"""

        self.buf = StringIO()
        self.states = []
        while True:
            line = self.stream.readline()
            if not line:
                break

            if not self.states and line.strip():
                self.states.append((self._read_block, dict()))

            pos = self.buf.tell()
            self.buf.write(line)
            self.buf.seek(pos)
            sub_state = None
            while self.states:
                func, state = self.states.pop()
                sub_state = func(sub_state, **state)
                if sub_state is None:
                    break
            else:
                size = self.buf.tell()
                self.buf.seek(0)
                ret = self.buf.read(size)
                self.buf = StringIO()
                if not (sub_state and sub_state.get('newline')):
                    ret += '\n'
                return ret

        if self.states:
            raise IOError('stream closed with trailing content')

    def _read_block(
            self, sub_state,
            depth=0):
        if sub_state and sub_state.get('newline'):
            self.buf.seek(self.buf.tell() - 1)

        get_state = lambda: {'depth': depth}

        while True:
            char = self.buf.read(1)
            if not char:
                break

            if char == '"' or char == "'":
                self.states.append((self._read_block, get_state()))
                self.states.append((self._read_quoted_string, {'quote': char}))
                return Ellipsis
            elif char == '#':
                self.states.append((self._read_block, get_state()))
                self.states.append((self._read_comment, dict()))
                return Ellipsis
            elif char == '\n':
                if depth == 0:
                    return {'newline': True}
            elif char == '{':
                depth += 1
            elif char == '}':
                if depth == 0:
                    raise ValueError('unexpected }')

                depth -= 1

        self.states.append((self._read_block, get_state()))

    def _read_quoted_string(
            self, sub_state,
            quote='"', escaped=False):
        while True:
            char = self.buf.read(1)
            if not char:
                break

            if escaped:
                escaped = False
                continue

            if char == '\\':
                escaped = True
            elif char == quote:
                return dict()

        self.states.append((self._read_quoted_string, {'quote': quote, 'escaped': escaped}))

    def _read_comment(self, sub_state):
        line = self.buf.readline()
        if line.endswith('\n'):
            return {'newline': True}

        self.states.append((self._read_comment, dict()))


if __name__ == '__main__':
    s = StringIO("""
        a: 1
        b {
            x: 2 # waka'waka
            y {
                z: "Some
                    Mutiline
                    Text"
            }
            y {
                z: 'Apple\\'s good'
            }
        }
        """)
    s = StreamReader(s)
    for b in s:
        print(b.rstrip('\n'))
        print('-' * 9)
