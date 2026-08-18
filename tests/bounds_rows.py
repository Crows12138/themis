"""Reading one row out of the bounds SET, in tests.

``bounds_results`` holds one entry per method whose assumptions the
program supports. Tests that check a particular method's arithmetic want
that method's row, and indexing by position would make them depend on the
presentation order — which the producer states carries no meaning, and
which a fourth method would shift.
"""
from __future__ import annotations


def row(result: dict, method: str) -> dict:
    """The row this method produced, or a failure naming what was there."""
    rows = result.get("bounds_results") or []
    for b in rows:
        if b.get("method") == method:
            return b
    raise AssertionError(
        f"no {method!r} row in bounds_results; got "
        f"{[b.get('method') for b in rows]}"
    )


def methods(result: dict) -> list[str]:
    """Every method that reached the reader, in presentation order."""
    return [b.get("method") for b in (result.get("bounds_results") or [])]


def only(result: dict) -> dict:
    """The single row, asserting there is exactly one.

    Useful where the point of the test is that nothing sharper applied.
    """
    rows = result.get("bounds_results") or []
    assert len(rows) == 1, f"expected one bounds row, got {methods(result)}"
    return rows[0]
