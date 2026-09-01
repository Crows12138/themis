"""What ``themis.verify`` reruns is the family, not a copy of it.

Nineteen result-only doors stand beside :func:`themis.verify`, and nine of
them audit the same artifact it does: an envelope surface standing beside
the answer. ``verify`` reruns those in the course of its own pass, because
their failure mode is one-sided — a surface that under-discloses reads
exactly like one with nothing to disclose, so a caller who called only
``verify`` would never learn of it.

It reran them by reaching for the RULE inside :mod:`themis.verifier`, and
what it meant was "everything that door audits". A door is free to grow a
second rule; a copy of one of its rules does not grow with it. On
2026-07-11 ``verify_data_gap_report`` grew ``verify_type_reconciliation``
and the copy inside ``verify`` did not, so an ``extensions.
type_reconciliation`` block with its observed scale rewritten, its unique
count rewritten, its whole check list emptied, or its mismatch gap deleted
passed the full door and was refused by the narrow one. The divergence
runs the one way nothing outside can notice: every narrow door keeps its
strength and the full door quietly loses some.

``audits.bind_rerun`` is what makes the list the family. Its denominator
is every ``query_result`` row that does not need the program — needing the
program marks an audit of the ANSWER, and ``verify`` is one of those two
and performs the other on its own terms. Each entry is the SINGLE copy of
that surface's audit, and the public door reaches it through the same key,
so the two entrances cannot be audits of different things.

WHAT THIS FILE DOES NOT CHECK. That any of those audits is correct; each
has its own file. What is checked here is that there is one of it.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis import audits, kernel
from themis.verifier.errors import VerificationError


def _nothing(result):
    return None


OWED = sorted(row.name for row in audits.AUDITS
              if row.artifact == audits.Artifact.QUERY_RESULT
              and not row.needs_program)


# =============================================================== the binding


def test_every_envelope_surface_is_bound_to_a_rerun():
    """The list, stated once here so a reader of this file can see it
    without reading the kernel's table."""
    assert sorted(kernel._ENVELOPE_SURFACE_AUDITS) == OWED
    assert len(OWED) == 8, OWED


def test_a_surface_the_full_door_does_not_rerun_is_refused():
    """The counterexample the gate exists for. A surface audited only by
    the door that names it is one a caller has to know to ask for."""
    table = {name: _nothing for name in OWED}
    del table["verify_data_gap_report"]
    with pytest.raises(RuntimeError, match="does not rerun envelope audit"):
        audits.bind_rerun(table)


@pytest.mark.parametrize("name", ["verify", "verify_bounds_results"])
def test_an_audit_of_the_answer_is_not_verifys_to_repeat(name):
    """The other half, on the two rows that need the program. ``verify``
    IS the first and performs the second itself, non-strictly, because a
    bounds method whose verifier does not exist yet is not its business —
    binding either here would claim ``verify`` owes itself a rerun."""
    table = {n: _nothing for n in OWED}
    table[name] = _nothing
    with pytest.raises(RuntimeError, match="not an envelope surface"):
        audits.bind_rerun(table)


def test_an_audit_of_a_standalone_artifact_is_not_verifys_to_repeat():
    """And the rows that are not about an envelope at all. A Markov
    blanket is not a query_result; ``verify`` never sees one."""
    table = {n: _nothing for n in OWED}
    table["verify_markov_blanket"] = _nothing
    with pytest.raises(RuntimeError, match="not an envelope surface"):
        audits.bind_rerun(table)


def test_a_complete_table_is_accepted():
    """The denominator. A gate that refused everything would refuse all
    three forgeries above and mean nothing by it."""
    assert audits.bind_rerun({name: _nothing for name in OWED})


# ================================================= the table is the one copy


@pytest.mark.parametrize("name", OWED)
def test_both_entrances_reach_the_same_object(monkeypatch, name):
    """The structural claim, made behaviourally.

    Replacing a surface's entry makes BOTH the public door and the pass
    inside ``verify`` raise it. That is what "one copy" means and what a
    hand-written call in either place would break — a test that only
    compared two lists of names would still pass on the day the two
    entrances started calling different functions.
    """
    class Sentinel(Exception):
        pass

    def explode(result):
        raise Sentinel(name)

    monkeypatch.setitem(kernel._ENVELOPE_SURFACE_AUDITS, name, explode)

    with pytest.raises(Sentinel):
        getattr(themis, name)(_backdoor_result())
    with pytest.raises(Sentinel):
        themis.verify(_BACKDOOR_PROG, _backdoor_result())


# ======================================================= what got through it


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _program(x_decl):
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", **x_decl},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "query", "id": "q", "query": {"kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True}, "given": []}},
        ],
    }


# Declared continuous, measured binary: the mismatch the pre-flight
# diagnostic exists to find, and the block a reader is shown it in.
_MISMATCH_PROG = _program({"scale": "continuous"})
_BACKDOOR_PROG = _program({"domain": [True, False]})


def _df(n=300, seed=0):
    rng = np.random.default_rng(seed)
    z = rng.integers(0, 2, n)
    x = (rng.random(n) < 0.3 + 0.4 * z).astype(int)
    y = (rng.random(n) < 0.2 + 0.3 * x + 0.2 * z).astype(int)
    return pd.DataFrame({"x": x.astype(bool), "y": y.astype(bool),
                         "z": z.astype(bool)})


@pytest.fixture(scope="module")
def mismatched():
    return themis.estimate(_MISMATCH_PROG, _df(), ci_bootstrap=0)["results"][0]


def _backdoor_result():
    return themis.estimate(
        _BACKDOOR_PROG, _df(), ci_bootstrap=0)["results"][0]


def test_the_honest_answer_passes_both_doors(mismatched):
    """First, or a refused tamper below proves nothing. The block is
    really there and the mismatch really fired."""
    assert mismatched["extensions"]["type_reconciliation"]["checks"]
    themis.verify(_MISMATCH_PROG, mismatched)
    themis.verify_data_gap_report(mismatched)


def _checks(r):
    return r["extensions"]["type_reconciliation"]["checks"]


def _drop_mismatch_gap(r):
    r["data_gap_report"]["gaps"] = [
        g for g in r["data_gap_report"]["gaps"]
        if g.get("kind") != "declared_type_data_mismatch"]


@pytest.mark.parametrize("tamper,expect", [
    (lambda r: _checks(r)[0].__setitem__("observed_scale", "continuous"),
     "recorded observed_scale"),
    (lambda r: _checks(r)[0].__setitem__("n_unique", 400),
     "observed_values has 2 entries"),
    (lambda r: _checks(r)[0].__setitem__("declared_scale", "discrete"),
     "recorded verdict"),
    (lambda r: r["extensions"]["type_reconciliation"].__setitem__("checks", []),
     "no backing type_reconciliation"),
    (_drop_mismatch_gap, "no declared_type_data_mismatch"),
], ids=["observed_scale", "n_unique", "declared_scale", "checks_emptied",
        "gap_deleted"])
def test_a_tampered_reconciliation_no_longer_passes_the_full_door(
        mismatched, tamper, expect):
    """Five edits, each of which a reader would act on: a column that
    disagrees with its declaration reported as agreeing, a two-valued
    column reported as four hundred distinct values, the finding itself
    deleted. All five passed ``themis.verify`` and were refused by
    ``themis.verify_data_gap_report``."""
    r = copy.deepcopy(mismatched)
    tamper(r)
    with pytest.raises(VerificationError, match=expect):
        themis.verify(_MISMATCH_PROG, r)
    with pytest.raises(VerificationError, match=expect):
        themis.verify_data_gap_report(r)


# ==================================================== the boundary, not a gap


def test_a_recovered_ate_is_out_of_the_full_doors_reach_and_stays_bound():
    """Why two rows are in the table and never fire from ``verify``.

    Both recovery estimators produce a result whose status is
    ``numerically_solved`` and whose derivation is absent, and ``verify``
    declines a derivation-less result before reading any block — so the
    narrow door is the audit path for those, exactly as its docstring
    says. That is a fact about what the producer builds, not about the
    audit, which is why the binding holds them anyway: the day such a
    result carries a chain, the full door audits its number without
    anyone remembering to add a call.
    """
    for name in ("verify_selection_recovery_numeric",
                 "verify_missing_data_numeric"):
        assert name in kernel._ENVELOPE_SURFACE_AUDITS

    rng = np.random.default_rng(11)
    n = 40_000
    X = rng.binomial(1, 0.5, n)
    Y = rng.binomial(1, 0.3 + 0.4 * X)
    M = rng.binomial(1, 0.2 + 0.5 * Y)
    W = rng.binomial(1, 0.1 + 0.4 * X + 0.4 * M)
    full = pd.DataFrame({"x": X.astype(bool), "y": Y.astype(bool),
                         "m": M.astype(bool), "w": W.astype(bool)})
    prog = {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": [
                {"kind": "variable", "predicate": p, "domain": [True, False]}
                for p in ("x", "y", "m", "w")
            ] + [
                {"kind": "cause", "from": _atom(a), "to": _atom(b)}
                for a, b in (("x", "y"), ("x", "w"), ("y", "m"), ("m", "w"))
            ] + [
                {"kind": "observation", "atom": _atom("w"), "value": True},
                {"kind": "query", "id": "q", "query": {"kind": "effect",
                    "intervention": {"atom": _atom("x"), "value": True},
                    "target": {"atom": _atom("y"), "value": True},
                    "given": []}},
            ]}
    biased = full[full.w].reset_index(drop=True)
    reference = pd.DataFrame(full)
    res = themis.estimate(
        prog, biased, reference_data=reference)["results"][0]

    assert res["numeric_estimate"]["method"] == "selection_backdoor_recovery"
    assert res.get("derivation") is None
    with pytest.raises(ValueError, match="requires a result with a derivation"):
        themis.verify(prog, res)
    themis.verify_selection_recovery_numeric(res)  # the audit path
