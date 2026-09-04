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
- 怎么读 `themis_run` 返回的 envelope（`investigation_requests` / `data_gap_report` / `bounds_results` / numeric)
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
from themis import run, apply_patch_and_run, estimate, audit

out = run(program)                           # 主入口：JSON/dict → JSON/dict
out2 = apply_patch_and_run(program, [bundle]) # 多轮补录闭环
estimated = estimate(program, df)            # 有数据时的旁路估计
audit(program, out["results"][0])            # 独立复核：适用的每一项各跑一遍
```

`audit` 之下是 13 个 `verify_*` 公开出口，直接点名调用也支持（MCP 就是这么做的），
但那样「哪一项适用于这份结果」就归你判断：其中 5 个审的是**独立产物**而不是
`query_result` 信封，拿错了会用**和「没通过」完全相同的异常**拒绝你，而 `verify`
对没有推导链的结果是明确拒答而不是默认放行。每一项审什么、什么时候适用，写在
`themis/audits.py` 一张表里。

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
- 在有数据时通过 `themis.estimate(...)` 给出 backdoor / front-door / IV（含 Anderson-Rubin 弱工具稳健置信集，工具再弱也有效、并如实返回无界集）/ mediation / dose-response / 通用-ID / 近端 proximal / PN·PS·PNS 归因概率（Tian-Pearl，单调下点识别 + 无假设界）/ 反事实合取 / 删失结局的 RMST（Kaplan-Meier 限制平均生存时间之差，逐层标准化）的数值估计
- 在不能给点估计时生成 `data_gap_report`，告诉用户还缺什么数据或假设
- 假设账本上区分「可检验」与「这一次检验过」：一条前提如果本次真的拿数据核过，那一行直接写出结论（`checked.verdict` = 成立 / 没被否决 / **被这批数据否决**）和跑的是什么检验（逐层两臂计数 / 拟合倾向分带外份额 / Sargan / 稳健 Hansen J / ACR 边际权重），被否决的行排在同级最前。同一条前提有强弱两个见证人时，**通过值多少由见证人决定**：逐层计数就是那个条件本身，通过即「成立」；拟合只是估计它，通过最多算「没被否决」。判决必须能从信封里的证据重算，`verify_assumption_ledger` 用自己的一套 reader 双向核对——既拒夸大，也拒「跑了检验却在那一行只字不提」
- 靠拟合模型下的判断，通过那一面也留痕：重叠（`fitted_overlap`）与准分离（`outcome_saturation`）现在把带外份额、拟合概率范围、判定阈值一起写进 `numeric_estimate`，**不论落在判定线哪一边**——缺口天生只在出错时抬头，只有缺口的话，「查过、没问题」和「压根没查」在信封上是同一句话。缺口本身改成对这份记录做算术，所以缺口清单与假设账本不可能对同一帧给出两种说法
- 通过 workflow / prompt / KB / MCP 层，把 NL 输入、补录、验证、估计串成可组合流程
- `themis.build_analysis_report(result, program=...)` / MCP `themis_report`：把一次分析（问题 / 因果图 + 边来源 / 答案 / **验证状态** / 假设账本 / 数据缺口）确定性组装成一份中文 Markdown 报告——无需 LLM / API key，前置突出 Themis 独有的「验证 + 还缺什么数据」
- 前置数据诊断：`themis.estimate(...)` 会把每个变量**声明的测量尺度**（`scale` = binary/discrete/continuous，或枚举 `domain`）与**实际数据列**核对——声明连续却只有 2 个取值、或声明二元却 5 个取值，都作为 `declared_type_data_mismatch` 缺口当场提醒，避免闷头算出一个答非所问的数；证据记进 `extensions.type_reconciliation`，由 `verify_type_reconciliation` 从充分统计量独立重导判决。未正向声明的变量不检查（"没说" ≠ "说了连续"），一致的程序完全静默
- 因果发现 + **发现层首个逐数验证**：`themis.estimation.discovery` 有 PC/FCI/GES/GRaSP/LiNGAM 五个整图学习器（causal-learn，输出为待人工审的建议），另加 `markov_blanket(data, target)`——用 grow-shrink 到不动点找目标的马尔可夫毯（局部屏蔽集，供**筛变量建 DAG**，非调整集）。按数据类型分派：连续用 Fisher-Z（充分统计量=相关矩阵）、离散用卡方（充分统计量=稀疏联合列联表）；两条路径下 `themis.verify_markov_blanket(...)` 都能从记录的充分统计量**独立重算**完备性/最小性定义、拒伪造或裁剪的毯（混合连续+离散类型报错，未做）
- 选择偏倚数值端（§S9.1）：样本被限制在选择对撞上时，普通后门会算出**悄悄有偏**的数——`themis.estimate` 不再吐它。若给了外部无偏参考数据 `reference_data=`，则按 Bareinboim-Pearl 选择后门公式（定理3.5）从有偏样本 + 参考权重算出**恢复后的 ATE**；否则明确拒绝并点名所缺的外部数据（真选择对撞下这些权重永远无法从有偏样本本身估出，故外部数据是硬需求，非可选）。`themis.verify_selection_recovery_numeric(...)` 从记录的每层计数 + 权重表独立重跑公式核对（二值处理 + 离散调整集）
- 中介 four-way 验证器强化：差值尺度分解 `four_way_decomposition` 现在把它本就是闭式函数的六个标准化 cell means 记为**充分统计量**，`verify_mediation_numeric` 用 VanderWeele 14.1b 的独立转写从中重导每个分量，连**完全自洽的伪造**也拒（对标 four_way_ratio 锚定拟合系数）；线性结局下同一组 cell means 也逐位钉死 NDE/NIE，logit 结局下 NDE/NIE 来自蒙特卡洛积分故保持不变量级（诚实天花板）
- 缺失数据 recovered-ATE 数值验证器（§S9.2）：`estimate_recovered_ate` 的数挂在无 derivation 的 `needs_investigation` 结果上，derivation 门控的 `themis.verify` 够不到它——过去伪造 point 无人审。现在估计器把 g-formula 求和所用的每层充分统计量（conditional `{z,arm,n,y_sum}` + marginal `{z,count}`）记进 `recovered_ate.sufficient_statistics`，公开验证器 `themis.verify_missing_data_numeric(result)` 独立重跑 `Σ_z (E[Y|1,z]−E[Y|0,z])·P(z)` 核对 point、朴素对照、归一与丢层，拒伪造 point 或篡改层（MCP 新增 `themis_verify_missing_data_numeric`，13→14）
- 过度识别 IV + Sargan 检验（候选 F）：IV 层过去硬锁单工具，图里两个合法工具只用第一个、默默丢弃其余、也从不做过度识别检验。现在同一 conditioning 下 ≥2 工具走**过度识别 2SLS**（`estimate_iv_overid`）并跑 **Sargan (1958) 过度识别检验**——**小 p 值反驳工具集的联合有效性**（数据能否证伪工具集，是线性/连续版的 Balke-Pearl 工具不等式，孟德尔随机化的杀手场景）。派生终端做结构许可，`verify_iv_overid_numeric` 从记录的残差矩阵独立重导点 + Sargan J + p 拒伪造；Sargan 拒绝时挂 `overidentification_rejected` gap。单工具路径逐字不变（异方差稳健 Hansen J 见下条）
- 测量误差混淆矩阵求逆（候选 E）：测量误差过去只有定性 gap 警告（`measurement_error_concern`：识别路径有自报/问卷/单次测量→挂 ⚠"估计有偏"），估计层零校正——即便用户手握验证研究的误分类率也反解不出真效应。现在被误分类的**离散结局**给定验证过的混淆矩阵 M，在**非差异误分类**假设下逐后门层求逆 `p_true=M⁻¹p_obs` 恢复真分布并做后门标准化（二值即 **Rogan-Gladen 1978**，整体=naive/det(M)，det=Se+Sp−1 衰减因子）。接口 `estimate(misclassification={outcome:{confusion_matrix,states}})`，混淆矩阵是载荷性外部输入（噪声数据本身识别不出），拒奇异/非列随机矩阵、拒非后门识别，refusal 记 estimator_failure 不悄悄吐衰减朴素点；`verify_measurement_correction_numeric` 从记录的矩阵+每层值计数**独立重新求逆**重导校正/朴素点拒伪造点、篡改矩阵、丢层、缺臂。仅结局误分类·仅非差异·矩阵视为固定（暴露误分类/差异矩阵/连续误测仍属 gap 领域）
- 非二值处理 Manski 自然界限（候选 C）：partial-identification（bounds）层此前对**非布尔处理**整层跳过——调度器顶部 `if not intervention_is_bool: return` 把多值处理（如 `do(dose=2)`）连无假设的 Manski 下限都挡掉，尽管单臂自然界 `P(Y=y|do(X=x)) ∈ [P(Y=y,X=x), P(Y=y,X=x)+P(X≠x)]` 与处理基数无关（这是"门控非数学"：数值算术早已对，符号层却吐废字符串、验证器硬门拒审）。现在解顶层门（BP/MTR 当时仍各自门控在布尔——多值落到无假设 Manski 地板；**BP 那一道已在候选 G 拆掉**，见下）+ 新增处理侧离散门（未声明离散域的连续点干预不挂平凡 `[0,1]`）；符号补臂对多值渲染为汇总不等式 `P(X≠x)`（布尔仍 `P(X=¬x)`）；数值层记录三个臂计数作充分统计量，`verify_manski_natural_bounds_result` 从记录计数**独立重导** lower=n_joint/n、upper=(n_joint+n_other)/n + 臂划分不变量（把 Manski 数值端从仅元数据审计升级为强重导——多值汇总补臂质量元数据审计验不出伪造宽度，重导能）。仅 Manski 自然界·多值处理 MTR/Balke-Pearl（二值构造）与多层对比界推迟

- 任意基数 Balke-Pearl 界（候选 G）：Balke-Pearl 此前三处闸门都问「是不是二值」，第四处 `_detect_iv_candidate_structural` 更是直接要求工具的声明域 `== {True, False}`。**根因是 `16` 被写死成两张四元组查找表**（生产者一份、验证器独立誊写一份）：响应函数模型本来是「X 是 z→x 的映射、Y 是 x→y 的映射」一句话，类型数 `|X|^{|Z|}·|Y|^{|X|}` 是它的推论，写死之后基数从模型的参数变成了前提。实测代价不是「没有退路」（Manski 地板一直在），而是**非二值时工具变量的全部信息被丢掉**——三值处理宽 6.2 倍、三值结局 3.7 倍、**三值工具**（X/Y 都二值！）3.7 倍。现在类型表由基数生成、约束矩阵按基数缓存；**估计量随之改成查询问的那条臂** `P(Y=y|do(X=x))`——ACE 要二值结局才是概率之差、要二值处理才有基准臂，推广不下去，而单臂在任意基数下都是同一族类型分布上的线性泛函；ACE 在有基准臂时以具名 `contrast` 另发一对端点（Vitamin A 的 −0.1946/0.0054 逐位不变）。平价验证：300 张随机二值表上广义 LP 与原 16 型 LP `max|diff|=0`、56 次拒答完全一致。算力上限 `MAX_RESPONSE_TYPES=10000`，超限**不静默**——落回 Manski 地板时 notes 说明「更紧的方法因尺寸被放弃」并给出算式。验证器独立誊写广义 LP，`sufficient_statistics` 必带三条水平表与两个臂下标（2×3×2 的表被当成 3×2×2 读会重导出另一个区间），`contrast` 按自己的目标函数重导。顺带补上：`estimand` 字段此前**零个读者**，两个读者面都只打两个数和方法名——现在都说出这个区间是关于什么量的。取舍（声明）=多值处理仍无 ACE（没有基准臂）·MTR 仍是二值处理构造·BP 与 MTR 争同一槽位时由 if 链顺序决定（#358）
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

- 反事实单格的干预风险接上 **general ID**（2026-07-22）：跨世界的格子消费一臂 `P(Y=1|do x')`，此前它只能来自后门调整集或随机实验——没有调整集就等于没有风险，这一格于是只在单调性把它整个钉死时才答得出。但「没有调整集」不等于「不可识别」：general ID（c-factor 分解）能到达任何协变量集都表达不出的估计量（潜混杂下的前门结构就是最干净的例子：调整可证失败、ID 可证成功）。回退是纯加法——后门优先（有调整集时逐字节不变），后门失败才试 ID，ID 也失败才落回单调性。provenance 多出 `general_id_plug_in`，并且和其余五值一样**是可复核的断言**：验证器重算「确实没有可容许调整集」，再对 `ctx.query` 问的**那一臂**重跑 ID，把自己导出的估计量与记录的逐节点比对——**算了另一臂却当成本格上报**是会静默给错答案的真实故障模式，这一步正好抓它。取舍：IV 识别的风险未接（Wald 比是 ATE 不是单臂风险）——**这条仍成立，但它挡住的那件事已经从另一条路走通**（见下条）·估计量条件到的每层须有支撑。D1：真值 oracle 仍是数生成器的潜在结果；三类篡改各因该抓的原因被拒且原因钉进测试。+11 测试

- 反事实单格接上**工具变量的响应函数多面体**（2026-08-12，#322）：同一个程序、同一份 DataFrame、同一个工具变量，effect 门拿到 Balke-Pearl 区间`P(y=1|do(x=false)) ∈ [0.2434, 0.4723]`，counterfactual 门却拒答「那一臂后门与 general ID 都识别不出来」——**拒答理由正是隔壁门刚刚括起来的那个量**。根因：级联的终止条件写成了「能不能**点**识别」，而更深一层，一致性恒等式把干预风险当**一个标量**吃进去，工具变量给的却是**一族联合分布**。现在多一条路线：单格分子 `P(Y_{x'}=y*, X=x[,Y=y])` 是同一族响应型分布上的又一个线性泛函（分母被观测表钉死，所以仍是纯 LP），**这是 #320 那个多面体的第三个目标函数**——那次把基数变成参数，这次把估计量变成参数（Balke & Pearl 1994, UAI）。**便宜路线被实测排除**：先用 BP 框住那一臂、再把两个端点代回恒等式，是有效的外界但更宽——400 个随机二值 IV 模型里它只在 **46** 个上给出非平凡区间，直接优化给 **133** 个（最悬殊一例：直接 [0.9207, 1.0]，两步 [0, 1]）；中位宽度比 1.000，所以判据是**「有多少情形从有信息变成没信息」而不是平均宽度**。而且两步并不更省——同一个多面体，只有目标向量不同。声明的单调性作为**类型空间限制**进 LP（不是另开公式，否则这里会成为全仓唯一一处静默丢掉调用方已声明假设的地方），并因此换来一个新的反驳通道：带限制不可行、不带限制可行 = **数据推翻了这条单调性**，与「工具被推翻」分开报。验证器独立誊写多面体上的单格目标（坐标与单调性一律读 query）、从图上重导 Pearl 判据确认那一列真的是工具变量且唯一、并要求记录的 `P(X,Y|Z)` 边缘化回信封另一处的四格联合。取舍（声明）=只做数据端（多面体在 `estimation/`，`runtime`/`output` 不 import 它，θ 端要先能从 theta 取出 `P(X,Y|Z)`，#359）·两个合法工具时不答（挑一个是在悄悄回答更窄的问题）·`|Z|` 过大按名拒答不静默回退·同一个 PN 走 `causation` 门仍拒答（新的跨门不对称，并入 #321）

- 注释被允许假设读者当时也在场（2026-08-12，dsh 借鉴，#360/#361）：判据抄自 DeepSeek Harness 的 `dsh-trim-cot-leakage`，只有一句——**HEAD 处一个没有会话记录、没有 PR 讨论串、没有未提交草稿的读者，能否解析每一处引用、验证每一条断言**。拿它扫本仓：**465 处 `iter NNN`、61 个文件**，而全仓唯一带这些序号的 `wall.md` 只覆盖被引用的 143 个里的 **59** 个。根因是注释总在一次会话里写、会话有序号而代码没有，于是「哪次做的」被当成「为什么」的一部分——它在写下的当下是真信息，在 HEAD 上是死引用，而**从写下它的那个文件内部看，死引用和活引用长得一模一样**。判据的价值在它拒绝定罪的部分，所以反向边界与判据并列写出并由测试钉住：自带解析目标的引用留下（`wall.md iter 150` 留、裸 `iter 150` 不留——号码从来不是问题，缺的是指针）、反事实回归钉留下、带出处的度量留下、外部文献留下。每一处是**改写不是删除**：时间戳去掉，交叉引用留缺陷去号码，变更叙事改成它本来在描述的**现在时危害**（「以前用的是 `state.x`」只能被相信，「在这里读 `state.x` 会……」可以被构造）。两处按会话组织的 docstring 连组织原则一起重排。**这一遍照出读一遍照不出的东西**：一个会话序号印在一句用户可见的中文消息里；一条限制声称并行多中介无解，而解它的兄弟函数**就在同一个调用者手里、几行之上**；一个 helper 仍把已落地的推导写成未来计划——三处都因为**被包装成历史**而活下来。门禁只守可判定的那一个子类并说明为什么只守这一个，它抓到两样 grep 抓不到的：一处**跨行折断**的引用，和一条只断言号码、不断言指针的测试。同时把**被度量定下来的决定的数字挪到决定旁边**（#360）：两步反事实路线 46/400 vs 133/400、塌缩结局 240 张表里 154 张对不上（最大差 0.323）、交接不变量按字面执行会打断 81 条正确路径——**一个没有度量的被拒备选是一句断言，下一个读者有权重新提出它**

- 纪律只到达了那个唯一可枚举的面（2026-08-12，dsh 借鉴，#362）：一个封闭词表写在一处、被重述到每个要读它的面（schema / prompt / 参考表）。浏览器那一面守得很好——锚在 kernel 一侧，且强制 `verdict.ts` 里每张表自报是不是词表；**其余的面靠三十来条 pin，每一条都是某次漂移已经发货之后才补的**。根因不是忘了推广：浏览器那条能成立是因为 `verdict.ts` 把表声明成 `const NAME: Record<...>`——**有一个集合可供 partition**；prompt 是散文，没有声明单位，形状搬不过去。**分界线正好落在「这个面还能不能被枚举」上。**修法是把枚举的一侧翻过来：25 个封闭词表各说出它到达哪些读者，21 个锚在 schema 的 enum 站点上逐字相等（用**具名站点的相等**而不是「在并集里」，因为 schema 承认而 kernel 从不发出的取值读起来像「有人处理过」；用**一组站点**而不是一个，因为单格能声明的许可不等于 causation 块能声明的——那正是 #336），4 个写下「为什么没有 schema 说它」。partition 逼出那 4 个从没表态的。**它还照出手写义务值多少**：钉 `gap_to_action.md` 的那条 pin 手列 4 个估计器时段 kind，而那组有 6 个，**漏的两个恰好就是 prompt 里没有的两个**——清单是照着prompt 已写的抄的，**它拿 prompt 验 prompt**。那一组现在被声明出来，prompt 也补齐。同时把上一档的散文门禁从 `.py` 扩到 prompt 与现状文档（**排除项连同理由写在模块里**），又抓到 16 处序号和**一整个搬走的目录**（15 处 `docs/prompts/`，其中两处在告诉读者 web bridge 加载哪个文件）

- 组件说的话也归读者的语言管（2026-08-22，#390 档⑥b）：17 个组件 + `App.tsx`
+ `api.ts` 的 **181 行**单语文本拿到第二门语言，浏览器单语读者面行数
**193 → 12**。**先定接缝 `useLang()`**：语言怎么到达组件，各处 import
`DEFAULT_LANG` 也能跑，但那样档④ 的开关是 17 个文件的改动，而那一刻的压力会是
「把 lang 当 prop 一路穿下去」；把**问题**命名在一处，档④ 就在那一处回答。
边界随之清楚——**组件里用 hook，纯模块里用参数**。**转换时撞见一件事**：答案
三档的词有**三个作者**（`TIER_META` + 页脚图例 + 侧栏），且两个副本已漂
（`点` vs `点估计`、`能算出` vs `可以算出`）；**一份重复的正确修法不是翻成两份，
是让它别再是重复**——两处改成读 `tierMeta()`。这是 #394 往上一层：kernel↔浏览器
的复述有闸口，浏览器↔浏览器的**没有锚点**。**错误消息分三种只有一种是我们的**：
`KernelError` 多带 `words`，`errorText(e, lang)` 是本文件措辞的 / 服务端措辞的 /
平台抛的三者相遇的唯一一处；`DagBuilder.serialize()` 同形，五条校验消息返回
`{refused: Words}`——**校验跑在没有读者的地方，消息读在有读者的地方**。**带强调
的句子拆成部件**（强调在另一门语言里落在另一个词上），列表分隔符 `、` vs `, `
属于句子不属于数据。**不该被语言碰的留在外面**：`ROLE_META.cls` 是样式名、
`citations()` 不收 lang（翻译论文标题是另一个断言）、集合花括号留在槽位值里。
剩下 12 行各自是一个**未答的问题**而非欠的翻译，都已登记，都不靠新开豁免名单。
**顺带修掉三条钉拼写的判据**（两红一潜）：一条找精确调用串、一条用中文串的字节
位置代表渲染顺序、一条 `"依据文献" in component` 没红但已不说它要说的事——根因
同一个，**语言层把读者面文本提到了文件顶部的表里**，于是文本的位置不再是渲染的
位置、文本的存在不再是那一节的存在。改成**钉渲染点而不是拼写**

- 闸口的分母停在了语言边界上（2026-08-21，#390 档⑥a 收口）：`verdict.ts` 的
词表与句子全部拿到第二门语言、全绿，而旁边 `Verdict.tsx` 的 34 行中文从没被
问过。**根因是分母跟着实现手段走**——语言闸口那半边扫描建在 `ast` 上，于是
分母是 `themis/**/*.py`；「用什么读」是关于读者的事实不是关于主体的，而
**分母停在语言边界上时，它报的是「一个面的完备度」，读起来却像整次构建的**。
不是补一张浏览器名单，而是让分母是「读者面」：`_reader_facing_ts` 吐出与
Python 半边**同型的五元组**，`_owed` 与完备性那一臂各接上，两个既有测试
一字不改。这一面的语言由**在不在一个 `Words` 里**裁定（`words_literals`
读，其覆盖面已被另一条闸口钉住），是那半边「文本的语言写在它旁边的键上」
往上抬一层。**单位是行不是字面量**：JSX 文字根本不是字面量，按字面量数会把
整篇中文的组件报成几乎没欠；代价是同一行上「该翻的词」与「不该翻的数据」
共存时要一起等。`STILL_ONE_LANGUAGE` 多出 20 行 **193 条**，计数不是上限、
只能减。反例两个都真红：加一行中文（8→9）、把 `Verdict.tsx` 摘下表（立刻
点出 `aria-label="判决"`）。**顺带撞红另一条闸口而且红得对**：17 个 `.tsx`
被报成「路径不存在」、名字少一个 x——`_PATH` 的扩展名交替里 tsx 就写着，
但**正则交替最左优先而非最长匹配**，`ts` 在前于是永远只吃到 `.ts`。挪一下
今天能绿，下一个同型组合却不会红、只会静静地少匹配（分母又悄悄变小）。
改成两个机制：正则说「路径到哪里结束」，**集合**说「哪些结尾算我们的」

- 剩下的渲染器与 8 行数据（2026-08-21，#390 档⑥a-3/a-4）：14 个数值细节渲染器
+ 纵向/θ 三个辅助 + `causation`/`scm_counterfactual` 两个答案渲染器 +
`estimateMeta` + `structuralReadout` + 反事实单格问句 + 推导链/答案两张行表，
单语读者面行数 **188 → 8**。`DetailRenderer` 收**两个必需参数**而非块渲染器
那个具名对象（它们拿的是装着这个数的容器，没有 `ext` 也没有 `ciLevel`）。
**`fill` 的槽位类型不收 `undefined`，逮到一个原来就在的缺陷**：9 处被替换掉的
模板串会把 `undefined` 这个词印给读者，修法是 `?? '?'`（本文件既有约定），
**不是放宽 `fill` 的类型**——放宽等于把「洞印在页面上」换个形式再犯。剩下
8 行是一簇，登记 #400 不翻译：`FRAMING_FIELDS` 的 `def` 同时是给读者看的字、
身份标记（消费方 `.includes('未指定')`）、和**真正写进 program 的值**，变成
`Words` 等于让存下来的数据取决于浏览器当时是哪门语言；它还有第二个作者
（`themis/web/app.py` 的 `_FILL_DEFAULTS`），两边无人要求一致。理由写进了
源码而不只是这里

- 路线渲染器没有一个槽位能让读者的语言到达（2026-08-21，#390 档⑥a-2）：
`verdict.ts` 的 12 个词表查询早就收 `lang`；写这些词**周围那些句子**的渲染器
一个都没有，而且**没地方放**——`ROUTE_RENDERERS` 是分派表，渲染器的签名就是
表的类型，语言加不进其中一条。**与档⑤ 在 `analysis_report.py` 遇到的同形**
（那次给五张表配 Protocol）。TS 能直接写函数类型，修法更小，但顺带照出：
**路线表把契约写在行内、答案表写成了 `BlockRenderer`**，行内那份少一个参数，
于是第四个参数成了「三个没人用的位置参数 vs 第二份契约」的二选一。现在一份
契约、具名对象 `{ ext, lang, ciLevel? }`。**`ciLevel` 保持可选是查过的**：
两个装因果概率的容器**形状不同**——`blockRows` 那条是 `causationQuantity`
（`{lower,upper,point}`，`additionalProperties:false`，schema 旁边写着「两个
写入者从没产生过采样带」），`answerRows` 那条带 `ci_lower/ci_upper` 且确实传
了 `num.ci_level`；**没有 CI 水平可给的路靠「不给」说出这件事**。63 条文本变
`Words`（一渲染器一张表，让渲染器和它说的话待在一起）。**变量名/数字/公式保持
裸的**——那是数据，第二门语言对 `${b.instrument}` 的改变是零，这也是让计数诚实
的东西；`${b.latent}（取 k 个值）` 因此成了**一条带两个具名槽位的 `Words`**
而非拼接。单语读者面行数 **251 → 188**。

- 浏览器的语言层只造了「词」那一半（2026-08-21，#390 档⑥a-1）：kernel 的
`language.py` 给三个查询——`say`（词）、`gloss`（信封上读回的取值）、
`fill`（句子，`Words` 带**具名槽位**）。浏览器只镜像了前两个。于是
`verdict.ts` 唯一一条带洞的句子就地发挥：`say` 取文本 + `said.replace(
'{factor}', …)` 填洞——**调用点的名字和文本里的名字是两个必须碰巧一致的
字面量**，不一致时读者拿到页面上印着的 `{factor}`；`say` 的回退让另一半也
是静的（缺语言时渲染标识符而不是报错）。**根因是契约缺了一半，不是那一处
写错**——现在修是因为档⑥ 还有 **82 条带洞的句子**要上这个面，每条都能自己
长一个 `replace`。`fill` 逐字镜像 kernel，**连两条拒绝一起**：只认具名槽位
（洞的意义若是位置就挪不动，而两门语言不同意位置——这正是句子不能是模板
字面量的全部理由）、两种缺洞都抛（句子没有 identifier 可退；没人填的槽位会
以 `{name}` 到达页面）。两条闸口：**查询清单从 kernel 上读出**而不是手列
（要点是**缺一个的面不会失败，它会即兴发挥，而即兴在源码里看不出来**）；
禁止在 `src` 下用 `String.replace` 填具名洞，反例照真实那处的写法造。

- 复述的边界写在条目的形状里，不写在一张名单上（2026-08-21，#393/#394）：
浏览器 20 张词表复述 kernel，两种语言下 220 条串。先量边界：**15 张逐字复述
（220 对，修完后零差异，另 4 对只差 `**` 强调）、3 张是浏览器自己的渲染、
2 张 kernel 故意不发词**。量的过程中撞上 #394——只钉键集的两张表已漂：
`c_factor` 的中文少了「分解」，它和 `ace` 被重打时全角括号成了半角。
根因不是打错字，是**文字钉子按表逐个手写**：四处（两张名单 + 一个独立函数 +
`test_risk_provenance`）共盖 18 张可比表中的 8 张，**没有一条规则说「每张表
都必须被钉住」**，漂的两处就在没人看的那 10 张里。**这是本模块 docstring
早就为「键」那一层写下的同一个诊断在下一层重演——一个靠枚举来覆盖的修法，
会把它下面那一层也留成枚举的。**修法：文字检查与键检查共用 `ANCHORS` 这个
分母，三张名单删掉；**豁免从条目形状读出来**（裸 `Words` 是 kernel 的词，
结构化条目是自渲染），再用等式把结构化集合钉死，使豁免藏不下第四张。
语言分母用 `written()` 而不是 `Lang`——**英文最容易悄悄漂，恰恰因为还没有
读者能被它回答**；`**` 归一化掉，强调是各面自己的排版决定。反例照真实漂移
的样子造（全角括号打成半角），并用漂移前的真实字符串复验过。
**#393 答复**：不做运行时供词（那会把渲染搬进信封，与 #391 反向）；构建期
生成 + 签入是对的方向，**且量完发现它没被 #390 档⑥ 挡住**——20 张表已经是
`Record<成员, Words>` 的最终形状（占 verdict.ts 845/2362 行），档⑥ 要动的是
另外 467 行裸单语（浏览器 656 行 CJK 中 189 行已在 `Words` 内），两者不重叠。
今天仍选保留 220 条手写复述并钉死它，生成另立一条：**闸口让重复变安全，
生成让重复变零，是两件不同的好处**，而今天两门语言都齐、第三门还没有。
**放弃的更优解是「零手写复述」，代价是这 220 条仍需人手同步**——换来同步
失败在 CI 立刻响，而这条闸口正是将来那个生成器的新鲜度检查。

- 一条假设的第二个作者——删掉整条结构化通道（2026-08-21，#392）：
词表按 id 存着 `layer`/`testable`/`claim`，55 处结构化 spec 又各写一份，
**28 个 id 全都已有词表行**。于是 **`testable` 矛盾 15 处、`layer` 矛盾 2 处**
（严重度跟着 layer 走）、**一条前提的中文写了 3 种**（词表里是第 4 种）。
根因：**一个字段同时装「身份」和「按身份可查的事实」＝给那些事实立第二个作者**——
#343 杀 provenance、#345 杀 severity 是同一形状的前两例。
中途一次演示：把词表 positivity 改对之后跑真答案，**读者看到的还是旧值**。
测量说结构化通道没带任何扁平通道没有的 id（`dose_response` 甚至反过来
从 spec 派生扁平列表，注释还写着「one source of truth」），所以是**删**不是缩。
17 处逐条判：positivity 是 spec 对（重叠能数，`_ID` 不蕴含不可查）、
iv3 与捆绑 id 是词表对、线性 SCM 那两行留 `_FORM` 且**把这条可争之处写明**。
路线相关的那一样折进 id：`monotonicity_assumed_*` / `_refutable_*`，
判别词在前。闸口键形状不键计数：台账条目只在造台账的两个模块里组装

- 一条 id 自己的词要排在运行时值之前（2026-08-21，#398）：词表 14 行普通模板
各自断言「我前缀之后的一切都是调用者的一个名字」，两族 id 让它为假。
`backdoor_adjustment_set_{z,w}_sufficient` 把自己的词放在了值之后（**潜伏**：
四条路线上结构化 spec 都先认领了它）；`propensity_clipped_to_floor_0.01_on_755_units`
是**一条 id 带两个值而模板只有一个洞**（**活的漏**：真跑一次 AIPW，读者就看到
`0.01_on_755_units`）。**两个缺陷不同，修法也不同**——一个把词挪到值前面，
一个给它 `_Fills` 规则（词表顶上早写了「a runtime suffix is not always ONE name」，
这行只是没拿到）。闸口用 AST 扫每个字符串构造式：开头命中普通模板前缀、
中间有洞、**结尾字面量还带字母**的就抓；**标点不算词**，收尾的 `}` 是调用者集合的括号

- 假设的身份是 id 不是句子（2026-08-21，#396）：31 个估计器里有一个用中文散文
当假设声明，于是词表四行按「这句中文怎么开头」键。**根因是键的类型错了**——
台账每条要的「哪一层 / 能不能查」散文挂不住，而**键不是给读者看的**，
翻成双语也没用；这个模块一说英文，声明就会静悄悄掉进未分类默认，
**丢层级和严重度**。改在估计器端：声明 id，每个误测列各一条
（各自的 σ²_u 各自会错，**读者没法一块一块反驳的假设是他没法行动的假设**）。
新词表两行与 `outcome_error` **成镜像而镜像不对称**：那边 σ²_v 只给区间定价，
这边 σ²_u 进入校正本身，所以同一句话在这边是识别层。四行里一行是**死行**
（为 `model_assumption` 写的，而那个字段去 mechanism_audit，从不经过这张表）。
闸口：150 个键一个都不许带非 ASCII 或空白——**不是「不许中文」**，
英文句子当键是同一个毛病；运行时后缀天然豁免，因为它不是键

- 主报告整份换语言——一张分派表的接口是它的值的签名（2026-08-21，#390 档⑤）：`analysis_report.py` **314 句 → 0**，368 条 `Words`，默认值只在入口。五张分派表的值都是渲染函数，**表的接口就是它们的签名**；读者的语言按**关键字**到达，而 `Callable[[dict, dict], str]` 只能描述**位置**——所以立 Protocol，其中两个设成 **positional-only**，因为各家族给容器起的名字不同（`ne` / `block` / `ledger`），**不加 `/` 就成了固定拼写而不是固定形状**。翻译逼出重复：条件从句写过三遍、信封散文的补句号写过两遍、「- 标签：值」写过三遍，还有一个**自带空格的洞**（`f" {by} "`）——**同一句话在一门语言里写两遍像是习惯，在两门语言里写两遍就是两行会各自漂的记录**。跑了一份 `lang="en"`：整份英文，**剩下的中文全在它引用信封的地方**——缺口是运行时算好写进信封的，语言在那一刻就定死了。`themis/output` 由此 1116 → 33，且这 33 条已全部挂在 #391 / #396 名下

- 参数没有地方可去——`explain(result, lang)` 只有一张十个 `_zh` 函数组成的表可以递（2026-08-21，#390 档④，关闭 #327）：`lang` 当了半年 `NotImplementedError` 桩，**不是没实现**——`explain` 的下一跳是 `_EXPLAINERS[kind](result, stmt)`，而表里十个值都把语言烧死在名字里，**名字不接受参数**。`explainer.py` 81 条 `Words`、77 次 `language.fill`、18 处签名接语言，十个产出函数摘掉 `_zh`，75 → 0。闸口同时从**注册表**升到**整包每个作用域**（AST，含参数与局部名），并给出豁免的正例：`Lang.ZH` 整个名字就是那个 tag，它命名的是**语言本身**，连它一起扫掉参数就没有值可取——判据因此是「tag **附着**在别的东西上」。留一行具名欠账 `_VERDICT_ZH`：它的名字今天是**诚实的**，先改名只会让名字撒谎，档⑤ 翻译时删

- 缺口报告的 160 句，和一个靠「剪掉中文前缀」取回名字的标签（2026-08-21，#390 档③）：读者的语言穿过 `data_gap_report.py` 的 41 处签名，149 次 `language.fill` 出去。**私有产出函数一律不给默认值**——`language.DEFAULT` 的含义是「调用者没说时给他什么」，复制到 40 个产出函数里就等于给「语言在中途被丢掉」开了 40 个静默出口；默认值只留在入口。`say` 全换成 `fill`：`say` 要调用者写 fallback 是因为它给查表用，**一个模块级的句子没有 token 可以退回**。翻译逼出两个真缺陷——① `_short_label_for` 取回分布名的方式是**从 `description` 上剪掉中文前缀**，而**一句话在读者的语言里，名字不在开头**（改读产出方写下的 provenance）；② 同一张标签表里一条说 `P*(...) on user`、兄弟说 `... 在 rct_meta 上`，**两个读者一个也没被写给**。8 条中文针是 `Wrote.QUOTED`：它们拿去比对**用户的变量声明**，决定语言的是程序的而不是读者的，**按读者拆开反而认不出用另一门语言写的声明**。`_Renderer` 改成 Protocol，因为 `Callable` 说不出「按关键字到达」。160 → 0；同批把 `bounds.py` 8 条与 `result_orchestrator.py` 13 条标注为**信封散文**（#391），不属渲染层

- 138 条断言各只说一门语言，而「自己填洞」的豁免只有一行长（2026-08-21，#390 档②）：根因是这张表**把「一条假设是什么」和「怎么把它说给读者听」写成了同一个字符串**——一个 id 对应一句中文，前缀规则再把 id 的尾巴接进那句话里，于是「加一门语言」不是给表加一列，是把表的形状换掉。换成：**一条假设有一个 id，id 底下挂一个 `Words`，洞是有名字的**。138 条精确 id 走 `_EXACT`，8 条前缀规则走 `_PREFIX`（尾巴要么原样填进 `{suffix}`，要么交给一个函数拆——工具变量和结局各自成一个槽，单调方向去查 `monotonicity_word(direction, lang)`）；`classify_assumption` 因此多了 `lang` 参数，因为**信封不带语言**，读者的语言只能在渲染时到达它。**两个类型分开是 mypy 指出的一件真事**：合成一个联合类型 `language.say` 就收不下，分开之后类型自己说了句话——**一个精确 id 没有尾巴可读，所以「规则」这个形状只属于前缀表**。**豁免清单空了，于是删掉的是清单本身**：`FILLS_ITS_OWN` 只有这一个模块，清干净它剩下的会是一个空清单加一个永远 skip 的「这条豁免还在用吗」测试，**空清单配跑不起来的守卫，比规则自己把话说完还要少说一点**。146 → 4，**剩下的 4 条不是断言是键**——`regression_calibration` 把中文散文当作假设的身份声明，这张表只好靠句子怎么开头去认它，**修在那个估计量上，不修在这里**（#396）

- 规则问的是「旁边有没有语言」，而豁免里的那个「或」压着 276 条拒答（2026-08-21，#390 档①）：「kernel 写读者的语言，英文需要理由」**只在读者的语言只有一种时才是一条规则**——两种之后「给英文读者写的词是英文」不构成任何证据。重新问一遍才看清它一直想问的是**这条文本旁边有没有写着它是哪门语言**，而这样问，问题里不再提到哪一门。于是全仓只剩**一条**规则覆盖每一条能到达读者的文本（**坐在说出自己语言的键底下，否则是欠账**），两个探测器喂它——中文在字形里自己宣告，英文得先和公式分开。**这样一问删掉了一条豁免、劈开了另一条**：`Wrote.HELD` 豁免拒答通道的理由是「该用哪种语言到达读者不归这条规则决定」，**那是给一个问题起名字而不是给一个答案起名字**，而新规则回答了它（每一种）——HELD 上一条中文没有、123 条英文有，其中 `estimator_failure.reason` 两个读者面都在打印；每个 `raise` 都被豁免的理由是「要么是开发者读的不变量，要么是正在去拒答通道的话」，**只有前半句与读者无关**，而语法里本来就分得开（**断言抛内建异常，拒答抛自己定义的**），那个「或」后面站着 **276 条**（43 个模块）。反方向也纠正一处：`Refusal.says` 的 69 条英文**不是**欠账（其 docstring 自陈「不是读者的句子」，一个写入者零个读者）=`UNREAD`——**闸口变准了不只是变大**。欠账清单 `STILL_ONE_LANGUAGE` **1369 条 / 62 个模块逐模块精确计数**，形状抄本仓 `mypy.ini` 那条（全仓规则 − 只能变短的具名例外）；**精确而非上限**，因为上限就是「还能再加一条」的余地。再加两条规则：**一句话在每种语言里要的东西必须一样**（`format` 丢掉没拿到的槽，于是漏槽的翻译渲染成一句短话而不是错误，下游看不见）——第一次跑就抓到前门那句测量误差的**英文半边还带着位置槽** `{}`；**填洞是 `language.fill` 独占的**（`say` 缺语言时返回兜底，而一句话的兜底是空串，`say(...).format(...)` 会把空白递给读者并报告成功），全仓只有 3 处 `.format(`，两处手工的其中一处是拒答。**而这两条规则的分母自己也得有人管**：浏览器第一版扫描只认「每种语言一个串」，`Words<T>` 的 **50 个语言键一个都没被看见**、两条规则在它们上面平凡通过（#373 的形状），补的是**读第二种形状**＋**把分母钉在「语言标签被当作键写下的次数」**（每语言每 `Words` 恰好一次，334/334 与 344/344），第三种形状现在到达的方式是**一个没人够到的标签**而不是沉默

- 「答得出」和「有词」是同一个集合，第二门语言把它们掰开（2026-08-21，#389 / #327）：`Lang` 一个名字同时说「读者能被用哪些语言回答」和「每条文本必须存在于哪些语言」——一门语言时两者同真同假，两门就必须错开：英文没法先攒（闸口不许写在不应答的语言里），`Lang.EN` 也不能先加（那等于宣布每个面都齐）。拆成 `Lang`（门）与 `ARRIVING`（正在写），**`written()` 是全仓完备性的分母**，所以标签一进 `ARRIVING` 所有闸口立刻逐成员点名。档 A 只建闸口不写一个英文（浏览器 20 张表补上语言这一维，合法性交给类型系统）；档 B 设上标签、**一字未写先跑一遍——32 条测试把缺口逐个报出来**，再填 388 条英文。两条闸口自己错了且是同一个错（读串不读槽）：「词不能等于标识符」在英文里假（`blocking` 就是 `blocking` 的英文），改成问 gloss「没文本时你说什么」；「英文小句」扫描新增一条**结构性**豁免——**坐在语言键底下的字面量，语言就是那个键说的**

- 读者的语言是名字的一部分，所以它没法被请求（2026-08-21，#388 / #327）：23 个 gloss 把语言拼进函数名（`scale_zh`）、8 张表拼进表名、4 个词表拼进字段名、一处拼进 **JSON 键**——**一个名字接不了参数**，所以「用英文回答这个读者」**不是一个能提出的请求**（`explain(..., lang=)` 从 v0.1 起就在，且对除 `zh` 外一切 `NotImplementedError`：参数是对的，无处可去）。**「加一张中→英表」也不通**：到达读者的串有 **427 个是插值拼的**，中文句子不是常量、当不了键——缺的是**不带语言的那个事实**，而它一直在（token）。新增 `themis/language.py`（`Lang` / `Words` / `token` / `say` / `gloss`），并掉两份不等价的 `_describe`；23 个 gloss 改成 `(value, lang)`；`Layer.zh` → `.words`；audit 行 `"zh"` → `"words"`（**行是凭据不是渲染**）。**先建闸口再迁移**：`Lang` 今天只有 `ZH`，完备性闸口按**成员×语言**参数化后平凡通过，**加 `EN` 那一刻它会把每个缺英文的成员点名**。新闸口 38 条，每条带反例，并钉住**绝不回退到另一种语言**——半个语言的报告是缺陷不是修法

- 四个数据指纹坐在一份答案上，没有任何东西比较过它们（2026-08-21，#385 / #383）：运行契约的、估计器的、界的、推导步骤的——**十五条规则各读一次 `data_hash`、各自只查「是不是 64 位十六进制」、没有一条去看第二个**，于是「界在 frame A 上算、点在 frame B 上算」的信封**通过了现有全部检查**。**这条关系在指纹带上分母之前写不出来，因为相容≠相等**（Manski 界要的列比它包住的点估计少，两个 digest 本就该不同）——要成立的是**digest 是它覆盖的那批列的函数**。五条关系**每条都先在「套件产出的每一份信封」上量过才写下来**（312 份带指纹、13 种形态、零例外）：分母非空不重复；同清单→同 digest；**不同清单→不同 digest**（否则是**抄**的，`_hash_frame` 先混列名所以算不出相等）；不得立在没到达过的列上；**没有分母的指纹必须等于某个有分母的**。它是**信封上的一条**而不是十五条里各一句，因为这个断言是**块与块之间的**。第 5 条顺带关掉 #383：230 个推导指纹全无分母、218 个全部匹配 `numeric_estimate`，所以不用改那十五处；更严的写法需要一张**今天没有任何输入能行使**的 rule→block 映射，**那会是一个说不出「不」的闸口**，已登记触发条件

- 一个字段装着「digest 覆盖什么」和「矩阵怎么读」，而 docstring 说的是第三样（2026-08-21，#384）：discovery 的 `columns` 作为**集合**是 `data_hash` 覆盖的列，作为**顺序**是下游一切的索引顺序（节点 id、`correlation` 的行列、`contingency` 的元组）——**同一批成员的不同顺序**，一个名字必然对其中一件为假，**而两处 docstring 都答了第三样**「canonical order」，两件都不是。**只改名是错的**：那会把索引顺序带进一个在另外五个容器里意思是「digest 走过的顺序」的拼法，**让一个名字在包里指两种顺序**。所以是**拆**成两个字段。**承重的证据是 digest 只能从其中一份重算出来**——闸口用故意不按字典序的 frame 跑：`_hash_frame(frame[data_columns]) == data_hash` 而 `[columns]` 那份 `!=`（`_hash_frame` 先混列名，顺序是 digest 的一部分），期望值**独立重算**而不是拿生产者写的另一个字段去比。分出去的一半：这两个块**在任何 schema 之外**（`kernel_ast.extensions` 是开口袋；`markov_blanket` 是**六种 artifact 里没 schema 的五种**之一），所以 #381 的闸口够不着——**不是拼错名字，是没有任何 schema 说它存在**（#387）

- 那个基类有意放弃了同一性，而 35 处在花它（2026-08-21，#382）：`EnvelopeName` 改写三处让复制/pickle 的成员**变回纯 `str`**（信封是数据，序列化的人不该收到注册表），它拿**同一性**换这件事——而全仓 **35 处 `x is <词表>.MEMBER`** 在花那份同一性。**今天没有一处是假的，这是量出来的**（23 处 copy/deepcopy 全在叙事层的 program AST 上）；**值得删的是它坏掉的方式**——坏在未来某次复制、坏在没人再看的比较里、**且静默**（其中一处决定 Manski 收紧哪一侧，产生的是**错答案**不是异常）。改 `==`（对成员和它变成的字符串都成立）；**跨词表值冲突先量过**——只有 `identification`（Block/Layer），不涉及这 35 处。**线画在基类上而不是 `is` 这个词上**：普通 `Enum` 保留单例，`ResultStatus`/`Role`/`AnswerTier` 上约三十处原样不动；这条线买到的是**迁移**——`Monotonicity` 改基类后闸口**立刻点名三处**（bounds.py:342、counterfactual.py:240/242），由规则找出来而不是靠记性，闸口另在改前源码上重放、35 处一处不漏。已登记：还有 **19 个词表** 的 `str()` 仍答成员的地址，**而「有没有一个地址真的到了读者」没有量**（JSON 安全，唯一暴露路径是插值——#380 那五个缺陷正在那条路上、扫字面引用看不见）（#386）

- 指纹从不带上它的分母，于是「和什么一样」没有答案（2026-08-21，#381）：`data_hash` 把每一列的**名字**再把它的值混进 SHA-256，而**五个容器带指纹、零个带它覆盖的列集**——两个不同的指纹只能说「不是同一次运行」，**说不出变的是被测的值还是被测的列**。受害者是 #377 那条读法：「这个答案立在哪些列上」没有槽位、散在约十个不同名字的键里，所以两边都只能收集文档里的每一个字符串。修法是五个容器各带 `…data_columns`，schema 用 **`dependentRequired`** 绑住（不是 `required`——两个容器的指纹本身可选），闸口分母由 glob 发现、三种坏法各一个反例；审计页脚（指纹**唯一到达人的地方**）现在说出覆盖了哪些列，**且两者从同一个容器读**。三件度量改变了做法：**「有槽位就变成一次字段读取」是过头话**（识别层的答案是估计量不是数，所以留两条读法）；**只加字段会静默弄坏 #377**（`estimation_context` 的分母是**到达了什么**、包含没人估计过的列，原来的走法会把它当成「立在上面」——排除它是**承重**的，有测试钉住）；**验证器那份「独立孪生」在这条上从来抓不到东西**（两边同样地猜同一个事实，按构造必然一致＝不可能失败的规则；现在生产者**声明**再拿自己的声明定级，两条**此前不可达**的失败已建成测试）。**这条改动自己犯了它在讲的那个错**：给界的分母写描述时写了一句「界和点估计说的是同一份数据当且仅当两个列表相同」，量一遍是假的（点估计 `(x,y,z)`、Manski 界 `(x,y)`，digest 本就不同而数据相同）——**把可检查的关系写成散文，于是没人核对过它**，正是 (208)。描述改成只说它是什么，真关系交给规则，而**那条规则今天不存在**（一份结果并存 2–4 个指纹、验证器只查十六进制格式、从不比较任何两个，已登记 #385）。另：第一版按行长得像改，41 行里 12 行是规则的声明参数，炸出 345 failed；AST 分类修好后**仍漏一个**——`terminal_inputs` 先赋值再传，语法上不在那个调用里

- 方向没有「读者的词」，于是五个生产者各写了一份（2026-08-21，#380）：`Monotonicity` 在任何地方都没有一份读者的词，于是**四处把 token 插进中文句子**、**一处手写英文从句**塞进中文 notes（同句里还有裸的 `lower`/`upper`）。登记册用一句**写下来的理由**放行了它——「台账那一行用词说出了方向」，**而那一行印的是 token**，这句话是假的且从没有东西要求它为真（39 条 `no_gloss` 对 22 条 `glossed_by`）。**这种理由就是写成散文的 `glossed_by`**：映射要么存在（那就命名它）要么不存在（那句话就是假的）。现在这一行写 `glossed_by`，并新增一条规则：**台账词表的值插进中文句子要经过它的 gloss**（分母＝`themis.ledger` 的 `*_zh` × 每个模块，都不是谁维护的清单）。顺带度量到：`Monotonicity` 不是 `EnvelopeName`，`str(member)` 是成员的地址，**一条测试靠两个 fallback 互相比较通过了**；更宽的「字面量里不得出现 token」规则不成立（53 条命中几乎全是英文单词本身）

- 工具变量只活在那句散文里，于是审计它的办法是「搜索」（2026-08-21，#379）：Balke-Pearl 行印的是**对线性规划的引用**（一般基数下无闭式），而工具变量**只存在于那句话里**，所以规则**对那句话跑正则**。两个方向同时错：**换个说法就把审计弄坏**（`startswith("min of P(")` 检查的是开头短语），**拟合到错变量上却弄不坏它**（句子写 z、正则捞出 z、规则和自己达成一致）。现在工具变量是**字段**，规则**读它并对着图核**（入处理有边、入结局无边）——**必要而非充分，并写明如此**。`estimand` 也第一次真被检查。「哪一端」不再审：**用找词去审会拒掉谓词含该词的程序，`vitamin` 里含 `min`**。第二半：这个字段**早就存在**，被描述成「数值端的」——**按谁写的它而不是它是什么去描述**，于是符号端不认得它、又加了一份同名声明；**JSON 对重复键保留最后一个且不报错**。已建闸口，并由闸口找出早于本次的第二处（`det`）

- 一条 gap 同时装着「这是谁的发现」和「这要谁付代价」（2026-08-21，#377）：类型核对的**发现**属于程序、对每份结果都为真；它的**代价**属于手上这份答案——没有任何查询估计过的列改变不了这里的数。写成一条就只能按更强的那个报，于是**一个没人用到的声明不符变量阻断了每个查询的点估计**。修法不丢东西：`extensions.type_reconciliation` **到不了任何读者面**，gap 是这条发现唯一的到达方式，「只在被估计时才升起」会恰好在最该说话时消音。现在发现仍到达每份结果，估计量之外是 informational / interpretation，并在自己的句子里说清是哪一个断言。「答案立在哪些列上」是读出来的而非查表——信封在约十处说这件事、没有一处把它当一个事实（已另立待办：data_hash 文档写明只覆盖模型列，而列集本身从不随行）；读法保守，出错方向是 block 得更多。验证器自己走一遍、两个方向都拒

- 拓宽销毁掉的那个事实，答在拓宽的旁边（2026-08-21，#376）：契约把数值模型列 `astype("float64")` 后，dtype 不再区分「整数编码的类别」与「测量值」，**三个**估计器各自把「是不是整数值」推了一遍（登记条目说两个），并**恰好在没人比较它们的地方分歧**：`np.round(inf)==inf`，所以缺 `isfinite` 守卫的 `missing_recovery` **收下了一个无穷的分层 level**（可达，已演示）；空列上另两处一个说是一个说不是（不可达——正因不可达才活了下来）。并成 `contract.integer_valued`，**放在使它成为必要的那次 cast 旁边**，有限性是答案的一部分而非旁边的守卫。闸口分母＝源码里所有「与四舍五入结果比较」的地方，且只认「与自己比较」不认「四舍五入」本身

- 「它序列化得了」不是那条承诺问的问题（2026-08-21，#375）：`envelope_scalar` 承诺「JSON 写得下的五样」，**float 是五样之一却仍可能一样都不是**——JSON 没有 NaN 也没有无穷，`json.dumps` 自己发明三个 token、`allow_nan=False` 下又自己全拒。而为这条承诺兜底的后置条件跑在**默认（宽松）模式**，**恰好对承诺排除的值为真**：不是少一条分支，是**检查比承诺更宽松**。改法＝后置条件用 `allow_nan=False`，转换按**读者那侧会拿到的 token**（取自写方）拒绝非有限 float。**先量再拒**：19,930,596 次转换 + 1,768 份信封，非有限值 0，所以拒的是可能到来的。另一条路线（**算出来的** float 不经过它）无法由源码判定——那是算术的性质，已在语料臂的 docstring 里写明边界。顺手把「七个生产者指向同一函数」的分母从手写清单改为源码扫描

- Σ 绑住它接管的原子——而这件事被写成了两次调用（2026-08-21，#374）：`_bind_none_to_varref` 自陈是事后补丁，不做它求值器就在 `P(m|x=True)` 撞上 `value=None` 抛 `InsufficientTheta`，**而绑它的 Σ 就在树的正上方**。两件事其实是一个操作：`value=None` 意为「由持有这份公式的人来绑」，一个 Σ 接管了它就成了那个持有者，**指向该 Σ 的名字就是「接管」的全部内容**。并成 `_bind_and_sum`，三处调用点全部走它。**两个更早的解释被度量否掉**：登记条目的「需要第四种值状态」——3841 份出货公式里 `None` 只有两种落点；我自己写的「Y 侧缺 `query_y`」——**21 份公式里查询目标同时是分子的洞和分母 `Σ_y` 下的变量**（Tian 条件化的归一化常数本来就要边缘化掉被问的量），所以判据不能按原子设。闸口的分母是源码里全部 `SumExpr(...)` 构造点，并区分「命名新变量」与「保结构重建」

- 头部日期原本是「必须存在的字段」，现在是「必须成立的断言」（2026-08-21，#378）：旧规则只查 `> 更新时间：YYYY-MM-DD` 在不在，并写明不再往前走的理由是「陈旧与否取决于文件历史，正则不可靠」。它不取决于历史——写有日期工作的文档，日期就在正文里。实测：CORE_STATUS 与自己最新日期相符，**COVERAGE_MAP 声明 2026-07-11 而正文写着 2026-07-13**，即**旧理由为真的那个文件恰好是陈旧的那个**。新规则不需要逐文件结构也不需要例外表：正文里不得出现比头部更晚的日期。本条不修、也不假装修了的是——这张地图的**内容**落后约一个月，而闸口看不见它（停止更新的文档也停止获得新日期）

- 闸口数的是「这次跑出来的串」，于是它报的是自己看过的那部分的完备（2026-08-21，#373）：`themis/` 里 **823 条**文档之外的英文从句，语言闸口全绿——其中一条落在闸口自己已声明为「散文」的 `cde_status.reason` 上，被中文报告和浏览器两处原样印出。两条臂的分母都是「跑一次产出了什么」，**连那条专管「有没有漏分类」的完备性臂也是**，所以没被语料触及的分支既不被检查也不被报成未检查。修法是第二条臂改从源码出发、**分类反转**：内核写读者的语言，英文才需要理由。四条结构性豁免由 AST 自判（文档串 1606、`raise`/`super()` 1590、verifier+oracle 396、具名槽位 201），余下 **222 条已译**。设计自身的两个缺陷都是同一个病：手写的关键字表漏了 15 条（改为从 schema 叶名推导），匿名 dict 只按键名索引会把拒答通道和读者散文压成一行（改为按键签名、子集判据，撞签名即失败）

- 闸口问错了问题：它问谁在读，该问的是潜在共因动不动得了答案（2026-08-21，#353）：ADMG 上的 `cause` / `probability` 被 `SemanticError` 挡死，解门后逐个量，**答案本来就是对的**。闸口自己写的解门条件「路径读不读 bidirected 边集」是个代理，**两个方向都错**——`cause` 永远不会读它（潜在共因不是因果），按那句条件会被永远拒；`scm_counterfactual` 同样不读却从没被拒，因为闸口执行的是一对手写 `isinstance`，**未列名的 kind 默认放行**。修法是按 kind 声明真判据（动不动得了答案、动不了为什么），没分类的 kind 连模块都导不进来。放行的两种取值刻意分开：`ABSORBED` 怎么改都对，`CONSULTED` 哪天不再拿到边集就错、而且不出声。`scm_counterfactual` 归 ABSORBED 的理由是量出来的——abduction 是单元级的，40 单元对闭式真值最大误差 2e-15，声不声明那条边完全一样

- 一个布尔放在了兄弟函数收「轴」的位置上，于是披露说错了轴（2026-08-21，#352）：结局误分类通道，`differential_by="z"` 跑的是逐协变量层求逆（点 0.448888），台账却写「随处理臂而变」+「逐臂矩阵」。**一份确立各中心检出率的验证研究，对各处理臂检出率什么都没说**——核实的人会去查错的研究。根因是 `_assumptions` 收 `differential: bool`，而同模块的兄弟 `_exposure_assumptions` 收 `differential_axis`：**同一件事的两条通道，一个说得出轴、一个说不出**；布尔没地方放轴，所以改参数而非加分支。验证器不重算台账字符串 → 无镜像可对，闸口只能是**反例**（两个轴互不冒名）。登记条目原本记的另两件事**都已被正确处理**，没命中任何一件真出错的事

- 两个问题被焊在一起，而它们在答案的两侧（2026-08-21，#323 完成）：结局测量误差的精度代价推广到**前门与工具变量**设计。IV 的残差绕 β̂ 取，**而 β̂ 就是答案**，可这一行跑在所有估计量之前——看着像顺序问题，实则**一行在做两件对时机要求相反的事**：「这个声明可能为真吗」必须在答案**之前**（它能停掉查询），「这台噪声花了多少」必须在答案**之后**（没有答案就无从谈损失）。焊在一起就只能待一侧，于是需要答案的那种设计永远定不了价，而另两种是**偶然**能工作的。拆成两行，后一行声明 `after_the_answer`——**优先级轴排的是竞争者，而只做注解的行不是竞争者**；两道闸口各自构造了该拒绝的输入。β̂ 从答案**读回**不重算（两条 IV 行未必选同一候选，重算=第二份记录）。前门的因子作为**上界**披露（实测报 1.25 对真值 1.09），并带一条**数据证伪不了**的前提：前门图假设的那个未观测混杂，**若与测量误差相关，点估计本身会动**

- 一条「注解」行占有了查询，而它占有的那个条件正好定义了两条路线（2026-08-21，#323 侦察发现）：同一份数据，**声明结局有测量误差**就让前门 / IV 的答案从 `frontdoor_linear 0.4416` 变成 `numeric_estimate=None`。**占有是行的属性不是结果的属性**——这一行成功时 `annotated()`（它没有自己的估计量），却在「没有设计」时 `blocked()`，而它停下所依据的「调整集为空」**正是那两条路线的定义**。判据：**可以因为学到了什么停下，绝不因为够不着停下**；闸口做成普查（26 个处理器里恰好 1 个同时 annotate 和 block，点名 + 把规则写进失败消息）。另一半是**沉默**：报告只在数值分支全部落空后才够得到拒答，于是放行数值反而让它不可见——现在与答案共存的拒答是答案底下的一条注记，而浏览器那半相反，它印的 lead 是「没有给出数值」，正压在一个显示着数值的图块上

- 六份「numpy→JSON」降级辅助并成一份，而它们不一样恰恰说明这不是去重（2026-08-21，#318 完成）：登记说 5 份 / 7 个文件，实测 6 份 / 6 个文件，点名的三个文件一份都没有。**根因是谓词写错了**——六份都被当作「去掉 numpy」写，而调用点要的是「能进信封」，而 `.item()` 的值域是**内置**类型、内置类型不是 JSON 类型（时刻、时长、复数都写不下）。构造出的反例：一个 `datetime.date` 列进信封，`json.dumps` 直接炸。合并后的判据写成两半、**只有第二半是承诺**：numpy 说自己的等价内置值，然后结果**必须是** JSON 写得下的五种之一，不是就在产出者还在栈上时具名报错——**不打印**，因为验证器只从信封反推，被打印成串的层级和本来就是串的层级分不出来。家在 `themis/types.py` 紧挨 `EnvelopeName`。等价证明：六个 HEAD 版函数体 exec 进来对跑 24 个值，**0 处差异**

- 抑制名单 32 → 1，而复核抓到的两条回归是清理自己造的（2026-08-20，#331 完成）：剩下 32 个模块用多 agent 并行清 + **对抗性复核**逐个读 diff 判断「说出真相还是藏起问题」。两条真回归都是靠**把旧版函数体 exec 进活模块、同一输入对跑两版**抓到的：`dispatch` 删掉 `or {}` 兜底后，一条被记录的拒答变成逃出 `themis.estimate` 的 AttributeError；`rules._envelope_number` 让非数字字符串以裸 ValueError 逃出验证器（顺带关掉了相反方向的 NaN——它不是被拒绝，是被**静默认证**）。还有一批「只说了一半真话」：narrow 掉 None 之后，`explainer` 落进一句与 status 自相矛盾的中文，而崩溃虽难看但不撒谎。owner 侧：`VerifiableQuery` 是 `Query` 漏了一个成员的手抄副本，改成别名；两处 `-> None` 写在只会抛的函数上（普查 23 个里 21 个已是 `NoReturn`），改过来当场掀出一条被压住的真 finding。**findings 663 → 1**，剩的那一行含义已从「还没读过」变成「读过了，代价在这里」

- 累加器用它的第一个值声明自己（2026-08-20，#331）：mypy 抑制名单 **58 → 32**，findings 663 → 586（登记写的 605 是**旧数**，而 `structural_solver` 早就干净了）。最大一族 63 条是同一句话——元组字面量的推断类型带**元数**，定长记录对、累加器错，而源码里两者写法一样；补上 `tuple[str, ...]` 后 **10 个模块归零**。剩下的逐条读出真问题：外部区间从未校验元数与元素类型、一个函数里同名变量装两种东西（改一个露出三个）、`_is_fixed` 与 `_world_value` 各扫一遍同一结构、`.get` 当排序键、点样本与 bootstrap 共用一个返回类型、守卫只问了一对变量中的一个

- 类就是注册表——而登记里有一条早就成立了（2026-08-20，#330）：`Block` / `Family` 改成枚举。**收益一条声称一条反例，并记「在哪一层被拒」**：别名与「载体名指向不存在的东西」从**测试**升到 **import**（后者以前只查了一半——两个载体是引用、两个是裸字符串）；`CARRIER_FIELDS` 是新声明，由测试 held against schema；漏字段的 TypeError **本来就是** import 期，是保住不是赚到。**登记那条「拼错变静态错误」在 mypy 下本来就成立**，反例两种拼法都红。真正赚到的是 `DECLARED`/`ALL`/`FAMILIES` 三张派生列表消失。`BY_NAME` 留着——带自定义 `__new__` 的枚举，`Block(name)` 在 mypy 眼里是构造不是查找

- 没有人在写「失败的步骤」，而五个读者还在找它（2026-08-20，#339）：登记说那条分支「插桩 0 次到达」，**重新插桩是 10 次**，且 10 次全在**为它写的 5 个单元测试**里——测试造出内核造不出的形状，把死代码养活。该问的于是变成「**还有没有东西能造出这个形状**」，而这是关于**源码**的断言：87 个 `DerivationStep` 构造点、58 个字面 rule 名，**没有一个**能让判据为真。死的不是一条分支，是整套表示法——`_classify_missing_iv` 同样恒不执行，于是 `missing_iv_candidate` 全仓没有产生端。它看起来还活着，是因为 e2e 写的是**析取**（#367 同形）。闸口**不靠语料**：构造点普查是封闭的（算出来的 rule 要逐条声明，`**` 解包直接禁止），语料臂的分母写进 docstring 免得被当覆盖率读。验证器那份同名表**留着**——它读的是别人提交的推导链

- 已经有一道抓「写错语言」的闸口，而它的分母是一个块的三个键（2026-08-20，#372）：`late_caveat` 一整段英文印进中文报告而闸口全绿 —— 它的主语是「缺口的句子」不是「读者会拿到的散文」。度量当场给出契约里没写过的区分：**不是每个内核发出的字符串都是在对读者说话**（公式 / 引文 / 用户原话回显必须逐字保留）。**反例把第一版闸口打回来了**：判据「整串不含中文」有 6 条反例回绿，因为散文是**拼接**的，换掉一个从句剩下的中文仍在 —— 而这正是原缺陷的形状（中文模板里插一段英文）。规则因此倒过来：**显式声明哪些字段是对读者说话**，启发式退到「有没有没被分类的字段」那一侧，在那里猜错只值一行分类。13 处内核散文改中文，符号保留

- 「哪个门更弱」是数出来的，不是回忆出来的（2026-08-20，#367）：中介一节有 **6 条**「A 比 B 强/弱」的断言全写在 docstring 里、**一条没算过**，两条是错的（`C2 strictly weaker than M4` 方向写反，且它举的例子是一种**不存在的候选**）。根因是实现有教科书没有的前置条件（M 必须真的中介），它让两个判据坍缩成一个。枚举 4/5 节点全部 DAG 后又量出登记里没有的事：**`M2`/`M4`/`C2` 三个标签不可达**，而三者都在 schema enum 里、都有中文释义、都会被浏览器印出来——因为搜索失败时报的是**「W=∅ 那次」的标签**，而空集不违反任何成员判据。改成「**走得最远的候选被哪条挡住**」后六个标签全可达，`identifiable` 计数**一个没变**：中间混杂器现在说「能挡住的变量有，但它是 X 的后代」，而不是让读者去找一个就在他图里的变量

- 「不存在」有两种合法拼法，而没人规定过哪种（2026-08-20，#371）：同一个路径 `extensions.causation.pn.point` 上，θ 路线**不写这个键**、数据路线写 **`null`**，两种都合法、没有消费者能分开。展开 `$ref` 后 971 条声明路径里 **76 条**同时可缺省且可为 null；插桩全量录实际发出的拼法，只发一种的 67 条（关掉另一种即可，零行为变化），真含糊的 **9 条**。**度量推翻了原定规则**：`point` 与 `ci_lower` 的缺省是同一批 60 条结果、逐方法同步，那是「这个方法根本没有顶层点估计」与「有点但没算区间」**两件事**。所以规则改成：可缺省 ∧ 可为 null 只有在 `dependentRequired` 组里有**不可为 null 的锚**时才允许。`kernel.py` 的存在性核对退化成值核对，`causationQuantity` 拆成两个（结构块白拿的两个 ci 字段两个写入者谁都没写过）。读者侧一行没改——所有读者早就 `.get()`，病正是这样潜伏下来的

- 一个键由谁说，有四条通道，只有一条是一等对象（2026-08-20，#370）：块限定地问「这个块**自己的**渲染器拼不拼写这个键」，先把 #369 建的**详情表**这条通道算进去（那张表的键里就写着块名），78/181 掉到 44/181。逐条分类撞见四处真问题：选择偏倚把整个 Z 说成挡后门的（判据只对 **Z⁺** 检查阻断，Z⁻ 是处理的后代挡不了）；数值层那句括号解释**三个分支上全说反了**；单调性被推翻的份额只有可剥离的 explainer 说；**识别路线自己声明的前提从不进假设台账**——台账读四条通道，这条不在里面，而跑过估计器的路径上估计器带着同样的 id，所以恰恰在有数的地方看不出来。教训：我本来写一行「台账会说」就过去了，块限定的问题逼着我去查那句话是不是真的

- 到达读者的分母只到「有人画线的那一层」（2026-08-19，#369）：schema 全深度下 189 条声明键路径，**39 条任何读者面都不拼写**；最大一簇是四个**路线块**各自挂的 `numeric`——θ 路径算出来的数。CLadder Q1358 算出 TE=+0.1387 而 **NDE=−0.0725**（直接与间接反号，这是中介分析的全部内容），报告只印「0.1387」；条件 IV 把英文 caveat 整段印出来，那段话指着 `strata` / `treatment_shift` 说话，而这两个字段一个字都没显示。根因：分母的深度是被上一次事故决定的——`blocks.bind` 问 18 个块，#368 问 `numeric_estimate` 的直接属性，块内部的键从来没有分母。改法：**详情表的键改成信封里的一条路径**；恢复路线说出恢复式；反事实格说出它是哪一格；块内部还开着的 14 个 map 关掉（其中一个已在实发两个未声明的键）

- 引用是横切字段，而每一个渲染器都绑在一个容器上（2026-08-19，#338）：登记项是一个「一个写入者零个读者」的 bool，量它的时候（运行时 hook 住两个出口跑全量）量出它旁边坐着 `reference`——**7 个写入点、6 个容器、5 处 schema 声明、0 个渲染面**。每张渲染表的单位都是「某个容器里有什么」，而引用不是任何一个容器的主题，于是六个容器一致地漏。改法：**渲染绑信封不绑容器**，测试的参数集从 schema 走出来；删掉那个 bool（#334 之后是第三份记录）；把还开着的四个块关掉——而 #342 那个文件的 docstring 早就写着「其余每个块都是封闭的」，从没被检查过，说这话时有四个反例

- 「怎么算出来的」绑的是 extensions，而数是怎么算的记在 numeric_estimate 上（2026-08-19，#368）：#366 留下的 12 个块，**其中 10 个是同一个结构漏洞**——报告与浏览器的「怎么算出来的」都绑在 `extensions` 上，而「估计量拿到数据之后做了什么」记在 `numeric_estimate` 上，绑定看不见它；这一节自己的注释里已经为同一件事手工追加过两次（`formula` 是字段不是块、推导链在 `derivation` 里）。改法：两个面各加一张按 schema 细节键分派的表，进已有的那一节，**并按顺序把两张表钉成相等**（逐面对等这次可查，因为两面都用表分派）。剩下两个不是缺渲染：`inference` 是同一事实的第三份副本且只记 bool 无法佐证，**删掉**；`bootstrap` 上一轮被我写成「没人读」，实际被簇推断验证器当键读，改为 `consumed_by`

- 完备性纪律继承了它被挂上去的那套机制的分母（2026-08-19，#366）：登记的是「AR 置信集三个块两个确定性读者面都没有」，**量下来是 19 个，不是 3 个**——`numeric_estimate` 底下 28 个复合部件里，19 个没有任何确定性读者面读它。**根因**：`blocks.py` 的分母是按「拼错了会不会静默」划的（`extensions` 的键会，有类型字段不会），而 #333 把「谁读它」挂到了同一张表上，于是**「谁读它」继承了「拼错会不会静默」的分母**——两件事毫无关系。改法：按 schema 走这个容器建门，一部件一行三选一（点名渲染器／点名非读者消费者／`unrendered` 但必须说清读者拿不到什么，且**反向核实这条声明为真**），并渲染其中 6 个（AR 三块 + 过度识别检验 + 倾向分重叠 + OVB 稳健值）。**「读了」必须是「当键读」**：裸词匹配曾把一句 docstring 和一句注释算成读者

- 归一化是一份「允许两份副本不一样」的清单，而它的内容是倒推来的（2026-08-19，#365）：登记的是两份重复的 `_half_width` 替换表，给的解法是合并成一处共享。**量下来登记的前提是假的**——它声称的「`verdict.ts` 通篇半角」并不成立（它的中文串全角 42 : 半角 42，整个前端 59 : 58，而内核 361 : 5），这条「惯例」是从这道门恰好比对的两张表推断出来的。**根因不是共享工具缺位，是一条被推断出来、从未被决定的「允许差异」**：它必然比它描述的短、必然被复制、必然漂，而合并只消掉复制、不消掉允许。改法是把允许换成禁止：两张表改到与内核**逐字节相同**、删掉两份归一化（比较因此**变严**），并加一道禁令——`themis/**` 与 `tests/**` 里不写「在分隔中文的半角标点」，一次改完 80 处。**规则的分界也是量出来的**：逗号后紧跟汉字即算，而带空格的那 24 处压倒性是「英文句子里列中文词」，那里半角是对的

- 一个词能不能被翻译，取决于内核要不要在 Python 里对它分支（2026-08-18，#357）：登记的是三处「封闭词表到达读者时仍是英文原文」，**量下来分母是 58 个信封 enum 站点，其中 #362 的完备性门只认账 20 个**——全部 70 个站点里 **42 个根本没有 Python 声明**，只活在 JSON 里，于是那道从 `enum.Enum` 子类走起的门**从没问过它们谁读**。**根因不是忘了翻译，是词表的声明位置有两个而只有一个能挂读者的词**，而落在哪边由「内核要不要分支」决定——与「读者会不会看见」无关。改法：完备性门**两扇门都走**，一个词表一行，同时回答「谁声明它」与「谁把它变成读者的词」；`no_gloss` 是断言不是豁免，必须点名读者拿到的是什么。门一开就抓到 6 处裸标识符（含登记里没有的 `framing_note.missing` 9 值、`_STATUS_BADGE` 7 缺 2、`_ACTION_PHRASE` 6 缺 1），另有 2 个 producer 把整句英文写给中文读者（48 条英文 alternative_paths 里 46 条来自同一个 gap kind）

- 一个装得下任意一个的槽位只装得下一个（2026-08-18，#358）：bounds 那趟 pass 是一条 if 链，返回**第一个开火的方法**。登记的现象（工具变量与调用方声明的单调性抢一个槽位、赢家由行号决定）**量下来零实例**；而同一个病灶的另一面 **3/3 全中**——36 条带 bounds 的结果里 3 条报 Balke-Pearl，这 3 条的无假设 Manski 地板同样适用、同样被 `if bounds is None` 吞掉，**而那趟 pass 自己的注释写的就是「the assumption-free floor」**。**根因不是谁排在前面，是这一层的输出本来就是一个集合**：三个方法 estimand 全是 `arm_probability`（同一个量），靠的是互不包含的假设集，而本仓的排序原则「无假设压过带假设」管的是**估计量变了**不是「谁更紧」——估计量相同它拒绝排序。改法：`bounds_result` → **`bounds_results` 元组**（连名字一起改，让 495 处引用逐一被逼着访问），producer 收集所有适用的方法，顺序降级为呈现顺序并明说**不该建 precedence 表**（表会重新暗示不存在的排序）。**不求交**并把这句话印给读者：交集含真值但不是合取下的锐界，且会抹掉各自靠什么。修后无假设地板 **36/36 在场**（此前 33/36）

- 表能说出谁赢，说不出谁输了（2026-08-18，#364）：同时点名 mediator 与 target_population 的查询被两条路线认领，dispatcher 在第一条就 `return`，**被夺走那条的 guard 真值从来没被计算过**；披露只好在下游读「哪个 extension 非空」倒推。**根因不在分类器，在路由表**——它能表达谁赢（precedence）也能表达谁可以把查询交给别人（defers_to），却表达不了**「两条 guard 可以同时为真，而赢家答的是另一个问题」**。三个推论都成立：形状档两两可同真的组合枚举出来有 **10 对而只有 1 对有披露**；其中两条的作用域**只写在字段 docstring 里**（散文，不是约束）；估计层 `considered` 自称解释可达性，却装不下「排在赢家之下、guard 为真、从未被问」。修法是给 `Route` 加`triggered_by` 与 `displaces`，两层共用 `displaced_by` 且**只求值被声明的那几条guard**，记录进 `QueryResult.dispatch`，分类器只读记录。不可表达做不到的那一半用闸口补：**形状档可枚举**，用一个「除 query 外一律抛异常」的桩让**每条路线的guard 自己分类**，穷举 2⁵ 个声明组合——未声明的同真对当场红。10 对现已全覆盖

- 图撤销的是「丢掉非父节点」的许可，不是分解本身（2026-08-18，#359）：同一张 bow+IV 图、同一份 θ（八个数一个不缺），`effect` 查询印着「计算只需要观察到的 P(y,x|z)」——**把手上已有的东西列成了还需要提供的数据**；反事实单格则跟它要一个边缘化一次就能得到的 P(x)。**根因不是求解器放在哪一层**：联合恢复只认「图上父集」这一种条件集，而**排他性恰好使 Z 不是 Y 的父节点**，于是在多面体唯一适用的那张图上，运行时永远问不出带 z 的那个 key。链式法则在拓扑序上对任何分布都成立，图给的只是**丢掉非父节点的许可**——双向边撤销的是这个许可，剩下的是**项更多的同一个分解**，所以条件集放宽到拓扑前缀。登记时的前置度量（有没有程序真会声明带 z 的联合）测到 0，但**这个 0 是供给侧的**：一个没有消费者的输入不会有实例。接上单格门之后 **#321 刚消掉的跨门不对称立刻重现**（单格答、causation 拒），所以两扇门一起接、差异（问哪几个泛函）作回调传入，并把点了定理的规则名改成中性的 `causation_probability_bounds`。顺带：两份恢复级联并成一份、工具变量探测器的结构半边并成一份、LP 内核搬到 `themis/response_polytope.py`（两端都向下 import）；θ 端因为**有 theta 这个第二来源**，能做数据端做不到的审计——逐层重导 P(X,Y|Z) 比对，分层标签由此可审计

- 一条识别级联，两个门都是它的投影（2026-08-18，#321）：同一个 PN 走 counterfactual 门给 `[0.1717, 1.0]`（真值 0.4516 在内），走 causation 门拒答。**根因不是漏了一档，是级联有两份**——一份六档、一份是它的前缀，而**两份从各自文件内部读都是完整的**，所以后来加的general-ID 与工具变量多面体只落在被改的那一份上。级联并成一份，门与门唯一的真实差异（**要几个臂**）变成参数，走到头返回 `None` 把终局留给门自己。**PN/PS/PNS 是同一个多面体上的三个目标向量，而且选的是同一个响应型**（结局跟着处理走的那种单位）——三者只差问的是哪个事实人群，PNS 的事实臂是**没有**而不是设成了什么。单调性怎么进多面体是**量出来的**：400 个随机 IV 模型里它 0/365 收成点、365/365 都收窄、35/400 被表推翻，所以折进程序是唯一不丢信息的读法。顺带：causation 门同时拿到 general-ID 路线；主报告与浏览器那句「这三个数怎么来的」原来挂在「两个干预风险都在」上，于是**唯一不需要干预风险的路线什么都不说**

- 一条关于「决定」的警告，仍然是那个决定被做出了（2026-08-12，dsh 借鉴，#363/#364）：判据是 dsh 拒绝 detect-and-report 的那一句——**「事后才抓到；一个违规的请求仍然被构造出来并发出去了」**。扫到三处：①bounds 槽位由行号在两组不可比的假设间决定，原注释把问题推给一个待办号（**那不算把问题说出来**），现在问题、三条出路与「哪一条不是出路」（求交等于同时断言两组假设）都写在原地；②dispatch 冲突是**事后读输出反推**的——分类器看哪个 extension 被填了来倒推跳了哪一层，而**结果早已构造完毕**，同一个仓在隔壁一层已经否掉过一模一样的动作（d-sep 拒绝由 `InsufficientTheta.gap` 携带，「决定在发现它的地方做出，不在下游靠搜索文本恢复」）；③跨门不对称——两个门各维护一条终止条件就必然分叉。**三处都没在本档修**（各自会改信封形状、各自是一件已登记的活），但**判据现在写在代码旁而不是任务列表里**——**一个待办号不是 HEAD 处读者能跟着走的引用**，这是前两档的教训用在我自己的笔记上。散文门禁因此多了第三个可判定子类：`CORE_STATUS` 每条登记项一条目，所以 id 在活落地后才解析得了、还开着时解析不了，而两者读起来一模一样

- 中介**块**对披露层是瞎的（2026-07-22，修复型）：同一张图、同一个查询，问单个中介时人看的输出带两条识别假设 caveat，换成中介块后**一条都没有**。根因是缺口层的生产者绑在 `extensions.mediation_decomposition` 这个单中介专用 key 上，而不是绑在「做了中介分解」这件事上。归一化成一个 `_mediation_view`，四处漏一起闭：识别假设 caveat 完全不出（最重——「可识别」读起来成了无条件的，而块的前提与单中介严格不同）、调整集谓词不进「查询相关」集导致协变量上的 `llm_proposal` 边逃过披露、数据需求永不列出、静默跳层的诚实 gap 只认单数字段。另加同源两处：数据端联合估计算了中介比例却不出 headline；`mediators` 只写一个中介时两条路由都不接，**整个中介分析被静默跳过且无任何信号**（集合就是集合，一个元素也是）。D1：五条新测试先在改前代码上跑成红的；核心不变量是 parity——问块与问单中介必须披露同样的东西。+6 测试

- 条件工具变量接上 theta 端（2026-07-25）：`iv_sets` 一直会返回**条件**（Brito-Pearl）工具变量——Z 只有在 W 被固定之后才是工具——identify 路径一直照实报，DataFrame 路径也一直用 2SLS 吃 W；只有 theta 端一见条件集就 `return None`。于是同一张图，identify 说「可识别，用 z 在 w 之下」，effect 带着完整 theta 回「backdoor / front-door / Tian ID 都到不了」，只字不提工具变量。补上**分层 Wald**：W=∅ 是同一套算术的单层退化（边际答案逐字节不变），层权按链式法则展开；聚合是**比值的平均而非平均的比值**——每层按它自己的 complier 份额加权（那正是分母项，Abadie 2003），得到的才是 complier 平均因果效应，把各层 LATE 按 P(w) 平均是另一个估计量，测试把两个数都算出来钉住。`treatment_shift` 顺带成为报出来的 complier 份额。第二半是说清**为什么给不出数**：`None` 不携带信息，于是「没声明 monotonicity」「theta 少一格」「一阶段退化」全塌成「这图没救」；现在各自点名，并排追加在结构项旁边——**「有可用的 IV 逃生通道」不等于「可识别」**，顶替掉结构项会让区间答案被当成点识别（第一版正是这么写的，被回归抓住）。验证器不复读：就地重验 (Z,W) 真是工具（抓「算了边际 Wald 却把 W 记成 ∅」）、从 theta 的域重新枚举层（抓少记一层）、按比值的平均重算聚合。取舍：处理与工具须二值·条件**查询**仍归 IDC·theta 查表不走边缘化回退。D1：16 条新测试全部先在改前代码上跑成红的；前提先证后证结论；四类篡改各因该抓的原因被拒。+16 测试

当前全量测试基线：**16603 passed / 512 skipped**，warning-clean。

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
- **测试套件**：16603 passed / 512 skipped（2026-09-05）
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
