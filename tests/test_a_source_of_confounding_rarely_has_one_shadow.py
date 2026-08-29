"""A proximal sieve is built from a design, and a design is not one column.

Three questions a caller could not ask before, and all three are the same
missing object — there was no way to say that a design matrix is made of
terms, so it was made of one variable's basis and everything else was out.

  * Two negative-control outcomes. A study of frailty has bone density AND
    grip strength, and confounding by frailty is not what either of them
    alone measures. Picking one throws away the half the other would have
    caught, and the first test here is the measurement of exactly that: the
    same data, the same graph, one proxy versus two, against a truth both
    are being asked for.

  * Observed covariates. "Condition on age and sex, then run proximal
    inside that" is an ordinary request and had nowhere to go.

  * An interaction. A covariate ADDED to a bridge shifts it up and down; a
    covariate MULTIPLIED into it lets the bridge be a different function of
    the proxy in each stratum. Only the second answers the request above
    when the proxy's own relationship to the confounder differs by stratum,
    which is why terms hold several variables rather than one.

The oracles are data where the bridge has a closed form, so what is being
compared is an estimate against a number that is true rather than against
another estimate.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.input.semantic_validator import Malformed, SemanticError

BETA = 1.5


# --- the program ---------------------------------------------------------------

def _var(p, **kw):
    out = {"kind": "variable", "predicate": p}
    out.update(kw)
    return out


def _atom(p):
    return {"predicate": p, "args": []}


def _cause(a, b):
    return {"kind": "cause", "from": _atom(a), "to": _atom(b)}


def _factor(variable, basis="polynomial", dimension=2):
    return {"variable": _atom(variable), "basis": basis,
            "dimension": dimension}


def _term(*factors):
    """One block of the design — a product where it names more than one."""
    return {"factors": list(factors)}


def _bridge(outcome_terms, instrument_terms, ridge=None):
    out = {"kind": "bridge_function",
           "outcome_terms": outcome_terms,
           "instrument_terms": instrument_terms}
    if ridge is not None:
        out["ridge"] = ridge
    return out


def _program(*, proxies, channel, covariates=(), edges=(), scales=None):
    """Miao model (f) over as many proxies as are named.

    ``u`` is one node of the graph and the data behind it need not be one
    number: the graph says a confounder is unobserved and says nothing
    about its dimension, which is the whole reason more than one shadow of
    it is worth having.
    """
    zs, ws = proxies
    names = [*zs, *ws, *covariates]
    scales = scales or {}
    return {
        "version": "0.1",
        "domain": {"objects": []},
        "statements": [
            _var("x", domain=[True, False]), _var("y", scale="continuous"),
            _var("u"),
            *(_var(n, scale=scales.get(n, "continuous")) for n in names),
            _cause("u", "x"), _cause("u", "y"), _cause("x", "y"),
            *(_cause("u", n) for n in (*zs, *ws)),
            *(_cause(a, b) for a, b in edges),
            {"kind": "query", "id": "q", "query": {
                "kind": "proximal_effect", "treatment": _atom("x"),
                "outcome": _atom("y"), "latent": _atom("u"),
                "treatment_proxy": [_atom(z) for z in zs],
                "outcome_proxy": [_atom(w) for w in ws],
                **({"covariates": [_atom(c) for c in covariates]}
                   if covariates else {}),
                "channel": channel,
            }},
        ],
    }


# --- oracle one: two shadows of one confounder --------------------------------

@pytest.fixture(scope="module")
def two_shadow_frame() -> pd.DataFrame:
    """A confounder with two independent parts, each with its own proxies.

    ``u1`` and ``u2`` are both unobserved and both move X and Y. ``z1``/``w1``
    see only ``u1`` and ``z2``/``w2`` only ``u2``, so

        h(w1, w2, x) = βx + (d1/b1)·w1 + (d2/b2)·w2

    is an exact bridge — E[W_i | Z, X] = b_i·E[U_i | Z, X] because each W is
    independent of (Z, X) given U — while NO function of ``w1`` alone is,
    since ``z2`` moves E[U2 | Z, X] with E[U1 | Z, X] held still. Both proxy
    means are zero, so the two arms differ by exactly β.
    """
    rng = np.random.default_rng(20260829)
    n = 6000
    u1, u2 = rng.standard_normal(n), rng.standard_normal(n)
    x = rng.random(n) < 1 / (1 + np.exp(-(1.1 * u1 + 1.3 * u2)))
    return pd.DataFrame({
        "x": x,
        "y": BETA * x + 1.0 * u1 + 1.4 * u2 + 0.3 * rng.standard_normal(n),
        "z1": 1.2 * u1 + 0.4 * rng.standard_normal(n),
        "z2": 1.1 * u2 + 0.4 * rng.standard_normal(n),
        "w1": 0.9 * u1 + 0.4 * rng.standard_normal(n),
        "w2": 1.3 * u2 + 0.4 * rng.standard_normal(n),
    })


def _point(program, frame):
    out = themis.estimate(program, frame, ci_bootstrap=0)["results"][0]
    assert out["status"] == "numerically_solved", out.get("estimator_failure")
    return out["numeric_estimate"]["point"]


def _both_shadows(**kw):
    return _program(
        proxies=(("z1", "z2"), ("w1", "w2")),
        channel=_bridge([_term(_factor("w1")), _term(_factor("w2"))],
                        [_term(_factor("z1")), _term(_factor("z2"))]),
        **kw)


def _one_shadow(**kw):
    """The same question with one negative control instead of two.

    Both instruments are kept, so this is not a narrower question asked
    with less data — it is the same moments asked to pin down a bridge that
    does not lie in the span it is being sought in.
    """
    return _program(
        proxies=(("z1", "z2"), ("w1",)),
        channel=_bridge([_term(_factor("w1"))],
                        [_term(_factor("z1")), _term(_factor("z2"))]),
        **kw)


def test_the_second_negative_control_is_what_makes_the_answer_true(
        two_shadow_frame):
    """The whole feature, as one comparison.

    Same data, same graph, same question, same instruments. With one
    outcome proxy the bridge is not in the declared span and the answer is
    wrong by more than a tenth of the effect; with the second one it is in
    the span, and the answer is the truth.
    """
    with_one = _point(_one_shadow(), two_shadow_frame)
    with_two = _point(_both_shadows(), two_shadow_frame)

    assert abs(with_two - BETA) < 0.05, with_two
    assert abs(with_one - BETA) > 0.15, with_one


def test_the_answer_does_not_depend_on_which_shadow_is_written_first(
        two_shadow_frame):
    """Terms are a sum, and a sum does not care about order — but the design
    matrix's columns do come out in the order they were written, and a
    solve that quietly depended on that would be reporting a fact about the
    program text."""
    swapped = _program(
        proxies=(("z2", "z1"), ("w2", "w1")),
        channel=_bridge([_term(_factor("w2")), _term(_factor("w1"))],
                        [_term(_factor("z2")), _term(_factor("z1"))]))
    assert _point(swapped, two_shadow_frame) == pytest.approx(
        _point(_both_shadows(), two_shadow_frame), abs=1e-6)


def test_both_proxies_reach_the_reader(two_shadow_frame):
    """A report naming one of two negative controls describes a study that
    was not run. Checked in both languages because the joining punctuation
    between them is the reader's, not the producer's."""
    out = themis.estimate(_both_shadows(), two_shadow_frame,
                          ci_bootstrap=0)["results"][0]
    for lang in ("zh", "en"):
        report = themis.build_analysis_report(out, lang=lang)
        for name in ("w1", "w2", "z1", "z2"):
            assert f"`{name}`" in report, (lang, name)


def test_the_estimand_block_carries_every_role_it_rests_on(two_shadow_frame):
    out = themis.estimate(_both_shadows(), two_shadow_frame,
                          ci_bootstrap=0)["results"][0]
    block = out["extensions"]["proximal_estimand"]
    assert block["treatment_proxy"] == ["z1()", "z2()"]
    assert block["outcome_proxy"] == ["w1()", "w2()"]
    assert block["covariates"] == []
    # Two terms of two columns each, less one shared constant apiece.
    assert block["dimension"] == 3 and block["instrument_dimension"] == 3


# --- oracle two: a stratum the bridge is different inside ----------------------

@pytest.fixture(scope="module")
def stratified_frame() -> pd.DataFrame:
    """A proxy whose relationship to the confounder differs by stratum.

    ``c`` is observed and settled before treatment. The outcome proxy loads
    on ``u`` at 0.5 in one stratum and at 2.0 in the other, so the bridge

        h(w, x, c) = βx + (d / b(c))·w

    is a DIFFERENT function of ``w`` in each, and an additive term can only
    move the whole bridge up or down.

    Treatment assignment depends on ``u`` at different strengths in the two
    strata as well, and that half is not decoration — it is what the first
    version of this fixture was missing. With the same assignment rule
    everywhere, both arms carry the same mix of strata, the additive
    design's misfit is the same in each, and it CANCELS in the contrast:
    the wrong span lands within two percent of the truth and this file
    would have been claiming something false. What the interaction buys is
    only visible where the arms are composed differently, which is exactly
    where a stratified question is worth asking.
    """
    rng = np.random.default_rng(20260830)
    n = 8000
    c = (rng.random(n) < 0.5).astype(float)
    u = rng.standard_normal(n)
    load = np.where(c > 0.5, 2.0, 0.5)
    assignment = np.where(c > 0.5, 2.5, 0.3)
    x = rng.random(n) < 1 / (1 + np.exp(-(assignment * u)))
    return pd.DataFrame({
        "c": c,
        "x": x,
        "y": BETA * x + 1.2 * u + 0.3 * rng.standard_normal(n),
        "z": 1.3 * u + 0.35 * rng.standard_normal(n),
        "w": load * u + 0.35 * rng.standard_normal(n),
    })


def _interacted():
    return _program(
        proxies=(("z",), ("w",)), covariates=("c",),
        channel=_bridge(
            [_term(_factor("w"), _factor("c"))],
            [_term(_factor("z", dimension=3), _factor("c"))]))


def _added():
    return _program(
        proxies=(("z",), ("w",)), covariates=("c",),
        channel=_bridge(
            [_term(_factor("w")), _term(_factor("c"))],
            [_term(_factor("z", dimension=3)), _term(_factor("c"))]))


def test_a_stratifier_multiplied_in_answers_what_one_added_in_cannot(
        stratified_frame):
    """The reason a term holds several variables.

    Both programs declare the same covariate and condition on it. Only the
    one that lets the bridge BE a different function of the proxy inside
    each stratum finds the truth; the additive one is left fitting one
    slope to two, and lands a third of the effect below it.
    """
    interacted = _point(_interacted(), stratified_frame)
    added = _point(_added(), stratified_frame)

    assert abs(interacted - BETA) < 0.05, interacted
    assert abs(added - BETA) > 0.35, added


def test_the_covariate_reaches_the_reader(stratified_frame):
    """Conditioning on something changes what the number is ABOUT, so a
    reader who is not told cannot know which quantity they were handed."""
    out = themis.estimate(_interacted(), stratified_frame,
                          ci_bootstrap=0)["results"][0]
    assert out["extensions"]["proximal_estimand"]["covariates"] == ["c()"]
    for lang, fragment in (("zh", "给定"), ("en", "given")):
        assert fragment in themis.build_analysis_report(out, lang=lang)


def test_an_interaction_says_it_is_one(stratified_frame):
    """A design's width is not its shape. Two designs of the same width can
    be an interaction and a pair of additive terms, and which one ran is
    what a reader deciding whether to believe the number needs."""
    out = themis.estimate(_interacted(), stratified_frame,
                          ci_bootstrap=0)["results"][0]
    for lang, fragment in (("zh", "交互"), ("en", "interaction")):
        assert fragment in themis.build_analysis_report(out, lang=lang)


def test_a_truthful_stratified_answer_verifies(stratified_frame):
    """The re-derivation reaches the same number from the recorded moments
    alone — over a design of four columns built from two variables, which
    is the arrangement the record had no way to describe before."""
    themis.verify(_interacted(), _answered(_interacted(), stratified_frame))


# --- what the door says no to -------------------------------------------------

def _refused(program) -> SemanticError:
    with pytest.raises(SemanticError) as raised:
        themis.run(program)
    return raised.value


def test_a_treatment_proxy_on_the_outcome_side_is_refused():
    """The bridge is a function of (W, X, C). A treatment-side proxy is the
    direction moments are taken ALONG, and putting it among the unknowns
    asks the equation to solve for the thing it is being tested against."""
    bad = _program(
        proxies=(("z",), ("w",)),
        channel=_bridge([_term(_factor("w")), _term(_factor("z"))],
                        [_term(_factor("z", dimension=3))]))
    assert _refused(bad).species is (
        Malformed.SIEVE_OUTCOME_TERM_NAMES_A_STRANGER)


def test_an_outcome_proxy_on_the_moment_side_is_refused():
    """The mirror, and not the same mistake: this one would make the
    equation hold by construction rather than fail to be posed."""
    bad = _program(
        proxies=(("z",), ("w",)),
        channel=_bridge([_term(_factor("w"))],
                        [_term(_factor("z")), _term(_factor("w"))]))
    assert _refused(bad).species is (
        Malformed.SIEVE_MOMENT_TERM_NAMES_A_STRANGER)


def test_a_proxy_the_design_never_uses_is_refused():
    """Declaring a negative control and then not expanding it is a claim
    with no arithmetic behind it: model (f) is checked over the pair, the
    ledger counts it, and the number does not know it exists."""
    bad = _program(
        proxies=(("z1", "z2"), ("w1", "w2")),
        channel=_bridge([_term(_factor("w1"))],
                        [_term(_factor("z1")), _term(_factor("z2"))]))
    error = _refused(bad)
    assert error.species is Malformed.SIEVE_LEAVES_A_PROXY_UNUSED
    assert error.details["variables"] == ["w2"]


def test_a_covariate_the_moments_do_not_span_is_refused():
    """(b1) is an equality that holds GIVEN C. A bridge that varies in four
    directions of C, tested at moments that vary in two, is not identified
    by those moments — and the failure is silent, because the solve
    succeeds and returns a number."""
    bad = _program(
        proxies=(("z",), ("w",)), covariates=("c",),
        channel=_bridge([_term(_factor("w"), _factor("c"))],
                        [_term(_factor("z", dimension=4))]))
    error = _refused(bad)
    assert error.species is Malformed.COVARIATE_NOT_ON_BOTH_SIDES
    assert error.details["variable"] == "c"


def test_a_covariate_the_treatment_causes_is_refused():
    """Stratifying on a consequence of the treatment blocks part of the
    effect being asked for. Back-door condition (i), applied to the set the
    caller added rather than to the confounder they declared."""
    bad = _program(
        proxies=(("z",), ("w",)), covariates=("c",),
        edges=(("x", "c"),),
        channel=_bridge([_term(_factor("w")), _term(_factor("c"))],
                        [_term(_factor("z", dimension=3)),
                         _term(_factor("c"))]))
    out = themis.run(bad)["results"][0]
    assert out["status"] == "needs_investigation"
    assert any("covariate_is_descendant" in str(g)
               for g in out.get("missing_information", ()))


def test_a_leak_from_the_second_proxy_alone_is_refused():
    """Model (f) is read over every pair, which is what makes a set of
    proxies a set rather than a list nobody checked past the first. Here
    ``w1`` is sound and ``w2`` is caused by ``z1``, so a criterion that
    stopped at the first pair would admit the whole program."""
    bad = _program(
        proxies=(("z1",), ("w1", "w2")),
        edges=(("z1", "w2"),),
        channel=_bridge([_term(_factor("w1")), _term(_factor("w2"))],
                        [_term(_factor("z1", dimension=4))]))
    out = themis.run(bad)["results"][0]
    assert out["status"] == "needs_investigation"
    assert any("outcome_proxy_leaks_to_treatment_proxy" in str(g)
               for g in out.get("missing_information", ()))


def test_the_discrete_channel_still_takes_one_proxy_each():
    """Formula (5) inverts ONE k×k measurement matrix. Two proxies on a
    side is not a harder version of that computation, it is a different
    one — so the refusal names the channel that does take them."""
    bad = _program(
        proxies=(("z1", "z2"), ("w",)),
        scales={"z1": "discrete", "z2": "discrete", "w": "discrete"},
        channel={"kind": "discrete_channel", "latent_cardinality": 2})
    error = _refused(bad)
    assert error.species is (
        Malformed.DISCRETE_CHANNEL_TAKES_ONE_PROXY_EACH)
    assert error.details["treatment_proxies"] == 2


def test_the_discrete_channel_takes_no_covariates():
    bad = _program(
        proxies=(("z",), ("w",)), covariates=("c",),
        channel={"kind": "discrete_channel", "latent_cardinality": 2})
    assert _refused(bad).species is (
        Malformed.DISCRETE_CHANNEL_TAKES_NO_COVARIATES)


def test_a_design_with_fewer_moments_than_unknowns_is_still_refused():
    """The rule that survived the widths becoming derived — and it is
    stronger for it: there is no integer beside the design to be wrong
    about, so what is compared is the two designs themselves."""
    bad = _program(
        proxies=(("z",), ("w1", "w2")),
        channel=_bridge([_term(_factor("w1", dimension=3)),
                         _term(_factor("w2", dimension=3))],
                        [_term(_factor("z"))]))
    error = _refused(bad)
    assert error.species is Malformed.BRIDGE_UNDER_DETERMINED
    # 1 + 2 + 2 unknowns against 1 + 1 moments.
    assert error.details["dimension"] == 5
    assert error.details["instruments"] == 2


# --- what the re-derivation says no to ----------------------------------------

def _answered(program, frame) -> dict:
    return themis.estimate(program, frame, ci_bootstrap=0)["results"][0]


def _factor_record(result: dict, side: str, term: int, factor: int) -> dict:
    """One factor of one recorded design, as the wire holds it."""
    for step in result["derivation"]["steps"]:
        if step.get("rule") == "numeric_proximal_bridge_estimate":
            design = step["inputs"]["measurement_channel"]["items"][side]
            return design["items"][term]["items"][factor]["items"]
    raise AssertionError("no bridge solve step in this derivation")


def _refused_by_verify(forged, program) -> str:
    from themis.verifier import VerificationError

    with pytest.raises(VerificationError) as raised:
        themis.verify(program, forged)
    return str(raised.value)


def test_a_design_that_swaps_a_factor_of_one_term_is_refused(
        stratified_frame):
    """The tie to the query, over a design with more than one factor in it.

    Everything else in the record still agrees with itself, and a check
    that compared only the WIDTH would pass: the forged design has exactly
    as many columns as the declared one, built from a different assumption
    about where the bridge lies. The doctored factor is the SECOND of its
    term, which is the one a check written for a single basis per side
    could not have been looking at.
    """
    forged = copy.deepcopy(_answered(_interacted(), stratified_frame))
    _factor_record(forged, "w_basis", 0, 1)["family"] = "piecewise_linear"
    assert "the bridge is assumed to lie among" in _refused_by_verify(
        forged, _interacted())


def test_a_design_that_renames_a_variable_is_refused(stratified_frame):
    """The half a family check would miss. Same families, same dimensions,
    same width — a different column of the frame."""
    forged = copy.deepcopy(_answered(_interacted(), stratified_frame))
    _factor_record(forged, "w_basis", 0, 0)["variable"] = "c"
    assert "the bridge is assumed to lie among" in _refused_by_verify(
        forged, _interacted())
