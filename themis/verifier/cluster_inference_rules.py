"""Independent audit of cluster-robust inference disclosure.

A cluster / block column is a statement about the unit of independence. Honour
it and the interval widens; drop it and the interval is anti-conservative — the
number looks the same either way, so the failure is invisible in the point and
visible only in a width nobody can check without the raw data.

What makes it auditable at all is that the envelope carries the fact from two
independent directions:

- ``estimation_context.cluster`` — what the RUN resolved, recorded once before
  any estimator can consume it.
- ``numeric_estimate.assumptions`` — what the ESTIMATOR itself declares it did
  with that column, in its own words (it resampled whole clusters; or its
  interval comes from an analytic formula that ignores them).

This module holds the two against each other. The check that matters is
one-sided and follows from what silence means: an interval computed under a
clustered run that says nothing about the cluster column is indistinguishable,
to every consumer, from an interval computed on independent rows. So silence is
the defect — not merely undocumented, but a claim of i.i.d. inference the run
gave no basis for.

It also rejects the mirror failure: a ``bootstrap`` block asserting
cluster-robustness that the run never resolved, that names a different column
than the run did, or that the estimator's own declarations do not corroborate.
That block is written by the dispatch layer, one call site per estimator
family; requiring the estimator to independently declare the same thing turns a
hand-written assertion into a two-source agreement.

What it deliberately does NOT audit: whether the interval is *numerically*
cluster-robust. Re-deriving a percentile bootstrap needs the raw data, which is
the data-refit ceiling every numeric verifier in this package stops at. The
auditable claim is disclosure, and disclosure is where this failure hid.

**Independence pin:** this module MUST NOT import from
``themis.estimation`` — it re-derives what is owed from the envelope alone.
"""
from __future__ import annotations

from typing import NoReturn

from .errors import VerificationError

_RULE = "cluster_inference_check"


def _reject(message: str) -> NoReturn:
    raise VerificationError(message, rule=_RULE)


def verify_cluster_inference(result: dict) -> None:
    """Audit one result's cluster-robustness disclosure.

    No-op when the run named no cluster column and nothing claims one.
    Raises :class:`VerificationError` on under-disclosure or on a
    cluster-robustness claim the envelope does not support.
    """
    context = result.get("estimation_context") or {}
    run_cluster = context.get("cluster")

    estimate = result.get("numeric_estimate") or {}
    stamp = estimate.get("bootstrap")
    bounds = result.get("numeric_bounds") or {}
    bounds_cluster = bounds.get("numeric_cluster")

    if run_cluster is None:
        # Nothing was resolved, so nothing may claim to have honoured it.
        if isinstance(stamp, dict) and stamp.get("kind") == "cluster":
            _reject(
                "numeric_estimate.bootstrap claims a cluster bootstrap on "
                f"{stamp.get('cluster_column')!r}, but the run recorded no "
                "cluster column in estimation_context — the claim has no "
                "run-level basis"
            )
        if bounds_cluster is not None:
            _reject(
                f"numeric_bounds.numeric_cluster names {bounds_cluster!r}, "
                "but the run recorded no cluster column in estimation_context"
            )
        return

    _check_stamp(stamp, run_cluster, estimate)
    _check_bounds(bounds_cluster, run_cluster)
    _check_declaration(estimate, run_cluster)


def _check_stamp(stamp, run_cluster: str, estimate: dict) -> None:
    """The dispatch-written bootstrap block must agree with the run and be
    corroborated by the estimator's own declarations."""
    if not isinstance(stamp, dict) or stamp.get("kind") != "cluster":
        return
    stamped = stamp.get("cluster_column")
    if stamped != run_cluster:
        _reject(
            f"numeric_estimate.bootstrap resampled {stamped!r} but the run "
            f"resolved cluster column {run_cluster!r}"
        )
    if not _names(estimate.get("assumptions"), run_cluster):
        _reject(
            f"numeric_estimate.bootstrap claims a cluster bootstrap on "
            f"{run_cluster!r}, but the estimator's own assumptions never "
            "mention that column — the claim is unattributed"
        )


def _check_bounds(bounds_cluster, run_cluster: str) -> None:
    if bounds_cluster is not None and bounds_cluster != run_cluster:
        _reject(
            f"numeric_bounds.numeric_cluster names {bounds_cluster!r} but the "
            f"run resolved cluster column {run_cluster!r}"
        )


def _check_declaration(estimate: dict, run_cluster: str) -> None:
    """Every interval produced under a clustered run must say, in the
    estimator's own declarations, what it did with the column."""
    if estimate.get("ci_lower") is None and estimate.get("ci_upper") is None:
        return  # no interval — there is nothing to be robust about
    if _names(estimate.get("assumptions"), run_cluster):
        return
    _reject(
        f"the run resolved cluster column {run_cluster!r}, but the "
        f"{estimate.get('method')!r} interval's declared assumptions never "
        "mention it: an interval that says nothing about a named cluster "
        "column reads as i.i.d. inference the run gave no basis for. An "
        "estimator that cannot cluster must declare that it did not."
    )


def _names(assumptions, cluster: str) -> bool:
    """True iff some declared assumption names the cluster column.

    Deliberately wording-agnostic: estimators declare their resampling in
    several registers (``ci_via_pairs_cluster_bootstrap_on_<col>``,
    ``ci_not_cluster_robust_..._ignores_<col>``, Chinese prose). What every
    honest declaration has in common — and what silence lacks — is the column
    name, so that is what is checked. Pinning one spelling would make the
    audit a transcription of the producer's string format.
    """
    for item in assumptions or ():
        if isinstance(item, str) and cluster in item:
            return True
    return False
