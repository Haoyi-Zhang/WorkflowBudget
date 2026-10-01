"""Deterministic bounded finite validation; run a single chunk per process."""
import argparse
from itertools import product, combinations
import json
import os
from pathlib import Path
import resource
import time
from examples import all_forward_controllers, controller, pair, R, E, selector_pair
from producer import compare, static_width
from checker import check
from oracle import observations, canonical, workflow_observations, workflow_denotation
from workflows import enumerate_workflows, compile_workflow, POLICIES



if not __debug__:
    raise SystemExit("claim-critical validation refuses optimized Python; rerun without -O or PYTHONOPTIMIZE")

def truth(a,b):
    first = None
    for x,y in zip(a,b):
        for t,(u,v) in enumerate(zip(x,y)):
            if u != v:
                first = t if first is None else min(first,t)
                break
    return first


def evaluate(pair, traces, signatures=None):
    cert, info = compare(pair)
    budget = truth(*traces)
    assert info['budget'] == budget and info['equivalent'] == (budget is None)
    accepted = check(pair,cert)
    assert accepted['accepted']
    if signatures is not None:
        assert (signatures[0] == signatures[1]) == info['equivalent']
    width = static_width(pair)
    assert info['max_retained_keys'] <= width
    return {**info,'width':width,'proof_states':accepted['proof_states'],
            'oracle_agrees':True,'certificate_accepted':True}


def finite(m,k,block):
    cs = list(all_forward_controllers(m,k))
    assert len(cs) == (48 if (m,k)==(2,2) else 360)
    worlds = list(product((0,1),repeat=k))
    ts = [[observations(c,w,m+1) for w in worlds] for c in cs]
    sig = [canonical(c) for c in cs]
    lo,hi = (0,len(cs)) if m==2 else (block*30,(block+1)*30)
    assert 0 <= lo < hi <= len(cs)
    for i in range(lo,hi):
        for j in range(len(cs)):
            info=evaluate({'left':cs[i],'right':cs[j]},(ts[i],ts[j]),(sig[i],sig[j]))
            yield {'left_index':i,'right_index':j,'oracle_worlds':len(worlds),**info}


def workflows():
    ws=enumerate_workflows(5)
    assert len(ws)==516
    worlds=list(product((0,1),repeat=2))
    for i,w in enumerate(ws):
        cs=[compile_workflow(w,p,key_count=2,result_count=2) for p in POLICIES]
        h=max(len(c['nodes']) for c in cs)
        ts=[[observations(c,v,h) for v in worlds] for c in cs]
        for j,p in enumerate(POLICIES):
            for z,v in enumerate(worlds):
                assert ts[j][z]==workflow_observations(w,p,v,h)
                if j < 4:
                    assert ts[j][z][-1]==workflow_denotation(w,v)
        for a,b in combinations(range(len(cs)),2):
            info=evaluate({'left':cs[a],'right':cs[b]},(ts[a],ts[b]))
            final_equal=all(x[-1]==y[-1] for x,y in zip(ts[a],ts[b]))
            yield {'workflow_index':i,'left_policy':POLICIES[a],
                   'right_policy':POLICIES[b],'oracle_worlds':4,
                   'terminal_equal':final_equal,'compiler_agrees':True,**info}


def stress():
    for keys in (4,8,12,14):
        expr=E(0)
        for k in reversed(range(keys)): expr=R(k,expr,expr)
        c=controller(expr,keys=keys,results=1)
        p={'left':c,'right':c}
        for erase in (True,False):
            start=time.process_time()
            _,info=compare(p,erase=erase,make_certificate=False)
            assert info['equivalent']
            yield {'keys':keys,'live_projection':erase,'width':static_width(p),
                   'cpu_seconds':time.process_time()-start,**info}


def selectors():
    for keys in (4,8):
        for mutate in (False,True):
            p=selector_pair(keys,mutate)
            worlds=list(product((0,1),repeat=len(p['left']['keys'])))
            h=max(len(c['nodes']) for c in p.values())
            ts=[[observations(p[side],w,h) for w in worlds]
                for side in ('left','right')]
            info=evaluate(p,ts)
            assert info['equivalent'] == (not mutate)
            yield {'data_keys':keys,'mutation':mutate,'oracle_worlds':len(worlds),**info}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('suite',choices=('two-node','three-node','workflows','stress','selectors'))
    parser.add_argument('--block',type=int,default=0)
    args=parser.parse_args()
    if hasattr(os,'sched_setaffinity'):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_CPU,(35,35))
    resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
    start=time.perf_counter(); cpu=time.process_time()
    name=args.suite+(f'-{args.block:02d}' if args.suite=='three-node' else '')
    fn=Path('results')/(name+'.jsonl'); fn.parent.mkdir(exist_ok=True)
    if args.suite=='two-node': it=finite(2,2,0)
    elif args.suite=='three-node': it=finite(3,1,args.block)
    elif args.suite=='workflows': it=workflows()
    elif args.suite=='selectors': it=selectors()
    else: it=stress()
    counts={'cases':0,'equivalent':0,'inequivalent':0,'max_states':0,'max_width':0}
    tmp=fn.with_suffix('.partial')
    with tmp.open('w') as out:
        for row in it:
            out.write(json.dumps(row,sort_keys=True)+'\n')
            counts['cases']+=1
            counts['equivalent' if row['equivalent'] else 'inequivalent']+=1
            counts['max_states']=max(counts['max_states'],row['states'])
            counts['max_width']=max(counts['max_width'],row['width'])
    tmp.replace(fn)
    ru=resource.getrusage(resource.RUSAGE_SELF)
    report={'suite':name,**counts,'failures':0,'workers':1,
            'wall_seconds':time.perf_counter()-start,
            'campaign_cpu_seconds':time.process_time()-cpu,
            'process_cpu_seconds':ru.ru_utime+ru.ru_stime,
            'peak_rss_kib':ru.ru_maxrss,
            'cpu_cap_seconds':35,'address_space_cap_bytes':3*1024**3}
    fn.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))

if __name__=='__main__': main()
