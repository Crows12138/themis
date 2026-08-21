"""Every digest on one envelope is a digest of one run of one table.

An answer can carry four fingerprints: the run's data contract, the
estimator's own, a bound's, and the one recorded in the derivation step
the verifier walks. Fifteen rules read ``inputs["data_hash"]`` and each
checks the same one thing — that it is sixty-four lowercase hex
characters. None of them compares it to anything. So an envelope whose
bound was computed on one frame and whose point came from another passed
every check there was, and the reader was handed two intervals about two
different tables under one question.

The relation could not be written down before the digests carried their
denominators, because **agreement is not equality**. A Manski bound needs
the exposure and the outcome where the estimator whose point it brackets
also needed the adjustment set, so the two digests on one result SHOULD
differ. What has to hold is that the digest is a function of the
denominator: the same list gives the same digest, a different list gives a
different one, and no answer stands on a column that never arrived.

It lives here rather than inside the fifteen rules because the claim is
between blocks. Fifteen comparisons that do not know about each other
would each be right about one pair and silent about the rest, and the
derivation step — which carries a digest and no denominator — is not
reachable from any of them without extending every rule's declared
parameter set.

The five relations were measured before being written down: across every
envelope the suite produces (312 with at least one digest, in 13 distinct
fingerprint shapes) all five hold with no exceptions. A relation with
exceptions would have been a defect to report or a false rule to drop,
and either way not this.

Reads only the JSON envelope, never typed dataclasses, and imports
nothing from the producer.
"""
from __future__ import annotations

from .errors import VerificationError

_RULE = "fingerprints_agree"

#: How a digest is spelled, and how the columns it covers are spelled.
#: The pair is recognised by name inside one container, which is what
#: makes a route that adds a fifth fingerprint join this audit without
#: being listed anywhere.
_DIGEST_SUFFIX = "data_hash"
_DENOMINATOR_SUFFIX = "data_columns"

#: The one container whose digest is of what ARRIVED rather than of what
#: an answer used: every predicate the program declared, including the
#: ones no query estimated. Every other denominator has to fit inside it.
_RUN_WIDE = "estimation_context"


def _fingerprints(result: dict) -> list[tuple[str, str, tuple[str, ...] | None]]:
    """``(path, digest, denominator-or-None)`` for every digest present."""
    found: list[tuple[str, str, tuple[str, ...] | None]] = []

    def walk(node, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if not isinstance(key, str):
                    continue
                if key.endswith(_DIGEST_SUFFIX) and isinstance(value, str):
                    prefix = key[: -len(_DIGEST_SUFFIX)]
                    columns = node.get(prefix + _DENOMINATOR_SUFFIX)
                    found.append((
                        f"{path}/{key}",
                        value,
                        tuple(columns) if isinstance(columns, list) else None,
                    ))
                else:
                    walk(value, f"{path}/{key}")
        elif isinstance(node, list):
            for i, value in enumerate(node):
                walk(value, f"{path}/{i}")

    walk(result, "")
    return found


def verify_fingerprints_agree(result: dict) -> None:
    """Audit that every digest on ``result`` describes the same table.

    Raises :class:`VerificationError` on the first relation that fails.
    Returns ``None`` on an envelope carrying no digest at all — there is
    nothing to disagree about on an identification-only answer.
    """
    if not isinstance(result, dict):
        raise TypeError(f"result must be a dict; got {type(result).__name__}")

    prints = _fingerprints(result)
    if not prints:
        return

    # 1. A denominator that is not a set of column names is not a
    #    denominator. Distinctness matters because the digest walks the
    #    list: a repeated column would be mixed in twice.
    for path, _, columns in prints:
        if columns is None:
            continue
        if not columns:
            raise VerificationError(
                f"{path} declares an empty denominator; a digest of no "
                f"columns is a digest of nothing",
                step_index=None, rule=_RULE,
            )
        if not all(isinstance(c, str) for c in columns):
            raise VerificationError(
                f"{path} declares a denominator that is not column names: "
                f"{list(columns)!r}",
                step_index=None, rule=_RULE,
            )
        if len(set(columns)) != len(columns):
            raise VerificationError(
                f"{path} declares a denominator with a repeated column "
                f"{sorted({c for c in columns if list(columns).count(c) > 1})!r}"
                f"; the digest walks this list, so a repeat is hashed twice",
                step_index=None, rule=_RULE,
            )

    # 2 and 3. The digest is a function of the denominator. Same list ->
    #    same digest, or two runs are being reported as one; different
    #    list -> different digest, or a digest was copied across blocks
    #    instead of computed (``_hash_frame`` mixes each column's NAME
    #    before its values, so different lists cannot collide short of
    #    breaking SHA-256).
    denominated = [(p, h, c) for p, h, c in prints if c is not None]
    for i, (path_a, digest_a, columns_a) in enumerate(denominated):
        for path_b, digest_b, columns_b in denominated[i + 1:]:
            if columns_a == columns_b and digest_a != digest_b:
                raise VerificationError(
                    f"{path_a} and {path_b} cover the same columns "
                    f"{list(columns_a)!r} but carry different digests "
                    f"({digest_a[:12]}… vs {digest_b[:12]}…); one answer "
                    f"here was computed on a different table",
                    step_index=None, rule=_RULE,
                )
            if columns_a != columns_b and digest_a == digest_b:
                raise VerificationError(
                    f"{path_a} and {path_b} carry one digest "
                    f"{digest_a[:12]}… over different columns "
                    f"({list(columns_a)!r} vs {list(columns_b)!r}); a "
                    f"digest of these two column sets cannot be equal, so "
                    f"this one was copied rather than computed",
                    step_index=None, rule=_RULE,
                )

    # 4. No answer stands on a column that never arrived.
    run_wide = next(
        (c for p, _, c in prints
         if p.split("/")[1:2] == [_RUN_WIDE] and c is not None),
        None,
    )
    if run_wide is not None:
        arrived = set(run_wide)
        for path, _, columns in denominated:
            if path.split("/")[1:2] == [_RUN_WIDE] or columns is None:
                continue
            outside = sorted(set(columns) - arrived)
            if outside:
                raise VerificationError(
                    f"{path} says its answer stands on {outside!r}, which "
                    f"{_RUN_WIDE} does not record as having arrived",
                    step_index=None, rule=_RULE,
                )

    # 5. A digest with no denominator — the derivation steps — has to be
    #    one of the digests that has one. This is what makes the chain
    #    checkable without giving fifteen rules a new declared parameter:
    #    a chain that talks about another table says so here.
    known = {h for _, h, c in prints if c is not None}
    if known:
        for path, digest, columns in prints:
            if columns is None and digest not in known:
                raise VerificationError(
                    f"{path} carries digest {digest[:12]}…, which matches "
                    f"no digest on this envelope that says what it covers; "
                    f"the chain is about a table the answer is not",
                    step_index=None, rule=_RULE,
                )
