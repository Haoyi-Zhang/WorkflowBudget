#!/usr/bin/env python3
"""Independent finite reconciliation of reduced paths with concrete worlds.

This module intentionally imports none of the producer, checker, model, oracle,
or workflow implementations.  For complete small controller domains it computes
(1) reachable reduced-product state sets and (2) the union of projections of
all concrete common-world executions, then requires exact equality at every
instruction depth.  These are finite implementation checks, not a mechanized
proof of the general path theorem.
"""
from __future__ import annotations

import argparse
from itertools import product
import json
import os
from pathlib import Path
import resource
import time
from typing import Iterable

State = tuple[int, int, int, int, tuple[tuple[int, int], ...]]


def controller_encodings(nonterminal: int, keys: int) -> Iterable[dict]:
    """Enumerate the complete forward-indexed domain used by the campaigns.

    The generator is repeated here rather than imported from the artifact's
    ordinary test infrastructure so that this check has no implementation
    dependency on the product, concrete oracle, or domain generator.
    """
    choices: list[list[dict]] = []
    final = nonterminal
    for source in range(nonterminal):
        later = range(source + 1, final + 1)
        options: list[dict] = []
        for target in later:
            options.append({"op": "step", "next": target})
            options.append({"op": "emit", "result": 0, "next": target})
        for key in range(keys):
            for zero in later:
                for one in later:
                    options.append(
                        {"op": "read", "key": key, "zero": zero, "one": one}
                    )
        choices.append(options)
    for selected in product(*choices):
        yield {
            "keys": [f"x{i}" for i in range(keys)],
            "results": ["r0"],
            "start": 0,
            "nodes": [dict(node) for node in selected] + [{"op": "halt"}],
        }


def future_masks(controller: dict) -> tuple[int, ...]:
    """Compute future-read masks directly from strict forward edges."""
    nodes = controller["nodes"]
    masks = [0] * len(nodes)
    for source in range(len(nodes) - 1, -1, -1):
        node = nodes[source]
        op = node["op"]
        if op == "read":
            masks[source] |= 1 << node["key"]
            targets = (node["zero"], node["one"])
        elif op in ("step", "emit"):
            targets = (node["next"],)
        else:
            targets = ()
        for target in targets:
            masks[source] |= masks[target]
    return tuple(masks)


def controller_trace(controller: dict, world: tuple[int, ...], horizon: int):
    """Return (control, output mask, all keys exposed so far) at each depth."""
    control = controller["start"]
    output = 0
    exposed = 0
    trace = [(control, output, exposed)]
    for _ in range(horizon):
        node = controller["nodes"][control]
        op = node["op"]
        if op == "read":
            key = node["key"]
            exposed |= 1 << key
            control = node["one"] if world[key] else node["zero"]
        elif op == "emit":
            output |= 1 << node["result"]
            control = node["next"]
        elif op == "step":
            control = node["next"]
        elif op != "halt":
            raise AssertionError(f"unexpected operation {op!r}")
        trace.append((control, output, exposed))
    return tuple(trace)


def reduced_successors(left: dict, right: dict, fl, fr, state: State):
    """Independent successor relation for the future-key quotient."""
    p, q, out_left, out_right, memory = state
    left_node = left["nodes"][p]
    right_node = right["nodes"][q]
    known = dict(memory)
    requested = sorted(
        {
            node["key"]
            for node in (left_node, right_node)
            if node["op"] == "read"
        }
    )
    fresh = [key for key in requested if key not in known]

    for answers in product((0, 1), repeat=len(fresh)):
        valuation = dict(known)
        valuation.update(zip(fresh, answers))

        def tick(node: dict, control: int, output: int) -> tuple[int, int]:
            op = node["op"]
            if op == "halt":
                return control, output
            if op == "read":
                return (
                    node["one"] if valuation[node["key"]] else node["zero"],
                    output,
                )
            if op == "emit":
                return node["next"], output | (1 << node["result"])
            if op == "step":
                return node["next"], output
            raise AssertionError(f"unexpected operation {op!r}")

        p_next, out_left_next = tick(left_node, p, out_left)
        q_next, out_right_next = tick(right_node, q, out_right)
        live = fl[p_next] | fr[q_next]
        retained = tuple(
            sorted((key, value) for key, value in valuation.items() if live >> key & 1)
        )
        yield p_next, q_next, out_left_next, out_right_next, retained


def reduced_layers(left: dict, right: dict, fl, fr, horizon: int):
    layers: list[frozenset[State]] = [
        frozenset({(left["start"], right["start"], 0, 0, ())})
    ]
    for _ in range(horizon):
        next_layer: set[State] = set()
        for state in layers[-1]:
            next_layer.update(reduced_successors(left, right, fl, fr, state))
        layers.append(frozenset(next_layer))
    return tuple(layers)


def concrete_layers(
    left_traces,
    right_traces,
    worlds: tuple[tuple[int, ...], ...],
    fl,
    fr,
    horizon: int,
):
    layers: list[frozenset[State]] = []
    for depth in range(horizon + 1):
        states: set[State] = set()
        for index, world in enumerate(worlds):
            p, out_left, exposed_left = left_traces[index][depth]
            q, out_right, exposed_right = right_traces[index][depth]
            retained_mask = (exposed_left | exposed_right) & (fl[p] | fr[q])
            memory = tuple(
                (key, world[key])
                for key in range(len(world))
                if retained_mask >> key & 1
            )
            states.add((p, q, out_left, out_right, memory))
        layers.append(frozenset(states))
    return tuple(layers)


def run_domain(nonterminal: int, keys: int) -> dict:
    controllers = tuple(controller_encodings(nonterminal, keys))
    expected = 48 if (nonterminal, keys) == (2, 2) else 360
    if len(controllers) != expected:
        raise AssertionError(
            f"domain ({nonterminal}, {keys}) has {len(controllers)} encodings; "
            f"expected {expected}"
        )
    horizon = nonterminal + 1
    worlds = tuple(product((0, 1), repeat=keys))
    futures = tuple(future_masks(controller) for controller in controllers)
    traces = tuple(
        tuple(controller_trace(controller, world, horizon) for world in worlds)
        for controller in controllers
    )

    pairs = 0
    depth_sets = 0
    reduced_state_occurrences = 0
    concrete_state_occurrences = 0
    max_layer_size = 0
    for left_index, left in enumerate(controllers):
        for right_index, right in enumerate(controllers):
            reduced = reduced_layers(
                left,
                right,
                futures[left_index],
                futures[right_index],
                horizon,
            )
            concrete = concrete_layers(
                traces[left_index],
                traces[right_index],
                worlds,
                futures[left_index],
                futures[right_index],
                horizon,
            )
            if reduced != concrete:
                for depth, (reduced_set, concrete_set) in enumerate(
                    zip(reduced, concrete)
                ):
                    if reduced_set != concrete_set:
                        extra = sorted(reduced_set - concrete_set)[:3]
                        missing = sorted(concrete_set - reduced_set)[:3]
                        raise AssertionError(
                            "path-set mismatch for "
                            f"domain=({nonterminal},{keys}) pair=({left_index},{right_index}) "
                            f"depth={depth}; reduced-only={extra}; concrete-only={missing}"
                        )
                raise AssertionError("layer tuple mismatch without differing layer")
            pairs += 1
            depth_sets += len(reduced)
            reduced_state_occurrences += sum(len(layer) for layer in reduced)
            concrete_state_occurrences += sum(len(layer) for layer in concrete)
            max_layer_size = max(max_layer_size, *(len(layer) for layer in reduced))

    return {
        "nonterminal_nodes": nonterminal,
        "keys": keys,
        "controller_encodings": len(controllers),
        "ordered_pairs": pairs,
        "worlds_per_pair": len(worlds),
        "horizon": horizon,
        "depth_set_equalities": depth_sets,
        "reduced_state_occurrences": reduced_state_occurrences,
        "concrete_state_occurrences": concrete_state_occurrences,
        "maximum_layer_states": max_layer_size,
        "mismatches": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "scope",
        choices=("two-node", "all"),
        nargs="?",
        default="all",
        help="two-node quick check or both complete small domains",
    )
    args = parser.parse_args()

    if hasattr(os, "sched_setaffinity"):
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_CPU, (35, 35))
    resource.setrlimit(resource.RLIMIT_AS, (3 * 1024**3, 3 * 1024**3))

    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    domains = [run_domain(2, 2)]
    if args.scope == "all":
        domains.append(run_domain(3, 1))

    usage = resource.getrusage(resource.RUSAGE_SELF)
    result = {
        "scope": args.scope,
        "domains": domains,
        "ordered_pairs": sum(domain["ordered_pairs"] for domain in domains),
        "depth_set_equalities": sum(
            domain["depth_set_equalities"] for domain in domains
        ),
        "reduced_state_occurrences": sum(
            domain["reduced_state_occurrences"] for domain in domains
        ),
        "concrete_state_occurrences": sum(
            domain["concrete_state_occurrences"] for domain in domains
        ),
        "mismatches": 0,
        "workers": 1,
        "wall_seconds": time.perf_counter() - wall_start,
        "campaign_cpu_seconds": time.process_time() - cpu_start,
        "process_cpu_seconds": usage.ru_utime + usage.ru_stime,
        "peak_rss_kib": usage.ru_maxrss,
        "cpu_cap_seconds": 35,
        "address_space_cap_bytes": 3 * 1024**3,
    }
    output = Path("results/path-checks.json")
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
