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
the part it read — no static check can — and that both surfaces render it
rather than one. Per-surface parity for the ``extensions`` map is what
``RENDERED_BLOCKS`` and ``blocks.bind`` hold from either end; for this
container the rows record which surfaces reach it, so an asymmetry is
visible in the table, and closing one is its own item.
"""
from __future__ import annotations

import ast
import json
import pathlib
import re
from dataclasses import dataclass, field

import pytest

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
    "propensity_summary": Part(
        holds="the propensity range before Winsorizing and how many units "
              "were clipped — the overlap picture",
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

    # --- not for a reader ---------------------------------------------------
    "node_fits": Part(
        holds="the per-node fitted structural equations and their OLS "
              "moment matrices",
        consumed_by="themis.verifier.verify",
    ),

    # --- read by nobody, and what the reader gets instead --------------------
    #
    # Each of these is a section the reader does not get. The claim in each
    # row is only that the number the part stands behind does reach them;
    # what is lost is named, so the row can be argued with. Registered as
    # one follow-up rather than nine.
    "stratified_wald": Part(
        holds="the per-stratum table the ratio of averages was aggregated "
              "from",
        unrendered="The reader gets the aggregate and, from the stratified "
                   "AR set, the number of strata. Which cell is pulling the "
                   "ratio is not shown.",
    ),
    "measurement_correction": Part(
        holds="the misclassification-matrix inversion behind a corrected "
              "estimate",
        unrendered="The reader gets the corrected point and the ledger line "
                   "saying a declared matrix corrected it. How far the "
                   "correction moved the number is not shown.",
    ),
    "regression_calibration": Part(
        holds="the continuous-exposure analogue of that correction",
        unrendered="As its discrete twin: the corrected point reaches the "
                   "reader, the size of the correction does not.",
    ),
    "selection_recovery_numeric": Part(
        holds="the detail behind an ATE recovered from selection bias",
        unrendered="The recovered ATE is the headline. Which selection "
                   "values it conditioned on, and against which reference "
                   "sample, are not shown.",
    ),
    "recovered_ate": Part(
        holds="the back-door ATE recovered from data with missing values, "
              "beside the listwise-deletion estimate it corrects",
        unrendered="The recovered point is the headline. "
                   "`naive_listwise_ate` — the biased number a reader would "
                   "otherwise have computed, which is the whole argument for "
                   "the method — is not shown.",
    ),
    "bootstrap": Part(
        holds="the resampling that produced the interval",
        unrendered="The interval it produced IS the headline CI, and the "
                   "precision line is about it. The replicate count and "
                   "scheme are not shown.",
    ),
    "inference": Part(
        holds="which inferential scheme the interval came from — "
              "cluster-robust and its variants",
        unrendered="The interval reaches the reader; what kind of interval "
                   "it is does not, on any surface, and no verifier rule "
                   "reads it either. Of everything in this table it is the "
                   "one with no reader at all.",
    ),
    "longitudinal_gformula": Part(
        holds="the time-ordered treatment strategy contrast by g-computation",
        unrendered="The point and interval are the headline. The strategies "
                   "being contrasted, and the confounders at each time, are "
                   "not shown.",
    ),
    "longitudinal_ipw_msm": Part(
        holds="the same strategy contrast by a marginal structural model",
        unrendered="As its twin — and the fact that the two are INDEPENDENT "
                   "routes to one contrast, so that agreeing or disagreeing "
                   "is itself a finding, reaches nobody.",
    ),
    "four_way_decomposition": Part(
        holds="VanderWeele's split of the total effect into mediation, "
              "interaction, both and neither",
        unrendered="Nothing of it reaches the reader; the total effect "
                   "does.",
    ),
    "four_way_ratio": Part(
        holds="the same decomposition on the excess-relative-risk scale",
        unrendered="As its difference-scale twin.",
    ),
    "four_way_unavailable": Part(
        holds="why the difference-scale four-way was not valid here",
        unrendered="The reader sees no four-way decomposition and is not "
                   "told that one was attempted, nor why it was withheld.",
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


@pytest.mark.parametrize("name", sorted(
    n for n, r in PARTS.items() if r.unrendered))
def test_a_part_said_to_reach_nobody_reaches_nobody(name):
    """The claim, checked in the direction that can go stale.

    A row saying no surface renders this is exactly as much of a fact as one
    naming a renderer, and it goes wrong the same way: somebody renders it
    and the table still says nobody does. The reader is then told less than
    the code says — which is the failure this whole item is about, pointed
    the other way.
    """
    pattern = _reads(name)
    found = sorted(where for where, text in CHUNKS.items()
                   if pattern.search(text))
    assert not found, (
        f"{name} says nobody renders it, but {found} read it; the row is "
        f"stale and should name them"
    )
