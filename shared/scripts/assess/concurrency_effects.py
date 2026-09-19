"""Describe paired task results; never infer effect from an installed mechanism.

Input is an explicit external-run manifest, not an instruction to run its code.
No thresholds, model judge, or sixth total score. Missing runs abstain. A fast
failed run is excluded from the both-successful latency comparison. Statistical
results are descriptive for this observed sample, not causal/general guarantees.
"""
from __future__ import annotations
import argparse
import json
import math
import statistics
import sys
from pathlib import Path

ARMS={'serial','isolated-worktree','uncoordinated','mcp-only','crdt-only','room'}

def number(x):
    return type(x) in (int,float) and math.isfinite(x) and x>=0

def compare(data, baseline='isolated-worktree', treatment='room'):
    if not isinstance(data,dict) or data.get('schema')!=1 or not isinstance(data.get('runs'),list):
        raise ValueError('run manifest schema 1 required')
    if baseline not in ARMS or treatment not in ARMS or baseline==treatment:
        raise ValueError('select two distinct supported arms')
    rows={}; missing=[]
    for row in data['runs']:
        if not isinstance(row,dict) or row.get('arm') not in ARMS: raise ValueError('invalid run arm')
        for key in ('task','model','revision','task_sha256','environment','grader'):
            if not isinstance(row.get(key),str) or not row[key]: raise ValueError('missing stable identity: '+key)
        if type(row.get('seed')) is not int: raise ValueError('seed must be an integer')
        key=tuple(row[k] for k in ('task','model','revision','task_sha256','environment','grader','seed'))
        arm=row['arm']
        if (key,arm) in rows: raise ValueError('duplicate paired observation')
        if row.get('status')=='could-not-run':
            rows[key,arm]=None; missing.append({'task':row['task'],'arm':arm,'status':'could-not-run'}); continue
        if row.get('status')!='measured' or type(row.get('passed')) is not bool or not number(row.get('seconds')):
            raise ValueError('measured runs need boolean passed and finite seconds')
        for field in ('input_tokens','output_tokens','dollars','manual_interventions'):
            if field in row and row[field] is not None and not number(row[field]): raise ValueError('invalid '+field)
        rows[key,arm]=row
    keys={k for k,arm in rows if arm in (baseline,treatment)}
    pairs=[]
    for key in sorted(keys):
        a,b=rows.get((key,baseline)),rows.get((key,treatment))
        if a is None or b is None: missing.append({'task':key[0],'status':'unpaired-or-unavailable'}); continue
        pairs.append((a,b))
    if not pairs: return {'status':'not-measured','score':None,'pairs':0,'missing':missing}
    wins=sum(not a['passed'] and b['passed'] for a,b in pairs)
    losses=sum(a['passed'] and not b['passed'] for a,b in pairs)
    discordant=wins+losses
    p=min(1.0,2*sum(math.comb(discordant,k) for k in range(min(wins,losses)+1))/2**discordant) if discordant else 1.0
    speeds=[a['seconds']/b['seconds'] for a,b in pairs if a['passed'] and b['passed'] and b['seconds']>0]
    costs={}
    for field in ('input_tokens','output_tokens','dollars','manual_interventions'):
        complete=[(a[field],b[field]) for a,b in pairs if a.get(field) is not None and b.get(field) is not None]
        costs[field]={'paired_observations':len(complete),
                      'baseline_sum':sum(a for a,b in complete) if complete else None,
                      'treatment_sum':sum(b for a,b in complete) if complete else None}
    return {'schema':1,'status':'measured-descriptive','score':None,'pairs':len(pairs),
            'baseline':baseline,'treatment':treatment,'synthetic':bool(data.get('synthetic',False)),
            'pass_rate':{'baseline':sum(a['passed'] for a,b in pairs)/len(pairs),
                         'treatment':sum(b['passed'] for a,b in pairs)/len(pairs)},
            'discordant':{'treatment_only':wins,'baseline_only':losses,'exact_two_sided_p':p},
            'both_successful_latency':{'pairs':len(speeds),'median_speedup':statistics.median(speeds) if speeds else None},
            'costs':costs,'missing':missing,'generalization_proven':False}

def main():
    p=argparse.ArgumentParser(description=__doc__.splitlines()[0]); p.add_argument('manifest')
    p.add_argument('--baseline',default='isolated-worktree'); p.add_argument('--treatment',default='room'); args=p.parse_args()
    try:
        result=compare(json.loads(Path(args.manifest).read_text(encoding='utf-8')),args.baseline,args.treatment)
        print(json.dumps(result,indent=2,allow_nan=False)); return 2 if result['status']=='not-measured' else 0
    except (ValueError,OSError,TypeError) as exc:
        print('could not judge concurrency effects: '+str(exc),file=sys.stderr); return 2

if __name__=='__main__': sys.exit(main())
