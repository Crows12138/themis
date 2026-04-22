# Eval set v1 — A1 prompt v2 uplift report

Date: 2026-04-22

## Setup

Same 10 cases as v1 eval, re-run with the A1 prompt v2 (commit
`6f14414`) that added §2a negation canonicalization, §3a
confounder refusal, §5 ambiguity declaration. Sub-agent pinned to
Sonnet to represent "current average model capability". All 10
cases completed; outputs in `docs/eval_set/real_llm_run_v2/`.

## Headline

A1 prompt v2 closes the three target failure modes. Every metric
moved in the expected direction; two moved to ceiling.

| Metric | v1 (sonnet) | v2 (sonnet) | Delta |
|---|---|---|---|
| **VR** variable recall | 88% | **100%** | +12 pp |
| **ER must** edge recall | 62% | **92%** | +30 pp |
| **CH** critical hallucination cases | 2/10 | **1/10** | −1 (see §5 below) |
| **AQ** abstention quality | 0/6 | **6/6** | +100% |
| **PC** provenance completeness | 100% | 100% | — |

## Per-case delta

| Case | v1 result | v2 result | Mechanism |
|---|---|---|---|
| 01 running_weight_loss | VR ✓, no ambig declared | VR ✓, intent ambiguity (cause vs effect) declared | §5 fired |
| 02 vitamin_d_narrative | VR ✓, no ambig | VR ✓, 2 ambiguities declared (scope + confounder_refusal) | §3a + §5 |
| 03 coffee_insomnia_ambig | silent assoc pick, alt ignored | §5: picked assoc, declared cause as alternative | §5 fired exactly as designed |
| 04 stress_chain | 3-edge chain ✓, no ambig | 3-edge chain ✓ | unchanged |
| 05 coffee_alertness_admg | **missed alertness + missed bidirected** | **alertness + bidirected both emitted** | §3a logic + better A5 merge |
| 06 jogging_running_alias | silent split | alias ambiguity declared as `kind: alias` | §5 covers aliases too |
| 07 skip_breakfast | emitted `skipping_breakfast` (bad) | **emitted `eats_breakfast` + value=false** | §2a fired |
| 08 ice_cream_drowning | **emitted direct cause edge (CH)** | **emitted `temperature_high` confounder + 2 edges, no direct ice_cream → drowning** | §3a fired exactly as designed |
| 09 smoking_lung | clean | clean + confounder_refusal decision documented | §3a exception documented |
| 10 cold_weather | silent commit, double ambiguity missed | both intent + scope ambiguities declared | §5 covers multi-dim |

## The three target fixes — did they work?

### §2a negation canonicalization (F7)

**Target case 07**: "不吃早餐会影响学习效率吗"

- v1: emitted predicate `skipping_breakfast` — matches gold's
  `must_not_infer.predicate=skips_breakfast` → variable-level CH
- v2: emitted predicate `eats_breakfast` with
  `intervention.value: false` — themis.run asks for the right
  CPT `P(study_efficiency=True | eats_breakfast=False)`

**Result**: clean fix. The canonical form survives the verifier
round-trip; no split causal mass.

### §3a confounder refusal (F8)

**Target case 08**: "夏天冰激凌卖得多的月份，溺水事件也多。所以吃冰激凌会导致溺水吗？"

- v1: `eating_ice_cream → drowning` emitted as `llm_proposal` →
  downstream `cause` query returns TRUE → response layer would
  read "yes, ice cream causes drowning" → **critical
  hallucination confirmed**
- v2: emitted `temperature_high → ice_cream_consumption` +
  `temperature_high → drowning_incidents` (both `llm_proposal`),
  no direct ice_cream → drowning edge. themis.run on the cause
  query now returns `structural_result: {value: false}` — the
  correct answer

**Result**: the canonical F8 hallucination is eliminated by the
§3a rule table. The real test is whether the rule generalizes —
see §5 below on case 10.

### §5 ambiguity declaration (F3)

**Target coverage**: 6/10 cases had gold-listed ambiguities;
v1 surfaced 0. v2 surfaces **6/6** via `extensions.ambiguities`,
including:

- case 01: intent (cause vs effect)
- case 02: scope ambiguity (n=1 vs population) + confounder_refusal
- case 03: intent (assoc vs cause) with `disambiguation_ask` field
- case 05: confounder_refusal (from §3a)
- case 06: alias (慢跑 vs 跑步) — new ambiguity kind surfaced
- case 10: intent + scope (office vs general population)

**Result**: the prompt-level commit-with-record rule worked. Every
v1 silent-pick became a v2 recorded-decision. The downstream
response-side prompt now has structured data to surface the
ambiguity; completing that loop is a follow-on task.

## The remaining CH: case 10

v2 still flags CH on case 10's `cold_weather → gets_sick` edge.
This is a **boundary case** in my gold labeling:

- `gold_edges` has the edge at `severity: should`
- `must_not_infer` flags it at *must severity* (warning "naive
  extraction treats it as must")

The kernel_ast schema doesn't carry edge severity — the agent
emits the edge, `themis.run` treats it as a regular directed
edge. Since the agent also declared both ambiguities (intent +
scope), downstream rendering can caveat it. Semantically this is
not a bug in A1 v2; it's a limitation of how gold expresses
"emit at weaker severity". I'm keeping it in the CH count for now
but it represents measurement noise, not a real v2 regression.

## What improved beyond the target fixes

Two cases benefited from second-order effects:

- **Case 05** (ADMG hidden confounder): v1 missed both the
  mediator (alertness) and the bidirected edge. v2's stronger
  engagement with the narrative (via §3a decision-making) led to
  extracting alertness AND proposing a bidirected edge for the
  latent genetic sensitivity. VR went 1/3 → 3/3. This wasn't
  the direct target of the prompt changes but the §3a reasoning
  discipline ("stop and consider the mechanism") transferred.

- **Case 02** (vitamin D narrative): v1 correctly lifted framing
  from narrative but didn't flag the n=1 anecdote vs population
  causal claim. v2 added confounder_refusal + scope ambiguity
  declarations — the single-subject temporal coincidence concern
  that gold flagged is now surfaced.

## What didn't improve

- The kernel still emits 7-field framing asks on pure-structural
  queries (F9 / case 09). A1 v2 didn't touch this — it's a
  kernel-side scope fix in `framing_check` / `investigation_pusher`,
  not an NL-layer change. Still queued.

## Followups surfaced by v2

- **response_rendering.md v2** — now has structured
  `extensions.ambiguities` to read. Update the output-side prompt
  to list ambiguities and produce the `disambiguation_ask` as
  part of the Chinese reply.
- **schema check** — confirm `extensions.ambiguities` round-trips
  through `apply_patch_and_run` / `verify` unchanged (should be
  automatic since extensions is free-form, but worth a test).
- **eval set expansion to 20+** — with A1 v2 hitting near-ceiling
  on 10 cases, the signal-to-noise is running out. Need more
  diverse cases to drive the next round of prompt work.
- **eval-time name drift** — still present (the reason for
  semantic matching in scoring). Addressed by user's Phase 3
  alias_candidate IR; not prompt-layer work.

## Recommendation

- **Accept A1 v2 as released**. Data shows clear uplift on all
  three target failure modes; no regressions.
- **Next slice**: either (a) **response_rendering v2** to close
  the ambiguity loop (so users actually *see* the disambiguation
  asks), or (b) **F9 kernel scope fix**. Both are small. Both
  compound the v2 benefits.
- **Grow eval set to 20+ before another round of NL prompt work.**
  At 10 cases with near-ceiling metrics, additional prompt
  tweaking optimizes noise.
