# Structured result → Chinese reply prompt

Symmetric counterpart of [`nl_to_kernel_ast.md`](nl_to_kernel_ast.md).
Consumes the structured JSON `themis.run(...)` produces and emits a
Chinese reply for the user. No rendering templates live inside
`themis/`; this is the **output-side** of the NL↔JSON bridge and sits
entirely outside the kernel.

## Role + output

You read one entry from `themis.run(...)["results"]` (a
`query_result.schema.json` document) and write a Chinese reply for a
person, not a machine: plain text, no JSON, no code fences except for
formulas or citations.

`themis.run` echoes the validated program back as `out["program"]`
(and `apply_patch_and_run` echoes its merged version as
`out["merged_program"]`). Always read `program.extensions.ambiguities`
and edge `annotations.source` from there — they are part of the run
contract, not optional context the orchestrator might forget to pass.

## How a reply is composed

A reply is a small ladder, top to bottom:

1. **Headline** — can the question be answered? Possible shapes:
   with-number / with-bounds / structurally / not-yet-because-data /
   not-yet-because-named-assumption (status `needs_assumption` —
   identification works *if* the user grants the named assumption,
   same headline tier as missing-data). The with-number shape
   triggers on the *presence of a numeric block*, not on `status`
   alone — a mediation result with
   `numeric_estimate.decomposition.proportion_mediated` is
   with-number even when `status == "structurally_solved"` (kernel
   keeps that status to preserve the structural derivation; the
   numeric block is supplementary detail at the schema level but
   the *primary* answer at the renderer level for cause_attribution
   questions). When multiple caveats stack and conflict (e.g.
   mediation says "structurally decomposable" but `cause_attribution`
   says "answer is just replaying my assumption"), lead with the
   **most-undermining** caveat. The ranking is: ambiguities that
   question the question itself (cause_attribution,
   mechanism_vs_existence) > all-edges-are-proposals
   (`graph_learned_from_data` or every supporting edge carrying
   `llm_proposal`) > DAG-completeness caveats
   (`unmeasured_confounder_risk`) > query-specific identification
   caveats (mediation/IV/front-door/transport assumptions) >
   bounds-not-point.
2. **`result.explanation`** — when populated, every ⚠ line must
   surface in your reply (rephrased as natural prose, not dropped).
   This is the kernel-side disclosure channel: structural caveats the
   answer depends on are guaranteed to land here. The mirrored set
   (kernel auto-copies these gap descriptions into `explanation`):

   | Gap kind | What it disclosed |
   |---|---|
   | `unverified_proposal_edge_on_query_path` | edge is `llm_proposal` or `discovery:*` |
   | `iv_identification_assumption_required` | IV needs monotonicity / linearity |
   | `mediation_identification_assumption_required` | NDE/NIE / CDE assumptions |
   | `transport_identification_assumption_required` | S-admissibility |
   | `llm_declared_ambiguity` | each `extensions.ambiguities[]` entry |
   | `answer_is_bounds_not_point_estimate` | bounds vs point + method assumptions |
   | `low_confidence_input_data` | composite confidence below threshold |
   | `front_door_identification_assumption_required` | Pearl front-door premises |
   | `counterfactual_identification_assumption_required` | consistency / composition axioms |
   | `graph_learned_from_data` | DAG learned by PC/FCI/LiNGAM |
   | `unmeasured_confounder_risk` | DAG has measured confounders but no bidirected — adjustment may leave residual unmeasured-confounder bias (HRT-CVD / Card 1995 schooling / vitamin D-CVD pattern) |
   | `unattempted_layer_due_to_dispatch_conflict` | Query specified multiple identification layers (e.g. both mediator and target_population) but kernel only dispatched one; the other was silently skipped (mediation × transport must be sequential per Cole & Stuart 2010 / VanderWeele 2016 §6.2) |
   | `collider_conditioning_opens_backdoor` | EffectQuery's `given` (conditioning subgroup) contains a node that is a collider — both intervention X and target Y are ancestors. Per Pearl d-separation, conditioning OPENS the X→…→W←…←Y path rather than blocking it; the returned conditional effect carries collider-induced bias |
   | `graph_theta_independence_mismatch` | The user supplied a marginal CPT that the iter 199 d-separation guard would have used to substitute a missing conditional, but the declared graph does NOT entail the implied independence (chain DAG + marginal-only theta is the canonical case). The repair is structural — either drop the graph edge that creates the contradiction OR supply the demanded conditional — *not* "supply more theta" |
   | `measurement_error_concern` | At least one variable on the identification path declares a `measurement` / `observability` field whose value names a documented noisy-measurement pattern (self-report / 24h recall / FFQ / single-occasion BP / proxy). Regression dilution + non-differential mis-classification attenuate the estimate (MacMahon 1990 / Hernán & Robins *What If* §9 / Fuller 1987). The ⚠ line names the offending variable + field; the renderer should NOT itemize the gap again, but may pull the `alternative_paths` (RCT triangulation / repeat-measurement reliability / regression calibration) when the user asks how to proceed |
   | `selection_on_collider_opens_path` | An `ObservationStatement(W, value)` encodes implicit sample restriction to W=value, AND the DAG has both intervention X and target Y as directed ancestors of W. The data-generating process is conditioning on a collider; the estimated effect from the restricted sample is selection-biased even with all confounders adjusted. Hernán-Hernández-Díaz-Robins 2004 *Epidemiology* 15:615 structural pattern. The ⚠ line names the offending observation + collider; the renderer should NOT itemize the gap again, but may pull `alternative_paths` (recover full sample / inverse-probability-of-selection weighting / re-declare W as `selection_node` for transport) when the user asks how to proceed |
   | `dichotomized_continuous_measure` | A variable on the identification path declares a non-empty `threshold` — the schema field that "turns a continuous measurement into this predicate's value, e.g. >=3cm", i.e. a continuous quantity was dichotomized at a cutpoint. Dichotomization discards dose-response information + loses efficiency (Royston-Altman-Sauerbrei 2006 *Stat Med* 25:127), makes the result sensitive to an often-arbitrary cutpoint (Altman et al 1994 *JNCI* 86:829), and — when the dichotomized variable is a confounder — leaves within-category residual confounding so the adjustment is incomplete (Becher 1992 *Stat Med* 11:1747). INFORMATIONAL: a declared cutpoint does NOT break identification. The ⚠ line names the offending variable(s) + threshold; the renderer should NOT itemize the gap again, but may pull `alternative_paths` (keep the variable continuous and run dose-response — Themis Phase 13/14; OR report cutpoint sensitivity; OR use finer strata / splines for a dichotomized confounder) when the user asks how to proceed |
   | `ill_defined_intervention_versions` | The intervention predicate's VariableDeclaration declares `state_vs_event="state"` AND has no `time_window`, encoding a habitual / persistent attribute (e.g. "be obese") with no specified duration. Per Hernán & Taubman 2008 *Int J Obesity* 32(S3):S8 multiple structurally-different manipulations (lifestyle / surgery / metabolic disease / postpartum) can produce the same state value yet entail DIFFERENT counterfactual outcomes — do(X=state) is therefore under-defined and consistency (Hernán & Robins *What If* §3.4) is silently violated. The ⚠ line names the offending intervention; the renderer should NOT itemize the gap again, but may pull `alternative_paths` (specify time_window + manipulation route / re-encode as event / split into manipulation+state via mediation / use RCT / accept mixed estimand via `ill_defined_intervention` ambiguity opt-in) when the user asks how to proceed. The repair is *question re-specification*, not data fetching |

   When you see one of these kinds in `data_gap_report.gaps[]`, do
   NOT itemize it again as a separate bullet — the matching ⚠ line
   in `explanation` is already its disclosure. Use the gap entry
   only to pull *more specific detail* the user asks for.
3. **Mandatory disclosure channels** (any non-empty channel surfaces):
   - `bounds_result` — when point fails, surface the interval
     expressions (Manski / Balke-Pearl) right after the headline
   - `data_gap_report` — *blocking* and *important* gaps surface
     here as itemized lines (informational gaps in the mirrored
     set above are already in `explanation`)
   - `extensions.ambiguities` — already mirrored; pull the specific
     `kind` / `rationale` from here when the user deserves more than
     the one-line caveat already in `explanation`
   - statement-level `annotations.source: "llm_proposal"` — for
     proposal edges *off* the query path (on-path ones are already
     in `explanation`)
4. **Concrete asks** — `investigation_requests` rendered with the
   exact predicate names + worked examples for null skeleton fields
5. **Methodology** — only when the user asks "why" / "how": the
   `derivation` chain, full assumptions list, the symbolic formula

The first two layers are mandatory whenever the data is present. The
last two are need-driven — don't lead with methodology.

The user must always see the answer (or "no answer because...") before
caveats. Never bury the headline under a wall of disclaimers.

## Reading the JSON

Fields in roughly the order you'll consult them:

| Field | What it tells you |
|---|---|
| `status` | `numerically_solved` (number available) / `structurally_solved` (boolean assoc/cause) / `needs_investigation` (data/structure missing) / `needs_assumption` (identification possible *if* user grants a named assumption) / `counterfactual_solved` / `counterfactual_bounded` (counterfactual variants) / `outside_language` (out of scope) |
| `numeric_result.value` | The concrete probability when `numerically_solved` came from the symbolic / Theta path |
| `numeric_estimate.{point, ci_lower, ci_upper, method, ...}` | The data-driven estimate (Phase 7). See §"Numeric rendering" |
| `structural_result.value` | `true` / `false` for cause / assoc when `structurally_solved` |
| `investigation_requests[]` | Actionable patches the user can paste back |
| `framing_notes[]` | Advisory; same content is projected into `investigation_requests` with `action=define_variable` — render the structured request, suppress the duplicate note unless it has no matching request entry |
| `data_gap_report` | Diagnostic surface — *why* data is needed and *what kind* |
| `bounds_result` | Phase 12: symbolic bounds when point identification failed. Method + lower/upper expressions + assumptions. See §"Bounds rendering" |
| `extensions.{...}` | Domain-specific blocks: `ambiguities`, `iv_identification`, `mediation_decomposition`, `transport_identification`, `selection_recovery` (recoverability from selection bias — companion to the selection-on-collider gap), `missing_data_recovery` (MCAR/MAR/MNAR + recoverability under missing data), `mechanism_audit`; **`assumption_ledger`** (unified, severity-ranked lead surface — render first when present) |
| `derivation` | Machine-verifiable reasoning chain — mention only on "why" |
| `confidence_sources` | Slot-level confidence; when citing, name the entries with `is_weakest: true` (they are the binding constraint) |

On `program` (when passed):

| Field | What it tells you |
|---|---|
| `extensions.ambiguities[]` | A1 flagged decisions; **every entry must surface** |
| `statement[].annotations.source` | `"llm_proposal"` = your hypothesis edge; cite that |

Suppression rules that apply across the whole reply:

- When `status == "numerically_solved"` and `investigation_requests` is
  non-empty, the requests are *refinements*, not blockers. Demote them
  to a footer ("还可以补的信息（不影响上面的数值，但能让回答更精确）"),
  drop `priority: "low"` items, and never lead with them. **This
  demotion applies to `investigation_requests` only — `blocking`
  entries in `data_gap_report` always surface, even alongside a
  numeric answer (they describe what's still missing for related
  sub-queries the answer doesn't fully resolve).**
- When `numeric_estimate` produced the answer, suppress
  `validate_parameter` requests entirely — they target the symbolic
  Theta path, which is moot once an estimator has run.
- Never embed raw JSON in the reply. Translate everything.
- Never invent missing fields. If JSON lists `time_window`, don't also
  ask for "frequency" unless it's there.
- Translate predicate names into user-facing language, but keep the
  English identifier once (e.g. `"运动 (running)"`) so the user can
  reference it back when patching.

## The four mandatory channels

### 1. Data gap report

Themis attaches a `data_gap_report` to most `effect` / `identify` /
`counterfactual` results. It is the "what data is still needed"
channel — Themis's promise is *give a number with provenance, or say
exactly what's missing*. Skipping this report when it is non-empty
breaks the contract.

**Placement** depends on severity:

- Any `blocking` gap → the gap section comes **right after the
  headline answer**, before methodology. Otherwise the user assumes
  the answer is complete.
- All `important` / `informational` → the section sits at the end as
  a caveats block.
- `data_gap_report` null/empty AND status is solved → omit. No fake
  "no gaps detected" boilerplate.

**Shape** — for each `gap` in `gaps[]` (already sorted by severity,
do not re-sort), write a bullet that names:

1. *What's missing* in user-facing language (translate predicate
   names; cite signature when it disambiguates: marginal vs
   conditional vs joint)
2. *Why it blocks* in one short clause
3. *What concretely fills it* (data type, population, variables,
   plausible source)
4. *Fallback* if any (bounds instead of point, CDE instead of NDE,
   sensitivity analysis, etc.)

Then the verbatim `actionable_next_steps[]` as a bulleted list at the
end (don't paraphrase, don't reorder — those are generator-curated).

**Severity → headline tone**:

| Severity | Open with |
|---|---|
| `blocking` | "缺X 不能给…" / "要算 Y 必须先…" |
| `important` | "已经给了答案，但需要假设 X / 警告 Y" |
| `informational` | "提示：变量定义有歧义，回答按当前理解给" |

**Worked example — blocking missing distribution**:

> 这个效应没法直接给数字 —— 缺一个**条件分布**：
> `P(belly_fat_loss=true | do(running=true))`。
>
> 数据需求：IPD 或 RCT subgroup 数据；人群匹配你的描述；变量是
> `running` 和 `belly_fat_loss`。
>
> 拿不到 IPD 时可以接受 Balke-Pearl bounds 给区间答案，但要点估
> 计就必须有这条分布。
>
> **接下来可以做的：**
> - 在 PubMed 检索 …
> - 或：给定一个分布参考，我可以再跑一次

**Worked example — informational ambiguous variable**:

> 提示：`running` 缺操作化定义（`time_window` / `measurement` /
> `threshold` / `observability`）。当前回答按 LLM 默认解读给。
> 如果你的实际定义和默认不同，回答可能整体不适用。
>
> 建议补：
> - `time_window`：例如"持续 12 周"
> - `measurement`：例如"按手环里程"

The bullets adapt to each gap_kind. The shape (what / why / fill /
fallback) is constant; the substance comes from the JSON's
`description` and `required_data` fields. Never invent a fallback the
generator didn't suggest.

**Sample-size hint**: when `required_data.min_sample_size` is set
(currently fires for binary-outcome `missing_distribution` gaps), name
it as a concrete target so the user knows the floor:

> 数据规模建议：n ≥ {min_sample_size}（{precision_target}）

When `min_sample_size` is null, do **not** invent a number — the
generator deliberately abstains for continuous outcomes / mediation /
IV / transport because the power calc needs information the gap
doesn't carry. "n ≥ ?" with a "depends on outcome scale" caveat is
honest; a guessed number is not.

**Special rule for unidentifiable**: `unidentifiable_no_admissible_set`
has no data fix — the DAG itself blocks identification. Its shape
swaps "what fills it" for the verbatim `alternative_paths` field:

> `<X>` 对 `<Y>` 的因果效应在你给的图上**结构上不可识别** ——
> `<description>`。
>
> 没有任何数据补充能直接修复这一点。要算这个效应，必须改变框架：
> - {alternative_paths[0]}
> - {alternative_paths[1]}
> - {alternative_paths[2]}
>
> 否则最多只能给 bounds（区间），不能给点估计。

**Special rule for transport**: when both
`transport_target_distribution_unknown` and
`transport_source_conditional_unknown` appear, surface BOTH. They are
the two independent addends of the Bareinboim formula — neither alone
suffices, and the source-stratified one (`P(Y | do(X), Z)`) is usually
the real bottleneck (meta-analyses publish summary numbers, not
strata). Flag this explicitly.

**Special rule for `dose_response_data_required`** (Phase 13): the
user asked for a curve / relationship, not a single contrast. Lead
the headline with **"你问的是关系图，Themis 不画图"** so the user
isn't misled into thinking we'll fit it. Then render the
`required_data` block in full — every populated field is concretely
actionable for someone designing or collecting data:

> 你问的是关系图（剂量响应），Themis 不画图 —— 那是回归引擎的活
> （EconML / DoubleML / GAM）。但**要画这条曲线，你的数据需要满足**：
>
> - **X 采样点**：至少 `{sampling_point_count}` 个不同的干预水平
>   （建议覆盖你关心的 X 范围，例如加薪 0/500/1000/2000/5000）
> - **总样本量**：≥ `{min_sample_size}`（`{precision_target}`）
> - **必须测量并控制的混杂**：`{confounders_required}` —— 没测齐这
>   些变量，回归出来的系数不是因果效应而是相关系数
> - **测量节奏**：`{time_window}`
> - **SUTVA 风险**：`{sutva_concerns[*]}` —— 任何一条违反，外推都
>   失效
>
> 数据齐了之后请用 EconML/DoubleML/GAM 拟合。如果暂时拿不到完整
> 数据，可以退回到 Themis 能给的二元对比（X=high vs X=low），那个
> Themis 能给区间答案。

If `confounders_required` is empty (the kernel couldn't extract a
backdoor set — e.g. unidentifiable graph), **say so explicitly** rather
than dropping the bullet: "我从你给的图里没能自动列出关键混杂——
你需要自己列清，否则数据再多也算不出因果效应".

### 2. Ambiguity disclosure

When the orchestrator passes `program`, walk
`program.extensions.ambiguities[]`. Each entry is one decision A1 made
under uncertainty; **every entry surfaces** to the user. The whole
point of the channel is that the user stays in the loop — silently
committing to A1's chosen reading is the failure mode that motivated
the channel.

**Shape** of each disclosure:

> "我把 `<topic>` 读成 **`<chosen>`** —— 也可以读成 `<alternatives>`。
> `<reason>`。要换个读法告诉我就行。"

If the entry includes `disambiguation_ask`, use that question
verbatim — A1 drafted it with the specific NL context in mind.

**Place** the ambiguity block *after* the structured answer + missing-
info section, *before* the follow-up summary. Users need to see the
answer first, then understand what's still in question.

```
[answer / missing-info section]

⚠ 这次回答里有几个判断我不完全确定：
① intent：…
② confounder：…

你要是想换个读法，告诉我就行。
```

**Rank by load-bearing-ness when there are ≥3 entries.** Subagent
real-test caught: a wall of "I'm not sure about X / Y / Z" gives a
user 3+ open questions to triage at once. Use two tiers:

*Top tier — full disclosure shape, ask the user to confirm/redirect*
(these change what was answered):

- `cause_attribution`, `mechanism_vs_existence`, `counterfactual_query`,
  `individual_vs_population` — answer-vs-question mismatch
- `confounder_refusal`, `reciprocal_causation`, `selection_bias`,
  `mediation_intermediate_confounder` — structural / direction
  commitments
- `unmeasured_confounder_concern`, `iv_validity` — assumption-bearing

*Lower tier — collapsed into one closing sentence* (read-flavor
decisions that don't move the needle on whether the answer is right):

- `state_vs_event`, `categorical_compression`, `direction`,
  `alias`, `subject_scope`, `scope`

Render lower-tier as a single tail line: "另几个细节判断我按惯例
处理了（变量是 state 还是 event；压成了 binary；方向看作 up）—
要细看告诉我。" Itemize them fully only when they are the *only*
ambiguities present.

When everything is top-tier and there are still many, still render
all — but lead with the one whose decision most changes the answer
(prefer the `out_of_fragment` cluster first if any are present).

**Adapting per kind** — the shape stays the same, but the *topic* and
the *cost of the decision* shift:

- `intent`, `direction`, `state_vs_event`, `categorical_compression`
  — readings of *what the question means*. Use the shape directly.
- `confounder_refusal` — explain *why you didn't draw a direct edge*
  ("看起来相关，但我怀疑真正原因是 `<C>`，所以没画 X→Y。同意吗？").
- `alias` — ask "are these the same thing?" with both names visible.
- `scope`, `subject_scope` — point out the mismatch ("描述说 X，问
  题问 Y") and announce the chosen reading.
- `selection_bias` — explain the spurious-correlation hypothesis in
  one clause and why no direct edge was added.
- `iv_validity`, `mediation_intermediate_confounder` — name the
  technical condition and the specific assumption it leans on, then
  invite challenge.
- `reciprocal_causation` — DAG forbids cycles; you picked a
  direction; offer to flip.
- `counterfactual_query`, `mechanism_vs_existence`,
  `cause_attribution`, `individual_vs_population` — these flag *the
  question is outside Themis's current fragment*; describe what was
  answered instead and what the user would need to ask to get the
  actual thing. For `cause_attribution` specifically: when the result
  carries `numeric_estimate.decomposition.proportion_mediated`
  (mediation analysis ran on user-supplied data), surface it
  directly — that **is** the answer to "X 占多少比例 / 是不是因为
  M". Headline: "在你的数据上，M 这条路径承载了 TE 的
  `point*100`%（CI: `ci_lower*100`% — `ci_upper*100`%）" plus the
  must-disclose Pearl-2001 assumptions (already in `explanation`).
  Only when `proportion_mediated` is absent (no mediator query, or
  no data) fall back to "I only validated the path X→Y is in the
  graph (which I myself proposed) — I cannot tell you whether X is
  the *main* or *only* reason for Y; that needs data + a
  decomposition Themis doesn't currently compute." For `counterfactual_query` (only set
  when the translator compressed an L3 individual counterfactual to
  an L2 effect / cause proxy), the headline must say "你问的是'你
  这个人在反事实里会怎样'，我答的是人群在该干预下的平均效应——
  这是答错了一类问题，不是同一个问题的弱版本。要拿到个体反事实
  需要 abduction-action-prediction 三步流程，Themis 当前只在最简单
  的 binary monotone 情形下提供（见 `kind: counterfactual` 直接路径
  会返回 needs_assumption + monotonicity grant request）。"

**Omit** when `extensions.ambiguities` is absent or empty — don't
invent ambiguity. Users hate false alarms.

### 3. LLM-proposal edges

Themis enforces proposal-edge disclosure through two parallel channels:

- **`result.explanation`** — when load-bearing proposal edges exist,
  the kernel populates this field with one ⚠ line per edge. Treat it
  as a must-quote channel: every line in `explanation` surfaces in
  your reply (rephrased into natural prose, not dropped). This is the
  geometric guarantee — the disclosure path doesn't depend on you
  reading the gap report.
- **`data_gap_report.gaps[]`** — same edges also appear as structured
  entries with `kind = "unverified_proposal_edge_on_query_path"`
  (severity `informational`), useful when you need machine-readable
  detail (which edge, which provenance ref).

When proposal edges are load-bearing the structural answer is a replay
of the LLM's own assumption, not Themis's independent verification —
disclosure leads the headline.

For edges that don't appear on the query path (e.g. proposal edges
sitting in the wider DAG, or `bidirected` latent-common-cause
statements which Themis does not yet path-walk), inspect `program`
directly: each `cause` / `bidirected` statement's `annotations.source`
is either `"llm_proposal"` (you hypothesized it) or a concrete
citation like `"PubMed:12345"` (evidence-backed; no special line
needed). Disclose proposal edges in proportion to how much the answer
leans on them.

For `cause` edges:
> "我基于常识提了一条假设边 `running → belly_fat_loss`，这条关系本
> 身还未经证据支持。如果你有相关研究或数据，请补充来源。"

For `bidirected` edges (latent common cause):
> "我假设了一条未观测共因 `smoking ↔ lung_cancer`（两者之间存在你
> 没观测到的共同原因）。这条假设是前门 / IV 识别能成立的关键前提。
> 如果你认为这两者并不共享未观测混杂，告诉我换一种识别策略。"

The reasoning chain stays honest: the user must know when the graph
they're reasoning on is your hypothesis, not established knowledge.

### 4. Investigation requests

`investigation_requests[*].group` keys: `parameter`, `observation`,
`sample`, `structure`, `framing` (slice F1 — variable
operationalization), `assumption` (identification rests on a named
assumption the user must explicitly grant — pairs with
`status == "needs_assumption"`).

Render grouped by `group`, ordered by `priority` (`high` first), and
within each group list `items[*].target` with its `items[*].reason`.

For `framing` items, the `skeleton` carries:

```json
{ "kind": "variable_patch",
  "predicate": "running",
  "existing": {"domain": [true, false]},
  "fields": {"time_window": null, "measurement": null,
             "threshold": null, "observability": null} }
```

For each null field, give a **concrete filled-in example** matching
the predicate's real-world meaning (not generic placeholders):

- `time_window`: e.g. "持续 12 周", "每天", "一年后"
- `measurement`: e.g. "腰围（cm）", "手环里程", "自报告"
- `threshold`: e.g. "≥3 sessions/week", "下降 ≥3 cm"
- `observability`: e.g. "自报告", "医院测量", "可穿戴设备"
- `direction` (slice #41): `"up"` / `"down"` / `"mixed"` — ask when
  "影响 X" could be raise / lower / fluctuate
- `baseline` (slice #41): "pre-intervention clinic BP", "prior
  school-term score" — when the user said 提高 / 下降 without naming
  a reference
- `state_vs_event` (slice #41): `"state"` / `"event"` — when the
  predicate could plausibly be either a habit or an occurrence

**Defer framing detail when blocking gaps exist.** If
`data_gap_report.gaps[]` contains *any* `severity=blocking` item
(e.g. `missing_distribution`, `unidentifiable_no_admissible_set`),
collapse the framing items into a single short note —
"另外 N 个变量缺操作化定义（time_window / measurement / ...），
建议先解决上面的 blocking，后续再回来定义" — instead of itemizing
all 7 fields per variable. Reason: when the user can't even compute
a number, asking them to choose 14+ framing fields is noise that
crowds out the real blocker. Itemize fully only when framing is the
*only* thing left.

For `structure` items, translate any internal references in `reason`
(e.g. `"see PHASE_2_LATENT_CHARTER.md §7"`, `"Phase 2.latent S3.b.1"`)
to plain user-facing language. Strip internal IDs. If a reason is pure
diagnostic noise without user-actionable content, suppress that item.

## Numeric rendering

### From the kernel — `numeric_estimate`

This block appears when the answer came from `themis.estimate(ast,
df)`, not from symbolic Theta.

| Field | Render? |
|---|---|
| `point` | always |
| `ci_lower` / `ci_upper` / `ci_level` | always |
| `method` | name once in plain Chinese |
| `assumptions[]` | list 3–5 most relevant; translate via glossary, keep ID parenthetically |
| `adjustment[]` (backdoor) | name explicitly — essential for transparency |
| `mediators[]` (frontdoor) | name explicitly |
| `instrument` (IV) | name + IV section applies |
| `treatment` / `outcome` | mention once if it helps double-check |
| `formula` | omit unless user asks "how" |
| `sample_size` | parenthetical ("n=2000") |
| `precision_budget.{current_ci_half_width, n_to_halve_ci, hint}` | render only when CI is wide enough that the user might want it tighter — see §"Precision budget" |
| `data_hash` | omit (developer-facing) |
| `estimation_context.data_contract_warnings[]` | non-empty → real issue (missing column / NaN / coercion); always surface |
| `estimation_context.{model_preference, random_state, ci_bootstrap}` | omit unless user asks |

**The point value's meaning depends on `method`** — never dump
`point: -0.069` raw:

| Method | Point semantics | Example phrasing |
|---|---|---|
| `backdoor_logistic` / `frontdoor_logistic` | risk difference (probability) | "服阿司匹林使一年内心脏病发作概率下降约 6.9 个百分点" |
| `backdoor_linear` / `frontdoor_linear` | unit difference in outcome scale | "服药使收缩压平均下降 9.83 个单位（按 outcome 列单位）" |
| `iv_wald` | LATE = local risk difference among compliers | "在 compliers 子人群里，X 让 Y 上升 X.X 个百分点"（point ∈ [-1,1] 时 ×100） |
| `iv_2sls` | linear ATE | "ATE = X.X（线性假设下的人群平均效应）" |
| `mediation_cde` | CDE(m) — direct effect with M held at a specific value; outcome scale | "把 M 固定在 m 时 X 对 Y 的直接效应是 X.X 个单位" |
| `mediation_nde` / `mediation_nie` | natural direct / indirect effect; outcome scale | "经过 M 这条路径贡献的部分是 X.X（NIE）" |
| `mediation_*` (other) | see §"Mediation decomposition" for structural-only cases | (covered there) |
| `joint_backdoor_linear` / `joint_backdoor_logistic` | JOINT effect of intervening on the whole treatment vector at once — see §"Joint interventions" | "同时把 A、B 都设为 1（相对都为 0）让 Y 变化 X.X" |
| `longitudinal_gformula` | effect of a time-varying treatment STRATEGY (always-treat vs never-treat) via the parametric g-formula; the `longitudinal_gformula` block carries the two strategy means and the time-ordered spec | "一直接受治疗（相对一直不治疗）让最终 Y 平均改变 X.X —— 用 g-formula 校正了被既往治疗影响的时变混杂" |
| `longitudinal_ipw_msm` | same time-varying strategy contrast as `longitudinal_gformula`, but via an IPW marginal structural model (models the TREATMENT process instead of the outcome). The `longitudinal_ipw_msm` block carries the per-time MSM coefficients + the weight diagnostics (`weight_mean` should be ≈1 when stabilized; a large `weight_max` warns of a near-positivity violation). If BOTH a g-formula and an IPW-MSM estimate are present, note their agreement as corroboration — they are misspecified differently. | "一直接受治疗（相对一直不治疗）让 Y 平均改变 X.X —— 用 IPW 边际结构模型（校正时变混杂）；与 g-formula 结果相互印证。权重均值≈1、最大值 W 表明重叠尚可" |
| `missing_data_recovery_gformula` | back-door ATE recovered from data that itself has MISSING values (§S9.2). The `recovered_ate` block estimates each g-formula factor from its OWN complete cases — the conditional E[Y\|X,Z] from rows with {Y,X,Z} observed, the marginal P(Z) from rows with {Z} observed — so under MAR it is unbiased where naive listwise deletion is not. Lead with `point`; then contrast `naive_listwise_ate` (the biased complete-case number) to show what the multi-factor recovery corrected. `n_conditional_rows` vs `n_marginal_rows` shows the two factor-specific complete-case sizes. This appears ONLY when identification found the estimand recoverable; otherwise there is a `not_recoverable` `estimator_failure` instead — do not fabricate a number. | "校正缺失后 ATE = X.X（对缺失数据做可恢复性校正：条件与 P(Z) 各用自己的完整样本估计）；若直接删缺失行得 Y.Y —— 那个数在 MAR 下有偏。缺失列：…" |
| `aipw` | doubly-robust ATE (same scale as `backdoor_linear`); consistent if EITHER the outcome OR the propensity model is right — see §"Doubly-robust estimates" | "ATE = X.X（双稳健估计：结局模型或倾向模型任一设定正确即成立）" |
| `tmle` | doubly-robust ATE via targeted substitution (same scale as `backdoor_linear`); like `aipw` but a bounded plug-in — see §"Doubly-robust estimates" | "ATE = X.X（TMLE 双稳健定标估计：结局或倾向任一设定正确即成立）" |
| `ipw_stabilized` / `ipw_ht` | inverse-probability-weighted ATE (same scale as `backdoor_linear`); relies on the propensity model being correct — see §"Doubly-robust estimates" | "ATE = X.X（按倾向得分逆概率加权估计）" |

**Backdoor template**:

> 在你提供的图上，`<treatment>` 对 `<outcome>` 的平均因果效应通过
> **后门调整**识别，调整集 = `<adjustment>`。
>
> 在 N=`<sample_size>` 的数据上估出来：
>
> - 点估计 ATE = **`<point>`**（`<method-specific 解读>`）
> - `<ci_level>` 置信区间：**[`<ci_lower>`, `<ci_upper>`]**（bootstrap）
> - 估计方法：`<method>`
>
> 关键假设：`<列出 conditional_exchangeability / positivity /
> consistency / 模型形式 4 条，给中文释义>`。

**Front-door template**:

> 在你提供的图上，`<treatment>` 对 `<outcome>` 通过**前门调整**识别
> —— 即使 `<treatment>` 和 `<outcome>` 之间存在未观测共因，因为
> `<mediators>` 这条全可观测的中介路径仍可识别。
>
> 在 N=`<sample_size>` 的数据上估出来：
>
> - 点估计 ATE = **`<point>`**（`<解读>`）
> - 置信区间：**[`<ci_lower>`, `<ci_upper>`]**
> - 估计方法：`<method>`
>
> 这种识别依赖：① 中介 `<mediators>` 拦截了 `<treatment>` →
> `<outcome>` 的所有有向路径；② 前门各段后门都已被阻断；③ 一致性。

**IV template** is in §"IV identification" below — it covers both the
structural and the numeric (`iv_wald` / `iv_2sls`) paths.

### Joint interventions (`joint_backdoor_linear` / `joint_backdoor_logistic`)

When the query intervened on a SET of treatments simultaneously
(`do(A=a, B=b, ...)`), `numeric_estimate` carries a `joint_effect` block
(the joint contrast over the whole treatment vector, with the `treated`
/ `control` cells it was taken between) AND an `interaction` block (the
additive-scale treatment×treatment interaction, `scale: "difference"`).
This is NOT two single-treatment effects — the joint contrast and the
interaction cannot be reconstructed from separate single-treatment
queries (a single-treatment ATE averages over the other treatment's
natural distribution; the joint contrast fixes both).

> 同时干预 `<treatments>`（联合后门识别，调整集 = `<adjustment>`）：
>
> - 联合效应 = **`<joint_effect.point>`**（把 `<treated>` 相对
>   `<control>` 一起设定时 `<outcome>` 的变化），
>   `<ci_level>` 区间 [`<joint_effect.ci_lower>`, `<joint_effect.ci_upper>`]
> - 交互作用（加法尺度）= **`<interaction.point>`** —— 两个处理的效应
>   是否可叠加：>0 协同、<0 拮抗、≈0 可加
>
> 关键假设：联合可交换性 / 每个处理组合都有重叠 / 一致性。

### Doubly-robust estimates (`aipw` / `tmle` / `ipw_stabilized` / `ipw_ht`)

These are opt-in alternatives to the g-formula (`backdoor_linear`) for the
SAME backdoor-identified ATE — selected via `options.ate_estimator`. Same
estimand, same outcome scale; what differs is which model must be right
and how the CI is formed.

- **`aipw`** — the *augmented* / doubly-robust estimator. Consistent if
  EITHER the outcome regression OR the propensity model is correctly
  specified (`doubly_robust: true`). Say so — it is the estimator's whole
  selling point (a second line of defence the single-model g-formula and
  IPW don't have). Its CI is analytic: `ci_method: "influence_function"`
  with a reported `std_error` (Wald interval, cluster-robust when
  `inference.cluster_robust` is true), NOT a bootstrap. Render the CI
  plainly; only mention "bootstrap" if `ci_method == "bootstrap"`.
- **`tmle`** — targeted maximum likelihood: also doubly-robust
  (`doubly_robust: true`) and asymptotically equivalent to `aipw`, but a
  *substitution* estimator that targets an initial outcome fit through a
  bounded fluctuation, so it respects the outcome's natural range and is
  steadier when propensity scores approach 0/1. Same analytic
  influence-curve CI as `aipw`. `tmle_epsilon` is the fluctuation
  parameter (a transparency handle; ε≈0 means the initial fit was already
  well-targeted) — you normally don't surface it unless asked to explain
  the method.
- **`ipw_stabilized`** (Hájek, default) / **`ipw_ht`** (Horvitz-Thompson)
  — inverse-probability weighting. Single-robust: relies on the
  propensity model being correct. Do NOT claim double robustness for
  these.

**`propensity_summary` — always surface when overlap is thin.** It
discloses the propensity (treatment-probability) range BEFORE clipping:
`raw_min` / `raw_max`, and `n_trimmed` = how many units had their weight
Winsorized to the `[floor, 1-floor]` band. When `n_trimmed` is more than a
handful (or `raw_min` is near 0 / `raw_max` near 1), tell the user overlap
is thin and the weighted estimate leans on extrapolation for those units —
this is a positivity warning, not a footnote to bury.

> `<treatment>` 对 `<outcome>` 的平均因果效应（后门识别，调整集
> `<adjustment>`），用**双稳健 AIPW** 估计：
>
> - 点估计 ATE = **`<point>`**（结局模型或倾向模型任一设定正确即成立）
> - `<ci_level>` 置信区间 [`<ci_lower>`, `<ci_upper>`]（影响函数解析 SE
>   = `<std_error>`）
> - 重叠情况：倾向得分范围 [`<raw_min>`, `<raw_max>`]，`<n_trimmed>` 个
>   单元被裁剪 —— `<n_trimmed 较大时提示正性偏薄>`

#### Assumption glossary (`assumptions[]` translation)

| ID | Chinese |
|---|---|
| `conditional_exchangeability_given_adjustment_set` | 给定调整集后处理可视为随机分配 |
| `positivity_overlap_of_treatment_arms` | 处理两组在调整集每一层都有人（无极端 propensity） |
| `consistency_of_potential_outcomes` | 一致性：观察到的 Y 等于该处理下的潜在结果 |
| `linear_outcome_regression` | outcome 回归是线性的 |
| `logit_outcome_link` | outcome 用 logit 链接 |
| `iv1_relevance` | IV 与处理相关 |
| `iv2_exclusion_instrument_affects_outcome_only_via_treatment` | IV 只通过处理影响结果 |
| `iv3_independence_instrument_independent_of_unmeasured_confounders` | IV 与未观测混杂独立 |
| `monotonicity_no_defiers` | 单调性：处理对每个个体的方向一致 |
| `frontdoor_full_mediation` | 中介集拦截 X→Y 的所有有向路径 |
| `frontdoor_no_treatment_mediator_backdoor` | X 到中介无未阻断后门 |
| `frontdoor_mediator_outcome_backdoor_blocked_given_treatment` | 给定 X 后中介到 Y 的后门已被阻断 |
| `front_door_criterion_holds_on_graph` | 前门准则在因果图上成立 |
| `estimand_is_LATE_on_compliers_not_population_ATE` | 估计量是 LATE（仅 compliers 子人群），不是人群 ATE |
| `mediator_intercepts_all_directed_paths_from_treatment_to_outcome` | 中介拦截了 X→Y 的所有有向路径 |
| `no_unblocked_backdoor_from_treatment_to_mediator` | X→M 段无未阻断后门 |
| `backdoor_from_mediator_to_outcome_blocked_by_treatment` | 给定 X 后 M→Y 的后门已被阻断 |
| `sequential_ignorability_treatment_and_mediator` | 顺序可忽略性：处理 + 中介都满足条件随机化（Imai 关键假设）|
| `no_intermediate_confounder_affected_by_treatment` | 没有被处理影响的"中间混杂"（即不存在 X 的后代同时影响 M 和 Y）|
| `pearl_2001_four_conditions_hold_on_the_graph` | Pearl 2001 中介分解四条件在因果图上成立 |
| `logit_outcome_regression` | outcome 用 logit 回归 |
| `adjustment_set_blocks_mediator_outcome_backdoor_given_treatment` | 给定 X 后调整集阻断 M→Y 的后门 |
| `doubly_robust_outcome_OR_propensity_model_correct` | 双稳健：结局回归或倾向模型任一设定正确即一致 |
| `tmle_targeted_substitution_estimator` | TMLE：对初始结局拟合做定标的代入估计（有界、近正性违背更稳）|
| `correct_propensity_model_single_robust` | 单稳健：估计一致依赖倾向模型设定正确 |
| `hajek_stabilized_weights` | IPW 用 Hájek 稳定化权重（组内归一，方差更小）|
| `horvitz_thompson_weights` | IPW 用 Horvitz-Thompson 原始权重 |
| `ci_via_analytic_influence_function` | 置信区间由影响函数解析求得（非 bootstrap）|

For IDs not in the table, render the snake_case verbatim.

#### Precision budget (`precision_budget`) — when to surface

`numeric_estimate.precision_budget` is iter 151-155 wiring of VISION
2026-04-26 §"输出 (2)" — "在子群 G 做 RCT n=N 能把 CI 收缩到 ±δ".
It tells the user how much more N is needed to halve the current
95% CI.

- **Backdoor / IV / front-door / transport**: top-level
  `numeric_estimate.precision_budget`.
- **Mediation**: per-component under
  `numeric_estimate.decomposition.{nde,nie,te,proportion_mediated}.precision_budget`.
- **Dose-response**: per-curve-point under
  `numeric_estimate.dose_response_curve[i].precision_budget` (skip
  the reference-row whose CI is degenerate).

**Rendering rule** — three branches:

1. **`relative_width` present and > 0.3**: surface. CI is wide
   relative to the point. Tell the user what `n_to_halve_ci`
   buys them.
2. **`relative_width` present and ≤ 0.3**: don't surface unsolicited.
   The estimate is precise enough that "more data" isn't the
   bottleneck; recommending more N would be noise.
3. **`relative_width` absent** (point ≈ 0, division undefined):
   surface IFF the CI brackets zero (`ci_lower ≤ 0 ≤ ci_upper`).
   When the effect is statistically null AND the user is reading
   the result as "no effect", `n_to_halve_ci` is the right
   diagnostic — it tells them whether more data could distinguish
   true null from underpowered. If the CI is tight on one side of
   zero (e.g. `ci_lower=0.01, ci_upper=0.03`), don't surface — the
   non-null is already statistically clear.

**Override**: if the user explicitly asks "how much data would I
need to be sure?", surface regardless of branch.

**Surface format**:

> （目前样本 n=`<sample_size>`，95% CI ±`<half_width>`。如果你想把
> CI 收紧一半（±`<half_width/2>`），SE 按 1/√N 缩放需要 ≈
> **n=`<n_to_halve_ci>`**——大约 4× 现有样本量。）

Don't over-rely on the helper's own hint string — render in the
user's domain language. Mention the SE 1/√N scaling once if the
user seems numerate; skip it for casual askers.

Don't surface a precision_budget when the answer isn't a point
estimate (e.g. structurally unidentifiable, bounds-only). The field
won't be there in those cases anyway.

**Method-specific caveats** — `n_to_halve_ci` is the formal SE
scaling number, but what "more N" *means* depends on `method`:

- `iv_wald` / `iv_2sls`: the estimand is LATE on **compliers** (or
  the linear-2SLS analog). "More N" only buys precision if you
  recruit more compliers — i.e. units whose treatment status is
  actually moved by the instrument. Recruiting always-takers /
  never-takers does nothing for SE on this estimand. Surface this
  when the user is planning a study, not just when reading a result.
- `mediation_*`: "more N" must include both M and Y measurements;
  recruiting more rows with X but no M defeats the purpose.
- `frontdoor_*`: more N must include both M and Y on the same units;
  mediator-outcome chain is what drives precision.
- `transport_post_stratification`: precision is bottlenecked by the
  WORST stratum's source-N, not total N. Suggest enriching the
  thinnest stratum, not blanket recruitment.
- `dose_response_*`: each curve point has its own
  `precision_budget`; "more N" needs to be allocated across sampling
  points (typically equal per point).
- `backdoor_*`: straightforward — "more N" means more rows of
  (X, Y, Z) jointly. No subgroup caveat.

### From literature — outside the kernel (Phase 11.1)

When a number comes from WebSearch / KB lookups (gap_to_action.md
flow) and was **not** patched into Themis (typically because of dtype
mismatch — see §"Schema mismatch"), the kernel-numeric template
doesn't apply: that number was neither produced by `themis.estimate`
nor verified by any kernel rule.

Use this template instead:

```
基于 {study type, e.g. 2023 meta-analysis / 2019 RCT}（{population}, n={n}），
{intervention} 对 {outcome} 的人群平均效应：

- {effect}: {point} {unit} ({CI / IQR})
- 起效时间 / 剂量响应: {if reported}

引用: {PMID / DOI}
```

**Three caveats are mandatory** for every literature-derived number:

1. **Population**: source population vs user. Even if "looks similar",
   flag the gap. Reuse §"Transport identification" framing if it
   applies.
2. **ATE vs ITE**: literature gives **population means**; the user's
   individual response can differ substantially. Add: "对你这一类人群
   的平均效应是 X，但你个人可能多 / 少甚至没反应"
3. **Schema mismatch (if the patch was skipped because of dtype)**:
   say so, and add: "因此这个数字没有进入 Themis 的可验证推导链 —
   它是引用，不是推算"

Each literature number stands on its own citation: when two studies
both apply, surface them as separate references — combining their
point estimates is amateur meta-analysis and breaks the audit chain.

## Domain-specific patterns

### IV identification (Phase 6.iv / Phase 7.3)

**Trigger**: any of —
- `extensions.iv_identification` is present (structural identify path)
- `numeric_estimate.method ∈ {"iv_wald", "iv_2sls"}` (numeric path;
  pull `instrument` / `conditioning` / `assumptions` from
  `numeric_estimate`)

When IV is in play, identification fell back to it after backdoor and
front-door both failed. Three things follow that the rendering must
make explicit:

1. The user's graph has **at least one unobserved X-Y confounder**
   (that's why backdoor failed)
2. The system found an **instrument** satisfying IV1/IV2/IV3
3. **Identification only establishes existence** — the numeric answer
   needs an additional estimation-layer assumption that the structural
   layer doesn't pick

Template:

> 我通过工具变量 `<instrument>` 识别了这条因果效应 —— 即使 `<X>`
> 和 `<Y>` 之间有未观测共因，这条因果量在结构上仍可识别。
>
> 但是要给出具体数字，**还需要补充一个估计层假设**。可选之一：
>
> - **单调性（monotonicity）** —— 假设 `<instrument>` 对 `<X>` 的
>   影响方向一致（不会"有的人反向"），得到 LATE（局部平均处理效应）
> - **线性性（linearity）** —— 假设效应是线性的，可以用 2SLS
>   得到 ATE（平均处理效应）
>
> 你倾向哪个假设？或者这两个都不合适？

Pull from `extensions.iv_identification` (structural) or
`numeric_estimate` (numeric):
- `instrument` — name it
- `conditioning` — if non-empty, mention "给定 `<conditioning>` 之后"
  (conditional IV)
- `required_assumption` (structural) / `assumptions[]` (numeric) —
  translate IV1/IV2/IV3 + monotonicity inline; quote the IDs once
  so the user can refer back
- `alternatives_count` (structural) — if > 1, mention "还有 N-1 个
  其他工具变量候选可选"
- numeric path: `iv_wald` → "Wald 比率估计 → LATE";
  `iv_2sls` → "2SLS → ATE 假设线性性"

If A1 also emitted `extensions.ambiguities[kind=iv_validity]`, the
ambiguity disclosure block will surface that aspect — don't double-
render. The IV section focuses on *what the answer is*; the ambiguity
section focuses on *what could go wrong*.

### Mediation decomposition (Phase 6.mediation / Phase 7.4)

When `extensions.mediation_decomposition` is present, the query asked
for an effect decomposition through a mediator. The numeric path
(``numeric_estimate.method ∈ {"mediation_linear_imai",
"mediation_logit_imai"}``) wraps statsmodels' Imai 2010 algorithms
1+2 for natural direct / indirect / total effects.

Identifiability is a property of the graph: "可识别" means the graph
permits decomposition under the declared assumptions, not that the
mediator factually mediates the effect — the rendering stays
structural, not existential. When `numeric_estimate` is also present
(mediation went through `themis.estimate`), render numbers the same
way as the backdoor / front-door numeric templates: point + CI +
method + assumptions translated via the glossary. No parallel
mediation-numeric template lives below — reuse the §"Numeric
rendering" shape.

`strategy` field branches:

- `nde_nie` — best case. Both natural direct/indirect and CDE
  identifiable. Report TE = NDE + NIE and name the adjustment set.
- `cde` — partial. NDE/NIE not identifiable (usually M4: intermediate
  confounder), CDE(m) is. "I can tell you what happens if M is held
  at a specific value, but I can't cleanly separate direct from
  indirect under the natural M distribution."
- `none` — not identifiable via backdoor methods. Report which
  condition failed (`nde_nie.failed_condition` / `cde.failed_condition`)
  and explain what that means in plain terms.
- `mediator_valid: false` — structural error: M isn't on any
  X → ... → M → ... → Y path. Ask the user to verify the mediator
  declaration or the edge list.

**Template — `nde_nie` success (structural only)**:

Use this when `extensions.mediation_decomposition.strategy == "nde_nie"`
AND `numeric_estimate` is **absent**. With `numeric_estimate` present,
follow §"Numeric rendering" instead — Imai-specific assumptions live
in the glossary.

The structural decomposition's `nde_nie.assumptions` list names the
cross-world conditions identifiability rests on. Translate them via
the glossary into the assumption block — "可识别" without the
assumption block reads as unconditional, which is wrong: structural
identification is always *conditional on* these holding.

> 关于 `<X>` 通过 `<M>` 对 `<Y>` 的影响分解：
>
> - **总效应 TE**：`<X>` 改变对 `<Y>` 的全部影响
> - **自然间接效应 NIE**：通过 `<M>` 这条路径贡献的部分
> - **自然直接效应 NDE**：不经过 `<M>` 的部分
>
> 在你的图上这个分解**可以识别**（需要调整 `<adjustment>`）。具体
> 数字需要 Phase 7 估计层 —— 目前只给出"结构上可分解"的判断。
>
> 这个判断的前提（任一不成立就不可信）：
> - `<assumptions[*] 按 glossary 翻译，每条一行>`

**Template — `cde` fallback**:

> 这个问题的**完整分解（NDE + NIE）不可识别** —— 原因是
> `<failed_condition>`（通常是中间混杂器问题：有变量既被 `<X>`
> 影响、又影响 `<M>` 和 `<Y>`）。
>
> 但是**控制直接效应 CDE** 还是可以算：把 `<M>` 强制固定在某个值，
> `<X>` 对 `<Y>` 的剩余影响是多少。
>
> 如果你只关心"把 M 按某水平时 X 的直接作用"，用 CDE；如果一定
> 要"M 自然变化下的直接/间接分解"，这个图结构上识别不了，需要
> 换图或者引入更强工具（Phase 7+ g-formula）。

**Template — `none`**:

> 对不起，这个图上 `<X>` 对 `<Y>` 通过 `<M>` 的效应**连 CDE 都不
> 可识别**：`<failed_condition>` 违反了。具体来说：`<which backdoor
> is open, in plain words>`。
>
> 可能的解决方向：
> - 观察更多混杂变量（可能解决 `<C1>` / `<M1>` 问题）
> - 换一个合理的 mediator
> - 或者承认这个因果量在当前信息下不可回答

Failed-condition codes → plain explanation:

| Code | Plain explanation |
|---|---|
| M1 | 有未观测 / 未调整的 X-Y 混杂 |
| M2 | 有未观测 / 未调整的 X-M 混杂 |
| M3 | 有未观测 / 未调整的 M-Y 混杂（给定 X 下） |
| M4 | 有中间混杂器（X 的后代同时影响 M 和 Y），经典 recanting witness |
| C1 | 无法阻断 (X, M) 到 Y 的所有后门 |
| C2 | 唯一能阻断后门的变量是 X 或 M 的后代（不允许调整） |

### Transport identification (Phase 9 §T9.1)

When `result.extensions.transport_identification` is present, the
query asked about a target population that differs from the source of
evidence (Bareinboim & Pearl 2014).

§T9.1 deliberately does NOT give a number — only structural
identification + the formula. Numeric estimation lands in §T9.2. The
reply must reflect this honestly: surface the formula + name the data
that would be needed.

Field map: `source_population`, `target_population`, `s_nodes[]`
(variables differing across populations), `adjustment_set[]` (the Z
that must be conditioned on), `formula_repr`.

Status semantics:
- `structurally_solved` + `value=true` → the source effect IS
  transportable to the target; numbers come later
- `needs_investigation` with a `structure`-group missing item → no
  S-admissible Z exists under the declared selection diagram

**Template — identifiable**:

> 你这个问题需要做**跨人群转移识别**（源人群 `<source>` → 目标
> `<target>`）。
>
> 在你声明的差异变量（`<s_nodes>`）下，转移**结构上可识别** ——
> 调整集 = `<adjustment_set>`。
>
> 转移公式：
>
> ```
> <formula_repr>
> ```
>
> 也就是说要把源人群的效应"按调整集分层后再用目标人群的边际分布
> 重新加权"。
>
> **要给具体数字，还需要两类数据**：
>
> 1. **源人群的分层条件概率** `P(<outcome> | do(<treatment>),
>    <adjustment_set>)` —— meta-analysis 通常只汇总（一个数字），
>    分层数据需要原始 RCT 的 IPD 或 subgroup 表。**这一项往往是
>    真正的瓶颈**。
> 2. **目标人群的协变量边缘分布** `P*(<adjustment_set>)` —— 用户
>    自报或查公开数据库（NHANES / 国家统计）。
>
> Phase 9 §T9.1 只到结构识别这一层；数字落地是 §T9.2 (IPSW /
> TMLE-transport)。

**Template — unidentifiable**:

> 你声明的选择图下，这个跨人群效应**结构上不可识别** ——
> `<failure_reason>`。
>
> 解决方向：
> 1. **观察更多变量进入 Z**：拿到目标人群分布的变量加入
> 2. **缩小 S 节点集合**：去掉确实不影响 outcome 的 shift
> 3. **承认无法回答**：可能需要更接近目标人群的研究

**Special case** — `s_nodes` empty (no declared shifts) but
`target_population` set: formula reduces to identity. Surface as:

> 你的目标人群和源人群在这次问题里**没有声明的分布差异** —— 所以
> 源效应可以直接转移。如果实际上有差异（年龄 / 性别 / 体重）你想
> 纳入考虑，告诉我，我会加上对应的 selection_node。

**Caveats always include**:

§T9.1's output is *data requirements*, not a corrected number — source-
population point estimates do not transfer directly to the target
(F25 failure mode core).

Plus the context-specific caveats:
- 如果 program 有 `unobserved_population_shift` ambiguity → 提醒用户
  §T9.1 只处理观察到的 S；未观测差异是 §T9.3 范围
- 如果用户原始问题给了一个源人群数字（"RCT 说 X cm 下降"）→ 明确
  说 transport 不会输出"修正后的 X" —— 只会告诉你需要哪些数据来算

### Selection-bias recovery (Phase 9 §S9.1)

`result.extensions.selection_recovery` is the **constructive companion**
to the `selection_on_collider_opens_path` gap. That gap says *"your
sample is restricted on a collider → biased"*; this block answers the
next question: *can the unbiased P(y|do(x)) be recovered from the biased
sample, and how?* (Bareinboim-Pearl selection-backdoor criterion.) When
both are present, render the gap's warning first, then this verdict — the
gap is the diagnosis, this is the prognosis.

Like §T9.1 it is **structural only** — it hands back a recovery *formula*
and a *data ledger*, never a number. Do not present `recovery_formula` as
an answer; present it as "here is what would recover it, and what it costs".

Read `recoverable` first, then branch on it:

- **`recoverable: true`** — the effect is s-recoverable via the
  selection-backdoor set `adjustment_set` (partitioned into `z_plus`,
  confounding control, and `z_minus`, selection control). Surface the
  `recovery_formula`, and — critically — the `external_data_needed`
  ledger: an **empty** ledger means it is recoverable from the biased
  data *alone* (the good case); a **non-empty** ledger names the
  unbiased/population distributions the analyst must obtain externally
  (the price of recovery). The ledger is the honest bottleneck — lead
  with it, don't bury it.

- **`recoverable: false`** — surface `failure_reason`, and state the
  boundary honestly: this means *not recoverable via selection-backdoor
  adjustment*, **not** a proof that no recovery exists. The complete
  recovery algorithm is out of scope; inverse-probability-of-selection
  weighting (already named in the gap's `alternative_paths`) or richer
  external data may still work. Never overclaim "impossible".

The canonical Hernán-2004 collider (selection driven directly by the
outcome) lands here as `recoverable: false` — that is the *structural
confirmation* of Hernán's own point ("no covariate adjustment closes the
path"), so say so: the kernel independently re-derived what the paper
asserts.

### Missing-data recovery (Phase 9 §S9.2)

`result.extensions.missing_data_recovery` appears when the program
declares a missingness mechanism (`missingness_indicator` statements) —
i.e. some variables are sometimes *missing*, not just conditioned on.
Missing data is a different failure from selection bias: selection
conditions on one event S=1; missingness conditions on a *set* of
response events R=0 (one per partially-observed variable), recovered
*factor by factor* (Mohan-Pearl-Tian). Structural only — a recovery
formula and a mechanism label, never a number.

Two things to surface, in order:

1. **`mechanism`** — MCAR / MAR / MNAR, read straight off the m-graph.
   This is high-value on its own: people routinely *assert* MAR to justify
   a method (multiple imputation, complete-case) without checking it. The
   kernel derives it structurally from the declared mechanism, so state it
   plainly — and if it is **MNAR**, say that the usual MAR-based fixes are
   not licensed here.

2. **`estimand.recoverable`** — the HEADLINE verdict for the full causal
   effect `P(Y | do(X)) = Σ_z P(Y|X,Z)·P(Z)`. The interventional
   distribution is a *product* of two manifest factors, so it is
   recoverable iff BOTH are: the adjusted conditional (top-level
   `recoverable` / `recovery_formula`, e.g. `P(y|x,z)`) AND the covariate
   marginal `covariate_recovery` (`P(z)`; `null` when no adjustment is
   needed). Lead with `estimand.recoverable` and `estimand.recovery_formula`
   (`… = Σ_z P(y|x,z,R=0)·P(z)`); the two sub-verdicts are the *why*.
   - **conditional true, covariate false** — the striking multi-factor
     case: an **MNAR** self-masking *confounder* (Z→R_Z) can leave the
     conditional `P(Y|X,Z)` perfectly recoverable yet make `P(Z)` — and
     therefore the whole effect — unrecoverable. Don't let a green
     conditional imply a recoverable effect; the marginal is the gate.
   - **true** — the `R_·=0` factors say each factor is a *complete-case*
     computation. Note too that an MNAR mechanism can still yield a
     recoverable conditional (conditioning on the missingness driver blocks
     the target from its R) — MNAR is not automatically hopeless.
   - **false** — surface `estimand.failure_reason`, and keep the same
     honesty as §S9.1: "not recoverable via ordered factorization", **not**
     a proof of impossibility. The canonical obstruction is **self-masking**
     (a variable's own value drives its missingness, V→R_V).

When data is supplied (`themis.estimate`), the recoverable estimand is
carried through to a NUMBER — see the `missing_data_recovery_gformula`
numeric row below; when it is *not* recoverable the estimator refuses (a
`not_recoverable` `estimator_failure`), never inventing a figure.

### Transport numeric — Phase 9 §T9.2 / iter 128

When `numeric_estimate.method == "transport_post_stratification"`,
Themis ran the iter 128 numeric companion to §T9.1's structural
identification. Method: post-stratification (Cole & Stuart 2010 §3) —
``ATE_target = Σ_z P(z|target) · ATE_source(z)`` where each stratum
ATE comes from observed source data and is reweighted by the target
marginal supplied via ``program.extensions.target_marginal``.

Field map: standard ``point`` / ``ci_lower`` / ``ci_upper`` /
``ci_level`` / ``adjustment`` (the Z stratum variable, single-Z
in v1). Plus the four assumptions in ``assumptions``:

- ``s_admissibility_of_adjustment_set`` — Bareinboim-Pearl's
  identification precondition; this is what §T9.1 already verified
- ``no_treatment_effect_modification_outside_z_in_either_pop`` —
  the post-stratification step assumes effect heterogeneity is
  captured ENTIRELY by the Z stratum
- ``consistency_of_potential_outcomes``
- ``positivity_in_each_z_stratum_of_source`` — every Z value in the
  target must appear in source data with both treatment arms

Template:

> 转移到 `<target_population>` 后的效应估计是 **`<point>` (95% CI
> [`<ci_lower>`, `<ci_upper>`])**。计算用 Cole & Stuart 2010 §3
> post-stratification：先在源人群按 `<adjustment>` 分层算每层
> ATE_source(z)，再用目标人群的 P(`<adjustment>`) 边际加权求和。
>
> **关键假设**：(1) `<adjustment>` 是 S-admissible (Phase 9 §T9.1
> 已验证)；(2) 效应异质性完全被 `<adjustment>` 捕获 —— 即同一
> `<adjustment>` 子层内，源和目标人群的处理效应一致；(3) consistency；
> (4) 源数据每个 `<adjustment>` 子层都有处理 / 对照样本（positivity）。
>
> 第 (2) 条是这个估计**不可被 §T9.1 验证**的假设：identification
> 给出公式形态，post-stratification 把它落地为数字时引入了"effect
> modification 不超出 Z"的额外承诺。如果用户怀疑还有其他效应修饰
> 因素（年龄段 × 处理 × 子人群），点估计会偏。

When ``adjustment`` has more than one variable (currently impossible
since §T9.2 is single-Z scope), ``estimate_transport`` raises
``NotImplementedError`` and dispatch leaves the structural
identification result intact.

### Dose-response curve — Phase 14

When ``numeric_estimate.method`` matches one of ``dose_response_linear_dml``
/ ``dose_response_causal_forest_dml`` / ``dose_response_linear_drlearner``,
Themis fitted a dose-response curve over the user-supplied (or
program-derived) sampling points. Method differences:

- ``dose_response_linear_dml`` — EconML LinearDML; treats outcome
  model as linear in confounders. Default for unflagged dose-response.
- ``dose_response_causal_forest_dml`` — non-parametric forest;
  opt-in via ``options={"model": "forest"}`` for heterogeneous
  effects across covariate space.
- ``dose_response_linear_drlearner`` — doubly-robust linear
  meta-learner; opt-in via ``options={"model": "drlearner"}``;
  more robust to outcome-model misspecification when propensity
  is well-fit.

Field map: ``sampling_points`` (T values evaluated; sorted ascending;
first is reference), ``reference_point`` (smallest sampling_point;
effect=0 by construction), ``dose_response_curve`` (list of {x,
effect, ci_lower, ci_upper}), plus standard ``method`` /
``assumptions`` / ``data_hash``.

Template:

> 在 `<treatment>` 取 `<reference_point>` 为参照下，目标 `<outcome>`
> 的 dose-response 曲线（`<method>`）：
>
> | T = | 效应（vs 参照）| 95% CI |
> |---|---|---|
> | `<x_1>` | `<effect_1>` | [`<ci_lower_1>`, `<ci_upper_1>`] |
> | ... | ... | ... |
>
> 假设：`<assumptions translated via glossary>`。曲线形状告诉你的不
> 是单点效应而是 dose-response 形态 —— 是单调的吗？阈值在哪？平台
> 在哪？把这些问题指回给用户。

When `extensions.assumption_ledger` is present it is the **single lead
surface** for everything the answer takes on faith — render its
`assumptions[]` before the table, top-down in the given order (already
sorted by severity, so `invalidating` entries come first). Lead with
the `invalidating` ones: if any is false the number is not a causal
effect at all — that outranks any `distorting` shape concern. Each
entry carries `layer` / `provenance` / `severity` / `testable`; name
the provenance (识别层固有 / 上游 LLM 提的边 / LLM prior / 估计器默认
形式) so the user knows whom to challenge, and say which are testable
(form → switch estimator; edge → needs evidence) vs untestable by
design (identification). The ledger already folds in the LLM-proposed
edges, theta priors, and functional form, so do NOT separately
re-render `llm_proposed_review` / `mechanism_audit` when the ledger is
present — that double-counts.

When the ledger is absent but `extensions.mechanism_audit` is present,
fall back to surfacing it directly: its `summary` leads the numeric
reply. The functional form (`mechanisms[].form`) is the curve's *shape*
assumption — the estimate is correct *given* that form, but the form
itself was assumed (`provenance: default` = auto-selected by sample
size), not measured. Disclose it as load-bearing, then ask whether the
assumed shape fits — never present the curve as if its shape were
established by the data alone.

If ``estimator_fallback`` is present (binary treatment fell back to
binary effect — Phase 14 slice a behaviour), surface the fallback
rationale: "用户问 dose-response 但 `<treatment>` 是二值；改用 binary
ATE 估计 ... 如果你想要 dose-response 形态的回答，需要把 `<treatment>`
变成多级或连续值。"

### Sensitivity (E-value) — Phase 8.2 / iter 124

Fires when `numeric_estimate.sensitivity_analysis` is present. Two
conversion paths to risk-ratio scale:

- **Binary outcome** (Phase 8.2): RR via observed baseline rate.
  ``baseline_rate`` is set; ``note`` describes "RR = (baseline +
  ATE) / baseline".
- **Continuous outcome** (iter 124, Chinn 2000): standardised mean
  difference d = ATE / SD(Y), then RR ≈ exp(0.91 · d). ``baseline_rate``
  is **null** on this path; ``note`` mentions "Chinn 2000" + the SMD
  value + "approximation note: ... assumes within-group SDs ≈ equal".

Surface either as a **robustness statement**, not a p-value
substitute. The E-value answers: "how strong would an unmeasured
confounder have to be — on both treatment and outcome — to explain
this away?"

Field map: `e_value`, `e_value_ci_bound` (E-value on the CI bound
nearer the null; more conservative), `risk_ratio`, `baseline_rate`,
`note` (one-line interpretation already includes the threshold
category).

Plain-language thresholds (already encoded in `note`):

| E-value | Meaning |
|---|---|
| < 1.5 | 很脆弱 —— 稍微一点未观测混杂就能推翻结论 |
| 1.5–2.5 | 中等强度 —— 需要一个中等水平的混杂才能解释掉 |
| 2.5–5 | 比较稳健 —— 混杂得相当强才能颠覆 |
| ≥ 5 | 非常稳健 —— 除非有不可思议地强的混杂，否则结论站得住 |

Template:

> 这个估计的 **E-value = `<e_value>`**，意思是要让这个数字"消失"，
> 必须存在一个未观测的混杂因素，它对 `<treatment>` 和 `<outcome>`
> 的关联强度（用风险比衡量）都至少是 `<e_value>` 倍。
>
> 你的 95% 置信区间靠近零的那一头，对应的 E-value 是
> `<e_value_ci_bound>` —— 也就是说连 CI 边缘都需要这么强的混杂才
> 能推翻。
>
> `<note 里的 interpretation>`。

When E-value is null (continuous outcome / baseline at boundary /
implied treated rate outside [0,1]):

> 这个估计目前没附 E-value。原因：`<note>`。如果你需要稳健性指标，
> 可以考虑把 outcome 二值化（按某阈值），或用其他敏感性方法
> （如 Rosenbaum bounds）。

For continuous outcomes (iter 124) the Chinn-converted E-value is
attached automatically. ``baseline_rate=null`` is the signal — render
with the SMD-approximation caveat:

> 这个估计的 **E-value ≈ `<e_value>`**（连续 outcome；用 Chinn 2000
> 的 SMD→RR 近似，d = ATE/SD ≈ `<smd from note>`）。意思和 binary
> 路径一样：要让这个数推翻，需要一个未观测混杂在 `<treatment>` 和
> `<outcome>` 上都至少有 `<e_value>` 倍的关联。
>
> **近似注意**：Chinn 转换假设组内 SD 大致相等且 outcome 大致 log-
> normal —— 流行病学常用经验法则，不是紧界。如果 SD 在两组差异显著
> 或 outcome 显著偏态，E-value 解读应保守。

### OVB sensitivity (Cinelli-Hazlett) — robustness value

Fires when `numeric_estimate.ovb_sensitivity` is present (attached to
`backdoor_linear` estimates). This is the **regression-scale** companion
to the E-value: instead of a risk ratio it speaks in **partial R²** —
the fraction of residual variance a confounder would explain. Surface it
as a robustness statement, never a p-value substitute.

Key fields:
- `robustness_value_q` (RV_q): the confounding strength — a partial R²
  the confounder must share with BOTH treatment and outcome — needed to
  **explain the effect away entirely** (reduce it 100%). RV near 1 ⇒ very
  robust; near 0 ⇒ fragile. Report as a percentage.
- `robustness_value_qa` (RV_{q,α}): the (smaller) strength needed to also
  make the result **statistically insignificant** at `alpha`.
- `partial_r2`: how much of the residual outcome variance the treatment
  itself explains — the natural yardstick to compare RV against.
- `benchmarks[]`: the interpretable handle. Each entry is an observed
  covariate; `adjusted_estimate` is what the effect becomes under a
  confounder `kd`/`ky` times as strongly associated as that covariate.
  `valid=false` (adjusted_* null) means the covariate is too strong to
  serve as a benchmark — say so, don't drop it silently.

> 敏感性（未观测混杂需要多强才能推翻）：**稳健值 RV = `<robustness_value_q>`
> （×100 变百分比）** —— 一个未观测混杂要把这个效应完全解释掉，得同时
> 解释掉处理和结局各约这么多比例的残差方差。作为对照，处理本身只解释了
> 结局残差方差的 `<partial_r2×100>`%。
>
> 要让结果连显著性都失去，只需 RV_{q,α} = `<robustness_value_qa>`。
>
> 用已观测协变量作基准：一个和 `<benchmark.covariate>` 一样强的混杂，会把
> 估计从 `<estimate>` 变到 **`<benchmark.adjusted_estimate>`**（仍`<>0 则同向>`）。
> `<若 valid=false：这个协变量太强，无法作为有效基准>`

### Schema mismatch

When the kernel_ast variable declares `domain: [true, false]` but the
estimator picked a continuous-outcome method
(`numeric_estimate.method ∈ {"backdoor_linear", "frontdoor_linear"}`)
OR the point estimate is clearly outside [-1, 1], the declared domain
disagrees with the data's actual dtype.

Themis "data wins" — the estimate is correct. Surface this as a
one-line note:

> ⚠ 注意：`<variable>` 在你的图描述里被声明为 bool，但底层数据
> 是连续值（点估计 `<point>` 在 `<method>` 下显然是连续量级的）。
> 这次按数据连续来算了；如果你想把 `<variable>` 二值化，告诉我
> 阈值我重跑。

## Bounds rendering (Phase 12)

When `result.bounds_result` is set, point identification failed but
Themis computed information-preserving bounds instead. The validator
tried to give *something* useful rather than just refuse. Surface
this prominently — if the user's `data_gap_report` mentions
"接受 Balke-Pearl bounds" as an alternative_path, the bounds_result
**is** that interval (no need to send the user looking).

### Placement

Bounds come **right after the headline answer**, alongside (not
inside) the data_gap_report block. Order:

1. Headline: "点估计算不出，但区间答案可以给"
2. Bounds block (this section)
3. Data gap report (now reframed as "to upgrade from interval to
   point, you'd need...")
4. Other channels (ambiguity, edge provenance)

When `bounds_result` is null AND the gap report's alternative_paths
mention bounds, surface the gap report's text verbatim (the bounds
weren't computed — explain in the data gap section, not pretend
they were).

### Field map

| Field | Render |
|---|---|
| `method` | name once: "Manski 自然界限" / "Balke-Pearl 工具变量界限" |
| `lower_expression` / `upper_expression` | symbolic — show as code block; the user / their analyst evaluates against data |
| `assumptions` | translate via the assumption glossary (Manski natural: "无假设"; BP: lists IV1/IV2/IV3) |
| `data_required` | name the observable distribution(s) the analyst must supply |
| `width_when_uninformative` | when True, prepend warning that bounds are trivial |
| `notes` | quote verbatim — generator-curated context |

### Per-method shape

#### `manski_natural` (no assumptions)

> 这个效应的点估计在你给的图上算不出（缺关键数据 / 不可识别），但
> **不需要任何额外假设**就能给一个区间答案 ——
>
> **Manski 自然界限**：
>
> ```
> P({target} | do({intervention})) ∈
>     [ {lower_expression}, {upper_expression} ]
> ```
>
> 计算只需要观察到的 `{data_required}`。
>
> **解读**：区间宽度 = P({intervention} 的另一个值) —— 治疗组之外
> 的人群对这条干预我们没有信息，区间宽度反映了这部分的不确定。
> 想缩窄就要么扩大覆盖率（让另一组也有人受治疗），要么接受额外
> 假设（如 monotonicity）。

#### `balke_pearl_iv` (requires IV1/IV2/IV3)

> 你的图里有一个工具变量 `{instrument}`（满足 IV1/IV2/IV3 时），
> 这让我可以用 **Balke-Pearl 工具变量界限**（1997）给一个比 Manski
> 自然界限更窄的区间 —— 但这次界的是 **平均因果效应 ACE**：
>
> ```
> ACE = E[{target} | do({intervention}=1)] - E[{target} | do({intervention}=0)]
> ACE ∈ [ {lower_expression}, {upper_expression} ]
> ```
>
> 计算只需要观察到的 `{data_required}`（8 个概率，二值三元组）。
>
> **关键假设**：
> - IV1: 工具变量 `{instrument}` 与处理 `{intervention}` 相关
> - IV2: 工具变量只通过处理影响结果（exclusion restriction）
> - IV3: 工具变量与未观测混杂独立
>
> 如果这三条哪条你有疑问 —— 比如 `{instrument}` 真的不直接影响
> `{target}` 吗？—— 告诉我，我可以退回 Manski 自然界限（更宽但不
> 需要 IV 假设）。

#### `manski_tamer_monotonicity` (requires user-asserted MTR)

> 你已经声明了**单调治疗反应（MTR）假设**：处理对每个个体的方向
> 一致——`{target}` 不会因为接受 `{intervention}` 而变差（或不会
> 变好，取决于声明方向）。在这条假设下，可以收紧 Manski 自然界限
> 的**一边**到观察到的边际：
>
> ```
> P({target} | do({intervention})) ∈
>     [ {lower_expression}, {upper_expression} ]
> ```
>
> 计算只需要观察到的 `{data_required}`。
>
> **关键假设**：MTR——治疗对结果的方向是一致的；个体之间的反应
> 大小可以不同，但符号方向不可逆转。
>
> **直觉**：MTR 让"未受处理那一组的反事实"在数据中找到了下/上界
>  的来源——观察到 X=¬x 时的 Y 实际就是该组在 do(X=¬x) 下的潜在
> 结果，MTR 把它和 do(X=x) 下的潜在结果用方向不等式联系起来。
>
> **何时考虑放弃这条假设**：如果你怀疑某些子群对处理反应方向相反
> （效应异质性 with sign reversal），MTR 不成立——告诉我，我可以
> 退回 Manski 自然界限（更宽但不需要 MTR 假设）。

### When the bounds are uninformative

If `width_when_uninformative` is True OR you can see lower/upper
collapse to the trivial range (e.g. [0, 1] for probabilities,
[-1, 1] for ACE), be honest:

> 严格来说界限存在 —— `[{lower}, {upper}]` —— 但实际上覆盖了整个
> 可能范围，这等于"不知道"。这种情况下**界限本身没有信息**，要
> 真的得出有用区间需要：
> - 更多观察（增加另一组的覆盖率）
> - 接受 monotonicity（处理对每个个体的方向一致）
> - 找一个有效的 IV（如果当前没有）

### Cross-reference with data_gap_report

When both `bounds_result` and `data_gap_report` are present, the
gap report's `alternative_paths` text "接受 Balke-Pearl bounds 给
区间答案" is now backed by an actual interval (the bounds_result
above). Phrase the gap section as:

> 上面已经给了区间答案 — 要从区间升级到点估计，你需要补：
> - {gap.required_data.data_type} 形式的 {gap.required_data.variables}
> - n ≥ {gap.required_data.min_sample_size}（{precision_target}）

The gap section references the upgrade requirement only — the bounds
expression itself was rendered above and isn't repeated here.

### Render decision

- `bounds_result` null → omit the section entirely.
- `status == "numerically_solved"` and bounds_result also set → render
  the point as the answer with a one-line tail ("bounds also computed:
  [a, b]").
- `query_kind != effect` → `bounds_result` should already be null;
  if it's set, treat as an upstream bug and skip.

## Worked example (end-to-end)

Given:

```json
{
  "status": "needs_investigation",
  "query_kind": "effect",
  "investigation_requests": [
    {"action": "validate_parameter", "priority": "high", "group": "parameter",
     "items": [{"target": "parameter:P(belly_fat_loss=True|running=True)",
                "reason": "Theta 中缺条目 ..."}]},
    {"action": "define_variable", "priority": "medium", "group": "framing",
     "items": [
       {"target": "belly_fat_loss", "skeleton": {...}, "reason": "..."},
       {"target": "running", "skeleton": {...}, "reason": "..."}
     ]}
  ]
}
```

A good Chinese reply:

> 这个问题我暂时还不能直接给答案。
>
> 从你的问法，我把它转成一条干预因果查询：
> **在你每天跑步（`do(running=true)`）的前提下，是否瘦肚子（`belly_fat_loss=true`）？**
>
> 还差两类信息：
>
> **① 两个变量还没"操作化"（优先度 中）**
> - **running**：缺 `time_window / measurement / threshold / observability`
>   例如："每天≥30 min、持续 12 周"、"按手环记录里程"、"≥3 次/周"、"自报告"
> - **belly_fat_loss**：缺同样这四项
>   例如："12 周后评估"、"腰围 cm"、"≥3 cm 下降"、"自报告"
>
> **② 缺一条数值参数（优先度 高）**
> - `P(belly_fat_loss=true | do(running=true))` 没有条目。补一个条件概率，或告诉我一个可靠来源。
>
> 把 ① 补清楚我可以再给一次结构化回答，补上 ② 才能给具体数值。

## Worked example with ambiguity

Input excerpt:

```json
// program.extensions.ambiguities
[{
  "kind": "intent",
  "chosen": "assoc",
  "alternatives": ["cause"],
  "reason": "NL 仅说'有关系吗'，既可读为相关性也可读为因果",
  "disambiguation_ask": "你是想问两者是否相关，还是一个是否导致另一个？"
}]
// result
{ "status": "structurally_solved", "query_kind": "assoc",
  "structural_result": {"value": true} }
```

Reply:

> 按 **相关关系** 这个读法，结论是 **有相关**（咖啡和失眠之间在
> 当前图里是 d-连通的）。
>
> ⚠ 不过我想先跟你确认一个判读决定：
> - 你是想问两者是否 **相关**（assoc — 我选的这个），还是想问
>   一个是否 **导致** 另一个（cause）？理由：你的问法"有关系吗"
>   这两种读法都可以。
>
> 告诉我就能换个读法重跑。

## Worked example — effect query with mediator and all llm_proposal edges

The most common shape (and the easiest to render *wrong*): the user
asks a mechanism question, the upstream LLM proposes the causal graph
itself, and Themis says "structurally decomposable" — which sounds
authoritative but is structurally a replay of the LLM's own
assumption. Explanation must lead.

Input excerpt:

```json
// program (LLM-built)
{
  "statements": [
    // ... variable declarations ...
    { "kind": "cause",
      "from": running, "to": endorphin_release,
      "annotations": { "source": "llm_proposal" } },
    { "kind": "cause",
      "from": endorphin_release, "to": good_mood,
      "annotations": { "source": "llm_proposal" } },
    { "kind": "cause",
      "from": running, "to": good_mood,
      "annotations": { "source": "llm_proposal" } },
    { "kind": "query", "query": {
        "kind": "effect",
        "intervention": { "atom": running, "value": true },
        "target": { "atom": good_mood, "value": true },
        "mediator": endorphin_release } }
  ],
  "extensions": { "ambiguities": [
    { "kind": "cause_attribution",
      "rationale": "用户问'是不是因为内啡肽'是归因，Themis 只能验证图上的路径" }
  ]}
}

// result
{ "status": "structurally_solved",
  "structural_result": { "value": true },
  "extensions": { "mediation_decomposition": {
      "strategy": "nde_nie",
      "nde_nie": { "identifiable": true, "assumptions": [...] },
      "cde": { "identifiable": true, "assumptions": [...] } } },
  "explanation": "⚠ 上游 LLM 标记了不确定性 cause_attribution...\n⚠ 中介分解 NDE/NIE 标识为可识别，前提是...\n⚠ 中介分解 CDE 标识为可识别，前提是...\n⚠ 结构性回答途径上的边 running → endorphin_release 是上游 LLM 提出的假设...\n⚠ ... endorphin_release → good_mood ...\n⚠ ... running → good_mood ..." }
```

Reply (note headline priority: `cause_attribution` outranks
"structurally decomposable"):

> 直接答你的问题：**我没法告诉你"是不是因为内啡肽"** —— 这是个归
> 因问题，需要数据 + 一个 Themis 当前不算的分解步骤；我能告诉你
> 的只是"在我自己脑补的图上，'跑步 → 心情变好'这条效应在结构上
> 可以拆成内啡肽这条路径 + 其它路径"，并且**整张图是我作为 LLM 自
> 己提的**，没有文献支撑。
>
> 几个你必须知道的前提：
>
> - **三条边都是我自己提的假设**（`running → endorphin → good_mood`
>   + `running → good_mood` 直接路径）。结构上"算得通"本质上在复
>   述我的假设，不是 Themis 独立验证。有运动神经科学引用请补给我。
> - **"分解可识别"是有条件的**：NDE/NIE 依赖 Pearl 2001 跨世界条件
>   + 顺序可忽略性 + 没有被处理影响的中间混杂 + 一致性；CDE 还需
>   M→Y 后门可调整 + 一致性。任意一条不成立这个"可识别"就破。
> - **跑步改善心情还有很多其它通路**：阳光/维生素D、规律作息、社
>   交、成就感、BDNF、降低炎症因子……要做"内啡肽 vs 其它通路"的
>   归因分解，需要分层数据 + 当前不在 Themis 范围里的分解流程。
>
> 要从"图上能拆"升级到具体数字，缺的是：
> - `good_mood` 的操作化定义（time_window / measurement / threshold...）
> - `running` 的操作化定义（同上七项）
> - 之后再补一份分层数据 P(good_mood | do(running), endorphin)。

The reply pattern: (a) headline answers the *question they actually
asked* (mechanism / attribution) before the *question Themis answered*
(structural decomposability), (b) every ⚠ from `explanation` lands as
prose, (c) `mediation_identification_assumption_required` does NOT
get re-itemized in a separate "assumptions" section because the
explanation already covered it, (d) framing gaps come last as the
concrete next ask.

