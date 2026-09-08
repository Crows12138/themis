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

**And the mirror of that mirror, which was the one direction missing.** Those
three all begin at the stamp: they ask what the block claims and then look for
corroboration. Nothing asked the question the other way round — the estimator
declared it resampled whole clusters, does the stamp say so? — so a stamp
could under-claim freely. Measured through the public door on a clustered run
that really did resample clusters: rewriting ``kind`` from ``cluster`` to
``iid`` was refused by no door, and neither was a block left saying ``iid``
while still naming the column it had supposedly ignored. An interval labelled
i.i.d. is read as anti-conservative by every consumer that reads the label,
which is the same failure this module exists for, arriving from the side it
was not watching. So the two records of one loop are now held BOTH ways.

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

#: The one declaration that asserts a LOOP resampled whole clusters.
#:
#: Spelled out here, where :func:`_names` below deliberately is not, because
#: the two answer different questions. ``_names`` asks whether a declaration
#: MENTIONS the column, and every honest declaration does whichever register
#: it is written in, so pinning a spelling there would make the audit a
#: transcription of the producer's string format. This asks which register a
#: declaration is IN — resampled the clusters, or ignored them and said so —
#: and a reading that cannot tell those apart cannot ask this question at all.
#: What keeps it from going stale is that it is a registered prefix rather
#: than a string invented here: ``themis.assumption_glossary`` carries it,
#: the parity test that keeps the glossary in step with what the estimators
#: emit reaches it, and the test beside this rule pins the two equal.
_RESAMPLED_WHOLE_CLUSTERS = "ci_via_pairs_cluster_bootstrap_on_"


def _reject(message: str) -> NoReturn:
    raise VerificationError(message, rule=_RULE)


def verify_cluster_inference(result: dict) -> None:
    """Audit one result's cluster-robustness disclosure.

    No-op when the run named no cluster column and neither the stamp nor
    the estimator's declarations claim one. Raises
    :class:`VerificationError` on under-disclosure, on a cluster-robustness
    claim the envelope does not support, and on a stamp that says less than
    the estimator declared.
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
    else:
        _check_stamp(stamp, run_cluster, estimate)
        _check_bounds(bounds_cluster, run_cluster)
        _check_declaration(estimate, run_cluster)

    # Last, and in both branches. Last because the checks above own the
    # cases they can already name, and a rule that reaches a forgery first
    # with a wider sentence takes the better one away from the reader. In
    # both branches because an estimator saying it resampled whole clusters
    # is a claim about its own loop, owed a stamp that says so whether or
    # not the run recorded a column of its own.
    _check_every_stamp_says_what_the_estimator_declared(estimate)


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


def _resampled_clusters_on(assumptions) -> str | None:
    """The column the estimator says its loop resampled, or ``None``.

    One column: an estimator declares the unit of independence its own
    interval rests on, and two of those would be two intervals.
    """
    for item in assumptions or ():
        text = str(item)
        if text.startswith(_RESAMPLED_WHOLE_CLUSTERS):
            return text[len(_RESAMPLED_WHOLE_CLUSTERS):]
    return None


def _stamps(node, under: str = "numeric_estimate"):
    """Every bootstrap record on one estimate, and the block it sits in.

    Walked rather than read off the top level, because a decomposition puts
    a second loop under a block of its own and that loop is described by
    the same flat list of declarations — a stamp is not exempt from a
    claim for sitting one level down.
    """
    if isinstance(node, dict):
        record = node.get("bootstrap")
        if isinstance(record, dict):
            yield f"{under}.bootstrap", record
        for key, value in node.items():
            if key != "bootstrap":
                yield from _stamps(value, key)
    elif isinstance(node, list):
        for value in node:
            yield from _stamps(value, under)


def _check_every_stamp_says_what_the_estimator_declared(estimate) -> None:
    """A loop the estimator says clustered may not be stamped otherwise.

    The direction the module's three checks above do not cover: they start
    at the stamp and look for corroboration, so a stamp that says LESS than
    the estimator declared is corroborated by nobody and refused by nobody.

    Silent where no stamp exists at all. That used to be a hold this rule
    could not have: a run told to cluster and asked for no replicates drew
    nothing and declared the cluster bootstrap anyway, measured on every
    family, so "declared and no block" was the ordinary shape of a run with
    no interval and refusing it would have refused honest answers. The
    defect it was really evidence of — a declaration written whether or not
    the loop it describes ran — was fixed in #603 where the declaration is
    written, so that shape is gone from the estimators.

    Still silent, and the hold that #603 made available is taken in
    :mod:`themis.verifier.bootstrap_rules`: a resampled interval carries a
    general sentence as well as this cluster refinement, and an answer
    carrying that sentence with no block anywhere contradicts itself
    without any second record to compare. This rule compares records, so
    an answer with none is not its question.
    """
    if not isinstance(estimate, dict):
        return
    column = _resampled_clusters_on(estimate.get("assumptions"))
    if column is None:
        return
    for where, record in _stamps(estimate):
        kind = record.get("kind")
        if kind != "cluster":
            _reject(
                f"the estimator declares it resampled whole clusters by "
                f"{column!r} and {where} says {kind!r}. An interval "
                f"labelled i.i.d. is read as resting on independent rows, "
                f"so a stamp saying less than the estimator declared hands "
                f"the reader a narrower claim than the run supports — and "
                f"the two are records of one loop"
            )
        stamped = record.get("cluster_column")
        if stamped != column:
            _reject(
                f"the estimator declares it resampled whole clusters by "
                f"{column!r} and {where} resampled {stamped!r}. One loop "
                f"ran, so one column was resampled, and a reader deciding "
                f"whether the interval covers their unit of independence "
                f"is reading whichever of the two they happened to find"
            )


def _check_bounds(bounds_cluster, run_cluster: str) -> None:
    if bounds_cluster is not None and bounds_cluster != run_cluster:
        _reject(
            f"numeric_bounds.numeric_cluster names {bounds_cluster!r} but the "
            f"run resolved cluster column {run_cluster!r}"
        )


def _reports_an_interval(node: object) -> bool:
    """Whether this estimate reports an interval anywhere in it.

    Read at every depth for the reason :func:`_stamps` is read that way: a
    decomposition puts its endpoints in blocks of its own, described by the
    same flat list of declarations, and an interval is not exempt from the
    disclosure for sitting one level down. This question used to be asked of
    two keys at the top, so an answer whose intervals all nest left the rule
    by the early return meant for answers that have no interval at all —
    a check present, looking in one place, and indistinguishable from a pass.

    Measured when this was written: fourteen of the eighty-five answers this
    repository harvests report endpoints ONLY below the top level, across
    nine methods — three dose-response backends, both joint decompositions,
    mediation, the counterfactual cell, the proximal bridge and the CDE. A
    clustered mediation run carries eleven of them, and dropping the column
    from every record left it accepted while the same tampering on a
    back-door answer was refused.

    ``ci_lower`` / ``ci_upper`` and nothing else, which is a convention this
    envelope already keeps on purpose rather than a spelling chosen here:
    the one writer that publishes a pair of numbers which is NOT an
    estimate's endpoints calls them ``band_lower`` / ``band_upper``, and
    says in its own comment that it does so because a pair named lower and
    upper is read as endpoints.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("ci_lower", "ci_upper"):
                if value is not None:
                    return True
            elif _reports_an_interval(value):
                return True
    elif isinstance(node, list):
        return any(_reports_an_interval(v) for v in node)
    return False


def _check_declaration(estimate: dict, run_cluster: str) -> None:
    """Every interval produced under a clustered run must say, in the
    estimator's own declarations, what it did with the column."""
    if not _reports_an_interval(estimate):
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
