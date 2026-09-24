"""Small exact constructions used to validate the complexity arguments.

The functions in this module are deterministic generators and exhaustive
reference analyses. They are not SAT solvers and are used only on tiny inputs.
"""
from __future__ import annotations
from itertools import product
from typing import Iterable

from examples import H, E, S, R, controller
from oracle import observations


def _shift_clauses(clauses: Iterable[Iterable[int]], offset: int) -> list[list[int]]:
    """Shift 1-based signed literals to a disjoint global key block."""
    out: list[list[int]] = []
    for clause in clauses:
        row: list[int] = []
        for literal in clause:
            if type(literal) is not int or literal == 0:
                raise ValueError("literals must be nonzero integers")
            row.append((1 if literal > 0 else -1) * (abs(literal) + offset))
        out.append(row)
    return out


def fixed_cnf_expression(clauses: list[list[int]], on_true, on_false):
    """Evaluate a CNF in exactly one read per literal occurrence.

    Literals are signed, 1-based global key indices. The control state records
    whether all completed clauses and the current clause are satisfied. There is
    no short-circuiting, so every world reaches ``on_true`` or ``on_false`` after
    exactly ``sum(map(len, clauses))`` read ticks.
    """
    memo = {}

    def build(ci: int, li: int, all_ok: bool, clause_ok: bool):
        key = (ci, li, all_ok, clause_ok)
        if key in memo:
            return memo[key]
        if ci == len(clauses):
            ans = on_true if all_ok else on_false
        elif li == len(clauses[ci]):
            ans = build(ci + 1, 0, all_ok and clause_ok, False)
        else:
            literal = clauses[ci][li]
            k = abs(literal) - 1
            false_sat = clause_ok or (literal < 0)
            true_sat = clause_ok or (literal > 0)
            ans = R(k,
                    build(ci, li + 1, all_ok, false_sat),
                    build(ci, li + 1, all_ok, true_sat))
        memo[key] = ans
        return ans

    # The empty conjunction is true. An empty clause makes all_ok false at its
    # boundary, exactly as required by CNF semantics.
    return build(0, 0, True, False)


def exact_budget_pair(phi: list[list[int]], psi: list[list[int]],
                      phi_keys: int, psi_keys: int) -> tuple[dict, int, int]:
    """Reduction from SAT-UNSAT to an exact least-separation budget.

    ``phi`` and ``psi`` use separate local 1-based key spaces. The returned pair
    has one result.  It separates at ``early`` iff psi is satisfiable; otherwise
    it separates at ``late`` iff phi is satisfiable.  If both formulas are
    unsatisfiable the controllers are equivalent.
    """
    if phi_keys < 0 or psi_keys < 0:
        raise ValueError("negative key count")
    p = _shift_clauses(phi, 0)
    q = _shift_clauses(psi, phi_keys)
    nkeys = phi_keys + psi_keys

    left_phi = fixed_cnf_expression(p, E(0), S(H))
    right_phi = fixed_cnf_expression(p, S(H), S(H))
    left = fixed_cnf_expression(q, E(0, left_phi), S(left_phi))
    right = fixed_cnf_expression(q, S(right_phi), S(right_phi))

    early = sum(len(c) for c in q) + 1
    late = early + sum(len(c) for c in p) + 1
    return {"left": controller(left, nkeys, 1),
            "right": controller(right, nkeys, 1)}, early, late


def cnf_satisfiable(clauses: list[list[int]], nkeys: int) -> bool:
    """Tiny exhaustive CNF oracle for reduction tests."""
    if nkeys > 16:
        raise ValueError("tiny CNF oracle limited to sixteen variables")
    for world in product((0, 1), repeat=nkeys):
        ok = True
        for clause in clauses:
            sat = False
            for literal in clause:
                bit = world[abs(literal) - 1]
                sat |= bool(bit) if literal > 0 else not bool(bit)
            ok &= sat
        if ok:
            return True
    return False


def residual_observations(c: dict, start: int, world: tuple[int, ...]) -> tuple[frozenset, ...]:
    """Concrete observation trace from an arbitrary controller node."""
    clone = {"keys": c["keys"], "results": c["results"],
             "start": start, "nodes": c["nodes"]}
    return observations(clone, world, len(c["nodes"]))


def semantically_relevant_keys(c: dict, start: int | None = None) -> tuple[int, ...]:
    """Return keys whose value can change a residual observation trace.

    This exact analysis is deliberately exponential and is restricted to the
    same small-input boundary as the independent oracle.
    """
    n = len(c["keys"])
    if n > 16:
        raise ValueError("semantic relevance oracle limited to sixteen keys")
    p = c["start"] if start is None else start
    relevant: list[int] = []
    for key in range(n):
        others = [i for i in range(n) if i != key]
        found = False
        for bits in product((0, 1), repeat=len(others)):
            w0 = [0] * n
            for i, bit in zip(others, bits):
                w0[i] = bit
            w1 = list(w0)
            w1[key] = 1
            if residual_observations(c, p, tuple(w0)) != residual_observations(c, p, tuple(w1)):
                found = True
                break
        if found:
            relevant.append(key)
    return tuple(relevant)


def semantic_irrelevance_controller(clauses: list[list[int]], nkeys: int) -> tuple[dict, int]:
    """Controller used in the coNP-hardness reduction for exact key irrelevance.

    A fresh distinguished key x is relevant exactly when ``clauses`` is
    satisfiable: the controller emits iff x is true and the CNF is true.
    """
    shifted = _shift_clauses(clauses, 1)
    distinguished = 0
    body = fixed_cnf_expression(shifted, E(0), H)
    expr = R(distinguished, H, body)
    return controller(expr, nkeys + 1, 1), distinguished
