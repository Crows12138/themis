# Case 004 — Pearl's smoking → tar → cancer (front-door)

> 验证抑制路径（已声明 bidirected → unmeasured_confounder_risk 应不
> fire）+ 第一例 front-door L3 case。**意外发现真 bug**。

## NL question

"吸烟会导致肺癌吗？"

## Authoritative source

- **Pearl J.** "Causality: Models, Reasoning, and Inference." 2nd ed.
  Cambridge University Press 2009, §3.3.2 "The Front-Door Criterion."
- 历史：Pearl 用这个例子展示当 X↔Y 有 latent confounder（如 genetic
  predisposition 共同影响 smoking 和 cancer）时，可以通过 mediator
  tar deposit 实现识别——backdoor 不可用，但 front-door 提供出路。

### 核心 quote

Pearl 2009 Theorem 3.3.4 (Front-Door Adjustment):
> If a set of variables M satisfies the front-door criterion relative
> to (X, Y), and if P(X, M) > 0, then the causal effect of X on Y is
> identifiable and given by the formula
> P(Y | do(X=x)) = Σ_m P(M=m | X=x) · Σ_{x'} P(Y | X=x', M=m) · P(X=x').

要点：front-door 假设（FD1/FD2/FD3 + consistency）失效则识别失效。

## Encoded kernel_ast

[`case_004_pearl_smoking_tar_cancer.json`](case_004_pearl_smoking_tar_cancer.json)

DAG：
- `smoking → tar`
- `tar → cancer`
- `smoking ↔ cancer`（latent confounder, 如 genetic predisposition）
- query: effect of smoking on cancer

## Themis 实跑结果

### iter 10 跑出（修复前）

```
status: needs_investigation
explanation: ⚠ 答案是 manski_natural 给出的符号区间...

GAP KINDS:
  - missing_distribution (blocking)
  - ambiguous_variable_definition × 2 (important)
  - answer_is_bounds_not_point_estimate (informational)
```

**关键 miss**：缺 `front_door_identification_assumption_required`。
front-door 公式确实被构造（formula 是 ∑ᵗᵃʳ P(cancer|tar,smoking') ·
P(tar|smoking)），但 FD1/FD2/FD3 advisory 没 surface。

`unmeasured_confounder_risk` ✓ 正确抑制（has bidirected → 不 fire）。

### Bug root cause

`_classify_front_door_assumptions` 扫 `derivation` 找
`identify_via_front_door` step。但当 status=NEEDS_INVESTIGATION（缺
theta）时，derivation 是空的——同 iter 5 在 unmeasured_confounder_risk
classifier 上踩过的坑。

### iter 10 修

加 program-shape fallback `_has_front_door_pattern`：
- query.intervention 是 X
- query.target 是 Y
- 程序声明了 X ↔ Y bidirected
- 至少存在一个 mediator M 满足 X→M 且 M→Y

满足时 emit advisory 用 `verifier_check` provenance（ref_id =
`program:front_door_pattern`）。verifier registry 也更新允许
`derivation_step | verifier_check`。

### iter 10 跑出（修复后）

```
GAP KINDS:
  - missing_distribution (blocking)
  - ambiguous_variable_definition × 2 (important)
  - answer_is_bounds_not_point_estimate (informational)
  - front_door_identification_assumption_required (informational) ← 新

EXPLANATION:
⚠ 答案是 manski_natural 给出的符号区间...
⚠ 前门识别（Pearl front-door criterion）的有效性以下列假设为前提：
  (1) 中介集 M 阻断 X→Y 的所有有向路径；
  (2) 不存在未阻断的 X→M 后门路径；
  (3) 所有 M→Y 后门路径已被 X 阻断；
  (4) consistency of potential outcomes。
```

## 评估：✅ match（修复后）+ ✅ 抑制路径正确

### Themis 命中

- `unmeasured_confounder_risk` 抑制 ✓（bidirected 声明 → 不 fire）
- `front_door_identification_assumption_required` ✓（修复后）
- front-door formula 正确构造 ∑ᵗᵃʳ P(cancer|tar,smoking') ·
  P(tar|smoking)
- bounds fallback (manski_natural) 因缺 theta

### Themis 错过（修复前）

- 见 Bug root cause / 已在 iter 10 修

## L3 corpus 进度

第一次 L3 simulation 找到一个**Themis 真 bug**而不仅是 missing
gap_kind 概念——同 derivation-empty 模式之前已知（iter 5），但这条
分支没 patch。

加 1 个回归测试 `test_front_door_advisory_fires_via_program_shape_fallback`
钉住修复。

## 历史

- 2026-05-07 iter 10：编码 + 跑（◐ partial：FD assumption miss）→
  identify root cause → 修 program-shape fallback → 跑 ✅ match。
  顺便加 9 testㄜtotal 在 test_unmeasured_confounder_risk.py
  （重命名候选：iter 11+ rename 到更通用的 file 名）。
