"""Independent full-world, concrete interpreter and small canonical semantics.

Deliberately uses sets and a fresh concrete valuation instead of the producer's
bit masks, projected memory, or paired transition routine. Not a proof assistant.
"""
from __future__ import annotations
from itertools import product


def observations(controller: dict, world: tuple[int,...], horizon: int) -> tuple[frozenset,...]:
    at = controller["start"]
    found: set[int] = set()
    trace = [frozenset()]
    for _ in range(horizon):
        node = controller["nodes"][at]
        op = node["op"]
        if op == "read":
            if world[node["key"]] == 0:
                at = node["zero"]
            else:
                at = node["one"]
        elif op == "step":
            at = node["next"]
        elif op == "emit":
            found.add(node["result"])
            at = node["next"]
        elif op != "halt":
            raise ValueError("unknown operation")
        trace.append(frozenset(found))
    return tuple(trace)


def decide(pair: dict) -> dict:
    l,r = pair["left"],pair["right"]
    n = len(l["keys"])
    if n > 16:
        raise ValueError("exhaustive oracle is limited to sixteen Boolean keys")
    h = max(len(l["nodes"]),len(r["nodes"]))
    best = None
    witness = None
    worlds = 0
    for world in product((0,1),repeat=n):
        worlds += 1
        a,b = observations(l,world,h),observations(r,world,h)
        for t in range(h+1):
            if a[t] != b[t]:
                if best is None or t < best:
                    best,witness = t,world
                break
    return {"equivalent":best is None,"budget":best,
            "world":list(witness) if witness is not None else None,
            "worlds":worlds}


def discovery_vector(controller: dict, world: tuple[int,...]) -> tuple[int,...]:
    traces = observations(controller,world,len(controller["nodes"]))
    # Zero denotes infinity: no result can first appear at time zero.
    result = []
    for r in range(len(controller["results"])):
        result.append(next((i for i,s in enumerate(traces) if r in s),0))
    return tuple(result)


def canonical(controller: dict):
    """Canonical reduced ordered multi-terminal decision tree/DAG signature.

This is a deliberately exhaustive reference implementation, not a new BDD
algorithm, and is used only for small instances. Fixed alphabet order matters.
"""
    n = len(controller["keys"])
    if n > 16:
        raise ValueError("reference canonicalization limited to sixteen inputs")
    def descend(prefix):
        k = len(prefix)
        if k == n:
            return ("leaf",discovery_vector(controller,prefix))
        zero = descend(prefix+(0,))
        one = descend(prefix+(1,))
        return zero if zero == one else ("read",k,zero,one)
    return descend(())


def workflow_observations(workflow, policy, world, horizon):
    """Direct tree interpreter: does not import the workflow compiler."""
    tasks = [workflow]
    results = set()
    trace = [frozenset()]
    for _ in range(horizon):
        if tasks:
            chosen = 0
            if policy == "lifo":
                chosen = len(tasks)-1
            elif policy == "query-first":
                for j,task in enumerate(tasks):
                    if task[0] == "test": chosen = j; break
            elif policy == "emit-first":
                for j,task in enumerate(tasks):
                    if task[0] == "return": chosen = j; break
            task = tasks.pop(chosen)
            if task[0] == "split":
                tasks.append(task[1]); tasks.append(task[2])
            elif task[0] == "test":
                tasks.append(task[2] if world[task[1]] == 0 else task[3])
            elif task[0] == "return":
                results.add(task[1])
                if policy == "first-result": tasks = []
            elif task[0] != "fail":
                raise ValueError("invalid workflow constructor")
            if policy == "beam-one": tasks = tasks[:1]
        trace.append(frozenset(results))
    return tuple(trace)


def workflow_denotation(w, world):
    # Independent iterative traversal of the selected source branches. This
    # avoids imposing Python's call-stack depth on a valid finite workflow.
    pending, found = [w], set()
    while pending:
        term = pending.pop()
        op = term[0]
        if op == "return":
            found.add(term[1])
        elif op == "split":
            pending.extend((term[2], term[1]))
        elif op == "test":
            pending.append(term[2] if world[term[1]] == 0 else term[3])
        elif op != "fail":
            raise ValueError("unknown syntax")
    return frozenset(found)
