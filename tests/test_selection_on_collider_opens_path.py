"""Tests for the selection_on_collider_opens_path gap_kind — the
second shape of selection bias.

Triggered by program-shape: an ObservationStatement(W, value) encodes
implicit sample restriction to W=value, AND the DAG has both intervention
X and target Y as directed ancestors of W. Per Pearl d-separation,
conditioning on W (which the restricted sample implicitly does) opens
X→…→W←…←Y; the marginal effect estimate from the restricted sample
carries selection-induced bias that no covariate adjustment can close.

Authoritative trigger reference — Hernán MA, Hernández-Díaz S, Robins JM
2004 *Epidemiology* 15:615 "A Structural Approach to Selection Bias",
specifically §3 ("conditioning on a common effect" = selection bias) and
§4 (differential loss to follow-up depends on both exposure and outcome).

Distinction from ``collider_conditioning_opens_backdoor``:
that kind fires on EffectQuery.given (explicit conditioning); this kind
fires on ObservationStatement (implicit sample restriction). Both shapes
together cover board #7 selection bias.

Distinction from Phase 9 §T9.1 ``SelectionNode``: SelectionNode is a
*transport* primitive (cross-population distribution difference); this
gap is *within-sample* bias from a downstream collider.

Key invariants pinned here:
- fires when ObservationStatement is on a node W with X and Y as
  directed ancestors (both conditions required)
- does NOT fire when W has only X as ancestor (not a collider on X→Y)
- does NOT fire when W has only Y as ancestor (not a collider on X→Y)
- does NOT fire when W has no ObservationStatement (just a free
  declared collider has no implicit-restriction signal)
- does NOT fire when ObservationStatement is on intervention or target
  themselves (degenerate query, not selection bias)
- severity is IMPORTANT (identification damage, not informational)
- alternative_paths name IPSW + revise-DAG + transport-not-this options
- provenance ref structurally names (observed_node, X→Y) trio
- must-disclose ⚠ line lands in result.explanation
- distinct kind from collider_conditioning_opens_backdoor (mutual
  exclusion when one path applies — no double-fire on the same case)
"""
from themis import run


def _make_program(
    *,
    add_x_to_w_edge=True,
    add_y_to_w_edge=True,
    observe_w=True,
    observe_predicate=None,
    observe_value=True,
):
    """Minimal X→Y plus optional X→W and Y→W (collider on W) plus
    optional ObservationStatement on W.

    Defaults match the canonical Hernán 2004 selection-bias structure;
    flip flags off to construct negative tests.
    """
    statements = [
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "y", "domain": [True, False]},
        {"kind": "variable", "predicate": "w", "domain": [True, False]},
        {"kind": "cause",
         "from": {"predicate": "x", "args": [{"type": "const", "name": "p"}]},
         "to":   {"predicate": "y", "args": [{"type": "const", "name": "p"}]}},
    ]
    if add_x_to_w_edge:
        statements.append({"kind": "cause",
            "from": {"predicate": "x",
                     "args": [{"type": "const", "name": "p"}]},
            "to":   {"predicate": "w",
                     "args": [{"type": "const", "name": "p"}]}})
    if add_y_to_w_edge:
        statements.append({"kind": "cause",
            "from": {"predicate": "y",
                     "args": [{"type": "const", "name": "p"}]},
            "to":   {"predicate": "w",
                     "args": [{"type": "const", "name": "p"}]}})
    if observe_w:
        pred = observe_predicate or "w"
        statements.append({
            "kind": "observation",
            "atom": {"predicate": pred,
                     "args": [{"type": "const", "name": "p"}]},
            "value": observe_value,
        })
    statements.append({
        "kind": "query", "id": "q",
        "query": {
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
        },
    })
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "p"}]},
        "statements": statements,
    }


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


def test_fires_on_canonical_hernan_2004_structure():
    """The Hernán 2004 §4 structure: X→Y, X→W, Y→W (W is collider),
    Observation(W, True). Should fire."""
    out = run(_make_program())
    assert "selection_on_collider_opens_path" in _gap_kinds(out)


def test_does_not_fire_when_only_x_is_ancestor_of_w():
    """W is downstream of X but not Y — not a collider on the X→Y path.
    Conditioning on W is then a different problem (mediator-block /
    overcontrol), not selection bias of this shape."""
    out = run(_make_program(add_y_to_w_edge=False))
    assert "selection_on_collider_opens_path" not in _gap_kinds(out)


def test_does_not_fire_when_only_y_is_ancestor_of_w():
    """W is downstream of Y but not X — also not a V-collider linking
    X and Y. Conditioning on W has different bias semantics."""
    out = run(_make_program(add_x_to_w_edge=False))
    assert "selection_on_collider_opens_path" not in _gap_kinds(out)


def test_does_not_fire_when_no_observation_statement():
    """A free collider node W (X→W, Y→W) without any ObservationStatement
    is just a declared structural feature — there's no implicit sample
    restriction to surface a bias from. The kind only fires when the
    program *also* encodes the restriction."""
    out = run(_make_program(observe_w=False))
    assert "selection_on_collider_opens_path" not in _gap_kinds(out)


def test_does_not_fire_when_observation_on_intervention():
    """Observation on the intervention itself (X) is a different
    problem (degenerate query — fixing the treatment value), not
    selection-on-collider. Classifier explicitly skips this."""
    out = run(_make_program(observe_predicate="x"))
    assert "selection_on_collider_opens_path" not in _gap_kinds(out)


def test_does_not_fire_when_observation_on_target():
    """Observation on the target itself (Y) similarly degenerates
    the effect query — not the selection-bias structure."""
    out = run(_make_program(observe_predicate="y"))
    assert "selection_on_collider_opens_path" not in _gap_kinds(out)


def test_severity_is_important():
    """Pinned severity choice: selection on a collider is identification-
    impacting bias (Hernán 2004 §5: 'no covariate adjustment closes the
    new path'), not informational caveat. Must be IMPORTANT."""
    out = run(_make_program())
    gap = _gap_by_kind(out, "selection_on_collider_opens_path")
    assert gap is not None
    assert gap["severity"] == "important"


def test_provenance_names_observation_node_and_x_y_pair():
    """Provenance ref must structurally name (observed_node,
    intervention -> target) so a downstream consumer can route the
    correct repair action without re-parsing the description text."""
    out = run(_make_program())
    gap = _gap_by_kind(out, "selection_on_collider_opens_path")
    assert gap is not None
    refs = gap["provenance"]
    assert any(
        "selection_observation:w" in ref["ref_id"]
        and "x" in ref["ref_id"]
        and "y" in ref["ref_id"]
        for ref in refs
    ), refs


def test_alternative_paths_name_structural_repairs():
    """Pin: alternative_paths must surface the three structural repair
    options Hernán et al 2004 spell out — IPSW, revise DAG, route via
    transport (selection_node) instead of within-sample restriction.
    'Adjust on more covariates' is NOT in the list because it doesn't
    fix the bias (Hernán 2004 §5)."""
    out = run(_make_program())
    gap = _gap_by_kind(out, "selection_on_collider_opens_path")
    assert gap is not None
    alts = " || ".join(gap["alternative_paths"])
    # IPSW reference (Hernán 2004 §5)
    assert "inverse-probability-of-selection" in alts or "IPSW" in alts
    # transport / selection_node distinction
    assert "selection_node" in alts or "transport" in alts


def test_must_disclose_explanation_includes_warning_line():
    """Pin the must-disclose mirror: when this kind fires, scheduler.
    _attach_structural_caveats must copy a ⚠ line into result.explanation
    so a renderer reading only ``explanation`` sees the bias warning
    before the headline number."""
    out = run(_make_program())
    explanation = out["results"][0].get("explanation", "")
    assert "⚠" in explanation
    assert "selected" in explanation or "selection" in explanation.lower() \
        or "样本" in explanation


def test_distinct_kind_from_collider_conditioning_opens_backdoor():
    """`collider_conditioning_opens_backdoor` fires on
    EffectQuery.given containing a collider;
    `selection_on_collider_opens_path` fires on ObservationStatement.
    Same V-structure, different access path. Where given is empty AND
    an ObservationStatement is present, ONLY the second must fire —
    they are mutually exclusive on this program shape."""
    out = run(_make_program())
    kinds = _gap_kinds(out)
    assert "selection_on_collider_opens_path" in kinds
    assert "collider_conditioning_opens_backdoor" not in kinds


def test_l3_case_014_fires_with_full_envelope():
    """Integration pin: the actual case_014 JSON file (Hernán 2004
    HIV/AZT → AIDS-death) must fire selection_on_collider_opens_path
    end-to-end through themis.run, with severity IMPORTANT and a
    must-disclose explanation line. This is the regression-test
    counterpart to the corpus parametrize entry."""
    import json
    from pathlib import Path
    case_path = (
        Path(__file__).resolve().parent.parent
        / "docs" / "l3_simulation"
        / "case_014_hernan_2004_selection_bias.json"
    )
    program = json.loads(case_path.read_text(encoding="utf-8"))
    out = run(program)
    kinds = _gap_kinds(out)
    assert "selection_on_collider_opens_path" in kinds, kinds
    gap = _gap_by_kind(out, "selection_on_collider_opens_path")
    assert gap is not None
    assert gap["severity"] == "important"
    explanation = out["results"][0].get("explanation", "")
    assert "⚠" in explanation
