# Phase 13 Charter — Dose-Response Diagnostic

> 立项日期：2026-04-28
> 状态：**charter draft, 待用户签字**
> 触发：5-subagent 真测 + 用户提问形态归纳显示一类用户痛点 Themis 没正面回答：
> "X 让 Y 增加多少 / 关系图" 这种 dose-response 问题。
> 当前 Themis 把它压成 binary effect 或丢给 ambiguity，没有显式产出
> "要画这条曲线你需要什么"清单。

---

## 0. 一句话

**用户问"加薪和敬业度的关系图"时，Themis 不画图（那是 EconML 的活），
但要给一份完整的"画这条曲线你需要什么数据 + 什么假设"清单**。

这是 validator + data gap diagnostician 在剂量响应问句上的对称补完。

## 1. 现状（问题）

### 1.1 真测证据

**subagent #1 加薪 → 敬业度（连续）**：
- 用户真问：加薪 X 元让敬业度变化多少
- 当前出口：被迫压成 `engagement=true / false`，标 `categorical_compression`
- 缺口：用户拿到 bounds + 数据缺口报告后，不知道**画曲线**还需要什么

**subagent #4 没辍学 → 工资差（连续）**：
- 用户真问：辍学造成工资差**多少**
- 当前出口：counterfactual + 工资压成 binary 高薪/低薪
- 缺口：同上

### 1.2 用户能力分布

按这次会话讨论：医生 / 政策 / 普通研究者占 50%+，**不会自己跑回归**。
即便 DS 工程师也常错把"OLS 系数"当因果效应。

所以 Themis 给"这是 EconML 的活，自己去"——**没接得住的用户面只有 5-15%**。
Phase 13 的诊断输出至少让用户知道**该收什么数据 / 该满足什么假设**，
减少 80% 的"我懂卡在哪儿但不知道怎么开始"。

### 1.3 与 Phase 14 (estimator) 的边界

Phase 13 = 诊断（"要怎么做 + 缺什么"），不调外部库
Phase 14 = 真做（用 EconML 算曲线），调外部库

两件事**分开 charter**。先做 13 让 14 站在诊断之上。

## 2. 范围

### 2.1 必须做（symbolic 诊断层 — 纯 validator）

**目标**：当 NL 是 dose-response 形态时，emit 一个新 gap_kind
`dose_response_data_required`，自带具体到字段的数据清单。

#### 2.1.1 New gap_kind: `DOSE_RESPONSE_DATA_REQUIRED`

```python
class GapKind(str, Enum):
    ...
    DOSE_RESPONSE_DATA_REQUIRED = "dose_response_data_required"
```

**触发条件**（在 `_classify_dose_response_data` 里组合判断）：
- query.kind = effect
- target predicate 是连续型（VariableDeclaration.domain 缺失或长度 ≥ 5）
- intervention predicate 是连续型 OR 用户在 ambiguity 写了
  `dose_response_query`
- AND 用户至少一个 NL 句式触发剂量响应（"多少 / 关系 / 曲线 /
  从...到...变化")

**严重度**: blocking（用户不能跳过这个 gap 拿到曲线）
**blocks**: `point_estimate`（拿不到曲线就没有点估计）

#### 2.1.2 GapRequiredData 扩展

```python
@dataclass(frozen=True)
class GapRequiredData:
    ...  # 现有字段
    sampling_points: tuple[float, ...] | None = None
    """X 的建议采样点（连续 X 时使用），如 (0, 500, 1000, 2000, 5000)"""
    
    sampling_point_count: int | None = None
    """X 至少需要的采样点个数（≥4 推荐）"""
    
    confounders_required: tuple[str, ...] = ()
    """从 DAG 后门集合 / 用户 ambiguity 推出的关键混杂"""
    
    time_window: str | None = None
    """测量时间窗 / 复测频率（如 'baseline + 4w + 12w'）"""
    
    sutva_concerns: tuple[str, ...] = ()
    """SUTVA 违反风险点（员工互相讨论加薪 / 邻里效应等）"""
```

JSON schema 同步扩展（向后兼容，所有字段 optional）。

#### 2.1.3 计算逻辑

`_classify_dose_response_data` 实现：

```python
def _classify_dose_response_data(
    program, query, ambiguities, derivation
) -> Iterable[DataGap]:
    if not _is_dose_response(program, query, ambiguities):
        return
    
    # 1. 采样点数 - 默认 K=5（Hill-Tukey 经验）
    K = 5
    
    # 2. 每点样本量 - Cohen's d=0.5 power calc
    n_per_point, _ = estimate_min_n_two_arm_continuous()
    n_per_arm = n_per_point // 2
    
    # 3. 总样本
    total = K * n_per_arm
    
    # 4. 混杂从 derivation 里的 backdoor 调整集捞
    confounders = _extract_backdoor_set(derivation)
    
    # 5. 时间窗从用户提供的 framing notes 或 default
    time_window = _extract_time_window(program, query) or "建议 baseline + 4w + 12w"
    
    yield DataGap(
        kind=GapKind.DOSE_RESPONSE_DATA_REQUIRED,
        severity=GapSeverity.BLOCKING,
        description=(
            f"用户问的是 {query.target} 与 {query.intervention} 的剂量响应"
            f"关系。Themis 不画曲线（请用 EconML/DoubleML/GAM）但能告诉"
            f"你做这件事需要的数据。"
        ),
        blocks=GapBlocks.POINT_ESTIMATE,
        required_data=GapRequiredData(
            data_type=RequiredDataType.IPD,
            sampling_point_count=K,
            min_sample_size=total,
            precision_target=(
                f"K={K} 个 X 采样点 × n={n_per_arm}/点 (Cohen's d=0.5"
                f", α=0.05, power=0.80)"
            ),
            confounders_required=confounders,
            time_window=time_window,
            sutva_concerns=_default_sutva_for(query),
        ),
        if_provided="可委托外部回归 (EconML / DoubleML / GAM) 拟合曲线",
        alternative_paths=(
            "退一步只看二元对比 (X=high vs X=low)，Themis 给 binary bounds",
        ),
        provenance=...,
    )
```

### 2.2 应该做（prompt 层）

#### 2.2.1 New ambiguity kind: `dose_response_query`

`nl_to_kernel_ast.md` ambiguity catalog 新增：

> `dose_response_query` | NL asks "多少 / 关系 / 从 A 到 B / X 让 Y 增加" — wants the dose-response curve E[Y|do(X=x)] as a function of x. The kernel doesn't compute curves (Phase 14 will via EconML). Emit the closest-fit `effect` query AND flag this ambiguity so the response layer surfaces "I'm a validator, not a regression engine; here's the data spec for fitting the curve elsewhere."

#### 2.2.2 触发短语 + worked example

§5 加：

> **Watch for dose-response phrasings.** "X 让 Y 升 / 降多少 / 多大 /
> 多重 / 关系 / 曲线 / 从 X1 到 X2 时 Y 怎么变" 触发 `dose_response_query`
> ambiguity. Emit a closest-fit binary effect query (e.g. X=high vs
> X=low at sensible thresholds) for Themis to validate; the
> dose_response_data_required gap will list what's needed for the
> curve itself.

### 2.3 应该做（response 渲染）

`response_rendering.md` 加：

- 当 gap 含 `dose_response_data_required` 时，**头条**写"你问的是关系图，
  Themis 不画图——下面是画图所需数据清单"
- 渲染 sampling_points / confounders_required / time_window / sutva_concerns
  各自成段
- 末尾标"画完图请用 EconML / DoubleML / GAM —— Themis 不算曲线"

### 2.4 不做（永远 / 推后到 Phase 14）

- **真画曲线 / 调 EconML / 出数值** — Phase 14 才做
- **CATE / 异质性效应** — Phase 14
- **自动 K 采样点选择**（按 X 范围 / 用户先验自适应）— 没必要
- **多 outcome 同时 dose-response** — 单一 Y 这一版

## 3. Sub-slices

| Sub | 内容 | 估时 |
|---|---|---|
| **S.13.1** | types + schema：GapKind 加 DOSE_RESPONSE_DATA_REQUIRED；GapRequiredData 加 4 个新字段；JSON schema 同步 | 2h |
| **S.13.2** | classifier `_classify_dose_response_data` + `_is_dose_response` 检测 + 默认采样建议 + backdoor 混杂提取 | 3h |
| **S.13.3** | scheduler / data_gap_report orchestrator 接 classifier；新 gap_kind 走分类；alt_paths reconcile 兼容 | 1h |
| **S.13.4** | nl_to_kernel_ast.md：dose_response_query ambiguity 加目录 + 触发短语 + worked example | 1h |
| **S.13.5** | response_rendering.md：渲染规则（清单各段 + "Themis 不算曲线"标语）| 1h |
| **S.13.6** | subagent 真测：subagent #1 / #4 同问题重跑，看是否自然 emit dose_response_query 并接住数据清单 | 1h |

合计 **~9h 净时间**，约 1 天。可拆 2 批 commit：S.13.1-3 / S.13.4-6。

## 4. 验收

### 必须

- 1363 baseline tests 不降级
- ~25 新测试覆盖 classifier + schema + e2e
- subagent 真测：跑 "加薪能让敬业度升多少" 出来的 data_gap_report
  含 `dose_response_data_required`，required_data 的 5 个新字段都填了

### 应该

- VISION.md / CORE_STATUS.md 同步：剂量响应**诊断**到位，**估计**留给 Phase 14
- 改进效果可量化：subagent #1 元评估的"被迫 binary 化"应该消失或转为
  "用 binary 当退路"

## 5. 显式 out-of-scope

- 调 EconML / 任何外部估计库（Phase 14 才做）
- 自动从 X 范围拟合采样点
- 多变量 dose-response 联合
- 时序 dose-response（time-indexed）
- counterfactual dose-response

## 6. Review checklist（用户答）

1. ☐ 新 gap_kind 命名 `DOSE_RESPONSE_DATA_REQUIRED` 是否合适？或者
   `dose_response_data_spec`?
2. ☐ 默认 K=5 采样点合不合理？这是 Hill-Tukey 经验法则，要不要让用户
   能在 program 里 override？
3. ☐ §2.1.2 GapRequiredData 加 4 个新字段（sampling_points,
   sampling_point_count, confounders_required, time_window,
   sutva_concerns）是否过设计？或者一个 freeform `notes` 就够？
4. ☐ S.13.6 真测一次够不够？要不要并行跑 3 个 subagent 覆盖不同
   dose-response 形态（连续→连续 / 连续→Likert / 连续→binary）？
5. ☐ §2.4 "永远不做"里的某条想松吗？
