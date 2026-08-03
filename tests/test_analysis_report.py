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
from themis import refusals
from themis.output.analysis_report import (
    _KIND_ZH,
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


def test_verify_stamp_reflects_passed_verdict(numeric_env):
    prog, env = numeric_env
    res = env["results"][0]
    # a genuine verify verdict, passed in by the caller (report never verifies)
    try:
        themis.verify(env.get("program", prog), res)
        verdict = True
    except Exception:
        verdict = False
    assert verdict is True
    md = build_analysis_report(res, program=prog, verified=True)
    assert "已独立复核通过" in md


def test_verify_stamp_reflects_failed_verdict(numeric_env):
    prog, env = numeric_env
    md = build_analysis_report(env["results"][0], program=prog, verified=False)
    assert "复核未通过" in md


def test_no_stamp_without_verdict_but_derivation_noted(numeric_env):
    prog, env = numeric_env
    md = build_analysis_report(env["results"][0], program=prog, verified=None)
    assert "已独立复核通过" not in md
    assert "复核未通过" not in md
    assert "可独立复核的推导链" in md
    assert "themis.verify" in md


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
        "bounds_result": {"lower_value": -0.19, "upper_value": 0.01, "method": "balke_pearl_iv"},
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
    defect above returning under a new name."""
    assert set(_KIND_ZH) == set(refusals.KINDS)


@pytest.mark.parametrize("kind", sorted(refusals.KINDS))
def test_each_kind_reads_as_something_different(kind):
    answer = _render_answer({
        "status": "needs_investigation", "query_kind": "effect", "query_id": "r",
        "estimator_failure": {
            "estimator": "e", "failure_type": "not_identified",
            "reason": "why it stopped", "kind": kind,
        },
    })
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
    answer = _render_answer(res)
    assert "0.31" in answer
    assert "没有给出数值" not in answer
