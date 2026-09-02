"""What an envelope says about the one table this run read.

Two facts about that table live here — WHICH one it is and HOW BIG it
was — because an envelope records each of them in several places and
nothing had compared the copies.

FIRST, WHICH TABLE. Every digest on one envelope is a digest of one run
of one table.

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

SECOND, HOW BIG. The row count is recorded the same scattered way — once
by the run and again by the point estimate, each bounds row, the
outcome-error block and every derivation step's inputs — and two rules
already state that those must agree, each for the one block its author
was walking (``bounds_rules`` on a Manski row, ``frame_rules`` on a
fitted block; both say "should be the row count" in as many words).
Neither can see ``estimation_context``, so the run's own record — the
number a reader is likeliest to quote the precision off — was the one
nothing compared to anything.

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


# ----------------------------------------------- and how many rows it had

_ROWS = "one_row_count"

#: The name the contract gives one fact: how many rows the table this run
#: read had. One name asked wherever the envelope writes it, not a roster
#: of keys — and asked for EXACTLY, unlike the digests above, because
#: ``reference_sample_size`` is the size of the other table a selection
#: recovery reads and a suffix match would equate two tables.
_COUNT = "sample_size"


def _row_counts(result: dict) -> list[tuple[str, int]]:
    """``(path, value)`` for every place this envelope records that count."""
    found: list[tuple[str, int]] = []

    def walk(node, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == _COUNT:
                    if isinstance(value, int) and not isinstance(value, bool):
                        found.append((f"{path}/{key}", value))
                else:
                    walk(value, f"{path}/{key}")
        elif isinstance(node, list):
            for i, value in enumerate(node):
                walk(value, f"{path}/{i}")

    walk(result, "")
    return found


def verify_one_row_count(result: dict) -> None:
    """Audit that every record of the run's row count is the same number.

    The digests say which table an answer stands on. This says how big it
    was. Across every envelope the suite produces the copies agree —
    forty-six thousand six hundred and forty-nine of them, against four
    hundred and twenty-six disagreements every one of which is a leaf some
    test bent on purpose — and nothing had said they must.

    WHY THE NAME AND NOT EVERY COUNT. ``sufficient_statistics.n`` is the
    same fact under another name, and where it appears it is already held
    against the block around it. The counts that are NOT this fact are
    spelled the same way one level down — ``strata[].n``, ``cells[].n``,
    the treated and control halves of a measurement channel — and those
    are PARTS of the table rather than the table, so a walk that took
    every count would have to tell a part from a whole before it could
    refuse anything, and would refuse honest answers whenever it guessed
    wrong. It never has to guess: the envelope gives the whole its own
    name and no part ever wears it.

    Returns ``None`` on an envelope recording the count once or not at all
    — a single record disagrees with nothing. Raises
    :class:`VerificationError` on the first disagreement.
    """
    if not isinstance(result, dict):
        raise TypeError(f"result must be a dict; got {type(result).__name__}")

    counts = _row_counts(result)
    if len(counts) < 2:
        return

    # The run's own record is the one to name in the message when it is
    # present: it is the copy taken before any estimator ran, so it is the
    # one a reader is being invited to disagree with.
    anchor_path, anchor = next(
        ((p, v) for p, v in counts if p.split("/")[1:2] == [_RUN_WIDE]),
        counts[0],
    )

    for path, value in counts:
        if value != anchor:
            raise VerificationError(
                f"{path} says this answer was computed on {value} rows and "
                f"{anchor_path} says {anchor}; both record the size of the "
                f"one table this run read, so the precision a reader takes "
                f"off one of them belongs to a table the other was not "
                f"computed on",
                step_index=None, rule=_ROWS,
            )
