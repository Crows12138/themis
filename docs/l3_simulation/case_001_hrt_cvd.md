# Case 001 — HRT 对绝经后女性心血管病 (CVD) 的因果效应

> 因果推理史上最经典的 RCT-vs-观察性 discrepancy。Themis 数据缺口诊断
> 在这个场景下应该 surface 什么？

## NL question

"绝经后女性长期使用激素替代疗法 (HRT) 能不能降低心血管疾病风险？"

## Authoritative source（外部 ground truth）

- **Manson JE et al.** "Menopausal Hormone Therapy and Health Outcomes
  During the Intervention and Extended Poststopping Phases of the
  Women's Health Initiative Randomized Trials." *JAMA*
  2013;310(13):1353-1368. PMID: 24084921
- **Hernán MA et al.** "Observational studies analyzed like randomized
  experiments: an application to postmenopausal hormones and coronary
  heart disease." *Epidemiology* 2008;19(6):766-779. PMID: 18854698
- **Rossouw JE et al.** (WHI 2002 NEJM landmark RCT)

### 核心 quote（数据限制）

Hernán 2008 §"Why observational studies failed":

> The discrepancy between the WHI trial and earlier observational
> studies has been attributed to **uncontrolled confounding by healthy
> behaviors** (e.g., women who chose HRT also exercised more, had
> better diets, sought more medical care) **and to differences in the
> timing of HRT initiation relative to menopause**. Even careful
> adjustment for measured covariates (age, BMI, smoking, prior CVD)
> failed to recover the WHI estimate; the bias from unmeasured
> "healthy user" effect was substantial.

要点：
1. **Unmeasured confounding** (healthy user bias) — 即便调整了所有可测
   变量，未测量的健康行为仍引入实质偏差
2. **Effect modification by timing of initiation** — 接近绝经开始 HRT
   可能保护，绝经多年后开始可能有害
3. **Solution**: Hernán 2008 用 target trial emulation + per-protocol
   analysis 在更严格的 eligibility 下重做观察性，结论才与 WHI 对齐

## Encoded kernel_ast

文件：[`case_001_hrt_cvd.json`](case_001_hrt_cvd.json)

DAG：
- `hrt_use → cvd_event`（目标因果边）
- `age → hrt_use, age → cvd_event`（measured confounder）
- `baseline_health → hrt_use, baseline_health → cvd_event`（measured
  confounder）
- 注意：用户**没有**编码 unmeasured `healthy_lifestyle` 节点 / bidirected
  edge —— 模拟一个真实用户相信"我把所有混杂都测了"的常见误区

## Themis 实跑结果

```bash
python -c "
import json
from themis import run
with open('docs/l3_simulation/case_001_hrt_cvd.json') as f:
    program = json.load(f)
print(json.dumps(run(program), ensure_ascii=False, indent=2, default=str))
"
```

### 关键 output 摘录

```
status: needs_investigation
formula: ΣᶻP(cvd_event|hrt_use, age=z₁, baseline_health=z₂) · P(age=z₁) · P(baseline_health=z₂|age=z₁)
missing_information: parameter:P(cvd_event=True|age=True,baseline_health=True,hrt_use=True)
explanation: ⚠ 答案是 manski_natural 给出的符号区间，不是点估计

data_gap_report:
  - missing_distribution (blocking, point_estimate)
    → 补 P(...) 后可给点估计
  - ambiguous_variable_definition × 2 (cvd_event / hrt_use 缺 7 个 framing 字段)
  - answer_is_bounds_not_point_estimate (informational)

bounds_result: manski_natural [P(cvd|hrt)·P(hrt), P(cvd|hrt)·P(hrt)+P(¬hrt)]
```

## 评估：◐ partial match

### Themis 命中 ✅

- 正确识别 backdoor structure，构造完整 adjustment formula on {age,
  baseline_health}
- 正确报告 missing distribution P(...)（要求 IPD，min n=400）
- 正确 fallback 到 Manski bounds 作 alternative path
- 正确 surface variable framing 缺口（cvd_event / hrt_use 操作化定义
  缺 7 个字段）
- ⚠ caveat "答案是 bounds 不是点估计" 已在 explanation 第一行 surface

### Themis 错过 ❌

**关键 miss**：Themis 没有 surface "**即使调整了 age + baseline_health，
仍可能存在 unmeasured confounder（healthy user bias）**"——这是 HRT-CVD
案例最重要的历史教训，也是 Hernán 2008 全文的核心论点。

具体观察：
- `data_gap_report` 没有 `unmeasured_confounder_risk` 这个 gap_kind
  （目前 8 个 gap_kind 全是 missing_distribution / ambiguous /
  bounds 类，没有 "你的 DAG 可能漏了潜变量" 这种 advisory）
- 用户编码 DAG 时没声明任何 bidirected edge → Themis 信任 DAG 完整性
  → 不主动质疑
- 没有任何 advisory 提示"在收集数据前考虑哪些 unmeasured confounder
  可能威胁有效性"
- E-value sensitivity analysis 只在 numeric estimate 阶段附（Phase 8.2），
  structural-only 阶段不会主动 prompt 用户考虑

**次要 miss**（域内专家会指出，但严格说不在 Themis 当前 scope）：
- Timing-of-initiation effect modification（需要用户编码 effect
  modifier，kernel 信任用户 DAG）
- 域 specific 历史教训（"HRT-CVD 历史上有大 RCT-obs discrepancy"）
  ——这是 KB 范畴，不是 kernel
- Hernán 2008 推荐的 target trial emulation framework

## Action

为 iter 4+ 立的 actionable improvement：

> **新 gap_kind 候选：`unmeasured_confounder_risk`**
>
> 当 query 是 effect / probability，user-provided DAG 的 confounder
> 全是 directed（无 bidirected），且 query 落到 backdoor
> structurally_solved 时，data_gap_report 应自动追加一条
> informational 级 gap：
>
> - kind: `unmeasured_confounder_risk`
> - severity: informational（不 block 出数）
> - description: "User-provided DAG 假设所有 confounder 已观测且无遗漏。
>   现实中 unmeasured confounder（典型如 healthy user bias / lifestyle
>   factors）经常导致观察性研究 vs RCT 大幅 discrepancy。建议在拿到
>   数据后跑 sensitivity analysis (E-value) 量化稳健性。"
> - alternative_paths: ["E-value sensitivity analysis（拿到数据后）",
>   "Triangulation：寻找 RCT / quasi-experimental 数据"]
>
> 这是 Themis "数据缺口诊断器" 定位的延伸 —— 缺的不只是数据本身，
> 还有"你 DAG 可能不完整"这种 meta-data 缺口。

**iter 4 起点**：评估这个新 gap_kind 是否值得加（先 grep 现有
gap_kinds 看有没有近似，没有就加）。

## 历史

- 2026-05-07 iter 3：编码 + 跑 + 评估，partial match。
