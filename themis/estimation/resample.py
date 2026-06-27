"""Shared bootstrap resampler — i.i.d. rows or whole clusters.

Every data estimator's percentile-bootstrap CI draws B resamples and
refits. By default that draw is an i.i.d. row resample
(``rng.integers(0, n, size=n)``), which assumes independent
observations. When the data has within-cluster dependence (families /
pedigrees, repeated measures, schools), i.i.d. resampling
UNDERESTIMATES the sampling variance, so the percentile CI comes out
too narrow (anti-conservative).

This module centralises the draw so every estimator routes through one
helper:

- ``groups is None`` → i.i.d. row resample, byte-identical to the
  legacy inline ``rng.integers(0, n, size=n)`` (same rng consumption).
- ``groups`` supplied → Cameron-Gelbach-Miller *pairs cluster
  bootstrap* (Cameron & Miller 2015, "A Practitioner's Guide to
  Cluster-Robust Inference", §3.3): draw G cluster ids with
  replacement from the G unique clusters, then concatenate ALL rows of
  the drawn clusters. The resampled frame keeps whole clusters intact,
  so the within-cluster correlation structure is preserved and the
  bootstrap distribution reflects the true (cluster-level) sampling
  variability.

The helper returns POSITIONAL indices into a frame of length ``n``, so
callers use them exactly like the old inline draw: ``df.iloc[idx]``.
Note the cluster draw can return a frame whose length differs from
``n`` (clusters have unequal sizes) — that is correct and expected for
the pairs cluster bootstrap.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def resample_indices(
    n: int,
    rng: np.random.Generator,
    groups: np.ndarray | None = None,
) -> np.ndarray:
    """Return positional indices for one bootstrap replicate.

    Parameters
    ----------
    n: number of rows in the frame being resampled.
    rng: a seeded ``numpy.random.Generator`` (deterministic draws).
    groups: optional length-``n`` array of cluster labels, positionally
        aligned with the frame. ``None`` → i.i.d. row resample.

    Returns
    -------
    A 1-D ``int`` array of positional indices. For the i.i.d. path the
    length is exactly ``n``; for the cluster path it is the sum of the
    sizes of the G drawn clusters.
    """
    if groups is None:
        # Byte-identical to the legacy inline draw — same rng state
        # consumption, so cluster=None reproduces existing results.
        return rng.integers(0, n, size=n)

    groups = np.asarray(groups)
    if len(groups) != n:
        raise ValueError(
            f"groups length {len(groups)} does not match frame length {n}"
        )
    # Contiguous 0..G-1 codes in first-appearance order (deterministic,
    # independent of label dtype: ints, strings, categoricals all work).
    codes = pd.factorize(groups, sort=False)[0]
    n_clusters = int(codes.max()) + 1 if len(codes) else 0
    if n_clusters == 0:
        return rng.integers(0, n, size=n)

    positions = np.arange(n)
    cluster_positions = [positions[codes == g] for g in range(n_clusters)]

    drawn = rng.integers(0, n_clusters, size=n_clusters)
    return np.concatenate([cluster_positions[g] for g in drawn])


def cluster_labels(
    data: pd.DataFrame,
    cluster: str,
    *,
    expected_n: int,
) -> np.ndarray:
    """Extract the cluster-label array for a column, with validation.

    The cluster column is a *variance concern*, not a causal-model
    node — it is never coerced to bool/float, never added to the model
    design, and never part of the data hash. This helper just pulls the
    raw labels (any hashable dtype) positionally aligned with the
    estimator's rows.

    Raises ``KeyError`` if the column is absent, ``ValueError`` if its
    length disagrees with the model frame or it contains nulls (a null
    cluster id would silently form its own degenerate cluster).
    """
    if cluster not in data.columns:
        raise KeyError(
            f"cluster column {cluster!r} not found in data columns "
            f"{list(data.columns)}"
        )
    labels = data[cluster].to_numpy()
    if len(labels) != expected_n:
        raise ValueError(
            f"cluster column {cluster!r} has length {len(labels)} but the "
            f"model frame has {expected_n} rows"
        )
    if pd.isna(labels).any():
        raise ValueError(
            f"cluster column {cluster!r} contains null values; every row "
            f"must carry a cluster id for the cluster bootstrap"
        )
    return labels
