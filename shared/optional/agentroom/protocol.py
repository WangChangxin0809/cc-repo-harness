"""Small, dependency-free MCP stdio reference transport (2025-11-25).

Implements ONLY initialize, initialized, ping, tools/list and tools/call.
No HTTP, roots, prompts, sampling or task extension is advertised. Production
paper profile uses the official SDK; this transport is independently exercised
on real pipes, not an in-memory stand-in for SDK interoperability.
"""
from __future__ import annotations

import inspect
import json
import sys
import typing

VERSIONS = ('2025-11-25', '2025-06-18', '2025-03-26', '2024-11-05')
MAX_LINE = 1_500_000


def schema(fn):
    props, required = {}, []
    hints = typing.get_type_hints(fn)
    for name, p in inspect.signature(fn).parameters.items():
        kind = {str: 'string', int: 'integer', bool: 'boolean', float: 'number'}[hints[name]]
        props[name] = {'type': kind}
        if p.default is inspect.Parameter.empty: required.append(name)
        else: props[name]['default'] = p.default
    return {'type': 'object', 'properties': props, 'required': required, 'additionalProperties': False}


def validated(fn, args):
    if not isinstance(args, dict): raise ValueError('arguments must be an object')
    contract = schema(fn)
    if set(args) - set(contract['properties']): raise ValueError('unknown tool arguments')
    if set(contract['required']) - set(args): raise ValueError('required tool argument missing')
    for name, value in args.items():
        kind = contract['properties'][name]['type']
        good = {'string': isinstance(value, str), 'integer': type(value) is int,
                'boolean': type(value) is bool, 'number': type(value) in (int, float)}[kind]
        if not good: raise ValueError('invalid argument type: ' + name)
    return fn(**args)


def rpc_error(ident, code, message):
    return {'jsonrpc': '2.0', 'id': ident, 'error': {'code': code, 'message': message}}


class Dispatcher:
    def __init__(self, service):
        self.service = service
        self.negotiated = self.ready = False

    def handle(self, request):
        if (not isinstance(request, dict) or request.get('jsonrpc') != '2.0'
                or not isinstance(request.get('method'), str)):
            return rpc_error(None, -32600, 'Invalid Request')
        ident = request.get('id')
        if 'id' in request and (type(ident) not in (str, int)):
            return rpc_error(None, -32600, 'request ID must be a string or integer')
        method, params = request['method'], request.get('params', {})
        if 'id' not in request:
            if method == 'notifications/initialized' and self.negotiated: self.ready = True
            return None
        if not isinstance(params, dict): return rpc_error(ident, -32602, 'params must be an object')
        if method == 'initialize':
            if self.negotiated: return rpc_error(ident, -32600, 'already initialized')
            if (not isinstance(params.get('protocolVersion'), str)
                    or not isinstance(params.get('clientInfo'), dict)
                    or not isinstance(params.get('capabilities'), dict)):
                return rpc_error(ident, -32602, 'invalid initialize parameters')
            self.negotiated = True
            requested = params['protocolVersion']
            result = {'protocolVersion': requested if requested in VERSIONS else VERSIONS[0],
                      'serverInfo': {'name': 'cc-repo-harness-room-reference', 'version': '0.3.0'},
                      'capabilities': {'tools': {'listChanged': False}},
                      'instructions': self.service.instructions}
        elif method == 'ping': result = {}
        elif not self.ready: return rpc_error(ident, -32000, 'initialize and notify initialized first')
        elif method == 'tools/list':
            if params.get('cursor'): return rpc_error(ident, -32602, 'no pagination cursor was issued')
            result = {'tools': [{'name': name, 'description': fn.__doc__ or name,
                                'inputSchema': schema(fn)} for name, fn in self.service.tools.items()]}
        elif method == 'tools/call':
            name = params.get('name')
            if not isinstance(name, str): return rpc_error(ident, -32602, 'tool name must be a string')
            fn = self.service.tools.get(name)
            if fn is None: return rpc_error(ident, -32602, 'unknown tool')
            try:
                data = validated(fn, params.get('arguments', {}))
                result = {'content': [{'type': 'text', 'text': json.dumps(data, ensure_ascii=False)}],
                          'structuredContent': data, 'isError': False}
            except Exception as exc:
                result = {'content': [{'type': 'text', 'text': f'{type(exc).__name__}: {exc}'}], 'isError': True}
        else: return rpc_error(ident, -32601, 'Method not found')
        return {'jsonrpc': '2.0', 'id': ident, 'result': result}


def serve(service, stdin=None, stdout=None):
    source, target = stdin or sys.stdin.buffer, stdout or sys.stdout
    dispatcher = Dispatcher(service)
    while True:
        raw = source.readline(MAX_LINE + 1)
        if not raw: break
        if len(raw) > MAX_LINE or not raw.endswith(b'\n'):
            response = rpc_error(None, -32700, 'message is oversized or not newline delimited')
            target.write(json.dumps(response) + '\n'); target.flush(); return 2
        try:
            request = json.loads(raw.decode('utf-8'), parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
            response = dispatcher.handle(request)
        except (ValueError, UnicodeError, RecursionError):
            response = rpc_error(None, -32700, 'Parse error')
        if response is not None:
            target.write(json.dumps(response, ensure_ascii=False, allow_nan=False) + '\n'); target.flush()
    return 0
