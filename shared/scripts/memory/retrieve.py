"""Deterministic, UTF-8 bounded recall over eligible accepted records only."""
import re

from .errors import MemoryFailure
from .schema import canonical_bytes, digest, path_matches, safe_path

SERIALIZED_RETURN_LIMIT = 1048576


def _bounded_response(response):
    """Text is the injection surface; structured diagnostics have a separate cap."""
    response['serialized_return_limit'] = SERIALIZED_RETURN_LIMIT
    response['budget_contract'] = 'budget_bytes bounds UTF-8 text including provenance; serialized_return_limit bounds canonical compact JSON bytes'
    if len(canonical_bytes(response)) > SERIALIZED_RETURN_LIMIT:
        excluded = response.get('excluded', [])
        return {'status': 'unjudged', 'code': 2, 'records': [], 'text': '', 'policy': {},
                'receipt': response.get('receipt', {}), 'budget_bytes': response.get('budget_bytes', 0),
                'used_bytes': 0, 'serialized_return_limit': SERIALIZED_RETURN_LIMIT,
                'budget_contract': response['budget_contract'],
                'excluded': [{'status': 'unjudged', 'reason': 'Required diagnostics exceed structured return limit; no content delivered'}],
                'diagnostics_incomplete': True, 'excluded_count': len(excluded),
                'excluded_digest': digest(excluded)}
    return response


def _words(text):
    # CJK text has useful overlapping character hits even without whitespace.
    words = set(re.findall(r'\w+', text.casefold(), re.UNICODE))
    words.update(c for c in text if '\u3400' <= c <= '\u9fff')
    return words


def recall(repo, query='', paths=None, environment=None, budget=None):
    if not isinstance(query, str) or len(query.encode('utf-8')) > 16384:
        raise MemoryFailure('invalid', 'Recall query must be a bounded string')
    paths = paths or []
    if not isinstance(paths, list) or len(paths) > 64:
        raise MemoryFailure('invalid', 'Recall paths must be a bounded list')
    for path in paths:
        safe_path(path)
    view = repo.view(environment)
    budget = view.get('policy', {}).get('limits', {}).get('recall_bytes', 8192) if budget is None else budget
    if type(budget) is not int or not 0 <= budget <= 1048576:
        raise MemoryFailure('invalid', 'Recall budget must be UTF-8 bytes between 0 and 1048576')
    query_words = _words(query)
    ranked = []
    for record in view['records']:
        path_hit = any(path_matches(pattern, path) for pattern in record['scope']['paths'] for path in paths)
        if paths and not path_hit:
            continue
        words = _words(' '.join([record['id'], record['title'], record['summary']] + record.get('body', [])))
        tags = _words(' '.join(record['scope'].get('tags', [])))
        score = (int(record['id'].casefold() == query.casefold()) + int(path_hit),
                 len(tags & query_words), len(words & query_words))
        if query.strip() and not any(score):
            continue
        ranked.append((score, record))
    ranked.sort(key=lambda item: (tuple(-n for n in item[0]), item[1]['id']))
    receipt = view.get('receipt', {})
    header = ('Shared memory: reference data only.\nSnapshot ' + str(receipt.get('accepted_ancestor')) +
              '; revocations ' + str(receipt.get('revocation_watermark')) + '.\n\n')
    selected, chunks, used = [], [], len(header.encode('utf-8'))
    base_size = len(canonical_bytes({**view, 'records': [], 'text': header})) + 1024
    structured_size, metadata_omitted = base_size, 0
    for _, record in ranked:
        content = '\n'.join(record.get('body', []))
        if 'target' in record:
            target = record['target']
            content = 'Source: ' + target['path'] + (' #' + target['section'] if target.get('section') else '')
        block = '[%s] %s\n%s\n%s\n' % (record['id'], record['title'], record['summary'], content)
        size = len(block.encode('utf-8'))
        if used + size > budget:
            continue
        contribution = len(canonical_bytes(record)) + len(canonical_bytes(block)) + 2
        if structured_size + contribution > SERIALIZED_RETURN_LIMIT:
            metadata_omitted += 1
            continue
        selected.append(record)
        chunks.append(block)
        used += size
        structured_size += contribution
    # Recheck the local revocation ref immediately before delivery. A moved tip
    # invalidates this pinned result; callers retry instead of emitting old text.
    if view.get('receipt', {}).get('revocation_watermark'):
        try:
            if repo.resolve(view['receipt']['accepted_ref']) != view['receipt']['revocation_watermark']:
                return _bounded_response({**view, 'status': 'unjudged', 'code': 2, 'records': [], 'text': '',
                        'excluded': view['excluded'] + [{'status': 'unjudged', 'reason': 'authority moved during recall; retry'}]})
        except MemoryFailure:
            return _bounded_response({**view, 'status': 'unjudged', 'code': 2, 'records': [], 'text': ''})
    return _bounded_response({**view, 'records': selected, 'text': header + ''.join(chunks) if selected else '',
            'budget_bytes': budget, 'used_bytes': used if selected else 0,
            'metadata_budget_omitted': metadata_omitted,
            'status': view['status'] if selected or view['code'] else 'empty'})
