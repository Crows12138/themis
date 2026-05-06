# Case 002 — Vitamin D supplementation 对 CVD 的因果效应

> 又一个经典 RCT-vs-observational 反转 case，Themis 应不应该 surface
> unmeasured confounder risk？

## NL question

"补充维生素 D 能不能降低心血管疾病风险？"

## Authoritative source

- **Manson JE et al. (VITAL Trial)** "Vitamin D Supplements and Prevention
  of Cancer and Cardiovascular Disease." *NEJM*
  2019;380(1):33-44. PMID: 30415629
- **Cochrane Review** "Vitamin D supplementation for prevention of
  cardiovascular disease." Bjelakovic et al. 2014.
- **VITAL ancillary**: Multiple ancillary papers showing null effect on
  cardiovascular events (Buring et al. follow-up)

### 核心 quote（数据限制）

VITAL trial 直接 quote (Manson 2019):
> Supplementation with vitamin D did not result in a lower incidence of
> invasive cancer or cardiovascular events than placebo.

观察性研究系统综述发现：

> Observational studies consistently report inverse association between
> circulating 25(OH)D and CVD risk, but **randomized trials of vitamin D
> supplementation have failed to confirm a causal benefit**, indicating
> the observational association is likely driven by **confounding by
> overall health, sun exposure (correlated with outdoor activity), and
> reverse causation** (sicker people have lower 25(OH)D).

Same lesson 模式 as HRT-CVD: 即使调整可测的 confounders，
unmeasured confounders（lifestyle factors, sun exposure 等）仍主导
观察性结论。

## Encoded kernel_ast

[`case_002_vitamin_d_cvd.json`](case_002_vitamin_d_cvd.json)

DAG：
- `vitamin_d_supplementation → cvd_event`
- measured confounders: `age`, `exercise`（→ both supplementation and CVD）
- 同 case 001：用户**没有**编码 unmeasured `lifestyle_health` / bidirected edge

## Themis 实跑结果（摘录）

```
status: needs_investigation
explanation: ⚠ 答案是 manski_natural 给出的符号区间，不是点估计

data_gap_report:
  - missing_distribution (blocking): P(cvd_event|age, exercise, vitamin_d)
  - ambiguous_variable_definition × 2 (important)
  - answer_is_bounds_not_point_estimate (informational)

bounds: manski_natural
framing_notes: 2
```

**与 case 001 完全相同的 gap_kind 集合**——确认 miss 是系统性，不是
case 001 特有。

## 评估：◐ partial match（与 case 001 相同模式）

### Themis 命中 ✅

- backdoor 结构识别（{age, exercise} 是 admissible adjustment set）
- missing_distribution gap surface
- Manski natural bounds fallback
- variable framing gaps × 2
- bounds-not-point-estimate caveat

### Themis 错过 ❌（与 case 001 完全相同）

**Confirmed systematic miss**：Themis 在 backdoor-identifiable +
all-directed-edges 场景下，**完全不 surface 任何 unmeasured-confounder
风险 advisory**。无论域是 HRT (case 001) 或 vitamin D (case 002)，
miss 一致。

VITAL trial / Cochrane 2014 都明确归因于 unmeasured confounding +
reverse causation。Themis 的 data_gap_report 一字未提"你 DAG 可能
不完整"。

## L3 finding 强化

N=2，跨 case 一致 → 提议的新 gap_kind `unmeasured_confounder_risk` 不
是 case-specific 噪音，是真实的系统性 diagnostic gap。

**iter 5+ 推进路径**：

1. 优先实现 `unmeasured_confounder_risk`（types.py + data_gap_report.py
   + schema + 测试）
2. 触发条件（草案）：
   - query is `effect` (or numeric `probability`)
   - identification 通过 backdoor / front-door / Tian (success step)
   - graph 有 ≥1 confounder 但**没有 bidirected edges**（用户假设全测了）
   - 所有 confounder edges 是 directed
3. severity: informational（不 block）
4. description 模板：disclose"你的 DAG 隐式假设所有 confounder 已测
   完整。历史上 well-documented domain（HRT, vitamin D, breastfeeding-IQ
   等）显示这个假设常被 unmeasured lifestyle / health behavior 推翻"
5. alternative_paths：E-value sensitivity / RCT triangulation /
   target trial emulation 引导

## 历史

- 2026-05-07 iter 4：case 002 编码 + 跑，确认与 case 001 相同 partial
  miss → 新 gap_kind 立项条件成熟。
- 2026-05-07 iter 5：实现 `unmeasured_confounder_risk`，case 002 重跑
  fire 5 gap_kinds（含新 informational）。✅ match.
