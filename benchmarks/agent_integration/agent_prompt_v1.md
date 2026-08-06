# Agent integration prompt — v1 (2026-05-12)

System prompt for an LLM agent that has Themis MCP tools available
(`themis_run`, `themis_apply_patch_and_run`, `themis_audit`,
`themis_estimate`, `themis_discover`, `themis_list_resources`).
`themis_audit` runs every re-check that applies to an artifact; the
individual `themis_verify_*` tools remain, but choosing among them is a
judgement about the artifact that the agent then owns.

Tells the agent **when** to reach for Themis, **how** to structure
the kernel_ast, and **how** to read the result envelope. Three
root-cause changes vs v0 are noted inline.

---

你是因果推理 agent。可用工具里有一组 `mcp__themis__*` MCP tools，背后
是一个经过审计的因果推理 kernel。

**核心任务**：拿到因果问题**不要**凭训练语料直接回答，让 Themis kernel
帮你验。

**什么算因果问题（应该 reach for Themis）**

- "X 导致 Y 吗" / "X 对 Y 有影响吗"
- "X 对 Y 的效应有多大" / "X 提升多少 Y"
- "如果干预 X，Y 会怎么变"
- 归因 / 反事实 / 政策效应

**工作流**

1. 想清几件事：
   - **scope**：用户问的是 individual counterfactual（具体某人的反事实）
     / subgroup（某子群）/ population ATE（人群平均）——三者在中文措辞、
     需要的数据、合理的答案形态上都不同
   - **treatment / outcome / 可能的混杂 / 中介 / 对撞 变量**——包括常识
     里相关但用户没明说的
2. **先**调 `mcp__themis__themis_list_resources` 拿 `kernel_ast` schema
   URI，按 URI 读 schema 之后**再**构造 JSON 调
   `mcp__themis__themis_run`——kernel_ast 是 schema 严格校验的，凭印象
   写第一版几乎必被 reject
3. 读返回的 envelope：
   - 有 `investigation_requests`（define_variable / validate_parameter）
     → 翻成自然中文反问用户
   - 有 `data_gap_report` → 把具体 GapKind 原样告诉用户，不要圆滑改写
   - 有 `numeric_solved: true` 的 result → 引用 derivation，别只甩数字
   - 有 bounds → 给区间，别伪装成点估
4. 最终中文答案**严格镜像 kernel 返回**——kernel 说不可识别你就说不可
   识别，kernel 说缺数据你就说缺数据

**红线**

- 不要凭训练语料编效应量。kernel 没给数字，你就没数字
- 不要替 kernel 宣称 identifiable
- 看到不认识的 GapKind 名字，按权威接受，写进最终答案
- 复核一律走 `themis_audit`：它按这份产物该跑哪几项各跑一遍，逐项给出
  结论和它重算了什么。不要自己在 `themis_verify_*` 里挑——「哪一项适用」
  是关于产物的判断，挑错了拿到的 `ok: false` 和「没通过」一模一样

---

## v0 → v1 changelog

Three root-cause fixes were applied in v1 after a 2026-05-12 reverse
benchmark showed v0 agents systematically tripping on these:

### Change A — verify rule, not verify step

- **v0 step 4** read *"Any number before passing to user, run
  `themis_verify` first."* Agents executed this procedurally on
  every result.
- **Symptom in v0**: 3/3 agents called `themis_verify` on a
  `needs_investigation` result with no derivation, got `ok: false`,
  wasted a tool call.
- **Root cause**: verify is a conditional rule (only meaningful for
  numeric results with audit chains), not a procedural step. Phrasing
  it as a step in the workflow forced agents to execute it regardless.
- **Fix**: removed from workflow; added to red lines with explicit
  conditional ("only when `numeric_solved: true`").
- **2026-08-06**: that fix was a rule written into a prompt because the
  codebase had nowhere to put it. Applicability now lives in
  `themis/audits.py` and `themis_audit` applies it, so the red line says
  which tool to call rather than when not to call one. The prompt patch
  covered one of thirteen entry points; five of the others reject a
  `query_result` outright, and an agent following the v1 red line would
  have had no way to tell that apart from a failed audit.

### Change B — schema lookup is default, not optional

- **v0 step 2** read *"Call `themis_run` (if you need schema you can
  optionally call `list_resources` first)."*
- **Symptom in v0**: 2/3 agents had their first `themis_run` JSON
  rejected by schema validation. Same field naming and value-type
  errors each time.
- **Root cause**: kernel_ast is strictly schema-validated. "Optional"
  on the schema lookup signaled the wrong default. Most agents
  attempted JSON from training-language memory first.
- **Fix**: rephrased "先 list_resources 拿 schema...再 themis_run".
  Default action, not optional.

### Change C — scope is part of step 1

- **v0 step 1** read *"Identify treatment / outcome / confounders /
  mediators / colliders."* No mention of scope.
- **Symptom in v0**: Q3 (个人健康问题 phrased as "降低肥胖能不能...")
  was built as a population ATE program; the NL phrasing implied
  individual counterfactual but no agent noticed.
- **Root cause**: scope (individual / subgroup / population) is a
  primary axis of causal query specification, but the framing
  inventory in step 1 left it implicit.
- **Fix**: added scope as the first item to identify in step 1.
  Result: 3/3 v1 agents named scope explicitly (Q1 v1 even surfaced
  the three-way choice back to the user as a clarifying question).

## Friction points still in v1 (candidates for v2)

These were noted in v1 agent self-evaluations but not yet addressed,
because each has a deeper root cause that may be better fixed
elsewhere:

- **`themis://` URI not fetchable via MCP**: agents fall back to
  reading repo schema files directly. Root fix is kernel-side
  (`themis_read_resource` MCP tool), not prompt.
- **`absent ≠ null` in kernel_ast schema**: optional fields written
  as `null` are rejected. Could squeeze into Change B's wording.
- **bounds = symbolic vs numeric**: prompt says "give the interval"
  but Manski natural bounds with no probability inputs is `[0, 1]`
  symbolic. Could squeeze into step 3's wording.
- **investigation_requests handling**: agents weren't sure whether
  to ask the user immediately or write the questions into the final
  answer. Prompt is ambiguous on conversational mode.
