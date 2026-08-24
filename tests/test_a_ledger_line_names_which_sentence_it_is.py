"""#395 sixth cut — a ledger line carries which sentence it is, not the text.

``assumption_ledger.assumptions[].claim`` was the last large body of prose the
kernel wrote onto an envelope. Its shape is what made it prose: three fields
on one line, two of them facts (a layer is a vocabulary, ``testable`` is a
boolean) and the third a rendered sentence — so ``classify_assumption`` took
the reader's language, and the kernel decided who was reading in order to fill
one field of four.

What the field holds now is a LIST of statements, because three channels write
it and one of them contributes as many as its occasion had: the glossary words
the assumptions an estimator declares, a gap's own statements word an
unverified edge, and a number the model supplied words itself.

The counterexamples below are the three shapes this replaced, and each is
confirmed to fail on its OWN error rather than on whatever the validator
happens to reach first.
"""
from __future__ import annotations

import pytest

from themis import gaps, language
from themis.input.syntactic_validator import validator_for
from themis.output import assumption_glossary
from themis.output.assumption_glossary import (
    CLAIM,
    CLAIMS,
    _PREFIX,
    _RULES,
    classify_assumption,
)
from themis.output.result_orchestrator import Prior, to_dict
from themis.types import QueryKind, QueryResult, ResultStatus


def _validator():
    return validator_for("query_result.schema.json")


def _line(claim, **over):
    """One ledger line, with everything but the claim held fixed."""
    line = {"id": "consistency_of_potential_outcomes", "claim": claim,
            "layer": "identification", "severity": "invalidating",
            "provenance": "inherent", "testable": False}
    line.update(over)
    return line


def _envelope(*lines):
    return to_dict(QueryResult(
        status=ResultStatus.NEEDS_INVESTIGATION,
        query_kind=QueryKind.EFFECT,
        extensions={"assumption_ledger": {"assumptions": list(lines)}},
    ))


#: One statement from each of the three channels that write this field.
def _from_the_glossary():
    return classify_assumption("consistency_of_potential_outcomes")["claim"][0]


def _from_a_gap():
    return language.restate(
        {"sentence": "the_edge_was_learned_by_discovery",
         "said": {"edge": "x → y", "algorithm": "pc"}},
        gaps.DESCRIBED, "sentence")


def _from_the_model():
    return language.state(Prior.A_COMMONSENSE_PRIOR,
                          key="p_y_given_x", value=0.3)


# ------------------------------------------------------- the positive arm

def test_a_line_from_every_channel_passes_the_contract():
    """Three authors, one field, and no author knowing about the others."""
    doc = _envelope(
        _line([_from_the_glossary()]),
        _line([_from_a_gap()], id="edge_x_y", provenance="discovery",
              layer="structural_edge", testable=True),
        _line([_from_the_model()], id="p_y_given_x", provenance="llm_prior",
              layer="parameter", severity="distorting", testable=True),
    )
    _validator().validate(doc)


@pytest.mark.parametrize("statement", [
    pytest.param(_from_the_glossary, id="glossary"),
    pytest.param(_from_a_gap, id="gap"),
    pytest.param(_from_the_model, id="model"),
])
def test_every_channel_reaches_a_reader_in_every_language(statement):
    """A statement is only a statement if some table answers to its name.

    Asked of each language this build writes rather than the one it answers
    in: English is the one able to drift unnoticed, because no reader can be
    handed it yet.
    """
    one = statement()
    assert one["vocabulary"] in language.VOCABULARIES
    for lang in sorted(language.written()):
        said = language.spoke(one, lang)
        assert said and one["token"] not in said, (lang, said)


def test_the_line_is_the_statements_joined_where_the_reader_is():
    """Several sentences on one line, with this language's gap between them.

    Chinese needs none and English does, so a paragraph joined in the kernel
    read correctly in the only language anybody was answered in.
    """
    claim = [_from_the_glossary(), _from_the_model()]
    assert language.spoken(claim, "zh") == "".join(
        language.spoke(one, "zh") for one in claim)
    assert language.spoken(claim, "en") == " ".join(
        language.spoke(one, "en") for one in claim)


# ---------------------------------------------------- the three it refuses

def test_the_envelope_refuses_a_claim_written_as_text():
    """The shape this replaced: the sentence itself, in one language."""
    with pytest.raises(Exception) as caught:
        _validator().validate(_envelope(_line("处理的取值就是它被指派的取值")))
    assert "is not of type 'array'" in str(caught.value)


def test_the_envelope_refuses_a_line_with_nothing_to_say():
    """An empty list is what an empty string was, one shape along."""
    with pytest.raises(Exception) as caught:
        _validator().validate(_envelope(_line([])))
    assert "should be non-empty" in str(caught.value)


def test_the_envelope_refuses_a_statement_with_no_token():
    """Facts and no sentence to put them in: nothing a reader can be handed."""
    with pytest.raises(Exception) as caught:
        _validator().validate(_envelope(_line(
            [{"vocabulary": CLAIM, "said": {"suffix": "age"}}])))
    assert "'token' is a required property" in str(caught.value)


def test_each_refusal_is_for_its_own_reason():
    """The counterexamples are not circular.

    Three shapes, three errors, no two alike — which is what says the gate
    above is reading the thing it claims to and not tripping over some
    unrelated omission the fixture shares.
    """
    reasons = set()
    for claim in ("处理的取值就是它被指派的取值", [],
                  [{"vocabulary": CLAIM, "said": {"suffix": "age"}}]):
        with pytest.raises(Exception) as caught:
            _validator().validate(_envelope(_line(claim)))
        reasons.add(str(caught.value).splitlines()[0])
    assert len(reasons) == 3, reasons


# ------------------------------------------------------ the table's own shape

def test_every_row_of_both_tables_is_reachable_by_a_token():
    """The vocabulary is the two tables plus the sentences only a rule picks.

    Counted rather than asserted row by row: a collision between an id and a
    prefix would silently drop one of them, and a dropped row is a sentence
    the reader is never handed with nothing saying so.
    """
    assert len(CLAIMS) == len(assumption_glossary._EXACT) + len(_PREFIX) + 2


def test_a_rule_only_ever_names_a_row_that_exists():
    """A rule returns a TOKEN, and a token no table carries is a hole.

    Exercised rather than read: which token a rule returns depends on
    whether the tail it was handed reads, and both halves of that are what
    the fallbacks exist for.
    """
    tails = ("non_decreasing_in_treatment", "non_increasing", "",
             "0.01_on_37_units", "z_on_y", "wibble")
    for prefix, rule in _RULES.items():
        for tail in tails:
            token, _slots = rule(prefix, tail)
            assert token in CLAIMS, (prefix, tail, token)


def test_a_rule_belongs_to_a_prefix_the_table_declares():
    """How an id is read is keyed on the row that says what it MEANS."""
    assert set(_RULES) <= {p for p, _row in _PREFIX}
