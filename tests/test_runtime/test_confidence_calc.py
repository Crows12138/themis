"""Unit tests for the v0.2 composite confidence rule.

Each test pins one of the nine criteria from
``confidence_rfc_v0_2.md`` §4, so any future rule change has to
either satisfy them explicitly or delete the test with a stated
rationale.
"""
from __future__ import annotations

from themis.runtime.confidence_calc import composite


# S1 — order independence

def test_s1_order_independence():
    assert composite(0.2, 0.9, 0.5) == composite(0.9, 0.5, 0.2)
    assert composite(0.2, 0.9, 0.5) == composite(0.5, 0.2, 0.9)


# S2 — monotone: adding a weaker input cannot raise composite

def test_s2_monotone_weaker_input_cannot_raise():
    base = composite(0.9, 0.7)
    with_weaker = composite(0.9, 0.7, 0.3)
    assert with_weaker <= base


def test_s2_monotone_stronger_input_cannot_raise_either():
    """Adding a stronger input also cannot raise past the existing min."""
    base = composite(0.4, 0.7)
    with_stronger = composite(0.4, 0.7, 0.95)
    assert with_stronger == base


# S3 — identity

def test_s3_identity_single_input_passes_through():
    assert composite(0.77) == 0.77


# S4 — empty → None

def test_s4_empty_returns_none():
    assert composite() is None


def test_s4_all_none_returns_none():
    assert composite(None, None) is None


# S5 — no independence assumption required
#    (demonstrated by the absence of product or noisy-OR behaviour)

def test_s5_no_product_decay_with_many_inputs():
    """Ten inputs at 0.9 stay at 0.9 under min, not decay to ~0.35
    like product would."""
    inputs = [0.9] * 10
    assert composite(*inputs) == 0.9


# S6 — interpretable: min matches the "weakest link" phrasing

def test_s6_weakest_input_wins():
    assert composite(0.9, 0.3, 0.7) == 0.3


# S7 — simple: handles None filtering without extras

def test_s7_nones_are_dropped_before_reduction():
    assert composite(None, 0.5, None, 0.8) == 0.5


# S8 — pipeline friendly: min of mins is still a min

def test_s8_min_of_mins_equivalence():
    a = composite(0.9, 0.3)
    b = composite(0.7, 0.5)
    assert composite(a, b) == composite(0.9, 0.3, 0.7, 0.5)


# S9 — v0.1.0 compatibility: without any input, still None

def test_s9_no_inputs_preserves_v0_1_0_behaviour():
    assert composite() is None


# Additional sanity

def test_idempotent():
    assert composite(0.5, 0.5) == 0.5
