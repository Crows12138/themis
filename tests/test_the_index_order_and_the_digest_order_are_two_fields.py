"""One list cannot be both what the digest covers and how to read a matrix.

Both discovery results recorded a single ``columns``. It was doing two
jobs. As a SET it is what ``data_hash`` was taken over. As an ORDER it is
how everything downstream is indexed — the node ids in the returned edges,
and the rows and columns of the sufficient statistic a verifier recomputes
from. Those are the same members in different orders, so one field had to
be wrong about one of them, and both docstrings answered with a third
thing: "canonical order", which is neither.

Splitting is the fix and renaming was not: ``data_columns`` means the
digest's order in five other containers, so pointing that spelling at the
statistic order would make one name mean two orders across the package.

What makes the split load-bearing rather than tidy is that the digest is
reproducible from one of the two lists and not from the other. These
recompute it both ways.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from themis.estimation.contract import _hash_frame
from themis.estimation.discovery import (
    discover_graph,
    discovery_to_kernel_ast,
    markov_blanket,
    markov_blanket_to_dict,
)


def _frame(n=400, seed=5):
    """Deliberately NOT in sorted column order, so the two lists differ."""
    rng = np.random.default_rng(seed)
    z = rng.standard_normal(n)
    x = 0.8 * z + rng.standard_normal(n)
    y = 0.6 * x + 0.4 * z + rng.standard_normal(n)
    return pd.DataFrame({"z": z, "y": y, "x": x})


@pytest.fixture(scope="module")
def graph():
    frame = _frame()
    return frame, discover_graph(frame, algorithm="pc", alpha=0.05)


@pytest.fixture(scope="module")
def blanket():
    frame = _frame()
    return frame, markov_blanket(frame, target="y")


# --- the two lists are not the same list --------------------------------

def test_the_graph_result_keeps_both_orders(graph):
    _, result = graph
    assert set(result.columns) == set(result.data_columns)
    assert result.data_columns == tuple(sorted(result.columns))
    assert result.columns != result.data_columns, (
        "the frame was built out of sorted order so that these differ; "
        "if they stopped differing the test proves nothing"
    )


def test_the_blanket_result_keeps_both_orders(blanket):
    _, result = blanket
    assert set(result.columns) == set(result.data_columns)
    assert result.data_columns == tuple(sorted(result.columns))
    assert result.columns[0] == result.target, "the statistic is target-first"
    assert result.columns != result.data_columns


# --- and only one of them reproduces the digest -------------------------

@pytest.mark.parametrize("which", ["graph", "blanket"])
def test_the_digest_is_reproducible_from_its_own_denominator(
    which, graph, blanket,
):
    """Recomputed here rather than compared to a field the producer also
    wrote: the point is that this list, in this order, is the thing the
    hash was taken over."""
    frame, result = graph if which == "graph" else blanket
    assert _hash_frame(frame[list(result.data_columns)]) == result.data_hash


@pytest.mark.parametrize("which", ["graph", "blanket"])
def test_the_other_order_does_not_reproduce_it(which, graph, blanket):
    """The counterexample the split exists for. ``_hash_frame`` mixes each
    column's name before its values, so the order is part of the digest and
    the index order is not interchangeable with the denominator."""
    frame, result = graph if which == "graph" else blanket
    assert _hash_frame(frame[list(result.columns)]) != result.data_hash


# --- and both travel ----------------------------------------------------

def test_the_graph_program_carries_both(graph):
    _, result = graph
    meta = discovery_to_kernel_ast(result)["extensions"]["discovery_metadata"]
    assert meta["data_hash"] == result.data_hash
    assert meta["data_columns"] == list(result.data_columns)
    assert meta["columns"] == list(result.columns)


def test_the_blanket_artifact_carries_both(blanket):
    _, result = blanket
    d = markov_blanket_to_dict(result)
    assert d["data_hash"] == result.data_hash
    assert d["data_columns"] == list(result.data_columns)
    assert d["columns"] == list(result.columns)
