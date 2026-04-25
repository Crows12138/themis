"""Phase 7 (M2) — numerical estimation layer.

Public contract: pandas DataFrame in, point estimate + CI out. The
kernel's existing JSON-in / JSON-out identification layer is not
disturbed — data flows through a separate Python API
(``themis.estimate``) so JSON callers that only need identification
keep the v1.0 kernel surface verbatim.

Phase 7.1 scope: data contract + backdoor ATE estimator. Front-door /
IV / mediation estimators follow in 7.2 / 7.3 / 7.4.
"""
from .backdoor import BackdoorEstimate, estimate_backdoor_ate
from .contract import DataContract, DataContractError
from .frontdoor import FrontdoorEstimate, estimate_frontdoor_ate
from .iv import IVEstimate, estimate_iv_ate
from .mediation import MediationEstimate, estimate_mediation
from .sensitivity import (
    EValueResult,
    e_value_for_risk_ratio,
    e_value_from_ate_binary,
)

__all__ = [
    "BackdoorEstimate",
    "DataContract",
    "DataContractError",
    "EValueResult",
    "FrontdoorEstimate",
    "IVEstimate",
    "MediationEstimate",
    "e_value_for_risk_ratio",
    "e_value_from_ate_binary",
    "estimate_backdoor_ate",
    "estimate_frontdoor_ate",
    "estimate_iv_ate",
    "estimate_mediation",
]
