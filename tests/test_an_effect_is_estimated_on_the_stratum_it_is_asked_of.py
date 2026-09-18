"""An effect asked of a stratum is estimated on the stratum's rows.

A question conditioning on ``Z=z`` asks what the treatment does to the
people in that stratum. The identification layer has read the stratum for
as long as there has been one -- the back-door criterion drops a
conditioned variable from the adjustment set, because it is already held
-- and the estimation layer read the whole table. The two halves computed
neither quantity between them: measured on one model where the effect is
0.70 among ``c=True`` and 0.40 over everybody, the g-formula returned
0.49, IPW 0.53, AIPW 0.52 and TMLE 0.54, each adjusting for ``z`` alone
and standardising over every row. Both doors took all four.

What this file holds:

- the rows an effect question is answered on are the rows its stratum
  names, for every route that estimates on the question's own table: the
  contract is restricted once, where the question's facts are assembled,
  so a route added later is about the question as asked without saying
  anything, and a question naming no stratum is still the whole table
- and the answer says so: ``numeric_estimate.given`` carries the stratum,
  written once beside the number rather than by each route
- a stratum the frame barely holds is refused as this question's refusal,
  and the queries beside it are answered
- a route whose estimand is not the one the question conditions to says so
  by asking for the whole table: the IDC plug-in conditions inside its own
  formula and is handed every row, and transport, which cannot narrow a
  target marginal to the asked stratum, declines the question rather than
  answering another one under its name
- the other two entrances into an effect question read the stratum too.
  The longitudinal g-formula, which answers before the loop and makes it
  skip the result, answers on the rows of a stratum the spec's own time
  ordering puts before every treatment, and on a covariate measured after
  one it does not claim the query at all. Missing-data recovery, which
  returns above the data contract because its columns carry NaN, says it
  cannot hold a stratum rather than reporting a number over everybody
- the verifier holds both halves: a number answering a conditional
  question that names no stratum is refused, and one naming another
  stratum than the question's is refused too
- the two rules whose premise was "one table" read the stratum: a row
  count that is the stratum's is allowed where the answer declares it, and
  a count nothing declares is still refused

WHAT IT COSTS. Allowing a second row count costs the run's own record its
hold: the envelope records the table's size once and the estimate's twice,
so an inflated table beside an honestly narrowed estimate is the same
envelope, leaf for leaf, as an honest answer about a smaller stratum of a
bigger table, and the doors have no data to count rows in. It is held from
below -- a part of a table is not bigger than the table, which the last
test here holds -- and the gate's declaration file says so for each shape
that names a stratum.

WHAT THIS FILE DOES NOT CLAIM. Nothing here says the interval beside the
number is the stratum's by any argument other than being computed on its
rows. The bootstrap resamples the restricted frame, which is the right
resampling for a conditional estimand, and the file does not test that
interval's coverage -- the resample tests own that question for the
unconditional case and neither was extended here. Nor does the IDC test
below re-check the value that plug-in returns; ``test_estimation_general_
id_idc`` holds it against enumerated truth, and what is held here is which
rows the route was handed.
"""
from __future__ import annotations

import copy
import itertools
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.contract import validate_data, within_the_stratum
from themis.estimation.strategy import EffectFacts
from themis.refusals import EstimatorFailure
from themis.verifier import VerificationError


def _atom(predicate: str) -> dict:
    return {"predicate": predicate, "args": []}


#: c and z both cause the treatment and the outcome, and the outcome's
#: table gives x a far larger effect where c holds: 0.70 within c=True and
#: 0.40 over the whole table, which is the gap every measurement below is
#: taken across.
_ORDER = ["c", "z", "x", "y"]
_PARENTS = {"c": [], "z": [], "x": ["c", "z"], "y": ["x", "c", "z"]}


def _table(parents: list[str], values: list[float]) -> dict:
    keys = list(itertools.product((True, False), repeat=len(parents)))
    assert len(keys) == len(values), (len(keys), len(values))
    return dict(zip(keys, values))


_CPT = {
    "c": _table([], [0.5]),
    "z": _table([], [0.4]),
    "x": _table(["c", "z"], [0.8, 0.6, 0.35, 0.2]),
    "y": _table(["x", "c", "z"], [0.90, 0.85, 0.35, 0.30,
                                  0.20, 0.15, 0.25, 0.20]),
}


def _simulate(n: int, seed: int = 6955) -> pd.DataFrame:
    rs = np.random.default_rng(seed)
    cols: dict[str, np.ndarray] = {}
    for v in _ORDER:
        if _PARENTS[v]:
            probs = np.array([_CPT[v][tuple(bool(b) for b in row)]
                              for row in zip(*[cols[u] for u in _PARENTS[v]])])
        else:
            probs = np.full(n, _CPT[v][()])
        cols[v] = rs.random(n) < probs
    return pd.DataFrame(cols)


def _p_do(xval: bool, given: dict) -> float:
    num = den = 0.0
    for cfg in itertools.product((True, False), repeat=len(_ORDER)):
        row = dict(zip(_ORDER, cfg))
        if row["x"] != xval or any(row[k] != v for k, v in given.items()):
            continue
        w = 1.0
        for v in _ORDER:
            if v == "x":
                continue
            q = _CPT[v][tuple(row[u] for u in _PARENTS[v])]
            w *= q if row[v] else 1 - q
        den += w
        num += w if row["y"] else 0.0
    return num / den


def _truth(given: dict) -> float:
    return _p_do(True, given) - _p_do(False, given)


def _program(given: dict, *, query_id: str = "q") -> dict:
    statements = [{"kind": "variable", "predicate": v, "domain": [True, False]}
                  for v in _ORDER]
    statements += [{"kind": "cause", "from": _atom(u), "to": _atom(v)}
                   for v in _ORDER for u in _PARENTS[v]]
    statements.append({"kind": "query", "id": query_id, "query": {
        "kind": "effect",
        "intervention": {"atom": _atom("x"), "value": True},
        "target": {"atom": _atom("y"), "value": True},
        "given": [{"atom": _atom(k), "value": v} for k, v in given.items()]}})
    return {"version": "0.1", "domain": {"objects": []},
            "statements": statements}


@pytest.fixture(scope="module")
def frame() -> pd.DataFrame:
    return _simulate(8000)


def _answer(program: dict, frame: pd.DataFrame, **options) -> dict:
    return themis.estimate(copy.deepcopy(program), frame, random_state=7,
                           ci_bootstrap=0, **options)["results"][0]


# --- the rows an answer is computed on ------------------------------------


def test_the_rows_are_the_ones_the_stratum_names(frame):
    """The measurement this file exists for: within the stratum, on the
    stratum's rows, and near the stratum's own effect rather than the
    table's."""
    answer = _answer(_program({"c": True}), frame)
    estimate = answer["numeric_estimate"]
    assert estimate["sample_size"] == int((frame["c"]).sum())
    assert answer["estimation_context"]["sample_size"] == len(frame)
    assert estimate["point"] == pytest.approx(_truth({"c": True}), abs=0.05)
    assert abs(estimate["point"] - _truth({})) > 0.15


@pytest.mark.parametrize("estimator", ["gformula", "ipw", "aipw", "tmle"])
def test_every_estimator_built_on_the_back_door_reads_it(frame, estimator):
    """One restriction, where the question's facts are assembled, so the
    four estimators that answer this question answer it about the same
    people without each being told."""
    answer = _answer(_program({"c": True}), frame, ate_estimator=estimator)
    estimate = answer["numeric_estimate"]
    assert estimate["sample_size"] == int((frame["c"]).sum())
    assert estimate["point"] == pytest.approx(_truth({"c": True}), abs=0.06)


def test_a_question_with_no_stratum_is_still_the_whole_table(frame):
    """The other half of the same claim, and the regression that would
    otherwise be silent: nothing is restricted where nothing was asked."""
    answer = _answer(_program({}), frame)
    estimate = answer["numeric_estimate"]
    assert estimate["sample_size"] == len(frame)
    assert "given" not in estimate
    assert estimate["point"] == pytest.approx(_truth({}), abs=0.05)


def test_the_answer_says_which_people_its_number_is_about(frame):
    """Written once beside the number rather than by each route."""
    answer = _answer(_program({"c": True, "z": False}), frame)
    assert answer["numeric_estimate"]["given"] == [["c", True], ["z", False]]


def test_the_stratum_is_written_in_the_questions_order(frame):
    answer = _answer(_program({"z": True, "c": False}), frame)
    assert answer["numeric_estimate"]["given"] == [["z", True], ["c", False]]


def test_the_step_names_the_variables_and_the_estimate_names_their_values(
        frame):
    """One fact in two spellings. The identification step records WHICH
    variables the question holds; the estimate records the stratum they
    single out. A door comparing the two as written would refuse every
    honest conditional answer, so the copy rule compares them by name."""
    program = _program({"c": True})
    answer = _answer(program, frame)
    held = answer["derivation"]["steps"][0]["inputs"]["given"]
    assert [atom["predicate"] for atom in held["items"]] == ["c"]
    assert answer["numeric_estimate"]["given"] == [["c", True]]
    themis.verify(copy.deepcopy(program), copy.deepcopy(answer))


# --- the contract's own view ----------------------------------------------


def test_the_view_is_the_same_contract_read_on_fewer_rows(frame):
    contract = validate_data(frame, required_columns=_ORDER)
    view = within_the_stratum(contract, (("c", True),))
    assert view.columns == contract.columns
    assert view.sample_size == int(frame["c"].sum()) < contract.sample_size
    assert view.data_hash != contract.data_hash
    assert bool(view.data["c"].all())


def test_a_stratum_of_nothing_is_the_whole_table(frame):
    contract = validate_data(frame, required_columns=_ORDER)
    assert within_the_stratum(contract, ()) is contract


def test_two_strata_of_one_table_do_not_share_a_fingerprint(frame):
    contract = validate_data(frame, required_columns=_ORDER)
    one = within_the_stratum(contract, (("c", True),))
    other = within_the_stratum(contract, (("c", False),))
    assert one.data_hash != other.data_hash
    assert one.sample_size + other.sample_size == contract.sample_size


def test_a_stratum_the_frame_barely_holds_is_the_estimators_refusal(frame):
    """Raised as a refusal and not as a contract error: the frame is fine,
    and what cannot be answered on it is this question."""
    thin = frame[:40].copy()
    thin["c"] = False
    thin.loc[thin.index[:4], "c"] = True
    with pytest.raises(EstimatorFailure) as caught:
        within_the_stratum(
            validate_data(thin, required_columns=_ORDER), (("c", True),))
    assert str(caught.value.failure_type) == "too_few_rows_in_the_stratum_asked"
    assert caught.value.details["rows"] == 4


# --- and the question that cannot be answered on them ---------------------


def test_a_thin_stratum_is_this_questions_refusal_and_not_the_runs(frame):
    """The other queries are about other people and are answered."""
    thin = frame.copy()
    thin["c"] = False
    thin.loc[thin.index[:4], "c"] = True
    program = _program({"c": True})
    program["statements"].append({"kind": "query", "id": "q2", "query": {
        "kind": "effect",
        "intervention": {"atom": _atom("x"), "value": True},
        "target": {"atom": _atom("y"), "value": True},
        "given": []}})
    results = themis.estimate(program, thin, random_state=7,
                              ci_bootstrap=0)["results"]
    refused = next(r for r in results if r.get("query_id") == "q")
    answered = next(r for r in results if r.get("query_id") == "q2")
    assert "numeric_estimate" not in refused
    assert (refused["estimator_failure"]["failure_type"]
            == "too_few_rows_in_the_stratum_asked")
    assert answered["numeric_estimate"]["sample_size"] == len(thin)


# --- the routes whose estimand is not the one the question conditions to --


def _facts(**overrides):
    fields = dict(
        q_stmt=SimpleNamespace(query=None), graph=None, bidirected=(),
        feedback=None, prog=None,
        ate_estimator="gformula", misclassification=None,
        measurement_error=None, selection_recovery=None,
        dose_response_triggered=False,
    )
    fields.update(overrides)
    return EffectFacts(**fields)


def test_a_route_is_handed_the_stratum_unless_it_asks_for_the_table():
    """The default is the narrower of the two, which is what makes a route
    added later about the question as asked without saying anything."""
    stratum, table = object(), object()
    assert _facts(contract=stratum).whole is stratum
    narrowed = _facts(contract=stratum, whole=table)
    assert narrowed.contract is stratum and narrowed.whole is table


def _idc_program(zval: bool) -> dict:
    """Z->X->M->Y with X<->Y and Z<->Y: Z survives the exchange, so the
    conditional estimand is a fraction and the rows outside the stratum are
    part of its denominator."""
    def a(p):
        return {"predicate": p, "args": [{"type": "const", "name": "me"}]}

    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": v, "domain": [True, False]}
            for v in ("z", "x", "m", "y")
        ] + [
            {"kind": "cause", "from": a("z"), "to": a("x")},
            {"kind": "cause", "from": a("x"), "to": a("m")},
            {"kind": "cause", "from": a("m"), "to": a("y")},
            {"kind": "bidirected", "left": a("x"), "right": a("y")},
            {"kind": "bidirected", "left": a("z"), "right": a("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": a("x"), "value": True},
                "target": {"atom": a("y"), "value": True},
                "given": [{"atom": a("z"), "value": zval}]}},
        ],
    }


def _idc_frame(n: int = 12000, seed: int = 8) -> pd.DataFrame:
    rs = np.random.default_rng(seed)
    u = rs.random(n) < 0.3
    w = rs.random(n) < 0.6
    z = rs.random(n) < np.where(w, 0.8, 0.2)
    x = rs.random(n) < np.where(z ^ u, 0.7, 0.25)
    m = rs.random(n) < np.where(x, 0.9, 0.15)
    y = rs.random(n) < (0.2 + 0.5 * m + 0.15 * u + 0.1 * w)
    return pd.DataFrame({"z": z, "x": x, "m": m, "y": y})


def test_a_formula_that_conditions_inside_itself_reads_every_row():
    """The IDC plug-in identifies P(Y | do(X), Z=z) as a ratio over the
    whole joint distribution, so restricting to the stratum would delete
    its denominator. It asks for the table and still says which people its
    number is about."""
    program = _idc_program(True)
    frame = _idc_frame()
    answer = _answer(program, frame)
    estimate = answer["numeric_estimate"]
    assert estimate["method"] == "general_id_idc_plugin"
    assert estimate["sample_size"] == len(frame)
    assert estimate["given"] == [["z", True]]
    themis.verify(copy.deepcopy(program), copy.deepcopy(answer))


def _transport_program(given: tuple) -> dict:
    def a(p):
        return {"predicate": p, "args": [{"type": "const", "name": "me"}]}

    def cause(u, v):
        return {"kind": "cause", "from": a(u), "to": a(v)}

    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": v, "domain": [True, False]}
            for v in ("z", "c", "x", "y")
        ] + [
            cause("z", "x"), cause("z", "y"), cause("x", "y"),
            cause("c", "x"), cause("c", "y"),
            {"kind": "selection_node", "id": "s_z", "affects": a("z"),
             "source_population": "trial", "target_population": "user"},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "given": [{"atom": a(k), "value": v} for k, v in given],
                "target": {"atom": a("y"), "value": True},
                "intervention": {"atom": a("x"), "value": True},
                "target_population": "user"}},
        ],
        "extensions": {
            "target_marginal": {"predicate": "z",
                                "marginal": {"true": 0.7, "false": 0.3}},
        },
    }


@pytest.fixture(scope="module")
def transport_frame() -> pd.DataFrame:
    rs = np.random.default_rng(7)
    n = 4000
    z = rs.random(n) < 0.4
    c = rs.random(n) < 0.5
    x = rs.random(n) < (0.2 + 0.4 * z + 0.2 * c)
    y = rs.random(n) < (0.1 + 0.3 * x + 0.3 * z + 0.2 * c)
    return pd.DataFrame({"z": z, "c": c, "x": x, "y": y})


def test_transporting_reads_the_source_sample_whole(transport_frame):
    """Post-stratification re-weights the source's strata by the target's
    marginal, which is a statement about every row of the source."""
    program = _transport_program(())
    estimate = _answer(program, transport_frame)["numeric_estimate"]
    assert estimate["method"] == "transport_post_stratification"
    assert estimate["sample_size"] == len(transport_frame)


def test_a_target_population_asked_of_a_stratum_gets_no_number(
        transport_frame):
    """What the program declares about the target is one marginal over the
    adjustment set, and no distribution on the envelope says what the asked
    stratum looks like there. So the structural answer stands and no number
    is attached -- the alternative is the whole target's effect reported
    under the stratum's name."""
    program = _transport_program((("c", True),))
    answer = _answer(program, transport_frame)
    assert answer["status"] == "structurally_solved"
    assert "numeric_estimate" not in answer
    themis.verify(copy.deepcopy(program), copy.deepcopy(answer))


def _longitudinal_program(given: tuple) -> dict:
    """A time-varying program: c and l0 before the first treatment, l1
    after it. The g-formula runs before the effect-query loop and claims
    the result, so it is the other entrance an effect question can be
    answered through."""
    order = ("c", "l0", "a0", "l1", "a1", "y")
    edges = (("c", "a0"), ("c", "y"), ("l0", "a0"), ("l0", "y"),
             ("a0", "l1"), ("a0", "y"), ("l1", "a1"), ("l1", "y"),
             ("a1", "y"))
    return {
        "version": "0.1",
        "domain": {"objects": []},
        "statements": [
            {"kind": "variable", "predicate": v, "domain": [True, False]}
            for v in order
        ] + [
            {"kind": "cause", "from": _atom(u), "to": _atom(v)}
            for u, v in edges
        ] + [
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("a0"), "value": True},
                "target": {"atom": _atom("y"), "value": True},
                "given": [{"atom": _atom(k), "value": v} for k, v in given]}},
        ],
        "options": {"longitudinal": {
            "treatments": ["a0", "a1"],
            "confounders_by_time": [["c", "l0"], ["l1"]],
            "outcome": "y",
        }},
    }


@pytest.fixture(scope="module")
def longitudinal_frame() -> pd.DataFrame:
    rs = np.random.default_rng(11)
    n = 6000
    c = rs.random(n) < 0.5
    l0 = rs.random(n) < 0.4
    a0 = rs.random(n) < (0.2 + 0.3 * c + 0.3 * l0)
    l1 = rs.random(n) < (0.2 + 0.5 * a0)
    a1 = rs.random(n) < (0.2 + 0.5 * l1)
    y = rs.random(n) < np.clip(
        0.1 + 0.25 * a0 + 0.25 * a1 + 0.2 * c + 0.1 * l0, 0, 1)
    return pd.DataFrame({"c": c, "l0": l0, "a0": a0, "l1": l1, "a1": a1,
                         "y": y})


def test_the_other_entrance_into_an_effect_question_reads_it_too(
        longitudinal_frame):
    """This pass answers before the loop does and the loop then skips the
    result, so it reads the stratum itself: on a covariate the spec's own
    ordering puts before every treatment, it answers on that stratum's rows
    and says so."""
    program = _longitudinal_program((("c", True),))
    answer = _answer(program, longitudinal_frame)
    estimate = answer["numeric_estimate"]
    assert estimate["method"] == "longitudinal_gformula"
    assert estimate["sample_size"] == int(longitudinal_frame["c"].sum())
    assert estimate["given"] == [["c", True]]
    whole = _answer(_longitudinal_program(()), longitudinal_frame)
    assert whole["numeric_estimate"]["point"] != estimate["point"]
    themis.verify_answer_claims(copy.deepcopy(program), copy.deepcopy(answer))
    themis.verify(copy.deepcopy(program), copy.deepcopy(answer))


def test_an_entrance_that_cannot_hold_a_later_covariate_stands_aside(
        longitudinal_frame):
    """A g-formula has no way to condition on a covariate measured after a
    treatment, and the cascade's conditional route does -- it conditions
    inside its own formula. So this pass does not claim the query rather
    than answering a different one under it."""
    program = _longitudinal_program((("l1", True),))
    answer = _answer(program, longitudinal_frame)
    estimate = answer["numeric_estimate"]
    assert not estimate["method"].startswith("longitudinal_")
    assert estimate["given"] == [["l1", True]]
    themis.verify_answer_claims(copy.deepcopy(program), copy.deepcopy(answer))
    themis.verify(copy.deepcopy(program), copy.deepcopy(answer))


def test_a_route_that_cannot_hold_a_stratum_says_so_instead_of_a_number(
        frame):
    """The third entrance: missing-data recovery returns above the data
    contract, because the columns it recovers from carry NaN, and before
    the loop. It cannot restrict a partially observed frame by a stratum --
    taking the rows where a column equals a value selects on having
    observed it, which is the bias the route exists to undo -- so it says
    that rather than reporting a number over everybody."""
    from tests import partially_observed

    program = partially_observed.program()
    for statement in program["statements"]:
        if statement.get("kind") == "query":
            statement["query"]["given"] = [
                {"atom": {"predicate": "z",
                          "args": [{"type": "const", "name": "p"}]},
                 "value": True}]
    answer = _answer(program, partially_observed.frame())
    assert "numeric_estimate" not in answer
    assert (answer["estimator_failure"]["failure_type"]
            == "no_estimate_within_the_stratum_asked")
    themis.verify_answer_claims(copy.deepcopy(program), copy.deepcopy(answer))


def test_the_same_route_still_answers_the_question_it_was_built_for(frame):
    """And the marginal question it does answer is untouched."""
    from tests import partially_observed

    program = partially_observed.program()
    answer = _answer(program, partially_observed.frame())
    assert (answer["numeric_estimate"]["method"]
            == "missing_data_recovery_gformula")
    assert "given" not in answer["numeric_estimate"]
    themis.verify_answer_claims(copy.deepcopy(program), copy.deepcopy(answer))


# --- what the doors hold --------------------------------------------------


def _doors(program: dict, answer: dict):
    for door in ("verify_answer_claims", "verify"):
        with pytest.raises(VerificationError):
            getattr(themis, door)(copy.deepcopy(program), copy.deepcopy(answer))


def test_an_honest_answer_passes_every_door_that_reads_it(frame):
    program = _program({"c": True})
    answer = _answer(program, frame)
    themis.verify_answer_claims(copy.deepcopy(program), copy.deepcopy(answer))
    themis.verify(copy.deepcopy(program), copy.deepcopy(answer))


def test_a_number_that_names_no_stratum_is_refused(frame):
    program = _program({"c": True})
    answer = _answer(program, frame)
    answer["numeric_estimate"].pop("given")
    _doors(program, answer)


def test_a_number_naming_another_stratum_is_refused(frame):
    program = _program({"c": True})
    answer = _answer(program, frame)
    answer["numeric_estimate"]["given"] = [["c", False]]
    _doors(program, answer)


def test_a_number_naming_another_variable_is_refused(frame):
    program = _program({"c": True})
    answer = _answer(program, frame)
    answer["numeric_estimate"]["given"] = [["z", True]]
    _doors(program, answer)


def test_the_tables_row_count_written_over_the_stratums_is_refused(frame):
    program = _program({"c": True})
    answer = _answer(program, frame)
    answer["numeric_estimate"]["sample_size"] = (
        answer["estimation_context"]["sample_size"])
    _doors(program, answer)


def test_the_whole_tables_answer_moved_onto_the_question_is_refused(frame):
    """The forgery this frontier's own bug used to be."""
    program = _program({"c": True})
    whole = _answer(_program({}), frame)
    whole["query_id"] = "q"
    _doors(program, whole)


def test_a_count_no_answer_declares_is_refused(frame):
    """The row-count rule still holds every other copy to the table: the
    stratum's count is allowed because the answer says which stratum, and
    a second number with nothing declaring it is not."""
    program = _program({})
    answer = _answer(program, frame)
    answer["numeric_estimate"]["sample_size"] = 11
    _doors(program, answer)


def test_a_stratum_bigger_than_the_table_is_refused(frame):
    program = _program({"c": True})
    answer = _answer(program, frame)
    answer["estimation_context"]["sample_size"] = 10
    _doors(program, answer)
