"""Owned finite source and formula contracts, including deep admitted trees."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from checker import check
from complexity import exact_budget_pair, cnf_satisfiable, semantic_irrelevance_controller
from model import validate, validate_pair
from oracle import observations, workflow_denotation, workflow_observations
from producer import compare
from workflows import compile_workflow, POLICIES


def deep_workflow(depth=1000):
    term = ('return', 0)
    for _ in range(depth):
        term = ('test', 0, ('fail',), term)
    return term


class WorkflowBoundaries(unittest.TestCase):
    def test_deep_valid_compiler(self):
        source = deep_workflow()
        for policy in POLICIES:
            with self.subTest(policy=policy):
                compiled = validate(compile_workflow(source, policy))
                self.assertLessEqual(len(compiled['nodes']), 2048)
                pair = {'left': compiled, 'right': compiled}
                certificate, result = compare(pair)
                self.assertTrue(result['equivalent'])
                self.assertTrue(check(pair, certificate)['accepted'])
                for world in ((0,), (1,)):
                    self.assertEqual(observations(compiled, world, 1002),
                                     workflow_observations(source, policy, world, 1002))

    def test_deep_denotation_and_budget(self):
        source = deep_workflow()
        self.assertEqual(workflow_denotation(source, (0,)), frozenset())
        self.assertEqual(workflow_denotation(source, (1,)), frozenset((0,)))
        trace = workflow_observations(source, 'fifo', (1,), 1002)
        self.assertEqual(trace[1000], frozenset())
        self.assertEqual(trace[1001], frozenset((0,)))

    def test_shared_source_objects_keep_occurrences(self):
        child = ('return', 0)
        source = ('split', child, child)
        c = compile_workflow(source, 'fifo')
        self.assertEqual(observations(c, (), 3),
                         (frozenset(), frozenset(), frozenset((0,)), frozenset((0,))))
        self.assertEqual(len(c['nodes']), 4)

    def test_disjoint_formula_blocks_are_admitted_not_assumed(self):
        for args in (([[1]], [], 0, 1), ([], [[2]], 1, 1), ([], [], True, 0),
                     ([], [], 0, False), ([], [], 1.0, 1), ([], [], -1, 1)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                exact_budget_pair(*args)

    def test_cnf_oracle_rejects_invalid_literal_identity(self):
        for formula, count in (([[0]], 1), ([[True]], 1), ([[2]], 1), ([[1]], -1),
                               ([], True), ([], 1.0)):
            with self.subTest(formula=formula, count=count), self.assertRaises(ValueError):
                cnf_satisfiable(formula, count)

    def test_irrelevance_reduction_rejects_undersized_block(self):
        for formula, count in (([[1]], 0), ([[2]], 1), ([], True), ([], -1)):
            with self.subTest(formula=formula, count=count), self.assertRaises(ValueError):
                semantic_irrelevance_controller(formula, count)

    def test_valid_empty_and_disjoint_reductions_preserved(self):
        for phi, psi, pn, qn in (([], [[]], 0, 0), ([[1]], [[1], [-1]], 1, 1),
                                ([[1], [-1]], [[1]], 1, 1)):
            pair, early, late = exact_budget_pair(phi, psi, pn, qn)
            validate_pair(pair)
            cert, result = compare(pair)
            expected = early if cnf_satisfiable(psi, qn) else (
                late if cnf_satisfiable(phi, pn) else None)
            self.assertEqual(result['budget'], expected)
            self.assertTrue(check(pair, cert)['accepted'])


if __name__ == '__main__':
    unittest.main()
