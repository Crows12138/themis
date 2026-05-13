# Response renderer stress test — output bridge blind validation

Date: 2026-04-25

## Setup

Four blind sub-agents (isolated conversations, only access to
`themis/prompts/response_rendering.md` + one per-case input file)
rendered the Themis JSON outputs of cases 25-28 into Chinese
replies. Inputs assembled in `docs/eval_set/render_run_v1/` —
each contains `narrative + question + program + result`. No
gold reply exists (output side has no gold), so this is a
**prompt-gap discovery** run, not pass/fail.

This is the first end-to-end blind test of the **output bridge**.
Earlier stress test (`phase_7_8_stress_test.md`) only validated
the input bridge (NL → kernel_ast).

## Aggregate result

| Case | Method | Render status | Major gaps surfaced |
|---|---|---|---|
| 25 (med→BP) | backdoor_linear | reasonable reply | numeric_estimate template missing; bool-vs-float schema mismatch unhandled |
| 26 (smoke→tar→cancer) | frontdoor_logistic | reasonable reply | no front-door numeric template; bidirected edge provenance unspecified |
| 27 (gene IV) | iv_wald | reasonable reply | IV section trigger gap (only fires on `extensions.iv_identification`, not on `method=iv_wald`) |
| 28 (aspirin / sensitivity) | backdoor_logistic | reasonable reply | E-value note phrase ↔ threshold band mismatch ("substantial" vs "比较稳健") |

All 4 produced usable Chinese replies. None hallucinated numbers.
All 4 surfaced some llm_proposal edges. All 4 successfully
omitted A1 ambiguity block when `program.extensions.ambiguities`
was absent.

## Gap clusters (consolidated across 4 agents)

### Cluster A — `numeric_estimate` block has no rendering template (CRITICAL)

**Reported by**: all 4 agents, in slightly different phrasings.

The "Reading the JSON" field table lists `numeric_result.value`
(a probability), but Phase 7's actual output field is
`numeric_estimate` with sub-fields:
`point / ci_lower / ci_upper / ci_level / method / assumptions /
sample_size / data_hash / treatment / outcome / adjustment /
instrument / conditioning / formula / decomposition`.

Agents independently invented:
- Whether to list CI (all did)
- Whether to list assumptions (all did, in different formats)
- Whether to translate snake_case assumption IDs to Chinese (3 did, 1 quoted verbatim)
- Whether to mention sample_size, data_hash, model (split 2/2)
- Whether to render the `formula` symbolically (none did, but unclear)

**Severity**: high. Rendering prompt was written for the v0 layer
(structural-only); was never updated when Phase 7 numeric layer
landed.

### Cluster B — Bidirected edge `annotations.source` not covered

**Reported by**: 26, 27, 28.

Edge-provenance section says "each `cause` statement's
`annotations.source`". Cases 26 / 27 / 28 all have `bidirected`
statements also annotated `source: "llm_proposal"`. Agents
extended the cause-edge convention to bidirected by analogy,
but this is invented.

**Severity**: medium. Easy fix: explicitly extend the rule.

### Cluster C — IV section trigger gap

**Reported by**: 27.

Prompt says "When the result's `extensions.iv_identification` is
present, …". Case 27 was numerically solved via `iv_wald`, but
that path **does not populate** `extensions.iv_identification`
— only the structural identification path does. Agent had to
recognize IV from `numeric_estimate.method=iv_wald` +
`numeric_estimate.instrument` and apply the IV template by
analogy.

**Severity**: high. The IV disclosure section exists precisely
because IV needs special caveats (LATE vs ATE, monotonicity,
exclusion). Missing it on the numeric path defeats the section.

### Cluster D — Front-door numeric has no dedicated section

**Reported by**: 26.

Prompt has dedicated templates for IV identification and
mediation decomposition, but not for front-door. Case 26 was
solved via `frontdoor_logistic` — agent assembled the answer
from the generic numeric block + assumption list, with no
template guidance on whether to mention "identified despite
unobserved confounder via the bidirected edge", whether to
show the front-door formula symbolically, etc.

**Severity**: medium. Front-door is rarer than backdoor; gap
is real but lower-frequency.

### Cluster E — `numerically_solved` + still-open `investigation_requests`

**Reported by**: 25, 26, 27, 28.

Prompt says investigation_requests are "usually the main content
of your reply" — implicitly assumes `needs_investigation` status.
But all 4 cases are `numerically_solved` AND have non-empty
investigation_requests (parameter / framing). Agents split:
- Render full grouping anyway (3 agents)
- Demote to "doesn't block the answer" footer (1 agent)

**Severity**: medium. Real ambiguity; prompt should pick one.

### Cluster F — Continuous-outcome ATE semantics

**Reported by**: 25, 28.

`numeric_result.value` is a probability (0..1). `numeric_estimate.point`
can be:
- a probability (logistic outcome, e.g., case 28: -0.069 → "下降 6.9 个百分点")
- a continuous unit difference (linear outcome, e.g., case 25: -9.83 → mmHg)

Prompt has no guidance on translating either to user-facing prose.
Both agents invented their phrasing successfully, but this should
be templated.

**Severity**: medium. Affects every numeric reply.

### Cluster G — Bool-declared variable + continuous data mismatch

**Reported by**: 25.

Case 25's program declares `systolic_bp` with `domain: [true, false]`,
but `method=backdoor_linear` reveals the actual data is continuous
(ATE = -9.83). Themis "data wins" gracefully. Renderer has no
guidance on whether to surface this schema/data mismatch to the
user. Agent did flag it; it was actually useful.

**Severity**: low-medium. The A1 prompt v2.6.1 was supposed to fix
the upstream side; renderer surfacing it is a defense-in-depth.

### Cluster H — E-value `note` phrase vs threshold band mismatch

**Reported by**: 28.

`note` field says "substantial — confounder would need to be
sizable to explain away". Prompt's threshold table maps E-value
2.5-5 → "比较稳健" and 1.5-2.5 → "中等强度". "Substantial" maps
ambiguously between them. Case 28's E-value = 2.66 → falls in
"比较稳健" band per table, but note says "substantial" which the
table doesn't explicitly Chinese-map.

**Severity**: low. Cosmetic. Either align note phrasing to the
table or remove the duplication.

### Cluster I — `investigation_requests[group=structure]` with developer-internal reasons

**Reported by**: 27.

Case 27 has a `structure`-group request whose `reason` cites
"PHASE_2_LATENT_CHARTER.md §7" — internal doc reference. Renderer
has to translate to user prose. Prompt gives no guidance for
structure-group rendering or for handling developer-facing reason
strings.

**Severity**: low. Affects edge-case structural notes.

### Cluster J — `framing_notes` vs `investigation_requests` redundancy

**Reported by**: 25, 28.

Both fields can carry the same framing info. Prompt says "use the
structured request instead", but doesn't say whether to actively
ignore framing_notes or treat as cross-check.

**Severity**: low. Easy fix: explicit "skip framing_notes when
investigation_requests covers same predicates".

## Recommendation — response_rendering.md v3

In rough effort order (high-leverage first):

1. **Add `## Numeric estimate rendering (Phase 7)` section** —
   covers `numeric_estimate.*` field rendering. Templates per
   `method` value (backdoor_linear / backdoor_logistic /
   frontdoor_logistic / iv_wald / iv_2sls / mediation_*). Specifies
   how to format point + CI, how to translate snake_case
   assumptions to Chinese, what `data_hash` / `sample_size` to
   surface. **Closes clusters A, C, D, F.**

2. **Extend edge-provenance section to bidirected** — one
   paragraph. **Closes cluster B.**

3. **Add "numerically_solved + still-open requests" rule** —
   pick: demote to footer with "the answer is given; these are
   for refinement". **Closes cluster E.**

4. **Add `## Schema mismatch disclosure` section** — when
   `numeric_estimate.method ∈ {backdoor_linear, frontdoor_linear}`
   but program's outcome variable was declared bool, surface
   the mismatch. **Closes cluster G.**

5. **Align E-value note phrases to threshold table** — either
   change `themis/estimation/sensitivity.py` `note` strings to
   use exact band words ("中等" / "比较稳健" / "非常稳健"), or
   remove the duplication. **Closes cluster H.**

6. **Add structure-group rendering rule** — say "if reason
   cites internal doc paths, translate to user-facing reason or
   suppress". **Closes cluster I.**

7. **Explicit framing_notes ↔ investigation_requests
   deduplication rule**. **Closes cluster J.**

## Estimated effort

- Patch v3: ~3-4 hours of prompt edits + sensitivity note
  alignment
- Re-stress with same 4 cases: ~10 minutes (driver script exists)

## Artifacts

- `docs/eval_set/render_run_v1/{25,26,27,28}_*_input.json` — agent inputs
- This report
- 4 sub-agent transcripts in temp dir

---

## v3 verification (re-stress, same 4 cases, 2026-04-25)

After patching `response_rendering.md` to v3, re-spawned 4 fresh
blind agents on the same 4 inputs. **All 4 produced
substantially better replies** with consistent structure and
field handling.

### Closed gaps

| Cluster | Status | Evidence |
|---|---|---|
| A — numeric_estimate template | **closed** | All 4 agents now use the per-method template (Backdoor / Front-door / IV); CI / method / assumptions consistently rendered |
| B — bidirected provenance | **closed** | Cases 26, 27 surfaced bidirected `llm_proposal` correctly with the new template |
| C — IV trigger via numeric path | **closed** | Case 27 triggered IV section from `numeric_estimate.method=iv_wald` |
| D — front-door numeric template | **closed** | Case 26 used the new front-door template directly |
| E — numerically_solved + open requests | **closed** | All 4 demoted requests to footer; no longer led with them |
| F — ATE semantics translation | **closed** | All 4 used the per-method "What the point value means" table |
| G — schema mismatch | **closed** | Case 25 surfaced bool↔float for systolic_bp |
| H — E-value note alignment | **closed** | Sensitivity note now embeds Chinese band ("substantial / 比较稳健"); no agent confused |
| I — structure-group rendering | **closed** | Case 27 correctly suppressed the developer-facing ADMG/c-factor note |
| J — framing_notes dedup | **closed** | All 4 dropped framing_notes when investigation_requests covered same predicates |

### Residual minor gaps (v3.1 candidates, low priority)

1. **`validate_parameter` redundancy under numeric path** — fixed
   in v3.1 patch (suppress entirely when `numeric_estimate` already
   delivered).
2. **Percentage-point conversion explicitness** (case 27) — clarified
   in v3.1 IV row of "What the point value means" table.
3. **Assumptions table extension** — added 5 more IDs covering
   front-door + IV LATE estimand semantics in v3.1.
4. **Multi-edge `llm_proposal` consolidation** — when 5+ edges all
   carry `llm_proposal`, listing each separately is verbose.
   Renderers naturally consolidate; not enforced by prompt. Could
   add explicit guidance later.
5. **Bidirected `llm_proposal` disclosure phrasing for IV case** —
   the v3 template wording suggests "switch to another strategy"
   if user disagrees with bidirected — but for IV, removing
   bidirected means falling back to backdoor, not "another strategy".
   Cosmetic.

### v3 + v3.1 overall

10/10 major gaps from the original blind run are now closed.
Residual gaps are stylistic / cosmetic. **Output bridge is
production-ready** at the same quality bar as the input bridge
(after Phase 7+8 stress test → v2.6 patch).

### v3.1 micro-patch contents (also in this commit)

- Suppress-rule for `validate_parameter` under `numeric_estimate`
- Percentage conversion note in IV row of point-semantics table
- 5 additional assumption ID translations (front-door + IV LATE)

