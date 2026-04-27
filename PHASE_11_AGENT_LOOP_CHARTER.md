# Phase 11 Charter — Agent Loop Closure

> 立项日期：2026-04-26
> 状态：**S.11.1 / 11.1.2-3 / 11.2 全部已落地**；S.11.3+（真 KB adapter）按
> 真实压力推进
> 对应 VISION：Phase 10 把 gap **结构化**，Phase 11 把 gap **触发**外部
> 动作 — 让 Themis 从被动诊断器升级为 agent 工作流的因果决策中枢
> 触发：2026-04-26 用户洞察 — "发现缺陷告诉 LLM 之后，其实就是驱动
> LLM 做下一步，这是一个闭环"

## 0. 本 charter 结构

Phase 11 分两阶段：

- **S.11.1 prompt-only loop closure**（已落地）— 一份 prompt 文件
  + MCP server 注册 + 测试更新。零代码改动，所有 LLM 客户端立即可用。
- **S.11.2+ KB 接入**（待开）— 给 prompt 决策表里"WebSearch + KB"那
  一栏加真实的 KB adapters（PrimeKG / SciGraph / SemMedDB）。这是
  COVERAGE_MAP 元基础设施扩展，不在 12 板块内。

S.11.1 设计的关键洞察：**完整闭环不需要等 KB 接入**。LLM 已经有
WebSearch 工具，prompt 告诉它什么时候用 / 用什么 / 怎么把结果包成
patch 就足够把回路跑起来。KB 接入是把"WebSearch 结果质量"提升到
"结构化 KG triples 质量"——是优化，不是必要前提。

---

## 1. 动机

### 1.1 真实压力

2026-04-26 用户对话："发现缺陷告诉 LLM 之后，其实就是驱动 LLM 做下
一步，这是一个闭环"。

之前 Phase 10 完成后，data_gap_report 是结构化的，但**没有 prompt
告诉 LLM 怎么用它**。LLM 看到"missing_distribution: P(y|x)" 后会自己
脑补该 WebSearch 还是 AskUser 还是放弃 — 行为不一致、不可审计、
经常跳过 gap 直接编一个数。

S.11.1 给 LLM 一份**决策表 + 工作流约束**，让"gap → action → patch
→ re-run → verify"这个回路有明确规则。

### 1.2 闭环示意

```
用户 NL 问题
   ↓
LLM 提取变量 + DAG + 断言   ← nl_to_kernel_ast.md
   ↓
themis.run → data_gap_report
   ↓
LLM 按 gap_kind 选动作       ← gap_to_action.md  (S.11.1 这个新 prompt)
   ↓
执行（WebSearch / AskUser / 终止）
   ↓
themis.apply_patch_and_run → 新结果
   ↓
themis.verify (T10 audit)    ← 防 LLM 假装补完
   ↓
循环到 numerically_solved 或 unidentifiable
   ↓
按 response_rendering.md 渲染回复用户
```

### 1.3 为什么 prompt-only 优先

- **零代码改动**：1 个新 prompt 文件 + MCP 注册 + 1 行 test 更新
- **立即可用**：所有挂 Themis MCP 的 LLM 客户端读到这份 prompt 就
  能按规则跑闭环
- **不卡 KB**：KB 接入是**优化**（结构化 vs WebSearch），不是必要
  前提。先把回路跑通，再优化每一步的工具
- **可独立测试**：用子 agent 真测（见
  `feedback_themis_real_test_methodology.md`）验证 LLM 是否按决策
  表走

### 1.4 OSS 现状

类似的 "agent loop with structured tool decisions" 在 LangChain /
AutoGen / DSPy 都有，但**没有一个是因果推理专用的**。Themis 这份
prompt 把决策权完全建立在 `data_gap_report.kind` 这个结构化语义上，
不依赖 LLM 模糊判断 — 这是因果推理 agent 的一个独立小贡献。

---

## 2. S.11.1 设计（已落地）

### 2.1 新 prompt 文件 `docs/prompts/gap_to_action.md`

包含：

1. **闭环示意图** — 文档开头给出"NL → run → gap → action → patch → ..."
   的视觉模型，让 LLM 知道自己在哪一步
2. **决策表** — 9 个 gap_kind 各对应 next action + tool + severity
3. **终止条件** — 5 个明确停止信号（status 完成 / 全 unidentifiable /
   3 次失败 / 用户拒绝 / 5 轮总预算）
4. **autonomous fetch vs ask user 启发式** — 公开数据自己查，
   epistemological choice 必问用户
5. **patch 构造模板** — parameter_fill_bundle / framing_skeleton_bundle
   两种形状 + provenance 强制规则
6. **2 个 worked example** — 一个 transport 双 gap loop（fetch +
   AskUser 混合）；一个 unidentifiable 直接终止
7. **What NOT to do** — 6 条硬规则（禁止编造 / 禁止跳 verifier /
   禁止吞 gap / unidentifiable 不能 paraphrase 成 "unsure" / 5 轮硬
   预算 / 不要问用户应该自己 fetch 的数据 / assumption gap 必问用户）
8. **Loop budget** — 3 fetch + 1 user + 5 总轮上限

### 2.2 MCP server 注册

`themis/mcp/server.py` PROMPT_FILES 加 `gap_to_action.md`。同步
更新模块 docstring 和 test_mcp_server 的 resource 列表断言。

### 2.3 不需要其他改动

- types / schema / verifier / generator 全部不动
- response_rendering.md 不动（gap_to_action 是 *新* prompt，不替换）
- 所有 12 板块代码不动
- kernel.py / scheduler.py 不动

S.11.1 = **加一份指引文件 + 让 MCP 知道它存在**。仅此而已。

---

## 3. S.11.2+ 待开（KB 接入）

S.11.1 让 LLM 知道"missing_distribution → WebSearch 那个 P(...)"。
S.11.2+ 是把那一行的 "WebSearch" 升级成结构化 KG 查询，提高数据质量
+ 减少 LLM 幻觉风险。

按真实压力分阶段：

**重要重排（2026-04-27）**：原计划 S.11.2 = PrimeKG 直接接入，
1.5 周。实际执行选择 adapter-first：先建 `themis/kb/` 契约骨架
（`PHASE_11_2_KB_ADAPTER_CHARTER.md`），后续真 KB 接入插件式做。
理由：避免 PrimeKG-shaped 抽象偏倚后续 SciGraph/SemMedDB 接入。
重排后：

> **进一步收紧（2026-04-27 同日）**：用户明确"LLM 怎么搜资料不关我们
> 的事"。S.11.3-S.11.7 全部**废弃**——真 KB adapter（PrimeKG /
> SciGraph / SemMedDB / Wikidata / 冲突解决）都不是 Themis 的事，是
> 客户端 / 第三方 repo 的工作。Themis 的 KB 工作以 S.11.2 契约骨架为
> 终点；下表保留作历史记录但不会推进。详见
> `project_kb_adapter_invariants.md` 记忆（"Themis 不发网络请求 + 不
> 教 LLM 如何 fetch"双重边界）。

| Sub-slice | KB / 工作 | 板块 | 估时 | 状态 |
|---|---|---|---|---|
| **S.11.2** | KB adapter 契约骨架（schemas / ABC / translator / cache / reference adapter） | 元基础设施 | ~1 天 | ✅ 已落地 (2026-04-27, +95 tests) |
| **S.11.3** | PrimeKG (Harvard) — 结构化 + evidence_grade 字段 | 生物医学 | ~3 d (sibling repo) | 待开 |
| **S.11.4** | SciGraph SCP (浙大/上海 AI Lab) — 现成 MCP，覆盖中文中药 | 生物医学补充 | ~3 d | 待开 |
| **S.11.5** | SemMedDB — 11M biomedical SPO triples，接近 Themis 想要的 "X causes Y + 文献来源" | 生物医学 | ~4 d | 待开 |
| **S.11.6** | Wikidata — 实体对齐（"运动" → "physical exercise" Q1003932）| 通用 | ~3 d | 待开 |
| **S.11.7** | 冲突解决算法（多 KB 给不同结论时按 study_type × sample_size × recency 加权） | 元基础设施 | 1 周 | 待开 |

注：S.11.3+ 必须 **sibling repo 形态**，不进 themis 主仓
（详见 `project_kb_adapter_invariants.md` 记忆）。每个独立立 charter，
按真实压力推进。

---

## 4. 显式 Out-of-scope

- **代码层 agent loop 实现** — Themis 不内建 agent runtime；prompt
  指引的执行权完全在客户端 LLM。本 charter 只提供决策表，不提供
  Python orchestrator
- **NL → kernel_ast 改进** — 那是 nl_to_kernel_ast.md 的范畴
- **新 gap_kind** — Phase 10 已经有 9 种；新 kind 等真实压力出现
- **LLM 训练 / 微调** — 永远不在 Themis scope（VISION "5 条 API 允许
  规则"已划清）
- **autonomous tool 执行** — Themis 不做"代理人执行 WebSearch"，那是
  上游 LLM 客户端的工具能力

---

## 5. 完成标志

### S.11.1（已完成）

- ✅ `docs/prompts/gap_to_action.md` 落地
- ✅ MCP server 注册新 prompt
- ✅ test_mcp_server 加断言
- ✅ 全部测试通过
- ✅ 子 agent 真测：能在没人提示的情况下读到 gap_to_action.md 并
  按决策表走（**这一项需用户重启 Claude Code 后用真问题压测**）

### S.11.2+（按真实压力）

每个 KB sub-slice 独立 charter + 完成标志。

---

## 6. 验收

S.11.1：
- ✅ `tests/test_mcp_server.py::test_server_exposes_prompt_and_schema_resources`
  接受 `gap_to_action.md` URI
- ✅ 1171 baseline tests 不降级
- ✅ 子 agent 真测确认决策表语义可用（待用户重启 MCP 后验证）

---

## 7. 不做的（永远）

- 在 Themis 内置 agent runtime — 与 VISION "JSON-in / JSON-out, no LLM
  inside" 矛盾
- 自动调用外部 LLM 完成 fetch — 同上
- prompt 里嵌入特定模型的 quirks — gap_to_action.md 应该对所有遵守
  prompt 的 LLM 都有效，不针对 Claude / GPT-4 / Gemini 任何一个

---

## Review checklist（用户答）

1. ☐ S.11.1 用 prompt-only 完成回路定义是否够轻量？还是应该加点
   schema 层强制（例如 patch_bundle 必须带 provenance 才接受）？
2. ☐ 决策表 9 行是否够覆盖？需要再加 `severity=informational` 时
   的 fallthrough 规则吗？
3. ☐ Loop budget (3/1/5) 是否合理？需要让用户能在 program 里覆盖吗？
4. ☐ S.11.2+ KB 接入优先级：PrimeKG → SciGraph → SemMedDB 这个排序
   合理吗？还是应该先做 SemMedDB（最接近"X causes Y"语义）？
5. ☐ 是否要为 prompt 写 markdown linter / consistency check？现在
   prompt 是 free-form 文档，没有自动校验
