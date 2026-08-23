"""Tests for the ill_defined_intervention_versions gap_kind — the
well-defined-intervention prerequisite.

Triggered by program-shape: the EffectQuery's intervention predicate's
VariableDeclaration declares ``state_vs_event = "state"`` AND no
``time_window`` is set on the same declaration. The schema admitted both
fields for a long time with NO classifier reading state_vs_event's
VALUE — the same shape as the measurement field and the
ObservationStatement. Reading the field's VALUE is what this adds.

Authoritative trigger reference — Hernán MA, Taubman SL 2008 *Int J
Obesity* 32(Suppl 3):S8-S14 "Does obesity shorten life? The importance
of well-defined interventions to answer causal questions": when the
exposure is a habitual / persistent attribute, multiple structurally-
different manipulations can produce the same state value yet entail
DIFFERENT counterfactual outcomes. do(X=state) is therefore under-
defined; the consistency assumption (Hernán & Robins *What If* §3.4)
is silently violated.

Distinct from ``ambiguous_variable_definition``: that kind fires when
fields are absent (silence); this fires on contradictorily-set fields
(state declared, duration absent — the variable schema admits the
inconsistency). Distinct from ``measurement_error_concern``, which
biases the estimate of a well-defined estimand; this one biases the
estimand's definition.

Key invariants pinned here:
- fires when intervention has state_vs_event="state" AND no time_window
  (the explicit contradiction shape)
- ALSO fires when neither state_vs_event NOR time_window is declared
  (silence shape — default-on prophylactic added 2026-05 after Q3
  retest analysis showed explicit-only trigger put the "spot the
  methodology trap" burden back on the LLM)
- does NOT fire when state_vs_event="event" (explicit acute-exposure
  opt-out)
- does NOT fire when time_window is set (the inconsistency is closed)
- does NOT fire on non-EFFECT queries (consistency-violation story is
  about do(.))
- does NOT fire when intervention predicate has no VariableDeclaration
  at all (no schema admittance to flag inferred state on)
- does NOT fire when extensions.ambiguities[*] declares an
  ``ill_defined_intervention`` / ``well_defined_intervention`` kind
  (case 011-style escape hatch)
- severity is IMPORTANT for both shapes (the methodological concern
  is identical regardless of how it was detected)
- description and provenance ref_id differ between explicit and
  inferred: explicit uses ``intervention_state_without_time_window:X``,
  inferred uses ``intervention_state_inferred:X`` — renderers can
  soften wording on the inferred path if desired
- alternative_paths name re-spec / event-encoding / mediation-split /
  RCT / opt-in mixed estimand options — none of which is "fetch more
  data" (the gap is question definition, not row count)
- must-disclose ⚠ line lands in result.explanation
- distinct from ambiguous_variable_definition / measurement_error_concern
"""
from themis import run
from themis import gaps as _gaps


def _make_program(
    *,
    state_vs_event="state",
    time_window=None,
    declare_variable=True,
    query_kind="effect",
    extensions=None,
):
    """Minimal X→Y program with controllable intervention-decl shape."""
    decl = {"kind": "variable", "predicate": "x",
            "domain": [True, False]}
    if state_vs_event is not None:
        decl["state_vs_event"] = state_vs_event
    if time_window is not None:
        decl["time_window"] = time_window
    statements = []
    if declare_variable:
        statements.append(decl)
    statements.extend([
        {"kind": "variable", "predicate": "y",
         "domain": [True, False]},
        {"kind": "cause",
         "from": {"predicate": "x",
                  "args": [{"type": "const", "name": "p"}]},
         "to":   {"predicate": "y",
                  "args": [{"type": "const", "name": "p"}]}},
    ])

    if query_kind == "effect":
        q = {
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
        q = {
            "kind": "cause",
            "from": {"predicate": "x",
                     "args": [{"type": "const", "name": "p"}]},
            "to":   {"predicate": "y",
                     "args": [{"type": "const", "name": "p"}]},
        }
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


def test_fires_on_state_without_time_window():
    """Canonical Hernán & Taubman 2008 trigger: intervention is a
    state-type attribute (BMI / obesity / smoking-status-as-attribute)
    with no duration declared."""
    out = run(_make_program(state_vs_event="state", time_window=None))
    assert "ill_defined_intervention_versions" in _gap_kinds(out)


def test_fires_on_state_vs_event_unset_too():
    """state_vs_event=None means the LLM didn't declare state-vs-event.
    Combined with absent time_window, this is the 'silence' shape:
    an intervention atom in an EFFECT query without any time / state
    framing. Default-on prophylactic — fires the same GapKind as the
    explicit-state shape so the methodology concern surfaces even when
    the LLM didn't think to flag it. Treating this as
    'silence ≠ contradiction' and staying quiet was the first design,
    but a retest
    2026-05 showed that put 'spot the methodology trap' back on the
    LLM, defeating Themis's positioning. Distinguish via provenance
    ref_id, not via fire/no-fire.)"""
    out = run(_make_program(state_vs_event=None, time_window=None))
    assert "ill_defined_intervention_versions" in _gap_kinds(out)


def test_inferred_path_provenance_distinguishable_from_explicit():
    """Both the 'state explicit + no time_window' and the 'both fields
    absent' shapes fire the same GapKind, but the provenance ref_id
    distinguishes them so a renderer can soften wording on the
    inferred path:
    - explicit:  intervention_state_without_time_window:<predicate>
    - inferred:  intervention_state_inferred:<predicate>
    This pins the audit-trail invariant so downstream consumers can
    rely on the ref_id prefix to route inferred-vs-explicit handling
    without re-parsing description text."""
    out_inferred = run(_make_program(
        state_vs_event=None, time_window=None,
    ))
    out_explicit = run(_make_program(
        state_vs_event="state", time_window=None,
    ))
    gap_inferred = _gap_by_kind(out_inferred,
                                "ill_defined_intervention_versions")
    gap_explicit = _gap_by_kind(out_explicit,
                                "ill_defined_intervention_versions")
    assert gap_inferred is not None
    assert gap_explicit is not None
    refs_inferred = [r["ref_id"] for r in gap_inferred["provenance"]]
    refs_explicit = [r["ref_id"] for r in gap_explicit["provenance"]]
    assert any("state_inferred:x" in r for r in refs_inferred), \
        refs_inferred
    assert any(
        "state_without_time_window:x" in r for r in refs_explicit
    ), refs_explicit


def test_inferred_path_severity_matches_explicit():
    """The methodological concern is identical whether detected via
    explicit state declaration or inferred from silence. Severity must
    be IMPORTANT on both paths — softer severity on the inferred
    branch would risk renderers dropping the warning."""
    out_inferred = run(_make_program(
        state_vs_event=None, time_window=None,
    ))
    gap = _gap_by_kind(out_inferred, "ill_defined_intervention_versions")
    assert gap is not None
    assert gap["severity"] == "important"


def test_inferred_path_description_signals_opt_out_route():
    """The inferred-path description must tell the user how to silence
    the warning (declare state_vs_event='event' or time_window).
    Without this guidance the warning is unactionable for the case
    where the LLM actually meant an event-like intervention."""
    out = run(_make_program(state_vs_event=None, time_window=None))
    gap = _gap_by_kind(out, "ill_defined_intervention_versions")
    assert gap is not None
    description = _gaps.described(gap)
    # opt-out route 1: declare state_vs_event="event"
    assert "event" in description
    # opt-out route 2: declare time_window
    assert "time_window" in description


def test_does_not_fire_when_event_type():
    """state_vs_event='event' is a discrete acute exposure (e.g.
    'received vaccine dose at visit 3') — the canonical well-defined
    intervention. Even with no time_window it's well-defined enough
    that consistency holds."""
    out = run(_make_program(state_vs_event="event", time_window=None))
    assert "ill_defined_intervention_versions" not in _gap_kinds(out)


def test_does_not_fire_when_time_window_supplied():
    """state_vs_event='state' with a time_window says 'this state
    persisting for ≥X duration'. The duration closes the version-
    ambiguity gap because a sustained-state intervention is well-
    defined relative to the named duration (Hernán & Taubman §3:
    'a well-defined intervention requires either an act or an
    act-equivalent state with timing')."""
    out = run(_make_program(state_vs_event="state",
                            time_window="≥6 months sustained"))
    assert "ill_defined_intervention_versions" not in _gap_kinds(out)


def test_does_not_fire_on_non_effect_query():
    """The consistency-violation story is about do(.) operator
    semantics. cause / assoc / probability queries don't invoke the
    do-operator on a state-attribute, so the kind is suppressed.
    (cause query also has no data needs branch — and no must-disclose
    pollution — so this is the cleaner suppression path.)"""
    out = run(_make_program(state_vs_event="state", time_window=None,
                            query_kind="cause"))
    assert "ill_defined_intervention_versions" not in _gap_kinds(out)


def test_does_not_fire_when_intervention_predicate_undeclared():
    """No VariableDeclaration for the intervention predicate at all
    means there's no schema admittance to call out as dead-schema
    theatre. Framing-check would emit nothing for an undeclared
    predicate; this kind follows the same opt-in convention."""
    out = run(_make_program(declare_variable=False))
    assert "ill_defined_intervention_versions" not in _gap_kinds(out)


def test_suppressed_by_extensions_ambiguity_escape_hatch():
    """The same escape hatch measurement_error_concern honours: when
    the user or upstream LLM has
    already declared the concern as an A1 ambiguity, firing the
    structural kind on top would double-disclose. The escape-hatch
    keys are 'ill_defined_intervention' or 'well_defined_intervention'."""
    extensions = {
        "ambiguities": [
            {"kind": "ill_defined_intervention",
             "rationale": "obesity manipulation route unspecified"},
        ],
    }
    out = run(_make_program(state_vs_event="state", time_window=None,
                            extensions=extensions))
    assert "ill_defined_intervention_versions" not in _gap_kinds(out)


def test_suppressed_by_well_defined_intervention_escape_hatch():
    """Symmetric escape-hatch: alternate spelling of the same
    declaration."""
    extensions = {
        "ambiguities": [
            {"kind": "well_defined_intervention",
             "rationale": "deliberately accepting state ambiguity"},
        ],
    }
    out = run(_make_program(state_vs_event="state", time_window=None,
                            extensions=extensions))
    assert "ill_defined_intervention_versions" not in _gap_kinds(out)


def test_severity_is_important():
    """Pinned: consistency violation distorts the *estimand definition*
    (multiple manipulations producing the same state value entail
    different counterfactual outcomes), not just adds a caveat. The
    answer to the question as posed is genuinely ambiguous, not
    merely uncertain. Severity must be IMPORTANT."""
    out = run(_make_program(state_vs_event="state", time_window=None))
    gap = _gap_by_kind(out, "ill_defined_intervention_versions")
    assert gap is not None
    assert gap["severity"] == "important"


def test_provenance_names_offending_intervention():
    """Structured provenance must name the predicate so a downstream
    consumer can route the right action (which variable to re-encode
    or add time_window to) without re-parsing description text."""
    out = run(_make_program(state_vs_event="state", time_window=None))
    gap = _gap_by_kind(out, "ill_defined_intervention_versions")
    assert gap is not None
    refs = gap["provenance"]
    assert any(
        "intervention_state_without_time_window:x" in ref["ref_id"]
        for ref in refs
    ), refs


def test_alternative_paths_name_question_re_specification_options():
    """Pin: alternative_paths must surface the structural repair
    options Hernán & Taubman 2008 §3-§5 spell out — re-encode as
    event, split via mediation, use RCT, opt in via ambiguity escape
    hatch. 'Fetch more data' is NOT in the list because no row count
    fixes an under-defined estimand."""
    out = run(_make_program(state_vs_event="state", time_window=None))
    gap = _gap_by_kind(out, "ill_defined_intervention_versions")
    assert gap is not None
    assert [a["route"] for a in gap["alternative_paths"]] == [
        "declare_the_intervention_an_event",   # turn the state into an act
        "split_the_intervention_in_two",       # intervention + state pair
        "use_experimental_data_for_the_versions",   # RCT triangulation
        "accept_the_mixed_estimand",           # the ambiguity escape hatch
    ]
    # The two that vary by occasion carry the variable they are about,
    # rather than having it rendered into a sentence upstream.
    assert gap["alternative_paths"][0]["said"] == {"intervention": "x"}
    assert gap["alternative_paths"][1]["said"] == {"intervention": "x"}


def test_must_disclose_explanation_includes_warning_line():
    """Pin the must-disclose mirror: when this kind fires, scheduler.
    _attach_structural_caveats must copy a ⚠ line into result.explanation
    so a renderer reading only ``explanation`` sees the well-defined-
    intervention concern before the headline number."""
    out = run(_make_program(state_vs_event="state", time_window=None))
    explanation = out["results"][0].get("explanation", "")
    assert "⚠" in explanation
    # Must reference Hernán & Taubman 2008 to anchor the structural claim.
    assert "Taubman" in explanation or "well-defined" in explanation \
        or "ill-defined" in explanation


def test_distinct_from_ambiguous_variable_definition():
    """When state_vs_event='state' is declared, ambiguous_variable_definition
    will still fire on the OTHER missing fields (observability,
    direction, etc.) — they're complementary, not duplicate. This
    kind specifically targets the state-without-duration contradiction;
    ambiguous_variable_definition targets the silence on other fields.
    Both can fire on the same program; this test asserts neither
    suppresses the other (no double-fire on state_vs_event line, but
    both kinds present)."""
    out = run(_make_program(state_vs_event="state", time_window=None))
    kinds = _gap_kinds(out)
    assert "ill_defined_intervention_versions" in kinds
    assert "ambiguous_variable_definition" in kinds


def test_l3_case_015_fires_with_full_envelope():
    """Integration pin: the actual case_015 JSON file (Hernán & Taubman
    2008 obesity → 5yr mortality) must fire ill_defined_intervention_versions
    end-to-end through themis.run, with severity IMPORTANT and a
    must-disclose explanation line. This is the regression-test
    counterpart to the corpus parametrize entry."""
    import json
    from pathlib import Path
    case_path = (
        Path(__file__).resolve().parent.parent
        / "docs" / "l3_simulation"
        / "case_015_hernan_taubman_2008_obesity_well_defined.json"
    )
    program = json.loads(case_path.read_text(encoding="utf-8"))
    out = run(program)
    kinds = _gap_kinds(out)
    assert "ill_defined_intervention_versions" in kinds, kinds
    gap = _gap_by_kind(out, "ill_defined_intervention_versions")
    assert gap is not None
    assert gap["severity"] == "important"
    explanation = out["results"][0].get("explanation", "")
    assert "⚠" in explanation
