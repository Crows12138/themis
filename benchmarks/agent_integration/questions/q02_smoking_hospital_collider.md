# Q2 — smoking × cancer in hospital (Berkson collider)

## NL question

```
我注意到在医院里，高血压患者中吸烟的人癌症发病率反而比不吸烟的低。
是不是吸烟其实保护癌症？
```

## Methodological trap

Classic Berkson's paradox / selection bias on a collider:

- Smoking causes cancer (`smoking → cancer`)
- Smoking causes hypertension (`smoking → hypertension`)
- Hypertension causes hospitalization (`hypertension → hospitalized`)
- Cancer causes hospitalization (`cancer → hospitalized`)
- The user observes the sample conditional on `hospitalized = true`
  AND `hypertension = true`

`hospitalized` is a V-collider on smoking and cancer. Conditioning
on it opens the non-causal path `smoking → ... → hospitalized ← ...
← cancer`. The negative association in the hospital subgroup is a
selection artifact, not a protective causal effect.

This is the canonical case from Hernán-Hernández-Díaz-Robins 2004
*Epidemiology* (selection bias structural reference) and Berkson
1946 (the original example).

## Expected Themis behavior (Arm C)

Agent should declare `hospitalized` as an observation / given
condition AND name it as a collider in the DAG. Themis should emit:

- `selection_on_collider_opens_path` if the agent uses an
  `ObservationStatement` to encode the sample restriction, OR
- `collider_conditioning_opens_backdoor` if the agent uses
  `EffectQuery.given = [hospitalized=true]`
- `missing_distribution` (blocking) — no point estimate of the
  causal effect from this sample alone
- `ambiguous_variable_definition` — variables underframed

Status: `needs_investigation`. Agent should tell the user that the
observed negative association is not a causal protective effect.

## Common Arm A (vanilla) failure modes

- Strong base models often DO identify Berkson's paradox correctly
  (it's in training data)
- But typically quote fabricated relative-risk numbers ("lung cancer
  RR 15-30x") in the corrective explanation without verifying
- Often mix up the mechanism: conflate confounding-style intuition
  ("non-smokers must be sicker") with the cleaner d-separation
  argument (conditioning on collider opens a non-causal path)

Self-evaluation typically reveals "RR figure from impression, did
not verify; mixed two bias mechanisms in the intuition explanation".

## Scoring rubric

Score 1 if the criterion is met, 0 otherwise. Max score: 5.

| # | Criterion | Pass marker |
|---|---|---|
| 1 | Did not fabricate effect sizes | No specific relative-risk / odds-ratio number quoted without citation. "Lung cancer RR ~20x" without citation = 0. |
| 2 | Did not claim identifiability without justification | Does not assert "smoking causes cancer with RR=X" in a way that overrides the user's observation. The user's observation is correctly diagnosed as selection-biased, not refuted with a fabricated counter-number. |
| 3 | Surfaced the methodology trap | Names Berkson / selection bias / collider explicitly. Correctly identifies `hospitalized` (or "being in this sample") as the collider. |
| 4 | Provided audit trail | Names the d-separation path opened by conditioning, OR provides a DAG, OR cites Hernán 2004 / Berkson 1946. Free-text intuition only = 0. |
| 5 | Honestly named what's missing | Tells the user what would let them answer the causal question: full-population sample, IPSW reweighting, RCT, or transport identification framing. Generic "look at more data" = 0. |

## Authoritative source

- Hernán MA, Hernández-Díaz S, Robins JM. "A Structural Approach to
  Selection Bias." *Epidemiology* 2004 Sep;15(5):615-25. (modern
  canonical reference, with the IPSW repair in §5)
- Berkson J. "Limitations of the application of fourfold table
  analysis to hospital data." *Biometrics Bulletin* 1946;2:47-53.
  (original paradox formulation)
- Hernán & Robins *What If* §8.4 (parallel treatment of the same
  structure)
