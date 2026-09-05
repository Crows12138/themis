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
What it does import is the shared contract — ``themis.gaps``, which both sides
answer to and neither owns — and a sibling rule's reading of the program. A
producer's DECISIONS are what may not be borrowed; the vocabulary a claim is
written in is what makes two readings of it comparable at all.

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
and independently re-derives every CONCLUSION drawn from them. Trusted is
not the same as unknowable, and three things about them are knowable from
the envelope alone: a column's distinct values cannot outnumber the rows
the run says arrived, the recorded value set is a SET and in the order the
producer sorted it into, and each of its members is of the type this
column's own dtype family yields. ``len(observed_values) == n_unique`` was
the whole of what the set was asked, and a length says nothing about what
is in the list.

Two fields here are the PROGRAM's words copied onto the envelope, and
copying them is what made them look like findings. The declared scale and
the declared domain are what the reconciliation was RUN against, so a
verdict re-derived from them agrees with them however they read — which is
what it is for a field to be an input rather than a claim. Held against the
program by :func:`verify_declared_types` they are claims again: the block
says what the program declared, and the program is the one side an answer
may not edit. Resolving a raw ``scale`` and a ``domain`` into one positive
type is transcribed a second time here, for the reason every re-derivation
in this file is.

The sentence beside them is a rendering, and its producer says of what: the
first entry on the gap it files for this column. Two readings of one
statement, able to say different things, and nothing had compared them.
Comparing them calls the one renderer both sides call — the claim is that
this string IS that statement rendered, so a second copy of the templates
would be checking a different claim, and checking it against itself.

Reads only the JSON envelope (dicts), never typed dataclasses, so the audit
also catches serialization-layer bugs. The program-facing door is the one
exception and only on the asked side: what a declaration says is not on the
envelope at all.
"""
from __future__ import annotations

from typing import Any, NoReturn

from ..gaps import describe
from .errors import VerificationError
from .investigation_rules import declarations_of


_RULE = "type_reconciliation_check"

#: What a dtype family says every value read out of that column will be.
#: ``types.envelope_scalar`` delegates the conversion to numpy and then
#: requires one of the five JSON types, so a family that fixes the storage
#: fixes the recorded type exactly.
_VALUE_TYPE_BY_DTYPE: dict[str, type] = {
    "bool": bool, "integer": int, "float": float,
}

#: And the families that fix nothing: an object column holds whatever it
#: holds, a categorical holds its own labels, and ``other`` is the arm that
#: names no family at all. Written down rather than left out. A table whose
#: completeness is its author's memory goes wrong silently — the omitted
#: key simply never matches — so the two sets together are held against the
#: closed ``dtype_kind`` vocabulary of ``query_result.schema.json``, in both
#: directions, by a test. A family added there cannot pass through here
#: unnoticed, which is the only way a partial map can be read as deliberate.
_DTYPE_FIXES_NOTHING = frozenset({"categorical", "object", "other"})

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


def _reject(says: str) -> NoReturn:
    raise VerificationError(says, step_index=None, rule=_RULE)


def _rows_that_arrived(result: dict) -> int | None:
    """How many rows the run says it was given, where it says."""
    context = result.get("estimation_context")
    if not isinstance(context, dict):
        return None
    rows = context.get("sample_size")
    if isinstance(rows, bool) or not isinstance(rows, int):
        return None
    return rows


def _check_the_recorded_values_are_a_set(pred: str, values: list,
                                         dtype_kind: str) -> None:
    """The distinct values, as the field says they are.

    Distinct, because that is what "distinct values" means; in the order
    the producer sorted them into, because it sorted them; and each of the
    type this column's dtype family yields. What is NOT knowable is whether
    a value was in the column at all — the envelope records the set once —
    so a member swapped for another of the same type passes here, and says
    so rather than being counted as held.
    """
    seen = [(type(value).__name__, value) for value in values]
    if len(set(seen)) != len(seen):
        _reject(
            f"type_reconciliation check for {pred!r}: observed_values is the "
            f"column's DISTINCT values and {values!r} repeats one"
        )
    try:
        in_order = sorted(values) == list(values)
    except TypeError:
        # Values of kinds that cannot be ordered against each other. The
        # producer sorted them, so it never made this list; nothing here
        # can say which order it would have been.
        in_order = True
    if not in_order:
        _reject(
            f"type_reconciliation check for {pred!r}: observed_values is "
            f"recorded sorted and {values!r} is not"
        )
    wanted = _VALUE_TYPE_BY_DTYPE.get(dtype_kind)
    if wanted is None:
        return
    for value in values:
        if type(value) is not wanted:
            _reject(
                f"type_reconciliation check for {pred!r}: a {dtype_kind} "
                f"column reads out as {wanted.__name__}, and observed_values "
                f"carries {value!r}"
            )


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
    """Independent re-derivation of the positive declared type, from a raw
    (scale-ish string, domain) pair.

    Asked twice of two different pairs, because "what did the program
    declare" and "is the block's own record of it consistent" are two
    questions. Given the block's already-resolved ``declared_scale`` beside
    its domain it catches a producer that recorded an inconsistent
    resolution; given the PROGRAM's raw scale and domain it is what the
    recorded value has to equal, and that is the question the block alone
    cannot be asked."""
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
    rows = _rows_that_arrived(result)
    expected_gap_signatures: dict[str, str] = {}
    detail_by_predicate: dict[str, object] = {}
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

        # And the rest of what the set is: distinct, in the order it was
        # sorted into, of the type its own dtype family reads out as.
        if isinstance(observed_values, list):
            _check_the_recorded_values_are_a_set(pred, observed_values,
                                                 dtype_kind)

        # 1a2. A column cannot hold more distinct values than the run held
        # rows. The count itself is trusted, as the other statistics are —
        # but the run states the rows beside it, and two recorded numbers
        # about one frame can be asked whether they can both be true.
        if rows is not None and n_unique > rows:
            _reject(
                f"type_reconciliation check for {pred!r}: n_unique="
                f"{n_unique} distinct values in a frame the run records as "
                f"{rows} rows"
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
        detail_by_predicate[pred] = c.get("detail")

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
        # The block's sentence about this column, against the statement it
        # is a rendering OF — which is this gap's first entry, and which
        # its producer says in as many words cannot differ from it. Both
        # sides call the one renderer, because that identity is the claim.
        detail = detail_by_predicate.get(pred)
        said = next(iter(gap.get("describes") or ()), None)
        if isinstance(detail, str) and isinstance(said, dict):
            try:
                spoken: str | None = describe(said)
            except Exception:
                # A statement whose facts do not fill its own holes cannot
                # be rendered, and that finding belongs to the carrier that
                # asks statements about their holes. Re-raising it from
                # here would report one defect as another.
                spoken = None
            if spoken is not None and detail != spoken:
                _reject(
                    f"type_reconciliation check for {pred!r} reads its "
                    f"mismatch as {detail!r}, and the statement on the gap "
                    f"beside it reads {spoken!r}"
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


def verify_declared_types(result: dict, program: Any) -> None:
    """Hold the block's copy of a declaration against the declaration.

    Everything the audit above re-derives, it re-derives FROM the declared
    scale and the declared domain — so those two fields are premises of it,
    and a verdict computed from a rewritten declaration agrees with the
    rewritten declaration. The column they describe is the program's, the
    words are the program's, and the program is the side an answer cannot
    edit; asked of it, they stop being premises.

    Silent where the block is absent, and silent about the observation
    statistics, which the program has nothing to say about. Raises
    ``VerificationError`` where the block reports a declaration the program
    did not make.
    """
    if not isinstance(result, dict):
        return
    extensions = result.get("extensions") or {}
    recon = extensions.get("type_reconciliation")
    if not isinstance(recon, dict):
        return
    checks = recon.get("checks")
    if not isinstance(checks, list):
        return

    declared = declarations_of(program)
    for check in checks:
        if not isinstance(check, dict):
            continue
        pred = check.get("predicate")
        if not isinstance(pred, str):
            continue
        statement = declared.get(pred)
        if statement is None:
            _reject(
                f"type_reconciliation reconciles {pred!r}, which this "
                f"program declares no variable for"
            )
        domain = (list(statement.domain)
                  if statement.domain is not None else None)
        if check.get("declared_domain") != domain:
            _reject(
                f"type_reconciliation check for {pred!r} records the "
                f"declared domain as {check.get('declared_domain')!r}; the "
                f"program declares {domain!r}"
            )
        # What the program's own pair resolves to. A block is written only
        # where that is a positive declaration, so nothing resolving to
        # "didn't say" can be the subject of one.
        scale = _declared_from_scale_domain(statement.scale, statement.domain)
        if scale is None:
            _reject(
                f"type_reconciliation check for {pred!r} reconciles a "
                f"variable the program declares no measurement type for"
            )
        if check.get("declared_scale") != scale:
            _reject(
                f"type_reconciliation check for {pred!r} records the "
                f"declared scale as {check.get('declared_scale')!r}; the "
                f"program's declaration resolves to {scale!r}"
            )
