# Eval set v2 — 7-case increment to N=20 (F11/F12 + F15–F18)

Date: 2026-04-22

## Setup

Seven new cases (14–20) added to bring the eval set from 13 to 20,
hitting the stated weekly target. Four new failure modes added to the
taxonomy: F15 (selection bias / collider conditioning), F16
(counterfactual vs interventional estimand), F17 (mechanism-vs-
existence question kind), F18 (individual-vs-population estimand).

Cases 14 and 15 exercise previously-declared-but-unrun modes (F11
temporal, F12 categorical-numeric). Case 20 is a compound case
stacking F3 + F8 + F15 to see if §3a and §5 coexist cleanly when both
should fire.

Sub-agent pinned to sonnet ran each through the A1 v2 prompt and
`themis.run`; outputs in `docs/eval_set/real_llm_run_v2/1[4-9]_*.json`
and `20_*.json`.

## Per-case summary

### Case 14 — F11 temporal

| Metric | Result |
|---|---|
| Query kind | cause |
| Edges emitted | stays_up_late → feels_tired_next_morning |
| Ambiguities declared | `temporal` |
| themis.run | structurally_solved |

Agent flattened the same-day lag ("熬夜 tonight → 没精神 next
morning") to an atemporal edge AND declared `temporal` ambiguity
noting the compression. Matches F11 expected behavior.

**Verdict**: F11 handled. No prompt change needed — the A1 v2 ambiguity
channel carried the flag.

### Case 15 — F12 categorical

| Metric | Result |
|---|---|
| Query kind | effect |
| Vars | `exercises_regularly`, `blood_pressure_controlled` (BOTH bool) |
| Edges | exercises_regularly → blood_pressure_controlled |
| Ambiguities declared | `categorical_domain` (improvised kind) |

**Two problems**:

1. **Bool collapse without level retention**: The user explicitly
   named 3-level categorical domains (少/中/多 and 低/中/高) and the
   specific level-pair contrast (intervention: 少→多, target: 高 →
   {中,低}). Agent collapsed to bool + renamed predicates. The 少→多
   contrast is inexpressible in the resulting AST.
2. **A1 v2 has no rule for categorical domains**. §2 says "every
   predicate is bool by default". No guidance on *when* to retain
   user-specified multi-level categorical, nor how to encode
   level-pair interventions.

**New gap** (F12a): the A1 v2 prompt needs a rule: if the NL
explicitly names >2 levels for a variable, retain the categorical
domain AND preserve the level-pair contrast in the query (or declare
that it was compressed). Current behavior silently drops user
information.

### Case 16 — F15 selection bias

| Metric | Result |
|---|---|
| Query kind | cause |
| Vars | is_hospitalized, has_diabetes, underlying_illness_severity |
| Edges | underlying_illness_severity → is_hospitalized, → has_diabetes |
| Direct hospitalize→diabetes | **not emitted** (correct) |
| Ambiguities declared | `selection_bias`, `confounder_refusal` |
| themis.run | structurally_solved |

Agent correctly refused the direct edge and proposed the latent
common cause. Declared both ambiguity kinds (one for selection
pattern, one for §3a trigger). The kernel result returns
`structurally_solved` because query atoms enter V via the confounder
edges.

**Verdict**: F15 handled by §3a generalizing well beyond simple
confounder cases. The `selection_bias` kind is improvised; should be
promoted to the A1 v2 §5 named-kinds list.

### Case 17 — F16 counterfactual

| Metric | Result |
|---|---|
| Query kind | effect (Layer-2 proxy) |
| Vars | chose_cs_major, higher_current_income |
| Edges | chose_cs_major → higher_current_income |
| Ambiguities declared | `counterfactual_query` (improvised) |

Agent emitted an interventional-effect program (Layer 2) and
declared the Layer-3 (twin network) gap as
`counterfactual_query` ambiguity.

**Verdict**: graceful Layer-2 fallback + honest estimand-gap
disclosure. The kind name is improvised — A1 v2 has no mention of
counterfactual phrasing ("如果当初…", "要是没…"). **New gap**: add
counterfactual-detection rule + named kind.

### Case 18 — F17 mechanism-vs-existence

| Metric | Result |
|---|---|
| Query kind | cause |
| Edges | smokes → has_lung_cancer |
| Ambiguities declared | `mechanism_vs_existence` (improvised) |

Agent treated "为什么…会导致…" as an existence-of-path query with a
flagged mechanism gap. This is the honest fallback — the kernel's
cause query can't enumerate biological mediators.

**Verdict**: acceptable fallback; kind name improvised. **New gap**:
A1 v2 has no "为什么 / 怎么 / 通过什么机制" detection rule. Suggestion:
add to §5 signal-word table.

### Case 19 — F18 individual-vs-population

| Metric | Result |
|---|---|
| Query kind | effect |
| Vars | takes_drug, blood_pressure_drops |
| Edges | takes_drug → blood_pressure_drops |
| Ambiguities declared | `individual_vs_population` (improvised) |

Agent delivered the population-average effect as the best proxy and
named the estimand gap. The kind name is improvised but semantically
correct.

**Verdict**: acceptable. **New gap**: §5 has a `scope` kind for
population/subpopulation mismatches but not for the ATE-vs-ITE
estimand distinction. Either broaden `scope` or add
`individual_vs_population` as a named kind.

### Case 20 — F3 + F8 + F15 compound

| Metric | Result |
|---|---|
| Query kind | cause (conservative pick over effect) |
| Vars | high_immigration, high_local_unemployment, adverse_economic_conditions |
| Direct edge emitted | **no** (correct) |
| Confounder edges | adverse_economic_conditions → both |
| Ambiguities declared | `confounder_refusal`, `intent` |
| themis.run | structurally_solved |

Stacking §3a (confounder refusal) and §5 (intent disambiguation)
works cleanly. Agent picked `cause` as the conservative intent
default over `effect`, refused the direct edge, emitted confounder
structure. Both ambiguities declared.

**Verdict**: compound patterns compose well.

## Aggregate (N=20)

| Metric | Result |
|---|---|
| themis.run errors | 0 / 20 |
| VR (semantic match) | ~20/20 predicates |
| Must-edge recall | 7/7 required direct edges emitted (cases where gold had must-edges) |
| Refused edges correctly | 3/3 (cases 08, 16, 20) |
| AQ (ambiguity declared where expected) | 11/11 cases with gold ambiguity → declared at least one relevant kind |
| Critical hallucinations | 0 (no must-not-infer edges emitted on 16 or 20) |
| PC | 100% (llm_proposal annotations consistent) |

## A1 v2 prompt gaps exposed by this round

Five distinct improvisations the agent had to make — each a concrete
prompt-side follow-up:

1. **F12a categorical-level contrast** (case 15, most serious): NL
   gives >2 levels + explicit level-pair intervention contrast.
   Current prompt silently bools. **Needs**: "retain categorical
   domain if user names >2 levels; encode level-pair if named; else
   declare `categorical_domain` compression".
2. **F15 selection-bias named kind** (case 16): §3a catches the
   pattern, but `selection_bias` is not a named §5 kind. **Needs**:
   add `selection_bias` to §5 kinds list.
3. **F16 counterfactual detection** (case 17): no rule for "如果当
   初…". **Needs**: §5 signal-word entry + `counterfactual_query`
   kind.
4. **F17 mechanism detection** (case 18): no rule for "为什么 /
   怎么". **Needs**: §5 entry + `mechanism_vs_existence` kind.
5. **F18 ATE-vs-ITE** (case 19): `scope` covers population mismatch
   not estimand mismatch. **Needs**: either broaden `scope` or add
   `individual_vs_population` as a named kind.

None of these block current behavior — agent improvised acceptable
fallbacks on all 5. But the improvised kind names would vary
unpredictably across LLM runs; naming them in the prompt stabilizes
the response-rendering contract.

## Recommendation

Treat the five gaps as a single A1 v2.1 prompt amendment (one edit
batch). Priority order: F12a (case 15 lost user information — it's
not just a naming gap) > F15 > F16/F17/F18 (cosmetic stability).

The eval set has now reached its weekly target (20 cases / 18
modes). Next natural slice: either ship the v2.1 amendment and
re-run the affected cases, OR move to #37.c narrative_to_edges
(still partially covered by §3a and narrative extraction in cases
02/05/08/14/16/19/20).

**No code change this round** — only prompt + eval set growth.
