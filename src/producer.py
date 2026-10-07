"""Produce closure certificates or shortest-budget separating certificates."""
from __future__ import annotations
import argparse
from collections import deque
from itertools import product
import json
from pathlib import Path
from model import State, future, load, past, successors, tick, validate_pair


def _requested_keys(left: dict, right: dict, p: int, q: int) -> tuple[int, ...]:
    """Controller metadata only; no memory, masks, or answer caching."""
    return tuple(sorted({c["nodes"][at]["key"] for c, at in
                         ((left, p), (right, q))
                         if c["nodes"][at]["op"] == "read"}))


def _extensions_for_reads(left, right, state, fl, fr, reads, erase):
    base = dict(state.memory)
    unknown = [k for k in reads if k not in base]
    for answers in product((0, 1), repeat=len(unknown)):
        values = dict(base)
        values.update(zip(unknown, answers))
        p, a = tick(left, state.left, state.out_left, values)
        q, b = tick(right, state.right, state.out_right, values)
        alive = fl[p] | fr[q]
        memory = tuple(sorted((k, v) for k, v in values.items()
                              if not erase or ((alive >> k) & 1)))
        yield State(p, q, a, b, memory), tuple((k, values[k]) for k in reads)


def extensions(left: dict, right: dict, state: State, fl: list[int], fr: list[int],
               erase: bool = True):
    """Enumerate shared-key assignments, never chronological response streams."""
    reads = _requested_keys(left, right, state.left, state.right)
    yield from _extensions_for_reads(left, right, state, fl, fr, reads, erase)


def compare(pair: dict, *, erase: bool = True, make_certificate: bool = True,
            max_states: int = 200_000) -> tuple[dict | None, dict]:
    left, right = validate_pair(pair)
    fl, fr = future(left), future(right)
    root = State(left["start"], right["start"], 0, 0, ())
    distance = {root: 0}
    previous: dict[State, tuple[State, tuple[tuple[int,int], ...]]] = {}
    queue = deque([root])
    requested = {}
    transitions = 0
    max_memory = 0
    bad = None
    while queue and bad is None:
        state = queue.popleft()
        controls = (state.left, state.right)
        if controls not in requested:
            requested[controls] = _requested_keys(left, right, *controls)
        for target, answers in _extensions_for_reads(
                left, right, state, fl, fr, requested[controls], erase):
            transitions += 1
            max_memory = max(max_memory, len(target.memory))
            if target in distance:
                continue
            if len(distance) >= max_states:
                raise RuntimeError("explicit-state limit reached; no equivalence answer")
            distance[target] = distance[state] + 1
            if make_certificate:
                previous[target] = (state, answers)
            if target.bad:
                bad = target
                break
            queue.append(target)
    result = {"equivalent": bad is None,
              "budget": None if bad is None else distance[bad],
              "states": len(distance), "transitions": transitions,
              "max_retained_keys": max_memory}
    if not make_certificate:
        return None, result
    if not erase:
        raise ValueError("certificate format requires live-input projection")
    if bad is None:
        cert = {"kind": "equivalent", "nodes": [
            {"state": s.encode(), "rank": d} for s, d in distance.items()]}
    else:
        budget = distance[bad]
        world = [0] * len(left["keys"])
        assigned = {}
        cursor = bad
        while cursor != root:
            parent, answers = previous[cursor]
            for key, value in answers:
                if key in assigned and assigned[key] != value:
                    raise AssertionError("forgotten input was resurrected")
                assigned[key] = value
            cursor = parent
        for key, value in assigned.items():
            world[key] = value
        cert = {"kind": "inequivalent", "budget": budget, "world": world,
                "nodes": [{"state": s.encode(), "rank": d}
                          for s, d in distance.items() if d < budget]}
    return cert, result


def static_width(pair: dict) -> int:
    left, right = validate_pair(pair)
    fl, fr = future(left), future(right)
    pl, rl = past(left)
    pr, rr = past(right)
    pending = [(left["start"], right["start"])]
    seen = set(pending)
    bound = 0
    while pending:
        p, q = pending.pop()
        bound = max(bound, ((pl[p] | pr[q]) & (fl[p] | fr[q])).bit_count())
        for i in successors(left, p) or (p,):
            for j in successors(right, q) or (q,):
                if (i, j) not in seen:
                    seen.add((i, j)); pending.append((i, j))
    return bound


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pair")
    parser.add_argument("certificate")
    args = parser.parse_args()
    try:
        certificate, info = compare(load(args.pair))
        Path(args.certificate).write_text(json.dumps(certificate, indent=2)+"\n")
        print(json.dumps(info, sort_keys=True))
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 2
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
