"""Owned finite fixtures and full-world references; no other test imports."""
from itertools import product
from pathlib import Path
import copy
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import producer
from model import State, future
import checker


def future_reference(c, start):
    pending, seen, keys = [start], set(), set()
    while pending:
        at = pending.pop()
        if at in seen:
            continue
        seen.add(at)
        node = c["nodes"][at]
        if node["op"] == "read":
            keys.add(node["key"])
            pending.extend((node["zero"], node["one"]))
        elif node["op"] in ("step", "emit"):
            pending.append(node["next"])
    return keys


def concrete_tick(c, at, found, world):
    node = c["nodes"][at]
    found = set(found)
    if node["op"] == "read":
        at = node["zero"] if world[node["key"]] == 0 else node["one"]
    elif node["op"] == "emit":
        found.add(node["result"])
        at = node["next"]
    elif node["op"] == "step":
        at = node["next"]
    return at, found


def extension_reference(left, right, state, erase):
    """Total-world enumeration, deduplicated by the requested answer stream."""
    reads = sorted({c["nodes"][at]["key"] for c, at in
                    ((left, state.left), (right, state.right))
                    if c["nodes"][at]["op"] == "read"})
    seen, records = set(), []
    for world in product((0, 1), repeat=len(left["keys"])):
        if any(world[key] != value for key, value in state.memory):
            continue
        answers = tuple((key, world[key]) for key in reads)
        if answers in seen:
            continue
        seen.add(answers)
        masks = (state.out_left, state.out_right)
        outputs = [{r for r in range(len(left["results"])) if mask & (1 << r)} for mask in masks]
        p, a = concrete_tick(left, state.left, outputs[0], world)
        q, b = concrete_tick(right, state.right, outputs[1], world)
        known = dict(state.memory)
        known.update(answers)
        alive = future_reference(left, p) | future_reference(right, q)
        memory = sorted((key, value) for key, value in known.items() if not erase or key in alive)
        records.append(([p, q, sum(1 << r for r in a), sum(1 << r for r in b),
                         [[key, value] for key, value in memory]], answers))
    return records


def budget_reference(pair):
    best = None
    left, right = pair["left"], pair["right"]
    for world in product((0, 1), repeat=len(left["keys"])):
        p, q, a, b = left["start"], right["start"], set(), set()
        for budget in range(1, max(len(left["nodes"]), len(right["nodes"])) + 1):
            p, a = concrete_tick(left, p, a, world)
            q, b = concrete_tick(right, q, b, world)
            if a != b:
                best = budget if best is None else min(best, budget)
                break
    return best


def owned_controller(key=0, result=0):
    return {"keys": ["a", "b"], "results": ["yes", "no"], "start": 0,
            "nodes": [{"op": "read", "key": key, "zero": 1, "one": 1},
                      {"op": "read", "key": 1 - key, "zero": 2, "one": 2},
                      {"op": "read", "key": key, "zero": 4, "one": 3},
                      {"op": "emit", "result": result, "next": 4}, {"op": "halt"}]}


class RequestedKeys(unittest.TestCase):
    def test_extension_cartesian_answers_and_projection(self):
        for kl, kr, p, q, ml, mr, memory, erase in product(
                (0, 1), (0, 1), range(5), range(5), (0, 3), (0, 3),
                ((), ((0, 0),), ((1, 1),), ((0, 1), (1, 0))), (True, False)):
            left, right = owned_controller(kl), owned_controller(kr)
            state = State(p, q, ml, mr, memory)
            actual = [(target.encode(), answers) for target, answers in
                      producer.extensions(left, right, state, future(left), future(right), erase)]
            self.assertEqual(actual, extension_reference(left, right, state, erase))

    def test_complete_world_budget_and_independent_checker(self):
        for kl, kr, rl, rr in product((0, 1), repeat=4):
            pair = {"left": owned_controller(kl, rl), "right": owned_controller(kr, rr)}
            cert, stats = producer.compare(pair)
            self.assertEqual(stats["budget"], budget_reference(pair))
            self.assertEqual(stats["equivalent"], stats["budget"] is None)
            self.assertTrue(checker.check(pair, cert)["accepted"])
            malformed = copy.deepcopy(cert)
            malformed["nodes"][0]["rank"] = 1
            with self.assertRaisesRegex(checker.Invalid, "missing zero-rank root"):
                checker.check(pair, malformed)

    def test_direct_helper_observes_controller_changes(self):
        left, right = owned_controller(), owned_controller()
        root = State(0, 0, 0, 0, ())
        first = list(producer.extensions(left, right, root, future(left), future(right)))
        right["nodes"][0]["key"] = 1
        second = list(producer.extensions(left, right, root, future(left), future(right)))
        self.assertEqual((len(first), len(second)), (2, 4))
        self.assertEqual(second, list(producer.extensions(left, right, root, future(left), future(right))))

    def test_cutoff_and_full_history_certificate_error(self):
        pair = {"left": owned_controller(), "right": owned_controller(1)}
        for cap in (0, 1, 2):
            with self.assertRaisesRegex(RuntimeError, "explicit-state limit reached; no equivalence answer"):
                producer.compare(pair, max_states=cap)
        with self.assertRaisesRegex(ValueError, "certificate format requires live-input projection"):
            producer.compare(pair, erase=False)
        self.assertIsNone(producer.compare(pair, erase=False, make_certificate=False)[0])

    def test_metadata_reused_once_per_control_pair_in_both_arms(self):
        pair = {"left": owned_controller(), "right": owned_controller(1)}
        for erase in (True, False):
            original, controls = producer._requested_keys, []
            def counted(left, right, p, q):
                controls.append((p, q))
                return original(left, right, p, q)
            with patch.object(producer, "_requested_keys", side_effect=counted):
                _, stats = producer.compare(pair, erase=erase, make_certificate=False)
            self.assertEqual(len(controls), len(set(controls)))
            self.assertLess(len(controls), stats["states"])

    def test_cache_does_not_survive_an_invocation(self):
        pair = {"left": owned_controller(), "right": owned_controller()}
        producer.compare(pair)
        pair["right"]["nodes"][0]["key"] = 1
        cert, stats = producer.compare(pair)
        self.assertEqual(stats["budget"], budget_reference(pair))
        self.assertTrue(checker.check(pair, cert)["accepted"])


if __name__ == "__main__":
    unittest.main()
