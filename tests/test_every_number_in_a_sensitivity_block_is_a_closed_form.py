"""A sensitivity block's totality is a list, not a sentence.

``verify_ovb_sensitivity`` said every number in the block was a closed
form of the recorded statistics and that it recomputed them all. It
recomputed seven of the nine: ``adjusted_se`` and ``adjusted_t`` arrived
beside ``adjusted_estimate`` after the sentence was written and the loop
stopped at the field it already had. Sixteen leaves of the declared
remainder sat under this block.

What a reader does with them is the reason it matters. The block answers
"how strong would an unmeasured confounder have to be to overturn this",
and a benchmark answers it in the units of a covariate that WAS adjusted
for -- a confounder as strong as this one leaves the estimate here, with
this standard error, at this t. A forged ``adjusted_se`` moves the last
two without touching anything a rule looked at, and a finding a benchmark
confounder would overturn reads as one it would not.

So the fix is not two more comparisons. The rule now names what it reads
and what it rebuilds as two sets, and this file holds them against the
schema's own field list: every field the contract declares is in exactly
one of them. A field added to this block tomorrow fails here until
somebody says which kind it is, which is the totality the docstring could
only assert.

The three recorded statistics are one fact. An OLS t-value IS the
coefficient over its standard error, so the block cannot be asked to
rebuild any of the three and can be asked for the identity -- which is
what holds ``estimate`` and ``se``, neither of them a function of
anything else the envelope carries.
"""
from __future__ import annotations

import copy
import json
import math
import pathlib

import pytest

import themis
from themis.verifier.errors import VerificationError
from themis.verifier.verify import (
    _OVB_BENCHMARK_REBUILT,
    _OVB_BENCHMARK_RECORDED,
    _OVB_REBUILT,
    _OVB_RECORDED,
    verify_ovb_sensitivity,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
REPO = FIXTURES.parent.parent
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))
SCHEMA = json.loads(
    (REPO / "themis" / "schemas" / "query_result.schema.json")
    .read_text(encoding="utf-8"))

BLOCK_SCHEMA = (SCHEMA["properties"]["numeric_estimate"]["properties"]
                ["ovb_sensitivity"])
BENCHMARK_SCHEMA = BLOCK_SCHEMA["properties"]["benchmarks"]["items"]

#: Every stored answer carrying the block. The forgeries below are asked of
#: all of them, because "which shapes a rule reached" is the defect this
#: package keeps meeting.
CARRYING = sorted(
    name for name, pair in SHAPES.items()
    if isinstance((pair["result"].get("numeric_estimate") or {})
                  .get("ovb_sensitivity"), dict))

#: Of those, the ones whose benchmark list is non-empty. A block with an
#: empty adjustment set benchmarks nothing, and half the fields below do
#: not exist on it.
WITH_BENCHMARKS = sorted(
    name for name in CARRYING
    if (SHAPES[name]["result"]["numeric_estimate"]["ovb_sensitivity"]
        .get("benchmarks")))

ROSTER = 5
BENCHMARKED = 2


def test_the_roster_is_the_size_this_file_was_written_against():
    """An empty parametrisation is a green test that asks nothing."""
    assert len(CARRYING) == ROSTER, CARRYING
    assert len(WITH_BENCHMARKS) == BENCHMARKED, WITH_BENCHMARKS


# ------------------------------------------------- the totality, structural


def test_every_field_the_contract_declares_is_read_or_rebuilt():
    """The list the docstring used to be.

    Not a spelling of the schema kept beside it: the sets are what the
    rule branches on, so a field that joins neither is a field the rule
    never mentions.
    """
    declared = set(BLOCK_SCHEMA["properties"])
    assert declared == _OVB_RECORDED | _OVB_REBUILT, (
        declared ^ (_OVB_RECORDED | _OVB_REBUILT))
    assert not (_OVB_RECORDED & _OVB_REBUILT)


def test_every_benchmark_field_the_contract_declares_is_read_or_rebuilt():
    declared = set(BENCHMARK_SCHEMA["properties"])
    assert declared == _OVB_BENCHMARK_RECORDED | _OVB_BENCHMARK_REBUILT, (
        declared ^ (_OVB_BENCHMARK_RECORDED | _OVB_BENCHMARK_REBUILT))
    assert not (_OVB_BENCHMARK_RECORDED & _OVB_BENCHMARK_REBUILT)


def test_the_contract_requires_every_field_both_sets_name():
    """So the sets cannot be satisfied by a field that may be absent."""
    assert set(BLOCK_SCHEMA["required"]) == _OVB_RECORDED | _OVB_REBUILT
    assert (set(BENCHMARK_SCHEMA["required"])
            == _OVB_BENCHMARK_RECORDED | _OVB_BENCHMARK_REBUILT)


# ------------------------------------------ the identity the three of them owe


@pytest.mark.parametrize("shape", CARRYING)
@pytest.mark.parametrize("field", ["estimate", "se", "t_statistic"])
def test_the_recorded_triple_is_held_to_being_one_fact(shape, field):
    """None of the three is a closed form of anything else here; together
    they are checkable, and that is the whole of what holds two of them."""
    pair = SHAPES[shape]
    result = copy.deepcopy(pair["result"])
    block = result["numeric_estimate"]["ovb_sensitivity"]
    block[field] = block[field] * 2.0 + 1.0
    with pytest.raises(VerificationError):
        themis.verify(pair["program"], result)


def test_the_identity_holds_on_every_stored_block():
    """Measured rather than assumed: a rule resting on an identity the
    corpus does not satisfy would refuse every honest answer."""
    for shape in CARRYING:
        b = SHAPES[shape]["result"]["numeric_estimate"]["ovb_sensitivity"]
        assert math.isclose(b["t_statistic"] * b["se"], b["estimate"],
                            rel_tol=1e-9, abs_tol=1e-12), shape


def test_the_identity_is_multiplied_because_one_stored_fit_is_degenerate():
    """The reason the check is ``est == t * se`` and not ``est / se == t``.

    One stored answer fits perfectly: its standard error is 1e-17 and its
    t-value 8e16. A quotient there is the ratio of two roundings, and the
    tolerance that would have to admit it would admit anything.
    """
    tiny = [s for s in CARRYING
            if SHAPES[s]["result"]["numeric_estimate"]["ovb_sensitivity"]["se"]
            < 1e-12]
    assert tiny, "the degenerate fit this reasoning is about has left"
    b = SHAPES[tiny[0]]["result"]["numeric_estimate"]["ovb_sensitivity"]
    assert math.isclose(b["t_statistic"] * b["se"], b["estimate"],
                        rel_tol=1e-9)


# --------------------------------------------------- the benchmark's own three


@pytest.mark.parametrize("shape", WITH_BENCHMARKS)
@pytest.mark.parametrize("field", ["adjusted_se", "adjusted_t"])
def test_an_adjusted_number_is_rebuilt_wherever_the_block_appears(
        shape, field):
    """Asked of every shape carrying one, because which shapes a rule
    reached is the defect this package keeps meeting."""
    pair = SHAPES[shape]
    result = copy.deepcopy(pair["result"])
    bm = result["numeric_estimate"]["ovb_sensitivity"]["benchmarks"][0]
    bm[field] = bm[field] * 2.0 + 1.0
    with pytest.raises(VerificationError, match=field):
        themis.verify(pair["program"], result)


@pytest.mark.parametrize("shape", WITH_BENCHMARKS)
def test_a_benchmark_names_a_covariate_the_estimate_adjusted_for(shape):
    """The producer refuses a benchmark outside the adjustment set; this
    is the same fact read from the answer instead of from the data."""
    pair = SHAPES[shape]
    result = copy.deepcopy(pair["result"])
    bm = result["numeric_estimate"]["ovb_sensitivity"]["benchmarks"][0]
    bm["covariate"] = "a_column_no_document_names"
    with pytest.raises(VerificationError, match="does not adjust for"):
        themis.verify(pair["program"], result)


@pytest.mark.parametrize("shape", WITH_BENCHMARKS)
def test_one_covariate_does_not_get_two_answers(shape):
    pair = SHAPES[shape]
    result = copy.deepcopy(pair["result"])
    block = result["numeric_estimate"]["ovb_sensitivity"]
    block["benchmarks"] = block["benchmarks"] + [
        copy.deepcopy(block["benchmarks"][0])]
    with pytest.raises(VerificationError, match="benchmarked twice"):
        themis.verify(pair["program"], result)


#: A benchmark whose bound comes out FINITE and out of range. The distinct
#: case from a bound that is undefined, which the rule already refused: the
#: numbers exist, they are simply not a partial R², and the branch that
#: says so is the one this file added.
_OUT_OF_RANGE = {"kd": 1.0, "ky": 4.0, "r2dxj_x": 0.05, "r2yxj_dx": 0.5}


def _bound(kd, ky, r2dxj_x, r2yxj_dx):
    """The bound, recomputed here so the fixture below is honest about it.

    Named as the contract names them, so the fixture and this can be one
    dict rather than two spellings of one.
    """
    r2dz = kd * (r2dxj_x / (1.0 - r2dxj_x))
    r2zxj = (kd * (r2dxj_x ** 2)
             / ((1.0 - kd * r2dxj_x) * (1.0 - r2dxj_x)))
    r2yz = (((math.sqrt(ky) + math.sqrt(r2zxj)) / math.sqrt(1.0 - r2zxj)) ** 2
            * (r2yxj_dx / (1.0 - r2yxj_dx)))
    return r2dz, r2yz


def test_a_bound_out_of_range_buys_no_adjusted_numbers():
    """Synthetic, because no stored block has an invalid benchmark.

    The corpus is a sample and not the system, so the branch is exercised
    here rather than left to whichever answer happens to arrive. Before
    this, the only field an out-of-range verdict moved was the verdict:
    the three adjusted numbers beside it could say anything.
    """
    r2dz, r2yz = _bound(**_OUT_OF_RANGE)
    assert math.isfinite(r2dz) and math.isfinite(r2yz), (r2dz, r2yz)
    assert 0.0 <= r2dz < 1.0, r2dz
    assert not (0.0 <= r2yz <= 1.0), r2yz

    def benchmark(**over):
        row = dict(_OUT_OF_RANGE, covariate="z", r2dz_x=r2dz, r2yz_dx=r2yz,
                   valid=False, adjusted_estimate=None, adjusted_se=None,
                   adjusted_t=None)
        row.update(over)
        return _honest({
            "estimate": 1.0, "se": 0.5, "t_statistic": 2.0, "dof": 100,
            "q": 1.0, "alpha": 0.05, "partial_r2": 0.0,
            "robustness_value_q": 0.0, "robustness_value_qa": 0.0,
            "benchmarks": [row],
        })

    verify_ovb_sensitivity(benchmark(), ["z"])  # the honest silence

    for field, forged in (("adjusted_estimate", 0.9), ("adjusted_se", 0.1),
                          ("adjusted_t", 9.0)):
        with pytest.raises(VerificationError, match="benchmarks nothing"):
            verify_ovb_sensitivity(benchmark(**{field: forged}), ["z"])


def _honest(block: dict) -> dict:
    """The block with its two robustness values set to what the rule
    recomputes, so a test about one field is not answered by another."""
    import math as _m

    from scipy.stats import t as _t

    out = copy.deepcopy(block)
    t, dof, q, alpha = out["t_statistic"], out["dof"], out["q"], out["alpha"]

    def rv(a):
        fq = q * abs(t / _m.sqrt(dof))
        fc = abs(_t.ppf(a / 2.0, dof - 1)) / _m.sqrt(dof - 1)
        fqa = fq - fc
        if fqa < 0:
            return 0.0
        if fc > 0 and fq > 1.0 / fc:
            return (fq * fq - fc * fc) / (1.0 + fq * fq)
        return 0.5 * (_m.sqrt(fqa ** 4 + 4.0 * fqa ** 2) - fqa ** 2)

    out["partial_r2"] = t * t / (t * t + dof)
    out["robustness_value_q"] = rv(1.0)
    out["robustness_value_qa"] = rv(alpha)
    return out


# ------------------------------------------------------------ what is left


#: The degenerate fit's three settings. They stay open and this says why.
STILL_OPEN = {"alpha", "dof", "q"}


def test_what_a_degenerate_fit_leaves_open_is_named():
    """One stored answer fits perfectly, and on it the rebuilt numbers stop
    telling the settings apart.

    ``partial_r2`` is t²/(t²+dof) and t is 8e16, so it is 1.0 whatever dof
    says; both robustness values are at their limits for the same reason.
    Refusing a different ``dof`` there would mean refusing a number that
    makes every recomputation come out right, which is not a lie about
    anything. The settings of a fit with no residual variance are held by
    nothing here, and that is a fact about that fit rather than a gap in
    this rule.
    """
    degenerate = [s for s in CARRYING
                  if SHAPES[s]["result"]["numeric_estimate"]
                  ["ovb_sensitivity"]["se"] < 1e-12]
    assert len(degenerate) == 1, degenerate
    b = SHAPES[degenerate[0]]["result"]["numeric_estimate"]["ovb_sensitivity"]
    assert STILL_OPEN <= set(b)
    t, dof = b["t_statistic"], b["dof"]
    assert math.isclose(t * t / (t * t + dof), 1.0)
    assert math.isclose(t * t / (t * t + dof + 39), 1.0)


# --------------------------------------------------------- nothing else moved


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_no_stored_answer_is_refused(shape):
    themis.verify_answer_claims(
        SHAPES[shape]["program"], SHAPES[shape]["result"])
