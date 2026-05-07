# Themis Core Status

> 更新时间：2026-05-07

这份文档只回答一件事：

**当前 Themis 核心到底完成到了什么程度。**

它不是愿景文档，也不是长期路线图。  
长期目标看 [VISION.md](VISION.md)，阶段路线看
[ROADMAP.md](ROADMAP.md)，上游建模层看
[WORLD_MODELING.md](WORLD_MODELING.md)。

---

## 当前快照（2026-05-07）

Themis 当前开发态是 **`0.15.0-dev`**。它已经不只是 `v0.1` 静态
DAG 内核，而是：

**可审计的因果推理编排器 + 数据缺口诊断器 + 受控估计层。**

当前已落地的主线能力：

- 静态 DAG 核心 + front-door / 窄 ADMG / 窄 temporal / 窄 counterfactual
- IV / mediation / transport 结构识别
- backdoor / front-door / IV / mediation / dose-response 数值估计
- causal discovery / sensitivity / bounds-first / data-gap report
- NL bridge、variable framing、KB adapter contract、MCP wrapper
- V0-V5 derivation verifier + T10 data-gap verifier

当前全量验证基线：

```text
1596 passed / 143 skipped, warning-clean
```

注意：下方保留了早期 `v1.0 core freeze` 和 Phase 5 以前的历史收口记录。
后续 Phase 6-14 是显式解冻后的 fragment / workflow / estimator 扩展，
不是对 `v0.1.0` 基线的静默漂移。

---

## 核心冻结 v1.0

> 冻结日期：2026-04-21
> 初始冻结后第一批延伸 fragment：A6.front-door、Phase 2.latent、Phase 5.temporal、Phase 5.counterfactual（见下方"冻结后显式立项的 fragment"段）。后续 Phase 6-14 另以独立 charter / slice 继续显式解冻。

从这一版起，**Themis 核心（语言 + 运行时 + 数值层 + verifier）视为已收口**。
后续工作往外长，不再往核心里塞。

**收口面**：

- 语言：`cause / probability / observation / query / variableDeclaration` +
  `forall` + 有限对象域
- 运行时：DAG 投影、`cause / assoc / identify / effect / probability`
  调度、backdoor 调整集、conditional identify、supporting paths
- 数值层：`Theta`、probability / effect 数值求值、缺参数精确报缺
- 工作流：`needs_investigation`、parameter skeleton、bundle 提取与回填、重跑 diff
- 解释与 framing：explanation、`framing_notes`、A0 advisory 检查
- confidence：`min(non-None)` 规则、解释文本中呈现
- 严格推导层：V0 identify / V1 numeric / V2 derivation JSON /
  V3 负结构见证 / V4 正结构见证 / V5 context JSON

**冻结期允许的改动**：

- bug 修复（语义不变）
- verifier 规则内部加强（同一 rule family 内的紧化，比如 V4 那种 witness 完整性）
- 文档 / 测试 / 真实案例 fixture
- 上层 workflow（比如 Variable Framer）—— 在核心之外，不算破冻

**冻结期禁止的改动**：

- 新 query 类型（前门 / 完备 ID / 反事实 等）
- 新语义维度（时序索引、潜变量、双向边、ADMG）
- 新 rule family、新 AST 语句类型
- 已有 framing_notes / confidence / derivation 语义的改写

要改这些，先解冻，并在此文档里留记录。

---

## 冻结后显式立项的 fragment

### A6.front-door（立项 2026-04-21，落地同日）

**理由**：按 ROADMAP 原则 "如果某个跃迁已经被清楚定义为一个新的理论 fragment,
边界/对象语言/规则集和完成标志都能说清, 也可以 theory-first 地启动"。
前门准则是对 V0–V5 识别骨架的 scope 内对称扩展——不引入潜变量 / 双向边 /
新 AST 节点，只在已有 DAG 语义内补另一条识别路径。

**交付**：

- `structural_solver.front_door_sets(graph, x, y)` — 返回满足 Pearl 前门
  准则 (FD1/FD2/FD3) 的最小 mediator 集合
- `formula_builder.front_door_formula(target, intervention, mediators)` —
  单 mediator 前门公式构造，多 mediator 暂 raise `FormulaSupportError`
- `scheduler._dispatch_identify` / `_dispatch_effect`：backdoor 搜索失败
  且 query.given 为空时，回退到 front-door
- verifier rules：`front_door_criterion` / `front_door_adjustment_formula` /
  `identify_via_front_door`，独立重实现 FD1/FD2/FD3 和公式模板
- `verify_identify` / `verify_numeric` 接受 `identify_via_front_door`
  作为候补的识别见证 rule

**未包含**：

- 多 mediator 前门（需要链式 P(Z1..Zk|X) 分解）
- 条件化前门（`given` 非空时）
- 潜变量 / 双向边 / ADMG — 这是后续独立 fragment 的地盘

**Done 标志**：14 个测试覆盖结构搜索、公式形状、scheduler 回退、
verifier 接受 / 拒绝三类篡改（mediator / 公式目标 / conditioned query）。
451 passed 全绿。

### Phase 2.latent — 窄 scope（立项 2026-04-21，S1–S4 落地同日；窄化 charter 同日）

**理由**：ROADMAP Phase 2 的 theory-first 启动规则 —— ADMG + m-separation
+ ADMG-aware backdoor / front-door 是对 V0–V5 识别骨架的一次有边界的
扩张；charter（[PHASE_2_LATENT_CHARTER.md](PHASE_2_LATENT_CHARTER.md)）
§0 记录了实现过程中的一次 scope 窄化：generic Tian c-factor / c-forest
/ complete ID 全部移出本 fragment，等真实案例逼出需求时再独立立项。

**交付（runtime）**：

- AST + schema：`BidirectedStatement`（无向 semi-Markov 边，`left` /
  `right` / 可选 `forall` / 可选 `annotations`）；kernel_ast.schema.json
  新增 `bidirectedStatement` $def 并入 `statement` oneOf
- `structural_solver.m_separated` / `is_m_connected` / `c_components` /
  `bidirected_from_ground`：ADMG 上的路径阻塞判定 + 分区原语 + ground
  抽取。m-separation 在 `bidirected=∅` 下与 d-separation 精确一致
  （6-node 全枚举回归 pin）
- `front_door_sets` 增 `bidirected` 形参；FD2 / FD3 在 ADMG 上改用 m-sep
- `minimal_adjustment_sets` 增 `bidirected` 形参；adjustment 有效性改用
  ADMG-aware backdoor m-path 判定
- scheduler：ADMG 程序 identify / effect 先试 ADMG-aware backdoor，失败
  回退 ADMG-aware front-door，仍不通过则 `needs_investigation` +
  `query:identify_admg` / `query:effect_admg`
- gate：ADMG 程序上 cause / assoc / probability 查询仍被 semantic
  validator 拒绝（dispatch 路径未 ADMG-aware）

**交付（verifier, S4）**：

- `VerificationContext.bidirected` 新字段
- 独立 m-sep 重实现（byte-code 扫描 pin：`_verifier_is_m_connected` /
  `_verifier_is_admg_backdoor_connected` 不调用 `structural_solver`）
- 新 rule family：`m_separation_witness` / `m_connection_witness`
- `backdoor_criterion` / `front_door_criterion` rule 在
  `ctx.bidirected` 非空时切换到独立 m-sep 检查
- `themis.verify` 对 ADMG 结果直接 accept，`AdmgVerificationPending`
  从代码路径中移除（类符号保留供历史 import）

**未包含（移出 charter，延后立项）**：

- ~~generic Tian c-factor 公式构造 + Pearl ID 算法递归~~ → **已落地为
  S.3.b.2 fragment**（2026-05-06，见下方 Phase 2.latent §S3.b.2 节）
- ~~c-forest / hedge 作为 unidentifiable witness~~ → **同上**
- IDC / 多 intervention / 多 target / 非空 given 的 conditional ID
- ADMG 下的 cause / assoc / probability 查询（dispatch 路径仍需
  ADMG-aware，独立立项）

**Done 标志**：3 个 ADMG 案例 + DAG 回归（S3.a 正例：hidden-U 前门；
S3.b.1 正例：Z→X→Y, W↔Z, W→Y 的 backdoor；bow-arc 反例：
`needs_investigation`，本 charter 不判 unidentifiable）。verifier
独立性由 byte-code 扫描 + 多个篡改复核测试 pin。640 passed 全绿。

### Phase 5.temporal（立项 2026-04-22，§T / S.T.1–S.T.6 同日落地）

**理由**：按 Phase 5 charter（[PHASE_5_CHARTER.md](PHASE_5_CHARTER.md)）
对 v1.0 核心做一次显式时序解冻，让 kernel 能表达 clean `t-1 -> t`
的相对时间滞后，而不再把这类问题压平成 atemporal DAG。

**交付**：

- AST / schema：`Atom.time_index`（首版只支持
  `{"kind":"relative","value": int}`）
- verifier：`T1_time_monotonicity` / `T2_lag_bound` /
  `T3_unroll_acyclic`
- graph projection：`(predicate, args, time_index)` 视作独立节点
- scheduler：现有 `cause / assoc / identify / effect / probability`
  直接复用时间展开图，无需专门 temporal dispatcher
- e2e：Case 14 的 timed AST / timed query 跑通
- prompt：A1 v2.2 直接产出 `time_index`，不再对 clean `t-1 -> t`
  案例声明 `extensions.ambiguities[kind=temporal]`

**首版 scope**：

- 程序级相对时间轴
- 1 阶 Markov（lag ≤ 1）
- 不引入绝对时间 / 多步 lag / 动作序列 / planner

**Done 标志**：`S.T.1–S.T.6` 全通；Case 14 从“压缩 + temporal
ambiguity”升级为 timed AST / timed query。相关测试 29 passed。

### Phase 5.counterfactual（立项 2026-04-22，§C / S.C.1–S.C.6 窄 scope 落地）

**理由**：按 Phase 5 charter（[PHASE_5_CHARTER.md](PHASE_5_CHARTER.md)）
对 v1.0 核心做一次显式反事实解冻，让 kernel 不再把 clean
Layer-3 反事实问题一律压成 Layer-2 effect proxy。

**交付**：

- AST / schema：`counterfactual` query kind +
  `assumptions.monotonicity`
- runtime：twin-network projection primitive + Balke-Pearl binary
  monotone bounds primitive
- scheduler：缺 monotonicity -> `needs_assumption`；缺 Theta ->
  `needs_investigation`；条件齐 -> `counterfactual_bounded` /
  `counterfactual_solved`
- prompt：A1 v2.3 对 clean "如果当初..." 直接产出 `counterfactual`
  query，不再默认声明 `counterfactual_query` ambiguity
- e2e：Case 17 从 effect-proxy / ambiguity 升级为 real
  counterfactual query path

**首版 scope**：

- bool-only SCM
- 单 intervention / 单 target
- 显式 monotonicity 假设
- 窄 runtime path：优先在无相关 `bidirected` 触碰的 directed ancestral
  subgraph 上恢复 `P(X,Y)`；不适用时回退到局部链式 / 布尔互补恢复

**Done 标志**：`S.C.1–S.C.6` 全通；Case 17 对 clean counterfactual
不再走 ambiguity proxy；并已接上 derivation / verifier / context JSON 外部复核。
当前检查点全量测试：726 passed / 143 skipped。

---

## 一句话结论

**Themis 作为“已知模型下的静态因果推理内核”，已经基本成型。**

更具体地说：

- 已经能在给定结构、给定参数时，对 `cause / assoc / identify / effect / probability`
  做结构推理、公式构造、数值求值、缺口报告和最小工作流闭环
- 已经开始具备“严格推导”的形态：核心结果可附带 derivation，由独立 verifier 复核
- 还没有完成上游世界建模、更宽的 counterfactual / 动作级时序、以及更完整的 ID / 自动建模这些更大层次

所以当前最准确的定位是：

**一个可运行、可验证、可补录的因果推理内核；其静态 DAG 核心已收口，并已显式解冻出 front-door、窄 ADMG、窄 temporal、以及窄 counterfactual fragment。**

---

## 当前核心范围

当前系统范围只包含：

1. **已知变量、已知结构、已知/部分已知参数** 下的推理
2. 静态 DAG 核心 + 已显式立项的 fragment：
   - A6.front-door
   - Phase 2.latent（窄 scope）
   - Phase 5.temporal（窄 scope）
3. 结构查询、数值查询、缺参数闭环
4. 结果解释、confidence、以及 derivation verifier

当前系统范围明确**不包含**：

- 完整自动世界建模平台（事实抽取 / 候选关系收敛 / 自动模型治理）
- 动作序列语义 / 多步时间规划 / 完整动态系统
- 完整潜变量 / 完整 ADMG / complete ID
- 完整 Layer-3 反事实 / 连续反事实 / 通用 twin-network ID
- 通用 agent 行为

---

## 已完成能力

### 1. 语言与输入

- JSON AST + schema
- 有限对象域
- `forall` 实例化
- `cause / probability / observation / query`
- `variableDeclaration`（predicate 层 metadata，opt-in）

### 2. 结构推理

- DAG 投影
- `cause`
- `assoc`
- `identify`
- 后门调整集
- front-door
- 条件 identify（`given`）
- 路径 / 开放路径 / supporting_paths
- 窄 ADMG：m-separation、c-components、ADMG-aware backdoor / front-door
- 窄 temporal：relative `time_index`、time-expanded graph、现有 dispatcher 复用

### 3. 数值层

- `Theta`
- `probability` 查询数值求值
- `effect` 查询通过后门 / front-door 公式数值求值
- 布尔与分类值域
- 缺参数时精确报缺，不瞎算

### 4. 工作流层

- `needs_investigation`
- investigation grouping
- parameter skeleton
- skeleton bundle 提取
- 回填 merge
- 重跑 diff

### 5. 解释与 framing

- 中文 explanation
- 解释与公式/结果的一致性
- `framing_notes`
- A0：问题定义不充分的 advisory 检查

### 6. confidence

- 正式规则：`min(non-None inputs)`
- 结果上可输出 `confidence`
- 解释文本中可呈现 confidence

### 7. 严格推导层（verifier）

已完成到：

- **V0**：`identify` 结构证明
- **V1**：`effect / probability` 数值证明
- **V2**：derivation JSON round-trip
- **V3**：负结构 witness
- **V4**：正结构 witness
- **V5**：context JSON round-trip

也就是说，当前已经能把：

- derivation
- graph
- query
- theta

都序列化出来，然后由 verifier 独立 accept / reject。

---

## V0..V5 当前状态

### V0：Identify Derivation

状态：**完成**

已具备：

- `backdoor_criterion`
- `backdoor_adjustment_formula`
- `identify_via_backdoor`
- verifier 绑定到当前 query
- 真实公式见证约束

### V1：Numeric Derivation

状态：**完成**

已具备：

- `probability_ref_lookup`
- `formula_evaluation`
- `numeric_result`
- `effect / probability` 数值证明与 query/formula 绑定

### V2：Derivation Serialization

状态：**完成**

已具备：

- `derivation.schema.json`
- derivation round-trip
- malformed derivation 统一报 `DerivationSerializationError`

### V3：Negative Structural Witnesses

状态：**完成**

已具备：

- `unidentifiable_via_backdoor`
- `d_separated`
- `no_directed_path`
- theorem family 绑定

### V4：Positive Structural Witnesses

状态：**完成**

已具备：

- `cause_via_directed_path`
- `d_connected_via_open_path`
- supporting path 集合完整性检查

### V5：VerificationContext Serialization

状态：**完成**

已具备：

- `context_to_dict / context_from_dict`
- graph + query + theta JSON 化
- malformed context 统一报 `DerivationSerializationError`
- `effect / probability` query value 只允许字面量

---

## 基本完成但还不算“更大系统完成”的部分

### 1. Framing 三层状态（post slice #36 / #40 / #41）

- **变量框定闭环（kernel / JSON 层）**——**已完成**
  `variableDeclaration`（含 slice #41 的 direction / baseline /
  state_vs_event 共 7 个可选 framing 字段）+ `framing_notes` + F1
  `DEFINE_VARIABLE` investigation + `extract_definition_skeleton` +
  `merge_variable_declaration` + `apply_patch_and_run` 二轮重跑。
  `test_a3_apply_patch` + `test_framing_fields_v2` 已 pin。
- **变量框定闭环（NL / agent 层）**——**已完成（slice #40）**
  第三条 prompt `reply_to_framing_patch.md` 把用户 NL 答复结构化成
  `framing_skeleton_bundle`。A1 的 question / response 两侧加上这条
  答复侧，NL↔JSON 三方对称。
- **变量框定强 gate（问题没框清就拒绝出数）**——**已完成（slice #36）**
  opt-in 的 `program.options.strict_framing: true`。启用时
  `effect` / `probability` 查询在 A0 报出任何 framing gap 时直接
  flip 到 `needs_investigation` 且不出数，F1 DEFINE_VARIABLE
  仍然正常产出填写 skeleton。默认 `false` 保持 advisory 行为。
  15 个 pin 测试覆盖矩阵（见 `test_strict_framing_gate.py`）。

### 2. 真实案例已经能跑，但还没有变成系统上游

当前有：

- `exercise_waist`
- `sleep_focus`
- `tutoring_exam`

当前没有：

- 从真实语料自动构变量
- 从事实语料自动产候选关系

### 3. Confidence 已经是正式语义，但证据来源追踪还没完成

当前有：

- numeric confidence
- explanation 中的 confidence 文案

当前没有：

- 完整 source 结构化
- 最弱证据来源追踪

---

## 还没有开始或明确延后的部分

### 1. 完整上游世界建模平台

当前已经有 NL bridge、narrative merge、variable framing、KB adapter
contract 和 MCP wrapper 这些 down-payment。仍未完成的是：

- 事实抽取
- 候选关系生成
- 模型收敛
- 跨来源冲突解决
- 自动模型治理

这部分是
[WORLD_MODELING.md](WORLD_MODELING.md)
定义的上游层，不是 Themis 当前核心的一部分。

### 2. 更强识别能力

包括：

- 完备 ID

当前明确延后，等待真实案例逼出需求。

### 3. 更宽时序语义

当前已完成 **窄 scope temporal fragment**，但还没有真正的：

- 绝对时间
- `lag >= 2`
- 动作序列
- 动态因果过程

### 4. 更宽问题 gate

当前已经有 opt-in `program.options.strict_framing: true`，能在问题
框定不充分时拒绝 `effect / probability` 出数。仍未完成的是：

- 默认全局强 gate 策略
- 不同 query kind 的细粒度 gate policy
- 上游世界建模输出进入推理前的系统级 gate

---

## 现在可以认为“收口”的部分

如果只看 Themis 核心 + 已显式立项的主要 fragment，这一批内容已经可以
视为当前收口面：

- 静态 DAG 推理语义
- `cause / assoc / identify / effect / probability`
- 结构结果与数值结果
- parameter fill-back workflow
- variable framing workflow + opt-in strict gate
- confidence
- derivation verifier V0..V5
- data-gap report + T10 verifier
- bounds-first 输出
- Phase 6-15 已落地 slice 的当前实现边界

这意味着：

**接下来如果继续改 Themis 核心，应该优先是小修小补、边界澄清、文档
同步和真实压力测试，不应再随意扩大语义面。**

---

## 当前建议

当前更合理的节奏不是继续膨胀核心，而是：

1. 把当前 Themis 视为 **`0.15.0-dev` 收口候选**
2. 同步 README / ROADMAP / CORE_STATUS / charter 状态，避免文档和代码脱节
3. 继续拿真实案例试跑，尤其压测 world-modeling / estimation / data-gap / KB / MCP 组合路径
4. 让下一阶段需求从真实痛点或明确 theory-first charter 里长出来

也就是说：

- 如果真实痛点落在“变量定义补录”，就推进 Variable Framer workflow
- 如果真实痛点落在“来源追踪”，就推进 source metadata
- 如果真实痛点落在“后门不够”，才进入更强识别阶段

---

### Phase 6 = M1 识别层完整化（立项 2026-04-24）

**理由**：VISION.md "扩展愿景"段里确认了从"静态因果推理内核"扩展到
"LLM-native 全板块因果推理编排器"的新方向。Phase 6 是这个扩展的第
一个里程碑——把识别层补齐到 Pearl 因果识别文献的 90%+ 覆盖。

**状态总览**：

| Slice | Charter | 状态 |
|---|---|---|
| 6.iv | PHASE_6_IV_CHARTER.md | **✅ 已落地（2026-04-24）**|
| 6.mediation | PHASE_6_MEDIATION_CHARTER.md | **✅ 已落地（2026-04-24）**|
| 6.front-door-multi | 无独立 charter（扩展既有族）| **✅ 已落地（2026-04-24）**|
| 6.complete-id | 未立 | 可选延至 Phase 6.5 |

#### Phase 6.iv 已落地（2026-04-24）

S.IV.1 – S.IV.7 全部完成：
- `structural_solver.iv_sets`：Brito-Pearl 2002 公式，ADMG-aware +
  conditional IV 搜索（|W| ≤ 3 默认）
- `_dispatch_identify` 回退链：backdoor → front-door → **IV**
- `_build_identify_via_iv` + 2-step derivation（iv_criterion_check
  + identify_via_iv）
- 新 verifier rule family：`iv_criterion_check` + `identify_via_iv`，
  byte-code scan 钉独立性，不调 structural_solver
- `query_result.schema.json` 加 `extensions.iv_identification` 子 schema
- A1 prompt v2.2 §3b：NL 层 IV 识别规则；response_rendering v2.2：
  IV 结果披露 + `iv_validity` ambiguity 模板
- 2 个 eval case（21 valid IV / 22 conditional IV rescue）+ F19
  taxonomy
- DoWhy 0.14 parity：9 个 DAG 案例全部对齐；ADMG 案例文档化为 Themis
  独有能力（DoWhy 无 bidirected 支持）

**Phase 6.iv 新增语言 / 语义面**（解冻清单）：
- 无新 statement kind
- 无新 query kind
- 新增 `QueryResult.extensions.iv_identification` 结构化字段
- `IdentifyResult` 识别策略加 "iv"（在 derivation rule name 层面）

**未包含**：Phase 6 其余 slice（mediation / 多 mediator 前门 / 完整
ID）独立 charter；Phase 7（估计器）、Phase 8（发现 + 敏感性）独立
立项。

**时间实际**：S.IV.1 到 S.IV.7 全部落地约 1.5 天（含 charter 起草）。
Charter 原估 ~4 周是为 4 个 slice（iv + mediation + multi-front-door
+ complete-id）合计；单独 iv 子 slice 的实际耗时证实算法本身不复杂，
主要工作在 verifier 独立实现 + schema 扩展 + eval case 配套。

#### Phase 6.mediation 已落地（2026-04-24）

S.M.1 – S.M.7 全部完成：
- `structural_solver.mediation_sets`：Pearl 2001 四条件 (M1-M4) NDE/NIE
  识别 + 后门式 CDE 识别 (C1-C2)，ADMG-aware，subset-minimal W 搜索
- `EffectQuery.mediator` 可选字段 + `_dispatch_mediation` 在 `_dispatch_effect`
  里短路：STRUCTURALLY_SOLVED + `extensions.mediation_decomposition`
- 三个新 verifier rule：`mediation_nde_nie_check` / `mediation_cde_check` /
  `identify_via_mediation`，byte-code scan 钉独立性
- `verify_effect_structural` 支持 EffectQuery 的识别层结果路径
- `query_result.schema.json` 加 `extensions.mediation_decomposition` 子
  schema（strategy 枚举 / failed_condition 严格约束）
- A1 prompt v2.3 §3c：mediation decomposition 触发模式 + canonical
  example；response_rendering：三类 strategy 展示模板 + M1-C2 plain-
  language 映射
- 2 个 eval case（23 running_metabolism NDE/NIE / 24 drug_inflammation
  recanting witness）+ F20 taxonomy
- DoWhy 0.14 parity：5 个案例覆盖共识与语义差异（DoWhy auto-picks
  mediator，Themis 用户指定 mediator）

**Phase 6.mediation 新增语言 / 语义面**：
- `EffectQuery` 加可选 `mediator: Atom | None` 字段
- `QueryResult.extensions.mediation_decomposition` 结构化字段
- 新 derivation rule names 族（`mediation_*_check` + `identify_via_mediation`）

**未包含**：数值 NDE/NIE 估计（Imai 非参 / g-formula 的 CDE 救援）→
Phase 7；多 mediator 链式前门 → 6.front-door-multi。

**时间实际**：S.M.1 到 S.M.7 全部落地约 1 天（含 charter 起草 + 测试）。

#### Phase 6.front-door-multi 已落地（2026-04-24）

扩展既有 front-door rule family 到多 mediator（无独立 charter）：
- `formula_builder.front_door_formula` 接受 mediator 元组 ≥2，按拓扑
  顺序做 chain-rule 因子分解 `P(Z1,...,Zk|X) = ∏ P(Zi|Z_{<i}, X)`
- `_build_expected_front_door_formula` 镜像扩展（独立重实现，不调
  builder）
- `_rule_front_door_adjustment_formula` 不再硬限制 `len(z) == 1`
- 4 集成测试：parallel-paths ADMG `X → M1 → Y, X → M2 → Y, X ↔ Y`
  通过 {M1, M2} 识别 + verifier 圆环

板块 1 覆盖 60-70% → 75-80%。落地 commit: `219cf5a`。

### Phase 7 = M2 数值估计层（已全落地 2026-04-24/25）

**理由**：M1 完成后用户能问"图能不能识别"但还要"给数字"。Phase 7
打开数据→数字这一环。

**状态总览**：

| Slice | Charter | 状态 | 落地 commits |
|---|---|---|---|
| 7.1 backdoor numeric | PHASE_7_1_BACKDOOR_NUMERIC_CHARTER.md | ✅ | 3935b81 → eb92efd |
| 7.2 front-door numeric | PHASE_7_2_FRONTDOOR_NUMERIC_CHARTER.md | ✅ | 5cdac9a → 7745d5a |
| 7.3 IV numeric | PHASE_7_3_IV_NUMERIC_CHARTER.md | ✅ | aa5867c → 829845e |
| 7.4 mediation numeric | （混入父 charter） | ✅ | 90dad85 → 4e474d1 |

**Phase 7 新增公开 API**：
- `themis.estimate(ast_dict, pandas_df) -> dict`：新顶层入口，数据
  通过 Python 旁路（不进 JSON）保持识别契约纯净
- `themis.estimation.{estimate_backdoor_ate, estimate_frontdoor_ate,
  estimate_iv_ate, estimate_mediation}`：四个独立 estimator
- `themis.estimation.DataContract`：DataFrame 验证 + SHA-256 hash

**Estimator 选择**：
- backdoor：sklearn LogisticRegression / LinearRegression + percentile
  bootstrap CI
- front-door：Pearl 3.29 plug-in，单/多 mediator chain-rule
- IV：Wald (binary Z+X) + 2SLS (continuous)，auto select
- mediation：statsmodels.stats.mediation.Mediation (Imai 2010
  algorithms 1+2)，作 production backend

**Verifier 松弛审**：4 个新 rule（`numeric_{backdoor,frontdoor,iv}_estimate`
+ mediation 走原 `identify_via_mediation`）。不重新训练（sklearn /
bootstrap 引入随机性使 bit-exact 复检不现实），只审 method enum +
point in CI + data_hash 格式 + adjustment 与识别 step 的一致性 + 字
段 disjoint 等。byte-code scan 钉独立性。

**Schema 扩展**：`numeric_estimate` 顶层字段 + `estimation_context`
+ `decomposition` 子块（mediation 用）。method enum 8 个值
（backdoor / frontdoor / iv / mediation × linear/logistic）。

**dispatch 优先级**：mediation queries (q.mediator 设) → backdoor
→ front-door → IV。每条路径失败/不适用时静默跳过。

**未包含**：CATE / ITE、AIPW、TMLE、Causal Forests Python
简化版、deep causal、连续 treatment IV、CDE 数值（参考 m 值）。

**时间实际**：Phase 7 整体（4 个子 slice）约 2 天落地。

板块 6 中介 50% → 70%；板块 11 数据驱动估计 0% → 50%。

### Phase 8 = M3 因果发现 + 敏感性（已全落地 2026-04-25）

**理由**：到 M2 为止 Themis 假设用户给图。M3 解决"图从哪来"
（discovery）和"图错了 / 假设违反时怎么办"（sensitivity）。

**状态总览**：

| Slice | 状态 | 落地 commits |
|---|---|---|
| 8.1 discovery (PC/FCI/LiNGAM) | ✅ | e2b2677 → 48a7e6f |
| 8.2 sensitivity (E-value) | ✅ | e1d8bdc → 97daad6 |

**8.1 Discovery**：
- `themis.estimation.discover_graph(df, algorithm="auto")` 包装
  causal-learn 0.1.4.5 的三个算法
- `discovery_to_kernel_ast(result)` 把 DiscoveryResult 转成可直接
  喂 `themis.run` 的 kernel_ast 草稿
- Algorithms：PC（无潜变量假设，CPDAG），FCI（容许潜变量，PAG），
  LiNGAM（线性非高斯，DAG）；'auto' 按 skewness 选 LiNGAM/PC
- Output 三桶：directed / bidirected / ambiguous（CPDAG 或 PAG 圆环
  端点）
- Ambiguous edges 自动转成 `extensions.ambiguities[kind=
  ambiguous_orientation]`，附 disambiguation_ask
- 5 条 API gate 审计：causal-learn ⚠ track record 4 年（接近但未达
  5 年门槛），其他 4 条满足；定为 production-with-caution，pin 版本

**8.2 Sensitivity**：
- `e_value_for_risk_ratio(rr)`：VanderWeele & Ding 2017 closed form
- `e_value_from_ate_binary(ate, baseline_rate, ci_bound)`：从 ATE
  自动转 RR 再算 E-value
- 在 `dispatch.py` 的所有 4 个 estimator 路径尾巴自动调用
  `_attach_e_value_if_binary`，仅对 bool outcome 触发
- `numeric_estimate.sensitivity_analysis` 子 schema：e_value /
  e_value_ci_bound / risk_ratio / baseline_rate / note
- response_rendering 加专门 disclosure section + 4 档威胁水平模板
- F22 加入失败模式 taxonomy

板块 10 敏感性 0% → 30%；板块 12 因果发现 0% → 40%。

**整体加权覆盖**：从 Phase 6 启动时的 ~20% 跃升到 **50-60%**。

**时间实际**：Phase 8 整体（2 个子 slice）约 1 天落地。

---

## 最短版本

```text
Themis 已经从识别内核演化成全栈因果系统：
- 识别（M1）：backdoor / front-door 单+多 / IV basic+conditional+ADMG / NDE-NIE-CDE
- 估计（M2+Phase14）：backdoor / front-door / IV / mediation / dose-response 都能给数字 + CI 或结构化失败
- 敏感性（M3.1）：每个 binary outcome 自动带 VanderWeele E-value
- 发现（M3.2）：用户给 DataFrame 没图时 PC/FCI/LiNGAM 自动建图建议
- 诊断（Phase10-13）：data_gap_report + bounds-first + dose-response 数据规格
- 全程 verifier 松弛 / 严格审，每步带 derivation

12 板块加权覆盖 ~65-75%。
但仍不是完整世界建模系统；
完整反事实（Layer 3 全套）、动作级时序、自动语料建模仍在后续 Phase。
```

---

### Phase 4 down-payment + 双面 bridge 打磨（2026-04-25）

把 Phase 7+8 落地后暴露的输入/输出 bridge 缺口补齐，把 Phase 4 上游层
从 prompt-only 推到端到端可跑。

**输出 bridge：response_rendering.md v3 + v3.1**
- 补 numeric_estimate 渲染（per-method 模板）/ IV trigger via numeric
  path / bidirected provenance / numerically_solved + 仍开 requests /
  schema mismatch / E-value 中英 band 对齐 / structure-group / framing_notes dedup
- 4 个 blind 子代理在 cases 25-28 输出端 blind 验证：v3 关闭 10 个 gap
- `themis/estimation/sensitivity.py` note 嵌入中文 band 与 prompt 表对齐

**Phase 4 上游层端到端**
- `merge_edge_extractions` / `merge_edges_into_program`：对称变量合并；
  ADMG cause+bidirected 共存（修了一个真 bug，refusal vs edge 互斥）；
  保留 atom 上的 `time_index`（吃下 case 14 V-set）
- `compose_program(base, vars?, edges?)` 端到端胶水
- annotation schema 加 `evidence`（A2 一直在 emit，schema 之前拒收）
- e2e blind 压测：3 个子代理跑 A1+A5+A2，合成 + run，3/3 通过：
  case 14 (temporal `cause=true`) / 16 (selection `cause=false`) /
  21 (IV ADMG `needs_investigation`)

**kernel V-set 放松**（charter-free，小修）
- `graph_projection.project()` 为带 VariableDeclaration 的 query 原子
  加孤立节点。Refusal-only 图（case 16）正确返回 `cause=false (no path)`
  而非 SemanticError；未声明的原子仍被拒，V-set 严格性 6 测全过。

**MCP server**（task #35）
- `themis/mcp/server.py` FastMCP 包装：5 个 kernel / audit 入口（run /
  apply_patch_and_run / verify / verify_data_gap_report / estimate）+ 1 个
  catalog tool；7 个 prompts + 5 个 schema 作为 resources；不调 LLM
- README + 8 个 in-process 测试

**A2 prompt 小补**：refusal `suggested_confounder` →
`pattern: confounder|collider|reverse_causation|coincidence` +
`suggested_node`（按 pattern 解释）

**DoWhy parity flake 修**：mediator 选择非确定 → 只断言 DoWhy 返回
identification，不锁选哪个

**测试**：1015 passed / 143 skipped（本轮 +28）；0 fail；0 known flake。

---

### Phase 9 §T9.1 单源转移识别（2026-04-25 落地，板块 9: 0% → 25-30%）

**真实压力来源**：W0 跑步 case 闭环后用户反问 "文献是 35-50 男性 RCT，
我是 28 女 BMI 正常，0.55 这个数字适不适用"。这是 transportability
问题——板块 9，之前 0% 覆盖。

**charter**: PHASE_9_TRANSPORT_CHARTER.md（slice 内立项 + 7 sub-slice）

**理论基础**：Bareinboim & Pearl 2014 "A General Algorithm for Deciding
Transportability" Theorem 1（充分条件）：Z is S-admissible iff Z
d-separates {S nodes} from Y in G_{\\bar{X}}.

**OSS 现状检查**：DoWhy / EconML / causal-learn 都没有 Bareinboim
selection-diagram transportability 的 production 实现；只有学术论文 +
Causal Fusion (Columbia) web demo。Themis 做这块属于 **Python OSS 内
首发**。自家写，不 vendor。

**7 sub-slice 落地状态**：

| Slice | 内容 | 状态 |
|---|---|---|
| S.T9.1.1 | schema (selectionNodeStatement / population / target_population) | ✅ |
| S.T9.1.2 | types + parser + transport_runtime_gate | ✅ |
| S.T9.1.3 | identify (s_admissibility_check / transport_formula / identify_via_transport) + scheduler dispatch hook | ✅ |
| S.T9.1.4 | verifier T9-1 / T9-2 独立审 + 字节码独立性钉死 | ✅ |
| S.T9.1.5 | eval case 29 (跑步瘦肚子 transport) + 4 e2e 测试 | ✅ |
| S.T9.1.6 | A1 §3f population mismatch + response_rendering transport disclosure | ✅ |
| S.T9.1.7 | docs sync (本节 + COVERAGE_MAP + failure_modes F25) | ✅ |

**端到端**：跑步 case 现在跑通：

```
NL: "meta-analysis 是 35-50 男性，我 28 女 BMI 正常，能套吗"
↓ (A1 §3f)
kernel_ast: 3 selection_nodes (S_age/S_sex/S_bmi) + effect query w/ target_population=user
↓ (themis.run + _dispatch_transport)
status=structurally_solved, formula=P*(belly_fat_loss|do(running)) = Σ_{age,sex,bmi} P(...|...,Z) · P*(Z)
↓ (themis.verify)
T9-1 重跑 S-admissibility ✓; T9-2 审 formula 形状 ✓
↓ (response_rendering Transport disclosure)
"结构上可识别，调整集 = {age,sex,bmi}；要给数字还需要源人群分层 P 和你的 P*(Z)"
```

**显式 out-of-scope**（charter §4 已划清，按需另立 fragment）：
- §T9.2 数值估计（IPSW / TMLE-transport）
- §T9.3 latent S（不可观测的人群差异）
- 多源 transport（Bareinboim 2014 §5）
- 自动从 dataset 检测人群差异（discovery 范畴）

**测试**：1064 passed / 143 skipped（+49 from baseline 1015）；0 fail；
0 known flake。新增：
- 15 schema/types/gate (test_phase9_transport_schema)
- 13 transport primitive (test_runtime/test_transport)
- 7 verifier (test_verifier/test_transport_rules)
- 4 case 29 e2e (test_e2e/test_case_29_transport)

**新失败模式**：F25 transport / population mismatch（failure_modes.md）

**加权覆盖跃升**：约 55-65% → **60-70%**。第一次给板块 9 一个真实的
非零数字。

### Phase 10 数据缺口诊断器（2026-04-26 落地，VISION 定位收紧的输出 (2)）

**真实压力来源**：2026-04-26 用户战略反思——"构建量化的因果关系太难
了，主要是缺乏数据"。这是因果推理学科根本天花板，不是 Themis 工程
问题。结论：把 Themis 重新定位为**因果断言验证器 + 数据缺口诊断
器**，不再追求"任何因果问题都能给数字"——卖给用户的是"告诉你这问
题能不能算 + 不能算缺什么数据"。这是 DoWhy / EconML / ChatGPT 都不
做的独占生态位。

**VISION 同步**：VISION.md 加新节"定位收紧 (2026-04-26)"——两段式
输出契约：(1) 全面检查（已有）+ (2) **数据缺口报告（新）**。
"当前原则"加第 5 条："数据缺口诊断 ≥ 数值估计"。

**charter**: PHASE_10_DATA_GAP_REPORT_CHARTER.md（7 sub-slice）

**理论基础**：不需要新理论 fragment——所有信号都在现有 derivation /
investigation_request / framing_note / extensions 里，Phase 10 只是
**结构化聚合 + 转换为 actionable 数据需求**。

**OSS 现状检查**：无同类。流行病学有 Hernan "What If" 第 II 部分讲
study design recommendation，但都是教科书，没有工程实现。Themis 做
这块属于**全 OSS 内首发**。

**7 sub-slice 落地状态**：

| Slice | 内容 | 状态 |
|---|---|---|
| S.10.1 | schema (`data_gap_report` / `dataGap` $def / 8 gap_kind / 3 severity / 4 ref_kind / derivation step `success`) | ✅ |
| S.10.2 | types (`DataGap` / `DataGapReport` dataclass + `DerivationStep.success` + result_orchestrator 序列化) | ✅ |
| S.10.3 | generator (`themis/output/data_gap_report.py` 8 + 1 classifier 分支 + severity 排序 + scheduler `_attach_data_gap_report` 挂载) | ✅ |
| S.10.4 | verifier T10-1 / T10-2 / T10-3 + byte-code 独立性钉死 (forbidden import + 独立 failure-rule 注册表) | ✅ |
| S.10.5 | 5 e2e gap_kind 全覆盖 + multi-gap 排序 + `themis.verify` round-trip | ✅ |
| S.10.6 | response_rendering v3.2 加 §"Data gap report rendering" 8 中文模板 + severity 排序 + multi-gap 措辞 + "禁止吞 gap" 硬规则 | ✅ |
| S.10.7 | docs sync（本节 + COVERAGE_MAP + failure_modes F26 + VISION 已在定位收紧节落地） | ✅ |

**端到端**：missing_parameter 案例闭环：

```
NL: "diet_control 干预下 waist_reduced 的 ATE"
↓ (themis.run)
status=needs_investigation, derivation=identify_via_backdoor (success=true),
investigation_requests=[{group=parameter, target=P(waist_reduced=True|...)}]
↓ (_attach_data_gap_report)
data_gap_report:
  summary: 缺概率分布 P(waist_reduced=True|...)
  gaps: [{kind=missing_distribution, severity=blocking, signature=conditional,
          required_data={data_type=ipd}, alternative_paths=[Balke-Pearl bounds]}]
  actionable_next_steps: [补 ... → 可给点估计, 或：接受 bounds]
↓ (themis.verify → T10-1/2/3)
T10-1 provenance ref ✓; T10-2 失败 step + 参数 request 全覆盖 ✓; T10-3 kind 一致性 ✓
↓ (response_rendering §Data gap report rendering)
"识别上没问题，但要给点估计还缺一个条件分布 P(...)，类型需要 IPD..."
```

**显式 out-of-scope**（charter §4 已划清）：
- 任何 I/O / API 调用（**绝对禁止**——生成器是纯 reasoning，需要外部
  数据是 Phase 11+ KB 接入的事）
- 样本量精确计算（statistical power）—— `min_sample_size` 字段允许
  填，但生成器自己不算
- 自动 KB 查询填补 gap → Phase 11+
- 多 gap 之间的优先级排序算法（按 severity + derivation order 已够）
- 可视化（DAG with red gap edges）

**测试**：1168 passed / 144 skipped（+104 from baseline 1064）；0 fail；
0 known flake。新增：
- 33 schema (test_output/test_phase10_data_gap_schema)
- 17 types (test_output/test_phase10_data_gap_types)
- 24 generator (test_output/test_phase10_data_gap_generator)
- 25 T10 verifier (test_verifier/test_data_gap_rules)
- 5 + 1 e2e gap_kinds (test_e2e/test_phase10_gap_kinds)

**新失败模式**：F26 silent data-gap suppression（failure_modes.md）

**加权覆盖**：板块覆盖率不变（Phase 10 不在 12 板块内），但 Themis
的产品定位重大跃迁——从"全板块编排器"扩展为"全板块编排器 + 数据
缺口诊断器"。这是 VISION 写明的**独占生态位**第一次有可交付实现。

---

## Phase 11.1 prompt-only 闭环 (2026-04-26 → 2026-04-27, S.11.1.1-3)

新增 `docs/prompts/gap_to_action.md` —— LLM 拿到 `data_gap_report` 后
按三个原则（结构可修？数据 vs 用户选？dtype 匹配？）自主决策下一步动
作（autonomous fetch / ask user / 终止），不再编造。MCP 注册 + 子 agent
真测找到并修了 transport 对偶 gap、prompt 的 schema 不匹配漏洞、
literature numeric 缺渲染模板等问题。

S.11.1.2-3 prompt elegance pass：`gap_to_action.md` / `response_rendering.md`
/ `nl_to_kernel_ast.md` 三个最累 prompt 从枚举换原则 + worked example，
2255→1652 行 (-27%)。子 agent 真测每次都找出 ~3 个真洞已立即修复。

零代码改动：所有挂 Themis MCP 的 LLM 客户端读到这份 prompt 即可。

## Phase 11.2 KB adapter 契约 (2026-04-27, S.11.2.1-7)

`themis/kb/` package 落地：

- **schemas.py**: `KBQuery` / `KBResult` / `KBProvenance` 数据类 + 7 个
  `KBQueryKind` (映射自 gap_kind) + 6 个 GRADE-style `KBConfidenceGrade`
  + JSON dict 双向转换
- **contract.py**: `KBAdapter` ABC + `KBRegistry` 客户端容器
- **translator.py**: `gap_to_kb_query()` + `kb_results_to_bundle()` 纯
  函数；3 个 gap_kind 不可 KB-fixable 时返回 None
- **cache.py**: `KBCache` (SQLite, 无 TTL, 可缓存负结果)
- **adapters/websearch_proxy.py**: reference adapter 包装客户端 search_fn
- **MCP 暴露**: 2 个 schema 资源 + 1 个新 prompt (`kb_lookup.md`)
- **关键架构边界**：Themis 自己不发任何网络请求；adapter 实例化 + 执行
  在客户端 / 第三方 repo（详见 `PHASE_11_2_KB_ADAPTER_CHARTER.md` §1）

子 agent 真测找到一个 pre-existing bug：`SelectionNode` 漏在
`_statement_to_dict` 里，让任何 transport 程序过不了 `apply_patch_and_run`
—— 已修复并加 transport 全闭环 e2e 回归测试。

**测试**：1266 passed / 144 skipped（+95 from 1171）；0 fail。

**显式 out-of-scope（已划清）**：
- ❌ 真实 PrimeKG / SciGraph / SemMedDB adapter 进 themis 主仓 → 必须
  sibling repo 形态（详见 `project_kb_adapter_invariants.md` 记忆）
- ❌ Themis 内置任何 HTTP client / 数据库 driver
- ❌ 跨 KB 冲突解决（S.11.7 元基础设施扩展）
- ❌ async adapter（先做同步契约）

## Phase 12 bounds-first (2026-04-27, S.12.1-6)

兑现 Phase 10 的"alternative_paths 接受 bounds"承诺 —— 之前是空话，
现在 kernel 真在算 bounds。

- **types + schema**: `BoundsMethod` enum (manski_natural / balke_pearl_iv /
  frontdoor_partial / manski_tamer_monotonicity) + `BoundsResult` 数据类
  + `QueryResult.bounds_result` 字段 + JSON schema $def
- **themis/output/bounds.py**: `attempt_manski_natural`（无假设，binary
  outcome 自然界限）+ `attempt_balke_pearl_iv`（Pearl 1995 §3 / BP 1997，
  binary 三元组 + IV1/IV2/IV3）
- **scheduler `_attach_bounds_result`**: identify 失败时自动尝试；BP 优先
  Manski 兜底；轻量 IV 检测（程序图里 Z→X 且无 Z→Y 且 Z 是 bool → 取
  作 IV）
- **response_rendering.md**: 新 §"Bounds rendering"（placement / per-method
  shape / uninformative-bounds 反模式 / 不要伪装界限有用）
- **subagent 真测**找到 2 真 bug，都已修：
  - `unidentifiable_no_admissible_set` 在 ADMG 不可识别 effect query 漏
    发（`query:effect_admg` prefix 不被 classifier 接 → 已扩展前缀列表）
  - BP-IV 在用户给 IV-shape 但 kernel 没跑 IV identification 时不触发
    （lightweight structural 检测补上）

测试：1335 passed / 144 skipped（+~80 Phase 12 新增）；0 fail。

### Phase 12 followup (2026-04-27 同日，9 场景真测驱动)

`themis.run` 跑 9 个真实场景（W0 跑步 / sleep+bidirected / 非 binary BP /
mediation / transport / counterfactual / conditional effect / happy path /
apply_patch_and_run）逐个查 alt_paths × bounds_result × required_data 对齐，
找出 5 真 bug + 配套 UX/sample_size 补齐。8 commits：

- `57785c7` reconcile alt_paths：算出的 method 名替换静态 "Balke-Pearl"
- `2d8e731` `GapBlocks.INTERPRETATION` 新增；framing gap 不再谎称 block
  identification
- `1557289` blocking gap 没提 bounds 时 prepend 已计算结果（让
  actionable_next_steps 看得到）
- `4845746` 非 binary outcome 时 bounds attempt 返回 None → strip 静态
  bounds 承诺，不留空头支票
- `919f1b2` response_rendering：blocking 存在时 framing 折叠成一句话
  （subagent 之前提的 UX 改进）
- `8b100ea` 移除 alt_paths 里泄给用户的内部章节号 "§T9.2"
- `8d23b00` mediation NDE/NIE sample_size（2.5× simple ATE 启发）
- `670abf7` transport sample_size（target marginal + source conditional
  按 2^k strata 缩放）

测试：1350 passed / 144 skipped（+15 followup 新增）；0 fail。

显式 out-of-scope（仍未做，按真实压力）：
- 数值 bounds estimator（symbolic 已经够用作 validator 输出）
- Frontdoor partial / Manski-Tamer monotonicity 等更高级方法
- 非 binary outcome 的 bounds
- IV 路径 sample_size（gap 是结构性"找 IV 变量"，不是分布，无 n 可算）

## Phase 13 dose-response diagnostic (2026-04-28 落地)

**真实压力来源**：用户问的不是二元 ATE，而是"X 让 Y 增加多少 / 关系图 /
从 A 到 B 怎么变"。这类问题不能再被静默压成 binary effect。

**交付**：

- 新 `GapKind.DOSE_RESPONSE_DATA_REQUIRED`
- `GapRequiredData` 扩展 sampling points / sampling_point_count /
  confounders_required / time_window / sutva_concerns
- data-gap classifier 能把 dose-response 问题转成可执行数据规格
- A1 prompt 新增 `dose_response_query` ambiguity
- response rendering 明确区分"诊断清单"与"真实画曲线"

**边界**：Phase 13 不估计曲线，只告诉用户画曲线需要什么数据和假设。
真实估计由 Phase 14 接手。

## Phase 14 dose-response estimator (2026-04-28 落地)

**定位变化**：`themis.estimate(...)` 从 binary treatment ATE 扩到连续 /
多剂量 treatment 的 dose-response curve。kernel 仍保持纯 JSON；估计层走
DataFrame 旁路。

**已落地 slice**：

- slice a：EconML `LinearDML` wrapper，输出 `dose_response_curve`
- slice b：`model='auto'|'linear'|'forest'`，`CausalForestDML` explicit opt-in
- slice c：typed `EstimatorFailure` + overlap pre-check
- slice b.2：`model='drlearner'`，LinearDRLearner + T 离散化，可恢复
  T-Y 非线性；`auto` 在样本量和采样点足够时选择 drlearner
- followup：verify roundtrip 与 model-string normalization 修复

**当前边界**：

- 依赖 EconML / sklearn 等估计栈；缺依赖或数据契约不满足时返回结构化失败
- CATE / 自动 hyperparameter 搜索 / 多 outcome dose-response 仍不在当前范围
- 统计有效性依赖 overlap、样本量、模型设定；Themis 只承诺显式披露方法和失败原因

**当前全量测试**：1402 passed / 144 skipped, warning-clean。

## Phase 15 world-modeling pressure harness (2026-04-30 起步)

**定位**：不新增内核语义，不接 LLM。把已有 A1/A2/A5 prompt examples、
`themis.upstream.compose_program(...)`、`themis.run(...)`、`verify` /
`verify_data_gap_report` 串成可重复压测，先暴露上游世界建模真正卡点。

**当前脚本**：

```powershell
python scripts\run_015_world_modeling_pressure.py
```

**已固定的 5 个压力用例**：

- `exercise_waist_variable_merge`：narrative framing 能缩小 `running`
  的 gap，但 target `belly_fat_loss` 仍完整欠框定，且 effect 仍缺分布数据
- `late_sleep_predicate_drift`：question 用 `stays_up_late` /
  `feels_tired_next_morning`，narrative 用 `staying_up_late` /
  `cognitive_slowness`，导致补录无法复用 —— 暴露 predicate linking 缺口
- `late_sleep_predicate_links_rewrite_edges`：同一份已确认 predicate link
  bundle 能同步改写 A2 edge endpoints，避免边把旧谓词名重新带回图里
- `coffee_latent_edge_assoc`：A2 能抽出 bidirected latent edge，ADMG
  assoc query 现在经 `m_connection_witness` 返回结构解，并可被 verifier 复核
- `ice_cream_refusal_filters_edge`：A2 refusal 能过滤 A1 question-side
  naive direct edge，最终 cause query 返回 `false`，拒绝理由保留在
  `extensions.ambiguities`

**当前 followup**：

- `themis.upstream.diagnose_predicate_links(...)`：对 narrative extraction
  里未命中 base program 的 predicate 产出候选 link 诊断；只建议、不自动重写
- `themis.upstream.diagnose_edge_predicate_links(...)`：对 A2 edge /
  refusal endpoints 做同类候选诊断；去重后只输出待确认项
- `themis.upstream.apply_predicate_links(...)`：消费已确认的
  source -> target link bundle，重写 narrative variables 后再走既有 merge；
  多个 source 合到同一 target 时复用字段冲突检查
- `themis.upstream.apply_predicate_links_to_edges(...)`：同一 confirmed
  link bundle 可重写 A2 cause / bidirected endpoints 与 refusals，保证
  变量合并和边合并使用同一套 predicate 对齐
- `themis.upstream.compose_program(..., predicate_links=...)`：把 confirmed
  link bundle 作为统一入口，同时应用到 variables 和 edges，降低调用方漏改一侧的风险；
  link target 必须已存在于 base program variables，否则抛 `PredicateLinkError`
- 0.15 压测输出现在包含 `predicate_link_diagnostic`，能把
  `staying_up_late -> stays_up_late` 这种形态漂移高分暴露出来，同时把
  `cognitive_slowness` 这种低 lexical evidence 保持为待确认项
- exercise 压测也固定了低 lexical evidence 的 target link：
  `waist_reduced -> belly_fat_loss` 只作为候选出现；确认回注后不会新增
  predicate，`belly_fat_loss` 的 framing gaps 会缩小，但
  `missing_distribution` 仍保留
- late_sleep 压测现在还证明：确认 link 后不会新增 predicate，query 侧
  `stays_up_late` / `feels_tired_next_morning` 的 framing gaps 会按已补字段缩小
- narrative edge refusal 现在由 `apply_edge_refusals(...)` 在
  `compose_program(...)` 内先执行：只删除 exact directed `cause` match，
  不删除反向边或 bidirected；拒绝理由写回 `extensions.ambiguities`
- A2 的 `narrative_ambiguities` 现在由
  `merge_narrative_ambiguities_into_program(...)` 保留到最终 program 边界；
  coffee ADMG case 会同时保留 latent-common-cause ambiguity 与 refusal
  audit trail
- Phase 2.latent S4 的窄 runtime gate 已放开 `assoc`：ADMG 程序上的
  association 查询走 m-separation；`cause` / `probability` 仍保持 gate

**当前全量测试**：1420 passed / 144 skipped, warning-clean。

## Phase 2.latent §S3.b.2 — Tian / Shpitser ID（2026-05-06 落地）

**真实压力来源**：bow-arc 形 ADMG 案例（X ↔ Y 直接 latent confounder）当
backdoor / front-door / IV 全失败时落到 needs_investigation。c-component
分解 primitive 已经在 `structural_solver` 里了，闲置；hedge witness 形态
是 ADMG 不可识别中最常见的一种。Phase 2.latent charter §4.2 记的延后条件
（"实际案例逼出"）触发。

**交付**：

- `themis/runtime/c_factor.py`：Shpitser-Pearl ID 算法在 kernel identify
  query shape 上的 restriction（单 intervention / 单 target / 空 given）。
  覆盖递归 Lines 1-6：祖先收缩、后代排除、c-component split、hedge
  witness、Q[S] 乘积形式
- 新 derivation rule family：
  - `tian_c_decomposition`：声明性 c-decomposition step
  - `identify_via_tian`：terminal rule，结果 `StructuralResult(True)` +
    c-factor 公式
  - `tian_hedge_witness`：terminal rule，结果 `StructuralResult(False)` +
    hedge graph
- scheduler dispatch：ADMG 上 backdoor / front-door / IV 全失败后回退到
  Tian
- Line 7（递归符号 substitute under Q[S'] re-factorization）返回 None；
  scheduler 落到 `needs_investigation`，**不假声 unidentifiable**

**未包含**：

- Line 7 完整 ID*（递归 Q[S'] re-factorization）
- IDC（conditional ID）/ 多 intervention / 多 target / 非空 given
- ADMG 下的 cause / assoc / probability 查询（dispatch 路径仍需 ADMG-aware）

**Done 标志**：8 个测试覆盖正例（c-decomposition）+ 反例（hedge witness）
+ Line-7 fall-through。bow-arc 之前 `needs_investigation`，现在
`structurally_solved` value=False + `tian_hedge_witness` rule。

板块 2 ADMG 80% → ~85%。

---

## Phase 5 §T runtime 强制（2026-05-06 落地）

**真实压力来源**：Phase 5 §T 标"已落地"，但 verifier 的 T1 / T2 / T3
primitive 从未被 runtime 调用——意味着 kernel 程序声明 `X@t=1 cause
Y@t=0`（因果反向跑）会被 kernel 静默接受。这是一个真实的语义漏洞。

**交付**：

- `semantic_validator` 新增 `temporal_monotonicity` 检查：parse 时拒绝
  `CauseStatement` 当 `src.time_index > dst.time_index`。无 `time_index`
  的 atemporal endpoint 旁路（处于虚拟 atemporal slice，顺序不指定）
- T2_lag_bound verifier rule：从 `|lag| ≤ 1`（一阶 Markov 脚手架）放宽
  到 `lag ≥ 0`。真实案例——1 周糖 → 蛀牙、1 月训练 → 马拉松时间、多日
  压力 → 疲劳链——都需要 `lag > 1`。T2 现在与 T1 冗余（都强制非负），
  保留在 registry 让既有 derivation 引用 T2 仍能验证

**测试**：`tests/test_temporal_enforcement.py` 7 个新测试。负例：反向时间
被拒；正例：向前 / 同时 / 部分 atemporal 接受、多日 lag 和混合 lag 链
接受。既有 T2 unit test 更新到断言放宽。

---

## Web UI mode (a) + (b)（2026-05-06 落地）

**定位**：peripheral surface——给没有 agent / MCP 的非开发者用户一个
可点的探索入口。kernel 仍纯 JSON，不被这层污染。

**Mode (b) — paste-JSON 探索**（commit `f420a70`）：

- `python -m themis.web` → FastAPI `http://127.0.0.1:8000`
- 单页 UI 把 result envelope（explanation / ⚠ caveats /
  structural_result / numeric_result / bounds / data_gap_report /
  derivation）渲染成比 raw JSON 易读的形式
- POST `/api/run` / POST `/api/verify` / GET `/api/examples`（从
  `docs/prompts/examples/` 加载 worked NL→kernel_ast pairs）
- localhost-bound 默认；`--host 0.0.0.0` 局域网共享

**Mode (a) — LLM bridge**（commit `dfdf1c7`）：

- 中文问题 → LLM emit kernel_ast → `themis.run` → LLM render 中文回复
- `themis/web/llm_bridge.py`：包装 anthropic SDK，两个函数
  (`nl_to_kernel_ast` / `render_reply`) + e2e `ask()`
- POST `/api/ask` 返回 `{nl, kernel_ast, envelope, reply}`；失败返回
  400 + `{stage, error, message}` + 中间 artifacts（让 UI 能调试
  mid-pipeline 中断）
- `LLMBridgeError` 与 kernel 异常区分开，API 能正确归因失败 stage

**未包含**：

- 公网部署（kernel 自己不发网络请求；公网部署是客户端 / sibling repo
  的事）
- 鉴权 / rate limit / billing — 当前 demo 级别
- mode (a) 的 LLM provider 切换抽象（当前固定 anthropic）

**测试**：`tests/test_web_app.py`（6）+ `tests/test_web_llm_bridge.py`（13）。

---

## 下一步候选（按真实压力等待选）

- **真人测试** — 找不熟项目的人跑一遍 MCP / web UI（一直没做，是诚实
  的 gap）
- **样本量扩展** — sample_size 接到 mediation / IV / transport 路径
- **更多 gap_kind / 更深检测** — dtype mismatch / IV 强度不足 /
  propensity overlap / SUTVA 违反
- **bounds 扩展** — frontdoor partial / Manski-Tamer monotonicity /
  非 binary outcome / 数值层
- **A1/A2/歧义识别更广** — 输入诊断更准
- **V0-V5 + T10 verifier 更深规则** — 验证器更严
- **Tian Line 7** — 完整 ID* 递归（当前案例没逼出，但延后随时可立项）

**注**：Phase 11 母 charter §3 列的 S.11.3-S.11.7（PrimeKG / SciGraph /
SemMedDB / Wikidata / 冲突解决）**已废弃** — "LLM 怎么搜资料不关我们
的事"（2026-04-27 用户校正）。adapter 在客户端，Themis 不教 LLM 怎么
找数据。详见 `project_kb_adapter_invariants.md` 记忆。
