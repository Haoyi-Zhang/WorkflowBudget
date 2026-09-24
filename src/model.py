"""Finite, acyclic controllers with immutable Boolean inputs and set outputs.

Only the certificate producer imports this module. The checker and concrete
oracle have separate transition implementations. There is no external service.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Iterable
import json
from pathlib import Path

MAX_NODES = 2048
MAX_KEYS = 64
MAX_RESULTS = 8


def integer(value: Any, low: int, high: int) -> bool:
    return type(value) is int and low <= value <= high


def load(path: str | Path, limit: int = 8 * 1024 * 1024) -> Any:
    """Read strict JSON, rejecting duplicate keys and non-finite constants."""
    p = Path(path)
    if p.stat().st_size > limit:
        raise ValueError("input exceeds documented byte limit")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON object key")
            result[key] = value
        return result

    def reject_constant(name: str):
        raise ValueError(f"non-finite JSON constant: {name}")

    return json.loads(
        p.read_text(encoding="utf-8"),
        object_pairs_hook=unique,
        parse_constant=reject_constant,
    )


def validate(c: Any) -> dict:
    if type(c) is not dict or set(c) != {"keys", "results", "start", "nodes"}:
        raise ValueError("controller requires keys, results, start, nodes")
    for field, bound in [("keys", MAX_KEYS), ("results", MAX_RESULTS)]:
        a = c[field]
        if type(a) is not list or len(a) > bound:
            raise ValueError("invalid alphabet")
        if any(type(s) is not str or not 1 <= len(s) <= 64 for s in a):
            raise ValueError("invalid alphabet label")
        if len(a) != len(set(a)):
            raise ValueError("duplicate alphabet label")
    nodes = c["nodes"]
    if type(nodes) is not list or not 1 <= len(nodes) <= MAX_NODES:
        raise ValueError("invalid node table")
    if not integer(c["start"], 0, len(nodes)-1):
        raise ValueError("invalid entry")
    fields = {"halt": {"op"}, "step": {"op", "next"},
              "emit": {"op", "result", "next"},
              "read": {"op", "key", "zero", "one"}}
    for i, node in enumerate(nodes):
        if type(node) is not dict or type(node.get("op")) is not str:
            raise ValueError("malformed node")
        op = node["op"]
        if op not in fields or set(node) != fields[op]:
            raise ValueError("unknown operation or fields")
        targets = [node["zero"], node["one"]] if op == "read" else (
            [node["next"]] if op in ("step", "emit") else [])
        if any(not integer(t, i+1, len(nodes)-1) for t in targets):
            raise ValueError("nonterminal edges must go strictly forward")
        if op == "read" and not integer(node["key"], 0, len(c["keys"])-1):
            raise ValueError("invalid input index")
        if op == "emit" and not integer(node["result"], 0, len(c["results"])-1):
            raise ValueError("invalid result index")
    return c


def validate_pair(pair: Any) -> tuple[dict, dict]:
    if type(pair) is not dict or set(pair) != {"left", "right"}:
        raise ValueError("pair requires exactly left and right")
    a, b = validate(pair["left"]), validate(pair["right"])
    if a["keys"] != b["keys"] or a["results"] != b["results"]:
        raise ValueError("both controllers must share ordered alphabets")
    return a, b


def successors(c: dict, p: int) -> tuple[int, ...]:
    n = c["nodes"][p]
    if n["op"] == "read":
        return tuple(sorted(set((n["zero"], n["one"]))))
    if n["op"] in ("step", "emit"):
        return (n["next"],)
    return ()


def future(c: dict) -> list[int]:
    out = [0] * len(c["nodes"])
    for p in range(len(out)-1, -1, -1):
        n = c["nodes"][p]
        out[p] = (1 << n["key"]) if n["op"] == "read" else 0
        for t in successors(c, p):
            out[p] |= out[t]
    return out


def past(c: dict) -> tuple[list[int], set[int]]:
    out = [0] * len(c["nodes"])
    reachable = {c["start"]}
    for p in range(len(out)):
        if p not in reachable:
            continue
        n = c["nodes"][p]
        value = out[p] | ((1 << n["key"]) if n["op"] == "read" else 0)
        for t in successors(c, p):
            out[t] |= value
            reachable.add(t)
    return out, reachable


def tick(c: dict, p: int, mask: int, values: dict[int, int]) -> tuple[int, int]:
    n = c["nodes"][p]
    op = n["op"]
    if op == "halt":
        return p, mask
    if op == "read":
        return n["one"] if values[n["key"]] else n["zero"], mask
    if op == "emit":
        mask |= 1 << n["result"]
    return n["next"], mask


@dataclass(frozen=True)
class State:
    left: int
    right: int
    out_left: int
    out_right: int
    memory: tuple[tuple[int, int], ...]

    @property
    def bad(self) -> bool:
        return self.out_left != self.out_right

    def encode(self) -> list:
        return [self.left, self.right, self.out_left, self.out_right,
                [[k, v] for k, v in self.memory]]
