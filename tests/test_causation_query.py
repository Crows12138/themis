"""Integration tests for the `causation` query kind — PN / PS / PNS
(Tian & Pearl 2000) wired end-to-end through themis.run + themis.verify.

The pure-formula core lives in tests/test_probabilities_of_causation.py
(verified against the published drug-example numbers). These tests pin
the *integration*: parsing, the observational-joint recovery from theta,
the two ways the interventional risks are obtained (derived via effect
identification vs. user-supplied experimental data), result packaging,
and the independent verifier.
"""
from __future__ import annotations

import copy

import pytest

from themis import kernel
from themis.output.analysis_report import build_analysis_report
from themis.verifier.errors import RuleCheckFailed
from themis import language

X = {"predicate": "drug", "args": [{"type": "const", "name": "p"}]}
Y = {"predicate": "death", "args": [{"type": "const", "name": "p"}]}


def _prog(query, *, bidirected=False, p_x1=0.5, py_x1=0.2, py_x0=0.1):
    stmts = [{"kind": "cause", "from": X, "to": Y}]
    if bidirected:
        stmts.append({"kind": "bidirected", "left": X, "right": Y})
    stmts += [
        {"kind": "probability", "target": {"atom": X, "value": True},
         "given": [], "value": p_x1},
        {"kind": "probability", "target": {"atom": Y, "value": True},
         "given": [{"atom": X, "value": True}], "value": py_x1},
        {"kind": "probability", "target": {"atom": Y, "value": True},
         "given": [{"atom": X, "value": False}], "value": py_x0},
        {"kind": "query", "id": "q1", "query": query},
    ]
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "p"}]},
        "statements": stmts,
    }


# ============================================ derived interventional risks


def test_exogenous_monotonic_derives_risks_and_matches_analytic():
    """X→Y, no confounding ⇒ P(Y|do(X))=P(Y|X) is derived from theta.
    With P(x)=0.5, P(y|x)=0.2, P(y|x')=0.1 the analytic monotone points
    are PN=0.5, PNS=0.1, PS=1/9."""
    prog = _prog({"kind": "causation", "cause": X, "effect": Y,
                  "monotonic": True})
    r = kernel.run(prog)["results"][0]
    assert r["status"] == "counterfactual_solved"
    assert r["query_kind"] == "causation"
    c = r["extensions"]["causation"]
    assert c["interventional_risk_provenance"] == "derived_identification"
    assert abs(c["p_y_do_x1"] - 0.2) < 1e-9 and abs(c["p_y_do_x0"] - 0.1) < 1e-9
    assert abs(c["pn"]["point"] - 0.5) < 1e-6
    assert abs(c["pns"]["point"] - 0.1) < 1e-6
    assert abs(c["ps"]["point"] - (1.0 / 9.0)) < 1e-6
    # Headline numeric_result carries the PN point.
    assert abs(r["numeric_result"]["value"] - 0.5) < 1e-6
    kernel.verify(prog, r)  # independent audit accepts


def test_measured_confounder_derives_risks_via_backdoor():
    """Z→X, Z→Y, X→Y: do(X) is confounded but identifiable via backdoor
    on the measured Z. The observational joint needs ancestral BN
    factorization (P(X)/P(Y|X) marginals aren't directly in theta), and
    the interventional risks come from the g-formula over Z. Regression:
    an earlier joint-recovery that only did local P(X)·P(Y|X) chain-rule
    failed this whole family with a spurious data gap."""
    Z = {"predicate": "sick", "args": [{"type": "const", "name": "p"}]}
    prog = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "p"}]},
        "statements": [
            {"kind": "cause", "from": Z, "to": X},
            {"kind": "cause", "from": Z, "to": Y},
            {"kind": "cause", "from": X, "to": Y},
            {"kind": "probability", "target": {"atom": Z, "value": True},
             "given": [], "value": 0.5},
            {"kind": "probability", "target": {"atom": X, "value": True},
             "given": [{"atom": Z, "value": True}], "value": 0.8},
            {"kind": "probability", "target": {"atom": X, "value": True},
             "given": [{"atom": Z, "value": False}], "value": 0.2},
            {"kind": "probability", "target": {"atom": Y, "value": True},
             "given": [{"atom": X, "value": True}, {"atom": Z, "value": True}],
             "value": 0.6},
            {"kind": "probability", "target": {"atom": Y, "value": True},
             "given": [{"atom": X, "value": True}, {"atom": Z, "value": False}],
             "value": 0.3},
            {"kind": "probability", "target": {"atom": Y, "value": True},
             "given": [{"atom": X, "value": False}, {"atom": Z, "value": True}],
             "value": 0.5},
            {"kind": "probability", "target": {"atom": Y, "value": True},
             "given": [{"atom": X, "value": False}, {"atom": Z, "value": False}],
             "value": 0.1},
            {"kind": "query", "id": "q1",
             "query": {"kind": "causation", "cause": X, "effect": Y,
                       "monotonic": True}},
        ],
    }
    r = kernel.run(prog)["results"][0]
    assert r["status"] == "counterfactual_solved"
    c = r["extensions"]["causation"]
    assert c["interventional_risk_provenance"] == "derived_identification"
    # Backdoor g-formula: P(Y=1|do(X=1))=Σ_z P(Y=1|X=1,z)P(z)=0.45; do(X=0)=0.30.
    assert abs(c["p_y_do_x1"] - 0.45) < 1e-9
    assert abs(c["p_y_do_x0"] - 0.30) < 1e-9
    # Joint via ancestral factorization (summing over Z).
    assert abs(c["observational_joint"]["p_x1_y1"] - 0.27) < 1e-9
    # Monotone points.
    assert abs(c["pns"]["point"] - 0.15) < 1e-9
    assert abs(c["pn"]["point"] - (0.06 / 0.27)) < 1e-9
    assert abs(c["ps"]["point"] - (0.09 / 0.41)) < 1e-9
    kernel.verify(prog, r)


def test_non_monotonic_returns_bounds_not_points():
    prog = _prog({"kind": "causation", "cause": X, "effect": Y})
    r = kernel.run(prog)["results"][0]
    assert r["status"] == "counterfactual_bounded"
    c = r["extensions"]["causation"]
    for q in ("pn", "ps", "pns"):
        # Null, and present. "Not point-identified" is said, not left to the
        # key being missing — the data route said it this way all along and
        # this one used to omit, which no reader could tell from a producer
        # that forgot.
        assert c[q]["point"] is None
        assert c[q]["lower"] <= c[q]["upper"]
    # Headline is an interval, not a point.
    assert r["numeric_result"]["value"] is None
    assert r["numeric_result"]["interval"]["low"] <= r["numeric_result"]["interval"]["high"]
    kernel.verify(prog, r)


# ============================================ user-supplied experimental risks
# Tian & Pearl (2000) drug-court example: confounded (do(X) not identifiable
# from observation alone), experimental risks supplied from an RCT.


def test_drug_example_experimental_matches_tian_pearl_published():
    prog = _prog(
        {"kind": "causation", "cause": X, "effect": Y, "monotonic": True,
         "experimental_risk_treated": 0.016, "experimental_risk_control": 0.014},
        bidirected=True, py_x1=0.002, py_x0=0.028,
    )
    r = kernel.run(prog)["results"][0]
    assert r["status"] == "counterfactual_solved"
    c = r["extensions"]["causation"]
    assert c["interventional_risk_provenance"] == "user_experimental"
    # Tian-Pearl eqs (58)-(63): PN=1.0, PNS∈[0.002,0.016], PS∈[0.002,0.031].
    assert abs(c["pn"]["point"] - 1.0) < 1e-3
    assert abs(c["pns"]["lower"] - 0.002) < 1e-3
    assert abs(c["pns"]["upper"] - 0.016) < 1e-3
    assert abs(c["ps"]["lower"] - 0.002) < 1e-3
    assert abs(c["ps"]["upper"] - 0.031) < 1e-3
    kernel.verify(prog, r)


# ============================================ and it reaches the reader


def test_the_answer_section_names_all_three_quantities():
    """The question line asks for PN, PS and PNS by name.

    The answer was ``numeric_result``, which holds PN because a headline
    has to be one number — so the report printed one of three with no name
    on it. Answering from theta produces no ``numeric_estimate``, so no
    answer shape described it and nothing noticed; the block that held all
    three was read by the detachable explainer alone.
    """
    prog = _prog({"kind": "causation", "cause": X, "effect": Y,
                  "monotonic": True})
    r = kernel.run(prog)["results"][0]
    answer = build_analysis_report(r, program=prog).split(
        "## 答案", 1)[1].split("\n##", 1)[0]
    assert "必要性 PN" in answer and "0.5" in answer
    assert "充分性 PS" in answer and "0.1111" in answer
    assert "必要且充分 PNS" in answer and "0.1" in answer
    # And where the two interventional risks it is computed from came
    # from, which is what says how far PN can be trusted.
    assert "do X" in answer and "识别层" in answer


def test_without_monotonicity_the_answer_section_says_bounds_are_all_there_is():
    """The same three quantities, and the reason there is no point.

    Monotonicity is an assumption about the mechanism, not something the
    data can supply, so its absence is an answer rather than a hole — and
    a reader who is shown ``[0.5, 1]`` with no word about why has no way
    to tell those two apart.
    """
    prog = _prog({"kind": "causation", "cause": X, "effect": Y})
    r = kernel.run(prog)["results"][0]
    answer = build_analysis_report(r, program=prog).split(
        "## 答案", 1)[1].split("\n##", 1)[0]
    assert "未假设单调性" in answer
    assert "必要性 PN" in answer and "[0.5, 1]" in answer
    assert "充分性 PS" in answer and "[0.1111, 0.2222]" in answer
    assert "必要且充分 PNS" in answer and "[0.1, 0.2]" in answer
    assert "**0.5**" not in answer, "a bound printed as if it were a point"


# ============================================ gap paths


def test_confounded_without_experimental_risks_is_a_gap():
    """A bidirected X↔Y bow arc makes P(Y|do(X)) unidentifiable; with no
    experimental risks supplied the query cannot be answered and surfaces
    the experimental-risk escape hatch."""
    prog = _prog(
        {"kind": "causation", "cause": X, "effect": Y, "monotonic": True},
        bidirected=True,
    )
    r = kernel.run(prog)["results"][0]
    assert r["status"] == "needs_investigation"
    names = {m["name"] for m in r["missing_information"]}
    assert "causation:interventional_risk_unavailable" in names


def test_infeasible_experimental_risks_is_a_gap():
    """Regression (stress-test find): user-supplied experimental risks that
    contradict the observational joint (P(y_x) outside [P(x,y), P(x,y)+P(x')])
    must be reported as a gap, not silently turned into an inverted
    [lower>upper] PN/PS/PNS interval."""
    prog = _prog(
        {"kind": "causation", "cause": X, "effect": Y,
         "experimental_risk_treated": 1.0, "experimental_risk_control": 0.0},
        bidirected=True, p_x1=0.5, py_x1=0.5, py_x0=0.5,
    )
    r = kernel.run(prog)["results"][0]
    assert r["status"] == "needs_investigation"
    assert any(m["name"] == "causation:interventional_risks_infeasible"
               for m in r["missing_information"])


def test_verify_rejects_inverted_bounds_from_tampered_risk(solved):
    """The verifier independently recomputes the Tian-Pearl bounds from the
    declared inputs; an interventional risk tampered to an infeasible value
    inverts the bounds, which the lower<=upper invariant must reject."""
    prog, r = solved
    rT = copy.deepcopy(r)
    rT["derivation"]["steps"][-1]["inputs"]["p_y_do_x1"] = 1.0  # infeasible
    with pytest.raises(Exception):
        kernel.verify(prog, rT)


def test_non_binary_cause_is_outside_language():
    Xc = {"predicate": "dose", "args": [{"type": "const", "name": "p"}]}
    prog = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "p"}]},
        "statements": [
            {"kind": "cause", "from": Xc, "to": Y},
            {"kind": "probability", "target": {"atom": Xc, "value": "low"},
             "given": [], "value": 0.5},
            {"kind": "probability", "target": {"atom": Xc, "value": "high"},
             "given": [], "value": 0.5},
            {"kind": "probability", "target": {"atom": Y, "value": True},
             "given": [{"atom": Xc, "value": "low"}], "value": 0.1},
            {"kind": "probability", "target": {"atom": Y, "value": True},
             "given": [{"atom": Xc, "value": "high"}], "value": 0.3},
            {"kind": "query", "id": "q1",
             "query": {"kind": "causation", "cause": Xc, "effect": Y}},
        ],
    }
    r = kernel.run(prog)["results"][0]
    assert r["status"] == "outside_language"
    # The refusal travels in the field the schema has always had for it,
    # bearing the species the data end raises for the same reason — not
    # in prose in an extensions block only the explainer ever read.
    failure = r["estimator_failure"]
    assert failure["failure_type"] == "cause_or_effect_not_binary"
    assert failure["kind"] == "unbuilt"
    assert "binary" in failure["reason"] and "dose" in failure["reason"]
    # And it reaches the reader.
    report = build_analysis_report(r, program=prog)
    assert "binary" in report.split("## 答案", 1)[1].split("##", 1)[0]


# ============================================ verifier independence (tamper)


@pytest.fixture()
def solved():
    prog = _prog({"kind": "causation", "cause": X, "effect": Y,
                  "monotonic": True})
    return prog, kernel.run(prog)["results"][0]


def _step_output_items(result):
    return result["derivation"]["steps"][-1]["output"]["items"]


def test_verify_rejects_tampered_pn_point(solved):
    prog, r = solved
    rT = copy.deepcopy(r)
    _step_output_items(rT)["pn"]["items"]["point"] = 0.99
    with pytest.raises(Exception):
        kernel.verify(prog, rT)


def test_verify_rejects_tampered_joint_cell_input(solved):
    prog, r = solved
    rT = copy.deepcopy(r)
    rT["derivation"]["steps"][-1]["inputs"]["p_x1_y1"] = 0.3
    with pytest.raises(Exception):
        kernel.verify(prog, rT)


def test_verify_rejects_tampered_headline(solved):
    prog, r = solved
    rT = copy.deepcopy(r)
    rT["numeric_result"]["value"] = 0.77
    with pytest.raises(Exception):
        kernel.verify(prog, rT)


def test_verify_rejects_extensions_only_tamper(solved):
    """Regression (stress-test find): PS/PNS surface to a reader only via
    extensions.causation (the headline is just PN). Tampering that display
    copy while leaving the audited derivation intact must NOT pass —
    verify cross-checks extensions against the verified envelope."""
    prog, r = solved
    rT = copy.deepcopy(r)
    rT["extensions"]["causation"]["ps"]["point"] = 0.99   # derivation untouched
    with pytest.raises(Exception):
        kernel.verify(prog, rT)


def test_verify_rejects_phantom_point_when_non_monotonic(solved):
    """Flipping monotonic to False while keeping a point must be caught —
    the quantity is not point-identified without monotonicity."""
    prog, r = solved
    rT = copy.deepcopy(r)
    rT["derivation"]["steps"][-1]["inputs"]["monotonic"] = False
    _step_output_items(rT)["monotonic"] = False
    with pytest.raises(Exception):
        kernel.verify(prog, rT)


def test_the_report_names_the_licence_behind_the_two_do_risks():
    """Both paths reach this line and each must get its own sentence.

    The gloss used to be a map in the report and another in the explainer
    and a two-branch ``if/else`` in a third place; they now all read one
    table. What is worth pinning HERE is the end of the pipe: the report
    prints the licence for the do-risks it actually got, on both paths.
    The vocabulary itself is held together in
    ``tests/test_risk_provenance.py``.
    """
    from themis import risk_provenance

    prog = _prog({"kind": "causation", "cause": X, "effect": Y,
                  "monotonic": True})
    r = kernel.run(prog)["results"][0]
    assert r["extensions"]["causation"][
        "interventional_risk_provenance"] == "derived_identification"
    report = build_analysis_report(r, program=prog)
    assert (risk_provenance.RiskProvenance.DERIVED_IDENTIFICATION
            .words[language.DEFAULT]) in report


# =========================== a malformed claim is a verdict, not an exception

def _pn(result):
    return _step_output_items(result)["pn"]["items"]


def test_a_non_numeric_bound_is_a_verdict_and_not_a_raw_exception(solved):
    """A verifier that crashes has not rejected anything.

    Everything the verifier decides leaves it as a ``VerificationError`` —
    that is the contract ``kernel.verify`` is called under, and there is no
    ``try``/``except`` between a rule and its caller to soften anything else.
    So a bound the producer wrote as a non-numeral must come back as a
    verdict on the claim; if instead ``float`` is handed the string and its
    ``ValueError`` walks out, the caller cannot tell "this answer is wrong"
    from "the checker broke", and the claim goes un-adjudicated.

    Both bounds are tampered on purpose. While the two comparisons sat in
    one ``or``, a mismatching ``lower`` short-circuited and the malformed
    ``upper`` was never touched, so this hole could not be reached from
    here; reading both bounds before comparing them is what opened it.
    """
    prog, r = solved
    rT = copy.deepcopy(r)
    _pn(rT).update(lower=0.9, upper="abc")
    with pytest.raises(RuleCheckFailed) as exc:
        kernel.verify(prog, rT)
    assert exc.value.rule == "causation_probability_bounds"


def test_a_nan_bound_is_refused_by_the_rule_that_owns_it(solved):
    """NaN fails the opposite way round from a non-number: silently.

    Every check on these bounds has the shape ``abs(claimed - expected) >
    tol``, and that is False against NaN — so a NaN bound does not trip any
    numeric check, it *passes* them all. What used to notice was the
    downstream cross-check of the display copy in ``extensions``, and only
    because ``nan != nan``; tamper both copies to the same NaN, as a
    producer bug actually would, and the reader was told the display copy
    diverged from the audited answer, which is a false statement about a
    byte-identical copy. Being refused by the rule that owns the envelope is
    what makes the diagnosis true.
    """
    prog, r = solved
    rT = copy.deepcopy(r)
    _pn(rT).update(lower=float("nan"), upper=float("nan"))
    rT["extensions"]["causation"]["pn"].update(
        lower=float("nan"), upper=float("nan"))
    with pytest.raises(RuleCheckFailed) as exc:
        kernel.verify(prog, rT)
    assert exc.value.rule == "causation_probability_bounds"
    assert "nan" in str(exc.value)


def test_a_non_numeric_point_is_a_verdict_too(solved):
    """The point slot is read by the same rule and needs the same answer.

    It is a separate line of code from the bounds and it used to convert on
    its own, so it could fail in both directions the bounds could — crash on
    a non-numeral, certify a NaN — while the bounds beside it were guarded.
    A slot that may legitimately be absent still may not be legitimately
    unreadable.
    """
    prog, r = solved
    rT = copy.deepcopy(r)
    _pn(rT)["point"] = "abc"
    with pytest.raises(RuleCheckFailed) as exc:
        kernel.verify(prog, rT)
    assert exc.value.rule == "causation_probability_bounds"


def test_a_non_numeric_bound_is_a_verdict_on_the_polytope_route_too():
    """The same rule reaches the same envelope down a second body.

    ``causation_probability_bounds`` splits on the licence: Tian-Pearl's
    closed form when both do-risks are numbers, the response-type polytope
    when a bow arc means there are none. The two write their own envelope
    comparison, so a guard that only one of them goes through leaves the
    other exactly as it was — this pins that both read a claimed bound the
    same way.
    """
    prog = _bow_arc_prog()
    r = kernel.run(prog)["results"][0]
    assert _step_output_items(r)[
        "interventional_risk_provenance"] == "instrument_response_polytope"
    rT = copy.deepcopy(r)
    _pn(rT).update(lower=0.9, upper="abc")
    with pytest.raises(RuleCheckFailed) as exc:
        kernel.verify(prog, rT)
    assert exc.value.rule == "causation_probability_bounds"


def _bow_arc_prog():
    """Z→X→Y with a bow arc X<->Y: no do-risk is point-identified, so the
    causation query is answered over the instrument's response polytope."""
    Z = {"predicate": "assigned", "args": [{"type": "const", "name": "p"}]}

    def p(target, given, value):
        return {"kind": "probability", "target": {"atom": target, "value": True},
                "given": given, "value": value}

    def at(atom, value):
        return {"atom": atom, "value": value}

    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "p"}]},
        "statements": [
            {"kind": "cause", "from": Z, "to": X},
            {"kind": "cause", "from": X, "to": Y},
            {"kind": "bidirected", "left": X, "right": Y},
            p(Z, [], 0.5),
            p(X, [at(Z, True)], 0.8),
            p(X, [at(Z, False)], 0.2),
            p(Y, [at(X, True), at(Z, True)], 0.3),
            p(Y, [at(X, False), at(Z, True)], 0.1),
            p(Y, [at(X, True), at(Z, False)], 0.35),
            p(Y, [at(X, False), at(Z, False)], 0.15),
            {"kind": "query", "id": "q1",
             "query": {"kind": "causation", "cause": X, "effect": Y,
                       "monotonic": False}},
        ],
    }
