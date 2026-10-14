"""Fixed same-input comparison including acquisition and certificate I/O.

Owned finite fixtures only. No external systems, arbitrary code execution,
network, trained parameters, or performance-optimal baseline claim.
"""
import argparse
import csv
import hashlib
import itertools
import json
from pathlib import Path
import platform
import statistics
import sys
import time

from budget_solver import solve
from checker import check, read_json
from examples import curated, controller, E, R, selector_pair
from model import load, validate_pair
from oracle import decide, observations, workflow_observations, workflow_denotation
from producer import compare
from workflows import compile_workflow, POLICIES

ARMS = ('certificate', 'projected-no-certificate', 'reflexive-no-certificate', 'complete-world')


def source_cases():
    f = ('fail',)
    a, b = ('return', 0), ('return', 1)
    yield 'eligibility', ('split', ('test', 0, f, a), ('test', 1, f, b))
    yield 'repeated-condition', ('test', 0, ('split', a, b), ('test', 0, f, a))
    yield 'duplicate-result', ('split', a, ('split', f, a))


def specifications():
    specs = [dict(name=name, family='curated', index=i) for i, (name, *_) in enumerate(curated())]
    specs += [dict(name=f'selector-{k}-{int(mut)}', family='selector', keys=k, mutation=mut)
              for k in (4, 8) for mut in (False, True)]
    specs += [dict(name=f'dead-{k}', family='dead', keys=k) for k in (4, 8, 12, 14)]
    specs += [dict(name=f'workflow-{name}', family='workflow', index=i, source=source)
              for i, (name, source) in enumerate(source_cases())]
    return specs


def prepare(spec):
    if spec['family'] == 'curated':
        return curated()[spec['index']][2]
    if spec['family'] == 'selector':
        return selector_pair(spec['keys'], spec['mutation'])
    if spec['family'] == 'dead':
        expr = E(0)
        for key in reversed(range(spec['keys'])):
            expr = R(key, expr, expr)
        c = controller(expr, keys=spec['keys'], results=1)
        return dict(left=c, right=c)
    source = tuple_source(spec['source'])
    return dict(left=compile_workflow(source, 'fifo', key_count=2, result_count=2),
                right=compile_workflow(source, 'lifo', key_count=2, result_count=2))


def tuple_source(value):
    return tuple(tuple_source(v) if isinstance(v, (list, tuple)) else v for v in value)


def measure(spec_path, directory, arm):
    directory.mkdir(parents=True)
    start = time.perf_counter()
    spec = load(spec_path)
    pair = prepare(spec)
    pair_path = directory / 'pair.json'
    pair_bytes = (json.dumps(pair, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')
    pair_path.write_bytes(pair_bytes)
    prepared = time.perf_counter()
    pair = load(pair_path)
    validate_pair(pair)
    acquired = time.perf_counter()
    cert_bytes = 0
    check_seconds = 0.0
    cert_io_seconds = 0.0
    if arm == 'certificate':
        cert, answer = compare(pair)
        searched = time.perf_counter()
        cert_path = directory / 'certificate.json'
        encoded = (json.dumps(cert, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')
        cert_path.write_bytes(encoded)
        cert_bytes = len(encoded)
        parsed_pair = read_json(str(pair_path), 8 * 1024**2)
        parsed_cert = read_json(str(cert_path), 64 * 1024**2)
        decoded = time.perf_counter()
        checked = check(parsed_pair, parsed_cert)
        if not checked['accepted']:
            raise AssertionError('certificate rejected')
        check_seconds = time.perf_counter() - decoded
        cert_io_seconds = decoded - searched
    elif arm == 'projected-no-certificate':
        _, answer = compare(pair, make_certificate=False)
        searched = time.perf_counter()
    elif arm == 'reflexive-no-certificate':
        answer = solve(pair)
        searched = time.perf_counter()
    elif arm == 'complete-world':
        answer = decide(pair)
        searched = time.perf_counter()
    else:
        raise ValueError('unknown arm')
    (directory / 'answer.json').write_text(json.dumps(answer, sort_keys=True) + '\n', encoding='utf-8')
    end = time.perf_counter()
    return dict(arm=arm, equivalent=answer['equivalent'], budget=answer['budget'],
                input_sha256=hashlib.sha256(pair_bytes).hexdigest(), input_bytes=len(pair_bytes),
                certificate_bytes=cert_bytes, states=answer.get('states'), worlds=answer.get('worlds'),
                structural_identity=answer.get('structural_identity', False),
                source_preparation_and_pair_write_seconds=prepared-start,
                pair_read_and_validation_seconds=acquired-prepared, search_seconds=searched-acquired,
                certificate_write_reparse_seconds=cert_io_seconds, checker_seconds=check_seconds,
                answer_write_seconds=end-searched-cert_io_seconds-check_seconds,
                total_seconds=end-start, pair_boundary_seconds=end-prepared)


def source_execution_rows():
    for name, source in source_cases():
        for policy in POLICIES:
            compiled = compile_workflow(source, policy, key_count=2, result_count=2)
            h = len(compiled['nodes'])
            for world in itertools.product((0, 1), repeat=2):
                actual = workflow_observations(source, policy, world, h)
                expected = observations(compiled, world, h)
                terminal = workflow_denotation(source, world)
                if actual != expected or (policy in POLICIES[:4] and actual[-1] != terminal):
                    raise AssertionError('ordinary workflow execution differs')
                yield dict(source=name, policy=policy, world=world, horizon=h,
                           direct_trace=[sorted(x) for x in actual], controller_trace=[sorted(x) for x in expected],
                           denotation=sorted(terminal), terminal_equal=actual[-1] == terminal)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--repeats', type=int, default=5)
    args = ap.parse_args()
    if args.repeats < 1:
        ap.error('positive repeats required')
    args.out.mkdir(parents=True)
    inputs = args.out / 'inputs'; inputs.mkdir()
    specs = specifications()
    for spec in specs:
        (inputs / (spec['name'] + '.json')).write_text(json.dumps(spec, indent=2) + '\n', encoding='utf-8')
    records = []
    for trial in range(args.repeats):
        # Fixed rotation balances warm-process order without data-dependent tuning.
        arms = ARMS[trial % 4:] + ARMS[:trial % 4]
        for spec in specs:
            trial_rows = []
            for arm in arms:
                row = measure(inputs / (spec['name'] + '.json'), args.out / 'runs' / str(trial) / spec['name'] / arm, arm)
                row.update(case=spec['name'], family=spec['family'], trial=trial)
                records.append(row); trial_rows.append(row)
            if len({(r['equivalent'], r['budget'], r['input_sha256']) for r in trial_rows}) != 1:
                raise AssertionError('same-input arms disagree')
    with (args.out / 'rows.jsonl').open('w', encoding='utf-8') as f:
        for row in records:
            f.write(json.dumps(row, sort_keys=True) + '\n')
    with (args.out / 'workflow-traces.jsonl').open('w', encoding='utf-8') as f:
        for row in source_execution_rows():
            f.write(json.dumps(row, sort_keys=True) + '\n')
    aggregates = []
    for spec in specs:
        medians = {arm: statistics.median(r['total_seconds'] for r in records
                                         if r['case'] == spec['name'] and r['arm'] == arm) for arm in ARMS}
        aggregates.append(dict(case=spec['name'], family=spec['family'],
                               **{arm.replace('-', '_') + '_seconds': medians[arm] for arm in ARMS},
                               certificate_over_projected_ratio=medians['certificate'] / medians['projected-no-certificate']))
    with (args.out / 'comparison.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(aggregates[0])); w.writeheader(); w.writerows(aggregates)
    sources = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob('*.py')}
    summary = dict(cases=len(specs), trials=args.repeats, arm_executions=len(records), workflow_traces=72,
                   all_arm_inputs_and_answers_equal=True, measured_host=platform.platform(), python=sys.version,
                   source_hashes=sources, total_measurement='source preparation, file acquisition/validation, solving, certificate write/reparse/check when requested, answer write',
                   excludes='process startup, imports, experiment row emission, fsync durability, original-library acquisition and third-party solvers',
                   maintenance='fresh pair and invocation-local search each trial; no persistent index or incremental updates',
                   timing_scope='warm same-process local measurements, not external workload or performance-superiority evidence',
                   aggregates=aggregates)
    (args.out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: summary[k] for k in ('cases', 'trials', 'arm_executions', 'workflow_traces')}))


if __name__ == '__main__':
    main()
