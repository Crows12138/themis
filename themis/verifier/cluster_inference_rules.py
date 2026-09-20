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

Where such a record may sit is a question the CONTRACT answers, and this
module used to answer it from the shape of a producer's function name. The
result schema declares a ``bootstrap`` block in four places -- the estimate,
two decompositions under it, and a row of ``bounds_results`` -- and every one
of them carries stamps in practice. This module walked the first three and
watched, for the fourth, a top-level ``numeric_bounds`` key that the schema
does not declare and nothing has ever written, so the check reading it could
not fire on any answer that passes the door. What the producer calls
``_attach_numeric_bounds`` fills a ROW, and ``numeric_cluster`` is declared on
that row and nowhere else.

It also rejects the mirror failure: a ``bootstrap`` block asserting
cluster-robustness that the run never resolved, that names a different column
than the run did, that contradicts itself by labelling an interval ``iid``
beside the very column it claims to have ignored, or that the estimator's own
declarations do not corroborate.
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

    No-op when the run named no cluster column and nothing on the answer
    claims one. Raises :class:`VerificationError` on under-disclosure, on a
    cluster-robustness claim the envelope does not support, on a block that
    contradicts itself, and on a stamp that says less than the estimator
    declared.
    """
    context = result.get("estimation_context") or {}
    run_cluster = context.get("cluster")
    estimate = result.get("numeric_estimate") or {}

    for where, block, stamp, declared in _stamped_blocks(result):
        _check_one_block(where, block, stamp, run_cluster, declared)

    if run_cluster is not None:
        _check_declaration(estimate, run_cluster)

    # Last, and whatever the run recorded. Last because the checks above
    # own the cases they can already name, and a rule that reaches a
    # forgery first with a wider sentence takes the better one away from
    # the reader. Whatever the run recorded, because an estimator saying it
    # resampled whole clusters is a claim about its own loop, owed a stamp
    # that says so whether or not the run recorded a column of its own.
    _check_every_stamp_says_what_the_estimator_declared(estimate)


def _stamped_blocks(result: dict):
    """Every block on one result carrying a stamp, and what describes it.

    Four yields' worth of places, because that is how many the contract
    declares: ``numeric_estimate``, the two decompositions under it, and a
    row of ``bounds_results``. The first three are one walk, for the reason
    :func:`_stamps` gives. The fourth is a row, and reaching it is the
    whole of what this function adds -- see the module docstring for the
    key that was being watched instead.

    The last element of each yield is what describes THIS loop in its own
    words, or nothing where nothing does. A bounds row has an
    ``assumptions`` slot that no producer fills: thirteen of the fourteen
    stamped rows in this repository's corpus carry ``None``, both of the
    clustered ones among them. So the corroboration this module asks of the
    estimate has nothing to ask of a row -- which is a record the row does
    not have rather than a direction left unwatched, and the block checks
    below are written to ask only where there is something to ask.
    """
    estimate = result.get("numeric_estimate")
    if isinstance(estimate, dict):
        declared = estimate.get("assumptions")
        for where, block, stamp in _stamps(estimate):
            yield where, block, stamp, declared
    for row in result.get("bounds_results") or ():
        if isinstance(row, dict) and isinstance(row.get("bootstrap"), dict):
            yield (f"bounds_results[{row.get('method')!r}]", row,
                   row["bootstrap"], row.get("assumptions"))


def _check_one_block(where: str, block: dict, stamp: dict,
                     run_cluster, declared) -> None:
    """One block's stamp: against itself, against the run, against words.

    The first of those is a biconditional the contract states in prose and
    cannot carry. ``bootstrapDraws`` says ``cluster_column`` "is present
    exactly then"; ``numeric_cluster`` is "absent for the i.i.d.
    bootstrap". An enum beside a closed object accepts ``iid`` next to a
    named column either way round, so holding it is a rule's job.

    Which slot each half is asked of is the whole of the care here.
    ``cluster_column`` belongs to the stamp, and every stamp is a
    ``bootstrapDraws``, so requiring it whenever the kind is ``cluster``
    needs to know nothing about the container. ``numeric_cluster`` is
    declared on a bounds row and on nothing else, so it is read where it is
    PRESENT: a rule demanding it of every block would refuse every honest
    estimate, and a rule demanding it of the containers it could name would
    be a table of containers again -- which is the mistake this module is
    being taken out of.

    That asymmetry costs one hold, named here rather than left to be
    discovered: a bounds row stamped ``cluster`` whose ``numeric_cluster``
    is missing is accepted, because the half of the biconditional that
    would refuse it is the half that needs the container. The row still
    names the column in its stamp, so no reader is told the wrong unit of
    independence; what is lost is the envelope's second copy of it.
    """
    stamp_at = f"{where}.bootstrap"
    kind = stamp.get("kind")
    named: dict[str, object] = {}
    if stamp.get("cluster_column") is not None:
        named[f"{stamp_at}.cluster_column"] = stamp["cluster_column"]
    if block.get("numeric_cluster") is not None:
        named[f"{where}.numeric_cluster"] = block["numeric_cluster"]
    listed = ", ".join(f"{slot}={value!r}"
                       for slot, value in sorted(named.items()))

    if kind == "cluster" and stamp.get("cluster_column") is None:
        _reject(
            f"{stamp_at} says its loop resampled whole clusters and does "
            f"not say which column. Which column is the unit of "
            f"independence is the whole of what that claim tells a reader, "
            f"so a claim without one leaves them nothing to check their "
            f"own unit against"
        )
    if kind != "cluster" and named:
        _reject(
            f"{stamp_at} says {kind!r} while its block still names the "
            f"column it would have had to ignore ({listed}). An interval "
            f"labelled i.i.d. is read as resting on independent rows and "
            f"one naming a cluster column is read as resampling it, so "
            f"this block is read both ways by two readers who both looked"
        )
    if len(set(named.values())) > 1:
        _reject(
            f"one loop ran, so one column was resampled, and {where} names "
            f"more than one ({listed}). A reader deciding whether the "
            f"interval covers their unit of independence reads whichever "
            f"of them they happened to find"
        )

    for slot, column in sorted(named.items()):
        if run_cluster is None:
            _reject(
                f"{slot} claims a cluster bootstrap on {column!r}, but the "
                f"run recorded no cluster column in estimation_context — "
                f"the claim has no run-level basis"
            )
        if column != run_cluster:
            _reject(
                f"{slot} resampled {column!r} but the run resolved cluster "
                f"column {run_cluster!r}"
            )

    if named and declared and not _names(declared, run_cluster):
        _reject(
            f"{stamp_at} claims a cluster bootstrap on {run_cluster!r}, but "
            f"the estimator's own assumptions never mention that column "
            f"— the claim is unattributed"
        )
    # Where the stamp is the only register a block has, the stamp is what
    # has to say it. ``declared is None`` means nothing on this envelope
    # describes this loop in words -- a bounds row, whose ``assumptions``
    # slot no producer fills -- so an ``iid`` label under a clustered run
    # is the whole of what the block says about the column, and it is a
    # claim the run gave no basis for. Where words exist the same question
    # belongs to :func:`_check_declaration`, which also reaches intervals
    # carrying no stamp at all; asking it twice would take that case away
    # from the rule whose sentence is about it.
    if declared is None and kind != "cluster" and run_cluster is not None:
        _reject(
            f"the run resolved cluster column {run_cluster!r} and "
            f"{stamp_at} says {kind!r}, with nothing on this block saying "
            f"what its loop did with that column and no declarations of "
            f"its own to say it in. An interval labelled i.i.d. under a "
            f"clustered run is an anti-conservative claim the run gave no "
            f"basis for — the same failure as silence, asserted"
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

    The block as well as the record, because a column can be named twice in
    one place and the question is about the block rather than about the
    stamp alone.
    """
    if isinstance(node, dict):
        record = node.get("bootstrap")
        if isinstance(record, dict):
            yield under, node, record
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
    for where, _block, record in _stamps(estimate):
        kind = record.get("kind")
        if kind != "cluster":
            _reject(
                f"the estimator declares it resampled whole clusters by "
                f"{column!r} and {where}.bootstrap says {kind!r}. An interval "
                f"labelled i.i.d. is read as resting on independent rows, "
                f"so a stamp saying less than the estimator declared hands "
                f"the reader a narrower claim than the run supports — and "
                f"the two are records of one loop"
            )
        stamped = record.get("cluster_column")
        if stamped != column:
            _reject(
                f"the estimator declares it resampled whole clusters by "
                f"{column!r} and {where}.bootstrap resampled {stamped!r}. "
                f"One loop "
                f"ran, so one column was resampled, and a reader deciding "
                f"whether the interval covers their unit of independence "
                f"is reading whichever of the two they happened to find"
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
    estimator's own declarations, what it did with the column.

    The estimate's, because this asks about intervals that carry no stamp
    at all — an analytic one, or a decomposition's endpoint — and
    the declarations are the only record those have. A block that does
    carry a stamp is asked the same question by :func:`_check_one_block`,
    where the stamp itself counts as saying what the loop did.
    """
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
