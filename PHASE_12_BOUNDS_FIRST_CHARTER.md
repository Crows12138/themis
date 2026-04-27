# Phase 12 Charter — Bounds-first Output

> 立项日期：2026-04-27
> 状态：**S.12.1-6 全部已落地（同日）**；commits 88653eb / aa1b577 /
> b208897 / 4342808。
> 触发：Phase 10 落地后 9 个 gap_kind 里 5 个的 `alternative_paths`
> 写"接受 Balke-Pearl bounds"——但 kernel 算不出 bounds，是空头承诺。
> Phase 12 把它兑现。
> 对应 VISION：验证器对"能给什么"的承诺，缺口诊断器的兜底输出。

---

## 0. 一句话

**当点估计不可识别 / 数据不够 / 假设不肯接受时，Themis 不该沉默 ——
应该说"点不能给，但区间是 [a, b]"**。

这是验证器定位的自然延伸：能验证 + 能诊断缺口 + **能给信息保留的兜
底答案**。

## 1. 现状（问题）

数据缺口报告里 9 个 gap_kind 的 `alternative_paths`：

| gap_kind | alternative_paths 写了 bounds？ | kernel 实际能算？ |
|---|---|---|
| `unidentifiable_no_admissible_set` | "或接受 bounds" | ❌ 不能 |
| `missing_distribution` | "接受 Balke-Pearl bounds 给区间答案" | ❌ 不能 |
| `missing_assumption` | "接受 bounds 而非点估计 (Balke-Pearl / Manski)" | ❌ 不能 |
| `missing_iv_candidate` | "Balke-Pearl bounds 仅在有 IV 时才更窄" | ❌ 不能 |
| `transport_*` | "接受源人群 ATE 作为粗略估计 / 等待 sensitivity 给区间" | ❌ 不能 |

5 个 gap_kind 在告诉用户"用 bounds 兜底"，但 Themis 没有 bounds 计算
路径。用户按指引去做，回头发现 kernel 给不出。**承诺 vs 交付的 gap**。

## 2. 范围

### 2.1 必须做（symbolic 层 — 纯 validator）

**目标**：当 `themis.run` 检测到点不可识别 / 缺关键数据时，自动尝试
计算 symbolic bounds 表达式，attach 到 result envelope。

```
themis.run → effect query
  ↓
identify pass: 点可识别？
  ├─ 是 → numeric_result / numeric_estimate（现有路径）
  └─ 否 → bounds_attempt(query, graph, observable_data_signature)
            ├─ Manski 总是可算（无假设）
            ├─ Balke-Pearl 仅 binary IV 时
            ├─ Frontdoor partial 仅 mediator 部分可观测时
            └─ 输出 BoundsResult: {method, lower_expr, upper_expr,
                                    assumptions, data_required}
```

**bounds_result 落在 result.bounds_result（新字段）**，不是
`numeric_result` —— 这是 validator 的不同输出 channel：
- 不需要 DataFrame
- 表达式 + 计算条件，让客户端知道"如果有 P(X)/P(Y)/IV strength
  这些数据，能填出区间 [a, b]"

### 2.2 应该做（numeric 层）

`themis.estimate(program, df)` 的 fallback：当现有 estimator 失败
（identification 不通），调 `bounds_estimator` 给具体数值区间。

延后做，等 §2.1 落地后看真实压力。

### 2.3 不做（永远）

- 自动从外部 KB / 文献拉数据来填 bounds 公式（外部数据不是 Themis 的事，
  详 `project_kb_adapter_invariants.md`）
- 真接入第三方 bounds 库（DoWhy / EconML 都没单独的 bounds 模块；自家写）
- 假装 bounds 比真实窄（uninformative bounds [−1, 1] 必须老实输出，
  不能为了"看起来有用"做手脚）

## 3. 方法选择（symbolic 层）

按优先级：

| 方法 | 触发条件 | 假设 | 输出 |
|---|---|---|---|
| **Manski natural bounds** | 任何 binary outcome effect query | 无 | [−P(X=0), P(X=1)] 或类似（risk difference 自然界限） |
| **Balke-Pearl IV bounds** | 有 binary IV + binary X + binary Y | IV1/IV2/IV3 | 比 Manski 窄；公式 Pearl 1995 §3 |
| **Frontdoor partial bounds** | mediator 部分可观测 | front-door 假设 | Pearl 2009 §3.3 |
| Manski-Tamer monotonicity bounds | + 用户接受 monotonicity 假设 | + monotonicity | 比 Manski 窄 |

**S.12.1-S.12.3 仅做前两个**（Manski + Balke-Pearl）。Frontdoor partial
等到真实压力。

## 4. Sub-slices

| Sub | 内容 | 估时 |
|---|---|---|
| **S.12.1** | types: `BoundsResult` 数据类 + `BoundsMethod` enum + JSON schema 字段；T10 verifier 加 bounds 一致性规则 | 4h |
| **S.12.2** | `themis/output/bounds.py`: Manski natural bounds (binary outcome effect queries) | 6h |
| **S.12.3** | Balke-Pearl IV bounds（要求 `extensions.iv_identification` present） | 6h |
| **S.12.4** | scheduler.py / kernel.py wiring：identify 失败时调用 bounds_attempt，attach BoundsResult；alternative_paths 文案改为"已计算 bounds: [a, b]"形式 | 4h |
| **S.12.5** | response_rendering.md 加 §"Bounds rendering"：解释方法、信息保留意义、如果太宽要如何缩窄 | 2h |
| **S.12.6** | subagent 真测：构造一组 unidentifiable + missing_distribution + IV 三类 query，验证 BoundsResult 输出可被 LLM 正确呈现 | 2h |

总 ~24h 净时间。可拆 3 批 commit（S.12.1-2 / S.12.3-4 / S.12.5-6）。

## 5. 验收

### 必须
- 1286 baseline tests 不降级
- ~50 新测试覆盖 Manski + Balke-Pearl symbolic + verifier
- 至少一个 e2e：unidentifiable_no_admissible_set 触发 + Manski bounds
  attach + response_rendering 正确呈现
- subagent 真测无回归

### 应该
- `alternative_paths` 文案从"接受 Balke-Pearl bounds"升级为"已计算
  bounds: [...]"或"bounds 不可用，因为 ..."
- VISION.md / CORE_STATUS.md 同步 bounds-first 兑现状态

## 6. 显式 out-of-scope

- 数值 bounds estimator（§2.2 延后）
- Frontdoor partial / Manski-Tamer 等更复杂方法
- bounds 与现有 `numeric_estimate` 的混合输出（当点能算时也给 bounds 作 sanity）
- bounds 的 sensitivity analysis
- 任何 KB / 外部数据 / adapter 相关（与 Phase 11 已划清相同的边界）

## 7. Review checklist（用户答）

1. ☐ symbolic-only 这一轮 OK 吗？还是同步做 numeric estimator？
2. ☐ Manski + Balke-Pearl 两个方法够吗？还是要加 Frontdoor partial？
3. ☐ `BoundsResult` 是新顶层字段还是塞进 `numeric_result`？我倾向新字段（语义不同 — bounds 是 validator 输出，不是估计层）
4. ☐ 6 个 sub-slice 粒度合适吗？
5. ☐ 不同意 §2.3 "永远不做" 里的某条吗？
