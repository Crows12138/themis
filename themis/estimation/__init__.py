"""Numerical estimation layer (Phase 7 / 8.1 / 8.2 / 14).

Public contract: pandas DataFrame in, point estimate / CI / sensitivity
/ DAG-skeleton out. The kernel's existing JSON-in / JSON-out
identification layer is not disturbed — data flows through a separate
Python API (``themis.estimate``) so JSON callers that only need
identification keep the v1.0 kernel surface verbatim.

Landed scope:

- Phase 7.1-7.4 — ATE estimators: ``estimate_backdoor_ate`` /
  ``estimate_frontdoor_ate`` / ``estimate_iv_ate`` /
  ``estimate_mediation`` returning ``BackdoorEstimate`` /
  ``FrontdoorEstimate`` / ``IVEstimate`` / ``MediationEstimate``
- Phase 7.5 (iter 125) — Controlled Direct Effect at fixed M=m*:
  ``estimate_cde`` returning ``CDEEstimate``. Plug-in g-formula
  on a sklearn outcome model; complements the Imai NDE/NIE path
  with the policy-relevant "what if we forced M to this level?"
  contrast (VanderWeele 2015 ch.2.3.3).
- Phase 7.5+ (iter 134) — Multi-mediator chain CDE:
  ``estimate_cde_chain`` returning ``CDEChainEstimate``. Extends the
  iter 125 single-M CDE to N mediators X→M_1→...→M_n→Y, fixing
  each M_i at a chosen reference (VanderWeele 2015 ch.5).
- Phase 9 §T9.2 (iter 128) — transport-numeric ATE via post-
  stratification (Cole & Stuart 2010 §3): ``estimate_transport``
  returning ``TransportEstimate``. Source data + target marginal
  P(Z) → reweighted ATE in target population. Single-Z scope; multi-
  Z and IPSW (Westreich 2017) follow in §T9.3+.
- Phase 8.1 — discovery: ``discover_graph`` (PC / FCI / LiNGAM via
  causal-learn) returning ``DiscoveryResult`` +
  ``discovery_to_kernel_ast`` adapter
- Phase 8.2 — sensitivity: ``e_value_for_risk_ratio`` /
  ``e_value_from_ate_binary`` / ``e_value_from_ate_continuous``
  (iter 124, Chinn 2000 SMD→RR) returning ``EValueResult``
  (VanderWeele 2017); auto-attached to ATE estimates (binary OR
  continuous outcome) by the dispatcher
- Phase 14 — dose-response curves via ``themis.estimate(...)`` with
  ``dose_response_*`` method options (LinearDML / CausalForestDML /
  DRLearner, opt-in)

The data contract (``DataContract`` / ``DataContractError``) is shared
by all estimators — same DataFrame validation, same SHA-256 hash
threaded into derivation provenance.
"""
from .backdoor import BackdoorEstimate, estimate_backdoor_ate
from .contract import DataContract, DataContractError
from .frontdoor import FrontdoorEstimate, estimate_frontdoor_ate
from .discovery import (
    DiscoveryResult,
    discover_graph,
    discovery_to_kernel_ast,
)
from .iv import IVEstimate, estimate_iv_ate
from .mediation import (
    CDEChainEstimate,
    CDEEstimate,
    MediationEstimate,
    estimate_cde,
    estimate_cde_chain,
    estimate_mediation,
)
from .sensitivity import (
    EValueResult,
    e_value_for_risk_ratio,
    e_value_from_ate_binary,
    e_value_from_ate_continuous,
)
from .transport import TransportEstimate, estimate_transport

__all__ = [
    "BackdoorEstimate",
    "CDEChainEstimate",
    "CDEEstimate",
    "DataContract",
    "DataContractError",
    "DiscoveryResult",
    "EValueResult",
    "FrontdoorEstimate",
    "IVEstimate",
    "MediationEstimate",
    "TransportEstimate",
    "discover_graph",
    "discovery_to_kernel_ast",
    "e_value_for_risk_ratio",
    "e_value_from_ate_binary",
    "e_value_from_ate_continuous",
    "estimate_backdoor_ate",
    "estimate_cde",
    "estimate_cde_chain",
    "estimate_frontdoor_ate",
    "estimate_iv_ate",
    "estimate_mediation",
    "estimate_transport",
]
