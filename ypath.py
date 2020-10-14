#! /usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
Created on Tue Sep 22 21:03:43 2020

@author: Macrobull
"""

from __future__ import absolute_import, division, unicode_literals

import re

from quick_prototxt import load_prototxt


class YPathSyntaxError(Exception):
    r"""SyntaxError for YPath"""

    token_type :type
    text       :str
    problem    :'Optional[str]' = None
    position   :'Optional[int]' = None

    def __init__(self, token_type:type, text:str,
                 problem:'Optional[str]'=None, position:'Optional[int]'=None):
        self.token_type = token_type
        self.text = text
        self.problem = problem
        self.position = position

    def __str__(self)->str:
        s0 = f'invalid {self.token_type.__name__} syntax:'
        s1 = "'" + self.text + "'"

        if self.problem is None or self.position is None:
            return s0 + ' ' + s1

        s2 = ' ' * self.position
        s3 = f' ^ {self.problem}'
        newline = '\n    '
        return s0 + newline + s1 + newline + s2 + s3


class Node(object):
    r"""node: a basic field in a struct"""

    PATTERN :str          = r'([a-zA-Z]\w*)(?:\s*@\s*([\-\+]?\d+))?'
    REGEX   :'re.Pattern' = re.compile(PATTERN)

    name  :str
    index :'Optional[int]' = None

    def __repr__(self)->str:
        index = '' if self.index is None else f'@{self.index}'
        return f'<Node {self.name}{index}>'

    def parse(self, text:str,
              full:bool=True)->int:
        r"""parse from text fully or partially from head"""

        m = (Node.REGEX.fullmatch if full else Node.REGEX.match)(text)
        if not m:
            raise YPathSyntaxError(Node, text)

        self.name, index = m.groups()
        self.index = index and int(index)
        return m.end()

    def access(self, mapping:'Mapping[str, Any]')->'Any':
        r"""acess the item specified by this node in a mapping object"""

        ret = mapping[self.name]
        if self.index is not None:
            ret = ret[self.index]
        return ret

    def collect(self, mapping:'Mapping[str, Any]',
                with_name:bool=False)->'Sequence[Any]':
        r"""collect all items matches this node in a mapping object"""

        try:
            ret = self.access(mapping)
        except (LookupError, TypeError):
            ret = []
        else:
            ret = ret if isinstance(ret, list) else [ret]
        return [{self.name: r} for r in ret] if with_name else ret


class Path(object):
    r"""path: a hierarchy of nested 'Node's"""

    NodeClass :type = Node

    nodes     :'Sequence[NodeClass]'
    seperator :str

    def __init__(self,
                 seperator:str='/'):
        self.seperator = seperator

    def __repr__(self)->str:
        nodes = ', '.join(map(str, self.nodes))
        return f'<Path seperated with {self.seperator} {nodes}>'

    def __iter__(self)->'Iterator':
        return iter(self.nodes)

    def __getitem__(self, i:int)->NodeClass:
        return self.nodes[i]

    def parse(self, text:str,
              full:bool=True)->int:
        r"""parse from text fully or partially from head"""

        text_ = text
        nodes = []
        exception = None
        while True:
            if not text_:
                break
            if nodes and not text_.startswith(self.seperator): # permit first omission
                exception = YPathSyntaxError(
                    Path, text, 'seperator expected', len(text) - len(text_))
                break
            text__ = text_.lstrip(self.seperator).lstrip() #
            node = self.NodeClass()
            try:
                pos = node.parse(text__, full=False)
            except YPathSyntaxError as e:
                exception = e
                break
            else:
                nodes.append(node)
                text_ = text__[pos:].lstrip()

        if not nodes:
            raise YPathSyntaxError(Path, text, 'node expected', len(text) - len(text_))
        if full and text_:
            if exception is None:
                raise YPathSyntaxError(Path, text, 'unexpected token', len(text) - len(text_))
            else:
                raise exception

        self.nodes = tuple(nodes)
        return len(text) - len(text_)

    def access(self, mapping:'Mapping[str, Any]')->'Any':
        r"""acess the item specified by this path in a mapping object"""

        ret = mapping
        for node in self.nodes:
            ret = node.access(ret)
        return ret

    def collect(self, mapping:'Mapping[str, Any]',
                with_name:bool=False)->'Sequence[Any]':
        r"""collect all items matches this path in a mapping object"""

        ret = [mapping]
        for node in self.nodes[:-1]:
            ret = sum((node.collect(i) for i in ret), [])
        if with_name:
            ret = sum((self.nodes[-1].collect(i, with_name=with_name) for i in ret), [])
        else:
            ret = sum((self.nodes[-1].collect(i) for i in ret), [])
        return ret


# @inherit_docs
class NodeWithPredicates(Node):
    r"""single_node: the 'Node' with 'Predicates'"""

    PREDICATES_BEGIN     :str = r'('
    PREDICATES_END       :str = r')'
    PREDICATES_DELIMITER :str = r'|'

    predicates :'Sequence[Predicate]' = tuple()

    def __repr__(self)->str:
        index = '' if self.index is None else f'@{self.index}'
        predicates = ' and '.join(map(str, self.predicates))
        predicates = predicates and (' where ' + predicates)
        return f'<NodeWithPredicates {self.name}{index}{predicates}>'

    def parse(self, text:str,
              full:bool=True)->int:
        pos = super().parse(text, full=False)
        text_ = text[pos:].lstrip()
        predicates = []
        started = False
        while True:
            if started:
                if not text_:
                    raise YPathSyntaxError(
                        NodeWithPredicates, text, 'trailing predicates', len(text))
                if text_[0] == NodeWithPredicates.PREDICATES_END:
                    text_ = text_[1:]
                    if full and text_:
                        raise YPathSyntaxError(
                            NodeWithPredicates, text,
                            'unexpected token', len(text) - len(text_))
                    break
                elif text_[0] == NodeWithPredicates.PREDICATES_DELIMITER:
                    text_ = text_[1:].lstrip()
                    predicate = Predicate()
                    pos = predicate.parse(text_, full=False)
                    predicates.append(predicate)
                    text_ = text_[pos:].lstrip()
                    continue
                raise YPathSyntaxError(
                    NodeWithPredicates, text, 'unexpected token', len(text) - len(text_))
            else:
                if not text_:
                    break
                if text_[0] == NodeWithPredicates.PREDICATES_BEGIN:
                    started = True
                    text_ = text_[1:].lstrip()
                    predicate = Predicate()
                    pos = predicate.parse(text_, full=False)
                    predicates.append(predicate)
                    text_ = text_[pos:].lstrip()
                    continue
                if full:
                    raise YPathSyntaxError(
                        NodeWithPredicates, text, 'unexpected token', len(text) - len(text_))
                break
        self.predicates = tuple(predicates)
        return len(text) - len(text_)

    def access(self, mapping:'Mapping[str, Any]')->'Any':
        ret = super().access(mapping)
        if not all(p.match(ret) for p in self.predicates):
            raise LookupError('item not match predicates')
        return ret

    def collect(self, mapping:'Mapping[str, Any]',
                with_name:bool=False)->'Sequence[Any]':
        try:
            items = super().access(mapping)
        except (LookupError, TypeError):
            items = []
        else:
            items = items if isinstance(items, list) else [items]
        ret = list(i for i in items if all(p.match(i) for p in self.predicates))
        return [{self.name: r} for r in ret] if with_name else ret


class NodeGroup(object):
    r"""node_group: single 'Node' or a group of 'Path's / 'YPath's"""

    NODES_BEGIN     :str = r'{'
    NODES_END       :str = r'}'
    NODES_DELIMITER :str = r','

    NodeClass: type = NodeWithPredicates
    PathClass: type = Path # placeholder, will be overrided later

    nodes :'Sequence[NodeWithPredicates]'

    def __repr__(self)->str:
        nodes = ' or '.join(map(str, self.nodes))
        return f'<NodeGroup {nodes}>'

    def __iter__(self)->'Iterator':
        return iter(self.nodes)

    def __getitem__(self, i:int)->'Union[NodeClass, PathClass]':
        return self.nodes[i]

    def parse(self, text:str,
              full:bool=True)->int:
        r"""parse from text fully or partially from head"""

        if not text:
            raise YPathSyntaxError(NodeGroup, text)

        text_ = text
        nodes = []
        if text_[0] == NodeGroup.NODES_BEGIN:
            while True:
                text_ = text_[1:].lstrip()
                node = self.PathClass()
                pos = node.parse(text_, full=False)
                nodes.append(node)
                text_ = text_[pos:].lstrip()
                if not text_:
                    raise YPathSyntaxError(NodeGroup, text, 'trailing nodes', len(text))
                if text_[0] == NodeGroup.NODES_END:
                    text_ = text_[1:]
                    if full and text_:
                        raise YPathSyntaxError(
                            NodeGroup, text, 'unexpected token', len(text) - len(text_))
                    break
                elif text_[0] == NodeGroup.NODES_DELIMITER:
                    continue
                raise YPathSyntaxError(
                    NodeGroup, text, 'unexpected token', len(text) - len(text_))
        else:
            node = self.NodeClass()
            pos = node.parse(text_, full=full)
            nodes.append(node)
            text_ = text_[pos:]

        self.nodes = tuple(nodes)
        return len(text) - len(text_)

    def collect(self, mapping:'Mapping[str, Any]',
                with_name:bool=False)->'Sequence[Any]':
        r"""collect 'Node's"""

        items = sum((n.collect(mapping, with_name=with_name) for n in self.nodes), [])
        if with_name:
            items = {id(next(iter(i.values()))): i for i in items}
        else:
            items = {id(i): i for i in items}
        return list(items.values())


# @inherit_docs
class YPath(Path):
    r"""ypath: 'Path' with group support"""

    NodeClass :type = NodeGroup

    access = property(doc='Disabled method')


NodeGroup.PathClass = YPath


class Predicate(object):
    r"""predicate: the 'Node' filter"""

    subclasses :'Seqeunce[type]' = []

    def parse(self, text:str,
              full:bool=True)->int:
        r"""parse from text fully or partially from head"""

        for cls in Predicate.subclasses:
            try:
                ret = cls.parse(self, text, full=full)
            except YPathSyntaxError:
                pass
            else:
                self.__class__ = cls
                return ret

        raise YPathSyntaxError(Predicate, text)

    def match(self, mapping:'Mapping[str, Any]')->bool:
        r"""test if a node should be filtered"""

        raise NotImplementedError('Abstract method')


# @inherit_docs
class HasAttrPredicate(Predicate):
    r"""test if a 'Node' has a field"""

    attr_path :Path
    inversed  :bool = False

    def __repr__(self)->str:
        prefix = '!' if self.inversed else ''
        return f'<HasAttr {prefix}{self.attr_path}>'

    def parse(self, text:str,
              full:bool=True)->int:
        if not text:
            raise YPathSyntaxError(HasAttrPredicate, text)
        text_ = text
        if text_[0] == '!':
            self.inversed = True
            text_ = text_[1:].lstrip()
        self.attr_path = Path(seperator='.')
        pos = self.attr_path.parse(text_, full=full)
        return len(text) - len(text_) + pos

    def match(self, mapping:'Mapping[str, Any]')->bool:
        try:
            self.attr_path.access(mapping)
        except (LookupError, TypeError):
            return self.inversed
        else:
            return not self.inversed


# @inherit_docs
class MatchAttrPredicate(Predicate):
    r"""test if a 'Node' whose field matches target"""

    OPERATORS    :'Mapping[str, Callable[[Any, Any], bool]]' = {
        # dict is ordered
        # 2 characters
        '==': lambda a, b: a == b,
        '!=': lambda a, b: a != b,
        '<>': lambda a, b: a != b,
        '>=': lambda a, b: a >= b,
        '<=': lambda a, b: a <= b,
        '~=': lambda a, b: b in a,
        # 1 character
        '>' : lambda a, b: a > b,
        '<' : lambda a, b: a < b,
    }
    REGEX_TARGET :'re.Pattern'                               = re.compile(r'\w+')

    attr_path :Path
    operator  :str
    func      :'Callable[[Any, Any], bool]'
    target    :'Any'

    def __repr__(self)->str:
        return f'<MatchAttr {self.attr_path} {self.operator} {self.target}>'

    def parse(self, text:str,
              full:bool=True)->int:
        self.attr_path = Path(seperator='.')
        pos = self.attr_path.parse(text, full=False)
        text_ = text[pos:].lstrip()
        if not text_:
            raise YPathSyntaxError(MatchAttrPredicate, text, 'operator expected', len(text))

        for operator, func in MatchAttrPredicate.OPERATORS.items():
            if text_.startswith(operator):
                self.operator = operator
                self.func = func
                text_ = text_[len(operator):].lstrip()
                break
        else:
            raise YPathSyntaxError(
                MatchAttrPredicate, text, 'invalid operator', len(text) - len(text_))

        if not text_:
            raise YPathSyntaxError(MatchAttrPredicate, text, 'target expected', len(text))

        if text_[0] in '"\'':
            quote = text_[0]
            escaped = False
            pos += 1
            for pos in range(1, len(text_)):
                if escaped:
                    escaped = False
                    continue
                char = text_[pos]
                if char == '\\':
                    escaped = True
                elif char == quote:
                    quote = None
                    pos += 1
                    break
            if quote:
                raise YPathSyntaxError(MatchAttrPredicate, text, 'trailing target', len(text))

            target = text_[:pos]
            text_ = text_[pos:]
        else:
            m = MatchAttrPredicate.REGEX_TARGET.match(text_)
            if not m:
                raise YPathSyntaxError(
                    MatchAttrPredicate, text, 'invalid target', len(text) - len(text_))

            target = m.group()
            text_ = text_[m.end():]

        self.target = load_prototxt(target)
        return len(text) - len(text_)

    def match(self, mapping:'Mapping[str, Any]')->bool:
        try:
            item = self.attr_path.access(mapping)
        except (LookupError, TypeError):
            return False
        else:
            return self.func(item, self.target)


# Predicate registries
Predicate.subclasses.extend([MatchAttrPredicate, HasAttrPredicate])


if __name__ == '__main__':
    node = Node()
    node.parse('node')
    print(node, node.access({'node': 1}), node.collect({'nonode': 1}))
    node.parse('node@1')
    print(node, node.access({'node': [1, 2, 3]}), node.collect({'nonode': 1}))
    node.parse('node@-1')
    print(node, node.access({'node': [1, 2, 3]}), node.collect({'node': 1}))

    for text in ('1node', 'node@', 'node@first'):
        try:
            node.parse(text)
        except YPathSyntaxError as e:
            print(e)
        else:
            raise AssertionError('unexpected success')

    path = Path()
    path.parse('a')
    print(path)
    path.parse('/a')
    print(path)
    path.parse('/a/b@-1/c@+1/d')
    print(path)
    print(path.access({'a': {'b': [{'c': [{'d': 0}, {'d': 1}]}]}}))
    print(path.collect({'a': {'b': [{'c': [{'d': 0}, {'d': 1}]}]}}, with_name=True))

    for text in ('//', 'a/b@/c', 'a/b.c'):
        try:
            path.parse(text)
        except YPathSyntaxError as e:
            print(e)
        else:
            raise AssertionError('unexpected success')

    node = NodeWithPredicates()
    node.parse('node(has_field)')
    print(node)
    print(node.access({'node': {'has_field': 1}}), node.access({'node': {'has_field': [1, 2]}}))
    print(node.collect({'node': {'has_field': 1}}), node.collect({'node': {'other_field': 2}}))
    print(node.collect({'node': [1, 2, 3]}))
    print(node.collect({'node': [{'has_field': 1}, {'not_has_field': 2}]}))
    node.parse('node(x==1)')
    print(node)
    print(node.access({'node': {'x': 1}}))
    print(node.collect({'node': {'x': 1}}), node.collect({'node': {'x': 2}}))
    print(node.collect({'node': [1, 2, 3]}))
    print(node.collect({'node': [{'x': 1}, {'x': 2}]}))

    for text in ('1a', 'a@', 'a@b', 'a(', 'a)', 'a(()', 'a(b', 'a@(b)', 'a@0(b@)'):
        try:
            node.parse(text)
        except YPathSyntaxError as e:
            print(e)
        else:
            raise AssertionError('unexpected success')

    group = NodeGroup()
    group.parse('{node(x==1), node(x>1)}')
    print(group.collect({'node': [{'x': 1}, {'x': 2}]}))

    for text in ('1a', 'a@', 'a@b', 'a{', '{a', 'a}', '{a, 1}', '{{}', '{a/b, a.b}'):
        try:
            group.parse(text)
        except YPathSyntaxError as e:
            print(e)
        else:
            raise AssertionError('unexpected success')

    path = YPath()
    path.parse('/{/proxy/node(x==1), node(x>=1)}')
    print(path.collect({'proxy': {'node': {'x': 1}}, 'node': {'x': 2}}))

    for text in ('/a/', 'a/b{x,y/z}'):
        try:
            path.parse(text)
        except YPathSyntaxError as e:
            print(e)
        else:
            raise AssertionError('unexpected success')
