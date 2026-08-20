# GapKind reference — single-source table for all 30 gap_kinds

> **Authoritative source**: ``themis.types.GapKind`` enum.
> This document mirrors that enum for human reading.
> A sync pin (``test_every_gap_kind_documented_in_reference``) asserts
> every enum value has a row here verbatim — adding a new GapKind
> without updating this file breaks the test.

Themis's data-gap-diagnostician position (VISION line 248-298) lives
in the gap_kind taxonomy. Each gap names a specific reason an answer
is incomplete or caveated, plus what's needed to close it. Gaps come
from three places: the **classifier** in
``themis/output/data_gap_report.py`` (program-shape signals + result-
envelope inspection), the **estimator-runtime hooks** in
``themis/estimation/dispatch.py`` (post-fit diagnostics), and a
**must-disclose channel** in ``themis/runtime/scheduler.py`` that
auto-mirrors selected kinds to ``result.explanation`` as ⚠ lines.

For the LLM-side rendering / decision rules see
``themis/prompts/response_rendering.md`` (mirrored-set table) and
``themis/prompts/gap_to_action.md`` (Q0 INFORMATIONAL pre-screen).

## Table

| GapKind value | Severity (typical) | Blocks | Description |
|---|---|---|---|
| `unidentifiable_no_admissible_set` | blocking | identification | DAG itself blocks identification — no data closes this; the structural bottleneck is the only fix (add measured Z, RCT, valid IV). |
| `missing_distribution` | blocking | point_estimate | Backdoor / front-door formula needs a probability conditional Themis doesn't have; ``signature`` field tags marginal vs conditional vs joint. |
| `missing_population_distribution` | blocking | identification | Phase 9 §T9.1 transport — target population marginal P*(Z) needed. **No producer**: multi-source transport (§T9.2 / §T9.3) does not exist in the kernel, so nothing can raise it. Declared in ``data_gap_report.GAP_KINDS_WITH_NO_PRODUCER``. |
| `missing_assumption` | important | point_estimate | Fires on the assumption-group investigation channel — a ``MissingKind.ASSUMPTION`` item — not on a result status. (It was keyed on ``ResultStatus.NEEDS_ASSUMPTION`` until 2026-07-27; that status has had no producer since the counterfactual cell was rebuilt around bounds, and a classifier keyed on it emits nothing while nothing fails.) Three shapes arrive here: a premise the kernel refuses to choose for you (``effect:iv_monotonicity_undeclared`` — an instrument alone does not pick between Wald, 2SLS and bounds), an input only an experiment can supply (``causation:``/``counterfactual:interventional_risk_unavailable`` — P(Y=1\|do(x)) under confounding), and declared inputs that contradict each other (``causation:interventional_risks_infeasible`` outside the consistency band, ``effect:iv_stratum_weights_not_normalized``, ``effect:iv_first_stage_degenerate``). Because the repair differs across the three, the gap carries the item's own ``reason`` as its description and offers no generic alternative path. |
| `missing_unit_observation` | blocking | point_estimate | Observation-group investigation item. A deterministic SCM counterfactual recovers this unit's exogenous term by abduction from its own measured values, so what is wanted is a reading for *this unit* — a distribution over units does not substitute, which is why it is not a `missing_distribution`. Before 2026-07-27 no classifier read the observation group at all and these items produced no gap. |
| `missing_structural_input` | blocking | point_estimate | Residual for any structure-group investigation item no more specific classifier claimed — an undeclared path coefficient, a mediator that lies on no directed path, a query atom absent from V, a conditioning event with probability zero in every model the graph admits. Deliberately does **not** assert that identification failed: a missing coefficient leaves a point-identified estimand whose number was simply never declared, and `unidentifiable_no_admissible_set` is the kind `answer_tier` reads to conclude the point is blocked. Its purpose is to make the default loud — the specific classifiers match items by name, so before this kind existed a name none of them matched produced no gap and left the report reading `gaps == []`, its own signal for "asked and got a clean bill of health". |
| `missing_iv_candidate` | blocking | identification | IV-shape detected in the program but no instrument was nominated. **No producer**: the classifier that raised it read for a *failed* IV derivation step, and the kernel writes only steps that succeeded — it says "not identifiable" with a `tian_hedge_witness` step or an investigation item. It is also absent from ``MISSING_ITEM_GAPS``, so no item may declare it. Declared in ``data_gap_report.GAP_KINDS_WITH_NO_PRODUCER``; a producer that wants one adds the species to that vocabulary and binds a renderer. |
| `missing_mediator_data` | blocking | point_estimate | Mediation identification requires P(M\|X) and/or P(Y\|M,X) data the user hasn't provided. |
| `transport_target_distribution_unknown` | blocking | identification | Phase 9 §T9.1 / Bareinboim transport — selection diagram needs target marginal of S-affected variables. |
| `transport_source_conditional_unknown` | blocking | identification | Phase 9 §T9.1 — source population conditional needed for the transport formula. |
| `ambiguous_variable_definition` | important | interpretation | A1 framing fields (time_window / measurement / threshold / direction / etc.) unset; downstream semantic is undetermined until filled. |
| `dose_response_data_required` | blocking | point_estimate | Phase 13 — user asked for a dose-response curve but data spec (sampling points × n per point) hasn't been pinned. |
| `unverified_proposal_edge_on_query_path` | informational | interpretation | The structural answer rests on edges flagged as ``annotations.source: llm_proposal``; reasoning replays an LLM assumption rather than evidence-backed graph. |
| `iv_identification_assumption_required` | informational | interpretation | IV path used; renderer must surface IV1/IV2/IV3 + monotonicity (LATE) or linearity (2SLS ATE) caveats. |
| `mediation_identification_assumption_required` | informational | interpretation | NDE/NIE assume sequential ignorability + no intermediate confounder + consistency; CDE has weaker assumption set. |
| `transport_identification_assumption_required` | informational | interpretation | Phase 9 §T9.1 — S-admissibility + correct selection-node specification needed for the transferred estimate to be valid outside the source population. |
| `llm_declared_ambiguity` | informational | interpretation | A1-emitted ``extensions.ambiguities[]`` entry — LLM flagged uncertainty the user should know about (mechanism vs existence, individual vs population, etc.). |
| `answer_is_bounds_not_point_estimate` | informational | interpretation | Bounds layer (Phase 12) attached symbolic interval rather than a point — the answer IS bounds, not a missing point estimate. |
| `low_confidence_input_data` | informational | interpretation | Composite confidence aggregator dropped below threshold — input theta values themselves are noisy. |
| `front_door_identification_assumption_required` | informational | interpretation | Pearl front-door criterion premises (no direct edge X→Y; M is complete mediator; M and Y unconfounded given X). |
| `counterfactual_identification_assumption_required` | informational | interpretation | Phase 5 §C — consistency / composition axioms needed for the counterfactual quantity. |
| `graph_learned_from_data` | informational | interpretation | DAG was learned via Phase 8.1 discovery (PC / FCI / LiNGAM) — uncertainty in the structural identification claim. |
| `unmeasured_confounder_risk` | informational | interpretation | DAG declares confounders but no bidirected edges — measured-covariate adjustment may have residual unmeasured-confounder bias (HRT-CVD / Card 1995 schooling / vitamin D-CVD pattern). |
| `unattempted_layer_due_to_dispatch_conflict` | important | interpretation | Query declared two identification layers that one dispatch cannot both do; the cascade answered the higher-precedence one and the other was never attempted. Every such pair — and why it cannot be done in one pass — is declared on `Route.displaces` in `themis/routing.py`; mediation × transport (which must be sequential per Cole & Stuart 2010 / VanderWeele 2016 §6.2) is one of them. |
| `weak_iv_instrument` | informational | interpretation | First-stage F-stat below Stock-Yogo (2005) threshold (10); IV estimate's bias toward OLS scales with 1/F and standard 2SLS asymptotic CIs underestimate uncertainty. |
| `iv_estimand_fallback_to_linear` | informational | interpretation | A binary-Z / binary-X design whose instrument is valid only given W names the stratified Wald (the LATE on compliers), but the sample could not be cut into those strata — W continuous, too many cells, or a cell holding only one instrument arm — so the estimate fell back to 2SLS. 2SLS with W entered additively weights each stratum's effect by the instrument's residual variance there rather than by that stratum's complier share, so the two agree only when the first stage is equally strong everywhere. Discloses the substitution, not a quality loss. |
| `overidentification_rejected` | important | interpretation | Over-identified 2SLS (q ≥ 2 instruments) — the Sargan over-identification test rejects the instruments' joint validity (p < 0.05); the data refute at least one exclusion restriction. A falsification (linear analogue of the Balke-Pearl instrumental inequalities), not a data-quantity gap: it will not resolve with more of the same data. |
| `propensity_overlap_violation` | informational | interpretation | Fitted P(X\|Z) outside [0.05, 0.95] for >5% of sample; backdoor / g-formula extrapolates the outcome regression into off-support territory (Hernán & Robins ch.3 positivity). |
| `collider_conditioning_opens_backdoor` | important | identification | EffectQuery `given` contains a node where both X and Y are ancestors (collider). Conditioning OPENS the X→…→W←…←Y path per Pearl d-separation; the conditional effect is biased. F27 names the upstream NL pattern. |
| `outcome_model_quasi_separation` | informational | interpretation | Fitted P(Y\|X,Z) saturated near 0/1 for >10% of sample; logistic logits blow up, plug-in g-formula extrapolates with near-singular gradient, CI underestimates uncertainty. |
| `graph_theta_independence_mismatch` | important | point_estimate | The user supplied a marginal P(target\|S) that the d-separation guard would have used to substitute the missing conditional, but the declared graph does NOT entail target ⊥ extras \| S (chain DAG + marginal-only theta is the canonical case). Repair is structural — drop the offending edge OR supply the demanded conditional — not "supply more theta". Routes via the same investigation-request channel as missing_distribution; classifier branches on the d-sep refusal signature in item.reason. |
| `measurement_error_concern` | important | identification | At least one variable on the identification path declares a (`measurement` \| `observability`) field whose value names a documented noisy-measurement pattern (self-report / questionnaire / 24h recall / single-occasion BP / FFQ / proxy). Regression dilution / non-differential mis-classification attenuates the estimate (MacMahon 1990 *Lancet* 335:765 — single-occasion BP attenuates BP-CHD slope ~60%; Hernán & Robins *What If* §9; Fuller 1987 *Measurement Error Models*). The gap names each flagged variable's ROLE, because that is what decides the consequence: attenuation from the exposure, residual confounding from a covariate, and — for a CONTINUOUS outcome under classical additive error — no bias at all, only a precision cost the numeric end quantifies (`result.outcome_error`) instead of correcting. Suppressed when extensions.ambiguities[*] already declared `measurement_quality` (case 011 escape-hatch path). L3 case 013. |
| `selection_on_collider_opens_path` | important | identification | The implicit-selection shape, complementing the explicit-conditioning kind) — an ObservationStatement on node W encodes implicit sample restriction to W=value, AND W has both intervention X and target Y as directed ancestors. Conditioning on the implicit restriction opens X→…→W←…←Y per Pearl d-separation; the marginal effect estimate from the restricted sample is selection-biased. Hernán-Hernández-Díaz-Robins 2004 *Epidemiology* 15:615 "A Structural Approach to Selection Bias" Figure 3-style HIV/AZT → AIDS-death cohort. Distinct from `collider_conditioning_opens_backdoor` (explicit `given`-list conditioning) and from `SelectionNode` (Phase 9 §T9.1, transport diagram for cross-population). L3 case 014. |
| `dichotomized_continuous_measure` | informational | interpretation | 2026-06-18 (dichotomization; fourth field of that shape after the measurement / 206 ObservationStatement / 207 state_vs_event lineage) — a variable on the identification path declares a non-empty `threshold` (the schema field "Cutoff that turns a continuous measurement into this predicate's value, e.g. >=3cm"), i.e. a continuous quantity was dichotomized at a cutpoint. Its ABSENCE drove `ambiguous_variable_definition`; its PRESENCE — the fingerprint of dichotomization — produced no signal until this kind. Dichotomizing loses dose-response info + efficiency (Royston, Altman & Sauerbrei 2006 *Stat Med* 25:127), makes results cutpoint-sensitive (Altman et al 1994 *JNCI* 86:829 — data-driven "optimal" cutpoints inflate type-I error), and leaves within-category residual confounding for a dichotomized confounder (Becher 1992 *Stat Med* 11:1747). INFORMATIONAL — a declared cutpoint does not break identification; points at Themis's own dose-response path (Phase 13/14) as the continuous alternative. Suppressed when extensions.ambiguities[*] declares `kind in {dichotomization, arbitrary_cutpoint, continuous_dichotomized}`. |
| `declared_type_data_mismatch` | important | point_estimate / interpretation | 2026-07-11 pre-flight data diagnostic (borrow-list #3 — the first gap driven by the ACTUAL supplied data, not program shape) — a model variable positively declares its measurement type (`scale` = binary/discrete/continuous, or an enumerated `domain`) and the CSV column contradicts it: declared `scale="continuous"` but only 2 distinct values (`signature=declared_continuous_data_discrete`, blocks interpretation — the dose-response estimand collapses to a binary contrast), or declared binary/discrete but the data has more / out-of-domain values (`signature=domain_violated`, blocks point_estimate — the declared estimand rests on a false premise). Silent on consistent programs and on undeclared variables (absence of `scale`/`domain` is "didn't say", never "said continuous"). Evidence recorded in `extensions.type_reconciliation`; `verify_type_reconciliation` re-derives the verdict from the recorded n_unique / dtype_kind / distinct-value set. No external causal library reconciles declared variable scale against supplied data — Themis owns both the variable schema and the data contract. |
| `ill_defined_intervention_versions` | important | identification | The well-defined-intervention prerequisite; third field of that shape, after `measurement` and the ObservationStatement) — the EffectQuery's intervention predicate's VariableDeclaration declares `state_vs_event="state"` AND has no `time_window`. Multiple structurally-different manipulations producing the same state value entail different counterfactual outcomes; do(X=state) without naming the manipulation route silently violates consistency (Hernán & Robins *What If* §3.4). Hernán & Taubman 2008 *Int J Obesity* 32(S3):S8-S14 "Does obesity shorten life? The importance of well-defined interventions to answer causal questions" canonical structural pattern. Repair is question re-specification, NOT data fetching. Suppressed when extensions.ambiguities[*] declares `kind in {ill_defined_intervention, well_defined_intervention}` (escape hatch mirroring case 011's `measurement_quality`). L3 case 015. |

## Categories (cross-reference with code)

**Phase 10 §10.3 initial 8** (classifier-driven, ``themis/output/data_gap_report.py``):
``unidentifiable_no_admissible_set``, ``missing_distribution``,
``missing_population_distribution``, ``missing_assumption``,
``missing_iv_candidate``, ``missing_mediator_data``,
``transport_target_distribution_unknown``,
``ambiguous_variable_definition``.

Two of those eight no longer have a classifier:
``missing_population_distribution`` never had a signal, and
``missing_iv_candidate``'s read for a failed derivation step, which the
kernel stopped writing. Both are declared in
``data_gap_report.GAP_KINDS_WITH_NO_PRODUCER``.

**Must-disclose channel** (auto-mirrored to ``result.explanation`` by
``themis/runtime/scheduler.py._attach_structural_caveats``;
``_MUST_DISCLOSE_GAP_KINDS`` set):
``unverified_proposal_edge_on_query_path``,
``iv_identification_assumption_required``,
``mediation_identification_assumption_required``,
``transport_identification_assumption_required``,
``llm_declared_ambiguity``, ``answer_is_bounds_not_point_estimate``,
``low_confidence_input_data``,
``front_door_identification_assumption_required``,
``counterfactual_identification_assumption_required``,
``graph_learned_from_data``, ``unmeasured_confounder_risk``,
``unattempted_layer_due_to_dispatch_conflict``,
``collider_conditioning_opens_backdoor``,
``graph_theta_independence_mismatch``,
``measurement_error_concern``,
``selection_on_collider_opens_path``,
``ill_defined_intervention_versions``,
``dichotomized_continuous_measure``.

**Additional data-need** (NOT must-disclose; surface only via
``data_gap_report``):
``transport_source_conditional_unknown``,
``dose_response_data_required``.

**Estimator-runtime** (attached during ``themis.estimate`` dispatch
NOT by the classifier; require fitted estimate to inspect):
``weak_iv_instrument`` (post-IV first-stage F),
``iv_estimand_fallback_to_linear`` (post-IV estimator resolution),
``propensity_overlap_violation`` (post-backdoor logistic propensity
fit), ``outcome_model_quasi_separation`` (post-backdoor logistic
outcome fit).

## Adding a new GapKind

1. Add enum value to ``themis/types.py`` ``GapKind`` with comment
   noting motivation / example trigger.
2. Add to ``query_result.schema.json`` ``kind`` enum.
3. Decide whether classifier-driven (write
   ``_classify_<name>`` in ``themis/output/data_gap_report.py``,
   wire into ``compute_data_gap_report``) or estimator-runtime
   (write ``_attach_<name>_warning`` helper in
   ``themis/estimation/dispatch.py``, wire into appropriate
   estimator path).
4. Add to ``themis/verifier/data_gap_rules.py`` registry with
   provenance ref_kind set.
   A kind with neither is declared in
   ``data_gap_report.GAP_KINDS_WITH_NO_PRODUCER`` with the reason its
   slot is open; a census in
   ``tests/test_no_step_the_kernel_wrote_says_it_failed.py`` holds that
   table to the tree, in both directions.
5. Say where it belongs among the three declared sets in
   ``themis/types.py`` — ``MIRRORED_INTO_EXPLANATION`` (a caveat
   prepended to ``explanation``), ``ESTIMATOR_TIME_FINDINGS`` (reaches
   ``explanation`` in the estimator's own words), or
   ``GAP_REPORT_ONLY_ASKS``. An unclassified kind raises at import, so
   this step cannot be skipped.
6. If mirrored: add it to the mirrored-set table in
   ``themis/prompts/response_rendering.md``.
7. Add it to the Q0 INFORMATIONAL list in
   ``themis/prompts/gap_to_action.md`` if it reaches ``explanation`` by
   either route.
8. **Add a row to this reference table.**
9. Bump ``COVERAGE_MAP.md`` 元基础设施 row's gap_kind count.
10. Write tests covering the trigger.

Steps 2 and 6-9 are held by ``tests/test_vocabulary_reach.py``, which
enumerates from the kernel's side: every closed vocabulary the package
declares says which readers it reaches, and a new one fails there until
it does. That is the difference between a surface being pinned and every
surface being pinned — the two look the same in the source.
