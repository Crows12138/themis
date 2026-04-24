# Phase 6.mediation stress test — cases 23 & 24 via A1 v2.3 §3c

Date: 2026-04-24

## Setup

Two blind sub-agents (isolated conversation, access to A1 v2.3 prompt
but NO access to `docs/eval_set/cases/` gold files or any
`real_llm_run_*/` artifact) were given the case 23 and 24 natural-
language questions and asked to produce a `kernel_ast.json` following
the prompt. Outputs were then fed to `themis.run` and compared to
each case's gold `mediation_decomposition` expectation.

Purpose: validate that A1 v2.3 §3c "Mediation decomposition" guidance
is actually sufficient on its own to produce correct kernel_ast, not
just readable in principle.

## Case 23 — clean NDE/NIE decomposition

NL: 跑步 → 代谢改善 → 减肥 + 跑步直接消耗热量。问各占多少？

Sub-agent output matched gold **variable-for-variable and edge-for-edge**:

| Field | Sub-agent | Gold | Match |
|---|---|---|---|
| Variables | `running` / `metabolism_improved` / `weight_loss` | same | ✓ |
| Edges | 3 directed (parallel + mediated paths) | same | ✓ |
| Mediator | `metabolism_improved` | same | ✓ |
| Ambiguities | none | none | ✓ |

Kernel output: `strategy=nde_nie`, both branches identifiable with
empty adjustment — **exactly** matching gold_extensions.

Agent's own decision log cites §3c canonical example explicitly:
"matches the worked example almost verbatim." This is a **positive
signal** that the prompt's canonical example is load-bearing and the
rules are followable.

## Case 24 — recanting-witness (intermediate confounder)

NL: 药 → 血压 → 心脏病 + 药 → 炎症（既影响血压又影响心脏病）。
直接 vs 间接各占多少？

Sub-agent correctly:

- Identified `inflammation` as an **intermediate confounder** (X-descendant
  affecting both M and Y)
- **Did not silently omit** inflammation (§3c: "emit the structure
  faithfully and flag")
- Declared `mediation_intermediate_confounder` ambiguity with the
  variable name
- Set `mediator = blood_pressure_*` per the NL's explicit framing
  ("不通过血压 = direct")

Kernel output: `strategy=none`, `nde_nie.failed_condition=M3`,
`cde.failed_condition=C1` — within the `{M3, M4}` and `{C1, C2}`
envelopes the gold specifies.

### Observed divergence (not a bug)

The sub-agent chose variable names `blood_pressure_elevated` and
`takes_antihypertensive_drug` where the gold file uses
`blood_pressure_lowered` and `drug`. The direction-of-effect
framing wasn't explicit in the NL, so either choice is defensible
in the absence of a §2 `direction` framing field. Structural content
(graph + edges + mediator role) is identical. If this mattered
downstream, the `direction` field in §2 framing would pin it; since
the kernel's mediation identification is direction-agnostic, it
doesn't matter here.

## Prompt gaps surfaced

None that affect correctness. One minor observation:

- **§3c doesn't mandate a specific direction polarity** for
  medication / treatment framing. The sub-agent picked an intuitive
  name but it diverged cosmetically from the gold. If we want
  v2.3.1 tightening, we could add a note that when direction is
  implicit in the NL ("降压药" implies `bp_lowered`), prefer the
  NL's implicit polarity. Low priority — doesn't break anything.

## Aggregate status (updated)

- A1 v2.3 §3c: **working as intended** on both clean and hazard cases
- No spurious `nde_nie` successes on intermediate-confounder
- Mediation decomposition disclosure (response_rendering side) not
  stress-tested here — would need a separate "response-writer"
  sub-agent pass. Deferred: response-rendering prompts are generally
  easier to validate by inspection since they only consume structured
  JSON.

## Recommendation

- **Accept Phase 6.mediation as production-ready on the NL layer**.
  Sub-agent can drive it end-to-end with no prompt fixes needed.
- Defer v2.3.1 direction-polarity tightening until a real case
  actually breaks on it.
- Proceed to Phase 7 M2 (numerical estimation) with confidence
  that identification-layer NL handling is stable.
