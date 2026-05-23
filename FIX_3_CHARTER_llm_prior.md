# Fix 3 Charter — LLM-proposed theta as bounded fallback

> 立项日期：2026-05-23
> 状态：**📝 charter only —— 未实施**
> 对应 task：session todo #127
> 前置依赖：
> - Gap B (v0.1.3) — `ProbabilityStatement.provenance` 字段 + `observational` 取值已落地
> - A2 (slice A2) — `CauseStatement.annotations.source` 已落地（边的来源标注）
> - Fix 1 (v0.1.4) — mediation 数值评估，证明"kernel 把活干到底"是对的方向
>
> Fix 3 是 Gap B / A2 同一条命题的**第三件衣服**：把 provenance 系统从"边 + 观察值"扩到"LLM 常识 prior"。

---

## 0. Scope

**本 charter 只管 LLM 在用户没给 theta 时如何兜底提议参数，以及如何强制审计透明。**

不做：
- 边的来源标注（A2 已做）
- 区间式 prior 表达（Phase 12 bounds-first 自有路径）
- KB 检索式 prior（Phase 11.2 KB adapter 路径）
- LLM 主动给 prior（明确**只**兜底，不机会主义）
- 新增 ResultStatus（用 extensions 信号就够，避免下游分支爆炸）

---

## 1. 动机

### 1.1 核心张力

Themis 的卖点是"**LLM 不能编数字 → kernel 把数字钉死在数据 / 用户陈述参数上**"。

Fix 3 看似反方向：**让 LLM 提议数字**。如果做粗糙，Themis 沦为"自己骗自己" —— LLM 编 prior，kernel 算出漂亮的 0.18，downstream 看到 `numerically_solved` 以为是 ground truth。

但**现实场景**需要它：
- 用户问"咖啡提高效率吗" —— 没数据没参数
- 不做 Fix 3 → Themis 只能返 `needs_investigation` / bounds —— **比 vanilla LLM 更难用**
- Themis 沦为"必须先有数据"的工具，丢失日常对话场景

### 1.2 化解张力的设计原则

**承认 LLM 提议合法，但强制每一项可审查 + 用户在使用前看到清单。**

这跟 project memory `project_themis_repositioning_data_scarcity` 的定位完全一致：

> 用户/LLM 给 DAG+断言，**Themis 全面检查** + 告诉用户"要验证**还缺什么数据**"

Themis 不是答案生成器，是审计者。LLM 提议、Themis 算、用户验。三方分工。

### 1.3 兜底 vs 机会主义

**兜底（本 charter 采纳）**：LLM 默认**不**提议；只有当第一轮 `themis.run` 返 `InsufficientTheta` 时，LLM 才提议 prior 跑第二轮。

**机会主义（拒绝）**：LLM 总是带 prior 上来跟用户数据混。

兜底更纯：
- 单一来源 fallback chain（数据 > 用户陈述 > LLM prior），易审计
- LLM 提议的是**精确缺哪些 keys**，不是猜哪些可能缺
- 用户陈述的数字**永远**优先，不会被 LLM 静默覆盖

---

## 2. 语言扩展

### 2.1 schema 变更

**`themis/types.py:ProbabilityStatement`**：

```python
provenance: Literal["structural", "observational", "llm_prior"]
```

第三个取值新增。语义：

| 值 | 含义 | 校验行为（input/semantic_validator） |
|---|---|---|
| `structural` | 用户陈述的 CPT 条目（默认） | parent-subset 严格校验 |
| `observational` | 经验观察条件值 | 跳过 parent-subset 校验（Gap B） |
| `llm_prior` | LLM 常识 prior | 跟 structural 同（**还是** CPT 形状），但**额外要求** `annotations.source` 非空 |

**`themis/types.py:Annotation`**：
保持现有 `source: str | None`，但当 ProbabilityStatement 的 `provenance == "llm_prior"` 时，annotations 必须存在且 source 必须非空且非纯空白字符串。一句话理由强制 —— "猜的" 三个字也比 None 强。

**`themis/schemas/kernel_ast.schema.json`**：
- ProbabilityStatement 的 `provenance` 枚举加 `"llm_prior"`
- 加 conditional schema：`if provenance == llm_prior then annotations.source required & non-empty`

### 2.2 input 层

`semantic_validator._to_statement` 自动 pass through 新值（基础设施已就位）。新校验：
- 加一条规则 `llm_prior_requires_source`（pre-graph），违反报 SemanticError

### 2.3 runtime 层

**完全不动**。Theta 编译只看 key/value/given，不看 provenance。计算上 llm_prior 跟 structural 等价。

### 2.4 output 层

**新增字段** `QueryResult.extensions.llm_proposed_review`：

```python
{
  "edges": [
    {
      "from": "x",
      "to": "y",
      "source": "llm_proposal",          # 从 CauseStatement.annotations.source
      "reason": "<excerpt from source>",
    },
    ...
  ],
  "probabilities": [
    {
      "key": "P(y=true|x=true,m=true)",  # 通过 format_probability_key
      "value": 0.33,
      "reason": "<from annotations.source>",
    },
    ...
  ],
  "summary": "3 条边 + 6 个概率参数来自 LLM 常识 prior。Themis 数学计算正确，但答案依赖这些 prior 的合理性 —— 请审核后再使用。"
}
```

**何时生成**：`result_orchestrator` 走遍 `program.statements`，收集：
- 所有 `CauseStatement` 的 `annotations.source` 含 `"llm"` 关键词（或显式标注为 llm proposal）
- 所有 `ProbabilityStatement` 的 `provenance == "llm_prior"`

如果两个集合都空 → 不输出 `llm_proposed_review` 字段（向下兼容）。

### 2.5 query_result.schema.json

`extensions.llm_proposed_review` 子 schema 新增。

---

## 3. 数据流（兜底循环）

```
Turn 1
  user → LLM → kernel_ast (无 probability statements)
                  ↓
                themis.run
                  ↓
              InsufficientTheta  ←  全部缺
                  ↓
       extensions 列出 missing_keys
                  ↓
Turn 2
  LLM 看 missing_keys → 从常识为每个 key 提议数字
       构造 patch bundle，每条 ProbabilityStatement 带：
         - provenance: "llm_prior"
         - annotations.source: 一句话理由
                  ↓
              themis.apply_patch_and_run
                  ↓
          numerically_solved      ← 计算成功
                  ↓
       extensions.llm_proposed_review  ← 含所有 llm prior 清单
                  ↓
Turn 3 (LLM → 用户)
  reply 强制以 review 表面开头：
  "在回答前，我用了以下 LLM 常识 prior（请审核）：
    - P(Y=1|X=1)=0.7（理由：基础医学常识）
    - P(M=1|X=0)=0.4（理由：药物典型副作用率）
    ...
  基于这些假设，Themis 算出 NIE=0.11。"
```

---

## 4. Skill v3 — LLM 行为协议

`themis/claude_skills/themis-causal-check/SKILL.md` 需新增段落：

### 兜底 propose 规则

- **仅当** `themis_run` 返 `InsufficientTheta` 时才提议 prior
- **不**主动塞 prior 进第一轮 kernel_ast
- 用户给出的任何参数 **永远** 优先

### prior 提议要求

- 走 `apply_patch_and_run`，每条 `ProbabilityStatement` 标 `provenance: "llm_prior"`
- 每条 **必须** 带 `annotations.source`：一句话说明你怎么推出这个数字
  - 好："基础医学常识 + Cochrane meta-analysis 量级"
  - 差：null / "因为" / 空字符串
- 不要造引用 —— 如果你不知道出处，写 "common knowledge, no specific citation"

### 回答格式强制

第二轮 `apply_patch_and_run` 返回的 result 一定带 `extensions.llm_proposed_review`。回答给用户时：

1. **第一段** 必须复述这个 review 列表（中文 / 用户语言）
2. **第二段** 才说结果（"基于这些假设，Themis 计算..."）
3. 不要把 review 折叠到"附录"或"caveats" —— 它**就是答案的前提**

---

## 5. 实施切片

| 切片 | 内容 | 估时 |
|---|---|---|
| 3.1 | types.py + schema + semantic_validator 加 `llm_prior` provenance + `llm_prior_requires_source` 规则 | 半天 |
| 3.2 | result_orchestrator + query_result.schema.json 加 `llm_proposed_review` 输出；遍历 program 收集 | 半天 |
| 3.3 | Skill v3：兜底 propose 规则 + 回答格式强制 | 半天 |
| 3.4 | tests：兜底循环 fixture（turn 1 InsufficientTheta → turn 2 patch with llm_prior → numerically_solved + review surface 完整） | 半天 |
| 3.5 (optional) | verifier 加 soft signal "result_depends_on_llm_priors"，verifier 计算上不变（数值还是要复算） | 半天 |
| **合计** | | **2-2.5 天** |

---

## 6. 不做（明确边界）

- ❌ 新增 ResultStatus —— 用 `extensions.llm_proposed_review` 存在性信号就够，避免 7 状态升 8 状态的下游分支爆炸
- ❌ LLM 必须给 academic 引用 —— common knowledge 没引用是正常状态，强制只会让 LLM 编假引用
- ❌ 区间 prior 表达 —— 跟 Phase 12 bounds 路径耦合复杂，留给独立 charter
- ❌ 机会主义提议 —— LLM 默认不提议（见 §1.3）
- ❌ verifier 拒绝 llm_prior 结果 —— 数学还是要复算，否则 verifier 失去对 mediation 类计算的保护
- ❌ 自动 GapKind for "this result uses prior" —— `llm_proposed_review` 已经是结构化披露，再加 GapKind 是重复

---

## 7. 验收

Fix 3 实施完成的标志：

1. 单元测试：`tests/test_types/test_provenance_llm_prior.py`（新文件），覆盖 schema 校验、`llm_prior_requires_source` 规则、orchestrator 收集
2. 集成测试：`tests/test_e2e/test_llm_prior_fallback_loop.py`（新文件），完整兜底循环
3. Skill fixture：手动 / agent 测试 propose 流程在真实 MCP 链路上工作
4. README / SKILL.md 更新到 v3
5. 全套件 ≥ 1979 passed + 新增测试，0 退化

---

## 8. 关联其他 fix / phase

- Gap B (v0.1.3) — `observational` provenance 是 `llm_prior` 的孪生：都是不动 runtime / orchestrator surface 不同
- A2 — cause-edge provenance：Fix 3 是它的 probability 端对偶；review 表面把两者统一
- Fix 1 (v0.1.4) — "kernel 把活干到底"原则：Fix 3 在 InsufficientTheta 那一刻接住而不是甩给 LLM 蛮干
- Phase 11.1 `gap_to_action.md` — 已有 prompt 教 LLM 怎么响应 gap，Fix 3 是其中一个 action 分支（"propose prior" vs 现有的 "ask user / search KB / accept bounds"）
- Phase 11.2 KB adapter — 未来的"非 LLM"prior 来源，跟 llm_prior 平行：将来加 `kb_prior` provenance + `kb_proposed_review` 是对称扩展

---

## 9. 触发实施的信号

不要为了"完整"提前做。等以下之一发生：

1. 真实用户场景：有人用 Themis 问日常因果问题，反复撞 `InsufficientTheta` —— 这是 Fix 3 的射程
2. Phase 1c 大样本 CLadder benchmark 暴露"Themis 比 vanilla 难用"的 UX 反馈
3. 主动决定将 Themis 定位推向"日常对话辅助" —— 这是 Themis 整体 product roadmap 决策，不是 fix 决策

否则 Fix 3 留在 charter 状态。
