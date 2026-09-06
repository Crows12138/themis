"""One estimate, one ``form_provenance``, and more shape decisions than one.

#426. ``form_provenance`` answers "who settled the OUTCOME MODEL", and the
block handed that one answer to every functional-form assumption the estimate
declared. An estimator makes several shape decisions, pulled by different
levers — ``model=``, ``propensity_floor=``, ``stabilized=`` — and only the
first has a do-nothing value the caller can be distinguished by, because only
it defaults to a word (``"auto"``) rather than to a real number.

Measured on one unchanged default propensity floor of 0.01, on the same frame,
with nothing about the clip differing between the runs:

    ipw                       inherent
    aipw  model='logistic'    caller_asserted
    aipw  auto                default
    tmle                      inherent

Three different answers to "who set this floor", and the true answer —
nobody — was one of them by coincidence. ``caller_asserted`` is the one that
costs the reader something: :attr:`Provenance.CALLER_ASSERTED.answerable`
promises that withdrawing it widens the answer, and there was nothing to
withdraw.

The repair is that the estimator making the decision says who made it, per
assumption id, because it is the only thing that knows which of its shapes
have a lever. What that replaced was a table in the CONSUMER listing which ids
stood outside the run's resolution — five entries, guessed from the outside,
and it missed four.
"""
from __future__ import annotations

import ast
import pathlib

import numpy as np
import pandas as pd
import pytest

import themis
from themis import blocks, ledger
from themis.estimation.aipw import (
    DEFAULT_PROPENSITY_FLOOR,
    estimate_aipw_ate,
    estimate_ipw_ate,
)
from themis.estimation.form import (
    NO_OTHER_SHAPES,
    UNSET,
    pulled_by,
    shapes_settled,
)
from themis.estimation.tmle import estimate_tmle_ate
from themis.assumption_glossary import layer_of
from themis.output.result_orchestrator import build_mechanism_audit
from themis.verifier.assumption_ledger_rules import (
    verify_assumption_ledger as _rule_verify,
)

_FLOOR = f"propensity_clipped_to_floor_{DEFAULT_PROPENSITY_FLOOR}"
_HAJEK = "hajek_stabilized_weights"
_HT = "horvitz_thompson_weights"
_DR = "doubly_robust_outcome_OR_propensity_model_correct"
_LINK = "logit_outcome_regression"


# --- one frame, thin enough that the clip actually bites ----------------------


@pytest.fixture(scope="module")
def frame() -> pd.DataFrame:
    """Propensities driven to both extremes, so ``n_trimmed`` is non-zero and
    the clip disclosure is really declared. A floor nobody is clipped to is a
    line that never reaches the ledger, and a line that never reaches the
    ledger cannot be measured saying the wrong thing."""
    rng = np.random.default_rng(4)
    n = 4000
    z = rng.normal(size=n)
    x = rng.random(n) < 1 / (1 + np.exp(-3.2 * z))
    y = rng.random(n) < np.clip(0.2 + 0.3 * x + 0.25 * (z > 0), 0, 1)
    return pd.DataFrame({"x": x, "y": y, "z": z})


def _atom(predicate: str) -> dict:
    return {"predicate": predicate, "args": [{"type": "const", "name": "u"}]}


@pytest.fixture(scope="module")
def program() -> dict:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "u"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "variable", "predicate": "z", "scale": "continuous"},
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True},
                "given": []}},
        ],
    }


#: The four runs the defect was measured on, as ``(kwargs, label)``.
_RUNS = (
    ({"ate_estimator": "ipw"}, "ipw"),
    ({"ate_estimator": "aipw", "model": "logistic"}, "aipw-told"),
    ({"ate_estimator": "aipw"}, "aipw-auto"),
    ({"ate_estimator": "tmle"}, "tmle"),
)


def _result(program: dict, frame: pd.DataFrame, **kw) -> dict:
    return themis.estimate(program, frame, ci_bootstrap=0, **kw)["results"][0]


def _settled(result: dict) -> dict[str, str]:
    mech = result["extensions"][blocks.Block.MECHANISM_AUDIT]["mechanisms"][0]
    return {str(a["id"]): str(a["settled_by"]) for a in mech["assumptions"]}


def _floor_id(settled: dict[str, str]) -> str:
    hit = [i for i in settled if i.startswith(_FLOOR)]
    assert len(hit) == 1, settled
    return hit[0]


# --- the rule this replaced, transcribed --------------------------------------


#: The consumer-side table, as it stood, and the function that spent it. Kept
#: verbatim rather than described: the claim below is that these five entries
#: were the whole of what stood outside a run's resolution, and a paraphrase
#: could not be wrong about that.
_FORM_NOT_RESOLVED = {
    "multi_level_covariates_entered_as_ordered_numbers": "default",
    "mediators_drawn_jointly_via_gaussian_residual_copula": "default",
    "chain_rule_factoring_of_joint_mediator_conditional": "inherent",
    "no_mediator_mediator_interaction_in_outcome_model": "inherent",
    "outcome_model_correctly_specified_at_chain_fixed_values": "inherent",
}


def _the_rule_this_replaced(assumption_id: str, form_provenance: str) -> str:
    fixed = _FORM_NOT_RESOLVED.get(assumption_id)
    return fixed if fixed is not None else form_provenance


def test_the_old_rule_gave_one_unchanged_floor_three_different_origins(
        program, frame):
    """The measurement, reproduced from the envelope the fix produces.

    The run's own ``form_provenance`` still reaches the block — it is the
    answer for the link — so the pre-#426 answer for the floor can be read off
    a current result by applying the old rule to it. Nothing about the clip
    differs across these four runs: same frame, same 0.01, same units trimmed.
    """
    was: dict[str, str] = {}
    for kw, label in _RUNS:
        settled = _settled(_result(program, frame, **kw))
        # The run's resolution, read back off the block: the id that IS the
        # outcome model, or — for IPW, which fits none — the propensity model
        # it fits instead, which is what its constant answers for.
        resolution = settled.get(
            _LINK) or settled["correct_propensity_model_single_robust"]
        was[label] = _the_rule_this_replaced(_floor_id(settled), resolution)

    assert was == {
        "ipw": "inherent",
        "aipw-told": "caller_asserted",
        "aipw-auto": "default",
        "tmle": "inherent",
    }
    # And one of them told the reader they had asserted it.
    assert was["aipw-told"] == ledger.Provenance.CALLER_ASSERTED


def test_the_same_unchanged_floor_now_reads_the_same_way_on_every_run(
        program, frame):
    """One fact, one answer. ``default`` and not ``inherent``, because
    :attr:`Provenance.DEFAULT.answerable` is the true one: nobody set it, and
    a caller who wants a different clip can name one."""
    answers = {}
    for kw, label in _RUNS:
        settled = _settled(_result(program, frame, **kw))
        answers[label] = settled[_floor_id(settled)]
    assert set(answers.values()) == {"default"}, answers


def test_a_family_with_three_levers_gives_three_answers(program, frame):
    """The shape of the defect, on the run that shows all three at once.

    Double robustness is AIPW's, whatever the caller says; the link is the
    caller's, because they named it; the floor is nobody's. One field could
    not have carried this, which is why the repair is not a better default.
    """
    settled = _settled(_result(program, frame,
                               ate_estimator="aipw", model="logistic"))
    assert settled[_DR] == "inherent"
    assert settled[_LINK] == "caller_asserted"
    assert settled[_floor_id(settled)] == "default"


# --- the lever the estimator API exposes --------------------------------------


def _block_for(estimate) -> dict[str, str]:
    audit = build_mechanism_audit(
        target="y", form=estimate.form, method=estimate.method,
        assumptions=estimate.assumptions,
        form_provenance=estimate.form_provenance,
        shape_provenance=estimate.shape_provenance,
    )
    assert audit is not None
    return {str(a["id"]): str(a["settled_by"])
            for a in audit["mechanisms"][0]["assumptions"]}


def test_naming_the_default_value_is_not_the_same_call_as_naming_nothing(
        frame):
    """The whole reason the lever needed a sentinel.

    Both runs clip at 0.01 and produce the same number, the same id and the
    same declaration. What differs is that one caller wrote it down — and
    ``caller_asserted`` promises a reader that withdrawing it widens the
    answer, which is only true of the one who has something to withdraw.
    A lever whose do-nothing value is a real number cannot tell them apart
    after the call, so it is asked before.
    """
    quiet = estimate_ipw_ate(frame, treatment="x", outcome="y",
                             adjustment=("z",), ci_bootstrap=0)
    told = estimate_ipw_ate(frame, treatment="x", outcome="y",
                            adjustment=("z",), ci_bootstrap=0,
                            propensity_floor=DEFAULT_PROPENSITY_FLOOR)

    assert quiet.point == told.point
    assert quiet.assumptions == told.assumptions
    quiet_block, told_block = _block_for(quiet), _block_for(told)
    floor = _floor_id(quiet_block)
    assert quiet_block[floor] == "default"
    assert told_block[floor] == "caller_asserted"


@pytest.mark.parametrize("stabilized, weights", [(None, _HAJEK), (False, _HT)])
def test_which_weights_is_its_own_lever_and_says_so(frame, stabilized, weights):
    """``stabilized=`` settles which estimator the weights come from, and no
    value of ``model=`` reaches it. IPW's ``form_provenance`` is the constant
    ``inherent`` — true of the propensity model, which IS the method, and
    false of this."""
    kw = {} if stabilized is None else {"stabilized": stabilized}
    block = _block_for(estimate_ipw_ate(
        frame, treatment="x", outcome="y", adjustment=("z",),
        ci_bootstrap=0, **kw))

    assert weights in block
    assert block[weights] == ("default" if stabilized is None
                              else "caller_asserted")
    # ...and the propensity model beside it still answers with the method's.
    assert block["correct_propensity_model_single_robust"] == "inherent"


def test_the_floor_lever_is_the_same_lever_on_all_three_families(frame):
    """AIPW and TMLE clip the same propensities through the same helper, and
    the id is spelled in one place so all three file the origin under the id
    the reader will actually see."""
    for estimate in (
        estimate_ipw_ate(frame, treatment="x", outcome="y",
                         adjustment=("z",), ci_bootstrap=0),
        estimate_aipw_ate(frame, treatment="x", outcome="y",
                          adjustment=("z",), ci_bootstrap=0,
                          propensity_floor=0.05),
        estimate_tmle_ate(frame, treatment="x", outcome="y",
                          adjustment=("z",), ci_bootstrap=0,
                          propensity_floor=0.05),
    ):
        block = _block_for(estimate)
        floor = [i for i in block if i.startswith("propensity_clipped_to_floor_")]
        assert len(floor) == 1, block
        assert block[floor[0]] == (
            "default" if estimate.propensity.floor == DEFAULT_PROPENSITY_FLOOR
            else "caller_asserted")


# --- the helper, and what it refuses to say -----------------------------------


def test_an_origin_is_kept_only_for_a_shape_the_run_actually_assumed():
    """The estimator names the pairs it MIGHT emit; the declaration list
    decides which are real. A clip that trimmed nobody declares nothing, and
    an origin filed against it would be an answer to a question the reader was
    never asked — and the builder refuses one."""
    assumptions = ("consistency_of_potential_outcomes", _HAJEK)
    kept = shapes_settled(
        assumptions,
        (_HAJEK, ledger.Provenance.DEFAULT),
        ("propensity_clipped_to_floor_0.01_on_7", ledger.Provenance.DEFAULT),
    )
    assert dict(kept) == {_HAJEK: "default"}


def test_a_family_with_no_other_lever_says_so_by_saying_nothing():
    assert dict(shapes_settled(("anything",))) == {}
    assert dict(NO_OTHER_SHAPES) == {}
    with pytest.raises(TypeError):
        NO_OTHER_SHAPES["x"] = "default"      # type: ignore[index]


def test_the_sentinel_is_what_absence_looks_like():
    """``pulled_by`` reads the absence of a value; :func:`chosen_by` one axis
    over reads a word. Both exist because a do-nothing value has to be
    distinguishable from a value that does the same thing."""
    assert pulled_by(UNSET) == ledger.Provenance.DEFAULT
    assert pulled_by(DEFAULT_PROPENSITY_FLOOR) == (
        ledger.Provenance.CALLER_ASSERTED)
    assert pulled_by(False) == ledger.Provenance.CALLER_ASSERTED
    assert pulled_by(0) == ledger.Provenance.CALLER_ASSERTED


# --- every pair an estimator names is a shape, and a word it may write --------


_ESTIMATION = pathlib.Path(themis.__file__).parent / "estimation"


def _literal_pairs() -> list[tuple[str, str, str]]:
    """Every ``(id, Provenance.X)`` written literally into a
    ``shapes_settled`` call, as ``(module, id, provenance)``."""
    found: list[tuple[str, str, str]] = []
    for path in sorted(_ESTIMATION.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "shapes_settled"):
                continue
            for arg in node.args[1:]:
                if not (isinstance(arg, ast.Tuple) and len(arg.elts) == 2):
                    continue
                name, origin = arg.elts
                if (isinstance(name, ast.Constant)
                        and isinstance(name.value, str)
                        and isinstance(origin, ast.Attribute)):
                    found.append((path.name, name.value, origin.attr))
    return found


def test_every_origin_an_estimator_files_is_a_shape_and_an_allowed_word():
    """An origin filed against an id the glossary does not read as a shape is
    an origin nothing reaches: it reads in the source exactly like a
    considered decision and excuses nothing. This is the gate the consumer's
    table used to carry, moved to where the pairs are now written."""
    pairs = _literal_pairs()
    assert len(pairs) >= 5, pairs
    # The criterion discriminates: an identification premise declared in the
    # same tuple is not a shape, and a pair naming one would fail below.
    assert layer_of("consistency_of_potential_outcomes") != (
        ledger.Layer.FUNCTIONAL_FORM)
    _, admissible = ledger.ADMISSIBLE["audited_mechanism"]
    for module, name, origin in pairs:
        assert layer_of(name) == ledger.Layer.FUNCTIONAL_FORM, (module, name)
        assert getattr(ledger.Provenance, origin) in admissible, (module, name)


def test_the_design_matrix_pair_is_a_shape_and_an_allowed_word():
    """The one pair carried as a constant rather than written at the call, so
    that the nine families appending the row cannot disagree about it."""
    from themis.estimation.declared import ORDERED_ENTRY_SHAPE

    name, origin = ORDERED_ENTRY_SHAPE
    _, admissible = ledger.ADMISSIBLE["audited_mechanism"]
    assert layer_of(name) == ledger.Layer.FUNCTIONAL_FORM
    assert origin in admissible


# --- and the whole thing still passes its own audit ---------------------------


def test_the_ledger_rules_pass_on_every_one_of_the_four_runs(program, frame):
    """A check that says no to everything says nothing.

    The RULES rather than ``themis.verify_assumption_ledger``, which runs the
    schema gate first: on a frame this thin the overlap-violation gap writes
    ``required_data: null`` where the schema declares an object, which is
    #427 and has nothing to do with who settled a shape.
    """
    for kw, _label in _RUNS:
        _rule_verify(_result(program, frame, **kw))
