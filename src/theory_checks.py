#!/usr/bin/env python3
"""Bounded executable checks for the paper's complexity and size constructions.

These checks validate concrete reductions and finite family instances. They do
not replace the handwritten general proofs in ``docs/proofs.md``.
"""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import resource
import time

from checker import check
from complexity import (
    cnf_satisfiable,
    exact_budget_pair,
    semantic_irrelevance_controller,
    semantically_relevant_keys,
)
from examples import all_forward_controllers, selector_pair
from model import future
from oracle import decide
from producer import compare


FORMULAS = (
    ("true-0", 0, []),
    ("false-0", 0, [[]]),
    ("x", 1, [[1]]),
    ("not-x", 1, [[-1]]),
    ("contradiction-1", 1, [[1], [-1]]),
    ("tautology-1", 1, [[1, -1]]),
    ("xor-like-2", 2, [[1, 2], [-1, -2]]),
    ("contradiction-2", 2, [[1], [-1, 2], [-2]]),
)



if not __debug__:
    raise SystemExit("claim-critical validation refuses optimized Python; rerun without -O or PYTHONOPTIMIZE")

def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise AssertionError("refusing to write an empty evidence table")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def exact_budget_checks() -> list[dict]:
    rows: list[dict] = []
    for phi_name, phi_n, phi in FORMULAS:
        phi_sat = cnf_satisfiable(phi, phi_n)
        for psi_name, psi_n, psi in FORMULAS:
            psi_sat = cnf_satisfiable(psi, psi_n)
            pair, early, late = exact_budget_pair(phi, psi, phi_n, psi_n)
            cert, info = compare(pair)
            replay = decide(pair)
            accepted = check(pair, cert)
            expected = early if psi_sat else (late if phi_sat else None)
            assert info["budget"] == expected
            assert replay["budget"] == expected
            assert info["equivalent"] == (expected is None)
            assert accepted["accepted"]
            rows.append({
                "phi": phi_name,
                "psi": psi_name,
                "phi_satisfiable": phi_sat,
                "psi_satisfiable": psi_sat,
                "early_budget": early,
                "late_budget": late,
                "expected_least_budget": "equivalent" if expected is None else expected,
                "producer_least_budget": "equivalent" if info["budget"] is None else info["budget"],
                "oracle_least_budget": "equivalent" if replay["budget"] is None else replay["budget"],
                "certificate_accepted": accepted["accepted"],
                "states": info["states"],
            })
    return rows


def semantic_key_checks() -> tuple[list[dict], dict]:
    formula_rows: list[dict] = []
    for name, nkeys, clauses in FORMULAS:
        sat = cnf_satisfiable(clauses, nkeys)
        controller, distinguished = semantic_irrelevance_controller(clauses, nkeys)
        exact = set(semantically_relevant_keys(controller))
        syntactic = {k for k in range(len(controller["keys"]))
                     if (future(controller)[controller["start"]] >> k) & 1}
        assert distinguished in exact if sat else distinguished not in exact
        assert exact <= syntactic
        formula_rows.append({
            "formula": name,
            "satisfiable": sat,
            "distinguished_key": distinguished,
            "distinguished_semantically_relevant": distinguished in exact,
            "semantic_key_count": len(exact),
            "syntactic_future_key_count": len(syntactic),
            "semantic_subset_of_syntactic": exact <= syntactic,
        })

    controllers = list(all_forward_controllers(2, 2)) + list(all_forward_controllers(3, 1))
    node_count = 0
    exact_total = 0
    syntactic_total = 0
    strict_nodes = 0
    violations = 0
    max_gap = 0
    for controller in controllers:
        f = future(controller)
        for node in range(len(controller["nodes"])):
            node_count += 1
            exact = set(semantically_relevant_keys(controller, node))
            syntactic = {k for k in range(len(controller["keys"])) if (f[node] >> k) & 1}
            if not exact <= syntactic:
                violations += 1
            gap = len(syntactic - exact)
            strict_nodes += gap > 0
            exact_total += len(exact)
            syntactic_total += len(syntactic)
            max_gap = max(max_gap, gap)
    assert violations == 0
    census = {
        "controller_encodings": len(controllers),
        "controller_nodes_checked": node_count,
        "soundness_violations": violations,
        "nodes_with_strict_overapproximation": strict_nodes,
        "semantic_key_occurrences": exact_total,
        "syntactic_future_key_occurrences": syntactic_total,
        "maximum_per_node_gap": max_gap,
    }
    return formula_rows, census


def selector_certificate_checks() -> list[dict]:
    rows: list[dict] = []
    for keys in (2, 4, 8):
        for mutation in (False, True):
            pair = selector_pair(keys, mutation)
            cert, info = compare(pair)
            accepted = check(pair, cert)
            assert accepted["accepted"]
            full_by_rank: dict[int, set[tuple[tuple[int, int], ...]]] = {}
            for node in cert["nodes"]:
                state = node["state"]
                memory = tuple(tuple(item) for item in state[4])
                if len(memory) == keys:
                    full_by_rank.setdefault(node["rank"], set()).add(memory)
            bottleneck_rank = min(rank for rank, memories in full_by_rank.items()
                                  if len(memories) == 2 ** keys)
            valuations = len(full_by_rank[bottleneck_rank])
            assert valuations == 2 ** keys
            rows.append({
                "data_keys": keys,
                "mutation": mutation,
                "equivalent": info["equivalent"],
                "least_budget": "equivalent" if info["budget"] is None else info["budget"],
                "certificate_nodes": len(cert["nodes"]),
                "bottleneck_rank": bottleneck_rank,
                "distinct_full_data_valuations": valuations,
                "required_by_family": 2 ** keys,
                "certificate_accepted": accepted["accepted"],
            })
    return rows


def main() -> None:
    if hasattr(os, "sched_setaffinity"):
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_CPU, (35, 35))
    resource.setrlimit(resource.RLIMIT_AS, (3 * 1024**3, 3 * 1024**3))
    start = time.perf_counter()
    cpu = time.process_time()
    out = Path("results")
    out.mkdir(exist_ok=True)

    exact = exact_budget_checks()
    formulas, census = semantic_key_checks()
    selectors = selector_certificate_checks()
    write_csv(out / "exact-budget-reduction.csv", exact)
    write_csv(out / "semantic-key-reduction.csv", formulas)
    write_csv(out / "certificate-lower-bound.csv", selectors)
    (out / "semantic-liveness-census.json").write_text(
        json.dumps(census, indent=2) + "\n", encoding="utf-8")

    usage = resource.getrusage(resource.RUSAGE_SELF)
    summary = {
        "exact_budget_instances": len(exact),
        "semantic_reduction_instances": len(formulas),
        "semantic_liveness_nodes": census["controller_nodes_checked"],
        "semantic_liveness_soundness_violations": census["soundness_violations"],
        "semantic_liveness_strict_nodes": census["nodes_with_strict_overapproximation"],
        "selector_family_instances": len(selectors),
        "failures": 0,
        "workers": 1,
        "wall_seconds": time.perf_counter() - start,
        "campaign_cpu_seconds": time.process_time() - cpu,
        "process_cpu_seconds": usage.ru_utime + usage.ru_stime,
        "peak_rss_kib": usage.ru_maxrss,
        "cpu_cap_seconds": 35,
        "address_space_cap_bytes": 3 * 1024**3,
    }
    (out / "theory-checks.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
