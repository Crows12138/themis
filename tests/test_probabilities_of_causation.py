"""PN/PS/PNS — verified against Tian & Pearl (2000) worked numbers (the oracle)."""
from __future__ import annotations

from themis.runtime.probabilities_of_causation import (
    probabilities_of_causation as poc,
)


# Drug-court example, Tian-Pearl 2000 Table 2 + eqs (58)-(63).
# Non-experimental (per 1000 each arm): x → 2 deaths / 998 survive;
# x' → 28 deaths / 972 survive. Experimental risks P(y_x)=0.016, P(y_{x'})=0.014.
_DRUG = dict(
    p_x1_y1=2 / 2000, p_x1_y0=998 / 2000,
    p_x0_y1=28 / 2000, p_x0_y0=972 / 2000,
    p_y_do_x1=0.016, p_y_do_x0=0.014,
)


def test_drug_example_bounds_no_assumptions():
    r = poc(**_DRUG, monotonic=False)
    assert abs(r.pns_lower - 0.002) < 1e-3 and abs(r.pns_upper - 0.016) < 1e-3
    assert abs(r.pn_lower - 1.0) < 1e-6 and abs(r.pn_upper - 1.0) < 1e-6  # eq (59): PN = 1.0
    assert abs(r.ps_lower - 0.002) < 1e-3 and abs(r.ps_upper - 0.031) < 1e-3
    # no point identification without monotonicity
    assert r.pns_point is None and r.pn_point is None and r.ps_point is None


def test_drug_example_point_under_monotonicity():
    r = poc(**_DRUG, monotonic=True)
    assert abs(r.pns_point - 0.002) < 1e-3   # eq (61)
    assert abs(r.pn_point - 1.0) < 1e-3      # eq (62): drug WAS responsible
    assert abs(r.ps_point - 0.002) < 1e-3    # eq (63)


def test_exogeneity_monotonicity_reduces_to_excess_risk_ratio():
    """Tian-Pearl Theorem 4: under exogeneity (P(y|do(x))=P(y|x)) + monotonicity,
    PN = 1 - 1/RR. With P(y|x=1)=0.2, P(y|x=0)=0.1 (RR=2), P(x)=0.5:
    PN=0.5, PNS=0.1, PS=(0.2-0.1)/(1-0.1)=1/9."""
    r = poc(
        p_x1_y1=0.2 * 0.5, p_x1_y0=0.8 * 0.5,
        p_x0_y1=0.1 * 0.5, p_x0_y0=0.9 * 0.5,
        p_y_do_x1=0.2, p_y_do_x0=0.1, monotonic=True,
    )
    assert abs(r.pn_point - 0.5) < 1e-9          # 1 - 1/RR
    assert abs(r.pns_point - 0.1) < 1e-9
    assert abs(r.ps_point - (1.0 / 9.0)) < 1e-9


def test_bounds_collapse_to_point_when_consistent():
    """PNS lower ≤ upper, PN/PS in [0,1], and the monotonicity point lies inside
    the assumption-free bounds (it must, being a tighter identification)."""
    r = poc(**_DRUG, monotonic=True)
    assert r.pns_lower <= r.pns_point <= r.pns_upper
    assert r.pn_lower <= r.pn_point <= r.pn_upper
    assert r.ps_lower <= r.ps_point <= r.ps_upper


def test_zero_conditioning_event_is_not_a_crash():
    """If P(X=1,Y=1)=0 the PN conditioning event is empty — report [0,1], no
    division by zero, no point."""
    r = poc(
        p_x1_y1=0.0, p_x1_y0=0.5, p_x0_y1=0.2, p_x0_y0=0.3,
        p_y_do_x1=0.1, p_y_do_x0=0.2, monotonic=True,
    )
    assert r.pn_lower == 0.0 and r.pn_upper == 1.0
    assert r.pn_point is None
