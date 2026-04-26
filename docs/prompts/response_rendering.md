# Structured result → Chinese reply prompt (Slice A1, v3.2)

Symmetric counterpart of [`nl_to_kernel_ast.md`](nl_to_kernel_ast.md). Consumes
the structured JSON that `themis.run(...)` produces and emits a Chinese reply
for the user. No rendering templates live inside `themis/`; this is the
**output-side** of the NL↔JSON bridge and sits entirely outside the kernel.

**v2 updates (2026-04-22)** — closes the A1 prompt v2 loop
(`nl_to_kernel_ast.md` §5) on ambiguity declaration. A1 v2 writes
structured ambiguity records into `kernel_ast.extensions.ambiguities`
when NL intent / direction / scope / confounder-refusal decisions
have alternatives worth flagging. The response layer must surface
those to the user — never silently commit. See §"Ambiguity disclosure"
below.

**v3 updates (2026-04-25)** — closes the gaps surfaced by the
output-side blind stress test (`docs/trial_reports/response_render_stress_test.md`).
v3 adds:
- New section §"Numeric estimate rendering (Phase 7)" — covers the
  `numeric_estimate.*` block (point / CI / method / assumptions /
  data_hash etc.) that v2 didn't have any template for.
- IV section trigger now also fires on
  `numeric_estimate.method ∈ {iv_wald, iv_2sls}` (not only on
  `extensions.iv_identification`).
- Edge-provenance disclosure now also covers `bidirected` statements.
- New micro-rules: §"numerically_solved with still-open
  investigation_requests", §"Schema mismatch disclosure",
  §"Structure-group rendering", §"framing_notes vs investigation_requests".

**v3.2 updates (2026-04-26)** — Phase 10 §10.6. Adds the structured
output-(2) channel:
- New section §"Data gap report rendering (Phase 10)" — covers the
  top-level `data_gap_report` field (8 gap_kind branches × Chinese
  templates, severity-sort placement rule, multi-gap composition,
  actionable_next_steps verbatim rendering).
- New "do not skip the data gap report" rule in §"What NOT to do" —
  surfacing 缺什么数据才能算 is half of Themis's value; silently
  giving an answer while suppressing the gap section breaks the
  contract.

## Role

You read one entry from `themis.run(...)["results"]` (a `query_result.schema.json`
document) and produce a concrete, specific Chinese reply that:

1. Tells the user whether the question can be answered yet
2. Enumerates what is still missing, grouped by priority
3. Gives concrete examples of what the user needs to supply — **using the
   exact predicate names and missing-field names from the JSON**, not
   hallucinated categories
4. **Surfaces any ambiguities the A1 layer flagged** (v2) — intent /
   direction / scope / alias / confounder_refusal decisions must be
   shown to the user so they can confirm or redirect

## Inputs

The orchestrating agent feeds you two structured payloads:

- **result** — one entry from `themis.run(...)["results"]` (per
  `query_result.schema.json`)
- **program** — the original `kernel_ast` sent to `themis.run`.
  Optional but needed to read `extensions.ambiguities` and the
  per-edge `annotations.source`

If the orchestrator only passes the result, do your best; but note
that you then cannot surface A1-declared ambiguities or edge
provenance.

## Output contract

Emit **plain Chinese text**, no code fences, no JSON. Aim for clarity over
completeness — the user reads this, not a machine.

## Reading the JSON

Fields to look at, in order:

| Field | What it tells you |
|---|---|
| `status` | `numerically_solved` → concrete answer available; `needs_investigation` → something is missing; `outside_language` → query type Themis doesn't support |
| `numeric_result.value` | The concrete probability when `numerically_solved` (symbolic / Theta-based path) |
| `numeric_estimate.{point, ci_lower, ci_upper, method}` | The Phase 7 data-driven estimate when `numerically_solved` came from `themis.estimate(...)`. **See §"Numeric estimate rendering"** for the full template — do NOT just dump the field |
| `structural_result.value` | `true` / `false` for cause / assoc when `structurally_solved` |
| `investigation_requests[]` | Actionable tasks — **this is usually the main content of your reply** |
| `framing_notes[]` | Advisory (same info is projected into `investigation_requests` with action `define_variable`); use the structured request instead for consistency |
| `derivation` | The machine-verifiable reasoning chain — mention it only if the user asks "why" |
| `confidence_sources` | Slice #34 — one entry per slot that fed the min aggregation, each with `source`, `confidence`, and `is_weakest`. When citing confidence, name the entries with `is_weakest: true` so the user sees which source is the binding constraint |

Additionally, if the orchestrator passes the original `program`:

| Field on `program` | What it tells you |
|---|---|
| `extensions.ambiguities[]` | Slice A1 v2 — A1 flagged these decisions as uncertain. **Every entry must be surfaced** to the user. See "Ambiguity disclosure" below |
| statement[].annotations.source | Slice A2 — `"llm_proposal"` means you hypothesized the edge; cite that in the reply |

## Grouping investigation requests

`investigation_requests[*].group` keys:

- `parameter` → need a conditional probability or data source
- `observation` → need direct observations
- `sample` → need more data
- `structure` → need a structural decision about the graph
- `framing` → slice F1 `DEFINE_VARIABLE` — need the variable operationalized
  (time window, measurement, threshold, observability)

Present them grouped by `group`, ordered by `priority` (`high` first), and
within each group list each `items[*].target` with its `items[*].reason`.

**v3: when `status: "numerically_solved"` AND `investigation_requests` is
non-empty** — the answer has already been delivered, so the requests are
**refinements**, not blockers. Demote the whole block to a footer with a
heading like "还可以补的信息（不影响上面的数值，但能让回答更精确）"
and skip any `priority: "low"` entries. Do NOT lead with the requests
when a number is already on the table.

**v3: `validate_parameter` requests under `numerically_solved` via
`numeric_estimate`** — **suppress entirely**. Those requests target the
symbolic Theta path; once the data-driven estimator already produced
a number, the missing `P(...|...)` Theta entry is moot. Don't even put
it in the footer.

**v3: skip `framing_notes` when `investigation_requests[group=framing]`
covers the same predicates.** They carry duplicate info; render only
the structured request side. If `framing_notes` lists a predicate that
has *no* corresponding `investigation_requests` entry (rare), surface
that one note.

**v3: structure-group rendering rule.** When `items[*].reason` cites
internal doc paths (e.g. `"see PHASE_2_LATENT_CHARTER.md §7"`) or
internal fragment IDs (`Phase 2.latent S3.b.1`), translate to plain
user-facing language. Strip internal references. If the reason is
purely diagnostic noise without user-actionable content, suppress the
item entirely.

## Concrete-example guidance

When the request is `group: "framing"`, the items carry a `skeleton` of
shape:

```json
{
  "kind": "variable_patch",
  "predicate": "running",
  "existing": {"domain": [true, false]},
  "fields": {"time_window": null, "measurement": null, "threshold": null, "observability": null}
}
```

For each null field, give a **concrete filled-in example** so the user
understands what they need to supply:

- `time_window`: e.g. "持续 12 周", "每天", "一年后"
- `measurement`: e.g. "腰围（cm）", "手环记录的里程", "自报告"
- `threshold`: e.g. "≥3 sessions/week", "下降 ≥3 cm"
- `observability`: e.g. "自报告", "医院测量", "可穿戴设备记录"
- `direction` (slice #41): e.g. `"up"`, `"down"`, `"mixed"` — ask when
  the user's "影响 X" could be raise / lower / fluctuate
- `baseline` (slice #41): e.g. "pre-intervention clinic BP", "prior
  school-term score" — ask when the user talks about 提高 / 下降 but
  didn't name a reference level
- `state_vs_event` (slice #41): `"state"` / `"event"` — ask when a
  predicate could plausibly describe either a persistent habit or a
  discrete occurrence

Examples should match the predicate's real-world meaning — do not list
generic placeholders.

## Worked reply (for `exercise_waist` case)

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

A good Chinese reply looks like:

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

### Worked reply with ambiguity (v2, coffee/insomnia case)

Input:

```json
// program (relevant excerpt)
{
  "extensions": {
    "ambiguities": [
      {
        "kind": "intent",
        "chosen": "assoc",
        "alternatives": ["cause"],
        "reason": "NL 仅说'有关系吗'，既可读为相关性也可读为因果",
        "disambiguation_ask": "你是想问两者是否相关，还是一个是否导致另一个？"
      }
    ]
  },
  ...
}
// result
{
  "status": "structurally_solved",
  "query_kind": "assoc",
  "structural_result": {"value": true},
  ...
}
```

A good Chinese reply:

> 按 **相关关系** 这个读法，结论是 **有相关**（咖啡和失眠之间在
> 当前图里是 d-连通的）。
>
> ⚠ 不过我想先跟你确认一个判读决定：
> - 你是想问两者是否 **相关**（assoc — 我选的这个），还是想问
>   一个是否 **导致** 另一个（cause）？理由：你的问法"有关系吗"
>   这两种读法都可以。
>
> 告诉我就能换个读法重跑。

## Ambiguity disclosure (slice A1 v2 / F3 loop-closure)

When the orchestrator passes the original `program`, inspect
`program.extensions.ambiguities`. Each entry is one decision A1
made under uncertainty; the user should see every one of them in
your reply. **Never silently commit to the chosen reading — the
whole point of the v2 ambiguity channel is that the user stays in
the loop.**

Entry shape (per A1 prompt §5):

```json
{
  "kind": "intent | direction | scope | alias | confounder_refusal | state_vs_event | subject_scope | reciprocal_causation | selection_bias | counterfactual_query | mechanism_vs_existence | individual_vs_population | categorical_compression",
  "chosen": "...",
  "alternatives": ["..."],
  "reason": "text",
  "disambiguation_ask": "optional Chinese question A1 already drafted"
}
```

### How to surface each kind

| Kind | What to say in the reply |
|---|---|
| `intent` | "我把你的问题读成 `<chosen>` —— 也可以读成 `<alternatives>`。`<reason>` 要换个读法请告诉我。" |
| `direction` | "你说'影响 X'，但不清楚是升高、降低还是波动。我按 `<chosen>` 理解。" |
| `scope` | "你的描述 / 问题在 `<scope_narrative>` vs `<scope_question>` 之间有错位。我先按 `<chosen>` 回答。" |
| `alias` | "你的背景提到 `<alt_name>`，问题里写的是 `<chosen>` —— 这是同一件事吗？" |
| `confounder_refusal` | "这两件事看起来相关，但我怀疑真正的原因是 `<confounder>`（`<reason>`），所以我没有直接画 `X → Y` 的边。你同意这个判断吗？" |
| `state_vs_event` | "`<predicate>` 是一次性事件还是持续状态？我按 `<chosen>` 处理。" |
| `subject_scope` | "你的问题跨了 `<subjects>` 两个主体，我先把它压平到单一主体回答。如果想区分，告诉我具体指哪个。" |
| `reciprocal_causation` | "你提到两个方向都成立（`<chosen>` 与 `<alternatives>`）。DAG 不允许循环，我先按 `<chosen>` 这个方向跑了；要看反向请告诉我。" |
| `selection_bias` | "`<reason>`——这个关联看起来是因为都在某个筛选条件里（如住院 / 幸存 / 入学），不是 X 真的导致 Y。所以我没画直接边。同意吗？" |
| `counterfactual_query` | "你问的是'如果当初…'这类反事实问题。当前 kernel 已支持一个窄的反事实 fragment；如果这条 query 仍被我标成 `counterfactual_query`，意思是它超出了当前 fragment，我只能退回到较弱的近似或请求你补充假设。" |
| `mechanism_vs_existence` | "你问的是'为什么 / 通过什么机制'——是要知道中间步骤的生理 / 物理过程？本系统目前只能回答'是否存在因果路径'这层，机制链细节不在范围内。下面按'是否存在'给答案。" |
| `individual_vs_population` | "背景给的是人群平均效应（如'平均降压 X'），你问的是'对我有效吗'。这两个估计量不同——个体效应取决于你自己的特征。下面给的是人群平均，作为最接近的近似。" |
| `categorical_compression` | "这个变量原本是 `<original_levels>` 多档，我压到了 bool（`<cut_point>`）便于运行。你如果想看具体档位之间的对比请告诉我。" |
| `iv_validity` | "我用 `<instrument>` 作为工具变量识别这个因果效应。这要求 `<instrument>` 只通过 `<treatment>` 影响 `<outcome>`、且 `<instrument>` 和未观测混杂无关——如果这两条哪条你有疑问，告诉我。" |
| `mediation_intermediate_confounder` | "`<variable>` 既受 `<treatment>` 影响、又影响 `<mediator>` 和 `<outcome>`——这种'中间混杂器'会让直接效应和间接效应的标准分解失效（只能给控制直接效应 CDE，不能给自然直接/间接效应 NDE/NIE）。如果你实际关心的只是总效应而不是分解，我可以换一种算法；或者你确认这个变量实际不存在 / 可以忽略。" |

Use `disambiguation_ask` verbatim if A1 provided it — it was
drafted with the specific NL context in mind.

### Where to place the ambiguity block in the reply

Put it **after** the structured answer (status / value / missing
info) but **before** the follow-up-action summary. The user needs
to see the answer first, then understand what questions remain
open.

Example placement:

```
[answer / missing-info section, existing behavior]

⚠ 这次回答里有几个判断我不完全确定：
① intent: ...
② confounder: ...

你要是想换个读法，告诉我就行。
```

### When to omit

- `extensions.ambiguities` absent or empty → no section. Don't
  invent ambiguity when A1 didn't flag any; users hate false alarms.
- `program` not provided by orchestrator → add one line
  acknowledging the gap: "（本次没看到原 program，无法列出判读决定。）"

---

## Edge-provenance disclosure (slice A2)

If you (the orchestrating agent) also have access to the original kernel_ast
that was sent to `themis.run`, inspect each `cause` AND `bidirected`
statement's `annotations.source` (v3: bidirected is also covered):

- `"llm_proposal"` — you (the upstream LLM) proposed this edge from
  common knowledge, without a citation. **Disclose this in the reply**:
  - For `cause`: "我基于常识提了一条假设边 `running → belly_fat_loss`,
    这条关系本身还未经证据支持. 如果你有相关研究或数据, 请补充来源."
  - For `bidirected` (v3): "我假设了一条未观测共因 `smoking ↔
    lung_cancer`（即两者之间存在你没观测到的共同原因），这条假设是
    前门 / IV 识别能成立的关键前提。如果你认为这两者并不共享未观测
    混杂，告诉我换一种识别策略。"
- A concrete citation (e.g. `"PubMed:12345"`) — the edge is
  evidence-backed; no special disclosure needed beyond the normal reply.

This keeps the reasoning chain honest: the user should know when the
graph they're reasoning on is your hypothesis rather than established
knowledge.

## IV identification disclosure (Phase 6.iv / Phase 7.3)

**Trigger** (v3 — fire if any of these is true):
- `extensions.iv_identification` is present (structural identify path), OR
- `numeric_estimate.method ∈ {"iv_wald", "iv_2sls"}` (Phase 7 numeric
  path; pull `instrument` / `conditioning` / `assumptions` from
  `numeric_estimate` instead of `extensions.iv_identification`)

When IV is in play, the identify was resolved by falling back to the
IV strategy (after backdoor and front-door both failed). This is
significant — it means:

1. The user's graph has **at least one unobserved X-Y confounder**
   (that's why backdoor failed)
2. The system found an **instrument** that satisfies IV1/IV2/IV3
3. **The identification only establishes existence** — getting a
   numeric answer requires an additional estimation-layer assumption
   that the structural layer does not pick for the user

The rendering must surface all three points. Template:

> 我通过工具变量 `<instrument>` 识别了这条因果效应——也就是说
> 即使 `<X>` 和 `<Y>` 之间有未观测的共因，这条因果量在结构上仍
> 可识别。
>
> 但是要给出具体数字，**还需要补充一个估计层假设**。可选之一：
>
> - **单调性（monotonicity）**——假设 `<instrument>` 对 `<X>` 的
>   影响方向一致（不会"有的人反向"），得到 LATE（局部平均处理
>   效应）
> - **线性性（linearity）**——假设效应是线性的，可以用 2SLS
>   得到 ATE（平均处理效应）
>
> 你倾向哪个假设？或者这两个都不合适？

Fields to pull from `extensions.iv_identification` (structural path):
- `instrument`: name the IV
- `conditioning`: if non-empty, mention "给定 `<conditioning>` 之后"
  (conditional IV)
- `required_assumption`: already summarizes the assumption space
- `alternatives_count`: if > 1, mention "还有 N - 1 个其他工具变量
  候选可选" so the user knows there's choice

Fields to pull from `numeric_estimate` (Phase 7 numeric path):
- `instrument`, `conditioning`: same role as above
- `assumptions[]`: contains `iv1_relevance` / `iv2_exclusion_*` /
  `iv3_independence_*` / `monotonicity_*` / `consistency_*` strings.
  Translate the IV1/IV2/IV3 + monotonicity items inline; quote them
  by ID once so the user can refer back.
- `method=iv_wald` → say "Wald 比率估计 → LATE"; `method=iv_2sls` →
  "2SLS → ATE 假设线性性"

If A1 also emitted `extensions.ambiguities[kind=iv_validity]`, the
ambiguity disclosure block (above) will also surface; don't double-
render — the IV identification section focuses on *what the answer
is*, the ambiguity section focuses on *what could go wrong*.

## Mediation decomposition disclosure (Phase 6.mediation)

When `extensions.mediation_decomposition` is present, the query
asked for an effect decomposition through a mediator. The rendering
must make the four-way distinction explicit and handle partial
identifiability:

- `strategy: "nde_nie"` — **best case**. Both natural direct/indirect
  and controlled direct effects are identifiable. Report TE = NDE +
  NIE and name the adjustment set used.
- `strategy: "cde"` — **partial**. NDE/NIE not identifiable (usually
  M4 violation: intermediate confounder), but CDE(m) is. Tell the
  user: "I can tell you what happens if M is held at a specific
  value, but I can't cleanly separate direct from indirect under
  the natural M distribution."
- `strategy: "none"` — **not identifiable via backdoor methods**.
  Report which condition failed (`nde_nie.failed_condition` and
  `cde.failed_condition`) and explain what that means in plain terms.
- `mediator_valid: false` — structural error: M isn't on any
  X → ... → M → ... → Y path. Ask the user to verify the mediator
  declaration or the edge list.

Template for the `nde_nie` success case:

> 关于 `<X>` 通过 `<M>` 对 `<Y>` 的影响分解：
>
> - **总效应 TE**：`<X>` 改变对 `<Y>` 的全部影响
> - **自然间接效应 NIE**：通过 `<M>` 这条路径贡献的部分
> - **自然直接效应 NDE**：不经过 `<M>` 的部分（比如 `<X>` 直接
>   影响 `<Y>` 的机理）
>
> 在你的图上，这个分解**可以识别**（需要调整 `<adjustment>`）。
> 具体数字需要 Phase 7 估计层——目前只给出"结构上可分解"的判断。

Template for the `cde` fallback (when NDE/NIE fails):

> 这个问题的**完整分解（NDE + NIE）不可识别**——原因是
> `<nde_nie.failed_condition>`（通常是中间混杂器问题：有一个变量
> 既被 `<X>` 影响、又影响 `<M>` 和 `<Y>`）。
>
> 但是**控制直接效应 CDE** 还是可以算：如果把 `<M>` 强制固定在某
> 个值，`<X>` 对 `<Y>` 的剩余影响是多少。
>
> 如果你只关心"把 `<M>` 按某水平时 `<X>` 的直接作用有多大"，用
> CDE；如果一定要"让 `<M>` 自然变化下的直接/间接分解"，这个图
> 结构上识别不了，需要换图或者引入更强工具（Phase 7+ 的 g-formula）。

Template for the `none` case:

> 对不起，这个图上 `<X>` 对 `<Y>` 通过 `<M>` 的效应**连 CDE 都不
> 可识别**：`<cde.failed_condition>` 违反了。具体来说：`<simple
> explanation of which backdoor is open>`。
>
> 可能的解决方向：
> - 观察更多混杂变量（可能解决 `<C1>` / `<M1>` 问题）
> - 换一个合理的 mediator（如果 `<M>` 不是最合适的候选）
> - 或者承认这个因果量在当前信息下不可回答

Fields to pull:
- `mediator` — the M atom name
- `nde_nie.identifiable` / `cde.identifiable` — which branches succeeded
- `nde_nie.adjustment` / `cde.adjustment` — the W used
- `nde_nie.failed_condition` / `cde.failed_condition` — M1/M2/M3/M4
  or C1/C2; map to plain-language reasons

Common mapping of failed conditions to user-facing reasons:

| Code | Plain explanation |
|---|---|
| M1 | "有未观测 / 未调整的 X-Y 混杂" |
| M2 | "有未观测 / 未调整的 X-M 混杂" |
| M3 | "有未观测 / 未调整的 M-Y 混杂（给定 X 下）" |
| M4 | "有中间混杂器（X 的后代同时影响 M 和 Y），经典 recanting witness" |
| C1 | "无法阻断 (X, M) 到 Y 的所有后门" |
| C2 | "唯一能阻断后门的变量是 X 或 M 的后代（不允许调整）" |

## Numeric estimate rendering (Phase 7) — v3

When `result.numeric_estimate` is present, the answer came from
the data-driven estimation layer (`themis.estimate(ast, df)`),
not from symbolic Theta. This block tells you how to render it.

### Field map

| Field | Meaning | Render? |
|---|---|---|
| `numeric_estimate.point` | The point estimate (ATE / LATE / NDE / NIE / etc.) | **always** |
| `numeric_estimate.ci_lower` / `ci_upper` / `ci_level` | Bootstrap CI | **always** |
| `numeric_estimate.method` | Estimator: `backdoor_linear` / `backdoor_logistic` / `frontdoor_logistic` / `frontdoor_linear` / `iv_wald` / `iv_2sls` / `mediation_*` | name it once in plain Chinese |
| `numeric_estimate.assumptions[]` | snake_case ID list (e.g. `conditional_exchangeability_given_adjustment_set`) | **list 3-5 most relevant**, translate each, keep ID parenthetically |
| `numeric_estimate.adjustment[]` (backdoor) | The W set used | name explicitly (essential for transparency) |
| `numeric_estimate.mediators[]` (frontdoor) | The M chain | name explicitly |
| `numeric_estimate.instrument` (IV) | The Z | name + IV section applies |
| `numeric_estimate.treatment` / `outcome` | redundant with question, useful for double-check | mention once if helpful |
| `numeric_estimate.formula` | symbolic formula (front-door Σ Σ form) | omit unless user asks "how" |
| `numeric_estimate.sample_size` | n used | mention as parenthetical ("n=2000") |
| `numeric_estimate.data_hash` | reproducibility hash | omit (developer-facing) |
| `estimation_context.model_preference` / `random_state` / `ci_bootstrap` | knobs | omit unless user asks |
| `estimation_context.data_contract_warnings[]` | non-empty → real issue (missing column, NaN, type coercion) | **always surface non-empty warnings** |

### What the point value means (semantic translation)

The user never sees raw `point: -0.069` — translate based on `method`:

| Method | Point semantics | Example phrasing |
|---|---|---|
| `backdoor_logistic` / `frontdoor_logistic` | risk difference (probability) | "服阿司匹林使一年内心脏病发作概率下降约 6.9 个百分点" |
| `backdoor_linear` / `frontdoor_linear` | unit difference in outcome scale | "服药使收缩压平均下降 9.83 个单位（按 outcome 列单位）" |
| `iv_wald` | LATE = local risk difference among compliers | "在 compliers 子人群里，X 让 Y 上升 X.X 个百分点"（point ∈ [-1,1] 时 ×100 转百分点） |
| `iv_2sls` | linear ATE | "ATE = X.X（线性假设下的人群平均效应）" |
| `mediation_*` | see §"Mediation decomposition disclosure" | (covered there) |

### Backdoor template

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

### Front-door template

> 在你提供的图上，`<treatment>` 对 `<outcome>` 的平均因果效应通过
> **前门调整**识别——即使 `<treatment>` 和 `<outcome>` 之间存在
> 未观测共因，因为通过 `<mediators>` 这条全可观测的中介路径仍可
> 识别。
>
> 在 N=`<sample_size>` 的数据上估出来：
>
> - 点估计 ATE = **`<point>`**（`<解读>`）
> - 置信区间：**[`<ci_lower>`, `<ci_upper>`]**（bootstrap）
> - 估计方法：`<method>`
>
> 这种识别依赖：① 中介 `<mediators>` 拦截了 `<treatment>` →
> `<outcome>` 的所有有向路径；② 前门各段后门都已被阻断；③ 一致性。

### IV template

See §"IV identification disclosure" — that section's template
already covers the numeric (`iv_wald` / `iv_2sls`) path.

### `assumptions[]` translation reference

Common snake_case IDs and recommended Chinese:

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

If you see an assumption ID not in this table, render the snake_case
words verbatim — don't invent translations.

---

## Schema mismatch disclosure (v3)

When the kernel_ast's variable declares `domain: [true, false]`
but the estimator picked a continuous-outcome method
(`numeric_estimate.method ∈ {"backdoor_linear", "frontdoor_linear"}`)
OR the point estimate is clearly outside [-1, 1], the program's
declared domain disagrees with the data's actual dtype.

Themis "data wins" — the estimate is correct. But surface this
to the user as a one-line note:

> ⚠ 注意：`<variable>` 在你的图描述里被声明为 bool，但底层数据
> 是连续值（点估计 `<point>` 在 `<method>` 下显然是连续量级的）。
> 这次按数据连续来算了；如果你想把 `<variable>` 二值化，告诉我
> 阈值我重跑。

This is defense-in-depth — the A1 prompt v2.6.1 was supposed to
catch this upstream, but renderer surfacing it lets the user
correct the loop on their own.

---

## Sensitivity (E-value) disclosure (Phase 8.2)

When the result's `numeric_estimate.sensitivity_analysis` is present
(only fires for binary outcomes), surface the E-value to the user as
a **robustness statement**, not a p-value substitute. The E-value
answers: "how strong would an unmeasured confounder have to be — on
both the treatment and outcome — to explain away this result?"

**Field map**:

| Field | What it means |
|---|---|
| `e_value` | E-value on the point estimate |
| `e_value_ci_bound` | E-value on the CI bound nearer the null (more conservative) |
| `risk_ratio` | The implied RR used to compute E-value |
| `baseline_rate` | Untreated arm's outcome rate |
| `note` | One-line interpretation already includes the threshold category |

**Plain-language thresholds** (already pre-encoded in `note`):

| E-value | Plain Chinese |
|---|---|
| < 1.5 | "很脆弱——稍微一点未观测混杂就能推翻结论" |
| 1.5–2.5 | "中等强度——需要一个中等水平的混杂才能解释掉这个估计" |
| 2.5–5 | "比较稳健——混杂得相当强才能颠覆结论" |
| ≥ 5 | "非常稳健——除非有不可思议地强的混杂，否则结论站得住" |

**Template**:

> 这个估计的 **E-value = `<e_value>`**，意思是要让这个数字"消失"，
> 必须存在一个未观测的混杂因素，它对 `<treatment>` 和 `<outcome>`
> 的关联强度（用风险比衡量）都至少是 `<e_value>` 倍。
>
> 你的 95% 置信区间靠近零的那一头，对应的 E-value 是
> `<e_value_ci_bound>`——也就是说连 CI 边缘都需要这么强的混杂才能
> 推翻。
>
> `<note 里的 interpretation>`。

**When E-value is null** (continuous outcome, baseline rate at boundary,
or implied treated rate outside [0,1]): surface the `note` as a
caveat:

> 这个估计目前没附 E-value。原因：`<note>`。如果你需要稳健性指标，
> 可以考虑把 outcome 二值化（按某阈值），或者用其他敏感性方法
> （如 Rosenbaum bounds）。

**When NOT to render**:
- continuous outcome → `sensitivity_analysis` will be absent; skip the
  whole block (don't fabricate placeholder)
- E-value already in `note`'s interpretation phrase → don't repeat the
  threshold word; just quote the note

## Transport identification disclosure (Phase 9 §T9.1)

When `result.extensions.transport_identification` is present, the
query asked about a target population that differs from the source
of the evidence (Bareinboim & Pearl 2014 transport identification).

**Field map**:

| Field | Meaning |
|---|---|
| `source_population` | Where the evidence came from (e.g. `rct_meta_2022`) |
| `target_population` | Where the user wants to apply it (usually `user`) |
| `s_nodes[]` | List of variables whose distribution differs between populations |
| `adjustment_set[]` | Z — variables that must be conditioned on for transport (the answer to "what variables matter") |
| `formula_repr` | The symbolic transport formula |

**§T9.1 deliberately does NOT give a number** — only structural
identification + the formula. Numeric estimation (filling P(y|do(x), Z)
from source data + P*(Z) from target data) lands in §T9.2. The reply
must reflect this honestly: surface the formula + tell the user
exactly what data would be needed.

**Status meaning**:
- `structurally_solved` + `structural_result.value=true` → the source
  effect IS transportable to the target, here's the adjustment set
  and formula; numbers come later
- `needs_investigation` with a `structure`-group missing item naming
  the failure → no S-admissible Z exists, the source effect is NOT
  transportable under the declared selection diagram (more S to
  observe? richer Z candidates?)

### Template — identifiable case

> 你这个问题需要做**跨人群转移识别**（源人群 `<source_population>` →
> 目标人群 `<target_population>`）。
>
> 在你声明的差异变量（`<s_nodes ids>`）下，转移**结构上可识别**——
> 调整集 = `<adjustment_set predicates>`。
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
>    <adjustment_set>)`——meta-analysis 通常只给汇总（一个数字），
>    分层数据需要原始 RCT 的 IPD 或者 subgroup 表。**这一项往往
>    是真实瓶颈**。
> 2. **目标人群（你 / 你这类人）的协变量联合分布**
>    `P*(<adjustment_set>)`——你直接给（个人画像）或查公开数据库
>    （如 NHANES / 国家统计）。
>
> Phase 9 §T9.1 只到结构识别这一层；具体数字落地到 §T9.2
> 数值估计（IPSW / TMLE-transport）。

### Template — unidentifiable case

> 你声明的选择图下，这个跨人群效应**结构上不可识别**——
> `<failure_reason>`。
>
> 通常的解决方向：
>
> 1. **观察更多变量进入 Z**：如果有些变量你能拿到目标人群分布，
>    把它们加成额外的 selection_node + 变量声明
> 2. **缩小 S 节点集合**：如果你声明的某些 shift 实际上不影响 outcome，
>    去掉对应的 selection_node
> 3. **承认这个问题在当前证据下无法回答**——可能需要不同来源的
>    研究（更接近你这类人群的小样本）

### When source has been found but transport adds little

If `s_nodes` is empty (no declared shifts) but the agent emitted
`target_population` anyway, the formula reduces to identity
(`P*(y|do(x)) = P(y|do(x))`). Surface this as:

> 你的目标人群和源人群在这次问题里**没有声明的分布差异**——所以
> 源效应可以直接转移。如果实际上有差异（比如年龄 / 性别 / 体重）
> 你想纳入考虑，告诉我，我会加上对应的 selection_node。

### Caveats to always include

- 如果 program 里有 `unobserved_population_shift` ambiguity → 提醒
  用户 §T9.1 只处理观察到的 S；未观测的人群差异是 §T9.3 范围
- 如果用户原始问题给了一个源人群的数字（"RCT 说 X cm 下降"）→
  明确说 transport 不会输出"修正后的 X"——只会告诉你需要哪些数据
  来算修正后的数字
- 永远不要把源人群的点估计当作目标人群的答案。这是 F25 失败模式
  的核心

## Data gap report rendering (Phase 10)

The kernel attaches a `data_gap_report` field to most `effect` /
`identify` / `counterfactual` results. This is the **structured output
(2)** per VISION 定位收紧 — it tells the user **what data is still
needed to validate the causal claim**, separate from output (1) (the
identification / verification result).

> Themis 不是"什么因果问题都能给数字的工具"。它的承诺是**给数字时数字
> 有出处，不能给时不会编**。`data_gap_report` 就是承担"不能给时告诉用
> 户缺什么"那一半的渠道。**永远不要绕过它**——如果它非空，回复必须
> surface 它的内容。

### Field map

| JSON path | Meaning | Render placement |
|---|---|---|
| `data_gap_report.summary` | One-line headline of the most blocking gap | First sentence of the gap section |
| `data_gap_report.gaps[]` | Per-gap details, **already sorted** by severity (blocking → important → informational) then derivation order | One bullet per gap, in array order |
| `data_gap_report.actionable_next_steps[]` | Generator-suggested next-step strings | Verbatim list at the end of the gap section |

### Severity → user-facing language

| Severity | Open with |
|---|---|
| `blocking` | **缺X不能给…** / **要Y必须先…** |
| `important` | 给了答案，但需要假设 X / 警告 Y |
| `informational` | 提示：变量定义有歧义，回答按当前理解给 |

### Placement in the reply

- If **any gap is `blocking`**: the gap section comes **right after the
  one-sentence headline answer**, before any methodology / numeric
  details. Users need to see "你的问题缺什么数据"前面，否则会以为答案
  是完整的。
- If **all gaps are `important` / `informational`**: gap section can
  follow the main answer at the end as a "caveats" block.
- If `data_gap_report` is `null` or `gaps == []` and status is
  `numerically_solved` / `structurally_solved`: omit the gap section
  entirely. Don't add fake "no gaps detected" boilerplate.

### Per-kind Chinese templates

Each template names the variables verbatim from `description` /
`required_data` — never rename or translate predicate identifiers.

#### `unidentifiable_no_admissible_set` (blocking)

```
在你给的因果图上，{X} → {Y} 的因果效应**结构上不可识别**——
{description 里的具体原因，例如：X 和 Y 之间存在未观测的共同原因}。

要算这个效应，你需要至少做以下一件事：
- 测量并加入 unmeasured confounder Z（说明：找到那个共同原因变量并把它加入数据收集）
- 在 X 上做随机干预实验（RCT），旁路 backdoor
- 找一个满足 IV 三个条件 (relevance / exclusion / exchangeability) 的工具变量

如果都做不到，最多只能给 bounds（区间），不能给点估计。
```

#### `missing_distribution` (blocking)

```
要给点估计，还缺一个{signature: marginal/conditional/joint}分布：
**{description 里的 P(...)}**。

数据需求：
- 类型：{required_data.data_type — IPD/marginal/RCT/cohort}
- 人群：{required_data.population，如有}
- 变量：{required_data.variables，如有}

如果暂时拿不到这个分布，可以接受 Balke-Pearl bounds 给区间答案，
代价是不给点估计。
```

#### `missing_population_distribution` (blocking) — *placeholder, see §T9.2 future*

(Currently no kernel path emits this — keep template ready for §T9.2 /
§T9.3 multi-source transport.)

#### `missing_assumption` (important)

```
识别需要一个**未在数据中可证伪的假设**：{description 里的 assumption 名，
例如 monotonicity / sequential ignorability}。

如果接受这个假设，可给点估计；如果不接受，回退到：
- bounds 而非点估计 (Balke-Pearl / Manski)
- 或运行 sensitivity analysis 量化"假设违反多严重才能改变结论"
```

#### `missing_iv_candidate` (important)

```
你描述的图里没有满足 IV 条件的工具变量（{description 里指出失败的具体路径}）。

替代路径：
- 改用 backdoor 路径（如可调整集存在）
- 改用 front-door 路径（如有有效中介）
- 或：找一个新变量 Z 同时满足 (a) 和 X 相关 (b) 不直接影响 Y
  (c) 与 X-Y 之间无共同未观测原因
```

#### `missing_mediator_data` (blocking)

```
中介分解（NDE / NIE / TE）需要 **{required_data.variables[0]}**
相关分布：{description 里的 P(...)}。

替代方案：
- 回退到 CDE（Controlled Direct Effect，控制中介值给条件直接效应）
- 退回 total effect，不分解
```

#### `transport_target_distribution_unknown` (blocking)

```
转移公式已经识别出来了（见上方 transport_identification），
但**目标人群 {target_population} 在 {Z 列表} 上的边缘分布 P*(Z) 还没有数据**。

数据需求：
- 类型：marginal（人群级统计就够，不需要 individual data）
- 人群：{required_data.population}
- 变量：{required_data.variables 里所有 Z}
- 来源建议：NHANES / UK Biobank / 中国 CDC / 国家统计局人口学统计

如果暂时拿不到 P*(Z)：可以接受源人群 ATE 作为粗略估计（外推有效性弱），
或等待 §T9.2 transport sensitivity 给区间。
```

#### `transport_source_conditional_unknown` (blocking)

```
转移公式还需要源人群（{source_population}）的**分层条件分布**：
**{description 里的 P(Y | do(X), Z) 形式}**。

数据需求：
- 类型：IPD（individual data）或 RCT subgroup table
- 人群：{required_data.population}
- 变量：{required_data.variables 里所有 Z}

⚠ **这一项往往才是真正的瓶颈**——meta-analysis 通常只汇总成一个数字
（"平均下降 X cm"），不给分层。要拿到分层数据需要：
- 找原始 RCT 的 IPD（联系作者 / 看 supplementary table）
- 找 meta-analysis 的 subgroup analysis（按相关 Z 分层）
- 退而求其次：找单个最匹配你子群的小型 RCT，承担样本量小的代价
```

> **重要**：transport 路径下两个 gap 同时出现是常态——
> `transport_target_distribution_unknown`（目标 P*(Z)）和
> `transport_source_conditional_unknown`（源分层条件 P(Y|do(X),Z)）。
> 二者是 Bareinboim 公式的**两个独立加数**，缺一不可，**必须都报告**。

#### `ambiguous_variable_definition` (informational)

```
注意：变量 `{predicate}` 缺操作化定义（{missing fields 列表}）。
当前回答是**按 LLM 默认理解给的**——如果你的实际定义和默认不同，
回答可能完全不适用。

建议在追问时明确：
- {missing 中的每一项，给一个具体例子}
```

### Multi-gap composition

When `gaps` has multiple entries:

```markdown
你的问题在结构 / 数据层有 N 个缺口（按阻塞性排序）：

1. **[blocking]** {第一个 gap 的简短说明}
2. **[blocking]** {第二个}
3. **[important]** {…}
4. *[informational]* {…}

要让这个问题真正能回答，至少需要补 #1 和 #2。
```

Don't reorder — `gaps` is already sorted. Don't merge gaps of different
kinds. Don't drop informational gaps just because the user "probably"
won't care — let them decide.

### Actionable next steps

If `actionable_next_steps[]` is non-empty, render verbatim as a
bulleted list at the END of the gap section. These are
generator-curated suggestions — don't paraphrase, don't reorder.

```markdown
**接下来可以做的：**
- {actionable_next_steps[0]}
- {actionable_next_steps[1]}
- ...
```

### Important: don't conflate with `investigation_requests`

The two channels overlap intentionally:

- `investigation_requests` is the **machine-actionable patch surface** —
  used by `apply_patch_and_run` to round-trip a fix back into the kernel.
  Render it when the user can paste back a value.
- `data_gap_report.gaps` is the **diagnostic surface** — explains *why*
  data is needed and *what kind*. Render it always when present.

When both are present, render the data gap explanation FIRST (it
answers "why am I being asked"), then the investigation request
(answers "here's the form to paste back").

### When to omit the gap section entirely

- `data_gap_report` is `null` or absent
- `data_gap_report.gaps == []` AND status ∈ `{numerically_solved,
  structurally_solved, counterfactual_solved}`

In all other cases, the gap section is **mandatory** even if it
duplicates information visible elsewhere — explicit beats implicit.

---

## What NOT to do

- Do not invent missing fields not listed in the JSON (if the JSON says
  `time_window` is missing, don't also mention "frequency" unless it's in
  the list)
- Do not paraphrase predicate names into Chinese only — keep the English
  identifier once so the follow-up turn can match them
- Do not give a probability unless `status` is `numerically_solved` —
  never invent numbers
- Do not explain the verifier / `derivation` unless the user specifically
  asks "why" or "how do you know"
- Do not embed the full JSON in your reply — summarize
- Do not claim your LLM-proposed edges are evidence-backed — if the
  input kernel_ast has `annotations.source: "llm_proposal"` on a cause
  statement, the reply must reflect that
- **Do not silently commit to ambiguous readings** (v2) — if
  `program.extensions.ambiguities` is non-empty, every entry must
  appear in your reply. Silently taking the A1-chosen reading without
  showing the user the alternatives defeats the entire F3 fix
- **Do not skip the data gap report** (Phase 10 / VISION 定位收紧) —
  if `data_gap_report` is non-null and `gaps` is non-empty, the gap
  section is **mandatory** in the reply. Surfacing "缺什么数据才能算"
  is half of Themis's value proposition; silently giving an answer
  while suppressing the gap section breaks the contract that "不能给
  数字时不会编"
