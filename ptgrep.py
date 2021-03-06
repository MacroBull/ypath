#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
Created on Wen Feb 20 20:20:20 2020

@author: Macrobull
"""

from __future__ import absolute_import, division, unicode_literals

import logging, sys, time
import yaml

from pb_utils import StreamReader
from quick_prototxt import dump_prototxt, load_prototxt
from ypath import YPath


def main():
    r"""main entrance"""

    import argparse

    class Formatter(argparse.ArgumentDefaultsHelpFormatter,
                    argparse.RawDescriptionHelpFormatter):
        r"""Formatter mixin"""

    parser = argparse.ArgumentParser(
        description='grep prototxt with YPath',
        formatter_class=Formatter,
        epilog=r"""
YPath syntax:
    ypath          ::= [/]<node_group>[/<node_group>/<node_group>...]
    node_group     ::= <single_node> | {<ypath>,<ypath>...}
    single_node    ::= <node>[(<predicate>|<predicate>...)]
    predicate      ::= [!]<predicate_path> | <predicate_path> <operator> <target>
    predicate_path ::= [.]<node>[.<node>.<node>...]
    node           ::= <field_name>[@<index>]
    operator       ::= == | != | <> | > | < | >= | <= | ~=
    field_name     ::= (any valid ProtoBuffer field name)
    index          ::= (any positive or negative integer)
    target         ::= (any valid ProtoBuffer text format value)
        """,
    )
    parser.add_argument(
        'path', type=str,
        help='the YPath for filtering',
    )
    parser.add_argument(
        'file', type=str, nargs='?',
        help='file to filter, stdin if not set',
    )
    parser.add_argument(
        '--delimiter', '-t', type=str, nargs='?', default='---', const='',
        help='delimiter between occurance',
    )
    parser.add_argument(
        '--debug', '-d', action='store_true',
        help='enable debug logging',
    )
    args = parser.parse_args()

    logging_format = '[%(levelname)8s]%(name)s::%(funcName)s:%(lineno)d: %(message)s'
    logging_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(format=logging_format, level=logging_level)
    logger = logging.getLogger(name='main')

    path = YPath()
    stream = StreamReader(sys.stdin if args.file is None else open(args.file))
    delimiter = args.delimiter

    if delimiter and not delimiter.endswith('\n'):
        delimiter += '\n'

    timings = {
        'parsing YPath': [None, None],
    }
    key = 'parsing YPath'
    timings[key][0] = time.time()
    path.parse(args.path.strip())
    timings[key][1] = time.time()
    logger.debug('path:\n\t%s', path)
    for key, (t0, t1) in timings.items():
        logger.debug('timing - %s: %.3fms', key, (t1 - t0) * 1e3)

    timings = {
        'last': None,
        'print': None,
        'split prototxt': [0, 0],
        'parsing prototxt': [0, 0],
        'filter YPath': [0, 0],
        'serialize prototxt': [0, 0],
    }

    def _add_measurement(key):
        if not args.debug:
            return

        tn, tl = time.time(), timings['last']
        timings['last'] = tn
        timings[key][0] += tn - tl
        timings[key][1] += 1

    def _report_timings():
        if not args.debug:
            return

        tp = time.time()
        if tp - timings['print'] > 2:  # every 2 seconds
            timings['print'] = tp
            for key, value in timings.items():
                if isinstance(value, list):
                    t, c = value
                    value[0] = value[1] = 0
                    logger.debug('timing - %s: %.3fms (%d samples)',
                                 key, t * 1e3 / c, c)
            logger.debug('timing ' + delimiter.rstrip())
        timings['last'] = time.time()

    timings['print'] = timings['last'] = time.time()
    for block in stream:
        _add_measurement('split prototxt')

        try:
            root = load_prototxt(block)
        except yaml.parser.ParserError:
            continue
        else:
            _add_measurement('parsing prototxt')

            if root is None or not isinstance(root, dict): # shortcut
                continue

            results = path.collect(root, with_name=True)

            _add_measurement('filter YPath')

            for result in results:
                sys.stdout.write(dump_prototxt(result))
                sys.stdout.write(delimiter)

            _add_measurement('serialize prototxt')

            sys.stdout.flush()

            _report_timings()


if __name__ == '__main__':
    main()
