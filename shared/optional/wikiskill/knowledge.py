"""LLM-Wiki-style ingest/query/lint with source versions and reviewed publication.

Separate from the private experience wiki. No model automatically confers truth
or approval. A page cites exact source hashes and line ranges; source changes
make it stale. Contradiction lint covers EXPLICIT structured claim keys, not
arbitrary natural-language truth. Raw sources are never exported to the site.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

try:
    from .persistence import dumps
except ImportError:
    from persistence import dumps

SECRET_PATTERNS = [
    re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b'),
    re.compile(r'\bsk-[A-Za-z0-9_-]{20,}\b'),
    re.compile(r'(?i)\b(?:api[_-]?key|access[_-]?token|password)\s*[:=]\s*["\']?[^\s"\']{12,}'),
]


def redact(text):
    """Conservative known-pattern redaction, NOT a guarantee to remove all secrets/PII."""
    for pattern in SECRET_PATTERNS:
        text = pattern.sub('[REDACTED]', text)
    return text


def safe_identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,119}', value):
        raise ValueError('use a bounded identifier, not a path')
    return value


def text_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def tokens(text):
    words = re.findall(r'[a-z0-9_]+|[\u3400-\u9fff]', text.lower())
    words += [a+b for a,b in zip(words, words[1:]) if len(a)==len(b)==1 and ord(a)>255 and ord(b)>255]
    return set(words)


class Knowledge:
    def __init__(self, directory):
        self.root = Path(directory).absolute()
        if any(p.is_symlink() for p in [self.root, *self.root.parents]):
            raise ValueError('knowledge directory cannot traverse symlinks')
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = self.root / 'knowledge.sqlite3'
        if self.db.is_symlink(): raise ValueError('knowledge database cannot be a symlink')
        with self.connect() as c:
            c.execute('PRAGMA journal_mode=WAL')
            c.executescript('''
                CREATE TABLE IF NOT EXISTS sources(id TEXT NOT NULL, sha TEXT NOT NULL,
                    label TEXT NOT NULL, body TEXT NOT NULL, PRIMARY KEY(id,sha));
                CREATE TABLE IF NOT EXISTS heads(id TEXT PRIMARY KEY, sha TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS pages(id TEXT PRIMARY KEY, version INTEGER NOT NULL,
                    body TEXT NOT NULL, status TEXT NOT NULL, reviewer TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS history(seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    page TEXT NOT NULL, version INTEGER NOT NULL, body TEXT NOT NULL, event TEXT NOT NULL, time REAL NOT NULL);
            ''')
        self.db.chmod(0o600)

    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.db, timeout=10, isolation_level=None)
        c.row_factory = sqlite3.Row
        try: yield c
        finally: c.close()

    def ingest(self, source_id, content, label=''):
        safe_identifier(source_id)
        if not isinstance(content, str) or len(content.encode('utf-8')) > 2_000_000:
            raise ValueError('source must be text no larger than 2 MB')
        if redact(content) != content:
            raise ValueError('source contains a credential-shaped value; redact before ingesting')
        fingerprint = text_hash(content)
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('INSERT OR IGNORE INTO sources VALUES(?,?,?,?)', (source_id, fingerprint, label, content))
            c.execute('INSERT OR REPLACE INTO heads VALUES(?,?)', (source_id, fingerprint))
            c.commit()
        return {'source': source_id, 'sha256': fingerprint, 'lines': len(content.splitlines())}

    def _reference(self, c, ref):
        if not isinstance(ref, dict) or set(ref) != {'source', 'sha256', 'start', 'end'}:
            raise ValueError('evidence needs source, sha256, start, end')
        safe_identifier(ref['source'])
        if (not isinstance(ref['sha256'], str) or not re.fullmatch('[a-f0-9]{64}', ref['sha256'])
                or type(ref['start']) is not int or type(ref['end']) is not int
                or not 1 <= ref['start'] <= ref['end']):
            raise ValueError('invalid evidence range or digest')
        source = c.execute('SELECT * FROM sources WHERE id=? AND sha=?', (ref['source'],ref['sha256'])).fetchone()
        if source is None: raise ValueError('evidence source version does not exist')
        lines = source['body'].splitlines()
        if ref['end'] > len(lines): raise ValueError('evidence range exceeds the source')
        head = c.execute('SELECT sha FROM heads WHERE id=?', (ref['source'],)).fetchone()
        return {'stale': not head or head[0] != ref['sha256'],
                'excerpt': '\n'.join(lines[ref['start']-1:ref['end']]),
                'citation_id': f"{ref['source']}@{ref['sha256']}:{ref['start']}-{ref['end']}"}

    def compile(self, page_id, source_ids, adapter):
        """Explicit model-assisted ingest-to-draft; never grants approval."""
        if not isinstance(source_ids, list) or not source_ids or len(source_ids) > 12:
            raise ValueError('select 1..12 source IDs explicitly')
        with self.connect() as c:
            c.execute('BEGIN')
            sources = []
            for identifier in dict.fromkeys(source_ids):
                safe_identifier(identifier)
                row = c.execute('SELECT s.* FROM sources s JOIN heads h ON h.id=s.id AND h.sha=s.sha WHERE s.id=?', (identifier,)).fetchone()
                if row is None: raise ValueError('source not found')
                sources.append({'source':row['id'], 'sha256':row['sha'], 'lines':row['body'].splitlines()})
            index = [{'page':row['id'],'title':json.loads(row['body'])['title']} for row in c.execute('SELECT id,body FROM pages')]
        spec = adapter.run('compile', {'sources':sources,'page_index':index})
        allowed = {(r['source'],r['sha256']) for r in sources}
        if (not isinstance(spec,dict) or not isinstance(spec.get('evidence'),list)
                or any(not isinstance(r,dict) or (r.get('source'),r.get('sha256')) not in allowed for r in spec['evidence'])):
            raise ValueError('compiled page cites a source outside the supplied set')
        return self.draft(page_id,spec)

    def draft(self, page_id, spec):
        safe_identifier(page_id)
        required = {'title','content','evidence','claims','supersedes'}
        if (not isinstance(spec, dict) or set(spec) != required or not isinstance(spec['title'], str)
                or not isinstance(spec['content'], str) or not spec['content'].strip()
                or not isinstance(spec['evidence'], list) or not spec['evidence']
                or not isinstance(spec['claims'], list) or not isinstance(spec['supersedes'], list)):
            raise ValueError('page needs title/content, nonempty evidence, claims and supersedes lists')
        if redact(dumps(spec)) != dumps(spec): raise ValueError('page contains a credential-shaped value')
        if len(dumps(spec)) > 250_000: raise ValueError('page too large')
        for claim in spec['claims']:
            if (not isinstance(claim, dict) or set(claim) != {'key','value'}
                    or not isinstance(claim['key'], str) or not claim['key']
                    or not isinstance(claim['value'], str)):
                raise ValueError('claims must have string key and value')
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            for ref in spec['evidence']: self._reference(c, ref)
            for old in spec['supersedes']:
                safe_identifier(old)
                if old == page_id or not c.execute('SELECT id FROM pages WHERE id=?', (old,)).fetchone():
                    raise ValueError('supersedes must name another existing page')
                frontier, seen = [old], set()
                while frontier:
                    current = frontier.pop()
                    if current == page_id: raise ValueError('cyclic supersedes graph')
                    if current in seen: continue
                    seen.add(current)
                    row = c.execute('SELECT body FROM pages WHERE id=?', (current,)).fetchone()
                    if row: frontier += json.loads(row[0])['supersedes']
            row = c.execute('SELECT version FROM pages WHERE id=?', (page_id,)).fetchone()
            version = row[0]+1 if row else 1
            c.execute('INSERT OR REPLACE INTO pages VALUES(?,?,?,?,?)', (page_id,version,dumps(spec),'draft',''))
            c.execute('INSERT INTO history(page,version,body,event,time) VALUES(?,?,?,?,?)',
                      (page_id,version,dumps(spec),'draft',time.time()))
            c.commit()
        return {'page': page_id, 'version': version, 'status': 'draft'}

    def approve(self, page_id, reviewer):
        safe_identifier(page_id)
        if not isinstance(reviewer, str) or not reviewer.strip(): raise ValueError('human reviewer identity required')
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT * FROM pages WHERE id=?',(page_id,)).fetchone()
            if row is None: raise ValueError('unknown page')
            spec = json.loads(row['body'])
            if any(self._reference(c,r)['stale'] for r in spec['evidence']): raise ValueError('cannot approve stale evidence')
            c.execute('UPDATE pages SET status="approved",reviewer=? WHERE id=?',(reviewer,page_id))
            for old in spec['supersedes']: c.execute('UPDATE pages SET status="superseded" WHERE id=?',(old,))
            c.execute('INSERT INTO history(page,version,body,event,time) VALUES(?,?,?,?,?)',
                      (page_id,row['version'],dumps({'reviewer':reviewer}),'approved',time.time()))
            c.commit()
        return {'page':page_id,'status':'approved'}

    def lint(self):
        with self.connect() as c:
            c.execute("BEGIN")
            return self._lint(c)

    def _lint(self, c):
        issues, claims = [], {}
        for row in c.execute('SELECT * FROM pages ORDER BY id').fetchall():
            spec = json.loads(row['body'])
            for ref in spec['evidence']:
                try:
                    if self._reference(c,ref)['stale']:
                        issues.append({'page':row['id'],'status':row['status'],'kind':'stale-source','source':ref['source']})
                except ValueError:
                    issues.append({'page':row['id'],'status':row['status'],'kind':'broken-evidence'})
            if redact(row['body']) != row['body']:
                issues.append({'page':row['id'],'status':row['status'],'kind':'credential-shaped-content'})
            if row['status'] == 'approved':
                for claim in spec['claims']:
                    old = claims.setdefault(claim['key'], (claim['value'], row['id']))
                    if old[0] != claim['value']:
                        issues.append({'page':row['id'],'status':'approved','kind':'structured-contradiction',
                                       'other':old[1],'key':claim['key']})
        return {'issues': issues, 'semantic_truth_verified': False}

    def query(self, question, limit=5):
        if not isinstance(question,str) or not question.strip() or type(limit) is not int or not 1<=limit<=20:
            raise ValueError('nonempty question and limit 1..20 required')
        wanted, hits = tokens(question), []
        with self.connect() as c:
            c.execute('BEGIN')
            for row in c.execute('SELECT * FROM pages WHERE status="approved"'):
                spec = json.loads(row['body'])
                refs = [self._reference(c,r) for r in spec['evidence']]
                if any(r['stale'] for r in refs): continue
                overlap = wanted & tokens(spec['title']+' '+spec['content'])
                if not overlap: continue
                hits.append({'page':row['id'],'title':spec['title'],'content':spec['content'],
                             'evidence':[dict(original,**info) for original,info in zip(spec['evidence'],refs)],
                             'rank_overlap':len(overlap),'reviewer':row['reviewer']})
        hits.sort(key=lambda h:(-h['rank_overlap'],h['page']))
        return {'hits':hits[:limit],'untrusted_source_content':True,'retrieval':'lexical-reference-v1'}

    def answer(self, question, adapter):
        evidence = self.query(question)
        result = adapter.run('answer', {'question':question, 'knowledge':evidence})
        allowed = {r['citation_id'] for h in evidence['hits'] for r in h['evidence']}
        if (not isinstance(result,dict) or not isinstance(result.get('answer'),str)
                or not isinstance(result.get('citations'),list)
                or any(not isinstance(x,str) or x not in allowed for x in result['citations'])):
            raise ValueError('model returned an unsupported citation')
        if result['answer'].strip() and evidence['hits'] and not result['citations']:
            raise ValueError('an evidence-based answer must cite the supplied references')
        return result

    def publish(self, directory):
        target = Path(directory)
        if any(p.is_symlink() for p in [target.absolute(), *target.absolute().parents]):
            raise ValueError('publish destination cannot traverse symlinks')
        index = []
        with self.connect() as c:
            c.execute('BEGIN')
            blockers = [i for i in self._lint(c)['issues'] if i['status']=='approved']
            if blockers: raise ValueError('approved knowledge has unresolved lint findings')
            target.mkdir(parents=True,exist_ok=False)
            for row in c.execute('SELECT * FROM pages WHERE status="approved" ORDER BY id'):
                spec = json.loads(row['body'])
                body = '# '+spec['title']+'\n\n'+spec['content']+'\n\n## Evidence\n\n'
                body += '\n'.join('- '+self._reference(c,r)['citation_id'] for r in spec['evidence'])+'\n'
                (target/(row['id']+'.md')).write_text(body,encoding='utf-8')
                index.append({'page':row['id'],'version':row['version'],'reviewer':row['reviewer']})
        (target/'publication.json').write_text(json.dumps({'pages':index,'raw_exported':False},indent=2),encoding='utf-8')
        return {'pages':len(index),'raw_exported':False}
