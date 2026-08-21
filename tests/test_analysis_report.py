"""Phase — deterministic unified analysis report (build_analysis_report).

Pins that the report assembles the whole envelope into one Markdown
document, foregrounding the answer, then the two Themis differentiators
(verification status + assumptions/data-gaps), across every result
status — and that it stays a passive assembler (no reasoning re-run).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import themis
from themis import language
from themis import refusals
from themis.estimation.outcome_error import OutcomeErrorDesign
from themis.output.assumption_glossary import classify_assumption
from themis.output.result_orchestrator import augment_assumption_ledger
from themis.output.analysis_report import (
    _OUTCOME_ERROR_DESIGN_WORDS,
    _estimate_meta,
    _kind_words,
    _render_answer,
    build_analysis_report,
)


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _backdoor_program():
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False], "state_vs_event": "event"},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "cause", "from": _atom("z"), "to": _atom("x"), "annotations": {"source": "llm_proposal"}},
            {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "query", "id": "q", "query": {"kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True}, "given": []}},
        ],
    }


def _backdoor_data(n=3000, seed=0):
    rng = np.random.default_rng(seed)
    z = rng.integers(0, 2, n)
    x = (rng.random(n) < 0.3 + 0.4 * z).astype(int)
    y = (rng.random(n) < 0.2 + 0.3 * x + 0.2 * z).astype(int)
    return pd.DataFrame({"x": x.astype(bool), "y": y.astype(bool), "z": z.astype(bool)})


# ============================================ shape / always-on


def test_report_is_markdown_with_core_sections():
    res = themis.run(_backdoor_program())["results"][0]
    md = build_analysis_report(res, program=_backdoor_program())
    assert md.startswith("# 因果分析报告")
    for heading in ("## 问题", "## 答案", "## 因果模型", "## 验证"):
        assert heading in md


def test_report_is_deterministic():
    prog = _backdoor_program()
    res = themis.run(prog)["results"][0]
    assert build_analysis_report(res, program=prog) == build_analysis_report(res, program=prog)


# ============================================ numeric estimate (the flagship)


@pytest.fixture(scope="module")
def numeric_env():
    prog = _backdoor_program()
    env = themis.estimate(prog, _backdoor_data(), ci_bootstrap=100)
    return prog, env


def test_numeric_answer_shows_point_ci_method_and_robustness(numeric_env):
    prog, env = numeric_env
    md = build_analysis_report(env["results"][0], program=prog)
    assert "已估计（数值层）" in md
    assert "95% CI" in md
    assert "backdoor_logistic" in md
    assert "E-value" in md          # sensitivity/robustness surfaced
    assert "样本量 N=3000" in md


def test_numeric_report_shows_severity_ranked_assumptions(numeric_env):
    prog, env = numeric_env
    md = build_analysis_report(env["results"][0], program=prog)
    assert "## 假设" in md
    assert "作废级" in md            # invalidating identification assumptions
    assert "扭曲级" in md            # functional-form (distorting)


def test_stamp_reflects_a_passed_audit_set(numeric_env):
    prog, env = numeric_env
    res = env["results"][0]
    # genuine audit rows, run by the caller (the report never re-checks)
    rows = themis.audit(env.get("program", prog), res)
    assert rows and all(row["ok"] for row in rows)
    md = build_analysis_report(res, program=prog, audited=rows)
    assert "独立复核全部通过" in md
    assert f"✓ **{len(rows)} 项" in md


def test_stamp_names_the_check_that_did_not_pass(numeric_env):
    """One ✗ among several ✓ has to be findable, or a reader who sees the
    section at all reads the whole thing as passed."""
    prog, env = numeric_env
    res = env["results"][0]
    rows = themis.audit(env.get("program", prog), res)
    broken = [
        {**row, "ok": False, "refusal": "VerificationError: 端点对不上"}
        if row["audit"] == "verify" else row
        for row in rows
    ]
    md = build_analysis_report(res, program=prog, audited=broken)
    assert "1 项复核未通过" in md
    assert "端点对不上" in md
    # the checks that did pass still say so
    assert "✓ " in md


def test_without_audit_rows_it_says_what_applies_and_claims_nothing_ran(numeric_env):
    prog, env = numeric_env
    md = build_analysis_report(env["results"][0], program=prog, audited=None)
    assert "独立复核全部通过" not in md
    assert "复核未通过" not in md
    assert "本身可以被独立重算" in md
    assert "themis.verify(program, result)" in md
    assert "themis.audit(program, result)" in md


# ============================================ structural bool


def test_structural_cause_answer():
    prog = {
        "version": "0.1", "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "query", "id": "c", "query": {"kind": "cause", "from": _atom("x"), "to": _atom("y")}},
        ],
    }
    res = themis.run(prog)["results"][0]
    assert res["status"] == "structurally_solved"
    md = build_analysis_report(res, program=prog)
    assert "已解决（结构层）" in md
    assert "结论：**是**" in md
    assert "推导链" in md


# ============================================ needs data (identified, no data)


def test_identified_but_needs_data_report():
    prog = _backdoor_program()
    res = themis.run(prog)["results"][0]
    md = build_analysis_report(res, program=prog)
    assert "可识别" in md
    assert "没有数据" in md
    assert "## 数据缺口与下一步" in md
    # no derivation on this status → points at the gap-report verifier
    assert "verify_data_gap_report" in md


# ============================================ causal-model provenance


def test_model_flags_llm_proposal_edge():
    prog = _backdoor_program()
    res = themis.run(prog)["results"][0]
    md = build_analysis_report(res, program=prog)
    assert "z → x" in md
    assert "LLM 假设" in md
    assert "图例" in md


def test_model_flags_discovery_edge_with_confidence():
    # hand-built result (unit): only the program's edges matter for this section
    prog = {
        "version": "0.1", "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "cause", "from": _atom("a"), "to": _atom("b"),
             "annotations": {"source": "discovery:pc", "confidence": 0.9}},
        ],
    }
    md = build_analysis_report({"status": "needs_investigation", "query_kind": "effect"}, program=prog)
    assert "发现算法 PC" in md
    assert "稳定度 90%" in md


def test_program_none_omits_model_section_but_still_answers():
    res = themis.run(_backdoor_program())["results"][0]
    md = build_analysis_report(res)  # no program
    assert "## 因果模型" not in md
    assert "## 答案" in md


# ============================================ passive assembler / robustness


def test_minimal_result_does_not_crash():
    md = build_analysis_report({"status": "outside_language", "query_kind": "effect"})
    assert "超出" in md
    assert md.startswith("# 因果分析报告")


def test_bounds_answer_branch():
    res = {
        "status": "needs_investigation", "query_kind": "effect", "query_id": "b",
        "bounds_results": [{"lower_value": -0.19, "upper_value": 0.01,
                            "method": "balke_pearl_iv"}],
    }
    md = build_analysis_report(res)
    assert "区间" in md
    assert "balke_pearl_iv" in md


# ============================================ refusals as answers


def test_a_refusal_is_an_answer_not_a_missing_one():
    """A run that was given data and declined to trust it used to render
    as 「当前没有数据」.

    That sentence is the identified-but-no-data fall-through, reached
    because the refusal channel had no branch of its own — the report
    said the opposite of what happened.
    """
    res = {
        "status": "needs_investigation", "query_kind": "effect", "query_id": "r",
        "formula": "sum_z P(y|x,z)P(z)",
        "estimator_failure": {
            "estimator": "backdoor", "failure_type": "overlap_insufficient",
            "reason": "stratum z=3 has no treated rows", "kind": "data",
        },
    }
    md = build_analysis_report(res)
    assert "没有数据" not in md
    assert "这批数据支撑不住" in md
    assert "stratum z=3 has no treated rows" in md
    assert "overlap_insufficient" in md


def test_the_report_has_a_sentence_for_every_kind():
    """The registry owns the taxonomy, this file owns the words. A kind
    with no sentence falls back through to the generic line, which is the
    defect above returning under a new name.

    That every branch *exists* is ``assert_never``'s to check, statically.
    This asks the half a checker cannot see: that the branch returns a
    sentence rather than falling out with nothing."""
    for kind in refusals.Kind:
        assert _kind_words(kind), f"kind {kind!r} renders as nothing"


def test_a_kind_this_kernel_never_heard_of_gets_no_sentence():
    """What we read is wider than what we emit. An envelope from another
    kernel naming a sixth kind gets the generic line, not a wrong one."""
    assert _kind_words("kind_from_the_future") is None
    assert _kind_words(None) is None


@pytest.mark.parametrize("kind", sorted(refusals.Kind))
def test_each_kind_reads_as_something_different(kind):
    answer = _render_answer({
        "status": "needs_investigation", "query_kind": "effect", "query_id": "r",
        "estimator_failure": {
            "estimator": "e", "failure_type": "not_identified",
            "reason": "why it stopped", "kind": kind,
        },
    }, lang=language.DEFAULT)
    assert "why it stopped" in answer
    # graph is a finding about the model, backend is a fact about the
    # tool. A reader who cannot tell them apart learned nothing from the
    # kind, which is the only thing it is there to do.
    assert ("图" in answer) == (kind == "graph")


def test_a_point_outranks_a_refusal_that_sits_beside_it():
    """Dispatch attaches the longitudinal refusal to the first effect
    result, which may already carry a genuine back-door point. There the
    refusal is about a supplementary block, and the point is the answer."""
    res = {
        "status": "numerically_solved", "query_kind": "effect", "query_id": "r",
        "numeric_estimate": {"point": 0.31, "method": "backdoor_linear"},
        "estimator_failure": {
            "estimator": "longitudinal_gformula", "failure_type": "not_identified",
            "reason": "an unblocked back-door from A_1 to Y", "kind": "graph",
        },
    }
    answer = _render_answer(res, lang=language.DEFAULT)
    assert "0.31" in answer
    assert "没有给出数值" not in answer


def test_a_refusal_beside_a_point_still_reaches_the_reader():
    """Outranked is not the same as unsaid.

    ``_render_answer`` reaches the refusal only once nothing above it has
    fired, so a refusal about something SUPPLEMENTARY to the number — a
    correction the caller asked for, a precision cost on a design this
    package has no split for — was outranked into silence. A caller who
    declared what they knew about their outcome got the right number and not
    one word about the assessment they had asked for.
    """
    res = {
        "status": "numerically_solved", "query_kind": "effect", "query_id": "r",
        "numeric_estimate": {"point": 0.31, "method": "backdoor_linear"},
        "estimator_failure": {
            "estimator": "outcome_measurement_error",
            "failure_type": "requires_backdoor_identification",
            "reason": "no assessment is issued", "kind": "unbuilt",
        },
    }
    md = build_analysis_report(res)
    assert "0.31" in md
    assert "requires_backdoor_identification" in md
    assert "outcome_measurement_error" in md
    # And it says what it is: a second thing that was not produced, not the
    # absence of the number printed directly above it.
    assert "另有一项没能给出" in md
    assert "没有给出数值" not in md


def test_a_refusal_that_is_the_answer_is_not_repeated_under_it():
    """The note is keyed on the rendered answer, so the branch that already
    said the refusal does not say it twice."""
    res = {
        "status": "needs_investigation", "query_kind": "effect", "query_id": "r",
        "estimator_failure": {
            "estimator": "backdoor", "failure_type": "overlap_insufficient",
            "reason": "stratum z=3 has no treated rows", "kind": "data",
        },
    }
    md = build_analysis_report(res)
    assert md.count("overlap_insufficient") == 1
    assert "另有一项没能给出" not in md


def test_an_interval_outranks_a_refusal_that_sits_beside_it():
    """The same rule one rung down, and the one that decides where the
    refusal branch goes. Sixteen envelopes in the suite carry bounds AND a
    refusal — many more than carry a refusal beside a structural verdict —
    and in every one the interval is the answer to what was asked."""
    res = {
        "status": "needs_investigation", "query_kind": "effect", "query_id": "r",
        "bounds_results": [{
            "lower_value": -0.2, "upper_value": 0.4, "method": "manski",
        }],
        "estimator_failure": {
            "estimator": "backdoor", "failure_type": "overlap_insufficient",
            "reason": "a single observed treatment level", "kind": "data",
        },
    }
    answer = _render_answer(res, lang=language.DEFAULT)
    assert "区间" in answer
    assert "没有给出数值" not in answer


def test_a_refusal_outranks_a_verdict_about_the_graph():
    """A run given data that asked for a number and could not have one.

    Identification succeeded, so the envelope carries a structural verdict
    saying so — and that verdict used to be rendered in the answer slot,
    where a positivity violation reached the reader as "结论：是". It is
    true and it is not the answer; the question asked for a number.
    """
    res = {
        "status": "structurally_solved", "query_kind": "effect", "query_id": "r",
        "structural_result": {"value": True},
        "estimator_failure": {
            "estimator": "proximal", "failure_type": "insufficient_support",
            "reason": "an empty (Z, X) stratum", "kind": "data",
        },
    }
    answer = _render_answer(res, lang=language.DEFAULT)
    assert "没有给出数值" in answer
    assert "结论" not in answer


def test_a_verdict_about_the_graph_is_still_the_answer_when_it_is_the_answer():
    """The other half of the same rule. A cause / association / identify
    query produces nothing but the verdict, so nothing outranks it — which
    is why the branch can sit low without a query-kind test guarding it."""
    res = {
        "status": "structurally_solved", "query_kind": "cause", "query_id": "r",
        "structural_result": {"value": True, "supporting_paths": [["x", "y"]]},
    }
    assert _render_answer(res, lang=language.DEFAULT).startswith("结论：**是**")


# ============================================ 结局测量误差：设计说了什么


def _meta_line(design_kind: object) -> str:
    """The measurement-error line for one design, out of the shared lines."""
    block = {"outcome": "y", "se_inflation": 1.2534, "noise_share": 0.31}
    if design_kind is not None:
        block["design_kind"] = str(design_kind)
    lines = [
        ln for ln in _estimate_meta({"method": "m", "sample_size": 1500}, block, lang=language.DEFAULT)
        if "结局测量误差" in ln
    ]
    assert len(lines) == 1, lines
    return lines[0]


def test_every_design_has_a_word_before_it_can_reach_a_report():
    """A closed vocabulary reaches this surface complete or not at all.

    Checked against the enum rather than against a list written here: a
    fourth design added to the kernel is exactly the member that would
    otherwise arrive as its own identifier, and a list in the test would
    have been written from the three that already existed.
    """
    assert (set(_OUTCOME_ERROR_DESIGN_WORDS)
            == {str(d) for d in OutcomeErrorDesign})


@pytest.mark.parametrize("design", list(OutcomeErrorDesign))
def test_the_design_the_cost_was_taken_around_is_said_in_words(design):
    """WHICH residual absorbed σ²_v, and not as the envelope's token.

    Three designs price the same declared error against three different
    residuals, and the factor alone cannot be checked against a study
    without knowing which — so the identifier reaching the page would be
    the reader's only clue, and it is in the wrong language.
    """
    line = _meta_line(design)
    assert str(design) not in line
    assert "1.25" in line


def test_the_three_designs_do_not_say_the_same_thing():
    """The check the parametrized one cannot make: a table whose three
    entries were copies would pass every per-member assertion above while
    telling the reader nothing that varies."""
    said = {str(d): _meta_line(d) for d in OutcomeErrorDesign}
    assert len(set(said.values())) == len(said)


@pytest.mark.parametrize("design", list(OutcomeErrorDesign))
def test_a_factor_that_is_only_a_ceiling_is_said_to_be_one(design):
    """The number means different things on different designs.

    On the front door the influence function splits the variance and only
    one term carries the outcome residual, so the same arithmetic returns an
    UPPER BOUND — 1.25 reported against a true CI-width ratio of 1.09 on
    this repository's own front-door estimator. A reader who takes that as
    the cost has been told the outcome is worth remeasuring by a quarter
    more than it is.

    Keyed on ``exact`` rather than on the member name, because that is the
    fact the sentence is supposed to carry; naming ``front_door`` here would
    let a fourth inexact design ship saying the factor is the cost.
    """
    line = _meta_line(design)
    assert ("至多" in line and "上界" in line) is not design.exact


@pytest.mark.parametrize("design", list(OutcomeErrorDesign))
def test_the_route_that_can_move_the_point_says_so(design):
    """"点估计不受影响" is true on two of the three routes.

    The front-door graph posits an unmeasured confounder; if the error
    depends on it the classical premise fails on the design the outcome
    model conditions on, and what moves is the POINT. Saying the flat
    sentence there would be the report vouching for a premise about a
    variable nobody measured.
    """
    line = _meta_line(design)
    unconditional = "点估计不受影响" in line
    conditional = "未观测" in line and "点估计本身" in line
    assert unconditional != conditional
    # The two exact designs are the ones whose premise is about variables in
    # the data, which is the same fact that makes their factor exact.
    assert unconditional is design.exact


def test_an_envelope_that_never_named_the_design_claims_neither():
    """The input this line has to refuse: a factor with no design beside it.

    Reading it as the back-door one is the tempting default and is the one
    thing that cannot be done — which residual the factor was taken around
    is exactly what decides whether it is the cost or a ceiling, and an
    older build's envelope is not evidence about a question that build
    never asked.
    """
    line = _meta_line(None)
    assert "1.25" in line
    assert "无从判断" in line
    # It names no design, and it does not present the factor as settled.
    assert "至多" not in line
    for design in OutcomeErrorDesign:
        assert line != _meta_line(design)


def test_a_design_this_build_has_never_heard_of_is_not_guessed_at():
    """The same refusal one step further out: an envelope from a build that
    declares a fourth design. Falling back to any of the three sentences
    would have this report describe a residual it knows nothing about."""
    line = _meta_line("saturated_ratio")
    for design in OutcomeErrorDesign:
        assert line != _meta_line(design)
    # And it is the same sentence as no design at all — "a name this build
    # cannot read" and "no name" leave the reader in one position, and
    # splitting them would be a distinction they cannot act on.
    assert line == _meta_line(None)


# ============================================ 结局测量误差：新的两条前提


def _ledger_claims(assumptions: tuple[str, ...]) -> list[dict]:
    res = {
        "status": "numerically_solved", "query_kind": "effect", "query_id": "r",
        "numeric_estimate": {"point": 0.31, "method": "iv_2sls",
                             "assumptions": ["iv1_relevance"]},
        "outcome_error": {"outcome": "y", "se_inflation": 1.25,
                          "noise_share": 0.31, "assumptions": list(assumptions)},
    }
    augment_assumption_ledger(res)
    entries = res["extensions"]["assumption_ledger"]["assumptions"]
    return [e for e in entries if str(e.get("id", "")).startswith("outcome_error_")]


def test_the_instrument_premise_names_the_instrument_and_denies_the_other_one():
    """The IV route's premise is about the INSTRUMENT, and a reader who
    reads it as a wider classical premise will check the wrong variable.

    Mean-independence given the instrument and mean-independence given the
    design do not imply each other in either direction, so the claim has to
    say so rather than leave the resemblance to do the work.
    """
    claims = _ledger_claims(
        ("outcome_error_mean_independent_of_instrument_z_on_y",))
    assert len(claims) == 1
    claim = claims[0]["claim"]
    assert "z" in claim and "y" in claim
    assert "互不蕴含" in claim
    # And it is not the classical premise's words under a new id.
    classical = classify_assumption(
        "outcome_error_classical_non_differential_on_y")["claim"]
    assert claim != classical


def test_the_front_door_latent_premise_says_the_reader_cannot_check_it():
    """The premise that decides whether the POINT survives, about the
    confounder the front-door graph posits and nobody measured.

    ``testable`` false is the machine-readable half; the reader gets the
    other half only if the claim says why — "not yet checked" and "there is
    nothing in this data that could check it" are different instructions.
    """
    claims = _ledger_claims((
        "outcome_error_classical_non_differential_on_y",
        "outcome_error_independent_of_the_front_door_latent_confounder_on_y",
    ))
    latent = [c for c in claims if "front_door_latent" in c["id"]]
    assert len(latent) == 1
    assert latent[0]["testable"] is False
    assert "没法用数据检验" in latent[0]["claim"]
    assert "点估计本身" in latent[0]["claim"]


@pytest.mark.parametrize("premise", [
    "outcome_error_mean_independent_of_instrument_z_on_y",
    "outcome_error_independent_of_the_front_door_latent_confounder_on_y",
])
def test_neither_new_premise_reaches_the_ledger_as_its_own_identifier(premise):
    """The input the glossary has to say NO to: an unclassified id.

    An id nobody classified is surfaced with its raw English text, which is
    the right failure for a disclosure surface and the wrong thing for a
    Chinese report — and it is silent, so the only thing that catches it is
    asking.
    """
    entry = classify_assumption(premise)
    assert entry["claim"] != premise
    assert not entry["claim"].isascii()
    # Withdrawable by the caller, like every other premise on this channel:
    # the assessment runs only because they attached the measurement model.
    assert str(entry["provenance"]) == "caller_asserted"
