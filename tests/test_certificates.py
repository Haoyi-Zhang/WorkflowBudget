import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from examples import curated, pair, H, E, S, R, controller, cnf_controller, all_forward_controllers
from producer import compare, static_width
from model import load
from checker import check, Invalid, read_json
from oracle import decide, canonical, observations, workflow_observations
from negative_controls import chronological, forget_everything, independent_worlds, terminal_only
from complexity import (exact_budget_pair, cnf_satisfiable, semantically_relevant_keys,
                        semantic_irrelevance_controller)
from workflows import compile_workflow


class Certificates(unittest.TestCase):
    def test_examples(self):
        for name,_,p,e,t in curated():
            with self.subTest(case=name):
                cert,stats = compare(p)
                self.assertEqual((stats["equivalent"],stats["budget"]),(e,t))
                truth = decide(p)
                self.assertEqual((truth["equivalent"],truth["budget"]),(e,t))
                self.assertTrue(check(p,cert)["accepted"])
                self.assertEqual(canonical(p["left"])==canonical(p["right"]),e)
                self.assertLessEqual(stats["max_retained_keys"],static_width(p))
                if name == "case-01":
                    reranked = copy.deepcopy(cert)
                    for record in reranked["nodes"]:
                        record["rank"] = 0
                    self.assertTrue(check(p, reranked)["accepted"])

    def rejected(self,p,c):
        with self.assertRaises(Invalid): check(p,c)

    def test_deleted_successor(self):
        p = curated()[0][2]; c,_ = compare(p)
        del c["nodes"][-1]
        self.rejected(p,c)

    def test_omitted_input_binding(self):
        p = curated()[1][2]; c,_ = compare(p)
        entry = next(s for s in c["nodes"] if s["state"][4])
        entry["state"][4] = []
        self.rejected(p,c)

    def test_changed_input_binding(self):
        p = curated()[0][2]; c,_ = compare(p)
        entry = next(s for s in c["nodes"] if s["state"][4])
        entry["state"][4][0][1] ^= 1
        self.rejected(p,c)

    def test_swapped_result_masks(self):
        p = curated()[5][2]; c,_ = compare(p)
        c["nodes"][-1]["state"][2] ^= 2
        self.rejected(p,c)

    def test_false_root(self):
        p = curated()[0][2]; c,_ = compare(p)
        c["nodes"][0]["rank"] = 1
        self.rejected(p,c)

    def test_duplicate_state(self):
        p = curated()[0][2]; c,_ = compare(p)
        c["nodes"].append(copy.deepcopy(c["nodes"][0]))
        self.rejected(p,c)

    def test_non_live_memory(self):
        p = pair(E(0),E(0)); c,_ = compare(p)
        c["nodes"][0]["state"][4] = [[0,0]]
        self.rejected(p,c)

    def test_later_witness_not_shortest(self):
        p = curated()[4][2]; c,_ = compare(p)
        c["budget"] = 2
        self.rejected(p,c)

    def test_rank_cannot_skip_shorter_path(self):
        p = curated()[8][2]; c,_ = compare(p)
        c["nodes"][1]["rank"] = 2
        self.rejected(p,c)

    def test_nondistinguishing_world(self):
        p = pair(R(0,H,E(0)),H); c,_ = compare(p)
        c["world"] = [0,0]
        self.rejected(p,c)

    def test_world_boolean_not_integer(self):
        p = curated()[4][2]; c,_ = compare(p)
        c["world"][0] = True
        self.rejected(p,c)

    def test_controller_backward_edge(self):
        p = pair(S(H),S(H)); c,_ = compare(p)
        p["left"]["nodes"][0]["next"] = 0
        self.rejected(p,c)

    def test_controller_alphabet_mismatch(self):
        p = pair(E(0),E(0)); c,_ = compare(p)
        p["right"]["keys"].reverse()
        self.rejected(p,c)

    def test_out_of_range_mask(self):
        p = pair(E(0),E(0)); c,_ = compare(p)
        c["nodes"][0]["state"][2:4] = [4,4]
        self.rejected(p,c)

    def test_extra_fields(self):
        p = pair(E(0),E(0)); c,_ = compare(p)
        c["trusted"] = True
        self.rejected(p,c)

    def test_duplicate_json_fields(self):
        with tempfile.TemporaryDirectory() as td:
            duplicate = Path(td)/"duplicate.json"
            duplicate.write_text('{"kind": "equivalent", "kind": "inequivalent"}')
            with self.assertRaises(Invalid):
                read_json(str(duplicate), 1024)
            with self.assertRaises(ValueError):
                load(duplicate, 1024)

            nonfinite = Path(td)/"nonfinite.json"
            nonfinite.write_text('{"value": NaN}')
            with self.assertRaises(Invalid):
                read_json(str(nonfinite), 1024)
            with self.assertRaises(ValueError):
                load(nonfinite, 1024)

    def test_wrong_memory_type(self):
        p = pair(E(0),E(0)); c,_ = compare(p)
        c["nodes"][0]["state"][4] = 0
        self.rejected(p,c)

    def test_empty_keys_and_results(self):
        p = pair(S(H),H,keys=0,results=0)
        c,info = compare(p)
        self.assertTrue(info["equivalent"])
        self.assertTrue(check(p,c)["accepted"])

    def test_nonzero_entry_and_unreachable_nodes(self):
        node_count = 512
        nodes = [{"op":"step","next":i+1} for i in range(node_count-1)]
        nodes.append({"op":"halt"})
        controller_with_unreachable_prefix = {
            "keys": [], "results": [], "start": node_count-1, "nodes": nodes,
        }
        p = {"left": copy.deepcopy(controller_with_unreachable_prefix),
             "right": copy.deepcopy(controller_with_unreachable_prefix)}
        c,info = compare(p)
        verdict = check(p,c)
        self.assertTrue(info["equivalent"])
        self.assertEqual(len(c["nodes"]), 1)
        self.assertEqual(verdict["proof_states"], 1)
        self.assertEqual(verdict["checked_transitions"], 1)

    def test_workflow_compiler_alphabet_contract(self):
        returned = compile_workflow(("return",2), "fifo")
        self.assertEqual(returned["keys"], [])
        self.assertEqual(returned["results"], ["r0","r1","r2"])
        self.assertEqual(returned["nodes"][returned["start"]]["result"], 2)
        with self.assertRaises(ValueError):
            compile_workflow(("return",2), "fifo", result_count=2)

        source = ("test",2,("fail",),("return",0))
        compiled = compile_workflow(source, "fifo")
        self.assertEqual(compiled["keys"], ["x0","x1","x2"])
        self.assertEqual(compiled["results"], ["r0"])
        horizon = len(compiled["nodes"])
        for world in ((0,0,0),(1,1,0),(0,0,1),(1,1,1)):
            self.assertEqual(
                observations(compiled, world, horizon),
                workflow_observations(source, "fifo", world, horizon),
            )
        with self.assertRaises(ValueError):
            compile_workflow(source, "fifo", key_count=2)

    def test_negative_controls(self):
        cases = {x[0]:x[2] for x in curated()}
        self.assertEqual(chronological(cases["case-01"]),3)
        self.assertEqual(forget_everything(cases["case-02"]),3)
        self.assertEqual(independent_worlds(cases["case-03"]),2)
        self.assertTrue(terminal_only(cases["case-04"]))

    def test_cnf_reduction(self):
        for clauses,sat in [([],True),([[]],False),([[1],[-1]],False),
                            ([[1,2],[-1]],True),([[1],[-1,2],[-2]],False)]:
            p = {"left":cnf_controller(clauses,2),"right":controller(H,2,1)}
            cert,stats = compare(p)
            self.assertEqual(not stats["equivalent"],sat)
            self.assertTrue(check(p,cert)["accepted"])


    def test_exact_budget_dp_reduction(self):
        formulas = [
            ([], 0),
            ([[]], 0),
            ([[1]], 1),
            ([[1], [-1]], 1),
            ([[1, 2], [-1]], 2),
        ]
        for phi, pn in formulas:
            for psi, qn in formulas:
                with self.subTest(phi=phi, psi=psi):
                    p, early, late = exact_budget_pair(phi, psi, pn, qn)
                    cert, info = compare(p)
                    psat = cnf_satisfiable(phi, pn)
                    qsat = cnf_satisfiable(psi, qn)
                    expected = early if qsat else (late if psat else None)
                    self.assertEqual(info["budget"], expected)
                    self.assertEqual(info["equivalent"], expected is None)
                    self.assertTrue(check(p, cert)["accepted"])
                    self.assertEqual(decide(p)["budget"], expected)

    def test_semantic_key_relevance_reduction(self):
        formulas = [
            ([], 0, True),
            ([[]], 0, False),
            ([[1]], 1, True),
            ([[1], [-1]], 1, False),
            ([[1, 2], [-1]], 2, True),
        ]
        for clauses, nkeys, sat in formulas:
            with self.subTest(clauses=clauses):
                c, distinguished = semantic_irrelevance_controller(clauses, nkeys)
                relevant = semantically_relevant_keys(c)
                self.assertEqual(distinguished in relevant, sat)

    def test_semantic_relevance_is_within_syntactic_future(self):
        from model import future
        for c in all_forward_controllers(2, 2):
            exact = set(semantically_relevant_keys(c))
            syntactic = {k for k in range(2) if (future(c)[c["start"]] >> k) & 1}
            self.assertTrue(exact <= syntactic)

    def test_resource_cutoff_is_not_equivalence(self):
        p = curated()[0][2]
        with self.assertRaises(RuntimeError): compare(p,max_states=1)

if __name__ == "__main__": unittest.main()
