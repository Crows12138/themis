"""Tests for the ``dichotomized_continuous_measure`` gap_kind (2026-06-18,
dichotomization).

Triggered by program-shape: a VariableDeclaration on the identification
path (the intervention, the target, or a directed ancestor of either)
declares a non-empty ``threshold`` field. The variable schema documents
``threshold`` as "Cutoff that turns a continuous measurement into this
predicate's value, e.g. >=3cm" — so its PRESENCE is the structural
fingerprint that a continuous quantity was dichotomized at a cutpoint.

This is the fourth field of the same shape, after ``measurement``, the
``ObservationStatement`` and ``state_vs_event``: without this kind,
``threshold``'s ABSENCE
drove ``ambiguous_variable_definition`` (you didn't operationalize) but
its PRESENCE produced no signal at all.

Authoritative references — Royston, Altman & Sauerbrei 2006 *Stat Med*
25:127 "Dichotomizing continuous predictors in multiple regression: a
bad idea" (power loss + cutpoint dependence + residual confounding);
Altman et al 1994 *JNCI* 86:829 (data-driven "optimal" cutpoint inflates
type-I error); Becher 1992 *Stat Med* 11:1747 (residual confounding from
coarse categorisation of a continuous confounder).

Distinct from ``ambiguous_variable_definition`` (fires on ABSENT framing
fields) and from ``measurement_error_concern`` (noisy measurement
modality, not cutpoint coarsening). Severity INFORMATIONAL — a declared
cutpoint does NOT break identification; the caveat informs interpretation
and points at Themis's own dose-response path (Phase 13/14).
"""
from themis import run


def _make_program(
    *,
    thresholds=None,           # {predicate: threshold_string}
    confounder=False,          # add Z->X, Z->Y
    isolated=False,            # add an isolated variable w (off-path)
    query_kind="effect",
    extensions=None,
):
    """X->Y program, optionally with a confounder Z and an off-path w,
    with controllable ``threshold`` declarations per variable."""
    thresholds = thresholds or {}

    def _decl(pred):
        d = {"kind": "variable", "predicate": pred, "domain": [True, False]}
        if pred in thresholds:
            d["threshold"] = thresholds[pred]
        return d

    def _atom(pred):
        return {"predicate": pred, "args": [{"type": "const", "name": "p"}]}

    statements = [_decl("x"), _decl("y")]
    statements.append({"kind": "cause", "from": _atom("x"), "to": _atom("y")})
    if confounder:
        statements.append(_decl("z"))
        statements.append({"kind": "cause", "from": _atom("z"), "to": _atom("x")})
        statements.append({"kind": "cause", "from": _atom("z"), "to": _atom("y")})
    if isolated:
        statements.append(_decl("w"))  # declared, no edges -> off the path

    if query_kind == "effect":
        q = {
            "kind": "effect",
            "target": {"atom": _atom("y"), "value": True},
            "intervention": {"atom": _atom("x"), "value": True},
            "given": [],
        }
    elif query_kind == "cause":
        q = {"kind": "cause", "from": _atom("x"), "to": _atom("y")}
    else:
        raise ValueError(query_kind)

    statements.append({"kind": "query", "id": "q", "query": q})
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "p"}]},
        "statements": statements,
    }
    if extensions is not None:
        program["extensions"] = extensions
    return program


KIND = "dichotomized_continuous_measure"


def _gap_kinds(out):
    report = out["results"][0].get("data_gap_report") or {}
    return [g["kind"] for g in report.get("gaps", [])]


def _gap(out):
    report = out["results"][0].get("data_gap_report") or {}
    for g in report.get("gaps", []):
        if g["kind"] == KIND:
            return g
    return None


def test_fires_when_exposure_dichotomized():
    """The canonical case: a continuous exposure (e.g. BMI) declared via a
    cutpoint (`>=30`) — do(X=high) coarsens a dose and loses the
    dose-response."""
    out = run(_make_program(thresholds={"x": ">=30 (BMI obese cutoff)"}))
    assert KIND in _gap_kinds(out)


def test_fires_when_confounder_dichotomized():
    """A dichotomized CONFOUNDER (age cut at 50) is exactly Becher 1992's
    residual-confounding case — coarse categories leave within-stratum
    confounding so the backdoor adjustment is incomplete. The classifier
    must reach confounders via the directed-ancestor closure, not just
    X / Y."""
    out = run(_make_program(
        thresholds={"z": ">=50 (age dichotomized)"}, confounder=True,
    ))
    assert KIND in _gap_kinds(out)


def test_does_not_fire_without_threshold():
    """No threshold anywhere — nothing was dichotomized, so silence."""
    out = run(_make_program(thresholds={}))
    assert KIND not in _gap_kinds(out)


def test_does_not_fire_for_off_path_variable():
    """A declared variable with a threshold that is NOT on the
    identification path (no causal connection to X or Y) is not part of
    the estimand and must not trigger the caveat."""
    out = run(_make_program(
        thresholds={"w": ">=median split"}, isolated=True,
    ))
    assert KIND not in _gap_kinds(out)


def test_does_not_fire_on_non_effect_query():
    """The dichotomization-bias story is about estimating X->Y under
    do(.). A cause query (does a path exist?) carries no estimand and no
    data needs, so the kind is suppressed."""
    out = run(_make_program(
        thresholds={"x": ">=30"}, query_kind="cause",
    ))
    assert KIND not in _gap_kinds(out)


def test_suppressed_by_extensions_ambiguity_escape_hatch():
    """The escape hatch measurement_error_concern honours: when the
    upstream LLM has already named
    the dichotomization as an A1 ambiguity, firing the structural kind on
    top would double-disclose."""
    extensions = {"ambiguities": [
        {"kind": "dichotomization", "rationale": "median split chosen by analyst"},
    ]}
    out = run(_make_program(
        thresholds={"x": ">=30"}, extensions=extensions,
    ))
    assert KIND not in _gap_kinds(out)


def test_severity_is_informational():
    """Pinned: a declared cutpoint does NOT break identification (unlike
    measurement_error's regression dilution or ill_defined's undefined
    estimand). It is a known, bounded modeling choice. Severity must be
    INFORMATIONAL — escalating it would over-warn on well-documented
    standard cutpoints (BMI>=30, etc.)."""
    out = run(_make_program(thresholds={"x": ">=30"}))
    gap = _gap(out)
    assert gap is not None
    assert gap["severity"] == "informational"


def test_provenance_names_variable_and_threshold():
    """Structured provenance must name the offending predicate AND the
    threshold value so a downstream consumer can route the action
    (which variable to keep continuous) without re-parsing description."""
    out = run(_make_program(thresholds={"x": ">=30 (BMI obese cutoff)"}))
    gap = _gap(out)
    assert gap is not None
    refs = [r["ref_id"] for r in gap["provenance"]]
    assert any("program:variable:x:threshold:" in r for r in refs), refs


def test_alternative_paths_point_at_dose_response():
    """The repair is a modeling choice (keep it continuous), not 'fetch
    more rows'. alternative_paths must surface Themis's own dose-response
    path as the continuous alternative + cutpoint sensitivity.

    By route rather than by phrase. What the reader is told is the route's
    sentence and that is one wording of it in one language; what this test
    is about is WHICH way out was offered, which is the route.
    """
    out = run(_make_program(thresholds={"x": ">=30"}))
    gap = _gap(out)
    assert gap is not None
    assert [a["route"] for a in gap["alternative_paths"]] == [
        "keep_the_measure_continuous",
        "report_cutpoint_sensitivity",
        "stratify_more_finely",
    ]


def test_must_disclose_explanation_includes_warning_line():
    """Pin the must-disclose mirror: a ⚠ line must land in
    result.explanation so a renderer reading only ``explanation`` sees
    the operationalisation caveat before the headline number."""
    out = run(_make_program(thresholds={"x": ">=30"}))
    explanation = out["results"][0].get("explanation", "")
    assert "⚠" in explanation
    assert "二分" in explanation or "Royston" in explanation


def test_distinct_from_ambiguous_variable_definition():
    """When `threshold` is declared on X (but other framing fields are
    absent), ambiguous_variable_definition still fires on those OTHER
    fields — the two kinds are complementary, not duplicate. This kind
    targets the dichotomization fingerprint; ambiguous_variable_definition
    targets the silence on remaining fields."""
    out = run(_make_program(thresholds={"x": ">=30"}))
    kinds = _gap_kinds(out)
    assert KIND in kinds
    assert "ambiguous_variable_definition" in kinds
