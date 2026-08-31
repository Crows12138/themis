"""Independent audit of a lagged graph learned without causal sufficiency.

Its sibling audits a graph whose two stages each claim a property. This one
audits three, and the third is the reason the module exists: an orientation.

- **The screen** is claimed to be a grow-shrink fixpoint — every member
  dependent on the target given the OTHER members, every non-member
  independent given ALL of them. The producer does not present it as the
  answer, and it is checked anyway, because the conditioning pool every
  verdict below was reached inside is a function of it: a screen that is not
  a fixpoint is a pool nobody chose.
- **Each verdict** is claimed to be the outcome of a search over subsets of
  that pool. ``separated`` says the recorded set separates the pair AND that
  nothing smaller or earlier did — which is what makes the recorded set the
  one the orientation rules were entitled to read. ``adjacent`` says NOTHING
  in the enumeration separated them, which is the only claim here that
  cannot be checked by looking at one number, so the enumeration is re-run.
- **Each mark** is claimed to follow from one triple by one rule. The marks
  are re-derived here from the recorded adjacency and separating sets and
  held against the recorded ones, and every recorded orientation is
  additionally checked to satisfy its own rule's preconditions. A mark that
  the rules do not produce is the failure this catches, and it is the
  failure that matters: a fabricated ``tail`` is a causal claim made out of
  nothing, which is precisely what the assumption this module drops used to
  produce.

Independence pin: ``_partial_corr`` / ``_fisher_z_pvalue`` here are a second,
standalone transcription, as are the pool, the enumeration and the rules.
They read only the recorded statistic; a bug in the producer's search, its
test or its orientation cannot mask itself through them.

Trust boundary (stated honestly): the recorded correlation matrix is taken as
given. It is pinned to the fitted data by ``data_hash``, but this function
does not re-read the raw data, so it cannot see a misaligned lag
construction. What it guarantees is: *given the recorded statistic*, the
screen is a fixpoint at the stated alpha, every verdict is what the subset
search returns, every recorded number is correct, the edge list is exactly
the adjacent verdicts, and every endpoint mark is one the rules produce.
"""
from __future__ import annotations

import itertools

import numpy as np

from .errors import VerificationError

_P_ATOL = 1e-6
_R_ATOL = 1e-6

#: The cap the producer searches to. A second transcription rather than an
#: import, for the reason every other number here is one: read from the
#: producer it would be a constant the artifact agrees with itself about.
_MAX_SEPARATING_SET = 3

_MARKS = ("tail", "arrow", "circle")
_RULES = ("collider", "non_collider", "ancestry")


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
    return tuple(
        f"{var}@t" if lag == 0 else f"{var}@t-{lag}"
        for var in variables
        for lag in range(depth + 1)
    )


def _index(position: int, lag: int, depth: int) -> int:
    return position * (depth + 1) + lag


def _as_link(index: int, variables: list[str], depth: int) -> tuple[str, int]:
    pos, lag = divmod(index, depth + 1)
    return variables[pos], lag


def _name(driver: str, lag: int) -> str:
    return f"{driver}@t" if lag == 0 else f"{driver}@t-{lag}"


def verify_latent_lagged_discovery(result: dict) -> None:
    """Independently audit a latent-confounder lagged-discovery result dict.

    Returns ``None`` on accept; raises ``VerificationError`` on any structural
    inconsistency, an ill-formed sufficient statistic, a screen that is not a
    fixpoint, a verdict the subset search does not return, a recorded number
    that disagrees with the independent recomputation, an edge list that is
    not the adjacent verdicts, or an endpoint mark the orientation rules do
    not produce.
    """
    _require(isinstance(result, dict), "result must be a dict")
    _require(
        result.get("kind") == "latent_lagged_discovery",
        f"not a latent_lagged_discovery result (kind={result.get('kind')!r})",
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
        f"depth is {depth} but a separating set is looked for among the "
        f"driver's screen shifted by up to max_lag, so the design has to "
        f"reach {2 * max_lag}",
    )
    alpha = _require_number(result.get("alpha"), "alpha out of range")
    _require(0 < alpha < 1, "alpha out of range")
    n = _require_int(result.get("sample_size"), "sample_size must be an int > 3")
    _require(n > 3, "sample_size must be an int > 3")
    _require(
        result.get("test") == "fisherz",
        f"unknown test type {result.get('test')!r}",
    )
    _require(
        result.get("method") == "tsfci_gs",
        f"unknown method {result.get('method')!r}; this audit holds a result "
        f"to the properties of one procedure and cannot audit another",
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

    candidates = tuple(
        _index(i, lag, depth)
        for i in range(len(variables))
        for lag in range(1, max_lag + 1)
    )

    # --- the screen, and the fixpoint it claims -------------------------------
    screen: dict[str, tuple[tuple[str, int], ...]] = {}
    entries = _require_list(result.get("screen"), "screen must be a list")
    _require(
        len(entries) == len(variables),
        f"screen must have one entry per variable; got {len(entries)} for "
        f"{len(variables)} series",
    )
    for entry in entries:
        block = _require_dict(entry, "each screen entry must be a record")
        target = _require_str(block.get("target"),
                              "each screen entry must name its target")
        _require(target in position, f"screen entry for unknown {target!r}")
        _require(target not in screen, f"two screens for {target!r}")
        members = [
            _lagged_variable(m, position, max_lag, f"screen for {target!r}")
            for m in _require_list(block.get("members"),
                                   f"screen for {target!r} must be a list")
        ]
        _require(len(set(members)) == len(members),
                 f"screen for {target!r} names the same variable twice")
        screen[target] = tuple(sorted(members))
    _require(set(screen) == set(variables),
             "screen must cover exactly the variables")

    for target in variables:
        t_idx = _index(position[target], 0, depth)
        kept = {_index(position[d], lag, depth) for d, lag in screen[target]}
        whole = tuple(sorted(kept))
        for c in candidates:
            driver, lag = _as_link(c, variables, depth)
            inside = c in kept
            cond = tuple(x for x in whole if x != c) if inside else whole
            pv = _fisher_z_pvalue(R, t_idx, c, cond, n)
            _require(
                (pv <= alpha) if inside else (pv > alpha),
                f"the screen of {target!r} is not a fixpoint: "
                f"{driver}@t-{lag} is "
                f"{'in it but independent' if inside else 'outside it but dependent'} "
                f"given {sorted(columns[x] for x in cond)} "
                f"(p={pv:.4g}, alpha={alpha})",
            )

    # --- one verdict per candidate pair, and the search behind it -------------
    recorded: dict[tuple[str, str, int], dict] = {}
    for entry in _require_list(result.get("pair_tests"),
                               "pair_tests must be a list"):
        block = _require_dict(entry, "each pair_tests entry must be a record")
        key = (
            _require_str(block.get("target"), "a pair test must name a target"),
            _require_str(block.get("driver"), "a pair test must name a driver"),
            _require_int(block.get("lag"), "a pair test must name a lag"),
        )
        _require(key not in recorded, f"two pair tests for {key}")
        recorded[key] = block
    expected = {
        (target, *_as_link(c, variables, depth))
        for target in variables for c in candidates
    }
    _require(
        set(recorded) == expected,
        "pair_tests must cover exactly one verdict per candidate pair, "
        "adjacent or not; a list of only the surviving edges cannot be "
        f"checked for having dropped one. Missing "
        f"{len(expected - set(recorded))}, extra {len(set(recorded) - expected)}",
    )

    adjacency: dict[str, set[tuple[str, int]]] = {v: set() for v in variables}
    sepsets: dict[tuple[str, int, str], frozenset[str]] = {}
    for target in variables:
        t_idx = _index(position[target], 0, depth)
        for c in candidates:
            driver, lag = _as_link(c, variables, depth)
            block = recorded[(target, driver, lag)]
            what = f"pair test {driver}@t-{lag} vs {target}@t"
            verdict = _require_str(block.get("verdict"),
                                   f"{what} must state a verdict")
            _require(verdict in ("adjacent", "separated"),
                     f"{what} has unknown verdict {verdict!r}")
            pool = _condition_pool((driver, lag), target, screen, depth,
                                   position, variables)
            found = _search(lambda i, j, s: _fisher_z_pvalue(R, i, j, s, n),
                            t_idx, c, pool, alpha)
            _require(
                found[0] == verdict,
                f"{what} claims {verdict!r} and the subset search over the "
                f"recorded screen returns {found[0]!r}",
            )
            cond = found[1]
            _check_numbers(block, R, n, columns, t_idx, c, cond, alpha, what)
            names = frozenset(columns[x] for x in cond)
            if verdict == "adjacent":
                adjacency[target].add((driver, lag))
            else:
                sepsets[(driver, lag, target)] = names

    # --- the edges are exactly the adjacent verdicts --------------------------
    edges: dict[tuple[str, int, str], str] = {}
    for entry in _require_list(result.get("edges"), "edges must be a list"):
        block = _require_dict(entry, "each edges entry must be a record")
        # An edge is keyed driver-first and a pair test target-first, which
        # is the order each of them reads in. Named apart rather than both
        # called ``key``, because one name for two orders of the same three
        # strings is a defect waiting for the day they are the same types.
        here = (
            _require_str(block.get("driver"), "an edge must name a driver"),
            _require_int(block.get("lag"), "an edge must name a lag"),
            _require_str(block.get("target"), "an edge must name a target"),
        )
        _require(here not in edges, f"two edges for {here}")
        mark = _require_str(block.get("driver_end"),
                            f"edge {here} must state its driver end")
        _require(mark in _MARKS, f"edge {here} has unknown mark {mark!r}")
        _require(
            block.get("target_end") == "arrow",
            f"edge {here} does not carry an arrowhead at its target end; the "
            f"target is later, so it is not an ancestor of the driver, and a "
            f"run that wrote anything else here would not be this method",
        )
        edges[here] = mark
    _require(
        set(edges) == {(d, lag, t) for t in variables
                       for d, lag in adjacency[t]},
        "the edge list is not the set of adjacent verdicts",
    )

    # --- the marks, re-derived from the adjacency and the separating sets ------
    derived, witnesses, conflicts = _marks(
        variables, adjacency, sepsets, max_lag)
    for where, mark in sorted(edges.items()):
        _require(
            derived[where] == mark,
            f"edge {where[0]}@t-{where[1]} -> {where[2]}@t is marked {mark!r} "
            f"and the orientation rules applied to the recorded adjacency and "
            f"separating sets give {derived[where]!r}",
        )

    seen: set[tuple[str, int, str]] = set()
    for entry in _require_list(result.get("orientations"),
                               "orientations must be a list"):
        block = _require_dict(entry, "each orientation must be a record")
        rule = _require_str(block.get("rule"), "an orientation names its rule")
        _require(rule in _RULES, f"unknown orientation rule {rule!r}")
        where = (
            _require_str(block.get("driver"), "an orientation names a driver"),
            _require_int(block.get("lag"), "an orientation names a lag"),
            _require_str(block.get("target"), "an orientation names a target"),
        )
        _require(where in edges, f"orientation for a non-edge {where}")
        _require(where not in seen, f"two orientations for {where}")
        seen.add(where)
        _require(
            block.get("driver_end") == edges[where],
            f"orientation for {where} writes {block.get('driver_end')!r} and "
            f"the edge carries {edges[where]!r}",
        )
        got = (rule, tuple(block.get("between") or ()), block.get("through"),
               None if "separating_set" not in block
               else frozenset(block["separating_set"]))
        _require(
            witnesses.get(where) == got,
            f"orientation for {where} cites rule {rule!r} on "
            f"{block.get('between')} through {block.get('through')!r} with "
            f"separating set {block.get('separating_set')}, which is not the "
            f"triple this audit reaches that mark by",
        )
    _require(
        seen == {at for at, mark in edges.items() if mark != "circle"},
        "orientations must cover exactly the marks that are not circles; "
        "a mark with no rule beside it is one nothing justified",
    )

    # --- the conflicts, re-derived the same way -------------------------------
    recorded_conflicts = []
    for entry in _require_list(result.get("conflicts"),
                               "conflicts must be a list"):
        block = _require_dict(entry, "each conflict must be a record")
        recorded_conflicts.append((
            _require_str(block.get("driver"), "a conflict names a driver"),
            _require_int(block.get("lag"), "a conflict names a lag"),
            _require_str(block.get("target"), "a conflict names a target"),
            block.get("kept"), block.get("refused"), block.get("rule"),
            tuple(block.get("between") or ()), block.get("through"),
        ))
    _require(
        sorted(recorded_conflicts) == sorted(conflicts),
        "the recorded conflicts are not the ones the rules produce on this "
        "adjacency; a disagreement dropped here is a premise failing in "
        "silence, and one invented here is a premise blamed for nothing",
    )


def _lagged_variable(entry, position, max_lag, what) -> tuple[str, int]:
    block = _require_dict(entry, f"{what}: each member must be a record")
    driver = _require_str(block.get("driver"), f"{what}: a member needs a name")
    lag = _require_int(block.get("lag"), f"{what}: a member needs a lag")
    _require(driver in position, f"{what}: unknown variable {driver!r}")
    _require(
        1 <= lag <= max_lag,
        f"{what}: lag {lag} is outside the candidate range 1..{max_lag}, so "
        f"it names a variable this run never looked at",
    )
    return driver, lag


def _condition_pool(link, target, screen, depth, position, variables):
    """What a subset may be drawn from, rebuilt from the recorded screen.

    Both endpoints' screens, the driver's shifted back by the lag — the shift
    is where causal stationarity is spent, and it is the half that would
    vanish without trace if a producer dropped it, leaving a search that
    could not separate a pair the driver's own past explains.
    """
    driver, lag = link
    out = {c for c in screen[target] if c != link}
    for their_driver, their_lag in screen.get(driver, ()):
        shifted = their_lag + lag
        if shifted <= depth:
            out.add((their_driver, shifted))
    out.discard((target, 0))
    out.discard(link)
    return tuple(sorted(_index(position[d], lg, depth) for d, lg in out))


def _search(ci, t_idx, d_idx, candidates, alpha):
    """``(verdict, set)`` for one pair, by the same enumeration order.

    Smallest first and the first hit wins, the whole pool last. The order is
    part of the claim rather than an implementation detail: the orientation
    rules ask whether a vertex is IN the recorded separating set, so a
    producer that returned a different separating set would reach different
    marks from the same data.
    """
    ordered = sorted(candidates)
    best: tuple[tuple[int, ...], float] = ((), 0.0)
    for size in range(0, _MAX_SEPARATING_SET + 1):
        if size > len(ordered):
            break
        for subset in itertools.combinations(ordered, size):
            p = ci(t_idx, d_idx, subset)
            if p > alpha:
                return "separated", subset
            if p >= best[1]:
                best = (subset, p)
    if len(ordered) > _MAX_SEPARATING_SET:
        whole = tuple(ordered)
        p = ci(t_idx, d_idx, whole)
        if p > alpha:
            return "separated", whole
        if p >= best[1]:
            best = (whole, p)
    return "adjacent", best[0]


def _marks(variables, adjacency, sepsets, max_lag):
    """Every endpoint mark and the triple behind it, plus the disagreements.

    A second transcription of the producer's rules. Two of them are one
    triple read two ways — is the middle vertex in the set that separated the
    ends — and the third is that a cause of a cause is a cause.
    """
    marks = {(d, lag, t): "circle"
             for t in variables for d, lag in adjacency[t]}
    witnesses: dict[tuple[str, int, str], tuple] = {}
    conflicts: list[tuple] = []

    def adjacent(driver, lag, target):
        return (driver, lag) in adjacency.get(target, ())

    def write(key, mark, rule, between, through, sep=None):
        if marks.get(key) is None:
            return
        if marks[key] != "circle":
            if marks[key] != mark:
                conflicts.append((*key, marks[key], mark, rule,
                                  tuple(between), through))
            return
        marks[key] = mark
        witnesses[key] = (rule, tuple(between), through, sep)

    for y in variables:
        for x, tx in sorted(adjacency[y]):
            for w in variables:
                for tw in range(tx + 1, max_lag + 1):
                    if not adjacent(w, tw - tx, x) or adjacent(w, tw, y):
                        continue
                    sep = sepsets.get((w, tw, y))
                    if sep is None:
                        continue
                    rule = ("non_collider" if _name(x, tx) in sep
                            else "collider")
                    write((x, tx, y),
                          "tail" if rule == "non_collider" else "arrow", rule,
                          [_name(w, tw), _name(y, 0)], _name(x, tx), sep)

    for _ in range(len(variables) * max_lag + 1):
        wrote = len(witnesses)
        for c in variables:
            for a, ta in sorted(adjacency[c]):
                if marks[(a, ta, c)] != "circle":
                    continue
                for b, tb in sorted(adjacency[c]):
                    if not 1 <= tb < ta:
                        continue
                    if marks[(b, tb, c)] != "tail":
                        continue
                    if marks.get((a, ta - tb, b)) != "tail":
                        continue
                    write((a, ta, c), "tail", "ancestry",
                          [_name(a, ta), _name(c, 0)], _name(b, tb))
                    break
        if len(witnesses) == wrote:
            break
    return marks, witnesses, conflicts


def _check_numbers(block, R, n, columns, i, j, cond, alpha, what) -> None:
    """The recorded set and its two numbers, held to the recomputation."""
    cond_msg = f"{what} has a mismatched conditioning set"
    rec_cond = [
        _require_str(c, cond_msg)
        for c in _require_list(block.get("conditioning_set", []), cond_msg)
    ]
    _require(sorted(rec_cond) == sorted(columns[x] for x in cond), cond_msg)
    rec_r = block.get("partial_correlation")
    rc = _partial_corr(R, i, j, cond)
    _require(
        isinstance(rec_r, (int, float)) and not isinstance(rec_r, bool)
        and abs(float(rec_r) - rc) <= _R_ATOL,
        f"{what} partial correlation {rec_r!r} != recomputed {rc:.6g}",
    )
    rec_p = block.get("p_value")
    pv = _fisher_z_pvalue(R, i, j, cond, n)
    _require(
        isinstance(rec_p, (int, float)) and not isinstance(rec_p, bool)
        and abs(float(rec_p) - pv) <= _P_ATOL,
        f"{what} p-value {rec_p!r} != recomputed {pv:.6g}",
    )
