"""Tests for the measurement_error_concern gap_kind.

Triggered by program-shape: at least one variable on the identification
path (intervention, target, or directed predecessor of either) declares
a ``measurement`` or ``observability`` field whose value names a
documented noisy-measurement pattern (self-report / questionnaire /
24h recall / single-occasion / proxy / FFQ).

Authoritative trigger references — MacMahon 1990 *Lancet* 335:765
(regression dilution from single-occasion BP) + Hernán & Robins
*What If* §9 (non-differential mis-classification of self-reported
exposure) + Fuller 1987 *Measurement Error Models* (attenuation).

Key invariants pinned here:
- fires when intervention.measurement contains a pattern
- fires when a confounder.measurement contains a pattern
- fires on observability field (parallel field with same semantics)
- suppressed when extensions.ambiguities[*].kind == "measurement_quality"
  (case 011 escape-hatch; LLM already declared it)
- suppressed on cause / probability / counterfactual queries (the
  bias story is about effect-on-Y from X)
- suppressed when query unidentifiable (don't pile caveats on already-
  failing branches)
- non-trigger words (free description text without the listed patterns)
  do NOT fire
- variable not on identification path is ignored (e.g. unrelated
  declared variable)
"""
from themis import run
from tests import caveats


def _make_program(
    *,
    intervention_measurement=None,
    intervention_observability=None,
    confounder_measurement=None,
    extensions=None,
    query_kind="effect",
):
    """Minimal X→Y + Z→X + Z→Y backdoor program; can attach measurement
    metadata to either X or Z and override the query kind."""
    statements = [
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "y", "domain": [True, False]},
        {"kind": "variable", "predicate": "z", "domain": [True, False]},
    ]
    if intervention_measurement is not None:
        statements[0]["measurement"] = intervention_measurement
    if intervention_observability is not None:
        statements[0]["observability"] = intervention_observability
    if confounder_measurement is not None:
        statements[2]["measurement"] = confounder_measurement
    statements.extend([
        {"kind": "cause",
         "from": {"predicate": "x", "args": [{"type": "const", "name": "p"}]},
         "to":   {"predicate": "y", "args": [{"type": "const", "name": "p"}]}},
        {"kind": "cause",
         "from": {"predicate": "z", "args": [{"type": "const", "name": "p"}]},
         "to":   {"predicate": "x", "args": [{"type": "const", "name": "p"}]}},
        {"kind": "cause",
         "from": {"predicate": "z", "args": [{"type": "const", "name": "p"}]},
         "to":   {"predicate": "y", "args": [{"type": "const", "name": "p"}]}},
    ])
    if query_kind == "effect":
        query_body = {
            "kind": "effect",
            "target": {
                "atom": {"predicate": "y",
                         "args": [{"type": "const", "name": "p"}]},
                "value": True,
            },
            "intervention": {
                "atom": {"predicate": "x",
                         "args": [{"type": "const", "name": "p"}]},
                "value": True,
            },
            "given": [],
        }
    elif query_kind == "cause":
        query_body = {
            "kind": "cause",
            "from": {"predicate": "x",
                     "args": [{"type": "const", "name": "p"}]},
            "to": {"predicate": "y",
                   "args": [{"type": "const", "name": "p"}]},
        }
    else:
        raise ValueError(query_kind)
    statements.append({"kind": "query", "id": "q", "query": query_body})
    program: dict = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "p"}]},
        "statements": statements,
    }
    if extensions is not None:
        program["extensions"] = extensions
    return program


def _gap_kinds(out):
    result = out["results"][0]
    report = result.get("data_gap_report") or {}
    return [g["kind"] for g in report.get("gaps", [])]


def _gap_by_kind(out, kind):
    result = out["results"][0]
    report = result.get("data_gap_report") or {}
    for g in report.get("gaps", []):
        if g["kind"] == kind:
            return g
    return None


def test_fires_when_intervention_measurement_contains_self_report():
    """Hernán & Robins What If §9 canonical case — exposure is
    self-reported."""
    out = run(_make_program(
        intervention_measurement="self-reported smoking via questionnaire",
    ))
    assert "measurement_error_concern" in _gap_kinds(out)


def test_fires_when_intervention_measurement_contains_single_occasion():
    """MacMahon 1990 Lancet canonical case — single-occasion BP."""
    out = run(_make_program(
        intervention_measurement=(
            "single-occasion office sphygmomanometer reading"
        ),
    ))
    assert "measurement_error_concern" in _gap_kinds(out)


def test_fires_when_observability_field_carries_pattern():
    """Same semantics on the observability field — structural placement
    parallels measurement so both should be read."""
    out = run(_make_program(
        intervention_observability=(
            "self-reported via FFQ; gold standard would be 24h urinary"
        ),
    ))
    assert "measurement_error_concern" in _gap_kinds(out)


def test_fires_when_confounder_measurement_contains_pattern():
    """A noisy confounder measurement also biases backdoor adjustment.
    Classifier walks ancestors of {intervention, target}, so a confounder
    Z with self-reported measurement triggers."""
    out = run(_make_program(
        confounder_measurement="self-reported by recall questionnaire",
    ))
    assert "measurement_error_concern" in _gap_kinds(out)


def test_suppressed_when_no_pattern_and_no_metadata():
    """Bare program with no measurement metadata should not fire — no
    structural signal, no false positive."""
    out = run(_make_program())
    assert "measurement_error_concern" not in _gap_kinds(out)


def test_suppressed_when_measurement_text_lacks_pattern():
    """Free-form measurement text that doesn't name a documented noisy
    modality must not fire — the classifier's allowlist is exact and
    intentional, not a fuzzy-match."""
    out = run(_make_program(
        intervention_measurement="objective laboratory blood test result",
    ))
    assert "measurement_error_concern" not in _gap_kinds(out)


def test_suppressed_when_extensions_already_declares_measurement_quality():
    """Case 011 (DASH-Sodium) escape-hatch: extensions.ambiguities[*]
    with kind == 'measurement_quality' is the upstream-LLM-declared
    channel; firing measurement_error_concern on top would double-
    disclose the same concern. The classifier deliberately steps back."""
    out = run(_make_program(
        intervention_measurement=(
            "self-reported via FFQ — well-documented underestimation"
        ),
        extensions={
            "ambiguities": [{
                "kind": "measurement_quality",
                "description": "FFQ has known underreporting",
            }]
        },
    ))
    kinds = _gap_kinds(out)
    assert "measurement_error_concern" not in kinds
    # llm_declared_ambiguity should still fire (the suppression is one-way)
    assert "llm_declared_ambiguity" in kinds


def test_suppressed_on_cause_query():
    """Cause queries are existence claims, not effect-magnitude. The
    regression-dilution / attenuation story is specific to effect
    estimation — cause queries don't carry the same identification-
    impact, so no fire."""
    out = run(_make_program(
        intervention_measurement="self-reported smoking",
        query_kind="cause",
    ))
    assert "measurement_error_concern" not in _gap_kinds(out)


def test_severity_is_important():
    """Pinned severity choice: regression dilution is identification-
    impacting (it distorts the estimate's magnitude), not just a
    caveat. Severity is IMPORTANT, not INFORMATIONAL."""
    out = run(_make_program(
        intervention_measurement="self-reported smoking via FFQ",
    ))
    gap = _gap_by_kind(out, "measurement_error_concern")
    assert gap is not None
    assert gap["severity"] == "important"


def test_provenance_names_offending_variable_field_and_pattern():
    """Provenance ref must structurally name (variable, field, pattern)
    so a downstream consumer can route the correct repair action without
    re-parsing the description text — the same routing principle
    graph_theta_independence_mismatch follows: the structured channel
    carries the actionable identifier."""
    out = run(_make_program(
        intervention_measurement=(
            "single-occasion office sphygmomanometer reading"
        ),
    ))
    gap = _gap_by_kind(out, "measurement_error_concern")
    assert gap is not None
    refs = gap["provenance"]
    assert any(
        "x" in ref["ref_id"]
        and "measurement" in ref["ref_id"]
        and "single-occasion" in ref["ref_id"]
        for ref in refs
    ), refs


def test_alternative_paths_name_structural_repairs():
    """Pin: alternative_paths must surface the three structural repair
    options — RCT triangulation / repeat-measurement reliability /
    attenuation factor sensitivity — not just generic 'collect more
    data'. The actionable shape is what makes this gap_kind useful
    downstream."""
    out = run(_make_program(
        intervention_measurement="self-reported smoking via FFQ",
    ))
    gap = _gap_by_kind(out, "measurement_error_concern")
    assert gap is not None
    assert [a["route"] for a in gap["alternative_paths"]] == [
        "use_experimental_data_instead_of_self_report",  # RCT triangulation
        "retest_reliability",           # repeat-measurement reliability
        "report_attenuation_range",     # attenuation-factor sensitivity
    ]


def test_the_concern_is_a_caveat_the_reader_is_led_with():
    """Pin the must-disclose mirror: when measurement_error_concern
    fires, scheduler._attach_structural_caveats must copy a ⚠ line into
    result.explanation. Without this the LLM rendering layer wouldn't
    know to surface the concern unless it parses data_gap_report itself."""
    out = run(_make_program(
        intervention_measurement="self-reported smoking via FFQ",
    ))
    explanation = caveats.text(out["results"][0])
    assert "⚠" in explanation
    assert "测量误差" in explanation


def test_does_not_fire_on_off_path_variable():
    """A variable declared but NOT on the identification path
    (intervention, target, or their ancestors) shouldn't trigger — only
    variables that actually contribute to the estimate carry the bias."""
    program = _make_program()
    # Add an unrelated variable W with self-reported metadata, but NO
    # cause edges connecting it to x or y. Classifier should ignore it.
    program["statements"].insert(0, {
        "kind": "variable",
        "predicate": "w",
        "domain": [True, False],
        "measurement": "self-reported via questionnaire",
    })
    out = run(program)
    assert "measurement_error_concern" not in _gap_kinds(out)
