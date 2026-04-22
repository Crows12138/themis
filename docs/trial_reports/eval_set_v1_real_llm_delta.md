# Eval set v1 — real-LLM run + delta vs simulated baseline

Date: 2026-04-22

## Setup

Real-LLM run: a general-purpose Claude Code sub-agent with blind
access to only `case.narrative` + `case.question` followed the
existing A1 + A5 prompts on 10 cases. 10/10 cases completed;
themis.run accepted every produced kernel_ast.

Artifacts:

- `docs/eval_set/real_llm_run_v1/<case_id>.json` × 10 — each carries
  `produced_kernel_ast` + `themis_run_output` + `agent_observations`
  + `extracted_for_scoring`
- `docs/eval_set/real_llm_run_v1/_process.py` — sub-agent's helper

## Scoring method + a bias we discovered

Initial scoring used exact predicate-name match against gold. That
**systematically under-reported** both recall and hallucination:
the agent produced perfectly reasonable names that differed from
gold's choice (`drinking_coffee` vs `drinks_coffee`,
`eating_ice_cream` vs `ice_cream_consumption`, `insomnia` vs
`has_insomnia`, `drowning` vs `drowning_incidents`,
`skipping_breakfast` vs `skips_breakfast`). All these are
synonymous in the user's mental model.

**New finding not in the simulated baseline**: predicate-naming
drift is a real evaluation concern. Strict exact-match underreports
both VR and CH. Numbers below use a post-hoc semantic match
(clearly synonymous names → counted as match).

The implication: when we later add the candidate IR (user's
"Phase 3: evidence layer") the `alias_candidate` channel is
operationally required — not just for narrative vs question
alias (F6) but also for gold-vs-LLM naming drift during
evaluation.

## Aggregated scores (semantic-matched)

| Metric | Value | Notes |
|---|---|---|
| VR (variable recall) | 88% avg | down from sim 93% once F5 mediator + F8 confounder are counted |
| ER must | 8/13 = 62% | sim was ~85%; real-LLM misses confounder structure (F8) and mediator (F5) more often |
| CH count | **2 / 10 cases** | sim predicted 1; real-LLM added case 07 (skipping_breakfast variable) |
| AQ | 0 / 6 ambiguity cases | real-LLM matches sim at 0% — neither surfaced ambiguity via proposal channel, only via in-reply commentary |
| PC (provenance) | 100% of directed edges tagged `llm_proposal` | clean; A2 tagging well-honored |

## Per-case delta

Format: (case_id) sim prediction → real-LLM finding.

| Case | Sim said | Real-LLM did | Match? |
|---|---|---|---|
| 01 running | correct, 7-field ask | correct, 7-field ask | ✓ |
| 02 vitamin D | A5 fills narrative framing, ambiguity not surfaced | A5 filled time_window/measurement/observability for both preds (✓ narrative framing works end-to-end); ambiguity not surfaced | ✓ |
| 03 coffee-insomnia | silent intent pick (assoc or cause) | picked assoc per A1 table, emitted cause edge as llm_proposal, did not surface dual reading | ✓ |
| 04 stress chain | 4 vars / 3 edges, chain preserved, backdoor collapses | exact match; chain preserved; also deliberately avoided stress→diabetes shortcut | ✓ |
| 05 coffee-alertness ADMG | narrative_to_edges gap; misses bidirected | stronger finding: **A5 extracts narrative variables but they don't flow into A1's causal path**. Agent explicitly stated: "A1 prompt forbids inventing intermediates the user didn't mention, so alertness is excluded". Bidirected also missed. | ⚠ real-LLM found an A5/A1 merge gap |
| 06 jogging-running alias | silent split | confirmed: jogging kept distinct from running, no alias proposal | ✓ |
| 07 skip breakfast | negation goes either way | **emitted `skipping_breakfast`** (not `eats_breakfast` + value=False). This matches gold's `must_not_infer.predicate=skips_breakfast` — a variable-level CH | ⚠ confirms F7 as real CH, not just "depends on LLM" |
| 08 ice cream-drowning | direct cause edge emitted | confirmed: `eating_ice_cream → drowning` emitted as llm_proposal; confounder structure missed | ✓ |
| 09 smoking | clean | clean; 7-field ask over-eager (F9) | ✓ |
| 10 cold weather | compound F1+F3 | **A5 returned empty** on third-person pattern narrative ("办公室里感冒的人变多" is statistical observation, not first-person habit) — new finding | ⚠ real-LLM exposed an A5 input-type gap |

## What the real-LLM run added vs the simulated baseline

Three findings the simulated baseline did not predict:

### (R1) Predicate-naming drift is an evaluation concern

Real LLMs choose reasonable names that diverge from any gold
author's guess. An eval pipeline without semantic matching (or an
explicit alias_candidate IR entry) will mis-measure both recall
and hallucination.

**Actionable**: the user's Phase 3 "candidate IR" with
`alias_candidate` as a first-class entity now has a second
motivation: not only narrative vs question drift but also
gold vs LLM drift at evaluation time.

### (R2) A5 → A1 wiring gap (case 05)

A5 extracts narrative variables; A1 extracts question-side
structure. The current merge rule (`merge_into_program`) lifts
A5's framing onto shared predicates but **doesn't add A5-only
variables into the causal path**. Case 05's narrative mentions
"大脑警觉水平" (alertness); the agent's A5 pass would have
extracted it as a candidate variable but A1 didn't see it in the
question, so it didn't become a mediator.

This isn't quite F5 (hidden confounder) — it's a wider issue:
**narrative mediators stay orphaned**. The prompts are strict
about not inventing intermediates not in the question; so
narrative-mentioned mediators need an explicit channel to enter
the question's structure.

**Actionable**: addressed by #37.c narrative_to_edges prompt +
merge rule that lifts narrative edges into the question-side
DAG when their endpoints overlap with question variables.

### (R3) A5 pattern-input gap (case 10)

A5 prompt is written for first-person habit descriptions. Third-
person statistical patterns (case 10's "办公室里感冒的人明显变多")
aren't covered — A5 returned empty.

**Actionable**: either (a) extend A5 to accept third-person
population-scale observations, or (b) add a sibling prompt for
"stylized-fact" narratives. Low priority — deferred until more
cases like this surface.

## Findings the real run confirmed

Every sim-predicted loss was confirmed in real-LLM:

- F3 silent intent pick: **100% confirmed** (agent followed
  prompt's cue-to-intent table mechanically)
- F5 hidden confounder dropped: confirmed
- F6 alias kept separate: confirmed
- F7 negation variable emission: confirmed (real-LLM did the bad
  thing, not the good thing)
- F8 critical hallucination on confounded pair: confirmed
- F9 structural-over-eager framing ask: confirmed

## Updated slice ranking

Combining sim + real-LLM findings:

1. **F3 A1 prompt update** — 100% silent-pick rate on ambiguous
   cases, confirmed across sim + real. Biggest real-loss fix per
   unit effort. NL-layer work.
2. **F8 A1 prompt confounder-awareness** — produced an active
   error in real-LLM run. Same NL layer, can bundle with #1.
3. **F7 A1 prompt negation canonicalization** — real-LLM emitted
   the bad variable form. Smallest of the three prompt fixes.
4. **F9 structural-vs-numeric framing scope** — clean kernel-side
   fix, no charter needed. Worth doing alongside #1-3.
5. **R2 A5→A1 wiring gap** — pushes #37.c narrative_to_edges up
   in priority: this is a real workflow gap, not a hypothetical.
6. **R1 eval-time aliasing** — needs the candidate IR (Phase 3
   of user's roadmap). Not a next slice, but a requirement for
   scaling eval set to 20+ with real-LLM drivers.
7. **F6 alias (narrative vs question)** — confirmed real; still
   single-case; keep in queue below #37.c.

## Recommendation

Next slice: **A1 prompt v2** covering F3 + F7 + F8 in one pass +
F9 kernel scope fix. All NL-layer or local; no charter changes
needed.

Then re-run the eval set against A1 v2 and measure: does the
silent-pick rate drop? does F8 CH go away? If yes, prompt work is
the dominant lever and we keep going there before building
narrative-edge machinery.

Only after that: #37.c (narrative_to_edges) to address R2.

Grow eval set to 20+ before declaring "A1 v2 works" — N=10 is
too small to distinguish prompt-improvement signal from noise.

## What didn't work / meta observations

- Strict exact-name scoring needs upgrading to semantic match or
  alias-aware. A simple normalization (case + underscores + stem)
  would catch 4 of the 5 drifts we saw.
- Sub-agent was unexpectedly good at prompt-literal behavior: it
  quoted the A1 prompt's "cue-to-intent" table when picking assoc
  on case 03, which is both a faithfulness win (follows prompt)
  and a diagnostic signal (the prompt's table is WHY F3 is 100%
  silent-pick — it instructs commit, not propose).
- 10 cases took ~3 minutes of sub-agent wall-clock + ~55K tokens.
  Scaling to 20-50 is feasible; 100+ would want batching.

## Known remaining gaps (for next iteration)

- Eval set still N=10; user's threshold is 20+
- Scoring still manual (Python script, not a committed driver)
- Real-LLM driver not yet programmatic (sub-agent runs are
  ad-hoc); a script that drives Anthropic API or DeepSeek
  directly would enable cheap re-runs after each prompt iteration
- No F10+ failure modes yet — need more diverse cases to find them
