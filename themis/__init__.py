"""Auditable causal reasoning and estimation system.

See ARCHITECTURE.md for layer definitions and dependency rules.

Public entry points::

    from themis import run, apply_patch_and_run, estimate, audit

    # Pure symbolic kernel:
    out = run(program_json_or_dict)

    # Multi-turn closed loop:
    out2 = apply_patch_and_run(program_json, [filled_bundle, ...])

    # DataFrame-backed estimation path:
    estimated = estimate(program_json_or_dict, dataframe)

    # Independent re-check (pure JSON; no typed objects needed):
    for row in audit(program_json, out["results"][0]):
        print(row["audit"], row["ok"], row["zh"])

Which audits apply to a given artifact is a question about the artifact,
and :mod:`themis.audits` answers it once. Reaching past ``audit`` for the
thirteen ``verify_*`` entry points directly is supported and is what the
MCP tools do, but then the applicability is yours to get right: five of
them audit standalone artifacts rather than a ``query_result`` envelope and
reject a foreign one with the same exception they use for a failed audit,
and ``verify`` refuses a result carrying no derivation rather than pass it
by omission. ``audit`` never hands a caller an audit that was not about
their artifact, which is the only way "did this pass" has an answer.

The kernel is JSON-in / JSON-out. Inputs conform to
``kernel_ast.schema.json``; outputs' ``results`` entries conform to
``query_result.schema.json`` (which $refs ``derivation.schema.json``
for the embedded reasoning chain). No natural language passes through
this boundary. The estimation entry point accepts DataFrame data as an
explicit side channel and does not change the kernel AST contract.

Common exceptions (importable from their sub-modules; not re-exported
on ``themis`` directly to keep the public surface minimal)::

    from themis.input.syntactic_validator import SyntacticError
    from themis.input.semantic_validator import SemanticError
    from themis.estimation.contract import DataContractError
    from themis.refusals import EstimatorFailure
    from themis.estimation.dose_response import EstimatorDependencyMissing
    from themis.runtime.numeric_estimator import InsufficientTheta
    from themis.verifier import VerificationError

``run`` raises ``SyntacticError`` / ``SemanticError`` for malformed
input. ``estimate`` raises ``DataContractError`` (DataFrame fails
column / dtype check) or ``EstimatorFailure`` (estimator hits an
overlap / convergence / sample-size limit). ``verify`` /
``verify_data_gap_report`` / ``verify_bounds_results`` raise
``VerificationError``.
``AdmgVerificationPending`` (re-exported below) is preserved for
backward-compat from the v0.1 era; current ADMG verification is
covered by the V0-V5 verifier and this exception is no longer raised
by the runtime path.
"""

from . import audits as _audits
from .audits import audit
from .kernel import (
    AdmgVerificationPending,
    apply_patch_and_run,
    estimate,
    run,
    verify,
    verify_assumption_ledger,
    verify_bounds_results,
    verify_cluster_inference,
    verify_data_gap_report,
    verify_markov_blanket,
    verify_missing_data_numeric,
    verify_orientation_ledger_export,
    verify_orientation_propagation,
    verify_orientation_questions,
    verify_orientation_session,
    verify_outcome_error,
    verify_selection_recovery_numeric,
)
from .output.analysis_report import build_analysis_report

__version__ = "0.15.0-dev"
__all__ = [
    "AdmgVerificationPending",
    "apply_patch_and_run",
    "audit",
    "build_analysis_report",
    "estimate",
    "run",
    "verify",
    "verify_assumption_ledger",
    "verify_bounds_results",
    "verify_cluster_inference",
    "verify_data_gap_report",
    "verify_markov_blanket",
    "verify_missing_data_numeric",
    "verify_orientation_ledger_export",
    "verify_orientation_propagation",
    "verify_orientation_questions",
    "verify_orientation_session",
    "verify_outcome_error",
    "verify_selection_recovery_numeric",
]

# Every public verifier declares what it is an audit of, or this raises.
_audits.bind(__all__)
