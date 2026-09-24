#!/usr/bin/env python3
"""Audit clean-copy reproduction and the non-destructive quick path.

The verifier copies the standalone repository to a temporary directory, runs
quick and full reproduction there, checks that quick mode leaves canonical full
evidence untouched, reconciles deterministic outputs with the delivered tree,
and exercises one producer-to-checker command-line chain. It writes the audit
record to ``results/clean-reproduction.json`` only after every check succeeds.

This is a reproducibility audit, not an independent review or a machine-checked
proof of the mathematical theorems.
"""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any

QUICK_ALLOWED_PREFIX = Path("results/quick")
QUICK_ALLOWED_FILES = {
    Path("results/reproduction-quick.json"),
    Path("results/clean-reproduction.json"),
}
RESULT_EXCLUSIONS = {
    Path("results/reproduction-quick.json"),
    Path("results/reproduction-full.json"),
    Path("results/clean-reproduction.json"),
}
VARIABLE_KEYS = {
    "wall_seconds",
    "cpu_seconds",
    "campaign_cpu_seconds",
    "process_cpu_seconds",
    "child_cpu_seconds",
    "inner_cpu_seconds",
    "instrumented_process_cpu_seconds",
    "instrumented_inner_cpu_seconds",
    "peak_rss_kib",
    "max_child_rss_kib",
    "max_peak_rss_kib",
}


def ignored(path: Path) -> bool:
    return (
        "__pycache__" in path.parts
        or path.suffix in {".pyc", ".pyo"}
        or path == QUICK_ALLOWED_PREFIX
        or QUICK_ALLOWED_PREFIX in path.parents
        or path in QUICK_ALLOWED_FILES
    )


def snapshot(root: Path) -> dict[Path, bytes]:
    out: dict[Path, bytes] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = path.relative_to(root)
            if not ignored(rel):
                out[rel] = path.read_bytes()
    return out


def run(command: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("PYTHONOPTIMIZE", None)
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
        timeout=timeout,
    )


def last_json_object(output: str) -> dict:
    for line in reversed(output.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise AssertionError("command output contained no JSON object")


def normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: normalize(item)
            for key, item in sorted(value.items())
            if key not in VARIABLE_KEYS
        }
    if isinstance(value, list):
        return [normalize(item) for item in value]
    return value


def result_files(root: Path) -> dict[Path, Path]:
    base = root / "results"
    out: dict[Path, Path] = {}
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if rel in RESULT_EXCLUSIONS or QUICK_ALLOWED_PREFIX in rel.parents:
            continue
        if path.suffix in {".json", ".jsonl", ".csv", ".tex"}:
            out[rel] = path
    return out


def compare_result(path_a: Path, path_b: Path) -> None:
    if path_a.suffix == ".json":
        a = normalize(json.loads(path_a.read_text(encoding="utf-8")))
        b = normalize(json.loads(path_b.read_text(encoding="utf-8")))
        if a != b:
            raise AssertionError(f"normalized JSON differs: {path_a.name}")
    elif path_a.suffix == ".jsonl":
        a = [normalize(json.loads(line)) for line in path_a.read_text(encoding="utf-8").splitlines()]
        b = [normalize(json.loads(line)) for line in path_b.read_text(encoding="utf-8").splitlines()]
        if a != b:
            raise AssertionError(f"normalized JSONL differs: {path_a.name}")
    elif path_a.read_bytes() != path_b.read_bytes():
        raise AssertionError(f"deterministic text output differs: {path_a.name}")


def byte_tree(root: Path, dirname: str) -> dict[Path, bytes]:
    base = root / dirname
    return {
        path.relative_to(base): path.read_bytes()
        for path in sorted(base.rglob("*"))
        if path.is_file()
    }


def count_jsonl_rows(files: dict[Path, Path]) -> int:
    return sum(
        len(path.read_text(encoding="utf-8").splitlines())
        for rel, path in files.items()
        if rel.suffix == ".jsonl"
    )


def csv_rows(path: Path) -> int:
    with path.open(newline="", encoding="utf-8") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def prepare_workspace(root: Path, workspace: Path) -> dict:
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)
    clean = workspace / root.name
    shutil.copytree(
        root,
        clean,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    before_quick = snapshot(clean)
    quick_process = run([sys.executable, "reproduce.py", "--quick"], clean, 180)
    quick = last_json_object(quick_process.stdout)
    after_quick = snapshot(clean)
    changed = sorted(
        str(path)
        for path in set(before_quick) | set(after_quick)
        if before_quick.get(path) != after_quick.get(path)
    )
    if changed:
        raise AssertionError(
            "quick mode modified canonical repository files: " + ", ".join(changed)
        )
    if not quick.get("canonical_full_results_preserved"):
        raise AssertionError("quick summary does not record canonical-result preservation")

    optimize_env = os.environ.copy()
    optimize_env["PYTHONDONTWRITEBYTECODE"] = "1"
    optimize_env.pop("PYTHONOPTIMIZE", None)
    optimized = subprocess.run(
        [sys.executable, "-O", "src/pilot.py"],
        cwd=clean,
        env=optimize_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=30,
    )
    expected_marker = "claim-critical validation refuses optimized Python"
    if optimized.returncode == 0 or expected_marker not in optimized.stdout:
        raise AssertionError("optimized Python was not explicitly rejected by a claim-critical script")
    optimization = {
        "all_succeeded": True,
        "optimized_python_rejected": True,
        "exit_code": optimized.returncode,
        "message_marker": expected_marker,
    }

    (workspace / "quick-audit.json").write_text(
        json.dumps(quick, indent=2) + "\n", encoding="utf-8"
    )
    (workspace / "optimization-audit.json").write_text(
        json.dumps(optimization, indent=2) + "\n", encoding="utf-8"
    )
    return quick


def run_full_workspace(root: Path, workspace: Path) -> dict:
    clean = workspace / root.name
    if not clean.is_dir():
        raise AssertionError("workspace is not prepared; run the prepare stage first")
    full_process = run([sys.executable, "reproduce.py"], clean, 240)
    full = last_json_object(full_process.stdout)
    (workspace / "full-audit.json").write_text(
        json.dumps(full, indent=2) + "\n", encoding="utf-8"
    )
    return full


def reconcile_workspace(root: Path, workspace: Path) -> dict:
    clean = workspace / root.name
    quick = json.loads((workspace / "quick-audit.json").read_text(encoding="utf-8"))
    full = json.loads((workspace / "full-audit.json").read_text(encoding="utf-8"))
    optimization = json.loads((workspace / "optimization-audit.json").read_text(encoding="utf-8"))

    source_results = result_files(root)
    clean_results = result_files(clean)
    if set(source_results) != set(clean_results):
        missing = sorted(str(p) for p in set(source_results) - set(clean_results))
        extra = sorted(str(p) for p in set(clean_results) - set(source_results))
        raise AssertionError(f"result file set differs; missing={missing}, extra={extra}")
    for rel in sorted(source_results):
        compare_result(source_results[rel], clean_results[rel])

    for dirname in ("inputs", "certificates"):
        if byte_tree(root, dirname) != byte_tree(clean, dirname):
            raise AssertionError(f"{dirname} differ after clean reproduction")

    with tempfile.TemporaryDirectory(prefix="strategy-certificate-") as cert_td:
        cert_path = Path(cert_td) / "case-04.json"
        producer_process = run(
            [sys.executable, "src/producer.py", "inputs/case-04.json", str(cert_path)],
            clean,
            60,
        )
        checker_process = run(
            [sys.executable, "src/checker.py", "inputs/case-04.json", str(cert_path)],
            clean,
            60,
        )
        producer = last_json_object(producer_process.stdout)
        checker = last_json_object(checker_process.stdout)

    summary = json.loads((clean / "results/summary.json").read_text(encoding="utf-8"))
    paths = json.loads((clean / "results/path-checks.json").read_text(encoding="utf-8"))
    theory = json.loads((clean / "results/theory-checks.json").read_text(encoding="utf-8"))
    tests = json.loads((clean / "results/unit-tests.json").read_text(encoding="utf-8"))
    references = json.loads((clean / "results/reference-checks.json").read_text(encoding="utf-8"))

    suffix_counts = {
        suffix: sum(rel.suffix == suffix for rel in clean_results)
        for suffix in (".json", ".jsonl", ".csv", ".tex")
    }
    raw_rows = count_jsonl_rows(clean_results)
    record = {
        "clean_copy": True,
        "standalone_without_paper": not (clean / "paper").exists(),
        "commands": [
            "python3 reproduce.py --quick",
            "python3 reproduce.py",
            "python3 src/producer.py inputs/case-04.json <temporary-certificate>",
            "python3 src/checker.py inputs/case-04.json <temporary-certificate>",
        ],
        "quick_execution": quick,
        "quick_non_destructive": {
            "canonical_files_changed": 0,
            "diagnostic_directory": "results/quick",
            "all_succeeded": True,
        },
        "optimized_python_guard": optimization,
        "full_execution": full,
        "semantic_reconciliation": {
            "result_files_compared": len(clean_results),
            "json_files": suffix_counts[".json"],
            "jsonl_files": suffix_counts[".jsonl"],
            "csv_files": suffix_counts[".csv"],
            "tex_files": suffix_counts[".tex"],
            "raw_rows": raw_rows,
            "pair_comparisons": summary["certified_oracle_comparisons"],
            "additional_ablation_rows": raw_rows - summary["certified_oracle_comparisons"],
            "report_derivations": 5,
            "theory_derivations": 4,
            "path_reconciliation_pairs": paths["ordered_pairs"],
            "path_depth_set_equalities": paths["depth_set_equalities"],
            "path_state_occurrences_each_representation": paths["reduced_state_occurrences"],
            "path_mismatches": paths["mismatches"],
            "pilot_inputs": len(byte_tree(clean, "inputs")),
            "pilot_certificates": len(byte_tree(clean, "certificates")),
            "all_equal": True,
            "excluded_variable_fields": sorted(VARIABLE_KEYS),
        },
        "unit_tests": tests,
        "claim_critical_totals": {
            "certified_oracle_comparisons": summary["certified_oracle_comparisons"],
            "compiler_traces": summary["compiler_world_traces"],
            "nonpruning_denotation_checks": summary["nonpruning_denotation_world_checks"],
            "exact_budget_reduction_instances": theory["exact_budget_instances"],
            "semantic_reduction_instances": theory["semantic_reduction_instances"],
            "semantic_liveness_nodes": theory["semantic_liveness_nodes"],
            "semantic_liveness_soundness_violations": theory["semantic_liveness_soundness_violations"],
            "semantic_liveness_strict_nodes": theory["semantic_liveness_strict_nodes"],
            "selector_family_instances": theory["selector_family_instances"],
            "path_reconciliation_pairs": paths["ordered_pairs"],
            "path_depth_set_equalities": paths["depth_set_equalities"],
            "path_state_occurrences_each_representation": paths["reduced_state_occurrences"],
            "path_reconciliation_mismatches": paths["mismatches"],
        },
        "reference_integrity": references,
        "cli_demonstration": {
            "producer_exit": producer_process.returncode,
            "checker_exit": checker_process.returncode,
            "kind": "inequivalent" if not producer["equivalent"] else "equivalent",
            "budget": producer["budget"],
            "proof_states": checker["proof_states"],
        },
        "scope": (
            "Clean-copy execution, quick-mode non-mutation, and deterministic semantic-data "
            "agreement; not independent scientific review, live resolution of every scholarly "
            "identifier, proof-assistant verification, or a general proof."
        ),
    }
    output = root / "results/clean-reproduction.json"
    output.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        choices=("all", "prepare", "full", "reconcile"),
        default="all",
        help="split the audit into bounded stages when the host has a short command timeout",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        help="persistent workspace required for prepare/full/reconcile staged execution",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parent

    if args.stage == "all":
        # Execute the same bounded stage entry points used by the documented
        # staged route, so one-shot and staged audits have identical semantics.
        # Keep the temporary clean copy beside the extracted repository when the
        # parent directory is writable.
        temp_parent = root.parent if os.access(root.parent, os.W_OK) else None
        with tempfile.TemporaryDirectory(
            prefix="strategy-equivalence-audit-", dir=temp_parent
        ) as td:
            workspace = Path(td) / "workspace"
            script = str(Path(__file__).resolve())
            stage_env = os.environ.copy()
            stage_env["PYTHONDONTWRITEBYTECODE"] = "1"
            stage_env.pop("PYTHONOPTIMIZE", None)
            for stage, timeout in (("prepare", 180), ("full", 300), ("reconcile", 180)):
                print(f"AUDIT STAGE {stage}", flush=True)
                subprocess.run(
                    [sys.executable, script, "--stage", stage, "--workspace", str(workspace)],
                    cwd=root,
                    env=stage_env,
                    check=True,
                    timeout=timeout,
                )
            record = json.loads(
                (root / "results" / "clean-reproduction.json").read_text(encoding="utf-8")
            )
    else:
        if args.workspace is None:
            parser.error("--workspace is required for staged execution")
        workspace = args.workspace.resolve()
        if args.stage == "prepare":
            quick = prepare_workspace(root, workspace)
            print(json.dumps({"all_succeeded": True, "stage": "prepare", "quick": quick}, sort_keys=True))
            return
        if args.stage == "full":
            full = run_full_workspace(root, workspace)
            print(json.dumps({"all_succeeded": True, "stage": "full", "full": full}, sort_keys=True))
            return
        record = reconcile_workspace(root, workspace)

    print(json.dumps({
        "all_succeeded": True,
        "result_files_compared": record["semantic_reconciliation"]["result_files_compared"],
        "quick_canonical_files_changed": 0,
        "full_commands": record["full_execution"]["commands"],
        "tests": record["unit_tests"]["tests_run"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
