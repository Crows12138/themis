"""The assumption ledger must cover every numeric answer, not the families
whose dispatch path happened to opt in.

The ledger is what ``build_analysis_report`` and ``response_rendering.md`` lead
with — everything the answer takes on faith, ranked by how it dies if it is
false. Its failure mode is one-sided: an assumption that never reaches it is,
to every consumer, an assumption nobody makes. Before this batch it was built
per estimator family and 14 of the 31 numeric methods never got one, while
their estimates declared 4-9 assumptions each; ``iv_wald`` got a ledger on 11
runs out of 29 and every one of those 11 carried only proposal-edge entries,
never the exclusion / monotonicity / LATE assumptions the number rests on.

The oracle here is the estimator's own ``numeric_estimate.assumptions`` — the
one channel every estimator populates. Whatever it declares must be on the
ledger, and the verifier re-derives that independently.
"""
import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.output.analysis_report import build_analysis_report
from themis.output.assumption_glossary import classify_assumption, is_classified
from themis.verifier.errors import VerificationError


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "u"}]}


def _var(p, **kw):
    return {"kind": "variable", "predicate": p, **kw}


def _cause(a, b):
    return {"kind": "cause", "from": _atom(a), "to": _atom(b)}


def _effect_query(**extra):
    q = {"kind": "effect",
         "intervention": {"atom": _atom("x"), "value": True},
         "target": {"atom": _atom("y"), "value": True}, "given": []}
    q.update(extra)
    return {"kind": "query", "id": "q", "query": q}


def _prog(statements):
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "u"}]},
            "statements": statements}


def _M(se, sp):
    return [[sp, 1 - se], [1 - sp, se]]


# --- the battery: one scenario per previously-uncovered estimator family ------


def _data(seed=5, n=8_000):
    rng = np.random.default_rng(seed)
    z = rng.integers(0, 2, n)
    u = rng.integers(0, 2, n)
    xs = (rng.random(n) < 0.3 + 0.3 * z).astype(int)
    ys = (rng.random(n) < 0.2 + 0.3 * xs + 0.2 * z).astype(int)
    ux, uy = rng.random(n), rng.random(n)
    xf = (rng.random(n) < 0.3 + 0.3 * u).astype(int)
    mf = (rng.random(n) < 0.2 + 0.5 * xf).astype(int)
    zi = rng.integers(0, 2, n)
    xi = (rng.random(n) < 0.2 + 0.5 * zi + 0.2 * u).astype(int)
    return {
        "backdoor": pd.DataFrame({"x": xs, "y": ys, "z": z}),
        "misclassified": pd.DataFrame({
            "x": np.where(xs == 1, (ux < 0.9).astype(int), (ux < 0.15).astype(int)),
            "y": np.where(ys == 1, (uy < 0.8).astype(int), (uy < 0.05).astype(int)),
            "z": z,
        }),
        "frontdoor": pd.DataFrame({
            "x": xf, "m": mf,
            "y": (rng.random(n) < 0.1 + 0.4 * mf + 0.3 * u).astype(int),
            "c": rng.integers(0, 40, n),
        }),
        "iv": pd.DataFrame({
            "z": zi, "x": xi,
            "y": 0.4 * xi + 0.6 * u + rng.normal(0, 0.3, n),
        }),
        "mediation": pd.DataFrame({
            "x": xf, "m": mf,
            "y": 0.3 * xf + 0.5 * mf + rng.normal(0, 0.3, n),
        }),
    }


_BACKDOOR = _prog([_var("x"), _var("y"), _var("z"),
                   _cause("x", "y"), _cause("z", "x"), _cause("z", "y"),
                   _effect_query()])
_MEASURED = _prog([_var("x", measurement="self-report"), _var("y"), _var("z"),
                   _cause("x", "y"), _cause("z", "x"), _cause("z", "y"),
                   _effect_query()])
_FRONTDOOR = _prog([_var("x"), _var("m"), _var("y"),
                    _cause("x", "m"), _cause("m", "y"),
                    {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
                    _effect_query()])
_IV = _prog([_var("z"), _var("x"), _var("y"),
             _cause("z", "x"), _cause("x", "y"),
             {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
             _effect_query()])
_MEDIATION = _prog([_var("x"), _var("m"), _var("y"),
                    _cause("x", "m"), _cause("m", "y"), _cause("x", "y"),
                    _effect_query(mediator=_atom("m"))])

_MC_X = {"x": {"confusion_matrix": _M(0.9, 0.85), "states": [False, True]}}
_MC_Y = {"y": {"confusion_matrix": _M(0.8, 0.95), "states": [False, True]}}

# name -> (program, data key, extra estimate kwargs)
_BATTERY = {
    "backdoor": (_BACKDOOR, "backdoor", {}),
    "frontdoor": (_FRONTDOOR, "frontdoor", {}),
    "iv": (_IV, "iv", {}),
    "mediation": (_MEDIATION, "mediation", {}),
    "exposure_misclassification": (_MEASURED, "misclassified",
                                   {"misclassification": _MC_X}),
    "outcome_misclassification": (_MEASURED, "misclassified",
                                  {"misclassification": _MC_Y}),
    "combined_misclassification": (_MEASURED, "misclassified",
                                   {"misclassification": {**_MC_X, **_MC_Y}}),
}


@pytest.fixture(scope="module")
def frames():
    return _data()


def _run(name, frames, **override):
    prog, key, kwargs = _BATTERY[name]
    opts = {"ci_bootstrap": 0, **kwargs, **override}
    out = themis.estimate(prog, frames[key], **opts)
    return prog, out["results"][0]


def _ledger(result):
    return (result.get("extensions") or {}).get("assumption_ledger")


# --- coverage -----------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(_BATTERY))
def test_every_numeric_answer_carries_an_assumption_ledger(name, frames):
    _, r = _run(name, frames)
    assert r.get("numeric_estimate"), f"{name} produced no number to audit"
    ledger = _ledger(r)
    assert ledger is not None, f"{name} answered with no assumption ledger"
    assert any(e["layer"] == "identification" for e in ledger["assumptions"]), (
        f"{name} ledger carries no identification assumption"
    )


@pytest.mark.parametrize("name", sorted(_BATTERY))
def test_nothing_the_estimator_declared_is_missing_from_the_ledger(name, frames):
    """The estimator's flat list is the oracle: either each entry is on the
    ledger, or the estimator supplied structured identification entries that
    say the same thing."""
    _, r = _run(name, frames)
    declared = set(r["numeric_estimate"]["assumptions"])
    entries = _ledger(r)["assumptions"]
    from_estimator = {e.get("id") for e in entries
                      if e.get("provenance") == "estimator_declared"}
    if from_estimator:
        assert declared <= from_estimator
    else:
        assert any(e["layer"] == "identification" for e in entries)


@pytest.mark.parametrize("name", sorted(_BATTERY))
def test_the_report_prints_an_assumptions_section(name, frames):
    prog, r = _run(name, frames)
    assert "## 假设" in build_analysis_report(r, program=prog)


def test_a_family_that_already_declared_structured_assumptions_is_untouched(frames):
    """Back-door supplies its own structured identification specs; the flat
    list is its unstructured twin and must not be folded in on top."""
    _, r = _run("backdoor", frames)
    entries = _ledger(r)["assumptions"]
    assert not any(e.get("provenance") == "estimator_declared" for e in entries)
    assert [e["layer"] for e in entries].count("identification") == 3


# --- classification -----------------------------------------------------------


def test_an_unclassified_assumption_is_surfaced_not_dropped():
    """The default decides whether adding an estimator can silently lose an
    assumption. It must not."""
    entry = classify_assumption("some_assumption_nobody_has_classified_yet")
    assert entry["claim"] == "some_assumption_nobody_has_classified_yet"
    assert entry["severity"] == "invalidating"
    assert entry["layer"] == "identification"
    assert not is_classified("some_assumption_nobody_has_classified_yet")


def test_how_the_interval_was_computed_is_not_an_invalidating_assumption(frames):
    """A cluster bootstrap being the wrong variance model widens or narrows the
    interval; it does not stop the number being a causal effect."""
    _, r = _run("frontdoor", frames, cluster="c", ci_bootstrap=20)
    entries = _ledger(r)["assumptions"]
    ci = [e for e in entries if e["id"].startswith("ci_via_pairs_cluster_bootstrap")]
    assert ci, "the cluster bootstrap was not declared"
    assert ci[0]["severity"] == "confidence_only"
    assert "c" in ci[0]["claim"]
    assert entries[-1]["severity"] == "confidence_only", "sorted last, as least severe"


@pytest.mark.parametrize("name", sorted(_BATTERY))
def test_the_glossary_keeps_up_with_what_the_estimators_emit(name, frames):
    """Unclassified IDs still reach the reader, but as raw snake_case with a
    presumed severity — so this is the signal to extend the glossary."""
    _, r = _run(name, frames)
    unknown = [a for a in r["numeric_estimate"]["assumptions"]
               if not is_classified(a)]
    assert not unknown, f"{name} emits unclassified assumption IDs: {unknown}"


def test_no_producer_invents_a_severity_outside_the_vocabulary(frames):
    """A severity the ledger's ranking does not know sorts by the fallback, and
    the report has no translation for it — the monotonicity specs used to."""
    from themis.estimation.causation import _identification_assumptions
    from themis.estimation.counterfactual_cell import (
        _identification_assumptions as _cell_assumptions,
    )
    vocabulary = {"invalidating", "distorting", "confidence_only"}
    specs = list(_identification_assumptions("backdoor_adjustment", True))
    specs += list(_cell_assumptions(
        provenance="backdoor_adjustment", adjustment=("z",),
        monotonicity="non_decreasing"))
    assert {s["severity"] for s in specs} <= vocabulary


# --- verifier -----------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(_BATTERY))
def test_verify_accepts_the_honest_ledger(name, frames):
    _, r = _run(name, frames)
    themis.verify_assumption_ledger(r)


def _tamper(result, mutate):
    r = copy.deepcopy(result)
    mutate(r["extensions"]["assumption_ledger"])
    return r


def test_verify_rejects_a_dropped_assumption(frames):
    _, r = _run("iv", frames)
    bad = _tamper(r, lambda led: led["assumptions"].pop())
    with pytest.raises(VerificationError, match="drops estimator-declared"):
        themis.verify_assumption_ledger(bad)


def test_verify_rejects_an_invented_assumption(frames):
    _, r = _run("iv", frames)

    def _add(led):
        led["assumptions"].append({
            "id": "never_declared", "claim": "never declared",
            "layer": "identification", "severity": "invalidating",
            "testable": False, "provenance": "estimator_declared"})
        led["summary"] = led["summary"].replace(
            f"依赖 {len(led['assumptions']) - 1} 条",
            f"依赖 {len(led['assumptions'])} 条")

    with pytest.raises(VerificationError, match="never declared"):
        themis.verify_assumption_ledger(_tamper(r, _add))


def test_verify_rejects_a_missing_ledger_while_assumptions_are_declared(frames):
    _, r = _run("iv", frames)
    r = copy.deepcopy(r)
    r["extensions"].pop("assumption_ledger")
    with pytest.raises(VerificationError, match="reads as 'nothing is assumed'"):
        themis.verify_assumption_ledger(r)


def test_verify_rejects_an_out_of_order_ledger(frames):
    _, r = _run("frontdoor", frames, cluster="c", ci_bootstrap=20)
    bad = _tamper(r, lambda led: led["assumptions"].reverse())
    with pytest.raises(VerificationError, match="not sorted by severity"):
        themis.verify_assumption_ledger(bad)


def test_verify_rejects_a_summary_that_undercounts(frames):
    _, r = _run("iv", frames)
    bad = _tamper(r, lambda led: led.__setitem__("summary", "这个结论依赖 1 条假设。"))
    with pytest.raises(VerificationError, match="does not state"):
        themis.verify_assumption_ledger(bad)


def test_verify_rejects_an_identification_assumption_ranked_below_invalidating(frames):
    _, r = _run("iv", frames)

    def _downgrade(led):
        led["assumptions"][0]["severity"] = "confidence_only"
        led["assumptions"].sort(key=lambda e: e["severity"] != "invalidating")
        n = len(led["assumptions"])
        led["summary"] = (f"这个结论依赖 {n} 条假设：{n - 1} 条一旦不成立、"
                          f"整条因果结论作废；1 条影响形状 / 量级或置信度。")

    with pytest.raises(VerificationError, match="invalidating"):
        themis.verify_assumption_ledger(_tamper(r, _downgrade))


def test_verify_rejects_a_ledger_that_hides_the_audited_mechanism(frames):
    """The mechanism audit is a separate channel; a ledger that folds in the
    estimator's assumptions but not the functional form still under-discloses."""
    _, r = _run("exposure_misclassification", frames)
    assert (r.get("extensions") or {}).get("mechanism_audit")

    def _strip(led):
        led["assumptions"] = [e for e in led["assumptions"]
                              if e["layer"] != "functional_form"]
        n = len(led["assumptions"])
        led["summary"] = f"这个结论依赖 {n} 条假设：{n} 条一旦不成立、整条因果结论作废。"

    with pytest.raises(VerificationError, match="functional_form"):
        themis.verify_assumption_ledger(_tamper(r, _strip))
