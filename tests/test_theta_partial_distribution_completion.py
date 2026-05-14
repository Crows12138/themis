"""Partial-distribution completion in ``theta_builder.build_theta``
(2026-05-14, found by CLadder dry run Q8706).

Before this iter: ``build_theta`` produced exactly the entries a user
supplied — no automatic completion. The numeric evaluator's
marginalization helper iterates a target's full declared domain to
compute ``Σ_z P(target|given,Z=z)·P(Z=z|given)``. If theta only had
``P(V=true)=0.43`` for a binary V (no ``P(V=false)=0.57``), the
domain-iteration broke and the whole marginalization chain failed,
even though ``P(V=false)`` is mechanically determined by the
probability axiom.

This iter: when a user supplies K-1 of K declared-domain values for
some ``(target_atom, given)`` group, build_theta synthesizes the
K-th as ``1 - sum(others)``. The rule is the probability axiom —
probabilities over a disjoint exhaustive domain sum to 1 — so no
inference is being smuggled in. Inconsistent inputs (sum > 1 + ε)
raise ``ConflictingThetaEntry``.

Pinned invariants:
- binary completion: P(X=true)=p alone → builder adds P(X=false)=1-p
- conditional binary completion: P(Y=true|X=true)=p alone →
  builder adds P(Y=false|X=true)=1-p
- multinomial K-1 → K completion: domain has 3 values, 2 supplied,
  builder adds the third
- no-op when full distribution supplied (no double-add, no perturb)
- no-op when more than one value is missing
- inconsistent supplied entries raise ConflictingThetaEntry
- declared-domain on VariableDeclaration wins over observed-only
- end-to-end: CLadder Q8706 shape now solves with one-sided marginal
"""
import pytest

from themis import run
from themis.input.syntactic_validator import validate_ast
from themis.input.semantic_validator import validate_program
from themis.runtime.theta_builder import (
    ConflictingThetaEntry,
    build_theta_from_program,
)


def _theta(program_dict):
    """Run the dict through validate → semantic-validate → build_theta."""
    ast = validate_ast(program_dict)
    prog = validate_program(ast)
    return build_theta_from_program(prog)


def _prog_with_theta(probability_statements, *, domain=(True, False)):
    """Helper: minimal program with one declared binary atom X and
    the given probability statements over it."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "p"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": list(domain)},
            *probability_statements,
        ],
    }


def _atom(pred, *, value=None, val_in_given=None):
    a = {
        "predicate": pred,
        "args": [{"type": "const", "name": "p"}],
    }
    if value is not None:
        return {"atom": a, "value": value}
    return a


def _prob(target_pred, target_value, value, *, given=()):
    return {
        "kind": "probability",
        "target": _atom(target_pred, value=target_value),
        "given": list(given),
        "value": value,
    }


def test_binary_completion_synthesizes_complement():
    """User supplies only P(X=true)=0.43; builder adds P(X=false)=0.57.

    The probability axiom over a binary domain pins the missing
    entry exactly — no model inference, just 1-p.
    """
    program = _prog_with_theta([
        _prob("x", True, 0.43),
    ])
    theta = _theta(program)
    # Locate both entries
    keys = list(theta.entries.keys())
    by_value = {k.target_value: theta.entries[k] for k in keys}
    assert by_value[True] == pytest.approx(0.43)
    assert by_value[False] == pytest.approx(0.57)


def test_conditional_binary_completion():
    """User supplies P(Y=true|X=true)=0.7; builder adds
    P(Y=false|X=true)=0.3 within the same conditioning group."""
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "p"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            _prob("y", True, 0.7,
                  given=[_atom("x", value=True)]),
        ],
    }
    theta = _theta(program)
    # Both true and false entries for the same (y, x=true) group
    found = {}
    for key, value in theta.entries.items():
        if key.target_atom.predicate == "y":
            found[key.target_value] = value
    assert found[True] == pytest.approx(0.7)
    assert found[False] == pytest.approx(0.3)


def test_multinomial_completion_k_minus_one_to_k():
    """Three-valued domain with 2 of 3 supplied → builder adds the
    third. Probability axiom generalizes naturally to K > 2."""
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "p"}]},
        "statements": [
            {"kind": "variable", "predicate": "color",
             "domain": ["red", "green", "blue"]},
            _prob("color", "red", 0.5),
            _prob("color", "green", 0.3),
        ],
    }
    theta = _theta(program)
    by_value = {}
    for key, value in theta.entries.items():
        if key.target_atom.predicate == "color" and not key.given:
            by_value[key.target_value] = value
    assert by_value["red"] == pytest.approx(0.5)
    assert by_value["green"] == pytest.approx(0.3)
    assert by_value["blue"] == pytest.approx(0.2)


def test_no_op_when_distribution_fully_supplied():
    """When K of K values are already given, builder must not
    perturb anything. Sanity: no double-addition, no float drift."""
    program = _prog_with_theta([
        _prob("x", True, 0.4),
        _prob("x", False, 0.6),
    ])
    theta = _theta(program)
    by_value = {}
    for key, value in theta.entries.items():
        if key.target_atom.predicate == "x":
            by_value[key.target_value] = value
    assert by_value[True] == pytest.approx(0.4)
    assert by_value[False] == pytest.approx(0.6)
    # Exactly 2 entries (no extra synthesized)
    assert sum(
        1 for k in theta.entries
        if k.target_atom.predicate == "x"
    ) == 2


def test_no_op_when_more_than_one_missing():
    """If K-2 (or fewer) are supplied for a K-valued domain, the
    probability axiom alone cannot determine the missing entries.
    Builder leaves them absent rather than guessing."""
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "p"}]},
        "statements": [
            {"kind": "variable", "predicate": "color",
             "domain": ["red", "green", "blue", "yellow"]},
            _prob("color", "red", 0.5),
        ],
    }
    theta = _theta(program)
    color_keys = [
        k for k in theta.entries if k.target_atom.predicate == "color"
    ]
    # Only the supplied one — green/blue/yellow stay absent.
    assert len(color_keys) == 1
    assert color_keys[0].target_value == "red"


def test_inconsistent_supplied_entries_raise():
    """Supplied probabilities summing to > 1+ε mean the implied
    complement would be negative. Reject rather than silently clamp —
    the supplied program is broken and the user needs to know."""
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "p"}]},
        "statements": [
            {"kind": "variable", "predicate": "color",
             "domain": ["red", "green", "blue"]},
            _prob("color", "red", 0.7),
            _prob("color", "green", 0.5),  # sum=1.2, implied blue=-0.2
        ],
    }
    with pytest.raises(ConflictingThetaEntry):
        _theta(program)


def test_declared_domain_takes_precedence_over_observed():
    """When VariableDeclaration.domain says (True, False) but only
    P(X=true) was observed in any statement, the builder should
    still treat the domain as binary for completion purposes (not
    fall to the singleton observed domain). Without this, single-
    sided marginal-only theta on a declared-binary atom won't
    complete."""
    program = _prog_with_theta([
        _prob("x", True, 0.6),
    ])
    theta = _theta(program)
    # Declared domain on the x VariableDeclaration is (True, False).
    # After completion, both values should be in theta.entries.
    by_value = {
        k.target_value: v for k, v in theta.entries.items()
        if k.target_atom.predicate == "x"
    }
    assert by_value[True] == pytest.approx(0.6)
    assert by_value[False] == pytest.approx(0.4)


def test_cladder_q8706_shape_solves_end_to_end():
    """The CLadder Q8706 dry-run finding: agent supplied
    ``P(V=true)=0.43`` (no ``P(V=false)``) plus ``P(R|V)`` for both
    sides. Pre-fix the kernel refused because marginalization
    iterated over V's full domain and couldn't find ``P(V=false)``.
    Post-fix the kernel synthesizes the complement and the marginal
    P(R=true) = 0.73·0.43 + 0.29·0.57 ≈ 0.4792 emerges from
    standard marginalization."""
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "p"}]},
        "statements": [
            {"kind": "variable", "predicate": "vaccine",
             "domain": [True, False]},
            {"kind": "variable", "predicate": "recovery",
             "domain": [True, False]},
            {"kind": "cause",
             "from": {"predicate": "vaccine",
                      "args": [{"type": "const", "name": "p"}]},
             "to": {"predicate": "recovery",
                    "args": [{"type": "const", "name": "p"}]}},
            _prob("vaccine", True, 0.43),
            _prob("recovery", True, 0.73,
                  given=[_atom("vaccine", value=True)]),
            _prob("recovery", True, 0.29,
                  given=[_atom("vaccine", value=False)]),
            {"kind": "query", "id": "q", "query": {
                "kind": "probability",
                "target": _atom("recovery", value=True),
                "given": [],
            }},
        ],
    }
    out = run(program)
    result = out["results"][0]
    assert result["status"] == "numerically_solved"
    expected = 0.73 * 0.43 + 0.29 * 0.57  # 0.4792
    # Pull the final numeric value out of the derivation
    final_output = None
    for step in result.get("derivation", {}).get("steps", []) or []:
        if step.get("rule") == "numeric_result":
            out_field = step.get("output")
            if isinstance(out_field, dict) and "value" in out_field:
                final_output = out_field["value"]
            else:
                final_output = out_field
    assert final_output == pytest.approx(expected, abs=1e-6)
