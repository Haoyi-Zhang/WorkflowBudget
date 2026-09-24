"""Check raw coverage, reconcile summaries, and export neutral data tables."""
import csv
import json
import os
import resource
from pathlib import Path
from collections import Counter, defaultdict



if not __debug__:
    raise SystemExit("claim-critical validation refuses optimized Python; rerun without -O or PYTHONOPTIMIZE")

def read_rows(name):
    with (Path('results')/(name+'.jsonl')).open() as f:
        rows=[json.loads(x) for x in f]
    summary=json.loads((Path('results')/(name+'.json')).read_text())
    assert len(rows)==summary['cases']
    assert sum(x['equivalent'] for x in rows)==summary['equivalent']
    assert all(x['width'] >= x['max_retained_keys'] for x in rows
               if x.get('live_projection',True))
    return rows,summary


def write_csv(name,rows):
    with (Path('results')/name).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def main():
    if hasattr(os, "sched_setaffinity"):
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_CPU, (35,35))
    resource.setrlimit(resource.RLIMIT_AS, (3*1024**3,3*1024**3))
    groups={};resources=[]
    a,r=read_rows('two-node');resources.append(r)
    assert {(x['left_index'],x['right_index']) for x in a} == {(i,j) for i in range(48) for j in range(48)}
    groups['Two-node controllers']=a
    rows=[]
    for b in range(12):
        x,r=read_rows(f'three-node-{b:02d}');rows+=x;resources.append(r)
        assert len(x)==10800
    assert len(rows)==129600 and len({(x['left_index'],x['right_index']) for x in rows})==129600
    assert all(0<=x['left_index']<360 and 0<=x['right_index']<360 for x in rows)
    groups['Three-node controllers']=rows
    w,r=read_rows('workflows');resources.append(r)
    assert len(w)==7740 and len({(x['workflow_index'],x['left_policy'],x['right_policy']) for x in w})==7740
    assert {x['workflow_index'] for x in w}==set(range(516))
    groups['Workflow policy pairs']=w
    s,r=read_rows('selectors');resources.append(r);assert len(s)==4
    groups['Selector pairs']=s
    stress,r=read_rows('stress');resources.append(r);assert len(stress)==8
    for rows in groups.values():
        assert all(x['oracle_agrees'] and x['certificate_accepted'] for x in rows)
    vals=[]
    for name,rows in groups.items():
        vals.append({'suite':name,'pairs':len(rows),'equivalent':sum(x['equivalent'] for x in rows),
                     'inequivalent':sum(not x['equivalent'] for x in rows),
                     'max_states':max(x['states'] for x in rows),
                     'max_width':max(x['width'] for x in rows)})
    write_csv('validation-summary.csv',vals)
    p=defaultdict(Counter)
    for x in w:
        c=p[x['left_policy'],x['right_policy']]
        c['equivalent' if x['equivalent'] else 'inequivalent']+=1
        c['terminal_inequivalent']+=not x['terminal_equal']
    write_csv('policy-summary.csv',[{'left':a,'right':b,'equivalent':c['equivalent'],
               'inequivalent':c['inequivalent'],'terminal_inequivalent':c['terminal_inequivalent']}
               for (a,b),c in p.items()])
    write_csv('cache-stress.csv',[{'keys':k,'live_states':next(x['states'] for x in stress if x['keys']==k and x['live_projection']),
             'full_states':next(x['states'] for x in stress if x['keys']==k and not x['live_projection'])}
             for k in (4,8,12,14)])
    write_csv('selector-summary.csv',[{k:x[k] for k in ('data_keys','mutation','oracle_worlds','equivalent','budget','states','width')} for x in s])
    theory=json.loads(Path('results/theory-checks.json').read_text())
    assert theory['failures']==0
    paths=json.loads(Path('results/path-checks.json').read_text())
    assert paths['scope']=='all' and paths['mismatches']==0
    assert paths['ordered_pairs']==131904 and paths['depth_set_equalities']==657216
    references=json.loads(Path('results/reference-checks.json').read_text())
    assert references['all_succeeded'] and references['bibliography_entries']==69
    total={'certified_oracle_comparisons':sum(x['pairs'] for x in vals),
           'compiler_world_traces':516*6*4,'nonpruning_denotation_world_checks':516*4*4,
           'exact_budget_reduction_instances':theory['exact_budget_instances'],
           'semantic_reduction_instances':theory['semantic_reduction_instances'],
           'semantic_liveness_nodes':theory['semantic_liveness_nodes'],
           'selector_family_instances':theory['selector_family_instances'],
           'path_reconciliation_pairs':paths['ordered_pairs'],
           'path_depth_set_equalities':paths['depth_set_equalities'],
           'path_state_occurrences':paths['reduced_state_occurrences'],
           'path_reconciliation_mismatches':paths['mismatches'],
           'bibliography_entries':references['bibliography_entries'],
           'doi_backed_entries':references['doi_backed_entries'],
           'stable_non_doi_entries':references['stable_non_doi_entries'],
           'reference_checks_passed':references['all_succeeded'],
           'instrumented_process_cpu_seconds':sum(x['process_cpu_seconds'] for x in resources)+theory['process_cpu_seconds']+paths['process_cpu_seconds'],
           'instrumented_inner_cpu_seconds':sum(x['campaign_cpu_seconds'] for x in resources)+theory['campaign_cpu_seconds']+paths['campaign_cpu_seconds'],
           'max_peak_rss_kib':max([x['peak_rss_kib'] for x in resources]+[theory['peak_rss_kib'],paths['peak_rss_kib']]),
           'suite_count':len(resources)+2,'failures':0}
    Path('results/summary.json').write_text(json.dumps(total,indent=2)+'\n')
    lines=['\\begin{tabular}{lrrrr}', '\\toprule',
           'Suite & Pairs & Equal & Unequal & Max. states \\\\', '\\midrule']
    for v in vals:
        lines.append(v['suite']+' & '+' & '.join(f"{v[k]:,}" for k in ('pairs','equivalent','inequivalent','max_states'))+' \\\\')
    lines+=['\\bottomrule','\\end{tabular}']
    Path('results/validation-table.tex').write_text('\n'.join(lines)+'\n')
    print(json.dumps(total))

if __name__=='__main__': main()
