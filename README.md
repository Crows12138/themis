# Themis — 可验证因果推理与估计系统

Themis 是一个 JSON-in / JSON-out 的因果推理系统。当前开发态为
`0.15.0-dev`，代码已经远超早期 `v0.1` 静态内核：它同时包含形式推理、
独立 verifier、数据缺口诊断、估计器、上游 NL/KB/MCP bridge 雏形。

核心原则仍然不变：

**语义干净、缺口显式、推导可审、不能算时说清楚缺什么。**

---

## 当前能力（一句话）

在已知或候选模型上，Themis 可以：

- 运行结构查询：`cause / assoc / identify / effect / probability`
- 处理已显式立项的 fragment：front-door、窄 ADMG、窄 temporal、窄 counterfactual、IV、mediation、transport
- 输出严格推导链，并通过独立 verifier 复核
- 在有数据时通过 `themis.estimate(...)` 给出 backdoor / front-door / IV / mediation / dose-response 估计
- 在不能给点估计时生成 `data_gap_report`，告诉用户还缺什么数据或假设
- 通过 workflow / prompt / KB / MCP 层，把 NL 输入、补录、验证、估计串成可组合流程

当前全量测试基线：`1592 passed / 143 skipped`，warning-clean。

---

## 公开入口

```python
from themis import run, apply_patch_and_run, estimate, verify

# Pure symbolic kernel: JSON/dict -> JSON/dict
out = run(program)

# Multi-turn补录闭环
out2 = apply_patch_and_run(program, [filled_bundle])

# DataFrame旁路估计
estimated = estimate(program, df)

# 独立复核一个 result JSON
verify(program, out["results"][0])

# 独立复核 data_gap_report；适用于没有 derivation 的诊断类结果
from themis import verify_data_gap_report
verify_data_gap_report(out["results"][0])
```

边界约定：

- `run` / `verify` 是纯 JSON 边界，不读外部数据。
- `estimate` 接 DataFrame，是估计层旁路，不改变 kernel AST 的纯语义。
- Themis 自己不发网络请求；KB adapter / LLM / 外部资料检索放在客户端或 sibling repo。

通过 MCP 调用时：MCP server 是长进程，Python 模块只在启动时 import 一次，不
监听文件改动。改完 `themis/*.py` 之后必须重启 MCP server（在 Claude Code 里
退出会话或 `/mcp restart`），否则旧进程会用旧字节码运行新场景，常见症状是
`AttributeError: GapKind has no attribute 'XXX'` 这类对最近加的 enum 找不到的
错误。in-process（`python -c "import themis; ..."` / pytest）每次都是新进程，
不受影响。

---

## 快速压测

当前收口期的最小 smoke：

```powershell
python scripts\run_014_stabilization_smoke.py
```

这条脚本不调 LLM、不发网络请求，覆盖五条 0.14 关键路径：

- dose-response 问句 -> `data_gap_report`
- transport 结构识别 -> `verify`
- dose-response 估计 -> `numeric_estimate` + `verify`
- transport gap -> mock KB adapter -> patch bundle -> `apply_patch_and_run`
- MCP wrapper -> tool catalog + `themis_run` + `themis_verify` + `themis_verify_data_gap_report` + `themis_estimate` + resources

上游世界建模层的当前压力测试：

```powershell
python scripts\run_015_world_modeling_pressure.py
```

这条脚本同样不调 LLM、不发网络请求，用现有 prompt example 固定四类
0.15 压力信号：变量 framing merge、predicate 命名漂移、ADMG assoc m-connection、
narrative refusal 过滤 naive edge。
其中 predicate 漂移通过 `diagnose_predicate_links(...)` /
`diagnose_edge_predicate_links(...)` 只产出候选诊断，确认后再由
`apply_predicate_links(...)` / `apply_predicate_links_to_edges(...)` 回注变量和
边端点；`compose_program(..., predicate_links=...)` 提供统一入口。不自动改写
模型语义。exercise case 也固定了低分 `waist_reduced -> belly_fat_loss` 候选：
确认后 target framing 缩小，但 `missing_distribution` 仍保留。A2 的
`narrative_ambiguities` 会被保留到最终 program 的 `extensions.ambiguities`。

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
  kb/           KB adapter contract, translator, cache, reference proxy
  mcp/          FastMCP wrapper for tools/resources
  web/          local FastAPI UI: mode (b) paste-JSON + mode (a) LLM bridge
  oracle/       development-only differential/parity adapters
```

---

## 权威状态文档

- [CORE_STATUS.md](CORE_STATUS.md) — 当前真实完成度与收口面
- [ROADMAP.md](ROADMAP.md) — 阶段路线与下一步原则
- [COVERAGE_MAP.md](COVERAGE_MAP.md) — 12 个因果定量板块覆盖图
- [VISION.md](VISION.md) — 长期系统定位
- [WORLD_MODELING.md](WORLD_MODELING.md) — 上游世界建模层设计

历史基线仍保留：

- [v0_1_scope.md](v0_1_scope.md) — `v0.1.0` 已冻结基线
- [v0_2_priorities.md](v0_2_priorities.md) — 早期真实工作流强化记录
- [理论框架_v0_1.md](理论框架_v0_1.md) / [formula_ast_spec_v0_1.md](formula_ast_spec_v0_1.md) — 初始形式语义与公式子语言

---

## 当前定位

Themis 现在最准确的定位是：

**可审计的因果推理编排器 + 数据缺口诊断器 + 受控估计层。**

它不是：

- 通用 agent
- 自动世界建模平台
- 预测建模工具
- 替代统计专家的黑盒估计器

Themis 的价值不在“什么都能算”，而在：

1. 能形式化的问题严格推导；
2. 可识别但缺数据的问题明确报缺；
3. 可以估计的问题留下数据契约、方法、CI、敏感性提示；
4. 不该回答的问题拒绝伪装成结论。

---

## 版本状态

- `v0.1.0`：静态 DAG 推理内核历史冻结 tag。
- `v1.0 core freeze`：早期语言 / 运行时 / verifier 收口面，见 `CORE_STATUS.md`。
- `0.14.0-dev`：Phase 14 dose-response estimator。
- `0.15.0-dev`：当前开发态，新增 world-modeling pressure harness。

Phase 编号不是稳定发布号；它记录理论 fragment 与工程 slice 的推进顺序。
