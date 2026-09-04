"""A block that repeats what the program said, held against the program.

Two blocks on a result are not conclusions the kernel reached but copies
of the caller's own words. ``llm_proposed_review`` gathers every edge and
prior a language model proposed, so a reader can accept or reject them
before trusting the number. ``ambiguities`` is the program's own
side-channel of unresolved naming questions, filtered to the query in
hand. Neither is derived from anything, which is why each can be
re-derived in full — and why nothing having done so was worth a module.

What a copy is worth is what it costs to edit. A review with one edge
removed tells a reader a person drew a graph a language model drew. An
ambiguity nobody declared is worse than noise, because the gap report
READS this block: an entry saying ``measurement_quality`` SUPPRESSES the
measurement-error concern — severity important, the regression-dilution
warning — on the reasoning that the upstream model already named it. One
invented line deletes a warning and supplies the excuse for its absence
in the same stroke.

Both rules are total, so both directions are checked. A copy that is
missing is not a copy that agrees: the program declaring something and
the block being absent is the failure these surfaces exist to prevent,
and it is the one that leaves no trace on the page.

The comparison is order-insensitive because order is not a claim either
block makes — a reader is shown a list of what was proposed, not a
sequence. Every edit that can be made to the content survives sorting:
an entry added, removed, re-pointed, or relabelled all change the
multiset.

**Independence pin:** this module MUST NOT import from ``themis.output``
or any producer-side module. Both collection criteria and both rendering
forms are re-transcribed here, so a bug in the generator cannot mask
itself in the audit. It also reads the program as the JSON the caller
submitted rather than the typed ``Program`` the producer walks, which is
a second way the two can disagree: a serialisation that dropped an
annotation would be invisible to a check written over the same objects.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from .errors import VerificationError


def _atom_text(atom: dict) -> str:
    """An atom as the review surface spells it. Independent twin of the
    producer's ``_atom_repr``: predicate, then its argument names in
    parentheses, and the bare predicate when there are none."""
    args = ",".join(str(a.get("name")) for a in (atom.get("args") or ()))
    predicate = str(atom.get("predicate"))
    return f"{predicate}({args})" if args else predicate


def _valued(va: dict) -> str:
    return f"{_atom_text(va.get('atom') or {})}={va.get('value')}"


def _prior_key(stmt: dict) -> str:
    """A probability statement as the review surface spells it.

    The statement's own surface rather than a canonical key: what the
    reader is being asked to accept is the prior as it was written."""
    body = _valued(stmt.get("target") or {})
    given = stmt.get("given") or ()
    if given:
        body = body + "|" + ",".join(_valued(g) for g in given)
    population = stmt.get("population")
    prefix = "P" if population is None else f"P_{population}"
    return f"{prefix}({body})"


def _rederive_review(program: dict) -> dict | None:
    """Every LLM-proposed element of a program, collected again.

    An edge counts when its annotation's source names a language model —
    substring, case-insensitively, because the convention is
    ``llm_proposal`` and the field is free text. A prior counts when its
    provenance is exactly ``llm_prior``. Evidence-sourced edges are not
    LLM-proposed and are left out.
    """
    edges: list[dict] = []
    priors: list[dict] = []
    for stmt in program.get("statements") or ():
        if not isinstance(stmt, dict):
            continue
        kind = stmt.get("kind")
        if kind == "cause":
            source = (stmt.get("annotations") or {}).get("source") or ""
            if "llm" not in str(source).lower():
                continue
            edges.append({
                "from": _atom_text(stmt.get("from") or {}),
                "to": _atom_text(stmt.get("to") or {}),
                "source": source,
            })
        elif kind == "probability":
            if stmt.get("provenance") != "llm_prior":
                continue
            reason = (stmt.get("annotations") or {}).get("source") or ""
            entry: dict = {
                "key": _prior_key(stmt),
                "value": stmt.get("value"),
                "reason": reason,
            }
            if stmt.get("population") is not None:
                entry["population"] = stmt.get("population")
            priors.append(entry)
    if not edges and not priors:
        return None
    return {"edges": edges, "probabilities": priors}


def _canonical(rows) -> list[str]:
    return sorted(json.dumps(row, sort_keys=True, ensure_ascii=False)
                  for row in rows or ())


def verify_llm_proposed_review(block, program: dict) -> None:
    """Audit ``extensions.llm_proposed_review`` against the program.

    The block is the surface on which a reader decides whether to trust a
    graph, so both halves of the disagreement matter: an edge the program
    does not carry, and an edge the program carries that the block does
    not name. Silence is the dangerous half — an LLM-proposed edge that
    never reaches this surface is indistinguishable from one a person
    drew.

    Accepts a result with no such block when the program proposes
    nothing, which is the same fact stated from the other side.
    """
    expected = _rederive_review(program)
    if expected is None:
        if block is None:
            return
        raise VerificationError(
            "llm_proposed_review is present on a result whose program "
            "proposes no LLM edge and no LLM prior; a review of nothing "
            "asks a reader to accept something the program never said",
            rule="llm_proposed_review_check",
        )
    if block is None:
        raise VerificationError(
            f"the program carries {len(expected['edges'])} LLM-proposed "
            f"edge(s) and {len(expected['probabilities'])} LLM prior(s) and "
            "the result carries no llm_proposed_review; an edge that never "
            "reaches that surface reads as one a person drew",
            rule="llm_proposed_review_check",
        )
    if not isinstance(block, dict):
        raise VerificationError(
            f"llm_proposed_review is a {type(block).__name__}, not an "
            "object with edges and probabilities",
            rule="llm_proposed_review_check",
        )
    for field in ("edges", "probabilities"):
        got = _canonical(block.get(field))
        want = _canonical(expected[field])
        if got != want:
            raise VerificationError(
                f"llm_proposed_review.{field} is not what the program "
                f"proposes: the block says {got} and the program says "
                f"{want}",
                rule="llm_proposed_review_check",
            )


def _rederive_ambiguities(program: dict, query_id) -> list[dict]:
    """The program's declared ambiguities that bear on one query.

    An entry naming no query is a program-wide concern and reaches every
    result; one naming a query reaches that result only. Entries that are
    not objects carry no ``query_id`` to read and are not copied.
    """
    declared = (program.get("extensions") or {}).get("ambiguities") or ()
    return [a for a in declared
            if isinstance(a, dict)
            and a.get("query_id") in (None, query_id)]


# =================================== the answer says which question it answers


def _predicate(node) -> str | None:
    if isinstance(node, dict):
        if "predicate" in node:
            return str(node["predicate"])
        inner = node.get("atom")
        if isinstance(inner, dict) and "predicate" in inner:
            return str(inner["predicate"])
    return None


def _predicates(nodes) -> list[str] | None:
    if not isinstance(nodes, list):
        return None
    out = [_predicate(n) for n in nodes]
    return None if any(p is None for p in out) else [p for p in out if p]


#: How each kind of question names the variables an answer claims to be
#: about. Written per kind because the question is spelled differently in
#: each — a causation query has a cause and an effect where an effect query
#: has an intervention and a target — and a reading invented for one kind
#: and applied to another is how an answer would be held to the wrong
#: question. A kind absent here supplies nothing, and the leaves stay
#: unheld rather than held to a guess; the sweep gate is what keeps that
#: visible.
_QUESTION_READS: dict[str, dict[str, Callable[[dict], Any]]] = {
    "effect": {
        "treatment": lambda q: _predicate(q.get("intervention")),
        "outcome": lambda q: _predicate(q.get("target")),
        "mediator": lambda q: _predicate(q.get("mediator")),
        "mediators": lambda q: _predicates(q.get("mediators")),
    },
    "causation": {
        "treatment": lambda q: _predicate(q.get("cause")),
        "outcome": lambda q: _predicate(q.get("effect")),
    },
    "counterfactual": {
        "treatment": lambda q: _predicate(q.get("counterfactual_intervention")),
        "outcome": lambda q: _predicate(q.get("counterfactual_target")),
    },
    "proximal_effect": {
        "treatment": lambda q: _predicate(q.get("treatment")),
        "outcome": lambda q: _predicate(q.get("outcome")),
        "treatment_proxy": lambda q: _predicates(q.get("treatment_proxy")),
        "outcome_proxy": lambda q: _predicates(q.get("outcome_proxy")),
    },
}


def query_of(program: dict, query_id) -> dict | None:
    """The query a result answers, as the caller wrote it.

    Public within the package because more than one rule needs the question
    itself rather than a reading of it: this module holds the answer's
    variable NAMES to it, and ``frame_rules`` holds a
    correction's target VALUE to the same statement. Two copies of a lookup
    are two places for it to go stale.
    """
    for stmt in program.get("statements") or ():
        if not isinstance(stmt, dict):
            continue
        if stmt.get("kind") == "query" and stmt.get("id") == query_id:
            q = stmt.get("query")
            return q if isinstance(q, dict) else None
    return None


def verify_answer_names_its_kind(result, program: dict) -> None:
    """WHICH question this answer says it is an answer to.

    The rule below holds the variables an answer names; this holds the
    word for the question itself. It went unheld for the reason that
    makes it worth holding: ``verify`` routes on it. Which audits an
    answer meets is chosen by ``result["query_kind"]``, so the field that
    decides who checks the answer was the one field no checker was ever
    selected to look at — a premise of the audit rather than a claim in
    it.

    The record it is held to is the program, which is the strongest one
    there is: an answer may not edit the question it was asked.
    """
    if not isinstance(result, dict):
        return
    shown = result.get("query_kind")
    if not isinstance(shown, str):
        return
    query = query_of(program, result.get("query_id"))
    if not isinstance(query, dict):
        return
    asked = query.get("kind")
    if not isinstance(asked, str) or shown == asked:
        return
    raise VerificationError(
        f"the answer says it answers a {shown!r} question and the question "
        f"asked was {asked!r}; every claim beside it was then audited as "
        f"the wrong kind of answer",
        step_index=None, rule="answer_kind_check",
    )


def verify_answer_names_its_question(estimate, program: dict, *, query_id
                                     ) -> None:
    """The variables an answer says it is about, held to the question asked.

    ``numeric_estimate`` opens with what a reader reads first: the effect
    of THIS on THAT, through THIS mediator, using THESE proxies. No
    derivation step records any of it, so nothing re-derived it and the
    names could be edited freely — and an edited name does not change a
    single number, it changes which question the number is an answer to,
    which is the most complete way to be wrong while looking right.

    These names come from the query, not from the chain, so this is where
    the audit belongs rather than beside the record the numbers were
    checked from.

    A sequence spelled as one field — the longitudinal path writes its
    whole treatment course into ``treatment`` — is a different estimand
    from the one the query's single atom names, and is declined rather
    than compared. Declining leaves the leaf unheld, which the sweep
    reports; comparing would refuse an honest answer.
    """
    if not isinstance(estimate, dict):
        return
    query = query_of(program, query_id)
    if query is None:
        return
    reads = _QUESTION_READS.get(str(query.get("kind")))
    if not reads:
        return
    for name, read in reads.items():
        if name not in estimate:
            continue
        shown = estimate[name]
        if isinstance(shown, str) and "," in shown:
            continue
        asked = read(query)
        if asked is None:
            continue
        if isinstance(shown, list):
            shown = [str(s) for s in shown]
        elif shown is not None:
            shown = str(shown)
        if shown != asked:
            raise VerificationError(
                f"the answer says its {name} is {shown!r} and the question "
                f"asked about {asked!r}; every number beside it is then an "
                f"answer to a question nobody asked",
                rule="answer_names_its_question",
            )


def verify_ambiguity_copy(block, program: dict, *, query_id) -> None:
    """Audit ``extensions.ambiguities`` against the program's side channel.

    The copy is the program's own words, filtered to this query, and the
    filter is the whole of the producer's freedom — so the audit is the
    whole of the block. An entry the program never declared is a licence
    the gap report honours; a declared one dropped is a concern the reader
    was told about and does not see.
    """
    expected = _rederive_ambiguities(program, query_id)
    if not expected:
        if block is None:
            return
        raise VerificationError(
            f"result for query {query_id!r} carries an ambiguities block "
            "and the program declares none that bear on this query; the "
            "gap report reads this block, so an entry nobody declared can "
            "be the stated reason a warning is missing",
            rule="ambiguity_copy_check",
        )
    if block is None:
        raise VerificationError(
            f"the program declares {len(expected)} ambiguit(ies) bearing on "
            f"query {query_id!r} and the result copies none of them across; "
            "a concern the caller raised reads as one nobody raised",
            rule="ambiguity_copy_check",
        )
    got, want = _canonical(block), _canonical(expected)
    if got != want:
        raise VerificationError(
            f"extensions.ambiguities for query {query_id!r} is not what the "
            f"program declares: the block says {got} and the program says "
            f"{want}",
            rule="ambiguity_copy_check",
        )
