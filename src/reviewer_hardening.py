#!/usr/bin/env python3
"""Independent reviewer-facing hardening checks.

This module deliberately uses only subprocess-level contracts for producer/checker
validation.  It does not import the controller semantics, oracle, producer, or
checker.  Its purpose is to test trust boundaries rather than repeat the main
implementation internally.
"""
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Iterable

ARTIFACT = Path(__file__).resolve().parents[1]
SRC = ARTIFACT / "src"
INPUTS = ARTIFACT / "inputs"
RESULTS = ARTIFACT / "results"
PRODUCER = SRC / "producer.py"
CHECKER = SRC / "checker.py"


def run(cmd: list[str], *, cwd: Path = ARTIFACT, timeout: int = 90) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
        env={**os.environ, "PYTHONHASHSEED": "0"},
    )


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def duplicate_first_object_key(raw: bytes) -> bytes:
    text = raw.decode("utf-8")
    obj = json.loads(text)
    if not isinstance(obj, dict) or not obj:
        return b'{"x":0,"x":1}'
    key = next(iter(obj))
    encoded = json.dumps(key, ensure_ascii=False)
    value = json.dumps(obj[key], ensure_ascii=False, separators=(",", ":"))
    pos = text.find("{") + 1
    return (text[:pos] + encoded + ":" + value + "," + text[pos:]).encode("utf-8")


def invalid_variants(raw: bytes) -> list[tuple[str, bytes]]:
    stripped = raw.rstrip()
    variants: list[tuple[str, bytes]] = [
        ("root-null", b"null\n"),
        ("root-array", b"[]\n"),
        ("trailing-garbage", stripped + b" GARBAGE\n"),
        ("truncated", stripped[:-1] if len(stripped) > 1 else b""),
        ("duplicate-key", duplicate_first_object_key(raw)),
        ("nonfinite-nan", b'{"__reviewer_probe__":NaN}\n'),
        ("nonfinite-infinity", b'{"__reviewer_probe__":Infinity}\n'),
        ("invalid-utf8", b"{\xff}\n"),
    ]
    return variants


def check_python_syntax() -> dict[str, Any]:
    files = sorted(SRC.rglob("*.py"))
    # Keep compiler-strength validation (including invalid return/break placement)
    # without compileall's .pyc writes. This fixed validator only compiles the
    # owned sources in memory; it never executes the resulting code objects.
    validator = (
        "import pathlib,sys; "
        "[compile(p.read_text(encoding='utf-8'),str(p),'exec') "
        "for p in sorted(pathlib.Path(sys.argv[1]).rglob('*.py'))]"
    )
    proc = run([sys.executable, "-B", "-c", validator, str(SRC)])
    if proc.returncode != 0:
        raise RuntimeError(f"Python source syntax failed: {proc.stderr}")
    return {"python_files": len(files), "method": "in-memory source compilation", "status": "pass"}


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module.split(".")[0])
    return mods


def check_static_trust_boundary() -> dict[str, Any]:
    files = sorted(SRC.rglob("*.py"))
    forbidden_calls: list[dict[str, str]] = []
    shell_true: list[str] = []
    symlink_escapes: list[str] = []
    secret_like: list[str] = []
    forbidden_names = {"eval", "exec", "compile"}
    secret_re = re.compile(r"(?i)(api[_-]?key|secret|password|token)\s*=\s*['\"][^'\"]{8,}")
    for path in files:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = node.func.id if isinstance(node.func, ast.Name) else ""
                if name in forbidden_names:
                    forbidden_calls.append({"file": str(path.relative_to(ARTIFACT)), "call": name})
                for kw in node.keywords:
                    if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                        shell_true.append(str(path.relative_to(ARTIFACT)))
        if secret_re.search(source):
            secret_like.append(str(path.relative_to(ARTIFACT)))
    for path in ARTIFACT.rglob("*"):
        if path.is_symlink():
            try:
                path.resolve().relative_to(ARTIFACT.resolve())
            except ValueError:
                symlink_escapes.append(str(path.relative_to(ARTIFACT)))
    if forbidden_calls or shell_true or symlink_escapes or secret_like:
        raise RuntimeError(json.dumps({
            "forbidden_calls": forbidden_calls,
            "shell_true": shell_true,
            "symlink_escapes": symlink_escapes,
            "secret_like": secret_like,
        }, indent=2))

    checker_imports = imported_modules(CHECKER)
    path_checker = SRC / "path_checks.py"
    path_imports = imported_modules(path_checker) if path_checker.exists() else set()
    prohibited_checker = sorted(checker_imports & {"producer", "campaign", "oracle", "path_checks"})
    prohibited_path = sorted(path_imports & {"producer", "checker", "oracle", "model", "compiler", "workflow"})
    if prohibited_checker or prohibited_path:
        raise RuntimeError(f"independence violation: checker={prohibited_checker}; path_checks={prohibited_path}")
    return {
        "python_files_scanned": len(files),
        "checker_direct_imports": sorted(checker_imports),
        "path_checker_direct_imports": sorted(path_imports),
        "forbidden_dynamic_execution": 0,
        "shell_true": 0,
        "escaping_symlinks": 0,
        "credential_like_assignments": 0,
        "status": "pass",
    }


def find_inputs(limit: int | None = None) -> list[Path]:
    paths = sorted(INPUTS.glob("*.json"))
    if not paths:
        raise RuntimeError("no JSON inputs found")
    return paths if limit is None else paths[:limit]


def check_cli_determinism(quick: bool) -> dict[str, Any]:
    inputs = find_inputs(1 if quick else None)
    checked = 0
    with tempfile.TemporaryDirectory(prefix="reviewer-determinism-") as td:
        tmp = Path(td)
        for inp in inputs:
            outs = [tmp / f"{inp.stem}-{i}.json" for i in range(3)]
            transcripts: list[tuple[int, str, str]] = []
            for out in outs:
                proc = run([sys.executable, str(PRODUCER), str(inp), str(out)])
                if proc.returncode != 0 or not out.exists():
                    raise RuntimeError(f"producer failed for {inp.name}: {proc.stderr}")
                transcripts.append((proc.returncode, proc.stdout, proc.stderr))
                check = run([sys.executable, str(CHECKER), str(inp), str(out)])
                if check.returncode != 0:
                    raise RuntimeError(f"checker rejected producer output for {inp.name}: {check.stderr}")
            hashes = {sha256(out) for out in outs}
            if len(hashes) != 1 or len(set(transcripts)) != 1:
                raise RuntimeError(f"non-deterministic producer for {inp.name}")
            checked += 1
    return {"inputs": checked, "producer_runs": checked * 3, "byte_identical": True, "status": "pass"}


def check_strict_cli_parsing(quick: bool) -> dict[str, Any]:
    # The malformed byte patterns exercise parser behavior rather than semantic
    # diversity. Keep the check subprocess-level but use one representative
    # valid pair; structural certificate mutations are covered separately by
    # the 30-method unit suite.
    inputs = find_inputs(1)
    total = 0
    accepted = []
    with tempfile.TemporaryDirectory(prefix="reviewer-json-") as td:
        tmp = Path(td)
        for inp in inputs:
            cert = tmp / f"{inp.stem}-valid.json"
            base = run([sys.executable, str(PRODUCER), str(inp), str(cert)])
            if base.returncode != 0:
                raise RuntimeError(f"producer baseline failed: {inp.name}: {base.stderr}")
            input_variants = invalid_variants(inp.read_bytes())
            cert_variants = invalid_variants(cert.read_bytes())
            if quick:
                representative = {"duplicate-key", "nonfinite-nan", "invalid-utf8"}
                input_variants = [item for item in input_variants if item[0] in representative]
                cert_variants = [item for item in cert_variants if item[0] in representative]
            for label, payload in input_variants:
                bad = tmp / f"bad-input-{inp.stem}-{label}.json"
                bad.write_bytes(payload)
                out = tmp / f"out-{inp.stem}-{label}.json"
                proc = run([sys.executable, str(PRODUCER), str(bad), str(out)])
                total += 1
                if proc.returncode == 0:
                    accepted.append(f"producer:{inp.name}:{label}")
            for label, payload in cert_variants:
                bad = tmp / f"bad-cert-{inp.stem}-{label}.json"
                bad.write_bytes(payload)
                proc = run([sys.executable, str(CHECKER), str(inp), str(bad)])
                total += 1
                if proc.returncode == 0:
                    accepted.append(f"checker:{inp.name}:{label}")
    if accepted:
        raise RuntimeError(f"strict parser accepted malformed cases: {accepted}")
    return {
        "representative_inputs": len(inputs),
        "negative_cases": total,
        "unexpected_acceptances": 0,
        "status": "pass",
    }


def _required_json(base: Path, name: str) -> dict[str, Any]:
    path = base / name
    if not path.is_file():
        raise RuntimeError(f"missing required result file: {path.relative_to(ARTIFACT)}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if type(value) is not dict:
        raise RuntimeError(f"result is not a JSON object: {path.relative_to(ARTIFACT)}")
    return value


def _require_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise RuntimeError(f"{label}: expected {expected!r}, found {actual!r}")


def check_result_contract(quick: bool) -> dict[str, Any]:
    """Validate only the evidence families and counts this project actually claims."""
    base = RESULTS / "quick" if quick else RESULTS
    reference = _required_json(base, "reference-checks.json")
    unit = _required_json(base, "unit-tests.json")
    pilot = _required_json(base, "pilot.json")
    theory = _required_json(base, "theory-checks.json")
    paths = _required_json(base, "path-checks.json")
    two_node = _required_json(base, "two-node.json")

    _require_equal(reference.get("all_succeeded"), True, "reference gate")
    _require_equal(reference.get("bibliography_entries"), 69, "bibliography entries")
    _require_equal(reference.get("doi_backed_entries"), 61, "DOI-backed entries")
    _require_equal(reference.get("stable_non_doi_entries"), 8, "stable non-DOI entries")

    _require_equal(unit.get("tests_run"), 30, "unit-test methods")
    _require_equal(unit.get("failures"), 0, "unit-test failures")
    _require_equal(unit.get("errors"), 0, "unit-test errors")
    _require_equal(unit.get("successful"), True, "unit-test success")

    cases = pilot.get("cases")
    _require_equal(len(cases) if type(cases) is list else None, 10, "curated pilot cases")
    if not all(type(row) is dict and row.get("certificate_accepted") is True for row in cases):
        raise RuntimeError("a curated pilot certificate was not accepted")
    _require_equal(
        set(pilot.get("negative_controls", {})),
        {
            "chronological_false_rejection",
            "premature_forgetting_false_rejection",
            "independent_worlds_false_rejection",
            "terminal_only_false_acceptance",
        },
        "negative-control fields",
    )

    expected_theory = {
        "exact_budget_instances": 64,
        "semantic_reduction_instances": 8,
        "semantic_liveness_nodes": 1584,
        "semantic_liveness_soundness_violations": 0,
        "semantic_liveness_strict_nodes": 558,
        "selector_family_instances": 6,
        "failures": 0,
    }
    for field, expected in expected_theory.items():
        _require_equal(theory.get(field), expected, f"theory-checks.{field}")

    expected_path = {
        "scope": "two-node" if quick else "all",
        "ordered_pairs": 2304 if quick else 131904,
        "depth_set_equalities": 9216 if quick else 657216,
        "reduced_state_occurrences": 11854 if quick else 890465,
        "concrete_state_occurrences": 11854 if quick else 890465,
        "mismatches": 0,
    }
    for field, expected in expected_path.items():
        _require_equal(paths.get(field), expected, f"path-checks.{field}")
    _require_equal(two_node.get("cases"), 2304, "two-node cases")
    _require_equal(two_node.get("failures"), 0, "two-node failures")

    lower_path = base / "certificate-lower-bound.csv"
    if not lower_path.is_file():
        raise RuntimeError(f"missing required result file: {lower_path.relative_to(ARTIFACT)}")
    with lower_path.open(newline="", encoding="utf-8") as handle:
        lower_rows = list(csv.DictReader(handle))
    _require_equal(len(lower_rows), 6, "selector-family rows")
    for row in lower_rows:
        k = int(row["data_keys"])
        mutated = row["mutation_r0_to_r1"] == "True"
        expected_budget = str(k + (k.bit_length() - 1) + 2) if mutated else "equivalent"
        expected_keys = ";".join(str(i) for i in range(k))
        expected_assignments = str(2 ** k)
        exact = {
            "family": "reverse-order-dual-result",
            "certificate_kind": "inequivalent" if mutated else "equivalent",
            "expected_least_budget": expected_budget,
            "producer_least_budget": expected_budget,
            "oracle_least_budget": expected_budget,
            "first_full_exposure_rank": str(k // 2),
            "first_full_exposure_controls": f"{k // 2}:{k // 2}",
            "post_data_rank": str(k),
            "post_data_controls": f"{k}:{k}",
            "exact_data_key_set": expected_keys,
            "first_full_exposure_assignments": expected_assignments,
            "post_data_assignments": expected_assignments,
            "required_by_family": expected_assignments,
            "read_orders_checked": "True",
            "json_round_trip_checked": "True",
            "certificate_accepted_after_round_trip": "True",
        }
        for field, expected in exact.items():
            _require_equal(row.get(field), expected, f"selector k={k} mutation={mutated} {field}")

    full_summary = None
    if not quick:
        full_summary = _required_json(base, "summary.json")
        expected_summary = {
            "certified_oracle_comparisons": 139648,
            "compiler_world_traces": 12384,
            "nonpruning_denotation_world_checks": 8256,
            "exact_budget_reduction_instances": 64,
            "semantic_reduction_instances": 8,
            "semantic_liveness_nodes": 1584,
            "selector_family_instances": 6,
            "path_reconciliation_pairs": 131904,
            "path_depth_set_equalities": 657216,
            "path_state_occurrences": 890465,
            "path_reconciliation_mismatches": 0,
            "bibliography_entries": 69,
            "failures": 0,
        }
        for field, expected in expected_summary.items():
            _require_equal(full_summary.get(field), expected, f"summary.{field}")

    return {
        "result_root": str(base.relative_to(ARTIFACT)),
        "reference_entries": 69,
        "unit_tests": 30,
        "pilot_cases": 10,
        "theory_instances": {
            "exact_budget": 64,
            "semantic_reduction": 8,
            "semantic_liveness_nodes": 1584,
            "selector_family": 6,
        },
        "path_pairs": expected_path["ordered_pairs"],
        "path_depth_sets": expected_path["depth_set_equalities"],
        "two_node_pairs": 2304,
        "full_comparisons": None if quick else full_summary["certified_oracle_comparisons"],
        "status": "pass",
    }


def check_latex_data_dependencies(paper_root: Path | None) -> dict[str, Any]:
    if paper_root is None:
        return {"paper_present": False, "status": "not-applicable"}
    paper = paper_root.resolve()
    if not paper.exists():
        raise RuntimeError(f"paper root does not exist: {paper}")
    tex_files = sorted(paper.rglob("*.tex"))
    missing: list[str] = []
    refs = 0
    pattern = re.compile(r"\\(?:input|include|addbibresource)\s*\{([^}]+)\}")
    for tex in tex_files:
        s = tex.read_text(encoding="utf-8", errors="replace")
        for raw in pattern.findall(s):
            if "#" in raw or "\\" in raw:
                continue
            candidate = (tex.parent / raw)
            possibilities = [candidate, candidate.with_suffix(".tex"), candidate.with_suffix(".bib")]
            if not any(p.exists() for p in possibilities):
                missing.append(f"{tex.relative_to(paper)} -> {raw}")
            refs += 1
    if missing:
        raise RuntimeError(f"missing LaTeX dependencies: {missing}")
    return {"paper_present": True, "tex_files": len(tex_files), "checked_dependencies": refs, "missing": 0, "status": "pass"}


def write_outputs(summary: dict[str, Any], *, quick: bool) -> None:
    destination = RESULTS / "quick" if quick else RESULTS
    destination.mkdir(parents=True, exist_ok=True)
    out = destination / "reviewer-hardening.json"
    out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with (destination / "reviewer-hardening.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["check", "status", "details"])
        for name, data in summary["checks"].items():
            writer.writerow([name, data.get("status", ""), json.dumps(data, sort_keys=True, separators=(",", ":"))])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="run a representative subset")
    ap.add_argument("--paper-root", type=Path, default=None, help="optionally check manuscript data dependencies")
    args = ap.parse_args(argv)
    checks: dict[str, Any] = {}
    tasks = (
        ("python_syntax", lambda: check_python_syntax()),
        ("static_trust_boundary", lambda: check_static_trust_boundary()),
        ("cli_determinism", lambda: check_cli_determinism(args.quick)),
        ("strict_cli_parsing", lambda: check_strict_cli_parsing(args.quick)),
        ("result_contract", lambda: check_result_contract(args.quick)),
        ("latex_data_dependencies", lambda: check_latex_data_dependencies(args.paper_root)),
    )
    for name, task in tasks:
        print(f"HARDEN {name}", flush=True)
        checks[name] = task()
    summary = {
        "schema": 1,
        "mode": "quick" if args.quick else "full",
        "checks": checks,
        "status": "pass",
    }
    write_outputs(summary, quick=args.quick)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
