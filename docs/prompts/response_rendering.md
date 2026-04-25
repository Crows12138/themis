# Structured result → Chinese reply prompt (Slice A1, v2)

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
| `numeric_result.value` | The concrete probability when `numerically_solved` |
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
that was sent to `themis.run`, inspect each `cause` statement's
`annotations.source`:

- `"llm_proposal"` — you (the upstream LLM) proposed this edge from
  common knowledge, without a citation. **Disclose this in the reply**:
  e.g. "我基于常识提了一条假设边 `running → belly_fat_loss`, 这条
  关系本身还未经证据支持. 如果你有相关研究或数据, 请补充来源."
- A concrete citation (e.g. `"PubMed:12345"`) — the edge is
  evidence-backed; no special disclosure needed beyond the normal reply.

This keeps the reasoning chain honest: the user should know when the
graph they're reasoning on is your hypothesis rather than established
knowledge.

## IV identification disclosure (Phase 6.iv)

When the result's `extensions.iv_identification` is present, the
identify was resolved by falling back to the IV strategy (after
backdoor and front-door both failed). This is significant —
it means:

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

Fields to pull from `extensions.iv_identification`:
- `instrument`: name the IV
- `conditioning`: if non-empty, mention "给定 `<conditioning>` 之后"
  (conditional IV)
- `required_assumption`: already summarizes the assumption space
- `alternatives_count`: if > 1, mention "还有 N - 1 个其他工具变量
  候选可选" so the user knows there's choice

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
