# Phase 17 — 策略表：识别 / 估计 / 缺口合成一次求值

> 状态：**立项 2026-07-28，未开工**。用户定的第一原则：结构要优雅简洁，
> 改动成本不是选型依据。本 charter 据此只给最优结构，不给便宜的过渡方案。

## 根因假设

**现象**。近九档工作里六档是修复型，失败形状高度一致：同一个问题换个入口
问会得到不同答案、或凭空拒答、或答案正确但依据没露到人眼前。**没有一档
是「公式算错了」**——最接近的簇列那档，错法也是「一句声明被静默丢掉」。
信息从来不缺，缺的是传递。

**根因**。一个语义事实（"这次用了条件工具变量" / "这次做了中介分解" /
"这次的误差落在结局上"）在系统里**没有一等表示**。它只以两种形态存在：
某个 dict 的一个 key，和散在三个文件里的若干 if 分支。key 是约定不是契约，
分支是手写不是派生。凡是需要跨路径一致的性质——能力对等、披露完整、
验证覆盖——都退化成「必须记得去改另外 N 个地方」，而**漏改不会报错**。

**为什么是根因不是表象**。三条独立证据：

1. **同一组守卫写了两遍，顺序还不一样。** `_dispatch_effect`（识别层）与
   `_estimate_effect_queries`（估计层）都是「先匹配先赢」的守卫级联，守卫
   条件几乎同名同义，但 `target_population` 在识别层排第 3、在估计层排第 5。
   同时命中两个守卫的查询，两层会路由到不同策略。这不是谁忘了接线，是
   **同一个决策被表达了两次然后各自演化**。
2. **`data_gap_report` 末尾有一个 `_classify_residual_investigation_items`
   兜底分类器。** 只有当你在残渣上做模式匹配时，才需要一个「猜漏了的」兜底。
3. **架构默认值对最了解它的人同样生效。** 2026-07-28c 那档，我在刚写完
   `augment_assumption_ledger` 的孪生规则之后，立刻又被自己那条规则吞掉了
   新块的假设（账本里一条都没有，端到端测试才抓到）。这不是粗心，是默认
   沉默在起作用。

**拟做的结构性修改**。把「策略」升为一等对象，把识别、拒答、缺口报告变成
**同一次求值的三种读法**：满足的前置条件 → 答案；不满足的 → 缺口；被援引的
→ 假设账本。守卫写一次，优先级是数据不是行号，块登记与可达性矩阵由策略
声明派生而非另行维护。

---

## 实测的现状（2026-07-28，全部为本机 grep/AST 实测，非文档转述）

| 项 | 实测值 |
|---|---|
| `themis/` 总行 | 74,940 |
| `tests/` 总行 | 76,086（**测试 > 代码**） |
| 最大文件 | `verifier/rules.py` 9115 · `estimation/dispatch.py` 6535 · `runtime/scheduler.py` 5957 · `verifier/verify.py` 4113 · `output/data_gap_report.py` 3372 |
| `dispatch.py` 里碰 numpy/pandas 的行 | **19** —— 接线层几乎不算数学 |
| `dispatch.py` 顶层函数 | 109；`_try_*` 共 19 个、合计 2193 行 |
| `_try_*` 返回类型 | **10 个 `bool` / 9 个 `None`** —— 同一角色两种协议 |
| `dispatch.py` 裸 `return None/False` | 27 处（放弃且不留痕迹） |
| `_estimate_effect_queries` | 555 行，first-match-wins 级联，**优先级 = 源码行号** |
| `_dispatch_effect` | 497 行，9 个顶层守卫，16 个 return，**同形状** |
| `scheduler.py` | 84 个顶层函数；14 个 `_dispatch_X`（按 query 类型）；`dispatch()` 尾部 **9 个 `_attach_*` 手工排序管线** |
| `data_gap_report.py` | **28 个 `_classify_*`**；`GapKind` 36 个成员 |
| `extensions` 块产出 vs 消费 | 产出 ~19；`data_gap_report` 读 **4**、`result_orchestrator` 读 **3**、`analysis_report` 读 **0** |
| 测试对要改内容的耦合 | 171 个测试文件中 **158 个完全不碰** `dispatch`/`scheduler` 内部；`_try_*` 被 import 次数 = **0** |

**结论**：要改的恰好是耦合最少、数学含量最低、行为级测试覆盖最厚的那一层。

**已埋好但尚未引爆的陷阱**：`_attach_data_gap_report` 在 `dispatch()` 里跑在
`_attach_selection_recovery` / `_attach_missing_data_recovery` **之前**，
所以缺口报告结构上看不见这两个块。今天不炸只因恰好没有分类器读它们。

---

## 目标结构

### 一等对象：Strategy

```
Strategy
  id            稳定标识 —— 进信封、进日志、进可达性矩阵、进审计
  layer         identification | estimation
  applies_when  声明式守卫：对 (query, graph, program, specs) 的纯谓词
  precedence    显式偏序（不是源码行号）
  role          claim（认领后终止） | annotate（记录后继续）
  requires      前置条件列表，每条 = (缺什么, 谁能填, 哪一层)
  produces      写哪个块 + 什么估计量
  assumes       携带哪些假设 id
  run           唯一的命令式部分 —— 原样调用现有估计模块
```

`role` 只需两个值。实测核对：19 个 `_try_*` 里只有结局误差评估（记录后继续）
与剂量反应回退（失败则继续）不是纯认领，两者都落在 `annotate` +「declined
则试下一条」内。

### 求值的产物是对象，不是副作用

```
Evaluation
  fired       谁认领了，产出什么
  annotated   哪些注解型策略跑了
  declined    [(策略, 哪条 requires 不满足, 为什么)]   ← 这就是缺口
  considered  求值过但守卫不成立的                     ← 这就是可达性的解释
```

**`declined` 中每一条不满足的前置条件，直接就是一个 `DataGap`。** 不必去
`derivation` 里找 `unidentifiable_*` 前缀，不必在 investigation 组里猜，
**更不需要 residual 兜底——因为没有残渣了。**

### 各层的归宿

| 现在 | 之后 |
|---|---|
| 14 个 `_dispatch_X` + 19 个 `_try_*`，**两套守卫** | 一张策略表，**守卫写一次**；两层是同表的 `layer` 字段 |
| 源码行号表达的优先级 | `precedence`：显式、可断言、**可断言两层一致** |
| `data_gap_report` 中重建型 classifier | **消失**，由 `declined` 直接产出 |
| `data_gap_report` 中输入审计型 classifier（对撞条件开后门、二分化连续量、未声明混杂、图是学来的、良定义干预版本…） | **保留但迁移**：它们是「你给我的输入有问题」，不是「我试了但缺东西」，属于求值**之前**的独立输入审计阶段。现状把两个物种混在一个列表里 |
| 9 个 `_attach_*` 的手工顺序 + 注释里的理由 | 后处理器声明 `reads`/`writes`，顺序由**拓扑排序**得出；读一个尚未被写的块 = **启动期报错**，不是运行时沉默 |
| 块登记表 | 由 `produces` 派生，不是额外维护物 |
| 可达性矩阵 | 由 `applies_when × layer` 派生 |
| 假设账本 | 由 fired / annotated 策略的 `assumes` 派生 |
| 27 处裸 `return None/False` | `decline(REASON)`，REASON 必须在表内登记 |
| `_try_*` 的 10 bool / 9 None | 单一返回契约 |

---

## 不变量 / 纪律（不可违反）

1. **验证器的重复是设计，不是债务。** `verifier/rules.py` + `verify.py`
   合计 13k 行必须继续独立重导；与生产者共享结构等于自证。**「优雅简洁」
   在此主动踩刹车**——这是全仓唯一一处「重复即正确性」。
2. **kernel 契约不变**：JSON in / JSON out，kernel 内无 LLM。
3. **估计层数学模块不动**：策略的 `run` 原样调用 `iv.py` / `measurement.py`
   / `mediation.py` / `outcome_error.py` 等。
4. **每个 slice 结束时全量套件全绿。** 分阶段的理由是**行为等价**，不是省事。
   绿 = 语义没丢，这是重构与砸掉重写的分界。
5. **两层守卫合一必须先证等价**：合并前逐条列出识别层与估计层的守卫及其
   顺序差异，对每处差异给出「哪个是对的 + 为什么」，作为 slice 0 的产物。
   顺序差异是已知的（`target_population`），不许在合并中被静默抹平。

---

## Slice 计划

- **slice 0 — 守卫等价性审计（无代码改动）。** 逐条抽出 `_dispatch_effect`
  与 `_estimate_effect_queries` 的守卫与优先级，做成对照表；对每处顺序/条件
  差异判定对错。产出：差异清单 + 判定 + 由此暴露的真实 bug（若有，单独修，
  不混进重构）。
- **slice 1 — 协议统一。** 单一返回契约；27 处裸 return 改 `decline(REASON)`；
  REASON 集合登记。逐个分支做，每步全绿。
- **slice 2 — 策略表 + 驱动（估计层）。** 19 个 `_try_*` 迁入表；
  `_estimate_effect_queries` 退化为驱动。
- **slice 3 — 策略表（识别层）。** 14 个 `_dispatch_X` 的守卫并入同表；
  两层守卫合一，等价性由 slice 0 的对照表背书。
- **slice 4 — `declined` → 缺口。** 重建型 classifier 删除；
  `data_gap_report` 只保留输入审计型并迁至求值前阶段。
- **slice 5 — 后处理拓扑化。** `_attach_*` 声明 reads/writes，顺序算出来。
- **slice 6 — 派生面。** 块登记、可达性矩阵、假设账本改为表的读出；
  元测试：跨入口同一估计量给同一个数。

---

## Slice 0 产出 — 守卫等价性审计（2026-07-28 完成，无代码改动）

`_dispatch_effect`（scheduler.py:4124-4620）与 `_estimate_effect_queries`
（dispatch.py:679-1232）逐条对照。两者都是「先匹配先赢」级联。

| # | 守卫 | 识别层 | 估计层 | 判定 |
|---|---|---|---|---|
| 1 | 查询原子不在图中 | I1 | — | 层次分工，正确 |
| 2 | longitudinal | I2：读 `options.longitudinal` + 匹配（**输入条件**） | E1：读 `numeric_estimate.method` 是否已是 `longitudinal_*`（**结果残迹**） | **识别层对**。估计层用代理信号当守卫，方法名一改即失效——与 2026-07-27「假设分类器绑死状态码」同型的脆弱点，非当前 bug |
| 3 | `extra_interventions` | I3 | E2 | 一致 |
| 4 | `target_population` | **I4** | **E5** | 顺序相反，见下方发现 B |
| 5 | `mediators`（集合） | I5 `if q.mediators:`（k≥1） | E3 `len(...) >= 2` | **阈值不一致 → 已确认真 bug，见发现 A** |
| 6 | `mediator`（单数） | I6 | E4 | 守卫一致；但 E4 **无条件 `continue`**，见发现 B |
| 7 | `selection_recovery` | — （由 `dispatch()` 尾部 attach，且在 gap report **之后**） | E6 | 跨层隐式依赖，靠执行顺序维系 |
| 8 | 误分类 / 测量误差 / 剂量反应 | — | E7–E13 | 层次分工，正确（识别层看不到 DataFrame） |
| 9 | front-door 的 `given` 空条件 | I7 内 `not observed_atoms` | E16 `not given_atoms` | **一致**；估计层注释明写 "mirrors the identification layer" —— 说明作者知道要镜像，但只在这一处做了 |
| 10 | general-ID 与 IV 的先后 | IV Wald(4268) → Tian(4281) | general_id(1059) → IV(1067) | **顺序相反 → 已实测确认会咬，见发现 C** |

**四处需要判定的差异中，三处识别层对、一处估计层对。没有哪一层系统性更对**
——这本身就是证据：不是某层写得糙，是**没有单一真相来源，两边各自漂移**。

### 发现 A（已实测确认，真 bug）—— `mediators: [m]` 的 k=1 块在估计层丢失

同一份 AST + 同一份数据（`tests/test_mediation_joint.py` 的 `_joint_scm`）：

| | k=2 `[m1,m2]` | k=1 `[m1]` |
|---|---|---|
| 识别端 `themis.run` | 联合块，identifiable | 联合块，identifiable（已有测试 `test_a_block_of_one_is_still_answered` 覆盖） |
| 估计端 `themis.estimate` | `mediation_joint_linear` + `decomposition` | **`backdoor_linear`，point 2.2018，无 decomposition** |

真值 NIE = 1.70；2.2018 是**总效应**。信封里同时挂着
`extensions.mediation_joint_decomposition`（"我做了分解"）和一个与中介无关的数，
gap 报告还在提示 `mediation_identification_assumption_required`。

**识别层对**：其注释已明确论证「一个元素的块仍是块，k=1 时 estimator 逐字节相同，
否则就是用户看不见的静默能力丢失」。估计层的 `>= 2` 没跟上这个决定。

### 发现 B（已实测确认，三组对照）—— `mediator` 守卫吞掉 transport 的数值端

`docs/l3_simulation/case_009_mediation_x_transport.json` 是一个**真实存在**的
同时带 `mediator` 与 `target_population` 的 case。

识别层**是诚实的**（原假设被证伪）：走 transport，并显式报
`unattempted_layer_due_to_dispatch_conflict`，明说"你还声明了 mediator，我没做那层"。

估计层则：E4 守卫命中 → `_try_mediation_estimate` 因
`extensions.mediation_decomposition` 不存在而立即返回 → **`continue` 无条件执行**
→ E5 的 transport 数值端永远不可达。识别层说 transport 可识别，估计层一个数都不给，
也不说为什么。

**三组对照实测**（`tests/test_estimation_transport.py` 的 `_transport_program`
+ `_balanced_source`，把「图变了」与「字段变了」分开）：

| | 识别端 | 估计端 |
|---|---|---|
| A 基线（图里无 m） | transport，`structurally_solved` | `transport_post_stratification`，**0.4106** |
| B 图里加 `x→m→y`，query 不写 `mediator` | transport，`structurally_solved` | **0.4106**（与 A 逐位相同） |
| C 同 B 的图，query 写 `mediator: m` | transport，`structurally_solved` | **三个答案通道全空** |

图相同、数据相同、`extensions.transport_identification` 块**逐字段相同**；
只多了一个字段，数就没了。C 的 `numeric_estimate` / `numeric_result` /
`bounds_result` 全是 `None`，而 `estimator_failure` **也是 `None`**——
估计层对自己什么都没产出这件事一个字都没记。

**二阶发现**：C 的缺口报告 `answer_tier` 仍然是 **`point`**，即它向读者
承诺一个信封里任何通道都不存在的点答案。（A/B 也是 `point`，那里名副其实。）
本档只在这个情形下观测到，**未核实 `answer_tier` 在其他空信封情形下是否同样
失准**——那是独立一条。

C 相对 B 多出的四条缺口（`missing_distribution`、
`transport_source_conditional_unknown`、`transport_target_distribution_unknown`、
`unattempted_layer_due_to_dispatch_conflict`）中，前三条是 theta 侧的
investigation 请求——B 的数值端把它们消掉了，C 没有数值端所以留着。**不是
误报**，是"没人来满足它们"的正常后果。第四条来自识别层，是它诚实报出的冲突。

**识别层对**。估计层应当跟随识别层的选择，或像识别层一样显式拒绝；
现状是两者都不做。路径由读代码定位（`dispatch.py:762-768` 的**无条件
`continue`** + `_try_mediation_estimate` 的 `decomp is None → return`），
由上表端到端坐实。

### 发现 C（已实测确认）—— 声明一个假设，把无假设的答案换成了需假设的答案

估计层 general-ID 先于 IV，注释给了正确理由：c-factor 估计量无假设，
IV 点估计需单调性/效应同质性。识别层反过来（IV Wald 先）。

**见证图**：Pearl napkin（`w→z→x→y`，`w↔x`，`w↔y`）。实测该图上
`iv_sets` 恰有一个**条件**工具候选 `z | w`，后门集 0，前门集 0——所以
识别层确实会走到 IV/Tian 这一段。theta 由 napkin DGP 的经验条件概率供给，
按验证器的真实规则（`admissible = parents ∪ ancestors ∪ bidirected 兄弟`，
不是报错文案说的 `parents`）逐条发。

**同一张图、同一份 theta、同一个查询，只多声明一个 `monotonicity`：**

| | derivation | `numeric_result.value` |
|---|---|---|
| 不声明 | `tian_c_decomposition → identify_via_tian → tian_formula_ast` | **0.6021** |
| 声明 | `iv_criterion_check → identify_via_iv → iv_wald_numeric_evaluate` | **0.2122** |

两个数各自都对，但**不是同一个量**：0.6021 是查询真正问的
P(Y=1\|do(x=1))（DGP 真值 0.6036）；0.2122 是 Wald LATE，一个对比量
（DGP 的 ATE 0.2071）。**多给一条信息，答案从无假设的总体量变成了需单调性
的 complier 量。** 信息增加不该让估计量退化。

**估计层对**，其 dispatch 注释已写明理由。识别层的顺序应翻转，
**slice 3 合并守卫时，合并后的 precedence 必须是「无假设优先」**。

**不是静默问题**：IV 路径的披露是充分的——`extensions.iv_identification`
带 `late_caveat` 明写「这是 complier 上的效应，不是总体 ATE，混淆二者是已知
的 IV 部署陷阱」，缺口报告也报 `iv_identification_assumption_required`。
缺陷在**策略**，不在沉默。

**方法论教训（记下来）**：本发现的第一次探针跑出「两次同一个数、无分歧」，
我据此差点判定假设被证伪。真因是探针把概率 `round(p, 6)`，导致
条件层权重和 0.999999≠1，IV 路径**正确地拒绝**了这份 theta 并落回 Tian。
去掉舍入后分歧立刻出现。**探针的产物必须先自证不是探针自身的假象**——
一次"没测出来"不等于"不存在"。

### 对重构的输入

- 差异 5 / 4 / 10 全部是**同一个决定被写了两遍然后漂移**，正是策略表要消灭的东西。
- 差异 9 证明镜像是可行的（做到过一次），但靠人做不可持续。
- 差异 2 说明守卫必须是**输入条件**，不许读结果残迹——策略表的 `applies_when`
  只允许对 (query, graph, program, specs) 求值，**不允许读 result**。这条写进
  slice 2 的验收。
- 发现 A 已修（`9e91534`）。**发现 B / C 均已实测确认，必须先单独修再重构**
  （charter 纪律：真 bug 不混进重构）。B 的修法要连带决定 `answer_tier`
  在空信封上该报什么；C 的修法就是把识别层的 precedence 翻成无假设优先。

## 显式 Out-of-scope

- 验证器的任何「消重」。
- 估计器数学的重写或替换。
- schema 的语义变更（字段可增，既有语义不动）。
- `estimator_failure.failure_type` 枚举的系统性修复（10 个 vs 实发 51 个）
  ——独立一档，但 slice 1 会与它相撞，届时按当时结论处理。
- web / 渲染 / prompt 层的重构。

---

## 风险

- **最大风险：两层守卫合一时静默改变路由。** 缓解 = slice 0 的等价性审计
  先行 + 158 个行为级测试文件全程绿 + 任何路由变化必须在对照表里有判定。
- **次风险：`declined` 表达不了某些现有缺口。** 28 个 classifier 中输入审计型
  的边界尚未逐个核实；若某个「看似重建型」的分类器实际做了独立推理，它属于
  审计型，误删会丢能力。缓解 = slice 4 前逐个读，不按名字归类。
- **`precedence` 可能需要偏序而非全序。** 现状是全序（行号），但合并两层后
  可能出现只在某层有序的对。若出现，表必须表达偏序，不许退回全序凑合。

---

## 未读（形状已定，尺寸未定）

- `data_gap_report.py` 的 28 个 classifier 未逐个读——按名字归的 A/B 两类，
  决定该文件能瘦多少，**不影响目标结构形状**。
- `scheduler.py` 14 个 `_dispatch_X` 只读了 `_dispatch_effect`——其余 13 个
  是否同为级联形状，决定策略表条目数，同样不影响形状。
