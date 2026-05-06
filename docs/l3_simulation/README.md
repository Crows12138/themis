# L3 Simulation — 用权威源压测 `data_gap_report`

## 为什么模拟

VISION L3 价值层（"数据缺口诊断器"独占定位真被用户感知）需要真用户。
Loop 没法采访人。User prompt 授权"遇到需要真人测试的也可以尝试自己
模拟"——这里就是落地。

模拟的关键是 **ground truth 必须外部**——不是 Themis 自己 derive 的、
也不是 loop 自己评的，而是 expert community 已经 document 了的：
- 实际数据限制是什么
- 需要什么数据才能给出权威答案
- 为什么观察性研究曾经给错（如果 RCT 推翻过）

这些"外部已写下的事实"是 Themis 的 `data_gap_report` 可以被对照的
标准——没有 echo chamber。

## 可接受的权威源

- Cochrane systematic reviews
- USPSTF / NICE / WHO recommendation statements
- Hernán & Robins "Causal Inference: What If" textbook
- VanderWeele "Explanation in Causal Inference"
- Pearl / Glymour / Jewell "Causal Inference in Statistics"
- NEJM / JAMA / BMJ / Lancet 标志性论文（明确讨论数据限制时）
- Bareinboim & Pearl transportability papers
- Imbens & Rubin "Causal Inference for Statistics, Social, and Biomedical Sciences"

## 不接受

- LLM 自己生成的解释（echo chamber）
- 单 study claim 没有 review 复核
- Press release / 新闻
- Themis 自己的 derivation 作为 ground truth（循环）
- Wikipedia（除非引用上述权威源时仅作 pointer 用）

## Case 文件结构

每个案例两个文件：
- `case_NNN_<short_name>.md` — 案例描述 + 期望 + 实跑结果 + 评估
- `case_NNN_<short_name>.json` — kernel_ast encoding（可能多个）

`.md` 内部章节：

```markdown
# Case NNN — <title>

## NL question
"..."（用户可能用中文 NL 问的形式）

## Authoritative source
- 引用：<author year journal/book>
- 核心 quote（讨论数据限制 / RCT-obs 差异 / 关键混杂）

## Expected Themis output
- structural_result：identifiable / unidentifiable / needs_investigation
- data_gap_report：哪些 gap_kind 应该被报、哪些 alternative_paths 应该有

## Themis 实跑结果
（命令 + 完整 envelope，paste verbatim）

## 评估
- ✅ match：Themis 报的 gap 与权威源说的限制一致
- ◐ partial：部分 gap match，部分 miss
- ✗ miss：Themis 完全没 surface 那个关键数据限制
- 💥 false-positive：Themis 报了一个权威源没说的"问题"

## 后续 action
- match → 当 regression test pin 住
- partial → 提具体改进项（哪个 gap_kind 要加 / 强化）
- miss → 提 kernel / report generator bug，下个 iter 修
- false-positive → 提 kernel 误报 bug，下个 iter 修
```

## Loop 终止条件

当 ≥10 mined cases 都通过（match 或 partial-known-gap，且新 case 不再
surface 新的系统性 disagreement）→ L3 simulation 进入 plateau，回交
用户做真人 recruitment（loop 自己不能 claim L3 已被真用户验证）。

## 已落地案例索引

（按 case ID 升序填充）

- [Case 001 — HRT-CVD discrepancy](case_001_hrt_cvd.md)（2026-05-07，
  ◐ partial match：识别 / formula / bounds / framing 全对，但 miss 了
  unmeasured-confounder-risk advisory；提议新 gap_kind
  `unmeasured_confounder_risk`）
- [Case 002 — Vitamin D supplementation for CVD](case_002_vitamin_d_cvd.md)
  （2026-05-07，◐ same partial miss as case 001 → confirmed systematic：
  N=2 跨 case 同一 4 gap_kind 集合，新 gap_kind 立项条件成熟）
