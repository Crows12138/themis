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


class DataContractError(ValueError):
    """Raised when a DataFrame does not satisfy the numerical estimation
    contract (missing column, wrong dtype, NaN, too-small sample)."""


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
) -> DataContract:
    """Validate ``data`` against the contract and return a DataContract.

    ``required_columns`` must all be present; ``bool_columns`` and
    ``continuous_columns`` are enforced on dtype. A column not listed
    in either typed set is accepted as-is provided it's numeric or bool.

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
            # Auto-detect: bool-like → bool, numeric → float, else reject
            if pd.api.types.is_bool_dtype(series) or _is_bool_like(series):
                normalised[col] = _coerce_bool(series, col)
            elif pd.api.types.is_numeric_dtype(series):
                normalised[col] = series.astype("float64")
            else:
                raise DataContractError(
                    f"column {col!r} has dtype {series.dtype} which is "
                    f"neither bool-like nor numeric"
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
        arr = df[col].to_numpy()
        # Always bytes-of-float for cross-version determinism — bool
        # converts unambiguously to 0.0 / 1.0.
        h.update(arr.astype(np.float64, copy=False).tobytes())
    return h.hexdigest()
