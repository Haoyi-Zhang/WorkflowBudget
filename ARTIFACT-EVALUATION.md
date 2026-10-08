# Artifact evaluation guide

## Scope

The artifact checks the finite, acyclic, shared-input model stated in the paper.
It is designed for deterministic offline evaluation.  It does not claim to be a
production workflow engine or a proof assistant.

Full reproduction requires a Unix-like host with Python's `resource` module;
the scientific CI is configured for Ubuntu 24.04 only. Direct Windows checks
cover the 30-method core suite and two separate six-method regression suites
(requested-key reuse and delivery-baseline selection). Their success is not a
full campaign or clean-copy delivery result, and their method counts are not
added to the retained comparison totals.

## Entry points

```bash
make quick       # representative smoke test; canonical full results are unchanged
make full        # complete reproduction plus reviewer-hardening gate
make hardening   # trust-boundary, determinism, and strict-serialization checks
make delivery    # clean-copy and package-oriented reconciliation
```

The full path runs the 22-command scientific reproduction and then the separate
reviewer-hardening gate.  A nonzero process exit means the evaluation failed.
Do not infer success merely from the presence of precomputed files.

## Expected retained evidence

- exhaustive oracle / producer / checker comparison records;
- import-independent path reconciliation;
- exact Boolean common-world path reconciliation;
- strict checker/producer CLI parsing and deterministic serialization checks;
- source compilation and termination checks;
- exact-budget and semantic-key reduction instances;
- explicit-certificate lower-bound family;
- malformed-input, malformed-certificate, and semantic negative controls;
- reference, trust-boundary, and delivery audits.

## Determinism

Claim-relevant JSON, JSONL, CSV, TeX-table, input, and certificate outputs are
deterministic.  Timing, CPU, peak RSS, temporary paths, and PDF creation metadata
are environment-dependent and are excluded from semantic reconciliation.

## Trust boundary

The independent path reconciler does not import the main model, producer,
checker, oracle, compiler, or workflow interpreter.  The reviewer-hardening
module exercises producer and checker only through their command-line contract.
Python, its standard library, the operating system, and the bundled source files
remain trusted.

## Resource expectations

The complete campaign is intended for a conventional workstation and is much
slower than the quick path.  The retained summary records the measurements from
the reference environment; they are observations, not performance guarantees.
