"""The one answer a strategy handler gives the estimation cascade.

The cascade is a sequence of handlers, each guarded, each deciding whether
this query is its own. Before this module that decision was carried by two
different conventions — ten handlers returned ``bool``, nine returned
``None`` — and neither could say the thing that actually matters, so a
handler that owned a query but could not answer it was indistinguishable
from one that had nothing to do with it. That gap is not academic: it is
how a query naming a mediator lost the transport number it was entitled to,
and how a mediation query whose decomposition was unidentifiable came back
carrying a total effect instead.

Four outcomes, and the second one is the whole point:

``answered()``
    The handler owns this query and attached the answer.

``blocked(reason)``
    The handler owns this query and could not answer it. **The query stops
    here.** Passing it onward would let some other handler answer a
    DIFFERENT estimand in its place — a decomposition question answered with
    a total effect — which is worse than no number at all.

``annotated()``
    The handler added something to the envelope and does NOT own the query —
    a cost, a caveat, a diagnostic beside whatever answers it. The query
    continues to the handler that will answer it.

``passed(reason)``
    The query is still in flight and this handler added nothing. Either
    another handler owns it (the identification layer chose a different
    strategy) or this is one rung of an escalation ladder whose later rungs
    target the SAME estimand.

**The rule that separates ``blocked`` from ``passed``**: passing on is
legitimate only when whatever answers next answers the same question. That
invariant cannot be checked here — no handler yet declares which estimand it
targets — so for now it is a rule reviewers apply. Making the driver enforce
it is what the strategy table is for.

``reason`` is drawn from a closed vocabulary so that a decline is auditable
rather than merely silent. Nothing consumes the reasons yet: routing them
into the envelope changes what callers see, which belongs with the driver
that will collect them, not with this protocol change. ``blocked`` and
``passed`` reject an unregistered reason on the spot, so the vocabulary
cannot drift open.
"""
from __future__ import annotations

from dataclasses import dataclass

# Why a handler that was reached did not answer. Each entry names the fact
# and, implicitly, who can change it: the graph, the data, or the package.
BLOCK_REASONS: dict[str, str] = {
    "identification_chose_another_strategy": (
        "the identification layer routed this query elsewhere; the handler "
        "that owns it runs later in the cascade"
    ),
    "not_identified": (
        "identification chose this strategy and could not identify the "
        "estimand on this graph — a structural fact, not a data one"
    ),
    "numeric_end_not_built": (
        "the estimand is identified and this package has no numeric end for "
        "it yet — a declared gap in the package, not in the user's input"
    ),
    "combination_out_of_scope": (
        "this combination of query features is refused by design and by both "
        "layers alike — the package does not, for instance, decompose a joint "
        "multi-treatment effect through a mediator"
    ),
    "required_columns_absent": (
        "the design this strategy needs names columns the data does not have"
    ),
    "design_unavailable": (
        "the structural object this strategy needs (an adjustment set, an "
        "instrument, a mediator set) does not exist on this graph"
    ),
    "estimator_dependency_missing": (
        "the estimator needs an optional dependency this installation does "
        "not have; the user can change that by installing it"
    ),
    "estimator_refused": (
        "the estimator was reached and declined — a numeric or contract "
        "condition it checks for itself"
    ),
}


@dataclass(frozen=True)
class Claim:
    """A handler's answer to "is this query yours, and did you answer it"."""

    owned: bool
    answered: bool
    reason: str | None = None

    @property
    def stops_here(self) -> bool:
        """Whether the cascade must not offer this query to a later handler."""
        return self.owned


_ANSWERED = Claim(owned=True, answered=True)
_ANNOTATED = Claim(owned=False, answered=False)


def answered() -> Claim:
    """Owned, and the answer is attached."""
    return _ANSWERED


def annotated() -> Claim:
    """Something was added beside the answer; the query is someone else's."""
    return _ANNOTATED


def blocked(reason: str) -> Claim:
    """Owned, no answer — and no later handler may answer in its place."""
    return Claim(owned=True, answered=False, reason=_checked(reason))


def passed(reason: str) -> Claim:
    """Not answered here, and the query stays in flight for the next handler."""
    return Claim(owned=False, answered=False, reason=_checked(reason))


def _checked(reason: str) -> str:
    if reason not in BLOCK_REASONS:
        raise ValueError(
            f"unregistered decline reason {reason!r}; add it to "
            f"BLOCK_REASONS with a line saying what it means and who can "
            f"change it, or use one of: {sorted(BLOCK_REASONS)}"
        )
    return reason
