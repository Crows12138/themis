# Themis — 给 LLM agent 的因果推理 backbone

> *中文 README · [English README](README.en.md)*

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

- 运行结构查询：`cause / assoc / identify / effect / probability / counterfactual / causation / scm_counterfactual / counterfactual_conjunction / proximal_effect`
- 处理已显式立项的 fragment：front-door、窄 ADMG、窄 temporal、窄 counterfactual、IV、mediation、transport、probabilities of causation（PN/PS/PNS, Tian-Pearl 2000）、线性 SCM 反事实点（Pearl Primer §4 溯因-干预-预测）、通用反事实识别（Shpitser-Pearl ID*，任意反事实合取 P(γ) 的非参数可识别性判定）
- 输出严格推导链，并通过独立 verifier 复核
- 在有数据时通过 `themis.estimate(...)` 给出 backdoor / front-door / IV（含 Anderson-Rubin 弱工具稳健置信集，工具再弱也有效、并如实返回无界集）/ mediation / dose-response / 通用-ID / 近端 proximal / PN·PS·PNS 归因概率（Tian-Pearl，单调下点识别 + 无假设界）/ 反事实合取的数值估计
- 在不能给点估计时生成 `data_gap_report`，告诉用户还缺什么数据或假设
- 通过 workflow / prompt / KB / MCP 层，把 NL 输入、补录、验证、估计串成可组合流程
- `themis.build_analysis_report(result, program=...)` / MCP `themis_report`：把一次分析（问题 / 因果图 + 边来源 / 答案 / **验证状态** / 假设账本 / 数据缺口）确定性组装成一份中文 Markdown 报告——无需 LLM / API key，前置突出 Themis 独有的「验证 + 还缺什么数据」
- 前置数据诊断：`themis.estimate(...)` 会把每个变量**声明的测量尺度**（`scale` = binary/discrete/continuous，或枚举 `domain`）与**实际数据列**核对——声明连续却只有 2 个取值、或声明二元却 5 个取值，都作为 `declared_type_data_mismatch` 缺口当场提醒，避免闷头算出一个答非所问的数；证据记进 `extensions.type_reconciliation`，由 `verify_type_reconciliation` 从充分统计量独立重导判决。未正向声明的变量不检查（"没说" ≠ "说了连续"），一致的程序完全静默
- 因果发现 + **发现层首个逐数验证**：`themis.estimation.discovery` 有 PC/FCI/GES/GRaSP/LiNGAM 五个整图学习器（causal-learn，输出为待人工审的建议），另加 `markov_blanket(data, target)`——用 grow-shrink 到不动点找目标的马尔可夫毯（局部屏蔽集，供**筛变量建 DAG**，非调整集）。按数据类型分派：连续用 Fisher-Z（充分统计量=相关矩阵）、离散用卡方（充分统计量=稀疏联合列联表）；两条路径下 `themis.verify_markov_blanket(...)` 都能从记录的充分统计量**独立重算**完备性/最小性定义、拒伪造或裁剪的毯（混合连续+离散类型报错，未做）
- 选择偏倚数值端（§S9.1）：样本被限制在选择对撞上时，普通后门会算出**悄悄有偏**的数——`themis.estimate` 不再吐它。若给了外部无偏参考数据 `reference_data=`，则按 Bareinboim-Pearl 选择后门公式（定理3.5）从有偏样本 + 参考权重算出**恢复后的 ATE**；否则明确拒绝并点名所缺的外部数据（真选择对撞下这些权重永远无法从有偏样本本身估出，故外部数据是硬需求，非可选）。`themis.verify_selection_recovery_numeric(...)` 从记录的每层计数 + 权重表独立重跑公式核对（二值处理 + 离散调整集）
- 中介 four-way 验证器强化：差值尺度分解 `four_way_decomposition` 现在把它本就是闭式函数的六个标准化 cell means 记为**充分统计量**，`verify_mediation_numeric` 用 VanderWeele 14.1b 的独立转写从中重导每个分量，连**完全自洽的伪造**也拒（对标 four_way_ratio 锚定拟合系数）；线性结局下同一组 cell means 也逐位钉死 NDE/NIE，logit 结局下 NDE/NIE 来自蒙特卡洛积分故保持不变量级（诚实天花板）
- 缺失数据 recovered-ATE 数值验证器（§S9.2）：`estimate_recovered_ate` 的数挂在无 derivation 的 `needs_investigation` 结果上，derivation 门控的 `themis.verify` 够不到它——过去伪造 point 无人审。现在估计器把 g-formula 求和所用的每层充分统计量（conditional `{z,arm,n,y_sum}` + marginal `{z,count}`）记进 `recovered_ate.sufficient_statistics`，公开验证器 `themis.verify_missing_data_numeric(result)` 独立重跑 `Σ_z (E[Y|1,z]−E[Y|0,z])·P(z)` 核对 point、朴素对照、归一与丢层，拒伪造 point 或篡改层（MCP 新增 `themis_verify_missing_data_numeric`，13→14）
- 过度识别 IV + Sargan 检验（候选 F）：IV 层过去硬锁单工具，图里两个合法工具只用第一个、默默丢弃其余、也从不做过度识别检验。现在同一 conditioning 下 ≥2 工具走**过度识别 2SLS**（`estimate_iv_overid`）并跑 **Sargan (1958) 过度识别检验**——**小 p 值反驳工具集的联合有效性**（数据能否证伪工具集，是线性/连续版的 Balke-Pearl 工具不等式，孟德尔随机化的杀手场景）。派生终端做结构许可，`verify_iv_overid_numeric` 从记录的残差矩阵独立重导点 + Sargan J + p 拒伪造；Sargan 拒绝时挂 `overidentification_rejected` gap。单工具路径逐字不变（异方差稳健 Hansen J 见下条）
- 测量误差混淆矩阵求逆（候选 E）：测量误差过去只有定性 gap 警告（`measurement_error_concern`：识别路径有自报/问卷/单次测量→挂 ⚠"估计有偏"），估计层零校正——即便用户手握验证研究的误分类率也反解不出真效应。现在被误分类的**离散结局**给定验证过的混淆矩阵 M，在**非差异误分类**假设下逐后门层求逆 `p_true=M⁻¹p_obs` 恢复真分布并做后门标准化（二值即 **Rogan-Gladen 1978**，整体=naive/det(M)，det=Se+Sp−1 衰减因子）。接口 `estimate(misclassification={outcome:{confusion_matrix,states}})`，混淆矩阵是载荷性外部输入（噪声数据本身识别不出），拒奇异/非列随机矩阵、拒非后门识别，refusal 记 estimator_failure 不悄悄吐衰减朴素点；`verify_measurement_correction_numeric` 从记录的矩阵+每层值计数**独立重新求逆**重导校正/朴素点拒伪造点、篡改矩阵、丢层、缺臂。仅结局误分类·仅非差异·矩阵视为固定（暴露误分类/差异矩阵/连续误测仍属 gap 领域）
- 非二值处理 Manski 自然界限（候选 C）：partial-identification（bounds）层此前对**非布尔处理**整层跳过——调度器顶部 `if not intervention_is_bool: return` 把多值处理（如 `do(dose=2)`）连无假设的 Manski 下限都挡掉，尽管单臂自然界 `P(Y=y|do(X=x)) ∈ [P(Y=y,X=x), P(Y=y,X=x)+P(X≠x)]` 与处理基数无关（这是"门控非数学"：数值算术早已对，符号层却吐废字符串、验证器硬门拒审）。现在解顶层门（BP/MTR 仍各自门控在布尔——多值落到无假设 Manski 地板）+ 新增处理侧离散门（未声明离散域的连续点干预不挂平凡 `[0,1]`）；符号补臂对多值渲染为汇总不等式 `P(X≠x)`（布尔仍 `P(X=¬x)`）；数值层记录三个臂计数作充分统计量，`verify_manski_natural_bounds_result` 从记录计数**独立重导** lower=n_joint/n、upper=(n_joint+n_other)/n + 臂划分不变量（把 Manski 数值端从仅元数据审计升级为强重导——多值汇总补臂质量元数据审计验不出伪造宽度，重导能）。仅 Manski 自然界·多值处理 MTR/Balke-Pearl（二值构造）与多层对比界推迟
- 异方差稳健 Hansen J 过度识别检验：过度识别 2SLS 此前只算**同方差 Sargan (1958) J**（iv.py 明写「Hansen 稳健 J 推迟」）。异方差/聚类数据下 Sargan 用了错误的权重矩阵，其对工具集的证伪不可信（探针：3 工具异方差设计 Sargan J=0.038 vs Hansen J=0.032，同方差重合）。现补上高效两步 GMM 的 **Hansen (1982) J**——同 H0/同 χ²(q−1)，但用稳健矩方差矩阵 `Ŝ=(1/n)Σûᵢ²zᵢzᵢ'`（聚类声明下走聚类稳健 CR0）替代同方差 σ²(Z'Z)。头条点估计仍 2SLS（同方差下相同），高效 GMM 点作诊断记录；Hansen 是附加项，Ŝ 奇异时 2SLS+Sargan 原样保留。**过度识别 gap 改由稳健 Hansen 驱动**（复用既有 `overidentification_rejected` kind），`verify_iv_overid_numeric` 增独立 Hansen 重导（从记录的 Ŝ + 交叉矩第二次转写重导高效 GMM 点 + J，加 Ŝ 对称-PSD 校验）。仅单内生·HC0/CR0 无有限样本乘子·多内生推迟
- 多工具弱识别 Anderson-Rubin 置信集：过度识别路径能**检测**联合弱识别（联合 F），但唯一的区间是 bootstrap CI——工具联合弱时它失效（正是单工具 AR 要替换的问题），过度识别侧此前没有弱识别稳健集。关键认识：对**单个内生回归元** + q 个工具，AR 统计量仍是 β0 的**二次式之比**（q 维投影只改系数不改代数），故集合仍是一条二次不等式的解、同样五种形态（向量-β 的二次曲面几何只在多个内生回归元时才出现，而过度识别本就单内生）。补上 `anderson_rubin_overid_set`：投影二次型给出 `N(β0)=e'P_Z e`，临界值 `κ=q·F(q,m)`（单工具 `F(1,m)` 的推广），反演 `AR≤F(q,m)` 得 `A·β0²+B·β0+C≤0`，q=1 时**精确**退化为单工具 AR。与恰好识别集不同，过度识别集可为**空**（无 β0 满足全部 q 条矩约束=过度识别拒绝显现在集合几何里）、且 2SLS 点**不必**落在集内。联合 F 弱时 `weak_iv_instrument` gap 指向 AR 集作为 bootstrap CI 的诚实替代；`verify_iv_overid_numeric` 从**同一批**记录矩阵独立重导投影二次型、用验证器自有二次分类器重解、核对 kind+端点+κ+点。仅齐方差 AR·单内生·单 β 标量集（向量-β 二次曲面推迟）。D1=网格反演（闭式集==直接 AR 测试成员）+ q=1 精确退化 + 覆盖率仿真（~96.5%）+ 空集⟺Sargan 拒绝
- 异方差稳健 Anderson-Rubin 置信集（Stock-Wright S / Kleibergen）：上一条的多工具 AR 集是**同方差**的——异方差/聚类下它和 Sargan 一样用错权重（Sargan vs 稳健 Hansen J 的同一缺陷），覆盖率失准。补上**异方差稳健 AR 集**，同时对**弱识别和异方差**稳健：反演 `AR_r(β0)=n·ḡ(β0)'Ŝ(β0)⁻¹ḡ(β0)~χ²(q)`，稳健权 `Ŝ(β0)=(1/n)Σ(yᵢ−β0xᵢ)²zᵢzᵢ'=S0−β0·S1+β0²·S2`（聚类下走 CR0 簇和）。**关键=可验证性**：因 Ŝ(β0) 依赖 β0，AR_r 非二次式之比、集合无闭式——但边界 `{AR_r=crit}` 恰是**一个 ≤2q 次多项式的实根**（`np.roots` 精确且完备不漏根），且 Ŝ(β0)=Σ(非负)²zz' 对所有 β0 PSD → AR_r 处处有限、两侧共享有限渐近线 `L∞=(1/n)zx'S2⁻¹zx`（弱识别信号：L∞≤crit→集合无界）。集合表示为 segments 区间列表（bounded/disconnected/whole_line/empty/union）。联合 F 弱时 `weak_iv_instrument` gap **优先**指向稳健 AR 集；`verify_iv_overid_numeric` 从记录的 S0/S1/S2 独立重导 AR_r，核对每个 crossing 在边界+crit+渐近线+segments，并用**独立密集网格成员扫描**（与生产者精确多项式根不同方法）核完备性防漏根。仅 χ²(q) 渐近·单内生·单 β 标量集。D1=网格反演 vs 闭集 + 异方差覆盖率仿真（**稳健 0.955 vs 同方差 0.855**）+ 空⟺无界渐近线信号 + 聚类 CR0

当前全量测试基线：**2964 passed / 144 skipped**，warning-clean。

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
  claude_skills/ Claude Code Skill bundles (e.g. themis-causal-check), shipped with the wheel
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
- **测试套件**：2964 passed / 144 skipped（2026-07-13）
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
