"""Same-information exact no-certificate baseline, not an independent kernel.

Shares the projected search engine, but skips predecessor/certificate work.
Validated structural identity is a sound optional fast path for equivalence.
"""
from model import validate_pair
from producer import compare


def solve(pair, *, reflexivity=True, max_states=200_000):
    left, right = validate_pair(pair)
    if reflexivity and left == right:
        return dict(equivalent=True, budget=None, states=0, transitions=0,
                    max_retained_keys=0, structural_identity=True)
    _, answer = compare(pair, make_certificate=False, max_states=max_states)
    return dict(answer, structural_identity=False)
