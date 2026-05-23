# Fix 3+4 Charter — LLM-mediated transport with priors

> 立项日期：2026-05-23
> 状态：**📝 charter only —— 未实施**
> 对应 task：session todo #127 + #128
> 取代：本 charter 取代 `FIX_3_CHARTER_llm_prior.md`（独立 Fix 3 charter）—— Fix 3 与 Fix 4 在产品语义和实施上共生，独立 charter 化已是 split-brain
> 前置依赖：
> - Gap B (v0.1.3) — `ProbabilityStatement.provenance` 字段 + `observational` 取值
> - A2 (slice) — `CauseStatement.annotations.source`（边的来源标注）
> - Fix 1 (v0.1.4) — mediation 数值评估，证明"kernel 把活干到底" + 公式 builder + 求值 + verifier 孪生四件套是可行模板
> - Phase 9 §T9.1 — `SelectionNode` + `EffectQuery.target_population` + `ProbabilityStatement.population` 字段 + Bareinboim Theorem 1 结构识别已落地（**§T9.2 数值评估推迟到本 charter**）

---

## 0. Scope

**本 charter 同时管两件事，因为它们在产品语义上是同一件事**：

1. **Fix 3 部分**：LLM 在用户没给 theta 时**有限度地**提议参数（`provenance: "llm_prior"`），并**强制审计透明**
2. **Fix 4 部分**：Transport 识别成功 + theta 充足（包括 LLM-proposed）时，kernel 评估 Bareinboim 公式给出数字，而不是 STRUCTURALLY_SOLVED

**两者合一**的关键洞察（见 §1.3）：
- Transport 公式天然需要 target population 的边缘分布 `P*(Z)`
- 真实部署里**没有用户会查目标群体的数据**
- LLM 从常识 propose `P*(Z)` + 用户审核 = 唯一可行的真实流程

→ Fix 3 是 Fix 4 在真实场景下能跑通的**必要前提**。反过来，transport 是 Fix 3 最经典、最有价值的使用场景。

不做：
- 单 population 的 Fix 3（独立 `llm_prior` 不接 transport）——技术上能拆但产品无意义；如果未来出现非 transport 的 llm_prior 场景，再独立做
- 实验干预的非 boolean 离散 / 连续场景（boolean MVP 同 Fix 1）
- 多 mediator + transport 联合（先二选一）
- target population 真实数据接入（KB / DataFrame）——本 charter 只走 LLM-proposed 路径，真实 target 数据是 Phase 11.2 (KB adapter) 和 Phase 7 (DataFrame) 的事
- 新 ResultStatus（用 extensions 信号 + provenance trail 即可）

---

## 1. 动机

### 1.1 真实部署里"几乎所有问题都是 transport"

vanilla LLM-Themis 链路上 99% 的用户问题：
- "我朋友 60 岁糖尿病，吃阿司匹林会出血吗？"
- "我读了 Boston 这个 RCT，对中国农村人群适用吗？"
- "我们公司 SaaS 用户教育水平偏高，A/B 实验结论能搬到大众市场吗？"

**没有一个**问题问的是 source population 内部的事。每个都是"source 数据 → user 所属的某个 target stratum"的隐式 transport。

Themis 当前的 Phase 9 §T9.1 完成了结构识别（"transport 是否 identifiable"），但**数字给不出**（§T9.2 推迟）。这意味着**普通用户用 Themis 问真实问题，永远拿不到具体效应数**。Themis 沦为"yes/no 可识别性"工具。

### 1.2 核心张力

Themis 的卖点是 "**LLM 不能编数字 → kernel 把数字钉死在数据 / 用户陈述参数上**"。

Fix 3+4 看似软化此承诺 —— LLM 提议 `P*(Z)`，kernel 接受。如果做粗糙，Themis 退化为 "self-confirming：LLM 编 prior，kernel 用 prior 算 transport，下游看到 `numerically_solved` 以为有数据"。

化解：**承认 LLM 提议合法，但强制每一项可审查 + 用户在使用前看到清单**。Themis 不是答案生成器，是**审计者 + 缺口诊断器**（memory `project_themis_repositioning_data_scarcity`）：

- LLM **提议** → kernel **计算** → 用户 **审核**：三方分工
- review surface 自动列出所有 LLM-proposed 量（边 + 概率 + target priors）
- Skill 强制 reply 以 review 表面开头

### 1.3 用户洞察（设计转折点）

2026-05-23 session 里用户提出：

> "是不是可以 LLM 猜 population 然后用户纠正呢 现实中把用户当做一个人群的平均去计算也很合理吧？"

**这句话定义了本 charter 的产品哲学**：

> Themis 不假装能预测**单个个体**的反事实。Themis 给的是**用户所属那个 stratum 的群体期望**。这跟 transport 的数学语义自洽 —— 群体平均近似个体。Stratum 内个体差异不在估计范围。

—— vanilla LLM 默认假装在做个体预测；Themis 显式坦白"我给的是 stratum 平均"。**这条 disclaimer 就是 Themis 的产品差异化**。

### 1.4 兜底 vs 机会主义（继承 Fix 3 原 charter §1.3）

LLM 默认**不**提议；只有当第一轮 `themis.run` 在 transport 公式上撞 `InsufficientTheta` 时，LLM 才提议 `P*(Z)`。

- 兜底：单一 fallback chain（用户数据 > 用户陈述 > LLM prior），易审计
- LLM 提议**精确缺哪些 keys**，不是猜哪些可能缺
- 用户陈述的数字**永远**优先

---

## 2. 两条用户路径（产品分层）

### 路径 A — CATE：用户作为 source 已分层 stratum

当 user 协变量**在 source 数据里已经分层**：

```
LLM 构造 EffectQuery：
  intervention: aspirin = true
  target: bleeding = true
  given: [age = "60+", has_hypertension = true]   ← user 协变量

→ Themis backdoor / front-door 在 source 数据子集上跑标准识别
→ 返回该 stratum 内的 ATE
```

**已工作 — 无需 Fix 3+4**。本 charter 不动 path A，但 Skill 段落会教 LLM **首选** path A，path B 是 fallback。

### 路径 B — Transport with LLM-proposed target priors

当 user 的 stratum **不在 source 数据**里（age 范围不重叠 / 国家不同 / 共病组合 source 没研究过）：

```
LLM 识别 source vs target 的 S-nodes（differing mechanisms）
LLM 构造带 SelectionNode 的 program + EffectQuery.target_population
                                                                
第一轮 themis.run →
  Bareinboim 公式：P*(Y|do(X)) = Σ_z P(Y|do(X),z) · P*(z)
  → InsufficientTheta：缺 P*(z=value) for value in z.domain

第二轮：
  LLM 看 missing_keys → 从常识 propose P*(z=value)
  patch bundle：
    [{ProbabilityStatement, population: "target_xxx",
       provenance: "llm_prior",
       annotations.source: "<一句话理由>"}]
  
  themis.apply_patch_and_run →
    numerically_solved
    + extensions.transport_identification.numeric
    + extensions.llm_proposed_review 列出所有 LLM 提的 P*(z)

回答用户：
  "在你这种 stratum（60+ T2DM 中国农村）上，预计副作用率 12%。
   依赖以下 LLM 提议的 target prior（请审核）：
     - P*(age=60+) = 0.6（理由：你说你 60 岁）
     - P*(has_t2dm) = 1.0（理由：你说你有糖尿病）
     - P*(rural) = 0.7（理由：常识：中国农村人口比例）"
```

---

## 3. 语言扩展

### 3.1 schema 变更 — Fix 3 部分

**`themis/types.py:ProbabilityStatement`**：

```python
provenance: Literal["structural", "observational", "llm_prior"]
```

第三个取值新增。语义：

| 值 | 含义 | 校验行为 |
|---|---|---|
| `structural` | 用户陈述的 CPT 条目（默认） | parent-subset 严格校验 |
| `observational` | 经验观察条件值 | 跳过 parent-subset 校验（Gap B） |
| `llm_prior` | LLM 常识 prior | 跟 structural 同，但**额外要求** `annotations.source` 非空 |

**`themis/types.py:Annotation`**：现有 `source` 字段；llm_prior 时强制非空非空白。

**`themis/schemas/kernel_ast.schema.json`**：
- `provenance` 枚举加 `"llm_prior"`
- conditional schema：if provenance == llm_prior then annotations.source required & non-empty

### 3.2 schema 变更 — Fix 4 部分

**`themis/runtime/numeric_estimator.py:ProbabilityKey`**：

```python
@dataclass(frozen=True)
class ProbabilityKey:
    target_atom: Atom
    target_value: AtomValue
    given: frozenset[tuple[Atom, AtomValue]]
    population: str | None = None     # 新；None = 默认 / source
```

**`themis/types.py:ProbabilityRefExpr`**：

```python
@dataclass(frozen=True)
class ProbabilityRefExpr:
    target: ValuedAtom
    given: tuple[ValuedAtom, ...]
    population: str | None = None     # 新
```

**`themis/schemas/derivation.schema.json`**：probability_ref 子 schema 加 optional `population` 字段。

**`themis/schemas/query_result.schema.json`**：
- `extensions.transport_identification` 加 `numeric` 子字段（结构类似 `mediation_decomposition.numeric`）
- `extensions.llm_proposed_review` 新顶层字段

### 3.3 backward compat 保证

- 所有现有 ProbabilityStatement 默认 population=None → key population=None
- 所有现有 ProbabilityRefExpr 默认 population=None → key lookup population=None
- 所有 backdoor/frontdoor/mediation builder 不传 population → 默认 None
- **预期 1979 现有测试在 4.1-4.5 完成后仍 1979 passed，0 退化**

---

## 4. 数据流（联合兜底循环）

```
Turn 1
  user → LLM → 检查 source data 是否覆盖 user stratum：
                  IF 是 → 走 Path A（CATE，给 EffectQuery 加 given clause）
                  IF 否 → 走 Path B：
                    1. 构造带 SelectionNode 的 program（标记 S-nodes）
                    2. EffectQuery.target_population 写 "user_xxx"
                    3. 不带 P*(Z) 概率参数
                  ↓
                themis.run
                  ↓
              transport 结构识别成功（Phase 9 §T9.1 现有逻辑）
                  ↓
              transport_formula 构造（4.4 新 builder）
                  ↓
              估算 → InsufficientTheta：缺 P*(z) for z ∈ Z.domain
                  ↓
       extensions 列出 missing_keys（带 population="target_xxx" hint）

Turn 2
  LLM 看 missing_keys → 从常识为每个 P*(z) 提议
       构造 patch bundle，每条 ProbabilityStatement 带：
         - population: "target_xxx"
         - provenance: "llm_prior"
         - annotations.source: 一句话理由
                  ↓
              themis.apply_patch_and_run
                  ↓
          numerically_solved
                  ↓
       extensions.transport_identification.numeric ← 含数字
       extensions.llm_proposed_review              ← 含所有 llm_prior 清单

Turn 3 (LLM → 用户)
  reply 强制以 review 表面开头：
  "我用了以下 LLM 常识 prior（请审核）：
    - P*(age=60+) = 0.6（理由：你说你 60 岁）
    - ...
   基于这些假设，Themis 算出在你这种 stratum 上预计副作用率 12%。
   stratum 内个体差异不在此估计。"
```

---

## 5. Skill v3 — LLM 行为协议

`themis/claude_skills/themis-causal-check/SKILL.md` 新增：

### 5.1 Path 选择规则

**优先 Path A**（CATE）：
- 当用户给的协变量在 source 数据已分层 → EffectQuery + given clause
- 不需要 LLM-prior，不需要 transport
- **大部分日常对话场景应走这条**

**Path B**（transport with priors）只在以下条件全满足才走：
1. User 描述了清晰的 target stratum（age / location / 共病 / 职业等）
2. Source 数据该 stratum 缺失或边界外
3. LLM 能合理地为 P*(Z) 提议常识 prior

### 5.2 兜底 propose 规则（Path B）

- **仅当** transport 公式上 `InsufficientTheta` 时才提议
- **不**主动塞 P*(Z) 进第一轮 program
- 每条 prior **必须** 带：
  - `population: "<target_name>"`
  - `provenance: "llm_prior"`
  - `annotations.source`: 非空一句话理由

### 5.3 回答格式强制

第二轮 result 一定带 `extensions.llm_proposed_review`。回答时：

1. **第一段** 必须复述 review 列表
2. **第二段** 必须包含 stratum disclaimer："这是对你所属 stratum 的群体期望，不是个体预测"
3. **第三段** 才说数字

---

## 6. 实施切片

按依赖排序。Fix 3+4 共用基础设施 → 多个切片相互依赖。

| 切片 | 文件 | 内容 | 估时 |
|---|---|---|---|
| **F3.1** | types.py + kernel_ast.schema.json + semantic_validator | `llm_prior` provenance + 强制 source 校验 | 半天 |
| **F4.1** | types.py | `ProbabilityRefExpr.population` 字段 | 5 分钟 |
| **F4.2** | numeric_estimator.py | `ProbabilityKey.population` 字段 + `_probability_ref_key` 读 ProbRef.population + 3 层 fallback population 隔离 | 一天（最高风险） |
| **F4.3** | theta_builder.py | `_key_of` 加 stmt.population；partial-distribution completion 按 (predicate, given, population) 分组 | 半天 |
| **F4.4** | formula_builder.py | 新 `transport_formula` builder：FormulaExpr 输出 `SumExpr(over=Z, body=ProductExpr(P(Y\|do(X),Z, pop=source), P*(Z, pop=target)))` | 半天 |
| **F4.5** | scheduler.py | `_dispatch_transport` 接 theta + 调 builder + `_try_numeric`；填 `extensions.transport_identification.numeric` | 半天 |
| **F34.6** | output/result_orchestrator.py + query_result.schema.json | `extensions.llm_proposed_review` 输出：扫 program statements 收集所有 llm_prior + 已有的 llm cause edges | 半天 |
| **F4.7** | verifier/rules.py | 加 `_rule_transport_numeric_evaluate`（独立 builder + 独立求值 + population 路由）；扩 `_rule_transport_formula` 接 FormulaExpr | 一天 |
| **F4.8** | verifier/serialization.py | ProbabilityKey + ProbabilityRefExpr 序列化加 population；保 backward-compat | 半天 |
| **F34.9** | Skill v3：Path A vs Path B 决策 + 兜底协议 + review-first 输出 | 半天 |
| **F34.10** | tests：单 population (regression) + 兜底循环 transport + paired verifier + Skill fixture | 一天半 |
| **F34.11** | 文档：README 加段落 + MCP README counts 更新 | 1 小时 |
| **合计** | | | **5-6 天** |

---

## 7. 风险点

### 7.1 numeric_estimator 3 层 fallback × population

`_try_derive_via_marginalization` / `_try_marginal_independence_lookup` / `_try_derive_via_bayes_inversion` 当前在 ProbabilityKey 上操作。加 population 后**必须**：

- fallback **只在同 population 内**触发（不允许从 source theta 推 target marginal，反之亦然）
- d-separation 守卫保留
- 性能：population 数量通常很小（1-3 个），不影响

**这是 F4.2 半天的来源 —— 不是"加个字段"那么简单**。

### 7.2 verifier 独立重写 transport

verifier 的 `_rule_transport_numeric_evaluate` 不能调用 `formula_builder.transport_formula` —— 必须独立重建公式（参照 Fix 1 mediation 模板）。这是 paired-implementation 纪律。

### 7.3 review surface 的"完整性"

`llm_proposed_review` 必须扫遍 program.statements 收集**所有** llm-tagged 元素。漏一项 → 用户看不到完整审计面 → Themis 承诺受损。F34.6 需要单测覆盖"加多种 llm_prior + cause llm_proposal 混合，review 全收齐"。

### 7.4 Skill v3 "Path 选择"的判断力

LLM 自己决定走 A 还是 B —— 这是 prompt-shaped 行为，不是 schema-shaped。Skill 必须**给原则不给决策表**（CLAUDE.md 的"教思维方式不要填鸭"）。验收靠 manual / agent fixture 测试，不是单元测试。

---

## 8. 不做（明确边界）

- ❌ 真实 target 数据 ingest（CSV / KB） —— Phase 11.2 (KB) 和 Phase 7 (DataFrame) 路径
- ❌ 多 mediator + transport 联合 —— 先二选一
- ❌ 非 boolean 干预 —— boolean MVP 同 Fix 1
- ❌ 自动检测"该走 Path A 还是 B" —— LLM 自己判断，Skill 给原则
- ❌ Population 在 ResultStatus 维度 —— 用 extensions 信号 + provenance trail
- ❌ 强制 academic 引用 —— common knowledge 通常没引用
- ❌ 区间 prior（Phase 12 bounds 路径）
- ❌ 机会主义提议 —— 仅 InsufficientTheta 触发

---

## 9. 验收

Fix 3+4 实施完成的标志：

1. **基础设施测试**：population-aware ProbabilityKey / Theta / numeric_estimator 单测全过
2. **回归测试**：现有 1979 测试在 population 字段加入后仍然 1979 passed
3. **transport numeric 端到端**：Q1358 类 fixture（source 数据 + target llm_prior → numerically_solved + review surface 完整）
4. **paired verifier**：所有 transport_numeric_evaluate 步骤 verifier 独立重算 1e-9 内一致
5. **真实 MCP 端**：重启 server 后 transport 程序在 MCP 通路上正确返回 numerically_solved
6. **Skill 行为**：subagent 测试在 Path A / Path B 决策上合理；review-first 输出格式遵守

---

## 10. 触发实施的信号

不为完整性提前做。触发条件：

1. **真实跨群体用户场景**：有人用 Themis 问"我朋友的情况"类问题，反复撞 `InsufficientTheta` —— 这是 Fix 3+4 的射程
2. **Phase 1c 大样本 benchmark** 暴露 Themis 在 transport-style 问题上比 vanilla 难用
3. **战略决策**：主动确认 Themis 走"真实世界 LLM agent backbone"路线 —— 这是产品 roadmap 决策

否则 Fix 3+4 留在 charter 状态。

---

## 11. 关联其他 fix / phase

- Gap B (v0.1.3) — `observational` provenance：`llm_prior` 是它的孪生
- A2 — cause-edge provenance：`llm_proposal` source 已有；review surface 把边和概率两者统一
- Fix 1 (v0.1.4) — "kernel 把活干到底" + 四件套模板：F4 完全照搬此模板
- Fix 2A (v0.1.5) — `submit_verdict` 工具：Skill v3 复述 review 后再 submit_verdict（如果问题是 binary）—— 自然组合
- Phase 9 §T9.1 — 结构识别已落地；本 charter 完成 §T9.2 数值评估
- Phase 11.1 `gap_to_action.md` — `propose llm_prior` 是该 prompt 的一个新 action 分支
- Phase 11.2 KB adapter — 未来 `kb_prior` provenance 是 `llm_prior` 的对偶
- Fix 4 charter（原计划独立）—— **取消独立，并入本 charter**

---

## 12. 历史

- 2026-05-23 session：
  - 用户原始问题："127 可以吗" → 讨论 LLM 提 theta
  - 写了独立 `FIX_3_CHARTER_llm_prior.md`（commit 4891cd9）
  - audit 发现 transport 是 Fix-1 同款 gap（`_dispatch_transport` STRUCTURALLY_SOLVED）
  - 设计 Fix 4 时撞上"population-aware kernel"基础设施问题
  - 用户提出"LLM 猜 population + 用户审"洞察 → 重组 Fix 3 + Fix 4 为联合 charter
  - 本 charter 取代原 `FIX_3_CHARTER_llm_prior.md`
