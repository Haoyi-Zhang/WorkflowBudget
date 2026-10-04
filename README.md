# Strategy-equivalence angelic

This standalone, offline research artifact accompanies **Shared-Input Certificates for Budgeted Finite Workflow Search**. It contains an explicit finite-controller semantics, certificate producer, separately implemented checker, exhaustive-world oracle, independent depth-by-depth path reconciler, workflow compiler, deterministic validation campaigns, mathematical proof documentation, and raw claim-linked results.

The artifact is complete for the declared finite model. Its evidence consists of written proofs and finite executable checks without proof-assistant verification; it does not cover deployed agent systems.

## Reproduce

Use Python 3.10 or later on a Unix-like platform that provides Python's `resource` module. No third-party Python package, solver, network connection, GPU, model API, private dataset, account, device, or service is needed. Run from this directory:

```sh
python3 reproduce.py --quick
python3 reproduce.py
```

Quick mode runs six sequential subprocess commands in an isolated temporary copy: the 69-entry bibliography/audit consistency gate, 27 unit tests, ten pilot pairs, all theory-construction checks, a 2,304-pair path-set reconciliation, and 2,304 two-node comparisons. Its diagnostics are copied to `results/quick/`; canonical full-campaign files are not overwritten. Claim-critical campaign/report scripts explicitly reject optimized Python, so `python -O` or `PYTHONOPTIMIZE` cannot silently remove validation assertions. Full mode runs 22 sequential subprocess commands in place: the same gates with the complete 131,904-pair path reconciliation, twelve three-node blocks, the workflow suite, dead-key ablation, selector suite, and report generation. The wrapper stops on a failed command or a 40-second child timeout. Scientific chunks use one worker, a 3 GiB address-space cap, and a 35 CPU-second cap; a cutoff is inconclusive rather than an equivalence verdict.

Expected full semantic totals are:

- 139,648 oracle/certificate pair comparisons with zero disagreements;
- 131,904 complete-small-domain controller pairs whose reduced and concrete projected state sets agree at all 657,216 checked depths (890,465 state occurrences on each side);
- 12,384 direct-workflow/compiler trace checks;
- 8,256 terminal-denotation checks for non-pruning policies;
- 64 exact-budget SAT–UNSAT construction instances;
- 8 semantic-key relevance reductions;
- 1,584 exact-versus-syntactic liveness node checks, with zero containment violations and 558 strict overapproximations;
- 6 selector certificate-family instances;
- 27 passing unit tests; and
- 69 bibliography records matched to a dated audit ledger (61 unique DOI-backed entries and eight stable non-DOI records), with all 69 used by the paper and the 12+5+5 calibration sets enforced.

The eight dead-key ablation arm rows, ten curated pilot pairs, and theory-construction records are not added to the 139,648 comparison count. `results/summary.json`, the raw JSONL/JSON/CSV files, and generated table inputs are the evidence. Runtime and peak memory are expected to vary. The delivered `verify_delivery.py` performs a clean-copy audit: it proves that quick mode changes zero canonical files, executes full mode, reconciles 50 deterministic claim-linked files, and accepts the direct case-04 producer-to-checker example. Exact measurements and excluded variable fields are in `results/clean-reproduction.json`. Hosts with a per-command limit shorter than the complete audit may run the same three bounded stages separately:

```sh
AUDIT_WORKSPACE=../strategy-equivalence-audit-workspace
python3 verify_delivery.py --stage prepare --workspace "$AUDIT_WORKSPACE"
python3 verify_delivery.py --stage full --workspace "$AUDIT_WORKSPACE"
python3 verify_delivery.py --stage reconcile --workspace "$AUDIT_WORKSPACE"
```

`src/reference_checks.py` is deliberately offline. It checks the frozen BibTeX against `results/reference-audit.csv`, rejects duplicate and known-misassigned identifiers, verifies the corrected high-risk records, enforces metadata equality and the calibration quotas, and—when invoked by the paper build in no-write mode—requires exactly the same 69 citation keys in the manuscript without mutating the standalone artifact results. The ledger records the publisher/DOI or stable catalog page consulted on 2026-09-16--17, with eleven high-risk or calibration records rechecked on 2026-09-19. This is stronger than a raw reference count, but it is not live DOI resolution or an exhaustive proof that no relevant paper exists.

To produce and check one certificate directly:

```sh
python3 src/producer.py inputs/case-04.json /tmp/strategy-certificate.json
python3 src/checker.py inputs/case-04.json /tmp/strategy-certificate.json
```

Case 04 separates at budget one. Checker status zero means acceptance under the declared finite semantics; status two means rejection. The command-line programs are local scientific tools, not hardened network services.

## Semantic contract

A controller pair shares ordered Boolean-key and result alphabets. One immutable total world assigns each key once; every read of that key on either side returns the same value. Each non-halt instruction costs one budget tick, halt pads silently, and observations are cumulative result sets. Equivalence means equality for every common world and every budget, not only terminal equality and not comparison under independently sampled worlds.

Controllers are explicit and acyclic. The implementation admits at most 2,048 nodes per side, 64 keys, eight result labels, and 200,000 proof states; the exhaustive oracle separately caps keys at sixteen. These are admission bounds, not theorem parameters. The source language is finite `fail`, `return`, `split`, and immutable `test`. Cycles, mutation, probability, exceptions, scores, ordering/multiplicity, wall-clock cost, model calls, and production services are outside scope.

## Evidence map

| Location | Purpose |
|---|---|
| `src/model.py`, `src/producer.py` | Strict JSON/controller validation, live-memory product, breadth-first certificate production |
| `src/checker.py` | Standalone parser and proof checker; imports no producer/model/compiler/oracle code |
| `src/oracle.py` | Complete-world simulation, least budget, canonical signatures, direct workflow interpreter |
| `src/path_checks.py` | Independent complete-small-domain equality of reduced layers and projections of all concrete common-world runs |
| `src/workflows.py`, `src/examples.py` | Source compiler and deterministic finite generators |
| `src/complexity.py`, `src/theory_checks.py` | Fixed-length reductions, semantic relevance, liveness census, selector certificate checks |
| `tests/test_certificates.py` | 27 deterministic tests, including seventeen malformed-input/certificate cases |
| `src/negative_controls.py` | Four intentionally wrong comparators used only as counterexamples |
| `inputs/`, `certificates/` | Ten readable pilot pairs and accepted positive/negative certificates |
| `results/` | Canonical full rows and derivations, isolated quick diagnostics, plot data, and reproduction records |
| `docs/proofs.md` | Self-contained handwritten proof architecture and limitations |
| `docs/schema.md` | Exact controller, proof-state, and certificate grammar |
| `docs/literature.md` | Complete 12+5+5 theorem-level calibration and non-subsumption matrix |
| `claim_evidence_ledger.csv` | Material claims mapped to proofs, code, experiments, figures, raw results, maturity, and boundary |
| `external_resources.csv` | Scholarly/official dependencies, acquisition mode, integration, and licensing notes |
| `verify_delivery.py` | Clean-copy full regeneration, quick-mode non-mutation, normalized result reconciliation, and CLI-chain audit |

The two complete controller suites enumerate encodings, including unreachable and semantically duplicate syntax; pair count is not workload diversity. The selector suite is a transparent construction check, not held-out data. The cache ablation compares two modes of the new producer and makes no speed claim against existing tools.

## Trust and assistance boundary

Producer, checker, exhaustive oracle, path-set reconciler, workflow interpreter/compiler, and signature oracle use distinct core execution paths, reducing but not eliminating shared conceptual error. The checker recomputes future sets, successors, closure, ranks, and concrete replay; it is handwritten Python rather than a verified kernel.


Original artifact code, generated data, and documentation are under `LICENSE`. No cited paper, external executable baseline, or third-party dataset is vendored. Reproduction is fully offline and contains no fabricated repository address.
