"""#462. A continuous search was deferred because nobody could check it.

The repo recorded NOTEARS as "不做" in three places, and the reason given
each time was the same: a local optimum found by L-BFGS-B cannot be replayed
step for step, so a returned graph would be a number nobody could re-derive
— which is the one thing this repo does not ship.

The reason is wrong, and this file is where that is measured rather than
argued. The objective and its gradient depend on the data ONLY through the
Gram matrix S = X'X / n:

    ‖X − XW‖²_F / 2n = tr((I − W)' S (I − W)) / 2      ∇ = −S(I − W)

so a d×d matrix is a sufficient statistic for the entire problem. Replaying
the SEARCH and re-deriving the ANSWER are two different things, and only the
first is impossible.

What that does not buy, and what is asserted here as loudly as what it does:
global optimality is not certified, the standardised re-run is not re-solved,
and the Gram matrix itself is taken as given. Each has a test saying so.

The second half of the file is about scale. Reisach, Seiler & Weichwald
(2021) showed this family exploits the marginal variances — when they rise
along the causal order, sorting by variance alone reproduces the graph and
the search takes the credit. The answer here is not a caveat in prose: the
same fit is run on standardised data and the diagnostic reports, PER EDGE,
which edges survived. A global "scale-dependent: yes/no" was written first
and thrown away, because L1 plus a fixed threshold is not scale-equivariant,
so it fires almost always and says nothing.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.audits import Artifact, artifact_of
from themis.estimation.discovery import (
    ALGORITHM_NAMES, DiscoveryError, discover_graph, notears_fit_to_dict,
)
from themis.estimation.refusal_words import Refuses
from themis.estimation.notears import fit_notears, stationarity
from themis.verifier import notears_rules
from themis.verifier.errors import VerificationError

COLS = ("a", "b", "c", "d", "e")
#: a → b → d, a → c → d, c → e.
TRUE_EDGES = {("a", "b"), ("a", "c"), ("b", "d"), ("c", "d"), ("c", "e")}
TRUE = {("a", "b"): 1.2, ("b", "d"): -0.9, ("a", "c"): 0.8,
        ("c", "d"): 1.1, ("c", "e"): -1.3}


def _sample(n: int = 3000, seed: int = 0, scales=None) -> pd.DataFrame:
    """A linear SCM over a known DAG. ``scales`` multiplies the noise of each
    column, which is the knob Reisach et al.'s failure mode turns."""
    rng = np.random.default_rng(seed)
    idx = {c: i for i, c in enumerate(COLS)}
    x = np.zeros((n, len(COLS)))
    noise = rng.normal(0, 1, size=(n, len(COLS)))
    if scales is not None:
        noise = noise * np.asarray(scales, dtype=float)
    for col in COLS:  # COLS is already a topological order
        acc = noise[:, idx[col]].copy()
        for (src, dst), weight in TRUE.items():
            if dst == col:
                acc = acc + weight * x[:, idx[src]]
        x[:, idx[col]] = acc
    return pd.DataFrame(x, columns=list(COLS))


@pytest.fixture(scope="module")
def plain() -> pd.DataFrame:
    return _sample()


@pytest.fixture(scope="module")
def fitted(plain) -> dict:
    return notears_fit_to_dict(discover_graph(plain, algorithm="notears"))


# ============================================================ it finds the DAG


def test_it_recovers_a_known_dag_when_the_scales_say_nothing(plain):
    result = discover_graph(plain, algorithm="notears")
    assert set(result.directed_edges) == TRUE_EDGES
    assert result.bidirected_edges == ()
    assert result.ambiguous_edges == (), (
        "NOTEARS returns a DAG, not an equivalence class — an ambiguous "
        "bucket here would mean the runner is describing somebody else's "
        "output shape"
    )


def test_the_weights_are_near_the_ones_the_data_was_made_with(plain):
    result = discover_graph(plain, algorithm="notears")
    index = {c: i for i, c in enumerate(result.columns)}
    for (src, dst), truth in TRUE.items():
        got = result.notears_weights[index[src]][index[dst]]
        # L1 shrinks, so the recovered weight is smaller in magnitude; what
        # is pinned is the sign and the order of magnitude, not the value.
        assert np.sign(got) == np.sign(truth), (src, dst, got, truth)
        assert 0.5 * abs(truth) < abs(got) <= abs(truth) + 0.2, (src, dst, got)


def test_it_is_explicit_only(plain):
    """``auto`` must never resolve to it. A continuous search rests on a
    linear SCM, which is a stronger assumption than the selector measures."""
    assert "notears" in ALGORITHM_NAMES
    for frame in (plain, _sample(n=600, seed=4)):
        assert discover_graph(frame, algorithm="auto").algorithm != "notears"


def test_two_runs_on_one_frame_agree_to_the_bit(plain):
    """No random_state is threaded because none is used: the solver starts
    from zero and L-BFGS-B is deterministic. A run that drifted would make
    every claim below a claim about one lucky run."""
    first = discover_graph(plain, algorithm="notears")
    second = discover_graph(plain, algorithm="notears")
    assert first.notears_weights == second.notears_weights
    assert first.notears_certificate == second.notears_certificate
    assert first.notears_scale == second.notears_scale


# ================================================ the certificate is the point


def test_the_gram_matrix_is_the_sufficient_statistic(plain):
    """The claim the whole feature rests on, checked directly: the loss and
    its gradient computed from the raw data equal the ones computed from a
    d×d matrix."""
    centred = plain.to_numpy(dtype=float)
    centred = centred - centred.mean(axis=0, keepdims=True)
    n, d = centred.shape
    gram = centred.T @ centred / n
    rng = np.random.default_rng(19)
    for _ in range(5):
        w = rng.normal(size=(d, d)) * 0.4
        np.fill_diagonal(w, 0.0)
        from_data = float(((centred - centred @ w) ** 2).sum() / (2 * n))
        resid = np.eye(d) - w
        from_gram = float(np.trace(resid.T @ gram @ resid) / 2.0)
        assert from_data == pytest.approx(from_gram, rel=1e-10)

        grad_data = -centred.T @ (centred - centred @ w) / n
        grad_gram = -gram @ resid
        assert np.abs(grad_data - grad_gram).max() < 1e-10


def test_the_certificate_travels_and_the_verifier_accepts_it(fitted):
    assert artifact_of(fitted) is Artifact.NOTEARS_FIT
    themis.verify_notears_fit(fitted)


def test_the_residual_is_small_but_reported_rather_than_asserted(fitted):
    """The envelope reports the number and lets the reader judge it. The
    test's job is only to say the solver did get near a stationary point —
    if it did not, every other claim here is about a point nobody chose."""
    assert fitted["stationarity"] < 0.05
    assert fitted["acyclicity"] < 1e-7


def test_the_diagonal_is_not_part_of_the_residual(plain):
    """W_ii is pinned at zero by the no-self-loop bound rather than chosen,
    so its first-order condition carries a bound multiplier that absorbs any
    gradient. Including it reports the residual variance of each column —
    which is what it did, and is why the residual read 1.09 instead of
    0.0046 on this very frame."""
    centred = plain.to_numpy(dtype=float)
    centred = centred - centred.mean(axis=0, keepdims=True)
    gram = centred.T @ centred / centred.shape[0]
    fit = fit_notears(centred, COLS)
    cert = fit.certificate
    w = np.asarray(fit.weights)

    resid = np.eye(len(COLS)) - w
    g_loss = -gram @ resid
    diagonal_would_say = float(
        np.maximum(0.0, np.abs(np.diag(g_loss)) - cert.l1_penalty).max())
    assert diagonal_would_say > 20 * cert.stationarity, (
        "the counterexample has stopped being one — if the diagonal no "
        "longer dominates, this test is pinning nothing"
    )
    # And what it would have reported is the residual variance of a column,
    # a fact about fit and not about optimality.
    residual_variances = np.diag(gram @ resid)
    assert np.abs(np.diag(g_loss) + residual_variances).max() < 1e-9


def test_stationarity_is_about_the_multiplier_it_is_given(plain):
    """One number and not the (α, ρ) pair. Handing it a different multiplier
    must move it — otherwise the field is decorative and a swapped
    multiplier would be undetectable."""
    centred = plain.to_numpy(dtype=float)
    centred = centred - centred.mean(axis=0, keepdims=True)
    gram = centred.T @ centred / centred.shape[0]
    fit = fit_notears(centred, COLS)
    w = np.asarray(fit.weights)
    cert = fit.certificate
    at_exit = stationarity(w, gram, cert.l1_penalty, cert.multiplier)
    doubled = stationarity(w, gram, cert.l1_penalty, cert.multiplier * 2)
    assert at_exit == pytest.approx(cert.stationarity, rel=1e-12)
    assert doubled > 100 * at_exit


def test_the_second_transcription_of_expm_agrees_with_scipy(fitted):
    """The independence pin. A power series over a non-negative argument and
    a Padé approximant are two routes; if they were one, a bug in the
    producer's exponential would certify itself."""
    import scipy.linalg

    w = np.asarray(fitted["weights"])
    series = notears_rules._expm(w * w)
    pade = scipy.linalg.expm(w * w)
    assert np.abs(series - pade).max() < 1e-12


def test_the_series_route_survives_a_large_argument():
    """Scaling-and-squaring, exercised where the plain series would overflow
    into meaninglessness. Squaring preserves the non-negativity the pin
    rests on."""
    import scipy.linalg

    rng = np.random.default_rng(5)
    big = np.abs(rng.normal(size=(6, 6))) * 3.0
    assert np.abs(big).sum(axis=0).max() > 10
    assert np.abs(
        notears_rules._expm(big) - scipy.linalg.expm(big)
    ).max() < 1e-6 * np.abs(scipy.linalg.expm(big)).max()


# ================================================== what it does NOT certify


def test_global_optimality_is_not_claimed_anywhere(fitted):
    """Stated as a test because a field named ``objective`` beside a field
    named ``stationarity`` reads like one, and it is not."""
    import json
    import pathlib

    schemas = pathlib.Path(themis.__file__).resolve().parent / "schemas"
    doc = json.loads(
        (schemas / "notears_fit.schema.json").read_text(encoding="utf-8"))
    assert "Global optimality is NOT certified" in doc["description"]
    assert set(fitted) & {"is_global_optimum", "optimal", "converged"} == set()


def test_a_different_local_optimum_is_certified_just_as_happily(plain):
    """The honest consequence of the above, shown rather than described: a
    verifier that accepted only the best point would be claiming something
    it cannot check. Take the real solution, damp it toward zero, re-derive
    every field about THAT point, and the audit passes — the certificate
    says "these numbers describe this point", not "this point is best"."""
    fit = fit_notears(
        plain.to_numpy(dtype=float) - plain.to_numpy(dtype=float).mean(axis=0),
        COLS,
    )
    centred = plain.to_numpy(dtype=float)
    centred = centred - centred.mean(axis=0, keepdims=True)
    gram = centred.T @ centred / centred.shape[0]

    other = np.asarray(fit.weights) * 0.5
    resid = np.eye(len(COLS)) - other
    import scipy.linalg
    expm = scipy.linalg.expm(other * other)
    payload = {
        "kind": "notears_fit",
        "columns": list(COLS),
        "data_columns": sorted(COLS),
        "sample_size": len(plain),
        "data_hash": "0" * 64,
        "weights": [list(map(float, row)) for row in other],
        "gram": [list(map(float, row)) for row in gram],
        "l1_penalty": fit.certificate.l1_penalty,
        "threshold": fit.certificate.threshold,
        "multiplier": fit.certificate.multiplier,
        "rho": fit.certificate.rho,
        "iterations": fit.certificate.iterations,
        "acyclicity": float(np.trace(expm) - len(COLS)),
        "objective": float(
            np.trace(resid.T @ gram @ resid) / 2.0
            + fit.certificate.l1_penalty * np.abs(other).sum()),
        "stationarity": stationarity(
            other, gram, fit.certificate.l1_penalty,
            fit.certificate.multiplier),
        "directed_edges": [
            [COLS[i], COLS[j]]
            for i, j in zip(*np.nonzero(
                np.where(np.abs(other) >= fit.certificate.threshold,
                         other, 0.0)))
        ],
        "varsortability": 0.0,
        "n_paths": 0,
        "edges_standardised": 0,
        "survives_standardising": [],
        "note": "a worse point, described correctly",
    }
    varsort, n_paths = notears_rules._varsortability(
        np.where(np.abs(other) >= fit.certificate.threshold, other, 0.0),
        np.diag(gram))
    payload["varsortability"] = varsort
    payload["n_paths"] = n_paths

    # It is genuinely worse than the fit's own point...
    assert payload["objective"] > fit.certificate.objective
    # ...and the audit accepts it, because it never claimed otherwise.
    themis.verify_notears_fit(payload)


def test_the_standardised_run_is_asserted_not_re_solved(fitted):
    """The audit checks the two ways that record can contradict itself and
    says so rather than implying it re-solved the second problem."""
    survives = {tuple(e) for e in fitted["survives_standardising"]}
    reported = {tuple(e) for e in fitted["directed_edges"]}
    assert survives <= reported
    assert "does not re-solve" in notears_rules.__doc__ or \
        "does not re-solve" in notears_rules.__doc__.replace("\n", " ")


# ======================================================== the scale diagnostic


def test_varsortability_is_recomputable_from_the_gram_diagonal(fitted):
    """A centred column's variance IS its Gram diagonal entry, so the
    diagnostic is not a claim the reader has to take on faith — which is
    what decided that it travels as a number rather than as prose."""
    weights = np.asarray(fitted["weights"])
    pruned = np.where(np.abs(weights) >= fitted["threshold"], weights, 0.0)
    varsort, n_paths = notears_rules._varsortability(
        pruned, np.diag(np.asarray(fitted["gram"])))
    assert varsort == pytest.approx(fitted["varsortability"], abs=1e-12)
    assert n_paths == fitted["n_paths"]


def test_scales_rising_along_the_dag_are_reported_as_such():
    """The Reisach failure mode, on data built to have it. Varsortability
    near 1 means the marginal variances alone would have ordered this graph,
    so the search deserves no credit for the order."""
    result = discover_graph(
        _sample(scales=[0.3, 0.6, 0.9, 1.5, 2.0]), algorithm="notears")
    assert result.notears_scale is not None
    assert result.notears_scale.varsortability > 0.95


def test_the_edges_the_scales_decided_are_named_one_by_one():
    """Falling scales make the method invent reversed edges. The point of
    the per-edge split is that it separates them from the real ones — a
    global flag could only have said "something moved"."""
    result = discover_graph(
        _sample(scales=[2.0, 1.5, 0.9, 0.6, 0.3]), algorithm="notears")
    found = set(result.directed_edges)
    spurious = found - TRUE_EDGES
    assert spurious, "this frame is supposed to break the method"

    survived = set(result.notears_scale.survives_standardising)
    assert not (spurious & survived), (
        "an edge the scales invented survived removing the scales", spurious)
    assert TRUE_EDGES & survived, "and the real edges did survive"


def test_a_global_scale_flag_would_have_said_nothing():
    """Why the boolean was thrown away, measured on the case it was supposed
    to be silent about: with equal noise scales — where nothing is wrong —
    the two edge sets still differ, because L1 plus a fixed threshold is not
    scale-equivariant. A flag reading "yes" here reads "yes" everywhere."""
    result = discover_graph(_sample(), algorithm="notears")
    assert set(result.directed_edges) == TRUE_EDGES, (
        "the fit itself is correct on this frame")
    survived = set(result.notears_scale.survives_standardising)
    assert survived != set(result.directed_edges), (
        "if standardising no longer moves anything on clean data, the "
        "reason for the per-edge split is gone and it should be revisited")


def test_a_pre_run_warning_names_the_variance_spread():
    """The per-edge check is after the fact. A reader deciding whether to
    run at all gets the spread beforehand, from the data alone."""
    tilted = discover_graph(
        _sample(scales=[0.2, 0.6, 1.0, 2.0, 4.0]), algorithm="notears")
    said = {one["token"] for one in tilted.assumption_violations}
    assert "notears_reads_the_variance_order" in said
    flat = discover_graph(_sample(), algorithm="notears")
    assert "notears_reads_the_variance_order" not in {
        one["token"] for one in flat.assumption_violations}


def test_level_coded_columns_are_flagged_before_the_weights_are_read():
    frame = _sample(n=800)
    frame["b"] = (frame["b"] > 0).astype(float)
    result = discover_graph(frame, algorithm="notears")
    assert "notears_was_given_level_codes" in {
        one["token"] for one in result.assumption_violations}


# ================================================================== forgeries


def _forge(fitted: dict, mutate) -> dict:
    bad = copy.deepcopy(fitted)
    mutate(bad)
    return bad


FORGERIES = {
    "acyclicity replaced by zero":
        lambda d: d.__setitem__("acyclicity", 0.0),
    "objective inflated by one percent":
        lambda d: d.__setitem__("objective", d["objective"] * 1.01),
    "stationarity zeroed, claiming an exact optimum":
        lambda d: d.__setitem__("stationarity", 0.0),
    "an edge invented":
        lambda d: d["directed_edges"].append(["e", "a"]),
    "a real edge dropped":
        lambda d: d["directed_edges"].pop(0),
    "the threshold lowered without re-reading the edges":
        lambda d: d.__setitem__("threshold", 0.05),
    "the weights replaced, leaving the residuals behind":
        lambda d: d.__setitem__(
            "weights", [[0.0 if i == j else 0.9 for j in range(5)]
                        for i in range(5)]),
    "varsortability rounded to a friendlier number":
        lambda d: d.__setitem__("varsortability", 0.5),
    "n_paths inflated":
        lambda d: d.__setitem__("n_paths", d["n_paths"] + 3),
    "the multiplier swapped, so the residual is about another problem":
        lambda d: d.__setitem__("multiplier", d["multiplier"] * 2),
    "the penalty swapped":
        lambda d: d.__setitem__("l1_penalty", 0.2),
    "the Gram matrix rescaled — another dataset's statistic":
        lambda d: d.__setitem__(
            "gram", [[v * 1.05 for v in row] for row in d["gram"]]),
    "the Gram matrix made asymmetric":
        lambda d: d.__setitem__(
            "gram", [[v + (0.3 if (i, j) == (0, 1) else 0.0)
                      for j, v in enumerate(row)]
                     for i, row in enumerate(d["gram"])]),
    "a self-loop smuggled into the edge list":
        lambda d: d["directed_edges"].append(["a", "a"]),
    "a self-loop smuggled into the weights":
        lambda d: d["weights"][2].__setitem__(2, 0.4),
    "survives_standardising names an edge the fit never reported":
        lambda d: d["survives_standardising"].append(["d", "a"]),
    "survives_standardising larger than the run it intersects":
        lambda d: d.__setitem__("edges_standardised", 0),
    "an edge named twice":
        lambda d: d["directed_edges"].append(list(d["directed_edges"][0])),
    "an edge on a column that is not in the frame":
        lambda d: d["directed_edges"].append(["a", "zz"]),
    "somebody else's artifact":
        lambda d: d.__setitem__("kind", "markov_blanket"),
}


@pytest.mark.parametrize("name", sorted(FORGERIES))
def test_a_forgery_is_rejected(fitted, name):
    with pytest.raises(VerificationError):
        themis.verify_notears_fit(_forge(fitted, FORGERIES[name]))


def test_the_forgeries_are_forgeries(fitted):
    """Each mutation must actually change the artifact. A no-op mutation
    passing the audit would read as a rejection that never happened."""
    for name, mutate in FORGERIES.items():
        assert _forge(fitted, mutate) != fitted, name


def test_the_audit_refuses_an_envelope_rather_than_failing_it(plain):
    """The distinction #452 built the audit table for: "not your artifact"
    and "your artifact is wrong" must not arrive as the same event."""
    assert artifact_of({"query_kind": "effect"}) is Artifact.QUERY_RESULT
    with pytest.raises(VerificationError, match="not a notears_fit"):
        themis.verify_notears_fit({"query_kind": "effect"})


def test_the_audit_table_offers_it_for_this_artifact_and_no_other(fitted):
    rows = [row["audit"] for row in themis.audit(None, fitted)]
    assert rows == ["verify_notears_fit"]


def test_the_producer_refuses_to_export_another_algorithms_result(plain):
    result = discover_graph(plain, algorithm="pc")
    with pytest.raises(DiscoveryError) as raised:
        notears_fit_to_dict(result)
    assert raised.value.species is Refuses.ARTIFACT_HAS_NO_CERTIFICATE
