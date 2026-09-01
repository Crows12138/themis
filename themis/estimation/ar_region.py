"""Anderson-Rubin confidence sets as the solution of one quadratic inequality.

The AR test inverts to ``{beta0 : g(beta0) <= 0}`` where ``g`` is a quadratic
form. With ONE endogenous regressor ``g`` is a scalar quadratic and the set is
one of six shapes on the line (Dufour 1997). With ``k`` endogenous regressors
``g`` is a quadratic form on R^k and the set is a quadric region — the same
inversion, one dimension per treatment.

That is the whole content of this module: the scalar case is the ``k = 1``
instance, so the classifier that solves the line lives here and is what the
region's coordinate projections call.

**Why AR rather than a point.** The AR test's size is correct whatever the
first stage does — including when it has less than full rank, which is when a
point estimate of the vector does not exist at all (``q < k`` instruments for
``k`` treatments, or instruments that move the treatments in fewer directions
than there are treatments). The region is then unbounded in the directions the
data cannot pin down, which is the honest answer and not a failure: a method
that refused would be discarding the constraints the data DOES impose, and one
that reported a point would be inventing the rest.

**The inversion.** With ``W`` partialled out of ``y``, ``X`` (n x k) and ``Z``
(n x q), write ``N(b) = (y - Xb)'P_Z(y - Xb)`` for the projected sum of squares
and ``T(b) = (y - Xb)'(y - Xb)`` for the total. The AR statistic is
``[N/q] / [(T - N)/m]`` with ``m = n - |W| - 1 - q`` residual degrees of
freedom (the ``-1`` is the intercept; ``k`` does not enter). Accepting at level
``1 - alpha`` means ``AR <= F(q, m)``, i.e. with ``kappa = q*F(q, m)`` and
``G = m + kappa``::

    G*N(b) - kappa*T(b) <= 0

which expands to ``b'A b - 2 b'B + C <= 0`` with

    A = G*P_xx - kappa*XX      (k x k, symmetric)
    B = G*P_xy - kappa*xy      (k,)
    C = G*P_yy - kappa*yy      (scalar)

where ``P_.. = S_z.' (Z'Z)^-1 S_z.`` are the projections onto the instrument
space. At ``k = 1`` these are exactly the three coefficients
:func:`themis.estimation.iv.anderson_rubin_overid_set` computes.

**Projections.** The interval a reader wants for one coefficient is the
projection of the region onto that axis (Dufour & Taamouti 2005) — valid, and
conservative rather than the other way round. Minimising the quadratic over the
other coordinates is a Schur complement, so each projection is itself a scalar
quadratic inequality and comes back as one of the same six shapes.

References: Anderson & Rubin (1949); Dufour (1997) Econometrica 65(6);
Dufour & Taamouti (2005) Econometrica 73(4).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from ..intervals import CONFIDENCE_LEVEL


#: What the whole region looks like. Coarser than the six shapes a single
#: coordinate can take, because in R^k the question a reader asks first is
#: whether the data pinned the vector down at all — the per-coordinate shape
#: answers the rest. Every member is reachable: `bounded` when A is positive
#: definite and the region is non-empty, `unbounded` when some direction of
#: R^k leaves the quadratic negative forever, `whole_space` when the moments
#: say nothing at all, `empty` when every candidate vector is rejected — which
#: is not a degenerate case but a refutation of the instruments plus the linear
#: model at this level.
REGION_SHAPES = ("bounded", "unbounded", "whole_space", "empty")

#: What one coordinate can look like, on the line. Five of Dufour's shapes
#: plus `empty`; `disconnected` (the complement of an open interval) is the
#: weak-instrument signature.
LINE_SHAPES = (
    "bounded", "disconnected", "unbounded_below", "unbounded_above",
    "whole_line", "empty",
)


def solve_quadratic_set(a: float, b: float, c: float, *, atol: float):
    """Classify + solve ``{t : a*t^2 + b*t + c <= 0}``.

    Returns ``(kind, lower, upper)`` where the finite endpoints are ``None``
    on any open side. ``atol`` is the scale-aware threshold below which the
    leading coefficient counts as zero (the exactly-linear edge case).
    """
    if abs(a) <= atol:
        # Linear: b*t + c <= 0.
        if abs(b) <= atol:
            return ("whole_line", None, None) if c <= 0 else ("empty", None, None)
        root = -c / b
        if b > 0:
            return ("unbounded_below", None, root)   # t <= root
        return ("unbounded_above", root, None)        # t >= root

    disc = b * b - 4.0 * a * c
    if a > 0:
        if disc <= 0:
            # Opens upward, never dips to <= 0 (for a just-identified single
            # instrument the point always satisfies AR == 0, so there this
            # branch is a numerical guard rather than an expected outcome).
            return ("empty", None, None)
        sq = math.sqrt(disc)
        r1, r2 = (-b - sq) / (2 * a), (-b + sq) / (2 * a)
        lo, hi = (r1, r2) if r1 <= r2 else (r2, r1)
        return ("bounded", lo, hi)                    # <= 0 BETWEEN the roots

    # a < 0.
    if disc <= 0:
        return ("whole_line", None, None)             # opens down, <= 0 always
    sq = math.sqrt(disc)
    r1, r2 = (-b - sq) / (2 * a), (-b + sq) / (2 * a)
    lo, hi = (r1, r2) if r1 <= r2 else (r2, r1)
    return ("disconnected", lo, hi)                   # <= 0 OUTSIDE (lo, hi)


@dataclass(frozen=True)
class ARProjection:
    """One coordinate of the region, projected onto its own axis.

    ``kind`` is a member of :data:`LINE_SHAPES`; ``lower`` / ``upper`` carry
    the finite endpoints where they exist. This is a valid confidence interval
    for that one coefficient at the region's level — conservative, because the
    projection of a joint region covers at least as often as the joint region
    does.
    """

    treatment: str
    kind: str
    lower: float | None
    upper: float | None


@dataclass(frozen=True)
class ARRegion:
    """The AR confidence region for the whole coefficient vector.

    ``a_matrix`` / ``b_vector`` / ``c_scalar`` are the inverted quadratic and
    are retained so an independent verifier can re-classify and re-project
    without the raw data. ``center`` is the quadratic's minimiser and exists
    only when ``a_matrix`` is positive definite — it is where the region is
    centred and NOT an estimate of anything; ``point`` is the 2SLS point when
    the instruments identify one, which is a different object and may sit
    outside the region when the over-identifying restrictions are strained.
    """

    treatments: tuple[str, ...]
    shape: str
    a_matrix: tuple[tuple[float, ...], ...]
    b_vector: tuple[float, ...]
    c_scalar: float
    center: tuple[float, ...] | None
    point: tuple[float, ...] | None
    projections: tuple[ARProjection, ...]
    ci_level: float
    kappa: float
    dof_num: int
    dof_denom: int
    n_obs: int
    n_exog: int

    @property
    def bounded(self) -> bool:
        return self.shape == "bounded"


# --------------------------------------------------------------- linear algebra


def _sym(mat: np.ndarray) -> np.ndarray:
    """Symmetrise. ``A`` is a difference of two symmetric matrices, so any
    asymmetry is float noise, and the eigen-solvers below read only one
    triangle — which would silently keep whichever half the noise landed in."""
    return 0.5 * (mat + mat.T)


def _eig_tol(w: np.ndarray, rtol: float) -> float:
    scale = float(np.max(np.abs(w))) if w.size else 0.0
    return rtol * max(scale, 1.0)


def _in_range(vecs_null: np.ndarray, v: np.ndarray, tol: float) -> bool:
    """Is ``v`` orthogonal to the null space (i.e. in the range of a symmetric
    matrix whose null eigenvectors are the columns of ``vecs_null``)?"""
    if vecs_null.shape[1] == 0:
        return True
    return bool(np.max(np.abs(vecs_null.T @ v)) <= tol)


def classify_region(
    a_mat: np.ndarray, b_vec: np.ndarray, c: float, *, rtol: float = 1e-9,
) -> tuple[str, np.ndarray | None]:
    """Classify ``{b : b'A b - 2 b'B + C <= 0}`` into :data:`REGION_SHAPES`.

    Returns ``(shape, center)``; the centre is the quadratic's minimiser and is
    ``None`` unless ``A`` is positive definite (elsewhere there is no unique
    minimiser to report).

    The case split is the whole classification and each branch is a statement
    about a direction in R^k:

    - some eigenvalue negative → along that eigenvector the quadratic falls
      without bound, so the region is non-empty and unbounded;
    - ``A`` positive definite → an ellipsoid, empty iff its minimum is above 0;
    - ``A`` positive semi-definite and singular → constant or linear along the
      null space: linear (``B`` not orthogonal to it) makes it unbounded again,
      constant leaves the minimum over the range to decide empty vs a cylinder;
    - ``A`` and ``B`` both zero → the sign of ``C`` alone, so the whole space
      or nothing.
    """
    a_mat = _sym(np.asarray(a_mat, dtype=float))
    b_vec = np.asarray(b_vec, dtype=float).reshape(-1)
    w, vecs = np.linalg.eigh(a_mat)
    tol = _eig_tol(w, rtol)
    val_tol = rtol * (abs(float(c)) + float(np.abs(b_vec).sum()) + 1.0)

    if float(w[0]) < -tol:
        return "unbounded", None

    zero = np.abs(w) <= tol
    if not zero.any():
        center = np.linalg.solve(a_mat, b_vec)
        minimum = float(c) - float(b_vec @ center)
        if minimum > val_tol:
            return "empty", None
        return "bounded", center

    if not _in_range(vecs[:, zero], b_vec, tol * max(1.0, float(np.abs(b_vec).max() + 1.0))):
        # Linear and non-constant along a null direction: g -> -inf there.
        return "unbounded", None

    if zero.all():
        # A ~ 0 and B ~ 0: the constant C decides, everywhere at once.
        return ("whole_space", None) if float(c) <= val_tol else ("empty", None)

    minimum = float(c) - float(b_vec @ (np.linalg.pinv(a_mat) @ b_vec))
    if minimum > val_tol:
        return "empty", None
    # Non-empty and invariant along the null space, so unbounded.
    return "unbounded", None


def project_coordinate(
    a_mat: np.ndarray, b_vec: np.ndarray, c: float, j: int, *, rtol: float = 1e-9,
) -> tuple[str, float | None, float | None]:
    """Project the region onto coordinate ``j``.

    Minimising ``g`` over the other coordinates is exact when the corresponding
    principal submatrix is positive definite, and the minimised value is again
    a scalar quadratic in the remaining coordinate — the Schur complement — so
    the answer comes back from :func:`solve_quadratic_set`.

    When that submatrix is not positive definite the inner minimum is ``-inf``
    for all but at most one value of the coordinate, so every value survives
    and the projection is the whole line. Reporting the whole line there is the
    safe direction: a projection that is too WIDE is still a valid confidence
    interval, one that is too narrow is not.
    """
    a_mat = _sym(np.asarray(a_mat, dtype=float))
    b_vec = np.asarray(b_vec, dtype=float).reshape(-1)
    k = a_mat.shape[0]
    rest = [i for i in range(k) if i != j]

    if not rest:
        alpha, gamma, delta = float(a_mat[0, 0]), float(b_vec[0]), float(c)
    else:
        a_ss = a_mat[np.ix_(rest, rest)]
        a_sj = a_mat[np.ix_(rest, [j])].reshape(-1)
        b_s = b_vec[rest]
        w, vecs = np.linalg.eigh(a_ss)
        tol = _eig_tol(w, rtol)
        if float(w[0]) < -tol:
            return "whole_line", None, None
        zero = np.abs(w) <= tol
        if zero.any():
            span_tol = tol * max(
                1.0, float(np.abs(a_sj).max()), float(np.abs(b_s).max()) + 1.0)
            null_vecs = vecs[:, zero]
            if not (_in_range(null_vecs, a_sj, span_tol)
                    and _in_range(null_vecs, b_s, span_tol)):
                return "whole_line", None, None
            inv = np.linalg.pinv(a_ss)
        else:
            inv = np.linalg.inv(a_ss)
        alpha = float(a_mat[j, j]) - float(a_sj @ inv @ a_sj)
        gamma = float(b_vec[j]) - float(a_sj @ inv @ b_s)
        delta = float(c) - float(b_s @ inv @ b_s)

    scale = abs(alpha) + abs(gamma) + abs(delta) + 1.0
    return solve_quadratic_set(alpha, -2.0 * gamma, delta, atol=rtol * scale)


# ------------------------------------------------------------------ the region


def region_from_moments(
    m: dict, ci_level: float = CONFIDENCE_LEVEL, *, rtol: float = 1e-9,
) -> ARRegion | None:
    """Build the region from residualised second moments.

    ``m`` carries ``zz`` (q x q), ``zx`` (q x k), ``zy`` (q), ``xx`` (k x k),
    ``xy`` (k), ``yy``, ``n``, ``n_exog``, ``q``, and ``treatments`` (the k
    column names, in the order the matrices use). Returns ``None`` when the AR
    test is undefined: residual degrees of freedom below 1, or ``Z'Z`` singular
    (collinear instruments) — the caller leaves whatever else it has standing.

    ``q < k`` is NOT a refusal. It means no point estimate of the vector exists,
    which is exactly the case this region is for.
    """
    from scipy.stats import f as _f_dist

    q = int(m["q"])
    n = int(m["n"])
    n_exog = int(m["n_exog"])
    treatments = tuple(m["treatments"])
    k = len(treatments)
    dof_denom = n - n_exog - q - 1
    if dof_denom < 1 or k < 1 or q < 1:
        return None

    zz = np.asarray(m["zz"], dtype=float).reshape(q, q)
    zx = np.asarray(m["zx"], dtype=float).reshape(q, k)
    zy = np.asarray(m["zy"], dtype=float).reshape(q)
    xx = np.asarray(m["xx"], dtype=float).reshape(k, k)
    xy = np.asarray(m["xy"], dtype=float).reshape(k)
    yy = float(m["yy"])

    try:
        zz_inv = np.linalg.inv(zz)
    except np.linalg.LinAlgError:
        return None

    p_xx = zx.T @ zz_inv @ zx
    p_xy = zx.T @ zz_inv @ zy
    p_yy = float(zy @ zz_inv @ zy)

    kappa = float(q) * float(_f_dist.ppf(ci_level, q, dof_denom))
    g = dof_denom + kappa
    a_mat = _sym(g * p_xx - kappa * xx)
    b_vec = g * p_xy - kappa * xy
    c = g * p_yy - kappa * yy

    shape, center = classify_region(a_mat, b_vec, c, rtol=rtol)
    projections = tuple(
        ARProjection(treatment=name, kind=kind, lower=lower, upper=upper)
        for name, (kind, lower, upper) in zip(
            treatments,
            (project_coordinate(a_mat, b_vec, c, j, rtol=rtol) for j in range(k)),
        )
    )

    # The 2SLS point, when the instruments move the treatments in k independent
    # directions. It is a different object from the region and is reported
    # beside it rather than as its summary: with q > k it need not lie inside.
    point: tuple[float, ...] | None = None
    if q >= k:
        try:
            point = tuple(float(v) for v in np.linalg.solve(p_xx, p_xy))
        except np.linalg.LinAlgError:
            point = None

    return ARRegion(
        treatments=treatments,
        shape=shape,
        a_matrix=tuple(tuple(float(v) for v in row) for row in a_mat),
        b_vector=tuple(float(v) for v in b_vec),
        c_scalar=float(c),
        center=None if center is None else tuple(float(v) for v in center),
        point=point,
        projections=projections,
        ci_level=float(ci_level),
        kappa=kappa,
        dof_num=q,
        dof_denom=int(dof_denom),
        n_obs=n,
        n_exog=n_exog,
    )


def region_contains(
    region: ARRegion, beta: "tuple[float, ...] | list[float] | np.ndarray",
) -> bool:
    """Is ``beta`` in the region? Evaluates the retained quadratic directly.

    Membership is the region's definition, so this is what a test of the
    classification checks against: a shape is a claim about which vectors
    satisfy the inequality, and this is the inequality.
    """
    b = np.asarray(beta, dtype=float).reshape(-1)
    a_mat = np.asarray(region.a_matrix, dtype=float)
    b_vec = np.asarray(region.b_vector, dtype=float)
    return bool(float(b @ a_mat @ b) - 2.0 * float(b_vec @ b)
                + region.c_scalar <= 0.0)
