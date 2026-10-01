"""Finite angelic workflow trees and six deterministic search policies.

Workflow syntax: ('fail',), ('return', result), ('split', left, right),
('test', key, zero_child, one_child). Split explores both subtrees unless the
selected policy explicitly prunes. A test reads an immutable external input.

``compile_workflow`` accepts nonnegative integer key/result indices. By default
it infers the smallest ordered alphabets that contain every index used by the
source tree. Callers may instead supply explicit alphabet sizes; undersized or
out-of-contract sizes are rejected. The generated validation campaign passes
``key_count=2`` and ``result_count=2`` explicitly, so its historic two-key,
two-result domain is unchanged.
"""
from functools import lru_cache
from itertools import product

POLICIES = ("fifo","lifo","query-first","emit-first","beam-one","first-result")
MAX_KEYS = 64
MAX_RESULTS = 8


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


def _source_requirements(workflow):
    """Validate source syntax and return required key/result alphabet sizes."""
    max_key = -1
    max_result = -1

    def visit(term):
        nonlocal max_key, max_result
        if type(term) is not tuple or not term or type(term[0]) is not str:
            raise ValueError("workflow terms must be nonempty tuples")
        op = term[0]
        if op == "fail":
            if len(term) != 1:
                raise ValueError("fail has no operands")
        elif op == "return":
            if len(term) != 2 or type(term[1]) is not int or term[1] < 0:
                raise ValueError("return requires a nonnegative integer result index")
            max_result = max(max_result, term[1])
        elif op == "split":
            if len(term) != 3:
                raise ValueError("split requires two children")
            visit(term[1]); visit(term[2])
        elif op == "test":
            if len(term) != 4 or type(term[1]) is not int or term[1] < 0:
                raise ValueError("test requires a nonnegative integer key index and two children")
            max_key = max(max_key, term[1])
            visit(term[2]); visit(term[3])
        else:
            raise ValueError(f"unknown workflow operation: {op!r}")

    visit(workflow)
    return max_key + 1, max_result + 1


def _alphabet_size(name, supplied, required, cap):
    if supplied is None:
        supplied = required
    if type(supplied) is not int or not 0 <= supplied <= cap:
        raise ValueError(f"{name} must be an integer in [0,{cap}]")
    if supplied < required:
        raise ValueError(f"{name}={supplied} omits an index used by the workflow")
    return supplied


def compile_workflow(workflow, policy, *, key_count=None, result_count=None):
    """Compile one validated finite workflow under a declared policy.

    The mathematical construction permits arbitrary finite key and result
    alphabets. This concrete JSON implementation uses contiguous integer
    indices and the controller schema caps of 64 keys and eight results.
    """
    if policy not in POLICIES:
        raise ValueError("unknown scheduling policy")
    required_keys, required_results = _source_requirements(workflow)
    key_count = _alphabet_size("key_count", key_count, required_keys, MAX_KEYS)
    result_count = _alphabet_size(
        "result_count", result_count, required_results, MAX_RESULTS
    )

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
    return {"keys":[f"x{i}" for i in range(key_count)],
            "results":[f"r{i}" for i in range(result_count)],
            "start":names[start],"nodes":nodes}
