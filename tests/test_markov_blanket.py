"""Markov blanket discovery + independent verifier (2026-07-11, borrow-list #4).

The Markov blanket of a target is the minimal set that shields it from every
other variable (its parents, children, and children's other parents). These
tests pin:

- ``markov_blanket`` recovers a hand-derived blanket on a linear-Gaussian SCM,
  including the *spouse* (a co-parent of a child, marginally independent of the
  target but dependent once the child is conditioned on) — the subtle case;
- the continuous-only guard rejects discrete data instead of emitting an
  un-verifiable blanket;
- ``verify_markov_blanket`` accepts an honest result and rejects every tamper
  shape (spurious member, trimmed member, edited p-value / passed flag / role,
  a target hidden in its own blanket, a missing / phantom test, and a
  correlation matrix that is not well-formed);
- and rejects them *as* ``VerificationError``. That second half needs its own
  tests, because every value-tamper above hands the verifier a well-typed
  artifact and so exercises none of the type guards standing between an
  arbitrary JSON blob and the arithmetic. A wrong *shape* — a name that is not
  a string, a matrix that is not numeric, a count row that is not a pair —
  used to reach ``hash`` / ``sorted`` / ``np.asarray`` / ``len`` unchecked and
  leave as a raw ``TypeError`` or ``ValueError``, which is a promise this
  module and :func:`themis.verify_markov_blanket` both make in writing and a
  distinction its callers cannot act on;
- the producer's Fisher-Z p-values match causal-learn's independent CIT
  implementation (cross-implementation oracle), so the verifier's re-derivation
  is anchored to a third party, not just to the producer.
"""
from __future__ import annotations

import copy
import re

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.discovery import (
    MarkovBlanketError,
    MarkovBlanketResult,
    markov_blanket,
    markov_blanket_to_dict,
    _fisher_z_pvalue,
    _recode_discrete,
    _build_joint_counts,
    _chi_square_from_joint,
)
from themis.verifier import verify_markov_blanket
from themis.verifier.errors import VerificationError


# ============================================ data-generating processes


def _collider_scm(n=4000, seed=0):
    """X1 → T, X2 → T, T → Y, X3 → Y, X4 ⟂ everything.

    Hand-derived Markov blanket of T: parents {X1, X2}, child {Y}, and Y's
    other parent (spouse) {X3}  →  MB(T) = {X1, X2, X3, Y}. X4 is not in it.
    X3 is marginally independent of T but becomes dependent given Y (collider),
    so recovering it exercises the spouse case.
    """
    rng = np.random.default_rng(seed)
    x1 = rng.standard_normal(n)
    x2 = rng.standard_normal(n)
    x3 = rng.standard_normal(n)
    x4 = rng.standard_normal(n)
    t = 1.5 * x1 - 1.2 * x2 + 0.5 * rng.standard_normal(n)
    y = 1.3 * t + 1.1 * x3 + 0.5 * rng.standard_normal(n)
    return pd.DataFrame({"T": t, "X1": x1, "X2": x2, "X3": x3, "X4": x4, "Y": y})


def _independent_frame(n=2000, seed=1):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "T": rng.standard_normal(n),
        "A": rng.standard_normal(n),
        "B": rng.standard_normal(n),
    })


def _honest(seed=0):
    df = _collider_scm(seed=seed)
    return markov_blanket_to_dict(markov_blanket(df, "T"))


def _sig(z):
    return 1.0 / (1.0 + np.exp(-z))


def _discrete_collider_scm(n=6000, seed=0):
    """Discrete analogue: X1 → T, X2 → T, T → Y, X3 → Y, X4 ⟂ everything, all
    categorical. Hand-derived MB(T) = {X1, X2, X3, Y} (X3 is the spouse). X5 is
    a 3-level variable independent of everything (exercises cardinality > 2)."""
    rng = np.random.default_rng(seed)

    def bern(p):
        return (rng.random(n) < p).astype(int)

    x1, x2, x3, x4 = bern(0.5), bern(0.5), bern(0.5), bern(0.5)
    x5 = rng.integers(0, 3, n)
    t = (rng.random(n) < _sig(2.6 * x1 - 2.2 * x2 - 0.2)).astype(int)
    y = (rng.random(n) < _sig(2.6 * t + 2.2 * x3 - 2.4)).astype(int)
    return pd.DataFrame({"T": t, "X1": x1, "X2": x2, "X3": x3,
                         "X4": x4, "X5": x5, "Y": y})


def _honest_discrete(seed=0):
    df = _discrete_collider_scm(seed=seed)
    return markov_blanket_to_dict(markov_blanket(df, "T"))


# ============================================ recovery


def test_recovers_known_blanket_including_spouse():
    df = _collider_scm()
    res = markov_blanket(df, "T")
    assert isinstance(res, MarkovBlanketResult)
    assert res.blanket == ("X1", "X2", "X3", "Y")
    assert "X4" not in res.blanket


def test_empty_blanket_when_target_independent():
    df = _independent_frame()
    res = markov_blanket(df, "T")
    assert res.blanket == ()
    # An empty blanket is still a valid (trivially complete) blanket.
    verify_markov_blanket(markov_blanket_to_dict(res))


def test_result_records_sufficient_statistics():
    res = markov_blanket(_collider_scm(), "T")
    d = markov_blanket_to_dict(res)
    assert d["kind"] == "markov_blanket"
    p = len(d["columns"])
    assert len(d["correlation"]) == p and len(d["correlation"][0]) == p
    # one definition-check test per non-target variable
    assert {t["variable"] for t in d["tests"]} == set(d["columns"]) - {"T"}


# ============================================ which route a column chooses


def test_a_binarised_target_among_continuous_columns_crosses_the_types():
    """The guard this replaced said the run could not proceed; what was true
    is that neither of the two tests then built had a statistic for it.

    Binarising the target alone is the smallest mixed frame there is — one
    discrete column against several continuous ones — and it is the case a
    reader hits first, by discretising an outcome and asking the same
    question again."""
    df = _collider_scm()
    df["T"] = (df["T"] > 0).astype(int)  # binarise the target
    res = markov_blanket(df, "T")
    assert res.test == "cg_lrt"
    assert res.conditional_gaussian["discrete"] == ["T"]
    verify_markov_blanket(markov_blanket_to_dict(res))


def test_missing_target_raises():
    with pytest.raises(MarkovBlanketError):
        markov_blanket(_collider_scm(), "NOPE")


def test_no_candidates_raises():
    with pytest.raises(MarkovBlanketError):
        markov_blanket(pd.DataFrame({"T": np.arange(50.0)}), "T")


def test_unknown_method_raises():
    with pytest.raises(MarkovBlanketError):
        markov_blanket(_collider_scm(), "T", method="hiton")


# ============================================ verifier accepts honest


def test_verifier_accepts_honest():
    verify_markov_blanket(_honest())


def test_public_kernel_entry_accepts_honest():
    themis.verify_markov_blanket(_honest())


# ============================================ cross-implementation oracle


def test_fisher_z_matches_causal_learn():
    """The producer's Fisher-Z p-values must match causal-learn's independent
    CIT implementation — anchors the shared formula to a third party."""
    pytest.importorskip("causallearn")
    from causallearn.utils.cit import CIT

    df = _collider_scm()
    cols = ["T", "X1", "X2", "X3", "X4", "Y"]
    matrix = df[cols].to_numpy(dtype=float)
    R = np.corrcoef(matrix, rowvar=False)
    n = len(df)
    cit = CIT(matrix, "fisherz")

    cases = [(0, 5, ()), (0, 3, ()), (0, 3, (5,)), (0, 4, (1, 2, 3, 5))]
    for i, j, cond in cases:
        mine = _fisher_z_pvalue(R, i, j, cond, n)
        theirs = float(cit(i, j, list(cond)))
        assert abs(mine - theirs) < 1e-6, (i, j, cond, mine, theirs)


# ============================================ verifier rejects tampering


def _tampered(mutate):
    d = _honest()
    d = copy.deepcopy(d)
    mutate(d)
    return d


def test_rejects_added_spurious_member():
    def mutate(d):
        d["blanket"] = sorted(d["blanket"] + ["X4"])
    with pytest.raises(VerificationError):
        verify_markov_blanket(_tampered(mutate))


def test_rejects_removed_true_member():
    def mutate(d):
        d["blanket"] = [m for m in d["blanket"] if m != "X1"]
    with pytest.raises(VerificationError):
        verify_markov_blanket(_tampered(mutate))


def test_rejects_tampered_pvalue():
    def mutate(d):
        d["tests"][0]["p_value"] = 0.5 - float(d["tests"][0]["p_value"])
    with pytest.raises(VerificationError):
        verify_markov_blanket(_tampered(mutate))


def test_rejects_flipped_passed_flag():
    def mutate(d):
        d["tests"][0]["passed"] = not d["tests"][0]["passed"]
    with pytest.raises(VerificationError):
        verify_markov_blanket(_tampered(mutate))


def test_rejects_wrong_role():
    def mutate(d):
        for t in d["tests"]:
            t["role"] = "shield" if t["role"] == "necessary" else "necessary"
    with pytest.raises(VerificationError):
        verify_markov_blanket(_tampered(mutate))


def test_rejects_target_in_blanket():
    def mutate(d):
        d["blanket"] = sorted(d["blanket"] + ["T"])
    with pytest.raises(VerificationError):
        verify_markov_blanket(_tampered(mutate))


def test_rejects_missing_test():
    def mutate(d):
        d["tests"] = d["tests"][1:]
    with pytest.raises(VerificationError):
        verify_markov_blanket(_tampered(mutate))


def test_rejects_phantom_test():
    def mutate(d):
        d["tests"].append({
            "variable": "GHOST", "role": "shield", "conditioning_set": [],
            "partial_correlation": 0.0, "p_value": 0.9, "passed": True,
        })
    with pytest.raises(VerificationError):
        verify_markov_blanket(_tampered(mutate))


def test_rejects_broken_correlation_symmetry():
    def mutate(d):
        d["correlation"][0][1] = d["correlation"][0][1] + 0.3  # break symmetry
    with pytest.raises(VerificationError):
        verify_markov_blanket(_tampered(mutate))


def test_rejects_non_psd_correlation():
    def mutate(d):
        # symmetric, unit diagonal, but not a valid correlation matrix
        d["correlation"][0][1] = 0.99
        d["correlation"][1][0] = 0.99
        d["correlation"][0][2] = 0.99
        d["correlation"][2][0] = 0.99
        d["correlation"][1][2] = -0.99
        d["correlation"][2][1] = -0.99
    with pytest.raises(VerificationError):
        verify_markov_blanket(_tampered(mutate))


# ============================================ discrete (chi-square) path


def test_discrete_recovers_known_blanket_including_spouse():
    df = _discrete_collider_scm()
    res = markov_blanket(df, "T")
    assert res.test == "chisq"
    assert res.blanket == ("X1", "X2", "X3", "Y")
    assert "X4" not in res.blanket and "X5" not in res.blanket


def test_discrete_result_records_contingency_not_correlation():
    d = _honest_discrete()
    assert d["test"] == "chisq"
    assert "contingency" in d and "correlation" not in d
    assert len(d["contingency"]["levels"]) == len(d["columns"])
    # counts sum to the sample size (a complete sufficient statistic)
    assert sum(c for _, c in d["contingency"]["counts"]) == d["sample_size"]
    t0 = d["tests"][0]
    assert "statistic" in t0 and "dof" in t0 and "partial_correlation" not in t0


def test_discrete_verifier_accepts_honest():
    verify_markov_blanket(_honest_discrete())
    themis.verify_markov_blanket(_honest_discrete())


def test_chi_square_matches_causal_learn():
    """Producer chi-square p-values must match causal-learn's independent CIT
    chisq — anchors the shared formula (and its dof convention) to a third
    party."""
    pytest.importorskip("causallearn")
    from causallearn.utils.cit import CIT

    df = _discrete_collider_scm()
    cols = ("T", "X1", "X2", "X3", "X4", "X5", "Y")
    int_matrix, _levels, cards = _recode_discrete(df, cols)
    joint = _build_joint_counts(int_matrix)
    cit = CIT(int_matrix, "chisq")

    cases = [(0, 6, ()), (0, 3, ()), (0, 3, (6,)), (0, 1, (2, 6)), (0, 5, (1, 6))]
    for i, j, cond in cases:
        mine = _chi_square_from_joint(joint, cards, i, j, cond)[2]
        theirs = float(cit(i, j, list(cond)))
        assert abs(mine - theirs) < 1e-6, (i, j, cond, mine, theirs)


def test_mixed_continuous_and_discrete_takes_the_third_route():
    """One continuous column among discrete ones, and the blanket found in
    the all-discrete frame must survive its arrival.

    The added column is noise independent of everything, so it belongs to no
    blanket — which makes this a test of the new test's SIZE as well as its
    power: a statistic that mistook noise for structure would show up here as
    an extra member rather than as a wrong number."""
    df = _discrete_collider_scm()
    df["cont"] = np.random.default_rng(0).standard_normal(len(df))
    res = markov_blanket(df, "T")
    assert res.test == "cg_lrt"
    assert "cont" not in res.blanket
    assert res.blanket == markov_blanket(_discrete_collider_scm(), "T").blanket
    verify_markov_blanket(markov_blanket_to_dict(res))


def _tampered_discrete(mutate):
    d = copy.deepcopy(_honest_discrete())
    mutate(d)
    return d


def test_discrete_rejects_added_spurious_member():
    def mutate(d):
        d["blanket"] = sorted(d["blanket"] + ["X4"])
    with pytest.raises(VerificationError):
        verify_markov_blanket(_tampered_discrete(mutate))


def test_discrete_rejects_removed_true_member():
    def mutate(d):
        d["blanket"] = [m for m in d["blanket"] if m != "X1"]
    with pytest.raises(VerificationError):
        verify_markov_blanket(_tampered_discrete(mutate))


def test_discrete_rejects_tampered_statistic():
    def mutate(d):
        d["tests"][0]["statistic"] = float(d["tests"][0]["statistic"]) + 50.0
    with pytest.raises(VerificationError):
        verify_markov_blanket(_tampered_discrete(mutate))


def test_discrete_rejects_tampered_dof():
    def mutate(d):
        d["tests"][0]["dof"] = int(d["tests"][0]["dof"]) + 5
    with pytest.raises(VerificationError):
        verify_markov_blanket(_tampered_discrete(mutate))


def test_discrete_rejects_tampered_pvalue():
    def mutate(d):
        d["tests"][0]["p_value"] = 0.5 - float(d["tests"][0]["p_value"])
    with pytest.raises(VerificationError):
        verify_markov_blanket(_tampered_discrete(mutate))


def test_discrete_rejects_corrupted_count_sum():
    def mutate(d):
        d["contingency"]["counts"][0][1] += 999  # counts no longer sum to n
    with pytest.raises(VerificationError):
        verify_markov_blanket(_tampered_discrete(mutate))


def test_discrete_rejects_out_of_range_code():
    def mutate(d):
        d["contingency"]["counts"][0][0][0] = 99  # code beyond its cardinality
    with pytest.raises(VerificationError):
        verify_markov_blanket(_tampered_discrete(mutate))


def test_discrete_rejects_missing_test():
    def mutate(d):
        d["tests"] = d["tests"][1:]
    with pytest.raises(VerificationError):
        verify_markov_blanket(_tampered_discrete(mutate))


# ============================================ verifier rejects malformed shapes
#
# Everything above hands the verifier a structurally valid artifact and edits a
# number, a flag, or a name inside it. The guards these tests attack sit one
# level lower: they are what stands between an arbitrary JSON blob and the
# arithmetic, and a value-tamper never touches them. Their failure mode is
# quiet — not a wrong verdict, but the *right* rejection wearing the wrong
# exception type, which a caller that distinguishes "this artifact is bad" from
# "the verifier is bad" cannot act on.


def _set_path(d, path, value):
    """Assign ``value`` at ``path`` — a sequence of dict keys / list indices."""
    node = d
    for step in path[:-1]:
        node = node[step]
    node[path[-1]] = value


# (where to plant a wrong-shaped value, what to plant, what must come back).
# The message is asserted, not just the exception type: a guard that fires for
# the wrong reason is as much a defect as one that does not fire, and several
# of these rows are one reordering away from being answered by a later guard
# that happens to also reject them.
_SHAPE_TAMPERS = [
    (("columns",), "abc", "columns must be a non-empty list"),
    (("columns",), [], "columns must be a non-empty list"),
    (("columns", 1), ["X1"], "column name ['X1'] must be a string"),
    (("columns", 4), 7, "column name 7 must be a string"),
    (("target",), ["T"], "target ['T'] not among columns"),
    (("target",), "NOPE", "target 'NOPE' not among columns"),
    (("blanket",), "X1", "blanket must be a list"),
    (("tests",), {}, "tests must be a list"),
    (("tests", 0, "conditioning_set"), 5, "has a mismatched conditioning set"),
    (("tests", 0, "conditioning_set"), [1, "X2"], "has a mismatched conditioning set"),
    (("tests", 0, "p_value"), "x", "!= recomputed"),
    (("tests", 0, "partial_correlation"), "x", "!= recomputed"),
    (("alpha",), True, "alpha out of range"),
    (("alpha",), "0.05", "alpha out of range"),
    (("sample_size",), 100.0, "sample_size must be an int > 3"),
    (("sample_size",), "4000", "sample_size must be an int > 3"),
    (("correlation",), "abc", "correlation must be a 6x6 matrix of numbers"),
    (("correlation", 0), [1.0, 0.0], "correlation must be a 6x6 matrix of numbers"),
    (("correlation", 0, 1), "x", "correlation must be a 6x6 matrix of numbers"),
]


@pytest.mark.parametrize("path,value,message", _SHAPE_TAMPERS)
def test_rejects_malformed_shape(path, value, message):
    """Every field the verifier reads is artifact-supplied, so every field is a
    place a caller can hand it something of the wrong type. The one it must
    never do in return is fail in a way its own contract does not name."""
    def mutate(d):
        _set_path(d, path, value)
    with pytest.raises(VerificationError, match=re.escape(message)):
        verify_markov_blanket(_tampered(mutate))


def test_rejects_unhashable_test_variable():
    """``tests`` is indexed by the variable name each entry claims, so building
    that index hashes a value the artifact chose. An unhashable one used to
    take the dict comprehension itself down with a TypeError, before any guard
    got to look at it — the check has to happen on the way in, not after."""
    def mutate(d):
        d["tests"][0]["variable"] = ["x"]
    with pytest.raises(VerificationError, match=re.escape("test variable ['x'] must be a string")):
        verify_markov_blanket(_tampered(mutate))


def test_rejects_heterogeneous_test_variable_names():
    """The "tests must cover exactly the non-target variables" message sorts
    the two name sets to report what is missing and what is extra — and an
    f-string is built before it is passed, so the sort runs whether or not the
    check fails. Two claimed names of different types made that sort raise, so
    the artifact was rejected by a TypeError from inside the sentence written
    to explain the rejection. Needs *two* mismatched names of unlike type: one
    alone leaves each difference set homogeneous and sortable."""
    def mutate(d):
        d["tests"][0]["variable"] = 1
        d["tests"][1]["variable"] = "ZZZ"
    with pytest.raises(VerificationError, match=re.escape("test variable 1 must be a string")):
        verify_markov_blanket(_tampered(mutate))


def test_rejects_unhashable_blanket_member():
    """Nothing types the blanket directly — a member is known to be a string
    because it has to be one of the (checked) column names. That makes the
    order of the two checks load-bearing: the duplicate check hashes the
    members, so it has to run *after* the membership check that establishes
    they can be hashed, not before."""
    def mutate(d):
        d["blanket"][0] = ["X1"]
    with pytest.raises(VerificationError, match=re.escape("blanket member ['X1'] not among columns")):
        verify_markov_blanket(_tampered(mutate))


_DISCRETE_SHAPE_TAMPERS = [
    (("contingency",), [], "chisq result needs a contingency block"),
    (("contingency", "levels"), {}, "contingency.levels must have one entry per column"),
    (("contingency", "levels", 0), 3, "each contingency.levels entry must be a list"),
    (("contingency", "counts"), {}, "contingency.counts must be non-empty"),
    (("contingency", "counts"), [], "contingency.counts must be non-empty"),
    (("tests", 0, "statistic"), "x", "!= recomputed"),
    (("tests", 0, "dof"), "x", "!= recomputed"),
]


@pytest.mark.parametrize("path,value,message", _DISCRETE_SHAPE_TAMPERS)
def test_discrete_rejects_malformed_shape(path, value, message):
    """The chisq arm reads a whole sufficient statistic the fisherz arm never
    sees, so its guards are a separate surface and get their own sweep."""
    def mutate(d):
        _set_path(d, path, value)
    with pytest.raises(VerificationError, match=re.escape(message)):
        verify_markov_blanket(_tampered_discrete(mutate))


def test_discrete_rejects_tuple_levels():
    """``levels`` is the code book — entry *c* lists column *c*'s values — so
    the container's own shape is what makes "one entry per column" mean
    anything. A tuple of the right length holding the right entries satisfies
    every later check and would be accepted outright; the list guard is the
    only thing in the function that ever looks at it."""
    def mutate(d):
        d["contingency"]["levels"] = tuple(d["contingency"]["levels"])
    with pytest.raises(
        VerificationError,
        match=re.escape("contingency.levels must have one entry per column"),
    ):
        verify_markov_blanket(_tampered_discrete(mutate))


def test_discrete_rejects_tuple_count_row():
    """The count table is the discrete sufficient statistic, and its rows are
    unpacked as pairs. A JSON artifact cannot carry a tuple, but an in-process
    caller can, and the guard says "list" — so it must say so out loud rather
    than let a tuple through to be unpacked on a length it never checked."""
    def mutate(d):
        d["contingency"]["counts"][0] = tuple(d["contingency"]["counts"][0])
    with pytest.raises(VerificationError, match=re.escape("each count row must be [config, count]")):
        verify_markov_blanket(_tampered_discrete(mutate))


def test_discrete_rejects_over_long_count_row():
    """A three-element row would unpack into the wrong variables if the arity
    check were dropped, silently reinterpreting counts as configs."""
    def mutate(d):
        d["contingency"]["counts"][0] = list(d["contingency"]["counts"][0]) + [1]
    with pytest.raises(VerificationError, match=re.escape("each count row must be [config, count]")):
        verify_markov_blanket(_tampered_discrete(mutate))


def test_discrete_rejects_tuple_config():
    """Same boundary one level down: the per-row config is the thing indexed by
    column position, and its shape is what makes that indexing meaningful."""
    def mutate(d):
        row = d["contingency"]["counts"][0]
        row[0] = tuple(row[0])
    with pytest.raises(VerificationError, match=re.escape("each config must have one code per column")):
        verify_markov_blanket(_tampered_discrete(mutate))


def test_discrete_rejects_float_count():
    """Counts are occurrences. A float one would sum to a total that cannot
    equal an integer sample size except by rounding luck, so it is rejected on
    its type rather than left to be caught (or missed) by the total."""
    def mutate(d):
        d["contingency"]["counts"][0][1] = 5.0
    with pytest.raises(VerificationError, match=re.escape("each count must be a positive int")):
        verify_markov_blanket(_tampered_discrete(mutate))
