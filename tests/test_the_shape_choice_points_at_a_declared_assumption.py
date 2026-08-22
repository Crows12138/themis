"""The mechanism audit points at assumptions; it does not state them.

#416. The block carried one hand-written sentence per estimator family, and
a sentence cannot be asked anything: not which glossary row it is, so the
ledger hard-coded its layer; not which declaration it restates, so the
ledger's one deduplication — keyed on the assumption id — could not see it.
The same shape assumption therefore reached the reader twice, in two
wordings, under two layers and two severities, and the summary counted a
curve's shape among the assumptions whose failure voids the causal
conclusion.

What the block names now is the subset of the estimator's own declarations
that the glossary files under ``functional_form``. That makes the pointing
total (a family cannot be forgotten, because nobody writes it a sentence)
and checkable (the ids are the same ids, so the existing dedup collapses
the pair with no new logic).

The test that would have caught the original defect is not "no id appears
twice" — the old entry carried no id at all, and its claim was the prose
inside a frame, so neither an id nor a claim comparison saw it. It is
:func:`test_no_assumption_is_disclosed_twice`: the ledger holds exactly as
many lines as the channels have distinct things to say, and an entry that
restates one of them without saying which pushes that count up by one.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import themis
from themis import blocks, ledger
from themis.output.assumption_glossary import classify_assumption
from themis.output.result_orchestrator import (
    build_assumption_ledger,
    build_mechanism_audit,
)

# --- programmes ---------------------------------------------------------------


def _atom(p: str) -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": "u"}]}


_GRAPH = [
    {"kind": "variable", "predicate": "z", "domain": [True, False]},
    {"kind": "variable", "predicate": "t", "domain": [True, False]},
    {"kind": "variable", "predicate": "y", "domain": [True, False]},
    {"kind": "cause", "from": _atom("z"), "to": _atom("t")},
    {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
    {"kind": "cause", "from": _atom("t"), "to": _atom("y")},
]

_EFFECT = {
    "kind": "effect",
    "intervention": {"atom": _atom("t"), "value": True},
    "target": {"atom": _atom("y"), "value": True},
    "given": [],
}
_CAUSATION = {"kind": "causation", "cause": _atom("t"), "effect": _atom("y")}


def _program(query: dict) -> dict:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "u"}]},
        "statements": [*_GRAPH, {"kind": "query", "id": "q", "query": query}],
    }


@pytest.fixture(scope="module")
def frame() -> pd.DataFrame:
    n = 3000
    rng = np.random.default_rng(11)
    z = rng.random(n) < 0.5
    t = rng.random(n) < np.where(z, 0.7, 0.3)
    y = rng.random(n) < np.clip(0.2 + 0.35 * t + 0.3 * z, 0.0, 1.0)
    return pd.DataFrame({"z": z, "t": t, "y": y})


#: Families that reach a mechanism audit, and the estimator kwarg that picks
#: each. Every one of them fits a shape, so every one of them owes the reader
#: the disclosure — which is the point of selecting by layer rather than by
#: whoever remembered to write a sentence.
_SHAPED = {
    "backdoor": {},
    "aipw": {"ate_estimator": "aipw"},
    "ipw": {"ate_estimator": "ipw"},
    "tmle": {"ate_estimator": "tmle"},
}


def _run(query: dict, frame: pd.DataFrame, **kw) -> dict:
    out = themis.estimate(_program(query), frame, ci_bootstrap=0, **kw)
    return out["results"][0]


def _mechanism(result: dict) -> dict | None:
    block = (result.get("extensions") or {}).get(blocks.Block.MECHANISM_AUDIT)
    return None if block is None else block["mechanisms"][0]


def _entries(result: dict) -> list[dict]:
    block = (result.get("extensions") or {}).get(blocks.Block.ASSUMPTION_LEDGER)
    return list((block or {}).get("assumptions") or ())


# --- what the block may name --------------------------------------------------


def test_a_mechanism_names_only_the_shape_among_what_was_declared():
    """The argument is the estimator's whole flat list; the block keeps the
    functional-form part of it. Nothing is assembled for it to name."""
    audit = build_mechanism_audit(
        target="y",
        form="logistic",
        method="backdoor_logistic",
        assumptions=(
            "conditional_exchangeability_given_adjustment_set",  # identification
            "logit_outcome_regression",                          # form
            "ci_via_analytic_influence_function",                # confidence
        ),
    )
    assert audit is not None
    assert audit["mechanisms"][0]["assumptions"] == ["logit_outcome_regression"]


def test_an_estimator_that_assumes_no_shape_gets_no_block():
    """``None`` is a real answer. Six families used to fill the field with a
    narrative of the route taken, and the ledger filed that narrative as a
    distorting functional-form assumption — a row headed "the functional form
    is …" whose body said no functional form was assumed."""
    assert build_mechanism_audit(
        target="P(y|do(t))",
        form="nonparametric_matrix_plug_in",
        method="proximal_miao",
        assumptions=("consistency_of_potential_outcomes",),
    ) is None
    assert build_mechanism_audit(
        target="y", form="f", method="m", assumptions=(),
    ) is None


def test_the_block_is_absent_rather_than_present_and_empty(frame):
    """A key holding ``None`` says a mechanism was audited and found to be
    nothing, which is not what happened."""
    result = _run(_CAUSATION, frame)
    assert result["numeric_estimate"]["assumptions"]
    assert blocks.Block.MECHANISM_AUDIT not in (result.get("extensions") or {})


@pytest.mark.parametrize("family", sorted(_SHAPED))
def test_the_ids_a_mechanism_names_were_declared_by_the_estimator(family, frame):
    """The pointing, checked from the envelope. A block naming an id nowhere
    in the flat list would be introducing an assumption rather than pointing
    at one — and would be invisible to the dedup that keys on the id."""
    result = _run(_EFFECT, frame, **_SHAPED[family])
    mech = _mechanism(result)
    assert mech is not None, f"{family} fits a shape and disclosed none"
    declared = set(result["numeric_estimate"]["assumptions"])
    assert set(mech["assumptions"]) <= declared
    assert mech["assumptions"], "an empty list should have been no block"


@pytest.mark.parametrize("family", sorted(_SHAPED))
def test_every_id_it_names_is_a_shape_and_reaches_the_ledger_as_one(family, frame):
    """The layer is asked for, not asserted. The defect was a shape assumption
    arriving at the identification layer — invalidating — because prose has no
    row to read it off."""
    result = _run(_EFFECT, frame, **_SHAPED[family])
    mech = _mechanism(result)
    by_id = {str(e["id"]): e for e in _entries(result) if e.get("id")}
    for named in mech["assumptions"]:
        assert classify_assumption(named)["layer"] == ledger.Layer.FUNCTIONAL_FORM
        assert by_id[named]["layer"] == "functional_form"
        assert by_id[named]["severity"] == "distorting"


# --- the defect itself --------------------------------------------------------


def _owed(result: dict) -> int:
    """How many distinct things the channels have to say about this answer.

    The estimator's declarations are distinct by id; a proposal edge and a
    theta prior have no id and are counted by occurrence, because each is one
    edge and one number.
    """
    declared = set(result["numeric_estimate"]["assumptions"])
    report = result.get("data_gap_report") or {}
    n_edges = sum(
        1 for g in report.get("gaps") or ()
        if g.get("kind") == "unverified_proposal_edge_on_query_path"
    )
    review = (result.get("extensions") or {}).get(
        blocks.Block.LLM_PROPOSED_REVIEW) or {}
    return len(declared) + n_edges + len(review.get("probabilities") or ())


def _disclosed_once(result: dict) -> None:
    """Nothing is on the ledger twice — the criterion, in both its shapes.

    No id may repeat, which catches a channel that names the same id twice.
    And the total must equal what the channels owe, which catches a channel
    that restates a declaration WITHOUT naming it: that entry is invisible to
    an id comparison, and its claim is the declaration's sentence inside a
    frame, so it is invisible to a claim comparison too. Only the count sees
    it.
    """
    entries = _entries(result)
    ids = [str(e["id"]) for e in entries if e.get("id")]
    assert len(ids) == len(set(ids)), f"an id is disclosed twice: {ids}"
    assert len(entries) == _owed(result), (
        f"{len(entries)} ledger lines for {_owed(result)} things the channels "
        f"declared: {[str(e.get('id') or e.get('claim'))[:40] for e in entries]}"
    )


@pytest.mark.parametrize("family", sorted(_SHAPED))
def test_no_assumption_is_disclosed_twice(family, frame):
    _disclosed_once(_run(_EFFECT, frame, **_SHAPED[family]))


def test_the_criterion_rejects_the_ledger_this_defect_produced(frame):
    """The gate, shown refusing the artefact it was built for.

    Reconstructed rather than described: an entry assembled out of the block's
    own words, carrying the target, the form token and the assumption's
    sentence inside a frame — and no ``id``, because a sentence has none to
    carry. That is what the producer wrote for as long as the field was prose,
    and every check that keys on an id or compares claims passes on it.
    """
    result = _run(_EFFECT, frame)
    _disclosed_once(result)

    mech = _mechanism(result)
    named = mech["assumptions"][0]
    ledger_block = result["extensions"][blocks.Block.ASSUMPTION_LEDGER]
    ledger_block["assumptions"].append({
        "claim": (f"{mech['target']} 的函数形式为 {mech['form']}"
                  f"（{classify_assumption(named)['claim']}）"),
        "layer": "functional_form",
        "severity": "distorting",
        "provenance": "default",
        "testable": True,
    })
    with pytest.raises(AssertionError, match="things the channels declared"):
        _disclosed_once(result)


def test_one_id_gets_one_answer_about_who_can_overrule_it(frame):
    """Across families, because that is where the two answers came from.

    The mechanism channel knows something the glossary does not — who chose
    the form on this run — and still may not answer with it. If it did, the
    same id would read ``default`` in a family whose mechanism block is wired
    up and ``inherent`` in one whose is not, which is a fact about the wiring
    and not about the assumption. #421 is the field that carries the run's
    own answer.
    """
    seen: dict[str, set[str]] = {}
    for kw in _SHAPED.values():
        for e in _entries(_run(_EFFECT, frame, **kw)):
            if e.get("id"):
                seen.setdefault(str(e["id"]), set()).add(str(e["provenance"]))
    split = {k: sorted(v) for k, v in seen.items() if len(v) > 1}
    assert not split, f"one assumption, two answers: {split}"


# --- the case it must refuse --------------------------------------------------


def test_a_block_naming_something_that_is_not_a_shape_is_refused():
    """The gate, asked to say no.

    ``build_mechanism_audit`` selects by layer, so it cannot itself produce
    this — but the ledger reads the block off the envelope, where anything
    could have written it, and stamping the entry is where the two must
    agree. Passing the glossary's layer through rather than the constant
    ``functional_form`` is what makes the disagreement loud instead of a
    silent relabelling of an identification premise as a curve's shape.
    """
    result = {
        "extensions": {
            blocks.Block.MECHANISM_AUDIT: {
                "mechanisms": [{
                    "target": "y",
                    "form": "logistic",
                    "method": "backdoor_logistic",
                    "provenance": "default",
                    "assumptions": ["conditional_exchangeability_given_adjustment_set"],
                }],
                "summary": "…",
            },
        },
    }
    with pytest.raises(ValueError, match="may not write layer"):
        build_assumption_ledger(result)
