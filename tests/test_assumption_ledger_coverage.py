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
import ast
import copy
import pathlib

import numpy as np
import pandas as pd
import pytest

import themis
from themis import ledger
from themis.output.analysis_report import build_analysis_report
from themis.output.assumption_glossary import (
    _ANSWERABLE_EXACT,
    _ANSWERABLE_PREFIX,
    _EXACT,
    _PREFIX,
    classify_assumption,
    is_classified,
)
from themis.input.syntactic_validator import SyntacticError
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
        # Rank-preserving and monotone, so the two families whose answers
        # come in a sharper and a bounded mode can be asked both ways off
        # one frame. They were outside this battery until the sweep that
        # would have caught an unclassified declaration from either was
        # asked which families it actually runs.
        "monotone": _monotone_frame(rng, n),
    }


def _monotone_frame(rng, n):
    z = rng.random(n) < 0.5
    u = rng.random(n)
    y0, y1 = u < np.where(z, 0.5, 0.2), u < np.where(z, 0.8, 0.6)
    x = rng.random(n) < np.where(z, 0.7, 0.3)
    return pd.DataFrame({"x": x, "y": np.where(x, y1, y0), "z": z})


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



def _confounded(query):
    return _prog([_var("x", domain=[True, False]), _var("y", domain=[True, False]),
                  _var("z", domain=[True, False]),
                  _cause("z", "x"), _cause("z", "y"), _cause("x", "y"),
                  {"kind": "query", "id": "q", "query": query}])


def _causation_prog(monotonic):
    return _confounded({"kind": "causation", "cause": _atom("x"),
                        "effect": _atom("y"), "monotonic": monotonic})


def _cell_prog(monotonicity):
    q = {"kind": "counterfactual",
         "observed": {"atom": _atom("x"), "value": True},
         "counterfactual_intervention": {"atom": _atom("x"), "value": False},
         "counterfactual_target": {"atom": _atom("y"), "value": True},
         "factual_target_known": False}
    if monotonicity is not None:
        q["assumptions"] = {"monotonicity": monotonicity}
    return _confounded(q)


_MC_X = {"x": {"confusion_matrix": _M(0.9, 0.85), "states": [False, True]}}
_MC_Y = {"y": {"confusion_matrix": _M(0.8, 0.95), "states": [False, True]}}

# name -> (program, data key, extra estimate kwargs)
_BATTERY = {
    "backdoor": (_BACKDOOR, "backdoor", {}),
    # The doubly-robust and weighted arms of the same design. They declare
    # the most beyond identification — which weights, which substitution
    # estimator, how the interval was formed — so they are where a ledger
    # that reads only the identification channel loses the most.
    "backdoor_aipw": (_BACKDOOR, "backdoor", {"ate_estimator": "aipw"}),
    "backdoor_tmle": (_BACKDOOR, "backdoor", {"ate_estimator": "tmle"}),
    "backdoor_ipw": (_BACKDOOR, "backdoor", {"ate_estimator": "ipw"}),
    "frontdoor": (_FRONTDOOR, "frontdoor", {}),
    "iv": (_IV, "iv", {}),
    "mediation": (_MEDIATION, "mediation", {}),
    "exposure_misclassification": (_MEASURED, "misclassified",
                                   {"misclassification": _MC_X}),
    "outcome_misclassification": (_MEASURED, "misclassified",
                                  {"misclassification": _MC_Y}),
    "combined_misclassification": (_MEASURED, "misclassified",
                                   {"misclassification": {**_MC_X, **_MC_Y}}),
    # Both modes of the two families whose answer sharpens under an
    # assertion the caller may withhold. Asking each way is what makes
    # "assuming less rests on less" a question this battery can be asked.
    "causation_monotone": (_causation_prog(True), "monotone", {}),
    "causation_bounded": (_causation_prog(False), "monotone", {}),
    "cell_monotone": (_cell_prog("non_decreasing"), "monotone", {}),
    "cell_bounded": (_cell_prog(None), "monotone", {}),
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
    """The estimator's flat list is the oracle, and every entry of it must be
    on the ledger under its own id — whether it got there as the estimator's
    own entry or as the structured entry that names it.

    The test used to accept a second answer: "or the estimator supplied
    structured identification entries", satisfied by the presence of any
    identification entry at all. That let a family whose structured specs
    covered three of its five declarations pass while the other two went
    nowhere, which is what nineteen of them were doing."""
    _, r = _run(name, frames)
    declared = set(r["numeric_estimate"]["assumptions"])
    entries = _ledger(r)["assumptions"]
    on_ledger = {e["id"] for e in entries if e.get("id")}
    assert declared <= on_ledger, sorted(declared - on_ledger)


@pytest.mark.parametrize("name", sorted(_BATTERY))
def test_the_report_prints_an_assumptions_section(name, frames):
    prog, r = _run(name, frames)
    assert "## 假设" in build_analysis_report(r, program=prog)


@pytest.mark.parametrize("name,expected", [
    ("backdoor_ipw", "hajek_stabilized_weights"),
    ("backdoor_tmle", "tmle_targeted_substitution_estimator"),
    ("backdoor_aipw", "ci_via_analytic_influence_function"),
])
def test_what_the_estimator_declares_beyond_identification_is_disclosed(
    name, expected, frames,
):
    """Named because these are the ones that were being lost. Each is
    something the structured identification specs do not and could not
    restate: a weighting scheme, a substitution estimator, an interval
    method. Under the rule they replaced — any identification entry means
    the whole flat list is a restatement — all three were disclosed
    nowhere at all."""
    _, r = _run(name, frames)
    entries = _ledger(r)["assumptions"]
    assert expected in {e.get("id") for e in entries}


def test_a_structured_spec_replaces_the_declaration_it_names_and_no_other(frames):
    """Back-door supplies structured specs for three of its four declarations.
    Those three appear in the structured wording and not twice; the fourth —
    the outcome model, which no spec claims — is still disclosed."""
    _, r = _run("backdoor", frames)
    entries = _ledger(r)["assumptions"]
    by_id = {e["id"]: e for e in entries if e.get("id")}
    assert [e["layer"] for e in entries].count("identification") == 3
    structured = (
        "conditional_exchangeability_given_adjustment_set",
        "positivity_overlap_of_treatment_arms",
        "consistency_of_potential_outcomes",
    )
    for named in structured:
        assert sum(1 for e in entries if e.get("id") == named) == 1
    # The fold is visible in the CLAIM, which the spec wrote, and not in the
    # provenance: both channels carry the estimator's own assumptions, so
    # telling them apart there would be telling the reader which code path
    # ran.
    # The flat-only declaration is disclosed on the same footing. Its
    # provenance does NOT come from the same place, and that is #423: the
    # three above are identification premises, which the theorem requires of
    # anyone, and the fourth is a SHAPE, which this run resolved out of an
    # outcome column nobody said anything about. Reading it off the id made it
    # ``inherent`` — "required by the method itself" — to a reader holding the
    # argument that changes it.
    assert by_id["logit_outcome_regression"]["claim"]
    for named in structured:
        assert by_id[named]["provenance"] == "inherent"
    assert by_id["logit_outcome_regression"]["provenance"] == "default"


def test_one_assumption_gets_one_answer_about_who_can_overrule_it(frames):
    """The defect this vocabulary was rebuilt around.

    An estimator's assumptions reach the ledger down two channels — the
    structured identification spec and the flat declaration list — and while
    each channel answered ``provenance`` for itself, one id could carry two
    answers at once: ``consistency_of_potential_outcomes`` was ``inherent``
    191 times and ``estimator_declared`` 92 times in one suite run, the same
    sentence telling the reader two different things about what they could do
    about it. Both channels now key on the id, so this holds by construction
    — and a channel that starts answering for itself again breaks it here.

    Every layer but the SHAPE layer, which #423 excluded on purpose. Who
    settled a functional form is a property of the RUN and not of the id, so
    the same id MUST read differently across families — and the way it used to
    satisfy this was that every form line said ``inherent``, including for the
    families where one argument changes it. That answer is pinned per family
    in ``test_the_shape_choice_points_at_a_declared_assumption``.
    """
    seen: dict[str, set] = {}
    for name in sorted(_BATTERY):
        _, r = _run(name, frames)
        for e in (_ledger(r) or {}).get("assumptions") or ():
            if e.get("id") and e["layer"] != "functional_form":
                seen.setdefault(str(e["id"]), set()).add(str(e["provenance"]))
    split = {k: sorted(v) for k, v in seen.items() if len(v) > 1}
    assert not split, f"one assumption, two answers: {split}"


def test_an_assumption_the_method_needs_is_not_the_callers(frames):
    """The other half: the two are told apart by which assumption it is, not
    by a word in it. An IV point estimate IS the LATE and there is no LATE
    without first-stage monotonicity, so the caller cannot withdraw it and
    keep an answer — unlike the outcome monotonicity that pins PN/PS/PNS out
    of their bounds, which shares the word and nothing else."""
    _, r = _run("iv", frames)
    by_id = {e["id"]: e for e in _ledger(r)["assumptions"] if e.get("id")}
    mono = by_id["monotonicity_first_stage_effect_same_sign_for_all_units"]
    assert mono["provenance"] == "inherent"


# --- what may be on the list at all -------------------------------------------


def _monotone_causation_program(monotonic: bool) -> dict:
    def cause(a, b):
        return {"kind": "cause", "from": {"predicate": a, "args": []},
                "to": {"predicate": b, "args": []}}
    return {
        "version": "0.1",
        "domain": {"objects": []},
        "statements": [
            *({"kind": "variable", "predicate": v, "domain": [True, False]}
              for v in ("x", "y", "z")),
            cause("z", "x"), cause("z", "y"), cause("x", "y"),
            {"kind": "query", "id": "q", "query": {
                "kind": "causation",
                "cause": {"predicate": "x", "args": []},
                "effect": {"predicate": "y", "args": []},
                "monotonic": monotonic}},
        ],
    }


def _monotone_causation_frame():
    rng = np.random.default_rng(11)
    n = 4000
    z = rng.random(n) < 0.5
    u = rng.random(n)
    y0, y1 = u < np.where(z, 0.5, 0.2), u < np.where(z, 0.8, 0.6)
    x = rng.random(n) < np.where(z, 0.7, 0.3)
    return pd.DataFrame({"x": x, "y": np.where(x, y1, y0), "z": z})


def _causation_result(monotonic: bool) -> dict:
    return themis.estimate(
        _monotone_causation_program(monotonic), _monotone_causation_frame(),
        ci_bootstrap=0)["results"][0]


def test_an_answer_that_assumes_less_rests_on_less():
    """The membership test for this list, in the one form that is decidable.

    A ledger entry is a claim about the world the answer needs: false, and
    the answer is wrong. Ask the same question twice, once asserting
    monotonicity and once not, and the second answer rests on strictly
    fewer claims — it is the same derivation with one premise withdrawn.
    Both ledgers used to be the same length, because the branch that had
    nothing to declare declared that it had nothing, which reached the
    reader as a fifth thing whose failure voids the conclusion.
    """
    strong = _ledger(_causation_result(True))["assumptions"]
    weak = _ledger(_causation_result(False))["assumptions"]

    claimed = {e["id"] for e in strong if e.get("id")}
    weaker = {e["id"] for e in weak if e.get("id")}
    assert weaker < claimed, (
        f"assuming less added {sorted(weaker - claimed)!r} to the ledger"
    )
    assert claimed - weaker == {"monotonicity_refutable_x_never_prevents_y"}

    n_inval = sum(1 for e in weak if e["severity"] == "invalidating")
    assert f"{n_inval} 条一旦不成立" in ledger.summary(weak, "zh")
    assert n_inval == sum(
        1 for e in strong if e["severity"] == "invalidating") - 1


@pytest.mark.parametrize("stronger,weaker", [("non_decreasing", None)])
def test_the_cell_estimator_declares_less_when_it_assumes_less(stronger, weaker):
    """The same invariant at the producer, over every risk provenance —
    including the one whose branch used to add an entry of its own for a
    do-risk NOT being available."""
    from themis.estimation.counterfactual_cell import _assumptions
    from themis.risk_provenance import ADMISSIBLE

    for provenance in ADMISSIBLE["numeric_counterfactual_cell_estimate"]:
        more = set(_assumptions(provenance, ("z",), stronger, None))
        less = set(_assumptions(provenance, ("z",), weaker, None))
        assert less < more, (
            f"{provenance}: withdrawing monotonicity left {sorted(less - more)!r}"
        )


def test_the_reader_is_still_told_why_there_is_no_point():
    """What the two withdrawn entries were reaching for is real and belongs
    to the answer, so removing them must not take it away. It was already
    said there — this pins that it stays said."""
    r = _causation_result(False)
    report = build_analysis_report(r, program=_monotone_causation_program(False))
    answer = report.split("## 答案", 1)[1].split("##", 1)[0]
    assert "未假设单调性" in answer
    assert "单调性" in answer and "点识别" in answer


def test_a_cell_pinned_with_nothing_to_check_it_says_so_on_that_line():
    """The third entry of the same species carried something real: with no
    do-risk, nothing could have refuted the monotonicity. That is not a
    further assumption — it is what this one can be checked against, so it
    is on this line and not beside it.

    Which is a different question from whether a risk was an input, and the
    two only agreed while the consistency identity was the only solver. The
    response-function polytope consumes no risk and can still empty out under
    the declared direction, so it is refutable — a route reading the line off
    ``uses_risk`` would tell the reader the opposite.
    """
    from themis.estimation.counterfactual_cell import _assumptions
    from themis.risk_provenance import RiskProvenance

    for provenance, refutable in (
        (RiskProvenance.PINNED_BY_MONOTONICITY, False),
        (RiskProvenance.BACKDOOR_ADJUSTMENT, True),
        (RiskProvenance.INSTRUMENT_RESPONSE_POLYTOPE, True),
    ):
        mono = [a for a in _assumptions(provenance, ("z",), "non_decreasing",
                                        None)
                if a.startswith("monotonicity_")]
        assert len(mono) == 1
        # The route half of the answer is in the NAME. It used to be a
        # ``testable`` field on a structured spec, which made the producer a
        # second author of a column this table already keys on the id — and
        # the two had drifted on fifteen other ids by the time this one was
        # right.
        want = "refutable" if refutable else "assumed"
        assert mono[0] == f"monotonicity_{want}_non_decreasing_in_treatment"
        entry = classify_assumption(mono[0])
        assert entry["testable"] is refutable
        assert ("没有可以反驳它的东西" in entry["claim"]) is not refutable


# --- classification -----------------------------------------------------------


def test_an_unclassified_assumption_is_surfaced_not_dropped():
    """The default decides whether adding an estimator can silently lose an
    assumption. It must not."""
    entry = classify_assumption("some_assumption_nobody_has_classified_yet")
    assert entry["claim"] == "some_assumption_nobody_has_classified_yet"
    assert entry["layer"] == "identification"
    # And so invalidating — the glossary does not say that a second time.
    assert entry["layer"].severity == "invalidating"
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


def _written_for_a_reader(keys) -> list[str]:
    """Which of these keys is a sentence in somebody's language, not an id.

    Either mark is enough: a character outside ASCII, or any whitespace.
    Not "no Chinese" — an English sentence keyed here would be the same
    defect, wearing the language the code happens to be written in.

    A runtime SUFFIX is exempt by not being a key. What follows a prefix is
    the caller's own column name, which may be in any language and is not
    this table's to choose; what precedes it is the vocabulary this table
    owns.
    """
    return [k for k in keys if not k.isascii() or any(c.isspace() for c in k)]


def test_no_assumption_is_identified_by_a_sentence():
    """The ledger keys on an id, and a sentence has a language.

    Four rows here were once keyed on how a Chinese declaration OPENS,
    because one estimator declared prose where every other declared ids.
    That made those four the only rows that could not survive their
    estimator speaking a second language: an English declaration does not
    start with 「聚类 bootstrap」, so it would have fallen to the unclassified
    default silently — losing its layer and its severity, not only its
    wording.
    """
    keys = (list(_EXACT) + [p for p, _ in _PREFIX]
            + list(_ANSWERABLE_EXACT) + [p for p, _ in _ANSWERABLE_PREFIX])
    assert keys, "the tables did not load"
    assert _written_for_a_reader(keys) == []
    # And it can see one arriving in either language, while leaving alone an
    # id whose suffix will be filled with a name this table does not choose.
    assert _written_for_a_reader([
        "经典加性测量误差",
        "the outcome is measured with error",
        "ci_via_pairs_cluster_bootstrap_on_",
    ]) == ["经典加性测量误差", "the outcome is measured with error"]


REPO = pathlib.Path(__file__).resolve().parents[1]


def _built_string(node):
    """The literal pieces and the holes of a string built in one expression.

    ``None`` marks a hole — a value only known at runtime. Adjacent literals
    are joined, because how a long id is wrapped across source lines is a
    fact about the line length and not about the id.
    """
    if isinstance(node, ast.JoinedStr):
        parts = [v.value if isinstance(v, ast.Constant) else None
                 for v in node.values]
    elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _built_string(node.left), _built_string(node.right)
        if left is None or right is None:
            return None
        parts = left + right
    elif isinstance(node, ast.Constant):
        return [node.value] if isinstance(node.value, str) else None
    else:
        return [None]
    out: list = []
    for part in parts:
        if isinstance(part, str) and out and isinstance(out[-1], str):
            out[-1] += part
        else:
            out.append(part)
    return out


def _ids_with_a_word_after_the_hole(directory, prefixes):
    """Ids built at runtime that put a word of THIS codebase's after the hole.

    A row whose entry is a plain template fills one hole with everything
    after its prefix, which is a claim about the id: that what follows the
    prefix is the caller's name and nothing else. Where the id ends in a
    literal that still carries letters, the claim is false and that literal
    is handed to the reader inside a sentence.

    Punctuation is not a word. A trailing brace closes the set the caller's
    names are written in and belongs to them, not to this codebase.
    """
    found = {}
    for path in sorted(directory.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.JoinedStr, ast.BinOp)):
                continue
            parts = _built_string(node)
            if not parts or not isinstance(parts[0], str):
                continue
            if not any(parts[0].startswith(p) for p in prefixes):
                continue
            if None not in parts:
                continue
            tail = parts[-1]
            if isinstance(tail, str) and any(c.isalpha() for c in tail):
                found[(path.name, node.lineno)] = f"{path.name}:{node.lineno}"
    return sorted(found.values())


def test_no_id_puts_a_word_of_its_own_after_the_runtime_part():
    """Everything this table owns comes first; the caller's names come last.

    The table reads an id by stripping a prefix, so whatever follows the
    prefix is shown to the reader as their own name. Two ids used to break
    that and both leaked: the back-door one put its word after the set, and
    the clipped-propensity one put its word after the second number. What
    reached the reader was ``{z,w}_sufficient`` and ``0.01_on_37_units``.

    Only rows with a plain template are asked this. A row with a rule has
    taken on parsing its own id and may shape it however it likes — which
    is the other half of the same principle, not an exception to it.
    """
    plain = [p for p, (_layer, _testable, tpl) in _PREFIX if not callable(tpl)]
    assert plain, "the table did not load"
    assert _ids_with_a_word_after_the_hole(REPO / "themis", plain) == []


def test_the_check_sees_a_trailing_word_and_not_a_trailing_brace(tmp_path):
    """The counterexample, beside the two shapes that are not it."""
    (tmp_path / "m.py").write_text(
        'def build(z, c):\n'
        '    a = "backdoor_adjustment_set_sufficient_{" + ",".join(z)'
        ' + "}_needed"\n'
        '    b = f"ci_via_pairs_cluster_bootstrap_on_{c}"\n'
        '    d = "backdoor_adjustment_set_sufficient_{" + ",".join(z) + "}"\n'
        '    return a, b, d\n',
        encoding="utf-8")
    found = _ids_with_a_word_after_the_hole(
        tmp_path, ["backdoor_adjustment_set_sufficient_",
                   "ci_via_pairs_cluster_bootstrap_on_"])
    # ``a`` ends in a word of its own; ``b`` ends in the hole and ``d`` ends
    # in the brace that closes the caller's set.
    assert found == ["m.py:2"]


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
            "testable": False, "provenance": "inherent"})

    with pytest.raises(VerificationError, match="never declared"):
        themis.verify_assumption_ledger(_tamper(r, _add))


def test_verify_rejects_a_line_handed_to_a_caller_who_supplied_nothing(frames):
    """``caller_asserted`` is the one attribution that gives the reader an
    action — withdraw it and the answer comes back wider — so a back-door
    assumption wearing it offers an action they cannot take. Both values are
    legitimate and the pair is one a producer may write, so only re-deriving
    the caller's input from the answer itself catches it."""
    _, r = _run("backdoor", frames)

    def _hand_over(led):
        led["assumptions"][0]["provenance"] = "caller_asserted"

    with pytest.raises(VerificationError, match="records the caller supplying"):
        themis.verify_assumption_ledger(_tamper(r, _hand_over))


def test_verify_rejects_an_identification_assumption_relabelled_as_a_shape(frames):
    """The layer says which part of the answer stops being true and the
    severity grades how badly, so the second follows from the first. Moving
    conditional exchangeability to ``functional_form`` leaves a legal layer,
    a legal severity and a pair a producer may write — and tells the reader
    the average probably survives it, which is the opposite of true."""
    _, r = _run("backdoor", frames)

    def _soften(led):
        entry = next(e for e in led["assumptions"]
                     if e["layer"] == "identification")
        entry["layer"] = "functional_form"

    with pytest.raises(VerificationError, match="ranked 'invalidating'"):
        themis.verify_assumption_ledger(_tamper(r, _soften))


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


def test_a_ledger_carries_no_count_of_itself(frames):
    """What the undercount check became.

    There was a stored one-line summary here whose two facts were the list
    beside it counted, and the only way to check it was to search that line
    for ``依赖 {n} 条假设`` — a rule in one language, about a field the kernel
    wrote in one language. A count that is not stored cannot disagree with
    what it counts, so what is checked is that it is not stored: the envelope
    contract refuses the field, and the line a reader gets is assembled from
    the entries where their language is known.
    """
    _, r = _run("iv", frames)
    led = r["extensions"]["assumption_ledger"]
    assert set(led) == {"assumptions"}

    with pytest.raises(SyntacticError, match="summary"):
        themis.verify_assumption_ledger(
            _tamper(r, lambda l: l.__setitem__("summary", "这个结论依赖 1 条假设。")))

    n = len(led["assumptions"])
    assert f"依赖 {n} 条假设" in ledger.summary(led["assumptions"], "zh")


def test_verify_rejects_an_identification_assumption_ranked_below_invalidating(frames):
    _, r = _run("iv", frames)

    def _downgrade(led):
        led["assumptions"][0]["severity"] = "confidence_only"
        led["assumptions"].sort(key=lambda e: e["severity"] != "invalidating")

    with pytest.raises(VerificationError, match="invalidating"):
        themis.verify_assumption_ledger(_tamper(r, _downgrade))


def test_verify_rejects_a_ledger_that_hides_the_audited_mechanism(frames):
    """The mechanism audit is a separate channel, and the shape of hiding it
    changed when the channel started naming glossary ids.

    It used to be possible to drop the form entry outright and have only this
    check notice, because the entry carried no id and so no other check knew
    it was owed. Now the ids it names are ones the estimator also declared, so
    deleting the entry is caught upstream as a dropped declaration. What is
    left to this check — and to nothing else — is a form assumption RELABELLED
    as something else: the id is still on the ledger, so completeness holds,
    while the reader is told a curve's shape would void the causal conclusion.

    The forgery has to be thorough since #423: relabelling the layer alone now
    trips the pair check on the way past, because no producer writes an
    identification premise the estimator merely defaulted to. So the tampering
    below moves the provenance too — what a forger holding the whitelist would
    do — and this check is still the one that sees the shape line go missing.
    """
    _, r = _run("backdoor", frames)
    assert (r.get("extensions") or {}).get("mechanism_audit")

    def _relabel(led):
        for e in led["assumptions"]:
            if e["layer"] == "functional_form":
                e["layer"] = "identification"
                e["severity"] = "invalidating"
                e["provenance"] = "inherent"

    with pytest.raises(VerificationError, match="functional_form"):
        themis.verify_assumption_ledger(_tamper(r, _relabel))
