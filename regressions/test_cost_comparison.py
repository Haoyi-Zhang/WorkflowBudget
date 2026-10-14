"""Same-input baseline semantics and actual file-pipeline cost fields."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from budget_solver import solve
from cost_comparison import ARMS, measure, prepare, source_execution_rows, specifications
from examples import curated
from oracle import decide
from producer import compare


class CostComparison(unittest.TestCase):
    def test_no_certificate_has_exact_global_budget(self):
        for name, _, pair, eq, budget in curated():
            with self.subTest(case=name):
                actual = solve(pair)
                self.assertEqual((actual['equivalent'], actual['budget']), (eq, budget))
                self.assertEqual(actual['budget'], decide(pair)['budget'])

    def test_no_shortcut_matches_same_projected_engine(self):
        for _, _, pair, _, _ in curated():
            _, expected = compare(pair, make_certificate=False)
            actual = solve(pair, reflexivity=False)
            self.assertEqual({k: actual[k] for k in expected}, expected)

    def test_reflexivity_validates_before_returning(self):
        pair = copy.deepcopy(curated()[2][2])
        self.assertTrue(solve(pair)['structural_identity'])
        pair['left']['start'] = True
        pair['right'] = copy.deepcopy(pair['left'])
        with self.assertRaises(ValueError):
            solve(pair)

    def test_complete_file_pipeline_same_information(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            spec = specifications()[7]
            source = root / 'spec.json'
            source.write_text(json.dumps(spec), encoding='utf-8')
            records = [measure(source, root / arm, arm) for arm in ARMS]
            self.assertEqual(len({(r['equivalent'], r['budget'], r['input_sha256']) for r in records}), 1)
            for r in records:
                self.assertGreaterEqual(r['total_seconds'], r['pair_boundary_seconds'])
                self.assertGreaterEqual(r['pair_read_and_validation_seconds'], 0)
                self.assertEqual(r['certificate_bytes'] > 0, r['arm'] == 'certificate')

    def test_owned_source_trace_connection(self):
        rows = list(source_execution_rows())
        self.assertEqual(len(rows), 72)
        self.assertTrue(all(r['direct_trace'] == r['controller_trace'] for r in rows))
        for spec in specifications():
            pair = prepare(spec)
            self.assertEqual(solve(pair)['budget'], decide(pair)['budget'])


if __name__ == '__main__':
    unittest.main()
