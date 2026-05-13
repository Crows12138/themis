# Themis — 给 LLM agent 的因果推理 backbone

Themis 是给生产环境 LLM agent 用的**因果推理 backbone**。当 agent 收到"X 会不会导致 Y"/"干预 X 对 Y 的效应是多少"/"如果当初 X 没发生，Y 会怎样"这类问题时，让 agent 把变量、图、查询拉成 JSON 交 Themis 验证——结果是不会被编造、可被审计、可被引用的因果输出。

**核心保证**：

- **数字不会被编造**——kernel 没有数据就不返回数字，只返回 Manski/Balke-Pearl 等无假设界 + 缺什么数据的清单。LLM 在 prompt 边界外被结构性禁止输出"凭语料蒙的 RR=2.3"。
- **审计 trail 完整**——每个回答带 DAG、识别公式、bounds 表达式、`GapKind` 分类、文献引用 (Hernán / Pearl / MacMahon ...)，可以贴进 PR / 合规文档。
- **保守默认**——kernel 默认输出"缺什么、改怎么补"，不是默认给答案再附 caveat。

不是：

- 通用 LLM agent；不是聊天工具
- 自动从数据画 DAG 的工具（图还是 LLM/用户给出来）
- 替代统计专家的黑盒估计器
- 给终端用户直接用的产品

---

## 谁该用 / 谁不该用

**该用**：AI 工程师在做"输出会被引用 / 据此采取行动 / 被审计"的 agent——医疗决策辅助、A/B 归因、政策影响分析、科研助手、金融业务归因。这些场景需要 LLM 因果输出有诚实性 + 可审计性这两条机械保证。

**不该用**：闲聊 / 写作助手 / 创意场景；或者用户已经在 R/Python 里直接写 `dagitty` / `dowhy`——你不需要 Themis 多此一举。

---

## Quick start (临界路径)

> 当前 PyPI 发布**还未完成**——下面是从源码本地安装。`pip install themis-causal` 一旦上传 PyPI 也能跑（核心依赖 + console script 都在 pyproject.toml 里配好了）。

### 1. 安装 + 把 Themis MCP 接到 Claude Code

```bash
git clone https://github.com/Crows12138/themis.git
cd themis
pip install -e .              # 装核心依赖 + 注册 themis-mcp 命令
# 可选 extras：
# pip install -e .[discovery]  # causal-learn (themis_discover)
# pip install -e .[web]        # FastAPI demo UI (themis/web/)
# pip install -e .[oracle]     # pgmpy parity adapter (themis/oracle/)

# Claude Code MCP 配置（项目级 .mcp.json）：
# {
#   "mcpServers": {
#     "themis": {
#       "command": "themis-mcp"
#     }
#   }
# }
# （或者 "command": "python", "args": ["-m", "themis.mcp.server"]）
```

重启 Claude Code 会话；agent 上下文里现在能看到 `mcp__themis__*` 工具。

### 2. 把 agent 集成 prompt 喂给 agent

[`benchmarks/agent_integration/agent_prompt_v1.md`](benchmarks/agent_integration/agent_prompt_v1.md) 是当前稳定 prompt。包含：

- 什么 NL 形式应该 reach for Themis
- 怎么从 NL 构造 `kernel_ast` JSON（先 list_resources 拿 schema 再写）
- 怎么读 `themis_run` 返回的 envelope（`investigation_requests` / `data_gap_report` / `bounds_result` / numeric)
- 红线（不编效应量、不替 kernel 宣称 identifiable、`themis_verify` 只在 numeric_solved 时调）

把这份 prompt 作为 agent system prompt（或拼进现有 system prompt）。

### 3. 试一道因果问题

让 agent 收一道"X 对 Y 的因果效应"问题，看它走 `themis_list_resources → themis_run → 读 envelope → 中文答案`。

输出应包含：DAG + identification 路径 + GapKind 清单 + bounds（如适用），**而不是**自由文本散文 + 编造的效应量。

### 4. 用反差 benchmark 评估

[`benchmarks/agent_integration/`](benchmarks/agent_integration/) 是可复现的反差测试。提供 3 道真实 NL 因果题（confounding × missing parameter / collider / ill-defined intervention），三档 arm（vanilla LLM / LLM + Themis MCP 无 prompt / LLM + Themis MCP + agent prompt），五条评分准则。2026-05-12 首次跑：vanilla 7/15，Themis-v1 15/15。

---

## 程序化入口（Python，非 agent 路径）

如果你不通过 MCP 接 Themis（比如直接在 Python pipeline 里用），公开入口：

```python
from themis import run, apply_patch_and_run, estimate, verify, verify_data_gap_report

out = run(program)                           # 主入口：JSON/dict → JSON/dict
out2 = apply_patch_and_run(program, [bundle]) # 多轮补录闭环
estimated = estimate(program, df)            # 有数据时的旁路估计
verify(program, out["results"][0])           # 独立复核
verify_data_gap_report(out["results"][0])   # 复核 data_gap_report（无 derivation 时用）
```

边界：

- `run` / `verify` 是纯 JSON 边界，不发网络请求、不读外部数据。
- `estimate` 接 DataFrame，是估计层旁路，不改变 kernel AST 的纯语义。
- KB adapter / LLM / 外部资料检索放在客户端或 sibling repo——Themis 自己不发请求。

MCP 调用注意：MCP server 是长进程，Python 模块只在启动时 import 一次，**不监听文件改动**。改完 `themis/*.py` 必须重启 MCP server（Claude Code `/mcp restart` 或退出会话）；否则旧字节码会跑新场景，常见报错是 `AttributeError: GapKind has no attribute 'XXX'` 这类对新加 enum 找不到的错。in-process（`python -c`/`pytest`）每次新进程，不受影响。

---

## 当前能力（一句话）

在已知或候选模型上，Themis 可以：

- 运行结构查询：`cause / assoc / identify / effect / probability / counterfactual`
- 处理已显式立项的 fragment：front-door、窄 ADMG、窄 temporal、窄 counterfactual、IV、mediation、transport
- 输出严格推导链，并通过独立 verifier 复核
- 在有数据时通过 `themis.estimate(...)` 给出 backdoor / front-door / IV / mediation / dose-response 估计
- 在不能给点估计时生成 `data_gap_report`，告诉用户还缺什么数据或假设
- 通过 workflow / prompt / KB / MCP 层，把 NL 输入、补录、验证、估计串成可组合流程

当前全量测试基线：**1943 passed / 143 skipped**，warning-clean。

---

## 主要目录

```text
themis/
  input/        parser + syntactic / semantic validation
  runtime/      graph projection, structural solvers, scheduler, formulas, theta
  verifier/     independent derivation / context / data-gap verification
  output/       result serialization, explanation, data-gap report, bounds
  workflow/     parameter / variable framing fill-back workflows
  upstream/     NL bridge helpers: program builder and narrative merge
  estimation/   backdoor, front-door, IV, mediation, sensitivity, discovery, dose-response
  schemas/      JSON schemas for kernel_ast / query_result / derivation / atom / kb_*
  prompts/      agent-facing prompts + few-shot examples (gap_to_action / response_rendering / etc.)
  kb/           KB adapter contract, translator, cache, reference proxy
  mcp/          FastMCP wrapper for tools/resources
  web/          local FastAPI UI: mode (b) paste-JSON + mode (a) LLM bridge
  oracle/       development-only differential/parity adapters
```

## 临界路径 vs 周边

不是所有上述目录都在当前产品 thesis 的临界路径上。

**Load-bearing（产品临界路径）**：`input` / `runtime` / `verifier` / `output` / `workflow` / `estimation` / `mcp`，加上顶层 `kernel.py` + `types.py`。这些跑 1943 测试每行都在 earning its keep。
另外这些 repo-level 资产也是临界路径：
- `benchmarks/agent_integration/` — 反差 benchmark + agent prompt v1（外部 agent 接入参考）
- `docs/l3_simulation/` — 15 个真案例 corpus（kernel 侧 regression pin）
- `themis/prompts/gap_to_action.md` — GapKind → action 翻译，agent prompt 引用
- `themis/prompts/response_rendering.md` — 弱消费者用的可剥离渲染脚手架

**Deferred / parity / demo / superseded（非临界路径）**：

| 路径 | 当前状态 | 说明 |
|---|---|---|
| `themis/web/` | demo only | 早期 chat-user 定位的本地 FastAPI UI；不在当前产品路径上 |
| `themis/oracle/` | development-only QA | pgmpy / ananke parity adapter，跑 differential testing 用；非用户特性 |
| `themis/kb/` | contract slot only | KB adapter contract + reference proxy；具体 PrimeKG/SemMedDB 实现走 sibling repo（Themis 主仓不发请求） |
| `themis/upstream/` | Phase 4 deferred | narrative_merge + program_builder，配 NL 上游建模用，Phase 4 当前 0% |
| `themis/prompts/narrative_to_*.md` | Phase 4 deferred | 同上 |
| `themis/prompts/nl_to_kernel_ast.md` | superseded for agent flow | 早期 chat-user A1 prompt；agent flow 用 `benchmarks/.../agent_prompt_v1.md` |
| `themis/prompts/kb_lookup.md` | frozen with kb/ | 配 KB adapter 用 |
| `themis/prompts/reply_to_framing_patch.md` | A3 multi-turn | `apply_patch_and_run` 多轮 prompt，valid 但 agent prompt 未引用 |

---

## 反差证据 & 验证状态

- **反差 benchmark** (LLM 单干 vs LLM + Themis)：[benchmarks/agent_integration/findings_2026-05-12.md](benchmarks/agent_integration/findings_2026-05-12.md)
- **kernel L3 case corpus**（15 个真文献案例的 regression pin）：[docs/l3_simulation/README.md](docs/l3_simulation/README.md)
- **测试套件**：1943 passed / 143 skipped（2026-05-12）
- **iter retrospective log**（"为什么 commit X 是这样修的"）：[wall.md](wall.md)

---

## 权威状态文档

- [CORE_STATUS.md](CORE_STATUS.md) — kernel 真实完成度与收口面
- [VISION.md](VISION.md) — 长期定位
- [COVERAGE_MAP.md](COVERAGE_MAP.md) — 12 个因果定量板块覆盖图
- [ROADMAP.md](ROADMAP.md) — 阶段路线与下一步原则
- [ARCHITECTURE.md](ARCHITECTURE.md) — kernel 内部架构详解

---

## Roadmap shortlist（按对 thesis 价值排序）

1. **PyPI publish** — `pyproject.toml` + LICENSE + 本地 `pip install -e .` 都跑通了；剩下 TestPyPI 沙箱试跑 → 正式 PyPI publish 这两步还没做
2. **Claude Skill 包装** — `benchmarks/agent_integration/agent_prompt_v1.md` codify 成 `~/.claude/skills/themis-causal-check/SKILL.md`，自动 discoverable
3. **真用户测试** — sub-agent benchmark 是 proxy；找不熟项目的 AI 工程师真跑一遍
4. **MCP `themis_read_resource`** — 修 `themis://` URI 没 fetcher 的 friction 根因
5. **反差 benchmark 扩到 N=20-30 题** + Arm B (tool-available, no prompt) 测 discoverability
6. **Edge evidence-quality gradient** —`annotations.source` 单 string 分级为 `llm_proposal / cited_paper / kb_validated / RCT`
7. **连续 outcome 支持** — `EffectQuery.target` 接 delta/unit，不只是 literalValue
8. **Layer 3 counterfactual** — twin network / `Y_X` 反事实查询（Phase 5 deferred）

---

## 版本状态

- `v0.1.0`：静态 DAG 推理内核历史冻结 tag
- `v1.0 core freeze`：早期语言 / 运行时 / verifier 收口面，见 `CORE_STATUS.md`
- `0.14.0-dev`：Phase 14 dose-response estimator
- **`0.15.0-dev`**：当前开发态

Phase 编号不是稳定发布号；它记录理论 fragment 与工程 slice 的推进顺序。
