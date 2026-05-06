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

### 2026-05-07 iter 21-40 update — post-plateau infrastructure saturated

iter 21-40（doc / test / sync 安全网）累积现状：
- 5 cross-file sync pins（GapKind ↔ schema / verifier registry /
  must-disclose set / response_rendering prompt / kb_lookup prompt）
- 4 service-surface 透传 regression（kernel.run / web `/api/run` /
  MCP `themis_run` / apply_patch_and_run round 持续）
- 8 prompt audited / 多 stale module docstring 同步
- L3 perf pin（200 ms/case + 1 s total 阈值）
- L3 corpus .json/.md pairing pin
- orphan test file guard

剩 "下一步候选" 都需要外部 unblock 或 substantial 单 iter 不可达：
- 真人测试 — 等用户 recruitment（已记上方）
- Tian Line 7 — 需 Q[S'] re-factorization recursion，估 100+ LOC（c_factor.py
  iter 39 docstring 已记 honest deferral）
- 更多 gap_kind（dtype mismatch / propensity overlap / IV strength /
  SUTVA）— 需要 estimation pipeline + 真数据信号
- bounds 扩展（frontdoor partial / Manski-Tamer / 非 binary）— 真用户
  需求 trigger 才立项
- A1/A2 widening — 需 LLM 触达
- V0-V5 / T10 deeper — 需 V framework architectural extension

**loop 边际收益已显著递减**。继续 iter 仍可贡献小修，但每 iter
contribution magnitude 已下降到"小 docstring sync / 小 meta-test"
量级。建议触达真人 unblock L3 价值层 → 真用户反馈会驱动新一波 finding 与 fix。

---
