"""The licence behind an interventional risk, held together across surfaces.

``interventional_risk_provenance`` was a bare ``str`` listed eleven times
with no two listings naming the same set — and the sets genuinely differ,
because the admissible values depend on which derivation rule wrote them.
:mod:`themis.risk_provenance` states that dependence once. These tests hold
every other listing to it: the verifier's deliberately independent
re-declaration, the schema's three container enums, and the browser's map.

They also pin the part that made the missing table cost something rather
than merely read badly. A licence is a claim, and a claim nobody re-derives
is a claim the producer made about itself.
"""
from __future__ import annotations

import copy
import json
import pathlib
import re

import numpy as np
import pandas as pd
import pytest

import themis
from themis import risk_provenance
from themis.risk_provenance import ADMISSIBLE, RiskProvenance
from themis.verifier import VerificationError
from themis.verifier.rules import _RISK_FREE, _RISK_PROVENANCES_BY_RULE

REPO = pathlib.Path(__file__).resolve().parent.parent
SCHEMA = json.loads(
    (REPO / "themis" / "schemas" / "query_result.schema.json")
    .read_text(encoding="utf-8")
)
WEB = REPO / "themis" / "web" / "frontend" / "src" / "lib" / "verdict.ts"


# ----------------------------------------------------------- the vocabulary
def test_every_licence_says_what_it_asserts_and_what_the_reader_is_told():
    for licence in RiskProvenance:
        assert licence.asserts.strip(), f"{licence} asserts nothing"
        assert licence.zh.strip(), f"{licence} has no reader sentence"


@pytest.mark.parametrize("field", ["asserts", "zh"])
def test_no_two_licences_say_the_same_thing(field):
    """Two names with one sentence is the fingerprint of a missing table.

    The assumption glossary carried it for real — a plural id and a
    singular one, both glossed 干预风险取自随机实验, which dropped the only
    thing the second id existed to carry.
    """
    said = [getattr(p, field) for p in RiskProvenance]
    assert len(set(said)) == len(said), (
        f"two licences share a {field}: "
        f"{sorted(s for s in said if said.count(s) > 1)}"
    )


def test_the_readers_sentence_never_claims_the_answer_came_from_data():
    """The same licence reaches a reader from theta and from data.

    ``extensions.causation`` is written by both paths, so a sentence that
    said "computed from the data" would be false half the times it is
    printed — which is what the explainer's gloss used to do.
    """
    for licence in RiskProvenance:
        assert "从数据算得" not in licence.zh, licence


def test_a_licence_no_rule_may_write_is_refused_at_import():
    """The whitelist is silent about what it left out, so the question is
    asked from the other side. Falsified by dropping a member from every
    row: import raises."""
    written = frozenset().union(*ADMISSIBLE.values())
    assert set(RiskProvenance) == written


# ------------------------------------------------- the verifier's own copy
@pytest.mark.parametrize("rule", sorted(ADMISSIBLE))
def test_the_verifier_re_declares_the_same_row(rule):
    """Deliberately two copies (re-deriving an answer from the producer's own
    vocabulary is not an independent check), so drift needs pinning."""
    assert rule in _RISK_PROVENANCES_BY_RULE, (
        f"the verifier has no row for {rule}; a rule it does not know is a "
        f"rule whose provenance nothing re-derives"
    )
    assert _RISK_PROVENANCES_BY_RULE[rule] == {str(p) for p in ADMISSIBLE[rule]}


def test_the_verifier_knows_no_rule_the_registry_does_not():
    assert set(_RISK_PROVENANCES_BY_RULE) == set(ADMISSIBLE)


def test_the_verifiers_risk_free_set_is_the_registrys():
    assert _RISK_FREE == {str(p) for p in RiskProvenance if not p.uses_risk}


# ------------------------------------------------------ the schema's enums
def _enum_at(*path):
    node = SCHEMA
    for key in path:
        node = node[key]
    return set(node["interventional_risk_provenance"]["enum"])


def test_the_causation_block_carries_the_union_of_both_causation_rules():
    """``extensions.causation`` is written by the theta scheduler AND
    overwritten by the estimation dispatch, so a surface reading it sees
    either path's licences."""
    assert _enum_at(
        "properties", "extensions", "properties", "causation", "properties",
    ) == {str(p) for p in risk_provenance.carried_by(
        "causation_probability_bounds", "numeric_causation_estimate",
    )}


def test_the_two_numeric_blocks_carry_exactly_their_own_rule():
    ne = SCHEMA["$defs"]["numericEstimate"]["properties"] \
        if "numericEstimate" in SCHEMA.get("$defs", {}) \
        else SCHEMA["properties"]["numeric_estimate"]["properties"]
    for block, rule in (
        ("probabilities_of_causation", "numeric_causation_estimate"),
        ("counterfactual_cell", "numeric_counterfactual_cell_estimate"),
    ):
        assert set(
            ne[block]["properties"]["interventional_risk_provenance"]["enum"]
        ) == {str(p) for p in ADMISSIBLE[rule]}, block


# --------------------------------------------------------------- the web
def _web_map() -> dict[str, str]:
    source = WEB.read_text(encoding="utf-8")
    listed = re.search(
        r"const RISK_PROVENANCE_ZH: Record<string, string> = \{(.*?)\n\}",
        source, re.S,
    )
    assert listed, "verdict.ts declares no RISK_PROVENANCE_ZH"
    return dict(re.findall(r"^  (\w+): '(.*)',$", listed.group(1), re.M))


def _half_width(text: str) -> str:
    # Kept equal to the twin table in ``test_web_vocabularies``: the two used
    # to differ, so a divergence one gate caught the other read as agreement.
    for full, half in (
        ("，", ","), ("；", ";"), ("：", ":"), ("（", "("), ("）", ")"),
    ):
        text = text.replace(full, half)
    return text


def test_the_browser_translates_the_same_vocabulary_the_same_way():
    """The one copy that cannot import the table, because it is in another
    language. Keys AND sentences: a reader who gets one explanation in the
    report and a different one in the browser has been told the surfaces
    disagree about where the number came from.

    The web file writes half-width punctuation throughout — its own
    convention — so that substitution is the only difference allowed.

    Over EVERY rule, not the causation pair. The browser renders the
    counterfactual cell's licence too, and that block carries four licences
    the causation block cannot — so pinned against the causation union this
    passed while the cell's licences had no sentence in the browser at all.
    Naming the rules rather than the enum keeps the pin honest in the other
    direction as well: a licence no rule may write has no reader to serve.
    """
    carried = risk_provenance.carried_by(*risk_provenance.ADMISSIBLE)
    web = _web_map()
    assert set(web) == {str(p) for p in carried}
    for licence in carried:
        assert web[str(licence)] == _half_width(licence.zh)


# ------------------------------------------------- the licence is a claim
def _var(p):
    return {"kind": "variable", "predicate": p, "domain": [True, False]}


def _cause(a, b):
    return {"kind": "cause", "from": {"predicate": a, "args": []},
            "to": {"predicate": b, "args": []}}


def _causation_ast(**query_extra):
    query = {"kind": "causation", "cause": {"predicate": "x", "args": []},
             "effect": {"predicate": "y", "args": []}, "monotonic": True}
    query.update(query_extra)
    return {
        "version": "0.1", "domain": {"objects": []},
        "statements": [
            _var("x"), _var("y"), _var("z"),
            _cause("z", "x"), _cause("z", "y"), _cause("x", "y"),
            {"kind": "query", "id": "q", "query": query},
        ],
    }


def _confounded(n=20_000, seed=1):
    rng = np.random.default_rng(seed)
    z = rng.random(n) < 0.5
    u = rng.random(n)
    y0, y1 = u < np.where(z, 0.5, 0.2), u < np.where(z, 0.8, 0.6)
    x = rng.random(n) < np.where(z, 0.7, 0.3)
    return pd.DataFrame({"x": x, "y": np.where(x, y1, y0), "z": z})


def test_verify_rejects_a_back_door_estimate_relabelled_as_experimental():
    """The one that made this more than tidying.

    ``user_experimental`` is inside the schema's enum, so nothing upstream
    stops it; and it is the value that switches OFF the adjustment-set
    re-derivation, the only thing this rule re-derives on the graph. Until
    the licence itself was re-derived, mislabelling the provenance made a
    wrong adjustment set stop being audited.
    """
    ast = _causation_ast()
    good = themis.estimate(ast, _confounded())["results"][0]
    themis.verify(ast, good)
    assert good["derivation"]["steps"][0]["inputs"][
        "interventional_risk_provenance"] == "backdoor_adjustment"

    bad = copy.deepcopy(good)
    for holder in (bad["derivation"]["steps"][0]["inputs"],
                   bad["extensions"]["causation"],
                   bad["numeric_estimate"]["probabilities_of_causation"]):
        holder["interventional_risk_provenance"] = "user_experimental"
    with pytest.raises(VerificationError, match="the query carries none"):
        themis.verify(ast, bad)


def test_verify_rejects_an_experimental_estimate_relabelled_as_back_door():
    """The mirror. The caller DID hand over both arms, so nothing on the
    graph licensed the number — a graph-derived licence is the claim that
    it did."""
    ast = _causation_ast(
        experimental_risk_treated=0.7, experimental_risk_control=0.35,
    )
    good = themis.estimate(ast, _confounded())["results"][0]
    themis.verify(ast, good)
    assert good["derivation"]["steps"][0]["inputs"][
        "interventional_risk_provenance"] == "user_experimental"

    bad = copy.deepcopy(good)
    for holder in (bad["derivation"]["steps"][0]["inputs"],
                   bad["extensions"]["causation"],
                   bad["numeric_estimate"]["probabilities_of_causation"]):
        holder["interventional_risk_provenance"] = "backdoor_adjustment"
    with pytest.raises(
        VerificationError, match="claims the risk was obtained from the graph",
    ):
        themis.verify(ast, bad)


def test_a_same_world_cell_is_still_not_required_when_the_caller_sent_an_arm():
    """The exemption the biconditional would have got wrong.

    ``user_experimental`` iff the caller supplied the arm holds only for
    answers that USE an arm. A same-world cell reads none — consistency
    answers it — so what the caller also happened to send is not read, and
    demanding a licence match there would reject a correct answer.
    """
    atom = lambda p: {"predicate": p, "args": [{"type": "const", "name": "me"}]}
    prob = lambda pred, value, given, v: {
        "kind": "probability",
        "target": {"atom": atom(pred), "value": value},
        "given": [{"atom": atom(g), "value": gv} for g, gv in given],
        "value": v,
    }
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": atom("x"), "to": atom("y")},
            prob("x", False, [], 0.6), prob("x", True, [], 0.4),
            prob("y", True, [("x", False)], 0.3),
            prob("y", False, [("x", False)], 0.7),
            prob("y", True, [("x", True)], 0.8),
            prob("y", False, [("x", True)], 0.2),
            {"kind": "query", "id": "q", "query": {
                "kind": "counterfactual",
                "observed": {"atom": atom("x"), "value": True},
                "counterfactual_intervention": {
                    "atom": atom("x"), "value": True},
                "counterfactual_target": {"atom": atom("y"), "value": True},
                "experimental_risk_treated": 0.8,
            }},
        ],
    }
    result = themis.run(program)["results"][0]
    step = result["derivation"]["steps"][0]["inputs"]
    assert step["interventional_risk_provenance"] == "not_required"
    themis.verify(program, result)


def test_stamp_refuses_a_licence_the_rule_may_not_write():
    with pytest.raises(ValueError, match="may not write"):
        risk_provenance.stamp(
            "numeric_causation_estimate",
            RiskProvenance.DERIVED_IDENTIFICATION,
        )
    assert risk_provenance.stamp(
        "numeric_causation_estimate", RiskProvenance.EXOGENOUS,
    ) is RiskProvenance.EXOGENOUS


def test_an_unknown_rule_is_refused_rather_than_answered_with_nothing():
    with pytest.raises(KeyError, match="not a rule that writes"):
        risk_provenance.admissible("backdoor_adjustment_formula")


def test_a_licence_read_back_off_a_foreign_envelope_renders_as_its_token():
    assert risk_provenance.describe("something_this_build_never_heard_of") == (
        "`something_this_build_never_heard_of`"
    )
    assert risk_provenance.describe("exogenous") == RiskProvenance.EXOGENOUS.zh
