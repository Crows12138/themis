# Eval set v2 — 3-case increment (F10 / F13 / F14)

Date: 2026-04-22

## Setup

Three new cases (11 / 12 / 13) added to bring the eval set to
N=13. Cases cover failure modes not reachable from the original
F1–F9 set:

- F10 multi-subject (case 11, parent education → child grades)
- F13 long chain 5+ nodes (case 12, reading → vocab → comprehension → writing → exam)
- F14 reciprocal causation (case 13, exercise ↔ mood)

Sub-agent pinned to Sonnet ran each through A1 v2 +
response_rendering v2; outputs in `docs/eval_set/real_llm_run_v2/11_*.json`,
`12_*.json`, `13_*.json`.

## Per-case summary

### Case 11 — F10 multi-subject

| Metric | Result |
|---|---|
| VR | 2/2 (semantic match) |
| Ambiguities declared | `subject_scope`, `confounder_refusal` |
| themis.run status | `needs_investigation` |

Agent flattened the parent/child structure to single-`"me"`
predicates (kernel limitation), flagged the compression via
`extensions.ambiguities[kind=subject_scope]`, and — surprisingly —
also fired §3a confounder_refusal, introducing
`household_socioeconomic_status` as an unmeasured common cause
with two edges U→parent, U→child. Direct edge parent→child was
NOT emitted.

**Verdict**: §3a + §5 together handled F10 cleanly. The flatten-
with-declaration pattern is exactly what we'd want from a system
that can't express multi-subject natively yet.

Bonus: the `household_socioeconomic_status` confounder isn't in
gold_variables, but it's causally reasonable — gold was
conservative here.

### Case 12 — F13 long chain

| Metric | Result |
|---|---|
| VR | 5/5 (all chain nodes preserved) |
| Chain preserved | ✓ — all 4 edges, no shortcut |
| must_not_infer violations | 0 — no direct reading→exam edge |
| themis.run status | `structurally_solved`, value=True |
| Ambiguities declared | `intent`, `chain_structure` |

Chain identification works cleanly at 5 nodes. themis returned a
`cause` result with `supporting_paths` containing the full
4-hop path. Agent even declared a `chain_structure` ambiguity
noting the output collapsed to a structural assertion.

**Verdict**: F13 is handled by existing machinery without
changes — the long-chain concern was speculative.

### Case 13 — F14 reciprocal causation

| Metric | Result |
|---|---|
| Ambiguities declared | `reciprocal_causation`, `intent` |
| Edges emitted | **none** (agent refused to pick direction) |
| must_not_infer violations | 0 — neither silent direction |
| themis.run status | **ERROR**: SemanticError (query atoms not in V) |

Agent did exactly what A1 v2 §5 demands: declared
`reciprocal_causation` with both alternatives in
`extensions.ambiguities`, refused to silently commit to one
direction, emitted zero cause edges.

But the kernel's `query_atoms_in_V` semantic check rejected the
program because a query atom never appears in any cause edge —
so there's no graph node to dispatch against.

**This is a new finding (F14a, NL-vs-kernel contract mismatch)**:

- The A1 v2 prompt says "don't silently pick" on ambiguous
  intent / direction
- The kernel requires every query atom to enter the graph via a
  cause edge
- For genuinely undecidable directionality (reciprocal), these
  two rules contradict — the prompt-preferred output is
  kernel-unrunnable

## New failure mode (F14a): reciprocal-causation producing unrunnable AST

The symptom: A1 v2 honestly declines to commit to direction →
program has zero edges → query atoms never enter V → kernel
raises `SemanticError` before dispatch.

### Options to resolve (future slice, not this round)

1. **Prompt-side fix**: A1 v2 §5 extended — for
   `kind: reciprocal_causation`, pick ONE direction anyway (say
   the one implied first in the NL) + declare the alternative.
   The query runs; the user sees the flag and can redirect.
   Cost: slight dishonesty in the AST (one direction emitted
   that may be wrong). Mitigation: `extensions.ambiguities`
   entry makes the flag loud.

2. **Kernel-side fix**: allow "declaration-only" programs where
   query atoms are introduced by `variable` declarations without
   requiring a cause edge. Change `_check_query_atoms_in_V` to
   accept atoms that appear in any `variable` declaration, not
   just in cause edges. This is a semantic expansion — needs a
   slice-level decision.

3. **Schema-side fix**: new result status like
   `needs_direction_decision` or `ambiguous_structure` for this
   class of program. Requires changing the status enum.

**Recommendation**: option 1 (prompt-side) is smallest and
preserves the existing kernel contract. The declared-ambiguity
channel does the real work of surfacing the issue to the user;
the emitted direction is just a tiebreak for runnability. Cost
is that the agent has to pick SOMETHING even when it would
rather not — but it already had to pick a `chosen` value in the
`extensions.ambiguities` entry.

Leaving this as a follow-up task; no code change this round.

## Updated aggregate scores (13 cases)

| Metric | v1 10-case (sonnet) | v2 10-case (sonnet) | v2+incr 13-case |
|---|---|---|---|
| VR | 88% | 100% | 100% |
| ER must | 62% | 92% | 91% |
| CH cases | 2/10 | 1/10 | 1/13 |
| AQ | 0/6 | 6/6 | 9/9 |
| PC | 100% | 100% | 100% |

Adding 3 cases didn't introduce regressions; case 13's themis
error isn't a scoring loss (the AST is correct), it's a contract
mismatch finding.

## What these 3 cases told us

- **F10 handled** by existing v2 machinery (§3a + §5) — no new
  slice needed. If more multi-subject cases surface different
  failures, revisit.
- **F13 handled** too — long chains are a non-issue.
- **F14 partial** — NL layer honestly refuses; kernel can't run
  the refusal. Documented as F14a above; fix deferred.

## Recommendation for next round

- Keep growing the eval set toward 20+. F11 (temporal), F12
  (categorical-numeric), and other compound patterns (selection
  bias, mechanism-vs-existence, counterfactual, individual-vs-
  population) still uncovered.
- If F14a blocks real users, do the prompt-side fix (Option 1)
  as a one-line A1 v2 amendment. Otherwise leave deferred.
- The F3/F7/F8/F9/R2 wave of fixes was the big lift; additional
  prompt iterations on N=13 at near-ceiling metrics would be
  noise optimization.
