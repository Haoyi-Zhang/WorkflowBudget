#!/usr/bin/env python3
"""Offline deterministic reproduction from the standalone repository root.

Full mode regenerates the canonical ``results/`` evidence in place. Quick mode
runs in an isolated temporary copy, preserves the canonical full evidence, and
copies only its diagnostic outputs to ``results/quick/``. Commands are
sequential; the timeout applies to each child rather than the whole campaign.
No package installation, network request, external solver, model, or service is
used.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import tempfile
import time

CHILD_TIMEOUT_SECONDS = 40
QUICK_OUTPUTS = (
    "reference-checks.json",
    "unit-tests.json",
    "pilot.json",
    "theory-checks.json",
    "exact-budget-reduction.csv",
    "semantic-key-reduction.csv",
    "certificate-lower-bound.csv",
    "semantic-liveness-census.json",
    "path-checks.json",
    "two-node.json",
    "two-node.jsonl",
)


def commands(quick: bool) -> list[list[str]]:
    out = [
        ["src/reference_checks.py"],
        ["src/run_tests.py"],
        ["src/pilot.py"],
        ["src/theory_checks.py"],
        ["src/path_checks.py", "two-node" if quick else "all"],
        ["src/campaign.py", "two-node"],
    ]
    if not quick:
        out += [["src/campaign.py", "three-node", "--block", str(block)]
                for block in range(12)]
        out += [["src/campaign.py", suite]
                for suite in ("workflows", "stress", "selectors")]
        out += [["src/report.py"]]
    return out


def run_at(run_root: Path, quick: bool) -> dict:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("PYTHONOPTIMIZE", None)
    start = time.perf_counter()
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    for command in commands(quick):
        print("RUN", sys.executable, *command, flush=True)
        subprocess.run(
            [sys.executable, *command],
            cwd=run_root,
            env=env,
            check=True,
            timeout=CHILD_TIMEOUT_SECONDS,
        )
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    return {
        "commands": len(commands(quick)),
        "all_succeeded": True,
        "mode": "quick" if quick else "full",
        "child_cpu_seconds": (
            after.ru_utime + after.ru_stime - before.ru_utime - before.ru_stime
        ),
        "max_child_rss_kib": after.ru_maxrss,
        "wall_seconds": time.perf_counter() - start,
        "workers": 1,
        "canonical_full_results_preserved": bool(quick),
    }


def copy_quick_outputs(run_root: Path, root: Path) -> None:
    destination = root / "results" / "quick"
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    for name in QUICK_OUTPUTS:
        source = run_root / "results" / name
        if not source.is_file():
            raise RuntimeError(f"quick reproduction did not create results/{name}")
        shutil.copy2(source, destination / name)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--quick",
        action="store_true",
        help="run bounded diagnostics in an isolated copy without overwriting full evidence",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parent

    if args.quick:
        with tempfile.TemporaryDirectory(prefix="strategy-equivalence-quick-") as td:
            run_root = Path(td) / root.name
            shutil.copytree(
                root,
                run_root,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
            )
            data = run_at(run_root, True)
            copy_quick_outputs(run_root, root)
    else:
        data = run_at(root, False)

    output = root / "results" / f"reproduction-{data['mode']}.json"
    output.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    if args.quick:
        (root / "results" / "quick" / "reproduction-quick.json").write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps(data, sort_keys=True))


if __name__ == "__main__":
    main()
