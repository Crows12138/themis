"""Unit tests for the v0.1 placeholder composite confidence."""
from __future__ import annotations

from themis.runtime.confidence_calc import composite


def test_min_of_inputs():
    assert composite(0.9, 0.3, 0.7) == 0.3


def test_nones_are_dropped():
    assert composite(None, 0.5, None, 0.8) == 0.5


def test_all_none_returns_none():
    assert composite(None, None) is None


def test_empty_input_returns_none():
    assert composite() is None


def test_single_value_passes_through():
    assert composite(0.77) == 0.77


def test_order_independence():
    a = composite(0.2, 0.9, 0.5)
    b = composite(0.5, 0.2, 0.9)
    c = composite(0.9, 0.5, 0.2)
    assert a == b == c == 0.2
