"""Independent audit of a lagged-discovery result.

A learned graph is the one output where "re-run it and see" is not an audit:
re-running the same search on the same data reproduces its bugs exactly. What
can be audited is whether the returned object has the properties it claims,
and PCMCI's two stages each have one.

- **The parent set** is claimed to be a fixpoint: every parent is dependent
  on the target given the OTHER parents, and every non-parent independent
  given ALL of them. With every candidate at a strictly earlier time than the
  target — hence a non-descendant of it — and no future variable available to
  condition on, that pair of properties is what a parent set means under
  causal sufficiency and faithfulness. It is checkable without re-running the
  search, which is exactly why the producer runs grow-shrink to a fixpoint
  rather than the paper's PC1, whose output has no such property.
- **The MCI stage** is claimed to have tested each candidate link against the
  target's parents plus the driver's own parents shifted back by the lag. The
  conditioning set is a function of the recorded parents, so it is rebuilt
  here and the recorded one held to it — a link tested against a smaller set
  than it says is the way an MCI result would silently become an ordinary
  partial-correlation result.

Both rest on the Fisher-Z test being a pure function of the correlation
matrix, which is what makes that matrix a complete sufficient statistic.

Independence pin: ``_partial_corr`` / ``_fisher_z_pvalue`` here are a second,
standalone transcription. They read only the recorded statistic; a bug in the
producer's search or in its test cannot mask itself through them.

Trust boundary (stated honestly): the recorded correlation matrix is taken as
given — it is pinned to the fitted data by ``data_hash``, but this function
does not re-read the raw data to recompute it, and it therefore cannot see a
misaligned lag construction. What it guarantees is: *given the recorded
statistic*, the parent sets satisfy the definition at the stated alpha, every
recorded test statistic and p-value is correct, every MCI test conditioned on
what MCI conditions on, and the detected set is exactly the set those tests
support. That catches a search bug, a corrupted or reordered result, a
fabricated link, and a dropped one.
"""
from __future__ import annotations

import numpy as np

from .errors import VerificationError

_P_ATOL = 1e-6
_R_ATOL = 1e-6


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def _require_list(value: object, message: str) -> list:
    if not isinstance(value, list):
        raise VerificationError(message)
    return value


def _require_non_empty_list(value: object, message: str) -> list:
    checked = _require_list(value, message)
    if not checked:
        raise VerificationError(message)
    return checked


def _require_dict(value: object, message: str) -> dict:
    if not isinstance(value, dict):
        raise VerificationError(message)
    return value


def _require_str(value: object, message: str) -> str:
    if not isinstance(value, str):
        raise VerificationError(message)
    return value


def _require_int(value: object, message: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise VerificationError(message)
    return value


def _require_number(value: object, message: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise VerificationError(message)
    return float(value)


# --- Fisher-Z — independent reimplementation ---------------------------------


def _partial_corr(R: np.ndarray, i: int, j: int, cond: tuple[int, ...]) -> float:
    if not cond:
        return float(R[i, j])
    idx = [i, j, *cond]
    sub = R[np.ix_(idx, idx)]
    try:
        P = np.linalg.inv(sub)
    except np.linalg.LinAlgError:
        P = np.linalg.pinv(sub)
    denom = np.sqrt(P[0, 0] * P[1, 1])
    if denom <= 0.0:
        return 0.0
    return float(-P[0, 1] / denom)


def _fisher_z_pvalue(
    R: np.ndarray, i: int, j: int, cond: tuple[int, ...], n: int
) -> float:
    from scipy import stats

    r = _partial_corr(R, i, j, cond)
    r = max(min(r, 0.999999999999), -0.999999999999)
    z = float(np.arctanh(r))
    dof = n - len(cond) - 3
    if dof <= 0:
        return 0.0
    stat = np.sqrt(dof) * abs(z)
    return float(2.0 * (1.0 - stats.norm.cdf(stat)))


# --- the layout, derived here rather than parsed off the names ---------------


def _layout(variables: list[str], depth: int) -> tuple[str, ...]:
    """The design's column names in index order.

    A second transcription of the producer's rule, for the reason every other
    piece of arithmetic here is one: reading the recorded names back would
    make the index a thing the artifact asserts about itself. Rebuilding it
    makes a reordered design visible.
    """
    return tuple(
        f"{var}@t" if lag == 0 else f"{var}@t-{lag}"
        for var in variables
        for lag in range(depth + 1)
    )


def _index(position: int, lag: int, depth: int) -> int:
    return position * (depth + 1) + lag


def verify_lagged_discovery(result: dict) -> None:
    """Independently audit a lagged-discovery result dict (the artifact from
    ``lagged_discovery_to_dict`` / ``themis_discover_lagged_graph``).

    Returns ``None`` on accept; raises ``VerificationError`` on any structural
    inconsistency, an ill-formed sufficient statistic, a recorded test that
    disagrees with the independent recomputation, an MCI test run on the wrong
    conditioning set, or a parent set that does not satisfy its own definition
    at its alpha.
    """
    _require(isinstance(result, dict), "result must be a dict")
    _require(
        result.get("kind") == "lagged_discovery",
        f"not a lagged_discovery result (kind={result.get('kind')!r})",
    )

    variables = [
        _require_str(v, f"variable name {v!r} must be a string")
        for v in _require_non_empty_list(
            result.get("variables"), "variables must be a non-empty list"
        )
    ]
    _require(len(set(variables)) == len(variables), "duplicate variable names")
    _require(len(variables) >= 2, "a lagged graph needs at least two series")
    position = {var: i for i, var in enumerate(variables)}

    max_lag = _require_int(result.get("max_lag"), "max_lag must be an int >= 1")
    _require(max_lag >= 1, "max_lag must be an int >= 1")
    depth = _require_int(result.get("depth"), "depth must be an int")
    _require(
        depth == 2 * max_lag,
        f"depth is {depth} but MCI conditions on the driver's parents shifted "
        f"by up to max_lag, so the design has to reach {2 * max_lag}",
    )
    alpha = _require_number(result.get("alpha"), "alpha out of range")
    _require(0 < alpha < 1, "alpha out of range")
    n = _require_int(result.get("sample_size"), "sample_size must be an int > 3")
    _require(n > 3, "sample_size must be an int > 3")
    _require(
        result.get("test") == "fisherz",
        f"unknown test type {result.get('test')!r}",
    )

    columns = _layout(variables, depth)
    width = len(columns)
    _require(
        _require_list(result.get("columns"), "columns must be a list")
        == list(columns),
        "columns are not the design this method builds from these variables "
        "at this depth; the recorded layout and the index formula every test "
        "below is read by would refer to different variables",
    )

    try:
        R = np.asarray(result.get("correlation"), dtype=float)
    except (TypeError, ValueError) as exc:
        raise VerificationError(
            f"correlation must be a {width}x{width} matrix of numbers"
        ) from exc
    _require(R.shape == (width, width),
             f"correlation shape {R.shape} != ({width}, {width})")
    _require(np.allclose(R, R.T, atol=1e-8),
             "correlation matrix is not symmetric")
    _require(np.allclose(np.diag(R), 1.0, atol=1e-6),
             "correlation diagonal is not 1")
    _require(float(np.max(np.abs(R))) <= 1.0 + 1e-6,
             "correlation matrix has an entry outside [-1, 1]")
    _require(float(np.min(np.linalg.eigvalsh(R))) >= -1e-6,
             "correlation matrix is not positive semi-definite")

    # --- the parent sets, and the definition they claim -----------------------
    parents: dict[str, tuple[int, ...]] = {}
    entries = _require_list(result.get("parents"), "parents must be a list")
    _require(
        len(entries) == len(variables),
        f"parents must have one entry per variable; got {len(entries)} for "
        f"{len(variables)} series",
    )
    for entry in entries:
        block = _require_dict(entry, "each parents entry must be a record")
        target = _require_str(block.get("target"),
                              "each parents entry must name its target")
        _require(target in position, f"parents entry for unknown {target!r}")
        _require(target not in parents, f"two parent sets for {target!r}")
        found: list[int] = []
        for p in _require_list(block.get("parents"),
                               f"parents for {target!r} must be a list"):
            found.append(_link_index(p, position, depth, max_lag,
                                     f"parents for {target!r}"))
        _require(len(set(found)) == len(found),
                 f"parents for {target!r} name the same link twice")
        parents[target] = tuple(sorted(found))
    _require(set(parents) == set(variables),
             "parents must cover exactly the variables")

    candidates = tuple(
        _index(i, lag, depth)
        for i in range(len(variables))
        for lag in range(1, max_lag + 1)
    )

    recorded_parent_tests: dict[tuple[str, str, int], dict] = {}
    for entry in _require_list(result.get("parent_tests"),
                               "parent_tests must be a list"):
        block = _require_dict(entry, "each parent_tests entry must be a record")
        key = (
            _require_str(block.get("target"), "a parent test must name a target"),
            _require_str(block.get("driver"), "a parent test must name a driver"),
            _require_int(block.get("lag"), "a parent test must name a lag"),
        )
        _require(key not in recorded_parent_tests,
                 f"two parent tests for {key}")
        recorded_parent_tests[key] = block

    expected_keys = {
        (target, *_as_link(c, variables, depth))
        for target in variables for c in candidates
    }
    _require(
        set(recorded_parent_tests) == expected_keys,
        "parent_tests must cover exactly one test per candidate per target; "
        f"missing {len(expected_keys - set(recorded_parent_tests))}, extra "
        f"{len(set(recorded_parent_tests) - expected_keys)}",
    )

    for target in variables:
        t_idx = _index(position[target], 0, depth)
        kept = set(parents[target])
        for c in candidates:
            driver, lag = _as_link(c, variables, depth)
            rec = recorded_parent_tests[(target, driver, lag)]
            if c in kept:
                role, cond = "parent", tuple(x for x in parents[target] if x != c)
                ok_expr = "dependent (p <= alpha)"
            else:
                role, cond = "not_a_parent", parents[target]
                ok_expr = "independent (p > alpha)"
            pv = _fisher_z_pvalue(R, t_idx, c, cond, n)
            passed = pv <= alpha if role == "parent" else pv > alpha
            _require(
                passed,
                f"the parent set of {target!r} is not a fixpoint: "
                f"{driver}@t-{lag} is a "
                f"{'parent' if role == 'parent' else 'non-parent'} but not "
                f"{ok_expr} given "
                f"{sorted(columns[x] for x in cond)} "
                f"(p={pv:.4g}, alpha={alpha})",
            )
            _check_test(rec, R, n, columns, t_idx, c, cond, pv, passed,
                        role=role, what=f"parent test {driver}@t-{lag} "
                                        f"-> {target}")

    # --- the MCI stage --------------------------------------------------------
    recorded_links: dict[tuple[str, int, str], dict] = {}
    for entry in _require_list(result.get("links"), "links must be a list"):
        block = _require_dict(entry, "each links entry must be a record")
        link = (
            _require_str(block.get("driver"), "a link must name a driver"),
            _require_int(block.get("lag"), "a link must name a lag"),
            _require_str(block.get("target"), "a link must name a target"),
        )
        _require(link not in recorded_links, f"two links for {link}")
        recorded_links[link] = block
    expected_links = {
        (*_as_link(c, variables, depth), target)
        for target in variables for c in candidates
    }
    _require(
        set(recorded_links) == expected_links,
        "links must cover exactly one MCI test per candidate link, detected "
        "or not; a list of only the detected ones cannot be checked for "
        f"having dropped one. Missing "
        f"{len(expected_links - set(recorded_links))}, extra "
        f"{len(set(recorded_links) - expected_links)}",
    )

    for target in variables:
        t_idx = _index(position[target], 0, depth)
        for c in candidates:
            driver, lag = _as_link(c, variables, depth)
            rec = recorded_links[(driver, lag, target)]
            cond = _mci_conditions(
                c, t_idx, driver=driver, target=target, driver_lag=lag,
                parents=parents, variables=variables, position=position,
                depth=depth)
            pv = _fisher_z_pvalue(R, t_idx, c, cond, n)
            detected = pv <= alpha
            _check_test(rec, R, n, columns, t_idx, c, cond, pv, detected,
                        role=None,
                        what=f"MCI test {driver}@t-{lag} -> {target}",
                        verdict_key="detected")


def _as_link(index: int, variables: list[str], depth: int) -> tuple[str, int]:
    pos, lag = divmod(index, depth + 1)
    return variables[pos], lag


def _link_index(entry, position, depth, max_lag, what) -> int:
    block = _require_dict(entry, f"{what}: each parent must be a record")
    driver = _require_str(block.get("driver"), f"{what}: a parent needs a driver")
    lag = _require_int(block.get("lag"), f"{what}: a parent needs a lag")
    _require(driver in position, f"{what}: unknown driver {driver!r}")
    _require(
        1 <= lag <= max_lag,
        f"{what}: lag {lag} is outside the candidate range 1..{max_lag}, so "
        f"it names a link this run never looked for",
    )
    return _index(position[driver], lag, depth)


def _mci_conditions(
    d_idx: int, t_idx: int, *, driver: str, target: str, driver_lag: int,
    parents, variables, position, depth: int,
) -> tuple[int, ...]:
    """What an MCI test has to condition on, rebuilt from the recorded parents.

    The second half — the driver's own parents, shifted back by the link's lag
    — is the paper's contribution and the thing that makes the p-value
    trustworthy under autocorrelation. It is also the half that would vanish
    without trace if a producer dropped it, turning MCI into an ordinary
    partial correlation with an MCI label, so it is rebuilt rather than read.
    """
    cond = {x for x in parents[target] if x != d_idx}
    for their_driver, their_lag in (
        _as_link(x, variables, depth) for x in parents[driver]
    ):
        shifted = their_lag + driver_lag
        if shifted <= depth:
            cond.add(_index(position[their_driver], shifted, depth))
    cond.discard(t_idx)
    return tuple(sorted(cond))


def _check_test(
    rec: dict, R, n: int, columns, i: int, j: int, cond: tuple[int, ...],
    pv: float, verdict: bool, *, role, what: str, verdict_key: str = "passed",
) -> None:
    """One recorded test held to the independent recomputation."""
    if role is not None:
        _require(
            rec.get("role") == role,
            f"{what} claims role {rec.get('role')!r}, recomputed {role!r}",
        )
    cond_msg = f"{what} has a mismatched conditioning set"
    rec_cond = [
        _require_str(c, cond_msg)
        for c in _require_list(rec.get("conditioning_set", []), cond_msg)
    ]
    _require(sorted(rec_cond) == sorted(columns[x] for x in cond), cond_msg)
    rec_r = rec.get("partial_correlation")
    rc = _partial_corr(R, i, j, cond)
    _require(
        isinstance(rec_r, (int, float)) and not isinstance(rec_r, bool)
        and abs(float(rec_r) - rc) <= _R_ATOL,
        f"{what} partial correlation {rec_r!r} != recomputed {rc:.6g}",
    )
    rec_p = rec.get("p_value")
    _require(
        isinstance(rec_p, (int, float)) and not isinstance(rec_p, bool)
        and abs(float(rec_p) - pv) <= _P_ATOL,
        f"{what} p-value {rec_p!r} != recomputed {pv:.6g}",
    )
    _require(
        bool(rec.get(verdict_key)) is verdict,
        f"{what} claims {verdict_key}={rec.get(verdict_key)!r}, recomputed "
        f"{verdict}",
    )
