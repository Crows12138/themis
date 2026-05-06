# Case 010 — IPCC：人为 CO2 是否导致全球升温

> 第 10 例（plateau capstone）。换 climate science 域验 cause query 路径 +
> cross-domain advisory robustness。

## NL question

"工业以来人类排放 CO2 是否导致了全球温度升高？"（cause query, 不要数值）

## Authoritative source

- **IPCC AR6 WG1 Summary for Policymakers** (2021), Statement A.1:
  > "It is unequivocal that human influence has warmed the atmosphere,
  > ocean and land. Widespread and rapid changes in the atmosphere,
  > ocean, cryosphere and biosphere have occurred."
- **IPCC AR6 WG1 Ch 3** "Human Influence on the Climate System": 多
  attribution 方法（fingerprint analysis / counterfactual climate
  modeling / observed-vs-natural-forcings comparison）共同支持
  attribution。

### 核心 quote

IPCC AR6 SPM Statement A.1.3:
> "Human influence is very likely the main driver of these changes
> [in the atmosphere, ocean, cryosphere, biosphere]. **Multiple lines
> of evidence — historical observations, paleoclimate reconstructions,
> radiative forcing calculations, and detection-attribution studies —
> converge on this conclusion.**"

要点：因果断言**不靠单一数据源**或单一识别策略，而是 triangulation
across methods。Themis 这种 single-DAG 形式推理只是 attribution
discourse 的**一个 leg**——这是 cause query 在 climate domain 的本
质局限。

## Encoded kernel_ast

[`case_010_co2_temperature_ipcc.json`](case_010_co2_temperature_ipcc.json)

DAG：
- `anthropogenic_co2_high → global_temp_anomaly_high` (target)
- `solar_irradiance_high → global_temp_anomaly_high` (natural forcing)
- `volcanic_aerosols_high → global_temp_anomaly_high` (natural forcing)

query: `kind: cause, from: anthropogenic_co2_high, to: global_temp_anomaly_high`
（boolean cause inquiry, 不是 effect）

## Themis 实跑结果

```
status: structurally_solved
structural_result: {value: True, supporting_paths: [[anthropogenic_co2 → global_temp]]}
GAP KINDS:
  - ambiguous_variable_definition × 2 (important)
EXPLANATION: (none，无 must-disclose)
```

## 评估：✅ match — cause query 干净结构化解答

### Themis 命中 ✅

- cause query 正确 dispatch（不走 effect / mediation / transport 路径）
- structural_result.value=True with supporting_path 显式列出
- 无 missing_distribution（cause 不需 data）
- 无 unmeasured_confounder_risk（query_kind != EFFECT，正确抑制）
- 无 must-disclose advisory（cause query 没有 identification 假设
  paths layer 之类的 caveat）
- ambiguous_variable_definition × 2 提示用户操作化变量定义（一致风格）

### 关于 IPCC 多 lines 的 quote 与 Themis 局限

IPCC 强调 attribution 来自**多 method 三角化**，Themis 这次返回的
"per your DAG, yes" 只是其中一条 structural reasoning leg。其他 leg
（fingerprint analysis / paleoclimate / detection-attribution stats）
都不在 Themis 的 scope 内。

**这不是 Themis bug**——cause query 的本意就是"per user DAG, is X
causally connected to Y"。Themis 不假装是 attribution suite。VISION
段已显式 disclose："Themis 是因果断言的形式验证器 + 数据缺口诊断器，
不是黑盒 attribution platform"。

为 case 010 不需要新 gap_kind 标注 "结论需要 multi-line triangulation
support"——这条放在 cause query 上太通用，对 narrow DAG 都适用。
属于"用户应自知的 epistemological limit"，不是 Themis 该 prompt 的事。

## L3 plateau 达成

case 010 是第 10 例。回望 cases 001-010：
- ✅ 9 个 match（含 cases 004 和 009 经过 partial → fix → match 升级）
- 跨 7 个域：医学 × 5 / 经济学 / 教育 / 流行病 / 环境科学 / Layer 3 推理
- 覆盖全 8 识别路径 + cause query
- 2 个真实代码改动（front-door fallback iter 10；
  unattempted_layer_dispatch_conflict iter 19）+ 1 个新 gap_kind
  全 lifecycle（unmeasured_confounder_risk iter 5-9）

按 docs/l3_simulation/README.md 终止条件：
> ≥10 mined cases 全部通过（match 或 partial-known-gap）→ L3 simulation
> 进入 plateau，回交用户做真人 recruitment

**plateau 已达成**。loop 后续不需要再 mine 新 case，应该转向其他
VISION gaps 或等真人测试 unblock L3 价值层验证。

## 历史

- 2026-05-07 iter 20：编码 + 跑 ✅ match。第 10 例 capstone。L3 corpus
  plateau 达成，wall.md 已更新。
