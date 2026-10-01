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
import tempfile
from itertools import product

from checker import check, read_json
from complexity import (
    cnf_satisfiable,
    exact_budget_pair,
    semantic_irrelevance_controller,
    semantically_relevant_keys,
)
from examples import all_forward_controllers, selector_pair
from model import future, load
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


def _advance_equal_data_reads(controller: dict, count: int) -> tuple[int, list[int]]:
    """Follow ``count`` equal-successor reads and return control plus read keys."""
    control = controller["start"]
    seen: list[int] = []
    for _ in range(count):
        node = controller["nodes"][control]
        assert node["op"] == "read"
        assert node["zero"] == node["one"]
        seen.append(node["key"])
        control = node["zero"]
    return control, seen


def _valuation_layer(
    certificate: dict,
    *,
    rank: int,
    controls: tuple[int, int],
    data_keys: tuple[int, ...],
) -> set[tuple[int, ...]]:
    values: set[tuple[int, ...]] = set()
    for record in certificate["nodes"]:
        state = record["state"]
        if record["rank"] != rank or tuple(state[:2]) != controls:
            continue
        memory = tuple((int(key), int(value)) for key, value in state[4])
        assert tuple(key for key, _ in memory) == data_keys
        assert state[2] == state[3] == 0
        values.add(tuple(value for _, value in memory))
    return values


def selector_certificate_checks() -> list[dict]:
    """Check the exact reverse-order, two-result family used by the artifact.

    The executable family is not self-comparison. The left controller exposes
    ``x_0,...,x_{k-1}``, the right exposes the reverse order, and the mutated
    right controller emits ``r1`` where the left emits ``r0``. We check both the
    earliest full-exposure layer (rank ``k/2``) and the controls reached after
    both data prefixes (rank ``k``), then round-trip the pair and certificate
    through the strict JSON readers before checker acceptance.
    """
    rows: list[dict] = []
    for keys in (2, 4, 8):
        selector_depth = keys.bit_length() - 1
        expected_budget = keys + selector_depth + 2
        expected_assignments = set(product((0, 1), repeat=keys))
        data_key_tuple = tuple(range(keys))
        for mutation in (False, True):
            pair = selector_pair(keys, mutation)

            left_post, left_order = _advance_equal_data_reads(pair["left"], keys)
            right_post, right_order = _advance_equal_data_reads(pair["right"], keys)
            assert left_order == list(range(keys))
            assert right_order == list(reversed(range(keys)))
            assert (left_post, right_post) == (keys, keys)

            exposure_steps = keys // 2
            left_exposed, left_prefix = _advance_equal_data_reads(
                pair["left"], exposure_steps
            )
            right_exposed, right_prefix = _advance_equal_data_reads(
                pair["right"], exposure_steps
            )
            assert left_prefix == list(range(exposure_steps))
            assert right_prefix == list(reversed(range(keys)))[:exposure_steps]
            assert (left_exposed, right_exposed) == (exposure_steps, exposure_steps)

            certificate, info = compare(pair)
            oracle = decide(pair)
            assert info["equivalent"] == (not mutation)
            assert oracle["equivalent"] == (not mutation)
            expected_least = expected_budget if mutation else None
            assert info["budget"] == expected_least
            assert oracle["budget"] == expected_least
            assert certificate["kind"] == ("inequivalent" if mutation else "equivalent")

            full_exposure_values = _valuation_layer(
                certificate,
                rank=exposure_steps,
                controls=(left_exposed, right_exposed),
                data_keys=data_key_tuple,
            )
            post_data_values = _valuation_layer(
                certificate,
                rank=keys,
                controls=(left_post, right_post),
                data_keys=data_key_tuple,
            )
            assert full_exposure_values == expected_assignments
            assert post_data_values == expected_assignments

            with tempfile.TemporaryDirectory(prefix="selector-round-trip-") as td:
                root = Path(td)
                pair_path = root / "pair.json"
                cert_path = root / "certificate.json"
                pair_path.write_text(
                    json.dumps(pair, sort_keys=True, separators=(",", ":")) + "\n",
                    encoding="utf-8",
                )
                cert_path.write_text(
                    json.dumps(certificate, sort_keys=True, separators=(",", ":")) + "\n",
                    encoding="utf-8",
                )
                pair_round_trip = load(pair_path)
                cert_round_trip = read_json(str(cert_path), 64 * 1024 * 1024)
                accepted = check(pair_round_trip, cert_round_trip)
            assert accepted["accepted"]

            rows.append({
                "family": "reverse-order-dual-result",
                "data_keys": keys,
                "selector_keys": selector_depth,
                "mutation_r0_to_r1": mutation,
                "certificate_kind": certificate["kind"],
                "equivalent": info["equivalent"],
                "expected_least_budget": (
                    "equivalent" if expected_least is None else expected_least
                ),
                "producer_least_budget": (
                    "equivalent" if info["budget"] is None else info["budget"]
                ),
                "oracle_least_budget": (
                    "equivalent" if oracle["budget"] is None else oracle["budget"]
                ),
                "certificate_nodes": len(certificate["nodes"]),
                "first_full_exposure_rank": exposure_steps,
                "first_full_exposure_controls": f"{left_exposed}:{right_exposed}",
                "post_data_rank": keys,
                "post_data_controls": f"{left_post}:{right_post}",
                "exact_data_key_set": ";".join(map(str, data_key_tuple)),
                "first_full_exposure_assignments": len(full_exposure_values),
                "post_data_assignments": len(post_data_values),
                "required_by_family": 2 ** keys,
                "read_orders_checked": True,
                "json_round_trip_checked": True,
                "certificate_accepted_after_round_trip": accepted["accepted"],
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
