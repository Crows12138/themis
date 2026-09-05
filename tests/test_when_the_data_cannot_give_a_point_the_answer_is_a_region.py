"""A confidence REGION over a coefficient vector, and what it is allowed to say.

Every estimator here answered with a number. When two treatments are
intervened on together and both are endogenous, there may be no number to
answer with: with fewer instruments than treatments the vector is not
point-identified at all, and even with enough of them a weak first stage
makes a point estimate and its Wald interval a fiction — the interval is
built on an asymptotic approximation that fails exactly there.

Anderson-Rubin inverts a test instead. Its size is correct whatever the
first stage does, so what comes back is a region: bounded when the data pin
the vector down, unbounded in precisely the directions they do not, empty
when the premise itself is refuted. "Unbounded" is the answer, not a
failure — and the tests below are mostly about that sentence being kept.

Four things are held here and each is the counterexample to a different way
of getting this wrong:

- the algebra is the scalar one, one dimension up (parity at k=1, and
  coverage measured rather than argued);
- the graphical condition is read on the treatment SET and is genuinely not
  the conjunction of the scalar ones (a witness graph where the scalar test
  refuses the instrument the vector test accepts);
- the two vocabularies — the region's shape and each coordinate's — are tied
  by a theorem, and the verifier holds both ends of it;
- a tampered region is refused, one field at a time.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation import ar_region
from themis.estimation.iv import (
    _overid_moments,
    _vector_moments,
    anderson_rubin_overid_set,
    estimate_iv_vector,
)
from themis.output.analysis_report import build_analysis_report
from themis.runtime.structural_solver import iv_sets, vector_iv_sets
from themis.types import Atom, ConstTerm
from themis.verifier.errors import VerificationError
from themis.verifier.verify import verify_vector_iv_region


# --- the data ----------------------------------------------------------------

def _two_endogenous(n: int = 4000, seed: int = 0, *, pi: float = 0.9,
                    q: int = 2) -> pd.DataFrame:
    """Two endogenous treatments confounded by one unmeasured U, and ``q``
    instruments — z1 moves `a`, z2 (when present) moves `b`."""
    rng = np.random.default_rng(seed)
    z1 = rng.standard_normal(n)
    z2 = rng.standard_normal(n)
    u = rng.standard_normal(n)
    a = pi * z1 + u + 0.5 * rng.standard_normal(n)
    b = pi * z2 + u + 0.5 * rng.standard_normal(n)
    y = 1.0 * a - 0.5 * b + u + 0.3 * rng.standard_normal(n)
    frame = {"a": a, "b": b, "y": y, "z1": z1}
    if q >= 2:
        frame["z2"] = z2
    return pd.DataFrame(frame)


TRUE_BETA = (1.0, -0.5)


def _region(df: pd.DataFrame, instruments: tuple[str, ...]):
    return estimate_iv_vector(
        df, treatments=("a", "b"), outcome="y", instruments=instruments,
    ).region


# --- the algebra is the scalar one, one dimension up -------------------------

def _one_endogenous(n: int = 4000, seed: int = 1) -> pd.DataFrame:
    """One endogenous treatment and two instruments that are both valid for
    it — the design the scalar solver was written for."""
    rng = np.random.default_rng(seed)
    z1, z2 = rng.standard_normal(n), rng.standard_normal(n)
    u = rng.standard_normal(n)
    x = 0.8 * z1 + 0.6 * z2 + u + 0.5 * rng.standard_normal(n)
    y = 1.0 * x + u + 0.3 * rng.standard_normal(n)
    return pd.DataFrame({"x": x, "y": y, "z1": z1, "z2": z2})


def test_at_one_treatment_the_region_is_the_interval_the_scalar_solver_gives():
    """The scalar Anderson-Rubin set is the k=1 instance of this quadric, so
    it must come back the same to the last digit — not merely close.

    Two transcriptions of one inversion is exactly the arrangement that goes
    quietly wrong: the vector form is written in matrices and the scalar one
    in three floats, and every place they could disagree is a place where a
    reader gets two different intervals for one question.
    """
    df = _one_endogenous()
    scalar = anderson_rubin_overid_set(
        _overid_moments(df, "x", "y", ("z1", "z2"), ()))
    assert scalar is not None and scalar.kind == "bounded"

    moments = _vector_moments(df, ("x",), "y", ("z1", "z2"), ())
    region = ar_region.region_from_moments(moments)
    assert region is not None
    assert region.shape == "bounded"
    (only,) = region.projections
    assert only.kind == scalar.kind
    assert only.lower == scalar.lower
    assert only.upper == scalar.upper


@pytest.mark.parametrize("pi,shape", [(0.9, "bounded"), (0.01, "unbounded")])
def test_the_region_covers_the_truth_at_the_nominal_rate(pi, shape):
    """Coverage, measured. The whole claim of this route is that the rate does
    not depend on the first stage, so it is checked at a strong one and at one
    so weak that every region comes back unbounded — where a point estimate's
    Wald interval would be badly under-covering.

    Membership is asked of the quadratic itself rather than of the reported
    shape: the shape is a claim ABOUT which vectors satisfy the inequality,
    and this is the inequality. Asserting the shape beside it is what says the
    weak arm really is exercising the weak case rather than quietly running a
    second strong one.
    """
    covered = 0
    reps = 200
    for seed in range(reps):
        region = _region(_two_endogenous(n=300, seed=seed, pi=pi),
                         ("z1", "z2"))
        assert region.shape == shape
        covered += ar_region.region_contains(region, TRUE_BETA)
    rate = covered / reps
    assert 0.90 <= rate <= 0.995, f"coverage {rate} at nominal 0.95"


def test_fewer_instruments_than_treatments_is_answered_and_not_refused():
    """One instrument, two treatments: no point estimate of the vector exists.
    The region is the honest answer — unbounded along the direction the data
    cannot constrain, and still containing the truth."""
    region = _region(_two_endogenous(), ("z1",))
    assert region.shape == "unbounded"
    assert region.point is None
    assert ar_region.region_contains(region, TRUE_BETA)
    assert not ar_region.region_contains(region, (5.0, 5.0))


def test_bounded_is_the_same_word_as_every_coordinate_being_bounded():
    """The theorem tying the two vocabularies, on both designs. It is what
    lets a reader read the per-coefficient intervals as the answer when they
    are all finite, and it is what the verifier holds from both ends."""
    for instruments in (("z1", "z2"), ("z1",)):
        region = _region(_two_endogenous(), instruments)
        every = all(p.kind == "bounded" for p in region.projections)
        assert region.bounded == every


# --- the graphical condition is read on the SET ------------------------------

def _atom(name: str) -> Atom:
    return Atom(predicate=name, args=(ConstTerm("me"),))


def _witness_graph():
    """``za`` reaches Y only through the two treatments. Every arrow:
    za→a, za→b, a→b, a→y, b→y.

    ``a→b`` is what makes the case discriminating rather than merely
    illustrative: it puts `b` among a's descendants, so the scalar criterion
    for (a, Y) may not condition on it and has no way to close the
    za→b→Y path at all.
    """
    import networkx as nx

    g = nx.DiGraph()
    a, b, y, za = (_atom(n) for n in ("a", "b", "y", "za"))
    g.add_nodes_from([a, b, y, za])
    g.add_edges_from([(za, a), (za, b), (a, b), (a, y), (b, y)])
    return g, (a, b), y, za


def test_an_instrument_the_scalar_test_refuses_is_valid_for_the_vector():
    """The discriminating case, and the reason this is a separate condition
    rather than a loop over the scalar one.

    ``za`` reaches Y through `b` as well as through `a`. For the query "what
    does `a` do to Y" that is a path the instrument opens and no admissible
    conditioning set closes, so the scalar criterion refuses it — correctly.
    For "what do `a` and `b` do together" the same path is INSIDE the
    intervention: cutting the outgoing edges of BOTH treatments cuts it. A
    condition built as a conjunction of scalar checks would have refused this
    design and left the query unanswerable.
    """
    graph, treatments, y, za = _witness_graph()

    assert iv_sets(graph, treatments[0], y) == ()

    found = vector_iv_sets(graph, treatments, y)
    assert [c.instrument for c in found] == [za]
    assert found[0].conditioning == frozenset()
    # And it moves both, which is reported and is not what made it valid.
    assert set(found[0].relevant_to) == set(treatments)


# --- what a reader is told ---------------------------------------------------

def _program(instruments: tuple[str, ...]) -> dict:
    def atom(p):
        return {"predicate": p, "args": [{"type": "const", "name": "me"}]}

    statements: list[dict] = [
        {"kind": "variable", "predicate": v, "domain": [True, False]}
        for v in ("a", "b", "y", *instruments)
    ]
    edges = [("a", "y"), ("b", "y")]
    if "z1" in instruments:
        edges.append(("z1", "a"))
    if "z2" in instruments:
        edges.append(("z2", "b"))
    statements += [
        {"kind": "cause", "from": atom(u), "to": atom(w)} for u, w in edges
    ]
    statements += [
        {"kind": "bidirected", "left": atom(u), "right": atom(w)}
        for u, w in (("a", "y"), ("b", "y"), ("a", "b"))
    ]
    statements.append({"kind": "query", "id": "qj", "query": {
        "kind": "effect",
        "intervention": {"atom": atom("a"), "value": True},
        "extra_interventions": [{"atom": atom("b"), "value": True}],
        "target": {"atom": atom("y"), "value": True},
        "given": [],
    }})
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": statements}


def _answered(instruments: tuple[str, ...] = ("z1", "z2")) -> dict:
    program = _program(instruments)
    result = themis.estimate(program, _two_endogenous())["results"][0]
    return result


def test_the_report_says_the_shape_before_it_says_any_number():
    """A projected interval printed without the region's shape reads as an
    ordinary confidence interval, and for an unbounded region that reading is
    wrong in the direction that matters."""
    report = build_analysis_report(_answered())
    assert "Anderson-Rubin 置信域" in report
    assert "数据把整组系数都框住了" in report
    for name in ("`a`", "`b`"):
        assert name in report
    assert "保守" in report


def test_the_route_states_an_instrument_that_moves_nothing():
    """Relevance is reported and not required, so an instrument that moves no
    treatment is a row rather than an omission: it is still valid, and it
    still costs the test a degree of freedom."""
    block = dict(_answered()["extensions"]["vector_iv_identification"])
    block["relevance"] = [{"instrument": "z1", "moves": []}]
    from themis.output.analysis_report import _route_vector_iv_identification

    said = _route_vector_iv_identification(block, {}, lang="zh")
    assert "都不移动" in said


def test_an_unbounded_region_is_attached_beside_the_refusal_and_owns_nothing():
    """The annotating path. The row learned something about the answer and did
    not produce one, so the structural refusal stands and no derivation is
    written — a derivation is the chain THIS result stands on, and a chain
    ending in True on a result that says False is an envelope disagreeing with
    itself."""
    result = themis.estimate(_program(("z1",)),
                             _two_endogenous(q=1))["results"][0]
    assert result["status"] == "needs_investigation"
    assert result["structural_result"] == {"value": False}
    assert "derivation" not in result
    block = result["extensions"]["anderson_rubin_region"]
    assert block["region"]["shape"] == "unbounded"
    # Still auditable, through the verifier the kernel would have called.
    verify_vector_iv_region(block)


def test_the_ledger_carries_what_the_region_rests_on():
    """The estimator's flat declaration reaches the ledger from the region's
    own block. It used to be read at one address — ``numeric_estimate`` — and
    an answer that is not a number does not go there, so a region rested on
    exclusion, linearity and homoskedastic errors under an empty ledger."""
    ledger = _answered()["extensions"]["assumption_ledger"]
    ids = {row.get("id") for row in ledger["assumptions"]}
    assert "iv2_exclusion_instruments_affect_outcome_only_via_treatment_vector" in ids
    assert "linearity_of_the_outcome_equation_in_the_treatment_vector" in ids
    assert (
        "homoskedastic_errors_for_the_anderson_rubin_f_critical_value" in ids
    )


def test_the_kernel_verifies_the_whole_answer():
    program = _program(("z1", "z2"))
    themis.verify(program, _answered())


# --- and what the verifier refuses -------------------------------------------

def _tampered(**changes) -> dict:
    """The answered block with one field of the region replaced."""
    import copy

    block = copy.deepcopy(_ANSWERED_BLOCK)
    block["region"].update(changes)
    return block


_ANSWERED_BLOCK = _answered()["extensions"]["anderson_rubin_region"]


def test_the_verifier_accepts_the_region_it_was_given():
    """The other half of every rejection below: a check that says no to
    everything says nothing."""
    verify_vector_iv_region(_ANSWERED_BLOCK)


def test_a_shape_that_does_not_follow_from_the_moments_is_refused():
    with pytest.raises(VerificationError, match="shape mismatch"):
        verify_vector_iv_region(_tampered(shape="unbounded", bounded=False))


def test_bounded_and_the_shape_must_agree():
    with pytest.raises(VerificationError, match="contradicts shape"):
        verify_vector_iv_region(_tampered(bounded=False))


def test_a_narrowed_projection_is_refused():
    """The one that matters most to a reader: an endpoint moved inward makes
    the answer look sharper than the data support. It fails twice over — the
    re-projection disagrees, and the moved endpoint no longer touches the
    region."""
    import copy

    projections = copy.deepcopy(_ANSWERED_BLOCK["region"]["projections"])
    lower, upper = projections[0]["lower"], projections[0]["upper"]
    projections[0]["lower"] = lower + 0.25 * (upper - lower)
    with pytest.raises(VerificationError, match="lower mismatch"):
        verify_vector_iv_region(_tampered(projections=projections))


def test_a_critical_value_from_the_wrong_distribution_is_refused():
    with pytest.raises(VerificationError, match="kappa mismatch"):
        verify_vector_iv_region(
            _tampered(kappa=_ANSWERED_BLOCK["region"]["kappa"] * 1.5))


def test_reordering_the_coefficients_is_refused():
    """Every projection is labelled, and the labels are the order the moment
    matrices are in. Swapping them silently relabels each coefficient's
    interval as the other coefficient's."""
    region = dict(_ANSWERED_BLOCK["region"])
    with pytest.raises(VerificationError, match="not the order the moments"):
        verify_vector_iv_region(
            {**_ANSWERED_BLOCK,
             "region": {**region, "treatments": list(reversed(
                 region["treatments"]))}})


def test_a_region_with_no_moments_behind_it_is_refused():
    """A shape with nothing to re-derive it from is a claim no reader can
    check, which is the state this whole block exists to avoid."""
    block = {k: v for k, v in _ANSWERED_BLOCK.items()
             if k != "sufficient_statistics"}
    with pytest.raises(VerificationError, match="sufficient_statistics"):
        verify_vector_iv_region(block)


def test_a_centre_is_reported_exactly_where_one_exists():
    with pytest.raises(VerificationError, match="centre presence mismatch"):
        verify_vector_iv_region(_tampered(center=None))


def test_the_terminal_needs_a_witness_for_every_instrument():
    """The structural licence. Without it the region would rest on whatever
    columns the estimator was handed, and "these are instruments" would be the
    caller's word rather than the graph's."""
    from themis.verifier.rules import RuleCheckFailed, dispatch_rule
    from themis.types import StructuralResult

    import networkx as _nx

    from themis.verifier.context import VerificationContext as _Ctx

    a, b, y, za = _atom("a"), _atom("b"), _atom("y"), _atom("za")
    # A real context, because dispatch_rule now asks of every rule that the
    # atoms a step names are variables the graph has. Passing None said
    # "this rule does not read the context", which was true of the rule and
    # is no longer true of the door in front of it.
    _g = _nx.DiGraph()
    _g.add_edges_from([(a, y), (b, y), (za, a)])
    with pytest.raises(RuleCheckFailed, match="vector_iv_criterion_check"):
        dispatch_rule(
            "numeric_anderson_rubin_region",
            _Ctx(graph=_g, query=None),
            {
                "treatments": frozenset({a, b}), "outcome": y,
                "instruments": frozenset({za}), "conditioning": frozenset(),
                "method": "iv_anderson_rubin_region",
                "data_hash": "0" * 64, "sample_size": 4000,
                "shape": "bounded", "ci_level": 0.95,
            },
            StructuralResult(value=True),
            0, {}, {},
        )
