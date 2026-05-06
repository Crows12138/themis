# Case 006 — 孕期吸烟通过胎盘功能影响低出生体重（mediation）

> 第一个 L3-test mediation 路径。同时验 mediation advisory 和
> unmeasured_confounder_risk 在 mediation 场景下的 协同。

## NL question

"孕期吸烟会怎样导致新生儿低出生体重？通过胎盘功能解释多少？"

## Authoritative source

- **Cnattingius S.** "The epidemiology of smoking during pregnancy:
  smoking prevalence, maternal characteristics, and pregnancy
  outcomes." *Nicotine & Tobacco Research* 2004;6 Suppl 2:S125-40.
  PMID: 15203816
- **VanderWeele TJ.** "Mediation analysis: a practitioner's guide."
  *Annu Rev Public Health* 2016;37:17-32. PMID: 26653405
- **Slemenda et al.** earlier observational work establishing
  smoking→placenta→birthweight pathway.

### 核心 quote（mediation 假设要求）

VanderWeele 2016 §4.1：
> Identification of natural direct (NDE) and natural indirect (NIE)
> effects requires four assumptions: (1) no unmeasured confounding
> of the exposure-outcome relationship, (2) no unmeasured confounding
> of the mediator-outcome relationship, (3) no unmeasured confounding
> of the exposure-mediator relationship, and (4) **no mediator-outcome
> confounder affected by the exposure**. The fourth (cross-world)
> assumption is particularly strong and cannot be checked from data.

要点：mediation NDE/NIE 同时依赖四条 ignorability，其中
cross-world 假设 (4) 是最不可验证的。

## Encoded kernel_ast

[`case_006_smoking_birthweight_mediation.json`](case_006_smoking_birthweight_mediation.json)

DAG：
- `smoking_during_pregnancy → placental_dysfunction → low_birthweight`
  (mediation pathway)
- `smoking_during_pregnancy → low_birthweight` (direct effect)
- `ses_low → smoking_during_pregnancy, ses_low → low_birthweight`
  (measured confounder)
- query: effect with mediator field

## Themis 实跑结果

```
status: structurally_solved (与 cases 001-005 不同——mediation 不需 theta 即结构化解)

GAP KINDS:
  - ambiguous_variable_definition × 2 (important)
  - mediation_identification_assumption_required × 2 (informational, NDE/NIE + CDE)
  - unmeasured_confounder_risk (informational)

extensions.mediation_decomposition:
  mediator_valid: True
  nde_nie.identifiable: True
  cde.identifiable: True
```

## 评估：✅ match + 双 advisory 协同

### Themis 命中 ✅

- 正确识别 mediation 结构（NDE/NIE 和 CDE 双双 identifiable）
- mediator_valid: True
- 两条 mediation_identification_assumption_required（每个 branch 一条）
- 同时 fire `unmeasured_confounder_risk`（因为 ses_low 是 measured
  confounder + 没声明 bidirected）

### 双 advisory 协同（不冗余）

两条 advisory 处理的不是同一假设：
- `mediation_identification_assumption_required`: 关于 M-Y 的
  cross-world ignorability（VanderWeele 2016 假设 1-4）
- `unmeasured_confounder_risk`: 关于 X-Y 的整体 confounder coverage

VanderWeele 2016 假设 1（"no unmeasured confounding of
exposure-outcome"）正是 unmeasured_confounder_risk 在 surface 的事
—— 但 mediation advisory 描述 quoted 出来的是 4 条整体，不分
解。Themis 用两条 advisory 把这条 collateral 责任分给 user 时拆得
更细：mediation 假设给 mediation 细节，整体 confounder coverage
给 generic advisory。

cnattingius 2004 + VanderWeele 都明确：smoking-birthweight 观察
研究的 unmeasured 混杂主要是 nutrition / alcohol / stress / prenatal
care，这正是 unmeasured_confounder_risk 想 prompt 的方向。

### 副观察

mediation queries 走 `structurally_solved` 而非 `needs_investigation`
—— 这就是 iter 11 audit 时确认的"mediation extensions 在 status
完成时已被 populate"模式。L3 case 006 实测验证 audit 结论。

## 历史

- 2026-05-07 iter 14：编码 + 跑 ✅ match。第一个 L3-tested mediation
  路径。验证 mediation advisory + unmeasured_confounder_risk 双协同
  正确，无冗余。也跨域验 iter 11 audit 结论（mediation extensions
  在 structurally_solved 时正常 populate）。
