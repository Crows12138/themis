"""Independent verification of the pre-flight data diagnostic (2026-07-11,
borrow-list #3).

The estimate path (``themis/estimation/dispatch.py``) reconciles each model
variable's DECLARED measurement type (``scale`` / ``domain``) against the
supplied column and, on disagreement, records the evidence in
``extensions.type_reconciliation`` and attaches a
``declared_type_data_mismatch`` gap. ``verify_type_reconciliation`` re-derives
the whole verdict from the recorded sufficient statistics and confirms the
attached gaps match — so a producer bug (wrong classification, wrong verdict,
fabricated or missing gap, mis-labelled severity) cannot pass unnoticed.

One mismatch carries two claims with different scopes, and the audit
re-derives both. The FINDING — this column disagrees with its declaration
— belongs to the program and holds on every result. What it COSTS belongs
to the answer in hand and holds only where that answer stands on the
column; a column no query estimated changes no number. Written as one
claim they could only be reported at the stronger of the pair, which is
how a declared-but-unestimated column came to block every point estimate
in the program.

**Independence pin:** this module MUST NOT import from
``themis.estimation.dispatch`` or any producer-side module. The observed-scale
classification, the declared-vs-observed reconciliation, and the
verdict → severity/blocks mapping are all re-implemented from scratch here, so
a bug in the generator cannot mask itself in the verifier. A test in
``tests/test_type_reconciliation.py`` line-scans this file to enforce the rule.

Which columns the answer stands on is the one input this rule reads rather
than re-derives, wherever the answer is a number. It is a fact only the
producer holds, so both sides once inferred it the same way from the same
document — agreeing by construction, which is a rule that cannot fail. The
producer now states it (``…data_columns``, the denominator of the fingerprint
beside it) and classifies each gap against its own statement, so the two can
disagree and this rule is what notices. Where identification answered and no
estimator ran there is nothing stated, and both sides fall back to the same
over-approximation — as before, and with the same limit.

The verifier trusts the recorded observation statistics (``n_unique`` /
``dtype_kind`` / ``observed_values`` — it cannot recount without the raw
DataFrame, exactly as ``bounds_rules`` trusts the recorded ``P_xyz`` table)
and independently re-derives every CONCLUSION drawn from them. It also
cross-checks the recorded statistics for internal consistency
(``len(observed_values) == n_unique``).

Reads only the JSON envelope (dicts), never typed dataclasses, so the audit
also catches serialization-layer bugs.
"""
from __future__ import annotations

from .errors import VerificationError


_RULE = "type_reconciliation_check"

# Independent twin of dispatch._classify_observed. Re-implemented, NOT
# imported.
_DISCRETE_DTYPES = frozenset({"integer", "bool", "object", "categorical"})

# Independent twin of dispatch's verdict -> blocks mapping, for a result
# whose answer STANDS ON the column. Off it the finding is about the
# program rather than about this number, and interpretation is the whole
# of what it touches.
_BLOCKS_BY_VERDICT = {
    "declared_continuous_data_discrete": "interpretation",
    "domain_violated": "point_estimate",
}

# How a fingerprint's denominator is spelled, and the one container whose
# denominator describes the RUN rather than an answer: every predicate the
# program declared, including the ones no query estimated. Counting that
# one makes the question say yes for everything — which is how a
# declared-but-unestimated column once blocked every point estimate.
_DENOMINATOR_SUFFIX = "data_columns"
_RUN_WIDE_DENOMINATOR = "estimation_context"

# The two containers the fallback reading has to leave out, and why: the
# reconciliation block names every declared predicate by construction, and
# the gap report is the answer being checked.
_NOT_EVIDENCE_OF_STANDING = frozenset({"type_reconciliation", "data_gap_report"})


def _names_the_answer_stands_on(result: dict) -> frozenset[str]:
    """Which columns this result's answer rests on, read off the envelope.

    Where a number was computed, the answer-level denominators state it:
    each is the column set a hash beside it was taken over, so it is the
    set that estimator was handed. Where identification answered and no
    estimator ran, nothing states it, and the reading falls back to every
    name the document mentions — the same over-approximation the producer
    falls back to, kept because its error blocks MORE than it had to.

    The stated branch is read rather than re-derived, and that is the
    stronger arrangement. Both sides used to infer this the same way from
    the same document, agreeing by construction — a rule that cannot
    fail. On a number the producer now DECLARES the columns and then
    classifies each gap against its own declaration, so the two can
    disagree, and that disagreement is what this rule catches.
    """
    declared: set[str] = set()
    mentioned: set[str] = set()
    stack = [(result, False)]
    while stack:
        node, run_wide = stack.pop()
        if isinstance(node, dict):
            for key, value in node.items():
                if key in _NOT_EVIDENCE_OF_STANDING:
                    continue
                if isinstance(key, str) \
                        and key.endswith(_DENOMINATOR_SUFFIX):
                    if not run_wide and isinstance(value, list):
                        declared.update(
                            c for c in value if isinstance(c, str))
                    continue
                stack.append(
                    (value, run_wide or key == _RUN_WIDE_DENOMINATOR))
        elif isinstance(node, (list, tuple)):
            stack.extend((v, run_wide) for v in node)
        elif isinstance(node, str):
            mentioned.add(node)
    return frozenset(declared or mentioned)


def _classify_observed(n_unique: int, dtype_kind: str) -> str:
    """Pure (n_unique, dtype_kind) -> observed scale — independent re-derivation
    of the producer's rule."""
    if n_unique <= 2:
        return "binary"
    if n_unique <= 20 and dtype_kind in _DISCRETE_DTYPES:
        return "discrete"
    return "continuous"


def _declared_from_scale_domain(declared_scale, declared_domain) -> str | None:
    """Independent re-derivation of the positive declared type. The producer
    records the already-resolved ``declared_scale``; we recompute what it
    SHOULD be from the raw (scale-ish string, domain) to catch a producer that
    recorded an inconsistent resolution."""
    if declared_scale in ("binary", "discrete", "continuous", "nominal"):
        # For scale-driven declarations the recorded value IS the raw scale;
        # nothing further to derive.
        return declared_scale
    if declared_domain is not None:
        return "binary" if len(declared_domain) <= 2 else "discrete"
    return None


def _reconcile(declared, declared_domain, observed, n_unique,
               observed_values) -> str:
    """Independent re-derivation of the verdict. Mirrors dispatch
    ``_reconcile_declared_observed`` but returns the verdict token only."""
    if declared == "continuous":
        if observed in ("binary", "discrete"):
            return "declared_continuous_data_discrete"
        return "ok"
    if declared == "binary":
        if n_unique > 2:
            return "domain_violated"
        return "ok"
    # ``nominal`` is ``discrete`` plus a claim no column can contradict, so
    # it reconciles identically rather than in a branch of its own.
    if declared in ("discrete", "nominal"):
        if observed == "continuous":
            return "domain_violated"
        if declared_domain is not None and observed_values is not None:
            domain_set = set(declared_domain)
            if any(v not in domain_set for v in observed_values):
                return "domain_violated"
        return "ok"
    return "ok"


def verify_type_reconciliation(result: dict) -> None:
    """Audit ``extensions.type_reconciliation`` against its ``data_gap_report``.

    No-op when the result carries no reconciliation block (the estimate path
    only attaches one when a positive declaration disagrees with the data).
    Raises ``VerificationError`` on any inconsistency.
    """
    if not isinstance(result, dict):
        return
    extensions = result.get("extensions") or {}
    recon = extensions.get("type_reconciliation")
    if not recon:
        return
    if not isinstance(recon, dict):
        raise VerificationError(
            "extensions.type_reconciliation must be an object",
            step_index=None, rule=_RULE,
        )
    checks = recon.get("checks")
    if not isinstance(checks, list):
        raise VerificationError(
            "extensions.type_reconciliation.checks must be a list",
            step_index=None, rule=_RULE,
        )

    # 1. Re-derive each check independently.
    expected_gap_signatures: dict[str, str] = {}
    for i, c in enumerate(checks):
        if not isinstance(c, dict):
            raise VerificationError(
                f"type_reconciliation.checks[{i}] must be an object",
                step_index=None, rule=_RULE,
            )
        pred = c.get("predicate")
        n_unique = c.get("n_unique")
        dtype_kind = c.get("dtype_kind")
        observed_values = c.get("observed_values")
        declared_scale = c.get("declared_scale")
        declared_domain = c.get("declared_domain")
        recorded_observed = c.get("observed_scale")
        recorded_verdict = c.get("verdict")

        if not isinstance(pred, str) or not pred:
            raise VerificationError(
                f"type_reconciliation.checks[{i}] has no predicate",
                step_index=None, rule=_RULE,
            )
        if not isinstance(n_unique, int) or not isinstance(dtype_kind, str):
            raise VerificationError(
                f"type_reconciliation check for {pred!r} missing "
                f"n_unique/dtype_kind sufficient statistics",
                step_index=None, rule=_RULE,
            )

        # 1a. Internal consistency of the recorded statistics.
        if observed_values is not None and len(observed_values) != n_unique:
            raise VerificationError(
                f"type_reconciliation check for {pred!r}: recorded "
                f"observed_values has {len(observed_values)} entries but "
                f"n_unique={n_unique}",
                step_index=None, rule=_RULE,
            )

        # 1b. Independent observed-scale classification.
        derived_observed = _classify_observed(n_unique, dtype_kind)
        if derived_observed != recorded_observed:
            raise VerificationError(
                f"type_reconciliation check for {pred!r}: recorded "
                f"observed_scale={recorded_observed!r} but "
                f"(n_unique={n_unique}, dtype={dtype_kind!r}) re-derives to "
                f"{derived_observed!r}",
                step_index=None, rule=_RULE,
            )

        # 1c. Independent declared-type resolution.
        derived_declared = _declared_from_scale_domain(
            declared_scale, declared_domain
        )
        if derived_declared != declared_scale:
            raise VerificationError(
                f"type_reconciliation check for {pred!r}: recorded "
                f"declared_scale={declared_scale!r} is inconsistent with the "
                f"recorded domain {declared_domain!r} (re-derives to "
                f"{derived_declared!r})",
                step_index=None, rule=_RULE,
            )

        # 1d. Independent verdict.
        derived_verdict = _reconcile(
            derived_declared, declared_domain, derived_observed,
            n_unique, observed_values,
        )
        if derived_verdict != recorded_verdict:
            raise VerificationError(
                f"type_reconciliation check for {pred!r}: recorded "
                f"verdict={recorded_verdict!r} but independent re-derivation "
                f"gives {derived_verdict!r}",
                step_index=None, rule=_RULE,
            )
        if derived_verdict == "ok":
            raise VerificationError(
                f"type_reconciliation check for {pred!r} was recorded but "
                f"re-derives to 'ok' — only genuine mismatches should be "
                f"attached",
                step_index=None, rule=_RULE,
            )
        expected_gap_signatures[pred] = derived_verdict

    # 2. Cross-check the attached gaps against the re-derived checks.
    report = result.get("data_gap_report") or {}
    gaps = report.get("gaps", []) or []
    seen_predicates: set[str] = set()
    for gi, gap in enumerate(gaps):
        if gap.get("kind") != "declared_type_data_mismatch":
            continue
        # Recover the predicate from the verifier_check provenance ref.
        pred = None
        for ref in gap.get("provenance", []) or []:
            rid = ref.get("ref_id", "")
            if isinstance(rid, str) and rid.startswith("type_reconciliation:"):
                pred = rid.split(":", 1)[1]
                break
        if pred is None:
            raise VerificationError(
                f"declared_type_data_mismatch gap[{gi}] has no "
                f"'type_reconciliation:<predicate>' verifier_check provenance",
                step_index=None, rule=_RULE,
            )
        if pred not in expected_gap_signatures:
            raise VerificationError(
                f"declared_type_data_mismatch gap[{gi}] cites predicate "
                f"{pred!r} with no backing type_reconciliation check "
                f"(phantom gap)",
                step_index=None, rule=_RULE,
            )
        expected_verdict = expected_gap_signatures[pred]
        if gap.get("signature") != expected_verdict:
            raise VerificationError(
                f"declared_type_data_mismatch gap[{gi}] for {pred!r} has "
                f"signature={gap.get('signature')!r} but the check verdict is "
                f"{expected_verdict!r}",
                step_index=None, rule=_RULE,
            )
        # The finding is the program's and holds on every result; what it
        # costs is this answer's and holds only where the answer stands on
        # the column. Read separately here for the same reason the verdict
        # is: a producer that got the scope wrong would otherwise be graded
        # against its own mistake.
        stands_on = pred in _names_the_answer_stands_on(result)
        expected_severity = "important" if stands_on else "informational"
        if gap.get("severity") != expected_severity:
            raise VerificationError(
                f"declared_type_data_mismatch gap[{gi}] for {pred!r} must be "
                f"severity={expected_severity!r} on a result whose answer "
                f"{'stands on' if stands_on else 'does not stand on'} that "
                f"column; got {gap.get('severity')!r}",
                step_index=None, rule=_RULE,
            )
        expected_blocks = (
            _BLOCKS_BY_VERDICT.get(expected_verdict) if stands_on
            else "interpretation"
        )
        if gap.get("blocks") != expected_blocks:
            raise VerificationError(
                f"declared_type_data_mismatch gap[{gi}] for {pred!r} verdict "
                f"{expected_verdict!r} must block {expected_blocks!r}; got "
                f"{gap.get('blocks')!r}",
                step_index=None, rule=_RULE,
            )
        seen_predicates.add(pred)

    # 3. Every re-derived mismatch must have surfaced as a gap.
    missing = set(expected_gap_signatures) - seen_predicates
    if missing:
        raise VerificationError(
            f"type_reconciliation checks for {sorted(missing)} produced a "
            f"mismatch verdict but no declared_type_data_mismatch gap was "
            f"attached",
            step_index=None, rule=_RULE,
        )
