# Phase 9 §T9 Charter — 跨人群转移性 / 选择图

> 立项日期：2026-04-25
> 状态：**Draft，待 review**
> 对应 ROADMAP：Phase 9+ 板块 9（转移性 / 泛化），从 0% → 起步
> 触发：W0 跑步瘦肚子真实压测发现"文献给的 55% 是 35-50 男性
> RCT，用户是 28 岁女性"——transport 缺口

## 0. 本 charter 结构

板块 9 整体（多源 transportability、不可观测 S、selection bias
变体）非常宽。本 charter 只立第一个最小 fragment **§T9.1 — 单源
transportability with observable S**，对应 Bareinboim & Pearl 2014
论文里**最朴素的那一类 transport criterion**。

后续 fragment（多源 / 隐 S / source-side selection bias）按真实
压力另立 charter。

这是 Themis v1.0 核心冻结面的一次**显式解冻申请**。

---

## 1. 动机

### 1.1 真实压力来源（W0 case 续）

2026-04-25 会话中，跑步瘦肚子这条 NL 走完 NL→A1→themis.run→
WebSearch→apply_patch_and_run→numerically_solved 全闭环，给出
`P(belly_fat_loss=true | do(running=true)) = 0.55`。

但用户立刻指出：

> 文献是 35-50 岁超重男性 RCT，你是 28 岁正常体重女性。这个
> 0.55 多大程度上适用？

**这不是数值问题，是结构问题**——源人群 (`pop=meta_analysis_2022`)
和目标人群 (`pop=user`) 在 age / BMI / sex 上分布不同；这些变量**同时**
影响 outcome。文献的 ATE 想搬到目标人群必须做 transport 调整。

当前 kernel：
- 不知道"人群"是个概念
- 不能区分 source vs target
- 不能表达"S 节点"（标注分布差异源）
- 不能跑 transport identification

→ 这是一个**真实的"用户问出来的"瓶颈**，不是假设性需求。

### 1.2 理论 fragment 是否已固化

**完全固化**：
- Bareinboim & Pearl 2014, "Transportability from Multiple Environments
  with Limited Experiments: Completeness Results"
- Bareinboim & Pearl 2013, "Causal Transportability with Limited
  Experiments"
- Pearl & Bareinboim 2011, "Transportability of Causal and Statistical
  Relations: A Formal Approach"

理论给了：
- **Selection diagram** D：在原 DAG 上加方块节点 S（每个 S 指向
  一个变量，表示该变量在两群人间分布不同）
- **S-admissibility 判定**：Z 是 S-admissible 当且仅当
  Z d-separates S from Y in D_{\bar{X}}（移除 X 入边的图）
- **Transport formula**：当 Z S-admissible 时，
  `P*(y|do(x)) = Σ_z P(y|do(x), z) · P*(z)`，其中 P 是源、P* 是
  目标（Z 在目标群体上的分布是已知 / 可估的）
- **完备性**：Bareinboim 2014 给出**完整算法**判定 transport 是否
  可行 + 返回公式

满足 ROADMAP "理论 fragment 已清晰定义" 的启动门槛。

### 1.3 开源 / 同类工作现状（按 CLAUDE.md "先读开源" 检查）

- **Python OSS 生态**：**无 production 实现**。只有学术论文 + Causal
  Fusion (Columbia) 这种学术 web demo。
- **DoWhy**：无
- **EconML**：无
- **causal-learn**：无（专注 discovery）
- **R 生态**：有 `generalize` / `transportability` 等包，但都是
  **估计层方法**（IPSW / TMLE），不做结构层 identification
- **流行病学方法学**（Degtiar & Rose 2023 review）：方法名词成熟，
  但 selection-diagram-based identification 这一段在工程实现上
  几乎空白

→ Themis 做这块属于**Python OSS 内首发**，符合差异化定位（NL-native +
verifier + provenance + audit-friendly）。**不 vendor，自家写**。

### 1.4 对称性论证

- **和 Phase 2.latent (ADMG)**：ADMG 在**变量间**加 bidirected 表达
  潜共因。§T9 在**人群间**加 S 节点表达分布差异。结构相似但维度不同。
- **和 Phase 5 §T (temporal)**：§T 加 `time_index` 到 atom，增 1 维。
  §T9 加 `population` 到 query + 引入 selection_node 语句类型，增 1 维。
  正交。
- **和 Phase 5 §C (counterfactual)**：§C 是 Layer 3。§T9 仍在 Layer 2
  (do-calculus)，但 across populations。正交。

---

## 2. §T9.1 单源 transport fragment

### 2.1 动机段（见 §1.1）

### 2.2 语言扩展

#### 2.2.1 query 加可选 `target_population` 字段

```json
{
  "kind": "effect",
  "intervention": {...},
  "target": {...},
  "given": [],
  "target_population": "user_28f_normal_weight"
}
```

不带 `target_population` 的 query 行为不变（向后兼容）。带 `target_
population` 的 query 触发 transport identification 路径。

#### 2.2.2 新语句 `selection_node`

```json
{
  "kind": "selection_node",
  "id": "S_age",
  "affects": {"predicate": "age", "args": [{"type": "const", "name": "me"}]},
  "source_population": "meta_analysis_2022",
  "target_population": "user_28f_normal_weight",
  "annotations": {
    "source": "narrative_proposal | llm_proposal | <citation>",
    "evidence": "源人群均值 42 岁; 目标 28 岁"
  }
}
```

S 节点不出现在 G(M) 里，只出现在**selection diagram D** 中
（D = G(M) ∪ {S 节点 + S→affects 边}）。**reasoning 不读
annotations**，纯 provenance。

#### 2.2.3 数据语句加 `population` 标签（可选）

```json
{
  "kind": "probability",
  "target": {...},
  "given": [...],
  "value": 0.55,
  "population": "meta_analysis_2022",
  "annotations": {"source": "PMC9540641"}
}
```

不带 `population` 的 probability 视为对所有人群通用（向后兼容；
等同 source = target）。

### 2.3 识别规则

新 rule（在 verifier rule registry 加）：

- **`s_admissibility_check`**：给定 selection diagram D, treatment X,
  outcome Y, candidate adjustment set Z；判 Z 在 D_{\bar{X}} 中是否
  d-separates S from Y。复用现有 d-separation 实现，只是图加了
  S 节点。
- **`transport_formula`**：当 Z S-admissible 时，emit
  `P*(y|do(x)) = Σ_z P(y|do(x), z) · P*(z)` derivation step。
- **`identify_via_transport`**：组合上面两条 + 检查 source 数据可用
  + 目标人群 P*(z) 可用。

### 2.4 估计扩展（可选，留给 §T9.2）

§T9.1 **只到结构层 identification**——给出公式形状，告诉用户"需要
源 P(y|do(x), z) + 目标 P*(z) 这两类数据"。**不做数值估计**。

数值估计（IPSW / outcome-model transport / doubly robust transport）
是后续 fragment §T9.2，独立立项时考虑 vendor `survey` / `Generalize`
之类的 R/Python 包。

### 2.5 verifier 独立审

新独立 rule 文件 `themis/verifier/rules.py` 加：

- **T9-1**：`s_admissibility_check` 的独立 d-sep 复检
- **T9-2**：`transport_formula` 的形式正确性检查（Σ 在哪些变量上、
  P 和 P* 的归属正确）

byte-code scan pin 这些规则**不依赖** transportability 推理本身的
实现路径——和现有 V0-V5 同样的独立性保证。

---

## 3. Sub-slices

| Slice | 内容 | 估时 |
|---|---|---|
| **S.T9.1.1** schema | atom_schema / kernel_ast schema 加 `selection_node` / `target_population` / `population` 字段 | 半天 |
| **S.T9.1.2** types | types.py 加 `SelectionNode` dataclass；instantiation / projection 处理 | 半天 |
| **S.T9.1.3** identify | `s_admissibility_check` + `transport_formula` + `identify_via_transport` 三条规则 + dispatch | 2 天 |
| **S.T9.1.4** verifier | T9-1, T9-2 独立审 | 1 天 |
| **S.T9.1.5** eval | 加 case 29: 跑步瘦肚子 transport（源=meta_analysis_2022，目标=user_28f） | 半天 |
| **S.T9.1.6** prompt | A1 加 `population_mismatch` 识别规则；narrative_to_edges 加 selection_node 识别；response_rendering 加 transport disclosure 段 | 1 天 |
| **S.T9.1.7** docs | CORE_STATUS / COVERAGE_MAP / failure_modes (F25 transportability mismatch) 同步 | 半天 |

**总计 ~5-7 个工作日**（charter 标准 1-2 周内）

## 4. 显式 Out-of-scope

按 Phase 2.latent 经验，charter 一开始就划清边界：

- **多源 transport**（Bareinboim 2014 multiple environments）→ §T9.2
- **不可观测 S**（latent transport, much harder）→ §T9.3
- **Source 端 selection bias**（Bareinboim 2018 selection in source）
  → 单独 fragment
- **Counterfactual transport**（Bareinboim & Pearl 2013 limited
  experiments + counterfactual） → 等 §C 扩展时合并考虑
- **数值估计** (IPSW / outcome model / doubly robust transport) → §T9.2
- **自动检测分布差异**（从两个 dataset 自动 propose S 节点）→ Phase 12
  discovery 范畴

## 5. 完成标志

- S.T9.1.1 - S.T9.1.7 全部测试通过
- W0 跑步 case 跑通 transport 路径：返回 transport formula +
  指出"需要 P*(age, BMI) 在用户人群"
- COVERAGE_MAP 板块 9: 0% → 25-30%
- failure_modes.md 加 F25
- 在 case 25 (med→BP) 上验证 transport 不影响原有 backdoor 路径
  （向后兼容）

## 6. 验收

- 全部独立 verifier 通过
- 1015 baseline tests 不降级（向后兼容）
- 新增 ~10-15 测试覆盖 S.T9.1.* 各 slice

## 7. 不做的（永远）

- C++ 优化版本：板块 9 性能不是瓶颈
- 无监督自动 S 检测：理论上是 discovery 范畴，不在 §T9 内
- 多目标群体同时 transport：罕见场景，多源 transport 后再考虑

---

## Review checklist（请 Reviewer 答）

1. ☐ Scope 是否合适？S.T9.1 切到"单源 + observable S + 结构层"是否够小？
2. ☐ Schema 改动是否最小？query 加 `target_population` + 新 statement
   `selection_node` 是否够，要不要加 `population_decl`？
3. ☐ 估时 5-7 天是否合理？和 Phase 6.iv 7-slice 对比看？
4. ☐ §T9.1 不做数值估计，只到 formula 形状——是否会让 W0 case 真正
   闭环？还是必须连 §T9.2 一起做才能"用起来"？
5. ☐ 命名约定：`target_population` / `selection_node` / `affects` —
   或换成 `population_pair` / `S_node` / `partitions`？
6. ☐ Out-of-scope 列表是否够明确？
