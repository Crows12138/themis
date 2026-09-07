"""#472 — a percentile interval carries its truncation and the page did not.

A bootstrap asks for B replicates and gets fewer whenever a refit fails on
one. Skipping such a draw is right: the interval IS over the draws where the
estimand is evaluable, which is what all thirty-five loops in the estimation
package already did. What none of them said is how many that was — and an
interval over 962 draws and one over 1000 are the same two numbers on the
page, so the reader cannot get it back.

Three gates, and they hold three different things:

- The **accumulator** is the way a draw loop is spelled. Thirty-five
  transcriptions of one algorithm are why the count could go missing in all
  of them at once, so the fix is one object rather than thirty-five counters.
- The **source gate** holds every draw site to it, including the ones written
  after this. That is the part that survives the next estimator.
- The **verifier** holds each emitted block to its own arithmetic. A wrong
  count reads exactly like a right one, which is why the block's honesty is
  the thing worth auditing.

The source gate asked whether a loop was COUNTING and not where the number
it counted to came from, and ``Draws(n_rep)`` answers the first question
perfectly. Nothing forwards that number — dispatch hands each estimator the
settings the caller gave, keyword by keyword — so a parameter spelled
differently from the run's is not a wire that breaks but one that was never
drawn: the call site has no such argument, the estimator's default wins
silently, and the envelope goes on recording the caller's ask beside an
interval built on something else. Two mediation loops were spelled that way
and every mediation interval this system reported stood on two hundred
draws, including under a caller who asked for none, which is this system's
documented way to skip the interval. So the gate reads the argument as well
as the loop, and the verifier holds the emitted count against the run.
"""
from __future__ import annotations

import ast
import pathlib

import numpy as np
import pandas as pd
import pytest

import themis
from themis import kernel
from themis.audits import applicable
from themis.estimation.resample import (
    FEWEST_DRAWS,
    UNNAMED,
    Draws,
    share_lost_to,
)
from themis.input.syntactic_validator import validate_result
from themis.refusals import Refusal
from themis.verifier import VerificationError
from themis.verifier.bootstrap_rules import verify_bootstrap_records

_INFEASIBLE = str(Refusal.COUNTERFACTUAL_INPUTS_INFEASIBLE)
_THIN = str(Refusal.STRATA_WOULD_BE_TOO_THIN)


# ============================================ the accumulator


def test_a_draw_loop_counts_what_it_kept_and_what_took_the_rest():
    """The loop is the object. Iterating it is what makes the count exist."""
    draws = Draws(5)
    for i in draws:
        if i < 2:
            draws.usable()
        else:
            draws.unusable(Refusal.STRATA_WOULD_BE_TOO_THIN)
    assert (draws.requested, draws.used, draws.lost) == (5, 2, 3)
    assert draws.discarded == {_THIN: 3}


def test_a_loss_carrying_no_species_is_named_rather_than_dropped():
    """A reader told 3 draws went missing and shown reasons for 1 would read
    the other 2 as not having happened."""
    draws = Draws(3)
    for _ in draws:
        draws.unusable()
    assert draws.discarded == {UNNAMED: 3}
    assert sum(draws.discarded.values()) == draws.lost


def test_one_draw_is_not_a_sampling_distribution():
    """``np.quantile`` of a single value returns that value, so an interval
    over one surviving draw is a point printed twice with a confidence level
    beside it."""
    assert FEWEST_DRAWS == 2
    assert float(np.quantile([0.4], 0.025)) == float(np.quantile([0.4], 0.975))

    one = Draws(10)
    one.usable()
    assert not one.enough
    one.usable()
    assert one.enough


def test_the_record_says_how_the_draws_were_made_and_how_many_survived():
    """One block because it is one question. A reader holding the counts
    without the kind cannot tell a cluster bootstrap's smaller effective
    sample from a discarded draw."""
    clean = Draws(4)
    for _ in clean:
        clean.usable()
    assert clean.record(cluster=None) == {
        "kind": "iid", "requested": 4, "used": 4}
    assert clean.record(cluster="family") == {
        "kind": "cluster", "cluster_column": "family",
        "requested": 4, "used": 4}

    mixed = Draws(4)
    mixed.usable()
    mixed.unusable(Refusal.STRATA_WOULD_BE_TOO_THIN)
    mixed.unusable(Refusal.COUNTERFACTUAL_INPUTS_INFEASIBLE)
    mixed.unusable()
    assert mixed.record(cluster=None)["discarded"] == {
        _INFEASIBLE: 1, _THIN: 1, UNNAMED: 1}


# ============================================ the share one loss carries


def test_the_denominator_is_the_draws_that_answered():
    """A draw lost to a thin stratum was not a vote against monotonicity.
    Counting it as one reports a refutation rate lower than the data's."""
    record = {"requested": 100, "used": 60,
              "discarded": {_INFEASIBLE: 20, _THIN: 20}}
    assert share_lost_to(record, Refusal.COUNTERFACTUAL_INPUTS_INFEASIBLE) == (
        20 / 80)
    # And not 20/100, which is what a denominator of ``requested`` would say.
    assert share_lost_to(
        record, Refusal.COUNTERFACTUAL_INPUTS_INFEASIBLE) != 0.20


def test_no_loss_to_a_reason_is_not_a_share_of_zero():
    """A zero is a different statement: it tells every reader about an
    assumption nothing in their data touched."""
    assert share_lost_to(None, Refusal.COUNTERFACTUAL_INPUTS_INFEASIBLE) is None
    assert share_lost_to(
        {"requested": 9, "used": 9},
        Refusal.COUNTERFACTUAL_INPUTS_INFEASIBLE) is None
    assert share_lost_to(
        {"requested": 9, "used": 8, "discarded": {_THIN: 1}},
        Refusal.COUNTERFACTUAL_INPUTS_INFEASIBLE) is None


# ============================================ what the gate says no to


def _estimate(block: dict, **rest) -> dict:
    return {"numeric_estimate": {
        "method": "backdoor_adjustment", "point": 0.3,
        "ci_lower": 0.1, "ci_upper": 0.5, "bootstrap": block, **rest}}


def _refused(result: dict) -> str:
    with pytest.raises(VerificationError) as exc:
        verify_bootstrap_records(result)
    return str(exc.value)


def test_an_honest_block_is_accepted():
    """The gate discriminates: every rejection below differs from this by one
    fact, and this one passes."""
    verify_bootstrap_records(_estimate(
        {"kind": "iid", "requested": 100, "used": 88,
         "discarded": {_THIN: 12}}))


def test_losses_that_do_not_add_up_are_refused():
    """Unaccounted losses look exactly like no losses, and reasons totalling
    more than the losses mean one draw was filed twice."""
    short = _refused(_estimate(
        {"kind": "iid", "requested": 100, "used": 88,
         "discarded": {_THIN: 5}}))
    assert "12" in short and "5" in short

    over = _refused(_estimate(
        {"kind": "iid", "requested": 100, "used": 88,
         "discarded": {_THIN: 5, UNNAMED: 20}}))
    assert "25" in over

    # The plain case the whole block exists for: draws went missing and
    # nothing says what took them.
    silent = _refused(_estimate(
        {"kind": "iid", "requested": 1000, "used": 962}))
    assert "38" in silent


def test_a_reason_outside_the_vocabulary_is_refused():
    """A free-text reason reaches no reader: the surfaces that act on one
    look it up by species and find nothing."""
    message = _refused(_estimate(
        {"kind": "iid", "requested": 10, "used": 9,
         "discarded": {"fit_was_a_bit_odd": 1}}))
    assert "fit_was_a_bit_odd" in message


def test_a_reason_that_ate_no_draws_is_refused():
    """Said by not being there. A zero row is a reason the reader is invited
    to weigh and the data never raised."""
    assert "0" in _refused(_estimate(
        {"kind": "iid", "requested": 10, "used": 10,
         "discarded": {_THIN: 0}}))


def test_an_interval_reported_over_one_draw_is_refused():
    """And the same loop with no interval is not: a run may legitimately end
    with one usable draw and report no endpoints at all."""
    assert "1 usable draw" in _refused(_estimate(
        {"kind": "iid", "requested": 40, "used": 1,
         "discarded": {_THIN: 39}}))

    verify_bootstrap_records({"numeric_estimate": {
        "method": "backdoor_adjustment", "point": 0.3,
        "ci_lower": None, "ci_upper": None,
        "bootstrap": {"kind": "iid", "requested": 40, "used": 1,
                      "discarded": {_THIN: 39}}}})


def test_a_block_that_exists_says_a_bootstrap_ran():
    """A run of no replicates is said by having no block, so a block claiming
    zero is a producer disagreeing with itself."""
    assert "requested is 0" in _refused(_estimate(
        {"kind": "iid", "requested": 0, "used": 0}))


def test_more_usable_draws_than_drawn_is_refused():
    assert "more draws were usable" in _refused(_estimate(
        {"kind": "iid", "requested": 10, "used": 11}))


def test_a_count_that_is_not_a_count_is_refused():
    assert "must be an integer" in _refused(_estimate(
        {"kind": "iid", "requested": 10, "used": 9.5}))
    assert "must be an integer" in _refused(_estimate(
        {"kind": "iid", "requested": 10, "used": True}))
    assert "must be an object" in _refused(_estimate(
        {"kind": "iid", "requested": 10, "used": 9, "discarded": 1}))
    assert "must be an object" in _refused(_estimate("500 draws"))


def test_every_loop_is_audited_and_not_only_the_estimate_s():
    """Separate loops over separate quantities: auditing the estimate's says
    nothing about the margin table's, and the margin table is where a dead
    first stage eats draws the estimate's own loop never notices."""
    honest = {"kind": "iid", "requested": 50, "used": 50}
    broken = {"kind": "iid", "requested": 50, "used": 40}

    acr = _refused(_estimate(honest, acr_decomposition={
        "margins": [{"step": "1→2", "weight": 0.5, "ci_lower": 0.1,
                     "ci_upper": 0.9}],
        "bootstrap": broken}))
    assert "acr_decomposition" in acr

    ratio = _refused(_estimate(honest, four_way_ratio={
        "cde": {"point": 0.2, "ci_lower": 0.1, "ci_upper": 0.3},
        "bootstrap": broken}))
    assert "four_way_ratio" in ratio

    bounds = _refused({"bounds_results": [
        {"method": "manski_natural", "lower": 0.0, "upper": 1.0,
         "ci_lower": 0.0, "ci_upper": 1.0, "bootstrap": broken}]})
    assert "manski_natural" in bounds


# ============================================ the one loss a reader acts on


def _cell(**over) -> dict:
    cell = {"observed_x": True, "counterfactual_x": False,
            "target_y": True, "factual_y": True,
            "lower": 0.21, "upper": 0.63, "monotonicity": "mtr_positive",
            "monotonicity_refuted_share": 0.25}
    cell.update(over)
    return {"numeric_estimate": {
        "method": "counterfactual_cell_plugin",
        "bootstrap": {"kind": "iid", "requested": 250, "used": 150,
                      "discarded": {_INFEASIBLE: 50, _THIN: 50}},
        "counterfactual_cell": cell}}


def test_the_refuted_share_is_re_derived_rather_than_read():
    """The cell is copied into ``extensions`` where no estimate sits beside
    it, so this share travels as a field — and a field derived from another
    field is a second author unless somebody holds the two equal."""
    verify_bootstrap_records(_cell())          # 50 / (150 + 50)

    diluted = _refused(_cell(monotonicity_refuted_share=50 / 250))
    assert "ANSWERED" in diluted


def test_a_share_standing_where_nothing_was_refuted_is_refused():
    """It tells a reader their data argues against an assumption it never
    touched."""
    result = _cell()
    result["numeric_estimate"]["bootstrap"] = {
        "kind": "iid", "requested": 250, "used": 250}
    assert "never touched" in _refused(result)


def test_a_null_share_where_draws_were_refused_is_refused():
    """The nearest thing this package has to a test of an assumption usually
    called untestable, and a null reads as nothing to report."""
    assert "untestable" in _refused(_cell(monotonicity_refuted_share=None))


# ============================================ the source gate

_ESTIMATION = pathlib.Path(themis.__file__).parent / "estimation"


def _calls(node: ast.AST, name: str) -> bool:
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        func = sub.func
        if isinstance(func, ast.Name) and func.id == name:
            return True
        if isinstance(func, ast.Attribute) and func.attr == name:
            return True
    return False


def _blocks(node: ast.AST) -> list[list[ast.stmt]]:
    """Every statement list belonging to this loop, stopping at a nested one.

    A ``continue`` inside an inner loop is that loop's, and holding the outer
    loop responsible for it would ask a draw site to file a reason for a draw
    it did not skip.
    """
    found: list[list[ast.stmt]] = []
    pending: list[list[ast.stmt]] = [node.body]  # type: ignore[attr-defined]
    while pending:
        block = pending.pop()
        found.append(block)
        for stmt in block:
            if isinstance(stmt, (ast.For, ast.While, ast.FunctionDef,
                                 ast.AsyncFunctionDef, ast.Lambda)):
                continue
            for field in ("body", "orelse", "finalbody"):
                inner = getattr(stmt, field, None)
                if isinstance(inner, list) and inner:
                    pending.append(inner)
            for handler in getattr(stmt, "handlers", ()):
                pending.append(handler.body)
    return found


def _draw_loops(tree: ast.AST) -> list[ast.For | ast.While]:
    """Every loop in one module that draws a bootstrap replicate.

    Innermost, because a resample drawn inside a nested loop belongs to the
    nested one.
    """
    found: list[ast.For | ast.While] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.For, ast.While)):
            continue
        if not any(_calls(s, "resample_indices") for s in node.body):
            continue
        inner = [s for s in ast.walk(node)
                 if isinstance(s, (ast.For, ast.While)) and s is not node
                 and any(_calls(x, "resample_indices") for x in s.body)]
        if not inner:
            found.append(node)
    return found


#: The one name the run's resample count travels under. Dispatch forwards
#: it by keyword, so this is not a convention but the wire itself.
_KNOB = "ci_bootstrap"


def _knob_complaints(tree: ast.AST) -> list[str]:
    """Every ``Draws`` built from something other than the run's own knob.

    Asked of the ARGUMENT and of the enclosing signature, because either
    half alone passes the shape this exists to catch: a local named
    anything would satisfy "there is a variable", and a parameter nobody
    passes to ``Draws`` would satisfy "the signature takes the knob".
    """
    out: list[str] = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        params = {a.arg for a in fn.args.args + fn.args.kwonlyargs}
        for node in ast.walk(fn):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            if name != "Draws" or not node.args:
                continue
            given = node.args[0]
            where = f"{fn.name}:{node.lineno}"
            if not isinstance(given, ast.Name) or given.id != _KNOB:
                out.append(
                    f"{where}: draws {ast.unparse(given)} replicates, and "
                    f"the run's count arrives under the name {_KNOB!r} — a "
                    f"parameter spelled otherwise is never passed at all")
            elif _KNOB not in params:
                out.append(
                    f"{where}: draws {_KNOB} replicates and {fn.name} does "
                    f"not take it, so the number is this module's and not "
                    f"the run's")
    return out


def _complaints(source: str, module: str) -> list[str]:
    """Every way one module's draw sites fail to say what they discarded.

    Read from the source rather than from a run, because the defect is what a
    loop does not do: a draw dropped without a word leaves no trace to observe
    at runtime, which is the whole reason it went unnoticed in thirty-five
    places. Returned as a list rather than asserted here so the rules can be
    shown to reject the shapes they are about.
    """
    tree = ast.parse(source)
    out: list[str] = _knob_complaints(tree)
    for node in _draw_loops(tree):
        where = f"{module}:{node.lineno}"

        # Over a Draws, not over ``range(B)``. A counter can be added to a
        # loop that already exists and a loop cannot be written without one,
        # which is why the count could go missing everywhere at once.
        iterated = node.iter if isinstance(node, ast.For) else None
        if not isinstance(iterated, ast.Name):
            over = ("a while condition" if iterated is None
                    else ast.unparse(iterated))
            out.append(f"{where}: draws over {over}, which is not a Draws a "
                       "reader can be told the size of")
        elif not any(isinstance(n, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == iterated.id
                             for t in n.targets)
                     and _calls(n.value, "Draws")
                     for n in ast.walk(tree)):
            out.append(f"{where}: {iterated.id!r} is never built from Draws")

        # Every draw that leaves early says what took it. This is the defect
        # itself, one draw at a time: the losses stop adding up, and an
        # unaccounted loss reads exactly like no loss.
        for block in _blocks(node):
            for index, stmt in enumerate(block):
                if isinstance(stmt, ast.Continue) and not any(
                        isinstance(earlier, ast.Expr)
                        and _calls(earlier, "unusable")
                        for earlier in block[:index]):
                    out.append(f"{where}: the draw skipped at line "
                               f"{stmt.lineno} files no reason")

        if not _calls(node, "usable"):
            out.append(f"{where}: nothing counts a kept draw")
    return out


def test_every_draw_site_in_the_package_says_what_it_discarded():
    """Including the ones written after this. That is the part of #472 that
    survives the next estimator: a new loop that forgets is a failure here
    rather than an interval nobody can size."""
    seen, built, out = 0, 0, []
    for path in sorted(_ESTIMATION.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        seen += len(_draw_loops(tree))
        built += sum(
            1 for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and (getattr(node.func, "id", None)
                 or getattr(node.func, "attr", None)) == "Draws")
        out += _complaints(source, path.name)
    assert out == []
    # The denominators, low enough not to churn and high enough that a gate
    # reading an empty package would fail here rather than pass silently.
    # Two of them, because the two questions have different subjects: one
    # counts the loops, and the knob is asked of the CONSTRUCTIONS — a gate
    # that stopped finding those would report a package where every draw
    # site takes its size from the run.
    assert seen >= 30
    assert built >= 30


_HONEST = """
def fit(df, ci_bootstrap, rng, n):
    draws = Draws(ci_bootstrap) if ci_bootstrap > 0 else None
    if draws is not None:
        for _ in draws:
            idx = resample_indices(n, rng, groups=None)
            try:
                values.append(point(df.iloc[idx]))
            except EstimatorFailure as exc:
                draws.unusable(exc.failure_type)
                continue
            draws.usable()
"""


def test_the_source_gate_says_no_to_each_shape_it_is_about():
    """The counterexamples, since a gate nobody has seen refuse anything is a
    gate whose reach is unmeasured. Each differs from the honest loop above by
    exactly one fact."""
    assert _complaints(_HONEST, "honest.py") == []

    counted = _complaints(
        _HONEST.replace("for _ in draws:", "for _ in range(ci_bootstrap):"),
        "m.py")
    assert any("not a Draws" in c for c in counted), counted

    borrowed = _complaints(
        _HONEST.replace("draws = Draws(ci_bootstrap) if ci_bootstrap > 0 else None",
                        "draws = neighbouring_estimate.replicates"), "m.py")
    assert any("never built from Draws" in c for c in borrowed), borrowed

    # The shape this system actually shipped: the loop counts, files its
    # reasons and reports honestly — about a number the caller never gave
    # it, because dispatch has no argument by that name to pass.
    renamed = _complaints(_HONEST.replace("ci_bootstrap", "n_rep"), "m.py")
    assert any("arrives under the name" in c for c in renamed), renamed

    # And the half a rename alone would not catch: the right word, taken
    # from the module instead of from the call.
    local = _complaints(
        _HONEST.replace("def fit(df, ci_bootstrap, rng, n):",
                        "def fit(df, rng, n):\n    ci_bootstrap = 200"),
        "m.py")
    assert any("does not take it" in c for c in local), local

    silent = _complaints(
        _HONEST.replace("                draws.unusable(exc.failure_type)\n", ""),
        "m.py")
    assert any("files no reason" in c for c in silent), silent

    uncounted = _complaints(_HONEST.replace("draws.usable()", "pass"), "m.py")
    assert any("nothing counts a kept draw" in c for c in uncounted), uncounted

    # A ``continue`` belonging to a loop nested inside the draw loop is that
    # loop's, and asking the draw site to file a reason for a draw it did not
    # skip would make the gate refuse correct code.
    nested = _complaints(_HONEST.replace(
        "            draws.usable()",
        "            for row in idx:\n"
        "                if row < 0:\n"
        "                    continue\n"
        "            draws.usable()"), "m.py")
    assert nested == [], nested


# ============================================ end to end


def _clustered_frame() -> pd.DataFrame:
    rng = np.random.default_rng(7)
    fam = np.repeat(np.arange(60), 5)
    shift = rng.normal(0, 1.0, 60)[fam]
    a = (rng.random(300) + 0.3 * shift > 0.5)
    y = (rng.random(300) + 0.8 * a + 0.5 * shift > 1.0)
    return pd.DataFrame({"A": a, "Y": y, "fam": fam})


def _program() -> dict:
    A = {"predicate": "A", "args": [{"type": "const", "name": "u"}]}
    Y = {"predicate": "Y", "args": [{"type": "const", "name": "u"}]}
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "u"}]},
        "statements": [
            {"kind": "variable", "predicate": "A"},
            {"kind": "variable", "predicate": "Y"},
            {"kind": "cause", "from": A, "to": Y},
            {"kind": "query", "id": "q1", "query": {
                "kind": "effect", "target": {"atom": Y, "value": True},
                "intervention": {"atom": A, "value": True}, "given": []}},
        ],
    }


def test_a_real_run_says_what_its_interval_stands_on_and_survives_its_audit():
    """The pins above build blocks; this one asks the runtime for one."""
    result = kernel.estimate(
        _program(), _clustered_frame(), random_state=3)["results"][0]
    validate_result(result)

    block = result["numeric_estimate"]["bootstrap"]
    assert block["requested"] >= 1
    assert block["used"] + sum(block.get("discarded", {}).values()) == (
        block["requested"])

    themis.verify_bootstrap_draws(result)
    assert "verify_bootstrap_draws" in {row.name for row in applicable(result)}
