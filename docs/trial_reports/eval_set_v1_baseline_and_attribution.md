# Eval set v1 — baseline run + failure attribution

Date: 2026-04-22

## Scope

10 hand-labeled cases in `docs/eval_set/cases/` covering 9 failure
modes (F1–F9). This report is the first "data-driven slice
selection" pass: run each case through the current A1 + A5 +
merge + themis.run pipeline, score against gold, and quantify
which failure modes dominate so the next slice can be empirical.

## Limitations (read first)

- **No real LLM calls.** The baseline below uses author-simulated
  A1 / A5 output — i.e., what I'd expect a good LLM following
  `themis/prompts/nl_to_kernel_ast.md` + `narrative_to_variables.md`
  to produce. This biases toward "optimistic A1 behavior": real
  LLM drift (phrasing choices, intent mis-classification,
  hallucinated extras) is not captured here.
- **N = 10**, below the user's ≥ 20 threshold. This is a seed;
  a follow-up session should grow to 20+ before relying on the
  attribution percentages.
- Author-simulated means the "did A1 produce X" column is my
  best guess per prompt guidance. A real LLM-driver round will
  tighten this.

Accepting these caveats, the report is **indicative, not
measured**. The goal here is to stand up the eval harness and get
a first read, not to declare a winner.

## Metrics (v1 defined)

- **VR** variable recall = |extracted ∩ gold.predicates| / |gold|
- **ER (must)** edge recall on must-severity edges only
- **ER (should)** edge recall on all gold edges
- **CH** critical hallucination = count of extracted edges that
  match `must_not_infer`
- **AQ** abstention quality = did output surface the listed
  ambiguities? (boolean per case; aggregated as fraction)
- **PC** provenance completeness = fraction of extracted elements
  carrying `annotations.source`

## Per-case baseline run

Simulated-A1 behavior and score per case. "Pipeline output" is
themis.run's actual return on the simulated ast.

### 01 running_weight_loss_underframed (F1)

- Simulated A1: produces bool predicates + single edge running→weight_loss
  with `source=llm_proposal`; no framing fields filled.
- Pipeline output: `needs_investigation`, validate_parameter
  `P(weight_loss=True|running=True)`, define_variable for both
  predicates with 7 missing fields each.
- Score: VR=2/2, ER(must)=1/1, CH=0, AQ=n/a, PC=edge✓.
- **Failure mode attribution**: pure F1 — framing asks exist; user
  gets 7-field × 2-predicate ask list. Output is correct but
  user-facing ask is generic.

### 02 vitamin_d_narrative_edge (F2)

- Simulated A1 on question alone: produces vitamin_d_supplement →
  cold_frequency_reduced. No narrative framing fields extracted
  because A5 is a separate pass the orchestrator has to invoke.
- Pipeline output (with A5 applied): `needs_investigation`,
  validate_parameter, define_variable only on unfilled dimensions.
- Score: VR=2/2, ER(must)=1/1, CH=0, AQ≈0 (ambiguity about
  "personal anecdote vs causal claim" is NOT surfaced — A1 just
  produces a confident `llm_proposal` edge), PC=edge✓.
- **Failure mode attribution**: F2 handled if orchestrator invokes
  A5; fails if A5 isn't invoked. Note: A5 extracts framing hints
  from narrative but doesn't extract the edge itself — the edge is
  present in the question side, so F2 narrowly defined doesn't
  fire here. A variant where the question is "那益生菌呢？" without
  the narrative context would trip the real F2.

### 03 coffee_insomnia_ambiguous (F3)

- Simulated A1: NL prompt instructs "choose one intent";
  deterministically picks `cause` (assertion strong) or `assoc`
  (if 有关系 treated as correlational). Either way, silently
  commits.
- Pipeline output: `structurally_solved` / True, single derivation
  chain, no ambiguity flagged.
- Score: VR=2/2, ER(should)=1/1, CH=0, **AQ=0**, PC=edge✓.
- **Failure mode attribution**: pure F3. The A1 prompt's
  one-intent-per-example design makes this failure *systematic* —
  every ambiguous question produces confident output. The cost
  here happens to be zero (both readings give TRUE) but for other
  ambiguous pairs it would silently mislead.

### 04 stress_chain_diabetes (F4)

- Simulated A1: produces 4 variables + 3-edge chain correctly (the
  question names the chain explicitly, so A1 has enough signal).
- Pipeline output: for effect query with empty given, backdoor
  collapses to empty adjustment → asks for single CPT
  `P(diabetes=True|chronic_stress=True)`. Chain mediators present
  in the graph but not surfaced in the result.
- Score: VR=4/4, ER(must)=3/3, CH=0, AQ=n/a, PC=all edges✓.
- **Failure mode attribution**: F4. Output is not wrong, but the
  chain structure the user asked about is compressed into a single
  CPT ask. `supporting_paths` is empty because the structural
  result path wasn't exercised.

### 05 coffee_alertness_admg (F5)

- Simulated A1: produces drinks_coffee → alertness, alertness →
  stays_focused from question common-knowledge. The bidirected
  edge drinks_coffee ↔ stays_focused is extractable from narrative
  via A5+A5b (narrative_to_edges) — **but that prompt doesn't
  exist yet**. So the simulated A1 output misses the bidirected
  edge entirely.
- Pipeline output (without bidirected): goes through DAG backdoor;
  since drinks_coffee has no observed parents, empty adjustment is
  "valid" in the DAG reading — wrong answer shape.
- If bidirected edge IS present (manually added): S3.a front-door
  correctly identifies, as shown in Phase 2.latent S5 e2e tests.
- Score (without bidirected): VR=3/3, ER(must)=2/3 (missed
  bidirected), CH=0, AQ=n/a, PC=partial.
- **Failure mode attribution**: F5 is not reachable from current
  A1+A5 alone — needs narrative_to_edges (#37.c) to lift the
  bidirected claim out of narrative.

### 06 running_jogging_alias (F6)

- Simulated A1 on question: produces `running`. A5 on narrative:
  produces `jogging` (per current narrative prompt's naming rule).
- Merge: `merge_into_program` doesn't auto-alias → two separate
  predicates in the final ast. Question's running→is_healthier
  edge exists but the narrative's framing attaches only to
  jogging, not running. User's intended subject
  (jogging-as-running) is silently split.
- Pipeline output: two disconnected clusters — running + is_healthier
  from question, jogging (richly framed) as a dangling predicate.
  themis.run accepts; DAG has both. `cause` query only asks about
  running → is_healthier, missing jogging's framing.
- Score: VR split (2/3 for question side, jogging dropped as
  un-unified), ER(must)=1/1 (on question), CH=0, AQ=0 (alias not
  surfaced), PC=partial.
- **Failure mode attribution**: F6 — and unlike F5, this one
  actually manifests *today*, not just in theory. Alias silence is
  the real failure.

### 07 skip_breakfast_negation (F7)

- Simulated A1: the prompt guidance says "prefer positive
  predicate names; use value=False for negation". Good output:
  `eats_breakfast` + intervention value=False. Bad output:
  `skips_breakfast` + intervention value=True. Both are
  observed in practice depending on LLM temperature / phrasing.
- Pipeline output (good case): correctly encodes value=False. In
  bad case: silently computes the opposite of intended direction.
- Score (good case): VR=2/2, ER(must)=1/1, CH=0, AQ=n/a, PC=edge✓.
- **Failure mode attribution**: F7 is a prompt-consistency issue —
  the prompt tells A1 to prefer positive forms, but real LLM
  adherence varies. Not measurable without real-LLM runs.

### 08 ice_cream_drowning_confounded (F8)

- Simulated A1: without narrative_to_edges and without F8
  guidance in the A1 prompt, LLM would likely emit
  `ice_cream_consumption → drowning_incidents` because the
  question uses "导致". This is a critical hallucination matching
  must_not_infer.
- Pipeline output: `structurally_solved` / True for the cause
  query — *confirming* the wrong edge. User reads "yes, ice cream
  causes drowning".
- Score: VR=2/3 (temperature confounder missed), ER(must)=0/2
  (both confounder edges missed), **CH=1** (the direct edge is in
  must_not_infer), AQ=0, PC=edge✓.
- **Failure mode attribution**: pure F8. The current prompt doesn't
  instruct A1 to look for confounders or refuse direct edges under
  confounding suspicion. This is a real hallucination path, not a
  simulation artifact.

### 09 smoking_lung_cancer_structural (F9)

- Simulated A1: produces smoking → lung_cancer cause query.
- Pipeline output: `structurally_solved` / True with
  `cause_via_directed_path`. Plus define_variable investigation
  asking 7 framing fields on each predicate.
- Score: VR=2/2, ER(must)=1/1, CH=0, AQ=n/a, PC=edge✓.
- **Failure mode attribution**: pure F9. The answer is correct
  (yes, there's a causal path); the framing ask is irrelevant
  because a cause query doesn't need numeric resolution.

### 10 cold_weather_sick_directional (F1 + F3)

- Simulated A1: produces cold_weather → gets_sick with effect query
  + empty given. Single edge, missing the real mechanism
  (indoor_time → virus_transmission intermediate).
- Pipeline output: `needs_investigation` with 7-field framing on
  both predicates + CPT parameter ask.
- Score: VR=2/2 (at "surface" level), ER(must)=n/a (none at must
  severity), CH=0 (the direct edge is in must_not_infer but
  severity is "should not infer at must severity", not
  "never infer"), AQ=0 (both ambiguities — direction and
  population scope — not surfaced), PC=edge✓.
- **Failure mode attribution**: mixed F1 + F3 + population scope.
  The compound ambiguity is typical of real NL questions.

## Aggregated scores

| Case | VR | ER(must) | CH | AQ | PC |
|---|---|---|---|---|---|
| 01 | 1.0 | 1.0 | 0 | n/a | 1.0 |
| 02 | 1.0 | 1.0 | 0 | 0 | 1.0 |
| 03 | 1.0 | 1.0 | 0 | 0 | 1.0 |
| 04 | 1.0 | 1.0 | 0 | n/a | 1.0 |
| 05 | 1.0 | 0.67 | 0 | n/a | 0.67 |
| 06 | 0.67 | 1.0 | 0 | 0 | 0.5 |
| 07 | 1.0 | 1.0 | 0 | n/a | 1.0 |
| 08 | 0.67 | 0 | **1** | 0 | 1.0 |
| 09 | 1.0 | 1.0 | 0 | n/a | 1.0 |
| 10 | 1.0 | n/a | 0 | 0 | 1.0 |

- Average variable recall: **93%**
- Average must-severity edge recall: **85%** (on cases where
  must-severity applies)
- Critical hallucination count: **1 / 10 cases** (F8 ice cream;
  would likely be more frequent with real-LLM noise)
- Abstention quality: **0 / 6 cases with ambiguity** surfaced any
  of them. Silent-pick rate = 100% on the ambiguous subset.
- Provenance completeness: edges carry `source=llm_proposal` on
  most cases; gaps appear when narrative-derived content doesn't
  flow through (case 05, 06).

## Failure mode attribution

Grouping the losses by failure mode:

| Failure mode | Cases hit | Loss type |
|---|---|---|
| F1 under-framed | 01, 10 | over-eager 7-field ask (annoying but correct) |
| F2 edge-in-narrative | 02 | partially reachable if orchestrator invokes A5 |
| F3 ambiguous intent | 03, 10 | silent pick — 100% |
| F4 chain | 04 | chain collapsed into single CPT ask |
| F5 hidden confounder | 05 | **unreachable** without narrative_to_edges |
| F6 alias | 06 | silent split or silent merge; either bad |
| F7 negation | 07 | depends on real-LLM fidelity |
| F8 must-not-infer | 08 | **critical hallucination** |
| F9 structural framing mismatch | 09 | over-eager 7-field ask on pure cause query |

## Ranking by severity × actionability

- **Critical / acting now**:
  - F8 must-not-infer — produces actively wrong answers ("ice cream
    causes drowning"). Fix path needs A1 prompt updated with
    confounder-awareness or narrative_to_edges capable of proposing
    confounder structure.
  - F3 ambiguous intent — 100% silent pick. Fix path is in A1
    prompt surface (output proposal or clarify).

- **High severity, fix-path clear**:
  - F5 hidden confounder — unreachable without narrative_to_edges.
    Matches user's #37.c call-out.
  - F6 alias — manifests today. Matches user's #37.d (was deferred;
    F6 data says it should move up).

- **Medium, easy wins**:
  - F9 structural-vs-numeric framing scope — G1 from the earlier
    stress test. Low-risk local change in `framing_check` /
    `investigation_pusher`. Not a new capability.

- **Lower priority (known tradeoffs)**:
  - F1 under-framed — partially mitigated by #41; further
    framing fields only if real pressure.
  - F4 chain advisory — output shape change; defer.

## Decision per user's rules

Rule: "如果超过 30% 的失败来自 X, 先做 X."

- F8 + F3 together account for ~30% of the case set with real
  losses (F8 = 1 CH, F3 = 2 silent picks = "structural fail")
  — both live in the A1 prompt layer, not in narrative.
- F5 + F6 (narrative-side) together = 2 cases.
- F1 + F9 framing scope = 2 cases with soft losses.

The N=10 sample is **too small** to make the 30% threshold call
rigorously. What the sample does say:

1. **The NL (A1) layer is the biggest source of non-trivial loss**,
   not the merge layer and not the runtime. Silent intent pick
   (F3) and hallucinated direct cause (F8) are both A1-prompt
   issues.
2. **Narrative-side work (F5, F6, #37.c / #37.d) matters but
   doesn't dominate** in this sample — F5 is unreachable but
   single-case; F6 needs alias machinery.
3. **The structural-vs-numeric scope issue (F9 / G1) is a clean
   local fix** with clear upside and no charter.

## Recommendation

Given N=10 is a seed and the strongest losses concentrate in A1
prompt behavior (F3 silent picks + F8 confounder hallucination),
the **data-driven next slice** is:

1. **A1 prompt update for F3 and F8** — biggest real-loss fix per
   unit effort. Teach A1 to (a) detect ambiguity and output
   proposal-with-clarifying-ask instead of silent pick, (b)
   recognize confounder-smell keywords (correlational descriptors,
   plural subjects, seasonal / temporal patterns) and prefer
   confounder structure over direct cause edge. This is NL-layer
   work, not kernel work.

2. **F9 scoping fix** — alongside #1 because they land in the same
   area (how Themis's asks get presented) and the change is small.
   Scope DEFINE_VARIABLE to queries whose kind is effect /
   probability, not cause / assoc / identify.

3. **Grow eval set to 20+** — this report is on N=10. Before
   committing to #37.c or #37.d, need real-LLM runs on 20+ cases
   and measurement of silent-pick / hallucination rates under
   noise.

4. **Then** decide #37.c vs #37.d from richer data.

## What to NOT do (yet)

- Don't start #37.c narrative_to_edges until the eval set covers
  more F5 / F8 variants. One case of each isn't enough to design
  the prompt.
- Don't start #37.d alias warning until F6 is seen in more than 1
  case.
- Don't start #37.e e2e helper until the candidate IR shape is
  fixed (user's Phase 3 precondition).

## Artifacts

- `docs/eval_set/README.md` — schema + metrics definitions
- `docs/eval_set/failure_modes.md` — F1–F9 taxonomy
- `docs/eval_set/cases/*.json` — 10 cases
- This report

## Known gaps

- No real-LLM-driver implementation yet. The simulated baseline
  could diverge significantly from real behavior (probably more
  hallucination + more negation errors under noise).
- No F10+ failure modes identified yet (multi-object, temporal,
  quantitative-vs-categorical, deep chain, etc.). Add when real
  cases surface them.
- Scoring is manual per-case; a programmatic scorer + driver is
  the next infrastructural step.
