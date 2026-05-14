# CLadder Phase 1a dry run — 2026-05-14

## Setup

- **Base model**: Claude Opus 4.7 (via Claude Code Agent tool, fresh sub-agent per question)
- **Sample**: 6 stratified questions, 2 per rung (Pearl's causal hierarchy)
- **Arms**: vanilla (no tools) vs +Themis (themis-causal-check Skill auto-fires + MCP available)
- **Themis version**: 0.1.2 (PyPI), Skill installed at `~/.claude/skills/themis-causal-check/`
- **Score**: yes/no answer compared to CLadder ground-truth `label`

## Sample

| id | rung | query_type | graph_id | label |
|---|---|---|---|---|
| 8706 | 1 | marginal | confounding | yes |
| 6772 | 1 | exp_away | collision | no |
| 7847 | 2 | ate | mediation | no |
| 24227 | 2 | backadj | diamond | yes |
| 9864 | 3 | det-counterfactual | arrowhead | no |
| 18357 | 3 | ett | arrowhead | no |

## Per-question results

| id | rung | vanilla | themis | t_uses (themis) | wall time (themis) |
|---|---|---|---|---|---|
| 7847 | 2 | ✓ no | ✓ no | 10 | 60s |
| 8706 | 1 | ✓ yes | ✓ yes | 11 | 60s |
| 6772 | 1 | ✓ no | ✓ no | 11 | 91s |
| 24227 | 2 | ✓ yes | ✓ yes | **0** | 7s |
| 9864 | 3 | ✓ no | ✓ no | 2 | 18s |
| 18357 | 3 | ✓ no | ✓ no | 10 | 74s |

**Final accuracy**: vanilla **6/6 (100%)**, themis **6/6 (100%)** — ceiling effect.

## Findings

### 1. Opus 4.7 saturates this sample stratification

Vanilla Opus 4.7 perfectly answers all 6 questions, including Rung 3 counterfactuals. Reasoning traces show solid causal logic: identifying mediators vs confounders correctly, applying d-separation, computing marginal via law of total probability, propositional counterfactual evaluation. The published CLadder GPT-4 baseline (≈62%) is no longer the relevant comparison — modern frontier models have substantially exceeded it.

**Implication**: a Phase 1b run of 200 questions with Opus 4.7 vanilla is likely to land in the 80-95% range. Themis can only improve marginally on already-high accuracy. To show Themis's value clearly on CLadder, the harder-question slice (`question_property = "hard"` or specific query types like `det-counterfactual` / `nde` / `nie`) should be targeted, or a weaker base model used.

### 2. Themis tool usage varies sharply with question type

- **High tool usage (10-11 calls)**: Q7847 (ATE), Q8706 (marginal), Q6772 (exp_away), Q18357 (ETT) — questions where kernel evaluation adds verifiable structure (backdoor identification, counterfactual under no-confounding)
- **Low / zero usage**: Q24227 (Method 1 vs Method 2 — conceptual), Q9864 (deterministic AND/OR mechanism — propositional logic)

Even with the v0.1.2 SKILL.md "ALWAYS invoke" tightening, agents still opt out on questions they assess as "this is conceptual / deterministic, kernel won't help." On the conceptual Method 1/2 question, the agent's reasoning was sound and the opt-out was reasonable.

**Implication**: ALWAYS-invoke is a softer rule in practice than the description suggests. Agents reason about whether kernel will help and skip when they judge it won't. This is not necessarily a bad property — but means Themis's `kernel was invoked` rate ≠ 100%.

### 3. Two real kernel gaps surfaced

**Gap A — Q8706 (marginal)**: Themis kernel's `probabilityQuery` looks up theta directly rather than marginalizing through conditionals. CLadder Rung 1 marginal questions supply `P(V)` + `P(Y|V)` and ask `P(Y)`. The kernel returned `needs_investigation` because no direct `P(Y)` was in theta; the agent fell back to law-of-total-probability arithmetic and computed 0.4792 manually. Kernel should auto-marginalize over fully-conditioned variables when their distribution is available.

**Gap B — Q6772 (exp_away)**: The CLadder prompt provided `P(effort | admission, talent)` — observational conditionals going AGAINST DAG edge direction (`effort` is a root, `admission` is a leaf). Themis kernel only accepts structural CPTs in parent→child order. The agent recognized this as Berkson collider conditioning and answered correctly from direct comparison of the supplied conditionals (0.92 vs 0.94). Kernel could either accept observational conditionals (different field) or auto-invert via Bayes when sufficient info is available.

Both gaps are candidates for v0.1.3 kernel work — they would meaningfully expand the set of CLadder questions where Themis's structural verification fires cleanly.

### 4. Themis's value pattern on this benchmark

When Themis kernel DID engage (4/6 questions), it added:
- Formal backdoor identification with adjustment-set proof (Q7847, Q18357)
- Independent V0-V5 re-check of the derivation
- Explicit GapKind flagging (e.g., `ill_defined_intervention_versions` on Q7847 obesity-like framing, `ambiguous_variable_definition` on under-framed CLadder variables)
- Citation anchoring (Hernán-Taubman 2008, etc.)

When the kernel was bypassed (Q24227, Q9864), accuracy was unaffected — the question shape didn't need formal identification.

**Implication**: on CLadder Rung 1 / 2 / 3 with given DAGs, Themis is a structural-verification adjunct, not an accuracy-improver against a frontier base model. Its value-add is **audit trail + verifiable identification**, not **getting more right answers**.

## Cost / time

- 12 agents (6 vanilla + 6 themis), ran in parallel
- Vanilla arm: 5-10s per agent, ~25k tokens each
- Themis arm: 7-91s per agent (median ~60s), 23-60k tokens each
- Estimated total cost: ~$5-8 with Opus 4.7
- Wall-clock total: ~2 min (all in parallel)

## Next-step decision points

1. **Run Phase 1b (~150-200 questions) with Opus 4.7 anyway** to get a publishable score on a known benchmark, even if accuracy is similar across arms. Story: "Opus 4.7 + Themis matches Opus 4.7 alone on CLadder accuracy, but produces a fully audited derivation chain on 67% of questions where kernel engaged." Cost: ~$30-60.
2. **Pivot to harder slice**: filter CLadder to `question_property = "hard"` or `query_type in {det-counterfactual, nde, nie}`, where vanilla Opus 4.7 may show errors and Themis can demonstrably help. Cost: ~$30-60.
3. **Use weaker model (Claude Haiku 4.5 or open-source 70B)** where vanilla baseline is lower (room for Themis to improve). Cost: less; but story is "Themis lifts weaker model" — less impressive headline.
4. **Fix kernel gaps first** (auto-marginalize + accept inverse-direction conditionals) → then re-run. v0.1.3 work. Probably the right long-term move regardless.

## Raw outputs

Each agent's full output (reasoning trace + final answer) was captured by the Agent tool but kept in transient output files. Not yet committed to disk under `benchmarks/cladder/runs/` — would require re-running and explicit save. For reproducibility, the sample is in `samples_full.json` (with `reasoning` + `formal_form` for ground-truth verification); reruns are deterministic except for model nondeterminism.
