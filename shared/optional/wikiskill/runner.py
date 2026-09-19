"""Persistent WikiSkill orchestration over real adapters and deterministic graders.

Algorithm 1: baseline validation -> training traces -> maintain -> propose ->
strict validation improvement -> keep/rollback SKILLS ONLY. Final test is frozen
and reserved once. Partial stages resume; ambiguous final-test interruption does
not authorize another test run. No auto-publishing, no self-merging proposals.
"""
from __future__ import annotations

import copy
import dataclasses
import difflib
import json
import random
import re
from pathlib import Path

try:
    from .model import (CannotJudge, Task, Trace, Skill, Proposal, Edit, WikiEdit,
                        ProposerView, apply_wiki, apply_proposal, inject, check_splits,
                        sample_traces, scored)
    from .persistence import RunDB, digest, dumps
except ImportError:
    from model import (CannotJudge, Task, Trace, Skill, Proposal, Edit, WikiEdit,
                       ProposerView, apply_wiki, apply_proposal, inject, check_splits,
                       sample_traces, scored)
    from persistence import RunDB, digest, dumps


def load_dataset(value):
    if not isinstance(value, dict) or value.get('schema') != 1 or not isinstance(value.get('tasks'), list):
        raise CannotJudge('dataset schema must be 1 with a tasks list')
    groups = {'train': [], 'val': [], 'test': []}
    records = {}
    for row in value['tasks']:
        if not isinstance(row, dict) or not {'id', 'group', 'split', 'prompt', 'expected'} <= set(row):
            raise CannotJudge('task needs id, group, split, prompt, expected')
        if (not isinstance(row['id'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,120}', row['id'])
                or not isinstance(row['group'], str) or not row['group']
                or row['split'] not in groups or not isinstance(row['prompt'], str)
                or not isinstance(row['expected'], str)):
            raise CannotJudge('invalid dataset task')
        if row['id'] in records: raise CannotJudge('duplicate task')
        groups[row['split']].append(Task(row['id'], row['group']))
        records[row['id']] = row
    check_splits(groups)
    if len(groups['train']) < 4:
        raise CannotJudge('at least four training traces are needed for the paper inspection contract')
    return groups, records


def exact_grade(task, prediction):
    return float(prediction.strip() == task['expected'].strip())


def parse_proposal(value):
    if not isinstance(value, dict): raise CannotJudge('proposal must be an object')
    allowed = {'action', 'name', 'instructions', 'purpose', 'edits'}
    if set(value) - allowed: raise CannotJudge('unknown proposal fields')
    try:
        edits = tuple(Edit(**e) for e in value.get('edits', []))
        p = Proposal(**{k: v for k, v in value.items() if k != 'edits'}, edits=edits)
        if any(not isinstance(getattr(p, k), str) for k in ('action', 'name', 'instructions', 'purpose')):
            raise ValueError('invalid strings')
        return p
    except (TypeError, ValueError, KeyError) as exc:
        raise CannotJudge('invalid proposal schema') from exc


def parse_wiki(value):
    if not isinstance(value, dict) or set(value) - {'index', 'log', 'create', 'update'}:
        raise CannotJudge('invalid wiki edit fields')
    try:
        create = tuple((name, content) for name, content in value.get('create', []))
        if any(not isinstance(content, str) for _, content in create): raise ValueError('non-text page')
        update = tuple((name, tuple(Edit(**e) for e in edits)) for name, edits in value.get('update', []))
        return WikiEdit(value['index'], value['log'], create, update)
    except (TypeError, ValueError, KeyError) as exc: raise CannotJudge('invalid wiki edit schema') from exc


def skills_from(state):
    return {name: Skill(**entry) for name, entry in state['skills'].items()}


def difference(old, new, name):
    return ''.join(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
                                      fromfile=name + ':active', tofile=name + ':candidate'))


class Runner:
    def __init__(self, output, dataset, adapter, iterations=8, seed=0,
                 grader=exact_grade, grader_id='exact-match-stripped-v1'):
        if type(iterations) is not int or not 0 <= iterations <= 100:
            raise ValueError('iterations must be 0..100')
        self.splits, self.tasks = load_dataset(dataset)
        self.db = RunDB(output)
        self.adapter, self.grader = adapter, grader
        self.config = {'schema': 1, 'dataset_sha256': digest(dataset), 'adapter': adapter.identity,
                       'iterations': iterations, 'seed': seed, 'grader': grader_id,
                       'implementation': 'wikiskill-reference-0.3.0',
                       'synthetic': bool(dataset.get('synthetic', False))}
        self.state = None

    def _evaluate(self, split, skills):
        traces = []
        for task in self.splits[split]:
            record = self.tasks[task.name]
            request = {'task_id': task.name, 'prompt': record['prompt'],
                       'input': copy.deepcopy(record.get('input', {})), 'skill_text': inject(skills)}
            evidence_key = f'{split}:{self.state["iteration"]}:{digest(request)}'
            response = self.db.evidence(evidence_key, request)
            if response is None:
                response = self.adapter.run('inference', request)
                if (not isinstance(response, dict) or not isinstance(response.get('prediction'), str)
                        or not isinstance(response.get('trace'), str)):
                    raise CannotJudge('inference must return prediction and trace, both strings')
                self.db.evidence(evidence_key, request, response)
            score = self.grader(record, response['prediction'])
            traces.append(Trace(task.name, score, response['trace'], response['prediction'], record['expected']))
        return scored(traces, self.splits[split])

    def _save(self, kind, detail=None):
        self.db.save(self.state, kind, detail)

    def _impact(self, record):
        self.state['impacts'].append(record)
        self.state['wiki']['skill-impact.md'] = dumps(self.state['impacts'])

    def run(self):
        with self.db.lock():
            state = self.db.load()
            if state is None:
                state = {'stage': 'baseline', 'iteration': 0, 'config': self.config,
                         'best': None, 'skills': {}, 'wiki': {'index.md': '', 'logs.md': '', 'skill-impact.md': '[]'},
                         'impacts': [], 'train_traces': [], 'candidate': None,
                         'final_test': None, 'final_frozen_skills': None}
            elif state['config'] != self.config:
                raise CannotJudge('resume configuration, dataset, model or grader differs')
            self.state = state
            if state['stage'] == 'complete': return copy.deepcopy(state)
            if state['stage'] in ('final-running', 'final-interrupted'):
                raise CannotJudge('final test was reserved; ambiguous test runs are never silently repeated')
            self._save('run-opened')
            try:
                while state['stage'] != 'complete':
                    self.step()
            except Exception as exc:
                if state['stage'] == 'validate':
                    self._impact({**state['candidate']['record'], 'verdict': 'unjudged', 'score': None,
                                  'error': type(exc).__name__})
                if state['stage'] == 'final-running': state['stage'] = 'final-interrupted'
                self._save('interrupted', {'stage': state['stage'], 'error': type(exc).__name__})
                if isinstance(exc, CannotJudge): raise
                raise CannotJudge('run interrupted; committed progress is retained') from exc
            return copy.deepcopy(state)

    def step(self):
        s = self.state
        active = skills_from(s)
        if s['stage'] == 'baseline':
            _, s['best'] = self._evaluate('val', active)
            s['stage'] = 'train'; self._save('baseline-validated'); return
        if s['stage'] == 'train':
            if s['iteration'] >= self.config['iterations'] or s['best'] == 1.0:
                s['stage'] = 'final-ready'; self._save('evolution-finished'); return
            traces, _ = self._evaluate('train', active)
            s['train_traces'] = [dataclasses.asdict(t) for t in traces]
            s['stage'] = 'maintain'; self._save('training-committed'); return
        if s['stage'] == 'maintain':
            traces = [Trace(**t) for t in s['train_traces']]
            chosen = sample_traces(traces, random.Random(self.config['seed'] + s['iteration']))
            request = {'wiki': copy.deepcopy(s['wiki']), 'iteration': s['iteration'],
                       'traces': [dataclasses.asdict(t) for t in chosen]}
            edit = parse_wiki(self.adapter.run('maintain', request))
            s['wiki'] = apply_wiki(s['wiki'], edit)
            s['stage'] = 'propose'; self._save('wiki-committed'); return
        if s['stage'] == 'propose':
            traces = [Trace(**t) for t in s['train_traces']]
            view = ProposerView(s['wiki'], active, traces, s['impacts'])
            initial = copy.deepcopy(view.initial)
            initial['active_skills'] = [dataclasses.asdict(k) for k in initial['active_skills']]
            initial['trace_paths'] = ['traces/' + t.task for t in traces]
            p = parse_proposal(self.adapter.run('propose', initial, {'read_file': view.read_file}))
            if p.action != 'no_action' and len(view.read_trace_ids) < 4:
                raise CannotJudge('create/patch requires actual read_file calls on four distinct current traces')
            if p.action == 'no_action':
                self._impact({'iteration': s['iteration'], 'action': 'no_action', 'verdict': 'no_action', 'score': None})
                s['iteration'] += 1; s['stage'] = 'train'; self._save('no-action'); return
            candidate = apply_proposal(active, p)
            old, new = active.get(p.name), candidate[p.name]
            record = {'iteration': s['iteration'], 'action': p.action, 'name': p.name, 'best_before': s['best'],
                      'candidate_instructions': new.instructions, 'candidate_purpose': new.purpose,
                      'diff': difference(old.instructions if old else '', new.instructions, p.name + '/SKILL.md'),
                      'purpose_diff': difference(old.purpose if old else '', new.purpose, p.name + '/PURPOSE.md'),
                      'read_trace_ids': sorted(view.read_trace_ids)}
            s['candidate'] = {'skills': {k: dataclasses.asdict(v) for k, v in candidate.items()}, 'record': record}
            s['stage'] = 'validate'; self._save('candidate-staged'); return
        if s['stage'] == 'validate':
            candidate = {k: Skill(**v) for k, v in s['candidate']['skills'].items()}
            _, score = self._evaluate('val', candidate)
            accept = score > s['best']
            self._impact({**s['candidate']['record'], 'verdict': 'accepted' if accept else 'rejected', 'score': score})
            if accept:
                s['skills'] = s['candidate']['skills']; s['best'] = score
            s['candidate'] = None
            s['iteration'] += 1; s['stage'] = 'train'; self._save('validation-gated'); return
        if s['stage'] == 'final-ready':
            s['final_frozen_skills'] = digest(s['skills'])
            s['stage'] = 'final-running'
            self._save('final-test-reserved')
            _, s['final_test'] = self._evaluate('test', active)
            s['stage'] = 'complete'; self._save('final-test-completed'); return
        raise CannotJudge('unknown run stage')

    def export(self, destination, include_experience=False):
        state = self.db.load()
        if not state: raise CannotJudge('no run exists')
        target = Path(destination).absolute()
        if any(p.is_symlink() for p in [target, *target.parents]):
            raise CannotJudge('export destination cannot traverse symlinks')
        target.mkdir(parents=True, exist_ok=False, mode=0o700)
        for name, skill in skills_from(state).items():
            folder = target / 'skills' / name
            folder.mkdir(parents=True)
            (folder / 'SKILL.md').write_text(skill.instructions, encoding='utf-8')
            (folder / 'PURPOSE.md').write_text(skill.purpose, encoding='utf-8')
        report = {'stage': state['stage'], 'iteration': state['iteration'], 'best_validation': state['best'],
                  'final_test': state['final_test'], 'config': state['config'],
                  'frozen_skill_sha256': state['final_frozen_skills'],
                  'accepted': sum(r['verdict'] == 'accepted' for r in state['impacts']),
                  'rejected': sum(r['verdict'] == 'rejected' for r in state['impacts']),
                  'is_published': False, 'raw_traces_exported': False}
        (target / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
        if include_experience:
            for rel, text in state['wiki'].items():
                path = target / 'wiki' / rel; path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding='utf-8')
        return report
