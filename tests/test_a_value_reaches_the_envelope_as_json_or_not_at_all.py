"""One conversion, and the input it has to say no to (#318).

Six modules each wrote a numpy → JSON downgrade, and the six disagreed. Four
were ``.item()`` and pass the rest through; two dispatched on numpy kind and
printed anything else into a string; one additionally collapsed an integral
float to an integer. They agreed on every type the suite ever hands them —
``bool`` / ``int`` / ``float`` / ``np.bool_`` / ``np.int64`` / ``np.float64``,
and nothing else, measured over the whole suite — and disagreed everywhere
else, which is what independent rewrites look like as against copies.

What is pinned here is the merged conversion at
:func:`themis.types.envelope_scalar`: what it accepts and what it turns that
into; the values it now refuses BY NAME, where four of the six passed them on
to fail later inside ``json.dumps`` and two printed them into a string the
verifier could not tell from a level that really was one; and the one
deliberate non-merge — discovery's level label, whose integral-float collapse
is a statement about what a level IS on a discrete column and must not travel
with the shared conversion to estimators where 2.0 is a measurement.
"""
from __future__ import annotations

import ast
import datetime
import decimal
import importlib
import json
import pathlib

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation import bounds_numeric, discovery, general_id
from themis.estimation import dispatch, measurement, selection
from themis.estimation.contract import DataContractError
from themis.estimation.discovery import _level_label
from themis.types import envelope_scalar
from themis import response_polytope

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


# ---------------------------------------------------- what it accepts

# The whole domain the six were ever handed, measured by recording every
# call across the suite. A merge is behaviour-preserving exactly here.
MEASURED = [
    (np.bool_(True), True, bool),
    (np.bool_(False), False, bool),
    (np.int64(3), 3, int),
    (np.float64(1.5), 1.5, float),
    (np.float64(2.0), 2.0, float),
    (True, True, bool),
    (3, 3, int),
    (2.0, 2.0, float),
]


@pytest.mark.parametrize("value,expected,expected_type", MEASURED)
def test_the_measured_domain_arrives_as_plain_python(
    value, expected, expected_type
):
    got = envelope_scalar(value)
    assert got == expected
    # ``type`` and not ``isinstance``: np.float64 IS a float subclass, so an
    # isinstance check would pass on a value that still carries numpy.
    assert type(got) is expected_type


def test_a_numpy_string_stops_being_a_numpy_string():
    got = envelope_scalar(np.str_("a"))
    assert got == "a"
    assert type(got) is str


def test_a_plain_string_and_none_travel_unchanged():
    assert envelope_scalar("high") == "high"
    assert envelope_scalar(None) is None


@pytest.mark.parametrize("value,_e,_t", MEASURED)
def test_what_it_returns_is_what_json_writes_down(value, _e, _t):
    # The promise the four ``.item()`` copies made in their docstrings and
    # did not keep. It is a postcondition, so it is checked as one.
    #
    # ``allow_nan=False`` and not the default, because the default writes
    # NaN, Infinity and -Infinity — three tokens json.dumps invents, its
    # own strict mode refuses, and no parser is required to read. Run
    # permissively, this postcondition was true of a value the promise
    # excludes, which is a check asking an easier question than the claim
    # it stands behind.
    json.dumps(envelope_scalar(value), allow_nan=False)


# ---------------------------------------------------- what it refuses

REFUSED = [
    # ``.item()`` lands in the built-in types, and the built-in types are not
    # the JSON ones. Each of these is what a numpy scalar BECOMES.
    (np.datetime64("2020-01-02"), "datetime64"),
    (np.timedelta64(5, "D"), "timedelta64"),
    (np.complex128(1 + 2j), "complex128"),
    # And these never had a numpy step at all.
    (decimal.Decimal("1.5"), "Decimal"),
    (datetime.date(2020, 1, 2), "date"),
    (np.array([1, 2]), "ndarray"),
    ((1, 2), "tuple"),
]

# A float is one of the five and can still be none of them. These arrive
# as the type the envelope accepts, so nothing about the type refuses
# them; what refuses them is that JSON has no word for the value.
NOT_A_JSON_NUMBER = [
    (float("nan"), "NaN"),
    (float("inf"), "Infinity"),
    (float("-inf"), "-Infinity"),
    (np.float64("nan"), "NaN"),
    (np.float64("inf"), "Infinity"),
    (np.float64("-inf"), "-Infinity"),
]


@pytest.mark.parametrize("value,type_name", REFUSED)
def test_a_value_json_cannot_write_is_refused_by_name(value, type_name):
    with pytest.raises(TypeError) as exc:
        envelope_scalar(value)
    assert "reaches the envelope" in str(exc.value)
    assert type_name in str(exc.value)


@pytest.mark.parametrize("value,type_name", REFUSED)
def test_nothing_refused_comes_back_printed(value, type_name):
    # The failure mode of the two kind-dispatching copies: ``str(v)`` is a
    # value the envelope can carry, so nothing downstream ever objected, and
    # the verifier re-deriving from the envelope reads a level that was
    # printed as a level that was a string.
    with pytest.raises(TypeError):
        envelope_scalar(value)


@pytest.mark.parametrize("value,token", NOT_A_JSON_NUMBER)
def test_a_number_json_has_no_word_for_is_refused_by_that_word(value, token):
    with pytest.raises(TypeError) as exc:
        envelope_scalar(value)
    assert "reaches the envelope" in str(exc.value)
    # The token a reader on the other side would be handed, so the message
    # names the thing they would have to parse rather than the float's repr.
    assert token in str(exc.value)


@pytest.mark.parametrize("value,token", NOT_A_JSON_NUMBER)
def test_the_refused_number_is_one_json_dumps_would_have_written(value, token):
    # The two halves of the same claim: the permissive writer produces it,
    # and the strict one refuses it. Without this the token above is a
    # string in a test rather than a statement about JSON.
    assert json.dumps(float(value)) == token
    with pytest.raises(ValueError):
        json.dumps(float(value), allow_nan=False)


def test_a_finite_float_at_the_edge_is_still_a_number():
    # The rule is finiteness, not magnitude: the largest representable
    # float is a number JSON writes down, and rejecting it would be this
    # check overshooting into "is it a sensible value".
    import sys
    for value in (sys.float_info.max, -sys.float_info.max,
                  sys.float_info.min, 0.0, -0.0):
        assert envelope_scalar(value) == value
        json.dumps(envelope_scalar(value), allow_nan=False)


def test_the_refusal_names_what_arrived_not_what_it_became():
    # A numpy clock reading arrives as datetime64 and reaches the check as a
    # date; a message carrying only the second describes a column the reader
    # does not have.
    with pytest.raises(TypeError) as exc:
        envelope_scalar(np.datetime64("2020-01-02"))
    message = str(exc.value)
    assert "datetime64" in message
    assert "date" in message


def test_a_duration_is_refused_rather_than_coerced_to_an_integer():
    # np.timedelta64 subclasses np.signedinteger, so the two copies that
    # dispatched on numpy KIND routed it into ``int()`` and raised from the
    # coercion — a bare TypeError from a line that believed it had a total
    # function, on the branch its own ``str`` fallback was written to catch.
    with pytest.raises(TypeError) as exc:
        envelope_scalar(np.timedelta64(5, "D"))
    assert "reaches the envelope" in str(exc.value)


# ------------------------------------------------ one function, six callers

def _modules_that_name_the_conversion() -> list[str]:
    """Every module under ``themis/`` importing ``envelope_scalar``.

    Read off the source, because the thing this rule has to catch is a
    module nobody remembered — an eighth producer written next year — and
    a list written here is a denominator set by whoever last edited it.
    The seven that exist today are what the scan finds; nothing repeats
    them in this file.
    """
    found: list[str] = []
    for path in sorted((REPO_ROOT / "themis").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and any(
                alias.name == "envelope_scalar" for alias in node.names
            ):
                found.append(
                    ".".join(path.relative_to(REPO_ROOT).with_suffix("").parts)
                )
                break
    return found


def test_the_scan_finds_the_producers_that_exist():
    """The denominator is not empty and not everything."""
    names = _modules_that_name_the_conversion()
    assert "themis.types" not in names       # it declares it, not imports it
    assert len(names) >= 7, names


@pytest.mark.parametrize("name", _modules_that_name_the_conversion())
def test_every_producer_names_the_same_function(name):
    # The gate against re-divergence: six modules held six functions, and
    # what made them drift is that nothing ever compared them.
    module = importlib.import_module(name)
    assert module.envelope_scalar is envelope_scalar, name


def test_the_level_label_is_a_recoding_and_not_the_shared_conversion():
    # discovery reports the LEVELS of a discrete column, and the contract has
    # already cast that column to float64 — so an integer-coded column would
    # be reported as the floats the cast made rather than the codes the data
    # carries. Undoing that is a claim about what a level is, and it must not
    # reach an estimator where an outcome level of exactly 2.0 is a
    # measurement.
    assert _level_label(np.float64(2.0)) == 2
    assert type(_level_label(np.float64(2.0))) is int
    assert type(envelope_scalar(np.float64(2.0))) is float

    assert type(_level_label(np.float64(1.5))) is float
    assert _level_label(np.float64(1.5)) == 1.5


def test_the_level_label_still_refuses_what_the_envelope_cannot_hold():
    # It recodes on top of the shared conversion rather than beside it, so
    # the refusal is not something the second copy has to remember.
    with pytest.raises(TypeError):
        _level_label(datetime.date(2020, 1, 2))


# ------------------------------------------------------- on the real paths

def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _program(w_decl: dict | None = None):
    statements = [
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "y", "domain": [True, False]},
        {"kind": "variable", "predicate": "z", "domain": [True, False]},
        {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
        {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
        {"kind": "query", "id": "q", "query": {"kind": "effect",
            "intervention": {"atom": _atom("x"), "value": True},
            "target": {"atom": _atom("y"), "value": True}, "given": []}},
    ]
    if w_decl is not None:
        statements.insert(3, {"kind": "variable", "predicate": "w", **w_decl})
        statements.insert(-1, {"kind": "cause", "from": _atom("y"),
                               "to": _atom("w")})
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": statements}


def _frame(n=400, seed=0, extra=None):
    rng = np.random.default_rng(seed)
    z = rng.integers(0, 2, n).astype(bool)
    x = (rng.random(n) < 0.3 + 0.4 * z).astype(bool)
    y = (rng.random(n) < 0.2 + 0.3 * x + 0.2 * z).astype(bool)
    frame = pd.DataFrame({"x": x, "y": y, "z": z})
    if extra is not None:
        frame["w"] = extra(n)
    return frame


def test_a_column_the_envelope_could_not_hold_is_refused_by_the_contract():
    # The refusal above is a statement about a value, and on the estimate
    # path no such value gets that far: the contract decides the columns
    # first and names the one it will not take. So the merge does not put a
    # new failure in front of anybody — it names an old one earlier.
    df = _frame(extra=lambda n: [datetime.date(2020, 1, 1 + i % 3)
                                 for i in range(n)])
    with pytest.raises(DataContractError) as exc:
        themis.estimate(_program({"scale": "continuous"}), df)
    assert "'w'" in str(exc.value)


def test_the_estimate_envelope_is_json_and_not_merely_numpy_free():
    """What the four ``.item()`` copies promised, over a whole envelope.

    This is the other arm and it is a weaker one, stated here rather than
    left implied. ``envelope_scalar`` is the single exit for a value READ
    OUT OF THE DATA, and a computed float — an estimate, an interval
    bound, a p-value — reaches the envelope without passing through it.
    Nothing source-side can decide finiteness for those, because it is a
    property of the arithmetic and not of the code; so they are checked
    here, over whatever the corpus reaches, and a branch no case reaches
    is not checked. Measured at the time: 1768 envelopes, no non-finite
    value on either route.
    """
    df = _frame()
    df["w"] = np.arange(len(df)) % 4
    out = themis.estimate(_program({"scale": "binary"}), df)
    json.dumps(out, allow_nan=False)


# ------------------------------------------- the value a caller supplies

def _selection_scm(n, seed):
    """X→Y, X→W, Y→M, M→W: W is a selection collider, recovered on Z⁻={m}."""
    rng = np.random.default_rng(seed)
    x = rng.binomial(1, 0.5, n)
    y = rng.binomial(1, 0.3 + 0.4 * x)
    m = rng.binomial(1, 0.2 + 0.5 * y)
    w = rng.binomial(1, 0.1 + 0.4 * x + 0.4 * m)
    return pd.DataFrame({"x": x.astype(bool), "y": y.astype(bool),
                         "m": m.astype(bool), "w": w.astype(bool)})


def test_a_selected_value_the_envelope_cannot_hold_is_refused_at_the_entry():
    # What "selected" means has to be recorded for the answer to be
    # checkable, so a value that cannot be recorded is this input being
    # refused. Deciding it at the exit let the row filter speak first, and
    # a value that matches no rows leaves an empty sample — so the caller
    # was told the sample was too small, which is the symptom under the
    # name of the cause.
    full = _selection_scm(4_000, seed=0)
    biased = full[full.w].reset_index(drop=True)
    reference = _selection_scm(4_000, seed=1)
    with pytest.raises(TypeError) as exc:
        selection.estimate_selection_recovery(
            biased, reference, treatment="x", outcome="y",
            z_plus=(), z_minus=("m",), selection_nodes=("w",),
            selected_values={"w": datetime.date(2020, 1, 2)},
            ci_bootstrap=0, random_state=0,
        )
    assert "reaches the envelope" in str(exc.value)


def test_what_is_recorded_is_a_value_for_each_selection_node_and_no_other():
    # The schema says selected_values carries the value for EACH selection
    # node; the default, the conversion and that restriction are one
    # statement about the parameter, so they are made in one place.
    full = _selection_scm(20_000, seed=2)
    biased = full[full.w].reset_index(drop=True)
    reference = _selection_scm(20_000, seed=3)
    est = selection.estimate_selection_recovery(
        biased, reference, treatment="x", outcome="y",
        z_plus=(), z_minus=("m",), selection_nodes=("w",),
        selected_values={},
        ci_bootstrap=0, random_state=0,
    )
    assert est.selected_values == {"w": True}
    json.dumps(est.selected_values)
