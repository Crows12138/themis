"""Verifier layer (slice V0+).

Independent of ``themis.runtime.*``. Given a derivation and a
verification context (graph + query + optional Theta), re-runs each
named rule and confirms the derivation legitimately leads from the
premises to the claimed result.

Public surface (re-exports from sub-modules):

- Per-query-kind verifiers: ``verify_cause`` / ``verify_assoc`` /
  ``verify_identify`` / ``verify_effect_structural`` /
  ``verify_numeric`` / ``verify_numeric_estimate`` /
  ``verify_counterfactual`` / ``verify_causation`` (PN/PS/PNS,
  Tian-Pearl 2000 — independently re-derives the observational joint
  from theta and the Tian-Pearl bounds/points) /
  ``verify_scm_counterfactual`` (linear-SCM point, Pearl Primer §4.2 —
  independently re-runs abduction-action-prediction from the edge
  coefficients + the unit's observations) /
  ``verify_scm_counterfactual_numeric`` (the DATA end: re-solves each
  node's OLS from the recorded moment matrices and re-runs abduction-
  action-prediction from the fitted slopes + the unit). Both take the
  ``extensions.scm_counterfactual`` block and hold it to the world they
  just re-derived: a derivation step's output has room for the point, and
  the abducted noise and the rest of the counterfactual assignment reach a
  reader through that block and nothing else. The re-run already had them
  — asking for what it worked out is not a second implementation, and the
  sibling block has been held this way since ``extensions.causation``
  carried PS/PNS a reader could see nowhere else /
  ``verify_counterfactual_conjunction`` (general counterfactual
  identification, Shpitser-Pearl ID* R-336 — pins the id_star terminal
  rule and runs an independent Monte-Carlo semantic probe: samples SCMs
  consistent with the ADMG, computes the true P(γ) by counterfactual MC
  over a shared exogenous background, and rejects a formula that computes
  the wrong number) /
  ``verify_ovb_sensitivity`` (Cinelli-Hazlett OVB sensitivity — a second
  independent transcription of the robustness-value / partial-R² / bound
  closed forms, recomputed from the recorded t-value + dof + benchmark
  partial R²s) /
  ``verify_e_value`` (VanderWeele-Ding E-value sensitivity — the
  risk-ratio-scale sibling of the OVB block; a second independent
  transcription of E = RR + √(RR·(RR−1)), re-deriving the risk ratio and
  both E-values from the audited headline ATE + the recorded conversion
  input (baseline rate / outcome SD), so a tampered E-value is rejected) /
  ``verify_dose_response_curve`` (dose-response curve construction
  invariants — the curve values come from a black-box EconML fit and can't
  be re-derived, but the array (the answer) gets a semantic audit the
  metadata-only path skips: one point per sampling point with matching x,
  reference-point effect 0, and every point inside its own interval; catches
  a corrupted / reordered curve or a point escaping its CI) /
  ``verify_selection_recovery`` (Bareinboim-Pearl recoverability from
  selection bias — re-derives the selection-backdoor conditions and the
  Theorem-3.5 recovery formula against the graph, validates the returned
  adjustment-set witness, and re-searches to confirm a negative verdict) /
  ``verify_missing_data_recovery`` (Mohan-Pearl-Tian recoverability from
  missing data — rebuilds the m-graph from the declared indicators,
  reclassifies MCAR/MAR/MNAR, and re-searches the ordered factorization to
  re-derive the recoverability verdict + recovery formula) /
  ``verify_recovery_verdicts_are_owed`` (whether those two blocks are
  there at all. Each is audited where it is, and removed, every one on
  the corpus passed; a selection verdict added where the sample is
  restricted on no common effect passed too. Which answers owe one is
  read off the program, the question and the ground graph, both ways) /
  ``verify_transport_sources`` (Bareinboim-Pearl transport across several
  declared source domains — re-derives the agreement verdict over the
  per-source numbers the block records, so a reported number that some
  transporting domain contradicts, and a withheld one no domain
  contradicts, are both caught) /
  ``verify_acr_decomposition`` (an IV number over an ordered dose — the
  Angrist-Imbens margin table recomputed from the per-instrument-level
  counts and sums alone, so a weight that disagrees with the data, a
  weight vector that fails to sum to one, and a suppressed monotonicity
  refutation are each rejected) /
  ``verify_identification_pattern`` (the graph-level pattern the reader is
  told the answer came from — back door with its adjustment set, front
  door with its mediators and the covariates it needs held, an instrument
  with the set it is valid given, or the ID algorithm's general solution.
  The named sets are re-derived to satisfy the criterion the pattern
  names, by edge deletion plus the verifier's own m-separation rather than
  the producer's path enumeration; and the general solution is held to
  being general, so a back door or a front door that was there to be named
  and was not is rejected) /
  ``verify_the_conditioning_a_question_asks_is_named`` (the other half of
  that block, which the criterion cannot supply: a question conditioning on
  Z is about some of the people, and a sentence naming the criterion and
  not the conditioning is the sentence for the question about everybody.
  The variables are owed here; the values beside them are the estimate's to
  show) /
  ``verify_feedback_loop`` (the reason a reader is given for an answer the
  DAG did not compute — the loop is re-derived from the PROGRAM, since a
  block citing one nobody declared would license the swap of a correct
  adjustment answer for an instrument resting on linearity; the query's
  two ends, the loop reaching them, and the Haavelmo reduction are
  re-derived beside it) /
  ``verify_loop_withdrawal_is_owed`` (whether that block is there at all.
  An effect answer computed from the DAG, beside a program declaring a loop
  its estimand reaches, passed every door; which answers owe the block is
  read off the program, the question and the ground graph) /
  ``verify_a_given_holding_an_end_is_refused`` (a question conditioning on
  its own treatment or outcome is refused before any route, and answered
  with that refusal alone; a route's answer to one passed every door) /
  ``verify_a_decomposition_within_a_moved_stratum_is_refused`` (a
  decomposition asked within a stratum the treatment moves is answered
  with that refusal alone; with its item removed it passed every door) /
  ``verify_joint_identification`` (the same sentence for a do() over a
  treatment SET, in a block whose pattern vocabulary the contract declares
  disjoint from the scalar one — which is why one verifier dispatching on
  that key could not reach it. The criterion is the treatment-set back
  door and not a conjunction of scalar ones: edges are cut out of every
  treatment at once, since a path from one treatment through another is
  inside the intervention. The general solution is held to being general
  here too) /
  ``verify_proximal_estimand`` (the proximal descriptor, held to the
  question it describes. The criterion rule asks Miao's model (f) of the
  graph, in its own transcription, and takes the roles from the QUERY, so
  identifiability was
  established for the question asked while the block a reader reads could
  name a different one — the two proxy roles exchanged, or the unobserved
  confounder named as an observed variable. Both proxy roles compare as
  sets: which shadow of one confounder is written first is not a fact) /
  ``verify_longitudinal_identification`` (the flag that decides whether a
  time-varying strategy gets a number at all. The numeric verifier beside
  it reads ``numeric_estimate``, so it audits the numbers this flag
  licensed and never the flag. Two things are checked and differ in kind:
  that the block describes the strategy the PROGRAM declared, order
  included, since the history is built by walking it; and the criterion
  itself, per time — the ordinary back door asked K times of a growing
  measured history) /
  ``verify_mediation_decomposition`` (which decomposition a reader is
  being given and what has to hold for it — one function for both the
  single-mediator block and the joint one, because Pearl's 2001 conditions
  over a mediator SET reduce to his own at a singleton and a second
  transcription would be one more place for the two to disagree. A claim
  of identifiability names the W that carries it and is checked in full; a
  claim of NON-identifiability names no witness and is the claim that
  withholds an answer, so it is held to being negative by search.
  ``failed_condition`` is checked for agreement rather than re-derived:
  which condition is named is the label of the candidate that got
  furthest along a fixed order, which is a property of that search and not
  of the graph) /
  ``verify_mediation_decomposition_numeric`` (what was then computed from
  that decomposition, which is the same block's other half and needs
  theta: the four potential outcomes and the ten numbers read off them,
  the controlled direct effect at every reference point, and — for the
  arms that produced no number at all — the account of why, since which
  probability theta lacked, which reference point the walk stopped at and
  which species of shortfall it was are facts about this graph and this
  theta. Shares its re-derivation with the evaluation step's own rule,
  because the block reaches a reader in two copies, and most answers
  carrying one of these blocks carry no evaluation step at all) /
  ``verify_vector_iv_identification`` (the variables the Anderson-Rubin
  region was built from. The region verifier re-derives exact arithmetic
  on recorded second moments, which arrive already built from whichever
  columns were chosen, so it can confirm every number of a region computed
  on the wrong ones. Validity is read on the treatment SET — every
  treatment's outgoing edges cut at once, so an instrument reaching the
  outcome through ANOTHER treatment is admitted here and rejected by the
  scalar test — and the per-instrument relevance, reported rather than
  required, is re-derived in the original graph) /
  ``verify_iv_surfaces`` (the same claim reaches a reader from two blocks
  — the human surface and the one the IV report routes — so each is
  re-derived on its own fields and the two are then held equal. Passing
  the criterion is not agreeing: a graph with two valid instruments lets
  both blocks pass alone while a reader is shown one and the number came
  from the other)
- Numeric-end verifiers (data-based overlays that re-derive the reported
  numbers from the recorded sufficient statistics, not the raw data):
  ``verify_proximal_effect`` / ``verify_proximal_numeric`` (Miao-2018
  proximal do-effect), ``verify_causation_numeric`` (PN/PS/PNS plug-in),
  ``verify_counterfactual_cell_numeric`` (the single binary counterfactual
  cell re-solved from the reported empirical joint + interventional risk),
  ``verify_ctf_conjunction_numeric`` (ID*/IDC* counterfactual conjunction),
  ``verify_mediation_numeric`` (the numbers a mediation analysis attaches
  wherever they ride — the decomposition, the two four-way splits, the
  controlled-direct-effect curve: the VanderWeele ratio-scale four-way split
  re-derived from the recorded logistic coefficients, plus
  construction-identity checks on the difference-scale four-way and the Imai
  NDE/NIE decomposition whose simulation-based values aren't re-derivable),
  ``verify_longitudinal_numeric`` (the time-varying strategy contrast riding
  on a g-formula / sequential-back-door identification: the IPW-MSM contrast
  re-derived from the recorded marginal-structural-model coefficients, plus
  construction-identity checks on the black-box g-formula Monte-Carlo means
  that aren't re-derivable),
  ``verify_iv_overid_numeric`` (over-identified 2SLS: the 2SLS point AND the
  Sargan over-identification test — J and its p-value — re-derived by an
  independent transcription of the closed forms from the recorded residualised
  moment matrices Z'Z / Z'x / Z'y / xx / xy / yy; rejects a tampered point, a
  forged Sargan statistic, or a corrupted moment. Its derivation terminal
  ``numeric_iv_overid_estimate`` does only metadata + structural licensing
  because the moment matrices don't fit derivation-input serialization),
  ``verify_vector_iv_region`` (the Anderson-Rubin confidence REGION over a
  treatment vector: the inverted quadratic A/B/C, the region's shape, its
  centre, the 2SLS point and every coordinate projection re-derived from the
  recorded second moments. The shape is re-classified in the EIGENBASIS of A
  rather than by the producer's case split, and each finite projection
  endpoint is confirmed twice more — against the quadratic itself at the
  completion that minimises it, and, where the region is an ellipsoid,
  against the support function μ_j ± sqrt(r·(A⁻¹)_jj). Holds the theorem
  tying the two shape vocabularies in both directions, so a tampered
  ``shape`` and a tampered ``projections`` each fail on the other. Its
  derivation terminal ``numeric_anderson_rubin_region`` does only metadata +
  structural licensing because the moment matrices don't fit
  derivation-input serialization),
  ``verify_frontdoor_empirical_numeric`` (a front door whose mediator
  conditional came from the arms' own rows: the point is re-derived from the
  two standardized arms, and on a linear outcome model from the recorded
  coefficients and mediator shift — the product rule, with both halves of the
  product carried; on a logit one standardization is not collapsible and the
  difference identity is the honest ceiling),
  ``verify_treatment_box`` (a joint intervention on a treatment SET, by
  whichever road: both reported numbers are finite differences over the
  treatment box, and the box is recorded, so the contrast is recomputed as
  all-hi minus all-lo and the K-way interaction as the alternating sum over
  all 2^K corner risks — catching a number that is internally consistent but
  does not follow from the corners the same result reports. Asked of any
  answer carrying a box rather than of a named method, since two estimators
  emit the same block. Holds the box to what it claims: distinct cells
  naming every treatment, probabilities where the outcome is binary and
  means where it is not, and completeness exactly when an interaction is
  reported),
  ``verify_measurement_correction_numeric`` (frontier E — the de-attenuated
  effect on a misclassified discrete outcome: the corrected point, the naive
  (attenuated) point, and det(M) re-derived by an independent transcription of
  the per-stratum confusion-matrix inversion p_true=M⁻¹p_obs from the recorded
  matrix + value-count vectors; rejects a tampered point, a non-stochastic or
  det-inconsistent matrix, a dropped stratum, or a missing arm. Its derivation
  terminal ``numeric_measurement_correction_estimate`` does only metadata +
  structural licensing because the matrix + count vectors don't fit
  derivation-input serialization),
  ``verify_exposure_measurement_correction_numeric`` (frontier E, exposure side
  — the de-attenuated effect of a misclassified binary EXPOSURE: the corrected
  point, the naive (attenuated) point, and det(M) re-derived by an independent
  transcription of the matrix method p_true(X*,Y|z)=M⁻¹p_obs(X,Y|z) applied on
  the exposure margin, from the recorded matrix + per-stratum 2×k joint tables;
  rejects a tampered point, a non-stochastic or det-inconsistent matrix, a
  dropped stratum, an empty observed arm, or a degenerate recovered exposure
  marginal. Shares the ``numeric_measurement_correction_estimate`` terminal),
  ``verify_combined_measurement_correction_numeric`` (frontier E, both channels
  — the doubly corrected effect when the exposure AND the outcome are
  misclassified: the corrected point, the naive point and each channel's det
  re-derived by an independent transcription of the two-sided inversion
  p_true(z)=M_x⁻¹p_obs(z)(M_y⁻¹)ᵀ from the two recorded matrices + the same
  per-stratum 2×k joint tables. Adds one check the single-channel verifiers
  cannot make — the recorded det of the composed map must equal
  det(M_x)^k·det(M_y)², which catches a joint determinant carried over from a
  different pair of matrices — and rejects any claim of differential
  misclassification, which the two-sided factorisation does not license. Shares
  the same terminal),
  ``verify_regression_calibration_numeric`` (continuous mismeasurement — the
  de-attenuated slope of a continuously-mismeasured EXPOSURE by regression
  calibration: the corrected point, the naive (attenuated) slope, and the
  reliability λ=1−σ²_u/Var(W|Z) re-derived by an independent transcription of the
  moment correction β=(Σ_WZ−E)⁻¹Cov((W,Z),Y) from the recorded design covariance
  matrix + σ²_u; rejects a forged point / naive / reliability, a non-symmetric
  covariance, a degenerate reliability (σ²_u≥Var(W|Z)) that shipped a point, or a
  slope vector inconsistent with the covariance. Shares the
  ``numeric_measurement_correction_estimate`` terminal),
  ``verify_simex_numeric`` (the same design on a declared NONLINEAR outcome
  model, where that moment identity does not hold — simulation-extrapolation.
  Only the first of its two stages is random, and its output is the second's
  sufficient statistic, so the extrapolant's coefficients, the point at λ=−1,
  τ(−1) and the interval are all re-derived from the recorded simulation
  ladder alone, by normal equations rather than the producer's ``lstsq``, and
  without simulating anything. What cannot be re-derived is said rather than
  implied: the ladder is a seeded Monte Carlo. What CAN still be checked
  about it is — the λ=0 rung is not a simulation at all and must equal the
  reported naive point with zero replicate variance, the grid must start at
  zero and climb, and it must be long enough that the declared family is
  fitting rather than interpolating. Rejects a forged point / coefficient /
  variance, an interval that is not the recorded variance read at the
  recorded level, and a withheld interval whose stated reason is not true of
  the record. Shares the same terminal),
  ``verify_differential_error_numeric`` (the same design again with the
  NON-DIFFERENTIAL premise withdrawn — an error carrying a component that
  tracks the outcome. The correction moves the answer in two places where the
  classical one moves it in one: the observed covariance is un-inflated by
  δ·Var(Y|Z) before the variance is un-inflated by σ²_u, so a producer that
  applied only the second would return a number every reliability ratio a
  reader checks by hand agrees with, and wrong. Both steps are re-derived
  from the recorded design covariance, Cov(D,Y), Var(Y), σ²_u and δ — by
  inverting the joint precision matrix rather than by the producer's Schur
  complements — and the two declarations are re-tested against each other and
  against the sample, so a block that shipped through a guard it should have
  been refused by is rejected here rather than believed),
  ``verify_differential_outcome_error_numeric`` (the same premise withdrawn on
  the OTHER channel — a mismeasured outcome whose error tracks the exposure,
  which an unblinded assessor is the ordinary source of. There the whole
  correction is one subtraction, βx = naive − δ, and that is why it is audited
  rather than trusted: a producer that skipped it ships the ordinary back-door
  slope, and every other number on the block still agrees with it, because the
  block would then be describing a real fit of a real model — just not of the
  estimand the answer claims. So the naive slope is re-derived from the
  moments first and the point is held exactly δ below it, a claim about the
  distance rather than about either end. The variance split is checked for the
  reason it exists: σ²_v never reaches the point, so a wrong split reaches the
  reader as a precision claim with nothing else standing behind it),
  ``verify_selection_recovery_numeric`` (§S9.1 numeric end — the ATE recovered
  from selection bias by the Bareinboim-Pearl selection-backdoor formula
  (Theorem 3.5): re-runs the sum μ(x)=Σ_{z⁺}[Σ_{z⁻} E_biased[Y|x,z,S]·P_ref(z⁻|x,z⁺)]·P_ref(z⁺)
  from the recorded per-stratum biased counts + external unbiased weight
  tables, and checks the two arms, the point, and the weight-table
  normalisation; rejects a forged point or a tampered stratum),
  ``verify_missing_data_numeric`` (§S9.2 numeric end — the back-door ATE
  recovered from data that itself has missing values by the Mohan-Pearl-Tian
  ordered factorization: re-runs the g-formula Σ_z (E[Y|1,z]−E[Y|0,z])·P(z)
  from the recorded per-stratum {n, y_sum} conditionals + {z, count} marginal
  tables (the recovered estimate and, when present, the naive listwise foil),
  and checks the reported point, the marginal normalisation, and that no
  contributing stratum was dropped; rejects a forged point or a tampered
  stratum),
  ``verify_assumption_ledger`` (the disclosure surface the report assembler and
  the rendering bridge lead with: re-derives what the ledger owes from the four
  channels that feed it — the estimator's own ``numeric_estimate.assumptions``,
  load-bearing proposal edges, LLM theta priors, audited mechanisms — and
  rejects under-disclosure, a fabricated estimator entry, a line handed to a
  caller who supplied nothing, a line naming no assumption that is not word
  for word the line its gap or supplied prior owes, an unsorted ledger, a
  summary whose counts do not match, or an entry whose severity contradicts
  its layer — the layer says
  which part of the answer stops being true and the severity grades how badly
  that kills it, so the second follows from the first and is re-derived here
  rather than believed),
  ``verify_cluster_inference`` (the unit of independence: holds the run-level
  ``estimation_context.cluster`` against what the estimator declares it did
  with that column, so an interval computed under a clustered run cannot stay
  silent about it — silence reads as i.i.d. inference the run gave no basis
  for — and a dispatch-written ``bootstrap`` block cannot claim
  cluster-robustness the estimator never corroborated, name a different column
  than the run resolved, or appear with no cluster column resolved at all),
  ``verify_bootstrap_records`` (the other half of that block, and every other
  copy of it the envelope carries — the margin table's own loop, the ratio
  split's, a bounds row's outer band: how many replicates were asked for, how
  many a refit could use, and what took the rest, filed by refusal species.
  Rerunning a bootstrap needs the data, so what is checkable is the record,
  and the record's failure is one-sided — losses nobody accounted for look
  exactly like no losses. Rejects a total that does not add up, a reason
  outside the closed vocabulary, an interval resting on fewer draws than a
  quantile can be taken over, and the counterfactual cell's refuted share
  where it disagrees with the counts it is derived from),
  ``verify_outcome_error`` (the one block that changes no number: a declared
  classical error on a continuous outcome costs precision but not bias, so the
  audit is of the split it reports — every scalar re-derived from the recorded
  Σ_D, Cov(D,Y), Var(Y) and σ²_v — of whether that split was taken on the design
  the estimate actually fitted, and of whether its premises reach the
  estimate's declared assumptions, the non-differential-error premise being the
  entire reason no correction was applied),
  ``verify_berkson_error`` (the exposure channel's other structure and the
  package's strongest silence: under ``X* = W + U`` the back-door slope is the
  causal one already, so the block rides beside a number nobody de-attenuated
  — and the same declared variance read as classical would have moved it by
  half. The price is re-derived scalar by scalar from the recorded moments,
  the coefficient it is scaled by is held to the coefficient the answer
  reports, and the structure itself — which no arithmetic can witness — is
  held to reaching the assumption ledger),
  ``verify_survival_curve`` (a censored outcome, where the block is not a
  disclosure beside the answer but the answer's own working: the per-cell risk
  tables are a sufficient statistic, so the Kaplan-Meier curve, the area under
  it to the horizon and Greenwood's variance carried through that integral are
  all recomputed and held to what was recorded, as is the g-formula
  standardisation over them. The check that makes the rest worth anything is
  the table's own consistency — a forged table that dropped its censored units
  recomputes to a curve that is internally perfect and too optimistic
  everywhere — and independent censoring, which no arithmetic witnesses, is
  held to reaching the ledger)
- A copy of the run's own record: ``verify_numeric_display_agrees`` (an answer
  from data reaches its reader twice — the derivation's terminal step, which
  every rule here re-derives from, and ``numeric_estimate``, which the report
  and the browser read. Of forty-two leaves on a stratified-Wald answer,
  thirty-eight could be edited and still pass. This asks the one question
  needing no knowledge of any estimator: a name appearing on both sides names
  the same thing — the confidence level, the sample size, the digest, the
  method, the endpoints, and the variables, whose two spellings are
  transcribed rather than skipped, since a shape mismatch is how a relabelled
  outcome would pass. The nested views it does not reach are named in the
  module's own docstring)
- How big the table was, asked wherever the envelope says so:
  ``verify_one_row_count`` (the digest rules beside it say WHICH table an
  answer stands on; this says how many rows it had. The run records that once
  before any estimator runs, and the point estimate, each bounds row, the
  outcome-error block and every derivation step's inputs then carry their own
  copy. Two rules already stated the relation, each for the one block its
  author was walking, and neither could see ``estimation_context`` — so the
  run's own record, the number a reader is likeliest to quote a precision
  off, was the copy nothing compared to anything. Asked of the name the
  contract gives the whole, so that the parts spelled one level down —
  ``strata[].n``, a channel's treated and control halves — are never mistaken
  for it)
- Copies of the caller's own words: ``verify_llm_proposed_review`` (every edge
  whose annotation names a language model and every prior whose provenance is
  ``llm_prior``, collected again from the program JSON and compared with the
  block a reader accepts or rejects the graph on — both directions, because an
  LLM-proposed edge that never reaches that surface reads as one a person
  drew) and ``verify_ambiguity_copy`` (the program's declared ambiguities
  filtered to this query, which is the whole of what the producer does, so the
  copy is checked entire; the gap report READS this block, and an entry the
  program never declared suppresses the measurement-error concern — one
  invented line deletes a warning and supplies the excuse for its absence)
- WHICH question an answer says it answers, and what it says is still
  available: ``verify_answer_names_its_kind`` and ``verify_answer_tier``
  (the two words a run uses about itself, above everything else a reader
  sees. Both went unheld for one reason: every rule that could catch a lie
  about them is selected BY them — ``verify`` routes on ``query_kind`` and
  on ``status``, and every rule touching the gap report reads the gaps
  without reading the word those gaps add up to. A field that decides
  which checks run is a premise of the audit until somebody holds it. The
  kind is held to the program, which an answer may not edit; the tier is
  held only where the word is true whichever pass wrote it, because it has
  two authors and recomputing the first refuses honest answers the second
  had the last word on)
- The word an answer leads with: ``verify_answer_status`` (the third of
  that trio, named there and left. Measured before it was written: of 1458
  relabellings of the corpus's own answers, 673 were accepted at both
  doors — a gap diagnosis could call itself numerically solved. What holds
  it is on the envelope beside it, and what each word CLAIMS is now
  declared beside the word rather than nowhere: ``ResultStatus`` was seven
  bare strings where every other name in this package carries its meaning,
  which is why nothing could hold it. The two halves have two authors —
  the contract says what the word claims, this says what the blocks show —
  and the envelope is read at two strictnesses, because a promise read too
  narrowly and a denial read too widely both refuse an honest answer, so
  each is asked the reading that errs toward accepting)
- The same word against the question it answers:
  ``verify_answer_status_fits_its_question`` (what the envelope shows
  cannot separate two words that both say a quantity arrived, because they
  show the same thing; the question can. An effect query asks for an
  interventional contrast, and a counterfactual point is not a sharper
  answer to it but an answer to something else. Which words a question's
  ANSWER may lead with is declared beside the question, and the words a
  REFUSAL leaves are open to every question and declared once on
  ``refusals.Kind.outcome`` — a refusal is about what this system could not
  do, not about what was asked. The roster is collected from every result
  the suite causes this system to build rather than read off the
  producers, because a roster one entry short refuses an honest answer)
- What an answer calls the steps of its chain:
  ``verify_the_chain_names_its_steps`` (a name exists to be pointed at, and
  the reader of an answer holds no second record of what its producer liked
  to call things — so the slot took anything, and forging the first step's
  name left 81 of 178 stored answers accepted at every door. What a reader
  CAN recompute is where a step sits, so that is the name: the i-th step is
  ``s{i+1}``, written by the encoder and recomputed here, with a producer's
  own label stopping at the serialization boundary)
- Every sentence an envelope carries, against the sentence it names:
  ``verify_statements_carry_their_facts`` (a sentence travels as a token
  and the facts for that token's holes, and nothing had asked whether the
  two agree. Neither direction shows as a failure, because the assembler
  is built not to fail: a hole with no fact is rendered as a stated
  absence, and a fact with no hole is dropped in silence. So a description
  could be relabelled and keep the facts it had, and a reader would be
  told an unnameable edge was learned by an unnameable algorithm on a gap
  about something else. The word tables are read rather than restated —
  what a second author is worth restating is a producer's decision, and a
  sentence's holes are the sentence)
- And the words on the envelope a record other than the sentence decides:
  ``verify_statements_repeat_what_decided_them`` (a question spells which
  way a monotonicity assumption runs, and that direction decides which side
  of an interval tightens; the derivation says which estimator ran, and
  that decides whether an instrument's number is a LATE or one equation's
  coefficient. Each word is written in several blocks, and each was held
  at most where it was first computed — the direction by the bounds
  verifier for its own row, the premise by a check holding two of its
  copies to each other — so the gap telling a reader so could name the
  other word. One table of deciding records, one walk)
- The question an answer says it answers: ``verify_answer_names_its_question``
  (the treatment, outcome, mediator and proxies ``numeric_estimate`` opens
  with, read again off the query. No derivation step records any of them, so
  nothing had ever re-derived them; an edited name leaves every number on the
  envelope intact and changes only which question they are answers to. Read
  per query kind, because a causation query names a cause where an effect
  query names an intervention, and a reading applied to the wrong kind would
  hold an answer to the wrong question)
- The specification a time-varying answer was fitted from:
  ``verify_longitudinal_option_copy`` (the strategies contrasted, the
  simulation budget, whether the IP weights are stabilized — the caller's
  own words in ``options.longitudinal``, repeated beside the numbers and
  read by the page a reader is shown. The rule auditing that block is
  handed the estimate alone, so it holds only what the block recomputes
  from its own figures; these are held against the program where it
  declares a value and against the estimator's default where it does not,
  because the block shows one either way)
- Figures the envelope worked out from its own figures:
  ``verify_envelope_arithmetic`` (the interval's half width, its width as a
  share of the effect, the sample that would halve it, a mediation total
  against its two parts, and VanderWeele's four-way split against the
  identity the block itself cites. No independence question arises — there is
  no second implementation, only an identity that holds or does not — and
  every relation was measured against every answer shape before being
  asserted, since a relation nobody measured is a false refusal waiting for
  the shape that disobeys it. Asked wherever a budget appears on the
  envelope, the reader's copy of a block included, and not only under
  ``numeric_estimate``; the separate question of why a budget is ABSENT is
  put only across the subtree whose producer promises one, because that
  question reads a promise rather than the envelope)
- The level every interval on the envelope is stated at:
  ``verify_confidence_level`` (asked wherever the word appears, and held to
  the constant this system draws rather than to a second copy of itself.
  Nothing recomputes with it on most of the envelope — a percentile
  bootstrap keeps no multiplier to invert — and a caller cannot ask for
  another one, so the constant restated is the only honest copy. Before it,
  thirty-eight of forty-four answer shapes accepted every level on the
  envelope being rewritten at once, and thirty-one accepted one block
  claiming a different level from its neighbours)
- What a gap says, against the problem it says it about:
  ``verify_gap_names`` (a gap carries a ``need`` token and a ``said``
  mapping, and the sentence a reader gets is the template for that token
  with those facts substituted in — so ``said`` is the sentence's
  contents, not metadata beside it. The three audits above it read the
  report's skeleton and none descends into a gap, so all 462 ``said``
  string leaves on the answer shapes could be rewritten and the door said
  yes. The walk is depth-blind because depth was the defect)
- And what a gap QUOTES rather than names: ``verify_gap_quotes`` (the
  rule above asks whether a word is one of the problem's variables, and
  the roster it uses sorted every other key by WHAT KIND of thing fills
  it — a vocabulary member, a number, an expression. That is an answer to
  why a key fails name membership, and it was standing in for an answer
  to a different question: whether anything at all could hold the value.
  Three keys separate them. None of the three is a variable, so the
  classification was right, and each has an exact second record on the
  same envelope — the methods the answer ran, the keys
  ``missing_information`` files a shortfall under, the assumptions an
  interval and the ledger record. No table is restated and no membership
  is tested; these are equalities between two copies of one fact, and the
  copy the reader is shown was the one nothing compared. What stays out
  is measured rather than deferred: an honest value that lives nowhere
  else — a rendered number, a coined label — would be refused by a
  generic demand that every quoted fact be findable, which is why the
  roster is per key. Six more keys joined once the roster stopped being
  keyed on a slot's NAME: a slot's meaning is its sentence's, and
  ``target`` is a population where an answer is transported and a
  variable in the three statements about a curve and a collider, so one
  answer per name was right about one of those and silent on the rest.
  With the statement carried, the methods already in hand, the fields a
  declaration has, the domains the program declares and the uncertainties
  the caller flagged are all held. Both rosters are also bound at import
  to the slots a statement can declare, rather than to the keys the
  answer shapes happen to produce — eighteen slots this build can write
  were in neither, and a slot in neither is asked by no rule here. A
  NAME can have a second record too: where a statement writes a role of
  the question — the intervention, the treatment, the target, the
  outcome — the question is that record, and a gap rewriting one real
  variable into another, which the name rule has to pass, is held to it)
- How much data a reader is told to go and collect, and from where:
  ``verify_required_data`` (a blocking gap ends in an instruction somebody
  runs a trial on — 229 of its leaves could be rewritten and both doors
  said yes, every minimum sample size among them. The number is a copy of
  nothing, which is why nothing on the envelope held it: it is a power
  calculation. What makes it checkable is that the calculation's inputs
  travel beside it, since the number arrives with a statement of what it
  buys and that statement's facts are the terms it was computed from. So
  the authority is the arithmetic, re-run from a second transcription of
  the textbook closed forms — the producer lives in ``themis.output``,
  which no verifier may reach, and re-running the code that made a number
  proves only that it agrees with itself. Naming a different design is
  refused too, since its terms then fit no formula. Which designs exist is
  the output layer's roster, so a token this build has no arithmetic for
  is passed over; a test holds the table to that roster instead. The rest
  of the block is the problem's own words, asked of the problem: the
  variables to measure and the confounders to condition on are predicates
  it declares, and a population named is one it declares as a source or
  target domain. ``data_type`` stays open and says so — which shape of
  data closes a gap is chosen where the gap is raised, and a table from
  gap kinds to data types would restate a producer's judgement)
- What a column was DECLARED to be, against the declaration:
  ``verify_declared_types`` (the pre-flight diagnostic re-derives its whole
  verdict FROM the recorded declared scale and declared domain, so those two
  are premises of that audit rather than results of it — a verdict re-derived
  from a rewritten declaration agrees with the rewritten declaration. 219 of
  the block's leaves could be rewritten and the rule said yes, the declaration
  being 105 of them. The declaration is the PROGRAM's, and asked there it stops
  being a premise: the domain word for word, and the scale against what the
  declaration itself resolves to, which is a second transcription of the rule
  that resolves it. Beside it, in the audit that has only the envelope: the
  block's sentence about a column against the statement it is a rendering OF,
  which its producer names in a comment and nothing compared; a cardinality
  against the rows the run records; and the recorded value set held to being a
  set, sorted, of the type its own dtype family reads out as. ``dtype_kind``
  stays open and says so — a program declares what a variable MEANS, never how
  it was stored — and so does a value swapped for another of its own type)
- The block that stands where a number would have been:
  ``verify_refusal_block`` (an answer that produced no number says why in
  one shape, assembled by one function, and every ``needs_investigation``
  answer IS that shape — 273 of its leaves could be rewritten and both
  doors said yes. The rules beside it read it without holding it: the
  statement carrier asks whether a refusal's SLOTS match its species'
  holes, and the status rules read the outcome off the kind rather than
  compare it. What makes the block holdable is that its producer already
  declares every relation in it — the kind is stamped from the registry,
  the recorded facts and the sentence's facts are two halves of one
  mapping, and each fact is written twice, as what the envelope can hold
  and as what a sentence carries. Order is taken from the sentence and
  every value from the record, because a JSON object's key order is not a
  claim anybody makes. The two silences are the producers' own and point
  opposite ways: an unregistered species is accepted, since refusing it
  would reject somebody else's honest refusal, and an unregistered route
  is refused, since a route carries the sentence itself. ``estimator``
  stays open and measured — no second record on 31 of 36, and no roster
  to be a member of, since the contract types it a string where it gives
  the species a full enum)
- What a bounds row TELLS a reader, against what it was computed from:
  ``verify_bounds_account`` (``bounds_rules`` re-runs the Balke-Pearl LP
  and re-derives every expression — it verifies the INTERVAL and never
  the account of it, while a reader receives the account: what would
  narrow this, and where the width came from. It restates no table: a
  rendered quantity may use only names the program declares and words
  already in this row's own re-derived formulas, and every count is the
  number of levels the program declares. Asked before the method
  dispatch, since the two lists are the same on all three methods; the
  monotonicity note's words are passed the side the MTR rule has just
  derived, never a second derivation of it)
- The list a reader is told to go and fill, read rather than counted:
  ``verify_investigation_items`` (the second turn takes an item's
  ``skeleton`` verbatim as the patch a reader submits, so a rewritten
  predicate is a reader filling in a different variable. The two rules
  that touch the block use it as a DENOMINATOR — one resolves gap
  provenance against its targets, the other demands each item be cited —
  and a denominator can be shortened: the framing group is exempt by
  name, thirty-seven of forty-three requests, and the rest was reachable
  by emptying the target. It restates no table; every question is whether
  two records of one fact agree, and the sharpest of them is asked of the
  program, which is not the answer's to write)
- And WHICH of those names a gap is about: ``verify_gap_subjects``
  (the rule above asks whether a gap's words are words this problem is
  written in, and a forgery swapping one real variable for another
  passes it. A gap's own provenance says which one it is about and
  T10-1 already holds that ref, so the two were verified separately
  and never joined; the fields it says are unset are asked of the
  program, which is not the answer's to arrange, and so is every other
  fact a statement gives about the variable it names, in either half)
- And whether the place a gap cites is a place the problem HAS:
  ``verify_gap_program_sites`` (T10-1 follows a gap's envelope refs and
  refuses one that lands on nothing; a ``program_site`` ref makes the same
  claim about the other document and nothing followed it, because the
  audit that runs T10-1 is result-only by contract and the program is not
  there to look in. Seven spellings, three questions — an edge and the
  annotation it carries, a variable and a field of its declaration, a
  place under the program's extensions — plus two that name no site but a
  shape, one saying the problem declares an unmeasured confounder and one
  saying it declares none, which are the same count read both ways. An
  unrecognised spelling is refused, or the hole comes back one spelling
  at a time)
- And whether what a gap says about the edge it cites is what that edge
  says: ``verify_gap_edge_statements`` (the site above is named after
  ``annotations.source`` and only that field's presence was asked; a
  proposal-edge gap's statements — the edge in its direction, whose
  proposal, which algorithm, the share of resamples it survived — are
  that annotation read aloud, and a gap rewritten together with the
  ledger line that copies it had passed every door)
- And whether the edges such gaps disclose, with what each says, are the
  proposed edges the answer rests on, with what their statements say, on
  the ground graph it was reached on:
  ``verify_proposed_edges_are_disclosed`` (which edges had one was the
  report author's alone; removed with its ledger copy a gap passed every
  door 21 times of 21, and added for an edge that owes none, 18 of 18 —
  twelve of those an evidence-sourced edge told as a language model's)
- And whether the caveats that say a sample is restricted on a collider
  are the ones the answer owes, on that graph with its bidirected edges:
  ``verify_collider_caveats_are_owed`` (which answers carried one was the
  report author's alone; each of the corpus's 7, removed, passed every
  door, and one added for an atom that is no collider passed 5 times of 5)
- The thing a disclosed mechanism was fitted for, against the question:
  ``verify_mechanism_target`` (a mechanism block says which ``form`` a fit
  took and which ``target`` it took that shape FOR; the method and the
  named assumptions are held against the estimate, the target was not,
  and all thirty-one on the answer shapes could be rewritten. It is a
  module of its own because the authority is the question, and every
  other mechanism check is reached through a result-only door where the
  question does not exist — the stand-in reachable from there is the
  answer's own copy of its outcome, which was tried and blamed the field)
- The estimand a reader is shown, against the problem it claims to be for:
  ``verify_identification_formula`` (``result["formula"]`` is what the
  report prints and the browser shows, and nothing read it: on all
  twenty-three answers that carry one it could be deleted outright and the
  door said yes. Three questions with different prerequisites — whether
  the formula is ABOUT this problem needs only the declared names, so all
  twenty-three are asked; whether it COMPUTES what was asked needs an
  (X, Y) pair, which a counterfactual conjunction has none of, so
  twenty-two are; and whether it IS the question, asked where there is no
  X to compute against. A probability question identifies nothing, so its
  estimand is the conditional it names and the two are compared as
  quantities — the conditions as a multiset, because writing them in
  another order is a spelling rather than a forgery. That comparison
  already existed in the chain half, holding a ``formula_evaluation``
  step to the query's own reference verbatim, so what was held was the
  chain's record and not the one a reader is shown. It sits outside the
  query-kind dispatch because the
  formula is a fact about the answer, not about the route. The second
  question was answered by nobody for a while longer: it told the probe
  which value of Y the formula is about by cutting Y's domain to it, and
  that domain is what the probe samples its models from, so the outcome
  was a constant and every formula came back a match. Which values a
  formula is ABOUT is now a parameter of its own. It is a ONE-population
  question, so where the problem asks about a population and declares
  diagrams of it the arithmetic is not asked; what is asked there instead
  is the question the disagreement was really about — which population
  each factor is read from. A transported estimand takes its conditional
  from a source domain and its marginals from the target, and told a
  reader neither: the field exists on the shape and the producer sets it,
  and the envelope's encoder — a second writer of the same shape — had
  never learned it. Re-derived rather than trusted, from the declared
  selection nodes and the question's own target population, and asked of
  all twenty-three: where a problem has one population, silence names it
  and naming one anyway names something the problem lacks)
- An answer whose own chain records no estimation:
  ``verify_post_stratification`` (a transported effect, added up again from
  the target weight and the two arm totals of each stratum it sums over.
  The transport route appends no derivation step — its chain ends at
  ``identify_via_transport`` — so the copy check above had no second copy
  to compare, and a comparison with nothing to compare is silent rather
  than refusing. Measured before it existed: the transported effect
  accepted any value at all)
- The evidence a reader weighs the answer WITH:
  ``verify_fitted_diagnostics`` (the fitted overlap and saturation ranges
  and the propensity clip, held to the arithmetic every fitted range obeys
  whatever model produced it — a share is a count over a count, a range
  inside its band is a count of zero outside it. The ledger's positivity
  verdict is read off the first of these, so the re-reading that makes that
  verdict a disclosure rather than a claim was resting on a figure that was
  itself only a claim)
- What a block says it is ABOUT: ``verify_frame`` (every
  measurement-error correction re-derives its number FROM the block's own
  labels — which columns, which states, which value the risk is of — so the
  labels are inputs, and an input cannot be wrong: change one and the
  arithmetic re-derives a number that agrees with itself everywhere, and
  answers a question nobody asked. Held here as claims instead — to the
  names the envelope already carries, the values the program declares, the
  position each index says it points at, the flag the risks decide, the
  columns of anything calling itself a misclassification channel, and, for
  every block on the envelope carrying its own sufficient statistics
  (corrections or not), the other writing of whatever it wrote down twice)
- Which node a column of the frame stood for:
  ``verify_a_column_is_one_node`` (the frame holds a column per variable
  and the estimation layer reads a node off the column its predicate
  names, so on a program with several nodes of a variable the frame
  supplied — unrolled in time, or about several objects — one column
  stood for more than one of them. Every record beside the number is
  written in columns, which agree with themselves: a lagged outcome
  adjusted for as the outcome's own column re-derived to the same wrong
  number, and passed)
- Whether a column of the frame stood for anything at all:
  ``verify_a_column_is_a_name_the_program_states`` (the other half of the
  same list, and not a half the rule above could reach: it finds its nodes
  by looking each column up, so a column naming none of them is a column
  it never visits. A frame narrowed to a column nobody declared is a
  number computed over data the program never described. Asked of the
  program rather than of the graph, because a program names a column in
  two places and the graph carries one: the predicate a variable is
  declared under, and the indicator a follow-up time declares beside it
  saying which rows had the event — which is no node of any graph, so a
  rule reading the graph would refuse the one honest survival answer
  there is)
- Pre-flight data diagnostic: ``verify_type_reconciliation`` (2026-07-11,
  borrow-list #3 — re-derives every declared_type_data_mismatch verdict from
  the recorded sufficient statistics in extensions.type_reconciliation
  [n_unique / dtype_kind / observed_values] and confirms the attached gaps
  match; catches a producer that mis-classifies a column, mislabels a
  verdict, or fabricates / drops a gap)
- Discovery-layer verifier: ``verify_markov_blanket`` (2026-07-11, borrow-list
  #4 — the first per-number audit to reach the causal-discovery layer. Re-checks
  the completeness + minimality Markov-blanket definition directly on the
  returned set, recomputing every conditional-independence test from the
  recorded sufficient statistic — the correlation matrix (continuous, Fisher-Z)
  or the sparse joint contingency counts (discrete, chi-square) — with an
  independent reimplementation, without re-running the grow-shrink search;
  rejects a fabricated / trimmed blanket, a corrupted sufficient statistic, or a
  recorded test that disagrees with the recomputation)
- Discovery-layer verifier: ``verify_notears_fit`` (2026-08-30 — the first
  audit of a CONTINUOUS search. A local optimum found by L-BFGS-B cannot be
  replayed, so this does not re-run it: the objective and its gradient depend
  on the data only through the Gram matrix, which makes a d×d matrix a
  sufficient statistic for the whole problem. Recomputes the acyclicity
  residual, the objective, the first-order residual, the edges at the declared
  threshold and the varsortability of the graph they make, with a second
  transcription of the matrix exponential as a non-negative power series;
  rejects a fabricated residual, an edge list that is not what the weights
  say, and a scale diagnostic that contradicts its own edge set. Global
  optimality is NOT certified, and the artifact does not claim it)
- Discovery-layer verifier: ``verify_orientation_propagation`` (2026-07-17,
  interactive equivalence-class resolution — Phase 1. Re-derives the Meek
  closure of a CPDAG under direction constraints from the recorded input CPDAG
  + constraints, with a second standalone transcription of rules R1-R4 and the
  constraint-application / conflict-detection logic — no producer call, no
  causal-learn. Rejects an ``oriented`` set that disagrees with the independent
  closure, a data-contradicting constraint that was silently applied instead of
  surfaced as a conflict, or an unjustified provenance entry)
- Discovery-layer verifier: ``verify_orientation_questions`` (2026-07-17,
  interactive equivalence-class resolution — Phase 2. Audits the compiled,
  leverage-ranked orientation question set: re-runs each remaining edge's two
  Meek cascades from the recorded post-propagation CPDAG with a second
  transcription of R1-R4, and checks every ``leverage`` / ``guaranteed`` /
  ``unlocks`` number, that conflicts are echoed exactly, that there is one
  question per remaining edge, and that the ranking is by descending leverage —
  no producer call)
- Discovery-layer verifier: ``verify_orientation_session`` (2026-07-17,
  interactive equivalence-class resolution — Phase 3. Audits an
  ``orientation_session`` artifact: delegates to ``verify_orientation_propagation``
  and ``verify_orientation_questions`` for the embedded Phase 1 / Phase 2 dicts,
  then certifies the session glue — that the constraints are the latest-wins
  projection of the recorded answers, the embedded artifacts are the session's
  own, ``deferred`` is exactly the still-open unknowns, the source trail credits
  every applied answer with its true entailment and no rejected one, and the
  status is correct — all re-derived from the answers, no producer call)
- Discovery-layer verifier: ``verify_orientation_ledger_export`` (2026-07-17,
  interactive equivalence-class resolution — Phase 5, ledger wiring. Audits an
  ``orientation_ledger_export`` artifact: delegates the embedded session to
  ``verify_orientation_session``, then independently re-derives every oriented
  edge's ledger ``source`` — with a second transcription of the ``llm_proposal``
  taint propagation through the Meek closure — and checks the ``edges``,
  ``proposal_edges``, ``cause_statements`` sources, and ``graph_learned_from_data``
  match; under-disclosure of a proposal-rooted edge is what it catches)
- Bounds-result verifiers — one per implemented BoundsMethod producer:
  * ``verify_manski_tamer_bounds_result`` re-derives the Manski-Tamer
    producer's symbolic expressions independently from program shape +
    the monotonicity declaration in ``program.extensions``.
  * ``verify_manski_natural_bounds_result`` re-derives the
    Phase 12 Manski-natural producer's canonical assumption-free
    expressions; rejects non-empty assumption tuples (Manski natural
    is by definition the no-assumption baseline).
  * ``verify_balke_pearl_iv_bounds_result`` audits the row's facts —
    estimand, the named instrument against what the graph offers, the
    iv1/iv2/iv3 assumption tag set — and rebuilds the lower/upper
    expressions from the query, the instrument and the cardinalities the
    program declares, the way the two closed-form methods' are rebuilt.
- ``VerificationContext`` — the (graph, query, theta) bundle that
  every verifier reads
- Serialization round-trip: ``derivation_to_dict`` /
  ``derivation_from_dict`` / ``context_to_dict`` /
  ``context_from_dict``; raises ``DerivationSerializationError`` on
  malformed input
- Errors — ``VerificationError`` (base) + the three input-class
  failures: ``RuleNotFoundError`` / ``UnknownRuleInputError`` /
  ``StepRefError``

See VERIFIER_DESIGN.md for the operational definition of 严格 this
layer is implementing.
"""
from .errors import (
    RuleNotFoundError,
    StepRefError,
    UnknownRuleInputError,
    VerificationError,
)
from .context import VerificationContext
from .serialization import (
    DerivationSerializationError,
    context_from_dict,
    context_to_dict,
    derivation_from_dict,
    derivation_to_dict,
)
from .verify import (
    verify_assoc,
    verify_causation,
    verify_causation_numeric,
    verify_cause,
    verify_counterfactual,
    verify_counterfactual_cell_numeric,
    verify_counterfactual_conjunction,
    verify_ctf_conjunction_numeric,
    verify_dose_response_curve,
    verify_acr_decomposition,
    verify_e_value,
    verify_effect_structural,
    verify_identification_formula,
    verify_combined_measurement_correction_numeric,
    verify_exposure_measurement_correction_numeric,
    verify_frontdoor_empirical_numeric,
    verify_feedback_loop,
    verify_identification_pattern,
    verify_the_conditioning_a_question_asks_is_named,
    verify_iv_surfaces,
    verify_identify,
    verify_iv_overid_numeric,
    verify_treatment_box,
    verify_joint_identification,
    verify_longitudinal_identification,
    verify_longitudinal_numeric,
    verify_mediation_decomposition,
    verify_mediation_decomposition_numeric,
    verify_measurement_correction_numeric,
    verify_mediation_numeric,
    verify_missing_data_recovery,
    verify_numeric,
    verify_numeric_estimate,
    verify_ovb_sensitivity,
    verify_proximal_effect,
    verify_proximal_estimand,
    verify_proximal_numeric,
    verify_regression_calibration_numeric,
    verify_scm_counterfactual,
    verify_scm_counterfactual_numeric,
    verify_a_given_holding_an_end_is_refused,
    verify_a_decomposition_within_a_moved_stratum_is_refused,
    verify_loop_withdrawal_is_owed,
    verify_recovery_verdicts_are_owed,
    verify_selection_recovery,
    verify_transport_sources,
    verify_vector_iv_identification,
    verify_vector_iv_region,
)
from .bounds_rules import (
    verify_balke_pearl_iv_bounds_result,
    verify_manski_natural_bounds_result,
    verify_manski_tamer_bounds_result,
)
from .assumption_ledger_rules import verify_assumption_ledger
from .bootstrap_rules import verify_bootstrap_records
from .cluster_inference_rules import verify_cluster_inference
from .outcome_error_rules import verify_outcome_error
from .berkson_rules import verify_berkson_error
from .survival_rules import verify_survival_curve
from .fingerprint_rules import verify_fingerprints_agree, verify_one_row_count
from .type_reconciliation_rules import (
    verify_declared_types, verify_type_reconciliation)
from .program_copy_rules import (
    verify_ambiguity_copy,
    verify_answer_names_its_kind,
    verify_answer_names_its_question,
    verify_longitudinal_option_copy,
    verify_llm_proposed_review,
)
from .envelope_arithmetic_rules import verify_envelope_arithmetic
from .confidence_level_rules import verify_confidence_level
from .data_gap_rules import (
    verify_answer_tier,
    verify_collider_caveats_are_owed,
    verify_gap_edge_statements,
    verify_gap_program_sites,
    verify_proposed_edges_are_disclosed,
)
from .statement_rules import (
    verify_statements_carry_their_facts,
    verify_statements_repeat_what_decided_them,
)
from .status_rules import (
    verify_answer_status,
    verify_answer_status_fits_its_question,
)
from .step_name_rules import verify_the_chain_names_its_steps
from .gap_claim_rules import (
    verify_gap_names,
    verify_gap_quotes,
    verify_gap_subjects,
)
from .estimator_failure_rules import verify_refusal_block
from .sample_size_rules import verify_required_data
from .mechanism_rules import verify_mechanism_target
from .investigation_rules import verify_investigation_items
from .bounds_account_rules import verify_bounds_account
from .post_stratification_rules import verify_post_stratification
from .fitted_diagnostic_rules import verify_fitted_diagnostics
from .frame_rules import (
    verify_a_column_is_one_node,
    verify_a_column_is_a_name_the_program_states,
    verify_frame,
)
from .display_copy_rules import verify_numeric_display_agrees
from .markov_blanket_rules import verify_markov_blanket
from .notears_rules import verify_notears_fit
from .simex_rules import verify_simex_numeric
from .differential_error_rules import (
    verify_differential_error_numeric,
    verify_differential_outcome_error_numeric,
)
from .orientation_rules import verify_orientation_propagation
from .orientation_question_rules import verify_orientation_questions
from .orientation_session_rules import verify_orientation_session
from .orientation_ledger_rules import verify_orientation_ledger_export
from .selection_numeric_rules import verify_selection_recovery_numeric
from .missing_numeric_rules import verify_missing_data_numeric

__all__ = [
    "DerivationSerializationError",
    "RuleNotFoundError",
    "StepRefError",
    "UnknownRuleInputError",
    "VerificationContext",
    "VerificationError",
    "context_from_dict",
    "context_to_dict",
    "derivation_from_dict",
    "derivation_to_dict",
    "verify_ambiguity_copy",
    "verify_answer_names_its_kind",
    "verify_answer_names_its_question",
    "verify_longitudinal_option_copy",
    "verify_answer_tier",
    "verify_answer_status",
    "verify_answer_status_fits_its_question",
    "verify_statements_carry_their_facts",
    "verify_statements_repeat_what_decided_them",
    "verify_the_chain_names_its_steps",
    "verify_confidence_level",
    "verify_envelope_arithmetic",
    "verify_gap_names",
    "verify_gap_program_sites",
    "verify_gap_edge_statements",
    "verify_proposed_edges_are_disclosed",
    "verify_collider_caveats_are_owed",
    "verify_gap_quotes",
    "verify_gap_subjects",
    "verify_refusal_block",
    "verify_required_data",
    "verify_mechanism_target",
    "verify_investigation_items",
    "verify_bounds_account",
    "verify_identification_formula",
    "verify_fitted_diagnostics",
    "verify_a_column_is_one_node",
    "verify_a_column_is_a_name_the_program_states",
    "verify_frame",
    "verify_post_stratification",
    "verify_assoc",
    "verify_assumption_ledger",
    "verify_causation",
    "verify_causation_numeric",
    "verify_cause",
    "verify_berkson_error",
    "verify_survival_curve",
    "verify_bootstrap_records",
    "verify_cluster_inference",
    "verify_differential_error_numeric",
    "verify_differential_outcome_error_numeric",
    "verify_outcome_error",
    "verify_counterfactual",
    "verify_counterfactual_cell_numeric",
    "verify_counterfactual_conjunction",
    "verify_ctf_conjunction_numeric",
    "verify_dose_response_curve",
    "verify_acr_decomposition",
    "verify_e_value",
    "verify_effect_structural",
    "verify_combined_measurement_correction_numeric",
    "verify_exposure_measurement_correction_numeric",
    "verify_balke_pearl_iv_bounds_result",
    "verify_feedback_loop",
    "verify_identification_pattern",
    "verify_the_conditioning_a_question_asks_is_named",
    "verify_iv_surfaces",
    "verify_identify",
    "verify_joint_identification",
    "verify_llm_proposed_review",
    "verify_longitudinal_identification",
    "verify_longitudinal_numeric",
    "verify_manski_natural_bounds_result",
    "verify_manski_tamer_bounds_result",
    "verify_markov_blanket",
    "verify_notears_fit",
    "verify_numeric_display_agrees",
    "verify_orientation_propagation",
    "verify_orientation_questions",
    "verify_orientation_session",
    "verify_orientation_ledger_export",
    "verify_frontdoor_empirical_numeric",
    "verify_iv_overid_numeric",
    "verify_treatment_box",
    "verify_measurement_correction_numeric",
    "verify_mediation_decomposition",
    "verify_mediation_decomposition_numeric",
    "verify_mediation_numeric",
    "verify_numeric",
    "verify_numeric_estimate",
    "verify_one_row_count",
    "verify_missing_data_numeric",
    "verify_missing_data_recovery",
    "verify_ovb_sensitivity",
    "verify_proximal_effect",
    "verify_proximal_estimand",
    "verify_proximal_numeric",
    "verify_regression_calibration_numeric",
    "verify_scm_counterfactual",
    "verify_scm_counterfactual_numeric",
    "verify_a_given_holding_an_end_is_refused",
    "verify_a_decomposition_within_a_moved_stratum_is_refused",
    "verify_loop_withdrawal_is_owed",
    "verify_recovery_verdicts_are_owed",
    "verify_selection_recovery",
    "verify_selection_recovery_numeric",
    "verify_simex_numeric",
    "verify_transport_sources",
    "verify_declared_types",
    "verify_type_reconciliation",
    "verify_vector_iv_identification",
    "verify_vector_iv_region",
]
