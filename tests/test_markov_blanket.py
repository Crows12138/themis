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
- the producer's Fisher-Z p-values match causal-learn's independent CIT
  implementation (cross-implementation oracle), so the verifier's re-derivation
  is anchored to a third party, not just to the producer.
"""
from __future__ import annotations

import copy

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


# ============================================ continuous-only guard


def test_discrete_target_raises():
    df = _collider_scm()
    df["T"] = (df["T"] > 0).astype(int)  # binarise the target
    with pytest.raises(MarkovBlanketError):
        markov_blanket(df, "T")


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
