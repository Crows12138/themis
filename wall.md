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

### 2026-05-07 iter 100 — milestone retrospective

100 iters of /loop. Summary metrics:

- Tests: 1420 → 1591 (+171)
- L3 corpus: 10/10 plateau achieved (iter 20)
- Real findings: 5 substantive
  - iter 5-9: unmeasured_confounder_risk gap_kind full lifecycle
  - iter 10: front-door derivation-empty fallback (real bug fix)
  - iter 19: unattempted_layer_due_to_dispatch_conflict gap_kind
  - iter 45: themis.__version__ stale (0.14 → 0.15)
  - iter 60-71: misc real drifts (charter status × 7, count drifts × 4,
    abs paths × 28, pytest deprecation, exception docs, missing test
    docstring, etc.)
- Preventive sync pins: ~32 across cross-file sync / docstring inventory /
  link integrity / path bans / count consistency / version sync
- Doc surface: 5 v0.x-era docs got version-pointer headers; all charters
  status-synced; prompt audit (4 files); 5 timestamp drifts caught and
  reset

**iter 41 saturation prediction was wrong** (post-iter-41 still found
~10 more real drift categories). **iter 51 correction was right**
("signal not zero, just lower hit rate"). True命中率: roughly 1
substantive finding per 5-10 post-saturation iters.

Where the loop stops being valuable: when each iter is
- 30-line micro-doc improvements + sync pin tightening
- the loop has fully covered cross-file consistency for current code state

Honest current-state assessment (iter 99): basically there. iter 100+
expected to be cosmetic / late preventive work. Genuine future value:
- Real-user testing (still externally blocked)
- Tian Line 7 (single-iter-infeasible algorithm work)
- New gap_kinds driven by real user data (dtype mismatch / propensity
  overlap / SUTVA), not synthetic case mining

---

### 2026-05-07 iter 96 — minor cosmetic findings not pinned

- 2 files with mixed CRLF/LF line endings (`themis/kernel.py`,
  `tests/test_runtime/test_scheduler.py`). Repo is on Windows; git
  auto-conversion handles most consumer environments. Normalizing
  them to LF would trigger CRLF re-conversion warnings on next
  Windows checkout (`warning: LF will be replaced by CRLF`),
  cascading into many files. Documented here, not auto-fixed.

- Other test files (`test_unmeasured_confounder_risk.py` 12 tests,
  `test_web_app.py` 7 tests, `test_mcp_server.py` 10 tests, etc.)
  don't have docstring inventory like meta-test files do. Inventory
  pattern is appropriate for long meta-files (gap_kind_coverage at
  844 lines / 28 tests, l3_corpus at ~390 lines / 11 tests) where
  navigation matters; smaller files get by without.

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

### 2026-05-07 iter 21-80 update — post-plateau infrastructure saturated

iter 21-80（doc / test / sync 安全网）累积现状：
- **25 sync pins**（GapKind ↔ schema / verifier registry / must-disclose
  set / response_rendering / kb_lookup; CORE_STATUS↔README 测试数;
  package version ↔ 3 doc files; charter status presence; failure_modes
  count; eval_set README counts; COVERAGE_MAP MCP tool/resource count;
  README sub-package list; L3 corpus .json/.md pairing; eval_set case
  edge consistency; README from-themis import; abs path ban .md/.py;
  markdown cross-link resolve; backtick py refs resolve; __all__ ↔
  imports; kernel deprecation-clean; L3 README case index; L3 CASES
  symmetry; .json validity; themis/ docstring; scripts/ docstring;
  tests/ docstring; init docstring exception import resolves）
- 4 service-surface 透传 regression（kernel.run / web `/api/run` /
  MCP `themis_run` / apply_patch_and_run round 持续）
- 多 prompt audited（4 个 prompt 至少一次 currency check）/ 多 stale
  module docstring 同步 / 5 个 v0.x-era doc 加版本指针
- L3 perf pin（200 ms/case + 1 s total 阈值）
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

#### 2026-05-07 iter 45 update — 校正 saturation 绝对论

iter 45 audit 找到真 drift：`themis.__version__ = "0.14.0-dev"` 与
CORE_STATUS / ROADMAP / README 写的 "0.15.0-dev" 不一致——iter 1 doc
sync 漏了 `__init__.py`。任何 `import themis; print(themis.__version__)`
整个 release cycle 拿错版本。修 + 加新 sync pin（package version vs
3 doc files）。

→ "saturation" 不是"零边际"。post-saturation iter 仍能 catch 真 drift；
只是命中率下降到"audit 多次找到一次真 find"水平。继续 cron 仍有信号
价值，但用户应当知道：每个 commit 平均 magnitude 较 iter 1-20 显著
下降。

#### 2026-05-07 iter 45-74 update — 8+ distinct drift categories caught

事实进一步反驳"saturation 等同零边际"：iter 45-74 实际找到 8 个独立
drift category（不计同类多个 instance）：

1. iter 45: `themis.__version__ = 0.14.0-dev` vs docs 0.15.0-dev
2. iter 52-54: 6 PHASE_*_CHARTER status lines stale (Phase 10 / 11.2 /
   2.latent / 7 M2 / 8 M3 / 5)
3. iter 56: failure_modes.md header "22 codes" vs 实际 26
4. iter 57: eval_set/README.md "28 cases / 24 modes" vs 实际 29 / 26
5. iter 59: COVERAGE_MAP "6 MCP tools" vs 实际 7
6. iter 60: README 主要目录漏 web/ 子包
7. iter 63: 28 个 .md 文件含 hardcoded user-specific Windows abs paths
8. iter 68: pytest-asyncio `asyncio_default_fixture_loop_scope` unset
   deprecation warning

加 iter 71 真实 user-facing gap (kernel API 缺 exception docs)，约
50+ 个 specific drift instances 修复。每发现 drift class 立 sync pin
（共 21 个）防再发。

修订观察：post-saturation 命中率下降但**非零**——仍是有效的低成本
audit 通道。每 1-3 iter 平均仍能 catch 1 个真 finding。loop 继续运转
仍有价值，特别是发现 doc/code drift（很难靠人工 review catch 这种
"小但累积"的问题）。

---
