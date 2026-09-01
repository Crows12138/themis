"""A re-derivation ran because of where its author was standing.

Fifteen rules re-derive a number the derivation chain cannot reach — a
confusion-matrix inversion, a SIMEX ladder, an E-value, a set of per-corner
risks. Each was guarded by a sentence about the estimate ("this method",
"this block is present") and each stood inside one branch of the kind
dispatch, so what it actually covered was that branch.

Measured end to end before this was written: ``mediation_logit_imai``
reports its finding FRAGILE — an unmeasured confounder of risk ratio 1.58
would explain it away. Relabel the block ``very_robust`` with an E-value of
99 and ``themis.verify`` accepted it, because a mediation result is
``structurally_solved`` and takes a branch the E-value rule was never put
on. Both mediation shapes accepted four or five such forgeries; the other
fifteen shapes carrying the same block refused every one.

The repository had already met this once: ``verify_mediation_numeric`` was
hand-copied onto a second branch when somebody noticed the same blocks
arriving by a second route. A third route would have needed a third copy,
and nothing would have said so.

So the tests here are of two kinds. The forgeries are asked of EVERY shape
that carries the block, because "which shapes are covered" was the whole
defect and a test that picks one shape reproduces it. The structural gates
hold the table's two edges: that it is the only way a rule is called, and
that every selector in it names something the schema declares — a renamed
block would otherwise leave a row that matches nothing, and a rule that
matches nothing is indistinguishable from a rule that found nothing wrong.
"""
from __future__ import annotations

import ast
import copy
import json
import pathlib

import pytest

import themis
from themis import kernel
from themis.verifier.errors import VerificationError

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
REPO = FIXTURES.parent.parent
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))
ESTIMATE_SCHEMA = json.loads(
    (REPO / "themis" / "schemas" / "query_result.schema.json")
    .read_text(encoding="utf-8"))["properties"]["numeric_estimate"]

KERNEL = ast.parse((REPO / "themis" / "kernel.py").read_text(encoding="utf-8"))


def _carrying(block: str) -> list[str]:
    return sorted(
        name for name, pair in SHAPES.items()
        if isinstance((pair["result"].get("numeric_estimate") or {}).get(block),
                      dict))


SENSITIVITY = _carrying("sensitivity_analysis")
OVB = _carrying("ovb_sensitivity")


# ------------------------------------------- the reading a person acts on


@pytest.mark.parametrize("shape", SENSITIVITY)
@pytest.mark.parametrize("field,forged", [
    ("e_value", 99.0),
    ("e_value_ci_bound", 99.0),
    ("risk_ratio", 9.9),
    ("interpretation_band", "very_robust"),
])
def test_an_e_value_is_re_derived_wherever_the_block_appears(
        shape, field, forged):
    """Every shape, because the defect was which shapes.

    Nothing about the fit changes: the robustness claim beside it does, and
    that is the sentence a reader acts on.
    """
    pair = SHAPES[shape]
    result = copy.deepcopy(pair["result"])
    block = result["numeric_estimate"]["sensitivity_analysis"]
    if block.get(field) is None or block[field] == forged:
        pytest.skip(f"{shape} records no {field}")
    block[field] = forged
    with pytest.raises(VerificationError, match="e_value"):
        themis.verify(pair["program"], result)


@pytest.mark.parametrize("shape", OVB)
@pytest.mark.parametrize("field", ["robustness_value_q", "partial_r2"])
def test_an_omitted_variable_bound_is_re_derived_wherever_it_appears(
        shape, field):
    pair = SHAPES[shape]
    result = copy.deepcopy(pair["result"])
    block = result["numeric_estimate"]["ovb_sensitivity"]
    if block.get(field) is None:
        pytest.skip(f"{shape} records no {field}")
    block[field] = 0.99
    with pytest.raises(VerificationError):
        themis.verify(pair["program"], result)


def test_the_block_above_really_does_arrive_by_more_than_one_route():
    """Otherwise the tests above are a sweep over one route wearing a
    parametrisation.

    ``status`` is what the dispatch keys on, so two statuses among the
    shapes carrying one block IS the fact this module exists for: the block
    is a property of the estimate and the route is not, and any rule bound
    to one of them covers the shapes of the other by luck.
    """
    routes = {SHAPES[s]["result"].get("status") for s in SENSITIVITY}
    assert len(routes) > 1, routes
    for shape in SENSITIVITY:
        themis.verify(SHAPES[shape]["program"], SHAPES[shape]["result"])


# --------------------------------------------------- the table's two edges


def _rule_names() -> set[str]:
    return {row.rule.__name__ for row in kernel._ESTIMATE_AUDITS}


def _call_sites() -> dict[str, int]:
    sites: dict[str, int] = {}
    for node in ast.walk(KERNEL):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            sites[node.func.id] = sites.get(node.func.id, 0) + 1
    return sites


def _adapter_targets() -> dict[str, set[str]]:
    """For each kernel-local row, the verifier it hands the work to.

    One row adapts a rule that takes the block rather than the estimate
    around it. Resolved rather than listed, so the gate below reaches the
    real rule and not the wrapper standing in front of it.
    """
    out: dict[str, set[str]] = {}
    names = _rule_names()
    for node in KERNEL.body:
        if not isinstance(node, ast.FunctionDef) or node.name not in names:
            continue
        out[node.name] = {
            sub.func.id for sub in ast.walk(node)
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
            and sub.func.id.startswith("verify_")
        }
    return out


def test_the_table_is_the_only_way_one_of_these_rules_is_called():
    """What a hand-copied call costs is invisible from outside.

    A rule reached only through ``row.rule`` cannot acquire a second caller
    on a branch, which is how fifteen of them ended up covering a branch
    instead of covering the blocks they audit. Asked of the sources, so it
    is the shape of the code that is pinned and not one run through it.
    """
    sites = _call_sites()
    named = sorted(name for name in _rule_names() if name.startswith("verify"))
    assert named, "no rule in the table — this gate reads nothing"
    called = {name: sites[name] for name in named if name in sites}
    assert not called, called

    for adapter, targets in _adapter_targets().items():
        for target in targets:
            assert sites.get(target, 0) == 1, (
                f"{target} is called {sites.get(target, 0)} times in "
                f"kernel.py; {adapter} is meant to be its only caller")


def test_every_selector_names_something_the_schema_declares():
    """A row that matches nothing looks exactly like a row that found
    nothing wrong."""
    blocks = set(ESTIMATE_SCHEMA["properties"])
    methods = set(ESTIMATE_SCHEMA["properties"]["method"]["enum"])
    for row in kernel._ESTIMATE_AUDITS:
        where = row.rule.__name__
        assert row.methods | row.method_prefixes | row.blocks, (
            f"{where} has no selector and can never run")
        assert row.blocks <= blocks, (where, row.blocks - blocks)
        assert row.methods <= methods, (where, row.methods - methods)
        for prefix in row.method_prefixes:
            assert any(m.startswith(prefix) for m in methods), (where, prefix)


def test_no_row_selects_something_the_producer_never_writes():
    """The gate above reads the schema; this one reads the answers.

    A selector can name a declared block that no estimator has emitted
    since it was renamed, and the row is then dead in the only way that
    matters — matching nothing, forever, saying nothing about it. The
    schema cannot tell the two apart because both names are in it.
    """
    reached: set[str] = set()
    for pair in SHAPES.values():
        estimate = pair["result"].get("numeric_estimate") or {}
        reached |= {row.rule.__name__ for row in kernel._ESTIMATE_AUDITS
                    if row.applies(estimate)}
    dead = sorted(_rule_names() - reached)
    assert not dead, dead
