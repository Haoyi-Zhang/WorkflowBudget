"""Read-only controls for current-cohort result selection."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verify_delivery import compare_result, prepare_workspace, result_files
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import reviewer_hardening


class DeliveryBaselineTests(unittest.TestCase):
    def test_current_tests_selected_without_changing_history(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            historical = root / 'results' / 'unit-tests.json'
            current = root / 'results' / 'current' / 'results' / 'unit-tests.json'
            current.parent.mkdir(parents=True)
            historical.write_text(json.dumps({'tests_run': 27, 'failures': 0}))
            current.write_text(json.dumps({'tests_run': 30, 'failures': 0}))
            before = historical.read_bytes()
            selected = result_files(root, current_baseline=True)
            self.assertEqual(selected[Path('results/unit-tests.json')], current)
            self.assertEqual(historical.read_bytes(), before)

    def test_scientific_test_counts_are_not_normalized_away(self):
        with tempfile.TemporaryDirectory() as temp:
            left, right = Path(temp) / 'left.json', Path(temp) / 'right.json'
            left.write_text(json.dumps({'tests_run': 30, 'wall_seconds': 1}))
            right.write_text(json.dumps({'tests_run': 30, 'wall_seconds': 9}))
            compare_result(left, right)
            right.write_text(json.dumps({'tests_run': 27, 'wall_seconds': 1}))
            with self.assertRaises(AssertionError):
                compare_result(left, right)

    def test_fresh_results_are_not_masked_by_copied_current_baseline(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fresh = root / 'results' / 'unit-tests.json'
            copied = root / 'results' / 'current' / 'results' / 'unit-tests.json'
            copied.parent.mkdir(parents=True)
            fresh.write_text(json.dumps({'tests_run': 30, 'failures': 1}))
            copied.write_text(json.dumps({'tests_run': 30, 'failures': 0}))
            selected = result_files(root)
            self.assertEqual(selected[Path('results/unit-tests.json')], fresh)
            with self.assertRaises(AssertionError):
                compare_result(copied, selected[Path('results/unit-tests.json')])

    def test_existing_workspace_is_refused_without_removing_files(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp) / 'workspace'
            workspace.mkdir()
            sentinel = workspace / 'keep.txt'
            sentinel.write_text('keep')
            with self.assertRaises(FileExistsError):
                prepare_workspace(Path(temp), workspace)
            self.assertEqual(sentinel.read_text(), 'keep')

    def test_explicit_current_cohort_satisfies_result_contract(self):
        base=reviewer_hardening.RESULTS / 'current' / 'results'
        summary=reviewer_hardening.check_result_contract(False,base)
        self.assertEqual(summary['unit_tests'],30)
        self.assertEqual(Path(summary['result_root']),Path('results/current/results'))

    def test_default_contract_does_not_substitute_current_for_fresh_tests(self):
        read=reviewer_hardening._required_json
        def fresh_failure(base,name):
            value=read(base,name)
            if name=='unit-tests.json':
                value=dict(value,tests_run=30,failures=1)
            return value
        with patch.object(reviewer_hardening,'_required_json',side_effect=fresh_failure):
            with self.assertRaisesRegex(RuntimeError,'unit-test failures'):
                reviewer_hardening.check_result_contract(False)


if __name__ == '__main__':
    unittest.main()
