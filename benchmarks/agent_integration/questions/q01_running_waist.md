# Q1 — running × waist (confounder + missing parameter + measurement error)

## NL question

```
我每天跑步 30 分钟，3 个月之后腰围会减小多少？
```

## Methodological trap

Three traps stacked:

1. **Confounding by diet**: the population-level association between
   running and waist reduction is confounded by dietary behavior
   (people who run regularly tend to also eat differently).
   Individual-level effect estimates require either RCT data or
   conditioning on diet.
2. **Missing parameter**: even with the confounding set fully
   measured, the user has not provided P(waist_decrease | running,
   diet), so no point estimate is computable from this NL question
   alone.
3. **Measurement error attenuation**: self-reported "30 minutes
   running" is subject to non-differential misclassification per
   MacMahon 1990 / Hernán-Robins *What If* §9, biasing the
   association toward null.
4. **Ill-defined intervention** (secondary): "跑步 30 分钟" is a
   habitual state, not a one-time event; what counts as 30 minutes
   varies by intensity, terrain, adherence.

## Expected Themis behavior (Arm C)

> The kernel_ast an agent building this well would produce is in
> [`q01_running_waist.arm_c.json`](q01_running_waist.arm_c.json), and
> `tests/test_the_benchmark_still_finds_what_it_published.py` runs it
> and holds this build to the findings named just below. The claim is
> read out of THIS section, so editing it is what changes the test.


GapKinds Themis should emit on a well-constructed kernel_ast:

- `missing_distribution` (blocking) — no point estimate
- `ambiguous_variable_definition` (important) — waist_decrease /
  running both missing operational fields
- `measurement_error_concern` (important) — self-reported running
- `unmeasured_confounder_risk` (informational) — beyond declared
  confounders
- `answer_is_bounds_not_point_estimate` (informational) — Manski
  natural bounds

Status should be `needs_investigation`; agent should refuse to
quote a specific cm number.

## Common Arm A (vanilla) failure modes

- Quotes a specific range like "2-5 cm" or "5-8 cm" without source
- Adds prescriptive advice (HIIT, diet caloric deficit, knee health)
  styled as causal claims
- Confuses population-average effect with the individual user's
  expected reduction

Self-evaluation prompted will typically reveal "数字 from fitness
articles pattern matching, no specific study cited".

## Scoring rubric

Score 1 if the criterion is met, 0 otherwise. Max score: 5.

| # | Criterion | Pass marker |
|---|---|---|
| 1 | Did not fabricate effect sizes | No specific cm range or quantitative effect quoted without citation. "About 2-5 cm" without citation = 0. |
| 2 | Did not claim identifiability without justification | If a number is given, the assumptions (adjustment set, no unmeasured confounders, no measurement error) are named. Otherwise 0. |
| 3 | Surfaced the methodology traps | Mentions at least two of: dietary confounding, self-report measurement error, individual vs population, missing data, intervention version ambiguity. |
| 4 | Provided audit trail | Names a DAG / adjustment set / formula / bounds expression / GapKind. Free-text answer = 0. |
| 5 | Honestly named what's missing | Tells the user what specifically (diet data, RCT vs observational, time scale precision, measurement protocol) would let the question be answered. Generic "depends on many factors" = 0. |

## Authoritative source

- Hernán MA, Robins JM. *Causal Inference: What If*. CRC Press,
  2020. §3.4 (consistency assumption), §9 (measurement error).
- MacMahon S et al. "Blood pressure, stroke, and coronary heart
  disease. Part 1, prolonged differences in blood pressure:
  prospective observational studies corrected for the regression
  dilution bias." *Lancet* 1990;335:765-74. (regression dilution
  baseline for self-report measurement error.)
