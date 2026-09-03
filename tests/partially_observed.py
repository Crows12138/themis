"""A program whose outcome is partially observed, and data to match.

The shape that routes to the missing-data recovery estimator, which is the
one route that declines the ordinary path entirely: the columns it recovers
from carry NaN, which the data contract forbids, so it returns above the
contract. Answers from it arrive with a number, an interval, and no chain —
which is why more than one gate is asked about them, and why the program
lives here rather than beside any one of those questions.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _atom(predicate: str) -> dict:
    return {"predicate": predicate, "args": [{"type": "const", "name": "p"}]}


def program() -> dict:
    """x→y confounded by z, y partially observed, its indicator caused by z."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "p"}]},
        "statements": [
            {"kind": "variable", "predicate": p, "domain": [True, False]}
            for p in ("x", "y", "z")
        ] + [
            {"kind": "cause", "from": _atom(a), "to": _atom(b)}
            for a, b in (("z", "x"), ("z", "y"), ("x", "y"))
        ] + [
            {"kind": "missingness_indicator", "id": "R_y",
             "missing_var": _atom("y"), "caused_by": [_atom("z")]},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "target": {"atom": _atom("y"), "value": True},
                "intervention": {"atom": _atom("x"), "value": True},
                "given": []}},
        ],
    }


def frame(n: int = 4000, seed: int = 4) -> pd.DataFrame:
    """Missing at random: whether y is observed depends on z alone."""
    rng = np.random.default_rng(seed)
    z = rng.binomial(1, 0.5, n)
    x = rng.binomial(1, 0.3 + 0.4 * z)
    y = rng.binomial(1, np.clip(0.2 + 0.2 * x + 0.2 * z, 0, 1)).astype(float)
    y[rng.binomial(1, 0.1 + 0.6 * z) == 1] = np.nan
    return pd.DataFrame({"x": x.astype(float), "y": y, "z": z.astype(float)})
