"""Explicit opt-in WikiSkill run/resume, reviewed knowledge management, and demo.

Use a private output directory OUTSIDE the repository. --http permits paid API
calls; --command-json executes trusted code only with --allow-exec. No API or
process adapter runs at import, install, status, query, lint, or publish time.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from .adapters import CommandAdapter, HTTPAdapter
    from .model import CannotJudge
    from .persistence import RunDB
    from .runner import Runner
    from .knowledge import Knowledge
except ImportError:
    from adapters import CommandAdapter, HTTPAdapter
    from model import CannotJudge
    from persistence import RunDB
    from runner import Runner
    from knowledge import Knowledge


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest='action', required=True)
    run = sub.add_parser('run', help='start or resume the same frozen run configuration')
    run.add_argument('--dataset', required=True)
    run.add_argument('--out', required=True)
    run.add_argument('--iterations', type=int, default=8)
    run.add_argument('--seed', type=int, default=0)
    adapter = run.add_mutually_exclusive_group(required=True)
    adapter.add_argument('--http', help='explicit chat/completions URL; may spend API quota')
    adapter.add_argument('--command-json', help='JSON argv array, no shell evaluation')
    run.add_argument('--max-calls', type=int, default=200)
    run.add_argument('--model'); run.add_argument('--allow-exec', action='store_true')
    run.add_argument('--key-env', default='WIKISKILL_API_KEY')
    run.add_argument('--export', help='new directory for accepted skills; does not install them')
    run.add_argument('--include-experience', action='store_true', help='private export, never for site publication')
    demo = sub.add_parser('demo'); demo.add_argument('--out', required=True)
    stat = sub.add_parser('status'); stat.add_argument('--out', required=True)
    kb = sub.add_parser('knowledge'); kb.add_argument('--store', required=True)
    ksub = kb.add_subparsers(dest='operation', required=True)
    ingest = ksub.add_parser('ingest'); ingest.add_argument('--id', required=True); ingest.add_argument('--file', required=True)
    draft = ksub.add_parser('draft'); draft.add_argument('--id', required=True); draft.add_argument('--spec', required=True)
    approve = ksub.add_parser('approve'); approve.add_argument('--id', required=True); approve.add_argument('--reviewer', required=True)
    query = ksub.add_parser('query'); query.add_argument('question')
    ksub.add_parser('lint')
    compile_cmd = ksub.add_parser('compile'); compile_cmd.add_argument('--id', required=True)
    compile_cmd.add_argument('--source', action='append', required=True)
    answer_cmd = ksub.add_parser('answer'); answer_cmd.add_argument('question')
    for selected in (compile_cmd, answer_cmd):
        selected.add_argument('--http', required=True); selected.add_argument('--model', required=True)
        selected.add_argument('--key-env', default='WIKISKILL_API_KEY')
        selected.add_argument('--max-calls', type=int, default=20)
    publish = ksub.add_parser('publish'); publish.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == 'status':
            state = RunDB(args.out).load()
            if state is None: raise CannotJudge('no run exists')
            result = {k: state[k] for k in ('stage', 'iteration', 'best', 'final_test', 'final_frozen_skills')}
        elif args.action == 'knowledge':
            knowledge = Knowledge(args.store)
            if args.operation == 'ingest':
                result = knowledge.ingest(args.id, Path(args.file).read_text(encoding='utf-8'), Path(args.file).name)
            elif args.operation == 'draft': result = knowledge.draft(args.id, read_json(args.spec))
            elif args.operation == 'approve': result = knowledge.approve(args.id, args.reviewer)
            elif args.operation in ('compile', 'answer'):
                agent = HTTPAdapter(args.http, args.model, args.key_env, max_requests=args.max_calls)
                result = (knowledge.compile(args.id, args.source, agent) if args.operation == 'compile'
                          else knowledge.answer(args.question, agent))
            elif args.operation == 'query': result = knowledge.query(args.question)
            elif args.operation == 'lint': result = knowledge.lint()
            else: result = knowledge.publish(args.out)
        else:
            if args.action == 'demo':
                home = Path(__file__).resolve().parent
                dataset = read_json(home/'examples'/'demo-dataset.json')
                agent = CommandAdapter([sys.executable, str(home/'examples'/'demo_adapter.py')], allow_exec=True)
                runner = Runner(args.out, dataset, agent, iterations=2)
            else:
                if args.http:
                    if not args.model: raise ValueError('--model is required for HTTP')
                    agent = HTTPAdapter(args.http, args.model, args.key_env, max_requests=args.max_calls)
                else: agent = CommandAdapter(json.loads(args.command_json), allow_exec=args.allow_exec)
                runner = Runner(args.out, read_json(args.dataset), agent, args.iterations, args.seed)
            state = runner.run()
            result = {k: state[k] for k in ('stage', 'iteration', 'best', 'final_test', 'final_frozen_skills')}
            result['synthetic'] = runner.config['synthetic']
            if args.action == 'run' and args.export:
                result['export'] = runner.export(args.export, args.include_experience)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        if args.action == 'knowledge' and args.operation == 'lint' and result['issues']: return 1
        return 0
    except (CannotJudge, ValueError, OSError, KeyError, TypeError) as exc:
        print('could not judge: '+str(exc), file=sys.stderr); return 2


if __name__ == '__main__':
    sys.exit(main())
