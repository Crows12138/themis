# Phase 10 Charter — DataGapReport（数据缺口诊断器）

> 立项日期：2026-04-26
> 状态：**✅ 已落地（2026-04-26）** — S.10.1-S.10.7 全部完成；详见
> [`CORE_STATUS.md`](CORE_STATUS.md) "Phase 10 数据缺口诊断器" 节。
> 后续 L3 simulation 工作（2026-05-07，10 cases + 2 真 bug 修 + 1 新
> gap_kind `unmeasured_confounder_risk` 完整 lifecycle + 1 新 gap_kind
> `unattempted_layer_due_to_dispatch_conflict`）在此 charter 基础上扩展。
> 对应 VISION：定位收紧 (2026-04-26) — Themis = 验证器 + 数据缺口诊断器
> 触发：2026-04-26 战略对齐——量化因果数据缺乏是学科天花板，"告诉
> 用户去收什么数据"是 DoWhy/EconML/ChatGPT 都不做的独占生态位

## 0. 本 charter 结构

把 VISION "推进问题"原则（一直在但隐式）升格为**一等输出 (2)**。
不动 kernel 现有识别 / 估计 / 验证路径，**只在末端加一个综合层**：
扫描 derivation + ambiguity + investigation_request + identifiability
失败原因，合成结构化的 `data_gap_report` 字段。

这不是新算法 fragment，是**输出层重构**。不需要解冻 kernel 核心
（identifier / verifier 不动），但**需要扩展 query_result schema**。

---

## 1. 动机

### 1.1 真实压力

- W0 case (跑步×腰围)：能给数字 0.55，但是源人群 35-50 男 vs 用户
  28 女。Phase 9 §T9.1 已经标出"transport 缺口"，但**只在 derivation
  里能看到**，渲染层没有结构化总结。
- case 28：用户问"我每天熬夜会变笨吗"，Themis 现在的回答是"需要
  P(cognition_decline | do(stay_up=true))"——**用户看不出来这是个什
  么样的数据需求**（要 RCT？要 cohort？n 多少？什么人群？）。
- 通用：Themis 当前的 `investigation_requests[]` 只说"缺这个参数"，
  不说"**为什么缺**、**怎么收**、**收了能精确到什么程度**"。

### 1.2 对比检查

| 工具 | 数据缺口报告 |
|---|---|
| DoWhy | ✗（identify 失败时只说"unidentifiable"）|
| EconML | ✗（estimator API，假设数据已就位）|
| pgmpy | ✗ |
| causal-learn | ✗ |
| ChatGPT 裸用 | ✗（会编一个数字）|
| **Themis（目标）**| **✓** |

→ 独占生态位，符合 VISION 定位收紧。

### 1.3 理论基础

不需要新理论 fragment——**所有信息都在现有 derivation 里**，只需
要重新组织：

- identifiability 失败 → derivation 给出"哪条边没 block / 哪个 backdoor
  open"
- 参数缺失 → investigation_request 已经列出 missing distributions
- 转移性失败 → Phase 9 §T9.1 给出 selection_diagram + S-admissibility 判定
- 反事实需要 monotonicity → Phase 5 §C 已经标 needs_assumption
- 中介需要 sequential ignorability → Phase 6.mediation 已经标

DataGapReport 是这些信号的**结构化聚合 + 转换为 actionable 数据需求**。

### 1.4 OSS 现状

无同类。流行病学有 "study design recommendation" 论文（Hernan 2020,
"What If" 第 II 部分），但都是教科书，没有工程实现。

---

## 2. 设计

### 2.1 Schema 扩展

在 `query_result.schema.json` 加新顶层字段（可选）：

```json
"data_gap_report": {
  "type": "object",
  "properties": {
    "summary": {"type": "string"},
    "gaps": {
      "type": "array",
      "items": {"$ref": "#/$defs/dataGap"}
    },
    "actionable_next_steps": {
      "type": "array",
      "items": {"type": "string"}
    }
  }
}
```

`dataGap` $def：

```json
{
  "kind": {
    "enum": [
      "unidentifiable_no_admissible_set",
      "missing_distribution",
      "missing_population_distribution",
      "missing_assumption",
      "missing_iv_candidate",
      "missing_mediator_data",
      "transport_target_distribution_unknown",
      "ambiguous_variable_definition"
    ],
    "type": "string"
  },
  "signature": {
    "type": "string",
    "description": "for missing_distribution: 'marginal' | 'conditional' | 'joint'; otherwise omitted"
  },
  "severity": {
    "enum": ["blocking", "important", "informational"],
    "description": "blocking = downstream output cannot be produced; important = output produced but quality reduced; informational = caveat only"
  },
  "description": {"type": "string"},
  "required_data": {
    "type": "object",
    "properties": {
      "data_type": {"enum": ["ipd", "marginal", "rct", "cohort", "case_control", "expert_judgment"]},
      "population": {"type": "string"},
      "variables": {"type": "array", "items": {"type": "string"}},
      "min_sample_size": {"type": "integer"},
      "precision_target": {"type": "string"}
    }
  },
  "blocks": {
    "description": "this gap blocks which downstream output",
    "enum": ["point_estimate", "bounds", "identification", "transport"]
  },
  "if_provided": {
    "type": "string",
    "description": "what becomes possible if this gap is filled"
  },
  "alternative_paths": {
    "type": "array",
    "items": {"type": "string"},
    "description": "alternative ways to make progress without this exact data"
  },
  "provenance": {
    "type": "array",
    "items": {
      "type": "object",
      "properties": {
        "ref_kind": {"enum": ["derivation_step", "investigation_request", "framing_note", "verifier_check"]},
        "ref_id": {"type": "string"}
      },
      "required": ["ref_kind", "ref_id"]
    },
    "description": "one gap may be triggered by multiple signals; array allows multi-source attribution"
  }
}
```

`gaps` 数组在生成时**按 severity 排序**（blocking → important → informational），同 severity 内按 derivation 顺序。

**对 derivation step schema 的硬约束**：每个 derivation step 必须有 `success: bool` 字段（默认 true）。`*_failed` 类 step 必须 `success=false`。这是 T10-2 完整性检查的依赖前提——没有 success 字段就没有"失败信号"可遍历。

### 2.2 Generator

新模块 `themis/output/data_gap_report.py`，纯函数：

```python
def compute_data_gap_report(
    query: Query,
    derivation: tuple[DerivationStep, ...],
    investigation_requests: tuple[InvestigationRequest, ...],
    framing_notes: tuple[FramingNote, ...],
    extensions: dict,  # carries transport_identification, mediation_block, etc.
) -> DataGapReport
```

逻辑分支（每条对应一个 gap_kind）：

1. **`unidentifiable_no_admissible_set`**（blocking）：扫 derivation 找
   `backdoor_failed` / `frontdoor_failed` / `iv_invalid` / `id_algorithm_failed`
   （以 `success=false` 标记），提取 blocking edge 列表 → 建议"加 unmeasured
   covariate Z 或换 design"
2. **`missing_distribution`**（blocking）：从 investigation_request 的
   parameter_missing 项映射；`signature` 字段标 `marginal` / `conditional` /
   `joint`；提示需要的数据类型（IPD vs marginal）
3. **`missing_population_distribution`**（blocking）：从 transport_identification
   block 提取 P*(Z) 缺失，建议"目标人群 P*(Z) 通过 census / cohort 估"
4. **`missing_assumption`**（important）：从 needs_assumption 标记提取
   （monotonicity / sequential ignorability）→ 提示"需要专家断言或
   敏感性分析"
5. **`missing_iv_candidate`**（important）：identify 路径试过 IV 但没找到 valid
   工具变量 → 提示"找一个满足 relevance + exclusion + exchangeability 的 Z"
6. **`missing_mediator_data`**（blocking）：mediation 路径需要 P(M|X) 但缺 → 提示
7. **`transport_target_distribution_unknown`**（blocking）：T9.1 给了 formula 但
   P*(Z) 没数 → 提示具体 Z 列表
8. **`ambiguous_variable_definition`**（informational）：framing_notes 里
   define_variable 项 → 提示"先操作化定义 X 的 measurement / time_window"

**注**：8 条不是固定上限。新板块（板块 8 测量误差 / 板块 4 g-methods /
L3b 嵌套反事实）上线时随之扩展 gap_kind enum。

### 2.3 在 dispatch 后挂载

`themis/output/result_orchestrator.py` 的 `to_dict` 之前调用
`compute_data_gap_report`，结果挂到 `QueryResult.data_gap_report`。

向后兼容：如果是 `cause` / `assoc` 这种本身没数据需求的 query，
report 为 `None` 或 empty `gaps=[]` + summary="no data needed"。

### 2.4 verifier 独立审

新规则 `T10` 系列：

- **T10-1 `data_gap_provenance_check`**：每个 gap 的 `provenance[]` 数组
  里每个 ref 都必须指向真实存在的 derivation_step / investigation_request /
  framing_note / verifier_check。
- **T10-2 `data_gap_completeness_check`**：遍历 derivation 中所有
  `success=false` 的 step，必须在 report 中找到对应 gap；遍历
  investigation_request 中所有 missing parameter，必须在 report 中找到
  对应 gap；遍历 framing_note 中所有 define_variable 项，同上。
- **T10-3 `no_phantom_gaps`**：report 里每个 gap 的 provenance 必须能映射
  回真实信号，不能凭空捏造。

**独立性硬约束**：T10 rule 文件**禁止 import** `themis.output.data_gap_report`
或任何 generator 内部模块。byte-code scan 在测试中 pin 此约束（沿用
V0-V5 同款 forbidden imports check）。

### 2.5 渲染层

`themis/prompts/response_rendering.md` 加新节 "Data gap report rendering"：

中文模板按 gap_kind 分支：

```
[unidentifiable_no_admissible_set]
"在你给的图上，{X}→{Y} 不可识别——{blocking_path} 这条后门没 block。
要算这个效应，需要：(a) 测量 {Z} 把它加进 adjust set，或 (b) 在 {Z} 上
随机化（RCT），或 (c) 找一个满足 IV 条件的 {W}。"

[missing_population_distribution]
"结构上可识别（公式：P*(y|do(x)) = Σ_z P(y|do(x),z) · P*(z)），但缺
目标人群在 {Z=age, sex, BMI} 上的分布 P*(Z)。建议：查 NHANES /
UK Biobank / 中国 CDC 报表对应的人口学统计。"

[missing_assumption]
"识别需要 {assumption}（{说人话的解释}）。如不接受，可改用
{alternative}（如 Balke-Pearl bounds），代价是只给区间不给点估计。"
```

---

## 3. Sub-slices

| Slice | 内容 | 估时 |
|---|---|---|
| **S.10.1 schema** | `query_result.schema.json` 加 `data_gap_report` + `dataGap` $def + derivation step `success` 字段 | 1 天 |
| **S.10.2 types** | `types.py` 加 `DataGap` / `DataGapReport` dataclass；derivation step 加 success；result_orchestrator 挂载点 | 1 天 |
| **S.10.3 generator** | `themis/output/data_gap_report.py` 8 条 gap_kind 分支 + severity 排序 + dispatch 后挂载 | 4 天 |
| **S.10.4 verifier** | T10-1 / T10-2 / T10-3 三条独立审 + byte-code import pin | 1 天 |
| **S.10.5 eval** | 5 个 case 各对应一个主 gap_kind（unidentifiable / transport / iv / mediator / ambiguous）| 1 天 |
| **S.10.6 prompt** | response_rendering 加 data gap 渲染模板（8 条分支 + severity 排序 + 多 gap 共存措辞）| 1.5 天 |
| **S.10.7 docs** | VISION / CORE_STATUS / COVERAGE_MAP / failure_modes 同步 | 半天 |

**总计 ~9-11 个工作日**（charter 标准 1.5-2 周内，留有 buffer）

---

## 4. 显式 Out-of-scope

- **任何 I/O / API 调用** — DataGapReport generator 是**纯 reasoning over
  现有 derivation 的合成**，不联网、不查 KB、不 ping 外部服务、不读
  外部数据集。需要外部数据源是 Phase 11 的事，绝对禁止"顺手查一下
  PrimeKG 看 P*(Z) 在不在"这种偷渡。
- **样本量精确计算（statistical power）** — 需要 effect size 假设和具体
  分布。`required_data.min_sample_size` 字段允许填，但 generator 自己**不算**，
  只在有外部信号（如 transport block 的 effect size hint）时透传
- **数据收集成本-效益分析** — 业务/伦理范畴，超出 Themis 推理职责
- **自动 KB 查询填补 gap** — Phase 11 KB 接入做的事
- **Bayesian elicitation of priors** — 独立学科
- **可视化（DAG with red gap edges）** — 渲染层的事，按需加
- **多语言渲染** — 渲染层只出中文模板（沿用 response_rendering 现状）

---

## 5. 完成标志

- S.10.1 - S.10.7 全部测试通过
- 现有 28 cases + case 29 在新 schema 下结果不变（向后兼容），且
  对相关 case 自动产生 data_gap_report
- W0 case 重新跑：除了原 transport_identification block，**新增结构化
  data_gap_report**，summary 一句话说清"缺 P*(age, sex, bmi) 在用户
  人群"
- VISION 定位收紧的两段式输出契约**真正落地**——任何 effect/identify
  query 都能产生 (1) full check + (2) actionable gap report

## 6. 验收

- 全部独立 verifier 通过
- ~1030 baseline tests 不降级
- 新增 ~15-20 测试覆盖 S.10.* 各 slice
- 9 条 gap_kind 在 eval set 内全部至少触发一次

## 7. 不做的（永远）

- 把 DataGapReport 做成"诊断后自动尝试补 gap" — 那是另一层 agent loop，
  不在 reasoning kernel 职责
- 替用户决定"该收哪个数据" — 只列选项 + 后果，决定权留给用户
- 经济学/医学/物理学的领域特定 gap 模板 — 保持通用

---

## Review checklist（请 Reviewer 答）

1. ☐ Scope 是否合适？9 条 gap_kind 是否够覆盖现有 query 类型的失败模式？
2. ☐ Schema 改动是否最小？`data_gap_report` 作为可选顶层字段是否合理，
   还是应该塞进 `extensions`？
3. ☐ 估时 7-8 天是否合理？generator 3 天会不会低估？
4. ☐ verifier T10 三条是否够独立？还是 generator 和 verifier 会共享
   太多代码导致独立性破坏？
5. ☐ 渲染模板放在 response_rendering.md 还是新文件 `data_gap_rendering.md`？
6. ☐ 命名：`data_gap_report` / `gaps` / `gap_kind` — 或换成
   `validation_report` / `findings` / `finding_kind`？
7. ☐ 8 条 gap_kind 中是否有应该合并 / 拆分的？
8. ☐ Out-of-scope 列表是否够明确？

## Self-review 已应用的修订（2026-04-26）

1. gap_kind 9 → 8：合并 `missing_marginal_distribution` +
   `missing_conditional_distribution` 为 `missing_distribution` + `signature` 子字段
2. 估时 7-8 → 9-11 天：S.10.3 generator 3 → 4 天；S.10.6 prompt 1 → 1.5 天
3. T10 加 byte-code import pin（禁止 import generator 模块）
4. provenance: object → array（一个 gap 可由多信号触发）
5. 加 `severity: blocking | important | informational` 字段 + 按 severity 排序
6. derivation step schema 加 `success: bool` 硬约束（T10-2 完整性检查依赖）
7. Out-of-scope 加"禁止任何 I/O / API 调用"硬约束
8. 删除 §10.b sample size 跟进 promise（不预约，等真实压力）
