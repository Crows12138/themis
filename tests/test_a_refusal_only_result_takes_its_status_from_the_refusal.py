"""Where a refusal is the whole result, the refusal says what became of the query.

Identification returns a result rather than raising, so it is the layer that
has to name a ``status``. Each site named one of its own until #434 — and a
site names what it CATCHES, which is an exception family:
``CounterfactualBoundsError`` reaches two handlers carrying nine species
across four kinds, and the ``outside_language`` both of them wrote is true of
one of the nine. A reader whose data were fine and whose input contradicted
itself was told the question was outside what Themis can express.

Measured at the kernel exit over a full suite run (93 refusals stamped, 47
distinct combinations, 33 of 108 species reached):

    STATUS x KIND            data    graph  request  unbuilt
    needs_investigation        15       16       35       10
    outside_language            .        .        1        6
    structurally_solved         5        .        2        .

Two things in that table decided the shape of the fix.

It is not diagonal, which refutes the hypothesis this cut was registered
with — that ``status`` had become a second copy of ``kind`` (the shape #345
removed). They answer different questions: the kind says whose limitation it
is, the status says what became of the query. Which is also why the map below
is COARSER than the kind, and why the fix is not a new ``ResultStatus``
member for ``request``: one status per kind would be the second copy.

And the ``structurally_solved`` row is the case the map does not cover. Those
results carry an identification answer as well as a refusal, and their status
is about THAT — the data end's refusals all ride such results, which is why
this gate reads the identification layer and not the estimators.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from themis import refusals
from themis.refusals import Kind, Refusal
from themis.types import ResultStatus

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEDULER = ROOT / "themis" / "runtime" / "scheduler.py"


def _refusal_only_results(tree: ast.AST) -> list[tuple[int, bool]]:
    """Every ``QueryResult`` whose only content is a refusal, and whether it
    names its own status.

    Only content, read as: it carries ``estimator_failure`` and no field that
    would be an answer or a gap. A result that carries both is the case the
    map does not cover, and this scan must not claim it.
    """
    answers = {"missing_information", "investigation_requests", "numeric_result",
               "structural_result", "bounds_result", "extensions", "derivation"}
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and getattr(node.func, "id", "") == "QueryResult"):
            continue
        given = {kw.arg for kw in node.keywords if kw.arg}
        if "estimator_failure" not in given or given & answers:
            continue
        status = next((kw.value for kw in node.keywords if kw.arg == "status"),
                      None)
        names_its_own = any(
            getattr(n, "id", "") == "ResultStatus" for n in ast.walk(status)
        ) if status is not None else False
        found.append((node.lineno, names_its_own))
    return found


def test_the_map_is_total():
    """Every kind answers, because every refusal that is a whole result has
    to be given a status and there is nowhere else to get one."""
    assert {k: k.outcome for k in Kind} and all(
        isinstance(k.outcome, ResultStatus) for k in Kind)


def test_the_map_is_coarser_than_the_kind():
    """The property that keeps the status from being the kind again.

    Not a count that happens to hold: an injective map would mean a consumer
    could read either field and get the same partition, and then one of them
    is a copy. The kind is the one that answers "get more data or fix your
    input"; the status answers what became of the query, and several kinds
    end a query the same way.
    """
    assert len({k.outcome for k in Kind}) < len(list(Kind))


def test_the_one_kind_that_ends_a_query_outside_the_language_is_unbuilt():
    """``outside_language`` already told readers "not that the data are short
    — the form of the question has no representation here yet", which is what
    ``unbuilt`` says and what no other kind says."""
    assert {k for k in Kind if k.outcome is ResultStatus.OUTSIDE_LANGUAGE} == {
        Kind.UNBUILT}


@pytest.mark.parametrize("species,expected", [
    # The nine the two counterfactual handlers can reach, by kind.
    (Refusal.COUNTERFACTUAL_CELL_NOT_BINARY, ResultStatus.OUTSIDE_LANGUAGE),
    (Refusal.INTERVENTIONAL_RISK_NOT_IDENTIFIABLE,
     ResultStatus.NEEDS_INVESTIGATION),
    (Refusal.UNDEFINED_CONDITIONING_EVENT, ResultStatus.NEEDS_INVESTIGATION),
    (Refusal.INPUTS_CONTRADICT_BY_CONSISTENCY,
     ResultStatus.NEEDS_INVESTIGATION),
    (Refusal.INVALID_MONOTONICITY, ResultStatus.NEEDS_INVESTIGATION),
])
def test_a_refusal_says_what_became_of_the_query(species, expected):
    assert refusals.outcome({"failure_type": species}) is expected


def test_an_unregistered_species_cannot_be_asked_what_became_of_the_query():
    with pytest.raises(ValueError, match="unregistered failure_type"):
        refusals.outcome({"failure_type": "not_a_species"})


def test_no_site_that_answers_with_a_refusal_alone_names_its_own_status():
    """The gate. It says no to the shape rather than to a list of species,
    because the list is what the two handlers could not see: they named a
    status for the family in front of them and the family grew.
    """
    tree = ast.parse(SCHEDULER.read_text(encoding="utf-8"))
    named = [line for line, own in _refusal_only_results(tree) if own]
    assert not named, [f"themis/runtime/scheduler.py:{line}" for line in named]


def test_the_scan_finds_the_sites_it_is_watching():
    """A gate whose denominator went to zero is a gate that passes by finding
    nothing. These are the results this file exists for, and the count is
    here so that a rewrite which hides them from the scan is loud."""
    assert len(_refusal_only_results(ast.parse(
        SCHEDULER.read_text(encoding="utf-8")))) == 1
