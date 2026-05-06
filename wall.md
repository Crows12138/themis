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

---
