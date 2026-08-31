# Themis 12 板块覆盖地图

> 更新时间：2026-07-13（前置数据诊断层：`declared_type_data_mismatch`
> gap_kind + `VariableDeclaration.scale` 字段 — 第一个由实际数据（非程序
> 结构）驱动的 gap，把声明的测量尺度/域与 CSV 列核对，31→32 gap_kind。
> 历史注：2026-06-18 dead-schema 第四 crack：
> `dichotomized_continuous_measure` 把变量的 `threshold` 字段
> （schema 文档为"turns a continuous measurement into this predicate's
> value, e.g. >=3cm"）的 PRESENCE 暴露为连续量在 cutpoint 处被二分。
> 此前 `threshold` 只有 ABSENCE 被读（驱动 `ambiguous_variable_definition`），
> PRESENCE — 二分化的结构指纹 — 零信号。in-process 场景扫验证 silent
> miss → 加 GapKind + classifier。二分化丢 dose-response 信息 / 效率
> （Royston-Altman-Sauerbrei 2006 *Stat Med* 25:127）、对切点敏感
> （Altman et al 1994 *JNCI*）、被二分 confounder 留类内残余混杂
> （Becher 1992）；INFORMATIONAL，指向 Themis 自有 dose-response 路径
> （Phase 13/14）。横跨「连续/数据驱动估计」与「可观测识别」两块，与 `measurement` /
> 206 ObservationStatement / 207 state_vs_event 同型，第四例
> dead-schema-theatre fix；总数 31 GapKind。
> 2026-05-10（`state_vs_event` 是第三个只被 schema 承认、无人读取值的字段：
> `ill_defined_intervention_versions` 把 `state_vs_event="state"` +
> 无 `time_window` 的 intervention 暴露为 Hernán & Taubman 2008 *IJO*
> "Does obesity shorten life?" 的 well-defined-intervention prerequisite
> 违反 — schema 200+ iters 前就 admit 这两个字段，但 pre-207 没有任何
> classifier 读 state_vs_event 的 VALUE。L3 case 015 (obesity → 5yr
> mortality) 真测确认 silent miss → 加 GapKind + classifier。boards
> 横跨「可观测识别」与「连续/数据驱动估计」：不增加单一板块覆盖率，但首次让 schema 中的
> consistency-assumption-relevant 字段在 runtime 起作用。这是 iter
> `measurement` 与 ObservationStatement 之后第三例同型
> dead-schema-theatre fix；总数 30 GapKind。
> 2026-05-07（测量误差从 0% → 5-10% 首次破冰：
> 加 `measurement_error_concern` gap_kind，从程序结构（变量 measurement /
> observability 字段值含 self-report / single-occasion BP / 24h recall / FFQ /
> questionnaire / proxy 等 documented 模态）surfacing 测量误差风险。L3 case
> 013 MacMahon 1990 Lancet BP-CHD 案例真测发现真 gap → 加 GapKind + classifier
> + suppression（case 011 `measurement_quality` ambiguity 路径）。修
> probability 查询 dispatch 路径上的 d-sep
> guard dormant bug：L3 case 012 真实案例压测发现 `_dispatch_probability`
> 从未把 bidirected 传给 `_try_numeric`，导致 chain DAG + marginal-only
> theta + probability query 整条路径默默用 marginal 替代条件量。修复
> 5 行 + 加 sync pin。d-sep refusal 升格为
> 一等 GapKind `graph_theta_independence_mismatch`：现在
> data_gap_report.gaps[].kind 直接告诉下游 LLM/UI "图与 CPT 矛盾，
> 修图或补条件量"，不再被 generic `missing_distribution` 误导成"补更多
> 数据"；d-sep guard 拒绝路径加结构化诊断；verifier
> 端 d-sep guard 镜像补完，R7 不再 silently 同意 runtime 的链式 DAG +
> marginal-only theta 错误数字）
> 本文档跟踪 Themis 对"因果定量问题全 12 板块"的实际覆盖进度。每完
> 成一个 slice 同步更新。配套 [VISION.md](VISION.md) "扩展愿景" 段 +
> [ROADMAP.md](ROADMAP.md) Phase 6+。

---

## 12 板块与当前覆盖

| # | 板块 | 覆盖 | 现状 / 策略 |
|---|---|---|---|
| 1 | 可观测识别 | **~90%** | backdoor ✓ / front-door 单 + 多 mediator ✓ / IV ✓ / **完整 ID (Shpitser) 含 Line-7 嵌套 ✓**（`314c1de`：do-无关 Tian Identify，napkin / 多 mediator 扩展 napkin / parallel multi-mediator 全部非参数识别，探针验；不可识别 case 带 hedge 证明正确 punt）/ **ananke parity 实证（2026-06-16）**：Themis `identify_via_tian` 对照 `ananke` OneLineID 扫 14,360 个 ADMG（全部连通 4 节点穷举 8354 + 5 节点采样 6000），**零漏识别、零过度声称**——含 ~7,460 个可识别图，非空覆盖。slice-3 图感知完备层经此确认**当前不需要**。可复跑：`tests/test_parity_ananke_nested_id.py`（skip-if-no-ananke）|
| 2 | ADMG / 潜变量 | **~91%** | bidirected ✓ / m-sep ✓ / ADMG-backdoor/front-door ✓ / **Tian-Pearl ID Lines 1-6 ✓ + 多种 e2e 解锁** ：修复 degenerate-sum bug；验证器放松（admissible_given = parents ∪ directed_ancestors ∪ bidirected_siblings）；runtime 自动边缘化 Σ_z P(Y\|given,Z=z)·P(Z=z\|given) 递归 depth ≤ 3；verifier 镜像。**Bayes 反转**：P(M1\|X,M2) = P(M2\|X,M1)·P(M1\|X)/P(M2\|X)，解锁链式 mediator front-door 变种；N-mediator 链通过递归自然处理。capability ladder：disjoint-Y c-component / 单 mediator front-door 变种 / 链 mediator front-door 变种 / N-mediator 链。**Line 7 完整嵌套 ID 已落（`314c1de`，2026-06-16）**：do-无关 Tian Identify（Lemma 4 c-factor 比值 + Phase 16 eager 化简，do 值只在边界施加）解锁 extended napkin (1-3 mediator) + **parallel multi-mediator (X→M1→Y, X→M2→Y, X↔Y)**（原残留 gap，现 probe=match）。图感知完备层（JMLR Alg 1）按真实压力触发 |
| 3 | 反事实（Layer 3） | **20-25%** | **Phase 5 §C 已落地（窄 scope）**：Balke-Pearl 二值单调 bounds + counterfactual query + monotonicity needs_assumption 通道 / ID\* / 连续 ✗ → 长期 |
| 4 | 时序 / 动态 | **30-35%** | **Phase 5 §T 已落地**：atom `time_index` 一等公民 / 时间展开 graph / verifier T1-T3 / case 14 e2e ✓ / g-methods ✗ / 连续时间 ✗ → Phase 9+ |
| 5 | 工具变量 (IV) | **~85%** | **Phase 6.iv + Phase 7.3 全部落地**（basic + conditional + ADMG-aware identification + Wald LATE / 2SLS ATE 数值估计）|
| 6 | 中介分析 | **~80%** | Phase 6.mediation 识别 ✓ / **Phase 7.4 Imai NDE/NIE 数值估计 ✓**（via statsmodels）/ **Phase 7.5 CDE numeric ✓ 且从 `themis.estimate` 可达**（#481；`strategy: "cde"`——自然效应不可识别而受控效应可识别的那条分支——走 `estimate_cde_curve`，sklearn plug-in g-formula，结局模型带 X:M 交互，答案是**按中介固定水平索引的曲线**而非点，二值中介读样本真有的取值、连续中介读分位数并如实声明；线性路径由记录的 θ_x/θ_xm 逐数重导）/ **Phase 7.5+ CDE chain ✓ 但仅作为直接 API**（`estimate_cde_chain`，VanderWeele 2015 ch.5；调度层明说 `numeric_end_not_built`——中介**集**的参考值是向量，曲线形状按一个数给行编索引）；多 mediator 联合（非链式）/ NIE 链式分解 → 后续。**这一行在 #481 之前写着「CDE numeric ✓」而没有任何程序到得了它**——「估计器存在」不等于「有路走到它」，勾要说清是哪一个 |
| 7 | 选择偏差 | **45-50%** | A1 §3a / A2 refusal pattern ✓ / **kernel V-set 放松** ✓（refusal-only 图返回 `cause=false (no path)`，case 16 e2e ✓）/ **`collider_conditioning_opens_backdoor` gap_kind ✓** (EffectQuery `given` 中含 collider 时结构性诊断) / **`selection_on_collider_opens_path` gap_kind ✓** (**ObservationStatement(W, value) 编码隐式样本限制 + W 是 X/Y 共同后代时 surface Hernán-Hernández-Díaz-Robins 2004 *Epidemiology* 15:615 "A Structural Approach to Selection Bias" 经典结构**；与 explicit-given 那条互补 —— 两条路径都覆盖) / **§S9.1 可恢复性判决 ✓**（Bareinboim-Pearl 选择后门 `recover_effect`，`extensions.selection_recovery` 给恢复公式 + 外部数据账本 + `verify_selection_recovery`）/ **§S9.1 数值端 + 诚实门 ✓**（2026-07-13，`estimation/selection.py` 按定理3.5 从有偏样本 + 外部无偏 `reference_data` 求恢复后 ATE；选择偏倚在场时**抑制**普通后门有偏数、改 `external_data_required`/`not_recoverable` 拒绝；`verify_selection_recovery_numeric` 从每层计数 + 权重表独立重跑公式）/ 选择节点结构 (selection_node 已存在仅用于 transport) / IPSW selection-weight 加权 + 连续 proxy / Z⁺,Z⁻ 完备恢复算法(BTP-2014 RC) → 后续 |
| 8 | 测量误差 | **~70%** | **诊断 + 校正两层都在**。诊断：`measurement_error_concern` gap_kind 从程序结构（变量 `measurement` / `observability` 字段值含 self-report / 24h recall / single-occasion BP / questionnaire / FFQ / proxy 等已 documented 的高噪声模态）surfacing 风险，文献依据 MacMahon 1990 Lancet (regression dilution) / Hernán & Robins What If §9 / Fuller 1987。校正：**离散**=混淆矩阵求逆（结局 / 暴露 / 双信道 / 差异 / 按协变量差异五种）；**连续线性结局**=regression calibration 矩量校正（暴露和/或后门协变量）；**连续非线性结局**=SIMEX 模拟外推（#463，Cook & Stefanski 1994，梯子是充分统计量故第二阶段逐数可重算，区间走 Stefanski-Cook 1995 τ 外推而非 bootstrap）；**连续结局**=不偏故只报精度代价；**Berkson 结构**=不校正、只报代价（#464，Berkson 1950，`X*=W+U` 下 `E[X*|W,Z]=W` 故朴素后门斜率本身就是因果斜率，校正它反而把真值 0.8 的答案改成 1.6；散布按 β̂²σ²_u 落进残差，是这一族里唯一被答案缩放的声明方差，故排在答案之后；结构无数据见证，靠 `structure: berkson` 声明，不认识的结构词也归这一行以免声明静默丢失）；**差异型**（#465，误差含一份随结局走的分量 `U=δ·Ỹ+f`，同时抬高观测方差**和**协方差，故矩量校正只除掉前者会落到真值另一侧——实测真值 0.8、给它正确的总方差，δ=−0.4 时它给 0.398、δ=+0.5 时给 0.900；闭式先把 δ·Var(Y|Z) 从协方差里减掉，`βx=(C−δB)/S`，δ=0 时精确退回 regression calibration，差 4.4e-15；δ 只能来自验证子研究，样本分不开 δ 与 βx）。未做：结局信道的差异误差、Cox、验证研究本身不确定性的传播、分类协变量 |
| 9 | 转移性 / 泛化 | **35-40%** | **Phase 9 §T9.1 已落地**：单源 + 可观测 S 的 Bareinboim transport identification（schema + types + identify + verifier T9-1/T9-2 + case 29）/ **Phase 9 §T9.2 已落地**：post-stratification numeric (Cole & Stuart 2010 §3) — `estimate_transport` + dispatch path + bootstrap CI / **多变量 Z 联合已落地**：joint post-stratification over the Z set（结构层早已产多-Z S-admissible 集，数值端追平 + joint target `cells` 表 + E2E + verifier round-trip）；多源 §T9.3（mz-transportability，需结构地基）/ latent S / IPSW (Westreich 2017) → 后续 |
| 10 | 敏感性分析 | **~35%** | **Phase 8.2 已落地**（VanderWeele E-value 自动附在 binary 估计 + Chinn 2000 SMD→RR 路径让连续 outcome 同样获得 E-value）；Rosenbaum bounds / 多假设 sensitivity → 可选扩展 |
| 11 | 连续 / 数据驱动估计 | **~55-65%** | **Phase 7.1-7.4 + Phase 14 已落地**（backdoor + front-door + IV + mediation numeric，4 条识别路径都能给数字 + CI；dose-response estimator 支持 LinearDML / CausalForestDML opt-in / DRLearner）/ **前门的中介现在可以是连续的**（#483；`frontdoor_empirical_{linear,logistic}`——P(M|X) 取自各臂自己的样本行而非拟合的多项 logistic 链，每行两次模型求值，不枚举分层因而也不受交叉积上限约束；线性形态的点由记录的结局系数 × 中介位移逐数重导。枚举路在可精确求和时仍然优先，已发布的数一个没动）|
| 12 | 因果发现 | **~56%** | **Phase 8.1 已落地**（PC/FCI/GES/GRaSP/LiNGAM via causal-learn + kernel_ast suggestion path）；**borrow-list #4：Markov blanket（grow-shrink 到不动点，连续/Fisher-Z + 离散/卡方两条路径）+ 独立验证器 `verify_markov_blanket`**——发现层首个逐数验证（从记录的充分统计量[相关矩阵 / 稀疏联合列联表]重算完备性/最小性定义）；**时序 PCMCI（#449）+ NOTEARS（#462，自写：连续优化 + 可重算证书 + 逐边尺度稳健性）**——三个 artifact 各有独立验证器 |

**加权覆盖**：约 **65-75%**。**Phase 7 M2 + Phase 8 M3 + Phase 5 §T/§C + Phase 9 §T9.1 + Phase 10-14** 全部落地——识别 / 估计 / 敏感性 / 发现 / 时序 / 反事实 / 转移性 / 数据缺口诊断 / dose-response 诊断与估计里程碑齐全；**Phase 10 数据缺口诊断器**作为 VISION 定位收紧的输出 (2) 通道独立交付。Phase 4 上游层端到端 e2e 3/3 通过（cases 14/16/21）；Phase 9 §T9.1 case 29 跑通；Phase 10 §10.5 五种 gap_kind e2e 全部跑通；Phase 13/14 把 dose-response 从数据规格推进到估计曲线。

> **Phase 10 不在 12 板块内**——它是输出层，不是新算法。但它是 Themis
> 真正独占的生态位（"告诉用户去收什么数据"），见 VISION "定位收紧
> (2026-04-26)" 节。所以从覆盖率角度它不计入板块，但从产品价值角度
> 是一个独立里程碑。

---

## 元基础设施（不在 12 板块内但是核心价值来源）

这部分 Themis 比任何单一开源库都强——**没有同类**：

| 基础设施 | 状态 |
|---|---|
| NL↔JSON 桥（A1 v2.7 / A5 / A2 / response_rendering v3.2） | **~100%** |
| 上游层 narrative_merge（变量+边对称合并 + compose_program） | **~100%**（down-payment；ROADMAP 真独立层 → 长期） |
| V0-V5 独立 verifier（byte-code scan 钉独立性） | **~100%** |
| **T10 DataGapReport 独立 verifier**（byte-code scan 钉独立性，Phase 10）| **~100%** |
| Derivation JSON + 审计字段 + `success` 字段（Phase 10 标失败 step） | **~100%** |
| ambiguity kind 分类体系（loose-string；A1/A2/A5 prompts + eval_set fixtures 联合用例） | **~100%** |
| **DataGapReport schema (42 gap_kind / 3 severity / 4 ref_kind, Phase 10+13+iter expansions)** | **~100%** |
| Eval set (29 cases / F1-F26) + 真实 LLM 基线 | **~100%** |
| `investigation_request` 报缺 + fill-back | **~100%** |
| Schema 层（atom / kernel_ast / query_result / derivation） | **~100%** |
| Theta 数值层 + confidence 聚合 | **~100%** |
| MCP server 包装（19 tools + 12 resources，stdio） | **~100%** |

---

## 每板块的具体策略

### 自家写（所有 production 代码在 `themis/` 下）

- 板块 1-10、12 的大部分算法
- 见具体板块的 "策略" 列

### 外部库的位置：只作 parity calibration，不作 production backend

开发时 pip install 以下库跑 parity test，**production 依赖里不包含**：

- **DoWhy**：板块 1 (identify) 的 parity 校准
- **EconML**：板块 5 / 6 / 11 的 parity 校准
- **causal-learn**：板块 12 的 parity 校准
- **pgmpy**：板块 2 BN 推理的 parity 校准
- **statsmodels / sklearn**：作为 ML 原语依赖，production 里装

### API 调用的 5 条允许规则

允许接外部 API 作 production backend 的条件（**必须全部满足**）：

1. ✅ 函数是**确定性纯变换**（同输入同输出）
2. ✅ 库有 **5+ 年稳定 track record**（主要 API 未破坏性变更）
3. ✅ **pin 具体版本**（`dowhy==0.11.1`，不用 `>=`）
4. ✅ 配套 **parity test**，每次升级必跑
5. ✅ 结果可 **完整嵌入** derivation JSON（无隐藏状态）

**任何一条不满足就自家写**。

**结论**：估计层（板块 11）的 ML 估计器**永远不接 API**——默认参数
漂移 + 随机性会破坏可审计承诺。识别层的纯算法 API（如 DoWhy.identify）
理论上可接，但因为 Themis 自己也要实现识别层，实际上还是自家写。

### 明确 defer / 不做的

- **C++ 核心方法** (grf 原版 Causal Forests) ——vendor 成本过高 /
  V0-V5 审不到 C++ 层。按需写纯 Python 简化版或 defer
- **SuperLearner TMLE** / 研究级统计方法——需要真实统计专家审
- ~~**NOTEARS**~~——**已做（#462，自写非 vendor）**。Gram 矩阵是充分统计量，所以「连续优化验不了」这条推迟理由不成立；同族的 DAG-GNN / RL-discovery 没有这条，推迟理由对它们仍然成立
- **连续时间 SDE 因果**——不在 long-term scope 内
- **非因果问题**（预测、相关挖掘、纯 Bayesian 建模、优化）——明确
  不是 Themis 的场景，路由层识别后返回 "out of scope"

---

## 完成节奏目标

| Phase | 对应里程碑 | 完成后覆盖率（估）| 时间预估 |
|---|---|---|---|
| Phase 6 | M1 识别完整化 | ~30% | 4 周（不含 complete ID）|
| Phase 7 | M2 基础估计 | ~55% | 6-8 周 |
| Phase 8 | M3 发现 + 敏感性 | ~70% | 4-6 周 |
| Phase 9+ | 按需扩展 | → 逐步达 85-90% | 按真实压力 |

总计 M1-M3 约 **3.5-4.5 个月**完成核心三个里程碑，剩余部分按真实需
求逐个推进，永远不追求"100% 覆盖"（因为最后几个板块的 ROI 很低）。

---

## 和现有开源生态的差异化

每完成一个 slice 问自己这个问题：
**"Themis 在这个板块比 DoWhy / EconML / causal-learn 多做了什么？"**

答案应该来自 4 个维度：

1. **NL-native 接口**：用户用自然语言描述问题，不是填 API 参数
2. **Ambiguity 显式声明**：用户的歧义被识别 + 分类 + surface
3. **Derivation 可审计**：每一步推导有 rule name + witness
4. **V-verifier 独立审查**：结果不是"信 library"，是"我们重检过"

**如果某 slice 做完只是"复刻了 DoWhy 的算法"，那不是 Themis 想做
的东西**——必须能在上述 4 维之一显示出 Themis 的增量价值。

---

## 更新规则

- 完成一个 slice 后更新对应板块的百分比
- 新加板块或重排策略要先改 VISION / ROADMAP 再同步此文档
- 表格里的数字是主观估计，不是测试覆盖率，但要随着 eval set 扩大
  趋于准确
