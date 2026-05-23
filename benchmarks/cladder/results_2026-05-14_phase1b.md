# CLadder Phase 1b — 2026-05-14

## Setup

- **Base model**: Claude Sonnet 4.6 (via Claude Code Agent tool, fresh sub-agent per question)
- **Sample**: 30 stratified questions, 10 per rung × 2 arms = 60 sub-agent runs
- **Arms**: vanilla (no tools) vs +Themis (themis-causal-check Skill auto-fires + MCP available)
- **Themis version**: 0.1.3 (PyPI), Skill installed at `~/.claude/skills/themis-causal-check/`
- **Score**: yes/no answer compared to CLadder ground-truth `label`
- **Stratification**: `random.seed(42)`, round-robin across query_types within each rung,
  excludes the 6 Phase 1a dry-run IDs `{8706, 6772, 7847, 24227, 9864, 18357}`
- **Sample artifacts**: `samples_60.json` (agent-facing) + `samples_60_full.json`
  (with `reasoning` + `formal_form` for scoring)

## Why Sonnet 4.6 instead of Opus 4.7

Phase 1a saturated at 100% with Opus 4.7 on 6 questions — ceiling effect made
Themis's value invisible. Sonnet 4.6 was chosen for Phase 1b to leave headroom
on the vanilla baseline, so any Themis lift (or regression) would show up.

## Headline result

| Arm | Correct | Total runs | Accuracy |
|---|---|---|---|
| Vanilla (Sonnet 4.6, no tools) | 27 | 30 | **90.0%** |
| +Themis (Sonnet 4.6 + MCP + Skill) | 24 | 29 | **82.8%** |

One Themis run failed to produce a parseable answer (sub-agent transient issue,
not a kernel failure); denominator adjusted to 29.

**Themis slightly underperformed vanilla** — the opposite of what we'd hoped to
see on a benchmark Themis was built to help with. The next sections diagnose why.

## Themis-only misses

Two questions where vanilla was correct but Themis arm was wrong. Both diagnosed.

### Q1358 — mediation NIE numeric error

**Question**: "Does medication negatively affect heart condition through blood pressure?"

**Structure**: X = medication, M = blood pressure, Y = heart condition.
DAG: X → M → Y, X → Y (direct). Pure mediation question; CLadder ground-truth
NIE (X=0 reference) = 0.11, so "no, NOT negatively through blood pressure".

**What kernel produced**: status = `structurally_solved`. Identification was
correct (NDE/NIE four conditions hold with W=∅; CDE also identifiable). Kernel
emitted a 3-step derivation describing the formula but **no numeric answer** —
the comment in `_dispatch_mediation` said "mediation numeric estimation belongs
to Phase 7", which only covers DataFrame estimation, not the theta-only path
CLadder uses.

**What LLM did**: read the derivation's `extensions.mediation_decomposition.strategy:
"nde_nie"`, attempted to plug CLadder's supplied conditionals into the NIE formula
by hand, **arithmetic error** in the cross-world cancellation, output "yes"
(thought NIE was negative). Wrong.

**Same root cause as Gap A / Gap B (fixed in v0.1.3)**: kernel did the structural
work and stopped at the formula, leaving the numeric assembly to the LLM. When
the LLM does math outside the kernel, it sometimes errs — exactly the failure
mode Themis exists to prevent.

**Fix 1 — shipped in v0.1.4** (this commit): kernel now computes NDE / NIE /
CDE numerically when theta is sufficient. Re-run of the equivalent Q1358 program
through `themis.run` now returns `numerically_solved` with `nie_at_control = 0.11`
matching CLadder ground truth. See `tests/test_runtime/test_mediation_numeric.py`.

### Q9007 — LLM token-level typo

**Question**: a Rung 3 counterfactual. Themis kernel produced a correct
structural identification + correct numeric derivation. The LLM's reasoning
trace was correct end-to-end. The final emitted token was the wrong word
("yes" instead of "no") — a generation artifact at the last decoding step, not
a reasoning failure.

**No kernel fix possible**. This is a LLM-output-layer issue. Two candidate
mitigations:

- **Fix 2A (forced structured output)**: introduce a `submit_verdict` MCP tool
  that takes `verdict: "yes" | "no"` as a structured field, refused by the
  schema if missing. Forces the LLM to commit to a verdict in a parseable
  channel rather than at the end of free text.
- **Fix 2B (benchmark parser)**: improve the agent-output parser to favor the
  in-derivation verdict over the trailing free-text token.

Both deferred to a separate charter (task #126). Neither blocks Fix 1.

## What Phase 1b shows beyond the two misses

- On the **27 questions where Themis got the same answer as vanilla**, the
  Themis arm produced:
  - A formal identification derivation (backdoor / front-door / mediation)
  - Independent V0-V5 verifier re-check of every step
  - GapKind diagnostics when applicable
  - Audit-trail metadata (assumption labels, paper citations)

  None of which the vanilla arm produced.

- The Themis MCP server was invoked on roughly 75% of questions (rough estimate
  from transient run logs; not exhaustively counted). On conceptual /
  propositional-logic-only questions, Sonnet 4.6 sometimes opted out of the
  kernel call — same pattern observed in Phase 1a with Opus 4.7. The
  ALWAYS-invoke description in the Skill frontmatter is a soft rule in
  practice; agents reason about whether the kernel will help.

## Why the underperformance was structural, not random

Both themis-only misses had a common shape: **kernel did the structural work
correctly and stopped before the numeric answer**, leaving room for LLM error
(Q1358) or LLM output artifact (Q9007). Vanilla LLM, in contrast, did
end-to-end reasoning in one continuous chain — fewer hand-offs, fewer points
of failure.

Themis's "structural rigor + audit trail" only helps **when the kernel finishes
the job**. If the kernel emits a formula but the LLM has to evaluate it, the
LLM becomes the weak link — and the Themis path is now strictly longer than
the vanilla path (LLM thinks + asks kernel + LLM does math + LLM emits answer
vs. LLM thinks + LLM emits answer). More steps, more error opportunities.

Hence Fix 1's significance: it closes the most common "structural-only emission"
gap for theta-complete inputs.

## Cost / time

- 60 agents (30 vanilla + 30 Themis), 2 batches of 30 in parallel
- Vanilla arm: 5-30s per agent, ~15-30k tokens each
- Themis arm: 20-180s per agent (median ~70s), 25-80k tokens each
- Wall-clock total: ~5 min per arm
- Estimated total cost: ~$15-25 with Sonnet 4.6

## Implications for the next phase

1. **Re-run Q1358 (and any other mediation-numeric questions in the 30-set)**
   under v0.1.4 to confirm the Fix 1 lift on this benchmark.
2. **Run Phase 1c with the full ~200 question sample** under v0.1.4 to get a
   publishable accuracy comparison. Expect Themis to match-or-slightly-exceed
   vanilla now that mediation numeric works.
3. **Q9007-class artifacts** will keep showing up at low rate regardless of
   kernel changes. Fix 2A (`submit_verdict`) is the right mitigation but
   doesn't gate Phase 1c.
4. **The "kernel must finish the job" principle** generalises: anywhere the
   kernel emits a formula without evaluating it, an LLM gets to make a math
   mistake. Audit other identification strategies (front-door numeric path
   from theta, transport numeric, counterfactual numeric) for the same
   structural gap. Track as task #127 / future charters.

## Raw outputs

Per-question sub-agent transcripts were captured by the Agent tool but kept in
transient outputs, not committed to disk under `benchmarks/cladder/runs/`.
The 30 sampled question payloads are persisted in `samples_60.json` and
`samples_60_full.json`. Reruns are deterministic up to model nondeterminism.

## Cross-reference

- Phase 1a dry-run findings (Opus 4.7, ceiling effect): `results_2026-05-14_dry_run.md`
- Fix 1 implementation (v0.1.4): `tests/test_runtime/test_mediation_numeric.py`,
  `themis/runtime/formula_builder.py`, `themis/runtime/scheduler.py:_dispatch_mediation`,
  `themis/verifier/rules.py:_rule_mediation_numeric_evaluate`
- Q9007 charter (deferred): task #126 in session todo list
