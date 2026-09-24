#!/usr/bin/env python3
"""Complete reproduction entry point, including reviewer-hardening checks."""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def run(cmd: list[str]) -> None:
    completed=subprocess.run(cmd,cwd=ROOT,check=False)
    if completed.returncode:
        raise SystemExit(completed.returncode)

def main() -> int:
    args=sys.argv[1:]
    run([sys.executable,str(ROOT/'_reproduce_core.py'),*args])
    hardening=[sys.executable,str(ROOT/'src/reviewer_hardening.py')]
    if '--quick' in args:
        hardening.append('--quick')
    run(hardening)
    print('Reviewer-hardening gate: PASS (complete entry point)')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
