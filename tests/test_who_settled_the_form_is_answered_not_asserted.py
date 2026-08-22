"""#421 — who chose the functional form, asked rather than assumed.

The mechanism-audit block carries a ``provenance``: who settled the shape the
number was fitted through. It was the literal ``"default"``, written at
fourteen attach points, so every family said the same thing — and a constant is
not an answer. For TMLE, which takes no ``model=`` at all, "the estimator
picked a form because none was specified, so the caller can specify one and
this line changes" is false in both halves.

The fact was not missing, it was discarded. Ten estimators resolved a caller's
``model=`` into a concrete form and each computed the answer on the way:
``auto`` means the system chose, anything else means the caller named it. None
of them kept it, and it cannot be recovered afterwards — a resolved
``"logistic"`` and a caller's ``"logistic"`` are the same string.

Seven of those ten were also the SAME resolution, spelled seven ways across
four modules. :mod:`themis.estimation.form` is that decision, and the census
below is what keeps a sixteenth estimate from carrying a shape it cannot say
the origin of.
"""
from __future__ import annotations

import dataclasses
import inspect

import numpy as np
import pandas as pd
import pytest

import themis
from themis import estimation
from themis.estimation.form import AUTO, chosen_by, outcome_form
from themis.ledger import Provenance
from themis.output.result_orchestrator import build_mechanism_audit


def _atom(predicate: str) -> dict:
    return {"predicate": predicate, "args": [{"type": "const", "name": "me"}]}


def _backdoor_program() -> dict:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "t", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "cause", "from": _atom("z"), "to": _atom("t")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("t"), "to": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("t"), "value": True},
                "target": {"atom": _atom("y"), "value": True},
                "given": [],
            }},
        ],
    }


@pytest.fixture(scope="module")
def frame() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    n = 1_500
    z = rng.integers(0, 2, n).astype(bool)
    t = rng.random(n) < 0.3 + 0.4 * z
    y = rng.random(n) < 0.2 + 0.3 * t + 0.2 * z
    return pd.DataFrame({"t": t, "y": y, "z": z})


def _mechanism(result: dict) -> dict:
    audit = (result.get("extensions") or {}).get("mechanism_audit") or {}
    mechanisms = audit.get("mechanisms") or []
    assert len(mechanisms) == 1, mechanisms
    return mechanisms[0]


def _run(frame: pd.DataFrame, **kwargs) -> dict:
    envelope = themis.estimate(
        _backdoor_program(), frame, ci_bootstrap=0, **kwargs)
    return envelope["results"][0]


# ====================================================== the by-product


def test_auto_is_the_system_choosing_and_anything_else_is_the_caller():
    assert chosen_by(AUTO) == Provenance.DEFAULT
    assert chosen_by("linear") == Provenance.CALLER_ASSERTED
    assert chosen_by("drlearner") == Provenance.CALLER_ASSERTED


def test_the_outcome_column_settles_auto_and_the_caller_settles_the_rest():
    binary = pd.Series([True, False, True, False])
    numeric = pd.Series([1.5, 2.5, 3.5, 4.5])

    assert outcome_form(AUTO, binary) == ("logistic", Provenance.DEFAULT)
    assert outcome_form(AUTO, numeric) == ("linear", Provenance.DEFAULT)
    assert outcome_form(AUTO, binary, logistic="logit") == (
        "logit", Provenance.DEFAULT)
    assert outcome_form("linear", binary) == (
        "linear", Provenance.CALLER_ASSERTED)


def test_a_form_the_function_has_never_heard_of_passes_through():
    """Which forms an estimator can fit is that estimator's question.

    Refusing here would answer it once for all ten of them, and they do not
    agree: ``2sls`` is a form for the IV family and nothing to the rest.
    """
    assert outcome_form("2sls", pd.Series([True, False])) == (
        "2sls", Provenance.CALLER_ASSERTED)


# ====================================================== nobody can forget


def test_every_estimate_that_carries_a_shape_can_say_who_settled_it():
    """The census, so a sixteenth family cannot quietly go back to a constant.

    A ``form`` with no ``form_provenance`` beside it is an estimate whose
    disclosure surface has to guess, and guessing is what this was.
    """
    carriers = []
    for name in dir(estimation):
        obj = getattr(estimation, name)
        if not inspect.isclass(obj) or not dataclasses.is_dataclass(obj):
            continue
        fields = {f.name for f in dataclasses.fields(obj)}
        if "form" in fields:
            carriers.append((name, fields))

    assert carriers, "no estimate carries a form — the census found nothing"
    missing = [name for name, fields in carriers
               if "form_provenance" not in fields]
    assert not missing, f"these carry a form and cannot say who chose it: {missing}"


def test_the_declared_origins_are_all_in_the_vocabulary():
    for name in dir(estimation):
        obj = getattr(estimation, name)
        if not inspect.isclass(obj) or not dataclasses.is_dataclass(obj):
            continue
        for field in dataclasses.fields(obj):
            if field.name != "form_provenance":
                continue
            if field.default in ("", dataclasses.MISSING):
                continue        # resolved at construction, checked below
            Provenance(field.default)      # raises if it is not a member


# ====================================================== end to end


def _settled(mechanism: dict) -> dict[str, str]:
    """Who settled each shape assumption the block names.

    Per assumption and not per block, since #423: one field held one answer
    for however many shape decisions a family made, and a back-door run with
    a caller's ``model=`` and a multi-level covariate holds two of different
    origin.
    """
    return {str(a["id"]): str(a["settled_by"]) for a in mechanism["assumptions"]}


def test_the_block_says_the_system_chose_when_nothing_was_specified(frame):
    mechanism = _mechanism(_run(frame))
    assert mechanism["form"] == "logistic"
    assert _settled(mechanism) == {
        "logit_outcome_regression": Provenance.DEFAULT}


def test_the_block_says_the_caller_chose_when_the_caller_did(frame):
    mechanism = _mechanism(_run(frame, model="logistic"))
    assert mechanism["form"] == "logistic"
    assert _settled(mechanism) == {
        "logit_outcome_regression": Provenance.CALLER_ASSERTED}


def test_the_two_runs_differ_only_there(frame):
    """Same shape, same number, different answer to "who decided".

    Which is the whole point: the string ``"logistic"`` cannot tell them
    apart, so the disclosure surface could not either.
    """
    auto = _run(frame)
    told = _run(frame, model="logistic")
    assert auto["numeric_estimate"]["point"] == pytest.approx(
        told["numeric_estimate"]["point"])
    assert _mechanism(auto)["form"] == _mechanism(told)["form"]
    assert _settled(_mechanism(auto)) != _settled(_mechanism(told))


def test_a_family_with_no_lever_says_the_method_required_it(frame):
    """TMLE takes no ``model=``. Nothing was chosen, so nothing says it was.

    This is the case the constant got exactly backwards: it told the reader to
    pass an argument that does not exist.
    """
    result = _run(frame, ate_estimator="tmle")
    mechanism = _mechanism(result)
    assert mechanism["method"] == "tmle"
    assert set(_settled(mechanism).values()) == {Provenance.INHERENT}


def test_the_origin_clause_follows_the_provenance(frame):
    auto = (_run(frame)["extensions"] or {})["mechanism_audit"]["summary"]
    told = (_run(frame, model="logistic")["extensions"]
            or {})["mechanism_audit"]["summary"]
    assert "估计器默认选择" in auto
    assert "你在问题里断言的" in told


# ====================================================== the refusal


def test_the_block_cannot_be_built_without_saying_who_chose():
    """No default, because a default is what this was.

    A keyword with no default fails at the call site, where the family that
    forgot is named — rather than four frames later in a sentence a reader
    would have had to disbelieve.
    """
    with pytest.raises(TypeError):
        build_mechanism_audit(          # type: ignore[call-arg]
            target="y", form="logistic", method="backdoor_logistic",
            assumptions=("logit_outcome_regression",),
        )


def test_an_estimate_that_forgot_is_refused_rather_than_rendered_blank():
    """The empty string a resolved family carries until it fills it in."""
    with pytest.raises(ValueError):
        build_mechanism_audit(
            target="y", form="logistic", method="backdoor_logistic",
            assumptions=("logit_outcome_regression",), form_provenance="",
            shape_provenance={},
        )


def test_a_word_outside_the_vocabulary_is_refused_too():
    with pytest.raises(ValueError):
        build_mechanism_audit(
            target="y", form="logistic", method="backdoor_logistic",
            assumptions=("logit_outcome_regression",),
            form_provenance="estimator_default", shape_provenance={},
        )
