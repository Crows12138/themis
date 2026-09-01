"""Two blocks say back what the caller said, and nobody compared them.

``llm_proposed_review`` is every edge and prior a language model proposed,
gathered so a reader can accept or reject them before trusting the number.
``ambiguities`` is the program's own side-channel of unresolved naming
questions, filtered to the query in hand. Neither is derived from
anything: both are copies, both re-derivable in full from a document
``themis.verify`` already holds.

Ten edits passed the full door. The review could lose its only LLM edge,
gain one the program never carried, have its edge re-pointed at another
pair or its source relabelled ``pubmed``, or be deleted whole — and a
reader would decide whether to trust the graph on the strength of it. The
ambiguity copy is worse than cosmetic, because the gap report READS it:
an entry saying ``measurement_quality`` suppresses the measurement-error
concern, severity important, the regression-dilution warning. One invented
line deletes a warning and supplies the excuse for its absence.

Both directions, in both blocks. A copy that is missing is not a copy that
agrees — the program declaring something and the block staying silent is
the failure these surfaces exist to prevent, and the one that leaves no
mark on the page.

WHY THE NARROW DOORS STILL ACCEPT. ``verify_assumption_ledger`` and
``verify_data_gap_report`` are result-only by contract, and neither block
can be checked against anything the result carries. This is the one class
of claim where the full door is properly stronger: it holds the program.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.verifier import verify_ambiguity_copy, verify_llm_proposed_review
from themis.verifier.errors import VerificationError


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _query(qid, x, y):
    return {"kind": "query", "id": qid, "query": {"kind": "effect",
            "intervention": {"atom": _atom(x), "value": True},
            "target": {"atom": _atom(y), "value": True}, "given": []}}


def _program(*, llm_edge=False, ambiguities=None, extra_queries=()):
    zy = {"kind": "cause", "from": _atom("z"), "to": _atom("y")}
    if llm_edge:
        zy["annotations"] = {"source": "llm_proposal"}
    prog = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
            zy,
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            _query("q", "x", "y"),
            *extra_queries,
        ],
    }
    if ambiguities is not None:
        prog["extensions"] = {"ambiguities": ambiguities}
    return prog


def _df(n=300, seed=0):
    rng = np.random.default_rng(seed)
    z = rng.integers(0, 2, n)
    x = (rng.random(n) < 0.3 + 0.4 * z).astype(int)
    y = (rng.random(n) < 0.2 + 0.3 * x + 0.2 * z).astype(int)
    return pd.DataFrame({"x": x.astype(bool), "y": y.astype(bool),
                         "z": z.astype(bool)})


DECLARED = [
    {"kind": "mediator_choice", "note": "which mediator counts"},
    {"kind": "reciprocal_causation", "note": "q2 only", "query_id": "q2"},
]

RICH_PROG = _program(llm_edge=True, ambiguities=DECLARED,
                     extra_queries=(_query("q2", "z", "y"),))
BARE_PROG = _program()


@pytest.fixture(scope="module")
def rich():
    return themis.estimate(RICH_PROG, _df(), ci_bootstrap=0)["results"]


@pytest.fixture(scope="module")
def bare():
    return themis.estimate(BARE_PROG, _df(), ci_bootstrap=0)["results"][0]


# ================================================== the honest answers first


def test_the_honest_answers_pass(rich, bare):
    """First, or every refusal below proves nothing. Both blocks are
    really there, and the query-targeted entry really reaches only its
    own query."""
    q, q2 = rich
    assert q["extensions"]["llm_proposed_review"]["edges"]
    assert q["extensions"]["ambiguities"] == [DECLARED[0]]
    assert q2["extensions"]["ambiguities"] == DECLARED
    themis.verify(RICH_PROG, q)
    themis.verify(RICH_PROG, q2)

    assert "llm_proposed_review" not in (bare.get("extensions") or {})
    assert "ambiguities" not in (bare.get("extensions") or {})
    themis.verify(BARE_PROG, bare)


# ============================================ the surface a graph is trusted on


def _review(r):
    return r["extensions"]["llm_proposed_review"]


@pytest.mark.parametrize("tamper,expect", [
    (lambda r: _review(r).__setitem__("edges", []),
     "not what the program proposes"),
    (lambda r: r["extensions"].pop("llm_proposed_review"),
     "carries no llm_proposed_review"),
    (lambda r: _review(r)["edges"][0].update({"from": "x(me)", "to": "z(me)"}),
     "not what the program proposes"),
    (lambda r: _review(r)["edges"][0].__setitem__("source", "pubmed"),
     "not what the program proposes"),
    (lambda r: _review(r)["edges"].append(
        {"from": "x(me)", "to": "y(me)", "source": "llm_proposal"}),
     "not what the program proposes"),
], ids=["edge_deleted", "block_deleted", "re_pointed", "relabelled_evidence",
        "edge_invented"])
def test_a_review_that_is_not_what_the_program_proposes(rich, tamper, expect):
    r = copy.deepcopy(rich[0])
    tamper(r)
    with pytest.raises(VerificationError, match=expect):
        themis.verify(RICH_PROG, r)


def test_a_review_on_a_program_that_proposed_nothing(bare):
    """The other side of the same claim. A review of nothing asks a
    reader to accept something the program never said."""
    r = copy.deepcopy(bare)
    r.setdefault("extensions", {})["llm_proposed_review"] = {
        "edges": [{"from": "z(me)", "to": "y(me)", "source": "llm_proposal"}],
        "probabilities": []}
    with pytest.raises(VerificationError, match="proposes no LLM edge"):
        themis.verify(BARE_PROG, r)


def test_a_prior_is_collected_and_spelled_the_way_a_reader_sees_it():
    """The other half of the review, and the half the estimate path does
    not produce here. A prior counts by its provenance being exactly
    ``llm_prior``, and what a reader is asked to accept is the statement
    as it was written — so the key is the statement's own surface, not a
    canonicalised one."""
    prog = _program()
    prog["statements"].append({
        "kind": "probability",
        "target": {"atom": _atom("y"), "value": True},
        "given": [{"atom": _atom("x"), "value": True}],
        "value": 0.42,
        "provenance": "llm_prior",
        "annotations": {"source": "guessed by a language model"},
    })
    review = {"edges": [], "probabilities": [
        {"key": "P(y(me)=True|x(me)=True)", "value": 0.42,
         "reason": "guessed by a language model"}]}
    verify_llm_proposed_review(review, prog)

    wrong = copy.deepcopy(review)
    wrong["probabilities"][0]["value"] = 0.43
    with pytest.raises(VerificationError, match="probabilities"):
        verify_llm_proposed_review(wrong, prog)

    dropped = {"edges": [], "probabilities": []}
    with pytest.raises(VerificationError, match="probabilities"):
        verify_llm_proposed_review(dropped, prog)


def test_an_edge_from_evidence_is_not_an_llm_proposal():
    """The denominator of the collection rule. A check that gathered
    every annotated edge would refuse an honest program that cites a
    paper, and would say nothing by refusing the forgeries above."""
    prog = _program()
    prog["statements"][4]["annotations"] = {"source": "pubmed:12345"}
    verify_llm_proposed_review(None, prog)


# ========================================= the copy the gap report acts on


def _set_amb(r, value):
    ext = dict(r.get("extensions") or {})
    if value is None:
        ext.pop("ambiguities", None)
    else:
        ext["ambiguities"] = value
    r["extensions"] = ext


@pytest.mark.parametrize("tamper,expect", [
    (lambda r: _set_amb(r, [{"kind": "measurement_quality"}]),
     "not what the program declares"),
    (lambda r: _set_amb(r, None), "copies none of them across"),
    (lambda r: _set_amb(r, DECLARED), "not what the program declares"),
    (lambda r: _set_amb(r, [{"kind": "reciprocal_causation",
                             "note": "which mediator counts"}]),
     "not what the program declares"),
    (lambda r: _set_amb(r, [{"kind": "mediator_choice", "note": "rewritten"}]),
     "not what the program declares"),
], ids=["invented", "deleted", "another_querys_entry", "kind_rewritten",
        "note_rewritten"])
def test_an_ambiguity_copy_that_is_not_what_the_program_declares(
        rich, tamper, expect):
    """The third case is the one a set comparison alone would miss: the
    entry is real, the program did declare it, and it belongs to the
    other query. Targeting is the whole of what the producer decides
    here, so it is the whole of what there is to check."""
    r = copy.deepcopy(rich[0])
    tamper(r)
    with pytest.raises(VerificationError, match=expect):
        themis.verify(RICH_PROG, r)


def test_an_ambiguity_on_a_program_that_declared_none(bare):
    """The forgery the gap report would honour: an entry nobody declared,
    of the kind that suppresses the measurement-error concern."""
    r = copy.deepcopy(bare)
    r.setdefault("extensions", {})["ambiguities"] = [
        {"kind": "measurement_quality", "note": "invented"}]
    with pytest.raises(VerificationError, match="the program declares none"):
        themis.verify(BARE_PROG, r)


def test_an_entry_that_is_not_an_object_is_not_copied():
    """The producer skips what carries no query_id to read. A verifier
    that copied it instead would refuse every honest result of a program
    whose side-channel holds a stray string."""
    prog = _program(ambiguities=["a bare string", {"kind": "mediator_choice"}])
    verify_ambiguity_copy([{"kind": "mediator_choice"}], prog, query_id="q")
