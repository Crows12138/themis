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

1. **Headline** — can the question be answered? (with-number /
   with-bounds / structurally / not-yet-because-X)
2. **Mandatory disclosure channels** (any non-empty channel surfaces;
   skipping any of them breaks Themis's contract):
   - `bounds_result` — Phase 12: when point fails, surface the
     interval (Manski / Balke-Pearl) right after the headline
   - `data_gap_report` — what data is still needed
   - `extensions.ambiguities` — decisions made under uncertainty
   - statement-level `annotations.source: "llm_proposal"` — hypothesis
     edges
3. **Concrete asks** — `investigation_requests` rendered with the
   exact predicate names + worked examples for null skeleton fields
4. **Methodology** — only when the user asks "why" / "how": the
   `derivation` chain, full assumptions list, the symbolic formula

The first two layers are mandatory whenever the data is present. The
last two are need-driven — don't lead with methodology.

The user must always see the answer (or "no answer because...") before
caveats. Never bury the headline under a wall of disclaimers.

## Reading the JSON

Fields in roughly the order you'll consult them:

| Field | What it tells you |
|---|---|
| `status` | `numerically_solved` (number available) / `structurally_solved` (boolean assoc/cause) / `needs_investigation` (something missing) / `outside_language` (out of scope) |
| `numeric_result.value` | The concrete probability when `numerically_solved` came from the symbolic / Theta path |
| `numeric_estimate.{point, ci_lower, ci_upper, method, ...}` | The data-driven estimate (Phase 7). See §"Numeric rendering" |
| `structural_result.value` | `true` / `false` for cause / assoc when `structurally_solved` |
| `investigation_requests[]` | Actionable patches the user can paste back |
| `framing_notes[]` | Advisory; same content is projected into `investigation_requests` with `action=define_variable` — render the structured request, suppress the duplicate note unless it has no matching request entry |
| `data_gap_report` | Diagnostic surface — *why* data is needed and *what kind* |
| `bounds_result` | Phase 12: symbolic bounds when point identification failed. Method + lower/upper expressions + assumptions. See §"Bounds rendering" |
| `extensions.{...}` | Domain-specific blocks: `ambiguities`, `iv_identification`, `mediation_decomposition`, `transport_identification` |
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
  actual thing. For `cause_attribution` specifically, the headline
  must say "I only validated the path X→Y is in the graph (which I
  myself proposed) — I cannot tell you whether X is the *main* or
  *only* reason for Y; that needs data + a decomposition Themis
  doesn't currently compute."

**Omit** when `extensions.ambiguities` is absent or empty — don't
invent ambiguity. Users hate false alarms.

### 3. LLM-proposal edges

If `program` is available, inspect each `cause` and `bidirected`
statement's `annotations.source`:

- `"llm_proposal"` — you (the upstream LLM) hypothesized this edge.
  Disclose explicitly.
- A concrete citation (e.g. `"PubMed:12345"`) — evidence-backed; no
  special line needed beyond the normal reply.

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
operationalization).

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

For IDs not in the table, render the snake_case verbatim — don't
invent translations.

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

Anti-patterns specific to literature numbers:

- Letting a literature number masquerade as Themis-verified
- Combining literature point estimates across studies on your own
  ("study A + study B → average") — that's amateur meta-analysis
- Extrapolating the literature CI to the user's individual case
  (the CI is on the population mean, not on individuals)
- Dropping the citation. Inline link or PMID is mandatory.
  Unsourced literature is operationally fabrication

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

### Mediation decomposition (Phase 6.mediation)

When `extensions.mediation_decomposition` is present, the query asked
for an effect decomposition through a mediator.

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

**Template — `nde_nie` success**:

> 关于 `<X>` 通过 `<M>` 对 `<Y>` 的影响分解：
>
> - **总效应 TE**：`<X>` 改变对 `<Y>` 的全部影响
> - **自然间接效应 NIE**：通过 `<M>` 这条路径贡献的部分
> - **自然直接效应 NDE**：不经过 `<M>` 的部分
>
> 在你的图上这个分解**可以识别**（需要调整 `<adjustment>`）。具体
> 数字需要 Phase 7 估计层 —— 目前只给出"结构上可分解"的判断。

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
- 如果 program 有 `unobserved_population_shift` ambiguity → 提醒用户
  §T9.1 只处理观察到的 S；未观测差异是 §T9.3 范围
- 如果用户原始问题给了一个源人群数字（"RCT 说 X cm 下降"）→ 明确
  说 transport 不会输出"修正后的 X" —— 只会告诉你需要哪些数据来算
- 永远不要把源人群的点估计当作目标人群的答案（F25 失败模式核心）

### Sensitivity (E-value) — Phase 8.2

Fires when `numeric_estimate.sensitivity_analysis` is present (binary
outcomes only). Surface as a **robustness statement**, not a p-value
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

Skip the block entirely for continuous outcomes. Don't fabricate
placeholders.

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

Defense in depth — A1 prompt v2.6.1 was supposed to catch this
upstream, but renderer surfacing lets the user correct the loop.

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

Don't bury the warning. Useless bounds dressed up as useful is the
single biggest bounds-rendering anti-pattern.

### Cross-reference with data_gap_report

When both `bounds_result` and `data_gap_report` are present, the
gap report's `alternative_paths` text "接受 Balke-Pearl bounds 给
区间答案" is now backed by an actual interval (the bounds_result
above). Phrase the gap section as:

> 上面已经给了区间答案 — 要从区间升级到点估计，你需要补：
> - {gap.required_data.data_type} 形式的 {gap.required_data.variables}
> - n ≥ {gap.required_data.min_sample_size}（{precision_target}）

Don't repeat the bounds expression inside the gap section — it's
already rendered above.

### When NOT to render bounds

- `bounds_result` is null → omit entirely. Don't fabricate.
- `status == "numerically_solved"` AND bounds_result somehow set
  (shouldn't happen but defensive) → render the point + a one-line
  note "bounds also computed: [a, b]"; the point is the answer.
- `query_kind != effect` → `bounds_result` should be null already;
  if not, it's an upstream bug — don't render.

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

## Anti-patterns

- **Inventing missing fields not in the JSON** — render only what's
  declared
- **Paraphrasing predicate names into Chinese only** — keep the
  English identifier once so the user can reference it back
- **Giving a probability when status is not `numerically_solved`** —
  never invent numbers
- **Front-loading methodology** — the user wants the answer first;
  `derivation` and assumptions only on demand
- **Embedding raw JSON in the reply** — translate
- **Claiming LLM-proposed edges are evidence-backed** — if
  `annotations.source: "llm_proposal"` is present, disclose
- **Silently committing to ambiguous readings** — every entry in
  `program.extensions.ambiguities` must surface
- **Skipping the data gap report** — `data_gap_report` non-null +
  non-empty means the gap section is mandatory; surfacing "缺什么数据
  才能算" is half of Themis's value, and silently giving an answer
  while suppressing it breaks the contract that "不能给数字时不会编"
- **Combining or extrapolating literature numbers** without sources —
  citation IS the audit trail
