"""Every composite part of a numeric estimate says who tells the reader.

:mod:`themis.blocks` asks this of the ``extensions`` map, and its opening
paragraph says why the map is where it stops: an extensions key is a string
literal repeated at every writer and every reader, so a misspelling there is
silence, while the typed fields of a result cannot be misspelled at all.
That is a true statement about spelling. What happened next is that the
reader's question — which of a reader's questions does this answer, and how
does it get to them — was hung on the same registry, and so inherited a
denominator drawn for a different question entirely.

``numeric_estimate`` is one of those typed fields. Everything hanging off
it was therefore never asked who reads it, not because anyone judged that
it reached a reader but because it could not be misspelled. Measured, that
subtree declares twenty-eight composite parts, and nineteen of them were
read by no deterministic reader surface: not a stratum table, not an
over-identification test, not a confidence set with seven shapes, not a
four-way decomposition. Each is a section, not a digit of the number the
surfaces already print.

Asking produced two different answers, and the split is the useful part.
Six qualify the interval above them and became shared lines under every
headline. Ten say what the estimator did with the data — which is the
other half of the question the section titled "怎么算出来的" already asks,
and the half its binding could not reach, because that binding is over the
``extensions`` map and these are fields. One was neither: an ``inference``
block restating, from a third direction, two facts the envelope already
carried from the two the cluster audit is built on. It was deleted rather
than rendered; a part that reaches no reader is not always a part that
needs one.

So the question is asked here, of that container, one row per part. The
rows are not in :mod:`themis.blocks` because these names already exist in
exactly one place — the result schema — and a second Python declaration of
all twenty-eight would be the duplication that registry exists to prevent,
pointed the other way. The schema supplies the names; a row supplies only
the answer.

WHAT COUNTS AS READING IT. A renderer names the key as a quoted string or
reaches it as an attribute. Naming it in prose does not count, and that is
not pedantry: the first pass of this measurement, matching the bare word,
reported ``bootstrap`` as rendered because a docstring about edge stability
in the discovery layer says the word, and ``inference`` as rendered because
a comment says "an inference from residue". A guard that a writer's own
comment satisfies is the guard :mod:`themis.blocks` already had and had to
replace.

WHAT THIS DOES NOT CHECK. That the sentence a renderer produces is ABOUT
the part it read — no static check can. The pins below narrow that for the
parts this file was written around: each builds an envelope carrying one
part and asks the report for a phrase only a renderer reading that part
could produce.

The denominator is this container's OWN properties, one level deep. A
part of a part is not in it, and one of them turned out to reach nobody:
three of the composite parts below carry a ``reference``, the paper the
closed form comes from, and the renderers this file holds them to render
their numbers without it.
:mod:`tests.test_a_citation_is_not_a_field_of_one_container` is where
that is answered, and it answers it for the whole envelope because the
same field is written under ``extensions`` too.

Depth is where this container's line was drawn, and drawing a line one
level down from wherever the last one sat is what put four route blocks'
``numeric`` sub-objects outside every census there was.
:mod:`tests.test_no_part_of_a_block_is_silent` asks the question of
``extensions`` at every depth the schema declares, which is why the table
below is now keyed by an envelope PATH: the ten computation details are
properties of this container and four more are not, and a table keyed by
one container's property names cannot hold both.

Per-surface parity is checked for the computation details and not for the
rest. It is checkable there because both surfaces dispatch them from a
table, so the two tables can be held equal, in order, with no third list to
go stale. Elsewhere a row records which surfaces reach a part and an
asymmetry is visible in the table rather than caught by it — the same
standing gap ``RENDERED_BLOCKS`` and ``blocks.bind`` close for the
``extensions`` map from either end.
"""
from __future__ import annotations

import ast
import json
import pathlib
import re
from dataclasses import dataclass, field

import pytest

from themis import language
from themis.estimation.warning_words import FourWay

from . import web_source

REPO = pathlib.Path(__file__).resolve().parent.parent
SCHEMA = REPO / "themis" / "schemas" / "query_result.schema.json"
REPORT = REPO / "themis" / "output"
VERIFIER = REPO / "themis" / "verifier"


@dataclass(frozen=True)
class Part:
    """One composite part of ``numeric_estimate``, and who says it.

    ``rendered_by`` and ``consumed_by`` and ``unrendered`` are exclusive and
    one is required. ``unrendered`` is a claim rather than an exemption: it
    has to say what the reader gets instead, and the check below holds it to
    being true — a part that says nobody renders it and is then rendered
    fails here, the same way one that claims a renderer and has none does.
    """

    holds: str
    rendered_by: tuple[str, ...] = ()
    consumed_by: str = ""
    unrendered: str = ""


#: Where a renderer lives. ``module.name`` for the report, ``file:name`` for
#: the browser — the two spell their top-level declarations differently and
#: a single spelling would have to be translated at every row.
_REPORT_META = "analysis_report._estimate_meta"
_WEB_META = "verdict.ts:estimateMeta"
_WEB_ANSWER = "verdict.ts:answerRows"
#: The browser states the computation details as one keyed table, the way it
#: states routes and answers; the report states them as functions. Two
#: spellings of the same thing, because that is how each surface already
#: declares a dispatch. Both are keyed by envelope path, so the ten that are
#: properties of this container and the four that are not sit in one table.
_WEB_DETAIL = "verdict.ts:NUMERIC_DETAIL_RENDERERS"

PARTS: dict[str, Part] = {
    # --- the shared lines under every headline ------------------------------
    "anderson_rubin_confidence_set": Part(
        holds="the weak-identification-robust confidence set for the IV "
              "coefficient, in one of six shapes",
        rendered_by=(_REPORT_META, _WEB_META),
    ),
    "stratified_anderson_rubin_confidence_set": Part(
        holds="the same set inverted on the stratified Wald's own moment, "
              "which is a different estimand and never present beside it",
        rendered_by=(_REPORT_META, _WEB_META),
    ),
    "robust_anderson_rubin_confidence_set": Part(
        holds="the heteroskedasticity-robust set, the only one that can "
              "come back in more than two pieces",
        rendered_by=(_REPORT_META, _WEB_META),
    ),
    "over_identification": Part(
        holds="the Sargan / Hansen test of the instruments' joint validity",
        rendered_by=(_REPORT_META, _WEB_META),
    ),
    "stratum_support": Part(
        holds="the cells the adjustment set cuts the sample into and how "
              "many held both arms — overlap counted rather than fitted, and "
              "the evidence a ledger line's verdict on positivity is read "
              "off by the producer and by the verifier",
        rendered_by=(_REPORT_META, _WEB_META),
    ),
    "propensity_summary": Part(
        holds="the propensity range before Winsorizing and how many units "
              "were clipped — the overlap picture a MODEL gives of the same "
              "question the count above answers directly",
        rendered_by=(_REPORT_META, _WEB_META),
    ),
    "ovb_sensitivity": Part(
        holds="the Cinelli-Hazlett robustness value: how strong an "
              "unmeasured confounder would have to be",
        rendered_by=(_REPORT_META, _WEB_META),
    ),
    "sensitivity_analysis": Part(
        holds="the E-value, the same question on the risk-ratio scale",
        rendered_by=(_REPORT_META, "Verdict.tsx:Verdict"),
    ),
    "precision_budget": Part(
        holds="how much more N would halve the interval",
        rendered_by=(_REPORT_META, _WEB_META),
    ),

    # --- the headline itself, for the shapes that are not one number --------
    "decomposition": Part(
        holds="total, direct and indirect effect through one mediator",
        rendered_by=("analysis_report._render_mediation_decomposition",
                     _WEB_ANSWER),
    ),
    "dose_response_curve": Part(
        holds="the effect at each sampled dose against the reference",
        rendered_by=("analysis_report._render_dose_response_curve",
                     _WEB_ANSWER),
    ),
    "controlled_direct_effect": Part(
        holds="the direct effect at each level the mediator is held at, "
              "and whether it is the same at all of them",
        rendered_by=("analysis_report._render_controlled_direct_curve",
                     _WEB_ANSWER),
    ),
    "no_effect_test": Part(
        holds="whether there is an effect at all, when the channel would "
              "not invert and no size could be recovered",
        rendered_by=("analysis_report._render_no_effect_test", _WEB_ANSWER),
    ),
    "joint_effect": Part(
        holds="the contrast between two joint corners",
        rendered_by=("analysis_report._render_joint_contrast", _WEB_ANSWER),
    ),
    "interaction": Part(
        holds="what riding together adds over the sum of the singles",
        rendered_by=("analysis_report._render_joint_contrast", _WEB_ANSWER),
    ),
    "interaction_unavailable": Part(
        holds="why the interaction could not be formed",
        rendered_by=("analysis_report._render_joint_contrast",),
    ),
    "probabilities_of_causation": Part(
        holds="PN, PS and PNS — three quantities under one question",
        rendered_by=("analysis_report._render_causation_estimate",
                     _WEB_ANSWER),
    ),
    "counterfactual_cell": Part(
        holds="one counterfactual cell, as a point or as bounds",
        rendered_by=("analysis_report._render_counterfactual_cell_bounds",
                     _WEB_ANSWER),
    ),

    # --- how the number was computed, in the section that asks -------------
    #
    # These say what the estimator did with the data, which is the other half
    # of "怎么算出来的" — the half that section's binding could not reach,
    # because it is bound to ``extensions`` and these are fields.
    "acr_decomposition": Part(
        holds="which steps of an ordered dose the IV number averages over, with what weight, and whether a negative one refutes monotonicity",
        rendered_by=("analysis_report._detail_acr", _WEB_DETAIL),
    ),
    "stratified_wald": Part(
        holds="the per-stratum table the ratio of averages was aggregated "
              "from",
        rendered_by=("analysis_report._detail_stratified_wald", _WEB_DETAIL),
    ),
    "recovered_ate": Part(
        holds="the back-door ATE recovered from data with missing values, "
              "beside the listwise-deletion estimate it corrects",
        rendered_by=("analysis_report._detail_recovered_ate", _WEB_DETAIL),
    ),
    "selection_recovery_numeric": Part(
        holds="the detail behind an ATE recovered from selection bias",
        rendered_by=("analysis_report._detail_selection_recovery_numeric",
                     _WEB_DETAIL),
    ),
    "measurement_correction": Part(
        holds="the misclassification-matrix inversion behind a corrected "
              "estimate",
        rendered_by=("analysis_report._detail_measurement_correction",
                     _WEB_DETAIL),
    ),
    "regression_calibration": Part(
        holds="the continuous-exposure analogue of that correction",
        rendered_by=("analysis_report._detail_regression_calibration",
                     _WEB_DETAIL),
    ),
    "differential_error": Part(
        holds="the same correction with its non-differential premise "
              "withdrawn — the covariance the error inflated, taken off "
              "before anything is de-attenuated",
        rendered_by=("analysis_report._detail_differential_error",
                     _WEB_DETAIL),
    ),
    "differential_outcome_error": Part(
        holds="the same premise withdrawn on the other channel — an outcome "
              "error that tracks the exposure, and the δ the back-door slope "
              "has to give back",
        rendered_by=("analysis_report._detail_differential_outcome_error",
                     _WEB_DETAIL),
    ),
    "simex": Part(
        holds="the simulation ladder the same correction is extrapolated "
              "back along when the coefficient lives in a nonlinear model",
        rendered_by=("analysis_report._detail_simex", _WEB_DETAIL),
    ),
    "longitudinal_gformula": Part(
        holds="the time-ordered treatment strategy contrast by g-computation",
        rendered_by=("analysis_report._detail_longitudinal_gformula",
                     _WEB_DETAIL),
    ),
    "longitudinal_ipw_msm": Part(
        holds="the same strategy contrast by a marginal structural model",
        rendered_by=("analysis_report._detail_longitudinal_ipw_msm",
                     _WEB_DETAIL),
    ),
    "four_way_decomposition": Part(
        holds="VanderWeele's split of the total effect into mediation, "
              "interaction, both and neither",
        rendered_by=("analysis_report._detail_four_way_decomposition",
                     _WEB_DETAIL),
    ),
    "four_way_ratio": Part(
        holds="the same decomposition on the excess-relative-risk scale",
        rendered_by=("analysis_report._detail_four_way_ratio", _WEB_DETAIL),
    ),
    "four_way_unavailable": Part(
        holds="why the difference-scale four-way was not valid here",
        rendered_by=("analysis_report._detail_four_way_unavailable",
                     _WEB_DETAIL),
    ),

    # --- not for a reader ---------------------------------------------------
    "node_fits": Part(
        holds="the per-node fitted structural equations and their OLS "
              "moment matrices",
        consumed_by="themis.verifier.verify",
    ),
    "bootstrap": Part(
        holds="that the interval resampled whole clusters, and which column "
              "it clustered on",
        # Written by the dispatch layer as an assertion, and read as one: the
        # cluster audit holds it against what the run resolved and against
        # what the estimator declared, so a claim of cluster-robustness with
        # no run-level basis is rejected rather than believed. The reader
        # gets the fact from the estimator's own declaration, which the
        # assumption ledger states in words. This row said nobody read it,
        # which was wrong in the direction the check below cannot see:
        # ``consumed_by`` is verified, ``unrendered`` only against surfaces.
        consumed_by="themis.verifier.cluster_inference_rules",
    ),
    "front_door_empirical": Part(
        holds="the two standardized arms a front door taken over the arms' "
              "own rows is a difference of, and the fit behind them",
        # The reader is given the point and, in the ledger, the one premise
        # this road adds. These are what make the point checkable: the
        # difference identity on either outcome form, and on the linear one
        # the product rule — coefficients dotted with the mediator shift —
        # which is a re-derivation and not a re-reading.
        consumed_by="themis.verifier.verify",
    ),
    "corner_risks": Part(
        holds="the interventional risk at each corner of the treatment box "
              "the two reported numbers were formed from",
        # The contrast is a difference of two of these and the K-way
        # interaction an alternating sum over all of them, so the audit
        # re-derives both rather than re-reading them. The reader is given
        # the two answers; the box is what makes them checkable, the same
        # way an over-identification test's sufficient statistics are.
        consumed_by="themis.verifier.verify",
    ),
}


# --------------------------------------------------------------- the schema
def _numeric_estimate() -> dict:
    doc = json.loads(SCHEMA.read_text(encoding="utf-8"))
    return doc["properties"]["numeric_estimate"], doc.get("$defs", {})


def _composite(spec: dict, defs: dict) -> bool:
    """A part with an inside — a section rather than a digit.

    Scalars under ``numeric_estimate`` are the number the surfaces already
    print, or a label on it. What needs asking about is anything with fields
    of its own, including an array of them.
    """
    if "$ref" in spec:
        spec = defs.get(spec["$ref"].rsplit("/", 1)[-1], {})
    if spec.get("type") == "object" or "properties" in spec:
        return True
    items = spec.get("items")
    return spec.get("type") == "array" and isinstance(items, dict) and (
        items.get("type") == "object" or "properties" in items)


def _declared() -> set[str]:
    ne, defs = _numeric_estimate()
    return {name for name, spec in ne["properties"].items()
            if _composite(spec, defs)}


# ------------------------------------------------------------- the surfaces
def _reads(name: str) -> re.Pattern:
    """The key as a key: quoted, reached as an attribute, or an object key."""
    n = re.escape(name)
    return re.compile(rf"""["']{n}["']|\.{n}\b|(?<![\w.]){n}\?*\s*:""")


def _chunks() -> dict[str, str]:
    """Every top-level declaration of every reader surface, by name.

    Top level rather than whole file, because "some module mentions it" is
    the check this replaces. A table declared at module level counts the
    same as a function: the reader's word can live in either.
    """
    out: dict[str, str] = {}
    for path in sorted(REPORT.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines(keepends=True)
        for node in ast.parse(source).body:
            text = "".join(lines[node.lineno - 1:node.end_lineno])
            names = []
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
                names = [node.name]
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target,
                                                                ast.Name):
                names = [node.target.id]
            elif isinstance(node, ast.Assign):
                names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            for name in names:
                out[f"{path.stem}.{name}"] = text
    for path in (sorted(web_source.SRC.rglob("*.ts"))
                 + sorted(web_source.SRC.rglob("*.tsx"))):
        if path.name == "types.ts" or "node_modules" in path.parts:
            continue
        for name, text in web_source.chunks(
                path.read_text(encoding="utf-8")).items():
            out[f"{path.name}:{name}"] = text
    return out


def _verifier_sources() -> dict[str, str]:
    return {f"themis.verifier.{p.stem}": p.read_text(encoding="utf-8")
            for p in sorted(VERIFIER.rglob("*.py"))}


CHUNKS = _chunks()


# ----------------------------------------------------------------- the gate
def test_every_composite_part_has_exactly_one_row():
    """The schema decides the denominator, not the table.

    A part added to ``numeric_estimate`` with fields of its own is a section
    somebody has to answer for, and it enters here the moment the schema
    declares it.
    """
    declared, rows = _declared(), set(PARTS)
    assert not declared - rows, (
        f"numeric_estimate declares composite part(s) no row answers for: "
        f"{sorted(declared - rows)}"
    )
    assert not rows - declared, (
        f"row(s) for parts the schema does not declare: {sorted(rows - declared)}"
    )


def test_the_schema_still_has_parts_to_ask_about():
    """A walk that finds nothing satisfies the check above in silence."""
    assert len(_declared()) > 20, len(_declared())


@pytest.mark.parametrize("name", sorted(PARTS))
def test_every_row_says_exactly_one_thing(name):
    """Rendered, consumed elsewhere, or read by nobody — and only one.

    Two answers is a row that has not decided; none is a part that arrives
    at every surface and produces nothing, which is the silence this module
    exists to make impossible to add.
    """
    row = PARTS[name]
    said = [bool(row.rendered_by), bool(row.consumed_by), bool(row.unrendered)]
    assert sum(said) == 1, (
        f"{name}: says {sum(said)} of rendered_by / consumed_by / unrendered"
    )
    assert row.holds, f"{name}: no row says what a writer puts in it"


@pytest.mark.parametrize("name", sorted(
    n for n, r in PARTS.items() if r.rendered_by))
def test_a_claimed_renderer_reads_the_part(name):
    """Named, and reading it as a key rather than saying the word."""
    pattern = _reads(name)
    for where in PARTS[name].rendered_by:
        assert where in CHUNKS, (
            f"{name}: no surface declares {where!r}; the renderer was "
            f"renamed or removed and the row still claims it"
        )
        assert pattern.search(CHUNKS[where]), (
            f"{name}: {where} does not read it — a row may not claim a "
            f"renderer that only mentions the name"
        )


@pytest.mark.parametrize("name", sorted(
    n for n, r in PARTS.items() if r.consumed_by))
def test_a_claimed_consumer_reads_the_part(name):
    """Not for a reader is a claim about who it IS for, and that is checkable."""
    sources = _verifier_sources()
    where = PARTS[name].consumed_by
    assert where in sources, f"{name}: no module {where!r}"
    assert _reads(name).search(sources[where]), (
        f"{name}: {where} does not read it, so the row names a consumer "
        f"that does not consume it"
    )


#: One envelope per newly rendered part, and the phrase a reader must find.
#: The rows above check that a renderer reads the key; these check that
#: reading it produces a sentence. A renderer can read a key and print
#: nothing, and that is exactly what a static check cannot see.
_SAYS: tuple[tuple[str, dict, tuple[str, ...], tuple[str, ...]], ...] = (
    (
        "an unbounded AR set is the finding, not a wide interval",
        {"anderson_rubin_confidence_set": {
            "kind": "unbounded_above", "lower": 0.4, "upper": None,
            "ci_level": 0.95, "point": 1.2}},
        ("弱工具稳健区间", "+∞", "工具太弱"),
        ("unbounded_above",),
    ),
    (
        "an empty AR set says the data refute the instruments",
        {"robust_anderson_rubin_confidence_set": {
            "kind": "empty", "segments": [], "ci_level": 0.95}},
        ("∅", "否定这组工具"),
        ("empty",),
    ),
    (
        "a rejected over-identification test is not left as a p-value",
        {"over_identification": {"sargan_j": 12.0, "sargan_dof": 2,
                                 "sargan_p_value": 0.0025}},
        ("工具联合有效性", "Sargan", "排除限制不成立"),
        (),
    ),
    (
        "trimming says what thin overlap costs the reader",
        {"propensity_summary": {"raw_min": 0.002, "raw_max": 0.997,
                                "n_trimmed": 41, "floor": 0.01,
                                "model": "logistic"}},
        ("重叠", "41", "外推"),
        (),
    ),
    (
        "the robustness value is stated as a quantity of confounding",
        {"ovb_sensitivity": {"robustness_value_q": 0.13,
                             "robustness_value_qa": 0.07, "alpha": 0.05}},
        ("未测混杂", "13.0%", "抹平"),
        (),
    ),
)


@pytest.mark.parametrize(
    "why,block,expected,forbidden", _SAYS,
    ids=[case[0] for case in _SAYS])
def test_the_reader_gets_a_sentence_and_not_the_identifier(
        why, block, expected, forbidden):
    """What the reader actually reads, for the parts this item rendered."""
    from themis.output import analysis_report

    numeric = {"point": 1.2, "ci_lower": 0.3, "ci_upper": 2.1,
               "ci_level": 0.95, "method": "iv_wald", "sample_size": 1500}
    numeric.update(block)
    text = analysis_report.build_analysis_report(
        {"status": "numerically_solved", "query_id": "q",
         "query_kind": "effect", "numeric_estimate": numeric})
    for phrase in expected:
        assert phrase in text, f"{why}: the report never says {phrase!r}"
    for token in forbidden:
        assert token not in text, (
            f"{why}: the report prints the identifier {token!r} at the reader"
        )


def test_the_robust_set_is_the_one_reported_when_both_are_there():
    """Two sets, one line, and which one is not a matter of order.

    The heteroskedasticity-robust set is valid under weak identification AND
    heteroskedasticity; the homoskedastic one beside it is the same set
    computed under an assumption the data may not support. Reporting the
    latter because it is checked first would hand the reader the narrower
    interval on the stronger premise, which is the direction of error this
    whole family of blocks exists to prevent.
    """
    from themis.output import analysis_report

    text = analysis_report.build_analysis_report({
        "status": "numerically_solved", "query_id": "q",
        "query_kind": "effect",
        "numeric_estimate": {
            "point": 1.2, "method": "iv_2sls_overid", "sample_size": 2000,
            "anderson_rubin_confidence_set": {
                "kind": "bounded", "lower": 0.9, "upper": 1.5,
                "ci_level": 0.95},
            "robust_anderson_rubin_confidence_set": {
                "kind": "whole_line", "segments": [], "ci_level": 0.95},
        },
    })
    assert "整条实轴" in text, "the homoskedastic set won the ?? chain"
    assert "[0.9" not in text


def test_both_surfaces_dispatch_the_same_details_in_the_same_order():
    """The parity check that is available here and nowhere else in this file.

    Both surfaces state the computation details from a table, so the tables
    can be held equal without writing a third list of the names to hold them
    against. Order as well as membership: a reader comparing the report and
    the browser on one envelope is reading one argument, and two orders make
    that a reconciliation.
    """
    from themis.output import analysis_report

    report = [name for name, _ in analysis_report._NUMERIC_DETAIL_RENDERERS]
    source = web_source.read(web_source.VERDICT)
    browser = re.findall(
        r"'([^']+)'", web_source.literal("NUMERIC_DETAIL_ORDER", source))
    assert report == browser, (
        f"the two surfaces disagree about which computation details to state, "
        f"or in what order: report={report} browser={browser}"
    )
    bound = web_source.top_level_keys(
        web_source.literal("NUMERIC_DETAIL_RENDERERS", source))
    assert bound == set(report), (
        f"the browser's detail order and its renderers disagree: "
        f"order-only={sorted(set(report) - bound)}, "
        f"renderer-only={sorted(bound - set(report))}"
    )


#: One envelope per computation detail, and what a reader must find in the
#: report. The rows check that a renderer reads the key; these check that
#: reading it produces the sentence the row promised — the stratum, the
#: uncorrected number, the route that was not run.
_DETAIL_SAYS: tuple[
    tuple[str, str, dict, tuple[str, ...], tuple[str, ...]], ...] = (
    (
        "a stratum table says which cell carries what weight",
        "iv_stratified_wald",
        {"stratified_wald": {
            "conditioning_order": ["age"],
            "outcome_shift": 0.24, "treatment_shift": 0.4,
            "strata": [{"values": ["old"], "weight": 0.6, "n_obs": 600,
                        "n_instrument_high": 300, "n_instrument_low": 300,
                        "outcome_shift": 0.3, "treatment_shift": 0.5}],
        }},
        ("分层 Wald 的逐格明细", "age=old", "不是各格比值的平均"),
        # Not ``stratified_wald`` — the method line legitimately prints
        # ``iv_stratified_wald``, and a forbidden token that the estimator's
        # own name contains would fail for the wrong reason.
        ("conditioning_order", "n_instrument_high"),
    ),
    (
        "the listwise number the recovery corrects is shown beside it",
        "missing_data_recovery_gformula",
        {"recovered_ate": {
            "point": 0.42, "naive_listwise_ate": 0.91,
            "adjustment": ["z"], "n_total": 1000, "n_complete_case": 410,
            "n_conditional_rows": 830, "n_marginal_rows": 950,
            "n_strata": 4, "missing_columns": ["z"], "n_bootstrap": 200,
        }},
        ("列表删除法", "0.91", "全部的作用"),
        ("naive_listwise_ate",),
    ),
    (
        "a recovery from selection bias names the external sample it leans on",
        "selection_backdoor_recovery",
        {"selection_recovery_numeric": {
            "reference_sample_size": 2200, "reference_data_hash": "h",
            "z_plus": ["z1"], "z_minus": ["z2"],
            "selected_values": {"s": 1},
            "mu_treated": 0.7, "mu_control": 0.3,
        }},
        # Not "Z⁻ is the half that needs the external sample": which half
        # does is not a property of the half. The criterion asks it of Z as a
        # whole, and answers with Z⁺'s marginal when Z⁻ is empty — the exact
        # opposite of what this pin used to hold the renderer to.
        ("外部参照样本", "挡后门路径的是它", "挡不了后门",
         "代表未被筛过的人群"),
        ("z_minus",),
    ),
    (
        "a misclassification correction says how far it moved the number",
        "measurement_error_correction",
        {"measurement_correction": {
            "side": "exposure", "naive_point": 0.2, "det": 0.04,
            "out_of_simplex": True, "differential": False,
            "states": [0, 1], "target_value": 1,
            "sufficient_statistics": {},
        }},
        ("暴露被误分类", "校正把这个数挪了", "概率单纯形之外"),
        ("out_of_simplex",),
    ),
    (
        "regression calibration states the reliability the correction divides by",
        "regression_calibration",
        {"regression_calibration": {
            "naive_point": 0.3, "reliability": 0.6, "error_variance": 0.4,
            "error_variances": {"w": 0.4}, "exposure": "w",
            "design_vars": ["w", "z"], "sufficient_statistics": {},
        }},
        ("可靠度 λ", "把衰减除回去", "不是从数据里估的"),
        (),
    ),
    (
        "the differential correction names both steps, because the "
        "reliability alone no longer reproduces the answer",
        "differential_regression_calibration",
        {"differential_error": {
            "naive_point": 0.6, "exposure": "w", "differential_by": "y",
            "differential_coefficient": 0.3, "error_variance": 0.64,
            "nondifferential_variance": 0.5,
            "outcome_tracking_covariance": 0.49,
            "exposure_variance": 1.0, "reliability": 0.47,
            "design_vars": ["w", "z"], "sufficient_statistics": {},
        }},
        ("是误差而不是效应", "未校正的数除以 λ", "只能从外部来"),
        (),
    ),
    (
        "simex shows the ladder the answer was read off the end of",
        "simex",
        {"simex": {
            "naive_point": 0.55, "outcome_model": "logistic",
            "extrapolant": "rational", "error_variance": 0.5, "exposure": "w",
            "n_replicates": 100, "random_state": 42,
            "grid": [
                {"lambda": 0.0, "theta": 0.55, "replicate_variance": 0.0,
                 "variance_mean": 0.004, "replicates": 1},
                {"lambda": 1.0, "theta": 0.44, "replicate_variance": 0.001,
                 "variance_mean": 0.004, "replicates": 100},
                {"lambda": 2.0, "theta": 0.37, "replicate_variance": 0.002,
                 "variance_mean": 0.005, "replicates": 100},
            ],
            "coefficients": [0.1, 0.6, 1.2],
            "variance_coefficients": [0.001, 0.002, 1.5],
            "extrapolated_variance": None,
            "no_interval_because": "extrapolated_variance_is_not_positive",
            "cluster": None,
        }},
        ("模拟外推", "λ=0 那一档不是模拟", "没有可报的宽度"),
        (),
    ),
    (
        "the g-formula route names the route that was not run beside it",
        "longitudinal_gformula",
        {"longitudinal_gformula": {
            "point": 0.5, "treatments": ["a1", "a2"],
            "confounders_by_time": [["l1"], ["l2"]], "outcome": "y",
            "strategy_treated": 1, "strategy_control": 0,
            "e_y_treated": 0.8, "e_y_control": 0.3,
            "n_sim": 5000, "n_bootstrap": 200,
        }},
        ("纵向 g-公式", "第 2 时点调整", "一致与否本身就是一个发现"),
        ("longitudinal_ipw_msm",),
    ),
    (
        "the MSM route says when a few subjects carry the estimate",
        "longitudinal_ipw_msm",
        {"longitudinal_ipw_msm": {
            "point": 0.5, "treatments": ["a1"], "confounders_by_time": [["l1"]],
            "outcome": "y", "strategy_treated": 1, "strategy_control": 0,
            "e_y_treated": 0.8, "e_y_control": 0.3, "stabilized": True,
            "msm_coefficients": [0.1, 0.5], "weight_mean": 1.02,
            "weight_max": 38.0, "n_bootstrap": 200,
        }},
        ("纵向 IPW 边缘结构模型", "稳定化权重", "少数个体在主导这个数"),
        ("msm_coefficients",),
    ),
    (
        "the four-way split names its four parts rather than four acronyms",
        "mediation_linear_imai",
        {"decomposition": {"te": {"point": 1.0}},
         "four_way_decomposition": {
             "cde": {"point": 0.4}, "intref": {"point": 0.1},
             "intmed": {"point": 0.2}, "pie": {"point": 0.3},
             "te": {"point": 1.0}, "prop_mediated": {"point": 0.5},
             "prop_interaction": {"point": 0.3},
             "additive_interaction": 0.15, "scale": "difference",
         }},
        ("纯直接（CDE）", "既靠交互，又靠处理确实改变了中介",
         "交互那部分改中介去不掉"),
        ("intref", "intmed"),
    ),
    (
        "the ratio-scale split says which closed form produced it",
        "mediation_logit_imai",
        {"decomposition": {"te": {"point": 1.0}},
         "four_way_ratio": {
             "mediator_scale": "binary",
             "err_cde": {"point": 0.4}, "err_intref": {"point": 0.1},
             "err_intmed": {"point": 0.2}, "err_pie": {"point": 0.3},
             "total_err": {"point": 1.0}, "total_rr": {"point": 2.0},
             "prop_mediated": {"point": 0.5},
             "prop_interaction": {"point": 0.3},
             "prop_eliminated": {"point": 0.4},
             "coefficients": {},
         }},
        ("超额相对风险", "eAppendix §3.4", "把中介固定住能消掉的比例"),
        ("mediator_scale",),
    ),
    (
        "a withheld four-way says it was attempted",
        "mediation_linear_imai",
        {"decomposition": {"te": {"point": 1.0}},
         # The reason is a STATEMENT — the block beside it says what the
         # split IS, so what it is NOT belongs in the same shape rather
         # than in a string each branch is the author of.
         "four_way_unavailable": {"reason": language.state(
             FourWay.THE_MEDIATOR_IS_CONTINUOUS_UNDER_A_NONLINEAR_OUTCOME)}},
        ("四分解没有给出", "不是没算", "外推到中介取值范围之外"),
        ("four_way_unavailable",),
    ),
)


@pytest.mark.parametrize(
    "why,method,block,expected,forbidden", _DETAIL_SAYS,
    ids=[case[0] for case in _DETAIL_SAYS])
def test_the_computation_detail_reaches_the_reader_as_a_sentence(
        why, method, block, expected, forbidden):
    """What the reader actually reads, for each detail this item rendered."""
    from themis.output import analysis_report

    numeric = {"point": 0.5, "ci_lower": 0.2, "ci_upper": 0.8,
               "ci_level": 0.95, "method": method, "sample_size": 1000}
    numeric.update(block)
    text = analysis_report.build_analysis_report(
        {"status": "numerically_solved", "query_id": "q",
         "query_kind": "effect", "numeric_estimate": numeric})
    assert "## 怎么算出来的" in text, (
        f"{why}: the detail did not land in the section that asks for it"
    )
    for phrase in expected:
        assert phrase in text, f"{why}: the report never says {phrase!r}"
    for token in forbidden:
        assert token not in text, (
            f"{why}: the report prints the identifier {token!r} at the reader"
        )


@pytest.mark.parametrize("name", sorted(
    n for n, r in PARTS.items() if r.unrendered))
def test_a_part_said_to_reach_nobody_reaches_nobody(name):
    """The claim, checked in the direction that can go stale.

    A row saying no surface renders this is exactly as much of a fact as one
    naming a renderer, and it goes wrong the same way: somebody renders it
    and the table still says nobody does. The reader is then told less than
    the code says — which is the failure this whole item is about, pointed
    the other way.

    No row says it today, so this collects empty and reports as one skip.
    That is the state of the container rather than a gap in the check: the
    answer stays legal, it is documented on :class:`Part`, and the moment a
    row uses it this runs against it.
    """
    pattern = _reads(name)
    found = sorted(where for where, text in CHUNKS.items()
                   if pattern.search(text))
    assert not found, (
        f"{name} says nobody renders it, but {found} read it; the row is "
        f"stale and should name them"
    )
