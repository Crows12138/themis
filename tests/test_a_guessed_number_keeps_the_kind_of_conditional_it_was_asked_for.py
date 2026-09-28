"""A guessed number keeps the kind of conditional it was asked for.

Two confounders of x → y that share a cause: the back-door adjustment over
both, expanded by the chain rule, names P(w | z), and z is not a parent of
w. The kernel's ask for that factor says so — ``provenance:
observational`` — because a statement conditioning on a non-parent is
admitted only when it says it is not a CPT entry.

"Estimate the missing numbers" filled it as ``provenance: llm_prior``, and
the validator held that to parents and refused the whole patch: the demo's
estimate failed on every such graph. The field held two facts — what kind
of conditional a number is, and who supplied it — in three values, and the
fourth combination, a model's guess at an observational factor, had no
spelling. The other road through was worse: kept observational, a guess is
admitted and never reaches the review a reader is shown.

So who supplied the number is its own field, ``llm_prior``, and filling an
ask adds a value, that mark and a reason to what the kernel wrote, whatever
kind it asked for:

- on two confounders sharing a cause, the cells, and on three, a table of
  the observational factor too, are answered, disclosed and audited;
- a guess that claims to be a CPT entry is still held to parents, and a
  guess of either kind owes its reason;
- the old spelling is refused rather than read as a third kind.
"""
from __future__ import annotations

import json
import math
from itertools import product
from types import SimpleNamespace

import pytest

import themis
from themis.input.semantic_validator import Malformed, SemanticError
from themis.input.syntactic_validator import SyntacticError
from themis.web import app as web_app
from themis.web import llm_bridge


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _program(confounders, *extra):
    """x → y, each confounder a cause of both, and c a cause of every
    confounder; no numbers."""
    edges = [("x", "y"), *(("c", z) for z in confounders),
             *((z, t) for z in confounders for t in ("x", "y"))]
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            *({"kind": "variable", "predicate": p, "domain": [True, False]}
              for p in ("c", "x", "y", *confounders)),
            *({"kind": "cause", "from": _atom(a), "to": _atom(b),
               "annotations": {"source": "llm_proposal"}} for a, b in edges),
            {"kind": "query", "id": "q", "query": {
                "kind": "effect", "target": {"atom": _atom("y"), "value": True},
                "intervention": {"atom": _atom("x"), "value": True},
                "given": []}},
            *extra,
        ],
    }


def _cell(trues):
    """What the fake answers a cell whose conditions hold ``trues`` values
    at true: distinct per cell, so the adjustment's weights show."""
    return 0.2 + 0.2 * trues


@pytest.fixture
def model(monkeypatch):
    def create(**kwargs):
        asked = json.loads(kwargs["messages"][0]["content"].split(
            "leave none out:\n", 1)[1])
        priors = [
            {"index": a["index"],
             "baseline": {"value": 0.2, "reason": "how common"},
             "odds_ratios": [{"ratio": r["ratio"], "value": 2.0,
                              "reason": f"effect {r['condition']}"}
                             for r in a["ratios"]]}
            if "table" in a else
            {"index": a["index"],
             "value": _cell(a["probability"].partition(" | ")[2].count("=True")),
             "reason": "a cell"}
            for a in asked]
        return SimpleNamespace(content=[SimpleNamespace(
            type="text", text=json.dumps({"priors": priors}))])

    monkeypatch.setattr(llm_bridge, "_client", lambda api_key=None: SimpleNamespace(
        base_url="http://stub.invalid", messages=SimpleNamespace(create=create)))


def _p(odds):
    return odds / (1 + odds)


def _two():
    """Σ_z,w P(z) P(w|z) P(y|x,z,w), every factor a cell."""
    def at(p, holds):
        return p if holds else 1 - p
    return sum(at(_cell(0), z) * at(_cell(z), w) * _cell(1 + z + w)
               for z, w in product((1, 0), repeat=2))


def _three():
    """The same over v too, whose factor P(v|z,w) and y's are tables:
    baseline 0.2 with every condition absent, odds doubled by each present
    — x among them, set by do(x)."""
    def at(p, holds):
        return p if holds else 1 - p
    return sum(at(_cell(0), z) * at(_cell(z), w)
               * at(_p(0.25 * 2 ** (z + w)), v) * _p(0.25 * 2 ** (1 + z + w + v))
               for z, w, v in product((1, 0), repeat=3))


def _kind_asked(rows, record):
    """The provenance the rows of ``record``'s distribution were asked in."""
    def which(r):
        return (json.dumps(r["target"]["atom"], sort_keys=True),
                frozenset(json.dumps(g["atom"], sort_keys=True)
                          for g in r.get("given") or ()))
    kinds = {r.get("provenance") for r in rows if which(r) == which(record)}
    assert len(kinds) == 1, kinds
    return kinds.pop()


@pytest.mark.parametrize("confounders, want", [
    (("z", "w"), _two()), (("z", "w", "v"), _three()),
], ids=["two confounders: cells", "three: a table of the observational factor"])
def test_a_guess_at_an_observational_factor_is_answered_disclosed_and_audited(
        model, confounders, want):
    program = _program(confounders)
    rows = web_app._probability_skeletons(themis.run(program)["results"][0])
    assert any(r.get("provenance") == "observational" for r in rows)

    filled = llm_bridge.propose_theta_priors(program, rows)
    assert all(f["llm_prior"] is True for f in filled)
    kinds = [(f["kind"], f.get("provenance")) for f in filled]
    assert ("probability", "observational") in kinds
    if len(confounders) == 3:
        assert ("probability_model", "observational") in kinds
    for f in filled:
        assert f.get("provenance") == _kind_asked(rows, f)

    out = themis.apply_patch_and_run(program, {
        "version": "0.1", "kind": "parameter_fill_bundle", "skeletons": filled})
    result = out["results"][0]
    assert result["status"] == "numerically_solved"
    assert result["numeric_result"]["value"] == pytest.approx(want, abs=1e-12)
    disclosed = {p["key"] for p in
                 result["extensions"]["llm_proposed_review"]["probabilities"]}
    assert "P(w(me)=True|z(me)=True)" in disclosed
    themis.verify(out["merged_program"], result)


def _guess(**fields):
    return {"kind": "probability",
            "target": {"atom": _atom("w"), "value": True},
            "given": [{"atom": _atom("z"), "value": True}],
            "value": 0.4, "llm_prior": True, **fields}


def _refused(program):
    with pytest.raises(SemanticError) as raised:
        themis.run(program)
    return raised.value.species


def test_a_guess_that_claims_to_be_a_cpt_entry_is_still_held_to_parents():
    """Who supplied a number does not change what it says it is."""
    program = _program(("z", "w"), _guess(annotations={"source": "a guess"}))
    assert _refused(program) is Malformed.GIVEN_NOT_PARENTS


def test_a_guess_of_either_kind_owes_its_reason():
    program = _program(("z", "w"), _guess(provenance="observational"))
    assert _refused(program) is Malformed.LLM_PRIOR_WITHOUT_SOURCE


def test_the_old_spelling_is_not_read_as_a_third_kind():
    """``provenance: llm_prior`` said who and left what unsaid; a program
    written that way is refused, not read as one or the other."""
    stated = _guess(provenance="llm_prior", annotations={"source": "a guess"})
    del stated["llm_prior"]
    with pytest.raises(SyntacticError, match="provenance"):
        themis.run(_program(("z", "w"), stated))
