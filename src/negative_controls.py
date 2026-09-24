"""Intentionally invalid semantics used only as negative controls.

These routines never produce accepted certificates and are not imported by the
checker. They expose why independent sampling, chronological coupling, and
premature forgetting are not the declared immutable-input semantics.
"""
from collections import deque
from itertools import product
from model import State, future, tick
from producer import extensions
from oracle import observations


def forget_everything(pair):
    l,r = pair["left"],pair["right"]
    fl,fr = future(l),future(r)
    root = State(l["start"],r["start"],0,0,())
    todo = deque([(root,0)])
    seen = {root}
    while todo:
        s,d = todo.popleft()
        for t,_ in extensions(l,r,s,fl,fr):
            t = State(t.left,t.right,t.out_left,t.out_right,())
            if t.bad:
                return d+1
            if t not in seen:
                seen.add(t); todo.append((t,d+1))
    return None


def chronological(pair):
    """Feed the same j-th bit to the j-th read, regardless of input identity."""
    l,r = pair["left"],pair["right"]
    h = max(len(l["nodes"]),len(r["nodes"]))
    def run(c,stream):
        p,read_index,mask = c["start"],0,0
        out = [0]
        for _ in range(h):
            node = c["nodes"][p]
            values = {}
            if node["op"] == "read":
                values[node["key"]] = stream[read_index]
                read_index += 1
            p,mask = tick(c,p,mask,values)
            out.append(mask)
        return out
    best = None
    for stream in product((0,1),repeat=h):
        a,b = run(l,stream),run(r,stream)
        for t,(u,v) in enumerate(zip(a,b)):
            if u != v:
                best = t if best is None else min(t,best)
                break
    return best


def independent_worlds(pair):
    l,r = pair["left"],pair["right"]
    h = max(len(l["nodes"]),len(r["nodes"]))
    worlds = list(product((0,1),repeat=len(l["keys"])))
    best = None
    for v in worlds:
        for w in worlds:
            a,b = observations(l,v,h),observations(r,w,h)
            for t in range(h+1):
                if a[t] != b[t]:
                    best = t if best is None else min(t,best)
                    break
    return best


def terminal_only(pair):
    l,r = pair["left"],pair["right"]
    h = max(len(l["nodes"]),len(r["nodes"]))
    return all(observations(l,w,h)[-1] == observations(r,w,h)[-1]
               for w in product((0,1),repeat=len(l["keys"])))
