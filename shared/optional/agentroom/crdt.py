"""A bounded reference RGA sequence CRDT and an explicitly selected Yrs adapter.

RGA is NOT pycrdt/Yjs wire-compatible. It is the dependency-free reference
profile; the paper-family profile uses PycrdtBackend and never silently falls
back. Both compute updates against the READ snapshot, not the latest text.
No tombstone GC: pruning without replica acknowledgements can resurrect edits.
"""
from __future__ import annotations

import base64
import difflib
import json
import re
import uuid
from collections import defaultdict

MAX_TEXT = 128_000
MAX_NODES = 512_000
HEAD = "0:head"


def checked_text(value):
    if not isinstance(value, str) or '\x00' in value:
        raise ValueError('only UTF-8 text without NUL is supported')
    if len(value.encode('utf-8')) > MAX_TEXT:
        raise ValueError('text exceeds the explicit 128000-byte limit')
    return value


def edit_opcodes(old, desired):
    prefix = 0
    while prefix < min(len(old), len(desired)) and old[prefix] == desired[prefix]:
        prefix += 1
    suffix = 0
    while (suffix < min(len(old)-prefix, len(desired)-prefix)
           and old[len(old)-suffix-1] == desired[len(desired)-suffix-1]):
        suffix += 1
    stop_old, stop_new = len(old)-suffix, len(desired)-suffix
    left, right = old[prefix:stop_old], desired[prefix:stop_new]
    if len(left)*len(right) > 2_000_000:
        return [('replace', prefix, stop_old, prefix, stop_new)]
    return [(op,i+prefix,j+prefix,a+prefix,b+prefix)
            for op,i,j,a,b in difflib.SequenceMatcher(None,left,right,autojunk=False).get_opcodes()]


def key(identifier):
    if not isinstance(identifier, str) or not re.fullmatch(r'[0-9]+:[a-zA-Z0-9_-]{1,64}', identifier):
        raise ValueError('invalid CRDT identity')
    clock, actor = identifier.split(':')
    number = int(clock)
    if number > 2**63 - 1:
        raise ValueError('CRDT clock overflow')
    return number, actor


class RGA:
    name = 'rga-reference-v1'

    @staticmethod
    def empty():
        return {'nodes': {}, 'deleted': []}

    @staticmethod
    def validate(state):
        if not isinstance(state, dict) or set(state) != {'nodes', 'deleted'}:
            raise ValueError('invalid RGA state')
        nodes, deleted = state['nodes'], state['deleted']
        if not isinstance(nodes, dict) or not isinstance(deleted, list):
            raise ValueError('invalid RGA collections')
        if len(nodes) + len(deleted) > MAX_NODES:
            raise ValueError('CRDT capacity reached; archive explicitly, never discard tombstones')
        for ident, value in nodes.items():
            clock, _ = key(ident)
            if not isinstance(value, list) or len(value) != 2:
                raise ValueError('invalid insertion')
            parent, char = value
            if key(parent)[0] >= clock or (key(parent)[0] == 0 and parent != HEAD):
                raise ValueError('parent must causally precede child')
            if not isinstance(char, str) or len(char) != 1 or char == '\x00':
                raise ValueError('insert exactly one Unicode code point')
            char.encode('utf-8')
        for ident in deleted:
            if key(ident)[0] == 0:
                raise ValueError('cannot delete sentinel')
        return state

    @classmethod
    def merge(cls, left, right):
        cls.validate(left); cls.validate(right)
        nodes = {k: list(v) for k, v in left['nodes'].items()}
        for ident, value in right['nodes'].items():
            if ident in nodes and nodes[ident] != value:
                raise ValueError('CRDT ID equivocation')
            nodes[ident] = list(value)
        return cls.validate({'nodes': nodes, 'deleted': sorted(set(left['deleted']) | set(right['deleted']))})

    @classmethod
    def visible(cls, state):
        cls.validate(state)
        children = defaultdict(list)
        for ident, (parent, _char) in state['nodes'].items():
            children[parent].append(ident)
        for values in children.values():
            values.sort(key=key)
        stack, result = list(children[HEAD]), []
        deleted = set(state['deleted'])
        while stack:
            ident = stack.pop()
            if ident not in deleted:
                result.append(ident)
            stack.extend(children[ident])
        return result

    @classmethod
    def text(cls, state):
        return ''.join(state['nodes'][ident][1] for ident in cls.visible(state))

    @classmethod
    def delta(cls, base, desired, actor=None):
        checked_text(desired)
        ids = cls.visible(base)
        old = ''.join(base['nodes'][i][1] for i in ids)
        actor = actor or uuid.uuid4().hex
        clock = max([0] + [key(i)[0] for i in base['nodes']] + [key(i)[0] for i in base['deleted']])
        change = cls.empty()
        for op, i, j, a, b in edit_opcodes(old, desired):
            if op == 'equal':
                continue
            change['deleted'].extend(ids[i:j])
            parent = ids[i - 1] if i else HEAD
            for char in desired[a:b]:
                clock += 1
                ident = f'{clock}:{actor}'
                change['nodes'][ident] = [parent, char]
                parent = ident
        if cls.text(cls.merge(base, change)) != desired:
            raise ValueError('reference CRDT edit failed its local round trip')
        return change

    @classmethod
    def initial(cls, value):
        return cls.merge(cls.empty(), cls.delta(cls.empty(), value))


class PycrdtBackend:
    name = 'pycrdt-v1'

    def __init__(self):
        from pycrdt import Doc, Text
        self.Doc, self.Text = Doc, Text
        probe = Doc({'text': Text('é😀')})
        width = len(probe['text'])
        self.units = {2: 'codepoints', 3: 'utf16', 6: 'utf8'}.get(width)
        if self.units is None:
            raise RuntimeError('unrecognized pycrdt text offsets; refuse unsafe indexing')

    def _width(self, text):
        if self.units == 'codepoints':
            return len(text)
        return len(text.encode('utf-16-le')) // 2 if self.units == 'utf16' else len(text.encode('utf-8'))

    def _doc(self, state=None):
        doc = self.Doc({'text': self.Text()})
        if state is not None:
            updates = state.get('updates', [state['update']] if 'update' in state else [])
            if not isinstance(updates, list) or any(not isinstance(u, str) for u in updates):
                raise ValueError('invalid native update journal')
            for update in updates:
                doc.apply_update(base64.b64decode(update, validate=True))
        return doc

    def empty(self):
        return {'updates': []}

    def text(self, state):
        return str(self._doc(state)['text'])

    def delta(self, base, desired, actor=None):
        checked_text(desired)
        doc = self._doc(base)
        text = doc['text']
        old, vector = str(text), doc.get_state()
        with doc.transaction():
            for op, i, j, a, b in reversed(edit_opcodes(old, desired)):
                if op == 'equal':
                    continue
                start, stop = self._width(old[:i]), self._width(old[:j])
                if stop > start:
                    del text[start:stop]
                if desired[a:b]:
                    text.insert(start, desired[a:b])
        if str(text) != desired:
            raise RuntimeError('pycrdt edit failed its local round trip')
        return {'updates': [base64.b64encode(doc.get_update(vector)).decode()]}

    def merge(self, left, right):
        updates = []
        for source in (left, right):
            updates.extend(source.get('updates', [source['update']] if 'update' in source else []))
        state = {'updates': sorted(set(updates))}
        if sum(len(u) for u in state['updates']) > 16_000_000:
            raise ValueError('native update journal needs an explicit reviewed checkpoint')
        self._doc(state)
        return state

    def initial(self, value):
        empty = self.empty()
        return self.merge(empty, self.delta(empty, value))


def backend(name):
    if name == 'rga':
        return RGA()
    if name == 'pycrdt':
        return PycrdtBackend()
    raise ValueError('backend must be explicitly rga or pycrdt')


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
