"""Verification context — everything the verifier needs as *premises*.

The context is an explicit enumeration of the inputs Themis treats as
given. The verifier trusts the context (it doesn't check whether the
graph reflects reality); it only checks that the derivation legitimately
moves from context + prior steps to each claimed output.

V0 used ``graph`` + ``query``. V1 adds ``theta`` for the numeric rules
(R6 ``probability_ref_lookup``, R7 ``formula_evaluation``). Theta stays
optional — identify-only derivations still pass ``theta=None``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Union

import networkx as nx

from ..runtime.numeric_estimator import Theta
from ..types import (
    AssocQuery,
    CauseQuery,
    EffectQuery,
    IdentifyQuery,
    ProbabilityQuery,
)


VerifiableQuery = Union[
    CauseQuery, AssocQuery, IdentifyQuery, EffectQuery, ProbabilityQuery,
]


@dataclass(frozen=True)
class VerificationContext:
    graph: nx.DiGraph
    query: VerifiableQuery
    theta: Theta | None = None
