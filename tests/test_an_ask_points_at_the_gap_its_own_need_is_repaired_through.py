"""An ask names a species. Which species was settled and never checked.

An investigation item tells a reader to go and supply something, and its
``gap`` says which of this answer's gaps that would close. One rule holds
that reference: the species must be one the report carries. That is all a
reference to a list can be asked on its own — an ask pointed at another
gap the report really does carry sends a reader after something for a
problem that IS on the envelope, and no reading of the report alone tells
that from the truth.

It was never on its own. An item also says what was NEEDED, and
:class:`themis.gaps.Need` declares the channel that repairs each need on
the member itself — ``Need.gap`` — with its own docstring giving the
reason: "so a site cannot file a need under a kind that contradicts it".
That constrains the producer. Nothing held the ENVELOPE to it, so a
relation the contract states was a relation no answer had to honour.

MEASURED, both which forgeries are reachable and who refuses them. The
item schema admits ten species, so most cross-species bends are refused by
validation before any rule reads them; 192 are reachable on the corpus.
102 of those are refused by the sentence below and 90 by the rule holding
an item against its ``missing_information`` row — which is the pairing
that exists where an item HAS a second record, and is silent for every
framing ask and some of the rest. None went unrefused. The two together
are the space, and neither is the other.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
from themis import gaps
from themis.verifier.errors import VerificationError
from themis.verifier.investigation_rules import (
    _check_it_names_the_species_its_need_raises,
)

CORPUS = pathlib.Path(__file__).resolve().parent / "fixtures" / (
    "answer_shapes.json")
SCHEMA = pathlib.Path(__file__).resolve().parents[1] / "themis" / (
    "schemas") / "query_result.schema.json"


@pytest.fixture(scope="module")
def corpus() -> dict:
    return json.loads(CORPUS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def namable() -> set[str]:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    return set(schema["$defs"]["investigationItem"]["properties"]["gap"][
        "enum"])


def _results(envelope):
    return envelope.get("results") or [envelope]


def _items(result):
    for request_index, request in enumerate(
            result.get("investigation_requests") or []):
        for item_index, item in enumerate(request.get("items") or []):
            yield request_index, item_index, item


# --- the relation is the contract's, read off the member ------------------


def test_every_need_declares_the_one_species_that_repairs_it():
    """The premise, read from the enum rather than gathered from the
    corpus: a need this build has never raised is held to the same
    sentence as the ones it raises daily."""
    needs = list(gaps.Need)
    assert needs, "no needs declared; this check is measuring nothing"
    for need in needs:
        assert isinstance(need.gap, gaps.GapKind)
    assert gaps.BY_NAME["framing_fields_unfilled"].gap == (
        gaps.GapKind.AMBIGUOUS_VARIABLE_DEFINITION)


def test_one_declared_need_names_a_species_no_ask_may_point_at(namable):
    """A fact this check turned up rather than closed, kept where it can
    be argued with. The item schema admits ten species and every need's
    channel is one of them but one: ``the_penalty_is_doing_the_work`` is
    repaired through ``regularisation_is_moving_the_answer``, which an
    item may not name. So an ask raised for that need could not point at
    its own gap and stay valid. It raises none today; if it ever does, one
    of the two declarations has to move, and this line says which two."""
    outside = sorted(need.value for need in gaps.Need
                     if need.gap.value not in namable)
    assert outside == ["the_penalty_is_doing_the_work"]


# --- the honest side, on every ask the corpus carries ---------------------


def test_every_ask_in_the_corpus_points_at_its_own_channel(corpus):
    """What a refusing rule has to earn first. Every item on every row,
    against the contract's relation — a false refusal here would be worse
    than the hole it closes."""
    checked = 0
    for name, row in sorted(corpus.items()):
        for result in _results(row["result"]):
            for _ri, _ii, item in _items(result):
                if not isinstance(item.get("need"), str):
                    continue
                _check_it_names_the_species_its_need_raises("where", item)
                checked += 1
    assert checked > 300, checked


# --- and the ask pointed at another gap the report really has -------------


def test_an_ask_pointed_at_another_real_gap_is_refused(corpus):
    """The forgery this closes, and the one the reference check cannot
    see: the species named IS on the envelope, so the rule asking whether
    the report carries it is satisfied, and the reader is still sent to
    collect something that would not close this ask."""
    row = corpus["iv_2sls_overid"]
    forged = copy.deepcopy(row["result"])
    bent = None
    for result in _results(forged):
        for ri, ii, item in _items(result):
            species = {gap.get("kind")
                       for gap in (result.get("data_gap_report")
                                   or {}).get("gaps") or []}
            other = next(s for s in sorted(species)
                         if s != item.get("gap")
                         and s == "ambiguous_variable_definition")
            result["investigation_requests"][ri]["items"][ii]["gap"] = other
            bent = (item.get("need"), other)
            break
        break
    assert bent

    with pytest.raises(VerificationError) as caught:
        themis.verify(row["program"], forged)
    complaint = str(caught.value)
    assert "is repaired through" in complaint
    assert bent[0] in complaint and bent[1] in complaint
    with pytest.raises(VerificationError):
        themis.verify_answer_claims(row["program"], forged)


def test_the_species_an_item_names_is_still_held_to_the_report_as_well(corpus):
    """The other rule, unchanged and still needed. A species this answer
    never reported is refused whether or not it is the ask's own channel,
    and that is a different sentence about a different mistake."""
    row = corpus["aipw"]
    forged = copy.deepcopy(row["result"])
    for result in _results(forged):
        for ri, ii, _item in _items(result):
            result["investigation_requests"][ri]["items"][ii]["gap"] = (
                "missing_distribution")
            break
        break
    with pytest.raises(VerificationError) as caught:
        themis.verify(row["program"], forged)
    assert "does not carry one" in str(caught.value)


def test_an_item_saying_nothing_about_what_it_needed_is_not_this_rules_business():
    """Silence rather than refusal where there is no need to read: an item
    with no ``need`` is held by the rules that hold items, and inventing a
    channel for it here would be this rule answering a question nobody
    asked it."""
    _check_it_names_the_species_its_need_raises(
        "where", {"gap": "missing_distribution"})
    _check_it_names_the_species_its_need_raises(
        "where", {"need": "theta_entry_missing"})
    _check_it_names_the_species_its_need_raises(
        "where", {"need": "not_a_need_this_build_has",
                  "gap": "missing_distribution"})
