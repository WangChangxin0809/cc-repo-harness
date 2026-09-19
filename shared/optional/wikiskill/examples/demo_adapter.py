"""Deterministic process adapter for wiring tests. NOT an LLM or a benchmark."""
import json
import sys

request = json.loads(sys.stdin.readline())
role, data = request['role'], request['input']
if role == 'inference':
    value = data.get('input', {}).get('text', '')
    prediction = value.upper() if 'UPPERCASE_TEXT' in data.get('skill_text', '') else value
    output = {'prediction': prediction, 'trace': 'Synthetic process: read public text; apply active rule.'}
elif role == 'maintain':
    output = {'index': 'Transformation failures are recorded in the log.',
              'log': 'Examined synthetic training traces: ' + ','.join(t['task'] for t in data['traces'])}
elif role == 'propose':
    for i, path in enumerate(data['trace_paths'][:4]):
        print(json.dumps({'type': 'tool', 'id': i, 'name': 'read_file', 'arguments': {'path': path}}), flush=True)
        result = json.loads(sys.stdin.readline())
        if 'error' in result: raise RuntimeError(result['error'])
    if data['active_skills']:
        output = {'action': 'no_action'}
    else:
        output = {'action': 'create', 'name': 'uppercase_text',
                  'instructions': '---\nname: uppercase_text\ndescription: Transform public text to uppercase\n---\nUPPERCASE_TEXT: output the uppercase form of input.text.\n',
                  'purpose': 'Synthetic teaching candidate supported by the four read traces.'}
else:
    raise RuntimeError('unsupported synthetic role')
print(json.dumps({'type': 'done', 'output': output}), flush=True)
