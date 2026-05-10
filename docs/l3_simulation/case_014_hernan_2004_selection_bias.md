# Case 014 — Hernán-Hernández-Díaz-Robins 2004 selection bias (HIV/AZT → AIDS death)

> 第 14 例。第一次有意识用真实文献案例测**板块 7 (选择偏差) 第二条
> 形状** —— *implicit sample restriction via ObservationStatement 上的
> collider*，与 iter 122 的 *explicit conditioning via EffectQuery.given*
> 互补。结果：✅ 真 gap → 加新 GapKind + classifier。板块 7
> 20-25% → 25-30%。

## NL question

"我们有一个 HIV 队列研究，登记后跟踪。AZT 治疗对 AIDS 死亡的因果效应是？
注意：能进入这次跟踪分析的是 'selected = true' 的受试者（保持随访 / 没
退出 / 在 study window 内有数据）—— 而 selected 状态本身受 AZT 治疗
（依从性高的更易留在研究里）和 AIDS 死亡（已死者不再被 selected）共同
影响。"

(用户期望：被告知**仅在 selected=1 子样本上估计 AZT→AIDS-death** 是
selection-on-collider 经典结构，导致估计有 selection bias —— 不论
covariate adjustment 多么完美。)

## Authoritative source

- **Hernán MA, Hernández-Díaz S, Robins JM.** "A Structural Approach to
  Selection Bias." *Epidemiology* 2004 Sep;15(5):615-25.

  这篇是流行病学界关于 selection bias 的现代经典；任何因果推断教科书
  讲 selection bias 都要引这篇。

### 核心 quote — selection on a collider IS the structural mechanism

Hernán et al 2004 §3 "A General Definition of Selection Bias":
> "Selection bias arises when conditioning on a common effect (or its
> descendant) of two variables, one of which is either the exposure or
> a cause of the exposure, and the other is either the outcome or a
> cause of the outcome … In all cases, the bias arises from
> **conditioning on a common effect** that is *not* on a causal pathway
> between exposure and outcome."

§4 "Examples — Differential Loss to Follow-Up":
> "A common form of selection bias due to differential loss to
> follow-up arises in observational studies when **the loss-to-follow-
> up indicator C depends on both the exposure E and the outcome D**.
> Estimating E→D using only those with C=0 (i.e. those *not* lost to
> follow-up) inverts the standard adjustment intuition: even if the
> measured covariates would close all backdoor paths from E to D in
> the full population, they cannot close the new path E→C←D opened by
> conditioning on C=0."

§5 "Adjustment for Selection Bias":
> "**Inverse probability of selection weighting** … weights each
> observed individual by 1/P(C=0|E,D,L); the reweighted pseudo-
> population mimics what would have been observed had nobody been
> lost to follow-up."

### Hernán & Robins *What If* §8.4 平行 quote

> "In a cohort initially of size N restricted to those with C=0, the
> association of E and D is *not* generally an unbiased estimator of
> the causal effect of E on D, **even when E was randomly assigned**,
> because the restricted sample no longer represents the full target
> population."

### 已 documented data limitations 跟 Themis 应当 surface 的对应

1. ✅ **Selection bias from sample restriction** — implicit
   conditioning on selected=1 opens E→C←D non-causal path
2. ✅ **未测混杂** — measured covariates can't close the
   collider-opened path no matter how rich
3. ✅ **变量定义模糊** — "selected" / "follow-up" / "AIDS death"
   operationalization
4. ⚠ **无法用 standard backdoor adjustment 修** — 这是 selection
   bias 与 confounding 的根本区别（Hernán 2004 §5 强调）

## Encoded kernel_ast

`case_014_hernan_2004_selection_bias.json`:

- 节点：azt, aids_death, selected
- 边：azt → aids_death (生物学); azt → selected (study_design,
  AZT users 更易留在研究); aids_death → selected (study_design,
  已死者不再被 selected) —— `selected` 是 azt 和 aids_death 的
  共同后代（collider）
- 关键 ObservationStatement：`{kind: "observation", atom: selected,
  value: true}` —— 编码**隐式 sample restriction** 到 selected=1 的
  子样本
- query: P(aids_death | do(azt)) effect query, given=[]
- **NOT** 在 EffectQuery.given 里写 selected —— 故意走 implicit
  路径而不是 iter 122 的 explicit 路径，看 Themis 能否从 program
  shape 自己识别隐式 collider 限制

## Pre-iter-206 Themis output (the gap)

```
status: needs_investigation

gaps (4):
  missing_distribution (blocking): 缺概率分布 P(aids_death=True|azt=True)
  ambiguous_variable_definition (important) ×2 (azt + aids_death)
  answer_is_bounds_not_point_estimate (informational): manski_natural

explanation: ⚠ 答案是 manski_natural ... (no selection-bias signal)
```

**没有 fire 任何 selection-bias 相关 gap_kind。** Themis 看到了
program 里有 `azt → selected ← aids_death` 这个 V-collider 结构，
也看到了 `ObservationStatement(selected, True)` 这个隐式样本限制，
但当时**没有 classifier 把这两个信号串起来**。iter 122 加的
`collider_conditioning_opens_backdoor` 只走 EffectQuery.given 路径
（用户**显式**把 collider 写进条件子组），这个 case 走的是
**隐式**路径（用户不在 given 里声明，但 dataset 的存在隐含 selected=1
条件）—— iter 122 完全不覆盖这条。

Hernán 2004 在文献里写了 22 年（自 2004 起），任何流行病学家在该
program shape 上 30 秒内会指出它，Themis 在板块 7 上之前只覆盖了
explicit 一半。

## Post-iter-206 Themis output (✅ match)

加了 `selection_on_collider_opens_path` gap_kind + 新 classifier 后：

```
status: needs_investigation

gaps (5):
  missing_distribution (blocking)
  ambiguous_variable_definition (important) ×2
  selection_on_collider_opens_path (important):
    样本被结构性限制为 selected=True 的受试者（program 里有
    ObservationStatement 编码了这个限制），但声明的 DAG 里 azt 和
    aids_death 都是 selected 的祖先 —— selected 是 collider。
    Pearl d-separation：用『仅 selected=True 的子样本』估计
    P(aids_death | do(azt)) 等于在 collider 上做条件，会**打开**
    azt→...→selected←...←aids_death 这条非因果路径，给估计引入
    selection-induced bias。Hernán-Hernández-Díaz-Robins 2004
    *Epidemiology* 15:615 "A Structural Approach to Selection Bias"
    的标准结构。
  answer_is_bounds_not_point_estimate (informational)

result.explanation 头部：
  ⚠ 样本被结构性限制为 selected=True 的受试者 ...
```

`alternative_paths` 给了三条结构性可执行行动:
1. 用 inverse-probability-of-selection weighting (Hernán 2004 §5)
2. 修 DAG（如果 selected 实际并非由 azt 和 aids_death 共同决定）
3. 把 selected 重新声明为 selection_node 走 transport identification

`if_provided` 给的是：补充未被 selected 限制的对照样本（覆盖
selected=¬True 的受试者，把全样本作为分析对象）—— 而**不是** "再
拿更多 selected=true 的数据"。

## 评估

### ✅ match (post-iter-206, 与 iter 122 互补 + 与 SelectionNode 区分)

- ✅ Hernán 2004 §3 "selection bias arises when conditioning on a
  common effect" 直接对应新 gap_kind 的 description
- ✅ Hernán 2004 §4 "differential loss to follow-up depends on both
  exposure E and outcome D" 直接对应 detection rule（W 的 ancestor
  closure 同时含 X 和 Y）
- ✅ provenance ref 准确指出 (observation_node, intervention->target)
  trio
- ✅ severity = IMPORTANT 而非 INFORMATIONAL：selection bias 是
  identification-impacting bias（Hernán 2004 §5 强调"无法靠 covariate
  adjustment 修"），不是只是 caveat
- ✅ alternative_paths[0] 引用 Hernán 2004 §5 IPSW —— 与 source
  文献的 §5 "Adjustment for Selection Bias" 段完全对应
- ✅ alternative_paths[2] 把 SelectionNode (Phase 9 §T9.1, transport)
  的边界明确指出 —— 防止用户错把 selection bias 当 transport 处理

### 与 iter 122 (collider_conditioning_opens_backdoor) 的区分

| 触发条件 | iter 122 | iter 206 (本 iter) |
|---|---|---|
| Collider W 在哪 | EffectQuery.given list | ObservationStatement.atom |
| 用户意图 | 显式条件子组分析 | 隐式样本限制（dataset 限制） |
| 错误形态 | 把"条件 ATE on subgroup"当 marginal ATE | 把 selection-biased 估计当 unbiased |
| 修法 | 移除 given 或走 transport | 全样本 / IPSW / 修 DAG |
| 文献 | Pearl 2009 §3 | Hernán-Hernández-Díaz-Robins 2004 |

两个 case 互补：case 014 (本) + (没有现有 case 直接测 iter 122
shape，但 iter 122 在 unit test 里 pin 住了) 联合覆盖板块 7 两条
形状。

### 与 SelectionNode (Phase 9 §T9.1) 的区分

`SelectionNode` 描述"两个人群之间分布差异" —— 用 selection diagram
D = G ∪ {S → affects} 处理 transport 跨人群泛化（Bareinboim-Pearl
§T9.1）。`selection_on_collider_opens_path` 描述"**单个**样本内
collider conditioning" —— 是 bias *within* sample，不是 transport
*across* populations。alternative_paths 里点名这个区分，避免用户
混用两个概念。

### 范围 honesty

板块 7 的 COVERAGE_MAP 描述从 **20-25%** 调到 **25-30%**：
- ✅ 加：iter 122 (explicit conditioning) + iter 206 (implicit
  sample restriction) 联合覆盖板块 7 两条结构形状
- ❌ 没做：IPSW selection-weight 数值估计器（alternative_paths
  point 1 只是给方向，不是给 fitted estimate）
- ❌ 没做：differential loss-to-follow-up 的多 round 分析
  (Hernán 2004 §6 longitudinal IPSW)
- ❌ 没做：selection bias × measurement bias 的 joint structure
  (Hernán & Cole 2009)

那三个 ❌ 是 Phase 9+ 工作（数值 IPSW 需新 estimator；longitudinal
版本需 g-methods；joint bias 需 multi-bias structural integration）。
当前 iter 只破冰板块 7 第二条形状。

## 后续 action

- ✅ Bug fix landed (iter 206 — 是新 capability，不是 bug fix)
- ✅ Add to L3 corpus regression test（must-have:
  selection_on_collider_opens_path + missing_distribution +
  ambiguous_variable_definition;
  must-not-have: graph_theta_independence_mismatch /
  collider_conditioning_opens_backdoor —— 注意这条，因为本 case
  走的是 *implicit* observation 路径不是 *explicit* given 路径）
- ✅ 加 unit test pin classifier 触发 + 三个 suppression / negative
  分支 (W 不是 collider / W = X / W = Y / 没 ObservationStatement)
- ✅ Update GAP_KINDS_REFERENCE / response_rendering / gap_to_action 同步
- ✅ COVERAGE_MAP 板块 7 行 + 元基础设施 row gap_kind 数 28 → 29

## 历史

- **2026-05-10 iter 206**: Real-finding via L3 simulation methodology。
  外部权威源：Hernán MA, Hernández-Díaz S, Robins JM 2004 *Epidemiology*
  15:615 "A Structural Approach to Selection Bias" + Hernán & Robins
  *Causal Inference: What If* §8.4。Bug：板块 7 (selection bias) 之前
  iter 122 加的 `collider_conditioning_opens_backdoor` 只覆盖 explicit
  EffectQuery.given 路径；implicit 路径（ObservationStatement 编码
  的样本限制 + DAG 上 collider）从未被任何 classifier 检测过。
  case 014 用 Hernán 2004 §4 经典 HIV/AZT → AIDS-death + loss-to-
  follow-up 编码 surface 这个 gap → 加新
  `selection_on_collider_opens_path` GapKind + 新 program-shape
  classifier，与 iter 122 的 explicit-given classifier 严格互补
  (一个看 EffectQuery.given，一个看 ObservationStatement)。
  与 SelectionNode (Phase 9 §T9.1 transport) 边界清楚。L3 corpus
  13/13 → 14/14。
