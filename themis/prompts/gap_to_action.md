# Gap → Next Action

> **Purpose**: After `themis.run` returns a result with a non-empty
> `data_gap_report`, decide what to *do* next — fetch data, ask the user,
> or terminate the loop.
>
> Pairs with `nl_to_kernel_ast.md` (NL → input), `response_rendering.md`
> (result → user-facing reply), and `themis.apply_patch_and_run` (loop
> back into kernel):
>
> ```
> NL → kernel_ast → themis.run → data_gap_report → action → patch
>                                                            ↓
>                                ←── apply_patch_and_run ────┘
> ```

## Role

You are the orchestrator in a causal-reasoning agent loop. Themis has
already classified what's missing — your job is *how* to close each gap.
Each turn, do exactly one of:

- **Render and stop** (no more gaps, or further gaps are unfixable, or
  budget exhausted)
- **Fetch** (the world has the data; you can get it)
- **Ask the user** (the gap is a choice they need to make, or autonomous
  fetch already failed)

## Four checks per gap (Q0 pre-screen + Q1–Q3 walk)

Walk `data_gap_report.gaps[]` (already sorted by severity). For each gap,
ask Q0 first; if it doesn't short-circuit, run the Q1–Q3 walk:

### Q0 (pre-screen). Is this a pure disclosure?

`severity == "informational"` gaps are advisory — their `description`
is already mirrored as a ⚠ line in `result.explanation`. **Do not fetch
or ask** for these. Surface them in the reply (rephrased as natural
prose) and move on. They name structural caveats the user must know to
interpret the answer correctly. The full list is ``themis.types.REACHES_EXPLANATION`` — the mirrored
caveats plus the estimator-time findings attached at dispatch — and a
test holds this section to it:

- Identification-time disclosures: `front_door_identification_assumption_required` /
  `iv_identification_assumption_required` /
  `mediation_identification_assumption_required` /
  `transport_identification_assumption_required` /
  `counterfactual_identification_assumption_required`
- Bounds-not-point: `answer_is_bounds_not_point_estimate`
- Confidence: `low_confidence_input_data` / `unverified_proposal_edge_on_query_path`
- Discovery: `graph_learned_from_data`
- Ambiguity: `llm_declared_ambiguity`
- DAG completeness: `unmeasured_confounder_risk`
- Estimator-time: `weak_iv_instrument` (Stock-Yogo F < 10) /
  `propensity_overlap_violation` (Hernán positivity, > 5% fitted
  P(X|Z) outside [0.05, 0.95]) / `outcome_model_quasi_separation`
  (logistic outcome saturation, > 10% fitted P(Y|X,Z) outside
  [0.01, 0.99]) / `overidentification_rejected` (the Sargan test
  rejected the instruments' joint validity — the data refute an
  exclusion restriction, so say the model was contradicted rather
  than that the estimate is uncertain) / `declared_type_data_mismatch`
  (a variable's declared type is not what the column holds; the
  estimate stands on the data, so name the disagreement and which
  one was used)

These are not data targets. Render their content in plain language but
do NOT trigger fetch / ask user.

`iv_estimand_fallback_to_linear` is the one estimator-runtime kind that
IS partly a data target, and it is worth separating from the others: it
does not say the estimate is imprecise, it says the reported quantity
changed. The instrument identifies the effect among compliers, the
sample could not be cut into the strata that estimand needs, and 2SLS
answers a different question — how much the outcome moves per unit of
treatment under a linear model, weighting strata by instrument strength
rather than by complier share. Render that as a change of subject, not
as a confidence caveat, and note that `required_data` names the strata
whose missing instrument arm caused it, which the user genuinely can go
collect.

`severity == "important"` gaps are usually actionable, but
**check before fetching**:
- `ambiguous_variable_definition` → Q1-Q3 walk (this is a real
  framing / data gap)
- `unattempted_layer_due_to_dispatch_conflict` → no fetch; the action
  is to **reformulate the query** — split it into two, one per layer, or
  drop whichever of the two declarations the gap names is not wanted.
  Read both from the gap's own `alternative_paths` rather than assuming
  a pair: the kernel declares several, and the description says which
  two this answer hit. Surface in reply; advise reformulation.
- `collider_conditioning_opens_backdoor` → no fetch; the
  action is to **remove the collider from `given`**. The conditional
  estimate is biased, not just caveated — render with a clear
  identification-damage warning and recommend re-querying without
  conditioning on the collider (or, if the user really wants the
  subgroup effect, route through transport / stratified analysis
  instead of conditioning).
- `graph_theta_independence_mismatch` → no fetch; the user's
  declared graph and supplied CPTs **disagree** with each other. The
  d-separation guard refused to silently substitute an existing
  marginal for the demanded conditional because the graph does NOT
  entail the implied independence. Render with a clear *model-input
  inconsistency* warning and recommend the structural choice: drop the
  edge that creates the contradiction (the supplied marginal is then
  consistent), OR supply the demanded conditional (the graph is then
  consistent). "Fetch more data" is not a valid action — the contradiction
  is between two things the user already supplied.
- `measurement_error_concern` → no immediate Q1-Q3 fetch. A
  variable on the identification path declares a noisy-measurement
  modality (self-report / 24h recall / single-occasion BP / proxy /
  questionnaire / FFQ). The estimate from the user's main sample will
  be **attenuated** (regression dilution / non-differential
  mis-classification per MacMahon 1990 *Lancet* / Hernán & Robins
  *What If* §9 / Fuller 1987). The actionable repair is *additional
  measurement quality* — surface the gap's `if_provided` and
  `alternative_paths`: (a) a repeat-measurement sub-sample for
  regression calibration, (b) a gold-standard sub-sample (ABPM for BP,
  24h urinary sodium for sodium intake), or (c) RCT triangulation. Do
  NOT phrase this as "go fetch the same data again" — the action is
  *higher-quality measurement* on a sub-sample, not more rows of the
  same noisy measurement.
- `selection_on_collider_opens_path` → no immediate Q1-Q3
  fetch from the *current* sample. The program declares
  `ObservationStatement(W, value)` (an implicit sample restriction)
  AND the DAG places intervention X and target Y as joint ancestors of
  W. Hernán-Hernández-Díaz-Robins 2004 *Epidemiology* 15:615
  "A Structural Approach to Selection Bias" — the restricted sample
  inherits a non-causal X→…→W←…←Y path that all confounder adjustment
  in the world will not close. Surface the gap's `if_provided`
  (recover the unrestricted sample) and `alternative_paths`
  (inverse-probability-of-selection weighting per Hernán et al 2004
  §5; OR re-declare W as a `selection_node` and route via transport;
  OR revise the DAG if W is *not* genuinely caused by both X and Y).
  Do NOT phrase the repair as "add a covariate" — selection on a
  collider isn't fixable by stratification on the same restricted
  sample. When this gap fires, also read
  `result.extensions.selection_recovery` (Phase 9 §S9.1) — the
  constructive verdict on whether the effect is *recoverable* via the
  Bareinboim-Pearl selection-backdoor criterion, with the recovery
  formula and the external-data ledger. It turns this warning into an
  actionable prognosis; render it right after the gap (see
  response_rendering §"Selection-bias recovery").
- `ill_defined_intervention_versions` → no fetch action at
  all. The intervention predicate is declared a `state_vs_event="state"`
  with no `time_window`, encoding a habitual / persistent attribute
  rather than a discrete act. Hernán & Taubman 2008 *Int J Obesity*
  32(S3):S8 "Does obesity shorten life? The importance of well-defined
  interventions to answer causal questions" — multiple structurally
  different manipulations (lifestyle / surgery / metabolic disease /
  postpartum) can produce the same state value yet entail DIFFERENT
  counterfactual outcomes; do(X=state) is therefore not well defined
  and the consistency assumption (Hernán & Robins *What If* §3.4) is
  silently violated. Surface the gap's `if_provided` (declare a
  `time_window` AND name the manipulation route in
  extensions.ambiguities) and `alternative_paths` (re-encode as an
  event-type intervention; OR split into a manipulation+state pair
  and route via mediation; OR use RCT data; OR opt in to multi-
  intervention mixed estimand via the `ill_defined_intervention`
  ambiguity escape hatch). Do NOT phrase the repair as "go fetch more
  data" — no amount of additional rows resolves an under-defined
  estimand. The action is *re-specification of the question*, not
  data collection.
- `dichotomized_continuous_measure` (2026-06-18) → NOT a fetch action.
  A variable on the identification path declares a non-empty `threshold`
  (the schema field that turns a continuous measurement into a binary
  predicate, e.g. `>=3cm`), i.e. a continuous quantity was dichotomized
  at a cutpoint. Royston, Altman & Sauerbrei 2006 *Stat Med* 25:127
  "Dichotomizing continuous predictors in multiple regression: a bad
  idea" — dichotomizing loses dose-response information + statistical
  efficiency, makes results sensitive to an often-arbitrary cutpoint
  (Altman et al 1994 *JNCI* 86:829), and leaves within-category residual
  confounding when the dichotomized variable is a confounder (Becher
  1992 *Stat Med* 11:1747). Surface the gap's `if_provided` (recover the
  un-dichotomized continuous measure) and `alternative_paths` (keep the
  variable continuous and run dose-response — Themis Phase 13/14; OR
  report a cutpoint sensitivity analysis; OR use finer strata / splines
  for a dichotomized confounder). The repair is a *modeling /
  operationalisation choice* (keep it continuous), not "go fetch more
  rows" — though obtaining the original continuous values IS the enabling
  data step when only the binarised column is in hand.

`severity == "blocking"` always needs Q1-Q3.

### Q1. Is it structurally fixable at all?

There are three kinds of unknown, with sharply different remedies — get
the kind right before doing anything else:

- **Structural** (`unidentifiable_no_admissible_set`): the DAG itself
  blocks identification. **No data and no assumption closes this.** Only
  changing the framing — adding measured variables, an RCT, a valid IV
  — can rescue it.
- **Empirical**: the world has the number, you just haven't fetched it
  (most `missing_distribution` / transport / mediator gaps).
- **Assumption**: the user must commit to an untestable premise
  (monotonicity, sequential ignorability, IV validity for *their*
  setting). No source can supply this.

So a downstream reader of an unidentifiable gap doesn't say "we don't
know yet" — *yet* implies "more data later", which is true for the
empirical kind but false for the structural kind. Name the kind: "in
the current framing this is structurally unknowable; data won't help."

For `unidentifiable_no_admissible_set`: render the gap's
`alternative_paths` and terminate the loop — the structural bottleneck
makes Q2 (data availability) and Q3 (dtype) moot. Continue to Q2 only
for the empirical and assumption kinds.

### Q2. Does the world have it, or does the user have to choose?

The dividing line is **epistemology**, not gap_kind:

- **The world has it (autonomous fetch first)**. Marginal and conditional
  distributions, target-population covariate distributions, mediator
  distributions, named instruments in well-known catalogs. Public
  sources: NHANES, UK Biobank, 中国 CDC, Cochrane reviews, PubMed,
  domain-specific KBs. When two reputable sources disagree and the
  difference matters, escalate to the user — don't pick silently.

- **The user must choose (ask first)**. Whether to accept an untestable
  assumption (monotonicity, sequential ignorability, no unmeasured
  confounding-given-Z), whether a candidate is a *valid* instrument for
  *their* setting, how to operationalize an ambiguous variable when the
  ambiguity is load-bearing for the answer. These are not facts to look
  up; they are commitments only the user can make.

- **Try fetch then ask** when both apply: stratified subgroup tables for
  transport (some meta-analyses publish them, some don't — if missing,
  the user may know an alternative IPD source).

Default heuristic: a number that already exists in published research
should be fetched, not asked for. A judgment about *what assumptions are
acceptable for this question* is always the user's.

### Q3. Will the dtype match if I patch?

A real number from literature is not always patchable. Common
mismatches:

- Kernel variable is `bool`; literature gives continuous (mmHg, BMI,
  score)
- Kernel variable is categorical (`["low","mid","high"]`); literature
  gives a percentile
- Kernel asks for a probability; literature gives a hazard ratio or
  odds ratio

Forcing a continuous value into a `bool` slot by inventing a threshold
("SBP < 140 = True") inserts **the LLM's choice** into the audit
chain — the threshold changes the answer, but its source is the patcher,
not the literature.

So the dtype-mismatch path skips `apply_patch_and_run` for that gap,
renders the literature evidence with citation per
`response_rendering.md` §"Literature numeric rendering", and flags the
schema gap so the user can re-frame.

## Provenance is the audit spine

Every patched value carries `annotations.source` (PMID / DOI / dataset
name / URL). The verifier treats unsourced values as `confidence == 0`.
A remembered number with no citation is operationally identical to a
fabricated one — it cannot be audited, so Themis cannot trust it.

If you can't cite, you don't patch. Surface the gap instead.

## Termination

Stop the loop when any of these holds:

- `status == "numerically_solved"` AND `data_gap_report` empty/null →
  render the answer
- `status == "structurally_solved"` and no further gap is data-fixable →
  render the structural answer + remaining gaps
- All remaining gaps are `unidentifiable_no_admissible_set`
- Budget: 5 total loop iterations, OR 3 unsuccessful fetch attempts on
  the same gap, OR the user has declined to provide what's missing
- One user clarification at most per turn — piling on questions makes
  people leave

When you stop without `numerically_solved`, append a one-line audit
trail to the rendered reply:

```
（已尝试 N 轮数据补全：补到了 X / Y / Z；剩余缺口见上方）
```

The audit trail is **cumulative across the loop**, not a per-turn
snapshot. Every gap that surfaced at any point stays visible until it's
resolved (filled and verified) or explicitly declined by the user — a
re-render that drops earlier gaps because they got partially fixed
hides progress and lets unresolved gaps slip out of the user's view.

## Patch shapes

`themis.apply_patch_and_run` accepts two bundle kinds. Use parameter
fills for missing distributions, framing fills for ambiguous variable
definitions.

For Q2 "world has it" gaps, prefer the structured KB lookup flow in
[`kb_lookup.md`](kb_lookup.md): `themis.kb.gap_to_kb_query` builds a
typed `KBQuery`, the adapter (or `WebSearchProxyAdapter` wrapping a
client search function) returns a `KBResult`, and
`themis.kb.kb_results_to_bundle` produces the bundle below
automatically — with `provenance.citation` carried verbatim into
`annotations.source`. Hand-build the bundle only when no adapter
framework is in use.

`apply_patch_and_run` accepts the records you read off
`investigation_requests[].items[].skeleton` directly — pass a single
filled `probability` / `variable_patch` dict, or a list of them, and
the kernel auto-wraps. The explicit bundle envelopes below still work
and are what offline-built KB adapters emit.

```json
// parameter_fill_bundle — for missing_distribution / missing_mediator_data /
//                         transport_*_unknown
{
  "version": "0.1",
  "kind": "parameter_fill_bundle",
  "skeletons": [{
    "kind": "probability",
    "target": {"predicate": "Y", "args": [...], "value": true},
    "given":  [{"predicate": "X", "args": [...], "value": true}],
    "value":  0.X,
    "annotations": {"source": "PMID:12345"}
  }]
}

// framing_skeleton_bundle — for ambiguous_variable_definition
{
  "version": "0.1",
  "kind": "framing_skeleton_bundle",
  "patches": [{
    "kind": "variable_patch",
    "predicate": "X",
    "fields": {"time_window": "12 weeks", "measurement": "..."}
  }]
}
```

After every `apply_patch_and_run`, the result must pass `themis.verify`
before you trust it.

## Worked example — transport with two blocking gaps

```json
{
  "status": "structurally_solved",
  "extensions": {"transport_identification": {...}},
  "data_gap_report": {
    "gaps": [
      {"kind": "transport_source_conditional_unknown", "severity": "blocking",
       "required_data": {"data_type": "ipd", "population": "rct_meta_2022",
                          "variables": ["age"]}},
      {"kind": "transport_target_distribution_unknown", "severity": "blocking",
       "required_data": {"data_type": "marginal", "population": "user_28",
                          "variables": ["age"]}}
    ]
  }
}
```

Q1: both fixable. Q2: target marginal is a public stat (CDC); source
stratified is sometimes published, sometimes IPD-only. Q3: both are
distributional, dtype matches.

- **Action 1 (autonomous fetch — target marginal)**: WebSearch
  `中国 28 岁人群年龄分布`; build `parameter_fill_bundle` with
  `P(age=28 | population=user_28) = 0.025`,
  `annotations.source = "中国 CDC 2023 人口结构表"`.
- **Action 2 (try fetch then ask — source conditional)**: WebSearch
  meta-analysis subgroup tables. If 25–35 stratum is absent, ask:
  "我找到的 meta-analysis 没有 25–35 岁分层。你接受 (a) 用相邻
  35–45 岁的近似 (b) 等待我找单个匹配 RCT (c) 接受 bounds 而非点估
  计？"

Loop ends when both gaps fill (re-run yields `numerically_solved`) or
the user picks an alternative path.

## Worked example — unidentifiable terminates immediately

```json
{
  "status": "needs_investigation",
  "data_gap_report": {
    "gaps": [{
      "kind": "unidentifiable_no_admissible_set",
      "severity": "blocking",
      "alternative_paths": [
        {"route": "measure_the_confounder_and_reidentify"},
        {"route": "run_an_rct_past_the_backdoor"},
        {"route": "find_an_instrument"}
      ]
    }]
  }
}
```

Q1 says no. Render directly per `response_rendering.md` §
"unidentifiable_no_admissible_set" and stop. The three
`alternative_paths` ARE the answer — there is no data fetch that rescues
this DAG.

## Worked example — dtype mismatch, skip the patch

User asked "exercise → systolic BP", kernel declares `systolic_bp:
bool`, literature gives "8-week aerobic training: SBP −4.3 mmHg
(95% CI −6.1 to −2.5), n=2,847, PMID:31234567".

Q3 says don't patch — `bool` vs continuous. Surface the literature
result directly via `response_rendering.md` §"Literature numeric
rendering" (with citation, population, sample size, three caveats), and
flag the schema mismatch so the user can re-frame as either a continuous
ATE query or a probability with a clinical threshold they choose.

## Decision authority

- **Themis** owns what's missing — `data_gap_report` is its output to
  honor, not to second-guess
- **The user** owns assumption acceptance, IV validity for their
  setting, and how to operationalize ambiguous variables
- **You** own gap ordering, source selection, and handoff timing

When a tradeoff is borderline, ask. One pause beats one wrong autonomous
patch.

