"""Standalone deterministic certificate checker (Python standard library only).

No imports from the producer, model, workflow compiler, or concrete oracle.
Acceptance certifies exactly the supplied explicit controller pair. It does not
certify arbitrary Python, a source compiler, resource models, or a deployed agent.
"""
from __future__ import annotations
import argparse
import itertools
import json
from pathlib import Path
from typing import Any

class Invalid(ValueError):
    pass


def need(condition: bool, message: str) -> None:
    if not condition:
        raise Invalid(message)


def natural(x: Any, lower: int, upper: int) -> bool:
    return type(x) is int and lower <= x <= upper


def read_json(path: str, byte_cap: int) -> Any:
    p = Path(path)
    need(p.stat().st_size <= byte_cap, "JSON file too large")
    # Duplicate object keys are rejected rather than silently overwritten.
    def unique(pairs):
        result = {}
        for key, value in pairs:
            need(key not in result, "duplicate JSON object key")
            result[key] = value
        return result
    def reject_constant(name: str):
        raise Invalid(f"non-finite JSON constant: {name}")
    return json.loads(
        p.read_text(encoding="utf-8"),
        object_pairs_hook=unique,
        parse_constant=reject_constant,
    )


def inspect_controller(c: Any):
    need(type(c) is dict and set(c) == {"keys","results","start","nodes"},
         "malformed controller object")
    for field, cap in (("keys",64),("results",8)):
        a = c[field]
        need(type(a) is list and len(a) <= cap, "alphabet size or type")
        need(all(type(v) is str and 0 < len(v) <= 64 for v in a), "alphabet label")
        need(len(set(a)) == len(a), "duplicate alphabet label")
    ns = c["nodes"]
    need(type(ns) is list and 0 < len(ns) <= 2048, "node count")
    need(natural(c["start"],0,len(ns)-1), "start node")
    adjacency = []
    for i, n in enumerate(ns):
        need(type(n) is dict and type(n.get("op")) is str, "node type")
        op = n["op"]
        if op == "halt":
            need(set(n) == {"op"}, "halt fields")
            targets = []
        elif op == "step":
            need(set(n) == {"op","next"}, "step fields")
            targets = [n["next"]]
        elif op == "emit":
            need(set(n) == {"op","result","next"}, "emit fields")
            need(natural(n["result"],0,len(c["results"])-1), "result index")
            targets = [n["next"]]
        elif op == "read":
            need(set(n) == {"op","key","zero","one"}, "read fields")
            need(natural(n["key"],0,len(c["keys"])-1), "key index")
            targets = [n["zero"],n["one"]]
        else:
            raise Invalid("unknown node operation")
        need(all(natural(t,i+1,len(ns)-1) for t in targets), "non-forward edge")
        adjacency.append(targets)
    # Compute future query sets without using producer code or supplied hints.
    future = [set() for _ in ns]
    for i in range(len(ns)-1,-1,-1):
        if ns[i]["op"] == "read":
            future[i].add(ns[i]["key"])
        for t in adjacency[i]:
            future[i].update(future[t])
    return future


def decode_state(data: Any, left: dict, right: dict, fl, fr):
    need(type(data) is list and len(data) == 5, "state arity")
    p,q,a,b,memory = data
    need(natural(p,0,len(left["nodes"])-1), "left control index")
    need(natural(q,0,len(right["nodes"])-1), "right control index")
    mask_cap = (1 << len(left["results"])) - 1
    need(natural(a,0,mask_cap) and natural(b,0,mask_cap), "result mask")
    need(type(memory) is list and len(memory) <= len(left["keys"]), "memory type")
    parsed = []
    old = -1
    for entry in memory:
        need(type(entry) is list and len(entry) == 2, "memory binding")
        k,v = entry
        need(natural(k,0,len(left["keys"])-1) and k > old, "memory key/order")
        need(natural(v,0,1), "memory value")
        need(k in fl[p] or k in fr[q], "non-live memory binding")
        parsed.append((k,v))
        old = k
    return p,q,a,b,tuple(parsed)


def expected_successors(left, right, fl, fr, state):
    p,q,a,b,memory = state
    nl,nr = left["nodes"][p],right["nodes"][q]
    known = dict(memory)
    requested = set()
    for node in (nl,nr):
        if node["op"] == "read":
            requested.add(node["key"])
    fresh = sorted(requested - known.keys())
    for choices in itertools.product((0,1),repeat=len(fresh)):
        valuation = dict(known)
        for key,val in zip(fresh, choices):
            valuation[key] = val
        controls, observations = [], []
        for node,index,mask in ((nl,p,a),(nr,q,b)):
            op = node["op"]
            if op == "halt":
                controls.append(index)
                observations.append(mask)
            elif op == "read":
                controls.append(node["one"] if valuation[node["key"]] == 1 else node["zero"])
                observations.append(mask)
            elif op == "emit":
                controls.append(node["next"])
                observations.append(mask | (1 << node["result"]))
            else:
                controls.append(node["next"])
                observations.append(mask)
        i,j = controls
        retained = tuple(sorted((key,val) for key,val in valuation.items()
                                if key in fl[i] or key in fr[j]))
        yield i,j,observations[0],observations[1],retained


def replay(c: dict, world: list[int], budget: int) -> int:
    cursor, output = c["start"], 0
    for _ in range(budget):
        n = c["nodes"][cursor]
        if n["op"] == "halt":
            break
        if n["op"] == "read":
            cursor = n["one"] if world[n["key"]] else n["zero"]
        else:
            if n["op"] == "emit":
                output |= 1 << n["result"]
            cursor = n["next"]
    return output


def check(pair: Any, certificate: Any) -> dict:
    need(type(pair) is dict and set(pair) == {"left","right"}, "pair fields")
    l,r = pair["left"],pair["right"]
    fl,fr = inspect_controller(l),inspect_controller(r)
    need(l["keys"] == r["keys"] and l["results"] == r["results"], "alphabet mismatch")
    need(type(certificate) is dict, "certificate object")
    kind = certificate.get("kind")
    need(kind in ("equivalent","inequivalent"), "certificate kind")
    needed = {"kind","nodes"} if kind == "equivalent" else {"kind","nodes","world","budget"}
    need(set(certificate) == needed, "certificate fields")
    entries = certificate["nodes"]
    need(type(entries) is list and 0 < len(entries) <= 200_000, "certificate node count")
    horizon = max(len(l["nodes"]),len(r["nodes"]))
    budget = certificate.get("budget")
    if kind == "inequivalent":
        need(natural(budget,1,horizon), "witness budget")
        w = certificate["world"]
        need(type(w) is list and len(w) == len(l["keys"]), "world dimension")
        need(all(natural(v,0,1) for v in w), "world value")
        need(replay(l,w,budget) != replay(r,w,budget), "world does not distinguish at budget")
    table = {}
    for entry in entries:
        need(type(entry) is dict and set(entry) == {"state","rank"}, "proof record")
        s = decode_state(entry["state"],l,r,fl,fr)
        need(s not in table, "duplicate proof state")
        need(s[2] == s[3], "unsafe proof state")
        cap = horizon if kind == "equivalent" else budget-1
        need(natural(entry["rank"],0,cap), "invalid rank")
        table[s] = entry["rank"]
    root = (l["start"],r["start"],0,0,())
    need(root in table and table[root] == 0, "missing zero-rank root")
    checked = 0
    for state,rank in table.items():
        if kind == "inequivalent" and rank == budget-1:
            continue
        for target in expected_successors(l,r,fl,fr,state):
            need(target in table, "closure omits a compatible successor")
            if kind == "inequivalent":
                need(table[target] <= rank+1, "safe-radius rank increases too fast")
            checked += 1
    return {"accepted": True,"kind":kind,"proof_states":len(table),
            "checked_transitions":checked,"budget":budget}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pair")
    parser.add_argument("certificate")
    args = parser.parse_args()
    try:
        answer = check(read_json(args.pair,8*1024*1024),
                       read_json(args.certificate,64*1024*1024))
        print(json.dumps(answer,sort_keys=True))
        return 0
    except (Invalid,OSError,UnicodeError,json.JSONDecodeError,RecursionError) as exc:
        print(f"REJECT: {exc}")
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
