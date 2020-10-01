#! /usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
Created on Sun Sep 15 22:09:46 2019

@author: Macrobull
"""

from __future__ import absolute_import, division, unicode_literals

import logging, re
import yaml

from io import StringIO


DELIMITER             :str = '@'
UNAME_ID_FORMAT       :str = '{:09d}'

CYAML_WARNING_MESSAGE :str = (
    'cYAML not enabled, using pyYAML implementation may impact performance'
)

logger :logging.Logger = logging.getLogger(name=__name__)

state :dict = dict()

if hasattr(yaml, 'cyaml'):
    dumper :yaml.Dumper = yaml.CSafeDumper

    state['loader'] = yaml.CSafeLoader
else:
    logger.warning(CYAML_WARNING_MESSAGE)

    dumper :yaml.Dumper = yaml.SafeDumper

    state['loader'] = yaml.SafeLoader


def set_default_dict_type(dict_cls:type):
    r"""override default dict class"""

    from collections.abc import Hashable
    from yaml import Node
    from yaml.constructor import ConstructorError, SafeConstructor

    # @inherit_docs
    class Constructor(SafeConstructor):
        r"""overload with custom dict class"""

        def construct_mapping(
                self, node:Node,
                *args, **kwds)->'Mapping[Any, Any]':
            if not isinstance(node, yaml.nodes.MappingNode):
                raise ConstructorError(
                    None, None,
                    "expected a mapping node, but found %s" % (node.id, ),
                    node.start_mark)
            mapping = dict_cls()
            for key_node, value_node in node.value:
                key = self.construct_object(key_node, *args, **kwds)
                if not isinstance(key, Hashable):
                    raise ConstructorError("while constructing a mapping", node.start_mark,
                                           "found unhashable key", key_node.start_mark)
                value = self.construct_object(value_node, *args, **kwds)
                mapping[key] = value
            return mapping

        def construct_yaml_map(self, node:Node):
            data = dict_cls()
            yield data

            value = self.construct_mapping(node)
            data.update(value)

    Constructor.add_constructor(u'tag:yaml.org,2002:map', Constructor.construct_yaml_map)

    if hasattr(yaml, 'cyaml'):
        # @inherit_docs
        class Loader(
                yaml.cyaml.CParser,
                Constructor,
                yaml.resolver.Resolver):
            r"""overload"""

            def __init__(self, stream:'io.TextIOBase'):
                yaml.cyaml.CParser.__init__(self, stream)
                Constructor.__init__(self)
                yaml.resolver.Resolver.__init__(self)
    else:
        logger.warning(CYAML_WARNING_MESSAGE)

        # @inherit_docs
        class Loader(
                yaml.reader.Reader, yaml.scanner.Scanner,
                yaml.parser.Parser, yaml.composer.Composer,
                Constructor,
                yaml.resolver.Resolver):
            r"""overload"""

            def __init__(self, stream:'io.TextIOBase'):
                yaml.reader.Reader.__init__(self, stream)
                yaml.scanner.Scanner.__init__(self)
                yaml.parser.Parser.__init__(self)
                yaml.composer.Composer.__init__(self)
                Constructor.__init__(self)
                yaml.resolver.Resolver.__init__(self)

    state['loader'] = Loader


def load_prototxt(
        s:str,
        **load_kwds)->'Any':
    r"""
    direct deserialize from Protobuf text format
    load_kwds: kwds for 'yaml.load', leave it empty
    """

    # HINT: in fact no load_kwds required
    load = lambda s: yaml.load(s, Loader=state['loader'], **load_kwds)

    if not re.search(r'[a-zA-Z]\w*\s*[{:]', s): # if scalar
        return load(s)

    unames = dict()

    def replace_key(s):
        t = StringIO()
        start = 0
        idx = 0
        for m in re.finditer(r'(\n\s*)([a-zA-Z]\w*)\s*:', s):
            prefix, ok = m.groups()
            nk = ok + DELIMITER + UNAME_ID_FORMAT.format(idx)
            unames[nk] = ok
            t.write(s[start:m.start()])
            t.write(prefix)
            t.write(nk)
            t.write(':')
            start = m.end()
            idx += 1
        t.write(s[start:])
        return t.getvalue()

    def restore_key(no):
        oo = type(no)()
        for nk, nv in no.items():
            ok = unames[nk]
            nv = restore_key(nv) if isinstance(nv, dict) else nv
            ov = oo.get(ok)
            if ov is None:
                oo[ok] = nv
            else:
                if not isinstance(ov, list):
                    oo[ok] = [ov]
                oo[ok].append(nv)
        return oo

    s = '\n' + s + '\n'
    s = re.sub(r'\s+\n', '\n', s) # rstrip each line
    s = re.sub(r'(?<=\w)\s*{\n', ': {\n', s) # add : for field
    s = replace_key(s)
    s = re.sub(r'(?<=[^{\s])\n', ',\n', s) # add, for flow mapping
    s = '{' + s + '}' # simply

    # NOTE: Python 3 built-in ordered dict makes repeated fields parsing perfect
    # see yaml/constructor.py: BaseConstructor.construct_mapping for details
    o = load(s)

    return restore_key(o)


def dump_prototxt(
        o:'Any',
        unquote_rule:'Callable[[str], bool]'=str.isupper,
        quote:str='"', indent:int=2,
        **dump_kwds)->str:
    r"""
    direct serialize to Protobuf text format
    unquote_rule:
        function judges wether a string value should not be quoted for types like enum,
        by default full-uppercased (an usual alternative is str.istitle)
    quote: prefered quote convension, ' or "
    indent: indent size
    dump_kwds: kwds for 'yaml.dump'
    """

    list_clss = (list, tuple, set)

    assert not isinstance(o, list_clss), f"'o' {o!r}cannot be unnamed list"

    # sorting is a required default behavior
    dump_kwds_ = dict(
        indent=indent, width=(indent * 2 + 1),
        default_flow_style=True, allow_unicode=True, # sort_keys=True,
    )
    dump_kwds_.update(dump_kwds)
    dump = lambda o: yaml.dump(o, Dumper=dumper, **dump_kwds_)

    def remove_document_end(s):
        t = '\n...'
        if s.endswith(t):
            s = s[:-len(t)]
        return s

    if not isinstance(o, dict): # extra scalar support
        if isinstance(o, str):
            if unquote_rule(o):
                s = o
            else:
                s = quote + o + quote
        else:
            s = dump(o)
            s = s.strip()
            s = remove_document_end(s)
        return s + '\n'

    str_tag = '!str '

    # impl from protobuf
    def is_numeric(s):
        if re.match(r'-?inf(?:inity)?f?', s, re.IGNORECASE):
            return True
        if re.match(r'nanf?', s, re.IGNORECASE):
            return True
        try:
            float(s.rstrip('f')) # throw ValueError
        except ValueError:
            return False
        else:
            return True

    def replace_key_value(oo):
        no = type(oo)()
        for ok, ov in oo.items():
            assert DELIMITER not in ok, f'invalid field name {ok!r} in Protobuf'

            if isinstance(ov, dict):
                no[ok] = replace_key_value(ov)
            elif isinstance(ov, str):
                no[ok] = ov if is_numeric(ov) else str_tag + ov # skip numeric literals
            elif isinstance(ov, list_clss):
                prefix = str(ok) + DELIMITER
                for idx, oi in enumerate(ov):
                    assert not isinstance(oi, list_clss), (
                        f'list item {oi!r} cannot be unnamed list')

                    nk = prefix + UNAME_ID_FORMAT.format(idx) # make key ordered
                    ni = replace_key_value(oi) if isinstance(oi, dict) else oi
                    no[nk] = ni
            else:
                no[ok] = ov
        return no

    def restore_key(s):
        t = StringIO()
        start = 0
        for m in re.finditer(r'(\n\s*)([a-zA-Z]\w*)' + DELIMITER + r'\d+\s*:', s):
            prefix, ok = m.groups()
            t.write(s[start:m.start()])
            t.write(prefix)
            t.write(ok)
            t.write(':')
            start = m.end()
        t.write(s[start:])
        return t.getvalue()

    def fix_mapping_end_break(s):
        t = StringIO()
        start = 0
        current_space_size = 0
        for m in re.finditer(r'\n(\s*)(.+?)({*)(}*)(?=\n)', s):
            spaces, content, lbraces, rbraces = m.groups()
            t.write(s[start:m.start()])

            if len(spaces) > current_space_size:
                assert len(spaces) == current_space_size + indent

                spaces = spaces[:current_space_size]
                t.write(' ')
            else:
                assert len(spaces) == current_space_size

                t.write('\n')
                t.write(spaces)

            current_space_size += indent * len(lbraces)
            assert current_space_size >= len(rbraces) * indent

            spaces = ' ' * current_space_size
            current_space_size -= indent * len(rbraces)
            t.write(content)
            t.write(lbraces)

            for brace in rbraces:
                spaces = spaces[:-indent]
                t.write('\n')
                t.write(spaces)
                t.write(brace)

            start = m.end()

        t.write(s[start:])
        return t.getvalue()

    def fix_value_quote(s):
        t = StringIO()
        start = 0
        str_re = re.compile(r'([\'"])' + str_tag + r'(.*?)([\'"])\s*\n') #
        for m in re.finditer(r'(?<=\n)(\s*)([a-zA-Z]\w*)(:\s*)(.+?)(\s*\n)', s):
            s0, key, s1, value, s2 = m.groups()
            t.write(s[start:m.start()])
            t.write(s0)
            t.write(key)
            t.write(s1)

            unquoted = True
            str_match = str_re.match(value + s2)
            if str_match:
                lquote, value, rquote = str_match.groups()
                if lquote == rquote:
                    if not unquote_rule(value):
                        unquoted = False
                        if lquote != quote and quote not in value: # HINT: not forced
                            lquote = quote
                        t.write(lquote)
                        t.write(value)
                        t.write(lquote)

            if unquoted:
                t.write(value)

            t.write(s2)
            start = m.end()

        t.write(s[start:])
        return t.getvalue()

    o = replace_key_value(o)
    # HINT: ~ canonical=True
    s = dump(o)
    s = '\n' + s.strip()[1: -1].replace('\n  ', '\n') + '\n' # remove root flow mapping brace
    s = restore_key(s)
    s = s.replace(',\n', '\n').replace(': {', ' {') # remove , and :)
    s = fix_mapping_end_break(s)
    s = fix_value_quote(s)
    return s[1:]


if __name__ == '__main__':
    o = 'hello world'
    t = dump_prototxt(o)
    print(t)
    o = load_prototxt(t)
    print(o)
    print('-' * 8)
    o = {'hello': [{'world': 42}, {'what': False}, {'enum': 'DEBUG'}]}
    t = dump_prototxt(o)
    print(t)
    o = load_prototxt(t)
    print(o)
    print('-' * 8)

    from easydict import EasyDict

    set_default_dict_type(EasyDict)
    o = {'y': [1, 2], 'x': [{'a': 3.0, 'b': {'c': 4}}, {'a': 0, 'z': '1 2 3 4'}]}
    t = dump_prototxt(o)
    print(t)
    o = load_prototxt(t)
    print(o)
    print('-' * 8)
