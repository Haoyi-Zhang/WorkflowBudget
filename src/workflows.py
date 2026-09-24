"""Finite angelic workflow trees and six deterministic search policies.

Workflow syntax: ('fail',), ('return', result), ('split', left, right),
('test', key, zero_child, one_child). Split explores both subtrees unless the
selected policy explicitly prunes. A test reads an immutable external input.
"""
from functools import lru_cache
from itertools import product

POLICIES = ("fifo","lifo","query-first","emit-first","beam-one","first-result")


def enumerate_workflows(max_nodes=5):
    @lru_cache(None)
    def exact(size):
        if size == 1:
            return (("fail",),("return",0),("return",1))
        values = []
        for a in range(1,size-1):
            b = size-1-a
            for l,r in product(exact(a),exact(b)):
                values += [("split",l,r),("test",0,l,r),("test",1,l,r)]
        return tuple(values)
    return [w for n in range(1,max_nodes+1) for w in exact(n)]


def compile_workflow(workflow,policy):
    if policy not in POLICIES:
        raise ValueError("unknown scheduling policy")
    tree = []
    masses = []
    def intern(w):
        here = len(tree)
        tree.append(None); masses.append(0)
        op = w[0]
        if op in ("fail","return"):
            node = {"op":op}
            if op == "return": node["result"] = w[1]
            mass = 1
        else:
            l,r = intern(w[-2]),intern(w[-1])
            node = {"op":op,"left":l,"right":r}
            if op == "test": node["key"] = w[1]
            mass = 1+masses[l]+masses[r]
        tree[here] = node; masses[here] = mass
        return here
    start = (intern(workflow),)
    pending = [start]
    actions = {}
    while pending:
        frontier = pending.pop()
        if frontier in actions: continue
        if not frontier:
            actions[frontier] = {"op":"halt"}
            continue
        index = len(frontier)-1 if policy == "lifo" else 0
        if policy == "query-first":
            index = next((i for i,v in enumerate(frontier) if tree[v]["op"] == "test"),0)
        elif policy == "emit-first":
            index = next((i for i,v in enumerate(frontier) if tree[v]["op"] == "return"),0)
        task = tree[frontier[index]]
        rest = frontier[:index]+frontier[index+1:]
        def finish(extra=()):
            new = rest+extra
            return new[:1] if policy == "beam-one" else new
        op = task["op"]
        if op == "test":
            targets = (finish((task["left"],)),finish((task["right"],)))
            row = {"op":"read","key":task["key"],"zero":targets[0],"one":targets[1]}
        elif op == "split":
            targets = (finish((task["left"],task["right"])),)
            row = {"op":"step","next":targets[0]}
        elif op == "return":
            targets = ((),) if policy == "first-result" else (finish(),)
            row = {"op":"emit","result":task["result"],"next":targets[0]}
        else:
            targets = (finish(),)
            row = {"op":"step","next":targets[0]}
        actions[frontier] = row
        pending.extend(t for t in targets if t not in actions)
    order = sorted(actions,key=lambda f:(-sum(masses[i] for i in f),f))
    names = {f:i for i,f in enumerate(order)}
    nodes = []
    for f in order:
        row = dict(actions[f])
        for key in ("next","zero","one"):
            if key in row: row[key] = names[row[key]]
        nodes.append(row)
    return {"keys":["x0","x1"],"results":["r0","r1"],
            "start":names[start],"nodes":nodes}
