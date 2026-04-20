"""Verification context — everything the verifier needs as *premises*.

The context is an explicit enumeration of the inputs Themis treats as
given. The verifier trusts the context (it doesn't check whether the
graph reflects reality); it only checks that the derivation legitimately
moves from context + prior steps to each claimed output.

Slice V0 only needs ``graph`` and ``query``. Later slices will add
``theta`` for numeric rules and ``declarations`` for framing tie-ins.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx

from ..types import IdentifyQuery


@dataclass(frozen=True)
class VerificationContext:
    graph: nx.DiGraph
    query: IdentifyQuery
