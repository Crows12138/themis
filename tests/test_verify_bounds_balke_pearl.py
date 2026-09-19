"""Verifier rule for the Balke-Pearl IV bounds (Phase 12 producer).

Completes the verifier-layer trilogy for the 3 implemented BoundsMethod
producers (MN + MTR + BP-IV ✓; frontdoor_partial is aspirational).

The producer emits a reference to the linear programme, because at a
general cardinality there is no closed form to print. That reference is
a sentence, and the audit reads the row's FACTS rather than the sentence:

- method, and the estimand — the field the canonical opening phrase was
  standing in for
- the named instrument, against what the graph offers for X → Y
- the iv1/iv2/iv3 assumption tag set, exactly

The expressions are rebuilt from the query, the instrument field and the
cardinalities the program declares, and compared — the treatment the two
closed-form methods' expressions always had. What holding them to naming
their facts instead left open, and what the rebuild costs, is in
``test_a_bound_names_its_instrument_as_a_fact``.
"""
from __future__ import annotations

import ast
import inspect

import pytest

from themis.verifier.bounds_rules import (
    verify_balke_pearl_iv_bounds_result,
)
from themis.verifier.errors import VerificationError


# ---------------------------------------------------------------------------
# Byte-code independence (parallel to the T10 and sibling pins)
# ---------------------------------------------------------------------------


from tests.bounds_rows import methods, row

def test_bounds_rules_independence_pin_holds_for_bp_too():
    """Module-level pin: never import themis.output.bounds (parallel
    to T10's independence pin). The pin is on the MODULE, so each new
    verifier function re-asserts it rather than needing its own."""
    import themis.verifier.bounds_rules as br
    src = inspect.getsource(br)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert "output.bounds" not in mod
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "output.bounds" not in alias.name


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _query_dict(target_pred="y", target_val=True,
                intervention_pred="x", intervention_val=True):
    return {
        "kind": "effect",
        "target": {
            "atom": {"predicate": target_pred,
                     "args": [{"type": "const", "name": "me"}]},
            "value": target_val,
        },
        "intervention": {
            "atom": {"predicate": intervention_pred,
                     "args": [{"type": "const", "name": "me"}]},
            "value": intervention_val,
        },
        "given": [],
    }


def _bp_graph(target_pred="y", treatment_pred="x", z="z"):
    """The graph the canonical row is a bound over: z → x → y, x ↔ y.

    The rule checks the named instrument against the edges, so a case
    that cares which graph passes its own; the rest get this one.
    """
    def atom(pred):
        return {"predicate": pred, "args": [{"type": "const", "name": "me"}]}

    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": p, "domain": [True, False]}
            for p in (z, treatment_pred, target_pred)
        ] + [
            {"kind": "cause", "from": atom(z), "to": atom(treatment_pred)},
            {"kind": "cause", "from": atom(treatment_pred),
             "to": atom(target_pred)},
            {"kind": "bidirected", "left": atom(treatment_pred),
             "right": atom(target_pred)},
        ],
    }


def _verify(bounds, *, query_dict, program=None):
    """Audit a row against a graph, defaulting to the canonical one."""
    return verify_balke_pearl_iv_bounds_result(
        bounds,
        program=_bp_graph() if program is None else program,
        query_dict=query_dict,
    )


def _expected_bp_bounds(target_pred="y", treatment_pred="x", z="z"):
    arm = f"P({target_pred}=true | do({treatment_pred}=true))"
    observables = f"P({target_pred}, {treatment_pred} | {z})"
    return {
        "method": "balke_pearl_iv",
        "tightness": "sharp",
        "lower_expression": (
            f"min of {arm} over the response-function polytope fitted to "
            f"{observables} (Balke-Pearl LP, 16 response types)"
        ),
        "upper_expression": (
            f"max of {arm} over the response-function polytope fitted to "
            f"{observables} (same polytope, same observables as lower)"
        ),
        "estimand": "arm_probability",
        "instrument": z,
        "assumptions": [
            "iv1_relevance",
            "iv2_exclusion_instrument_affects_outcome_only_via_treatment",
            "iv3_independence_instrument_independent_of_unmeasured_confounders",
        ],
        "data_required": [
            f"{observables}  # 8 probabilities",
        ],
        "width_when_uninformative": False,
        "notes": f"Balke-Pearl sharp bounds on {arm} ...",
    }


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_accepts_canonical_bp_bounds():
    bounds = _expected_bp_bounds()
    _verify(bounds, query_dict=_query_dict())


def test_accepts_alternative_predicate_names():
    """Verifier must work for any (target, treatment, z) substitution."""
    bounds = _expected_bp_bounds(
        target_pred="cancer", treatment_pred="smoking", z="card_lottery",
    )
    query = _query_dict(
        target_pred="cancer", intervention_pred="smoking",
    )
    _verify(bounds, query_dict=query,
            program=_bp_graph('cancer', 'smoking', 'card_lottery'))


# ---------------------------------------------------------------------------
# Tampered bounds — verifier must catch
# ---------------------------------------------------------------------------


def test_rejects_wrong_method_field():
    bounds = _expected_bp_bounds()
    bounds["method"] = "manski_natural"
    with pytest.raises(VerificationError, match="expected 'balke_pearl_iv'"):
        _verify(bounds, query_dict=_query_dict())


def test_refuses_the_same_bound_said_differently():
    """The facts are all still here; the sentence is not this one.

    The phrase was once the only place the instrument was written down,
    so the rule read the phrase and the phrase became unchangeable. The
    instrument is a field now and the phrase carries no fact of its own
    — which made it look free, and what free left behind is a sentence
    nothing re-derives. It is re-derived now, so a rewording is refused
    for saying something other than what this program renders, and the
    whole case for paying that is in the file this one points at.
    """
    bounds = _expected_bp_bounds()
    bounds["lower_expression"] = bounds["lower_expression"].replace(
        "min of P(", "smallest plausible value of P(",
    )
    with pytest.raises(VerificationError, match="lower_expression mismatch"):
        _verify(bounds, query_dict=_query_dict())


def test_rejects_upper_with_wrong_phrase():
    bounds = _expected_bp_bounds()
    bounds["upper_expression"] = "garbage upper expression"
    with pytest.raises(VerificationError, match="upper_expression mismatch"):
        _verify(bounds, query_dict=_query_dict())


def test_rejects_an_expression_that_does_not_name_the_arm():
    """The check the old phrase could not make.

    'max over 8 Balke-Pearl lower terms (linear combos of P(y, x | z))' is
    a true sentence about an ACE bound and about an arm bound alike — it
    names the observables and not the estimand. The canonical phrase that
    replaced it caught this by accident of wording; what catches it now
    is that the sentence names the treatment at two levels, and a row
    declaring 'arm_probability' brackets one arm.
    """
    bounds = _expected_bp_bounds()
    for key in ("lower_expression", "upper_expression"):
        bounds[key] = bounds[key].replace(
            "P(y=true | do(x=true))",
            "ACE = P(y=true|do(x=1)) - P(y=true|do(x=0))",
        )
    with pytest.raises(VerificationError, match="lower_expression mismatch"):
        _verify(bounds, query_dict=_query_dict())


def test_rejects_an_expression_whose_arm_is_a_different_treatment():
    bounds = _expected_bp_bounds()
    for key in ("lower_expression", "upper_expression"):
        bounds[key] = bounds[key].replace("do(x=true)", "do(other=true)")
    with pytest.raises(VerificationError, match="lower_expression mismatch"):
        _verify(bounds, query_dict=_query_dict())


def test_a_predicate_that_contains_the_other_operator_is_not_refused():
    """Which end of the interval a rendering is, is audited — by building.

    It was audited once by the opening phrase, which also caught a
    swapped pair, and then not at all, because auditing the operator by
    LOOKING FOR it refuses any programme whose predicates contain it and
    ``vitamin`` contains ``min``: a real exposure would have had its
    upper bound rejected for being spelled. A sentence built out of this
    programme's own predicates carries the word where the producer put
    it, so the swapped pair is caught and the exposure is not — which is
    what this case is here to show.
    """
    bounds = _expected_bp_bounds(target_pred="cancer",
                                 treatment_pred="vitamin", z="lottery")
    query = _query_dict(target_pred="cancer", intervention_pred="vitamin")
    _verify(bounds, query_dict=query,
            program=_bp_graph("cancer", "vitamin", "lottery"))


def test_rejects_lower_missing_target_predicate():
    """Tampering: keep canonical phrase but strip target pred → catch."""
    bounds = _expected_bp_bounds()
    bounds["lower_expression"] = (
        "min of P(something | do(x=true)) over some other content"
    )
    with pytest.raises(VerificationError, match="lower_expression mismatch"):
        _verify(bounds, query_dict=_query_dict())


def test_rejects_lower_naming_a_different_treatment():
    """The treatment side used to be checked by the do(...) clause, once.

    There used to be a second check for the bare predicate beside it, and
    then neither: an expression built from the query names the treatment
    wherever the query's treatment goes, so naming another one is a
    mismatch like any other. What the case is about survives the change
    — a bound on a different variable than the one asked about — and it
    is the message that moved.
    """
    bounds = _expected_bp_bounds()
    bounds["lower_expression"] = (
        "min of P(y=true | do(other=true)) over P(y, other | z)"
    )
    bounds["upper_expression"] = (
        "max of P(y=true | do(other=true)) over P(y, other | z)"
    )
    with pytest.raises(VerificationError, match="lower_expression mismatch"):
        _verify(bounds, query_dict=_query_dict())


def test_rejects_lower_missing_instrument_conditioning():
    """A sentence that drops the instrument leaves the reader unable to
    tell what the bound rests on — so it is refused as a rendering, not
    read as the record of which instrument was used."""
    bounds = _expected_bp_bounds()
    bounds["lower_expression"] = (
        "min of P(y=true | do(x=true)) over the polytope fitted to P(y, x)"
    )
    with pytest.raises(VerificationError, match="lower_expression mismatch"):
        _verify(bounds, query_dict=_query_dict())


def test_rejects_missing_iv1_assumption():
    bounds = _expected_bp_bounds()
    bounds["assumptions"] = [
        a for a in bounds["assumptions"] if "iv1" not in a
    ]
    with pytest.raises(VerificationError, match="iv1/iv2/iv3 set"):
        _verify(bounds, query_dict=_query_dict())


def test_rejects_extra_assumption_tag():
    bounds = _expected_bp_bounds()
    bounds["assumptions"] = list(bounds["assumptions"]) + [
        "monotonicity_first_stage_for_late",  # not BP's set
    ]
    with pytest.raises(VerificationError, match="iv1/iv2/iv3 set"):
        _verify(bounds, query_dict=_query_dict())


def test_rejects_non_string_target_predicate():
    bounds = _expected_bp_bounds()
    query = {
        "target": {"atom": {"predicate": 42}, "value": True},
        "intervention": {"atom": {"predicate": "x"}, "value": True},
        "given": [],
    }
    with pytest.raises(VerificationError, match="string target / treatment"):
        _verify(
            bounds, query_dict=query,
        )


# ---------------------------------------------------------------------------
# E2E via real producer output
# ---------------------------------------------------------------------------


def _bp_program():
    """ADMG with binary IV: z → x, x → y, latent u between x and y
    (declared as bidirected). BP-IV bounds fire on the effect query."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "z",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "x",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "x",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "y",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "bidirected", "forall": ["I"],
             "left": {"predicate": "x",
                      "args": [{"type": "var", "name": "I"}]},
             "right": {"predicate": "y",
                       "args": [{"type": "var", "name": "I"}]}},
            {"kind": "query", "id": "bp_e2e",
             "query": {"kind": "effect",
                       "target": {"atom": {"predicate": "y",
                                           "args": [{"type": "const",
                                                     "name": "me"}]},
                                  "value": True},
                       "intervention": {"atom": {"predicate": "x",
                                                 "args": [{"type": "const",
                                                           "name": "me"}]},
                                        "value": True},
                       "given": []}},
        ],
    }


def test_real_bp_program_bounds_pass_verifier_e2e():
    """themis.run on a real BP-IV program emits balke_pearl_iv bounds;
    the new verifier audits cleanly via direct call (themis.verify
    rejects derivation-less results so the wired path is dormant for
    needs_investigation status — same posture as its siblings)."""
    import themis

    program = _bp_program()
    out = themis.run(program)
    result = out["results"][0]
    assert "balke_pearl_iv" in methods(result)
    _verify(
        row(result, "balke_pearl_iv"),
        program=program,
        query_dict=program["statements"][-1]["query"],
    )


def test_real_bp_program_tampered_phrase_caught_e2e():
    import themis

    program = _bp_program()
    out = themis.run(program)
    result = out["results"][0]
    row(result, "balke_pearl_iv")["lower_expression"] = "fake lower"
    with pytest.raises(VerificationError, match="lower_expression mismatch"):
        _verify(
            row(result, "balke_pearl_iv"),
            program=program,
            query_dict=program["statements"][-1]["query"],
        )


def test_re_exported_from_themis_verifier():
    import themis.verifier as v
    assert "verify_balke_pearl_iv_bounds_result" in v.__all__
    assert v.verify_balke_pearl_iv_bounds_result is \
        verify_balke_pearl_iv_bounds_result


# ---------------------------------------------------------------------------
# Trilogy completion sanity
# ---------------------------------------------------------------------------


def test_all_implemented_bounds_methods_have_verifier():
    """Every BoundsMethod value with a real
    producer in themis/output/bounds.py has a dedicated verifier
    function in themis/verifier/bounds_rules.py.

    BoundsMethod values (4 total):
    - manski_natural ✓ producer ✓ verifier
    - balke_pearl_iv ✓ producer ✓ verifier
    - manski_tamer_monotonicity ✓ producer ✓ verifier
    - frontdoor_partial ✗ producer (aspirational) → no verifier needed
    """
    from themis.types import BoundsMethod
    import themis.verifier.bounds_rules as br

    # Producers: read bounds.py for "method=BoundsMethod.X" patterns.
    import re
    bounds_src = inspect.getsource(
        __import__("themis.output.bounds", fromlist=["bounds"])
    )
    produced_names = set(re.findall(
        r"method=BoundsMethod\.([A-Z_]+)", bounds_src
    ))
    name_to_value = {bm.name: bm.value for bm in BoundsMethod}
    produced_values = {name_to_value[n] for n in produced_names}

    # Each produced method must have a verify_X_bounds_result function.
    name_map = {
        "manski_natural": "verify_manski_natural_bounds_result",
        "balke_pearl_iv": "verify_balke_pearl_iv_bounds_result",
        "manski_tamer_monotonicity": "verify_manski_tamer_bounds_result",
    }
    missing = []
    for value in produced_values:
        verifier_name = name_map.get(value)
        if verifier_name is None:
            missing.append(f"{value} (no expected verifier name mapped)")
            continue
        if not hasattr(br, verifier_name):
            missing.append(f"{value} → {verifier_name}")

    assert not missing, (
        f"BoundsMethod producers missing dedicated verifiers: {missing}. "
        "one verifier per producer is the invariant."
    )
