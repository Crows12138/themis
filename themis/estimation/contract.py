"""Phase 7.1 S.N.1 — data contract for numerical estimation.

Validates that a user-supplied pandas DataFrame conforms to the
expectations of the identification artefacts in a kernel_ast program:

- every predicate referenced by the program's variables / edges / query
  must appear as a column
- bool predicates must have bool-like data (True/False or 0/1)
- continuous predicates must have numeric dtype
- no NaN / missing (first version — relax later if real cases need)
- sample size >= 10 (estimation is not meaningful below this)

Returns a normalised DataFrame + a SHA-256 hash for verifier
reproducibility checks.

See PHASE_7_1_BACKDOOR_NUMERIC_CHARTER.md §1 for the full contract.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

from .. import language as _lang
from ..refusals import EstimatorFailure, Refusal
from .refusal_words import Refuses
from .warning_words import Contract


class DataContractError(_lang.Voiced, ValueError):
    """Raised when a DataFrame does not satisfy the numerical estimation
    contract (missing column, wrong dtype, NaN, too-small sample).

    A :class:`themis.language.Voiced`: it carries the species and this
    occasion's facts, and the sentence is
    :class:`themis.estimation.refusal_words.Refuses`'. Every one of
    these was an f-string at its raise site, which is how a module
    whose whole job is to tell a person what is wrong with their frame
    came to tell them in English.

    ``ValueError`` as well, because that is what a caller has always
    been able to catch.
    """


_MIN_SAMPLE_SIZE = 10
_WARN_SAMPLE_SIZE = 30


@dataclass(frozen=True)
class DataContract:
    """A validated, normalised view of user data alongside its hash.

    Attributes:
        data: the normalised DataFrame (bool columns coerced to bool,
              numeric columns to float64)
        data_hash: SHA-256 hex digest of the canonical serialisation,
                   used by the verifier to confirm reproducibility
        sample_size: row count
        warnings: non-fatal issues surfaced during validation (e.g.
                  sample size < 30), each a statement rather than a
                  sentence — a ``str`` here made this function the author
                  of prose it had no way to write in the reader's language
        columns: tuple of column names in canonical (sorted) order
    """

    data: pd.DataFrame
    data_hash: str
    sample_size: int
    warnings: tuple[_lang.Statement, ...]
    columns: tuple[str, ...]


def validate_data(
    data: pd.DataFrame,
    *,
    required_columns: Iterable[str],
    bool_columns: Iterable[str] = (),
    continuous_columns: Iterable[str] = (),
    presence_columns: Iterable[str] = (),
    quantity_columns: Iterable[str] = (),
) -> DataContract:
    """Validate ``data`` against the contract and return a DataContract.

    ``required_columns`` must all be present; ``bool_columns`` and
    ``continuous_columns`` are enforced on dtype. A column not listed
    in either typed set is accepted as-is provided it's numeric or bool.

    ``quantity_columns`` are the columns this caller will read as NUMBERS
    — its treatment, its outcome, its instrument. Naming them is how an
    estimator says which of its columns cannot be a bare set of levels, and
    it is a statement about the ROLE rather than about the dtype, which is
    why it sits apart from the two sets above: the same column is an
    ordinary covariate in the next estimator along, and there it is fine.
    An estimator that reads no column as a number names none, and one that
    does not know its roles yet — the pre-flight over the whole program\'s
    frame — names none either, because the answer there is "not yet" and a
    guess would refuse a covariate.

    ``presence_columns`` (e.g. a cluster / block id) are a different
    category: they must be present and non-null, but they are a
    *variance concern*, not a causal-model variable. They are carried
    through into ``contract.data`` UNCOERCED (so string / categorical
    cluster ids survive), are NOT subjected to the numeric/bool dtype
    rule, and are EXCLUDED from ``data_hash`` — so the hash (and hence
    the reproducibility fingerprint) is identical whether or not a
    cluster column is supplied.

    Raises DataContractError on any violation that would prevent
    estimation. Emits non-fatal warnings (returned via ``contract.warnings``)
    for conditions that are suspicious but still estimable.
    """
    if not isinstance(data, pd.DataFrame):
        raise DataContractError(Refuses.DATA_IS_NOT_A_FRAME,
                                got=type(data).__name__)

    required = set(required_columns)
    bool_set = set(bool_columns)
    cont_set = set(continuous_columns)
    # A presence column that is also a model variable is already covered
    # by the model rules — drop it from the presence-only set.
    presence = set(presence_columns) - required
    quantities = set(quantity_columns)
    present = set(data.columns)

    missing = (required | presence) - present
    if missing:
        raise DataContractError(Refuses.COLUMNS_ARE_MISSING,
                                columns=sorted(missing))

    sample_size = len(data)
    if sample_size < _MIN_SAMPLE_SIZE:
        raise DataContractError(Refuses.SAMPLE_IS_TOO_SMALL,
                                rows=sample_size,
                                minimum=_MIN_SAMPLE_SIZE)

    warnings: list[_lang.Statement] = []
    if sample_size < _WARN_SAMPLE_SIZE:
        warnings.append(_lang.state(Contract.SAMPLE_IS_BELOW_THE_ADVISORY,
                                    rows=sample_size,
                                    advisory=_WARN_SAMPLE_SIZE))

    # Presence-only columns: existence + non-null, but no dtype coercion
    # and no hash contribution. Validated up front so a null cluster id
    # fails loudly rather than forming a silent degenerate cluster.
    for col in presence:
        if data[col].isna().any():
            raise DataContractError(Refuses.PRESENCE_COLUMN_HAS_GAPS,
                                    column=col)

    # Normalise: coerce bool columns to bool dtype, continuous to float64
    normalised = data.copy()
    for col in required:
        series = normalised[col]
        if series.isna().any():
            raise DataContractError(Refuses.COLUMN_HAS_GAPS, column=col)

        if isinstance(series.dtype, pd.CategoricalDtype) and col in quantities:
            # The declaration and the role disagree, and the declaration is
            # the one that came from a person. Refused here rather than four
            # frames later, where it surfaces as pandas failing to make a
            # float out of a channel name.
            raise DataContractError(
                Refuses.LEVEL_COLUMN_READ_AS_A_NUMBER, column=col,
                levels=list(series.dtype.categories))

        if col in bool_set:
            normalised[col] = _coerce_bool(series, col)
        elif col in cont_set:
            if not pd.api.types.is_numeric_dtype(series):
                raise DataContractError(
                    Refuses.DECLARED_CONTINUOUS_IS_NOT_NUMERIC,
                    column=col, dtype=str(series.dtype))
            normalised[col] = series.astype("float64")
        else:
            # Auto-detect: bool-like → bool, levels → levels, numeric →
            # float, else reject.
            if pd.api.types.is_bool_dtype(series) or _is_bool_like(series):
                normalised[col] = _coerce_bool(series, col)
            elif isinstance(series.dtype, pd.CategoricalDtype):
                # A third kind of column, and the one this contract used to
                # be unable to name. Bool and numeric are both orderings; a
                # set of levels with no order is neither, and coercing it to
                # either is the misspecification, not the fix. It arrives
                # here already marked by ``declared.conform``, which is the
                # only thing that can know — no column shows the absence of
                # an order — and it is carried through untouched so the
                # design build can make it one indicator per level.
                normalised[col] = series
            elif pd.api.types.is_numeric_dtype(series):
                normalised[col] = series.astype("float64")
            else:
                # A labelled column with a declared domain never reaches
                # here — ``declared.conform`` places it on its levels before
                # the frame arrives. What is left is a column nothing said
                # anything about, and the fix is the declaration rather than
                # a re-encoding: the dtype is the symptom, and naming it is
                # what sent people to astype() instead.
                raise DataContractError(
                    Refuses.LABELS_WITH_NO_DECLARED_ORDER,
                    column=col, dtype=str(series.dtype))

    # Restrict to required columns in canonical order for the hash. The
    # hash covers ONLY model columns, so adding a presence (cluster)
    # column leaves the fingerprint unchanged.
    columns = tuple(sorted(required))
    subset = normalised[list(columns)]
    data_hash = _hash_frame(subset)

    # The returned frame additionally carries presence-only columns
    # (uncoerced) so downstream estimators can read e.g. the cluster id.
    # Presence columns are appended after the canonical model columns.
    if presence:
        extra = sorted(presence)
        data_view = normalised[list(columns) + extra]
    else:
        data_view = subset

    return DataContract(
        data=data_view,
        data_hash=data_hash,
        sample_size=sample_size,
        warnings=tuple(warnings),
        columns=columns,
    )


def within_the_stratum(
    contract: DataContract, stratum: Iterable[tuple[str, object]],
) -> DataContract:
    """The same contract read on the rows a question's stratum names.

    A question conditioning on ``Z=z`` asks about the people in that
    stratum, and every number answering it — the point, the interval, the
    sensitivity beside it — is theirs. The columns, their types and their
    completeness are facts about the whole frame and were settled before
    this; what is settled here is which rows the estimate is about.

    The fingerprint moves with the rows: ``data_hash`` is recomputed over
    the same columns on the restricted frame, so two numbers taken within
    different strata of one table cannot share a fingerprint, and the row
    count the contract reports is the stratum's own. The minimum is asked
    again for the same reason it was asked of the table: under it what
    comes out is the arithmetic of a few rows, and a stratum that thin is
    refused rather than answered from the rows outside it. A stratum on a
    continuous column asks for equality with a point and lands here too,
    which is the honest answer to a question the data cannot hold.

    The two ways this refuses are two different facts and leave by two
    doors. A column the frame does not have is the frame's: no question
    about that stratum can be answered from these rows, and it is a
    contract error like every other missing column. A stratum the frame
    holds too few rows in is the QUESTION's: the frame is fine and the
    people asked about are barely in it, which is an estimator refusing to
    speak — so it is raised as one, reaches the envelope through the same
    door every other refusal does, and leaves the queries beside it alone.

    ``stratum`` is a sequence of ``(column, value)`` pairs, in the
    question's order. An empty one returns the contract unchanged: a
    question naming no stratum is about the whole table.
    """
    held = tuple(stratum)
    if not held:
        return contract
    spelt = ", ".join(f"{column}={value}" for column, value in held)
    missing = sorted({column for column, _ in held
                      if column not in contract.data.columns})
    if missing:
        raise DataContractError(Refuses.THE_STRATUM_IS_NOT_IN_THE_DATA,
                                stratum=spelt, columns=missing)
    keep = pd.Series(True, index=contract.data.index)
    for column, value in held:
        keep &= contract.data[column] == value
    rows = contract.data[keep].reset_index(drop=True)
    if len(rows) < _MIN_SAMPLE_SIZE:
        raise EstimatorFailure(Refusal.TOO_FEW_ROWS_IN_THE_STRATUM_ASKED,
                               stratum=spelt, rows=len(rows),
                               minimum=_MIN_SAMPLE_SIZE)
    # The advisory is about the rows a number was fitted on, so the whole
    # table's copy of it is dropped and this stratum's asked afresh.
    whole_said = _lang.state(Contract.SAMPLE_IS_BELOW_THE_ADVISORY,
                             rows=contract.sample_size,
                             advisory=_WARN_SAMPLE_SIZE)
    warnings = [w for w in contract.warnings if w != whole_said]
    if len(rows) < _WARN_SAMPLE_SIZE:
        warnings.append(_lang.state(Contract.SAMPLE_IS_BELOW_THE_ADVISORY,
                                    rows=len(rows),
                                    advisory=_WARN_SAMPLE_SIZE))
    return DataContract(
        data=rows,
        data_hash=_hash_frame(rows[list(contract.columns)]),
        sample_size=len(rows),
        warnings=tuple(warnings),
        columns=contract.columns,
    )


def _is_bool_like(series: pd.Series) -> bool:
    """True iff all non-null values are in {0, 1, True, False}."""
    if not pd.api.types.is_numeric_dtype(series):
        return False
    unique = set(pd.unique(series.dropna()))
    return unique.issubset({0, 1, True, False, 0.0, 1.0})


def _coerce_bool(series: pd.Series, col_name: str) -> pd.Series:
    """Coerce a bool-like series to a clean bool dtype; raise if not bool-like."""
    if pd.api.types.is_bool_dtype(series):
        return series.astype(bool)
    unique = set(pd.unique(series))
    allowed = {0, 1, True, False, 0.0, 1.0}
    if not unique.issubset(allowed):
        raise DataContractError(
            Refuses.DECLARED_BOOL_HAS_OTHER_VALUES, column=col_name,
            values=sorted(
                (v for v in unique if v not in allowed), key=str))
    return series.astype(bool)


def _hash_frame(df: pd.DataFrame) -> str:
    """Canonical SHA-256 hex of a DataFrame — sorted columns, numpy
    bytes of each column concatenated. Deterministic across runs and
    pandas versions (doesn't rely on pickle).
    """
    h = hashlib.sha256()
    for col in df.columns:
        h.update(col.encode("utf-8"))
        series = df[col]
        if isinstance(series.dtype, pd.CategoricalDtype):
            # Levels have no numeric reading, so what gets hashed is what
            # they are: the labels, then each row's position among them.
            # Both halves matter — the labels are the data, and their order
            # is what fixed the level the design leaves out, so two runs
            # that differ only in which level was the reference fitted
            # different matrices and must not share a fingerprint.
            for level in series.cat.categories:
                h.update(str(level).encode("utf-8"))
            h.update(series.cat.codes.to_numpy().astype(np.int64).tobytes())
            continue
        # Always bytes-of-float for cross-version determinism — bool
        # converts unambiguously to 0.0 / 1.0.
        h.update(series.to_numpy().astype(np.float64, copy=False).tobytes())
    return h.hexdigest()


def integer_valued(values) -> bool:
    """Whether every observed value is a whole number.

    The question three estimators each had to answer and each answered for
    itself, because the normalisation above widens every numeric model
    column to float64 and dtype then stops distinguishing an integer-coded
    category from a measurement. Integer-valuedness survives the widening;
    dtype does not — so the fact the callers need is this one, and it
    belongs beside the cast that makes it necessary rather than three
    times downstream of it.

    Finiteness is part of the answer and not a separate guard beside it:
    ``np.round(inf)`` is ``inf``, so a bare comparison against the rounded
    value calls an infinity a whole number. Two of the three rewrites
    carried the guard and one did not — which is what independent rewrites
    look like as against copies, and the one without it accepted an
    infinite stratum level.

    An empty set is vacuously integer-valued: there is no value in it that
    is not one. A caller that cannot work with no values is asking a
    different question and asks it itself; folding that in here produced
    "an empty column is continuous", which is a statement about a column
    with nothing in it.

    The caller decides whether the column is numeric at all — labels are
    levels by construction and never reach this question.
    """
    array = np.asarray(pd.Series(values).dropna().to_numpy(), dtype=float)
    return bool(
        np.all(np.isfinite(array)) and np.all(array == np.round(array))
    )
