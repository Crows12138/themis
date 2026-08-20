"""Every step in a kernel derivation is a step that succeeded.

The gap report used to scan derivations for a failed step — one carrying
``success=False``, or named ``unidentifiable_via_*`` — and raised the
blocking identification gap from it. The Tian wiring replaced that
representation. Unidentifiability now arrives one of two ways, and
neither is a step that failed: as a SUCCESSFUL ``tian_hedge_witness``
step whose output is ``StructuralResult(False)``, or, when the complete
algorithm exhausts without a witness, as an investigation item declaring
``UNIDENTIFIABLE_NO_ADMISSIBLE_SET``. No producer has written a failed
step since, so the scan and every branch it fed were removed.

Deleting a reader is safe only while the shape it read cannot be
produced, and "cannot" is a claim about the source rather than about a
run — a census over the corpus would report that nobody came, which is a
different sentence. The censuses below are therefore over every
``DerivationStep`` construction site in ``themis/``, and they are closed
rather than sampled: a site either writes a literal rule name, or it
computes one at a site declared here with its reason, and a step built by
unpacking a mapping — where neither reading applies — is refused
outright.

There is a corpus arm too, and its denominator is stated because it is
not the one carrying the claim: over the fifteen L3 programs only four
results carry a derivation at all, ten steps naming seven of the
fifty-eight rules the kernel can emit. It is corroboration, not coverage.

The fourth arm is the same coin's other face. Removing the dead IV
classifier left ``missing_iv_candidate`` with no producer anywhere,
joining ``missing_population_distribution``; both are declared in
``GAP_KINDS_WITH_NO_PRODUCER``, and this file holds that table to a
census of the tree. Note which direction the census proves. Zero
construction sites IS a proof that nothing constructs the kind. One or
more sites is NOT a proof that anything reaches one —
``missing_iv_candidate`` had a site for as long as it was unreachable,
which is how it came to be in the table.

The verifier is deliberately held to none of this. Its input is a
derivation somebody else wrote, which may claim a failure the kernel
would never produce; recognising that claim is its whole job, and its own
copy of the failure names stays where it is.
"""
from __future__ import annotations

import ast
import json
import pathlib

import pytest

import themis
from themis.output.data_gap_report import GAP_KINDS_WITH_NO_PRODUCER
from themis.types import GapKind

REPO = pathlib.Path(__file__).resolve().parents[1]
THEMIS = REPO / "themis"

# The rule names a step may carry to say it failed. Written out here and
# not imported: the producer no longer keeps such a table, and the one
# copy that remains is the verifier's, which is the single thing this
# file must not hold itself to.
FAILURE_RULE_NAMES = frozenset({
    "unidentifiable_via_backdoor",
    "unidentifiable_via_front_door",
    "unidentifiable_via_iv",
    "unidentifiable_via_mediation",
    "unidentifiable_via_transport",
})

# Where those names may still be written, and why. Each of these reads a
# derivation it did not write.
NAMES_MAY_APPEAR_IN: dict[str, str] = {
    "themis/verifier/data_gap_rules.py":
        "the verifier's own failure list, deliberately not imported",
    "themis/verifier/rules.py":
        "the replay rule that checks a submitted unidentifiability claim",
    "themis/verifier/verify.py":
        "dispatch into that rule, and the step vocabulary it belongs to",
}

# The one site that may hand a DerivationStep a ``success`` it did not
# choose: the verifier's parser, forwarding what the submitted JSON said.
SUCCESS_MAY_BE_PASSED_IN: dict[str, str] = {
    "themis/verifier/serialization.py":
        "the parser, forwarding the flag the submitted derivation set",
}

# The sites where a step's rule is not a literal, keyed by the expression
# as written. A literal is checked by the census above; these three are
# checked by reading, and each reading is recoverable from the tree:
RULE_MAY_BE_COMPUTED_AT: dict[tuple[str, str], str] = {
    ("themis/estimation/dispatch.py", "terminal_rule"):
        "the doubly-robust terminal step; the argument comes from a "
        "three-entry literal dict of numeric_*_estimate names, all of "
        "which the literal census above sees in this same file",
    ("themis/runtime/scheduler.py",
     "'m_connection_witness' if connected else 'm_separation_witness'"):
        "a ternary over two literals, both of which the census sees",
    ("themis/verifier/serialization.py", "rule"):
        "the parser, forwarding the name the submitted derivation gave",
}

CORPUS = sorted((REPO / "docs" / "l3_simulation").glob("case_*.json"))


def _rel(path: pathlib.Path) -> str:
    return str(path.relative_to(REPO)).replace("\\", "/")


def _py_files() -> list[pathlib.Path]:
    return [
        p for p in sorted(THEMIS.rglob("*.py"))
        if "node_modules" not in p.parts and "__pycache__" not in p.parts
    ]


def _tree(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


# ============================================ the source censuses


def test_no_module_outside_the_verifier_writes_a_failure_rule_name():
    """A producer that names a step ``unidentifiable_via_*`` is a producer
    expecting the gap report to notice, and nothing there notices any
    more."""
    offenders: list[str] = []
    for path in _py_files():
        rel = _rel(path)
        if rel in NAMES_MAY_APPEAR_IN:
            continue
        for node in ast.walk(_tree(path)):
            if (isinstance(node, ast.Constant)
                    and node.value in FAILURE_RULE_NAMES):
                offenders.append(f"{rel}:{node.lineno} {node.value!r}")
    assert not offenders, (
        "these write a failure rule name outside the verifier: "
        f"{offenders}. A step by that name says the identification failed, "
        "and the gap report no longer reads for it — the kernel says so "
        "with a tian_hedge_witness step or an investigation item."
    )


@pytest.mark.parametrize("rel", sorted(NAMES_MAY_APPEAR_IN))
def test_every_file_allowed_to_write_one_still_does(rel: str):
    """The allowance describes the tree, so an entry that has stopped
    being true is an allowance nobody is using."""
    text = (REPO / rel).read_text(encoding="utf-8")
    assert any(name in text for name in FAILURE_RULE_NAMES), (
        f"{rel} is listed as a place a failure rule name may appear "
        f"({NAMES_MAY_APPEAR_IN[rel]}) and no longer writes one. Drop the "
        "entry."
    )


def _step_call_sites():
    """Every ``DerivationStep(...)`` call in themis/, as
    (relpath, node)."""
    for path in _py_files():
        rel = _rel(path)
        for node in ast.walk(_tree(path)):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = (
                fn.id if isinstance(fn, ast.Name)
                else fn.attr if isinstance(fn, ast.Attribute)
                else None
            )
            if name == "DerivationStep":
                yield rel, node


def test_a_rule_that_is_not_a_literal_is_declared_with_its_reason():
    """The census over literals is only closed while every rule name IS
    one. Each site that computes a name is read once and written down;
    a new one has to be read too, rather than passing because it is not
    a string the census recognises."""
    seen: set[tuple[str, str]] = set()
    for rel, node in _step_call_sites():
        args = [kw.value for kw in node.keywords if kw.arg == "rule"]
        if not args and node.args:
            args = [node.args[0]]
        for value in args:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                continue
            seen.add((rel, ast.unparse(value)))
    declared = set(RULE_MAY_BE_COMPUTED_AT)
    assert seen == declared, (
        f"undeclared computed rule names: {sorted(seen - declared)}; "
        f"declared but no longer present: {sorted(declared - seen)}"
    )


def test_no_step_is_built_by_unpacking_a_mapping():
    """``DerivationStep(**payload)`` would carry a rule and a success
    flag no census can read. Nothing does it; this is what keeps that
    true."""
    offenders = [
        f"{rel}:{node.lineno}"
        for rel, node in _step_call_sites()
        if any(kw.arg is None for kw in node.keywords)
    ]
    assert not offenders, (
        f"these build a DerivationStep from an unpacked mapping: "
        f"{offenders}. Pass the fields by name so the census can read them."
    )


def test_no_module_outside_the_parser_hands_a_step_a_success_flag():
    """``DerivationStep.success`` exists so a submitted derivation can
    claim a failure and the verifier can check the claim. A producer
    setting it is a producer claiming one about itself."""
    offenders = [
        f"{rel}:{node.lineno}"
        for rel, node in _step_call_sites()
        if rel not in SUCCESS_MAY_BE_PASSED_IN
        and any(kw.arg == "success" for kw in node.keywords)
    ]
    assert not offenders, (
        f"these build a DerivationStep with an explicit success: {offenders}"
    )


# ============================================ the corpus arm


@pytest.mark.parametrize("case", CORPUS, ids=lambda p: p.stem)
def test_no_step_in_a_real_run_says_it_failed(case: pathlib.Path):
    """Corroboration. Its denominator is the corpus, so it says nobody
    came rather than nobody can, and the census arms are what carry the
    claim. Ten steps over four of these fifteen programs."""
    out = themis.run(json.loads(case.read_text(encoding="utf-8")))
    for result in out["results"]:
        for i, step in enumerate(result.get("derivation", {}).get("steps", [])):
            assert step.get("success", True) is True, (
                f"{case.name} {result.get('query_id')} step {i} "
                f"({step.get('rule')}) says it failed"
            )
            assert step.get("rule") not in FAILURE_RULE_NAMES, (
                f"{case.name} {result.get('query_id')} step {i} is named "
                f"{step.get('rule')!r}"
            )


# ============================================ the empty slots


def _construction_sites() -> dict[str, list[str]]:
    """Every place a GapKind can be constructed, by either form the tree
    uses: ``kind=GapKind.X`` / ``gap=GapKind.X`` on a dataclass, and the
    raw ``{"kind": "<value>"}`` dict the estimator-time findings are
    written as."""
    by_value = {k.value: k.name for k in GapKind}
    by_name = {k.name for k in GapKind}
    sites: dict[str, list[str]] = {k.name: [] for k in GapKind}
    for path in _py_files():
        rel = _rel(path)
        if rel == "themis/types.py":
            continue  # the declaration and its classification sets
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.keyword) and node.arg in ("kind", "gap"):
                v = node.value
                if (isinstance(v, ast.Attribute)
                        and isinstance(v.value, ast.Name)
                        and v.value.id == "GapKind"
                        and v.attr in by_name):
                    sites[v.attr].append(f"{rel}:{v.lineno}")
            if isinstance(node, ast.Dict):
                for key, val in zip(node.keys, node.values):
                    if (isinstance(key, ast.Constant) and key.value == "kind"
                            and isinstance(val, ast.Constant)
                            and val.value in by_value):
                        sites[by_value[val.value]].append(
                            f"{rel}:{val.lineno}")
    return sites


def test_a_gap_kind_no_code_constructs_is_declared_as_one():
    sites = _construction_sites()
    uncons = {k for k in GapKind if not sites[k.name]}
    declared = set(GAP_KINDS_WITH_NO_PRODUCER)
    assert uncons == declared, (
        "GAP_KINDS_WITH_NO_PRODUCER disagrees with the tree. Nothing "
        f"constructs {sorted(k.value for k in uncons - declared)} and they "
        "are not declared; "
        f"{sorted(k.value for k in declared - uncons)} are declared and "
        "something does — "
        + "; ".join(
            f"{k.value} at {sites[k.name]}" for k in sorted(
                declared - uncons, key=lambda k: k.value)
        )
    )


def test_every_empty_slot_says_why_it_is_empty():
    blank = [
        k.value for k, why in GAP_KINDS_WITH_NO_PRODUCER.items()
        if not why.strip()
    ]
    assert not blank, f"declared with no reason: {blank}"
