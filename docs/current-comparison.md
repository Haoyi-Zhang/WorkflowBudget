# Source-boundary repair and same-information comparison

The original MIT license and upstream notices remain unchanged. All new fixtures
are owned finite computations with immutable Boolean inputs; no external target,
service, model, dataset, shell, dynamic input-code execution or installation is used.

`workflows.py` now validates and lowers finite source trees iteratively, keeping
each task occurrence distinct. `oracle.py` evaluates their terminal denotation
independently without recursion. A depth-1,000 repeated-test chain has 2,002
controller nodes, within the existing 2,048-node cap. Its all-one world first
returns result zero at budget 1,001; the zero world returns nothing. All six
policies preserve direct/controller traces and pass self-comparison checking.
The source language and its instruction-count cost are unchanged. This is not
general Python compilation or production workflow validation.

CNF constructors/oracles validate exact integer counts and nonzero integer
literals within their declared local blocks before shifting/evaluation. Empty
CNFs and clauses are unchanged. Boolean count coercion and zero-to-minus-one
indexing are rejected. The 64 original exact-budget and eight relevance cases
retain their original outcomes; valid controller parsing guards were already
strict before this repair.

## Reproduce the new bounded comparison

From the artifact root with Python 3.11 or later, choose an absent output directory:

```sh
python3 -B -m unittest discover -s tests -p test_certificates.py -v
python3 -B -m unittest discover -s regressions -p 'test_*.py' -v
python3 -B -O -m unittest discover -s regressions -p 'test_*.py' -v
python3 -B src/cost_comparison.py --out /path/to/fresh/output --repeats 5
```

Set `PYTHONDONTWRITEBYTECODE=1`. Core plus supplemental tests are 30+24=54
methods; the supplied current records pass all 54 in normal and optimized
Python, not merely the optimized supplemental command shown above. Unittests
use explicit assertions. The claim-critical legacy campaign scripts continue
to refuse `-O`; that refusal is retained separately in the private execution log.

The four arms are certificate creation/file reparse/checking; the exact same
projected BFS without predecessor/certificate work; that solver plus validated
structural identity; and complete-world enumeration. All use identical input
files and target the same verdict/global least budget. The solver baseline
shares the product engine and is not an independently implemented checker.

Inputs are fixed before measuring: ten curated cases, four selector cases, four
dead-key cases and three handwritten two-condition source workflows. Five
fixed-order rotated trials give 420 arm executions and 72 actual direct source
traces. Every row retains source preparation/compilation, pair writing, strict
acquisition/validation, search, requested proof I/O/checking, and answer writing.
Both total and pair-boundary times are retained. Fresh invocations maintain no
persistent index. Startup/imports, experiment-row emission, source-library
acquisition and fsync durability are excluded; the execution receipt separately
records whole-process time. These are warm, same-process, local measurements.

The certificate arm's ratio of five-trial median total time to the projected
no-certificate arm ranges from 1.4458384865473344 to 3.1074077129091786. All cases
and slower outcomes remain. On reflexive dead-key inputs the identity arm
explores zero states after validation. Thus the existing full-cache ablation
does not establish superiority over a strong no-certificate solver. Certificates
provide transferable locally checked evidence at a measured extra cost here.

## Current raw evidence and historical separation

`results/revision-2026-10-14/same-information/` contains all 420 rows, all 21
specifications, content-addressed pair/proof JSON, source bindings, 72 traces,
full comparison CSV, summary/source hashes and the actual execution receipt.
Five proof/input copies were byte-identical per case before deduplicating.
`paper/figures/certificate-cost.csv` is a direct projection of these medians.

`results/revision-2026-10-14/tests/` retains both complete 54-method runs and
their exact commands/source bindings. Historical 27- and 30-method records,
all prior campaign data and all original figure inputs are unchanged.

`finite-domains/` repeats all original science domains on Windows CPython
3.12.14: 139,648 comparisons, 131,904 path pairs/657,216 depth sets, 12,384
compiler traces, 8,256 terminal checks, 64 exact-budget constructions, eight
relevance cases, 1,584 liveness nodes and six selector certificate instances.
Every scientific raw row matches retained data; only ablation CPU timing is
excluded. Construction CSVs are byte-equal; the census JSON is field-exact,
with LF/CRLF serialization immaterial. Four top-level unavailable `resource`
imports were omitted by a reviewed private harness; scientific function bodies
and assertions were unchanged. This is not the 22-command Unix wrapper, its
resource limits, fresh Unix RSS/CPU, remote CI or clean-copy delivery acceptance.
The public Unix reproduction route remains `python3 reproduce.py`; the private
Windows harness and its exact read/command scope are for main independent review.

No EnCompass execution or abstraction, native machine-code deployment,
independent workload gain, full literature priority, mechanization or scientific
acceptance follows from these runs.
