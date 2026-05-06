# Wall.md — Autonomous-loop blockers

Append-only log of items the /loop hits and cannot fully resolve without
external input (real users / infra / credentials). Used by subsequent
iterations to avoid redundant retries.

Format: `## YYYY-MM-DD · <class> · <one-line summary>` then short body.

---

## 2026-05-07 · real-user-validation · L3 价值层未被真人验证

VISION 定位"数据缺口诊断器"这条独占价值需要真人跑系统并反馈，loop
没法采访人。

**Workaround**（per user prompt 授权 "遇到需要真人测试的也可以尝试自己
模拟"）：从公开权威源（Cochrane systematic reviews / USPSTF / NICE /
Hernán "What If" / Pearl 等）挖案例做模拟。每个案例需要：
1. 外部权威源 quote 出"实际的数据限制"
2. 跑 Themis 拿 `data_gap_report`
3. 对照——不是 loop 自评

methodology + cases 见 `docs/l3_simulation/`。

**Stop condition**：≥10 mined cases 全部通过（match 或
partial-known-gap）即判定 L3 simulation plateaued，loop 回交用户做真人
recruitment。

**Reverse-direction safety**：如果 loop 发现 Themis 在多个 mined cases
上误判 gap_kind，是真 bug，回到 kernel / report generator 修，**不**
判定 L3 通过。

### 2026-05-07 iter 20 update — plateau **达成**

- 10 cases mined（cases 001-010），跨 7 个域，覆盖全 8 识别路径 + cause query
- ✅ 9 ✅ + 1 ✅ (case 009 经 partial → iter 19 fix 升 match)
- 2 个真 bug 修：front-door derivation-empty fallback (iter 10) +
  unattempted_layer_due_to_dispatch_conflict (iter 19)
- 1 个新 gap_kind 全 lifecycle：unmeasured_confounder_risk (iter 5-9)
- L3 corpus regression test pin 10/10 cases (iter 17 + iter 19)

**status**: L3 simulation plateaued。loop 不应再 mine 新 case，应转向
其他 VISION gaps 或等真人 recruitment unblock L3 价值层验证。

实测真人需要的：(1) 真人提交他们关心的因果问题；(2) 收集 Themis 的
data_gap_report 是否对应他们实际的数据可得性；(3) 中文 NL 输入 / 错误
信息友好度反馈。loop 都做不到，需要外部触达用户。

---
