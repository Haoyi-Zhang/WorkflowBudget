"""Original finite cases; all data are generated locally from explicit syntax."""
from __future__ import annotations
from itertools import product

H = ("halt",)
def R(k, a, b): return ("read", k, a, b)
def E(r, t=H): return ("emit", r, t)
def S(t=H): return ("step", t)


def controller(expression, keys=2, results=2):
    """Hash-cons a finite expression DAG, then number nodes topologically.

    Visit expression objects once by identity and intern shallow instruction
    keys after their children. Hashing a nested tuple directly unfolds shared
    children repeatedly; an equal-successor chain would then cost exponentially
    in its depth even though its explicit controller is linear in that depth.
    The iterative postorder also avoids a Python recursion-depth restriction.
    """
    rows = []
    memo = {}
    resolved = {}
    pending = [(expression, False)]
    while pending:
        e, ready = pending.pop()
        if id(e) in resolved:
            continue
        op = e[0]
        if op == "halt":
            children = ()
        elif op == "read":
            children = (e[2], e[3])
        elif op == "emit":
            children = (e[2],)
        elif op == "step":
            children = (e[1],)
        else:
            raise ValueError("bad finite expression")
        if not ready:
            pending.append((e, True))
            pending.extend((child, False) for child in reversed(children))
            continue
        if op == "halt":
            signature = (op,)
            row = {"op":"halt"}
        elif op == "read":
            z,o = resolved[id(e[2])],resolved[id(e[3])]
            signature = (op, e[1], z, o)
            row = {"op":"read","key":e[1],"zero":z,"one":o}
        elif op == "emit":
            target = resolved[id(e[2])]
            signature = (op, e[1], target)
            row = {"op":"emit","result":e[1],"next":target}
        else:
            target = resolved[id(e[1])]
            signature = (op, target)
            row = {"op":"step","next":target}
        if signature not in memo:
            memo[signature] = len(rows)
            rows.append(row)
        resolved[id(e)] = memo[signature]
    entry = resolved[id(expression)]
    total = len(rows)
    output = []
    for row in reversed(rows):
        item = dict(row)
        for field in ("next","zero","one"):
            if field in item:
                item[field] = total-1-item[field]
        output.append(item)
    return {"keys":[f"x{i}" for i in range(keys)],
            "results":[f"r{i}" for i in range(results)],
            "start":total-1-entry,"nodes":output}


def pair(a,b,keys=2,results=2):
    return {"left":controller(a,keys,results),"right":controller(b,keys,results)}


def curated():
    x,y = 0,1
    reorder_left = R(x,R(y,H,H),R(y,E(0),E(0)))
    reorder_right = R(y,R(x,H,E(0)),R(x,H,E(0)))
    inconsistent = R(x,R(x,H,E(0)),R(x,E(0),H))
    return [
        ("case-01", "reordered immutable reads", pair(reorder_left,reorder_right),True,None),
        ("case-02", "repeated input consistency", pair(inconsistent,S(S(H))),True,None),
        ("case-03", "same-key simultaneous coupling", pair(R(x,H,E(0)),R(x,H,E(0))),True,None),
        ("case-04", "clock is observable", pair(E(0,S(H)),S(E(0))),False,1),
        ("case-05", "result identity is observable", pair(E(0),E(1)),False,1),
        ("case-06", "duplicate outputs are idempotent", pair(E(0,E(0)),E(0,S(H))),True,None),
        ("case-07", "silent suffix is unobservable", pair(E(0,S(S(H))),E(0)),True,None),
        ("case-08", "key identity changes outcome function", pair(R(x,H,E(0)),R(y,H,E(0))),False,2),
        ("case-09", "late output cannot be pruned", pair(S(S(E(0))),S(S(H))),False,3),
        ("case-10", "branch-dependent dead input", pair(R(x,R(y,H,H),R(y,H,H)),S(S(H))),True,None),
    ]


def all_forward_controllers(nonterminal: int, keys: int):
    """Every forward-indexed controller with one output and final halt.

Includes unreachable nodes and equal-target reads. These are encodings, not
isomorphism classes. Each nonterminal is step, emit(0), or read(key).
"""
    choices = []
    for i in range(nonterminal):
        later = range(i+1,nonterminal+1)
        options = []
        for t in later:
            options += [{"op":"step","next":t},
                        {"op":"emit","result":0,"next":t}]
        for k in range(keys):
            for z in later:
                for o in later:
                    options.append({"op":"read","key":k,"zero":z,"one":o})
        choices.append(options)
    for selected in product(*choices):
        yield {"keys":[f"x{i}" for i in range(keys)],"results":["r0"],
               "start":0,"nodes":[dict(v) for v in selected]+[{"op":"halt"}]}


def cnf_controller(clauses, nkeys):
    # Positive literal i+1 means xi; negative literal -(i+1) means not xi.
    success = E(0)
    for clause in reversed(clauses):
        test = H
        for literal in reversed(clause):
            key = abs(literal)-1
            test = R(key,test,success) if literal > 0 else R(key,success,test)
        success = test
    return controller(success,keys=nkeys,results=1)


def selector_pair(keys=4, mutate=False):
    """Two differently ordered data exposures followed by the same selector.

    keys is a power of two. Data reads have equal successors. The later
    selector chooses one data key to re-read; selected true data emits r0.
    A mutation changes the final emitted label in the right controller.
    """
    if keys < 2 or keys & (keys-1):
        raise ValueError('keys must be a power of two')
    depth=keys.bit_length()-1
    def tail(level,first,result):
        if level==depth:
            return R(first,H,E(result))
        half=1 << (depth-level-1)
        return R(keys+level,tail(level+1,first,result),
                 tail(level+1,first+half,result))
    def make(reverse,result):
        expr=tail(0,0,result)
        order=list(range(keys))
        if reverse: order.reverse()
        for k in reversed(order): expr=R(k,expr,expr)
        return controller(expr,keys=keys+depth,results=2)
    return {'left':make(False,0),'right':make(True,1 if mutate else 0)}
