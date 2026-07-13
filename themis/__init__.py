"""Auditable causal reasoning and estimation system.

See ARCHITECTURE.md for layer definitions and dependency rules.

Public entry points::

    from themis import (
        run,
        apply_patch_and_run,
        estimate,
        verify,
        verify_data_gap_report,
        verify_bounds_result,
    )

    # Pure symbolic kernel:
    out = run(program_json_or_dict)

    # Multi-turn closed loop:
    out2 = apply_patch_and_run(program_json, [filled_bundle, ...])

    # DataFrame-backed estimation path:
    estimated = estimate(program_json_or_dict, dataframe)

    # Independent re-check (pure JSON; no typed objects needed). The three
    # audit surfaces partition by what the result carries — pick by result
    # content, do not reach for verify() unconditionally:
    #
    #   verify                 — audits the reasoning chain; applies ONLY to
    #                            results that carry a "derivation" (structurally
    #                            / numerically solved answers). It deliberately
    #                            rejects derivation-less results (no audit-by-
    #                            omission), raising ValueError — so guard the call.
    #   verify_data_gap_report — audits the T10 gap report; always applicable,
    #                            including diagnostic / derivation-less results.
    #   verify_bounds_result   — audits a bounds answer; applies when the result
    #                            carries a "bounds_result" (Phase 12 Manski
    #                            natural / Balke-Pearl IV / iter 119 Manski-Tamer).
    #
    # The two most common statuses — needs_investigation (identifiable but
    # missing theta) and needs_assumption (counterfactual) — carry NO
    # derivation, so verify() alone is the wrong surface for them; use the
    # gap / bounds audits. The copy-paste-safe pattern:
    result = out["results"][0]
    if "derivation" in result:
        verify(program_json, result)            # reasoning-chain audit
    verify_data_gap_report(result)              # gap-report audit (always ok)
    if "bounds_result" in result:
        verify_bounds_result(program_json, result)

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
    from themis.estimation.dose_response import EstimatorFailure
    from themis.estimation.dose_response import EstimatorDependencyMissing
    from themis.runtime.numeric_estimator import InsufficientTheta
    from themis.verifier import VerificationError

``run`` raises ``SyntacticError`` / ``SemanticError`` for malformed
input. ``estimate`` raises ``DataContractError`` (DataFrame fails
column / dtype check) or ``EstimatorFailure`` (estimator hits an
overlap / convergence / sample-size limit). ``verify`` /
``verify_data_gap_report`` / ``verify_bounds_result`` raise
``VerificationError``.
``AdmgVerificationPending`` (re-exported below) is preserved for
backward-compat from the v0.1 era; current ADMG verification is
covered by the V0-V5 verifier and this exception is no longer raised
by the runtime path.
"""

from .kernel import (
    AdmgVerificationPending,
    apply_patch_and_run,
    estimate,
    run,
    verify,
    verify_bounds_result,
    verify_data_gap_report,
    verify_markov_blanket,
    verify_selection_recovery_numeric,
)
from .output.analysis_report import build_analysis_report

__version__ = "0.15.0-dev"
__all__ = [
    "AdmgVerificationPending",
    "apply_patch_and_run",
    "build_analysis_report",
    "estimate",
    "run",
    "verify",
    "verify_bounds_result",
    "verify_data_gap_report",
    "verify_markov_blanket",
    "verify_selection_recovery_numeric",
]
