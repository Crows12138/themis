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


class DataContractError(ValueError):
    """Raised when a DataFrame does not satisfy the numerical estimation
    contract (missing column, wrong dtype, NaN, too-small sample)."""


#: What this module says to a person when a column cannot serve the role
#: the caller needs of it. The neighbouring refusals here are still written
#: in one language and are registered as such (#391); this one is new, and a
#: new sentence has no reason to arrive already in debt.
_SAID: dict[str, _lang.Words] = {
    "level_column_read_as_a_number": {
        "zh": "\u5217 {column} \u58f0\u660e\u4e3a nominal\uff08{levels} \u8fd9\u51e0\u6863\u4e4b\u95f4"
              "\u6ca1\u6709\u5927\u5c0f\u4e4b\u5206\uff09\uff0c\u800c\u8fd9\u4e2a\u4f30\u8ba1\u91cf\u8981\u628a\u5b83\u5f53\u6210"
              "\u4e00\u4e2a\u6570\u6765\u8bfb\uff1a\u5904\u7406\u5217\u3001\u7ed3\u5c40\u5217\u3001\u5de5\u5177\u53d8\u91cf"
              "\u90fd\u5fc5\u987b\u662f\u80fd\u6bd4\u5927\u5c0f\u7684\u91cf\u3002\u6ca1\u6709\u5927\u5c0f\u4e4b\u5206\u7684\u5217"
              "\u53ea\u80fd\u8fdb\u8c03\u6574\u96c6\u3002\u5982\u679c\u5b83\u672c\u6765\u5c31\u6709\u5927\u5c0f\uff08\u6bd4\u5982"
              "\u5242\u91cf\u6863\uff09\uff0c\u628a scale \u6539\u6210 discrete\uff1b\u5982\u679c\u5b83\u786e\u5b9e\u662f\u5206\u7c7b"
              "\u800c\u4f60\u8981\u6bd4\u7684\u662f\u5176\u4e2d\u4e24\u6863\uff0c\u628a\u90a3\u4e24\u6863\u505a\u6210\u4e00\u4e2a"
              "\u4e8c\u503c\u5217\uff0c\u5176\u4f59\u884c\u4e0d\u53c2\u4e0e\u8fd9\u6b21\u5bf9\u6bd4",
        "en": "column {column} is declared nominal \u2014 its levels {levels} have "
              "no greater and lesser \u2014 and this estimator reads it as a "
              "number: a treatment, an outcome and an instrument all have to "
              "be quantities. A column with no order can only enter an "
              "adjustment set. If it does have an order (dose bands, say), "
              "declare `scale: \"discrete\"`; if it really is categorical and "
              "the contrast you want is between two of its levels, make those "
              "two a binary column and leave the other rows out of it",
    },
}


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
                  sample size < 30)
        columns: tuple of column names in canonical (sorted) order
    """

    data: pd.DataFrame
    data_hash: str
    sample_size: int
    warnings: tuple[str, ...]
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
        raise DataContractError(
            f"data must be a pandas DataFrame, got {type(data).__name__}"
        )

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
        raise DataContractError(
            f"data missing required columns: {sorted(missing)}"
        )

    sample_size = len(data)
    if sample_size < _MIN_SAMPLE_SIZE:
        raise DataContractError(
            f"sample size {sample_size} is below the minimum "
            f"({_MIN_SAMPLE_SIZE}) for numerical estimation"
        )

    warnings: list[str] = []
    if sample_size < _WARN_SAMPLE_SIZE:
        warnings.append(
            f"样本量 {sample_size} 低于建议阈值 "
            f"（{_WARN_SAMPLE_SIZE}）；置信区间会很宽"
        )

    # Presence-only columns: existence + non-null, but no dtype coercion
    # and no hash contribution. Validated up front so a null cluster id
    # fails loudly rather than forming a silent degenerate cluster.
    for col in presence:
        if data[col].isna().any():
            raise DataContractError(
                f"presence column {col!r} contains NaN; every row must "
                f"carry a value (e.g. a cluster id) for it to be usable"
            )

    # Normalise: coerce bool columns to bool dtype, continuous to float64
    normalised = data.copy()
    for col in required:
        series = normalised[col]
        if series.isna().any():
            raise DataContractError(
                f"column {col!r} contains NaN; missing values are not "
                f"supported in the first version of the contract"
            )

        if isinstance(series.dtype, pd.CategoricalDtype) and col in quantities:
            # The declaration and the role disagree, and the declaration is
            # the one that came from a person. Refused here rather than four
            # frames later, where it surfaces as pandas failing to make a
            # float out of a channel name.
            raise DataContractError(_lang.fill(
                _SAID["level_column_read_as_a_number"], _lang.DEFAULT,
                column=col, levels=list(series.dtype.categories)))

        if col in bool_set:
            normalised[col] = _coerce_bool(series, col)
        elif col in cont_set:
            if not pd.api.types.is_numeric_dtype(series):
                raise DataContractError(
                    f"column {col!r} is declared continuous but dtype "
                    f"is {series.dtype}; expected numeric"
                )
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
                    f"column {col!r} holds labels ({series.dtype}) and the "
                    f"program declares no domain for it, so there is no "
                    f"order to place them on. Declare the variable's "
                    f"`domain` (its levels, in the order you mean) and the "
                    f"column is usable as it stands"
                )

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
            f"column {col_name!r} declared bool but has values "
            f"{sorted(v for v in unique if v not in allowed)!r} outside "
            f"{{0, 1, True, False}}"
        )
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
