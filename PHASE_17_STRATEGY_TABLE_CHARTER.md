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

**一条我提错的二阶发现，就地结掉**：我曾把「C 的 `answer_tier` 仍是 `point`
而信封里没有数」记为可能的缺陷。读 `_compute_answer_tier` 的契约后作废——
它的 docstring 明写 POINT 的语义是「**点估计量可识别**」，并把
「identifiable-but-missing-θ（a data gap, still a point）」显式算作 POINT。
C 的估计量确实是点可识别的（识别层给了 `structurally_solved`），所以
`answer_tier: point` **符合它自己的契约**，不是缺陷。记下来是因为这正是
「诚实拒绝也当待验证断言」反过来用在自己身上：我标注的可疑项，读契约后
是对的。

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
- **三个发现均已修，重构开工前的地基是干净的**（charter 纪律：真 bug 不混进
  重构）。A = `9e91534`（守卫判集合大小 → 判是否点名了集合）；B = 中介两个
  分支改为「产出了才认领」，顺带把 `_try_*` 的双协议往单一 bool 推进一格，
  是 slice 1 的定金；C = 识别层把 Tian 移到 IV escalation 之前，与估计层
  一致。`answer_tier` 一项经查是我提错，见发现 B 内的更正。
- **slice 1 的一条验收由 B 的修法定下**：认领与否只能由「策略真产出了」
  决定，不能由「守卫命中」决定——`decline(REASON)` 的返回值就是这件事。

## Slice 1 产出 — 协议统一（2026-07-29 完成）

`themis/estimation/claim.py`：**四态**，19/19 handler 全部改说它（AST 级核过，
无一残留 `bool` / `None` / 裸 `return`）。

| | 拥有查询 | 查询继续 | 何时 |
|---|---|---|---|
| `answered()` | ✓ | 停 | 答案已附上 |
| `blocked(reason)` | ✓ | **停** | 答不出来——且**别人不许替它答** |
| `annotated()` | ✗ | 继续 | 在答案旁加了东西（精度代价 / caveat） |
| `passed(reason)` | ✗ | 继续 | 还在飞，后面有人接**同一个问题** |

第二态是全部意义所在：旧的 bool 表达不了「拥有但答不出来」，而发现 A / B
两个已测缺陷都长在这个表达不了的位置上。第三态是 charter 预留的 `annotate`
角色——`_try_outcome_error_assessment` 正是它，那个 handler 此前**协议倒置**
（`True` 表示「没认领、继续」，与其余 11 个 bool 相反）。

**理由词汇表 8 条**，全部从代码提出、每条附一句「谁能改变它」（图 / 数据 /
本包 / 装依赖）：`identification_chose_another_strategy`、`not_identified`、
`numeric_end_not_built`、`combination_out_of_scope`、`required_columns_absent`、
`design_unavailable`、`estimator_dependency_missing`、`estimator_refused`。
`blocked()`/`passed()` 当场拒绝未登记的理由。

### 修正 charter 先前的数字

「27 处裸 return」是错的：那个数把 **13 处纯 helper**（`_compute_precision_budget`、
`_is_binary_treatment`、`_declared_scale` 等）的 `return None` 算了进去——那里
的 None 是「没有值」，不是「拒绝一个查询」，slice 1 不动它们。真正的策略拒绝
**22 处**，另有 7 个 `-> None` handler 的 33 个裸 `return`。

### 转换中暴露的三件事

1. **`_try_dose_response_estimate` 早就在做对的事**：四个出口里三个是「把失败
   写进信封 + 认领」，正是本协议要形式化的模式——只是从未被当成模式，其余 18 个
   handler 都没学。
2. **它的调用点注释在说谎**：那句「fall through to the binary path so the user
   still gets *something*」描述的分支**不可达**（该函数没有 `return False`）。
   不可达是好事——可达才是发现 A 那类缺陷——但注释该改。**登记为独立小项。**
3. **9 处宽 `except (EstimatorFailure, ValueError, NotImplementedError)`** 把
   「估计器诚实拒绝」与「代码炸了」压进同一个分支。slice 1 只登记不拆：拆它要
   逐个判断哪些异常是真信号，那是行为变更。**独立一档。**

### 元测试当场抓到的两个缺陷（`tests/test_claim_protocol.py`）

- **`Claim` 是 dataclass，永远真值为 True。** 两个中介调用点仍写 `if _try_x(...):`，
  于是**每个**查询都被认领——**发现 B 被原样打破**。这是类型从值语义迁到对象
  语义时的必然陷阱且完全静默，故专有一条测试钉「调用点必须读 `.stops_here`」。
  同一次全量独立复现了它（`test_a_named_mediator_does_not_swallow_the_transport_number`
  报 `assert None is not None`），两条路径指向同一个缺陷。
- **`combination_out_of_scope` 用了但没登记。** 运行时 `_checked` 会抛，但没有
  测试走那条路径——**它会先到用户手里再到测试手里**。静态扫描全文件字面量的
  那条测试专抓这一类。

### 仍靠 review 的不变量（交棒给 slice 2）

`blocked` 与 `passed` 的分界是「**往下传只有在接手者回答同一个问题时才合法**」。
此刻机器强制不了——没有 handler 声明自己瞄准哪个估计量。**slice 2 的策略表
`produces` 字段兑现它**，届时驱动可以断言：一次 `passed` 之后真正作答的策略，
其估计量必须与放行者相同。

## Slice 2 产出 — 估计层策略表 + 驱动（2026-07-29 完成）

`themis/estimation/strategy.py` 是协议，`dispatch.py` 里 `_EFFECT_STRATEGIES`
是表，`_estimate_effect_queries` 从 **570 行降到 ~90 行**且只做一件事：
装配一个策略被允许看见的东西，然后把查询逐条递给表。

**18 行，优先级 10..180**，与旧链逐条同序（有一条测试逐字钉住这个顺序，
所以任何重排必须是对那张清单的显式编辑，而不是挪代码的副作用）。其中
13 行是原有 `_try_*`；**5 行是原先内联在链里的**——backdoor / frontdoor /
IV-Wald / doubly-robust / dose-response 二值回退。不抽出来的话优先级仍有一半
是行号，表就是假的。

### 三个结构性判定

1. **守卫看不见本层输出——不是约定，是没有那个属性。** `EffectFacts` 没有
   `result` 字段，想读只能 AttributeError。守卫**可以**读识别层的结论
   （`selection_recovery` 是识别层写的，估计层无人写），那是分层边界在正常
   工作。一条测试要求每个守卫的 lambda 体内除了自己的参数和 builtins 不许
   出现任何名字——**守卫是 facts 的纯函数**。
2. **E1（longitudinal 已作答）不是守卫，是驱动的终止条件。** 它测的是
   「前一趟已经认领了这个 result」，没有任何策略靠它路由。归到驱动后，
   「守卫不许读 result」这条就不是例外条款而是全称成立。它仍在嗅方法名残迹，
   **这一点没修**：让 longitudinal 那趟显式声明认领，要先回答「它因识别失败
   而拒答、什么残迹都不留时该发生什么」——那是行为问题不是表的问题，**登记
   独立一档**。
3. **表覆盖的是效应级联，不是全部 19 个 `_try_*`。** 另外 6 个各自属于
   「一个 query kind 一个策略」的驱动（ctf / proximal / causation /
   counterfactual cell / scm），**没有级联就没有优先级漂移**，现在入表只增加
   条目不消除风险。它们在 slice 6（派生面需要块登记时）入表。

### 用全量套件实测了级联真正在做什么

驱动返回 `Evaluation`，套件跑一遍收集到 **434 次求值**（探针是外挂 pytest
plugin，不进仓）：

| 读法 | 实测 |
|---|---|
| `fired` | backdoor 98 · iv_wald 70 · dose_response 29 · 各测量误差臂 59 · mediation 30 · frontdoor 19 · joint 15 · general_id 14 · transport 9 · selection_recovery 5 |
| `declined` | 20 种 (策略, 理由) 组合，最大宗是 `dose_response_curve\|estimator_refused` 6 次 |
| `passed_by` | **92 次，其中 88 次是 general_id** |
| `substitutions` | **只有两种形状**：general_id→IV 80 次，mediation_single→transport 1 次 |
| 无人作答且无人记录 | **8 次** |

### 实测把交接来的不变量改了形状——然后兑现了它

slice 1 交棒时写的是「往下传只有在接手者回答同一个问题时才合法」。
**实测证明这条按字面讲是错的**：general_id 放行、IV 作答的 80 次里，IV 给的是
complier 上的对比量，根本不是同一个量——而那正是有意为之的逃生梯，且答案上
挂着 `late_caveat`。按字面执行会打断 81 个正确路径。

正确的规则是「**替换必须被声明**」，落成 `Strategy.defers_to`：一行只有在表里
写明「我允许 X 用别的估计量替我作答」时，X 才可以。同估计量的接力不需要声明
（本来就是同一个问题）。全表**只有两条声明**，恰好等于实测出的两种形状；
其余任何替换当场 `AssertionError`。

**这条规则抓得住我自己犯过的那个错。** slice 1 里 Fix B 的第一版让中介按
「有没有产出数」认领，于是分解型查询掉进 backdoor 拿到总效应——
`backdoor ∉ mediation_single.defers_to`，会直接炸。而如果规则改用「理由是否
许可替换」（`identification_chose_another_strategy` 就放行），那次就抓不到。
**规则选型是按「它能不能抓住已经发生过的错」定的，不是按听起来是否优雅。**

### 实测顺带查出的两件事（都不在本档修）

- **`general_id` 的 88 次放行全部报 `estimator_refused`。** 读它那个宽 except
  的注释，它自己写明吞了三样东西：「非参数不可识别」（结构，该 `not_identified`）、
  「超出插件二值范围」（本包，该 `numeric_end_not_built`）、「positivity 拒绝」
  （数据）。理由词汇表的意义是告诉读者**谁能改变它**，而全系统流量最大的拒绝点
  报的是错的那个。这就是 slice 1 登记的「9 处宽 except」条目——**现在它有数字了
  ：88/92**。拆它是行为变更，仍独立一档。
- **8 次「无人作答且无人记录」**，恰好 = 88 次 general_id 放行 − 80 次 IV 接手。
  即：非参数识别失败且图上没有工具变量 → 信封里没有数，也没有 `estimator_failure`。
  这正是发现 B 的形状，是既有行为，**现在是一个被测出来的数而不是一个猜想**。
  slice 4（`declined` → 缺口）的第一批客户就是它。

### 顺带结清的两个登记项

- slice 1 记的「`_try_dose_response_estimate` 调用点注释在说谎」——那句注释随
  内联分支一起消失了。
- slice 1 的元测试「调用点必须读 `.stops_here`」在表化之后会**空转**（没有
  `if handler(...)` 了）。改成更强的一条：**dispatch.py 里任何 `if` 的条件中
  都不许出现 `_try_*` 调用**——多一个手写分支就是多一个派发器，而两个派发器
  正是两层当初漂开的原因。

## Slice 3 前置 — 识别层实测 + 发现 D（2026-07-29）

### 先纠正 charter 自己的两个说法

- **不是 14 个 `_dispatch_X`，是 15 个**（漏了 `_dispatch_probability`）。
- **更要紧的是「并入同表」的对象错了**。实测调用图：`dispatch()` 按 **query kind**
  在 10 个 dispatcher 里选一个——一个查询只有一种 kind，**这里没有优先级、
  没有漂移**。真正的级联只有一处：`_dispatch_effect`，它自己按守卫委派给
  5 个子 dispatcher（longitudinal / joint / transport / mediation_joint /
  mediation），**恰好就是估计层第 10-40 号那几行的镜像**，再往下是结构性策略
  （front-door / Tian / IV / IDC / backdoor）。所以 slice 3 的对象是
  `_dispatch_effect` 一个函数，不是 15 个 dispatcher。

### 两层守卫逐条对照（slice 0 之后的现状）

| 策略 | 识别层 | 估计层 | 判定 |
|---|---|---|---|
| longitudinal | 4165 | 驱动前置检查 | 分工，正确 |
| joint | 4177 | 10 | 一致 |
| transport | **4188** | **40** | **顺序仍相反**，见下 |
| mediation_joint | 4210 | 20 | 同上 |
| mediation_single | 4215 | 30 | 同上 |
| backdoor | 尾部 4533 | 140 | **一致**（识别层的 `if bidirected` 分叉经证是 `bidirected or None` 的等价展开） |
| front-door | 4234 / 4493 | 150 | 一致 |
| Tian | 4281 | 160 | 一致（发现 C 已修，两层同序） |
| IV Wald | 4354 | 180 | 一致 |
| IDC | 4374 | 并入 160 | **识别层不可达，见发现 D** |

**transport 与 mediation 的相对顺序仍然相反**，但两层现在殊途同归：识别层
transport 在前直接路由过去；估计层 mediation 在前、发现识别层选了别人于是
`passed`，再由 transport 认领——这正是 slice 2 唯一那条 `defers_to` 的来历。
**合表时这里会变成一个数**，届时 `mediation_single.defers_to` 应当随之消失。

### 发现 D（已实测确认，真 bug，且**不是重构引入的**）—— 识别层拒答了一个它自己的验证器认可的查询

**见证**：`x→m→y`，无双向边，查询 `P(y|do(x), m)`（`given=[m]`）。

| | 状态 | 产物 |
|---|---|---|
| `themis.run`（识别） | `needs_investigation` | `identification:not_identifiable`，**无 derivation** |
| `themis.estimate`（估计） | `numerically_solved` | `general_id_idc_plugin`，point **0.0**，完整 derivation |
| `themis.verify`（独立重导） | — | **接受估计层那份信封** |

**0.0 是对的**：图上 y ⊥ x \| m，条件对比量本就为零。在 slice 2 之前的 commit
（`59fc123`，独立 worktree）逐字复现同样结果——**既有缺陷，非本次重构引入**。

**根因假设**。`_dispatch_effect` 的结构性策略尾巴**在同一个函数体内写了两遍**：
第一份在 `if bidirected:` 的 else 里（4230-4455），含 front-door → Tian → IV →
**IDC** → 拒答；第二份在 `if not adjustment_sets:` 里（4487-4518），**只有
front-door → 拒答**。无潜在混杂的查询走第二份，IDC 因此永远不可达。而
**IDC 做的是条件识别，与潜在混杂正交**——它被 `bidirected` 挡住，纯粹因为它
恰好被写在了那一份拷贝里。

**为什么是根因不是表象**。表象修法是「在第二份尾巴里补上 IDC」，那是把同一个
决策写第三遍。两份拷贝的差异**不是设计**，有两条硬证据：(1) 两份的 front-door
段**逐字节相同**，只差一个 `bidirected=` kwarg，而 solver 三个入口的该参数默认
值就是 `None`——即那个分叉在结构上什么也没买到；(2) 第一份的注释逐条论证了
「Tian 为什么排在 IV 前」「IDC 为什么不能拿边际顶替条件」，**这些论证对第二份
同样成立，第二份只是没有它们**。与 charter 根因假设里「同一组守卫写了两遍、
顺序还不一样」同形，只不过这次两份拷贝在同一个函数里。

**拟做的结构性修改**。合成一条尾巴：`adjustment_sets` 用 `bidirected or None`
一次算出（等价性已证），`if bidirected:` 的分叉随之消失；front-door / Tian /
IV / IDC / 拒答成为唯一序列。**拒答文案不合并**——ADMG 版与普通版携带的信息
本就不同（前者会提 Tian/ID 试过了、并挂 `iv_note`），按 `bidirected` 是否为空
选择，保持逐字不变；合并的是梯子，不是措辞。

### 发现 D 的修复与它掀出来的东西（已完成）

见证查询修复前后：

| | 修复前 | 修复后 |
|---|---|---|
| `themis.run` | `structure / identification:not_identifiable` | `parameter / P(y=True\|m=True)` |

即从**「图挡住了」错判**变成**「识别成功，缺这个数」**——而缺的正是 IDC 公式
逐项要的那两个条件概率。两层从此一致。

**全量套件只有 4 条失败，全部来自同一个 fixture，且判定结果是「测试的前提是
一个错误的理论陈述」**：`_collider_program` 的 docstring 写着「没有后门也没有
前门可调整集，所以 kernel 报 `identification:not_identifiable`」——**这不是
定理**。全观测 DAG 上每个干预分布都可识别（ID/IDC 完备性）；没有可调整集只
排除了那两条调整公式。**kernel 之所以一直同意这句错话，正是因为它的 IDC 分支
被潜在混杂守卫挡着**；分支一变得可达，它就不同意了。修法是给 fixture 补上
它名字里一直暗示、图里却没有的那条 bow arc，而不是改代码迁就测试。

**登记一个没在本档动的第四处同族不一致**：普通拒答设
`structural_result=StructuralResult(value=False)`，ADMG 拒答**不设**（留 `None`）。
同一个「识别失败」在两份拷贝里表达得不一样。不动的理由是它**承重**——
`oracle/differential.py:246` 恰好用 `structural_result is None` 判断「运行时
没给出结构判决，oracle 无从比对」，改它会把一批 ADMG 拒答送进差分比对。
那需要它自己的判定，不是顺手。

**一个如实记录、未解决的观察**：合并后**没有任何测试再产出
`identification:not_identifiable`**（仅存的引用是新测试断言它不出现、以及
verifier 测试合成构造）。要么它本来就该死（它此前只在可识别的查询上触发），
要么它是 IDC 实现 hedge 时的兜底。**我无法证明 `identify_via_idc` 的完备性，
所以不宣称它是死代码。**

### 发现 E（已实测确认，真 bug，非重构引入）—— 估计层用一个与 `given` 无关的数回答了条件查询

准备 slice 3 的合表时逐条比对两层的 IV 守卫，发现估计层的 `iv_wald` /
`iv_overidentified` 守卫里**没有任何关于 `given` 的条件**，而 `front_door_sets`
在有 `given` 时返回 `()` 的短路让这两行**恰好可达**。

**现象**。Pearl napkin（`w→z→x→y`，`w↔x`，`w↔y`），查询
`P(y=True|do(x=True), w)`：

| | 结论 |
|---|---|
| `themis.run` | `needs_investigation` / `query:effect_admg_conditional`——明说不识别，且「不拿边际顶替」 |
| `themis.estimate` | `numerically_solved`，`iv_stratified_wald`，point **0.1627** |

**这个数不可能是任一问题的答案**：把 `given` 从 `w=True` 换成 `w=False`，
两次输出**逐位相同**（0.1627287839426641）。信封里报的 `conditioning: ["w"]`
是**工具变量自己的条件集 W**，与查询的 `given` 只是碰巧同名——换一张图
（`z→x→y`，`x↔y`，另加 `c→y`，查询 `given=[c]`）照样出 `iv_wald`，那里
W=∅ 与 `given={c}` 连碰巧都算不上。

**根因假设**。「IV 只回答无条件查询」这条约束**从来不是守卫，而是一个函数体
的第一行**——`_try_iv_wald_in_effect` 开头的 `if q.given: return _IVWaldAttempt()`，
其 docstring 还把理由写得很清楚（「Wald 是两点对比，条件查询属于 IDC 分支，
拿无条件 LATE 顶替是在回答另一个问题」）。**理由写在了正确的地方，约束却写在
了只对一个调用点生效的地方**。估计层的守卫是另写的，它继承了 front-door 的
同类约束（因为那一条被表达成了**事实**：`front_door_sets` 在有 `given` 时
返回 `()`），却没有继承 IV 的，因为 IV 那条根本不在事实里。

**为什么是根因不是表象**。表象修法是在 `_try_iv_wald_estimate` 里加一行
`if facts.given_atoms: return blocked(...)`——那是把同一条约束写第三遍，且仍然
写在 handler 里，`iv_overidentified` 和将来任何 IV 族策略（AR 稳健集等）还会
各漏一次。真正缺的是**估计量适用范围的一等表示**：front-door 有（事实层短路），
IV 没有。与发现 D 同形——发现 D 是同一条梯子写了两遍，发现 E 是同一条约束
只写在了两处中的一处。

**结构性修改**。`EffectFacts.iv_candidates` 在 `given_atoms` 非空时返回 `()`，
与 `front_door_sets` 逐字同构，理由写在同一个位置。由此**两行 IV 守卫和
`overid_instruments` 一起受约束**，且 slice 3 合表时识别层直接共用这条守卫——
它此刻的早返回就变成守卫的一个后果，而不是第二份拷贝。

**代价，明说**：修后该查询在估计层**一个数都没有**，且 `estimator_failure`
仍是 `None`（general_id 放行、无人接手）。这正是 slice 2 实测到的「8 次无人
作答且无人记录」那一族，是 slice 4 的客户。**没有数**比**一个答非所问的数**
正确——识别层对同一查询本来就是拒答。

## Slice 3 产出 — 一张路由表，两层各绑一端（2026-07-29 完成）

`themis/routing.py` 是表，两层各是它的一个**端**。`_dispatch_effect`
**从 431 行降到 59 行**，且只做一件事：装配事实，然后按表逐行发问。

**19 行，一条优先级轴，三个带**：

| 带 | 内容 | 谁能跑 |
|---|---|---|
| 10-50 | 按**问题的形状**路由（longitudinal / joint / transport / mediation_joint / mediation_single）——在看图之前 | 两层（longitudinal 只有识别端） |
| 60-140 | 数据层（选择偏倚恢复 / 测量误差 / 剂量反应 / DR）——识别层看不见 DataFrame | 只有数值端 |
| 150-190 | 结构梯子（backdoor / frontdoor / general_id / IV）——**无假设永远排在需假设之前** | 两层（over-ID 只有数值端） |

三个带**交错在同一条轴上而不是分成三张表**，因为「谁来回答这个查询」只有
一个答案。

### 三条结构性保证（都不是约定）

1. **`Strategy` 持有 route 对象本身，不拷贝它的字段**——`id` / `precedence` /
   `applies_when` 都是穿透读。两层同序从此是**对象同一性**，而不是一次「看着
   一样」的比对。此前那个比对失败过三次，每次都无声。
2. **`ends` 不是标签，是绑定检查的依据**。`routing.bind` 双向拒绝：某端声明了
   却没绑（**发现 D 就是这个形状**——表承诺了条件识别，那层从来没跑），以及
   绑了表并不路由过来的（**那是第二个派发器的起点**）。
3. **事实分层用类型表达**。`StructuralFacts`（两层都有：查询、图、solver 的
   判决）→ `EffectFacts`（加数据与调用方 spec）/ 识别层的 `_EffectFacts`
   （加 theta、selection、longitudinal spec）。**只有识别端的路由，其守卫命名
   的是只有识别层事实才有的属性**——拿到另一层求值就是 AttributeError，不是
   一条「请不要这样写」。与 slice 2「守卫看不见本层输出」同一手法。

### 顺序合一，一条 `defers_to` 随之消失

**transport 移到 mediation 之前**，取识别层的原序。理由是那一层本来就对：
同时点名 mediator 与 target_population 的查询**只有一个主人**，且 transport
会显式报 `unattempted_layer_due_to_dispatch_conflict`，明说「你还声明了另一层，
我没做」。

**`mediation_single.defers_to = {"transport"}` 一并删除**。那条声明**本来就只是
两份拷贝分歧的产物**：估计层 mediation 在前，只能靠它先「站下来」才走得到
transport，而两者估计量不同，所以那次交接必须被声明。合表后交接根本不发生。

**这不是靠推理断言的**：`run_cascade` 里那条「未声明的替换当场 AssertionError」
仍然武装着，声明已经删了，**全量 3652 绿 ⇒ 这个交接一次都没再发生**。

### 顺带清掉的两处重算 / 早返回

- `_try_iv_wald_in_effect` 开头的 `if q.given: return` 删除——发现 E 已把它
  升成事实（`iv_candidates` 在有条件时为空），守卫接管，早返回就是第二份拷贝。
- 该函数不再自己调 `structural_solver.iv_sets`，改读 facts；识别层此前用
  `bidirected=frozenset()`、估计层用 `bidirected or None`（solver 对两者等价，
  但那是**两个人各自赌了一次**）。

### 本档明确没做的

- **10 个按 query kind 选择的 dispatcher 没有入表**。slice 3 前置已判定：一个
  查询只有一种 kind，**那里没有优先级也没有漂移**，入表只增条目不消风险。
- **拒答文案仍按 `bidirected` 分叉**，有意保留：ADMG 版会说「Tian/ID 都试过了」
  并挂 `iv_note`，对没有潜在混杂的用户描述的是他从未涉及的机器。**合并的是
  梯子，不是措辞。**
- **`structural_result` 第四处同族不一致仍在**（发现 D 已登记，`oracle/
  differential.py` 承重）。

**基线**：3646 → **3652**（新增 6 条元测试：一条轴的逐字清单、两层 route 对象
同一性、形状先于图、数值端行序、缺绑定被拒、多绑定被拒、驱动体内不许出现策略名）。

## Slice 4 前置 — 缺口报告实测 + 发现 F（2026-07-29）

### 先纠正 charter 自己对 slice 4 的判断

charter 把 `data_gap_report` 的分类器分成两个物种（重建型 / 输入审计型），
并把 slice 4 的对象定为「`declined` 直接产出缺口」。**实测下来这个划分和这个
对象都不对。**

**28 个 `_classify_*` 按「读什么」分是三个物种，不是两个**：

| 物种 | 读什么 | 数量 | 例 |
|---|---|---|---|
| 输入审计 | 只读 `program` / `stmt` / `framing_notes` | ~7 | 图是学来的、对撞条件开后门、干预版本未良定义 |
| **块回声** | 读策略自己写下的 `extensions.*` 块 | ~7 | IV / 中介 / transport 的假设披露 |
| **残渣重建** | 读 `investigation_requests` 的**名字字符串**、或 `derivation` 的**规则名字符串** | ~10 | `_classify_unidentifiable_from_request`、`_classify_missing_iv`、`_classify_residual_investigation_items` |

**「块回声」这一族是 charter 漏掉的**，而且它恰恰**不是**重建型：它读的是策略
显式写下的块，属于「翻译」而非「猜」。真正要消灭的只有第三族。

**更要紧的是 slice 4 的对象错了**。`declined` 只覆盖**驱动层**的拒绝
（识别层实测只有 general_id 与 iv_wald 会 decline）。缺口报告读的那堆残渣，
绝大多数是**被认领的子 dispatcher 在自己的结果里写的 `MissingItem`**。实测
全仓 **`MissingItem` 构造点 33 处、全部在 `scheduler.py`、名字模板约 30 个**，
而 `InvestigationItem.target` 就是 `MissingItem.name` 原样（`investigation_pusher.py:105`）。

所以 slice 4 的真对象是：**`MissingItem.name` 是一个字符串，产生端知道这是
哪一类缺口、把它压成名字扔掉，消费端再用前缀 / 子串匹配猜回来。**
`MissingKind` 只有 5 个值（哪个渠道），`GapKind` 有 36 个（哪一类），
**粗→细的那一步全靠猜**。这是 charter 根因（语义事实无一等表示）最纯的形态，
只是对象是 `MissingItem` 而不是 `declined`。

### 发现 F（已实测确认，真 bug，用户可见）—— 「given」里有「iv」

**见证**：`x→y`、`x→d`，问 `identify(y | do(x), given=[d])`。`d` 是 `X` 的后代，
kernel **正确拒答**，`MissingItem.reason` 写得很清楚：「identify.given violates
backdoor pre-conditions (contains X, Y, or a descendant of X): d(me)」。

用户读到的缺口报告是：**「未找到满足 IV 条件的工具变量：query:identify_given」**，
而真正的原因**一条都没进报告**。

**根因**。`_classify_missing_iv` 判定「这是不是 IV 缺口」的判据是
`"iv" not in item.target.lower()` —— **一个裸子串测试**。而
`query:identify_g·iv·en` 里有 `iv`。同一个子串判据同时被两处使用：
`_classify_missing_iv` 用它**纳入**，`_classify_unidentifiable_from_request`
用它**排除**——**一次巧合既伪造了一个缺口，又压掉了真缺口**。

**为什么是根因不是表象**。表象修法是把子串换成更严的字符串测试；但信息在
产生端**是有的**（那个分支的 `reason` 明说是 backdoor 前置条件违规），被压成
一个字符串扔掉，再由消费端做模式匹配猜回来。**缺口的物种不是它名字的子串。**

**顺带查出的第二处同族缺陷**：同一个分类器的 docstring 明写规则——「程序缺陷
走 residual，不许告诉 `answer_tier` 说图挡住了估计量」——然后把这条规则编码成
前缀 `"query:identify"`，**比它想表达的距离短了一个词**：
`query:identify_unreachable`（ID 算法报告无 witness，真结构缺口）与
`query:identify_given`（用户条件在 X 的后代上，删一个词就好）被同一个前缀扫进
同一类。**规则说得对，编码比规则粗。**

**第三处，只登记不动**：`_UNIDENTIFIABLE_PREFIXES` 里的
`"query:counterfactual_admg"` 在全仓**只出现这一次**——**没有任何产生端**。
一条永远不可能命中的匹配规则。不在本档删，因为删它是零行为变更、无法用测试
钉住；slice 4 会把整张前缀表一起删掉。

**本档的修法（最小且正确，不预支 slice 4）**：把 IV 判据从「子串」改成
**名字的 local part 以 `iv_` 开头**，两个调用点**共用同一个谓词**（此前是
两份各自演化的子串测试，这正是它们一个伪造一个压制的原因）；把
`"query:identify"` 收窄成 `"query:identify_unreachable"`。修后端到端产出
`missing_structural_input | blocking | 缺结构输入：identify.given violates
backdoor pre-conditions…`——**kernel 给的理由逐字到了用户眼前**。

**三条测试各钉一半，且都验过非空转**：去掉谓词修复 → 两条失败；只回退前缀
收窄 → 第三条失败。

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
