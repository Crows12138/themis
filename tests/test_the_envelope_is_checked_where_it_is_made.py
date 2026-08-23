"""The output half of the kernel's contract, enforced at the door (#443).

``themis.kernel``'s module docstring lists two contracts — the input
conforms to ``kernel_ast.schema.json``, the output's ``results`` entries
conform to ``query_result.schema.json``. Only the first was checked here.
The second was left to :func:`themis.input.syntactic_validator.
validate_result`, which is the VERIFIER's entry: a caller who never
verifies never checks it, and a test suite checks exactly as much of it
as its tests remembered to ask for.

Measured before this existed, by validating every envelope the whole
suite produced: four shapes on public results that the schema forbids —
the caller's ``model`` string as typed rather than as understood, a block
with three readers the contract had never heard of, a sentence inside a
closed object, and a field removed from the gap report one commit earlier
that one road went on writing.

Three of the four were top-level keys, and that is not a coincidence:
``extensions`` has a registry check at the two exits
(:func:`themis.blocks.check_registered`, 18 members) and the top level had
nothing but the schema, which nobody read.

So the door checks it, and this module pins that the door does — by
forging an envelope past each door's producer and requiring the door to
refuse it, which is the only way to tell a check that runs from a check
that is merely written down.
"""
from __future__ import annotations

import ast
import json
import pathlib

import pytest

import themis
from themis import kernel
from themis.input.syntactic_validator import SyntacticError
from themis.types import (
    DataGap,
    DataGapReport,
    GapBlocks,
    GapKind,
    GapProvenanceRef,
    GapRefKind,
    GapSeverity,
)

REPO = pathlib.Path(__file__).resolve().parent.parent
SCHEMA = json.loads(
    (REPO / "themis" / "schemas" / "query_result.schema.json")
    .read_text(encoding="utf-8"))

#: The entries that hand an envelope to a caller. Named rather than
#: discovered, because what makes one of these a door is that it is
#: public and returns ``{"results": [...]}`` — a fact about the module's
#: intent that no scan can read off it.
DOORS = ("run", "estimate", "apply_patch_and_run")


def _atom(pred: str) -> dict:
    return {"predicate": pred, "args": [{"type": "const", "name": "me"}]}


def _program() -> dict:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True},
                "given": []}},
        ],
    }


# --- the door refuses what the schema forbids --------------------------------


def _forged(real, key: str = "a_block_from_the_future"):
    """The producer, with one undeclared key added to every result."""
    def producer(*args, **kwargs):
        out = real(*args, **kwargs)
        for entry in out.get("results") or ():
            entry[key] = {"anything": 1}
        return out
    return producer


def test_run_refuses_an_envelope_the_schema_forbids(monkeypatch):
    """The counterexample the door exists for. Without it the key reaches
    the caller, and the suite stays green because nothing downstream of
    the kernel asks."""
    monkeypatch.setattr(kernel, "_run_typed", _forged(kernel._run_typed))
    with pytest.raises(SyntacticError, match="a_block_from_the_future"):
        themis.run(_program())


def test_apply_patch_and_run_refuses_it_too(monkeypatch):
    """The same producer behind a second door. A door that re-runs the
    pipeline is a door, and it was the one most easily forgotten because
    the check would have looked like a copy of ``run``'s."""
    monkeypatch.setattr(kernel, "_run_typed", _forged(kernel._run_typed))
    with pytest.raises(SyntacticError, match="a_block_from_the_future"):
        themis.apply_patch_and_run(_program(), [])


def test_estimate_refuses_it_through_its_own_producer(monkeypatch):
    """The estimate door reaches its producer through an import inside the
    function, so this patches where that import resolves."""
    from themis.estimation import dispatch

    monkeypatch.setattr(dispatch, "estimate_program",
                        _forged(dispatch.estimate_program))
    pd = pytest.importorskip("pandas")
    frame = pd.DataFrame({"x": [True, False] * 20, "y": [True, False] * 20})
    with pytest.raises(SyntacticError, match="a_block_from_the_future"):
        themis.estimate(_program(), frame, ci_bootstrap=0)


def test_a_clean_envelope_still_leaves(monkeypatch):
    """The other half of the counterexample: the check is not a blanket
    refusal, and the ordinary path is unchanged."""
    out = themis.run(_program())
    assert out["results"]


@pytest.mark.parametrize("door", DOORS)
def test_every_door_returns_through_the_check(door):
    """Read out of the module rather than trusted. A fourth door added
    later without this is an envelope nobody holds to the contract, and
    the three tests above cannot see it — they name the doors they know.
    """
    tree = ast.parse((REPO / "themis" / "kernel.py").read_text(
        encoding="utf-8"))
    node = next(n for n in tree.body
                if isinstance(n, ast.FunctionDef) and n.name == door)
    returns = [n for n in ast.walk(node) if isinstance(n, ast.Return)]
    assert returns, door
    for one in returns:
        assert one.value is not None and ast.unparse(one.value).startswith(
            "_leaving("), (door, ast.unparse(one.value or ast.Constant(None)))


# --- the top level is closed, and the closure has one record ------------------


def test_the_envelope_is_closed_at_the_top_level():
    """What the door enforces. Opened, the door still runs and stops
    meaning anything — which is how three of the four measured breaches
    were top-level keys while ``extensions`` had a registry check."""
    assert SCHEMA["additionalProperties"] is False


def test_the_registry_closes_extensions_and_not_the_top_level():
    """Said out loud because the two closures live in different places
    and the docstring of the estimate exit claims only one of them. A
    reader who takes ``check_registered`` for the whole answer is the
    reader who adds a top-level key."""
    from themis import blocks

    declared = {str(b) for b in blocks.Block}
    assert declared == set(
        SCHEMA["properties"]["extensions"]["properties"])
    assert not declared & set(SCHEMA["properties"])


# --- the report born in estimation is the same shape as any other -------------


def _gap() -> DataGap:
    from themis import gaps

    return DataGap(
        kind=GapKind.MISSING_DISTRIBUTION,
        severity=GapSeverity.BLOCKING,
        blocks=GapBlocks.POINT_ESTIMATE,
        describes=(gaps.sentence(gaps.Sentence.TIAN_FOUND_A_HEDGE),),
        provenance=(GapProvenanceRef(ref_kind=GapRefKind.VERIFIER_CHECK,
                                     ref_id="x"),),
    )


def test_a_report_born_in_estimation_has_the_same_keys_as_any_other():
    """One author for the report's key set, as there already was for an
    entry's. The estimation road hand-built this dict, which is why it
    went on writing a field the dataclass and the schema had both
    dropped."""
    from themis.estimation.dispatch import _file_gaps
    from themis.output.result_orchestrator import data_gap_report_to_dict

    born_here: dict = {}
    _file_gaps(born_here, [_gap()])
    assert set(born_here["data_gap_report"]) == set(
        data_gap_report_to_dict(DataGapReport(gaps=(_gap(),))))


def test_only_one_place_builds_the_report_s_key_set():
    """The static half. A second dict literal carrying ``gaps`` and
    assigned to ``data_gap_report`` is a second author, whatever it is
    called."""
    written = []
    for path in sorted((REPO / "themis").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            names = {ast.unparse(t) for t in node.targets}
            if not any(n.endswith('["data_gap_report"]') or
                       n.endswith("'data_gap_report']") for n in names):
                continue
            if isinstance(node.value, ast.Dict):
                written.append(f"{path.name}:{node.lineno}")
    assert written == [], written


# --- an option is a closed vocabulary, and the envelope records it as one -----


def test_the_accepted_models_are_the_ones_the_envelope_declares():
    """Two records of one set, held equal. The context field's enum and
    the function that fills it were written apart, and what reached the
    envelope was the caller's string untouched."""
    from themis.estimation.dispatch import _DECLARED_MODELS

    enum = SCHEMA["properties"]["estimation_context"]["properties"][
        "model_preference"]["enum"]
    assert set(_DECLARED_MODELS) == set(enum)


@pytest.mark.parametrize("typed,meant", [
    ("DRLearner", "drlearner"),
    ("  Linear  ", "linear"),
    ("AUTO", "auto"),
    ("logistic", "logistic"),
])
def test_casing_and_space_are_the_caller_s_and_not_the_run_s(typed, meant):
    """Facts about the call, not about the run, so they are settled once
    and neither the estimators nor the envelope see them — and 'DRLearner'
    is the casing EconML's own class name invites."""
    from themis.estimation.dispatch import _declared_model

    assert _declared_model(typed) == meant


def test_a_model_outside_the_set_is_refused_at_the_entry():
    """Where it is the caller's mistake, rather than at whichever
    estimator happens to read the option — a program that never reaches
    the dose-response path used to carry the typo onto the envelope."""
    from themis.estimation.dispatch import _declared_model

    with pytest.raises(ValueError, match="unknown model"):
        _declared_model("lienar")
    with pytest.raises(ValueError, match="must be a string"):
        _declared_model(None)      # type: ignore[arg-type]


def test_the_option_is_understood_once_and_not_at_each_reader():
    """Through the public door, because the first version of this fix was
    wrong in a way only running it could show.

    ``model`` has five readers. Two normalise and three compare exactly,
    so cleaning up only what reached the ENVELOPE left ``'  Linear  '``
    answering on one route and raising on another while the envelope
    recorded a third thing. Normalising at the single exit is what makes
    the recorded option the option every reader got.
    """
    pd = pytest.importorskip("pandas")
    frame = pd.DataFrame({"x": [True, False] * 20,
                          "y": [True, False, True, False] * 10})

    def ran(model):
        out = themis.estimate(_program(), frame, model=model, ci_bootstrap=0)
        return (out["results"][0].get("estimation_context")
                or {}).get("model_preference")

    assert ran("  Linear  ") == ran("linear") == "linear"
    with pytest.raises(ValueError, match="unknown model"):
        themis.estimate(_program(), frame, model="lienar", ci_bootstrap=0)


# --- the block that had readers and no shape ---------------------------------


def test_the_substitution_block_is_declared_where_it_is_written():
    """It had three readers — a test, the language gate, and the
    rendering prompt — and no entry in the contract, so the envelope
    carrying it was outside its own schema every time a dose-response
    query met a binary treatment."""
    declared = SCHEMA["properties"]["estimator_fallback"]
    assert declared["additionalProperties"] is False
    assert set(declared["required"]) == set(declared["properties"]) == {
        "from", "to", "reason"}


def test_the_fallback_block_is_written_beside_the_sentence_that_carries_it():
    """Declaring it asked the browser what it does with it, and the answer
    recorded there is that another field carries it.

    That answer is a claim about the WRITER, so it is checked on the
    writer: one site, and in the same unbranched body a data-contract
    warning saying which estimator was asked for, which one ran and why —
    a line that surface prints verbatim. A second writer, or this one
    putting either statement behind a condition, and the block can reach an
    envelope with nothing carrying it.
    """
    sites = []
    for path in sorted((REPO / "themis").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        funcs = [n for n in ast.walk(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            if not any("estimator_fallback" in ast.unparse(t)
                       for t in node.targets):
                continue
            inner = max(
                (f for f in funcs
                 if f.lineno <= node.lineno <= (f.end_lineno or f.lineno)),
                key=lambda f: f.lineno, default=None)
            sites.append((f"{path.name}:{node.lineno}", node, inner))

    assert len(sites) == 1, [where for where, _, _ in sites]
    where, assign, inner = sites[0]
    assert inner is not None, where
    assert assign in inner.body, f"{where} writes the block conditionally"
    beside = [s for s in inner.body
              if isinstance(s, ast.Expr) and isinstance(s.value, ast.Call)
              and "_append_result_data_contract_warning" in ast.unparse(
                  s.value.func)]
    assert beside, (
        f"{where} writes estimator_fallback and nothing beside it appends "
        f"the warning types.ts names as its carrier")
