"""Binary observational joint + interventional risk, recovered from a DataFrame.

The two attribution rungs — probabilities of causation (PN/PS/PNS, see
:mod:`themis.estimation.causation`) and the single binary counterfactual cell
(see :mod:`themis.estimation.counterfactual_cell`) — answer different
theorems, but both need exactly the same two things out of the data before
their theorem can run:

- the four observational cells ``P(X=x, Y=y)`` — empirical frequencies;
- the interventional risk ``P(Y=1 | do(X=x))`` for one or both arms. For
  binary Y, ``E[Y | do(X=x)] = P(Y=1 | do(X=x))`` exactly, so each arm is the
  back-door standardized (g-formula) mean ``Σ_z P̂(Y=1 | X=x, Z=z) · P̂(Z=z)``
  over a minimal back-door adjustment set Z. Z=∅ (exogeneity / randomization)
  reduces it to ``P̂(Y=1 | X=x)``.

Neither of those is the theorem under test in either module, so the
transcription lives here once and both estimators reuse it. What each module
owns is its own theorem: Tian-Pearl's PN/PS/PNS in one, the linear
consistency identity of :func:`themis.runtime.counterfactual.counterfactual_cell_interval`
in the other.

And neither owns the CASCADE — the ordered question "which of these routes
reaches the risks this answer needs". :func:`choose_risk_route` is that
question asked once. It used to be asked twice, once at the top of each
estimator, and the two copies were a prefix apart: adding the general-ID
route and then the instrument route moved one of them and left the other
where it was. Nothing was wrong in either file, which is the point — from
inside a file its own cascade reads complete, so the divergence was visible
only by asking the same question through both doors and noticing the answers
differed. A door may still decide its OWN terminal (what to do when no route
reaches); what it may not do is keep a private opinion about which routes
exist.

Reference: Hernán & Robins 2020 ch.13 for the g-formula (standardization)
plug-in in the non-parametric limit.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

import numpy as np
import pandas as pd

from ..risk_provenance import RiskProvenance
from ..runtime import structural_solver
from ..types import Atom, FormulaExpr
from ..refusals import Refusal
from ..refusals import EstimatorFailure


def minimal_backdoor_adjustment(
    graph, cause: Atom, effect: Atom, bidirected,
) -> tuple[str, ...]:
    """The minimal back-door adjustment set for the do-risks, as column names.

    Raises ``EstimatorFailure`` when no admissible set exists (an unmeasured
    confounder — the do-risks are not identified from the observational frame,
    and the caller must supply experimental risks)."""
    sets = structural_solver.minimal_adjustment_sets(
        graph, cause, effect, bidirected=bidirected or None,
    )
    if not sets:
        raise EstimatorFailure(
            Refusal.DO_RISK_NOT_IDENTIFIABLE,
            "P(Y=1|do(X)) is not back-door identifiable from the observational "
            "data (no admissible adjustment set — likely an unmeasured "
            "confounder). Supply experimental_risk_treated / "
            "experimental_risk_control from a randomized experiment.",
        )
    # Prefer the smallest set (fewest strata → most support per cell).
    best = min(sets, key=len)
    return tuple(sorted(a.predicate for a in best))


def instrument_for(
    graph, cause: Atom, effect: Atom, bidirected,
) -> Atom | None:
    """The instrument this graph declares for ``cause → effect``, if exactly one.

    Pearl's graphical criterion (2009 §7.4.5), stated once: Z is an instrument
    when it is m-separated from the outcome in the graph with the treatment's
    OUTGOING edges deleted. That single separation carries both of the
    conditions usually written apart — exclusion (no directed path from Z to Y
    that bypasses X survives the deletion) and independence from the latent
    background (a Z↔Y path, or a shared parent, is open in that graph) — so
    they are not checked twice under two names.

    Relevance is the structural edge Z→X, which is also what the
    response-function model consumes: the map it enumerates is ``z → x``.

    ``None`` when no candidate qualifies AND when several do. Several valid
    instruments carry MORE information than any one of them, so picking one
    would be answering a narrower question quietly; returning nothing leaves
    the caller to say what it could not do.
    """
    import networkx as nx

    bid = bidirected or frozenset()
    if cause not in graph or effect not in graph:
        return None
    without_treatment_effects = nx.DiGraph()
    without_treatment_effects.add_nodes_from(graph.nodes())
    without_treatment_effects.add_edges_from(
        (u, v) for u, v in graph.edges() if u != cause
    )
    candidates = [
        z for z in graph.predecessors(cause)
        if z != effect
        and structural_solver.m_separated(
            without_treatment_effects, bid, z, effect, (),
        )
    ]
    return candidates[0] if len(candidates) == 1 else None


@dataclass(frozen=True)
class RiskRoute:
    """How an attribution answer will obtain what observation cannot give it.

    ``provenance`` is the licence; the other three carry whatever that
    particular licence needs to be acted on and re-derived — the adjustment
    set to standardize over, the per-arm ID estimand to evaluate, the
    instrument column to fit the polytope to. Exactly one of them is
    populated on any route, and which one follows from the licence, so a
    consumer that reads the wrong field gets an empty answer rather than a
    plausible one.

    Each is carried at the type the door will act on it at — the estimands as
    the ``FormulaExpr`` the identification layer built, not as anonymous
    objects. A cascade that named them more loosely than it knows them would
    hand every door the same small job of deciding what it had just been
    given, and that job is one the cascade has already done.
    """

    provenance: RiskProvenance
    adjustment: tuple[str, ...] = ()
    formulas: dict[bool, FormulaExpr] = field(default_factory=dict)
    instrument: Atom | None = None


#: The mechanism sentence's short name, by the route that produced it.
#:
#: A lookup with a default rather than a chain, because a route added to the
#: cascade should be a row here and not another branch to get the order right
#: in — and beside the cascade rather than inside each door, because the name
#: describes what the ROUTE did. Only the routes that depart from the
#: g-formula appear; every other licence takes the default.
FORM_BY_PROVENANCE: dict[RiskProvenance, str] = {
    RiskProvenance.GENERAL_ID_PLUG_IN: "nonparametric_c_factor_plug_in",
    RiskProvenance.INSTRUMENT_RESPONSE_POLYTOPE:
        "nonparametric_response_function_lp",
}

DEFAULT_FORM = "nonparametric_gformula_plug_in"


def choose_risk_route(
    graph,
    bidirected,
    *,
    cause: Atom,
    effect: Atom,
    arms: tuple[bool, ...],
    supplied: Mapping[bool, float | None] = {},
) -> RiskRoute | None:
    """The one cascade: which route reaches ``P(Y=1 | do(X=arm))`` for ``arms``.

    Ordered by how little the answer has to assume, which is also the order in
    which the routes stop being available: an arm the caller measured needs no
    graph at all; a back-door set is the weakest graphical claim; the general
    ID algorithm reaches arms no covariate set blocks; and an instrument
    delivers no risk whatsoever — it delivers the SET of models the data
    admit, which is a different kind of answer and therefore last.

    ``arms`` is which arms this answer consumes: empty for a cell whose two
    worlds coincide, one for a cell that crosses them, both for PN/PS/PNS.
    That is the only way the two doors differ here, and it is a parameter
    rather than a branch because the routes themselves do not care.

    Returns ``None`` when no route reaches — deliberately, rather than
    raising. What to do next is the caller's, and the two doors genuinely
    differ: a counterfactual cell can still be pinned outright by a declared
    monotonicity, and probabilities of causation cannot.
    """
    from .general_id import identify_arm_risk_formula

    if not arms:
        return RiskRoute(RiskProvenance.NOT_REQUIRED)
    if all(supplied.get(arm) is not None for arm in arms):
        return RiskRoute(RiskProvenance.USER_EXPERIMENTAL)
    try:
        adjustment = minimal_backdoor_adjustment(graph, cause, effect, bidirected)
    except EstimatorFailure:
        pass
    else:
        return RiskRoute(
            RiskProvenance.EXOGENOUS if not adjustment
            else RiskProvenance.BACKDOOR_ADJUSTMENT,
            adjustment=adjustment,
        )
    formulas: dict[bool, FormulaExpr] = {}
    for arm in arms:
        try:
            formulas[arm] = identify_arm_risk_formula(
                graph, bidirected,
                treatment_atom=cause, outcome_atom=effect,
                # The arms are booleans and the columns are binary; True/False
                # and 1/0 compare and hash alike, so the literal threaded
                # through the estimand matches the data's own levels either way.
                arm_value=arm, outcome_value=True,
            )
        except EstimatorFailure:
            # Every arm or none. An answer needing two arms is not served by
            # having identified one of them, and reporting the licence for a
            # half-finished route would name a method that did not run.
            formulas = {}
            break
    if formulas:
        return RiskRoute(RiskProvenance.GENERAL_ID_PLUG_IN, formulas=formulas)
    instrument = instrument_for(graph, cause, effect, bidirected)
    if instrument is not None:
        return RiskRoute(
            RiskProvenance.INSTRUMENT_RESPONSE_POLYTOPE, instrument=instrument,
        )
    return None


def as_binary_column(col: pd.Series, name: str) -> np.ndarray:
    """Coerce a column to a boolean numpy array, refusing non-binary data."""
    vals = set(pd.unique(col.dropna()))
    if not vals <= {0, 1, True, False, 0.0, 1.0}:
        raise EstimatorFailure(
            Refusal.CAUSE_OR_EFFECT_NOT_BINARY,
            column=name, values=sorted(vals, key=str),
        )
    return col.to_numpy().astype(bool)


def observational_joint_xy(
    x: np.ndarray, y: np.ndarray,
) -> dict[tuple[bool, bool], float]:
    """Empirical P(X=x, Y=y) — the four cells as sample frequencies."""
    n = len(x)
    return {
        (xv, yv): float(np.count_nonzero((x == xv) & (y == yv))) / n
        for xv in (True, False)
        for yv in (True, False)
    }


def backdoor_do_risk(
    x: np.ndarray, y: np.ndarray, frame: pd.DataFrame,
    adjustment: tuple[str, ...], *, arm: bool,
) -> float:
    """P(Y=1 | do(X=arm)) by back-door standardization (discrete g-formula).

    ``Σ_z P̂(Y=1 | X=arm, Z=z) · P̂(Z=z)`` over the empirical distribution of
    the adjustment set Z. Z=∅ reduces to P̂(Y=1 | X=arm). A stratum present in
    the marginal Z but empty under this treatment arm is a positivity
    violation — raises rather than fabricating a mean."""
    if not adjustment:
        mask = x == arm
        if not mask.any():
            # No rows at this arm ANYWHERE, which is the treatment column
            # sitting at a single level — the neighbour species, not the
            # empty-cell one it used to name.
            raise EstimatorFailure(
                Refusal.OVERLAP_INSUFFICIENT,
                f"no rows with X={arm}; cannot estimate P(Y=1|do(X={arm})).",
            )
        return float(y[mask].mean())

    z = frame[list(adjustment)]
    n = len(frame)
    total = 0.0
    # Standardize over every stratum that occurs in the full sample.
    for key, idx in z.groupby(list(adjustment), sort=False, observed=True).indices.items():
        p_z = len(idx) / n
        arm_rows = idx[x[idx] == arm]
        if arm_rows.size == 0:
            # The cell, not just the fact: "positivity is violated" without
            # naming the stratum is a thing the reader cannot act on.
            raise EstimatorFailure(
                Refusal.NO_WITHIN_STRATUM_CONTRAST,
                strata=[dict(zip(adjustment,
                                 key if isinstance(key, tuple) else (key,)))],
                recorded={"arm": arm},
            )
        p_y_given = float(y[arm_rows].mean())
        total += p_y_given * p_z
    return total
