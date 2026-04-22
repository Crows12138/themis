# A1 prompt v2.1 — amendment covering 5 gaps from N=20 eval run

Date: 2026-04-22

## Context

The N=20 eval run (see `eval_set_v2_increment_20_cases.md`) surfaced
5 distinct gaps in the A1 v2 prompt. v2.1 is a single-edit batch
that addresses all 5. No kernel changes.

## Changes

### §2b — Categorical domains (F12a, highest-priority gap)

New section after §2a. Rule: if user names ≥3 discrete levels
(低/中/高, 少/中/多, …), retain the categorical domain verbatim.
Encode named level-pair contrasts on the query (intervention.value
/ target.value carry the levels, not just booleans). If compression
to bool is forced, declare it in
`extensions.ambiguities[kind=categorical_compression]`.

### §5 named-kind list — 4 new entries

Added to the structural-ambiguity list after `alias`:

- `selection_bias` — for collider-conditioning patterns
  (住院病人中 / 入学学生里 / 只看幸存). Distinct from
  `confounder_refusal` — the refused structure is a collider, not
  an unobserved common cause. Both may apply together.
- `counterfactual_query` — for Pearl Layer-3 phrasing ("如果当初",
  "要是当时没", "假如我当时"). Emit the Layer-2 interventional
  proxy and declare the estimand gap.
- `mechanism_vs_existence` — for "为什么 X 会 Y", "X 怎么导致 Y",
  "通过什么机制". Emit a cause-query for existence-of-path and
  declare the mechanism gap.
- `individual_vs_population` — for narrative-population + question-
  individual mismatch ("临床试验平均…" → "对我有效吗"). Emit
  population ATE as proxy and declare the ATE-vs-ITE gap.

### §5 signal-word table — 2 new rows

Added cues for counterfactual ("如果当初" / "要是没") and mechanism
("为什么" / "怎么导致" / "通过什么机制").

## Verification

Re-ran case 15 (F12 categorical) through sonnet sub-agent with
v2.1:

| Dimension | v2 run | v2.1 run |
|---|---|---|
| Predicates | `exercises_regularly` (bool), `blood_pressure_controlled` (bool) — renamed + collapsed | `exercise_amount` (少/中/多), `blood_pressure_level` (低/中/高) — preserved |
| Level-pair intervention | lost | `intervention.value="多"` |
| Level-pair target | lost | `target.value="中"` + alternative "低" declared |
| Missing-param request | `P(blood_pressure_controlled=True\|exercises_regularly=True)` — anonymous | `P(blood_pressure_level=中\|exercise_amount=多)` — meaningful |
| themis.run | structurally_solved (vacuous) | needs_investigation (on the level-pair contrast) |

**Kernel finding**: string-valued categorical domains are accepted
end-to-end (variable, query, framing_check, missing_information).
No kernel change needed to support F12a — the gap was entirely in
the A1 prompt.

Output at `docs/eval_set/real_llm_run_v2_1/15_bp_exercise_categorical.json`.

## Gaps NOT re-run

Cases 16, 17, 18, 19 were already handled correctly by v2 through
improvised kind names — the v2.1 change only stabilizes the names
so downstream response rendering can match them deterministically.
Re-running to verify they still pass is low-priority; deferred
unless a failure appears.

## Follow-ups

- Response rendering (`response_rendering.md`) may need parallel
  updates to recognize the 4 new named kinds. Check next time the
  rendering layer is exercised.
- Case 15's themis.run output is `needs_investigation` — next-turn
  parameter fill-back on the categorical parameter pair is the
  natural A3 loop continuation; not exercised in this round.
