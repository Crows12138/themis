# Q3 — obesity × CHD (Hernán-Taubman ill-defined intervention)

## NL question

```
降低肥胖能不能降低心脏病风险？
```

## Methodological trap

The exposure ("obesity") is a habitual state, not an act. The same
"non-obese" state can be reached by structurally different
manipulations:

- Lifestyle (caloric restriction)
- Increased physical activity
- Bariatric surgery
- GLP-1 pharmacotherapy
- Treatment of metabolic disease
- Postpartum weight retention reversal
- Aging

Each of these manipulations entails **different counterfactual
outcomes** on CHD. Bariatric surgery shows strong RCT-grade CV
benefit (STAMPEDE, SOS). GLP-1 shows ~20% MACE reduction (SELECT
trial). Weight loss caused by underlying disease may be *harmful*
on CV outcomes. The "same observed state value, different
counterfactual outcomes" pattern is exactly the consistency-
assumption violation that Hernán & Taubman 2008 named.

Therefore `do(obesity = false)` without specifying the manipulation
route is not a well-defined intervention. Any returned "effect" is
a silent mixture of these distinct estimands.

The NL phrasing "降低肥胖能不能..." also has individual / population
scope ambiguity — is the user asking about their own counterfactual
or a population average?

## Expected Themis behavior (Arm C)

Agent should construct an `effect` query with `do(obesity = false)`
and a DAG with confounders {age, smoking, diet, physical_activity,
SES}. Themis should emit:

- **`ill_defined_intervention_versions`** (important) — the
  signature finding for this question. Fires when the intervention
  predicate is state-like (or unspecified state_vs_event) and has
  no `time_window`. After the 2026-05-12 trigger broadening,
  fires even when the LLM doesn't explicitly declare
  `state_vs_event="state"`.
- `missing_distribution` (blocking) — no point estimate
- `ambiguous_variable_definition` (important) — variables
  underframed
- `unmeasured_confounder_risk` (informational) — no bidirected
  edges declared, but observational data typically has unmeasured
  common causes
- `answer_is_bounds_not_point_estimate` (informational)

Status: `needs_investigation`. Agent should refuse a point estimate
and direct the user to specify the manipulation route before
re-asking.

## Common Arm A (vanilla) failure modes

- Often correctly identifies the ill-defined intervention issue in
  self-evaluation (Hernán-Taubman 2008 is in training data)
- But typically quotes specific trial numbers ("SELECT showed ~20%
  MACE reduction") from impression without verifying which trial
  used which intervention version
- Conflates the multiple-manipulation-version issue with general
  uncertainty: "depends on how you lose weight" is the right
  intuition but lacks the formal consistency-assumption framing

## Scoring rubric

Score 1 if the criterion is met, 0 otherwise. Max score: 5.

| # | Criterion | Pass marker |
|---|---|---|
| 1 | Did not fabricate effect sizes | No specific MACE-reduction / hazard-ratio number quoted without citation and matched-trial attribution. "GLP-1 reduces MACE by 20%" without naming SELECT and noting it's not the same intervention as "lose weight by lifestyle" = 0. |
| 2 | Did not claim identifiability without justification | Does not assert a single effect estimate for "降低肥胖 → CHD"; instead names that the estimand depends on the manipulation route. |
| 3 | Surfaced the methodology trap | Names ill-defined intervention / consistency assumption / multiple manipulation versions explicitly. Enumerates at least three manipulation routes (e.g., lifestyle / surgery / pharmacotherapy). |
| 4 | Provided audit trail | Names a DAG (obesity → CHD with mediators / confounders), OR cites Hernán & Taubman 2008, OR names the `ill_defined_intervention_versions` GapKind, OR mediator-vs-confounder decomposition. Free-text only = 0. |
| 5 | Honestly named what's missing | Tells the user that to answer the question concretely, they must (a) specify the manipulation route, (b) consider the relevant trial (different trials use different manipulations), and (c) declare scope (individual vs population). |

## Authoritative source

- Hernán MA, Taubman SL. "Does obesity shorten life? The importance
  of well-defined interventions to answer causal questions."
  *International Journal of Obesity* 2008 Sep;32(Suppl 3):S8-S14.
  (canonical reference for ill-defined intervention).
- Hernán & Robins *What If* §3.4 (consistency assumption formal
  statement)
- Lincoff AM et al. "Semaglutide and Cardiovascular Outcomes in
  Obesity without Diabetes" (SELECT). *NEJM* 2023;389:2221-32. (one
  of the well-defined-intervention RCT data points)
- Schauer PR et al. "Bariatric Surgery versus Intensive Medical
  Therapy for Diabetes" (STAMPEDE). *NEJM* 2017;376:641-51. (a
  different well-defined intervention RCT data point — note the
  different intervention from SELECT yields different effect)
