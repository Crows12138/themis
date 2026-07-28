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
- 暴露误分类矩阵法（Barron/Greenland/Marshall）：测量误差校正此前只做**结局**误分类（Rogan-Gladen），暴露侧被明确推迟。缺口是"静默错误答案"：潜 X*→Y SCM 下把 `misclassification` 按暴露变量名给，themis 静默忽略→照发衰减的 `backdoor_logistic` 点（探针：真值 0.198，朴素后门 0.137，衰减 ~31%）。补上**矩阵法**——非差异（X⊥(Y,Z)|X*）下沿暴露轴对 (X,Y) 联合逐结局列求逆 `p_true(X*,Y|z)=M⁻¹p_obs(X,Y|z)`，再用**恢复的真实暴露**做后门标准化。**关键**：暴露侧分母 P(X*=x|z) 本身也是求逆结果（非观测计数）→**无 naive/det 捷径**，故做独立估计器；恢复暴露边际≤0 时 `degenerate_recovered_exposure` 拒。`misclassification` 按变量名键分派（暴露名走暴露校正，X+Y 都给→组合校正推迟拒）；`verify_exposure_measurement_correction_numeric` 从记录的混淆矩阵 + per-stratum 2×k 联合表**第二次独立求逆**重导校正/朴素点，拒伪造点/非列随机矩阵/篡改联合表/丢层/空臂。仅二值暴露·非差异·已知固定矩阵·离散结局·后门识别；多值暴露/组合(X+Y)/差异矩阵/连续误测(regression calibration/SIMEX)推迟。D1=潜 X* SCM 逐位恢复真 RD（矩阵法 0.197 vs 朴素 0.137 vs 真 0.198）
- 差异误分类矩阵法（differential misclassification）：测量误差校正此前只做**非差异**（各条件层同一矩阵）。缺口仍是"静默做错"：结局误分类**随暴露臂而异**（detection bias）时，用"池化单矩阵"非差异校正把真值 0.30 校到 0.48（误差 +0.18，比不校正的 0.36 更差）——且差异误分类可**朝远离零方向偏**（非差异永远朝零衰减），这正是必须逐层求逆的理由。补上两个规范差异型：**结局侧逐暴露臂**矩阵 M_x（`p_true(·|x,z)=M_x⁻¹p_obs`）与**暴露侧逐结局层**矩阵 M_y（对结局 y 的列用 M_y⁻¹ 求逆，recall bias）。接口 `differential=True`+`confusion_matrices`（对齐 list）+`differential_levels`（条件变量取值，避 JSON string-key 类型坍缩），内部统一成 `Minv_by_level` 字典使代码路径归一。两个 `verify_*_measurement_correction_numeric` 分支 `suff.differential`，从记录的**每层矩阵**+计数/联合表**第二次独立逐层求逆**重导校正点，拒伪造点/篡改某层矩阵（det 不符）/差异标志翻转/层不覆盖全臂或全结局。仅结局或暴露轴差异（**协变量差异**推迟）·已知固定矩阵·离散结局·后门识别。D1=detection-bias 逐臂恢复 0.197 vs 真 0.199·recall-bias 0.198 vs 真 0.195·单矩阵校正显著偏·e2e+verify+四类篡改被拒
- 连续误测（regression calibration）：测量误差校正此前全是**离散**（混淆矩阵求逆），连续误测在 `measurement.py`/`response_rendering.md`/`__init__.py` **三处**明写推迟、留给 `measurement_error_concern` gap 让用户自己做。缺口是"静默错误答案"：连续暴露被经典加性误差污染（观测 W=X*+U），今天最好的做法（W 上的后门 OLS 斜率）把真值 0.8 的每单位因果斜率发成 **0.398（衰减 ~50%）**还标 numerically_solved，且**无任何校正通道**（`misclassification=` 只吃离散矩阵）。补 **regression calibration 精确矩量校正**（Carroll 2006）：经典误差只抬高设计协方差中 W 的方差（Σ_WZ=Σ_{X*Z}+E，E=diag(σ²_u,0,…)），Cov((W,Z),Y) 不变，故真实系数=朴素系数的精确校正 **β_true=(Σ_WZ−E)⁻¹Σ_WZ·b_naive**——离散 M⁻¹ 的连续对应；单暴露即 **βx=b_naive/λ**，λ=1−σ²_u/Var(W|Z) 是**连续版 det(M)**。接口=新 kwarg `measurement_error={暴露名:{error_variance:σ²_u}}`（与 `misclassification=` 平行的载荷性外部输入），暴露侧；结局/组合连续误测**诚实拒绝**非静默忽略。守卫：σ²_u≤0、σ²_u≥Var(W|Z)（退化可靠比）、近离散暴露（指向混淆矩阵法）、奇异设计，全 refuse 不吐衰减朴素点。`verify_regression_calibration_numeric` 从记录的设计协方差+σ²_u **第二次独立**重解 b/β/λ，拒伪造点/naive/reliability、非对称协方差、退化 σ²_u 出点、斜率与协方差不符；derivation 复用既有终端、kernel 按 method 触发（**MCP 数不变**）。仅连续暴露·经典加性误差·**线性**结局·已知固定 σ²_u·数值协变量；Berkson/差异误差·误测结局或协变量·非线性结局（SIMEX）推迟。D1 双 oracle：矩阵形式 0.7982==可靠比 b_naive/λ 0.7982（逐位）·恢复真斜率 0.80 vs 朴素 0.40·五类篡改被拒
- 连续误测扩到误测协变量/混杂：上一条 regression calibration 把误差矩阵 E 硬编码在**暴露列**（E=diag(σ²_u,0,…)），误测**混杂**没有校正通道——又是"静默错误答案"：真混杂 z→x、z→y，只观测噪声代理 W_z=z+U_z，对 W_z 做后门调整留下**残差混淆**→朴素斜率 0.835（真 0.5，高估 67% 且**偏离零方向**，与暴露衰减朝零相反）、标 numerically_solved、`measurement_error={z:…}` 被静默忽略。泛化=把 E 从"暴露列"推广到**设计矩阵任意列**：同一条 `β_true=(Σ_obs−E)⁻¹Σ_obs·b_naive`，E=diag(σ²_u 放在被误测列)。`error_variance` 参数多态（float=暴露 sugar / dict={变量名:σ²_u}），暴露+混杂组合=E 多个对角非零。**误测混杂无标量可靠比捷径**（矩阵求逆必需），每列各报 λ_v=1−σ²_uv/Var(V|rest)；退化守卫升级为 **Σ_obs−E 的 Cholesky 正定检验**（多列时逐列 λ>0 必要不充分）。dispatch 优先选含全部命名混杂的后门集，命名变量不在设计中→`mismeasured_covariate_not_in_adjustment` 诚实拒绝。`verify_regression_calibration_numeric` 从记录的 `error_variances`（名→σ²_uv）按 design_vars 索引**重建 E**（关键：否则用 E=0 重导朴素 β 会误拒诚实校正点），去掉"暴露 σ²_u>0"要求（改为 Σe>0）、校标量 error_variance==暴露对角、逐列 λ 交叉核对。仅连续误测变量（暴露和/或混杂）·经典加性·线性·已知固定 σ²_u；误测**结局**、Berkson/差异、非线性 SIMEX 仍推迟。D1=潜混杂 SCM 恢复真 0.50 vs 残差混淆朴素 0.835·矩量方程残差交叉核·组合 X+Z 恢复·验证器拒伪造点/篡改 σ²_uz

- 协变量差异误分类（differential_by）：差异误分类此前的差异轴**硬编码为暴露臂**（detection bias / recall bias）；混淆矩阵**随一个协变量分层而异**（如误分类率随测量地点/年龄）没有校正通道。缺口除了能力缺失，还藏一个静默 bug：站点 z∈{0,1} 与暴露臂 bool{False,True} **碰撞**，`differential_levels_mismatch` 守卫不触发，逐站点矩阵被**静默误读为逐臂**——真 ATE 0.2004 发成 0.2613（高估 30%）还标 numerically_solved。现在把差异轴从"永远是暴露臂"泛化到**任意命名变量**（新 `differential_by` 字段，与上一条 RC 的 E-列泛化同构）：`differential_by=<协变量>` 时逐后门层按该协变量取值选矩阵 `Minv_by_level`（暴露臂默认路径保持不变）。守卫 `differential_by_unknown` / `differential_level_uncovered`（某观测层无矩阵）。`verify_measurement_correction_numeric` 加协变量分支从记录的逐层矩阵按 adjustment_vars 定位 differential_by、逐层第二次独立重求逆，拒伪造点/篡改层矩阵/differential_by 不符/层未覆盖。仅**结局侧**协变量差异；暴露侧（recall）协变量差异、臂×协变量联合差异推迟。D1=逐站点 SCM 恢复真 0.200 vs 池化单矩阵 0.259

- 协变量差异误分类·暴露侧（differential_by 续）：上一条只闭了结局侧；**暴露侧**（矩阵法）的差异轴此前硬编码为**结局**（recall bias），暴露误分类**随后门协变量分层而异**（如暴露测量准确度随地点变）无通道。同型静默错答+潜藏碰撞 bug：站点 z∈{0,1} 与结局值 {0,1} 碰撞→per-site 矩阵经 by-outcome 通道通过覆盖检查、被**静默当 per-outcome 列求逆**，真后门 RD 0.298 发成 0.324（冲过头）还标 numerically_solved（naive 0.173 严重衰减）。与结局侧同构地给 `estimate_exposure_measurement_correction` 加 `differential_by`（默认=结局/recall；`differential_by=<协变量>` 时每个后门层内用**本层单一 M_z** 对所有结局列求逆）；`_exposure_formula` 统一成按 `differential_axis` 逐列选矩阵。守卫 `differential_by_unknown`（=暴露自身/非结局非调整协变量）/`differential_level_uncovered`。`verify_exposure_measurement_correction_numeric` 加协变量分支从 `confusion_matrices_by_level` 按 adjustment_vars 定位 differential_by、逐层从 z 取值选 M_z 第二次独立重求逆，拒伪造点/篡改层矩阵/differential_by 不符/层未覆盖。仅暴露侧协变量差异；臂/结局×协变量联合、组合(暴露+结局)、多值暴露推迟。D1=逐站点 SCM 恢复真 0.20 vs by-outcome 误读 0.32

- 条件效应在 ADMG 上静默丢 given（止血）：测量误差方向的戏剧性静默错答挖尽后转攻更高价值前沿，4 条并行探针里前门探针揪出一条**戏剧性静默错答**。`scheduler._dispatch_effect` 的 bidirected 分支里 Tian-in-effect fallback **无 `observed_atoms` 守卫**——`identify_via_tian` 只算无条件 do(X)、忽略 given，识别成功就发数标 numerically_solved。故任何非后门识别的**条件**效应查询（前门最典型）静默丢 given、**发边际值当条件值**：`P(Y=1|do(X=1),C=1)` 发 0.545=边际（真条件 0.675），C=0/C=1 报同一个数，且 `themis.verify` 直接崩溃而非拒绝。止血=Tian fallback 加 `and not observed_atoms` 守卫，条件查询**诚实拒绝**（`query:effect_admg_conditional`，reason 明说边际被 withheld）。非 bidirected/后门条件本就正确处理 given。分阶段前沿 Phase 1（纠正性）；Phase 2=条件 general-ID（IDC*）数值端。+2 回归测试

- 条件 general-ID（IDC*）数值端（Phase 2，纠正性完成）：把上一条 Phase 1 的诚实拒绝翻成**正确条件值**。`observed_atoms` 非空时走 `identify_via_idc`（Rule-2 exchange + `ID(Y∪Z_rem,X')/ID(Z_rem,X')` 归一化）+ 新 `bind_idc_values`（target 与 given 两侧绑 Y/Z）+ `_try_numeric`；派生 `idc_rule2_exchange`+`identify_via_idc`+`idc_formula_ast`+`formula_evaluation`+`numeric_result`。验证器泛化 `_rule_identify_via_idc` 接 EffectQuery、加 `_rule_idc_formula_ast` 独立重绑、`_evaluate_formula` 加 FractionExpr 分支、见证清单纳入 IDC。潜变量-SCM 分数条件恢复到 **1e-9**、手算非分数 `P(Y=1|do(X=1),C=1)`=**0.60**（≠边际 0.47）；+2 篡改测试（伪造数值/顶替绑定公式均被独立验证器拒）。顺带堵 `_try_iv_wald_in_effect` 同类相邻静默错答（条件查询带工具+单调性时发无条件 Wald LATE 丢 given）：加 `if q.given: return None` 守卫

- 条件 general-ID（IDC）**data/pandas 端**（Phase 2 声明的 follow-on）：Phase 2 只做 theta 路径，这一档补 **DataFrame** 路径（此前 `dispatch.py:_try_general_id_estimate` `if given_atoms: return False` 诚实 bail=能力缺口）。新 `estimate_general_id_conditional_ate`：两 do-臂各 `identify_via_idc` + `bind_idc_values`，复用无条件路径的 VE plug-in（`ve_estimate_formula` 早支持 FractionExpr），出**层内条件-ATE 对比** `P(Y=y_hi|do(x_hi),Z=z)−P(Y=y_hi|do(x_lo),Z=z)`（镜像无条件 data 路径出 ATE）。验证深度**对齐无条件 data 路径**：泛化 `_rule_general_id_criterion` 按 `ctx.query.given` 路由（有 given→重跑 `identify_via_idc` 确认可识别=安全关键，conditioning 读自 query 防低报绕过），method 枚举加 `general_id_idc_plugin`；plug-in 算术是共享的 data-refit 天花板（元数据审计）。D1 双 DGP 落为数据：效应修饰图恢复 ATE(C=1)=0.30/ATE(C=0)=0.18/边际=0.24 三者皆异；潜-SCM 分数端恢复 0.375。+14 测试

- K-treatment 联合干预**数值端**（2026-07-16）：联合 `do(A,B,C,…)` 此前分层不对称——结构层 `minimal_adjustment_sets_joint` 本就支持任意 K，但数值层硬锁 exactly-2（K≥3 静默 no-op=结构证到、数值给不出的诚实缺口）。`estimate_joint_effect` 泛化：结局回归纳入**饱和 treatment 交互基**（所有非空子集乘积项，K=2 即 `[A,B,A·B]` 字节级等价），交互泛化为 **K 阶最高阶混合有限差** `Σ_s (−1)^{#lo(s)} μ(s)`（2^K 角点交替求和，湮灭所有 <K 阶项，隔离最高阶交互）；`interaction.order`=K 入 schema。**验证器零改动**（两条 joint 规则本就 atom-set·K-agnostic）。取舍：二值·K≤5·只报最高阶交互·latent 联合仍诚实拒绝。D1：K=3 真 3-way 恢复对比 5/交互 2；anti-silent-wrong=有 2-way 无 3-way 时 3 阶交互恢复 ~0；K=4 恢复 5.5/1.5。+14 测试

- joint **ADMG/latent** 调整（2026-07-16，K-treatment 续）：联合前沿第二半。`minimal_adjustment_sets_joint` 此前 `if bidirected: raise NotImplementedError` 拒 latent（能力缺口）。把广义（treatment-SET）后门/调整准则从 d-分离**广义为 m-分离**（van der Zander 2019 / Perković 2018）：proper back-door graph 阻断检查按 bidirected 路由 m-分离/d-分离（**DAG 路径字节级不变**）。**关键洞察=联合干预中和 latent**：`Z→{A,B,Y}, A→Y, B→Y, A↔B` 里 G_pbd 移除 A→Y/B→Y 后 A↔B 后门路被 collider B 阻断→`{Z}` 有效，而单 do(A) 需 `{B,Z}`——集合准则≠单处理准则之并。数值端零改动（有效调整集喂 `estimate_joint_effect`，g-formula 在 latent 下无偏）。**soundness 非完备声明**：只覆盖可调整识别子集；ID-可识别但非调整-可识别（前门/c-component for sets）诚实拒绝，联合 general-ID 留 follow-on（ID 引擎内部本就集合式）。D1：潜 SCM（U→A,B=A↔B）恢复真对比 4.02/交互 2.02；A↔Y 无调整集诚实拒绝；篡改丢 Z 被 m-分离重导拒。+8 测试

- 反事实单格**数据端**（2026-07-22）：theta 端刚重建的一致性恒等式，现在也能吃 DataFrame——四个观测格用经验频率、被问格子真正依赖的**那一臂** do-风险用后门标准化，喂进**同一个求解器**（公式不再转写第二遍；先把「二值联合 + 后门 do-风险」抽成 `estimation/binary_do_risk.py` 与 PN/PS/PNS 估计器共用，两边各自只剩自己那条定理）。数据端多出来的两样：**抽样不确定性**（点给百分位 CI，区间给区间自身的外带）和**单调性推翻率**（求解器在空可行集时报拒绝，跨 bootstrap 的被推翻占比 = 这条「不可检验」假设离被数据推翻有多近，theta 端表达不出来）。`interventional_risk_provenance` 五值全部可复核——`not_required` / `pinned_by_monotonicity` 声称「没用干预风险」，验证器自己重算这两条理由成不成立。取舍：二值·须干预被观测的同一变量·do-风险只走后门。D1：两扇门在同一份 DataFrame 上逐位一致（1e-12）；**真值 oracle 是数生成器的潜在结果**而不是再跑一遍恒等式；构造「另一臂有 positivity 空洞」的数据坐实只取被依赖的那一臂。+32 测试

- 反事实单格的干预风险接上 **general ID**（2026-07-22）：跨世界的格子消费一臂 `P(Y=1|do x')`，此前它只能来自后门调整集或随机实验——没有调整集就等于没有风险，这一格于是只在单调性把它整个钉死时才答得出。但「没有调整集」不等于「不可识别」：general ID（c-factor 分解）能到达任何协变量集都表达不出的估计量（潜混杂下的前门结构就是最干净的例子：调整可证失败、ID 可证成功）。回退是纯加法——后门优先（有调整集时逐字节不变），后门失败才试 ID，ID 也失败才落回单调性。provenance 多出 `general_id_plug_in`，并且和其余五值一样**是可复核的断言**：验证器重算「确实没有可容许调整集」，再对 `ctx.query` 问的**那一臂**重跑 ID，把自己导出的估计量与记录的逐节点比对——**算了另一臂却当成本格上报**是会静默给错答案的真实故障模式，这一步正好抓它。取舍：IV 识别的风险未接（Wald 比是 ATE 不是单臂风险）·估计量条件到的每层须有支撑。D1：真值 oracle 仍是数生成器的潜在结果；三类篡改各因该抓的原因被拒且原因钉进测试。+11 测试

- 中介**块**对披露层是瞎的（2026-07-22，修复型）：同一张图、同一个查询，问单个中介时人看的输出带两条识别假设 caveat，换成中介块后**一条都没有**。根因是缺口层的生产者绑在 `extensions.mediation_decomposition` 这个单中介专用 key 上，而不是绑在「做了中介分解」这件事上。归一化成一个 `_mediation_view`，四处漏一起闭：识别假设 caveat 完全不出（最重——「可识别」读起来成了无条件的，而块的前提与单中介严格不同）、调整集谓词不进「查询相关」集导致协变量上的 `llm_proposal` 边逃过披露、数据需求永不列出、静默跳层的诚实 gap 只认单数字段。另加同源两处：数据端联合估计算了中介比例却不出 headline；`mediators` 只写一个中介时两条路由都不接，**整个中介分析被静默跳过且无任何信号**（集合就是集合，一个元素也是）。D1：五条新测试先在改前代码上跑成红的；核心不变量是 parity——问块与问单中介必须披露同样的东西。+6 测试

- 条件工具变量接上 theta 端（2026-07-25）：`iv_sets` 一直会返回**条件**（Brito-Pearl）工具变量——Z 只有在 W 被固定之后才是工具——identify 路径一直照实报，DataFrame 路径也一直用 2SLS 吃 W；只有 theta 端一见条件集就 `return None`。于是同一张图，identify 说「可识别，用 z 在 w 之下」，effect 带着完整 theta 回「backdoor / front-door / Tian ID 都到不了」，只字不提工具变量。补上**分层 Wald**：W=∅ 是同一套算术的单层退化（边际答案逐字节不变），层权按链式法则展开；聚合是**比值的平均而非平均的比值**——每层按它自己的 complier 份额加权（那正是分母项，Abadie 2003），得到的才是 complier 平均因果效应，把各层 LATE 按 P(w) 平均是另一个估计量，测试把两个数都算出来钉住。`treatment_shift` 顺带成为报出来的 complier 份额。第二半是说清**为什么给不出数**：`None` 不携带信息，于是「没声明 monotonicity」「theta 少一格」「一阶段退化」全塌成「这图没救」；现在各自点名，并排追加在结构项旁边——**「有可用的 IV 逃生通道」不等于「可识别」**，顶替掉结构项会让区间答案被当成点识别（第一版正是这么写的，被回归抓住）。验证器不复读：就地重验 (Z,W) 真是工具（抓「算了边际 Wald 却把 W 记成 ∅」）、从 theta 的域重新枚举层（抓少记一层）、按比值的平均重算聚合。取舍：处理与工具须二值·条件**查询**仍归 IDC·theta 查表不走边缘化回退。D1：16 条新测试全部先在改前代码上跑成红的；前提先证后证结论；四类篡改各因该抓的原因被拒。+16 测试

当前全量测试基线：**3607 passed / 144 skipped**，warning-clean。

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
- **测试套件**：3607 passed / 144 skipped（2026-07-28）
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
