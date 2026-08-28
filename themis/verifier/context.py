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

from dataclasses import dataclass, field

import networkx as nx

from ..runtime.numeric_estimator import Theta
from ..types import Atom, Query


# Every kind the query language can express reaches a verify_* rule —
# ``kernel.verify`` dispatches all ten and refuses anything else outright —
# so "verifiable" is not a subset of the query vocabulary, it IS that
# vocabulary. An alias rather than a second listing: what stood here was
# the union written out a second time, and it had gone one member stale
# (``ProximalEffectQuery``, added to the language and to the dispatch but
# not to the copy). Nothing could have caught that, because a copy states
# no relationship to the thing it copies — the name is what the context
# needs this query FOR, and the type is where the query kinds are declared.
VerifiableQuery = Query


@dataclass(frozen=True)
class VerificationContext:
    graph: nx.DiGraph
    query: VerifiableQuery
    theta: Theta | None = None
    # Phase 2.latent S4: bidirected edge set for ADMG programs. Empty
    # frozenset (the default) preserves all pre-ADMG verification paths
    # bit-identically. When non-empty, backdoor_criterion and
    # front_door_criterion rules consult m-separation (via independent
    # verifier reimplementation, not structural_solver) instead of
    # directed-only d-separation.
    bidirected: frozenset[frozenset[Atom]] = field(default_factory=frozenset)
    # Phase 9 §T9.1: selection node set for transport identification.
    # Empty tuple on non-transport programs preserves all pre-Phase-9
    # paths bit-identically. T9-1 / T9-2 rules read this to re-derive
    # S-admissibility independently of runtime/transport.py.
    selection_nodes: tuple = ()
    # Linear-SCM counterfactual (Pearl Primer §4): the unit's observed
    # factual values (Atom -> float), i.e. the evidence E=e the abduction
    # step solves the exogenous U from. None on every non-SCM path. The
    # scm_abduction_action_prediction rule reads this to re-run the
    # three-step computation independently of runtime/scm_counterfactual.
    observations: dict | None = None
    # #450: the reciprocal loops the program declares, as unordered pairs.
    # Empty on every program that declares none, which is every program
    # written before the statement existed. The rule that reads it does
    # NOT take the loop from the derivation step it is checking: a step
    # naming a loop nobody declared would otherwise license its own
    # withdrawal, and the withdrawal is the thing that removed an answer.
    feedback: frozenset[frozenset[Atom]] = field(default_factory=frozenset)
