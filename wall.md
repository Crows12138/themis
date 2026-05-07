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

#### 2026-05-07 iter 119 update — direction shift: feature instead of drift-hunt

iter 105-118 全是 doc / inventory drift sync。iter 100 retrospective 的
"basically there + cosmetic phase" 判断把 cron 锁在了易拿 commit 的
低价值动作上。用户 iter 118 直接质问"你现在就是在写 docs 吗"——是。
我之前把 "真正能推进 VISION 的事都需要外部 unblock" 当借口。

实际：iter 110 找到 BoundsMethod 有两个 enum value 没 producer
(frontdoor_partial, manski_tamer_monotonicity)，这是真 feature 缺口
而不是真 unblock。Manski 1997 数学发表 30 年，~150 LOC 实现，scope
clean。

iter 119 落地 **Manski-Tamer monotonicity bounds**：

- `themis/output/bounds.py`: `attempt_manski_tamer_monotonicity` 函数。
  binary outcome / binary intervention 下，给定 MTR 方向（non_decreasing
  / non_increasing），把 Manski natural 的**一边**收紧到观察到的边
  际 P(Y=y)。另一边不变。strictly contained in Manski natural interval。
- `themis/runtime/scheduler.py`: dispatch 优先级 BP-IV → MTR → Manski
  natural；MTR 触发条件读 `program.extensions.monotonicity` dict
  （或 dict 列表），匹配查询的 target+treatment pair。**没有改 kernel
  surface**——不加 EffectQuery 字段、不加 schema 必填 enum、走现有
  extensions 通道。
- `docs/prompts/response_rendering.md`: 加 `#### manski_tamer_monotonicity`
  渲染模板（iter 110 pin 要求 producer 必须有 template）。
- 测试：12 个单元测试 (`test_phase12_bounds_manski_tamer.py`) +
  7 个 dispatch 集成测试 (`test_bounds_manski_tamer_dispatch.py`)
  覆盖 happy path / 4 个方向 × 干预值组合 / fallback / 无关 pair /
  list 形式 / 不合法 direction。

测试基线 1610 → 1629（+19）。iter 100 plateau 判断被这次破除——存量
"aspirational enum 没人写"也算系统真增量，不需要外部 unblock。

下一步候选（同样不需要 unblock）：
1. Front-door partial bounds (Tian 2002) — 第 2 个 aspirational 占位
2. dtype mismatch gap_kind — 从 program 声明 vs estimator 要求推断
3. IV strength gap_kind — F-stat threshold check
4. SUTVA gap_kind — 从 program shape (network/spillover variable) 警告

#### 2026-05-07 iter 140 update — Tian Line 7 honest attempt + math-risk confirmed

iter 140 ended 13-iter streak of "skip Tian Line 7 due to math risk"
with an honest attempt. Read c_factor.py thoroughly; designed naive
"recurse on G[S']" implementation; **traced against simplest Line 7
trigger (front-door variant, X→M→Y with X↔Y latent confounder)** —
naive recursion produces:
    Σ_M P(M|X) · P(Y|X, M)
which is back-door adjustment with (X, M) as adjustment set —
**INCORRECT** because the X↔Y latent confounder makes
P(Y|X, M) ≠ P(Y|do(X), do(M)). Correct front-door formula:
    Σ_M P(M|X) · Σ_{X'} P(Y|X', M) · P(X')

Concrete math finding: Line 7 truly needs Q[S'] symbolic substitution
that walks both G[S'] subgraph AND the substituted distribution's
factorization (so the inner recursion's Line-1 marginal averages
over X' instead of conditioning on original X). Naive "just shrink
the graph" recursion does NOT capture the substitution semantics.

Required for full correctness:
1. Track "current input distribution" symbolically (P vs Q[S']-
   substituted) on _IdState
2. Update _build_marginal to construct factors that respect the
   substituted distribution's factorization (different from global
   topo product)
3. Re-walk recursion's exit so the returned formula is in terms of
   original P, not Q[S']

Estimated 150-300 LOC of careful symbolic machinery + risk of
subtle math error on edge cases. **Confirmed: 13 prior iter declines
were not just "I don't want to" — Line 7 is genuinely subtle and
does require dedicated focus.** Documented in c_factor.py Line 7
punt comment so future contributor (or future me) starts from this
trace instead of repeating the failed naive attempt.

iter 140 deliverable = honest documentation of attempted+failed
attempt, not committing wrong code. wall.md retrospective form is
genuinely new (no recent iter has been "I tried, here's why it
didn't work" entry).

---

#### 2026-05-07 iter 143 update — iter 141 Line 7 shortcut RETRACTED

iter 141 thought it had found a simpler shortcut: call
`_build_q_factor(state, s=s_prime, keep=y, summed_x=frozenset())`
to get Σ_X P(X)·P(Y|X,M) (front-door inner sum). Tests passed
(`identifiable=True`, formula non-None, repr contains x/y/m
tokens). Committed `7bec2f3` + `15853c2`.

iter 143 instrumented the actual formula and traced its evaluation:

```
SumExpr(bind='t_m_me', over=M, body=ProductExpr(
  P(m=None | x=value=True),    # outer Line 4 wrap, m bound externally — OK
  SumExpr(bind='t_x_me', over=X, body=ProductExpr(
    P(x=value=True | _),       # ← BUG: x is literal True, not VarRef('t_x_me')
    P(y=None | x=value=True, m=value=True)  # ← BUG: x=True, m=True literals
  ))
))
```

`grep "VarRef" repr(formula)` returns nothing. Both inner sums are
degenerate (body doesn't reference bind variable). Formula evaluates
to:

```
P(x=True) · P(y|x=True)    (NOT front-door; Σ_X collapses; Σ_M
                            collapses via tower over M)
```

Root cause: `_atom_to_target_va(state, atom)` always returns
`value=state.x_value` when `atom ∈ state.x`, regardless of whether
the call site wants atom as do-substituted or as a bind variable.
The `summed_x` parameter to `_build_q_factor` only controls the
sum-wrap set, NOT the per-atom value. For Line 6 calls this is
fine because `summed_x = state.x` and atoms in `state.x` ARE
do-substituted. For Line 7 shortcut where `summed_x = ∅`, atoms
in `state.x` should be bind variables — but the helper hardcodes
them.

iter 141's "math finding" was wrong; it ignored the
`_atom_to_target_va` substitution semantics. Tests passed because
they only checked structural properties (identifiable, formula
non-None, repr contains tokens) — exactly the "shallow tests" trap.

iter 143 reverts:
- `themis/runtime/c_factor.py` Line 7 → `return None` (no hedge)
- `tests/test_tian_line_7_shortcut.py` deleted
- `tests/test_tian_id.py` docstring + test name back to "punts
  rather than lying"
- `COVERAGE_MAP.md` ADMG row 88% → 85%, "Line 7 推迟" with
  retraction note
- `README.md` / `CORE_STATUS.md` test count 1830 → 1824

Honest finding: real Line 7 implementation needs `_atom_to_target_va`
parameterized by `do_atoms` (atoms to substitute) vs free atoms
(those summed as bind variables) — not derived from `state.x` blind.
Until that exists, Line 7 stays punted.

Lesson for future Line 7 attempts: **trace the formula's evaluation
semantics, not just structure**. Tests must pin (a) `VarRef` exists
inside expected sum bodies, (b) numerical evaluation matches
reference (DoWhy / hand calc) on a concrete CPT.

---

#### 2026-05-07 iter 144 update — sweeping bug discovery via property test

Acted on the iter 143 lesson: wrote a generic property test
(`tests/test_formula_sum_bind_referenced.py`) — for every SumExpr
in a formula, the body MUST reference the bind name via at least
one VarRef. Otherwise the sum is degenerate.

Self-tests (synthetic buggy + synthetic well-formed): pass.

Applied to existing Tian Lines 1-6 paths (claimed working since
2026-05-06): **both audit tests fail**.

- `X → M → Y` (no bidirected): formula has Σ_M wrap with
  BindDecl='t_m_me' but body's
  `P(y=None | x=True, m=True)` has m hardcoded as literal True.
  Σ_M collapses → formula = `P(y|x=True, m=True)` (wrong; should
  marginalize over M to give `P(y|x=True)`).

- `X → Z1, X → Z2, Z1 ↔ Z2, Z1 → Y, Z2 → Y` (the real Tian use
  case — backdoor doesn't apply): Σ_Z1 Σ_Z2 wraps but body has
  `P(y | x=True, z1=True, z2=True)` literals. Both inner sums
  collapse → formula reduces to `P(y|x=T, z1=T, z2=T)` instead
  of properly marginalizing.

Same `_atom_to_target_va` root cause as iter 141. The bug has
been latent in Lines 1-6 the whole time, masked because:
- Backdoor / front-door / IV / ADMG-aware paths fire BEFORE Tian
  for most queries
- Existing Tian unit tests only assert `identifiable=True` and
  `formula is not None`, never numerical evaluation

Iter 144 deliverables:
1. `find_degenerate_sums(formula)` helper — pure function, tested
2. 2 self-tests (helper itself works on synthetic buggy + good)
3. 2 audit tests on real Tian formulas, marked `xfail(strict=True)`
   so future fix flips them to xpass and forces the marker removal
4. wall.md retrospective (this entry)
5. Test count 1824 → 1826 (2 xfailed not counted as passed)

Future fix: parameterize `_atom_to_target_va(state, atom, *, do_atoms)`
so the substitution happens only for atoms in `do_atoms` (the
caller's effective intervention set), not for every atom in
`state.x` (which gets enriched in Line 4 sub-recursion). Multiple
call sites need updating to pass the right `do_atoms`. Not a 60s
fix — but the property test is now infrastructure that makes the
fix auditable.

Lesson reinforced: **shallow tests = invisible bugs**. The Tian
algorithm has been "working" for a year by passing identifiable=True
checks while emitting incorrect formulas. The property-test layer
is now the canary; future formula-emitting code (any new Phase, any
new ID line) should add a degenerate-sum check.

---

#### 2026-05-07 iter 145 update — fix the Tian degenerate-sum bug

iter 144 documented the fix path. iter 145 implemented it:

- Added ``do_atoms: frozenset[Atom]`` field to ``_IdState``,
  defaulting to ``frozenset()``. ``identify_via_tian`` initializes
  it to the user's true intervention atoms (``x_set``).
- All sub-recursion ``_IdState`` constructions (Line 2 ancestor
  shrink, Line 3 W join, Line 4 sub-recursion) thread
  ``do_atoms=state.do_atoms`` unchanged.
- ``_atom_to_target_va`` checks ``atom in state.do_atoms`` instead
  of ``atom in state.x``. Atoms that are in ``state.x`` only via
  algorithmic recursion (not in the user's original do-set) now
  get ``VarRef(name=_canonical_bind_name(atom))`` and the wrap
  step's bind name matches.

Result: both audit tests in ``test_formula_sum_bind_referenced.py``
go from xfail to pass. All existing Tian unit tests still pass
(structural assertions are unaffected). Test count 1826 + 2 xfailed
→ 1828 passed.

Verification: ran the disjoint-Y-component case manually and
confirmed Σ_Z1 Σ_Z2 wraps now have body terms with
``value=VarRef('t_z1_me')`` / ``value=VarRef('t_z2_me')`` — sums
are no longer degenerate.

Iter 141 → 145 arc: 4-iter sequence to honestly land a real fix.

- iter 141: thought I had a Line 7 shortcut, shipped wrong code
  (wrong tests passed because shallow)
- iter 142: doc-sync update reflecting the (still-broken) shortcut
- iter 143: traced formula evaluation, retracted iter 141 + 142,
  documented "tests must pin VarRef + numerical eval" lesson
- iter 144: built the property test that would have caught it,
  applied to existing code, discovered same bug had been latent
  in Tian Lines 1-6 the whole time, marked xfail with note
- iter 145: implemented the do_atoms / x split fix, audit tests
  flip to pass, no regressions

Honest record of how a bad commit becomes a real fix when the
infrastructure exists to catch it. The xfail-strict marker pattern
in particular — file the bug as a strict-xfail with the fix path,
then a future iter implements the fix and watches the marker
flip — is now a worth-repeating pattern for known bugs.

---

#### 2026-05-07 iter 150 update — Tian e2e architectural gap

Tried to write an e2e numerical test (kernel_ast → themis.run →
identify_via_tian → numeric_estimator → numerically_solved). The
disjoint-Y case (X→Z1, X→Z2, Z1↔Z2, Z1→Y, Z2→Y) was the natural
target — backdoor / front-door fail; Tian succeeds.

semantic_validator REJECTED the test fixture:

```
ground_statements[11]: probability.given includes ['z1'] which are
not structural parents of z2 (parents=['x']). given must be a
subset of parents(target)
```

Root cause: Tian's c-factor product Q[S] = ∏ P(V_i | V_{<i}) uses
the FULL TOPOLOGICAL PREDECESSOR set, not the structural-parent
set. For the disjoint-Y graph with topo order [X, Z1, Z2, Y]:
Q[{Z1,Z2}] = P(Z1|X) · P(Z2|X, Z1). The second factor conditions
on Z1 even though Z2's structural parents are just {X} — Z1 ↔ Z2
is bidirected (latent confounder), not a structural edge.

The kernel's CPT model only accepts ``probability`` statements
where ``given`` ⊆ structural_parents(target). Tian's formula needs
non-structural conditional CPTs to evaluate. So:

- Tian formula correctness pinned at unit level (iter 145, 147,
  148): ✓ (`identify_via_tian` + `estimate_formula` agree)
- e2e via `themis.run` with theta: ✗ — semantic validator blocks
  the fixture

This is a real architectural gap, not a bug. Either:
1. Loosen semantic validator: when an ADMG has bidirected edges,
   allow ``probability.given`` to include topo-predecessors that
   aren't structural parents (Tian's product needs them).
2. Reformulate Tian's output: factor Q[S] via the joint
   P(S | parents(S)) and add a joint-CPT primitive to the kernel.
3. Accept the gap: document that the Tian path can produce
   structurally identified formulas but they're only numerically
   evaluable when the user supplies the broader CPT family.

Option 1 is least invasive — semantic validator already knows
about bidirected edges (validates ADMG vs DAG distinctions
elsewhere). Option 2 is bigger. Option 3 leaves the gap.

iter 150 decided to NOT pick a fix in 60s; instead documented the
gap here so a future iter can carry it through. The unit-level
pins in test_formula_sum_bind_referenced.py remain authoritative
for Tian formula correctness; only the e2e wiring is gapped.

Lesson: even when iter 145+147 fixed the formula generation, the
end-to-end pipeline can have OTHER places where the assumption
"theta has every conditional you need" doesn't hold. The kernel's
CPT contract was designed for backdoor (where ``given`` ⊆ parents
always holds); ADMG identification breaks that assumption.

---

#### 2026-05-07 iter 151-163 retrospective — precision_budget arc closed

Stepped out of the formula-correctness arc to a different VISION
priority: output (2) item #4 — "在子群 G 做 RCT n=N 能把 CI 收缩到
±δ". 13 iters, all 6 estimator paths now wire post-hoc precision
budgeting end-to-end (helper → wire → schema → renderer doc → sync
pins → method caveats → decision tree).

Arc trajectory:
- 151: math helper estimate_n_for_target_ci_half_width (SE ∝ 1/√N)
- 152: wired backdoor (introduced silent schema violation)
- 153: extended to IV / front-door / transport
- 154: mediation per-component + caught/fixed iter 152 schema gap
  via verify roundtrip
- 155: dose-response per-curve-point — coverage complete
- 156: response_rendering doc — without this LLMs wouldn't surface
- 157: sync pins (rendering + schema) — regression guard
- 158: actionable error message for probability.given violations
  (closes UX gap from iter 150)
- 159: sister property pin (find_unbound_varrefs)
- 160: relative_width = half_width/|point| for mechanical surface
  heuristic instead of LLM judgment
- 161: method-specific caveats (IV/mediation/transport/dose-response
  each have different "more N means" semantics)
- 162: tightened halving template (4× is a fixed constant)
- 163: 3-branch decision tree for surface rule, with crisp handling
  of point≈0 case (CI-brackets-zero vs tight-non-null near zero)

Key lessons reinforced:

1. **Schema enforcement only fires through verify**, not run/estimate.
   iter 152's silent schema violation lasted 2 iters until iter 154's
   mediation verify-roundtrip exposed it. Schema-touching changes
   need eager verify tests.

2. **Mechanical fields beat LLM judgment for derivable rules**.
   iter 156's "surface when CI > 30% of point" was LLM-computed;
   iter 160 made it `relative_width` arithmetic. Reduces LLM error
   on a math step LLMs sometimes get wrong.

3. **Same value field, different semantics per method**. iter 161's
   method-specific caveats: precision_budget hint is the same field,
   but "more N" means compliers (IV) / joint M+Y rows (mediation) /
   weak-stratum enrichment (transport) / per-point allocation
   (dose-response) / straightforward (backdoor). Without these
   caveats, naive LLM rendering would mislead study design.

4. **Test infrastructure can saturate user value**. By iter 161-163
   the value-per-iter dropped sharply — refinements rather than
   bugs. The 144→150 arc had real bug discovery; the 151→160 arc
   delivered a real VISION feature; 161-163 refined edge cases.
   Honest stopping point: when remaining 60s work is sub-bikeshed,
   the genuine remaining value (real LLM stress, Tian e2e fix,
   KB integration, 板块 8/3 expansion) needs multi-iter scope and
   shouldn't be smuggled through 60s ticks.

Test count trajectory through the arc: 1822 → 1856 (+34 across
13 iters; ~2.6 tests/iter average; weighted heavier in helper +
audit + numerical-eval iters).

---

#### 2026-05-07 iter 167 update — Tian e2e fix attempt (partial revert)

Attempted iter 150 option 1: loosen ``probability_parents`` rule
to also accept ``given`` atoms that are bidirected siblings of
target. Threaded ``bidirected`` kwarg through
``validate_against_graph`` from ``dispatch_all`` (already had it
two lines below the call).

Result on iter 165 xfail-strict tracker: STILL FAILS, but on a
different probability statement than before:

- Pre-iter-167: validator rejected ``P(Z2|X=T, Z1)`` because Z1
  isn't Z2's structural parent (Z1 ↔ Z2 bidirected).
- Post-iter-167-loosen: that statement now passes (Z1 IS Z2's
  bidirected sibling). But the next probability statement
  ``P(Y|X, Z1, Z2)`` STILL fails because X is neither Y's
  structural parent nor Y's bidirected sibling — X is a
  grandparent of Y through Z1, Z2.

Root cause: Tian's c-factor product needs ``given`` to range over
ALL topo-predecessors of target within the c-component closure,
not just direct bidirected siblings. The disjoint-Y graph topo
order is [X, Z1, Z2, Y]; Y's V_{<i} = {X, Z1, Z2} — full prefix.
A complete fix needs:

1. Compute c-component containing target_atom (already a
   ``c_components`` helper)
2. Build ancestor closure of that c-component in the directed
   graph (call it the "extended scope")
3. Topo-order that scope and let ``given`` ⊆ predecessors-of-
   target-in-extended-topo

This is correct but ~30-50 LOC of careful work. Out of 60s scope.

Iter 167 deliverable:
- Reverted the substantive loosen (kept rule strict)
- KEPT the ``bidirected`` plumbing through validate_against_graph
  (avoids future plumbing churn — the +24 LOC change is mostly
  the kwarg threading)
- Documented the richer rule needed in semantic_validator.py
  docstring + this wall.md entry

iter 165 xfail-strict tracker remains in place. Next iter's path
forward is clear: implement the topo-predecessor-in-c-component-
closure rule using existing structural_solver helpers.

---

#### 2026-05-07 iter 168 update — validator loosen lands; scheduler routing gap exposed

Implemented the richer rule iter 167 documented:

```
admissible_given = parents(target)
                 ∪ directed_ancestors(target)
                 ∪ bidirected_siblings(target)
```

Disjoint-Y case CPTs now all pass validation:
- P(Z1|X): parents ✓
- P(Z2|X, Z1): X is parent, Z1 is bidirected sibling ✓
- P(Y|X, Z1, Z2): Z1, Z2 are parents; X is directed ancestor ✓

Existing test_non_parent_in_given_is_rejected still rejects
correctly (unrelated atom is neither parent, ancestor, nor sibling).
All 1856 tests still pass.

But iter 165 xfail-strict tracker STILL xfails — for a different
reason now. The disjoint-Y query routes through BACKDOOR
identification (X has no parents → empty adjustment set →
P(Y|do(X)) = P(Y|X)). Backdoor demands P(Y|X) which the user
didn't supply (they supplied the joint P(Y|X, Z1, Z2) family).
Status: needs_investigation with missing_information=
[{name: 'parameter:P(y=True|x=True)'}].

This is a SCHEDULER ROUTING GAP, not a validation gap:
- The user's data is Tian-evaluable (Q[{Z1,Z2}] · Q[{Y}] product)
- But scheduler picked backdoor (preferred path) without checking
  if the user actually supplied the backdoor CPTs
- Backdoor's missing P(Y|X) could be DERIVED via tower from the
  supplied joint, but kernel doesn't auto-marginalize

Two follow-on fixes (in updated xfail reason):
(a) Scheduler fall-through: when preferred path's CPTs are absent
    but a downstream path's CPTs are present, retry on the
    downstream path
(b) numeric_estimator auto-marginalization: when P(Y|X) is the
    demand and the joint family is in theta, derive by Σ over
    intermediates

iter 168 deliverable: validator loosen + xfail-strict reason
updated to reflect the new (scheduler-side) gap. The next
iter has a clear concrete fix path with two options.

---

#### 2026-05-07 iter 171-172 update — auto-marginalization in runtime

Implemented iter 168 option (b): numeric_estimator now auto-derives
missing CPTs by marginalization. When ``_evaluate`` hits a missing
P(Y|given) lookup, it tries ``_try_derive_via_marginalization``
which looks for an atom Z such that:
- For every z in domain(Z), P(Y|given, Z=z) ∈ theta (or recursively
  derivable, depth ≤ 3)
- For every z, P(Z=z|given) ∈ theta (or recursively derivable)

If found: returns Σ_z P(Y|given, Z=z) · P(Z=z|given). Bounded
recursion handles disjoint-Y's two-deep marginalization
(P(Y|X) → marginal over Z1 → marginal over Z2).

iter 171: detection helper (can_derive_via_marginalization, +5 unit
tests).
iter 172: actual derivation + recursion (_try_derive_via_marginalization
called from _evaluate's miss path).

End-to-end on disjoint-Y test fixture: ``themis.run`` now returns
``status='numerically_solved' value=0.596`` matching the hand-
computed reference. iter 165 xfail-strict tracker STILL fails —
now on the verifier side. ``themis.verify`` uses an INDEPENDENT
evaluator (themis.verifier.rules._evaluate_formula) that doesn't
have the marginalization fallback, so raises RuleCheckFailed.

Iter 173 path: port the same fallback to the verifier's evaluator.
Verifier independence is the design goal (V0-V5 audit) so this is
a pure mirror, not a shared dependency.

---

#### 2026-05-07 iter 173 update — verifier mirror lands; gap CLOSED

Ported _try_derive_via_marginalization to verifier as
_verifier_derive_via_marginalization (byte-for-byte semantic mirror,
pure theta + canonical math, no shared state — V0-V5 independence
preserved). Evaluator's missing-CPT branch now tries derivation
before raising _NonConcreteValue.

iter 165 xfail-strict tracker → XPASS(strict) → marker removed →
test renamed test_tian_disjoint_y_e2e_returns_correct_numeric →
PASSING regression pin. Test count 1864 + 1 xfailed → 1865 passed.

Architectural arc summary (iter 165→173, 9 iters):
- 165: xfail-strict tracker filed
- 167: plumbing — bidirected through validate_against_graph
- 168: validator loosen (parents ∪ ancestors ∪ siblings)
- 169: COVERAGE_MAP crosslink
- 170: direct unit pins for iter 168 behavior
- 171: detection helper can_derive_via_marginalization (+5 tests)
- 172: runtime auto-marginalization (+ recursion ≤ 3)
- 173: verifier mirror — gap CLOSED end-to-end

Layers walked: validator → scheduler routing → runtime evaluator
→ verifier evaluator. Each layer closed in turn. The xfail-strict
pattern (iter 144→145 originally) proved its value again: a future-
work tracker with strict=True forces commitment to flip the marker,
not just hand-wave that the gap is "documented".

Lesson: architectural multi-layer gaps DO yield to incremental
60s iters when each layer's fix is well-scoped and the tracker
keeps the goal in sight. Honest 9-iter progression beat the "this
is too risky for 60s" intuition I had at iter 167.

---

#### 2026-05-07 iter 181-183 mini-arc — iter 168 unlocked unanticipated capability

After iter 174-180 micro-refinements (where I kept saying "value
saturated"), iter 181 probed whether the iter 167-173 infrastructure
had any non-obvious effects. Tried the canonical Tian Line 7 trigger
fixture (X→M→Y, X↔Y latent — what iter 141-143 attempted via Tian
shortcut and retracted).

Discovery: themis.run NOW produces correct Pearl front-door 0.6 for
this fixture. NOT via Tian Line 7 (still punted), but via the
EXISTING front-door fragment combined with iter 168's validator
loosen. Pre-iter-168 the fixture's P(Y|X, M) was rejected because
X isn't Y's structural parent. Iter 168's "parents ∪ ancestors ∪
siblings" rule admitted X (BOTH ancestor of Y via X→M→Y AND
bidirected sibling via X↔Y).

So a capability that was structurally impossible to express pre-
iter-168 is now standard kernel behavior. iter 141-143 tried to
force this via Tian Line 7 and failed; the actual fix was at the
validator layer four iters earlier without my realizing.

Verifier-side gap surfaced: themis.verify rejected the same fixture
with a cryptic "backdoor_adjustment_formula witness" error. iter 182
traced to verify.py:367 hardcoding backdoor as the only valid
witness for formula_evaluation. Fix: extended to a frozenset of
admissible identification-formula rules (backdoor + front-door).

Iter 183: hoisted the witness set to module level + added sync pin
to prevent the same hardcoded-magic-string drift class.

Mini-arc deliverables (iter 181-183):
- 181: discovered the unlock + filed regression test for runtime
- 182: closed verifier-side gap (witness set extension)
- 183: hoisted the set + sync pin

Test count 1869 → 1871.

Lessons:

1. **Don't trust "value saturated"**. After iter 174-180 of micro-
   refinements I had concluded the loop was at diminishing returns.
   iter 181's probe found a real new capability that came online
   from the iter 167-173 work but went undocumented for 8 iters.
   Probing what was unlocked, not what's still broken, is a
   different question worth asking.

2. **Architectural fixes have unanticipated downstream effects**.
   iter 168 was scoped narrowly (admit ADMG c-factor CPTs for the
   disjoint-Y case). It silently unlocked the front-door variant
   too — because the validator rule applies to all ADMG cases, not
   just the one driving the fix. Worth probing related fixtures
   after any cross-cutting fix.

3. **Verifier independence cuts both ways**. The verifier's hardcoded
   backdoor-only witness rule wasn't a bug per the "verifier is
   independent" principle — but it WAS a bug in coverage. New
   capabilities need both runtime AND verifier extension; iter 175's
   sync pin pattern + iter 183's witness-set pin both address this.
