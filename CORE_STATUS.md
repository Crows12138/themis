# Themis Core Status

> 更新时间：2026-09-02

这份文档只回答一件事：

**当前 Themis 核心到底完成到了什么程度。**

它不是愿景文档，也不是长期路线图。  
长期目标看 [VISION.md](VISION.md)，阶段路线看
[ROADMAP.md](ROADMAP.md)，上游建模层看
[WORLD_MODELING.md](WORLD_MODELING.md)。

---

## 当前快照（2026-08-07）

Themis 当前开发态是 **`0.15.0-dev`**。它已经不只是 `v0.1` 静态
DAG 内核，而是：

**可审计的因果推理编排器 + 数据缺口诊断器 + 受控估计层。**

当前已落地的主线能力：

- 静态 DAG 核心 + front-door / 窄 ADMG / 窄 temporal / 窄 counterfactual
- IV / mediation / transport 结构识别
- backdoor / front-door / IV / mediation / dose-response 数值估计
- causal discovery / sensitivity / bounds-first / data-gap report
- NL bridge、variable framing、KB adapter contract、MCP wrapper
- V0-V5 derivation verifier + T10 data-gap verifier

当前全量验证基线：

```text
11691 passed / 236 skipped, warning-clean
```

**统一分析报告（build_analysis_report，2026-07-11）**：借鉴 Causal-Copilot
「一份可读报告」的思路，但做成**确定性、无 LLM** 的组装器
（`themis/output/analysis_report.py`；顶层 `themis.build_analysis_report` +
MCP `themis_report`）。把一次分析缝成六节：问题 / 因果图（含边来源：用户
断言 vs `discovery:*` vs `llm_proposal` + bootstrap 稳定度）/ 答案（按状态
分支：数值 point+CI+method+精度+E-value 稳健性 / 结构 bool / bounds 区间 /
可识别但需数据 / 需补充）/ **验证** / 假设账本（严重度排序）/ 数据缺口 +
下一步。**被动组装、绝不重跑推理、绝不内部调 verify**（守 output 层铁律）：
「验证」节展示 derivation 存在性（可 `themis.verify` 独立复核；无 derivation
→指向 `verify_data_gap_report`），调用方可把 *另做* 的 verify verdict 传进来
打 ✓/✗。前置顺序遵 `response_rendering.md`（答案优先→假设→缺口）。**与
Causal-Copilot 报告的根本差别 = 前置了它没有的「验证 + 缺什么数据」两节**。
+15 测试（14 报告 + 1 MCP 工具端到端）；MCP 工具 9→10（同步 test/README/
COVERAGE_MAP/smoke 四处清单守卫）；基线 2740→**2755**。这是「借鉴
Causal-Copilot」清单 #2。

**前置数据诊断层（declared_type_data_mismatch + VariableDeclaration.scale，
2026-07-11）**：借鉴清单 #3。这是**第一个由实际数据（而非程序结构）驱动
的 gap**——`themis.estimate(...)` 在末尾把每个变量声明的测量类型与实际列
核对（`themis/estimation/dispatch.py:_attach_type_reconciliation`，用**原始
未强转数据**分类以保留整数离散性）。根因勘定：Themis 此前**没有正向的连续
声明**（「连续」= 没写 `domain`，而「没写」歧义于「懒得写」，靠它报警会在
海量二元-无-domain 用例上误报），故加**可选 `scale` 字段**（binary/discrete/
continuous）作为正向声明的单一真相源（与 `domain` 互补，不是并列第二真相
源）。两种判决：`declared_continuous_data_discrete`（声明连续、数据仅 k 个
离散值 → 估计量塌成离散对比而非剂量曲线，blocks interpretation）、
`domain_violated`（声明二元/离散、数据取值更多或越界，blocks point_estimate）。
**只在正向声明被数据违反时触发**，未声明变量与一致程序完全静默（零既有测试
破坏）。证据记进 `extensions.type_reconciliation`（记 n_unique/dtype_kind/
distinct-value 集作充分统计量），`verify_type_reconciliation` 从零重导分类+
判决+gap 对应（独立性 pin，不 import 生产侧），接进顶层
`themis.verify_data_gap_report` 故现有 MCP 工具自动带上、**零新 MCP 工具**。
硬同步：GapKind 枚举 ↔ query_result schema ↔ verifier `_KIND_ACCEPTS_REF`
三方 + GAP_KINDS_REFERENCE 行 + COVERAGE_MAP 计数 31→32；`scale` round-trip
过 `_statement_to_dict` + `_to_statement` + kernel_ast schema。+22 测试；
基线 2755→**2777**。

**Markov blanket 发现 + 独立验证器（2026-07-11）**：借鉴清单 #4「更多发现
算法」。现有 5 个整图学习器（PC/FCI/GES/GRaSP/LiNGAM，均无验证器）之外，加
**目标相对的局部原语**：目标 T 的马尔可夫毯 = 屏蔽 T 与其余所有变量的最小
集（父、子、以及子的其他父/配偶）。用途是把几十列**筛**到与 T 局部相关的少
数几个，供建 DAG——**不是调整集**（毯含子与配偶，估计效应时不可条件化，否则
开对撞）。`themis/estimation/discovery.py:markov_blanket`：**grow-shrink 交织
到不动点**——在不动点上「加不进」保证完备性、「删不掉」保证最小性，两条正是
马尔可夫毯定义，故生产者输出**恒满足其所声称的定义**。**发现层首个逐数验证**：
连续数据下 Fisher-Z 偏相关检验是相关矩阵的纯函数，故相关矩阵是**完备充分
统计量**；`verify_markov_blanket`（`themis.verify_markov_blanket` 公开面，平行
`verify_bounds_result`）从记录的相关矩阵**独立重写 Fisher-Z**（不 import 生产
侧、不 import causal-learn、不重跑搜索）重算每条完备性/最小性检验，拒伪造/裁剪
的毯、篡改的检验、非良构（非对称/非 PSD）的相关矩阵。D1 oracle：已知
线性高斯 SCM 恢复手推毯（含**配偶**这一微妙情形——与 T 边际独立、条件于共同
子后才相关）+ 生产者 Fisher-Z p 值对齐 causal-learn CIT（跨实现锚定）。MCP
工具 10→12（`themis_markov_blanket` 产 + `themis_verify_markov_blanket` 验；
同步 test_mcp_server 精确集 + server.py 模块 docstring + README 目录表与计数 +
COVERAGE_MAP 计数四处守卫）；+21 测试；基线 2777→**2798**。

**离散马尔可夫毯（卡方，同 session follow-up）**：补齐上条「仅连续」的取舍。
`markov_blanket` 现按数据类型分派：全连续→Fisher-Z（相关矩阵）、全离散
[整数编码/bool]→**卡方**（充分统计量=**稀疏联合列联表**，以 distinct-行数≤n 为界
而非 k^p 稠密表）；grow-shrink 抽成接受 CI 闭包的通用版，两条路径共享搜索。
卡方自由度**逐字对齐 causal-learn 约定**（每层 dof=(该层出现的 X 水平−1)(Y 水平
−1)，按出现过的分层求和）；`verify_markov_blanket` 从记录的联合列联表独立重写
卡方、重算完备性/最小性，拒伪造/裁剪毯 + 篡改 statistic/dof/p + 列联计数和≠n +
越界编码。**分类必须用原始未强转数据**（validate_data 把整数列转 float64 →
`_classify_column` 会把离散整数误判成 continuous，同借鉴清单 #3 的教训）；混合
连续+离散报错（混合 CI 检验未做，显式推迟）。D1=离散对撞 SCM 恢复含配偶的
手推毯 [X1,X2,X3,Y] + 3 水平无关变量正确排除 + `_chi_square_from_joint` p 值对齐
causal-learn CIT chisq（跨实现锚定，含多值/多条件）。MCP 工具数不变（复用同
两工具）；+13 测试；基线 2798→**2811**。

**选择偏倚数值端 + 诚实门（§S9.1，2026-07-13）**：结构层
`selection_recovery`（Bareinboim-Pearl 选择后门，定理3.5）此前只出**恢复公式**，
从不出数；且 estimate() 在选择偏倚在场时会**悄悄跑普通后门、吐一个有偏数**
（实测 X→Y,X→W,Y→M,M→W 限制在 W：真 ATE 0.40，却吐 backdoor_logistic 0.28，
还标 numerically_solved，跟同结果自己的 selection_recovery 判决矛盾）。先实测
坐实此 bug，再修：**结构定理**——真选择对撞下 X、Y 都是 S 的祖先，堵被打开的
S–Y 路径只能调整 S 的祖先，祖先必与 S 相关，故 P(z⁺)/P(z⁻|x,z⁺) 权重**永远**
无法从有偏样本本身估出（暴力搜 1385 个对撞场景，「有偏样本独立可算」的=0），
必须外部无偏参考数据。故 `estimate(program, biased, reference_data=ref)` 新增第二
DataFrame 通道（论文的 unbiased sample T）：有偏样本给 S 条件分层均值
E[Y|x,z,S]，参考样本给权重，`estimation/selection.py` 按定理3.5 求
μ(x)=Σ_{z⁺}[Σ_{z⁻} E_biased[Y|x,z,S]·P_ref(z⁻|x,z⁺)]·P_ref(z⁺)、ATE=μ(1)−μ(0)。
**诚实门**：选择偏倚在场 → 永不落到普通后门；不可恢复(Hernán)→`not_recoverable`、
可恢复但没给参考数据→`external_data_required`（点名所缺外部数据、withhold 有偏
数），仅在给了参考数据且离散可算时出恢复数并翻 numerically_solved。
`verify_selection_recovery_numeric` 从记录的每层 (n,y_sum) 计数 + 外部权重表**独立
重跑定理3.5 求和**核对 ATE/两臂/权重归一，拒伪造点/篡改层（不 import 生产器、
不碰原数据）。取舍：二值处理 X（多值推迟）、离散调整集、数值/二值结局；参考数据
需带权重列。D1 双 oracle：∅,Z⁻（真 0.40）+ Z⁺,Z⁻ 带混杂（真 0.30），两法一致而
朴素有偏偏离；12-seed 无偏（均值 0.4004）。MCP 12→**13**（+reference_csv_path、
+themis_verify_selection_recovery_numeric，四处清单镜像同步）；schema 加
selection_backdoor_recovery method + selection_recovery_numeric 子块 +
external_data_required 等 failure_type；+16 测试；基线 2811→**2827**。

**中介 four-way 验证器强化（2026-07-13）**：差值尺度 `four_way_decomposition`
与 Imai NDE/NIE 此前只做构造不变量检查（TE = 各部分之和；比例 = 比值），
一个**完全自洽的伪造**（各分量与 te 同乘一个因子）能原样通过 verify——已被
一个「通过」的测试固化的洞。修法=记录该分解本就是其闭式函数的**充分统计量**：
估计器现在把六个标准化 cell means（p_am=E[Y|A,M]、q_a=E[M|A]，g-formula 标准化）
记进 `four_way_decomposition.sufficient_statistics.cell_means`，验证器用
VanderWeele 14.1b 的**独立转写**从中重导 CDE/INTref/INTmed/PIE/TE 并拒任何篡改
（对标 four_way_ratio 锚定拟合系数）。同一组 cell means 在**线性**路径上也钉死
NDE/NIE（PNDE=CDE+INTref、TNIE=INTmed+PIE 与报告值逐位相等，1e-16；线性使
plug-in E[M|X] 等于 m∈{0,1} 混合）；**logit** 路径的 NDE/NIE 来自对 M 的
蒙特卡洛积分，{0,1} cell means 钉不住，故该块保持不变量级——诚实天花板，
现在显式声明而非套用到两块。cell means 缺失（手搓/旧块）时回退到构造不变量，
不强制任何生产者提供。schema 给 four_way_decomposition 加 sufficient_statistics
子对象；+5 测试；基线 2827→**2832**。

**缺失数据 recovered-ATE 数值验证器（2026-07-13）**：§S9.2 的
`estimate_recovered_ate` 出的数此前**零逐数审计**——它挂在 `needs_investigation`
结果上、**无 derivation**，所以 derivation 门控的 `themis.verify` 直接以"没有
推理链无法审计"退出、够不到它；结构验证器 `verify_missing_data_recovery` 只重导
m-graph/可恢复性判决，从不碰那个数。**伪造 point 原样通过**（实测坐实）。照
选择偏倚数值端同法补：估计器现在把 g-formula 求和所用的**每层充分统计量**记进
`recovered_ate.sufficient_statistics`——恢复估计（+朴素 listwise 对照）各一张
conditional_strata（每个 (arm,z) 一条 `{z,arm,n,y_sum}`，故 E[Y|arm,z]=y_sum/n）
+marginal（`{z,count}`+marginal_total，故 P(z)=count/total），是 `_gformula_ate`
**实际求和的那些格**（穿参收集，bootstrap 热循环跳过零开销）。新公开验证器
`verify_missing_data_numeric` 独立重跑 `Σ_z (E[Y|1,z]−E[Y|0,z])·P(z)`（第二份
独立转写、不 import 生产器也不碰原数据），核对 point、recovered_ate.point 回显、
朴素对照、marginal 归一（计数须等于 total→丢层被抓）、每层两臂齐全，拒伪造 point
或篡改层。诚实边界：记录的计数取信（由 data_hash 锚定）不从数据重算。接成公开
kernel 函数 + MCP 工具 `themis_verify_missing_data_numeric`（MCP 13→**14**，四处
清单镜像同步），与 `verify_selection_recovery_numeric` 对等；schema 加
recovered_ate.sufficient_statistics（新 $def gformulaFactorStats）；+20 测试；
基线 2832→**2852**。

**过度识别 IV + Sargan 检验（2026-07-13，候选 F）**：IV 层此前**硬锁单工具**
（`iv.py` `instrument: str`、2SLS 单列、AR 标量二次；`sargan|hansen|overid|gmm`
全仓零命中）。实测坐实：图里声明两个合法工具时，dispatch 取 `iv_sets()[0]` 只用
z1、**默默丢弃 z2**，也从不做过度识别检验（数据无从反驳工具集）。落地=真正的新
能力：估计器 `estimate_iv_overid`（多工具 2SLS + **Sargan (1958) 过度识别检验**
J=n·(û'P_Z û)/(û'û)~χ²(q−1)，**小 p 值反驳工具集的联合有效性=线性/连续版的
Balke-Pearl 工具不等式**；点、J、联合 first-stage F 都是残差二阶矩的闭式，D1 用
独立全矩阵 2SLS+Sargan oracle 钉到 1e-8）。dispatch 按**相同最小 W 分组**：同一
conditioning 下 ≥2 工具→过度识别路径（退化则回退单工具，单工具路径逐字不变）。
验证器双层：派生终端 `numeric_iv_overid_estimate`（元数据+结构许可：每个工具都要
有 `iv_criterion_check` 见证）+ 强数值端 `verify_iv_overid_numeric`（从记录的残差
矩阵**独立转写**重导点+J+p，拒伪造点/篡改 J/篡改矩；因矩阵不进 derivation-input
序列化故由 kernel.verify 对 iv_2sls_overid 单独调用，仿 longitudinal 先例）。
Sargan 拒绝时挂 `overidentification_rejected` gap（新 GapKind，important 必披露，
gap_kind 32→33）。schema 加 `iv_2sls_overid` method+`over_identification` 块（含
sufficient_statistics 残差矩阵）；取舍（声明）=齐方差 Sargan（Hansen 稳健 J 推迟，
仿齐方差 AR）·单内生变量·多工具弱识别 AR 集推迟（q>1 几何 LARGE）。MCP 工具数
不变（走 kernel.verify 无需新工具）；+27 测试→**2879**。

**测量误差混淆矩阵求逆（2026-07-13，候选 E）**：测量误差此前**只有定性 gap 警告**
（`measurement_error_concern`：识别路径上有变量声明自报/问卷/单次测量→挂 ⚠"回归稀
释使你的估计有偏，做 RCT/重测/衰减敏感性"），估计层**零校正**（`rogan|gladen|
misclassif|confusion` 全仓零命中）；实测坐实：即便用户手握验证研究给的误分类率，
Themis 也无法把真效应反解回来，gap 描述明写"不做去衰减估计"。落地=真正的新能力：
被误分类的**离散结局**给定验证过的混淆矩阵 M（列随机 M[i][j]=P(Y=state_i|Y*=state_j)），
在**非差异误分类**假设下（Y⊥(X,Z)|Y*，各臂各层同一 M）逐后门层求逆 p_true=M⁻¹p_obs
恢复真实分布，再对目标值 y* 做后门标准化 ATE=Σ_z[p_true(y*|1,z)−p_true(y*|0,z)]P(z)；
二值结局即逐层 **Rogan-Gladen (1978)**，整体塌成 naive_ATE/det(M)（det=Se+Sp−1=经典
衰减因子，反着用）。接口=`estimate(misclassification={outcome:{confusion_matrix,
states}})`，混淆矩阵是**载荷性外部输入**（验证研究），与 `reference_data` 平行、只在
estimate 时用、噪声数据本身识别不出——不碰 AST/新 statement 类型（VariableDeclaration
契约明说"不改数值输出"故放不得）。估计器 `estimate_measurement_correction`（`measurement.py`）
含奇异矩阵拒绝（|det|<1e-6 仿 proximal rank guard）、out_of_simplex 诊断（报矩估计不裁剪）、
positivity 拒绝、M 固定的 bootstrap CI。dispatch 按结局是否有 spec 路由（抢在朴素后门前；
拒绝记 estimator_failure 不悄悄吐衰减朴素点）。双层验证：派生终端
`numeric_measurement_correction_estimate`（元数据+`backdoor_criterion` 结构许可）+ 强数值端
`verify_measurement_correction_numeric`（从记录的混淆矩阵+每层值计数向量+边际计数**独立
重新求逆**重导校正点/朴素点/det，拒伪造点、非列随机或 det 不符的矩阵、丢层、篡改计数、
缺臂；矩阵不进 derivation-input 序列化故由 kernel.verify 对 measurement_error_correction
单独调用，仿 iv_overid/longitudinal 先例）。gap 描述软化为"有验证混淆矩阵则数值层可去衰减
校正"。取舍（声明）=仅结局误分类·仅非差异·矩阵视为固定（验证研究对 M 的不确定性不传播）·
仅离散结局（暴露误分类/差异矩阵/连续误测的 regression calibration/SIMEX 仍属 gap 领域）。
D1=合成 SCM 模拟潜在真结局，真后门 RD 已知；校正估计（只见 Se/Sp 信道后的观测 Y）恢复它、
朴素被 det 衰减；交叉验证=全 M⁻¹+取目标分量==代数独立的标量 Rogan-Gladen naive/det。MCP
工具数不变（走 kernel.verify）；+23 测试→**2902**。

**非二值处理 Manski 自然界限（候选 C，2026-07-13）**：partial-identification（bounds）
层此前对**非布尔处理**整层跳过——调度器 `_attach_bounds_result` 顶部 `if not
intervention_is_bool: return` 把多值处理（如 `do(dose=2)`）连无假设的 Manski 下限都挡掉，
尽管单臂自然界 `P(Y=y|do(X=x)) ∈ [P(Y=y,X=x), P(Y=y,X=x)+P(X≠x)]` 与处理基数无关。这是
「门控非数学」：数值算术 `_manski_natural_arm` 用 `~x_eq`（`X≠x`）对多值**已对**，符号层
`_negate` 却吐废字符串 `NOT_2`（`P(X=NOT_2)` 错，应是全体其它臂汇总的 `P(X≠2)`），验证器也
硬门 `if not isinstance(intervention_val, bool): raise`。四层协调修正：①调度器解顶层门，
BP（16 型响应函数）/MTR（有序层单调包络）仍各自门控在布尔——多值处理落到无假设 Manski 地板；
新增**处理侧离散门** `_intervention_arm_is_discrete`（把 `_target_event_is_discrete` 抽成
共用 `_event_is_discrete`），未声明离散域的连续点干预不挂平凡 `[0,1]` 界。②符号层
`_complement_mass` 助手：布尔→单一另一臂 `P(X=¬x)`（不变），多值→汇总不等式 `P(X≠x)`。
③数值层 `evaluate_manski_natural_bounds` 记录三个臂计数 `{n, n_joint_target_arm,
n_other_arm}` 作充分统计量。④验证器 `verify_manski_natural_bounds_result` 接受非布尔干预、
镜像补臂表达式，并新增 `_rederive_manski_natural_numeric` 从记录计数**独立重导**
lower=n_joint/n、upper=(n_joint+n_other)/n + 臂划分不变量 n_joint+n_other≤n + n==sample_size
（把 Manski 数值端从仅元数据审计升级为强重导；对多值尤其关键——汇总补臂质量 `P(X≠x)` 是多个
层之和，元数据审计验不出伪造宽度，重导能）。取舍（声明）=仅 Manski 自然界·多值处理 MTR
（单调包络）与 Balke-Pearl（16 型响应函数）仍是二值处理构造故推迟〔**Balke-Pearl 这一半已在
#320 结掉**：16 是 `|X|^{|Z|}·|Y|^{|X|}` 在全二值时的取值，不是构造的前提〕·多层**对比**界
`[L_a−U_b, U_a−L_b]`（需对比查询类型=结构改动）推迟。D1=合成 3 值 dose SCM，数值端逐位对
手算 `n_joint/n`、`(n_joint+n_other)/n` 一致；verify 接受诚实、拒篡改补臂表达式/伪造 off-arm
计数/臂划分违反/计数-样本量不符。MCP 工具数不变；+15 测试→**2917**。

**异方差稳健 Hansen J 过度识别检验（2026-07-13）**：过度识别 2SLS 此前只算
**同方差 Sargan (1958) J**——iv.py 白纸黑字写着「the heteroskedasticity-robust
Hansen J is deferred (declared)」。异方差（或聚类）数据下 Sargan 用了**错误的
权重矩阵**，其对工具集的证伪不可信。探针坐实非装饰性：3 工具异方差设计下
Sargan J=0.038 vs Hansen J=0.032（差 ~17%）、高效 GMM 点(1.433)异于 2SLS(1.431)，
同方差下两者重合。补上高效两步 GMM 的 **Hansen (1982) J**（Sargan 的稳健推广）：
同 H0（q 个工具联合有效）、同 χ²(q−1) 零分布，但用稳健矩方差矩阵
`Ŝ=(1/n)Σûᵢ²zᵢzᵢ'`（聚类声明下走聚类稳健 CR0 和）替代同方差 σ²(Z'Z)。头条 `point`
仍 2SLS（同方差下相同），高效 GMM 点作诊断副产品记录；Hansen 是**附加项**，Ŝ 奇异
时 2SLS+Sargan 估计原样保留（hansen=None，向后兼容零破坏）。①iv.py：`HansenJTest`
+ `hansen` 字段，残差化抽成 `_residualise_iv_columns`/`_moments_from_arrays`，
`_robust_weight_matrix`（HC0/聚类 CR0）、`solve_hansen_from_s`（producer 转写）、
`_hansen_robust_j` 把 Ŝ 记进矩字典。②dispatch.py：发射 hansen_* 五字段；
**过度识别 gap 改由稳健 Hansen J 驱动**（可用时，复用既有 `overidentification_rejected`
kind=不新增 GapKind），Sargan 并列显示，Ŝ 奇异才回退 Sargan。③verify.py：
`verify_iv_overid_numeric` 增独立 Hansen 重导——从记录的 Ŝ + 交叉矩**第二次独立转写**
重导高效 GMM 点 + J，加 Ŝ 对称-PSD 校验（否则重导 J 非合法 χ²）；条件于 hansen_j 存在
故老的仅-Sargan 块仍验；从 kernel 自动触发。④schema：hansen_* + s_robust 全可选；
response_rendering：优先稳健 Hansen p 值，Sargan/Hansen 分歧本身有信息（结论依赖同方差）。
取舍（声明）=单内生回归元·HC0/CR0 无有限样本乘子·多内生推迟。D1=独立高效两步 GMM
oracle（step1 全矩阵 2SLS、Ŝ 显式残差化）重导 Hansen J + GMM 点 <1e-7；同方差重合、
异方差发散；verify 拒伪造 hansen_j/GMM 点/dof、非 PSD/非对称/缺失 Ŝ、不符拒绝标志；
聚类 CR0 权异于 HC0 且自洽。+15 测试→**2932**。

**多工具弱识别 Anderson-Rubin 置信集（2026-07-13）**：过度识别路径能**检测**
联合弱识别（联合 F），但它唯一的区间是 bootstrap CI——与恰好识别情形一样，工具
联合弱时 bootstrap **失效**（这正是单工具 AR `b2c07d4` 要替换的问题），过度识别侧
此前没有对应的弱识别稳健集。关键认识：对**单个内生回归元** + q 个工具，AR 统计量
仍是 β0 的**二次式之比**——q 维投影只改系数不改代数——故集合仍是一条二次不等式
的解，同样五种 Dufour 形态（向量-β 的二次曲面几何只在**多个内生回归元**时才出现，
而过度识别路径本就单内生）。补上 `anderson_rubin_overid_set`：投影二次型
`P_yy/P_xy/P_xx=z·'(Z'Z)⁻¹z·` 给出 `N(β0)=e'P_Z e`，临界值 `κ=q·F(q,m)`
（m=n−|W|−q−1，单工具的 `F(1,m)` 的推广），反演 `AR≤F(q,m)` 得
`A·β0²+B·β0+C≤0`，复用 `_ar_solve_set`。q=1 时**精确**退化为单工具 AR。与恰好识别
集不同，过度识别集可为**空**（无 β0 满足全部 q 条矩约束=过度识别拒绝**显现在集合
几何里**），且 2SLS 点**不必**落在集合内（违反时 N(point)=û'P_Z û>0）。①iv.py：
`OverIDARConfidenceSet` + `anderson_rubin_overid_set`（moments 字典的纯闭式）+
`OverIDIVEstimate.anderson_rubin` 字段。②dispatch.py：发射
`anderson_rubin_confidence_set`（kind/lower/upper/point/kappa/dof_num/dof_denom），
联合 F 弱时 `weak_iv_instrument` gap 指向 AR 集作为 bootstrap CI 的诚实替代（与单
工具 `_attach_weak_iv_warning_if_low_f` 对齐）。③verify.py：`verify_iv_overid_numeric`
增独立 AR 重导——从**同一批**记录矩阵重导 P_yy/P_xy/P_xx，用验证器自有二次分类器
（rules `_ar_solve_set_verifier`）重解，核对 kind+端点+`κ=q·F(q,m)`+2SLS 点（**不**
强制点在集内）；条件于 AR 块存在故退化设计无 AR 集仍验。④schema：kappa/dof_num/
dof_denom 全可选（单工具路径不发），描述含 empty 形态与「点不必在集内」。取舍（声明）=
齐方差 AR·单内生·单 β 标量集（向量-β 二次曲面推迟）。D1=网格反演（6001 点，闭式集
== 直接 AR 测试成员，含条件集 W）+ q=1 精确退化 + 覆盖率仿真（有效工具 95% AR 集
覆盖真值 ~96.5%）+ 空集⟺Sargan 拒绝；verify 拒伪造 kind/lower/upper/kappa/point/
dof。+17 测试→**2949**。

**异方差稳健 Anderson-Rubin 置信集（Stock-Wright S，2026-07-13）**：上一条的多工具
AR 集 docstring 白纸黑字写「homoskedastic」——异方差（或聚类）下它和 Sargan 一样用
错权重（Sargan vs 稳健 Hansen J 的同一缺陷），覆盖率失准。补上**异方差稳健 AR 集**
（Stock-Wright 2000 S / Kleibergen 2005），同时对**弱识别和异方差**稳健：反演
`AR_r(β0)=n·ḡ(β0)'Ŝ(β0)⁻¹ḡ(β0) ~ χ²(q)`，稳健权
`Ŝ(β0)=(1/n)Σ(yᵢ−β0xᵢ)²zᵢzᵢ' = S0 − β0·S1 + β0²·S2`（三个 q×q 矩阵；聚类下走 CR0
簇和）。**关键=可验证性**：因 Ŝ(β0) 依赖 β0，AR_r 非二次式之比、集合无闭式——但
边界 `{AR_r=crit}` 恰是**一个 ≤2q 次多项式 P=N−crit·D 的实根**（`np.roots` 精确且
完备，不漏根），且 Ŝ(β0)=Σ(非负)²zz' 对所有 β0 PSD → AR_r 处处有限、两侧共享有限
渐近线 `L∞=(1/n)zx'S2⁻¹zx`（弱识别信号：L∞≤crit → 集合无界）。集合表示为 **segments
区间列表**（可 bounded/disconnected 双射线/whole_line/empty/union）。①iv.py：
`RobustARConfidenceSet`+`robust_anderson_rubin_overid_set`（Chebyshev 拟合 P 系数→
chebroots→按渐近线分类；自洽守卫拒不可靠数值→None）+`_robust_moment_matrices`(HC0/CR0)
+`robust_ar_statistic`；`robust_anderson_rubin` 字段。②dispatch.py：发射
`robust_anderson_rubin_confidence_set`+联合 F 弱时 `weak_iv_instrument` gap **优先**指向
稳健 AR 集（弱识别 AND 异方差都稳健）。③verify.py：`verify_iv_overid_numeric` 增独立
稳健重导——从记录的 S0/S1/S2 **第二次转写** AR_r，(a) 每 crossing 核在边界 AR_r≈crit、
(b) 重导 crit=χ²(q)+渐近线、(c) 从 crossings+渐近线重建 segments 核对、(d) **独立密集
网格成员扫描**（与生产者精确多项式根**不同方法**）核完备性防漏根。④schema：s0/s1/s2
进 sufficient_statistics + robust_ar 块全可选；response_rendering：弱工具下优先稳健 AR，
与同方差分歧则结论依赖同方差假设。取舍（声明）=χ²(q) 渐近（无有限样本 F 修正）·单内生·
单 β 标量集。D1=网格反演 vs 闭集（raw-data AR_r 与 S 矩阵形式 1e-7 一致）+ 异方差覆盖率
仿真（**稳健 0.955 vs 同方差 0.855**=收官全部价值）+ 空⟺无界渐近线信号 + 聚类 CR0；
verify 拒伪造 crossing/segment/asymptote/crit、篡改 S0、**漏 crossing（网格扫描逮）**、
缺 S 矩阵。+15→**2964**。

**暴露误分类矩阵法（2026-07-14）**：测量误差校正此前只做**结局**误分类（Rogan-Gladen
`a64fc38`），docstring 明写"暴露误分类是不同的校正、推迟"。探针坐实缺口：潜 X*→Y SCM +
混杂 Z，暴露非差异误分类，themis 对 `misclassification={暴露变量名:...}` **静默忽略**→
照发 `backdoor_logistic` 衰减点 0.137（真值 0.198，衰减 ~31%），只挂软
`measurement_error_concern` gap——正是护城河要拦的"静默错误答案"。补**矩阵法**
（Barron 1977 / Greenland 1988 / Marshall 1990）：非差异（X⊥(Y,Z)|X*）下沿暴露轴对
(X,Y) 联合**逐结局列求逆** p_true(X*,Y|z)=M⁻¹p_obs(X,Y|z)，再用**恢复的真实暴露**做后门
标准化 ATE=Σ_z[P(Y=y*|X*=1,z)−P(Y=y*|X*=0,z)]P(z)。**关键=暴露侧分母 P(X*=x|z) 本身
也是求逆结果**（非观测计数）→无 naive/det 捷径，故做独立估计器而非结局侧开关；衰减量随
混杂结构变（det 只守可逆性）。①measurement.py：`ExposureMeasurementCorrectionEstimate`
+`estimate_exposure_measurement_correction`（复用矩阵校验/离散/边际助手），新守卫
`degenerate_recovered_exposure`（恢复暴露边际≤0→条件风险未定义→拒）、
`exposure_not_binary`、`continuous_outcome`、positivity。②dispatch.py：`misclassification`
按**变量名**键分派——键=暴露名走 `_try_exposure_measurement_correction_estimate`，
X+Y 都给→合成校正（当时是 `combined_misclassification_deferred` 拒，见下方「两条通道同时误分类」一档）；发 measurement_correction 块
side=exposure + per-stratum 2×k 联合表。③verify.py：
`verify_exposure_measurement_correction_numeric` 从记录的 M+2×k 联合表**第二次转写**沿
暴露轴求逆重导校正/朴素点+det，拒伪造点/非列随机或 det 不符矩阵/篡改联合表/丢层/空臂/
side 篡改；kernel 按 method 触发；复用 `numeric_measurement_correction_estimate` 派生
终端（方法加进白名单）。④schema：method enum + side + outcome_states + strata `oneOf`
（结局 arm/counts/n | 暴露 z/joint_counts）全可选；估计/verifier `__init__` 导出+docstring
清单同步；response_rendering 暴露侧渲染（无 naive/det）；data_gap_report
`measurement_error_concern` 文本升级（结局**或暴露**）。取舍（声明）=仅二值暴露·非差异·
已知固定矩阵·离散结局·后门识别；多值暴露/组合(X+Y)/差异矩阵/连续误测
(regression calibration/SIMEX) 推迟。D1=潜 X* SCM 数值端逐位恢复真 RD（矩阵法 0.197 vs
朴素 0.137 vs 真 0.198）·无 naive/det 捷径核·退化恢复暴露拒。+26→**2990**。

**差异误分类矩阵法（differential misclassification）**：测量误差校正此前只做**非差异**
（各条件层同一矩阵 M），docstring 明写差异矩阵"改变几何、推迟"。探针坐实缺口是**静默做错**
非缺功能：结局误分类**随暴露臂而异**（detection bias）的 SCM 上，今天能做的最好（用"池化
单矩阵"非差异校正）把真值 0.30 "校正"到 0.48（误差 +0.18，**比不校正的 0.36 还差**）——
而且差异误分类可**朝远离零方向偏**（naive 0.36 > 真 0.30），非差异永远朝零衰减，这正是差异
版必须逐层求逆的科学理由。补两个规范差异型：①**结局侧逐暴露臂**矩阵 M_x（detection bias，
`p_true(·|x,z)=M_x⁻¹p_obs`）；②**暴露侧逐结局层**矩阵 M_y（recall bias，对结局 y 的列用
M_y⁻¹ 求逆）。接口=`differential=True` + `confusion_matrices`（对齐 list）+
`differential_levels`（条件变量取值，避 JSON string-key 类型坍缩）；内部统一成 `Minv_by_level`
字典（非差异=各 level 同一矩阵，代码路径归一）。**关键工程坑**：数据契约把二值列强转 bool，
故 `_level_key` 按**值**匹配（0≡False）、记录**规范**结局值让 verifier 对齐。护城河=两个
`verify_*_measurement_correction_numeric` 分支 `suff.differential`，从记录的**每层矩阵**
+2×k/计数表**第二次独立逐层求逆**重导校正点，拒伪造点/篡改某层矩阵（det 不符）/差异标志翻转/
层不覆盖全臂或全结局。schema：top+suff 放开 `confusion_matrices`(_by_arm/_by_outcome)+
`differential`，单 `confusion_matrix`/`det` 改可选（非差异不变）。取舍（声明）=仅二值暴露·
仅结局/暴露轴差异（**协变量差异**推迟）·已知固定矩阵·离散结局·后门识别；组合(X+Y)、多值暴露、
连续误测仍推迟。D1=detection-bias SCM 逐臂恢复真 RD 0.197 vs 真 0.199·recall-bias SCM
0.198 vs 真 0.195·单矩阵校正显著偏（>0.03）·e2e numerically_solved+verify 接受+四类篡改
被拒。+14→**3004**。

**连续误测（regression calibration，2026-07-16）**：测量误差校正此前全是**离散**（混淆
矩阵求逆：结局 Rogan-Gladen、暴露矩阵法、差异矩阵），`measurement.py`/`response_rendering.md`
/`__init__.py` **三处**明写连续误测（regression calibration / SIMEX）推迟、留给
`measurement_error_concern` gap"告诉用户自己去做"。探针坐实是**静默错误答案**非缺功能：连续
暴露被经典加性误差污染（观测 W=X*+U，真值 X*），今天最好的做法（W 上的后门 OLS 斜率）把真值
0.8 的每单位因果斜率发成 **0.398（衰减 ~50%）**、还标 numerically_solved，连混杂 Z 的系数也
被带偏（1.2 vs 真 1.0），且**没有任何校正通道**（`misclassification=` 只吃离散混淆矩阵）。补
**regression calibration 的精确矩量校正**（Carroll 2006 / Rosner-Willett-Spiegelman 1989）：
经典误差只抬高设计协方差中 W 的方差（Σ_WZ=Σ_{X*Z}+E，E=diag(σ²_u,0,…)），而 Cov((W,Z),Y)
不变，故真实结构系数是朴素系数的精确校正 **β_true=(Σ_WZ−E)⁻¹Σ_WZ·b_naive**——离散 M⁻¹ 的连续
对应。暴露分量 βx=对 Z 调整后每单位真实暴露的因果斜率；单暴露即 **βx=b_naive/λ**，λ=1−σ²_u
/Var(W|Z) 是**连续版 det(M)**（可靠比）。接口=**新 kwarg** `measurement_error={暴露名:
{error_variance:σ²_u}}`（与 `misclassification=` 平行、载荷性外部输入），暴露侧；结局/组合连续
误测**诚实拒绝**非静默忽略。守卫：σ²_u≤0、σ²_u≥Var(W|Z)（λ≤0=退化可靠比、Σ_WZ−E 非 PD）、
近离散暴露（指向混淆矩阵法）、奇异设计——全部 refuse 不吐衰减朴素点。derivation **复用**
`numeric_measurement_correction_estimate` 终端（方法白名单加一项，避新终端多处 allowed-finals
同步）；护城河=`verify_regression_calibration_numeric` 从记录的设计协方差 Σ_WZ+Cov((W,Z),Y)
+σ²_u **第二次独立**重解 b=Σ⁻¹cov_DY、β=(Σ−E)⁻¹cov_DY、λ，拒伪造点/naive/reliability、
非对称协方差、σ²_u 令 Σ−E 非 PD 却出点、斜率向量与协方差不符（逮未传播的篡改协方差）；kernel
按 method 自动触发（**MCP 数不变**，无新工具）。取舍（声明）=连续暴露·经典加性误差·**线性**
结局（矩量校正对线性精确）·已知固定 σ²_u·数值协变量；Berkson/差异误差·误测结局或协变量·非线性
结局（SIMEX，模拟外推非闭式故不合逐数复核契约）推迟。D1 双 oracle：矩阵形式 βx=0.7982==单变量
可靠比 b_naive/λ=0.7982（逐位）·恢复真斜率 0.80 vs 朴素 0.40 vs 真 0.8·CI 覆盖·五类篡改被拒。
+19→**3023**。

**连续误测扩到误测协变量/混杂（2026-07-16 续）**：上一档 RC 把 E 硬编码在暴露列
（E=diag(σ²_u,0,…)），误测**混杂**没有校正通道。探针坐实又是**静默错误答案**：真混杂 z→x、
z→y，观测 W_z=z+U_z，对噪声代理 W_z 做后门调整留下**残差混淆**→朴素斜率 **0.835**（真 0.5，
**高估 67% 且偏离零**，与暴露衰减朝零相反）、标 numerically_solved、`measurement_error={z:…}`
被**静默忽略**。泛化=把 E 从"暴露列"推广到**设计矩阵任意列**：同一条
**β_true=(Σ_obs−E)⁻¹Σ_obs·b_naive**，E=diag(σ²_u 放在被误测列)。`error_variance` 参数**多态**
（float=暴露 sugar / dict={变量名:σ²_u}），暴露+混杂组合=E 多个对角非零。**混杂误测无标量可靠比
捷径**（矩阵求逆必需），每列各报 λ_v=1−σ²_uv/Var(V|rest)；退化守卫升级为 **Σ_obs−E 的 Cholesky
PD 检验**（多列时逐列 λ>0 必要不充分）。dispatch 收集非暴露非结局的 spec 为混杂误差、优先选含全部
命名混杂的后门集，命名变量不在设计中→`mismeasured_covariate_not_in_adjustment` 诚实拒绝。
`verify_regression_calibration_numeric` 从记录的 `error_variances`（名→σ²_uv）按 design_vars
索引**重建 E**（关键：否则用 E=0 重导出朴素 β 误拒诚实校正点），去掉"暴露 σ²_u>0"要求（改为
Σe>0）、校标量 error_variance==暴露对角、逐列 λ 交叉核对；误测**结局**/组合仍诚实拒。取舍（声明）
=连续误测变量（暴露和/或混杂）·经典加性·线性·已知固定 σ²_u；误测结局、Berkson/差异、非线性
SIMEX 仍推迟。D1=潜混杂 SCM 恢复真 0.50 vs 残差混淆朴素 0.835·矩量方程残差交叉核·组合 X+Z 恢复
·四守卫·验证器拒伪造点/篡改 σ²_uz。+11→**3034**。

**协变量差异误分类（differential_by，2026-07-16 续）**：差异误分类此前的差异轴**硬编码为暴露臂**
（`Minv_by_arm`，detection bias）；混淆矩阵**随协变量分层而异**（如误分类率随测量地点/年龄）无
校正通道，line 74-75 明写推迟。探针坐实是**静默错误答案**且暴露一枚潜藏 bug：站点 z∈{0,1} 与暴露臂
bool{False,True} **碰撞**→`differential_levels_mismatch` 守卫不触发→把逐站点矩阵 [M0,M1] **静默误读
为逐臂**（M0→control、M1→treated），真 ATE 0.2004 发成 **0.2613（高估 30%）**、标 numerically_solved
无 error。泛化=把差异轴从"永远是暴露臂"推广到**任意命名变量**（新 `differential_by` 字段），与上一档
RC 的 E-列泛化同构：`differential_by=<协变量>` 时 `_formula` 在每个后门层按该协变量取值选矩阵
`Minv_by_level[_level_key(z 中该列值)]`（暴露臂路径 byte-identical 保持，走 `Minv_by_arm`）。混杂-only
时暴露可非二值。守卫：`differential_by_unknown`（非暴露非调整协变量）、`differential_level_uncovered`
（某观测层无矩阵）。**踩坑：数据契约把二值协变量转 np.bool_，`_level_key` 的 isinstance(v,bool) 不认
numpy bool→键 ("s","False") 漏配 ("n",0.0)，须先 `_py()` 归一**（老 bool-coercion 坑复现）。
`verify_measurement_correction_numeric` 加协变量分支：从记录的 `confusion_matrices_by_level`（名→矩阵）
按 adjustment_vars 定位 differential_by 索引、逐层从 z 取该协变量值选矩阵**第二次独立重求逆**，拒伪造点/
篡改层矩阵/differential_by 不符/层未覆盖。取舍（声明）=仅**结局侧**协变量差异；暴露侧（recall）协变量
差异、臂×协变量联合差异、多值暴露仍推迟。D1=逐站点 SCM 恢复真 0.200 vs 池化单矩阵 0.259（RD 随站点
异故池化 mis-weight，恒定 RD 下会抵消）·naive 0.16·e2e flip·verify 拒伪造点/篡改层矩阵/differential_by
翻转。+10→**3044**。

**协变量差异误分类·暴露侧（differential_by，2026-07-16 再续）**：上一档只闭了**结局侧**协变量差异；
**暴露侧**（矩阵法，混淆矩阵随后门协变量分层而异——如暴露测量准确度随地点变）此前差异轴**硬编码为结局**
（recall bias，`Minv_by_outcome` 逐结局列求逆），无协变量差异通道。探针坐实同型**静默错答+潜藏 bug**：站点
z∈{0,1} 与结局值 {0,1} 碰撞→per-site 矩阵 [M0,M1] 经 by-outcome 通道通过覆盖检查、被**静默当 per-outcome
列求逆**，真后门 RD 0.298 发成 **0.324**（冲过头）、标 numerically_solved 无 error（naive 0.173 严重衰减）。
泛化=与结局侧同构：`estimate_exposure_measurement_correction` 加 `differential_by`（默认=结局/recall；
`differential_by=<协变量>` 时每个后门层内用**本层单一 M_z** 对所有结局列求逆）；`_exposure_formula` 统一成
按 `differential_axis` 逐列选矩阵 `Minv_by_level[_level_key(值)]`——结局轴逐列取 M_y，协变量轴每列取
z_key[axis_idx] 对应的 M_z（`_py()` 归一防 np.bool_ 漏配）。守卫：`differential_by_unknown`（=暴露自身/非
结局非调整协变量）、`differential_level_uncovered`。`verify_exposure_measurement_correction_numeric` 加协变量
分支：从 `confusion_matrices_by_level` 按 adjustment_vars 定位 differential_by、逐层从 z 取值选 M_z**第二次
独立重求逆**，拒伪造点/篡改层矩阵/differential_by 不符/层未覆盖。schema 结构本已允许（suff 属性不按 side
门控），仅拓宽描述。取舍（声明）=仅暴露侧协变量差异；臂/结局×协变量联合、组合(暴露+结局)、多值暴露仍推迟。
D1=逐站点 SCM 恢复真 0.20 vs by-outcome 误读 0.32·naive 0.17·e2e flip·verify 拒伪造点/篡改层矩阵/
differential_by 翻转。+11→**3055**。

**条件效应在 ADMG 上静默丢 given（止血，2026-07-16 pivot 后）**：测量误差方向"戏剧性静默错答"矿脉挖尽后转攻更高价值前沿；4 条并行探针
（条件前门/条件 IV/general-ID 条件/ADMG 上 cause·probability）里**前门探针揪出一条戏剧性静默错答**。机制：`scheduler._dispatch_effect` 的 bidirected 分支里
**Tian-in-effect fallback（scheduler.py:3544）无 `observed_atoms` 守卫**——前门分支被 `if not observed_atoms`（3491）门控、IV-in-effect 内部对 conditioning
bail，但 Tian fallback 对**任意** given 都触发；`identify_via_tian` 只算无条件 do(X)、**忽略 given**，识别成功就绑定目标值发数标 numerically_solved。故任何
非后门识别的**条件**效应查询（前门最典型）→静默丢 given→**发边际值当条件值**。独立复现（4M 行 SCM，C 是效应修饰）：`P(Y=1|do(X=1),C=1)`
发 **0.545=边际**（真条件 0.675），ATE 尺度报 0.240（边际）vs 真条件 0.300（~25% 偏）、且 C=0/C=1 报**同一个数**；更糟——`themis.verify` 直接崩溃
（RuleCheckFailed `identify_via_tian requires IdentifyQuery context`）而非拒绝。**止血**=给 Tian fallback 加 `and not observed_atoms` 守卫：条件查询
**诚实拒绝**（needs_investigation，新 MissingItem `query:effect_admg_conditional`，reason 明说"边际被 withheld 而非顶替条件值发出"）而非发边际。非
bidirected 分支/后门条件（`minimal_adjustment_sets(...,given=)`）本就正确处理 given，故止血只动 bidirected Tian fallback 一处。这是分阶段前沿的 **Phase 1
（纠正性）**；Phase 2=条件 general-ID（IDC*）数值端（`identify_via_idc` 已在、验证到 1e-9），把拒绝翻成正确条件值。+2 回归测试（条件拒绝+边际仍解）→**3057**。
（4 探针结论：条件 IV data 路径 2SLS 已正确/仅 theta 拒绝；general-ID 条件诚实拒绝但天真删门=戏剧错答；ADMG 上 cause·probability 是**过度阻断**
——答案本已正确算出，低价值 gate 移除；前门/条件 IDC 是赢家。）

**条件 general-ID（IDC*）数值端（Phase 2，纠正性完成）**：把 Phase 1 的诚实拒绝翻成**正确条件值**。`scheduler._dispatch_effect` 的 bidirected 分支
里，Phase 1 的 `query:effect_admg_conditional` 拒绝换成 IDC-in-effect 数值分支：`observed_atoms` 非空时调 `c_factor.identify_via_idc(graph, bidirected,
x, y, z_atoms, x_value)` 拿到条件估计量（Rule-2 exchange 把可交换 Z 移入 do-set，余项归一化为 `ID(Y∪Z_rem, X') / ID(Z_rem, X')`），再用**新** `c_factor.
bind_idc_values(formula, {Y:y, Z:z...})` 把查询的 Y/Z 值绑进公式（**target 与 given 两侧都绑**——交换掉的 Z 落在 do-context 侧、留下的 Z_rem 既是分子
target 又是链式 conditioning），最后走 `_try_numeric` 对 theta 求值。派生 = `idc_rule2_exchange`(s1) + `identify_via_idc`(s2, 不动符号公式) +
`idc_formula_ast`(s3, 绑值) + `formula_evaluation` + `numeric_result`，镜像 Tian-in-effect 三步前缀。验证器五处接线：(1) `_rule_identify_via_idc` 泛化
接受 **EffectQuery** 上下文（从 ValuedAtom 抽 atom，核心 Rule-2 重放不变）；(2) 新 `_rule_idc_formula_ast` + `_verifier_bind_idc_values` 独立重绑
Y/Z（含 FractionExpr、given 位）比对；(3) `_evaluate_formula` 加 FractionExpr 分支（num/den + positivity 守卫，镜像 runtime）；(4) `formula_evaluation`
类型检查 + `IDENTIFICATION_FORMULA_RULES` 纳入 `idc_formula_ast`；(5) 效应见证清单纳入 `identify_via_idc`。两独立 oracle：潜变量-SCM
（Z→X→M→Y、X↔Y、Z↔Y，Z 存活=真分数）条件恢复到 **1e-9**（`_scm_ground_truth`）；手算前门+效应修饰（C→Y、C 交换掉=非分数）`P(Y=1|do(X=1),C=1)`
=0.8·0.7+0.2·0.2=**0.60**、C=0=0.34、边际=0.47（条件≠边际=Phase 1 拒发的那个戏剧差）。+2 篡改测试（伪造数值→formula_evaluation 独立重算 0.60 拒
0.47；用 unbound holes 顶替 idc_formula_ast 输出→独立重绑拒）。Phase 1 的"条件拒绝"回归测试改判为"IDC 正确求解"。**顺带堵一个同类相邻静默错答**：
`_try_iv_wald_in_effect`（在条件路由里跑在 IDC 之前）的 Wald LATE 是**无条件** complier 效应（查 P(Y|Z)/P(X|Z) 无 given 项），此前对**带 given** 的查询
（有工具+单调性时）会发无条件 LATE 静默丢 given（实证：`P(Y=1|do(X=1),C=1)` 发 0.50=无条件 LATE、丢 C=1）；加 `if q.given: return None` 守卫，
条件查询落到 IDC/诚实拒绝，无条件 IV 查询不受影响仍发 LATE。+回归测试。+新增测试 →**3064**。

**条件 general-ID（IDC）data/pandas 端（2026-07-16，Phase 2 声明的 follow-on）**：Phase 2 把条件效应 `P(Y|do(X),Z=z)` 在 **theta** 路径翻成正确条件值；这一档补 **DataFrame** 路径（`estimation/dispatch.py:_try_general_id_estimate` 此前 `if given_atoms: return False` 诚实 bail=有能力缺口非静默错答）。新 `estimation/general_id.py:estimate_general_id_conditional_ate`：对 do(X) 两臂各调 `c_factor.identify_via_idc(...)` → `bind_idc_values(formula, {Y:y_hi, Z:z...})` 绑值 → 复用无条件路径的 `_point_ate`/`_bootstrap_ci`/`_prob_do`（VE plug-in，`ve_estimate_formula`/`referenced_keys` 早已支持 FractionExpr 含零分母 positivity 守卫），返回**层内条件-ATE 对比** `P(Y=y_hi|do(x_hi),Z=z)−P(Y=y_hi|do(x_lo),Z=z)`（镜像无条件 data 路径出 ATE 而非 theta 路径出点值）。dispatch 按 `given_atoms` 路由（有=IDC/无=Tian，共享下游），numeric_estimate 记 `given` 分层。**验证深度对齐无条件 data 路径**（data-refit 诚实天花板共享——plug-in 算术不重导）：泛化 `_rule_general_id_criterion` 按 **ctx.query.given** 路由（有 given→重跑 `identify_via_idc` 确认可识别=安全关键，无→`identify_via_tian`；conditioning 读自 query 非 producer 输入，防低报 given 绕过更严的 IDC 门），method 枚举加 `general_id_idc_plugin`（rules + schema + response_rendering 三处同步）。取舍（声明）=离散·二值处理/结局·层内对比（与无条件 plug-in 同）·验证器元数据审计（非重导，同所有 data 路径 plug-in）。D1 双 DGP 均落地为**数据**：效应修饰 DGP（前门+C→Y 修饰+X↔Y，C 交换掉=非分数）恢复 ATE(C=1)=0.30/ATE(C=0)=0.18/边际=0.24 三者皆异（对比才暴露的 anti-silent-wrong，加性图会抹平）；潜-SCM DGP（Z 存活=真分数）走 VE 分数端恢复 0.375。+篡改（criterion 谎称不可识别→重跑 IDC 拒、错 method、点越出 CI）+非 IDC 可识别诚实拒绝+无条件仍走前门回归。+14 →**3078**。

**K-treatment 联合干预数值端（2026-07-16）**：联合 `do(A,B,C,…)` 此前**分层不对称**——结构层 `minimal_adjustment_sets_joint`（广义 treatment-SET 后门）本就支持任意 K，但**数值层**（`estimation/joint.py:estimate_joint_effect` + `dispatch.py:_try_joint_estimate`）硬锁 exactly-2，K≥3 静默 no-op=结构证到、数值给不出（诚实缺口非静默错答，同 IDC data-end 同型）。这一档把数值层追上结构层的 K 射程。`estimate_joint_effect` 泛化：结局回归纳入 **饱和 treatment 交互基**（K 个处理的所有非空子集乘积项——K=2 即 `[A,B,A·B]` 字节级等价现状），对 Z 仍线性（同 backdoor.py）；联合对比 = do(全 treated)−do(全 control) 的 g-formula 标准化；交互泛化为 **K 阶（最高阶）混合有限差** `Σ_s (−1)^{#lo(s)} μ(s)`（2^K 角点交替求和，K=2 精确退化为 `(m11−m10)−(m01−m00)`；有限差湮灭所有 <K 阶项+Z 常量，隔离最高阶交互）。dispatch 去掉 `!=2` 改 `<2`/去重守卫；`interaction.order`=K 入 numeric_estimate + schema（`additionalProperties:false` 下同步加 order 属性）。**验证器零改动**——结构 `_rule_joint_backdoor_criterion` + 数值 `_rule_numeric_joint_backdoor_estimate` 本就用 atom-set·K-agnostic、method 名（joint_backdoor_linear/logistic）不随 K 变。取舍（声明）=二值处理·K≤5 上限（饱和基 2^K−1 列的资源界非根本限制，越界诚实 `NotImplementedError`→dispatch no-op→结构层仍 solved）·**只报最高阶交互不报 2..(K−1) 阶层级**·验证器元数据审计（同所有 data-refit plug-in）·latent/ADMG 联合不动仍诚实拒绝。D1：K=3 真 3-way DGP（Y=A+B+C+2·ABC+2Z）恢复联合对比 5.0 / 3 阶交互 2.0；**anti-silent-wrong**=K=3 无 3-way 但有 2-way（γ·AB=1.5）DGP 的 3 阶交互恢复 ~0（把 γ 当 3 阶交互报出=戏剧错答，有限差正确隔离）；K=4 真 4-way 恢复 5.5/1.5；+K=2 回归·verify 往返·schema·篡改（丢 Z→重跑 K-set 联合 criterion 拒、K 阶交互点越 CI 拒）·K<2 及 K>5 及重复列诚实拒绝·K=3 latent 仍 needs_investigation 无数字。+14 →**3092**。

**joint ADMG/latent 调整(2026-07-16,K-treatment 续)**：联合前沿第二半。`minimal_adjustment_sets_joint`(structural_solver.py)此前 `if bidirected: raise NotImplementedError` 拒 latent→scheduler/dispatch 对 latent joint 给 `joint:bidirected_out_of_scope`(能力缺口非静默错答)。这一档把广义(treatment-SET)后门/调整准则从 d-分离**广义为 m-分离**(van der Zander 2019 / Perković 2018,section header 本已引用完备准则、实现只限了 d-sep)。改动:leg(ii)proper back-door graph 阻断检查——bidir 非空用 `_set_m_connected`(建于 `is_m_connected`)否则 `_set_d_connected`(**DAG 路径字节级不变**,`if bidir_eff:` gate);leg(i)forbidden 区(proper causal path+后代)保持 directed-only(bidirected=latent 共因非因果)。**关键洞察=联合干预中和 latent**:`Z→{A,B,Y}, A→Y, B→Y, A↔B` 里 G_pbd 移除 proper-causal 首边 A→Y/B→Y 后,A↔B 后门路被 collider B(Z→B 与 A↔B 双箭头)阻断→`{Z}` 有效;单 do(A) 却需 `{B,Z}`(A↔B→Y 仍开)——**集合准则≠单处理准则之并**。**数值端零改动**:有效调整集喂 `estimate_joint_effect`,g-formula 在 latent 下照样无偏(调整泛函 Σ_z P(Y|X,Z)P(z)=P(Y|do(X)) 在广义准则下成立)→出对比+K 阶交互。验证器 `_rule_joint_backdoor_criterion` 去 bidirected 拒绝、按 ctx.bidirected 路由 m-分离(新 `_verifier_set_m_connected` 建于本地独立 `_verifier_is_m_connected`)。scheduler+dispatch 删已失效 `bidirected_out_of_scope` 死分支。**soundness(非完备)声明**:返回的 Z 必是有效调整集,但只覆盖**可调整识别**子集;ID-可识别但非调整-可识别(前门/c-component for sets)返回空→诚实拒绝。**联合 general-ID 留作 follow-on——ID 引擎(`c_factor._id`/`_IdState`)内部本就集合式(`x/y/do_atoms:frozenset`),public `identify_via_tian` 只包单 atom,故 follow-on 是接线+逐原子值穿线+集合值数值/验证器,非从零**。D1 潜 SCM(U→A,B=A↔B;Z→A,B,Y;Y=A+B+2AB+1.5Z,U 不入 Y)恢复真对比 4.02/交互 2.02(调整 {Z}、U 隐藏)+verify m-分离往返+schema;A↔Y(latent 混杂处理与结局)无调整集→`joint_not_identifiable` 诚实拒绝无数字;DAG 空-bidirected 字节级等价;篡改丢 Z→m-分离重导找到 A←Z→Y 开路拒;单-vs-联合准则对比。+8 →**3100**。

**joint general-ID（2026-07-16，联合前沿第三半=收口）**：latent 调整那档声明的 follow-on。潜混杂让联合 `do(A,B,…)` **无调整集**时，效应仍可能被**集合值 Shpitser-Pearl ID** 点识别（前门 / c-component for sets）——这是单处理 general-ID 逃生层的联合版。此前 `minimal_adjustment_sets_joint` 返回空→scheduler/dispatch 一律 `joint_not_identifiable` 诚实拒绝（能力缺口）；这一档把「无调整集但 ID-可识别」从拒绝翻成正确联合值。**识别端**：`c_factor.identify_via_tian` 重构出 `_run_tian_id(x_set, *, allow_full_line7)` 核心 + 新 `identify_via_tian_joint`（集合值，**compact-shortcut only** `allow_full_line7=False`——napkin 式 nested-ID 的全 Line-7 数值自检是单-atom 的，联合安全起见 PUNT 到不可识别而非冒错）；单处理行为字节级不变（`identify_via_tian` 薄包 `_run_tian_id(frozenset({x}), allow_full_line7=True)`）。单标量 x_value 穿进**每个** do-atom 外层→**均匀角点** do(X=v ∀X)：联合对比取 all-hi/all-lo 两次调用（各均匀），混合角点 do(A=1,B=0) 需逐-atom 绑值=留 v2。**数值端** `estimation/general_id.py:estimate_joint_general_id_ate`（method=`joint_general_id_plugin`）：两均匀角点各 `identify_via_tian_joint`→`_bind_target_value`→复用无条件 plug-in 的 `_point_ate`/`_bootstrap_ci`/`_prob_do`（VE），出**联合对比** `P(Y=y_hi|do(all hi))−P(Y|do(all lo))`；`treatments` 列全向量，**无 joint_effect/interaction 块**（K 阶交互需混合角点）。**接线**：scheduler `_dispatch_joint_effect` 在 `if not joint_sets` 拒绝**前**试 `identify_via_tian_joint`（仅无条件），成则出 STRUCTURALLY_SOLVED derivation `[general_id_criterion, identify_via_general_id]` + `joint_general_id` annotation；dispatch `_try_joint_estimate` 的空-joint_sets 分支加 `_try_joint_general_id_estimate` 回退（复用单-general-ID 的 numeric derivation helper，primary atom 标 x/treatment 槽）。**验证器**：`_rule_general_id_criterion` 按 **ctx.query.extra_interventions** 路由——有 extra→`identify_via_tian_joint` 对**从 query 读的** treatment SET（非 producer 输入，防低报处理集把更难的联合伪装成可识别；条件+联合组合=v1 外→recompute False）；新 `_rule_identify_via_general_id` 终端（镜像 `identify_via_joint_backdoor`，注册进 `_STEP_REF_RULES`+dispatch+`verify_effect_structural` 终端白名单）；`joint_general_id_plugin` 入 `_NUMERIC_GENERAL_ID_METHODS`+schema method 枚举。**顺带堵序列化隐性缺口**：`EffectQuery.extra_interventions` 此前**不 round-trip**（`_query_to_dict`/`_decode_query` 漏），验证器从 ctx.query 读联合集依赖它 JSON 往返——补上（仅非空时 emit，单处理字节级不变）。取舍（声明）=对比-only（无 K 阶交互，需混合角点）·二值+共享二层集处理·均匀角点（do(A=1,B=0) 延后）·compact-shortcut（napkin 式联合 nested-ID PUNT 到诚实拒绝）·无条件-only·验证器元数据审计（同所有 data-refit plug-in）。**soundness 非完备**：只覆盖 shortcut-可表达的集合 ID 子集；表达不了的 PUNT→诚实拒绝，绝不冒错。D1：2×前门潜 SCM（A→Ma→Y,B→Mb→Y,A↔Y,B↔Y；调整必失败）恢复真联合对比 0.526 vs MC-oracle 0.520+verify 集合-ID 往返+schema；**anti-silent-wrong**=bow-arc（A→Y 且 A↔Y）联合既无调整集也无集合 ID→`joint_not_identifiable` 诚实拒绝无数字（criterion 规则直测=重跑集合 ID 拒伪造 identifiable）；可调整 DAG 联合仍走 joint_backdoor（回归）；篡改点越 CI 拒；extra_interventions 序列化往返+单处理 omit。+8 →**3108**。

**SCM 反事实数值端（2026-07-17，4 探针核实的最高价值前沿；用户选"SCM 反事实数值端"）**：因果最高层（Layer-3 反事实）此前**只有 theta/符号端**——`_dispatch_scm_counterfactual`（Pearl Primer §4.2 abduction–action–prediction）要求路径系数**声明在 cause 边上**；系数未声明时 `needs_investigation`（缺 `coefficient:` gap），有 DataFrame 也不拟合。探针坐实=**点识别但未建**（非"多数反事实只可界"的那类——线性 SCM 单位反事实是点）。这一档补数据端：每个内生变量对其图父节点做 **per-node OLS** 拟合结构方程系数（`estimation/scm_counterfactual.py:estimate_scm_counterfactual_point`），单位的外生项从 ObservationStatements abduct，再走**同一条** `runtime.scm_counterfactual.linear_scm_counterfactual` 三步算术出点。**关键洞察=截距无需单独处理**：OLS 含截距 β₀ 吸收 E[U_V]，abduction `U_V=v_obs−Σα·parent_obs=β₀+ε_unit` 自动带回截距，prediction 前推时精确携带——故只喂**斜率**给共享算术即精确复现，零改动 runtime。单位（E=e）仍来自 ObservationStatements（DataFrame 供人群拟合机制，观测钉具体单位），不复用 DataFrame 当单位。接线：dispatch `_estimate_scm_counterfactual_queries`+`_try_scm_counterfactual_estimate`（在 causation 之后，纯增量，声明系数的结构路径仍主），出 `numeric_estimate`（method=`scm_counterfactual_linear_fit`，含 `node_fits`=每节点斜率+**增广法方程矩** XtX/Xty 供验证器重解，+`observed_unit`+bootstrap CI[重采样→**重拟合每方程**→重算点，单位固定]）+ derivation 单终端 `numeric_scm_counterfactual_estimate`+`extensions.scm_counterfactual` 显示副本（target_value/abducted_noise/cf_values）。**强验证器 `verify_scm_counterfactual_numeric`**（非仅元数据审计——遵 regression-calibration/iv-overid 先例，矩阵不进 derivation-input 序列化故由 kernel.verify 按 method 调）：从 ctx.graph+ctx.query **独立**重算 relevant/topo/父集，逐节点从记录矩 `β=solve(XtX,Xty)` **重解 OLS**、核斜率==记录系数+父集==图，再从**重解斜率**+记录单位**独立重跑 abduction-action-prediction** 核点（**不 import 估计器/runtime，验证器自带算术**；只信矩[data_hash 锚定]+单位=data-refit 天花板）；kernel 加 `_verify_scm_counterfactual_extensions_match`（显示副本 target_value==审计点，防单改副本）。metadata 终端规则 `numeric_scm_counterfactual_estimate` 绑 target/intervention 到 **query** 非 producer 输入。schema：method 枚举+`node_fits`/`observed_unit`/`target`/`intervention_var`/`intervention_value` 属性+if/then/else 改三分支（scm 要 target 而非 treatment/outcome）。取舍（声明）=连续线性递归 SCM·单位经 observations 供（非复用 DataFrame）·点+bootstrap CI·秩亏设计（共线父/常量列）诚实 `EstimatorFailure` 拒非最小范数解·非线性机制=不可测建模假设入 ledger 不在此拦。D1：闭式 SCM（z→x→m→y、z→y，系数 .8/1.5/2/.5）恢复 Y_cf=y0+3(x'−x0)=18 vs 拟合 18.01+CI 包住+斜率复现（m~x:1.50、y~(m,z):2.00/0.50、abduction 精确）；声明真系数时 theta 点与数据点一致；篡改系数（重解 OLS 不符拒）/篡改矩 Xty（重解斜率≠记录系数拒）/篡改点+显示副本（重跑 APP 不符拒）/只改显示副本（kernel 交叉核拒）；欠观测单位/秩亏设计诚实无数字。+8 →**3116**。

**交互式等价类定向 — Meek 传播（R1-R4）+ 约束一致性（2026-07-17，Phase 1；用户经"实验对比"逐条逼准后拍板，R4 完备性缺口由用户"改成白盒"追问牵出并修复）**：因果发现只能恢复 CPDAG（Markov 等价类）——骨架 + 对撞能定的方向，其余边**数据定不了向**。外部知识（时序/领域事实/人或 LLM 的答案）能补方向，逻辑上被强制的其余方向再经 **Meek(1995) 规则**传播——**不重碰数据**。此前 Themis **零方向传播代码**（grep 确认，传播全靠 causal-learn 内部）。这一档把传播做成**确定性、算法无关**的原语（`estimation/orientation.py:propagate_orientations`→`OrientationResult`）：**Meek 四条规则 R1-R4** 在**固定骨架**上跑到不动点。**R4 的来历（诚实记录）**：初次落地（ed44373）只写了 R1-R3 并在 docstring 误称"CPDAG 情形 R1-R3 即完备"——这对**裸 pattern** 成立（Meek 1995），但本模块的职责恰是**应用约束（背景知识）**，而一旦约束定了一条数据未定的边，R1-R3 **不完备**（会漏定逻辑上被强制的边——sound 但 incomplete）。用户"既然要 provenance 何不 fork causal-learn 的 Meek 改成白盒"的追问促使读 causal-learn 源码，发现**它也只实现 R1-R3**（parity 测试因此共享同一缺口、抓不到）；遂另造**独立于两者的暴力真值 oracle**（枚举所有与 骨架+对撞+约束 一致的 DAG 取交集=真正被强制的边）坐实缺口，补 R4（经典 kite 形态，Meek 1995 定理背书）后 oracle 复验 **unsound=0 且 incomplete=0（11k+ 随机用例，R4 实触发上百次）**。PAG/潜混杂需 Zhang 2008 更大规则集，**声明推迟**不用不完备规则硬跑。传播另做两件"重跑发现算法"做不到的事：①**冲突检测**——约束与数据确立的对撞矛盾时**不静默应用**，surfacing 成 `conflicts` 交人裁决（重跑会把冲突埋进搜索）；②**来源链** provenance——每条传播出的方向记录强制它的规则（R1-R4）+ 追溯到它最终依赖的根约束（错答的 blast radius 显式可查）。**强验证器 `verify_orientation_propagation`**（`verifier/orientation_rules.py`，kernel/顶层 themis 经 `verify_markov_blanket` 镜像导出）：从记录的输入 CPDAG + 约束**独立第二次转写 R1-R4** + 约束应用/冲突逻辑重算闭包，核 `oriented`/`remaining`/`conflicts` **精确一致** + 每条 provenance 规则确在闭包中成立、roots 皆为已应用约束（**不 import producer、不碰 causal-learn**；R4 也独立转写进验证器，否则会误拒 producer 的合法 R4 边）。**决策由实验定**（非嘴上）：3 组对比坐实自写传播优于回喂重跑——PC 上"重跑带约束"与 Meek 传播 **70/70 逐字节相同**（Meek 定理，非巧合，先前"重跑会改骨架"的猜想被证伪）；**GES/GRaSP 根本无 `background_knowledge`**（重跑不可用→传播是唯一统一解）；构造的**反例**（数据对撞 A→C←B + 答 C→A）证明重跑**静默覆盖数据、埋掉冲突**而后处理**能检测**——冲突检测因此是 P1 的安全底座而非后续。取舍（声明）=CPDAG 情形（causal sufficiency）·**R1-R4**·PAG/FCI 推迟·运行时无库依赖。**oracle 分层（诚实）**：暴力真值 oracle 是**权威**（覆盖含约束/含 R4，抓 unsound + incomplete）；causal-learn 参考 Meek 只实现 R1-R3，**仅**作**无约束裸 CPDAG 补全**的跨库交叉验证，**不能**认证有约束情形。D1：R1/R2/R3/**R4** 各隔离/回归单测（R4 例=答 A→B 经 R4 定 C→D 再连锁解锁 C→E/D→E，R1-R3 全丢）+ 约束传播来源链（roots=[[A,B]]）+ 反例冲突 flagged 不 applied + 验证器拒伪造方向/拒静默应用数据矛盾/拒丢 conflict/**拒丢 R4 边** + **暴力真值 oracle 属性测试（数百随机 CPDAG+约束逐边=真值，含 R4 触发断言）** + **causal-learn 裸 CPDAG parity（≥20 随机图，无约束）**。+14 →**3130**。（后续 Phase 2=等价类→杠杆排序问题集；Phase 3=答案摄取/交互循环/unknown 逃生；LLM 答题骑既有 agent 提议正门。）

**交互式等价类定向 — 杠杆排序问题编译器（2026-07-17，Phase 2；用户"好那就照这个实现"拍板）**：Phase 1 给出 CPDAG 闭包（已定向/仍未定/冲突）后，交互问题是**下一步该问人/LLM 哪几条边、按什么序**。这一档把它编成**排序问题集**（`estimation/orientation_questions.py:compile_orientation_questions`→`QuestionSet`/`OrientationQuestion`；`question_set_to_dict` 供验证器）。两类问题：①**冲突问题优先**——Phase 1 每条冲突（答案与数据确立的对撞矛盾/指向非边）编成一条**必须人裁**的问题，排在最前（它挑战数据已定的事实，是正确性阻断）；②**定向问题按杠杆排序**——每条仍未定的边一问，`leverage`=该边某个答案经 Meek 传播能级联定死的边数（取两方向较大者=最好情形解锁，用于排序），`guaranteed`=两方向都能定死的边数（恒≥1，即它自身），`unlocks`=无论答哪向都被定死的其余边。**杠杆用 Phase 1 传播引擎本身测**（把边分别定两向、跑闭包、数新定边），精确（单答案的 Meek 闭包=所有认同该答案的成员 DAG 共识边）且复用已验证原语——**无枚举爆炸、无大分量兜底**。**关键设计取舍（诚实，用户"照这个实现"前已把根因摊开）**：初版按"最坏情形最小覆盖集"设计，但 **20000 随机 CPDAG 实测：任何单边的最坏情形（保证）杠杆恒=1**——CPDAG 链分量里没有哪个单答案能不论方向都强制第二条边，故"最坏情形覆盖集"退化成"问每条边"=空洞声明。退一步看根因：交互工具是**一问一答循环**（问 top→喂回 propagate 级联→重编译剩余），真正有用的杠杆是**最好情形级联潜力**非最坏保证。遂改成"全部剩余边按最好情形级联降序"——**排序**而非抠更小子集，且不少报问题数（早答级联通常让后面的边在重编译时自动掉出，实际问的远少于全表）。**强验证器 `verify_orientation_questions`**（`verifier/orientation_question_rules.py`，kernel/顶层 themis 经专用入口镜像，parallel `verify_orientation_propagation`）：从记录的 post-propagation CPDAG **独立第二次转写 R1-R4** 自算每条边两向级联，核 `leverage`/`guaranteed`/`unlocks` 精确一致 + 冲突精确回显 + 每条剩余边恰一问 + 排序确为杠杆降序（**不 import producer、不调 propagate_orientations**）。**oracle 分层（诚实）**：验证器的 Meek 转写与 producer 引擎共享规则集；**测试里的暴力等价类枚举 oracle**（枚举成员、按"给定该答案哪些边恒定"重算 leverage/guaranteed/unlocks）是与两条传播路径**零共享代码**的真正独立判据（R4 教训=独立 oracle 不能是可能同错的另一实现）。取舍（声明）=CPDAG 情形·杠杆=最好情形非最坏保证·排序非最小覆盖·运行时无库依赖。D1：A-B-C 链每边 leverage=2/guaranteed=1（答 A→B 定 B→C）+ 冲突排最前且 prompt 含 override + 一边一问 + 验证器拒抬高杠杆/拒错 guaranteed/拒丢问题/拒伪造冲突/拒非边问题/拒乱序 + **暴力枚举 oracle 属性测试（数百随机 CPDAG 逐边逐数=真值，含 cascade≥2 断言）**。+11 →**3141**。（后续 Phase 3=答案摄取/交互循环/unknown 逃生/provenance 入账本；LLM 答题骑既有 agent 提议正门。）

**交互式等价类定向 — 交互式解决会话（2026-07-17，Phase 3；用户"继续"拍板）**：Phase 1 闭包 + Phase 2 排序问题之上,跑**循环**：摄取答案(人/LLM)→喂回 Phase 1 闭包(级联去掉被定死的边)→重编译 Phase 2 问题→报状态。`estimation/orientation_session.py`：`start_orientation_session`/`ingest_orientation_answers`→`OrientationSession`；`next_questions`(可问子集)；`session_to_dict` 供验证器。**事件溯源**——会话只存 input CPDAG + 有序答案,派生态每次从答案序列**重放**(最易独立验证、内核纯函数)。**内核无 LLM**(答案 JSON 在正门产,内核只校验/应用/审计)。循环做三件一次性 pass 做不到的事：①**unknown 逃生**——答案可 `direction=None`→该边进 `deferred` **永不再问**(逼答=静默错注入口,"不知道"是一等安全出口);只剩 deferred 时 `status=blocked` 交人而非猜。②**修正(latest-wins)**——同边后续答案覆盖前者(人可把 unknown 改成方向、或纠错),只重放。③**来源链**——每条被应用的定向答案记 `source`(llm_proposal/human/temporal_order…)+`entails`(该答案经闭包强制的下游边=错答 blast radius,从 Phase 1 provenance roots 反查),是发现会话级的假设账本(接 query-envelope 的 `assumption_ledger`=发现图**被查询用到时**的既有 `GRAPH_LEARNED_FROM_DATA`/`llm_proposal` GapKind 路径,不在本档重做)。**组合式设计**：会话 artifact 内嵌 Phase 1 `orientation_propagation` + Phase 2 `orientation_question_set` 两个 dict。**强验证器 `verify_orientation_session`**(`verifier/orientation_session_rules.py`,kernel/顶层专用入口)：**委派**给 `verify_orientation_propagation`(审闭包)+ `verify_orientation_questions`(审问题)审两个内嵌 artifact——**不第四次转写 Meek**;自己只审**会话胶水**(全部从答案独立重导):约束=答案的 latest-wins 投影、内嵌 artifact 确是本会话的(同一 input CPDAG/同一 oriented)、deferred=仍未定的 unknown 边、来源链每条已应用答案带真 entails 且拒绝的不冒领、status 正确。**Phase 3 顺带修 Phase 1 潜在缺口(它暴露的)**：`propagate_orientations` 应用约束时**只挡数据矛盾/非边,未挡约束自身成环**——交互循环里人/LLM 可给联合成环的答案(三角形 A→B/B→C/C→A)导致产出**有环图**。补**环守卫**：闭环那条答案(`_is_ancestor(D,b,a)`)flagged `creates_cycle` **不应用**,像冲突一样 surfacing;producer+两个验证器 `_recompute` **三处一致**转写(独立性税)。取舍(声明)=CPDAG·事件溯源重放·会话级账本不重做 query-envelope 接线。D1：单答案 A→B 级联到 resolved(entails=[B→C,C→D]) + unknown 双边→blocked/不再问 + 冲突答案 C→A 拒绝不应用/surfacing + latest-wins(unknown→方向、方向→反向) + **成环答案 flagged creates_cycle**(Phase 1+Phase 3 各一测) + 验证器拒陈旧约束/拒错 deferred/拒伪造 entails/拒冒领拒绝答案/拒错 status/拒篡改内嵌闭包 + **随机答案序列属性测试(数百 CPDAG×多轮混合方向/unknown/修正,逐会话 verify+不变量)**。+15(含 Phase 1 环守卫回归)→**3156**。（后续：Phase 4=数据对撞 CI-独立性侧冲突检测；发现图→查询的 assumption_ledger 接线;LLM 答题骑既有 agent 提议正门。）

**交互式等价类定向 — CI-独立性侧冲突检测（2026-07-17，Phase 4；用户"phase4"拍板）**：Phase 1 只检**方向侧**冲突（约束与数据确立的对撞方向矛盾→`contradicts_data_orientation`）。但一条 unshielded 对撞 a→C←b **同时**依赖两个数据事实：C 处的碰撞（方向），以及 a、b **非相邻**——这正是 CI 检验发现的独立性、也是它"unshielded"因而可定向的前提。此前**独立性侧完全不检**：知识断言"a、b 直接相连"（数据判为独立/无边）只能伪装成对非边的定向约束→得到误导性的 `non_adjacent_pair`（"没这条边可定向"），把实质的数据-知识分歧当打字错，且不点明它抽掉了哪个对撞的前提（grep 确认全仓零 CI-侧冲突检测代码）。这一档补 `propagate_orientations` 的 **`asserted_adjacencies` 输入**：每条断言对照数据的独立性结构——数据判为非相邻的对是 faithfulness 下的独立性发现，断言其相邻即矛盾→`contradicts_independence`；若该非相邻恰是一或多个数据对撞的前提，则 `undermines_collider` 并**点名对撞顶点**（那些方向若相邻为真则失去数据支持）。与方向侧一致，断言**绝不应用**（应用=改骨架=重跑发现，故意越界），只 surfacing 交人。**设计强制的耦合**：新冲突形状（keyed `assertion` 而非 `constraint`）必须一致流经既有通道——Phase 2 `compile_orientation_questions` 把邻接冲突编成**冲突问题**（排最前，prompt 点明对撞）、Phase 3 `start_orientation_session(asserted_adjacencies=)` 作**会话级前置知识**接入循环（否则 producer/session 读 `c["constraint"]` 会对邻接冲突 KeyError=耦合是设计强制非可选）。**三处独立转写一致**（producer + `verify_orientation_propagation` + `verify_orientation_questions` 各自第二次转写 CI-侧检测；session 验证器**委派**这两个并只加断言-邻接 tie 检查=不第五次转写）。**独立 oracle（R4 教训延用）**：属性测试的顶点真值**直接从生成 DAG 的边**推（`(a,z)∈DAG 且 (b,z)∈DAG`），与 producer 从 CPDAG `directed` 集算是不同表示——非相邻对的任一公共子必是 unshielded 对撞顶点故二者恒等。取舍（声明）=CPDAG·断言只 surfacing 不应用·`asserted_adjacencies` 是**会话级前置知识非每轮可改答案类型**（邻接作一等循环答案带 unknown 逃生/latest-wins 留 follow-on）·对称的"数据有边知识说独立"（删边）留 follow-on（本档只做 memory 点名的"数据独立、知识给边"侧）。D1：数据对撞 A→C←B 断言 A-B→undermines_collider 点名 C 且闭包不动 + 无对撞对→contradicts_independence + 既有边断言→无冲突 + 未知节点→flagged + 自邻接 raise + 去重 + 方向侧与邻接侧冲突并存 + 邻接冲突编成排最前的冲突问题 + 会话前置断言成问题且 source_trail/rejected 不受影响 + 验证器拒伪造顶点/降级 reason/捏造冲突/丢冲突/丢冲突问题/session 断言不符 + **随机 CPDAG×随机断言属性测试（DAG-边 oracle 逐断言核 reason+顶点）**。+16 →**3172**。（剩：邻接作一等可改循环答案；删边侧冲突；发现图→查询 assumption_ledger 接线。）

**交互式等价类定向 — 会话→假设账本接线（2026-07-17，Phase 5；用户选"①"）**：Phase 1-4 解决 CPDAG 后,每条定向边带 provenance（强制它的 Meek 规则+它依赖的根约束）,每条已应用答案带 source（llm_proposal/human/temporal_order…）。但这些**都没到查询披露假设的地方**——assumption_ledger,它由 `data_gap_report` 从程序边的 `annotations.source` 喂养（`UNVERIFIED_PROPOSAL_EDGE_ON_QUERY_PATH`=边 source==llm_proposal 且在查询路径上;`GRAPH_LEARNED_FROM_DATA`=图来自发现）。发现图**被查询用到时**会把 LLM 猜的方向当已验证静默呈现（Explore agent 核实:会话完全 standalone,无任何代码把它变成 program/gaps/ledger）。这一档接上两者。`estimation/orientation_ledger.py:orientation_ledger_export` 把每条定向边映射到查询侧**既有识别**的 source 词表（`data_gap_report._is_non_evidence_source`=`llm_proposal` 或 `discovery:*`）,并产出 source 标注的 `cause_statements`——已解决的图丢进 program 就经**零改动**的既有机制触发正确披露。**唯一非直通的是 taint propagation（核心）**:Meek 从一个 llm_proposal 答案**强制**出的边只和那答案一样可信,故也必须披露 llm_proposal——边是 proposal 边 iff 它依赖的**任一**根约束是 llm_proposal 答案（weakest-root-wins）=来源链 blast radius 转成账本 provenance。逐边:数据对撞（或无约束根的 Meek 边）→`data_source`（discovery:* marker）;≥1 llm_proposal 根→`llm_proposal`;仅 trusted（human/temporal/domain）根→单一则该 source 否则 `orientation_multiple`（evidence-backed 无 gap）。**验证器 `verify_orientation_ledger_export`**（`verifier/orientation_ledger_rules.py`,kernel/顶层 themis 镜像）:**委派** `verify_orientation_session` 审内嵌会话（故它据以重导的 provenance/来源链本身受认证,伪造 provenance 混不过）,再**第二次转写** taint 规则独立重导每边 source,核 `edges`/`proposal_edges`/`cause_statements` source/`graph_learned_from_data` 一致——**under-disclosure**（依赖 llm_proposal 答案的边被披露成别的）正是它要抓的。**端到端证明**:导出的 cause_statements 装进 program+query→经**未改动**的 `data_gap_report` 机制触发 `unverified_proposal_edge_on_query_path`+落成 ledger 的 structural_edge 条目;human 解决的图不触发 proposal gap。取舍（声明）=导出产 source 标注的 cause_statements（可查询接缝）+可审计逐边 provenance,装配 variable decls+query 是调用方的活（反正它得给 query）;whole-graph `GRAPH_LEARNED_FROM_DATA` 是上游发现 `discovery_metadata` 的职责（它带 algorithm/alpha/N,会话拿 bare edges 根本不知道,伪造=编造算法;这里逐边给 data 对撞 `data_source` 查询侧已披露+set `graph_learned_from_data` bool 作钩子,真实流里 discovery_metadata 从发现运行带过来）;不改 gap 触发的 trusted 细节仅在多不同 trusted 答案时收成一 marker。D1:taint 链（A→B llm_proposal 级联 B→C/C→D 皆 llm_proposal）+human trusted 无 proposal+数据对撞 discovery:pc+learned+kite R3 weakest-root-wins（llm+human→llm）+orientation_multiple+验证器拒 under-disclosure/伪造 proposal 表/cause source 不符/错 learned 标/坏 data_source/篡改内嵌会话+**两端到端（经 themis.run:proposal gap+ledger 触发;human 图不触发）**。+14 →**3186**。（剩:邻接作一等可改循环答案+删边侧冲突[Phase 4 follow-on];LLM 答题骑既有正门。发现图→查询接线本档完成。）

**交互式等价类定向 — 删边侧冲突检测（2026-07-17，Phase 4 follow-on；用户"继续吧"拍板）**：Phase 4 只做了独立性侧的**一个极性**——"数据判独立/无边、知识断言相邻"（`asserted_adjacencies`）。它的**镜像极性**此前零检测（grep 确认 `contradicts_dependence`/`asserted_absence`/`unshield` 全仓不存在）：**"数据有边、知识断言独立"（删边）**——一条 unshielded 对撞既依赖 a、b 非相邻，也依赖 CI 检验发现的**依赖**（数据没把某对分开=骨架里有边）。领域专家常判某条发现出的边是**假阳**（有限样本 CI 误差/漏测条件集），需 flag "你骨架里这条边我认为是伪的"，Themis 应 surfacing（数据**确实**测到依赖,不静默删=删边就是改骨架=重跑发现）交人裁决。这一档补 `propagate_orientations` 的 **`asserted_absences` 输入**（Phase 4 的平行 start-time 参数,前向兼容后续 per-turn 泛化,零 churn）：断言某对独立——数据判非相邻→**同意数据无冲突**;数据判相邻——若那条边只是裸无向骨架边→`contradicts_dependence`;**若是有向对撞臂**（a→b 且 b 是对撞顶点=另有父 x→b）→`undermines_collider` **点名顶点**（删该边=移一条臂→对撞失数据支持）。**镜像的高危层是有根据的非投机**（对撞在数据里真实存在,不像"删边会**造出**新 unshielded 三元"那样需重测数据才知的推测——那种未做,遵 CLAUDE.md 不为假想需求设计）。与 Phase 4 一致：**绝不应用**只 surfacing。**三处独立转写一致**（producer + `verify_orientation_propagation` + `verify_orientation_questions` 各第二次转写臂检测；session 验证器**委派**并只加 absence tie 检查）。`_conflict_prompt` 加 absence 分支（undermines 版重建臂方向 `{a if x==b else b}→{x}`）;冲突键三分（`constraint`/`assertion`/`absence`）流经问题编译器+会话。**独立 oracle（R4 教训延用）**：属性测试从生成 DAG 直接重算臂性（数据边 a→b 是对撞臂 iff b 另有父 w 且 a、w 非相邻）,与 producer 从 CPDAG `directed` 集算是不同表示、恒等但独立。取舍（声明）=CPDAG·断言只 surfacing 不应用·`asserted_absences` 是**会话级前置知识非每轮可改答案**（邻接[两极性]作一等循环答案带 unknown 逃生/latest-wins 是**唯一剩下的 follow-on**）·只做臂检测的高危层不做投机的"删边造对撞"。D1：对撞臂 A→C 断言删→undermines_collider 点名 C 且闭包不动 + 裸无向边删→contradicts_dependence + 真非相邻断言→无冲突 + 未知节点/自环/去重 + 邻接侧与删边侧冲突并存 + 方向侧与删边侧并存 + absence 冲突编成排最前问题（prompt 含臂/含"drop the edge"）+ 验证器拒伪造/丢弃/降级 reason/伪造顶点/丢冲突问题/session 断言不符 + **随机 CPDAG×随机删边断言属性测试（DAG-边 oracle 逐断言核 reason+顶点，含臂与裸边混合）**。+18 →**3204**。（剩:**邻接（两极性）作一等可改循环答案**[带 unknown 逃生/latest-wins]=交互式等价类定向前沿**唯一剩下的 follow-on**;LLM 答题骑既有正门。）

**交互式等价类定向 — 邻接作一等可改循环答案（2026-07-20，Phase 4 follow-on 收尾；用户"继续吧"拍板）**：Phase 4 + 删边把独立性侧**两个极性**都检了（加边 `asserted_adjacencies` + 删边 `asserted_absences`），但它们都只是 **start-time 定死的会话级前置知识**——不是循环里每轮可改的答案（那时答案只有方向一种）。这一档收尾**前沿唯一剩下的 follow-on**：把邻接（两极性）升成和方向平起平坐的**一等、每轮可改的循环答案**，带自己的 unknown 逃生 + latest-wins。**根设计（最优雅的结构改动，非 append）**：一条答案是关于**一个 pair** 的，做**恰好一个**声明——方向（a→b）/ 邻接极性（`"present"`=加边 / `"absent"`=删边）/ 无（unknown）——三者平权，latest-wins **跨三种 kind 按 pair** 归并。方向喂闭包作约束；邻接极性喂 producer 的 CI-侧/删边冲突检测（surfacing 绝不应用，应用=改骨架）；unknown 延后。**producer 与 Phase-2 编译器/其验证器全部零改动**——它们消费的是 producer 的 `OrientationResult`（effective 两集 + conflicts），对"集从 start-time 还是答案派生"完全无感（本档核实此不变量后只碰 session 层 + session 验证器）。`OrientationAnswer` 加 `adjacency` 字段（与 direction 互斥，第 3 位但全仓构造均 keyword 故无破坏）;`_derive_answer_sets`（原 `_derive_constraints`）按 latest-wins 折出 constraints + 两邻接极性集;`_build` 算 **effective = base 去掉被答复的 pair 再并上答案派生集**（`start` 的 `asserted_*` 降为 **turn-0 base**，per-turn 邻接答案按同一 latest-wins 覆盖），把 effective 喂 producer、把 **base** 存进 session;deferred 收紧成"latest 既非方向也非邻接"。**session 验证器独立重导 effective**（读 base + 答案历史第二次转写同一投影，把内嵌 propagation/question-set 的 asserted 集 tie 到 **effective 而非 base**——喂原始 base 而非答案投影后的 effective 会被抓;under-projection 正是它要抓的），并放宽答案解析认 adjacency（校验值 + direction⊕adjacency 互斥）、deferred 同步收紧。**独立 oracle（R4 教训延用，但此处是定义性折叠非算法闭包）**：属性测试从 base + 答案历史**直接**重算 latest-wins 投影（三处独立转写：producer/`_build` + 验证器 + 测试 oracle 各按"每 pair 最后一条答案定其归属"的语义独立折叠），核 `s.result.asserted_adjacencies`/`asserted_absences` 恒等;Meek 闭包完备性仍由 Phase-1 验证器的暴力 DAG oracle 兜底（不变）。取舍（声明）=CPDAG·邻接答案只 surfacing 不应用·**保留 start-time base 参数并让 per-turn 答案覆盖**（前向兼容既有 Phase-4/删边测试与调用方，非替换）·邻接投影是纯 latest-wins 折叠故三处转写足够（不像 Meek 闭包需真独立暴力 oracle）。D1：per-turn present→CI undermines_collider 点名顶点 + per-turn absent 臂→删边 undermines + 裸边 absent→contradicts_dependence + present 同意数据→无冲突 + present-then-absent latest-wins（翻成同意数据的 absence，冲突消失）+ base 邻接被 absent 答案覆盖 + 邻接答案被 unknown 撤回（回落为 deferred 无向边）+ 方向答案盖过早先 present（升为约束、退出邻接集）+ 方向与邻接答案跨边并存 + direction⊕adjacency 同答案 raise + 非法 adjacency 值/自环 raise + 验证器拒（抹掉 adjacency 字段/翻转极性/篡改 base/同答案给方向+邻接 → effective 不符）+ **随机 CPDAG×随机答案序列（方向/unknown/present/absent 混合、含随机 start-time base）属性测试逐轮核独立 latest-wins 投影 + deferred**。+17 →**3221**。**交互式等价类定向前沿（Phase 1-5 + CI-侧 Phase 4 + 删边 + 本档邻接一等答案）至此全部收口**——剩：LLM 答题骑既有 `themis-causal-check`/agent 正门（非 kernel 活）;PAG/latent（FCI，需 Zhang 2008 规则集，故意越界）。


**非单调 PN/PS/PNS 的数据端界（2026-07-22，`37a2ea0`）**：归因层的数值路径此前在**没有单调性**时整个拒绝——`_try_causation_estimate` 一见 `pn_point is None` 就 `return False`，于是"有 DataFrame + 非单调原因"的用户拿到 `needs_investigation` 加一墙"缺分布"缺口，**尽管同一份经验联合 + 后门 do-risk 已经把无假设的 Tian-Pearl 界（式 24-26）钉死了**；需要"X 从不阻止 Y"的只是**点**识别（式 40-42, Thm 3）。**这是路径分叉不是功能缺失**：theta 路径一直是对的（`_dispatch_causation` 无点时返回 `COUNTERFACTUAL_BOUNDED` 带 PN 区间，`_poc_quantity` 逐量省略 `point`），跑偏的是数据端；本档把它拉回对齐。**通道选 `numeric_estimate.probabilities_of_causation` 而非 `bounds_result`**（后者结构上只装**一个**区间、`estimand` 枚举封闭且 `additionalProperties:false`，装不下三个量；且 `kernel.verify` 只对带 `numeric_estimate` 的 `numerically_solved` 结果跑归因验证器，路由过去等于把答案移出被审计路径），于是 **schema 零改动**——`causationQuantity` 本就把 `point`/`ci_lower`/`ci_upper` 声明成可空、只要求 `lower`/`upper`。**由此确立不变量（两条路径通用）**：归因的答案永远是三个 Tian-Pearl 区间，单调性只决定它们塌不塌成点。估计层给每个区间加**外带** bootstrap（下端点样本取 α 分位、上端点取 1−α，沿用 `bounds_numeric._bootstrap_outer_band` 的 Manski/Balke-Pearl 数据界惯例；单调点 CI 逐位不变=同一批抽样同一套分位计算）；dispatch 省略头条 `point`（schema 里它是 number-only，只能缺席不能为 null）并走界式收尾，把已被满足的分布缺口和解掉、报 `answer_tier="interval"`；验证器去掉硬拒、把**真实** `monotonic` 传进独立 Tian-Pearl 转写（那份转写本来就无条件算界），篡改界值 / 上游 do-risk / 渲染副本三类都被拒；explainer/report 渲染区间答案而不是落到"无可呈现的答案字段"或打印 None 点。取舍（声明）=仅二值原因/结局·do-risk 仍须后门可识别或外生或实验供给·外带 CI 是 bootstrap 产物只做有效性校验（data-refit 天花板）而**界本身强重导**。

**联合中介块的 theta/SCM 数值端（2026-07-22，`8d38bc2`）**：对**一个**中介问分解、对着声明的 CPT 能出数；对**两个**中介问同一个分解，同一张图同一份 theta，只多点了一个中介名，答案就没了——`_dispatch_mediation_joint` 只做识别，并且自己写明 theta 数值端"（把联合中介分布声明成结构系数）是刻意分开、尚未建的一档"。**那个前提是错的，也正是它把这件事显得很大**：块的联合律不需要任何新声明、更不需要独立性假设，因为

```text
P(M1..Mk | X=x, W=w) = ∏_j P(Mj | M_<j, X=x, W=w)
```

是**链式法则**——一个恒等式，而且是 `mediation_potential_outcome_formula` **早就**对调整集 W 用的同一个装置。g-formula 别的地方一个字不用改。而当中介在给定 (X,W) 下条件独立时，数值层那个**图守卫的边际独立归约**会把每个因子解到用户实际声明的 per-mediator CPT 上——那个归约的 docstring 点名的正是这种需求形状。于是平行块从普通 theta 就能求值，链式块则去要图本身命名的那个条件概率。把"中介"从一个原子推广成**有序块**：公式构造器两个中介公式改吃 `mediators`（自然效应公式多出链式乘积和每中介一层求和；受控效应公式只是把它们全部固定——每个中介都被 do 住，故这里不需要链式法则），单元素块逐项复现经典 Pearl 2001 形态；scheduler 的 `_evaluate_mediation_numerically` 同时服务两条分派，`_mediator_block_order` 按拓扑序排块使每个因子顺着结构父子关系跑，CDE 表变成**块的每个参考点**一项（各中介域的笛卡尔积，带上限），键按块序把取值用 `|` 连起来（k=1 时就是裸 `str(value)`）；验证器的独立转写同样推广，并且 `mediation_numeric_evaluate` 新增校验**被求值的块等于 query 声明的中介集**——悄悄少一个中介会产出**内部自洽但回答了另一个问题**的数，这恰恰是只核对数字的重导会确认而不会抓住的东西；块**序**则刻意不钉（链式法则对任意序都精确，凡能求值的序给出同一个值）。`verify_numeric` 的见证清单补 `identify_via_mediation_joint`，否则块一升成 `numerically_solved` 就会被**拒审**。

建这一档时浮出两个缺陷，因块的工作使其可达，一并修在本档：**①生产者从不把图传给 `estimate_formula`**，于是边际独立归约走的是 iter 193"信任用户"分支而非 iter 199 的 d-分离守卫——**守卫只接了验证器侧**。在**链式**块（X→M1→M2→Y，正是块识别专门支持的形状）+ 只声明边际 theta 时，运行时拿 `P(M2|X)` 顶替被要求的 `P(M2|M1,X)`，把 te=0.571 当 `numerically_solved` 报了出去（探针复现）。现在诚实拒绝，并点名缺哪个 CPT、为什么边际不能替代。单中介很少暴露这个洞是因为 `P(M|X)` 通常恰好就是被要的量；块使那个条件量变成常规需求。**②`kernel.verify` 按"status 是 numerically_solved **且**存在 numeric_estimate"路由**，把两件正交的事混为一谈。中介结果可以同时带**两条独立数值通道**——终结于 `numeric_result` 的 theta 求值，加上对同一分解的 DataFrame 估计——拿数据估计去比 theta 派生的终端会**拒掉诚实结果**。改成按派生的**实际终端**路由，两条通道各按自己的方式审计。这在"单中介 + theta + 数据"上本就是坏的（已复现），故一并修好。取舍（声明）=布尔处理（同单中介路径）·块 CDE 参考点上限 16 组、超出报 `too_many_reference_points`·穿过块中**某一个**成员的路径专属分解仍然越界（那是 recanting-witness 不可识别，不是没做）。

**反事实单格从一条一致性恒等式重建（2026-07-22）**：同一个反事实量，经两扇门问会拿到天差地别的答案。经 `causation` 门问 PN = P(Y_{x'}=0 | X=1, Y=1)，得到 Tian-Pearl 无假设界（单调则点）；经 `counterfactual` 门问**同一个量**——没声明 monotonicity 直接 `needs_assumption` 拒绝，声明了则返回 **[0,1] 空洞区间**。**根因不是公式弱，是输入集被人为窄化**：`balke_pearl_bounds_binary_monotone` 只消费观测联合 P(X,Y)，从不索取干预风险 P(Y=1|do(X))，而在那个信息集下 [0,1] 确实是正确答案——单调性单独约束不了 PN。同一内核里 do-风险的识别级联（后门/前门/Tian/ID/IV）一直都在，`causation` 门就在用 `_derive_interventional_risks` 调它，**这条路径没接识别层**。证据在旧代码本身：`_bounds_non_decreasing`/`_bounds_non_increasing` 八个格子中，**返回确定点的四个恰是单调性单独就能定死的格子**（X=1、Y=0、非减 ⟹ Y_0=0），**返回 (0,1) 的两个恰是 PN 格和 PS 格**——空洞与"需要 do-风险"一一对应。

于是不并列写第二套公式，而是把整族归约到一条线性一致性约束。记 `a = P(Y_{x'}=1 | X=x, Y=1)`、`b = P(Y_{x'}=1 | X=x, Y=0)`，则

```text
a·P(x, Y=1) + b·P(x, Y=0) = P(Y=1 | do(x')) − P(x', Y=1)
```

左边是 `P(Y_{x'}=1 | X=x)·P(x)`，右边由 consistency `P(Y_{x'}=1, X=x') = P(Y=1, X=x')` 把 `P(Y_{x'}=1)` 的另一半切掉。**一条方程把两个格子拴在一起，各自住在 [0,1] 盒里，单调性（若声明）把其中一个钉死**——所有答案都是这个小规划对被问格子求解的结果：没有 `factual_target_known` 时目标就是左边除以 P(x)，**是点不是界**（ETT 恒等式）；已知时另一格自由则映成区间（PN 格逐项复现式 25、PS 格复现式 26）；已知且另一格被单调性钉死时方程只剩一个值——**Tian-Pearl 的单调点识别（式 41-42）是它的推论而不是第二次转写**。30000 例随机输入对着独立写成的 `probabilities_of_causation` 交叉验证，PN/PS 界与单调点最大偏差 1.8e-14。

接线：`_dispatch_counterfactual` 去掉 monotonicity 硬门，复用 causation 门的识别机制取 do-风险，并且**只取被问格子真正依赖的那一臂**（抽出 `_derive_interventional_risk_arm`——取另一臂会为答案根本不依赖的信息凭空造出缺口）；同一世界的 consistency 格和被单调性钉死的格**完全不取**（`InterventionalRiskRequired` 点名需要哪一臂，取不到时报 `counterfactual:interventional_risk_unavailable` 而不是返回看着像答案的 [0,1]）。`CounterfactualQuery` 与 `CausationQuery` 对齐，新增 `experimental_risk_treated`/`experimental_risk_control`（混杂但有 RCT 的 Tian-Pearl 药物例形态，两处 schema + validator + 序列化 round-trip）。派生规则更名 `counterfactual_bounds_binary_monotone` → `counterfactual_cell_bounds`（旧名在新语义下说谎）。验证器独立第二次转写恒等式与钉死表，并新增一条真正的可靠性检查：**`interventional_risk_provenance = "not_required"` 必须经得起复核**——验证器自己重算这个格子到底依不依赖 do-风险，否则"不需要"就是自证。风险还要是概率、且不得与 theta 重建的联合矛盾。

顺带修掉一个报告缺陷：`answer_tier` 只读 effect 专用的 `bounds_result` 来判断"手里有没有区间"，而反事实的区间住在 `numeric_result.interval`，于是拿着 [0.625, 0.875] 却报 `none`（无答案可给）。改成两条通道都算数。

取舍（声明）=二值原因/结局（非二值无退路可落，越界即压成 effect 代理）·单世界一次 do·`ResultStatus.NEEDS_ASSUMPTION` 因此**再无生产者**（唯一的生产者就是被拆掉的这道门；状态保留在 envelope 契约里且消费端仍处理，但 data_gap_report/explainer 的三处分支今天不可达，已在枚举处写明）·DataFrame 数据端仍未建（theta 端本档收口，数据端是 `37a2ea0` 的镜像 follow-on）。D1：PN/PS 两扇门逐位一致（无假设界与单调点各一测）·ETT 出点 0.8 而旧路径只能给 [0.3,1.0]·混杂图诚实报缺再由实验风险救回·只供被依赖的那一臂即足·被钉死的格子在效应不可识别时照样出点·消费不了的实验风险（违 consistency）与**被数据推翻的单调性**分别报出而不是 clamp 到边界（判空必须在 clamp **之前**，反序会把空可行集折到边界上报出一个自信的 0 或 1）·四种可答形态全部过独立验证·篡改申报风险与谎称"不需要风险"均被拒。+42 →**3324**。

**反事实单格数据端（2026-07-22）**：上一档声明的镜像 follow-on，本档收口。theta 端从 `theta` 恢复观测联合、跑识别拿一臂 do-风险、交给 `counterfactual_cell_interval` 的一致性恒等式；数据端把**同一个求解器**的两项输入换成经验量——四个观测格用频率，被问格子真正依赖的**那一臂**干预风险用后门标准化（饱和 g-formula）——公式一次都没有再转写。

结构上先做了一步抽取：`estimation/binary_do_risk.py` 拿走 `causation.py` 里的「二值观测联合 + 后门 do-风险」四个函数（`minimal_backdoor_adjustment` / `as_binary_column` / `observational_joint_xy` / `backdoor_do_risk`）。理由不是去重本身：g-formula 在这两个模块里**都不是被检验的定理**（一个检验 Tian-Pearl，一个检验一致性恒等式），把它放在共用的地基上，两边就都只剩下自己那条定理。`causation.py` 行为逐字节不变。

新 `estimation/counterfactual_cell.py`（`estimate_counterfactual_cell` → `CounterfactualCellEstimate`）。数据端相对 theta 端多出来的两样东西都不是装饰：

- **抽样不确定性**。theta 端从声明的分布回答，根本没有抽样误差可言。这里点识别时给点的百分位 CI，区间时给 `[lower, upper]` 的**外带**（Manski / Balke-Pearl 数据界惯例，与 `causation.py` 同一约定）——「区间外面的一条带」和「点外面的一条区间」是两回事，prompt 里专门点名不要混。
- **单调性的推翻率**。求解器在联合与 do-风险在所声明单调性下无解时报空可行集。点估计上这是拒绝；跨 bootstrap 重抽样时，**被推翻的那部分抽样占比**是「这条通常被称作不可检验的假设，离被这份数据推翻有多近」的有限样本度量——theta 端根本表达不出来。它被计数上报（`bootstrap_draws_infeasible`），不是静默跳过。

`interventional_risk_provenance` 五值，且每一个都是**可复核的断言**而非自述：`not_required`（两世界重合，一致性直接回答）/ `pinned_by_monotonicity`（do-风险不可得，但单调性把这一格钉死了）/ `user_experimental` / `exogenous` / `backdoor_adjustment`。前两个是「没用干预风险」，验证器从 `ctx.query` 自己重算这两条理由成不成立——否则「不需要」就是自证。

接线：`dispatch._estimate_counterfactual_cell_queries` 纯加法（任何拒绝都原样保留结构答案）；派生 `numeric_counterfactual_cell_estimate`；`numeric_estimate.counterfactual_cell` 子块 + schema；`extensions.counterfactual_cell` 显示副本 + 解释器渲染（此前 `numerically_solved` 的反事实会掉进「结果未分类」）；kernel.verify 按 status 路由到新的 `verify_counterfactual_cell_numeric` + 显示副本一致性检查。验证器侧把上一档的恒等式转写抽成 `_solve_counterfactual_cell_for_verifier(query, joint, ...)`，两个入口（theta 端符号恢复联合 / 数据端上报经验联合）共用**同一次**转写，新增的数据端规则再独立复核 provenance、调整集可容许性、区间是否真的塌成点、CI 是否夹住点。

顺带修掉上一档自己造成的一处陈述失真：`counterfactual_identification_assumption_required` 这条 caveat 还写着「当走 monotone bounds 时还需要…单调性」——那是 `balke_pearl_bounds_binary_monotone` 时代的因果链（单调性 ⟹ 有界）。重建之后单调性只是收紧区间的可选约束，真正被继承的新前提是**干预风险凭什么成立**（调整集充分 / 来自随机实验）。按「总是需要 / 条件需要」两层重写。

取舍（声明，其中「只走后门」已被下一档取消）=二值 X、Y·反事实必须干预**被观测的同一个变量**·干预风险只走后门（前门 / IV / general-ID 数据路径未接，镜像 `causation.py` 的同一边界）·调整集须离散且被问那一臂在每层有支撑。D1：**两扇门在同一份 DataFrame 上逐位一致**（PN 界、PS 界、单调 PN 点各一测，1e-12）·**独立真值 oracle 是数着生成器的潜在结果**而不是再跑一遍恒等式（ETT 点、单调 PN 点各恢复真值到 0.01；非单调 SCM 上无假设区间覆盖真值且下界真的咬得住）·**只取被依赖的那一臂**（构造了一份「另一臂有 positivity 空洞」的数据：本格照样出答案，而需要两臂的 causation 门在同一份数据上正确拒绝）·同世界格完全不取风险·潜混杂下诚实拒绝、被单调性钉死时照样出点、实验风险救回·违 consistency 的风险与被推翻的单调性分别拒绝·bootstrap 推翻率非零·篡改区间 / 风险 / 谎称 not_required / 谎称 pinned / 不可容许调整集 / 非塌区间上claim 点 / 篡改显示副本全部被拒。+32 →**3356**。

**反事实单格的干预风险接上 general ID（2026-07-22）**：上一档声明的三条 follow-on 里的第一条。跨世界的格子消费一臂 `P(Y=1|do x')`；此前它只能来自后门调整集或随机实验，**没有可用调整集就等于没有风险**——这一格于是只在单调性把它整个钉死时才答得出，否则整条估计放弃。但「没有调整集」不等于「不可识别」：general ID（c-factor 分解）能到达任何协变量集都表达不出的估计量。潜混杂下的前门结构就是最干净的例子——调整**可证**失败，ID **可证**成功。

`general_id.py` 补两个公开原语：`identify_arm_risk_formula`（单臂估计量，不是 ATE——本格只依赖一臂，索取另一臂等于凭空造需求）与 `evaluate_arm_risk`（复用同一个 VE plug-in）；域由 `data_domains` 显式传入，bootstrap 因此不会在某次抽样里把求和范围悄悄收窄成**另一个**估计量。回退顺序是纯加法：后门优先（有调整集时行为逐字节不变），后门失败才试 ID，ID 也失败才落回单调性钉死。

`interventional_risk_provenance` 因此多出第六个值 `general_id_plug_in`，而且它和其余五个一样**是可复核的断言**：验证器从 `ctx.graph` 重算「确实没有可容许调整集」，再对 `ctx.query` 问的那一臂重跑 ID，把自己导出的估计量与记录下来的逐节点比对。这比只查「可识别与否」严一格——**算了另一臂却当成本格上报**是个会静默给错答案的真实故障模式，逐节点比对正好抓它（记录的公式作为派生步骤输入随 envelope round-trip，沿用 `tian_formula_ast` 的先例）。数值本身仍在 data-refit 天花板之内（验证器只有 `data_hash`）：能钉死的是「这个数是从对的估计量上读下来的」。

取舍（声明）=IV 识别的风险未接（Wald 比是 ATE，不是本格消费的单臂风险）·ID 的 plug-in 要求估计量条件到的每一层都有支撑（前门结构里 `M` 对 `X` 若是确定性的，另一层就是真的 positivity 违反，如实拒绝）·离散饱和估计。D1：**独立真值 oracle 仍是数生成器的潜在结果**（阈值型单调前门 SCM，单调 PN 点恢复真值到 0.01；无单调性时区间覆盖真值）·先证「后门在这张图上确实拿不到调整集」再证本格出数·有调整集时仍走后门且不记公式·bow arc 照样诚实拒绝（回退不许无中生有）·端到端 estimate + schema + verify·三类篡改各因**该抓的原因**被拒并把原因钉进测试（谎称无调整集 / 记录另一臂的估计量 / 干脆不记）。+11 →**3367**。

**中介块对披露层是瞎的（2026-07-22）**：修复型。**现象**——同一张图、同一个查询，问单个中介时人看的输出带两条识别假设 caveat，把 `mediator` 换成 `mediators`（中介块）后**一条都没有**。**根因**——`data_gap_report` 里的生产者绑在 `extensions.mediation_decomposition` 这个**单中介专用的 extension key** 上，而不是绑在「这次做了中介分解」这件事上；联合块写在 `mediation_joint_decomposition`，于是整个缺口 / 披露层对它不可见。只在渲染层补一句话不解决问题：审计通道（data_gap_report → assumption_ledger → 报告）仍然缺，而且下一个中介变体会第三次踩同一个坑。

结构性改动是一个归一化视图 `_mediation_view(extensions)`：两种形状（`mediator` / `mediators`、`mediator_valid` / `mediator_set_valid`、两个 key）归一成同一个东西，四个生产者改成消费它而不是消费某个 key。实测坐实的四处漏：**① 识别假设 caveat 完全不出**（最重——「可识别」在人看的一面读起来是无条件的，而块的前提与单中介**严格不同**：VanderWeele-Vansteelandt 联合条件、块-CDE 把**整组**固定在参考值）；**② 调整集谓词不进「查询相关」集**，于是调整协变量上的 `llm_proposal` 边逃过 `unverified_proposal_edge_on_query_path` 披露（单中介同图会被抓）；③ `missing_mediator_data` 数据需求永不列出；④ `mediator + target_population` 的静默跳层诚实 gap 只认单数字段。措辞只多一个主语，实质仍来自块自带的 assumptions 列表——块还必须说清它**不**主张什么：整组分解，不拆到单条路径（拆开是 recanting witness，真不可识别）。

同源第五处在估计端：数据路径的联合估计**算了** `proportion_mediated` 却从不出 headline，单中介出。第六处最危险，是核实过程中撞见的：`mediators` 只写**一个**中介时，联合路由要求 ≥2、单中介路由读单数字段，两边都不接——**整个中介分析被静默跳过，无 extension、无 caveat、无任何信号**。集合就是集合，一个元素也是（k=1 时集合机制精确退化到经典单中介，估计器早有逐位相等的测试），改成非空即路由。

D1：五条新测试**先在改前的代码上跑成红的**（`git stash` 实测：JOINT 分支 0 条 caveat、`llm_proposal` 边 ABSENT），改后全绿；核心不变量是**parity**——同一张图，问块与问单中介必须披露同样的东西（`counts(joint) == counts(single)`），这条不变量正是当初能挡住这个 bug 的那条。+6 →**3373**。

**条件工具变量接上 theta 端（2026-07-25）**：`structural_solver.iv_sets` 一直会返回**条件**（Brito-Pearl）工具变量——一个 Z 只有在 W 被固定之后才是工具——identify 路径一直照实报它，`estimate_iv_ate` 的 DataFrame 路径也一直用 2SLS 吃 W。只有 theta 端不接：`_try_iv_wald_in_effect` 取 `iv_candidates[0]`，一见 `chosen.conditioning` 非空就 `return None`。于是**同一张图**（`w→z, w→y, z→x, x→y, x↔y`）：identify 问「可识别吗」回 `structurally_solved`「用 z，在 w 之下」，effect 带着完整 theta 和 monotonicity 问「值是多少」回 `needs_investigation`，理由写着「backdoor / front-door / Tian ID **都到不了**」——只字不提工具变量。

补上**分层 Wald**。W=∅ 是同一套算术的单层退化（权重 1、条件里不带 W 项），因此边际答案逐字节不变，不是两条路径。层权 P(W=w) 按链式法则展开，沿用 `backdoor_formula` 联合分布那套拓扑序约定。聚合方式是**比值的平均而不是平均的比值**：

```
LATE = Σ_w P(w)·[P(y|z⁺,w) − P(y|z⁻,w)]  /  Σ_w P(w)·[P(x⁺|z⁺,w) − P(x⁺|z⁻,w)]
```

——每层按**它自己的 complier 份额**加权，那正好就是分母项（Abadie 2003），得到的才是 complier 平均因果效应；把各层 LATE 按 P(w) 平均是另一个估计量，两者只在工具在各层推动处理的力度相同时才重合。这是这条路上最像的错答，所以测试直接把两个数都算出来钉住（0.625 对 0.65），验证器也独立重算成比值的平均。`treatment_shift` 顺带成为**报出来的 complier 份额**——LATE 是子人群上的效应，读者要判断这个数与自己有没有关系就需要知道那个子人群多大。

第二半是**说清为什么给不出数**。`None` 不携带信息，于是「monotonicity 没声明」「theta 少一格」「一阶段退化」全塌成同一个「这图没救」。改成返回 `_IVWaldAttempt(result | missing)`：monotonicity 门移进函数内部，于是能说「有 1 个工具变量 z 在 {w} 之下够到了这个效应，但工具本身不挑估计量，请声明 monotonicity」；theta 少一格则直接点名 `parameter:P(y=True|w=False,z=False)`；层权不构成分布时拒绝（LATE 比值对尺度不敏感，照样会出数，但报出去的 complier 份额就没意义了）。候选也改成**逐个试**而不是只试第一个：某个候选 theta 供不上，跟下一个候选能不能用无关。

这些新条目是**并排追加**而不是顶替原来的 `query:effect_admg`——第一版写成顶替，被回归抓住：那条结构项承载「非参数点识别确实失败」，下游 `answer_tier` 读它来决定答案是区间还是点，`unidentifiable_no_admissible_set` 的 `alternative_paths` 早已在有工具时改写成「声明 monotonicity / linearity 把区间收成点」。顶替掉它等于把一个 IV/Wald 估计当点识别发出去。**「有可用的 IV 逃生通道」不等于「可识别」**，两条是不同的事实，都要说；只把结构项的措辞从「IV 也到不了」改掉。

验证器不复读、自己重导三件事：**①（Z, W）在 `ctx.graph` 上确实是工具**——就地重跑而不倚靠相邻的 `iv_criterion_check` 步，因为这段算术只在它真正算的那个 W 上才是 LATE，要抓的正是「算了边际 Wald 却把 W 记成 ∅」这种每个数字都自洽、只有图不同意的故障；**② 层从 `ctx.theta` 的域重新枚举**，少记一层不能当成对全人群求了平均；**③ 聚合按比值的平均重算**。附带把 `_tuple_to_dict` 补上通用 `value_tuple` 分支——tagged-dict 早就任意递归，元组不许放 dict 只是分支顺序的意外，不是规矩。

取舍（声明）=处理与工具须二值（Wald 是两点对比，放宽是选估计量不是补数字，非二值仍落回结构拒绝）·条件**查询**（`q.given`）仍归 IDC 分支·theta 查表不走边缘化回退（沿用边际 Wald 一直以来的约定，代价是分层工具要把每层条件和每个 P(W=w) 都写出来，收益是生产者与验证器不会在「哪个洞被什么推导填上了」这件事上漂移）。**发现但未修**：`_classify_missing_assumption` 以 `status == NEEDS_ASSUMPTION` 为门，而该状态现已无生产者，因此**所有** `MissingKind.ASSUMPTION` 项（含既有的 `counterfactual:interventional_risk_unavailable` 等）都进不了 `data_gap_report`——它们仍经 `investigation_requests`（`define_assumption`）到达用户。这是既有形状、波及多条我未探过的路径，另开一档处理。

D1：16 条新测试**全部先在改前的代码上跑成红的**（`git stash push -- themis/` 实测）；前提先证后证结论（先断言这张图没有可容许调整集、且它给出的工具**全都**带条件集，再断言 effect 出数）；边际 Wald 单层退化逐字段钉死；四类篡改各因该抓的原因被拒（把 W 抹成 ∅ / 删一层 / 把答案换成平均的比值 / 改一层权重）；条件集上的 `llm_proposal` 边照样被披露（W 不在查询里，它只因为「让 Z 成为工具」而进入答案，现在它还承载数值）。+16 →**3389**。

**条件工具变量的数据端对上同一个估计量（2026-07-27）**：修复型，而且是上一档的直接后果。**现象**——同一张图、同一个 DGP、同一个条件工具变量，theta 端给 0.625（complier 份额加权的 LATE），DataFrame 端给 0.5639 或 0.6838（随设计而定）。两个数都自洽、都不报错。**根因**——`iv.py` 的估计量分派把 `not conditioning` 和二值性检查写在同一个条件里，**把「有协变量」当成了放弃 Wald 家族的理由，而那只是分层的理由**；那句 `NotImplementedError("not supported in v1")` 说明它本来就是一次延期，不是设计判断。表象读法是「2SLS 算错了」——不是，2SLS 是标准估计量、连续 Z/X 下还是唯一选择、假设表里也确实写了 `constant_treatment_effect_else_estimand_is_weighted_average`。真问题在分派：**加一个协变量就静默地把估计目标从「compliers 上的 LATE，靠单调性」换成「总体加权平均，靠线性」，连假设表都整个换掉，而没有任何东西告诉读者这是两个不同的目标**。而且在上一档之前，这世上只有一个数（theta 端拒答）；是上一档让第二个数存在的，所以这是必须收口的 follow-on，不是可选前沿。

实测坐实分歧只在特定形状下现身：`Var(Z|w)` 在各层相等时两者重合（0.5/0.5、0.8/0.2、0.2/0.8 三个设计误差都 <0.003），不等时立刻分道且两个方向都能偏（0.9/0.5 → +0.059，0.5/0.1 → −0.061，n=4×10⁶）。2SLS 把 W **加性**放进两阶段（`stage1_X = [Z, W]`，无 Z×W 交互），于是按 `Var(Z|w)` 加权各层 LATE，不是按 complier 份额。

补 `stratified_wald` 估计量：二值 Z/X + 可切的 W 时 `auto` 解析到它，与 theta 端算同一个比值的平均。W=() 是单层退化，与边际 Wald **逐位相同**（`stratified.point == marginal.point`），因此没有第二条代码路径。切不动时（W 连续、层数超帽、某层缺一个工具臂）**退回 2SLS 并把退回本身作为一等事实报出来**——新 GapKind `iv_estimand_fallback_to_linear`，INFORMATIONAL，镜像进 explanation（与 `weak_iv_instrument` 同姿态），`required_data` 点名是哪些层缺臂、缺的是哪几列，那是用户真能去收的数据。**显式** `model="stratified_wald"` 则绝不退回：点名要一个估计量却静默收到另一个，正是这条路要挡的事。空层不是丢掉而是拒绝——丢掉等于在一个更窄的人群上求平均，而算术照样自洽。

两层不共用代码（`themis/runtime` 不 import `themis/estimation`，这个边界值得留着），所以一致性靠**估计量命名 + 两端 parity 测试**保证，新文件 `tests/test_iv_stratified_wald_parity.py` 就是这条契约。验证器这次**越过了 data-refit 天花板**：分层表本身就是充分统计量（点是层权与两个位移的函数，别无其他），把它记进推导输入后，验证器不需要原始数据就能独立重算比值的平均，并在点等于平均的比值时**点名**说出来。表与方法互相钉死：非分层方法不许带表，分层方法不许不带。

我自己踩的坑：`_w_levels` 第一版用 dtype 判断「能不能切」，但真正的判据是**取值个数**——数据契约会把整数列加宽成 float，于是整数编码的离散 W（最常见的类别写法）整个丢掉分层路径。改成只按基数判定，float 且高基数时才说「连续」。

取舍（声明）=处理与工具须二值·**分层路径上不附 Anderson-Rubin 集**：AR 反转的是线性 IV 系数的检验、它自己记录的 `point` 就是 2SLS 那个数，挂上去等于把两个估计量塞进同一个结果，正是这次要消除的混淆；代价是这条路暂时没有弱工具稳健集（一阶段 F 警告与 `treatment_shift` 仍在），**分层矩上的 AR 集**（同一个 `_ar_solve_set` 二次求逆，(A−βB)² ≤ κ·Σ_w p̂²_w[…] 形状一致）是声明的下一步。

D1：30 条新测试先在改前代码上跑成红的（`git stash push -- themis/ docs/ COVERAGE_MAP.md` 实测）；另 3 条是守卫/round-trip（「2SLS 在本设计上确实不等于 LATE」这个前提、verify 不炸），本就两边都绿，不算作红过。+32 →**3421**（31 条新测试 + `test_gap_kind_has_test_coverage` 因新 GapKind 多出的一个参数化用例）。

**分层矩上的 Anderson-Rubin 集（2026-07-27）**：修复型，收上一档自己声明的缺口。**现象**——`estimate_iv_ate` 在 `resolved == "stratified_wald"` 时把 `ar_set` 置 `None`。而上一档让 `auto` 在「二值 Z/X + 可切 W」时一律解析到分层路径，那正是条件工具变量的**默认路径**——所以上一档实际上把默认路径上原本存在的弱工具稳健集拿掉了。披露过，但那是净损失，不是本来就没有。

**根因**——仓里只存在**一种** AR 集，而它建在 FWL 残差矩上（`_residualise(·, W)`）。把 W 加性投影掉正是产生 2SLS 加权的那个投影，于是这个集合在构造上就绑死在线性估计量上，它记录的 `point = s_zy/s_zx` 是线性那个数；验证器还把这条绑定钉死了（`_check_anderson_rubin` 直接断言 `point == s_zy/s_zx`）。所以「分层路径没有 AR 集」不是漏了一次调用，而是**缺一个建在分层矩上的 AR 集**。表象读法「忘了接上去」经不起一试：接上现有那个会立刻被验证器判失败，因为它算的确实是另一个估计量的区间；反过来说，如果侥幸没被抓住，那才是真正的静默错答——一个标着分层 Wald 的点，配一条围绕 2SLS 的区间。

**改法**——把检验建在估计量自己的矩上。记 `A = Σ p_w Δy_w`、`B = Σ p_w Δx_w`（点就是 `A/B`），零假设说 `A − β₀B` 均值为零；各层独立，聚合方差 `Var = c_yy − 2β₀c_xy + β₀²c_xx`（`c = Σ p_w²·` 该层两臂的二阶矩除以各自臂样本量）。反转 `G² ≤ κ·Var` 得同形状的二次不等式，`a = B² − κc_xx`、`b = 2(κc_xy − AB)`、`c = A² − κc_yy`，**复用现成的 `_ar_solve_set`**——五种 Dufour 形态与弱工具行为原样继承：`B → 0` 时首项系数转负、集合张开成整条实线，那正是工具推不动 compliers 时的诚实答案（实测退化设计确实返回 `whole_line`）。

**只反转聚合矩，不反转 S 条分层矩**，这是刻意的：分层 Wald 的定义就是比值的平均，聚合矩才是这个估计量自己的矩；把 S 条矩一起压上去测的是「每层共享同一个 LATE」这个**更强**的假设，而各层 LATE 真的不同正是这个估计量要平均掉的东西，不是它的失败。（层间同质性检验是另一件事，另开。）

**方差按臂取**，所以不假设两臂等噪声。这不是装饰：臂平衡时合并估计量与分臂估计量恰好重合（等样本量下的经典结论），实测 20000 样本、`P(Z=1)=0.85` 的不平衡设计上两者分道，而且**两个方向都会**——噪声落在大臂时合并集宽 2.3 倍，落在小臂时合并集**窄到不足一半**，后者是危险方向。这条已钉成测试。

`kappa = F(1, n − 2S)`（每层两个格均值）是有限样本修正，相对分臂稳健方差严格支持的渐近 χ²(1) 偏保守——只会更宽不会更窄。层权 `p_w` 视为固定（推断条件在观测到的层大小上，分层估计量的标准立场，也正是集合能成为记录表的闭式函数而非只有原始数据才算得出的东西的原因）。两条都声明在此。

**顺带修好的真洞**：弱工具警告一直只读线性那个字段，于是**分层路径上一个弱工具会拿到警告却拿不到集合**，`alternative_paths` 还写着「去算一个 AR 集」——而它就在同一个对象上。改成取任一已填充的那个（两者互斥、形状相同，一行）。弱一阶段恰恰是最需要这个集合的时候。

验证器把这条路**整体**留在 data-refit 天花板之上：集合是同一张表的闭式函数，于是它从**逐层的**方差列重建聚合矩（而不是读生产者记下的聚合值）、重算 κ、独立重解二次式、比对形状与端点。载荷最重的一钉是**集合的点必须就是 headline 点**。线性集合与分层方法的互斥则**按结构判、不按数值判**：各层一阶段力度恰好相同时两个点重合，只比数值会放行。为此把验证器里的调用顺序改成先定路由、再各自审计——哪个集合属于哪个方法是路由事实，得在任何一个集合被按自己的规则审计之前定下来。

**我核实后推翻的两个假设**（先量再写）：① 以为「弱工具下 bootstrap CI 会失守而 AR 顶住」——实测三种弱设计下 bootstrap 覆盖率 0.940/0.964/0.964，AR 0.952/0.956/0.960，**bootstrap 并没有欠覆盖**，所以不写这个卖点；AR 的价值是覆盖率由构造保证而非碰巧，外加能给出百分位区间在结构上给不出的形状（中位一阶段 F=0.9 时 200 draw 里 145 次返回整条实线，同样这些 draw 里 bootstrap 每次都给出有限区间——但宽度中位 67、最窄 12.7，它并不是在假装自信，只是没有「说不出」这个选项）。② 以为分臂方差在异方差下就会与合并方差分道——**臂平衡时不会**，必须同时不平衡才现身（见上）。

D1：18 条测试先在改前代码上跑成红的（`git stash push -- themis/` 实测），其中 17 条全新、1 条是原「分层路径无 AR 集」那条改写后加了新断言。另有 1 条既有篡改测试（删一层）因为篡改要多动三列而在旧代码上以 KeyError 变红——那是机械原因，**不算作证明了什么**。+18 →**3439**。

**假设通道接上缺口报告（2026-07-27）**：修复型。**现象**——全量套件里内核产出的 `MissingKind.ASSUMPTION` 项共 62 次，**61 次从不进 `data_gap_report`**；唯一进去的那 1 条来自生成器单元测试里手工构造的结果。（用一个包住 `compute_data_gap_report` 的临时 conftest 全量跑了一遍才量出来，不是读代码推的。同一次测量里 structure 组 54/166 未被引用、observation 组 3/3 未被引用；framing 组表面 100% 未引用是探针的假阳性——它走 `framing_note` ref，另有覆盖。）

**根因**——`_classify_missing_assumption` 的触发条件写的是 `status == ResultStatus.NEEDS_ASSUMPTION`，一个**代理信号**，而不是断言本身所在的通道。2026-07-22 反事实单格重建（`d1efd3b`）把该状态最后一个生产者移除之后，这个分类器就整体失效了，没有任何东西报警。表象读法是「状态该恢复」，但状态不该恢复：那 7 个生产点返回 `NEEDS_INVESTIGATION` 是对的，它们是缺信息结果而不是一个独立状态。真正的问题是分类器绑在一个**可以消失**的东西上，而它要报告的事实有自己一直存在的通道——`MissingKind.ASSUMPTION` 经 `investigation_pusher` 恒定落到 `group == "assumption"`。

**它为什么能活这么久**——`_verify_t10_2_completeness` 是专门抓 under-disclosure 的那条规则，它逐组枚举「必须被某个 gap 引用」的通道，而只列了 `parameter`（外加派生步骤与 framing note）。`assumption` 从来不在名单上。于是「生成器死了」这件事在验证器眼里完全合法。**生成器和验证器用同一种手工枚举，留下同一个默认值：没列到的等于静默无缺口。** 而分类器唯一那条绿测试，喂给它的是一个内核不产生的状态——所以它从来没有证明过任何事情。这也是本档所有端到端测试都走 `themis.run` 而不是手搓 `QueryResult` 的原因。

**改法**——触发改成通道本身，删掉死状态分支（那条分支产出的 gap 内容是「具体假设未在 missing_information 标注」，即一个内容为「内容缺失」的缺口）。T10-2 把 `assumption` 纳入必须被引用的组，判据写进 docstring：**列进来的是那些条目在报告里没有第二个表示渠道的组**——parameter 名字里的那个概率没有别处会提，assumption 名字里的那条前提既没有派生步骤也没有 framing note 承载；structure 组的条目大多是报告已经通过派生步骤引用过的那次失败的复述，framing 条目走第 3 项检查的 `framing_note` ref。

**描述改成携带条目自己的 `reason`**，因为 remedy 写在那里。这条不是润色：这个通道上到的**不是一种东西**——有内核拒绝替你选的前提（`effect:iv_monotonicity_undeclared`：有工具变量不等于选定了估计量），有只有实验给得出的输入（`causation:` / `counterfactual:interventional_risk_unavailable`），还有**互相矛盾的已声明输入**（`causation:interventional_risks_infeasible` 落在一致性带之外、`effect:iv_stratum_weights_not_normalized`、`effect:iv_first_stage_degenerate`）。原来那两条通用建议（「接受 bounds 而非点估计」「运行 sensitivity analysis」）对后三种是**把读者引过错误而不是引到错误**，所以删掉——缺口只说内核说过的话，不补内核没推导出的建议。`actionable_next_steps` 的标签同步从「识别假设」改成「识别前提」：同一个通道也承载要修的声明，标签只能命名前提，不能命名修法。

**顺带修的陈述失真**（同一个死状态的下游）：`response_rendering.md` 把 assumption 组说成「与 `status == "needs_assumption"` 配对」、headline 阶梯把该状态当触发；`nl_to_kernel_ast.md` 更实质——它告诉上游 LLM「干净的个体反事实内核会返回 `needs_assumption`（请用户授予单调性），那是几何上正确的答案」，而现在返回的是 Tian-Pearl 区间（`counterfactual_bounded`），单调性成立时收紧成点。那句话是在一个**已经不成立的前提**上引导上游的压缩决策。`docs/GAP_KINDS_REFERENCE.md` 的行也改写了。

**声明的边界**——structure 组（54 条未引用）与 observation 组（3 条）**没有一并处理**：observation 条目（SCM 反事实的单位观测）在 `GapKind` 里没有合适的成员，补它是一次带 schema 变更的独立改动；structure 条目当时判断为多与一条已被引用的失败派生步骤同源。这条边界钉成了测试而不是留成默认值。

> **下一档更正（同日）**：上面那句「structure 条目多与一条已被引用的失败派生步骤同源」是**没有验证的假设，且不成立**。同样的插桩记账量到 `failed_rules` 对全部 54 条都是空的——它们背后根本没有失败的派生步骤。详见下一条。

D1：14 条测试先在改前代码上跑成红的（`git stash push -- themis/` 实测）。另有 5 条在新旧两边都绿——4 条是端到端的验证器审计（旧 T10-2 根本不查这组）、1 条是「结构组仍留给它的派生步骤」这个边界钉，**不算作证明了什么**。+19 →**3458**。

**残余缺口分类器：把静默默认翻成响（2026-07-27）**：修复型，收上一档自己声明的边界——并**推翻我在那一档写下的判断**。

**现象**——同一套插桩记账量到 57 条 structure / observation 条目未被引用，而 `failed_rules` 对**全部 54 条 structure 条目都是空的**：它们背后根本没有失败的派生步骤。上一档写的「structure 条目多与一条已被引用的失败派生步骤同源」是没验证的假设，不成立。实际分布分两类：

- **报告存在但 `gaps` 全空** 30+ 次：SCM 反事实缺路径系数（27）、缺单位观测（3）、ID*/IDC* 不可识别（3）、proximal 不可识别（2）、条件事件概率为零（1）。模块 docstring 自己写着 `gaps=()` 的语义是「asked and got a clean bill of health」——一个什么都没返回、并在 `missing_information` 里写清了为什么的查询，报的却是「查过了，没问题」。
- **更糟的一类，不是漏报是反着报**：`identification:not_identifiable`（11 次，effect 查询）。探针实测 `structural_result.value = False`、`missing_information` 明写 "no valid back-door or front-door adjustment exists"，而 `data_gap_report.answer_tier` 返回 **`"point"`**——信封告诉消费者「点估计量在手」。同类还有 `identification:joint_not_identifiable`（5）、`longitudinal:sequential_exchangeability_fails`（2），共 18 次。

**根因**——`_classify_unidentifiable_from_request` 用**三条名字前缀白名单**认领结构失败，`_classify_missing_iv` 用子串 `iv`；除此之外整个 structure 组、以及**完全无人读取的 observation 组**，默认值是静默无缺口。与上一档的逐组枚举同形——**枚举式守卫的默认值是静默通过**——只是这次落在名字粒度上。而下游 `answer_tier` 读的正是那个没被产出的 kind，于是「少一条 gap」变成了「发一个错的 tier」。表象读法是把漏掉的名字补进白名单，但那保留了同一个默认值，下一个上游新增的拒绝名照样静默。

**改法**——把默认翻成响。新增 `_classify_residual_investigation_items`，**残余的定义是「跑完所有分类器后仍未被任何 gap 引用的条目」**，从已产出的 gap 列表里读，而不是复制一份判据——所以它结构上不会与细化分类器漂移：上游加一条细化，残余自动变窄；去掉一条，残余自动变宽。白名单降级为**细化**：忘记加名字的代价从「消失」变成「缺口不够具体」。

两个新 `GapKind`。`missing_unit_observation` 给 observation 组——abduction 要的是**这个单位的读数**，人群分布替代不了，所以它不是 `missing_distribution`。`missing_structural_input` 给 structure 组的残余（未声明的路径系数、不在因果路径上的中介、不在 V 里的查询原子、在图允许的每个模型下概率为零的条件事件），它**刻意不声称识别失败**：缺一个系数时估计量是点识别的，只是那个数从没被声明，而 `unidentifiable_no_admissible_set` 才是 `answer_tier` 用来判定点被阻断的那个 kind。两者的 `blocks` 都取 `point_estimate`——那是对上述所有形态都成立的那句话；描述携带条目自己的 `reason`，不附任何内核没推导出的建议（同一组条目从「补一个系数」到「你的条件事件不可能发生」，一条通用建议对它们不存在）。

白名单同时扩到真正意味着「点识别失败」的那几个名字（`identification:not_identifiable` / `identification:joint_not_identifiable` / `query:proximal_not_identifiable` / `query:counterfactual_unidentifiable` / `longitudinal:sequential_exchangeability_fails`），修掉 answer_tier 反着报。实测：同一个 collider 程序从 `answer_tier: point` 变成 `none`，summary 从一条 collider 建议变成「识别路径失败：no valid back-door or front-door adjustment exists」。**判据是「这个估计量在这张图和这些数据下不是点识别的」，不是「程序里有错」**——中介声明错了、原子不在 V 里都是程序缺陷，走残余，免得 tier 被告知识别失败。

**验证器**——T10-2 的组名单从「列出被覆盖的组」翻成**「列出豁免的组」**，唯一豁免是 framing（它的条目以 `framing_note` ref 进报告，第 3 项检查已经持有；要求第二次以另一种 ref 引用会把正确报告判错）。写成豁免式是刻意的：包含式的默认值是让没列到的组静默通过，而这正是这条规则先后在 assumption 通道、structure 与 observation 通道上全绿而下面什么都没产出的原因。

D1：12 条测试先在改前代码上跑成红的。另有 6 条两边都绿——3 条端到端验证器审计（旧 T10-2 不查这两组）、1 条 collider 程序本来就有别的 gap、1 条 framing 豁免钉、1 条「已解出的查询不应凭空多出残余缺口」的前提钉，**不算作证明了什么**。+19 →**3477**。

**两条通道同时误分类：合成校正（2026-07-28）**：能力型，收 `measurement.py` / `dispatch.py` / `estimation/__init__.py` 三处都写着的声明式缺口。

**缺口**——暴露与结局各有验证研究给出的混淆矩阵时（自报暴露 + 病历摘录结局，很常见），`dispatch.py` 一直**诚实拒绝**（`combined_misclassification_deferred`），理由写得对：只校正一条通道再把点发出去，等于把另一条通道的偏倚留在数上。所以这是能力缺口，不是静默错答——要做的是把拒绝翻成正确的数。

**数学**——两条误差机制在真值下相互独立时，某后门层内的观测联合是真实联合的**双边线性像**：

    P_obs(z)[a,b] = Σ_{a*,b*} M_x[a,a*] M_y[b,b*] P_true(z)[a*,b*] = (M_x · P_true(z) · M_yᵀ)[a,b]
  ⇒ P_true(z) = M_x⁻¹ · P_obs(z) · (M_y⁻¹)ᵀ

即暴露侧的左乘求逆与结局侧的右乘求逆，作用在**同一张** 2×k 联合表上；随后照暴露侧原样标准化 ATE=Σ_z[P(Y*=y*|X*=1,z)−P(Y*=y*|X*=0,z)]P(z)。

**★关键是它比两条单通道校正各自多要一个前提★**——`X ⊥ Y | (X*, Y*, Z)`：两条误差机制在真值下相互独立。两条**各自**非差异的通道仍然可以彼此相关（同一个粗心的摘录员把一条记录的两个字段一起写错就破坏它），所以这是严格更强的前提，也正是它让上面那个因子分解成立。它单列进 `assumptions`（`independent_error_channels_X_indep_Y_given_Xtrue_Ytrue_Z`），不埋在两条非差异假设里。

**★声明的边界是结构性的而非预算性的★**——任一通道**差异**（differential）时拒绝而不近似：detection bias 让 M_y 依赖真实暴露、recall bias 让 M_x 依赖真实结局，**选矩阵的那个层级恰恰是另一条通道正在误测的量**，观测表于是不再是双边乘积（映射对 2k 个未知量仍线性，但不是 Kronecker 积），当成双边乘积去求逆会返回一个错的数而不是一次拒绝。新 `differential_combined_misclassification_deferred`。

**实现**——①`measurement.py`：`CombinedMeasurementCorrectionEstimate` + `estimate_combined_measurement_correction`，复用暴露侧的 2×k 联合表构造/positivity/`degenerate_recovered_exposure`/`out_of_simplex`（报不裁剪）；`_validate_matrix` 加 `label=` 让"哪条通道的矩阵坏了"能说出口（两张矩阵在场时"confusion matrix"是歧义的）。②`dispatch.py`：拒绝分支换成 `_try_combined_measurement_correction_estimate`，`_measurement_correction_block` 加 combined 分支——**两条通道各带自己的矩阵名**（`confusion_matrix_exposure`/`confusion_matrix_outcome`/`det_exposure`/`det_outcome`），没有"那张"矩阵也没有单一 `det`。③`det_joint = det(M_x)^k·det(M_y)²`=合成 2k×2k 映射（Kronecker 积）的行列式，一个数说清两条通道**共同**销毁多少信息，任一 det 单独都给不出。④`verify.py`：`verify_combined_measurement_correction_numeric` 第二次独立转写双边求逆；**只此一条路有的检查**=记录的 `det_joint` 必须能因子分解成 `det(M_x)^k·det(M_y)²`，抓"点从这两张矩阵重导得出、而 det_joint 是从另一对矩阵抄来的"；另拒任何 differential 声明（双边分解没许可它）。⑤schema/rules/kernel/两个 `__init__`/response_rendering 同步。

**D1**——新能力的红是"这东西当时不存在"，要分清：真正因行为改变而红的是 3 条（合成分派把拒绝翻成 `numerically_solved` 且点落在潜真值 ±0.03；差异通道给出的是**新的**专用 failure_type 而非旧的通用拒绝；诚实结果通过 verify）；9 条估计器级测试在改前代码上**连收集都过不去**（符号不存在）；7 条篡改测试红在 `KeyError: numeric_estimate`（旧代码没产出可篡改的对象）=**机械原因，不算作证明了什么**。真值 oracle 是模拟 SCM 的潜 X*/Y*：双边校正恢复潜真 RD（0.3014 vs 0.3002），而 naive 偏 0.140、**只校正结局偏 0.086、只校正暴露偏 0.074**——最后这一对才是这个估计器存在的理由，写成了测试。恒等矩阵通道退化回对应的单通道估计量（1e-9）。旧的 `test_combined_exposure_and_outcome_spec_deferred` 改写成钉住新路由。+19 →**3496**。

**假设账本对多数估计器是瞎的：把披露面接到唯一的漏斗（2026-07-28）**：修复型。`assumption_ledger` 是 `build_analysis_report` 与 `response_rendering.md` 都拿来**领起整段回答**的那个面——"这个答案把什么当成了真"，按"假的话结论怎么死"排序。

**现象（实测，非推断）**——临时 conftest 包住数值漏斗跑完整套件记账：**31 个数值 method 里 14 个从来拿不到账本**（这还是低估，见下）（前门、IV 全家、中介、纵向、transport、选择偏倚恢复、三种误分类校正、regression calibration、joint…），而这些估计各自的 `numeric_estimate.assumptions` 里带着 4–9 条载荷假设；`build_analysis_report` 对它们**整个 `## 假设` 段落不打印**——那正是它的 docstring 自称"让这份报告是 Themis 的报告而不是一份通用因果分析摘要"的两样东西之一。最刺眼的是 `iv_wald`：29 次里 11 次有账本，而**那 11 次全部只含 `structural_edge` 条目**（共 22 条）——账本在不在，取决于恰好有没有一条 LLM 提议边落在答案路径上，与这个估计量自己的排他性 / 单调性 / LATE 假设无关。（**记账本身也有盲区，而且当场兑现了**：第一版把 conftest 挂在 `_finalise_numeric_result` 上，中介家族刻意保留 `structurally_solved`、根本不流经那个漏斗，于是整个没进统计。改完后用挂在真正单一出口上的同一份记账重跑，可见的 method 从 31 变成 **36**——多出来的 5 个正是 4 个中介家族 + `missing_data_recovery_gformula`，它们同样一条账本都没有。**真实规模是 36 个里 19 个**，加上 `iv_wald` 那种"有账本但只含提议边"的半覆盖。）

**根因**——`build_assumption_ledger` 自称是 "a VIEW over the existing channels"，但它枚举的通道是 gap 报告的提议边、`llm_proposed_review` 的 theta prior、`mechanism_audit` 的函数形式，外加**由调用方传进来**的 `identification_specs`——**唯独漏掉 `numeric_estimate.assumptions`：最老的、也是每个估计器都填的那条通道**。于是账本变成每个估计器家族各自 opt-in：要同时记得①在 estimate 上加结构化字段②在 dispatch 里调用 builder，漏掉任一条都静默，31 个里只有 17 个记全。builder 的 docstring 写着 "Returns None when nothing is assumed" ——这句话是假的，它只是没读那条通道。

**为什么是根因不是表象**——表象读法是"`_render_assumptions` 读不到账本就返回空串"，在那里加个回退能让报告非空，但**每加一个估计器家族默认仍然是静默**。默认值才是缺陷。

**改法**——①flat 通道升成一等通道（`augment_assumption_ledger`，条目带 `provenance: estimator_declared` + 原始 `id`）；②构建搬到 `estimate_program` 的**单一出口**（原函数改名 `_estimate_program`，公开名成一层薄壳），因为漏斗不能是 `_finalise_numeric_result`——中介家族刻意保留 `structurally_solved` 状态、根本不经过它；③严重度集中到新的 `output/assumption_glossary.py`（ID→claim/layer/severity/testable，精确 ID + 显式前缀两种形状，前缀是数据不是关键词启发式），**未知 ID 的默认是"按识别层、作废级、原文照登"**——披露面出错要往多报的方向错，加估计器不可能让一条假设消失，最坏是没翻译；④估计器已声明结构化 identification 条目时 flat 通道**不读**（那是同一句话的更好说法），现有 17 个 method 的账本因此不变，并钉成测试。

**顺带被新验证器抓出来的两个真缺陷**——都不是我改出来的，是原本就在的、同一类"默认静默"：①误分类 / regression calibration 路径挂着 `mechanism_audit` 却没有账本，于是第一版的 `augment_` 只补 flat 通道会**披露估计器假设、藏起旁边的函数形式**→改成没有账本时先读全部四条通道；②`causation.py` / `counterfactual_cell.py` 给单调性假设发明了一个 `severity: "consequential"`，**不在账本排序词表里**，于是 `.get(..., 9)` 把它沉到**最底**（比"仅影响置信"还低），而单调性正是让 PN/PS/PNS 从区间变成点的那一条；`analysis_report` 的 `_SEVERITY_ZH` 也没有它的译名，直接印英文。改成 `invalidating`，并把排序 fallback 从 9 翻成 −1——未知严重度应该浮到最上面让人看见，而不是沉到最下面。

**验证器**——`verify_assumption_ledger`（`verifier/assumption_ledger_rules.py`，独立性钉：不许 import `result_orchestrator` / `assumption_glossary`），进 `verify()` 且另有 result-only 公开入口（账本会挂在状态从不翻成 `numerically_solved` 的结果上）。它从四条通道**独立重导账本欠什么**，专抓 under-disclosure：丢条目 / 凭空多出估计器条目 / 没排序 / summary 计数对不上 / identification 层条目排在 `invalidating` 以下。**刻意不审**某条假设该判什么严重度——那是 glossary 里的策展判断，不是从信封能推出来的事实，在这里重述一遍只是转写不是验证。

**D1**——46 条新测试在改前代码上跑：**20 条红在正确的理由**（6 个家族各自"没有账本"/"声明的假设不在账本上"/"报告不打印 `## 假设`"，加上"置信区间怎么算的不是作废级假设"和"没有生产者发明词表外的严重度"）；**14 条红在 `themis.verify_assumption_ledger` 当时不存在**=机械原因，**不算作证明了什么**；12 条两边都绿（新 glossary 模块是未跟踪文件、stash 后仍在，以及"backdoor 家族保持不变"这条不变量），同样不算。+46 →**3542**。**覆盖归零的证据**：用同一份记账在改后重跑整套，`methods with ANY missing ledger: 0 / 36`——这是唯一能证明"覆盖住了"的东西，推理和逐个抽查都不算。

**基线**：3496 → **3542**（更早 3477 → 3496、3458 → 3477、3439 → 3458、3421 → 3439、3389 → 3421、3373 → 3389、3367 → 3373、3356 → 3367、3324 → 3356）。更早的跳幅（3221 → 3324）还吸收了此前 session 只提了 feat、没更新本文件的两档（`a2bac78` 联合平行多中介 NDE/NIE、`fa686a0` CDE-for-a-set），它们的详细条目未回填。

**旧基线行**（保留原文，勿改写）：3477 → **3496**（更早 3458 → 3477、3439 → 3458、3421 → 3439、3389 → 3421、3373 → 3389、3367 → 3373、3356 → 3367、3324 → 3356）。更早的跳幅（3221 → 3324）还吸收了此前 session 只提了 feat、没更新本文件的两档（`a2bac78` 联合平行多中介 NDE/NIE、`fa686a0` CDE-for-a-set），它们的详细条目未回填。

**独立性单位被静默丢掉：把"这次跑用了哪个簇列"记成运行级事实（2026-07-28b）**：修复型。簇 / 分块列是一句关于**独立性单位**的声明。honour 它区间变宽，丢掉它区间偏窄——而**点估计一模一样**，所以这类错答在数上完全看不出来，只体现在一个没有原始数据就核不了的宽度里。

**现象（实测）**——`themis.estimate(prog, df, cluster="clinic")` 在纵向程序上返回的区间与 `cluster=None` **逐位相同**（g-formula 0.809918、IPW-MSM 0.917301，两次一字不差），而 `"clinic"` 在整个信封里**一处都不出现**：没有 `bootstrap` 块、没有假设条目、没有 data_contract 警告。用户声明了簇结构，Themis 悄悄丢掉并发了一个反保守的区间。

**规模（全量静态记账，不是抽查）**——用 ast 枚举 `dispatch.py` 里**所有会产出 `numeric_estimate` / `numeric_bounds` 的函数**：22 个生产者，21 个把解析出的 `cluster` 交给了自己的估计器，**只有 `_maybe_estimate_longitudinal` 一个没有**（`_try_dose_response_estimate` 收了参数但**诚实声明**它的 EconML 解析区间做不到簇稳健，属于已披露）。再往下一层查估计器模块本身：每个 honour 簇列的估计器**本来就**在自己的 `assumptions` 里声明了（`ci_via_pairs_cluster_bootstrap_on_<col>` / `cluster_robust_influence_variance_on_<col>` / RC 那条中文散文），dose-response 声明相反的那条——**两个独立来源一直都躺在信封里，只是从来没人做过交叉核对**。

**根因**——「这次跑解析出了哪个簇列」这个**运行级事实从来没有被记录过**。信封里唯一提到簇的地方是 `numeric_estimate.bootstrap`，而那是各生产者**逐个手写**的声明（19 处 `_attach_bootstrap_meta` 调用，18 处传的是原始入参、只有 `_try_joint_estimate` 传的是估计器报回来的 `estimate.cluster`）。于是「没人命名簇列」与「命名了但这个估计器丢了」在信封里**完全同形**，任何验证器都分不出来。

**为什么是根因不是表象**——给 `_maybe_estimate_longitudinal` 补一个参数能修好今天这一个，**默认值原封不动**：明天第 23 个生产者照样静默丢。21/22 的正确率是**靠自觉维持的**，而自觉正是会衰减的那种性质。

**改法**——①`estimation_context.cluster` 记录运行级解析结果，**记一次、放在 missingness 早返回分支之前**（`random_state`/`ci_bootstrap` 已在同一个块里，同属推断级输入；只在解析到簇列时写，无簇的信封逐字节不变）；②纵向 g-formula 与 IPW-MSM 真正吃下簇列（`presence_columns` 带进契约 → `cluster_labels` → `resample_indices(groups=)`，两条 bootstrap 回路各一处），估计量**报回**自己实际重采样的那一列，dispatch 按**报回值**盖章而不是按入参——声明与事实于是不可能漂开；③新验证器把两个来源对起来。

**验证器**——`verify_cluster_inference`（`verifier/cluster_inference_rules.py`，独立性钉：不许 import `themis.estimation`），进 `verify()` 且另有 result-only 公开入口。判据是**单边**的、从"沉默意味着什么"推出来的：运行级记了簇列，则每个**带区间**的数值答案必须在它**自己声明的假设**里点名这一列——honour 了或明确说没 honour 都行，**沉默不行**，因为对消费者来说沉默与"这些行本来就独立"无法区分。镜像故障也拒：盖了章但运行级没记簇列 / 盖的列与运行解析的不是同一列 / 盖了章但估计器自己的声明里没有这一列（=dispatch 在替估计器做一个它从没做过的断言）。**判据刻意与措辞无关**——只查列名是否出现，不钉某一种拼法，否则审计就变成对生产者字符串格式的转写。**刻意不审**区间在数值上到底是不是簇稳健：重跑百分位 bootstrap 需要原始数据，那是本包每个数值验证器都停下的 data-refit 天花板；可审计的断言是披露，而这次的故障恰恰藏在披露里。

**D1**——31 条新测试在改前代码上跑：**6 条红在正确的理由**（运行级 `cluster` 没被记录 ×2〔显式 kwarg / `options.cluster` 两条入口〕；纵向答案端到端"加簇列后区间宽度**逐位相同**" ×2；簇声明没进 `assumption_ledger`〔渲染层领起的那个面〕×2）；**20 条红在机械原因**——8 条是 `estimate_longitudinal_*() got an unexpected keyword 'cluster'`（签名不存在），12 条是 `themis.verify_cluster_inference` 当时不存在，**都不算作证明了什么**；5 条两边都绿（横截面家族本来就诚实），同样不算。**真值 oracle**：簇层随机化 + 簇效应的纵向 DGP（真值 ψ=6.5 解析已知），10 次重抽——i.i.d. 区间在名义 95% 下只覆盖 7/10、8/10，簇 bootstrap 覆盖 9/10 以上且宽度是前者的 1.5 倍以上。**这一对才是这次改动存在的理由，写成了测试**。

**取舍**——18 处仍传原始入参的 `_attach_bootstrap_meta` 调用点**没有一并改成报回值形式**：那条 `cluster in df.columns else None` 降级分支经公开入口不可达（`validate_data` 对缺失的簇列直接抛错），所以那 18 处目前不说谎，改它们是无实测缺陷支撑的 churn。新验证器要求「盖章必须有估计器侧声明佐证」已经把这一类挡在信封层了。

**基线**：3542 → **3573**。

**误测的代价取决于它落在哪个位置：连续结局的经典误差不需要校正（2026-07-28c）**：修复型。测量噪声一直被当成一种**与位置无关**的威胁。但后果完全由位置决定：落在暴露上是回归稀释、落在协变量上是残差混淆、落在**连续结局**上则一点偏倚都没有——经典可加误差保持所有条件均值不变，而本包在连续结局上报的每一个估计量都是由条件均值搭起来的。

**现象（实测）**——同一个连续后门程序、同一份数据：无 spec 时 `backdoor_linear` 给 0.8117（真值 0.8）、`numerically_solved`；加上 `measurement_error={"y": {...}}` 后**一个数都没有**，`needs_investigation` + `continuous_outcome_mismeasurement_deferred`；`{"x": …, "y": …}` 同时给则 `combined_mismeasurement_deferred`，**连本来做得出来的暴露侧 RC 校正一起扔掉**。把同一份数据的结局换成潜在的干净值再跑一遍，得 0.8074——**被拒绝掉的那个数本来就是对的**。独立核实：V⊥(X,Z,Y\*) 时斜率 0.7929 vs 干净 0.7994（n=20 万，se=0.005），偏倚没有，se 涨 2.232 倍，而理论值 √(1+σ²_v/σ²_true)=√5=**2.236**。

**根因**——这两条分支按「**哪个变量带了 spec**」分流，而不是按「这个变量在估计量里的位置意味着什么」。于是「校正做不出来」与「根本不需要校正」塌成同一个拒绝，消费者分不出是哪一种；联合情形下还把唯一可用的那个校正一并牺牲。

**为什么是根因不是表象**——直接删掉这两条分支会让结局 spec **静默失效**：收下一个载荷性外部输入却不产生任何可观察后果，这正是本仓反复抓到的另一种失败。改法必须给结局通道自己的后果。

**改法**——新 `estimation/outcome_error.py`：`Var(Y|D)=Var(Y*|D)+σ²_v` 把观测残差方差劈成信号与测量噪声，`se_inflation=√(Var(Y|D)/Var(Y*|D))` 是**报出来的区间除以同一设计在结局测准时会给出的区间**——它把两种补救分开了，这部分宽度**加样本量消不掉、只能靠把结局测准**。dispatch 的两条 deferred 改成「校验 spec 后放行」：结局 spec 不再声称这条查询，点估计照常由原路由产出（联合情形照跑 RC）。拒绝换成三条**正确**的：结局离散（那是误分类，误差**确实**衰减效应且**可**校正——指向 `misclassification=`）、σ²_v 非正、**σ²_v ≥ 残差方差**（声明的噪声塞不进数据留下的未解释变异，则声明的方差 / 结局模型线性 / 误差与设计独立三者至少一条为假，而**最后那条正是点估计免疫的前提**）。

**边界（声明）**——分解取在后门设计周围，所以无后门集时（IV / front-door / 不可识别）**不出评估、也不出数**，与 RC 完全同形：调用方给了一个载荷性输入而这里 honour 不了，就不发那个数。点估计免疫这一条其实对 IV / front-door 一样成立（它们同样由条件均值搭成），把评估推广到那些设计是独立的下一档。

**披露**——两条前提（**非差异**=点估计免疫的理由，作废级；σ²_v 已知且固定=只影响精度陈述，置信级）作为 glossary 前缀条目进假设账本。这里推翻了上一档我自己写下的边界：`augment_assumption_ledger` 里「估计器已声明结构化 identification 条目时 flat 通道不读」的理由是「flat 是它的非结构化孪生」——那对**估计器自己的**通道成立，但 `outcome_error` 是**另一个作者的另一条通道**，说的是 identification 没说过的事。所以它按自己的 provenance（`measurement_declared`）**无条件**折进账本，孪生规则原封不动只管它本来管的那条通道，17 个既有账本逐字节不变。报告层把 `se_inflation` 印在 `precision_budget` 提示**旁边**：那条提示说"再加多少样本能把区间减半"，而这段宽度加多少样本都减不掉，只印前者会把读者送去买错东西。

**验证器**——`verify_outcome_error`（`verifier/outcome_error_rules.py`，独立性钉：不许 import `themis.estimation`；自带高斯消元，不与生产者共用线代）。它审两件事：**算术**（残差方差 / 信号方差 / 噪声占比 / 膨胀因子全部从记录的 Σ_D、Cov(D,Y)、Var(Y)、σ²_v 重算，抄邻近一次运行的因子活不下来）与**披露**（前提必须到达假设账本——停在自己那个块里的前提，对下游而言等于没有假设）。还拒镜像故障：分解所用的设计不是估计量报告自己拟合的那个设计。**刻意不审** Σ_D 与 Var(Y) 是不是这份数据的矩——重导它们需要样本，那是 data-refit 天花板。

**D1**——34 条新测试在改前代码上跑：**13 条红在正确的理由**（被withheld 的数本该产出、联合情形丢掉 RC 校正、三条分解/oracle、两条账本、报告打的是 manski 界而不是数、两条拒绝给的是错的 failure_type、schema 不通过、无后门时的诊断）；**17 条红在机械原因**（7 条 `assess_outcome_error` 不存在，10 条因 `outcome_error` 块不存在而在 fixture 里 KeyError），**不算作证明了什么**；2 条两边都绿，同样不算。**真值 oracle 两条独立路线**：解析 OLS 在干净 / 观测结局上的 se 之比（rel 2% 内），以及引擎实际发出的 bootstrap 区间宽度之比（rel 10% 内、>1.5 倍）。

**顺带发现但只修了自己那部分**——`estimator_failure.failure_type` 是个**封闭 enum，只列了 10 个值，而估计器实际会发出 51 个**：任何一次拒绝只要类型不在表里，信封就**不满足自己的 schema**，而所有公开 verify 入口都先 `validate_result`，于是那种结果**根本无法被审计**。本档只把自己新发的四个补进去并加了「拒绝信封也要过 schema」的测试，同时在 schema 描述里写明这个缺口是**已知缺陷**而不是"其余拒绝都合法"的断言。系统性修法（enum 该不该封闭）另开一档。

**基线**：3573 → **3607**。

**一个元素的块在数据端被丢掉（2026-07-28d，Phase 17 slice 0 的产物）**：修复型。为 `PHASE_17_STRATEGY_TABLE_CHARTER.md` 做守卫等价性审计时实测出来的第一个真 bug。

**现象（实测）**——同一份 AST、同一份数据，只把 `mediators` 从 `[m1, m2]` 换成 `[m1]`：识别端两种情形都给出联合块且 `identifiable`；估计端 k=2 给 `mediation_joint_linear` 带 `decomposition`，k=1 给 **`backdoor_linear`，point 2.2018，没有 decomposition**——而真值 NIE 是 1.70，2.2018 是**总效应**。同一个信封里同时挂着 `extensions.mediation_joint_decomposition`（"我做了分解"）和一个与中介无关的数，缺口报告还在提示 `mediation_identification_assumption_required`。

**根因**——`_estimate_effect_queries` 的守卫是 `len(mediators) >= 2`，一个**关于集合大小**的判断，而路由该依据的是**这个查询问的是什么**。表象读法是"阈值写错了"，但 `>= 2` 当初不是笔误：它是在"两个以上走联合、一个走单数路径"的分流意图下写的。真问题是 `mediators` 与 `mediator` 是**两个不同的字段**，填了前者永远不会填后者，所以"一个走单数"这条路在字段层面根本不通——尺寸阈值不是分流，是**丢弃**。识别层后来认识到了这点并改成 `if q.mediators:`（注释明确论证"一个元素的块仍是块，k=1 时 estimator 逐字节相同，否则就是用户看不见的静默能力丢失"），**估计层没跟上**。这正是 Phase 17 要消灭的东西：同一个分流决定被两层各自表达，然后漂移。

**改法**——守卫改为 `if q_stmt.query.mediators:`，与识别层同源。全仓只此一处 `>= 2`；`estimate_mediation_joint` 的 k=1 支持早就存在且由 `test_k1_equivalence_to_single_mediator_linear` 独立钉住（它在 k=1 时逐位等于 `estimate_mediation`），卡住的只有这个守卫。注释重写成说原理而非说数字。

**测试**——`test_a_block_of_one_reaches_the_data_end_too`，紧挨识别端的 `test_a_block_of_one_is_still_answered`，**成对，一层一条**。断言链是「识别层说做了分解 ⟹ 数必须是那个分解」而非硬编码字符串：先核 `nde_nie.identifiable`，再核 method，最后以 `estimate_mediation(mediator="m1")` 作**独立 oracle** 校 NDE/NIE 两个点（k=1 等价性由另一条测试独立钉住，故非自证）。**D1**：改前红在 `assert 'backdoor_linear' == 'mediation_joint_linear'`——fixture 正常执行、识别层断言先过，红的是行为不是环境。全仓仅两处构造单元素 `mediators`（识别端老测试 + 本条），**没有任何测试断言过旧行为**。

**基线**：3607 → **3608**。

**两层守卫的两处漂移（2026-07-28e，Phase 17 slice 0 的另外两个产物）**：修复型，同批两条，都由守卫等价性审计实测暴露。

**B — 一个字段吞掉整个数值端**。现象：`_transport_program` 上做三组对照，A（图里无 m）与 B（图里加 `x→m→y`、query 不写 `mediator`）都给 `transport_post_stratification` 0.4106 逐位相同；C（同一张图、query 写 `mediator: m`）**三个答案通道全空**，`estimator_failure` 也是 `None`——估计层对自己什么都没产出这件事一个字没记。识别层三组都走 transport（`target_population` 在它的级联里排第 3、`mediator` 排第 6）。根因：`_try_mediation_estimate` 本来就读 `extensions.mediation_decomposition`、识别层没选中介它就会拒——**但守卫在它拒绝之后仍然无条件 `continue`**。分支用「查询提到了中介」认领了查询，而它实际能不能做取决于识别层的选择。表象读法是「把 continue 改成条件的」。

**第一版改法是错的，全量套件把它抓了出来（2 failed）**：我让「产出了数」当认领判据，于是「识别层选了中介但中介不可识别」（中间混杂，`strategy == "none"`）的查询也不再认领，落到后门分支拿到一个**总效应**的数——**正是发现 A 的错误，我刚修完就自己犯了一遍**。判据不是「我产出了数」，而是「**识别层是不是把这个查询路由给了我**」：块**不存在** = 识别层选了别的策略 → 不认领；块**存在但不可识别/算不出来** = 识别层就是选了中介、只是没走通 → **必须认领**，宁可什么都不给，也不能让另一个估计量顶上。改完后两个 helper 各恰好一个 `return False`（块不存在），其余全部认领。

这件事本身是 Phase 17 论点的又一证据：**估计层唯一该做的是跟随识别层的决定，而不是从查询字段重新推导**——我第一版写错，正因为我也在用「字段 + 产出」推理而不是读识别层的决定。顺带把 `_try_*` 的 10 bool / 9 None 双协议往单一契约推进一格，是 slice 1 的定金；由此也给 slice 1 定了判据：**返回值的语义是「这个查询是不是我的」，不是「我算出来了没有」**。

**工具教训**：那次误报「全量通过」源于 `pytest -q 2>&1 | tail` 取到的是 `tail` 的退出码。全量一律直接取 pytest 退出码，不经管道。

**C — 声明一个假设，把无假设的答案换成了需假设的答案**。现象：Pearl napkin（`w→z→x→y`, `w↔x`, `w↔y`；实测该图后门集 0、前门集 0、恰有一个条件工具 `z|w`）上供足 theta，同一查询只多声明一个 `monotonicity`：不声明走 `identify_via_tian` 得 0.6021（正是查询问的 P(Y=1|do(x=1))，DGP 真值 0.6036）；声明则走 `iv_wald_numeric_evaluate` 得 0.2122（Wald LATE，一个 complier 上的对比量）。两个数各自都对，但**不是同一个量**——多给一条信息，估计量退化了。根因：识别层把需假设的 IV escalation 排在无假设的 general-ID 之前，而估计层反过来且注释早已写明理由（"c-factor 估计量无假设，IV 点估计需单调性/效应同质性"）。改法：Tian 块移到 IV 之前，保住 `iv_attempt` 仍在最终拒绝之前求值（那句拒绝要用它的 `missing` 说「有工具变量，只是你没声明单调性」）。**这不是静默缺陷**——IV 路径的 `late_caveat` 披露充分；缺陷在策略。

**测试**——B：`test_a_named_mediator_does_not_swallow_the_transport_number`，三组对照写进断言，把「图变了」与「字段变了」分开。C：`test_declaring_an_assumption_does_not_replace_the_assumption_free_answer`，napkin + 由**一个显式联合**导出的自洽 theta（不依赖数据、条件层权重严格和 1），并带**防空过守卫**：先断言该图上 `iv_sets` 非空且后门/前门皆空，否则「IV 没抢先」什么都证明不了。**D1**：`git stash` 掉源码改动只留测试 → C 红在 `'identify_via_tian' not in ['iv_criterion_check','identify_via_iv',...]`，B 红在 `assert None is not None`，均非机械红（前置守卫断言先过）。

**一条我提错并就地作废的发现**——曾把「C 的 `answer_tier` 仍是 `point` 而信封无数」记为可能缺陷。读 `_compute_answer_tier` 契约后作废：POINT 的语义是「点估计量可识别」，docstring 明确把「identifiable-but-missing-θ」算作 POINT，所以它符合自己的契约。**方法论**：C 的第一次探针跑出「无分歧」，真因是探针把概率 `round(p, 6)` 导致条件层权重和 0.999999≠1、IV 路径**正确地拒绝**了那份 theta——探针的「没测出来」必须先自证不是探针自身的假象。

**基线**：3608 → **3610**。

**级联的认领协议统一（2026-07-29，Phase 17 slice 1）**：结构型。估计级联是一串带守卫的 handler，每个决定「这个查询是不是我的」。此前这个决定用**两套互不兼容的约定**承载——10 个返回 `bool`、9 个返回 `None`，而那 10 个里还有 1 个的 `True` 与其余 9 个含义**正好相反**（`_try_outcome_error_assessment` 的 True 表示「没认领、继续走」）。更要命的是两套都表达不了决定正确性的那件事：**一个 handler 拥有某个查询却答不出来**。发现 A / B 两个已测缺陷正长在这个表达不了的位置上。

**改法**——`themis/estimation/claim.py` 定四态，19/19 handler 全部改说（AST 级核过，无一残留 `bool`/`None`/裸 `return`）：`answered()`（拥有，答案已附）/ `blocked(reason)`（**拥有但答不出来，查询到此为止**）/ `annotated()`（在答案旁加了东西，不拥有）/ `passed(reason)`（还在飞，后面有人接**同一个问题**）。第二态是全部意义所在；第三态兑现了 charter 预留的 `annotate` 角色，那个协议倒置的 handler 归位于此。**理由词汇表 8 条**，全部从代码提出、每条附一句「谁能改变它」（图/数据/本包/装依赖），`blocked()`/`passed()` 当场拒绝未登记的理由。

**修正 charter 的数字**——「27 处裸 return」错了：它把 **13 处纯 helper**（`_compute_precision_budget`、`_is_binary_treatment` 等）的 `return None` 算了进去，那里的 None 是「没有值」不是「拒绝一个查询」。真正的策略拒绝 **22 处**，另有 7 个 `-> None` handler 的 33 个裸 return。

**转换中暴露三件事**——(1) `_try_dose_response_estimate` **早就在做对的事**：四个出口三个是「把失败写进信封 + 认领」，正是本协议要形式化的模式，但它一个人做对、另外 18 个都没学——**没有一等表示的东西，正确做法无法传播**。(2) 它调用点那句「fall through to the binary path so the user still gets *something*」描述的分支**不可达**（该函数没有 `return False`）；不可达是好事，但注释在说一件没发生的事，登记为独立小项。(3) 9 处宽 `except (EstimatorFailure, ValueError, NotImplementedError)` 把「估计器诚实拒绝」与「代码炸了」压进同一分支——只登记不拆，拆它是行为变更，独立一档。

**元测试当场抓到两个我自己造的缺陷**（`tests/test_claim_protocol.py`，8 条）——(1) **`Claim` 是 dataclass，永远真值为 True**：两个中介调用点仍写 `if _try_x(...):`，于是**每个**查询都被认领，**发现 B 被原样打破**。这是类型从值语义迁到对象语义时的必然陷阱且完全静默，故专有一条测试钉「调用点必须读 `.stops_here`」；同一次全量独立复现（`assert None is not None`），两条路径指向同一缺陷。(2) **`combination_out_of_scope` 用了但没登记**：运行时会抛，但没有测试走那条路径——**它会先到用户手里再到测试手里**，静态扫描全文件字面量的那条测试专抓这类。

**仍靠 review 的不变量（交棒 slice 2）**——`blocked` 与 `passed` 的分界是「往下传只有在接手者回答**同一个问题**时才合法」。此刻机器强制不了：没有 handler 声明自己瞄准哪个估计量。策略表的 `produces` 兑现它后，驱动即可断言「一次 `passed` 之后真正作答的策略，估计量必须与放行者相同」——**那正是发现 A、B 与我 Fix B 第一版三次踩的同一个坑**。

**基线**：3610 → **3618**。

**估计层策略表 + 驱动（2026-07-29，Phase 17 slice 2）**：结构型。`_estimate_effect_queries` 从 **570 行的 if 链降到 ~90 行的装配器**，路由本身搬进 `_EFFECT_STRATEGIES`——**18 行，优先级 10..180，与旧链逐条同序**（一条测试逐字钉住这个顺序，任何重排必须是对那张清单的显式编辑，不能是挪代码的副作用）。13 行是原有 `_try_*`；**5 行是原先内联在链里的**（backdoor / frontdoor / IV-Wald / doubly-robust / dose-response 二值回退）——不抽出来，优先级就仍有一半是行号，表就是假的。

**三个结构性判定**——(1) **守卫看不见本层输出，不是靠约定而是没有那个属性**：`EffectFacts` 没有 `result` 字段，想读只能 AttributeError；守卫**可以**读识别层的结论（`selection_recovery` 由识别层独家写入），那是分层边界在正常工作。一条测试要求每个守卫 lambda 体内除自己的参数和 builtins 外不出现任何名字——**守卫是 facts 的纯函数**。(2) **「longitudinal 已作答」不是守卫、是驱动的终止条件**：没有任何策略靠它路由，归位后「守卫不许读 result」才是全称成立而非带例外。它仍在嗅方法名残迹，**本档没修**——让那趟显式声明认领，得先回答「它因识别失败拒答、不留任何残迹时该发生什么」，是行为问题不是表的问题，独立登记。(3) **表覆盖效应级联，不是全部 19 个 `_try_*`**：另外 6 个属于「一个 query kind 一个策略」的驱动，**没有级联就没有优先级漂移**，此刻入表只增条目不消风险，留到 slice 6 派生面需要块登记时一起。

**用全量套件实测级联在做什么**（驱动返回 `Evaluation`，外挂 pytest plugin 收集，不进仓）——**434 次求值**：`fired` 以 backdoor 98 / iv_wald 70 / dose_response 29 领衔；`declined` 20 种 (策略,理由) 组合；`passed_by` **92 次其中 88 次是 general_id**；`substitutions`（放行者与作答者估计量不同）**只有两种形状**：general_id→IV **80 次**、mediation_single→transport **1 次**；无人作答且无人记录 **8 次**。

**实测把 slice 1 交接的不变量改了形状，然后兑现了它**——交棒原话是「往下传只有在接手者回答同一个问题时才合法」。**实测证明按字面讲这条是错的**：general_id 放行、IV 作答的 80 次里 IV 给的是 complier 对比量，根本不是同一个量，而那正是有意为之的逃生梯（答案上挂着 `late_caveat`）。按字面执行会打断 81 条正确路径。正确的规则是「**替换必须被声明**」，落成 `Strategy.defers_to`：同估计量接力不需声明（本就是同一个问题），换估计量必须在表里写明谁可以替我作答。**全表只有两条声明，恰好等于实测出的两种形状**，其余任何替换当场 `AssertionError`。**规则选型是按「能不能抓住已经发生过的错」定的**：slice 1 里 Fix B 的第一版会让分解型查询掉进 backdoor 拿总效应——`backdoor ∉ mediation_single.defers_to`，直接炸；而若改用「理由是否许可替换」那种更省事的判据，那次就抓不到。

**实测顺带查出两件事（都不在本档修）**——(1) **`general_id` 的 88 次放行全部报 `estimator_refused`**，而它那个宽 except 的注释自己写明吞了三样：「非参数不可识别」（结构，该 `not_identified`）、「超出插件二值范围」（本包，该 `numeric_end_not_built`）、「positivity 拒绝」（数据）。理由词汇表的意义是告诉读者**谁能改变它**，而全系统流量最大的拒绝点报的是错的那个——这就是 slice 1 登记的「9 处宽 except」，**现在它有数字了：88/92**。(2) **8 次「无人作答且无人记录」**，恰好 = 88 − 80：非参数识别失败且图上无工具变量 → 信封里没有数也没有 `estimator_failure`。这是发现 B 的形状，属既有行为，**现在是一个测出来的数而不是一个猜想**，slice 4（`declined` → 缺口）的第一批客户。

**顺带结清两个登记项**——`_try_dose_response_estimate` 那句说谎的调用点注释随内联分支一并消失；slice 1 的元测试「调用点必须读 `.stops_here`」表化后会**空转**，改成更强的一条：**dispatch.py 里任何 `if` 条件中都不许出现 `_try_*` 调用**——多一个手写分支就是多一个派发器，而两个派发器正是两层当初漂开的原因。

**基线**：3618 → **3644**。

**识别层的策略梯子合成一条（2026-07-29，Phase 17 发现 D）**：修复型。**同一个 AST、同一个查询，两个入口给出相反的结论**：`x→m→y` 无双向边、问 `P(y|do(x), m)`，`themis.run` 报 `structure / identification:not_identifiable`（无 derivation），`themis.estimate` 却给出 `general_id_idc_plugin`、point 0.0、完整 derivation——而**独立重导的验证器接受后者**。0.0 是对的（图上 y ⊥ x | m，条件对比量本就为零）。在 slice 2 之前的 commit 独立 worktree 上逐字复现，**既有缺陷，非重构引入**。

**根因**——`_dispatch_effect` 的结构性策略尾巴**在同一个函数体内写了两遍**：一份在 `if bidirected:` 的 else 里，含 front-door → Tian → IV → **IDC** → 拒答；另一份在 `if not adjustment_sets:` 里，**只有 front-door → 拒答**。无潜在混杂的查询走第二份，IDC 永远不可达。而 **IDC 做的是条件识别，与潜在混杂正交**——它被 `bidirected` 挡住纯粹因为它恰好被写在了那一份拷贝里。两条硬证据说明这不是设计：(1) 两份的 front-door 段**逐字节相同**，只差一个 `bidirected=` kwarg，而 solver 三个入口该参数的默认值就是 `None`——那个分叉在结构上什么也没买到；(2) 第一份的注释逐条论证了「Tian 为何排在 IV 前」「IDC 为何不能拿边际顶替条件」，**这些论证对第二份同样成立，第二份只是没有它们**。

**改法**——合成一条尾巴，`adjustment_sets` 用 `bidirected or None` 一次算出。**拒答文案不合并**：ADMG 版会说「Tian/ID 都试过了」并挂 `iv_note`，对一个没有潜在混杂的用户描述的是他从未涉及的机器；按 `bidirected` 是否为空选择，逐字不变。合并的是梯子，不是措辞。修复后 `themis.run` 从「图挡住了」错判变成 **`parameter / P(y=True|m=True)`**——识别成功、缺这个数，而缺的正是 IDC 公式逐项要的那两个条件概率。

**全量只有 4 条失败，全部同一 fixture，判定是「测试的前提是一个错误的理论陈述」**——`_collider_program` 的 docstring 写着「没有后门也没有前门可调整集，所以 kernel 报 `identification:not_identifiable`」，**这不是定理**：全观测 DAG 上每个干预分布都可识别（ID/IDC 完备性），没有可调整集只排除了那两条调整公式。**kernel 一直同意这句错话，恰恰因为它的 IDC 分支被潜在混杂守卫挡着。** 修法是给 fixture 补上它名字里一直暗示、图里却没有的那条 bow arc，不是改代码迁就测试。

**两件明确没在本档动的**——(1) 普通拒答设 `structural_result=False`、ADMG 拒答留 `None`，是同族第四处不一致；不动的理由是它**承重**：`oracle/differential.py:246` 正是用 `structural_result is None` 判断「运行时没给出结构判决，无从比对」，改它会把一批 ADMG 拒答送进差分比对，那需要它自己的判定。(2) 合并后**没有任何测试再产出 `identification:not_identifiable``**；要么它本来就该死（此前只在可识别的查询上触发），要么它是 IDC 实现 hedge 时的兜底——**我无法证明 `identify_via_idc` 的完备性，所以不宣称它是死代码**。

**基线**：3644 → **3645**。

**Wald 比不能回答条件查询（2026-07-29，Phase 17 发现 E）**：修复型。为 slice 3 合表逐条比对两层的 IV 守卫时发现：估计层的 `iv_wald` / `iv_overidentified` 守卫里**没有任何关于 `given` 的条件**，而 `front_door_sets` 在有 `given` 时返回 `()` 的短路恰好让这两行**可达**。见证：napkin 上问 `P(y|do(x), w)`，`themis.run` 拒答（`query:effect_admg_conditional`，明说「不拿边际顶替」），`themis.estimate` 却给出 `iv_stratified_wald` point 0.1627。**这个数不可能是任一问题的答案**——把 `given` 从 `w=True` 换成 `w=False`，两次输出**逐位相同**；信封里报的 `conditioning: ["w"]` 是**工具变量自己的条件集 W**，与查询的 `given` 只是碰巧同名（换一张图，W=∅ 而 `given={c}`，照样出 `iv_wald`）。

**根因**——「IV 只回答无条件查询」这条约束**从来不是守卫，而是一个函数体的第一行**（`_try_iv_wald_in_effect` 开头的 `if q.given: return`），其 docstring 还把理由写得很清楚。**理由写在了正确的地方，约束却写在了只对一个调用点生效的地方**。估计层的守卫是另写的：它继承了 front-door 的同类约束（因为那一条被表达成了**事实**），没有继承 IV 的（因为 IV 那条不在事实里）。表象修法是在 handler 里再加一行判断——那是把同一条约束写第三遍，且 `iv_overidentified` 和将来任何 IV 族策略还会各漏一次。**结构性修改**：`EffectFacts.iv_candidates` 在 `given_atoms` 非空时返回 `()`，与 `front_door_sets` 逐字同构，两行 IV 守卫和 `overid_instruments` 一起受约束。

**代价，明说**：修后该查询在估计层**一个数都没有**，且 `estimator_failure` 仍是 `None`（general_id 放行、无人接手）——正是 slice 2 实测到的「8 次无人作答且无人记录」那一族，slice 4 的客户。**没有数**比**一个答非所问的数**正确；识别层对同一查询本来就是拒答。

**基线**：3645 → **3646**。

**一张路由表，两层各绑一端（2026-07-29，Phase 17 slice 3）**：结构型。「谁来回答这个查询、按什么顺序」是关于**问题**的事实，不属于任何一层；而两层各自决定过它——识别层是 `_dispatch_effect` 里 431 行的 `if` 链，估计层是一张表——**两份拷贝已实测漂移五次**：顺序三次（发现 A、C 在内）、可达性一次（D）、约束覆盖一次（E）。`themis/routing.py` 把它变成数据：**19 行，一条优先级轴，三个带**——10-50 按**问题的形状**路由（在看图之前）、60-140 是数据层（识别层看不见 DataFrame）、150-190 是结构梯子（**无假设永远排在需假设之前**）。三个带交错在同一条轴上而不是分成三张表，因为「谁来回答」只有一个答案。`_dispatch_effect` **431 行 → 59 行**，且只做装配 + 按表发问（一条测试钉住：驱动体内不许出现任何策略名）。

**三条保证都不是约定**——(1) **`Strategy` 持有 route 对象本身而非拷贝其字段**，`id`/`precedence`/`applies_when` 穿透读，两层同序从此是**对象同一性**而不是一次「看着一样」的比对（那个比对无声失败过三次）。(2) **`ends` 不是标签，是绑定检查的依据**：`routing.bind` 双向拒绝——声明了某端却没绑（**发现 D 的形状：表承诺了条件识别，那层从来没跑**），以及绑了表不路由过来的（**第二个派发器的起点**）。(3) **事实分层用类型表达**：`StructuralFacts`（两层都有）→ `EffectFacts` / 识别层 `_EffectFacts`；只有识别端的路由，其守卫命名的是只有那层事实才有的属性——拿到另一层求值就是 AttributeError。

**顺序合一，一条 `defers_to` 随之消失**——transport 移到 mediation 之前（取识别层原序：同时点名 mediator 与 target_population 的查询**只有一个主人**，且 transport 会显式报 `unattempted_layer_due_to_dispatch_conflict`）。`mediation_single.defers_to = {"transport"}` 一并删除：**那条声明本来就只是两份拷贝分歧的产物**——估计层 mediation 在前，只能靠它先站下来才走得到 transport，而两者估计量不同，所以那次交接必须被声明；合表后交接根本不发生。**这不是推理断言的**：「未声明的替换当场 AssertionError」仍武装着、声明已删，**全量绿 ⇒ 该交接一次都没再发生**。

**明确没做的**——10 个按 query kind 选择的 dispatcher 不入表（一个查询只有一种 kind，**没有优先级就没有漂移**）；拒答文案仍按 `bidirected` 分叉（**合并的是梯子不是措辞**）；`structural_result` 第四处不一致仍在（承重，见发现 D）。

**基线**：3646 → **3652**。

**「given」里有「iv」（2026-07-29，Phase 17 发现 F）**：修复型，用户可见。为 slice 4 实测缺口报告时撞出：`x→y`、`x→d`，问 `identify(y | do(x), given=[d])`——`d` 是 X 的后代，kernel **正确拒答**且理由写得很清楚（「identify.given violates backdoor pre-conditions…」），而用户读到的缺口是**「未找到满足 IV 条件的工具变量：query:identify_given」**，真正的原因**一条都没进报告**。根因：`_classify_missing_iv` 判定「这是不是 IV 缺口」用的是 `"iv" not in item.target.lower()`——**一个裸子串测试**，而 `query:identify_g·iv·en` 里有 `iv`；同一个判据又被 `_classify_unidentifiable_from_request` 用来**排除**，**一次巧合既伪造了一个缺口又压掉了真缺口**（两份各自演化的子串测试，所以能同时朝相反方向出错）。同族第二处：该分类器 docstring 明写「程序缺陷走 residual，不许告诉 `answer_tier` 说图挡住了估计量」，却把这条规则编码成前缀 `"query:identify"`——**比规则短了一个词**，于是 `query:identify_unreachable`（ID 算法无 witness）与 `query:identify_given`（用户删一个词就好）被扫进同一类。修法：IV 判据改成「名字的 local part 以 `iv_` 开头」且**两个调用点共用同一个谓词**；前缀收窄成 `query:identify_unreachable`。修后端到端产出 `missing_structural_input | blocking | 缺结构输入：identify.given violates backdoor pre-conditions…`——**kernel 给的理由逐字到了用户眼前**。三条测试各钉一半，都验过非空转。**但这两处都没让编码变对**：缺口的物种仍是一个产生端扔掉、消费端猜回来的字符串——那是 slice 4 的对象，本档是它的见证。

**slice 4 的对象已据实测更正**（charter 内）：28 个 `_classify_*` 按「读什么」分是**三个物种**不是两个（漏了「块回声」一族，它读策略显式写的 `extensions.*`，属翻译不属猜）；且 `declined` 只覆盖驱动层拒绝，缺口报告读的残渣绝大多数是被认领的子 dispatcher 写的 `MissingItem`。**真对象是 `MissingItem.name`**：全仓 33 个构造点全在 `scheduler.py`，`InvestigationItem.target` 就是它原样，`MissingKind` 5 个值 → `GapKind` 36 个值那一步**全靠前缀 / 子串猜**。

**基线**：3652 → **3655**。

**缺口的物种由产生端说出来（2026-07-29，Phase 17 slice 4）**：结构型，两个 commit。`MissingItem.name` 一个字符串背了三件事：**缺什么**、**哪个渠道能补**、**这是哪一类缺口**——前两件各有字段，第三件没有：产生端知道它、压进名字扔掉，消费端再用前缀和子串猜回来（发现 F 就是这么同时伪造一个缺口又压掉一个真缺口的）。`MissingItem.gap` 现在说出来，取值限定在 `types.MISSING_ITEM_GAPS`（**7 个，`GapKind` 36 个的真子集**——绝大多数 GapKind 不是 kernel *撞上*的缺口，而是它*读程序读出来*的告诫，任何 item 都不该声明）。消费端 `_ITEM_SPECIES` 一物种一渲染器，`_bind_item_species` 在 import 时**双向拒绝**：缺绑定 = 有 item 到得了报告却渲染不出东西，多绑定 = 渲染器永远等不到 item。与 slice 3 的 `routing.bind` 同形。

**删掉四样，每样的保证都有接手方**：8 条 `_UNIDENTIFIABLE_PREFIXES`（→ 产生端声明）；`_names_an_instrument` + `_classify_missing_iv` 信号 A（→ `MISSING_IV_CANDIDATE` 不在词表里，**没有名字能变成它**）；`_classify_residual_investigation_items` + `_RESIDUAL_GROUPS`（→ 词表封闭 + 每个成员有绑定 ⇒ 到得了报告就到得了用户，且这条在 **import 时**成立而不是每次运行末尾扫一遍）；`"query:counterfactual_admg"`（全仓无产生端的死规则）。**顺序随之不再承重**：residual 必须最后跑、还要读 `emitted` 才知道跳过谁——两个 pass 抢同一个 item；现在一个 item 一个物种一个渲染器，没有可排的东西。`InvestigationItem.gap` 是**必填**：framing 渠道没有 MissingItem，声明 `AMBIGUOUS_VARIABLE_DEFINITION` 并由表绑到 `_RaisedElsewhere`——**声明的让位，不是表里的空缺**（slice 2 那条规矩）；手搭 request 的测试证明了区别：有默认值它们继续静默不出缺口，没默认值当场构造失败。

**行为不变是证出来的不是论证出来的**：两种编码并存的那个 commit 里，`compute_data_gap_report` **每次运行都断言**声明的物种落在分类器为该 item 推出的那组 kind 里；全量绿 = 断言武装着，**把断言反向套件立刻红** = 它在执行不在跳过。再把断言看到的每个 item 记下来跑全量：**30 个名字模板覆盖了 23 个**，另 5 个是全套件**从来不跑的分支**（`query:identify_unreachable`、`joint:duplicate_treatment`、`joint:unsupported_layer_combination`、`longitudinal:atom_not_in_graph:*`、`transport:*`）——那 5 个上写错物种没有任何东西会发现，正是字符串匹配当年所处的位置；`tests/test_missing_item_species.py` 第一次跑它们。**方法论**：等价性证据必须来自运行，不能重写一遍推断再比对两个猜测；覆盖率必须测，不能因为「全量绿」就当全量测过。

**发现 G（实测确认，真 bug，用户可见，本档只钉住不修）**：transport 不可识别时 `answer_tier == "point"`。见证：`x→y`、选择节点作用在 `y` 上，问 `real_world` 的 `P(y|do(x))`——无 S-admissible 集，kernel 正确拒答且理由逐字进了 summary，`needs_investigation`、**无 formula、无 structural_result**，而 tier 说 point。根因：`_compute_answer_tier` 只认 `unidentifiable_no_admissible_set` 一个物种，而 `transport:{pop}` 落在 `missing_structural_input`（此前 residual 兜底的结果，本档如实照抄以保行为不变）。**散文说对了，机器读的那个字段说反了。** 声明机制让改法只是一个 token，但那是行为变更，不混进重构档；本档把现状钉住，使那次更正是**看得见的物种变更**而不是悄悄的编辑。

**一处未证实的疑点，登记为待验**：`_classify_missing_mediator` 的 `m in item.target` 不是物种推断而是**连接**（问名字的内容不是它的类别），所以留着；但块里的中介标签是 `_atom_to_str(m)`（`m(me)`）而参数名用裸谓词（`P(y=True|m=True)`），两种格式对不上，则该连接在真实运行里可能从不命中——现有测试全是合成输入。已试构造端到端见证未成功（mediation 查询走 `structurally_solved`，theta 路径不请求参数），**故只登记疑点，不断言它是 bug**。

**基线**：3655 → **3664**。

**transport 不可识别，两个答案字段各错各的（2026-07-29，Phase 17 发现 G）**：修复型，用户可见。`x→y`、选择节点作用在 `y` 上，问 `real_world` 的 `P(y|do(x))`——无 S-admissible 集，kernel **正确拒答**，理由逐字进了 summary，`needs_investigation`、**无 formula、无 structural_result**，而 `answer_tier` 说 **`point`**。根因：`_compute_answer_tier` 判「点估计被挡住没有」只认 `unidentifiable_no_admissible_set` 一个物种，`transport:{pop}` 却落在 `missing_structural_input`。**散文说对了，机器读的那个字段说反了。**

**改物种把第二个错答案掀了出来**：tier 不再说 `point`，改说 **`interval`**，而那个 interval 是 `manski_natural`——**从源人群的观测联合分布算出来的**。选择图刚判定源效应**不可迁移**，也就是说源分布对目标估计量**没有约束**；那个区间不是「关于对的量、松一点」，而是「关于错的量、还挺紧」（源里 `P(y|x)=0.9` 给出的界可以把目标真值 0.1 完全排除）。同族根因：**查询自己带着的 `target_population` 没有任何守卫去看它**——`_attach_bounds_result` 检查了目标事件离散、干预臂离散、状态，唯独没检查这些界限说的是哪个人群。**第一半修好之前，这一半被 `point` 挡着看不见——一个错答案盖住了另一个错答案。**

**两处结构性修改，各说一件事**：(1) `transport:{pop}` 声明 `UNIDENTIFIABLE_NO_ADMISSIBLE_SET`——tier 要读的正是这件事；(2) `_attach_bounds_result` 在 `target_population is not None` 时返回——**无假设的地板是源人群的地板**，换人群就没有无假设的地板。修后 `answer_tier == "none"`、`bounds_result is None`、summary 逐字带 kernel 的理由：**「什么都没有」是这个查询的真答案**，两个字段现在都这么说。

**代价，明说**：`UNIDENTIFIABLE_NO_ADMISSIBLE_SET` 渲染器挂的是**按物种写死的三条通用出路**（测混杂 / 做 RCT / 找工具变量），前两条对 transport 大致说得通（要测的是让 S-admissibility 成立的协变量、RCT 要在目标人群做），第三条不对。**出路取决于识别为什么失败，物种一个人说不出这件事**——同一族的下一个对象（产生端知道怎么补、报告在猜），本次不做，登记。

**基线**：3664（不变，改的是已有测试的断言）。

**后处理的顺序是算出来的（2026-07-29，Phase 17 slice 5）**：结构型。`dispatch()` 尾部把答案交给一串后处理器（置信度轨迹 / 界限 / 缺口报告 / 必须披露的告诫），**它们之间的顺序承重**：framing 跑在 investigation 前面，investigation 就会看到非空的 request 元组、断定「别人已经产出过了」、直接退出，把 missing item 本该产生的每一条 action 全部丢掉。而这个顺序此前**只由九个连写的调用表达，理由写在上面一条注释里**——注释不被任何东西查阅，插错位置的 pass 不是错误而是**一个悄悄不同的答案**（它读到 dispatcher 留下的 `None`，且不会说自己跑早了）。

**声明什么**：`themis/runtime/postprocess.py`。一个 pass 声明它需要已完成的块（`reads`）和它可能改动的块（`writes`），顺序由拓扑排序得出；**两个字段的交集自己携带语义**，不需要第三个动词——只在 `writes` 里 = 产出者，同时在两边 = 改写者。关键是「读」的定义要精确：**一个 `reads` 声明，是在断言「跑在这个块的写者前面会让我给出不同的答案」**。产出者对自己的块做「已经有了就不重复产出」的守卫**不是读**（那读的是 dispatcher 留下的状态，每个 pass 看到的都一样）；把它算作读，`investigation_requests` 就会变成「没有产出者、两个改写者」，表在 import 期直接拒绝。**块的粒度就是依赖存在的粒度**：结果的每个字段是一个块，`extensions` 除外——它是一张 map，三个 pass 各写一个键、谁也不等谁，把整张 map 当一个块会在它们之间连出边，**读起来像一个有含义的顺序**，所以表禁止命名整张 map。

**import 期拒绝五类无法排序的表**：块名不是 `QueryResult` 字段（拼错的依赖静默变成没有依赖）、命名整张 `extensions`、一个块两个产出者、一个块两个改写者（谁先改由声明顺序决定——正是表要取代的东西）、改写一个没人产出的块、环。

**算出来的顺序与手写顺序只差一处，而那一处是修正**：十个 pass（不是九个——`_attach_structural_caveats` 是**藏在 `_attach_data_gap_report` 尾调用里的第十个**），排序结果与手写链条逐位相同，唯一例外是 `data_gap_report → reconcile_alt_paths → structural_caveats`。手写链条里 caveats 跑在 reconcile **之前**，因为它是另一个 pass 的尾调用——**由构造决定而不是由需要决定**；它读缺口报告，而 reconcile 改写缺口报告，读者读到的应当是结果最终带出去的那一版。**一个 pass 藏在另一个 pass 里，正是它当初怎么会读到过期版本的原因。** slice 0 记下的那个陷阱（缺口报告跑在两个 recovery 块之前）现在是**一条声明而不是一个巧合**：报告列出了它读的五个 extension 键，两个 recovery 块不在其中；哪天有 classifier 要读，`reads` 加一行，排序自动改。

**声明是否完备，是跑出来的**：测试不检查算出的顺序等于某个列表，而是检查**声明允许的每一种顺序都给同一个答案**——按依赖随机采样合法线性序（定种子），每个语料程序跑 20 个；漏声明的读会在某个把它排到写者前面的序里露出来。三件配套测量都不是论证：(1) 20 个采样序两两不同且无一等于规范序；(2) **对照实验**——强行把 caveats 排到报告之前（声明禁止的序），`explanation` 里的 ⚠ 行消失，否则那张测试在一张边毫无含义的表上同样会绿；(3) **覆盖率先测后补**——第一版语料下 `selection_recovery` 与 `missing_data_recovery` **从未改动过任何结果**，重排 no-op 不可能移动答案，等于两个 pass 的声明没有任何东西在检查；补两个程序（对撞子上的样本限制 / 结局的缺失指示器）后十个全部走活，并把这条测量**钉成守卫**（新 pass 若无语料能走到它，测试直接红）。

**顺带删掉**：`_attach_bounds_result` 从未被使用的 `bidirected` 参数（统一签名后自然消失）、两个 recovery pass 里 `program is None or stmt is None` 的死守卫、`_attach_data_gap_report` 里「报告为 None 但结果上已有报告」这个不可达分支（该块只有一个产出者，现在是表强制的）。

**基线**：3664 → **3683**（+19，全部是新机制自己的测试）。

**信封的部件只命名一次（2026-08-03，Phase 17 slice 6）**：结构型。结果带两种部件——带类型的是 `QueryResult` 字段（声明一次，拼错即 `AttributeError`），其余住在 `extensions` 这张无类型 map 里，键是**在每个写点和读点各拼一遍的字面量**（20 个块、约 117 处、至少 5 种语法形状），拼错是**沉默**：读者拿到 `None`，然后报出「这个块本来就没有」时会报的东西。这让 slice 5 的保证**卡在它自己那张表的边界上**——`reads={"extensions.拼错"}` import 期通过、运行时永远 None。**登记表本来就存在，只是掉队了没人知道**：`query_result.schema.json` 给其中 9 个块写了完整子 schema，而那张 map 明写「未知字段允许，为前向兼容」，于是另外 11 个块这些年陆续加进来、一个都没进去。`themis/blocks.py` 把 20 个块各声明一次；`Block` 是 `str` 子类，所以块名用在原来的一切地方都不变，但只存在一处，拼错变成 import 期 `AttributeError`。**落进信封的仍是纯字符串**——`__reduce__` 让 copy/pickle 退回 `str`，这条是**套件抓出来的**（deepcopy 一个带 `Block` 键的信封当场炸 = 注册表元数据已渗进数据）。两个单一出口拒绝发出未登记的块；**读不对称**：`verify()` 仍接受别人信封里它不认识的键——开放 map 就是为这个，**关的是我们发出去的东西**。验证器保留字面量（与生产者共享符号等于自证），程序自己的 `extensions` 旁路也保留（它与结果信封只共用 `ambiguities` 这个词）。

**账本的孪生是被声明的，不是被推断的（2026-08-03，Phase 17 slice 6）**：修复型，用户可见。原规则=「只要账本里有一条 identification 条目，估计器那张 flat 声明列表整张都是它的复述，不读」。全量套件带探针实测：**19 个估计器族走这条路径**，随之消失的是它们在识别之外声明的一切——**IPW 用哪种权重（Hájek）、TMLE 是定标代入估计、区间来自影响函数还是聚类 bootstrap、近端识别依赖 Miao model f、因果概率答的是界因为没假设单调性**——而这些**没有别处在说**，账本正是报告与渲染桥都以它开头的那个面。判据无法靠细化来修：**唯一知道谁复述谁的是估计器自己**。改法=每条结构化 spec 带上它所复述的那条 flat 声明的 `id`，折叠规则变成「没有被任何条目按 id 认领的声明，一律折入」；一条把两件事写成一句的 spec 拆成两条（一个 id 一条假设，否则任何按 id 计数的东西都看到一个洞）。**验证器独立写的那份伸手够的是同一个逃生口**——本仓「重复即正确性」第一次实测失效：两份各自演化却收敛到同一个便利假设，所以 19 个族丢假设时两边都不吭声；新规则不看 provenance，只问「声明过的每条 id 在不在账本上」，从信封本身可判定。`outcome_error` 的豁免条款随之消失（它当初存在就是因为孪生规则太粗）。**已知代价（未修、单独登记）**：`mechanism_audit` 条目与被折入的 form 声明并排、文字重叠——方向是多披露（该模块自己写明的安全方向）且替换的是**少**披露，消除它需要让 mechanism 条目声明它覆盖的 id 集合。

**可达性矩阵：建之前先查，发现没有对象（2026-08-03，Phase 17 slice 6）**：charter 把它列在「现在 → 之后」表里，意思是它是一件被单独维护的东西；**实测不是**——仓里从来没有一张可达性矩阵，不在代码也不在文档。而它想防的那类缺陷已有两道：结构那半 slice 3 的 `routing.bind` 已兑现（**发现 D 正是这一类**），经验那半只能测不能从表推（守卫是不透明谓词）——带探针跑全量的实测是 **18 个估计行 × 9 个识别行、27 格全部非空**，且任何一行真死掉**它自己那个特性测试会先红**。此刻建一张矩阵是新增一件维护物，与 slice 目的相反，故按 slice 5 的先例更正原话、不假装兑现。

**跨入口同一估计量给同一个数（2026-08-03，Phase 17 slice 6）**：`produces` 声明一行的数字是**什么的**估计，但**在有东西去比这些数字之前，它宣称的一致性从来不需要兑现**。`tests/test_estimand_agreement.py` 让四个入口（g-formula 默认走 `backdoor` 行，ipw/aipw/tmle 走 `doubly_robust` 行）在同一查询上给数，要求一致。**判据是量出来的**：四个点在给定数据下确定（重采样进的是区间不是点），实测跨度 0.00102，界取五倍 0.005。**区间重叠是错的判据**——区间回答「真值会不会在别处」，这里各约 0.042 宽，只要求点落在别人区间里等于接受两行在 0.30 的效应上差 0.02（实测该判据要 0.03 才报警）。另有一条测试守着这个界本身（区间一旦窄到与界同量级，这条测试就不再比区间多说什么，那时该重新量）。配一条前提测试（四个入口确实落到四个不同方法，否则是拿一个数跟自己比）与一条**说明为什么允许比**的测试：`backdoor` 与 `doubly_robust` 声明同一 estimand，IV 两行声明 `complier_effect`——**是表说了哪些数字可以比，不是读者的判断**。

**基线**：3683 → **3731**（+48：块登记 26、账本 18、估计量一致 4）。

---

**拒答的物种只命名一次（2026-08-03，Phase 17 之后的第一条）**：结构型 + 修复型。拒答在本仓是**一等的答案**——估计器算不出诚实的数就发结构化 `estimator_failure` 而不是发一个有偏的数，`failure_type` 是让这个块可被机器读的那个字段（它自己的话：「让调用方按原因分支，而不用解析自由文本」）。分支要求原因是**已知集合**，而它不是：schema 的 enum 是封闭的、列 **14** 个，估计层实发 **64** 个，**50 个不在里面**。带那 50 个之一的信封**过不了 Themis 自己的 schema**，而 6 个公开 verify 入口全部先 `validate_result`——**那些拒答根本无法被审计**（`outcome_error` 那一档已记下这个洞并写明「系统性修法另开一档」，这就是那一档）。

**根因**——物种是 `EstimatorFailure(...)` 第一个位置参数上的**自由字符串**，写在 18 个估计器模块的每个 raise 处；schema 的 enum 是同一事实**手抄的第二份**。没有任何一处让两者对齐：新增一个物种不需要碰 enum，不碰也没人报。表象修法是「把 50 个补进 enum」，但补完之后第 65 个物种照样以自由字符串出生、enum 会再次掉队，**而且下一次它看起来更像是维护过的**——slice 6 的教训原样重演。真正没定过的是**权威在哪**。

**修法**——`themis/refusals.py` 把 64 个物种各声明一次，每条带 `kind`（graph／data／unbuilt／request／backend：图不允许／这批数据支撑不住／还没建／请求要改／后端放弃），因为「没有数」不是一个答案而是五个，是哪个决定读者下一步该做什么。`EstimatorFailure` 从 `dose_response.py` 一并搬过来——**18 个估计器模块加 20 个测试文件伸手进某一个估计器的模块去拿通用拒答类型**，这本身就是「这个概念没有家」，而它的 docstring 还停在只有 dose-response 用它的年代（列三个值）。三道闸：构造异常时拒未登记物种（**最早的时刻**，raise 点直接进 traceback）；两个单一出口拒未登记物种（dispatch 有约 30 处手写 dict，那里没有构造函数）；schema 的 enum 由登记表**钉死**而非并排维护。读仍不对称——`verify()` 接受别人信封里它不认识的物种，与块登记同理。

**过程中实测查出三件，都不在根因假设里**：①`bounds_numeric.py` 用 `f"{role}_not_binary"` **拼**物种名，于是 `instrument_not_binary` 存在过但**任何字面量扫描都看不见**、没有测试、没进 schema、没进任何清单——一条 AST 测试现在禁止 `EstimatorFailure` 第一参数是字面量或 f-string，理由写在测试里。②**dispatch 两处在洗掉物种**：longitudinal 把两个名字以外的一切改写成 `unknown`，missing-recovery 把 `insufficient_support` 改写成 `overlap_insufficient`、其余改写成 `unknown`——**估计器在 raise 处已经说对了，dispatch 为了迁就那张不对的清单把它降级**，这正是那张 enum 当初看起来够用的原因；改为原样透传（既有测试断言的是 `exc.failure_type`，无一条钉住被洗后的值）。③一处物种**用错了**：`options.longitudinal.estimator` 收到非法值时发 `unknown`（「我们不知道为什么」），而那是最清楚的一类调用方输入错误，改 `invalid_input`；另 `estimator_failure` 与 `unknown` 是同一件事的两种拼法（前者是 6 处 getattr 兜底），合并成一个。

**取舍（声明）**：~~`kind` 只进登记表**不进信封**~~ —— **已兑现，见下一条**（当时的判断成立：那确是新增字段、属于功能不属于修复）。另：`CORE_STATUS` 早前登记的「9 处宽 `except (EstimatorFailure, ValueError, NotImplementedError)` 把『诚实拒绝』与『代码炸了』压进同一分支」**因这一档而变得可做**——诚实拒绝现在必然携带登记过的物种，`ValueError` 不会。

**基线**：3731 → **3804**（+73：登记表元测试，其中 64 条是「每个登记的物种都真有人引用」的逐条参数化）。

---

**拒答说出读者该做什么（2026-08-03，接上一条）**：功能型 + 修复型。上一条把 64 个物种各命名一次、各带 `kind`，但 `kind` **只活在登记表里**。信封之外的消费者——渲染层的 LLM、web 前端——拿到的仍旧是 64 个 snake_case 标识符之一，加一句自由文本 `reason`。

**根因**——「读到这个拒答该怎么办」是**物种的属性**，而它在信封里没有表示，于是这条知识只能在消费者一侧**逐处重新推导**。实测：`response_rendering.md` 两千行里**没有任何一节讲拒答**，指导散在 6 个方法各自的段落里、各自重写一遍「report the refusal, don't ship the biased number」，累计只覆盖到约 **10 个物种**；其余 54 个（`rank_condition_violated`、`singular_confusion_matrix`、`unit_underobserved`…）**一个字的指导都没有**，LLM 只能即兴，而最省力的即兴是「系统暂时无法计算」——把一个诚实的结构性拒答渲染成故障，正是本仓存在的理由的反面。表象修法是「给那 54 个也补上渲染指导」，那是把登记表手抄进 Markdown 的**第三份**，只是抄写的地方从 JSON 换成了散文。

**修法**——`kind` 进信封，且**不在任何 emit 处手写**：它是物种的函数，只能由登记表在唯一出口盖上去。`refusals.check_registered` 改名 `refusals.stamp`（一个会写数据的函数不该叫 check），检查与盖章是同一件事的两面——**查不到的物种盖不了章**，两个保证由一次调用给出。schema 加 `kind`（5 值 enum），**可选不必填**：沿用块登记已定的读写不对称，我们发的必带（端到端测试钉住 `result["estimator_failure"]["kind"]`），别人的信封不强求。`response_rendering.md` 新开 §「When there is no number」，**按 5 个 kind 写原则，不按 64 个物种枚举**；各方法段落里纯属复述通则的话删掉，只留物种特有的内容——选择偏倚那段反而更实了：`external_data_required` 是 `request`、`not_recoverable` 是 `graph`，读者能做的事完全相反，而这正是 `kind` 的用处。

**过程中实测查出一件更重的，不在根因假设里**：确定性报告 `analysis_report._render_answer` 有 5 个分支（数值／符号／结构布尔／界／可识别但没数据），**没有拒答那一支**——于是一个带 `formula` 又带 `estimator_failure` 的结果掉进第 5 支，报告告诉读者「效应**可识别**…但当前**没有数据** → 需要数据才能给出具体数值」。**给了数据、估计器看过数据后拒绝相信它，报告说的是反话**（实测复现，见 `tests/test_analysis_report.py::test_a_refusal_is_an_answer_not_a_missing_one`）。同一个根因的另一个消费者，而且它比 prompt 那边更糟：prompt 是没指导所以即兴，这里是**默认掉到一句确定的假话**。修法=在第 5 支之前插一支按 `kind` 渲染；**放在数值/结构/界之后而不是之前**，因为 dispatch 会把 longitudinal 的拒答挂到第一个 effect 结果上，而那个结果可能本来就有一个真点估计，那里点仍是答案。`_KIND_ZH` 五句话住在渲染层（登记表管分类、渲染层管措辞，同 `assumption_glossary`），一条测试钉住它的键等于 `refusals.KINDS`——少一句就又是默默掉回通用行。

**过程中改对一处判断**：`KIND_BACKEND` 原文写「Nothing about the question is wrong」，但 `unknown`——唯一承认自己没被分类的物种——也归在 backend 下，对它说「你的问题没问题」是**没有依据的断言**。改为「没有对问题、图或数据做出任何判定」，并在 prompt 那一行点明 backend 不得**编造 block 里没有的诊断**。分类本身不动：五个 kind 分的是**读者该做什么**，而 `unknown` 与后端放弃对读者是同一件事。

**取舍（声明）**：`says`（登记表里每个物种的一句话释义）**不进信封**——`reason` 已经承担「这一次发生了什么」且是在 raise 处写的、更具体；`says` 是物种级的，发出去与 `reason` 重复，它留给登记表维护者和写 prompt 的人。web 前端**未动**：`Verdict.tsx` 现在把 `failure_type` 这个英文标识符直接显示给中文用户，`types.ts` 只镜像它渲染的字段——改渲染是 UI 决策、且要 `pnpm build`，登记为机会，不当作本档欠账。

**基线（本条）**：3804 → **3815**（+11：登记表侧 3——kind enum 与登记表相等、盖章是 kind 的唯一来源、AST 禁止在拒答处手写 kind；报告侧 8——拒答不再渲染成「没有数据」、每个 kind 都有一句话、5 个 kind 逐条读起来确实不同、点估计压过挂在旁边的拒答）。

---

**诚实拒绝与代码炸了不再共用一个分支（2026-08-03，接上两条）**：修复型。dispatch 有 9 处 `except (EstimatorFailure, ValueError, NotImplementedError)`——一次诚实拒绝和一个 bug 落进同一分支，后果完全相同：数值块不出现、结构答案照发、一个字的消息都没有。写成这样不是疏忽：**在 `EstimatorFailure` 有登记表之前，「这是不是一次诚实拒绝」没有可靠的载体**，兜住整个异常类型是当时唯一稳妥的做法。前两条把载体建起来（诚实拒绝现在必然是 `EstimatorFailure` 且必然带一个登记过的物种），这一条才做得成。

**判据是量出来的，不是读出来的。** 光读代码只能说「8 个被调模块自己一处都不 `raise ValueError` / `NotImplementedError` / `KeyError`」，但库会抛，读不全。所以插桩：9 处各记一行「接住的是什么类型、来自哪一帧」，跑一轮全量（3815 passed，插桩不影响结果），然后把插桩删掉。**127 次捕获，127 次都是 `EstimatorFailure`**，另外三种 0 次。来源：`general_id` 90、`bounds_numeric` 15、`four_way_ratio` 14、其余 8。唯一没有运行时证据的是 site 2301（causation，套件里从未触发），只有静态证据（`causation.py` 不 raise 这三种，它调的 `binary_do_risk` 抛 `EstimatorFailure`）——一并收窄，并把「这一处只有静态证据」记在这里。

**过程中推翻自己一个推断。** 看到 `DataContractError(ValueError)` 就推断「数据契约违规也被这 9 处静默吞掉」。**实测不成立**——dispatch 在进这些 try 之前已经建过一次 contract，5 行数据在 back-door 与 general-ID 两条路径上**都**如实抛出（`themis/__init__.py:97` 记的正是这个公开契约）。反过来，这成了收窄的一个正面理由：**这 9 处让 `estimate` 悄悄违反它自己文档化的行为**。

**声明的行为改变与风险。** 收窄之后，一个没被分类的库异常会**炸出去**而不是被吞掉。这是想要的——不许静默是本仓的全部主张；但它是真风险：某条测试没覆盖到的路径上若真有未转换的库异常，用户会拿到 traceback 而不是一个结构答案。取舍明说：**安静地少一个数是最坏的选项**，因为它长得和一次诚实拒绝一模一样，没有任何人会去查它。

**未做、已登记（划在这一档之外）。** 这 9 处即便接住的是诚实拒绝，也**不在信封上留痕**：`blocked('estimator_refused')` 记的是 dispatch 级联自己的账（`Claim.reason` → `Evaluation.declined` → 一个 `_recorder`），不进结果。用户看到的是「这题没有数」，而不是「这题因为 X 没有数」。修它要往信封加 `estimator_failure` 块，属功能不属修复。另：`counterfactual_cell.py:414` 那处 `(EstimatorFailure, cf.CounterfactualBoundsError)` **不在问题范围**——两个都是诚实拒绝通道，AST 守卫按「不许与**通用**异常同筐」写，正好放它过去。

**基线（本条）**：3815 → **3816**（+1：AST 守着「拒答不与通用异常同筐」——这比单纯删掉那两项更耐久，因为下一个人会想把它们加回来）。~~未做、已登记~~ **已兑现，见下一条。**

**拒答终于留在信封上，报告不再拿「可识别」冒充答案（2026-08-03，接上条）**：修复型。上一条把「这 9 处不在信封留痕」登记为待办。实测下来**比登记的更糟，而且是两处病灶不是一处**。

**现象（跑出来的，不是读出来的）**：proximal 查询，数据 (Z,X) 有空层。估计器如实拒答，物种和一句解释都齐全。用户拿到的是 `numeric_estimate: None`、`estimator_failure: None`、`data_gap_report: {"summary":"","gaps":[]}`，报告正文一行「结论：**是**」。全信封搜不到任何拒答痕迹。这不是「没数且没说原因」，是**拿结构层的「可识别=是」冒充了答案**。

**根因**：这 5 个 handler 的契约句是同一句 —— *"returns False and touches nothing, so the structural answer stays primary"*。它把**答案**（不该被覆盖，对的）和**诊断**（该被记下）塞进了一个词，`touches nothing` 保护答案的方式是连解释一起噤声。dispatch 里另外 32 处写 `estimator_failure` 的地方证明系统本来就知道正确行为——这 5 处是异类，不是惯例。

**修法**：拒答块的形状由 `themis/refusals.py::record` 说一次（该模块已拥有 `stamp`，本就是「拒答在信封上长什么样」的归属地；`record` 只写块，「查询是否到此为止」仍是 handler 的决定，留在 handler）。5 处沉默的终局站点调用它（**缺陷本身**）；11 处已在手写同一块的 `except ... as exc` 站点改为走它（纯重构）。顺带闭掉两个同源静默：`getattr(exc, "failure_type", refusals.UNKNOWN)` 共 6 处——`EstimatorFailure.__init__` 现在总是设已校验的 `failure_type`，这个兜底**永不触发**，是登记表之前的化石；`exc.details` 全仓只有 **1 处**写进信封，而 schema 声明了它、docstring 承诺了它，126 处 raise 里 **36 处**带着真诊断（`sparse_bins` / `bin_counts` / `outcome_std` / `bandwidth` / `t_range`），除 dose_response 自己那处外全部丢弃。

**消费端顺序是量出来的，不是推出来的。** 写完块之后报告**照样**输出「结论：是」——`_render_answer` 的结构布尔分支排在拒答分支前面（㉓：根因修在产生端，假话在消费端说出口）。顺序不靠推理定：在两个单一出口插桩，跑一轮全量，记下 **2025 条信封**各自哪些分支能触发，再把插桩删掉。结果——拒答 + 结构布尔：**2** 条，全是 `effect`；拒答 + 界：**16** 条，全是 `effect`（界在那里是真答案，拒答绝不能赢）；结构布尔 + 界且无数：**4** 条，全是 `effect`。`cause` / `association` / `identify` **一条都没被波及**。故新顺序 = 点 / PN-PS-PNS / theta 数 / 界 / 拒答 / 结构布尔，并写成原则而非字段强弱排名：**先给查询所要的答案，再给「为什么没有答案」，最后才是关于图本身的结论**——答案本就是布尔的那些查询，上面的分支从不触发，所以布尔下沉不需要任何 query_kind 判断。`response_rendering.md` 同步：`details` 补进字段表，并加一条「拒答优先于关于图的结论」。

**守卫按原则写，不按「我改过的名字」写**（㉔）：`except EstimatorFailure` 且 `blocked(...)`（查询到此为止）的分支必须 `record`；`passed(...)` 的分支豁免——那里查询仍在飞，此刻写块会和后来的答案并列在信封上。

**未做、已登记（明确划在这一档之外）**：

- **5 处估计器根本没接进拒答通道**：frontdoor / IV / 两条 mediation / joint 的 `except (ValueError, NotImplementedError): return blocked(...)`，同样终结查询却不说原因。但根因在更深一层——注释自己写着「连续中介，超出 v1」「Wald 分母为零」，**这些本就是如实拒答，只是估计器用裸异常表达**。就地记成 species `unknown` 等于把崩溃洗成拒答，而 `unknown` 的定义正是「唯一一个自己都不知道在说什么的物种」。正解是给那几个估计器发物种。
- **33 处拒答文案把数据值直接插进给人看的句子**，其中约 10–15 处是裸 numpy 标量，实测渲染出 `empty stratum (Z=np.False_, X=True)`。它因这次改动**刚变成承重的**（`reason` 现在进用户主答案行），但根因另在一条（给人看的值应当被格式化而非被 repr），修法是一个格式化出口 + 约 15 处站点 + 守卫。
- web `Verdict.tsx` 仍直给英文 `failure_type`，且没接 `kind` / `details`（那里是加法式渲染，不受这次排序影响）。
- `EstimatorDependencyMissing` 那处**不在问题范围**：它记录到另一个块 `estimator_dependency_missing`，不是静默——普查按 key 找曾误判它，读了才发现。

**基线（本条）**：3816 → **3822**（+6：2 个原则守卫「终结查询必说明原因」「拒答带上它量到的数」+ 1 个端到端回归（那条 proximal 查询）+ 3 个消费端排序钉死，含「答案本就是布尔时布尔仍然赢」的反向一条）。~~未做第一项~~ **已兑现，见下一条。**

**四个估计器接进拒答通道，裸异常不再冒充拒答（2026-08-03，接上条）**：功能型，兑现上条划出的第一项。frontdoor / mediation（两条）/ joint 用裸 `ValueError` / `NotImplementedError` 表达如实拒答，dispatch 的 handler 用 `except (ValueError, NotImplementedError)` 一把兜住，终结查询却不说原因。根因在估计器一侧：它们的注释自己写着「连续中介，超出 v1」「至少要两个处理」——**这些本就是拒答，只是没有物种可说**。所以修法不是在 handler 里记成 `unknown`（那等于把崩溃洗成拒答，而 `unknown` 的定义正是「唯一一个自己都不知道在说什么的物种」），而是**给估计器发物种**。

**先量再改（㉔），而量出来的东西比改动本身重要。** 给这 5 个入口插桩跑全量：**3822 个测试一共只接住 3 次**。5 个站点里有 2 个（dispatch 2940 / 3217）**零命中**——它们的转换是防御性的、无运行时证据，这一点单独记，不混进「实测」。

**其中一次接住的是 numpy 的 `LinAlgError`——上一档我证明不了的那件事，这次被抓住了。** ㉔ 说「读代码只能证明『我们自己不抛』，证明不了『不会到达』——库会抛」。这里它真的到达了：`LinAlgError` 是 `ValueError` 的**子类**，mediation 的**点估计**拟合在秩亏设计上让 statsmodels 抛出它，正落进通用兜底被吞掉。而 bootstrap 循环本来就守着退化抽样（跳过该次抽样、用其余的建区间），**点估计那一次没人守**——它的失败就是整个估计的失败，必须说出来。故 `_fit_or_refuse` 只包点估计，不碰 bootstrap 的容错。

**新增 3 个物种**（净）：`continuous_mediator` / `mediator_strata_intractable` / `too_many_joint_treatments`；`singular_design` / `not_a_joint_intervention` / `invalid_input` 复用已有登记。schema enum 同步（测试钉死 enum ≡ 登记表）。4 个 dispatch handler 收窄为 `except EstimatorFailure` + `record`，joint_backdoor 之后那条通用兜底直接删掉。

**登记表守卫抓到了我自己。** 我顺手登记了 `no_first_stage` 准备给 iv.py 用，然后又明确推迟了 iv.py——全量跑出 `Refusal('no_first_stage') is registered but no module names refusals.NO_FIRST_STAGE`。守卫的原话是「一条谁都不引用的登记，是一个除了这里之外已被删干净的拒答」。**推迟一件事，要连它的登记一起推迟**：物种随 iv.py 一起回来。

**8 个既有测试断言的是旧的裸异常类型**（其中两个名字里就写着 `raises_not_implemented` / `raises_value_error`，已改名）。这是有意的行为改变，且方向是**回到已文档化的契约**——`themis/__init__.py` 早就写明 `estimate` 抛 `EstimatorFailure`，裸内置异常才是偏离。另把 `test_dispatch_skips_frontdoor_when_continuous_mediator` 重写为 `test_a_continuous_mediator_is_refused_out_loud`：它原本只断言「没有 numeric_estimate」、注释写着「优雅地跳过」——**那正是从允许它的测试内部看过去，一次静默拒答的样子**。

**未做、已登记（明确划在这一档之外）**：

- **iv.py 仍未接入**：它的 Wald 路径耦合着一个 bootstrap 容错循环，内层靠 `except ValueError` 跳过退化抽样，而退化抽样正是 `_wald_point` 抛 `ValueError` 造成的。正确终态要求把「每次抽样的失败通道」一并转成物种——那会动到**用户看得见的置信区间**，值得单独一轮带测量地做。over-ID 路径经核实**不属于这类缺陷**（它返回 `passed` 让路给恰好识别那一行，此刻写块会和后来的答案并列在信封上）。dispatch 站点 1224 随它留着，**不加临时白名单**：AST 守卫会自紧——每转一个估计器，就有一个通用 handler 变成 `except EstimatorFailure`，守卫随即覆盖它。
- **joint 的 `singular_design` 无运行时证据**：K=2 / K=3 的完全共线处理向量、重复调整列、bool / 连续结局都试过，构造不出触发样本。**顺带撞见一件该单独查的事**：`b == a` 的完全共线联合设计**返回了一个数**且无任何提示，那个数对不对没查。

**基线（本条）**：3822 → **3828**（+3 登记表守卫的参数化，净增 3 个物种；+3 行为测试：mediation 秩亏点估计的单元一条 + 端到端一条（信封确实带上了原因）、frontdoor 层交叉积上限一条——层数各自合规、交叉积不合规，与「连续中介」是两个物种）。

**联合交互不再在空角点上编数（2026-08-03，接上条）**：修复型，**上一条「顺带撞见、那数对不对没查」的那件事查了，是真的错数**。

**现象（跑出来的）**：两个处理 A、B 在数据里从不分开出现——(1,0) 和 (0,1) 两个角点**零观测**。`estimate_joint_effect` 照样报出 `interaction = 0.9999`，带置信区间，无任何提示。真值是**不可识别**。联合对比 2.9996（真值 3.0）是对的——它只用到有数据的两个角点。

**根因：正性被声明在「格」上，却被检查在「边际」上。** joint.py 逐个处理检查 `df[t].unique()` 有没有两个水平——那是边际；而假设账本条目自己叫 `positivity_overlap_of_every_treatment_cell`——那是格。K 个边际都非退化，联合的 2^K 个格照样可以有空的。空格上 `predict(sample, cell)` **仍然返回一个数**（sklearn `LinearRegression` 走 lstsq/pinv，秩亏时给最小范数解，**从不抛异常**），所以缺数据不表现为错误，只表现为一个编出来的数。**这也顺带解释了上一条「joint 的 `singular_design` 构造不出触发样本」**——不是我构造得不好，是那条路径对线性/逻辑两个后端基本不可达，我上一轮瞄错了靶子。

**为什么是根因不是表象**：①完全共线只是让格为空的一种方式，任何「两种处理从不联用」的真实数据都走同一条路；②秩亏是症状，修在秩上还会**误伤联合对比**——对比只需要它自己那两个格，那两个有数据时它是对的；③账本早就用正确的粒度写下了这条假设，缺的不是「想到要检查」，是检查的粒度掉了一档。

**修法：两个量需要的角点不同，所以判据分开。** 对比只需要 all-hi / all-lo 两个格——缺则整个估计如实拒答（`overlap_insufficient`，**取代**旧的边际检查：一个卡在单一水平的处理必然清空对面那个格，而新消息说的是**哪个格**空了，比说哪一列更准）；K 阶交互需要全部 2^K 个格——只缺这些则**对比照出、交互不出**，并点名缺的格。角点归属**只标一次**（每行打一个角点标签，bootstrap 里切片即可）——这让检查在自助循环里几乎免费，也让**丢了角点的抽样只退出它影响的那一个区间**：对比能活过交互活不过的抽样。

**消费端逐个走过（㉓）**：`interaction` 块**缺席**而不是「在场但装着 null」——读 `interaction.point` 的人不该还要知道这个字段可能是空的；`interaction_unavailable`（reason + 缺的格）站在它原来的位置，镜像既有的 `four_way_unavailable`。推导输入同样二选一，**验证器要求缺席必须自报理由**：否则「角点空了所以没有」和「出门路上被谁弄丢了」在审计眼里长得一模一样。schema 加块、`response_rendering.md` 按原则改写（两个块依赖的数据量不同，所以会分开到达）。

**未做、已登记**：`longitudinal.py` **有同一形状的缺口但不是同一个 bug**——它的账本声明 `positivity_each_treatment_level_observed_within_history_strata`（历史层内的序贯正性），检查的也是边际，粒度同样掉档；但它的结局模型是**参数化**而非饱和的，参数化 g-formula 的价值正在于能识别没人完全照做过的方案，代价是一条**已声明**的函数形式假设。照搬这次的修法会误拒本来合法的估计。正确修法要区分离散历史（可查）与连续历史（不可查），是一个设计决定，单独一轮。

**基线（本条）**：3828 → **3832**（+4：空角点扣住交互而对比仍恢复真值 3.0 的单元一条、对比自己的格空了整体拒答一条、端到端信封一条、验证器拒绝「无理由消失的交互」一条）。

**假设账本当索引，把全部估计器扫了一遍（2026-08-03，接上条）**：上一条的根因（正性**声明在格、检查在边际**）不是 joint 独有的形状，所以把它当尺子——**每条声明的假设 vs 真正执行的检查，并排读一遍**——扫过全部估计器。

**扫的结果分四类，这个分类本身是这一档最有用的产出**：

1. **检查掉档、且模型在缺口处无根据地给数 → 缺陷。** joint（上一条已修）：饱和基下空角点的均值字面上是任意的。
2. **检查掉档、但模型在缺口处的外推是一条已声明的假设 → 不是缺陷。** `longitudinal.py`（参数化 g-formula，声明 `..._within_history_strata` 查边际）、`dose_response.py`（DR-ML，声明 `..._has_support_on_W` 查剂量邻域而非 W 层）。照搬 joint 的修法会**误拒本来合法的估计**。判据是：**这个估计器在缺数据的地方靠什么给出数，那个东西有没有被声明过。**
3. **检查到位 → 干净。** `causation`/`counterfactual_cell`（`binary_do_risk` 逐层逐臂）、`general_id`/`ctf_conjunction`（`_prob_do` 逐条件层）、`proximal`/`selection`/`measurement`/`missing_recovery`、`backdoor`/`aipw`/`tmle`（单处理，边际即格）、`iv`（每层每臂 ≥ `_MIN_PER_ARM`，**比声明更严**，且不可分层时回退 2SLS 并带上理由——「没人看得见的回退才是失效模式」，代码自己这么写的）。**普查按物种名计数曾把 `causation` 误判成「一个拒答都不抛」，读了才发现它的 raise 在共享 helper 里**（㉕③ 又验证一次）。
4. **检查对了、但物种在下游用散文猜 → 缺陷（本条修的）。** `transport.py`。

**transport 的现象**：源数据某 z 层只有处理臂没有对照臂。估计器如实拒答，用户拿到的 `failure_type` 是 `invalid_input`——「你的请求有问题」，而请求完全正确，真相是数据在那一层没有重叠（`overlap_insufficient`，kind=data）。

**根因**：物种是产生端的知识，这里被丢进一句散文，由 handler 用 `"no observations" in msg` 在下游猜回来；两个正性守卫只有一个的文案命中，另一个落进默认的 `INVALID_INPUT`。**这与上一档同根、是另一面**：上一档是「估计器没有物种可说」，这一档是「估计器有知识但没渠道」。为什么不是补一条子串分支：任何在消费端重建产生端知识的机制都必然滞后于产生端的改动——**证据就在现场，猜对的那一支有测试、猜错的那一支没有**。

**修法**：transport 的 9 处 raise 各自带物种（2 处正性 → `overlap_insufficient` + details 说清哪一层、几个处理几个对照；7 处请求格式 → `invalid_input`），handler 收窄为 `except EstimatorFailure` + `refusals.record`，子串匹配删除。bootstrap 容错循环同步改容 `EstimatorFailure`（策略不变：丢了层的抽样退出区间）。**全仓只此一处在用散文猜物种**（grep 过 `in msg` / `in str(exc)`），所以这是收口不是开头。

**登记表守卫第二次抓到人**：删掉那条永不触发的 `NOT_IMPLEMENTED` 分支后，`not_implemented` 在全仓再无引用。删掉它不只是守规矩——它是「未建」那一类的 `unknown`，内容就是「超出这条路径实现的范围」，读者拿它没法做任何事；而登记表里已有的未建物种各自说清了没建的是什么。iv.py 转换时应当说具体没建什么，不该伸手拿这个通用的。

**基线（本条）**：3832 → **3833**（+2 行为测试：缺一臂的层是数据发现而非坏请求、格式确实坏时物种不能漂成数据发现——两侧一起钉才使这个区分承重；−1 删掉的孤儿物种参数化）。

**最后一个估计器接进拒答通道，用户不再收到一条办不到的建议（2026-08-03，接上条）**：修复型，用户可见。iv.py 是唯一还把拒答理由留在异常字符串里的估计器。

**现象（实测，不是推演）**：构造 E[X|Z=1] = E[X|Z=0] = 0.5 的数据跑 `themis.estimate`，估计器准确说出了原因——「instrument has no measurable first-stage effect on treatment」——而 `estimator_failure` 是 `null`，用户读到的唯一一句可执行的话是识别层的「声明 `assumptions.monotonicity` 就能拿到 Wald LATE」。**照做拿不到任何数**：单调性给不了一个死掉的第一阶段。同一张 AST 换成健康工具变量，`missing_information` 是空的——那两条只在估计器拒答时才浮出来，而它们讨论的是「一个工具变量不足以挑估计器」，不是「这个工具变量是死的」。

**根因**：字符串跨不过 dispatch 边界。`except (ValueError, NotImplementedError): return blocked(...)` 接住的是**类型**不是**句子**，裸 `ValueError` 到那里只剩「出了点事」。**为什么不在 handler 里补一个字典**：那要求消费端重建产生端已经知道的物种，正是上一条 transport 修掉的形状。

**修法**：14 处拒答点各自声明物种 + details；dispatch 两个站点收窄为 `except EstimatorFailure`。新登记三个物种——`no_first_stage`（data，工具变量在这批数据里不推动处理，比值的分母是 0）、`no_usable_resample`（data，每一次重抽样都退化，区间没有可取分位数的样本）、`conditioning_too_fine`（unbuilt，W 比我们愿意枚举的切法更细）。

**上一档登记这件事时说「会动 CI」，读完不成立、已更正**：bootstrap 那个 `except ValueError` 接住的恰好是 `_wald_point` / `_stratified_wald_table` / `_NotStratifiable` 三者，一起转换后集合不变；`_two_sls_point` 走 sklearn lstsq **根本不抛**（上一档在 joint 上查实的同一件事）。**收窄仍然实测**（㉔）：把旧的 `except ValueError` 作为额外分支挂在新分支之后、跑全量套件记录任何落进去的东西——**两个 bootstrap 一共 0 条**。读代码只能证明「我们不抛」，这条才证明「不会到达」。

**登记表守卫第三次抓到人，而且这次逼出了更好的设计**：`test_an_honest_refusal_is_not_caught_beside_a_crash` 报 `except (np.linalg.LinAlgError, EstimatorFailure)` 两处违规——`LinAlgError` 是通用失败，不许和拒答同筐。**正确答案不是加白名单**（上一档预先拒绝过），是让 numpy 的异常根本不跨边界：`solve_overid_from_moments` 与 `solve_hansen_from_s` 在 `np.linalg.inv` 处就发 `singular_design`，于是两个 handler 都变成只接 `EstimatorFailure`，`estimate_iv_overid` 里那层「把 LinAlgError 包成 ValueError」的转译整个删掉。**守卫自紧的兑现**：上一档说「站点 1224 留着不加白名单——AST 守卫自紧」，这一档它自己紧上来了。

**两处 `ValueError` 是故意留的**（`_robust_weight_matrix` / `_robust_moment_matrices` 的「cluster 标签与残差化行数不齐」）：它报的是**我们的**不变量破了，不是用户数据的限度。把它降级成「没有 Hansen」等于把 bug 洗成诊断，所以 `_hansen_robust_j` 现在只接 `EstimatorFailure`，这条真触发时会响。

**过度识别路径不写块，这是判断不是遗漏**：它的 handler 返回 `passed`——查询仍在飞，恰好识别的路径会答它。`blocked` 必须记原因，`passed` 必须不记，否则信封上会出现一个「没有给出数值」的块，紧挨着后面真的给出的那个数。配了测试钉住。

**覆盖三档，不合并（㉖）**：全量套件跑 line coverage 落到 iv.py 的 24 个拒答点上。**实测触发 10 处**（wald 要二值 / wald 不吃 W / Wald 分母 0 / W 连续 / 层内缺一臂 / 聚合第一阶段 0 / Z'Z 奇异 / 少于两个工具，加本条新建的两处）。**明显可构造、本轮没建 8 处**（显式 stratified_wald 遇非二值、未知 model 名、**非浮点列超基数上限**——现有那条测试用整数列，而数据契约把整数拓宽成浮点，走的是 float 那一支、517 从没走过、层数乘积超 64、W 有放不进任何格的值、over-ID 联合第一阶段退化、over-ID bootstrap 两支）。**论证构造不出 1 处**（「W 的格一个都没被填充」——只要有行就至少有一格被填）。**没试也没论证清楚 3 处**（Ŝ 奇异 / 高效 GMM 第一阶段退化 / û'û ≤ 0）。**两条 `ValueError` 绊线不该触发，实测也没有。**

**方法论新增（㉙）：插桩记「有没有坏东西落进来」必须配一次可达性测量，否则空结果的意思是「什么都没落进来」。** 本轮两个 bootstrap 的收窄先用旧 `except ValueError` 挂在新分支之后跑全量、记录 0 条，我当时说「实测过、不是假设」——**coverage 随后显示那个 handler 全套件一次都没执行**，所以那 0 条是**没有流量**而不是**没有泄漏**，什么都没证明。这是 ㉔ 自己的陷阱深一层：㉔ 说「读代码只能证明我们不抛」，㉙ 说「插桩得零也可能只证明没人来」。补法不是再跑一次插桩，是**建出到达那条分支的构造**（10 个恰好卡在每臂下限的层，全样本过得去、重抽样几乎必失手：73/200 落进降级分支，200/200 落进「没有可用重抽样」），并把「落进来的是不是拒答」写成**常驻断言**而不是一次性的 tally。

**未修、已登记（本条查实的第二个缺陷）**：识别层那条「An instrumental-variable escalation does reach it, but it is assumption-laden and **could not be run as it stands**」在 IV 因数据拒答时**是假的**——IV 路径跑了。它的压制条件是「有没有答上」，不是「IV 路径用没用上」。修它要决定识别层条目与估计层结局如何一般性地对账，不能只为 IV 打补丁，单独一轮。现在它不再是唯一那句话（拒答块排在报告的答案段），但它还在。

**基线（本条）**：3833 → **3840**（+2 dispatch/信封行为：死工具变量说出物种与 kind、过度识别回退**不**留拒答块；+2 bootstrap 分支的构造：降级抽样被丢弃且落进来的确是拒答、全部退化时区间被拒答；+3 新物种的登记表参数化）。

**数据到了就算数：识别期的参数请求不再在数据到达后继续要（2026-08-04，接上条）**：修复型，用户可见，跨全部估计器。上一条登记了识别层那句「could not be run as it stands」是假的；查它的时候量出一个更大的、同根的：**识别期写下的「θ 里缺这个条目」，在用户改用数据通道之后，四个面上一条都没撤。**

**现象，四格全部实测**：

| 场景 | 信封上留下的话 | 事实 |
|---|---|---|
| IV 第一阶段恒为零、已声明单调性 → 估计器拒答 | `missing_information` 4 条「Theta 中缺条目 P(x=True\|z=True)」 | 那个数就印在旁边拒答块的 `details` 里（`e_treatment_high: 0.5`） |
| 同上 | `data_gap_report` 4 条 `missing_distribution / blocking`，`required_data.min_sample_size: 400` | 手上就是 400 行 |
| **IV 第一阶段健康 → 成功给出点估计** | 同样 4 条 blocking，外加「答案是符号区间不是点估计」 | 点估计已经在同一个信封里 |
| **普通 backdoor 成功给出点估计** | gaps 已清干净，**`actionable_next_steps` 仍以「补 P(y=True\|w=True,x=True)」开头** | 同上；而 `response_rendering.md` 要求这一串**逐字**渲染给用户 |

第四行不是本条改动带来的，是**已有对账自己漏掉的一面**，量出来的——最常走的那条路径上。

**根因**：「数据回答了哪些请求」和「答案是什么等级」被写成一个函数、一个早退、一个调用点。`_reconcile_gap_report_after_numeric_solve` 里 `unidentifiable_no_admissible_set` 早退对**等级**是对的（IV LATE 确实不是无假设点识别，界的措辞该留着），却把参数满足一起吞了；它只挂在成功路径上也是对等级说的，却把参数满足一起挡在拒答路径外。**参数满足只依赖一个前提：数据契约通过**——契约要求每个已声明变量都有一列，`validate_data` 一返回，那些请求就由数据回答了，与后面算没算出数、算出的是点还是区间无关。

**更深一层，也是修法落点**：`_missing_parameter_from_key` 是这类请求的**唯一**生产端，手里握着 `ProbabilityKey`（要哪些变量、在哪个总体），却把它压成字符串 `parameter:P(y=True|z=True)`。消费端要回答「到手的样本回答了它没有」，就只能把这串解析回去。`MissingItem` 的 docstring 早就为 `gap` 写过同一句判词——「producer knew the species, pressed it into a string, and the report recovered it with prefix and substring tests」——**这是同一个病低一层**。

**修法三处，各说一件事**：

1. **`MissingItem.observable`**（`Observable(variables, population)`）——生产端说出「观测什么能了结它」。`population=None` 是在研总体（一份 DataFrame 就是它的样本）；具名总体是另一个样本，这批数据再全也不顶。
2. **`_settle_asks_the_sample_answers`**——契约通过后**立刻**执行一次，早于任何估计器，逐条比对 `observable` 与已认证列集，同步四个面（`missing_information` / `investigation_requests` / `data_gap_report.gaps` / 两条派生摘要）。`_reconcile_gap_report_after_numeric_solve` 一个字没改：它保留的是另一半，等级那一半确实依赖结果。
3. **`data_gap_from_dict` + `rederive_summary_and_steps`**——摘要与「下一步」是 gaps 的函数，**删了 gaps 就得重新求一遍**。dispatch 里那份 `_summary_from_gap_dicts` 副本（docstring 自己写着「Mirror `output.data_gap_report._make_summary`」）删除，两处旧对账改走同一条路——**这一步同时修好了上表第四行**。反序列化器照 `derivation_from_dict` 的先例做，配双向 round-trip 测试 + 一条「凡内核真发出的 gap 都过一遍」的测试（漏字段不会抛，只会静默变默认值）。

**为什么不是在拒答分支再抄一遍过滤**：那只补一条路径，成功路径上那 4 条 blocking 会继续留着；而且每加一个后置补丁，就多一次「忘掉一个派生面」的机会——上表第四行就是这么来的。**一个从 gaps 派生的面，不会因为 gaps 被对账而变对；它只会因为被重新求一遍而变对。**

**顺带修掉的第二句假话（即上一条登记的那个）**：「An IV escalation does reach it, but it is assumption-laden and **could not be run as it stands — see the items alongside this one**」。两处错：（a）IV 跑了，是数据把它杀的；（b）θ 请求被对账掉之后，「旁边那批 item」是**空的**。而且它的门是 `if notes`——**所有路线**注记之和，跟有没有工具变量无关。改法：这句话只说它能一直担保的那半句（这张图上有工具变量、它带假设），门换成它真正断言的那个事实 `facts.iv_candidates`。易腐的那半句本来就有人在说：注记在时注记说，数据把它杀掉时 `estimator_failure` 说（`no_first_stage`，`details.instrument`）。**一条 item 的 reason 里放一份旁边那批 item 的散文摘要 = 第二份副本，副本会过期。**

**三档覆盖，实测（㉖）**：全量套件插桩量新对账的到达情况。**535 条结果到达**（454 条带 `missing_information`），**2139 条 item 过手**，其中 `missing_distribution` **1955 条、全部带 `observable`**（生产端覆盖整条通道，没有静默产生端）；**settle 掉 1942 条、连带丢掉 1942 条 gap**。两条保守分支：**「具名总体」实测到达 13 次**（population = `trial`，transport 的源条件），全部正确保留——配了行为测试，因为那批 ask 要的 x/y/z **恰好都是手上这份样本的列**，只看变量名的规则会把它错误地当成已回答；**「列不全」0 次**，与契约论证一致，是论证的安全网而非活分支。**「请求只丢掉一部分 item」0 次**（712 个请求：359 个被清空、353 个未动）——原则上可达（一条结果要同时提出在研总体和具名总体的请求），所以那条重算摘要的规则用**单元测试钉住**，断言它产出的 target/note/priority 与「一开始就只有剩下这些 item」时 `push` 会产出的完全相同；**不当作已覆盖**。

**仍然登记，没修**：

- 未声明单调性 + 死工具变量时，用户仍会读到「声明 monotonicity 就能拿到 Wald LATE」，照做拿不到数。要一般性地解决，得决定**哪些拒答与假设无关**——`no_first_stage` 是（单调性造不出第一阶段），但这是**逐物种的判断**，和 `kind` 同类，正解是在 `themis/refusals.py` 里再声明一格，不是特判。
- `_declares_missingness` 早退路径不建契约，因此不对账。那条路上的列按设计含 NaN，「一列 NaN 是否供给了那个条件分布」是另一个判断，猜错会丢掉活的请求。
- `dispatch.py` 里 `_collect_required_columns` 与 `_ensure_dict` **各有两份模块级定义**（6501/6524、6517/6555），后者胜出、前者是死代码。AST 查实，与本条无关，未动。

**基线（本条）**：3840 → **3849**（+3 IV dispatch 行为：拒答后不再索要刚读过的数、成功的 IV 点估计不再带自己输入的 blocking 缺口、ADMG 那句话由它断言的事实把门；+2 生产端：参数请求说出总体、无 key 时不编造观测；+2 gap 反序列化：手写 round-trip 与全内核 gap round-trip；+1 请求缩水后的摘要等价于重来一遍；+1 具名总体的请求不被在研样本了结）。

**三条登记全部结清：一条建议、一条早退、两份同名定义（2026-08-04，接上条）**：修复型，用户可见两条。上一条结束时登记了三件事没修；这里逐条查实、逐条修，其中一条**登记时写下的解法被实测推翻**。

---

**一、「声明 monotonicity 就能拿到 Wald LATE」——它在两种结局下都是假的**

现象，四格实测（`themis.estimate`，Z→X→Y + X↔Y）：

| 数据 | 声明 | 结果 | 信封上那句话 |
|---|---|---|---|
| 死工具（E[X\|Z=1]=E[X\|Z=0]=0.5） | 未声明 | `no_first_stage` 拒答 | 「Declare assumptions.monotonicity to get the Wald LATE」 |
| 死工具 | **已声明** | **同一条拒答，没有数** | —— 上一格那句话由此被证伪 |
| 活工具 | 未声明 | **`numerically_solved`，method=`iv_wald`，点值 1.209** | 同一句话仍在 gap 上 |
| 活工具 | 已声明 | 同上，逐字节相同 | —— 声明与否，估计层的输出一模一样 |

全量插桩（538 条结果经过估计层出口，483 条有数、39 条拒答）：这条 ask 留在 `missing_information` 上 **2 次**（全是 `no_first_stage / data / iv_wald`，即登记的那格）；但**留在 gap 上、旁边就摆着一个数的有 54 次**——`iv_wald` 42、`iv_2sls_overid` 10、`iv_2sls` 2。**登记时只看到 2 次里的那格，实际主战场在成功路径上。**

**根因**：这条 item 是**识别层给自己定的前置条件**（不声明单调性，我不写这个 estimand），却被写成一句关于**内核**会做什么的许诺。估计层拿到 DataFrame 后**根本不读这个声明**，两种结局都把许诺作废：跑出数（ledger 已把单调性列为 `invalidating`，读者该看的披露在那儿），或者拒答（没有任何声明能给一个不动的第一阶段造出第一阶段）。没有任何一遍拿估计层的结局去对账它。

两条漏法同源，都是「撤一半」：`_finalise_numeric_result` **无条件** `pop("missing_information")`，而它下游的 gap 对账被 `unidentifiable_no_admissible_set` 早退挡在门外——**item 删了、gap 留着**，两张「还缺什么」的表从此各说各的，而读者看到的（summary / next_steps 都从 gap 派生）正是没被对账的那张。这跟上一条修的是同一个门：那次它吞掉了 θ 那一半，这次吞掉的是前置条件那一半。

**登记的解法是错的，实测推翻**：登记写的是「在 `refusals.py` 里逐物种声明『这个拒答与假设无关』」。两处站不住：（a）同一条 ask 的下游估计器实测有三个名字，逐物种对不上；（b）更根本的是，**拒答是什么物种压根不重要**——估计层从不读那个声明，所以它**开了口**这件事本身就足以作废许诺，回的是数还是拒答都一样。

**修法**：`MissingItem.superseded_by_estimation` ——「估计层开口即作废」，由**提出前置条件的那一遍**声明（只有它知道那是前置条件）。`push` 像抄 `gap` 一样把它抄到 `InvestigationItem`，**而这次抄有更硬的理由：那是 pop 之后仍然活着的面**。撤销在 `estimate_program` 唯一出口执行，**排在 ledger 折叠之后**——撤销所依赖的那份披露正是在那一步落到读者主面上的。四个面（item / request / gap / 由 gap 重算的 summary + next_steps）一起动，走的是上一条建好的那三个 helper。

**二、`_declares_missingness` 早退路径——登记的诊断对，开的药方不对**

现象实测（4 条结果、3 条出了数）：**16 条 θ item、16 条 θ gap、16 句「补 P(…)」**，其中一条恢复出来的 ATE 旁边就摆着 4 个 blocking 缺口，要的正是它刚估出来的那几个条件分布；4/4 条 `estimation_context` 为 null。

登记写的是「不建契约故不对账」。**契约不是该用的凭据**：2B 格（z 自遮蔽 → `not_recoverable`）里 z 这一列**在**，但 `P(z)` 恰恰不可恢复——那就是拒答本身；按「列在不在」结算会撤掉拒答赖以成立的那批请求。这条路上唯一站得住的凭据是「**数出来了**」，而这条路从不调用那次对账。

**修法**：把「数回答了哪些请求」从「结果的地位变成什么」里拆出来（`_withdraw_asks_the_number_answers`）。两者依赖不同：有数就答掉了请求；而敢不敢声称 `numerically_solved` 是另一回事——**这条路不写 derivation，`verify` 拒绝审计没有 derivation 的结果**，声称了就是超出信封能背书的范围。所以它撤请求、不动 status。焊在一起时，这条路上撤销这一半干脆整个缺席。

**三、`dispatch.py` 里两份同名模块级定义**

`_collect_required_columns`（6501/6524）与 `_ensure_dict`（6517/6555）。删掉靠前的那两份（后者胜出）。值得一记：死掉的那份 `_collect_required_columns` 是**更旧更窄**的版本——它不知道 proximal latent，先读到它的人会得出「契约要求为一个构造上不可观测的节点提供列」的结论。加一条 AST 守卫：**themis/ 下任何模块不得两次定义同一个顶层名**（`tests/test_no_definition_is_shadowed.py`）。Python 对此从不报错，后一份静默胜出，前一份变成「读起来像在跑」的代码，而两份通常隔着几千行。

**仍然登记，没修**：

- 缺失恢复路径 4/4 条没有 `estimation_context`（无契约，故无 data_hash / sample_size / random_state）。数值块自带 `data_hash`，审计链没断，但这条路与其他所有路不对称。
- 同一条路不写 derivation，因此既不能声称 `numerically_solved`，也过不了 `themis.verify`——`tests/test_verify_missing_data_numeric.py` 的模块 docstring 早就把这件事写出来了，并为此单建了一个审计器。

**基线（本条）**：3849 → **3855**（+3 IV：无数据通道里这条前置条件带着「估计层开口即作废」的标记出现在两个面上、死工具拒答后四个面上都不再有它、交付的 LATE 不再一边给数一边劝你去声明它——同时钉住 ledger 仍以 `invalidating` 披露单调性；+2 缺失恢复：出了数就撤掉它答掉的请求（并过 `verify_data_gap_report`）、不可恢复时那批请求原样留着（列在不等于分布可得）；+1 AST 守卫：themis/ 下没有模块两次定义同一个顶层名）。

**答案的形状成为一等事实：四个估计器族不再被渲染成「结论：是」（2026-08-04，接上条）**：修复型，用户可见，是本轮**先做全量测量、再定改法**的产物。用户问「为什么还有这么多杂七杂八的要改，系统不是一个整体吗」，普查了一遍信封的消费端，答案是：**内部是整体（`routing.py` 一张路由表、`refusals.py` 64 个物种、`blocks.py` 20 个块，各自「声明一次 + 单一出口拒绝未登记的」），但从「内核知道的事实」到「读者看到的面」之间没有对应的那张表**——那一段是手工的，所以每加一个一等事实就掉出几件杂活。

**测量（两轮全量插桩，3855 passed 不受影响）**：①**事实清单** 21 个顶层字段 + 20 个块 = 41；**消费面** 160 个文件（人 67 / 审计 20 / 契约 7，含 MCP、剔除 node_modules 与 dist）。②**7/20 个块没有任何确定性渲染器**，6 个实测在产生（共 490 次）：`mechanism_audit` 276、`type_reconciliation` 122、`missing_data_recovery` 39、`joint_identification` 26、`longitudinal_identification` 19、`proximal_estimand` 8；其中 3 个连 LLM prompt 都不认识。四条确定性的路各自手写、各自不全：`analysis_report` 3/20、`explainer` 5/20、`data_gap_report` 7/20、`Verdict.tsx` 2/20。③**决定性的那一格**：459 次数值估计里 **93 次 `point` 为空**，其中 **84 次读者在「答案」节读到的是 `结论：是`**——`dose_response_*` 29 / `mediation_*` 28 / `joint_backdoor_linear` 17 / `counterfactual_cell_plugin` 11，跨 8 个方法、4 个族；答案本身就在同一个块里，字段数一一对应（`dose_response_curve` 29、`decomposition` 29、`joint_effect` 17、`counterfactual_cell` 11）。web 同病（`fmtNum(null)` → 一个破折号），且 `types.ts` 把 `point` 声明成不可空。

**根因**：`_render_answer` 靠**探测字段名**推断「这个估计的答案长什么形状」，而这个事实**产生端知道、从未被声明过**。失败方式是**静默下坠**——掉进分支 5（结构布尔），那里总有值，所以永远不会红。为什么是根因不是表象：①84 次横跨 4 个族、不同时期加入；②分支 1b（`probabilities_of_causation`）是上一次同一伤口的补丁，**它救下的正好是 7 次**，紧挨着的 84 次没人补——补丁式修法实测不能自我扩展；③`_render_answer` 的 docstring 自己写着这个失败模式（*「rendering scaffolding in the answer slot is how a positivity violation reached a reader as a confident 是」*），**病知道、警告写了、照样复发**；④正确形状仓里已有——`data_gap_report._bind_item_species`（闭合词表 `MISSING_ITEM_GAPS` + import 时双向拒绝 + 允许显式声明 `_RaisedElsewhere(reason=...)`），**只服务于一个事实**。

**修法**：新 `themis/answers.py`（与 `blocks.py` / `refusals.py` / `routing.py` 同列）——6 个答案形状各声明一次（`lives_in` 说出答案住在哪个键，是**字段不是闭包细节**，因为 web 用 TypeScript 渲染、导不进这张表，词表必须可被检视）；`SHAPES_OF` 把 schema 里 38 个 method 各绑一组形状，**meta 测试双向钉死**（enum 里没绑的 = 估计到了报告说不出话；表里多绑的 = 读起来像覆盖的死文案）；`bind` 让每个面各绑自己那一端并拒绝覆盖不全的绑定集（`routing.py` 的形状）。消费端：`analysis_report` 补 4 个渲染器 + 抽出公用元信息尾巴 `_estimate_meta`（**测试当场抓到唯一打过补丁的 causation 分支不带这条尾巴**：方法名、样本量、E-value 全无）；**分支 5 从兜底降级**——估计块在场但说不出答案时，直说「没有任何可呈现的答案」而不是借用下面那句关于图的结论。web 端 `lib/verdict.ts` 新 `answerRows` 绑同一套词表、`Verdict.tsx` 加分支、`types.ts` 补字段并把 `point` 改为可空（`tsc -b` 干净）。

**先量再改救回一条**：普查一度把 `mechanism_audit`（276 次）列为「没人读」，**核实后不成立**——`build_assumption_ledger:596` 读它、转成一条 `functional_form` 账本条目，而账本有 3 个确定性面渲染。它属于「在别处渲染」，正是 `_RaisedElsewhere` 存在的理由：**没有声明，「在别处」和「忘了」长得一模一样**。同法核实 `_compute_answer_tier` 键在识别信号上而非 `point` 上，故中介仍被判为「点估计」层级，**这一处没有同病**。

**声明的取舍**：①`bind` 只保证 Python 面有渲染器；web 是独立手写的 TS 链，**用 meta 测试按 `lives_in` 钉它的覆盖**——这是明确更弱的一半，理由是不把渲染好的文字塞进信封（那会让内核开始生产给人看的字）。②`explainer.py` 不动：它只读 `numeric_result`（theta 路）、根本不读 `numeric_estimate`，是结构解释面不是答案面，也不在 `themis.__all__`（只有测试 import）。③`ipw_ht` / `joint_backdoor_logistic` 两个 method 全套件从未触发，形状按同族兄弟声明并**在表里标明**（㉖ 三档记账，不混进「实测」）。

**未做已登记**：①还有 5 个块没有任何确定性渲染器且不属于「在别处渲染」——`type_reconciliation`（122 次，3 个验证器读、没有人面）、`missing_data_recovery`（39）、`joint_identification`（26）、`longitudinal_identification`（19）、`proximal_estimand`（8）；它们不是**答案**而是**答案的来路**，该进的面是「怎么算出来的」而不是答案节，是另一张表。②`counterfactual_error` / `causation_error` 两个块全套件零产生，且写的是**裸异常字符串**（`extensions={blocks.COUNTERFACTUAL_ERROR: str(exc)}`）——这正是拒答通道取代掉的老模式，该并进 `refusals.py` 而不是留着。③上一条登记的缺失恢复路径两件事仍未做。

**基线（本条）**：3855 → **3880**（+25：形状词表对着 schema enum 双向钉死、`bind` 两个方向各拒一次、未声明的 method 响亮而非默认、双模的两个族点在前；5 个形状各一条「不得渲染成关于图的结论且必须出数」+ 各一条「必须带公用尾巴」；点估计仍以数字开头；估计块无答案时不借用结构结论；结构查询仍读作它的判断；web 按 `lives_in` 逐形状钉覆盖）。

**答案的来路成了一节：十个识别块不再对读者一言不发（2026-08-04，接上条）**：修复型，用户可见。上一条登记「还有 5 个块没有渲染器」；**按声明清点，真实数字是 10 个块、369 次**，而且那份 5 个的清单本身有一条是错的——`type_reconciliation` 其实经 `declared_type_data_mismatch` gap 到达读者，属「在别处渲染」。

**测量（全量插桩，3880 passed 不受影响）**：`transport_identification` 75 / `identification` 53 / `mediation_decomposition` 50 / `selection_recovery` 40 / `missing_data_recovery` 39 / `iv_identification` 31 / `mediation_joint_decomposition` 28 / `joint_identification` 26 / `longitudinal_identification` 19 / `proximal_estimand` 8。**每个块的定义性事实在几乎每一次出现里都缺席**：`identification` 50/53 次连自己的模式名（backdoor / front_door / instrumental_variable）都没出现；`iv_identification` 31/31 缺 `iv`、29/31 缺工具名；`longitudinal` 19/19 全缺；`missing_data_recovery` 39/39 缺估计量、31/39 缺机制；`transport` 缺两个总体名（32 / 29）与迁移公式（25）。**本轮的插桩教训**：命中判据写成「块里任一字符串出现在报告里」，于是三个块记成 100% 命中——实际命中的是 `x` / `y` 这类变量名，问题行里本来就有。**token 重合分不出「在别处渲染」和「巧合」**；上一轮 `mechanism_audit` 那次分得出来，是因为查的是「它去了哪」而不是「有没有重合」。

**根因**：报告的小节表是 问题 / 答案 / 因果模型 / 验证 / 假设 / 数据缺口——**没有「答案的来路」这一节**，所以干这活的事实全都没有落点，来一个哑一个。三条证据说明缺的是节、不是渲染器：①**一等字段同病**——`formula` 与 `derivation` 也不渲染，footer 原话是「估计式已生成（**机器可读，见 `result.formula`**）」；两条完全不同的通道栽在同一件事上，毛病在两者的下游。②**生产端已经为一个不存在的消费端写了字**：`scheduler.py:748` 的注释称 `extensions["identification"]` 是「the human surface」，并设想「a renderer keying off」它——那个 renderer 从没被建过。③`blocks.py` 的分组从第一天起就是**按谁写的**（「识别层得出的」「数值端产出的」「读答案时配着看的」），**没有一处按谁读**——这正是上一轮那份「事实 × 消费面」矩阵必须手工拉的原因。而报告的另外四族——答案（`answers.py`）、假设（账本）、缺口（gap 列表）、拒答（`refusals.py`）——**各有一张表、各有一个落点；只有「来路」两样都没有**。

**修法**：`blocks.py` 把注释分组升成一等字段 `Block.read_as`（必填，5 个 `Family` 各声明一次、20 个块各选一个），加 `DECLARED`（保留声明顺序）/ `declared_as(family)` / `bind(family, renderers)` 两向拒绝——`answers.bind` 的同一安排。`analysis_report` 新开「怎么算出来的」一节（在 答案 之后、因果模型 之前），10 个路线渲染器由 `bind(ROUTE, …)` 绑定：**新加一个路线块而没有渲染器，`themis` 直接 import 失败**。web 端 `lib/verdict.ts` 新 `routeRows` + `ROUTE_ORDER`；`Verdict.tsx` 那个**一直叫「怎么算出来的」却只说公式和路径**的折叠块，现在真的说路线（`tsc -b` 干净）。prompt 侧把 `extensions.{...}` 那一行**从枚举 7 个块改成说五族原则**（没见过的块也能按「它说的是什么」归位），Methodology 那一层点名 route。

**实测当场纠了一处自造的噪音**：真实 IV 结构路上 `identification` 与 `iv_identification` 并存，第二条 bullet 渲染出来是 `- **工具变量**：\`z(me)\``——**一句新话都没有**。生产端把 strategy / instrument / conditioning / required_assumption **有意复制**进 `identification` 并称那份副本是 human surface，所以 IV 块该说的只剩「候选里做过选择」和「Wald 比答的是依从者」；数值 IV 路单独发这个块，工具名才由它来说。规则写成一句：**渲染器可以拒绝重复同一信封上更靠前的块已经说过的事实，说不出新话就返回空、空行被丢掉**（这也是签名要收整个 result 的理由）。

**声明的取舍**：①**没有把路线写进信封**。信封里已有面向读者的散文（gap 的 `description`、账本的 `claim`、拒答的 `reason`），照那个先例本可以让两个面读同一份字符串、彻底免掉跨语言重复；不做，因为那是**改内核数据契约**，而且信封现有散文语言不一致（gap 是英文、账本是中文），在那件事定下来之前再开第三条散文通道会把不一致焊得更死。代价：10 个渲染器 Python 与 TS 各写一遍，靠一条**解析 `ROUTE_ORDER` 并与 `declared_as(ROUTE)` 逐项比对**的测试钉住——比上一轮答案形状那条「名字出现过」强一档，连顺序一起钉。②报告仍不渲染识别公式：`formula` 是 AST dict，web 有 `fmtFormula`、Python 侧没有对应物，另开一档。③`ROUTE` 之外的四族只**声明**了归属，没有 `bind` 强制——import 期保证目前只有 route 这一族有。

**顺带查实、未修已登记**：中介类效应查询走结构层（无 θ 无数据）时，答案节渲染的是 `结论：**是**`——**又一次拿关于图的判断冒充「效应多大」**，且是上一轮形状表够不着的一格（这次是**根本没有估计块**，不是估计块空）。不当场修，因为分支 5 对 `structural_result=False` 的 effect 查询说「不可识别」是**对的**，正确的门要按 query_kind × 值分，需要自己的一轮测量。

**基线（本条）**：3880 → **3913**（+33：每个块必须说出自己被当作哪一族读、五族对注册表的划分、声明顺序即小节的宣读顺序、`bind` 两个方向各拒一次、不写 `read_as` 的块建不出来；10 条路线各一条「定义性事实必须到达读者」+ 各一条「必须出现在组装好的报告里」；无路线时不出空标题；节序在答案与因果模型之间；两条路线按注册表顺序而非字典插入顺序宣读；未登记的模式名照原样说出而不是丢掉；IV 不重复上一条已说过的事实、且单独出现时工具名不丢；web 的 `ROUTE_ORDER` 与注册表逐项比对且每个名字都有渲染器）。

**答案是不是答案，取决于问的是什么：一个布尔字段断言十个命题（2026-08-04，接上条）**：修复型，用户可见。上一条登记「中介类 effect 查询答案节仍渲染 `结论：**是**`」。**按 query_kind × 分支 × 值全量清点，真实规模是 81 次答非所问**，而且登记时看到的又是尾巴——最刺眼的一格根本不是中介。

**测量（全量插桩，1397 个结果到达读者，插桩不影响当时的 3913 passed）**：答案节 271 次渲染那句结构布尔，其中 **81 次问的是一个数**（`effect` 78 + `proximal_effect` 3）。细分：**34 次带着 `formula`**——它们要的那句话（「效应**可识别**（估计式已生成），但当前**没有数据**」，本轮共命中 352 次）**已经写在下一个分支里了**，够不到只是因为分支 5 排在前面且无条件接住任何布尔；32 次既无 formula 也无估计块（中介、近端），落到分支 5 后无处可去；12 次 `value=False` 渲染成 `结论：**否**`——对「效应多大」这个问题，「否」不是弱答案，是不成句。`structural_value` 实测只出现过 True / False / None，schema 允许的 string 无任何产生端使用。

**根因**：`structural_result.value` 是**裸布尔，它断言的命题不在信封里**。这个命题是 query_kind 的函数，而这张表**系统里已经有五份，没有一份是数据**：① `verify()` 必须按 query_kind 分派到四个不同验证器（`verify_cause` / `verify_assoc` / `verify_identify` / `verify_effect_structural`）——不知道 claim 的是哪个命题就无法独立重算，所以验证器**不得不**知道；② `explainer.py` 一种一个函数、每个都说命题不说裸布尔，**并且未知即 `raise`——它是唯一写全并且强制了的面**；③ web `structuralReadout` 三个特例 + `成立 / 不成立` 兜底；④ 报告问题行判 `kind == "association"`，枚举值是 `"assoc"`，**这条分支永不命中**，于是三种「布尔即答案」的问法之一被问成 `（查询类型：assoc）`——**而死分支底下还压着第二个 bug**：那行读的是 `from` / `to`，是 **`cause` 查询的字段**；`assoc` 查询带的是 `left` / `right`，所以就算字符串写对了，它也只会问出 `**?** 与 **?** 是否相关联`。**一条永不命中的分支不会出声，所以它错得再离谱也没人知道**；⑤ prompt 只写「`true` / `false` for cause / assoc」，且把 `structurally_solved` 说成「boolean assoc/cause」——中介 effect 查询就是反例。**五个面五种错法**指向共同的空缺；explainer 完整不是因为写它的人更小心，而是因为**它的兜底是 `raise` 而不是 `return`**。

**修法**：`themis/questions.py`——schema 已钉死且**必填**的 10 个 query_kind 各声明一条读法（`asks` / `settles` / `fails` / **`verdict_is_the_answer`**），`bind` 两向拒绝。那个布尔字段是所有面都需要、谁都没有的事实，而且**它不是「cause 和 assoc」**：`identify` 问的正是可识别性，所以同一个命题对 effect 是脚手架、对 identify 就是答案——**探字段名永远分不出来，字段一模一样，只有问题能分**。三个面各绑一端：答案节（是答案就说命题、不说裸「是 / 否」；不是答案且为假就说「不可识别」，为真就让位给下面那句本来就对的话，另补「可识别但没有产出可代入的估计式」一格给中介 / 近端）、问题行（死分支由构造消失，另 6 种从回显英文枚举名改成中文问句）、explainer（`if` 链换成 `bind`，保证从「第十一条分支在结果到达时抛」提前到「少一个 kind 就 import 失败」）。web 端 `QUESTION_READINGS` 十条、删掉兜底，chip 的 cap 按 `answersIt` 分——**把识别前提叫「结论」是同一个替换的一词版**。prompt 两行改成原则。

**中途撤回了自己的一条取舍**：本条原打算「`asks` 只做问题行的兜底文案，6 种 kind 不写原子级模板，因为要逐一核实每种 query 的字段形状、是另一档活」。查 `assoc` 那个 bug 时发现，**`$defs.query.oneOf` 一条命令就能把十种 query 的字段形状全读出来**——理由不成立，取舍随之作废，十个模板全写了。**schema 当场又纠正了一次直觉**：`counterfactual.observed` 是**单个** groundedAtom 不是数组，按数组写会去迭代 dict 然后崩。

**声明的取舍**：①web 那份表是 Python 表的镜像，靠**解析 `QUESTION_READINGS` 并把 key 与 `answersIt` 逐项比对**的测试钉住——钉的是那个布尔（事实），不是文案（说法）。②`Verdict.tsx` 的 `query_kind === 'cause' ? '因果路径' : '支持路径'` 看过没动：supporting_paths 只有 cause / assoc 产生，一分为二是对的，不值得为它给词表加字段。③十条问题行的测试用 fixture 而非端到端真跑——但 fixture **必须只用 schema 声明的字段、且覆盖全部 required**，由一条读 `$defs.query.oneOf` 的测试守着：**第一版测试正是照渲染器抄的 fixture，所以它跟着渲染器一起错，一个字都没抓到**。

**修完重量一遍（同一插桩，全量）**：1400 个结果，**答非所问 0 次**（原 81）；仍以结构布尔作答的 192 次正好是 cause 76 + identify 67 + assoc 49——只剩那三种「布尔就是答案」的问法。（探针的分类器按旧句子前缀分桶，而修复恰好改了那些前缀，所以「可识别待数据」那一桶归零、数量并入兜底桶「数值」；那是**探针失真不是行为变化**，决定性的是前两个数。）

**端到端时又抓到一个（已修）**：把 cause 与 assoc 两道题放进**同一个程序**跑，assoc 那份报告的问题行是「**x** 是否因果影响 **y**？」——**cause 的问题**。`_find_query` 取的是程序里的**第一条** query 语句，不看 `result.query_id`；单查询程序两者一致，而 **suite 里每个 fixture 都是单查询**，所以它一直没出过声。改成按 `query_id` 取（schema 里 `id` 是必填），取不到就落回该 kind 的散文——**拿另一道题的变量去填，正是这个 bug 本身**。旁证：`tests/test_e2e/` 里两个文件各自写了自己的 `_find_query(program, query_id)`，**它们早就知道要按 id 取**。

**顺带查实、未修已登记**：`data_gap_report.py` 的 `_ESTIMAND_QUERY_KINDS = {effect, identify, counterfactual}` 是**另一条轴**（「`answer_tier` 有没有意义」），不是本条这张表的拷贝，所以没有并；但它自己有个可疑处——**只列 3 种，而注释只解释了 7 个排除项里的 3 个**（「cause / assoc / probability 不是估计量查询」），`causation` / `scm_counterfactual` / `counterfactual_conjunction` / `proximal_effect` 这四种**会产出数值**的 kind 被静默排除、`answer_tier` 恒为 `None`，没有写下理由。判它是有意还是漏，要按 kind 量一轮 tier 的实际分布。

**自己的测试当场犯了上一条的错**：「每种 kind 的问题行不许出现枚举 token」判 `identify` 失败——那行是完整中文问句，末尾带 `（\`identify\`）` 标签。**token 出现与否分不出「句子＋标签」和「token 顶替句子」**（正是上一条 ㉝ 说的），改成量「旧兜底 `（查询类型：x）` 的形状还在不在」＋中文字符数下限。

**基线（本条）**：3913 → **3963**（+50：词表与 schema 的 `query_kind` 枚举双向相等、`query_kind` 必填所以无需兜底、恰好三种问法由布尔作答（字面钉死）、每条读法两个值都得有命题且不相等、少绑一种拒绝、多绑一种拒绝、未知 kind 抛而不兜、explainer 是绑的不是链的；六个实测格各一条——问数不再答判断、不可识别说成「不可识别」而不是「否」、带 formula 的落到本来就写好的那句、图问题仍由判断作答（真 / 假各一）、十种 kind 都不落到「无可呈现的答案字段」；问题行：fixture 只许用 schema 声明的字段且必须覆盖 required、十种 kind 各一条「问句里必须点到它被问的那几个变量、且不许出现未解析的 `?`」、十种 kind 无 program 时也不落回旧兜底形状；同一程序里两道题各问各的、`query_id` 落空时回散文而不是借用别人的变量、kind 对不上的 query 不会被塞进这个 kind 的渲染器；web 的表与 Python 逐项相等、兜底确已消失；一次真实中介运行端到端）。

**一个三元集合回答了两个问题，两个都答错了 probability（2026-08-04，接上条）**：修复型，用户可见。上一条登记「`_ESTIMAND_QUERY_KINDS` 只列 3 种、注释只解释了 7 个排除里的 3 个，四种会产数的 kind 被静默排除、`answer_tier` 恒 None」。**量完，登记的说法是错的**——那个字段不是恒 None，而是**看你从哪个入口进来**。

**测量（全量插桩，行为不变 3963 passed）**：识别路径上 7 种 kind 全为 None，**而估计路径无条件写**——`dispatch._finalise_numeric_result` / `_finalise_numeric_bounds_result` 直接往报告里塞 `answer_tier="point"/"interval"`，**不看 query_kind、不读任何名单**。所以同一个 causation 查询走 `themis.run` 没有 tier、走 `themis.estimate` 有：信封实测 causation 25 个里 17 个有、8 个没有；scm_counterfactual 6/17；proximal_effect 4/10；counterfactual_conjunction 5/6。第二个消费端更刺眼：同一个集合还决定「缺分布时区间是不是真退路」，它的 else 分支被调用 **226 次，其中 222 次是 causation**，说的是「观察性条件量是点可估的，**没有 bounds 替代路径**」——对 PN/PS/PNS 这是**假的**，Tian-Pearl bounds 正是它的答案。**那句注释解释的是它 226 次里的 4 次。**

**顺手量了孪生集合，抓到第三个（真丢数据）**：`_QUERY_KINDS_WITHOUT_DATA_NEEDS` 把 `probability` 列为「无数据需求」，并且**在物种分类之前就 `return None`**。子集实测 2 次：内核明明提了 `MISSING_DISTRIBUTION`（「Theta 中缺条目 P(coin=True)」），报告整个不存在——而**报告不存在正是「问过了，什么都不缺」的信号**。

**根因**：两条都是「问法的属性」被手写成 output 模块里的私有名单，一次成员测试回答两个不同的问题（「这个问法有没有一个量」／「点没了区间能不能顶」）。**同一个文件自己就矛盾**：321 行说 probability「不是估计量查询」，1926 行说 probability「是点可估的量」。两个问题对那 3 个成员碰巧同答案，else 分支就各自跑偏；后加的 kind 静默落进 else 继承了 probability 的答案，**没有人决定过**。决定性证据是**估计层根本没有这张表**——「这个问法能不能有 tier」在系统里有两份互相矛盾的实现，其中一份是空的。

**修法**：两条事实各成 `Question` 的一等字段（必填，十种问法各声明一次）——`names_an_estimand`（只有 cause / assoc 为假：它们问的是图，没有量）与 `interval_fallback`（`str | None`，只有 effect / counterfactual / causation 有：Balke-Pearl / Tian-Pearl ×2）。两个名单删除，三个消费端各读一端：早退门读前者、tier 门读前者、缺分布的替代路径读后者并**把定理名说对**（causation 与 counterfactual 从 Balke-Pearl 改成 Tian-Pearl；effect 那句字节不变，它本来就是被 `_reconcile_alt_paths_with_bounds` 改写的占位符）。`interval_fallback` 是**库存事实不是数学事实**——写成 `str | None` 而不是布尔，是因为下一个 kind 的作者必须说出「谁来给这个区间」，说不出就是 None。

**没修完的那一格，是被自己的测试逼出来的**：本条原本要让 causation 也在识别期报 tier。第一版按「monotonic 未声明 ⇒ 点被前提挡住 ⇒ 区间」写完，构造一个 `x<->y` 的图去验，**它照样报 interval**——查下去发现 causation 的 dispatcher **先要观测联合、再去识别干预风险**，缺 θ 时两件事都没发生：monotonic=True 也不知道点在不在（风险可能不可识别），monotonic=False 也不知道区间在不在（Tian-Pearl 同样要那两个风险）。**两个默认值都是许诺**：POINT 许一个缺单调性就没有的数，INTERVAL 许一个被未观测混杂否掉的界。`AnswerTier` 没有「还不知道」这个成员，所以 causation 在**没有数**时不发 tier——不是名单，是 `_answer_shape_is_undecided` 这条按结果判的规则。实测：causation 43 次里 29 次不发（形状未定）、14 次照数发（point 10 / interval 4，原来全是 None）。

**修完重量一遍（同一插桩，全量）**：causation 缺分布的 266 条替代路径全部改说 Tian-Pearl，**那句假话 0 次**（原 222）；`report is None 且带着 item` **0 次**（子集原 2 次；全量里 6 次走这条形状，其中 4 次是本轮新测试）；四个原本静默排除的 kind 在识别期各自报出实测正确的 tier——probability 36/36 point、scm_counterfactual 27/27 point、counterfactual_conjunction 19 point + 3 none（none 即 ID* hedge）、proximal_effect 9 point + 2 none；effect / identify / counterfactual 三档分布**逐格不变**（1246 / 133 / 68）。

**声明的取舍**：①**web 的头条会变**——`Verdict.tsx` 是 `!tier && struct ? structuralReadout(...)`，所以这四种 kind 的头条从「识别：…可识别」换成「能给的最强答案：点估计」。这是 effect / identify / counterfactual 早就在用的处理，现在一致了；代价是 proximal / conjunction 的读者在头条上看不到「识别条件成立」那半句（仍在信封里）。②**causation 的替代路径没有对账**——`_reconcile_alt_paths_with_bounds` 只对 effect 查询和已算出 `bounds_result` 的结果动手，所以 causation 那句「接受 Tian-Pearl bounds」在风险不可识别时是乐观的；要修得先让 causation 先识别后要数（见下）。③没有为「未声明单调性」新开一条 `missing_assumption` 缺口告诉用户「声明它就能拿到点」——那是功能不是纠错，登记。

**未做已登记**：**causation 的 dispatcher 顺序**（先要 θ 的观测联合、后识别干预风险）是它识别期没有 tier 的根因，也是替代路径无法对账的根因——把顺序倒过来（识别在前、要数在后，其余 kind 都是这个顺序）能同时结掉这两条。

**基线（本条）**：3963 → **3980**（+17：两个字段各一条字面钉死（恰好 cause/assoc 无估计量、恰好三种有区间退路）、无量者必无区间、**报告模块里不许再有任何 QueryKind 的模块级集合**；三个消费端各自的实测格——causation 缺口拿到 Tian-Pearl、probability 缺口不被许诺区间、probability 的缺口不再随报告一起消失、图问题无话时仍不出报告；tier：causation 形状未定时（单调与否各一）不发、形状未定连界也不存在时也不发、有数时照数发 interval、probability 发 point、图问题不发、scm_counterfactual / proximal_effect / counterfactual_conjunction 三种各一条「没有估计器也该有 tier」）。

**先问哪个输入纯粹是代码顺序，而顺序决定了「有没有答案」会不会被问出口（2026-08-04，接上条）**：修复型，用户可见。上一条登记「causation 的 dispatcher 先要 θ 的观测联合、后识别干预风险，是它识别期没有 tier 的根因」。量完发现它还是一条**更重的假话**的根因。

**测量（影子跑，不改行为）**：causation 21 次停在「theta 缺观测联合」这一步，**识别根本没跑**。让影子替它跑完：20 次是「可识别、只差数据」（monotonic 11 / 非 9），**1 次是「根本不可识别」**（`UNIDENTIFIABLE_NO_ADMISSIBLE_SET:query:effect_admg`）——那一次的报告只说「缺概率分布 P(x=True)、P(x=False)」，**即「去收这两个边缘就有答案了」，而任何数据都答不了它**。套件里正好有对照：`test_confounded_without_experimental_risks_is_a_gap` 是同一张 `x<->y` 图**带 θ**，识别跑了、逃生口正常出现；上一条新写的那个是同一张图**不带 θ**，真相被埋。**identifiability 是图的性质，同一张图两个答案，说明报的不是图而是代码走到哪一步。**

**根因**：dispatcher **在第一个拿不到的东西那里就返回**，于是报告只描述了它需要的两个输入之一；而这两个输入是独立的（观测联合来自 theta，干预风险来自识别），先问哪个纯粹是代码顺序。

**修法**：两个输入都取齐再决定报什么——`_derive_interventional_risks` 改成返回 items（与单臂版同形）而不是现成 QueryResult，新 `_causation_gap` 按名字去重后走**同一次** `push`（两份缺口本来就重叠，拼接会让读者看到同一组两遍；风险侧 item 的 skeleton 从已 push 的请求里取回，与 theta 的 skeleton 表合并）。**逃生口的理由按实际是哪种失败写**：它对「不可识别」和「只差数据」都触发，而这两种要的修法相反，原来一句「effect not identifiable from the supplied data」会把后者的读者送去改一张本来就对的图。tier 恢复按「单调性 + 不可识别信号」判——上一条删掉它是因为信号缺席，现在信号在了；不可识别**压过**前提，那时界也够不到，NONE 才是实话。

**顺带结掉上一条登记的 (d)**：`answer_tier == NONE` 时撤回缺口上的区间承诺（`_withdraw_interval_offers`）。**承诺和撤回是同一个字符串按构造生成的**（`_interval_offer(query_kind)` 从词表取），不是子串匹配——否则这条检查会随文案漂移而烂掉；`_species_theta_graph_mismatch` 里硬写的 Balke-Pearl 一并换成同一个来源（对 counterfactual 它本来就说错了定理）。**实测撤回确实会触发**：causation 2 次共撤 4 条；effect 在 NONE 上 9 次撤 0 条，因为 `_reconcile_alt_paths_with_bounds` 早就替它做了——**0 的意思是「本来就没有」，不是「没生效」**，两者要分清（㉙）。

**修完重量一遍（全量插桩）**：causation 47 次 tier **一次 None 都没有**（interval 19 / point 21 / none 7；本轮之前是 29 次 None）；「联合缺 + 不可识别」这一格 **2 次**，现在四条 item 齐全（两条 `missing_distribution` + `unidentifiable_no_admissible_set` + 逃生口），原来只有前两条；其余 kind 逐格不变（effect 1246＝1040/169/37、identify 133、counterfactual 68、probability 36、scm 27、conjunction 22、proximal 11）。

**基线（本条）**：3980 → **3983**（+3 净：删掉上一条钉「形状未定就不发 tier」的 3 条、新增 6 条——withheld premise 决定形状（单调 point／非单调 interval）、**同一张图带不带 θ 必须得出同一个识别结论**（两参数）、NONE 上不许留区间承诺、逃生口必须说清自己是两种起因里的哪一种）。

**拒答的句子是读者的答案行，所以句子里的值就是给读者看的值（2026-08-04，接上条）**：修复型，用户可见。登记写的是「33 处拒答文案把数据值直插给人看的句子、约 10-15 处是裸 numpy」。**两头都不对**：处数是 158 个 raise、135 个插值；而运行时真出问题的形态**主要不是 numpy**。

**测量（全量插桩）**：一轮抛出 581 次拒答，**78 次**的句子带着不该给人看的东西。最大的一格 `outcome_not_binary` **55 次**，消息里写「outcome 'y' has 3000 observed levels ({levels})」——**把整列 3000 个浮点的 repr 倒进一句话，实测 62,003 字符**，而 `_render_answer` 把 `reason` 原样放进答案节。`treatment_not_binary` 17 次同形（500 个值）。真正的 numpy repr 只有 9 次（`np.float64(0.0)`、`Z=np.True_`）。**登记指的是小的那一半。**

**根因**：拒答消息是**给人看的句子**，构造方式却是调试式 `{x!r}` 插值。系统里已有**五份**把 numpy 标量降成 Python 的辅助（`_py`×3、`_to_py_scalar`、dispatch 内联一处），**五份的自述全是「JSON-safe / for the result dict」**——同一个值有两个去处（信封 / 句子），**只有信封那条路上有规范化**；而"多少"连一步都没有：`{levels}` 对 2 个和 3000 个一视同仁。`EstimatorFailure` 的 docstring 早写着 `details` 是「the numbers behind the refusal…belong to the occasion」，**结构化落点本来就在**。

**修法**：`refusals.describe` 做「值进人话」的单一出口——numpy 标量降级、浮点按 6 位有效数字、集合说数量加样例；**截断阈值按元素类型读而不是定死**，因为两种集合要相反的待遇：一串**名字**（调整集、设计变量、声明的状态）本身就是答案，砍掉就砍掉了读者要用的东西；一列**数据值**只是计数的证据，且没有上限。`EstimatorFailure.__init__`（已经在那里校验物种的同一个出生点）加一道 1000 字符的**不抛异常**兜底——拒答若因为自己解释太长而崩，就把「没有数，原因是」变成了没有答案。

**静态规则又找出运行时没触发过的 19 处**：AST 守卫两条——「句子里说了有多少个，就不许再把它们印出来」（`len(X)` 与裸 `X` 同现）和「不许插一个刚 `sorted()`/`list()` 出来的集合」。前者是 62,003 那句的形状本身，后者按**表达式形状**判而不是按名字（㉝）。**运行时量到「已经爆的」，静态量到「能爆的」，两者都要**。

**修完重量一遍**：78 → **2**，而这 2 次是**探针误判**——`non_positive_error_variance` 说的是「got nan」，`nan` 本来就是该说的英文词，是我的正则把它当成了 numpy 痕迹。原来 62,003 那一格现在中位数 **151 字符**；全套件真实消息最长 426，兜底（1000）**一次都没在真实站点触发**，唯一被截断的是专门测它的那条测试。

**没有据可claim 的一格，如实说**：`counterfactual_error` / `causation_error` 两块本轮探针记到 0 次产生——但那个计数器只看 `themis.run` / `themis.estimate` 出来的信封，而 causation 那条 `outside_language` 分支在别处也走得到（同一天的另一轮探针就量到过 1 次）。**0 在这里的意思是「没有流量经过我的插桩」，不是「没有产生」**（㉙），所以那条登记仍未验证。

**基线（本条）**：3983 → **3996**（+13：numpy 标量按它代表的值出现、整列只说数量加样例、名字列表整份印出（截断阈值按元素类型读的理由）、短集合原样、浮点丢掉没人要的尾巴、字符串保留引号；超长消息截断而不抛且物种仍在、正常消息逐字不动；两条 AST 规则——数了就不许印、不许插刚建的集合；实测 62,003 那句现在成句；分层标签读作值不读作 dtype）。

**估计式终于被说出来：一个一等字段被两个指针指了十轮（2026-08-05，接上条）**：修复型，用户可见。登记写的是「报告不渲染识别公式」。

**测量（全量插桩）**：**788 个结果带着 `formula`**（effect 724／identify 43／probability 15…），每一个都被告知两句话——答案节「估计式已生成，**见文末审计**」，而文末审计说「估计式已生成（**机器可读，见 `result.formula`**）」。**两个指针，尽头什么都没有。** 节点实测 `probability_ref` 1496／`sum` 658／`product` 622／`fraction` 25，顶层 sum 508／probability_ref 265／fraction 15，深度最深 6（depth≥4 的 89 个）。

**根因**：两轮前建「怎么算出来的」这一节时，`bind` 接的是 `extensions` 里的 10 个**块**；`formula` 是**顶层字段不是块**，所以那次「少一个渲染器就 import 失败」的强制从来没看它一眼。留下的注释就是物证（㉕ 的自辩式句子）：「机器可读，见 X」——同一形态 `derivation` 也有（footer 只说「推导链 N 步」）。

**为什么不能照抄 web 那份**：`fmtFormula` 41 行，而 schema 的 `formulaExpression` 有**五**种节点它只处理四种——`constant` 落到 default 会渲染成字面量 `"constant"`（实测今天不可达，登记）；更实的是它把**所有 `var_ref` 硬编码成字母 `z`**、`Σ` 的下标却取自 `over.predicate`，**同一条公式里同一个绑定变量印成两个名字**，嵌套求和会把不同绑定塌成同一个 `z`。**两个缺陷都是读 schema 读出来的，不是读那份实现读出来的**（㉟）。

**修法**：新 `themis/output/formula_text.py`——五种节点各一个渲染器、`bind` 两向拒绝（少一种 import 期失败），渲染时带一个环境把 `sum` 的绑定传下去，于是被绑的值读作它所在的那个原子：`Σ_z [ P(y | x, z) · P(z) ]`，正是读者认识的 g-formula 写法。报告在「怎么算出来的」里说出估计式，答案节与 footer 那两句不再指向字段。web 的 `formula.ts` 同步改（`tsc -b` 干净、`vite build` 已跑，dist 不陈旧）。

**自己写的第一版又犯了同一个错**：front-door 渲染成 `Σ_m [ P(m | x) · Σ_x [ P(y | x, m) · P(x) ] ]`——**`x` 既是被干预的值又是求和变量，同一个字母两个意思**，正是我刚批评 web 的那件事。第一版的判据是「扫这个 sum 自己的 body」，而冲突的另一半（`P(m | x)` 里固定的 x）**在另一棵子树上**，sum 从自己身上看不见。改成一次全树判定「哪些谓词被钉到了具体值」，再给撞名的求和变量加撇：`Σ_m [ P(m | x) · Σ_x' [ P(y | x', m) · P(x') ] ]`。

**基线（本条）**：3996 → **4013**（+17：五种节点与 schema 的 `formulaExpression` 双向相等、少绑一种拒绝、多绑一种拒绝、未声明的节点抛而不兜；真 / 假值读作谓词与否定、外部绑定的值读作裸谓词、被求和的变量读作原子本身而不是 `z=z`、常量说出自己的值、嵌套求和各保各的变量；两条真实估计式端到端（后门、前门带撇）；报告说出估计式且不再出现「机器可读 / result.formula」、且落在「怎么算出来的」节里；web 五种节点各有一个 case）。

**识别层拒答走进它自己的通道：一个字段两条路，只有一条通向读者（2026-08-05，接上条）**：修复型，用户可见。登记写的是「`counterfactual_error`／`causation_error` 两块零产生且写裸散文，该并进 `refusals.py`」。

**测量**：先按方案做「块 × 到达面」的普查（AST，不是 grep——**探针自己被修正了两次**：一开始把 `bind` 字典里的键算成写点，于是 ROUTE 族显示「没人读」；改完又发现只匹配属性名不匹配模块名，`questions.CAUSATION` 被当成 `blocks.CAUSATION`，凭空给两个 ANSWER 块记上了渲染器）。修正后：ROUTE 10 块全部有 `bind` 保证；ASSUMPTION 3 块经 orchestrator 到达；GAP 的 `type_reconciliation` 符号读点为 0，**真实消费端是 `verifier/type_reconciliation_rules.py:105` 的裸字符串**（绕开注册表，登记）；REFUSAL 两块——`causation_error` 只有 explainer 读，`counterfactual_error` **写 2 读 0**。「零产生」是错的，3 个产生端都在 `scheduler.py`。

**普查顺带推翻方案的原假设**：`explainer` 不是死代码，是**外部调用的可剥离脚手架**（`scripts/` 与 e2e 调用，`themis/` 包内零调用）。所以缺的不是「四族没有 `bind`」——`read_as` 声明的是**读者的哪个问题**，而 `bind` 需要的是**哪个面负责**；ROUTE 恰好全落在 `analysis_report` 所以那张表能用，别的族散在不同面上。

**根因**：`QueryResult` **没有 `estimator_failure` 字段**，而结果 schema 顶层一直有它（enum 钉死、`stamp` 盖 kind、报告有分支、web 有分支）。识别层**返回**结果，不像估计器那样 raise 给 dispatch 接，于是没有地方放理由，只好往 `extensions` 写散文——**又一次是类型落后于 schema**（`blocks.py` 那轮同形）。实测代价：非二值 causation 时内核明明写下了「require a binary cause (x); got domain ['hi','lo','mid']」，主报告只说「该问题超出 Themis 可表达 / 可识别的范围」。

**物种两处都早就有，缺的只是让它到达**：反事实那族的三个子类在 `counterfactual_cell.py`（数据端）已各自映射到一个已登记物种，θ 端却写 `str(exc)`；非二值那条 `cause_or_effect_not_binary` 早在 `binary_do_risk.py` 用着——**我一度重复造了一个新物种，核实后删除**（㊵）。

**修法**：让**异常自己声明它的物种**（`__init_subclass__` 强制子类声明、不许继承一个为别的失败选的理由），两个 catch 点读同一处，`counterfactual_cell` 的三个分支塌成两个；`QueryResult` 补上字段并序列化；`refusals.block()` 成为信封块的单一出口（`record()` 改为调它，`_registered`／`_capped` 抽出，识别层没有构造器所以出口也验物种）；`scheduler` 三处改发 `estimator_failure`；`blocks.py` 删两个块并**删掉整个 REFUSAL 族**（没有块的 Family 是空壳不是分类）；explainer 两处改读真实理由（原句「已进入语法层，但当前仍未进入求解层」是内部实现语言，且描述的是阶段不是失败）；报告措辞「估计器」→「来自」。

**顺带修掉一句用户可见的假话**：同一份报告说「当前最强答案层级：**区间**」，而非二值的 Tian-Pearl 界根本没有定义。根因是上一轮引入的前瞻性 INTERVAL 分支没有读 `OUTSIDE_LANGUAGE`——**一个还没成立的问题没有形状可前瞻**。不加 causation 专用检查，因为同一句假话在 `counterfactual` 上正等着（它的 `interval_fallback` 也非 None）。证据链：`OUTSIDE_LANGUAGE` 只有 3 个产生端且都不带数不带界，唯一会加界的 `_attach_bounds_result` 第一条守卫就是 `status != NEEDS_INVESTIGATION`。

**基线（本条）**：4013 → **4024**（+11：三个求解器失败各命名一个已登记物种且三者互不相同、未声明物种的子类 import 期 `TypeError`；`QueryResult` 带上 schema 一直声明的那个字段；`refusals.block` 的形状与它对未登记物种的拒绝（识别层没有构造器，所以出口也验）；识别层拒答被 `stamp` 盖 kind、且复用数据端的物种；两个散文块与 REFUSAL 族均已消失；报告说出是哪个变量哪些取值且不再只说「超出可表达范围」；被拒的问题不再被许诺区间。另有两条旧测试改为钉事实而非钉载体，一条 schema 守卫抓出我漏删的 `counterfactual_error` 子 schema）。

**六张表一直在手工模拟的那件事，语言本来就有：`Refusal`/`Kind` 成枚举，mypy 进套件（2026-08-05，接上条）**：结构型 + 一个真 bug（用户可见）。

**起因是「是不是该重构成 Rust」**。分析结论是不该——按层量：`estimation` 26,467 + `verifier` 19,618 = 57%，正是最依赖科学计算生态、`causal-learn` 在 Rust 无对等物的部分；而六张表所在的顶层只有 5,405 行 = 7%，那才是 Rust 能白拿的。更关键：`verifier` 那 19,618 行的价值全在**故意重复实现**上（memory 记着一次实测，两份实现各自演化后收敛到同一个便利假设），而 Rust 的类型系统恰好诱导两份实现共享类型定义。**但分析查出一件真事**：这个仓库零静态类型检查（dev 依赖只有 pytest / pytest-cov，全仓无 `assert_never`）。六张表 + `bind` 一直在手工补一个从没装过的检查。

**先验两件事再动**（探针，不是推理）：`StrEnum` 成员能不能带 `kind`/`says` 而不变成成员——能；序列化会不会退化——不会，json / f-string / hash / dict 查找 / `==` 全等于裸名字，17/17。

**改法**：`Kind` 5 个、`Refusal` 69 个各成一个 `StrEnum`；258 处 `refusals.<NAME>` → `Refusal.<NAME>`（脚本改，成员体由现文件生成并逐条对账 value/kind/says 69/69 一致——**这一步的探针也自己错了一次**：我造的假 `Kind` 用大写值，于是 69 个 kind 全报「不一致」，㊶ 又一次成立）。塌掉三个只为「让模块能枚举自己」而存在的派生集合：`ALL`（类就是集合）、`KINDS`（同）、`BY_KIND`（唯一消费端是它自己的注册表测试）；`BY_NAME` 留着，因为「读比写宽」需要一个能返回 None 的查找。`@unique` 让「两个名字一个物种」成为 import 期错误——那本来是一条测试。

**信封仍然是数据**：enum 在三个地方各自抵抗这一点（pickle 回来查成员、`__copy__`/`__deepcopy__` 直接返回 self、不经过 pickle），所以三个 dunder 提成 `_EnvelopeName` 基类、两个枚举共用一条规则。**这是套件抓出来的**：我第一版只覆盖 `__reduce_ex__`，`test_a_species_is_the_plain_name_once_it_is_data` 立刻失败——那条测试写着理由，理由成立。

**`_KIND_ZH` 从表变成 `match` + `assert_never`**：要保证的是「读者那半边分类完整」，那是一个关于**分支**的断言，dict 装不下。运行时测试留着，因为它问的是另一半——每个分支是否真说了话，那是检查器看不见的。**实测这条链会咬人**：临时注入第六个 kind，`analysis_report.py:85` 立刻类型错误、指着 `assert_never` 那行。另外普查确认 `_KIND_ZH` 是**唯一**一张没有 `bind` 守着的词表消费端（另五张各有 `bind`；scheduler 里 16 处「blocks 键的 dict」是 1-2 条目的写点，不是表）。

**mypy 首跑就抓到一个真 bug，在活路径上**：`dispatch.py:5571` 的 `except EstimatorFailure` 用了一个模块全局里不存在的名字。**根因不是那一行漏写**——`EstimatorFailure` 在 dispatch.py 里是「每个函数各 import 一次」的约定，24 处函数内 import、模块级零处，第 25 个 handler 忘了；而 `except X` 的 `X` **只在异常发生时才求值**，所以从测试里看不见。端到端复现：让 aipw 按设计拒答，`themis.estimate()` 整个抛 `NameError` 而不是记下拒答（ipw / tmle 同）。修在约定上：一次模块级 import + 删掉 24 处；独立 AST 扫描全包（滤掉 builtins 后）确认只此一处、与 mypy 完全一致。

**顺带两件**：`formula_text` 的 `env` 声明为 `dict[str, str]` 却在 `"@pinned"` 这个魔法键下装 `set[str]`——**注释自己写着「不是标识符，所以撞不上任何 bind 名」，需要一个撞不上的键正是这个值不属于这张表的证据**；改成 `_Env(bound, pinned)` 两个字段（放宽标注会往 6 个签名扩散，比修好它更贵）。`_atom_pred` 的签名说不收 `None`，而函数体第一件事就是 `atom_dict or {}`。

**mypy 的范围是一张名单不是一个包**：全包首跑 660 findings / 64 文件（218 union-attr / 172 arg-type / 104 assignment / 77 index / 20 attr-defined / 19 var-annotated / 9 name-defined / …），那个数说的是「没标注」不是「坏了」，没人会读。名单从六张表 + `analysis_report` 起步（7 个文件，`--warn-unused-ignores` 下零 findings），并由一条测试守住「**凡写了 `assert_never` 的文件必须在名单里**」——否则那句话只是一条恰好可执行的注释（㊷ 同型：写下了 ≠ 有人读）。剩下的 findings 已登记逐条查（#329），`blocks.py` 同样改枚举已登记（#330，实测 143 处引用）。

**基线（本条）**：4024 → **4029**（+5：mypy 名单里的 7 个文件零 findings；缺一个分支的 `match` 被抓（`assert_never` 那条链的实测）；拼错的物种被抓；凡写了 `assert_never` 的文件都在名单里；这个内核没听过的 kind 不被硬塞一句话。另有三条旧测试改为钉现在还成立的那半边——「注册表收全了」和「两个名字一个物种」都成了 import 期错误，替它们的是「成员名和信封上的名字是同一个决定」）

---

### 一张白名单沉默地少保护了 62 个模块：那 25 条线索查完，闸口反过来（2026-08-05，接上条）

上条把 mypy 接进套件时，名单只放了七个文件，剩下的 findings 登记为「逐条查」（#329）。
查的结果不是 25 个问题：**1 个真崩溃 + 8 条真注解谎言 + 16 条误报，而那 16 条共用一个根因。**

**真崩溃在 `data_gap_report.py`，而且是这个仓库反复犯的那个错**：`_extract_dose_response_confounders`
读 `step.context`——`DerivationStep` 没有这个字段——然后去找 `adjustment_set` / `backdoor_set`
两个键，**全仓从来没有任何一步写过它们**（真名是 `backdoor_criterion` 步的 `inputs["z"]`）。
四行里两个互相独立的错误一起活着，说明它**从未跑对过一次**，不是写对了后来漂了。
根因不是手滑：`DerivationStep.inputs` 是一个裸 `dict`，键集由 `rule` 字段决定，而**没有任何东西
说出这个映射**（㉞：字段含义取决于另一个字段＝它没有一等表示），于是作者猜了一个形状，
而没有类型、没有测试、没有检查器能反驳。㉞ 的探针再一次准：**谁已经不得不知道这个形状？验证器。**
实测 `.inputs` 的读者 46 处，45 处在 `themis/verifier/` 里——**圈外只有这一个，也就是唯一一个猜错的**。
它活下来是因为语料里所有剂量响应程序都是裸 X→Y、全部 `needs_investigation`、derivation 为空：
插桩实测 55 次调用、进入该分支 **0 次**。加一个混杂 + 够用的 theta，`themis.run()` 当场抛
`AttributeError`。修完之后 `confounders_required` 第一次有了内容（`['tenure']`）——
这个字段此前每一次运行都是空的。

**8 条 `name-defined` 是「注解命名了本模块没有的类型」**，`scheduler.py` 里 7 个
`"tuple[Statement, ...]"` + 1 个 `FormulaExpr`。字符串注解和函数内局部变量注解都不求值，
所以从没炸过——**又是㊹ 那类「延迟求值的位置，测试看不见」**。真正值钱的是：把 `Statement`
import 进来之后，检查器第一次能读这 7 条注解，**立刻发现注解本身是错的**——写的是整个
`Statement` 联合，而实际元素全是 `SelectionNode`（三处调用点都在按它过滤，代码只读
`.affects` / `.source_population` 两个 `SelectionNode` 字段）。顺手把三处
`from ..types import SelectionNode as _SN` 的函数内 import 收成模块级一处（㊹ 修在约定上）。

**16 条误报共用一个根因，而且是老熟人**：一个变量装着判别联合，却按其中一个成员声明，
**判别信息另存在一个字符串里**——`estimator == "gformula"`、`estimator in ("aipw","tmle")`、
`chain[i] = ("clf", obj)`。三处全部改成按类型判别（`isinstance`），front-door 那个平行的
`"const"`/`"clf"` 标签直接删掉：**条目的类型本来就说了它是哪一种，标签是同一个事实的第二份记录**。
`_PreparedData.contract: object` 只是漏标（真类型 `DataContract`）。
`conditioned_collider_opens_path` 标着 `Atom` 而唯一的调用方传谓词字符串——
函数体只把参数当图的节点用，**这个仓库的图两种键都有**（scheduler 按 `Atom` 建、
data-gap 报告按 `str` 建），所以真正诚实的标注是一个节点 TypeVar。

**然后是比这 25 条更大的那件事：白名单的形状本身在骗人。** 量出来
**已经零 findings、却不在名单里的模块有 62 个**——名单里只有 8 个。pyproject 的注释写着
「清干净了就加进来」，但真正的门槛从来不是干净，是**没人去加**。
**白名单对自己漏掉了什么是沉默的，而要防的恰恰是没人想到要写下的那个。**
于是把闸口反过来：`files = ["themis"]`，另开一张 58 个模块的 `ignore_errors` 例外名单。
反过来之后——那张名单**只会缩短**、新模块**写出来当天就受保护**、清干净一个模块＝删一行。
守卫也跟着换了问题：原来问「写了 `assert_never` 的文件在不在名单里」，现在问
「**在不在被压住的名单里**」。**实测这道闸真的多保护了东西**：往
`themis/output/sample_size.py`（62 个里的一个）注入一个类型错误，套件立刻红——
在这次改动之前，同一个错误一声不响。

**基线（本条）**：4029 → **4030**（+1：带混杂且能出解的剂量响应查询，`confounders_required`
就是那一步 back-door 自己用的调整集。另有四条测试改写：名单变成「包减去例外」之后，
「配置里的模块零 findings」变成「包零 findings」，「凡写了 `assert_never` 的文件都在名单里」
变成「都不在被压住的名单里」）。包内 findings **643 → 605**，且逐条比对确认**没有引入任何新条目**。

**剩余登记**：58 个被压住的模块逐个清（头四个占 605 条里的 334：`verifier/verify.py` 195、
`verifier/rules.py` 62、`estimation/dispatch.py` 46、`runtime/scheduler.py` 31）；
`blocks.py` 改枚举（#330）。

### 一个块靠什么到达读者，从三句族注释变成一个必答字段——问出口的当天，同一族三个成员给了三个不同答案（2026-08-05，接上条）

上条的登记里有一条是「并排读五处 `bind`，验一验『系统有一等的词汇、没有一等的面』」。
**假设被证伪了**：那五处的差异在逻辑不在措辞——`routing.bind` 的消费者是执行层不是渲染面，
而且它是唯一返回**有序**元组的（消费者按序取第一条适用的，不做键查找）；
`blocks.bind` 的 `family`（来自单值的 `read_as`＝分区）与 `routing.bind` 的 `end`
（来自集合值的 `ends`＝覆盖）是两种集合算术；四句「沉默」写的是**三种不同事故**
（什么都没渲染 / 被 fallback 答成「成立」 / 内部 token 泄漏给读者）。
所以不该去建那张「面」表。但并排读量出了另一件真事，就是本条。

**现象**（三条，全部实测）：

1. `blocks.bind` 全仓**只被调用一次**（`analysis_report.py`，ROUTE 族）。`read_as` 承诺的
   「一个块不能在没有渲染器的情况下被加进来」，18 个块里只覆盖了 10 个。
2. 守着它的那条测试问的是「有没有模块**提到** `blocks.X`」——**产生端就满足它**。
   族外那 8 个块全过，而它们真实处在三种完全不同的状态：1 个账本（主报告确实读了）、
   5 个被别的东西承载、2 个只被**可剥离脚手架**（`explainer.py`）读到。
   **「被提到」正是这三种状态的公共部分，所以这条检查分不出来**——连我们自己都没分出来：
   那 5 个里的第三个是这次逼出字段之后才认出来的（见下），审计当时把它算在「只有脚手架」那一堆里。
3. 于是 causation 查询的报告长这样——问题行按 schema 问「必要性 PN / 充分性 PS /
   必要且充分 PNS」，答案节印一个 `**0.5**`。块里 `pn=0.5`、`ps=0.1111`、`pns=0.1`
   三个**具名**的数都在，报告给一个**不具名**的数。

**根因**：「这个块答的是读者的哪个问题」（`read_as`）和「它靠什么到达那个读者」是两件事，
只有第一件成了字段。第二件留在注释里，**而且写在族一级**——三句族注释各说一种机制。
但机制是**逐块**的：同一个 ASSUMPTION 族里，`assumption_ledger` 被主报告直接渲染，
另两个是 `result_orchestrator` 折进账本的。没有一等表示 → 无法检查 → 守卫只能退而问
「有没有人提到」。ANSWER 那句族注释更直接：它写的是「Read by `output.explainer`」——
**把病症写成了解释**。

**为什么是根因不是表象**：表象修法是给 causation 补个渲染器，挡不住第 19 个块。
更要紧的是，**把这个问题逼成必答字段之后，ANSWER 族三个成员给出了三个不同的答案**——
`counterfactual_cell` 根本不该由主报告渲染（它的产生端自己写着「Display copy」，
只在同时产出 `numeric_estimate` 的那条路上写，而 `answers.py` 的
`counterfactual_cell_bounds` 形状早已从 `numeric_estimate` 里把它渲染出来了，
所以是 `carried_by="numeric_estimate"`）；`scm_counterfactual` 只有一半是新的
（`target_value` 与 `numeric_result` 重复，它独有的是 abduction 出的个体扰动）；
只有 `causation` 是整块缺渲染。**只补渲染器，前两件一件也发现不了。**
theta 路径为什么会这样也随之清楚了：causation 与 scm_counterfactual 不经估计器，
没有 `numeric_estimate`，于是**没有任何答案形状描述过它们**，`answers.py` 那张表
按构造看不见它们。

**改动**：

- `Block` 增加必填字段 `carried_by`。`None` ＝「某个面为它绑了渲染器」，
  一个名字 ＝「别的东西把它呈现出来」，而那个名字只能是**已有表的成员**：
  另一个已声明的块，或 `query_result.schema.json` 的一个顶层字段。
  两种都是真的成员检查，不是散文。实测 18 个块：13 个 `None`、5 个被承载。
- `rendered_in(family)` 取代 `declared_as(family)` 当 `bind` 的成员集：
  被承载的块不该再被要求说第二遍，绑它反而是**第二次讲同一件事**（承载者先到读者手上），
  所以 `bind` 现在两向都拒。
- `bind` 记下**是谁绑的**（`BOUND: dict[面, set[块]]`）。**按面分桶而不是求和**——
  「有人渲染了」正是让这件事溜过去的那种检查，脚手架满足它。
  面的名字从调用栈上取（`sys._getframe(1)`），不让每个调用点自己写一遍参数。
- 那条半步守卫换成两条真守卫：声明 `carried_by=None` 的块必须出现在**主报告**绑下的集合里；
  声明了承载者的块，承载链必须终止于一个字段或一个自己有渲染器的块（带环检测）。
  **两个反例都构造过**：注入一个声称有渲染器却没有的块、和一个指向不存在的承载者的块，
  套件分别红在这两条上。
- 主报告为 causation 与 scm_counterfactual 各写一个渲染器（#313 一并做掉）。
  causation 答案节现在三个数各有名字，并说出它们由哪两个干预风险算来、那两个风险又从哪来；
  没声明单调性时改印界并说明**为什么没有点**（单调性是关于机制的假设，数据补不上，
  它的缺席是答案而不是窟窿）。scm 答案节带上 abduction 出的个体扰动与同一反事实世界下的其他变量。
- ASSUMPTION 族也走 `bind`（一个成员），`_render_assumptions` 从直接 `.get` 改成按族分派。
- 新答案分支排在「裸数」分支**之前**：那个裸数是**从块里摘出来的** headline，
  而 headline 说不出自己是三者中的哪一个。

**代价（当场声明）**：`read_as` 的族归属**没动**。把 `scm_counterfactual` 挪进 ROUTE 是硬凑——
ROUTE 说的是「识别模式」，abduction 是计算不是识别。它留在 ANSWER，渲染器把推导一并说出来；
代价是「怎么算出来的」那一节对 SCM 路径仍然是空的，登记为 #334。

**基线（本条）**：4030 → **4038**（+8：两条守卫各一条、`carried_by` 缺席即 `TypeError` 一条、
「记录说得出是哪个面」一条、「不许绑别人承载的块」一条，加上 causation 单调/非单调两条与
scm 反事实一条的答案节。）

**方法论沉淀**：(52)**一个可达性检查如果不问「哪个面」，脚手架就能替真读者签收**。
判据：①「有没有人读」和「有没有到达读者」差一个量词，而本档的三种状态
（真读者 / 被承载 / 只有脚手架）在前一个问题下**长得一模一样**；
②记录要**按面分桶**（㊷ 的可执行版本），求和会把脚手架计入；
③需要知道「谁做的」而调用方本来就有这个事实时，**从栈上取比让每个调用点重写一遍更可靠**
（㊹：必须在每个使用点重写的约定一定会漏一次，而这里漏掉会让守卫**默默变弱**而不是报错）。
(53)**「给同一族的所有成员建一个统一机制」之前，先逐个成员问那个问题——
机制是逐成员的时候，族一级的答案必然对一部分成员是假的**。判据：①本档三句族注释，
两句真一句假，而假的那句把病症写成了解释；②探针是**同一族内成员的产生端是否不同**
（ASSUMPTION 族：一个由 kernel 写、两个由 dispatch 写后被 orchestrator 折叠）；
③逼成必答字段之后，**答不出来的成员就是标错了的成员**——本档同一族三个成员给出三个不同答案，
其中两个是只补渲染器发现不了的。

**顺带量出、未做、已登记（#336）**：写 causation 渲染器时要把
`interventional_risk_provenance` 翻成中文，才发现这个词表**被列了七次，没有两次是同一个集合**：
schema 三处（`extensions.causation` 4 个 / `numeric_estimate.probabilities_of_causation` 3 个 /
`numeric_estimate.counterfactual_cell` 6 个）、`counterfactual_cell.py:96` 的
`RISK_PROVENANCES` 6 个、`verifier/rules.py` 两处（具名常量 6 个 + 内联字面量 3 个）、
`causation.py:107` 的行尾注释 3 个（字段是裸 `str`，且**这条注释是陈旧的**）。
差异**很可能不是漂移而是按容器分的合法子集**（两个产生端的词汇几乎不相交），
但**没有任何东西说出这件事**，那才是缺的表。而且
`tests/test_counterfactual_cell_numeric.py:721` **已经**把其中三处钉成相等、
docstring 还专门论证了为什么必须钉——**同一条纪律，七处里只施行了三处**。
消费端三份手写映射覆盖不同子集，我这轮又加了第三份。

> 更正：本段初稿写的是「产生端 `estimation` 4 个、集合写在行尾注释里、㉞ 的标准形态」，
> 并且**完全没提 schema**——两处都错。㊵（建一等事物前先在已有登记表里搜同义词）
> 这条规则我自己刚写完就没执行，代价是差点在七份登记之外造第八份。
> 同段初稿担心的「explainer 那个两分支 `else` 在说假话」**也不成立**：
> `result_orchestrator.from_dict` 是 `NotImplementedError`，估计层的信封在结构上到不了
> explainer（插桩实测该函数全语料 **0 次调用**）。但同一处 `dispatch.py:2393` 的注释
> 「the explainer reads extensions.causation」**是假的**，理由正是同一条——
> ㉕ 那类「拿一个结构上不可能消费的消费者来为自己辩护」的注释。已并进 #336。

**剩余登记**：**web 面对 theta 路径的答案与修前的主报告同病**（#335，实测
`verdict.ts:367` 只读 `numeric_estimate.probabilities_of_causation`＝数据路径，
`Verdict.tsx:15` 无估计块时回落到 `numeric_result.value`＝那个不具名的数）——
而 `BOUND` 按构造只能记录 Python 面，web 是 TS 面、在注册表之外，
**两条新守卫对它是沉默的**；`blocks.py` 改枚举（#330，实测 143 处引用）；
58 个被 mypy 压住的模块（#331）；「怎么算出来的」对 SCM 反事实路径为空（#334）。

### 声明了形状不等于声明了对的形状：更锋利的那半个答案，反而印得更不具名（2026-08-05，接上条）

上条修完 theta 路径的当天，同一个查询走**数据**路径仍然印一个不具名的数。直接复现
（20000 行、后门 `{z}`、`monotonic=True`）：

```text
## 答案
**0.4379**　（95% CI [0.4204, 0.4566]）
- 方法 `causation_plugin`，样本量 N=20000
```

问题行按 schema 问「必要性 PN / 充分性 PS / 必要且充分 PNS」。而**非单调**那一支是对的——
三个名字都在。**更锋利的答案被渲染得更不具名。**

**根因**：`SHAPES_OF["causation_plugin"] = (POINT, CAUSATION_BOUNDS)`。单调时
`numeric_estimate["point"]`（PN headline）非空，`shape_of` 按序取到 `POINT`；而
`POINT.carries` 自己写着「a single number for **the** estimand」——**causation 有三个
estimand，所以 POINT 对它从来就不成立**。缺的不是渲染器，是那个形状：
「三个各自具名的点」这个形状不存在，于是只能借用通用的那一个。

**为什么是根因不是表象**：形状表的守卫问的是**覆盖**——每个方法都声明了形状吗、
每个形状都有渲染器吗。`causation_plugin` 两个形状都声明了、都有渲染器、`bind` 全绿。
**覆盖型守卫对「贴不贴切」是沉默的。** 而同族的
`counterfactual_cell_plugin = (POINT, COUNTERFACTUAL_CELL_BOUNDS)` 恰恰**不是**同一个毛病：
一个反事实格确实就是一个数。这个对照说明病根在**「读者问了几个量」**，不在 `POINT` 本身，
所以修在形状表而不是在渲染器里加一个 `if method == ...`（那正是形状表建起来要消灭的东西）。

**改动**：
- `answers.py` 新增 `CAUSATION_POINTS`（`lives_in="probabilities_of_causation"`，
  `detect` = `pn.point` 非空——块两种模式都在，单调性买到的东西在**每个量的里面**）。
  `causation_plugin` 改为 `(CAUSATION_POINTS, CAUSATION_BOUNDS)`，`POINT` 退出。
- **三个入口绑同一个渲染器**：两个数据形状 + theta 的 `blocks.CAUSATION`。原来的
  `_render_causation_bounds` 与上一档新写的 `_answer_causation` 合并成
  `_render_causation`——它们本来就在说同一批名字，而各自只知道一半：一个知道置信带和
  调整集，另一个知道单调性买到的点和干预风险的来路。合并后信息取并集。
- 顺带一个原来说不出的区别：`ci_lower`/`ci_upper` 两个键**在两种模式下意思不同**
  （有点时是点的抽样区间，没点时是可识别集的外带），而决定它是哪一种的正是决定形状的
  那件事，所以渲染器按同一个条件分叉，不再需要第二份代码。单调那支现在还会说出
  **这个假设买到了什么**（「无单调性假设时只能给到 [a, b]」）——Tian-Pearl 界本来就不用
  单调性，所以那正是被替换掉的区间。

**基线（本条）**：4038 → **4041**（+3：形状表那条 fixture 级的回归——它带着
`point` 字段，改前必然渲染成 `**0.5**`；走真实管线的数据端两模式答案节；
第三条不是新写的——`test_the_web_reads_every_shape_the_kernel_can_answer_in`
按 `answers.ALL` 参数化，**新形状自动多出一个 case**，也就是 web 那一面当天就被问了
「你认不认得这个形状」，答案是认得：`lives_in` 与 `causation_bounds` 同为
`probabilities_of_causation`）。
另有一条既有测试**被改写**：`test_the_sharper_shape_wins_when_monotonicity_supplied_one`
原来断言「两个双模方法都把 `POINT` 放在第一位」——**那条断言本身就是这个 bug 的书面形式**。

**方法论沉淀**：(54)**覆盖型守卫（「每个 X 都有一个 Y」）对贴切性是沉默的——
「声明了形状」和「声明了对的形状」是两件事，而一条把错误声明写进断言的测试会让它更难被发现**。
判据：①探针不是覆盖而是**算术**——读者问了几个量、这个形状装得下几个（`POINT.carries`
自己写着「a single number」，而问题行问了三个）；②**同族里那个「看起来一样但其实正确」的
兄弟就是判据**（反事实格确实是一个数），它把病因从「`POINT` 用错了」收窄到「这个估计量有几个
被问到的量」；③修在**词表**而不是在渲染器里加方法名分支，否则等于把词表要消灭的
「按字段名探形状」又请回来一次。(55)**为 A 做的插桩会暴露 B——量「同一个块出现在哪些容器里」，
就会看见「同一个缺陷还留在哪条路径上」**。判据：本条不是查它查出来的，是查
`interventional_risk_provenance` 时看见 `extensions.causation` 有 15 次带着
`backdoor_adjustment`（＝数据路径也写这个块），才回头问「那数据路径的报告说了什么」。

### 「验证」那一节数得出推导有几步，「怎么算出来的」那一节说不出那几步是什么（2026-08-06）

登记的 #334 说的是「SCM 反事实路径这一节仍为空」。插桩跑全量实测，**它是六种
query kind 里的一种**：72 份报告里 **22 份（31%）这一节整个缺失**，其中 **14 份是
带着推导链缺的**（另外 8 份是拒答 / 尚无答案，空得合理）：

```text
assoc              6   d_connected_via_open_path / d_separated
causation          5   probabilities_of_causation_tian_pearl / numeric_causation_estimate
cause              1   cause_via_directed_path
effect（IV）        1   iv_criterion_check → numeric_iv_estimate
scm_counterfactual 1   scm_abduction_action_prediction
```

**根因**：这一节绑的是 **ROUTE 族的块**，而块只在「图被识别成某个模式」时才被写
出来。其余每一种得到答案的方式——d-分离判定、Tian-Pearl 公式、abduction-action-
prediction——把路线记在 `derivation.steps[*].rule` 里，那是**每个有答案的结果都有的
一等字段，而这一节从不读它**。

**为什么是根因不是表象**：表象修法是「给 SCM 加一个 ROUTE 块」。判据三条——
①那样只修 14 份里的 1 份；②SCM 的路线材料**已经在信封里**（`abducted_noise` 等），
再加一个块是把同一份数据写两遍，而 `read_as` 是单值的、块也确实只该回答一个问题；
③**这正是 `formula` 那次的同型**——`_render_route` 自己的注释写着 `formula`
「is a field rather than a block, so the binding above never looked at it」，同一个
坑第二次（㊴：按某一类事物建的表，会漏掉不属于那一类、但同属一个面的东西）。

**最锋利的物证**：「验证」那一节一直在说「此答案携带一条**可独立复核的推导链**
（N 步）」——`_derivation_step_count` 存在、**它数了步数，却从不说这 N 步是什么**。
两个独立通道以同一种方式失败，说明缺的东西在两者的下游。

**改动**：
- 新建 `themis/output/derivation_glossary.py`（与 `assumption_glossary` 同址同型、
  同样的默认约定）：**58 条产生端会写的规则各一句话**，说的是这一步**做了什么**，
  不是验证器复核了什么——读者在读一份配方，不是在审一份审计。凡是碰了数据而不只是
  碰图 / θ 的，句子里说出来。
- `_render_route` 渲染推导链，**每个有推导链的结果都渲染**，不是「块什么都没说时
  才兜底」——兜底恰好会藏住这件事：块只说了一点点的路径会一直看起来像说全了。
- 顺序：模式块 → 估计式 → 推导链。前两者是细节（哪个模式、在哪个集合上、什么表达
  式），链是骨架。
- `data_gap_report` 那句直接把 `rule` 印给读者的话换成同一张表。

**这一节现在说什么**（实测，真管线）：

```text
effect（后门，数据）
  - **估计式**：`Σ_z [ P(y | x, z) · P(z) ]`
  - **推导链**（每一步都可被独立重导）：
    1. 在图上验证调整集满足后门准则：阻断全部后门路径，且不含处理的后代
    2. 在数据上按后门公式求平均因果效应

SCM 反事实（结构路径）
    1. 按你声明的结构方程系数：从该个体的观测值反推它自己的外生扰动（abduction）、
       施加干预（action）、再沿方程重算目标（prediction）

SCM 反事实（数据路径）
    1. 结构方程的系数没有声明，改由每个节点的 OLS 从数据拟合，再做
       反推扰动-施加干预-沿方程重算
```

最后那一句顺带补上了另一个洞：**「这些结构方程是你声明的，还是从你的数据里拟合
的」这件事原来谁都读不到**——数据路径往信封写了 `estimated_from_data: True`，
**一个写入者、零个读者，schema 里也没有**。现在这个事实由两条规则的名字承载（两条
路径本来就是两个 rule），到达了读者。那个布尔量因此成了冗余字段，**已登记**、未删
（删信封字段是另一个决定）。

**守卫（六条，各自构造反例见红）**：①产生端写的每个 rule 都得有句子（AST 走遍
`DerivationStep(rule=...)`，不用 grep——同一个字符串在验证器消息、缺口启发式、
docstring 里都出现，文本搜索既会高估也会低估）；②词表里不许有没人发出的句子；
③两条规则不许共用一句话（共用了读者就分不出链里的两步）；④**任何带推导链的结果，
这一节不许为空**（按 58 条规则参数化）；⑤步骤按运行顺序说；⑥链排在模式与估计式
之后。

**声明的取舍 / 未做**：`data_gap_report` 那句改动**测不了**——插桩跑全量，那条分支
**0 次到达**。它是为 `unidentifiable_via_backdoor` 写的，而 Tian 接线之后没有任何
产生端再发这条规则，所有不可识别的情形都从上面的 hedge 分支离开。**0 的意思是「没人
来」不是「不会漏」**（㉙），所以句子留着、并在代码里写明它当前不可达；「那条死分支
＋ `test_phase10_gap_kinds.py:73` 那句已过时的 docstring」**已登记**，删死分支是另一
个 slice。

**基线（本条）**：4078 → **4200**。

**方法论沉淀**：(60)**「有几个」和「是哪几个」是两个问题，而一个面可能只答得出前
一个——这种半答是最难看见的缺口，因为它读起来像已经答了**。判据：本档最锋利的物证
不是那一节为空，是**另一节说「（N 步）」**：`_derivation_step_count` 存在、
`step["rule"]` 无人读。找法是扫「报告里出现的计数」，逐个问「它数的那些东西，有没有
哪一面把它们列出来」。(61)**登记条目给的是一个实例，不是缺口的大小；动手前先按「同
一条判据」把全量扫一遍，denominator 常常大一个量级**——#334 登记的是一种 kind，实测
是六种、14 份报告；(56) 的「先数分母」在这里换了个形态：分母不是「表有几行」，是
**「这条判据在真实语料上被违反了几次」**，而那要跑起来才知道。

### #530 一个叶子的名字有没有意义，不是它嵌得多深的事（2026-09-02）

**现象（端到端跑出来的）。** 因果层级最高那一阶——归因——的两个块，**十三次伪造，
十三次接受**，没有一次碰到任何估计器：`counterfactual_cell.lower` 从 0.0 改成 0.4、
`upper` 从 1.0 改成 0.6（**这个块的答案就是这对界**，整对换掉），`p_y_do_x_cf`、
`p_y_do_x0` / `p_y_do_x1`、观测联合分布的四个格、**`monotonic`（它决定用哪一套界的
公式）**、调整集，以及「这是四格里的哪一格」那四个索引。

**根因假设。** `verify_numeric_display_agrees` 早就在走信封的每一层，问那个不需要懂
任何估计器的问题：**两边都出现的名字，指的必须是同一件事**。但在最外层以下它只问**一种
拼法**——「块名 _ 叶名」。这条拼法的理由是对的：一个答案报告自己的那些词，多半是**相对
于承载它的那个答案**的——`ps.ci_lower` 是充分性概率的区间，步骤里的 `ci_lower` 是这次
运行的，把两者相比等于说一份诚实的信封是两次不同的运行。**把这句对的话读成一条关于
「深度」的规则，才是代价所在。**

**为什么是根因不是表象。** `pn.lower` 是被押住的——纯粹因为它比别人**多嵌了一层**，
拼出来的 `pn_lower` 恰好撞上步骤记的那个名字。而 `p_y_do_x0`、`observed_x`、反事实
单元格自己的 `lower`，**每一个在整个信封上都只有一个意思、每一个都被平铺记在步骤里**，
却全都躲在一个任何步骤都不会写的拼法后面。**押没押住是拼写的巧合。**

**结构性改动。**
1. **裸名作为后备拼法，且仅当这份信封上只有一个叶子答应这个词。**「相对还是绝对」是一个
   关于信封的问题，而信封自己回答得了：三个块说 `ci_lower`，一个说 `p_y_do_x0`。有第二个
   主人就什么也不问——**歧义不是分歧**，而普查是让这份沉默保持可见的东西。
2. **解包递归进序列**：一个由「被序列化的东西」组成的序列也是一个。原来停在外层容器上，
   而它的注释写着不会——于是按时间分段记的混杂集合，被拿「名字」去比「序列化后的原子」。
3. **挡在路上的那件事：一个事实，一种形状。** 两条归因路线把调整集**逗号拼成一个字符串**
   记进推导，注释写着「序列化器不接受字符串元组」。**那句话早就不成立了**——序列化器自己的
   文档字符串就记着当初为什么改：「拒绝列表逼得生产方把集合拼成一句话，于是一串记号变成了
   一个句子，而句子需要一种语言。」现在记名字本身；两处验证器里各自 `split(",")` 的读回
   合并成一个 helper。**一个拼起来的字符串分不出「两个变量」和「一个名字里带逗号的变量」。**
4. **那四个索引，任何步骤都没记**——它们是**问题**不是记录。所以押到 query 上：把原来只读
   effect 一种问法的 `_asked_value` 泛化成**按问题种类的一张表**（effect 说出一个值，
   counterfactual 说出四个）。`factual_y` 的**缺席本身是一个答案**（证据里没有事实结局 ⇒
   这个格子变成 ETT 恒等式，是另一个量），所以它被比较而不是被跳过。

**声明的取舍。** 没有去写「从块自己的证据把 Tian-Pearl 那对界重算一遍」。那个恒等式**已经
有人算了**——从推导链记的那一份；再写一遍是两条验证器规则查同一个恒等式，那是冗余不是独立。
证据不再是装饰，是因为**它现在被押到了算这对界的那一份记录上**。

**核实方式。** 二十一条：九条伪造证据、两条整对换掉答案、四条把单元格说成另一个格子、
一条「缺席也是答案」、一条**误报护栏**（`pn`/`ps`/`pns` 都带 `ci_lower`，这条规则必须在
那里保持沉默，而且是**因为歧义**而不是因为哪里写了个名字）、序列解包与两条纵向混杂集合、
以及一条钉住调整集现在以名字的形状旅行。四十四种诚实形态**一条不拒**；快照里那两对用
`--only` 定向重采，同程序、同数据指纹、同样本量。

**账。** 宣告的未押住叶片 **103 → 81**，关掉 **22 片**。基线 11670 → 11691，skipped 236 不变。

### #529 一条重算覆盖的是它审的那个块，还是它站的那条分支（2026-09-02）

**现象（端到端跑出来的）。** `mediation_logit_imai` 的答案自己说这个发现是
**fragile**——「一个 RR 1.58 的未测混杂就足以把它解释掉」。把 `e_value` 改成
99.0、`interpretation_band` 改成 `very_robust`，**`themis.verify` 接受**。
`e_value_ci_bound`、`risk_ratio`、`band_basis` 同样接受；`mediation_linear_imai`
四项接受。**其余十五种带这个块的形态，五项全部正确拒绝**——同一个块、同一条规则、
同一次编辑距离，拒不拒只看这个答案是从哪条路走来的。

**根因假设。** `verify_e_value` 的守卫是
`if num_est.get("sensitivity_analysis") is not None`——一句**关于信封的话**。但它
站在 `kernel.py` 那条按 `status == "numerically_solved"` 选中的路由分支**里面**。
mediation 的结果是 `structurally_solved`，走另一条分支，永远到不了它。同一条分支里
还挤着**十四条同型的重算**（混淆矩阵求逆、SIMEX 阶梯、Sargan 检验、每个角上的风险、
剂量反应曲线……），每一条的守卫都是「方法叫什么」或「块在不在」，**没有一条是关于
走哪条路由的**。覆盖面 = 那条分支够得着的形态集合，而不是 = 带着这个块的形态集合。

**为什么是根因不是表象。** `verify_mediation_numeric` **已经被手抄到两条分支上**——
有人发现过一次「这些块两条路都会挂」，就地补了第二份抄件。第三条路就要第三份抄件，
而漏抄的时候**没有任何东西会说话**：门照常返回，读者看到一次干净的运行。所以缺的不是
某一句调用，是**「这条重算是关于谁的」这件事没有被写下来过**——它只存在于「当初谁在
哪条分支上加的」。

**结构性改动。**
1. **十六条重算成为一张表**，每一行声明它审的是**什么**：一个方法名、一族方法名前缀、
   或者一组块名——**三样都是写在 `numeric_estimate` 上的事实，没有一样是关于分支的**。
   走表的那一遍**在整个 kind 分派之外**，每个结果都会经过。
2. **表是唯一的入口，而且这一点被钉住。** 一条 AST 闸走 `kernel.py`：表里点名的规则
   **在源码里一次都不被直接调用**（只经由 `row.rule` 到达），需要转接的那一条则**恰好
   被调用一次**——就是那个转接器。**往分支上手抄一句调用，当场红。**
3. **每个选择器都必须指到 schema 声明过的东西**（方法在那 49 项闭枚举里、块在那 82 个
   声明属性里、前缀至少匹配到一个方法）。再加一条反向闸：**没有任何一行是死的**——
   每一行都至少被一种真实形态选中。schema 那条挡改名挡不住的那半，这条挡：一个仍在
   schema 里、但生产方早就不再产出的名字，匹配不到任何东西，而**匹配不到和没查出问题
   在门上长得一模一样**。

**一处必须说清的取舍。** 这一条**没有**去建「枚举里的每个方法，要么有一条重算、要么
被声明为不需要」的全覆盖账本。那是**另一句话**（哪些方法配得上一条链外重算），我没有
量过它；这次量到的缺口是**块跨路由**，账本该覆盖的是块而不是方法。普查是让这一半保持
可见的东西。

**一处如实的边界。** `ovb_sensitivity` 和其余按块触发的几条，今天**没有**任何一种形态
把它们挂在一条不重算的路由上——它们的暴露是**潜在的，不是量出来的**。这次一并搬走是
因为它们和 E-value 是同一族、同一个理由，不是因为各自都有一个反例。

**核实方式。** 五十九条：E-value 的四种伪造**问每一种带这个块的形态**（覆盖面就是缺口
本身，只挑一种形态的测试会把缺口原样复制一遍），OVB 同理；一条测试断言那些形态**确实
跨着不止一个 `status`**，否则上面那一片只是一次单路由扫描换了身衣服；三条结构闸。
四十四种诚实形态**一条不拒**。

**账。** 宣告的未押住叶片 **111 → 103**，关掉 **8 片**（两个 mediation 形态的整个敏感性块）。基线 11611 → 11670，skipped 221 → 236（伪造按形态×字段参数化，某形态不记某个字段时跳过）。

### #528 取景不是校正块的属性，是每一个块的属性（2026-09-02）

**现象（端到端跑出来的）。** 十次伪造，十次接受，没有一次动了任何一个数：
`decomposition.cde.reference_control.mediator_level` 和 `reference_treated`
的那一份，从 0 和 1 一起改成 **7.0**——「把每一个中介都按住在 7」——两行的点
估计一个字都没动，**接受**；`four_way_decomposition.scale` 从
`risk_difference` 改成 `risk_ratio`（四个加数还是那四个差，读者被告知它们是比），
接受；`four_way_decomposition.cde_mediator_reference` 从 0 改成 7，接受；
`interaction.order` 从 2 改成 9，接受；五个容器里的 `reference`——那句「这个分解
按谁的定义拆的」——统统换成 `"x"`，接受。

**根因假设。** #526 说的是「校正块的算术被审了，它的取景没有」，于是它做成了
`correction_frame_rules`：**按块的家族划的边界**。但取景不是校正块的属性。重算
读旁边的标签当**输入**：设计矩阵有哪几列、变量取哪些值、风险是关于哪个值的、
**中介被按在哪一档**。当成输入读，一个标签就不可能错——这句话对分解块、对联合
对比、对任何带着重算的块，一字不差地成立。

**为什么是根因不是表象。** 最锋利的一条在**同一个文件里**，相隔三十行：独立的
受控直接效应曲线一直是**读它自己那一行写的档位**再重算的；而联合分解的两行，
档位是**写死在规则里的 0 和 1**——于是一行被改标成 m\*=7，继续满足着一条关于
m\*=0 的检查。同一件事、同一个人、同一次编辑距离，一个读了一个没读，说明缺的不是
某条规则而是**「取景」这个类别本身没被当成类别**。

**结构性改动。**
1. **模块改名成它真正的主语**：`correction_frame_rules` → `frame_rules`、
   `verify_correction_frame` → `verify_frame`、`_RULE` → `frame_check`。同时
   加上第六种主张：**「这是本系统定的一个常数，块里露出的是它的一份拷贝」**。
2. **重算读块自己写的档位**：`CDE(m*) = beta_x + m* · sum_j gamma_j` 对每一个
   m\* 都成立，一般形式和写死 0/1 的形式是同一个形式——**要写的一直是一般的那个**。
3. **引用做成登记表，而且对 schema 全覆盖**：一条测试断言登记表的键**恰好等于
   schema 声明的每一条 `reference` 路径**（走 schema 走出来，不是手抄），另一条
   走 AST 断言**仓库里每一个写在 `reference` 键下的字面量都在登记表里**。所以
   「哪个容器带引用」不再是谁记得的函数——**schema 声明的那天就被覆盖**。
4. `interaction.order` 是联合对比的**元数**：它必须等于那个对比自己列出来的处理
   个数。

**登记表当场找出来的一件真事。** `extensions.scm_counterfactual.reference` 在仓库里
有**两份合法的文本**：调度那一份和分派那一份，后者多一句「; coefficients fitted by
per-node OLS」。所以每条路径登记的是**一组**可接受的文本而不是一句——押住的是「这个
容器只会说这几句里的一句」，而不是硬把两处不同的话说成同一句。

**声明的取舍：这一族还剩什么。**
- `controlled_direct_effect.levels_observed`（「这些档位是数据里真有的，还是外推的」）
  仍然可以翻面且被接受。**没有第二份记录说得出档位是不是从数据里来的**——要押住它，
  得让估计层把「这些档位来自哪里」记下来，那是另一件事的开头，不是这一条的边角。
- 引用的八条路径里，快照能走到的只有六条；另外两条挂在这套形态不产生的结果上，所以
  它们是**在规则上逐条问**的——一个没人能到达的引用，正是值得押住的那一个。

**核实方式。** 四十二条：四十四种诚实形态先过（一条不拒）；九条伪造逐条撞门，并且
断言**是这条规则拒的**（多数伪造会先撞上别的重算，「门拒绝」和「这条规则拒绝」是两句话）；
登记表的两条全覆盖闸；档位缺席由 schema 那一层挡下——那条测试从外面钉住它，因为
`mediator_level` 一旦不再必填，上一条测试的主语就被悄悄拿走了。

**账。** 宣告的未押住叶片 **125 → 111**，关掉 **14 片**。基线 11595 → 11611，skipped 221
不变。

### #527 判决 = 量出来的数 + 一条线 + 结论，#524 只押住了第一样（2026-09-02）

**现象（端到端跑出来的）。** aipw 的答案说 4000 个单位里 1453 个（36.3%）落在重叠带外，
把 `propensity_overlap_violation` 这条警告**整条从 gap report 里删掉——`themis.verify`
接受**。读者看到的是一次干净的运行。同一批答案里：`outcome_saturation.threshold` 从 0.10
改成 0.90（「一成以上饱和才警告」变成「九成以上才警告」），接受；`fitted_overlap.band_lower`
从 0.05 挪到 0.0，接受；`propensity_summary.floor` 从 0.01 改成 0.005（于是「多少单位被
截断」在说另一件事），接受。

**根因假设。** 一个诊断判决是**三样东西**：从拟合里量出来的数、系统画的那条线、以及两者
得出的结论。#524 押住了**第一样**的算术（份额是计数之比、范围出不出带与计数一致、两个块
的原始范围相同）。**线**在答案里只有块自己写的那一份；**结论**（那条 gap）在答案里只有
gap report 自己写的那一份；两份之间没有对账。

**为什么是根因不是表象。** 这一层做四个判决，其中**恰好有一个**是有账的——账本的 positivity
结论从 `fitted_overlap` 重读一遍（那是刻意设计：让判决成为一次**披露**而不是一次**主张**），
所以动 `fitted_overlap.threshold` 会被拒。**同一个系统、同一件事，一个接了三个没接**——
说明「结论必须能从它的证据重新读一遍」这件事是**逐个手工接的**，覆盖面是「谁记得接」的
函数。这跟 #525 同型：覆盖面应该是**信封形状的函数**（哪些块记了诊断），不是记性的函数。

**结构性改动。**
1. **线成为一份词汇表。** 验证器复述一份（不 import 生产方——读着被查的那个数去查它，是
   按构造同意，什么也没押住），一条测试把两份钉成相等；**凡答案里露出判决线而不在词汇表
   里的对象，当场拒绝**——一条没人登记的线就是一条没人核过的线，而在门上「没人登记」和
   「不需要核」是同一种沉默。这一走查**问信封里的每一个对象**，按它自己那把键的名字去查
   登记表，序列的每一行也照问。
2. **每个记录在案的诊断，它的结论必须能从它重新读一遍。** 凡带着 `share_outside` 和
   `threshold` 的块，它喂养的那条警告在不在，就是「份额有没有过线」这句话，**两个方向都
   问**。少报那一侧是危险的那一侧：一条根本不存在的警告，看起来跟一次干净的运行一模一样。
3. **分层支持那三个数是一件事的三种说法**：多少格、多少格两条臂都有、有多少比例的样本坐
   在只有一条臂的格里。单臂格至少装着一个单位，所以份额为正当且仅当有格是短的；而有格是
   短的那次运行，就是这个条件被违反的运行——必须有那条警告。

**两种线，两种押法，判据是「这条线是谁画的」。** 带和阈值是**系统**画的，答案之外没有第
二份记录，所以唯一诚实的副本就是那个常数、复述一份。而**截断的地板是调用方可以画的**
（估计器专门记了「是不是调用方点的」），**把它押到常数上，等于因为一次运行照着被要求的
样子做而拒绝它**——那是误报，比它闭掉的洞更糟。这一条改成押到**账本**上：那里本来就有
一条读者被要求接受的前提，写着同一个地板和同一个计数（`propensity_clipped_to_floor_
{floor}_on_{n}`），而**从来没有任何东西把它和旁边那个块对过**。所以它是**读**出来的不是
**拼**出来的——那个 id 的格式属于写它的人，这条规则关心的是里面那两个数，在这里重拼一遍
会让一次改格式看起来像一次关于截断的分歧。顺带把 `n_trimmed` 也押住了：那是我原本已经
写进「关不掉」的一片。

**一处必须说清的细节：为什么「块在 ⟹ 警告 = 过线」是对的。** 重叠这个条件有**两个证人**
——调整集能枚举时数「有几个格只有一条臂」，不能枚举时看拟合出来的倾向得分——**两个证人报
同一个 kind**。它们不会同时说话：数格子的那个一旦发难就当场返回，在任何模型被拟合之前，
所以**信封上有那个拟合块，本身就是「另一个证人没话说」这句话**。

**一处自己给自己找出来的盲点。** 走查的第一版是「从一个 dict 走到它的孩子」，于是**一条
直接坐在序列某一行上的线永远不会被看到**——而它的注释写着「at any depth」。今天没有任何
形态长成那样，所以没有一个测试会红。**要修的是那句话而不是覆盖面**：一条关于覆盖面的规则
自己留着一个没人量过的盲点，正是这个仓库反复找到的东西。改成走查每一个对象、按它到来时
那把键去查登记表，四条测试把「序列的一行」「估计本身」「两层以下」「一个登记过的块出现在
下一层」逐个钉住。

**声明的取舍：这一族还剩什么。**
- `outcome_saturation.p_min` / `p_max` ×4 与 `fitted_overlap.p_min` / `p_max` ×1。一段拟合
  范围的两端是**数据的事实，答案只记了一次**。能押住它们的只有带和计数（已押）：带外计数
  为零就意味着两端都在带内。**带内它们仍然自由**，而没有任何第二份记录能说它们该是多少。
- 这一条没有去碰 `stratum_support` 与拟合块**同时**出现时谁该说话的问题（今天由生产方的
  控制流保证，规则依赖它而没有独立复核）。

**核实方式。** 二十七条：四种形态诚实先过；六条挪线；五条未登记／错位的线；两条删/造警告
（饱和那条这套快照里从来没触发过，所以是**把每个数一起挪到它该警告的状态**再删警告——算术
照旧通过，缺的只有那句话）；三条分层支持；四条截断；外加**一条专门的反误报测试**：一个地板
0.2 而账本同样写着 0.2 的运行，必须被接受。

**账。** 宣告的未押住叶片 **153 → 125**，关掉 **28 片**。基线 11568 → 11595，skipped 221
不变，mypy clean（181 个源文件）。

### #526 校正的算术被审了，它的取景没有（2026-09-02）

**现象（端到端跑出来的）。** `regression_calibration.exposure` 从 `"w"` 改成 `"z"`——答案
于是宣称它校正的是协变量而不是暴露——`themis.verify` **接受**。同一族里 `design_vars`
改名、`states` 换成另一组取值、`target_value` 从 `true` 改成 `false`、
`sufficient_statistics.n` 改成别的数、`out_of_simplex` 从 false 翻成 true，全部接受。六种
方法五个块，**48 片叶子可改而过门**；其中凡是「起名字」而不是「记数」的那些，**改掉它，
页面上一个数都不动**。

**根因假设。** 每种校正都有一支验证器，从块自己的 `sufficient_statistics` **把那个数重新
算一遍**。而它读这些标签时，标签是**重算的输入**：哪几列、哪些取值、风险问的是哪个值、
目标在列表里的第几位。**当成输入读，一个标签就不可能错**——改掉它，算术会重新导出另一
个数，那个数**在每一处都和自己一致**，于是每条规则都通过，而答案回答的是没人问过的
问题。

**为什么是根因不是表象。** 不是「某几个字段忘了查」。这一族每加一种校正都会带来同一批
标签，而每一支新验证器都会以同样的方式读它们——因为**「从充分统计量重算」这件事本身就
要求把标签当参数**。缺陷是这条读法，不是一张漏掉的字段清单。它跟前两条是同一个病的第三
面：#522 是规则只问最外层键，#525 是生产方照名单挂，这次是**规则把主张读成了参数**。

**结构性改动。** 一支新的独立验证器 `verify_correction_frame`，把标签当**主张**问，并按
主张的**种类**组织，不按块名：
1. **信封已经带着的名字**——暴露、设计矩阵的列、调整集、样本量。
2. **程序已经声明的取值**——变量取哪些状态，查询问的是结局的哪个值。
3. **旁边那张列表里的位置**——`target_index` / `exposure_index` 指的必须是它自称指的那个。
4. **旁边那些数决定的事实**——校正后的风险有没有跑出 [0,1]，和 `out_of_simplex` 是同一
   件事；两个方向都问，因为「少报」和「没得报」在页面上长得一样。
5. **对象自己的性质**——凡自称是误分类通道的矩阵，**每一列是一个分布**（真值为 j 的单位
   一定被记成了某个东西），旁边记的行列式必须是它的行列式；逐格通道表的每一行是一个格，
   格坐标取的是程序给的值，两行不能是同一个格。
6. **凡记了两遍的，另一遍**。

**第 2 条补上的是「一个问题不只由变量名定义」。** `verify_answer_names_its_question` 把
答案的**变量名**押到了查询上——treatment/outcome/mediator。而一个 `effect` 查询还点名了
**结局的取值**，离散校正报的正是那个取值的风险。**名字那半被押住了，值那半没有**：块、
它自己的记录、指进去的下标可以一起说「这是 y=False 的风险」，而查询问的是 y=True。

**第 6 条不是关于校正的，也没写成关于校正的。** 信封上凡是带着自己
`sufficient_statistics` 的块，两边就是**同一次运行写了两遍**：统计量那份被重算押着，块
自己那份是**给读者看的**，此前没有任何东西把两者拴在一起——一个块可以从它从没展示过的
设计完美重算，再展示一个它从没用过的设计。哪些块是这样的，是**信封形状的事实**，不是这
里维护的名单。**这一问关掉了 48 片里的 19 片，而且它不需要知道其中任何一片是什么意思。**
（今天带统计量的块有 12 个，6 个是校正、6 个不是；那 6 个非校正块只记统计量、不重复展示，
所以这一问在它们身上**问了，并且找到了「没有」**——那是一个回答不是一次跳过，等哪天其中
一个把它审过的事实也展示给读者，它当场变成检查。）

**真正要测的是「同时改掉每一份拷贝」，因为普查问不出这个。** 普查一次只弯一片叶子。取景
规则针对的伪造是：块、块自己的记录、指进去的下标**一起挪**，挪成一个内部完美自洽的故事
——算术重算得出、两份拷贝相同、下标指得没错——**唯一和它冲突的是问题**。三条这样的测试
写在案：`states` 一起改成变量没有的取值、`target_value` 连同下标一起改成另一个结局值、
设计的两份拷贝一起改名。

**一处必须说清的顺序。** 这些伪造里大多数会**先**撞上重算（改了状态集，算术当然导出别的
数），所以每条测试同时断言两件事：门拒绝，**并且这条规则以它自己的理由拒绝**。前者是调用
方拿到的，后者才是这条测试说的话；而「同时改每一份拷贝」的那三条，正是重算满意、取景不
满意的那一档。

**一份查找器收成一份。** 「这个结果回答的是哪个查询」原本是 `program_copy_rules` 的私有
`_query_of`。取景规则要问同一个语句的**取值**，于是把它升成包内公开的 `query_of`，一份。
按「谁在做同一个判断」数副本——一次查找抄两遍，就是两处会各自走味的地方。

**量过之后决定不加的两条。**
- **「记下来的矩确实是矩」**：`cov_design_yᵀ Σ⁻¹ cov_design_y ≤ var_y`（设计解释不了比结局
  自身更多的方差）是真不等式，诚实答案上成立。但它**只从下方约束 `var_y`**——把 `var_y`
  调大照样通过——所以关不掉那片叶子；而且它说的是「这些矩是矩」，属于记录本身而不属于
  取景。
- **`det_joint = det_exposure² · det_outcome²`**（Kronecker 积的行列式）成立且量过，但
  `det_joint` 已被第 6 条押住，两条规则查同一批伪造只是冗余。

**声明的取舍：还剩 7 片，每片有它的理由。**
- `measurement_correction.form` ×3。这三条路线是**非参数标准化，没有假设任何函数形式**，
  所以 `mechanism_audit` 对它们正确地保持沉默——而那正是另外四个块的 `form` 被押住的地方
  （块上的名字和审计里的名字是同一次选择记了两遍）。这三个名字因此**无处可押**；押成
  「方法名→形式名」的表，就是一张会对下一个新方法沉默的化石。诚实的修法在生产方一侧
  （给结局通道那条一个显式的 `side`，并让形式名成为可审计对象），**本条没做**。
- `measurement_error_correction.out_of_simplex`。这条逐格路线**报了判决、没展示它所判的
  风险**——块上没有 `risks`。这里没有可比的东西，规则据此不作声，把叶片留在普查看得见的
  地方。**「一个读者看不到其所指之数的警告位」本身是个发现**，也在生产方一侧。
- `sufficient_statistics.var_y` ×2。这两种形态里 `var_y` **不进算术**（回归校准和结局通道
  都用不到它），而**没有任何东西能从上方约束一个结局自己的方差**。
- `simex.error_variance`。声明的 σ²_u 是这次校正的全部许可证，而**整个答案只在这一处记了
  它**——假设账本说「已知且固定于 w」，说的是**哪个变量**，不说**固定在几**。没有第二处，
  就没有东西能反驳它。

**核实方式。** 十四条伪造，每条先确认诚实答案通过（否则测试会因为错误的理由通过）；44 种
形态先整体过一遍新规则再接线，0 例误拒。取值集与程序声明的关系用**子集**而不是相等：数据
里恰好没出现的那个状态，是一份诚实答案，不是一次伪造。

**账。** 宣告的未押住叶片 **194 → 153**，关掉 **41 片**。基线 11540 → 11568，skipped 221
不变，mypy clean（181 个源文件）。

### #525 一个区间能不能被复核，是「谁写的」的事实（2026-09-01）

**现象（端到端跑出来的）。** `decomposition.nde.ci_lower` 从 0.4768 改成 **50.48**——区间
既倒过来、又把自己的点估计甩在外面——`themis.verify` **接受**。四分解两种方法**各七个
分量**、纵向两种、ACR 边际表每一行，端点同样全部接受。而**同一个块**在
`mediation_linear_imai` 上，同样的改动**被拒**。

**根因假设。** 押住一个区间端点的是它旁边的**精度预算**：半宽和「半宽比点估计」是那两个
端点的算术，规则能重新算一遍，于是单改一端就对不上。做这件事的规则**从写下来那天起就是
走查全信封的**——它自己的注释写着「wherever a budget appears, and not at a list of places
it is known to appear」。**生产方那一侧不是。** 它用**四个几乎一样的函数**挂预算——flat /
curve / joint / decomposition——彼此只差「去哪儿找区间」和「旁边那个数叫什么」，每条路线调
它作者当时想到的那一个。**于是读者的区间可不可核，取决于有没有人想到它。**

**为什么是根因不是表象。** 不是「四分解漏挂了」。再写第五个变体就是同一个函数的第五份
拷贝，下一个带区间的块就是第六个洞。这跟 #522 同型而方向相反：那次是**规则**只问最外层
键，这次是规则会走、**生产方**在照名单挂。真正的缺陷是这条不对称本身。

顺带说明这个洞为什么此前完全没人碰得到：**「点估计落在区间里」这条检查是有的，它只问
最外层那一组**（`rules.py` 的 numeric-estimate 基本检查）。所以「区间倒过来、点估计在外
面」在信封顶层是拒的，往下一层就没人问——**同一句话在两个深度上一个是规则、一个是空气**。

**结构性改动。**
1. 四个挂载函数收成**一次走查**：走遍 `numeric_estimate`，凡是一个块自带
   `ci_lower`/`ci_upper`，就用共享的顶层 `sample_size` 给它定价。覆盖面从此在门的**两侧**
   都是信封形状的函数。
2. **「区间旁边那个数」是一份词汇表，不是一张位置清单**：`point`、`effect`（剂量曲线的
   采样点）、`weight`（有序剂量的边际行）。三个词，两边各存一份——验证器不许 import 生产
   方——**一条测试把两份钉成相等**，另一条走 schema，任何带区间的块若把自己的估计叫成第
   四个词就当场失败。这不是多余的谨慎：加 `weight` 时我只改了生产方，一个按 `weight` 定
   价的边际预算送到只认识 `point`/`effect` 的验证器面前，**被当成「除以了不存在的东西」
   拒掉**——一份词汇表分家的样子，就是它。
3. **schema 是找出落点的那把尺**：走查一开，门当场逐条报出「未声明的属性 precision_budget」
   ——十处。这十处就是覆盖面原来缺的那十处，不是我猜的。

**那份词汇表其实有三个副本，第三个是测试自己手写的。** 全量套件抓到：#521 那条「没有诚实
答案会声称自己是一个不存在的数的份额」的分母测试里，写着 `node.get("point") or
node.get("effect")`——一条**手抄的 or 链**。边际行按 `weight` 定价之后，这条测试把一份诚实
答案判成了「一个不存在的数的份额」——**它存在就是为了防止这件事，而它把枪口对准了自己**。
改成直接问规则用的那支 `_point_of`。→ **判据：一份词汇表的副本数，要按「谁在做同一个判断」
数，不是按「谁 import 了它」数**；测试里一条手抄的 `or` 链和一份 import 的常量，是同一个
副本的两种伪装。

**走查一开就撞出来的一个真问题。** 有一条剂量路线把曲线**从估计器自己的对象**记进推导
步骤，于是每条曲线都定价之后，「读者副本必须等于记录」那条规则的两份拷贝**再也不可能
相等**——而它之前不响，只是因为那条路线的曲线原本没被定价。规则的判决因此取决于**注解
发生在建推导之前还是之后**，那是个**顺序事实，不是关于答案的事实**。定下来：**记录记的
是估计器产出的数；从那两个数算出来的注解不参与这次比对。** 它并没有因此没人管——每一份
预算都被「用旁边的区间重新算一遍」押着，那是比「两份拷贝是否相同」更强的问题；块**里面
的数**照旧逐个比。

**核实方式。** 七种形态、十个端点，每一个先确认它现在带着预算（否则测试会因为错误的理由
通过），再推过去：把下端推到上端之外，以及**把区间朝两边撑开**——后者次序仍对、点估计仍
在里面，是半宽认出来的。诚实先过。

**一条量过之后决定不加的规则。** 本来打算顺手押住「`lower ≤ point ≤ upper` 且
`lower ≤ upper`」，并且量过：44 种形态里 118 个带区间的块，诚实答案上 **0 例违反**——所以
它是安全的。**但它是多余的**：预算铺开之后，任何一端被动都会让半宽对不上，包括上面那两种
伪造；而「撑开一个区间」恰恰是包含性**看不见**的那一种。两条规则查同一批伪造只是冗余，
所以没加。

**一处声明的取舍。** 新挂上的这些预算**现在没有读者面**——它们是让端点可核的证据，跟
`corner_risks` / `post_stratification` 同类。「每个分量也该告诉读者再多多少样本能把它的区间
砍半」是一条**成立的读者面改进，本条没做**。另外，走查从 `numeric_estimate` 起步，所以
结果根上的 `bounds_results` 不在它的覆盖里——界不是置信区间，那是另一个问题。

**把两轮都撞上的采集教训烧进 `tests/harvest_answer_shapes.py`。** 那支工具原来只会**整份
重采**——串行跑全套件，这台机器上近三小时——而这次只有七种形态动了。加了 `--only`，并且
**它的安全性不来自「按套件顺序跑文件」**（那只是代理，而且当场失效过：照直觉点
`test_aipw.py` 换回来的是同一形态的**另一次运行**，n 4000→3000、三种形态还整块少了
`outcome_saturation`——宣告余量会因为**样本换了**而缩水），**来自证明同一性**：同一个程序、
同一个数据摘要、同一个规模，任一不符就拒绝写入。每次运行现在还打印**每种形态第一次由哪个
测试产出**，下一次定向重采是点名而不是搜索。

**这一条里另有一次「不去找那个文件」的判断。** 七种里有一种，追它的产出文件两轮都没追到，
而每轮要十几分钟。停下来问了一句：找到它能买到什么？这次生产方唯一变的东西是**一支纯函数**
——预算只由两个端点和样本量决定，三样都在快照里。于是改成**在存下来的信封上重放生产方自己
那支函数**，并且**先证明这句话**：44 种形态里**既有的每一份预算，重放后逐位不变（0 处改动，
31 处新增）**。幂等成立，「这是生产方现在会写的东西」就不是猜测。**能被证明等价的重放，
胜过再跑一次找不到的搜索**；而工具里没有加这条路，因为它只在「唯一的变化是一支纯函数」时
成立，那是这一条的性质，不是采集的性质。

**账。** 宣告的未押住叶片 **256 → 194**，关掉 **62 片**：迁移之外三个中介块的全部区间端点、
纵向两种、ACR 边际表，外加顺带被绑住的两处 `sample_size` 和一处 `point`（预算把它们和区间
拴在了一起）。
基线 11481 -> 11540，skipped 221 不变，mypy clean（180 个源文件）。

### #524 判决从一个数读出来，而那个数是生产方一面之词（2026-09-01）

**现象（端到端跑出来的）。** `fitted_overlap.share_outside`——「拟合倾向有多大比例落在
可比带外」，读者据以决定**要不要信这个数**的那个量——诚实值 0.36325，改成 **0.9**、改成
**0.19**，`themis.verify` 两次都接受。三种「这份数据坏到什么程度」的图景，门全放行。

**根因假设。** 这个块**只上了结论摘要**。计数——多少个单位落在带外、总共多少个——在
估计器里**已经算出来、已经在缺口句子里说给读者听了**，然后在写信封前被扔掉，到门口的
只剩一个商。而假设账本对 positivity 的判决正是从这里读的，它**刻意不重述阈值、要重算**，
好让判决是**披露**而不是**主张**；可它重读的那个数本身只是一句主张。**独立性在离地一层
的地方停住，就只是装饰。**

**为什么是根因不是表象。** 不是「漏记一个字段」，而是这条链上**唯一看这个数的东西是一次
和阈值的比较**。于是任何**不越过阈值**的谎言都不可见（0.9 和 0.19 与 0.36 同在 0.05 的
同一侧，账本的重算纹丝不动），而越过阈值的谎言被拦下**是因为账本自己那份判决对不上**
——那是一条关于账本的规则，不是关于这个数的规则。同一个病灶横跨三块共 **60 片**未押住
叶子：`fitted_overlap` 24、`outcome_saturation` 24、`propensity_summary` 12，四种方法。

**结构性改动。** 不是补第二次拟合——验证器没有数据，也跑不了。是**任何模型拟合出来的
范围都必须满足的那组算术**：
1. 写者改成**收计数、自己去除**份额（`n_outside / n_total`），返回给调用方；原来调用点
   那句 `.mean()` 消失——一个事实在生产侧只算一次。上信封 + schema（`required`）+ 前端
   类型。
2. 新模块 `themis/verifier/fitted_diagnostic_rules.py`。押住的全是**定义性**的事：份额是
   计数除计数；**范围落在带内 ⟺ 带外计数为零**（双向）；越出带外则计数至少是越出的边数；
   诊断拟合在多少人身上，必须就是这个估计算在多少人身上；截尾计数与它截自的那个范围
   必须对得上；**倾向不依赖任何东西时不可能有范围**（空调整集 ⟺ `marginal` 模型）。
   独立性铁律：不许 import `themis.estimation`。
3. **在场与否交给 schema，不在这条规则里重问。** 这跟 #523 的「缺块就拒」不是同一件事：
   那里方法名本身说了分层必须存在，这里信封上**没有任何东西**说这次拟合该不该发生
   （处理变量是不是二值、拟合收没收敛，门都不知道）。所以缺块是**没做这项检查**，不是
   藏起来了——读者得到的是「什么也没说」，不是「说了假话」。schema 的 `required` 已经在
   前一道门拦下「带块但不带计数」，规则里再写一遍就是一条跑不到的守卫。

**量出来的一次改主意。** 原本决定**不做**跨块相等（`fitted_overlap.p_min` 与
`propensity_summary.raw_min` 在快照上精确相等），理由是那会把两个模块的模型选择钉死在
一起。扫描证明这个顾虑站错了地方：这两个数**在报告里是上下两行同时给读者看的**，它们
是**同一个调整集上同一个条件概率的同一个范围**——两行不一致，无论哪个模块是对的，读者
都被误导。这不是两份实现互押，是**一个量被披露了两次必须只有一个值**。加上它，另外
**12 片**当场关掉（三种方法 ×`p_min`/`p_max`/`raw_min`/`raw_max`）。

**核实方式。** 每一条恒等式**先在全部诚实答案上量过**才写进规则（一条没人量过的关系，
是一次等着某个形态来触发的误报）。然后正反都验：份额三种伪造、**把计数改成一致的干净
零**（这一条才是要害——它把判决从「被否定」翻成「没被否定」，拦住它的是**范围**：带外
没人就意味着每个拟合值都在带内，而这一个从 0.000002 跑到 0.99998，谎必须撒两遍，第二遍
印在读者眼前）、干净答案上凭空多出的带外计数、比拟合人数还多的带外人数、拿别人的样本
量当分母、截尾计数两个方向、两次披露的范围对不上、`marginal` 模型带范围、模型与调整集
互相矛盾。分母：没有这些块的答案一律放行。有一条**构造**而非采集：空调整集那个分支套件
里没有答案走到，而**没人走过的分支是一条没人读过的断言**。

**账。** 宣告的未押住叶片 **281 → 256**，关掉 25 片。剩下的三类，说清为什么留着：
`threshold`、`band_lower`、`floor` 是**估计层选的常数**，信封上没有任何东西能决定它们；
`outcome_saturation` 的 `p_min`/`p_max` **没有第二次披露**可比（倾向那对有，所以关掉了）；
`n_trimmed` 是**没有别的东西在数的一个计数**——范围只能决定它是不是零，决定不了它是几。
基线 11458 → 11481，skipped 221 不变，mypy clean（180 个源文件）。

### #523 迁移后的效应量本身，可以被改成任何数并且过公开门（2026-09-01）

**现象（端到端跑出来的）。** `transport_post_stratification` 的 `point`——把试验人群
的效应搬到目标人群之后那个数，读者据以行动的那一个数——诚实值 0.4106，改成 **2.23**、
改成 **−1.41**、改成 **0.0**，`themis.verify` **三次全部接受**。

**根因假设。** 这条路径把 `numeric_estimate` 挂到一个**由识别层写成的推导链**上，
**一个数值步骤都不追加**——链止于 `identify_via_transport`，说的是「这个估计量是怎么被
识别的」，然后一个数出现在旁边。于是 #515 那条「把读者副本押到记录上」的规则**没有第二
份副本可比**。而**一条比较两份副本的规则，在第二份不存在时什么都不做，而「什么都不做」
和「没查出问题」在门上长得一模一样。**

**为什么是根因不是表象。** 因为这不是「漏了一个字段」。逐形态量过：44 种答案形态里
**7 种的推导链没有任何 `numeric_*` 步骤**，它们合计背着当时 291 片未押住叶子中的
**84 片**；其中 `longitudinal_gformula` / `longitudinal_ipw_msm` 把信封上 **14 个顶层名
字记录了 0 个**。迁移只是这一族里**后果最严重**的那个：别的形态至少还有专门的数值验证器
或块内一致性规则接着，而迁移的点估计**没有任何规则**。（区间存在时 #520 那条
`relative_width` 会顺手拦下单改点估计的伪造——但那是副作用，只在有区间时存在，且改点又
改区间就穿过去；而套件自己的迁移答案**根本没有区间**。）

**结构性改动。** 不是补第二份实现——**这里没有可独立于的东西**，只有估计量自己的定义：
`Σ_z P*(z)·[E(Y|X=1,z) − E(Y|X=0,z)]`。

1. `estimate_transport` 记下**每个目标边际单元的充分统计量**：该单元的目标权重，以及它
   在源人群里那一层**两臂各自的人数与结局总和**。记的是**和与计数，不是两个均值**——
   验证器自己去除，抄一个均值过来就又多一个「生产方一面之词」的数；而两臂人数是那句
   「这一层的对比是站在十一个人还是一千一百个人上」的唯一出处。
2. `numeric_estimate.post_stratification` 上信封 + schema。**两道登记闸口当场都拒了它**：
   schema 说「未声明的属性不许出现」，复合部件普查说「schema 声明了一个没人认领的部件」
   ——后者要求这个块回答「谁读它」。答案是**验证器读，读者不读**：记的是和与计数，读者
   拿到的是那个数本身。（读者在这条路上确实还缺一样东西——目标权重压在源人群多薄的层
   上。那是 `stratum_support` 的问题，后门路上已经问过也已经渲染，迁移这条路没挂，
   **是另一条前沿，本条没做**。）
3. 新模块 `themis/verifier/post_stratification_rules.py`，从这些统计量把点估计**重新加
   一遍**。独立性铁律：不许 import `themis.estimation`。
4. **缺了这个块就拒，不是跳过。** 因为在生产方开始记之前，**每一份迁移答案都处在这个状
   态**，而门一声不吭。沉默必须变成拒绝，否则删掉一个键就把洞原样还回来。

**扫描当场逼出的第五件事。** 加完之后重扫，冒出一片**新的**未押住叶子：
`post_stratification.[].values.z`——**行标签**。求和不读标签，所以把两行的标签对调，
算术一字不变，而读者看到的是「甲层的目标权重」配着「乙层的数字」。这跟 #515 分层 Wald
表遇到的是同一个问题，用的也是同一类答案：**押到没有记录也成立的事实上**——一行的坐标
就是这次调整的那几个变量、同一张表的两行是两个不同的单元、以及权重必须加起来是一整个
人群（后者是**独立**约束：两个权重反向对移，求和纹丝不动）。

**核实方式。** 诚实先过；然后三种伪造（×3+1 / 取负 / 归零）逐一被拒，外加一个
**+1e-4 的微调**——它落在 `relative_width` 容差之内，是证明「这条新规则真的在干活、而不
是搭了旧规则便车」的那一个。反向也验：动权重、动人数、动结局总和、对调标签、把权重整体
减半、整块删掉，各有各的拒绝语句。分母：其他方法的答案一律放行。

**一处工程教训，值得记。** 快照本该整份重采，而 `harvest_answer_shapes.py` 是**串行跑
整套件**——这台机器上 5 分钟才走 3%，全程近三小时。但**只有一种形态动了**。改成「只重采
那一种、并入快照」：5.4 秒。**快照是按形态收集的，所以它也可以按形态重采**——重跑一整
份，是把「收集的单位」和「重跑的单位」当成了同一个。

**账。** 宣告的未押住叶片 **284 → 281**，关掉的三片是 `point`、`sample_size`、
`adjustment.[]`——**迁移这条路上，读者看的那个数第一次有了人复核**（新加的
`post_stratification` 块自己也一片不欠：标签、权重、两臂人数与总和全部被押住）。
基线 11435 → 11458，skipped 221 不变，mypy clean（179 个源文件）。
剩下 281 片里最大的一族仍然是**同一个病灶的其余六种形态**：中介四分解 34 + 分解 41 的
区间端点、纵向两种的区间、`counterfactual_cell` 12——它们的链同样不记估计，只是各自还
有别的规则接着，没有迁移这么彻底。

### #522 「同名即同物」只问过信封最外面那一层键（2026-09-01）

**现象。** #521 宣告的 291 片未押住叶子里，有一族根本不缺记录——**记录里就有这个数**，
只是它在信封上多套了一层。因果概率的六个界（PN/PS/PNS 各自的上下界）就是这样：步骤里明
明写着 `pn_lower`、`ps_upper`，而读者看到的 `probabilities_of_causation.pn.lower` 从来
没有跟它比过。

**根因假设。** #515 那条规则问的是「两边共有的名字必须指同一件事」，可它**只问了
`numeric_estimate` 的最外层键**。于是规则的覆盖面成了**「估计器把答案嵌多深」的函数**，
而不是「读者被展示了什么」的函数。嵌一层的答案自动出界。

**为什么是根因不是表象。** 因为补一张「还要看这几个块」的名单，就是再写一张会过期的表，
而**这个模块的历史已经证过两次**：wrapper 名单漏了 `atom_tuple`（#519 修的）、stratum
列名写死。**深度不该是这条规则的参数。**

**加深之后，问的必须是另一个名字——这才是这一条的全部内容。**

我第一版是「任何深度，拿叶子**自己的名字**去比」。44 种形态的快照说安全（45 处一致、
0 处分歧），**全量套件当场证伪**：`probabilities_of_causation.ps.ci_lower` 撞上了步骤记
的 `ci_lower`。一个是「充分性概率」自己的区间，一个是整轮运行的区间。

根因是：**答案报告自己用的那套词汇（`point` / `ci_lower` / `ci_upper`）是相对的**——
相对于「你现在看的是哪个答案」。而子答案跟整轮运行**用同一套词**。所以叶子自己的名字在
深处**不构成任何证据**，能消歧的恰恰是**块的名字**，而记录里带着它：`pn: {lower, upper}`
对 `pn_lower`。

**三次量出来的取舍，每一次都推翻了我一个想当然：**

1. **列表里的更早就撞了。** 剂量曲线每个点都有 `ci_lower`，还有 `x`（点上是剂量值
   0.878，记录里是处理变量名 `'raise_amount'`）——**照比会在诚实答案上错 47 次**。
2. **拼名可以，猜拼写不行。** `<块名>_<叶名>` 是关于两种**形状**的规则。我顺手加的
   「再去掉复数试一次」把 `pns.lower` 匹配到了 `pn_lower`——**两个不同的量，当场拒掉一份
   诚实答案**。
3. **深处只比「值」不比「块」。** 嵌套块的名字描述的是它**在父块里的角色**，角色不是记录
   的词汇。实测：中介分解的系数表把每个中介的系数挂在 `mediators` 下，步骤记的
   `mediators` 是**中介名单**——一个词，一个是函数一个是它的定义域。

**一条没做、并且说明白为什么。** `adjustment` 在信封上是 `["z"]`，记录里是 `"z"`——调整
集被写进了**一个字段**，而分隔符**没有任何地方记过**。收窄成拼名规则之后这一对根本够不
着，所以它留在宣告名单上。**顺带删掉了我为它写的两个守卫**（序列对字符串、`step_ref`
指针）：收窄之后**它们一次都跑不到**，而**跑不到的守卫是一条没人核过的断言**。

**核实方式。** 44 种形态逐一诚实过门先跑——这一步当场拦下我三次（`adjustment`、
`confounders_by_time` + `cde`、`mediators`）。然后全量套件，它拦下了第四次，**而且是最
要命的那次**：`ps.ci_lower`。这份快照里那个字段两边**恰好都是空**，所以快照说「安全」。
**快照覆盖的是形态，不是一种形态能取的值**——#520 立的这条，这次是它救的场。

**账。** 宣告的未押住叶片 **291 → 284**（关掉 7：PN/PS/PNS 六个界 +
`joint_backdoor_logistic.interaction.point`）。这 7 片全部由**拼名**押住，一片都不是由
「深处的裸名字」押住的——第一版那个更宽的规则闭掉的多，但它闭掉的方式是拒绝诚实答案。
基线 11432 → **11435**（新测 3）。skipped 221 不变。mypy clean（178 files）。
`_recorded_anywhere` 顺手换成 `_chain_record`：链只摊平一次，不是每个名字搜一遍。

### #521 「守住了」是关于我恰好试的那一次改动的事实（2026-09-01）

**现象。** #519 立的那条叶片扫描，每片叶子**只弯一次**。把它改成每片叶子问**好几种**
谎言（翻转 / 加常数 / 归零 / 取负 / 翻倍 / 清空 / 换名），44 种答案形态上多出 **11 片**
能改了照样通过公开门。其中一片不是诊断也不是舍入，是**答案本身**——
`joint_backdoor_linear.joint_effect.point`，同时干预两个处理的点估计。

**根因假设。** 「守住」这个判定的分辨率，是由**提问的人**定的，不是由被查的东西定的。
一条只抓某一种改动的规则，在只问那一种改动的扫描里就叫「守住」。于是宣告出去的 283
**是一个下界穿着测量的衣服**——而这份文件存在的全部理由，就是让那个数不再是一面之词。

追下去，那片答案叶子为什么只被一条规则守着，是同一个老毛病的第三次：#520 的
`relative_width` 是 `半宽 / |点估计|`，我为了不让零进分母写了 `if point:`——**静默跳
过**。点估计被改成 `0.0` 时这条比值整个不做，而它是 `joint_effect.point`
**唯一**的守卫。

**为什么是根因不是表象。** 这个形状本次会话已经撞见三次：#515 的 `_bend` 对字符串返回
`None`（弯不动就跳过，#519 查出来的），显示规则查不到记录就 `continue`（#519 修的），
现在是我自己在 #520 里写的 `if point:`。**零分母不是「没什么可说」，恰恰是「旁边那个比值不可能对」。** 跳过和拒绝
在这个位置上是相反的意思，而在代码里它们长得一模一样。

**把问题问宽，问出来的第一个东西是我自己的误报——这条比上面那条更值得记。**

新弯曲集把 `iv_2sls_overid` 的 `over_identification.hansen_p_value` 报成了幸存者。追进
去：它的诚实值是 **1.09e-229**，唯一活下来的弯法是**把它改成 `0.0`**。那不是谎言，那
是**同一个数**——接受它的规则是对的，报它的扫描是错的。

根因不是「少排除了一种弯法」，是我**把「什么才算谎言」写成了配方而不是判据**：原话是
「不要用 `value + 1e-3` 这种弯法」。配方管不住**同一个配方在不同量级上退化**——`0.0`
对 0.5 是替换，对 1e-229 是微调。补一条例外就得为下一个量级再补一条，而**例外是一个关
于「这里为什么对不上」的假设**。

所以判据独立成 `_is_material(old, new)`：**问的是两个数的差，不是产生它的配方**，
用显式声明的 `_ATOL = 1e-6` / `_RTOL = 1e-5`（比规则们各自声明的容差都宽——**这个闸口
必须在不读规则的前提下判定重要性**）。同一条判据同时解释了两次误报：大数上的 `+1e-3`
是相对容差以内，1e-229 上的 `0.0` 是绝对容差以内。

**结构性改动。**

1. `envelope_arithmetic_rules.py`：分母为零或缺失时**拒绝**，不跳过。拒绝语句把算出来
   的一侧渲染成 *nothing — the figure it is a share OF is zero or absent*：读者看到的是
   「你在报一个不存在的东西的份额」，而不是一个对不上的数。
2. 闸口 `_bend` → `_bends`：一片叶子**每一种**谎言都被拒才算守住，任一种活下来就是洞。
3. 闸口新增 `_is_material`：弯曲集只负责说「有哪些**种类**的谎言」，「这一次弯到底算不
   算谎言」交给判据。**误报比它闭掉的洞更糟**，在一份「宣告剩余」的文件里尤其如此。

**核实方式。** 诚实先过（44 种形态逐一过门，否则被拒的伪造什么都不证明）。**分母测过才
敢拒**：44 种形态里没有任何一份诚实答案在点估计为零或缺失时还报 `relative_width`。
`joint_effect.point` 的四种伪造（`0.0` / ×3+1 / 取负 / 减半）逐一被拒——**每一种，因为
「守住」曾经是关于其中一种的事实**。判据本身也钉了一条测试，拿 fixture 里那个真实的
1.09e-229 当例子，让它可以被后来的人反驳而不是被重新发现。

**账。** 宣告的未押住叶片 **283 → 291**。这不是变差：其中 **8 片**是同一批洞里之前**只
被问了一种问法所以没被看见**的；另外 2 片（`joint_effect.point` /
`interaction.point`）被这次的拒绝改动关掉了，它们**从来没进过宣告名单**——单次弯曲把
它们报成了守住。闸口本身现在约 **3500 次过门调用、两分钟量级**——一片叶子最多问四遍，
这是把下界换成测量要付的钱。基线 11428 → **11432**（新测 4）。skipped 221 不变。
mypy clean（178 files）。

新暴露的 8 片已写进 `unwitnessed_leaves.json`，**下一条前沿从名单开始，而且顺手量过了它
们分别缺什么**：

- `propensity_summary.floor`（aipw / ipw_stabilized / tmle）——**这个数已经在记录里了**，
  写作 `derivation.steps[1].inputs.propensity_floor`。#515 那条「把读者副本押到记录上」的
  规则没押住它，只因为**两处名字不同**。同一件事的两种说法，又一次。
- `fitted_overlap.threshold`（同三种）——记录里**没有**，得让生产方先记下来。
- `stratum_support.cells`（backdoor_logistic）——同上。
- `over_identification.sufficient_statistics.s1.[].[]`（iv_2sls_overid）——**不是**「重算
  没读它」：测过，×3+1 与取负都被 `iv_overid_numeric` 的稳健 AR 扫描拒掉，**归零和减半
  过**。重算读它，但那条路径对某些方向不敏感。这一片是四片里最值钱的。

### #520 「再招 4000 人就能把区间减半」——这句话是算术，没人算第二遍（2026-09-01）

**现象。** #519 留下的 383 片未押住叶子里，有一整类根本不是测量：**区间的半宽**、
**宽度占效应的比例**、**要把区间减半得再收多少样本**。三个数全是对信封上**已有的数**
做的加减乘除——区间、点估计、样本量就在旁边。而这三个里最能左右读者行动的那个
（「再去招 4000 人」）恰恰是**没有人会手算**的那个。

**根因假设。** 推导链记的是**估计器做了什么**，不记估计器做完之后有人取的那几个和。
于是 #515 那条「把读者副本押到记录上」的规则**没有东西可押**——记录里根本没有这些量。
它们就这样以生产方一面之词的身份到达读者。

**为什么是根因不是表象。** 因为这一类的**输入全部已经在信封上**。闭掉它**什么都不用
记**——这正是它跟「重算估计器」那类审计的根本区别：**这里没有独立性问题，因为没有第二
份实现，只有一条要么成立要么不成立的恒等式。** 把它当成「又一个 #516（让生产方记下充分
统计量）」就会白做一遍工。

**结构性改动。** 新模块 `themis/verifier/envelope_arithmetic_rules.py`：凡是信封上出现
`precision_budget` 的地方（**按出现处遍历，不按已知位置列表**——新块换个名字自己就会走
进来），拿同一个对象里的区间与点估计、以及这次运行的样本量，把三个数各算一遍。

**三次测量纠正了三次想当然——这条才是本条的主要内容。**

1. **8 条候选关系里有 2 条在诚实答案上就不成立。** `additive_interaction` **不是**两个
   交互项之和；两块各自报的 proportion mediated 在 **logit 尺度上本就不相等**（它们是
   不同的分解）。任何一条被断言，都会拒掉一份诚实答案。**没量过的关系是一条等着遇上不
   遵守它的形态的误报。**
2. **另 3 条成立，但仍然不写。** 中介总效应 = 直接 + 间接、四分解的两个比例——带上和不
   带跑同一遍扫描，**闭掉的叶子一模一样**（383 → 286 两次都是 286）：
   `verify_mediation_numeric` 早就押住了每一条。写进去的代码又删掉了。**重复一条已有的
   检查不是第二意见，是同一件事的第二个出错地点。**
3. **`n_to_halve_ci` 我按「4 倍样本」写，然后被全量套件证伪。** 44 种形态上过了 27/31，
   剩下 4 个都是剂量反应曲线上的点，我归因为「曲线上的点有自己的样本量」并**特地写了一
   条例外**。跑全量：`n=90` 的那份答案要的是 **400 不是 360**。真正缺的是**向上取整到
   50**——读者要去招的是人，给的得是个整数。补上取整之后，**曲线上的点也全部对得上**，
   那条例外整个删掉，又多闭了 3 片。**一个特例是一个关于「为什么这里对不上」的假设，而
   假设是要被证伪的。**

**方法论上的一条，值得单独记。** #519 那 44 种形态的快照覆盖的是**形态**，不是一种形态
能取的所有**值**。`n=90` 这个反例只在全量套件里出现。所以：**快照是让扫描能跑的东西，
诚实分母仍然是全量套件。**

**核实方式。** 44 种形态逐一诚实过门（作为参数化测试，不是一次循环——哪一种坏了就报哪一
种）。然后逐条伪造：三个和各改一个、反过来改被它定价的区间、**只有 budget 没有区间**
（拒：给不存在的东西定价，既不可能错也不可能对）、以及**舍入的边界**（半宽给读者时保留
六位，所以容差正好是半个末位——比舍入更宽的容差会开始接受「不是任何数的舍入」的数）。

**账。** 未押住叶片 **383 → 283**（关掉 100）。基线 11368 → **11428**（新测 60：新文件
58 条 + 两条按模块文件参数化的门自动收进新模块）。skipped 221 不变。mypy clean
（178 files）。

### #519 叶片扫描只问过 1 种答案形态，另外 43 种里 420 片叶子随便改（2026-09-01）

**现象（跑出来的，不是读出来的）。** 从套件自己的出口插桩收上 **44 种答案形态**（一种
`numeric_estimate.method` 一对 (program, result)，不是编的程序），逐叶篡改后过公开门：
**1312 片不同形状的叶子里，420 片能改了照样通过**，44 种形态里 **42 种**至少有一片。
里面有：纵向答案的区间端点 `ci_lower/ci_upper`、剂量反应曲线**每个点**的置信带与
precision budget、读者用来判断该不该信这个数的 `fitted_overlap` / `outcome_saturation`
/ `propensity_summary` **每一格**、中介分解四个成分的全部区间端点，以及——**几乎所有
形态的 `treatment` 和 `outcome`**。

#515 立的那条「把测量本身当闸口」的叶片扫描本该发现这些，它没有，因为两件事：**它只跑
了一种形态**（分层 Wald），而且它的 `_bend` 对**字符串**返回 `None`——**弯不动的就默默
跳过**。命名变量的叶子全是字符串。

**根因假设。** 三处，同一个形状：**覆盖面由被检查方决定，而规则的沉默既可能表示「对上
了」也可能表示「根本没看」，两者在门口无法区分。**

1. 展示副本规则只跟**终止步**比：`if name not in inputs: continue`。于是它的射程不是由
   「读者看到什么」决定的，而是由「最后一步碰巧记了什么」决定的，而那随估计器而变。
2. 解包表把 wrapper **一个个列名**（`atom` / `atom_set` / `value_tuple` / `dict`），
   `atom_tuple` 漏了——一个中介集因此「形状不同」被跳过。
3. `treatment` / `outcome` / `mediator` / 两个 proxy **任何一步都不记**：它们来自
   **query**，不来自链。「同名比对」这条路本来就到不了它们。

**为什么是根因不是表象。** 表象是「某某字段没押住」，改法是逐个补记——那是把 #516 重复
五百次。真正要改的是**谁决定覆盖面**：只在名字撞上时才说话的规则，其覆盖面是被检查方给
的；#515 的闸口自己也犯了同一条（`_bend` 返回 None 即跳过）。

**结构性改动。**

1. **比对范围从终止步扩到整条链。**（先实测：44 份诚实答案零误报，多够到 12 片。）
2. **解包按形状不按名字**：有 `items` 是列表就当列表、是字典就当字典。**把 wrapper 逐个
   列名正是漏掉 `atom_tuple` 的原因**，所以不再列名。
3. **新规则 `verify_answer_names_its_question`：变量名不跟链比，跟问题比。** 按 query
   kind 分别读（causation 的 `cause` 和 effect 的 `intervention` 是同一件事的不同拼法，
   拿错读法就会把答案押到别的问题上）。**改一个名字不动任何数字，却把旁边每一个数都变成
   另一个问题的答案**——这是「看起来完全正确」的最彻底的一种错。序列写进一个字段的（纵向
   路径把整条处理序列写成 `A0,A1`，而 query 只点了 `A1`）**拒绝比对而不是猜**：#517 刚教
   过，把诚实答案说成谎话比漏一个洞更糟。
4. **扫描升格成闸口，铺到全部 44 种形态。** 44 对 (program, result) 存成快照
   （`tests/fixtures/answer_shapes.json`，由 `tests/harvest_answer_shapes.py` 重生成），
   剩余 383 片写进 `fixtures/unwitnessed_leaves.json`。**快照是副本，所以它对被抄物作了
   声明**：每一对先诚实过门再扫，生产方一旦漂移就在那里失败，而不是默默扫一份化石。一片
   叶子**只能因为被闭掉**而离开那份文件——多出来一片，测试直接把它的名字说出来。

**核实方式。** 诚实先过（44 份全过，且是闸口的第一条断言）。改完重扫：**420 → 383**，
关掉 37 片。四种形态上直接钉住「改名字必被拒」（backdoor 的 outcome、mediation 的
mediator、proximal 的 outcome_proxy、causation 的 treatment）。纵向那条序列字段单独测：
规则**放行**它（而门口由链比对接住，这是分工在起作用，不是规则多余），而同一条规则对一个
对不上的单名答案照拒。

**声明的取舍。** 剩 **383 片**没有证人，全部写在册。它们分四类，各是一条独立前沿：区间
端点（可从 bootstrap 抽样重算）、precision budget（纯算术，可由信封里别的数推出）、拟合
诊断（要充分统计量，走 #516 那条路）、以及 `adjustment` 之类来自识别路线的副本。闸口耗时
**43 秒**——这是让一个 383 片的洞不能再长大的价格。

**账。** 基线 11360 → **11368**（新测 8）；skipped 221 不变。mypy clean（177 files）。

### #518 一个能算出来的数被抄成七份散文，七份一起过期（2026-09-01）

**现象。** `AUDITS` 现有 **19** 行，其中审的是别的 artifact（不是 query_result 信封）的
有 **8** 行。而七处散文各自写着「**thirteen** audits，**five** of them standalone」：
`themis/__init__.py`、`themis/mcp/server.py`、`themis/web/app.py`、
`themis/output/analysis_report.py`、前端 `api.ts` 与 `Recheck.tsx`、以及 `audits.py`
里那句「A **fourteenth** entry point…quietly answers for **twelve**」。七处独立抄写，
**七处一起停在 13/5**，跨越了六个条目的新增没有任何东西发现。

**根因假设。** 这个数由 `len(AUDITS)` 一行算得。它被抄成了七份散文常量，而**抄本对被抄
物不作任何声明**——所以没有任何机制能发现原件变了。这跟 #513（把程序的话抄下来那两块
没人跟程序对过）、#515（一个答案到达读者两次只有一份被审）是同一种病，只是这次副本是
散文、原件是一张表。

**为什么是根因不是表象。** 表象是「七个数字过时了」，改法就是把 13 改成 19。但那只是把
七份常量刷新一次，下次加审计时它们会再一起过期——而**这次的证据就是它们已经一起过期
了**，而且过期的是 6 个条目，不是 1 个。真正的问题是：这个数对读者根本没有用。读者在这
些位置需要知道的是**「有些审计不是关于你这个 artifact 的，拿错了它会用和『没通过』一模
一样的异常拒绝你」**——这句话不含数字，且永远为真。

**结构性改动。** 七处**把数去掉、把事实留下**（`thirteen` → `among many` /
`several of them`）。**能不写数就不写数**：不存在的副本不会漂移。

**声明的取舍：没有加闸口。** 想拦住「以后又有人往散文里写个数」，闸口就得能区分**活的
断言**（「现在一共十三条」）和**历史测量**（`blocks.py` 的「of thirteen ROUTE blocks,
six had an audit and seven did not」、`test_web_envelope_fields` 的「types.ts named
thirteen」——这些记的是当时量到的事，本来就不该跟着现状变）。这个区分不是机械可得的，
硬写一条扫散文数字的门会开始拦历史记录，比病本身更糟。**唯一保留的活数字是
`_ROUTE_AUDITS` 的 13**，而它不是散文常量：`bind_audit` 的完备性检查在 import 时押着它。

**账。** 只动散文，无行为改动；基线 11360 不变。mypy clean（177 files）。

### #517 拒答是一个关于程序的断言，而没有任何一扇门去看程序（2026-09-01）

**现象（跑出来的，不是读出来的）。** 拿一份诚实拒答——`x → y` 带未测混杂、
`unidentifiable_no_admissible_set / blocking`，三条建议是「去测那个混杂因子 / 去做
RCT / 去找工具变量」——**一个字节都不改**，只把它交回给一个 Themis 自己刚给出点估计
的查询（`w` 可观测、后门可调整、`numerically_solved`）。结果：

| 门 | 诚实拒答 | 伪造拒答 |
|---|---|---|
| `themis.verify` | ValueError（没有推导链） | ValueError（同一句） |
| `validate_result` | 通过 | 通过 |
| `themis.verify_data_gap_report` | 通过 | 通过 |
| `themis.audit(program, ·)` | 逐行全 ok | **逐行完全相同，全 ok** |

也就是说：**读者被送去采一份这张图本来就能识别的数据，而没有任何一扇门有话说。**
顺带测到的另一半：把那条「去做 RCT」的建议整段改写，`verify_data_gap_report` 照样
通过——它按契约只看结果内部一致性。

**根因假设。** `verify()` 把「没有推导链」等同于「以省略冒充验证」，整类拒收。对**答案**
这是对的。但拒答的内容不是答案，也不是不可验证的——它是**关于程序那张图的断言**
（「不存在可容许集」），而这张图验证器每验一个答案都要重建一遍。因为**唯一收程序的
那扇门整类不受理**，这一类就只剩「只收结果」的门在管，而只收结果的门管不了关于程序
的断言。

**为什么是根因不是表象。** 表象会说「`unidentifiable_no_admissible_set` 少一条规则」。
把规则塞进 `verify_data_gap_report` 做不到——那扇门按契约不收程序（docstring 明写
「deliberately result-only」），所有现有调用方含 MCP 工具都只传结果。真正缺的是**门的
形状**：`verify` 的写法是「重走推导链」，仓库里没有任何入口的写法是「重走这次拒答」。
而这个形状仓库自己有先例，理由一字不差：`verify_bounds_results` 的 docstring 说，界
「通常在点识别失败、没有推导链时挂上，所以 verify 恰好对带界的结果是休眠的」。**同一
句话对缺口报告成立，只是没人写。**

更靠内的一层佐证：`_classify_unidentifiable` 的注释自己说，它改成读**成功的**
`tian_hedge_witness` 步，是因为「失败的步只是一个『出事了』的断言」，而 c-分量分解是
**验证器可以重放的证明**。**这条原则在推导链内部已经确立，只是没有在门口执行**——另
一个发射点 `_species_unidentifiable` 从一个 InvestigationItem 发出同一个 kind，身上一
个证人也没有，而它正是没有推导链的那条路径。

**结构性改动。**

1. **新公开门 `themis.verify_refusal(program, result)`**，收程序，AUDITS 里
   `needs_program=True` + `needs_field="data_gap_report"`。于是 `themis.audit` 与 MCP
   的 `themis_audit` **自动带上，零新 MCP 工具**。
2. **新模块 `themis/verifier/refusal_rules.py`，是个证伪器不是确认器。** 它在图里**搜
   证人**：可容许集用 Perković 的正则调整集（存在任一可容许集则它就是一个），前门用
   有界的中介集搜索；找到就拒答为假，并**把证人的名字报出来**（「adjusting for {w}」/
   「front-door through {m}」）——那正是读者真正要的那句「那我当初该怎么做」。
   **返回 None 不是「这份拒答已证成立」**：证明不可识别是生产方的活，它做过的地方证明
   就是推导链里那个 hedge witness。所以模块里每一处边界都**只往「找不到证人、放行」
   那一侧偏**——往另一侧偏的边界会把诚实拒答说成谎话。
3. **GapKind 上一张必须完备的绑定表。** 每个 kind 归到「由程序 settle」/「由数据或这
   次运行 settle」/「只是把调用方自己的声明抄回来」。少一个 kind → **import 失败**。
   声明了「由程序 settle」却没有证人搜索的，不写在注释里而是**由 `UNWITNESSED` 算出来
   并由测试钉住**——一个 kind 只能因为**被闭掉**而离开那张名单。
4. **`verify` 走同一条内部路径**（#512 的规矩：全门不得弱于窄门）。一个已答结果的缺口
   清单里被塞进「这张图什么都识别不了」，现在 `themis.verify` 就会拒。

**核实方式。** **诚实答案先过**，而且这次这条格外重，因为**误报比它闭掉的洞更糟**——
那等于把一句诚实的「我答不了」说成谎话。四种诚实形态先过：真不可识别的图、有一堆
帮不上忙的观测变量的图、唯一能闭合路径的节点在处理下游的图、以及**因为缺数据而拒答**
的前门程序（它的 kind 是 `missing_distribution`，这扇门一个字都不能说）。然后是伪造：
后门证人 {w}、前门证人 {m}、`themis.audit` 两列现在不同了、以及**已答结果被塞进假缺口
时全门也拒**。**分母**：一条「由数据 settle」的缺口即使图完全没问题也必须放行——写成
「拿不准就拒」的门会把伪造也拒掉，然后什么都没说明。另加：**全量测试串行跑一遍，
把这扇门挂在每一个 run/estimate 出口上**，凡是套件自己产出、带着可搜证人的 kind 的
拒答，逐个过门，确认零误报。

伪造那一侧除了后门证人 `{w}` 与前门证人 `{m}`，还专门测了两处容易做错的：**M-bias 下证人
是空集**——这张图上唯一可选的变量一旦条件上去反而打开路径，「随便凑一个集合」和「只肯给
非空集合」两种写法在这里都会给出错的答案；以及**潜在混杂长在别处**时（图里有双向边、搜索
整体切到 m-分离）证人 `{w}` 依然找得到。另外「读者要求的条件化」正反两面各一条：条件化在
处理前的变量上时证人照样成立，条件化在处理下游的对撞子上时**没有任何集合可容许，这份拒答
就该站住**——证人是关于估计量的事实，不是关于图的。

**全量那一跑抓到了一整类误报，而且是我自己推理时明确排除掉的那一类。** 565 次拒答里
**28 次误报，全是同一类：迁移（transport）**。原因是我拿**查询的类型**当护栏
（`isinstance(q, EffectQuery)`），以为「路线失败的是迁移」的那些拒答会因此被挡在外面——
**而迁移查询就是 `EffectQuery`，只是多带一个 `target_population` 字段**，不是另一个类型。
于是搜索在**源人群的图**里找到可容许集，转头说这份「不可迁移」的拒答是假的。

根因不是「漏了一个字段」，是**我假定估计量由查询的类型定住**。改法相应地也不是补一条
`if target_population`：**写下搜索读的是哪几个字段**（`target` / `intervention` /
`given`），其余字段一律要求处在默认值——**「哪些字段会取消资格」那张反向名单，会在有人
在旁边加一个字段的当天过期**，而这正是这次犯的错的形状。选择节点同理并入同一条原则：
数据是被选择过的子人群时，搜索所识别的那个分布本来就不在手上。28 份误报的
(program, result) 全部留着，改完**离线重放，28/28 全部放行**，而伪造仍然照拒。

**声明的取舍。** 11 个「由程序 settle」的 kind 里，这次只有 1 个有证人搜索；另外 10 个
（`collider_conditioning_opens_backdoor` / `missing_iv_candidate` /
`ill_defined_intervention_versions` / `ambiguous_variable_definition` 等）**在表里、在
`UNWITNESSED` 里、在测试里各写了一遍**，是可见的余额不是静默的缺口。前门搜索的中介集
上界是 2，这个界只会让证伪器**少找到**证人。

**账。** 基线 11333 → **11360**（新文件 25 条，另 +2 是两条按模块文件参数化的门自动把
新模块收了进去）；skipped 221 不变。mypy clean（177 files）。

### #516 判定「工具是不是弱的」那个数，从来没人重算过（2026-09-01）

**现象。** Stock-Yogo 阈值作用在**一个数**上，读者靠它决定要不要相信这个点估计。
它从原始数据框算出、写到信封上、**在任何推导步骤里都没有名字**——所以没有任何规则
能重算它，也确实没有。`first_stage_f_stat = 0.1` 和 `= 104526` 对公开门是**同样
可接受**的。#515 把这一片叶子作为「已量过的例外」写进了测试；这一条是把它闭掉。

**根因假设。** 这不是「展示副本跟记录不一致」，是**一个没有记录的数**。#515 那条
通用规则问的是「两边同名的量是否一致」——而它一边都没有出现。生产方在 `iv.py` 里
从原始 df 算出 F，写进 `numeric_estimate`，**中间不经过推导**。

**为什么是根因不是表象。** 因为凡是「算完直接写上信封、不进推导」的量，都在验证器
的射程之外，而射程之外和「验过了」在门口是同一件事。这一类里 F 是后果最直接的
一个：它不改变任何数字，只改变**读者要不要相信那个数字**。

**结构性改动。**

1. **生产方记下它是哪两项之比。** `FirstStageMoments`——(Z, X) 在 [1, W] 上残差化
   之后的二阶矩 `s_zz / s_zx / s_xx` 加 `n_obs / n_exog`，对这个 F 是充分的。选记
   **矩**而不是生产方实际形成的两个平方和，是因为**这三个数正是 Anderson-Rubin
   集在恰好识别路径上已经带着的那三个**——于是同一条回归的两份记录可以互相押住，
   伪造者动了第一阶段就必须把置信集一起动。
2. **验证器走另一条公式。** `_check_first_stage`：生产方由两个 SSR 之比得到 F，
   这条由「被解释的部分 / 剩下的部分 / 自由度」得到。**共用同一段算术会让两边按
   构造相等，那是一条不可能失败的检查。** 再加两个方向：报了 F 却没记统计量 → 拒
   （否则那个数仍然只是一面之词）；记了统计量却没有 F → 拒（记统计量就是为了让
   统计量可查，旁边没有统计量的算术无所谓真假）。
3. **推导里也记下 F 本身**，于是信封上那份副本由 #515 的同名规则顺带押住——**加一
   个键闭掉副本，加一组矩闭掉数本身**。
4. **过度识别路径什么都不用记。** 它的联合 F 是一个 q 约束检验，用的是 Sargan
   统计量本来就靠着的那些矩矩阵——`verify_iv_overid_numeric` 里加一段重算即可。
   **这个数一直是可算的，只是一直没人算。**

**核实方式。** 先让诚实答案过（恰好识别、带外生块的、过度识别三种形态都过，且
`n_exog` 确实是 1——自由度数错的检查会在无条件那条上通过、在这条上现形）。然后
逐条篡改：只动信封那份（#515 的同名规则接住）、**两份一起动**（此时同名规则无话可
说，正是重算本身要起作用的地方）、只动矩、五个统计量**逐个**删掉、只删 F、让两份
记录互相矛盾、动过度识别的联合 F——全部被拒。**分母**：一个**诚实的弱工具**
（F < 10）必须照常通过——写成「F 必须够大」的检查会在这里现形。

**#515 留下的那个闸口自己动了手。** 那条遍历每片叶子的测试断言「除了已声明的例外
没有一片能活」，例外集合里正是 `first_stage_f_stat`。这次改完它**失败了**——因为
那片叶子不再能活。例外集合现在是空的，而它是**被闭掉**而不是被豁免才离开的，
这是唯一该有的离开方式。

**账。** 基线 11319 → **11333**（新测 14）；skipped 221 不变。mypy clean
（176 files）。分层 Wald 答案上 **42 片叶子全部押住**。

### #515 一个答案到达读者两次，只有一份被审过（2026-09-01）

**现象。** 数据路径上的答案有两份记录：推导的**终止步骤**记着估计量做了什么
（验证器里每条规则都从**它**重算），旁边的 `numeric_estimate` 才是读者、报告和
浏览器真正读的那份。对一个分层 Wald 答案把 `numeric_estimate` 下的**每一片叶子**
逐个扰动再过公开门：**42 片里 38 片通过**。声明的置信水平、样本量、分层表的每一格、
置信集的每一个端点——读者可以被展示一个撑成 `[-99, 99]` 的置信集，或者一个
`first_stage_f_stat = 0.1`（弱工具）而这次运行算出来的是十万——门都说验过了。
只有点估计和敏感性块守住了。

**根因假设。** 「展示副本要跟被审过的记录对上」这个惯用法在这仓库里**是有的**——
kernel 里 `_verify_causation_extensions_match` 等三条正是干这个的——但它是**每加一
个块、由人想起来写一次**的，覆盖的是「有人记得的那些块」。`numeric_estimate`
**自己的子块从来不在那个人群里**：它不是 `Block`，任何家族绑定都够不到它，
ROUTE 那轮扫描也没问过它。

**为什么是根因不是表象。** 因为这不是某个字段漏了，而是**整个类没有被表述过**：
「凡是既出现在推导 inputs（在那里被重算）又出现在信封上（在那里被读）的量，两者
必须一致」。没有这句话，覆盖就只能靠记性，而记性的覆盖面正好等于 38/42。

**结构性改动。** 新模块 `themis/verifier/display_copy_rules.py`——它是
`program_copy_rules` 的同胞：一个审「程序说过的话的副本」，一个审「这次运行自己
记录的副本」，合起来说的是**信封上每一份拷贝都被押在它的原件上**。

1. **同名即同物**——不需要知道任何估计量：`ci_level`、`sample_size`、`data_hash`、
   `method`、端点、以及变量。推导 inputs 用**带类型的序列化包装**
   （`value_tuple` / `dict` / `atom` / `atom_set`），所以先**解包再比**，而不是
   遇到形状不一致就跳过——「形状不一样」正是一个被改标的结局变量会溜过去的方式。
2. **嵌套视图**两种形状：置信集是推导字段**加个前缀**（`ar_` / `sar_`），所以
   对应关系就是那个前缀，且**要求完全**——视图上有一片叶子而记录里没有，就是一堆
   数里挖了个洞还没人出声。分层表在推导里是**按列**、在信封上是**按行**，两种拼法
   还不规则（`stratum_weights` 旁边是 `stratum_shift_var_xx`），所以那张映射**写
   出来**而不是猜；猜一条在六个里对三个的规则，会让另外三个不被检查且沉默。
3. **推导没记的那三格**（这一层有多少单位、按工具分成几组），押在把它们跟记录下来
   的东西联系起来的**算术**上：权重是这一层占样本的份额，两个臂加起来是整层。再
   加上「一张表的两行是两个不同的格」——**改标某一行会落在已经被占的格上**，这是
   「这一行说的是哪一层」在没有记录时唯一还成立的事实。

**顺序就是含义。** 这条检查放在推导规则**之后**而不是之前。放在前面，它会在
「重算该量的那条规则」跑起来之前就替一个被篡改的推导作答，那些规则在公开门上就
**再也不会被跑到**——套件当场把这件事说了出来：22 个篡改**记录**的测试开始因为
**拒错了原因**而失败。

**三处被诚实答案纠正的先入之见，都留在注释里。**
- 推导 inputs 是**带包装**的（`{"kind":"value_tuple","items":[...]}`），不解包就
  会把诚实的剂量曲线判成不一致。
- 有些名字两边**粒度不同**：推导只记一个判别词（`'corner_unsupported'`），信封记
  整块。两者共有的是 `kind`，那就比 `kind`——沉默会让两个名字慢慢漂开。
- **过度识别路径**的 AR 集在终止步骤里**一个 `ar_*` 都没有**——它的矩矩阵不适合
  推导输入的序列化格式，整套集合由 `verify_iv_overid_numeric` 从矩矩阵重解。于是
  前缀视图的条件写成「这个前缀**整个**不在」而不是列一串方法名：某个方法哪天开始
  只记半套，会被「要求完全」那一条抓住，而不是被一个名字豁免。

**核实方式。** 先让诚实答案过；然后**把那次测量本身留成闸口**——测试遍历信封实际
携带的每一片叶子，逐片扰动、逐片过门，断言除了那条已声明的例外**没有一片能活下来**。
写死一串字段名的测试，会在旁边新加一个字段的那天照样通过；这条会带着新字段自己的
名字失败。另加分母：没有 `numeric_estimate` 的答案必须放行，普通 backdoor 答案
必须照常通过（同名规则若对其中任何一个名字判断错了，会在这里而不是只在 IV 路上
现形）。

**剩下一片，已量过并写进测试。** `first_stage_f_stat`——Stock-Yogo 阈值作用于它、
读者据它判断工具强弱的那个数——**在任何推导步骤里都不存在**。它从原始数据框算出，
而一个 F 是哪两项之比，推导一个字都没记。所以它不是「跟记录不一致的展示副本」，
是**一个没有记录的数**：读者听说工具很强，只有生产方的一面之词。闭掉它要生产方
先把统计量记下来，那是另一件事。

**账。** 基线 11303 → **11319**（新测 14，另 2 条来自按 `__all__` 参数化的清单
测试）；skipped 221 不变。mypy clean（176 files）。分层 Wald 答案上 42 片叶子
现在 **41 片被押住**。

### #514 「这个数是按什么形状算出来的」那一块，自己是分母（2026-09-01）

**现象。** `mechanism_audit` 是读者唯一能知道「眼前这个数经过哪个函数形式拟合
出来」的地方。六个编辑里**五个通过两扇门**：`form` logistic→linear、`method`
改标、`target` y→z、mechanisms 清空、整块删掉。唯一被拒的那个（`settled_by`
改成枚举外的词）是 **schema 拒的，不是任何审计**。

**根因假设。** 已有两条检查都读这块，而且**都是从块出发走**：一条按块里每个
assumption 去台账找那一行，另一条（`_owed_mechanisms` → `_check_channel`）
按块里的 mechanism 数去数台账欠几行。两条都把块当**分母**。

**为什么是根因不是表象。** 因为**分母是唯一永远不会被检查的位置**。把
`mechanisms` 清空，不只是跳过了它自己那条审计——它同时**降低了台账被认为欠下的
东西**。一把尺子可以被剪短，而剪短它的人是拿它量东西的那一方。方向决定了什么
能被发现：单向检查里，被当作参照的那一侧永远免检。

**结构性改动。**

1. **补上反方向**：`_check_every_shape_the_ledger_names_has_a_mechanism`——台账里
   每一条 `layer == "functional_form"` 的行，都必须有某个 mechanism 的 assumption
   认领。**锚在哪里**：一条形状假设之所以进台账，是因为**拟合**声明了它（
   `_check_estimator_channel` 已经钉住这一点——删掉那行会被「assumption_ledger
   drops estimator-declared assumption(s)」拒）。所以每一条 functional_form 行都
   是某次拟合settle下来的形状，读者有权知道是哪次拟合。**按台账的行去问，而不是
   按本模块自己维护的一张 id 表**：层就写在行上，而层与它旁边的 severity 已经
   互相钉死（把 `functional_form` 改标成 `identification` 会被上一级拒——
   identification 的假设不可能只是 `distorting`）。
2. **块对着它是谁的视图的那个原件**：`_check_the_block_describes_the_fit_that_ran`
   ——`method` 必须等于这次拟合报的 method，`assumptions[*].id` 必须在这次拟合
   声明的清单里（「一个机制不引入假设，它指向已经声明的假设」）。

**两处「先想当然、被测量纠正」的地方，都留在代码注释里。**

- **原件不止一个地方。** 起初写死 `numeric_estimate`，**三个诚实结果被拒**：答案
  是**区间**而不是点时（向量 IV 的 Anderson-Rubin 区域）根本没有 `numeric_estimate`，
  而形状照样拟合过——method 和 assumptions 报在 `extensions.anderson_rubin_region`
  上。于是有了 `_the_fit_this_run_reported`：**一次运行把「我拟合了什么」报在
  一个地方，是哪个地方取决于答案是什么**。两处都没有时**拒绝**而不是静默跳过——
  将来第三种答案形状要进这个函数，被告知的方式应该是套件停下来。
- **`target` 一词两义。** 起初拿它对 `numeric_estimate.outcome`，**十七个诚实结果
  被拒**：形状为一个变量拟合时它是变量名，为一个**估计量**拟合时它是估计量
  ——回归校准里是 `d E[y|do(x),Z]/dx`。**一个有两个含义的字段对哪个含义都没有
  见证**，因为能回答其中一个的拷贝对另一个是沉默的。这是发现，不是限制。

**两个字段没有见证，且已写进测试。** `form` 只经这一块到达信封（拟合报的是
method，从不报形状那个词），所以没有可与之不一致的东西；替它编一条规则（「method
里拼着 form」）在结局模型上成立，在 `aipw` 旁边诚实的 `logistic_propensity` 上
就垮了。`target` 如上。两者按房规当作**生产方声明、不重算**，并由
`test_two_fields_have_no_witness_and_this_records_which` 钉住——哪天它们中的
任何一个有了同一次运行写的第二份拷贝，这条测试就是说「记录过期了」的那个东西。

**核实方式。** 先让诚实答案过（点答案与区间答案两种载体都过），再逐条篡改：
清空、删块、改 method、编造 assumption id——全部被两扇门拒绝。另加**分母**测试：
一个没有形状可披露的结构性结果**必须通过**，否则「拒绝」什么都不说明。

**账。** 基线 11295 → **11303**（新测 8）；skipped 221 不变。mypy clean
（175 files）。ASSUMPTION 家族三块现在全部有复核；家族级绑定仍是独立的一题
（见 #513 末段）。

### #513 把程序自己的话抄下来的那两块，没人跟程序对过（2026-09-01）

**现象。** 结果上有两块不是内核的结论，而是**调用者自己的话的副本**：
`llm_proposed_review`（语言模型提议的每条边和每个先验，读者据此决定信不信这张
图）和 `ambiguities`（程序自己的歧义侧信道，按当前 query 过滤）。**十个编辑全部
通过全门**——评审里唯一那条 LLM 边被删掉、多出一条程序从没有过的边、边被改指
到另一对节点、来源被改标成 `pubmed`、整块删掉；歧义副本被塞进一条程序没声明过
的条目、被删掉、被换成另一个 query 的条目、kind 被改写、note 被改写。

**根因假设。** 两块都是**副本**，而仓库里没有任何东西问过「副本跟原件一样吗」。
`bind`/`carried_by` 这条线早就说过：被别的面 carry 只是「怎么到达读者」，对
「有没有人重算过」一个字也没说。这两块更极端——它们**不从任何东西推导出来**，
所以完全可重算，而恰恰因为「没什么可算的」，就没人算。

**为什么是根因不是表象。** 因为副本的危害不在于它算错，而在于**它改起来最便宜、
错起来最贵**：评审少一条边，读者会以为那张图是人画的；而歧义副本更糟——缺口报告
**读这一块**：一条 `kind == "measurement_quality"` 的条目会**压掉**
`measurement_error_concern`（severity important，回归稀释那条警告）。一条凭空
编出来的行同时做了两件事：删掉一条警告，并**为这条警告的缺席提供理由**。

**结构性改动。** 新模块 `themis/verifier/program_copy_rules.py`——「一块把程序
的话说回来的块，拿去跟程序对」。一个模块两条规则一个想法。

- `verify_llm_proposed_review`：重走一遍收集判据（`annotations.source` 里含
  "llm"，大小写不敏感子串；先验的 `provenance` 恰为 `llm_prior`），并**重新誊写
  两种渲染形式**（原子写法、先验键写法）。
- `verify_ambiguity_copy`：按 `query_id` 重新过滤程序的侧信道——没有 `query_id`
  的是全程序关切、到每个结果；带 `query_id` 的只到那一个。**过滤就是生产方全部
  的自由，所以它就是全部要检的东西。**
- **两个方向都检。** 副本缺失不等于副本一致：程序声明了而块沉默，正是这两个面
  存在的理由，也是**纸面上留不下痕迹**的那一半。
- **比较忽略顺序**，因为顺序不是这两块做出的断言（读者看到的是一份清单不是一个
  序列）；而内容上能做的每一种编辑——增、删、改指、改标——都会改变多重集。
- **独立性钉子**：不得 import `themis.output`；并且读的是**调用者提交的程序
  JSON**，不是生产方遍历的那个 typed `Program`——这是两边还能不一致的第二个来源：
  一次把 annotation 丢掉的序列化，对着同一批对象写的检查是看不见的。

**接线。** 挂在 `verify` 里 ROUTE 表那个循环之后，**不进那张表**：它们不属于那个
家族，而且它们的前提是程序 JSON 而不是从中投影出来的图。

**核实方式。** 先让诚实答案过（否则拒掉篡改什么都不证明）：两块都真的在、
带 `query_id` 的条目真的只到它自己那个 query、什么都没提议的程序真的两块都不出现。
然后十个篡改逐条被全门拒绝。另加两条**分母**测试，否则「拒绝」不说明什么：
引用 pubmed 的边**不是** LLM 提议（收集判据不能是「凡有注解都算」），侧信道里一个
裸字符串**不该**被抄过来（生产方跳过没有 `query_id` 可读的条目）。

**两扇窄门仍然接受，这是对的。** `verify_assumption_ledger` 和
`verify_data_gap_report` 按契约只看结果，而这两块**没法拿结果里的任何东西对**。
这是唯一一类「全门理应更强」的断言——它手里有程序。

**留下的（已量过，不是疏忽）。** `mechanism_audit` 仍然可篡改（6 个编辑里 5 个
通过两扇门，唯一那次拒绝是 schema 枚举不是审计）：它说的是「这个数是按什么函数
形式算出来的」，属于 ASSUMPTION 家族，可对的原件是**估计量**（`numeric_estimate`
的 method/outcome）和**假设台账的 functional_form 那些行**——现有检查只做了
mech→ledger 单向。另：ASSUMPTION 与 GAP 两个家族**没有绑定**（ROUTE 有）；不是
忘了，是量过之后发现 `bind_audit` 那个形状套不上——这几个家族的审计分属不同的门、
参数形状各异，硬塞进一张表要么重复跑要么是为了绑定而造抽象。这个「通用绑定该用
什么器械」是独立的一题（候选是行为性闸口而非调用表）。

**账。** 基线 11277 → **11295**（新测 16，另 2 条来自按 `__all__` 参数化的清单
测试）；skipped 221 不变。mypy clean（175 files）。

### #512 窄门比全门强：复跑兄弟审计时抄的是规则，不是门（2026-09-01）

**现象。** 把 `extensions.type_reconciliation` 篡改后过两扇门：observed_scale
从 binary 改成 continuous、n_unique 从 2 改成 400、declared_scale 改掉、整张
checks 清空、那条不一致缺口整条删掉——**5 个 tamper 全部通过 `themis.verify`，
全部被 `themis.verify_data_gap_report` 拒绝**。读者拿到的是「声明为连续的列其实
只有两个取值」这条发现被抹掉后的结果，而全门说它验过了。

**根因假设。** `verify` 复跑一个兄弟面时，伸手去拿的是 `themis.verifier` 里的
**规则**，而它想说的是「那扇门审的**全部**」。门可以长出第二条规则——2026-07-11
的预检诊断 `verify_type_reconciliation` 就是接在 `verify_data_gap_report` 这扇门
上的——手抄的那份副本不会跟着长，也没有任何东西会因此出声。

**为什么是根因不是表象。** 因为这不是 type_reconciliation 一块的事：`verify`
内联的**每一个**兄弟面都是同一个形状（调规则、不调门）。今天只有一扇门有两条
规则；下一扇门长出第二条时，同样的静默分叉会原样再发生一次。而且方向是最坏的
那个——分叉**只会让全门变弱**：门长出的新规则留在门里，只有**点名叫它**的调用者
才跑得到，每一扇窄门都保持满血，唯独那个「我全验了」的入口在悄悄漏。从外面看，
两扇门的行为差别恰好是看不见的那一半。

**结构性改动。**

1. **`audits.bind_rerun`**——`bind` 的同胞，分母就是全部差别。`bind` 问「有哪些
   审计」；这一条问「其中哪些是 `verify` **必须在自己那一趟里跑掉**的」，答案是
   **每一条 artifact=QUERY_RESULT 且不需要 program 的行**。「需要 program」标记
   的是**对答案本身**的审计（链和界都是关于图的断言）——`verify` 自己就是其中
   一条，另一条它按自己的口径非严格地跑（一个还没有验证器的 bounds method 不是
   它的事）。剩下的就是**答案旁边**那些面，它们的失效是单向的：披露不足读起来
   和没什么可披露一模一样，只叫了 `verify` 的调用者永远不会知道——这也正是
   `verify` 会去碰链以外任何东西的全部理由。
2. **kernel 里每个面一个命名单元，两个入口走同一个键。** `_ENVELOPE_SURFACE_AUDITS`
   由 `bind_rerun` 绑定；`verify` 尾部那一串手写调用收成一个遍历（去重后的值），
   八扇公开门各自 `_ENVELOPE_SURFACE_AUDITS["自己的名字"](result)`。于是**一个面
   只有一份可执行的复核**，两个入口不可能审的是不同的东西。缺口那一面本来就是
   两条规则却没有名字——`_audit_data_gap_surface` 就是给它的名字，八周前它缺的
   就是这个。
3. `verify_berkson_error` / `verify_survival_curve` **留在表外**，因为它们在家族
   外：两者都不是公开门（不在 `themis.__all__`，也没有 `AUDITS` 行），`verify`
   里那次调用是它们唯一的调用者，没有第二份副本可分叉。

**一处闸口当场抓住的东西。** `bind_rerun` 里写了 `row.artifact is
Artifact.QUERY_RESULT`——`Artifact` 继承 `EnvelopeName`，那是**故意放弃单例身份**
的词汇表，`test_a_vocabulary_that_gives_up_identity_is_not_asked_for_it` 立刻报了
出来。改成 `==`。

**核实方式。**
- **先让诚实答案过**（否则拒掉一个篡改什么都不证明）：改动后两扇门对诚实结果
  都接受，对**七个** tamper 给出**逐条相同**的判词。
- **行为性证明「一份拷贝」**：把表里某一项换成会抛异常的哨兵，公开门**和**
  `verify` 都必须抛出它——只比对两串名字的测试，在两个入口开始调用不同函数的
  那天照样会过。
- 闸口按房规构造它该说「不」的反例：少绑一个面 → 拒；把 `verify` 或
  `verify_bounds_results`（需要 program 的那两条）绑进来 → 拒；把
  `verify_markov_blanket`（独立工件）绑进来 → 拒；全绑 → 过。
- **一个被证伪的邻项**：两个 recovery 数值审计本来读起来像同一个缺口（它们
  `re_derives_answer=True` 而 `verify` 不跑）。构造出来跑一遍——
  `selection_backdoor_recovery` 的结果 `status` 是 `numerically_solved` 但
  **derivation 是空的**，全门连诚实答案都拒收。那是关于**生产方造出什么**的事实，
  不是审计的缺口，窄门本来就是它的审计路径。仍然绑进表里：哪天这种结果带上了
  链，全门不用谁记得加一行就会审它的那个数。

**账。** 基线 11256 → **11277**（新测 21）；skipped 221 不变。mypy clean
（174 files）。九扇兄弟门现在**全部**是全门的子集（逐门 profile 实测，非按名字
比对）。

### #511 渲染那一半不可能忘，复核这一半没有任何绑定（2026-09-01）

**现象。** #505-#510 把 ROUTE 家族 13 个块从「6 个有复核」补到 13 个。但
「补齐了」和「不补不行」是两回事：这六次补的每一块，当初都是**加进家族时
没人想起要写复核**，而仓库里没有任何东西会因此出声。

**根因假设。** `themis.blocks` 早就把这一类命了名——`Family.ROUTE` 就是
「这个数从哪来」，而 `analysis_report` 用 `blocks.bind(Family.ROUTE, …)` 把
**渲染**那一半钉死了：「a block added to the family cannot reach this section
and render nothing」。**复核这一半没有任何绑定**，于是它只能靠人记得。
六次「忘了」不是六个疏忽，是同一个缺失的绑定被触发了六次。

**结构性改动。**

1. **`blocks.bind_audit`**——`bind` 的同胞，**分母就是全部差别**。`bind` 问的
   是 `rendered_in`：被别的面 carry 的块已经说过了，再要一遍就是要重复。
   `bind_audit` 问的是**整个家族** `declared_as`：`carried_by` 是「这块**怎么
   到达**读者」的事实，对「有没有人**重算**过它」一个字也没说——被 carrier
   转述的数，是生产方的一面之词**说了两遍**。两个分母在 ROUTE 上今天相等，
   在 ANSWER / ASSUMPTION / GAP 上**不相等**，所以这条区别是**对着真实家族**
   钉的而不是对着假设：`counterfactual_cell` 由 `numeric_estimate` carry，
   而 kernel 恰恰要交叉核对它——正因为「被转述」不等于「被审过」。
2. **kernel 里散落的十来处 `if _x_block is not None:` 收成一张表加一个循环。**
   表就是 `bind_audit` 绑的那张，循环遍历它的**去重后的**值——两个块共用一个
   复核（中介的单/联合双生子；IV 的人类面与它的来源）正是「拷贝之间对不对得
   上」这个问题唯一能被问出来的形状，按块逐个跑会把它跑两遍。**表就是真正
   执行的那条路**，否则又是这仓库反复要替换掉的「声明即覆盖」。
3. `_RouteFacts`——一个形状喂所有复核。信封和前提放在一起，是刻意的：有三条
   声明写在**不止一个块**里，只能看见「自己那一块」的复核问不出那个该问的
   问题。

**两处被闸口当场抓住的东西，都留下了。**
- **`facts.block(...)` 这个方法名撞了 `NAMED_DOORS` 里的 `block`**——那是一个
  **申报拒答**的门。`test_a_refusal_says_one_thing_in_every_language` 立刻把
  12 个新调用点报成「转发了一个自己读不出物种的拒答」（1 → 13）。改名成
  `carries`：在这个包里 `block` 已经既指「申报拒答」又指「调整集挡住一条
  路径」，同一个音节上的第三个义项，是读者开始不信任前两个的方式。
- survival 那条复核原本在尾部一串「单向披露面」审计里，随表一起上移到
  per-kind 分派之前，与其余 route 块同处；全量套件不变。

**核实方式。** 闸口按房规**构造它该说「不」的那个反例**才算验过：少绑一个
成员 → 拒（"nothing re-derives route block(s) ['proximal_estimand']"）；
绑一个不属于这个家族的 → 拒；全绑 → 过。第四条对着 ANSWER / ASSUMPTION /
GAP 三个**真实**家族跑，钉住「被 carry 不构成豁免」。

**账。** 基线 11248 → **11256**（新测 8）；skipped 221 不变。mypy clean
（174 files）。**ROUTE 家族 13/13，且现在少一个都 import 不进来。**

### #510 最后两块，以及一个假阳性被证伪（2026-09-01）

**现象。** ROUTE 家族剩下的三个候选，逐条按 #480 的判据篡改：

- `longitudinal_identification`：**7 处篡改 7 处放行**。`identified` 是决定
  这条时变策略**到底给不给数**的那个开关，可以随手翻；处理可以在**时间上
  倒序**、协变量块可以清空、结局可以改名成一条处理。
- `proximal_estimand`：**6 处篡改 6 处放行**。最要命的两处：**两个代理角色
  互换**（不是改个标签——两个角色扛的是**相反**的独立性要求，换过来描述的是
  另一项研究），以及**把「未观测」的混杂命名成一个被观测的变量**——近端
  推断的整个前提被反着说了一遍。
- `survival_curve`：**扫描假阳性，已证伪**。四处篡改（某格的 rmst、某格的
  方差、horizon、某臂的标准化均值）**全部被 `themis.verify` 当场拒绝**。
  它一直是全推的；扫描看不见它，只因为 kernel 把**整份 result** 传给规则，
  而不是按名字传那一块。

**根因假设。** 前两条各有一条很强的复核站在旁边，复核的都是别的东西——
这一族第六、第七例：

- `verify_longitudinal_numeric` 收的是 `numeric_estimate`。它审的是**这个
  开关放行之后的那些数**，从来不审开关本身，也不审开关所声称的那段历史。
- `_rule_proximal_criterion` **确实**在图上重跑 Miao 的 model (f)——但它的
  角色取自 `ctx.query`，不取自这一块。于是「可识别」是**对被问的那个问题**
  成立的，而读者读的那一块可以命名**另一个问题**。

**结构性改动。**

1. `verify_longitudinal_identification`。核两件性质不同的事：**这一块描述的
   得是程序声明的那条策略**（treatments / outcome / confounders_by_time 都来自
   `options.longitudinal`，且**顺序算描述的一部分**——H_k 是照着这个列表走出来
   的，换一对顺序，之后每一时刻的历史都不同了）；以及**判据本身，逐时刻**——
   H_k 里不许有 A_k 的后代，且剪掉 A_k 出边后 A_k 在 H_k 下与 Y m-separated。
   两半分别测，因为只比对声明的检查对任何图都会通过。
2. `verify_proximal_estimand`。这一块**每个字段都是查询的复述**，所以整块可
   核：两端、latent、两个代理**集合**、条件所在的协变量、以及决定用哪套代数的
   channel。**不重复推图**——判据规则拥有那件事，而这些和它对齐之后，它拥有的
   就是同一组角色。代理按**集合**比：一个混杂源的哪个影子被排在前面不是事实。

**两处「第一版是错的」，都由诚实答案抓出来。**
- channel 的判别式是**类型**不是字段（查询携带 `DiscreteChannel` /
  `BridgeChannel`），而信封里是 token——因为读者面无法按 Python 类分派。
  第一版写 `getattr(channel, "kind")`，**静默恒真**，篡改 `channel_kind` 照过；
  按类型判后才真拒。
- 离散通道**两侧各只收一个代理**（求逆的是 k×k 测量矩阵），所以「两个影子」
  只能在 bridge channel 上成立。集合比较那条因此改成**对着规则**测而不是走
  数值门：要钉的是**比较方式**，走估计器就变成在测 bridge 估计器了。

**顺带记一笔（与 #506 同一条边界）。** 时变那条路线 `identified=false` 的
结果**没有 derivation**，`themis.verify` 在读任何块之前先拒绝无 derivation 的
结果。所以这个开关的 **false 那一面经报告到达读者、经这扇门到不了**。新测里
把它作为事实钉住（直接调规则证明规则接受诚实的拒答、并拒绝把它翻成 true 的
伪造），没有借此扩大改动。

**账。** 基线 11228 → **11248**（新测 20：时变 11 + 近端 9）；skipped 221 不变。
mypy clean（174 files）。

**ROUTE 家族 13/13 全部交给验证器。** 下一步是把这件事从「做到了」变成
「不做不行」：在 verifier 侧加 `blocks.bind(Family.ROUTE, …)`，与
`analysis_report` 早就有的渲染绑定对称。

### #509 一条判据两个块，就该只转录一次（2026-09-01）

**现象。** 中介分解答案里，`extensions.mediation_decomposition`（以及它的
联合孪生）——告诉读者「你拿到的是哪一种分解、它要什么才成立」的那一块——
把 `mediator` 改成结果变量、把 `mediator_valid` 翻成 false、把某一臂的
`identifiable` 从 true 翻成 false、把 `adjustment` 换成随便一个集合，
`themis.verify` 全放行（单中介 6 处 5 处放行，联合 4 处 4 处放行；唯一被拒
的那处是**假设台账**发现自己被少报，不是这一块被重推）。

**根因假设。** `verify_mediation_numeric` 收的是 `numeric_estimate`——那是
另一个对象。这一族第五条，形状与 #508 同类：**旁边有一条很强的复核，只是
它复核的是别的东西。**

**结构性改动：一条判据只转录一次，两个块共用。** 把 Pearl 2001 的四条件
写在**中介集**上（VanderWeele-Vansteelandt 2014），单中介就是它在**单元素**
上的取值——把每个成员的出边都剪掉的图，在单元素时就是把那一个成员的出边
剪掉的图；逐成员的分离在单元素时就是那一条分离；而成员限制（M4 / C2）在
生产方那边**本来就写成集合形式**，两条路线都是。所以给单中介再写一份转录，
只会多一个让两者对同一条定理起分歧的地方。

    M1  Y ⊥ X | W        in G[x̄]
    M2  M_j ⊥ X | W      in G[x̄]，逐成员
    M3  M_j ⊥ Y | X, W   in G[m̄]，每个成员的出边都剪掉
    M4  W 不含 X 的任何后代

    C1  Y ⊥ X | W 且 Y ⊥ M_j | W   in G[x̄, m̄]
    C2  W 不含 X 或任何成员的后代

**两种声明被区别对待，这个不对称就是设计。** 「可识别」**点名了**承载它的
那个 W，所以能被完整核实——那个集合要么满足条件要么不满足。「不可识别」
**不点名任何见证**，而且它是**从读者手里扣下一个答案**的那种声明，所以按
`c_factor` / `joint_general_id` 的老规矩**反向搜索钉住**：存在而未被点名的
合法 W 就是失败。

**明确不重推的一项。** `failed_condition` 只核**一致性**不重推，区别正是
要点：被点名的是「沿固定顺序走得**最远**的那个候选」的标签，而且那一遍
搜索是**去掉成员限制**跑的（好让中间混杂能被叫出名字而不是被藏住）。
「沿某顺序走得最远」是那次**搜索**的性质、不是**图**的性质，重推它就是在
转录生产方的策略、按构造同意。**是**图的事实的那一半——「恰好在有条件失败
时才点名一个条件」——照核。

**`strategy` 上两块真的不同，但不同的是词表不是规则。** 联合块有
`nde_nie+cde` 这个成员（两臂都可识别时如实说），单中介块没有、只报更强的
那一个。用哪套词表由块自己的键（`mediators` vs `mediator`）读出来——和
分辨 `mediator_valid` / `mediator_set_valid` 用的是同一个判别式。第一版
把单中介的规则套到联合块上，**当场被诚实答案拒掉**，这正是「诚实答案先要
能过」这条纪律该抓的。

**核实方式。** 改前 10 处篡改 9 处放行。改后 10 处全拒，三种诚实答案
（单中介、联合、以及中间混杂那张自然效应真不可识别的图）全过。反向搜索是
**无上界**的（生产方那边 |W| ≤ 3），全量套件通过说明这一步没有拒掉任何
诚实答案——若哪天拒了，那是生产方搜浅了的真发现，不是误报。

**账。** 基线 11206 → **11228**（新测 22）；skipped 221 不变。mypy clean
（174 files）。ROUTE 家族 13 个成员，现在 **10** 个交给验证器，剩 3 个：
`longitudinal_identification`、`proximal_estimand`、`survival_curve`
（后者很可能是扫描假阳性）。

### #508 把每个数都重算对了，只是算的是另外几个变量（2026-09-01）

**现象。** 一个处理**向量**的 Anderson-Rubin 置信域答案，把
`extensions.vector_iv_identification` 里的 `instruments` 改成两条**处理
自己**、改成**结果变量**、把 `treatments` 换成旁观者或倒序、把 `outcome`
换成一条处理、`conditioning` 凭空造一个、`relevance` 说某工具变量推动
结果变量（或什么都不推动）——`themis.verify` **7 处全放行**。

**根因假设。** `verify_vector_iv_region` 是这条路线上最扎实的复核之一：
从记录下的二阶矩重推被反演的二次型、在 A 的**特征基**里重新分类形状
（不照抄生产方的分情况）、重推中心、2SLS 点和每一个坐标投影，还把两套形状
词表的定理**双向**钉死。但那些矩**到达它时已经是用某几列算好的了**。于是
「这个域的每个数都对」和「这个域是用对的变量算的」是两句话，而只有前一句
有人验。命名那几个变量的块——报告读的那一块——谁也没读。

这是 #505 / #506 / #507 之后同一族的第四条，但它的形状值得单独记：前三条
是「块旁边有一条审 derivation 的规则，看起来覆盖了」；这一条是**块旁边有
一条极强的、审同一条路线另一个对象的数值复核**，强到更容易让人以为覆盖了。
**复核的强度不代表复核的对象。**

**结构性改动。** `verify_vector_iv_identification`，全部从图重推：

- **有效性读在处理集上，不是标量条件的合取。** 边是**同时**从**每一条**
  处理上剪掉的，所以一条只经由向量里**另一条处理**到达结果的工具变量，
  在这里**有效**（那条路在干预内部），而标量检验会拒绝它——在标量语境下
  另一条处理是混杂。**两面都在测试里跑**：新测专门造了 z1→a、z1→b 的图，
  钉住它被接受、`moves == ["a","b"]`；反向那面由「w→y 的旁观者被塞进
  instruments」钉住。
- `conditioning` 不许碰处理／结果／工具变量本身，也不许含**任何**处理的
  后代——固定向量里某一条的中介，坏掉的东西和标量情形一样。
- `treatments` **按顺序**核，不排序掉：域的坐标投影就是按这个列表索引的，
  读者「哪个区间属于哪条处理」读的正是这个顺序，排序掉会让两者悄悄不一致。
- `relevance` 是**报告项不是要求项**（域的覆盖率与工具变量推不推得动无关，
  它预测的是域回不回得来有界）——但**报告不等于不查**。空的 `moves` 也是
  一条关于图的事实，所以照样重推，且在**原图**里推（相关性住在那里），
  不在被剪过的图里。

**核实方式。** 改前 7 处篡改 7 处放行。改后 7 处全拒，诚实答案照过，
「经由另一条处理」的诚实答案也照过。新测 12 条。

**剩余分母。** ROUTE 家族 13 个成员，现在 8 个交给验证器，还剩 5 个：
`mediation_decomposition`（已篡改核实：6 处 5 处放行，唯一被拒的那处是
假设台账发现自己被少报，不是这一块被重推）、
`mediation_joint_decomposition`（4 处 4 处放行）、
`longitudinal_identification`、`proximal_estimand`、`survival_curve`
（后者很可能是扫描假阳性，`_verify_survival_curve_rule` 整份传结果）。
全部补齐后，在 verifier 侧加 `blocks.bind(Family.ROUTE, …)`，让「加了
route 块却没有重推」从「不太可能」变成「不可能」——与渲染那一半对称。

**账。** 基线 11194 → **11206**（新测 12）；skipped 221 不变。mypy clean
（174 files）。

### #507 同一个问题换了个容器，审计就留在原地了（2026-09-01）

**现象。** 一个 `do(a, b)` 的联合答案，读者被告知「控制 z」。把
`extensions.joint_identification.adjustment_set` 清空、换成结果变量、换成
向量里的另一条处理，把 `treatments` 少写一条或写成旁观者，把
`conditioned_on` 凭空造一个——`themis.verify` **全部放行**。同一份信封上
标量版的 `extensions.identification.adjustment_set` 是被逐条重推的
（edge deletion + verifier 自己的 m-separation）。

**根因假设。** `verify_identification_pattern` 的分派键是
`identification.pattern`。联合路线的识别声明**不写在那一块**：它另开一块
`joint_identification`，`pattern` 是另一套词表，而 schema 自己就写着这两套
"are disjoint"。于是一个**按容器绑定**的验证器，对同一个读者问题的第二个
容器结构上就够不着。derivation 那头有 `identify_via_joint_backdoor` 终结
规则在审，块这头没有——和 #505（IV）、#506（回路）第三次同一个病：
**同一个问题换了个容器，审计就留在原地了。**

**先量分母。** 这次没按 grep 的名字数，按仓库自己的分类数。
`themis.blocks` 的 `Family.ROUTE` 就是「这个数从哪来」这一类块，
`analysis_report` 用 `blocks.bind(Family.ROUTE, …)` 钉死了每一个成员都得
有渲染器——「a block added to the family cannot reach this section and
render nothing」。**渲染那一半不可能忘，复核这一半没有任何绑定。**
量出来：13 个 ROUTE 成员，公开门口交给验证器的 **6** 个
（identification / iv_identification / feedback_loop /
transport_identification / selection_recovery / missing_data_recovery，
后两个之外的四个里有三个是 #505-#507 这几天补的），**7** 个没有
（vector_iv_identification、joint_identification、
longitudinal_identification、mediation_decomposition、
mediation_joint_decomposition、proximal_estimand、survival_curve）。
扫描单向可靠：`survival_curve` 走 `_verify_survival_curve_rule(result)`
整份传结果、名字不出现在调用点，很可能是假阳性；
`proximal_estimand` 那头的 `verify_proximal_effect(derivation, ctx, …)`
审的是 derivation，多半是真的。**逐条仍要按 #480 的判据篡改核实**，本条
先关掉 `joint_identification`。

**结构性改动。** `verify_joint_identification`：

- **判据是处理集的后门，不是标量后门的合取。** 边是**同时**从**每一条**
  处理上剪掉的——一条从某处理穿过另一条处理进入结果的路径在干预**内部**，
  不是后门；被固定的集合不许含**任何**处理的后代，而不是某一条的。这个
  差别正是新测里两条用例的分界：另一条处理，作为路径上的一环是合法的，
  作为被固定的变量是非法的。
- `treatments` 必须就是这个查询干预的那个集合，`conditioned_on` 必须就是
  这个问题条件的那个集合——判据在哪个集合上验的，得是问题问的那个。
- `joint_general_id` 是**否定**声明（正因为不存在调整集才可识别），所以
  像 `c_factor` 一样**被反向搜索钉住**：存在而未被点名的合法联合调整集就是
  失败。两面都跑：存在的图上拒掉这个声明，不存在的图上（a↔y 潜变量 + 中介）
  接受诚实答案。

**核实方式。** 改前 7 处篡改 7 处放行。改后 7 处全拒，三种诚实答案全过
（joint_backdoor 带集合的、joint_backdoor 空集的——两条处理之间的潜变量
被联合干预剪掉了，本来就不用调整——以及真正的 joint_general_id）。

**顺带记一笔量测方法的坑。** 通用「逐叶篡改」扫描曾把这一块报成
ACCEPTED **在修好之后**，原因是扫描对单元素列表的扰动是
`[v] → [v, v]`、对双元素是倒序，两者作为**集合**都没变，而判据看的是集合。
扰动必须真的改变被检验的那个量，否则「通过」是扫描的假阴性而不是结论。

**账。** 基线 11183 → **11194**（新测 11）；skipped 221 不变。mypy clean
（174 files）。

### #506 一条路线有两扇门，它的诚实性只在一扇门上被测过（2026-09-01）

**现象。** 两件事，同一条路线（#450 的反馈回路）。

1. `themis.run` 跑一个声明了 feedback 回路的程序，返回
   `structurally_solved` 的工具变量答案；把这份答案原样交给
   `themis.verify`，**被拒**：「structural effect derivation must end in
   identify_via_mediation, …」。诚实答案在公开门口被拒。
2. 数值门（`themis.estimate`）那份能过，但 `extensions.feedback_loop`
   ——报告和缺口清单真正读的那一块——每个字段随便改都能过：回路可以挪到
   程序**从未声明**的一对变量上、`treatment`/`outcome` 可以改成旁观者、
   Haavelmo 归约可以从一个真用了工具变量的答案旁边删掉。

**根因假设。** 两条同一个根：**这条路线有两扇门，而它的诚实性只在一扇门
上被测过。** 该路线的测试文件里每一条测试都带 `frame` 夹具、走
`themis.estimate`；同一个程序经 `themis.run` 产出的那份答案，从来没有
任何东西验证过。于是：

- 结构门的终结名单（`verify_effect_structural` 里手写的一串规则名）从没
  被这条路线碰过。它是**唯一**以 `identify_via_iv` 结束一个 effect 查询的
  路线（无回路时同一张图是 `needs_investigation`），而那个终结对
  `identify` 合法、对 `effect` 不在名单里——没人发现；
- block 之所以没人复核，和 #505 里 IV 那条同因：旁边有一条 derivation-step
  规则（`feedback_loop_withdraws_adjustment`）确实从**程序**重推了回路，
  于是 block 看起来被覆盖了。它不是同一个对象——该路线现有的两条伪造测试，
  篡改的都是 `step["inputs"]`。

**为什么是根因不是表象。** 把 `identify_via_iv` 加进名单能修好第 1 条，
但名单里一个光秃秃的名字说的是「这条规则可以做结论」，而这里的真相要窄
得多：**只有在同一条 derivation 里带着那张撤销许可证时，effect 查询才可以
以工具变量结束。** 没有回路，一个 effect 查询以 IV 结束，就意味着把一个
本来有 backdoor 答案的问题换成了靠线性假设的 IV 答案——正是
`feedback_loop_withdraws_adjustment` 自己 docstring 里说「值得伪造」的
那件事。往名单里加一个名字，是把这句真话写成半句。

**结构性改动。**

1. **终结按前提准入，不按名字准入。** effect 以 `identify_via_iv` 结束，
   当且仅当同一条 derivation 里有 `feedback_loop_withdraws_adjustment`。
   缺了它，同一条 derivation 就是「一次普通的 IV 升级，发生在一张
   backdoor 本来够用的图上」——该拒。
2. **`verify_feedback_loop`：从程序重推那一块。** `left`/`right` 必须是
   程序真声明的一对 feedback（和 step 规则同一个来源、不同的对象）；
   `treatment`/`outcome` 必须是这个查询自己的两端——回路够不够得着估计量
   是关于**这一对**的事实，记着别人的查询就是在声称一件自己没建立的事；
   `reduction` **两面都查**：写了，回路必须正好在两端之间（Haavelmo 归约
   正是「在两端之间」买来的）；没写，旁边就不许站着工具变量——回路之下，
   要么把这一对读成两个方程、工具变量识别其中一个系数，要么什么也识别
   不了，删掉归约的读者拿到的是另一个量。

**明确不做的取舍。** `withdrew` 仍是生产方的一面之词。它列的是 route id，
重推「这个回路拿掉了哪些路线」就得读生产方的路由表——verifier 至今不
import `themis.routing`，我不做第一个；照抄了也就是按构造同意，恰是独立
复核定义上要排除的。

**顺带量到的一条边界（本次不动）。** 这条路线三个结局里有两个是
`needs_investigation` 的拒答，它们**带着 `feedback_loop` 块但没有
derivation**。`themis.verify` 在读任何块之前就先拒绝无 derivation 的
结果（「external agents cannot audit an answer without its reasoning
chain」）。所以那两个结局的块经报告和缺口清单到达读者，经这扇门则**完全
到不了**。这是关于「公开审计从哪里开始」的事实，不是关于这一块的；新测
里把它作为事实钉住（直接调规则本身证明规则接受它们），没有借此扩大改动。

**核实方式。** 仍是 #480 的判据。改前：结构门连诚实答案都拒，数值门 6 处
篡改 6 处放行。改后：两扇门都接受诚实答案，4 处当场被拒（第 5、6 处是上面
声明放弃的 `withdrew` 两式）。新测 14 条，两扇门各跑一遍同一批篡改。

**一条既有测试改了断言。** `test_a_withdrawal_citing_a_loop_nobody_declared_is_refused`
把程序里的 feedback 语句删掉再验——现在这一份答案在**两个**地方都是伪造
（许可证和块都引了一个不存在的回路），块的拒答先到。两种拒答都对，测试
名说的事照旧发生；规则单独的覆盖由它下面那条保住——程序声明了两个回路、
step 指错一个而块是诚实的，那里只有规则会说话。

**账。** 基线 11169 → **11183**（新测 14）；skipped 221 不变。mypy clean
（174 files）。

### #505 一句「另一层已经核过了」，核的是另一个东西（2026-09-01）

**现象。** 造一份工具变量答案，把读者面上的
`extensions.identification.instrument` 改成**结果变量本身**——「用 y 当 y
的工具变量」——`themis.verify` 通过。把 `conditioning` 改成准则明令禁止的
集合，通过；把 `required_assumption` 改成另一条前提，通过；
`extensions.iv_identification`（IV 路线的报告真正路由的那一块）整块的每个
字段，全部可以随意改，全部通过。同一处改动落在 **derivation** 上则当场被
拒：`RuleCheckFailed: iv_criterion_check: x, y, and instrument must be
distinct`。

**根因假设。** `verify_identification_pattern` 是「这个数从哪来」这句话的
验证器，按 block 的 `pattern` 分派。碰上 `instrumental_variable` 它立即
`return`，并在原地写下理由：这些是「premises the iv_criterion derivation
rule already re-derives」。这句话对 derivation 是真的，对这个 block 什么也
没说——derivation 带的是它**自己那份** instrument 拷贝，而没有任何规则把
两者联系起来。于是四条识别路线里唯一「点识别还欠一条前提」的那条，成了
唯一读者面无人复核的那条。

**为什么是根因不是表象。** 同一个函数对**未知** pattern 是会报错的
（`_err(f"unknown pattern {pattern!r}")`），也就是说枚举覆盖闸口一直在，
而且它通过了——因为这个成员被点名了，只是点名去做「什么也不做」。真正
出问题的是：一句停手的理由，被允许指向和被停手对象**不同的另一个东西**
（derivation 的输入 vs 读者的 block），而仓库里没有任何东西能分辨这两者。
只补 IV 这一支，这条毛病原封不动——下一个「因为另一层会查」而站开的
block 级验证器，同样不可证伪。

**结构性改动。**

1. **没有一个分支再不复核就返回。** IV 支移到图已解码之后，用**这一块
   自己**持有的字符串重新推导 Pearl 判据：IV1（G 中 Z 与 X 在 W 下
   m-connected）、IV2+IV3（G[x̄] 中 Z 与 Y 在 W 下 m-separated），走
   verifier 自己的 m-separation，和它三个同胞（backdoor / front_door /
   c_factor）一模一样。报错信息带上是哪一半没过——「什么都推不动」和
   「自己另有一条通往结果的路」是两种不同的抱怨。
2. **判据只转录一次，两个调用方。** `iv_criterion_holds` 提到
   `verifier/rules.py` 顶层，`_rule_iv_criterion_check`（审 derivation 的
   输入）和 `verify_identification_pattern`（审读者看到的 block）都调它。
   同一句话在离 derivation 两步远的地方到达读者，第二份转录只会多一个
   互相打架的地方。
3. **两块都审，且互相钉死。** 这句话写在两个 block 里——
   `identification` 是人类面，`iv_identification` 是报告路由的那块——
   kernel 现在把后者也送进同一个验证器（`verify_iv_surfaces`），各按自己
   的字段复核，谁也不靠对方背书。**过判据不等于对得上**：一张图可以有
   两个合法工具变量，那时两块各自都能过，而读者看到的是一个、数是另一个
   算的。所以共有字段还要**相等**——这正是信封里另外三份 display copy
   早就在守的规矩：「a tamper of the display copy alone cannot pass」。
   两块都改成 `z2` 则**放行**：那是这张图支持的另一个诚实答案，规则管的
   是分歧，不是生产方的偏好。
4. 相等只在**两边都有时**要求。反馈回路那条路线故意不在人类面写
   `required_assumption`，并在原地写明理由（回路下的前提是 gap report 完整
   说出的一句话，这里再写一遍就是同一主张两个作者）。**缺席**是那条路线
   关于「读者读到哪一句」的决定；**不同的一句**不是。

**明确不做的取舍。** `alternatives_count`（结构搜索找到多少个其它合法
(Z, W)）仍是生产方的一面之词，本次不复核。理由不是成本：产它的
`iv_sets` 把 |W| 上限设成 3、每个 Z 只留 subset-minimal 的 W——那是生产
方的**搜索参数**，不是定理。验证器要么照抄这两个参数（那就是按构造同意，
恰是「独立复核」定义上要排除的），要么自定一套而去拒绝诚实答案。所以
数目留给生产方，被数目所计的那个工具变量不留。

**核实方式。** 按 #480 的判据——不问「审这件事的代码写了吗」，问「产出方
真产出的那个东西，走完整公开入口能不能过」。改前：7 处篡改 7 处放行。
改后：6 处当场被拒（第 7 处是上面声明放弃的 `alternatives_count`），诚实
答案照过。新测 17 条，含两张专门造的图：两个合法工具变量的那张（分离
「过判据」与「对得上」），和把 IV1 失败与 IV2+IV3 失败拆开的那张。

**账。** 基线 11152 → **11169**（新测 17 + `verifier/__init__` 清单闸口与
mypy 那两条本来就该过的）；skipped 221 不变。mypy clean（174 files）。

### #504 只在失败时开口的判断，读者读不出它有没有开过口（2026-09-01）

**现象**：后门一族的每次运行都会做两条**靠拟合模型来下的判断**——重叠（拟合 P(处理|调整集)，
看有多少样本落在 [0.05, 0.95] 之外）与准分离（拟合 P(结局|处理,调整集)，看有多少落在
[0.01, 0.99] 之外）。两条都**只通过缺口说话**，而缺口天生只在出错时抬头。端到端实测（连续
混杂 z，`scale: continuous`，所以没有格子可数）：

```text
弱混杂    倾向分 [0.192, 0.769]   带外 0.0%   信封里：一个字都没有
强混杂    倾向分 [8.05e-10, 1.000] 带外 60.2%  信封里：仍然一个字都没有，数字只活在缺口的句子里
准分离帧  P(Y|·) [5.66e-17, 1.000] 带外 70.8%  同上
```

**代价有两处，第二处是 #503 刚打开的**：(1) 读者分不清「查过、没问题」和「压根没查」；
(2) 台账那一行**无从重算判决**——强混杂那一帧的答案里，缺口清单说「重叠被违反」，假设台账
同一屏上说这条前提 `checked=null`（没人核过）。**连续调整集上计数没有格子可数，拟合是唯一
的见证人**，所以 #503 关掉计数那一半之后，剩下的正是这一半。

**根因假设**：**一条判断只通过缺口说话，就等于只在失败时留痕；而「没留痕」在信封上和「没
做过」是同一句话。** 判决不是没地方放（#503 已经建好 `checked`），是**被判决的那件事本身
没有落在信封上**。

**为什么这是根因不是表象**：同一个仓库里两条同类判断早就做对了，而且把判据写在自己的
docstring 里——`REGULARISATION_IS_MOVING_THE_ANSWER` 与 `TREATMENT_BRIDGE_LEAVES_ITS_RANGE`
都写着「the finding is arithmetic on a statistic the estimate already carries」，所以它们
的缺口是可重算的、通过那一面也读得出来。**重叠与分离是这条判据的两个例外**，不是两个独立
的小疏漏。表象修法（给台账特判一下重叠）会让第三条同类判断再犯一次。

**做法**：

- 一份形状 `$defs/fittedRange`，两处落地：`numeric_estimate.fitted_overlap`（P(处理|调整集)）
  与 `numeric_estimate.outcome_saturation`（P(结局|处理,调整集)）。**不论落在判定线哪一边
  都写**。
- **阈值随发现一起走**（`threshold` 是这份形状的必填字段），不许任何读者复述它。原本它要被
  抄进三处（估计层、判决生产者、验证器），而判决声称的是「**这批数据**否决了这条前提」——
  它必须和旁边那条缺口在**每一帧上**同时成立，包括有人重调判定线之后。
- 缺口改成对这份记录做算术，于是「缺口在不在」和「带外份额有没有超过阈值」按构造是同一件事。
- 台账：新增 `Check.FITTED_PROPENSITY_RANGE`，`a_pass_settles_it=False`，判的是同一条
  `positivity_overlap_of_treatment_arms`。**表里排在计数之前**（后写的赢）：**计数就是那个
  条件本身，拟合只是估计它**——同一帧上逻辑回归会跨格子平滑，实测把一个经验处理率恰为 0.000
  的层估成了舒服的 0.091。所以有格子可数时计数说了算并且 `held`，没格子时拟合是唯一的见证
  人并且**最多只能 `not_refuted`**。三值词表在这里第一次同时用上了两个非拒绝档。
- **分离那一块不上台账，这是决定不是遗漏**：旁边那行写的是「outcome 用 logit 回归建模」——
  它陈述的是**做了什么**，不是一条数据能否决的前提。给它一个判决，是让一套词表去回答没人问
  的问题。这句话写进 schema 描述里。

**新闸口，每一条都构造了它该说「不」的那个反例**：把拟合出的否决软化成 not_refuted、把
not_refuted 夸成 held、**只动记录上的阈值不动那一行**（从另一侧撞同一个不一致）。

**一道既有闸口把这个形状的名字改对了**：区间普查（「一对端点的宽度是关于什么的事实」）当场
拒收新形状的 `lower`/`upper`——而 `Width` 的三个成员（抽样 / 识别 / 外带）对它**没有一个是
真的**：这对数不是估计的端点，是**这次判断自己选的一条常数带**，答案里没有任何东西能让它变
窄。**正确的修法是名字而不是给词表加第四个成员**：叫 `band_lower`/`band_upper`，它就不再邀请
那个普查存在的目的所要防的读法。给 `Width` 加一个「宣告的带」会稀释一套三个成员都在讲识别与
抽样的词表。

**顺带记一次我自己的失手（被两道闸口当场抓住）**：改名脚本的锚点不唯一，一次替换命中三处，把
`causationQuantity` / `causationEstimate` 的 `lower`/`upper` 一起改了。区间普查的**反向**规则
（「登记了而 schema 没有这对」）和 #501 的 types.ts 对账闸同时报错。教训是老的：**机械替换先
断言命中次数等于预期，而不是只断言 ≥1**。

**基线**：11126 / 221 → **11152 / 221**。skip 数不动：这次没有新的 Python 词表类，`Check` 只是多了一个成员。

**方法论沉淀**：(354)**一条判断如果只通过缺口说话，它就只在失败时留痕，而「没留痕」和「没
做过」在信封上是同一句话**——找法：对每条 GapKind 问一句「没有它的时候读者知道什么」，答案
若是「不知道查没查」，那条缺口缺一份记录。42 条里已核实两条做对了（判据写在它们自己的
docstring 上：**发现要是信封已带的统计量上的算术**），这次补上剩下的两条例外。
(355)**一个被多方判断的阈值应该跟着发现走，而不是被每个读者各抄一份**——三处各存一份是三次
分歧机会，而判决声称的是数据的态度，它和缺口必须逐帧一致。
(356)**同一条前提有强弱两个见证人时，把「通过值多少」编进见证人而不是编进调用点**——计数
settles、拟合只 not_refuted，这一条一旦写在调用点，下一个作者就会让模型的意见冒充数据的答案。
(357)**一道普查拒收一个新形状时，先问它问的那个问题对这个形状成不成立**——三个答案都不真，
说明该改的是名字，不是给词表加第四个成员；**给一套讲识别与抽样的词表加一个「宣告的常数」会把
它稀释成「任何两个数」**。

### #503 台账记得下「可检验」，记不下「这一次检验过，而这批数据否决了它」（2026-09-01）

**现象**：假设台账每行有 `testable`，它是**静态属性**——这条假设原则上有没有人能去核。它对
「这一次有没有人真去核了」一个字都不说。于是一条**本次已经检验、并且被这批数据否决**的前
提，在页面上和一条从来没人看过的前提长得一模一样：同样的严重度、同样的 claim、同样一个
「可检验」，没有任何判决。补偿性的说明落在几屏之外的缺口清单里，还得先说一句「这不是缺口」。

全量扫一遍分母（一次跑完整套测试、把每个信封 dump 下来）：

```text
3610 个信封，1288 个带台账；162 个不同的假设 id，其中 73 个标了 testable
本次真的会跑、且结果已经在信封里的检验：逐层两臂计数 / Sargan / 稳健 Hansen J / ACR 边际权重
```

**判决其实一直在被偷运，两条路**：

1. **重叠（positivity）——改的是假设的名字**。逐层计数一旦发现有层只含一个处理臂，估计器就
   声明**另一个 id**（`positivity_violated_some_strata_hold_one_arm`）。发现被塞进了「它所发现
   的那个东西」的名字里。代价有两处，第二处更隐蔽：**数清了且全部合格的那一帧，和根本没人数
   的那一帧，说的是同一句话**——两者都只写 `positivity_overlap_of_treatment_arms`。
2. **过度识别——只在被拒绝时说，而且说在缺口里**。没有缺口既可能是「检验过、没拒绝」，也可能
   是「压根没做这个检验」。

**根因假设**：**台账行上没有「本次做了什么检验、结论是什么」这个字段**，所以每个生产者各自
找地方安放一个判决——一个改名字，一个写进别的板块。**「可检验」和「已检验」是两个不同强度的
问题，而只有前一个有位置。**

**为什么这是根因不是表象**：表象修法是给重叠那条特判、或者在缺口里多写一句。但两条偷运路径
互不相干、形态完全不同，却是同一个空缺的两个症状——这正是「缺一个字段」的样子。而且判决是台
账上**唯一一个生产者可以凭空断言、读者无从反驳**的东西：一句「这条被否决了」如果只是被写下
来，验证器没有任何东西可以拿去对。**所以字段本身不够，字段必须可从信封里的证据重算**——这一
条反过来决定了哪些检验现在能进：**只有把结果留在了信封里的那几个**。

**做法**：

- `ledger.Verdict`（`held` / `not_refuted` / `refuted`）+ `ledger.Check`（跑的是什么）。
  **三个成员不是两个**，因为「没能拒绝」不等于「已经成立」；而**一次通过到底值哪个词，是检验
  自己的属性**（`Check.a_pass_settles_it`），不归调用点：**清点格子是把条件本身数了一遍，
  假设检验没拒绝则什么也没排除**。生产者只报「这次检验失败了没有」，词由 `ledger.checked` 给。
- **重叠的分叉删掉**，`overlap_assumption(support)` 变回一个常量 `OVERLAP_ASSUMPTION`；逐层计
  数改为写进信封 `numeric_estimate.stratum_support`（`cells` / `supported` /
  `extrapolated_share`），**不论结果如何都写**——只在出错时留下的记录，读者读不出通过的那一
  面。原来那句「声明一条自己已经量出来是假的假设，比不检查更糟」在当时是对的，因为**判决当时
  无处可放**；现在有了，前提就该说回一条，判决挂在行上。
- 排序多一个键：同一严重度里 **refuted 的行排在前面**。不是给它一个自己的严重度——被否决的前
  提让答案损失的仍然是它那一层损失的东西；变的是读者遇见它的次序。
- 台账首行原来结尾是「假设本身的真假需要你逐条审核」，在没有任何一条能记录检验时它对每一行都
  成立。**能记录的那一刻它就不成立了**：改成「其中 {n} 条这一次已经检验过（结论标在那一行
  上）」。

**验证器独立重算，两个方向都验**：`assumption_ledger_rules` 自己写了一套 reader 去读同一批数
字（表按惯例重述、由测试钉死相等，**reader 不共享**）。夸大被抓是因为证据被重读；**沉默同样被
抓**——一次跑出了某项检验的结果、而它该判的那一行只字未提，正是这个模块存在的那种缺陷。另外
三条：判决必须落在该检验管的那条 id 上、两个检验都在时必须报稳健的那个、一行不能同时说「没人
能核」和「本次核过」。

**故意不进来的一族**：**相关性**（第一阶段 F）。那个统计量是**支持**该假设的证据，而
held / not_refuted / refuted 这套词说不出「有支持」——把其中一个掰弯去表示它，就是把判决往上偷
运一层。

**新闸口，每一条都构造了它该说「不」的那个反例**：把 refuted 软化成 not_refuted、把
not_refuted 夸成 refuted、把「没能拒绝」写成 held、真有结果却删掉 `checked`、判决挂到邻居那一
行、两个检验都在时报了较弱的 Sargan、`testable=false` 的行带判决、把 refuted 的行埋到同级下面。

**端到端两族各两帧**（数值是跑出来的）：

```text
两个工具、都有效        hansen_p=0.149  不拒绝 → not_refuted / robust_hansen_j
两个工具、z2 破除外生    hansen_j=1047.0, p=1.09e-229 拒绝 → refuted / robust_hansen_j
                        （点估计 2.108，真 β=1.5，答案照样返回——所以那一行必须说话）
三层、每层两臂齐备      cells=3 supported=3 → held / stratum_arm_counts
三层、一层只有一个臂    cells=3 supported=2 外推占 25.1% → refuted / stratum_arm_counts
```

**改动**：`ledger.py`（两个词表 + `checked` + `leads` + 首行改写 + 把 Verdict 并进
「没有生产者能写的成员就是死成员」那道进程内检查）、`result_orchestrator.py`
（`WHAT_THIS_RUN_CHECKED` + `adjudicate` + 次级排序键）、`assumption_ledger_rules.py`
（独立 reader + 双向闸 + 排序闸）、schema 两处（`checked`、`stratum_support`）、
`dispatch.py`（`_attach_propensity_overlap_warning` → `_attach_overlap_assessment`，
兼记录计数）、`support.py` / `backdoor.py` / `aipw.py` / `tmle.py`（删分叉）、
`assumption_glossary.py`（删那一行）、`analysis_report.py`（判决行 + 计数行）、
`reader_words.py` / `test_vocabulary_reach.py` 各两行、前端
（`types.ts` / `verdict.ts` / `Verdict.tsx` / `styles.css` / 重生成词表）、
`response_rendering.md`。测试：新模块
`test_a_premise_this_run_tested_says_so_on_that_line.py`（23 条），
`test_a_stratum_the_formula_needs_has_both_arms.py` 的三条断言从「id 变了没有」
改成「那一行的判决是什么」（并补了「没有格子可数时不带判决」这一侧），
`test_the_answer_has_no_silent_parts.py` 补 `stratum_support` 一行。

**两道既有闸口当场抓到了这次改动的欠账**，两条都是它们该说的话：#501 的
types.ts 对账闸报「匿名形状从 28 涨到 30」——新加的两处内联形状没有名字，就在每条
规则之外；给它们名字（`LedgerCheck` / `StratumSupport`）并各补一行 MIRRORS 之后
回到 28。改名的那个函数还有一处旧调用点在测试里，由收集期的 ImportError 抓到。

**基线**：11075 / 219 → **11126 / 221**。多出来的两条 skip 不是被关掉的测试：`test_a_member_that_is_not_an_envelope_name_keeps_its_identity` 按词表逐个参数化，凡是 `EnvelopeName` 的整门跳过（那一门由 #382 接手），新的 `Verdict` 与 `Check` 正是两个 `EnvelopeName`。

**方法论沉淀**：(349)**一个字段缺席的证据，是判决在别处被偷运的形态数**——重叠改的是假设的名
字、过度识别写的是缺口，两条路互不相干却是同一个空缺；**看见「同一件事有两种说法」就去问是不
是少了一个位置**。(350)**判决类字段必须可从信封里的证据重算，否则它是不可反驳的断言**——这一
条反过来定了范围：只有把结果留在信封里的检验才有资格出现在台账上，其余的先把证据送进信封。
(351)**「一次通过值多少」是检验的属性，不是调用点的**——把它放在调用点，下一个作者就会给一次
没拒绝的假设检验写上 held。(352)**只在失败时留下的记录，读不出成功那一面**——缺口天然是单向
的，所以「数清了且全合格」和「根本没数」在信封上曾经是同一句话。(353)**一个成员如果没有生产
者能写出来，它在源码里就和「还没人需要」长得一样**——`Verdict.HELD` 只有在「清点」成为一个检
验之后才活得下来，所以那道进程内检查（原本管 Layer / Provenance / Severity）这次一并管上了它；
**新词表的第三个成员要么当场给出能写它的生产者，要么先别写。**

### #502 说清两个成员之间放什么，就是说清一个成员是什么——而只有前半句是可核的（2026-09-01）

**现象**：#498 让每个词表声明 `between=`（成员之间放什么：`、` / `；` / 句号后的那个空
隙）。把 55 个词表逐条按「这个成员自己收不收尾」量一遍：

```text
gap_describes         seam=SENTENCES   88 个成员，14 个不收尾
gap_says              seam=STATEMENTS  37 个成员，16 个收尾
refusal_sentence      seam=STATEMENTS 137 个成员， 6 个收尾
orientation_asks      seam=SENTENCES   17 个成员， 2 个不收尾
instrument_route_note seam=SENTENCES    3 个成员， 1 个不收尾
discovery_note        seam=STATEMENTS  25 个成员， 1 个收尾（那一个是问句）
```

**六个词表各自装着两种东西**，所以它们声明的那个缝对其中一部分成员必然是错的：声明
SENTENCES，不收尾的成员和下一句之间就没有边界（中文的句间空隙是空串）；声明 STATEMENTS，
收尾的成员接出来就是「。；」。这一类错**不产生任何症状**——渲染不报错、类型不变、测试不红，
只有真的把两个成员接起来时读者才看得见。

**根因假设**：**说「两个成员之间放什么」就是在说「一个成员是什么」，而只有前半句被写了下
来。** 后半句从来没有被问过，于是每个作者按手感写。更具体的一处空白：**一个模板以洞结尾时
（`识别路径失败：{why}`），句号该由谁写没有规定**。8 条 gap_describes 把收尾交给洞，而洞里
装的是 gap_says 的成员——它有自己的缝，对这句话不欠任何东西。两边都以为对方会写。

**为什么这是根因不是表象**：表象修法是把 39 处标点改齐。但 #498 当初**恰恰是因为**「加这道
闸会在四个既有词表上失败」才没有加它，并把这件事登记下来；只改标点而不定规则，下一个成员照
样按手感写。要定的规则是**「以洞结尾的模板不是整句，句号写在洞后面」**——有了它，缝和句末
标点变成同一件事的两面，闸口才可能是机械的。

**做法**：闸口放在**声明的同一处**（`language._answers_to`）。缝是三种之一这件事本来就在那
里被验；现在成员是不是缝说的那一种，也在那里被验。**先验成员再认领名字**，所以被拒的词表不
会占掉那个名字（这一条自己也配了测试）。判据 `language.ends_a_sentence` 与
`SENTENCE_MARKS` 一起放进语言层——句号和问号在下游是同一件事，而只有句号是**生产者会写**
的那个记号，所以它和既有的 `FULL_STOP` 是两张表不是一张。

**改动（39 处标点 + 1 处搬家）**：`gaps.py` 30 处（16 去 / 14 补）、`refusals.py` 6 处、
`scheduler_words.py` 1 处（`：{refusal}` 之后补句号）、`orientation_questions.py` 2 处
（问号之后挂着一个括号注释，改写成第二句话；括号里外都不摆句号，是因为那样一来中英各有一套
排版规矩，而两句话在两种语言里都成立）。
- **`discovery_note` 那一条是真的装了两种东西**：`which_way_between_these_two` 是一个**问
  句**，而这张表自己的段落白纸黑字写着「NOTES 的成员不收尾，它进的是一句更大的话的槽」。
  **它的同胞信道早就做对了**——不假设因果充分性的那次滞后搜索，向同一个读者问同一个问题，
  放在成员是整句的集合里。搬到新的 `discovery_asks`（成员是整句），调用点从表查改成
  `language.state`，reader_words 与 reach 表各补一行。

**新闸口，每一条都构造了它该说「不」的那个反例**：声明 SENTENCES 而某成员不收尾、声明轻缝
而某成员收尾、以洞结尾的模板声明成整句、被拒的词表没有占掉名字、`。**` 仍然算收尾。

**一处对自己量法的更正**：第一版扫描报的是**七**个词表不一致，多出来的那个是
`latent_lagged_discovery_says`——它有一条成员以 `。**` 结尾，而那一版判据 rstrip 完直接看
最后一个字符。**它量的是 markdown，不是标点。** 判据改成能看穿收尾之后闭合的记号（强调、
引号、括号）之后，它自己就合上了；这条判据现在带着自己的反例住在语言层里。

**基线**：11006 / 218 → **11075 / 219**。多出来的那一条 skip 不是被关掉的测试：
`test_a_vocabulary_prints_as_the_word_it_is` 按词表逐个参数化，而 `Word` 那一门本来就整门跳过
（它按设计交出身份，由另一条规则接手），新词表 `discovery_asks` 走的正是这一门。

**方法论沉淀**：(346)**一条声明如果只有一半可核，另一半就会在暗处长出两种东西**——`between=`
的可核部分（是不是三种之一）从第一天就被验着，不可核的那部分（成员到底是不是整句）在六个词
表里各自跑偏；**判断一条声明够不够，问它「写错了会怎样被发现」**。(347)**登记里那句「加这道
闸会在四个既有词表上失败，而那不是它们的接缝错了」是有价值的欠条，但它把因果记反了**——真
相是那四个词表的成员本来就该改，闸口不是迁就它们而是揭发它们；**「闸口会失败所以先不加」下
一次要连带写清「失败的是闸口还是被测者」**。(348)**扫描类判据要先在自己身上找反例**：一条
「以什么结尾」的规则遇到 markdown 就量错了对象，而它报出来的七个里有一个是自己造的；**先看
最不像的那一条，再决定要不要动 39 处**。

### #501 一份手抄的形状，抄得下有哪些字段，抄不下哪些字段一定在（2026-09-01）

**现象**：浏览器的 `types.ts` 是 `query_result.schema.json` 的手抄本。旁边那个模块管的是
「顶层有哪些字段」，那是一个类型所声称的一半；另一半是**这些字段里哪些是保证给的**，而从来
没有人问过。把整份接口逐条对着 schema 量一遍：

```text
types.ts 40 个接口 / query_result.schema.json 39 个 $defs
按 camelCase 名字能配上的：7 个，其中 1 个是假配对
schema 保证、这边写成可选：115 个字段
这边写成必填、schema 里根本没有这个字段：1 个（LlmProposedReview.summary）
#497 手工修过的 8 个里，编译器抓到的：2 个
```

抄漏一个 `required` **不留痕迹**：字段还在，类型还对，只是变成可选——于是编译器要求浏览器
去处理一个信封永远不会出现的情形，有人就为这个不存在的情形给读者写了一行字。反方向更糟：
这边必填、那边不保证，等于 **`undefined` 穿着值的类型**，而编译器站在它那一边。`summary`
正是这一种：生产者早就不写了（它数的是旁边两张表自己就能数的东西），schema 里没有它，`src`
里没有人读它，而这份类型一直向每个使用者保证它是一个 `string`。

**根因假设**：一个接口和一个 schema 形状之间**没有身份**。顶层字段有身份——字段名就是
schema 顶层 property 名，所以那三张表能对账；嵌套形状的身份只能靠名字碰运气。没有身份就
没有对账，没有对账，`required` 就只能靠人抄对，而人抄漏了不会有任何东西响。

**为什么这是根因不是表象**：表象修法有两个，都不行。一个是给那 7 个名字能配上的接口加
required 检查——**覆盖 7/40，还带一个假报**（`CausationQuantity` 同时镜像 theta 路的
`causationQuantity` 和数据路的 `causationEstimate`，两者保证的东西不一样），那是「长得像
覆盖的覆盖」。另一个是把 40 个接口手工再核一遍——下一个接口来的时候又没人管了，这正是
#497 修完 8 个字段之后的状态。

**做法**：每个接口**说出它抄的是哪个形状**，写成 JSON Pointer（schema 给自己内部位置起名
的那套写法，跨文件时前面加文件名），和 `CARRIED_BY` / `NOT_FOR_A_READER` /
`NOT_YET_SAID_HERE` 同一种结构、同一个理由：没有可推导的源，而**手写一张能被检验的表**好过
一条推导不出来的规则。一个接口**可以指多个形状**，因为可以有多个生产者填它；代价是精确的
——**一个字段只有在被指到的每一个形状都要求时才是保证的**，所以多指一个形状只能让承诺变弱，
永远不能凭空造出一个承诺。

**改动**：
- `types.ts`：新增 `MIRRORS`（36 个接口指向的形状）与 `NOT_THE_ENVELOPE`（4 个浏览器自己
  的 HTTP 形状，内核里没有对应物）；115 处 `?` 去掉、按 schema 的类型补 `| null`；删掉
  `summary`。
- `Band` 是**被组合进十几个槽的碎片而不是其中之一**，所以它列的是每一个落点。三个数变必填之
  后，`dose_response_curve` 不再 `& Band`——曲线上的一点**没有 `point`**（它带的数叫
  `effect`），`& Band` 一直在承诺一个任何信封都没有过的字段。
- `tests/web_source.py`：`interface_fields` 一次遍历回答两个问题（字段可不可选、它的类型
  文本），并跟着 `extends` 走；`top_level_keys` 退回只读对象字面量——**一行一个键**是字面量
  的写法而不是接口的写法，四十个接口里有七个把一行写满。

**新闸口，每一条都构造了它该说「不」的那个反例**：抄漏一个 required（`sample_size`）、
承诺一个 schema 不保证的字段（`form`）、声明一个没有任何形状放得下的字段（新加的 `eta`）、
被写进 `NOT_THE_ENVELOPE` 的形状**不许被任何镜像接口引用**（否则那张表就成了下一个嵌套形状
的藏身处）。另外两条是关于表本身的：每个接口必须恰好出现在两张表之一，每个指针必须落在一个
**真有字段的**形状上（落在描述或枚举上会让它底下所有承诺平凡为真，正是本模块要防的那件事
高一层的形态）。

**够不到的那一圈被数出来并钉住**：写在类型里的匿名对象没有名字，就说不出自己镜像谁。
**28 个槽**指向这样的形状，计数只许降不许升——降的办法是给那个形状起个名字。

**一处对自己说法的更正**：`build_llm_proposed_review` 的 docstring 里还整段写着它返回的那句
summary 长什么样。**函数早就不返回它了**，而浏览器那半之所以一直保证有这个键，多半就是照着
这段话抄的。

**基线**：10960 / 218 → **11006 / 218**。

**方法论沉淀**：(343)**「有这个字段」和「这个字段一定在」是两条独立的对账，第二条从来不会
自己失败**——抄漏 required 不产生任何症状：类型还在、编译还过、渲染还对，只是多写了一段永远
跑不到的读者文字；所以这一类账**必须有闸口，不可能靠用起来发现**。(344)**按名字配对的对账
是「长得像覆盖的覆盖」**——7/40 且带假报，而它的报告方式和真覆盖一模一样；**先量分母再决定
要不要这条规则**，量法是把两边的成员都列出来数配上的有几个。(345)**多指一个来源只能让承诺
变弱，是判断「多对一」表设计对不对的判据**——把必填取交集而不是并集，于是「再补一个生产者」
这个动作永远不会凭空造出一条保证；如果一张表的第二行能让结论变强，那张表的语义就还没定对。

### #500 一列时间在观察停止的地方停住，而每一个估计量都把它当成测量值平均了（2026-09-01）

**现象**：造一份真值已知的数据——生存时间服从指数分布、处理把均值翻一倍、独立的指数删失
带走 41.5% 的人，喂给 `themis.estimate`：

```text
真 ATE（生存时间上）      = +1.000
记录列上的臂间差          = +0.333
status: numerically_solved   method: backdoor_linear   point: 0.343
信封里出现 'censor' / '删失' / 'survival' / 'Cox'：全 False
gap kinds: ambiguous_variable_definition ×2, ill_defined_intervention_versions
```

**差三倍，戴着「已估计」的牌子。** 而且没有任何地方看起来不对：数稳、区间窄、列出来的
假设条条为真。**错的方向还不可签**——记录列在一个臂上的均值是 `1/(λ+μ)`，所以臂间差是偏
大还是偏小取决于**删失率**，一个谁也没记录、页面上也看不见的量：开这一刀的那份设计上它
偏小三分之二，本刀测试用的那份设计上它偏大三分之一。「至少方向是对的」这句安慰不成立。

**根因假设**：内核**说不出「这一列在观察停止的地方停住」**。变量声明能说域、能说尺度、能
说测量方式，而这几件事说的都是「一个定义清楚的量是怎么被操作化的」；删失说的是**记录下来
的那一列压根不是那个量**——它是 `min(事件时间, 随访终点)`。数据本身分不开这两者：以事件
结束的时间和以观察者移开视线结束的时间，在列里是同一个数。于是没有声明就没有信息，没有
信息就只剩下把它当普通的数平均。

**为什么这是根因不是表象**：表象修法是加一个 Cox 估计器或者报一个「可能有删失」的 gap。
两条都不对。gap 是猜的——凭什么说这一列是随访时间？没有任何数据特征能说。而 Cox 是**另一
个问题的答案**：风险比要比例风险假定（一个关于整条曲线的、数据被默默要求扛住的假设），
量纲也不是时间。缺的是一句**正向声明**，加上一条从这句声明出发的、不需要比例风险的路。

**做法（Kaplan-Meier 1958 + Irwin 1949 / Royston & Parmar 2013）**：删失变量的**无限制均值
不是这份数据里的量**——超出随访终点的那一段没人看到过，等更久是唯一能缩短它的办法。数据
里有的是 `E[min(T,τ)]`，**限制平均生存时间**。于是视界 τ 不是一个可调设置，是**这个问题的
另一半**；不给就诚实拒答。这样一来估计量的**形状还是内核已有的「均值差」**
（`E[min(T,τ)|do(x=1)] − E[min(T,τ)|do(x=0)]`），不需要新的 query kind、不需要新的读法，
变的只是这个均值怎么取：逐（层×臂）非参数 KM 曲线，积到 τ，按层权做 g-formula 标准化，
两臂相减；方差用 Greenwood 经积分传播（Klein & Moeschberger §4.5）。**格内不拟合任何函数
形式**，所以整条路上唯一的形式假定就是调用方选层时已经做过的那一个——因而不挂
mechanism_audit，而它的缺席本身是结论不是遗漏。**没做 Cox，理由写进模块头**：不是工作量，
是它答的是另一个问题。

**改动（五层）**：
- **声明**：`variableDeclaration.censoring{event_indicator, horizon}`，正向声明，未声明者
  完全静默（照 `scale` 的先例）。`horizon` 在 schema 里**可选、在估计器里必需**，这个不
  对称是故意的：schema 报「缺必填字段」教不会任何人，而那句拒答说得出「删失变量的均值不
  是数据里的量」。
- **路由**：`Route("survival", precedence=95)`，排在**每一条会把结局列平均掉的行前面**——
  包括两条结局测量误差行。次序本身就是声明的内容：那两行说记录值等于真值加噪声、并去校正
  噪声；这一行说记录下来的**压根不是那个量**，对它做校正是在校正一个没人问过的量。
- **两条出口都停住，不往下传**：同时声明了结局测量误差 → 出不去（两个前提只认一个，等于在
  作者已经收回的前提下出数，正是 #485 那次的形状）；图里没有后门集 → 出不去（往下传就会有
  别的路线去平均那一列）。各配一条种族和双语句子。
- **验证器** `themis/verifier/survival_rules.py`：从记录的风险集表**独立重导**曲线 / 面积 /
  方差 / 标准化，不导入生产者。
- **渲染**：报告与浏览器双语各一份，第一句说的是**这个数是什么**。

**新闸口，每一条都构造了它该说「不」的那个反例**：六条拒答各一例（无 τ / 事件列不是指示 /
随访时间为负 / τ 越过某格终点 / 层内缺一臂 / τ 不是数）、两条停住各一例、验证器七例。数值
端不对着上一次运行、对着**闭式**：指数分布的限制均值是 `(1−e^{−λτ})/λ`；无删失时 KM 曲线
就是经验分布，故面积**精确**等于 `min(T,τ)` 的样本均值（实测 1.6e-14），一条答别的问题的
路不会有这个恒等式；再加 60 次重复量覆盖率。

**套件替这一刀改掉的三处**——都是既有闸口问出来的，都不是「让测试过去」而是改错本身：
- `a_censored_mean_needs_a_horizon` 原先记 `Kind.DATA`。`test_no_data_refusal_measures_something_the_caller_declared` 的判据是「DATA 是一个关于第二份数据集的承诺」——而这一条缺的是**调用方已经知道的一个数**，把读者派去收数据是错的指令。改 `Kind.REQUEST`。（另一半：`a_follow_up_time_is_negative` 的种族句原先以声明开头，改成以**测到的东西**开头——负值确实是这份样本的性质，换一份就没有，DATA 是对的，错的是句子的语序。）
- 四条新句子里写了「怎么办」（给一个 horizon / 撤掉其中一个声明 / 把 τ 收回来）。`test_a_refusal_does_not_tell_the_reader_what_to_do` 说得对：**出路属于 `Remedy`、属于那一次的场合**，因为同一个种族从 Python 直接调用时缺的是关键字参数、从程序进来时缺的是声明里的一行。句子只说错在哪，出路挂在 raise 点上。
- 变量声明的两处描述里都写着「这里没有任何东西会左右推理」，而我刚加了一个会的。**族的自述变成了假话**，这比字段本身更值得改：现在两处都说出那条界线——框架字段说的是「一个定义清楚的量怎么被操作化」，`censoring` 说的是「记录下来的压根不是那个量」，后者不能是建议。

**一处对自己说法的更正**：验证器原先写着「一张把删失单位抹掉的伪造表能骗过上面每一条算术
检查，只有风险集自洽这条挡得住」。构造反例时发现**这句是错的**——把表整个重建成「谁都没提
前离开」得到的是一张**自洽**的表，风险集那条不响；挡住它的是格里另记的那个计数（有多少人
没等到事件）。真正被风险集自洽挡住的是另一种东西：`at_risk` 那一列和它自己的 events /
censored 对不上，也就是生产者数错风险集的那两种写法。两条检查都留着，说法改成各自真正挡的
东西，并把这条审计的**限度**写成一条测试：块就是全部证据，一个连派生标量一起改写的生产者
留下的块，块里没有任何东西能反驳。

**基线**：10844 / 218 → **10960 / 218**。

**方法论沉淀**：(340)**「有渲染器」和「渲染器跑得到」是两件事，注册表只保证前一件**——
`blocks.bind` 会拒绝一个没人渲染的块，所以新块加进 ANSWER 家族时全套测试是绿的；而那一节
是 first-match `return`，因为它的成员是**互斥的答案路径**（theta 路的格、装不进
`numeric_estimate` 的置信域），于是一个**伴随**数字而不是替代数字的块，渲染器一次都没跑
过。发现它靠的是把报告真打出来看一眼。放对家族之后（ROUTE 的成员是全渲染的）才有输出。
**判据：这个块是在回答「答案是什么」，还是在限定「这是哪个答案」——后者永远和数字并存。**
(341)**反例的作用不止是「看闸口会不会响」，它会证伪你对闸口为什么该响的解释**——先把「这
条闸挡的是什么」写下来，再动手构造；对不上的时候要改的是解释，不是把测试凑成能过。这一刀
里那句写在模块头上的解释就是这么被自己的反例推翻的。(342)**「一条声明对应一列」这个一一
对应，是在声明只能谈变量自己的时候才成立的**——数据契约把帧收窄到「声明命名的列」，而事件
指示列不是图里的节点、永远也不会是；收窄那一步会静默地把它扔掉，症状是「程序明明写了这一
列」却在契约层报缺列。凡是新字段指向了**别的列**，收窄那一步就得跟着改。

### #499 读者选了语言，而唯一两条不由浏览器渲染的回答从来没被告知（2026-09-01）

**现象**：`themis/web/app.py` 的四个 LLM 端点**一个都不传 `lang`**。`/api/ask`、`/api/render` 调
`render_reply`，`/api/assume` 调 `propose_theta_priors`，三处都跑在 `language.DEFAULT` 上——**同一个
浏览器，同一个读者**：他选了 en，页面上每一句都变成英文，唯独模型写的那段回复和那些先验的理由是中文。
#495 在关语言债时量到了这一条并当场声明「本刀不动它」，登记为待办；这一刀是那条待办。

**根因假设**：本仓的语言规则是**信封不携带语言，渲染时才定**——所以每一条通路都天然是语言中立的：
内核发 `words`，浏览器拿着读者的选择去填。四个端点里有三十来处返回值走的都是这条路，连失败也走
（`failure.payload` 发的是 `{stage, words, slots}`，两种语言一起过去，浏览器挑）。

**这两条通路是唯一的例外，而例外没有被标出来**：它们的产物不是一份可渲染的结构，是**一段由模型写好的
散文**——而一句话的语言在它被写出来的那一刻就定了，之后没有任何时刻可以让浏览器再挑一次。于是「渲染时
才定」这条规则在这里本就不适用，可是**没有任何东西说得出「这条通路不一样」**：请求体里没有这个字段，
前端也没有发，而这件事在类型上看不出来——`render_reply` 返回 `str`，和别处返回 `dict` 一样普通。

**为什么这是根因不是表象**：表象修法是给三个 pydantic 模型加字段、三处透传、前端三处带上。那当然要做，
但只做这些的话，**下一条产出散文的通路还会同样地漏掉**，而且同样地没有人会发现——这一条在 HEAD 上活了
很久，正是因为没有任何检查在问它。#495 已经把答案的一半写在内核侧了：`Wrote.PROMPTED` 那一档的成立
前提是「向模型要读者文字的函数必须收 `lang`」，并且有闸口钉住这两个签名。缺的是**同一条规则的另一半：
收了这个参数的门，有没有人带着读者的语言走进去**。

**改动**：
- 三个请求模型各加 `lang: language.Lang = language.DEFAULT`。**类型是枚举而不是字符串**——这个 build
  答不了的语言在边界上就被拒（422），和一个不是对象的 `program` 得到同样的待遇，而不是悄悄落回站点
  自己那门语言。默认值放在**这扇门**上，因为「调用方没说是哪门语言」这件事只在这里发生；再往下每一扇
  门都是收参数的。
- 三处调用点透传；浏览器 `api.ts` 的 `ask`/`render`/`assume` 各加一个**必填**参数 `lang`——**可选参数
  是一个调用方可以忘记的默认值，而忘记它正是本条缺陷**。两个调用点本来就有 `lang` 在作用域里（其中
  一个已经在用它渲染错误文案）。
- 浏览器那半边由**编译器**守：必填参数，三个调用点漏一个就编不过——#497 刚把 `tsc` 接进套件，所以这道
  闸不用另写。

**新闸口一条，构造了它该说「不」的那个反例**：
`test_a_caller_of_one_of_those_doors_says_who_is_reading` 从 `llm_bridge` 的**签名**里读出「哪些门收
读者的语言」，再扫 `themis/` 下每一个 Python 调用点，凡是调了这些门却没给 `lang=` 的逐个点名。**对着
签名而不是对着一张端点清单**——清单是要人记得去扩的东西，而漏掉的那个端点从来不会在清单上。验过：把
`/api/render` 那处的 `lang=` 拿掉，闸口报 `['themis\web\app.py:428 render_reply']`。它和上面那条
（门必须收 `lang`）是同一条规则的两半：一半管门开着，一半管有人带着东西走进去。

**端到端**：`/api/render` 分别以 `zh` 和 `en` 请求，录下端点交给桥接的到底是什么——**两门语言都测，
只测一门的话，一个仍旧写死作者语言的站点会通过其中一门**。另加两条：不说语言时仍拿到默认值（默认值就是
为这个存在的），以及 `lang: "fr"` 在门口被拒。

**基线**：10839 / 218 → **10844 / 218**。

**方法论沉淀**：(337)**当一个系统的每条通路都天然满足某条性质，唯一不满足的那条会没有名字**——本仓所有
回答都是语言中立的结构，于是「这条通路产出的是散文、因而必须知道读者是谁」这件事既没有类型说得出，也
没有人想起要检查。找法是反过来问：**这条普遍性质是靠什么保证的，有没有哪里绕过了那个保证**。
(338)**一条「必须收某个参数」的规则，只写了门就只关了一半**——门开着而没有人带东西进来，读者拿到的
东西和门根本没开是一样的；两半要一起写，且都对着签名而不是对着调用方清单。(339)**一个可选参数是一个
调用方可以忘记的默认值**：这里的缺陷本身就是「忘了传」，所以修法里那个参数不能是可选的——把它设成必填，
守卫就从「另写一个闸口」变成了编译器。

### #498 几条语句放进一个洞，接缝由「它是个 list」决定，而不是由它们是什么决定（2026-09-01）

**现象**：把一份已知输入喂进内核——两条一致性约束同时被违反——渲染出来是这样：

```text
P(Y=1|do(X=1))=1 has to sit inside [P(X=1,Y=1), P(X=1,Y=1)+P(X=0)] = [0.25, 0.75], P(Y=1|do(X=0))=0 has to sit inside …
P(Y=1|do(X=1))=1 必须落在 … 之内、P(Y=1|do(X=0))=0 必须落在 … 之内
```

两条完整的小句被「名字与名字之间」的那个记号接在一起。中文侧的 `、` 是明摆着的错；英文侧更糟——
**这两条小句自己内部就带着逗号**（`[0.25, 0.75]`、`[P(X=1,Y=1), P(X=1,Y=1)+P(X=0)]`），所以那个接缝
**不是偏轻，是根本找不到**：读者没有任何办法知道一条到哪里结束。

**根因假设**：`assemble` 挑接缝时唯一能看见的事实是「我拿到了一个 list」，于是一律走 `listed` →
`BETWEEN_ITEMS`。但**「用哪个接缝」是关于里面装的是什么的事实**：一串名字之间是 `、`，一串小句之间
是 `；`，一串整句之间是句号后面那个空。生产者知道装的是什么；而 `assemble` 是在读者面前跑的，那时手里
只有几个 token，**当初知道的那个人已经不在这个进程里了**。

`BETWEEN_STATEMENTS` 这张表**没有门**，这是同一件事的另一半：它左右两个邻居各有一个（`listing` 管
名字、`sentences` 管整句），中间这一个只有表——于是仓库里 8 个要用它的站点各自手写了一遍
`fill(BETWEEN_STATEMENTS, lang).join(...)`，而 `assemble` 连一个可以调用的「另一个选择」都没有。

**为什么这是根因不是表象**：上一刀把这条登记为「**先量再改**」，理由是一律改成 `；` 会把每一个装名字的
洞弄错。这次量了：**给 `assemble` 挂钩子跑完整套 10824 条测试，全仓一共只有 5 个洞会被装进列表，其中
3 个装小句、2 个装名字**。所以两个方向的默认值都是错的——缺的不是一个更好的默认值，是**一个能把这件事
说出来的地方**。

而那个地方只能是**词表**：接缝只在读者面前才需要，那一刻还在场的东西只有 token 和注册表，**信封不携带
它**。放在填洞的站点（传一个 joiner 进来）等于把标点的选择权还给站点——那正是前一刀刚关掉的缺陷；放在
模板上则无处可挂，模板是一张纯文本的 `Words`，而同一个洞装的一直是同一个词表的成员。

**改动**：
- `Word.__init_subclass__` 与 `declare()` 各加一个**必答**的 `between=`，取值只能是语言层自己那三张表
  之一。**54 个词表全部作答**：17 个 `BETWEEN_ITEMS`（成员是名字：`bound_side` 的 `lower`/`upper`、
  `measurement_note` 的 `x（切点：">=3cm"）`）、27 个 `BETWEEN_STATEMENTS`、10 个 `BETWEEN_SENTENCES`
  （成员本身就以句号收尾）。没作答的在**导入时**就报错，所以渲染时不可能缺——`assemble` 既不猜也不抛。
- 新门 `language.statements()`，以及顺手补齐的第四个 `language.clauses()`（`BETWEEN_CLAUSES` 同样只有
  表没有门）。洞用的那个是 `language.joined()`：它从条目自己的词表读接缝；一条列表混了多个词表时取
  **最粗**的那个——**一个偏重的记号仍然分得开两样东西，一个偏轻的记号让读者找不到边界**。
- 8 个手写消费者，加上另外 8 处直接拿表 join 的站点（`BETWEEN_ITEMS` 4、`BETWEEN_CLAUSES` 3、
  `BETWEEN_SENTENCES` 2），全部改走门；新闸口钉死**除 `language.py` 外没有任何模块直接在接缝表上 join**。
- **浏览器有同一个缺陷**：`verdict.ts` 自己那份 `assembled` 也是 `listing(...)`。接缝按词表生成进
  `kernelWords.generated.ts`（`SEAMS`，54 条，只写记号的名字不写记号本身），`seam`/`joined` 在浏览器侧
  重写一遍，`assembled` 改走它。它进 `NOT_VOCABULARIES` 并说明理由——**按词表键控，却一个词都不带**。

**新闸口十五条，每条都构造了它该说「不」的那个反例**：没作答的词表被拒；自造一个记号的词表被拒
（`{zh: " · "}`）；两条小句在洞里必须带 `；`，且英文侧**不得**落回逗号粘连；两个名字必须仍是 `、` 且
不得变成 `；`；混词表取粗；未知词表落回列表记号（**全套唯一的一次猜**，与 `gloss` 一层之下已经在做的
那次是同一个理由）；四个记号各有门；无人绕过门（扫描自身的 reach 也被钉住，读不到东西的规则会通过）；
浏览器那张表逐条等于内核的；浏览器的 `assembled` 里不再出现 `listing(`。

**显式声明：量到但没做的那一件**。若干词表**内部对「成员是不是一个完整句子」并不一致**：`gap_says`
37 个成员里 16 个以句号收尾、`orientation_asks` 17 里 15、`refusal_sentence` 131 里 6、`discovery_note`
25 里 1。也就是说这几档的声明对一部分成员是折中（`；` 跟在一个句号后面并不好看）。本刀没有去统一——
那是「**一个集合的成员是不是同一种东西**」的问题，不是接缝的问题，已登记为待办。也正因为这种不一致
今天就在，**没有**加「声明 SENTENCES 的词表其成员必须都以句号收尾」那道机械闸：它会在四个既有词表上
失败，而那不是它们的接缝错了。

**基线**：10824 / 218 → **10839 / 218**。

**方法论沉淀**：(334)**当一个决定只看得见容器、看不见内容，它做的就不是那个决定**——`assemble` 看见的
是「这是个 list」，要答的却是「这些是什么」。这类缺陷的形状是**默认值在一部分场合恰好是对的**，所以它
活得久：错的那几处从来没有人报错，只是读起来怪。(335)**先量分母，再动默认值**——上一刀停在这里是对的；
挂钩子跑完整套才知道 5 个洞里错 3 个，不量就只能在两个都错的默认值之间换一个。(336)**一个事实该放在
哪里，由「它在哪里被需要」倒推**：接缝在读者面前才需要，那一刻只剩 token 和注册表，所以它只能是词表的
属性——站点知道却不在场，模板在场却无处可挂。

### #497 浏览器的每一条规矩都是用正则读 TypeScript，而编译器从没被问过（2026-09-01）

**现象**：`npx tsc -b` 在 HEAD 上给出三条错误，全在 `src/lib/verdict.ts`。一条 TS6196——
`BootstrapDraws` 这个 type import 从未被用到；两条 TS2322——`boot.used` 与 `boot.requested` 的类型是
`number | undefined`，而它们被填进一句话的洞里，那里要的是 `string | number`。

**根因假设**：两条不同的根因，而它们能一起活在 HEAD 上靠的是第三条。

- **两条 TS2322**：`bootstrapDraws` 在 schema 里写着 `required: [kind, requested, used]`，而 `types.ts`
  里这三个字段全是可选。浏览器这份信封形状是**手抄的**，而已有的对账（`test_web_envelope_fields.py`）
  只对**「有哪些字段」**，不对**「哪些字段是保证给的」**。于是内核保证一定给的东西，到浏览器成了「可能
  没有」；一个真的用上这个保证的调用点就成了类型错误，而它只剩两条出路：编一个内核永远不会产生的
  默认值，或者把错留在那儿。留在那儿了。
- **一条 TS6196**：`web_source.sources_that_could_read` 的 docstring 里早写着这条规律——「import 不是
  use：一个组件停止渲染某样东西之后仍然继续 import 它」。这是同一件事在类型层的形态。
- **为什么三条都没人发现**：本仓对浏览器的每一条约束，都是**用 Python 正则去读 TypeScript**——二十一份
  词表的转写、信封字段的三方对账、两节渲染的先后。那些规则问的是源码**说了什么**，正则够用。而**唯一
  读得懂 TypeScript 的那个读者——编译器——从来没有被问过**。

**为什么这是根因不是表象**：三条里最省事的改法是在 4030 行加 `?? 0`、删掉那个 import。但 `?? 0` 是
**给一个内核永远不会产生的情形编一段读者文字**——与 #495 里那个「为了通过非空检查而存在的常量」是同一
种缺陷；而删掉 import 之后，下一条类型错误照样会静静躺在 HEAD 上，因为**没有人会发现**。

**改动**：
- `types.ts` 里四个接口按 schema 的 `required` 改回必填，共 8 个字段：`BootstrapDraws` 的
  `kind`/`requested`/`used`、`BoundsResult.tightness`、`DataGap.provenance`、`CausationQuantity` 的
  `lower`/`upper`/`point`。最后一个顺带说清了它为什么长这样：它**同时镜像两个 schema 形状**——数据路的
  `causationEstimate` 和 theta 路的 `causationQuantity`——三个字段两边都要求，而 ci 三件套只有前者有，
  因为 theta 路上没有任何东西产生抽样分布。
- 删掉 `verdict.ts` 的死 import。
- **新闸口 `tests/test_the_browser_s_source_is_read_by_a_compiler.py`**（3 条，1.7 s）：跑本项目自己的
  `tsc -b --force`。`--force` 而不是默认的增量——增量所信任的那个 buildinfo 是上一个跑编译的人写的，
  而**一个可以被告知「没什么要做」的检查，通过的理由与源码无关**。node 或 `node_modules` 不在时前两条
  跳过，第三条不跳。

**反例**：`test_a_type_error_in_the_browser_s_source_would_be_refused` 在 `src` **旁边**（不是里面）
写一个探针文件，用一份 `extends` 项目 app 配置、只换文件列表的 tsconfig 去编它。放在 `src` 外面是必需
的：**其它每一条规则都在扫 `src` 下的 TypeScript，八个 worker 并行时，一个 worker 为了被拒而写进去的
文件是另一个 worker 眼里的真实源码**。探针一个文件里带两种错（未用的 type import + 读一个可能不存在
的值），因为**抓这两种错的是两个不同的编译选项，只带一种的反例会让另一种的选项可以被关掉而没有任何
测试发现**。断言看编译器**说了什么**而不是错误号：号码是编译器版本的事实，而这两种错要跨版本一直被
抓住。第三条 `test_the_build_that_ships_runs_the_compiler_first` **不需要 node**——`dist` 是产物且不
入库，`pnpm build` 是编译器唯一保证会跑的地方，断言 `tsc` 在 `vite build` **之前**：打包器不读类型就
把它擦掉，反过来的顺序会把编译器本该拒绝的东西发出去。

**验过**：把 `BootstrapDraws` 的 `used`/`requested` 改回可选，闸口逐字复现 HEAD 上那两条 TS2322 并
失败；改回来即过。

**显式声明：本刀没做的那一件**。schema 与 `types.ts` 之间**没有** required 的对账闸。实测分母：
`types.ts` 有 40 个接口，schema 有 39 个 `$defs`，**按名字能配上的只有 7 个**，且这 7 个里还有 1 个是
假配对（`CausationQuantity` 镜像的是两个形状）。一个覆盖 7/40 且带假报的闸，读起来像「浏览器的类型与
schema 一致」而其实不是——正是本仓反复点名的那种**长得像覆盖的覆盖**。真正的做法是让每个接口**声明它
镜像哪个 schema 形状**（与 `CARRIED_BY` / `NOT_FOR_A_READER` 同一种结构），那是一条独立的前沿，已登记
为待办。编译器闸口只抓**有人真的用上了那个保证**的那部分漂移：本刀修的 8 个字段里，被它抓到的只有 2 个。

**基线**：10821 / 218 → **10824 / 218**。

**方法论沉淀**：(331)**一份手抄的镜像会丢掉「必填」这一半，而且丢得没有声音**——字段名对不上会立刻炸，
可选性对不上只在有人用上那个保证时才炸，于是它能躺很久。(332)**当一份源码的所有规矩都由另一种语言的
正则来执行时，先问它自己的编译器有没有被问过**——正则问的是「说了什么」，编译器问的是「说得通吗」，
后者是前者永远补不上的一整类。(333)**一个反例文件要放在别人扫不到的地方**——并行套件里，一个 worker
为了被拒而写下的东西，是另一个 worker 眼里的真实源码。

### #496 时间挡不住一个没被记录的共同原因，而滞后发现假装它挡得住（2026-09-01）

**现象**：造一个已知的线性 SCM——一个**未记录**的驱动 u 同时驱动 x 与 y（滞后不同），x 与 y 之间
没有任何边——喂给 `discover_lagged_graph`（PCMCI，#449），4000 步、α=0.01：它返回
`x@t-1 → y` p=0、`x@t-2 → y` p=1.3e-15。两条都是编造出来的因果，而且是**最有把握**的那两条。
第二个设计（w → x，u → x 且 u → y，于是 x 是 w 与 u 的对撞结点）6000 步：三条链接里两条错，其中
`w@t-2 → y` 这一条**只因为条件集里含了一个对撞结点才存在**——它是搜索自己造出来的相依。

**根因假设**：PCMCI 的正确性建立在**因果充分性**（每个共同原因都被记录了）之上，而这条假设在 #449
里是文档中的一句话、不是输出里的一个记号。于是这个模块**没有「未记录的共同原因」这个词**——它的边
只有一种记号（`→`，一个原因）。当数据里的相依来自一个没被记录的驱动时，它没有第二种话可说，只能把
它读成因果。**缺的不是一个更强的检验，是一个第三种答案。**

**为什么这是根因不是表象**：把 α 调紧、把样本加大，那两条边都不会消失——它们的 p 值随样本增大而
**更**小，因为那个相依是真的，错的只是「相依 ⇒ 因果」这最后一步。换一个更保守的条件选择也一样没用：
`grow-shrink` 的不动点只有在因果充分性下才是父集，放松之后它只是一个**筛子**——配偶会经由一个潜在的
孩子进来（w→x、u→x、u→y，一条件于 x，w 与 y 就相依了）。所以错的不是搜索的某一步，是**输出的字母表
只有一个字母**。

**改动**：新模块 `themis/estimation/latent_lagged_discovery.py`，SVAR-FCI / tsFCI（Malinsky &
Spirtes 2018；FCI = Spirtes/Meek/Richardson 1995，定向规则 Zhang 2008）——把 FCI 跑在时间滞后设计
上，时间序当背景知识。时间序在每条边**较晚**的那一端钉死一个箭头，于是每条边只剩一个问题：较早那端
的记号是什么。三个字母：

- `tail`（`→`）：一个原因；
- `arrow`（`↔`）：两端共享某个未记录的东西——**这是对混杂的正面识别，不是弃权**；
- `circle`（`o→`）：二者之一，这份数据说不出是哪个。

每一个非 `circle` 的记号都带着**定下它的那个三元组**（R0/R1 的对偶：W、X、Y 三点，W 与 Y 不相邻，
X 在 `sepset(W,Y)` 里 → 非对撞 → `tail`，不在 → 对撞 → `arrow`；R8 = 祖先传递，原因的原因是原因）。

**为什么必须搜子集、且空集必须在里面**：因果充分性下一个条件集就够了（父集）；放松之后，**条件在一个
对撞结点上会制造相依**，所以分离集只能在**子集**里找。空集必须是候选之一——少了它，「只有在条件于对撞
结点时才出现的相依」这一整类就永远抓不到，对撞那一支根本走不到。

**声明的两处取舍**（两条都是「少答」，不是「答错」）：

1. **LPCMCI（Gerhardus & Runge 2020）没做**。它瞄准同一个图、同样的可靠性保证，在强自相关下能恢复出
   更多。那是**功效**上的改进不是正确性上的：两者的差别不是「答案有多对」，是「答案里留了多少个
   circle」——而本仓一贯把后者排在第二位。一个 circle 说的是数据没把它定下来，而本模块要消掉的那个
   失败是**一个被编造出来的箭头**。
2. **Zhang 的 R2–R4、R9–R10 没做**（R2 在这里本来就是空的：它的结论是较晚一端的箭头，时间序已经写好
   了）。输出因此是**可靠的**——写下的每个记号都对——但**不是最大信息的**：某些 circle 在完整规则集下
   本会是 tail 或箭头。**明说而不是吸收掉**，因为「我们分不出」和「我们没去找」在读者那里读起来一样，
   而它们不是同一个断言。

**接线与验证**：schema `latent_lagged_discovery.schema.json`（`orientation` 用 `if/then/else` 按
`rule` 要求见证：除 `ancestry` 外都必须带 `separating_set`）；`verify_latent_lagged_discovery`
**第二次独立转写**偏相关 / Fisher-Z / 布局 / 条件池 / 子集搜索 / 定向规则（不 import 生产侧），核对
四件事：筛选集是不是它自称的那个不动点、每一对的判决是不是搜索给出的那个、边集是不是恰好等于「相邻」
判决的集合、每个记号能不能从**记录下来的**相邻关系与分离集重新推出来。四个反例逐个被拒：伪造的 tail、
被篡改的分离集、被删掉的边、被打破的筛选集。伪造 tail 的拒绝话术：`edge w@t-1 -> x@t is marked
'tail' and the orientation rules applied to the recorded adjacency and separating sets give
'circle'`。见证元组里直接存 sepset，**验证器因此一个列名都不用解析**。`Artifact` 9 个成员 / 8 个
独立件；MCP 工具 19 → **21**；`circle` 出内核 AST 时落进 `extensions.ambiguities`
（`latent_or_causal`），**不假装成一条边**。

**证据（同样两个设计、同一份数据）**：

- 潜驱动设计：新模块给 `x@t-1 o→ y@t`、`x@t-2 o→ y@t`（诚实的 circle）；`z@t-1 → z@t`、
  `z@t-1 → w@t`（正确的 tail，由三元组 `z@t-2, z@t-1, w@t` 的非对撞规则定下）；并把 PCMCI 塞进 x
  父集里的 `z@t-2` 用子集搜索删掉（条件于 `{z@t-3}` 即分离，p=0.25）。
- 对撞设计：`w@t-1 o→ x@t`、`x@t-1 ↔ y@t`——**混杂被正面认出来了**；PCMCI 那条 `w@t-2 → y@t`
  不复存在。

**基线**：10754 / 217 → **10821 / 218**。

**方法论沉淀**：(328)**筛选集不是答案**——grow-shrink 的不动点只在因果充分性下才等于父集，放松之后
它是个筛子；把筛子当结论，多进来的那些配偶就会变成边。(329)**空集必须在候选分离集里**——一个从 size 1
起步的枚举永远走不到对撞那一支，于是「条件于对撞结点才产生的相依」这一整类错误对它永远不可见；这类
「少试了一个退化情形」的缺陷不会报错，只会安静地少一种结论。(330)**当一个模块在某类输入上必然说错话，
先问它的输出字母表是不是少了一个字母**——不是所有的错都是搜索错了，有的是**没有别的话可说**。

### #495 说给谁听，在一个模块里有三个答案，而它从没把它们分开（2026-09-01）

**现象**：语言债还剩最后 8 条：`themis/web/llm_bridge.py` 7 条、`themis/language.py` 1 条。

**根因假设（`llm_bridge.py`）**：这个模块是内核与语言模型之间的胶水，而**「这段文字说给谁听」
在这里有三个不同的答案，模块从来没把它们分开**——于是每一段都由写它的人按自己当时在想的语言写。
三种读者恰好各对应本仓已经给过答案的一扇门：

- **给调用方/等在浏览器前的人的**（3 条，`LLMBridgeError` 的消息）：这个类是裸 `RuntimeError`，
  没有物种的概念，于是「哪一种没拿到」和「这一次的事实」被压成一个英文字符串，由站点写。它经
  `failure.payload` 到浏览器时只落进 `diagnostic`——**和 #493 修好 `SemanticError` 之前一模一样的
  形状**，而 #493 已经把那条分支从「点名某个类」改成 `isinstance(exc, language.Voiced)`，门早就
  开好了。
- **给模型的**（2 条，两处 prompt 正文框）：`render_reply` 用英文并用 `language.endonym(lang)` 点名
  目标语言，二十行外的 `propose_theta_priors` 用中文。**分歧的根因不是谁忘了统一，是只有前者被告知过
  「回来的东西谁读」**：后者根本没有 `lang` 参数，于是它没有别的语言可写，只能写作者自己的。
- **给读答案的人、却由内核代笔的**（1 条，`"LLM 常识先验"`）：模型没给 reason 时的兜底默认值。

**为什么这是根因不是表象**：因为那条兜底值把话说穿了。`annotations.source` 在 `llm_prior` 上被
校验器要求**非空**，校验器自己的注释写着为什么——「空的 source 会让 LLM 把编造的数悄悄洗白、不留
披露」。而这个常量**满足了这条检查却什么也没披露**：它是被它所防范的那一层用一个常量绕过去的检查。
所以它不是「一条待翻译的中文」，是一条不该存在的句子——**它也是全模块唯一一条没有任何人能替它选
语言的读者文字**，因为其余每条 reason 都是模型的，只有这一条是我们的。三个读者、三扇门，谁都没被
打开，是同一个缺失的后果。

**根因假设（`language.py` 的那一条）**：`capped()` 的截断标记
「… (truncated at 1000 characters — a value was interpolated raw; see themis.language.describe)」
**一句话同时说了两件事给两个人听**：文字到此为止（读者的），以及有个值被原样插进来了、去看
`describe`（维护者的诊断）。而 `capped` 只拿到一个 `str`、拿不到 `lang`，**它是全包里唯一不能说出
这两句中任何一句的位置**——三个调用方里有两个是在把一个值送进洞之前上界，第三个上界的是**已经拼好
的整句**，那里根本没有什么「被插进来的值」，长的是模板自己。CORE_STATUS 早就记过这个后果：截断处
那句英文提示出现在中文段落中间。

**改动**：
- `LLMBridgeError` 变成 `language.Voiced` 子类，新建 `themis/web/bridge_words.py`（`bridge_refusal`，
  11 个物种）。一个信道十一个物种不是凑合：调用方要做的事只有一件（这一步没拿到能用的东西），是
  **哪一种**由 `species` 读出来。
- `propose_theta_priors` 收 `lang`，正文框改英文（与它所延续的文档一致），并在请求里用 endonym 说
  一次目标语言——**reason 是读者要看的东西**，所以它跟回复走同一条规则。`propose_theta_priors.md`
  的中文标题与中文示例 reason 一并改英文：文档只有一种语言，读者的语言在请求里说。
- 兜底值改成**拒绝**（`A_PRIOR_CAME_WITH_NO_REASON`）。删掉一句只为让非空检查通过的常量。
- `capped` 的标记改成一个 `…`。读者那一半是排版不是散文——`describe` 省略长集合用的就是这个字符；
  维护者那一半是**一个站点做不出的诊断**，三个调用方里有两个它是错的，**一条在无法核实处被当作事实
  说出的诊断是删掉而不是翻译**。而且它最常见的去处是别人句子的洞里：**往一个洞里塞一句话，正是
  #491 拿掉的那个缺陷**。
- 债表新增 `Wrote.PROMPTED` 一档：**写给模型的文字，其语言由它所延续的那份文档定**——与 `SOURCE`
  同一个理由，只是消费方从编译器换成模型。它与其它各档的区别写在自己的 docstring 里：**这段文字
  写给一个会用它没说出的语言回答的人**，所以读者的语言是请求的参数而不是文本的属性；一个模块若
  向模型要读者文字却不收这个参数，就不在这条豁免之内。

**新闸口三道，各自构造了它该说「不」的那个反例**：
1. `test_a_prompt_frame_is_in_the_language_of_the_document_it_continues`——正文框与它延续的文档
   同语言。不是「必须是英文」：哪天文档改成中文，框子跟着走。
2. `test_a_prompt_that_sources_reader_text_takes_the_reader_s_language`——两个函数签名里都必须有
   `lang`。**这条是豁免成立的前提**：没有这个参数，`PROMPTED` 的理由就不成立。
3. `test_a_frame_in_the_language_its_document_is_not_would_be_refused`——反例，以及一次**闸口自己
   先错了的记录**：第一版直接在文档里搜 CJK，被 `response_rendering.md` 判为中文文档——2258 行英文，
   全部证据是引用另一份文档一个章节标题里的两个汉字。**一个文件不因为出现了一种语言的一个字符就是
   用那种语言写的**；引号与代码块里的东西是引文，`Wrote.QUOTED` 早就为字面量画过这条线，这里把它
   画给段落。

**证据**：语言债 8 → **0**，两行都是**删行**。`STILL_ONE_LANGUAGE` 现在是空的，规则的分母成了整个
包（`test_a_module_not_on_the_debt_writes_every_language` 一条兜住）。`llm_bridge.py` 进
`NO_SITE_WRITES_ITS_OWN`——那是比债表更强的第二条规则：raise 站点连字符串都不许拿。
`test_the_debt_is_exactly_what_it_says` 从逐模块参数化改成循环：空表参数化会产生一个 skip，而**一条
做完了的检查不该长得像一条没做完的**。

**显式声明：本刀没做的那一件**。`themis/web/app.py` 的四个端点**一个都不传 `lang`**——浏览器把读者
的选择留在本地、自己渲染内核的 words，所以没有任何请求体带它，两条 LLM 通路因此始终跑在
`language.DEFAULT` 上，不管问的人是谁。这是**端点接线的缺口**，不是本模块的语言债；已登记为待办，
本条不动它（要动就得改三个 pydantic 模型 + 前端发送，而前端在 #489 上还有三条既有 tsc 报错）。

**基线**：10702 / 216 → **10754 / 217**。多出来的那一条 skip 是机械的：每新增一个词表，
`test_a_member_that_is_not_an_envelope_name_keeps_its_identity` 就多一条「按设计放弃 identity」的
跳过。HEAD 的 10702/216 是在独立 worktree 上实测复核过的，不是照抄上一条。

**方法论沉淀**：(324)**一组措辞不一致，先问「它们各自说给谁听」——如果答案不止一个，不一致是结果
不是原因**。统一措辞会把三种读者压成一种。(325)**两个同族站点分歧时，看的不是谁写错了，是谁被告知
得更少**：`propose_theta_priors` 写中文不是疏忽，是它从未拿到过读者是谁这个事实，除了作者自己的
语言它没有别的可写。(326)**一个满足了检查却什么也没提供的默认值，是那条检查被绕过而不是被满足**；
它通常长得像「补一个占位」，而它防的恰恰是占位。(327)**一个文件不因为出现了某种语言的一个字符就是
用那种语言写的**——判断一段文字的语言时，引文和代码块要先摘掉，否则闸口会被一次引用击落。

### #494 四条互不相干的备注，其实是一个三值的事实（2026-09-01）

**现象**：`types.ts` 剩 4 条语言债，全是 `NOT_FOR_A_READER` 这张表的**值**——四段中文，
说明这四个信封字段为什么本面不渲染。

**根因假设**：**这四段不是四件事，是同一个事实的四次取值，而那个事实是「这个字段说给谁听」。**
`query_id` 说给调用方；`confidence` / `confidence_sources` 说给审计方；
`estimator_dependency_missing` 说给运维。**这张表自己的注释里早就写着这个集合**——「they address
the caller or an auditor, not the person reading the answer」——只是类型里装的一直是散文。

**为什么这是根因不是表象**：因为另外两条路都被本仓自己堵死过。
- **翻译它们**：#490 的结论逐字适用——把写在站点上的那句话翻译一遍，只是换了它辜负哪个读者；
  而这四段**没有任何读者**（`test_web_envelope_fields.py` 只读这张表的**键**）。给没人读的散文加一门
  语言是纯成本。
- **给它开豁免**：债表在这一行自己的注释里拒绝过——「a second allowance here would be a list, and a
  list is what the rule above stopped being」。

两条都堵死，剩下的唯一出路就是**换掉这个槽位回答的问题**：从「为什么不渲染」换成「说给谁」。
而这也是本轮（#491/#492/#493）反复出现的同一形状再走一遍：**一个值的槽位在回答一个它不能被问的
问题，于是挤进来一段散文**。

**改动**：
- `types.ts` 新增 `export type Audience = 'the_caller' | 'an_auditor' | 'whoever_runs_it'`，
  `NOT_FOR_A_READER` 的值类型从 `string` 变成 `Audience`。每个字段各自的细节（「报告把 query_id 印在
  审计脚注里，本面没有审计脚注」）挪进**注释**——理由在这个文件里本来就住注释，`CARRIED_BY` 一直
  如此。
- 名单**仍然是手写的**，这一点没有变，也不该在本条里变：#403 那条登记说的是「web 边界把
  『读者能据以行动的拒答』和『意外错误』分开之后，不对读者说才有可查来源」——那说的是**异常**，
  不是**信封字段**。本刀只动值，不碰键的来历。

**新闸口，并且构造了它该说不的那个反例**：`test_every_written_off_field_names_one_of_the_declared_
audiences` 从同一个文件里读出 `Audience` 联合类型，再要求表里每个值都在其中（并断言联合至少两员、
表非空，否则这条会空转）。实测确认：三个 audience、四个条目、一个不在集合里的值会被抓住。
**为什么这比一句散文强**：散文可以为任何东西写出来，而在三个里挑一个**是会挑错的**——会错，才值得写。

**证据**：语言债 12 → 8，`types.ts` 4 → **0**（删行，不是降数）。剩下 `llm_bridge.py` 7 +
`language.py` 1。前端 `tsc -b` 仍是 HEAD 上那三条既有报错，本刀一条没加（登记项 #489 未动）。

**基线（本条）**：10702 → **10702**——**不动**，因为新增的那一条闸口恰好补上了债表删掉
`types.ts` 那一行所减少的一个参数化用例。这个巧合本身值得写下来：**基线不动不等于什么都没发生**。

**方法论沉淀**：(321)**一组「互不相干的备注」，先数它们回答的是不是同一个问题**。四段散文看起来是
四件事，是因为散文没有形状；一旦问「这些句子共同回答什么」，答案往往是一个没被写下来的封闭集合。
(322)**当翻译和豁免两条路都被堵死时，剩下的那条一定是改这个槽位问的问题**——这不是妥协，是那两条
路的堵死本身在指方向。(323)**一个理由能为任何东西编出来，一个分类会挑错**；要一个字段「说点什么」
不构成闸口，要它「在三个里挑一个」才构成。

### #493 场合早就拆出来了，只有措辞还焊在站点上（2026-09-01）

**现象**：`theta_builder.py` 3 条语言债，全是 raise 站点上的英文异常消息。

**根因假设**：承载它们的两个类是**裸 `ValueError` 子类**——**它们没有「物种」这个概念**。于是
「哪一种错」和「这次的事实」被压进同一个字符串，而写下那个字符串的是 raise 站点，站点作者用自己
正在想的那种语言写。

**为什么这是根因不是表象**：因为**场合早就被拆出来了，只有措辞焊在站点上**。那个非字面量检查本来
就带一个 `role=` 参数——「target」还是「given atom」——也就是说「概率语句的哪一半出了问题」这个
事实**从这个检查存在的第一天起就是一个槽位**，唯独那句话不是。这正是 `upstream/extraction_words`
（#470）逐字写下的发现：**站点之间不同的几乎总是路径，而路径从来不是那句话**——49 个 f-string 因此
收成 16 个物种。而这里的 `role=` 装的还是**词**不是值：把 `given atom` 插进一句中文里，就是在中文
句子中间放一个英文短语。

**改动**：
- 新增 `themis/runtime/theta_words.py`。`Half`（2 员，`probability_statement_half`）——
  `P(target | given)` 的两侧；`Refuses`（3 员，`theta_refusal`）——值不是字面量 / 两条语句对同一个键
  给了两个值 / 供给的质量把补集顶出了 [0, 1]。
- 两个异常类改成 `language.Voiced` 子类，**三个物种、两个通道**，而这不是错配：调用方 catch 的是
  **通道**，读的是**物种**，这是两个问题。`ConflictingThetaEntry` 一个类带两个物种——重复冲突和
  和越界，两者都是「你给的数不可能同时为真」，但只有一个是重复。把词表按 catch 通道分，会把这两件
  事压成「一句话 + 一个『是哪种矛盾』的洞」，而那个洞没法向读者解释。

**这一刀把一处更远的缺陷顶了出来**：`themis/web/failure.py` 的分支写的是
`isinstance(exc, SemanticError)`，而它真正在问的是「**这个异常自带句子吗**」。`SemanticError` 只是
**若干个** `Voiced` 子类中的一个——`MalformedBundleError` 是另一个，本刀新增的两个又是——而没被点名
的那些，抵达浏览器的方式和 `SemanticError` 被加进来之前**一模一样**：英文塞在 `diagnostic` 里，压在
一句读者早已拿到两种语言的 stage 句子下面。**又是一条闸口的措辞比它的判据窄**，本仓反复抓到的那个
形状：点名类，就是把它变成一张要靠人记得去扩的清单。改成 `isinstance(exc, language.Voiced)`——
判据本来就有名字。**这条分支此前一个测试都没有**，本刀补上一对：一个不是 `SemanticError` 的
`Voiced` 拿到自己物种的句子（旧分支漏掉的那一格），以及它的反例——一个没有物种的异常仍然落回
stage 句子。

**两处断言加强而不是迁就**：原来是 `pytest.raises(..., match="target 'x'")` 和 `match="given atom
'x'"`——在渲染好的句子里搜一个英文子串，**这种断言只能在一种语言里成立**。现在读 `species`、读
`words["half"]` 的 token，再把整句逐语言装配一遍，钉死中英互异且各自含有对应那一半的词。

**证据**：语言债 15 → 12，`theta_builder.py` 3 → **0**（删行，不是降数）。mypy Success (169 files)。

**基线（本条）**：10671 → **10702**。

**方法论沉淀**：(319)**场合已经是槽位、措辞还焊在站点上，是「多个站点其实是少数几个物种」的信号**。
判据不是「这些消息像不像」，而是「站点之间**不同的那部分**是不是已经作为参数传进来了」——是的话，
剩下的那部分就是同一句话。(320)**一个 `isinstance` 分支点名类，就是把判据换成了一份要人去扩的名单**。
问它真正在问什么：「自带句子吗」有名字（`Voiced`），「是不是语义检查器抛的」没有对应的判据。
找法：grep `isinstance` 里点了具体类名、而那个类有兄弟的地方。

### #492 一句解释，被放进了它所解释的那个值的槽位里（2026-09-01）

**现象**：语言债还剩 19 条，其中估计层 4 条：`dispatch.py` 3 条 + `mediation.py` 1 条。

**根因假设**：**每一条都是一句解释，被放进了它所解释的那个值的槽位里。**
- 两条 AR 集：`(−∞, +∞)` 是**记法**，「工具太弱无法约束效应」是对这个记法的**读法**，被一个破折号
  粘进了记法字符串里——而那个字符串正好要去填一句双语句子的 `{interval}` 洞。
- 一条 `four_way_unavailable_reason`：正面 `four_way` 是一个结构化的**块**，反面只有一个 `string`。
- 一条 `required_data.population`：这个字段装的是人群的**名字**（没有名字时用 `Unnamed` 那个词），
  而这里装的是一段**刻画**——「条件集里目前只带一条工具臂的那些分层」。

**为什么这是根因不是表象**：**因为一个值的槽位没法被问这个问题**。记法回答「这个集合是什么」，
回答不了「所以呢」；块回答「这个分解是什么」，回答不了「它为什么不在」；名字回答「哪个人群」，
在没人命过名的时候回答不了「哪些个体」。三处的**正面**全都有结构，只有读法／反面／没名字的那一侧
没有槽位——于是它们各自挤进了旁边那个值里。这句话 `language.state` 的 docstring 早就写下来了：
**Prose is what a system produces when structuring a sentence has no door**。门是有的；这三处是把门
开在了别处。这也是 #491 的同一个发现挪一层：那次是「一句话被塞进另一句话的**洞**」，这次是
「一句话被塞进一个**值**的槽位」。

**改动**：
- `gaps.Sentence.THE_SET_CONSTRAINS_NOTHING`。读法是一**句**，和报告集合的那句**并排**放进 gap 的
  `describes` 元组里——同一个信道、同一个列表，多一句话，而不是在 `{interval}` 里多一段。三个调用点
  各接一次（单工具 / 多工具 / 异方差稳健）。
- `gaps.Population`（新词表 `described_population`，1 员）。放在 `Unnamed` 旁边而不是里面，界线是
  **这次场合有没有值**：占位符站在没有值的地方，而这个是有值的——内核自己挑出来的一个子集，能说清
  是哪一个，只是没有名字可供传递。
- `warning_words.FourWay`（新词表 `four_way_unavailable`，1 员）。放这个模块是按**主题**而不是按
  字段：这个模块讲的是「估计层不拒答时对读者说的话」，而这一条自己有信道。
- `GapRequiredData.population: str | dict`。这是**跟随这个 dataclass 自己已经定下的形状**——
  `precision_target` / `time_window` / `sutva_concerns` 三个兄弟字段早已是「as a STATEMENT rather
  than as its text」。schema、`types.ts`、`gaps._occasion` 的渲染同步。
- 顺手结清同一处的两个相邻缺陷：两个渲染器对**同一个数学对象**用了两种减号（`_render_robust_ar_set`
  用 U+2212 `−∞`，`_render_ar_set` 用 ASCII `-∞`），现在是一个常量；`_render_robust_ar_set` 里的
  `fmt` 是死代码。**一个对象两个渲染器，代价就是这个。**

**mypy 抓到一个潜伏的缺陷**：`required_data.population` 一改成 `str | dict`，
`themis/kb/translator.py` 立刻不过——它把这个字段直接喂给 `KBQuery.population`，而那是要拿去
**查外部知识库的搜索键**。一段刻画不是任何知识库能被问的人群（那是关于这个程序的事实，不是谁发表过的
队列）。**今天没有活的 bug**（带刻画的 gap 全是 informational，`_resolve_query_kind` 对它们返回
`None`），所以这是**在有人走进来之前把门关上**，如实这么写。

**当场声明的取舍**：同一个 `if` 链里 `kind == "empty"` 渲染成 `∅`，**它也有读法而且更强**——AR 集
为空意味着这个置信水平上每一个效应取值都被数据拒掉。这一刀**没有加**：#492 的判据是「这句话本来
就在，只是被塞错了槽位」，而 `∅` 从来没有任何一句话，加一句是我没量过的行为改变（会不会和
`overidentification_rejected` 重复说同一件事）。登记为待办，不默默跳过。

**三处断言加强而不是迁就**：AR 那条是**新加的一对**——一个跑出 `whole_line` 并钉死三条语句的 token
顺序、`{interval}` 里只有记法、读法中英不同；另一个是**它的反例**，一个有界的集合不多说那一句，
而且它的记法在两种语言里是同一个字符串。四分解那条从 `assert "four_way_unavailable" in est` 变成读
token + 逐语言渲染。IV 回退那条补上 `population` 的 token 与中英互异。

**证据**：语言债 19 → 15，`dispatch.py` 3 → **0**、`mediation.py` 1 → **0**（两行都是删掉，不是
降数）。mypy Success (168 files)。

**基线（本条）**：10638 → **10671**。

**方法论沉淀**：(316)**记法与记法的读法是两件东西**。`(−∞, +∞)` 对每个读者都一样，「所以什么也约束
不住」不是——把读法粘在记法上，就是往一个「对所有人相同」的位置写进一种语言。找法：grep 渲染函数里
带破折号 / 冒号的返回值。(317)**一个判定的正面是结构、反面是散文，是缺陷的固定形状**。正面有块、有
记法、有名字，反面只有一个 `string`，因为没人给反面留槽位。(318)**放宽一个字段的类型是一次免费的
消费者普查**：`str` → `str | dict` 让 mypy 把所有把它当 `str` 用的地方一次列全，其中就有把它当外部
搜索键的那个——**比 grep 可靠，因为它按类型而不是按名字找**。

### #491 一句双语的句子，洞里塞了一句单语的话（2026-09-01）

**现象**：`scheduler.py` 还剩最后 5 条语言债。这个模块已经被前面四刀各清过一遍，这五条一次都没被
碰到。

**根因假设**：**五条全部落在 `themis.gaps` 拥有的那句双语句子的洞里**。三条是
`interventional_risk_*` 三个 gap 模板的 `{note}`，两条是
`interventional_risks_contradict_the_joint` 的 `{detail}`。

**为什么这是根因不是表象**：**不是规则漏掉了它们**——债表上 `scheduler.py: 5` 数的正是这五条，
一条不多一条不少（本刀之后那一行被删掉而不是降数，就是这个数是精确计数的证明）。**被量到了，
四刀还是没碰**，这才是要解释的事。

原因有两层。第一层：前四刀各自是按**字段**、按**生产者**、按**信道**组织的——`late_caveat` 是一个
字段，`required_assumption` 是一个字段，`data_contract_warnings` 是一个字段。而这五条**不属于任何
一个族**：每一条都是一个孤零零的值，交给**别人的**一句话。它们唯一的共同属性是**位置**——「在一个
洞里」——而按字段组织的清扫，永远不会把一个「位置」收拢成一批。

第二层是它们为什么在人眼里也不显眼：**从任何一端单独看，它都是对的**。看 gap 那一端：模板中英
俱全，连 `{note}` 这个洞都在两种模板里各留了一个。看站点那一端：那是一句通顺的中文，读起来没有
任何毛病。缺陷只存在于**接缝**上。所以**一句双语的句子，它的洞是一个独立的审计位置**——按位置
清扫是本刀新加的一种切法，不是对量具的修补。

**第二个共同点，同样是站点选的**：五条全部自带一个**连接符**。`{note}` 那三条是 `f" {note}"`
——一个 ASCII 空格顶在一句中文前面；`{detail}` 那两条是 `"；".join(...)`——一个中文分号夹在两句
英文之间。**两句话之间放什么、一个小句前面有没有空格，都是关于语言的事实**，而写下它的站点只
知道自己那一种语言的答案。这是同一个错误犯了两次。

**改动**：
- 新增 `themis/runtime/scheduler_words.py`。放在 `iv_words.py` 旁边而不是里面：那两个是 envelope
  schema 声明的**字段**、渲染器按名字查；这两个进的是**别人一句话的洞**——是不同的契约。
- `Tried`（3 员，`instrument_route_note`）：响应型多面体被递上一个工具之后发生了什么。一条说
  「没有任何干预风险可得」的 gap，在**工具存在且试过了**的情况下，说的是真话但没用——读者分不清
  「这张图没有工具」和「这张图的工具多面体用不上」，而只有后者值得动手。
- `Feasibility`（1 员，`consistency_constraint`）：**一个成员，两个场合**。两条臂的差别只是哪几个
  联合分布单元把它夹住，那是记法。第二个成员会是同一句话把 X=1 拼成 X=0。
- **`{note}` 的洞从 said 半边挪到 words 半边**。`assemble` 里 words 后于 said 施加，所以
  raise 站点声明的 `note=""`（「没什么要补的」，这在每种语言里都一样，是个**值**）被调用方填的
  语句覆盖（那是**一句话**）。`halve` 按值的类型自己读出该进哪半边，两条路一个关键字参数。
- **分隔符进模板**：三个 en 模板末尾改成 `. {note}`，zh 不需要。`language.assemble` 末尾加
  `.rstrip()`——**任何语言里，行末空格都不是一句话的事实**，而模板末尾的洞在这个场合没东西可填时
  是它唯一的来源。
- **拒答被引用（cite），不是被引述（quote）**。`str(exc)` 会用**默认语言**渲染，也就是往一句
  「读者自己选了语言」的句子中间写死了一种语言。`Voiced` 本来就带着 species 和这次场合的两个
  半边——那正是一条语句的全部材料——所以 `language.restate` 把它读回成语句就行，不是第二份
  `halve`。

**新开的门：`refusals.REFUSED`**。`refusal_sentence` 这个名字浏览器侧从「第一次要说一条拒答」起
就有了，**内核自己的读者一直没有**——`language.VOCABULARIES` 只在 `Word` 子类的类体跑过、或有人
显式 `declare` 时才有条目，而 `refusals.SAYS` 是一张表、没有人 declare 它。所以这一刀落地后第一次
跑，`iv_model_refuted` 渲染成了 `` `iv_model_refuted`（本版本没有它的说法）``。**这条不是回归，是
一直没被要求过**：以前没有任何洞里装过拒答。`language.declare(REFUSED, SAYS)` 一行补上。

**当场声明的取舍**：`assemble` 对 `words` 里的列表一律走 `listed` → `BETWEEN_ITEMS`（`、` / `, `），
而这两条是小句、按语言层自己的分法该走 `BETWEEN_STATEMENTS`（`；` / `; `）。这一刀**没有改它**：
改了会把仓库里每一个洞里的语句列表都从 `、` 变成 `；`，而我没有先量过那些洞装的是什么。本刀要
关的缺陷——分隔符由站点选——已经关上了（英文读者不再拿到中文分号）；「挑哪一个」是关于
`language` 自己那两张表的问题，登记为待办，先量再改。

**两处断言加强而不是迁就**：`test_a_theta_the_instrument_model_refutes_says_so` 原来在渲染好的句子
里找中文子串，现在读 token、读**嵌在洞里的那条拒答**（连同它自己的 `level_index` / `statistic` 两个
洞——被 cite 而不是被 quote，这些洞才还填得上），再逐语言渲染钉死中英各自到位。
`test_infeasible_experimental_risks_is_a_gap` 原来只断言 gap 的 `name`，现在断言两条同成员语句、各自
的 `quantity`，以及**两语言的接缝互不相同**。

**证据**：语言债 24 → 19，`scheduler.py` 5 → **0**（在债表里删掉一行，不是降一个数）。
mypy Success (168 files)。

**基线（本条）**：10605 → **10638**。

**方法论沉淀**：(313)**被量到 ≠ 被看见；按字段清扫收不拢一个「位置」**。债表精确数着这五条，四刀
仍然从旁边走过，因为每一刀都是按字段／生产者／信道组织的，而它们唯一的共同属性是**在一个洞里**。
所以**一句双语的句子，它的洞是一个独立的审计位置**：两端分别看都对，缺陷只在接缝上。清单还剩
东西却连着几刀清不动时，先问「我这几刀是按什么组织的，有没有一类东西根本不按那个分类聚集」。(314)**站点选的连接符是站点选的
语言**。`" ".join` / `"；".join` / `f" {x}"` 都是在替读者回答「两句话之间放什么」，而那是关于语言的
事实。找法：grep 生产端的 join 和字面量分隔符，尤其是被塞进模板洞里的那些。(315)**一个异常应该
被 cite 而不是被 quote**。`str(exc)` 是「用默认语言现在就渲染」；异常本身带着 species 和场合两个
半边，把它读回成语句既保住了读者的语言，也保住了它自己的洞。

### #490 把写在站点上的那句话翻译一遍，只是换了它辜负哪个读者（2026-09-01）

**现象**：`scheduler.py` 还剩 10 条语言债，其中 5 条是 IV 块上的两个 `string` 字段——
`required_assumption`（三处）与 `late_caveat`（那一整段）。

**根因假设**：这两个字段的病灶，本仓库已经用自己的话写下来过两遍，作者还是两个人。
- 第一遍是**量它的那条规则**。`late_caveat` 正是
  `test_no_sentence_reaches_the_reader_in_the_wrong_language` 开篇的那个案例——「一整段英文
  散文原样印进中文报告，而所有检查都是绿的」。后来它被翻译了，于是变成**一整段中文散文原样印进
  读者要的任何一种报告**。**把写在站点上的那句话翻译一遍，只是换了它辜负哪个读者。**
- 第二遍是**一个生产者拒绝加入**。反馈环那条路往 `required_assumption` 里写的是一个 **token**，
  并在旁边写明了理由：「其他每个生产者都往这儿写散文，而报告原样渲染它——这正是这一条不写的
  原因」。所以这个字段的契约**在它四个生产者之间是有争议的，而其中一个把这件事写下来了**。
  三个兄弟写散文、第四个写 token，这不是措辞分歧，是**这个字段没有形状**。

**改动**：
- 新增 `themis/runtime/iv_words.py`。放这里而不是 `themis/ledger.py`，因为两者只有一个是假设：
  另一个说的是「这个数**是**哪个估计量」，和「它**依赖**什么」是两个问题，本来就走两个字段。
- `Premise`（3 员）：`monotonicity_or_linearity` / `monotonicity_as_declared`（洞里放的是
  `monotonicity` **词**，不是它的 token——四个生产者此前各自把 token 拼进句子）/
  `linear_simultaneous_system`。**每个成员都带上它换来的估计量**：只被告知「单调性」而没被告知
  它换来的是 LATE 的读者，只知道一半。
- `Complier`（2 员）：`late_is_not_the_ate` 与条件那半 `strata_weighted_by_complier_share`。
  字段改成**列表**——那两半原来是 `+=` 接起来的，而**两句话之间放什么是关于语言的事实**，
  `+=` 只会一种。
- 五层同步：4 个生产站点 + schema 三个槽（`iv_identification` 两个 + `identification` 里的那份
  拷贝）+ 三个内核消费者（报告两处 `spoke`/`spoken`；`data_gap_report` 把前提放进 gap 句子的
  **洞**里，那是语句套语句——它此前是把文本拼进一句双语句子中间，也就是这条规则原始病例的
  同一个形状）+ 浏览器（`stated`/`sentences` 两处、`WORDS` 与 `VOCABULARIES` 两个注册处、
  重新生成的词表）+ 两个词汇表注册闸口。
- 反馈环那条路的 token 变成语句之后，**它旁边那段解释自己为什么与众不同的注释没有了**——
  它担心的事在结构上不再可能。gap 报告在有环时仍然让位（那是「读者该拿到哪一句」的决定，
  不是「用哪种语言」的决定）。

**闸口自己也变了**：`MUST_APPEAR` 从 `...late_caveat` 改成 `...late_caveat.[].token`，而它证明的
东西跟着变了：原来问「这段话是哪种语言写的」，现在问「只有条件工具才走到的那后半段，是作为
**成员**到达的，还是被谁**追加**上去的」。断言从在段落里找子串 `` `strata` `` 变成
`"strata_weighted_by_complier_share" in tokens`——前者只能在一种语言里成立。

**六处测试断言同样被加强而不是迁就**：披露契约是「读者被告知这个数是 LATE」，而原来搜的那句话
只能持有这句话的一种拼法。现在逐语言渲染后再断言，并钉死中英两版**互不相同**。

**证据**：语言债 29 → 24，`scheduler.py` 10 → 5。mypy Success (167 files)。

**基线（本条）**：10565 → **10605**。

**方法论沉淀**：(310)**翻译一个写在站点上的句子不是修复，是换一个受害者**——判据不是「这句话
现在是哪种语言」，而是「这个字段的类型允许它有几种语言」。`string` 的答案永远是一种。
(311)**当一个生产者在字段里写下与兄弟不同的东西、还在旁边解释为什么，那条注释就是缺陷报告**。
它说的是「这个字段的契约我不同意」，而一个契约有争议的字段是没有契约的字段。找法：grep 那些
解释「为什么这里和别处不一样」的注释。(312)**一个洞里放语句而不是文本**——双语句子中间嵌一段
单语文本，是这类缺陷最难看见的形态，因为两边分别看都是对的。

### #489 一个 `string` 字段让每个分支都成了自己那句话的作者（2026-09-01）

**现象**：`estimation_context.data_contract_warnings` 上有六句读者散文，五句中文、一句英文，
而那句英文和其中四句中文**在同一条 `if`/`elif` 链里**。两个生产者共写这一个字段：
`contract.py` 1 句、`dispatch.py` 5 句。

**根因假设**：字段类型是 `array of string`。**一个 `string` 字段让每个分支成为自己那句话的
作者**，而分支不知道谁在读。语言只是症状——那句英文不是漏译，是「这里该写哪种语言从没被规定
过」的必然结果：没有规则被违反，因为没有规则。#395/#467 在 `orientation_questions.py` 的 18 条
上诊断的是同一个病灶，解法（`statement.schema.json` 这扇门）这个字段一直没走。

**为什么是根因不是表象**：逐句翻译只会把六个作者变成六个双语作者，第七个分支还是第七个作者。
而且这个字段**两个模块共写、谁也不拥有**，所以没有任何一处有资格规定语言。

**改动**：
- 新增 `themis/estimation/warning_words.py`——`refusal_words` 旁边那条信道：那些以异常离开
  （没有结果可以承载），这些骑在信封上、旁边就有一个照样算出来的数。两个词汇表七个成员，
  中英各写一遍。
- `data_contract_warnings` 的 items 从 `string` 改为 `$ref statement.schema.json#/$defs/statement`；
  `contract.DataContract.warnings` 从 `tuple[str, ...]` 改为 `tuple[Statement, ...]`。
  去重从「比较句子」改为「比较语句」——vocabulary + token + 本次的事实，这是唯一一个在读者
  换语言之后仍然成立的比较。
- **两个词汇表而不是一个，这本身是这个字段的一条发现**：六条里只有第一条是关于数据契约的，
  其余五条是关于「一个 dose-response 请求挂到了哪个 query 上」——是关于**程序**的。它们共用
  一个字段，只因为当时那是唯一现成的字符串列表。每个 token 旁边带着自己的 vocabulary 名，
  就把这道裂缝显式化了，也给日后拆出第二条信道留了记号。
- `estimator_fallback.reason` 也一并进了 statement，并且**和它旁边那条 warning 是同一个语句
  对象**。浏览器本来就跳过这个块，理由写在 `types.ts` 的注释里：「它说的和那句话一模一样」——
  那在此前只是一句无法核对的断言，现在是一个可以 `assert fallback["reason"] in warnings` 的事实。
- 五层同步：产物（两个生产者）+ schema（两个槽位）+ 浏览器（`types.ts` 的类型、`verdict.ts` 的
  `stated()` 渲染、`WORDS` 与 `VOCABULARIES` 两个注册处、重新生成的 `kernelWords.generated.ts`）
  + `reader_words.GLOSSED` 两行（成员锚在模块上而非 schema enum 上：schema 说的是这些**以什么
  形状**到达，不是这个集合有哪些成员）+ 渲染提示词两处。

**测试也跟着变好了**：五处断言原本在字符串里找 `"没有任何 effect 查询"` / `"二值"` /
`"建议阈值"`——那是在断言「内核当时想的是哪种语言」。现在断言 token 和它的事实，并在契约那条
上直接钉住两种语言都能出、且**互不相同**。

**证据**：语言债 36 → 29，模块 8 → 7；`contract.py` 清零，`dispatch.py` 9 → 3。mypy Success
(166 files)。前端 `tsc -b` 的三条报错在 HEAD 上就在（用 detached worktree 对照确认），不是本次
引入的；**它们仍然没修，另记一条前沿**。

**基线（本条）**：10519 → **10565**（新词汇表进入多个按词汇表参数化的注册闸口；skip 206 → 208
是那两个 `EnvelopeName` 子类在 #382 的身份闸口上按设计跳过）。

**方法论沉淀**：(307)**看见一个家族里混着两种语言，先看承载它的字段是什么类型**——`string`
类型的字段不是「忘了翻译」的地方，是「作者身份被下放到每个分支」的地方，而分支不知道读者是谁。
判据：这个字段有几个生产者？两个以上而没有主人，就没有任何一处有资格规定语言。(308)**一个
字段里出现两个词汇表，往往是这个字段名在说谎**——`data_contract_warnings` 里六条只有一条关于
数据契约。不必立刻改名（那是信封契约的改动），但让 vocabulary 名随每个 token 一起走，裂缝就
从注释变成了数据。(309)**注释里的「这两处说的是同一件事」是一句无法核对的断言**；让两个槽位
装同一个对象，断言就变成事实。

### #488 债务表在替十七条文本保管一个没人做过的决定：它们**是什么**（2026-09-01）

**现象**：#487 之后语言债还剩 54 条。其中十七条根本不是「缺一份翻译」——`kernel.py` 7、
`claim.py` 8、`joint.py` 1、`transport.py` 1、`runtime/counterfactual.py` 1。

**根因假设**：**债务表被当成了未决分类的暂存处**。这个规则的出口一直有三种，而这十七条各自
属于其中一种，只是没人说过是哪种：文本的**类别**没被判定，于是默认落进「欠一份翻译」。三种
答案在仓库里都已经存在，缺的不是机制，是那次判定。

**改动（一种一种说，因为它们不是同一件事）**：
- **`kernel.py` 7 条是 finding，而 allowance 读的是它们住在哪棵树、不是它们是哪个类。**
  `AUDIT_TREES = ("themis/verifier/", "themis/oracle/")` 的判据是「审计轨迹」，措辞是目录。
  审计轨迹的载体是 `VerificationError`：树里 1039 次、树外 7 次，全在 `kernel.py`——kernel 把
  `extensions` 里的展示副本和它刚审完的答案对照。`themis.verify` 把这 1046 条经同一个
  `{ok, error}` 交给同一个读者。所以 `Wrote.AUDIT` 现在有**两扇门**：按类（`_findings`，在哪
  都算），按树（那两棵树里不在 raise 里的文本——helper 的 message 参数、期望形状表——它们正在
  为一条 finding 备料而本身不是）。读路径的规则会在有人把一条检查从 verifier 挪进 kernel 时
  让债务表无故变动，而那次移动什么也没改变。
- **`claim.py` 8 条是一个词汇表的维护者侧。** `BLOCK_REASONS` 的**键**被消费（`blocked` 拒收
  表外的键，键本身走进 `Evaluation.declined`），**值**哪儿也不去——这是 `refusals.Refusal.says`
  与 `gaps.Need` 已经用了很久的形状：一个字段给维护它的人，一个字段给读它的人。**这条是量出来
  的不是照抄文档的**：模块自己的 docstring 说「reasons 还没有被消费」，只说对了一半。清掉它的
  条件写在 allowance 里：`declined` 走进信封那天。
- **`joint.py` 1 条是不变量。** `_ContrastCornerEmpty` 由抽样循环 `except (ValueError, ...)`
  接住、丢掉这一次抽样，从不打开异常。名字只为被按类型接住而存在——正是 `Undeclared` 的定义。
- **`transport.py` / `counterfactual.py` 各 1 条根本不是散文。** 两者都是 `MALFORMED_ARGUMENT`
  的 `shape=`，而 `shape` 会被拼进读者自己那门语言的句子里。前者写着「…, or the multi-Z … form」，
  后者写着「over the four (False/True) pairs」——**一个英文连接词插在中文句子中间**，正是这个
  规则的 docstring 里 `precision_target` 那个原始病例。改成记号：`|` 就是那两个形状本来的并集，
  枚举 `{(False|True, False|True): probability}` 就是「四个」。

**新闸口与它的反例**：按类的那扇门必须能说「不」。`kernel.py` 里每一条 raise 都是 finding，
所以在包上跑永远看不见它拒绝——反例写在片段上：同一个函数里两条 raise 携带同一个字符串，
`VerificationError` 的被标记、另一个不被标记。

**证据**：语言债 54 → 36，模块 13 → 8。剩下的 36 条现在是一张干净的分布：24 条是真的读者散文
只写了中文（`scheduler` 10、`dispatch` 9 及四个零头），7 条在 LLM 桥（其中 4 条是写给模型的
提示词，不是写给读者的），3 条是 program 形状拒答（该走 `#476` 的物种+事实），4 条是
`types.ts` 里那张自己写明「这里没有一句话是说给读者的」的表。

**基线（本条）**：10522 → **10519**（删掉五行债务表条目 −5，新增一条 allowance +1，新闸口 +1）。

**方法论沉淀**：(305)**一张「待办清单」型的表会悄悄替人保管未做的决定**——债务表上的每一行都
读作「这条欠一份翻译」，而其中有 17 行真正欠的是一次分类。分辨法：对着表里的条目问「假如我
现在就把它翻译了，谁会读到那份译文」，答不上来的那些欠的不是翻译。(306)**当一条 allowance 用
地址（目录、模块、路径）表达一个关于角色的判据时，它一定在某处漏掉了同角色的异地成员**——
而且漏掉的那些会长得像新问题。#487 与本条是同一个病灶的两次发作：一次在 `builtin` 这个代理上，
一次在目录这个代理上。

### #487 同一句话在代理的两侧各写了一遍，于是一半是不变量、一半是债（2026-09-01）

**现象**：语言债表上有七条属于同一个物种——`answers` 1 条、`intervals` 4 条、
`output/formula_text` 1 条、`questions` 1 条，说的都是「本包自己的某张声明表里没有这个键的行」。

**根因假设**：这个物种在包里有**五种措辞、两套约定**。`ledger.admissible` /
`routing.route` / `risk_provenance.admissible` 抛裸 `KeyError` 并附上「表里已声明的是哪些」，
被语言规则当作 invariant 放行；上面四个模块抛具名 `KeyError` 子类、不附那份清单，被计入债务。
两半之间**只差一件事：作者需不需要一个名字给测试去 catch**——那是关于测试的事实，不是关于
读者的。规则的判据是「这句话说给谁听」，措辞却是「raise 处的名字是不是 builtin」。代理在全包
其余地方都成立，唯独在这里失效，因为同一句话在代理的两侧各出现了一次。

**为什么不能靠放宽代理来修**：`EstimatorFailure` 也派生自 builtin（`RuntimeError`），
它名下 404 个 raise 站点里绝大多数是读者会拿到的拒答。所以「派生自 builtin」从来就不是可用的
更宽读法——**受众必须被显式声明，不能被推断**。这一步是先量了再设计：先想到的那个方案被这次
测量当场否掉了。

**改动**：
- 新增 `themis/registry.py`。`Undeclared` 是**受众本身写成一个基类**：凡子类都因为本仓库自己
  维护的某份声明不完整而触发（表里没有行、行里声明了「没有」、生产者该填的字段没填），键、
  行、字段全部产自包内，外面的人既造不出也修不了。**它和裸 `raise KeyError(...)` 是同一件事**，
  名字只是为了被 catch——而「被按类型 catch 的异常仍然是不变量」这句话，此前没有地方写着。
- `NoRowDeclared(Undeclared, KeyError)` + `row_for(table, key, *, named)` 收掉八个站点的五种
  措辞。**它携带三个事实、不写句子**：哪张表、哪个键、这张表**声明了哪些**——最后一条原本八个
  站点里只有三个写。被删掉的那半句都是建议（「加在发出它的估计量旁边」「加在文法旁边」
  「加在过程旁边」），而对一个已经站在这张表的点分名字前面的人，那句话说的是他看得见的事。
  剩下的正是本包从另一头收敛到的形状：**站点携带事实，渲染方挑词**；不变量没有渲染方，于是
  事实就是消息，类名就是谓语。
- `intervals` 里两条**故意不并进去**的：`NothingToBeTight`（行存在、且声明了「没有这个区间」）
  与 `WidthNotStated`（生产者没写自己声明要写的字段）。没有行 ≠ 行说没有：前者靠补一行解决，
  后者靠不问解决。两者现在都经由一个说明了受众的类抛出。
- 语言规则的第二支从「名字是不是 builtin」改读「这个类**声明了**自己是什么」，
  `_declared_invariants()` 从源码的基类链传递求出，不是列表——明年新加一个，作者写下声明就被
  放行，没写就是债。代价是必须写下来，而那正是要的代价。

**新闸口与它的反例**：`Undeclared` 说「这句话永远不会递到读者手上」，语言规则照单全收，所以
必须有一条闸把它钉住——**没有任何地方按类型 catch 到一个不变量之后去读它的文本**。只管具名
handler：`except Exception` 读到的可能是 `ZeroDivisionError`，那是崩溃信道不是对这个物种的处理，
也正是裸 `raise KeyError` 一直被放行的同一个理由。闸口的反例单独写：
`except WidthNotStated as exc: return str(exc)` 判 True，`except WidthNotStated: return UNSTATED`
判 False——后者正是 `intervals.width_or_unstated` 现在的样子（降级成一个词，不是一句话）。

**证据**：九个站点端到端跑过，一句话；`test_a_class_is_an_invariant_only_where_it_says_so`
把「派生自 builtin 不构成声明」写死在 `EstimatorFailure` 上。语言债 61 → 54，模块 17 → 13。

**基线（本条）**：10521 → **10522**。

**方法论沉淀**：(302)**一条规则的措辞是它判据的代理时，去找同一个东西在代理两侧各出现一次的
地方**——那里代理和判据分了岔，而两侧读起来都天经地义。找法不是审规则，是审**被规则分到两边
的同一个物种**。(303)**放宽一条代理之前先量它会放过什么**：这次「派生自 builtin」看上去正是
那个更宽的读法，一测才知道它会连同 404 个读者可见的拒答一起放行。先量再设计，别先设计再验证。
(304)**受众可以是一个基类**。「这段文字说给谁听」此前只能靠 allowance 清单表达，一条一个槽位；
写成基类之后它是可传递、可自动扩张的，且**逼作者当场做这个决定**——而清单是给人抄的。

### #486 拒答的理由是关于那两个统计量的，不是关于那个问题的（2026-09-01）

**现象**：`markov_blanket` 在列的类型混合时拒答 `mixed_types_in_one_test`——「混合类型的
检验没有实现，把分析拆开，或者把连续列离散化」。而**把结局二值化之后再问同一个问题**，
就是读者最先撞上的那种混合。

**根因假设**：这句拒答是诚实的，它给的理由也是真的——Fisher-Z 的充分统计量是相关矩阵、
卡方的是列联表，谁也不是对方那些列的充分统计量。但**这个理由是关于那两个统计量的，不是
关于那个问题的**：条件独立性检验并不要求列同质，只是这两条已建的路各自要求。找洞的判据
因此不是「谁没建」，而是「拒答的理由挂在哪一层」——挂在实现上的拒答，往上一层往往有答案。

**选哪个混合检验，是被这个包的验证器纪律决定的，不是被功效决定的**。审计要从记录的充分
统计量在没有数据的情况下重算每一次检验，所以候选之间的分界不是「更强 / 更弱」，是「统计量
写得下来 / 写不下来」：核方法的是 n×n Gram 阵，秩方法的是秩，两者都等于原数据——**要携带
原数据才能被审的东西不是 artifact**。Lauritzen & Wermuth (1989) 的齐次条件高斯族的统计量
是逐格的 [计数, Σy, Σyy']，而检验要问的每一个列集合都是它的一个边缘。它换来的代价是一条
前提：各个离散格共用一个协方差。**而前提正是这个包会记的东西。**

**改动**：
- `discovery.py` 第三条路 `test="cg_lrt"`：`_cg_cells` / `_cg_loglik` / `_cg_dof` /
  `_cg_test`。l(V) = Σ_i n_i·log(n_i/n) − (n/2)·log det Σ̂ − (n·|C|/2)(1+log 2π)，
  G² = 2[l(XYS)+l(S)−l(XS)−l(YS)]，df 是同一组四个模型自由度的带号组合，
  df(V) = (∏k−1) + |C|·∏k + |C|(|C|+1)/2。
- artifact 新增 `conditional_gaussian` 块与第三种检验条目形状。条目的统计量叫
  `likelihood_ratio` 而不是复用 `statistic`——schema 自己写着「三种形状靠**携带哪个统计量**
  区分」，第三种写成第二种的样子会让 `oneOf` 认不出来；**命名与可区分性是同一个决定**。
- 验证器第三支：`W = T − B`（总离差减格间离差，方差分析恒等式）而不是生产端的逐格减均值，
  行列式走 Cholesky 而不是 LU——同一个矩阵，两条路，没有共用的一行。
- `MIXED_TYPES_IN_ONE_TEST` 删除。它说的是「检验没建」，而那句话现在是假的。换成
  `THE_CELLS_LEAVE_NO_SPREAD_TO_POOL`：离散列把样本切得太碎、减掉各格自己的均值之后不够估
  那个公用协方差。**两句话对读者不是同一件事**——只有后一句的补救办法是关于他们的数据的。
- 检验的印刷名从句子处的 `if/else` 挪进 `_TEST_NAMES` 表。第三个值会把那个 `else` 变成
  一句关于「跑的是哪个检验」的假话，而且是静默的——因为假分支此前从没错过。

**证据**：混合帧 a(离散,3层)→t(连续)→b(离散,2层)，外加无关的连续列 c，n=4000：毯子
`('a','b')`，c 被挡在外面（G²=0.167, df=1, p=0.68），两个成员 p<1e-130。**oracle 是它自己的
两个退化点**：无离散列时 G² = −n·log(1−ρ²) 到 1e-9（这是恒等式不是近似——Fisher 变换正是
这个量的方差稳定化），无连续列时自由度精确等于 Σ_s (k_x−1)(k_y−1)、统计量与 Pearson χ² 差
<5%。所以两条老路**一位没动**，一致性由测试钉死而不是由重构保证。七条伪造全被拒，其中
「把七个观测从一个格挪到另一个格」总数不变、结构无一处可抱怨，只有重算那四个拟合才看得见。
齐次前提在哪里咬人也写成了测试：两格同均值不同方差时检验读成独立——是**漏报不是误报**，
前提花的是功效、不会凭空造边。`tests/test_a_column_of_each_kind_can_meet_in_one_test.py`。

**基线（本条）**：10506 → **10521**。

**方法论沉淀**：(300)**一条拒答的理由挂在哪一层，决定它是能力边界还是实现边界**——「这两个
统计量都不适用」是关于实现的，「这个问题没有答案」才是关于能力的。前者往上一层通常有答案，
而它读起来和后者一模一样。找法：读拒答的**理由**而不是它的措辞，问「这句话是关于什么的」。
(301)**当一族方法要在验证器纪律下选型时，先按「充分统计量写不写得下来」筛，再谈功效**——
写不下来的那些不是更贵，是**根本进不了这个架构**：审计要在没有原数据的情况下重算，而
要携带原数据才能被审的东西不是 artifact。换来的前提要显式记进 artifact，并**单独写一个测试
说明它在哪里咬人、往哪个方向咬**（漏报还是误报）。

### #485 「经典误差不动点估计」里那个形容词，调用方一直可以收回（2026-09-01）

**现象**：`measurement_error={"y": {error_variance, differential_by:"x",
differential_coefficient:0.5}}`——真值 β=0.8——返回 `numerically_solved`，点估计
**1.3103 = β + δ**。没有拒答，没有标注，信封上任何地方都没提过 δ。声明里那一条「说这个数
是错的」的键，被静默丢掉了。

**根因假设**：这个包到处在说「结局上的**经典**可加误差只花精度、不动点估计」。这句话是对的，
而其中干活的那个词是**经典**——调用方在同一份 spec 里就能收回它。读结局误差声明的那一行
只读 `error_variance`，`DeclaredVariance.from_spec` 自称「是**归一器**不是校验器」，于是
「这份声明里有没有没人读的键」这个问题**没有主人**。而在 Y = Y* + δ·(X − E[X|Z]) + f 下，
普通后门拟合把 δ·X̃ 整个吸进暴露的系数，估的是 βx + δ。这是本轮第八次同一形状：**闸口的
措辞比它的判据窄**——那一行「不校正只定价」的理由里点了名的前提（非差异），代码里没有
任何东西建立过它。

**第二个缺陷，修好第一个之后才看得见**。判断「声明的 σ²_v 装不装得进残差」的那道闸，拿的是
**总方差**去比。这个判据只在「误差整份都落在残差里」时成立——那正是经典误差的定义。δ 被
声明时，δ·X̃ 已经被设计吸走，残差里只剩 σ²_f。于是 δ=1.5 那次，一份**自洽**的声明
（σ²_f=0.36，远低于残差 1.366）被 `outcome_error_exceeds_residual_variance` 把**整条查询**
否掉：声明 3.689 对残差 1.366。没被否掉的那些，精度代价按一份不在那个残差里的方差算：
δ=0.5 时报 noise_share 0.534 / se_inflation 1.465，真值是 0.352 / 1.243。

**改动**：
- `estimate_differential_outcome_error`：闭式 βx = naive − δ，新路由 `differential_outcome_error`
  （precedence 105，紧接声明行之后、所有估计器之前）。它**拥有**查询而不是标注——定价是
  别人答案旁边的一句注解，而这是答案本身。
- `outcome_error` 的两个入口都接 δ，共用 `_split_off_the_tracking_part`：送进残差比较和定价的
  是**算出来的余量**，不是传进来的标量。δ 缺席时余量恒等于 σ²_v，已发布的数一位没动。
- `DeclaredVariance.inflation_interval(..., absorbed_share=)`：研究量的是**总量**，所以被重抽的
  是总量，第 X 抽时残差里剩的份额是 `(share+absorbed)·df/X − absorbed`——上式的平移，仍单调，
  分位数仍精确；absorbed=0 时逐项还原。
- 假设账本：δ 在场时 `outcome_error_classical_non_differential` 被**替换**成
  `outcome_error_classical_once_the_exposure_is_partialled_out`，不是并列。并列等于在读者面前
  写下一句调用方自己的声明否定掉的话，旁边还摆着按这句矛盾算出来的数。
- 路由属性的根因也一并修掉：`_declared_tracking` 让**键在不在**决定路由、**值能不能用**由
  估计器判。原先两问合一，第二问的「不能用」用第一问的话说了出来——一个不可用的 δ 读成
  没有 δ，拥有它的那一行从不运行，答案照旧在调用方特意写下来要收回的那个前提下出厂。
- 两条信道的口径统一：兄弟行 σ²_u = σ²_0 + δ²·Var(Ỹ|Z) 是对**轴的残差**取的，结局侧原先文档
  写 V = δ·X + f（总量按 Var(X) 分解）而算术按 Var(X|Z)——两套口径，其中一套没写下来。
  点估计两种读法相同，分解不同；统一到残差，并在类文档里说明为什么。

**证据**：δ ∈ {−0.4, 0.3, 0.5, 1.5}，n=20000，误差 <0.03，而**朴素数的偏差是校正后的 10 倍
以上**；σ²_v 翻 5 倍点估计逐位不变（这是两条信道最锐利的分界——兄弟行那边方差是校正的一半）；
δ ∈ {0.5,1.5,2.5} 三次的 noise_share 差 <1e-3，因为按构造余量不变——按总量算它会随 δ 爬。
十条反例全被拒，其中两条是今天才补上的闸：**δ 在块上和在充分统计量里各记一次**，原先没有
东西把两份记录钉在一起（读者判断的可以是另一个数）；以及 `design_error_tracks_*` 前提**从未
被要求出现**——两条信道都是，一并补。`tests/test_an_outcome_error_that_tracks_the_arm_is_not_free.py`。

**基线（本条）**：10472 → **10506**。

**方法论沉淀**：(298)**一句话里的形容词就是一条前提，而调用方能不能收回它，决定了下游每一处
重复这句话的地方是不是在说谎**。找法：在文档和 prompt 里搜「经典 / 非差异 / 独立 / 线性」这类
限定词，然后问「输入里有没有一个键能让它变成假」——有，就去看谁读了那个键。(299)**当一个
声明的含义依赖于「哪一份在残差里」这类由别处决定的事实时，别把那份方差当标量传**：让它成为
在知道设计之后算出来的量。表象修法是在每个读者那里加一个 if，而读者的数量只会增加；今天恰好
是两个。

### #484 两个特例之间站着一个拒答，而它们本是同一件事的一维切片（2026-08-31）

**现象**：误分类率既随处理臂变、又随协变量变（按治疗中心不同的检出偏倚——现实里最
常见的那种），Themis 拒答 `differential_by_unknown`。它已经会按臂给一套矩阵（检出偏倚），
也已经会按协变量层给一套（按站点变的准确率），唯独两者同时就不行。

**根因假设**：识别上什么都不缺。校正本来就是**在每个 (arm, z) 格里求逆**，每个格子本来
就有属于自己的矩阵——缺的只是**一种说法**：这张矩阵属于哪个格。`differential_by` 是
一个字符串，于是「轴」只能有一维；两个已建的情形不是两个能力，是同一件事沿两条坐标轴
各切了一刀，而它们中间那条拒答，拒的是**没被切过的原件**。这跟 #483 是同一个形状：
判据（这个格子有没有自己的矩阵）比措辞（轴是不是那一列）宽，措辞把宽的判据说窄了。

而且**联合轴是三者中最弱的前提**，不是最强的：「率随臂变」和「率随层变」各自都额外
断言了「在另一个坐标上不变」。所以它进假设账本是**一条**，不是两条——两条并排读起来
恰好是那两个更强的断言。

**改动**：
- `differential_axis(differential_by, *, home, adjustment, mismeasured, role)`：轴归一为
  **列的元组**，一列是元组长度为一的那个特例。内部一律按**格**（cell）建键、比较、覆盖，
  两个已建情形因此不是分支，是同一段代码的 n=1。
- 顺带修好一处不对称：「轴不能是被校正的那一列」原先只有暴露信道有专属物种，结局信道
  会掉进泛化的 `differential_by_unknown`——让读者去查一个拼写正确的列名。检查移进
  `differential_axis` 内部，**排在未知列检查之前**，两条信道同一套次序。
- 信封：`differential_by` 一列时是名字、多列时是名字的列表；每条记录的 `level` 同理是
  标量或列表。**类型本身说明轴有几列**，而这正是 `differential_by` 在旁边说的同一件事。
- 假设账本新增前缀族 `differential_misclassification_by_cell_{a,b}`（沿用同文件
  `backdoor_adjustment_{...}` 的写法）。
- 验证器两条信道各自泛化：`_axis_columns` / `_cell_key_v` / `_axis_slots` / `_record_cell`。
  暴露信道那支原本是「一张 M_z 乘整个 p_obs」，现在按结局列循环——轴不含结局时，
  每列选到同一张矩阵，是**同一段算术说一次而不是两次**。

**证据**：四个格子四套 (sens, spec) 全不同，n=120000。结局信道 0.20168 vs 真值 0.20015，
暴露信道 0.20137 vs 0.19766；而**朴素数是 −0.021 / −0.041**——真效应 +0.20，未校正的
读者读到的不是「小一点的效应」，是**相反方向的效应**。三条反例都被拒：伪造的点；
**把两条记录的 level 对调**（矩阵、det、tally 全都自洽，只有「这张矩阵管哪个格」被换了
——只有按整格重导才看得见，换矩阵那种伪造会被 det 拦住，测不到键）；以及两列轴上写标量
level 的记录（作为形状错误被拒，而不是外溢成「这层没有矩阵」——那是句关于错误对象的真话）。
`tests/test_a_matrix_may_vary_along_more_than_one_column.py`。

**基线（本条）**：10459 → **10472**。

**方法论沉淀**：(296)**两个特例分别建成之后，它们中间那个「都要」的情形往往不是更难的
第三件事，而是没被切过的原件**——判据（每个格子有自己的矩阵）从来是按格说的，是**签名**
（一个字符串）把它压成了一维。找法：看到两个并列的 `if axis == A: ... elif axis == B: ...`，
问「A 和 B 是两种能力，还是同一个参数的两个取值」。(297)**前提的强弱方向要单独判断，
不能按「条件更多 = 假设更强」来猜**——联合轴看起来是「又随臂变又随层变」，读起来像两条
假设叠加，实则是三者中最弱的一条：两个单轴情形各自多说了一句「在另一个坐标上不变」。
写进账本时说错方向，就是把最保守的那次分析标成了最激进的。

### #483 「连续中介要密度估计」把公式需要的东西说错了（2026-08-31）

**现象**：`X → M → Y`、`X ↔ Y`，M 连续。前门在图上成立、识别层给出 mediators=[m]，
估计层却拒答：`mediator_not_discrete`。拒答词说「高基数情形需要**密度估计**，已推迟」。
同一句话的另外两个形态是 `continuous_mediator`（层数超过每列 20 的上限）和
`mediator_strata_intractable`（∏ k_i 超过 2048）。三个物种，一个意思：这个前门没法靠
在中介的层上精确求和来回答。

**根因假设**：这句话把「前门的中介积分」和「密度估计」绑成了一件事，而它们不是一件事。
Pearl 3.29 里 P(M | X=x) 是外层平均的**权重**，不是要画出来的曲线；二值处理下，
`X=x` 那一组的样本行**本身就是**这个权重。于是外层积分是一次组内取均值，内层对 x′ 的
和是两点加权——每行两次模型求值，`O(n)`：

    E[Y | do(x)] = ⟨ Σ_x' P(x') · Ê[Y | X=x', M=M_i] ⟩_{i : X_i = x}

不需要密度、不需要枚举、不受交叉积上限约束，**线性和 logistic 结局都成立**。被推迟的
从来不是「连续中介的前门」，是「非参数密度下的前门」——而后者根本不在通往前者的路上。
这跟 #481 是同一个形状再往前一层：那次是**能力写好了却没有路到得了它**，这次是
**判据（精确求和做不到）被写成了结论（这个问题答不了）**。

**改动**：
- `frontdoor.exactly_summable(df, mediators)`——**一个谓词，问一次**：这组中介的联合
  取值能不能被精确求和。三个旧物种的三条判据全在里面（分数取值、单列层数、交叉积），
  因为它们回答的是同一个问题。返回假不再是拒答，是**岔路**。
- `_point_estimate_frontdoor_empirical`：新插值端，`frontdoor_empirical_{linear,logistic}`。
  两条路的差别只有一处——P(M|X) 来自拟合的多项 logistic 链，还是来自各臂自己的行——
  所以识别层的许可、验证器的规则、答案形状全都是同一份。
- **路只选一次**：bootstrap 收的是点估计函数而不是列名。重抽样只会让某列的取值变少、
  不会变多，所以「全样本可精确求和 ⇒ 每个重抽样都可以」，这条不变量写在谓词的
  docstring 里，也是区间不会由两个不同估计量拼出来的原因。
- `mediator_conditional_taken_from_the_arms_own_rows`：这条路多出来的那一个前提，
  进假设账本。枚举路不带它。
- `numeric_estimate.front_door_empirical`：两条标准化臂 + 处理边际 + 结局系数 +
  中介位移。`verify_frontdoor_empirical_numeric`（内核直调）用它**重算**：两种结局形态
  都查差分恒等式，线性形态另查 **point = 系数 · 中介位移**——截距和处理项在两臂相减时
  抵消，所以这正是前门乘积法则，而乘积的两半都在信封上。logit 上标准化不可折叠，
  能查的就到差分恒等式和「每臂是概率」为止，再往前就是审计在跟自己核对。
- **结局测量误差那一行跟着走**：它借的是前门的设计，原先也借它的拒答（`SPAN_OF_ONE_MEDIATOR`
  那条静默出口的全部理由是「两行下面那个估计量会用自己的名字说同一句话」）。现在它不说了，
  所以静默出口连同常量一起删掉，`_build_design` 自己问 `exactly_summable`：能精确求和就
  按层展开指标，不能就按 `design_terms` 读成量——**残差要围绕的，必须是真正被拟合的那个模型**。
- 三个 Refusal 物种（`continuous_mediator` / `mediator_not_discrete` /
  `mediator_strata_intractable`）连同 schema enum、reader 词表一并删除。**没有任何一条
  路能产出的物种，是词表许诺了却说不出口的一句话。**

**证据**：`X→M→Y, X↔Y`，M 连续，真值 = 1.3 × 0.7 = 0.91（两个系数都不告诉估计量），
n=20000 实测误差 < 0.03，而忽略图的朴素回归差了 10 倍以上。三条反例都构造了并且被拒：
伪造的点被差分恒等式拒；**把点和臂一起挪、让它跟自己自洽**的伪造被系数×位移那一步拒；
声称走了这条路却不带 block 的信封被拒。`tests/test_a_front_door_does_not_need_a_density.py`。

**基线（本条）**：10449 → **10459**。

**方法论沉淀**：(294)**一句拒答里往往有两个句子：一个关于「我这个算法做不到」，一个关于
「这个问题答不了」。前者是真的，后者是从前者推出来的，而这一步推理几乎从不写下来**——
本档三个物种的拒答词都在同一处折断：「精确求和做不到」（真）→「需要密度估计」（假，
因为公式要的是权重不是曲线）→「已推迟」（于是变成能力边界）。找法：拿一条拒答，
问「它说的是哪个算法的极限，还是这个估计量的极限」，再问「这个估计量真的只有这一个算法吗」。
(295)**判据从「取值的地方」挪到「决策的地方」，一个拒答就变成一个岔路**——`_discrete_levels`
在被要人索取层集合的那一刻才判断，那已经晚了一步：此时对答案唯一能做的事就是停下，
于是每个调用方都继承了一个「这个拒答该不该算我的」的问题（那正是静默出口存在的原因）。
同一个事实早问一步，就只是选路。

### #482 前门是图的性质，标签却因问题的性质被扣下（2026-08-31）

**现象**：`X → M → Y`、`X ↔ Y`、`C → Y` 这张图上，问 `P(Y | do(X), C=c)`，图层标注写
`pattern: "c_factor"`——**引擎的名字，不是结构的名字**。读者拿到的那一句「这个数是怎么来的」
于是什么结构都没说，而同一张图上 `generalized_front_door_sets` 实测**确实返回了**
mediators=[m]。

**根因假设**：`scheduler.py` 写着 `front = () if given else generalized_front_door_sets(...)`。
注释给的理由是「带条件的查询问的是别的东西，所以不给它这个标签」——**这句话是真的，但它说的是
估计量**：P(Y|do(X),Z=z) 确实不是普通前门那个估计量。而**标签说的是图**，图上的前门还在。

**为什么是根因不是表象**：同一个函数里**后门标签从不被这样扣下**——
`minimal_adjustment_sets(graph, x, y, given=given, …)` 带着条件一起算并给出答案。两者的不对称
不是对两种结构的判断，是对**两个签名**的判断：前门求解器没有 `given` 参数，于是当时选了
保守的「干脆不给标签」。可标注不是识别结论（Phase 15 之后识别一律走 ID/IDC 引擎，两种情形
都照常出数——实测 (a) `general_id_idc_plugin` 0.0879、(b) `general_id_plugin` 0.0767）。
说出「这张图有前门、经 M，而你的问题另外条件在 C 上」严格比说 `c_factor` 信息多。

**同一句话的第二份拷贝**：验证器 `verify_identification_pattern` 在 `c_factor` 分支里也写着
`if given: return`，理由逐字相同。两份一致时这个分歧看不见；产出方一改，这份会**安静地
停止搜索它现在该找到的前门**。两处一起改，判据(276)「一句话抄了 N 遍的地方，往上看一层」
这次抓到的是它的续集——**理由抄了两遍，而只有一遍是关于对的东西**。

**改动**：不再因 `given` 扣下前门搜索；`conditioned_on` 本来就无条件加在下面，两个事实并列
说出。`covariate_set`（准则握住的）与 `conditioned_on`（问题问的）**仍是两个键**——它们在
对撞点上读起来一样、意思相反，这正是当初扣下标签所要保护的东西，保留。

**守卫**：新文件 `test_a_front_door_is_a_fact_about_the_graph_not_the_question.py`（7 项）。
反例验过且是决定性的：把 `c_factor` 伪造在带条件的查询上，现在被拒，拒它的**正是那段原先
提前 return 的前门搜索**（报文 “claims the general solution while the effect is identified by
the front door through ['m']”）——旧代码下它会被接受。另加一条读源码的断言，防止
`() if given else` 被写回来。

**基线（本条）**：10442 → **10449**。

**方法论沉淀**：(292)**一个判断被「对的理由」扣下时，先问那个理由说的是哪一层。**
「带条件的查询问的是别的估计量」完全正确，而被它挡住的是一个**关于图**的标签；两句话都对，
只是不在同一层上。找法：看这个函数里**别的分支怎么处理同一个输入**——后门那条不扣，前门这条扣，
不对称本身就是问句。
(293)**保守的默认值也会说谎，而且它说的谎读起来像谦虚。** `c_factor` 不是错的（那确实是引擎
用的解法），它只是把能说的话咽了回去；一个「少说了」的标签和一个「没什么可说」的标签在
envelope 里长得一模一样。

### #481 受控直接效应写好了、导出了、单独测过，而没有任何程序到得了它（2026-08-31）

**现象**（两条，独立）。

一、`themis.estimate` 在识别层自己选出 `strategy: "cde"` 的那条分支上返回
`numeric_end_not_built`。那条分支正是 CDE 存在的理由：自然效应在这张图上不可识别、
受控直接效应可以（`structural_solver` 自己数过——四节点上有效中介的全部标号 DAG 里，
**256 张识别受控效应而不识别自然效应，反过来一张都没有**）。而
`mediation.py:974` 就摆着一个写好、`__all__` 导出、配了 340 行专属测试的
`estimate_cde`。**AST 数了：24 个导出的 `estimate_*` 里，dispatch 提到过 22 个，
没提到的正好是 CDE 那一对，而且没有任何别的 estimation 模块提过它们**——仓库里唯一的
调用方是它自己的测试。

二、它的结局模型是 `Y ~ X + M + Z`，**没有 X:M 交互项**，而它的参数表里偏偏有一个
`mediator_value`。实测：真值 CDE(m\*) = 1 + 2m\* 的一份数据上，m\* 取 0 / 0.5 / 1 / 2，
它四次都返回 **1.586343**——那个命名了估计量的参数是惰性的，账本里也没有任何一行说
模型不带交互。

**根因假设**。一：数值层把 CDE 建成了**自然效应估计的副产品**——两条路径的 CDE 数字都从
「为 NDE/NIE 拟合的那个模型」上读下来（`fw.cde`、`est.cde`），所以那个模型没拟合，
CDE 就没有来源，尽管它自己的调整集已经躺在 `cde.adjustment` 里。不是漏接线：放宽
`strategy != "nde_nie"` 之后，下一行立刻要 `nde_nie.identifiable`、再下一行要它的
`adjustment`，`estimate_mediation` 整个签名（含 `M ~ X + W` 中介模型）都是围着自然效应
建的。**缺的是一个以 CDE 自己的调整集为输入的估计量，不是一个 if 分支。**
二：同一个文件的自然效应那半明写着「交互项必须在，否则 VanderWeele 证明 NDE/NIE 塌成
有偏的 Baron-Kenny」——理由就写在第 234-246 行，而 CDE 那半是另一天写的另一条路径，
两者之间没有任何东西强制这个决定。

**改动**（五层）。估计层：`estimate_cde_curve` 成为原语——一次拟合、一次自助、N 个水平，
设计矩阵由**一个** `_design` 构造（拟合与两次反事实重建共用，交互项不可能被落在旧水平上，
那正是本文件说 statsmodels 犯的错）；`estimate_cde` 变成它 n=1 的包装，15 个既有测试
**逐位不变**——它们的 DGP 没有交互，新项估成 0。答案形状是**曲线不是点**：CDE 按定义就以
「把中介固定在哪」为索引，替读者挑一个水平是包在替他们定政策。接线：`strategy == "cde"`
走新分支，水平由 `support.levels_over_support` 给（二值→样本真有的两个取值，
连续→分位数，并**如实声明**是哪一种）。schema / glossary / analysis_report / verdict.ts
四处同步；`answers.py` 新增 `controlled_direct_curve` 形状——`bind` 当场在 import 时拒绝了
一个没有渲染器的形状，闸口按设计工作。

**验证**：`verify_mediation_numeric` 增第四个块。线性路径上协变量项从
「处理臂减对照臂」的差里**精确抵消**，于是 CDE(m\*) = θ_x + θ_xm·m\*，**两个记录下来的
系数重导整条曲线**；logit 路径不可折叠，判据降到「对比等于它自己那两个标准化风险」——
和本文件自然效应那半给自己的 Monte-Carlo 声明的是同一个诚实上限。反例验过：伪造点被拒，
**连同它自己那两个风险一起改成自洽的伪造也被拒**（因为系数还在）。

**守卫**：新文件 `test_every_estimator_has_a_road_from_the_front_door.py`（5 项）——把 #480
那个只管「测量误差校正」的闸口推广到**估计量**（第四次「闸口的措辞比它的判据窄」）。判据
用 AST 读 dispatch 提到的每一个名字（惰性 import 也算），例外表要求**写出是哪条路代它
回答**，而不是一份光秃秃的白名单。反例验过：把接线摘掉，`estimate_cde_curve` 就落进
未提及集合而例外表里没有它。另加
`test_a_direct_effect_is_read_at_the_level_the_mediator_is_held.py`（18 项），含一致性
（五个水平上误差 < 0.06）与**退化点**（无交互的数据上曲线必须平）。

**明说的取舍**：中介**集**的受控直接效应仍是 `numeric_end_not_built`，理由写在拒绝处——
它的参考值是一个**向量**，而曲线形状按一个数给行编索引；用那个字段装向量要造第二套说法
说同一件事，所以等它自己的形状，不借一个差不多合身的。

**基线（本条）**：10414 → **10442**。

**方法论沉淀**：(288)**「写了、导出了、有专属测试」三项全绿，仍然可以一个用户都到不了。**
#480 是验证器版，这条是估计器版，同一个病：**测试直接调那个函数时，从公开入口到它的整条
路都是盲区。** 可查的判据：`themis.estimate` 的调度模块**提没提过**这个名字——提不到就是
任何输入都到不了，比「可达」弱，但对真正发生过的那种失败是决定性的。
(289)**一个参数如果模型结构上不可能让它改变答案，那它不是默认值是装饰。** 找法：拿一份
该参数真的该改变答案的数据，把它扫一遍，看输出动不动。这条比读签名可靠——签名上
`mediator_value` 看起来完全正常。
(290)**同一个文件里，一半写明了某个建模决定的理由，另一半没做那个决定，就是找洞的地方。**
不需要跨模块比对：两个兄弟估计量共处一室、一个的注释解释了为什么必须带交互项、另一个
不带，这个反差本身就是线索。
(291)**一份按「这个估计器写了吗」记账的覆盖率表，会给一个谁也到不了的能力打勾。**
`COVERAGE_MAP.md` 板块 6 这一行此前写的是「Phase 7.5 CDE numeric ✓」——它没说错任何
一个字，`estimate_cde` 确实存在；错的是**这张表数的是模块不是路**。所以审覆盖率的人读到
勾就走了，而这个洞正好活在勾的背面。判据：**覆盖率的勾必须说清是「写了」还是「走得到」**，
两者在这张表里长得一模一样。

### #480 内核拒收自己产出的那一条校正，而写来审它的模块从没跑过（2026-08-31）

**现象**：`themis.estimate` 产出 `status: numerically_solved`、
`method: differential_regression_calibration` 的答案；同一个答案交给 `themis.verify`——

```text
RuleCheckFailed: numeric_measurement_correction_estimate.method must be one of
  [combined…, exposure…, measurement_error_correction, regression_calibration, simex];
  got 'differential_regression_calibration'
```

对照组（同数据同程序、经典校正）`accepted`。在 `13565aa` 建 worktree 复跑，结果一样——
**既存**，不是这一轮带出来的。这是整个包最核心的那个契约：产出的东西，自己的验证器判为不合法。

**根因假设**：六个产生端共用同一个终结步 `numeric_measurement_correction_estimate`，
而那条规则的方法白名单只有五个。**不是「验证器没写」**——
`verify_differential_error_numeric` 已经写好、导出、并在 `kernel.py:1279` 接线；它只是
永远走不到，因为 `kernel.py:1206` 的通用规则先抛。**闸口的措辞比它的判据窄**，今天第三次
同一形状（#478 的 `declaration_rules`、#479 的 δ 那扇门、这条白名单）。

**为什么没被任何测试抓到**：这一族每条路都有专用数值验证器，而**所有测试都直接调它**
（`audit(ne)` / `verify_differential_error_numeric(envelope)`）。于是测试证明了「算式能被
独立重导」，却完全看不见「内核根本到不了那段重导的代码」。**直接调验证器的测试，结构上
不可能发现这个病。**

**分母**：AST 数了写这个终结步的产生端，6 个；白名单 5 个；缺口正好 1 个，就是全部。

**改动**：方法补进白名单（注释写明它缺席的后果不是「审得松」而是「根本没审」）。

**守卫**：新文件 `test_every_correction_survives_the_kernel_that_dispatches_it.py`（13 项）。
它审的正是直接调验证器审不到的那件事：**一条路真产出的结果，能不能过 `themis.verify`**。
花名册**用 AST 从 dispatch 读**、不列表——第七条路没人给用例的那天它就红，因为「第六条
没有用例」正是这次的来历。每条路另配一条伪造点估计必须被拒的对照，否则「全都接受」的
验证器也会让上面那条全绿。反例验过：把方法从白名单摘掉，六条里**只有**差异性那条变红。

**基线（本条）**：10401 → **10414**。

**方法论沉淀**：(286)**「有专用验证器」和「那个验证器跑过」是两件事，中间隔着调用链。**
判据：**别问「审这件事的代码写了吗」，问「产出方真产出的那个东西，走完整入口能不能过」**。
这次专用验证器写了、导出了、接线了、被测试直接调过——四项全绿，而它一次都没在真实
路径上运行。找法：每个「产出→审计」的配对，都要有一条**从公开入口走完整条链**的用例；
测试直接调内部审计函数时，那条链上游的任何一道闸都是盲区。(287)**一族共用一个终结步
时，那个终结步的白名单就是这一族的花名册，而花名册要从产生端读、不能手列**——手列的
花名册漏一个不会报错，只会安静地把那条路挡在门外。

### #479 δ 也是有人量出来的，而量它的那次是一个回归（2026-08-31）

**现象**：这一族里每一个声明都有一扇门通向「量它的那次研究」——σ²_u 走 χ²、混淆矩阵走
Dirichlet、两条给别人区间定价的路读同一个 χ² 的分位数。**只有 δ 没有**。模块自己在
`_bootstrap` 的 docstring 里写着「δ has no such door yet」，理由也对：它的估计是一个回归
系数不是方差，抽样分布不是 χ²，「用方差那个字段再塞一种分布进来就是一个字段两个意思」。
那句话对的是**字段**，错的是**结论**——答案是第二个声明，不是第一个字段的第二种含义。

**为什么是「残差方差」不是「总方差」**：验证回归报的是斜率和残差方差，正态下这两者
**严格独立**；而总方差跟斜率**不独立**——σ̂²_u = σ̂²_0 + δ̂²·Var(Ỹ) 本身就是 δ̂ 的函数，
把 (δ̂, σ̂²_u) 当独立的抽，区间会被低估，低估量只在 δ=0 时消失（Cov ≈ 2·Var(Ỹ)·δ·se²）。
所以声明那次回归**打印出来的东西**才能让这一对的抽样是精确的——而那也正是调用方手上
真有的数：总方差是他要自己拼出来的。

**改动**：
- `resample.py` 加第三种声明 `DeclaredTracking`（前两种是方差和表，这一种是**回归**）：
  `coefficient` 单给＝精确；连同 `standard_error` / `residual_variance` /
  `validation_df` 一起给＝有研究。三个字段是同一个拟合的输出，所以**要么全给要么全不给**，
  自由度只有一个（一个回归对它的斜率和残差方差报同一个 df，写两遍就会有分歧）。
- 抽样是**一对一起抽**：σ²_0\* ~ σ̂²_0·df/χ²_df，δ\* = δ̂ + se·√(σ²_0\*/σ̂²_0)·Z。边际上
  就是 δ̂ + se·t_df，联合上是这一对自己的分布，而不是两个边际假装成一个。
- `_formula` 从「收 σ²_u」改成 `sigma_u` / `remainder` 二选一，算式统一写在 σ²_0 上——
  两种声明钉住的是不同的那一个，另一个随样本走。副作用是一条真性质：**声明两个独立
  片段的形状自己不可能自相矛盾**，`differential_coefficient_exceeds_the_declared_variance`
  在这条路上根本触发不了，因为矛盾只存在于「总方差和斜率分开钉」的那种声明里。
- 家族里「值 / 值＋测它的研究」一向是**同一个键收两种形状**，所以 δ 也走
  `differential_coefficient` 一个键，没有新开第二个键；路由读系数时走
  `DeclaredTracking.declared_value`，否则一份完整声明会被当成没声明、退回经典校正。
- 两条新拒绝：半份研究（`tracking_study_not_usable`）、研究和总方差同时给
  （`tracking_study_and_a_declared_variance`，同一件事写两遍）。
- 验证器加 `DIFFERENTIAL_COEFFICIENT` 一族，`carried` 从 block 的
  `tracking_standard_error` 推——**和 σ²_u 那条分开两个字段**，因为「δ 按协议固定、σ²_u
  由子研究量」是真实存在的运行，一个字段管两件事会把它读成两个都声明或都没声明。
- 词表补 studied 那条、改 exact 那条；报告在有研究时多说一句（说清它买的是**宽度**：
  点仍读在 δ̂ 上，那次回归系统性偏了点估计照样偏）；schema 补 `tracking_standard_error`。

**守卫**：新文件 `test_the_regression_that_measured_delta_has_its_own_uncertainty.py`
（29 项）。除了三种声明的点一致、区间随 se 单调变宽、闸口两个方向的反例之外，有一条
**直接测建模主张**：抽 20 万次，验 Var(δ\*)=se²·df/(df−2)、E[σ²_0\*]=σ̂²_0·df/(df−2)、
以及标准化后的斜率与它被缩放的那个方差**不相关**——那条独立性正是「该声明残差方差」的
理由，所以它是最该被测的那一条。还有一条测「声明形状不动 rng 流」：裸数和只包一层的
mapping 必须给出逐位相同的区间。

**#478 的闸口自动接管了这一族**：它的管辖范围**从词表读**——凡是被写成两种说法的族。
δ 长出第二种说法的当天就进了管辖，名单里一个字没加。新文件末尾从另一头把这件事钉住。

**基线（本条）**：10368 → **10401**。

**方法论沉淀**：(284)**一句「这里没有门」的注释，先分清它否掉的是「这个字段」还是
「这件事」。** 这条 docstring 说的每一句都对——δ 的分布不是 χ²、同一个字段塞两种分布就是
一个字段两个意思——可结论「所以没有门」并不跟着成立，缺的只是**第二个声明**。判据：
把注释里的理由逐条读成「它排除了什么」，如果排除的全是**某个具体载体**，那这件事没被
排除，只是没被建。(285)**两个数来自同一次研究时，先问它俩独不独立，再决定让调用方声明
哪两个。** 这里调用方本来声明的 (δ, σ²_u) 恰好是**相关**的那一对，而回归打印出来的
(δ, σ²_0) 恰好是**独立**的那一对——换一个参数化，近似就变成了精确，而且调用方还少算
一步。判据：**要重抽的一组量，参数化要选让它们独立的那一组**；做不到再谈近似，并当场
声明。

### #478 区间已经把那次验证研究算进去了，账本却说它没有（2026-08-31）

**现象**：给 `outcome_error` / `berkson` 声明 `validation_df` 之后，撑宽倍数确实按那次验证
研究定了价（`inflation_interval` 读 χ² 分位数，#474 做的）。可同一份报告里，紧挨着的账本
条目说的是反话：

```text
- 量这个方差的那次研究只有 24 个自由度，它的抽样分布里有 25% 落在这份残差装不下的
  方差上——所以这个倍数至少是 1.39，上面没有边。
- [仅影响置信] 结局 y 的测量误差方差 σ²_v 已知且固定：……不传播验证研究自身对 σ²_v 的
  不确定性……（设计侧那条会重抽的路见 design_error_variance_from_a_validation_study_on_）
```

第二行不只是漏说，它**把读者支去另一条通道**，找一个这条通道刚刚已经给过他的东西。而
`query_result.schema.json` 的 `validation_df` 描述里写着这时会声明
`..._from_a_validation_study_on_<变量>`——**全仓没有任何一行代码产出过这个 id**。

**根因假设**：不是「那两行字符串忘了改」。「这个数是怎么定下来的」只有一个知情者——
`DeclaredVariance`，唯一同时握着 `value` 与 `validation_df` 的对象，`premise()` 就是它说出
这件事的方法（#471/#475 建的，五条路在走）。而两个模块的
`_assumptions(outcome, design, instruments)` / `_assumptions(exposure)` **签名里没有这个
对象**——它们声称「前提只取决于设计和列名」。签名里没有的事实，函数体只能写死；写死时
选的永远是同一个，因为那是「还没有验证研究可声明」的年代里唯一存在的那个 id。

往上还有一层：**本该拦住它的闸口存在，但它的措辞把自己的适用范围缩掉了**。
`verifier/declaration_rules.py` 开篇就说「它们是同一个事实写了两遍，值得抓的失败就是两边
不一致」，可它的拒绝句里写死了 `redrew {short} each bootstrap round` 和
`the correction on {column}`。outcome / berkson 既不修正点、也不重抽（读的是分位数），
登记进去会说出假话——所以它们没被登记。不是谁忘了，是**闸口只受理会重抽的修正**。

**改动**：
- 两个 `_assumptions` 收 `DeclaredVariance`，调 `premise("outcome_error_variance", …)` /
  `premise("berkson_scatter_variance", …)`。
- `Declaration.how`（半句模板）拆成 `priced` / `exact` 两句**完整的话**——两种「研究抵达
  区间」的方式没有共同的句子，模板留一个洞就是逼第二族用第一族的词描述自己，而那正是
  把它们挡在门外的形状。四族各自说自己的那两句。
- 新增 `OUTCOME_ERROR_VARIANCE` / `BERKSON_SCATTER_VARIANCE` 两个 `Declaration`；两个
  verifier 把钉死的常量（`_EVERY_DESIGN_DECLARES`、`_VARIANCE`）换成
  `check_declaration_premises`，`carried` 从 block 自己的 `validation_df` 推，**不从前提
  推**：拿生产方的选择当问题，等于用这个选择确认这个选择。
- 词表补 `outcome_error_variance_from_a_validation_study_on_` /
  `berkson_scatter_variance_from_a_validation_study_on_` 两条，并把原来两条
  `known_and_fixed` 的话改成它现在真正的意思——「**本次运行没有声明估出它的那次研究**」，
  指路括号从设计侧改回自己对面那条。schema 不用动：它描述的一直是修好之后的行为。

**守卫**：新文件 `test_a_factor_that_priced_a_study_says_so_on_the_ledger.py`（76 项）。核心
一条把两个面钉成一个事实、且一个字都不引用：
`(se_inflation_lower is not None) == (声明的 id 以 from_a_validation_study 结尾)`。闸口的两个
方向各构造了反例（研究定了价却说取的是精确值 / 没有研究却声称有），两条通道各跑一遍。
真正防复发的是那条**扫描**：**词表里凡是被写成两种说法的族，`themis/estimation` 里不许有
任何模块把它的 id 写成字面量**——判据从词表读、不另立名单，所以某一族长出第二种说法的
当天就自动进入管辖，而不是等谁想起来登记。`differential_coefficient` 现在只有一种说法，
因此不在管辖内——它是**已登记的下一条**（δ 至今没定价，而 δ 进的是校正本身，动的是点）。

**基线（本条）**：10292 → **10368**。

**方法论沉淀**：(282)**刚做完一件事，去查它有没有把「说这件事的那一层」一起改**——功能
测试会全绿，因为功能真的对；错的是账本、schema、报告。找法很机械：grep 那个能力的**反面
id**（这里是 `from_a_validation_study_on_`），看有没有代码产出它；**文档里写着、代码里产
不出来，就是这个病**。(283)**一个闸口没覆盖到某一族，先看它的拒绝句在替谁说话**——
`declaration_rules` 不是漏登记，是它的措辞只描述得了「会重抽的修正」，第二族登记进去会说
出假话。判据：**闸口的措辞比它的判据窄，就是把适用范围写进了措辞**；改措辞（把整句交给
族），不是加分支。

### #477 同一个信封，两个模块各查了一遍，各自拒绝，各说各的话（2026-08-31）

**现象**：`themis/workflow` 的两条回填循环——填参数骨架、补变量框架——一共 19 句拒绝，
15 句在 `raise` 现场，另外 4 句藏在异常类的 `__init__` 里（所以扫 raise 现场的那条规则
根本没看见它们，这一族看上去比实际小四分之一）。全是英文。

**根因假设**：不是「这 19 句还没翻译」。往上看一层：一个 bundle 信封就是 version + kind +
一个由 kind 决定键名的记录列表，两种 bundle 用的是**同一个信封**，可读它的那四步检查
**逐行抄了两份**，只差一个常量和一个键名；`BUNDLE_VERSION = "0.1"` 声明了三处，kernel 里还
直接写了一次字面量。让这份抄写变便宜的东西就在旁边：**两个模块各自定义了一个 `MalformedBundleError`，
同名、同职责**。共享的检查必须抛共享的异常，而没有共享的异常可抛，于是形状只能在各自够得着
自己那个类的地方查。

**为什么是根因不是表象**：「信封是由 `(kind, 记录键名)` 参数化的同一个形状」这件事，仓库**早就知道**
——`kernel` 手里就有这张表，正好是这两个 kind，用来把散记录包成 bundle。缺的从来不是认识，是
一个能落地的位置；而位置之所以落不下，是因为**载体按类抄**（#476 的同一条），两个类就是两份。
只改句子会留下两份一模一样的检查和两个同名的类，下一个信封字段照样加两遍。

**改动**：`themis/workflow/bundle.py` 一个模块拿走整个信封——`VERSION`、一份 `envelope(bundle,
*, kind, key)`、一个 `MalformedBundleError`（`language.Voiced` 的子类）、9 个物种。两个模块各自
留下真正属于自己的那半：补丁 bundle 逐条查 kind / predicate / fields，因为「哪些字段能补」只有它
有词表。另外三个异常类（未知谓词、字段已有别的值、一个字段被回答两次）也变成 `Voiced` 的子类，
**同时保留 `.predicate` / `.field` / `.existing` / `.incoming` / `.unfilled` 这些属性**——要去高亮
那几个下标的调用方读的是属性，从渲染好的句子里再抠出来不算读到。

**六个物种共用一个名词表**：`{where} 必须是{shape}` 这一句覆盖了 6 处，而 shape 是名词不是句子。
这张名词表 #470 已经写过（`extraction_shape`），本次挪成 `themis/shape_words.py`、词表名改叫
`shape`：**没有人对 shape 做穷举匹配**，所以它可以全仓共用；而物种是要 `match` 的，一个通道一份
封闭枚举才是对的 API——`IS_NOT` 这类通用句子在三份物种表里各写一遍，是**穷举匹配的代价，不是遗漏**。

**闸口当场否掉了我自己刚写的一行**：把 `defaulted` 那两处改成物种时，我给 `where` 塞了一句英文
——`the variable_patch for x, fields.defaulted`。债务扫描立刻把 `variable_framing` 从「清零」拉回
「还欠 1」。路径是符号不是散文，改成 `variable_patch[x].fields.defaulted` 才清零。

+61 测试（新文件 20 条：一个类而不是两个、四种信封错误在两种 kind 上给同一个物种、把一种 bundle
递给另一条循环、名词以「词表+token」出境而不是渲染好的字、路径是符号、四个属性还在；外加两份词表
在既有可达性闸口里自动展开）。债务表少两行，名单多三个模块。基线 10231 → **10292**。

- (477) **句子抄了 19 遍的地方，往上看一层，多半有段代码也抄了两遍。** 现场写句子是**最后**一环，
  前面通常是：共享的检查要共享的异常 → 没有共享的异常 → 检查也只能各写一份。
- (477) **同名的两个类是一个信号，不是巧合。** 两处独立写出同一个名字，说明两边都认得那个概念，
  只是没有地方放它；先问「有谁真的分别 catch 过这两个吗」，答案通常是没有。
- (477) **判断「一份表能不能全仓共用」，看有没有人对它做穷举匹配。** 名词进槽位，只被读，共用；
  物种要 `match`，一个通道一份封闭枚举，通用句子重复几遍是这个 API 的定价而不是欠债。
- (477) **闸口该拦的第一个人是刚写完这次改动的自己。** 这次它拦下的正是我把英文散文塞进路径槽位
  的那一行——反例不必是构造的，它可以是刚刚写下的。

### #476 一层拒绝，四十六次由现场决定用哪种语言说（2026-08-31）

**现象**：估计层的六个模块把「你给的东西我用不了」写成了 46 个 f-string——数据契约、
声明域、图搜索、定向编译、定向问答、滞后设计。每一句都在它自己的 `raise` 处成文，
用的是那一行的作者当天在想的语言；调用方想知道**出了什么事**，只有读那个字符串一条路。
`themis/upstream` 的同一条通道在 #470 已经收干净了，这一层原样留着。

**根因假设**：不是「这些句子还没翻译」。承载这种拒绝的东西——异常带着**物种**加**这次
场合的事实**、`str(exc)` 自己渲染——**仓库里已经逐字抄了两份**（`upstream.ExtractionRefusal`
与 `input.SemanticError`，`__init__` 体一字不差）。第二份的 docstring 自己写了为什么要抄：
「一个包里四个异常类，否则就是四份拷贝」。那条理由**在包的边界上并没有失效**，可载体停在
包里，于是给第三个包物种化的代价是第三到第七份拷贝——**把「在现场写句子」变成了便宜的那条路**。

**为什么是根因不是表象**：`discovery.py` 里最主的那个搜索**连异常类都没有**，三处拒绝直接
`raise ValueError("...")`。同一股成本压力再往下一格：既然多一个类要多抄一份载体，那就连类都
不建。它的两个同胞（马尔可夫毯、滞后图）各有自己的通道，只有主搜索没有——**缺的从来不是句子，
是载体**。

**改动**：载体抽进 `themis/language.py::Voiced`（`halve` / `capped` / `assemble` / `occasion`
四个函数按它们唯一说得通的顺序装起来，别处再写就是第五个调用者重新发明这个顺序），三处旧的
都变成它的子类。估计层一份物种词表 `refusal_words.Refuses`：**40 个物种，46 个 raise，
6 个可捕获通道**（新增 `DiscoveryError`——主搜索欠了很久的那个）。一份词表配六个通道，因为
「这个名字不是数据里的一列」是同一句话，毯子撞上它和面板撞上它没有区别，**是哪个模块接住的
是槽位不是物种**。

**闸口挪了家，不是抄了一份**：#470 那条「没有 raise 现场自己写句子」的 AST 规则原本长在
`test_upstream/` 里、只扫那个包的两个模块。#476 让第二个包想要同一条规则——抄一份就是两份
规则。规则搬进了 `test_no_sentence_reaches_the_reader_in_the_wrong_language`：那里本来就按
模块判定「读者拿到的文本还允不允许只有一种语言」，规则在那儿跑一份名单，这两个模块是名单的
头两条。**两条规则不是一条**，而且这次是量出来的：往一个已清零的模块里种两个诱饵，
`f"there is no candidate column to look at here"` 被债务扫描**看见**，`f"pool={len(pool)}"`
**看不见**——功能词不够，`_english_clause_in` 把它当公式。所以扫描判散文、名单判形状，
名单上的模块 raise 处**根本不许接字符串**。名单是显式的而不是「所有没欠债的模块」：验证器那
739 处 `raise` 是写给维护规则的人的审计线索，故意就是字符串。

**债务表少了四行**：`discovery` / `orientation` / `orientation_session` / `lagged_discovery`
四个模块清零删行，`contract` 7 → 1。剩下那一条不是拒绝，是**警告**——样本量低于建议阈值时
往 `warnings: list[str]` 里写的一句中文，是另一条通道。四行注释里反复写着「这里剩下的只有
请求形状那一族」，这次就是把那一族一次切掉。

+132 测试（46 个 raise 各自的物种断言 + 词表 40 个成员在既有可达性闸口里自动展开 + 挪家后的
规则与两条反例：一条证明它会说不，一条量出它比扫描多看见什么）。基线 10100 → **10231**。

- (476) **一族拒绝一直用现场语言说，先去看承载它的东西被抄了几份。** 句子留在现场往往不是
  没人翻译，是**说得体面的那条路更贵**；数一数「要多写一个异常类得多抄多少行」，那个数就是
  真正的阻力。
- (476) **一个包里写对了两次的东西，第二次的注释就是它该往上搬的证据。** 「四个类否则四份
  拷贝」这条理由不会在包的边界上停下来——它已经在第二个包里被重新说了一遍。
- (476) **连异常类都懒得建，是同一股成本压力更深一格的痕迹。** 找漏网的一族时，别只顺着已有
  的异常类找；`raise ValueError("...")` 那几处往往正是**代价最高、所以退让最彻底**的地方。
- (476) **两条闸口不是一条，要用反例量。** 判散文的启发式对短句无能为力——`f"pool={n}"` 里
  一个功能词都没有。给已经清零的模块补一条**没有启发式**的规则，并且**当场种一个诱饵证明
  它确实多看见了**，否则「两条规则」只是一句自我安慰。

### #475 一个矩阵是数出来的，可整条路上只有一句话说它「来自验证研究」（2026-08-31）

**现象**：误分类校正报出的区间，混淆矩阵来自 20000 人一档的验证研究和来自 20 人一档的验证研究，
**页面上一样宽**（实测 0.0649 与 0.0649——后者本该是 0.2340）。而账本那一行写的是
`known_confusion_matrix_from_validation_study`——**它自己就说了「来自验证研究」**，然后把矩阵
当作精确已知的常数,一动不动地穿过每一轮 bootstrap。模块顶上那条取舍写得也很老实：「M 自身的
验证研究不确定性（第二层 bootstrap / 贝叶斯层）留待后续」。

**根因**：不是那句取舍没做，是**没有一个地方可以把那次计数说出来**。声明的形状只有「一个列随机
矩阵」，而验证研究交出来的从来不是一个矩阵，是一张**计数表**——多少个真实状态已知的受试者，各被
记成了哪个状态。列计数除以列总数才是矩阵，所以

    counts[:, j] / n_j  是矩阵的第 j 列,   它的抽样分布是 Dirichlet(counts[:, j])

**方差对 χ² 是什么，矩阵对 Dirichlet 就是什么**，两者都是那次研究本身量到的东西。#471 的三条路
各自找到了不用抽样的载体（#473 读曲线的哪一点、#474 取膨胀倍数的分位数），这一条正相反：
**它本来就在跑 bootstrap**，所以研究可以被最直接的那种载体带走——每一轮重抽矩阵。

**为什么是根因不是表象**：把「假设 id 措辞不当」当根因会得到一次改名。真正缺的是**声明的形状**：
调用者手上有的东西没有地方放。补上形状之后，那五个 id 全部退役不是收尾而是结论——它们既把
`mech` 那一行已经说过的**形状**（单矩阵 / 逐臂 / 逐层）又说了一遍，又把一次**没人携带**的研究
写进了账本。取代它们的是声明自己的前提，和 σ²_u 那一对逐字同构：
`confusion_matrix_known_and_fixed_on_<列>` / `confusion_matrix_from_a_validation_study_on_<列>`。

**声明的形状：计数表替掉矩阵，不是并排放**。`confusion_matrix=` 收到一个映射
`{validation_counts: [[...]]}` 就按列归一得到矩阵——**不接受两个都给**。同一个事实写两遍，总有
一天两份对不上，而那天没有任何东西能回答校正到底用的是哪一个。这条形状零成本地覆盖了全部路径：
结局通道、暴露通道、差异性矩阵组的每一档、以及组合校正的两条通道，一个新参数都没有加。

**实测**（n=6000、每档 600 次重抽；矩阵 Se=0.90 / Sp=0.85）：

| 矩阵怎么声明 | 点估计 | 区间宽度 |
|---|---|---|
| 直接给矩阵 | 0.30422 | 0.0677 |
| 每档数了 20000 人 | 0.30422 | 0.0649 |
| 每档数了 2000 人 | 0.30422 | 0.0652 |
| 每档数了 200 人 | 0.30422 | 0.0824 |
| 每档数了 50 人 | 0.30422 | 0.1293 |
| 每档数了 20 人 | 0.30422 | 0.2340 |

**点估计一个数位都没动**——校正求逆用的仍是那次研究自己的矩阵。两万人一档确实就等于「给矩阵」
（0.0649 vs 0.0677，差在蒙特卡洛噪声里），二十人一档宽 3.5 倍。

**Jeffreys 而不是裸计数**：五十个受试者里一次错记都没出现过，**不等于**这个错记不可能。α=counts
会让那个格子在每一轮都被抽成精确的 0，永远如此——正是这条要消掉的那一个方向上的过度自信。加
1/2 是多项分布的标准无信息先验，也是唯一既让没见过的格子保持可能、又不替它断言一个比率的选择。

**同一份声明在两个键下面是一次抽样，不是两次**：非差异通道是一个矩阵被每一档的键取到。按键抽会
把它变成一个**没人声明过的差异性通道**——每一档用不同的矩阵求逆，区间为一份并不存在的变异而
变宽。所以重抽按**对象同一性**去重，这也正是差异性矩阵组每档一个对象所表达的意思。

**重抽出来的通道不可逆是**一道兜底闸门，不是常见路径。近奇异的重抽**不该**被丢掉：一个 6 人一档、
Se=0.62/Sp=0.60 的通道，实测宽度 27.55 对 0.2311（丢弃 0 次），那个 27.55 就是「这份数据没有把
效应钉住」这句话本身——把这些抽样丢掉恰恰会把区间收窄，扔掉的正是带着消息的那几次。真正落到
`|det| < 1e-6` 的是**声明本身站不住**，走 #472 那套记名丢弃。闸门用一个恒返回平坦列的 rng 构造
反例验过。

**能重算的那一半**：区间是一次 bootstrap，没有任何充分统计量能复现它——这一路的验证契约从
#471 起就是「记录与前提说的是不是同一件事」。但**矩阵是计数表的按列归一，这是恒等式**，所以
验证器多了一件真能独立重算的事：计数表算出来的矩阵必须就是记录下来的那个矩阵。加上前提一致性，
一共五条伪造被逐条拦住。

**五层同步**：`DeclaredMatrix`（resample.py，`DeclaredVariance` 隔壁，同一对 settled 词）→
三个估计量各自的通道声明 + `_inverses` / `_any_measured`，非差异与差异共用一张 `declared_by_level`
→ schema 在**矩阵所在的每一处**多一个 `validation_counts`（block 三处、sufficient_statistics 三处、
三种逐档记录各一处）+ 三个新物种 → 验证器 `declared_variance_rules` 泛化成 `declaration_rules`
（一条规则两个族，差的只是几个名词）+ `_check_validation_tallies` 归一化重算 → 报告与浏览器各多
一行「这个矩阵是数出来的，每个真实状态站着多少人」，没数就还是原来那句。

+35 测试（新文件 29 条 + 既有断言改写）。基线 10065 → **10100**。

- (475) **「来自验证研究」写在假设里，不等于那次研究进了区间。** 判据不是措辞而是形状：调用者
  手上那个东西（一张计数表、一个自由度）有没有地方放；没有地方放，措辞再准也只是一句无人兑现
  的话。
- (475) **一次研究交出来的是它量到的东西，不是它的结论。** 矩阵是计数表的结论；接结论就丢掉了
  「数了多少个」。方差对 χ²、比例对 Dirichlet——形状不同，判据一样：**接那个能推出结论、结论
  推不回来的东西**。
- (475) **同一个事实不要收两遍。** 计数表已经决定了矩阵，所以矩阵不再接受并排声明——两份声明
  总有对不上的一天，而那天没有任何东西能回答用的是哪一份。

### #474 一个精确到两位小数的价格，标的是一份没人问它有多准的方差（2026-08-31）

**现象**：结局测量误差与 Berkson 误差都会报一个「区间比测准时宽 1.20 倍」。同一份数据，σ² 来自
4000 个自由度的验证研究和来自 4 个自由度的验证研究，页面上这个数**一模一样**——而实测下界与上界
分别是 [1.19, 1.21] 和 [1.06, 无上界]。#471 给这两条路留的是拒绝（`validation_df_not_carried_here`），
理由写的是「这里没有可以承载 σ² 不确定性的重抽轮次」。

**根因**：这两条路**不产生区间**，它们给别人的区间**标价**——价格是一个函数

    倍数 = 1 / √(1 − share),   share = σ² / 未解释方差

σ² 的不确定性不需要一个抽样落脚点，它**直接穿过这个函数**。经典重复测量给出 σ̂²·df/σ² ~ χ²_df，
于是真实份额是 `share·df/X`，倍数是 `1/√(1 − share·df/X)`——**在 X 上单调递减**，所以两个端点就是
χ² 的两个分位数原样代进去，`χ²_df.ppf(1−α/2)` 给下界、`χ²_df.ppf(α/2)` 给上界。闭式，一次抽样都不用，
第二个作者只凭 df 和 share 就能重算。

**为什么是根因不是表象**：#471 三条路问的都是同一个问题——「往哪儿放这次重抽」，找不到就拒绝。
SIMEX（#473）的答案是「读曲线的哪一点」，这里的答案是「这个倍数的哪两个分位数」。共同的东西是
**一次研究可以沿任何单调变换传下去，抽样只是其中一种载体**。于是那个物种的三个用户全部找到了别的
载体，`validation_df_not_carried_here` 退役——**一个物种的用户全部消失，是它当初被理解错的证据，
不是一次收尾**。

**实测**（结局通道 share=0.3049 / 倍数 1.1995；暴露通道 share=0.2547 / 倍数 1.1584；95%）：

| df | 结局通道区间 | 被否掉的份额 | Berkson 区间 | 被否掉的份额 |
|---|---|---|---|---|
| 4000 | [1.1885, 1.2116] | 0.000% | [1.1500, 1.1674] | 0.000% |
| 400 | [1.1678, 1.2423] | 0.000% | [1.1343, 1.1902] | 0.000% |
| 100 | [1.1436, 1.3028] | 0.000% | [1.1157, 1.2339] | 0.000% |
| 49 | [1.1271, 1.3782] | 0.000% | [1.1028, 1.2862] | 0.000% |
| 24 | [1.1083, 1.5620] | 0.043% | [1.0881, 1.4044] | 0.008% |
| 9 | [1.0810, **无上界**] | 2.643% | [1.0663, 2.5731] | 1.405% |
| 4 | [1.0597, **无上界**] | 12.516% | [1.0491, **无上界**] | 9.308% |

原来那个点值（1.1995 / 1.1584）在每一行里都在，而且在每一行里都不一样地不完整。

**上界的消失是信号，不是数值溢出**：被否掉的份额是 `χ²_df.cdf(df·share)`——**这份验证研究的抽样
分布里，有多大一块 σ² 大到把整份未解释方差吃光**。那块超过 α/2 时，这份研究本身**不排除「精度代价
无穷大」**，于是没有上界；写一个数上去等于替那次研究说出它没说的话。这也是本次唯一一条读者看不出来的
伪造：[1.06, 7.4] 和 [1.06, ∞) 共享第一个数，其它每个数都一致——所以验证器**单独**拦它。

**一个方法，不是两份代码**：两条通道的份额来路不同（结局通道是 σ²_v/残差，暴露通道是 βx²σ²_u/残差），
份额之后是同一套算术。所以分支挂在**声明**上——`DeclaredVariance.inflation_interval`——而不是挂在
任何一个模块里；σ² 本身根本不进这个式子，份额已经把它带进去了。

**五层同步**：`DeclaredVariance.inflation_interval`（resample.py，顶掉 `refuse_if_not_carried`）→
`assess_berkson_error` / `assess_outcome_error` 各收一个 `ci_level`、各多四个字段 → dispatch 两个
block（顺手把 outcome_error 那份内联字典抽成 `_outcome_error_block`，理由和 `_berkson_block` 早就是
函数的理由一样：复述它的审计必须读产出者写的形状，抄一份形状的测试是产出者少写一个字段也能通过的
测试）→ schema 两处各四个必填键、拒绝枚举少一个物种 → 验证器新模块 `inflation_rules`，一份构造被
两条通道复述 → 报告与浏览器各多一行，**只在真有验证研究时才说**，没有就还是原来那句话。

+32 测试（新文件；含 6 条伪造反例——挪下界、挪上界、事后把研究说大、事后否认有过研究、份额和记录
对不上、df 不是 df——外加单列的那条「研究给不出的上界」）。基线 10035 → **10065**。

- (474) **一个精确到两位小数的数，可能整条路上没有一个地方承认它是估出来的。** 判据是问「这个数是
  哪个量的函数，那个量是量出来的吗」——是，那它就继承那次测量的分布，和它自己算得多准无关。
- (474) **承载一次研究不必靠抽样。** 单调变换直接把分位数带过去，比任何重抽都便宜也更精确；#471 留下
  的三条「承载不了」的路，三次都只是在找错的那种载体。
- (474) **上界的缺席本身是信息。** 该报「至少 1.06，上面没有边」的时候报 1.20，读者看到的是一个更
  精确的数，其实是一句更强的、那份研究没说过的话。

### #473 λ=−1 是读答案的地方，只在 σ̂²_u 恰好等于 σ²_u 的时候（2026-08-31）

**现象**：同一条 SIMEX 曲线，验证研究给出的 σ̂²_u 分别带 400 个和 9 个自由度，页面上的区间宽度
**一模一样**（实测 0.182 与 0.180）。覆盖率却从 70/74 掉到 55/74。#471 把这条路留成「拒绝」
（`validation_df_not_carried_here`），理由是「σ²_u 决定每一档加的噪声，重抽它会挪动整把梯子而不是
梯子上的一次抽样」——这句话是对的，但它说的是**重抽**，不是**研究**。

**根因**：SIMEX 用**声明的** σ̂²_u 造梯子，所以 λ 那一档的总误差方差是 σ² + λσ̂²_u，让它归零的点是
λ* = −σ²/σ̂²_u。**λ = −1 是这个点在「σ̂²_u 就等于 σ²」这个前提下的取值**——标准 SIMEX 一直在读的
那个点，本身就是一句关于验证研究的断言。经典加性误差 + 重复测量正态给出 σ̂²_u·df/σ² ~ χ²_df，于是

    λ* = −σ²/σ̂²_u = −df / X,   X ~ χ²_df

**验证研究的不确定性就是「该在曲线的哪儿读」的不确定性。** 答案的分布是抽样正态
N(θ̂(λ*), τ(−1)) 在这个分布上的混合，区间取它的中央 1−α 区域，df → ∞ 时精确退回原来的 ±z√τ(−1)。

**为什么是根因不是表象**：#471 找的是「往哪儿放这次重抽」，找不到就拒绝。但这个模块**本来就不靠
重抽**——它只有一次模拟外推。缺的从来不是一个抽样的位置，是**看出 λ=−1 是个前提**。文献里到同一处的
路是把 σ̂²_u 当作叠加估计方程里的第二个参数做三明治方差（Carroll, Ruppert, Stefanski & Crainiceanu
2006 第 5 章），那是同一个恒等式的一阶版本；这里读的是精确版本，而且**一次模拟都不用**：混合分布是
闭式的，两个外推式已经拟好了，所以整个区间仍然是第二个作者只凭记录下来的系数就能重算的。

**实测**（线性结局 oracle，有理外推在那里精确；n=800、σ²_u=0.25、每档 300 次重复、每行 80 个样本）：

| df | 固定 σ̂²_u 的覆盖 / 宽度 | 带上研究的覆盖 / 宽度 | 多扣下的区间 |
|---|---|---|---|
| 400 | 70/74 · 0.182 | 72/74 · 0.190 | 0 |
| 200 | 69/74 · 0.181 | 72/74 · 0.199 | 0 |
| 100 | 68/74 · 0.180 | 71/74 · 0.219 | 0 |
| 49 | 68/75 · 0.180 | 73/75 · 0.265 | 0 |
| 24 | 65/75 · 0.180 | 72/75 · 0.386 | 0 |
| 9 | 55/74 · 0.180 | 67/68 · 0.859 | 6 |

固定那一列的宽度**和 df 无关**，这正是缺陷；带上之后覆盖率在整个范围里稳在 96–98%，宽度按研究的大小
从 0.190 拉到 0.859。df≥24 时一个区间都没有多扣。

**当场声明的取舍——τ 停在 λ=−1，读答案的点在动**：τ(λ) 本身是「各档方差均值减重复间方差」这个差的
外推，把它读到本模块唯一担保的那一点之外，实测结果由**它自己拟出来的极点碰巧落在哪儿**支配，而不是
由数据支配：df=24、每档 300 次重复时，「τ 也读在 λ*」这个变体 80 次里扣下 41 个区间、覆盖 36/39，
而「τ 停在 −1」扣下 5 个、覆盖 72/75。停住会在 λ<−1 一侧低估条件方差、在 λ>−1 一侧高估，实测净效果
偏保守。**带走验证研究的是均值的位移，那一项是精确读的。**

**读不到的那一段是个概率，不是网格上的计数**：有理式在 λ=−γ2 处无定义，而 λ* = −df/X 落到那以下
**恰好等价于 X ≤ df/γ2**，于是这个份额是 `χ²_df.cdf(df/γ2)` 的闭式——一个关于调用者的研究和这份数据的
性质，不是关于求积网格的性质（数出来的那个数会随网格动，读者对比两次运行时读到的是分辨率）。而且它
有确切含义：λ* 低于那个极点就是 **σ² 达到或超过暴露自己的观测离散度**，这份数据自己就排除了。所以这个
数是**「你的验证研究里有多大一块，被你的数据否掉了」**。多项式外推没有极点，那里它恒为 0。

份额没到端点该代表的那条尾巴（α/2）时，求积直接架在**可读的那段概率上**（等距概率从 `unreadable`
起算），所以条件化是精确的而不是「网格碰巧躲开了」；到了就没有区间，理由把这个数说出来。**唯一没做的
是给一个数据已经排除的 σ² 编一个值。**

**五层同步**：`mixture_interval` / `off_the_ladder`（simex.py，无种子的 512 点等距概率求积 + 定次数
二分，两者都是**算术**而不是调参——一个停止准则是两个作者可以不一样的地方，一个迭代预算不是）→
`validation_df` / `unreadable_share` 两个键进 schema + `no_interval_because` 第三个物种 →
验证器 `simex_rules` 重述整套构造（闭式份额、条件求积、同样的二分预算），**是「声明」而不是数字决定
走哪条公式**——一条把混合区间说成普通区间的记录会被拿去和它没用的那条公式对质 → 假设账本这一行改成
由 `DeclaredVariance.premise` 分支，`..._from_a_validation_study_on_w` 与 `..._known_and_fixed_on_w`
不再是这里写死的一条 → 报告 / 浏览器各多一行「σ²_u 是量出来的，不是给定的」，只在**真有区间**的时候说。

**#471 那条拒绝还在，只是名单短了一个**：Berkson 与 outcome_error 是给**别人的**区间标价，那里确实
没有任何一轮可以承载 σ² 的不确定性。SIMEX 离开这份名单不是因为它的区间变成了 bootstrap，而是因为
**抽样从来不是承载一次研究的唯一方式**。

+25 测试（新文件 26 条，减去 #471 那份拒绝名单里退役的一个参数；含 6 条伪造反例逐条钉住：挪端点、事后把研究说大、事后否认有过研究、份额和记录对不上、
没有研究却报份额、以及那条最锋利的——**声明了研究却把端点写成 ±z√τ(−1)，正是这一条要拦的东西**）。
基线 10010 → **10035**。

- (473) **一个被所有人当作常数读的位置，可能本身就是一句断言。** λ=−1 不是这个方法的定义，是它在
  「σ̂²=σ²」下的取值；判据是问「这个常数是从哪个等式解出来的，那个等式里有没有别人量出来的东西」。
- (473) **上一次找不到落脚点，可能是在找错的那种落脚点。** #471 找的是「往哪儿放这次重抽」；这里根本
  不需要重抽——**闭式的混合分布 + 已经拟好的曲线**就够了，而且不用付出「区间不可复算」的代价。
- (473) **一个数如果是从自己选的网格上数出来的，它就是关于网格的。** 同一个量能写成闭式就写闭式：
  读者比较两次运行时，读到的必须是数据的差别，不是分辨率的差别。

### #472 一个区间站在多少次抽样上，读者拿不回来（2026-08-31）

**现象**：一个反事实格的 95% 区间是 [0.0009, 0.0344]。它取自 200 次重抽样，其中 **111 次可用、89 次在
所声明的单调性下无解**——44.5% 的答话抽样在反驳这个假设。页面上只有那两个端点。同型的
regression_calibration：σ²_u 的验证研究 df=9 时 1000 次抽样丢掉 30 次（`degenerate_reliability`），区间宽
3.781；df=24 一次不丢，宽 0.799。两个宽度都印出来了，而「宽是因为 σ² 在抖，还是因为只剩 970 次」
没有任何一处说。

**根因**：`for _ in range(ci_bootstrap):` 是**三十五次誊写**的同一段算法。跳过一次失败的重拟合是对的
——区间本来就取在可求值的抽样上，每个循环的注释都这么写着——但**「有几次」这个数没有存放它的
地方**。一个计数器可以加进一个已经存在的循环，而一个循环不写计数器照样能写出来：所以它能在三十五处
同时缺席。

**为什么是根因不是表象**：反事实格**已经发现过**理由是重要的——它自己长出了 `bootstrap_draws_used` /
`bootstrap_draws_infeasible` 两个字段，专报「所声明的单调性被多少次抽样驳回」。那个数走不动，因为它是
**按那个估计量的理由命名的、不是按循环命名的**，于是另外 34 个循环把同一类信息原样扔掉。缺的不是第
36 次誊写，是**循环本身该是个对象**。

**改法是循环而不是计数器**：`Draws` 可迭代，`for _ in draws:` 就是这段算法现在的拼法。`usable()` 写在
循环留下值的那一点，于是计数和留值在同一个分支上决定；反过来数失败会把两者放到不同分支，而后加的
分支只需要记住一个。`unusable(why)` 按 `Refusal` 物种归档：词表封闭且已登记，读者看见是哪个拒绝吃掉了
抽样就知道该改什么，裸计数只告诉他有东西吃掉了。挂不上物种的（线性代数报错、不收敛）归入
`unclassified` 而不是丢掉——**告诉读者丢了 40 次、只给出 12 次的理由，剩下 28 次读起来像没发生过**。
它**故意不收集值**：三十五个循环累积的形状不一样（一个斜率、七个分解项、一整条曲线），一个坚持某种
形状的容器要么只装得下三分之一，要么自己变成一种要学的形状。

**它不数的那一类**：重拟合**成功了**、但某个量在这次抽样上无定义（比例的分母恰好为 0）——那是关于
那个量的事实，不是关于这次抽样的。两者塞进一个数就分不开，而读者的下一步不同：一个说样本逼近边界，
一个说这个比值逼近边界。mediation 的 `np.isfinite` 过滤和 four_way_ratio 的逐键过滤都留在原处，各自
带注释说明为什么。

**AST 闸口**：三十五处的一致性不能靠这一次改对。`test_every_draw_site_in_the_package_says_what_it_discarded`
读源码，对每个含 `resample_indices` 的最内层循环问三件事：迭代的是不是一个由 `Draws(...)` 造出来的名字
（而不是 `range(B)`）、每一条 `continue` 之前在**同一个语句块**里有没有 `unusable(...)`、循环里有没有
`usable()`。嵌套循环里的 `continue` 是那个循环的，闸口不追究。四个反例加两个正例把闸口自己会拒绝
什么逐条钉住——**一个没人见过它拒绝任何东西的闸口，射程是没量过的**。

**FEWEST_DRAWS = 2**：`np.quantile` 对单个值返回那个值，所以「只剩一次可用抽样」的 95% 区间是
**同一个点印了两遍**，而它在报告里读起来像全篇最紧的结果。这是一次**行为改变**，当场声明：
`ci_bootstrap == 1` 从前给一个退化区间，现在给「没有区间」或一条拒绝。`no_usable_resample` 的句子因此
重写（旧句只说得了「一次都没剩」），details 加 `usable`。

**四个面各说各该说的**：报告只说 {requested} 次里可用 {used} 次（整簇抽时加一句抽的是哪一列）；**哪个
物种吃掉了抽样留在信封上**给验证器和读 trail 的 LLM——审计细节归 envelope、读者拿翻译。唯一对读者
有意义的那一次丢弃（所声明的单调性无解）保留它自己的句子。i.i.d. 的块现在**总是**写出来：它的缺席
从前替「按行独立抽的」这句话说话，而**靠沉默说出来的断言只装得下一个事实**，「活下来几次」是第二个。

**一个派生字段，和一次独立重算**：反事实格是**被复制进 `extensions` 的展示副本**，schema 里写着
「生产者把同一个 dict 写进两处」，而 `QueryResult` 根本没有 `numeric_estimate` 字段——站在 extensions 里
的那份格子**够不到**它旁边的 bootstrap 块。于是那个份额升为格子自己的字段
`monotonicity_refuted_share`（`intervals.py` 的先例：当 N 个面各自把同一个事实推导 N 遍，这个事实就该是
一个字段）。分母是**答了话的抽样**（used 加上被它吃掉的），不是 requested——被薄分层吃掉的抽样不是
一张反对单调性的票，算进去只会把反驳率稀释。验证器**重算而不是读**这个份额，所以一个把分母改成
requested 的生产者会被抓住而不是被同意。

**五层同步**：`Draws` + `share_lost_to`（resample.py，与聚类重抽、`DeclaredVariance` 并列成「重抽是在说
什么变了」的第三条轴）→ 35 个循环 → dispatch 25 处接线，外加 4 个自带循环的块（ACR 边际表、四分解
比值、界的行、格子的份额）各写各的记录 → schema 把 `bootstrap` 提成 `$defs/bootstrapDraws` 由 4 处
`$ref`（一个形状一份记录）→ 新验证器模块 `bootstrap_rules` + 公开入口 `themis.verify_bootstrap_draws`
（AUDITS 16→17 行）→ 报告 / explainer / 浏览器三面。**删掉 6 个 schema 键**（`n_rep`、两条纵向路线和
recovered_ate 的 `n_bootstrap`、格子的两个 `bootstrap_draws_*`）：它们各自只装得下这个块的一部分，留着
就是表面上两套惯例。

**为什么公开入口是必要的而不是对称**：`verify()` 要求有推导链，而 `bounds_results` 的每一行**自带
bootstrap 块**——界正是在点识别失败时才挂上来的，所以 verify 恰好对那些没人审计其抽样的结果是休眠的。
`verify_bootstrap_draws` 不声明 `needs_field`，理由和它邻居一样：一份 bootstrap 记录挂在估计、分解表、
界的行里的哪一处都可能，没有哪一个顶层字段等于「有一份」。

**验证器能核的那件事**：重跑一次 percentile bootstrap 要原始数据，那是这里每个数值验证器都停在的
「数据重拟合」天花板。可核的是**记录本身**，而这正是缺陷藏身的地方：丢失加不加得起来（未记账的丢失
读起来和没有丢失一模一样，理由多于丢失则是某次抽样被记了两遍）、理由在不在封闭词表里（词表外的理由
谁也读不到——按物种去查的那些面查出来的是「没有」）、报了区间的地方是不是至少站在两次抽样上。
11 条反例逐条钉住，外加一条正例——**一个对什么都说不的 schema 什么也没说**。

+23 测试（21 条新写 + 2 条既有登记闸口按新 AUDITS 行自动展开）。基线 9987 → **10010**。

- (472) **一段誊写了三十五遍的算法，缺的东西会在三十五处同时缺席。** 判据不是「有没有重复代码」，是
  **「这段算法有没有一个对象」**——没有对象时，任何一件它该记住的事都只能靠三十五次记得。
- (472) **一个已经被发现的事实，若按发现它的那个估计量命名，就走不出那个估计量。** 反事实格的
  「单调性被驳回多少次」正确了很久，只是名字是它自己的；搬家的动作是**按循环重新命名**。
- (472) **展示副本够不到的事实，必须升成字段。** 判据是 schema 里那句「同一个 dict 写进两处」：凡是
  要从旁边推导的，展示副本那一侧一定推不出来。

### #471 σ²_u 也是有人量出来的，量它的那次也会抖（2026-08-30）

**现象**：一个名义 95% 的区间，实测覆盖 **52.5%**。真值 βx=0.8、n=800、σ²_u=0.5 由一个 24 自由度
的验证研究估出，120 次重复里分析者拿到的是 σ̂² 而不是 σ²——这才是真实处境。中位宽度 0.195。
把 σ²_u 按它自己的抽样分布重抽之后：覆盖 **95.8%**，中位宽度 0.826。

**根因**：`error_variance` 的类型是 `float`。一个 float 只装得下**一个点值**，所以「这个数有多准」
在整条管道上**没有落脚点**——spec 没有兄弟键、估计量没有参数、bootstrap 没有分布、验证器没有
可核的东西。缺的是**槽位**，不是计算。

**为什么是根因不是表象**：仓库自己在 `differential_error.py` 写下的立场是**对的**——「重抽一个
没人抽过的量，是在虚构精度」。缺的从来不是那个抽样动作，是**知道那次抽样发生在别处**。
`validation_df` 记的正是这件事，而 `None` 不是「没填的默认值」，是「这里没有分布可抽」这个断言：
`draw()` 对它**不消耗任何随机数**，所以没声明 df 的运行连 rng 流都和从前逐位一致。

**这个抽是精确的，不是近似**：这些估计量本来就假设经典加性误差、重复测量正态，那 σ̂²·df/σ² ~ χ²_df
就成立，于是 σ²* = σ̂²·df/X（X ~ χ²_df）是一次**验证研究的参数化 bootstrap**，和主样本的非参数
bootstrap 并排跑，且两者独立——因为那是两项独立的研究。

**跑起来才发现的第二个根因**：`EffectFacts.measurement_error_map` 是在**组装某条策略的实参**时求
值的——那时候能接住拒绝的那个 handler 还不存在。一个在这里做出的判决只能从异常门离开，而
`themis.estimate` 的调用方读不到那扇门。仓库其实已经为这类站点写过 `_spec_row` 包装器并在它的
docstring 里写明了理由，只是 regression_calibration 那一行当年不需要。改法不是再包一层：
**facts 描述运行，handler 判决运行**——`measurement_error_map` 改成原样交出声明，规范化与拒绝
落到估计量自己的 try 里，refusal 于是带着 `regression_calibration` 的名字进信封。
`outcome_error` 那条同型的 `from_spec` 站点也从 try 外挪进 try 内。

**三处形状的知识收成一处**：`DeclaredVariance.declared_value` 一个函数回答「这份声明里那个数是
多少」，四个估计量的正性守卫都改读它。此前每个守卫各自知道两种形状，**知道两种形状的守卫遇到
第三种时，拒绝的是它没认出的形状、用的却是关于方差的措辞**。

**装不下就说装不下**：SIMEX 的区间是 Stefanski-Cook 方差外推、Berkson 与 outcome_error 是给
**别人的**区间标价——三条路都没有哪一轮可以顺便重抽 σ²。它们现在**拒绝**而不是静默忽略
（`validation_df_not_carried_here`，与上一层 `Malformed.TREATMENT_BRIDGE_UNUSED` 同一条判断：
一条算术从不查阅的声明，读起来像是答案有它并没有的保护）。

**五层同步**：`DeclaredVariance`（resample.py，与聚类重抽并列成「重抽是在说什么变了」的第二条轴）
+ 2 个新拒绝物种（含中英句子）+ 2 个产物块的 `validation_df` 进 schema + 新验证器模块
`declared_variance_rules`（两个会重抽的校正共用一条规则）+ 假设账本新行。账本这一行是
**identification 层而不是 confidence 层**：设计侧的 σ²_u 进入校正本身，声明了 df 也照样进，所以它
错了错的仍是点估计——为「多说了一句自己的不确定性」把前提降级，正好降反了。

**验证器能核的那件事**：点估计两种声明下**一模一样**（实测逐位相等），所以没有任何充分统计量能
把两种运行分开——区间才是分开它们的东西，而 bootstrap 重放不出来。于是剩下唯一可核的，是
**块里记的和前提里说的是不是同一个故事**：`validation_df` 在与不在，必须和
`design_error_variance_{from_a_validation_study,known_and_fixed}_on_<v>` 对得上。页面上两种区间是
**同样两个数字**，读者除了这条前提没有别的把手。5 个反例逐条钉住（df 掉了前提没掉、前提降级 df
没降、两条前提同时声明、一条都不声明、给一个没方差的列记 df）。

**当场声明的取舍**：bootstrap 里让校正退化的抽样是**跳过**的，这是仓库 ~15 个估计量共同的成文
惯例（「区间取在可求值的抽样上」）。实测丢弃率：df≥49 是 0.0%、df=24 是 0.1%、df=9 是 3.8%
（λ=0.65）。df=24 实测覆盖 95.8%，所以这个截断当下没有把区间弄窄到失覆盖。但**这里被跳过的含义
变了**：过去它是数据的偶然，现在它是调用者自己那个 df 的函数，而「你的验证研究小到有 3.8% 的
σ² 取值让校正无定义」正是这个项目自称要报的那种数据缺口。没做，因为**只给这一个估计量加丢弃计数
就是一张表面上两套惯例**（#469 拒绝过同一件事），而给 15 个都加是另一刀。放这里当独立前沿。

**顺手抓到的**：`test_an_error_that_tracks_the_outcome_has_its_own_reliability` 里那个自称「dispatch
写的 numeric_estimate」的 fixture 少了 `assumptions`——新规则一跑就抓到。**一份宣称复刻产物的
fixture，短一个字段就是能通过产物过不了的审计。**

**这一刀把三句话变成了假话**：`regression_calibration` 的 docstring（「Held fixed across
bootstraps」）、differential 的 `differential_coefficient` schema 描述（「held FIXED … exactly as
sigma^2_u is」）、simex 的 `error_variance` 描述（「the same external input regression calibration
takes」）。三处都已改。**没有任何测试守着这三句**——闸口守枚举、守词表、守登记，守不住散文。
所以改一个字段的语义时，得主动 grep 这个字段名的所有文字描述，那是变假话的地方。

+39 测试。另有 6 条不是写出来的：既有登记闸口按 2 个新物种和 1 个新验证器模块自动展开
（每种语言渲染一遍拒绝句、每个物种得有人引用、新模块不得把词表当身份用）——**登记闸口在一个
功能只落地一半的那天就会响**，这 6 条是它们在响。基线 9942 → **9987**。

- (471) **缺的是槽位，不是计算。** 一个字段的类型只装得下一个点值时，「这个数有多准」不是没写，
  是**没地方写**——沿着类型往下游走一遍：spec、参数、抽样、验证器，四处都是空的。
- (471) **检查写在哪一刻，决定了有没有人读得到它。** 同一个检查，写在实参求值处是一个异常，
  写在 handler 里是一条信封上的拒绝。判断一条新守卫「够不够」，得看它抛出的东西走哪扇门。
- (471) **多说一句自己的不确定性，不该换来一个更轻的前提。** 前提的层级是「它错了什么会塌」，
  不是「这句话听起来像在讲区间还是讲识别」。

### #470 前门拒绝你的时候，是在跟你说话（2026-08-30）

**现象**：`themis/upstream` 是给 LLM 用的那一层——agent 递进来一个 extraction dict，要么拿回一个
程序，要么拿回一句「你递的东西哪里不对」。**那 49 句全是站点上的 f-string，全是英文。**

**根因**：`ExtractionError` / `ExtractionShapeError` / `MergeConflictError` / `PredicateLinkError`
四个异常的第一个参数是一个**成品字符串**，所以每个 raise 站点都是那句话的作者，而作者用自己
正在想的语言写。

**为什么是根因不是表象**：跟 #467 / #469 同一个根因第七次出现。

**让这一刀变小的那个发现**：**场合早就抽出来了，句子没有。** 这里每个 helper 都收一个 `what`
（`extraction.variables[3].predicate`）再插值——**路径从模块写下来那天起就是一个槽**，只有措辞
一直焊在站点上。所以 49 个站点其实是 **16 个物种**：站点之间的差别绝大多数是路径，而路径从来
不是句子。

**两张表而不是一张**：16 个物种里有 7 个是「{where} 必须是一个 dict / 列表 / 非空字符串 / …」，
这是**一个句子加一个洞**，不是七个句子。而「一个 token 填不进洞」正是 `language.Word` 存在的
理由——把 `dict` 直接 str 进中文句子就是往中文里塞英文 token。所以 `Shape`（7 个词）+
`Refuses`（17 个物种）。写成七个句子的话，将来多检查一种形状就是多一句话乘两种语言。

**顺手消掉的重复**：`program_ast must be a dict` + `statements must be a list` 这对守卫在五个入口
逐字重复了五遍（十个 raise）。抽成 `_require_program_ast` 之后是两个。**一个守卫抄五份，在其中
一份被改的那天就是五个守卫**；而且那也是五个站点各自独立决定同一句拒绝该怎么措辞。

**闸口读源码而不读债务表**：新测试用 AST 扫「`raise X("...")` 有没有字面量第一参数」。它当场抓到
两处债务表**从来没数进去过**的 `raise ValueError("max_candidates must be >= 1")`——一个调用方能
自己修的越界参数，是拒绝不是断言（`Malformed` 的说明早就划过这条线：「a dispatch table that meets
a kind it has no branch for is asserting, not refusing」）。**跑起来的测试只能覆盖被走到的分支，
读源码的闸口不挑分支。**

**测试断言换轴**：9 处测试原本 `match="must be a dict"` / `"duplicate"` / `"self-loop"`，改成断言
`.species`。钉英文措辞等于钉住一个读者的渲染，而那正是这个形状要消掉的东西；还留着 `match=` 的
几处钉的是**路径**，因为路径在两种语言里一模一样。

**五层同步**：2 个产生端 + 1 个新词表模块 + `reader_words.GLOSSED` 两行 +
`test_vocabulary_reach` 两行 + `__init__` 的导出与说明。语言债 155 → **106**，
`themis/upstream` 整包归零。+19 测试，含真反例（源码闸口喂一个自己写句子的假模块）。

基线 9836 → **9942**。

- (470) **一个模块已经把「场合」抽成参数，说明它离物种表只差一步。** 判断这类活的工作量，
  先看站点之间到底差什么：差路径 ≠ 差句子。49 → 16 不是压缩，是本来就只有 16 句话。
- (470) **闸口读源码，不读那份统计。** 语言债表是扫出来的，扫描器会漏（#469 漏了一整条 note，
  这里漏了两处 raise）。一条规则如果只对着它自己那份统计成立，那它守的是统计不是规则。

### #469 一个产物说自己的那句话，是说给某个人听的（2026-08-30）

**现象**：#467 开了 `statement.schema.json` 这扇门，并点名还有四个独立产物的 `note` 欠着。
其中一条长这样（实跑）：

```
Meek propagation: 2 data-oriented + 0 constraint + 0 propagated edges directed,
0 still undetermined；1 constraint与数据冲突
```

**一个字符串，前半句英文、后半句中文，中间是一个中文分号。** 两种读者，谁都拿不到一句完整
的话。

**根因**：字段类型是 `str`，它只装得下一个**成品**字符串。前半句在「算完计数」的地方写成，
后半句在「数完冲突」的地方 `+=` 上去——**粘合处正是第二个作者混进来的地方**，而第二个作者
没有地方放自己的语言，只能接着往同一个成品串上拼。这跟 #467 拆掉的那条「答案若走运，还能
顺带定下 …」从句是同一个形状。

**为什么是根因不是表象**：把这四条 note 翻一遍，下一个往 note 上追加子句的人还会照旧写，
因为字段还是 `str`。同一根因这仓库已经修过六次。

**结构性修改**：四个 `language.Word` 词表（`orientation_propagation_says` 6 员 /
`orientation_session_says` 4 员 / `markov_blanket_says` 2 员 / `lagged_discovery_says` 4 员），
`note: str` → `note: tuple[Statement, ...]`，四份 schema 的 `note` 改成
`$ref statement.schema.json`。**并且 `notears_fit` 的两处 `$ref` 从 `query_result` 改指共享
文件**——它形状对、路径错：一个独立产物穿过信封的文档去拿形状，正是当初另外四个够不着这个
形状的那种耦合，照着它写等于把病复制一遍。

**删掉的和留下的**：`status={status}` 从 session 的 note 里去掉了——它是旁边一个带 enum 的
字段，重述一遍是重述。但 `orientation_session_status` 的 `no_gloss` 理由白纸黑字写着
「**A person gets the session's `note`, which says the counts and the status in a sentence**」，
所以状态不能只是消失：它变成**三个成员**，说的是「这个状态意味着下一步该干什么」——`blocked`
和 `open` 都留着未定向的边，区别在于**再问一轮有没有用**，那是一句话不是一个词。同理
`markov_blanket_method` / `_ci_test` / `lagged_discovery_method` / `_ci_test` 四个 enum 之所以
被允许没有 gloss，理由正是「note 会用**published name** 说出来」，所以方法名和检验名一个都
没丢；而 published name 是语言中立的（跟论文标题同理），所以它们当**事实**走，不需要新词表。

**一处必须查清才敢动的判断**：句号到底归成员还是归渲染面？仓库里两种证据都有。查到底的
结论是**两者都对，分界线是 `listed` 和 `spoken` 这两扇已有的门**：`discovery_note` 的成员是
被塞进另一个句子的**槽**里当列表项的（gap 报告把每条违规放进一个洞，用顿号连），给它们加句号
会让句号落在逗号分隔的列表中间；而 `note` 数组里的是**独立整句**，`spoken` 只提供句子之间的
**间隔**、不提供**句末标记**（`FULL_STOP` 自己的说明就是这么写的），不自带标记就会连成一片。
所以本次 16 个成员全部自带句末标记，而 `discovery_note` 一个字没动——两条相反的闸口各有
自己的反例。

**一条不能动的字段**：`answer.note` / `sourceTrailEntry.note` 保持 `str`。那是**回答者自己
写的**文字，语言是他们的，这个包不能替别人选词。「把所有字符串都变成 statement」是错的规则，
对的分界是**这句话是谁写的**——两处 schema 补上了说明，免得下一个人顺手转掉。

**顺带**：语言债 159 → **155**；这四个模块的 note 通道全清，剩下的 27 条**全部**是请求形状
错误一族（#470 的料）。另外记一笔**分母的反向错误**：session 的 note 从头到尾没被债务表数
进去过，因为 `5 answer(s) ingested → 3 oriented, 2 undetermined; status=blocked` 里**一个虚词
都没有**，`_english_clause_in` 把它当成了公式。债务表会漏，不只会多。

**五层同步**：4 个产生端 + 5 份 schema + `reader_words.GLOSSED` 四行 +
`test_vocabulary_reach` 四行 + 验证器不动（它重算的是数字，一个字都不读 note）。+33 测试，
含三组真反例，跑的都是闸口自己那个函数：漏一种语言、两种语言的洞不一致、该收尾的没收尾／
不该收尾的收了尾。

基线 9729 → **9836**。

- (469) **一个字段的类型，就是它能容纳几个作者。** `str` 只装得下一个成品，所以第二个往上
  追加的人必然接着前一个的语言写下去——半英半中的那句话不是谁粗心，是字段形状的必然产物。
- (469) **删一句重述之前，先查有没有别人的「我不用说」是建立在它身上的。** 四个 enum 免 gloss
  的理由都写着「note 会说」，这些理由是**契约**：把 note 里的方法名删掉，就等于同时删掉了
  四个 enum 的读者，而闸口不会替你发现。
- (469) **同一个形状在两处出现，不必然是同一条规则。** 句号归谁，答案取决于这条 statement
  是**整句**还是**列表项**——判据是它走哪扇门（`spoken` / `listed`），不是它长什么样。

### #467 工具问人的那个问题，只用一种语言问（2026-08-30）

**现象**：交互式等价类定边会话——Themis 直接问人「是 X 导致 Y，还是 Y 导致 X？」，以及十几种
「数据说这样、你断言那样，信哪个？」的冲突裁决话术——**十八句全部只有中文**。一个不读中文的
读者，在这个建了四个模块的功能上，一句话都拿不到。

**根因**：不是翻译没做。`OrientationQuestion.prompt` 类型是 `str`，而产物自己的 schema 把它
描述成 **"A phrasing for a human. Rendering, not data"**——**信封携带的是渲染好的字符串，而
渲染发生在还不知道读者是谁的地方**。`_conflict_prompt` 是一串十二分支的 f-string，每个分支
既是作者又是渲染器。语言债表里 `discovery.py` 那条注解逐字记过同一个判断：
「the missing translations were never missing work, they were a **missing slot**」。

**为什么是根因不是表象**：把这十八句翻一遍，下一个加分支的人还是会在站点写成品字符串，
因为**字段类型就是 `str`，没有别的地方可写**。同一个根因已经被修过五次
（`semantic_validator` 26→28→29→归零、`bounds.py` 8→0、`proximal_identify` 9→11→0、
`sample_size` 7→6→0、`missing_data` 4→0），每一次的修法都一样：给它一个槽。

**结构性修改**：十二个分支本来就是一张物种表——每个分支读的都是 propagation 产物拥有的
`reason`，选物种是它开始写散文之前做的全部事情。于是 `Asks`（17 个成员）+ `Says`（1 个）
两个 `language.Word` 词表，双语句子写在成员上、名字做洞；`prompt` → `asks`、`note` → `says`，
两个字段都变成 statement；`asked(q, lang)` 是读者的门。**顺带消掉一处「站点粘出来的从句」**：
「答案若走运，还能顺带定下 …」原本是在站点拼上去的尾巴，现在是两个物种——粘合处正是第二个
作者混进来的地方，而这个文件的测试名字（「一个没有答案的问题不是问题」）说的就是那条从句
曾经以空对象结尾。

**这一刀的门开在哪**：新建 `themis/schemas/statement.schema.json`。信封从 #395 起就带
statement，**而六个独立产物没有**——因为那个形状写在 `query_result.schema.json` 自己的
`$defs` 里，别的产物够不着。语言债表里那条关于独立产物的注解写着「**What is owed is one cut
across that channel**」，这就是那一刀的门。**并且 query_result 现在引用它而不是自己再写一份**
——不是我主动做的选择，是仓库的 `test_no_shape_is_recorded_in_two_documents` 当场拒绝了
「先留两份、写个测试钉住相等」这个我准备声明的取舍。闸口是对的：一份形状抄两遍，改其中一遍
的那天就是两份形状。

**顺手修掉一笔假账**：`framing_check._CONTINUOUS_MEASUREMENT_CUES` 里的「岁 / 毫米 / 浓度」
被语言闸口算成 10 条欠翻译，而它是**匹配用的线索词元组**——同一个元组里 `mm`、`kg` 就在旁边。
匹配器的语言由**调用者可能怎么写**决定，不由读者决定；「给毫米补个翻译」要的东西两格之外就有。
按既有形制归到 `Wrote.QUOTED`，理由指向一层之外早已这么判过的 `_MEASUREMENT_ERROR_PATTERNS`
（「needles, not sentences」）。语言债 187 → **159**（-18 真修，-10 假账）。

**五层同步**：产物 + `statement.schema.json` + 产物 schema（`asks`/`says` 两个 `$ref`）+
`reader_words.GLOSSED` 两行（无 browser_table：四个 orientation 产物是 Python/MCP 面，
浏览器不显示它们，这是关于「在哪读」的陈述而不是遗漏）+ `test_vocabulary_reach` 两行 +
验证器不动（它一个字都不读 `prompt`，重算的是数字）。+15 测试，含真反例：
完整性检查与「两种语言的洞要一样」各喂一个该被拒的成员，**跑的是闸口自己那个函数**，
不是在旁边重演一遍算术。

**还欠着的**：另外五个独立产物的 `note`（`orientation_session` ×3、
`orientation_propagation`、`markov_blanket`、`lagged_discovery`、`notears_fit`）走同一扇门，
本次没做。请求形状错误那一族（`narrative_merge` 32 / `program_builder` 17 /
`variable_framing` 10 / orientation 家族 11，共约 70 条）是**另一条**已有判例的刀
（`semantic_validator` 那次），也没做。

基线 9660 → **9729**（+15 自写；其余是既有闸口按成员/按文档参数化撞上 18 个新成员与 1 个新
契约文档——光「一个词按读者的语言渲染」这一条就是 18×2；−4 是随形状搬走的那四行块内声明）。

- (467) **一句「这个字段是给人看的措辞」写在 schema 里，是在承认没人管它的语言。** 把渲染
  好的字符串放上信封，等于让产生端替读者选了语言；而字段类型是 `str` 时，站点**没有别的
  选择**——所以这类缺陷不是靠自律避免的，是靠有没有槽。
- (467) **一个准备声明的取舍，先看仓库有没有闸口已经拒绝过它。** 我打算「两份形状 + 一个
  相等测试」并写进说明，闸口直接说不。**声明取舍不能替代先问「这真是必要的取舍吗」。**

### #466 出路挂在「哪个渠道修」上，而不是挂在「为什么修不了」上（2026-08-30）

**现象**：`x→y`、选择节点作用在 `y` 上、问目标人群的效应。kernel 正确拒答，`answer_tier`
为 `none`，gap 的 `describes` 里明写 **`transport_not_identifiable`**。而同一个 gap 给读者的
三条出路是「测混杂再识别 / 随机化绕过后门 / 找工具变量」——**失败的是可迁移性，不是后门**。
第三条对 transport 直接是错的（源人群里的工具变量识别的是源人群的效应，正是刚被拒的那个）；
第二条不说在哪个人群随机化，照做还是同一个不可迁移的答案。**读者照着做，会去做一个答不了
他问题的研究。** 这条 2026-07-29 就被登记过「本次不做」。

**根因**：`alternative_paths` 挂在 `GapKind` 上，而 kind 是**粗的那个名字**——`gaps.py`
开篇自己实测过并写下了这件事：`unidentifiable_no_admissible_set` 覆盖十个不同的发现，
`missing_structural_input` 九个，`missing_assumption` 十一个，「kind 在做两份工作，`Need`
是细的那个名字，kind 是从它读出来的」。**出路是关于「为什么失败」的事实，而 kind 恰恰是
把这个区别抹掉的那一层。**

**三个症状，一个出口，两个方向同时错**。三个最宽的 kind 各有一个渲染器，两个**注意到了
问题并选择闭嘴**，各自把理由写进了自己的 docstring——`_species_structural_input`：「these
range too widely for one line of advice to fit them all」；`_species_missing_assumption`：
「one sentence of generic advice would be wrong for most of them」。第三个没注意到，**把
建议发了出去**。两句话对 kind 都是真的，对它底下任何一个物种都是假的。第三个症状是这个
病灶**已经被打过一次补丁**：`_rewrite_iv_aware_alternatives` 是个事后修复 pass，专门在 IV
界已经算出时把那条自相矛盾的「去找工具变量」换掉。而最干净的见证是 `no_c_factor_witness`
——它自己的物种句以「and no instrument route is available either」结尾，同一个 gap 的路线表
说「find an instrument」：**一个 gap 在相邻两个字段里自相矛盾**。

**结构性修改**：`gaps.ESCAPES: dict[Need, tuple[Route, ...]]`——出路按**物种**声明，
`_species_unidentifiable` / `_species_structural_input` / `_species_missing_assumption`
三个渲染器从 item 已经携带的物种读，不再写死。放在 `Route` 之后而不是做成 `Need` 的第四个
字段，是照 `SAYS` 已经画好的那条线：一个需要后面才定义的类型的属性，本模块的做法是键在
枚举上的表，不是把 420 行枚举搬家。

**空必须说话**：`NO_SPECIES_ESCAPE: dict[Need, str]` 收另一半，`_bind_escapes()` 在 import
期钉住两张表**并集完备、交集为空、且 ESCAPES 里不许出现空元组**——一个什么都不说的空，正是
这张表要终结的那个状态。两张表上的理由说的是**两件不同的事**：这个原因没有任何东西能修
（`transport_sources_disagree` 是证伪，要撤回的是读者自己的声明），或者它的出路**要念出这个
程序里的变量名**因而在站点构造（反馈环那两条）。后者不是缺席——这条线和 `SAYS` 在「句子」与
「填空」之间画的是同一条。

**十九个物种拿到了出路，八条路线是新写的，九条是早就写好但从这里够不着的**：
`accept_the_source_ate`（写给 transport 的数据请求通道）、`find_a_matched_rct`、
`drop_the_other_layer`（逐字写给 joint+mediation 那个程序）、`fall_back_to_the_total_effect`、
`fix_the_data_to_match_the_declaration` / `fix_the_declaration_to_match_the_data`（一对矛盾
的两个分支，正是声明与样本互相反驳时该说的话）、`find_a_stronger_instrument`。**它们不是缺，
是从粗名字底下够不着。**

**顺手掀出一个真的行为回归，而且不是测试过时**：`admg_effect_reachable_only_by_instrument`
拿到的是新路线 `take_the_instrument_route_the_graph_offers`（图里已经有一个合格的变量，不用
再去找），于是 `_rewrite_iv_aware_alternatives` **失灵**——它读的是 `find_an_instrument` 这
一个名字。修的是 pass 不是测试：新增 `gaps.INSTRUMENT_CHANNEL` 这个具名 frozenset，读它而不
读单个名字。**读者被送到工具变量通道时用的是哪个名字，是物种的事；一旦真有一个区间从工具变量
里出来了、下一步该干什么，是这次运行的事**——第二件事不该知道第一件事选了哪个名字。

**实测**（同一个程序，改前 / 改后）：`measure_the_confounder_and_reidentify,
run_an_rct_past_the_backdoor, find_an_instrument` → `measure_what_differs_between_the_
populations, run_the_study_in_the_target_population, accept_the_source_ate`。弓形弧
（`admg_effect_not_identifiable`）那三条**逐字不变**——本次的断言是关于**另外九个**物种的：
它们一直在被发这一个物种的答案。

**五层同步**：`gaps.py`（表+闸口+`escapes()`+`INSTRUMENT_CHANNEL`）· schema route 枚举 +8 ·
`kernelWords.generated.ts` 重生成（浏览器端本来就走 `gapWent` 通用渲染，无硬编码清单）·
`gap_to_action.md` 两处按「写原则不写枚举」改写（Q1 那句「adding measured variables, an RCT,
a valid IV」本身就是同一个病灶的 prompt 版）· 语言闸口按既有形制补一条 `Wrote.UNREAD` 声明。
+23 测试（含反例：抽掉一个物种 / 同时上两张表 / 空元组，三种都必须 import 期红）。
基线 9604 → **9660**（+23 自写；+32 是四个按 `sorted(Route)` 参数化的既有闸口 × 8 条新路线；
+1 是语言闸口按 `sorted(ALLOWED_SLOTS)` 参数化，那条新声明自己也要被查「还在被用」）。

**明确没做的一半**：这次只动**物种能独立settle 的**出路。同一次扫描里还翻出两笔账，都留着：
(1) `duplicate_treatment_atom` 这种**程序缺陷**的 gap 上会被盖一条
`bounds_already_computed`——`do(a=T, a=F)` 是一个写坏的查询，读者被告知「区间已经算好了」，
这是同族的下一个对象（occasion 驱动，不在本刀的刀口上）；(2) 六个测量误差估计器把 σ²_u / δ /
混淆矩阵一律当作**零抽样误差的已知常数**，验证研究自身的不确定性一处都不传播，区间因此
**系统性偏窄且只往一个方向偏**。

- (466) **一条覆盖 N 个原因的建议，两种失败方式看起来一点都不像，其实是同一个。** 说错话
  和闭嘴都是「这一层分不出细节」的表现，而闭嘴那两个还会把理由写进 docstring，读起来像深思
  熟虑的克制。**判据是问它闭嘴的理由适用于哪一层**：如果那句话对 kind 是真的、对每个物种
  都是假的，它就不是克制，是挂错了地方。
- (466) **产生端已经知道的事，别让报告端再猜一次。** 这个 gap 从来没有和自己不一致过——
  物种一直在信封上。缺的不是知识，是**从它到建议的那条路**。
- (466) **一个物种的句子说「没有 X」，就不能在隔壁字段发 X。** 这条现在是一个按 `says` 文本
  扫的通用测试，而不是一份要跟着走的名单。

### #465 「非差异」不是一句免责声明，是一条会把答案送到别处的前提（2026-08-30）

**现象**：regression calibration 把「误差非差异」记成一条 scope 说明，像撤掉它只是让
答案变粗糙。不是。差异性误差**同时**抬高观测的暴露方差**和**暴露-结局协方差，而那条
矩量校正只除掉前者。实测真值 0.8、把**正确的总方差**交给它（它有权要的那个量）：

| δ | 朴素 | regression calibration | 本条 |
|---|---|---|---|
| −0.4 | 0.12761 | **0.39820** | 0.80013 |
| −0.2 | 0.37858 | 0.69340 | 0.79985 |
| 0.0 | 0.53328 | 0.79957 | 0.79957 |
| +0.3 | 0.60742 | 0.87270 | 0.79914 |
| +0.5 | 0.59798 | **0.89978** | 0.79886 |

一边差 0.40、另一边差 0.10，**分居真值两侧**——所以这不是「校正得不够」，没有任何固定
的补正能把那一列拉回来。

**根因：这一族里所有的校正都建在一条「误差只进方差」的图景上，而差异性误差进两处。**
把调整集从两边偏出去之后（tilde=对 Z 的残差），模型是

    Ỹ = βx·X̃* + ẽ ,   W̃ = X̃* + U ,   U = δ·Ỹ + f ,   f ⟂ (X̃*, ẽ)

于是观测协方差 `C = βx·S + δ·B` 里有 δ·B 一份根本不是效应。矩量校正只做「除以可靠比」
那一步，等于**默认分子是干净的**——而分子恰恰是被污染的那一处。闭式要先把它减掉：

    σ²_0 = σ²_u − δ²·B      S = A − σ²_u + 2δ²·B − 2δ·C      βx = (C − δ·B)/S

**为什么是根因不是表象**：

- **δ=0 时这三条精确退回 regression calibration**（同一份样本上差 **4.4e-15**）。所以它
  不是旁边新起的一个方法，是同一条校正撤掉一条前提之后的样子；也所以**已经在仓里跑了
  几个月的那个模块就是这条的 oracle**，不必自己重述一遍代数来自证。
- **δ 只能从外部来，而这不是缺陷是事实。** δ 和 βx 进入观测协方差的方式完全一样，样本
  里没有任何东西能把「效应」和「误差」这两份分开。所以它跟 σ²_u 一样是声明，跟 σ²_u
  一样在 bootstrap 里**不重抽**——重抽一个没人抽过的东西，只会把区间撑宽得像是有根据。
- **调整后能当差异轴的只剩结局这一个。** 误差若随一个**被调整的**协变量走，把那列从两边
  偏出去之后 `W̃ = X̃* + f̃`——就是经典误差。所以那种情形不是本条的小号版本，而是**另一行
  的答案**：拒绝，并告诉调用者去用普通校正、配上偏掉那列之后的残差方差。既不是缩小的
  范围，也不是沉默。

**做了什么**

1. **`themis/estimation/differential_error.py`**：闭式 + bootstrap。`error_variance` 仍是
   `Var(W−X*)` **全量**——这一族里它一直是这个意思，不因为多了一条声明就改口；随结局走
   的那一份由 δ²·B 推出来，不让调用者报第二遍。
2. **两道闸，两个物种，因为读者的下一步不同**：`σ²_0 ≤ 0` 是**两条声明彼此矛盾**，在读
   数据之前就定了；`S ≤ 0` 是**声明和这份样本矛盾**。合成一个会让「改 δ」和「换数据」
   读起来一样。
3. **差异轴要判**：结局→算；被调整的协变量→拒并给出路；其余→拒并说这是缺口。
4. **Berkson + 差异同时声明→拒，不替调用者挑一条**。Berkson 的内容就是误差与记录下来的
   名义值独立，而随结局走的误差做不到——结局取决于真值，真值就是名义值加这个误差。
5. **验证器 `verify_differential_error_numeric` 走第二条转写**：生产端用 Schur 补拿
   (A, B, C)，验证端把 (W, Z…, Y) 的联合协方差求逆、取 (W, Y) 那个 2×2 精度子块再求逆
   ——同一个恒等式，没有一行共享代码。专门钉住那个**手算读者抓不到的伪造**：保持可靠比和
   各方差都诚实，只跳过协方差那一步，点就变成 naive/λ——正是一个重做经典算术的读者会算出
   并且认同的那个数。
6. **报告和网页都说两步**，因为只说可靠比会让读者自己去除一遍，得到第三个谁都不认的数。

**度量**：五个 δ 全部恢复 0.799–0.800；δ=0 退化差 **4.4e-15**；49 个新测试（含九类标量
伪造、上面那个「读者抓不到的」伪造、两道闸各自的反例、被调整协变量那条出路、Berkson×差异
的矛盾、无后门设计、第二个误测列）。推迟文本按半条改：`regression_calibration.py` /
`simex.py` / `estimation/__init__.py` / `dispatch.py` / `gaps.py` 中英各一 /
`response_rendering.md` 各自**保留**结局信道的差异误差、既按臂又按协变量差异的矩阵、Cox。
基线 9538 → **9604 passed / 196 skipped**；mypy clean；`tsc -b` 通过；MCP 工具数不变。

**方法论**：

- (468) **一条「我们假设 X」的 scope 说明，先算一遍「X 不成立时答案跑到哪」。** 如果跑到
  真值另一侧，那它就不是 scope 说明，是一个会静默答错的洞——两者在文档里长得一模一样。
- (469) **同一条公式撤掉一条前提之后的样子，最好的 oracle 是它自己。** 让新形式在前提成立
  处精确退回旧模块，比再写一份代数自证强：退化点是**已经被几个月的使用验过**的那一份。
- (470) **闸门要按「读者下一步做什么」分，不按「哪个不等式没过」分。** 两条声明互相矛盾和
  声明与数据矛盾，在算术上都是一个负数，在读者那里是两件完全不同的事。
- (471) **验证器要专挑「手算读者会认同的那个错」。** 差异校正里最危险的伪造不是乱改数，
  是**只做经典那一步**——出来的数经得起任何一个拿可靠比复核的人验算，而它是错的。

### #464 唯一一种「校正它才是错」的测量误差（2026-08-30）

**现象**：仓库在六处把「Berkson / 差异型连续误差」记成一条推迟，像它们是同一种缺口。
于是连续暴露的 `measurement_error={<暴露>: {error_variance}}` 只有一种读法。**而缺的
不是一个数，是一个答错的数**：同一份 Berkson 结构的数据，真值 0.8，朴素后门斜率
**0.80263**（本来就对），Themis 今天发的是 **1.59911**（正好翻倍），还标
`numerically_solved`。

**根因：把它归成了「缺一个估计量」，而它缺的是一个词。**
经典误差 `W = X* + U`（U 与**真值**独立）抬高暴露的方差、把斜率朝零衰减；Berkson 误差
`X* = W + U`（U 与**记录下来的名义值**独立——分配的剂量、拿一个监测站的读数当整个区的
值、开出的而非吸收的量）方向反过来：`E[X*|W,Z] = W` 精确成立，普通后门斜率**本身就是**
因果斜率。**没有任何一列数据的性质能分开这两种**——哪一种成立是关于「这个数是怎么测出
来的」的事实。所以包里缺的不是一条新公式，是让调用者说出结构的那个词；在那个词存在之前，
唯一那条读法在一半的场合是**静默的错误答案**。

**为什么是根因不是表象**：

- 表象说法「Berkson 也得配一个校正器」正好反了：它要的是**没有校正器**。反向 oracle
  能把这句钉死——同样两列、同样 σ²_u，换成经典结构的数据，RC 从朴素 **0.53323** 恢复
  到 **0.79814**。所以上面那个 1.6 不是 RC 坏了，是它被喂了一个不属于它的结构。
- **代价不是零，只是不在点上。** 真值的散布按 β̂²σ²_u 落进残差（实测 **0.32211**，理论
  0.8²×0.5=0.32），于是这条设计上的每个区间宽 **1.15** 倍。这是这一族里**唯一被答案缩放**
  的声明方差——结局信道那边 σ²_v 是不带系数进残差的——所以这一行只能排在答案之后：
  效应越大，同一个名义值误差越贵，代价在有答案之前不存在。
- **那条恒等式还要线性性，而它在这里是识别层不是形式层。** 非线性结局下 Berkson 误差
  **确实致偏**（非线性函数的条件均值不是条件均值的那个函数），所以这条前提失效时点是
  **有偏**而不只是**被扭**。同一个命题在 regression calibration 那里是形式层且走
  mechanism audit——因为那边估计量**真的在拟合**一个线性模型。一个 id 装不下两种用法，
  所以是两个 id；层是关于**用法**的事实，这张表自己早就写过这个先例（同一句方差的话
  「在这里是识别前提、在那里是置信前提」）。

**做了什么**

1. **`themis/estimation/berkson.py`**：只出价格，不出点——`BerksonAssessment` 里**没有**
   `point` 字段，而这个缺席就是结论。残差按观测设计取，散布 = β̂²σ²_u，signal =
   residual − scattered；散布装不进未被解释的变异时**拒**而不是报一个负的 signal：那时
   声明的方差、线性性、散布与名义值独立三条至少一条不成立，而最后那条正是「点本来就对」
   所依赖的前提。
2. **`structure` 这个词，以及它落在哪里**：`STRUCTURE_CLASSICAL` / `STRUCTURE_BERKSON`
   放在读它的 `EffectFacts` 旁边而不是任一估计量旁边——词是调用者的，它裁的那次路由不
   属于被它裁开的任何一行。缺省读成 classical：不说话的人拿到的还是这个键存在之前拿到
   的东西。路由端问的是布尔 `exposure_error_is_classical`，refusal 端要的是词本身，一个
   事实两种读法，路由表里不再写一次这个词。
3. **不认识的词也归 Berkson 那一行，这是设计不是兜底。** 一个包不认识的结构**正是**不
   该校正的情形（校正所倚的前提就是存疑的那条），所以两条校正行都关掉；但如果到此为止，
   这份声明就一个读者都到不了——结果看上去和「什么都没声明」一模一样。所以那一行拥有
   **每一个非 classical 的声明**，认识的算价格，不认识的**指名**。
4. **β̂ 必须等于设计自己的斜率。** 那条恒等式是关于**一个**泛函的——结局对（记录下来的
   暴露 + 调整集）的普通最小二乘斜率。少了这道闸，这个块会挨着任何一个后门答案坐下，
   告诉读者那个数不需要校正——而那是没人查过的断言。判据用**算术**（法方程的解）而不是
   方法名单：名单是那个数的第二份记录，可以和它不一致，而且以后新加的族会被一张没人更新
   的表判决。
5. **验证器 `verify_berkson_error`**：每个标量从记录的 Σ_D / Cov(D,Y) / Var(Y) / σ²_u /
   β̂ 重算，不碰原数据、不 import 生产端（用 `ast` 读 import 语句钉住，好让模块正文可以
   继续**说**它不许做什么）。三条前提必须到假设账本——**结构和线性性撑的是点，方差只撑
   宽度**，所以分三条不是一条。专门拒一个伪造：把 β̂ 和一切由它导出的量**一起**改，块内
   部完全自洽，而它给出的价格属于一个读者从没拿到过的效应——所以价格的系数还要对住
   `numeric_estimate.point`。
6. **顺手改掉一个「下次会被忘记」的形状**：`_estimate_meta` / `estimateMeta` 两侧的第二个
   参数由「一个块」改成**整个信封**。限定区间的东西并不都住在 `numeric_estimate` 上，
   一个一个块点名的签名，让七个调用点各自成了下一个块可能被漏掉的地方。账本那边同理：
   `_outcome_error_premises` 推广成 `_annotating_premises`，由一个块名变成一张表。

**度量**：Berkson 数据上朴素 **0.80263**（真 0.8）vs 同一个 σ²_u 读成经典的
**1.59911**；反向 oracle 经典数据上 RC **0.79814**（朴素 0.53323）；散布 0.32211 对
理论 0.32，se_inflation **1.15**；48 个新测试，九类标量伪造 + 内部自洽的系数伪造 +
三条前提各自缺席全拒；六处推迟文本各自**保留**差异型连续误差（含结局信道的差异误差）与
Cox 的推迟——**结局信道的 Berkson 不是推迟而是不存在**：结局不进设计，`Y* = Y + V` 下
`E[Y*|D] = E[Y|D]` 且 `Var(Y|D) = Var(Y*|D) − σ²_v`，记录下来的那个结局反而是更精确的
那个，没有代价可报。基线 9477 → **9538 passed / 196 skipped**；mypy clean；`pnpm build`
通过；MCP 工具数不变。

**方法论**：

- (464) **一条把两件事并列的推迟，先拆开问它们是不是同一种缺口。** 「Berkson / 差异」
  写在一起六年，可一个缺的是估计量、另一个缺的是词；缺词的那个不是答不出，是**答错**，
  而这两件事的优先级差着一个数量级。
- (465) **能被静默答错的地方，第一件事是让调用者有办法说出区别。** 数据分不开的两种结构，
  包里只实现了一种，等于替调用者做了一个他不知道自己做过的选择。
- (466) **一个包不认识的词，必须归给某一行，而不是让所有行都关掉。** 都关掉在行为上是
  对的（不认识就别校正），在读者那里却和「什么都没声明」不可区分——沉默才是那个缺陷。
- (467) **同一个命题在两个族里可以属于不同的层，层记的是用法。** 判据是失效后果：那边
  失效是形状被扭（估计量在拟合它），这边失效是点有偏（一条恒等式倚着它）。为了复用一个
  已有的 id 而把 invalidating 记成 distorting，是拿账本的可信度换一次少写。

### #463 一次模拟重跑不出来，可它算出来的那把梯子重算得出来（2026-08-30）

**现象**：仓库在四个文件里把 SIMEX 记成「不做」，理由是同一条——它是**模拟外推**，
是启发式而不是闭式，所以**不合逐数复核的契约**。于是「连续误测 + 非线性结局」这一格
一直空着：给了 σ²_u 又想要 logistic 系数的人，拿到的是 regression calibration
按线性结局算出来的那个数。

**根因：把 SIMEX 当成了一件事，而它是两件。**
Cook & Stefanski 1994 是**先模拟、后外推**：

1. 沿声明的 λ 梯子给已经带噪的暴露**再加** sqrt(λ)·σ_u 的噪声，重拟合 B 次取平均
   → θ̂(λ)。总误差方差变成 (1+λ)σ²_u，画出的是「测得更差时这个数怎么衰减」。
2. 把声明的函数族拟合过 {(λ_k, θ̂_k)}，读在 λ = −1——误差方差本会为零的那一点。

**只有第一阶段是随机的，而它的输出正是第二阶段的充分统计量。**
所以梯子上信封，它下游的一切——外推式系数、λ=−1 的点、方差、区间——都是闭式最小
二乘，`verify_simex_numeric` 一次模拟都不跑就重算得出来。重算不了的那部分**如实说**
而不是含混过去：梯子本身来自带种子的蒙特卡洛，可复现、不可被第二个作者重算。

**为什么是根因不是表象**：

- 表象说法「模拟不可复核」如果成立，**逐档也不该可核**——可 λ=0 那一档根本不是模拟：
  加零噪声就是原数据，所以那一档**就是**未校正的拟合，重复间方差按构造为零、重复次数
  为一，还必须等于信封另一处报的 naive 点。审计能拿它对住整把梯子。
- **闭式是选出来的，不是碰上的**。有理式 γ0+γ1/(γ2+λ) 用线性化拟合（由
  θ(γ2+λ)=γ0(γ2+λ)+γ1 得 θ·λ 对 (λ, 1, −θ) 回归）而不是非线性最小二乘：一个优化器
  的出口点第二个作者重算不出，一个闭式能；而在有理模型精确成立处两者残差同为零、
  本就重合——那正是 oracle 所在。
- **默认值是量出来的，不是跟着文献选的**。文献常用 quadratic；六种配置（两种结局模型
  × σ²_u ∈ {0.25, 0.5, 1.0}，各八个样本）实测：rational 消掉朴素偏倚的
  **91–99%**，quadratic **46–87%**，linear **18–52%**，而且误差方差越大差距越拉开
  ——正是最需要校正的地方。所以默认改成 rational；代价（有理式的方差外推偶尔为负）
  也是量的：每种配置十二个样本，linear/quadratic 十二次都给出区间，rational 十次。
  那两次**没有区间**，并说出是哪一项失败，而不是把宽度压到零报个数。

**「线性结局」不是一个用例，是这块的真值 oracle**：线性结局下朴素斜率**精确**按
θ(λ) = θ_naive·Var(W|Z)/(Var(W|Z)+λσ²_u) 衰减（一个有理函数），所以 SIMEX 配有理
外推**必须**复现 regression calibration 的矩量校正。实测闭式 **0.823004** vs
SIMEX **0.823657**，差 **6.5e-04**——纯蒙特卡洛噪声。非线性结局给不了这个 oracle，
所以 `outcome_model="linear"` 是为它存在的。

**做了什么**

1. **`themis/estimation/simex.py`**：两阶段 + 三个声明族（linear / quadratic /
   rational）；logistic 的 IRLS **自己写**——scikit-learn 默认是**带罚**拟合，
   而一个被收缩的系数就是一个被衰减的系数，那个岭会顺着整把梯子走一遍，出来看起来
   像测量误差。区间走 Stefanski & Cook 1995 的 τ(λ)=σ̄²(λ)−s²(λ) 同族外推到 −1，
   **没有 bootstrap 包在外面**：点和区间读的是同一把梯子。
2. **声明的是估计量，不是精度**。路由不看数据看**声明**：同样两列既支持线性概率
   斜率也支持对数优势比，数据里没有任何东西能说出想要哪一个。所以
   `measurement_error={<暴露>: {error_variance, outcome_model: "logistic"}}` 才走
   SIMEX；不写或写 "linear" 仍走闭式——闭式胜过它自己的带种子模拟。
3. **声明了簇就不发区间，而不是把区间说成簇稳健的**。梯子上每一档的方差都是模型给的，
   模型方差说的是行与行独立，而调用者刚说了不独立。点不受影响（聚类花的是精度不是
   识别），所以点照发、区间走「为什么没有」那道门。
4. **验证器 `verify_simex_numeric`**：只拿 `grid` 用**法方程**（生产端用 `lstsq`，
   第二条路）重算系数、点、τ(−1) 与区间；**「没有区间」也是一个断言，也被核**——
   说方差非正就得真重算成非正，说是聚类就得真有簇列。二十四个伪造全拒。
5. **两张登记表各多了一个成员，因为它们枚举的是当时有的东西**：
   `audited_mechanism` 此前只许写 inherent / default / caller_asserted——三者都经
   `model=` 那条路，而那条路只有「断言」和「默认」两个答案。SIMEX 是第四条：数据分不
   开两个估计量时，说出想要哪一个**不是关于世界的断言而是问题本身**，撤回它这里不是
   变宽而是没有答案——那按定义就是 `caller_chose`。为过闸把它改标成 asserted，等于
   让账本告诉读者「撤了还有数」，而那是假的。生产端与验证端两份表同步加，注释从「三种
   情形」改写成**那条轴上的区分**——会过时的正是枚举。
6. **顺带把「谁拉的杆」变成事实而不只是解读**：信封多记
   `outcome_model_was_declared` / `extrapolant_was_declared` 两个布尔。
   `caller_chose` 那条线原本无从核对——一个默认的 "rational" 和一个被点名的 "rational"
   是同一个字符串。有了这两个事实，`caller_chose` 与 `default` 两侧都能被反向核，
   而不是拿自己的解读去核自己。

**度量**：oracle 差 **6.5e-04**；六种配置 × 八样本的族间对比如上；二十四个伪造全拒；
两个新闸门各构造了它该拒的反例（把归属改标成读者找不到的杠杆、把杠杆位置改标成另一个
族）。四处推迟文本改写（`regression_calibration.py` / `estimation/__init__.py` /
`gaps.py` 中英各一 / `response_rendering.md`），各自**保留** Berkson / 差异型连续误差
/ Cox 的推迟。板块 8 覆盖率 5-10% → **~70%**（那一行早就陈旧：离散矩阵与 RC 都已落地
却仍写着「未做」）。MCP 工具数不变（走 kernel.verify）。基线 9384 → **9477 passed /
196 skipped**；mypy clean；`pnpm build` 通过。

**方法论**：

- (460) **一条「不合契约」的推迟，先问被推迟的那个东西是不是一件事。** SIMEX 的
  「不可复核」只对第一阶段成立，而第一阶段的输出恰好是第二阶段的全部输入。缝在哪里，
  契约就在哪里重新成立。
- (461) **重算不了的那部分要单独说出来，而不是让能重算的部分替它背书。** 审计说清楚
  「梯子我没重跑」，比声称全查过更值钱——后者一旦被发现有洞，整份审计都不作数。
- (462) **默认值只能量出来。** 文献默认是别人在别的数据上的量测；换成自己的六种配置
  一跑，最优的那个和文献默认不是同一个，代价也一并看得见。
- (463) **一个枚举出来的许可表，早晚会缺一个合法成员。** 判据是：新成员填不进去时，
  先读成员的定义再读表的注释——如果注释在列举情形而不是在说轴，那多半是表旧了，不是
  成员错了。为过闸而改标，是拿一个假的解读换一次通过。

### #462 「连续优化的解重放不了，所以验不了」——这条推迟理由是错的（2026-08-30）

**现象**：仓库在三个文件里把 NOTEARS 记成「不做」，三处给的理由是同一条：
L-BFGS-B 找到的局部最优**没法一步步重放**，所以返回的图会是一个谁都重算不出来的数——
而那正是这个仓库唯一不发的东西。

**根因：把「重放搜索」和「重算答案」当成了同一件事，而只有前者不可能。**
最小二乘目标与其梯度**只经由 Gram 矩阵 S = X'X/n 依赖数据**：

    ‖X − XW‖²_F / 2n = tr((I − W)' S (I − W)) / 2      ∇ = −S(I − W)

所以一个 d×d 矩阵就是**整个问题的充分统计量**。无环性残差 tr(e^{W∘W}) − d、
目标函数值、以及一阶（KKT）残差，全都能被一个**没见过数据、没跑过求解器**的东西
从这一个矩阵重算出来。d×d 小到能上信封——这跟仓库里那些放不下的矩量矩阵不同——
所以「连续搜索能不能被审计」在这里根本不取决于求解器，取决于统计量。

**为什么是根因不是表象**：

- 表象说法是「搜索不确定所以不可验证」。但同族里 DAG-GNN / RL-discovery **确实**
  没有这条充分统计量，对它们这条推迟理由**仍然成立**——三份文件里现在写的是这个
  区分，不是「NOTEARS 做了所以这一族都能做」。
- **不能证的那部分照样不证**：全局最优。问题非凸，一阶残差只说返回点近乎驻点，
  不说它最好。信封如实说了，schema 的描述里也写死了这句，并有一条测试拿**一个更差的
  局部点**（把解阻尼到一半、每个字段照实重算）去过审计——它**通过**，因为证书从来
  没声称过最优性。
- **地板是量出来的不是拍的**。误差容限一开始写成常数 1e-8，结果一个伪造漏了过去：
  把 8.56e-09 的无环性残差改写成 0.0。h 是两个接近 d 的数相减，抵消掉的量级由
  **矩阵指数的元素**决定（不是由 d，更不是由近零的结果），所以地板改成按
  `max|e^{W∘W}| · d` 推。实测：诚实分歧 2.8e-13、地板 3.0e-11、而 h 本身
  3.65e-09——两边各留 100 倍余量，d=2…24、等尺度与不等尺度全过。

**做了什么**

1. **`themis/estimation/notears.py`**：增广拉格朗日 + L-BFGS-B（[w⁺,w⁻]≥0 的 L1
   改写），出 `NotearsCertificate`（h / 目标 / 一阶残差 / 乘子 / Gram）。乘子只记
   **一个**数：子问题梯度用的是 α + ρ·h，而约束问题的 KKT 用的是更新后的乘子，
   两者是同一个量——**同时记 (α, ρ) 就是在邀请它被加两遍**（第一版就加了两遍）。
2. **一阶残差只对自由变量取**。对角线被 `bounds=(0,0)` 钉死（模型不许自环），
   被钉死的变量的一阶条件带一个边界乘子、能吸收任意梯度；在那里要求梯度落进 L1
   次微分，是在要求一个这道题从没提出过的条件。它报出来的数恰好等于每一列的
   **残差方差**——是拟合好坏的事实，跟最优性一个字关系都没有。这不是放宽容差：
   收紧 L-BFGS-B 容限、换任何一个乘子，那个 1.09 都纹丝不动，而排除对角线后
   立刻变成 0.0046。
3. **尺度诊断落到每条边上，不做全局布尔量**。Reisach 等 2021：这一族会利用边际方差
   顺序，方差恰好沿因果序上升时光排序就能复现整张图。所以同一份数据标准化后重跑一遍，
   报**哪些边活下来了**。全局布尔量试过，扔了——L1 加固定阈值本来就不是尺度等变的，
   所以「有东西动了」几乎恒真，说了等于没说；而逐边版本在方差递减那一例里
   **恰好把两条伪边挑了出来**，四条真边全部存活。
4. **验证器 `verify_notears_fit`**（第八个 artifact）：只拿 `gram` 与 `weights`
   重算三个残差、按声明阈值重读边、并从 Gram 的**对角线**重算 varsortability
   （中心化后一列的方差就是它的 Gram 对角元）。矩阵指数是**第二份誊写**：非负幂级数
   加 scaling-and-squaring，对上 SciPy 的 Padé——参数是 W∘W（逐元平方），所以级数
   全是非负项、没有抵消，两条路不一致就是真不一致。十七个伪造全部被拒。
5. **边的形状复用 `orientation_common#/$defs/edge`**，没有新造 `{from,to}`：
   一个形状两份记录，正是仓库那条规则在管的东西。

**顺带修的那件事，其实是它把路挡住了**：第六个算法要写自己的说明句，才发现
`AlgorithmSpec.note_clause` 的类型是 `str`——**缺的从来不是翻译，是语法上没有放
第二种语言的位置**。于是六个算法的说明、四组前提检查、选择器的理由、方向待定的追问
和数据诊断全部改走 `statedSentence` 那道门（token + 这次的事实，语言在读者那端组装）：
`themis/estimation/discovery_words.py` 一张表，`discovery.py` 的单语债 **23 → 6**
（剩下的六条是拒绝通道与 Markov blanket 自己的 note，另一条通道）。缺口报告里
`"; ".join(violations)` 也跟着没了——它拿 ASCII 分号去接中文句子，正是
`listing()` 存在的理由。

**度量**：已知 5 节点 DAG 在等噪声尺度下**边集完全正确**；噪声尺度沿因果序递减时
（varsortability 0.385）出现两条反向伪边，**逐边尺度检查恰好把这两条挑出来**。
Gram 充分统计量与原始数据的损失/梯度一致到 **1e-10**。两条矩阵指数路线相差
**4.4e-16**。十七个伪造全拒。基线 9320 → **9384 passed / 196 skipped**；
mypy clean；`pnpm build` 通过。

**方法论**：

- (456) **一条「做不到」的登记理由，本身也是待验证断言。** 这里的理由听起来无懈可击
  ——不确定的搜索、非凸、局部最优——但它把两个不同的问题合成了一个。推翻它不需要
  新算法，只需要问一句「答案依赖数据的哪一部分」。
- (457) **一个诊断做成全局布尔量之前，先问它会不会恒真。** 恒真的警告等于没有警告，
  而且比没有更糟：它会让读者以为这一项被看过了。
- (458) **误差容限必须从量级推，不能从手感定。** 一个近零的量，它的地板由被抵消掉的
  那些数决定，不由它自己决定；按结果定地板，就是给伪造留门。
- (459) **一个新成员写不进某个槽时，问题多半在槽不在成员。** 第六个算法没地方写它的
  说明句，暴露的是前五个也没有——它们不是「还没翻译」，是没地方翻译。

### #461 一个数是几档剂量的平均，而它从不说是哪几档（2026-08-30）

**现象**：有序剂量（0/1/2/3 支烟、0/1/2/3 年教育）配一个工具，`auto` 走 `iv_2sls`，
给出一个数。这个数**是对的**，但读者拿到的说法是「线性 ATE」——而在处理有多档时，IV
估计量根本不是任何单独一档的效应，是各档单位效应的一个**加权平均**，权重完全由处理与
工具决定、可以算出来，却一个字都没说。同时，单调性在这里其实是**可反驳的**，仓库却把它
列进「方法本身要求／不可检验」那一档，从不去查。

**根因：把答案的语言停在了「哪一族估计量」，没走到「这一族在这份数据上到底平均了什么」。**
Angrist-Imbens 1995 的内容不是一个新估计器，是**同一个数的正确读法**。把结局写成
`Y = Y_{s₀} + Σ_j (Y_{s_j} − Y_{s_{j−1}})·1{S ≥ s_j}`，再只用「Z 与所有潜在结局独立」
这一条，`Cov(Y,Z)/Cov(S,Z)` 就恒等于各档单位反应的加权平均，权重

    w_j = (s_j − s_{j−1}) · Cov(1{S ≥ s_j}, Z) / Cov(S, Z)

**只由 (S, Z) 决定**。所以缺的从来不是算力，是这份信封没有承载这句话的地方。

**为什么是根因不是表象**：

- 表象修法是新写一个「ACR 估计器」。但它算出来的就是 2SLS 那个数——二值工具下 2SLS＝
  Wald＝ACR。再写一遍等于给同一个比值找第二个作者，而两个作者里迟早有一个会漂。
  所以这一路**复用 `_two_sls_point` 出点**，只补它没说的那部分。
- 表象修法之二是把权重当成「附加信息」塞进日志。但权重里有一条**能被证伪的断言**：
  单调性成立时每一档的权重都与总体一阶段同号，所以**任何一档出现负权重就是数据在反驳
  单调性**。这不是注脚，是「这个数不是任何一组效应的平均、是在往外外推」。
- 决定性旁证：这条反驳**藏得住**。构造的人群里总体一阶段 +0.15、2SLS 点 +0.50，两个数
  看上去都正常，而 0→1 那一档的权重是 **−0.33**。一个只看总体一阶段的诊断永远发现不了它。

**做了什么**

1. **一条权重公式，不分二值工具与有序工具**——上面的恒等式本来就没有分叉。原先记的
   「有序工具要把 2SLS 拆成相邻工具档的 Wald 加权平均」那条式子另测过：它对，且
   `(z_ℓ − z_{ℓ−1})` 这个间距因子是必需的（等距时看不出来，不等距时差 0.142）；但按
   处理档展开的这条更简单也更该报给读者，于是取它。
2. **点由 `_two_sls_point` 出，逐位不变**——这条路重新描述一个数，不重新算一个数。
3. **`auto` 的判据不是「变量连不连续」**，是「这张档位表读不读得动」。分解对样本里
   **实际出现的水平**是精确的，所以剂量在概念上是否连续根本不是要问的问题；超过 12 档
   就退回线性系数，并**出声**说明原因（`acr_declined`），照 `stratification_fallback`
   的判例。二值处理不进来：一档承担全部权重就是把点重说一遍。
4. **单调性改记为 `monotonicity_refutable_*`**——仓库早有这套命名（数据能答话的写
   refutable、只能假设的写 assumed）。Wald 那条仍是 assumed 且正确，因为那里没有东西
   能答话；这条路算的正是单调性约束的那个量。
5. **条件集下不出 ACR**，因为条件下的 ACR 是**另一个估计量**（层内分解再选一种跨层
   聚合方式），不是这个估计量加一个选项。声明的边界，不是悄悄的近似。
6. **验证器 `verify_acr_decomposition`**：只拿「每个工具档的一个计数与三个求和」重算
   全部协方差、每一档权重、点，以及权重和为一。**权重和为一不是出口处归一化的结果，
   是恒等式的推论**——所以「和为一但与数据不符」和「与数据相符但和不为一」都会被抓。
   十个伪造全部被拒，含**把反驳压掉**这一个。
7. **删掉了一个字段**：原本记了一个 `basis`（区间判还是点判）。它是其他字段的纯函数
   （有没有区间一看便知），声明它就是同一个量写两遍——#458 刚修过这类洞。同理把档位的
   `lower/upper` 改名 `from_dose/to_dose`：两个字段之外就是置信区间，用端点的拼法写
   一个剂量跨度会被读成区间（仓库的区间登记表当场抓住了这一点）。

**度量**：D1 = 潜在逐单位反应的合成人群，真值从这些反应闭式算、估计器一眼都看不到：
恒等式在单调与有反抗者两种人群上都是 **< 1e-12**（它是恒等式，本来就不需要单调性）；
权重和为一 **< 1e-10**；去掉间距因子后在不等距剂量上相对误差 **> 10%**。反驳那一例：
总体一阶段 +0.15、点 +0.50 都正常，0→1 权重 −0.33，区间整体在零以下。基线 9284 →
**9320 passed / 196 skipped**；mypy clean；`pnpm build` 通过。

**方法论**：

- (452) **「这个数对不对」和「这个数是什么」是两个问题，而只有第一个有测试守着。**
  一个正确的数配一个太粗的名字，不会让任何测试变红——#459 与这一条撞的是同一堵墙，
  一个丢在图层，一个丢在估计层。
- (453) **一条假设被登记成「不可检验」时，先问是这条假设不可检验，还是这条路不去检验。**
  同一条单调性，Wald 那里确实无从答话，换一条路就有了；把它写死成属性，就永远不会去看。
- (454) **能被证伪的东西必须主动去证伪，而不是等它自己冒出来。** 这里的反驳信号
  （负权重）在总体一阶段上完全不可见——不专门看那一层，就等于没有这个检验。
- (455) **凡是能从别的字段算出来的字段都别写进信封。** `basis` 只是「有没有区间」的
  改写，写下来就多了一个会与事实分家的副本。

### #460 验证器读不懂提问的方式，就不是验证器（2026-08-30）

**现象**：凡由一般 ID 那一行（Tian 分支）给出**数值**答案的效应查询，
`themis.verify` 抛 `RuleCheckFailed: identify_via_tian requires IdentifyQuery
context`——不是判定不合格，是**根本无法验证**。在 96dcf89（当时未改动的 HEAD）
与工作树上表现一字不差，属既有缺陷；整套 9241 条测试没有一条覆盖它。#459 的
协变量前门图正好落在这一行上，才把它撞出来。

**根因**：`identify_via_tian` 与 `tian_hedge_witness` 通过 `IdentifyQuery` 的
**字段布局**去读 x 和 y，读不到就拒绝——而它们真正需要的两样东西在两种查询形状里
都在，只是取值路径不同（`q.target` 是 Atom，对效应查询则是 `q.target.atom`）。

**为什么是根因不是表象**：兄弟规则 `identify_via_idc` 早就两种形状都认，注释还明写
「Both reduce to the same atom-level check」——所以这不是「Tian 规则只服务符号查询」
的设计，是同一次扩展漏了两条。表象修法是在效应路上不发这一步：那会让数值答案的推导链
少掉「这个 c-factor 是合法识别式」的**唯一见证**，等于删证据换过验证。决定性旁证是
Tian 规则体除 x、y 之外什么都不用，剩下全是图上的 c-分量运算——它对 `IdentifyQuery`
的依赖是取值路径，不是语义。

**做了什么**：把 `identify_via_idc` 已在用的取原子写法提成 `_query_atoms`，三条规则
共用。原来那份内联的 fork 正是「会被复制到两处、只在一处更新」的写法，而它确实只被
更新了一处。

**方法论**：

- (450) **一条规则拒绝一份合法信封时，先看它拒的是「内容」还是「提问的方式」。**
  后者不是判定，是盲区——它既不说不合格，也不说合格，而外面看起来两者都像「验过了」。
- (451) **同族规则里有一条已经处理了某种形状、其余没有，那不是设计是漏。**
  已处理的那条的注释通常就写着为什么其余也该处理。

### #459 需要握住一个变量的前门，仍然是前门（2026-08-30）

**现象**（端到端跑过，不是读签名）：两处损失。

(a) 教科书前门图（X→M→Y、X↔Y）的报告告诉读者「前门调整 —— 经中介 {m}」；加上
C→X、C→M 之后（前门只在握住 C 时成立），同一个问题的报告只说「ID 算法的一般解
（c-factor 分解）」。数是对的——符号端 0.548＝手算 0.548，数值端 0.2771＝模拟 SCM
真值 0.275——丢的是读者能读的那一层：他不知道这是前门、不知道中介是谁、也不知道
「握住 C」才是它成立的条件。

(b) 更大的一处：`effect` 查询（**出数的那条主路**）上 `extensions["identification"]`
一律为 null，后门、前门、一般解全都没有。「识别模式」这一行**从未到达任何一个拿到数的
读者**。唯一的例外是 IV 逃生路——而正因为它是孤例，才说明这是漏了不是设计。

**根因：「图上认出来的是什么模式」被算了两遍，两遍都不完整。**

- 认模式的权威实现 `_recognize_identification_pattern` 只在 IDENTIFY 路上被调用。
  EFFECT 路把模式**隐式编码成了哪一行 cascade 命中**，只在推导步骤的词汇里留痕——
  而读者不读 cascade 行。
- 认模式器本身只认识文献里两个前门物种中的一个：`front_door_sets` 的 FD2 写死
  「空条件下」、FD3 写死「被 {X} 阻断」，没有协变量集这个概念。广义前门判据
  （Fulcher, Shpitser, Marealle & Tchetgen Tchetgen, JRSS-B 2020）允许一个基线
  协变量集 C：FD2 在给定 C 下成立、FD3 被 {X}∪C 阻断。ID 引擎早就能识别这一族图——
  它吐出的公式正是 Σ_c P(c)·Σ_z P(z|x,c)·Σ_x' P(x'|c)·P(y|x',z,c)。

**为什么是根因不是表象**：

- 从公式反猜模式＝读产物。而产物对每个点识别查询都是同一个规范 c-factor，本来就
  长一个样，猜不出来。
- 给 cascade 每行各写一份标注＝把认模式复制成 N 份，而权威实现已经存在；IV 行正是
  「N 份里没人更新的那一份」的先例。
- 把 `elif not q.given` 放宽成允许 `q.given`＝混淆两件事：`q.given` 是**查询自己的
  条件**（P(Y|do(X), Z)），不是**调整用的协变量**；两者读起来一样，在对撞点上意思
  相反。
- 决定性旁证：协变量那一例，引擎吐出的公式**就是广义前门公式**。引擎知道，标签器
  不知道，读者更不知道。

**做了什么**

1. **判据写一份，两个枚举器共用**（`_front_door_criterion_holds`）。
   `generalized_front_door_sets` 返回 (中介集, 协变量集) 对；`front_door_sets` 是它
   C=∅ 的那一面。语义逐图不变（七个图上逐一对过），这一点是必需的而不是保守：
   `estimate_frontdoor` 算的正是 C=∅ 的公式，喂给它一个带 C 的集合会算错。
2. **极小性取在「对」上**，按分量序；枚举按总规模递增，所以支配某一对的那一对
   一定先到手。
3. **认模式器改成按原子取参数**，不再接查询对象。两种查询形状都需要它，接
   `IdentifyQuery` 正是把它锁在一条路上的那件事。
4. **EFFECT 路在唯一知道哪一行赢了的地方挂上同一份标注**。自己已写识别块的行
   （IV / transport / 纵向 / 联合 / 中介 / 互为因果）不动——它们认的是这个识别器
   不知道的结构，覆盖过去是降级不是补充。
5. **读者那一行多一节**：「前门调整 —— 经中介 {m}，并握住 {c}」。空的协变量集是
   *缺席*而不是空列表：没有要握的东西，和「有一个集合等着你去找」不是一回事。
6. **验证器新增 `verify_identification_pattern`**——此前没有任何东西核对这句话，
   而它是读者关于「数从哪来」的唯一一句。它用**边删除 + m-分离**重导（「从 A 出发
   的后门路径在给定 S 下开着」⟺「剪掉 A 的出边后 A 与目标仍 m-连通」），与生产端的
   「路径枚举 + 首边过滤」是两套推导，且用验证器自己的 m-分离。**一般解是唯一被反过来
   查的标签**：宣称一般解而图上其实有后门或前门可命名，判为不合格——那正是这一条要修
   的失败，一个抓不住它的验证器等于没验。

**度量**：判据可靠性不靠断言靠 oracle——带潜在 U 的合成 SCM，真值从 SCM 参数闭式算，
广义公式只用把 U 边缘掉之后的观测联合算：60 个 SCM 上最大偏差 **< 1e-12**；同一批图上
把 C 丢掉而不是握住的教科书公式最大偏差 **0.0754**（所以 C 不是装饰，是识别成立的
条件）。十个伪造全部被拒，其中一个正是原缺陷本身。基线 9241 →
**9284 passed / 196 skipped**；mypy clean。

**方法论**：

- (447) **一个标签只覆盖文献里某判据的一种特例时，症状是「另一种特例失去了名字」，
  不是「算错了」。** 引擎完备时尤其如此：数照样对，丢的是人能读的那一层，所以没有
  任何测试会红。
- (448) **同一件事在两条路径上各算一遍，其中一条会先烂掉。** 判断哪一条烂了不靠读
  代码，靠问「这个事实在两条路径上都被写进信封了吗」——本例里 IV 行写了、其余全没写，
  那个孤例就是证据。
- (449) **凡是被写进信封给人读的判断，都要有一处独立重导它。** 数值一直有验证器，
  结构标注此前没有；而读者读的恰恰是标注。

### #458 剂量分档测错了，不该只因为分了档就没得救（2026-08-30）

**现象**（端到端跑过，不是读签名）：测量误差校正的**结局侧**混淆矩阵一直是 k×k，
**暴露侧**写死 2×2。给三值暴露配一个 3×3 的验证矩阵，拿到的是
`exposure_not_binary`（标记 `kind: "unbuilt"`）——没有数，退到宽 0.731 的 Manski
自然界（[0,1] 尺度上几乎不含信息）；而**不给**矩阵反而能拿到一个 `backdoor_logistic`
的数，只是它是衰减的。组合（X+Y 双通道）版有同样两道闸。流行病学最标准的暴露记法
——「每天 0 / 1–10 / 11–20 / 20+ 支」——正好落在这一档。

**根因：修正的数学与暴露有几个水平无关，把闸门钉在二值上的是答案的形状。**
逐层联合逐列求逆 `p_true[:, y] = M⁻¹ p_obs[:, y]` 对 k×k 一个字都不用改；真正卡住的是
实现把产物写成了 `r1 − r0` 这一个标量，而 k 个水平上不存在唯一的「那个差」。二值不是
数学的限制，是被写死的答案形状倒灌回了入口条件。

**为什么是根因不是表象**：

- 表象修法之一是放宽 `len(states) != 2` 仍返回一个点——那必须偷偷挑一对水平当「两臂」，
  等于程序替用户做了一个没被授权的决定（哪个是参照剂量）。
- 表象修法之二是非二值时静默退回 naive——等于宣布用户手上的验证研究没用，而它明明可用。
- 决定性的旁证是**结局侧为什么没撞上这堵墙**：结局的 k 个状态被 `target_value` 收成
  一个标量风险，**结局多值不改变答案形状，暴露多值改变**。这既解释了不对称当初为什么
  会产生，也说明它不是疏忽。
- 这与 #456 撞的是同一堵墙（「把两臂之差当原语，而定理把某水平上的反事实均值当原语」）。
  那一案已经判过，也已经留下承载它的答案形状 `DOSE_RESPONSE_CURVE`。所以正确的改动
  不是放宽闸门，是**让产物随暴露基数变形**，并复用既有形状而不是新造一个。

**做了什么**

1. **原语换成「每个水平上的标准化风险」**。`_exposure_formula` / `_combined_formula`
   返回 `risks[a] = Σ_z P(Y=y*|X*=states[a], z) P(z)`，对比从它上面读。二值时
   `risks[1] − risks[0]` 就是这个估计器一直返回的那个风险差，**同样的算术同样的次序**
   ——测试把它钉到最后一位（0.3065665768996223）。
2. **参照是调用方声明的第一个状态**。二值仍强制 `[control, treated]`（那里有个约定可以
   搞错，而已发出的每个数都由它签名）；超过两个水平没有这样的约定可读，**次序即声明**。
3. **超过两个水平就不出 `point`，答案是曲线**。`themis.answers` 声明的两个形状是
   **互斥备选**——每个渲染面取第一个命中的形状，所以点与曲线并列会让曲线一个答案都不
   承载。`(POINT, DOSE_RESPONSE_CURVE)` 照 `proximal_bridge` 的先例。
4. **组合版同样放宽**，并修掉一个只在二值下才对的式子：`det_joint` 是 Kronecker 积的
   行列式 `det(M_x)^k · det(M_y)^kx`，第二个指数原来写死 2。**它错得无声**——两种写法
   都给出一个看着合理的数。
5. **验证器逐水平独立重算**：从记录的逐层 kx×k 联合计数重解每个水平的风险、曲线上每一行
   的对比、以及记录的 `risks`/`naive_risks`。构造并跑通十个反例（伪造点、伪造曲线上一点、
   丢一个水平、把某行改标成参照、伪造逐水平风险、挪动参照、篡改联合计数、篡改矩阵、
   `reference_point` 与首个状态不符、在多值上记一个点）。
6. **读者拿到的不能变少**。「未校正 → 校正后」这一行是这一节存在的理由——没有它读者
   分不清「校正改变了一切」和「校正什么都没改」。多值下没有单一的移动，于是**逐水平**说：
   `1：未校正 0.1175 → 校正后 0.1511、2：未校正 0.2395 → 校正后 0.3459`。
7. **顺手补掉一个既有的洞**（反例探针撞出来的，不在原计划里）：`measurement_correction`
   块里展示给审计者看的混淆矩阵，与 `sufficient_statistics` 里那份**被真正求逆**的矩阵，
   此前从不互校。也就是说信封可以给读者看一个通道、而那个数是另一个通道算出来的，所有
   数值检查照过——因为所有数值检查读的是另一份。现在两份必须逐元素相等。
8. **`exposure_not_binary` 物种删除**——它说的那件事（「这项校正只做二值暴露」）不再为真，
   而一个被命名却永远说不出口的物种正是仓库禁止的。

**度量**：D1 = 潜在三值 X* + 已知 3×3 通道的合成 SCM，逐水平真值（0.29 / 0.44 / 0.64）
是从 SCM 参数闭式算的、不是从估计器读回来的；校正后最大偏差 0.0029，而 naive 在
2−0 这个对比上给 0.2395（真值 0.35）。双通道版最大偏差 0.0030。基线 9214 →
**9241 passed / 196 skipped**；mypy clean；`pnpm build` 通过。

**方法论**：

- (444) **登记表上「某函数没有某参数所以做不了某事」这类条目不可信**，因为能力会被上移到
  通用引擎而旧函数留在原地降级。判断缺口的唯一可信证据是**端到端跑一个它该失败的程序**；
  grep 到的签名只能用来找地方，不能用来下结论。这一条是当天另一件事逼出来的：清单上
  「条件前门」被同样的推理判成真缺口，实测两种处境全都早就通了（ID/IDC 引擎完备，
  `front_door_sets` 自 Phase 15 起只是给人看的图案标签器），是第五个误报坑。
- (445) **一个能力被限制在某个基数上时，先问限制是在数学里还是在产物的形状里。** 数学不
  在意宽度的时候，真正的约束几乎总是「答案被写成了一个标量」，而那是可以换形状的。
- (446) **同一个量在信封里写两遍时，必须有一处检查它们相等**——否则被重算的那份是真的，
  展示给人看的那份是装饰，而读者读的恰恰是装饰的那份。

### #457 通道反演不了，不等于什么都说不出（2026-08-29）

**现象**（五层核实过）：离散近端这条路，通道一薄就只会拒绝——代理层级数不够
（`proxy_cardinality_mismatch`）、处理多于两个水平（`treatment_not_binary`）、
矩阵解不动（`rank_condition_violated`）。三条都是诚实的拒绝，也都到此为止。而
Miao, Geng & Tchetgen Tchetgen 2018 的 §4 就是为这一档写的：给不出数的时候，
**「到底有没有效应」这个更弱的问题仍然可以答**。识别层、估计层、schema、验证
器、渲染层五层全查过，一处都没有。

**根因：Themis 把「近端」当成一种只有一种产物的能力——一个数。** 而论文里
「点识别」和「因果零假设可检验」是两个不同强度的结论，压在同一组模型 (f) 假设
上。公式 (5) 要每个代理各有 k 个水平、且 `P(W|Z,x)` 可逆；§4 只要**把各处理水平
的通道摞起来**之后行满秩——严格更弱：单个 x 上的矩阵可以是奇异的，摞起来仍然满
秩。挡住数的是**样本**，不是图；图识别得好好的。一个把「识别成功」和「有数」绑
死的估计层，读不出这两者之间还有一档。

**为什么是根因不是表象**：按表象修＝在拒绝的句子里加一句「你还可以去做个检验」。
那句话不产生检验，读者也没有工具去做；而且它把「Themis 能答的」和「Themis 没
答的」之间的界线画错了——检验是**这套假设下就能得到的结论**，不是别处的服务。

**动手前先回原文核对了 §4**（任务自己要求的），核出两件与记忆不符的事：

1. 条件 (iv) 松掉的是 **Z 不是 W**。`P(W|U)` 要可逆，所以 `|W| = |U| = k` 一步
   没松；松的是 `Q = {P(W|Z,x₁),…,P(W|Z,xᵢ)}` 只要行满秩，而它是 k×ij 的。于是
   要求变成 **ij ≥ k+1**：**粗的 Z 可以用多值的 X 来抵**。两个代理在检验里的角色
   因此是**相反**的——`W` 定 γ 的长度、必须折到 k；`Z` 的层级是拿来当矩条件花的，
   有几个用几个，用原始粒度。点估计要两个都折到 k，而**折 Z 恰恰是失败的那一步**，
   这就是查询走到这里的原因。
2. 定理 2 印出来的权重**不对**（见下）。

**测出来的偏离，以及它值多少**：定理 2 用 `Σ`＝`q̂` 自己的协方差做权重，只要求
`Q̂` 相合。但 `q̂` 与 `Q̂` 是**同一批行**上的平均，格子内 `Y` 与 `W` 由同一个 `U`
驱动、并不独立；零假设下残差是 `M(e − Eᵀγ)` 而不是 `Me`，只用 `Var(e)` 建的权重
差了一个同阶项。名义 5% 下实测：n=2000 时 15.5%、n=8000 时 11.9%、n=30000 时
12.7%——**不随样本变大而收敛**，这正是系统性错误与小样本误差的分界。把第一阶段
的误差一起带上（对矩条件 `E[Y − γᵀe_W | 格子] = 0` 做两步 GMM，权重取拟合出的 γ
真正留下的残差的方差）之后，同一批抽样上是 5.4% / 4.4% / 6.0%。同一个零假设、同
一个 γ、同一个 `r = ij − k`，只有权重不同——而权重就是「能守住水平的检验」与「守
不住的检验」之间的全部差别。印出来那版看着更有功效，那个「功效」是过度拒绝。

这是**对定理印出来那一版的偏离，不是对论文的更正**：拿它自己的模拟做的校准、
补充材料这边没有、设定也可能不同。只声称测到的东西。

**做了什么**

1. **新估计器 `proximal_null_test`**，产物是新答案形状 `NO_EFFECT_TEST`——不是
   点也不是区间。整条链走满五层：形状注册、信封、schema、验证器、双语渲染。
2. **交接由三条 species 触发，且只由它们**。图层的 `not_identifiable_proximal`
   照旧拒绝：§4 读零假设用的分解就架在模型 (f) 上，图不认证，检验一样没有意义。
   检验放掉的是**通道可逆**这个关于样本的条件，从来不是那个关于图的论证。
3. **`proxy_cardinality_mismatch` 盖着两个相反的处境**，只接管其中一个。代理太
   **粗**：没有任何声明能拿到数，检验是剩下的最强答案。代理太**细**：点估计只差
   一个 `proxy_coarsening`——这时交接会拿一个 p 值换掉一个够得着的数，还顺手把那
   条能拿到数的差事从页面上抹掉。这是既有测试抓出来的，不是想出来的。
4. **回退失败时，抛回原来那条拒绝**。检验是一次**加码**，加不成就该留下原本已经
   成立的事实。让检验自己的抱怨冒出来，会把调用方问的那件事（通道反演不了）换成
   一件他们没问过的事（样本喂不饱检验的格子），而后者永远是两者中更弱的那条。
5. **验证器整份重导**，不是审元数据。p 值是最需要这样对待的一个：它是 [0,1] 里的
   一个数，没有形状可以出错，除了从格子里重算一遍，没有任何东西能把真的和写上去
   的分开。逐格的充分统计量（占比、`E[Y]`、`E[Y²]`、`P(W)`、`E[Y·1{W=w}]`）随信封
   走，验证器先查它们彼此相容——占比求和为一、格内概率求和为一、`E[Y²] ≥ E[Y]²`、
   各格报同一组 W 水平——再重解统计量、自由度与 γ。
6. **答案层级归到 `none`**。检验既不是点也不是区间；已经产出答案的运行原本会被无
   条件调和成 `point`，那会许诺一个信封里没有的数。

**读者拿到的是什么，说清楚**：p 值交到一个问「有多大」的人手里，会被读成「效应很
小」。所以两个判决**分开写**、不写成一句带「不」的：拒绝，是「有效应」的证据，且
对大小、方向、人群一言不发；没拒绝，**不是**「效应为零」的证据，只是没有证据说它
不为零——同样的结果既来自真的没有效应，也来自行数不够，也来自代理太弱看不见。

**度量**：名义 5% 下的第一类错误率 0.052 / 0.043 / 0.054（n = 2000 / 8000 /
30000，各 1200 次）；功效 0.268 / 0.720 / 0.960 / 0.983（effect = 0.05 / 0.10 /
0.20 / 0.40，n=8000）。测试里钉的是 n=4000、400 次，实测 0.04，上限设在 9%——够松
能扛住蒙特卡洛噪声，够紧能让印出来那版的 12–15% 掉下去。基线 9147 → **9214
passed / 196 skipped**；mypy clean；`pnpm build` 通过。

**方法论**：

- (438) 「这个方法在这里给不出答案」要拆成两半问：是这套假设推不出任何结论（真
  边界），还是推不出**你要的那个强度的**结论（还有更弱的结论没取）。同一条拒绝
  读起来完全一样，而后者是一整档能力。
- (439) 论文里的定理，实现前要把它的**条件**逐条对着原文核，别对着自己的记忆核。
  这里记的是「单代理也能测」，原文说的是 `ij ≥ k+1`——松的是另一个代理，而且松出
  来的是「多值处理可以抵粗代理」这条我根本没记住的路。核对的成本是读两页，记错的
  成本是把闸门建在错的那一侧。
- (440) 检验类的东西，**唯一算数的验收是模拟出来的水平与功效**。读代码看不出一个
  权重是不是对的：这里印出来的那版逐行照抄也是错的，而且错得像「更灵敏」。守不住
  水平的检验比没有检验更糟——它在读者恰恰因为别无他法才来看它的场合，凭空造出因
  果证据。
- (441) 区分系统性错误与小样本误差，看**它随 n 收不收敛**。12–15% 三个样本量上不
  降，就不是「样本还不够大」，是权重错了。这一条比任何单点的数值比较都有判别力。
- (442) 一条 species 盖着两个**相反**的处境时，新加的回退只能接管其中一边。这里
  「代理太粗」与「代理太细」共用一条拒绝，而后者离一个真数只差一次声明——不加区分
  地接管，就是拿更弱的答案换掉更强的，并且把那条差事一起抹掉。既有测试抓到了它，
  这正是「别把回退写在拒绝点上、要写在拒绝**之后**」的理由。
- (443) 回退是加码，不是替换。加码失败时该抛回原来的结论，而不是让加码自己的失败
  冒出来——调用方没问过它，而它总是两者中信息更少的那条。

### #456 剂量不是两条臂加一个循环（2026-08-29）

**现象**（五层核实过）：处理有三个水平时，近端这条路返回 `treatment_not_binary`
拒绝——问题识别得出来（`structurally_solved`），数出不来。实测确认它不会悄悄
二值化，是一次诚实的拒绝。后门那条路早有整套剂量-反应（`dose_response_*` 三个
后端、答案形状 `DOSE_RESPONSE_CURVE`），近端连答案形状都还是 `POINT`。

**根因：Themis 的近端层把「两臂之差」当成原语，而定理把「某个水平上的反事实
均值」当成原语。** Cui et al. 2024 定理 2.1 式 (4) 是
`E[Y(a)] = ∫∫h(w,a,x)dF(w|x)dF(x)`——对任意水平 `a`；ATE 是它的差，是**导出
量**。定理 2.2 加 Remark 3 在 `q` 那侧说同样的话，并明说「也适用于连续、可能
多元的 A」。所以 `a` 从一开始就是桥的**自变量**。两臂切分把 `a` 当成了「哪一组
行」而不是「基函数的一个输入」；二值时这两件事恰好等价，反转一直没有代价，
水平一多就断了。

**为什么是根因不是表象**：按表象修＝在两臂循环外再套一层 for，对每对水平各跑
一次。那样曲线上每个点来自**不同的 h**，而式 (4) 要的是同一个 h 在不同 `a` 上
求值；而且那个积分是对全样本的 `dF(w|x)dF(x)`，不是对参与该次对比的行。

**做了什么**

1. **联合解**：`a` 进两侧设计，全样本解一次得一个 θ；水平 `a` 上的点是
   `w̄(a)ᵀθ`，`w̄(a)` 是把 span 设计的处理列换成常数 `a`、其余保持观测值后按行
   求均值——正是式 (4) 的那个积分。基函数复用**在观测列上拟合**的那一套；从常
   数列重拟合会按零方差标准化，等于每个水平上换了个函数。
2. **两条路并存，不迁移**。两臂解给每个臂自己的 θ，等于 A 上饱和的桥，二值时
   严格更一般；迁移会在调用方没饱和时悄悄收窄既有估计量。分岔由**声明**决定
   （sieve 提没提处理），答案形状由**基数**决定（两个水平是对比，更多是曲线）。
   四个格子里只剩一个是拒绝：多水平 + sieve 变不了。
3. **`treatment_not_binary` 收窄**，新 `bridge_cannot_vary_with_the_treatment`
   接手它原来盖住的另一半。后者是 `Kind.REQUEST` 不是 `UNBUILT`：工具有这个形
   式，是声明没用它，改一行再跑就有数。
4. **验证器全额重导**，没有借后门那条路的宽松。曲线的记录比对比的**更少**——
   一个算子加每个水平一个 `w̄`——验证器解一次 θ 再逐个乘出来，所以移动曲线上任
   何一个点，都是把它移离了产生它邻居的同一个 θ。梯子按每个水平重走：惩罚可以
   在不明显移动任何单点的情况下把曲线压平。
5. **语义校验层放行处理进 sieve**。它原先的报错句子里已经写着「h 是 (W, X, C)
   的函数」——散文早就对了，代码没跟上。

**度量**：饱和恒等式 |ATE 差| = 6.9e-15（两臂 vs 联合，n=20000）。三水平凹真值
(0, 1.0, 1.3) 取回 (0, 0.994, 1.303)。连续剂量七个水平**没有一行落在其上**，误
差全部 ≤0.004、都在 1 个标准误内，而同一份数据上直接回归把斜率读成 +1.507（真
值 +0.900）。

**第二座桥也上了曲线**，而且是不得不上：第一次提交后，一条声明了 `doubly_robust`
的曲线查询照样出数，台账上照样写着「两座桥里至少有一座落在它的 span 里」——而处理
桥根本没解。验证器抓住了（`_both_sieves_were_declared` 找不到记录），但 `estimate`
仍然产出了那个断言，不跑 `verify` 的调用方就会读到它。所以要么实现，要么当场拒绝，
不能留着。

实现比预想的简单，原因还是定理的形状：(8) 是乘着示性 `I(A=a)` 到估计器手里的，所以
`q` **本来就是一个水平一个水平**定下来的——每个水平自己一套系数，等于它在处理上自动
饱和。而 `h` 必须被**告知**怎么随水平变。两座桥在这里是不对称的，理由和它们上一条里
对称是同一个：示性是其中一个量的一部分，不是另一个的。

由此得到两条互为镜像的闸门。结局桥那侧：sieve 不提处理 → 拒绝（曲线会是平的）。处理
桥这侧：sieve **提了**处理 → 拒绝（臂内处理是常数，那些列在臂内共线，只把方程弄病态，
换不来任何形状）。两条是不同的 species 而不是一条带方向的，因为改法相反——照错的那条
去改，会把另一条弄成真的。

不对称还给出边界：臂是一组**行**，所以没有观测到的水平就没有臂。连续剂量因此只能走
结局回归——把一座拟合好的桥在某点求值，在没有观测的地方照样有定义；而逆概率加权在那
里无物可加权。这条拒绝单独成 species，并且在句子里说清楚**另一条路还开着**。

**#455 的承诺在新形状上差点静悄悄失效**：负 `q` 那条 gap 读的是 `treated`／`control`
两个键，而曲线的臂是它的水平。补上之后它报的是**最差的那一档是哪一档**、占多少、一共
几档——因为读者要判断的是「曲线上一个点坏了」还是「整条坏了」，而两臂的措辞里没有这个
问题。

**度量**（真值 0 / 1.0 / 1.3，n=200000，三水平）：

| | POR | PIPW | PDR |
|---|---|---|---|
| 两个都宽 | 0.0037 | 0.0056 | 0.0037 |
| h 的 span 窄 | 0.0714 错 | 0.0056 | **0.0052 对** |
| q 的 span 窄 | 0.0037 | 0.1405 错 | **0.0037 对** |
| 两个都窄 | 0.0714 错 | 0.1405 错 | 0.0746 错 |

——上一条为点估计立的那张表，在曲线上原样成立，包括第三行那个边界。

构造这张表本身有一个发现：**PIPW 曲线要求倾向得分离零有距离**。`q_a` 解的是
`E[q_a(Z)|W,A=a] = 1/f(A=a|W)`，`f` 一小 `1/f` 就炸，多项式 sieve 张不出这种函数。
在一个 `clip(round(·))` 出来的剂量上（尾部概率极小），q 的宽度从 3 试到 7，PIPW 的
误差始终在 0.11–0.33，而同一份数据上 POR 是 0.017。把多项 logit 与均匀分布混一个下
界（f ≥ 0.1）之后，同样的宽度 4 就把 PIPW 做到了 0.0056。这不是实现的毛病，是这条
路对数据的真实要求。

**方法论**：

- (432) 「这个方法只支持二值处理」这句话要拆成两半问：是对比需要两个水平（真
  的），还是实现只会切两刀（可以改）。一条拒绝同时盖住一个边界和一处缺失时，
  它读起来完全一样——而收窄它的前提是先有另一条species接住另一半。
- (433) 新解法与旧解法之间若存在**精确恒等式**，那就是最该钉的测试。这里是
  「设计在处理上饱和 → 联合解逐位复现两臂解」：它同时证明新路对、旧路没被改
  坏、以及两者的关系是包含而不是替代——一个数值容差断言这三件事一件也说不清。
- (434) 别拿「差得远不远」当选型理由，拿「定不定义」。逐对拟合在三水平样本上
  与联合解差不到千分之一；真正淘汰它的是连续处理下**没有一行落在被问的水平
  上**，逐对拟合无臂可拟合，而「把一座拟合好的桥在某点求值」在那里仍然有定
  义。能不能做，比做得好不好，先决。
- (435) 一个新答案形状落地时，要回头问上一条能力在它上面还成不成立。这里
  `doubly_robust` 的台账行在曲线上照写，而第二座桥没解——验证器抓住了，`estimate`
  没有。**验证器抓住 ≠ 没问题**：它证明的是闸门有效，不是产物无害，因为不是每个
  调用方都跑 verify。能力乘以形状是个笛卡尔积，新增一维就要重扫另一维。
- (436) 两条互为镜像的约束要写成两个 species，不要写成一个带方向的参数。「span 必
  须提处理」和「span 不许提处理」的修法相反，一条带方向的消息里读者要先读对方向才
  能动手——读反了就把另一条弄成真的。
- (437) 想验证「A 稳健而 B 不稳健」时，先确认在**没有任何东西出错**的那一格里 B 是
  对的。这里第一版实验的四格表里，PIPW 在控制格就已经错了 0.33，于是「h 错 q 对」
  那一格测的根本不是双稳健——它测的是两座桥都错。控制格是实验的前提，不是它的一行。

**度量**：基线 9082 → 9123（第一次提交，+41；新增 skip 是 `BridgeSide` 进了
「按设计放弃单例身份」那条参数化）→ **9241 passed / 196 skipped**（第二次提交，
第二座桥上曲线 +24）；mypy clean；`pnpm build` 通过。

### #455 一座桥没有办法对自己提出第二意见（2026-08-29）

**现象**：近端因果推断只有一个估计量。结局桥 `h` 被假设落在调用方声明的
span 里，落不进去答案就错，而且没有任何东西会发现——再多数据也逼近不到一个
不在搜索空间里的函数。后门那条路早就有三个估计量（`gformula` / `ipw` /
`aipw`），近端只有第一个。

**根因**：不是「少写了两个估计量」。按 Cui, Pu, Miao, Zhang & Tchetgen
Tchetgen 2024（JASA 119(546)）的公式先实现了一版，测出来三个估计量给的是
**同一个数**——`POR−PIPW` 在 −3.8e-10 到 2.5e-10 之间，那是代数恒等不是巧合。
真正的根因有两层：

1. `BridgeFunction` 把角色烧进了字段名（`outcome_terms` / `instrument_terms`），
   一个类型只能描述一座桥。而处理桥 `q` 和 `h` 形状完全相同、角色对调：
   `h` 活在 W 的函数里、在 Z 的矩上被检验，`q` 反过来。
2. 只加一个 `treatment_terms`（三套设计）时，`outcome_terms` 同时当 `h` 的
   span 和 `q` 的矩，于是把它调窄会**同时**弄坏两座桥——「h 错 q 对」那一半
   永远够不着。单向稳健叫不了双稳健。

**改动**：`BridgeFunction` 字段改成角色中立的 `span_terms` / `moment_terms`，
这一个类型用两次；新 `BridgeChannel` 装两座桥加一个 `estimator`。
`ProximalEstimator` 三个成员：`outcome_regression`（默认，等于原行为）、
`inverse_probability`、`doubly_robust`。「矩不少于未知数」于是只写一遍、对每
座桥各读一次，而不是照四个字段名写四遍；`_SIEVE_SIDES` 从两行变四行，表本身
就把那个对调画了出来。

**与论文的一处偏离，代价已声明**：论文的工作模型 `q = 1 + exp{...}` 对参数
非线性，验证器没有原始数据就重解不了它，信封上留不下有限充分统计量。把 (5)
两边乘 `I(A=a)·n(W,C)` 取期望，倾向得分自己消掉，剩下 `E[I(A=a)q_a n] = E[n]`
——对参数线性的 sieve 下这是线性系统 `M t = n̄`，`M` 是一个有限交叉矩。代价：
指数形式保证 `q > 1`（它是倒数概率），线性形式不保证，实测分配机制弯曲时有
31% 的行 `q < 0`；这个比例记在信封上当诊断量。论文的局部有效性是对它的工作
模型证的，这里不声称继承。

**新门**：`doubly_robust` 但两座桥的设计正好对调 → 拒绝。加上「矩不少于未知
数」，那种排布把两个方程组都逼成方阵，两个方阵解出同一个数，保险费付了保额
是零。测试不是拿容差钉的，是拿**性质**钉的：把两座桥的惩罚各降三个数量级，
三个估计量之间的差也降三个数量级——那是一个恒等式透过正则化在显形，两个都
相合但不同的估计量不会这样。

**度量**（真值 1.5，n=12000）：

| | POR | PIPW | PDR |
|---|---|---|---|
| h 的 span 太窄 | 错 | 对 | **对** |
| q 的 span 太窄 | 对 | 错 | **对** |
| 两个都窄 | 错 | 错 | **错** |

第三行是重点，也是 ledger 上写着的话：双稳健不是安全网，两座桥都错时它照样
错，而且不会告诉你。`doubly_robust` 的 ledger 上**没有**两条单独的 span 行，
只有并模型那一条——列出两条会是在描述一个更严格的估计量。

**标准误：宁可没有，也不给另一个估计量的**。三个估计量里只有
`outcome_regression` 报解析标准误，另外两个信封上**没有这个键**——不是 null，
是没有（`test_there_is_one_way_to_say_there_is_none` 盯着这个区别）。不是没
写：先按影响函数的插入式方差写了一版，再拿 400 次重抽样的样本标准差去量它，
两座桥都对时比值 0.966，一座桥错时 0.785——而一座桥错正是双稳健唯一被需要的
场合。Neyman 正交只在两个模型的**交**上成立，插入式方差于是恰好在它有用的地
方最不可信。bootstrap 没有这个毛病：两种情形下 SE 与抽样标准差之比都是
1.038–1.041，PDR 的覆盖率 97.5% / 92.5%。所以不确定性交给 bootstrap，解析标
准误缺席——而缺席在信封上是看得见的，不是一个悄悄变成 0 的数。

**新 gap `treatment_bridge_leaves_its_range`**：上面那处偏离的代价，报出来而
不是吞掉。拟合出的 `q` 在任一臂上有超过 0.5% 的行小于零就立案。它是
INTERPRETATION 级而不是 POINT_ESTIMATE 级：数照样出得来（走双稳健时甚至不因
此变差），坏掉的是「把逆概率加权读成一个平均」——一行上 `q` 为负，就是给结局
的平均贡献一个负权重。它也不是「再去收点数据」那类缺口：span 是声明不是估
计，多少行都修不好它，两条出路是把处理桥加宽，或者读双稳健那个数（它不单靠
这座桥做除法，而且已经算在信封上了）。

**方法论**：

- (427) 三个估计量给出同一个数时，先问它们是不是同一个估计量。差值随惩罚
  线性缩小＝代数恒等；差值不随惩罚变＝两个不同的相合估计量。容差分不清这两
  件事，性质可以。
- (428) 「双稳健」要求两个方向都能构造出反例。只能构造一个方向的，是单稳健
  换了个名字——而能不能构造，是数据结构决定的，不是估计量决定的：共用一套
  设计时，那个方向在算术上不存在。
- (429) 选算法时问「验证器读得到什么」。论文的工作模型非线性时，换一个对参
  数线性、张成同一类函数的形式，比放弃可验证性划算——但代价（这里是 q 的正
  性）要当场说出来并记在信封上，不能默默吃掉。
- (430) 渲染层不许用前缀拼字段名。拼出来的键在任何模块里都不出现，
  `test_no_part_of_a_block_is_silent` 这类静态闸门看不见它，schema、生产者、
  读者三边就会在无声中漂开。要么把键写全，要么让表把它们列出来。
- (431) 「插入式方差在两个模型的交上等于有效方差」这句话反过来读，是「它在交
  之外不可信」——而交之外正是双稳健被造出来对付的地方。一个估计量的稳健性边
  界，和它那条方差公式的可信边界，可能是同一条边界的两侧。量一下就知道该报
  哪个（这里是解析 0.966 / 0.785 对 bootstrap 1.04 / 1.04），别按公式好不好
  看来选。

**度量**：基线 9011 → 9057（第一次提交，双稳健 +24，其余为既有文件随命名迁
移）→ **9082 passed / 195 skipped**（第二次提交，标准误与出界 gap +25）；mypy
clean；`pnpm build` 通过。

### #454 一个混杂源很少只有一道影子，而设计矩阵只装得下一列（2026-08-29）

**现象**（五层核实过）：一份研究拿骨密度和握力两个 negative control 来约束「衰弱」这个未观测混杂，Themis 只能用其中一个——`estimate_bridge` 的签名是单个 `zcol`／单个 `wcol`，`ProximalEffectQuery` 的两个 proxy 字段各是一个 `Atom`，schema 里各是一个 atom，验证器的 `d`／`m` 从两张单独的 basis 记录上读。「按年龄性别分层、层内再跑近端」同样无处可写：`covariate` 在整条近端通道上零命中。

**根因假设：三条缺口是同一个缺失的对象——没有「一个 sieve 的设计由若干项组成」。** 设计矩阵是按「一列一个基」建的（`design_a = a(Z)`、`design_b = b(W)`），所以多个 W、多个 Z、观测协变量 C 各自都没有位置，而它们要的是同一件东西。

**为什么是根因不是表象**：按表象修就是给 `estimate_bridge` 加 `zcols: list[str]`，然后 `dimension` 立刻说不清是「每列几个基」还是「总共几列」，而 `instrument_dimension >= dimension` 这条欠定判据正架在这个数上——它会**静悄悄地失效**，因为两侧的宽度不再是调用方报的那两个整数。缺的不是几个参数，是一个可声明的结构。

**做了什么**

1. **`SieveTerm` / `SieveFactor` 进 AST**。一个 factor 是「一个变量 + 一个基族 + 一个维数」，一个 term 是若干 factor 的**张量积**，一侧的设计是若干 term 的**和**。`BridgeFunction{outcome_terms, instrument_terms, ridge?}`。
2. **`dimension` 与 `instrument_dimension` 两个字段被删掉**，改由 term 数出来（`width_of`：一个共享常数 + 每项宽度减一）。欠定判据因此**更硬**：它比的是两个设计本身，不再是调用方在设计旁边另写的两个整数——那两个数可以跟设计不一致，而只有设计在建矩阵。
3. **项内张量积不是排场，是那个请求本身**。协变量**加进** span 只能把整条 bridge 上下平移；**乘进**去才让 bridge 在每个层内是代理的不同函数——「分层之后在层内跑近端」要的是后者。文献主流（P2SLS，Park–Richardson–Tchetgen Tchetgen）把 W／Z／C 线性可加放进两阶段，那一档做不到这件事。
4. **两个 proxy 角色变成集合，`covariates` 新增**。识别层：model (f) 的判据是 d-分离，而**固定条件集下集合的 d-分离等价于逐对的 d-分离**，所以是同一条判据读更多对，不是第二条判据；协变量进每一条分离的条件集（W ⊥ (Z,X) | (U,C)、Z ⊥ Y | (U,X,C)、{U,C} 阻断所有后门），并且 **C 不得是 X 的后代**（后门条件 (i) 用在调用方加的那个集合上）。
5. **每一项都被去掉自己那份常数，整份设计只留一个**。这里的每个基族自己就张成常数（幂从 t⁰ 起、hat 函数处处求和为 1），所以两项并排就把常数放进去两次，`AᵀA` 在任何数据说话之前就奇异——一个关于**排布**的事实，会穿着关于**样本**的事实的衣服到达。
6. **五道新闸口在门口**（`proximal_sieve_design`）：一侧的项只能由这一侧的 proxy 与协变量建；声明了却没有任何项用到的 proxy 被拒；协变量在 bridge 里占的列数不得多于它在矩条件那一侧占的（(b1) 是**在给定 C 之下**成立的等式）；离散通道两侧各只收一个 proxy、且不收协变量（公式 (5) 求逆的是一个 k×k 通道）。全部只比同一份程序的两处声明，不碰数据。
7. **验证器按项按 factor 逐个比**：变量、族、维数，顺序在内。只比宽度不够——同样的列数可以来自展开另一个代理、或同一个代理换一个族，那是**关于 bridge 落在哪里的另一个假设**，不是同一个假设的另一种写法。

**闸口**（19 条，新文件 `tests/test_a_source_of_confounding_rarely_has_one_shadow.py`）：两个 oracle 都是 bridge 有闭式解的数据。**一**：`u=(u1,u2)` 两部分各有自己的代理，`h = βx + (d1/b1)w1 + (d2/b2)w2` 精确成立，而任何只含 `w1` 的函数都不是 bridge（`z2` 会在 `E[U1|Z,X]` 不动的情况下推动 `E[U2|Z,X]`）——同一份数据、同一张图、**同一组工具**，只用一个 negative control 得 2.9489491763332080，两个都用得 1.4826959073234150（真值 1.5）。**二**：代理对 u 的载荷在两层里不同（0.5 / 2.0），交互设计得 1.4999599648355075，可加设计得 0.9721398100996074。

**第二个 oracle 我第一次写错了，是跑出来才知道的**：最初只让载荷随层变、处理分配不随层变，结果**可加设计也落在真值 2% 以内**——两臂的层构成相同，错设的偏差在相减时抵掉了。让分配强度也随层变（0.3 / 2.5）之后差距才出现。这条写进了 fixture 的 docstring：交互买到的东西只在**两臂层构成不同**时才看得见，而那正是分层问题值得问的地方。

**同一刀的后半：基函数族从两个加到五个**（`cubic_spline` / `fourier` / `hermite`，新文件 `tests/test_a_basis_nobody_would_choose_is_not_a_choice.py` 31 条）。加成员本身不是前沿，**但一个没人有理由去选的成员是个名字不是选项**，所以每一个都得先量出它买到了什么：

- **`hermite` 买的是条件数**，不是新的 span——它和幂次张成同一个空间。归一化的 Hermite 多项式在标准正态权下正交，所以钟形的一列给出接近单位阵的 Gram，而原始幂次给的是 Vandermonde。实测 d=12：幂次 1.514e+11、Hermite 3.200e+04（差七个数量级）；同一份数据同一宽度，幂次被 `singular_design` 拒答，Hermite 照样给出数。**不适定问题里条件数就是那个先耗尽的东西**，这不是整洁性论证。
- **`fourier` 买的是列数**。声明它就是断言这个变量是周期的（角度、时刻、季节）。实测周期代理上 d=3：傅里叶 1.4904、幂次 1.7417（真值 1.5）；d=5 之后两者收敛。同样的 span 用更少的列，换来的就是更好求逆的那个矩阵。
- **`cubic_spline` 是一次交换，不是一次升级**——这条是量完之后改的。原本写的是「同维数下样条比 hat 花得更值」，两个方向都测过之后才成立的说法是：光滑目标上样条的最优逼近误差是 hat 的三分之一以下（d=10：0.0063 vs 0.0393），**折点目标 `|t|` 上反过来 hat 更近**（0.0190 vs 0.0227），而且 hat 的条件数一直好一个数量级（约 2e1 vs 3e2）。所以它是「相信 bridge 光滑」时的族，是「bridge 有个角」时的错族——词表把它说成严格更好，就是在邀请第二种情形用第一种的族去答。
- **五个族共同的不变量被逐个钉住**：每一族都张成常数，且**常数在第 0 列上的系数非零**（实测五族系数都恰好 1.0，残差 ~1e-14）。设计矩阵每项去掉自己那份常数、整份只留一个，这一步只有在被去掉的那列能由「其余列 + 常数」复原时才是去重而不是改 span。
- `cubic_spline` 至少要 4 个基函数（钳位节点向量里放不下三次），这条最小宽度写在 `SIEVE_MINIMUM_DIMENSION` 里由门口检查，反例已构造；其余四族在 d=2 上照常工作，这条也测了——免得那道闸口越界。

**度量**：基线 8934 → **9011 passed / 194 skipped**（设计矩阵 +43，基函数族 +34）；mypy clean；`pnpm build` 通过。

**声明的取舍（两条）**：

- **离散通道明确拒绝多代理与协变量**，而不是悄悄用第一个。多个离散代理要交叉分类成一个复合代理再折叠，协变量要层内各求逆一次再平均——两件都没实现，所以说出来并指向 bridge_function。代价：一个手上有两个离散代理的调用方，这一刀之后仍然只能用一个。
- **项内张量积让维数相乘**，两个 d=5 的变量做交互就是 25 列，而不适定性随维数迅速变坏。没有加任何「自动降维」：宽度是调用方声明出来的，`instrument_dimension` 与条件数会如实报，把它调小是调用方的决定而不是估计器替他做的简化。

**方法论沉淀**：

(422) **三条看起来独立的缺口，先问它们缺的是不是同一个对象。** 多个 W、多个 Z、协变量 C，分开看是三件事，合起来是「设计矩阵不是一份可声明的结构」这一件。逐条修会得到三套互不认识的参数；先把那个对象造出来，三条一起没了，而且第四条（交互）是白送的。

(423) **一个数如果既能被声明又能被数出来，就别让它被声明。** `dimension` 与 `instrument_dimension` 原先由调用方在设计旁边写出来，那等于给了同一件事两份记录，而只有一份在建矩阵。删掉声明、改成数出来，欠定判据反而变严——它现在校的是设计，不是调用方对设计的描述。

(424) **构造 oracle 时要先跑一遍「它该失败的那个设计」。** 我写的第一版分层数据里，可加设计也答对了——因为两臂的层构成一样，错设的偏差在相减时抵掉。**一个断言「A 比 B 好」的测试，必须先看见 B 真的不行**；看不见就说明数据没造出那个差别，而不是差别不存在。

(425) **往封闭词表里加成员，先量出它买到什么，再写它的理由。** 一个没人有理由去选的成员是个名字不是选项。而量的时候要**两个方向都量**：我给 `cubic_spline` 写的理由是「同维数下比 hat 更值」，测完才知道光滑目标上确实如此、折点目标上反过来、条件数上一直更差——它是一次交换。**只量了自己期待的那一侧，就会把一次交换写成一次升级**，而词表里一个被说成严格更好的成员，会把另一半情形也吸过去。

(426) **一族新基函数先检查它有没有破坏别人依赖的那个不变量。** 设计矩阵按项去常数这一步，依赖的是「常数在第 0 列上系数非零」——这不是各族自己的性质清单里会写的东西，而是**别处的一段代码悄悄依赖着的**。五个族逐个测这一条，比在每一族的实现里各写一句注释更牢：它是一条跨族的约束，就该在能看见所有族的地方检查。

### #453 拒绝一份程序的那扇门，从来没有人问过它说给谁听（2026-08-29）

**现象**：一份把 `given` 写成非父节点的程序，在网页上被拒。读者拿到两句话：一句 stage 句子「这份程序没能跑完」，中英文都有；一句 `diagnostic`，只有英文——而**只有后者说清了出什么事**。二十种「程序写错了」在这扇门后面是二十句不同的话，走出门时挤进同一个字段里的一坨英文。同一时刻近端识别那边也一样：`data_conditions` 是估计量上一个已经渲染好的字符串，`ProximalNotIdentified.reason` 是拒绝时当场拼好的一句英文。

**根因假设：这两条通道运走的是句子本身，而不是句子的名字。** 每个 raise 点当场写死一个 f-string，每个字段装的是渲染完的结果。而知道读者说什么语言的那一层在三层之外。**一句已经选好语言的话，下游没有任何人能再替它选一次**——`failure.py` 能做的只剩把它当 `diagnostic` 转出去，那正是它做的。

**为什么是根因不是表象**：当表象修，就是在 `failure.py` 里按 `str(exc)` 的内容猜是哪一种错、再查一张翻译表。那张表要跟二十个 raise 点手工对齐，第一次改措辞就静悄悄错位。缺的不是翻译，是**这二十种错各自没有名字**——`refusals.py` 早就给估计器的拒绝做过这件事（species + 双语模板 + 具名槽位），输入层这扇门只是从来没被问过同一个问题。

**做了什么**

1. **`Malformed` 词表进 `semantic_validator.py`**，二十个成员，每个是一整句带洞的双语话。`SemanticError(species, **details)`：`language.halve` 把事实按「渲染一次的值」和「随读者变的词」分两半，`assemble` 组句，`capped` 封顶。`failure.py` 多的是三行 `elif`——跟估计器拒绝那一支同一个形状，不是第二种约定。
2. **顺手把两个读者分开**：原先走 `SemanticError` 的五条派发不变量（未知 query kind、未知 proximal channel kind、未知 statement kind、未知图级检查、未知语义检查）改成 `TypeError` / `KeyError`。它们说给维护派发表的人听，不说给写程序的人听；**一个读者面词表里出现「未知 query kind」，就是这个词表把两个读者搞混了**。
3. **`_LATENT_EXPOSURE` 的第二列改名**：原先是 `(verdict, why)`，`why` 被插进拒绝句里。现在是 `Exposure(verdict, evidence)`——`evidence` 是「这个 kind 为什么判成这样」的论证，写给维护这张表的人，留在表里不出门。
4. **内部引用从读者的句子里挪进代码注释**：`wall.md iter 150`、`Phase 5 §T / T1`、几处 charter 章节号。读者手上有 `themis.estimate(...)`，没有这个仓库。
5. **`proximal_identify.py`：`reason` 字符串 → `language.Statement`**，三张词表（`Role` 五个角色、`Criterion` 八条判据、`DataCondition` 三个条件），每条判据自己是一整句带洞的双语话。`gaps.py` 与 `refusals.py` 的外层模板因此**各少了一个 `{criterion}` 洞**——一句话装进另一句话，`halve` 本来就认得这种值。
6. **`data_conditions`：一个渲染好的字符串 → 封闭词表的 token 数组**，schema 里是枚举，读者那一头用 `language.listed` 按各自语言的标点连起来。`serialization.py` 的 `_value_to_json` 同时接 `(tuple, list)`——原先那句「序列化器接不了集合」的注释比通用 `value_tuple` 回退还老。
7. **同名类让一条普查误报**：加了 `Role` 之后 `test_no_module_asks_an_envelope_vocabulary_for_its_identity` 拿四个**完全正确**的比较来失败——它按裸类名匹配，而它自己的 docstring 说界线画在基类上。改成 `_bound_here()`：名字在被扫的那个模块里解析，解析不出来就判失败（fail closed），并补了反例测试。

**闸口**：二十条钉在英文措辞上的断言改成钉 species——`raised.value.species is Malformed.X`，槽位另钉 `details`。这不是把测试改得能过，**这是同一件事的度量**：改之前「哪一种拒绝触发了」只能从一句英文里捞回来，而一条读措辞的断言分不出「改了措辞」和「改了规则」；改之后这两件事在两个地方，动哪个都各自有人喊。三条断言因此变强：`test_a_loop_across_two_time_steps_is_refused` 原先只看英文里有没有「这样写不需要工具变量」，现在中英文各看一遍；`test_the_rejection_message_includes_actionable_hints` 原先只保证英文读者拿得到三条出路，现在两种读者都拿得到；潜混杂那道闸口新加一条**反例**——维护者那半句 `evidence` 必须**不出现**在读者的句子里，这正是那次拆分存在的理由。

**度量**：基线 8785 → **8934 passed / 194 skipped**；`STILL_ONE_LANGUAGE` 两处清零（`semantic_validator.py` 29→0，`proximal_identify.py` 11→0），#451 声明的最后一条取舍到此付清；mypy clean；`pnpm build` 通过。端到端实测：同一份 M-bias 程序，`failure.payload` 出来的 `words` 中英文各写出完整的一句，`slots` 是 `{"index": 3, "query": "q", "atoms": ["m"]}`。

**声明的取舍（两条）**：

- **内部引用从读者句子里删掉了**。代价是：一个在浏览器里读到这句话、同时又手握仓库的人，少了一条直达 `wall.md iter 150` 的线索。换来的是那句话对**没有仓库的人**不再是噪声，而第三条出路真正给出的东西（`themis.estimate(...) 加原始数据`）是他做得到的动作。引用挪到了成员上方的注释里，没有丢。
- **五条派发不变量改抛内建异常**，捕 `SemanticError` 的调用方在这五处会看到别的类型。这正是要的效果（它们本来就不是拒绝），但它是一次行为变更，写在这里而不是留给下一个人撞上。

**方法论沉淀**：

(418) **一句已经选好语言的话，下游没有人能再替它选。** 凡是「产生它的地方」和「知道读者是谁的地方」隔着若干层，中间运的就必须是**名字加事实**，不能是句子。判断一条通道有没有这个病，不看它有没有翻译，看它**运的是什么**：只要字段里装的是渲染完的结果，就已经替所有读者做完了决定。

(419) **一个词表装不下两个读者。** 每个 raise 点先问一句「这话说给谁听」：说给维护这段代码的人，就抛内建异常，永远不进读者面词表；说给写程序的人，才配一个 species。混在一起的代价不是难看——是那个读者面词表会开始收纳「未知 query kind」这种成员，而它一旦进去，翻译、渲染、登记门就都要为它认真做一遍。

(420) **断言钉在措辞上，就分不出改措辞和改规则。** 有身份可钉的时候钉身份，措辞归词表——词表那一头可以**把每种语言一次全查一遍**，而一条 `match="..."` 只查得动作者当时在想的那一种。这也是为什么这类改动会自然地让断言变强：不是顺手加的，是原先那种写法根本表达不了。

(421) **按名字做的普查，会把别处同名的东西也算进来。** 一条扫「哪些类继承了某个基类」的规则，如果实现成匹配裸类名，另一个模块里一个同名的类就会让它报出四个完全正确的比较。普查要匹配**名字解析出来的那个东西**，解析不出来就判失败——否则它的误报会精确地出现在「有人新加了一个东西」的那一刻，也就是最容易被当成新代码有问题的那一刻。

### #451 连续代理下要解的不是矩阵，是一个不适定反问题——而正则化是没人测量过的输入（2026-08-29）

**现象**：一份 Miao 模型 (f) 的程序，两个代理是连续的（`scale: "continuous"`），Themis 走进近端通道，看见三千多个互不相同的浮点数，判定「代理层数 ≠ 声明的 k」，然后交出 `proxy_coarsening_undeclared`——请用户说清楚这三千个浮点数里哪些是同一个状态。**这件差事跑不了，而且它是错的差事**：连续版本的近端识别根本不给代理分箱，它解的是一个 bridge function。同一份数据上，朴素 OLS 给 2.1993982425483214，真值是 1.5。

**根因假设：`latent_cardinality` 是 query 的必填字段，而它一个字段扛了两件事。** 一是「U 被假设有几个状态」，二是「要被求逆的是一个矩阵」。这两件事在离散制度下重合，在连续制度下分开——连续制度里 U 的基数根本不被假设。所以只要这个字段是必填的，任何近端查询都只有一条路可走，而那条路的入口就摆着一次分箱。

**为什么是根因不是表象**：当表象修，就是在派发层加一句「如果代理是连续的，绕过基数检查」——绕过之后没有东西可以跑，因为矩阵制度是唯一实现的算法。缺的不是一个 if，是 query 里那个**说不出「连续制度」的字段**。改成 `channel: DiscreteChannel | BridgeFunction` 的判别联合之后，非法状态（连续代理 + 一个 k）不再可表示，而两个制度各自带齐自己的参数。

**做了什么**

1. **`channel` 判别联合进 AST**，`latent_cardinality` 从 query 必填字段里删掉（横跨 27 个文件 81 处的破坏性变更）。`DiscreteChannel{latent_cardinality, proxy_coarsening?}` 和 `BridgeFunction{basis, dimension, instrument_dimension, ridge?}` 两支，schema 里用 `kind` 做判别。`instrument_dimension < dimension` **在语义校验就被拒**——那不是病态求解，是欠定方程组，而欠定是声明本身的性质，跟数据无关。
2. **`themis/estimation/proximal_bridge.py`：sieve 两阶段最小二乘**（Deaner 2018 arXiv:1807.02667；Cui, Pu, Miao, Zhang & Tchetgen Tchetgen 2024 *JASA* 119(546)）。逐臂算 `S_AA=AᵀA/n`、`S_AB=AᵀB/n`、`S_Ay=Aᵀy/n`，得 `G=S_ABᵀS_AA⁻¹S_AB`、`c=S_ABᵀS_AA⁻¹S_Ay`，解 `θ_λ=(G+λI)⁻¹c`，再把 `w̄ᵀθ_x` 在**全样本**上平均。
3. **为什么是 sieve 不是 RKHS**（KPV / PMMR，Mastouri et al. 2021）：RKHS 的解活在由 n×n Gram 矩阵定义的空间里，**信封上带不走任何有限的东西**，第二份实现没有原始数据就复算不出这个数。sieve 每臂只留六个小的交叉矩量块，而验证器要的正是这个。
4. **正则化被声明、被归属、被复算、被把关**。声明：`ridge` 是 query 的一个字段。归属：台账里要么是 `regularisation_lambda_chosen_by_the_caller`（`caller_chose`），要么是 `regularisation_lambda_defaulted_by_the_estimator`（`default`）——**这两个 id 是两个人**。复算：一条跨八个数量级的四级罚项阶梯随答案一起走，验证器从矩量重解每一级。把关：答案随罚项动得比抽样噪声还大时，`regularisation_is_moving_the_answer` 说出来。
5. **判据是「弯折」不是「谱度」**：`|point − 最轻的那一级可解的解|` 与标准误比，外加「有任何一级解不出来」。先写的是谱度（阶梯上最大最小之差），实测把一个稳定的答案冤枉了——`piecewise_linear` d=3 谱度 0.092 而弯折 1.3e-5。**是跑出来的，不是想出来的。**
6. **`regularisation_is_moving_the_answer` 是 caveat 不是 errand**（`QUALIFIES_THE_ANSWER`，`GapBlocks.INTERPRETATION`）。数**算出来了**、而且可复算；受损的是「把它当成一个关于世界的事实而不是关于 λ 的事实」来读。这跟同一个估计器另一制度的 `proxy_coarsening_undeclared` 正好互为镜像：那边什么都没算出来、缺的是一句声明；这边全算出来了、其中一个输入不是任何人的测量。
7. **台账的 `estimator_assumption` 行放宽到 `parameter × default`，并带上自己的检查**。放宽是有理由的：当初把 `functional_form` 从这一行收掉，是因为**一个形状的作者读不出它的 id**；一个数值输入的作者读得出来，因为它有两个 id。所以同时加了 `_DEFAULT_IS_RECORDED_BY` 与逐 id 的 `_CHOICE_IS_RECORDED_BY`（未知 id 一律拒），两个方向都被钉住。

**闸口**（29 条，新文件 `tests/test_a_penalty_that_makes_an_equation_solvable_is_a_choice.py`）：oracle 是一份 bridge 有闭式解的数据——`U~N(0,1)` 不可观测，`Z=1.2U+ε`、`W=0.9U+ε`、`X~Bernoulli(logistic(0.8U))`、`Y=1.5X+U+ε`，此时 `h(w,x)=βx+(τ/γ)w` 精确成立、w 项在两臂之间抵消，所以真值就是 β 而不是这份数据碰巧落在的地方。默认罚项下 λ=7.35e-07、点 1.4568089023822755（朴素 OLS 2.1993982425483214）；换一族基（分段线性 d=3）落到 1.4701883508621132；λ=0.5 时点掉到 1.2141281752579725，缺口以 important 出现。反例逐条构造并逐条验：伪造 point、伪造某一臂的 do-概率、挪 `s_ay`（只动 c，解那一步抓到）、挪 `s_ab`（动 G，尺度恒等式提前一步抓到）、`s_aa` 非对称、换一份样本、换基函数族、换 λ、翻转 `ridge_was_declared`、**把阶梯里的某一级改写成看起来更稳**、把某一级谎报成解不出来、以及整条阶梯换一套自己的 fraction。最后一条是这里最锋利的：信封上其余每个数都是真的，唯一被动的是「更轻的罚项会怎么说」——也就是「这个数不依赖 λ」这句话本身，只有重解那一级才看得见。

**度量**：基线 8708 → **8785 passed / 190 skipped**（+29 新闸口，其余是登记门自动收编新成员：词表两张、schema 枚举六处、GapKind 普查、DataGap 与 Statement 站点扫描）；mypy clean；`pnpm build` 通过。

**声明的取舍（五条）**：

- **拒了 RKHS 选了 sieve**，代价是「bridge 落在声明的张成空间之外时，更多数据不会更好地逼近它」——这条假设进台账（`the_bridge_lies_in_the_span_of_the_declared_sieve`）而不是被溶解掉。换来的是这个数可以被第二份实现**在没有原始数据的情况下**重算出来，而这正是 Themis 的护城河所在。
- **`latent_cardinality` 不再是 query 的必填字段**，这是一次破坏性 AST 变更，横跨 27 个文件 81 处。换来的是非法状态不可表示；成本不是选型依据。
- **完备性不可检验，所以台账上是一条打了「未核」的线**（Canay, Santos & Shaikh 2013, *Econometrica* 81(6)）。条件数只是它的数值影子，是必要后果，**永远不是那个条件本身**——这一句写在产生它的地方，免得下一个人把条件数当成检验。
- **只有 outcome bridge，没有 treatment bridge，也没有双稳健的近端估计量**（Cui et al. 2024 的另一半）。两个基函数族、离散二元处理。
- **`STILL_ONE_LANGUAGE` 两处上涨**：`semantic_validator.py` 28→29（欠定 sieve 的拒绝走 `SemanticError`，那条通道整体没有双语渠道），`proximal_identify.py` 9→11（`data_conditions` 是估计量上的一个已渲染字符串，同样没有双语渠道）。两处都是加进既有的债，不是开第二种约定；付清它们各自需要把那条通道整体切成词表。

**方法论沉淀**：

(413) **不适定不等于数据不够。** 一个反问题的逆算子会放大手上任何数据里的噪声，所以「再多测一点」不是出路，稳定化才是——而稳定化是一个**没有人测量过的输入**。凡是这种输入，都要走同一条四段路：声明（它是一个字段）、归属（台账说是谁选的）、复算（换几个值再解一遍，结果随答案走）、把关（动得比噪声大就说出来）。缺任何一段，这个数看起来都跟一个没有输入的数一模一样。

(414) **挑判据先构造它该保持沉默的那个例子。** 「阶梯上最大最小之差」听起来就是要量的东西，而它会把一个稳定的答案判成不稳定——只要最极端的那一级远在任何人会用的范围之外。真正要问的是「答案在**这一级**和最轻的那一级之间弯了多少」，再拿它跟抽样噪声比。判据错了不会报错，只会一直响；**先跑一遍它该沉默的场景**，比读它的定义更快。

(415) **能被独立复算的，才配上信封。** 两个算法可以识别同一个量而在这件事上完全不同：sieve 在信封上留下六个小矩阵，第二份实现拿着它们、不碰原始数据就能重算出这个数；RKHS 的解活在由 n×n Gram 矩阵定义的空间里，留不下任何有限的东西。**验证器读得到什么，是选算法时的一个坐标轴**，不是实现完之后再想的事。

(416) **放宽一条许可，必须同一刀加上它自己的检查。** 把 `(parameter, default)` 加进台账的可写集合，等于说「这个组合有人可以写」；不同时说清楚**是谁、按什么记录**，放宽的实际含义就是「谁都能写」。判断该不该放宽也有一个干脆的问法：当初为什么收窄？如果收窄的理由（一个形状的作者读不出它的 id）在新情形下不成立（一个数值输入的作者读得出来），那就不是例外，是同一条原则的另一面。

(417) **算出来的名字，任何普查都看不见。** 规则名写成三元表达式，`DerivationStep(rule=...)` 的字面量普查就扫不到它——而下游的词表会因此报告「这两条词条没有人写」，一个看起来完全无关的失败。凡是有普查在读的地方，**分支要分到调用点上去**，而不是分在参数里。

### #450 「互为因果」只是一句回显给读者的话——而它是联立性，Themis 有整套 IV（2026-08-29）

**现象**：用户说「价格影响需求、需求也影响价格」，NL 层把这句写进 `ambiguities` 的自由文本，kernel 照常在 DAG 上找后门集、给出一个数。那个数是**单方程的 OLS 系数**（1.5767），真值是 1.5；同一张图上工具变量给的是 1.5053。Themis 不只是答错，它答得**有依据、有推导链、有审计**——错的那一层从来没有被问到过。

**根因假设：缺的不是 IV，是 AST 里没有一种「互为因果」能被路由层看见的形状。** `ambiguities` 是一串句子，而**句子不带原子**；路由层认的是 `StructuralFacts`，结构事实是从语句里的原子建出来的。所以这句话无论写得多清楚，都到不了任何一个 `applies_when`。缺的是一个 `Statement` 种类。

**为什么是根因不是表象**：把它当表象修，得到的是「在 NL prompt 里叫 LLM 遇到互为因果就别用 backdoor」——一条靠 LLM 记住的规则，而 kernel 依然无法拒绝一份声明了环的程序。一旦它是语句，剩下的全是 Themis 已经有的东西：Haavelmo 1943 把联立方程组约化成 Wald 比，Spirtes 1995（UAI-11）给出线性联立 SEM 上 d-分离仍然有效的许可，两者合起来就是「IV 通道原样可用」的证明。**不是新算法，是让已有的算法能被触发。**

**做了什么**

1. **`FeedbackLoop` 进 AST**（`kind: "feedback"`，两端无序，可带 `forall`）。它**不加边**——加边就是往 DAG 里塞一个 DAG 装不下的东西；图投影里两端只作孤立节点出现，环本身活在 `StructuralFacts.feedback` 里。语义校验拒两种写法：两端是同一个原子（那是自环，不是环），以及两端 `time_index` 不同（那不是同时性，是一条普通的滞后边，**不需要工具变量**）。
2. **`feedback` 不是 `bidirected` 的同义词**，尽管两者对「处理是否外生」的后果一样。折进去会**悄悄过度识别**：双向弧下 front-door 判据成立，环下不成立（X→Y 路径上的每个中介都落在环里）。两个种类分开留，路由分开。
3. **触达判据（保守，且写明是保守的）**：一个声明的环触达本次估计量，当且仅当它任一端能影响 x 或 y——在**加了环边的图**上按普通可达性算，**不是在 do-剪断的图上**。剪断后的判据会放行 X⇄Y，也就是所有人都同意坏掉的那一个：损害落在调整公式读的**观测联合分布**上，不在干预分布上。
4. **只有环恰好落在 {处理, 结果} 上才给数**（`reduction: "simultaneous_equations"`）。工具搜索直接在 `G + {X↔Y}` 上跑，和在 `G + {Y→X}` 上跑给出同一批候选：排除性上 Y 是路径**端点**、永远不是对撞点，所以 X 处的箭头朝哪没有区别；相关性上，一个只能经 Y 到达 X 的 Z 本来就过不了排除性。其余任何形状**只给拒绝**——两方程的代数是关于两个方程的。
5. **拒绝返回 `QueryResult` 而不是 `_Attempt(missing=...)`**，这是这一刀里最要紧的一行：返回 missing 会让级联继续往下走，backdoor 接住，给出的正好是要修掉的那个错数。
6. **撤回许可要落在发出去的那份答案上**：估计层会**覆写** `result["derivation"]`，所以只在识别层加一步 `s_loop` 等于没加——那一步在最终 envelope 上根本不存在。`_build_iv_numeric_derivation_dict` 现在带 `loop=`，验证器规则 `feedback_loop_withdraws_adjustment` 重新推一遍触达再放行。
7. **两条 need、三条路由、五句话，中英双语**：没有工具时给 `missing_iv_candidate`——这是它**第一次有生产者**（从前它读的是「一个失败的 IV 推导步」，而 kernel 只写成功的步，所以它永远不会被产出）；环从别处触达时给新的 `feedback_loop_reaches_the_estimand`。三条路由：给一个工具、把环在时间上解开（更强，且不需要工具）、撤回这条声明。

**闸口**（15 条，新文件）：oracle 是一份 β=1.5 的联立数据，**同一份数据、同一张图，差别只有一句 `feedback`**——不声明是 1.5766951193223655（OLS/backdoor），声明后是 1.5053097921277052（`iv_2sls`），后者逐位等于手算的 Wald 比 Cov(Z,Y)/Cov(Z,X)。反例逐条构造：把 `feedback` 当成 `bidirected` 时 front-door 仍然成立（所以两者不能合并）；环在旁边、碰不到估计量时查询原样通过；环在 X→Y 路径上但不在两端时**只能拒绝**；两端时间戳不同 / 两端同一个原子在语义校验就被拒；验证器两条（伪造撤回、环不在上下文里）。

**度量**：基线 8642 → **8708 passed / 189 skipped**（+15 新闸口，+51 是登记门自动收编新成员：路由表、策略表、blocks 家族、词表五张、schema 枚举、DataGap 站点扫描）；mypy clean。

**声明的取舍（三条）**：

- **触达判据是保守的：「可能已经污染」不等于「污染了」。** 两个协变量之间的环、或者处理与它一个死胡同子节点之间的环，处理仍然外生、调整的答案仍然对，而这条规则照样把它撤掉。代价写在 docstring 里；对冲是三条路由里有一条正是「撤回这条声明」。
- **只有 {处理, 结果} 那一种形状给数**，其余触达形状一律拒绝。放弃的是「给一个大概的数」；换来的是不会在一个**可能根本没有解**的循环 SCM 上（Bongers, Forré, Peters & Mooij 2021, *Ann. Statist.* 49(5):2885–2915）报一个只有 DAG 才定义得出的量。
- **`STILL_ONE_LANGUAGE` 里 `semantic_validator.py` 从 26 加到 28**：两条新的 `feedback` 拒绝走 `SemanticError`，那条通道整体没有双语渠道。不把它们推迟到估计层去说，是因为推迟等于接受一份格式错误的程序继续往下跑。

**方法论沉淀**：

(409) **一个到不了路由层的事实，等于没有这个事实——能不能被程序看见，取决于它有没有原子。** 自由文本可以写得非常清楚，而 `applies_when` 读的是结构事实，结构事实是从语句里的原子建出来的。所以「在 prompt 里补一句提醒 LLM」和「加一个语句种类」不是同一件事的两种做法，前者根本不在同一层——**回显给读者和进入判定，是两条不相交的通路**。

(410) **两个后果相同的东西不能就此合并；要问的是它们在别处的后果一样不一样。** `feedback` 与 `bidirected` 对「处理外生性」的结论完全一致，合并看起来是化简；而 front-door 判据在一个上成立、在另一个上不成立，合并的代价是**悄悄多识别一类问题**。判据很干脆：**先去找一处两者分歧的判据，找到了就不合并。**

(411) **一个不阻断的拒绝，和没有拒绝，在输出上一模一样。** 级联式派发里，返回「我做不了」是把问题交给下一条路线，而下一条路线往往正是要修掉的那条。所以拒绝必须返回**终态**。新加一条拒绝时，要验的不是「它说了不」，是「说完之后没有别人接着答」。

(412) **识别层写进推导链的东西，估计层会覆写。** 「许可写在推导链上」这句话必须落到**发出去的那份 envelope** 上量一遍：在识别层验过、在最终结果里没有，是这类跨层改动的默认失败形态——而它不会报错，只会让验证器少查一条。

### #449 一半会无声消失的检验——学一张滞后图，和让这张图能被第二遍查（2026-08-29）

**现象**：`time_index` 在 AST 里、纵向 g-methods 在估计层、`temporal` 在识别层——**表示得了滞后图、也估计得了滞后图，就是没有一段能从时间序列里把它学出来**。`themis_discover` 只做同期骨架（PC/GES），一个手上有面板数据、还不知道谁领先谁的用户，在 Themis 里没有入口。

**根因假设：缺的不是「再包一个库」，是一个学出来的图不能靠重跑来检查。** 静态发现那次（borrow-list #4，Markov blanket）已经立过这条判据：把同一份数据喂给同一个搜索，复现的是它的 bug。所以能补的不是「跑 PCMCI」，是**产出一个自称拥有某个性质、而那个性质可以在没有数据的情况下被重新验算的对象**。这决定了要落的是一整条 standalone artifact 通道（producer→schema→verifier→kernel→audits→MCP），不是一个函数。

**为什么是根因不是表象**：如果只把 tigramite 的输出转成 AST，Themis 对这张图能说的话和对一个用户手写的 DAG 一样多——「你断言的」。而它明明是**算出来的**，算的过程里每一步都是一次条件独立检验，每一次检验都是一条可以被独立重做的等式。放弃这一点，等于把 Themis 唯一的护城河（形式识别 + 逐数验证）在新板块上主动关掉。

**做了什么**

1. **`themis/estimation/lagged_discovery.py`——照论文自写**（Runge 等 2019, *Science Advances* 5:eaau4996；tigramite 是 GPL，只读不 vendor）。设计矩阵是 `var@t` / `var@t-k`，**深度是 2τmax 而不是 τmax**：MCI 要以驱动变量的父集按滞后平移为条件，一个 τ' 的父节点挂在 τ 的驱动后面就落在 τ+τ'，**设计里没有的列意味着那次检验不是它自称的那次**。
2. **换掉论文的第一阶段，并且写在产物自己身上**：PC₁ 只要「某个子集」让候选独立就删，输出不欠任何可查的等式；这里用 `themis.estimation.discovery` 已有的 grow-shrink 跑到不动点（在只含过去的候选池里，Markov blanket 就是父集——没有未来的孩子可以拿来做条件，配偶进不来）。`method` 因此是枚举 `"pcmci_gs"` 而不是自由字符串。**MCI 一步没动。**
3. **产物记的是充分统计量**：Fisher-Z 偏相关是相关矩阵的纯函数，所以整张相关矩阵 + 两阶段的全部检验（父集检验 18 条、MCI 18 条，**含没检出的**）随答案一起走。第二实现可以**在没有数据的情况下**把每一条重做一遍。
4. **验证器自己重建、不读**：`columns` 布局由 `variables`+`depth` 推出来再和记录的比对；父集的不动点**硬性执行**（每个父节点在给定其余父节点后相依、每个非父节点在给定全部父节点后独立）；每一次 MCI 的条件集**从记录的父集重新推**。
5. **面板的滞后按值取、绝不跨 unit**；`discover_lagged_graph` 拒绝非整数时间列（一个滞后是几步，只有调用者知道一步是什么）、拒绝离散列（Fisher-Z 之外没有充分统计量可记）、拒绝装不下的设计宽度、拒绝自由度不够的样本。
6. **接线**：`Artifact.LAGGED_DISCOVERY` + `verify_lagged_discovery` 进 audits 表与 `themis.audit` 路由，MCP 两把工具（`themis_discover_lagged_graph` / `themis_verify_lagged_discovery`，15→17），`lagged_discovery_to_kernel_ast` 把边发成带 `time_index` 的 `cause`，`annotations.source = "discovery:pcmci_gs"`——识别层和纵向估计层直接就能接着往下走。

**闸口**（26 条，新文件）：**oracle 是一份写下来之后才去测的 VAR(2)**（`x←x₁`、`y←y₁,x₁`、`z←z₁,y₂`）：三个父集逐个精确复现、检出链接恰好等于真值（0 漏 0 伪），15 列设计、对齐 1146 行、产物 12,913 字符（严格 JSON）、审计通过。反例逐条构造：伪造 p 值 / 伪造偏相关 / 检出标志翻转 / 丢掉一条没检出的链接 / 父集多一个 / 父集少一个 / 父节点的滞后超出本次搜索范围 / 设计列重排 / 相关矩阵不对称 / 外来产物。

**最尖的一条**：把 `y@t-2 → z` 的条件集从 `['x@t-3','y@t-3','z@t-1']` **削回只剩目标的父集**，并且**按那个较小集合把 r 和 p 重新算对**——产物每个字段都自洽，它只是不再是 MCI 而是一次普通的偏相关，戴着 MCI 的标签。逐字段的一致性一条都看不见它；只有**从记录的父集把条件集重新推一遍**才看得见。这就是「重建而不是读取」这个选择的全部理由。

**度量**：基线 8600 → **8642 passed / 189 skipped**（+26 新闸口，+16 是产物表/审计表/词表/schema/MCP 五张参数化门自动收编新成员）；mypy clean；kernel_ast 往返通过语法校验（5 条带 `time_index` 的边）。

**声明的取舍（两条）**：

- **`data_hash` 不覆盖 unit 列。** unit 走 presence column（和 cluster id 同一类，不强制数值化，于是字符串面板 id 能活着进来），而那一类被排除在摘要之外。可是 unit 列**会改答案**——它决定哪些行可以滞后到哪些行上。代价：两次只在分组上不同的运行共享同一个摘要；对冲是 `data_columns` 把分母写在产物上，而每一条断言最终都落在相关矩阵上，那张矩阵两次并不相同。
- **`STILL_ONE_LANGUAGE` 多了一行**（`themis/estimation/lagged_discovery.py: 12`）：11 条请求形状的拒绝 + 产物的 `note`。和它的姊妹 producer（`discovery.py`，19 行）是同一族债——standalone artifact 这条通道整体没有双语渠道，要还是一刀还，不是在这里补一个局部翻译。

**方法论沉淀**：

(405) **一个「学出来的」输出，唯一能被复核的是它自称拥有的性质；所以搜索步骤怎么选，要看它的输出留下了什么性质，而不只看它多快。** PC₁ 更省，但删一个候选的理由是「存在某个子集」，这个理由第二遍无从复查；grow-shrink 的不动点欠着两条可查的等式（没有可加的、没有可删的）。为可审计而换掉论文的一步是正当的，前提是把**换了哪一步、为什么、没换哪一步**写在产物自己身上——`method` 是枚举而不是自由字符串，因为不知道自己在审哪一步的审计不是审计。

(406) **会「无声消失」的那一半，必须重建而不是读取。** 判据很干脆：**如果某个字段被写错之后产物依然内部自洽，那它就不能靠自洽来检查。** MCI 条件集的第一半（目标的父集）少了会被别的等式抓到；第二半（驱动变量自己的父集按滞后平移）少了以后，r 和 p 真的就是那个较小集合给出的，每一处都对得上，只是它已经不是那次检验了。反例也必须照这个形状造——**改成自洽的弱版本**，而不是随手改个数。

(407) **搜索的停机规则错了，产物不会自相矛盾，它会一致地错。** 所以针对「不动点」的反例得先把该目标的全部记录按被改过的父集重算一遍再拿去被拒，否则先撞上「条件集对不上」，而那条拒绝跟不动点没有关系。这也划出了反例的分工：**自洽反例查声明的性质，常数伪造反例查算术**，两类都要有，而且不能互相顶替。

(408) **面板的接缝上，「处理了」和「碰巧没出事」在一次运行里长得一模一样。** 两段序列拼起来，如果两边的时间戳恰好隔得远，不带 unit 也取不到跨接缝的滞后——两边都对，而「按 unit 分组」这件事根本没被检验到。要让它被检验，必须构造**接缝上时钟连续**的那份数据，并且把带 unit 与不带 unit 的对齐行数一起量出来：差额正好等于 depth（892 vs 896，depth=4），才是接缝真被切开的证据。

### #448 粗化是「程序授权不了的决定」——缺的不是能力，是声明它的那个字段（2026-08-28）

**现象**：4 层的 proxy 配 `latent_cardinality=2`，Themis 抛 `proxy_cardinality_mismatch`，措辞自陈「把更细的代理粗化到 k 层还没有支持」，而 `data_gap_report` 是**空的**。也就是：说得出「声明和数据对不上」，说不出「声明什么能解锁」。

**根因假设：这不是措辞不够好，是词汇表里没有那个名字。** 缺口报告的每一条都要指向一个可以去补的东西——一个分布、一个工具变量、一份数据。粗化要补的是**一个决定**：`z=2` 和 `z=3` 是不是 U 的同一个状态。在 query 上没有地方写这句话，所以拒绝只能停在「对不上」。

**为什么是根因不是表象**：把拒绝的措辞改好也没用——它会指向一个不存在的字段。而反过来，光加字段也不够：折叠**会改数**（总体上任意保满秩的分组都识别同一个效应，有限样本上不会），所以它必须同时是**可声明的、可归属的、可重导的**三件事，缺一件就分别退化成「猜一个分组」「读者不知道这个数是自己选出来的」「验证器读的是别人折好的表」。

**做了什么**

1. **`ProxyCoarsening` 落在 query 上**（`kernel_ast.schema.json` / `types.py` / semantic_validator / kernel 往返）：每个 proxy 一组「层级分组」列表，组数=k。分组按**列表**而非「层级→组号」的映射，于是「组数」就是字段长度、「组非空」就是形状本身；两个 proxy 都要写出来（哪怕只有一个需要重编码），这样这份声明自己就说清了 M 的 k 列是什么，读者不必回去查数据。
2. **估计器一条路径**：无声明=单例分组，就是改动前一直在做的那套算术。折叠在**归一化之前**（`py[g]=Σy/Σn`、`M[i,g]=ΣΣw/Σn`、`pw[i]=Σ边际/n`），这是唯一给出粗化后变量条件概率的顺序。正定性也随之下移一层：**原始层级为空不再是违反**（稀疏层级常常正是要被并掉的那些），空的是**折后**的层才是 M 里没有行的一列。
3. **信封记折叠的输入，不是折叠的结果**：`measurement_channel` 现在带**列本身分辨率**的计数 + `z_groups`/`w_groups`，验证器自己再折一遍再跑公式 (5)。
4. **台账新增 `Provenance.CALLER_CHOSE`**，与 `CALLER_ASSERTED` 并列而不是合并（判据见方法论 402），并且和 `caller_asserted` 一样**由验证器从信封自身的记录重导**：一条说「这是你选的」的行，必须能在这份答案里找到那个选择（非平凡分组），否则拒绝。
5. **三个物种把三种情况分开**：没声明→`proxy_cardinality_mismatch` + 新的 `GapKind.PROXY_COARSENING_UNDECLARED`（blocking / point_estimate，两条出路：声明分组，或改 k）；声明了但不是层级的划分→`coarsening_does_not_partition_the_proxy`；声明了但组数≠k→`coarsening_group_count_is_not_k`。**已经写了字段的读者不会被打发去写那个字段。**

**闸口**（21 条，新文件）：**oracle 是四层列本来就是两层列加一枚硬币**——把硬币并掉的分组必须逐位复现两层列上的估计（`abs=1e-12`），折叠不是新估计量而是同一个估计量作用在重新编码的列上；换一个分组则给出另一个数（这条是「值得声明」的实证）。反例逐条构造：某层级被两个组认领 / 组里指到不存在的层级 / 空组 / 折成的列数与 query 的 k 不符 / 粗化下伪造 point / 声明多了一个层级 / 声明漏了一个层级 / 组数≠k / 某组在一臂上无样本 / 信封上根本没记分组 / 台账把选择归给一个没做过选择的运行。

**最尖的一条**：**一个数都不动，只把一个层级从一组挪到另一组**——W 行仍加总到本层、层仍覆盖样本、边际仍对、表逐字节相同，而答案变了。逐行的算术恒等式一条都看不见它，只有把折叠**再跑一遍**才看得见。这条反例就是「记输入不记结果」这个选择的全部理由。

**度量**：基线 8555 → **8600 passed / 189 skipped**（+21 新闸口，+24 是路由/语句/物种/拒绝四张参数化词表自动收编新成员）；mypy clean；derivation 与 query_result 两份 schema 都通过（后者每次 `themis.estimate` 出门都验）；严格 JSON 可序列化；两门语言的报告都不漏出表或分组，而拒绝的那一份**两门语言各有 3 行点名 `proxy_coarsening`**。

**声明的取舍**：组数≠k 这条检查本可以放在 semantic_validator（更早、不需要数据），放在了估计器。原因是 `SemanticError` 没有双语渠道——那个模块 26 条消息全是英文——而这条消息是要给写 query 的人看的。代价：一个组数写错的粗化要等到数据到场才被发现；因为识别层不读粗化，那也正是它第一次可能改变答案的时刻。

**方法论沉淀**：

(401) **「程序授权不了的决定」的完整形状是三件事，不是一件。** 一个诚实的拒绝只做了第一件：它说得出「对不上」。第二件是**在输入上给这个决定一个名字**——没有字段，再好的措辞也只能指向不存在的东西，所以「措辞不好」往往是「词汇表缺一项」的表象。第三件是**在台账里说这是谁选的**：一个会改数的决定如果不归属，读者会把它读成方法的性质。缺第一件是猜，缺第二件是死路，缺第三件是隐瞒。

(402) **「断言」和「选择」是两种归属，判据是撤回它之后还剩什么。** `CALLER_ASSERTED` 的自陈判据写着「撤回它答案变宽而不是消失」；粗化撤回了就没有答案，能做的是**换一个**。Provenance 的 docstring 自己立了规矩——「两个给出同样答案的成员就是一个成员」——那么给出不同答案的就该是两个。加一个成员的代价是可数的（一张 producer×(layer,provenance) 白名单、一个 schema 枚举、一条验证器重导、一份浏览器词表）；不加的代价是台账对读者说了一句小小的假话，而台账的全部价值就是读者能照着它行动。

(403) **(399) 的操作化：沿数据流往上走，记下最后一个「还没有人做过决定」的量。** 计数比概率可复核，是因为它欠着算术恒等式；而粗化后的 k×k 表**也是计数**、也满足全部恒等式、并且照样藏得住一个改动——把一个层级换个组，表一个字节都不变而答案变了。所以判据不是「记计数」，是**记决定之前的那一层**：折叠是一步，一步没人重走，就是答案能被挪走而不留痕的地方。

(404) **一条检查放在哪一层，不只由「最早能知道」决定，也由「哪个渠道能对读者说话」决定。** 同一个判断在解析层是最早的，在估计层才有双语的物种词表。当这条消息的读者是人而不是机器时，晚一点而说得出他们的语言，胜过早一点而只说得出一种语言——前提是把推迟的代价当场写下来，而不是让它变成一个没人记得的默认。

### #452 近端因果的数是被「元数据审计」放行的——伪造的点通过了全部复核（2026-08-25）

**怎么发现的**：不是读代码读出来的。上一条前沿（把 proxy 粗化做成可声明、可审计的决定）动手前按铁律核实缺口，核实的是**整条能力横跨的五层**而不是一个文件——查到 verifier 那一层时，`_rule_numeric_proximal_estimate` 的 docstring 自陈 `no re-fit`。**「可审计的粗化」要挂的那个审计不存在**，于是先构造反例。

**现象（跑出来的）**：正常两层 proxy 出 `point=0.334345`，把它改成 `0.634345`（错 90%）——

```
verify                   ok=True
verify_data_gap_report   ok=True
verify_assumption_ledger ok=True
verify_cluster_inference ok=True
verify_fingerprints_agree ok=True
themis.verify 直接通过
```

**根因假设：这条规则不是「查得不够严」，是它手上根本没有能重算的东西。** 它查的五件事——方法在不在枚举里、hash 是不是 64 位小写十六进制、样本量是不是整数、point 是不是个数、CI 有没有夹住它——**每一件都是关于这个块长什么样的事实，没有一件是那个数**。没记 CI 时最后一条连约束都不是；记了 CI 时，那个区间也是同一个产出方写的。

**为什么是根因不是表象**：把规则写严一点救不了它。**可复核性是产出方的属性，不是验证器的属性**——判据是「我要把这个数挪走，还得同时改什么才能自洽？」，当时的答案是**什么都不用改**。

**做了什么**

1. **产出方记下公式 (5) 反演的那张列联表**，作为 `measurement_channel` 进 derivation 的 inputs（不是进 `numeric_estimate`：这条结果**有** derivation，而选择偏倚/缺失数据把充分统计量放在块上恰恰是因为它们没有，审计路径是它们仅有的门）。
2. **记的是计数，不是它们归一化成的条件概率。** 这是这一刀最尖的一处：**对一个概率，第二遍能问的只有「在不在 [0,1]」；对一个计数，它欠着一串算术恒等式**——W 那一行要加总到本层的样本数，两臂的层要加总到整份样本，而那份样本要就是 data_hash 指的那一份。每一条都是改数的人必须同时满足的等式。
3. **估计器内部拆成两半**（`_arm_counts` 出计数 / `_risk_from_counts` 跑公式），bootstrap 走同一次转写而不是旁边再写一遍。
4. **终端规则重建 M/py/pw 并重跑公式 (5)**，比对两臂与 ATE。声明的边界：与产出方**共用 `numpy.linalg.solve`**——被独立重导的是公式与它立在的统计量，不是高斯消元的算术。

**闸口**（14 条，新文件）：真实信封通过（分母）+ 表确实在信封上（不然下面每条都空转）+ 层覆盖恒等式在真实信封上成立；**9 条反例逐条构造并跑过**——伪造 point / 伪造单臂 / 某层 W 计数不再加总 / 丢一层 / **把一层等比放大到内部自洽**（局部全对、只有样本总数不对，这正是逐行检查看不见而跨臂计数能看见的那一类）/ 篡改 W 边际 / 层序被换（数一个没动，动的是哪一列属于哪个 Z）/ 表来自另一份样本 / 表整个删掉（=改前每一份信封的形状）。

**反例照出了我自己规则里的一个缺陷**：整数计数下「代理对 U 一无所知」是**精确奇异**，而精确奇异会让 `np.linalg.solve` 先抛 `LinAlgError`——秩条件检查排在 solve 之后，于是这条规则会以未处理异常收场而不是一条说得出原因的拒绝。检查移到 solve 之前。

**度量**：伪造 point 从「五条审计全过」变成 `RuleCheckFailed: numeric_proximal_estimate.point is 0.634345, but re-deriving formula (5) from the recorded counts gives 0.33434542182669225`；基线 8540 → **8555 passed / 189 skipped**（+14 新闸口，+1 是 `proximal.py` 因为改用 `envelope_scalar` 自动被「每个产出方都用同一个转换器」那条参数化闸口收编）；mypy clean；derivation 仍通过 `derivation.schema.json`，严格 JSON 可序列化，两门语言的报告都不漏出这张表。

**顺带记下一处比登记更精确的现象**（粗化那一条的前置事实）：4 层 proxy + 声明 k=2 时，`estimator_failure` 如实说了「声明与数据不一致」，但 `data_gap_report` 是**空的**——Themis 说得出「对不上」，说不出「声明什么能解锁」。

**方法论沉淀**：

(399) **可复核性是产出方的属性，不是验证器的属性。** 判据是一句话：**「我要把这个数挪走，还得同时改什么才能自洽？」**——答案是「什么都不用改」，那这份记录就是一段描述，不是一个重导的地基，再严的规则也只能读它自己。让它成为地基的办法不是加检查，是**记下那个还欠着算术恒等式的中间量，而不是记下已经归一化完的结果**：概率只剩一个区间可查，计数欠着行和、总和、以及与指纹的一致，而一串互相咬住的等式是伪造者必须同时满足的东西。**这也划出了「重导」与「data-refit 天花板」的真界线**——不是「有没有原始数据」，是**充分统计量小到能随信封走吗**；能，就没有天花板可声明。

(400) **给一条闸口构造反例时，最先照出来的可能是闸口自己。** 秩条件那条反例第一次跑出来的不是拒绝，是一个未处理的 `LinAlgError`——因为判据排在了「会因为同一个原因崩溃的那一步」之后。**一个检查如果放在它所诊断的故障会先引爆的操作后面，它就永远不会被执行到**；顺序不是风格问题，是这条检查存不存在的问题。

### #395 档④刀4：语言开关本身——两门语言都写齐了，而没有一个读者能选（2026-08-25）

**现象**：档①-③ 把「语言」做成了一个参数：`Lang` 是封闭词表，两门语言的词逐成员齐全，kernel 不再自己写句子。但**能选**和**选得到**是两回事——网页固定按 `DEFAULT_LANG` 渲染，MCP 的 `themis_report` 连一个 `lang` 参数都没有。除了在 Python 里手写 `build_analysis_report(..., lang="en")` 的开发者，没有任何读者能说出自己读哪门语言。

**为什么这一刀只能最后做**：`ARRIVING` 的文档写着，把一个 tag 从「正在到来」升格出去断言的**不是它的词写完了——闸口早就在说这件事——而是「没有任何读者面是从没被看过的」**。所以升格前先看：25 个程序端到端渲染成英文，170,409 字符，**0 处未填槽位、0 处「本版本没有它的说法」兜底**，全篇唯一的中文是调用方自己写的引文（`一篇综述`），按调用方的话原样回显。看过了，才动 `Lang`。

**做了什么**（四件，一件一层）

1. **升格**：`Lang.EN` 入册，`ARRIVING` 归空；浏览器 `LANGS = ['zh', 'en']`、`ARRIVING = []`。空集合本身是一句断言：**这个 build 声明的每一门语言，它都答得出来**。集合留着，因为第三门语言会需要它。
2. **`language.answered(lang)`**：把 tag 换成成员，换不出来就按名拒绝。原本这句话内联在 `explainer.explain` 里，而 MCP 这扇门要做同一件事——**「这个 build 有哪几门语言」写两遍就是两条会分叉的规则**，正是 `Lang` 当初取代的东西。它返回成员而不是布尔：选词的是成员，只回「是」的校验器会让每个调用方再转换一次。
3. **浏览器的 `useLang()` 从常量变成真的选择**：模块级 store + `useSyncExternalStore`，初值 = 记住的选择 → 浏览器自己要的语言（丢掉地区段）→ `DEFAULT_LANG`；选择存 `localStorage`，并同步写 `document.documentElement.lang`（读屏软件挑声音、浏览器断词与字体匹配都看它）。masthead 加语言选择器，选项由 `LANGS` 迭代出来、按 **`ENDONYM`** 标注——**一门语言的名字是这个仓库里唯一一个不能用别人的语言写的串**：告诉英文读者另一个选项叫「Chinese」，等于用他正要离开的那门语言告诉他。`ENDONYM` 因此从 kernel 生成进 `kernelWords.generated.ts`（`reader_words.PUNCTUATION` 顺势更名 `PLAIN`——它装的从来不是「接缝」，是「浏览器也要持有、没有 token 没有洞的纯 `Words`」）。
4. **MCP `themis_report` 加 `lang`**：这是唯一一扇「读者的语言无法被观测」的读者面——浏览器面对着读者可以问，库调用方自己传，而门另一头的 agent 知道它的用户读哪门语言却没处说。

**一处与登记的解法不同，并说明理由**：登记时写的是「`lang` 在读者面入口做成 required」。**登记的解法也是待验证断言**——验证结果是不做：required 会打断每一个嵌入方，而读者一点好处都没有得到；用户要的「让中国人和外国人都可以用」靠的是**选择可达**，不是**选择强制**。所以 `explain` / `build_analysis_report` 保留有文档的 `DEFAULT`，而每一个读者面都补上问的方式。

**闸口**（20 条，新文件 `tests/test_the_reader_picks_the_language.py`）：门（成员往返、按名拒绝且同时报出可选集、拒绝句全仓只有一个作者、explainer 走同一扇门）；包内每一处渲染调用都点名语言（AST，今天 1 处，规则是让第 2 处显形）；MCP 门按 zh/en 各答一次且两份不同、不点名时等同默认、`kl` 被按名拒绝、`lang` 出现在 agent 能看到的 tool schema 里；浏览器侧 `useLang` 不是常量、17 个组件没有一个持有 `DEFAULT_LANG`、选择器由 `LANGS` 迭代而不是手写、endonym 与 kernel 逐字相等且没有第二处手写、`as Lang` 全仓只有一处（转换只在 `offered` 里发生，且比对的是 `LANGS` 不是更宽的 `WRITTEN`）、`documentElement.lang` 只有一个写入者。**8 条反例逐条构造并跑过**，每一条都只打掉它该守的那一条、其余 19 条仍过。

**这一刀让一整类缺陷第一次变得可见**：`verdict.ts` / `language.ts` 共 **39 个导出函数**带 `lang` 且默认 `DEFAULT_LANG`，被组件调用 **549 次**。少传一个参数在只有一门语言时完全不可见，类型系统也看不见（参数可选，漏掉照样编译）；从今天起它是英文页面里的一句中文。量出来是 **549 / 0**，并立成闸口。

**度量**：`ARRIVING` 1 → 0；浏览器 `LANGS` 1 → 2；`useLang` 常量 → 订阅；**组件改动 0 个**；基线 8517 → **8540 passed / 189 skipped**（+20 新闸口，+2 `test_risk_provenance` 双语参数化，+2 语言闸口，−1 旧的 `[en]` 参数化例，逐文件用 HEAD worktree 的 `--collect-only` 对出来）；mypy clean；`npx tsc -b --force` 通过；`pnpm build` 已重建。

**方法论沉淀**：

(397) **当一个事实还只有一个取值时，就要给「问它」这件事一个名字。** `useLang()` 立起来的那天返回的是常量，看着像一层没有用处的间接；今天把它变成真的选择，改动落在**一个函数**里，17 个组件一行没动。反过来的世界是：每个组件 `import DEFAULT_LANG`，第二个取值到来时改动散落在十七处——而那一刻的压力恰恰是给渲染不出东西的那几个组件穿一个 prop 过去，于是一个面半门语言。判据不是「将来会不会需要抽象」，是**这个常量将来会不会有第二个取值**；会，就现在把「读它」改成「问它」。

(398) **一条规则的主语如果是一个本来就该变空的集合，它会在自己最成功的那天悄悄停止运行。** `@parametrize("tag", sorted(ARRIVING))` 在 `en` 升格后变成 `got empty parameter set`——pytest 把它记成 **skip 而不是 fail**，在报告里和「跑过了」长得一样。判据：问这条规则在集合为空时还剩下什么。如果什么都不剩，它就不是一条独立规则，而是某条**无条件规则**在最容易出错那个子集上的加强——那么它该写成循环（空集合合法地什么都不做），并在 docstring 里说出无条件的那一半在哪里。

### #447 一个读者读的列表和一个公式里的参数表，被同一扇门当成了一件事（2026-08-25）

**现象**：浏览器里 8 处写死的中文顿号 `、`（登记时说「约 10 处，英文侧全错」）。

**根因假设：`listing()` 在干两件事——「一串给读者读的东西」和「一个公式里的参数表」，而后者不是读者语言里的列表。** `P(y | x, z)` 里的逗号是这个表达式的一部分，`Text.FORMULA` 自己就写着「翻译过的 Σ 不是 Σ」。

**为什么是根因不是表象**，三条：

- **跑出来的，不是读代码推的**：同一份中文报告里相邻两行，同一个条件集两种分隔符——
  ```
  - 条件概率这一层拆成 2 个因子：P(y | x、z) × P(z) ……
  - 整条估计量的恢复式：`Σ_z P(y | x, z) · P(z)`
  ```
  第一行是读者拼的（`listing`），第二行是 kernel 写的（`_factor_repr`，`, `）。
- **分歧在读者层与 kernel 之间，不是两个读者之间。** kernel 每次自己建这个表达式都写 `, `；两个读者面则一个借了读者的标点、一个手写了中文的。
- **登记的症状和这条不一致是同一个缺陷的两面**：8 处里 7 处确实是读者的列表（变量集、`col=level` 分层格、按组的 σ²），第 8 处正是这个公式。**「公式内部的分隔符」没有名字，于是需要它的人各挑各的**——挑中文的那次在中文里碰巧对，在别的语言里全错。

**做了什么**

1. **`language.within(items)`**：一个表达式内部的若干名字，按表达式自己的写法。**它不接语言，而没有这个参数就是它要说的全部**——读者的标点进不了一个从没被递过读者的门。浏览器同名的 `within()` 是它的孪生。
2. 两处公式内部改走它（报告的 `_recovery_factorization`、浏览器的 `recoveryFactors`），另外 7 处真列表改走 `listing(…, lang)`。浏览器里 `join('、')` 归零。
3. `test_no_part_of_a_block_is_silent` 有一条断言把 `P(y | x、z)` 钉住了——**它钉的是这个缺陷**，随之改成 `P(y | x, z)` 并写明为什么。

**闸口**（8 条，新文件）：一份报告里同一个条件集只有一种写法（zh/en 各一条）；两门语言下这个表达式逐字相同；`within` 的签名里没有 `lang`（AST）；浏览器不挑自己的标点（分母 = 这个面确实在用 `listing`，>8 处）；两个面的因子分解写法互相对上。**两条反例逐个构造并跑过**：把报告那处改回 `listing` → 1 failed；把浏览器那处改回 `join('、')` → 1 failed，其余 6 条仍过（说明失败的是它该守的那一条，不是连坐）。

**度量**：浏览器写死的列表标点 8 → 0；基线 8509 → **8517 passed / 189 skipped**（+8 正是新闸口）；mypy clean；`npx tsc -b --force` 通过；`pnpm build` 已重建。

**方法论沉淀**：

(396) **一个分隔符没有名字时，需要它的人会各挑各的——而在写这些代码的那门语言里，挑错的那个看起来是对的。** 中文顿号在中文报告里读着顺，所以它在两个面上各活了很久；只有第二门语言到来时才现形。判据不是「读一遍觉得别扭」，是**问这个接缝属于谁**：属于读者的（列表、句间）随读者变，属于内容的（公式里的参数、标识符里的下划线）不随任何人变。**接缝的归属是个可判定的问题，而没有名字的接缝一定会被当成前者。**

### #395 档④第八刀：一行能说出「靠哪条定理成的」，说不出「是哪一步没成」（2026-08-25）

**现象**：信封上最后一批 kernel 自写句子——两个恢复块的 `failure_reason`，7 处（普查只撞见其中 1 处，它给的是一个实例不是缺口的大小）；同一行上还有 `requires` 2 处、`external_data_needed` 3 处同族。

**根因假设：这一行能说出「靠哪条定理成的」，说不出「是哪一步没成」。** `criterion` 是个四值封闭词表，而它每一条失败上都是 `null`；失败那一半没有任何槽位，于是它的全部内容——哪个条件不成立、搜索走了多远、这个否定是不是一个证明——都被写进行上唯一的自由文本槽。

**为什么是根因不是表象**，五条独立证据：

- **`failure_reason` 出现在两条 `recoverable=True` 的记录上**（`"no selection nodes declared"` / `"no missingness declared"`），而两个读者面都只在 `recoverable` 为假时读它——**一个叫「失败原因」的字段装着「它没有失败」，且那两句零读者**。一个槽位在答另一个问题，这是最直接的外化。
- **`criterion` 这个封闭词表 schema 里声明着，两个读者面一个都不渲染。** 说「靠哪条定理成的」的词表没人读，说「哪一步没成」的词表不存在却两个面都读。
- **第七处是拼出来的**：`"; ".join(parts) + "。…"`——一个字段其实是一列，被拼成串，接缝和句号由 kernel 挑（第五刀第四作者同型）。
- **「这不等于证明了它不可恢复」在两个模块各写了一遍。** 它说的是**这个实现的完备性**，不是这次数据的事；每次重写，正因为没有地方登记它。
- **同块的 `requires` 是行上已有事实的第二份记录，而且已经漂了**：它写死 `"conditional P(Y|X,Z)"`（字面 Y/X/Z），同一行的 `target` / `covariate_recovery.target` 带的却是这次程序真实的谓词名。

**做了什么**

1. **失败那一半拿到形状**：两个词表，各在自己的 producer 旁——`selection_recovery_shortfall`（3 个成员）、`missing_data_shortfall`（4 个）。`failure_reason: str | None` → `Statement | None`。
2. **两条 `recoverable=True` 的文字删除**，不是翻译。行上的事实（没有选择节点 / `mechanism="none"`）已经说了它是哪一行，而那两句话没有任何读者能看到。
3. **`complete_criterion` 升为一等字段**，与 `search_budget` 并列：一个给出判决被检查过的范围，一个说产生它的判据是不是也必要。两者一起，读者才拿得到「没找到」和「不存在」的区别；措辞回到读者层写一次（报告 `_NOT_A_PROOF`、浏览器 `notAProof`），不再在两个模块各写一遍。**条件那一支是 iff，所以它的否定是证明**——这个区分以前在措辞里，现在可以被分支。
4. **估计量那条拼出来的句子改成「洞里装一列 statement」**：`A_PRODUCT_IS_BLOCKED_BY_ITS_FACTORS` 的 `{factors}` 洞装的是哪几个因子卡住了它，接缝由 `listing` 在读者那边挑。
5. **`requires` 与 `external_data_needed` 的「角色词 + 符号式」拆开**：角色进词表（`recovery_factor` / `unbiased_distribution`），符号式仍是符号式；`requires` 的 target 改用行上真实的那个，那份写死的第二记录随之消失。验证器独立重建这份 ledger——按词表名和 token 拼，不 import producer。
6. **`language.listed()`**：`spoken` 的孪生，一个接缝之隔。这两行以前在报告里写了两遍、`assemble` 里第三遍。

**顺带被这一刀逼出来的一处，而且是这一刀真正的意外收获**

`language.VOCABULARIES` 是在 producer 的类体跑起来时才填的，于是**一个读者能说哪些词表，取决于谁碰巧 import 过谁**。量出来：一个裸 `import themis` 之后，20 个 statement 词表里有 **8 个**是未注册的（本刀新增 4 个，加上 `measurement_note` / `precision_target` / `time_window` / `sutva_concern`——它们在 `data_gap_report` 里，而 `themis/__init__` 不 import 它）。kernel 跑过一遍时看不出来，因为跑查询顺路 import 了 producer；**在「拿一份存好的信封单独渲染」这条路上，读者会把 token 原样交给用户**。「哪些集合可能到达读者」不是每次调用的问题，而这份名单本来就在 `reader_words.GLOSSED` 里，于是加了一扇 `load()`，由包的 `__init__` 在最后调用一次。

**闸口**（15 条，新文件 `test_a_recovery_verdict_names_what_came_back_empty.py`）：四条反例逐个构造并确认契约说不，且**每条都断言报错里出现的是它自己那个值**——其中两条走同一个 `oneOf`、报错读起来会一样，为别人的理由被拒的反例证明不了自己。正面一臂：两个模块的否定判决逐语言渲染且 token 不出现在句子里；两条 `recoverable=True` 的行不带 shortfall；完备与不完备两支的措辞里都没有那句 caveat，而报告**恰好**在 `complete_criterion` 为假时加上它；被卡住的乘积把因子装在一个洞里且两门语言接缝不同；两个模块的源码里不再有 `"conditional P(Y|X,Z)"`。词表注册那条另有两测：源码里声明的 statement 词表在 `import themis` 之后全部在册（分母 ≥20），以及**它不是靠碰巧**——`themis/__init__` 的 import 里没有任何一条通向 `data_gap_report`，而 `measurement_note` 在册。

**度量**

- **kernel 自己写句子的信封路径 1 → 0，实处 1 → 0。** 25 个程序跑完，信封上剩下的 7 条带句子的路径**全部是调用方自己的话被回显**（用户写的歧义 note/description、他给的文献出处，以及缺口 `rationale`——那就是同一条 note）。这条线是 8 → 5 → 3 → 2 → 1 → **0**。
- 基线 8413 → **8509 passed / 189 skipped**。+100 条里 15 条是本刀的闸口文件，另外 85 条散在八个既有的完备性闸口里（`test_a_word_reaches_the_reader_as_a_word` +33、`test_vocabulary_reach` +12、`test_a_vocabulary_prints_as_the_word_it_is` +12、`test_web_vocabularies` +8 …）——四个新词表被这些闸口自动收进分母，这正是它们该有的反应。skip +4，正是四个新 `Word` 子类。
- mypy clean（143 files）；`npx tsc -b --force` 通过；`pnpm build` 已重建（bundle 776KB → 779KB）。

**方法论沉淀**：

(393) **一行能说出成功那一半、说不出失败那一半时，失败的全部内容会挤进行上唯一的自由文本槽。** 这里 `criterion` 只在成功时有值，于是「哪个条件不成立」「搜索走了多远」「这个否定是不是证明」三样事被写成了一句话。判据不是读那句话，是看**这一行有没有一个字段在 `recoverable=false` 时还说得出东西**——没有，就说明散文不是风格问题，是那半边没有形状。

(394) **一个字段出现在它的名字明说不该出现的行上，是这个槽位在答另一个问题的直接证据。** `failure_reason` 挂在两条 `recoverable=True` 的记录上，而两个读者面都只在失败时读它——**零读者的内容比任何措辞都更能说明问题**：没人看得见，它就不是为读者写的；名字与所在行矛盾，它就不是为这个问题写的。这两条一起，比读一遍句子快。

(395) **一个「注册表」如果靠 import 副作用填，那么它的完备性就是一个谁先 import 谁的问题——而这类洞只在最冷的那条路上现形。** 20 个词表有 8 个在裸 `import themis` 之后不在册，跑过一遍 kernel 就看不见，只有「拿存好的信封单独渲染」会撞上。答案不是让每个读者去记得 import，而是问「这份名单在哪」——它通常已经存在（这里是生成浏览器表的那张表），把它接上就行。

### #395 档④第七刀：一个洞里装的是另一句话，而它被渲染成了文本——因为那张表在信封上没有名字（2026-08-25）

**现象**：缺口报告 `gaps[].describes[].said.why` 五处带 kernel 中文。

**根因假设：这五处是把另一句话渲染成文本、塞进这句话的洞里**（`gaps.said(item, lang)`）。**而它必须被渲染，是因为 `gaps.SAYS` 和第六刀之前的 `DESCRIBES` 一样，是张 token→词的表却在信封上没有名字**——没有名字，读者就解析不了它，于是唯一能解析的地方是 kernel，渲染就发生在那里。

**为什么是根因不是表象**，量出来的证据是决定性的：

- **这个 `lang` 参数穿了 35 个签名（全模块 73 个函数）+ 27 处 `lang=lang` 传递，唯一的消费者就是这五处。**
- **而唯一的调用方从来没传过它。** `scheduler.py:5830` 那次 `compute_data_gap_report(...)` 列了 13 个具名参数，没有 `lang`——所以这条 35 层的线**一直是 `DEFAULT`**，模块文档里那句「`lang` 是读者的，它到达下面每个 producer」是假话。参数是 #437 把报告改成 statement 列表之后留下的化石：那一刀把这个模块的输出改成了 statement，却留下了它自己解析别人 statement 的那五处。

**做了什么**

1. **`gaps.SAYS` 拿到信封上的名字** `NEEDED = "gap_says"`，走第六刀开的 `language.declare`（它的孪生 `DESCRIBED` 上一刀已经拿到）。
2. **`gaps.shortfall(item)`**：一条 shortfall 以「另一句话的洞装它的样子」出来。`said` 是同一个事实的渲染，而渲染正是调用方被迫做的事——洞装得下一个值或一个**词**，而词是词表加 token，这张表当时没有名字可当那个词表。两种形状都从这扇门回来，因为洞两种都装得下：有物种的是 statement，没有的是它被登记的那个名字（那是调用方自己的话，对每个读者相同）。与 `said` 同理地两种输入都读，序列化边界在哪不是它的问题。
3. **五处 `why=gaps.said(item, lang) or item.target` → `why=gaps.shortfall(item)`。** 于是这个洞里装的是一句话，而不是一句话的影子——三层深：缺口的句子、它洞里的 shortfall、shortfall 洞里的 `query_part`。
4. **整条 `lang` 线删除**：35 个签名参数、27 处传递，以及删空之后悬着的 6 行 `*,`。模块文档改成它现在为真的那句：这里不到达任何语言，这个模块写的是 statement——哪一句加这一次的事实——所以没有一样东西需要挑语言。`language.` 的提及从 51 处降到 15 处（剩下的是别的用途）。
5. 浏览器 `WORDS` 接上 `gap_says: GAP_SAYS`。这张表早就生成好了（缺口报告自己那面要它），`VOCABULARIES` 里也早就钉着——缺的只是「statement 的 `vocabulary` 字段报这个名字时，去哪张表查」这一条。

**闸口**（四条）：shortfall 进洞是 statement 且逐语言渲染得出、三层嵌套的第三层是 `query_part`；没有物种的条目原样交回它被登记的名字；**AST 扫描：这个模块没有任何函数带 `lang` 参数**，并先断言函数总数 > 60 作分母（不然「一个都没找到」和「一个函数都没解析出来」长得一样）；两个 statement 生产者里 `gaps.said(` 零处、`gaps.shortfall(` 恰 5 处。

**度量**

- kernel 自己写句子的信封路径 **2 → 1**，实处 **6 → 1**。剩下的唯一一条是 `selection_recovery.failure_reason`（1 处），即第八刀。
- 基线 8409 → **8413 passed / 185 skipped**。+4 正是新增的四条闸口；skip 不变——`gap_says` 是**表**，不是 `EnvelopeName`，所以不进那份身份检查（这正是「+4 且 skip +0」这两个数一起验证的事）。
- mypy clean（143 files）；`npx tsc -b --force` 通过；`pnpm build` 已重建。生成体积不变：`GAP_SAYS` 本来就在生成表里，这一刀只是把它接进 `WORDS`。

**方法论沉淀**：

(391) **一个参数穿了多少层是表象，谁把它传进来才是判据。** 35 个签名带着 `lang` 看起来是「语言深入了 kernel」的铁证，但决定性的是另一头：唯一的调用方从来没传过它，于是这 35 层一直说着同一个默认值，而文档里那句「它是读者的」在任何一次运行里都不成立。**数调用方比数签名快，而且它答的是另一个问题**——签名答「这个值能走多远」，调用方答「这个值是不是真的存在过」。

(392) **一个洞里装的是另一句话时，「装 statement 还是装它的渲染」不由这段代码决定，由那句话所在的表在信封上有没有名字决定。** 没名字，读者就解析不了，能解析的只剩 kernel——于是渲染必然发生在那里，用的是查表时被递进来的那门语言。所以「kernel 里为什么会有语言」的答案常常不在这段代码里，而在另一个模块少了一个名字上；顺着洞往里找那张表，比顺着参数往上找调用方更早到达根因。

### #395 档④第六刀：这张表把「读者的说法」当成一个可以问语言的访问器，而不是一个词表（2026-08-25）

**现象**：信封上最后一条大宗 kernel 自写句子——假设台账的 `assumptions[].claim`，20 处。

**根因假设：这张表把 `claim` 当成一个可以问语言的访问器（`classify_assumption(id, lang)`），而不是一个词表。** 语言参数在 kernel 里被消费掉——而 kernel 是唯一不该知道读者是谁的地方。

**为什么是根因不是表象**，三条独立证据：

- **同一行三个字段，两个以事实上信封、一个以文本上信封。** `layer` 是词表、`testable` 是布尔，只有 `claim` 是渲染好的句子。差别不在这三样事实的性质，在于前两个有载体、第三个没有。
- **这个字段有三个作者，而只有一个走这张表。** 台账里另外两处直接写 `claim`：提案边走 `gaps.described(gap)`（在 kernel 里把一段话拼好，连句间接缝也由 kernel 挑），θ prior 走 `f"{key} = {value}（LLM 常识 prior）"`——一个硬写中文的 f-string。一个 `x-text: kernel` 的字段有三个作者、而契约只说 `type: string`，正是「这个槽位没有形状」的外化。
- **缺的机制是「词表可以是一张表」。** `language.VOCABULARIES` 只收 `Word` 子类，而 `Word` 把词放在成员上。这 157 行没有成员名可起——起了就是每个 id 的第二份拼写，而且没有任何东西会引用它。所以这张表不是「忘了做成词表」，是**做不成**：门只有一扇，而它进不去。

**做了什么**

1. **`VOCABULARIES` 从「`Word` 子类的注册表」拓宽成「词表的注册表」。** 一个词表就是 token 和它的词；两种的差别只在这份映射**放在哪**。`Word` 放在成员上——token 是我们自己的名字时该这样（拒答点名一个、槽位填一个，名字值得写）。**表**放在表里——token 是别人的名字时该这样。两扇门（`Word.__init_subclass__` / `declare`），一份注册，`_answers_to` 一处查重名。
2. **写者的门加了 `spelt(词表名, token, **facts)`**，`state(成员, **facts)` 委托给它；读者的 `spoke` 经 `_words_of` 两种都认。`spelt` 让「集合里没有的 token」可表达——这不是契约的洞，正是它有用的原因：token 是别人名字的词表一定会被递进来一个它没有的，而回答就是 `gloss` 早就给的那个（把名字交给读者，并说明这是替身）。
3. **`_EXACT` 与 `_PREFIX` 统一成同一行型** `(layer, testable, Words)`——它们本来不同，是因为前缀行的「词」那一格里可以放一条规则（一个槽位两样东西）。规则不是一种措辞，它说的是「这个 id 怎么读」，于是搬进按前缀键的 `_RULES`；返回值从「Words + 已渲染的槽位」变成「token + 这一次的事实」。四条 monotonicity 的 lambda 并成一个 `_direction`：方向以 `spelt(Monotonicity.vocabulary, tail)` 进洞，于是「tail 不是成员」不再需要 kernel 里的分支——`monotonicity_first_stage_effect_same_sign_for_all_units` 落到同一个兜底，逐字与改前相同。
4. **`claim` 变成 statement 的序列**（它本来就是一段话）。三个作者各有自己的词表：`assumption_claim`（表，157 行 = 136 exact + 19 prefix + 2 兜底）、`gap_describes`（`gaps.DESCRIBES` 本来就是一张 token→词的表，缺的只是一个信封上的名字）、`theta_prior_claim`（一个成员的 `Word`）。`language.restate` 把缺口那种「键名不同的同一个 statement」搬进通用形状，而不用把已经切好的两半再切一遍。
5. **`classify_assumption` 不再接语言**——返回的四样现在都是关于这条假设的事实，对每个读者相同。
6. **`language.spoken()`**：`spoke` 的复数，句间接缝归语言。浏览器同名的门是 `sentences()`，`GapReport` 自己那份 `seam` 随之删掉——它当初「属于这个面的排版」的理由，在这个字段成为第二个消费者时就不成立了。

**闸口**：三条反例逐个构造并确认契约说不——`claim` 写成渲染好的文本（`is not of type 'array'`）、`claim` 为空（`should be non-empty`）、一条 statement 没有 token（`'token' is a required property`）。三条报错互不相同，逐条打印核过，反例不循环。正面一臂是三个作者各写一行同时上信封并逐语言渲染；另有三条守这一刀立起来的东西：每条规则在六种 tail 下返回的 token 都在表里（**跑出来问，不是读代码**——返回哪个 token 取决于 tail 读不读得开）、`_RULES` 的键都是表声明的前缀、157 = 136 + 19 + 2（前缀与 id 撞名会静默吃掉一行，而少一行就是一句读者永远拿不到、且没有东西会说的话）。

**顺带被这一刀逼出来的两处**：测试侧 `web_source.entry` 的键匹配没有转义也不认引号——它的邻居 `top_level_keys` 早就写着「键不总是标识符」，而一个 token 是别人名字的词表，键里就有括号和竖线（`rank_condition_P(W|Z,x)_invertible_verified_on_data`）。词表登记表 `Vocabulary` 也开出第三扇声明门 `tabled`：成员由一张表声明，而不是由 Python 枚举或 schema 站点。

**度量**

- kernel 自己写句子的信封路径 **3 → 2**，实处 **26 → 6**。剩下两条：`describes[].said.why` 5、`selection_recovery.failure_reason` 1。
- 基线 8362 → **8409 passed / 185 skipped**。多出的 1 个 skip 已单独量过：身份检查从 184 跳到 185，正是新增的那一个 `Word` 子类 `Prior`；另外三个词表是**表**、不是 `EnvelopeName`，所以不贡献——这正是「+1 而不是 +4」这个数验证的事。
- mypy clean（143 files）；`npx tsc -b --force` 通过；`pnpm build` 已重建。

**当场声明的取舍**：157 行 × 两门语言现在生成进浏览器，`kernelWords.generated.ts` 从 176KB 涨到 215KB（+39KB，bundle 776KB）。备选是让 kernel 继续渲染这个字段——那正是这一刀要拆的病灶——所以没有选。这是 #399 那条「生成 + 签入」路线的代价，在这张最大的表上的兑现。

**方法论沉淀**：

(388) **一个词表就是 token 和它的词；两种写法的差别只在这份映射放在哪。** 放在成员上，是 token 是我们自己的名字时的写法（有名字可写、有地方引用）；放在表里，是 token 是别人的名字时的写法（起名字等于给每个 id 再拼一遍，而且没人会引用）。只开第一扇门，第二种集合就根本进不了词表——于是它的句子在查表的同一口气里被渲染掉，在 kernel 里，用查表时被递进来的那门语言。

(389) **一行上有几个字段，就该问它们是不是同一种东西。** 三个字段两个是事实一个是文本，差别不在事实的性质，在于前两个有载体、第三个没有。这比「这句话读起来像不像散文」是更快的判据，因为它不用看内容。

(390) **一个字段有几个作者，是在问这个槽位有没有形状。** `claim` 有三个作者而契约只说 `type: string`，于是两个作者各自发明了自己的写法——一个在 kernel 里拼段落，一个写 f-string。**契约松到能容纳所有作者，等于没有契约**；而数作者比读契约快。

### #395 档④第五刀：一个界说得出「这个区间是什么」，说不出「关于它读者还该知道什么」——于是两个装句子的字段成了垃圾场（2026-08-24）

**现象**：剩下五条 kernel 自写句子的路径里最大的两条都在 `bounds.py`——`bounds_results[].notes`（21 处）与 `bounds_results[].data_required[]`（21 处）。三个方法各写一句中文 notes，第四个作者在 `scheduler.py` 用 `f"{bounds.notes} {note}"` 空格拼第二句；`data_required` 的每一项是一个符号表达式，后面用 `  # ` 粘一句中文注释。

**根因假设：一个界能说出「这个区间是什么」，说不出「关于这个区间读者还该知道什么」。** 前者有一等字段（`method` / `estimand` / `assumptions` / `lower_expression` / `upper_expression` / `instrument`），后者一个都没有——于是第二类事实全被写成句子，而这一行上仅有的两个装句子的字段成了它们的去处。

**为什么是根因不是表象**，三条独立证据：

- **句子里锁着的事实信封上没有别的记录**：BP 的响应型个数与三个基数、MTR 收紧的是哪一侧、Manski 区间的宽度、scheduler 那条「更紧的方法按规模被放弃了」（含 `MAX_RESPONSE_TYPES`）。**渲染 prompt 自己承认了**：`| notes | quote verbatim — generator-curated context |`，以及「count `|X|^{|Z|}·|Y|^{|X|}` follows from those, and `notes` records it」。要 LLM 逐字引用，正是因为那是唯一的记录。
- **没有槽位时，作者会当场发明接缝。** `data_required` 用 `  # ` 把注释粘在表达式上（一个槽位两样东西，#379 / #384 同型）；第四个作者用空格把第二句粘在第一句后（一个字段其实是一列，拼写成了串，而那个空格是读者语言的标点，由 kernel 决定了）。
- **两个字段一个浏览器读者面都没有**——`Verdict.tsx` 只渲染 method / assumptions / tightness / lower / upper。事实锁在句子里、句子又只有 prompt 一个读者，是同一件事的两面。

**做了什么**

1. **三个词表**：`Note`（四个成员：区间宽度、响应型划分多大、收紧了哪一侧、更紧的方法按规模被放弃）、`Observable`（联合观测 / 完整分布共几个概率）、`Side`（下界 / 上界）。`notes: str | None` → `tuple[Statement, ...]`，`data_required: tuple[str, ...]` → `tuple[Statement, ...]`。
2. **第四个作者改成追加**：`notes=bounds.notes + (language.state(...),)`。它不再需要知道方法已经写了什么，也不再决定两句之间放什么。
3. **复述一律删除而不是翻译**：句子里凡是重说 `method` / `estimand` / `instrument` 的从句都去掉了——一句复述旁边字段的话是那个字段的第二份记录，可以不一致。#379 那条闸口（工具名同时在字段和句子里）因此变成更强的一条：**句子不再提它**。
4. **浏览器补上这两行**，并新增 `listing()`——把读者语言的列表标点收进一扇门，#447 的其余十处从这里走。

**顺带（不是顺带，是这一刀逼出来的）：`Monotonicity` 成为 `language.Word`，从 `themis/types.py` 搬到 `themis/ledger.py`。**

MTR 那句里的方向**不是复述**。先按复述删掉，跑出来才发现：这条 θ 路径上根本没有 `assumption_ledger`，方向只以 `mtr_non_decreasing` 这个 id 存在，而浏览器把 `assumptions` 裸拼出来——删掉就把 #380 退了回去。**登记的解法也是待验证断言，这次是当场被自己的测试证伪的。**

于是把词表补齐：`_MONOTONICITY_WORDS` 是一张摆在成员旁边、却不在成员上的表——正是 `Word` 存在的理由；它当初的注释写着「因为 `Monotonicity` 没有词可读」，而唯一挡着它变成 `Word` 的，是**槽位装不下一个词**（第三刀之前）。词表连同它的 `monotonicity_word` 访问器一起消失，两者并成一个类；因为携带自己文本的词表需要 `language`，而 `language` 导入 `types`，它搬到了 `ledger.py`——`Layer` / `Severity` / `Provenance` 旁边，`types.py` 只在 `TYPE_CHECKING` 下引用它。三处 `Monotonicity(x)` 改成 `Monotonicity.named(x)`（`Word` 早就为这件事开了门），`named` 的返回类型从 `Word` 改成 `Self`。注册名从 `counterfactual_cell_monotonicity` 改成 `monotonicity`：它现在经三个容器上信封，按第一个见到它的容器命名已经是假话。

**闸口**：三条反例逐个构造并确认契约说不——`notes` 写成一句渲染好的文本、`notes` 里有一句没有 token、`data_required` 的项是 `P(y, x)  # 联合观测`。三条各自的报错互不相同（`not of type 'array'` / `'token' is a required property` / `not of type 'object'`），逐条核过，反例不循环。正面一臂同时在场，另有两条守这一刀立起来的东西：第二个作者是追加而不是拼接；方向与侧别都以 token 上信封、以读者的词落地。

**度量**

- kernel 自己写句子的信封路径 **5 → 3**，实处 **68 → 26**。剩下三条：台账 `claim` 20、`describes[].said.why` 5、`selection_recovery.failure_reason` 1。
- 基线 8295 → **8362 passed / 184 skipped**。多出的 3 个 skip 已单独量过：身份检查从 31 跳到 34，正是新增的 `Note` / `Observable` / `Side`；`Monotonicity` 本来就是 `EnvelopeName`、本来就在跳，所以它不贡献——这正是「+3 而不是 +4」这个数验证的事。
- mypy clean（143 files）；`npx tsc -b --force` 通过；`pnpm build` 已重建。

**当场声明的取舍**：`Monotonicity` 搬家改了 22 个文件的一行 import。不搬的替代是在 `ledger.py` 再声明一个成员集相同的 `Word` 并加一条闸口钉住两者相等——那正是 #399 刚拆掉的形状（两份记录加一条闸口），所以没有选它。代价是这一刀的 diff 里混着一批纯机械的 import 行。

**方法论沉淀**：

(385) **一个装句子的字段，装的是「这一行没有字段可放的那些事实」。** 判断它是不是欠账，不看它写得像不像散文，看它说的事实在旁边有没有槽位：有，就是复述，删掉；没有，就是唯一的记录，拆成「哪句话 + 这一次的事实」。同一段句子里两种都有，是常态。

(386) **没有槽位时，作者会当场发明接缝，而接缝是找根因最快的指路牌。** 一个 `#` 把注释粘在公式后面，一个空格把第二句粘在第一句后面——两个都不是风格，是「载体少一格」的外化。搜产出方代码里的粘接符号，比搜自然语言更快指到缺的那一格。

(387) **删一条「复述」之前，要跑出来确认它真的在别处到达了读者。** 这一刀按复述删掉了 MTR 的方向，测试当场证伪：那条路径上台账不存在，方向只以 id 存在，而浏览器裸印 id。**「旁边有字段」不等于「读者拿得到词」**，中间还隔着一层渲染，而那层渲染可能对这条路径不成立。

### #395 档④第四刀：算出一个数的地方，把「这个数是从什么算出来的」写成了关于它的一句话（2026-08-24）

**现象**：第三刀之后还剩 8 条 kernel 自己写句子的信封路径，最大的一条是 `required_data.precision_target`——146 处里它一个人占 75。连同 `required_data.time_window`（1）与 `required_data.sutva_concerns`（2），这三条长在同一个模块群：`sample_size.py` 的六个估计器各返回 `(n, note)`，note 是一句中文散文。

**根因假设：一个算出数的地方，把「这个数是从什么算出来的」写成了关于它的一句话。** 六个估计器做的是同一件事——拿 α、power、效应量算出 n。数是一等公民，输入不是：效应量在信封上只以「那句话的文字」这一种形式存在。

**为什么是根因不是表象**——两条独立证据：

- **理由已经过期，形状留下了。** 那句话旁边的注释写着它「要进报告里的中文行」。在 HEAD 上核实：**没有任何 Python 读者面渲染 `precision_target`**，唯一的消费者是 prompt 里的 LLM。写成中文的理由今天是假的，而形状还在按这条假理由长。
- **真输入没地方放，假输入反而有。** 六个估计器的签名里带着 `z_alpha_2` / `z_beta` 两个形参，而它们各自的句子把「α=0.05、power=0.80」写死。全仓零个调用者传过。**一个没人转、转了会让旁边那句话变成假话的旋钮，不是功能**——它正是「输入不是一等公民」的孪生症状：假的输入有形参，真正的输入（h / d / 层数 / 采样点数）只能进文字。

**做了什么**

1. **`sample_size.Precision` 七个成员**（二值效应、连续效应、两条中介路径、逐层效应、目标分布、单比例、剂量-反应曲线）。六个估计器改成 `-> tuple[int, language.Statement]`，末行 `return total, language.state(Precision.X, …)`——**这一次的效应量成了槽位里的事实**，而不是句子里的一截字符。
2. **`z_alpha_2` / `z_beta` 两个形参删除**，降为模块常量，并在旁边写下删它的理由。
3. **`data_gap_report.Window`（1 个成员）与 `Sutva`（2 个成员）** 接掉另外两条，三个原来的模块级中文常量随之消失。
4. `types.py` 三个字段 `str | None` → `dict | None`（`precision_target` 的 docstring 里记下那条已被证伪的旧理由）；schema 三处改 `$ref: statedSentence`；生成器三张表；浏览器 `GapReport` 改用 `stated()`。

**顺带修掉的一处真错**：浏览器 `GapReport` 里「还需要什么数据」整块被 `variables` 非空 gate 住——一个只声明了 `data_type`、或只带 `n≥` 与精度目标的缺口，读者一行都看不到。现在拆成 `needed()`，每一项各自决定自己在不在。

**闸口**：两个反例逐个构造并确认 `SyntacticError`——洞里装着渲染好的整句、一句话没有 token；正面一臂（同一份 result 先验过再改）在场。另有两条正面闸口守这一刀真正立起来的东西：六个估计器**数与句子同出**（两个都答或都不答），以及**句子说的就是这个数算所用的输入**——改一个输入，两种语言里的话同时跟着变。

**度量**

- kernel 自己写句子的信封路径 **8 → 5**，实处 **146 → 68**。剩下的五条：`bounds_results[].data_required[]` 21、`bounds_results[].notes` 21、台账 `claim` 20、`describes[].said.why` 5、`selection_recovery.failure_reason` 1。
- 基线 8229 → **8295 passed / 181 skipped**。多出的 3 个 skip 已单独量过：`test_a_vocabulary_prints_as_the_word_it_is` 的身份检查从 28 跳到 31，正是新增的三个词表 `Precision` / `Window` / `Sutva`——`language.Word` 是 `EnvelopeName`，按设计放弃 `is` 同一性，由 #382 那条覆盖。
- mypy clean（143 files）；`npx tsc -b --force` 通过；`pnpm build` 已重建。

**当场声明的取舍**：台账的 `claim`（20 处）是 `id` 的纯函数，最省事的动作是把它删掉。这一刀不删——浏览器今天靠 `_EXACT` / `_PREFIX` 去匹配那句 claim 认路，删之前得先把那套匹配换成认 `id`。留给下一刀，按「说成一句话」而不是「删掉」处理；代价是这 20 处多活一刀。

**方法论沉淀**：

(382) **一个函数返回「一个数 + 关于这个数的一句话」时，句子里通常锁着这个数唯一的输入记录。** 判据不是句子的语言，是问「这个数是从什么算出来的，那些东西在信封上有没有自己的槽位」。没有，就说明这句话不是解释而是**唯一的记录**——它删不掉也翻译不了，只能拆成「哪句话 + 这一次的事实」。

(383) **代码里写着的「为什么这样写」是一句可以过期的断言，动手前要当场核实。** `precision_target` 的注释说它进中文报告行，而全仓没有一个 Python 读者面渲染它。理由过期而形状留下，是欠账最常见的存在方式；**先验证理由，常常会发现要改的比登记的更彻底**。

(384) **一个没人转、转了会让旁边那句话变成假话的旋钮，不是功能，是缺口的孪生症状。** 形参存在而无人传、同时另有一份硬编码的话与它矛盾，说明这一层的「输入」概念错位了：假的输入有形参，真的输入只能进文字。顺着这种旋钮找，比顺着散文找更快指到根因。

### #395 档④第三刀：一个槽位装得下一个词，装不下一句话——于是「里面还有一句话」的地方都提前渲染了（2026-08-24）

**现象**：第二刀的门（`state` / `spoke`）建好之后，剩下九条路径没有一条能直接走进去。逐条读代码，它们卡在四个不同的地方，而其中七条**根本不缺词表**——它们已经有词表、有模板、有槽位。

**根因假设：门只开在「信封的一个字段」这一层，没开在「一句话的一个槽位」这一层。** `halve` 见到 `Word` 成员就压成 `{vocabulary, token}` 收工，成员自己的事实没地方放；更装不下「好几句话」。于是任何「这句话里有一处要说另一句话」的地方，只能在 kernel 里把里面那句先渲染成串再塞进槽位。

**为什么是根因不是表象**：这七处写的不是散文，是**过早的渲染**——

- `describes[].said.why`（5 处）：`why=gaps.said(item, lang)`，把一个已经结构化的缺口语句在 kernel 里摊平成串。
- `describes[].said.variables`（2 处）：`", ".join(language.fill(_NOISY_MEASURE_SUMMARY, lang, …))`，把一列已经结构化的语句摊平**并且用半角逗号连接中文**。

过早渲染看起来和散文一模一样，因为它就是散文——只是有个模板。分辨它的指纹是**标点**：一个在 kernel 里 join 出来的列表，它的分隔符是作者的语言而不是读者的。

**做了什么**

1. **`halve` / `assemble` 认第三种槽位值**：一句话，以及一列这样的话。承载它的那一半本来就叫 `words`，不必改名——「一句话就是一个有洞的词」（第二刀立的那句）在这里第二次生效。`state()` 返回 `Statement`（`dict` 的子类：序列化时它就是那份 JSON，而类型是写方意图的证据，让槽位不必靠数键名来猜）；`assemble` 把 `spoken()` 换成 `spoke()`，列表用 `listing()` 连。**空序列仍然是值**——「有个洞要填『哪几个』而一个都没有」的句子，产出方本就不该发出来，渲染成空串会把这件事藏起来。
2. **`spoken()` 删除**。它只有一个调用者（`assemble`），而 `spoke()` 在裸词上与它逐字等价——一个函数的唯一调用者有了更好的门，它就没有了存在理由。
3. **schema 里 `spoken_word` 并进 `statedSentence`**：一个没有洞的词就是一个没有事实的句子，两个 `$def` 描述同一个形状必然漂。`words` 的值改成 `oneOf [statedSentence, array of statedSentence]`——于是**这个定义自指**，一句话里可以有一句话这件事是 schema 自己说出来的，而不是靠注释。
4. **浏览器四张索引表并成一张 `WORDS`**：`REFUSAL_VOCABULARIES` / `GAP_VOCABULARIES` / `STATED_SAYS` / `ALL_VOCABULARIES`（最后一张就是前两张的并集）。它们分开只是因为建的时间不同——一个洞能引哪个集合是**洞的事实而不是句子的事实**，代码注释早就这么写着。`assembled()` 少一个参数，词槽那一支整个变成对 `stated()` 的递归调用；`NOT_VOCABULARIES` 四条豁免变一条（顺带去掉一条重复登记的 `REFUSAL_VOCABULARIES`）。
5. **生成器多产出 kernel 的标点**（`BETWEEN_ITEMS` / `BETWEEN_SENTENCES` / `BETWEEN_CLAUSES` / `BETWEEN_STATEMENTS`）。它们不是词表——没有 token 没有成员——但是同一件「关于读者语言的事实」，而浏览器要在读者面前连接列表。手抄两个字符加一条闸口是 #399 刚拆掉的形状，所以生成。
6. **`data_gap_report.Measurement`** 是第一个走进新槽位的词表（两个成员），六个读者面全接齐。

**顺带修掉的两处真错**——都是同一个缺失机制造出来的，都只在英文侧才会暴露：

- 中文报告里那一列变量是用**半角逗号**连接的（`", ".join`），而中文的列表分隔符是「、」。现在由 `listing()` 在读者面前连接。
- 二分化那条里 `threshold:` 是**英文写死在中文句子里**的（`f"{pred} (threshold: “{cut}”)"`）。现在是 `Measurement.A_THRESHOLD_CUT_IT_IN_TWO` 的两种语言各自的文本。

**闸口**：契约必须对**装着渲染好的文本的洞**说不。三个反例逐个构造并确认 `SyntacticError`：整句已渲染、一列里有一个已渲染、一句话没有 token。第三个是形状检查，前两个才是这一刀守的东西——**一列里坏一个就整列拒收**，因为一个就足以让接缝变成别人的。正面一臂同时在场（同一份 result 先验过再改）。

**度量**

- 信封上 kernel 自己写的句子路径 **9 → 8**，实处 148 → 146。
- 新登记 **#447**：浏览器自己的列表标点——`verdict.ts` 与组件里约 10 处把「、」写死在代码里，英文侧全错。这一刀把 `BETWEEN_ITEMS` 送到了浏览器，那条的材料已经就位。
- 基线 8208 → **8229 passed / 178 skipped**（净 +21：新增闸口的三个反例与正面一臂，以及词表接齐的六个面各自的行）。多出的那 1 个 skip 已单独量过——`test_a_vocabulary_prints_as_the_word_it_is` 的身份检查从 27 跳到 28，是新词表 `Measurement`：`language.Word` 是 `EnvelopeName`，按设计放弃 `is` 同一性，由 #382 那条覆盖。
- mypy clean（143 files）；`npx tsc -b --force` 通过；`pnpm build` 已重建。

**当场声明的取舍**：生成的四个标点里，浏览器今天只用到 `BETWEEN_ITEMS`。导出完整的四个而不是用到的那一个——它们是 kernel 标点的**闭集**，只导一个是在这里再做一次「哪个重要」的判断，而那个判断的正确位置在使用它的地方。代价是三个当前没有消费者的导出。

**方法论沉淀**：

(379) **一个载体能不能装「里面还有一句话」，决定了它上游会不会写散文。** 把载体的能力按「它能装什么」列出来——值、词、一句话、一列句子——缺哪一格，上游就会在那一格上用提前渲染补。判据不是「这里为什么写了散文」，而是「这里要不写散文，载体得能装什么」。

(380) **过早的渲染是散文的第二种形态，它的指纹是标点。** 一个在产出方 join 出来的列表，分隔符是作者的语言而不是读者的；一句在产出方 `fill` 出来的话，它的语言是产出方选的。所以找过早渲染最快的办法是搜产出方代码里的标点常量与 join，而不是搜自然语言。

(381) **当新形状是旧形状的超集，正确的动作是让旧形状消失。** 并列声明两个描述同一件事的定义（schema 的两个 `$def`、浏览器的四张索引表）只有一个理由——它们是不同时候建的——而这个理由不是理由。合并之后 `words` 指回 `statedSentence`，「一句话里可以有一句话」变成定义自己说的话。

### #395 档④第二刀：把「一句话 + 它的事实」变成一扇门——散文是没有门时系统必然的产物（2026-08-24）

**分母先更正。** 第一刀报的「10 处 kernel 写的句子」是在 `run` 语料上量的——**那批程序里没有估计器跑过，于是没有估计器写过东西**。补上数据端（backdoor / front-door / IV / 不可识别，各带 bootstrap）重量：**20 条路径**，其中调用方自己的话 5 条（#436 的 `x-text` 已声明，不算欠账），**kernel 自己写的 13 条 / 148+12 处**。多出来的三条正是只有估计器才写的：`precision_budget.hint`、`sensitivity_analysis.note`、`mechanism_audit.summary`；台账的 `claim` 从 5 涨到 20，`summary` 从 1 涨到 4。

**根因假设：这个仓把「一句话 + 它的事实」这个载体实现了三遍，而没有一遍是第四个地方能直接用的。**

| 实现 | 物种 | 句子表 | 槽位 |
|---|---|---|---|
| 缺口 | `gaps.Sentence` | `gaps.DESCRIBES` | `said` / `words` |
| 拒答 | `refusals.Refusal` | `refusals.SAYS` | `details` |
| 句内的词 | `language.Word` | **成员自带**（最干净的那份） | — |

三份都焊死在自己那条通道上。于是任何一个**第四个**「我手里有几个值，要对读者说一句话」的地方，面对的成本是：把句子写下来 = 一行 f-string；给它一个 token 和一张表 = 再实现一遍载体。**散文是结构化一句话没有门时，系统必然产出的东西。** 这解释了为什么前十二刀每次都在新的地方重新发现同一个形状——第一刀之所以能一次清干净，正因为缺口那条通道**已经有**这扇门（#437 建的）。

**逐句问第一刀那个判据（「这句话说的事实，信封上还有没有第二处结构化地记着」），13 条分成两半：**

**一半是复述，删。** 五处，全部实测确认：

- `assumption_ledger.summary`——两个数都是旁边那张表数出来的。**验证器只能靠在这句话里搜中文子串 `依赖 {n} 条假设` 来查它**：一条只能用一种语言写的规则，查的是 kernel 用一种语言写的字段，检查和缺陷是同一件事。
- `mechanism_audit.summary`——form / method / 每个 id 的词 / 谁定的，全在 `mechanisms[]` 里。它还是 `classify_assumption(...)['claim']` 的一个消费者。
- `llm_proposed_review.summary`——两个计数就是它下面那两个数组。
- `precision_budget.hint`——三个数就在同一个 dict 和 `numeric_estimate.sample_size` 上。**浏览器早就独立判过同一件事**：`types.ts` 的注释写着「Three numbers and an English sentence restating them. The sentence has one reader, which prints it raw; this surface builds its own line from the numbers」——判了，写下来了，没人动手。这是第一刀「三处独立记录各自量到同一件事」的第四次。
- `sensitivity_analysis.note`——**一个字段两份职责**（#430 的形状）：有 E 值时它复述旁边四个数（外加连续路线上一句由 `path` 决定的近似说明）；没有 E 值时它是**四个原因里是哪一个的唯一记录**。前一半删，后一半留下来成为一个词。

**另一半是「某个事实唯一的记录形式」，给结构。** 本刀先建门，再用它落第一处。

**做了什么**

1. **`language.state()` / `language.spoke()`**——两个函数，二十行。写方交出一个 `Word` 成员和它的槽位值，读方拿回这一句。信封上的形状是 `{vocabulary, token, said, words}`——**和一个槽位里的「词」（`spoken_word`）完全同形**，因为一句话就是一个有洞的词，而信封本来就有「一个词」这个形状。schema 里叫 `statedSentence`，`gapSentence` / `gapRoute` 是它把 vocabulary 焊死在字段上的两个特例。
2. **`sensitivity.Undefined`** 是它的第一个词表（四个成员，各自带两种语言的文本）。`EValueResult.note: str` → `undefined_because: dict | None`；五处复述的 `_SAID` 行、`_note` / `_evalues_said` / `_format_note` / `_format_continuous_note` 全删。
3. **五处复述删除**，四处读者面改成自己组句：主报告的精度行从三个数组、E-value 行从四个数加 `path` 组、台账摘要走新的 `ledger.summary(entries, lang)`（与 `gaps.summary` 同形——那条路 #437 已经走过一次）；浏览器的台账摘要在组件里数，并**补上它一直缺的那一行**：E 值无定义时它以前什么都不显示，因为原因藏在一个它读不了的句子里。
4. **验证器少一条规则**：`_check_summary` 整个删掉。不是放松——**不存的计数不可能和被它计数的东西矛盾**，而新闸口守的是「它没被存」：信封契约拒收这个字段，测试用反例把它装回去并确认 `SyntacticError`。
5. **词表六个面全接齐**：`reader_words` 一行 → `kernelWords.generated.ts` 重生成 → `verdict.ts` 的 `VOCABULARIES` + `stated()` → `test_vocabulary_reach` 一行 → prompt。**这正是这扇门要证明的事**：新增一个「有事实、要说话」的地方，现在是加一行表，不是再造一个通道。

**顺带修掉的一处假话**：`sensitivity_analysis` 在连续路线上的近似说明，以前是 kernel 写死在句子里的一截；现在由 `path == "continuous"` 推出来，由读者面说。同一个值决定的事，不该有第二个作者。

**度量**

- 信封上带句子的路径 **20 → 16**；kernel 自己写的 **13 → 9**，实处 160 → 148。
- `result_orchestrator.py` 单语欠账 **10 → 1**，`sample_size.py` **7 → 6**——走掉的九条是那三个 summary，第七条是 `hint`。**删掉的散文不用翻译**，第一刀的这条结论第二次生效。
- 基线 8185 → **8208 passed / 177 skipped**（净 +23：新增闸口与拆开的断言；多出的那 1 个 skip 已逐条对过两份 -rs 清单——是新词表 Undefined：language.Word 是 EnvelopeName，按设计放弃 is 同一性，那条身份检查对它跳过，由 #382 那条覆盖）。mypy clean（143 files）；`npx tsc -b --force` 通过；`pnpm build` 已重建。

**当场声明的取舍**：`statedSentence.token` 在 schema 里是 `string` 而不是 enum——一扇对所有词表开放的门，schema 枚举不了它还不知道的集合。把集合关起来的是旁边的 `vocabulary`，两端由 `test_vocabulary_reach` 的那一行钉住；代价是**这一条的成员完备性靠测试而不靠 schema**，换来的是第四、第五个通道不必各自再造一次载体。

**剩下的九条，第三刀的分母**：`required_data.precision_target` (75)、`bounds_results[].data_required[]` (21)、`bounds_results[].notes` (21)、`assumption_ledger.assumptions[].claim` (20)、`describes[].said.why` (5)、`required_data.sutva_concerns[]` (2)、`describes[].said.variables` (2)、`required_data.time_window` (1)、`selection_recovery.failure_reason` (1)。其中 `claim` 已查明是**第一刀的形状**——`classify_assumption` 的 docstring 自己写着「only `claim` moves with `lang`」，而 `_EXACT` 以 id 为键、`_PREFIX` 从 id 切后缀，所以 `claim` 是 `id` 的纯函数，而 `id` 就在同一个条目上。

**方法论沉淀**：

(375) **散文是「结构化一句话没有门」时，系统必然的产物。** 判据不是「这里为什么写了散文」，而是「这里要不写散文，得付多少」。同一个载体被实现三遍且每遍都焊死在一条通道上，第四个地方写散文就不是疏忽而是理性选择。修法是把载体提出来变成一扇门，不是逐处翻译——翻译只让 kernel 有两种语言可选，选的人还是 kernel。

(376) **一次刀法的判据，分母通常大于发现它的那个字段。** 第一刀的判据（「这句话说的事实，信封上还有没有第二处结构化地记着」）在 `explanation` 上成立，闸口却只守缺口。逐句拿同一个判据去问剩下的每一条，13 条里有 5 条当场落到第一刀那一半。判据要单独登记并逐条施用，别让它跟着发现它的那个字段一起下班。

(377) **一个字段可以一半是复述、一半是唯一记录。** `note` 有 E 值时复述四个数，没有时是四个原因里哪一个的唯一记录。判据答「一半一半」时，正确的动作是**把字段拆开**，而不是二选一——两半的修法相反：一半删，一半给结构。

(378) **量分母时，先问「这批语料能不能跑到那条路」。** `run` 语料一个估计器都没跑，于是三条只有估计器才写的路径在分母里根本不存在，而报告出来的数字看不出这件事。判据：分母连同**它是在哪条执行路径上量的**一起登记；换一条路径重量一次，是登记的一部分而不是复核。

### #395 档④第一刀：信封上最后一段散文没有自己的内容——它是一次渲染，而渲染发生在没人知道读者是谁的时候（2026-08-24）

**现象（实测）**：一份最普通的 effect 查询，信封上只剩 **1 条**中文散文——
`results[].explanation`。同一份信封上，缺口是这样的：

```json
{"sentence": "the_intervention_says_neither_state_nor_event",
 "said": {"intervention": "x"}}
```

而 `explanation` 里是**同一件事**的 400 字中文段落。

**根因假设：`explanation` 没有任何原创内容。** 它每一行都是别处的复述——
一条缺口的句子，或者估计块里已经躺着的一个数。三处独立记录早就各自量到了
这件事，只是没人把它们并起来读：

| 记录 | 说了什么 |
|---|---|
| `types.py` 的注释 | 把它叫作 *derived view*，并写着 "the join happens at the default" |
| 浏览器的 `CARRIED_BY` | 一次全量跑里 4857 条 ⚠ 行，**4569 条**是缺口描述逐字复制；45 条是估计器给自己刚归档的缺口另写的一遍；剩下 246 条与所在信封矛盾 |
| `types.REACHES_EXPLANATION` | 每一条到达 `explanation` 的 ⚠ 行都对应一个**已经在缺口报告里**的 GapKind |

`dispatch.py` 里五个 ⚠ 站点把这件事写在同一屏上：先 `DataGap(kind=…,
describes=tuple(said))`（物种 + 具名槽，无语言），紧接着一句手写中文 f-string。

**为什么这是根因不是表象。** 一份必须被不断重新推导才不会过期的派生视图
（`_withdraw_caveat_lines` 整套机制就是为此存在的），根子上不该被**存**下来。
而只要它还在信封上，它就必然在 kernel 里定型——「读者要哪门语言」在它身上
永远问不出口，加 `Lang.EN` 也救不了它。**一个没有自己内容的字段是一次渲染；
一次存进信封的渲染，是在没人知道读者是谁的时候写好的。**

**它为什么活到今天，也是量出来的。** 三个读者面里，Python markdown 报告和
浏览器**都已经不读它**（浏览器把它登记为 `CARRIED_BY: data_gap_report`）。
只剩渲染 prompt 读，而 prompt 读它是因为**它是 LLM 唯一拿得到缺口句子的地方**：
#437 把缺口改成 `{sentence, said}` 之后，prompt 从来没有获得过读这个形状的
说明——它有 `alternative_paths` 的 `{route, said, words}` 那一节，没有对应的
`describes` 那一节，而第 216 行还指着 #437 已经删掉的 `description` 字段。
**散文以散文的身份活下来，是因为有一个读者还只会读散文。**

**做了什么**

1. **字段删除**，八个写入点一起走：`scheduler._attach_structural_caveats`
   （+ `_LEGACY_MUST_DISCLOSE_GAP_KINDS`、postprocess 里那一趟 pass）、
   `dispatch` 五处 ⚠ headline、中介比例 headline、`_withdraw_caveat_lines`
   与 `types.mirrored_caveat_lines`。schema 槽位、`QueryResult` 字段、
   `result_orchestrator` 的序列化一并删。
2. **三分变两分。** `MIRRORED_INTO_EXPLANATION` / `ESTIMATOR_TIME_FINDINGS` /
   `GAP_REPORT_ONLY_ASKS` 里，前两个的差别**只是谁打的字**——
   `ESTIMATOR_TIME_FINDINGS` 自己的注释写着「它们确实限定答案，只是由估计器
   用自己的话写进 explanation，再抄一遍缺口描述就会说两遍」。没人打字了，
   两半就没有东西能把它们分开：`QUALIFIES_THE_ANSWER`（限定答案，读者面
   **领着走**）/ `ASKS_FOR_SOMETHING`（要东西，读者面**列出来**），
   仍是对 `GapKind` 的划分，未分类仍在 import 期抛。
3. **prompt 补上它一直缺的那一节**：`#### 什么是一条缺口在说（describes）`，
   与它下面的 `alternative_paths` 一节同形——token 是每个读者相同的事实，
   措辞是某一门语言的。必读通道从「`explanation` 每一行」改成「`kind` 在
   caveat 表里的每一条缺口」，表里补齐 6 个估计器物种。
4. **闸口换主体**（`test_a_rendering_is_not_a_thing_the_envelope_carries.py`）：
   旧文件守的是两份存档同步，这条性质现在由构造保证——只有一份就不会不同步。
   新闸口守的是**没有第二份**：一条缺口说出来的句子，不得出现在信封上任何
   别的地方。配一条反例测试，按被删掉那趟 pass 的写法把 ⚠ 行装回去，闸口拒收。

**顺带量出的两件事，都记在这里**

- `dispatch.py` 的单语欠账 **21 → 9**：走掉的 12 条是给这个字段写的 ⚠ 句子，
  它们欠的第二语言不必再写了。**删掉的散文不用翻译**——这是这一栏能变短的
  第二条路，第一条是 #405/#432 那种「句子归物种所有」。
- **信封上还剩多少句子，量了**（21 个程序，L3 语料 + postprocess 语料）：
  **17 条路径**。其中调用方自己的话（`ambiguities[].note` / `description`、
  `annotations.source`、`confidence_sources[].source`）按 #436 的 `x-text`
  声明不算欠账；kernel 自己写的还有 **10 处**——`required_data.precision_target`
  (75)、`bounds_results[].data_required[]` (16)、`bounds_results[].notes` (16)、
  `assumption_ledger.assumptions[].claim` (5)、`describes[].said.why` (3)、
  `required_data.sutva_concerns[]` (2)、`describes[].said.variables` (2)、
  `required_data.time_window` (1)、`assumption_ledger.summary` (1)、
  `selection_recovery.failure_reason` (1)。**这十处是档④第二刀的分母，而它们
  的修法不是翻译**：翻译只是给 kernel 两种语言去选，选的人还是 kernel。

**当场声明的取舍**：渲染 prompt 现在必须自己从 `{sentence, said}` 组句，而不是
逐字引用一段现成的话。代价是同一条缺口在两次回复里的措辞可以不同；换来的是
措辞属于读者而不属于 kernel。这正是 #391 给 `reason`、#437 给缺口报告做过的
同一次交换，两次都判过一样。

基线：8187 → **8185 passed / 176 skipped**（旧闸口文件 8 条换成新闸口 8 条；
净 −2 来自被删掉的字段自己带走的参数化）。mypy clean（143 files）；
`npx tsc -b --force` 通过；`pnpm build` 已重建。

**方法论沉淀**：

(371) **一个没有自己内容的字段是一次渲染。** 判据：逐行问「这句话说的事实，
信封上还有没有第二处结构化地记着」。全是，那它就不是字段，是视图——而视图
不该被存，因为存下来的视图有版本，视图的版本会错。#437（缺口报告）与本条
（explanation）是同一判据的两次应用，两次的分母都是「一次全量跑里的每一行」。

(372) **一次「必须同步的派生」应当先被问「为什么要存」。** 修同步是对的，但它
把问题定格在「两份怎么保持一致」，而不是「为什么有两份」。判据：修完同步之后
再问一次「删掉其中一份，谁会缺东西」；答案是「某一个读者」时，去看那个读者
为什么只会读这一份——本条的答案是 prompt 从没被告知新形状怎么读。

(373) **散文活下来，通常是因为还有一个只会读散文的读者。** 三个读者面里两个
已经不读了，第三个读是因为它拿不到别的。判据：要删一处渲染之前，逐个读者面
问「它读这个字段，是因为需要这件事，还是因为只有这里有」；后者要补的是那个
读者的读法，不是保留那个字段。

(374) **两个集合的差别如果只是「谁打的字」，那它就不是一个区分。**
`MIRRORED` 与 `ESTIMATOR_TIME` 的分界线是作者身份，而作者身份来自一个正在被
删掉的机制。判据：拿掉那个机制之后，还有没有任何一句关于这两组的话是不一样的。

### #326 一张选择图属于一个源人群，而代码只有一张图——于是两个源的程序和一个源的程序输出逐字节相同（2026-08-24）

**问题本身。** 跨人群迁移里，用户声明的是若干个 `selection_node`，每个都带着自己的 `source_population`：「目标人群和**这一个**源在这个变量上分布不同」。Bareinboim-Pearl 的对象是**一组**选择图 `{D^(1)…D^(n)}`——共享同一张底层 G，各自带自己的 S 集、自己的可容许调整集、自己的答案。代码里只有一张：`build_selection_diagram` 把所有节点并进同一张图，三处调用点读 `selection_nodes[0].source_population`。

**这不是「多源没实现」，是「第二个源被静默丢掉」。** 两者的区别是可观测的：一个声明了 `rct_us` 和 `rct_eu` 两个源的程序，产出与只声明 `rct_us` 的程序**逐字节相同**——同一个公式、同一个源标签、同一条缺失参数。信封上没有任何一处能让读者发现 `rct_eu` 被扔了。判据式的验证：两个源分别移动 `z1` 和 `z2` 时，正确答案是 `rct_us` 调整 `{z1}`、`rct_eu` 调整 `{z2}`，而并成一张图的答案是**两个都调整 `{z1,z2}`**——于是系统向持有 EU 数据的读者要 US 的分层条件分布。

**表示改完，其余是它的推论。** `SourceDiagram(source_population, diagram, s_atoms, s_node_ids)` 一个源一份，`build_selection_diagrams` 按 `source_population` 分组；`identify_from_source` 是原来那个判据只看一张图，`identify_across_sources` 把它跑遍每一张。**单源是分组只有一个成员的情形，不是另一条代码路径**。`TransportIdentificationResult` 多了 `source_population` / `s_node_ids` / `blocked_by`，最后一个把两句中文 `failure_reason` 换成两成员封闭词表（`treatment_or_outcome_off_diagram` / `no_s_admissible_set`），这个文件的单语债因此归零。

**「能迁」是存在量词，「缺什么」是全称量词。** 效应可迁 ⟺ **某个**源可迁；而读者要知道的是**每个**源各自卡在哪、各自还差什么。所以信封上的 `sources[]` 一个源一项，可迁的带估计量、不可迁的带物种，两者互斥（schema 用 `if/then/not` 钉死，不许出现空串当「没有」的第二种拼法）。没有一个源可迁时，每个源一条缺失项，名字是 `transport:{源}->{目标}`；都可迁但 θ 不全时，每个源一条**它自己人群、它自己 Z** 的缺失参数——`P_rct_us(y|x,z1)` 与 `P_rct_eu(y|x,z2)`，正是缺陷的逆命题。

**两个源都算出数时，它们相等是一条可被数据否掉的限制。** 同一个目标量的两个估计量，θ 是**声明**的而不是估出来的，所以差距超过浮点漂移（`1e-9`，与 `_IV_WEIGHT_TOL` 同一标准）只能是所给分布**否掉了至少一张选择图**——与 `OVERIDENTIFICATION_REJECTED` 同族。这时**一个数都不报**：报其中任何一个都是替读者选了信哪一张图。新 `GapKind.TRANSPORT_SOURCES_DISAGREE` 是 `MISSING_ITEM_GAPS` 里唯一的证伪物种，也是唯一不带 `alternative_paths` 的——其余物种都能说出「去取什么」，这一条要改的是一句声明。它同时把 `answer_tier` 打到 `none`：识别没失败，而没有数，因为两个数不能都是它。

**验证器重算「扣住」这件事本身。** `verify_transport_sources`（kernel 无条件调用，不看状态——扣住那一支停在 `structurally_solved`，而它恰恰是最该审的那支）从块自己记的逐源数重新导一遍：报了数，就要求每个算出数的源都到了这个数、`agreeing_sources` 等于算出数的源数；没报数，就要求确实有两个源不一致。**一个把两个冲突值中的第一个报出来的产者，和一个把本该报的数藏起来的产者，都在这里被抓住**。容差与两成员词表验证器各抄一份。

**审计的「独立」在这条上曾经是假的。** `_rule_s_admissibility_check` 原来也把所有声明节点并成一张图重新导——**两边持有同一个建模假设，于是重复不是独立，是同一个错误被存了两份**，而审计抓不到它自己也犯的错。改成读 `inputs.selection_nodes_ids`、按 id 解析回 `ctx.selection_nodes`、跨源的步骤直接拒。

**语义闸口：一组对象在哪个维度上可以不一致，就是这组对象的定义。** 选择图在 `source_population` 上不一致——那正是多源；在 `target_population` 上不一致，就是一份程序在断言两件互不相容的事（一个问题只有一个目标人群），没有哪条路线比另一条更对，所以**拒**。同族地，查询问的目标人群不在任何声明的图里也拒。`SelectionNode.target_population` 在此之前有零个读者。

**度量（两个源，各移动一个变量，`z1,z2 → x`、`z1,z2 → y`、`x → y`）：**

- **两源同意**：`rct_us` 与 `rct_eu` 各自算出 0.50，`agreeing_sources = 2`，报一个数并说出「另外 1 个源算出同一个数」。
- **两源不同意**（EU 侧目标边际 0.5 → 0.9，EU 路线落在 0.34）：`structurally_solved`、**没有 `numeric_result`、块上没有 `numeric`**、缺口 `transport_sources_disagree` 带 spread `0.16`、`answer_tier = none`，两个冲突值留在各自路线上作为证据。
- **一个源迁不过来**（EU 的 S 节点落在结局上）：EU 路线 `no_s_admissible_set` 且不带数，US 路线照常答，`agreeing_sources = 1`。
- **都迁不过来**：两条 `transport:rct_us->real_world` / `transport:rct_eu->real_world`。
- **θ 全缺**：两条缺失参数，人群与 Z 各不相同。

四种情形 `themis.verify` 全通过。

**顺带修的两处，都不是这条路线自己的病：**

1. **`transport_not_identifiable` 的 `{detail}` 两边说的不是一件事。** 句子写的是源人群名，调度器传的是 `blocked_by`——于是读者看到「源人群 `no_s_admissible_set` 找不到调整集」。物种归物种（在块上，有自己的词），名字归名字。
2. **逐源数原来按位置写回块。** `working` 跳过了不可迁的路线而块保留全部，两者索引错位；改成按 `source_population` 索引——**一条路线就是它的源域**，位置不是它的身份。

**取舍与边界，明说：**

- **判据仍是「可调整」这一个充分条件**（Bareinboim & Pearl 2014 Theorem 1），只是从问一次变成每个源问一次。**没有覆盖的是把目标估计量拆成几个源各授权一块**（mz-transportability，`TR^mz`）——那不是这条判据的多源补课，是一套 ID 式递归，而它的**单源形式在这里同样不存在**。所以没有任何单个源能迁的目标，如实报成如此并说出每个源各自的理由，而不是猜。
- **数据端（DataFrame）在多个源同时可迁时不选，直接 `design_unavailable`。** DataFrame 上没有人群标签，替读者挑一个源等于替他选一份数据。
- **`treatment_or_outcome_off_diagram` 的端到端见证不存在**——查询原子不在 V 里会更早被 `_check_query_atoms_in_V` 拒掉，所以这个物种钉在 `identify_from_source` 这一层。

- **全量 8154 → 8187 passed / 176 skipped**（+33：新闸口文件 28 条，其余是既有参数化闸口的分母跟着新词表与新缺口物种长出来的）。mypy clean（143 files）；`npx tsc -b --force` 通过；`pnpm build` 已重建 `dist`。

**方法论沉淀：**

**(367) 一个字段若挂在集合的每个成员上，那它就是每个成员自己的事实；把它当成整个集合的事实读，等于读了第一个成员的。** 判据不是「代码里有没有 `[0]`」，是**这个字段的宿主是谁**：`source_population` 写在每个 `selection_node` 上，就说明它是节点的事实，那么读它的地方要么按它分组，要么在丢信息。这类缺陷最难发现的地方在于**输出仍然是良构的**——N 个源和 1 个源产出同一份合法信封，没有任何字段变成 null、没有任何断言失败，只有一个从未出现的第二条路线。附带一条：**要证明这种缺陷存在，就构造一个让被丢掉的成员给出不同答案的例子**；成员们答案相同时，丢与不丢看起来一样。

**(368) 重复只有在两边不共享同一个建模假设时才是独立。** 验证器不 import 产者，只保证了两边不共享**代码**；两边若都相信「这里只有一张图」，那么重复的是**同一个错误的两份**，而审计抓不住它自己也犯的错。判据：不要问「这两份实现会不会不一致」，要问「**它们对被审对象的形状有没有共同的信念**」——有，那份信念就是审计的盲区，得由别的东西（schema、闸口、或者把形状本身变成审计的输入）来守。

**(369) 同一个量的两个估计量，「它们相等」是一条可被数据否掉的限制；这时不报数比报其中任何一个都强。** 判据是**这两个数的差来自哪里**：来自抽样，那是噪声，该报点加区间；来自声明（θ 是给定的、图是画的），那是矛盾，再多同样的数据只会再矛盾一次。报其中一个等于替读者选了信哪份声明，而他连有两份声明打架都不知道。附带一条：**扣住也是一次断言，也要被审**——一个能把不存在的数编出来的产者，同样能把该报的数藏起来，两个方向要用同一份重算去守。

**(370) 一组对象在哪个维度上「可以不一致」，就是这组对象的定义；在别的维度上不一致就是矛盾，该当场拒。** 选择图在源人群上不一致正是「多源」，在目标人群上不一致是一份程序在断言两件互不相容的事。判据：把这组对象的**存在理由**写成一句话，那句话里变化的那一维就是允许不一致的维，其余每一维的不一致都没有「哪条更对」的答案，因而只能拒——**任何一种自动挑选都是在替调用者做他没授权的决定**。

### #325 一个干预是一份「赋值」，而它被存成「一个集合 + 一个大家共用的值」——于是混合角点不是没实现，是说不出来（2026-08-24）

**问题本身。** 两个处理一起干预、图上只有 general-ID 能识别时，系统只答一个数：全处理格对全对照格的对比。K 阶交互——「一起上」比「各自上之和」多出来的那一块——从来不答。而联合后门那条路是答的，同一个信封字段就在那儿空着。

**根因不在估计层，在表示层。** `identify_via_tian` 的签名是 `(x_atom, y_atom, x_value)`，联合那条路的调用方给的是**一个处理集合 + 一个大家共用的取值**。集合加一个值只能命名**均匀角点** `do(X=v，对所有 X)`；`do(A=1, B=0)` 这种**混合角点在接口层写不出来**——不是没实现，是说不出来。而 K 阶交互是 2^K 个角点上的有限差分，其中 2^K−2 个是混合的。

`_IdState` 里这件事以两个字段存着：`do_atoms` 和 `x_value`。ID 递归的 Line 7 干的正是「把某个处理从 do-集合里拿掉」，而**拿掉一个原子和拿掉它的值是同一件事**——两个字段意味着可以只发生一半。改成一个 `x_values: Mapping[Atom, object]`，`do_atoms` 变成**从它推导出来的属性**（`frozenset(self.x_values)`），四个读点各自塌成一次字典查表。新的公开入口 `identify_via_tian_joint(graph, bidirected, x_assignment, y_atom)`：赋值本身**就是**干预，一个角点是一个参数，不是一个集合加一个所有成员都得共享的档。单处理入口是 |X|=1 的那个特例，闸口按公式相等钉住。表示改完、一行行为还没加时，465 条 ID 子集全绿——这条改动是**行为保持**的。

**识别是值盲的，所以走盒子的是估计量不是识别。** `identify_via_tian_joint` 只看图，不看角点取到什么值：要么每个角点都识别，要么一个都不识别。于是 2^K 个角点各拿一份估计量，**失败只可能来自数据**（那一格没有行），不可能来自识别。交互本身是 K 阶混合有限差分（VanderWeele 2015 ch.14）：`Σ_角点 (−1)^{处于对照档的个数} P(Y=y_hi | do(角点))`，低阶项被交错和消掉，剩下顶阶。

**「给不出」是两个物种，写成两成员封闭词表而不是第二段中文散文。** `corner_unsupported`（盒子走过了，某个角点没有任何一行数据）与 `order_above_cap`（K 超过 `MAX_JOINT_TREATMENTS = 5`，盒子根本没走）。两者都**不动对比**——对比只要两个角点，多宽的盒子都只要两个——所以这是**扣住一项**，不是拒答。词表化顺手还掉了 `themis/estimation/joint.py` 两条单语债里的一条（那句「给不出」原来是估计器里拼出来的中文）。

**验证器重算，不重读。** 信封上新增 `corner_risks`：每个角点的干预风险。对比是其中两个的差，交互是全部 2^K 个的交错和，于是 `verify_joint_general_id_numeric` 把两个数**各自重新导一遍**，而不是读出来再看一眼——与 `over_identification.sufficient_statistics`、`anderson_rubin_region.sufficient_statistics` 同型。符号规则验证器按定义自己写了一份（一个角点的符号是「有几个处理处在**对照**档」的奇偶），两个物种名与上限常数也各自抄了一份：验证器 import 产者的那份，等于让它审自己的拼写。

**顺带修的两处，都不是这条路线自己的病：**

1. **`answers.SHAPES_OF["joint_general_id_plugin"]` 是 `(POINT,)`，而它产出的是一个裸点。** 同一个形状经由另一条路早就有名字（`JOINT_CONTRAST`，`lives_in = "joint_effect"`）。声明与产出不一致，是因为这条路当初只能说出均匀角点——形状是被表示层的天花板压出来的。
2. **`joint_effect` / `interaction` 底下的 `precision_budget`，schema 从这个块存在起就声明了，而两条联合路线一条都没写过。** 扁平那个助手读的是 `numeric_estimate.point`——联合答案没有这个键，于是「答案是一个对比」的地方精度预算整个消失。新增 `_attach_precision_budget_joint`，两条联合路线共用。

**新终结规则 `numeric_joint_general_id_estimate`。** 分派看的是推导链的终结规则（#324 的 (360)），所以联合答案得走自己那条规则，而不是蹭单处理那条——否则 `point` 和 `joint_point` 就成了同一个槽位的两种拼法。角点 / 符号 / 格三样原来在两条联合路线里各写一遍，收进新模块 `themis/estimation/treatment_box.py`。

**度量。** 潜变量 SCM：K 条各自带 latent 混杂的前门（`X_i → M_i → Y`、`X_i ↔ Y`），Y 的机制除一个顶阶乘积项外可加，所以两个 oracle 都是**闭式**而不是 Monte-Carlo：`E[Y|do(x)] = c0 + Σ c_i·p_i + c_K·∏p_i + Σ d_i/2`，交互 `= c_K·(0.9−0.1)^K`。（每个系数都让这个概率落在 [0,1] 内——不是整洁，是必须：Bernoulli 抽样会把越界的概率静默截断，于是 oracle 和它自己的数据不一致，账却记在估计量头上。第一版探针正是这么产生了一个 −0.015 的假偏倚。）

- **K=2 收敛**（解析交互 0.16）：n=5万 / 20万 / 80万 / 320万 上逐角点最大偏差 **0.00954 → 0.00483 → 0.00295 → 0.00167**，交互 **0.14874 → 0.16002 → 0.15623 → 0.15927**。
- **可加 DGP**（同图，去掉乘积项，交互真值恰为 0）：交互 **−0.00052**，而对比 0.21840（真值 0.216）——「≈0」是关于交互的事实，不是关于整个估计的。
- **K=3**（三阶交互真值 0.1024，无成对项）：n=60万 上 **0.11164**。三阶有限差分放大噪声，偏差比 K=2 大一个量级，这是有限差分的性质不是估计量的。
- **端到端** n=20万、60 次 bootstrap：`numerically_solved`，对比 **0.4109** [0.3999, 0.4195]（真值 0.416），交互 **0.1600** [0.1500, 0.1762]（真值 0.16），四个角点风险齐备，两个块各带精度预算，`themis.verify` 通过。

**取舍与判断，明说：**

- **`corner_unsupported` 的端到端见证在联合后门那条路上，不在这条。** 一个角点能单独塌掉，要求估计量的每个因子都读在**该角点自己的格**上；而估计量长成那样的图，`{A,B}` 到 Y 就没有关不掉的后门路径，于是 dispatch 会先走调整集那条路答掉。这条路线上的同一物种因此钉在估计器层（`A→M←B, M→Y, M↔Y`，A 与 B 永远同步，两个混合角点无行）。两条前门那种图上，估计量带着一项 `Σ_a' Σ_b' P(a')·P(b')·P(y|a',b',m)`——**它对所有角点是同一项**，所以它缺的格是每个角点都缺的格，对比会跟着交互一起塌。**角点支撑是估计量形状的性质，不是盒子的性质**（实测过：那张图上 A≡B 时整份估计拒答，不是扣交互）。
- **超上限那一支只识别对比的两个角点。** 盒子既然不走，就不去识别 2^K 个公式——`order_above_cap` 是关于「这个程序不做这趟枚举」的陈述，不是关于数据的。闸口把 K=5（在上限上，交互照给）与 K=6（越界，扣交互而对比照报）并成一对参数化，单看任一半都验不出区别。

**已知边界，明说：** 联合后门那条路仍然不记 `corner_risks`，所以它的两个数由它自己那条终结规则按别的判据审，而不是被重算。两条路线在「答案的形状」上现在一致，在「可重算性」上还不一致。

- **全量 8117 → 8154 passed / 176 skipped**（+37：新闸口文件 25 条，其余是既有参数化闸口的分母跟着新块与新词表长出来的）。mypy clean（143 files）；`npx tsc -b --force` 通过；`pnpm build` 已重建 `dist`。

**方法论沉淀：**

**(363) 一个能力缺口若长在接口的签名上，它读起来会像「没实现」，而实际上是「说不出来」。** 判据：把缺的那件事**当成一次调用写出来**——参数填得进去吗？填不进去，那就不是估计层的活，是表示层的。这一次填不进去的是 `do(A=1, B=0)`：签名收的是集合加一个共享的档，而混合角点要求每个原子带自己的值。附带一条：**一个「集合 + 每个成员共享的属性」几乎总是一份「映射」被压扁的结果**，压扁掉的那一维就是后来说不出来的那些取值。

**(364) 两个字段若必须一起变，就让其中一个从另一个推导出来。** `do_atoms` 与 `x_value` 是同一件事的两半，而 ID 递归的 Line 7 正是「拿掉一个处理」——两个字段允许只发生一半，一个映射加一个 `@property` 不允许。判据不是「它们现在会不会不同步」，是「**有没有一个操作在语义上同时动它们两个**」；有，就说明其中一个是另一个的函数。

**(365) 一个「给不出」要说清是**这批数据**给不出还是**这个程序**给不出，而这个区分只有在它是词表成员时才守得住。** 写成一句散文，两件事会长成两句读起来差不多的话；写成两成员的封闭词表，验证器就能对**每一个**成员问「你这句话立得住吗」——`order_above_cap` 是关于 K 的断言（K 在同一个块上），`corner_unsupported` 是关于盒子的断言（盒子在它旁边）。附带一条：**这两种缺席都不动它旁边那个答案**，所以它们是「扣住一项」而不是拒答；把整份结果拒掉的实现会让读者连数据确实支持的那个对比一起失去。

**(366) 一个用 Bernoulli 抽样生成数据的探针，必须先证明它的概率没出 [0,1]。** 出界时抽样静默截断，而闭式 oracle 算的是未截断的值，于是出现一个**不随 n 收缩**的偏差——它长得完全像「估计量算的是另一个估计量」。判据：探针的机制先取极值代一遍；偏差不随 n 缩小时，**先怀疑探针，再怀疑被测对象**，而分辨方法是把估计量的估计量在总体上手推一遍。

### #324 有些问题的答案不是一个数——两个内生处理一起干预时，工具变量给出的是一片置信域，而「域」这个形状在系统里没有位置（2026-08-24）

**问题本身。** 联合干预 `do(a, b)`，两个处理都内生。今天走到这里只有两条路：联合后门（要调整集）和联合 general-ID（要图上点识别）。两条都不成立时，`_try_joint_estimate` 直接 `blocked('design_unavailable')`。但数据里可能有工具变量——只是**工具数少于处理数时，这一组系数根本不点识别**，而工具很弱时，点估计连同它的 Wald 区间都是假的：那条区间立在一个恰好在弱工具处失效的渐近近似上。

Anderson-Rubin 反的是检验，不是估计。它的水平与第一阶段强弱无关，所以回来的东西是**一片域**：数据把整组系数框住时有界，框不住的那些方向上无界，前提本身被数据否掉时为空。**「无界」是答案，不是失败**——拒答会把数据确实施加的那些约束一起扔掉，报一个点则是把剩下的编出来。

**代数就是标量那一套，升一维。** 把 W 用 FWL 消掉，`AR(b) ≤ F(q, m)`（`m = n − |W| − q − 1`，那个 `−1` 是截距，`k` 不进来）在 `κ = q·F(q,m)`、`G = m + κ` 下展开成 `b'A b − 2b'B + C ≤ 0`：`A = G·P_xx − κ·XX`（k×k）、`B = G·P_xy − κ·xy`、`C = G·P_yy − κ·yy`。`k = 1` 时这三个数正是 `anderson_rubin_overid_set` 已经在算的那三个——所以标量解算器搬进新模块 `themis/estimation/ar_region.py`，**一份实现，两个维度**，闸口按端点逐位相等钉住（不是「接近」）。

逐系数区间是把域投到那一根轴上（Dufour & Taamouti 2005），即对其余坐标取极小——Schur 补，于是每个投影又是一条标量二次不等式，回到同一个解算器。域有界 ⟺ 每个坐标的投影都有界（`A ≻ 0` ⇒ 每个主子阵 ≻ 0，保守退路永不触发），这条定理两个方向都是闸口。

**结构条件读在处理的「集合」上，而且不是标量条件的合取。** 把**每一个**处理的出边都剪掉，再问 Z 在给定 W 下是否与 Y m-分离。判别性的见证图（`za→a`、`za→b`、`a→b`、`a→y`、`b→y`）：`za` 经 `b` 到 Y，对「a 对 Y 的效应」这个问题是一条无法关闭的路（`b` 是 a 的后代，不许进调整集），标量判据正确地拒了它；对「a 和 b 一起」这个问题，那条路在干预**内部**，剪双边就剪掉了。写成标量判据的合取会拒掉这整类设计。

**相关性（IV1）故意不进判据。** 域的覆盖率不取决于第一阶段，弱工具让它变大不让它变错；要求相关性等于拒掉这个方法正为之存在的那些设计。相关性改为**逐工具上报**——它预测的是域回来有没有界，不是域对不对。一个「哪个处理都不移动」的工具是路线块里的一行，不是被省略掉的一项。

**度量：**

- **k=1 平价**：`region_from_moments` 的唯一投影与 `anderson_rubin_overid_set` 的端点逐位相同。
- **覆盖率**（n=300、200 次重复、名义 0.95、成员资格直接问那条不等式而不问形状）：强工具 π=0.9 **0.960**（200/200 有界）；弱到 π=0.01 **0.960**（200/200 无界）。同一批 DGP 在 n=4000 上另测过 0.950 / 0.950 / 0.943（q=3）。**覆盖率不随第一阶段强弱变化**，这是这条路线的全部主张。
- **q=1 < k=2**：域无界、无 2SLS 点、含真值 (1, −0.5)、排除 (5, 5)。

**取舍与判断，逐条明说：**

- **`AnswerTier` 不加 `REGION` 成员。** 有界的域给出 k 条保守区间（走 `interval` 档），无界/空的域不答题、把结构性拒答留在原地。加一个档位是把「答案的形状」和「答案的强度」混进同一个词表——#343 的教训。
- **域不挂在 `numeric_estimate` 底下，自己是一个 ANSWER 族块。** 那个字段的契约是「一个估计量、一个数、一个区间」，k 个系数的域三样都不是；塞进去意味着把点和区间都改成可选，而那等于说这个字段不再承诺它们。
- **验证器与产者共享的只有那条定理。** 形状在 `A` 的**特征基**里重新分类（把 `B` 转进去，二次型可分，极小值是 `C − Σ_{λi>0} B̃i²/λi`，每一支都是关于一根轴的陈述），与产者的分支排布不同。每个有限端点还被查两次：在使其取极小的补全处代回**那条二次型本身**必须为 0（「域到此为止」的定义，任何分类都伪造不了），域是椭球时再与支撑函数 `μ_j ± sqrt(r·(A⁻¹)_jj)` 对一遍——这条公式与 Schur 补不共享任何代数。四个形状名验证器自己抄了一份（`_AR_REGION_SHAPES`）：验证器拥有它检查的每一个封闭词表，import 产者的那份会让它审自己的拼写。

**三处结构性修复，是建这条路线时撞出来的，都不是它自己的病：**

1. **`effect` 分支按「结果里有哪个字段」分派。** 两个字段 `numeric_estimate` / `numeric_result` 各自蕴含「答案是一个数」，域两个都不是，于是掉进兜底、撞上 `must carry a numeric_result`。同一段代码的注释早就写着「Routing keys on the derivation's TERMINAL」——路标本该是终结规则，只是没贯彻到底。改法是按终结规则分派，不是加一条 `if extensions.…` 的特判（下一条「答案不是一个数」的路线会再撞一次）。
2. **annotate 的行写了 derivation。** derivation 是「这份结果由此成立」的链，末步输出就是结果；域无界时这一行不拥有查询，写一条以 `True` 收尾的链挂在 `structural_result: false` 的结果上，等于信封自相矛盾。改成**只在答出时写**。
3. **估计量的扁平假设通道只有一个地址。** `augment_assumption_ledger` 读 `numeric_estimate.assumptions`——因为过去「估计」就是一个数。域不是，于是它的三条假设（集合上的排他性、对处理向量的线性、F 临界值要的同方差）落在台账之外，读者拿到的是一本空台账，读起来正是「什么都没假设」。改法与 `ROUTE_PREMISES` 同型：`ESTIMATOR_DECLARATIONS` 声明「估计量把自己的扁平清单放在哪」，两个地址。`test_ledger_vocabulary` 那条闸口的手写豁免名单也随之从「再加一条散文例外」改成「减去另一个注册表」，两个注册表于是**划分** schema 上的 `assumptions` 站点，而不是其中一个变成另一个漏掉了什么的记录。

**已知边界，明说：** 无界那一支 `status` 停在 `needs_investigation` 且不写 derivation，因此 `themis.verify(program, result)` 会以「这份结果没有推导链」拒审整份结果——这是**每一个**未识别 effect 结果的既有契约，不是这条路线引入的。域本身仍可审：`themis.verifier.verify_vector_iv_region(block)` 是公开导出的，`kernel.verify()` 也是从 extensions 上无条件调它（一个附在拒答旁边的事实就该挂在那里）。闸口里两支都验过。

- **全量 7965 → 8117 passed / 176 skipped**（收集数 8141 → 8293，+152：新闸口文件 20 条，其余全是既有参数化闸口的分母跟着新块长出来的——每键到达普查、词表到达、块注册表）。mypy clean（142 files）；`npx tsc -b --force` 通过；`pnpm build` 已重建 `dist`。

**方法论沉淀：**

**(360) 「答案是一个数」是一条假设，而它会以「字段」的形式藏进分派。** 一个系统的分派若按「结果里有哪个字段」走，那些字段的形状就成了它能回答的问题的形状——新增一种形状的答案时，撞墙的不是那个新形状，是三处早就写好的 `if`。判据：把「分派看的是什么」和「答案的形状」分开问一遍——路标应当是**推导链的终结规则**（这一次算了什么），不是**结果的字段**（这一次的答案长什么样）。同一条判据在这次撞出三处，其中两处（台账通道、derivation 的所有权）与 AR 域毫无关系。

**(361) 「不点识别」和「答不了」是两件事，而把它们混成一件是丢掉数据确实施加的约束。** 判据：这个方法在识别失败时给出的是拒答，还是一个**在失败的那些方向上**如实无界、在别的方向上仍然收紧的对象？后者才是把数据说完。附带一条：**只有在这种时候，「无界」才必须是一等的答案形状而不是错误码**——它得能被渲染、被验证、被读者读成一句话（「这些工具在那个方向上说不出话」），而不是让读者从一个空字段里猜。

**(362) 一个图上的判据读在「集合」上时，多半不是它读在单点上时的合取。** 干预的边界一变，什么算「穿堂而过的路径」就跟着变：对单处理是后门的那条路，对处理向量在干预内部。判据是找**判别性见证**——一张图，标量判据拒、集合判据受，或者反过来——找不到就说明这确实只是合取，那就别写第二套。

### #356 一个搜索给出的「找不到」是带量词的话，而那个量词只以「在搜索预算内」六个字到达读者——上界本身在信任边界两侧各存了一份（2026-08-24）

**先核实——登记的两半都不成立。** 登记说这两条恢复路线缺「真推导链 + 对应验证器规则」。规则四条都在，而且是自动调用的：`kernel.verify()` 一见到块就跑 `verify_selection_recovery` / `verify_missing_data_recovery`，数值端另有两条。推导链那一半也不是这两条路线的病——`derivation == 0` 是**每一个** `needs_investigation` 的 effect 查询的共同属性（拿两个对照查询验过），而选择恢复这条路线的报告里，「怎么算出来的」那一节本来就是完整的。**现象存在，归因错了。**

**读的时候撞见的才是真缺陷。** 两条路线的搜索都是「按尺寸枚举候选集合，到某个上界为止」。所以「找不到」从来不是「不存在」，是「≤ k 的里面没有」。这个 k 全仓 **8 份拷贝**：产者侧 5 个默认参数（`recover_conditional` / `recover_effect` / `recover_query` / `analyze_missing_data` / `analyze_missing_data_estimand`，后三个串在一条调用链上），验证器侧 3 个字面量（`_sbd_admissible_exists` 与 `_conditional_z_exists` 的默认值、`_pick_xi` 里的 `min(len(later_list), 4)`）。**没有任何东西要求这两侧相等。**

而验证器的全部意义是「不 import 产者、独立重算一遍」。它确实没 import 产者——它 import 了产者的那个数。两边各写一个 `4`，「独立重算」就退化成「拿同一个参数再跑一遍」；产者哪天搜得更宽（改一个入参就够），验证器会用更窄的范围搜、同样找不到，于是**确认**一个假阴性而不是抓住它。那正是这条搜索存在的那个方向。

第三件事：这个数从未到达读者。`failure_reason` 写的是「在搜索预算内没找到……」——说出了量词的形状，扣下了量词本身。

**根因**：「这个判决是相对于多大的搜索范围说的」没有槽位，于是它散成了一个产者的调用参数、一个验证器的实现细节、和一句中文散文。

**改法**——给量词一个槽位：

1. 两个结果类型各加 `search_budget: int`，产者在**每一个**判决上记下它实际搜到哪（包括搜索根本没跑的那几支——它说的是这次分析怎么配置的）。两个信封块与 schema 同步，`required` 也加（两块都是 `additionalProperties: false`）。
2. **两个验证器从块上读它**，用记录下来的范围重搜。块上没有、或不是非负整数，当场判错——没有量词就没有可重算的断言，而默默替它补一个正是这个字段要终结的那件事。
3. 验证器三处字面量全部去掉，两条否定判决的报错句子把数说出来（`… not SBD-recoverable within |Z| <= 1 …`）。
4. 两个读者面各加一句「（搜索范围：最多 N 个变量的集合）」，**只在否定判决上说**——肯定判决把找到的那个集合亮出来了，范围不修饰它。kernel 散文里那两处「在搜索预算内」删掉：事实归散文，量词归字段。「没找到 ≠ 证明了不存在」那一句保留，它说的是另一件事（这不是完备算法）。
5. `recover_effect` 里那句就地把 `max_size` 改写成 `min(len(candidates), max_size)` 的赋值撤掉——否则记下来的是「候选恰好有几个」，那是另一个事实。

**度量与取舍，逐条明说：**

- **8 份拷贝 → 1 个字段 + 5 个产者默认值。** 产者侧那 5 个保留：它们是这次分析的配置项，本来就该在入口写着。删掉的是边界另一侧那 3 个——同一个配置的第二份记录，而记录它的那一方无权知道它。
- **两个反例都构造成「同一个块、两个记录下来的范围、两种判决」**：`|Z| ≤ 1` 下否定判决成立，`|Z| ≤ 2` 下 {a,b}（条件路线）/ {z1,z2}（选择-后门路线）存在，同一个块必须被判错。**一个持有自己常数的验证器给不出两种答案**——这是「它真的读了那个字段」的证据，而不只是「字段存在」。缺失路线同型：把范围收到 0，MAR 那条本来可恢复的因子分解就重算不出来。
- **闸口另钉一条结构性的**：两个验证器函数体里剩下的整数只有 0 和 1（循环下界）。任何值得写下来的上界都比这大，写在这里就是把产者的常数又搬回边界另一侧。三个反例逐个跑红（验证器重新硬写 / 产者不记录 / 渲染层不说），AST 那条单独验过。
- **全量 7945 → 7965 passed / 176 skipped**（收集数 8121 → 8141，+20，全在新闸口文件）。mypy clean（141 files）；`npx tsc -b --force` 通过；`pnpm build` 已重建 `dist`。

**方法论沉淀：**

**(358) 一个搜索给出的「不存在」是带量词的断言，而量词没有槽位时，它会被当成没有量词的那一句读。** 判据是三问：上界写在哪、结论到达读者时带不带它、独立复核的那一边用的是谁的上界。第三问最容易漏，因为前两问都答对了，三份拷贝仍然可以各活各的。附带一条不对称：**只有否定判决需要量词**——肯定判决把见证亮出来了，范围不修饰它。所以「到处都说」和「该说的地方说」是两件事。

**(359) 验证器的独立性，止于它和产者共享的那个常数。** 「不 import 产者」是形式，「不共享这一次分析的配置」才是内容：同一个 `4` 写两遍，独立重算就退化成同参数重跑——而且**只有在两边不一致的那天才会现形，那天它给出的是确认，不是告警**。判据：验证器里出现的每一个字面量都要问「这是理论里的常数（`0`、`1`、循环下界），还是这一次分析的配置」。后者一律从块上读，读不到就判错，绝不给默认值。

### #446 一张必须和另一张保持相等的表，是一个被写成拷贝的推导——而那句「must stay in sync」已经不成立了（2026-08-24）

变量声明有九个说「这个变量是什么意思」的字段。系统里有五处要问关于这一组的问题：缺了哪些算缺口、patch 能带哪些、默认能答哪些、两份声明比哪些、补缺口表单给哪些一个空格。**每一处都靠把九个名字重列一遍来回答自己那一小部分**，全仓十张这样的表——dataclass、AST schema、`framing_check` 两张、`variable_framing` 两张、`narrative_merge` 一张、`web/app` 一张、`verdict.ts` 一张、schema 的 `defaulted` enum——**没有一张是从另一张推出来的**。

**登记时说它们「只在问两个是非题」，核实后不准确，而真相更尖：**

1. **`framing_check._PATCH_DISPLAY_FIELDS` 与 `variable_framing._PATCHABLE_FIELDS` 此刻就是不一致的。** 前者头上写着「**Must stay in sync with** `_PATCHABLE_FIELDS` — any shape change needs coordinated edits in both modules」。#400 往后者加了 `defaulted` 而没动前者，两边各打一个特例补上。**全仓没有任何测试把这两张钉在一起**——那条注释就是全部的执行机制，而它在被读到之前就已经失效了。
2. **抄了表就跟着抄了遍历表的循环。** `variable_framing._existing_view` 与 `framing_check.build_define_variable_skeleton` 里 `existing` 那一半，是同一个「这份声明已经定下来的东西，作 JSON」，5 个用例逐个比对**输出完全相同**。
3. 四个模块**互不 import**，所以共同的声明必须落到更低的地方。

**根因：这九个字段没有一个「它们是什么」的声明，只有九个字符串字面量被反复抄写。** 缺了那个对象，每个问题只能靠重列全集来回答，同步只能靠散文强制——因为两张表里没有哪张是源。

**四个集合背后是三个谓词，第四个是推导出来的：**

- `reported`——缺席算不算缺口（`unit` 否：不是每个变量都有单位）
- `defaultable`——「按标准的来」能不能答它（`domain` 否：它枚举的是层级，没有标准层级可取）
- `scalar`——装的是不是一个可比相等的值（`domain` 否：它是序列，每个遍历这组字段的地方都为它单开了分支）
- `asked`——表单给不给它一个空格 = **`reported ∧ defaultable`**，实测恰好是那 7 个。不是巧合：问一个缺席不被报告的字段，填了清不掉任何东西；问一个默认答不了的字段，留空就无解。**该被推导，不该被声明。**

`narrative_merge` 的 8 个与 `defaultable` 的 8 个**集合相同但理由不同**（「列表另有分支」vs「没有标准可取」）。两个理由不因答案巧合就合并。

**修法**（照 `themis/risk_provenance.py` 立过的先例：一个被列了十一次的词表收成一张「域真正依赖的那件事」当行的表，其余列举全是并或投影，由测试说明是哪一种）：

1. 新建 `themis/framing.py`：`FramingField(name, reported, defaultable, scalar)` 九行 + 五个投影 + `settled(decl)`。只 import `themis.types`，四个调用方都能拿。
2. 六张 Python 表变成投影调用；`_PATCH_DISPLAY_FIELDS` **删除**——`_PATCHABLE_FIELDS = framing.names() + (NAMES_THE_DEFAULTED,)`，差别写成表达式，只有「多那一个」会变，别的漂不了。重复的视图函数并成一个（`_existing_view = framing.settled`）。
3. 三处 import 不了这张表的（dataclass 自己的字段集、AST schema、`verdict.ts`）改成**对投影设闸口**。
4. 新闸口 `test_every_field_on_the_declaration_is_accounted_for`：声明上的字段要么是 framing 字段（那三个谓词得有人决定），要么落在具名的 `NOT_FRAMING` 里（`predicate` 标识变量、`scale` 是关于**数据**的断言、`defaulted` 命名表里的成员而不是成员）。**没有第三个地方**——这是防止表悄悄覆盖得比它自称的少。
5. 那句「must stay in sync」删掉：没有要同步的东西了。

**度量与取舍，逐条明说：**

- **十张表 → 一张表 + 六个投影 + 三处闸口。** 两处一致性此前从未被任何测试守过（`_PATCH_DISPLAY_FIELDS`/`_PATCHABLE_FIELDS`，以及 dataclass/schema/表 三者），其中第一处**已经漂了**。
- **`asked` 由声明降为推导**，两个排除各自有效（`reported − asked = {domain}`、`defaultable − asked = {unit}`），闸口把这一点单独钉住——一个第二半从不排除任何东西的合取，只是第一半的长写法。
- **#400 那份闸口里三条变成了同义反复**（浏览器键 vs `_FILL_FIELDS`、`_FILL_FIELDS ⊆ _REPORTABLE_FIELDS`、schema enum vs `_DEFAULTABLE_FIELDS`）——两边现在是同一次调用。**删掉而不是留着**：一条恒真的断言比没有断言更坏，因为它读起来像覆盖。它们要查的事在新闸口里对着表说。
- **全量 7926 → 7945 passed / 176 skipped**（收集数 8102 → 8121）：新闸口 20 条（含 9 条逐字段参数化），#400 退役 3 条，两张按模块参数化的普查各收进 `themis/framing.py` 一条。9 个反例逐个跑红。

**方法论沉淀：**

**(356) 一句「must stay in sync with X」是一条自证的缺陷登记——它在说这里本该是一个推导。** 不必去论证同步会不会失败：**它就是失败的那个机制**，因为唯一的执行者是下一个读到注释的人，而注释不参与运行。判据很直接：全仓 grep 「stay in sync」「keep in sync」「coordinated edits」这类措辞，每一处都问「哪一半是源」——答得出来就写成投影，答不出来说明两边其实在回答不同的问题，那就该把那两个问题分别命名。这一条的实证很干脆：注释在原地立着，两张表已经不相等，而且是**这个仓库自己二十分钟前弄坏的**。

**(357) 抄一张表，就会跟着抄遍历那张表的循环。** `_existing_view` 与 `build_define_variable_skeleton` 是同一个函数，在两个模块里、对任何人试过的输入都同意。这不是偶然：一旦第二个模块有了自己的字段列表，「遍历字段」就成了它自己能做的事，于是它做了。所以**发现重复的表时要接着数重复的循环**——表是名词，容易看见；由它长出来的动词分散在各处，而它们才是行为会分岔的地方。

---

### #400 一个值的唯一职责是「非空」——那它就是一个没有槽位的标志位，而这个标志位被写成了四句中文（2026-08-24）

变量声明有七个 framing 字段。读者被问「时间窗是什么意思」，有两种答法：说一个值，或者说「就按标准的来」。只有第一种有槽位。第二种被写进了值里——`_FILL_DEFAULTS` 的七个默认值有四句是中文句子，`"未指定（默认：研究随访期）"` 之类，写成这样是为了让 `framing_check._gaps` 的 `is None` 读出假、缺口从而清掉。

**先核实，登记时的两句说法都要更正：**

1. **`def` 从来没有渲染给读者看过。** `FramingFill.tsx` 用的是 `f.label` 和 `f.placeholder`。`verdict.ts` 那段注释说 `def`「同时做三件事，第一件是读者在空格里看到的字」——第一件是错的。`def` 的两份工作都是数据：服务端写入值的一份浏览器拷贝，以及靠它把那个值再认出来。
2. **不是两个作者，是四个。** 服务端 `_FILL_DEFAULTS`（真正写入）、浏览器 `FRAMING_FIELDS[].def`（逐字拷贝，只为再认出来）、`ResultView.tsx` 的 `defaultedMeans`（把四个值用散文再数一遍：「标准测量、研究随访期、任意可测变化、当前状态为基线」）、以及那段自称权威却已过时的注释。
3. **这七个字段的值，全仓没有任何下游读者。** 唯一一处读值的是 `framing_check._looks_continuous`，它去嗅 `measurement` 的字面。`/api/clarify` 与 `_complete_framing_fields` **一条测试都没有**。

**根因：「这个字段的值是谁给的」没有槽位，于是被编码进了值的措辞。** 一个事实住进措辞，它的每个消费者就都变成散文读者——固定语言、第二份拷贝、按子串判断。三个症状都是它的直接推论：

- 浏览器必须留一份逐字拷贝才能把值**再认出来**（`s[f.key] === f.def`），且无闸口。两边一漂，「这个答案立在没人确认过的定义上」不是报错，是静静地不说了。
- 认得出来这件事**结构上做不全**：`observability=observable` / `direction=up` / `state_vs_event=state` 本身就是合法选择，7 个里 3 个永远认不出来。注释自己承认了这点，也修不了。
- 高一层同一个形状：`_looks_continuous` 靠嗅 `measurement` 的字面（数字 + 一张中英混杂的线索词表）决定 `threshold` 算不算缺口，而 `VariableDeclaration.scale` 这个封闭词表**已经**正面声明了同一件事。与 #397 同型：把渲染当数据读，而结构化事实就在旁边。

**这句自我否定的话在挡什么——量出来的那处：** `ill_defined_intervention_versions`（Hernán & Taubman 2008，持久状态 + 无时长 ⇒ do(X) 不良定义）的抑制条件写着「`time_window` 被设了 → 时长把版本歧义关掉了」。旧的补全把 `"未指定（默认：研究随访期）"` 写进那个槽位，`if time_window:` 为真，**缺口不报了**。读者点一次「补全并重跑」、什么都不填，Themis 就不再告诉他估计量不良定义了——凭的是一句说「没有给时长」的话。

**修法：**

1. `VariableDeclaration.defaulted: tuple[str, ...]` ——那些读者答了「按标准的来」的字段名。第三种状态，前面七个字段装不下：未设 = 没人想过这个问题，有值 = 有人说了一个，两者都不是接受默认。连带 AST schema（`additionalProperties: false`，忘了改会当场炸）、解析、序列化、patch 通道、`narrative_merge` 第二条合并路径。
2. `_complete_framing_fields` → `_framing_fields`：**不再写任何值**，只说出读者留空了哪几个字段。`_FILL_DEFAULTS` 整张表删除。
3. `framing_check._gaps` 把列进 `defaulted` 的字段视为已回答——缺口照旧确定性地清掉，只是清它的是一个被记录的决定，不是一句偷渡进来的话。
4. `framingDefaultsInProgram` 读 `s.defaulted`；`def`、`_MARKER_DEFAULTS` 与那句子串测试整个消失。`label` / `placeholder` 是真渲染，改成 `Words`。`defaultedMeans` 不再数那四个值（它们不存在了），改说本来的意思：这几项没人指定。
5. `_looks_continuous` 先读 `decl.scale`，嗅字面只作未声明时的退路——那份线索词表读的是用户自己写的自由文本，本来就不可能语言中立，这正是正面声明该排在前面的理由。

**度量与取舍，逐条明说：**

- **语言债表两行归零并删除**：`verdict.ts` 8 → 0、`themis/web/app.py` 4 → 0。**不是因为翻译了，是因为那批数据不再是散文**——`verdict.ts` 那八行当初留着的理由正是「`def` 是写进 program 的值，读者的语言不能碰它，而 `label`/`placeholder` 和它同一行」；值一走，那两行只剩读者的字。
- **`variable_framing.py` 7 → 10，方向是错的**，如实登记：patch 通道新增的两个形状错误带三句英文。它们与已在册的七句同种，只改新的会让这个模块的错误说两套话；清掉这一行要靠它整套错误词表迁到 #411 那个「物种 + 事实」的形状。
- **一处行为变化，且是缺陷显形不是回归**：全空补全**不再**清掉 `ill_defined_intervention_versions`。接受一个时长的标准读法不是一个时长。补缺口表单仍然为该变量提供（`framingVariables` 认这个 kind），读者能接着填；填了 `time_window` 之后缺口清空。
- **三个字段第一次能被如实披露**：`observability`/`direction`/`state_vs_event` 过去永远判不出「他选的」和「没人选」，现在七个一视同仁——闸口按字段参数化，就是那份普查。
- **补全回路仍然是闭的，且多了一条路**：先接受默认、之后再指定某个字段，值胜出、该名字从 `defaulted` 移除。反过来（同一个 patch 里既给值又说默认，或对已有值的字段说默认）拒收——那是对一个问题的两个答案，这一层不知道读者要哪个。
- **全量 7902 → 7926 passed / 176 skipped**：新闸口 26 条，语言债表少 2 条参数化（删了两行）。11 个反例逐个跑红。

**方法论沉淀：**

**(354) 一个值的唯一职责是「非空」，那它就不是值，是一个没有槽位的标志位。** 判据很干脆：把这个字段的所有读者列出来，如果没有一个读它的**内容**，只有测它在不在，那它承载的就是一个布尔事实，而这个布尔事实缺一个自己的名字。危险在于标志位一旦写成句子就长得像值：它有语言、要翻译、会被第二个消费者拷贝、能被子串测。这里那句话甚至是自我否定的——`"未指定"` 写进 `time_window`，字面意思就是「这个槽位没有内容」。**看见一个说自己不存在的值，就是看见一个该被命名的事实。**

**(355) 一条抑制规则被满足了，要接着问：满足它的是不是它要的那个东西。** `ill_defined_intervention_versions` 要的是「有时长了，所以版本歧义关上了」，它测的是 `if time_window:`。测在场，不测内容——于是一句说「没有给时长」的话把它关掉了。这不是那条规则写错了，是**在场从来不等于内容**，而只要有任何一条路径能往那个槽位塞进一个「占位符」，这个等号就断了。判据：每条形如「X 被设了所以 Y 不成立」的抑制，都要去数一遍**谁往 X 里写过东西**，逐个问那次写入是不是真的让 Y 不成立了。

---

### #397 一份渲染有两个消费者：一个印给人看，一个决定跑哪条公式——而它要的事实早就算好了，在同一行的旁边（2026-08-24）

`item.target` 是一条印给人看的概率：`parameter:P(y=True|w=True,z=False)`。三个 pass 把它拆回去用：`is_binary_outcome_distribution` / `is_continuous_outcome_distribution` 靠子串测 `"=true"` 决定用 Cohen's h 还是 Cohen's d，`_distribution_signature` 靠有没有 `|` 决定要 IPD 还是边际数据、给 KB 适配器发哪种 query kind。全量跑一次 **4988 次**这样的判断。第四处在同一个函数里：中介匹配写的是 `m in item.target`——把中介名当子串去撞那条渲染串。

**根因不是判据写得糙，是一个渲染产物被当成数据用。** 同一个串两个消费者：一个在渲染时（`A_DISTRIBUTION_IS_MISSING` 的 `what=` 槽位），一个在运行时决定 kernel 走哪条分支。#438 已经登记并修过一次这个形状；这是它在样本量通道上的第二个实例。语言只是让它显形的那件事——`format_probability_key` 一旦为某门语言改写值的拼法，判据当场哑掉，而它不报错，只是让 `min_sample_size` 静静消失。

**真正的判据是：结构化事实早就算好了，就在旁边。**

- `MissingItem.observable` 的 docstring 已经把原则写死了——「*every consumer that had to take `P(y=True|z=True)` apart again was reconstructing what was thrown away here*」。它兜住了「哪些变量」，没兜住「目标取什么值」（定二值/连续）和「条件了几个」（定条件/边际）。**原则写下来了，分母没数过。**
- `_skeleton_for_parameter(key)` 从**同一个 key、同一时刻**产出 `{"target":{"atom":…,"value":True},"given":[…]}`，字段正是判据要的那两样。4988 次里 **4688 次**这份 statement 就在 `item.skeleton` 上，判据一次都没看它——**字符串与结构化事实一致 4688/4688，分歧 0**。判据每次都在费劲重推一个手里已有的答案。

**活体缺陷：289 条询问没有可粘回的 stub。** 剩下 300 次连 skeleton 都没有，而不是因为它们没有 key——`MissingKind.PARAMETER` 全仓只有一个产地（`_missing_parameter_from_key`，1688/1695 两支），它握着 key。丢失发生在之后：item 和 statement 被拆成 `(tuple, dict)` 两半分开传（`ObservationalJoint.skeletons`、`_AncestralRecovery.skeletons`、`joint_skeletons=` 参数链、6 个 `skeletons[item.name] = …` 赋值点、`_causation_gap` 里一段从别人的 request 反捞 skeleton 的合并），最后在 `investigation_pusher.push()` 里**靠渲染出来的名字当键重接**（`skeletons.get(m.name)`）。7 个 push 调用点里有 2 个根本没传这份 dict。插桩全量测得：pushed 的 parameter 询问 **5387 条，307 条没有 stub，其中 289 条是真 key 造出来的**（另外 18 条是测试手搓、本来就没有 key）——**这 289 条走不进 `parameter_fill` 的粘回闭环，而同一个产地的兄弟条目走得进**。这是同一个病灶往上一层：用渲染串当身份，正是 `name` 被拆成 kind/gap/need/observable 时要终结的那件事。

**修法：**

1. `MissingItem` 增 `skeleton` 字段，由**唯一那个产地**在握着 key 的地方填上。覆盖率按构造成立，不靠任何下游调用点记得传。
2. 整条侧通道删掉：`push()` 的 `skeletons=` 参数、`ObservationalJoint.skeletons` / `_AncestralRecovery.skeletons` 两个字段、`joint_skeletons=` 参数链、`_causation_gap` 的反捞合并，以及因此变成死返回值的 `_derive_interventional_risk_arm` / `_derive_interventional_risks` 第三个元素（它们存在的唯一理由就是把 skeleton 送到 `_causation_gap`）。
3. 判据改读结构化事实：新 `data_gap_report.asked(statement)` 一次读出三样——目标值落在哪个公式族（`sample_size.Measured`）、条件了几个、涉及哪些变量。两个字符串嗅探器**整个删除**，中介改按变量精确匹配。
4. **闸口写成一般形式**：在既产渲染又要分支的那两个函数里，读者的那份串**只能作为实参出现在写给人看的调用里**（`_sentence` / `_route` / `GapProvenanceRef`），AST 逐节点核。再加一条签名闸口：三个决策函数各自只收一个 `Ask | None`，未来的调用点递不进一条渲染。

**度量与取舍，逐条明说：**

- **覆盖率 289 → 0**。修后重跑：pushed parameter 询问 5384 条，23 条没有 stub，其中 **5 条是 `parameter:P*(…)` 这种测试手搓的名字，18 条是 `a`/`p1`/`b` 这类无 key 条目**——生产路径零遗漏。
- **数值零漂移**。`bool → PROPORTION`、`int/float → MEAN` 与旧嗅探器逐条同义（4688/4688 一致，值类型 bool 4629 / int 59；那 59 条是 `engagement=4`、`wage=50000` 这类，旧规则也判连续）。**刻意没有借用 `Scale` 那套词**：五档李克特是离散的却该走均值公式，用「连续」去说它是对变量说了假话。
- **`signature` 的域变了**：没有 statement 的缺口现在如实答 `None`（旧代码猜 `marginal`，而适配器把它读成「去哪儿找数据」的断言）；`joint` 从此产不出来——一条概率询问只有一个 target，它当初可达是因为签名读的是渲染名，而逗号在那里既可能是联合也可能是条件集。`kb/translator` 那一行留着并注明理由：旧信封反序列化回来仍可能带它，删掉会把它们打到默认分支。
- **反事实门的一处行为变化**，因为 `arm_requests` 随侧通道消失：那个分支现在像它的孪生 causation 门一样，**在合并集上 push 一次**，而不是转发子调度的 requests。插桩测得：pushed 条目 5960 → 5958（parameter −3、structure +1），逃生条目 `counterfactual:interventional_risk_unavailable` 前后都是 5 次且前后都有 entry（旧路径靠 `_fill_investigation_requests` 那个兜底 pass 补上）。**变的是 requests 现在与结果自己声明的 `missing_information` 同源**，而不是与子调度的那一份。
- **18 条测试手搓条目失去了样本量**，因为它们只给了渲染名、没说形状。这些测试改成把形状说出来——这正是新契约要的：形状是产地要声明的事实，不是从名字里再猜一遍的东西。

**方法论沉淀：**

**(351) 一条原则写进 docstring，不等于它被应用了；必须去数它的分母。** `observable` 的注释明说「每个把 `P(y|z)` 拆回去的消费者都是在重建这里丢掉的东西」，然后只兜住了三个事实里的一个——而那句话读起来像是已经解决了，于是没人再查。判据：把 docstring 里的原则当成一条**待验证断言**，枚举它声称覆盖的消费者，逐个核实。写得越好的注释越容易变成这种挡箭牌。

**(352) 一个对象拆成两半分开传，重接时拿什么当键，那个键就成了同一性。** 这里拿的是渲染出来的名字。要问的不是「重接会不会错」——它多数时候不错——而是「有几个调用点可能忘了带另一半」：6 个产地写 dict、7 个 push 点、其中 2 个没传，289 条询问就此没有可粘回的东西，而且**没有任何东西报错**，因为「没有 stub」和「这条本来就没有 stub」长得一模一样。**覆盖率必须是构造器的性质，不是每个下游调用点记性的性质**：把第二半挂到唯一那个产地上，能忘的地方就归零了。

**(353) 「一个渲染只能流向读者」可以做成 AST 闸口，而删掉判据不能。** 在同一个函数里既产出给人看的串、又要做分支时，规则不要写成「别读这个串」（新加的分支不受它约束），要写成「它只能作为实参出现在写给人看的那几个调用里」，逐节点核。这条对未来新增的每一个分支都生效，而「两个嗅探器已经删了」只对过去生效。

**分母**：`P(...)` 判据 4 处（2 个嗅探器 + 签名 + 中介子串匹配）全部改读 statement，字符串判据全仓归零；侧通道 6 个赋值点 + 2 个 dataclass 字段 + 3 个参数 + 2 个死返回值全部删除；反例八条全红（分支读渲染串、中介按子串撞、签名收回渲染、签名从名字里读、pusher 收回侧 map、产地不再挂 statement、statement 有第二个作者，其中中介那条两个测试各自红）。

基线：7889 → **7902 passed / 176 skipped**（收集数 8065 → 8078，+13：新闸口 14 条、`asked` 取代嗅探器 net −4、pusher −1、`Measured` 自动进入两张词表普查 +4）。mypy clean（140 files）；`npx tsc -b --force` 通过（本刀未动浏览器源码与 schema，`dist` 未重建）。

### #445 兜底不可达就不是兜底，是一份没人核对过的第二版文本——164 处写的是键名（2026-08-24）

`say(SAYS.tightness, lang, 'tightness')`。第三个实参是**键自己的名字**。全浏览器 **164 处**这么写（153 处裸串 + 11 处 `busy ? 'running' : 'demo'` 这种二选一），分布在 16 个组件加 `App.tsx`。

若 `SAYS.tightness` 在读者的语言下没有文本，读者看到的就是 `tightness`。它和一个真标签无从区分——比 #440 那两个替身更糟：**`tightness` / `ledeMid1` 不是任何东西的名字**，读者既看不懂，也没有可查之处（信封上的 token 至少指着一个真实存在的列）。

**但真正的发现是：这个兜底根本不可达。** 两个面上一共 **2195** 个 `Words` 字面量，**没有一个**缺任何一门已写语言。这些兜底全是死代码——而在那之前，**没有任何闸口说过这件事**。今天为真，明天有人写一个只带 `zh:` 的 `Words`，它编译通过、所有闸口全绿，然后英文读者拿到 164 分之一的键名。

**根因不是这 164 个字符串挑错了，是 `say` 把两种主语写成了一扇门。** 它自己的 docstring 并列着「一个词表成员、一张表的行」，而这两者**不可能同时缺席**：

- 从**外面**来的（另一个 build 的信封、线上传来的错误词）—— 缺席是一个关于这次调用的**事实**，替身是 `absent()` 的活；
- 这个 build **自己写的**（组件里两行之上的 `SAYS` 字面量）—— 缺席是**构建缺陷**，不是读者的事。

一扇门同时服务两种主语，就等于逼着 164 个作者为第二种主语编一个「读者可见的降级」，去掩盖一个本该响的构建缺陷。而手边唯一现成的东西就是键名。

**修法，闸口先立**：

1. **完备性闸口**：两个面上每一个 `Words` 字面量都必须写全每一门已写语言（2195/2195）。这条是让兜底不可达这件事**成为规则而不是巧合**——`ARRIVING` 那套两集合机制本来就是干这个的：一门语言在文本落地期间待在 `ARRIVING`（谁都答不了它），而不是让某个 `Words` 少一行。
2. **164 处改走 `fill`**：`fill(SAYS.tightness, lang)`。不是新机制——`fill` 一直就是「这个 build 自己写的句子」那扇门，缺席直接抛，理由写在它自己的注释里；这些行里凡是带槽位的本来就在用它。改完之后 `say` 只剩 **13 处**，每一处的主语都是**用一个从外面来的值查出来的**（`STATUS_META[status]`、`ROLE_META[role]`、`row.words`、`licence`），替身全是 `absent()` 或 `''`。
3. **调用点不得自己编文本**：`say` 的兜底里，剥掉 `absent(...)` 之后不许再有任何非空字符串字面量。`''` 留着——它不是给读者看的文本，是调用方在说「这里什么都不印」。

**一处必须明说的取舍：缺席从「降级成键名」变成了「抛异常」。** 组件里一个文本缺了读者的语言，现在整棵 React 子树渲染失败，而不是印一个 `ledeMid1`。选它的理由有三条：(a) 键名不是名字，读者拿它做不了任何事，所以「一个可查的名字胜过沉默」这条论证在这里根本不成立；(b) `fill` 对每一个带槽位的句子一直就是这个策略，理由完全相同；(c) 上面那条完备性闸口把它变成不可达——而在闸口立起来之前，这 164 个兜底其实也没在挡什么，它们只是让缺陷安静。**代价是真的**：闸口漏掉某种 `Words` 写法的话，代价从「一个词难看」变成「一块界面白屏」。这是知情选择，不是没想到。

**扫描器的一个坑，记下来**：判断「兜底里有没有非空串」的第一版正则是 `'[^']+'`，它把**两个相邻的空串**读成了一个长串——`{ label: token, gloss: '' }, failsTo: { label: token, gloss: '' }` 里，从第一个 `''` 的后引号一路匹配到第二个 `''` 的前引号，中间的代码全被当成字符串内容。改成「按 `'...'`（含空）**从左到右逐个切**，再看有没有长度 > 2 的」。一个跳过空串的模式，等于把空串之间的代码吞进串里。

**分母**：`say` 调用点 177 → 13，全部逐个读过；`Words` 字面量 2195，零例外；反例四条全红（组件把文本编回去、它的二选一形态、浏览器少一门语言的 `Words`、kernel 少一门语言的 `Words`）。

**方法论沉淀**：

**(349) 一个兜底如果不可达，它就不是兜底，是一份没人核对过的第二版文本。** 判据很硬：**能不能构造出触发它的输入**。构造不出来，就先把「构造不出来」这件事本身变成闸口，然后那段兜底可以**整段删掉**——不是「改好看一点」。这一步的顺序不能反：闸口没立之前，那段死代码确实是唯一挡着的东西，先删就是拿掉最后一层。

**(350) 一个门的兜底该不该存在，取决于它的主语是这个 build 自己写的，还是从外面来的。** 只有后者能缺席；前者缺席是构建缺陷，必须响。把两者塞进一扇门，调用点就得为「不会发生的那一半」编一个读者可见的降级——而手边唯一现成的东西通常是键名或那个值本身，于是缺陷被安静地翻译成了一个读者看不懂的字符串。判据：读这扇门的 docstring，看它并列了几种主语，逐一问「这一种缺席意味着什么」；答案不一样，门就是两扇。

基线：7887 → **7889 passed / 176 skipped**（收集数 8063 → 8065，+2）。mypy clean（140 files）；`npx tsc -b --force` 与 `pnpm build` 均通过（`dist` 已重建）。

### #444 判断被绑在「谁做它」上，而不是绑在它需要的事实上——于是第二扇门永远不做（2026-08-24）

#439 让路线能说出「什么样的界能替代我」（`Route.answered_by`），并让识别阶段的 pass 据此改写。但**往缺口报告里加路线的门有两扇**：

- 识别之后的 `_reconcile_alt_paths_with_bounds`，一个 postprocess pass，契约是 `QueryResult -> QueryResult`；
- 估计层的 `_file_gaps`，在 `run()` 序列化之后往 `result["data_gap_report"]["gaps"]` 追加。

第二扇门从不做那个判断。**全量插桩实测（一次全跑）**：估计期归档 323 个缺口，其中 11 个带「退回到界」的路线，而**其中 4 个，界就在同一个信封上**——

| 缺口 | 它给的退路 | 信封上已有的界 |
|---|---|---|
| `overidentification_rejected` | `fall_back_to_bounds_without_exclusion` | `manski_natural` |
| `weak_iv_instrument` | `fall_back_to_iv_bounds` | `manski_natural` |
| `weak_iv_instrument` | `fall_back_to_iv_bounds` | `manski_natural`, `manski_tamer_monotonicity`, `balke_pearl_iv` |
| `weak_iv_instrument` | `fall_back_to_iv_bounds` | `manski_natural`, `balke_pearl_iv` |

读者被送去做一件已经做完的事。第一行尤其难堪：过度识别检验刚**否掉**了工具，系统给的退路是「退回到不假设排他性的界」，而正是这样一个界（`manski_natural`）已经算好躺在旁边。

**根因不是漏调了一次和解，是这个判断被绑在了「这份报告此刻是什么类型」上。** 它真正需要的只有两样东西：这条路线接受哪些方法、哪些方法产出了区间。两样都是**关于这个答案的事实**，不是关于「报告现在是 dataclass 还是 dict」的事实，而且在追加缺口的那一刻两样都在手边——`_file_gaps` 收到的本来就是 `DataGap` dataclass。所谓「两种表示」，是这个判断长在 pass 里造成的表象。

**为什么表象修法不行**：「估计结束后再跑一遍 pass」要 dict→dataclass→dict 往返，并对 pass 提出它今天没有的幂等要求；「在 `_file_gaps` 里也写一遍」制造第二份判据，正是这个仓库反复清掉的病灶。两者都还是把和解绑在**时机**上——明天第三个作者再追加一条，照样漏。

**修法**：判断抽成 `themis.gaps.past_the_bounds_in_hand(offered, computed, *, delivered_nothing, blocking)`，住在路线自己的模块里，不认识任何一种表示；两扇门各自把手上的东西喂进去。它答三件事，和 #439 定下的三分支一字不差：接受得了在手的某个界 → 换成只点名这些方法的指针；界出来了但这条路线一个都不接受 → **保留**（替换会拿刚被否掉的假设去回答它自己）；一个界都没出来 → 看有没有人试过。

**一处刻意的不对称，写在门上而不是留给读者猜**：`delivered_nothing` 只有识别端传 `True`。「界试过了但什么都没出来」是从 `status` 读的，而估计器跑完之后 `status` 已经被改写，所以估计端**没有能力**区分「试过没出来」和「没试过」——它就不撤销任何承诺。保守的那一半，明写出来，免得后来的人把这个不对称「修」成事实并不支持的对称。

**闸口钉的是「只有一个作者」，不是「我调了两次」**：`Route.BOUNDS_ALREADY_COMPUTED` 只允许在 `past_the_bounds_in_hand` 内部被构造——它不是任何人**提供**的路线，是判断放在一条已兑现路线原处的东西；谁构造它谁就在自己做这个判断，而那正是两扇门当初分家的方式。配一条分母闸口：调用它的模块恰好是那两个（只钉「有一个作者」而没人调用它，同样是全绿）。五个反例全红：估计端不和解、估计端撤销它测不了的承诺、第三个模块自己造指针、一扇门改调别的函数、判断把它答不了的路线删掉。

**我又写了一道空转的闸口，这次是被短路挡住的。** 「估计端不撤销它测不了的承诺」这条测试，第一版恒绿——因为 `_file_gaps` 里有个 `if computed:` 短路，一个界都没算出来时判断根本不被调用，于是 `delivered_nothing` 传什么都一样。反例（把它改成 `True`）照样绿，这才暴露出来。去掉短路：判断对「什么都没算出来」自己会答「没有变化」，行为逐字节相同，而那个参数重新变成 load-bearing 的。**一个短路优化会把它挡住的那段语义连同钉它的闸口一起变成装饰。**

**血径实测，说明这一刀的影响面就是那 4 条**：估计端归档的缺口**没有一条是 `blocking`**（7 个产出点的 severity 只有 `INFORMATIONAL` / `IMPORTANT`），所以「给阻断性缺口把通用指针插到最前面」这条规则在这扇门上从不触发。变的只有「路线接受得了在手的界」那一支。

**方法论沉淀**：

**(347) 判断该住在哪，看它需要的输入在别处拿不拿得到，而不是看它现在长在谁身上。** 把这个判断的输入逐条列出来，逐条问「另一扇门在它做事的那一刻有没有这个东西」。全都有 → 它不属于任何一扇门，它属于那些输入共同描述的那个概念（这里是「路线」）。本刀里「dataclass vs dict」看着像一堵墙，其实是判断长错了地方投下的影子：搬到路线旁边之后，那堵墙在正确的位置上根本不存在。

**(348) 给闸口写反例时，如果反例改的正是被测的那个参数而测试依然绿，那么决定结果的是别的东西——通常是一条短路。** (343)/(#439) 记的是「按构造不可能失败」的空转闸口；这是它的第二种形态，更难看见：闸口测的语义是真的，只是被一个 `if` 挡在了到不了的地方。修法不是加断言，是**去掉短路、让门自己回答那种情况**——门答得出来，这段语义才回到运行路径上，闸口才有东西可钉。

基线：7882 → **7887 passed / 176 skipped**（收集数 8058 → 8063，+5）。mypy clean（140 files）；前端未受影响（判断不上信封，改写的是已在 schema 内的 `alternative_paths`）。

### #440 缺席穿着在场的记号——三样不同的东西渲染出来一模一样，而 25 个调用点各存了一份旧答案（2026-08-24）

反引号在这套系统的每一句话里都只意味着一件事：**这是个名字**。一个列、一个参数、一个估计量，模板
写成 `` `{variable}` ``，读者据此知道它指的是数据里真实存在的东西。而两个「替身」也是这么拼的：

- 一个句子的槽位没拿到事实 → `` `column` ``
- 一个词表拿到了值但本版本没有它的说法 → `` `sideways` ``

于是三样东西到达读者时长得完全一样：**句子谈论的那个东西、这一次没给的事实、这个版本说不出的
值**。读者手里没有任何线索能把它们分开。

**根因不是这两个字符串挑错了拼法，是「缺席」被写成了「在场」的记号。** 拼法只是它的表现；换成
方括号或别的括号一样解决不了——真正要成立的是「读者能看出这里是个替身」。所以修的不是引号，是让
两种缺席各自成为**一条有名字的句子**：`themis/language.py:ABSENT` 两行，`absent(kind, lang, **slots)`
是唯一的门。`（未提供 {name}）` / `` `{token}`（本版本没有它的说法） ``——第二行保留 token，因为
它确实是个读者可以去查的名字，缺的只是这个版本的说法。

**改完之后一测，一条读者可见的行为都没变——因为 25 个调用点早就把旧答案抄出去了。**

这才是这一刀的真题目。`gloss` 的默认值是对的，但它只对**没有人覆盖它**的调用点生效，而：

| 在哪 | 多少 | 写的是什么 |
|---|---|---|
| kernel `gloss(..., unknown=X)` | 6 | `unknown=status` / `unknown=mech` / `unknown=tier` / `unknown=g.get("severity","")` / `unknown=action.value` / `unknown=prio.value` |
| kernel `say(..., unknown=X)` | 2 | `` f"`{row.name}`" ``（审核行）、`str(member)`（拒答路线，注释里明写「照 gloss 的做法：交还 token」） |
| 浏览器 `gloss` 第四实参 | 15 | 全是 `sev` / `layer` / `kind` / `String(width ?? '')` 之类，即被查的那个值本身 |
| 浏览器 `say` 第三实参（反引号插值或裸 token） | 4 | 三处 `` `\`${...}\`` ``、一处 `{ label: String(role) }` |

**一个每个调用方都覆盖的默认，不是默认。** 而每一份抄本都是一个「读者的词退回成名字」的地方——
其中 `analysis_report.py:4098` 抄的正是被删掉的那个拼法。

**修法在门上，不在 25 个点上。** `gloss` 现在答三种情况而不是两种：

1. 有值有说法 → 说法；
2. 有值没说法 → `absent('no_word_for_this_token')`；
3. **没有值 → 空串**——一个可选字段缺席值不值得说一句话，是**它周围那句话**的问题，不是这里的。

第三种是之前没有的。加上它之后，那些写 `String(width ?? '')`、`unknown=""` 的调用点手里就没有第二
样东西可说了，25 处全部变成**删掉那个实参**。`say` 的两处（它的主语是一个没有 token 的 `Words`，
所以门无从代答）改成显式调 `absent()`。两扇门（`themis/language.py` 与 `lib/language.ts`）同改。

**闸口钉的是「调用方还能说什么」，两条规则：**

- **兜底不得由被替代的那个值搭出来**（kernel AST；浏览器只管 `gloss`）。唯一允许对这个值做的事
  是把它交给 `absent`——那正是「从名字变成会自报身份的替身」的那一步。扫描器把 `absent(...)` 整段
  剥掉之后再取标识符交集，所以「把值传给 absent」和「把值原样交还」在闸口眼里是两件事。
- **兜底不得写成一个纯反引号插值**（两面都管）。这条抓的是第一条看不见的形状：兜底是个模板而不是
  那个值本身，标识符交集为空，但它就是那个被删掉的拼法。

分母不是我数的：`themis/**.py` 里每一个 `unknown=`（10 个）都必须被 AST 扫描到，少一个就是「有人
从一扇扫描器不认识的门传了兜底进去」。十个反例全红：两个标记改回旧拼法、槽位标记丢掉括号、浏览器
表漂一个词 / 少一行、六个调用点各退回旧写法、`unknown=` 走一扇没登记的门。

**两处明说的取舍：**

1. **「本版本没有这个词」和「本版本有这个词但这门语言没写」仍然共用一个渲染。** 这个合并从一开始
   就是有意的、两面都写在注释里；要分开，浏览器那一面得再抄一份语言名表（`endonym`），而这个情况
   在「每张表在每门已写语言下都齐」的闸口下**不可能发生**。这一刀换到的是：这两者现在都不再可能
   被当成一个**名字**。
2. **`ABSENCE_WORDS` 是 `language.ts` 里手抄的 4 条串，不是生成的。** 我先把它加进
   `reader_words.GLOSSED`（那是给浏览器生成词表的注册表），三条浏览器闸口当场变红，理由是对的：
   那个注册表的每一行都锚在「**信封可能携带什么**」上，而缺席标记不被任何东西携带——它是渲染器在
   什么都没到时放上去的东西。于是它回到机制旁边（`fill` / `say` / `holes` 本来就是手写孪生），由
   一道「两张表必须相等」的闸口守着，这对 4 条串正是生成能买到的全部。

**登记一条相邻缺口，不并进来（#445）**：15 个组件 + `App.tsx` 共 **165** 处 `say(SAYS.foo, lang, 'foo')`
——兜底是键自己的英文名。**这不是同一个缺陷**：不带反引号，且 `say` 的契约明说「兜底由调用方命名」，
因为它主语里根本没有 token 可交还。所以浏览器那条规则**故意不管 `say`**——把它一并管上，闸口就会
对 165 个「门无从作答」的点说不，而那是另一个问题（键名是开发者的把手，不是读者的词）。

**我自己走过一次「表象修完就以为完了」**：两个标记改好、两面 `absent()` 到位、8 个字符串型测试更新
完，`tsc` 与全量都绿——看上去就是一刀干净的活。是**回头扫一遍「还有谁在产出这个替身」**才撞见那
25 处；其中一处抄的就是刚被删掉的那个拼法。改一个默认值的时候，绿色**不构成**这个默认生效了的证据。

**方法论沉淀**：

**(345) 改一个默认值之前，先数有多少调用点把它写出来了。** 判据极具体：**这个参数的每一处显式实参，
是不是就是默认值本身**。是的那些，全是「默认改了也不会生效」的点——本刀 33 处显式实参里 25 处如此。
一个每个调用方都覆盖的默认不是默认，是一份被复制了 25 遍的旧答案；而只要签名还在问「你想说什么」，
第 26 个调用点明天照样会写第 26 份。所以修法在收窄那个问题，不在改那 25 个字符串。

**(346) 「缺席」不是一种值，是三种：没有值 / 有值但本版本没有它的说法 / 有值也有说法。** 门只答两种
时，第三种会被调用方各自补上——而手边唯一现成的东西就是那个值，于是补法千篇一律地是「把它原样交
还」，而原样交还正是**在场**的记号。判据：去看这个门的调用点里有多少个在写 `?? ''` / `unknown=""`
这类「值不在时说点别的」的兜底；每一个都是门少答了一种情况的证据。

基线：7871 → **7882 passed / 176 skipped**（收集数 8047 → 8058，+11）。mypy clean（140 files）；
`npx tsc -b --force` 与 `pnpm build` 均通过（`dist` 已重建）。

### #439 「有没有界」和「哪一种界」是两个问题，而这个属性只装得下第一个（2026-08-24）

`FALL_BACK_TO_BOUNDS_WITHOUT_EXCLUSION` 是过度识别检验**否掉排他性**之后发给读者的退路。它
声明 `points_at_bounds=True`，而 `reconcile_alt_paths` 对任何 `points_at_bounds` 的路线都替换
成一个「已计算的界」指针，指针点名**所有**算出来的方法——其中可能有 `balke_pearl_iv`，正是假设
排他性的那个界。把读者送去看刚被数据否掉的那个假设。

**根因不是这一条的布尔值标错了，是这个属性问错了问题。** 路线要回答的是「**什么样的**界能替代
我」，`bool` 只能回答「有没有界就行」。「排他性刚被否掉」这个信息在通往 pass 的路上被类型丢掉，
而 pass 的替换动作恰恰需要它。

**三条证据说明它是根因不是表象**：

1. 把这一条改成 `False` 能消掉 bug，但那是**说谎**——它确实是一条「拿界代替点」的路线，改成
   `False` 之后连 Manski 界（不假设任何东西）算出来了也不会替换它，读者继续看到一条早已可兑现
   的建议。表象修法在另一个方向制造第二个错。
2. 这个属性只有一个读者，而那个读者做的事是**用指针替换路线**——替换成不成立，本来就取决于两
   边的假设集是否相容。类型比它要回答的问题窄一档。
3. **同一个窄类型已经在另一个方向咬过，而且是用注释补的**：`FALL_BACK_TO_A_BINARY_CONTRAST`
   和 `BOUND_THE_UNSUPPORTED_REGION` 的 `says` 里各写了一句「我 NOT `points_at_bounds`，因为
   我给的是**另一个问题**的区间」。两处散文，说的都是类型说不出的话。

**修法**：`points_at_bounds: bool` → `answered_by: frozenset[BoundsMethod]`。空集 ≡ 旧的
`False`（59 条逐条等价），三条无所逃避的路线是 `_ANY_BOUND`，逃离排他性的那条是
`_ANY_BOUND - {BALKE_PEARL_IV}`。pass 按「这条路线接受的方法 ∩ 实际算出来的方法」出指针：

- 交集非空 → 指针只点名交集里的方法（两个界在手时，逃离排他性的那条被替换成只写
  `manski_natural` 的指针）；
- 交集为空但算出了别的界 → **保留原路线**。它的建议仍然成立，替换会把读者送去看刚被否掉的
  那个假设，删掉则丢掉一条活着的退路——旧的布尔在这两个方向上都会犯错；
- 一个界都没算出来 → 照旧撤回这条空头承诺。

顺带把那个「通用指针」也并进来了：它不是第二样东西，就是「接受一切的那条路线」在同一个函数下的
答案（`_in_hand(Route.BOUNDS_ALREADY_COMPUTED)`）。

**闸口钉的是两份记录相等，不是我说的话。** `FALL_BACK_TO_BOUNDS_WITHOUT_EXCLUSION.answered_by`
必须等于「所有方法 − builder 实际挂了排他性假设的那些」，而后者是用 AST 从
`themis/output/bounds.py` 的 `BoundsResult(...)` 调用里读出来的。四个反例全红：逃离排他性的那条
改成接受一切、给 Manski 的 builder 加一条排他性假设（新方法「默认加入」的那个方向）、pass 把没
人能答的路线删掉、指针不再问路线接受什么。

**我自己写错了一次，而且是写在注释里。** `_BOUNDS_THAT_DO_NOT_ASSUME_EXCLUSION` 的第一版注释
说「写成差集，是为了让以后新增的方法默认加入、必须**主动**拿掉——这是 fail-safe 的方向」。正好
写反：对一个「用来逃离某个假设」的集合，默认加入是**不**安全的方向。让它安全的不是写法，是上面
那道把集合钉到 builder 上的闸口（第二个反例正是这一条）。

**还写了一道永远不会红的闸口，当场删掉。** 「每一个 `BoundsMethod` 都要被某条路线接受」——而
`_ANY_BOUND = frozenset(BoundsMethod)`，新成员自动进去，这个断言不可能失败。「新闸口必须构造它
该说不的那个反例」这条纪律，抓住的就是这种读起来像强制、实则空转的闸口。

**实测更正三条（登记的解法也是待验证断言）**：

1. 登记说这条 bug 今天不可达的两个理由之一是「`balke_pearl_iv` 只要一个工具、过度识别缺口要
   ≥2 个」——仍然成立，但**第二个理由更强也更普遍**。全量插桩 `reconcile_alt_paths`（7867 条
   测试）：production 里到达这个 pass 的 bounds 路线**只有 `accept_the_interval` 一条**；唯一
   一次 `fall_back_to_iv_bounds` 是那个测试文件自己的合成输入。
2. 于是 dispatch 归档的两条 bounds 路线**从来没有被和解过**——这不只是「那个 bug 不可达」，也是
   一个**今天就在的独立缺陷**：界算出来了，读者仍然看到「退回到 IV 界」这条早已可兑现的建议。
   根因不是 pass 顺序排错了：识别那半在 `QueryResult` dataclass 上工作，估计那半在
   `result["data_gap_report"]` 这个 dict 上工作并且**有自己的一套和解机器**，两半对同一份报告
   各有一套改写机制，而只有一套认识 `answered_by`。**登记为独立待办，不在这一刀里悄悄改**——
   这一刀是它的前置条件：现在让估计端的路线到达和解，已经不会引入本条修掉的那个 bug。
3. `types.py` 说 `MANSKI_TAMER_MONOTONICITY`「既不可达也没有 builder」——**实测假**：
   `output/bounds.py:383` 建它，同一轮全量里它和 `balke_pearl_iv` 在同一份结果上并存过。注释
   已更正，并写清了「谁产出它」这个问题只有跑起来才能回答。

**方法论沉淀**：

**(343) 一个属性的类型比它要回答的问题窄一档时，缺口会先以「注释」的形式冒出来。** 判据很具体：
**去看有没有人给一个布尔值写解释**。布尔值不需要解释；需要解释，就说明它承载的信息比一位多，而
多出来的那部分现在住在散文里、任何一个 pass 都读不到。本刀两处「我不是 X，因为我给的是另一个
问题的区间」就是这样两句，它们比那条 bug 早得多。

**(344) 一个集合默认「包含」还是默认「排除」哪个安全，取决于它是用来接受还是用来逃离。** 用来
接受的集合，漏掉一个成员只是少答一次；用来**逃离**的集合，多一个成员就是把读者送回他刚逃出来的
地方。所以差集写法本身不是安全性论据——安全性只能来自一道把这个集合钉到「事实的那一侧」的闸口
（这里是 builder 实际挂了哪些假设）。本刀的第一版注释把这两者搞反了，反例把它证伪。

基线：7867 → **7871 passed / 176 skipped**（收集数 8043 → 8047，+4）。mypy clean（140 files）；前端未受影响
（`answered_by` 不上信封）。

### #443 契约的输入那一半在门上强制，输出那一半写在 docstring 里——于是它由「谁记得再调一次验证器」来守（2026-08-24）

`themis/kernel.py` 的模块 docstring 把两条契约并排写着：输入符合 `kernel_ast.schema.json`，
输出的 `results` 条目符合 `query_result.schema.json`。`run` 的 docstring 再说一遍。第一条在门上
强制（`validate_ast`）；第二条**没有任何人在产出时检查**——`validate_result` 只出现在 `verify*`
那一族里，那是验证器的入口，不是产出信封的入口。

**根因不是「有几个字段写错了」，是这一半契约的执行者是调用方。** 一个从不调 `themis.verify` 的
调用方永远不会撞上它；一套测试对它的覆盖，恰好等于「有几个测试记得自己调一次 `validate_result`」。

**先把分母量出来**：把校验挂在三扇公开门上跑一轮全量（插桩不改行为），按「门 + 首行错误」去重：

```text
estimate  estimation_context/model_preference: 'DRLearner'      不在声明的枚举里
estimate  estimation_context/model_preference: '  Linear  '     同上，没去空白
estimate  <root>: estimator_fallback                            有三个读者的块，schema 从没声明过
run       extensions/…/cde_status: 'reason'                     已声明的封闭对象里多一个键
```

**四条里三条在顶层，这不是巧合。** `extensions` 那一层有注册表闸口（`blocks.check_registered`，
18 个成员，两个出口各调一次），顶层只有 schema 的 `additionalProperties: false`——而没有人读它。
相邻两层，一层有守卫者一层没有，缺口就长在没有的那层。

**第五条是这一刀撞出来的，也是它为什么撞得出来。** #442 把 `data_gap_report.summary` 从 dataclass
和 schema 里删掉之后，`dispatch._file_gaps` 在「报告还不存在」的分支里**手写**报告的键集，于是它
继续写这个键——经 `themis.estimate` 到达公开信封，而全量套件全绿。实测复现：完整 framing 的
`cause` 查询 + 声明尺度与数据不符 → `report keys: ['gaps', 'summary']`。**插桩没抓到它**，因为
套件里没有「估计阶段第一个归档缺口」这个程序形状——这也说明为什么闸口不能只靠语料。

**修法：门上检查，四条各按根因修，报告只留一个作者。**

- `kernel._leaving()`：三扇门（`run` / `estimate` / `apply_patch_and_run`）返回前逐条校验
  `results`，与输入那一半对称。**代价实测为零**：全量 250s vs 基线 246s。
- `model_preference` 记的是「内核理解成了什么」，不是「调用方敲了什么」。这一条的第一版修法自己
  就错了一次，值得记下来：我先只把**上信封**的那份归一化，docstring 里顺手写了句「估计器本来就
  读得过去」——跑一遍就假了。`model` 有 **5 个读者**，其中 2 个（两个剂量-反应入口）归一化、3 个
  （backdoor、mediation ×2、joint）逐字比较，于是 `model='  Linear  '` 在一条路线上是答案、在另
  一条路线上是 `ValueError`，而信封记的是第三样东西——原样的串。正确的位置是
  `estimate_program`：它的 docstring 本来就写着「对每一个数值答案都必须成立的事，在这里成立一次
  而不是每族一次」。选项在那里变成选项，估计器和信封都只见到规范形式；集合外的值在同一处报错，
  而「这条路线认不认这个值」仍是各条路线自己的问题。
- `estimator_fallback` 补进 schema（`{from, to, reason}`）。它不是该删的东西：有三个读者（一个
  测试、语言闸口、渲染 prompt），缺的是声明。
- `cde_status.reason` 删掉：**零个读者**，而它旁边的 `status` + `reference_point_count` + `cap`
  已经把同一件事说全了；它是一段写在内核里的中文渲染（#437 那一族）。
- `_file_gaps` 走 `data_gap_report_to_dict`（与 `data_gap_to_dict` 对称的那扇门），顺手删掉 6 处
  没有目的地的中文 summary 串和 `_OVERLAP_CELLS_SAID` 里那条只被它读的表项。

**补上一条声明，把以这份声明为分母的闸口一起唤醒了。** `estimator_fallback` 一进 schema，浏览器
那道「每一个信封字段，本面都要说清楚拿它怎么办」的划分闸口立刻红了——这个字段在信封上存在多久，
就在那道闸口的分母外待了多久。答案是 `CARRIED_BY: 'estimation_context'`，而这是量出来的而不是写
上去的：全仓只有一处写这个块，它在同一段无分支的函数体里追加一条 data-contract 警告，把「要的是
哪个估计量、跑的是哪个、为什么」说全，而浏览器逐条原样打印这些警告。这条断言钉在**写入方**上——
一处写入、两条语句都不在任何条件里，多一个写入者或任何一条挪进 `if`，闸口就红。

**为什么闸口不是一个静态扫描。** 试过：按 AST 扫「往名叫 result 的 dict 上写字符串键」，19 个键
里 15 个已声明、**4 个是假阳性**（发现算法的 result、一个 population dict、一条台账条目——都叫
result，都不是那个 result）。要它绿就得配一张例外表，而例外表是第二份要维护的声明。校验挂在门上
之后，**套件里每一条走过那扇门的测试都成了这道闸口的一个样本**，分母是「跑到的路径」而不是「扫描
器认得的写法」。签入的那份只钉门本身：三扇门各伪造一份带未声明键的信封，要求门拒绝它；再用 AST
读遍 `kernel.py`，要求每一扇门的每一条 `return` 都经过 `_leaving(`——第四扇门以后加进来时，前三条
测试看不见它。六个反例全红：载体被删、载体挪进条件、多一个写入者、一扇门绕过 `_leaving`、报告多
一个作者、选项集的两份记录不相等。

**方法论沉淀**：

**(338) 一条契约里，「被强制的那一半」和「只被声明的那一半」会分家；判据是数这条契约在代码里出现
过几次。** 输入那半在门上，输出那半在 docstring 里，两句话并排写着，中间隔着一个从没有人调用的
函数。这条不需要跑起来才看得见：把模块声明的契约逐条列出来，去代码里找它的执行者，找不到的那条
就是。

**(339) 相邻两层，一层有注册表一层没有，缺口就长在没有的那层。** `extensions.*` 有
`check_registered`，顶层什么都没有，四条违规里三条在顶层。找法是把系统里的「封闭集合」按层列
出来，逐层问「谁在关它」——而不是逐个字段问「它对不对」。

**(340) 闸口宁可是「跑起来会红」，不要是「扫一遍会红」。** 静态扫描的分母是「扫描器认得的写法」，
它对同名不同物无能为力（19 个键 4 个假阳性），补救办法只有一张例外表，而例外表是第二份声明。把
检查放进真实路径之后，分母变成「测试跑到的路径」——它会随语料自己长大，也会诚实地承认没跑到的
地方（本刀那条 `summary` 就是插桩没抓到、要靠门上的检查才拦得住的）。

**(341) 一个字段没被声明，它逃掉的不只是自己那份 schema，还有每一道拿这份声明当分母的闸口。**
所以「补一条声明」这个动作会同时**发现**若干别的面上的缺口，而不是只让一处变绿；反过来，评估
「加一条声明的代价」时要把这些一并算进去——它们不是新债，是一直在的债刚刚被点名。

**(342) 一个调用方选项必须在唯一入口变成「选项」，否则每个读者都在各自决定它是什么。** 判据是
两个数：这个选项有几个读者、其中几个做归一化。5 和 2 就意味着同一个拼法在不同路线上是不同的
东西，而信封记的往往是第三样。找法不是读代码风格，是**对每一个跨模块传递的字符串选项问一句
「谁把它变成规范形式」**——答案是「好几个」或「没有」时就中了。这条也是本刀自己踩出来的：只归
一化上信封的那一份，等于给同一个选项加了第 6 个读者。

基线：7845 → **7867 passed / 176 skipped**（收集数 8021 → 8043，+22）。逐条：新闸口文件 20 条，
浏览器划分闸口按 schema 字段参数化 +1（`estimator_fallback`），「声明了装谁的话的槽位必须装得下
话」按 `x-text` 参数化 +1（`estimator_fallback.reason`）。mypy clean（140 files）；前端 `tsc -b`
+ `pnpm build` clean。

### #442 一段渲染好的话，就是「语言在内核里被决定了」本身——而 summary 以它为唯一输入，把这个形状焊住（2026-08-24）

#437 的第四刀，四条大头里最后也最大的一条：`description`。

**根因不是「这里有散文」，是这一栏在信封上只能是一个串——因为另一栏拿它当唯一输入。**
`summary` 的头就是第一条缺口的 `description`，后面按 `answer_tier` 加个框。只要 `summary`
还在信封上，`description` 就必须是一个能被直接拼进另一句话的串；把它拆成一串句子，`summary`
立刻变成「一串句子的渲染的渲染」。**这两栏必须同一刀走**——而这件事站在 `description` 自己的
40 个建造点上，一处也看不见。

先按判据把全量扫一遍，再动手：

```text
写 `description=` 的建造点                  40（data_gap_report 31 / dispatch 9）
它专属的 language.Words 表                  54
其中把一段话拼成 2-5 个可选片段的            4
其中用另一条模板渲染好的文本填这条模板的洞    4
```

**最后一行是这一栏的病灶形态，不是它的一个瑕疵。** 槽位装值或装词（#410），装不了句子：一旦
装了句子，那条内层模板的语言在内核里就被决定了，外层再怎么传 `lang` 也改不回来。四处分别是
中介从句、调用方的理由、位移原因、置信集——正是这四处，让「一条缺口说的话」没法成为一张表。

**修法：一段话是一串句子，不是一个带洞的串。**

- `themis.gaps.Sentence` 69 个成员分 13 组，`DESCRIBES` 69 行双语（两门合计 29,355 字，
  中文 9,310）。
- `DataGap.description` → `describes: tuple[GapSentence, ...]`，与 `alternative_paths`
  （#438）同构的 `{sentence, said?, words?}`。**每句各带各的场合**，因为一条缺口有几句取决于
  这一次知道什么——发现算法记没记稳定度、几个方法夹住了答案、第二个过度识别检验算没算。按组合
  建物种会是一张笛卡尔积表；一串物种是同一段话，各说一次。
- 三扇门：`sentence()`（写）、`sentence_fields()`（序列化）、`describe()` / `described()`
  （渲染）。**句子之间的接缝属于语言，不属于任何一句**：它原本焊在句子里——英文那句自带一个
  前导空格好让前一句不粘连，于是中文读者在段落中间看到一个空格。
- `summary` 整栏离开信封，照 (324)：它的每一个输入都在它旁边（`gaps[0]` + `answer_tier`），
  `gaps.summary()` 在知道语言的地方组装。`rederive_summary` 与 `dispatch` 里那句「删完缺口
  记得重算」一并消失——没有派生栏，就没有要保持同步的东西。

**顺带发现并修掉的四处已经在错的渲染。** 都不是这一刀引入的，是这一刀让它们可见：

```text
过度识别缺口              把英文 also 从句拼进中文段落
_OVERLAP_CELLS_SAID       写死 _lang.DEFAULT 渲染，调用方传的 lang 到不了
假设台账                  靠 "发现算法" in desc 判这条边的来历——第五个读散文认路的 pass
浏览器 framingVariables   用正则在渲染好的中文段落里找反引号标识符
```

后两处是同一件事的两面：**只要身份长在措辞上，读它的人就必须押一门语言**——浏览器那条更彻底，
它对英文读者第一次来就什么都找不到。台账现在读
`witness is gaps.Sentence.THE_EDGE_WAS_LEARNED_BY_DISCOVERY`，浏览器现在读 `entry.said` 里的
`variable` / `intervention` 两个槽位名。

**第五处是这一刀自己踩出来的，根因写在前面才动的手。** `MESSAGE_CAP` 是「站点原样插进来的
一个值」的上界，而 `assemble()` 把它加在**拼好的整句**上。值那侧已在 `halve()` 里逐槽上过界，
所以第二层 cap 只可能截到模板自己——语料里最长的那条
（`a_variable_declares_a_noisy_measurement`，英文 3246 字 / 中文 1486 字）远超 cap 的 1000，
截断处那句英文提示于是出现在中文段落中间。cut D 之前这条模板走 `fill` 不走 `assemble`，第二层
cap 从没被触发过：**不是今天才错，是今天才可见**；调大 cap 只是把同一个错误推后。cap 落回值
进洞的那一刻（`fill()` 里逐槽施加），`assemble()` 与 `gaps.wanted()` 外面那两层去掉。

**闸口：一个洞是一句承诺，静态钉住，而这一次的分母是每一个建造点。** 新文件读遍两个模块的
**61 处** `sentence(...)`，要求每一处递的键名与它那条句子的洞名**恰好相等**。61 处里只有 58
处用字面量命名物种，另外 3 处一个按分支挑、两个查表拿——**只看字面量的扫描会漏掉最该看的那
三处**，所以扫描顺着模块自己的 import 把名字解回 `themis.gaps.sentence`，再顺着所在作用域把
`said = Sentence.A if ... else Sentence.B` 和 `**slots` 解开。分支那一处还多一条：两条候选
句子的洞集必须相等，否则填了一条就等于给另一条的读者看一个槽位名。

反例是现成的，九条全红：少递一个键、多递一个键、`**slots` 里少一个键、分支挑的两条句子洞不同、
表里删掉一条于是有成员无人能说、第三个模块也开始造句子、建造点数对不上、一条句子没有正文、
一个洞只有一门语言有。

**方法论沉淀**：

**(334) 动一个字段之前，先找谁以它为输入——派生栏会把源栏的形状焊死，而这件事从源栏自己的
建造点上看不见。** `summary` 的存在就是 `description` 必须是串的全部理由，而它在信封的另一处、
由另一个函数写。这条是 (324) 的反向：(324) 认出「这一栏是渲染」，这条认出「这一栏正在替另一
栏保住一个形状」。判据很便宜——grep 这个字段名，看有没有第二个读者把它当原料而不是当结果。

**(335) 一个槽位里装另一条模板的渲染结果，就是把语言在内核里定死。** 外层无论拿到什么 `lang`
都改不回来，因为决定已经在内层发生过了。正确形态是内层那句成为**列表里的一个元素**，而不是
外层句子里的一个值——一段话是一串句子，不是一个带洞的串。这条把 #410「槽位装值或装词」补完了：
装不了的第三样东西是句子，而它恰恰是最容易顺手装进去的那样。

**(336) 一个「对插进来的值」的上界，必须施加在值进洞的那一刻，不能施加在拼好的结果上。**
后者只在「所有模板都比上界短」时看起来一样，而这是一个没人声明过、也没人测过的偶然。上界一旦
施加在结果上，它截断的第一个东西是内核自己的散文，而截断提示本身是一门写死的语言。

**(337) 闸口认「门」要按它解析到什么，不能按它拼成什么。** 这一刀的扫描第一版按函数名末段匹配
`sentence` / `_sentence`，于是把 `refusals.sentence` 和 `analysis_report._sentence` 两个同名
不同物的东西也算成了缺口句子的建造者——**分母从 2 个模块变成 4 个，而闸口的中心断言正是「只有
这 2 个模块」**。改法是顺着被检查模块自己的 import 把名字解回定义处。这和 #382「同一性不能用
拼写代替」是同一条，只是那次问的是值，这次问的是函数。

基线：7579 → **7845 passed / 176 skipped**（收集数 7753 → 8021，+268）。逐条：新闸口文件
**+230**（69 条句子 × 3 条逐句断言 207；两个建造模块 × 2 条配对 4；两门语言 × 2 组 4；不
参数化的 15）；`unnamed_thing` 成为 `Word` 词表 **+31**（逐词渲染 15、逐成员打印 6、逐表到达
7、同一性 2、语言是参数 1），其中 **2 条是故意跳过**——它按 `EnvelopeName` 放弃同一性，#382
那条闸口正是为此跳过它；`gap_describes` 与 `unnamed_thing` 进浏览器逐表闸口 **+4**、进两个
渲染器逐串对照 **+2**；语言闸口 **+1**。mypy clean（140 files）；前端 `tsc -b` + `pnpm build`
干净。

### #441 「补上之后能拿到什么」是物种的属性，21 个 producer 一行一行地讲了 17 遍（2026-08-24）

#437 的第三刀，四条大头里的第三条：`if_provided`。

**根因不是「这里有散文」，是这个字段问的问题只有 `kind` 能回答，而它被存成了这一次的事实。**
先按判据把全量扫一遍，再动手：

```text
写它的 producer                        21
它们用的模板                           17
已经是双语 language.Words 的            20 / 21
对同一个 kind 给出不同答案的 producer     0
这一次才知道、模板里真有洞的槽位          5（collider / value / intervention / won / lost）
```

**零分歧。** 21 个作者里没有任何两个对同一个物种说了不同的话——所以它从来不是「这一次」的
事实，是一张 kernel 已经有的表，被一行一行地讲出来，然后在出门时冻进讲的人当时传的那门语言。

**修法：表说出来，缺口只带洞里的东西。**

- `themis.gaps.IF_PROVIDED` 20 条双语句子，按 `kind` 索引。
- `DataGap` 长出 `said` / `words`——和 `MissingItem`（#435）、`GapRoute`（#438）同一个三字段
  形状，一条缺口一对。**一对而不是每句一对**：把这 5 个槽位名和第四刀要动的 `description`
  的槽位名并排比过，**零冲突**，所以「这一次的事实」在一条缺口上是一份，这也是第四刀的地基。
- 三扇门：`occasion()`（写）、`occasion_fields()`（序列化）、`if_provided()`（渲染）。
  schema 里 `dataGap.if_provided` 换成 `said` / `words`，用的是 `gapRoute` 已经在用的那两个
  `$ref`——一个字段的第二种拼法就是第二个要维持相等的东西。
- 下一步那一栏的判据也跟着换：从「这个字段有没有值」改成「这个物种在不在表里」。

**故意只有 20 条，所以另外 16 条也得写下来——`themis.gaps.NOTHING_FILLS`。** 剩下 16 个
物种是「补什么都不改变它」：区间本身就是答案、假设只能被接受不能被测量、声明和数据互相矛盾、
工具被数据证伪。**半张表读起来和整张一样**（那是 (325)），所以「答过了：没有」必须是一件要写
下来的事，否则它和「没人答过」在闸口眼里长得一模一样。两张表严格划分 36 个 `GapKind`，无重叠
无遗漏。

**洞是一句承诺，静态钉住。** 4 个物种的句子里有洞，4 个建造点递了 `**_occasion(...)`——闸口
用 AST 读遍两个模块的 **38 处 `DataGap(...)`**（37 处字面写出物种，第 38 处是解码器），要求
每一处递的键名与它那条句子的洞名**恰好相等**。多递一个，是一个到不了任何读者的事实；少递一
个，是读者看见一个反引号包着的槽位名。

**顺带发现并修掉的一处已经在错的渲染：浏览器的 `fill` 只实现了一半的模板语言。** kernel 用的
是 `str.format` 的迷你语言，浏览器用的是一条正则 `\{(\w+)\}`——**它认识洞，不认识转义**。
以前不暴露，是因为浏览器只拿手写表，手写表的作者没人写过 `{{`；#399 把表改成 kernel 生成之
后，kernel 能写的每一种构造浏览器都得能读。把两个渲染器跑在今天全部生成表的语料上：

```text
GAP_SAYS  counterfactual_not_identifiable      zh / en    y'_{{x'}}          → 浏览器多两层括号
GAP_SAYS  graph_contradicts_supplied_marginal  zh / en    {{{extras}}}       → 同上
GAP_IF_PROVIDED  measurement_error_concern     zh / en    {{error_variance}} → 同上（本刀新增）
```

**前两个物种在这一刀之前就已经在信封上**——也就是说浏览器一直在给读者看多余的括号，而
「两张表逐字相等」那道闸口全绿：**它钉的是表，不是渲染的结果**。修法是把分词器抽成
`language.ts` 里的一个 `TOKEN` 常量加一个 `holes()`，`fill` 与 `assembled` 都走它（原来
`verdict.ts:360` 自己写了第二条同样残缺的正则）；闸口把浏览器的分词器**从它自己的源码里读
出来**，用它渲染每一条生成串，要求与 `str.format` 逐字相等。反例是现成的：旧正则在语料上
6 条不一致，新的 0 条。

**`Occasion` 在浏览器侧也只留一份。** `types.ts` 里 `GapRoute` 内联写着 `said` / `words`，
`DataGap` 本来要成为第三份、`verdict.ts` 里还有第四份（防御性的宽版）。现在是一个
`export interface Occasion`，两个信封类型 `extends` 它，`verdict.ts` 直接 import。

**prompt 里那 4 处「surface the gap's `if_provided`」指向的字段已经不存在了。** 机制在
§「Four checks per gap」的开头说一次——句子按 `kind` 读、有些物种根本没有这一句，而那是一个
答案；4 处只删掉字段名，括号里的实质内容一条没动（那是这一刀没有审过的东西，不在这里顺手改）。

**方法论沉淀**：

**(331) 判断一个字段是「物种的属性」还是「这一次的事实」，判据是：有没有两个 producer 对同一
个物种给出不同的值。** 零分歧就是它一直是一张表，只是被一行一行地讲。这条和 (324) 互补：
(324) 问「它的输入是不是都已经在旁边」，这条问「同一个物种的答案稳不稳定」——前者认出「这是
一层渲染」，后者认出「这是一张表」。

**(332) 一张故意只覆盖一部分的表，必须把「不适用」也列成一张表。** 否则闸口分不清「答过了，
答案是没有」和「没人答过」——这两件事在代码里都表现为「这个键不在表里」。写下来的代价是一行
给下一个人看的英文，收益是新物种落在两张表之外时当场红。

**(333) 两个面各自实现同一套模板语言时，要钉的是「同一串在两边渲染出同一个结果」，不是「两边
的表相等」。** 表相等的闸口早就有，它挡不住渲染器少实现一条规则——语料里 6 条串（3 个物种）
就是这么在浏览器上错着的，其中 2 个物种在这一刀之前就已经在信封上。**闸口要读被检查那一侧的
源码来取它的规则，而不是在测试里再抄一份**：抄一份就是第三份声明，它会和自己相等。

基线：7418 → **7579 passed / 174 skipped**（收集数 7592 → 7753，+161）。逐条：新闸口文件
**+157**（20 条 × 2 门语言的整句装配 40；32 张生成表逐表两渲染器对照 32；20 条各自的
语言完整性与洞名一致各 20；16 条「什么都补不上」的物种各 2 条 32；两个建造模块的静态配对 2；
不参数化的 11 条）；`gap_if_provided` 进浏览器逐表闸口 **+2**；语言闸口 **+2**
（`if_provided` 的 `x-text` 声明 −1，`said` / `words` 两处 +2，`NOTHING_FILLS` 那条
allowance 的「还在用吗」检查 +1）。mypy clean（140 files）；前端 `tsc -b` + `pnpm build`
干净。

### #438 装的是「哪一条路」，存的是「说出来什么样」——于是三个 pass 靠读散文认路（2026-08-24）

#437 的第二刀，四条大头里的第二条：`alternative_paths`。

**根因不是「这里有散文」，是这个字段的身份长在措辞上。** 它命名的是「绕过这个缺口的哪一条
路」，存的却是渲染好的句子。于是三个需要知道「这一条是哪一条」的 pass，只能从句子里把它认
回来：

```text
data_gap_report._withdraw_interval_offers       把句子重新拼一遍，然后字符串相等
data_gap_report._rewrite_iv_aware_alternatives  按整句中文匹配「找一个满足 IV 条件的工具变量」
runtime.scheduler._is_bounds_hint               搜 "bounds" / "Manski" / "Balke-Pearl bounds"
```

**第二条 pass 写下的替换句，带着一句注释说明它是特意那样措辞的——好让第三条 pass 搜不到它。**
一句面向用户的中文的措辞，是 kernel 控制流的输入；两个模块之间的契约是三个子串，而维持它的
唯一机制，是人记得。

**单语言下这件事没有形状，因为只有一种措辞，措辞就等于身份。** 把旧判据跑在今天双语的路线
表上，`bound_the_unsupported_region` 这一条：

```text
zh 「对没有支撑的那片区域，只给出界的答案」        旧判据 = False
en  "give a bounds answer over the region ..."      旧判据 = True
```

同一条路线，中文读者留着，英文读者被撤走。这不是已经发生的事故——旧代码那一栏只有中文，无从
分歧；是**第二语言落地当天就会发生**。这正是这一刀要排在 #395 之前的原因。

**第二个作者：`dispatch.py` 也在写这个字段，7 处 22 条。** 两个作者对同一条路线的措辞差一个
括号：

```text
data_gap_report          「退回到只给界的答案（Manski 自然界 / Balke-Pearl IV 界…）」  → 被替换
dispatch.py（过度识别弱）「退回到只给界的答案（对弱工具稳健）」                        → 不被替换
```

**那个括号决定控制流。** 同一句建议、同一个因果情形（工具弱 → 退回到界），只因为一处写了
"Manski" 一处没写，scheduler 对它们的处理不同。

**修法：条目变成 `{route, said?, words?}`——和 #435 的 `MissingItem` 同一个三字段形状。**

- `themis.gaps.Route` 63 条封闭词表，每条带 `points_at_bounds`（pass 唯一要问它的属性，由路线
  自己声明）和一句给「下一个添路线的人」看的 `says`。
- `themis.gaps.ROUTES` 63 条双语句子。写、序列化、反序列化、认身份、渲染是五扇门：
  `route()` / `route_fields()` / `route_entry()` / `taken()` / `went()`。
- 三个 pass 改成对**声明出来的东西**判断：`a.route != Route.ACCEPT_THE_INTERVAL`、
  `a.route == Route.FIND_AN_INSTRUMENT`、`alt.route.points_at_bounds`。scheduler 那条裸中文
  `"已计算 bounds（method=…）"` 变成带 `{methods}` 值槽的双语路线。
- schema `$defs/route`（63 成员）+ `$defs/gapRoute`；浏览器走 #399 的生成表拿到 `GAP_ROUTES`。
- `language.Word.named()`：按 token 取成员。`Route(str(x))` 这种查表写法在类型检查器眼里是
  「少传了两个构造参数」，于是每一处查表都要一个 ignore——而一个 ignore 和盖住真错误的那个
  长得一模一样。

**槽位里的形容词也是词（#410 的又一个实例）。** `dispatch.py` 那条「若 `{variable}` 确实是
{scale} 的」把 `scale_word(...)` 的**渲染结果**插进句子。`envelope_glossary.SCALE` 那张 dict
升成 `Scale(language.Word)`，值走 `words` 半边（`{vocabulary, token}`），浏览器多一张生成表
`MEASUREMENT_SCALE_WORDS`。不这么做，就是在同一个 commit 里重新打开 #411 刚关上的洞。#362 的
到达闸口当场把后续要过一遍：新词表欠一行 reach 记录、欠浏览器 `VOCABULARIES` 里的一行——8 条
断言，全是「你造了一个词表，它到六个面的路还没说清」。

**三处声明出来的行为改动：**

- 上面那两条「退回到界」合并成一条 `fall_back_to_iv_bounds`。合并意味着**过度识别那一处的行为
  变了**：它现在也会被 bounds 指针替换，和刚好识别那一处一直以来的行为一致。选这一边，是因为
  那台机器本来就是为这件事造的，而两条句子的差别是手写漂移。
- `find_a_stronger_instrument` / `find_stronger_instruments_jointly` **没有**合并：一个说单个
  工具，一个说这组工具的联合第一阶段，是两件事。
- `fall_back_to_bounds_without_exclusion` 保留 `points_at_bounds=True`（忠于旧判据），但它语义
  上可疑——排他性被数据否掉之后，把它替换成一个 Balke-Pearl 指针，正是把读者送去看那个假设刚
  被否掉的界。**登记为待办，不在这一刀里悄悄改。**

**新闸口的反例是构造出来跑过的，不是声称的。** 把 `fall_back_to_iv_bounds` 的句子改成不含那
三个子串，旧判据答 False / 路线答 True；把 `find_an_instrument` 的句子改成含 "Manski"，旧判据
答 True / 路线答 False。两条都指向被替换掉的那个实现。

**方法论沉淀**：

**(328) 一个字段装的是「哪一个」，却按「说出来什么样」存，identity 就落到措辞上。** 需要知道
「这是哪一个」的 pass 只能去读散文，而**单语言下这件事没有形状**——只有一种措辞，措辞就是身
份。第二语言不是把它暴露出来，是把它**变成 bug**：同一条路线在两个读者那里得到两个答案。所以
「值和句子分开」要排在第二种语言之前，不是之后。

**(329) 「我这句话特意这么写，好让上游匹配不到」——这种注释是一份结构报告，不是一条注意事项。**
它说的是：两个模块之间的契约是一个子串，维持它的唯一机制是人记得。写下这句话的人已经把根因
诊断完了，缺的只是把契约从措辞搬到名字上。**代码里出现「为了绕开别处的匹配而选的措辞」，就该
去把那处匹配换掉，而不是把绕法记下来。**

**(330) 同一件事的两个作者，差别会落在括号里，而括号可能是控制流的输入。** 判断「这两处是不是
一件事」不能只看句子像不像——要看**下游对它们的处理是否相同**；处理不同而语义相同，就是漂移已
经产生了后果。合并时必须当场声明选了哪一边的行为、为什么，以及哪几对看着像而**不该**合并。

基线：7124 → **7418 passed / 174 skipped**（收集数 7296 → 7592，+296）。逐条：新闸口文件
**+265**（63 条路线 × 4 条逐路线断言 = 252，加 13 条不参数化的）；`Route` 与 `Scale` 进
`EnvelopeName` 同一性两组闸口 **+6 / +2**；`Scale` 成为 `Word` 后进「槽位里的词」闸口
（4 个成员 × 2 门语言 + 4）**+12**；`gap_route` 进到达表 **+5**、`gap_route` 与
`measurement_scale` 进浏览器逐表闸口 **+4**；语言闸口 **+3 −1**（`alternative_paths` 的
`x-text` 声明拆成 `said` 与 `words` 两处，加 `Route` 那条 allowance 的「还在用吗」检查）。

### #437 一条 if 链 + 一个回落，就是一张没写完的表——而回落让「没写完」看起来像「覆盖了」（2026-08-23）

登记的说法是「data_gap_report 四条大头占了信封散文的 71k，它自己就是一层渲染，长在 kernel
里」。四条里最小的那条先动，因为它是唯一一条**整栏可以消失**的：`actionable_next_steps`。

**它的每一个输入都已经在它旁边的对象上。** 哪些缺口阻断（`severity`）、哪些有地方可去
（`if_provided`）、第一条备选是什么（`alternative_paths[0]`）、每条缺什么（`kind` +
`required_data` + `provenance`）——全部在 `gaps[]` 里。这一栏没有自己的事实，schema 里那句
描述把话说全了：

```json
"description": "User-facing suggestions in order of impact.
                Each entry is a complete sentence in Chinese;
                rendering layer reads these as-is."
```

**契约里写着「中文」。**

**它长在 kernel 里，代价是两个与渲染无关的模块替它操心。** `dispatch.py` 删掉缺口后要调
`rederive_summary_and_steps`（它自己的 docstring 警告「只重算 summary 就会漏，于是一份已经
没有分布缺口的报告继续用『补 P(y=True|w=True,x=True)』开头」）；`scheduler.py` 更直接——

```python
# Prepend so actionable_next_steps (which surfaces only the
# first alt) shows the already-computed fallback ahead of
# heavier structural suggestions like 'do an RCT'.
```

**kernel 在为一个视图排版。**

**造这一栏的那个函数，正在做它自己声明要防的事。** `_short_label_for` 的 docstring 说：完整
`description` 是一整句，拼进「补 X」会变成一堵字墙，所以每个 gap kind 给一个 1-3 个名词的短
标签。实测：

```text
gap kind 总数                36
链上具名的                   12
`return gap.description`     24
```

语料上有 6 个 kind 真的走到回落，产出 17 条「补 + 一整句」；其中
`measurement_error_concern` 的 description **中位数 1518 字**。

```text
   60  missing_distribution                          label      desc~40
   31  ambiguous_variable_definition                 label      desc~98
   12  ill_defined_intervention_versions        --> 整句        desc~583
    2  measurement_error_concern                --> 整句        desc~1518
    1  dose_response_data_required              --> 整句        desc~301
    1  unattempted_layer_due_to_dispatch_conflict --> 整句      desc~343
    1  selection_on_collider_opens_path         --> 整句        desc~417
```

**修法：短标签升成词表，对 `GapKind` 全覆盖，然后这一栏离开信封。**
`themis.gaps.WANTED` 36 条（+ `WANTED_NAMED` 5 条，给「这一次能报出变量名」的场合），读者面
的门是 `gaps.wanted(gap, lang)` / `gaps.next_steps(gaps, lang)`——和 #411 对拒答做的是同一个
形状。浏览器走 #399 那条路拿到生成的 `GAP_WANTED` 表；框架句「补 {}」留在各自的面上，和拒答
的 head/lead/tail 同理。

**三处顺带清掉的东西，都是这一栏在信封上才需要的：**

- `rederive_summary_and_steps` → `rederive_summary`。删缺口自动带走它的步骤，那一整类
  「派生面没跟着重算」的 hazard 对这一栏不存在了。
- `scheduler.py` 那段重建 + `[s for s in new_steps if "bounds_result" not in s]` 的子串过滤
  没了。过滤存在是因为 tail 把 `alternative_paths[0]` 原样抄了一遍，于是一段**已经算出来的
  区间**被当成「通往它自己的路」推荐给读者。
- tail 里的「或：」行整条取消。**同一份内容在两个面上的角色不一样，说明它放错了层**：主报告
  逐条印 `alternative_paths`，那条「或：」是重复；浏览器一条都不印，那条「或：」是**唯一**
  出口，另外几条备选谁也看不到。现在备选跟着缺口走，浏览器补上了这一节。

**顺带修的两处措辞。** 中文短语里的列表分隔符原来硬写 `", "`（`", ".join(rd.variables)`），
改成 `language.BETWEEN_ITEMS` 的 `、`；`missing_distribution` 取分布名时把 pusher 的
`parameter:` 前缀剪掉这件事，从生成器搬进了门里。

**闸口第一次说「不」是对既有代码说的**：全覆盖判据在 HEAD 上是 12/36。此外还立了两条——
短语长度上限 140（当初回落进来的那句是它的十倍），以及契约层面
`dataGapReport` 不再接受这个键（`additionalProperties: false`），谁再写就在这里知道。

**方法论：**

**(324) 一个字段，如果它的每一个输入都已经在它旁边的对象上，它就没有自己的事实——它是一层
渲染。** 判据不是「看起来像散文」，而是**逐个输入去找它今天在哪**；找完发现一个都不缺，这一栏
就是可以消失的。

**(325) 一条 if 链加一个回落，是一张没写完的表；而回落让「没写完」读起来和「覆盖了」一模
一样。** 12/36 不会报错、不会告警、不会留下痕迹，只会让三分之二的读者收到别人的句子。改成
对枚举全覆盖之后，「没写完」才有形状可以被闸口抓住。

**(326) 函数的 docstring 说它存在是为了防住某件事——那是一句可测的断言。** 这一条在语料上
被违反了 17 次，而没有任何东西在读它。写下判据的地方和检查判据的地方分开，判据就只是注释。

**(327) 同一份内容在两个读者面上的角色不同，说明它放错了层。** 那条「或：」行在主报告是
重复、在浏览器是唯一入口——一份内容不该在一个面上是噪音、在另一个面上是刚需；出现这种不对称
时，要动的是它挂在哪里，不是给某个面加过滤。

基线：7076 → **7124 passed / 172 skipped**（收集数 7248 → 7296，+48）。逐条：新闸口文件
**+47**（36 个 kind 的全覆盖 + 2 门语言 × 2 条 + 7 条）；新生成表 `GAP_WANTED` ×
`test_web_vocabularies` 的两条逐表闸口 **+2**；schema 少一个 `x-text` 声明 **−1**。
mypy clean（140 个源文件），`pnpm build` 通过。

### #436 装着调用方文字的槽，kernel 命名不了它——开放本身就是那句声明（2026-08-23）

登记的说法是「调用方自己的话穿堂而过，和 kernel 写的散文长得一样；任何『信封上还有多少散文』
的闸口都会把它们算进去，**分母永远清不干净**」。**这句话在今天不成立，而查清它为什么不成立
才找到了真的那条。**

按「信封上这个串是否原样出现在调用方交进来的 program 里」跑全语料：

```text
信封字符串路径      243
  只装调用方的串    114        其中 110 条是标识符（predicate 29 / name 26 / type 26 …）
  只装 kernel 的     126
  两者都装             3
```

**只装调用方「文本」的只有 4 条**，而这 4 条恰好就是语言闸口 `VERBATIM` 表里已经逐条标了
"declared by the user" 的那 4 条。闸口是对的，分母是干净的。登记举的 `.note` / `.rationale` /
`.disambiguation_ask` 语料上没出现。

**真正的缺陷是这个判断的载体。** 「这段文字是谁写的」是关于**来历**的事实，而 schema 只描述
**形状**（type / required / enum）。于是它退化成散文，在 13 份 schema 里被**用六种措辞各说了
一遍**——`ambiguities` 说「authored upstream by a user or a language model, not by the kernel」、
`numeric_result.unit` 说「never produced by the kernel」、`outcome_error.source` 说「as supplied
by the caller」、`variablePatch.existing` 说「already set on the VariableDeclaration」……**六个
作者，零个读者**；唯一需要它的那个消费者（语言闸口）只能自己从头判一遍，把答案记在自己的表里。
#395 是第二个消费者，它读不到第一份，只能再抄第三遍。

**一个实测把登记的两个候选解法都否掉了。** 把 25 条已分类路径逐条拿到 schema 里找槽位：

```text
能找到槽位的：21 / 25
找不到的 4 条：extensions.ambiguities.[].description
              investigation_requests.[].items.[].skeleton.existing.{measurement,observability,threshold}
```

**找不到槽位的那 4 条，正好就是调用方写文本的那 4 条。** 不是巧合，是结构本身：**一个装着调用
方文字的槽，kernel 命名不了它——命名它就是在主张「你只许写这几个字段」。** 两个容器都是
`additionalProperties` 开放的 object，而**开放本身就是那句「这不是我写的」，只是读不出来**。于是
登记的候选一（「归到一个声明过的容器下」）多余——容器早就在那儿；候选二（「每个字段声明
`authored_by`」）不可能——这 4 条根本没有字段可以声明。

**修法：来历成为 schema 上一个可读的声明，挂得上叶子也挂得上容器。**
`themis.language.Text` 是那个封闭词表，六个成员各是一条**理由**——`kernel` / `caller` /
`formula` / `citation` / `identifier` / `value`——而每个消费者真正要问的那一位是
`translated`，只有 `kernel` 为真。**多对一是刻意的**（四个成员共享 `False`）：想知道「要不要
翻」的读一个属性，想知道「为什么」的读到理由，而这正是它不会变成一个布尔的第二份记录的原因
（#434 的判据）。

写进 schema 的键是 `x-text`，29 处（`query_result` 28 + `derivation` 1），沿 `$ref` 展开后覆盖
**42 条信封路径**。Draft 2020-12 忽略不认识的关键字，所以这**加了一个事实而没有加一条约束**
——正好是被声明的那件事的形状：「这是谁的话」不是对槽里能放什么的限制。语言闸口的两张私有表
（`PROSE` 14 行 / `VERBATIM` 11 行）整体删除，改成沿 schema 走一遍、按最近的容器往上找。

**第二条缺陷，是查第一条时撞出来的，而它是这个模块把自己的规则用在自己身上。** 决定「哪些路径
要被分类」的判据是 `_could_be_a_sentence`——**要有空格、且至少两个拉丁词**。中文两样都没有。于是
**任何只用中文写的文本从来没有进过这个分母，一次都没有被问过「这是谁的话」**。语料上已经有两条
kernel 中文散文落在外面：`data_gap_report.gaps[].required_data.sutva_concerns[]` 和
`extensions.assumption_ledger.summary`（一整段台账小结）。

**反例是既有代码，且验过了**：把这一刀为它俩加的声明撤掉再问一次——旧判据点名 **0** 条，新判据
点名的正好是**那两条**。判据改成按脚本分开问：拉丁文要空格 + 两个词（标识符两样都没有），中文
只要出现即可（#411 之后词表已经以 token 离开信封，信封上剩下的中文只有散文）。

**一条刻意不做的事，明说。** kernel 侧**没有**建「读 schema 回答这个问题」的函数，浏览器侧也没有
生成对应的表。今天唯一的消费者是闸口，而在 kernel 里放一个零消费者的读者正是 #338 拆掉的形状；
#395 需要它的那天再建，那时它的签名由真实需求决定而不是由此刻的猜测决定（(312) 的同一条）。
被声明的事实已经在契约上，搬读者是一次 import 的事。

基线：7054 → **7076 passed / 172 skipped**（收集数 7225 → 7248，+23 = 新增 50 − 删去 27）。
逐条：新增的 **+42 是逐条声明**（新闸口「每条声明都坐在一个装得下串的槽上」，一条声明一个用例）、
`Text` 进四个既有词表闸口 +4、`test_vocabulary_reach` 的行 +1、豁免行 +1、改名的那条 +1；
删去的是 `test_every_classified_path_is_still_produced` 的 25 条、`test_a_path_is_not_in_both_lists`
1 条、改名的旧名 1 条。skipped +1 是 `Text` 作为 `EnvelopeName` 在 #382 那条同一性闸口上的故意
跳过。mypy clean（140 个源文件）。浏览器无改动。

**一条守卫换了形状，说清换成了什么。** 被删的 `test_every_classified_path_is_still_produced`
问的是「这条分类对应的路径，语料真的产出过吗」——那是一张手写表能被要求做到的最强的事，但仍然是
**语料限定的**：它甚至不能命名一条语料到不了的分支，而 schema 声明了很多条。换上的问题问 schema：
**每条声明都坐在一个装得下串的槽上吗**——`string`、串的数组、或一个开放对象（它下面的东西正是这条
声明说的那些）。同一个位置，一个没有任何一次运行能收窄的答案。

**方法论。**

- （321）**「这个区分不立，所以分母是错的」这类登记，要先分别量「区分」和「分母」。** 这里分母
  是对的（4 条全在表里），错的只有载体。判据：把同一条判据用机器跑一遍全量，然后**逐条对照现有
  的那张手写表**——两边一致就说明表是对的，缺陷在别处；不一致才是分母问题。跳过这一步会去修一个
  不存在的缺陷，并且真正那条（载体）会被顺手带过而不被写下来。
- （322）**一个事实无处安放时，先问它现在被记在哪里、记了几遍。** 六段散文说同一件事，就是这个
  事实真实存在、需要被表达、而且没有一等表达方式的证据——比任何论证都硬。反过来，如果一遍都没
  有被记过，那多半是它还不需要存在。
- （323）**「这条声明挂不上去」不是障碍，是关于被声明对象的信息。** 25 条里挂不上的 4 条正好是
  调用方写的那 4 条，因为装调用方文字的容器必须开放。第一反应「先给它们补上字段名再声明」会把
  这条信息毁掉——**那个字段名本来就不该由 kernel 来写**。挂不上的时候要问的是「为什么这里没有槽
  位」，答案常常就是该被声明的那件事本身。

### #435 缺口的句子有 38 个作者，而「缺什么」这一层根本不存在（2026-08-23）

登记的说法是「缺口的 `reason` 与拒答的 `reason` 是同一个形状——`MissingItem` **已经带着**
`GapKind`，缺的**只是**把值和句子分开」。前半句对，后半句错，而错在哪里是这一刀的全部内容。

`GapKind` 有 36 个成员；这条通道上实际要说的话有 33 种，落在其中 **7** 个 kind 上：

```text
unidentifiable_no_admissible_set    10
missing_structural_input             8
missing_assumption                   7
missing_distribution                 5
graph_theta_independence_mismatch    1
missing_unit_observation             1
ambiguous_variable_definition        1
```

最大的一格里 10 种话共用一个 kind。**`GapKind` 不是物种，是物种的像**——它回答「这是哪一类
缺口」（读者据此拿到哪一类修法），物种回答「这一次缺的是什么」（读者据此拿到那一句话）。
#434 刚立的「映射要比源粗」在这里换了个方向用：**正因为它比物种粗，它就当不了物种**。于是
缺的不是「把值和句子分开」这个动作，是**被分开的那一层根本不存在**——句子由 38 个点各写各的
（`scheduler.py` 34 处条目构造，加 4 处 `InsufficientTheta` 抛出点：3 处在 `numeric_estimator.py`，
1 处也在 `scheduler.py`），`GapKind` 只是它们碰巧都填了的另一个字段。

**修法：`themis/gaps.py`，`themis/refusals.py` 的孪生。** `Need(EnvelopeName)`，每个成员是
`(token, GapKind, 维护者的一句描述)`；**kind 从物种读出来**，于是「这条缺口属于哪一类」不可能
和「这条缺口是什么」不一致——那正是 38 个各写各的构造点保证不了的事。`SAYS` 一个物种一句、
两门语言，沿用 #411 的 `said`（已成符号的值槽）/ `words`（`{槽名: {vocabulary, token}}`）分割。

**造这个孪生的时候才发现，要孪生的那套机器一直是按它的第一个用户命名的。** `describe` /
`capped` / 场合压平 / 模板组装这四件事全在 `refusals.py` 里，而它们和拒答没有关系——它们讲的
是「一句带洞的话，加上这一次的事实」。缺口是第二个用这个形状的东西，而**缺口不是拒答**：一
个只为了拿组装器而 `import refusals` 的模块，命名的是第一个用户，不是那件东西。四件事整体搬
进 `themis/language.py`（`refusals.py` −236 行），两个通道并排调用同一套。这也是语言债务表上
`themis/refusals.py` 那一行消失、`themis/language.py: 1` 出现的原因：截断提示是**跟着上限走
的**，上限搬了它就搬。

**多了一个词表 `QueryPart`（6 个成员）**：「缺的是查询的哪一部分」——`query` / `causation_query`
/ `scm_counterfactual_query` / `counterfactual_event` / `proximal_role` / `longitudinal_spec`
——是一个**词**，不是一个串。这是 #410 那个机制的第二个用户，而第二个用户是它值不值得存在的
证据。

**门有五扇，各对一种形状**：`gaps.missing()` 造 `MissingItem`、`gaps.item()` 造
`InvestigationItem`、`gaps.fields()` 只交出信封上那三个字段（给不是条目、但走同一条异常的那个
块用）、`gaps.carried()` 从**两种**形状里任取其一读回那三个字段、`gaps.said()` 组句。
`scheduler.py` 34 处全部走门；裸构造只剩三处：`gaps.py` 里的两扇门本身，和
`investigation_pusher` 把物种从缺失条目**抄**到调查条目的那一处——那是投影，不是第 39 个作者。

**`**details` 把槽名和形参名放进了同一个命名空间**，因此撞了两次，而两处的解法**必须不同**。
`_missing_parameter_from_key` 的首参叫 `key`，物种的槽也叫 `{key}`——用位置参数 `/` 把形参搬出
关键字命名空间。`gaps.item` 的形参叫 `target`，不匹配那个物种的槽也叫 `{target}`——改**槽名**
（`{target}` → `{variable}`），因为 `target` 是 `InvestigationItem` 的一等字段，搬不走。判据：
**槽名属于句子，形参名属于门**；撞了就把其中一个搬出去，而搬得动的是哪一个，由「谁另有身份」
决定。

**三处刻意的行为变化，逐条说明。**

- **混合物种的调查分组不再有 note。** 原来那句是「N 条，各有各的原因」——一句关于这组**有几
  条**的话，不是关于**缺什么**的话，读者拿它做不了任何事。现在：同物种同场合 → 保留那一条；
  不同 → 没有。而「同不同」判的是 `json.dumps(事实, sort_keys=True)` 相等，**不是渲染串相等**
  ——同一件事在两种语言下是两个串，靠串判同一性等于让答案取决于读者是谁。
- **收集到的其余缺失键不再继承抛出者的物种。** `collect_missing_keys` 会把抛出点之外的其余
  键也列出来；原来它们复制抛出者的 `reason`。当抛出者是 `graph_contradicts_supplied_marginal`
  时，那等于把「你的图和你给的边缘量互相矛盾，去改图」这条修法，发给了一批只是**单纯没给**
  的键。现在抛出的那一个保留自己的物种，其余是 `theta_entry_missing`。
- **两句话丢掉了各自的一截，都是术语名而不是事实。** `strict_framing` 那条不再以选项名开头
  （`kind=framing` 已经说了是哪扇闸在拦）；d-sep 那条不再说 "d-separation"，改成直接写出它指
  的那个断言：`{变量} ⊥ {额外条件} | {原条件}`。

**声明的取舍，写在 `SAYS` 的 docstring 里：还有 5 个槽装着别的层已经渲染好的散文**
（`proximal_not_identifiable` / `transport_not_identifiable` /
`interventional_risks_contradict_the_joint` 的 `{detail}`，以及三个 interventional-risk 物种的
`{note}`——其中一种形态引的是一条拒答）。它们的作者在别的模块，这一刀收不了；#436 / #437 是
它们的刀。**这条取舍登记在 `SAYS` 旁边，而不是记在这条时间线上**——下一个动这张表的人在表上
就能读到它，而不必先找到这一段。

**一个既有闸口在这一刀上先说了「不」，而它说错了。** `test_no_part_of_a_block_is_silent` 报了
12 个「没有读者」的键——但那些键**有**读者：浏览器侧 `thetaArmStatus` → `gapSaid` →
`assembled`，三跳。闸口的 `_ts_closure` 只走**一跳**，看不见第三层里那两个 `.said` / `.words`
的读。修法是把闭包改成传递闭包，不是加 12 行豁免——**一个只走一跳的可达性判据，对任何三层深
的辅助函数链都会误报，而它今天恰好只有这一条链**。

语言闸口上，`PROSE` 从 19 行降到 **14** 行，**而那 5 行不是被翻译掉的，是不再是串了**：
`missing_information[].reason`、它在 `investigation_requests[].items[]` 上的投影、汇总它们的
`note`、以及中介两臂的 `.reason`。内核单语字符串：`scheduler.py` 51 → **13**、
`numeric_estimator.py` 5 → **0**、`investigation_pusher.py` 1 → **0**（共 44 条）。

基线：7020 → **7054 passed / 171 skipped**（收集数 7189 → 7225，+36 = 新增 46 − 删去 10）。
逐条——**其中 +39 一条新测试都不是，全是两个新词表被既有闸口收进分母**：
`test_a_word_reaches_the_reader_as_a_word` +18（`QueryPart` 6 个成员 × 2 语言 = 12，加「token
在每种语言下相同」6 条）、`test_a_vocabulary_prints_as_the_word_it_is` +6（2 个词表 × 3 条）、
`test_vocabulary_reach` +5、`test_web_vocabularies` +4（2 张新生成表 × 2 条逐表闸口，与 #411
同型）、`test_a_vocabulary_that_gives_up_identity_is_not_asked_for_it` +3、另三个闸口各 +1。
真正新写的只有 **+2**（调查分组的两条 note 性质），加上语言闸口的 3 条新行（1 条 VERBATIM
路径、1 条债务行、1 条豁免行）与 2 条改名。删去的 10 条：5 条 `PROSE` 路径、3 条债务行、
2 条改名的旧名。
skipped +2 是 `Need` / `QueryPart` 作为 `EnvelopeName` 在 #382 那条同一性闸口上的**故意跳过**。
mypy clean（140 个源文件），`pnpm build` 通过。

**方法论。**

- （317）**「A 已经带着 B，缺的只是把 C 分开」这类登记，要先量 A→B 的纤维有多大。** 纤维=1
  才是「已经带着」，纤维=10 意味着 B 是 A 的**像**，而像里没有原像的信息。判据一行就能跑：
  按 B 分组数 A 的成员数，最大那格 > 1，登记里的「只是」就是假的。#434 用「映射要比源粗」
  论证**不该**加成员，这里用同一句话论证**必须**加一层——同一条判据，方向由「谁在充当谁」
  决定。
- （318）`**kwargs` 转发把两个本来无关的命名空间**焊在一起**：调用方写的槽名，和门自己的形
  参名。这不是可以靠「小心起名」躲过去的，因为槽名由句子决定、形参名由数据结构决定，两边都
  有各自的正当理由。结构性的解法是**把其中一个搬出那个命名空间**——`/` 搬形参、改模板搬槽名
  ——而搬哪一个要看谁在别处另有身份：另有身份的那个搬不动。
- （319）**判「这两条是不是同一件事」，要拿事实比，不能拿渲染串比。** 串相等在单语系统里恰好
  等价于事实相等，于是这个错误在加第二门语言之前**一次都不会暴露**；加了之后，同一件事在两
  种语言下变成两个串，去重就会按读者是谁给出不同的结果。凡是「去重 / 分组 / 缓存键」落在一个
  会被渲染的东西上，都要问一次它比的是哪一层。
- （320）**「要不要抽出来」这个问题，第二个用户到场的那一刻自动有了答案，而信号是 import
  语句读起来别扭。** 一套机器只有一个用户时，放在那个用户里和放在它自己的模块里区别不大，所
  以当时不抽是对的；错的是**第二个用户到场时照着第一个用户的名字去 import**。判据不用衡量代
  码量：念一遍那句 `from X import Y`，如果 X 是「第一个用它的东西」而不是「Y 是什么」，就该
  搬。这一刀里 `refusals` −236 行，而搬走的四件事没有一件提到过拒答。

### #434 拒答是结果的全部时，status 由捕到它的那只手决定（2026-08-23）

登记的说法是「θ 端把四种 kind 的 8 个物种都报成 `outside_language`，而状态词表没有
『你给的两个输入互相矛盾』这个成员」，并挂了一条待验根因：`status` 可能是 `kind` 的
第二份记录（#345 同型）。**两条都要更正，而更正它们的是同一张表。**

在内核出口 `refusals.stamp` 上插桩跑一遍全量——每个上信封的拒答都过这一处——得到 93 次
拒答、47 个不同组合、108 个物种里 33 个被真正走到：

```text
STATUS × KIND            data    graph  request  unbuilt
needs_investigation        15       16       35       10
outside_language            .        .        1        6
structurally_solved         5        .        2        .
```

**更正一：根因假设被这张表否掉。** 它不是对角的。`needs_investigation` 横跨四种 kind。
两个字段答的是不同问题：kind 说「这是谁的局限」，status 说「这次查询的结局」。

**更正二：`structurally_solved` 那一行说出了缺陷的边界。** 那些结果同时带着识别层的
答案，它们的 status 说的是**那个答案**，不是拒答。数据端 24 个 `record` 点全在这一类
里——它们返回 `blocked(...)`，status 由调度器按结果里**还有什么**来定。**数据端没有这个
缺陷**，登记时以为有。

**根因：只有当拒答是结果的全部内容时，才需要有人替它命名一个 status——而命名它的是
「谁捕到了它」。** `scheduler.py` 三个这样的决策点，每个自己写死一个；而
`except CounterfactualBoundsError` 捕的是一个**族**，族里 9 个物种横跨 4 种 kind，两个
handler 写下的 `outside_language` 对其中 1 个成立。数据没毛病、只是两个输入互相矛盾的
读者，被告知「这个问题超出 Themis 可表达的范围」。

**修法：`Kind` 多声明一件事——`outcome`**：这个 kind 的拒答成为结果的全部时，查询的结局
是什么。五个成员各声明一次，`refusals.outcome(failure)` 是那一次查表，
`scheduler._refused()` 是唯一读它的地方。

**这张映射刻意比 kind 粗**，而这正是它不会变成 kind 第二份记录的原因——也是**没有**给
`request` 加一个 `ResultStatus` 成员的原因：一个 kind 一个 status 就是单射，单射就是复制。
读者要分「补数据」还是「改输入」，读的是 `kind`，那本来就是回答这个问题的字段。

- `unbuilt` → `outside_language`。唯一的一个，而且这正是那个状态一直在对读者说的话：
  「不是数据不够，是问题的形式本身还没有对应的表示」。
- `graph` / `data` / `request` → `needs_investigation`。**取舍，明说**：status 分不出这
  三者，分得出的是 kind。
- `backend` → `needs_investigation`。七个成员里最不错的那个，不是合适的那个；而且今天零
  producer——全量跑一遍没有一个 backend 拒答到达内核出口。第一个真正到达的那天，就是重估
  这一行的那天。

**顺带修掉一个同族的、两行之隔的。** `CounterfactualInfeasible` 有自己的 handler，把整个
拒答**扔掉**，重编码成一条 `MissingItem`，`reason=str(exc)`。而 #433 之后 `str(exc)` 就是
`SAYS` 那句话在 `language.DEFAULT` 下渲染出来的结果——**#411 刚从信封上拿掉的东西，换个
字段又上来了**。删掉那个 handler，让它走本族那扇门：status 不变（kind=`request`），变的是
它以拒答的身份到达读者。

**闸口按形状说不，不按名单说不**：一个 `QueryResult` 只带 `estimator_failure`、不带任何
答案或缺口字段，就不许自己写 `status=ResultStatus.X`。在改前的 HEAD 上验过它确实说「不」，
且点名的正是那三处（2212 / 2343 / 2958）——**反例是既有代码，不是造出来的**。

基线：7009 → **7020 passed / 169 skipped**（收集数 7178 → 7189，+11，全在新闸口文件：映射
的三条性质、五个物种各一条结局、未登记物种被拒一条、按形状的闸口一条、分母不许归零一条）。
mypy clean（139 个源文件）。

**方法论。**

- （314）一个「同一件事有几种说法」的普查，插桩要插在**出口**，不在构造点。第一版钩的是
  `QueryResult.__init__`，只看到 3/108 个物种——数据端的拒答写进的是 dict 而不是那个
  dataclass。改钩 `refusals.stamp`（每个上信封的拒答都必经的那一处）之后是 33 个。判据很
  便宜：问「这条路上有没有一处是所有分支都必须经过的」，有就钩那里；钩构造点等于**只钩了
  其中一扇门**，而这份文档里已经有一整刀是关于门有几扇的。
- （315）交叉表里的**满格子和空格子一样能说话**，而最要紧的那个常常是「看起来不该有却有」
  的那个。`structurally_solved × 拒答` 不是噪音，它是缺陷的**边界**：那些结果的 status 说
  的是别的东西。于是修法必须带一个「只当拒答是全部内容时」的限定；不带限定的修法会把 24
  个本来正确的点改错。
- （316）给一个封闭词表加成员之前，先问**加完之后这个字段和旁边那个字段是不是同一个划
  分**。「给 request 一个自己的 status」听起来是补全，实际会让 status 在这类结果上成为
  kind 的单射像——那正是 #345 拆掉的东西。判据是**映射要比源粗**：几个成员共享一个像，才
  是这两个字段在答不同问题的证据。

### #411 档3收口：信封上那句话是一次渲染，而渲染要知道语言（2026-08-23）

第十二刀之后，「谁在写句子」已经收敛成一个作者：每个抛出点交出一个物种和一次场合，
`SAYS` 里的模板在**一处**被填。但那一处在 kernel 里面。

`reason` 是**一次渲染的产物**——在拒答发生的那一刻、用 `language.DEFAULT` 填好的一句
中文，然后写进信封发出去。于是「读者用哪种语言」这个问题在 kernel 内部被回答了，而
kernel 契约说渲染层是**可剥离**的弱消费者。一个可剥离的层的产物，不该是不可剥离的那
一层的输出字段。

**上一档为这一档定的解法被实测推翻。** 登记时写的是「`reason` 改成一个 `Words`（每种
语言各一句）」，理由是浏览器没有 `describe()`、填不了槽。动手前按判据 (61) 重量了一遍：
`_slot` 只有**一个**依赖语言的分支——`isinstance(value, language.Word)`；其余全部走
`describe()`，而 `describe()` 的输出是符号，与语言无关。真正被词填的槽只有 **3 个**
（`role` / `design` / `refuted_by`，共 12 个抛出点），涉及 **10 / 108** 个物种。

分割线不在「语言」上，在「**值 / 词**」上。于是原本登记的方案——**信封带事实、读者面
组句**——不但可行，而且严格更好：让信封每种语言各带一句，是把渲染层的产物多印几份，
不是把它移走。

**信封改带两个字段，两个都是事实**：`said`（已经变成符号的值槽——列名、层数、样本量，
语言无关）与 `words`（`{槽名: {vocabulary, token}}`——一个**词**，不是一个串）。`reason`
删除。句子在读者面组装：Python 侧 `refusals.said(failure, lang)`，浏览器侧
`refusalSaid(failure, lang)`。

**`language.VOCABULARIES` 是让 `words` 只需装两个字符串的那件东西。**
`Word.__init_subclass__(vocabulary=...)` 在定义时登记自己，读者面用
`language.spoken(vocabulary, token, lang)` 按名字查回那张表。信封上因此没有类、没有语言，
只有「哪张表」和「表里哪一行」——这正是浏览器读得动的形状。

**分割在抛出点做，不在信封上做。** `_spoken(details)` 跑在 `_occasion()` 压平之前：压平
之后一个词只剩一个裸 token，「它曾经是个词」这件事已经没了。所以 `relayed()` 直接组装
`_envelope`，不再经过 `block()`——两个组装者**并排**，而不是一个套一个。转发者的计数因
此 2 → **1**：`relayed` 不再是门的使用者，它自己就是那个归档动作。

**空槽有自己的说法。** 识别层没有异常可抛，`block()` 常常一个 `details` 都不带；这时每
个洞用**它自己的名字**说出来（`` `column` ``），两个读者面同一条规则。

**一条闸口换了位置。** `block()` 原来是靠调用 `sentence()` 才会对「没有句子的物种」炸；
它现在不组句了，那个保证会**静默消失**——改成显式的 `str(species) not in SAYS` 检查。

**浏览器多了 6 张构建期生成的表**（走 #399 那条路，签入 `kernelWords.generated.ts`）：
`refusal_sentence`（108 句拒答模板）+ 5 张词表（`query_role` / `monotonicity_refutation` /
`recovery_mechanism` / `singular_matrix` / `outcome_error_premise`）。浏览器现在**填模板**，
而不是收一句填好的话。

基线：6997 → **7009 passed / 169 skipped**（收集数 7166 → 7178，+12）。逐条：6 张新生成表
× `test_web_vocabularies` 的两条逐表闸口 = **+12**；`test_a_refusal_reaches_the_envelope_one_way`
两条改名（+2 −2，净 0）。mypy clean（139 个源文件），`pnpm build` 通过。

**方法论。**

- （311）信封上的一个字段值不值得怀疑，判据是**问它是谁的产物**：产生它的那一步如果需要
  知道语言、需要知道读者是谁、需要一个 `DEFAULT`，它就是**一次渲染**，而渲染属于可剥离的
  那一层。「不把渲染好的文字塞进信封」这条规则本身早就写在这份文档里，一直缺的是**认出
  违反**的判据——一个 `lang=DEFAULT` 默认参数出现在 kernel 内部，就是那个信号。
- （312）**上一档为下一档定的解法，动手前必须再量一次。** 这里登记的是「整句变成
  `Words`」，实测是「依赖语言的只有一个分支、3 个槽、10/108 个物种」，直接推翻了它——被
  登记的那个理由（「浏览器没有 `describe`」）在今天的代码上不成立。登记条目是一条**待验证
  的断言**，不是一份施工图；不重量就照做，是把当时的认知当成事实执行。
- （313）把一个结构切成两半的时候，切点必须落在**信息还在**的地方。词和串在 `_occasion()`
  之后长得完全一样，所以分割只能在抛出点做；这条约束反过来决定了 `relayed()` 不能再经过
  `block()`——它决定的是**代码形状**，不只是执行顺序。

### #433 第十二刀：闸口按名字认门，于是子类是它的盲区（2026-08-23）

第十一刀之后，「还有几个抛出点自己写句子」这个计数是 **0**，「还有几条句子没人能说」
是 **1**。两个数都是真的，而它们的**分母**读的是**调用处的名字**——
`DOORS = {"EstimatorFailure", "IdentificationFailure", "block"}`。

于是两个用「抛一个子类」来归档拒答的族，**从来不在任何一个计数的分母里**：

- `themis/runtime/counterfactual.py` 的 `CounterfactualBoundsError` 族——**14 个抛出点，
  14 个全部自写英文散文**（13 处在求解器里，1 处在 `runtime/scheduler.py`）；
- `themis/estimation/iv.py` 的 `_NotStratifiable`——6 个抛出点，其中 3 处自写。

**17 个自写点，明面上是 15 个。** 盲区里的量级和明面上的量级没有关系。同时有 **3 个物种
在 `SAYS` 里根本没有句子**（`conditioning_too_fine` / `counterfactual_cell_out_of_scope` /
`interventional_risk_not_identifiable`）——它们能到达读者，全靠这些看不见的抛出点自己
在写。

**根因假设：不是漏了两个类名，是闸口把「哪些调用是在归档拒答」写成了一份名单。**
子类是**同一扇门的另一个名字**，而名单永远追不上下一个人加的那个子类——`STILL_UNSPOKEN`
里那条 `rows_outside_the_strata` 的注释自己就写着「这是子类盲区，把扫描放宽到子类才是修
法，猜哪些局部名字是物种不是」，挂了一刀没人回来做。改法是让闸口**读 class 语句**：
`_doors()` 从三个种子名出发，按继承关系求传递闭包，顺带把子类**在自己类体里钉的物种**
一并读出来（子类的抛出点不写物种，因为没什么可写了——只读调用的扫描会把它们全报成
「转发者」）。

**转发者的计数等到了它的答案。** `FORWARDED = 5` 的注释挂着一句「转发者是转述第一作者
的句子、还是自己又写了一句，这个计数存在就是为了让这件事可见」。答案是：**五个全在写第
二句**，其中四个把反事实求解器的 `str(exc)` 原样交上信封。剩下 2 个是真转发。

**`EstimatorFailure` 不再有 `message`。** 这是这一刀的结构核心。把 `str(exc)` 从转发里
拿掉是不够的——那样，还在写句子的抛出点会**静默丢句**；从构造器里把这个参数删掉，这个
状态就根本不可表达。前提是先量：生产侧用它的抛出点是 **0**，且已经 0 了一刀半。相应地
新开 `refusals.relayed(estimator=, exc=)`——转发的唯一形状，**不传 reason**；`record()`
改成委托给它。

**`CounterfactualBoundsError` 从一个物种变成一族的门。** 它原来钉着
`counterfactual_cell_out_of_scope`：一个意思是「这个求解器不做的十件事之一」的名字，由
基类携带，于是**没有一个抛出点需要选**。它在 `SAYS` 里没有句子，也不可能有——十件事没有
一句话。现在 `species = None`，抛出点自己报；子类仍各钉一个（调用方按名字捕获它们并据此
行动）。`counterfactual_cell_out_of_scope` 删除，位置上留一段注释说明它为什么曾经在这儿。
`_NotStratifiable` 同理丢掉自己的 `__init__`，`reason` 改成读 `str(self)` 的 property。

**又一批「一个名字盖了几种修法」**（判据(298)）：

- `conditioning_too_fine` 盖了三件事、三种修法：切之前就知道样本太薄（限制是**样本**的）、
  单列超过每列枚举上限、条件集的**乘积**超过总层数上限（没有哪一列单独有错）。→ 拆成
  `strata_would_be_too_thin` / `conditioning_too_fine` / `too_many_strata`。
- `counterfactual_inputs_infeasible` 的定义写着「要么两个来源矛盾、要么单调性被推翻」，
  而它只有第二句。被告知「你的单调性被推翻了」而真相是两个数据来源互相矛盾的读者，会去
  丢掉一条从来不是问题的假设。→ 拆出 `inputs_contradict_by_consistency`。
- `probabilities_do_not_sum` 旁边加 `not_a_probability`：和为 1 而有个负格，与每格都在
  [0,1] 而和是 1.4，**错在不同的地方**。
- 新词表 `Refutation`（`RESPONSE_TYPE_POLYTOPE` / `CELL_FEASIBLE_SET`）：两条路都到「你的
  单调性被数据推翻了」，**结论和该做的事都一样，差的是证据**——所以是一个词，不是第二个
  物种（走第十一刀 `Recovery` 那条路，判据(296)）。

**一处行为改变，明说。** 一致性矛盾那一支原来报 `needs_investigation` 加一条
`MISSING_ASSUMPTION` 缺口；现在报 `outside_language` 加拒答块。理由有两条：它的七个 θ 端
兄弟都这样报；而**这里没有任何一条假设需要改**——报成「缺一条假设」是把两个数据来源之间
的矛盾算到了用户的假设头上。测试跟着改，理由写进 docstring。

**顺带：一条分母归零的闸口，换成一条钉构造的。** `test_refusal_prose` 有两条 AST 扫描
（「说了有几个就不许再把它们印出来」「不许在 f-string 里现造一个集合」），它们读的是抛出点
自己写的句子——这一刀之后**没有句子可读了**。留着它会长期显示绿色而什么都没看。它们守的
性质今天由构造保证：每个槽位都要过 `_slot` → `describe`，抛出点**退不出去**。所以换成一条
直接钉这件事的测试，并把「原来是两条扫描、为什么不再是」写在它的 docstring 里。

物种 105 → **108**（+4 −1），`SAYS` 102 → **108**——**每一个物种都有句子，`STILL_UNSPOKEN`
空了**。这比看上去强：读者表里的每一句都有一个抛出点能产出它，所以一句话跟它的抛出点漂开
的时候，是有测试在看的。

基线：6979 → **6997 passed / 169 skipped**（收集数 7147 → 7166，+19）。逐条：物种 +3 带来
`test_a_refusal_says_one_thing_in_every_language` +6（两条逐物种闸口各 +3）与
`test_refusals_registry` +3；新词表 `Refutation` 带来 `test_a_word_reaches_the_reader_as_a_word`
+6、`test_a_vocabulary_prints_as_the_word_it_is` +3（其中一行按 #382 跳过，168 →
**169 skipped**）、`test_vocabulary_reach` +3，以及
`test_a_vocabulary_that_gives_up_identity_is_not_asked_for_it` /
`test_the_language_is_a_parameter_not_a_name` 各 +1；英文债表少两行（`iv.py` 3→0、
`estimation/counterfactual_cell.py` 1→0）→ `test_no_sentence_reaches_the_reader_in_the_wrong_language`
−2；`test_refusal_prose` −2（两条 AST 扫描换成一条钉构造的）。mypy clean（139 个源文件）。

**方法论。**

- （307）一个「谁在做 X」的计数器，如果它靠**调用处的名字**认门，**子类就是它的系统性
  盲区**，而盲区里的量级和明面上的量级没有任何关系（这里是 17 对 15）。判据很便宜：闸口
  的分母是不是一份**名单**？是名单，就问「下一个人加一个的时候，谁会红」。修法是让闸口
  **读结构**（class 语句 + 继承闭包），不是把名单加长——加长是把同一个缺陷推给下一个人。
- （308）计数器上写着「这件事我先计数、不判断」的那个数，**必须有人回来把它判掉**。
  `FORWARDED = 5` 的注释挂了两刀等到的答案是「五个全是第二作者」。一个没有回头动作的
  「留待观察」计数，就只是一个被登记过、然后被忘掉的缺陷。
- （309）要让一个「可选的坏用法」消失，**从消费端拿掉它是不够的**：消费端不再读，写它的
  那一侧会**静默地丢东西**。要么消费端保留，要么**从构造器里把这个参数删掉**，让那个状态
  不可表达。选后者的前提是先量出使用者是零——不是估计是零。
- （310）被这一刀清空了分母的闸口不要留着，它会长期显示绿色而什么都没看。两条出路：它守
  的性质如果已经**由构造保证**，就换成直接钉那个构造的测试；如果只是换了主体，就换主体。
  两条都要把「它原来读的是什么、为什么不再读」写在新测试旁边——否则下一个人会以为这条规则
  从来没存在过。

### #399 浏览器的 20 张词表改由 kernel 在构建期写（2026-08-23）

浏览器有 20 张表是 kernel 词表的**逐字复述**——同一批成员、同一批词，用 TypeScript
再打一遍。#317 量出八张里两张已漂，#394 量出三张只钉了键集、词已经不一样（`c_factor`
少一个「分解」、括号一半全角一半半角）。两次都修了，修法都是**再加一条闸口**：从测试
里那份 `glossed_by` 登记走到 kernel 的词，跟手写的那份比。

**根因假设：闸口比对的是两份手写，所以它永远比复述晚一步。** 一张新表得先有人打字，
闸口才追得上；第二语言一来，要打的字直接翻倍（20 张表 × 127 个成员 × 2 种语言 =
**254 对**）。而漂移只是症状——真问题是**浏览器拿不到 kernel 的词**：它不能 import
Python，所以「复述」是这条边界上唯一能走的路。#393 问的就是这个（「该不该改成由 kernel
供给」），答案是该；这一刀是做。

**做法：构建期生成 + 签入。** `themis/output/reader_words.py`（474 行）拥有注册表
`GLOSSED`——33 条，20 条是浏览器复述的表（记着它在浏览器叫什么名字），13 条只有 gloss
（kernel 自己用，浏览器没有对应表）。每条说三件事：这个词表的词从哪个点位取
（`themis/schemas/query_result.schema.json` 的 enum 是成员的分母，`Words` 是词）、怎么
枚举它的成员、浏览器那张表叫什么。`python -m themis.output.reader_words` 写出
`themis/web/frontend/src/lib/kernelWords.generated.ts`（582 行，20 张
`Record<string, Words>`），`verdict.ts` 里那 20 个字面量换成一行 `const X = generated.X`
——3600 → **3083 行**（+25 / −542）。

**登记搬出了测试套件。** 那 32 条 `glossed_by` 原来住在
`tests/test_vocabulary_reach.py::VOCABULARIES`。**只要问题是「有没有 gloss」，登记住在
测试里是对的**；现在包里有东西要**回答**同一个问题（生成器必须知道每张表的词从哪儿取），
它就必须住在包里，测试反过来从包里读——否则生产代码会照着测试再写一份登记，而那份和
这份不会自动相等。`VOCABULARIES` 现在是 `_ROWS` 与 `reader_words.GLOSSED` 的合成，搬的
时候 32 条路径逐条对过，零分歧。

**两条闸口，各挡一件事。** ①`test_the_checked_in_copy_is_what_the_kernel_writes_today`：
签入的文件必须逐字等于今天生成的。改 kernel 的词、加一个成员、加一种语言，下一次跑测试
就红，修法是跑一次生成器——254 对成员-语言词从此不再有人维护。②
`test_a_restated_table_is_written_by_the_kernel_and_not_by_hand`：被生成的表名不许再出现
在手写文件里。缺①会漂，缺②会有人把一张表复制回 `verdict.ts`，两份又活过来。

**手写的那份判断，得跟词一起生成。** 逐字生成第一次跑出来的差别只有一处：kernel 有 4 条
词带 markdown 强调（`outcome_error_design` 的前门与工具两行，各两种语言），而浏览器**不
渲染 markdown**——手抄的表里那 4 处星号是当初打字的人替掉的，一条**没写下来的规则**。
逐字生成会把它变成读者眼前的字面星号，所以生成器里有 `_without_emphasis`，并且把理由写在
它旁边。除此之外，20 张表的成员集与 254 对词与 HEAD 上手写的那份**逐条相同**——这一刀
不改任何一个读者看到的字。

**顺带。** ①`Wrote` 多一个成员 `SOURCE`：英文债探测器把生成器的文件头横幅报成了债，而
那是写给**读源码的人**看的，不是渲染给读者的句子——第五个类别，不是一条豁免。②有四个
测试模块各自去 `verdict.ts` 里捞表，其中几张已经搬进生成文件；`web_source.vocabularies()`
把「浏览器答读者用的所有表」合成一份文本，谁在问一张**表**就读它，只有「这张表归谁写」
这个问题才把两个文件分开读。

基线：6974 → **6979 passed / 168 skipped**。+5 逐条：2 条是上面那两道新闸口；另外 3 条是
既有元闸口的参数化各多一行——两条按模块（`reader_words.py` 是新模块），一条按允许项
（`ALLOWED_SLOTS` 多了 `_HEADER` 那条）。mypy clean（139 个源文件），`pnpm build` 通过。

**方法论。**

- （304）一份复述如果只能靠「两份手写互相比对」来钉，闸口就**永远比复述晚一步**：新的
  一张要先有人打字，它才追得上。这时根因通常不是「漏了闸口」，是**被复述的一方拿不到
  源**（跨语言、跨进程、跨构建）。答案不是再加一条比对，是**在构建期把源写出来并签入**，
  让闸口退化成「签入的等于今天写的」——这一条不随复述量增长。
- （305）一份登记住在测试里，只要它的用途是「问有没有」，就是对的。**当包里出现一个需要
  「回答」同一个问题的东西时，登记必须搬进包**，测试反过来从包里读；否则生产侧会照着测试
  再写一份，而两份不会自动相等。判据不是「谁先写的」，是**有没有人要用它去产出东西**。
- （306）生成一份复述，要连**打字的人做过的判断**一起生成。手抄的表里每一处「跟源不完全
  一样」的地方，要么是漂移，要么是一条没写下来的规则；逐字生成会把后者变成缺陷。所以搬之
  前必须逐字比一遍，把差别一条条判成这两类中的哪一类——判成规则的，写进生成器并把理由留在
  规则旁边。

### #405 第十一刀：名字是为第一个遇到它的抛出点写的（2026-08-23）

第十刀之后剩 15 个自写句子，分在 7 个物种上。它们跟测量误差族**正好相反**：没有
一个是调用方给的参数，每一个都是「这张图 / 这份样本 / 这个求解器够不够得着」的判
断。密度也不再集中——iv 6 处，其余六个物种加起来 9 处。

**根因假设：这些名字都是为「第一个遇到它的抛出点」写的，第二个抛出点站在别处。**
不是名字分错了维度（第八刀），也不是从来没写过句子（第九刀），更不是一个参数有多
种错法（第十刀）。是**同一个名字被证据强度不同、或信息量不同的两个门用了**：

- `do_risk_not_identifiable` 的定义是「没有后门调整集」。`binary_do_risk` 只跑了后门，
  这句话对它成立；`causation` 跑完了后门 / general-ID / 工具三条路的级联，它建立的是
  **更强**的命题。让强门说弱话，读者会去找一个已经试过的工具变量。→ 分出
  `do_risk_not_identifiable_by_any_route`。
- `iv_model_refuted` 的定义引用工具变量不等式。二值以外这条不等式**不一定充分**，所
  以 LP 不可行而不等式没被违反是可能的——这时按「被不等式否掉」报，等于给出一条不存
  在的引文。→ 分出 `iv_model_infeasible`（同一个结论，弱一级的证据，读者的下一步不同）。
- `continuous_mediator` 的定义写着「连续**或**层数太多」——又一个 "or"（判据(298)）。
  三个分数取值就是三个，「超过上限」对它是假话。→ 分出 `mediator_not_discrete`。
- `not_recoverable` 的定义写着「在所声明的选择**或**缺失机制之下」。这两件事只差一个
  词和判它的那条判据，所以走(296)那条更便宜的路：**把词提成槽位**。新词表 `Recovery`
  两个成员，各自把机制和判据一并说出（Mohan-Pearl-Tian 的有序因子分解 /
  Bareinboim-Pearl 的选择后门）。
- `no_identifying_design` 在 outcome_error 那一行上被借去说了一件它不拥有的事：拆分是
  **围绕**设计取的，缺的是精度代价、不是点估计。原来的注释说「缺一个给抛出行加注的槽
  位」——**那不是缺一个槽位，是缺一个物种**。→ `no_design_to_split_around`，它和
  `requires_a_point_estimate` 是一对（一个有设计没估计，一个有估计的问题没设计）。

**`no_first_stage` 的六处：三件事实。** ①三处是「工具推不动处理」，各有各的统计量，
名字对；②一处是「把条件集投影掉之后工具本身没变异了」——2SLS 照样出数，那个数与工
具无关，这跟「工具太弱」要说的不是一件事 → `instrument_absorbed_by_conditioning`；
③两处在矩记录求解器里，而**那份记录只带数字、不带列名**。

第③点是这一刀里最值得记的：`test_a_refusal_says_one_thing_in_every_language` 的
`STILL_UNSPOKEN` 注释把它记成了「一个契约问题」——要不要为了句子往矩记录里塞列名。
答案是不要。矩记录是生产侧转写，验证器从它独立重算而从不 import 生产者，**它对数字
充分、对句子刻意不充分**。所以那两处换一个「只说记录知道的事」的名字
（`joint_first_stage_degenerate`：q 个工具合起来解释不了任何变异），不动契约。

**顺带两处。** ①`_residualise` 在没有条件集时只做中心化，于是「残差平方和为零」就是
工具在样本里是常数——不是「被条件集吸收」，归 `overlap_insufficient`（又一次(295)：
一个判据同时覆盖了两件事）。②`_instrumental_inequality_violation` 原来返回**一句英
文或 None**，那让它成了物种句子的第二作者；改成返回**见证本身**（哪一档、超出多少），
意义留在 `SAYS`。

**拆物种打断了一条按物种名写的守卫。** dispatch 里有一处**让渡**：outcome_error 那一行
借用前门估计量的 span 检查，检查报的是列的毛病，所以这一行必须把拒答原样交回去、不许
署自己的名——否则读者会拿着「结局误测拒答了」去查自己声明的 σ²_v。守卫写的是
`exc.failure_type == CONTINUOUS_MEDIATOR`。拆出 `mediator_not_discrete` 之后，另一半
静默地落到了 `record(estimator="outcome_measurement_error")`。**根因不是漏了一个名字，
是守卫问错了问题**——它要问的是「这个拒答是不是那个借来的检查抛的」，而物种名只是那
个问题在当时的一份枚举。改成：`_discrete_levels` 在自己旁边声明 `SPAN_OF_ONE_MEDIATOR`，
dispatch 问这个集合；再加一条源级闸口，断言这个集合**恰好**等于该函数能抛的物种。

**新闸口：一张表一个键只能有一行。** 这一刀新开了一节 SAYS，把 `no_first_stage` 写了
进去——而它三百行以上的地方已经有一行。Python 的字面量允许重复键、静默取后一条，
`SAYS` 的两道闸口问的都是「这个物种**有没有**句子」，而有两条就是有。被遮蔽的那条带
的是复数槽位 `{instruments}`（旧编排留下的），所以谁去改它都不会有任何反应。JSON 对象
同病（`json.load` 也取后一条）。→ `tests/test_a_table_has_one_row_per_key.py`：`themis/`
与 `tests/` 两棵树下，Python 映射字面量与 JSON 对象都不许一个键出现两次；只管映射不管
集合字面量，因为 `{0, 1, True, False, 0.0, 1.0}` 那种六种拼法写同两档是仓里的有意写法，
而集合元素没有值可以被遮蔽。

**数字。** 自写句子 15 → **0**。schema enum 99 → 105。英文债台账再删五行
（`binary_do_risk` / `causation` / `dose_response` / `frontdoor` / `response_polytope`），
`dispatch` 73→69、`iv` 9→3。`STILL_TWO_AUTHORS` 空了，`STILL_UNSPOKEN` 只剩子类盲点
那一条。

**`iv_model_infeasible` 的反例是手算得出的。** 新物种要有它该说「不」的那个例子，而这
个例子按定义不能靠不等式找到：|Z|=3、四分之三的单位在每个 z 下都是 (X=1,Y=1)，剩下四
分之一在 z=0 是 (1,0)、z=1 是 (0,1)、z=2 是 (0,0)。不等式在 x=0 上等于 1/2、在 x=1 上
**恰好等于 1**，一条都没违反；而 z=0 那列（P(X=1|z=0)=1）读的是全体的 Y(1) 响应，z=1
和 z=2 两列又对同一个四分之一的 Y(0) 提出相反的要求——所以多面体是空的，且没有任何具
名的不等式能指出来。测试里另附一条断言「这张表确实没违反不等式」，否则一个不等式检查
静默失灵的构建会照样通过。

**零不等于完。** 剩下的是 #411 的另一半：`reason` 仍然是这个 kernel 在拒答那一刻、
用一种语言写下的字符串。归零买到的是**只剩一个作者可搬**——每个抛出点交出的是物种
加这一次的事实，句子在一个地方装配。

基线：6939 → **6974 passed / 168 skipped**。+36 收集数逐条对得上：+11 是逐句参数化
（SAYS 91→102），+6 是逐物种参数化（99→105），+10 是新词表 `Recovery` 在五个词表闸口
文件上各自摊到的行（其中 1 条是 skip，故 +35 passed / +1 skipped），+6 是新闸口
`test_a_table_has_one_row_per_key`，+2 是 `iv_model_infeasible` 的反例与它的前提，
+2 是让渡集合的行为反例与源级闸口，−5 是英文债台账删掉的五行。

**方法论。**

- （299）一个物种的名字通常是为**第一个遇到它的抛出点**写的。第二个抛出点站在别处
  时，名字往往还在，只是它承诺的那句话在新位置上说不出来或说错了。触发信号不是「抛
  出点多」，是**同一个名字被证据强度不同的两个门用了**——跑完级联的门 vs 只跑一条路
  的门，有见证的不等式 vs 只有线性规划不可行。弱证据借强名字，读者会照着一条不存在
  的线索走。
- （300）**名字要配得上抛出它的那一层。** 一份记录可以「对数字充分、对句子刻意不充
  分」（矩记录之于验证器就是），在这种记录上拒答时，正确做法是换一个只说记录知道的
  事的名字，而不是往记录里加字段去迁就一句话。把句子的需要倒灌进数据契约，是让读者
  面反过来定义计算层。
- （301）「这一行有一件真话要补，而物种不拥有它」——**那不是缺一个给抛出行加注的槽
  位，是缺一个物种**。加槽位会让每一行都能在物种的句子后面接一句自己的，一个字段两
  个作者就此长回来。
- （302）**拆一个物种，先找按它的名字写的守卫。** 名字是一份枚举，而枚举会因为拆分
  在别处静默地少一项——`==` 那半边继续通过，另一半走进它本不该走的分支。修法不是把
  新名字补进 `if`：**把「这个拒答是谁的限制」这个问题交回抛它的那个检查**，让检查在
  自己旁边声明它能抛的那一组，再用一条源级闸口钉住「声明的那组恰好等于它真能抛的」。
- （303）**一张表一个键只能有一行，而两种记法都不会说。** Python 字面量与 JSON 对象
  都接受重复键并静默取后一条，重复在解析后就不存在了——所以「每一项都有值吗」「值的
  形状对吗」这类问它的闸口全部照样绿灯。**分节维护的大表**（按族分节、靠人记住哪一节）
  是它的高发地。规则只能写在**源文本**上，而且不能只盯着出事的那张表：同样维护方式的
  表全在同一个坑边上。

### #405 第十刀：声明出来的参数，错法比列多（2026-08-23）

第九刀之后还剩 39 个自写句子，其中 **24 个挤在测量误差这一族的四个模块里**
（`measurement` 13、`regression_calibration` 5、`bounds_numeric` 1、`outcome_error` 1，
外加它们在别处的抛出点）。这个集中不是巧合。

**根因假设：这一族的参数是「声明」出来的，不是从数据里读出来的。** 暴露有哪两个
状态、哪个混淆矩阵配哪一层、误差方差多大——全部由调用方写下。一个声明能错的方式
比一列数据能错的方式多得多，而这些抛出点上方的名字是**按「哪个参数错了」分的**
（`differential_levels_mismatch` / `exposure_not_binary` / `non_positive_error_variance`），
**不是按「它怎么错了」分的**。于是同一个名字下面躺着两三件事实，每件事实只好自己
写一句话。

**判据：给这个物种写一句话，会不会在它某个抛出点上变成假话。** 四个「会」，四个新
物种：

- `differential_levels_not_the_axis_levels`——两个矩阵配两个层级，**数对了、名错了**：
  给的层级不是这条轴真正取到的那些。原来的 `differential_levels_mismatch` 说的是
  「矩阵数和层级数对不上」，对这两处是假话，而读者的下一步也不同（补一个矩阵 vs
  按真实取值重新索引）。
- `differential_by_the_mismeasured_variable`——`differential_by` 指到了这条通道正在
  误测的那个变量。原来的 `differential_by_unknown` 说「它不是一个能承载差异的变量」，
  而暴露恰恰是这个校正一定会条件化的那一个；真正让它不合格的是相反的事实。
- `arm_order_unreadable`——`[1, 2]` 是两个不同状态，`exposure_not_binary`（「只建了
  二值」）对它是假话。缺的不是二值性，是**「哪个是对照臂」这件事这一对里没人说**，
  而混淆矩阵的列是按位置读的。
- `corrected_design_not_positive_definite`——逐列可靠度全为正、合起来仍不正定。代码
  自己的注释早就写着「逐列判据必要而不充分」，而抛出的是 `degenerate_reliability`，
  把读者打发去找一个并不存在的「那一列」。

**第五个是同一条判据在另一个模块的重演，由一个既有测试当场逮到。**
`non_positive_error_variance` 的定义写着「absent **or** not positive」——一个「或」就
是一个名字盖了两件事。`{"y": {}}` 这样的 spec 到达估计量时是 `None`，落进正性判据，
读者收到「你声明的方差不是正数」，然后去自己的调用里找那个数。新物种
`argument_not_given`（通用，不限这一族）：**没有东西到达，和「到达了但没通过判据」
不是一回事**；它下面每一条判据都没有可判的东西。两处抛出点（`outcome_error` 的 σ²_v、
`regression_calibration` 的 σ²_u）。

**顺带两处不是这一族的事实，归还给通用名字。** `differential_levels` 少于 2 个 →
`too_few_inputs`；同一个层级出现两次 → `duplicate_input`。这两件事任何参数都能犯，
`_prepare_differential` 只是恰好也会碰上。

**数字。** 自写句子 39 → 15。schema enum 94 → 99。英文债台账**再删四行**——
`bounds_numeric` / `measurement` / `outcome_error` / `regression_calibration` 这四个
模块里除了这些拒答句以外没有别的英文；其中 `measurement.py` 的 13 条是这张表上第二
大的一行。

**方法论。**

- （297）一族的自写句子特别密，先问**这一族的参数是从哪来的**。从数据里读出来的参
  数只能以数据的方式错；由调用方**声明**的参数能以声明的方式错，错法更多、也更需要
  按「怎么错的」而不是按「哪个参数」来命名。抛出点的密度是这件事的信号，不是懒惰的
  信号。
- （298）物种定义里出现 **"A or B"**，就是一个名字盖了两件事的自供状——
  `non_positive_error_variance` 的 "absent or not positive" 是这样，而这两件事的读者
  下一步完全不同（补一个数 vs 改一个数）。「没有东西到达」在任何判据链的最前面都该
  有自己的名字：它不是一个没通过判据的值。

基线：6921 → **6939 passed / 167 skipped**（+14 是逐句参数化、+5 是逐物种参数化，
−4 是英文债台账删掉的四行，+3 是三个新反例）。mypy clean（138 files）。

### #405 第九刀：这两个名字说对了事实，只是从来没有过句子（2026-08-23）

登记时说的是 `INSUFFICIENT_SUPPORT` 15 处、`OVERLAP_INSUFFICIENT` 13 处。按同一条判据
扫全量是 **29 个抛出点**，分在 16 个模块里。

**根因假设：和请求侧同源，但不是同一个病。** 请求侧那两个 catch-all 是**名字分错了
维度**（上一刀）。这两个不是——`insufficient_support` 说的是「识别公式求和的某一格没
有行」，`overlap_insufficient` 说的是「某一列在整个样本里没有对比」，两句话都准确，
物种表里的定义也早就把它们和 `no_within_stratum_contrast` 三者划得清清楚楚。它们在
`SAYS` 里**根本没有条目**。于是每个抛出点都要重新把这条已经写好的事实写一遍，唯一的
目的是**把这一次的格 / 这一次的列塞进去**——「哪一格」「哪一列」「公式在那儿要的是
哪一项」，物种按定义就说不出来。

**判据不同，处理也不同。** catch-all 看的是描述里有没有把说明权交出去；这一类看的是
`SAYS` 里有没有它。两者在抛出点上长得一模一样（都在自写散文），所以只按「自写句子
数」排序会把它们混成一堆。前者要**一批新名字**，后者要**一句带槽位的句子**。

**结构性改动。** 两个物种各得一句双语句子：`insufficient_support` 拿 `{cells}`（这一
次的格）和 `{quantity}`（公式在那儿要的那一项，用列名写、不带取值——`P(y | x, z)` /
`P(x, y | z)` / `P(w | z, x)`），`overlap_insufficient` 拿 `{column}` / `{role}` /
`{levels}`。把「要什么」和「在哪儿」拆成两个槽位，是为了不让同一件事在一句话里被写
两遍。

**只有真正是别的事实的才立新物种**，三个：`too_sparse_to_estimate`（行有、两臂有、就
是不到这个估计量自己的下限——dose-response 的稀疏分箱与稀疏采样点，加 IV 分层里过薄
的那一臂）、`no_complete_case_rows`（格里有行，而每一行都在恢复公式要读的列上缺值
——和空格不是一回事，这正是缺失图要绕开的那个事实）、`rows_outside_the_strata`（切出
来的层只放下了一部分样本；「一个层都没填上」是它 covered=0 的极端，原本是第二句话，
现在并成一支）。

**顺带三处，都是闸口或反例逼出来的。**
①`QueryRole` 加 `INSTRUMENT`：九个抛出点在列名旁边用英文散文写着 "treatment" /
"instrument"，它们手工拼的那张词表就是这一张，只是少一个成员。
②`no_within_stratum_contrast` 的定义里写死了 "one **treatment** arm"，而 IV 分层缺的
是**工具**的一臂。角色提成 `{column}` 槽位，四个抛出点各自填自己的列——比换物种（说
错）和加一个物种（重复）都便宜，句子还更准。
③`dose_response` 的 `K < 2`：采样点是**调用方给的**，却记成 DATA 物种，读者被打发去
补数据，而该改的是自己的请求。改成 `too_few_inputs`（kind=REQUEST）——#408 那条判据
（物种的 kind 是一句可能判错的断言）在支撑侧的又一个实例。

**一个下限判据同时覆盖了两件事。** IV 分层原本是 `n_high < 2 or n_low < 2` 一支，于
是「这一臂一行都没有」和「这一臂只有一行」拿到同一句话。前者收到的是「行是有的，只
是不够」——对 0 行是假话。现在零那一端归 `no_within_stratum_contrast`，薄那一端归
`too_sparse_to_estimate`，各带自己的反例测试。

**数字。** 自写句子 65 → 39。schema enum 91 → 94。英文债台账**删掉八行**——`aipw` /
`backdoor` / `four_way_ratio` / `general_id` / `longitudinal` / `missing_recovery` /
`proximal` / `selection` 这八个模块里除了这些拒答句以外没有别的英文，所以不是变少，
是没有了；另外八个模块共降 18 条，合计 29 条。

**方法论。**

- （294）「物种说错了」和「物种没说话」要分开。前者的证据在**描述**里（它把说明权交
  给了句子），后者的证据在 `SAYS` 里（它根本没有条目）。两者在抛出点上的表现完全一
  样，只按「自写句子数」排序会把它们并成一堆，然后用错药。
- （295）一个下限判据 `< k`（k>1）**同时覆盖了「零」和「少」**，而这两件事的句子必须
  不同——「行是有的，只是不够」对零行是假话。加下限的时候要连着问：零那一端有没有自
  己的名字。
- （296）物种定义里写死一个**角色**（"one treatment arm"），第二个角色来的时候只剩两
  条路：换物种（说错）或加一个物种（重复）。把角色提成槽位比两者都便宜，句子还更准
  ——通用化不是抽象化，是把本来就在句子里的那个词交给抛出点填。

基线：6917 → **6921 passed / 167 skipped**。mypy clean（138 files）。

### #405 第八刀：两个 catch-all 是按「谁的错」分的名字，被要求装「什么事实」（2026-08-23）

登记时说的是 `INVALID_INPUT` 24 个自写句子。同一条判据把 `INVALID_CONFUSION_MATRIX`
的 9 处也扫进来——两个名字加起来 33 个抛出点，各写各的话。

**根因假设：这两个名字是按「谁的错」分类的，不是按「什么事实」分类的。** 物种名承载
的是 `kind`（这算谁的局限：请求 / 数据 / 图 / 没建 / 后端），而句子要说的是**事实**
（哪个参数、哪条契约、给了什么）。一个按 A 维度分出来的名字，被要求承载 B 维度的内
容，必然一名多义——`invalid_input` 自己的描述就写着「a malformed request whose own
message says what was wrong」，等于明说「名字不说，句子说」。这不是表象：只要名字停
在 kind 那一层，每个抛出点就都得自己把事实写成散文，写得再好也还是 33 份各自为政的
散文。

**于是真正的缺口不是「33 个句子没地方放」，而是这些通用的输入契约违反从来没有被命名
过。** 33 处里反复出现的是同几件事：你给的选项不在闭集里、你给的东西少于必需的个
数、你给了重复、两份输入对不上、你给的结构不对、你给的不是数、这些概率不加到 1、这
个参数不属于这个设计 / 这个设计缺这个参数、这个模型要二值列、这个选项回答的是另一个
问题，加上混淆矩阵的五种失败（形状 / 非数值 / 非有限 / 不在 [0,1] / 列不归一）。每
一件都被重新描述过三到五遍。

**结构性改动：退休两个 catch-all，立 16 个具名 REQUEST 物种。** `unknown_option` /
`too_few_inputs` / `duplicate_input` / `inputs_disagree` / `malformed_argument` /
`argument_not_a_number` / `probabilities_do_not_sum` /
`option_answers_another_question` / `model_needs_binary` /
`argument_missing_for_design` / `argument_foreign_to_design` / `matrix_wrong_shape`
/ `matrix_not_numeric` / `matrix_not_finite` / `matrix_not_probabilities` /
`matrix_not_column_stochastic`。每个自带双语句子和具名槽位（`{option,given,known}`、
`{one,one_is,other,other_is}`、`{argument,shape,given}`……），抛出点只填这一次的名字
和数。落到 8 个模块 35 个抛出点：dispatch 2、frontdoor 1、joint 1、mediation 6、
iv 5、measurement 9、outcome_error 4、transport 7。schema enum 77 → 91（退 2 进
16），测试钉死 enum ≡ 登记表。

**顺带出来的第二个词表。** `outcome_error.py` 里 `_WHAT_IT_IS` 是三段英文散文，讲的
是三种设计各自要哪个前提；它现在是 `Premise(language.Word)` 三个成员
（`INSTRUMENTS` / `TREATMENT_COEFFICIENT` / `MEDIATORS`），双语，进
`test_vocabulary_reach` 登记，作为槽位值随 `details` 走信封。这是 #410（槽位能装
「词」）第一次被别的刀直接用上——不立那个机制，这三段散文只能原地翻译。

**闸口逼出来的一条写法。** `test_no_refusal_slot_is_handed_a_word_spelled_out` 拦下
了 `what="mediators"` / `argument="treatment_coefficient"`：字面串跟词表成员的 token
撞了车。改成带尾等号的 `mediators=` / `treatment_coefficient=` / `instruments=` 之后
两者在字面上分开，而这个写法对读者也更准确——读者看到的是**要传的那个参数**，不是
一个概念。

**英文债台账真降 16 条**：dispatch 75→73、frontdoor 3→2、iv 16→13、measurement
20→16、outcome_error 7→1。跟 #432 那次不同，这次不是掉到判据线以下，是句子本身被换
成了物种的槽位。自写句子总数 99 → 65。skipped 166 → 167 也查了是哪一种：新词表
`Premise` 继承 `language.Word`，而 `Word` 继承 `EnvelopeName`，于是
`test_a_vocabulary_prints_as_the_word_it_is` 里那条「放弃同一性的词表交给 #382 管」
的跳过多了一项（16→17）——是登记生效，不是闸口被关掉。

**方法论。**

- （291）物种名与 `kind` 不是同一层：kind 是物种的**属性**，不是它的定义。一个名字如
  果只按 kind 那一维分，它就必然要靠句子去承载事实——catch-all 不是偷懒的结果，是这
  个错位的**稳定态**。看一个名字该不该拆，就看它的描述里有没有「message says what
  was wrong」这类**把说明权交出去**的话。
- （292）「没地方放」和「从来没被命名」要分开。前者缺的是**槽位**（#432 那一刀），后
  者缺的是**一批名字**。判据是：把 N 个抛出点的句子并排读，如果它们在**重新描述同一
  件事**，缺的就是那件事的名字；如果它们在说**各自不同的事**，缺的才是槽位。
- （293）关键字参数名和概念名共用一个字符串时，闸口分不出「一个词表成员被拼出来了」
  和「这是调用方要传的参数」。带上尾部 `=` 之后两者字面上分开——形式上的可区分和语义
  上的准确这次是同向的，不是为了迁就闸口而牺牲措辞。

基线：6871 → **6917 passed / 167 skipped**。mypy clean（138 files）。

### #432 「怎么办」有两个粒度，而信封只给了按物种的那个槽位（2026-08-23）

登记时说的是一处：`four_way_ratio.py` 用 `recorded={"use_instead":
"four_way_decomposition"}` 记下了「改用哪个」，而 `recorded` 是**句子不说的事实**
（#430 刚划的界），没有任何读者面会读它——这条出路对读者等于不存在。

**先把分母量出来。** 按同一条判据扫全仓自写拒答句：**16 条出路**散在 **14 个抛出
点 + 2 条物种句**里。形态几乎一样——事实陈述完，一个句号，然后一句祈使：`Supply
data with variation in {t!r}.`、`; use model='stratified_wald' ...`、`; set
differential_by to one of those`、`— use the confusion-matrix method
(misclassification=) instead`。其中 11 条是**英文散文粘在描述句尾**，于是它以「中
文报告里印一句英文」的形式到达了读者，且没有任何闸口管得着——语言闸口看的是「这条
串是不是单语」，而这条串本来就是单语英文债的一部分，早已登记在案。

**根因不是句子写得差，是缺槽位。** `kind`（5 个取值）回答的是**按物种**的「这算
谁的局限」，声明在物种旁边，一份。而「这一次怎么走出去」按物种答不了：
`overlap_insufficient` 有五个抛出点，四处的出路是「某一列得取到不止一个值」，第五
处是「换个能制造对比的设计」；`do_risk_not_identifiable` 三处同理。一句物种句装不
下五个答案，所以知道出路的抛出点只能自己写——它不是偷懒，是**没有别的地方可写**。

**结构性改动：出路是一个词加一个宾语，不是一句话。** `themis/refusals.py` 加
`Remedy`（6 个成员：补数据的变异 / 补某一层的数据 / 传某个参数 / 改某个参数的值 /
改用某个方法 / 换个设计），每个成员自带**各语言的模板**，至多一个 `{subject}`；宾
语是**这一次的名字**（一个列名、一个关键字参数、一个估计量），本身不属于任何语言。
成员是否带宾语由**成员**决定而不是由抛出点决定——抛出点漏给宾语，读者就会收到一个
带花括号的句子。信封上是 `estimator_failure.remedies`，每行 `{remedy, subject?}`，
两截都不带语言；句子在**知道读者语言的地方**拼装：主报告 `_routes_said`、浏览器
`remedyRoutes`。16 处抛出点的散文全部收回成纯描述。

**闸口，以及它对 HEAD 说的「不」。** `tests/test_a_route_past_a_refusal_is_a_word.py`
（32 项）四条规则：①一条出路在每种语言里**填同一个洞**（只有中文带
`{subject}` 的成员是两条出路穿一件衣服，而两边各自都渲染得好好的）；②模板除
`{subject}` 外没有别的洞；③抛出点用**成员**而不是字面串命名出路，且 6 个成员都有
抛出点能给出来；④**拒答句不对读者下指令**——两扇门的自写句子加 `SAYS` 全扫。反例
两条（一条把出路粘在描述后，一条用 `, or` 接第二条出路），另有一条反向反例（同样
的动词用来说**估计量**做了什么，不该被拦）。把④拿去跑 #431 那个提交的树：**14 个抛
出点全部被拒**，这才是它第一次真正说「不」。

**顺带两处。** ①`external_data_required` 与 `outcome_not_continuous` 两条**物种
句**里也写着出路（`Supply it as reference_data=`、`supply a validated confusion
matrix (misclassification=) instead`）——按物种确定的出路仍然是出路，留在句子里，
浏览器那一栏就会**恰好对最确定的那几种拒答是空的**；两条都收进了 `remedies`。②英
文债台账 `iv.py` 17→16、`mediation.py` 2→1，**不是**「少了两条英文」：剩下的
`estimate_iv_overid requires ≥ 2 instruments` 掉到了该模块「读起来像散文」的判据线
以下（4 个词 / 2 个虚词），英文还在，只是不再是一句对人说的话。数字降了，注释里写
清是哪一种。

**方法论。**

- （287）同一个问题有**两个粒度**时，只给一个槽位，知道得更细的那一层只能把它写进
  散文。缺的是槽位不是句子——把物种句写得再好，它也说不出另一个抛出点的出路。
- （288）一条自写句子里混了两件事（哪里错了 / 怎么办），任何闸口都分不开。分法不是
  措辞规则，是**先给第二件事一个自己的通道**；通道立起来之后，「句子里不许有它」才
  是一条能执行的规则，反例也才构造得出来。
- （289）词表的成员不一定是「词」，也可能是**带洞的句子**。这时「内核的说法」是模板
  本身，两个面**逐字比模板**比各自填完再比更强——填法也会漂，而模板比对连槽位名都
  钉住了。`outcome_error_design` 早就是这个形状，跟上它比新造一种便宜。
- （290）台账里的数字**降了也要问是哪一种降**。这次 2 条不是「债还了」，是剩下的英
  文掉到了判据线以下。一个用来量进度的数，记下一次并没发生的进度，比它不存在更糟。

基线：6829 → **6871 passed / 166 skipped**。mypy clean（138 files）。

### #431 一个形状被记了两遍，而复制是当时唯一不用审计任何东西的动作（2026-08-23）

登记时说的是一处：`kb_result.schema.json` 的 `$defs.kbQuery` 是 `kb_query.schema.json`
的第二份记录，且两份已经不相等（`given` 的 `default: []`、两条 description 只有一
份有）。证据是 #429 那一刀本身——它不得不同时改两份，改漏一份没有任何东西会说话。

**先把分母量出来。** 逐份比对十三份 schema 的规范化形状（去掉 description /
title / $id 这类只是措辞的键），得到的不是一处，是**六组逐字重复**，分布在三对文
档上：

| 记了两遍的形状 | 两处 |
| --- | --- |
| 值表达式 `constant` / `var_ref` / `sum_bind` | `derivation` ↔ `query_result` |
| 带 `kind` 的节点 `atom` / `graph` / `term` | `derivation` ↔ `verification_context` |

外加 14 个同名跨文档的名字，其中 11 个已经漂开。`kbQuery` 这一对**不在**六组里
——正因为它已经漂了，形状规则看不见它，抓到它的是名字规则。

**根因不是「谁手滑复制了一次」。** 跨文档 `$ref` 这个机制一直在，而且在生产里工
作：`themis/input/syntactic_validator.py::_load_registry` 把十三份全 glob 进一个
registry，103 处引用靠它解析。缺的不是机制，是**机制只有一个入口**。生产走
`validator_for`；其余地方要么手搓一个只装 1–2 份文档的 registry（测试里 7 处），
要么根本不给 registry（18 处）。于是「给某个形状加一条跨文档引用」从来不是局部改
动——作者得知道二十多个 validator 构造点里哪些会走到它；而**复制一份形状，什么都
不用审计**。六份逐字重复分布在三对文档、由不同时期的改动产生，是这个不对称的产
物，不是纪律问题。（`_load_registry` 自己的 docstring 早就记下过同型教训：列举改
成 glob。只有生产侧学到了。）

**两件事一起改，因为任何一件单独做都会烂回去：** 只立去重规则不立入口规则，下一
个作者照样退回复制；只立入口规则不去重，六份复制就一直躺在那里。

- `validator_for(schema_name)` 成为公开入口，是拿到「能解析全部文档的 validator」
  的唯一支持方式。`syntactic_validator` 的模块 docstring 同时改掉——它原本自称只
  管 kernel_ast，而它早就托管着 `validate_result` 和一个十三份的 registry。
- 七处重复改成一份记录加一条引用：`query_result` 的三个借 `derivation`（它本来就
  已经引用 derivation），`verification_context` 的三个同样，`kb_result.kbQuery` 借
  `kb_query`。文本外科手术而非重序列化——探针显示 `json.dumps(indent=2)` 会重写
  kernel_ast 约 917 行。删掉 128 行重复，加回 14 行。
- 15 个测试模块共 18 处裸 validator 与 7 处手搓 registry 全部改走 `validator_for`；
  两处验证「子树片段」的改用 `evolve()`，因为片段一旦被从文档里撬下来，就还带着引
  用却丢了解析它们的基址。顺带清掉 24 个因此没人再读的模块级常量。

**闸口（`tests/test_one_shape_has_one_record.py`，16 条）。** 两份文档不得记录同
一个形状；把局部 `$defs` 展开后仍不得（那是字面比较看不见的那种复制——
`derivation.value` 对 `verification_context.atom_value` 今天就是这个排布，只是两者
形状确实不同）；两份文档独立记录同一个名字时，要么其中一份是对另一份的引用，要么
在表里写清它们为什么是两回事（10 个名字，各带一句理由）；以及不得在共享 registry
之外构造 validator——**手搓一个 registry 也算**，它装的是作者当时想得到的那些文档，
明年新加的那条引用指向的正是他没想到的那份。

四条规则对 HEAD 全部说「不」：规则一 6 组、规则二 6 组、规则三 3 个（`graph` /
`kbquery` / `varref`）、规则四 18 处。规则三在写表时又逼出两个我自己的扫描漏掉的
名字（`term` / `query`）——我的扫描只走了带 `properties` 的 def，而这两个是 `oneOf`
联合。都是真不同：`atom` 的 `term` 是 const/var 两支的联合，`derivation` 的是一个
带 `type` 枚举的对象；两个 `query` 联合的成员集也不同（十支 vs 六支）。

**遍历要走多远，是问题的属性不是遍历的属性。** 改完之后 6 条既有闸口红了，同一个
根因：`schema_walk.resolve` **故意**不出文档，而现在三份文档的契约有一部分住在隔
壁，遍历到引用就断，分母缩水（`verification_context` 232 → 73）。但
`test_no_part_of_a_block_is_silent` 的模块 docstring 明写它**要**停在
`atom.schema.json`。两者都对，因为问的不是一个问题：问「这份载荷里有什么」必须跟
过去（借来的形状仍然在载荷里），问「这话该谁说」必须停住（形状归谁，答它的读者就
归谁）。所以 `cross` 成为 `walk` / `resolve` 的参数，两个闸口各自声明；跨文档解析
时把「落在哪份文档」一起带回来，否则那个形状自己的 `#/$defs/...` 会被拿到只是借用
它的文档里去查，查到别的东西或查不到，而两种情况都不出声。

**分母的对照组。** 重新基线后 `verification_context` 落在 **232 → 232**：三个形状
搬去一份记录，这份契约一个键都没少——这是「这次改动没从契约里拿走任何东西」的对照。
另外四份**涨了**：`kernel_ast` 157→399、`orientation_ledger_export` 24→105、
`orientation_session` 29→81、`query_result` 1775→2146。那些键一直是它们的，只是躲
在一条遍历当成「主题到此为止」的引用后面——#429 那条规则此前答的比它读起来答的要
少。新可见的键全部满足该规则，没有一处需要豁免。

顺带修掉两处同型的手搓解析：`test_formula_text._schema_node_kinds` 用
`ref.rsplit("/")[-1]` 自己解引用，遇到借来的形状就找不到 `properties`，会报出一份
比实际在用的更小的文法；`test_vocabulary_reach` 的 `kb_query_kind` 与 `term_type`
各自少掉一个站点——那正是被去掉的那份复制。

**方法论。**

- （282）一个机制「存在且在生产里工作」不等于「可用」。只要它只有一个入口，用它就
  不是局部改动，而绕开它（复制一份）不用审计任何东西。重复是这个不对称的产物；只
  删重复不修入口，等于把病灶留在原地。
- （283）闸口的分母取决于遍历走多远，而**走多远是问题的属性**。同一份遍历要同时服
  务「载荷里有什么」和「这话该谁说」，就必须把它做成参数并让每个闸口声明，而不是选
  一个默认值让另一个闸口悄悄失准。
- （284）一份**已经漂了**的重复，形状规则反而看不见——正因为它漂了。抓到 `kbQuery`
  的是名字规则。去重的闸口至少要有两条判据：形状相同，和名字相同而无人裁决。
- （285）把重复改成引用之后，被借出方的分母应当**回到原值**。verification_context
  的 232→232 是这次改动的对照组；如果它变小了，说明搬走的不只是重复。
- （286）登记条目给的是一个实例，不是缺口的大小——这条第 N 次成立：登记说 1 处，实
  际 6 处逐字重复 + 18 处裸 validator + 7 处手搓 registry。而这次连**我自己的普查
  也漏了**（只走带 `properties` 的 def，漏掉两个 `oneOf` 联合），是闸口在写表时把它
  逼出来的——普查会漏，闸口不会。

基线：6813 → **6829 passed / 165 skipped**。mypy clean（138 files）。

### #430 一次拒答的事实有两个受众，而它们共用一个名字（2026-08-23）

**现象**：33 处抛出点往 `details` 塞了一个键，而它所属物种的句子从来不说这个键。
`str.format` 对模板里没有洞的关键字**一声不吭地丢掉**，所以从来没有人发现——发现它靠的
是一次为这件事临时写的脚本。

**根因假设 → 根因**：`details` 命名的是**一个容器，不是一个受众**。它同时在做两件事：
**物种句子的实参**，和**这一次拒答在信封上的记录**。两个受众本来就都存在，缺的是第二个
名字——于是「物种故意不说的事实」（`unknown` 那 10 处的异常原文，是维护者的话）和
「句子本该说却漏掉的事实」在数据里长得一模一样。

**为什么是根因不是表象**：模块自己在**上一层**已经把这条线画出来了——`Refusal.says` 是
维护者的，`SAYS` 是读者的，两条 docstring 都明说；到了「这一次的事实」这一层，线没了。
而且两条 docstring 当场在打架：`record()` 说 details 是读者的（「读者只知道问题的形状、
不知道它的大小」），`four_way_ratio` 的作者在注释里写着「**它到达信封，不到达任何渲染
面，这是 `details` 其余部分本来就在做的交易**」。实测：**`details` 在内核和浏览器里零
读者**——它唯一的功能就是填句子。所以那 33 个键不是「忘了写进句子」，是**另一个受众的
东西挤在同一个名字下**。

**结构性修改**：给这一次的事实两个名字，和物种那一层同一条线。
- `details` = **句子说的**。闸口因此从**一个包含**变成**一个等式**（`holes == named`）：
  句子有洞而没给值，`str.format` 当场 KeyError，那一向是响的；**给了值而句子没有洞，
  以前是静音的**，现在是红的。
- `recorded` = **句子不说的**。信封上的兄弟字段，schema 里写清它是什么。

**33 个决定，全部落在 `recorded`，而这一条是量出来的不是选出来的**：每一个受影响的物种
都被 **2-7 个抛出点共用**（`missing_column` 7、`outcome_not_binary` 4、
`no_within_stratum_contrast` 3、`response_model_too_large` 2），而那个额外的键只有其中
一部分抛出点给得出来。给句子加一个洞，就会让同物种其余抛出点在 `str.format` 里炸掉——
**共用一句话的物种，说不出各家各自测的那个数**。所以没有一句句子被改写，这一点如实写在
这里：这一刀修的是通道，不是措辞。

三处测试因此要改一个字段名——它们同时也是证据：**这些事实本来就有消费者，只是不是读者**，
而这正是 `recorded` 现在明说的那件事。

**闸口第一次说「不」，是对 33 处既有抛出点说的**（(271)）。反例另外造了一条，并且**连
修好之后的写法也一起断言**——一个只会对错误形式说「不」的闸口，可能连正确形式也一起拒。

**登记（#431 / #432）**：`use_instead="four_way_decomposition"` 是「这一次该改用什么」，
它到不了任何读者面——物种句子说不了（4 个估计量共用，替代品各不同），`Refusal.kind`
（「怎么办」）是**按物种**的常量。移进 `recorded` 是诚实的归位，**不是解决**；真缺口是
per-occasion 的「改用哪个」没有一等通道，登记为 #432。

**方法论沉淀**：
- (279)**一个通道如果对「多出来的东西」是静音的，它就一定长出第二份职责**。判据：
  `str.format` / `dict.get` / `**kwargs` 这类**宽进**的接口，先问「多给了会怎样」——
  答案是「什么也不会发生」的话，它已经在同时服务两个用途了，只是你还没数过。
- (280)**同一条区分在上一层已经画好，下一层却没有，是最容易漏掉的重复**。判据：看到一个
  模块反复解释「A 是给谁的、B 是给谁的」，就去问它**每一层**是不是都有这两个名字；只有
  一层有的时候，另一层不是不需要，是把两样塞进了一个袋子。
- (281)**「一个物种一句话」和「每个抛出点各自测一个数」是会打架的，而输的一方是句子**。
  判据：想给共用物种的句子加一个洞之前，先数这个物种有几个抛出点、其中几个给得出这个
  值；给不出的那些会在 `format` 里炸——所以那个事实的归宿是记录，不是措辞。

基线：6810 → **6813 passed / 165 skipped**。mypy clean（138 files）。

### #429 一条关于「契约」的规则，实际上只管着十三份文档里的一份（2026-08-23）

**现象**：#371 定下「『没有』只能有一种拼法」——一个键**同时**可缺省且可为 null，两种
写法都合法、都表示同一件事，而没有任何消费者能分开。规则写在文档层，跑起来却只跑
`query_result.schema.json` 一份。另外五份 shipped schema 里有 **19 条路径**落在被禁的
那个形状里，从来没被问过。

**根因假设 → 根因**：`tests/schema_walk.py` 里 `SCHEMA` 是**模块常量**，从
`query_result.schema.json` 读，而 `resolve()` 闭包在它上面。**「哪一份文档」不是走查的
参数，是这个模块的身份**——于是任何建在这次走查上的闸口，分母自动就是那一个文件。

**为什么是根因不是表象**：如果病是「有人忘了把另外六个文件名加进一张清单」，改法就是
把清单补齐。可**根本没有清单可补**：只有一个常量，而 `resolve` 连「我现在在哪份文档
里」都不知道——它跟不了另一份文档里的 `$ref`，因为它没有「另一份文档」这个概念。规则
不是被有意缩到 `query_result` 的，是走查只认得一份文档，规则跟着它一起被缩了。

**结构性修改**
1. 文档成为走查的参数：`Document(name, spec)` 自带 `resolve` / `walk`，闸口说自己要哪
   一份（块覆盖那条问的是结果契约，就明写 `RESULT`）。
2. **「有哪些文档」由目录 glob 回答**，不是抄一份清单——清单要靠加文档的人自己去编辑，
   而那正好等于说「他不编辑的时候，新文档就悄悄进了 build」。
3. glob 只负责**看见**，另配一张**逐文档可达键数下限表**负责**被回答**：新增一份 schema
   不入表就红。逐文档而不是一个总数，因为总数是两份文档能互相扶住的地板——一棵子树塌
   了、另一棵长了，和不变一样。

**19 条 = 12 个决定**（九条是 kb 的三个键经三条 `$ref` 路线各到达一次）。每个决定的依据
不是我的判断，是**生产者实际发出的拼法**：

- **11 个键**的写入点全是 `if x is not None: d[k] = x`——null 那支**从来没被产生过**，
  所以从声明的 type 里拿掉（可缺省 + 不可为 null：缺省即是「没有」）。
  `kb_query` 三个、`kb_result` 六个、`derivation.steps[].step_id`、
  `factual_target_known`（`kernel_ast` 与 `verification_context` 两份文档同一个键）。
- **1 个键反过来**：`verification_context.theta` **永远写**，没有时写 `null`——改成
  `required`（必填 + 可为 null：状态被说出口）。

两个方向是同一件事：**把生产者已经在用的那一种拼法写进契约**。所以这一刀行为零变化，
而这也正是它值得做的原因——没被检查的从来不是代码，是**代码和契约还对不对得上**。

**闸口第一次说「不」，是对 19 条既有路径说的**，不是对我造的反例（(271)）。反例另外造
了一条，且**故意造在结果契约以外的文档上**（`orientation_propagation` 的副本上加一个
可缺省又可为 null 的 `note`）：「规则在跑」和「规则在这里跑」是两个断言，而 #429 讲的
是第二个——走查只握着一份文档的那些年里，下面这条检查在其余每一份 schema 上都是靠
「根本没读」通过的。

**顺手撞见，登记为 #431**：`kb_result.schema.json` 的 `$defs.kbQuery` 是
`kb_query.schema.json` 的第二份记录，两份在 HEAD 上**已经不相等**（`given` 的
`default: []` 只有一份有，`kb_name` / `target` 的 description 只有一份有）。证据就是这一刀
自己——它不得不同时改两份，改漏一份没有任何东西会说话。不在这里修：那要先决定这个
build 允不允许跨文档 `$ref`，而 `schema_walk.resolve` 是**故意**不出文档的。

**方法论沉淀**：
- (276)**一条规则的适用范围，是它调用的那次遍历的适用范围**。判据：看到「所有 X 都要
  满足 P」这样的闸口，先别读 P，**先读它从哪里拿到 X 的全集**——全集是常量、是模块级
  加载、是某次运行的产物，规则就只有那么大；而写在 docstring 里的那句话仍然会读成全称。
- (277)**「谁在集合里」交给 glob，「谁被回答了」交给表，两件事不能合并**。只有 glob，
  新成员悄悄进分母、悄悄通过；只有表，新成员根本不被看见。判据：分母要能自动发现，
  但发现出来的每一个都得有人**登记过一句关于它的话**，缺一句就红。
- (278)**要把一个「两种拼法」的键收成一种，先去读生产者，不要去判断哪种更好看**。判据：
  两种拼法里通常只有一种真的被发出过，另一种是声明里的死支——按发出的那种收口，行为
  零变化；反过来则是在改行为，还伪装成整理契约。

基线：6796 → **6810 passed / 165 skipped**。mypy clean（138 files）。

### #428 一句「还能顺带定下」后面什么都没有——因为那个前提从来没人检查（2026-08-23）

**现象**：定向问题带一个 `guaranteed`——「不管你答哪边，这一答都能定下几条边」。
它的 docstring 写着「永远 ≥ 1，至少是被问的这条边自己」。一张五节点的图上它读出
**0**，于是散文渲染成 `……还能顺带定下 （）`：动词后面是个空列表。

**根因假设 → 根因**。表层是两个事实共用一条通道：一个方向的 cascade 为空，既可能是
「它什么都定不下」（不可能——边在自己的 cascade 里），也可能是「这个方向根本不可用」；
拿一个真 cascade 去交一个不可用的，得到空。但真正的根因在下面一层：

> `guaranteed ≥ 1` 不是实现细节，**是 Meek 完备性定理**——把一个 pattern 闭包到底，
> 剩下的每条无向边都是可翻转的，所以两个方向都不会不可用。这条定理有一个**前提**：
> 输入是某张 DAG 的 pattern。**没有任何东西检查这个前提。** 那张五节点图枚举 16 种
> 定向，与它声明的对撞集一致的 DAG **有 0 个**——系统却问了两个已经没有答案的问题。

**第一版是错的，写在这里因为它错得有代表性**。我先补的是「症状的对偶」：闭包加一步
无环性定向（一个方向成环 ⇒ 另一个被迫，R2 去掉长度限制），闭包后再扫「输入没声明的
无屏蔽对撞」。它**可靠但不完备**——同一批抽样里 **3 张不可实现的图静默通过**，而我
当时给它们编了一个共同形状（「全无向的无弦圈，且没有有向边挨着」），**两张反例挨着
有向边**。更糟的是它**不确定**：`U` 是字符串元组的 set，哈希逐进程随机化，无环性步骤
和 Meek 规则同轮争同一条边，谁先轮到谁署名——`PYTHONHASHSEED=0/9` 下合法 pattern 也
会署上 `acyclicity`，而验证器要逐条复核 `rule`。

**结构性修改**：那个前提是一个**可判定问题**，就该由一个**判定过程**回答，而不是由
「我注意到的那种症状」的检查器回答。**Dor & Tarjan 1992** 的一致扩展构造：反复取一个
节点 x，满足 (i) 没有出边、(ii) 每个无向邻居都与 x 的其余邻居相邻，把 x 的无向边全部
定向为指入，删掉 x。条件 (ii) 恰好是「这样定不会造出新的无屏蔽对撞」；他们的定理是
**贪心不需要回溯**——找不到这样的 x，就不存在一致扩展。

- 判定跑在**输入**上（不是闭包上：闭包自己会造出新对撞，那样等于把待判的东西当前提）。
- 判定跑在**最前面**：闭包的完备性、「剩下的边两个方向都活着」、由此建出的问题，全都
  写在这个答案是「是」的假设上。答案属于它该在的位置。
- 判定说「不是」时，**一条定向问题都不问**。定向问题的意思是「这两个方向哪个成立」；
  一张没有 DAG 实现的图上两个都不成立，该递给人的是冲突——放弃哪一样——而不是在两个
  都是假的东西之间挑一个。`guaranteed ≥ 1` 因此**由构造成立**：它的前提在上游被判定，
  判定失败时下游根本没有东西可以说错。
- **无环性那一步删掉了**，连同 `acyclicity` 这个 provenance 取值和它在两份 schema 里的
  枚举。它只在「现在会被判定拦下」的图上触发过，在那种图上多定几条边是噪声不是信息。
- 顺手修掉的不确定性：闭包与三份转写全部改成 `sorted(U)`，`_forces` 的邻居扫描也排序
  ——**它返回的见证会进信封的 `roots`，而验证器要复核它**。

**一次不可实现只报一条冲突**。那张图上五个节点里有四个当不成汇点，各有各的理由；但
定理说「换个顺序也走不到更远」，所以那是**同一件事的四个观察面**。报四条会让读者以为
有四个问题，还会暗示「把这四对里任意一对连上就好了」——**没有任何东西这么说**。所以
报一条，带上字典序最小的那个见证（`c` 处，`a` 与 `d` 不相邻），散文明说「这不是某一条
边的毛病，{c} 只是能看见它的一处」。

**验过的是判定，不是症状**（一次抽样 4589 张人手可画的图，逐张与穷举枚举对照）：
**误报 0、漏报 0**，988 张不可实现的全部报出、578 张输入本身成环的抛 `OrientationError`
（且都确属不可实现）、3023 张合法的全部静默；另一批 2722 张**从 DAG 读出的真 pattern**
上，判定**一次都没响**。闸口把这两个方向都写成断言——只断言「不误报」的话，第一版那个
漏 3 张的实现也照样过。

**新增守卫**（`tests/test_a_question_with_no_answer_is_not_a_question.py`，12 条）：穷举
oracle 自身的自洽、样本图确属「无 DAG 可实现」、两个方向对齐两个总体、`guaranteed ≥ 1`
在两个总体上都成立、散文不出现空列表、成环输入抛错、以及**手拼一份「在不可实现的图上
问定向问题」的产物交给验证器必须被拒**——那份产物的 `guaranteed` 写的是诚实的 1，所以
能抓住它的只能是图本身。

**声明的取舍**：`themis/estimation/orientation.py` 与 `orientation_questions.py` 的单语言
债各 +1（6→7、17→18）。新增的是第六个 `OrientationError`、note 上的一个从句、和第
11/12 条冲突散文——三者各自所在的族**整族只有一种语言**，让一个成员两语反而比整族齐
落后更难读；而这些散文按 #411 排着要整体离开 kernel，现在补的第二语言是会被推翻的活。

**方法论沉淀**：
- (272)**一个「可判定的前提」被写成不变量而没人检查时，补法是判定过程，不是症状检查**。
  判据：如果你补的检查**可靠但不完备**，你补的就是「我注意到的那种坏法」；先去查这个
  性质有没有**已知的判定算法**（这一条是 Dor-Tarjan 1992，多项式），有就用它，
  「完备」这件事随之由构造成立，而不是靠我抽样抽不出反例。
- (273)**残差是要被证伪的断言，不是脚注**。第一版我写下「漏 4 张，形状是 X」——重测
  是 3 张，其中两张不是 X。判据：一条「我们漏掉的是这些」的说明，和一条功能断言一样
  要被同一批数据钉住；钉不住就说明**分类是我编的**，那正是该换判定过程的信号。
- (274)**内核对同一份输入产出进程相关的东西，是缺陷，哪怕「结果」是稳定的**。集合的
  哈希序会决定**谁署名**：Meek 闭包在合法输入上是汇合的（最终定向集合相同），但两条
  规则争同一条边时的先后决定了 provenance 里的 `rule` 和 `roots`，而验证器逐条复核它们。
  判据：**凡是会进信封的东西，它的产生顺序就是规格的一部分**——迭代集合前先 `sorted`，
  两个方向的规则分层而不是同轮竞争。
- (275)**一个不可实现的证据有 N 个见证，不等于有 N 个问题**。判据：报之前先问「这 N 个
  能不能被分别解决」——不能的话它们是同一件事的 N 个观察面，报一条、给一个最具体的
  见证、并在句子里说清楚「这只是能看见它的一处」，否则读者会去逐条修，而每一条都修不动。

基线：6784 → **6796 passed / 165 skipped**。mypy clean（138 files）。

### #410 一个槽位只装得下数，装不下词——于是三个物种各有一堆作者（2026-08-23）

**现象**：三个物种的每一个产出点都自己写读者那句话——`singular_design` 7 处、
`singular_confusion_matrix` 5 处、`invalid_confusion_matrix` 9 处——而它们写出来的
那些句子**彼此只差一个词**：哪一个矩阵求不了逆，哪一条通道被误测。

**根因**：`details` 这条通道被设计成**只装数**（哪一层、多少行、行列式多大）。
拒答句子需要的第二类东西是**词**，而词和数在这条通道上没有区别——到了 `_slot`
只剩 `str(value)`，而**一个词的 `str` 是它的 token**（#386 之后就是值本身，本仓库
里长得像英文）。**把英文 token 插进中文句子**，正是句子表存在的理由所反对的那件
事，只是低了一层。于是「这一次是哪一个」只能由产出点自己写成散文——**而写了散文，
它就成了这个物种句子的又一个作者**。这不是「顺便还没做」：那三个物种是**做不了**。

**做法**：`language.Word`——成员自带各语言文本的封闭词表（`EnvelopeName` 子类，
**token 上信封，词进句子**）。`Word.said` 是类方法而不是取实例属性，因为**能从
信封上读回来的只有 token**；一个只能拿活成员来问的 gloss，结果的消费者一个都用
不了。`_slot` 见到 `Word` 就按读者语言渲染，其余分支不动。

两张词表：`Design`（6 个成员，**纯名词短语**——「奇异了会怎样」是句子的事不是词的
事，写进成员就成了后半句从前半句的洞里钻出来，两种语言下都读成一个永远等不到谓语
的主语）、`QueryRole`（暴露 / 结局 / 路径上协变量）。

**顺带修掉的两处假话**：

① `_validate_matrix(cm, k, *, label=None)` 的缺省分支**悄悄地就是「结局」**
（`noun = f"{label} states" if label else "outcome states"`），而**暴露侧的校正
从不传 label**——于是一个畸形的**暴露**混淆矩阵，被以**结局**的名义拒掉：
`confusion matrix must be 2×2 to match 2 outcome states`（已实测复现）。改成必填
参数，缺省分支消失，假话跟着消失。

② `singular_design` 的第 7 处根本不是那件事：**什么都没有奇异**——拟合是精确的，
û'û = 0，Sargan 统计量成了 0/0。拆成 `no_residual_variation`。

**拆开的另一个物种**：per-level 混淆矩阵不可逆 → `singular_confusion_matrix_in_stratum`。
**物种断言的是后果**：一张矩阵不可逆＝整个校正没有；**某一层**的矩阵不可逆＝
**只有那一层**没有。把后者说成前者，是告诉读者「校正拿不到」，而拿不到的只是它的
一个分层。同一刀里 `_prepare_differential` 的 `level_name: str` 换成 `axis: str`：
原来那是三段在调用点拼出来的英文散文（`"exposure arm"` / `"outcome value"` /
`f"covariate {axis!r}"`），流进四条拒答消息——**句子的一截长在了调用点上，只有一种
语言，而且说得比它自己拼出来的那个列名还少**。

**闸口第一次说「不」，不是对我造的反例说的**：`general_id.py` 六处把
`role="treatment"` / `role="outcome"` 当**字符串字面量**交给槽位，其中三处正好拼出
`QueryRole` 的 token。判据因此收紧成**绝对断言**：产出点交给槽位的字符串字面量，
不许是本 build 任何一个词表成员的拼写。（判据没有做成「同一个槽位有没有两种填法」
——那要假设槽名跨物种同义。**产出点上的字面量永远是作者的词，不是调用方的数据**：
一个叫 outcome 的列是作为值到达的，不是被人敲进源码的。）

**删掉的一份重复**：`data_gap_report` 私有的 `_ROLE_EXPOSURE` / `_ROLE_OUTCOME` /
`_ROLE_ON_PATH_COVARIATE`，和 `QueryRole` 是同一个事实的第二份记录——
`language.Words` 的注释自己写着「两份相隔的记录会漂」。并成一份，别再自己造一份。

**改名**：这张词表本来叫 `Role`，而 `themis.estimation.strategy.Role` 已经占了这个
名字。两个词表同名不只是读起来歧义——**#382 那条身份闸口按裸名解析词表**，于是它
当场开始把 `strategy.Role` 的 `is` 比较报成这张词表的。改叫 `QueryRole`。那条闸口
按裸名解析是它自己的弱点，本刀未动。

**守卫（新模块 36 条，含构造反例）**：①每个成员在每种语言下 `_slot` 给出的就是那种
语言的词；②token 在所有语言下不变，且**至少有一种语言的词不等于 token**——否则这个
成员什么都证明不了；③把同一个物种、同一个成员按老办法 `format(role=str(...))` 渲染
一遍，**英文 token 确实出现在中文句子里**，走 `sentence()` 则不出现（**闸口的失败态
必须造得出来**，不然没人见过它说不）；④全仓没有一处把词表成员拼成字符串字面量交给
槽位；⑤在 tmp_path 里造一个这么写的模块，判据必须抓到它，删掉那半边则必须放行；
⑥分母自己说话：**如果全仓没有任何一处把词交给槽位，④就会因为无物可看而通过**——
这跟 (268) 那种「只看得见一扇门的作者计数」是同一种失明，值一条断言。

**声明的取舍 / 未做**：`invalid_confusion_matrix` 的 9 处仍自写句子。它卡的不只是
词——`_validate_matrix` 里那 5 处是**五种不同的畸形**（不是数值数组 / 形状不对 /
有非有限值 / 不在 [0,1] / 不是列随机），那是**五个事实**而不是「一个事实 + 一个
词」，拆物种是 #405 的活。这一刀只把它需要的那个词补上（`label` 从可选英文串变成
必填的 `QueryRole`），句子留在原地。

**数**：自写句子的产出点 111 → **99**（12 处：7 处 singular_design /
no_residual_variation ＋ 5 处混淆矩阵）。六个模块的单语言债各降一档：
iv 20→17、measurement 25→20、outcome_error 9→7、regression_calibration 6→5、
joint 4→3、mediation 3→2。

**登记（#430）**：`details` 其实有两份职责——**物种句子的槽位**，和**这次拒答在
信封上的记录**。一个键属于后者而不属于前者时 `str.format` 静默忽略它，而现有闸口
只查一个方向（holes ⊆ given）。反方向实测 **33 处**：10 处是 `unknown` 的
`diagnostic`（那是**约定**：异常原文只上信封、不进读者的句子），其余像是读者本该
拿到却没拿到的事实（`no_within_stratum_contrast` 三个产出点各记各的
arm / share / n_treated，而句子只说 strata；`outcome_not_binary` 记了 `use_instead`
而句子不说「那改用哪个」）。

**方法论沉淀**：
- (269)**一条通道只支持一种「值」，就会把需要另一种的东西挡在门外，而挡住的样子不是
  「缺一个功能」，是「下游 N 处各写各的」**。判据：看到 N 处代码只差一个词或一个
  名字，先别急着合并，**先问它们共用的那条通道装不装得下那个词**——装不下的话，合
  并出来的东西还得把词硬塞回去，等于把 N 份重复换成一份带补丁的重复。
- (270)**「缺省分支悄悄地就是某个取值」＝那个取值被选在了没人看得见的地方**。
  `label=None` 读起来是「没有标签」，下游拼出来是「结局」，于是从不传标签的那条通道
  被以另一条通道的名义拒掉。判据：一个可选参数如果**它的缺省分支在下游拼出了一个
  具体的名词**，它就不是可选参数，是一个默认选择；改成必填，谎言就无处安放。
- (271)**一条新闸口第一次说「不」，最好不是对作者自己构造的反例说的**。判据：新判据
  跑完全量如果只有构造的反例见红，要么它太窄，要么全量还没扫——两者都得当场说出来
  ((61) 的另一面：登记条目给的是一个实例，而闸口给的是分母)。

基线：6728 → **6784 passed / 165 skipped**。mypy clean（138 files）。

### #405 一条闸口数的是「门看得见的作者」，而手拼的那扇门它看不见（2026-08-23）

**现象**：拒答块有两条纪律在盯。一条数「还有多少产出点自己写读者那句话」
（`STILL_AUTHORED = 109`）；另一条数「还有多少块是手拼字典而不是走
`refusals.block()`」（棘轮 `STILL_HAND_BUILT = 7`），并把它当成一队**待改名**。

**根因**：**这两条数的是同一件事的两面，而其中一条的分母正是另一条的盲区。**
数作者的那个函数按 `DOORS = {EstimatorFailure, IdentificationFailure, block}` 找
**调用点**——一个字典字面量不是调用点。那 7 处**每一处都写了自己的 `reason`**，
于是真实的作者数是 **116**，闸口读出来是 109；更要命的是，有 **5 个物种只以字典
字面量这一种形态到达信封**，在那条「谁写了这个物种的话」的闸口眼里，它们是
**0 个产出点的物种**——它们的措辞**从来没有进过那条为了审它而建的闸口**。

**为什么是根因不是表象**：棘轮把「手拼」读成工作量（一队改名），所以它可以一直
慢慢降；而每留一处，就有一处措辞在审判之外。缺陷正好落在那里：纵向拒答的
`estimator` 字段是**条件的**（`longitudinal_ipw_msm` / `longitudinal_gformula`），
而它的句子**不是**——两处都写「不被 g-formula 识别」「g-formula 的估计会有偏」。
**跑 ipw_msm 的那一半，被告知一个它没跑的方法会有偏。** 序贯可交换性是两种
g-method 都要的，哪一个跑了信封本来就写着。

**修法**：把「手拼」变成**不可表达**——7 处全部走 `block()`，棘轮常量删掉、换成
绝对断言并自带反例。于是作者计数的分母**自动变成全部**。7 处里 5 个是**单作者
物种**（不是「一个物种背了多个事实所以写不出一句话」，只是句子写在了抛出点而不是
物种旁边），它们的句子进 `SAYS`、槽位具名、两门语言同槽：
`not_identified`（顺带修掉那句假话）、`external_data_required`、
`differential_combined_misclassification_deferred`、
`mismeasured_covariate_not_in_adjustment`、`requires_a_point_estimate`。
`_outcome_error_has_no_beta` 这个专门产散文的辅助随之删掉。

同口径量：**116 → 111**，`STILL_AUTHORED` 从 109 涨到 111 是**分母变了**，
而不是有人开始自撰——常量的注释把这件事写死在那儿，否则下一个人会把它读成退步。

**明确不做的那一半**：`invalid_input`（25 个作者）与 `not_recoverable`（2 个作者、
而且是**两个事实**——缺失数据模式 vs 选择偏倚——顶着一个名字）仍在门口自撰。
它们是**一个物种背了多个事实**，给它们写一句话等于**拆物种**：schema 里那张
75 项的 `failure_type` enum（登记写的 70 已过时）+ 浏览器 `verdict.ts` 的副本 +
prompt。那是 #405 剩下的主体，区别是它现在**在计数之内**而不是在计数之下。

**闸口**（`tests/test_a_species_the_door_cannot_see_is_still_a_species.py`，11 条）
- **修正是活的**：同一个不可识别的策略效应，两种 g-method 各跑一次，`estimator`
  字段不同、`reason` **逐字相同**、且不出现任何方法名；被替换的那句原文誊在文件
  里，断言它不再是任何语言下的那句。
- **五个物种真的会说话**：各按**它自己产出点提供的 details** 填，两门语言都渲染
  得出、无残留 `{`；再走一次真正的门端到端。
- **两个分母现在是同一个**：就地写一份「按调用点数」和一份「按调用点+字典字面量
  数」的计数器，断言两者相等——这正是关掉第二扇门而不是把它数到零的意义。判据
  自带反例：就地种一个手拼字典，宽的那份找得到、窄的那份找不到。
- 另加：`test_a_refusal_reaches_the_envelope_one_way` 的棘轮换成绝对断言 + 反例。

**方法论沉淀**：
- (267)**两条闸口分别盯一件事的两面时，先问「其中一条的分母是不是另一条的盲区」**
  ——本轮不是谁写错了，是**一条闸口的读数只在另一条清零后才是它自称的那个数**。
  判据：一条计数型闸口如果按「形态」找样本（找调用点 / 找某种字面量），就要问**还
  有没有别的形态**；有，那这个数就不叫「有多少」，叫「**我看得见多少**」。这类闸
  口的注释必须自己说出这句限定，否则读数会被当成事实。
- (268)**「棘轮」这个形状会把「不可表达」误读成「待办」**——`STILL_HAND_BUILT`
  把第二扇门读成一队可以慢慢降的改名，于是它可以合理地一直不为零；而**只要它不为
  零，另一条闸口就在审一个它说不出名字的子集**。判据：一条棘轮如果**挡的是「有没
  有第二条路」**而不是「有多少条待办」，它就该是绝对断言——不可表达 > 计数，这跟
  #363 是同一条。

基线：6711 → **6728 passed / 163 skipped**。mypy clean（138 files）。

### #387 是一种 artifact，和有一份形状声明，从来不是同一件事（2026-08-23）

**现象**：`themis.audits.Artifact` 是「离开进程时自报家门」的封闭清单——一个信封、
一个马尔可夫毯、交互定向的四个阶段，共 **6 种**。`themis/schemas/` 描述了其中
**1 种**。

**根因不是「五个文件没人写」**（那是工作量）。根因是那两张表**从来没有连起来**：
`validate_result` 用**字面量**点名它的文档，于是 `query_result` 有声明不是因为它特
殊，是因为它碰巧是当年被手工接上的那一个；注册表同病——七份 schema 里点名装了四
份。**没有任何东西问过这两张表是否一致**，所以明天第七种 artifact 会一样无声无息
地没有声明。

**为什么是根因不是表象**：schema 是每条结构性闸口的**分母**，所以目录外的 artifact
是**任何闸口都够不着**的 artifact。#381 建的「指纹必须带着它覆盖的列清单」那条规
则**glob 了 schema 目录**，正是为了「明天新加的容器当天就在规则里」——它从来没够到
`markov_blanket`，而那个 artifact **一直带着 `data_hash`**。不是它违规，是**没有任
何 schema 说它存在**。缺的恰好是「注册表里 schema 层不认识的那些成员」，这个形状本
身就是根因的指纹。

**修法**：`Artifact` 自己**派生**文档名（值本来就是 `kind`，第二张表就是一张会跟第
一张不一致的表）→ `validate_artifact(payload)` 按审计层早就在用的识别器
`artifact_of` 派发 → 注册表改 glob（跨文档 `$ref` 才解析得到东西）→ 五个生产者像
`kernel.py` 一直做的那样在出门时自检。**五份 schema 是这条链路的后果，不是修法本
身。**

**写声明本身把三件事变成了可说的**——这是主作用，不是副产品：

- **三个 artifact 是互相嵌套的**：session 嵌 propagation 与 question_set，ledger 嵌
  session——因为生产者就是调生产者。schema 用 `$ref` 指过去而不是各抄一份，于是
  「嵌进去两层的那个字段错了」当场被抓（闸口里就有这条）。
- **8 个封闭词表浮出水面**：CI 检验 / 检验角色 / 冲突原因 / Meek 规则 / 问题种类 /
  邻接答案 / 会话状态 / 搜索算法。它们在生产者里一直是字面量，#362 那条「每个
  schema enum 站点都要有一行说谁读它」当场报了 **10 个站点无人认领**。补的 8 行每
  行都要说清：**它的读者是重算这份 artifact 的第二实现**，人拿到的是 `note` /
  `prompt`。
- **两个真缺陷**（登记为 #428）：`OrientationQuestion.guaranteed` 的 docstring 写
  「永远 ≥ 1，至少是这条边本身」，实测是 **0**；同一处给人看的 `prompt` 渲染出
  「还能顺带定下 」后面空无一物。同源：一个方向被数据拒绝时那侧 cascade 为空，于是
  `leverage > guaranteed` 成立而要插值的集合是空的。更深的问题是——**一个方向不可
  能的边，还算不算一个「问题」**。

**明确不做的那一半**（登记为 #429）：#371 那条「『没有』只能有一种拼法」的规则，分
母仍然只有 `query_result`（`schema_walk` 点名了那一份）。实测另外六份 shipped
schema 里有 **19 个键**同时可缺省且可为 null——扩分母不是改一行常量，是**19 个各自
要判的决定**。五份新文档按那条规则写，一个这样的键都没有：`answer.direction` /
`answer.adjacency` 都是 required + nullable。

**闸口**（`tests/test_every_artifact_says_its_own_shape.py`，22 条）
- **链路本身**：每个 `Artifact` 成员都有文档、文档的 `$id` 认自己、文档声明的
  `kind` 就是这个成员。分母是 `Artifact` **自己**（6 个，5 个 standalone），不是一
  张文件名单——第七种当天就在问题之内。反例三条：删掉一份 / 让它认别人的 `$id` /
  让它描述另一个 artifact，在真目录的**副本**上跑，所以是「规则真的在开火」。
- **流量而不是声明**：五种 artifact 各造真实实例（马尔可夫毯两条 CI 路径都造、
  propagation 三态覆盖每一种冲突、session 四个回合），识别器把每一份路由到自己的文
  档、文档接受生产者**真正发出**的东西——这是「照着 builder 读一遍写出来的 schema」
  最容易写错的那一半。
- **17 个反例**：丢键 / 指纹没有分母 / 不是 SHA-256 / 两个充分统计量同时在 / 拿了兄
  弟分支的形状 / 值出词表 / 多一个没人声明的键 / **嵌进去两层的错误**。并断言这 17
  条不是同一条的 17 遍（覆盖 5 份文档）。
- **门是不是真的装上了**：五个生产者按 AST 读源码——**每一条 `return` 都必须过**
  `validate_artifact`；再加两条行为证明，用生产者自己的公开入口喂进坏结果，当场抛。
- **#381 那条闸口现在够得着它了**：断言 `markov_blanket.schema.json` 在指纹规则的分
  母里，配对就是 `data_hash` ↔ `data_columns`。

**方法论沉淀**：
- (265)**「注册表」和「描述这些成员的目录」是两张表时，缺的永远恰好是「没被手工接
  上的那些」**——判据不是「谁漏了」，是**有没有一处地方让「是 X」和「X 的形状是什
  么」成为同一个事实**。本轮的答案是让成员自己派生文档名（值本来就是名字）。反过来
  说：只补五个文件、再手工接一遍入口，就是把今天的状态原样复制到明天，而且**下一次
  同样没有任何东西能说出来**。
- (266)**写声明会逼人真的去看那些值**——五份 schema 顶出 8 个从没被登记过的封闭词表
  和 2 个真缺陷（一句 docstring 说「永远 ≥1」而实测是 0，一句给人看的散文渲染出空
  列表）。产出物一直在那儿，只是**没人被要求逐字段说出它是什么形状**。所以顺序要
  紧：**先跑出真实例、再照实例写声明**，比照 builder 读一遍值钱——前者会当场把你读
  错的地方顶回来（本轮第一版实例集没有一条开放 CPDAG，`detail` 的两支只见到一支，
  照它写出的 schema 会漏掉另一半）。

基线：6669 → **6711 passed / 163 skipped**。mypy clean（138 files）。

### #386 一个词表的成员，印出来是它被声明在哪儿，而不是它说的那个词（2026-08-23）

**现象**：`class X(str, Enum)` 让成员等于它的值、也能和值比较，然后
`str(member)`、`f"{member}"`、`"%s" % member` **三种写法一律**交出
`"X.MEMBER"`——声明的地址，恰恰是拿到值的读者唯一不需要的东西。#380 在
`Monotonicity` 上量到过**五个真实缺陷**就是这个形状，#382 把它迁到了修好这件事
的基类上。**还剩 18 个词表是旧形状**（登记写的 19，`Family` 已在 #330 迁走）。

**两件事必须分开说，而登记把它们混在了一起**

`EnvelopeName` 做的是**两件事**，而 #386 的缺陷只是其中一件：

| | 提供者 | 代价 |
|---|---|---|
| `str(member)` 是值不是地址 | `StrEnum` | 无 |
| 拷贝 / pickle 之后回来是普通 `str`（注册表不随信封走） | `EnvelopeName` | **放弃同一性**，`is` 不再可靠 |

登记里那句「先判 `EnvelopeName` 是不是凡上信封的词表都该继承」的谨慎，正是**把这
两件事当成一件**的结果。分开之后答案是现成的：这 18 个要的是**小的那件**。
`StrEnum` 保住 `is`（包里 31 处 + 测试里 124 处共 155 处比较原样不动）、
`json.dumps` 逐字节不变、mypy clean、全量套件一条不红。

**那 `EnvelopeName` 到底欠在哪儿？** 它欠在「**一个活的成员被放进了信封结构本
身**」的地方——那时谁 deepcopy 这份答案，谁就连注册表一起拿走了。**实测**产出的
信封：**恰好 4 个**——`Block` 当键，`Layer` / `Provenance` / `Severity` 当值——
而这 4 个**本来就已经是** `EnvelopeName`。18 个里一个都不在。

**登记留的那个开放问题，答了：今天没有一个地址真的到了读者。**
借用 `test_no_sentence_reaches_the_reader_in_the_wrong_language` 已经建好的语料
（L3 全部 case + conditional_iv，内核发出的**每一条**字符串）问同一个问题：
**4072 条里 0 条**带地址——**迁移前也是 0**（`git stash` 前后各跑一遍）。

所以这一条如实说是：**把一个潜在缺陷改成不可表达，而不是修好一个正在发作的
缺陷**。它值得做的理由是三条：① #380 证明这个失效模式**真的会发作**；② 产生它
的写法是**变量插值**，静态扫描看不见（登记里就写了这一点）；③ 代价为零。18 处
「一旦有人插值就静默说错话」变成 0 处，闸口让它留在 0。

**闸口**（`tests/test_a_vocabulary_prints_as_the_word_it_is.py`）
- **三种写法都钉**：`str()` / f-string / `%s` 逐成员相等于值。分母是包自己的
  `Enum.__subclasses__` 走查（32 个词表、200+ 成员），不是一张基类名单——明天新
  声明的第 19 个自动在问题之内。判据自带反例：就地声明一个 `(str, Enum)`，同一
  条判据当场认出它印的是地址。
- **明确钉住「没改的那一半」**：非 `EnvelopeName` 的词表 `deepcopy(m) is m`。这
  条不是多余的——它把「小基类不收那笔代价」写成了不可回退的事实。
- **`json.dumps` 逐词表不变**：迁移在信封上必须是隐形的（这也正是这个缺陷能长期
  潜伏的原因）。
- **`EnvelopeName` 欠在哪儿，成了可以点名的规则**：走查产出的信封，任何**活成员**
  必须是 `EnvelopeName`，并断言今天就是那 4 个——第 5 个出现时是一次可见的变更。
  同样自带反例：把一个没放弃同一性的成员种进同型位置，同一个走查找得到。
- **读者面**：内核发出的每条字符串都不带地址；地址正则单独钉（否则上一条靠匹配
  不到任何东西而通过）。

**方法论沉淀**：
- (263)**一个基类做了两件事时，「要不要继承它」这个问题是问不出答案的**——本轮
  卡住的不是难，是**问题问错了**：`EnvelopeName` 同时提供「印成值」和「放弃同一
  性以离开进程」，于是「凡上信封的都该继承吗」既不能答是也不能答否。把两件事
  拆开列成表，18 个要哪件、4 个要哪件，当场就清楚了。判据：**先列出这个基类分别
  提供什么、各自的代价是什么**，再问每个候选欠的是哪一件。
- (264)**「这个潜在缺陷今天发作了吗」要真去量，量出 0 也要如实写下来**——量出 0
  不是不修的理由（#380 证明它会发作、写法静态不可见、代价为零），但它决定这条
  entry 怎么写：是「修好了一个正在发作的缺陷」还是「把它改成不可表达」。把 0 说
  成前者，下一个人读这份 changelog 时会高估系统曾经的糟糕程度。借现成的语料问新
  问题，比为新问题另建语料更可靠——分母是别人已经辩护过的。

基线：6580 → **6669 passed / 163 skipped**（新增 89 条断言 + 13 条按基类跳过）。
mypy clean（138 files）。

### #427 一条缺口有两条路到 JSON，只有一条知道「没有」该怎么拼（2026-08-23）

**现象**：任何 overlap 稀薄的运行——倾向性分数被裁到下限、触发
`propensity_overlap_violation` 缺口——产出的信封**过不了自己的 schema**：

```
SyntacticError data_gap_report/gaps/4/required_data: None is not of type 'object'
```

四个 ATE 估计量（gformula / ipw / aipw / tmle）全中。schema 上
`required_data` 声明的是 `type: object` 且可缺省，正是 #371 定下的三种无歧义
形状之一——它从来没允许过 `null`。

**根因**：一条缺口变成 JSON 有**两条路**。

- **跑之前**发现的缺口是 `DataGap` dataclass，走 `_data_gap_to_dict`，那里
  `required_data is None` 时**不写这个键**。
- **跑之中**发现的诊断缺口（overlap、quasi-separation、弱工具、过度识别被否、
  声明类型不符）是估计层填进一份**已经序列化**的报告里的，于是 7 处**手写
  dict**，照着 dataclass 的字段表逐字抄——其中 3 处把 `None` 也抄了进去。

dataclass 的 `None` 意思是「没有这件事」；JSON 里「没有」有两种拼法，而 schema
只承认其中一种。两者在 Python 源码里**长得一模一样**。

**为什么是根因不是表象**：不是这三处忘了删。#371 已经把「没有怎么拼」钉在了
**声明**上，而且如实登记了自己的边界——「规则钉在声明上而不是流量上，`run()`
不校验自己的产出」。第二条路因此可以长期违反契约而不出错。补这三个 `None`
只修这一批，下一处手写缺口还会再犯；而且手写 dict 里 `kind` / `severity` /
`blocks` 是**没人检查的裸字符串**，拼错要等到 schema 校验才知道——而那正是没在
跑的那道检查。

**全量扫**（判据：包里每一个「带 kind + severity + description 且带 blocks 或
provenance」的 dict 字面量）：8 处，全在 `dispatch.py`。3 处写 `null`；
1 处是个**死的临时 dict**——它抄了 `kind` / `severity` / `blocks` 三个字段，而调用
方只 `pop("description")`，那三个字段是同一批事实的**第三份**拷贝，没有任何人读。

**修法（第二条路走第一条）**

- `_data_gap_to_dict` 改名 `data_gap_to_dict` 并公开：它是**唯一**决定「没有」
  怎么拼的地方，而它需要第二个调用方。
- 估计层的 7 处改成构造 `DataGap`。这不是「把三个 `None` 删掉」——是让这种拼法
  **不可表达**（#363 的原则）：dataclass 没有办法说「键在、值是 null」，而
  `kind` / `severity` / `blocks` 从裸串变成封闭词表的成员。
- 新增 `_file_gaps(result, gaps, summary=)`，把 5 处重复的「翻译 → 没有报告就
  建一个 → 有就追加」并成一处；新增 `_verifier_check(ref_id)`，把 7 份一模一样
  的 provenance 字面量并成一句。
- 那个死 dict 化成一个字符串局部量。

**闸口**
- **结构闸**：包里 dict 字面量中呈缺口形状的，有且只有一个，且必须在
  `data_gap_to_dict` 里。分母是**包里每一个 dict 字面量**，不是「有人看过的那几
  处」。判据自带反例：把改之前那段原样喂给同一个走查，它认得出来。
- **行为闸**：薄 overlap 的帧 × 四个估计量，先断言那条缺口**真在**信封里（否则
  测试是空的），再 `validate_result`。外加把改前那条 `required_data: null`
  原样塞回去，确认 schema 仍然拒。
- 翻译器自身：四个可选字段全为「没有」时，四个键**都不出现**；给了值时都写出来。

**判据修正**（值得记）：一开始以为「缺的是一道检查」。不是——`validate_result`
在 **40 个测试文件**里被调用过。缺的是**语料**：没有任何一份测试数据薄到会触发
这条缺口。检查早就在，只是从没在带着这个形状的信封上跑过。

**方法论沉淀**：
- (261)**dataclass 的 `None` 和 JSON 的 `null` 在 Python 源码里同形，所以「照着
  dataclass 的字段表手写 dict」必然把「没有」抄成「有一个键、值是空」**——判据
  是「这个概念有没有第二条不经过转换器的路到达信封」。有第二条路时，修法不是补
  那几处，是让第二条路走第一条：转换器是唯一知道「缺省 vs null」的地方，而手写
  dict 连这个问题都问不出口。
- (262)**一道检查被调用了 40 次，不等于它跑过 40 种形状**——本轮的检查早就存在
  且到处在调，缺的是「带着这个形状的输入」。判断一道闸口有多强，数的是它见过的
  **分支**，不是它被 assert 的次数；补的是语料，不是断言。

基线：6568 → **6580 passed / 150 skipped**。mypy clean（138 files）。

### #426 一个估计量只有一个「谁定的形状」，而它拉了不止一根杆（2026-08-23）

**现象**：同一批数据、同一个**没被任何人碰过**的 propensity 裁剪下限 0.01、同样
618 个单位被裁——四次运行，台账对「这个下限是谁定的」给出三个不同答案：

| 运行 | `propensity_clipped_to_floor_0.01_on_618` |
|---|---|
| ipw | `inherent`（方法本身要求） |
| aipw + `model='logistic'` | **`caller_asserted`（你在问题里断言的）** |
| aipw（auto） | `default`（估计器默认选择） |
| tmle | `inherent` |

真答案是「没人」。`caller_asserted` 这一条是**要读者付代价**的：词表里它承诺「撤回它
答案就变宽」，而读者手上根本没有可撤回的东西。同一次运行里还有第二条同病——AIPW 的
`doubly_robust_outcome_OR_propensity_model_correct`（双稳健）也读成 `caller_asserted`，
等于告诉读者「双稳健是你断言的」。

**根因**：`form_provenance` 回答的是「**谁定的结局模型**」，而 `settled_form` 把这
**一个**答案发给估计量声明的**每一条**函数形式假设。一个估计量做的形状决定不止一
个，各由不同的杆拉动（`model=` / `propensity_floor=` / `stabilized=`），而其中只有
`model=` 的「什么都不做」是一个**词**（`"auto"`）——另外两根杆的默认值是**真值**
（0.01、`True`），于是「叫了这个值的调用」和「什么都没叫的调用」在函数体里完全同形，
答案在调用那一刻就被销毁了，下游没有东西可读。

**为什么是根因不是表象**：#423 留下的例外表 `_FORM_NOT_RESOLVED` 正是想补这件事，
而它是**消费者**手上的一张表，按 id 猜「哪些 id 站在这次解析之外」。它猜漏了：
按同一条判据把 33 个函数形式 id 全量扫一遍（判据＝「这条 id 的来历，和这次运行解结
局模型的那件事，是不是同一件事」），漏掉的有 5 处（aipw 的裁剪下限 ×2、权重形态、
双稳健，tmle 的裁剪下限）。而且它**不可能**猜对：`hajek_stabilized_weights` 在调用
者点名时和没点名时都会被声明，同一条 id 两种来历，keyed on the id 的表没有值能同时
为真。只有估计量知道自己有哪几根杆。

**修法（做决定的那个人，在做决定的地方说出是谁定的）**
- `form.py` 加 `UNSET` / `pulled_by(value)`：非字符串的杆用**哨兵**当「什么都没说」，
  和 `AUTO` 之于 `model=` 是同一件事，差别只是「不做」长什么样。
- `form.py` 加 `shapes_settled(assumptions, *pairs)`：估计量报出它**可能**发出的
  (id, 来历) 对，**由这次真正声明的那条 assumptions 元组决定哪些是真的**——这次没
  假设的形状不能带着「谁假设的」出现，而且读的是同一个将要进信封的元组，来历不会被
  归档到一个读者永远看不到的 id 上。
- 每个估计上加 `shape_provenance`（29 处声明）：**restate 结局模型形状的那些 id 拿
  上面那个答案，别的杆定的 id 自己说**。裁剪下限的 id 只有一个作者
  （`_propensity_floor_id`），三个族共用。
- 设计矩阵那条（`multi_level_covariates_entered_as_ordered_numbers`）作为
  `ORDERED_ENTRY_SHAPE` 常量挂在 id 旁边——九个 append 这一行的族不可能各说各的。
- 消费者那张猜测表整张删掉：`_FORM_NOT_RESOLVED` 与 `settled_form` 从词表里移除，
  `build_mechanism_audit` 多要一个**没有默认值**的 `shape_provenance`（和
  `form_provenance` 同样的纪律：默认值本身就是这个缺陷）；给了一条这份估计从没声明过
  的形状的来历，直接抛。
- 验证器那条重述的例外表也删掉，换成它当初真正在替的那个事实：
  `_ONE_PER_LEVER`——**一根杆只有一个位置**，所以一个块不能同时点名 `linear` 和
  `logit`。这比原来的检查**更严**：原来比的是「答案是否一致」，两条都写 `default`
  的 linear+logit 伪造能过；新的不管答案说什么都拒。

**顺带量到、已登记**：① 这四次运行的信封都过不了自己的 schema——`required_data` 被
写成 `null` 而 schema 声明 `object`，缺口条目有两个作者（登记为 **#427**）。②
`propensity_floor=` / `stabilized=` 这两根杆在 Python API 上存在，但**从 JSON program
进不来**——于是走 `themis.estimate` 的读者被告知「默认，你可以指定一个」，而他们进来
的那扇门没有这个入口；信封上也没有「形状杆」这个一等词表。这一半是这次**明确不做**
的，一并登记。

**方法论沉淀**：
- (259)**「什么都不做」必须和「做了一件恰好一样的事」长得不一样，而这要在调用那一刻
  就分开**——默认值是真值的杆，把「谁定的」这条信息在函数入口处就销毁了，之后无论下
  游多聪明都推不回来。补救的形态永远是消费者猜，而消费者猜的是生产者的杆。哨兵不是
  风格问题，是让这条信息**有可能存在**的前提。
- (260)**消费者手上按 id 猜「哪些是例外」的表，错的不是内容而是位置**——它一定漏，因
  为同一条 id 在不同族里来历不同（`hajek_stabilized_weights` 点名与不点名都会声明）。
  这类表的正确修法不是补条目、也不是把表搬到生产者那里当常量，而是**让做决定的地方
  当场说**，再由「这次真声明了什么」筛掉没发生的。表删掉之后，验证器不能跟着删——要
  问「这张表当初在替哪个事实站岗」，把那个事实独立重述出来（这里是「一根杆一个位
  置」），常常比原来的检查更严。

基线：6553 → **6568 passed / 150 skipped**。mypy clean（138 files）。

### #425 「答案是一个集合」这个形状，浏览器没有渲染器（2026-08-23）

**现象**：`counterfactual_cell` 上有 `point / ci_lower / ci_upper / ci_width_is`
四个字段。主报告四样全印，浏览器**一样不印**——它只印 `[lower, upper]`，而它自己
的路线说明写着「在数据上重算这一格反事实（并用自助法给出抽样区间）」。同一个信封，
两个读者面对「这个答案里有什么」给出不同的清单。顺带还差两样：后门调整集、以及
「若能假设单调性这一格会收紧」。

**根因**：浏览器只有**一个**区间渲染器 `band()`，而它是**围绕「点」造的**——
`if (b.point == null) return ''`。「答案是一个集合、外面再套一条带」这个形状**没有
渲染器**，于是每个这样的位置都得手写；信封上正好只有两个对象是这个形状
（`intervals._BIMODAL`：因果概率量、反事实格），一处手写了，另一处没有。漏的不是
一行代码，是**这个形状没有名字**，所以在每个点上写它都是可选的。

**为什么是根因不是表象**：① `band()` 自己那句提前 return 就是这个假设的字面记录。
② 手写了的那处复现了四个决定——头部是点还是区间、带说的是两个对象里的哪一个、百
分比、点旁边那条无假设区间——**一个都没共享**，第三个同形状对象会再掷一次同样的硬
币。③ `ci_width_is` 正是 #419 加进来专门分辨这两个对象的字段，而它在浏览器上只有
**一个**调用点：字段加了，只有一个作者学会了说它。

**判据修正**（值得记）：先按「两个面对同一个块的每个键说法是否一致」全量扫，得到
「24 个块里 11 个有不对称」——**这个分母是假的**。共享 helper（`_band`、`band`）会
让「这个渲染器的正文里没出现这个键」误判成「这个面不说它」，两个方向都误。真正可
判定的分母是 `intervals.DECLARED`：信封能装的每一对端点，一条不落，且已经是封闭
表。按它扫，缺口精确为**「宽度由这次运行决定」的 2 对里的 1 对**。

**修法**
- `verdict.ts` 补上这个形状缺的那个渲染器：`pointOrSet(q, ciLevel, lang)` 吃
  `{point?, lower?, upper?, ci_lower?, ci_upper?, ci_width_is?}`，出「头部 + 带」，
  带里的宽度词由 `ci_width_is` 决定而不是由 `point != null` 反推。
- **两个双模位置都改走它**——因果概率那处从「唯一的手写者」变成第二个调用方，这一步
  比补上反事实格更重要：是它把「写这段是可选的」变成了「写这段是不可能不写的」。
- 反事实格补上：带、后门调整集、「什么能收紧它」。`types.ts` 把这个面确实要用的
  六个键声明出来。
- 闸口：`intervals` 判为 run-decided 的每一对，两个读者面都必须说出宽度词；表的键
  与词表本身**逐对相等**，所以第三个双模对象不可能带着一个面沉默进来。

**验的方式**：TypeScript 不能从 pytest 跑，所以这次把它**真跑起来**了——`tsc` 出
JS、node 直接调 `answerRows`，中英两语 × 三种形态（集合+外带 / 点+置信区间 / 已声
明单调性）逐行读输出，确认宽度词随 `ci_width_is` 变、单调性已声明时那条「什么能收
紧它」正确消失，并确认因果概率那处重构后逐字不变。

**方法论沉淀**：
- (257)**判据不可判定时，换分母而不是降标准**——「两个面说法是否一致」在共享
  helper 面前静态不可判，扫出来的 11/24 两个方向都有假阳。此时正确的动作不是给扫描
  器打补丁、也不是凭它动手，而是**换一个已经封闭、已经有权威表的分母**
  （`intervals.DECLARED`），代价是覆盖面变窄、换来的是每一条都真。窄而真的闸口能长
  期立住，宽而假的闸口第一次误报就会被绕过去。
- (258)**「这个形状没有渲染器」和「这一行忘了写」是两种缺陷，只有前者会重犯**——补
  上漏的那一行，下一个同形状对象还会漏；补上形状的渲染器，并**把已经写对的那处也改
  去走它**，才算修完。已经写对的那处不改，它就仍然是「可以不走」的证据。

基线：6545 → **6553 passed / 150 skipped**。前端 `tsc --noEmit` clean。

### #424 收紧哪一侧，是关于结局的问题，而三层都拿干预的极性顶了缺（2026-08-23）

**登记时说的是**「对照界现在挡不住了，缺的字段（#419 的 `tightness`）已补，把
Manski-Tamer 的对照建起来」。侦察推翻了这条登记的**前提**，并在同一处量出一个
**严重得多**的东西。

**现象**（端到端实测，不是推断）：问 `P(Y=False | do(X=True))`，答案区间
**不含真值**——真值 0.50，区间 [0.56, 0.66]，整段在真值上方；三档结局问底档同
病。走的是 `themis.estimate`，到得了读者，而 `themis.verify_bounds_results`
**通过**。

**根因**：收紧哪一侧需要**两个事实、关于两个变量**。一个关于 X——在这个臂上干预，
对另一臂观测到的那些单元，会把 Y 往上推还是往下推；另一个关于 Y——目标**事件**
在结局的序里排第几。MTR 约束的是 **Y**，而界是加在**事件 `Y=y`** 上的，
`1{Y=y}` 只在序的**顶端**随 Y 单调：底端反号，中间两个方向都不单调。系统里只存在
第一个事实。于是符号层（`output/bounds.py`）、数值层（`bounds_numeric.py`）、验证
器（`bounds_rules.py`）**三个作者各自独立推导，都写出**
`tighten_lower = treating_high == direction_increases_y`——**都拿手上唯一有的那个
极性，顶替了谁都没有的那个**。

**为什么是根因不是表象**：三份独立推导来自同一个缺失输入，就不是三道检查。旧规则
恰好是通式在 `y = y_max` 处的特例，所以围绕它写的每一条测试都是对的——缺陷不在任
何一处笔误里，在**这个事实没有槽位**。

**通式**（`a` = 干预臂，`b` = 另一臂，`up` = 在 a 上干预是否把 b 的单元往上推）：

```text
up:      lower = P(a,y) + 1{y=y_max}·P(b,y)     upper = P(a,y) + P(b, Y ≤ y)
not up:  lower = P(a,y) + 1{y=y_min}·P(b,y)     upper = P(a,y) + P(b, Y ≥ y)
```

在（二值，顶档）处逐字复现旧代码，底档换边，中间只收紧上界。决定侧的极性是
`up` **XOR** 「y 是那个方向上的极端」。

**登记的前提也不成立**：对照**是 sharp 的**。原来的理由——MTR 把 Y(x) 与 Y(x')
在单元层面绑在一起——为真，但推不到结论：两臂的**未知量**住在**互不相交的子总体**
里（b 单元的 Y(a)、a 单元的 Y(b)），各自只被自己那个单元的观测约束，所以两区间里
任意一对点都可同时达到，区间之差就是差之区间。用响应型枚举独立复核过：二值/二值给
出 `[0, P(X=x,Y=y) + P(X=x',Y≠y)]`，与两臂相减逐项相等。

**修法**——把序当**输入**接进来，而不是从别的字段反推：
- `runtime/scheduler.py` 新开 `_mtr_outcome_levels()`，**符号层与数值层同一个读
  者**，两层不可能假设出不同的序。声明 `nominal`、无 domain 且目标非 bool、目标值
  不在档里——三种都返回 `None`（都是同一句话：这里没人知道序），MTR 不出这一行。
- **序的来源**：类型自己有序就用类型的（`domain: [true, false]` 是这些程序列布尔
  的习惯写法，不是「false 更大」的声明）；类型没有序，声明写下的顺序就是唯一的
  序——`scale: nominal` 是说「没有序」的那句话。
- 数值层改成**在联合计数表上求闭式**（`xy_counts` + `mtr_bounds_from_counts`），
  并把表连同**读它用的档序**一起记进 `sufficient_statistics`。
- 验证器**自己再从 program 推一遍序**（`_declared_outcome_order`），复算区间与对
  照（`_rederive_manski_tamer_numeric`），并把两份序对上——**读出不同序的生产者从
  此是一次分歧，不再是第二个无声的答案**。

**两道独立复算**：随机 SCM 上跑 3 种基数 × 2 个方向 × 2 个臂 × 每一档，既查真值
落在区间里，也**构造出坐在端点上的那个 MTR 世界**（复现观测、逐单元核对仍满足
MTR、读出 P(Y(x)=y) 等于端点）——sharp 是构造出来的，不是断言的。

**方法论沉淀**：
- (255)**三份独立推导来自同一个缺失输入，就不是三份**——验证器复述生产者是设计，
  前提是两边**输入齐**。缺的那个事实不会因为被问三遍就出现；三个作者只会各自拿手
  上唯一有的那个近似值去顶，而且顶得一模一样。所以「验证器独立复算」这条纪律要配
  一句：**先问这条规则需要哪些事实，再问每个事实有没有槽位**。
- (256)**登记条目给的解法也是待验证断言，连它的「为什么不能做」一起**——#424 登记
  的是「字段补了，界可以建了」，而实际是前提（不 sharp）错、真缺陷（界不含真值）
  更严重。拦住这次动手的那句话（「subtracting 是外界」）被写进了三个地方的注释和
  一个测试的 docstring，**看起来像已经查过的结论**。判据：一句拦住工作的理由，重
  新推一遍的成本通常远低于它拦住的东西。

基线：6518 → **6545 passed / 150 skipped**。mypy clean（六个改动模块）。

### #423 「谁定的这个形状」不是这个 id 的属性，而台账问的正是这个 id（2026-08-23）

**现象**（两处实测）：调用方在 `themis.estimate(..., model='linear')` 里点名了函
数形式，机制块如实写 `caller_asserted`，**旁边那行台账写 `inherent`**——中文渲染
成「方法本身要求」。读者手里握着改掉这个形状的那个参数，却被告知这个形状不是他能
动的。第二处更硬：`model='logistic'` + 一列三档协变量，块级那**一个** `provenance`
字段底下挂着两条形状假设——一条是调用方点的名，另一条
（`multi_level_covariates_entered_as_ordered_numbers`）是**估计器的设计矩阵自己
决定的**，没有任何 `model=` 的取值能命名它。一个字段，两个来历。

**根因**：`answerable(assumption_id)` 回答的问题**不是这个 id 的属性**。它那句
`return Provenance.INHERENT` 兜底对全部 33 个函数形式 id 生效，而
「谁定的形状」是**这次运行**的属性：同一个 `logit_outcome_regression`，在 TMLE
里是方法的定义（TMLE 不收 `model=`，调用方没有杠杆），在 back-door 里是估计器解析
出来的默认，而调用方传一个参数它就变成 caller_asserted。**三个答案，一个 id**——
没有任何一张按 id 索引的表能填对，把表填满也不行。

**为什么是根因不是表象**：三个物证，都不是读出来的而是量出来的。
① `ledger.py` 里 `ADMISSIBLE["audited_mechanism"]` 的注释**已经把这个诊断写下来
了**，并点名 `Provenance.DEFAULT` 在这一行「至今没有生产者」——一个成员写在白名单
里却没人能写，就是缺口的静态残留。② 现有测试
`test_one_id_gets_one_answer_about_who_can_overrule_it` 把这个 bug **钉成了规则**：
它断言「同一个 id 跨族只能有一个 provenance」，听起来像不变量，实际正确的事实是
**跨族必须不同**；它之所以一直通过，是因为每一条形状行都读 `inherent`。③ 块级那
一个字段今天就在说假话（现象第二处）。

**普查**：33 个 exact FORM id + 1 个前缀。按**族**扫而不是按 id 扫——只有 5 个族
解析 `model=`（backdoor / frontdoor / joint / mediation / dose_response），其余
16 个族的 `form_provenance` 是 dataclass 上的常量，所以这次运行的答案对它们声明的
每一条都已经是对的。5 个解析族里挑出**5 条不随解析走**的：设计矩阵的有序进入、
logit 臂上抽中介用的高斯 copula（`model=` 没有一个取值叫 copula）、front-door 多
中介的链式分解、以及两条无条件声明的分解前提。

**修法**
- `answerable()` 对形状 id **拒答**（builtin `ValueError`：没人接、读者也永远看不
  到，它是接线错误不是拒答）；`classify_assumption` 对形状 id **不写
  `provenance` 这个键**——缺席而不是 `None`：需要它而忘了取的人拿到点名 id 的
  `KeyError`，只要 layer 的人根本不问。顺带把三个分支各写一遍的那份分类抽成一份
  `_row`，并开出 `layer_of()`，让「只要层」的调用方不必先造一句谁都没要的译文。
- `settled_form(id, resolution)`：默认取这次运行的 `form_provenance`，例外表 5 条
  按 id 命中。
- 块级 `provenance` **删掉**，`assumptions` 从 `[id]` 变成 `[{id, settled_by}]`。
- 台账两处折叠并成一个 `_fold_mechanisms`，形状通道**排在扁平通道之前**；扁平通道
  遇到答不上来的形状 id 当场拒，并说清「块是从同一份清单建的，这里有那里没有，说
  明它是从另一份建的」。
- `ADMISSIBLE` 两头都动：`estimator_assumption` **收掉** `functional_form`（那个
  通道只有 id，本来就答不了），`audited_mechanism` 加 `caller_asserted`（现在真有
  生产者了）。收窄比放宽更值得说：在它还允许的时候，那个通道写出来的 pair 是
  `(functional_form, inherent)`，**每一条都是**。

**两道独立复算**（新字段不配复算，等于把「读者自己猜」换成「读者信一句没人核过的
话」）：
- **块与行必须说同一件事**——这道不需要任何自带的表：块为重算的人写，行为读者写，
  两份是同一个生产者给两种读者的答案，唯一不能成立的就是它们不一致。而这恰好**就
  是这次的缺陷本身**。
- **一次运行只解析出一个形状**——自带一份例外表副本（读被检查那方的表会按构造同
  意）。它抓的是上一道抓不到的：两个面**互相一致**、但一致在一个没有任何运行能产
  出的答案上。
- 顺带补一个真缺口：验证器 `_caller_supplied` 要求 `caller_asserted` 的行**追得到
  调用方真的给过什么**，而 `estimation_context.model_preference` 这个记录一直在信
  封上、**从来没有读者**——因为在形状行能说出 `caller_asserted` 之前，没有东西需要
  追。现在读它。

**度量**：`model` 不指定 → 块与行都 `default`；`model='linear'` → 都
`caller_asserted`；三档协变量 + `model='logistic'` → **同一个块里**
`logit_outcome_regression: caller_asserted` 与
`multi_level_covariates_entered_as_ordered_numbers: default`，摘要句里两个「来源：」
各说各的。四道拒答都构造了反例：改行不改块、块点名一个没人声明过的 id、块退回裸
字符串（schema 与规则**两扇门各拒一次**）、一次运行两个解析结果。

**一个当场量出、但没有一起修的**：`stabilized` 与 `propensity_floor` 都是调用方可
传的参数（`aipw.py:199-200`），所以 `hajek_stabilized_weights` /
`propensity_clipped_to_floor_*` 的来历也不是 `inherent`。但这批 id 全长在**形状固
定的族**里，它们的 `form_provenance` 是常量——这是同一个「一个字段 N 个事实」的病
往上一层：**估计量只有一个 `form_provenance`，而它可能做了好几个来历不同的形状决
定**。本条改动对这批 id 是行为中性的（改前改后都读 `inherent`），我没有拿猜的值填
进例外表。登记为 #426。

基线：6499 → **6518 passed / 150 skipped**。mypy clean（138 个源文件）。浏览
器无改动：`mechanism_audit` 至今没有任何前端读者，那是 #368 族的事，不是本条的洞。

**方法论沉淀**：(253)**一条测试断言的「不变量」，可能就是缺陷本身被写下来了**
——判据不是它看起来对不对，而是**去问它守的那个量是谁的属性**：
`test_one_id_gets_one_answer` 守的是「一个 id 一个答案」，而那个答案是运行的属性，
于是它守的其实是「所有族都给同一个错答案」。这种测试的特征是**它通过的方式很单
调**：全场同一个值。找法是把断言的键（这里是 id）和事实的宿主（这里是 run）并排
写出来，两者不同名就是嫌疑。(254)**兜底返回值是最贵的一种沉默**：`return X`
写在函数末尾，读起来像「其余情形的答案」，实际是「我答不了，但我还是给你一个」。
分辨它只要一问：**这个函数看得见回答这个问题所需要的东西吗**？看不见就该拒答而不
是兜底——而拒答之后，「谁来答」这个问题会自己浮出来，因为编译不过的地方就是答案
应该来的地方。

### #419 一对键名装着两样东西，而四个面各自反推了一遍（2026-08-22）

**现象**：一份结果上并排三条区间。`iv_wald [0.326, 0.426]`，旁边挂着
`precision_budget` 说「再收 N≈16000 行，宽度减半」；`manski_natural
[0.348, 0.852]`，再多数据也一寸不窄；`balke_pearl_iv [0.552, 0.759]`，比
Manski 窄 2.4 倍，而**那 2.4 倍是声明了一个工具变量买来的，不是数据买来的**。
三条区间，一块屏幕，读者没有任何东西可以问「哪条是哪种」。

**根因**：不是「报告漏了句解释」，是**区间没有一个地方说出「我的宽度是关于什
么的」**，于是每个面各自去反推。报告的 causation 渲染器探 `point is not None`
来决定印「CI」还是「外带」，注释里自己承认了（"one pair of CI keys, two
meanings"）；`verdict.ts` 又推了一遍；`types.ts` 用散文第三次说了同一件事。而
`numeric_result.interval` ——有界反事实与有界 PN 的答案落点——只有
`{low, high}`，**连可反推的东西都没有**。

**为什么是根因不是表象**：这个缺失的字段今天就在**挡着代码不让写**。
`evaluate_manski_tamer_bounds` 明说它拒绝报一个它算得出来的对照，因为两条 MTR
区间相减得到的是**外界**而不是紧界，而「信封上没有字段说得出一行是哪种」。一
条 valid-but-unsharp 的行混在 sharp 的行里发出去，是同一个缺口的另一副面孔。

**普查**：26 对端点，四种拼法（`lower/upper`、`low/high`、`ci_lower/ci_upper`、
`lower_value/upper_value`）。17 条抽样 CI、6 条识别集、1 条固定外带、2 条由这次
运行决定。**`ci_` 这个前缀不是答案**：戴着它的那批里有一条是识别集的外带，两条
是「看这次跑出什么」。

**修法**（判据取自 #379）：把事实做成**行上的字段**，按「它是什么」命名，规则去
**读**它——绝不从另一个字段的形状反推。

- `intervals.Width` 三个成员：`sampling` / `identification` / `outer_band`。三
  个而不是两个——对**一个点**的置信陈述和对**一个识别集**的置信陈述是共用一对
  键名的两样东西，而识别集本身是第三样、根本不是置信陈述。每个成员带
  `advice`：「再收数据会不会变窄」是裸的两个数说不出、又恰好决定读者下一步做
  什么的那一半。
- `intervals.Tightness` 两个成员，**与上面正交**：同一套假设下有没有更窄的集。
  两件事只说一件，读者拿到的是错的那一半。
- `DECLARED` 是普查表，测试从 schema 走出所有端点对，**两个方向都钉**——新加一
  对端点而没回答「它的宽度是关于什么的」，当场失败，而不是加入需要读者猜的那一批。
- 两条「由这次运行决定」的不声明宽度，而是**点名信封上 settle 它的那个字段**
  （`settled_by`），由知道答案的那个 producer 写；没写就拒，不当常见情形读。
- 「没人说」降级成一个词而不是 traceback（`宽度未声明的区间`），且这个决定放在
  词表旁边一处——两个面问的是同一对端点，各自造一个词就是造两个不一样的词。
- **两个新字段各自配一份独立复算**。加字段而不加验证器镜像，只是把「读者自己猜」
  换成「读者信一句没人核过的话」，而这两句话恰好是**指挥读者下一步动作**的那句。
  `ci_width_is` 由验证器从「这次跑出点了没有」重新判定，写进推导步骤的 inputs 一
  起被审；`tightness` 由 bounds 验证器**自带一张表**（像它自带 estimand 表一样）
  ——去读 `intervals.TIGHTNESS_OF` 就会按构造同意，包括那张表本身错的时候。两道
  都构造了它该说「不」的反例：换词、不写词，端到端 `themis.verify` 都拒。

**自己数错了一次**：登记时数出三个作者，实际是**四个**——`explainer.py` 的反事
实单格也在探 `point is not None`，而且它给外带起的名字（「区间自身的抽样带」）是
第四种叫法。它不是我扫出来的，是**「块的每个键都要有读者」那道闸口在新字段上报
出来的**：`ci_lower` 这种叶名在报告源码里到处都是，扫描碰巧命中；`ci_width_is`
只此一处，于是闸口第一次真的问了这个块。顺带量出主报告的单格一节**根本没印那条
带**——只印识别区间，抽样那一半从没到过读者，现在两行都印。

**两道普查为此各多了一个能说的词**（都是「先能说，再能钉」）：
- 词表到达普查原本要求「schema 各站点的并集 == 成员集」。`Width` 是第一个**信封
  只能装一个真子集**的词表：`identification` 分类的是**槽位**，永远不会作为一行
  上的值出现。加 `partly_stated` 说清哪几个成员信封装不下、它们怎么到读者，并且
  **两头都盯**：站点多说了要炸，站点追平了也要炸（那句话就该删）。
- 块静默普查原本的三个答案是 consumed_by / said_by / vocabulary。这个键都不是：
  它有读者、拿得到词，只是渲染器**问了普查而没有拼那个字段名**。加 `read_through`
  说「拼写归这个登记表所有」，并检查两半——登记表真的持有那个拼写，且这个块的读
  者真的在问它。

**度量**：bounds 一节印
`…（无假设；紧的）[0.3483, 0.8522]；balke_pearl_iv（假设 iv1_relevance,
iv2_exclusion；紧的）[0.5519, 0.7591]。…关于宽度：再收数据不会变窄——宽度是这套
假设的事，要窄得再加一条假设。` 反事实单格三态（`outer_band` / `sampling` /
没写）分别印 `识别区间的外带 [0.17, 0.68]` + 对应 advice、`置信区间 [0.17,
0.68]` + 另一句 advice、`宽度未声明的区间 [0.17, 0.68]` 且不给 advice；英文面同
时出现。验证器侧：把有界 causation 的 `ci_width_is` 改成 `'sampling'`、或整个删
掉，`themis.verify` 都抛
`numeric_causation_estimate: ci_width_is is 'sampling' and this run produced
'outer_band' — the pair is a band on the identified interval.…`；反事实单格同型。

**一个被度量否掉的猜测**：原本假设 `_compute_precision_budget` 会把「再收 N 行
宽度减半」挂到一条识别宽度的区间上。实测：有界 causation 与有界反事实两条路上
`numeric_estimate.ci_lower/ci_upper` 都是 null，预算根本不触发。记为已否证，不
写进现象。

基线：6440 → **6499 passed / 150 skipped**。mypy clean（138 个源文件）；
`tsc -b` 通过。留下 #424：MTR 的对照界现在说得出「外界」了，界本身还要建——那是
一个新的估计量，带自己的正确性负担，不是本条的收尾。

**方法论沉淀**：(251)**同一件事被 N 个面各自算出来，等于那件事没有被记录下
来**——找法是搜「独立重复的推导」，尤其是**注释里已经承认了的**那种。分辨它是真
缺口还是单纯的重复劳动，只要一条判据：**有没有代码因为它而写不出来**；一个
producer 明说「我算得出来，但没地方说它是哪种，所以不报」，那就是字段缺失最硬的
物证。而 N **一定要重数**——手扫会漏，因为漏掉的那个面的叶名往往和别处撞名，扫
描碰巧命中就看不见了；**真正把第四个作者报出来的是「新字段没有读者」这道闸口**，
所以补字段时要顺着闸口的报错一路读到底，而不是补完就走。(252)**把一个事实从
「各面反推」改成「信封声明」，本身不减少错误，只是把错误换了个地方放**——反推至
少是从别的字段算出来的，声明是一句谁都没核过的话。所以「加字段」这件事的完成态包
含一份**独立复算**：能重算的（这次跑出点了没有）就在验证器里重算，重算不了的（这
个方法紧不紧）就让验证器**自带一份表**，绝不去读被检查的那一方的表。

### #418 一个命题两个作者，而只有措辞较差的那个到得了读者（2026-08-22）

**现象**：问「吸烟是否因果影响癌症」，报告答「结论：**是** —— 存在因果影响」。
这是一句关于世界的断言，而内核算的是 `nx.has_path`——在**用户自己画的那张图
上**，从原因到结果有没有一条有向路径。图是用户给的，边也是用户给的，所以这个
「是」是把用户自己的输入回读了一遍，答案行却没说它立在哪张图上。

**根因**：不是「答案行漏了个限定词」。`questions.Question.settles` 早就把命题
写准了（"a directed path runs from the source to the target in this graph"，
句子里自带作用域），它的 docstring 甚至明写了纪律：命题要照着审这一类的验证器
写，读者被告知的命题就是内核检查的那个命题。但 `settles` / `fails` 是**零消费
者**的英文串（语言闸口把它们登记成 `Wrote.UNREAD`）；读者看到的是
`analysis_report._VERDICT` 这张**手写的第二份**——`{"zh": "存在因果影响"}`，
作用域被抹掉了。**同一个命题两个作者，没有任何东西要求两者一致，而只有措辞较
差的那个有读者。** `effect` 那一对在一条目内部就已经不对称：假的那半写了「这
张图上」，真的那半只写「可识别」。

**修法**：

- 第二份作者**删掉**而不是改对（`_VERDICT`，55 行）；`settles` / `fails` 改成
  双语，10 个 kind × 两个值的作用域都写进命题**里面**，不当 caveat 挂在后面
  ——caveat 会被任何一个缩排的面丢掉，命题丢掉就等于丢掉答案。
- 闸口 = **渲染出来的那一行必须逐字包含声明的那个命题**（10 kind × 两值 ×
  两语 = 40 格）。改写成一句更好听的话当场就不匹配，不管改得对不对——「复述」
  这个动作本身是被禁的，不是「复述得不准」。
- 浏览器那份复述是**必须存在的**（它 import 不了 Python），于是从「只钉键集 +
  `answersIt`」升级成**逐串相等**：键集和 flag 早就钉住了，词是在它们底下漂
  的。为此把 `—— 数值还没算出来` 移出词表——它是关于这次渲染的事实，不是关于
  问题的，而且写在 10 条里的 2 条上、对 8 条都成立。

**度量**：cause 的答案行 `结论：**是** —— 存在因果影响` →
`结论：**是** —— 图里存在一条从原因到结果的有向路径（支持路径 1 条）`，
英文面同时出现。逐串相等这一步当场报出三处漂移：`identify` 的浏览器句子比内核
少了「该效应」/ 英文用的是另一个句式，`probability` 与 `effect` 把渲染备注吃进
了命题。`response_rendering.md` 的 `structural_result.value` 那一行也补上了
「陈述命题，不要转述它」。

基线：6397 → **6440 passed / 150 skipped**。mypy clean（137 个源文件）；
`tsc -b` 通过。

**方法论沉淀**：(250)**一个命题有两个作者时，先看哪一个有读者**——纪律写在没人
读的那一份上等于没写。判据不是「两份现在说得一样吗」（今天一样明天就不一样），
是「有没有任何东西要求它们一样」。删掉一份是最优雅的修法；删不掉的（跨语言的
那份）就把相等本身立成闸口，**逐串而不是逐键——漂移总是发生在已经钉住的那个轴
的下面一层**。

### #422 披露是每族手写一次的调用，于是「没人接线」和「没东西可披露」长得一模一样（2026-08-22）

**现象**：10 个族声明了函数形式假设，却没有机制审核块。台账上有那一行
（「这个数字依赖一个假设出来的函数形式」），但**没有任何一处说它是哪一个形式、
用什么方法拟的、谁定的**。读者拿到警告，拿不到要审的东西。front-door
就是其中一个：它声明 `logit_outcome_regression`，而任何面上都没有
「结局模型用的是 logit 链接，系统选的」这句话。

**根因**：这个披露是**每族手写一次的调用**，所以在读者面上，「没人接线的族」
和「本来就没有形状要披露的族」完全一样——**沉默的方式就是什么都不发生**。
只把那 10 处补上会留下同一个机制：第 11 个族明天加进来还是沉默的。

**修法**：

- 24 处写 `numeric_estimate` 的地方现在 24 处都问一遍（原 14），而**要不要出现
  由块自己决定**：声明了 FORM id 就出现，没有就返回 `None`。饱和插值的族
  （general_id / transport）不出现，**那是真答案，不是缺失**。
- 真正的闸口在 `augment_assumption_ledger`——**每个数值答案都要过的那一个漏斗**：
  声明了形状却没有块，当场报错并点名是哪个 `method` 声明的。
- 于是**全量测试套件成了普查**：漏掉的那一个族（transport）是被这条闸口报出来的，
  不是靠读 24 个调用点数出来的。

**度量**：front-door 之前 `extensions` 里只有 `assumption_ledger`；现在多一个
`mechanism_audit`，说 `frontdoor_logistic` / `logistic` /
`logit_outcome_regression` / `default`；调用方传 `model="logistic"` 就变成
`caller_asserted`。接线点 14 → 24，与 `numeric_estimate` 写入点 1:1。

基线：6391 → **6397 passed / 150 skipped**。mypy clean（137 个源文件）。

**方法论沉淀**：(248)**opt-in 的披露里，「没人接线」和「没有东西要披露」
在读者面上是同一个样子**——沉默的方式就是什么都不发生，所以它不会把自己报出来。
判据：这个披露是「每族写一次」还是「一处问所有族」？补齐当前的 N 处不算修好，
那只是把下一次沉默推迟到第 N+1 个族。(249)**闸口放在所有族都必须经过的那一个
漏斗上，测试套件自己就是普查**——不需要写一份族名单（名单会漂），
6397 条测试跑过的每一条路径都在替你数。

### #421 「谁定的函数形式」这个事实不是缺的，是被算出来后扇掉的（2026-08-22）

**现象**：机制审核块的 `provenance` 在 14 个接线点全是硬写的
`"default"`，摘要因此对每一族都说「系统按样本量自动选择」。TMLE
**根本没有 `model=` 参数**，这句话是在叫读者去传一个不存在的参数；
scm_counterfactual（线性 SCM）、proximal（矩阵求逆）、measurement（混淆矩阵）
同理——它们的形状就是方法本身。

**根因**：这个事实**不是缺的，是被丢掉的**。包里有 10 处把调用方的
`model=` 解析成具体形状的代码，每一处在路上都算出了答案——`auto` 就是
系统选的，其余就是调用方命名的——然后**每一处都只留下形状**。事后又
找不回来：解析出的 `"logistic"` 和调用方写的 `"logistic"` 是同一个字符串。
而那 10 处里有 7 处还是**同一句解析**（bool 就 logistic、否则 linear）在 4 个
模块里用七种写法各写一遍——与 #417 的 `to_numpy(dtype=float)` 同型。

**修法**：

- `themis/estimation/form.py` 是那一处决定：`outcome_form` 交出（形状，来源），
  `chosen_by` 只答后半（给那三处问题不同、答案结构相同的解析）。
- 每个带 `form` 的估计量同时带 `form_provenance`；形状固定的族把
  `Provenance.INHERENT` 写在常量旁边，解析的族在构造时填。
- 接线点不再传 provenance，改成**问估计量**；`build_mechanism_audit` 的
  `provenance` **没有默认值**——忘了就在调用点报错，而不是四层之下渲出
  一句读者得不相信的话。
- `ledger.provenance_named` 是那一处强制转换（`stamp` 里那份内联副本并进去）。
- 摘要的来源句改成统一走 `provenance_word`，那句写死的「按样本量」没了——
  它本来只对 dose_response 一族成立。

**度量**（同一块数据、同一个 backdoor）：

| 调用 | form | 点估计 | 块里的 provenance |
|---|---|---|---|
| 默认（`auto`） | logistic | 一样 | `default`（估计器默认选择） |
| `model="logistic"` | logistic | 一样 | `caller_asserted`（你在问题里断言的） |
| `ate_estimator="tmle"` | logistic | — | `inherent`（方法本身要求） |

三种情况原来全都说 `default`。顺带暴露并更正一条测试：dose-response
那条断言的是 `"default"`，而它传的是 `model="linear"`——断言的是缺陷本身。

基线：6376 → **6391 passed / 150 skipped**。mypy clean（137 个源文件）。

**新登记**：台账**行**的 provenance 仍走 `answerable(id)`，它对每个函数形式 id
都返回 `inherent`——对 backdoor 跑出来的 `logit_outcome_regression` 是假话。同一个
id 在 tmle 是 inherent、在 backdoor 是 default，所以 **provenance 不是 id 的属性**，
`answerable(id)` 从原理上答不了这个问题。

**方法论沉淀**：(246)**一个事实被算出来后扇掉，和一个事实压根不存在，
从下游看一模一样**——都是「这里没有信息」。判据不是往下游找，是往上游问：
**有没有人在某一处已经算出过它？** 找法是扫「解析 / 归一化 / resolve」这类函数，
逐个问它们除了返回值之外还知道什么。(247)**一个字段在 N 个接线点写同一个
字面量，就是这个字段问错了对象**——接线点不知道答案，才会 N 个人猜同一个。
该问的是那个知道答案的对象，而“它答不上来”本身就是缺口。

### #417 尺度词表说不出「档之间没有大小」，而该听的那一处根本不存在（2026-08-22）

**现象**：三个渠道编成 0/1/2，和「0..10 次就诊」声明得一模一样。
把三档渠道当混杂因素放进 backdoor logistic，真值 ATE = +0.1000，
算出来的是 **−0.0158——符号是反的**。披露面上有一行
`multi_level_covariates_entered_as_ordered_numbers` 在说这件事，但它只能
当免责声明读：读者无路可走。

**根因**：两件事各缺一半。**（a）词表缺成员**——`scale` 只有
binary / discrete / continuous，而「档之间有没有大小」**数据永远说不出**：
0/1/2 和一个计数是同样的字节，所以它只能是人声明的，不可能是推断出来的。
**（b）没有地方听**——就算能说，「把这些列变成设计块」这个决定
**不存在于任何一处**：它是 8 处 `df[list(adjustment)].to_numpy(dtype=float)`
的隐含结果。那不是一次转换，是**一句断言**——“每一列都是一个量，
所以第三档到第一档的距离是第二档的两倍”——写成 dtype cast 就不像断言了，
所以八处各写一遍、一处也没记录自己写过。

**修法**：

- `scale` 加 `nominal`（＝discrete ＋「无序无间距」）。多出来的那句数据
  证伪不了，所以**核对时完全按 discrete 走**，`observed_scale` 也没有这个成员——
  没有任何一列能显示它。
- `conform` 对 nominal 列**不编码**，直接放成无序 Categorical；标签一路带到
  设计矩阵，于是 #420 那条「数据说位置、程序说标签」的冲突在这条路上根本不产生。
- `declared.design_terms` 成为那一处决定，`design_block` / `design_widths`
  是它的两个读法；15 处设计构建改走它（backdoor / aipw×2 / tmle /
  dose_response / joint×2 / dispatch / iv×4 / mediation×2 / longitudinal /
  outcome_error / regression_calibration）。
- 契约新增 `quantity_columns`：估计量说出「哪几列我要当数读」（20 处接线）。
  没有大小的列当处理 / 结局 / 工具变量→**具名拒答**，而不是四层之下
  一句 `could not convert string to float: 'b'`。
- OVB 的逐协变量 partial R² 推广成**块** partial R²（qF/(qF+dof)，q=1
  时恰好等于原来的 t²/(t²+dof)）——因为 `2 + adjustment.index(cov)` 是
  把「名字里的位置」当成了「设计矩阵里的位置」。
- front-door 删掉一条**假话**：它其实早就把中介 one-hot 了，却仍向读者声明
  「这一列被当成一个有序的数进模型」。
- 词表里那条假设改成**指出出路**：声明 `scale: "nominal"`，这条假设随之消失。

**度量**（n=40000，三档非单调混杂）：

| 声明 | 点估计 | 偏差 | 台账里的有序行 |
|---|---|---|---|
| 真值 | +0.1000 | — | — |
| `discrete` | −0.0158 | −0.1158（符号反） | 有 |
| `nominal` | +0.1031 | +0.0031 | 无 |

基线：6355 → **6376 passed / 150 skipped**。mypy clean（136 个源文件）。

**方法论沉淀**：(243)**「一个事实能被说出来」和「这个事实有人听」是两件事；
只加词表成员、不建那一处听的地方，成员就没有消费者**。判据：问「这个事实
要改变的那个决定，今天写在哪一行」——如果答案是「写在 N 份一模一样的 dtype
cast 里」，那这个决定就不存在。(244)**一个新成员会把「原本不可达的状态」变成
可达，于是原本没人走过的路会第一次被走**——nominal 处理列以前不可表达，
加进来当天就是一条裸 traceback。加词表成员时要先问：这个新值能到达哪些角色，
每个角色都答得上来吗？(245)**一个量可能不再是一列**——一旦协变量能展开成
k−1 项，所有「按位置读系数」的代码都错了，而它们不会报错，只会指向另一个变量。

### #416 机制审核陈述了一句话，而系统的其余部分说的是 id——于是唯一那次去重看不见它（2026-08-22）

**现象**：同一条假设在台账里出现两次，两次的**层**和**严重度**还不同。
dose_response 最刺眼：`[作废级] 识别 LinearDML 假设 Y = θ·T + g(W) + ε…` 与
`[扭曲级] 函数形式 engagement 的函数形式为 linear（LinearDML 假设 Y = θ·T…）`
并排列着，摘要按前者数成「**4 条一旦不成立、整条因果结论作废**」——把「曲线
是不是直线」算进了「结论作废」那一栏。**条数错在夸大的方向上。**

**根因**：`mechanism_audit.mechanisms[].assumption` 装的是**手写的一句话**，而
系统里其他每一条假设通道装的都是**词表 id**。一句话什么都问不出来：问不出它是
词表哪一行，所以台账把 `functional_form` 硬写在代码里；问不出它复述的是哪条
声明，所以台账**唯一那次去重**（键是 `id`）看不见它。

**为什么是根因不是表象**：重复不是某个估计器的失手。凡是句子复述了已声明 id
的族必然重复；凡是句子讲的是**路线**而不是形状的族（measurement×3 / selection /
causation / counterfactual_cell / proximal），硬写的 `functional_form` 必然错层。
两个症状都从「该说 id 的地方说了句子」这一个表示选择掉下来。

**改法**：块**指向**已声明的 id，不自己陈述。`assumption: str` →
`assumptions`，且**不新增字段**——`build_mechanism_audit` 从估计器已有的 flat
`assumptions` 里取词表判为 `functional_form` 的那一层。于是：

- **16 个 dataclass 上的 `model_assumption` 连同 10 段手写散文整个删掉**，
  dispatch 14 处 5 行长写并成 `_attach_mechanism_audit(result, est, target=…)`；
- 机制命名的 id **按构造**是 flat 表的子集，去重必然生效，不靠测试去保证；
- 选择按「层」而不是按「谁记得写句子」，**漏不掉任何一族**；
- 一条形状假设都没声明的估计器返回 `None`，块**缺席而不是为空**——「我没有
  假设函数形式」本来就不该作为一条假设登记（#344 判过这个形状），而路线本来
  就在推导链上。

**中途撞上的第二个作者**：让机制条目沿用块自己的 `provenance`（恒为
`"default"`）会让**同一个 id 有两个答案**——有机制块的族里是「估计器默认选择」、
没有的族里是「方法本身要求」。这是关于**接线**的事实，不是关于假设的事实，而
`ledger.py` 自己写着「A producer may not choose the provenance of an estimator's
assumption」。改成和其余通道一样问词表；`Provenance.DEFAULT` 的真正写入者登记
为 #421。

**闸口**：`tests/test_the_shape_choice_points_at_a_declared_assumption.py`（18
条）。判据不是「没有 id 出现两次」——旧条目**根本不带 id**，claim 又是把词表句
子套进一个框，**按 id 查和按 claim 查当年都会通过**。能抓到的是
`test_no_assumption_is_disclosed_twice`：**台账行数必须等于各通道声明的不同事
物之和**，一条「复述了但没说复述谁」的条目把这个数顶高一。反例是按旧形状**重建**
出来的，测试里现场造给闸口判（`test_the_criterion_rejects_the_ledger_this_defect_produced`）。

**顺带**：kernel 里 45 条单语句子随散文一起消失（#390/#395 的债务表 14 个模块下调，
`tmle` / `ctf_conjunction` / `scm_counterfactual` 归零）。

**同时登记的两条**：#421（机制块 provenance 14 处硬写、对 7 个形状固定的族是假话）、
#422（frontdoor / joint / mediation / four_way_ratio / iv / longitudinal /
missing_recovery 七族声明了函数形式假设却没有机制审核块——接线仍是手写的，
所以「选择按层不会漏族」这句话今天只在已接线的 14 处成立）。

基线：6340 → **6355 passed / 150 skipped**。mypy clean（136 个源文件）。

---

### #420 帧被改成了声明的编码，程序还在用标签说话——于是「编码不一致」被报成了「数据不够」（2026-08-22）

**这是 #414 自己的缺口，落在 #414 的测试没覆盖的那类列上。**

**现象**：同一份数据两种写法，同一个问题。
- `where` 写成文字（`"office"` / `"remote"`），声明 `domain: ["office","remote"]`，
  查询 `intervention.value = "remote"` →
  `bounds_results: []`、`numeric_estimate: None`、**`estimator_failure: null`**，
  报告的答案行是「当前**还不能给出答案** —— 缺口与补法见下方「数据缺口」」。
- 同一份数据手工编码成 0/1、声明 `[0,1]`、查询 `value=1` → `manski_natural` 照常给出。

**根因**：`declared.conform` 把**帧**重编码成声明域里的位置，而**程序**仍用标签称呼那些
档。`_eq(codes, "remote")` 一行都不匹配，每条臂都是空的。全仓有 135 处拿程序里的值去比
数据里的值，它们**同时**失配——所以这不是某个估计量漏了分支，改任何一处都不解决。

**为什么必须以拒答结束，而不是让它降级**：**「这条臂没有行」是一个合法状态**——那正是
一条真的没被观测到的臂的样子。于是没有任何估计量能把两者分开，而「哪些量数据供不出来」
恰好是这个系统存在的理由。#414 之前带标签的列会以 `DataContractError` 结束，至少指名了
问题；#414 之后它安静地变成一份「数据不够」的报告——**把一个编码不一致伪装成一个数据
缺口**。correctness 没变坏，honesty 变坏了。

**判据是 AST 自己的形状，不是查询种类的清单**：一个「档」永远写在称呼它那一列的原子
旁边——`{"atom": …, "value": …}`（干预、grounded atom、观测），
`{"variable": …, "value": …}`（反事实事件）。`levels_named` 按这个形状遍历，于是
**新增一种带档的查询种类只要写成同样的形状就自动被覆盖**，写成别的形状会在测试里
当场失败。这条形状同时精确地排除掉程序上唯一那个「不是档」的 `value`——`probability`
语句的那个是 [0,1] 里的一个数，旁边没有自己的原子；而它的 `target` / `given` 里的
grounded atom 会在往下走的时候被找到，两次都对。测试
`test_every_schema_shape_that_carries_a_level_is_the_shape_this_reads` 把这条判据
钉在 schema 上。

**明确声明的取舍：这不是最优解，最优解需要 #417。**
- **正解**是让编码根本不逃出设计矩阵：帧一路保持标签，只有建设计矩阵那一步编码，
  程序和信封里永远不出现位置。它需要 `kernel_ast.schema.json` 里那个还不存在的
  `scale` 成员（#417）。
- **「把程序也重述成编码」不是正解**，而且是个陷阱：验证器和生产者都各自从
  `query_dict` 独立推导界的符号表达式（`bounds_rules.verify_manski_natural_bounds_result`
  与 `output/bounds.py`），两边会**一致地**变成 `P(where=1)`——**读者面上那个 `1` 是
  用户从来没写过的东西**。那是用一个可见缺陷换掉一个静默缺陷，不是修复。
- **本刀做的**：`conform` 只在「程序没有用标签称呼这一列的任何一个档」时才重编码，
  否则以 `DataContractError` 结束并指名怎么办（把列按声明域的顺序自己编成 `[0,1]`，
  domain 也声明成 `[0,1]`，程序里那些档改用对应的数）。**代价：带标签的处理列 /
  结局列今天仍然用不了**，只是失败从「安静的假数据缺口」变回「响亮的、带办法的拒答」。
  #414 打开的那条路（带标签的**协变量**）原样保留，这是它能覆盖的全部。

**#414 的中心断言因此需要更正**：commit 里说「labels and codes now yield the same
point estimate and the same data_hash」——对**协变量**为真，对**程序称呼过档的列**为假。
`test_the_encoding_does_not_decide_the_answer.py` 只测了协变量。

基线：6330 → **6340 passed / 150 skipped**。mypy clean（136 个源文件）。

### #415 问的是对照，答的是一条臂——被问的那个量在信封上根本不存在（2026-08-22）

**现象**：`remote → productive` 且两者有未测共因，问「远程办公会不会提高效率」。
点识别被阻断，报告落到界通道，答案区写着：

> 给出**区间** [0.3593, 0.848]——干预到所问的那一档之后，目标事件发生的概率
> （部分识别的界，不是点估计；method=`manski_natural`）。

而它上面的问题行写的是「估计 **干预 remote=True** 对 **productive=True** 的**因果效应**」。
**两行各自都对，合起来是答非所问**：`effect` 查询问的是**对照**
P(Y|do(X=x)) − P(Y|do(X=x'))，答案给的是**单臂**风险。读者会把那个区间当成效应的区间。

**根因不在措辞，在于被问的那个量没被算出来。** `bounds_results[].estimand` 是
schema:2457 上一个**只有一个成员**的枚举（`arm_probability`），能说出对照的槽位只有
`contrast`——而四个方法里**只有 `balke_pearl_iv` 填它**。`bounds_numeric.py` 的模块
docstring 把「Where the ACE is defined it is still reported」写成模块政策，这句话对
`manski_natural` 是假的：二值处理下 ACE 一样有定义，只是没人算。于是渲染层无论怎么
措辞，手上都只有另一个量。

**这一条不是一个实例，是一整条通道**：每一个落到界通道的 effect 查询都是这样，
唯一的例外是二值处理下的 Balke-Pearl。

**改法**：`_natural_ace_contrast` 把对照算出来。**无假设模型下它是 sharp 的，而且是
相减得到的**——两条臂的未观测质量分别是 `X≠x` 那群人的 `Y(x)` 和 `X=x` 那群人的
`Y(x')`，互不相交、互不约束，所以两区间里任意一对点都能同时取到，**区间之差就是差之
区间**。这正是 Balke-Pearl 不能走的那一步（响应型多面体把两臂绑在一起），也是它为什么
要跑第二次优化。处理和结局的基数都不进这个论证：`Y=y` 是个事件，每条臂的松弛在整个
off-arm 质量上自由。

**顺带得到一句这份报告里最有价值的话**：这个宽度是
`P(X≠x) + P(X≠x') = 1`，**在任何数据集上恒等于 1**。[−1,1] 里被排掉了一半，而且
**再多数据也不会更窄**——这是关于假设的定理，不是关于样本的事实。测试
`test_the_width_is_one_whatever_the_data_look_like` 跨 3 个种子 × 3 种处理分布把它钉住。

**代价：验证器得能独立重算它**，所以 `sufficient_statistics` 加第四个计数
`n_joint_other_arm`（无条件记录——它是关于数据的事实，而「有没有基准臂」是关于处理
基数的事实）。`_rederive_manski_natural_contrast` 从这些计数重推两个端点，另外单独
断言宽度为 1——那是关于模型的定理而不是计数里的恒等式，所以一个用别的路子算出这个
区间、宽度却不是 1 的生产者会被抓住。

**具名例外：`manski_tamer_monotonicity` 不报对照，而理由不是 ACE 没定义。**
MTR 把 `Y(x)` 与 `Y(x')` 在个体层面绑在一起，两臂不再彼此自由，相减只得到 valid
但一般不 sharp 的区间；而这个方法没有多面体可以跑第二次优化。**valid 但不 sharp 不
是没有价值，问题是信封上没有任何字段说一行区间是哪一种**——今天界通道每一条都是
sharp 的，把第一条不 sharp 的混进去、还不作标记，就是本条缺陷换了张脸：一条区间的
强度要靠读者从方法的名声去猜。已登记为 #419。

**闸口**：`_MAY_REPORT_CONTRAST` 把「哪些方法可以带 contrast」变成声明，验证器据此
拒收任何**没有规则能重算**的对照；生产者侧一份 AST 普查
（`test_every_numeric_bounds_method_reports_the_asked_quantity_or_says_why_not`）要求
每个数值端要么报对照、要么带理由具名在 `_NO_CONTRAST_AND_WHY` 里，第三条
（`test_the_producers_exemption_is_the_one_the_verifier_refuses`）要求两边恰好互补，
免得一边停报、另一边照收。

**登记更正——原条目的三个现象里只有这一个是 kernel 缺陷**：
- 「问中介答总效应」不是缺陷：复现用的 AST 编码的就是 `effect(X→Y)`，问题行如实写着
  「因果效应」，答案行给的正是它。落差在自然语言→AST 那一步，而 AST 是调用方对问题的
  陈述。
- 「结构性『是』说成事实」不是答非所问：`_VERDICT[CAUSE]` 说的正是 `cause` 查询问的
  那个命题，#313 的 `verdict_is_the_answer` 已经把这件事做成了表。它另有一个真问题
  ——那个「是」是把用户自己画的边回读一遍，答案行没说它立在哪张图上——但那是**溯源**
  缺口，根不同，已另立 #418。

基线：6303 → **6330 passed / 150 skipped**。mypy clean（136 个源文件）。

### #414 尺度是声明出来的，而两处做决定的地方都在从存储格式猜它（2026-08-22）

**现象一**：一份 1200 行的投放数据，`channel` 三个渠道写成文字（搜索 / 社交 / 邮件）——
业务数据最常见的一种列。`themis.estimate` 以 traceback 结束：
`DataContractError: column 'channel' has dtype object which is neither bool-like nor numeric`。

**现象二**：同一份数据，`channel` 改成 0/1/2，**不崩**，走 `backdoor_logistic` 给出
**+0.0549**，真值 **+0.0167**（三倍）。因为一个**三档名义变量以一个有序的数**进了
logistic：第三档到第一档的距离被当成第二档的两倍。信封上只有
`logit_outcome_regression`，**没有任何一句说这件事**。

**根因不是「契约太严」，是判据答错了问题。** 契约把「这列能不能进模型」回答成
「这列的 **dtype** 是不是 bool 或数值」——判据是**存储表示**，问题是**测量尺度**。
两个现象因此是同一个错误的两面：存储是 object 就判「不能用」（尽管它是完全可用的
三水平名义列），存储是 int64 就判「能用，而且能当数用」（尽管是同一列）。
**于是编码方式决定了答案**：同一个变量换个写法，一次是估计、一次是 traceback，
两个结果都不是关于数据的陈述。

**尺度早就声明过了**，而声明只到达了一个**只做报告**的消费者：
`{"kind":"variable","predicate":"channel","domain":[...]}`，`dispatch:7254`
的 `_declared_scale` 已经把它解析成 `discrete`，供
`_attach_type_reconciliation` 报告不一致。**没有任何做决定的地方读它。**
顺序更能说明问题——诊断在 `dispatch:318`，契约在 `:217`，所以文字那一帧上，
本来能给用户有用信息的那个诊断**根本没机会跑**。

**改法：声明在「程序还在作用域里」的那一步应用一次。** 新增
`themis/estimation/declared.py`：`conform(program, data)` 把带标签的列按**它自己
声明的域顺序**编码，`validate_data` 之前跑；下游 40 处 `validate_data` 调用看到的
已经是符合声明的帧，一处不用改。契约对**没声明任何东西**的列保留原有 dtype 判据——
所以这是**加一条路线**而不是改一条，既有程序逐字节不变。`_declared_scale` 与
「哪些取值落在声明域外」两处判据并进 `declared.py`，因为现在有两个消费者
（诊断报告它、编码依据它），两份读法能让诊断放过一帧而紧邻那步拒收它。

结果是这个 ticket 本身：**文字帧与整数帧现在给出同一个点估计、同一个 `data_hash`。**

**明确声明的取舍：一次性编码（one-hot）是更好的修法，本刀不做。**
`kernel_ast.schema.json:866` 的 `scale` 只有 `binary / discrete / continuous`——
**没有一个成员能说「这些档之间没有大小」**。于是三个渠道和一个 0..10 的就诊次数
声明得一模一样，按 `discrete` 一律 one-hot 会把一种静默误设换成另一种（给一个计数
变量造 14 个哑变量）。one-hot 需要的那个判断，**接口层今天表达不出来**——这正是
#363 已经定过的那一类：接口不可表达 > 检测并报告。

所以本刀**如实披露**：新假设 id
`multi_level_covariates_entered_as_ordered_numbers`（`Layer.FUNCTIONAL_FORM`），
由 **9 个按列建设计矩阵的估计量**各自声明（backdoor / ipw / aipw / tmle / joint /
mediation / frontdoor / 2SLS / dose-response），**分层路线不带这一行**——它切格，
不做这个假设。**代价：那个估计仍然是偏的（+0.0549 vs 真值 +0.0167），只是读者
现在被告知了。** 这条不是保守提示，测试 `test_and_the_estimate_really_is_off_by...`
把偏差本身钉住，免得日后被读成「只是谨慎」。

两条边界都是判据的一部分：**两档不带这个假设**（一个指示变量无论哪两个标签都是指示
变量，没有次序可假设）；**连续协变量也不带**——一个量以一项进模型正是
`linear_outcome_regression` 已经说的事，量的次序和间距是它自己的，在这里再报一次
会把真正要紧的那种情形埋掉。「有没有档」这个判断直接用 #412 `support.py` 已经定
下来的那一条（≤ `MAX_LEVELS` 且每档至少 2 行），因为「这列能不能切成层」在这里
是同一个问题。

**顺带修掉的两件事**：`reference_data`（同一个程序描述的第二帧）也走 `conform`——
一个入口成形、另一个不成形，是同一个缺陷换个更小的爆破半径，不是更小的缺陷；以及
`_dtype_kind` 里 `pd.api.types.is_categorical_dtype` 的弃用告警，它一直没响过，
**因为带标签的列在到达这个诊断之前就被契约结束了**——告警是随第一帧走到这里的数据
一起来的，这本身就是证据。

**两条既有闸口在全量里各拦下新模块一件事**，都拦对了：语言闸口发现
`declared.py` 的拒收句是单语的（改成双语句表，模块因此不进欠账清单；同一表面上
`contract.py` 那七句仍是单语、仍在册，它们该一起动，属 #391）；`envelope_scalar`
同一性闸口发现它被写成了函数内 import，于是模块属性上没有它——提到模块级。

基线：6283 → **6303 passed / 150 skipped**。mypy clean（136 个源文件）。

**留在后面的一件事**：`scale` 需要一个「档之间没有大小」的成员；有了它，one-hot /
饱和分层才是程序**授权**的决定而不是猜的。那是下一条 charter。

### #413 E-value 的「解读」读的是点估计，而该读的是区间端点——两处重复实现同病（2026-08-22）

**现象**：一份 90 行的投放数据，Themis 给出 ATE **+0.087**，95% CI
**[−0.014, +0.202]**——**区间含 0，什么都没证明**。同一份结果的敏感性分析写着
「解读：**比较稳健**——混杂要相当大才解释得掉」。区间靠近零那一端的 E 值是
**1.00**：能解释掉这个结果的，是那个平凡到不存在的混杂。**证据越弱，结论喊得越响。**

**根因不是「阈值挑错了」，是「档」在代码里根本不是一个东西。** 一次估计产出**两个**
E 值，它们回答的不是同一个问题：点估计上的 E 值问「多强的混杂能把**估计值**推到零」，
区间靠近零那端的 E 值问「多强的混杂能把**结论**拿走」。「这个结果稳不稳」问的是后者，
而档只是四段字符串字面量的副作用——`if e_point < 1.5 / elif < 2.5 / elif < 5.0 / else`，
**写了两遍**，一路一份。于是「该按哪个数判」这个问题在结构上无处可问，也无处可改；
两份拷贝还保证了任何修正只会修一半。

**两个缺陷叠在一起，才让这条读法够不着。** 区间端点算了、印了，然后不参与结论；而
`_closer_to_null` 对**任何跨零区间返回 `None`**——于是恰恰在不显著的那些结果上，
连可回退的端点都没有，档只能落回一个区间已经没能把它和零分开的点估计。

**改法：档升为对象。** 一张 cut-point 表 + `band_for(e_point, e_ci) -> (band, basis)`：
有区间端点就按它判，没有才回落到点估计，并且**把判据一起返回**——需要先知道规则
才能知道自己被告知了什么的读者，没法发现规则错了。两个 formatter 都调它，四分支链归零；
`1.5 / 2.5 / 5.0` 在模块里各只作为字面量出现一次，由测试钉住。

**判据本身也修了**：跨零区间返回 **0.0** 而不是 `None`——区间离零最近的那一点**就是**零，
那里的 E 值是 1，这是关于估计的事实，不是缺了输入。顺带，点估计不再是这个函数的入参：
一个区间离零最近的点是关于区间的事实。两份独立转写（`dispatch.py` 与 `verify.py`）
在同一个提交里改。

**词离开散文。** `interpretation_band`（fragile / moderate / substantial / very_robust）
与 `band_basis`（ci_bound / point）成为信封字段，进 schema、进词汇表、进 gloss、进浏览器。
`note` 从此只讲换算，不讲结论——**同一个档说两遍就是可以自相矛盾的档，而散文那份谁也
复核不了**。三条后果：验证器现在**独立重算这个档**（它是这一块里唯一一个到达读者、
却没有任何东西复核的部分）；主报告和浏览器**在两种语言里都能说出这条结论**，而
`note` 是在 kernel 里生产的、生产时还不知道谁在读，只能有一种语言；`sensitivity.py`
的单语欠账 **17 → 0**，从欠账表整行删除。

**新闸口的反例已构造**：`test_rejects_a_reading_taken_off_the_point` 递给验证器的不是
一个瞎编的档，而是这一块**在旧规则下本来会带的那个档**——点估计的 3.414 落在
`substantial`，端点的 2.366 落在 `moderate`。

基线：6252 → **6283 passed / 150 skipped**。mypy clean。前端已 `pnpm build`。

**留在后面的一件事**：`dispatch.py:3666` 一带，敏感性分析用的是 bootstrap 区间而不是
弱工具下的 Anderson-Rubin 集——换一个区间是关于估计量的主张，不是关于标签的，另立
charter。

### #412 逐层 positivity 从来没被量过：三处说的是「每一层」，三处查的都是别的东西（2026-08-22）

**现象**：一份 4000 行的投放数据，`channel` 有三个渠道，第三个渠道**从未投放过广告**
（1003 行，全是未处理）。Themis 给出 ATE **+0.1911**，95% CI **[+0.1642, +0.2215]**，
真值 **+0.0625**——错了三倍，且区间离真值很远。同一份结果的假设台账里写着
「重叠 / positivity：调整集**每一层内两个处理臂都有样本**」。更极端的完全分离
（channel 0 全投、channel 1 全不投，真实效应恰为 0）给出 **−0.1445**，CI
**[−0.1616, −0.0874]**，**排除 0**，台账同样声明 positivity 成立。

**根因不是「忘了写检查」，是判据的作用域错了一级。** 检查写了：
`backdoor.py:134` / `aipw.py:377` 的 `len(observed_levels) < 2`。但它问的是
**处理列在整份样本上有没有变化**，而 g-formula 要求的是**每一层内有没有变化**。前者是
后者在 z 上的求和——只要有**任何一层**两臂齐全就为真，因此对「另一层缺臂」结构性
失明。这不是「能力没建」：同一仓的饱和路径 `binary_do_risk.py:278` 查的正是逐层判据
并拒答。是同一个概念存在两份**不同作用域**的判据，而回归侧那份接错了级。

**同一个错误一共有三处，都是「定义写的是层、实现查的是代理」：**

| 说的 | 查的 |
|---|---|
| 台账 `positivity_overlap_of_treatment_arms`：「每一层内两个处理臂都有样本」 | 无条件声明，从不核对 |
| 估计量守卫：注释写 positivity | 处理列的**边际**取值数 |
| `GapKind.PROPENSITY_OVERLAP_VIOLATION` 注释：「every confounder stratum has both treated and untreated units」 | **拟合**倾向分数是否离开 [0.05, 0.95] |

第三处最能说明问题：拟合模型会跨层平滑，那个**经验投放率恰为 0.000** 的层拿到的拟合
倾向是 **0.09059**——舒舒服服落在阈值内。于是 25.1% 的样本落在从未投放的层里，而这条
本来就该管这件事的缺口**一次都没开火**。AIPW/TMLE 声称由 Winsorize 兜底也是同理失效：
下限 0.01 作用在同一个拟合值上，`n_trimmed == 0`，`propensity_clipped_to_floor_` 这条
假设根本不会出现。

**改法：一份表回答三个问题。** 新增 `themis/estimation/support.py`——调整集划出的层里，
哪些同时持有两个臂。拒答的守卫、声明假设的那一行、披露外推的那条缺口都读它，于是它们
对同一帧不可能各说各话。`measurement` / `selection` 各自持有的 `_MAX_LEVELS = 20`
（「这列还有没有层」的判据）并进这里，避免出现第三份。

**停止点定在零，不是定在阈值。** 部分层缺臂时估计**照常给出**——回归调整本来就是干这个
的——但台账那行换成
`positivity_violated_some_strata_hold_one_arm`（仍是 `_ID` 层，仍是**作废级**：答案回来了
不等于警告可以说得轻些），缺口点名**是哪几层、占样本多少**。而**没有任何一层持有两臂**
时拒答（`no_within_stratum_contrast`）：那时公式需要的每一项都由结局模型产出，给它配一个
置信区间等于给模型的意见配置信区间。阈值会是发明出来的数；零不是。

**顺带发现并修掉的既有缺陷**：后门策略**没有遵守级联自己的约定**——
`except EstimatorFailure → refusals.record → blocked(...)`。兄弟路径
（ipw / aipw / tmle，`dispatch.py:6057`）一直遵守。因此 `backdoor.py` 的边际守卫从写下
那天起就是**以 traceback 冲出 `themis.estimate`** 的，从没到过 `estimator_failure`——
没有任何测试走过这扇门。

基线：6236 → **6252 passed / 150 skipped**。mypy clean。

**留在后面的两件事**（都已核实为真空，不在本刀射程）：调整集连续时没有层可数，那条
「每一层」的措辞对它本就不成立，而今天仍照发——那是措辞的事，属 #416 一族；以及验证器
今天拿不到数据，要独立复核这条只能靠记录充分统计量（`rules.py:3838-3945` 的分层 Wald
是现成先例）。

### #405 第七刀：支撑边界上的「一对物种」其实是三件事实，中间那件谁都说不出（2026-08-22）

**做了什么**：`overlap_insufficient` 的 13 处与 `insufficient_support` 的 15 处并排
读了一遍，按注册表自己那条判据分组——**缺的是行，还是差异？**——13 处分成三堆，中间
那堆拿到自己的名字 `no_within_stratum_contrast`（`Kind.DATA`，带两门语言的句子）。
`transport.py:241` 与 `binary_do_risk.py:279` 改为委托，自写句子棘轮 `STILL_AUTHORED`
111 → **109**。

**为什么是三件而不是两件。** 注册表原来把这条界写成一对：

> The line between them is WHAT IS MISSING: rows, or a difference.
> ……A column at a single level **and a stratum holding one arm** are this, not the one above

那句话是为裁决一个归属歧义而写的，它裁对了，却把两件事实塞进了一个名字。对读者它们
是两回事：

- **一列在整份样本里不变** → 没有任何地方能估，读者的动作是去拿数据；
- **一层里有行、只有一个臂** → 它周围的层两臂齐全，回归会拿那些层的斜率把这一格补
  出来，并给出一个数。

第三件才是估计量必须能自己说出口的那件——因为**只有它是「拒答和出数都站得住」的
情形**。默默选了出数的估计量，等于替数据说了它没说过的话。

**这一刀是 #412 的硬前置。** `overlap_insufficient` 没有句子（46/74 有），13 处全部
自写，而闸口 `test_a_species_with_no_sentence_and_no_message_is_refused` 逐字断言
`"overlap_insufficient" not in refusals.SAYS`。于是 #412 要填一条拒答只有三条路：自写
（棘轮 111→112，反方向）、委托一条自己新写的句子（该物种便同时有自写与委托，
`STILL_TWO_AUTHORS` 1→2，反方向）、或者**先把这件事实拆出来**。第三条让棘轮往正确
方向走了两格。

**顺手修的两处，都是同一条路径的两半互不认识：**

- `refusals.describe` 没有 Mapping 分支。信封侧的 `_occasion` docstring 逐字写着
  「A stratum arrives as `{column: level}`」，句子侧却让 dict 掉进 `list(value)`——那
  只迭代键。`{'channel': 2}` 到读者手里是 `['channel']`，**取值静悄悄没了**。仓里三个
  估计量各自手写过一份层渲染（`_render_given` / `_json_key` / `dict(zip(...))`）；它们
  不得不自己写，就是同一件事的另一面。
- `describe` 的溢出串是 `"3000 values (e.g. …)"`——**英文**，而它运行在一个有语言的
  句子里。四个取值就够触发：`treatment_not_binary` 的中文句子此前会印「取值是
  4 values (e.g. 0, 1, 2, ...)」。语言闸口看不见它，因为这串是运行时拼的，这也正是
  「改成符号」而不是「翻译它」才是解法的原因。改完之后这类泄漏对**所有**调用者一次
  性消失。

**同时更正的物种归属（#408 类，第五、六例）**：`binary_do_risk.py` 两个守卫都填
`insufficient_support`，而按注册表自己的线，`:265`（整列没有这一臂）是
`overlap_insufficient`，`:279`（这一层没有这一臂）是新物种。一个函数的两个分支是两件
事实，此前共用一个名字。

基线：6226 → **6236 passed / 150 skipped**。mypy clean。

### #409 拒答有两扇门，而闸口只看着一扇（2026-08-22）

**根因**：`test_no_species_is_raised_both_ways`（「一个物种一个作者」）的分母是
**一扇门**——它只扫 `EstimatorFailure`。拒答到达信封还有第二扇：`refusals.block`
直接把块写到结果上。两扇门加起来 193 个抛出点，闸口看见其中 176 个的一部分。

**代价已经发生**，而且是这条线自己造的：

| 物种 | 走句子表 | 自己写 |
|---|---|---|
| `cause_or_effect_not_binary` | `binary_do_risk.py:233` | `runtime/scheduler.py:2968` |
| `no_identifying_design` | `dispatch.py:4062` | `dispatch.py:4744` |

第二行的两处**都是 #408 第二刀本会话写的**，当时全套测试是绿的——因为新写的那处
走的正是没人看着的那扇门。补这两处而不改分母，第三处照样进来。

**扫描器还有三个洞，一并补上**：

1. **三元表达式看不见**。`failure_type=(Refusal.A if cond else Refusal.B)` 的第一个
   参数不是 `Attribute`，旧扫描器记成 `"<computed>"`。#408 第二刀的 `_refuse_
   without_back_door` 正是这个形状，于是它**一次都没被计入**。改成扫子表达式。
2. **先选后抛看不见**。`regression_calibration.py:240` 把三元赋给局部变量 `ftype`
   再抛。改成解析同文件里绑到 `Refusal.X` 的局部名。
3. **关键字调用看不见**。旧扫描器要求 `node.args` 非空，于是
   `EstimatorFailure(failure_type=..., message=...)` 这种**全关键字**的调用整个不存在。
   `dose_response.py` 有 6 处是这个形状，其中 5 处自写句子——**从来没有被数过**。
   这是自写棘轮从 105 跳到 112 的主要来源：不是新增的债，是一直在那儿没被看见的债。

**新增两条闸口**：

- **每条句子至少有一处能说出它**。一个物种如果每处都自己写，它在 `SAYS` 里的句子
  就永远到不了读者——而它照样通过「两门语言都有」「槽位对齐」这些检查，于是安静地
  和那些本该收敛到它的抛出点越漂越远。今天唯一一条：`no_first_stage`（`STILL_UNSPOKEN`）。
- **转发点被数着**（`FORWARDED = 5`）。`EstimatorFailure(exc.species, ...)` 这类抛出点
  文件里读不出物种，上面所有闸口都管不到它们。数量钉死，让这个盲区保持已知大小。

**修好的一处**：`scheduler.py:2968` 改成走句子表。它自己的注释本来就写着「和数据端
是同一个物种、同一个理由」——那就该是同一句话。丢掉的是 `{role}`（"cause"/"effect"）
这个示意词，留下的是**读者自己起的列名**，后者才是能拿去查的那一半。

**没修的一处，以及为什么**：`dispatch.py:4744` 那行在物种的事实之外，还多说了一句
真话——「点估计仍然成立，缺的是精度代价，不是点」。**那句话不属于这个物种**，它属于
「这一行跳过了结局误差评估」。而今天没有任何槽位让一个抛出行在物种的句子之上加自己
的一句。做一个这样的槽位是解法；借物种的嗓子说它不是。登记在 `STILL_TWO_AUTHORS` 里。

自写句子棘轮 `STILL_AUTHORED` 105 → **111**（分母修正 +7，修好 −1）。
`scheduler.py` 单语欠账 52 → 51。基线：6221 → **6226 passed / 150 skipped**。

### #405 第六刀：一个 `if` 里两件事实，其中一件借了另一件的名字（2026-08-22）

**做了什么**：`treatment_not_binary` 的 7 处、`outcome_not_binary` 的 4 处自写句子
折成物种自己的两句；联合 general-ID 那处的守卫拆成两条，第二件事实拿到自己的名字
`treatment_levels_differ`。自写句子棘轮 `STILL_AUTHORED` 116 → **105**，六个模块的
单语欠账同步下调（`general_id.py` 10 → 4，`four_way_ratio.py` 2 → 1）。

**11 处里 10 处是同一句话抄了 10 遍。** 两个物种各自只有一件事实——这个估计量做的
是两个取值之间的对比，而它面前这列有这些取值——而 10 处各写各的：

> `treatment {t_col!r} has {len(t_levels)} observed levels …`（general_id ×2）
> `measurement-error correction needs a binary treatment {name!r}; …`
> `selection-backdoor recovery needs a binary treatment {name!r}; …`
> `treatment {treatment!r} must be binary 0/1 over its observed values; …`
> `the proximal ATE entry takes a binary treatment (two observed levels); …`

每一处都把「几个取值」和「哪些取值」插进散文里，而 `details` 里本来就该装它们。
折完之后读者拿到的是「{treatment} 在数据里的取值是 {levels}；这个估计量做的是两个
取值之间的对比，只接受二值处理」，两门语言各一句。proximal 那处此前**根本没说出列名**
（只有 "observed X levels = …"），折完反而多了一样东西。

**第 11 处不是这件事实。** 联合 general-ID 的守卫是

```python
if len(level_sets) != 1 or len(next(iter(level_sets))) != 2:
    raise EstimatorFailure(Refusal.TREATMENT_NOT_BINARY, …)
```

一个 `or` 底下两件事实：**处理们不共享同一个取值集**，或者**共享的那个集不是一对**。
第一件跟「二值」没有关系——`a ∈ {0,1}`、`b ∈ {0,2}` 两个都是二值的，
而「所有处理同时取同一个取值」这个角点仍然没有定义。照旧那句话读，调用者会去找
一列有三个取值的处理，找不到。拆成两条，第一条是新物种 `treatment_levels_differ`
（kind 仍是 UNBUILT：v1 声明的范围就是共享一对），第二条才是 `treatment_not_binary`，
而它此时的 `{treatment}` 是全部处理——它们是同一列的形状。

**这条守卫此前一个测试都没有**（`grep` 全仓：`treatment_not_binary` 的 7 处断言里没有
一处走联合入口）。两条分支各补一条，第一条就是拆分前必然失败的那个反例。

**声明的取舍**：`four_way_ratio` 原句尾部带一条路由提示——"Use the difference-scale
four_way_decomposition for a continuous outcome"。折进物种句子后它改走
`details["use_instead"]`，即**只到信封、不到任何渲染面**。这与 #405 第一刀、#403
是同一笔交易，理由也一样：比例尺需要风险、差值尺不需要，这是读者绕过拒答的路，
但它是这一次的事情，不是物种的定义。

基线：6215 → **6221 passed / 150 skipped**。

### #405 第五刀：一句话抄六遍，另一句话说的是别人的定义（2026-08-22）

**做了什么**：`missing_column` 的 7 处自写句子折成物种自己的一句；
`exposure_not_binary` 的 2 处改归 `states_incomplete`（并让它说出读者的列名）。
自写句子棘轮 `STILL_AUTHORED` 125 → **116**，`general_id.py` 单语欠账 16 → 10、
`measurement.py` 35 → 33。

**`missing_column`：7 处，其中 6 处是两句话各抄了三遍。**

> `treatment column {t_col!r} not present in the data`（×3）
> `outcome column {y_col!r} not present in the data`（×3）

第 7 处（`missing_recovery`）说「data is missing required columns: {missing}」，
而它交给 `details` 的是 **`treatment=treatment`——不是缺的那些列**。一句话就够：
「数据里没有 {columns} 这些列，而查询点了它们的名字」。角色（treatment / outcome）
留在 `details` 里，读者拿到的是列名本身。

**`exposure_not_binary` 的两处说的是第三个物种的定义。** 它们写着

> observed exposure values … are **not covered by** the declared exposure states

而 `states_incomplete` 的定义就是「数据里出现了声明的状态表没有的取值，校正会
悄悄丢掉它们」。`exposure_not_binary` 的事实是另一件——**这项校正只做二值暴露**。
`states_incomplete` 此前只服务结局通道，句子里写死了「结局」；改成说出**列名**，
两个通道都能用，而且对读者更好：那是他自己起的名字。

**顺带暴露的一件事**：`test_exposure_multi_level_refuses` 造的是「数据里有第三个
取值、声明只有两个」，断言 `exposure_not_binary`——**它从来测的就不是那个物种**。
真正测 `exposure_not_binary` 的是它下面那条（声明三个状态）。测试改名为
`test_an_exposure_level_the_declaration_omits_refuses`。

**没做的，以及被闸口挡下的原因**：`no_first_stage` 的 6 处本来也要折——一个事实
（工具变量没有推动处理），五种统计量作见证。改完跑测试，
`test_no_species_is_raised_both_ways` 说不行：**一个物种不能一半走句子表、一半自己
写**，否则同一个拒答会以两种措辞到达两个读者。而这 6 处里有 2 处在
`solve_hansen_from_s` / `solve_overid_from_moments` 里——**矩条记录（moments）是
验证器不 import 生产者、独立重算所依据的契约，它有意只装数字、不装列名**，那里
抛出的拒答说不出 `{instruments}` 和 `{treatment}`。要么 4 处失去读者的列名（倒退），
要么为了措辞去改一份契约。**这是契约问题，不是措辞问题**，整段回滚，登记。

基线：6213 → **6215 passed / 150 skipped**。

### #405 第四刀：四个抛出点填的是甲物种，写的是乙物种的定义（2026-08-22）

**做了什么**：`insufficient_support` 与 `overlap_insufficient` 之间的 4 处填反，
按各站点**自己那句话**改正。两个物种的 `says` 补上彼此的边界。

**这一对的分界是「缺的是什么」：行，还是差异。**

- `insufficient_support`：识别公式要求和的某个格子**没有行**——违反 positivity，
  这个和就不是估计量。**格子在公式里，不在数据里。**
- `overlap_insufficient`：变量 / 臂 / 采样点**没有可对比的差异**——行是有的，
  它们不变。

四处填反，每一处都能从它自己的措辞判出来：

| 站点 | 它自己写的 | 原填 | 改为 |
|---|---|---|---|
| `bounds_numeric.py` | 「a variable that **never varies**」 | insufficient_support | overlap_insufficient |
| `response_polytope.py` | 「an instrument that **never varies**」 | insufficient_support | overlap_insufficient |
| `joint.py` | 「**Positivity is violated outright**」 | overlap_insufficient | insufficient_support |
| `transport.py` | 「source data has **no observations with** stratum …」 | overlap_insufficient | insufficient_support |

**测试里也已经有这个区分了，只是没落到物种上。** transport 那两处是一对姐妹测试：
`test_transport_positivity_violation_surfaces_structured_failure`（**标题就写着
positivity**）和 `test_transport_one_armed_stratum_is_a_positivity_finding_...`，
后者的 docstring 明写「它的姐妹——一个一行都没有的层」——**两条测试认得这两个事实，
两条都断言了同一个物种**。

**没有为这一条加闸口，理由写在这里**：能把四处都揪出来的证据，是「这句话描述的是
哪个物种」——那正是物种本身存在的意义，没有比读它更机械的判据。语法上也切不开：
`transport.py` 两支都是「某个计数等于 0」，一支是层里没有行（positivity），一支是
层里只有一条臂（没有对比）。所以这一刀留下的是**把边界写进两个 `says`**，让下一个
人在填的时候看得见分界，而不是一条会在 #391 把措辞搬走之后自动失效的文本闸口。

**顺带量出、登记为后续**：`overlap_insufficient` 现有 13 处里其实压着**第三个事实**
——「采样点附近有行，但不够」（`dose_response` 的两处：DRLearner 分箱后
`c < 5`，以及 `_check_overlap` 的带宽内邻居 < 5）。这跟「一行都没有」和「不变」都不
一样，读者的下一步也不同（「x=100 附近只有 3 行，需要 5 行」是**加数据就能解决**的，
而且它说得出在哪）。这一刀不动它：新开一个物种要先把「空 / 稀 / 无对比」这三分想清楚，
不是顺手做的事。

基线不变：**6213 passed / 150 skipped**。

### #408 第三刀：四个物种量的是调用方自己声明的东西，却告诉读者「换批数据就行」（2026-08-22）

**做了什么**：四个物种从 DATA / UNBUILT 改判 REQUEST，并从枚举的 DATA / UNBUILT
段落移进 REQUEST 段落。#408 普查登记的四条，这一刀清掉三条，外加查证过程中冒出的
第四条。

**判据是 REQUEST 自己的定义**：「调用方给的请求或输入**格式不对，或与数据不相容**；
改一处再试。」而 DATA 的定义是「结构允许，**这一份样本**支撑不了……换一批数据就行」。
混淆矩阵、潜变量基数、误差方差、处理向量——**全都是从参数传进来的**，再多的行也不会
改变其中任何一个。

| 物种 | 原 kind | 现 kind | 它量的是 |
|---|---|---|---|
| `singular_confusion_matrix` | DATA | REQUEST | 调用方给的矩阵的行列式（5 处） |
| `degenerate_reliability` | DATA | REQUEST | 调用方声明的 σ²_u 对上数据里的方差 |
| `proxy_cardinality_mismatch` | DATA | REQUEST | 声明的 k 对上观测到的层数 |
| `not_a_joint_intervention` | UNBUILT | REQUEST | 入口拿到的处理向量长度 |

**决定性的证据是仓库自己已经答对过一次。** `degenerate_reliability` 的判据是
「声明的 σ²_u ≥ Var(V|rest)」；它在**结局那一侧**的孪生是
`outcome_error_exceeds_residual_variance`——

> the declared outcome error variance exceeds the residual variance in the data
> — **the declaration contradicts what is there**

——kind 是 **REQUEST**。同一个判断，两份记录，两个答案。这不是「哪个对」的争论，
是漂移。

`not_a_joint_intervention` 是另一种错法：UNBUILT 的意思是「Themis 还没建这一种」，
而**单处理的情形恰恰是建了的**（那是 back-door 那条路）。另外查证了它的可达性——
dispatch 在 `len(set(treatment_atoms)) < 2` 时就 `blocked('combination_out_of_scope')`
返回了，**这个物种走 dispatch 到不了读者**，只有直接调估计器的程序员会看到它。
改 kind 因此是安全的，且对那个读者才是对的。

**闸口，以及它的边界**：DATA 的物种，其 `says` 里不得出现
`declared` / `supplied` / `the caller`。**这条读的是维护者写的散文**，所以它抓得住
「说了自己在量声明」的那些，抓不住不说的那些——而这正是它值得存在的理由：本轮四个
全都说了，就写在「换批数据会有用」这句承诺的旁边。边界写在闸口自己的注释里，不假装
它是完备的。

**顺带补的两处**：`not_a_joint_intervention` 的句子现在说出处理列的名字
（`general_id.py` 那一处手上就攥着 `treatment_atoms`，原来只交了个数）；渲染 prompt
的物种清单补上了第二刀新增的 `no_identifying_design`——**上一刀改了读者面能看见什么，
prompt 是那个面的一部分**。

基线：6211 → **6213 passed / 150 skipped**。

### #408 第二刀：五行代码都停在「没有 back-door 集」，其中四行没有资格说那句话（2026-08-22）

**做了什么**：`not adjustment_sets` 底下的两个事实拆成两个物种。新增
`no_identifying_design`（GRAPH），`requires_backdoor_identification`（UNBUILT）
收窄成它本来该说的那一半。第五处手拼块折成 `block()`，棘轮
`STILL_HAND_BUILT` 8 → **7**。

**这五行的分工原来是什么**：四个校正行（结局误分类 / 暴露误分类 / 双通道合并 /
回归校准）判 `if not adjustment_sets` 就填
`requires_backdoor_identification`——kind 是 UNBUILT，意思是「问题成立**且已被
识别**，Themis 还没建这一种」。**但这四行从来没看过效应是不是被别的路识别了**。
第五行（结局测量误差）看了全部三条路（back-door / front-door / 工具），自己的
散文写着

> P(y|do(x)) is here **neither back-door nor front-door identified and has no
> instrument**

——那是**一个关于图的结论**——然后把它填进了同一个 UNBUILT 物种。

**动手前先按同一条判据量**：预测「套件里那四条测试构造的都是 GRAPH 那一支」，
然后跑。四条全红，全部报 `no_identifying_design`。也就是说
**`requires_backdoor_identification` 在整个套件里，从来没有一次是按它自己声明的
意思触发的**——它的四个站点的测试，构造的都是一张既没有中介、也没有工具的图。

**补上从来没人构造过的那个 occasion**：X→M→Y 且 X<->Y——没有 back-door 集，但
效应**是**被 front-door 识别的。同样喂一份误分类矩阵，现在报
`requires_backdoor_identification` / kind=`unbuilt`；原来那张图报
`no_identifying_design` / kind=`graph`。两个 occasion 各有一条测试，读者拿到的
下一步也真的不同：一边是「换个数」，一边是「换张图或换个问题」。

**物种收窄之后能说得更多**。原来：

> {exposure} 对 {outcome} 的效应在这里**不是 back-door 可识别的**……

现在：

> {exposure} 对 {outcome} 的效应在这里**是可识别的，但不是通过 back-door 调整**；
> 而这项校正只接在 back-door 调整之上，所以没有给出校正后的结果。

**拆开一个物种，剩下的那半反而能说出更强的话**——因为它终于只对一种 occasion 负责。

**闸口**：`Refusal.REQUIRES_BACKDOOR_IDENTIFICATION` 在 `themis/` 里只允许出现在
**一个函数**里（`_refuse_without_back_door`）——即那个**同时看过 front-door 集与
工具候选**、因而有资格分辨的地方。让四个常数各自变对没有用，明天加第五个校正行
时它会自己再写一遍那个判据；**要让它回不来，得是这个问题只有一个回答者**。

**顺带被既有闸口挡下的一处**：辅助函数最初直接 `return blocked(...)`，
`test_no_handler_still_returns_a_bare_bool_or_none` 报了四行——它要求 handler 的
return 必须是四个 Claim 构造器之一、写在读得到的地方。这条要求是对的，于是分工改
成：**辅助函数只决定物种，Claim 由行自己说**。行声明的是「查询还在不在飞」，那是
级联的事；「是哪个事实拦下了它」才是必须只有一个作者的那件。

基线：6207 → **6211 passed / 150 skipped**。

### #408 第一刀：一个求解器没跑完，读者被告知「你的工具变量被数据否证了」（2026-08-22）

**根因假设**（先写再动，按纪律）：

- **现象**：`convergence_failure`（kind=BACKEND，「什么都没判定」）被一个**拟合之前**的
  检查抛出——它刚刚量完结局列、发现它是常数；`iv_model_refuted`（kind=GRAPH，
  「数据与任何 IV 模型都不相容」）被 `not (lo.success and hi.success)` 抛出。
- **根因**：`Kind` 声明在**物种**上，而物种是**症状**的名字（「这个条件成立了」），
  kind 是关于**病因**的断言（「这是谁的局限」）。一个症状只要能由多种病因造成，
  就没有哪个常数是对的。
- **为什么这是根因不是表象**：这两处不是两个填错的常数。逐个改常数只会换一批出错的
  occasion——`requires_backdoor_identification` 的 4 处正是这样（见下「没做的」）。
  真正共同的形状是**症状命名 / 病因断言**这条错位。
- **结构性修改**：**让站点问出区分病因的那个问题**，然后一个病因一个名字。这不是妥协——
  两处的区分证据**本来就在手上，只是被丢掉了**。

**做了什么**：两个新物种、一条闸口。

**其一：`outcome_does_not_vary`（DATA）**。`dose_response._check_outcome_variance`
在任何拟合之前跑，量的是结局列的相对标准差与极差。它抛的是 BACKEND——而 BACKEND
的读者面框架句说的是「没有对问题、图或数据下任何结论」。**它自己的 message 写着
「用户会读成'无效应'实为数据问题」**：站点知道自己判的是数据，物种说的是反话。
两个函数之下的孪生检查（处理列不动 → `overlap_insufficient`，DATA）从写下的那天
起就是对的，源码注释里那句「像退化的 T 已经做的那样」正是本该有的对称。
句子现在也说出读者的列名（`结局列 engagement 在这份数据里几乎不变`）。

**其二：`linear_program_failed`（BACKEND）**。`response_polytope._solve_response_lp`
读 `linprog(...).success`——**一个五值状态的二值影子**。HiGHS 只有 status 2
（不可行）是关于**模型**的陈述；1（迭代/时间上限）、3（无界）、4（数值故障）
是求解器在说自己没跑完。原来这四种全部被翻译成

> the observed P(X,Y|Z) table is incompatible with the IV model …
> Either the instrument is invalid (IV1/IV2/IV3 fail) or …

**这是错得代价最大的方向**：因为一个程序跑超了迭代数，读者被告知他的识别设计有问题。
现在两支程序**都**给出不可行证书才算否证——它们共享可行集（同样的等式约束、同样的
单纯形、相反的目标），所以否证是两支都能证明的事，而两支互相矛盾是求解器的事，
不是数据的事。

**闸口**（`tests/test_a_refusal_names_whose_limitation_it_is.py`，10 条）：

> **BACKEND 的拒答是一句引语，不是一次测量**——某个例程被调用过、并且说了它没有答案。
> 所以填 BACKEND 的站点手上必须有那份记录：要么它站在 `except` 臂里，要么它头顶的
> 某个 `if` 读了例程自己的判词（`status` / `success`）。

拿修改前的代码验过：扫 HEAD 的 `dose_response.py`，闸口**点名 424 行**、并且放过
四十行之上那个 `except` 臂。反例（把病灶的形状写成 fixture）另有一条。

第二处不泛化，也不需要：**全仓只有一处 `linprog` 调用**，所以事实钉在它自己的接缝上
——五个 status 里哪一个允许下那个结论，另外四个改做什么。

**声明的取舍**：`iv_model_refuted` 在**真·不可行**那一支仍然是 GRAPH，而它自己的
句子承认另一种读法（「小样本下这可能是模型边界附近的抽样噪声」——那是 DATA）。
统计意义上的否证本来就分不开这两者，除非再做一次检验。这一次不动它：GRAPH 是
可行动的那一读，另一读已经写在句子里了。**记在这里，是因为它是同一条根因的第三个实例，
只是这个实例的区分证据不在手上。**

**没做的，以及量出来的分母**：按同一条判据把 **70 个物种、218 个填写点**全扫了一遍
（`kind_audit_408.py` / `guards_408.py`）。除已修的两处外，还有四处站得住：

- `requires_backdoor_identification`（UNBUILT）4 处的判据是 `if not adjustment_sets`
  ——**分不出「图什么都给不出」（GRAPH）与「图给了 front-door 集、只是这个工具不吃」
  （UNBUILT）**；第 5 处（`dispatch.py:4729`）自己的文字说的就是前者。
- `singular_confusion_matrix`（DATA）判的是**调用方声明的**混淆矩阵的行列式——换多少
  数据都不会变；同一个对象的另一个校验器 `invalid_confusion_matrix` 是 REQUEST。
- `not_a_joint_intervention`（UNBUILT）在 `len(treatments) < 2` 时说「Themis 没建」，
  而单处理的情形**恰恰是建了的**。
- `proxy_cardinality_mismatch`（DATA）的一个判据同时读**声明的** cardinality 与
  **观测到的**层数。

`external_data_required` 与 `counterfactual_inputs_infeasible` 查过之后**撤回**：
前者读者的下一步确实是改调用（REQUEST 成立），后者已经先去掉单调性重跑一遍来分辨
「被否证的是假设还是工具变量」，是对的。

`dose_response.py` 的单语欠账 9 → **8**（被棘轮要求下调，不是我挑的数）。

基线：6193 → **6207 passed / 150 skipped**（+14：新闸口 10 条，另 4 条来自两个新物种
被既有的逐成员完备性闸口自动收进分母）。

### #407 两句话之间的那个空格，谁都没写——因为它不属于任何一句（2026-08-22）

**做了什么**：一门语言的标点从 `themis/output` 的三个渲染模块搬进
`themis.language`，报告的拒答框架句拆成浏览器一直就有的三段。新增闸口
`tests/test_a_language_joins_its_own_sentences.py`（11 条）。

**现象**：五条拒答框架句在英文下把两句话粘死——

> ...**No number — this is a conclusion about the causal graph**:
> the error it raised has no name in this build.**M**ore of the same data
> will not change it；

`{reason}` 之后直接接后半句，没有空格。

**根因不是「漏了五个空格」。** 模板长这样：

```python
"en": "**{lead} — {head}**: {reason}More of the same data will not change it."
```

`{reason}` 之后要不要有空隙，**在这个模板里没有作者**——它被默认成 payload
的义务（每条 reason 自己带尾部空格）。而中文根本不要这个空隙（`。` 天生贴住
下一句），所以**在唯一有读者的那门语言里五条全是对的**，没人往下看。

**同一件事，两个读者面用了两种模型**：浏览器的 `REFUSAL_KIND_WORDS` 一直是
`{lead, head, tail}` 三段、由 TSX 负责拼；报告写成一整条带 `{reason}` 的模板。
「怎么拼」在报告这侧于是无处安放。改法是让报告也变成三段
（`_kind_parts`）+ 一个框架（`_KIND_FRAME`）+ 一条语言规则
（`language.sentences`）。

**闸口第一次跑就在真实语料上说了「不」，而且比预期大得多**——它扫的是
「模块级 `Words` 表，其取值全部由语法标点构成」。手工先搬的只有 `_AND` 一张；
闸口在剩下的代码里又点出 **6 张**：

- `_SEMICOLON` 在 `analysis_report` / `data_gap_report` / `explainer`
  里**各有一份**；
- 而决定性的一格：`_FULL_STOP = {"zh":"。","en":". "}` 与
  `_END_OF_SENTENCE = {"zh":"。","en":"."}` 是**同一个标点的两个名字，且英文
  侧不一致**——一个把句间空格烘进了标点里，另一个没有。哪条渲染读到哪个名字，
  决定了它的下一句有没有位置。**一个有时候自带空格的句号，是没人能拿来组合的
  句号。**

**搬进 `themis.language` 的五张表**：`BETWEEN_ITEMS`（原
`analysis_report._AND`，被同一个模块引用 11 次，于是第二个拼列表的面无处可拿）、
`BETWEEN_SENTENCES`（此前**不存在于任何地方**，这就是本条的病灶）、
`BETWEEN_CLAUSES`、`BETWEEN_STATEMENTS`、`FULL_STOP`（空格从中剥离）。加两个
组合器 `listing()` / `sentences()`——后者**丢掉空段而不是绕着它拼**：没有
occasion 可报的拒答是「一句接一句」，不是「一句、一个空隙、一句」。

**为什么 `BETWEEN_ITEMS` 与 `BETWEEN_CLAUSES` 是两张表**：中文用 `、` 分列表项、
用 `，` 分小句，英文两处都写逗号。**在一门语言里重合的两个事实仍然是两个**，
并成一张会让这个区分在需要它的语言里不可表达——而那正是本仓第一门语言。

**顺带的加固**：`_kind_parts` 拆出来之后，
`test_the_browser_tells_the_reader_what_the_report_tells_them` 从「浏览器的三段
是报告那句话的子串」升级成**逐段逐语言相等**。此前只能问子串，是因为报告那侧
只有一整句，三段「在里面某处」就是能问的全部。先量后改：5 kind × 3 段 × 2 语言
= **30 格逐字节相同**，等号是量出来的，不是要求出来的。

**边界（闸口第一版比它该管的宽）**：初版判据是「取值全是非词字符」，于是把
`_META_SEPARATOR`（`／`）和 `_FOOTER_SEPARATOR`（`　·　`）也算了进来。这两个
不是语法标点，是**这份报告**为自己的版式选的记号，另一个面选别的记号也不算错。
它们身上属于语言的只有**宽度**（全角 `／` 对 `  /  `、表意空格对两个 ASCII
空格），那比这一轮深一层。判据因此收窄成一张明写的 `GRAMMAR` 字符集
（`、，；。,;.` 与空格）——**豁免必须说得出自己豁免的是什么**。

基线：6182 → **6193 passed / 150 skipped**（+11 = 新闸口）。

### #405 第二刀之二：一句话抄了四遍，四遍都把读者的列名写成了字母（2026-08-22）

**做了什么**：`requires_backdoor_identification` 的 4 处手拼块折成物种自己的
一句话，抛出点交出两个名字（`{exposure}` / `{outcome}`）。棘轮
`STILL_HAND_BUILT` 12 → **8**。

**这 4 处此前的样子**：三处**逐字相同**——

> confusion-matrix correction composes with back-door standardisation, but
> **P(y|do(x))** is not back-door identified here; no corrected number is produced.

第四处（回归校准）只差两个词：「composes with back-door **adjustment**」和
「no corrected **slope** is produced」。

**真正值得记的不是重复，是那个 `P(y|do(x))`。** 四处都把效应写成**字面的
x 和 y**——读者手上是 `smoking` 和 `cancer`，报告里印的是两个字母。这不是
措辞粗糙：**抛出点手上有 `x_atom` / `y_atom`，它只是没把它们放进句子里**，
因为把值插进散文这件事本来就没有一条路可走（f-string 里插一个变量，与句子
本身长在一起，正是 #391 的病）。**句子归物种所有之后，「插进去的是什么」变成
了一个具名槽，于是它自然变成了读者的列名。**

现在（zh）：

> **smoking 对 cancer 的效应**在这里不是 back-door 可识别的，而这项校正接在
> back-door 调整之上，所以没有给出校正后的结果。

**声明的取舍**：第四处的「slope」并成了「结果」。回归校准校正的是一个系数、
不是一个风险，这个差别在物种层面不成立——而**哪个估计量在说话已经写在块的
`estimator` 字段上**。代价：回归校准的读者少看到一个「斜率」字样。

**没做的一处，以及顺着它量出来的更大一件事**：同物种的第 5 处
（`dispatch.py:4729`）**物种记错了**。它自己的文字说「既非 back-door、也非
front-door，也没有工具」——那是**一个关于图的结论**（`Kind.GRAPH`），而
`requires_backdoor_identification` 的 kind 是 `UNBUILT`（「问题成立**且已被
识别**，Themis 还没建」）。

顺着查下去发现的不止是「这一处填错了」：

**这个物种的 kind 本来就是逐次的。** 它底下有两个约束——图给不出 back-door 集
（图的事实）、这项校正只会 back-door（工具的事实）。图若还有 front-door 集，
绑住读者的是**工具**（UNBUILT 对）；图若什么都没有，绑住的是**图**（GRAPH 对）。
一个物种一个 kind 表达不了。

**而实测下来，判不判得了这件事，取决于抛出点手上有什么：**

| 抛出点 | 拿得到 | 记的 kind |
|---|---|---|
| 本刀折的那 4 处 | **只有 `adjustment_sets`** | UNBUILT |
| 第 5 处 `_try_outcome_error_declaration` | `adjustment_sets` + `front_door_sets` + `iv_candidates`，且三个都查了都没有 | UNBUILT |

**唯一有资格说 GRAPH 的那一处说了 UNBUILT；其余四处什么都无从判断，却在信封上
宣称「问题已被识别」。** 这个断言是从一个支撑不了它的位置做出的——而它今天之所以
无人察觉，正是因为 kind 不是抛出点写的，是物种替它写的。全部归 **#408**。

**基线（本条）**：6181 → **6182**（+1：`SAYS` 多一句，按它参数化的闸口自动多守
一条——与上一条同一个机制）。`dispatch.py` 的单语欠账 84 → **80**：**这个数不是
我改的，是棘轮自己要求下调的**——全量跑出来 `test_the_debt_is_exactly_what_it_says`
报「down to 80 — lower the number here」。四句折成一句，欠账正好少四条。

**方法论沉淀**：(242)**一句抄了 N 遍的话，值得看的往往不是「抄了 N 遍」，是
「这 N 遍共同回避了什么」**。四处都写 `P(y|do(x))`，而四处手上都有真实列名——
共同回避的是**把值放进句子**这件事，因为当时唯一的做法（f-string）会把句子和
语言一起焊死。所以「重复」是症状，「没有具名槽」是病；折成一句的收益里，**读者
看到自己的列名**比「少了三份副本」大得多。判据：并列读这 N 份副本，问它们**一致
地没说什么**，而不是问它们哪里不一样。

### #405 第二刀之一：一个物种的私有数据长在了所有物种共享的块上（2026-08-22）

**接上一条留的那个具体问题**：13 处手拼块里有一处（`dispatch.py:3962`）之所以
必须手拼，是因为**唯一的门造不出这个字段的全形**——schema 把 `estimator_failure`
声明成 7 个属性（`additionalProperties: false`），`block()` 造 4 个、`stamp()`
发出时补 `kind`，剩下 `external_data_needed` / `recovery_formula` 没有门造得出来。

**根因不是「给门补两个参数」。** 那两个属性的 schema 描述**自己写着**「§S9.1
`external_data_required` only」——它们是**一个物种的私有数据，长在了所有物种
共享的块上**。而且：

- **同样两个事实已经在信封的 `extensions.selection_recovery` 块上**，由
  `runtime/scheduler.py` 写；
- **读者读的是那一份**：报告的 `_route_selection_recovery` 和浏览器都从
  extensions 取；
- **`estimator_failure` 上的这一份一个写入者、生产侧零读者**——浏览器的
  `types.ts` 把这个块声明成 `{estimator, failure_type, kind, reason}`，**连字段
  名都没有**；报告、explainer、`Verdict.tsx`、`stamp()` 也都只读那四个键。

**唯一读它的是一条测试**（`test_wired_no_reference_refuses_biased_number`），
而这一点比「零读者」更值得记：那条测试的 docstring 写着「拒答要**说出**账本
要求的外部数据」——这是个对的断言，**但它钉在了副本上**。所以那份副本不是没人
在乎，是**唯一在乎它的人钉错了地方**：真正写着这件事、且两个读者面真正读的，
是 `extensions.selection_recovery`。断言已改到那里，语义一字未变。

这与 #338（`estimated_from_data`：一个写入者、零个读者、schema 里没有）是同一
形状，只是这次 schema 里**有**，所以它把「不完整」的责任推给了构造器：门造不
出全形，看起来像门的毛病。

**改动**：从 schema 删掉这两个属性（按文本编辑，不走 json round-trip）、把块
描述里指向它们的那半句改成指向 `extensions.selection_recovery`（「这个块说的是
为什么没有数，不是什么能产出数」）、`dispatch.py:3962` 去掉那两行并改走
`block()`。棘轮 `STILL_HAND_BUILT` 13 → **12**。

**代价**：生产侧为零。信封少两个键，而它们复述的事实原封不动留在原处；那条
测试的断言搬到事实所在处，语义不变。

**基线（本条）**：6181 → **6181**（不增不减：改的是一条既有断言的取值处）。

**方法论沉淀**：(240)**一个「通用构造器造不出全形」的抱怨，先查缺的那部分是不是
根本不该在这个形状里**。判据有两条，都很便宜：①schema 的字段描述里有没有
「only when …」这类话——那是这个字段在说自己只属于某一支；②这个字段有几个
读者——生产侧零读者且事实在别处已有，就是一份重复记录，而不是构造器的缺口。
反过来补进构造器，是把一份重复记录固化成契约。
(241)**「有一条测试读它」不等于「它有读者」——要看那条测试钉的断言，属于哪一份
记录**。这里唯一的读者是一条测试，而它要钉的事实（「拒答说出了要什么外部数据」）
在别处也成立、且那才是两个读者面真正读的地方。**一份重复记录会把钉它的测试
一起变成重复记录的一部分，于是删起来像是在削弱覆盖**——实际上只需要把断言搬到
事实所在处。判据：这条断言换个取值处还成立吗？成立就是搬，不成立才是覆盖损失。

### #405 第一刀：拒答有两扇门，#391 只修了一扇（2026-08-22）

**先更正登记条目。** #405 写的是「9 个物种各自带着不止一个事实，要拆」。逐条
量下来那句话是对的，但它**不是根因**，而且它解释不了同一批数据里更醒目的
一件事：**13 个物种一个 `raise` 都没有，却在被用。**

**根因**：`estimator_failure` 这个信封字段有**两个作者**。

| 门 | 处数 | 谁写的句子 | #391 的闸口够不够得着 |
|---|---|---|---|
| `raise EstimatorFailure(...)` → dispatch 捕获 → `refusals.record()` | 174 | 构造器从 `SAYS` 组句（#391 已建） | 够得着 |
| `dispatch.py` 里手拼 `{"failure_type": …, "reason": …}` | **23** | **调用点当场写散文** | **结构上够不着** |

23 处**全部**就地写散文，**没有一处**的物种在 `SAYS` 里有句子，其中 **8 个
物种只走这条路**——它们从来不经过 `EstimatorFailure.__init__`，所以那道
「没句子就 `ValueError`」的闸口对它们一句话也说不上。这同时解释了三件事：
为什么 13 个物种零 raise 点、为什么我数了三轮的分母（171→125）从没包含这
23 处、以及为什么「把物种拆细」不管拆到多细都修不了它们。

第二层更要命：**`refusals.block()` 自己收的 `reason` 是一个成品字符串**。
它的 docstring 自称「拒答在信封上的唯一形状」，实测 4 个调用者，而 23 处
绕开了它——**但即使那 23 处改成调它，句子仍然归调用点**。所以「并成一扇门」
必须同时把组句一起接过去，否则只是换了个地方写散文。

**这一刀做了什么**：`block()` 的 `reason` 变可选，缺省时从 `SAYS` 组句，
用与构造器**同一道**闸口（没句子且没给 `reason` → `ValueError`），并在这一
侧也对 `details` 做 `_occasion` 强转（一个没有异常可抛的调用者，此前是绕过
那次强转直接上信封的）。然后把 23 处里**同属一个事实的 10 处**改走它。

**那 10 处里有一个读者可见的真错。** 它们是同一件事：
`except (ValueError, KeyError[, TypeError]) as exc:` 接住了一个**没有人分过类**
的异常。其中——

- **7 处**记成 `invalid_input`，它的 kind 是 **REQUEST**，浏览器渲染成
  「需要你改一处输入 …… 改掉之后重跑即可」。
- **3 处**在**完全相同**的位置、接**完全相同**的异常类型，记成 `unknown`
  （kind=BACKEND：「这没有对问题或数据设计做出任何判定」）。

一个事实两个名字，名字由**谁写的这个 handler** 决定（方法论 231 的又一例）。
而这次两个名字不是并列的：其中一个**把责任判给了用户**——7 处让读者去改一个
可能完全没问题的输入，而真相是没有人知道它为什么失败。10 处现在统一记
`unknown`，`str(exc)` 移到 `details.diagnostic`。

**声明的代价**：`details` 今天**不到任何读者面**（报告和浏览器都不渲染它），
所以异常原文从此只在信封 JSON 里。这是有意的——它是维护者的文字，不是读者
的句子——而且与 #403 两次提交前在 web 边界做的是**同一个取舍**。代价是：拿
报告排查的人现在要去翻信封才看得到异常原文。

**闸口**（`tests/test_a_refusal_reaches_the_envelope_one_way.py`，8 条）：
`block()` 组句 / 物种无句子且无 `reason` 时拒绝 / 这一侧也强转 numpy /
`unknown` 那句**不许**插进任何 occasion 的值（含 `{}` 检查——「不知道为什么」
的句子里塞一段 stack trace，读者会当成答案）/ 手拼块的棘轮
`STILL_HAND_BUILT = 13` / **dispatch 里凡是没接住 `EstimatorFailure` 的
`except` 分支，写上信封的物种只能是 `Refusal.UNKNOWN`**（AST）+ 它的反例。

**剩下的 13 处不动，理由要说清**：它们是**估计量还没跑就决定的拒答**（识别
块已说不可识别、前置条件不满足），每一处陈述一个**自己的**事实；其中**一处**
（`dispatch.py:3962`）还带着 `block()` 不产出的额外键（`external_data_needed`
/ `recovery_formula`）——schema 把 `estimator_failure` 声明成 7 个属性、
`additionalProperties: false`，其中 4 个由 `block()` 造、`kind` 由 `stamp()`
在发出时补，**剩下 2 个没有任何门造得出来**。所以「它为什么手拼」有一个具体
答案：唯一的门造不出这个字段的全形。把
它们并进来需要为 7 个物种写句子，而其中 `not_identified` 的唯一用法是纵向
序贯可交换性——**物种名比它的唯一事实宽得多**，那正是 #405 登记的「要拆」，
要动 schema 的 70 项 enum。两件事混在一刀里，两边都验不了。

**另一处登记不动的**：`themis/runtime/scheduler.py:2968` 调 `block()` 却自写
句子，而它的物种 `cause_or_effect_not_binary` **有**句子——只差一个 `{role}`
槽（「cause 还是 effect」）。这是第三种形态的同一笔债：不是手拼字典，是
`block()` 的调用者自己写 `reason=`。加 `{role}` 要同时改数据端
（`binary_do_risk` 同物种），归下一刀。

**顺手撞见并登记（#407）**：给 `unknown` 写句子时才发现，拒答的框架句在
**英文侧没有接缝**——`_kind_words` 五个模板都是 `"…**: {reason}This decides
nothing…"`，填进一个以句号结尾的 reason 就渲染成 `"…here.This decides…"`。
中文不需要空格，所以这个缺陷在唯一有读者的那门语言里看不见。根因不是哪条
reason 忘了带尾空格——那是把「连接」推给 607 条 payload；是模板把连接表达成了
payload 的义务。已实测复现，未修，登记为 #407。

**基线（本条）**：6172 → **6181**（+9 = 8 条新闸口 + 1）。多出来的那 1 条是
机制在生效：`test_a_refusal_says_one_thing_in_every_language` 按 `SAYS` 参数化，
`SAYS` 从 36 句变 37 句，闸口自己多守了一句——**给物种写一句话，它的检查是
自动带上的**。

**方法论沉淀**：(238)**一个字段有几个作者，要按「谁写进去」数，不能按「谁
声明拥有它」数**。`block()` 的 docstring 明写自己是唯一形状，而它是二分之一
——把 docstring 当量测，会让另一半永远看不见。判据：对这个字段做一次赋值点
普查（AST 找 `X["field"] = ...` 与所有构造它的调用），数出来的作者数才是真的。
(239)**「一个事实两个名字」不总是对称的——先问这两个名字有没有一个在替读者
判定责任**。`invalid_input` 与 `unknown` 都能装下「估计量炸了」，但前者附带
一句「去改你的输入」。找法：把候选物种的 `kind` 摊开，看有没有哪个 kind 对
读者提出了要求。

### #404 的说法要更正：键集有闸口，形状没有（2026-08-22）

**先更正登记条目。** #404 写的是「浏览器内部的复述没有闸口——`TIER_META`
有三个作者、两个已漂」。两处都不成立：

- **作者是两个不是三个。** `AnswerTier` 到达读者只经过 kernel 的
  `analysis_report._TIER_WORDS` 和浏览器的 `TIER_META`。扫出来的另外两处
  （`Verdict.tsx`、`dispatch.py`）是我正则的假阳性——命中的是组件自己那张
  通用词表里的「区间 / 无」，不是按 tier 成键的表。
- **「已漂」是历史不是现状。** 那两次漂移（`STATUS_LABEL` 多了 kernel 不发的
  `unidentifiable`、少了它确实会发的 `outside_language`；`GAP_TITLE` 只覆盖
  36 个 kind 里的 28 个）已由 #317 / #394 修掉**并且建了闸口**：
  `test_the_browser_states_every_value_of_the_vocabulary` 对全部 20 个词表
  双向钉键集，`test_the_browser_has_a_word_for_every_member_in_every_language`
  钉每个成员在每门语言下都有词。

**真缺口在这两道闸口下面一级。** `_ITS_OWN_RENDERING` 里的三张表
（`TIER_META` / `STATUS_META` / `REFUSAL_KIND_WORDS`）不复述 kernel 的词，
它们**自己写**——所以它们被免检。免检的判据是「持有一个结构而不是一个串」，
而**形状被读出来只用来决定免检，读完没人再看它一眼**：`_browser_word` 从结构里
取出 `label` 就返回了。两道现存闸口看的都是**语言键在不在**，看不到**这门语言
下的字段齐不齐**。

**根因**：豁免的判据（持有结构）和豁免带来的义务（结构在每门语言下相同）本是
同一条规则的两半，只写了前一半。`StatusMeta.blurb` 在类型里是可选的，
`STATUS_META` / `REFUSAL_KIND_WORDS` 的键类型又是 `Record<string, …>` 而不是
各自的词表联合——TypeScript 那边也不管。于是「zh 有 blurb、en 只有 label」是
一条合法的、两道闸口都放行的漂移，而它的后果恰是这三张表被免检的那个理由本身：
**浏览器被允许说得比 kernel 多，然后只对一门语言说了。**

**为什么是根因不是表象**：今天量下来 15 个成员 × 2 门语言**零漂移**。所以这不是
「修哪一条」，是**没有人在看**——下一张自有措辞的表进来、或某天省掉一个 `blurb`，
还是只能靠手工发现，跟前两次一模一样。

**改动**（`tests/test_web_vocabularies.py`）：

- 抽出 `_said_in`——「找到这门语言那一块」原本每个调用者各写一遍。
- 新增 `_shape` + `test_a_table_in_its_own_terms_says_as_much_in_every_language`
  （按 `_ITS_OWN_RENDERING` 参数化，3 条）：每个成员在每门语言下**字段集相同**。
  **逐成员而不逐表**——`blurb?` 允许某个 status 不带解释，那是这张表可以做的
  选择；只对一门语言做这个选择不是，而**没有任何类型能区分这两者**。
- 反例 `test_the_check_sees_a_field_dropped_in_one_language`：在类型已经允许的
  地方下手（删掉 `needs_assumption` 的 zh `blurb`），改完 TypeScript 照样编译、
  两道旧闸口照样通过——并就地断言这一点，那正是它对别人不可见的原因。
- `test_a_table_is_exempt_only_by_having_a_shape_of_its_own` 的 docstring 指向
  新闸口：被免检**要求**什么，和**凭什么**被免检，是同一条规则的两半。

**明确放弃的一个更强做法**：把那两张 `Record<string, …>` 改成 TS 联合类型
（像 `TIER_META` 的 `Record<AnswerTier, …>`）。那要在 `types.ts` 里再手写一份
词表，换来的检查 Python 闸口已经覆盖、而且锚得更真（锚在 schema 上，不是第三份
手抄）；#393 已定浏览器的复述本身是要削的东西（#399）。**代价**：这两张表少一个
键，TS 编译期挡不住，只有 pytest 挡。

**基线（本条）**：6168 → **6172**（+4）。

**方法论沉淀**：(236)**一个「豁免」必须自带它的义务，否则它就是一个洞**。判据：
豁免是按什么属性测出来的？那个属性测完之后，有没有人对它提要求？这三张表因为
「持有结构」而免检，而结构本身从此无人过问——`_browser_word` 里那句 "the SHAPE
can be reported separately from the text" 说的正是它，只是说完就停在了「用来免检」。
(237)**登记条目里的「有 N 个作者」几乎一定要重量一遍**：文本扫描既高估（组件
自己的通用词撞上词表成员名）也低估。而「已漂」这类**现状**断言更要重量——它可能
在登记之后就被别的条目顺手修掉了，留着它会让人去修一个不存在的东西。

### #403 落地：边界画出来了，于是「不对读者说」才有东西可命名（2026-08-22）

**根因**（承上一条）：不是缺一个词，是 web 边界上 16 处 `except Exception`
把 `str(exc)` 当成读者的句子交出去，因而「这段文字说给谁听」这个区分根本
没被做。

**做了什么**：新建 `themis/web/failure.py`，`themis/web/app.py` 的 **16 处**
失败出口全部改走它，一条不剩（AST 闸口盯着：`app.py` 里不允许再出现自己
拼的 400 body）。这条边界有且只有两侧：

| 侧 | 内容 | 谁写的 |
|---|---|---|
| `words` | 读者的句子，**按语言成键**，浏览器来填 | 16 个阶段各一句，或——若是拒答——物种自己的那句 |
| `diagnostic` | `str(exc)` 原文 | 抛出点 |

**关键的一步是 `words` 而不是成品句**。服务器原来交的是一个已经选好语言的
字符串，也就是在没人知道谁在读之前就把语言定死了——**和 f-string 是同一个
错误，只是外移了一层**。`/api/audit` 早就是对的形状（「一行是产物不是渲染」），
这次只是把它推到全部出口。

**已有的拒答不重新措辞**：估计器拒答带着物种，物种在 `SAYS` 里已经有每门
语言的句子，直接透传（`words` 用物种的，`slots` 用 `details`）。物种还没有
句子的，落到阶段句，原文进 `diagnostic`。

**顺手删掉一份复述**：`AskWorkspace.tsx` 有一张 `STAGE_SAYS`，三个阶段各一
个标题——正是 #404 那个形状（浏览器复述 kernel 的词，没有闸口）。服务器现在
把句子交过来了，那三行撤掉。

**读者面的实际变化**：一个中文用户遇到内部错误，以前拿到
`ExtractionShapeError: edges[3] must be a mapping`；现在拿到「这份程序没能
跑完」＋「诊断信息：edges[3] must be a mapping」。诊断没有被藏起来——能贴
进 bug 报告的东西不该丢——但它不再冒充那句话。

**闸口四条 + 两条构造性反例**：每个阶段在每门语言里都有句子；`app.py` 里
零个自拼的失败 body；未声明的阶段**抛错而不是渲染成空句**（有回退的查表会
把「没话可说的失败」和「有话但没写」变成同一样东西）；拒答透传自己的句子
而不是阶段句。另外，`message` 这个字段名被测试钉死为不得出现——它就是当初
让 `str(exc)` 成为读者句子的那个槽位。

`app.py` 的单语欠账 10 → 4。全量 **6182 passed / 150 skipped**，mypy 干净，
前端已重新 build（陈旧 `dist` 是这个仓的头号坑）。

**方法论沉淀**：(234)**语言被定死的地方，往往比出问题的地方外一层**。
f-string 在写它的那行定死语言；服务器交成品字符串，是在 HTTP 边界上定死
同一件事。判据是同一条：**这段文字离开生产它的地方时，语言是不是已经选完
了**。(235)**一个catch-all 会把它下游所有的区分抹平**。16 个出口原本可以
各自区分「读者能做什么」和「维护者要看什么」，一处 `except Exception` +
`str(exc)` 让这 16 次区分一次都没发生——而且从每个出口单独看都看不出来。

### #403 的前提不成立：这个区分不是没有名字，是没有被维持（2026-08-22，勘定 + 更正）

**先更正我自己两小时前写在上面两条里的话。** 我说过「`Kind.REQUEST` 的 56 个
抛出点说给调用方，缺的不是翻译而是一个名字，归 #403」。**错了。**
`refusals.record()` 不按 kind 过滤——dispatch 捕到的任何 `EstimatorFailure`
都会以 `reason` 写进信封，`INVALID_INPUT` 和 `NOT_IDENTIFIED` 一样到达读者。
那 56 个点欠的就是翻译，归 #405，不归 #403。上面两条里的相应句子已就地改正。

推错的地方值得记下来：我把「这句话像是说给谁听的」当成了「这句话到达谁」。
前者是读措辞得来的印象，后者是可以量的。

**量的结果，以及它把 #403 变成了另一件事。** 判据取「这段文字有没有被接住
并留在结果里」——因为读者是被捕获点决定的，不是被物种、也不是被异常类决定的：

| | |
|---|---|
| 包内定义的异常类 | 41 |
| 包内**从没被接住**的（14 个抽样中） | 11 |
| 被接住且把文字留进 `QueryResult` 的 | `CounterfactualBoundsError`（2 处） |
| 被接住且把文字交给浏览器的 | `LLMBridgeError`（web/app.py 2 处） |
| 被接住且把文字写进信封的 | `EstimatorFailure`（`refusals.record`，全部） |

看起来「11 个没被接住 = 说给调用方」就是那个缺的名字。**但它不成立**：
`themis/web/app.py` 有 **6 处 `except Exception`**，每一处都把
`{"error": type(exc).__name__, "message": str(exc)}` 交给浏览器。于是
`ExtractionShapeError`、`DataContractError`、`MalformedBundleError` ……
全部都能以英文原文出现在一个中文用户的屏幕上。

**所以根因不是「『不对读者说』缺一个名字」，是这个区分在边界上根本没有被
维持**：一处 catch-all 把所有维护者／调用方的话都路由给了人。一个没有被
维持的区分，当然没有名字可给——先有边界，才有词。

**这也解释了为什么 `types.ts` 的 `NOT_FOR_A_READER` 是手写名单。** 它列的是
四个**信封字段**（`query_id` / `confidence` / `confidence_sources` /
`estimator_dependency_missing`），注释写着「它们说给调用方或审计方，不说给
读答案的人」——浏览器这一侧真的在维持这个区分，而 kernel 那一侧不在。名单
是手写的，因为它没有可读的来源。

**#403 因此重述为**：web 边界上的 6 处 catch-all 要区分「读者能据以行动的
拒答／校验结果」和「不该给人看的意外错误」，后者给读者一句他的语言里的话，
`str(exc)` 留在维护者通道。这条落地之后，「不对读者说」才有一个可查的来源，
`NOT_FOR_A_READER` 才可能不是手写的。

**方法论沉淀**：(232)**「这句话说给谁听」不能读措辞判断，要看它到达谁**。
措辞给的是作者的意图，到达给的是事实，两者可以差很远——而差的时候，读者
拿到的是事实。(233)**一个登记条目说「X 缺个名字」时，先验证 X 真的存在**。
缺名字有两种：区分在做但没被命名（补一个词就行），和区分压根没在做（补词
只会给一件没发生的事发一张证书）。这一条是后者，而两者从条目的措辞上看
一模一样。

### 档③ 第二刀：剩下的分歧不是一种，是三种（2026-08-22，#391）

把「还在抛出点自撰句子」的 140 个点按物种读了一遍。**一个物种的多个抛出点
彼此不一致时，不一致的是三样东西之一**：

1. **说话的是哪个估计器**（"the general-ID plug-in" / "measurement-error
   correction" / "selection-backdoor recovery"）——这已经在块上，字段叫
   `estimator`；
2. **这一次的那些数**（层级数、行列式、bootstrap 次数）——这就是 `details`；
3. **真的是另一件事**——那个物种在替两个物种干活。

只有第 3 种需要新物种。前两种和第一刀是同一个病。

于是第二刀取第 1、2 两类里判据无歧义的 7 个物种、15 个抛出点：
`not_identifiable_by_general_id`、`not_a_joint_intervention`、
`response_model_too_large`、`continuous_outcome`、`continuous_adjustment`、
`no_usable_resample`、`degenerate_recovered_exposure`。自撰点 **140 → 125**，
物种句子 29 → 36。欠账表再降 7 个模块（`measurement.py` 40→35、
`general_id.py` 20→16、`iv.py` 22→20……）。全量 **6182 passed / 150 skipped**，
mypy 干净。

**我把一个物种归错了类，是测试拦下来的。** `do_risk_not_identifiable` 两个
抛出点我当成「只差谁在说」合并了；`test_a_graph_with_no_route_at_all_still_refuses`
立刻炸了，而它的 docstring 正是为这件事写的：「拒答必须说出试过哪些路线——
只被告知『没有后门集』的调用方，会去找一个根本帮不上忙的协变量」。
`binary_do_risk` 只试后门，`causation` 试了后门／general-ID／工具三条。
**差的不是措辞，是事实**，属于第 3 类。已撤回，两个点恢复自撰。

**剩下 125 个点分两堆，两堆各缺一样东西**：

- **56 个点是 `Kind.REQUEST`**，其中 24 个是 `INVALID_INPUT`，措辞说的是
  *你这次调用写错了*。~~它们缺的不是翻译，是一个名字，归 #403。~~
  **更正**：`refusals.record()` 不按 kind 过滤，dispatch 捕到的每一条都以
  `reason` 写进信封，所以它们和别的拒答一样到达读者，欠的就是翻译，归 #405。
  仍然成立的那半句是「`Kind` 回答的是接下来做什么，不是说给谁听」——
  只是「说给谁听」这件事本身没被维持，见下一条。
- **59 个点属于 9 个物种，每个物种带着不止一个事实**：
  `insufficient_support` 15 个点混了「某一层没有行」和「某一列在这份样本里
  只有一个取值」；`overlap_insufficient` 9 个点里也有后者——**同一个事实
  挂在两个物种下面，边界由哪个估计器先写而定**。`exposure_not_binary` 6 个
  点是三件事（状态不是两个／状态不是真假一对／观测值不被声明的状态覆盖）。
  `singular_design` 7 个点各自命名了一个不同的矩阵。

**第二堆还牵出一个更前面的问题**，值得单独记下来：好几条自撰句子的尾巴是
**「换哪个估计器能行」**（"Use the difference-scale four_way_decomposition
for a continuous outcome"、"or use a design (RCT / IV) that creates the
contrast"）。那是有用的话，但信封上早就有一个一等字段装它——缺口报告的
`alternative_paths`。**一条写在拒答散文里的替代路线，是那个字段的第二份
记录**，而且是不可查询的那一份。所以这批的修法不是「把尾巴翻译了」，是
先问它该不该在这句话里。

**方法论沉淀**：(230)**分歧的种类比分歧的数量重要**。「140 个点措辞不一致」
是一个数，按它排期会得到一件大而无当的活；按「不一致的是什么」分完，它是
三件事，其中两件与已经做完的那一刀同型，第三件才需要新东西。(231)**一个
事实同时挂在两个名字下，说明名字的边界是被写入顺序决定的，不是被事实决定
的**——`insufficient_support` 与 `overlap_insufficient` 都收了「这一列不
变化」，因为先写到的那个估计器就近挑了一个。

### 档③ 第一刀：拒答的句子挂回物种，信封上留下能重说一遍的素材（2026-08-22，#391）

**做了什么**：`themis/refusals.py` 新增 `SAYS`——29 个物种 × 每门语言一句，
槽是具名的，由 `details` 填；`sentence(物种, details, lang)` 组句；
`EstimatorFailure(物种, **details)` 不给 `message` 时自己去查。31 个抛出点
从「自己写一句 f-string」改成「把这一次的数交给槽」。

| | 改前 | 改后 |
|---|---|---|
| 抛出点自撰句子 | 171 | **140** |
| 抛出点只交数、句子归物种 | 0 | **31** |
| 物种在两门语言里都有句子 | 0 | **29** |
| 同一个物种被两种方式抛 | — | **0**（闸口） |

**这一刀真正买到的不是「翻译了 29 句」，是信封上多了「能重说一遍」的素材。**
`estimator_failure` 现在同时带着 `failure_type` 和这句话要用的全部具名槽
（`details`）——而「每个委托点必须把它物种命名的槽供齐」正是新闸口守的那
一条。于是 #395 落地时，渲染层可以拿信封重新组一句读者语言的话；今天
`str(exc)` 只是按 `language.DEFAULT` 先组了一遍。**当场声明的取舍**：所以
拒答消息现在统一是中文（改前是 157 英文 / 6 中文的混合），一个只读异常
消息的英文维护者从此读到中文。选它是因为 `reason` 本就是读者面字段
（schema 里与 `failure_type` 并列），维护者面的那句是 `says`，那一栏仍是
英文；真正的终局是渲染时重说，那要等 #395，不是今天能做的。

**闸口五条，每条都构造了它该说「不」的那个反例并真跑过**：某门语言缺句子、
两门语言填的洞不一样、委托点漏了一个槽（`KeyError`，发生在最没有余力再失败
一次的时刻）、一个物种被两种方式抛、自撰点计数（140，只减不增）。另有两条
本身就是反例的测试：物种没句子且抛出点也没给 → `ValueError`；漏槽 → `KeyError`。

**副产物一（是全量测试抓到的，不是我想到的）**：`details` 现在要落成信封能
装的东西，我写的降级只认标量和列表，**字典掉进了兜底分支**——一个分层
`{'w': True}` 会以字符串 `"{'w': True}"` 的样子到达信封，读者还读得懂，下游
再也索引不了。三条测试同时炸出来，已修成递归，并立了测试。

**副产物二**：7 个死 import 清掉（2 个是这次改动造成的，4 个 `from .. import
refusals` 在 HEAD 上就已经死了，1 个 `monotonicity_word` 同理）。措辞上有一处
刻意的读者面改动：列名不再被 `!r` 加引号——引号是**句子的**，而句子现在有
一个作者，能一次决定。

**欠账表 16 个模块同时下降，共 29 条单语文本消失**（`measurement.py` 44→40、
`scm_counterfactual.py` 5→1、`missing_recovery.py` 6→3……）。全量
**6182 passed / 150 skipped**，mypy 干净。

**答上一条留下的设计问题**（普查说「动手时先答」）：`INVALID_INPUT` 24 个点
24 句话，两个候选答案——「一个物种在替 24 个物种干活」或「句子的键不止物种
一个」——**都不对**。24 句说的是同一件事：*你这次调用写错了*
（`unknown model 'foo'`、`estimate_iv_overid requires ≥ 2 instruments`、
`target_marginal must be {'predicate': str, ...}`）。它们本来就不该有读者的
句子。而 `Kind` 差一点就能说出这件事却说不出：`Kind.REQUEST` 的 19 个物种里，
`unknown model` 是程序员打错了字面量，`states_incomplete` 却是使用者提供的
混淆矩阵盖不住他自己数据里的结局取值——后者是读者的结论。**`Kind` 回答的是
「接下来该做什么」，「这句话说给谁听」是另一个问题，今天没有名字**——#403
登记的正是这个缺名字的问题，今天它有了第二个、也大得多的实例（24+ 个点）。

**剩下的 140 个点分两类**：24 个 `INVALID_INPUT` 连同同类，措辞像是说给调用方
的（~~归 #403~~ **更正：不归 #403，见下一条**——`refusals.record()` 不按 kind
过滤，它们照样以 `reason` 到达读者，欠的就是翻译）；其余的是物种自己跟自己不
一致（`TREATMENT_NOT_BINARY` 七个点六句话），逐个和解是一次阅读而不是机械动作，
值得单独一趟，中间保持全绿。

**方法论沉淀**：(228)**一句话能不能被翻译，看它是模板还是值**。f-string 在
写它的那一行就把值插完了，所以它是一个值，旁边没有位置留给第二门语言——
171 条里 149 条如此。要翻译的前提从来不是「找人翻」，是先把句子变回模板、
把这一次的数移到它本来就有的槽位里去。(229)**「说出来」和「说得回来」是
两件事**。信封上留下物种 + 具名槽，这句话在任何语言里都能被重新说一遍；
留下一句已经说好的话，它就只剩那一门语言。闸口该守的不是「翻没翻」，是
「素材齐不齐」——所以这次立的是「每个委托点必须把槽供齐」，而不是「每句
话必须有中英两版」。

### 档③ 动手前的普查：607 条不是一件事，是三件（2026-08-22，#391 勘定）

登记说 906，今天的欠账表说 607 / 58 个模块。**两个数都没说这些文本是什么**，
而修法完全取决于那个。按两个轴交叉一扫，出来的相关性几乎是完美的：

| | 中文 | 英文 |
|---|---|---|
| 写进**信封**的（字段、表） | **283** | 45 |
| **抛出来**的（异常消息） | 16 | **263** |

**kernel 写给读者的用中文，抛给调用方的用英文**——一条从没被说出口、也没有
任何东西执行的约定。它大体是对的：`DataContractError` 的「data must be a
pandas DataFrame」确实是说给程序员的。所以真正要看的是那 61 个例外。

**例外不是随机的，聚成两团，而且指向同一个字段。** 中文却被抛出的 16 条里，
6 条是 `dose_response.py` 的 `EstimatorFailure`、7 条是
`ProximalNotIdentified`——**都是拒答**，说的是「你的数据 / 你的图支撑不住
这个量」，那是读者的结论不是调用方的契约违规。英文却没被抛的 45 条里，
`claim.py` 的 `BLOCK_REASONS` 8 条与 `dispatch.py` 的
`estimator_failure.reason` 若干——**也是拒答**。

于是：

**`estimator_failure.reason` 一个信封字段，25 个作者模块，两门语言。**
157 条英文、6 条中文，那 6 条全来自 `dose_response.py`。同一个 UI 槽位，
**读者拿到哪门语言取决于是哪个估计器拒的答**。

跑出来是这样（`build_analysis_report`，`lang=zh`）：

- 「**没有给出数值 —— 这批数据支撑不住**：the design this strategy needs
  names columns the data does not have。结构上是可识别的……」
- 「**没有给出数值 —— 这批数据支撑不住**：treatment column 没有变化
  （max == min），无法估计剂量响应。结构上是可识别的……」

框架被翻译了，`reason` 原样贴进去。**这正是 #372 那条病**（「late_caveat
是一整段英文原文，直接印在中文报告里」）——当年修掉了一条串，没有扫过
分母，于是它在旁边活着，157 倍。

**根因不在「谁忘了翻译」，在这个类已经有三个槽位而句子占了两个的活。**
`EstimatorFailure(failure_type, message, **details)`：物种是
`themis/refusals.py` 的封闭词表（70 个已声明、58 个真被抛、12 个从没被
抛过），`details` 是「这一次的那些数」，`message` 是散文。量下来：

- 171 个抛出点，58 个物种，平均 2.95 个点／物种，29 个物种只被抛一次
- **171 条 message 里 149 条插值了一个运行时值**
- **只有 60 条同时传了 `details`**

也就是说 **89 个点把「这一次的那些数」插进了散文，而它旁边就有一个专门
装它的槽位**。一旦插进散文，这句话就不再是模板而是一个值——`language.py`
的模块 docstring 早就写着这件事为什么让翻译不可能：「427 of the strings
that reach a reader are built by interpolation, so the Chinese sentence is
not a constant and cannot be a key」。而渲染 prompt 也早就在要求读者面优先
读 `details`：「a reply that has it and paraphrases `reason` instead has
thrown away the actionable half」。**三处各自都说对了一半，没有一处能强制
另外两处。**

**所以档③ 的第一刀是 `estimator_failure`，形状是 `fill(SAYS[物种], lang,
**details)`**：句子挂在物种上、洞由 `details` 填。剩下的工作量是把那 89 个
点的插值挪进 `details`。**一个待答的设计问题**：`INVALID_INPUT` 一个物种被
抛了 24 次，24 句话不可能是同一句——是这个物种在替 24 个物种干活（那么它
该被拆），还是句子的键不止物种一个（那么键是什么）。这一条动手时先答。

**方法论沉淀**：(226)**一条判据的分母对齐了闸口，就不一定对齐设计**。
「607 条单语文本」是闸口该数的东西——它不该关心那是中文还是英文。而决定
怎么修的是「这段文字说给谁听、现在是哪门语言」，那要另外两个轴交叉才看得
见；只看总数会把三件事当成一件排期。(227)**约定越是大体正确，它的例外
越值钱**：546 条守着「读者用中文、调用方用英文」，61 条不守——而那 61 条
不是噪声，是同一个字段的两个作者。找病灶别扫大头，扫例外。

### prompt 把读者的语言当成了自己的语言（2026-08-22，#390 档⑥c / #401）

**现象**：`themis/prompts/response_rendering.md` 2179 行里 404 行中文，
标题 / 开场 / Role 段把「输出中文」写死。

**根因**：这份 prompt 是**写给模型的指令**，指令用哪门语言和回复用哪门
语言是两件事，而这份文件从没把它们分开。404 行的四种形状全是这一件事
的推论：251 行 `>` 成品回复是用**读者的语言**写的范文（语言被烧进证据
里）；约 50 行是 kernel 已经拥有的词表的第二份（必然漂）；约 65 行是
prompt 自己的指令写成了中文；约 40 行是拿一门具体语言演示一条与语言
无关的原则。

**为什么两半必须一起做**：只改标题加一句「用读者的语言回答」是无效的
——模型看到 251 行中文范文会照着写中文，**指令与它下面的证据矛盾时，
读它的模型信证据**。只收敛示例不参数化，标题仍写死。

**这条根因仓里已经有一份先例，而且是同一句话。** `nl_to_kernel_ast.md`
§"Reference examples" 写着它当年为什么撤掉注入的 few-shot：三对样例共享
同一个图形状，「as concrete demonstrations they outweighed the prose,
pulling nearly every answer toward that same triangle」。**同一个机制，
不同的轴**——那边一个演示把每个答案拉向同一个三角形，这边把每个回复
拉向同一门语言。

**复述量是量出来的**（我先前目测说「两条已漂」，实测差一个数量级）：

| 被复述的词表 | 行数 | 与拥有者不一致 |
|---|---|---|
| 假设 id（`assumption_glossary` 拥有，306 键） | 28 | **14**（正好一半） |
| 中介失败条件（`envelope_glossary` 拥有，**已有 en 面**） | 两张各 6 行 | 表 A 六条与词表逐字相同；表 B 六条与词表、与表 A **都不同**——**一个文件里两张同码表互相矛盾** |
| E-value 四档（`sensitivity._format_note` 生产，随 `note` 发货） | 4 | **4** |

合计 44 行复述，**24 行与拥有者说的不是一回事**。这些都不是「翻译欠账」，
是**第二个作者**——而写在 prompt 里的那份，是没有任何东西会去核对的那份。

**改法按形状分四类**：范文 → 收敛成它演示的那条规则（规则要完整到能独立
成立：后门 / 前门两张模板并成**一个形状 + 前门多出的那一句**——「即使
X、Y 之间有未观测共因也识别得了」，那一句才是读者要的）；复述 → 删掉，
指向信封已经带来的词；中文指令 → 用文件自己的语言写；填空示例 → 说
「给一个匹配这个谓词真实含义的具体例子」而不给一门语言的样例。方法枚举
表的第三列 `Example phrasing` 整列删掉：**两列说同一件事，其中一列用读者
的语言说**。

**参数化那一半**：`render_reply(..., lang=)` / `ask(..., lang=)`，user
message 用英文框架说 `Write the reply in {endonym}`。新增
`language.ENDONYM` / `endonym()`——用**本名**而不是某门固定语言里的名字，
因为这是整个请求里**唯一一条必须被「还不知道该用哪门语言」的读者读懂**
的话：用英文说 answer in Chinese，本身就是在用它被要求别用的那门语言
下指令。

**闸口钉结构不钉语言**：`test_a_prompt_instructs_rather_than_demonstrates`
——prompt 里的引用块只能是文件开头那段「这份文件是干什么的」（四份
prompt 现在正是这么用的），不能是某条规则底下的演示。语言无关，所以
`en` 升格之后它仍然有效——**一条只查中文的判据会在那天静悄悄失效，那
正是 ⑥a 那条病**。它够不到的地方写进了 docstring：写成散文的演示、写在
围栏块里混在 schema 与公式中间的演示，它都放行。

**这次改动的行为正确性在本次会话里验不了。** 方法论要求用 general-purpose
agent 出题压测真回复，而本次会话的规则禁止我未经要求调 Agent。能验的是：
既有结构闸口全绿（`test_gap_kind_coverage_meta` 14 条钉的节名 / 估计量名 /
gap kind、`test_vocabulary_reach` 的 `NAMED_IN_PROSE` 反引号成员、bounds 的
`#### <method>` 节，全部保留）+ 新立的可判定闸口。**回复质量是否退化只能
等真压测。**

顺带修掉一个既存缺陷：方法表 `counterfactual_cell_plugin` 那行的
`P(X, Y | Z)` 竖线没转义（同族的 `causation_plugin` 行写的是 `\|`），
markdown 里那一行多渲染出一列——是拆列脚本报的，不是看出来的。

规模：2179 → 1931 行，404 行中文 → **1 行**（`VISION 2026-04-26
§"输出 (2)"`，引用另一份文档的节标题，属于新 Role 段说的「保持原样」
那一类）。

**档② 到此收口，而剩下的 41 行不是它没做完的。** 三个面：prompt 剩 1 行
（引另一份文档的节标题），浏览器剩 12 行（`FRAMING_FIELDS` 8 + `NOT_FOR_A_READER`
4，两条都是**未答的问题**不是欠的翻译），`themis/output` 剩 29 行——逐条查过，
**全部是信封字段**：`bounds.py` 的 `notes` / `data_required`、
`result_orchestrator.py` 的 `extensions.*` 三块与台账 `claim`、`sample_size.py`
的 `precision_target`（已登记 #397）。一个例外是 `formula_text.py` 那条抛给
维护者的异常消息，与 `NOT_FOR_A_READER` 同形。

**档②的分母当初是按目录数的（「themis/output 1116 条」），而该做什么由「这段
文字最终落在哪」决定**——`themis/output/` 下有四个模块产的是信封内容不是报告
内容，它们归档③。这不是把线重画到胜利那边：`bounds_results[].notes` 是 schema
声明的字段，读者是从信封读到它的，不是从报告。

**方法论沉淀**：(224)**指令与它下面的证据矛盾时，读它的模型信证据**
——所以「把 X 变成参数」和「把演示 X 的样例收敛成原则」是同一件事的
两半，只做前一半得到的是一份自相矛盾的 prompt，比不改更差。判一份
prompt 有没有这个病，问它的示例：**里面有没有哪个属性本来应该是参数**
（这次是语言，`nl_to_kernel_ast` 那次是图形状）。(225)**一份 prompt 里
出现的封闭词表，默认就是第二个作者**——它不参与任何自动核对，所以
「今天一致」不是证据而是尚未发生的事。量法是拿它逐行比拥有者，别靠
翻阅：这次 44 行里 24 行早已不是一回事，其中一处**在同一个文件里就有
两张互相矛盾的表**，而两张都没人读。

### 组件说的话也归读者的语言管（2026-08-22，#390 档⑥b）

17 个组件 + `App.tsx` + `api.ts` 的 **181 行**单语文本拿到第二门语言。浏览器
的单语读者面行数 **193 → 12**，剩下的两处都不是「还没翻」，而是**「这段文字
到底是什么」还没答**（见下）。

**先定接缝：`useLang()`。** 语言怎么到达一个组件，今天各处 `import
DEFAULT_LANG` 也能跑，但那样档④ 的开关是 17 个文件的改动，而那一刻的压力
会是「把 lang 当 prop 一路穿下去」——连不渲染文字的中间组件也得带上它。所以
先把**问题**命名在一个地方：`language.ts` 的 `useLang()`，今天返回
`DEFAULT_LANG`，档④ 就在那一处回答它。边界随之清楚：**组件里用 hook，纯模块
里用参数**——`verdict.ts` 不是组件，它的函数继续收 `lang` 形参，由组件把
`useLang()` 的结果传进去。

**`TIER_META` 有三个作者，两个已经漂了。** 答案三档的词（`lib/verdict.ts` 的
`TIER_META`）在 `App.tsx` 的页脚图例和 `AskWorkspace.tsx` 的侧栏各被**重写了
一遍**：标签 `点` vs `点估计`，gloss `能算出` vs `可以算出`、`给不了，` vs
`给不了数，`。**一份重复的正确修法不是把它翻成两份，是让它别再是重复**——两处
都改成读 `tierMeta(tier, lang)`。这是 #394 那条病往上一层：kernel↔浏览器的
复述立了闸口，浏览器↔浏览器的复述**没有锚点**，于是这三处是转换时用人眼撞见
的。判据可以做（见登记项），今天先记下它是怎么被发现的。

**错误消息分三种，只有一种是我们的。** `api.ts` 原来把「请求失败（404）」这句
自己的话直接拼成字符串扔出去，而九个组件打印 `(e as Error).message`。现在
`KernelError` 多带一个 `words`：**这个文件自己措辞的失败**（用读者的语言说
它）、**服务端措辞的**（原样转交，服务端为自己的语言负责）、**平台抛的**
（也原样转交——网络栈的措辞不归我们翻）。`errorText(e, lang)` 是这三者相遇的
唯一一处。同一个形状在 `DagBuilder`：`serialize()` 的五条校验消息改成返回
`{refused: Words}` 而不是字符串——**校验跑在没有读者的地方，消息读在有读者的
地方**，这正是 kernel 自己的拒答一直在做的切分。

**带强调的句子拆成部件，不是一个带标记的字符串。** `<b>本机代理</b>` 这种，
强调在另一门语言里落在**另一个词**上，写进文本里的 `<b>` 会把它钉死在第一个
作者读的位置。所以是 `head/lead/tail`（两处强调就是五段），每门语言自己决定
它们之间是什么。同理，列表分隔符 `、` vs `, ` **属于句子不属于数据**。

**不该被语言碰的东西留在外面**：`ROLE_META` 的 `cls` 是样式表给这个角色起的
名字，每门语言都一样，逐语言各存一份就成了它的第二份记录；`citations()` 不收
`lang`，因为引用是信封自己的文本，**翻译一篇论文的标题是关于它的另一个断言**；
集合花括号 `{X, Y}` 留在槽位的值里而不是句子里——它是数学记号，而 `fill` 没有
转义，因为一个句子没有理由想要一个字面花括号。

**剩下的 12 行各自是一个未答的问题，不是欠的翻译**：`verdict.ts` 的 8 行是
`FRAMING_FIELDS`（`def` 同时是给读者看的字、身份标记、和写进 program 的值）；
`types.ts` 的 4 行是 `NOT_FOR_A_READER` 的值——那张表自己写着这里的东西**不对
读者说**，它们是写给维护者的散文，只是因为旁边的键是数据而被存成了数据的形状。
两条都已登记，都不靠再开一张豁免名单——**豁免名单正是上一档刚废掉的东西**。

**三条钉浏览器源码的判据，钉的是拼写而说的是结构。** 全量跑出来两红一潜：
一条找精确调用串 `derivationRows(result.derivation)`（多一个参数就断）；一条
用 `component.index("识别公式")` 定位那一节、靠三个位置的先后断言渲染顺序；
第三条 `assert "依据文献" in component` **没红，但已经不再说它要说的事**。
根因是同一个：**这些判据把源文件里的字面文本当成了它要断言的那个事实的载体**，
而语言层的做法正是**把读者面文本全提到文件顶部的一张表里**——于是「文本在文件
里的位置」不再是「它渲染在哪」，「文本在不在文件里」也不再是「这一节还在不在」。
把中文串换成表名能让今天绿，但那还是拿位置代表顺序。改法是**钉渲染点而不是
拼写**：顺序用 `say(SAYS.idFormula` 这个使用点定位，存在性用「哪个名字被读了」
断言，参数列表之后是什么与「读没读」无关。

### 闸口的分母停在了语言边界上（2026-08-21，#390 档⑥a 收口）

**现象**：`verdict.ts` 的 20 张词表和 63 条路线句、再加这一档的 180 条，
全部拿到了第二门语言，全绿。而它旁边的 `Verdict.tsx` 有 34 行中文从没被
任何东西问过。

**根因**：`test_no_sentence_reaches_the_reader_in_the_wrong_language` 的
分母是 `themis/**/*.py`，因为**那半边扫描建在 `ast` 上**。「用什么读」是
一件关于读者的事实，不是关于主体的事实——而**一条判据的分母停在语言边界
上，它报的就是「一个面的完备度」，读起来却像「这次构建的完备度」**。

**为什么这是根因不是表象**：不是「忘了加浏览器」。分母跟着实现手段走，
是每次新读者面出现时都会重演的形状；`themis/web/static/index.html`（#348）
当年也是同一种漏法。所以修法不是补一张浏览器名单，是**让分母是「读者面」
而不是「Python 文件」**：加 `_reader_facing_ts`，吐出与 Python 半边**同型
的五元组**，`_owed` 与完备性那一臂各自把它接上，两个既有测试一字不改。

**这一面的语言由什么裁定，是那半边的同一件事往上抬一层**：`Words` 里的
文本被它自己的键说明了语言，`Words` 外的文本是谁打的字就是哪门语言。所以
allowance 就是「在不在一个 `Words` 里」，由 `web_source.words_literals`
读——那个扫描自己的覆盖面已经被 `test_the_language_is_a_parameter_not_a_name`
钉住了。

**单位是「行」而不是「字面量」，与 Python 半边不同，这是代价也是判断**：
JSX 的文字根本不是字面量（`<span>因果验证器</span>` 是三个节点一句话），
按字面量数会把一个整篇中文写成的组件报成「几乎没欠」。行也正好是 diff 里
会动的那个东西。代价：同一行上若既有该翻的词又有不该翻的数据，这一行要等
数据那一侧有答案了才能清零——`FRAMING_FIELDS` 的 7 行就是这样（见下）。

浏览器接进分母后，`STILL_ONE_LANGUAGE` 多出 20 行、**193 条**。这张表是
计数不是上限，只能减：一个模块清完是「删掉这一行」，一个模块多写一句是
「和从没上过表一样红」。

**闸口按纪律构造了它该说「不」的两个反例**，两个都真的红了：往 `verdict.ts`
加一行中文（8→9，「up from 8」），以及把 `Verdict.tsx` 从表上摘掉（完备性
那一臂立刻点出 `Verdict.tsx:75 aria-label="判决"`）。单元级的反例写在
`test_a_browser_sentence_outside_a_words_is_refused`：三行一个文件——写给
维护者的注释、给齐了语言的标题、直接打进标记里的同一个标题——只有第三个是
读者被递了单语，把这三者分开就是这半边判据的全部。

**这一步顺带撞红了另一条闸口，而它红得对。** 新增的 17 个 `.tsx` 路径被
`test_no_source_file_names_a_path_that_is_not_there` 报成「不存在」，报出来
的名字少一个 x。根因不是「漏了 tsx」——`_PATH` 的扩展名交替里 `tsx` 就写在
那儿；是**正则交替最左优先而非最长匹配**，`ts` 排在前面于是每个 `.tsx` 只被
吃到 `.ts`。**书写顺序成了语义，而没有任何东西说顺序有语义**。挪一下今天能
绿，但下一个「一个后缀是另一个的前缀」的组合不会红，只会**静静地少匹配**，
也就是这条闸口的分母悄悄变小——正是上面刚修过的病。所以改成两个机制：正则
只说「路径到哪里结束」（最后一个点后的一串词字符），一个**集合**说「哪些结
尾算我们的」。集合无序，天然不可能有顺序 bug。反例也照这个形状补：`.tsx`
必须整个到达，`.ts.orig` 必须一个都不到达。

### 剩下的渲染器与 8 行数据（2026-08-21，#390 档⑥a-3/a-4）

14 个数值细节渲染器、纵向/θ 三个辅助、`causation` 与 `scm_counterfactual`
两个答案渲染器、`estimateMeta`、`structuralReadout`、反事实单格问句、推导
链与答案两张行表——`verdict.ts` 的单语读者面行数 **188 → 8**。

`DetailRenderer` 是**两个必需参数**而不是块渲染器那个具名对象，理由写在
类型旁边：它们收的是「装着这个数的那个容器」，没有 `ext` 也没有 `ciLevel`，
把它们塞进 `RenderCtx` 会让契约多出两个这一族永远不填的字段。

**`fill` 的槽位类型不收 `undefined`，于是逮到一个原来就在的缺陷。** 转换
时 tsc 在 9 处报 `Type 'number | undefined' is not assignable`——被替换掉的
那些模板串，在这些位置上**会把 `undefined` 这个词印给读者**。修法是 `?? '?'`
（这个文件本来就用 `?` 表示「没有名字」），**不是**把 `fill` 的类型放宽：
放宽等于把「洞印在页面上」换个形式再犯一次。

**剩下的 8 行是一簇，登记为 #400 而不是翻译掉。** `FRAMING_FIELDS` 的每行
带三样东西：`label`/`placeholder` 是纯读者面文本，而 `def` 同时是**给读者
看的字**、**身份标记**（消费方 `.includes('未指定')` 判它）、以及**真正写进
program 的那个值**。把 `def` 变成 `Words`，等于让**存进去的数据取决于当时
浏览器是哪门语言**。而且它有第二个作者——`themis/web/app.py` 的
`_FILL_DEFAULTS`，两边没有任何东西要求一致。理由写进了源码里
`FRAMING_FIELDS` 上方，不只写在这里。

### 路线渲染器没有一个槽位能让读者的语言到达（2026-08-21，#390 档⑥a-2）

`verdict.ts` 里 12 个**词表查询**早就收 `lang` 了。写这些词**周围那些句子**的
**渲染器**一个都没有，而且**没地方放**：`ROUTE_RENDERERS` 是一张分派表，
渲染器的签名就是这张表的类型，语言加不进其中一条。

**这与档⑤ 在 `analysis_report.py` 里遇到的是同一个形状**（那次给五张分派表
配了 Protocol）。TypeScript 能直接写出函数类型，所以修法更小，但顺带照出一件
事：**路线表把契约写在行内，答案表把它写成了 `BlockRenderer`**——行内那份因此
少一个参数，于是「读者的语言」这第四个参数变成了「要么三个没人用的位置参数，
要么第二份契约」的二选一。现在是一份契约，而且是**具名对象**：
`{ ext, lang, ciLevel? }`。

**`ciLevel` 保持可选，而这是查过的不是想当然的。** 两个容器装因果概率，
**形状不同**：走 `blockRows` 到达的那个是 `causationQuantity`，
`{lower, upper, point}` 且 `additionalProperties: false`，schema 就在旁边写着
「这个容器的两个写入者从没产生过采样带」；走 `answerRows` 到达的那个确实带
`ci_lower`/`ci_upper`，而那个调用点也确实传了 `num.ci_level`。**没有 CI 水平
可给的那条路，是靠「不给」把这件事说出来的**——可选是它的诚实表达，不是一个洞。

63 条文本变成 `Words`：十个路线渲染器，加上它们与尚未转换的表共用的三个辅助
函数。**一渲染器一张表**，而不是一串一个常量，这样渲染器和它说的话待在一起。

**变量名、数字、公式保持裸的**：那些是数据，第二门语言对 `${b.instrument}`
的改变是零——这也正是让这一档的计数诚实的东西。于是
`${b.latent}（取 k 个值）` 变成**一条带两个具名槽位的 `Words`** 而不是拼接；
挂理由用的那个 ` · ` 变成常量并写明理由：**两门语言里是同一个字形，而它后面
跟的是信封自己的文本，哪个面都不翻译它**。

`verdict.ts` 的单语读者面行数 **251 → 188**。

### 浏览器的语言层只造了「词」那一半（2026-08-21，#390 档⑥a-1）

`themis/language.py` 给调用方三个查询：`say`（一个词）、`gloss`（信封上读回
的一个取值）、`fill`（一个句子——`Words` 的文本带**具名槽位**，在调用点填）。
浏览器的 `lib/language.ts` 镜像了前两个，没有第三个。

于是 `verdict.ts` 里**唯一**一条带洞的句子只能就地发挥：用 `say`（那是词的
查询）取到文本，再 `said.replace('{factor}', fmtNum(...))` 填洞。**调用点打的
那个名字和文本里写的那个名字，是两个必须碰巧一致的字面量**——不一致时读者
拿到的是页面上印着的 `{factor}`。`say` 的回退让另一半也是静的：文本缺读者的
语言时，渲染出的是设计 kind 的标识符，而不是「这里有问题」。

**根因不是那一处，是契约缺了一半。** 没人做错什么——这就是「一份契约被实现
了一半」从内部看的样子。现在修而不是等到出事再修，是因为随着档⑥ 的浏览器面
落地，**还有 82 条带洞的句子正在往这个面上来**，每一条都可以自己长一个
`replace`。

`fill` 逐字镜像 kernel 的那个，**连它的两条拒绝一起**：只认具名槽位（一个
「意义就是位置」的洞挪不动，而两门语言不同意位置——这正是句子不能写成模板
字面量的全部理由）；两种缺洞都抛（句子不像词，没有 identifier 可以递出去；
而一个没人填的槽位会以 `{name}` 的样子到达页面）。

两条闸口。第一条**从 `themis.language` 上读出有哪几个查询**，而不是列一张
名单——那边多写一个，这边就多被要求一个；要点是**缺一个的那个面不会失败，
它会即兴发挥，而即兴发挥在源码里看不出来**。第二条禁止在 `src` 下任何地方用
`String.replace` 填具名洞，反例照真实那一处的写法造。

基线 6094/150 → **6097 passed / 150 skipped**，`tsc -b` 干净。

### 复述的边界写在条目的形状里，不写在一张名单上（2026-08-21，#393/#394）

浏览器有 20 张词表在复述 kernel 的封闭词表，两种语言下 220 条串。问题是
**该不该改成由 kernel 供给**。先量边界，量的过程中先撞上了 #394。

**逐张量出来的边界是三分的，而且分界写在源码形状里：**

- **15 张是逐字复述**——220 个「成员 × 语言」对，修完下面那两处之后
  **零差异**（另有 4 对只差 `**` 强调）。`derivation_rule` 一张就占 116。
- **3 张是浏览器自己的渲染**：`answer_tier`（label + 白话 gloss）、
  `result_status`（label + blurb，14 对全不同——emoji 前缀去掉、chip 标签更短）、
  `refusal_kind`（head/lead/tail）。**每一张都靠「条目是结构化的」宣告了自己**：
  复述装一个字符串，自渲染装一个按语言的结构。
- **2 张 kernel 故意不发词**（`gap_kind` / `query_kind`），理由各自写在
  `test_vocabulary_reach` 的登记行上——缺口自带 `description`，query kind 由
  一整条提问句解释，不由一个词。

**#394 的根因不是打错字，是钉子按表逐个手写。** 文字钉子今天有四处——本模块
里的两张名单（`_LEDGER_TABLES` 3 张、`_GLOSSARY_TABLES` 3 张）、一个独立函数
（`derivation_rule`）、外加 `test_risk_provenance` 里的一处——共盖 18 张可比表
中的 **8** 张，**没有任何一条规则说「每张表都必须被某处钉住」**。剩下 10 张里
漂了 2 张：`identification_pattern.c_factor` 的中文少了「分解」，它和
`bounds_contrast_kind.ace` 被重打时全角括号变成了半角。

**这正是本模块开头 docstring 早就为「键」那一层写下的同一个诊断，在下一层重演。**
那段话说的是「有一张表」和「每张表都被钉住」在源码里长得一模一样；键那一层已经
用 `ANCHORS`（写在 kernel 一侧、一词表一行、外加「每张声明的表都必须有一行」）
修过一次，文字这一层还留着修之前的样子。**一个靠枚举来覆盖的修法，会把它下面
那一层也留成枚举的。**

**修法：文字检查与键检查共用一个分母。** 按 `ANCHORS` 参数化，三张名单删掉，
kernel 的词一律经 `glossed_by` 那条访问器取（读者实际拿到的那个文本，而不是
它背后的表）。豁免**不写成名单**，而是从条目形状读出来——裸 `Words` 是 kernel
的词，结构化条目是浏览器自己的渲染——再用一条等式把「哪些表是结构化的」钉死，
**使豁免藏不下第四张**。

两个刻意的选择：

- **语言分母用 `language.written()` 而不是 `Lang`。** 英文是今天最容易悄悄漂的
  那一门，**恰恰因为还没有读者能被它回答**——没人在看它，而两边都已经写好了。
- **`**` 归一化掉，不钉。** 强调是各面对自己排版的决定（报告写 markdown，
  浏览器的 chip 不渲染它），`outcome_error_design` 那 4 句长句只差这个。

**反例是照着真实漂移的样子造的**：把一个全角括号打成半角。另外用两处**漂移前的
真实字符串**在内存里复验过——闸口对两处都说「不」，对修好的文本沉默。

`test_risk_provenance` 的那处文字钉子留着不动：**测试重复不是「事实的第二个
作者」**——两处都只读同一个源、断言同一件事，谁都写不了它；本仓明说验证器重复
是设计。

**#393 的答复，连同代价：**

- **不做运行时由 kernel 供词。** 那会把渲染搬进信封，与 #391 的方向正好相反。
- **构建期生成 + 签入是对的方向，而且没有被 #390 档⑥ 挡住。** 一开始以为
  档⑥ 会重写生成器要吐进去的那个形状，量完发现不是：这 20 张表**已经**是
  `Record<成员, Words>` 的最终形状（占 `verdict.ts` 的 845/2362 行，36%），
  而档⑥ 要动的是**另外 467 行裸单语**——浏览器全部 656 行 CJK 里，189 行已在
  `Words` 内，剩下的散在 15 个组件的行内散文里。两者不重叠。
- **今天选了：保留 220 条手写复述，把它钉死；生成另立一条，不挂在档⑥ 之后。**
  放弃的更优解是「零手写复述」（第三门语言只需在 kernel 写一次）。
  **代价 = 这 220 条仍需人手同步。** 之所以先交闸口：
  **闸口让重复变安全，生成让重复变零——这是两件不同的好处**，而今天两门语言
  都齐、都被钉住，第三门还没有。同步失败现在会在 CI 立刻响，而不是像
  `c_factor` 那样静静漂到读者面前；**这条闸口正是将来那个生成器要复用的新鲜度
  检查**，所以不是绕路。

顺带一件同名不同字：浏览器的登记表把结果状态叫 `status`，kernel 一侧叫
`result_status`——**一个词表两个名字，是「比较时得先被告知这两个是一回事」的
由来**，改成一个。`_word_for` 改收点分名而不是它所在的那一行，因为第二个调用
者没有行（`derivation_rule` 由词表声明，不由 schema enum 声明）。

基线 6084/145 → **6094 passed / 150 skipped**（删 7 条按表手写的、加 22 条按
分母参数化的，其中 5 条 skip），mypy 无新增。

### 一条假设的第二个作者——删掉整条结构化通道（2026-08-21，#392）

台账的 `layer` / `testable` / `claim` 三样，词表按 id 存着一份，
估计器的**结构化 identification spec** 又各自写了一份。
量出来：**55 处 spec 字典、28 个 id，而这 28 个 id 在词表里全部已有行**。
于是两份记录开始各说各话——

- **`testable` 矛盾 15 处**：全部 `positivity_*`（aipw / causation /
  counterfactual_cell / ctf_conjunction / general_id ×4 / tmle）spec 说 True、
  词表说 False；`iv3_independence_*` ×2 与 `latent_cardinality_*` 同向；
  `linear_structural_equations_*` 与 `additive_exogenous_noise_*` 反向。
- **`layer` 矛盾 2 处**（`scm_counterfactual`）——**严重度是 layer 的等级**，
  所以同一条前提在两个通道下严重度不同。
- **`claim` 6 个 id 已漂**：`consistency_of_potential_outcomes`
  在 8 处写了 **3 种**中文，词表里是**第 4 种**。

**根因是 spec 这个字典同时装了「身份」和「按身份可查的那些事实」。**
id 已经是台账的键，而那三样词表都按这个键存着——再写一份就是第二个作者。
这不是新形状：#343 用同一条判据杀掉了 provenance 的第二份记录
（`consistency_of_potential_outcomes` 曾经 191 次 `inherent`、92 次
`estimator_declared`），#345 杀掉了 severity 的（3252 条零例外）。
**这是同一个形状的第三例和第四例，而且这两例已经真的不一致了。**

**中途有一次决定性的演示。** 我先把词表里 positivity 那 11 行的
`testable` 改成 True，然后跑了一条 backdoor 真答案——读者看到的**还是**
`testable=False`，claim 也还是 backdoor.py 自己的措辞。
**修好了唯一该有的那张表，读者看到的仍是旧值，因为句子有第二个作者。**

**形状由一次测量定的：删通道，而不是缩小它。** 先怀疑 spec 该只留 `{"id"}`，
但那样它与扁平列表同型，问题就变成「两条通道是不是该并一条」。
逐模块扫过：**结构化通道没有携带任何扁平通道没有的 id**。
`dose_response` 最能说明问题——它的扁平列表是 `*(s["id"] for s in specs)`
**从结构化通道派生出来的**，注释写着「so there is one source of truth」：
**同一个重复，被局部地、朝相反方向解决过一次**。方向反过来才是通解。

**17 处矛盾逐条判过，而不是机械统一：**
- **positivity 是对的那一方，词表错了**——重叠能在数据里数（每层每臂有没有样本）。
  整族标 False 是照 `_ID` 一刀切的痕迹；同一张表里
  `rank_condition_P(W|Z,x)_invertible_verified_on_data` 就是 `_ID, True`，
  说明 `_ID` 从不蕴含「不可查」。11 行全改。
- **`iv3_independence_*` 词表对**：工具变量不等式反驳的是**排他性+独立性+无 defier
  的合取**，把可反驳性算到单独一行上是错的。
- **`latent_cardinality_k_correct_and_proxies_have_exactly_k_levels` 词表对**：
  它捆了两条主张（k 正确不可查、proxy 水平数可数），**捆绑主张的可查性取最弱那半**。
- **线性 SCM 那两行留在 `_FORM`，而这一条是可争的，写在这里让选择可见**：
  按 `IDENTIFICATION.breaks`（「算的根本不是那个量」）能论证单位级反事实下
  线性失败会让 abduct 回来的 u 不是那个单位的；但「这个单位的 Y_x」本身良定义，
  线性支配的是恢复得多准，那是 `FUNCTIONAL_FORM.breaks`。
  选 `_FORM`，与 `linearity_of_first_and_second_stage` 及 #396 刚写的
  `linear_structural_outcome_model_in_the_true_values` 一致；
  **不把两行升成作废级，是因为稀释作废级本身有代价（#344 的教训）。**

**有一样确实是路线的，不是假设的：单调性的 `testable`。**
闭式解路线上它当定理用，数据无从反驳；响应型多面体路线上它是模型限制，
**不加可行、加了不可行，就是数据在反驳这个方向**。
`RiskProvenance.can_refute_a_premise` 早就是一等的名字，docstring 明写
「which is what makes an assumption it carries TESTABLE」。
把路线那一半**折进 id**：`monotonicity_assumed_*` / `monotonicity_refutable_*`，
**判别词放在前面**，否则按前缀键的表看不见它（#398 的教训）。

**闸口 `test_no_producer_writes_a_ledger_entry_of_its_own`**：
台账条目只在造台账的两个模块里被组装。**键的是形状不是计数**——
原来那条守卫写的是 `found > 30`，这一批把分母从 60 打到 6，
一个阈值挡不住「哪天又有人开始写」。

顺带：估计层少了 55 句中文，10 个模块的单语欠账同时下降。

**方法论沉淀**：(223)**一个字段同时装「身份」和「按身份可查的事实」，
就是给那些事实立了第二个作者**——判据不是「它们现在一致吗」，
而是「有没有第二个地方能写它」；一致只是还没漂。
删掉第二个作者之后，矛盾里有一大半**自动**按剩下那个作者解决，
真正需要人判的只是「剩下那个作者本身对不对」。

全量 6084 passed / 145 skipped，mypy 133 Success。

### 一条 id 自己的词要排在运行时值之前，否则那截词漏进读者的句子（2026-08-21，#398）

词表 `_PREFIX` 有 14 行用普通模板——**一个洞装整条后缀**。这等于每一行都在
断言：「我这个前缀之后的一切，都是调用者的一个名字。」全仓扫过 14 行，
两族 id 让这个断言为假，共 7 处发出点，**两条性质不同**：

**一、`backdoor_adjustment_set_{z,w}_sufficient`**（causation.py ×2、
counterfactual_cell.py ×2）→「后门调整集充分：`{z,w}_sufficient` 阻断 X→Y
的所有后门路径」。它只有**一个**运行时值，缺陷是**把自己的词放在了值之后**。
修法就是把词挪到前面：`backdoor_adjustment_set_sufficient_{z,w}`。

**二、`propensity_clipped_to_floor_0.01_on_755_units`**（aipw.py ×2、tmle.py）
→「倾向得分被截断到下限（`0.01_on_755_units`）」。它的缺陷不同：**这条 id 带
两个运行时值，而模板只有一个洞**。而这正是 `_Fills` 规则形状被发明出来要处理
的情形——词表顶上那段注释写着「a runtime suffix is not always ONE name」，
这一行只是从来没拿到规则。修法是给它一条规则和一句两个洞的话，
并把尾巴上那个 `_units` 去掉（读者那句里已经有「个单位」了）。
**两个缺陷不同，所以两种修法不同**——一个是词放错了位置，一个是一个洞装不下两个值。

**两条的可达性也不同，实测过：**
- 截断那条是**活的漏**：真跑一次 AIPW（z→x 强关联，755 个单位被截到下限），
  读者面上就是那串 `0.01_on_755_units`；而且 aipw 的结构化 spec 里**没有**这个
  id，分类是它唯一的到达路径。
- 后门那条是**潜伏的**：battery 覆盖的四条路线上，结构化 spec 都先按 id 认领了
  它，`augment_assumption_ledger` 于是跳过扁平那条。同一个 id 走两个通道，
  哪个先到读者取决于这条路线的 dispatch 有没有传 `identification_specs`——
  **一个缺陷不显形，不等于它不在**。

**闸口 `test_no_id_puts_a_word_of_its_own_after_the_runtime_part`**：
AST 扫 `themis/` 下每一个字符串构造式（f-string 与 `+` 链，相邻字面量先合并——
一条长 id 怎么折行是行宽的事，不是 id 的事），凡是开头命中普通模板前缀、
中间有洞、而**结尾那段字面量还带字母**的，就是把本仓的词递到了读者手里。
**标点不算词**：收尾的 `}` 是调用者那个集合的括号，属于他们，不属于这里。
只问普通模板的那 14 行——**一行拿了规则，就等于接管了自己 id 的解析**，
它爱长什么样长什么样；这是同一条原则的另一半，不是它的例外。
反例构造了三条：带尾词的（该抓）、以洞结尾的、以括号结尾的（都该放行）。

**方法论沉淀**：(222)**一张按前缀键的表，读一条 id 的方式就是剥掉前缀，
于是前缀之后的一切都会被当作调用者的名字递出去**——所以本仓自己的词必须排在
运行时值之前；一个洞装不下两个值时，要的是规则而不是把两个值塞进一个洞。

全量 6084 passed / 145 skipped，mypy 133 Success。

### 假设的身份是 id 不是句子——一句话带着语言，而台账要按它分层（2026-08-21，#396）

全仓 31 个估计器里有一个用中文散文当假设声明：`regression_calibration`。
于是词表里有四行是按「这句中文怎么开头」键的——`("经典加性测量误差", ...)`、
`("聚类 bootstrap", ...)`。

**根因不是措辞，是键的类型错了。** 台账每一条要两样散文里没有的东西：
**它属于哪一层**（假了之后答案的哪一部分不成立）、**读者能不能去查**。
一个 id 能挂住这两样，一句话挂不住，所以词表只剩「匹配开头」这一个把手。
把中文键翻成双语键也救不了——**键不是给读者看的，是给代码匹配的**。
而一旦这个模块说第二种语言，英文声明不会以「聚类 bootstrap」开头，
它会静悄悄掉进「未分类」默认，**丢的是层级和严重度，不只是措辞**。

**改在估计器那一端**：它现在和其余每一个估计器一样声明 id。
- **粒度：每个被误测的列各一条**，而不是一条把它们全列出来。各自的 σ²_u
  来自各自的验证研究，各自可以单独错；**一条读者没法一块一块反驳的假设，
  是他没法行动的假设**（沿用 `outcome_error` 已经写下的那条判据）。
- 新词表两行与上面的 `outcome_error` 家族**成镜像，而镜像不对称**：
  结局那边 σ²_v 只给区间定价，这边 σ²_u **进入校正本身**
  β_true=(Σ_obs−E)⁻¹Σ_obs·b_naive——它错了动的是**点估计**。
  所以关于同一个量的同一句话，在这边是识别层，在那边是置信层。
- 「真实结局模型对真值线性」单立一行，**不复用旁边的 `linear_outcome_regression`**：
  后者是**怎么拟合的**，读者能看残差；前者是**世界是什么样**——真实模型对
  没人测到的值线性，而**正是这条线性使矩量校正精确而非近似**。
  它谈的那根轴上没有残差可看，这也是这一对里只有它标 untestable 的理由。
- 空调整集**不是空集合而是另一条主张**，所以用它自己的 id
  （`unconditional_exchangeability_...`，backdoor / aipw / tmle 三家已经这么做）。
  散文那边写的是「调整集 Z = {∅}」，把这层意思留给读者自己想。
- 那句「暴露连续；朴素 OLS 因回归稀释向零衰减」不是假设而是**后果**，
  删掉——它说的是校正的形状，而形状已经在 `model_assumption` 里说过一遍。

**四行里有一行是死行**：`("被经典加性误差污染的", ...)` 是为 `model_assumption`
写的，而那个字段去的是 mechanism_audit 块，**从来不经过这张表**。
一个从未被匹配过的前缀，在表里活了这么久，是因为它旁边三行是活的。

**闸口 `test_no_assumption_is_identified_by_a_sentence`**：150 个键，
一个都不许带非 ASCII 或空白。**不是「不许中文」**——一句英文句子当键是同一个
毛病，只是穿了代码碰巧用的那件语言。运行时**后缀天然豁免，因为它不是键**：
前缀之后那截是调用者自己的列名，可以是任何语言，本来就不归这张表选。
反例两条都构造了（中文键、英文句子键），且放行了一个真前缀。

三条分支都跑了一遍真数据（只误测暴露 / 无调整集 / 暴露+混杂且聚类），
七条声明全部命中分类、中英各一句、层级各就各位、`provenance` 全是
`inherent`——**withdraw 它就没有这个方法了，而不是答案变宽**。

顺带实证一个**先前就存在**的缺陷，另行登记（#398）：
`backdoor_adjustment_set_{z,w}_sufficient` 渲染成
「后门调整集充分：`{z,w}_sufficient` 阻断 X→Y 的所有后门路径」——
`_sufficient` 漏进了读者的句子。根因是**这个 id 的运行时部分在中间**，
而一张按前缀键的表只能剥掉前缀。

全量 6082 passed / 145 skipped，mypy 133 Success。

### 主报告整份换语言——一张分派表的接口是它的值的签名，而「按关键字到达」`Callable` 说不出来（2026-08-21，#390 档⑤）

`analysis_report.py` 的 **314 句 → 0**，368 条 `Words`，
`build_analysis_report(result, ..., lang=)` 进来，一路传到 60 个产出函数。
默认值只在入口，下面一个都没有——和档③同一条规则。
档④ 留的那行具名欠账 `_VERDICT_ZH` 死在这里，改回 `_VERDICT`，十种问句各一对判决语。
**那张欠账表本身也一起删掉**：它上一档存在的理由是「让整包闸口能在最后一个违规者消失之前先立起来」，
违规者没了，它就没了——**空的 parametrize 不是「没有欠账」，pytest 会把它渲染成一条 skip**，
和档② 从同一个文件里删掉的那条永远跳过的参数化是同一个形状。

**这一档真正的结构点是那五张分派表。** 问句一张、答案形状一张、答案块一张、
路线块一张、数值明细一张——每张的值都是一个渲染函数，
**表的接口就是这些函数的签名**。读者的语言是**按关键字**到达的，
而 `Callable[[dict, dict], str]` 只能描述**位置**，说不出这件事。
所以立三个 Protocol：`_QuestionLine` / `_ShapeRenderer` / `_BlockRenderer` / `_DetailRenderer`。
其中两个把位置参数设成 **positional-only（`/`）**——因为同一个形状要装不同家族的实现，
而各家族给那个容器起的名字不一样（`ne` / `block` / `ledger`）：
**不加 `/`，protocol 固定的就不是形状而是拼写。**

**翻译逼出的是重复。** 「（条件于 …）」这句话在三个问句函数里写了三遍，
其中两遍用 `_valued`、一遍用 `_atom_pred`——
现在是一个 `_given(entries, describe, *, lang)`。
信封散文的截断与补句号（`.strip().rstrip(".")` 再看末字符）写在两处，现在是 `_sentence`。
「- {标签}：{值}」这一行在中介分解、四分解、PoC 三处各写一遍，现在是 `_LABELLED_ROW`。
误分类那条更典型：原来是**一句话配一个自带空格的洞**
（`f" {by} "` 或 `"另一个变量"`），
洞里塞的是「值 + 它两边的空格」——现在是两句话，各自完整。
**同一句话在一门语言里写两遍像是习惯，在两门语言里写两遍就是两行会各自漂的记录。**

**跑一份 `lang="en"` 的报告看了。** 标题、状态、问题、答案、因果模型、图例、
验证的四条复核、页脚——整份英文。**剩下的中文全在它「引用」信封的地方**：
数据缺口那一节的每一条 gap、每一条 next step。
因为 `data_gap_report` 是**运行时**算出来写进信封的，
它的语言在那一刻就定死了，报告只是把它印出来。
`themis/output/sample_size.py` 那七句把这条缝说得最清楚：它有**两个消费者**——
缺口报告（渲染时，能问语言）和 `dispatch` 的 `precision_budget.hint`（运行时，写进信封，问不了）。

**于是 `themis/output` 从 1116 条降到 33 条，而这 33 条每一条都已经挂在别人名下**：
`bounds.py` 8 + `result_orchestrator.py` 13 + `sample_size.py` 7 是**信封散文**（#391），
`assumption_glossary.py` 4 是 #396，`formula_text.py` 1。
**渲染层这一档到此为止；剩下的不是「还没翻」，是「翻了也没用，因为语言在更早的一刻就定了」。**

测试里直接调产出函数的 60 处调用现在都说出语言——**它们和别的调用者没有区别**。

**方法论沉淀**：
(219)**一个参数是桩，往往不是没实现，而是它没有地方可以被递出去**（档④已记）。
(220)**一张按词表键出的分派表，它的接口是那些值的签名**——
参数按关键字到达这件事 `Callable[...]` 说不出来，它只能描述位置；
而当同一个形状要装不同家族的实现时，位置参数设成 positional-only，
protocol 才是在固定**形状**而不是在固定**拼写**。
(221)**同一句话在一门语言里写两遍像是习惯，在两门语言里写两遍就是两行会各自漂的记录**——
判据：翻译时发现自己在写同一个 `Words` 的第二份，那就是一处该合并的重复。

全量 6082 passed / 145 skipped，mypy 133 Success。

### 参数没有地方可去——`explain(result, lang)` 只有一张十个 `_zh` 函数组成的表可以递（2026-08-21，#390 档④，关闭 #327）

**根因**：#388 已经把「gloss 按语言命名」改成了「语言是参数」，但
`explain(result, lang)` 里那个 `lang` 仍然是 `NotImplementedError` 桩，
登记了半年（#327）。原因**不是没实现**：`_EXPLAINERS` 是一张十个
`_explain_effect_zh` / `_explain_cause_zh` … 组成的分派表，
**名字不接受参数**——`explain` 拿着读者的语言，下一跳是 `TABLE[kind](result, stmt)`，
而表里每个值都已经把语言烧死在自己名字里了。补实现的位置在**表**里，不在 `explain` 里。

**做法**：`explainer.py` 的每一句变成 `Words`——81 条，77 次 `language.fill/say/gloss`，
18 处签名接读者的语言；十个产出函数摘掉 `_zh`，连同
`_refused` / `_solved_without_point` / `_describe_adjustment` /
`_with_confidence_suffix` 等辅助一起接 `lang`。75 → 0，从欠账清单删行。

**闸口从「注册表」升到「整包」**。原来那条「名字里不许写语言」只守词表登记表里的
`glossed_by`——分母是注册表，因为报告自己的句子那时候还是由十个 `_zh` 函数写的，
守不了。现在它走 AST，**每个作用域都算**（函数 / 类 / 参数 / 赋值名），并配一个反例。

同批给它一个**豁免的正例**：`Lang.ZH` 的整个名字**就是**那个 tag，
它命名的是**语言本身**——连它一起扫掉，参数就没有值可取了。
所以判据是「tag **附着**在别的东西上」（一个名字在做参数的活），
而不是「名字里出现过 tag」。

**一行具名欠账**：`analysis_report.py` 的 `_VERDICT_ZH`（十种问句各一对判决语）。
它的名字**今天是诚实的**——表确实只有一门语言，先改名只会让名字撒谎，
而姊妹闸口那边还在按句子计数。所以记成一行，档⑤ 翻译时删掉。
**用具名行而不是计数**：名字不能被挪去顶另一个违规者，数字可以。

**方法论沉淀**：(219)**一个参数是桩，往往不是没实现，而是它没有地方可以被递出去**——
接收方是一张按名字分派的表，而名字不接受参数。
判据：看那个参数在函数体里的**下一跳**；如果下一跳是 `TABLE[key](...)`，
而表里的值各自把这个参数烧进了自己的名字，那么要补的是表，不是这个函数。

全量 6084 passed / 145 skipped，mypy 133 Success。

### 缺口报告的 160 句，和一个靠「剪掉中文前缀」取回名字的标签（2026-08-21，#390 档③）

**这一档没有根因要找——它是把 `data_gap_report.py` 的每一句翻过去。**
读者的语言穿过 41 处签名一路传到每个产出点：`compute_data_gap_report(..., lang=)`
进来，149 次 `language.fill` 出去。
**私有产出函数一律不给默认值**：`language.DEFAULT` 的含义是「调用者没说时给他什么」，
把它复制到 40 个产出函数里，就等于给「读者的语言在中途被丢掉」开了 40 个静默出口。
默认值只留在入口，那里才是「没说」发生的地方。

**`say` 全部换成 `fill`。** `say` 要求调用者自己写 fallback，因为它是给**查表**用的——
表里可能没有这一行，而那一行的替代品只有调用者知道。一个模块级的句子没有 token 可以退回，
和 `fill` 的处境一模一样：**缺了读者的语言就该抛，因为没有第二样东西可以递给读者**。

**翻译逼出两个真缺陷。**
① `_short_label_for` 取回分布名的方式是**从 `description` 上剪掉中文前缀 `"缺概率分布 "`**。
第二门语言一进来这就散了——**一句话在读者的语言里，名字不在开头**。
改成读产出方自己写下的 provenance（`ref_id` 去掉 `parameter:` 前缀），
和同一函数里「含糊变量」那一支本来就在做的事一样。
② 同一张标签表里，一条说 `P*(...) **on** user`，它的兄弟说 `... **在** rct_meta **上**`。
**两个读者，一个也没被写给。**

**8 条中文针不是句子，是针。** `_MEASUREMENT_ERROR_PATTERNS` 里的
「自报告 / 问卷 / 单次测量 / 代理」是拿去和**用户变量声明**里的 `measurement` 字段比对的，
所以决定它语言的是**程序的**语言而不是读者的——两门语言故意混在一个池子里，
**按读者拆开，反而认不出用另一门语言写的声明**。这是 `Wrote.QUOTED`：到达读者的是**匹配上的那个子串**，
按用户写的原样引回去。另有 `_RaisedElsewhere.reason` 一条英文是 `Wrote.UNREAD`——
遇到它的那一趟直接 `continue`，从不打开这个字段。

**`_Renderer` 变成 Protocol。** 读者的语言按关键字到达，
而 `Callable[[...], ...]` 只能描述**位置**，说不出这件事。

**160 → 0，`data_gap_report.py` 从欠账清单上删行。**
同批加两条豁免（上面两条），并把 `bounds.py` 8 条与 `result_orchestrator.py` 13 条
标注为**信封散文**：它们写进 `BoundsResult.notes` / `extensions.*`，是档3（#391）的，不是渲染层的。

**方法论沉淀**：(218)**一个函数去读另一个函数的「输出串」而不是它们共同的输入，
就把那个串的形状变成了接口**——而散文的形状里含着它的语言。
判据：扫 `startswith(` / `[len(...):]` / `.split(` 落在 `description` / `summary` / `reason`
这类字段上的地方，逐个问「这里要的那个事实，产出方是不是已经把它写在别处了」。

### 138 条断言各只说一门语言，而「自己填洞」的豁免只有一行长（2026-08-21，#390 档②）

**根因：这张表把「一条假设是什么」和「怎么把它说给读者听」写成了同一个字符串。**
一个 id 对应一句中文，前缀规则再把 id 的尾巴接进那句话里——
于是「加一门语言」不是给表加一列，是把表的形状换掉。

**换成的形状：一条假设有一个 id，id 底下挂一个 `Words`，洞是有名字的。**
138 条精确 id 走 `_EXACT`，8 条前缀规则走 `_PREFIX`；
前缀那侧的尾巴要么原样填进 `{suffix}`，要么交给一个函数拆——
工具变量和结局各自成一个槽，单调方向去查 `monotonicity_word(direction, lang)`。
`classify_assumption(assumption, lang)` 因此多了第二个参数：
**信封不带语言**，读者的语言只能在渲染时到达它；谁来选是档④的事（#395）。

**两个类型分开，是 mypy 指出来的一件真事。**
`_EXACT` 的第三格只能是 `Words`，`_PREFIX` 的可以是 `Words` 也可以是一个填洞函数——
起先合成一个联合类型，`language.say` 就收不下了。分开之后类型自己说了句话：
**一个精确 id 没有尾巴可读，所以「规则」这个形状只属于前缀表。**

**豁免清单空了，于是删掉的是清单本身。**
`FILLS_ITS_OWN`（「这个模块自己填洞」）只有一行，就是这个模块。清干净它之后剩下的
会是一个空清单，外加一个永远 skip 的「这条豁免还在用吗」参数化测试。
**一个空清单配一个跑不起来的守卫，比规则自己把话说完还要少说一点**——
所以「需要例外就在这里说明理由」并进了规则的失败信息，机制整个删掉。

**146 → 4，而剩下的 4 条不是断言，是键。** `regression_calibration`
把中文散文当作这条假设的身份声明，这张表只好靠句子怎么开头去认它。
它们计数，因为它们确实是同一句读者的话被写了第二遍；它们会在那个估计量
像别的估计量一样声明一个 id 时消失——**修在那里，不修在这里**（#396）。

### 规则问的是「旁边有没有语言」，而豁免里的那个「或」压着 276 条拒答（2026-08-21，#390 档①）

**根因：规则本身是在只有一门语言的时候写的。**
「kernel 写读者的语言，英文需要理由」——只要读者的语言只有一种，这条读起来像在问语言；
两种之后它就假了：**给英文读者写的词就是英文，这不构成任何证据**。
把它重新问一遍，才看清它一直想问的是另一件事：
**这条文本的旁边，有没有写着它是哪一门语言**。这样问，问题里就不再提到「哪一门」。
于是全仓只剩**一条**规则，覆盖每一条能到达读者的文本：
**它坐在一个说出自己语言的键底下，否则它是欠账。**
两个探测器喂它——中文在字形里自己宣告，英文得先和公式分开——
这是两门语言唯一被区别对待的地方。

**这样一问，删掉了一条豁免，劈开了另一条，还反向纠正了第三处。**

① `Wrote.HELD` 豁免拒答通道，理由写的是「该用哪种语言到达读者，不归这条规则决定」。
**那是给一个问题起了名字，不是给一个答案起名字**——而上面这条规则回答了它：每一门。
表里 12 条随之删掉。HELD 上**一条中文都没有**、123 条英文（按节点计），
其中 `estimator_failure.reason` 是两个读者面都在打印的。

② 每一个 `raise` 都被豁免，理由是「这里的异常，要么是开发者读的不变量，要么是正在去
拒答通道的话」。**只有前半句与读者无关**，而语法里本来就分得开：
**这个包在断言时抛内建异常，在拒答时抛自己定义的异常**。那个「或」后面站着
**276 条**（43 个模块）。`super().__init__` 因此不再需要单独一条豁免——
一个类是自己定义的，它就在拒答。

③ 反方向也有一条：`Refusal.says` 的 69 条英文**不是**欠账。它自己的 docstring 就写着
「不是读者的句子——那是场合的，是 block 上的 `reason`」，且一个写入者、零个读者。
它是 `UNREAD`。**闸口是变准了，不只是变大了。**

**欠账清单 `STILL_ONE_LANGUAGE`：1369 条 / 62 个模块，逐模块精确计数。**
形状抄本仓 `mypy.ini` 已经在用的那个：规则覆盖全仓，例外逐条列出且只能变短。
**精确而不是上限**——上限就是「还能再加一条」的余地。
清干净一个模块＝删一行；往旧模块里加一句新的单语言中文，同样见红。

**再加两条规则。**
④ **一句话在每种语言里要的东西必须一样。** `format` 填它拿到的、丢它没拿到的，
所以一份漏了槽位的翻译渲染出来是一句短一点的话而不是一个错误，**下游没有任何东西看得见**。
这条规则第一次跑就抓到一条真的：前门那句结局测量误差的英文半边还带着位置槽 `{}`，
中文半边已经是 `{factor}`（#389 改名时那处夹着 markdown 粗体，没匹配上）。
规则同时覆盖 kernel 与浏览器（167 ＋ 172 个 `Words` 字面量），
**浏览器那侧更要紧**：它用 `replace` 填洞，没填上的洞会原样印在页面上。
⑤ **填洞是 `language.fill` 独占的。** `say` 在缺语言时返回调用方给的兜底，
而一句话的兜底是空串——`say(...).format(...)` 会**把空白递给读者并报告成功**。
`fill` 改成抛异常（一句话没有标识符可以顶替）。全仓只有 3 处 `.format(`：
`fill` 自己，外加两处手工填的，其中一处是**拒答**——读者本来会一个字都收不到。
`assumption_glossary` 是唯一具名例外（它的模板还是单语言＋位置槽，那是档②的活）。

**而这两条规则的分母自己也得有人管。** 第一版浏览器扫描只认「每种语言一个串」那种
`Words`，于是 `Words<T>`（一个档位的 label ＋ gloss、一个状态的 label ＋ blurb）
**50 个语言键一个都没被看见**，两条规则在它们上面平凡通过——正是 #373 那个失败的形状。
补的不是一个 case 而是两件事：**读第二种形状**，以及**把分母钉住**——
不是谁数出来的一个数字，而是「语言标签被当作键写下的次数」，
每种语言每个 `Words` 恰好一次。kernel 334/334，浏览器 344/344。
第三种形状（模板字符串、f-string 拼出来的 `Words`）现在到达这里的方式是
**一个没人够到的标签**，而不是沉默。

**守卫（十一个方向，每个都在 `themis/` 里造了反例见红）**：不在清单上的模块写单语言 /
清单上的条数变多 / 清单上的模块已清空 / `raise ValueError(...)` 不算 /
`raise EstimatorFailure(...)` 算 / 一门语言丢了槽 / 两门语言都用位置槽 /
手工 `.format` / 被豁免却已经不再填 / `Words` 在使用处用 f-string 拼出来 /
浏览器的 `Words` 写成模板字符串。

**基线**：6023 → **6082** / 145 skipped。mypy 133 Success。前端 `tsc -b --force` 干净。

**方法论沉淀**：(217)**一条豁免的理由里出现「或」，它就是两条豁免捆在一个名字上，
而规则的强度等于较弱的那一半。** 判据：把理由拆成两句，逐句问「这一句单独成立吗」。
更隐蔽的同族形态是：**豁免的理由是一个问题而不是一个答案**（「该用哪种语言不归这条规则
决定」）——那是一次搁置，而搁置一旦写进例外表就再也看不出来，因为它和一个决定长得
一模一样。找法：把每条豁免的理由读一遍，逐条问它是在陈述一个事实，还是在说「我们还
没决定」。

---

### 「答得出」和「有词」是同一个集合，第二门语言把它们掰开（2026-08-21，#389 / #327）

**根因：`Lang` 一个名字同时承担两件事**——「读者可以被用哪些语言回答」（门开不开），
和「每条给读者的文本必须存在于哪些语言」（完备性按谁点名）。
只有一门语言时这两件事永远同真同假，所以从没分开过；第二门一来就必须错开：
闸口规定**没有任何文本写在一个 build 不应答的语言里**，所以英文没法先攒；
而 `Lang.EN` 一旦存在就等于宣布「这个 build 能用英文回答」，那要求每个面同时齐。
两个顺序都走不通——**卡住的不是提交大小，是两件事共用一个名字**。

**做了什么（两次提交，顺序本身是纪律）**

**档 A：先立闸口，一个英文都不写。** `ARRIVING` 与 `Lang` 并列，`written()` 是并集。
`Lang` 只管门（`explain` 让谁进、选择器能提供什么）；
**`written()` 是全仓每一条完备性检查的分母**——标签一进 `ARRIVING`，
现有闸口立刻开始逐成员点名，它豁免不了任何东西。
`Lang` 单独还管着的，只剩**今天还没有任何闸口的那些面**（#390 渲染层 / #391 信封散文），
这也正是把标签升进 `Lang` 所断言的东西。
浏览器补上它缺的那一维：20 张表从 `Record<string, string>`（其中 14 张把语言拼进表名）
改成 `Record<string, Words>`，每个取词处都收 `lang`，闸口按**每表每成员每语言**点名。
**合法性交给编译器而不是再写一条规则**：`Words` 由 `Lang` 索引，写错标签是编译错误。

三处是判断而不是改写：`answersIt`（那个布尔到底是不是答案本身）**留在语言轴外面**——
它是关于问题的事实、对每个读者都一样，塞进 `words` 就成了自己的第二份记录，
可以对一个读者说「结论」、对下一个说 identification，而说的是同一份结果；
拒答对没见过的 kind 返回 null、对见过但这门语言没句子的返回标识符（**成员缺失 ≠ 词缺失**，
合并了会让一句缺失的英文把整个拒答框删掉）；三处 risk-provenance 同理。

**档 B：把 `en` 放进 `ARRIVING`，388 条英文写在对应中文旁边。**
kernel 侧 94 条词表成员 + 58 条推导链句子 + 14 条审计行；浏览器侧 221 条 + 1 条散的。
**先设标签、一个字不写地跑一遍——32 条测试逐个报出缺口**：
23 个词表、推导链、审计行、浏览器 20 张表、跨面拒答钉。没有谁需要「记得去找」。

**两条闸口本身错了，而且是同一个错：读了「串」而不是「槽」。**
① 完备性检查原来拒绝「词等于成员标识符」——在标识符是英文、词不是英文时这是对的，
词也是英文时就假了：`blocking` **就是** `blocking` 的英文词（还有 `high`/`binary` 等 11 个）。
改成**问这个 gloss「没有文本时你说什么」再比对**，即直接问它想问的那个事实。
② 「没有句子用错语言到达读者」这条扫全仓字面量、报告英文小句——
它的规则（kernel 写读者的语言，英文需要理由）也是一门语言时写的，
166 条**正确的**英文会被它判违规。加第五种豁免，且**由结构判定而非列表**：
**一个字面量坐在语言键底下，它的语言就是那个键说的**，槽名从词表派生，第三门语言不需要加任何条目。

**审计行原来根本没有逐语言检查**——它是词表登记册够不到的一张表
（审计行是调用方收到的凭据，不是某个词表的成员）。这一档补上。

浏览器复述 kernel 的地方，**英文直接取 kernel 的**（运行时读表，不是再翻一遍）。
一个例外，而且是两个面的差别不是意见的差别：报告写 markdown、这个面写进 span，
所以 `**` 在过界时被剥掉。浏览器自己的措辞（缺口标题、状态说明、问题的两种读法）是它自己的。

**已登记的漂移说清楚**：那 20 张表里有 3 张的中文与 kernel 已经不一致
（`c-factor 分解`、一对括号全角/半角、markdown）。这一档不动它（#394），
但**每张镜像表的英文从出生起就是同一份**，所以分歧现在只剩中文这一半。

`tests/web_source.py` 学会两件事：**引号里的串不是它的拼法**——
英文句子自带撇号，单引号 TS 串把它写成 `\'`，有三条钉把转义读了回去，
于是把两份**完全相同**的拷贝报成不同（唯一一个看起来像漂移而其实不是的方向）；
以及 `entry` 现在在任意位置找键而不只在行首——`answersIt` 需要这个，
它不再和成员的左花括号同行之后，`test_question_readings` 自己那条正则**悄悄变空而不是失败**。

**基线**：5983 → 5991 / 146 skipped（档 A）→ **6023** / 145 skipped（档 B）。
少的那个 skip 就是「没有任何语言只在路上」那条——档 A 里参数集是空的，档 B 里它有话说了。
mypy 133 Success。前端 `tsc -b --force` 干净。

---

### 读者的语言是名字的一部分，所以它没法被请求（2026-08-21，#388 / #327）

用户要「一个语言选项，让中国人和外国人都可以用」。**这不是「翻译没做」。**

**根因：语言被烧进了三处「身份」，而不是当成一个参数。**
23 个 gloss 把它拼进函数名（`scale_zh`）、8 张表拼进表名（`_PATTERN_ZH`）、
4 个词表拼进字段名（`Layer.zh`）、还有一处拼进 **JSON 键**（audit 行的 `"zh"`）。
**一个名字接不了参数**，所以「用英文回答这个读者」在当时的结构里**根本不是一个能提出的请求**——
这正是 `explain(result, lang="zh")` 从 v0.1 起就带着一个 `lang` 却对除 `zh` 外一切
`NotImplementedError` 的原因：**参数是对的，只是无处可去**。

**「加一张中→英表」这条路也不通**：到达读者的串里有 **427 个是插值拼出来的**，
中文句子不是常量、当不了键。缺的从来不是翻译，是**那个不带任何语言的事实**——
而它一直在：词表成员自己的 token。

**做了什么**：新增 `themis/language.py`——`Lang` 封闭词表（**今天只有 `ZH`**）、
`Words`（一件事的文本按语言排）、`token()`、`say()`、`gloss()`。
两份互不知情的 `_describe` 并成一个：`ledger` 那份走 `_token()`（拿到成员也对），
`envelope_glossary` 那份走 `str(value)`（拿到普通 `(str, Enum)` 成员会渲染出成员地址，
正是 #382 的病）。23 个 gloss 目标全部改成 `(value, lang)`；
`Layer/Severity/Provenance/RiskProvenance` 的 `zh` 字段变成 `words`；
audit 行的 `"zh"` 键变成 `"words"`（**行是凭据不是渲染**，先替读者选好语言的凭据
会让两个读者需要跑两次）；浏览器同步 `lib/language.ts` + `AuditRow.words`。

**顺序是刻意的：先建闸口，再迁移**（方法论 (213)）。
`Lang` 今天只有一个成员，所以 `test_the_gloss_answers_for_every_member`
（现在按 **成员 × 语言** 参数化）**平凡通过**——
**加 `Lang.EN` 那一刻，它会把每一个缺英文的成员逐个点名**。
不需要谁记得去找。

**新闸口 `tests/test_the_language_is_a_parameter_not_a_name.py`（38 条）**，
每条都配了它该拒的反例：写在一个没人应答的语言里的文本、
`words` 是一个裸字符串、gloss 名字里带语言标签、
浏览器多一门 / 少一门 / 默认成另一门语言。
并钉住**不回退**：某语言缺文本时渲染成 token，**绝不悄悄改用另一种语言**——
一份半个语言的报告是缺陷本身，不是它的修法（#372 就是这个）。

**这条闸口够不到哪儿，说清楚**：浏览器那边只钉住了「TS 的 `LANGS` 等于 kernel 的 `Lang`」，
**没有**「浏览器每张表的每个成员在每种语言里都有词」——因为它的 20 张表今天是
`Record<string, string>`，**根本没有语言这一维**，那条闸口写不出来。
于是「`LANGS` 说能用英文、页面全是中文」这个失败**今天没有任何东西挡**。
#389 里先把表转成 `Record<string, Words>`（只填 zh，闸口平凡通过）再加 `EN`，
就是补这个缺口——**一个说自己覆盖了却看不见那一半的分区，比一个说出自己边界的分区更不值钱**。

**量出来的分档**（#389/#390/#391）：活的中文字面量 1668 条 / 44 模块，
其中 **552 条在 kernel 内**；信封上 **69 条路径带中文、2769 条串**。
要写第二遍的不是这些串，是它们背后**不同的源码模板**——f-string 的模板在源码里是常量，
按这个算全仓 **1175 条**，`themis/output` 占 **828**（#390），**kernel 那半 347**（#391）。
（语言闸口原来的 `PROSE` 表只有 20 条，是因为它的分母判据要「含空格 + ≥2 拉丁词」，
而**中文句子不带空格**——对它抓英文小句的用途是对的，不是语言选项的分母。）

**基线**：5941 → **5983**。mypy 133 Success。前端 `tsc -b --force` 干净。

---

### 四个数据指纹坐在一份答案上，没有任何东西比较过它们（2026-08-21，#385 / #383）

一份答案可以同时带着：这次运行的数据契约、估计器自己的、界的、以及验证器要走的那条推导步骤里的。
**十五条规则各读一次 `inputs["data_hash"]`，各自只检查同一件事**——是不是 64 位小写十六进制——
**没有一条去看第二个**。于是一份「界在 frame A 上算、点在 frame B 上算」的信封
**通过了现有的全部检查**，读者拿到的是同一个问题下关于两张表的两个区间。

**这条关系在指纹带上分母之前写不出来，因为「相容」不等于「相等」**：Manski 界要的是暴露和结局，
而它所包住的那个点估计还要调整集，**两个 digest 本就该不同**。要成立的是——
**digest 是它覆盖的那批列的函数**。

**五条关系，每一条都先在「套件产出的每一份信封」上量过才写下来**——
312 份带指纹、13 种不同的指纹形态、**五条全部零例外**：
1. 分母是一份非空、不重复的列名清单；
2. **同一份清单必须给出同一个 digest**，否则是把两次运行报成了一次；
3. **不同清单必须给出不同 digest**，否则这个 digest 是被**抄**过去的而不是算出来的
   （`_hash_frame` 把每列的**名字**先混进去，所以不同清单不可能算出相等）；
4. 没有任何答案立在 `estimation_context` 没记录为「到达过」的列上；
5. **没有分母的那种指纹，必须等于某个有分母的指纹**。

**它是信封上的一条规则，而不是塞进十五条生产者规则里**，因为这个断言**是块与块之间的**。
十五份互不知情的比较各自对一对是对的、对其余沉默；而推导步骤那一个，
不扩每条规则的声明参数集就**从任何一条里都够不着**。

**第 5 条顺带把 #383 关掉了。**普查说：推导步骤上 **230 个指纹全部没有分母**，
而其中 **218 个全部匹配 `numeric_estimate`**，无一例外——所以「推导链讲的是另一张表」
这个失败在这里被抓住，**不用改那十五处**。更严的写法（某一步的指纹要配**那一步产出的那个块**）
需要一张 rule → block 映射，而**今天没有任何输入能行使它**：没有任何路线产出带指纹的界推导步骤，
**那张映射会是一个说不出「不」的闸口**。已登记触发条件，到那天再做。

**接线与其余审计同形**：`AUDITS` 里一行（守在 `estimation_context` 上）、
公开的 `themis.verify_fingerprints_agree`、以及 `verify` 里与其他信封级审计并排的一次调用。
一条既有测试**把「审计答案之外的东西」的行数写死成 4**；现在重算答案的那四条仍按名字钉住，
其余**按「其余」算**——**加一条审计不该读起来像一次失败**。

**基线**：5928 → **5941**。mypy 132 Success。

---

### 一个字段装着「digest 覆盖什么」和「矩阵怎么读」，而 docstring 说的是第三样（2026-08-21，#384）

discovery 的两个结果各记一份 `columns`，**它在做两件事**：作为**集合**它是 `data_hash`
覆盖的那批列；作为**顺序**它是下游一切的索引顺序——返回边里的节点 id，
以及旁边那份充分统计量（`correlation` 的行列、`contingency` 的 config 元组）的行列顺序。
两者是**同一批成员的不同顺序**，所以一个名字必然对其中一件为假——
**而两处 docstring 都答了第三样**：「canonical order」，两件都不是
（`validate_data` 里 hash 走 `sorted(required)`；`discover_graph` 记的是调用方 / DataFrame
的顺序，`markov_blanket` 记的是 `(target, *pool)`，代码里明写 `# target first`，
而 `t_idx = 0` / `cand_idx = 1..` 直接依赖这个顺序）。

**只改名是错的。**把它叫 `data_columns` 会把「统计量的索引顺序」带进一个在另外五个容器里
意思是「digest 走过的顺序」的拼法——**让一个名字在包里指两种顺序**，比原来的含混更糟。
所以是**拆**：`data_columns` 与其余五处逐字同义，`columns` 留给索引顺序，
两处 docstring 各说自己真正是的东西。

**让这次拆分承重而不是整洁的，是 digest 只能从其中一份重算出来。**
闸口用一个**故意不按字典序**建的 frame 跑一遍：`_hash_frame(frame[data_columns]) == data_hash`，
而 `_hash_frame(frame[columns]) != data_hash`——`_hash_frame` 把每列的**名字**先混进去，
所以顺序是 digest 的一部分，两份列表**不可互换**。期望值是**独立重算的**，
不是拿生产者也写过的另一个字段去比。

**分出去的一半**：这两个块**在任何 schema 之外**——`kernel_ast` 的 `extensions` 是
`{"type": "object"}` 开口袋，而 `markov_blanket` 是**六种 artifact 里没有 schema 的五种**之一
（另四种是 orientation 那组，都不带 hash）。#381 的指纹闸口分母是「schema 描述过的容器」，
所以它够不着这里——**不是拼错了名字，是没有任何 schema 说它存在**（#387）。

**基线**：5920 → **5928**。mypy 131 Success。

---

### 那个基类有意放弃了同一性，而 35 处在花它（2026-08-21，#382）

`EnvelopeName` 改写了 `__reduce_ex__` / `__copy__` / `__deepcopy__`，
让被复制或被 pickle 的成员**变回纯 `str`**。这就是它存在的理由——**信封是数据，
序列化它的人不该连注册表一起收到**。而它是拿**同一性**去换这件事的，
全仓却有 **35 处 `x is <词表>.MEMBER`** 在花那份同一性。

**35 处今天没有一处是假的，这是量出来的不是推的**：`themis/` 下全部 23 处
`copy` / `deepcopy` 都在叙事层、对象是 program AST，没有一处复制过携带这些词表的值。
**值得删掉这个形状的是它坏掉的方式**：坏在未来某次复制、坏在一处没人再看的比较里、
而且**是静默的**——这 35 处里有一处决定 Manski 区间收紧哪一侧，
被复制过的值在那里产生的是**一个错答案**而不是一个异常。

`==` 对成员和它变成的字符串都成立，所以改动今天行为不变、复制之后仍然正确。
**跨词表的值冲突先量过**才敢这么说：只有一个（`identification`，Block 与 Layer），
而这 35 处一处都不涉及。

**这条规则把线画在基类上，不是画在 `is` 这个词上。**普通 `Enum` 保留成员单例，
对它用同一性是**对的**——`ResultStatus`、`Role`、`AnswerTier` 上约三十处**原样不动**。
这条线买到的是**迁移**：某个词表继承 `EnvelopeName` 的那一天，
每一处原本没问题的比较都变成缺陷。

**`Monotonicity` 就是这么迁的。**#380 量到它是普通 `(str, Enum)`、`str(member)` 答的是
**成员的地址**，于是 gloss 落到 fallback、一条测试靠两个 fallback 互相比较通过了；
当时因为那几处同一性判断**推迟了迁移**。有了闸口，迁移是机械的：改基类、跑闸口，
它点名 `bounds.py:342` 与 `counterfactual.py:240/242`——**三处，由规则找出来而不是靠记性**。
这也是这个闸口被验证的方式之一：除了三个构造的反例，还**在改前的源码上重放过**，
35 处一处不漏。

**已登记未做**：还有 **19 个词表** 的 `str()` 仍答成员的地址。
**今天有没有一个地址真的到了读者，没有量**——JSON 是安全的（str 子类按值序列化），
唯一暴露的路径是插值，而 #380 那五个缺陷正在那条路径上、**扫字面成员引用看不见**。
迁之前要先量清楚哪些**真的上信封**：其中几个看着是内部路由词表（#386）。

**基线**：5773 → **5920**。mypy 131 Success。

---

### 指纹从不带上它的分母，于是「和什么一样」没有答案（2026-08-21，#381）

`data_hash` 是**这份数据的指纹**：它把每一列的**名字**、再把这一列的值混进
SHA-256。**五个容器带着这个指纹，零个带着它覆盖的列集。**指纹存在的唯一用途是
回答「和什么一样？」，而没有分母时，两个不同的指纹只能说「不是同一次运行」——
**说不出变的是被测的值，还是被测的列**。

这个缺失有一个具体的受害者。#377 那条「这个答案立在哪些列上」的读法当时**没有槽位**，
散在约十个不同名字的键里（四个块下的 `adjustment_set`，加上 `instrument`、
`conditioning`、`mediator`、`s_nodes`、`selection_nodes`、`design_vars`），
所以两边都只能过近似——收集文档里出现的每一个字符串——并把这件事写进 docstring：
**「等它有了槽位，这个读法就变成一次字段读取」**。

修法：五个容器各带 `…data_columns`（32 个 dataclass 字段、35 个构造处、
28 个字面 dict 信封块 + 1 处赋值式的 bounds 行）；schema 用 **`dependentRequired`**
把分母绑在指纹上——**不是 `required`**，因为五个里有两个的指纹本身可选，
无条件必填会替它们说一句假话；闸口的**分母由 glob 发现**（`themis/schemas/*.json`），
三种坏法各构造一个反例（不声明属性、不绑 `dependentRequired`、类型写错）。
读者那一面也补上：审计页脚是这个指纹**唯一到达人的地方**，此前印的是截断的十六进制、
旁边什么都没有；现在它说出覆盖了哪些列，**且两者从同一个容器读**——
各取一个容器会把指纹和别人的分母印在一起，那正是第二份列表要防的混淆。

**过程中度量到、并且改变了做法的三件事。**

**那句「等它有槽位就变成一次字段读取」是过头话。**它假设每个答案都是一个数。
识别层的答案是一个**估计量**，它立在哪些列上仍然只能从结构见证读，而信封在约十处
说那件事。所以现在是**两条读法**，并写明各自管哪一种答案：有数就读它自己那份分母，
没数就退回原来的近似（出错方向仍是 block 得更多）。

**更要命的是：只加字段会把 #377 静默地弄坏。**`estimation_context` 的分母是
**到达了什么**——程序声明的每一个谓词，包括没有任何查询估计过的那些。原来的走法
收集文档里每个字符串，**新加的这份列表一进来，它就对每一列都说「立在上面」**，
正是 #377 修掉的那个缺陷。所以「排除按运行的那份分母」不是整洁而是**承重**，
并由一条测试钉住（往 `estimation_context.data_columns` 里塞一个假名字，读法不能变）。

**验证器那份「独立孪生」在这一条上从来抓不到东西。**两边用同样的办法、从同一份
文档、猜同一个只有生产者知道的事实——**按构造必然一致，是一条不可能失败的规则**。
现在生产者**声明**列集、再拿自己的声明去给每条 gap 定级，两者可以不一致，
而那个不一致才是这条规则审的东西。新写的两条测试正是**此前不可达**的失败：
声明 `{x, y, z}` 却拿 `w` 收费，以及反过来把分母加宽却留着窄的定级。

**还有一件关于「怎么找齐」的：**第一版 part 2 是**按行长得像**改的，41 行里有 12 行
是 `DerivationStep(inputs=...)`——一个 inputs 键是某条规则**声明的参数**，未声明的键
会被拒绝，于是 345 failed / 44 errors。改用 AST 按祖先分类之后分清了 29 个信封块 vs
12 个规则参数；**而这一版仍漏了一个**：`terminal_inputs` 先赋值给局部变量、再传进
`inputs=`，**语法上不在那个调用里**。「在这个调用里」这个判据本身有两种写法。

**这条改动自己犯了它在讲的那个错，并被度量抓住。**给
`boundsResult.numeric_data_columns` 写描述时，我写了一句「界和点估计说的是同一份数据，
当且仅当这个列表和 `numeric_estimate.data_columns` 相同」。量一遍：同一份结果上点估计的分母是
`(x, y, z)`、Manski 界的是 `(x, y)`，**两个 digest 因此不同，而两个答案说的就是同一份数据**——
这句话是假的。它错的方式正是本条在讲的 (208)：**把一个可检查的关系写成散文，于是没人核对过它**。
描述已改成只说这个字段**是什么**（这个 digest 的分母，通常比点估计的窄，因为界要的列更少），
真关系交给一条会跑的规则——**而那条规则今天不存在**：一份结果上并存 2–4 个指纹，
没有任何东西要求它们相容，验证器对 `data_hash` 只做「是不是 64 位十六进制」、**从不比较任何两个**。
已登记（#385）。

**排除项（都已登记）**：推导步骤 `inputs` 里的 12 个 hash 不给分母（#383，要扩约 15
条规则各自的输入集）；`discovery.py` 把同一个事实拼作 `columns` 且那两个块不在
schema 里（#384）。

**基线**：5752 → **5773**。mypy 131 Success。

---

### 方向没有「读者的词」，于是五个生产者各写了一份（2026-08-21，#380）

`Monotonicity` 是信封携带的封闭词表，而它**在任何地方都没有一份读者的词**。
五个生产者各自替它回答了这件事：**四处把 token 插进中文句子**——反事实单格的台账 claim、
IV 块的 required_assumption、以及假设词表的两条前缀模板（`单调性（non_decreasing）`）；
**一处手写了一对英文从句**塞进中文 notes，并在同一句里放了裸的 `lower` / `upper`。

**本该接住这件事的登记册，用一句写下来的理由把它放行了**：
「它产生的台账行才是读者面，那一行用词说出了方向」。**而那一行印的是 token。**
这句话是假的，且**从来没有任何东西要求它为真**——`Vocabulary.no_gloss` 自己写着
它是「a claim rather than an exemption」「the sentence somebody has to disagree with」，
**39 条 `no_gloss` 对 22 条 `glossed_by`**。

**这种形状的理由就是写成散文的 `glossed_by`**：如果某个面给每个成员一个词，
那就存在一份按成员的映射、可以被命名；如果不存在，那句「有一个面用词说了它」就是假的。
所以这一行现在写 `glossed_by="themis.ledger.monotonicity_zh"`，
由登记册自己那条按成员的检查（**用 token 回答就不算 gloss**）去做那句话在做的事。

**第二条规则**：五处都走它——**一个台账词表的值被插进中文句子时，要经过它的 gloss**。
分母是 `themis.ledger` 导出的 `*_zh` 名字 × `themis/` 下每个模块，**两个都不是谁维护的清单**——
这正是重点，因为缺陷本身就是**五个没人列过的点**。同一个值插进标识符里
（`mtr_{d}`、一个 assumption id）仍是 token，而这条线正是语言闸口已经画好的那条。

**过程中度量到的两件事，都值得占篇幅。**

**`Monotonicity` 是普通的 `(str, Enum)` 而不是 `EnvelopeName`**，所以 `str(member)`
是 `Monotonicity.NON_DECREASING`——**成员的地址而不是它的名字**。gloss 落到了自己的 fallback，
而一条为检查 notes 而写的测试**靠两个 fallback 互相比较通过了**。这里的修法是先读 `value`；
**把它改成 `EnvelopeName` 已另立待办**：那个基类让 copy / deepcopy 返回纯 `str`，
而代码里有 `monotonicity is Monotonicity.NON_DECREASING` 这样的同一性判断——被复制过的值会**静默**地不等。

**那条显而易见的更宽的规则不成立**，这件事记在这里而不是记在时间线上：
「读者面字面量里不得出现成员 token」在文档之外命中 **53 条**，而**几乎全部是英文单词本身而不是词表成员**
——`bounds`、`transport`、`effect`、`interpretation`、`marginal` 正是中文技术散文会借用的词。
**任何对文本的读法都分不开这两者**。插值规则分得开，因为那里的值是**运行时从词表来的**，
不是从谁的句子里来的。

**基线**：5611 → **5752**。mypy 131 Success。

---

### 工具变量只活在那句散文里，于是审计它的办法是「搜索」（2026-08-21，#379）

Balke-Pearl 那一行印的是**对一个线性规划的引用**——一般基数下没有闭式可印。
而这个引用是**一句话**，且**这一行里工具变量只存在于那句话里**，
所以负责确认它的规则**对那句话跑了一个正则**。

这一下两个方向同时错。**换个说法就把审计弄坏了**，因为审计读的是措辞：
`startswith("min of P(")` 是对开头短语的检查。而**拟合到错变量上却弄不坏它**，
因为「一句关于错变量的正确的话」形状是对的——句子写 `z`，正则捞出 `z`，规则和自己达成一致。

现在**这一行把工具变量作为字段携带**，规则**读它**，并**对着图核**：
一条入处理的边、零条入结局的边。这个条件**是必要而非充分的，并且被明确写成如此**——
候选有没有可枚举的域、模型在不在生产者的规模上限内，是**生产者关于数据和自身限制**的问题，
一条审计「命名了哪个变量」的规则无权把它们借过来。必要条件仍然拒掉了值得拒的那类：
**这张图根本给不出的名字**。

`estimand` **第一次真被检查**。docstring 说它被检查；站在那里的其实是那个开头短语，
它承载「界的是一条臂，不是 ACE」——只承载到有人改写它为止。
表达式只保留一项义务，即**一个渲染欠读者的那一项**：说出你渲染的东西——
目标、那条臂、工具变量，且**臂只说一次**（带两个 `do(X=…)` 的句子界的是一个差，
不管字段写了什么）。

**「这是区间的哪一端」不再被审计，这是决定不是遗漏**：方向就是槽位本身；
操作符词是它的渲染；**用「找这个词」去审它，会拒掉任何谓词里含这个词的程序——`vitamin` 里含 `min`**。
要让它可审，得让操作符变成**有封闭词表、每种语言一份渲染**的 token——
那正是单调方向已登记的形状，不该由某一条规则在某一个槽位上自创。

**这个字段其实早就存在**——发现这件事是本次的第二半。`_fill_numeric_bounds`
一直在写 `bounds["instrument"]`，schema 也声明了它——声明成**「数值端的」字段**。
**用「谁写的它」而不是「它是什么」去描述一个字段**，于是符号端不认得这个槽位是自己的，
就在旁边**又加了一份同名声明**。而 **JSON 对重复键的处理是「保留最后一个」，且完全不报错**：
先写的那份仍在文件里、仍读起来像生效中、却什么也不决定。

这是**一类缺陷不是一次事故**，所以现在**有闸口**了——而闸口又找出**第二处、且早于本次工作**：
`det` 在同一个对象里声明了两次，**带描述的那份输给了长长的属性列表末尾一个裸的重复声明**。
两处都并回一份，并**按「它是什么」重写描述**。在一个 `additionalProperties: false`
的 schema 里这是这个问题最坏的版本：**活下来的那份决定信封能不能携带这个键**。

工具变量现在有**两个写者**，这件事本身也被检查：数值端会覆写该字段，
而一个解出了不同工具变量的数值端会留下**表达式指一个变量、字段指另一个变量**的一行——
正被上面那条渲染义务拒掉。

**基线**：5573 → **5611**。mypy 131 Success。

---

### 一条 gap 同时装着「这是谁的发现」和「这要谁付代价」（2026-08-21，#377）

把变量声明的测量类型与供给的列核对，产出的是一条关于**程序**的发现——这一列与它的声明不符。
**这条发现对该程序产出的每一份结果都为真**。而它的**代价**属于手上的这一份答案：
**没有任何查询估计过的列，改变不了这份答案里的任何一个数**。

写成一条 gap，两者就只能按**更强的那个**来报，而更强的那个是 `domain_violated` 阻断
`point_estimate`。于是——**一个在程序里被声明、供给值超出声明范围、且没有任何查询用到的变量，
阻断了程序里每一个查询的点估计**。

**修法不丢任何东西，而且这不是风格选择**：`extensions.type_reconciliation`
**到不了任何读者面**（全仓只有 envelope glossary 的一句注释提到它），所以 gap 是这条发现
唯一的到达方式。「只在该列被估计时才升起 gap」会**恰好在没有查询触及该列时把它消音**——
而那正是这条诊断存在的理由。现在：发现仍到达每一份结果；**在估计量之外**它是
informational、只触及 interpretation，并且**在自己的句子里说清它是两个断言里的哪一个**，
而不是留给读者去推。

**「这份答案立在哪些列上」是从结果里读出来的**，而「为什么是读不是查表」值得写下来：
信封在**约十处**说这件事、且没有一处把它作为一个事实说出来——四个不同块里都叫
`adjustment_set`，外加 `instrument`、`conditioning`、`mediator`、`s_nodes`、
`selection_nodes`、`design_vars`。在这里按块建表＝把那份散落抄一遍，且会随下一条路线过期。
这个读法**保守**，所以它可能出错的方向是「block 得比必要更多」，不是更少。
两个容器必须排除：核对块**按构造**列出了每一个被声明的谓词，而 gap report 正是要写入的那个答案；
数进任何一个，这个问题就对所有东西答「是」。

**验证器自己走一遍得出这个作用域**，理由和它自己重导判定一样：作用域搞错的生产者，
否则就会被拿它自己的错误去评分。它**两个方向都拒**——把程序级发现装扮成这份答案的代价，
以及把这份答案的代价降格成程序备注。

**那份散落已单独登记为一条待办**（此处不写它的编号：CORE_STATUS 是已完成条目的登记册，
在这里写一个还没有条目的编号，会让「引用的编号必须有条目」那道闸口把它当成已有条目）：
信封携带的 data_hash 文档写明「只覆盖模型列」，而**列集本身从不随行**
——**验证器要独立重算这个哈希只能猜列集**。等列集有了自己的槽位，这里的读取就变成一次字段读。

**基线**：5562 → **5573**。mypy 131 Success。

---

### 拓宽销毁掉的那个事实，答在拓宽的旁边（2026-08-21，#376）

`validate_data` 把每个数值型模型列 `astype("float64")`。此后 dtype 不再区分
「整数编码的类别」与「测量值」，而下游要的正是**被这次拓宽销毁掉的那个事实**。
**三个**估计器各自把它推了一遍，各自写了一段解释同一次拓宽的话，
并且**恰好在没人比较它们的地方互相不一致**。

**登记条目说是两个模块，实测是三个**：`discovery._classify_column`、
`frontdoor._discrete_levels`、`missing_recovery._check_discrete`。
`discovery._level_label` 是第四处出现但**不并入**——把整数值 float 收成 int 是
「离散列上一个 level **是什么**」的建模决定，已被钉为刻意不合并。

**它们分歧在哪**：

```
无穷        np.round(inf) 就是 inf，所以单靠「与四舍五入结果比较」会把它当成整数。
            两处带 isfinite 守卫，_check_discrete 没有，于是它**收下了一个无穷的分层
            level**。可达，且已演示：对 [1.0, 2.0, inf]，它原本携带的推导答「都是整数」，
            合并后的读法拒绝该列。
空列        _classify_column 说「是整数值」——里面没有任何一个值不是；
            _discrete_levels 说「不是」，并把它当连续中介拒掉——那是一句关于
            「一个什么都没有的列」的话。**不可达**（契约要 ≥10 行且拒模型列里的 NaN），
            **不可达正是它活下来的原因**。
```

**结构性修改**：`contract.integer_valued` 是唯一的那次读取，**放在使它成为必要的那次 cast 旁边**。
有限性是**答案的一部分**而不是旁边的守卫——在任何调用方的意义下，无穷都不是整数。
空集**空真**地全是整数；连一个值都没有就没法工作的调用方，自己去问那个问题。

**闸口的分母是源码里所有「与四舍五入结果比较」的地方**，所以明年新写的第四次推导
和现存这三处受同样检查。它找的是「一个被四舍五入的值**与它自己**比较」——任一侧、
`==` 或 `!=`（两种写法都出现过）——而**不是**「四舍五入」本身，那是别人可以正当去做的另一件事。

**基线**：5550 → **5562**。mypy 131 Success。

---

### 「它序列化得了」不是那条承诺问的问题（2026-08-21，#375）

`envelope_scalar` 的承诺是「JSON 写得下的那五样」。**float 是五样之一，却仍然可以一样都不是**：
JSON 里**没有** NaN，也没有任何一种无穷。`json.dumps` **自己发明了三个 token**，
在 `allow_nan=False` 下**自己又全部拒掉**，而任何解析器都**不必**接受它们。

**根因**：为这条承诺兜底的后置条件是 `json.dumps(...)`——**默认模式**，也就是**会写出那三个**的模式。
于是这条检查**恰好对承诺所排除的那些值为真**。这不是「少了一条 NaN 分支」：
**它是一条比它所验的承诺更宽松的检查，问的是一个更容易的问题**；只补一个 NaN 用例，
洞会原样留下、只是宽了一个类型。

**结构性修改**：后置条件改 `allow_nan=False`；转换函数按**读者那侧真正会拿到的 token** 拒绝非有限 float
——token 取自 `json.dumps(plain)`（**来自写方**，不是这里手抄一张表），所以消息不可能与真正会被写出的东西漂开。
两条测试把两半钉在一起：宽松的写方产生这个 token，严格的写方拒绝它。判据是**有限性而非量级**，
所以最大的可表示 float 仍然是一个数。

**先量再拒**，因为一条会打断活路径的拒绝是另一种改动：在函数上、以及在
`from ..types import envelope_scalar` 绑定过它的**七个模块**上同时插桩，并遍历 `run`/`estimate`
返回的每一份信封，跑完全套——**19,930,596 次转换、1,768 份信封，两条路线上非有限值均为 0**。
所以这拒的是**可能到来的**，不是**正在到来的**。

**另一条路线更弱，现在它自己说了**：`envelope_scalar` 是「**从数据读出来的值**」的唯一出口；
而**算出来的** float——点估计、区间端点、p 值——不经过它就进了信封。**源码侧无法为它们判定有限性**，
因为那是**算术的性质、不是代码的性质**；所以那一臂是语料臂，其 docstring 直接写明这条边界，而不是留给人猜。

**顺手**：「七个生产者必须指向同一个函数」这条规则，分母原本是**写在测试里的一张清单**。
而它存在的意义正是抓住**没人记得的那个模块**——明年新写的第八个生产者——那恰恰是一张靠记性的清单
装不下的东西。分母改为源码：`themis/` 下所有 import 了这个名字的模块，走 import 语句扫出来，
并加一条测试断言这次扫描**既不是空的也不是全部**。

**基线**：5530 → **5550**。mypy 131 Success。

---

### Σ 绑住它接管的原子——而这件事被写成了两次调用（2026-08-21，#374）

`_bind_none_to_varref`（`c_factor.py`）自陈是事后补丁：Line 4 包完外层 Σ 之后，
把子递归留下的 `value=None` 改写掉，否则求值器在 `P(m|x=True)` 撞上那个洞、
抛 `InsufficientTheta`——**而绑住它的 Σ 就在树的正上方**。三个调用点，每处都紧贴一次包裹。

**根因**：这两件事是**一个**操作。`value=None` 的含义是「由**持有这份公式的人**来绑」
——查询，或者一个还没被套上去的外层构造。一个 Σ 接管了这个原子，它就**成了**那个持有者，
所以把该 occurrence 指向这个 Σ 自己的名字，不是包裹**之后**的一步，**那就是包裹的全部内容**。
写成两次调用就制造出「只做了其中一件」这个状态，而那正是旧注释描述的那个 bug。

**结构性修改**：`_bind_and_sum` 是整个操作，`_bind_occurrences` 降为它的私有一半；
三处（Line 4、符号分布的边缘化、自由参数的包裹）全部走它。

**两个更早的解释都被度量否掉了，第二个是我自己写的，一并记下**：

1. **登记条目说「递归需要第四种值状态」**。在公共入口上插桩、跑 ID 语料——
   **3841 份出货的可识别公式**——`value=None` 只落在两个地方，没有第三个：
   查询自己的目标，以及 IDC 的条件 Z。没有第三种含义在等一个名字。
2. **读完 `_IdState` 之后我写的后续假设是「Y 侧缺 X 侧已有的那个拆分」**——加一个全程固定的
   `query_y`，让 `_atom_to_target_va` 回答「这是不是**查询**的目标」而不是「是不是**本级**的」。
   同一份插桩把它否掉了：**21 份公式里，查询自己的目标在同一个估计量里同时以两种身份出现**
   ——分子里是 `value=None` 的洞，分母里在自己的 `Σ_y` 底下。那是 **Tian 条件化的比值**，
   分母就是归一化常数，**它本来就要把被问的那个量边缘化掉**。按原子设的规则会把那个分母
   变成分子。`state.y`（本级目标）才是对的判据，它从来不是缺陷；**权威是调用方给的 `over` 集合**，
   所以原语把它当参数收下，对「这是哪个原子」一个字都不问。

**闸口读的是递归的源码，不是某次运行**，并区分 `SumExpr(...)` 在那里的两种形状：
传 `bind=formula.bind` 的是保结构重建，传 `bind=BindDecl(...)` 的才是**命名了一个新变量**。
只有后者是 binder，且只有 `_bind_and_sum` 可以造。闸口会拒绝写在别处的 binder，放行重建。

**行为不变是量出来的、不是假设的**：合并后用同一份插桩跑同一份语料，
**普查结果逐字节相同**——同样 3841 份公式、同样的 `None` 落点、同样那 21 份。

**基线**：5523 → **5530**。mypy 131 Success。

---

### 头部日期原本是「必须存在的字段」，现在是「必须成立的断言」（2026-08-21，#378）

`test_status_docs_have_update_timestamp` 只查 `CORE_STATUS.md` 与 `COVERAGE_MAP.md`
各自声明了 `> 更新时间：YYYY-MM-DD`，并且写明了为什么不再往前走一步：陈旧与否
「取决于文件内容的历史，正则可靠不了」。

**它不取决于历史。**一份写有日期工作的文档，日期就写在它自己正文里。动手前先量：

```
CORE_STATUS.md   头部 2026-08-21，106 个标题里 72 个带日期，最新标题 2026-08-21，
                 全文最新日期 2026-08-21                      -> 相符
COVERAGE_MAP.md  头部 2026-07-11，0 个标题带日期，全文最新日期 2026-07-13
                 （在选择偏倚那一行的表格单元里）             -> 已陈旧
```

**旧理由为真的那个文件，恰好就是陈旧的那个**——COVERAGE_MAP 把日期放在表格单元
而不是标题里。所以那句理由不只是保守，它指的方向偏离了问题本身。

**结构性修改**：两种文件形状毫无共同点，但**两个头部所作的断言有**——正文里出现
比声明日期更晚的日期，就与那个断言矛盾，与正文是什么形状无关。于是规则不需要
逐文件结构、也不需要例外表，而这正是旧理由断定做不到的那件事。ISO 序意味着字符串
比较就是日期比较，整条检查就是「这份文件里有没有哪个日期晚于头部声明的那个」。

COVERAGE_MAP 的头部改为 **2026-07-13**——文件自己带的最新日期，**不是今天**。
今天是这道闸口写成的日子，而头部是关于这张地图的断言。

**本条不修、也不假装修了的一件事**：这张地图的**内容**落后约一个月，
2026-07-13 之后的东西一件都没反映进去。**这道闸口看不见它**——一份停止更新的文档
也就停止获得新日期。重写它是另一件活。

**基线**：5520 → **5523**。

---

### 闸口数的是「这次跑出来的串」，于是它报的是自己看过的那部分的完备（2026-08-21，#373）

`themis/` 里有 **823 条**英文从句写在文档之外，而「没有句子以错误语言到达读者」
那道闸口对它们**全绿**——其中一条就落在
`extensions.mediation_decomposition.numeric.cde_status.reason` 上，
**那条路径闸口自己的表里已经写着「散文」**，它被 `analysis_report` 嵌进中文报告、
被 `verdict.ts` 印进浏览器。

**根因**：闸口的两条臂都以「跑一次内核、语料产出了哪些串」为分母。语言臂看产出的串；
而**完备性臂——那条专门回答「有没有我没分类的路径」的臂——数的是同一批运行产出的
路径**。于是一条没有语料到达的分支，既不被检查，**也不被报成未检查**。
这个模块此前已经被同一件事咬过一次，当时的修法是**再手写一个程序**——那不是修法：
没人写得出一份能到达每条分支的语料，而要求它等于把 100% 分支覆盖率
变成一条文风规则的前置条件。

比「少一条臂」更糟：有一个测试断言**每条已分类路径都必须被语料产出**，所以读者面
那张表**结构上就装不下**语料到不了的路径。完备性不可能住在那里。

**结构性修改**：第二条臂改从**源码**出发。分母是 `themis/` 里的每一条字符串字面量
——没有哪次运行能把它变窄——并且**分类反转**：内核写读者的语言，**英文才需要理由**。
这才是表小得下来的原因：按产生点建表要一行一个构造点、还会随新构造点增长；
按理由建表只有四条结构性条目，全部由 AST 自己判定：

```
文档串           1606   裸字符串语句——模块 / 类 / 函数 docstring 与 PEP 258 属性文档同类
raise / super()  1590   异常消息；每一条要么是开发者读的不变量，要么是正在走向 #327 那条通道的拒答
verifier/、oracle/ 396   审计 trail。人拿到的是判定的渲染，从来不是这条串
具名槽位          201   held 115、unread 81、quoted 5
```

余下 **222 条、42 个槽位**四条都不沾，已逐条译出。

**设计自身的两个缺陷，恰好都是本条要修的那个病，且都是量出来而不是读出来的**：

1. 初稿用**手写的关键字表**来判断「哪些字段能承载句子」。那就是一个由「写清单的人
   看到了什么」决定的分母，实测漏掉 15 条（`four_way_unavailable_reason`、
   `formula_repr`、`reference`）。分母改为从**信封已声明的形状**——schema 的字符串
   叶名——推导，既不被某次运行变窄，也不被作者的记性变窄。
2. 匿名 dict 没有名字，只按键名索引会把 `estimator_failure.reason` 与
   `cde_status.reason` 压进同一行。一个是拒答通道，一个是读者读到的散文，
   用一份分类盖住两者，正是本仓反复抓到的「一个值站两个断言」。现在 dict **按键签名
   识别**，判据用子集而非相等（同一容器带不带可选键都出现过），而**同时匹配两个签名
   的字面量会拿到一个没有任何豁免能接住的标签**——它会失败，而不是被归进先写的那个。

3. 第三个是我在修本条时自己犯的：翻译四个 helper，把中文从句塞进了英文拒答的中间。
   结构规则（`raise`）与槽名**都读「字面量坐在哪」，都不跟着调用走**，所以一个把从句
   交给调用方拼进 `raise` 的 helper，落在它其实身处的通道之外。已回滚、每个一行说明
   它落在哪、并把这条限制写进模块 docstring。同一次阅读还抓到 `scheduler` 的一致性
   细节只翻了一半——从句判据要两个小写虚词，而 `must lie in` 只有一个。

槽名规则本身也补了一处：**模块体顶层的 `Name = 字面量`** 此前落进占位槽 `<module>`，
于是（a）只能整模块免检——那不叫豁免叫免检，（b）按名字写的豁免行必然是死行。
类体里的 `MEMBER = "..."` 归到类名是对的——**类就是那张表**；模块体不是表，
所以绑定它的那个名字就是槽位。

**三条豁免本身就说明了东西，不是「这样没问题」**：

- `unread` 不是 `off_envelope`。`Question.asks`、`Block.holds`、`Layer.breaks`、
  `Provenance.answerable`、`RiskProvenance.asserts`——**每一个的消费者都只有一个
  断言它非空的测试**。它们是**穿着值外衣的文档**，和 #338 在 `estimated_from_data`
  上抓到的是同一形状。记录而不翻译，这样「哪天有人把它接上」才是改变答案的那件事。
  其中三个旁边就有 `zh` 兄弟字段——那才是读者拿到的，也正是本仓对词表已有的分层。
- `held` 不是 `audit`。拒答通道**确实**到达读者；该用哪种语言是 **#327**，那是用户
  保留的决定。把它叫成 audit 会很方便，而且是假话。
- `attempt_balke_pearl_iv` 上的 `quoted` **记录了一个缺陷而不是豁免掉它**：
  `bounds_results[].{lower,upper}_expression` 是符号界，而那条分支之所以用文字写出
  这个线性规划，是因为 Balke-Pearl 界没有闭式可写。**把说明写进表达式槽位，
  是关于槽位的缺陷。**

**两条臂的盲点都写在各自身边**，因为这正是本条的教训：源码臂看不见由「没有任何单条
字面量含有的部件」拼出来的句子；语料臂看得见——前提是有语料到得了。
两条都不假装自己查的是全部，而它们查的是**不同的一半**。

**基线**：5492 → **5520**。mypy 131 Success。

---

### 闸口问错了问题：它问谁在读，该问的是潜在共因动不动得了答案（2026-08-21，#353）

ADMG（带 `bidirected` 边）上的 `cause` / `probability` 查询被 `SemanticError`
挡死。解门之后逐个量，答案**本来就是对的**：

```
x<->y 单独          cause(x,y) → False          （潜在共因不是因果）
x->m->y 且 x<->y    cause(x,y) → True，路径 x,m,y（双向边不进路径）
θ 里有 P(y|x)=0.7   probability → 0.7 逐字节
θ 里只有 P(y)=0.18  probability → 拒答，点名缺 P(y=True|x=True)
```

最后一格是**唯一**一处潜在共因真能动答案的地方：θ 缺精确条件时，求值器会考虑
拿一个更粗的条件顶上，而顶上去等于断言 y ⊥ x——`x<->y` 正是让这句断言变假的东西。
**把边集从守卫手里拿走，它就把 0.18 当成 P(y|x) 交出去；给它，它拒答。**
守卫早就是 m-分离而不是 d-分离的，所以这一格已经被守住了。

**根因**：闸口自己写下的解门条件——「只放行那些 dispatch 路径显式读取 bidirected
边集的 query kind」——是一个**代理**，替的是真正该问的那句：*潜在共因动得了这个
答案吗？* 而这个代理**两个方向都错**，并且在 HEAD 上都能证：

- `cause` **永远不会**读边集，因为潜在共因不是因果——按闸口自己写的条件，它会
  **永远**被拒，而它一直在给对的答案。
- `scm_counterfactual` **同样不读**边集，却从来没被拒过——因为闸口**根本没执行
  自己写的条件**，它执行的是一对手写 `isinstance`，写在十个 kind 里的五个还不
  存在的时候，而**未列名的 kind 默认放行**。

**为什么是根因不是表象**：如果只是清单过期，修法就是删两条——而下一个照着
docstring 办事的人会把它们加回去，因为那句条件对 `cause` 仍然是假的、而且永远
会是假的。放走 `scm_counterfactual` 的那份沉默，也正是会放走**下一个** kind 的
沉默：未分类者的默认值站在危险的那一侧。清单和它自称的条件对世界的说法不一致，
错的是条件。

**结构性修改**：把真正的判据按 query kind 声明一次——*潜在共因动得了这个答案吗？
动不了的话为什么动不了*——闸口读这张表而不是读 `isinstance` 元组，**没被分类的
kind 连模块都导不进来**。于是「这五个 kind 从来没人问过这个问题」不可能再发生。

三种取值，而放行的那两种**不是同一种放行**：`ABSORBED`（动不了）无论边集怎么
穿都还是对的；`CONSULTED`（动得了，路径拿到了边集）在它哪天不再拿到的那一刻就
错了，而且**不出声**。把两者压成「读不读边集」正是本条的病根，所以枚举里它们分开。

`scm_counterfactual` 归 `ABSORBED`，理由是**量出来的**：abduction 是**单元级**的，
潜在共因对这个单元结局做过什么，已经在事实观测钉住的那个外生项里，而 `do()`
不碰那个项。40 个单元对闭式单元反事实，最大误差 2e-15，**声不声明那条边完全一样**。

`QUERY_KIND_OF`（class → kind）从 scheduler 挪进 `types.py`（它连接的两个封闭集合
都在那），**它在那边的那个 helper `_query_kind` 全仓零调用者——这张表原地就是死的**，
这也解释了为什么没人发现位置不对：真正需要它的是 input 层，而 input 层导不进 runtime。
表现在**双向钉**在 query union 与 kind enum 上：一个没有 kind 的 class 是**构建失败**，
而不是在用户面前抛 KeyError——和本条其余部分是同一个形状。

**词表到达闸口（#362）当场抓住了我**：新枚举必须说出谁读它才让过。答案是**没人读**——
被它拒的程序抛 `SemanticError`、根本没有信封；被它放行的程序，信封里装的是**答案**，
不是「凭什么允许算这个答案」。理由随拒答句子走；`absorbed` / `consulted` 是写给
**下一个加 query kind 的人**看的。这正是那道闸口存在的意义。

**登记条目这次是对的**（本会话第一条），但「低价值 polish」低估了：它写的是解门
+ 翻 5 个测试，实际暴露的是**闸口默认值站错边**，而那一半比解门重要。

**基线**：5474 → **5492**。mypy 131 Success。

---

### 一个布尔放在了兄弟函数收「轴」的位置上，于是披露说错了轴（2026-08-21，#352）

同一份数据、同一条通道（结局误分类），唯一差别是**混淆矩阵被声明为随哪个轴变化**：

```
differential_by="z"  →  点估计 0.448888
differential_by="x"  →  点估计 0.461347
```

两次是**不同的修正**，本该如此。可两次的台账都写着：

```
differential_misclassification_by_exposure_arm_M_depends_on_X
known_per_arm_confusion_matrices_from_validation_study
```

**第一次跑的是「逐协变量层求逆」，却告诉读者它跑的是「逐处理臂」。** 这不是措辞不够精确：
一份确立了「各中心检出率不同」的验证研究，**对「各处理臂检出率不同」什么都没说**——
于是想核实这条前提的人会去查错的那份研究，而想判断自己信不信的读者，
**是在对一条这次运行从未做出的断言下判断**。

**根因**：`_assumptions` 收的是 `differential: bool`。同一模块里它的兄弟——暴露通道的
`_exposure_assumptions`——收的是 `differential_axis` 并据此分支。**同一件事的两条通道，
一个说得出轴、一个说不出**。布尔没有地方放「轴」，所以修法是**改参数**而不是在它上面加一个
分支：加分支会让两个签名继续不一致，而下一个轴依然说不出来。

**没有镜像，所以它活了下来。** 验证器独立重算一条修正的**算术**，但不重算它台账上的**字符串**，
于是台账是「究竟在主张哪条前提」的唯一记录，没有第二份能与它不一致。因此闸口只能是**反例**
而不是交叉核对：协变量轴不许声称处理臂，处理臂轴也不许声称协变量——**因为把另一个串写死，
会是同一个缺陷换了个标签**。

词表不用改：`differential_misclassification_by_covariate_` 这条前缀条目**早就在**，
是暴露通道放进去的——那条通道从一开始就是对的。

**登记条目本身两条都写错了。** #352 原本记的是另外两件事，而**两件都已被正确处理**：
合并臂拒绝 differential 矩阵**不是缺失的功能**——选中一条通道矩阵的那个层级，
正是另一条通道所测错的量，于是观测表不再是两侧乘积；它有具名拒答、有理由、有测试钉住。
而「同时按臂和协变量变化」是**已声明的延后**，且 `differential_by` 是单个名字，
**在接口层就不可表达**——那正是本项目偏好的形状（不可表达 > 检测并报告）。
原条目**没有命中任何一件真出错的事**。

**基线**：5473 → **5474**。mypy 131 Success。

---

### 两个问题被焊在一起，而它们在答案的两侧（2026-08-21，#323 完成）

结局有经典测量误差，不带偏、只花精度，而花多少**取决于设计**。此前只有后门设计被定价。
把这个分解推广到前门与工具变量设计就是这一条，而 **IV 那条臂正是逼得这一行必须拆开的原因**。

它的残差是**结构残差** Var(Y − βX − γ'W)，绕着 β̂ 取——**而 β̂ 就是答案**。这一行跑在
precedence 100，在所有估计量之前，所以根本没有 β̂ 可绕。这看起来像个顺序问题，**但不是**：
这一行在做**两件对时机要求相反的事**。

| | 必须在哪一侧 | 为什么 |
|---|---|---|
| 这个**声明**在这份数据下可能为真吗？ | 估计量**之前** | 它的答案能**停掉查询**——离散结局是误分类（**会**衰减）；σ²_v 塞不进未解释变异，则**点估计当初赖以成立的独立性前提本身存疑** |
| 这台噪声让**这个答案**损失多少？ | 估计量**之后** | 没有答案就无从谈损失 |

焊在一起，这一对就只能待在一侧，而它待在了早的那侧。于是**价格需要答案的那种设计永远定不了价**，
而另外两种「碰巧不需要」的设计**是偶然能工作的**——没有任何东西标出这一行站错了侧，因为
后门与前门的残差都是 OLS 投影，在任何估计量跑之前就存在。

拆成 `outcome_error_declaration`（100）与 `outcome_error_precision_cost`（200）。后者声明为
`after_the_answer`，而这是**优先级轴的新的一半**，不是行上的一个标志位：**precedence 排的是
竞争者**，而只做注解的行**不是竞争者**——它是关于「谁赢了」的一句披露。两道闸口守住这条界线，
**每道都构造了它该拒绝的输入**：`check_table` 拒绝一个「答案之后」却产出估计量的行；级联拒绝
一个在那里回答或停止查询的行——**事后的否决等于撤回一个已经写下的答案**。这样一行学得太晚的
东西，是数值旁边的一条注记，而那正是上一次提交建好的那个面。

**拒答仍然一律落在 OLS 残差上，而这不是用近似顶替结构残差。** Var(Y|D) = Var(Y*|D) + σ²_v
说的是**条件方差**，线性下它**就是**最小二乘残差，而最小二乘**最小化**它——所以
σ²_v ≤ Var(Y|D) **无论谁来回答都是必要条件**，更紧的那个检查才是对的那个。实测（恰好识别的
IV 构造）：结构残差 4.99 对最小二乘 2.52、5.99 对 3.53、7.96 对 5.52。正因为最小二乘那个更小，
**早检查放行的 σ²_v 不可能被晚检查拒掉**，于是晚的那条拒答只可能经由「作答行命名了、而早检查
没看见」的设计到达。

β̂ 是从 `numeric_estimate` **读回来**的，不是重算的。能回答这个查询的 IV 行有两条，未必选同一个
候选，所以在这里算出来的系数会是**出厂那个数的第二份记录**，随时可以与它不一致。已钉住：
被定价的那个系数**就是**出厂的那个浮点数。

`instruments` 是**复数**。过度识别的系统对每个工具各有一条 E[Z_j V] = 0，**各自可以为假**，
所以台账每个工具一条——在若干个里只报一个，等于**少报了实际假设的东西**。

**前门有两件事是说出来的，不是抹平的。** 其一，那个因子在前门是**高估**：有效影响函数
（Guo, Benkeser & Nabi, arXiv:2312.10234 式 4）把方差拆到多项，**只有一项带结局残差**，
所以它作为**上界**披露。**高出多少随设计而变、不是一个常数**——侦察那个构造上是
报 1.25 对真值 1.09，oracle 那个构造上是 8.3%，而在影响函数拆得最不均的设计上高出约 80%。
正因为如此，测试断言的是**方向**并给出**两头的夹逼**，而不是钉一个只对某一个数据生成过程
成立的「修正系数」。其二，前门图**假设了一个未观测的 X–Y
混杂**；**若测量误差与它相关，点估计本身会动**，而 IV 没有这个暴露面。那条前提是关于一个
**没人测过的变量**的，**任何数据都证伪不了**，所以它是台账上的第三条假设，不是一个脚注。

**那条「什么都不记」的出口现在有了反例。** 够到前门设计意味着借用那个估计量对中介的张成，
于是它的张成检查可能**先在这里**触发——那是关于**一个列**的事实，不是关于所声明方差的——
而保持沉默所依赖的，是「它所属的那个估计量会用自己的名义说同样的话」这句**关于别人的断言**。
构造出来了：中介连续时，**声明与不声明，查询死得一模一样**，同一个估计量、同一个种类。

**基线**：5367 → **5473**。mypy 131 Success。pnpm build 196 modules。

---

### 一条「注解」行占有了查询，而它占有的那个条件正好定义了两条路线（2026-08-21，#323 侦察发现）

同一个程序、同一份数据，唯一的差别是调用方**说不说自己知道结局有测量误差**：

```
themis.estimate(前门程序, df)                                   → numerically_solved, frontdoor_linear, 0.4416
themis.estimate(前门程序, df,
                measurement_error={"y": {"error_variance": 0.5}}) → needs_investigation, numeric_estimate=None
```

**声明结局有经典测量误差，代价不是少一块评估，是整个答案没了。**

**占有是行的属性，不是结果的属性。** 结局误差这一行成功时走 `annotated()`——经典可加误差不动
任何条件均值，所以它没有自己的估计量，谁回答这个查询谁回答。可它「没有设计」那条出口走的是
`blocked()`，而 `blocked` 是占有，级联在占有者处停止，于是 precedence 180/190 的 IV 与 front-door
处理器**从来没跑过**。而它停下所依据的条件——调整集为空——**正是这两条路线的定义**：
这一行恰好挡在了它服务不了的那些查询前面。

**判据不是「注解行永不停查询」。** 它另外两条出口仍然停，而且停得对：离散结局是误分类，
那**是**会衰减的；声明的方差塞不进数据显示的残差变异，则**使点估计当初赖以成立的独立性前提本身
存疑**。这两条都是**关于答案的事实**。而「这个包还没给这种设计写分解」是**关于这一行自己的事实**。
于是规则是：**它可以因为「学到了什么」停下查询，绝不因为「够不着」停下**。
拒答理由也随之改成 `numeric_end_not_built`——它在词表里的原话就是
「估计量已被识别，而这个包还没为它建数值端——是包的缺口，不是用户输入的缺口」。

这条线不是句法可判的，所以闸口做成**普查而不是禁令**：26 个返回 `Claim` 的处理器里，
**恰好一个**同时 annotate 和 block，测试点名它并把规则写在失败消息里。**出现第二个名字**，
意味着有人又画了一次这条线，失败消息请他来把规则读一遍。

**不再阻断查询只是一半。** `_render_answer` 只在上面每一条数值分支都没 return 时才够得到
`estimator_failure`——这是设计如此，因为**数在与「关于附带项的拒答」之间，数是答案**——
于是放行数值之后，那条拒答变得**完全不可见**：调用方声明了自己知道的事，拿到正确的数，
**关于他所要的那项评估一个字也没听到**。沉默是这里另一种错法。现在，
**与答案共存的拒答是答案底下的一条注记**（「另有一项没能给出（上面这个数不受影响）」），
判据挂在**已渲染的答案文本**上而不是第二个字段上——决定这件事的是「这条拒答有没有已经被说过」，
而只有文本知道；一个标志位会是它的第二份记录，随时可以与它不一致。

**浏览器那半正好相反**：它两样都渲染，但 kind 表里**每一条 lead 都以「没有给出数值」开头**——
那是一句关于信封的断言，而只有信封能裁定它，却被印在一个正显示着数值的图块正上方。

**基线**：5358 → **5367**。mypy 131 Success。

这条是 #323（把结局测量误差评估推广到 IV 与 front-door 设计）**侦察阶段**发现的缺陷，
能力扩张本身随后进行。先修它的理由：不修的话，能力扩张会把它盖住——**第四种设计**
（纵向 g-formula、transport……）再撞上同一条 `not adjustment_sets`，还会以同样的方式丢掉答案。

---

### 六份「numpy→JSON」降级辅助并成一份，而它们不一样恰恰说明这不是去重（2026-08-21，#318 完成）

登记说「5 份，散在 7 个文件」。实测是 **6 份、6 个文件**——登记点名的三个（`contract` /
`orientation_session` / `websearch_proxy`）**一份都没有**，漏掉的两个（`response_polytope` /
`general_id`）各有一份，另有 `bounds_numeric` 跨模块 `from ..response_polytope import _py`
借用私名。登记的注记「五份全服务『值进信封』，『值进句子』那条路一份都没有」也不成立：
`measurement` 有三处、`dispatch` 有两处把同一个转换的结果插进中文句子（拒答消息、gap 描述）。
一个 JSON 标量同时也是一个可打印标量，所以这个分工从来不存在，也不需要存在。

**六份长得不一样，而这件事本身就是判据。** 逐字相同的多份是复制粘贴，合并就是去重；
**长得不一样的多份是各自重写**，那么合并不是去重，是**第一次把这个谓词写下来**。三种行为：
①`.item()` 后原样透传（polytope / general_id / dispatch）；②按 numpy kind 分派再用 `str()`
兜底（measurement / selection）；③`.item()` 后把整数值 float 收成 int（discovery）。

**根因是谓词写错了：这个函数一直被当作「去掉 numpy」写，而调用点要的是「能进信封」。**
`.item()` 的值域是 Python **内置**类型，而信封要的是 `json.dumps` **写得下**的类型，
前者不含后者——时刻、时长、复数都是内置的，一个都写不下。所以一个值可以满足代码做的事、
同时违反 docstring 承诺的事，而破绽只在**别人的栈帧里**第一次 `json.dumps` 时才炸。
构造出的反例：一个 `datetime.date` 列走完 `_json_safe_value` 进 `extensions.type_reconciliation`，
`json.dumps(envelope)` → `TypeError: Object of type date is not JSON serializable`。
第二个：`np.timedelta64` 是 `np.signedinteger` 的子类，于是按 kind 分派的那两份把它送进
`int()` 分支抛裸 TypeError——**它自称的 `str()` 全兜底，恰好漏掉了自己写来兜的那一支**。

**家在 `themis/types.py`，紧挨 `EnvelopeName`。** 那个类的 docstring 最后一段已经把理由写完了
（「每个注册表各写一份基类，是一条到有人忘掉三分之一为止的规则」）——同一个问题不该有第二个家。
numpy 本来就是 `import themis` 的硬依赖（实测 `import themis.types` 就已把 numpy 装进
`sys.modules`），所以没有新增依赖。判据写成两半，**只有第二半是承诺**：numpy 自己说得出自己的
等价内置值，这半委托给它；然后结果**必须是** JSON 写得下的五种之一，不是就在**产出这个值的调用方
还在栈上时**具名报错，而不是把问题转交给一个说不出它来历的地方去抛。

**「打印出来」是必须被拒绝、而不只是没被选中的那个选项。** 验证器只从信封反推结论，
所以一个被打印成字符串的层级，在到达时和一个本来就是字符串的层级**分不出来**——
那是一句没有任何产出者做出、也没有任何读者能核查的、关于数据的断言。

**discovery 那份不并进来。** 它多做的「整数值 float 收成 int」不是 JSON 降级，是
「在离散列上一个**层级**是什么」的建模决定（契约把每个数值列无条件 `astype(float64)`，
整数编码列因此变成 0.0/1.0/2.0）。并进来会把每一个估计量信封里的 `2.0` 变成 `2`，
而对估计量来说 2.0 是一次**测量**不是一个编码。`_to_py_scalar` 改名 `_level_label`
（更早那条时间线记录里点的就是这个名字），并且**建在共用转换之上**而不是并排——
于是那条拒答不必被第二份代码再记一遍。

**一处顺带的位置修正**：`selection` 的 `selected_values` 是**调用方说的「被选中」是什么意思**，
而这个转换原本写在 return 语句上——于是一个信封记不下的值，要等每一层都标准化完才被拒；
而一个既记不下、又匹配不到任何行的值，会先被**契约**以「样本量为 0，低于下限」拒掉：
**症状顶着病因的名字说话**。现在默认值、转换、以及「只保留 selection 节点」写成一句
（schema 本来就写着这个字段是「每个选择节点 S 的值」，代码现在按构造让这句话为真）。

**度量与等价证明**：插桩跑全套 5317 条测试，记录六个函数**真实收到**的类型——只有六种
（`bool`/`int`/`float`/`np.bool_`/`np.int64`/`np.float64`），其余分支一条都到不了；
`measurement` 那份被调用 **19,778,749** 次，其中 99.98% 是 `bool` 透传。
再把六个 HEAD 版函数体用 `git show` 取出 exec 进来，与合并版在 24 个值上对跑：**0 处差异**。
所以三种行为在**真实可达域上完全一致**，分歧只在没人到得了、也没人测过的类型上。

**明确排除并登记，而不是顺手做掉**：`float('nan')`/`inf` 是货真价实的 Python float，会过闸，
而严格 JSON 里没有这两个词（#375）——但那是信封上**每一个 float** 的问题，不是这 52 个调用点的
问题，只在这里关掉就会造出「同一个约定的两半互相矛盾」，正是 #331 复核抓到的那个形状。
契约丢掉整数编码、discovery 与 dispatch 各自绕了一遍且互不知情，登记为 #376。

**基线**：5317 → **5358**（+41 条反例，含闸口该说「不」的七种输入、六个产出者指向同一个函数对象
的防再分裂普查、discovery 那份「是重编码不是降级」的两半，以及「入口点先决定」那条的反例）。
mypy 131 Success。

**方法论沉淀（第一八七至一八九条）**：
(187)**重复的形状会说出它是怎么来的**——逐字相同是复制粘贴，合并即去重；**长得不一样是各自重写**，
合并就不是去重而是第一次写规格。所以决定「该不该合、合成什么」之前，先看它们**哪里不一样**。
(188)**名字和 docstring 可能在承诺两件事，而代码只做了较弱的那件**——这六份做的是「去掉 numpy」，
承诺的是「JSON-safe」，两者的差集全是**内置**类型，所以光读代码看不出破绽。
凡是 docstring 里出现「-safe」「保证」「总是」，那句话就该被当作**后置条件真跑一遍**。
(189)**登记里待验证的不只是解法，现象本身也是**——这一条登记点名的三个文件一份都没有，
漏掉的两个各有一份，附带的分工判断也不成立。先量，再动。

---

### 抑制名单 32 → 1，而复核抓到的两条回归是清理自己造的（2026-08-20，#331 完成）

第一批清掉 26 个模块之后，剩下的 32 个用**多 agent 编排**并行清：一组修，一组**对抗性复核**逐个读 diff
判断「这是把真相说出来了，还是把问题藏起来了」，再一组按复核结论收口，最后一组独立确认「测试有没有牙」。
findings 从 586 降到 **1**。

**复核的价值不在它说了什么，在它怎么说。** 本轮 0 条 must_fix、19 条 should_fix，
而其中**两条是清理自己引入的真回归**——都不是靠读 diff 觉得可疑发现的，是靠
**把 HEAD 版本的函数体 exec 进活模块、用同一个输入对跑两版**抓到的：

- **`dispatch.py`**：`(spec or {}).get("error_variance")` 被改成 `spec.get(..., math.nan)`，
  `or {}` 那半截兜底没了。于是 `measurement_error={"y": 0}` 从**一条被记录的拒答**
  （`non_positive_error_variance`，信封上有）变成一个**逃出 `themis.estimate` 的 AttributeError**。
  路由守卫只证明「非 None」，从不证明「是 dict」；而兄弟代码 `EffectFacts.measurement_error_map`
  **保留了**那个 `or {}`，所以同一个约定的两半开始自相矛盾。
  修法比原样恢复更好：`_guarded_spec` 把「presence 由路由守卫决定，**is-a-mapping 从来没人负责**」
  这句话写出来，非 mapping 变成一条具名拒答（`Refusal.INVALID_INPUT`），由 `_spec_row`
  记进信封而不是从异常口出去。`nan` 默认值也退回 `None`，理由写在旁边：
  **默认 nan 在调用方读来是一个他们声明过的数，而他们什么也没声明。**
- **`verifier/rules.py`**：`_envelope_number` 接受 `str` 却不守 `float()`。
  它自己的 docstring 说「非数字的条目是一条畸形声称，应当拒绝」，可 `'abc'` 通过了类型测试、
  在下一行炸成裸 `ValueError`——**而从规则到 `kernel.verify` 之间没有任何 try/except**，
  于是一个非 VerificationError 离开了验证器。同一次改动还让调用点丢了 `or` 短路，
  把这条从「够不着」变成「够得着」。修法是把 `str` 整个从接受类型里去掉，
  并**一并关掉相反方向的那条**：NaN 是货真价实的 float，`abs(claimed - expected) > tol`
  对它恒为 False，所以一个 NaN 边界不是被拒绝，是被**静默认证**。

**复核还找出一批「只说了一半真话」的地方**，共同点是：mypy 报的都是真错，而修法选择了 narrow 掉，
narrow 之后的落点却没人检查——
`explainer` 的三胞胎 narrow 完掉进一句**与 status 自相矛盾**的中文（status 写着已解出，
句子说「结果未分类」），旧行为会崩，**崩是难看但不撒谎**；
`markov_blanket` 的 `dict[Any, dict]` 压住的是一条指向真 TypeError 的错误
（异质键集合排序，而模块承诺任何结构不一致都给 VerificationError）；
`narrative_merge` 的 `isinstance(pattern, str)` 把畸形拒答**静默归成通用类**，
读者面上没有任何信号说「你的 pattern 被丢了」——校验该加在形状校验器里。

**一处「有更优结构改法」被复核建出来跑过再交回**：`_as_formula` 被逐字抄进两个文件，
而根因是生产者 `RiskRoute.formulas: dict[bool, object]` 把类型擦掉了；收窄成
`dict[bool, FormulaExpr]` 之后**两份副本都可以删**，且逐字节复现了原改动的每一个探针结果。

**owner 侧的三条跨文件项**（agent 按纪律只报告不动）：
- **`VerifiableQuery` 是 `Query` 的手抄副本**，漏了 `ProximalEffectQuery`——而 `kernel.verify`
  十种 query kind 全部分派、末尾还有 `else: raise`，所以「可验证的查询」**就是**查询词表本身。
  改成别名，副本消失，漂移不再可能。
- **两处 `_reject(...) -> None` 而函数体只有一条裸 `raise`。** 普查：全仓 23 个只含 raise 的函数里
  **21 个已经是 `NoReturn`**，只剩这两个。改过来之后**当场掀出一条被假注解压住的真 finding**——
  假注解是压制器，`-> None` 让每一个 `if not isinstance(x, T): _reject(...)` 之后的 narrowing 失效。
- **`assess_outcome_error(error_variance: float)` 与自己的函数体自相矛盾**：它第一件事就是校验这个参数
  并给出具名拒答，`Raises` 段还明写会收到非数字。改成 `object`——**不是不写注解**，
  不写等于 `Any`，会让函数体内部也不受检。

**名单剩一行，而它的含义变了**：`themis.runtime.c_factor` 不再是「还没读过」，是「读过了，代价在这里」——
`_IdState.x_value` 同时持有一个具体 do 字面量和一个不可伪造的哨兵，而公式 AST 只有三种值状态，
ID 递归需要第四种。三种模块内绕法都被实证否掉（做成 VarRef 会改 `formula_simplify` 的行为、
做成字面量会毁掉哨兵的不可伪造性、用 None 会和「query 绑定的洞」相撞）。这是一个架构决定，
不是一条注解，登记为独立前沿项，pyproject 里把理由写在那一行旁边。

**基线**：5177 → **5317**（+140 条，全部是这一轮钉住行为改变的反例测试）。
mypy 131 Success，抑制名单 **58 → 1**，findings **663 → 1**。

**方法论沉淀（第一八四至一八六条）**：
(184)**对抗性复核的牙在「给出那个具体输入」这条要求上**——本轮两条真回归都不是靠读 diff
觉得可疑发现的，是靠把旧版函数体 exec 进活模块、同一批输入对跑两版抓到的。
要求每条判断（**包括判「没差别」的**）都附一个可独立复现的输入，是复核有没有牙的分水岭。
(185)**假注解是压制器**——`-> None` 写在只会抛的函数上，会让它后面每一处守卫的 narrowing 失效；
改成 `NoReturn` 之后被它压住的真 finding 会当场冒出来。同族：一个过宽的类型不只压住它自己那几条。
(186)**入口点参数的诚实类型是 `object`**——不写注解等于 `Any`（函数体内部也不再受检），
写 `float` 是一句「调用方已保证」的假话，而这句假话会逼调用方把同一个检查用自己的措辞写第二遍。

---

### 累加器用它的第一个值声明自己——58 个被压住的模块清掉 26 个（2026-08-20，#331）

`pyproject` 的 mypy 抑制名单是一笔**只能变小的债**（#329 把它从白名单倒过来时就是这么定的）。
本轮开始逐个清。先做的是**普查**：把 `ignore_errors` 那一段临时摘掉跑一次 mypy，
拿到逐模块、逐 error code 的真实分布——**登记里写的 605 条，实测 663 条**。
一个写在注释里的数字会在没人碰它的时候停止成立，所以那一段的注释早就写明「计数问上工具，
不写进注释」；这次量出来的差额正是它防的那件事。**而且 `themis.runtime.structural_solver`
早就干净了**，名单上白挂了一行——债务清单本身也会漂。

**最大的一族是 63 条，而它们是同一句话说错了**：

    assumptions = ("consistency_of_potential_outcomes", "positivity")
    if cluster is not None:
        assumptions = assumptions + (f"ci_via_pairs_cluster_bootstrap_on_{cluster}",)

元组字面量的推断类型带**元数**——`tuple[str, str]`，不是 `tuple[str, ...]`。
对一条定长记录这是对的；对一个累加器这是错的。而源码里**没有任何东西区分这两者**：
两种写法一模一样。补上的就是这句区分，一处一个注解，29 处声明、17 个文件。
清掉这一族之后 **10 个模块直接归零**。

**剩下的按模块从小到大逐条读，而这一步不是加注解，是读代码。** 其中若干条是真问题：

- **`websearch_proxy`**：外部检索/LLM 返回的 `interval` 只被 `tuple(...)` 换了个容器，
  **没有校验元数，也没有 coerce 元素**——一个三端点的、或者带字符串的区间，就这样进了一个
  声明为「一对 float」的字段。同一个适配器里 `value` / `sample_size` / `citation`
  **全都**显式 coerce 了，只有它没有。现在它校验成两元 float，不合格就按「不可解析」
  降级成失败结果（与该适配器既有的降级风格一致）。
- **`ctf_identify`**：一个函数里 `a`、`b`、`pair` 三个名字各被用于两种不同的东西
  （`PWNode` 与 `Atom`）。**改掉其中一个之后，另外三条才露出来**——原来的
  `tuple[Any, Any]` 把它们一起盖住了。
- **`ctf_identify` 的另一处**：`_is_fixed`（在不在）和 `_world_value`（是多少）
  **各扫一遍同一个结构**，两者的一致性只存在于读者脑中——于是「已知它被固定」推不出
  「它有值」。改成 `_is_fixed` 由 `_world_value` 实现，两个问题一次查找；
  `_intervened` 随之无人调用，删掉。
- **`iv.py`**：`_NotStratifiable.__init__(failure_type: str)`，而父类要 `Refusal`，
  六个 raise 点传的全是 `Refusal`。注解是陈的。
- **`investigation_pusher`**：`max(priorities, key=_PRIORITY_ORDER.get)`——表里缺一个
  优先级时 `.get` 返回 `None`，`max` 拿 `None` 去和 int 比。改成 `__getitem__`：
  表里没有就是**表的洞**，应该当场喊。
- **`joint.py`**：`_joint_and_interaction` 服务两个调用者——**点样本**（进函数前已经查过角点）
  和 **bootstrap 重抽**（没查过）。返回类型只能取两者中弱的那个 `float | None`，
  于是点路径把一个可能为 `None` 的东西交给声明为 `float` 的字段，而那句保证写在
  三十行以上的一条注释里。改成**抛**而不是返回 `None`：抽样循环本来就在 catch
  `ValueError`，行为分毫不变，而点路径的保证进了签名。
- **`app.py`**：`kernel_ast` 与 `envelope` 是两个变量、在同一个 try 里一起赋值，
  而守卫只问了其中一个。改成一个二元组——**守卫替两者说话**。
- **`selection_recovery`**：`chosen = None` 哨兵，它非空这件事由三十行前的一个
  `continue` 保证。改成用 `admissible[0]` 起头，哨兵消失，取值次数不变。

**新增的守卫只有两处，其中一处不是收益**：区间校验是真的——三端点区间、一端区间、
带字符串的区间以前**静静通过**，现在返回 `interval_not_a_float_pair`；
**九条反例测试，撤掉守卫 6/6 变红**（另外三条「缺省区间不算失败」保持绿，
那是「它仍然对该说是的说是」那一臂）。而 `llm_bridge` 那处 `isinstance` 之后，
`p["value"]` 缺失走的还是同一个 `except`、报同一句话——**行为完全相同，只是类型能读了**，
这一条不是收益。

**名单 58 → 32，findings 663 → 586。**基线 5168 → **5177**（+9 条区间反例，
其余改动一条测试都没动——它们把已经成立的运行时保证搬进了类型）。mypy 131 Success。

**方法论沉淀（第一八三条）**：
(183)**一个过宽的类型不只压住它自己的那几条**——`tuple[Any, Any]` 一改成真类型，
下游三处类型冲突同时冒出来。所以抑制名单上的「N 条」是**下界**，不是总数；
清一个模块要按「清完再量」而不是「量完再清」。

---

### 类就是注册表——而登记里有一条早就成立了（2026-08-20，#330）

`blocks.py` 的块名是一串模块常量 + 一个从模块里收集的 `ALL`，正是拒答species 变成枚举**之前**
的形状。本条把这里的两张注册表也改成枚举：`Block`，以及它被读的那根轴 `Family`。

**收益是量出来的，不是假定的**：一条声称对应一条反例，每条都记录**在哪一层被拒**。
六条里四条是真收益，一条是**更正**。

**import 期被拒，且是新增的**：
- **两个名字一个块**。`@unique` 直接拒掉别名——枚举本来会**悄悄**把第二个名字变成第一个的别名。
  这件事以前由一条测试说；那条测试现在删掉了，因为它已经不是一句「可能为假」的话。
- **载体名指向不存在的东西**。以前由测试查，而且**只查了一半**：两个载体写成对另一个块的**引用**
  （拼错 = ImportError），另外两个是**裸字符串**（拼错要等测试）。枚举体内一个成员的名字解析出来是
  它被赋的**原始元组**而不是成员本身，所以现在四个载体**全是字符串**——类下面一个循环拒掉任何
  「既不是已声明的块、也不在 `CARRIER_FIELDS` 里」的名字。四个，import 期，一视同仁。

**由测试守，且是新增的**：`CARRIER_FIELDS` 是注册表对「载体可以是哪些顶层字段」的声明。
它从内部读不到 schema，所以这条声明由那条走载体链的测试held against
`query_result.schema.json`。

**import 期被拒，但没变**：成员声明时漏了「怎么被读」/「怎么到达读者」，或族声明时漏了 `tells`。
常量本来就是模块级构造的，漏字段本来就是 import 期 TypeError。**是保住了，不是赚到了。**

**然后是更正。** 登记说「拼错的块名成为静态错误，而不是等着某条从未执行的分支抛 AttributeError」。
**在 mypy 下它本来就是**：模块上的 `blocks.IDENTIFICATON` 与类上的 `blocks.Block.IDENTIFICATON`
同样是 `[attr-defined]`，而 blocks.py 早就在被检查的集合里。反例在**两种拼法下都红**，
且是同一个原因。**这一条没有收益。**

**拒绝之外真正赚到的**，是**三张派生列表不再存在**：`DECLARED` 是声明顺序、`ALL` 是集合、
`FAMILIES` 是那四个——迭代这个类同时是这三样，于是「注册表是什么」这个问题只有一个答案了。

**`BY_NAME` 留着，而这是有意的**：`Block(name)` 是同一个查找、也更好读，但一个 `__new__`
连同值一起收事实的成员，会让这个调用在类型检查器眼里是**构造**——于是每一处带类型的查找都成了错误。
两张兄弟注册表（`refusals` / `risk_provenance`）本来就为同一个原因留着这个 dict。
**先删掉再放回去，就是这么发现的。**

**一个陷阱，点名记下**：成员**就是**它的名字，而枚举自己也有一个 `name`——`family.name` 现在是
`"ROUTE"`，以前是 `"route"`。六处读它的地方全部改成读成员本身（f-string 里、当 dict 键、当 test id）。
**一个本身就是字符串的族，不需要一个访问器来说它叫什么。**

**词表到达闸口把这次改动拦住了，而这正是它的用途**：两个新枚举必须各写一行说明「怎么到达读者」。
两个答案都不寻常，值得记：`Block` 是**唯一一个信封用「键」而不是 enum 来陈述的词表**——它的成员**恰好**
是 schema 里 `extensions` 底下的属性名，所以它没有 site 可指，而 site 本来要断言的那个相等，
`test_blocks_registry.py` 已经在两个方向上断言了。两者都 `no_gloss`，理由同一个：
**块名是渲染器被「找到」的方式，族是它产生的那一节**——到达读者的是那一节，带着它自己的标题。

**基线**：5167 → **5168**。**6/6 反例被拒**：三条 import 期、一条测试、一条 mypy。
mypy 131 Success。

**方法论沉淀（第一八一至一八二条）**：
(181)**「改成 X 有什么好处」要一条声称一条反例，并记下「在哪一层被拒」**——本轮六条里，两条的
拒绝层从「测试」升到「import」，一条是新声明，两条**本来就是这样**，一条**登记说错了**。
不做这个拆分，收益清单会把「保住的」和「赚到的」混成一句。
(182)**类型检查器读不懂的「查找」不是查找**——成员带自定义 `__new__` 的枚举，`E(value)`
在 mypy 眼里是构造。派生 dict 不是重复（它不会漂），删它之前先问它当初为什么在。

---

### 没有人在写「失败的步骤」，而五个读者还在找它（2026-08-20，#339）

登记的说法是「`_classify_unidentifiable` 那条不可识别分支已死，插桩跑全量 **0 次**到达」。
**重新插桩，真值不是 0，是 10**：6 次 `unidentifiable_via_backdoor`、2 次 `some_future_rule`、
2 次 `identify_via_iv` —— 而这 10 次**全部落在同一个测试文件的 5 个单元测试里**，它们手工造出
内核造不出的步骤。真实运行（全部 e2e / 语料）一次都没有。**它不是没人来，是被它自己的测试养活的。**

**这把问题换了一个提法**：该问的不是「这一条分支死没死」，而是「**还有没有东西能造出它读的那个形状**」——
而这是一句关于**源码**的断言，不是关于某次运行的。普查 `themis/` 里全部 **87 个 `DerivationStep(...)`
构造点、58 个字面 rule 名**：没有一个落在失败名表里；传 `success=` 的**只有一处**，是验证器的
反序列化器，它转发提交上来的 JSON 说的话。**对内核能造出的任何一步，`_step_failed` 恒为 False。**

**于是「一个读者」变成五个**：那条分支；`_classify_missing_iv` **整个分类器**（同一机制，同样恒不执行
—— 于是 `MISSING_IV_CANDIDATE` 今天**全仓一个产生端都没有**）；外加三处永远不改变结果的合取项。

**根因**：内核说「不可识别」有两种活的说法，**都不是「一步失败了」**——① 一个**成功**的
`tian_hedge_witness` 步，它命名的 c-component 就是证明，验证器能重放；② 完备算法穷尽而无见证时，
走 item 通道的 `UNIDENTIFIABLE_NO_ADMISSIBLE_SET`。「失败的步骤」是被 Tian 接线换掉的**第三种表示法**，
消费端没跟上。

**它为什么看起来还活着**：e2e 那条测试写的是**析取**——`missing_iv_candidate` **或**
`unidentifiable_no_admissible_set`。只有后一支曾经成立。**和 #367 让死标签藏起来的是同一个形状**：
析取会通过，而且不说是哪一边通过的。两半现在分开写。

**闸口不靠语料**（`tests/test_no_step_the_kernel_wrote_says_it_failed.py`）。普查是**封闭的**：
每个构造点要么写字面量（普查直接读），要么在 `RULE_MAY_BE_COMPUTED_AT` 里逐条声明理由（今天 3 条：
dispatch 的 `terminal_rule` 来自一张三条目的字面量字典、scheduler 的两支三元字面量、
验证器的解析器），而 `DerivationStep(**payload)` 这种普查读不到的写法**直接禁止**。
另有一条语料臂，**它的分母被写进 docstring**：15 个 L3 程序里只有 4 个的结果带推导链，共 **10 步、
58 个 rule 里的 7 个** —— 它是旁证，不是覆盖率，说清楚免得被当成后者读。

**空槽变成一张被普查钉住的表**：`GAP_KINDS_WITH_NO_PRODUCER` 两条（`missing_population_distribution`
本来就是占位，`missing_iv_candidate` 这次加入），闸口断言它**恰好等于**「全仓没有任何构造点的 kind」——
两个方向都管。**注意这个普查证的是哪一边**：**0 个构造点是「造不出」的证明；有构造点不是「到得了」的
证明**——`missing_iv_candidate` 在它不可达的那些年里一直有一个构造点。所以**死的产生端不能「留着无害」**，
留着它，完备性普查就会说假话。

**没动的，和为什么**：验证器 `data_gap_rules.py` 那份独立的同名表**留着**。产生端读的是内核刚造出来的
推导链；验证器读的是**别人提交的**推导链，它**可以**声称一步失败了——认出这个声称，是检查它的前提。
线上格式的 `success` 字段同理保留（`derivation.schema.json` 里那句「Failure-bearing rules **MUST**
emit success=false」是一条没有任何产生端遵守的产生端义务，改成真话）。

**基线**：5144 → **5167**。**9/9 反例全红**。mypy 131 Success。

**方法论沉淀（第一七八至一八〇条）**：
(178)**「插桩 0 次」要先问「跑的是谁」**——全量测试和真实运行是两个分母。本轮真值 10 次，全部来自
**为这条分支写的单元测试**：测试造出产生端造不出的形状，把死代码养活。删之前先看那个数是谁贡献的。
(179)**「不可能」是关于源码的断言**——语料只能说「没人来」。要说「来不了」，普查的分母必须是**构造点**，
而且必须封闭：字面量之外的每一处（算出来的 / `**` 解包）要么被声明并逐条读过，要么被禁止；
留一个不封闭的口子，普查就退化成抽样。
(180)**删掉死的产生端，是让完备性普查能说真话的前提**——「没有构造点」是不可能性的证明，
「有构造点」不是可达性的证明。留着一个不可达的产生端，就是给普查喂一句假话。

---

### 已经有一道抓「写错语言」的闸口，而它的分母是一个块的三个键（2026-08-20，#372）

登记的说法是「`late_caveat` 是一整段英文原文，直接印在中文报告里」。属实。但真正该问的是
**为什么没被抓到** —— 仓里早就有一道专抓「producer 写错语言」的闸口，它走
`data_gap_report.gaps[].{description, if_provided, alternative_paths}`，一路全绿。

**根因**：那道闸口的**主语是「缺口的句子」，不是「读者会拿到的散文」**。三个键是当初那两个英文
producer 恰好待的地方。`late_caveat` 从来不在分母里 —— **不是漏判，是没被问过**。

**为什么是根因不是表象**：把 `late_caveat` 翻成中文只修一条；「还有多少段英文会到达读者」仍然没人
知道，而这正是上一次建同型闸口时就该定的分母。

**先量**。15 个 L3 语料，结果里 **3904 条字符串**，凡「读起来是句子」却不含中文的登记：**17 条路径**。

**度量当场给出一条契约里没写过的区分**：这 17 条里只有一半该翻译。公式（`lower_expression` /
`formula_repr` / `derivation.steps[].output`）、引文（`reference`）、以及**用户自己写的原话回显**
（`skeleton.existing.threshold` / `ambiguities[].description`）**必须逐字保留** —— 翻译它们会毁掉
它们的用途。**「不是每一个内核发出的字符串都是在对读者说话」这件事，契约从没说过**，而没有这条
区分，闸口就没法从三个键拓宽到全体（「不含中文」对公式也成立）。

**读者面不止两个**。`bounds_results[].notes` 与 `precision_target` 都不到达报告或浏览器，但
**prompt 里写着**：前者「`notes` | **quote verbatim**」，后者被插进中文模板
`n ≥ {min_sample_size}（{precision_target}）`。**prompt 是第三个读者面**（#348 的教训），两条都是英文。

**反例把我的第一版闸口打回来了，而这是本条最值得记的一段。** 第一版的判据是
「**整串**不含中文即违规」+ 例外表。11 条反例里 **6 条回绿** —— 因为这些散文是**拼接**出来的：
把其中**一个从句**换回英文，剩下的中文让整串仍含 CJK，判据直接失效。

**这不是启发式不够好，这正是原缺陷的形状**：`precision_target` 到达读者的方式就是
「中文模板里插一段英文」。所以判据要**以从句为单位**，不是以整串为单位。

**规则因此被倒过来**：不再是「对所有字符串跑启发式 + 例外表」，而是**显式声明哪些路径是内核在对
读者说话**（`PROSE` 19 条）、哪些不是（`VERBATIM` 10 条），语言规则只作用在 `PROSE` 上。
启发式退到**完备性**那一侧——「出现了既不在 PROSE 也不在 VERBATIM 的路径」——在那里误报的代价
只是加一行分类，不是给错结论。分类的分母也量过：257 条带串路径里，**只有 29 条可能是句子**
（没有空格的字符串在任何语言里都不是句子，标识符与枚举值自动落选）。29 条是一张表，257 条是一场仪式。

**从句判据（`_english_clause_in`）**：把双引号 / 弯引号 / `*…*` 里的内容先去掉（**内核引用的不是
内核写的**），再按 CJK 切段，一段里 ≥4 个词且含 **≥2 个小写功能词**才算英文从句。三处收紧都是被
真实误报逼出来的：`P_rct_50_to_70_pool` 里的 `to`（标识符连下划线数字算一个词）、
`Hernán & Robins What If §9`（**大写的功能词属于名字或标题，小写的才在做语法**）、
以及弯引号里用户自己写的阈值原文。

**两条臂，分工写清**：整串无中文 → 由**不含启发式**的那条臂抓（技术英文可以简练到只有一个功能词，
比如 `6 items with distinct reasons`，它够不着从句判据，也不需要够着）；中英混排 → 由从句判据抓。

**改法**：13 处内核散文改中文（符号 LATE / ATE / α / power / Cohen's h / `strata` **保留** ——
那是读者要去查的名字，翻译过的 α 谁也搜不到）。闸口 =
`tests/test_no_sentence_reaches_the_reader_in_the_wrong_language.py`。

**语料也不是分母**：`late_caveat` 走的条件-IV 路径不在 L3 里，闸口自带一个到得了它的程序。
而且第一版自带的是**无条件变量**的 Z→X→Y —— 于是 `late_caveat` 的**条件那半段**根本没被跑到，
对应反例又是绿的。换成带 W 的条件-IV，并加一条断言「这半段确实到达了」。

**边界（不动的）**：`dispatch.py` 里两处拒答兜底文案是英文，那是 **#327「拒答消息的语言」**的地盘。
本轮翻译 `selection_recovery.failure_reason` 会让那个通道更参差 —— **如实说**：这是把 #327 的
不一致暴露得更清楚，不是新造的，而在中文报告里留英文散文是更差的取舍。

**基线**：5111 → **5144**。**11/11 反例全红**。mypy 131 Success。

**方法论沉淀（第一七五至一七七条）**：
(175)**一道闸口的价值上限是它的分母**——「抓写错语言」和「抓三个键写错语言」是两件事，后者会在
第四个键出现时静默通过。建闸口时先问「主语是什么」，再问「分母覆不覆盖这个主语」。
(176)**判据放在字段上，启发式放在完备性上**——「哪些字段是对读者说话」是**契约该声明的事实**，
声明了就不需要猜；猜的那部分退到「有没有没被分类的字段」，那里猜错的代价是加一行，不是给错结论。
拓宽覆盖时不许判据变松：旧的精确判据要作为单独一臂保留。
(177)**反例回绿时，先怀疑判据的「单位」错了**——本轮 6 条回绿不是启发式不够灵，是它以**整串**为
单位而缺陷以**从句**为单位。同理：允许清单必须逐条被产生过（凭猜想加的 5 条当场被打红），
自带的复现程序必须真的走到那条分支（第一版没带条件变量，半段代码从没被扫过）。

---

### 「哪个门更弱」是数出来的，不是回忆出来的（2026-08-20，#367）

登记的说法是「CDE 的 C2 注释说 `strictly weaker than M4`，代码里它更严」。核实下来那是一族问题
里的一条：`structural_solver` 的中介一节有 **6 条同型断言**——「策略 A 能识别的图集 ⊇/⊊ 策略 B 的」
——**一条都没被计算过**，其中两条是错的。

- `C2 is strictly weaker than M4`：**方向写反**。M4 拒 `w & x_desc`，C2 拒 `w & (x_desc ∪ m_desc)`。
  而且括号里的理由（「CDE 容忍非 M-后代的 X-后代」）**描述了一种不存在的候选**——教科书里那个
  中间混杂器 `L` 正是这种节点，两边都拒。
- 「中间混杂器下 NDE/NIE 失败，但 CDE 仍可能成立」：**假**。同一模块自己的单元测试
  `test_intermediate_confounder_breaks_both` 就断言两条都死——**测试和注释早就互相矛盾，而只有测试被检查**。
- 另外 4 条为真，但同样从没被算过。

**根因**：这 6 条形式相同——「A 的接受集包含 / 被包含于 B 的接受集」，一个**枚举即可判定**的命题。
系统里没有任何东西计算它，于是它们是凭教科书记忆写下的散文。而这份实现有教科书没有的
**结构前置条件**（`mediation_sets` 先要求 `has_path(X,M) ∧ has_path(M,Y)`），它蕴含
**`m_desc ⊆ x_desc`**，于是 C2 的 `| m_desc` 恒为空操作、两条路线的候选池**恒等**。偏差正是在
这条前置条件上产生的：教科书里 CDE 确实能靠 g-formula 处理中间混杂器，而这份实现只做单个 W 的
后门调整。

**为什么是根因不是表象**：把 `weaker` 改成 `stronger` 只修一条；同一节另有 5 条同型断言、其中一条
同样是假的。它们能漂移，是因为一个**可判定的包含关系**只活在散文里。

**先量**。4 节点全枚举（3072 组）与 5 节点（30800 组）：`(NDE 成立, CDE 不成立)` 这一格 **恒为 0**，
反向 256 / 2668；`m_desc ⊆ x_desc` **48/48、2800/2800、联合 18/18 零例外**。

**然后量出了一件登记里没有的事**。顺手统计「`failed_condition` 究竟能取到哪些值」：30800 张图里
NDE/NIE 只吐 `M1`(9122) 与 `M3`(6134)，CDE 只吐 `C1`(12588)。**`M2` / `M4` / `C2` 三个标签不可达**
——而三者都在 schema 的 enum 里、都有中文释义、都会被浏览器印出来。

这才是那条写反的注释的真正来历：**它在描述一个从来没有机会执行的判据**。而不可达的成因是
`_search_mediation_adjustment` 失败时报告的是**「W=∅ 那次检查」的标签**，不是「搜索为什么失败」——
空集不含任何后代，所以成员判据永远说不出口；`M2` 则被 `M1` 短路（前置条件下，W=∅ 时 M2 失败必然
蕴含 M1 先失败）。`default_failed` 参数也因此是**死代码**：size=0 那轮总会覆盖它。

**改法**

1. **四个检查器的成员判据（M4 / C2）移到末尾**——标签必须是「**定理顺序里的第一个失败**」，
   否则「谁走得最远」无意义：一个既违反 M4 又敞着后门的 W 会被标成 `M4`，看起来像走到了终点。
2. **搜索改成两问两遍**：第一遍只在**合规**候选里问「能不能识别」（成功时唯一执行的一遍）；
   失败才跑第二遍，在**不设成员限制**的池子里问「**走得最远的那个候选被哪条挡住**」。
   中间混杂器恰是「满足全部分离条件、只因是 X 的后代而被拒」的那个集合。
3. **两个候选池并成一个**，合规与否交给路线自己的 `_forbidden_for_nde` / `_forbidden_for_cde`
   ——**判定候选的规则与命名拒绝的规则从此是同一个函数**，这正是当初能漂开的地方。
4. **`| m_desc` 保留**：它是 joint do(X,M) 后门判据的正确表述，只是在此前置条件下冗余；
   闸口把这份「冗余」钉成前置条件的**推论**，前置条件一旦放宽，格会当场变。

**改后六个标签全部可达**：M1 5640 / M2 856 / M3 2800 / M4 5960 / C1 5600 / C2 6988，
而 `identifiable` 计数**一个没变**（15544 / 18212）——**只改诊断，不改判定**。
中间混杂器现在说的是 `M4` / `C2`：「能挡住那条后门的变量是有的，但它是 X 的后代」。
比原来的「后门还开着」强得多——后者让读者去找一个变量，而那个变量就在他图里。

**连带修的三处同族**

- `test_mediation_sets.py` 的覆盖矩阵写着「中间混杂器：CDE only」，与它自己下面的测试相反；
  两处 `assert failed_condition in ("M3","M4")` 这种**析取断言**，正是让死标签藏住的写法，改成钉死单值。
- `response_rendering.md` 里有一段**反例式补丁**：「中间混杂器的答案是 `M3`……**不要**告诉读者那是
  `M4`」——它是为掩盖这个缺陷而写的。缺陷修好后补丁本身成了错的，按「写原则不写反例」重写成
  「成员判据与分离判据对读者要求的是不同的东西」。
- `M3` 的中文释义把「中间混杂器」写在自己名下，那个案例现在归 `M4`；三个读者面
  （`envelope_glossary.py` / `verdict.ts` / prompt）一起改。
  `test_vocabulary_reaches_the_reader_as_a_word.py` 里硬编码的释义片段改成**问表**——
  测试自带一份句子片段本身就是第二张表，它也会漂。

**代价，量过并处理过**（不默默吞下）。第二遍在**不设限**的池子里搜，成本随池子三次方涨。用一个
「11 节点、8 个中间混杂器」的对抗图做同进程对比：失败路径 **0.44ms → 36ms（82×）**。三步处理：

1. **检查器变成「绑定到图的路线」**（`_Route`）——与候选 W 无关的东西（两张残缺图、禁止集）在建
   路线时算**一次**，而不是每试一个 W 重算一遍。这不只是提速：它把「什么不依赖 W」写成了结构，
   而且让路线**同时交出** check 与 forbidden，正是当初两条规则能漂开的地方。36ms → 26ms。
2. **每个候选最多检查一次**：第一遍已经看过合规候选并记下它们走到哪，第二遍只看被成员判据挡住的
   那些——正是它存在的理由。
3. **第一遍没挡住任何候选时，第二遍不存在**。

剩下的 26ms 是问「哪个候选走得最远」的固有代价，且只在**识别失败**时付。全量 **725.76s**，与本轮
之前的 720s 持平（中途一次 1328s 是机器负载，不是这个改动——同进程对比才是干净归因）。

**闸口**：`tests/test_which_gate_is_weaker_is_a_count.py`。枚举四节点全部标号 DAG × 全部潜在边子集，
钉住包含格（单中介 + 联合双向）、两条路线禁止集恒等（作为前置条件的推论）、以及
**契约声明的每一个条件都真能被报出来**——最后这条正是旧代码会红的那一条。

**基线**：5103 → **5111**。**12/12 反例全红**。mypy 131 Success。前端已 `pnpm build`。

**方法论沉淀（第一七二至一七四条）**：
(172)**「A 比 B 强/弱」是可枚举判定的命题，就该由枚举回答**——散文里的强弱断言必然随实现漂移，
尤其当实现有教科书没有的前置条件时（本轮就是 `M 必须真的中介` 使两个判据坍缩成一个）。度量它，
把数放在断言旁边。
(173)**prompt 里出现「不要告诉读者 X」这种反例式补丁，多半是在给一个实现缺陷打绷带**——先去查
那个缺陷。本轮那句「中间混杂器不要说成 M4」写下时 M4 根本不可达；缺陷修好，补丁自己成了错的。
(174)**诊断字段要回答「搜索为什么失败」，不是「某一个候选为什么失败」**——报告最小候选的失败等于
报告空集的失败，而空集不违反任何成员判据，于是最该说的那句话永远说不出口。同族的藏匿手法是
`assert x in (A, B)`：析取断言无论代码说哪个都过，不可达的那一支就永远不会被发现。

---

### 「不存在」有两种合法拼法，而没人规定过哪种（2026-08-20，#371）

登记的说法是「`point: null` vs 键不存在，两个容器两种写法」。核实下来更准的说法是：
**同一个 JSON 路径上两个写入者各写各的**——`extensions.causation.pn.point`，θ 路线
（`scheduler._poc_quantity`，docstring 还写着「absence is itself information」）**不写这个键**，
数据路线（`dispatch.py`）在同样情形下写 **`null`**。schema 的描述把这件事记成「两个容器各有
一种写法」，而实际上 `extensions.causation` 这**一个**容器两种都收。

**根因**：契约规定了「一个键可以取什么值」，从没规定过「**没有**这件事怎么拼」。一个键只要
同时「可缺省」且「可为 null」，两种拼法就都合法、都表示同一件事，而**没有任何消费者能分开**。

**为什么是根因不是表象**：如果病在 `_poc_quantity` 少写一行，改法就是补一行。但同一路径的两个
写入者能分歧，是因为**契约层允许分歧**；下游因此养了两套机械——θ 路线 `kernel.py` 用
`("point" in a) != ("point" in b)` 核**存在性**，数值孪生 `_num_eq` 核**值**，同一个问题两种写法
两道检查；schema 还要用 `allOf + required` 把 required 补回到总是写它的那个容器上。

**先量**。schema 展开 `$ref` 后 **971 条可声明实例路径，76 条同时可缺省且可为 null**。再插桩全量
跑一遍录**实际发出的拼法**（`validate_result` 与 `run` 两个源分开记，另记每个键所在容器的
`method`）：只发一种拼法的 67 条（只发 null 25、只发缺省 20、只发实值 12、从不携带值 7、
永远是 null 3），两种都真在发的只有 **9 条**。

**度量把规则本身改了**。原打算「每个键只留一种拼法」。但 `numeric_estimate` 里 `point` 与
`ci_lower` 的缺省是**同一批 60 条结果，逐方法完全同步**——causation 界 14、反事实格 16、
剂量反应 6、联合 10、中介 14——那是「这个方法的答案根本不是一个顶层点估计」这一类。那里缺省
与 null 不是一件事的两种拼法，而是**两件事**：「没有头条数字」与「有，但没算区间」。
`bounds_results` 的数值端（245 / 75）与 `std_error` ↔ `doubly_robust`（各 11）同样整组共现。

所以最终的规则是：**一个键可以既可缺省又可为 null，当且仅当它落在一个 `dependentRequired`
互相绑定的组里，且组里有一个不可为 null 的锚**——锚在不在，回答「这个概念属不属于这份答案」；
成员是不是 null，回答「有没有这个数」。没有锚，两个状态就没有任何东西能读出差别。
三种无歧义形状照旧合法：必填+不可 null、必填+可 null、可缺省+不可 null。

**改法**（#363 的原则：能让它不可表达，就不要去检测它）

1. **67 条只发一种拼法的**，在 schema 里把另一种关掉——零行为变化。
2. **9 条真含糊的**：`extensions.causation` 的 `pn/ps/pns.point` 与 `instrument` 定为
   **必填 + 可 null**，θ 写 null；`numeric_estimate` 的 `point/ci_lower/ci_upper`、
   `std_error/doubly_robust`、`bounds_results` 的 `lower_value/ci_lower/ci_upper` 三组各自
   用 `dependentRequired` 互绑。
3. **`causationQuantity` 一分为二**：结构块从共享 `$def` 白拿了 `ci_lower/ci_upper` 两个字段，
   **两个写入者谁都没写过**——拆成 `causationQuantity`（lower/upper/point）与
   `causationEstimate`（多两个 ci），`allOf + required` 那块补丁随之消失。
4. **`kernel.py` 的存在性核对退化成值核对**，与数值孪生同一句话。
5. 顺带撞见的**描述与代码不符**：`bounds_results[].lower_value` 说「没做数值求值时为 null」而
   写入者根本不写这个键；`first_stage_f_stat` 说「退化时为 null」而写入者是 `if is not None` 才写；
   `data_gap_report` / `formula` 各有一条**从没被产生过的 null 分支**（`to_dict` 只在非 None 时写）；
   `numeric_result.unit` 内核从不产生，只在调用方 JSON 往返时存活。

**闸口**：`tests/test_there_is_one_way_to_say_there_is_none.py`。`$ref` 走查提到
`tests/schema_walk.py`——第二道门问同一份文档的另一个问题，两份 `$ref` 走查就是两张曾经相等的表。
闸口自己先暴露了一个洞：`null` 还能写成 `oneOf: [X, {"type":"null"}]`，只看 `type` 会把「可为 null」
读成「不可为 null」；补上之后当场多找出三条（`formula`、`data_gap_report`、
`recovered_ate.sufficient_statistics.naive`）。判据自身单独钉（文档里没有 oneOf-null 且可缺省的键，
所以砍掉那条判据不会有任何活键变红）。

**为什么读者侧一行没改，而这正是重点**：所有读者早就写成 `.get(key)` / `!= null`，两种拼法答案
一样。病就是这么活下来的——它从来没让任何一次渲染出错。代价是**契约无法被检查**：一个悄悄不再
写某个键的写入者，在防御性读者眼里与「这条路线没什么可说」一模一样。同理浏览器的 `types.ts`
不受这条规则约束——那是**只读视图**，`?: T | null` 在那里是防御，不是写入者在两种拼法里选。

**如实说**：规则钉在声明上而不是流量上，所以它有多强取决于声明在哪里被强制——`run()` 不校验
自己的产出，写入者只有在有人调 `verify()` 的地方才受契约约束（审计路径、web 端点、会校验的测试
模块）。

**基线**：5098 → **5103**。

**方法论沉淀（第一六九至一七一条）**：
(169)**契约要规定「没有」怎么拼，否则它由写入者逐处自选**——判据：一个键若同时可缺省且可为 null，
就问「这两种状态有没有任何消费者能分开」；答案是「没有」时，它们是同一件事的两种拼法，多出来的
那种只是给两个写入者留了分歧的余地。
(170)**度量可以推翻自己提出的规则，要让它推翻**——本轮原定「每个键只留一种拼法」，逐方法计数
显示 `point` 与 `ci` 的缺省完全同步，那是两件事而非两种拼法；规则于是从「消灭一种」改成
「必须有一个锚把两种分开」。先量再定规则，量完还要允许规则改。
(171)**读者写得够防御，是病能长期潜伏的原因，不是没病的证据**——`.get(key)` 对缺省和 null 一视同仁，
所以两个写入者分歧多年而渲染从不出错；判断「这处不一致要不要修」时，别拿「反正没渲染错」当理由。

---

### 一个键由谁说，有四条通道，只有一条是一等对象（2026-08-20，#370）

#369 收尾时如实登记了自己的上界：把「这个部件到得了读者吗」**块限定**地问——这个块**自己的**
渲染器拼不拼写这个键——168 个叶名里 77 个答不上来。这一轮先把那 77 重新量了一遍。

**第一件事是度量更正**。#369 自己刚建的**详情表**是一条通道，而普查不知道它存在——那张表的键
就写着 `extensions.<块名>.numeric`，**块名在键里**，可查而没人查。把它算进去，数字从
**78/181 掉到 44/181**。

**根因：「一个键由谁说」有四条通道，只有一条是一等对象。**块自己的渲染器（`blocks.bind` 记录）
可查；载体（`Block.carried_by`）可查，但只到**块**这一级；详情表可查而没查；「同一事实在别处
已说」——`kind` 复述块名、`reference` 由信封走查渲染、`treatment`/`outcome` 是问题本身、
`checks[]` 是验证器的证据——**连记录都没有**。

**为什么是根因不是表象**：如果病在「渲染器少印了几个键」，修法就是补渲染器。但逐条看，44 条里
绝大多数读者其实看得到，只是看到的地方不是这个块。分母（键）对、分子（拼写）对，错的是**归属**。

**逐条分类时撞见的四处真问题**

| | |
|---|---|
| 选择偏倚的 Z⁺ / Z⁻ | 报告结构层印「经选择后门调整 {w, v}」，把整个 Z 说成挡后门的。而判据 `_zplus_blocks_backdoor` **只对 Z⁺ 检查阻断**：Z⁻ 是处理的后代，按构造挡不了后门 |
| 同上，数值层 | 括号里的解释**说反了**——写着「Z⁺ 在这份被筛过的样本里就能估；Z⁻ 只能从外部样本估」，而 `_external_ledger` 在 Z⁻ 为空时要的恰恰是 `unbiased P(z⁺)`，Z⁻ 非空时要的是整个 `P(x, z⁺, z⁻)`，Z ⊥ S 时两者都不需要外部数据。三个分支上全错 |
| 单调性被推翻的份额 | `bootstrap_draws_infeasible / (used + infeasible)` = 所声明的单调性在这份数据上离被推翻有多近——这是本系统对一条「不可检验假设」最接近检验的东西，而**只有可剥离的 explainer 说它**，主报告与浏览器都不说 |
| 路线自己声明的前提 | `longitudinal_identification.assumptions` 与两个中介块的 `nde_nie` / `cde` 两臂共 5 处，装的是词表 id（schema 自己写明「IDs reuse the renderer assumption glossary」）。台账读四条通道，这条不在里面。跑过估计器的路径上，估计器的扁平清单里带着同样的 id，所以**恰恰在有数的地方看不出来**；纯结构 / θ 路径上，块里列着 Pearl 2001 的四条跨世界条件，台账一个字没有 |

第四条是这一轮最该留下的教训：我本来要写一行 `said_by="assumption_ledger"` 就过去了——**块限定
地问，逼着我去查那句话是不是真的**。它不是。

**改法**

1. **闸口的问题换成块限定的那一个**：一个键被答上，当且仅当这个块**自己的**读者拼写它——
   `bind` 记录的渲染器 ∪ 键里写着这个块名的详情表条目 ∪ 载体的重述者。这条闸口成立则 #369 的
   下界自动成立，所以那条并入而不是并列。
2. **答不上来的写行**，沿用 #369 的三种答案，只把 `said_by` 的取值域拓宽到「一个读者函数」，
   并检查**它从 `build_analysis_report` 可达**——这正好堵上 #369 自认的那个弱点：没人调用的死
   渲染器照样拼写它读过的每个键。
3. **Z⁺ / Z⁻ 分开说**，两个面同构：Z⁺「不是处理的后代，挡后门路径的是它」；Z⁻「是处理的后代，
   挡不了后门，条件在它上面是为了让选择节点与结局条件独立，代价是恢复式里多一层重加权」。
   「哪一半要外部样本」是另一个问题，由 `external_data_needed` 回答。
4. **单调性被推翻的份额进主报告与浏览器**。
5. **台账加第三条通道**：`ROUTE_PREMISES` 五处，`themis/ledger.py` 加 `identification_premise`
   这一行生产者（比估计器那行更窄：只写 identification + inherent），验证器
   `_declaration_channels` 独立地把同样五处写一遍——**验证器不 import 生产者**，两边各写各的。
6. **`joint_identification.note` 删掉**：一个写入者、零个读者，内容是英文散文，说的是同一条
   分支的渲染器已经用中文说得更好的那件事（#338 的形状）。
7. **五处站点两边各写一遍，但都钉在 schema 上**，不是互相钉——互相钉只能说明两边一致；要失败的
   是「schema 里加了一条路线，而任意一边忘了」。这一条是写反例时才发现必须加的：把验证器那份
   剪掉，什么都没红——一条被盖成 identification/inherent 的路线前提与估计器的无法区分，伪造检查
   抓不到它。

**闸口如实说的话**：仍只在一个方向可靠——名字不在渲染器整个调用闭包里就一定没被读；在里面则
可能只是躺在某个分支、某条 docstring 里。两条弱点写进文件而不是修掉：死渲染器照样拼写（所以
指向读者函数的行被钉在「可达」上，所以底下有那些句子级的钉子），以及渲染器可以读了一个键却
什么都不印。

**基线**：4970 → **5098**。

**方法论沉淀（第一六六至一六八条）**：
(166)**「同一事实在别处已说」是一条真实的通道，而它没有一等对象**——`carried_by` 只到块这一级，
键这一级只剩人的记忆。判据：一条「别处会说」的断言，如果无处可查，就是无法被证伪的断言。
(167)**把断言写成一行之前，先去查那行是不是真的**——块限定的问题的价值不在它挡住了什么，而在
它逼着每一条「别处会说」的默认信念被验一遍；这一轮四处真问题里有一处正是这样掉出来的。
(168)**一条渲染器里的括号解释也是一个可以被代码证伪的断言**——「Z⁻ 只能从外部样本估」看起来
像人话不像判据，但它在三个分支上都与 `_external_ledger` 相反。凡是解释「为什么」的读者面文字，
都要拿产生它的那段代码对一遍。

---

### 到达读者的分母只到「有人画线的那一层」，而线每次只往下挪一层（2026-08-19，#369）

登记项是「extensions 各块的逐部件普查不存在」。量出来的分母是 **schema 全深度下的 189 条声明
键路径**（当时），其中 **39 条任何读者面都不拼写**——这是一个**声音下界**：没有任何面拼写过的
名字，一定没有被读。

最大一簇 21 条挂在同一个键名下：**`numeric`**。四个**路线块**各自带一个 `numeric`，装的是
**θ 路径**算出来的数（对着你声明的概率直接算，不碰数据）。

**跑真查询看到的**

| | |
|---|---|
| CLadder Q1358（θ 中介） | 算出 TE=+0.1387、**NDE=−0.0725**、NIE=+0.2112、CDE 随中介取值从 −0.13 翻到 +0.10；报告只印「**0.1387**」和「可识别，无需调整」 |
| 条件 IV（θ Wald） | 报告把 `late_caveat` 整段英文原文印给读者，那段话写着「**aggregates the per-stratum LATEs in `strata`**」「`treatment_shift` is that subpopulation's share」——而 `strata` 与 `treatment_shift` 一个字都没显示 |

中介分析的全部内容就是「直接与间接反不反号」。这里反号了，读者拿到的是它们的**和**。

**根因：「这个部件到得了读者吗」历来只在有人画线的那一层被问过一次，而线每次都只往下挪一层。**
`blocks.bind` 问的是 18 个块；#368 问的是 `numeric_estimate` 的 27 个**直接**属性。两次画线都是
出事之后手工挪的，挪完那一层就停。**块内部的键从来没有分母。**

**为什么是根因不是表象**：39 条里没有一条共同的业务原因。`numeric` 是**家族错配**（路线块渲染器
回答「怎么识别的」，`numeric` 回答「结果是多少」）；`recovery_formula` / `factorization` 是**同族
但渲染器停早了**（说了「可恢复」，没说恢复式）；`type_reconciliation.checks[]` 与
`observational_joint` 是**验证器的充分统计量**，本来就不为读者而写。三种互不相干的成因、同一个
后果——共同的原因不在任何一条上，而在「这一层没有分母」。

代码自己把这句话写在那里了：详情表的注释说「这一节被同一个缺口逮到过两次…到十个的时候，追加
一行不再是修复」——然后它**又开了一张绑在一个容器上的表**，第四次就落在这张表外面。

**改法**

1. **详情表的键从「`numeric_estimate` 的一个属性」改成「信封里的一条路径」**，两个面同构。原有
   十条变成 `numeric_estimate.<name>`，四条 θ 路径加进来。一张表既装得下这个容器的属性，也装得下
   别的容器的——这正是「绑一个容器」买不到的东西。
2. **两条恢复路线说出它许可你算什么**：`recovery_formula` / `factorization` / 协变量边缘那一层。
   「可恢复」是判决，恢复式才是判决许可的计算；别的路线的估计式由 `result.formula` 说，恢复路线
   自己写了一份，所以那条线够不到它。
3. **反事实格说出它是哪一格**。四个布尔量（实际处理、实际结局、若当初的处理、问的结局）各换一个
   就是另一个问题，而两个面此前都写「该反事实格的区间 […]」——一个没有名字的量上的区间，读者
   无法拿它对照自己问的问题。
4. **把块内部还开着的 map 关掉**。#338 关了 18 个块的 map 就停了；往下一层量，**还有 14 个开着**，
   其中 `cde_status` **已经在实发两个没人声明的键**（参考点数量与上限）。同时把 `pn`/`ps`/`pns` 与
   `observational_joint` 指向已有的 `$defs`，那四个 P(X,Y) 格子此前也是从一个开着的 map 漏出去的。

**闸口**：`tests/test_no_part_of_a_block_is_silent.py`。分母来自 schema 全深度（跟着 `$ref` 走——
不跟的话中介集那一整棵子树都不在分母里，而那正是这个文件要抓的漏法）；判据是那条声音下界；
例外必须写行，三种答案各自被检查——`consumed_by` 要真的读那个键，`said_by` 指向的路径自己得到达
读者，`vocabulary` 指向的必须是 `test_vocabulary_reach.py` 里**关于这个键**且**写了 no_gloss** 的
那一行（理由留在一处，这边只指过去，不复制）。

**如实说这条闸口值多少**：它只在一个方向上是可靠的。反方向的假阴性照旧——`outcome` 这种键名
在别处被读就算「到达」，渲染器也可以读了一个键却什么都不印。把同一个问题**块限定**地问，168 个
叶名里 **77 个**本块渲染器没有拼写（多数是合理的：跨块抄写、走信封的引用渲染器、复述块名）。
要把它做成闸口需要渲染器声明自己的读集——**登记为 #370，没有默默略过**。

**另外两条登记**：#371（「没点识别」在两个容器里一个写 `point: null`、一个不写这个键，而 kernel
的显示副本核对把**存在性**当事实核对，所以两边都固化了）；#372（`late_caveat` 是一整段英文散文，
直接印在中文报告里，还指着信封的键名说话）。

**基线**：4876 → **4970**。

**方法论沉淀（第一六三至一六五条）**：
(163)**分母的深度是被上一次事故决定的，不是被结构决定的**——每次「往下挪一层」都只挪到刚好
盖住这次的漏；判据是「这条线是谁画的、为什么画在这里」，答案若是「上次在这里出事」，那么下一层
一定还没有分母。
(164)**同一个容器可以同时回答两个问题**——路线块的 `numeric` 是答案不是路线。绑容器的渲染器
只会回答这个容器「主要」回答的那个问题，另一个问题的键就静默；判据是「这个键回答的是不是它
所在容器那一族的问题」。
(165)**闸口要如实说自己在哪个方向上可靠**——声音下界值得建，但必须把假阴性的规模一起量出来
写进去，否则「有闸口」读起来像「已覆盖」。

---

### 引用是横切字段，而每一个渲染器都绑在一个容器上（2026-08-19，#338）

登记项是一个字段：`extensions.scm_counterfactual.estimated_from_data`，一个写入者、
零个读者，「决定要不要删」。量它的时候顺手把 `extensions` 全部 18 个块做了一遍键级普查，
并且**在两个出口 hook 住 `blocks.check_registered` 跑了一遍全量**，拿到每个块运行时真正
发出的键（静态扫描漏了一半——多数块由构建函数返回，不是字面量）。

**量出来的**：读者面一个都到不了的键有 4 个，其中 3 个是同一个名字 `reference`。
顺着它全仓再量：

| | |
|---|---|
| 写入点 | **7 处** |
| 所在容器 | **6 个**——`scm_counterfactual` / `selection_recovery` / `missing_data_recovery`，以及 `numeric_estimate` 底下的 `decomposition` / `four_way_decomposition` / `four_way_ratio` |
| schema 声明 | **5 处**（两处还是 `required`）|
| 渲染它的面 | **0** |

**根因：引用是横切字段，而每一个渲染器都绑在一个容器上。** 这个系统里每张渲染表的单位
都是「某个容器里有什么」——块族表（ROUTE/ANSWER）、答案形状表（`Shape.lives_in`）、
#368 刚建的细节表（`numeric_estimate` 的直接键）。一个「每个容器都可能捎带一句」的字段，
在每张表里都不是那张表的主题，于是每张表的作者都合理地把它当成别人的事。**#368 里我自己
就是这么漏的**：渲染 `four_way_decomposition` 时把四块数、CI、尺度都渲染了，没渲染它带的
那句 VanderWeele 引用。

**为什么是根因不是表象**：它预测名单，也预测漏法的形状。每个容器里**属于该容器主题**的
字段都被渲染了，一个例外都没有；被漏的恰好是那一个**跨六个容器同名同义**的字段；而且是
**六个容器一致地漏**——六个作者独立做出同一个决定，说明决定不在作者手里。

**改法**

1. **引用的渲染绑在信封上，不绑在容器上**——一个渲染器走整个结果收集 citation，在
   「怎么算出来的」末尾作为「依据文献」出一次，同名同源的说一次。两个面同构。绑到「今天
   有引用的那六个容器」会渲染出一模一样的六条，然后以同样的方式丢掉第七条——那正是要拆掉
   的东西。测试的参数集**从 schema 走出来**，不是文件里的名单：第七个容器声明引用的那一刻
   就被覆盖，不需要任何人记得这个文件。
2. **删 `estimated_from_data`**。#334 把「结构方程是你声明的还是 OLS 拟合的」给了正主
   ——两条路径本来就是两条 rule，两条 rule 各有中文词条——这个 bool 于是成了第三份记录，
   和上一轮删掉的 `inference` 同型。
3. **把还开着的块关掉**。删完之后 `scm_counterfactual` 的声明键正好等于运行时实发键，
   `additionalProperties` 从 `true` 改成 `false`；同批把 `causation`、`assumption_ledger`、
   `identification` 一起关（前两个声明本来就完整，`identification` 补声明它的 7 个伴随键）。
   开着的只剩 `ambiguities` 一个，它开着有写下来的理由（内容由调用方/LLM 撰写，枚举它就是
   让内核决定调用方能报哪些歧义）。

**顺带发现，也是这一节该记的**：#342 那个文件的 docstring 里已经写着「其余每个块都拿到了
封闭的形状，这一个不能」——**这句话从没被检查过**，而说它的时候有四个块开着。现在它是一条
检查（`test_every_block_we_emit_is_closed_but_the_one_that_argues_for_it`），开放需要一条
写下来的理由，理由和名单在同一个 dict 里。

**更正登记的说法**：「schema 里也没有」只对了一半——**块**在 schema 里（#342 已经补齐 18/18），
**字段**不在。而字段能不在，正是因为这个块是六个带引用的容器里**唯一开着的那个**：
`numeric_estimate` 那三个都是 `additionalProperties: false`，写错一个键当场报错；
`selection_recovery` / `missing_data_recovery` 也是。一个对任何键都说「行」的块，
无法报告一个没人决定要带的字段——而那正是它会攒下的字段。

**更正一条已记录的决定**：`identification` 原先保持开放，理由写在 schema 描述里——
「伴随键的出现与否由 pattern 决定」。那句话是对的，但它论证的是**可选性**，不是**开放性**：
声明一个字段不等于要求它。开放对可选性没有任何贡献，却付掉了封闭唯一能买到的东西——
写错的键会报错而不是消失。改为逐个声明（不给域，只给类型）＋关闭。

**闸口验过（10 个反例逐个构造，全部当场变红）**：这一节不再渲染引用、把渲染绑回
`extensions` 一个容器、去掉去重、引用落到「怎么算出来的」之外、浏览器改成列容器而不是走
信封、浏览器算出来却不显示、重新打开 `scm_counterfactual`、重新打开 `identification`、
渲染了却不声明（真实 run 过不了 schema）、以及**把 `estimated_from_data` 再写回去**
——最后这条证明了关掉之后的 schema 会当场拒绝这一项一开始要处理的那个字段。

**声明的欠账（没有默默略过）**：`extensions` 各块的**逐部件到达读者**普查仍然不存在
（#368 为 `numeric_estimate` 建的那种）。`reference` 这条被绑信封的渲染器根治了，但一般性
保证没有。而且 #368 那份普查的分母只到 `numeric_estimate` 的**直接键**——`reference` 所在
的「块内部的键」这一层，连它都没覆盖到。两条已写进那个文件的 docstring 并登记为 #369。

**基线**：4864 → **4876**。

**方法论沉淀（第一六〇至一六二条）**：
(160)**横切字段会被每一个绑容器的渲染器合理地漏掉**——判据是「这个字段是不是每个容器都
可能带一句」；漏法的形状会说话：一个容器漏是疏忽，六个容器一致地漏是结构。
(161)**开放的容器无法报告「没人决定要带的字段」**——它会攒下的正是那种字段。开放要有写下来
的理由，而「这些字段是可选的」不是理由：声明不等于要求。
(162)**只写在 docstring 里的规则不是规则**——「除了这一个，其余都封闭」这句话说出来的时候
就有四个反例，因为没有任何东西去数。

---

### 「怎么算出来的」绑的是 extensions，而数是怎么算的记在 numeric_estimate 上（2026-08-19，#368）

#366 建了门之后，`numeric_estimate` 底下还剩 12 个复合块 `unrendered`。登记说
「先查 `inference` 是不是死字段，是就删，不是就渲染」——量下来它两样都不是，而剩下的
11 个也不是同一件事。

**根因：一节，两半，只绑了一半。** 报告与浏览器都有「怎么算出来的」这一节，两边都绑在
`extensions` 上（`blocks.bind(blocks.ROUTE, …)` / `ROUTE_RENDERERS`）。而「这个数是怎么
从数据里算出来的」这半边记在 `numeric_estimate` 上——**绑定看不见它**。这一节自己的注释
已经写过同一件事两次：

> ``formula`` … is a field rather than a block, so the binding above — **which is
> what catches a block nobody renders** — never looked at it, and for ten rounds the
> report said 「机器可读，见 result.formula」

> A route is written as a BLOCK only by the identification patterns that produce one;
> every other way of arriving at a number records what it did in ``step.rule`` …
> **Binding the section to the block family therefore left it empty for six query kinds**

两次都是**手工追加一行**补的。第三次是 10 个块——一张分层表、两条独立的纵向路线、
三个各自带着「不用这个方法会得到什么数」的校正——**到十个，追加就不再是补法了**。

**为什么是根因不是表象**：它预测名单。被渲染的 14 个恰好是 `answers.Shape.lives_in`
那一个键、形状渲染器顺手多读的兄弟键、和 `_estimate_meta` 那条共享行；到不了的 10 个
恰好是「方法声明 POINT／MEDIATION 之后，除答案键以外的细节块」。名单不是随机的。

**改法**
1. **两个面各加一张按 schema 细节键分派的表**，位置在识别公式之后、推导链（骨架）之前，
   进的是**已经存在的那一节**，不新开一节：识别是怎么找到估计式的，这是估计量拿到数据
   之后做了什么，两半合起来才是一个论证。
2. **逐面对等这次是可查的**：两个面都用表分派，于是两张表可以**按顺序**相等地钉住，
   不需要写第三份名单。（其余块的逐面对等仍不查，属 #313/#340/#347 那族。）
3. 渲染出封闭词表成员就得有词：新增 `MEASUREMENT_SIDE`（哪一侧被误分类）与
   `FOUR_WAY_MEDIATOR_SCALE`（走 eAppendix 哪个闭式）两张表，两面逐字节相同。
   `test_vocabulary_reach` 里这两行从 `no_gloss` 改为 `glossed_by`——其中
   `four_way_mediator_scale` 的旧理由（「四个分量按名字渲染了」）当时就是假的，
   那个块根本没有被渲染过。

**`inference` 删掉，不是渲染。** 它不是死字段（dispatch.py 在 `ci_method ==
"influence_function"` 时写它），但它记的两件事**都已有正主**：`method` 是单成员枚举，
值被创建它的那个 `if` 钉死，与同一分支上两行之前的 `ci_method` 逐字相同；
`cluster_robust` ＝ `cluster is not None`。而 `verifier/cluster_inference_rules` 的模块
注释明说这套审计成立**正是因为该事实从两个独立方向进入信封**——`estimation_context.cluster`
（运行时解析的）与 `numeric_estimate.assumptions`（估计量自述，且已有中文台账句
「影响函数方差按 X 做了簇稳健修正」到达读者）。`inference` 是 dispatch 层把自己刚传进去的
东西再说一遍的**第三份副本，来自那两个方向之外**；而且因为它只记一个 bool 而不记列名，
**结构上就无法被佐证**——旁边的 `bootstrap` 记了 `cluster_column`，所以它能被核对。
**一个不说出自己在断言什么的断言，只能被相信，不能被核对。**

**顺手更正上一轮自己写错的一行**：`bootstrap` 那行写的是「没人读」，实际它被
`themis/verifier/cluster_inference_rules.py` 当键读——是 `consumed_by`。错的方向正是
门查不到的那个方向：`consumed_by` 会被核实，`unrendered` 只对着读者面核实。

**顺手补一个共享工具的坑**：`web_source.string_list` 直接对数组字面量做引号提取，
英文注释里一个撇号（`the schema's own names`）就会开一个引号、在下一个条目上闭合，
于是这份名单**静悄悄少几个成员、多一段自己的碎片**。已改为先丢掉整行注释——
以 `//` 开头的行永远不是内容，而含 `//` 的字符串以引号开头，两者不会混。

**闸口验过（12 个反例逐个构造，全部当场变红）**：schema 新增未表态部件、渲染器不再读
它被声明负责的键、报告少一条细节而浏览器还有、两面顺序不一致、浏览器的顺序名单点到
渲染表里没有的键、恢复值不再显示它所纠正的那个数、封闭词表退回裸标识符、细节没有接进
那一节、词表少一个成员、浏览器的词与内核的词漂开、`consumed_by` 点名一个不消费它的模块、
`unrendered` 声明被渲染器当场证伪。

**skipped 从 144 变成 145**：`unrendered` 行清零之后，那条按 `unrendered` 行参数化的检查
参数集为空，pytest 记一个 skip。这是容器的现状，不是检查的缺口——`unrendered` 仍是合法
答案，一旦有行用它就立刻生效（反例 12 就是这么验的），已写进那条检查自己的 docstring。

**基线**：4849 → **4864**。

**方法论沉淀（第一五七至一五九条）**：
(157)**一节的绑定只覆盖问题的一半时，另一半不会报错，只会不出现**——判据是「这一节的
标题问的是什么，绑定枚举的又是什么容器」；同一处已经用「追加一行」补过两次，就说明
绑定漏了一整类，不是漏了一个。
(158)**「没人读它」有三种解法，不是两种**：渲染、留给非读者消费者、以及**删**——一个
到不了读者的部件，可能是缺渲染，也可能是同一事实的第 N 份副本。先问「它记的事实有没有
正主」，再问「谁渲染它」。
(159)**只记 bool 不记对象的断言无法被佐证**——`bootstrap` 记了列名所以能核对，
`inference` 只记 True/False 所以只能被相信。要审计一句断言，它必须说出自己在断言什么。

---

### 完备性纪律继承了它被挂上去的那套机制的分母（2026-08-19，#366）

登记的是「AR 置信集三个块两个确定性读者面都没有，只有 prompt 认识它」。
登记自己要求先量 `numeric_estimate` 底下还有几个同病——量完，**分母是 19，不是 3**。

**根因写在 `themis/blocks.py` 的开头**：

> A result carries two kinds of part. **The typed ones are fields of
> `QueryResult`** … a misspelling is an `AttributeError`. **The rest live under
> `extensions`** … and a misspelling there is silence.

注册表的分母是按**「拼错了会不会静默」**划的。后来 #333 把「这一块怎么到达读者」
（`read_as` / `carried_by`）挂到了**同一张表**上——于是「谁读它」这个问题的分母，
**继承了「拼错会不会静默」这个问题的分母**。这两件事毫无关系。`numeric_estimate`
是 `QueryResult` 的有类型字段，所以挂在它下面的 28 个复合部件从来没被问过「谁读你」，
不是因为有人判断过它们到达了读者，而是**因为它们拼不错**。而它们里有 19 个根本不是
「一个数的零件」，是整整一节：一张分层表、一个过度识别检验、一个有七种形态的置信集、
一整套四分解。

**这是同一个模式的第三次出现**：#362 是「in themis 被读成 in Python」，#357 是
「落在哪扇门由内核要不要分支决定」，这次是「完备性纪律继承了它被挂上去的机制的分母」。
判据一样：**读到「每个 X 都……」，就去问「X 是怎么被找到的」**。

**改法**
1. **建门** `tests/test_the_answer_has_no_silent_parts.py`：按 schema 走
   `numeric_estimate` 的复合部件，一部件一行，三选一且互斥必填——
   `rendered_by`（点名**那个渲染器**）／`consumed_by`（消费者不是读者而是验证器）／
   `unrendered`（**断言不是豁免**：必须点名读者因此拿不到什么，且门**反向核实**这条
   声明为真——一个说「没人渲染我」却被渲染了的行，和一个claim 了渲染器却没有的行，
   一样红）。
2. **新行不进 `blocks.py`**：这些名字已经只存在于 schema 一处，再写一份 28 个的
   Python 声明，正是那个注册表要防的重复反着来。schema 给名字，行只给答案。
3. **渲染 6 个**（AR 三块 + `over_identification` + `propensity_summary` +
   `ovb_sensitivity`），两个面都进**共享段落**（`_estimate_meta` / `estimateMeta`）
   而不是各开一节——它们全是「这个区间有多可信」的答案，且各自只在某一条估计路径上
   出现，只有部分路径能到的独立小节是大多数读者永远不知道存在的小节。

**「读了」的判据必须是「当键读」，不是「提到这个词」**：第一遍用裸词匹配，把
`bootstrap` 判成已渲染（因为 `data_gap_report` 有段 docstring 在讲发现层的边稳定性
bootstrap），把 `inference` 判成已渲染（因为一句注释写着 "an inference from residue"）。
**一道写它的人自己就能满足的守卫，正是 `blocks.py` 当年吃过并已经换掉的那种。**
收紧成「带引号的键／属性访问／对象键」之后，真实静默数从 15 升到 19。

**AR 的读者内容是无界那一句**：`AR_SET_KIND` 七个成员的译文**把后果写进词里**——
「向上无界 —— 工具太弱，数据约束不住效应的上限（旁边那个 bootstrap 区间会把这件事
掩盖掉）」「空集 —— 没有哪个取值能同时满足所有工具的矩条件，数据在否定这组工具本身」。
只说几何形状（「向上无界」）等于告诉读者形状而没告诉他结论。#357 里那条
`anderson_rubin_set_kind = no_gloss`（理由正是「没有哪一面渲染这个块」）**已改回
`glossed_by`**，两个面的表逐字节相同并钉在 schema 三个站点的并集上。

**顺手抓到一个我自己写的缺陷**：`??` 链先取同方差 AR 集。prompt 里早写明两者都在时
**稳健版才是该报的那个**（对弱识别与异方差同时有效）——先取同方差版就是把更窄的区间
建立在更强的前提上，正是这一族块存在的目的所要防的方向。两面都改成稳健优先，并配了
专门的钉子。

**声明不做的**：剩下 **12 个仍然 `unrendered`**，每行都写明读者拿不到什么，登记为
**#368**。其中最严重的是 `inference`——**两个读者面与验证器全都不读它，全仓零读者**，
承载的却是「这个区间是哪种区间」。另外门**不查两个面是否对等**（报告有、浏览器没有算
过），逐面对等是 #313/#340/#347 那一族，另立。

**闸口验过（12 个反例逐个构造，全部当场变红）**：schema 新增未表态的复合部件、行指向
schema 没有的部件、删掉一行、一行说两件事、一行什么都不说、渲染器改名不再读那个键、
行点名一个面上不存在的渲染器、`consumed_by` 点名一个并不消费它的模块、
**`unrendered` 声明过期**（让渲染器开始读它）、AR 那行退回只印标识符、稳健优先被换回
同方差优先、以及走不到任何部件的空扫描。

**基线**：4783 → **4849**。

**方法论沉淀（第一五四至一五六条）**：
(154)**一条纪律挂到既有注册表上时，会连它的分母一起继承**——而那个分母往往是为另一个
问题划的。判据仍是「X 是怎么被找到的」，但这一次要多问一句：**这张表当初是按什么划
范围的，和我现在要问的是同一件事吗**。
(155)**「谁读它」的判据必须是「当键读」**——裸词匹配会把写它的人自己的注释与 docstring
算成读者，而那正是被替换掉的那种守卫。
(156)**「没人渲染它」这句声明要反向核实**——它和「某某渲染它」一样是会过期的事实，
且过期的方向恰好是「读者比代码以为的拿得少」。

---

### 归一化是一份「允许两份副本不一样」的清单，而它的内容是倒推来的（2026-08-19，#365）

登记的是「两份 `_half_width` 全角→半角替换表，曾经不相等」，登记给的解法是
**合并成一处共享**。登记自己要求「做之前先量」——量完，前提是假的。

| 面 | 汉字之间全角 `，；：` | 汉字之间半角 `,;:` |
|---|---|---|
| `themis/**.py` 内核 | **361** | **5** |
| `themis/prompts/*.md` | 136 | 4 |
| `tests/**.py` | 19 | 2 |
| `web/static/*.html` | 3 | 0 |
| **前端 `src/**`** | **59** | **58**（散在 **11 个文件**） |

那两张表的 docstring 写着「The web file writes half-width punctuation
throughout — its own convention」。**`verdict.ts` 的中文串里全角 42 : 半角 42**，
整个前端 59 : 58。这条「惯例」是**从这道门恰好比对的那两张表推断出来的**，
而那两张表恰好全是半角。

**根因不是「共享工具缺位」，是一条被推断出来、从未被决定的「允许差异」。**
比较前的 normalize，每一行都在说「这两处可以在这里不一样」；而行的内容是从
「现在恰好已经不一样的地方」倒推的，不是从任何约定推出来的。于是它必然
**比它描述的东西短**（它自己的 docstring 承认「lists get shorter than the thing
they describe」）、必然**被复制**（第二道门遇到同样的差异只能再推断一次）、
必然**漂**（推断的输入不同）。按登记的做法合并成一份共享工具，只消掉复制，
**不消掉允许本身**——那份唯一的表仍然从现状倒推、仍然必然短、仍然让「同一句话
在两个面拼写成两样」合法，而且会把一条假约定升格成全仓唯一的权威说法。

**改法：把「允许」换成「禁止」。**
1. 让浏览器那两张被比对的表与内核**逐字节相同**（含一处括号宽度），删掉两份
   `_half_width`，比较回到 `==` / `in`——**删掉之后门变强**：任何标点差异现在都是红的。
2. 新门 `tests/test_a_sentence_has_one_spelling.py`：`themis/**` 与 `tests/**` 里
   **不写「在分隔中文的半角标点」**。这道禁令让删除成为永久的——否则下次谁在
   `verdict.ts` 敲个半角逗号，等式门变红，阻力最小的修法就是把归一化加回来。
3. 顺着禁令一次改完 **80 处**（前端 src 67、`frontend/index.html` 2、内核 5、
   prompt 4、tests 2）。

**规则的两条判据都是量出来的，不是我挑的**：
- **逗号/分号：后面紧跟汉字即算**，前面是什么无所谓——前一个子句以括号、公式或
  闭合标签结尾时，「两侧都要是汉字」正好放过的就是这些（实测 9 处，全是面向读者的
  中文散文）。**真正的分界是空格**：带空格的 24 处**压倒性地是「英文句子里列中文词」**
  （`sources: NHANES, UK Biobank, 中国 CDC`、`premises (星座, 命理, 风水…)`、
  `Measurement scales: 收缩压, 体重…`）——那里的半角标点是**对的**。
- **冒号不是同一个标记**：它引出值的次数不比分隔子句少，而被引出的那一侧
  常是标识符或章节号，所以冒号只在**两侧都是汉字**时才算。
- 半角 `.` `!` `?` 夹在两个汉字之间**全仓零出现**，写进规则就是立一条关于
  「不存在的东西」的法。**括号交给逐字节等式管**，不进全仓禁令：它确实两宽混用，
  但只在「同一句话有两份副本」处漂过，而那里等式已要求整句相同。

**作用域与代价，明说**：`docs/` 与 `CORE_STATUS.md` 不在门内。它们是**记录**——
喂进去的 eval case、逐字录下来的 LLM 输出、试跑报告、已经作出的决定——记录是
被引用的，不是被重新标点的。这一点在内容上就看得见：`docs/` 里全部半角分隔符
**无一例外落在列表/集合字面量里**，那些逗号是记号自己的分隔符，规则对它们是错的。
**作用域内一个这样的例子都没有**，这正是规则可以零例外成立的原因。
**不开「括号内除外」的口子**——开了就是给规则留一个能把原问题重新开回来的洞。
代价：`CORE_STATUS.md` 里 41 处半角保持原样，且这两处的新内容不受此规则约束。

**门第一次跑，红在自己的 docstring 上**：我用**举例**（把被禁的串抄进散文）解释
规则。这不是麻烦而是提示——把例子换成判据之后，门零豁免地守住了写它的那份文件。

**顺手闭掉的同族一处**：`propose_theta_priors.md` 与 `web/app.py` 都**逐字引用**
披露面板的一句话「这些数字是 AI 估的，请审核」，而**没有任何面渲染这句**
（面板说的是「这个答案里有 AI 假设的部分 —— 请审核后再用」）。同一族：一句话的
副本没人比对。改法也一致——**不同步，删副本**，改成陈述事实。

**登记那句「还有几处测试在自己写这类文本归一化」的答案是：只有这两处，现在零处。**

**闸口验过（10 个反例逐个构造全部变红，另 1 个必须保持绿）**：`.ts` 里放回半角
逗号、**括号后紧跟中文的那种**（放宽后新覆盖的）、`.py` 里同样、两侧汉字的半角
冒号、**新建**一个 `themis/` 下带违例的文件（证明是走目录不是查名单）、`.json`
带违例（不按后缀挑）、把 `SURFACES` 指向不存在的目录（真空守卫）、**当年被
归一化吞掉的那两种差异**（`RISK_PROVENANCE_ZH` 的括号宽度、`REFUSAL_KIND_ZH`
tail 的逗号宽度）、以及一串去掉空格的中文词表；**必须保持绿的那个**是同一串词
带上空格写在英文句子里——同一串词，**有空格绿、无空格红**。

**基线**：4779 → **4783**。

**方法论沉淀（第一五一至一五三条）**：
(151)**比较前的 normalize 是一份「允许两份副本不一样」的清单**——判据：问「这份允许
是谁决定的」。答不上来就是从现状倒推的，那它必然比它描述的东西短、必然被复制、
必然漂，而它声称的那条约定往往是从它恰好看的那几个样本推断出来的。
(152)**消除副本之间的差异，胜过给差异建一份共享的允许清单**——共享只消掉复制，
不消掉允许；而唯一那份还会把一条假约定升格成权威。删掉允许之后，比较变严了。
(153)**一条禁令要能守住写它的那份文件本身**——门在自己的 docstring 上变红，说明
规则是靠举例讲的；换成判据，规则就能零豁免地成立，而这正是「写原则不写示例」在
门禁上的可检验形式。

---

### 一个词能不能被翻译，取决于内核要不要在 Python 里对它分支（2026-08-18，#357）

登记的是三处「封闭词表到达读者时仍是英文原文」。**先量，分母比三大得多**：

| 面 | 词表数 | 有强制分区吗 |
|---|---|---|
| 浏览器 `verdict.ts` | 14 张 | **有**（`VOCABULARIES` / `NOT_VOCABULARIES`，#317） |
| Python 主报告 | 8 张字符串键表 | **没有** |
| 内核 Python 词表 | 25 个 enum，**只有 4 个带 `zh`** | — |
| 结果信封 schema | **58 个 enum 站点** | #362 的门只认账 **20** 个 |

**根因不是那三处忘了翻译，是词表的声明位置有两个而只有一个能挂读者的词。**
一个封闭词表有没有 Python `Enum`，取决于**内核要不要在 Python 里对它分支**——
与「读者会不会看见它」毫无关系。全部 70 个 schema enum 站点里 **42 个没有任何
Python 声明**，只活在 JSON 里，于是 #362 那道从 `enum.Enum` 子类走起的门
**从没问过它们谁读**。两道现有的门各自完备却合不拢：#362 从 Python 侧枚举，
只在 schema 里声明的看不见；#317 从浏览器侧枚举（因为 `verdict.ts` 把表声明成
`const NAME: Record<>`），只在主报告出现的看不见。#362 自己的 docstring 写着
「every closed vocabulary in `themis` appears below exactly once」——**这句是假的，
因为「in themis」被读成了「in Python」，而 schema 同样是内核的声明**。

**改法**：`tests/test_vocabulary_reach.py` 改成**两扇门都走**，一个词表一行，
一行同时回答两件事——谁声明它（Python enum / schema 站点），谁把它变成读者的词。
`glossed_by` 与 `no_gloss` 互斥且必填，`sites` 与 `off_envelope` 互斥且必填；
`no_gloss` 是**断言不是豁免**，必须点名读者拿到的是什么（「印成把手，旁边那句中文
caption 说它是什么」／「只作分支键，谁在分支」）——`numeric_estimate.method` 与
`bounds_result.method` 那次口头的「算配对过」由此变成声明。译源的检查是**逐成员去问**：
表少一个键、或函数回落成 `` `token` ``，都算没翻译。

**第三扇门明写在 docstring 里关不上**：只以译表形式存在的词表（`derivation_glossary`
的规则名）两扇门都走不到，它由渲染它的那一面各自钉住（`test_derivation_glossary.py`
＋浏览器 `ANCHORS`）。说清边界在哪，好过一道声称覆盖了它看不见的东西的门。

**门一开就抓到的（含两处登记里没有的）**：
- `nde_nie.failed_condition`（M1-M4）与 `cde.failed_condition`（C1-C2）——
  主报告 `：M3`、浏览器 `· M3`，**两个面都只印编号**。补 `envelope_glossary`
  两张表（两张，因为两条臂败在不同定理上、标号集不相交），两面各自渲染。
- `framing_note.missing`（9 值）——**登记里没有**。`explainer` 写
  `f"{predicate} 缺 {', '.join(note.missing)}"`，一句中文里直接列字段名；
  **451 条结果带着它，72 份渲染报告里 37 份印了原文**。
- `status`（7 值）——`_STATUS_BADGE` **只有 5 个键**，两个反事实状态走
  `.get(status, status)` 把标识符原样当标题印，**而浏览器 `STATUS_META` 七个全有**。
- `missing_data_recovery.mechanism`——`_MECHANISM_ZH` 3/4，缺 `none`（「没声明任何
  缺失指示变量」，不是更弱的 MNAR 而是这个问题不存在）。
- `InvestigationAction`——`_ACTION_PHRASE` 5/6，缺 `define_variable`：**唯一一条
  不需要任何新数据就能照做的下一步，印给读者的是 `define_variable`**。这条是
  门自己抓的，不在任何登记里。
- `mechanism_audit` 的 summary 把 `form` 裸插进中文句，且 `f"来源：{provenance}"`
  **给一个自带 `zh` 的词表手写了第二份翻译**。改成把估计器自己那句假设摆在 form
  旁边（与台账行同型的把手＋caption），来源问 `ledger.provenance_zh`。

**第三个读者面（LLM）连源都没有，且唯一那句解释是错的**：
`response_rendering.md` 让渲染方「report which condition failed and explain what
that means in plain terms」，却不给任何词表——LLM 只能自己编；而它自己带的唯一一句
gloss 写「usually M4: intermediate confounder」。**实测经典中间混杂器（X→L, L→M,
L→Y）报的是 `M3`**：`M4` 先把 `{L}`——唯一可能挡住 M→Y 后门的调整集——滤掉，剩下
W=∅ 再败在 M3，字段报的是「幸存调整集第一个失败的条件」而不是「障碍的名字」。
改成把六句话写进 prompt、点明这个错位、并由 `NAMED_IN_PROSE` 逐个成员钉住。

**两处不是词表问题、是整句语言**：全量 189 条 gap description 里 **1 条英文**
（`declared_type_data_mismatch`），219 条 alternative_paths 里 **48 条英文，其中
46 条来自 `unmeasured_confounder_risk` 一个 kind**。这不是 #327「拒答消息的语言」
那种待定策略，是**两个 producer 破了另外一百多条都在守的纪律**——都改成中文，
两个通道现在 100% 中文，并加一道逐条扫语料的门（任何 gap 的 description /
if_provided / alternative_paths 不含中日韩字符即红）。

**声明不做的**：`type_reconciliation` 的 `dtype_kind` 与 `verdict` 判为 `no_gloss`
——检查自己的 `detail` 已经把不一致说成中文，这两个是验证器复算用的机器记录；
造两张没人调用的译表比没有更糟。`anderson_rubin_confidence_set` 的 kind 也判
`no_gloss`，理由是**没有哪一面渲染这个块**：`grep anderson_rubin` 在主报告与浏览器
零命中，只有 `response_rendering.md` 认识它——那是缺一整节不是缺一个词，登记为 #366。

**闸口验过（七个反例逐个构造，全部当场变红）**：schema 新增一个未表态的 enum 站点、
Python 新增一个未表态的 enum、schema 站点多出内核不发的值、译表少一个成员、
把反事实徽章删掉、让中介臂重新直接内插编号、让 framing 从句重新列字段名、
以及把那条英文 alternative_path 放回去。

**基线**：4671 → **4779**。

**方法论沉淀（第一四七至一五〇条）**：
(147)**「完备性门禁」要先说清自己是从哪一侧枚举的**——两道各自完备的门可以合不拢，
中间那类东西两侧都看不见。判据：读到「every X appears below exactly once」，
就去问「X 是怎么被找到的」，找法定义的往往是一个比 X 更小的集合。
(148)**能力和需要不相关时，别让能力决定谁得到**——「有没有 Python enum」由内核要不要
分支决定，「要不要读者的词」由读者决定；两件事挂在一起，缺的就正好是那些没人分支
但人人会看见的。
(149)**「没有译源」的理由必须点名读者拿到的是什么**——写「不需要翻译」等于豁免，
写「印成把手，旁边那句中文说它是什么」才是可以被反驳的断言。
(150)**逐条扫产出的语言，比逐个词表检查更早抓到整句写错语言的 producer**——
词表没参与，任何键在词表上的检查都看不见它。

---

### 一个装得下任意一个的槽位只装得下一个（2026-08-18，#358）

`_attach_bounds_result` 是一条 if 链：先 Balke-Pearl，`if bounds is None and
intervention_is_bool` 再 Manski-Tamer，`if bounds is None` 最后 Manski natural。
登记时写的是「IV 与调用方声明的单调性两组假设争一个槽位，赢家由行号决定」，
代码里 5786-5788 的注释也把这件事说出来并指向本条。

**先量，度量把这条的重点挪了位**：语料 96 个可解析程序、69 条 effect 查询，
声明 MTR 的 **0 条**、同时有工具变量与 MTR 的 **0 条**——「IV vs MTR 由行号
决定」是**可构造但零实例**的状态。真正每次都在发生的是另一件事：**36 条带
bounds 的结果里 3 条报 Balke-Pearl，这 3 条的无假设 Manski 地板同样适用、
同样被丢掉——3/3**。链的第 4 步 `if bounds is None` 意味着**只要有更锐的方法
开火，无假设的地板就永远不会与它同现**，而这趟 pass 自己的注释写的正是
「The assumption-free floor, when point identification failed」。

**根因不是「谁排在前面」，是 `bounds_result` 是一个单数槽位而这一层的输出
本来就是一个集合。**三个方法 `estimand` 全是 `arm_probability`——**同一个被
界定的量**，靠的是互不包含的假设集：Manski 无假设、Balke-Pearl 要 IV1/IV2/IV3、
Manski-Tamer 要调用方声明的单调性。本仓已有的排序原则是「**无假设的估计量永远
压过带假设的**」（finding C），但那条管的是**估计量变了**（声明单调性把总体
效应换成了 complier 对比），不是「谁更紧」。这里估计量没变，所以**本仓自己的
规则拒绝在这三者之间排序**；不可比的东西被塞进单数槽位，无论用哪种顺序都是
替读者做一个它没有依据做的选择。零实例的「行号决定」与 3/3 的「地板被吞」
**是同一个病灶的两个面**。

**修法**：`QueryResult.bounds_result: BoundsResult | None` →
**`bounds_results: tuple[BoundsResult, ...]`**（改名成复数，让 495 处引用逐一
被编译器和测试逼着访问，**没有一处能把元组误读成对象**）。producer 收集
**所有适用的**方法而不是取第一个；顺序降级为**呈现顺序**（无假设在前），并在
代码里明说「顺序不再承载语义」——**这正是不该建 precedence 表的理由**：那会
重新暗示一个不存在的排序。schema 的 `bounds_result` 变数组、验证器逐行审计、
数值端逐行求值、主报告与浏览器逐行印出「方法 + 靠的假设 + 区间」。

**不求交（写进数据与两个渲染面）**：两条区间在各自假设下都成立，若两组假设都
真，交集确实含真值——但**它不是二者合取下的锐界**（合取的锐界是响应型多面体
上去掉单调型的另一个 LP，符号端没有闭式），并且一个不带标签的区间会把「各自
靠什么」抹掉。所以报集合，并把这句话印给读者。

**并掉的重复**：kernel 里「按 method 派发到三个逐方法验证器」有两份（`verify`
内联一份、公开入口 `verify_bounds_result` 一份），并成 `_verify_one_bounds_row`，
**唯一真实差异（未实现的方法该沉默还是该报错）作 `strict` 参数**——内联那份
走的是 kernel 产出的东西，公开那份是「请审计这一行」的请求，用沉默回答等于
判它通过。公开入口、MCP 工具、HTTP 端点一并改成复数名。

**度量（修后）**：36 条带 bounds 的结果、39 行；**无假设地板 36/36 在场**
（此前 33/36）；3 条同时带 `manski_natural` 与 `balke_pearl_iv`。

**基线**：4660 → **4671**。

**方法论沉淀（第一四三至一四六条）**：
(143)**先量，度量可以改写这一条的重点**——登记的现象（两组假设抢槽位）零实例，
而同一个病灶的另一面（无假设地板每次都被吞）3/3 全中。不量就会去修那个不发生的。
(144)**排序原则要看它管的是什么变了**——「无假设压过带假设」管的是**估计量变了**，
不是「谁更紧」；估计量相同时它拒绝排序，而拒绝排序的东西不能放进单数槽位。
(145)**字段改语义就连名字一起改**——`bounds_result`→`bounds_results` 让每一处
引用被迫访问；沿用旧名会留下「读起来对、跑起来错」的缝。
(146)**顺序不再承载语义时，不要建 precedence 表**——表会重新暗示一个不存在的
排序；直白的收集加一句「顺序是呈现不是优先级」比表更诚实。

---

### 表能说出谁赢，说不出谁输了（2026-08-18，#364）

`data_gap_report.py` 的 `_classify_unattempted_layer_dispatch_conflict` 靠
「`transport_identification` 与 mediation 视图哪个非空」倒推「跑了 A、跳了 B」，
再发一条 IMPORTANT gap。结果已经构造出来、`structurally_solved` 已经发出去，
**披露是下游读残留物重建的**。而同一条纪律的正面版本就写在 `numeric_estimator.py`
的 `DSEP_REFUSAL_SIGNATURE` 旁边：决定由发现它的地方携带，不在下游靠搜索恢复。

**根因不在那个分类器里，在 `themis/routing.py` 的路由表。**它能表达**谁赢**
（`precedence`，且 `_check` 明确拒绝并列——「并列会退回声明顺序，而 precedence
就是来替掉它的」），也能表达**谁可以把查询交给答另一个问题的人**（`defers_to`）。
但它**表达不了「两条路线的 guard 可以同时为真，而赢家答的是另一个问题」**——
transport 不是「让出」而是「答掉」，`defers_to` 的检查根本不触发，dispatcher 一个
`return` 就走，**mediation 的 guard 真值从来没被计算过**。

**三个可证伪的推论，都成立**：

1. **表达不出来 ⇒ 没人检查 ⇒ 同型实例不止一条。**形状档（precedence 10–50，
   guard 只读 query）有 5 条路线，两两可同时为真的组合**枚举出来是 10 对**，
   而**只有 1 对有披露**。
2. **其中两条的作用域只写在字段的 docstring 里**：`extra_interventions` 写着
   「no mediator / target_population combined with joint」，`mediators` 写着
   「Mutually exclusive with a single `mediator`」——**散文，不是约束**，两种组合
   都构造得出来且静默丢一层。
3. **估计层同一个洞**：`run_cascade` 在 `stops_here` 处 `break`，precedence 更低
   的策略既不在 `considered`（guard 为假）里也不在别处，而 `considered` 的
   docstring 写的是「解释可达性——一个存在的策略为什么没在这条查询上跑」。
   **它现在答不出它自称回答的那个问题。**

**修法**：`Route` 增加 `triggered_by`（这条路线读哪个声明）与 `displaces`
（排在我之下、guard 可与我同真、答的是另一个问题的路线）。`_check` 校验被声明者
存在、排名严格更低、`ends` 必须是两端（**只有一层能求值的 guard 不能被声明为被夺走
的**，否则另一层会在那里抛异常）、双方都说得出 `triggered_by`（说不出就意味着披露里
写不出「删哪个声明」，那条声明就不该能写）。两层共用 `routing.displaced_by(winner,
facts)`——**只求值被声明的那几条 guard**，所以 `StructuralFacts` 那条「答得早的
查询不该为一次调整集搜索付费、更不该被它弄坏」的约束不破。识别层把结果记进
`QueryResult.dispatch`（`DispatchRecord`），估计层记进 `Evaluation.displaced`，
分类器**只读这份记录**。

**不可表达的那一半用闸口补**：形状档的 guard 只读 query，所以**可枚举**。闸口用一个
「除 query 之外任何属性都抛 `AttributeError`」的 facts 桩把路线分成「形状可判定」
与否——**路线自己的 guard 决定它属于哪边，不靠人列名单**——再穷举 2⁵ 个声明组合。
任何一对同时为真而未声明的路线在这道门上失败；同一道门顺便钉死 `triggered_by`
与 guard 一致（只设一个声明时，开火的必须是声明它的那条），并要求每一对声明都有
一句中文说明（**表在 `routing.py`，句子在 `data_gap_report.py`，键集必须相等**——
少一句就是读者拿到一条中间开天窗的 gap）。**闸口验过**：抽掉 `transport.displaces`
两道门都当场变红。

**度量**：可达的 10 对现在全部声明、全部有披露；此前是 **1/10**。新覆盖的其中一对
（`mediators` + `mediator`）是残留物读法**按构造看不见**的——两个字段都是 mediation，
它唯一查的那个 extension 无论如何都非空，于是它推断出「没有冲突」。

**声明的取舍**：`DispatchRecord` **不进 envelope**。读者需要的披露是它产出的那条
gap，那条 gap 用散文点名了两层；把 route id 再放进信封是**同一个事实的第二份记录**
（#345 刚拆掉过一次），而 id 命名的是实现，不是读者读的概念。`Evaluation.displaced`
今天**没有生产消费者**——估计路径先跑识别，`dispatch` 已经在结果上、gap 已经发出；
它存在是因为 `Evaluation` 本身就是「这次评估决定了什么」的可检视记录，而它现在补上的
正是 `considered` 自称回答却答不出的那个问题。

**基线**：4640 → **4660**。

**方法论沉淀（第一三八至一四二条）**：
(138)**能表达「谁赢」不等于能表达「谁输了」**——优先级选出赢家，却不产生「有人被
夺走」这个事实；被夺走的一方连 guard 都没被求值，于是下游只能从残留物反推。
(139)**倒推式披露的覆盖面等于写它的人当时想到的那一对**——它不是漏了别的对，
它按构造看不见别的对。判据：把同型组合枚举一遍，数有披露的比例。
(140)**写在字段 docstring 里的作用域限制是散文**——「本版不支持 A 与 B 同时」
如果只出现在注释里，那个状态仍然构造得出来，而且会静默地只做一半。
(141)**不可表达做不到时，就把「可穷举的那一档」穷举掉**——判断哪些属于这一档不要
列名单：给一个只回答该档问题的桩，让每条路线的 guard 自己分类（够不着的当场抛）。
(142)**一份记录说自己解释某件事，就要能解释它的每一种情形**——`considered` 只装
「guard 为假」，而「排在赢家之下、guard 为真、从未被问」是同一个问题的另一半。

---

### 图撤销的是「丢掉非父节点」的许可，不是分解本身（2026-08-18，#359）

同一张图（Z→X→Y，X↔Y）、同一份 θ——`P(Z)`、`P(X|Z)`、`P(Y|X,Z)` 八个数一个不缺：

- `effect` 查询回来 `data_required: ['P(y, x | z)  # 8 probabilities']`，
  并经渲染层变成给用户看的「计算只需要观察到的 P(y, x | z)」——
  **它把手上已经有的东西列成了「还需要你提供的数据」**。
- 同一张图的反事实单格回来 `parameter:P(x=True) [missing_distribution]`——
  **跟它要一个把手上八个数边缘化一次就能得到的量**。

登记这条时附了一条前置度量：**先量有多少程序真会在 theta 里声明带 z 的联合，
如果没有，这条就该删掉而不是做**。量了：432 个 JSON、252 个程序，`|given|=2`
的概率语句有 54 条（全是后门调整的 `P(Y|X,C)`），**条件集含工具变量的 0 条**；
声明双向边的 24 个、问反事实的 6 个、**两者同时的 0 个**。

**但这个 0 不能按需求侧读。**surface 本身够用（54 条两条件语句已经在仓里），
而系统自己在另一个面上白纸黑字要那八个数。**一个没有消费者的输入不会有实例。**

**根因不是求解器放在哪一层。**`_assignment_probability_key` 用
`graph.predecessors(atom)` 造 key；一旦有双向边碰到 {X,Y} 的祖先集，整条祖先
因子分解**放弃**，退回只造 `|given|≤1` 的局部链式规则。而**排他性约束恰好使 Z
不是 Y 的父节点**——在多面体唯一适用的那张图上，运行时永远不会问出带 z 的那个
key。求解器搬到哪一层都不解决：即使就位，它在那张图上从 theta 拿到的仍然只有
`P(X)`、`P(Y|X)`。

**不可表达版**：链式法则在拓扑序上对任何分布都成立——它是算术，不是因果假设。
图能做的只是**许可丢掉非父节点**。双向边撤销的是这个许可，**不是分解本身**；
撤销一个「可以少写几项」的许可，剩下的是**项更多的同一个分解**。所以条件集从
父集**放宽到拓扑前缀**（`_factorization_conditioning`），θ 端在 bow+IV 图上要的
恰好是 `P(Z)`、`P(X|Z)`、`P(Y|X,Z)`——正是 `data_required` 印的那八个数。

**求解器的家**：LP 内核完全不碰 DataFrame，只吃 `(P, p_z)` 两个数组；它既不属于
θ 引擎也不属于数据引擎，于是搬到 `themis/response_polytope.py`，与 `refusals.py`
/ `risk_provenance.py` 同层，两端都向下 import，**没有箭头反向**。

**跨门不对称当场回来了一次，也当场闭掉。**给单格门接上多面体之后，同一张图、
同一份 θ、同一个 PN：单格门给 `[0.5441, 1.0]`，causation 门 `needs_investigation`
——**正是 #321 刚消掉的那个形状，在另一扇门上重现**，而且是这次改动造成的。
所以两扇门一起接：多面体前的部分（找工具变量、建表、前置条件）抽成
`_instrument_route_from_theta`，之后的部分（跑目标、把拒答变成一句话、
「什么也没排除就别答」）抽成 `_over_the_response_polytope`，**门之间唯一的差异
——问哪几个泛函——作为一个回调传进去**。现在两扇门的 PN 逐位相等。

**规则名不能点着一个定理再挂第二个求解器**：`probabilities_of_causation_tian_pearl`
改名 `causation_probability_bounds`（与 `counterfactual_cell_bounds` 对仗）。
数据端两条规则本来就是中性名，路线由 licence 说；θ 端这一条是唯一点了定理的，
再挂一个多面体求解器就成了假话。17 处引用一次改齐。

**并掉的两处重复**：`_counterfactual_joint_xy` 与 `_causation_observational_joint`
是同一条恢复级联的两份（祖先分解优先、局部链式规则兜底），并成
`_observational_joint_xy`——#321 第 126 条在同一个文件里的第二个实例；工具变量
探测器的**结构半边**（Z→X、无 Z→Y、唯一）抽成 `_instrument_candidates`，两个门
投影，基数问题各问各的权威（一个问声明域，一个问 theta）。

**「什么也没排除」的取舍（当场声明）**：200 个随机响应型模型里，PN 这一格多面体
只在 **37/200** 上排除了任何东西；其余 163 个 identified set 就是 [0,1]。**返回它
会把一条指名补救办法的 gap report 换成一个长得像答案的区间**——这正是这扇门已经
拒绝过一次的交易。判据是**每一个被问的量都是 [0,1]** 才算「什么也没排除」，不是
「有一个是」：工具变量不动处理时 PN/PS 确实退化，而 PNS 仍被联合分布约束，把三个
一起扣下会把已经拿到的那个也扔掉。数据端照旧返回同一个集合：LP 一样、数一样，
差的不是方法而是**每扇门手上还有什么可给**。

**验证器在这扇门上能做数据端做不到的事**：数据端只有生产者那一份表，最强只能查
它内部自洽 + 边缘化对得上；**这扇门有 theta 这个第二来源**，于是逐层重导
`P(X, Y | Z=z)` 与记录的表逐格比对——**分层标签因此变成可审计的**，而不是装饰：
`P(Z)` 对称时把 levels 置换一下，表仍然自洽、边缘化仍然一致，答出来的却是另一个
数。两扇门各七/五个篡改全拒。

**渲染层第五次同型**：推导链那一行按 `rule` 取句子，而**一个 rule 可以有两条
路线**，于是同一句话被印在两个不同的解法上。改法不是把句子写模糊，是**把 licence
印在它旁边**——licence 的 `zh` 本来就是为「两条路径上都为真」写的。主报告与浏览器
各一处。顺带修掉 `kernel._verify_causation_extensions_match` 的 `_num_eq`：两边都
是 `None` 时它返回假，于是**唯一「两个干预风险都没有」的路线会被自己的交叉检查
判为不一致**——#321 在数值那一份里修过同一处，θ 这一份当时还没有会触发它的路线。

**度量**：200 个随机二值 IV 模型，θ 端答出的 37 个**全部**覆盖生成器数出来的真值，
**逐位等于**直接对同样八个数求解的 LP，验证器**全部**接受。

**基线**：4613 → **4640**。

**方法论沉淀（第一三一至一三七条）**：
(131)**「没有实例」要分需求侧和供给侧**——一个没有消费者的输入不会有实例，
此时的 0 是「没人读」而不是「没人写」。判据：系统自己有没有在别处**要**过它。
(132)**一个约束被撤销时，先问撤销的是什么**——图给的是「可以丢掉非父节点」的
许可，双向边撤销它之后剩下的是项更多的同一个分解，不是没有分解。把「许可没了」
读成「方法没了」，代价是一整条路线。
(133)**能力缺口要从输入侧往回找**：先问「求解器拿不拿得到它要的东西」，再问
「求解器在哪一层」。放错层最多是难看，拿不到输入是根本答不出。
(134)**同一个方法在两扇门上可以有不同的终局**——数值一样，差的是每扇门手上还有
什么可给；这不是分歧，分歧是同一个问句得到两个不同的数。
(135)**验证器的强度取决于它有几个来源**：拿到第二来源就要用上，否则记录里那些
「只用来标注」的字段（分层标签、列名、层次序）按构造不可审计。
(136)**给一扇门加路线之后，必须再把同一个问句从每扇门送一遍**——已经消掉的
不对称，会在某扇门拿到新路线的那一刻按构造回来，而且是这次改动造成的。
判据：新路线让某扇门能答的那类图，别的门在同一份输入上还答不答。
(137)**规则名点了定理，就不能再挂第二个求解器**——路线由 licence 说，规则名
要么是中性的，要么就是假话。

---

### 一条识别级联，两个门都是它的投影（2026-08-18，#321）

同一个 PN——`P(Y_{x=0}=0 | X=1, Y=1)`——走 counterfactual 门得到 `[0.1717, 1.0]`
（生成器数出来的真值 0.4516 在内），走 causation 门得到 `REFUSED do_risk_not_identifiable`。
同一张表、同一张图、同一个数。

**根因不是漏了一档，是级联有两份。**`counterfactual_cell.py` 的第一步是一条六档级联
（同世界 → 用户实验 → 后门 → general-ID → 工具变量多面体 → 单调性钉住），`causation.py`
的第一步是同一条级联的**前缀**（用户实验 → 后门），然后 `raise`。加 general-ID 那次和加
多面体那次，都只落在被改的那一份上——而**两份从各自文件内部读都是完整的**，没有任何地方
声明这两处应当是同一条级联。于是「PN 走哪个门」成了答案的一部分。这正是 #363 判据点名的
形状：加一条「两门不一致就报警」只是把它检测出来，**违规的答案照样被构造并发出**。

**不可表达版**：级联只有一份（`binary_do_risk.choose_risk_route`），两个门各自向它投影。
门与门之间唯一的真实差异——**要几个臂**——是参数（单格要一个，PN/PS/PNS 要两个），
不是分支；级联走到头返回 `None` 而不是抛，**终局留给门自己**，因为两个门的终局确实不同
（一个单格还能被声明的单调性直接钉死，三个归因概率不能）。

**PN/PS/PNS 是同一个多面体上的三个目标向量**，而且比登记时以为的更紧：三者选的是**同一个
响应型**——结局跟着处理走的那种单位，`gy = (0↦0, 1↦1)`。这不是事后发现的巧合，这就是
「归因概率」的定义。三者只差**问的是哪个事实人群**：PN 问受了处理且发生了的那批，PS 问
没受处理也没发生的那批，PNS 问全体——所以 PNS 的事实臂是**没有**，而不是设成了什么。
于是目标函数只泛化一次（`_potential_outcome_objective`），反事实单格和三个归因概率都从
它落下来。

**单调性怎么进多面体，是量出来的不是想出来的。**400 个随机二值 IV 模型：单调性把三者
**0/365 收成点**、**365/365 都收窄**（PN 宽度中位数降 0.279），并且 **35/400 直接被表
推翻**。所以「先解无约束、塌成点才报点」会把它买到的全部丢掉，还会丢掉这条路线独有的
反驳信号。折进程序里是唯一不丢信息的读法——代价是：`*_lower/*_upper` 在闭式路线上是
无假设界（单调性买到的点在旁边自己的字段里），在多面体路线上是**已折入声明假设**的区间。
两条路线的假设进的是不同的位置，因为**两条定理给它的位置本来就不同**，这一条写在
`causation.py` 的 scope 里，而不是留给读者自己撞上。

顺带闭掉的：**causation 门同时得到了 general-ID 路线**（front-door 结构上两臂都点识别，
过去也是拒答）；**多面体的三个辅助函数**（两条前置拒答、充分统计量降级成纯 Python）从
两个门各一份并进多面体自己那侧；**渲染层两处**——主报告与浏览器的「这三个数怎么来的」
那一行原来挂在「两个干预风险都在」上，于是**唯一不需要干预风险的那条路线什么都不说**
（#313/#335/#346 同一形状第四次），现在挂在 licence 上，并且标题从 `monotonic` 这个 flag
改成从**回来的东西**读。

**验证器**（独立重算，不 import 生产者）：多面体路线自己写一遍三个目标向量 + 分母，
general-ID 路线**逐臂**重导估计量——三个归因概率吃两个臂，识别了容易的那个再用两次，
形状和诚实答案一模一样。五个篡改都被拒：改 `pn_upper`、改 `p_xyz` 单元、给多面体许可证
旁边伪造干预风险、把工具变量分层次序颠倒、把路线改标成后门。

**基线**：4598 → **4613**。

**方法论沉淀（第一二六至一三〇条）**：
(126)**两处「同一个问题」的级联，判别式是把同一个问句从两个门送进去、比较它选了哪条路线**——
比对例子只覆盖恰好有例子的地方，比对 **licence** 覆盖的是陈述本身。
(127)共享一条级联时，门之间真正的差异要变成**参数**，**终局留给门自己**；把不属于级联的
东西塞进级联，下一次分叉会以「参数」的形式回来。
(128)**一个假设进两个求解器的位置可能不同**（一条是第二条定理，一条是模型的限制），
于是它买到的东西也不同——这时候标题和区间语义**不能从 flag 读，要从回来的东西读**。
(129)表示法的选择要量：不量就会挑一个「看起来更整齐」的读法，而把该说的信息丢掉。
(130)**渲染层把「路线」那一行挂在某个字段在不在，等于假设只有一条路线**——新路线一到
它就静默。判别式：这一行的**条件**，是不是这一行要**说**的那件事。

---

### 一条关于「决定」的警告，仍然是那个决定被做出了（2026-08-12，dsh 借鉴 4，#363/#364）

dsh 拒绝 detect-and-report 只用一句话：**「事后才抓到；一个违规的请求仍然被构造出来
并发出去了。为了接口层面的不可表达性而拒绝。」**拿它扫本仓，判到三处，第三处是判据找出来的、
读一遍找不出来。

**① bounds 槽位由行号决定**（`scheduler.py`，登记为待办）。从图上读出的工具变量，与调用方
用话声明的单调性，是两组不同的假设：区间既不互相包含，「更紧」也判不了，于是**哪条分支先跑
哪条赢**。原来那句注释把问题推给一个待办号——**那不算把问题说出来**。现在它把问题、三条出路
及各自的信封形状后果一并写在原地，还写明**哪一条不是出路**：两个区间靠的是不同假设，求交等于
同时断言两者。

**② dispatch 冲突是从残留物反推的**（`data_gap_report.py:2978`，新登记 #364）。查询同时命名
mediator 与 target_population，dispatcher 跑一层、跳一层；披露来自一个**事后读输出**的分类器
——它看哪个 extension 被填了来倒推跳的是哪一层。**结果早已构造完毕、`structurally_solved`
早已发出。**而同一个仓在隔壁一层已经否掉过这一模一样的动作：d-sep 拒绝的签名由
`InsufficientTheta.gap` 携带，旁边那句注释明说**决定要在发现它的地方做出，而不是在下游靠
搜索文本恢复**。倒推在这里还有第二个代价：分类器只能从「哪个 extension 非空」猜被跳的是谁，
将来某一层若在填了 extension 之后才失败，它会报反。

**③ 跨门不对称**（并入 #321）。两个门各自维护一条终止条件，于是必然分叉，而分叉只在事后可见。
「两门不一致就报警」是 detect-and-report 那一版；**「一条识别级联，两个门都是它的投影」**是另一版。

**三处都没有在本档修**——每一处都会改动信封形状、且各自是一件已登记的活。但**判据现在写在
代码旁边而不是任务列表里**，这正是前两档的教训用在我自己的笔记上：**一个待办号不是 HEAD 处的
读者能跟着走的引用。**

于是散文门禁多了第三个可判定子类。`CORE_STATUS` 每条登记项一条目，所以**一个 id 在它的活落地
之后才解析得了、在它还开着时解析不了——而两者读起来一模一样**。这条检查抓到上面那处推诿、
三个仓里没有记录其编号的 slice 号，以及第四种编号：`boards #11/#1`——板块是有名字的，
而读者要的是名字。

**基线**：4597 → **4598**（+1：第三个可判定子类）。

**方法论沉淀（第一二三至一二五条）**：
(123)**「检测并报告」与「不可表达」的判别式：违规状态被构造出来了吗**。判据：读到一条警告 /
一个 gap / 一次断言，问「它报告的那件事，是在什么之后才知道的」——如果是在结果已经成型之后，
那么修法在构造那一侧，不在报告这一侧。
(124)**从残留物反推「系统做了什么」，是同一个缺陷的另一副面孔**。判据：这个分类器读的是
**输入的形状**还是**输出的痕迹**；读痕迹的，它在重建一个本该被直接告知的决定，而且它必须猜。
(125)**把一个活的设计问题推给待办号，不算把问题说出来**——待办清单不在 HEAD 上。判据：注释
里出现「见 #N」，问「HEAD 处的读者点开什么」；答不上来就把问题连同候选出路写在原地。

---

### 纪律只到达了那个唯一可枚举的面（2026-08-12，dsh 借鉴 1，#362）

一个封闭词表写在一处，然后被**重述**到每个要读它的面：admit 信封的 schema、
LLM 照着答的 prompt、人打开的参考表。`tests/test_web_vocabularies.py` 为浏览器
守住了全部——锚在 kernel 一侧，且强制 `verdict.ts` 里每张表自报是不是词表，所以
第十张表不可能悄悄到来。其余的面靠元测试文件里三十来条 pin，**每一条都是某次漂移
已经发货之后才补的**。

**根因不是「忘了推广」，量了才看清**：浏览器那条能成立，是因为 `verdict.ts` 把表
声明成 `const NAME: Record<...>`——**有一个集合可供 partition**。prompt 是散文，
没有声明单位，形状搬不过去；搬不动的地方就退回「想起一件补一条」。**分界线正好落在
「这个面还能不能被枚举」上。**

**修法是把枚举的一侧翻过来**：25 个封闭词表，每个说出它到达哪些读者。21 个锚在
schema 的 enum 站点上、必须**逐字相等**；4 个写下「为什么没有 schema 说它」。
用**具名站点的相等**而不是「在文件 enum 并集里」，因为 schema 承认而 kernel 从不发出的
取值读起来像「有人处理过这一档」；用**一组站点**而不是一个，因为反事实单格能声明的许可
不等于 causation 块能声明的——对任一个单独判等都会在半个词表没被说出时通过，那正是 #336。

**partition 逼出那 4 个从没表过态的**：3 个是内部的（策略行的估计量、它的角色、
表的哪一端实现它——读者一个也拿不到）；第 4 个走的是信封没有的那条路——`themis.audit`
自己的输出会命名它审的是哪种产物。

**它还照出「手写的义务」值多少**：钉住 `gap_to_action.md` 的那条 pin 手列了 4 个
估计器时段的 gap kind，而那一组有 6 个；**漏掉的两个恰好就是 prompt 里没有的两个**——
因为清单是照着 prompt 已经写了什么抄的。**它拿 prompt 验 prompt。**现在那一组被声明出来：
`ESTIMATOR_TIME_FINDINGS` 与 `GAP_REPORT_ONLY_ASKS` 并列，把
`NOT_MIRRORED_INTO_EXPLANATION` 里两段注释标题变成它们本来就是的集合，再加
`REACHES_EXPLANATION`——**一个给 agent 预筛的面真正需要覆盖的是「所有到达 explanation 的
kind」，mirrored 与否在那里没有区别**；prompt 补上 `overidentification_rejected` 与
`declared_type_data_mismatch` 两行。

**四条 pin 从元测试文件搬过来**，其中一条比原来更宽。留下的那些查的是别的东西：
一个计数、一个针对两个具体 `$defs` 的子集、一个 Python 注册表。

**上一档的散文门禁只到 `.py`**，于是 prompt——**HEAD 处读者的最严格情形，LLM 手上
什么都没有**——和参考表都在它视野外。现在它覆盖包、测试、prompt 与现状文档，
**排除项连同理由写在模块里**而不是隐含在 glob 里：`wall.md` 定义那些序号、
`CORE_STATUS` 与各 charter 是按时间的条目、`l3_simulation` 与试跑报告记录的是某一次运行。
扩了之后它又抓到 prompt 里 16 处序号，和**一整个搬走的目录**——15 处指向
`docs/prompts/`，那个目录早已不存在，其中两处还在告诉读者 web bridge 加载的是哪个文件。
**仓内死路径是第二个可判定子类**，而既有的 markdown 链接 pin 从来看不见它们，因为它只读 `.md`。

**基线**：4572 → **4597**。

**方法论沉淀（第一二〇至一二二条）**：
(120)**一条纪律只覆盖了一个面时，先问「其余的面是不是不可枚举」**，而不是先问「是不是
忘了」。判据：那个被守住的面有没有一个**声明单位**（一张表、一个 enum、一个注册表）；
有而别处没有，说明形状搬不动，要换枚举的方向而不是重复同一招。
(121)**手写的「必须覆盖」清单，通常是照着「已覆盖」抄的**——于是它拿被检查者验被检查者。
判据：这份清单是从哪来的？如果没有一个**独立声明的集合**能生成它，它证明不了任何事。
(122)**注释里的分组标题就是没被声明的集合**。判据：一个集合字面量里出现「// 第一类…
// 第二类…」，问「有没有别处需要单独用其中一类」——需要，就把标题变成声明。

---

### 注释被允许假设读者当时也在场（2026-08-12，dsh 借鉴 3+2，#360/#361）

读到 DeepSeek Harness 的 `dsh-trim-cot-leakage`，它只有一句判据：**HEAD 处一个没有会话
记录、没有 PR 讨论串、没有未提交草稿的读者，能否解析每一处引用、验证每一条断言。**拿
它扫本仓：**465 处 `iter NNN`，61 个文件**。全仓唯一带这些序号的 `wall.md` 只覆盖被引用
的 143 个里的 **59** 个，而一个裸号码本来也不会告诉读者去那儿查。

**根因**——注释总是在一次会话里写的，会话有序号，代码没有。于是「何时/在哪次做的」被
当成了「为什么」的一部分写进去。它在写的当下是真信息，在 HEAD 上是死引用；**从写下它
的那个文件内部看，死引用和活引用长得一模一样**，所以没人回头改。它不是纪律缺失的产物，
是纪律执行的产物——判据缺一条。

**判据的价值在它拒绝定罪的那部分**，所以反向边界与判据并列写出、并由测试钉住：**自带
解析目标的引用留下**（`wall.md iter 150` 留、裸 `iter 150` 不留——号码从来不是问题，缺的
是指针）；**反事实回归钉留下**（「在这里直接读 `state.x` 会让被扩充的原子拿到字面值而不是
绑定引用」是读者能自己构造的危害）；**带出处的度量留下**；**外部文献留下**。

**每一处是改写不是删除**，三种形态各一条规则：时间戳去掉（它对这个读者什么也没说）；
交叉引用留下它命名的缺陷、去掉号码；变更叙事改成它本来在描述的**现在时危害**——后者严格
更有用，「以前用的是 `state.x`」只能被相信，「在这里读 `state.x` 会……」可以被构造。

**两处 docstring 是按会话组织的**，只删号码会把组织留下。缺口报告的清单原本是五节「哪次
加的」，现在是模块真正有的三张表（mirrored / data-need / estimator-runtime）——而那正是
`types.py` 用 import 期穷尽检查声明的东西，于是 docstring 改成指过去，不再当**组织得更差
的第二份**。元测试文件的清单原本按时间排，现在按「什么被钉在什么上」分组，并直说：**它
里面每一条钉子都是缺陷已经发货之后才补的**——这正是它与 `test_web_vocabularies.py` 的差别，
也是下一件要修的（#362）。

**这一遍照出读一遍照不出的东西**：`iter 121` 印在一句**用户可见的中文消息**里，于是
quasi-separation 警告告诉用户这项检查与一次他们无从访问的会话「互补」；
`_try_derive_via_marginalization` 的一条限制声称并行多中介无解并列了两条将来可能的出路，
其中一条 `_try_marginal_independence_lookup` **已实现、且被同一个调用者在几行之上调用**；
一个 helper 的 docstring 仍把已落地的推导写成未来计划。三处都因为**被包装成历史**而活下来
——没有人去历史里找假陈述。

**门禁只守可判定的那一个子类**（无仓内目标的会话序号），并在自己的 docstring 里说明为什么
只守这一个：一条引用能否解析整体上不是正则能回答的问题，装作能回答的闸门会把它抓不到的
一切都合法化。它抓到两样 grep 抓不到的：一处**跨行折断**的引用，和一条只断言号码、不断言
指针的测试。

**被度量定下来的决定，数字现在挨着决定**（#360）。三处：两步反事实路线更弱这件事在
`counterfactual_cell_response_bounds` 里被论证过、度量却只在提交信息里（400 个随机 IV 模型
上 46 vs 133）；「把结局塌缩成查询问的那个取值」不是无损的，这个度量（240 张表里 154 张
对不上、最大差 0.323）在 `_response_types` 的读者到不了的地方；交接不变量按字面讲是错的，
这件事量遍了全量套件（434 次求值、80 次替换、按字面执行会打断 81 条正确路径）却只活在
CORE_STATUS 里。**一个没有度量的被拒备选是一句断言，下一个读者有权重新提出它。**

**基线**：4569 → **4572**（+3：判据的可判定子类、反向边界反例、锚点必须真能解析）。

**方法论沉淀（第一一六至一一九条）**：
(116)**注释里的引用，判据是「HEAD 处能不能解析」而不是「写的时候准不准」**。判据：
把每一处引用当成读者要去查的东西，问「他去哪儿查」；查不到的，要么说出它当时代表的缺陷,
要么补上指针。
(117)**一条判据必须配一张反向边界清单，否则它会漂成「删掉所有像会话号的数字」**——那会
把指针和死引用一起删掉。反向边界要和判据一起被测试钉住，不能只写在散文里。
(118)**变更叙事不是要删，是要翻译成现在时的危害**。判据：读到「以前是 X / 修复前 Y」，问
「它在描述什么危害」——危害可构造，历史只能被相信。
(119)**一份清单如果是按「哪次加的」组织的，删掉号码不算修好**——组织原则本身就是那个
序号。判据：清单的分节标题里有没有时间。

---

### 一致性恒等式把工具变量给的一族分布压成了一个标量（2026-08-12，接上条，#322）

登记说「counterfactual 查询的 `interval_fallback` 声明的是 Tian-Pearl bounds；界的数据端
存在与否需先核实」。核实结果：**数据端存在**（`estimation/counterfactual_cell.py`，后门 /
general ID / 用户实验三条路线 + 单调性钉死），**声明也没说谎**（`_withdraw_interval_offers`
在 tier=none 时把「接受 Tian-Pearl bounds 给区间答案」这句收了回去）。真正的缺口在别处，
而且是一句话能说清的：

**同一个程序、同一份 DataFrame、同一个工具变量，两个门给的东西差一个数量级：**

| 门 | 问的量 | 修前 | 修后 |
|---|---|---|---|
| effect | `P(y=1 \| do(x=false))` | `balke_pearl_iv` **[0.2434, 0.4723]** | 不变 |
| counterfactual | PN `P(Y_{x=0}=0 \| x=1,y=1)` | **拒答** `interventional_risk_not_identifiable` | **[0.1530, 1.0]**（真值 0.4564） |

而 counterfactual 门的拒答理由，正是「`P(Y=1\|do(x=False))` 后门与 general ID 都识别不出来」
——**隔壁门在同一次运行里刚刚把这个量括起来。**

**根因**：单格估计器的路线级联把终止条件写成了「这一臂能不能**点**识别」。更深一层——
`counterfactual_cell_interval` 把干预风险当**一个标量**吃进去，而工具变量给的从来不是标量，
是**一族联合分布**；把那族分布先压成一个边缘泛函的区间、再回代进恒等式，就丢掉了
「同一个分布必须同时产出这两件事」。

**「先压成区间再回代」这条便宜路线被实测排除**（400 个随机二值 IV 模型，直接从响应型分布
采样、无仿真噪声）：

| | 给出非平凡区间 | 平均宽 | 宽度比（两步/直接） |
|---|---|---|---|
| 两步：BP 框住臂 → 恒等式两端点 | **46 / 400** | 0.9575 | 中位 1.000 |
| 直接：单格作为同一多面体上的线性泛函 | **133 / 400** | 0.8906 | 均值 1.248，最大 **12.617** |

两条都覆盖真值 400/400（直接是 sharp，两步是有效外界）。最悬殊的一例：直接给
**[0.9207, 1.0]**（真值 0.9990），两步给 **[0, 1]**——**两步法丢掉三分之二有信息的情形**。
而且**两步并不更省**：两条路要解的是同一个多面体，只有目标向量不同。

**修法**（#320 立的「基数是参数、多面体是方法」，这一条把**目标泛函**也变成参数）：
单格分子 `P(Y_{x'}=y*, X=x[, Y=y])` 是同一族类型分布上的又一个线性泛函——一个 `(fx, gy)` 型
的单位在工具层 z 上取处理 `fx(z)`、显示结局 `gy(fx(z))`、在 `do(x')` 下会显示 `gy(x')`，
而 `P(z)` 能乘进来正是 IV 独立性那一条；分母 `P(X=x[,Y=y])` 被等式约束钉死，**所以仍是纯 LP、
不是分式规划**。级联在「general ID 也失败」之后多一条 IV 路线，新拒答/新许可各一。

**声明的单调性进 LP，不是另开公式**。理由不是省事：单格求解器的 docstring 本来就写着
「单调性是收紧的额外约束，不是回答的前提」，IV 路线若忽略它，就成了**全仓唯一一处静默丢掉
调用方已声明假设**的地方。落地为「总体中没有反向响应型」= 把那些 `gy` 的质量上界设为 0。
实测：PN 自由 [0.1530, 1.0] → 声明 non_decreasing 后 [0.2217, 0.7530]（仍含真值 0.4564，
**没有收紧成点**——Tian-Pearl 的单调点识别要单调性**加**已知干预风险）。

**它换来一个新的反驳通道**：`_sample_bow_iv` 是保秩的（无反向单位），声明 non_increasing
后类型空间被清空 → 拒答 `counterfactual_inputs_infeasible`，并且**说清是假设被推翻、不是工具
被推翻**（先不带限制重解一次，成功才这么说）。台账上这条单调性因此 `testable=True`——
而走「单调性钉死」那条路时它是 `testable=False`（干预风险不可得，数据无从推翻它）。

**`uses_risk` 被当成了另一个问题的答案**。`testable` 原本读的是「有没有用到干预风险」，
在只有恒等式一个求解器的时候两者同义；多面体不消耗任何风险却能推翻假设。加
`RiskProvenance.can_refute_a_premise` 一栏，把两个问题分开写在同一张表上。

**能力扩张顺带照出三处「只有一个求解器时不会错」的句子**（全部改成对路线不作断言的说法）：
1. 主报告「答案」节：「（无单调性假设，故为界而非点）」+「若可假设单调性，该格可**点识别**」
   ——本路线两句都不成立。改成读**许可**说明为什么是界，单调性那句改为「会被收紧——
   在干预风险已知时收紧成一个点」。
2. 推导链词表：「在数据上**解那条一致性恒等式**，求这一格反事实」——本路线根本没走恒等式。
   一条规则背后现在有两个求解器，句子只说规则做什么，路线交给许可。
3. must-disclose 提示：「跨世界的格子还要用到一臂干预风险 P(Y=1\|do X)，它凭什么成立
   （调整集充分 / general ID / 随机实验）也一并被继承……**这些假设都无法从数据本身验证**」
   ——本路线借不到那个数，三项一项不沾；且末句对「工具第一阶段」「可被推翻的单调性」是假的。
   改成**只说不变量**（consistency + composition）+ 指向许可与台账。

**浏览器少了半张表**。`RISK_PROVENANCE_ZH` 只有 4 项，而这个词表有 8 个成员——因为
`test_web_vocabularies` 的锚点指向 **causation 块**的 enum（4 项），而同一个词表还被
counterfactual cell 块携带（7 项）。**#336 说过「域取决于谁写的它」，锚点却挑了其中一个投影**。
改成锚在模块上（与 `refusal_kind` 同理），表补齐 8 项；浏览器的反事实格卡片现在也印出
「这一格怎么来的」+ 工具变量列名。

**验证器**：许可加进 `_RISK_FREE`（本路线不许在旁边报一个风险）；第 1 步按许可选求解器
（恒等式对本路线只会索要那个没人有的风险）；独立誊写**响应型多面体上的单格目标**，
坐标与单调性一律读 `ctx.query`；`_verifier_response_lp` 加 `forbidden`（禁止某个响应型 =
它的质量上界为 0）。**新增两道**：从 `ctx.graph` 重导 Pearl 判据确认那一列真的是工具变量
（且唯一），以及记录的 `P(X,Y|Z)` 必须**边缘化回**信封另一处报的四格联合——伪造区间现在
要连表一起伪造，且两半必须互相自洽。

**其他被当场决定的事**：
- 工具变量检测放在 `binary_do_risk.py`（与 `minimal_backdoor_adjustment` 同族），判据是
  Pearl 2009 §7.4.5 一句话：**把处理的出边剪掉后 Z 与结局 m-分离**——排他性与独立性
  两条常被分开写的条件，是同一个分离的两面。相关性用结构边 Z→X，因为响应函数模型枚举的
  正是这条 z→x 映射。
- **两个合法工具 → 不答**。多个工具携带的信息严格多于任一个，挑一个是在悄悄回答一个更窄的
  问题；返回 None 让调用方看见「做不到什么」。（联合工具是可做的，未做。）
- **上限不静默**：`|Z|` 过多时按 `RESPONSE_MODEL_TOO_LARGE` 拒答并点名那一列，而不是
  悄悄退回更弱的路线——退回会被读成「这已经是最好的了」。
- **θ 端不动**（登记就只说数据端）：响应型多面体在 `estimation/`，而 `runtime` / `output`
  从不 import `estimation`——θ 端要用得先能从 theta 取出 `P(X,Y|Z)`，那是另一件事，登记为 #359。
- **新的跨门不对称，当场声明**：同一个 PN，counterfactual 门现在有答案，`causation` 门仍
  `do_risk_not_identifiable`（两门修前都拒答）。#321 是 causation 门数值端的登记项，这条并进去。

**方法论沉淀（第一一二至一一五条）**：
(112)**级联的终止条件写成「点识别失败」，就等于宣布这个系统不做部分识别**。判据：读到
「identified / not identified」的二分支，问「这里失败之后，系统别处还知道怎么框住它吗」。
(113)**把一族分布压成一个标量再往下传，是最常见的一种「有效但不 sharp」**。判据：一个求解器
的入参是 `float`，而上游能给的是一个集合——此时便宜路线一定存在、一定有效、且一定更宽；
要不要付直接优化的代价，**用「有多少情形因此从有信息变成没信息」来衡量，不是用平均宽度**
（本条中位宽度比 1.000，而有信息的情形数差 2.9 倍）。
(114)**新增一条路线时，先找出所有「只有一条路线时不会错」的句子**。判据：搜断言路线的措辞
（「用……识别」「解那条……」「这些假设都无法……」），它们不是过时，是**当时正确**——
所以不会有人去改。
(115)**一个属性被当成另一个问题的答案用，加成员时才会暴露**。判据：读到
`if x.flag:` 决定的却是别的事（此处 `uses_risk` 决定 `testable`），问「这两个问题是同一个吗，
还是恰好同真」；恰好同真的，加一栏而不是加一个 or。

### 「16」被写死进了模型本身，于是四道闸门问的都是「是不是二值」（2026-08-12，接上条，#320）

登记说「现有 Balke-Pearl bounds 只支持二值处理与结局；非二值时这条退路今天不存在」。
**限制确实还在**（`output/bounds.py:141` 三个布尔与、`bounds_numeric.py:413` 三次
`len(levels) != 2`、`scheduler.py:5767` 两个 `is_bool`、`_detect_iv_candidate_structural`
的 `set(s.domain) == {True, False}`）。**但「退路不存在」是错的**——退路一直有，是
Manski 自然界；真正丢掉的是**工具变量的全部信息**。跑真内核（n=20000，bow-arc 阻断点识别）：

| 案例 | 修前方法 | 宽 | 修后（同一条臂） | 宽 |
|---|---|---|---|---|
| A 全二值 + IV | `balke_pearl_iv`（估计量=**ace**） | — | 16 型 | 0.085 |
| B X 三值 | `manski_natural` | 0.523 | 72 型 | 0.085 |
| C Y 三值 | `manski_natural` | 0.318 | 36 型 | 0.085 |
| D **Z 三值**（X/Y 二值） | `manski_natural` | 0.303 | 32 型 | 0.083 |
| E 全三值 | `manski_natural` | 0.537 | 729 型 | 0.083 |

**登记漏了 D**：它只提「处理与结局」。D 里 X、Y 都是二值，唯一非二值的是**工具**——
响应函数模型对它毫无障碍（X 对 Z 的响应型从 2²=4 变 2³=8，共 32 型），是那句
`set(s.domain) == {True, False}` 单方面把整个工具扔了，宽度差 3.7 倍。

**根因**：`16` 被写死成两张四元组查找表（生产者 `bounds_numeric.py:295-306`，验证器
`bounds_rules.py:544-549` 独立誊写了同样写死的一份）。响应函数模型本来是一句话——
**「X 是 z→x 的映射，Y 是 x→y 的映射」**——类型数 `|X|^{|Z|} · |Y|^{|X|}` 是它的推论。
写死之后基数从模型的**参数**变成了模型的**前提**，于是每个消费端只能各加一道
「是不是二值」，一共四道。**四道不是四个疏漏，是同一句话的四个下游后果**：把类型表变回
「由基数算出来的东西」，三道直接消失，第四道变成算力上限。

**估计量是被推广逼着改的，不是顺手改的**。`ACE = P(Y=1|do(X=1)) − P(Y=1|do(X=0))`
要二值结局才是概率之差、要二值处理才有基准臂——多值处理连基准都没有。而 `EffectQuery`
问的本来就是**单臂** `P(Y=y|do(X=x))`，它在任意基数下都是同一族类型分布上的线性泛函。
所以推广之后三个方法界的是**同一个量**，`estimand` 全线 `arm_probability`；ACE 在有基准臂时
以具名 `contrast` 另发一对端点。

**顺带量到的一半是修复型**：`estimand` 字段**零个读者**。主报告
（`analysis_report.py:428`）打「给出**区间** [lo, hi]（method=...）」，浏览器
`types.ts` 的 `BoundsResult` 接口里根本没有这个字段。而 `output/bounds.py:137` 的
docstring 写着「The renderer surfaces this distinction so the user understands what's
bounded」——**那句话是假的**。二值 + IV 时问的是 `P(y=true|do(x=true))`、给的是 ACE 区间，
两个面都没有一个字说这件事。

**验过的三件事**：
- **平价**：300 张随机二值表，广义 LP 的 ACE 目标 vs 原 16 型 LP，`max |diff| = 0.000e+00`，
  56 次拒答两边完全一致。**推广是严格超集不是替换**。已发表的两个算例（Vitamin A
  −0.1946/0.0054、worked 0.60/1.00）逐位不变，只是搬进了 `contrast`。
- **算力**：类型数 `|X|^{|Z|}·|Y|^{|X|}`；单次求解 16 型 0.004s / 729 型 0.009s / 4096 型
  0.028s / 78125 型 0.538s，200 次 bootstrap 分别 0.4s / 1.7s / 5.7s / **104s**。
  约束矩阵建表可忽略（≤0.036s，且只依赖基数所以缓存），**求解本身是瓶颈**——所以有上限
  `MAX_RESPONSE_TYPES = 10000`。**上限不静默**：落回 Manski 地板时 notes 说明
  「更紧的方法因尺寸被放弃、不是因为没有更紧的」并给出算式（三条测试钉住：超限要说、
  未超限不许说、没有工具时更不许说）。
- **一条捷径被排除**：把 Y 折叠成「是不是查询问的那个取值」（把 `|Y|` 移出指数）
  **不是无损的**——240 张随机表里 154 张对不上，最大差 0.323。`|Y|` 必须留在指数上。

**自己写错并当场改掉的一处**：docstring / schema 里我先写了「差的界严格窄于两个臂端点相减」，
测试当场证伪——8 张表（含两个已发表算例）上**两者完全相等**。改成只声明成立的那一半
（差落在两臂界之差里面），并把「实测在二值 IV 模型上重合」记为观察而不是定理。

**三道闸门自己抓到了三件事**：
1. 全量套件抓到一个真 bug——连续列在数值端呈现为几千个观测水平，`|Y|^{|X|}` 是一个
   Python **连转成十进制字符串都拒绝**的整数（>4300 位）。size law 改成逐步相乘、一过上限就停：
   「超过上限之后，调用方唯一需要的事实就是它超了」。
2. `test_every_registered_species_is_referred_to_by_something[instrument_not_binary]`——
   我删掉了它唯一的抛出点。**它自己的描述就写着它为什么留不住**：「a multi-valued one is a
   larger enumeration」——更大的枚举是拿来枚举的，不是拿来拒答的。连同 schema enum 一起删，
   还能拦住尺寸的是新增的 `response_model_too_large`。
3. mypy 抓到 `Any | None` 喂进按 `str` 索引的翻译表。

**验证器**：独立誊写广义 LP；`sufficient_statistics` 现在必须带三条水平表和两个臂下标——
一张 2×3×2 的表被当成 3×2×2 读会重导出另一个区间、并指控一个诚实的生产者。`contrast`
按**自己的目标函数**重导而不是用臂端点相减。**伪造天花板因此变窄**：换一张表并重解臂之后，
ACE 区间还站在旧表上——新增一条测试钉住这件事，完全自洽的伪造现在要多伪造一对数。
**顺手删掉一处已死分支**：表达式里必须出现 `do(x=` 之后，「必须出现 x」这条检查
再也不可能单独触发。

**两个读者面都说出这个区间是关于什么量的**，浏览器另加两张按 #317 纪律钉住的翻译表
（`bounds_estimand` / `bounds_contrast_kind` 进 `VOCABULARIES` + 测试侧 `ANCHORS`）。

**当场声明的一处后果**：BP 推广后覆盖面大增，于是「布尔处理 + 非布尔结局 + 图上有工具 +
用户显式声明了 MTR」这一类查询，修前走 Manski-Tamer、修后走 Balke-Pearl——赢家由
`if` 链的顺序决定，而两者假设集不同、界也不可直接比较。写进代码注释并登记 **#358**。

**方法论沉淀（第一〇八至一一一条）**：
(108)**一个常量如果是从别的量算出来的，就不该以常量的身份存在**。判据：读到一个魔数，
问「它是不是某几个输入的函数」；是的话，它现在这个写法会逼着每个消费端去检查那几个输入
**取没取到那个特定值**——本条四道闸门全是这么长出来的。
(109)**登记漏掉的那一档，往往是最便宜的那一档**。判据：登记说「A、B 不支持」时，把同族的
**所有**参数列出来（这里是 X、Y、**Z**），漏掉的那个通常没人试过、因而也没人发现它本来就行。
(110)**推广一个方法时先问「原来的估计量在新范围里还有定义吗」**。没有定义就说明它从来就是
特例的产物，而不是方法的目的——这时正确的做法是回去看**调用方问的是什么**，而不是给旧估计量
硬造一个推广。
(111)**能力扩张会连带暴露「这个数是关于什么的」从没被说过**——因为在只有一个估计量的世界里，
不说也不会错。判据：加第二个估计量之前，先查现有的那个有没有读者；`estimand` 零读者而
docstring 声称有读者，是本条的原型。

### 一条「故意只钉一个方向」的检查，另一边是 8 个块、829 份实例（2026-08-12，接上条，#342）

登记说「`extensions` 在 schema 里只命名了 18 个块中的 9 个」。重数：**10 个**（`assumption_ledger`
是 #341 补进去的），缺 **8** 个。先量它们是不是死代码——插桩 `blocks.check_registered` 跑全量：
**829 份实例**（`mechanism_audit` 348 / `ambiguities` 138 / `type_reconciliation` 122 /
`transport_identification` 97 / `joint_identification` 45 / `mediation_joint_decomposition` 36 /
`counterfactual_cell` 29 / `proximal_estimand` 14）。**全都在真产出。**

**那条检查自己说了它为什么只钉一个方向**。`test_the_schema_gives_shapes_only_to_registered_blocks`
的 docstring：「schema **predates this registry** and is where the drift was first measurable, so it
must not name a block the registry does not」——`schema ⊆ registry`。反方向从来没有人问过，而
`registry − schema` 就是这 8 个。

**代价不是「少了 8 条」，是这 8 个块把封闭词表带出内核而域没有任何地方声明**，于是同名字段
在孪生块上有 enum、在这边没有，成员集合各自漂：

| 字段 | 未声明的这边（实测） | 已 enum 的孪生 |
|---|---|---|
| `pattern` | joint：`joint_backdoor`×40 / `joint_general_id`×5 | `identification`：backdoor / front_door / c_factor / instrumental_variable ——**两集不相交** |
| `strategy` | mediation_joint：**全语料只出现过 `nde_nie+cde`（35 次）** | `mediation_decomposition`：nde_nie / cde / none ——**恰恰没有那个值** |
| `interventional_risk_provenance` | counterfactual_cell：多一个 `general_id_plug_in` | `causation` 那份的四个成员里没有它 |

`strategy` 那行最能说明问题：它的**唯一消费者**（`dispatch.py:2774`）写的是
`if decomp.get("strategy") != "nde_nie": blocked(...)`，只读单中介块；joint 块的 strategy **零读者**，
而唯一取值正是那个比较会判假的值。今天不是活 bug，给 joint 接数值端的那天就是。

**知识一直在，只是写在了邻居身上**：`identification` 的 description 里早写着
「`joint_identification.pattern` is a DIFFERENT vocabulary (joint_backdoor / joint_general_id) on a
different block」——写它的人知道，但那句话待在**另一个块**的描述里，而不是待在承载它的块上。

**修法**：①那条 meta 测试补成双向；②8 条 sub-schema，**只对真正封闭的词表出 enum**；③三处分叉
按事实定域且**不合并**；④`ambiguities` 保持开放并写出理由。

**判据写进了测试**：*封闭＝域是一组读者必须能分辨的固定含义；开放-但有限＝一个生产者一个值，
随生产者增长*。按此 `mechanism_audit.form`（14 个观测值）与 `method`（20 个）**不出 enum**——
enum 化会把「加一个估计量」变成校验失败，那是错的约束。

**四处写成 `$ref` 而不是第二份声明**：`extensions.counterfactual_cell` 指向
`numeric_estimate.counterfactual_cell`（生产者把**同一个 dict** 写进两处），joint 中介的两个臂与
`numeric` 指向单中介的那三份（**同一个识别器填、同一个求值器算**）。「第二份声明」正是同一个字段
名在一处有 `general_id_plug_in`、在邻居处没有的成因。

**`ambiguities` 是这道闸门必须继续说「是」的那个反例**：其余 7 个块都收紧了，它不能——它的条目是
从 program 的 side-channel 抄过来的、由调用者或语言模型写的内容，enum 化 `kind` 等于让内核规定
调用者可以报告哪几种歧义。测试直接喂一个内核没听说过的 kind，要求通过。

**验证**：全语料 2181 份块实例逐个对新 schema 验证——**全过**（唯一一处失败是 registry 单测手搓的
空块 `{}`，不是内核产物）。**D1**：退回 schema → **27 红 85 绿**；恢复 → 112 全绿。新增 37 条。
enum 逐个被伪造一次（13 处），因为**没被验证走到的 enum，读起来和正在生效的 enum 一模一样**——
joint 中介两个臂共享形状与生产者却不共享词表（M1-M4 vs C1/C2），`$ref` 指错那一个，语料里的东西
照样全过。

**基线（本条）**：4477 → **4514**。

**明确不做**：不把这些词表提升成 Python 一等对象 + 两面翻译表（#341 对 ledger 做的那一整套）。
schema enum 只挡「值飘出域」，**挡不住「两个面各写一份翻译」**——实测三处正把英文原样印给中文
读者：`mechanism_audit.form` 348 次印在「函数形式（`nonparametric_gformula_plug_in`，系统按样本量
自动选择）」里、`type_reconciliation.declared_scale` 印在「if 'x' really is `binary`, fix the data
column」里、中介的 `failed_condition` 把 `M3` / `C1` 直接给读者。登记为 #357。

**方法论沉淀（第一〇四至一〇七条）**：
(104)**一条「故意只钉一个方向」的检查，它的注释会告诉你另一个方向为什么不必钉——而那句理由通常
只对写它的那天成立**。判据：读到 `assert A <= B` 且注释解释了为什么不写反向，就去数 `B − A` 有几个
元素、它们在真语料上出现多少次。这里理由是「schema 早于 registry」，而差集是 8 个块 / 829 份实例。
(105)**同名字段是不是同一个词表，不能按名字答，要按「读者面对每个成员说的那句话」答**。判据：把两个
面对每个成员输出的字符串列出来——重复的才是同一个词表。`joint_backdoor` 与 `backdoor` 在两个面上
说的是不同的句子，所以是两个词表，**合并才是 bug**。
(106)**封闭 vs 开放-但有限**：域是一组读者必须能分辨的固定含义＝封闭，可以 enum；一个生产者一个值、
随生产者增长＝开放。判据：问「新增一个成员时，是这个词表的含义变了，还是只是多了一个实现」。
(107)**一个字段在全语料上只有一个取值，是「它的域从没被声明」最可靠的指纹**——因为没有人会去检查
一个从没变过的东西。判据：按字段统计值空间基数，基数=1 的逐个问「它的域写在哪里」。本条两个最锋利
的物证都是这么捞出来的：`mediation_joint.strategy` 只有 `nde_nie+cde`、`mechanism_audit.provenance`
348 次全是 `default`。

### 三成信封被告知「还没得出可复核的结论」，而重算它们答案的审计器就注册在表里（2026-08-12，接上条，#315）

登记说「缺失数据恢复路径 4/4 既不写 derivation 也不写 `estimation_context`」。先把它端到端跑出来，
再把同一条判据推到全量语料——**登记说的是一条估计路线，实测的作用域是三成信封**。

**读者收到的**（三种形态，都是端到端真产物，验证段印的是同一句话
「此状态**不携带推导链**（尚未得出可复核的数值 / 结构结论）」）：

```text
① 缺失数据恢复   point 0.3442  CI [0.3297, 0.3604]   status needs_investigation
                 → verify_missing_data_numeric 已注册、适用，正是重算这个数的那一个
② 选择偏倚恢复   point 0.4058                        status numerically_solved
                 → 同样无 derivation，themis.verify 同样抛错，同样一个字没提兄弟审计器
③ 普通 Manski 界 区间 [0.3534, 0.8502]                status needs_investigation
                 → 与两条恢复路线毫无关系，verify_bounds_result 会把两个端点各重算一遍
```

**全量语料**（插桩 `build_analysis_report`，跑整套测试）：**2803 份信封 / 1152 份无 derivation /
其中 878 份（占全部信封 31%）有一个已注册、已适用、专门重算它那个答案的审计器**，而验证段告诉
它们的读者「尚未得出可复核的结论」，并把人指向 `verify_data_gap_report`——那审的是缺口清单，
不是答案。878 份的构成：**860 份是普通区间答案**、10 份选择恢复、**8 份缺失恢复**。剩下 274 份
是真的没得出答案，那句话对它们是对的。**登记点名的那条，是 878 分之 8。**

**根因**：`_render_verification` 只问一个布尔——`derivation` 在不在——再从两句硬编码的话里选一句。
而「谁能独立复核这份结果」在系统里**已经是一等对象**：`themis.audits` 的 `AUDITS` 表，每行带一句
写给「正在决定要不要相信这个答案的人」的 `zh`，`applicable(result)` 就是这份结果的那份名单。报告
没查这张表，于是它说出口的不是「这份结果能被谁复核」，而是「`derivation` 这个字段在不在」。
`audits.py` 自己的 `needs_method` docstring 早就写着「两个恢复估计量有各自的审计器，**正因为它们的
结果不带 derivation**」——系统一直知道这件事，缺的从来不是审计能力，是**报告与那张表之间的线**。
同 #313 / #334 / #340 一族。

**同一处混淆的第二个出口**：MCP `themis_report` 的 `run_verify` 也按 derivation 开闸，于是它对每
一份区间答案一个印章都没盖过。浏览器（`Recheck.tsx` → `/api/audit`）本来就查表，是对的——**三个
读者面里两个手搓了同一个判断**。

**修法（四处，都在根因上）**：
1. `Audit` 增一个**声明**字段 `re_derives_answer`：这一行重算的是不是「这份结果给出的答案本身」。
   8 行 query_result 审计里 4 行是（`verify` / `verify_bounds_result` /
   `verify_selection_recovery_numeric` / `verify_missing_data_numeric`），4 行审的是答案旁边的事实
   （缺口清单 / 假设台账 / 簇声明 / 结局误差分解）。
2. `_render_verification` 改为查表：列出这份结果**实际**能被哪些审计重算（每行原话 + 调用式），
   第一句按「有没有一行覆盖答案」决定，caller 已经跑过就逐行盖印。公开参数
   `verified: bool | None` 一并换成 `audited: list[dict] | None`——那个三态布尔本身就是这处混淆在
   签名里的样子。
3. MCP 改问 `themis.audit`。
4. 状态判据统一：`_withdraw_asks_the_number_answers` 合回 `_finalise_numeric_result`；缺失恢复补
   `estimation_context`（`data_hash` / `sample_size` / `random_state` / `ci_bootstrap`）。它绕开数据
   契约是真的（列里带 NaN，契约不允许），但这四个值它自己全都有，从估计量写而不是从契约写。

**拆出去的那半个动作，理由被兄弟路线证伪**。`_withdraw_asks_the_number_answers` 的 docstring 说
「无 derivation 不能声称 `numerically_solved`，因为 `verify` 拒审」——一半当场就是假的（选择恢复
无 derivation 却声称了），另一半建立在「`verify` 是唯一审计者」上，而这张表说它不是。**结果能声称
什么，取决于它的答案能不能被重导，不取决于由哪个函数重导。** 而「声称」与「撤回被这个数答掉的
缺口」不可分：拆开之后，跳过它的那条路线上这个动作就是**缺席**——一份恢复出来的 ATE 与四条仍在
索要它刚刚估出来的条件概率的阻断级缺口一起发出去。

**明确不做，并说明代价**：**不给两条恢复路线编 derivation 链**。verifier 的 50 条规则里没有一条覆盖
「m-图可恢复性 / 有序分解」或「选择后门判据」。更要紧的是**用现有词表拼一条会比现状坏得多**：缺失
恢复的估计式确实是 `Σ_z P(y|x,z)·P(z)`，用 `backdoor_criterion` + `backdoor_adjustment_formula` +
`numeric_backdoor_estimate` 拼得出来、`verify` 会**通过**——而它一个字都没检查「两个因子各取自己的
完整病例」，那是这个方法的**全部内容**。那等于把「诚实地拒审」换成「对一条从没重导过恢复性的链说
通过」。真链＋新规则登记为 #356（charter 尺寸）。

**D1**：新增 21 条 + 报告 3 条重写 + MCP 1 条。逐文件退回改前：`dispatch.py` → **2 红 19 绿**；
`analysis_report.py` → **10 红 37 绿**；`audits.py` → 整个文件**收集失败**（新字段缺失）；
`mcp/server.py` → **1 红 17 绿**。两条**防修过头的反面钉**：一份真的没得出答案的信封必须仍然说
「没有能重算这个答案本身的复核」；把答案改坏之后**只有**声明了 `re_derives_answer` 的行能变红——
那个字段是这么挣来的，不是从表里读回来的（独立 oracle：`failed ⊆ ANSWER_ROWS`）。

**基线（本条）**：4455 → **4477**。

**方法论沉淀（第一〇一至一〇三条）**：
(101)**一句「能不能被复核」是存在命题，而代码里常被写成某一个具名审计者的状态**。判据：数系统里
这个命题有几个可能的见证者——只有一个时两种写法等价，多于一个时这个写法**已经错了，只是还没被
看见**。找法是把那句话的主语抄下来，问「它的量词是 ∃ 还是那一个」：这里报告问的是「有没有人能
重算这个答案」，代码答的是「`verify` 能不能」，而表里躺着四个见证者。
(102)**给一等的表加字段前，先试着从已有字段推出来；推得出来就不该加，而「推不出来」要靠同族里
的反例证明，不是靠说不出理由**。判据：`re_derives_answer` 看起来像 `needs_field` 的同义词，直到
`verify_outcome_error` ——**也**声明 needs_field、**也**重算一个数、**却不是答案**——把这条路堵死。
与 #337「同族里那个看起来一样但其实正确的兄弟就是判据」同型而反向用：同族兄弟不只用来把病因
收窄，也用来证明**一个区分必须被声明**。
(103)**读到「因为 X 拒绝，所以不能声称」这类推理，先问 X 是不是唯一的那一个**。这类理由通常写于
只有一个 X 的时候，然后在第二个出现时无人回头改。物证是**同型的兄弟路线做了相反的事而没人报错**
——两条路线同族、同样无链、同样有专属审计器，一个 `needs_investigation` 一个 `numerically_solved`。

### 五条 IV 路线里有四条会说「这个样本里没有第一阶段」（2026-08-07，接上条，#355）

登记说 iv.py 有「约 20 处降级性 `return None` 从未插桩」。先量：`coverage` 只盯 iv.py 跑全量
套件——**766 条语句 / 49 条从未执行 / 94%**。逐条对上去：**21 处显式 `return None` 里 15 处
任何测试都没走过**；登记点名的两处宽 `except (LinAlgError, ValueError)`（`estimate_iv_ate`
的 AR 调用、`estimate_iv_overid`）**也都没走过**，另有第三处 `_w_levels` 的 `except TypeError`。

**而活 bug 不在这 49 行里**。它是一条**没被写下来**的分支：`NO_FIRST_STAGE` 这条纪律施行在
5 条 IV 路线中的 4 条上——`_wald_point`、`_stratified_wald_table`、Hansen GMM、过度识别
2SLS 各有一处 raise——**恰识别 2SLS 一处也没有**。

**读者收到的**：图 `w→z, z→x, x→y, w→y, x↔y`（z 是给定 w 的条件工具），数据里 z 与 w 共线。

```text
status  : numerically_solved
point   : 1.4128     真实效应 2.0
CI      : (1.2891, 1.5190)          ← 真值不在里面
method  : iv_2sls
assumptions: iv1_relevance_instrument_affects_treatment, ...
```

那个数**不含工具变量的任何信息**——固定 x、y，把 z 换成 `w` / `2w+5` / `−w` / `7w−1` / `w/3`，
返回值**逐位相同**。最小二乘不会因为第一阶段秩亏而报错，它给最小范数解，于是 θ 变成
(X, Y, W) 的函数，配一个跟 W 上的数据一样窄的区间。弱工具 gap 确实挂了（F = 0.00），但它叫
读者「report the Anderson-Rubin confidence set」——那个集合因 `s_zz ≈ 0` 返回了 `None`，
根本不在信封里。

**失败与问题的严重程度反向**，这是最值得记的一点：把共线放松一点点（相关 0.9998 而非 1.0），
系统**完全正确**——AR 集 = (−∞, +∞)、明说「工具太弱无法约束效应」、并叫读者别用 bootstrap CI。
只有在最退化的那一点上，那条诚实通道整个消失。

**修法**：守卫补在**每个点估计器自己身上**，这正是另外三条路线已有的结构。`_two_sls_point` 按
过度识别路线**已有的同一个统计量** `x'P_Z x`（q=1 时 = s_zx²/s_zz）判退化，理由分两句——
「工具在 W 之下没有剩余变异」与「工具与处理正交」——因为对分析者而言这是两个不同的问题。
`_wald_point` 补上臂计数守卫：它原有的 `abs(denom) < 1e-12` **对 NaN 恒为假**，于是单臂工具正好
从为它而写的守卫下面穿过去，返回 `nan`（这一处**属潜在**：默认 bootstrap 把它转成
`no_usable_resample` 挡住了，只有 `ci_bootstrap=0` 才露出来）。端到端从 `numerically_solved`
变成 `needs_investigation` + 具名 `estimator_failure`。

**新守卫站到了两个出口前面**：`_first_stage_f_stat` 的 `np.var(z) < 1e-12` 与
`anderson_rubin_confidence_set` 的 `s_zz <= 1e-12` 从 `estimate_iv_ate` 不再可达（两者都是公开
函数，直接调用仍可达）——按 #316 的做法写测试说明**还开着哪扇门**，外加一条钉住「估计器在它们
之前就拒了」，否则那两条测试读起来像在覆盖一条调用者还会掉进去的路。

**读出来而不是量出来的三处死代码**（覆盖率只说「没跑过」，说不出「跑不到」）：
`_first_stage_f_stat` 的 `df_resid < 1` 与它上方 30 行的 `n − (2+|W|) < 1` 是**同一个谓词**，
中间 `n` 与 `w_cols` 都没被改过，第二遍永远不会成立；`_solve_robust_ar_set` 的 h 折半回退
（`if ap is None: return None`）要求 det S(t) 在 16 个不同 t 上全为零，而它是次数 ≤ 2q 的多项式、
最多 2q 个根，且 `arv(point)` 已经成功排除了恒奇异；`_w_levels` 的
`except TypeError  # mixed types in one column` 在契约之后不可能发生——每个 model 列非 bool 即
float64，与 #354 同型。

**顺带一句话的修正**：弱工具 gap 在没有 AR 集时的 `alternative_paths` 不再指向一个信封里没有的
块，改成说「这个样本形不成这样的区间」。

**D1**：32 条测试。把 iv.py 退回改前 → **7 红 25 绿**（四个共线形态 + 正交工具 + 单臂 Wald +
「估计器在那两个出口之前就拒了」）；单独把 dispatch 那一句退回 → **1 红**。「弱但真实的工具仍然
出数、且 AR 集是整条实线」那条是**防止守卫过头**的反面钉——不能拿拒答顶掉那个诚实的无界信号。
另有四条
`stratified_anderson_rubin_set` / `robust_anderson_rubin_overid_set` 的「支持时确实出答案」
配对，否则前面那些 `is None` 断言对一个无条件返回 None 的函数照样通过。

**方法论沉淀（第九十八至一百条）**：
(98)**覆盖率能告诉你哪条写下来的分支没跑过，说不出哪条分支根本没写**。后者要按 (56) 的方式
数——「同一条纪律施行在几条同族路线上」。四条路线各有一处 raise、第五条没有，在源码里长得
毫无异样，任何行级或分支级指标都不会亮。
(99)**`return None` 把两件事压成同一个值：「我判断不了」和「我判断了，答案是零」**。判据：读那个
`None` 的**唯一消费者**，看它的注释怎么解释这个 `None`——`_first_stage_f_stat` 的 docstring 写着
downstream 把 None 当作 "could not assess"，而它的四个来源里有一个是「工具方差为零」，那不是
判断不了，那是最确凿的判断。
(100)**一个失败如果与问题的严重程度反向，出错的就不是量的大小，而是某条路径在极端处整个消失**。
判据：把退化参数从小量连续调到 0，看输出是否连续——不连续的那一点就是消失的那条路径。这里
相关 0.9998 时系统说「工具太弱无法约束效应」，相关 1.0 时它给出一个 0.23 宽的区间。

### 同一个函数，一个调用点绕开了契约、另外两个没有（2026-08-07，接上条，#354）

#316 修的是 iv.py 一处「契约拓宽之后 dtype 不再可判定」的判据。#354 是把这个形状**全仓
扫一遍**。登记时我点名的线索（`refusals.py` 的 `CONTINUOUS_ADJUSTMENT` /
`ADJUSTMENT_NOT_DISCRETE` 都说 "too many distinct values"）**是错的**——那两条判的是基数
`k > _MAX_LEVELS` 和取值的整数性 `np.any(levels != np.round(levels))`，本来就不读 dtype。
连着两轮，登记点名的那条都不成立，而两轮都因为**去量**而找到了别的活 bug。

先把契约的出口态钉住：`validate_data` 之后，每个 model 列**只可能是 bool 或 float64**
（整数被 `astype("float64")`，字符串/Categorical 被拒收，bool-like 数值被收成 bool；全仓
无人传 `bool_columns=` / `continuous_columns=`，即 bool ⟺ 取值 ⊆ {0,1}）。据此逐个分类
契约之后运行的 **20 条 dtype 判据**：

```text
问「是不是 bool」                16   ← 契约创造了这个区分而不是抹掉它 → 全部正确
_classify_column（离散 vs 连续）  1   ← 活的错误，3 个调用点错 2 个
dispatch:3438 is_numeric_dtype   1   ← 恒真，第三支死代码
frontdoor 的 docstring           1   ← 行为对，散文列的 dtype 到不了
_viol_lingam 的 select_dtypes    1   ← 契约保留的 bool 被它丢掉 → 沉默
```

**活 bug**：`discovery._classify_column` 用 `is_integer_dtype / is_object_dtype /
is_categorical_dtype` 判「离散」，契约之后这三条**恒为 False**，于是 3–20 个取值的整数码列
一律落到 `continuous`。它有**三个调用点**：`markov_blanket` 传的是**原始数据**、并且注释里
逐字写着这个坑；`_diagnose_data` 与 `column_dtypes` 传的是契约后的数据。

**读者收到的**：5 个取值的整数码列（最普通的问卷/分级数据），`auto` 选了 **LiNGAM**——线性
非高斯**连续** SEM——而同一份结果里两句话互相矛盾：

> `selection_rationale`：**100% of continuous variables** fail a normality test … 所以选 LiNGAM
> `assumption_violations`：data appears **Gaussian** (max |skew| = 0.12 < 0.5); … edge directions
> are essentially **arbitrary**

那份数据里一个连续变量都没有。`column_dtypes` 报 `continuous`，`n_discrete=0`，「no continuous
columns → 该用卡方 CI 检验」那条提示**从不触发**。而 `column_dtypes` 不是内部字段：它进
`extensions.discovery_metadata`，`nl_to_kernel_ast.md` 明令 LLM 见到 `continuous` 就**回头问
用户要不要离散化**——于是系统会问用户，怎么把一个已经只有 5 个级别的列二分。

**根因**：判据读的属性契约已经改写了；而「必须传原始数据」这条要求**写在一个调用点的注释里，
不在函数里**——(44) 每个使用点重写的约定一定会漏一次，这里三个漏了两个。所以修的不是那两个
调用点（那会让这条不成文约定出现在第三、第四个地方），是**把要求消掉**：`_classify_column`
改读契约不会改写的量——取值本身（`≤2` → bool；`≤20` 且**取值皆整数** → discrete；否则
continuous）。三个调用点从此无论拿到哪张表答案都一样，`markov_blanket` 那条 workaround
连同它保护的前提一起删掉。与 #316 同型，也与 `missing_recovery` 已有的写法一致。

顺带的三处，逐条声明而不是默默做：`dispatch` 的 E 值分支把恒真的 `is_numeric_dtype` 与它
守着的死 `else`（注释写着「categorical / object outcomes」——那种列到不了这里）合成二分；
`frontdoor._discrete_levels` 的 docstring 不再列到不了的 dtype；`_viol_lingam` 原本用
`select_dtypes(include=[np.number])` 选列，**bool 不属于 np.number**，于是全 bool 帧返回
`()`——在它最该说话的时候沉默；改成按分类点名，`DomainMismatchError` 的消息也顺带从
`(continuous)` 变成了真话 `(discrete)`。

**D1**：18 条新测试，改前代码上 **7 红 11 绿**，红的正好是分类稳定性（整数码那一档）、分类
取值、auto 路由、理由不谈没有的变量、LiNGAM 两档。绿的 11 条守的是**修法不过头**——bool、
真连续、高基数整数码三档改前改后都不变，外加一条把前提本身钉住（「契约确实把 int64 变成了
float64」，否则整组测试对一个读 dtype 的判据也会通过，什么也没钉）。

**一个免费的物证**：改前的 `is_categorical_dtype` 是 pandas 2.x 的弃用 API，而这个仓库
warning-clean。把既有 discovery 测试跑成 `-W error::DeprecationWarning`，**指向 discovery.py
那一行的失败是 0 条**——也就是说，没有任何既有测试让 `n_unique` 落在 3–20 这条带上。**「最普通
的输入」又一次正好是没被测的那个**（#351 里是 |Z|=2，这里是 5 个级别）。

**方法论沉淀（第九十五至九十七条）**：
(95)**一个私有辅助函数如果对输入的来源有要求，那条要求会写在调用点的注释里而不是函数里——
去数有几个调用点带着它**。带着的那个把坑写得清清楚楚，没带的那两个连问都没问。修法不是补
注释（那是把不成文约定复制到第 4、第 5 个地方），是**把要求消掉**：让判据只读上游不会改写的
量，要求就不存在了。
(96)**弃用 API 是免费的覆盖率插桩**——一条恒假的 `is_categorical_dtype(...)` 分支在
warning-clean 的套件里从没抛过 DeprecationWarning，等于说没有任何测试执行过那一行。判据：
`-W error::DeprecationWarning` 跑一遍，凡是**没有**被点名的弃用调用点就是从没跑过的行。
与 (93) 互补：(93) 问字段基数，这条问「有没有外部信号能证明这行没跑过」。
(97)**同一份结果里两句互相矛盾的话，先找它们共同的上游统计量，别分头修**——「100% 的连续
变量非高斯」与「数据看起来是高斯的」是两个派生面在同一个被污染的分类上各说各话；分头修任何
一句都会把污染留在原地。

### 两个混杂因子是最普通的图，而没有一条测试问过（2026-08-07，接上条，#351）

#348 那个活 bug（有向路径集合被按顺序比，多路径 cause 声明全被拒）藏在一条**「见证有两个
元素时才跑」**的行上。#351 问的是：`themis/verifier/rules.py` 里还有没有同型的。子 agent 在
独立 worktree 上扫，**结论是没有**——这就是结论，不包装成 bug。

**规则级覆盖是错的粒度**，这是本档的主要收获。插桩 `dispatch_rule`，对每个产生端发出的
result 取哈希，**只有交给 `verify` 的 result 逐字节相等时才算 e2e**（手写的、被篡改的按构造
进不来），跑遍 84 个驱动 `themis.verify` 的测试模块：

```text
规则级：验过真实产物 61 / 从未验过 8   ← 那 8 条在 verifier 之外零产生端，是设计事实
行级：  剔除拒绝分支后，148 行实质逻辑只有手写测试走过
基数级：24 个集合型字段在真实产物下到过多元素，其中 0 个是「只有手写测试到过多元素」
```

——#348 当时的**规则级 e2e 覆盖是绿的**。所以要按**字段基数**问：哪些见证集合从来没有装过
一个以上的元素。两个：

- `backdoor_criterion.z` / `backdoor_adjustment_formula.z`——Z 上的链式乘积与嵌套 Σ **只在
  |Z|≥2 时存在**，而**两个混杂因子是最普通的图**。
- `iv_wald_numeric_evaluate.instrument_conditioning`——|W|=1 时链式前缀 `w_pairs[:i]` 恒空、
  笛卡尔积只有一个因子。

端到端第一次问它们（|Z|=1,2,3 与 |W|=1,2）：全部 `verify` 通过，调整后的值与手算一致
（0.16 / 0.28 / 0.52）。**是对的，所以这是回归钉不是修复。**

**钉的正当性是量出来的，而且我自己复验过**：我在**另一条规则**（`backdoor_adjustment_formula`）
上注入 #348 同型缺陷（用倒序的 `z` 重建期望公式），只有新钉在 **n=2 和 n=3** 上变红、**n=1 不红**，
`tests/test_verifier` 其余 **214 条全绿**。没有这个钉，后门调整公式里的同型错误对整个验证器
测试目录不可见。

**一条反例没红，而那是本档最有意思的发现**：把 `product()` 的参数顺序反转——**所有 W 都是布尔
时两个 domain 完全相同，反转产生一模一样的序列**，条件集顺序错配根本观测不到。所以新测试额外
断言了分层坐标宽度（`{1}` → `{2}`），否则那条钉守的量不是作者以为的那个。

**查了但没问题的（阴性同样是结论）**：静态形态扫描先用 `bc8b5fd^` 验召回（确实抓到 5985 行
的原 bug），当前只剩 1 处 `ORDERED_EQ`（IV strata，两侧用同一个 `conditioning` 元组和同一个
`product(theta.domain_of(...))`，顺序按构造一致）、`ONE_SIDED` 0 处、29 处 `SUBSET` 全是数值
比较或合法成员检查；`_formula_shape_equal`（同一字段两种语义，最像的候选）唯一调用点两侧逐行
同构；同族并排（mediation NDE/NIE vs joint、CDE vs CDE_joint、m-separation vs m-connection）
均为忠实推广或有意逐字相同。

两个**登记但不当 bug 报**的观察：`m_separation_witness` 与 `m_connection_witness` 检查完全
相同、规则名断言的命题与实际检查脱钩（产生端总选对名字，故非活 bug）；两个互相独立的条件变量
时产生端请求 `P(W2|W1)` 而语义校验器不允许声明它，查询走 data gap——是产生端保守，但它如实
报缺口、没说假话。

**方法论沉淀（第九十三至九十四条）**：
(93)**覆盖率要按「见证集合到过几个元素」问，不能按规则或按行问**——#348 藏在「集合有两个元素
时才跑」的那一行上，而它的规则级 e2e 覆盖是绿的、行级覆盖也会把那一行算成走过（|集合|=1 时
那行照样执行）。判据：对每个集合型字段，量它在**真实产物**下到过的最大基数；`max == 1` 的字段
就是这一类缺陷的藏身处，**而「最普通的输入」往往正好是 1**（一个混杂、一个条件变量）。
配套：判「是不是真实产物」要按**逐字节哈希**比对产生端发出的对象，按文件名或读测试源码都判不准。
(94)**反例不红时，先查被注入的那个量在这个输入上是否可观测**——把 `product()` 的参数顺序反转，
在**所有取值域相同**（全布尔）时产生完全一样的序列，于是「顺序错配」这个缺陷在该输入上不存在，
不是测试不灵。修法是让输入把那个量**分开**（域宽度 1 vs 2），而不是加断言。

### 契约拓宽之后，dtype 已经不携带那个分叉要问的信息（2026-08-07，接上条，#316）

登记说 `themis/estimation/iv.py` 有「约 8 处可构造但未建的拒答分支」，并点名「非浮点列
超基数上限」那一条。子 agent 在独立 worktree 上做，插桩实测（monkeypatch
`EstimatorFailure.__init__`，按 traceback 最内层 iv.py 帧计数，不改行为）：

```text
抛 EstimatorFailure 的站点      20   ← 不是 14，也不是 8
基线被测试到达                    9
零命中                          11   ← 其中 7 个从公共入口可构造、2 个被契约挡死、
                                       1 个被上游拒答遮蔽、1 个不可达
改完之后                     20/20   全部有测试到达
```

**登记点名的那一条说错了**：字符串列和 `pd.Categorical` 走的是 `DataContractError`
（dtype 不是 bool 也不是数值，直接被契约拒收），整数列被契约**拓宽成 float64**——所以
「非浮点列超基数上限」不是「可构造但没人写测试」，是**从公共入口不可达的死分支**。

**但它错得有价值，因为死的方式带出一个活 bug**。40 个整数码、5000 行的分层列，读者收到：

> conditioning column 'k' **is continuous** (40 distinct values over 5000 rows),
> so its strata would hold **about one observation each**

两半都是假的：它不连续，每格 125 行。这句话进 `stratification_fallback`，经
`_attach_iv_estimand_fallback_warning` 镜像进 `explanation`，到达读者。

**根因**：措辞分叉的判据是 `pd.api.types.is_float_dtype(series)`，而 `validate_data` 已经把
每个 required 列 `astype("float64")`——**dtype 在这一步之后不再携带它要区分的信息**，
float 支承接全部流量、另一支永远不可达。同一段的注释**已经写出正确原则**
（"Cardinality, not dtype, decides whether a column can be cut"，并明写"the contract also
widens integer columns to float"），紧接着的分叉又用了 dtype。

**物证是那条既有测试自己**：`test_too_many_strata_falls_back_naming_the_cap`——名字里就写着
**naming the cap**、用的正是 40 个整数码——断言是 `"distinct values" in fallback`，而**两条
消息都含这个短语**，所以它在「句子里根本没有 cap」的情况下一直是绿的。它的断言就是这个 bug
的书面形式。

**修法**：判据换成这个函数自己关心的、契约之后仍可判定的量——每个 level 平均分到多少行，
与 `2 * _MIN_PER_ARM` 比（一格要同时容纳两个工具臂）。两支同时变可达且都说真话；
`rows_per_level` 进 `details`、句子只说为什么。改后那句是「past the cap of 10 this cut
enumerates; its strata would hold about 125.0 observations each, **so the limit is ours and
not the sample's**」。既有测试的断言加强成 `"past the cap of 10" in ...` 且
`"continuous" not in ...`。

**合并前独立复核过**：我用仓库自己的 fixture、不含 agent 的代码复现了那句话，并核对
`_MIN_PER_ARM = 2` → 阈值 4 行/格、5000/40 = 125 确实该走 cap 支。

范围声明（agent 如实登记，我保留）：量的是拒答通道（`EstimatorFailure` 家族）。iv.py 里
另有约 20 处降级性 `return None` 和 2 处内部不变量 `ValueError` 未插桩；
`estimate_iv_ate:390` 与 `_first_stage_f_stat:765` 的 `except (LinAlgError, ValueError)`
是两处未插桩的宽 except（不吞拒答，因为 `EstimatorFailure` 是 `RuntimeError` 子类）。

两个不可达分支没有硬造拒答，而是把「上游拦住了它」写成测试
（`test_the_two_guards_the_contract_stands_in_front_of`）：公共入口拿 `DataContractError`、
内部函数拿 `INSUFFICIENT_SUPPORT`。`contract.py` 自己写着 "first version — relax later if
real cases need"，那天一到这个测试先红。

**方法论沉淀（第九十一至九十二条）**：
(91)**一个判据在数据流水线的某一步之后就不再可判定了，而它读起来仍然合理**——`dtype` 在
契约拓宽之后不再区分「整数码」与「连续量」，于是一支承接全部流量、另一支成为死代码，
**两支都不报错**。找法：问「这个判据读的那个属性，是谁最后写的」；若答案是上游某个规范化
步骤，这个判据就已经失效了。物证形态很特别：**正确原则往往已经写在紧邻的注释里**
（甚至写明了这个机制），因为写注释的人知道，写下一行的人忘了。
(92)**一条测试的名字说它验的是 A，断言却写的是 A 与 B 共有的那部分——它就永远分不出 A 和 B**。
判据：把断言的字符串拿去和**另一支**的输出比一遍，两边都含就等于什么也没验。这类测试比
没有测试更坏，因为它占着那个名字。

### 一份刚算出数的结果，同时在叫渲染器别报数（2026-08-07，接上条）

登记的 #346 说浏览器不显示 `explanation`（1627 份里 1332 份带它）。先量（(61)），
结论是**登记的说法基本是错的，而底下埋着一个活的假话**。

一次全量语料 **2225 份信封 / 4857 行 ⚠**：

```text
逐字等于某条 gap.description        4569   94.1%   ← 浏览器的 gap 列表本来就在印
估计器自己写、旁边另有一条 gap         40           ← 弱工具 F、Hansen J 等
既不是拷贝、也没有载体               248
```

那 248 里 **246 行是同一句话**：「答案是 `manski_natural` 给出的符号区间，**不是点估计**。
渲染时**必须明示这是 bounds 而非具体数值**。」按有无载体一分桶，界限干净得不像随机：

```text
有载体 911 份：needs_investigation 826
无载体 246 份：numerically_solved 242，且**全部**带 numeric_estimate、answer_tier=point
```

也就是说：结构层先给了符号区间，把「这是界不是点」**同时**写进 gap 和 explanation；
数据到达后估计器算出了**真的点估计**，gap 被正确撤掉了，**那句话没有**。而渲染 prompt
把每一条 ⚠ 行定为 **must-quote**——所以这不是一个躺着没人读的字段，是**一句「别报数」的
指令，和那个数一起发出去**。

**根因**：`explanation` 的 ⚠ 段是 gap 报告的**派生视图**。`postprocess` 的表里白纸黑字
写着 `structural_caveats: reads={data_gap_report}, writes={explanation}`，拓扑排序在识别期
保证了这个顺序；而数据到达后 `dispatch` 在**流水线之外**改了源块。`_set_gaps` 是「gap 列表
变了」的唯一出口，它的 docstring 自己就写着这条纪律、还举了同类事故当例子——

> ``summary`` 和 ``actionable_next_steps`` 派生自 gaps，所以**一个移除 gap 的 pass 在两者
> 都被重新求过之前都没有完成**。

——它列了**两个**派生面。第三个不在里面，因为这个函数的作用域是**报告**，而 `explanation`
是**结果**的字段：作用域划在哪里，决定了哪两个够得着、哪一个看不见。

**为什么是根因不是表象**：在撤 gap 处补一句「顺手也删掉那一行」是打补丁——它只修一个 kind，
而两张表（5 个 numeric-satisfied kind × 18 个必披露 kind）各自会长，交集会变，第三处没人记得同步。
㉚：派生面不会因为源被对账而变对，只会因为被**重新求一遍**而变对。

**改动**：
- 「哪些 kind 的描述会被抄进 explanation」从 `scheduler` 的私有 frozenset 提成 `GapKind`
  旁边的**分区**（`MIRRORED_INTO_EXPLANATION` 18 + `NOT_MIRRORED_INTO_EXPLANATION` 18），
  import 期反问「有没有取值掉出所有行 / 落进两行」。新表与旧名单**逐字相等**，一条测试钉住。
  不镜像的那 18 个分两类，各写清理由：**asks**（gap 报告本来就是装它们的）与
  **估计器现场发现**（也进 explanation，但由发现它的估计器用自己的话写，再抄一遍就说两遍）。
- `_set_gaps` 的作用域从报告提到**结果**，对**三个**派生面负责；撤 gap 时按名字撤掉它
  不再蕴含的那几行，**只撤这些**——估计器自己的 ⚠ 行报告的是它运行时看见的事，识别期报告
  的任何对账都不能让它变假。
- ⚠ 行由 `types.mirrored_caveat_lines` **一处**写出：两个模块派生它、一个模块撤销它，
  三者对齐到那个前缀符号，靠的只能是它只被写一次。

实测 **246 → 0**，而「撤了话也撤了」这一格从 **0 变成 32**——所以这个 0 是「发生了并被处理」，
不是「压根没来」（(71)）。

**#347 的形状也不是登记说的那样**。`outcome_error` / `estimation_context` 不是「两个字段没有
落点」，是**主报告用一个函数说六件事（方法/样本量/调整集/精度/结局测量误差/E-value），浏览器
说了其中三件**——而缺的那两件恰好是**必须一起读**的一对：精度提示说「再加多少样本能把区间
减半」，测量误差那行说「这段宽度里有多少是加样本消不掉的」。只给前一句，读者会去买错东西。
主报告的注释早就写着这一点，也早就把两行印在一起。

顺带两件实测：`numeric_estimate.sample_size` 与 `estimation_context.sample_size` 在
**528 对上零分歧**（(70) 的判据 → 浏览器只印一次）；`precision_budget.hint` 是一句**英文**
机器句子、**只有一个读者**（主报告，裸印给中文读者），而同样三个数在信封里是结构化字段
——浏览器读数字自己造句，不照抄（㉟：另一个面已有的实现是参考不是答案）。

`NOT_YET_SAID_HERE`（「本面欠读者」那张表）**3 → 0**，上限跟着降到 0；`explanation` 进
`CARRIED_BY` 并写上**量出来的数**，替掉原来那句没量过的「覆盖了其中一部分，但没有逐句对账过」
——那句自辩正是 (61) 的物证。

**五条反例，全部见红**（其中一条早在 import 期就抛）：①撤 gap 时不撤 ⚠ 行；②撤过头，
把估计器自己的 ⚠ 行也撤掉；③把一个 kind 从分区里删掉（import 期 `ValueError`）；
③b 把它**搬到另一行**（分区仍合法、内容错）；④把 `outcome_error` 塞回「欠读者」表；
⑤把测量误差那行从浏览器删掉。

**方法论沉淀（第八十八至九十条）**：
(88)**一个字段被登记成「某个面没显示它」时，先量它有多少内容是别处的第二份记录——
「没显示」和「显示了两遍」的修法正好相反**。94% 的重合意味着朴素的补法（给浏览器加一段
散文）会把 gap 列表**再说一遍**，而剩下 5% 里绝大多数是**假的**。判据：把该字段逐行拿去
和它的疑似来源做**逐字**比对，再按有无匹配分桶，看两桶在别的维度上分不分得开——分得开
（这里是 `status`）就说明差异有机制，不是噪声。
(89)**一个函数的作用域决定了它能对齐几个派生面，而「它列了两个」和「一共就两个」在
源码里长得一模一样**——`_set_gaps` 的 docstring 把这条纪律写得很清楚、还举了事故当例子，
它只是把作用域划在了报告上。找法：读那个「唯一出口」的参数表，问「它够不着什么」。
(90)**必须一起读的两句话，守卫要钉的是相邻，不是「两句都在」**——主报告把测量误差印在
精度提示旁边并写明了理由，只断言两者都存在的守卫会放过把它们拆开的改动。

### 十三个 `verify_*` 共用一个前缀和一个参数名，审的却是两种东西（2026-08-06，接上条）

登记的 #350 说上一档新加的 `Recheck` 那条端点路由没有守卫。先量（(61)）——缺口比登记大一个量级：

```text
themis.__all__ 里的公开 verify_* 出口                     13
__init__.py「audit surfaces partition by …」那段散文覆盖    6
MCP server 暴露                                           6（与散文那 6 个只重合 3）
浏览器 Recheck.tsx 用                                      2
benchmarks 的 agent prompt 点名                            2
```

把 13 个逐个打在 `tests/test_e2e` + `test_verifier` + `test_output` 跑出来的 **139** 份
`query_result` 上（不是全量语料，够回答「这个出口对信封是什么反应」）：

```text
verify                        ok  73 | ValueError       66
verify_bounds_result          ok  40 | ValueError       99
verify_markov_blanket         ok   0 | VerificationError 139   ← 每一份
verify_orientation_* ×4       ok   0 | VerificationError 139   ← 每一份
verify_outcome_error          ok 139 | —（语料里 0 份带 outcome_error）
```

**根因**：这 13 个共用一个前缀、一个参数名 `result: dict`、一个模块，**审的却不是同一种东西**——8 个审 `query_result` 信封，5 个审**独立产物**（Markov 毯与 orientation 四阶段），后者的 docstring 各自写着 "**not a query_result envelope**"，产物自带 `kind` 字段。而「这个函数审的是什么」只以散文分散在 13 份 docstring 里，`__init__.py` 那句「按结果携带什么划分」**把它们说成同一族的划分——那句话本身是错的**。

代价有三层，都量到了：①**「不适用」和「没通过」共用一个异常类型**，139/139；②不适用也可能**静默通过**（`verify_outcome_error` 在 0 份带该字段的语料上 139 次报 ok）；③四个消费端各自手写了一个不同的子集。

**第四条物证，是这个仓库自己写下的**。`benchmarks/agent_integration/agent_prompt_v1.md` 的 changelog：

> **Symptom in v0**: 3/3 agents called `themis_verify` on a `needs_investigation`
> result with no derivation, got `ok: false`, wasted a tool call.
> **Root cause**: verify is a conditional rule …, not a procedural step.
> **Fix**: removed from workflow; added to red lines with explicit conditional.

也就是说这条规则**代码里没地方放，于是被写进了 LLM 的红线**——而那条红线只覆盖了 13 个出口里的 1 个。

**为什么是根因不是表象**：登记给的两条解法都是待验证断言（㉛）。第一条（给 TS 加守卫）只钉得住我上一档写的那 2 个；第二条方向对但那张表**缺的那一列不是「端点」而是「这个审计审的是什么产物」**——五个 `verify_orientation_*` 根本不在信封这条轴上，按端点建表会把它们再漏一次（㊴）。而同一个问题的两条产生路给出**两个不重合的答案**（散文 6 vs MCP 6，交集 3），正是 (67) 的判据。

**改动**：`themis/audits.py`——13 个出口各声明一次「审哪种产物、什么条件下适用、它重算的是什么（给读者的一句中文）、要不要源程序」；`Artifact` 的五个非信封取值**逐字就是那些产物自带的 `kind`**；import 期 `bind(__all__)` 反问「有没有公开出口没登记」。`themis.audit(program, obj)` 选出适用的几项、逐项跑、逐项返回，**自己不抛**——于是五个独立产物审计**按声明被排除**而不是靠手写名单，「不适用」与「没通过」由构造分开。四个消费端塌成一个：`__init__` 那段散文换成指针、MCP 加 `themis_audit`、agent prompt 的红线从「什么时候别调」改成「调哪个」、浏览器那条 `routeFor` **整个删掉**（选哪些审计不是浏览器该回答的问题），`/api/audit` 一个薄壳。读者现在看到的是「**4 项独立复核全部通过**」外加每项重算了什么。顺带一个直接的读者收益：
上一档那个按钮只在结果带链或带界时才出现，**而三项审计对每一份信封都适用**——
`needs_investigation` 这类最常见的形态原来一个复核入口都没有，现在有三项。

加一个 MCP 工具立刻被**三处既有的数量钉**接住（`themis/mcp/README.md`、`COVERAGE_MAP.md`、
`scripts/run_014_stabilization_smoke.py` 各写着 14），这是这类钉子该有的样子。

**上一档那条守卫我自己问错了**：「每个端点都有调用方」应当问的是**够不够得着**。`/api/verify` 与 `/api/verify_bounds_result` 现在由 `/api/audit` 覆盖，`app.py` 的 `COVERED_BY` 说出这件事，而覆盖者自己必须被调用，否则覆盖是句空话。

**七条反例，两条第一次是绿的**：②把 `verify_markov_blanket` 改标成审信封的，而断言写的是「被选中那行的 `artifact` 不是 MARKOV_BLANKET」——改完它确实不是了，**断言的量取自被测的那张表**；⑥让 `Recheck` 不再调 `/api/audit`，可路径字面量按分层设计全住在 `api.ts` 里，**「产品里出现了这个字符串」恒真**。

**方法论沉淀（第八十三至八十七条）**：
(83)**同一个前缀 + 同一个参数名 + 同一个模块，是三个很强的「它们是一族」的暗示，而它们审的东西可以根本不同**——判据是问「**不适用的时候它做什么**」，答案不止一种就说明这一族从没被并排列出来过（这里有三种：抛 ValueError、抛 VerificationError、静默返回）。(66) 的姊妹：那里的物证是同义反复的成员，这里是**同一族成员对同一处境给出三种反应**。
(84)**「不适用」和「没通过」共用一个异常类型时，任何按「调用 + 捕获」工作的消费端都分辨不出来**，而这两件事对读者的意思正好相反。找法：把每个出口打在一份典型输入上数异常类型——**139 次全抛的那个，抛的不是「你错了」，是「你找错人了」**。
(85)**一条本该写进代码的规则被写进 LLM prompt 的红线里，就是「代码里没地方放它」的直接物证**——而 prompt 补丁天然只覆盖被观察到的那一个实例（13 分之 1）。找法：读 prompt 的 changelog，凡是「root cause: …；fix: 加一条守则」的条目都该回头问一句「这条规则在代码里的家在哪」。
(86)**断言「这一族不该出现」时，断言的量不能取自被测的那张表**——按分类字段断言，等于让表自证；要按**名字**断言，并把「名字集合与表一致」单列成第二条测试。(78) 的下一格。
(87)**「产品里出现了这个端点的字符串」证明的是有一个 wrapper，不是读者够得着**——分层设计会把所有路径字面量收在一个文件里，于是这个检查恒真。要问「**命名它的那个声明，自己有没有被别处调用**」。(65)「导入了不是用了」的下一格。

### `/` 在两个读者面之间做选择，而没有任何地方说有两个（2026-08-06，接上条）

登记的 #348 说 `themis/web/static/index.html` 是第三个读者面、两条纪律都不覆盖它。先量（(61)）：

```text
文件行数 / 动过它的 commit                       599 行 / 两个（建它那次、给它加 Ask 那次）
它读的信封顶层字段                                8 / 21
它裸印的封闭词表（产品镜像了 12 张）               4：status、gap.kind、gap.severity、
                                                 derivation.steps[].rule
读过它的测试                                      0
两条纪律的锚点                                    web_source.SRC = frontend/src（一个路径常量）
```

#313 #317 #335 #336 #337 #341 #340 —— 七轮「让浏览器说读者的话」，一轮都没轮到它。

**根因**：`app.py` 的 `/` **在两个读者面之间做选择**，而「有两个」这件事没有任何地方说出来。两条纪律各自用一个**路径常量**回答「哪些文件是读者面」，可路径常量回答的是「React app 在哪」。更要命的是**这不是一个 fallback**——fallback 是同一个东西的降级版，这里换上来的是**另一个、更旧的产品**，读者分辨不出自己拿到了哪一个。`scripts/launch_web.py` 知道这件事，它在**控制台**打印 "the page will fall back to the legacy static UI"；浏览器上一个字都没有。

**为什么是根因不是表象**：登记写的解法（把纪律扩到覆盖它）本身是待验证断言（㉛），验下来不成立——那会得到**第三份**词表镜像，而 (62)/㊹ 说过 N 份拷贝就是病本身。而且这条根因预测下一次：`/static` 是 mount 的，任何新放进那个目录的页面会以完全相同的方式掉出去。真正该数的量是**读者面有几个**，而这个数今天是一个 glob 的副产品。

**改动**：让它变成 1。`/` 只服务被纪律管住的那个产品；没有构建时给出的那一页**不含任何信封字段**，因此按构造不是读者面——文件改名 `no_build.html` 让名字承载这个事实，`tests/test_web_one_surface.py` 让它可检查（`static/` 下每个文件命中 0 个顶层字段，而目录成员是**列出来的**不是 glob 的：多一个文件就是多一样读者能打开的东西，该花掉一行）。

**合并之前先数它独有的能力**（(75) 第二次）。这次答案是「会丢」：

```text
app.py 提供的 /api/* 端点                        9
产品调用的                                        7
零调用方的                                        2 —— /api/verify、/api/verify_bounds_result
```

也就是说 Themis 的核心主张——每个答案都能被独立重导——**在产品上一个按钮都没有**，遗留页是它们唯一的浏览器入口。所以先搬后拆：`Recheck.tsx` 的「独立复核这个答案」。**不照抄**：旧页那个 Verify 无条件打 `/api/verify`，对没有推导链的结果一律显示 `verify failed: VerificationError`；新的按结果携带什么选端点（有链走 verify，只有界走 bounds-only，两样都没有就不出按钮）。「每个端点都有调用方」跟着成为一条守卫——那正是这次缺陷的另一半。

**搬的时候撞出一个活的真 bug。** 为验「按结果选端点」这条分支说的是不是真话，把语料上每个结果按同一规则送进对应端点数了一遍，一次拒答：

```text
（修前）chain→verify ok 27 / refused 1；bounds→verify_bounds ok 30 / refused 0
（修后）chain→verify ok 62 / refused 0；bounds→verify_bounds ok 31 / refused 0；无按钮 5
```

那一次是 X→M→Y 且 X→Y、问 `cause X→Y`：内核给 `structurally_solved`，`themis.verify` 拒绝。**`supporting_paths` 是一组路径，序不是它的语义内容，而两侧各自把它固定成了不同的序**——运行时按稳定序排（有一条测试专门要求跨 query kind 同序），验证器从 `nx.all_simple_paths` 的**遍历序**重建再要求逐位相等。于是**任何有不止一条有向路径的 cause 查询都被自己的验证器拒绝**，中介加一条直边是最常见的图形。

物证有三条：①这条规则的孪生 `d_connected_via_open_path` 四十行外带着一段注释，把病因一字不差地写着（"The SET of open paths is the semantic content; its order is not meaningful…"）——**它被修过，这一条被留下了**；②`cause_via_directed_path` 自己的 docstring 两次写着 "set"，实现用的是有序元组，**代码和它自己的说明书早就对不上**；③单元测试把见证和渲染串**从同一个元组按同一个序**造出来，二者按构造不可能不一致（㉟），而 `test_e2e_positive_structural.py` 的模块 docstring 自己写着「没有任何 fixture 带正向 cause 查询」——**那句话就是这个盲区的书面形式**。修法是照孪生改成集合比较；新的 `tests/test_e2e_structural_witnesses.py` 只手写图，结果与推导链都由 `themis.run` 产生，再交给 `themis.verify`。

**代价与没做**：浏览器上不再有「从零粘一段 JSON 就跑」的入口（产品的「改 json」要先有一个程序在手），`/api/verify` 只在结果带链时出按钮。原始信封改成产品底部的一个折页——**它并不了结 #346/#347 欠的那三个字段**，倒出一坨 JSON 不算「说给读者听」，`types.ts` 的三张名单仍然是那笔账的唯一记录。

**方法论沉淀（第七十九至八十二条）**：
(79)**一条纪律的适用范围若只由各处的路径常量各自回答，那个范围就是 glob 的副产品**——探针仍是「谁已经不得不知道」（㉞），答案通常是**做选择的那一处**，而它知道的形式是一句注释。这是 (56) 的下一层：(56) 数「一条纪律施行在几个面上」，这里问的是**分母本身从哪来**。配套判据：一个 if/else 是不是 fallback，要问「两支给出的是不是同一件事的两种成色」——不是的话那是分叉，不是降级。
(80)**消除一个面之前先数它独有的能力**（(75) 第二次，这次答案是「会丢」）。而**搬过去不能照抄**：旧面上的按钮可能一直在做一件对读者没意义的事，照抄就是把它装进产品。
(81)**端点路径互为前缀时，子串判「有没有调用方」会把长的算成短的**——`/api/verify` 因为 `/api/verify_bounds_result` 在场而被判成有人调用，反例第一次是绿的。㊶ 的又一次形态：判「有没有」要**连定界符一起匹配**。
(82)**「一组东西」的序不是语义内容，而两侧各自把它固定成不同的序时，双方都自认为在独立复核**——判据是同一个概念在产生端与验证端各被写成有序结构；**孪生实现里那段解释病因的注释是最强物证**（有一次修 ≠ 修遍了同型，(74) 的另一面），**代码与自己 docstring 的用词不一致**是第二条。

### 一张表的边界是按「拼错会不会静默」划的，而它后来问的是「怎么到达读者」（2026-08-06，接上条）

登记的 #340 说浏览器上没有「推导链」这一节，是 #334 的孪生。先量（(61)）：

```text
frontend/src 全目录出现 "derivation" 的次数            0
types.ts 的 QueryResult 里有没有这个字段                没有
一次全量里带 derivation.steps 的信封                  570 / 1627（10 种 query_kind）
这些链里的步数                                        1499 步，1 至 6 步不等
到达读者的规则种类                                     47 种（词表共 58 条）
success=false 的步                                     0（该分支现在没有产生端）
```

登记里的「63 个规则」不对，`derivation_glossary.SAYS` 是 **58** 条。

**根因**：「这个面渲染了内核要求的什么」在本仓有两张表——`blocks.py` / `RENDERED_BLOCKS` 管 `extensions` 里的**块**，`VOCABULARIES` 管**封闭词表**。`derivation` 两者都不是，它是信封的**顶层字段**。而 `blocks.py` 第一段自己写着为什么把范围划在 `extensions`：

> The typed ones are fields of ``QueryResult`` — declared in one place,
> spelled once, and **a misspelling is an AttributeError**. The rest live
> under ``extensions`` ... and a misspelling there is silence.

那条边界是按「**拼错会不会静默**」划的。这张表后来长出了 `read_as` 和 `carried_by`，问的是「**它怎么到达读者**」——**这个问题对字段和块一模一样地成立**，而边界还停在旧理由上。

**为什么是根因不是表象**，三条独立物证：

1. **同一个机制犯过的前三次，各在 `types.ts` 里留下一句描述它的注释**：「Leaving it out of this type is how the one field that tells a reader whom to argue with ... never left the envelope on this surface」（台账 `provenance`）、「Leaving `kind` out of this type is how 47 refusals ... arrived here as one line」、「Declaring only `value` here is how a bounded counterfactual reached the browser as an empty answer slot」。**三句话在描述同一个机制、都是事后补的、一条检查也没有**，第四次就是 `derivation`。
2. **上一次撞见同型缺陷时修的是实例不是机制**：`_render_route` 自己写着 `formula`「is a field rather than a block, so the binding above — which is what catches a block nobody renders — never looked at it」。㊴ 当时被认出来了，`formula` 被手工补上，**表的范围没动**，于是 `derivation` 从同一个洞掉下去。
3. **分母远大于 1**：

```text
query_result.schema.json 顶层字段                     21
types.ts 的 QueryResult 声明的                        13
其中 src 里没有任何地方读过的                          3（query_id / explanation / investigation_requests）
根本没声明的                                          8
真正到达读者的                                        10 / 21
读过 types.ts 的测试                                   0
```

**改动**

- **把 `carried_by` 那条纪律搬到信封「有类型的那一半」**。`types.ts` 底部三张名单，schema 的每个顶层字段恰好落进一张（或落进接口本身）：
  - `CARRIED_BY`——本面由另一个字段说出它，值是**字段名**（可检查：承载者必须是本面声明**且有人读**的字段，照搬 `Block.carried_by` 对承载者的要求）。三条全是内核缺口报告的输入，读者拿到的是策展版本。
  - `NOT_FOR_A_READER`——没人说，也不该有人说：这四条是给调用方或审计的。
  - `NOT_YET_SAID_HERE`——没人说，而**该有人说**。**带上限，只能缩短**。
  三者分开而不是并成一张，因为只有最后一张说「还欠着」，也只有它该被封顶。文件头那句「Only the fields the UI reads are typed; the rest is passthrough」删掉了——正是那句话让每一次遗漏都长得像一次决定。
- **`derivation` 因此必须被声明并被读**：`verdict.ts` 加 `DERIVATION_SAYS`（58 条，**逐字节镜像**内核的 `derivation_glossary`，测试用 `==` 比）+ `derivationRows()`，进 `VOCABULARIES`；`Verdict.tsx` 在识别公式之后渲染（与主报告同序：路线 → 估计式 → 推导链）。未收录的规则印它自己的 id，与报告同一个兜底。
- **`.ts` 源码解析器提成 `tests/web_source.py`**：现有那份在 `test_web_vocabularies.py` 里，新模块再写一份就是 ㊹ 说的「每个使用点重写一遍的约定」——那份解析器本身就是三个各写一遍的正则合并来的。

**八条反例全红**，其中第七条**第一次是绿的**：我把 `{formula ? (` 改成 `{false ? (`，公式确实不再渲染，但顺序断言读的是源码里 `识别公式` 的位置——**它没动**。改成把两个 JSX 块真的对调才变红。

**没做、已登记**：`NOT_YET_SAID_HERE` 里三条——`explanation`（1332/1627 份信封带它，会说出「这条边是上游 LLM 提出的假设，当前回答相当于复述它」这类话，本面用 ProposedReview 和台账覆盖了一部分但没逐句对账）、`outcome_error`、`estimation_context`。另外查出 `themis/web/static/index.html` 是**第三个读者面**（`frontend/dist` 不存在时 `app.py` 回落到它，而 dist 是 gitignore 的构建产物，新克隆就没有），只有创建它的那两个 commit 动过它，`(62)` 的词表纪律和 `RENDERED_BLOCKS` 都不覆盖它——它把 `step.rule` 直接印成英文 id。

**基线（本条）**：4275 → **4315**。

### 台账列了一条「我们没有假设什么」（2026-08-06，接上条）

登记的 #344 说两个 `no_monotonicity_assumption_free_*` 把「**没有**假设单调性」列成了假设。
先按同一条判据把全量扫一遍（(61)：登记给的是实例不是分母）：

```text
以 no_ / non_ / 未 / 不 开头的 glossary 行     19
其中真的是「关于世界的断言」（无未观测混杂等）  16
不是                                            3
```

**是三条不是两条**——第三条 `cell_determined_by_monotonicity_alone_no_interventional_risk`
（「本格仅由单调性定死，未用到任何干预风险」）是同一物种。而**名字带否定不是信号**：
16 个 `no_*` 全是真假设。

**读者拿到的**（非单调 causation 的报告，同一份里）：

```text
答案节开头   未假设单调性，三者只能给界：
答案节结尾   若可假设单调性（X 从不阻止 Y），三者可点识别。
机制审核行   …点识别需单调性(X 从不阻止 Y)，否则只给无假设界
假设节标题   这个结论依赖 6 条假设：5 条一旦不成立、整条因果结论作废
假设节第 5 条 [作废级] 未假设单调性：只给无假设界，不给点
```

同一件事说了三遍，第四遍是**把它说成一条「不成立就作废」的假设**，并让标题那个数多了 1。

**根因**：台账条目回答「**要让这个答案成立，世界必须是什么样**」，这三条回答的是
「**这次分析没有做什么**」。一个通道两个问题。具体机制是
`if 断言了X: append(真假设) else: append(...)`——else 分支没有假设可声明，
但作者要让读者知道「为什么只有界」，而当时唯一被读者读到的显眼通道就是台账。

**为什么是根因不是表象**：删掉那两个 id 既不解释第三条为什么在，也拦不住第四条。真正缺的
是**这张表的成员资格从没被说出来过**——`Layer` 的成员有这条测试（#341 用它淘汰了
`assumption`），glossary 的行从没被同一条测试筛过。

**改动**：

- glossary 头部把成员资格说一次：**一句为假时答案不变或更好的话，不是这里的成员**；
  并点明名字里的否定不是信号（16 个 `no_*` 都是成员）。
- 两个 `no_monotonicity_*` 的 `else` 分支删掉——**断言得更少就该声明得更少**。
- 第三条**折进它所修饰的那一行**：干预风险不可得时，那条单调性的 claim 自己带上
  「——而干预风险不可得，数据无从推翻它」，`testable` 本来就已经按 `provenance.uses_risk`
  逐分支算出。删之前数过它的内容有几份记录：**四份**
  （`RiskProvenance.PINNED_BY_MONOTONICITY.zh` 一字不差写着同一句 / 被修饰那行的
  `testable` / 它自己的 claim / 这个 id），所以删它零损失。

**守卫**：成员资格本身不可判定，但它有一个**可判定的影子**——同一个查询问两遍，
**断言更少的那次必须歇在更少的条目上**。

```text
                        改前            改后
断言单调性              6 条 / 5 作废   6 条 / 5 作废
不断言                  6 条 / 5 作废   5 条 / 4 作废
弱的那份多出来的        no_monotonicity…（1 条）   无
```

**五条反例全红**，但**第五条一开始是绿的**：「估计器声明了一个 glossary 没有的 id」
这条守卫**早就存在且写得对**，只是它的输入清单 `_BATTERY` 里 10 个族**没有 causation
也没有 counterfactual_cell**——缺陷所在的两个族从来没被它跑过。清单已扩到 14 个族
（两族各两种模式），第五条随即变红。**诚实的分母**：14 仍不是全部数值族。

**基线（本条）**：4251 → **4275**。

### 严重度不是第二件事实，是层的分级（2026-08-06，接上条）

上一条顺手量出的 #345：`layer × severity` 在 3252 条台账条目上一一对应、零例外。
动手前把它当**待验证断言**又量了两个独立来源：

```text
来源                     行 / 处   层→严重度
glossary 的行              146     identification→invalidating 110
                                   functional_form→distorting   29
                                   confidence→confidence_only    7
源码里的结构化 spec 字面量   48     identification→invalidating  48
```

**三个来源，零个反例。**

**根因**：`severity` 的职责是「结论怎么死」，而 `Layer.breaks` 那句话已经把它说完了——
「the number is not the causal effect at all」＝作废级、「the average often survives」
＝扭曲级、「only the interval moves」＝仅影响置信。严重度是那句话的三级分级
（5 层 → 3 级），不是关于这条假设的第二件事实。

**为什么是根因不是表象**：表象修法＝留着 #343 加的那条验证器规则当守卫。但它防的是一件
**本不该可能发生**的事：同一个事实被 199 处各自声明一次，第 200 处写错是必然。

**同一行里的对照列**是这个判据最锋利的地方：`testable` 留下了，因为它在
identification 层内部**有方差**（110 行里 8 行为 True——IV 相关性、Sargan、秩条件、
混淆矩阵可逆），两个同层假设在「读者能不能去查」上真的不同。所以「这张表该不该有这一列」
是**逐列**问的，不是逐表问的，而问法是「它能不能与旁边那列不一致」。

**改动**：

- `Severity` 挪到 `Layer` 之前，`Layer` 每个成员多声明一个字段：自己落在哪一级。
- `ledger.stamp` 从二元组改为**三元组**——**产生端不再有写严重度的机会**，它只说自己是
  哪条通道、这条假设撑住答案的哪一部分。
- glossary 的 `_Entry` 4 元组变 3 元组，146 行逐行断言「去掉的那个值等于层推出的那个」
  之后才删（一行不合就中止，而不是被默默改齐）。
- 10 个估计器文件里 48 个结构化 spec 删掉 `severity` 键；主 orchestrator 4 处常量删掉；
  还有一处 `e["severity"] == "invalidating"` 的裸字符串比较换成词表成员。
- import 期的「有没有取值掉出所有行」多问一句：**没有任何层落进去的那一级是死的**。

**验证器保留 `_SEVERITY_OF_LAYER`**，理由不变——它不 import 产生端，而「产生端现在推得对」
不能替代「从别处来的信封也对」。但头部那句「本模块不审严重度，那是逐 id 的策展判断、不是
能从信封推出的事实」现在是**假的**，已改：能推出的是严重度，**策展的是层**。

**新守卫一上就抓到一处**：`_WHY_THAT_SEVERITY["confidence"]` 与
`Layer.CONFIDENCE.breaks` **一字不差**——那不是独立重申，是逐字抄写，而抄写和重申在源码里
长得一模一样。已用验证器自己的话重写。

**八条反例，全部构造并见红**：层的分级与验证器那份漂开 / `stamp` 自己挑一级 /
某一级没有任何层落进去 / 某个 spec 又写了一次严重度 / 严重度规则缩回一层 /
验证器把产生端的句子抄过去 / 形状守卫钉回已经消失的那对键 / 对照列 `testable` 被同一套
理由抹平。

**一处顺带的教训**：那条按形状找台账条目的守卫，键是「同时带 `layer` 和 `severity` 的
字典字面量」——产生端不再写 severity 的那一刻，它能匹配的对象从 55 个掉到 4 个。
接住它的是守卫自带的 `assert found > 30`：**形状守卫必须自带「我还认得出多少个」的下限**，
否则它的绿色分不清「都合规」和「一个也没找到」。键已改为 `layer` + `claim`。

**修后实测**（全量跑，在唯一出口 `_ledger` 上插桩）：**4318 条**条目经过，五种
`层|严重度` 搭配**恰好是五个层各自的那一级**，**0 个 id 挂在两个严重度下**，两种条目形状
（带 id / 不带 id）**都仍带 severity**——字段没丢，只是没人再写它。这个 4318 与登记里的
3252 不是同一把尺（一份台账先 build 后 augment 时同一条会两次经过这个出口），**不是语料
变大**。

**基线（本条）**：4247 → **4251**。

**声明的取舍**：`severity` **仍然留在信封上**，没有删。它可由 `layer` 推出，但推它需要那张
映射，而信封的读者有浏览器、报告、验证器和外部 LLM 四个——让每个读者各存一份映射，正是
(62) 那一档的病。留在信封上、由**一个出口**算出，两边都占。

### 同一条假设，两个「你能拿它怎么办」（2026-08-06，接上条）

登记的 #343 说 `provenance` 的 7 个取值混了两个问题，而 `inherent` 盖在单调性上是
假话。两句都对，而**证据比登记硬**：

```text
identification × estimator_declared   1443
identification × inherent              700
```

按 id 一并，**3 个 id 同时挂在两个 provenance 下**，其中
`consistency_of_potential_outcomes` 是 `inherent` 191 次、`estimator_declared`
92 次——**同一句话，读者拿到两个不同的答案**，差别只是估计器把它放进了结构化 spec
还是扁平列表。

登记里「来自 `q.monotonic` 或一个检测器」**这半句是错的**：
`_detect_monotonicity_for_query` 的 docstring 自己写着 "resolve MTR declaration"，
它读 `query.assumptions.monotonicity` / `program.extensions['monotonicity']`——
**两条路都是调用方声明**，没有检测器。而 `inherent` 说的是「方法本身要求，不给就
跑不了」：单调性不给照样跑，只是给区间不给点。19 条（13 + 6）。

**根因**：`provenance` 的职责是说**读者能拿这条怎么办**（`answerable`），而它由
**产生端**写；产生端唯一知道的是「我是哪条通道」。于是七个取值实际按通道命名——
`inherent` / `estimator_declared` / `measurement_declared` 三个说的是同一句话
（「找估计器，除非换方法否则推不翻」），而真正的 answerable 是**假设本身的属性**，
从来没有一处说出来过，只能从通道猜，猜错也没人发现。

**为什么是根因不是表象**：表象修法＝给单调性单独加一个 provenance。那解决不了同一个
id 两个来路——那不是某个产生端填错了值，是**这个字段今天根本没有确定的答案**。

**改动**：

- `Provenance` 只回答一个问题，成员按「谁能推翻它、推翻了拿回什么」重划：
  `estimator_declared` / `measurement_declared` 并入 `inherent`（写不出与它不同的
  那句），新增 `caller_asserted`（「你在问题里断言的——撤掉它答案变宽而不是消失」）。
  7 → 6。
- **两条通道都向同一张按 id 的表要 provenance**：`assumption_glossary.answerable`，
  扁平通道和结构化 spec 各调一次。于是「一个 id 一个来路」**由构造成立**，不靠守卫。
  实测修后 **0 个 id 挂在两个 provenance 下**（修前 3 个）。
- `ADMISSIBLE` 的 `identification_spec` / `flat_channel` 两行并成
  `estimator_assumption` 一行——两行只可能靠通道名区分，而通道名正是这张表存在的
  目的所要消灭的东西。5 → 4 行。
- 验证器的「伪造」规则**换了把更强的钥匙**：原来问「provenance 是不是
  `estimator_declared`」，现在问「是不是归给了估计器」。实测**700 条结构化条目
  全都在扁平列表里（0 例外）**，所以换钥匙不是放宽——它现在能看见**伪造的结构化
  条目**，那是旧钥匙按构造问不到的。

**合并挤出一个一直藏着的缺口**：`outcome_error` 的两条前提**不在**
`numeric_estimate.assumptions` 里——验证器**从没读过那个块**，于是两个方向都没查过
（它们有没有进台账、台账上的它们是不是真被声明过）。两条声明通道现在取并集。
不合并就永远看不见：那个名字一直在替它挡着检查。

**一个中文标签的取舍**：`measurement_declared`（「测量模型声明」）这个名字没了，但
它说的事更准了——那两条前提现在是 `caller_asserted`：调用方附上了测量模型，撤掉它
点估计照旧，丢掉的是「噪声让区间宽了多少」这笔账。

**篡改扫描（同一条真台账，25 种改法）**：

```text
                       第一轮改完   补两条检查后
拦住                    21 / 25       25 / 25
```

第一轮剩下的 4 处静默里，**1 处是新洞**：`inherent → caller_asserted` 被放过——那会
对读者说「这条是你断言的，撤掉答案只是变宽」，而它其实是方法必需，**是这个字段唯一
会给出「读者做不到的动作」的方向**。补法不是收紧成员表（每个值都合法），而是
**独立复核**：实测 20/20 条 caller-asserted 单调性在信封里都有自己的记录
（`extensions.causation.monotonic` / `counterfactual_cell.monotonicity` /
`bounds_result.method == manski_tamer_monotonicity`），`outcome_error` 那两条自带
id 名单——所以验证器现在从答案自身重推「调用方到底供了什么」，供不出就拒。

另 3 处是层与层互换，顺手量出**更大的一件事**：`layer × severity` 在 **3252 条条目上
一一对应、零例外**。既有那条严重度规则只写了 identification 一层，于是把一条识别假设
改标成 `functional_form` 会得到一条合法层、合法严重度、合法配对的条目，而它告诉读者
「平均值多半扛得住」——恰好相反。规则推广到五层（层说答案的哪部分不成立，严重度给它
分级，第二个由第一个推出），三处静默归零。**severity 是不是整个可由 layer 推出**
登记为 #345。

**守卫（十二条反例，全部构造并见红）**：通道又自己作答 / 单调性又被说成方法自带 /
按「monotonicity」这个词而不是按假设去认（IV 的一阶单调性会被误判成调用方的）/
伪造的结构化条目 / 第二条声明通道又没人读 / 验证器那份重申漂一格 / schema enum
少一个值 / 浏览器表少一个键 / 主报告又裸印标识符 / 调用方追溯被删掉 / 严重度规则
缩回一层 / 追溯改成来者不拒。

**基线（本条）**：4241 → **4247**。

**声明的取舍**：`estimator_assumption` 一行是 `层 × 来路` 的积，因此它允许
`(functional_form, caller_asserted)` 和 `(confidence, caller_asserted)` 两对——
今天没有任何产生端写它们。这是余量不是洞（调用方传 `model='forest'` 就是在断言形状，
那条线写成 caller_asserted 是对的），而且这两对现在也过不了「调用方到底供了什么」
那道独立复核，所以它不再是这个检查抓不到的东西。

**新登记**：#344 `no_monotonicity_assumption_free_interval` /
`no_monotonicity_assumption_free_bounds_only` 共 19 条，把「**没有**假设单调性」列
成了一条假设——台账的定义是「这个答案建立在什么之上」，而这两条恰恰是它没建立在
什么之上。#345 `severity` 是 `layer` 的第二份记录（3252 条零例外），而 glossary 的
146 行各自独立声明了两个值。

**方法论沉淀**：(67)**「同一个字段在两处取值不同」和「同一个东西被说了两遍」是同一
个探针的两面——按 id 分桶，看有没有哪个 id 收到过两个答案**。域取决于产生端时
（(64)）验的是「这一对合不合法」；而当**同一个东西能走两条产生路**时，更锋利的探针
是让它走两遍再对账：`consistency_of_potential_outcomes` 每个取值单独看都合法、每一对
都合法，只有把两条路的答案摆在一起才看得见它们不一致。
(68)**合并两个同义成员会挤出一个一直藏着的缺口——被挤出来的那个，恰恰是原来靠这个
名字免检的东西**：`measurement_declared` 一并进 `inherent`，验证器立刻对着
`outcome_error` 的两条前提喊「估计器从没声明过」，而真相是**它从来没读过那条通道**。
把名字合掉之前，「这个名字在替谁挡着检查」要先问一遍。
(69)**新加一个取值就是新开一个洞，而该补的洞是它唯一会骗人的那个方向——问「这个值
说错了，读者会去做什么他其实做不到的事」**：`caller_asserted` 的错用会告诉读者「撤掉
它答案只是变宽」，那是这张表上唯一一个**可执行**的假话，所以它是唯一值得独立复核的
归属；而复核的材料要现成（实测 20/20 在信封里都留了记录），**先量再决定要不要建**。

### 一行台账三个封闭词表，两个从没有过表（2026-08-06，接上条）

登记的 #341 说的是「台账的 `layer` 是 6 取值的封闭词表，主报告裸印英文」。三句都对，
但同一个括号里还有第二个：

```text
- **[作废级]** 单调性：X 从不阻止 Y(Y_x ≥ Y_x')，使 PN/PS/PNS 点识别　（assumption／来源 inherent／不可检验）
- **[扭曲级]** Y 的函数形式为 linear（双稳健：结局回归或倾向模型任一设定正确即一致）　（functional_form／来源 default／可检验）
```

中文说完之后的括号里是三个字段，其中 `severity` 上一档刚给了表，`layer`（6 取值）和
`provenance`（7 取值）**两张表都没有**。2101 份真信封里 688 份带台账、**3169 条条目**，
两个字段每条都有。而浏览器**两个都不印**：`layer` 在 `LedgerEntry` 类型里声明了却从没
被读过，`provenance` 连类型里都没有。

**没人拦。** 把一条真台账的 `layer` 改成域里另一个值、改成 `not_a_layer_at_all`、改成
空串，`themis.verify_assumption_ledger` **21 次篡改过了 19 次**；`provenance` **8 次
全过**。被抓的两次抓的是既有的 severity 规则（identification 必须 invalidating），
不是 layer 检查。

**根因**：一条台账条目有五个字段，三个是封闭词表，而**「这条是谁写的、它每个字段的域
是什么」从来没有一个地方说过**。域只以散落的字符串字面量活在 5 个产生端里，于是没有
任何一端知道全集；验证器只能检查它碰巧硬编码了的那一个；两个读者面各自决定要不要印
它、谁也没写下为什么；而**一个成员的名字可以毫无信息量而没人会发现**——`assumption`
用在 19 条上，读者看到的是「这条假设，是一条假设」。

**为什么是根因不是表象**：表象修法是「给 `layer` 加一张中文表」。①那样只碰主报告的
一个字段，同一行紧挨着的 `provenance`（3169 条）碰不到，浏览器那一半也碰不到；
②加翻译表不会让验证器多拦住任何一个错值——实测 19/21 静默；③**这正是 #336 给
`interventional_risk_provenance` 解决过的那个形状**，同一个仓库、第二次。

**改动**：第七张顶层表 `themis/ledger.py`，照 `risk_provenance.py` 的形——

- `Layer` / `Severity` / `Provenance` 三个 `EnvelopeName`，每个取值声明一次：`Layer`
  说 `breaks`（它为假时读者失去什么），`Provenance` 说 `answerable`（读者该找谁），
  外加 `zh`。`assumption_glossary.SEVERITIES` 并进来——**一条条目的三个词表住一处**。
- `ADMISSIBLE` **按产生端分五行**（identification_spec／flat_channel／proposal_edge／
  theta_prior／audited_mechanism），每行是「层×来路」的许可；import 期反问「有没有
  取值掉出所有行」。
- `stamp(producer, layer, provenance)` 单一出口，**两个字段一起盖章**——因为单独看
  每个值都合法，错的是「这一对」。五个产生端各走一次。
- 验证器**独立重申**这五行（不 import，与 `risk_provenance` 同纪律），检查每条的
  `(layer, provenance)` 是不是某个产生端可以写的对。
- `assumption_ledger` 进 schema：三个 enum + `required`（顺带做掉 #342 的实质）。
- 主报告三个字段全翻译；浏览器补两张表、`types.ts` 补 `provenance`、组件渲染两个标签。

**一个成员当场出局**：`assumption` 分不出「答案的哪一部分死掉」——单调性为假 →
PN/PS/PNS 退回区间 → 那是**识别**。3 个产生端站点改掉（测试里没有任何断言依赖它）。
它真正想说的「这是额外声明的、不是方法自带的」属于 `provenance`，而产生端把 provenance
写死成 `inherent`——**那句话对单调性是假的**，登记为 #343。

**一个死取值当场出局**：`m.get("provenance", "estimator_default")` 是 `default` 的第二
种拼法，**从来没被写出来过**（mechanism 的 provenance 实测 305/305 全是 `default`）。
import 期的可达性反问正是为这种东西写的。

**修完之后（同一批篡改，同一条真台账）**：

```text
                  layer 篡改      provenance 篡改      合计
修前   拦住         2 / 21           0 / 8            2 / 29
修后   拦住        18 / 21           6 / 8           24 / 29
```

剩下 5 次静默**都是真合法组合**（结构化 spec 可以重述一条函数形式假设；flat 声明可以
走 estimator 或 measurement 两条通道之一），不是漏。

**守卫（十一条反例，全部构造并见红）**：加第六个 layer 没进任何行 / 加第六个进了行但
schema 没跟 / 验证器那份重申漂了一格 / schema enum 少一个值 / 主报告改回裸印 / 估计器
写域外的 layer / 浏览器少一个键 / 浏览器给同一个值换词 / 组件停掉 layer 渲染 / 组件
停掉 provenance 渲染 / 产生端盖一对没有通道能组装的值。

**反例抓到两件事，一件是我自己的守卫有洞**：新加的「表有没有人读」那条，第一版把
`import { ledgerLayerLabel } from ...` **算成了读**——于是一个停止渲染却保留 import 的
组件能过。草堆里剔掉 import 行之后见红。另一件是我把反例打错了靶（theta prior 那条
产生端根本不在我指的测试模块里，㊶ 第四次）。

**基线（本条）**：4219 → **4241**。

**声明的取舍 / 未做**：①45 处估计器仍写字符串字面量 `"layer": "identification"` 而不
import 常量——不churn 的理由是**运行时闸口更强**：`stamp` 是单一出口，写错的值在第一
次跑到就抛；静态那一半由**按形状**（同时带 `layer` 和 `severity` 的 dict 字面量）扫的
AST 守卫补上，而不能按字段名扫——`severity` 和 `provenance` 在这份信封里各自还是**另
一个不相交词表**的名字（缺口的 severity 是 blocking/important/informational，缺口的
provenance 是一个引用列表），按名字扫会在那些地方全部误报。②「表有没有人读」只证明
**有调用点**，不证明读者的眼睛到得了（㊷）；它能抓的是本档真发生过的那种——表加了、
组件没接。

**新登记**：#343 `provenance` 的 7 个取值混着两个问题（「谁负责这条为真」vs「它从哪条
通道到达台账」），且 `inherent` 盖在单调性上是活假话；#342 改写——实测 `extensions`
只**命名**了 18 个块里的 9 个（不是「有名字但没 properties」），已命名的 9 个全都有
properties，本档补进第 10 个。

**方法论沉淀**：(64)**「域取决于哪个产生端」这件事，拦得住错值的形态是「对」而不是
「成员」**——(58) 说过验成员资格拦不住域内的错值，这一档给出拦得住的：**把两个字段
一起盖章，因为单独看每个值都合法，是这一对错了**（2/29 → 24/29，剩下 5 次静默的都是
真合法组合）。(65)**「导入了」不是「用了」——查「有没有人读」的探针必须把 import 行
从草堆里剔掉**，否则一个停止渲染却保留 import 的组件会通过；这是 ㊷「渲染了≠到达
读者」再往前一格：连「有调用点」都还没保证。(66)**一个封闭集合里出现同义反复的成员，
是这张表从没被并排列出来过的直接物证**——判据是给每个成员写一句「它为假时读者失去
什么」，写不出**与其他成员不同**的那一句，它就不是这个划分的成员；而它真正想说的往往
属于**另一个字段**。

### 八张翻译表，三张被钉住，没被钉的五张里两张已经漂了（2026-08-06，接上条）

登记的 #317 说的是「`Verdict.tsx` 把英文 `failure_type` 印给用户」。挂在两个单一
出口上收下 **2101 份真信封**，按同一条判据（**一个值被浏览器印给读者，取自内核
声明的封闭词表，路上没有查表**）扫一遍，结果不是一处：

| 词表 | 信封数 | 读者看到 |
| --- | --- | --- |
| 拒答的 `kind` | 47 | **`types.ts` 里都没声明**——五种「怎么办」塌成一句 |
| 拒答的 `failure_type` | 47 | `overlap_insufficient` |
| 台账的 `severity` | **688** | `invalidating` |
| `status`（**表已漂**） | 6 | 裸 `outside_language` |
| `gap.kind`（**表已漂**） | 57（93 处） | `missing structural input` |

**最锋利的那半是 `kind`。** 它按 `failure_type` 纯函数由 `refusals.stamp` 盖在
信封上，47 份全带；主报告据它对这 47 份分别说五句**不同的话**——

```text
data 17 / unbuilt 13 / request 8 / graph 7 / backend 2
```

「这批数据支撑不住」／「Themis 还没有建这个情形」／「**需要你改一处输入，改掉之后
重跑即可**」／「这是关于因果图的结论，再多同样的数据也不会改变它」／「数值例程没有
返回结果」。浏览器对这 47 份说的是同一句：`拒绝 · <英文 id>`。**拒答唯一对读者有用
的那半——现在该干什么——一次都没过界。**

**根因**：不是「少了一张表」。浏览器是第二个面向读者的面，它本来就有 8 张翻译表；
问题是**「我陈述了内核的哪些词表、我的镜像是否还等于内核的」这件事没有任何地方
写下来**。实测 8 张里只有 3 张被测试钉住（`QUESTION_READINGS` /
`RISK_PROVENANCE_ZH` / `RENDERED_BLOCKS`，而且各自在各自的测试文件里手写了一份
`.ts` 正则），另外 5 张可以静默漂移——**而且已经漂了两张**：`STATUS_LABEL` 里有一个
内核从不发的 `unidentifiable`、缺一个内核会发的 `outside_language`；`GAP_TITLE`
把 36 个 gap kind 写了 28 个。

**为什么是根因不是表象**：表象修法是「给 `failure_type` 加一张表」。判据三条——
①那样只修 47 份里的一个字段，另外三处（688 + 57 + 6）一处也碰不到；②两张已漂的表
说明这不是「有人忘了写」而是**没有任何东西在数「几张表被钉住了」**，而「有一条纪律」
和「都施行了」在源码里长得一模一样（(56)）；③**这正是 `RENDERED_BLOCKS` 在 #335
给「块」解决过的那个问题**，同一个面、同一种缺口、第二次。

**物证**：`SEVERITY_LABEL` 只有 `blocking/important/informational` 三个键——而
「severity」这个字段名底下**是两个不相交的词表**：缺口报告用那三个（schema
`$defs.dataGap`），假设台账用 `invalidating/distorting/confidence_only`。Python 侧
`_SEVERITY_ZH` 把六个并进**一个 dict**，于是「severity 是一个词表」这个误读没人拦得
住，浏览器照着抄走了一半。

**改动**：

- `themis/web/frontend/src/lib/verdict.ts` 新增 `VOCABULARIES`：**这个面陈述的每一个
  内核封闭词表 → 陈述它的那张表**，九条；配套 `NOT_VOCABULARIES` 让另外几张 keyed
  表各自说明自己为什么不是（渲染器不是读者的字，钉它们的是 `RENDERED_BLOCKS`）。
  **豁免名单放在 `.ts` 里而不是测试里**——决定要待在表旁边，写表的人从不打开测试
  文件，那正是那五张没被钉住的表的来历。
- `tests/test_web_vocabularies.py`：一个**括号匹配**的 `.ts` 解析器（此前三个测试
  文件各写了一份只认一张表的正则），三条守卫——每张表的键集**双向**等于内核词表 /
  文件里每张 keyed 表都表过态 / `VOCABULARIES` 的每一条都有锚点。**锚点表写在内核
  一侧**：只有从「知道这个词表存在」的那端，才看得见「浏览器根本没有对应的表」。
- 拒答那一行改说 `kind`（五句各带 head/tail），`failure_type` 降为**安静的 mono
  标注**——与状态芯片、缺口清单已经在用的那种配对一致，也与主报告的选择一致
  （69 个物种是开发者的把手，读者的句子是 kind 这一句加上当次的 `reason`）。
- `STATUS_LABEL` + `STATUS_BLURB` 并成一张 `STATUS_META`（**同一个词表两张表就是
  两次只握住一半的机会**），补 `outside_language`、删内核不发的 `unidentifiable`；
  `GAP_TITLE` 补齐 8 条——写之前先从语料里读出每一条自己的 `description`，不照着
  名字猜。
- 两个 severity 词表分家：`assumption_glossary.SEVERITIES` 成为一等的（台账那三个），
  `analysis_report._SEVERITY_ZH` 收窄为 `_GAP_SEVERITY_ZH`（缺口那三个）。
- `extensions.identification.pattern` 进 schema 的 enum——四个「pattern 型」字段里
  它是唯一没有声明域的，而它是写得最多的那个。

**修完之后（把 2101 份真信封喂给编译后的 web 代码）**：

```text
[request]  没有给出数值 │ 需要你改一处输入  invalid_input
                       target_marginal probabilities must sum to 1; got 0.6 改掉之后重跑即可。
[graph]    没有给出数值 │ 这是关于因果图的结论  interventional_risk_not_identifiable
                       P(Y=1|do(x=False)) is identified by neither… 再多同样的数据也不会改变它;要改变的是图或问题本身。

gap kinds still printed raw : 0     ledger severities still raw : 0
```

**跨面这一条是最后补的，而它当场抓到我自己**：主报告对 `backend` 说的是「没有**算出**
数值」（例程跑了但没算出来），其余四种说「没有**给出**」——一个字的刻意区分。我的第一
版把 web 的行标签写死成「没有给出数值」，等于**这个面用一个字推翻了另一个面的判断**。
于是 `lead` 也进表、逐 kind 声明，钉法改成「web 的 `lead`/`head`/`tail` 三段都必须在
主报告那一句里出现」——反例 14 正是我二十分钟前那个版本，被拒。

**守卫（十五条反例，全部构造并见红）**：状态少一个 / 多一个内核不发的、gap kind 少
一条、新加一张 keyed 表却不表态、`VOCABULARIES` 加一条没锚点、两个 kind 说同一句话、
浏览器给台账 severity 自己换词、**schema 新增一个 gap kind 而没有标题**、两个
severity 词表出现交集、**一张表同时进两个名单**、**把真词表挪进豁免名单**（被内核侧
锚点抓住）、web 改了拒答的行动句、**主报告改了行动句**（两侧都咬）、web 抹平 算出/
给出、web 编一个主报告没说过的 lead。

**基线（本条）**：4200 → **4219**。

**声明的取舍 / 未做**：①`VOCABULARIES` 关不上的那半是**「一个词表被陈述了、却一张
表都没有」**——守卫只能看见「文件里已有的表」和「锚点表里已有的词表」，看不见「浏览器
印了某个东西而两边都没登记」。所以条目按**词表**命名而不是按表命名，锚点表写在内核
一侧，把洞收窄到「内核加了词表」这一侧能被发现。②`numeric_estimate.method`（489 份、
36 个值）与 `bounds_result.method`（1134 份、3 个值）**仍是裸标识符**，两个面都是——
但两个面都把它摆成中文 caption 旁边的机器把手（`方法 \`x\`` / `数值估计 · x`），与
`failure_type` 这次的处置同型，按已有纪律算配对过；未改，也没有为它偷偷另立一条规则。

**新登记**：#340 浏览器上**没有「推导链」这一节**（1041 份信封带 `derivation.steps`、
63 个规则，`derivation_glossary` 只在 Python 侧；是「缺一整节」不是「缺一张表」，
故没并进本条）；#341 台账的 `layer` 是 **6 个取值**的封闭词表（688 份信封），
**主报告裸印英文**，而 `assumption_glossary` 只声明了其中 3 个；#342
`assumption_ledger` 在 schema 里没有子 schema（18 个块里 10 个都没有），所以本条只能
把它的 severity 锚到 Python 模块，而不是锚到两个面共读的那份契约。

**方法论沉淀**：(62)**「有几张表」和「每张表都被钉住」在源码里长得一模一样——探针是
去数「已有的表里有几张真被测试钉住」，而漂移会集中出现在没被钉的那些里**。本档
8 张里 3 张被钉，没被钉的 5 张漂了 2 张（40%），被钉的 3 张漂了 0 张。这是 (56) 的
下一步：(56) 说「一条纪律施行在几个面上是可以数的」，这里是**同一个面之内，一条纪律
施行在几个成员上也是可以数的**。(63)**同一个字段名底下可能是两个不相交的词表，而
把它们并进一张表的那一侧不会出错——出错的是照着抄的下一个面**。判据：Python 的
`_SEVERITY_ZH` 六个键读起来完全正确，浏览器抄成三个键也读起来完全正确，只有把两个
域并排列出来才看得见它们不相交。找法是问「这个词表的域取决于什么」——答案若是「它挂
在哪个块上」，那就是两个词表（㉞ 的又一次）。

### 一个封闭词表被列了十一次，而它的域取决于「谁写的它」（2026-08-05，接上条）

上条给 web 面补答案时要把 `interventional_risk_provenance` 翻成中文，顺手量出这张
词表**被列了十一次，没有两次是同一个集合**。这条把它做完，并且查实差异不是漂移：

```text
四条推导规则，四个真实的域：
  probabilities_of_causation_tian_pearl   theta·两臂 → derived_identification / user_experimental
  numeric_causation_estimate              数据·两臂 → exogenous / backdoor_adjustment / user_experimental
  counterfactual_cell_bounds              theta·一臂 → not_required / derived_identification / user_experimental
  numeric_counterfactual_cell_estimate    数据·一臂 → 上面六个（无 derived_identification）
其余每一次列出，都是这四行的并集或投影——而**没有任何东西说出这件事**。
```

**根因**：域取决于**哪条推导规则写的它**，而那个映射没有一等表示（㉞）。于是每个
消费端只能就地写自己那半个域；更要命的是，「这个取值做出什么断言」也没处放，只能
以 `if provenance in (...)` 的形式散在规则体里——**一个取值只要没人给它写分支，
它就什么也不断言，而这看起来和「已经检查过了」一模一样**。

**为什么是根因不是表象**：表象修法是给缺检查的两条规则各补一句
`if provenance not in {...}: raise`。三条判据否掉了它——

- **schema 已经在做成员检查**。实测：把数据端 causation 的 provenance 改成
  `derived_identification`，`themis.verify` 在 `validate_result` 就拦下了。补那两句
  拦不住真正的漏洞，因为下面那个值**在域内**。
- **真正的洞是「`user_experimental` 在四条规则里都不做任何可复核的断言」**。实测：
  拿一个真的由 `{z}` 后门标准化算出来的 causation 结果，只把 provenance 改成
  `user_experimental` —— **`themis.verify` 通过**。而它同时是
  `if provenance in ("backdoor_adjustment", "exogenous")` 这个闸门的反面，那是该规则
  **唯一一次在图上复核**（调整集是否可容许）。也就是说：**改一个标签，就能让错误的
  调整集不再被审计**。姊妹规则的 docstring 写着「every value ... re-derived from the
  query rather than taken on the producer's word」——那句话是假的。
- **同一个 licence 在假设词表里有两个 ID**：`interventional_risks_from_randomized_
  experiment`（复数，两臂）和 `interventional_risk_from_randomized_experiment`
  （单数，一臂），**中文一字不差**都是「干预风险取自随机实验」。两个产生端各自发明
  一遍的指纹；而那句相同的中文，恰好把第二个 ID 存在的唯一理由丢了。

**改动**：

- 新建 `themis/risk_provenance.py`：`RiskProvenance(StrEnum)` 七个取值各声明一次，
  每个带 `uses_risk`（是否真的用了干预风险）/ `asserts`（**可复核的断言**，写给下一个
  加取值的人：给不出一句验证器能重推的话，那就不是 licence，是产生端的自述）/
  `zh`（读者句，**对 theta 与 data 两条路都为真**）。`ADMISSIBLE` **按推导规则分四行**，
  import 期反问「有没有取值掉出所有行」（白名单对自己漏掉了什么是沉默的，㊼）。
  `stamp(rule, licence)` 是唯一出口——产生端选 licence 的那条分支按构造就是没人测过
  的那条，让规则与 licence 在唯一同时已知的时刻碰一次面。
- **验证器仍然不 import 它**（沿用既有纪律：拿产生端选的词汇去复核不叫独立复核）。
  它自己重申同样四行 `_RISK_PROVENANCES_BY_RULE`，测试钉相等；四条规则各补成员检查，
  **并且四条都从 `ctx.query` 重新推导 `user_experimental`**——三份手写的 risk-free
  谓词塌成一个 `_RISK_FREE`。
- **断言写成三分支而不是双条件**：`user_experimental` ⇒ 查询必须带那一臂；用了臂的
  其他 licence ⇒ 查询**不能**带（每个产生端都优先取调用方给的臂）；risk-free 的两个
  **豁免**——同世界的格子根本不读臂，调用方顺手多传了什么与它无关。（第一版写成双
  条件，会把「同世界 + 调用方也传了实验臂」这个正确结果误拒；已构造该用例钉住。）
- **三份中文映射 + 那个二分支 `if/else` 塌成一次查表**（`describe`）。顺带修掉两处
  不准确：`exogenous` 原来说「X 无父节点」（真正的条件是**没有后门路径**），
  `backdoor_adjustment` 在 explainer 那份写着「从数据算得」（theta 路径上是假话）。
- `assumption_glossary` 那两句一字不差的中文各自说清是「两臂」还是「本格所需的那一臂」。
- `_EnvelopeName` 从 `refusals.py` 提到 `themis/types.py` 成 `EnvelopeName`——第二个
  上信封的枚举来了，每个注册表各写一遍 `__reduce_ex__`/`__copy__`/`__deepcopy__` 的
  约定必然漏掉三分之一（㊹）。

**账**：十一处列出 → **五处**（三个 schema enum + 验证器一张表 + web 一份映射），
**五处全部钉在同一张表上**；`counterfactual_cell.RISK_PROVENANCES`、
`rules._CF_CELL_RISK_PROVENANCES`、那个内联字面量、`causation.py:107` 的陈旧注释、
两份中文 dict、那个二分支 if/else —— 全部消失。web 那份连**句子**也钉了（只允许
半角标点这一处差异）：读者在报告里和在浏览器里得到两种解释，本身就是一条 bug。

**代价（声明）**：`explainer` 那个二分支 if/else **是潜在假话不是活假话**——插桩跑
全量实测 `_explain_causation` **零次调用**（`explain()` 只在 `run_trial_pack.py`
与测试里被调，而数据端的 `extensions.causation` 是 dispatch 往 dict 上写的、
`result_orchestrator.from_dict` 至今 `NotImplementedError`，所以数据端的值到不了
它）。修它的理由是「读者面的句子不该靠一条没人写下来的可达性论证才正确」，不是
「有人被骗了」。真正被骗的是**验证器**。

**基线（本条）**：4059 → **4078**。

**方法论沉淀**：(58)**一个封闭集合的每个取值都该说出「我断言什么」，而没人给它写
分支的取值不是「已检查」，是「什么也没断言」——这两者在代码里长得一模一样**。判据
三条：①先问「这个字段的域取决于什么」，答案若是「另一个事实」（这里是哪条推导规则），
那张映射就是缺的一等表示（㉞）；②**验成员资格拦不住域内的错值**——真正的探针是
「把值改成域内的另一个，验证器还过不过」，本档正是这样量出那个洞的；③一个取值若是
某个复核分支的**反面**（`if provenance in (A, B)` 的 else），它就是关掉复核的开关，
优先级最高。(59)**「A 当且仅当 B」这种断言，写之前要先找它的豁免类**——本档 licence
分三类：断言用了外部臂的、断言用了图的、和**根本不读臂的**；第三类对 B 无话可说，
双条件会把它们误拒。找法是问「这个字段在什么情况下压根没被读」。

### 同一条纪律，四个族里只施行在一个族上——浏览器那一面把整个答案丢了（2026-08-05，接上条）

上条在 Python 主报告上修完 causation 的答案节。同一个查询在 **web 面**上（实测，
跑真实管线 + 用 esbuild 编译真实的 `verdict.ts` 在 node 里跑）：

```text
单调    → 点估计 0.500                  ← 一个不具名的数,PS/PNS 一个字都没有
非单调  → (答案栏空)                     ← numeric_result.value 是 null
数据端  → 数值估计 · causation_plugin 0.432   ← 上条刚在报告上修掉的那个病
```

三个量的名字全都在 `extensions.causation` / `numeric_estimate.
probabilities_of_causation` 里躺着，没人读。

**根因**：`blocks.bind` 是 Python 函数，`BOUND` 的键从 `sys._getframe(1)` 取，
`.ts` 文件按构造永远进不去。于是 `carried_by=None`（「某个面渲染它」）在 Python 侧被
测试翻译成「**主报告**渲染它」，而对 web 面**这个断言不存在**。机制本身并不缺——
`test_route_section.py` 早就把 web 的 `ROUTE_ORDER` 数组解析出来、和
`blocks.declared_as(ROUTE)` 钉成相等、还逐个查渲染器。**分母是 13 个
`carried_by=None` 的块**：Python 主报告 import 期绑满 13/13（`bind` 三次，ROUTE +
ANSWER + ASSUMPTION，这是 #333 补上的——2026-08-04 那条「取舍③」说的「import 期
保证目前只有 route 一族」自那以后已不成立）；web 面 **10/13**，缺的正是 ANSWER
整族。这是 #333 那条在另一面的翻版：`read_as` 覆盖四族、强制只覆盖一族。

**为什么是根因不是表象**：表象修法是「给 `verdict.ts` 加一个 causation 分支」。判据
两条——①中招的不是一个块，是**整族两个 `carried_by=None` 的块**（`causation` +
`scm_counterfactual`），正是 #313 在 Python 侧发现缺渲染的同一族同两个；②「谁已经
不得不知道」这个探针命中了：`answerRows` 的注释自己写着「A test pins that every
declared shape is read here」——web 面**已经**在对 `answers.py` 那张表负责，它对
`blocks.py` 只负责 ROUTE 一族，纯粹因为没人写那条测试。

**探针本身翻车了一次，值得记**：朴素的「块名在 web 源码里出现过吗」给出 **18/18 全 OK**，
是假的。`causation`/`scm_counterfactual` 命中的是 `verdict.ts` 里 `VERDICT_META`
的 **query_kind 标签**（`questions.CAUSATION` vs `blocks.CAUSATION` 同名冲突，
第三次以同一形态出现）；`counterfactual_cell` 命中的是 `numeric_estimate.
counterfactual_cell`——那个块 `carried_by="numeric_estimate"`，所以这一次命中的
恰好是对的。**判据必须是「读没读 `extensions[<块名>]`」。**

**改动**：
- `verdict.ts` 把 ROUTE 已有的那套（声明数组 + 渲染器表 + 通用循环）泛化：
  `ANSWER_ORDER` + `ANSWER_RENDERERS`，`routeRows`/`answerBlockRows` 共用
  `blockRows`。`RENDERED_BLOCKS` 一张按族分桶的表说出「这个面自己渲染哪些块」，
  **四族键全在**（`gap: []`，两个 GAP 块由 `data_gap_report` 承载）。
- **一个渲染器,三个入口**：`extensions.causation`（theta）、
  `numeric_estimate.probabilities_of_causation`（数据）走同一个 `ANSWER_RENDERERS.
  causation`——和上条在 Python 侧做的合并是同一件事。顺带说出那个原来说不出的区别：
  `ci_lower/ci_upper` 有点时是抽样区间、没点时是可识别集的**外带**。
- **数据端那一半是查放置位置时才发现的**：`answerRows` 开头
  `if (num.point != null) return null`——对每个「没有点」的形状都对,对
  「每个量各有一个点」的形状是错的（causation 的 `point` 镜像 PN）。读 `poc` 的那
  一支被**排在早退之后**,于是永远不跑。
- `types.ts`：`numeric_result` 补 `interval`（原来只声明 `value`，这就是非单调那支
  答案栏为空的直接原因）；`probabilities_of_causation` 按 schema 的
  `causationQuantity` 写全（原来只有 lower/upper）。

**新守卫（三条，各自构造反例见红）**：
- `test_the_web_renders_every_family_the_registry_makes_a_surface_render`
  ——按 `blocks.FAMILIES` 参数化，`RENDERED_BLOCKS[族] == rendered_in(族)`，
  顺序也算。反例：删掉 `gap: []` / 调换 ANSWER 顺序 → 红。
- `test_every_block_the_web_lists_is_read_by_something_there`——列了就得有人读。
  接受两种机制（`verdict.ts` 里按名索引的渲染器，或组件里 `extensions.<name>` 的
  定义性读法），因为 `carried_by` 本身就是两值的；账本的行带严重度、是 JSX，为了
  让检查整齐把它压成 label/value 会让界面变差。反例：删掉 causation 渲染器**但把
  名字留在文件里**（第 99 行那个 query_kind 标签还在）→ 红。
- `test_the_web_reads_a_multi_quantity_shape_before_the_point_shortcut`
  ——「双模方法里更锋利的那个形状不是 `POINT`」这件事**已经在 `SHAPES_OF` 里**，
  不用给 `Shape` 加字段。反例：把 `poc` 那一支移回早退之后 → 红，**而原来那条
  按名字查的测试 7 条全绿**——(54) 这条当场又演了一遍。
- 跨语言的 `interventional_risk_provenance` 词表：web 需要它（否则「两个干预风险
  是从图上导出的还是实验测的」这件事在 web 上无处可说），但那是 #336 记的那张
  「列了七次」的词表。所以**新增的这一份当场钉在 schema 上**：
  `test_both_surfaces_translate_the_same_risk_provenance_vocabulary` 把
  `analysis_report._RISK_PROVENANCE_ZH` 和 `verdict.ts` 的
  `RISK_PROVENANCE_ZH` 都对着 `extensions.causation` 的 enum 校验。**#336 的
  计数因此是 7 处列出/3 处受纪律 → 8 处列出/5 处受纪律**，不是变糟。

**基线（本条）**：4041 → ****4059****。

**方法论沉淀**：(56)**一条纪律施行在几个族/几个面上,是可以数的,而「有一条」和
「都施行了」长得一模一样**。判据：①先数**分母**——这条纪律的对象一共有几个（四个族 ×
两个面），再数分子；②跨语言的保证会**按构造**漏掉另一种语言（`BOUND` 的键是
Python 模块名），所以「有守卫」不等于「守卫看得见这个面」；③补的时候要问
「另一个面已经有的那套结构能不能泛化」而不是新写一套——ROUTE 的三件套原样长出
ANSWER 的三件套，两条新守卫是同一条参数化出来的。(57)**放置一个新渲染器时要把
调用点的分支顺序读完——「读了这个字段」和「这一支会被执行」是两件事,而早退是
最常见的差别**。判据：本档数据端那半个 bug 不是查它查出来的,是决定
`answerBlocks` 放在 `Verdict.tsx` 哪一支时,顺手读了 `answerRows` 的第一行。

---

注意：下方保留了早期 `v1.0 core freeze` 和 Phase 5 以前的历史收口记录。
后续 Phase 6-14 是显式解冻后的 fragment / workflow / estimator 扩展，
不是对 `v0.1.0` 基线的静默漂移。

---

## 核心冻结 v1.0

> 冻结日期：2026-04-21
> 初始冻结后第一批延伸 fragment：A6.front-door、Phase 2.latent、Phase 5.temporal、Phase 5.counterfactual（见下方"冻结后显式立项的 fragment"段）。后续 Phase 6-14 另以独立 charter / slice 继续显式解冻。

从这一版起，**Themis 核心（语言 + 运行时 + 数值层 + verifier）视为已收口**。
后续工作往外长，不再往核心里塞。

**收口面**：

- 语言：`cause / probability / observation / query / variableDeclaration` +
  `forall` + 有限对象域
- 运行时：DAG 投影、`cause / assoc / identify / effect / probability`
  调度、backdoor 调整集、conditional identify、supporting paths
- 数值层：`Theta`、probability / effect 数值求值、缺参数精确报缺
- 工作流：`needs_investigation`、parameter skeleton、bundle 提取与回填、重跑 diff
- 解释与 framing：explanation、`framing_notes`、A0 advisory 检查
- confidence：`min(non-None)` 规则、解释文本中呈现
- 严格推导层：V0 identify / V1 numeric / V2 derivation JSON /
  V3 负结构见证 / V4 正结构见证 / V5 context JSON

**冻结期允许的改动**：

- bug 修复（语义不变）
- verifier 规则内部加强（同一 rule family 内的紧化，比如 V4 那种 witness 完整性）
- 文档 / 测试 / 真实案例 fixture
- 上层 workflow（比如 Variable Framer）—— 在核心之外，不算破冻

**冻结期禁止的改动**：

- 新 query 类型（前门 / 完备 ID / 反事实 等）
- 新语义维度（时序索引、潜变量、双向边、ADMG）
- 新 rule family、新 AST 语句类型
- 已有 framing_notes / confidence / derivation 语义的改写

要改这些，先解冻，并在此文档里留记录。

---

## 冻结后显式立项的 fragment

### A6.front-door（立项 2026-04-21，落地同日）

**理由**：按 ROADMAP 原则 "如果某个跃迁已经被清楚定义为一个新的理论 fragment,
边界/对象语言/规则集和完成标志都能说清, 也可以 theory-first 地启动"。
前门准则是对 V0–V5 识别骨架的 scope 内对称扩展——不引入潜变量 / 双向边 /
新 AST 节点，只在已有 DAG 语义内补另一条识别路径。

**交付**：

- `structural_solver.front_door_sets(graph, x, y)` — 返回满足 Pearl 前门
  准则 (FD1/FD2/FD3) 的最小 mediator 集合
- `formula_builder.front_door_formula(target, intervention, mediators)` —
  单 mediator 前门公式构造，多 mediator 暂 raise `FormulaSupportError`
- `scheduler._dispatch_identify` / `_dispatch_effect`：backdoor 搜索失败
  且 query.given 为空时，回退到 front-door
- verifier rules：`front_door_criterion` / `front_door_adjustment_formula` /
  `identify_via_front_door`，独立重实现 FD1/FD2/FD3 和公式模板
- `verify_identify` / `verify_numeric` 接受 `identify_via_front_door`
  作为候补的识别见证 rule

**未包含**：

- 多 mediator 前门（需要链式 P(Z1..Zk|X) 分解）
- 条件化前门（`given` 非空时）
- 潜变量 / 双向边 / ADMG — 这是后续独立 fragment 的地盘

**Done 标志**：14 个测试覆盖结构搜索、公式形状、scheduler 回退、
verifier 接受 / 拒绝三类篡改（mediator / 公式目标 / conditioned query）。
451 passed 全绿。

### Phase 2.latent — 窄 scope（立项 2026-04-21，S1–S4 落地同日；窄化 charter 同日）

**理由**：ROADMAP Phase 2 的 theory-first 启动规则 —— ADMG + m-separation
+ ADMG-aware backdoor / front-door 是对 V0–V5 识别骨架的一次有边界的
扩张；charter（[PHASE_2_LATENT_CHARTER.md](PHASE_2_LATENT_CHARTER.md)）
§0 记录了实现过程中的一次 scope 窄化：generic Tian c-factor / c-forest
/ complete ID 全部移出本 fragment，等真实案例逼出需求时再独立立项。

**交付（runtime）**：

- AST + schema：`BidirectedStatement`（无向 semi-Markov 边，`left` /
  `right` / 可选 `forall` / 可选 `annotations`）；kernel_ast.schema.json
  新增 `bidirectedStatement` $def 并入 `statement` oneOf
- `structural_solver.m_separated` / `is_m_connected` / `c_components` /
  `bidirected_from_ground`：ADMG 上的路径阻塞判定 + 分区原语 + ground
  抽取。m-separation 在 `bidirected=∅` 下与 d-separation 精确一致
  （6-node 全枚举回归 pin）
- `front_door_sets` 增 `bidirected` 形参；FD2 / FD3 在 ADMG 上改用 m-sep
- `minimal_adjustment_sets` 增 `bidirected` 形参；adjustment 有效性改用
  ADMG-aware backdoor m-path 判定
- scheduler：ADMG 程序 identify / effect 先试 ADMG-aware backdoor，失败
  回退 ADMG-aware front-door，仍不通过则 `needs_investigation` +
  `query:identify_admg` / `query:effect_admg`
- gate：ADMG 程序上 cause / assoc / probability 查询仍被 semantic
  validator 拒绝（dispatch 路径未 ADMG-aware）

**交付（verifier, S4）**：

- `VerificationContext.bidirected` 新字段
- 独立 m-sep 重实现（byte-code 扫描 pin：`_verifier_is_m_connected` /
  `_verifier_is_admg_backdoor_connected` 不调用 `structural_solver`）
- 新 rule family：`m_separation_witness` / `m_connection_witness`
- `backdoor_criterion` / `front_door_criterion` rule 在
  `ctx.bidirected` 非空时切换到独立 m-sep 检查
- `themis.verify` 对 ADMG 结果直接 accept，`AdmgVerificationPending`
  从代码路径中移除（类符号保留供历史 import）

**未包含（移出 charter，延后立项）**：

- ~~generic Tian c-factor 公式构造 + Pearl ID 算法递归~~ → **已落地为
  S.3.b.2 fragment**（2026-05-06，见下方 Phase 2.latent §S3.b.2 节）
- ~~c-forest / hedge 作为 unidentifiable witness~~ → **同上**
- IDC / 多 intervention / 多 target / 非空 given 的 conditional ID
- ADMG 下的 cause / assoc / probability 查询（dispatch 路径仍需
  ADMG-aware，独立立项）

**Done 标志**：3 个 ADMG 案例 + DAG 回归（S3.a 正例：hidden-U 前门；
S3.b.1 正例：Z→X→Y, W↔Z, W→Y 的 backdoor；bow-arc 反例：
`needs_investigation`，本 charter 不判 unidentifiable）。verifier
独立性由 byte-code 扫描 + 多个篡改复核测试 pin。640 passed 全绿。

### Phase 5.temporal（立项 2026-04-22，§T / S.T.1–S.T.6 同日落地）

**理由**：按 Phase 5 charter（[PHASE_5_CHARTER.md](PHASE_5_CHARTER.md)）
对 v1.0 核心做一次显式时序解冻，让 kernel 能表达 clean `t-1 -> t`
的相对时间滞后，而不再把这类问题压平成 atemporal DAG。

**交付**：

- AST / schema：`Atom.time_index`（首版只支持
  `{"kind":"relative","value": int}`）
- verifier：`T1_time_monotonicity` / `T2_lag_bound` /
  `T3_unroll_acyclic`
- graph projection：`(predicate, args, time_index)` 视作独立节点
- scheduler：现有 `cause / assoc / identify / effect / probability`
  直接复用时间展开图，无需专门 temporal dispatcher
- e2e：Case 14 的 timed AST / timed query 跑通
- prompt：A1 v2.2 直接产出 `time_index`，不再对 clean `t-1 -> t`
  案例声明 `extensions.ambiguities[kind=temporal]`

**首版 scope**：

- 程序级相对时间轴
- 1 阶 Markov（lag ≤ 1）
- 不引入绝对时间 / 多步 lag / 动作序列 / planner

**Done 标志**：`S.T.1–S.T.6` 全通；Case 14 从“压缩 + temporal
ambiguity”升级为 timed AST / timed query。相关测试 29 passed。

### Phase 5.counterfactual（立项 2026-04-22，§C / S.C.1–S.C.6 窄 scope 落地）

**理由**：按 Phase 5 charter（[PHASE_5_CHARTER.md](PHASE_5_CHARTER.md)）
对 v1.0 核心做一次显式反事实解冻，让 kernel 不再把 clean
Layer-3 反事实问题一律压成 Layer-2 effect proxy。

**交付**：

- AST / schema：`counterfactual` query kind +
  `assumptions.monotonicity`
- runtime：twin-network projection primitive + Balke-Pearl binary
  monotone bounds primitive
- scheduler：缺 monotonicity -> `needs_assumption`；缺 Theta ->
  `needs_investigation`；条件齐 -> `counterfactual_bounded` /
  `counterfactual_solved`
- prompt：A1 v2.3 对 clean "如果当初..." 直接产出 `counterfactual`
  query，不再默认声明 `counterfactual_query` ambiguity
- e2e：Case 17 从 effect-proxy / ambiguity 升级为 real
  counterfactual query path

**首版 scope**：

- bool-only SCM
- 单 intervention / 单 target
- 显式 monotonicity 假设
- 窄 runtime path：优先在无相关 `bidirected` 触碰的 directed ancestral
  subgraph 上恢复 `P(X,Y)`；不适用时回退到局部链式 / 布尔互补恢复

**Done 标志**：`S.C.1–S.C.6` 全通；Case 17 对 clean counterfactual
不再走 ambiguity proxy；并已接上 derivation / verifier / context JSON 外部复核。
当前检查点全量测试：726 passed / 143 skipped。

---

## 一句话结论

**Themis 作为“已知模型下的静态因果推理内核”，已经基本成型。**

更具体地说：

- 已经能在给定结构、给定参数时，对 `cause / assoc / identify / effect / probability`
  做结构推理、公式构造、数值求值、缺口报告和最小工作流闭环
- 已经开始具备“严格推导”的形态：核心结果可附带 derivation，由独立 verifier 复核
- 还没有完成上游世界建模、更宽的 counterfactual / 动作级时序、以及更完整的 ID / 自动建模这些更大层次

所以当前最准确的定位是：

**一个可运行、可验证、可补录的因果推理内核；其静态 DAG 核心已收口，并已显式解冻出 front-door、窄 ADMG、窄 temporal、以及窄 counterfactual fragment。**

---

## 当前核心范围

当前系统范围只包含：

1. **已知变量、已知结构、已知/部分已知参数** 下的推理
2. 静态 DAG 核心 + 已显式立项的 fragment：
   - A6.front-door
   - Phase 2.latent（窄 scope）
   - Phase 5.temporal（窄 scope）
3. 结构查询、数值查询、缺参数闭环
4. 结果解释、confidence、以及 derivation verifier

当前系统范围明确**不包含**：

- 完整自动世界建模平台（事实抽取 / 候选关系收敛 / 自动模型治理）
- 动作序列语义 / 多步时间规划 / 完整动态系统
- 完整潜变量 / 完整 ADMG / complete ID
- 完整 Layer-3 反事实 / 连续反事实 / 通用 twin-network ID
- 通用 agent 行为

---

## 已完成能力

### 1. 语言与输入

- JSON AST + schema
- 有限对象域
- `forall` 实例化
- `cause / probability / observation / query`
- `variableDeclaration`（predicate 层 metadata，opt-in）

### 2. 结构推理

- DAG 投影
- `cause`
- `assoc`
- `identify`
- 后门调整集
- front-door
- 条件 identify（`given`）
- 路径 / 开放路径 / supporting_paths
- 窄 ADMG：m-separation、c-components、ADMG-aware backdoor / front-door
- 窄 temporal：relative `time_index`、time-expanded graph、现有 dispatcher 复用

### 3. 数值层

- `Theta`
- `probability` 查询数值求值
- `effect` 查询通过后门 / front-door 公式数值求值
- 布尔与分类值域
- 缺参数时精确报缺，不瞎算

### 4. 工作流层

- `needs_investigation`
- investigation grouping
- parameter skeleton
- skeleton bundle 提取
- 回填 merge
- 重跑 diff

### 5. 解释与 framing

- 中文 explanation
- 解释与公式/结果的一致性
- `framing_notes`
- A0：问题定义不充分的 advisory 检查

### 6. confidence

- 正式规则：`min(non-None inputs)`
- 结果上可输出 `confidence`
- 解释文本中可呈现 confidence

### 7. 严格推导层（verifier）

已完成到：

- **V0**：`identify` 结构证明
- **V1**：`effect / probability` 数值证明
- **V2**：derivation JSON round-trip
- **V3**：负结构 witness
- **V4**：正结构 witness
- **V5**：context JSON round-trip

也就是说，当前已经能把：

- derivation
- graph
- query
- theta

都序列化出来，然后由 verifier 独立 accept / reject。

---

## V0..V5 当前状态

### V0：Identify Derivation

状态：**完成**

已具备：

- `backdoor_criterion`
- `backdoor_adjustment_formula`
- `identify_via_backdoor`
- verifier 绑定到当前 query
- 真实公式见证约束

### V1：Numeric Derivation

状态：**完成**

已具备：

- `probability_ref_lookup`
- `formula_evaluation`
- `numeric_result`
- `effect / probability` 数值证明与 query/formula 绑定

### V2：Derivation Serialization

状态：**完成**

已具备：

- `derivation.schema.json`
- derivation round-trip
- malformed derivation 统一报 `DerivationSerializationError`

### V3：Negative Structural Witnesses

状态：**完成**

已具备：

- `unidentifiable_via_backdoor`
- `d_separated`
- `no_directed_path`
- theorem family 绑定

### V4：Positive Structural Witnesses

状态：**完成**

已具备：

- `cause_via_directed_path`
- `d_connected_via_open_path`
- supporting path 集合完整性检查

### V5：VerificationContext Serialization

状态：**完成**

已具备：

- `context_to_dict / context_from_dict`
- graph + query + theta JSON 化
- malformed context 统一报 `DerivationSerializationError`
- `effect / probability` query value 只允许字面量

---

## 基本完成但还不算“更大系统完成”的部分

### 1. Framing 三层状态（post slice #36 / #40 / #41）

- **变量框定闭环（kernel / JSON 层）**——**已完成**
  `variableDeclaration`（含 slice #41 的 direction / baseline /
  state_vs_event 共 7 个可选 framing 字段）+ `framing_notes` + F1
  `DEFINE_VARIABLE` investigation + `extract_definition_skeleton` +
  `merge_variable_declaration` + `apply_patch_and_run` 二轮重跑。
  `test_a3_apply_patch` + `test_framing_fields_v2` 已 pin。
- **变量框定闭环（NL / agent 层）**——**已完成（slice #40）**
  第三条 prompt `reply_to_framing_patch.md` 把用户 NL 答复结构化成
  `framing_skeleton_bundle`。A1 的 question / response 两侧加上这条
  答复侧，NL↔JSON 三方对称。
- **变量框定强 gate（问题没框清就拒绝出数）**——**已完成（slice #36）**
  opt-in 的 `program.options.strict_framing: true`。启用时
  `effect` / `probability` 查询在 A0 报出任何 framing gap 时直接
  flip 到 `needs_investigation` 且不出数，F1 DEFINE_VARIABLE
  仍然正常产出填写 skeleton。默认 `false` 保持 advisory 行为。
  15 个 pin 测试覆盖矩阵（见 `test_strict_framing_gate.py`）。

### 2. 真实案例已经能跑，但还没有变成系统上游

当前有：

- `exercise_waist`
- `sleep_focus`
- `tutoring_exam`

当前没有：

- 从真实语料自动构变量
- 从事实语料自动产候选关系

### 3. Confidence 已经是正式语义，但证据来源追踪还没完成

当前有：

- numeric confidence
- explanation 中的 confidence 文案

当前没有：

- 完整 source 结构化
- 最弱证据来源追踪

---

## 还没有开始或明确延后的部分

### 1. 完整上游世界建模平台

当前已经有 NL bridge、narrative merge、variable framing、KB adapter
contract 和 MCP wrapper 这些 down-payment。仍未完成的是：

- 事实抽取
- 候选关系生成
- 模型收敛
- 跨来源冲突解决
- 自动模型治理

这部分是
[WORLD_MODELING.md](WORLD_MODELING.md)
定义的上游层，不是 Themis 当前核心的一部分。

### 2. 更强识别能力

包括：

- 完备 ID

当前明确延后，等待真实案例逼出需求。

### 3. 更宽时序语义

当前已完成 **窄 scope temporal fragment**，但还没有真正的：

- 绝对时间
- `lag >= 2`
- 动作序列
- 动态因果过程

### 4. 更宽问题 gate

当前已经有 opt-in `program.options.strict_framing: true`，能在问题
框定不充分时拒绝 `effect / probability` 出数。仍未完成的是：

- 默认全局强 gate 策略
- 不同 query kind 的细粒度 gate policy
- 上游世界建模输出进入推理前的系统级 gate

---

## 现在可以认为“收口”的部分

如果只看 Themis 核心 + 已显式立项的主要 fragment，这一批内容已经可以
视为当前收口面：

- 静态 DAG 推理语义
- `cause / assoc / identify / effect / probability`
- 结构结果与数值结果
- parameter fill-back workflow
- variable framing workflow + opt-in strict gate
- confidence
- derivation verifier V0..V5
- data-gap report + T10 verifier
- bounds-first 输出
- Phase 6-15 已落地 slice 的当前实现边界

这意味着：

**接下来如果继续改 Themis 核心，应该优先是小修小补、边界澄清、文档
同步和真实压力测试，不应再随意扩大语义面。**

---

## 当前建议

当前更合理的节奏不是继续膨胀核心，而是：

1. 把当前 Themis 视为 **`0.15.0-dev` 收口候选**
2. 同步 README / ROADMAP / CORE_STATUS / charter 状态，避免文档和代码脱节
3. 继续拿真实案例试跑，尤其压测 world-modeling / estimation / data-gap / KB / MCP 组合路径
4. 让下一阶段需求从真实痛点或明确 theory-first charter 里长出来

也就是说：

- 如果真实痛点落在“变量定义补录”，就推进 Variable Framer workflow
- 如果真实痛点落在“来源追踪”，就推进 source metadata
- 如果真实痛点落在“后门不够”，才进入更强识别阶段

---

### Phase 6 = M1 识别层完整化（立项 2026-04-24）

**理由**：VISION.md "扩展愿景"段里确认了从"静态因果推理内核"扩展到
"LLM-native 全板块因果推理编排器"的新方向。Phase 6 是这个扩展的第
一个里程碑——把识别层补齐到 Pearl 因果识别文献的 90%+ 覆盖。

**状态总览**：

| Slice | Charter | 状态 |
|---|---|---|
| 6.iv | PHASE_6_IV_CHARTER.md | **✅ 已落地（2026-04-24）**|
| 6.mediation | PHASE_6_MEDIATION_CHARTER.md | **✅ 已落地（2026-04-24）**|
| 6.front-door-multi | 无独立 charter（扩展既有族）| **✅ 已落地（2026-04-24）**|
| 6.complete-id | 未立 | 可选延至 Phase 6.5 |

#### Phase 6.iv 已落地（2026-04-24）

S.IV.1 – S.IV.7 全部完成：
- `structural_solver.iv_sets`：Brito-Pearl 2002 公式，ADMG-aware +
  conditional IV 搜索（|W| ≤ 3 默认）
- `_dispatch_identify` 回退链：backdoor → front-door → **IV**
- `_build_identify_via_iv` + 2-step derivation（iv_criterion_check
  + identify_via_iv）
- 新 verifier rule family：`iv_criterion_check` + `identify_via_iv`，
  byte-code scan 钉独立性，不调 structural_solver
- `query_result.schema.json` 加 `extensions.iv_identification` 子 schema
- A1 prompt v2.2 §3b：NL 层 IV 识别规则；response_rendering v2.2：
  IV 结果披露 + `iv_validity` ambiguity 模板
- 2 个 eval case（21 valid IV / 22 conditional IV rescue）+ F19
  taxonomy
- DoWhy 0.14 parity：9 个 DAG 案例全部对齐；ADMG 案例文档化为 Themis
  独有能力（DoWhy 无 bidirected 支持）

**Phase 6.iv 新增语言 / 语义面**（解冻清单）：
- 无新 statement kind
- 无新 query kind
- 新增 `QueryResult.extensions.iv_identification` 结构化字段
- `IdentifyResult` 识别策略加 "iv"（在 derivation rule name 层面）

**未包含**：Phase 6 其余 slice（mediation / 多 mediator 前门 / 完整
ID）独立 charter；Phase 7（估计器）、Phase 8（发现 + 敏感性）独立
立项。

**时间实际**：S.IV.1 到 S.IV.7 全部落地约 1.5 天（含 charter 起草）。
Charter 原估 ~4 周是为 4 个 slice（iv + mediation + multi-front-door
+ complete-id）合计；单独 iv 子 slice 的实际耗时证实算法本身不复杂，
主要工作在 verifier 独立实现 + schema 扩展 + eval case 配套。

#### Phase 6.mediation 已落地（2026-04-24）

S.M.1 – S.M.7 全部完成：
- `structural_solver.mediation_sets`：Pearl 2001 四条件 (M1-M4) NDE/NIE
  识别 + 后门式 CDE 识别 (C1-C2)，ADMG-aware，subset-minimal W 搜索
- `EffectQuery.mediator` 可选字段 + `_dispatch_mediation` 在 `_dispatch_effect`
  里短路：STRUCTURALLY_SOLVED + `extensions.mediation_decomposition`
- 三个新 verifier rule：`mediation_nde_nie_check` / `mediation_cde_check` /
  `identify_via_mediation`，byte-code scan 钉独立性
- `verify_effect_structural` 支持 EffectQuery 的识别层结果路径
- `query_result.schema.json` 加 `extensions.mediation_decomposition` 子
  schema（strategy 枚举 / failed_condition 严格约束）
- A1 prompt v2.3 §3c：mediation decomposition 触发模式 + canonical
  example；response_rendering：三类 strategy 展示模板 + M1-C2 plain-
  language 映射
- 2 个 eval case（23 running_metabolism NDE/NIE / 24 drug_inflammation
  recanting witness）+ F20 taxonomy
- DoWhy 0.14 parity：5 个案例覆盖共识与语义差异（DoWhy auto-picks
  mediator，Themis 用户指定 mediator）

**Phase 6.mediation 新增语言 / 语义面**：
- `EffectQuery` 加可选 `mediator: Atom | None` 字段
- `QueryResult.extensions.mediation_decomposition` 结构化字段
- 新 derivation rule names 族（`mediation_*_check` + `identify_via_mediation`）

**未包含**：数值 NDE/NIE 估计（Imai 非参 / g-formula 的 CDE 救援）→
Phase 7；多 mediator 链式前门 → 6.front-door-multi。

**时间实际**：S.M.1 到 S.M.7 全部落地约 1 天（含 charter 起草 + 测试）。

#### Phase 6.front-door-multi 已落地（2026-04-24）

扩展既有 front-door rule family 到多 mediator（无独立 charter）：
- `formula_builder.front_door_formula` 接受 mediator 元组 ≥2，按拓扑
  顺序做 chain-rule 因子分解 `P(Z1,...,Zk|X) = ∏ P(Zi|Z_{<i}, X)`
- `_build_expected_front_door_formula` 镜像扩展（独立重实现，不调
  builder）
- `_rule_front_door_adjustment_formula` 不再硬限制 `len(z) == 1`
- 4 集成测试：parallel-paths ADMG `X → M1 → Y, X → M2 → Y, X ↔ Y`
  通过 {M1, M2} 识别 + verifier 圆环

板块 1 覆盖 60-70% → 75-80%。落地 commit: `219cf5a`。

### Phase 7 = M2 数值估计层（已全落地 2026-04-24/25）

**理由**：M1 完成后用户能问"图能不能识别"但还要"给数字"。Phase 7
打开数据→数字这一环。

**状态总览**：

| Slice | Charter | 状态 | 落地 commits |
|---|---|---|---|
| 7.1 backdoor numeric | PHASE_7_1_BACKDOOR_NUMERIC_CHARTER.md | ✅ | 3935b81 → eb92efd |
| 7.2 front-door numeric | PHASE_7_2_FRONTDOOR_NUMERIC_CHARTER.md | ✅ | 5cdac9a → 7745d5a |
| 7.3 IV numeric | PHASE_7_3_IV_NUMERIC_CHARTER.md | ✅ | aa5867c → 829845e |
| 7.4 mediation numeric | （混入父 charter） | ✅ | 90dad85 → 4e474d1 |

**Phase 7 新增公开 API**：
- `themis.estimate(ast_dict, pandas_df) -> dict`：新顶层入口，数据
  通过 Python 旁路（不进 JSON）保持识别契约纯净
- `themis.estimation.{estimate_backdoor_ate, estimate_frontdoor_ate,
  estimate_iv_ate, estimate_mediation}`：四个独立 estimator
- `themis.estimation.DataContract`：DataFrame 验证 + SHA-256 hash

**Estimator 选择**：
- backdoor：sklearn LogisticRegression / LinearRegression + percentile
  bootstrap CI
- front-door：Pearl 3.29 plug-in，单/多 mediator chain-rule
- IV：Wald (binary Z+X) + 2SLS (continuous)，auto select
- mediation：statsmodels.stats.mediation.Mediation (Imai 2010
  algorithms 1+2)，作 production backend

**Verifier 松弛审**：4 个新 rule（`numeric_{backdoor,frontdoor,iv}_estimate`
+ mediation 走原 `identify_via_mediation`）。不重新训练（sklearn /
bootstrap 引入随机性使 bit-exact 复检不现实），只审 method enum +
point in CI + data_hash 格式 + adjustment 与识别 step 的一致性 + 字
段 disjoint 等。byte-code scan 钉独立性。

**followup(2026-07-10)：`verify_mediation_numeric` — mediation 数值答案块审计**。
此前 mediation 保持 `structurally_solved`→走 verify_effect_structural（只查
`identify_via_mediation` 终端），挂在上面的数值块（NDE/NIE decomposition +
两个 four-way 分解）**零数值审计**——实测 four_way_ratio 的 err_cde 篡改成 999 /
prop_mediated 篡改成 42 verify 全放过。修法分两级:①**four_way_ratio 强重导**
——block 补记拟合系数 `coefficients`(t1/t2/t3/b0/b1/bcc/mediator_reference)进
schema,验证器从系数经 VanderWeele 闭式(§3.4/§3.3)重导每个 err_*/prop_* 并核对
(自洽伪造也逮得住,因不再与记录的拟合吻合)+ 无转写内部恒等式(四 err 和=total_err、
total_rr−1=total_err、各 prop=分量比)独立复核;②**差值 four_way + NDE/NIE
decomposition 内部不变量**(TE=各部分和、prop=比)——其充分统计量(cell means/
模拟)未记录不可重导=诚实天花板,只逮单component篡改非自洽伪造(有测试钉住)。

**followup(2026-07-11)：longitudinal g-methods 全栈结构识别 + 数值验证器**。
此前时变处理(g-formula / IPW-MSM 策略对比数)骑在 `needs_investigation` 且**无
derivation** 的结果上——结构层对时变处理零识别,顶层 `themis.verify` 因 no-
derivation 守卫**直接拒审**,这个数完全在「没复核过的数不出门」契约之外(比漏验更
彻底的洞)。修法照 transport 先例给它一等公民结构识别:①**scheduler `_dispatch_
longitudinal`**(触发器=`options.longitudinal`,像 mediation/transport/joint)——
序贯后门可容许检查(每个 A_k 在测得历史 H_k={L_0..L_k, A_0..A_{k-1}} 条件下到 Y
无开放后门,未来协变量不入 H_k 故不误挡因果路径 A_k→L_{k+1}→Y),成功→`identify_
via_gformula` 终端 + STRUCTURALLY_SOLVED + `longitudinal_identification` 扩展;
②**numeric 层挂数翻 numerically_solved 保留结构 derivation**;③**验证器**:
`longitudinal_sequential_exchangeability_check` 规则用验证器本地 m-分离(mutilate
出边 + `_verifier_is_admg_backdoor_connected`,不调 structural_solver)独立重跑逐时
判据 + `verify_longitudinal_numeric` 从记录的 MSM 系数重导 IPW-MSM contrast/e_y
(逮孤立篡 point/mean/系数;整体系数向量自洽伪造=天花板,WLS 不重跑)、g-formula 只
构造不变量(point=E_treated−E_control,MC 黑盒=天花板)。**honest gate**:未测混杂
(bidirected A_k↔Y)→序贯可交换性失败→needs_investigation + `not_identified`
estimator_failure,**拒绝出有偏数**(遵循 missing_recovery 先例)。derivation 输入用
atom_tuple/atom_paths/单-StepRef 全可序列化(避开不支持的 tuple-of-StepRef)。

**Schema 扩展**：`numeric_estimate` 顶层字段 + `estimation_context`
+ `decomposition` 子块（mediation 用）。method enum 8 个值
（backdoor / frontdoor / iv / mediation × linear/logistic）。

**dispatch 优先级**：mediation queries (q.mediator 设) → backdoor
→ front-door → IV。每条路径失败/不适用时静默跳过。

**未包含**：CATE / ITE、AIPW、TMLE、Causal Forests Python
简化版、deep causal、连续 treatment IV、CDE 数值（参考 m 值）。

**时间实际**：Phase 7 整体（4 个子 slice）约 2 天落地。

板块 6 中介 50% → 70%；板块 11 数据驱动估计 0% → 50%。

### Phase 8 = M3 因果发现 + 敏感性（已全落地 2026-04-25）

**理由**：到 M2 为止 Themis 假设用户给图。M3 解决"图从哪来"
（discovery）和"图错了 / 假设违反时怎么办"（sensitivity）。

**状态总览**：

| Slice | 状态 | 落地 commits |
|---|---|---|
| 8.1 discovery (PC/FCI/GES/GRaSP/LiNGAM) | ✅ | e2b2677 → 48a7e6f；stronger-proposer + registry followup |
| 8.2 sensitivity (E-value) | ✅ | e1d8bdc → 97daad6 |

**8.1 Discovery**：
- `themis.estimation.discover_graph(df, algorithm="auto")` 包装
  causal-learn 0.1.4.5 的三个算法
- `discovery_to_kernel_ast(result)` 把 DiscoveryResult 转成可直接
  喂 `themis.run` 的 kernel_ast 草稿
- Algorithms：PC（无潜变量假设，CPDAG），FCI（容许潜变量，PAG），
  LiNGAM（线性非高斯，DAG）；'auto' 按 skewness 选 LiNGAM/PC
- Output 三桶：directed / bidirected / ambiguous（CPDAG 或 PAG 圆环
  端点）
- Ambiguous edges 自动转成 `extensions.ambiguities[kind=
  ambiguous_orientation]`，附 disambiguation_ask
- 5 条 API gate 审计：causal-learn ⚠ track record 4 年（接近但未达
  5 年门槛），其他 4 条满足；定为 production-with-caution，pin 版本

**8.1.2 更强的提议器（stronger proposer followup，2026-07-11）**：
- 定位：因果发现早已存在（proposer→已验证核心，学出的图隔离成待审提案）；
  这一档是把「提议」本身做得更好/更宽，不改护城河
- **GES**（score-based，Chickering 2002）作为第四个算法接入，
  `_run_ges` 复用 `_extract_edges`（返回 CPDAG 同 PC）；离散数据用
  `local_score_BDeu`、连续用 `local_score_BIC`
- **诊断驱动的确定性选择器**：`_diagnose_data`（样本量 / 变量类型 /
  连续列 D'Agostino 正态性 → `frac_non_gaussian`）→ `_select_algorithm`
  规则（连续+非高斯+N≥500→LiNGAM；全类别→PC+chisq；否则 PC+fisherz），
  返回 `Selection(algorithm, indep_test, score_func, rationale)`。选择是
  **数据的纯函数、可复现、可被验证器重算** —— 有别于 Causal-Copilot
  把 LLM 塞进选择回路
- **离散适配的检验 / 打分**：PC/FCI 在全类别数据上自动用 chi-square
  CI 检验（而非 Fisher-Z），GES 用 BDeu —— 修掉「在类别数据上跑高斯
  检验」这个静默误用
- **bootstrap 每条边稳定度**：`n_bootstrap>0`（默认 0 关闭）对行重采样
  重跑同一算法，`annotations.confidence∈[0,1]` = 该边重现比例；真链边
  ≈1.0、伪边低（逮伪边）。子种子由 `random_state` 派生 → 可复现。
  这是 data-refit 量（诚实天花板：可复现但不能独立重导），故作为
  proposal 上的 confidence 元数据、不当已验证结论
- 全链路：confidence 经 `_to_annotation` 进 `Annotation.confidence` →
  `discovery_to_kernel_ast` 挂到每条 cause/bidirected 边 + 歧义边的
  `skeleton_confidence` + `discovery_metadata.{diagnostics,
  selection_rationale,indep_test,score_func,n_bootstrap}`；data-gap 报告
  在发现边描述里追加「自助法稳定度 X%」；MCP `themis_discover` 加
  `n_bootstrap` 透传
- 取舍声明：仅在 causal-learn 既有算法内扩（GES 白拿，未引 gcastle/
  tigramite 新库）；选择器是规则式确定性（LLM 只在 agent 侧提先验）；
  bootstrap 是诚实天花板不可独立重导
- 测试：`tests/test_discovery_smart_proposer.py` +21（诊断 / 选择理由 /
  小样本回退 / 离散 chisq+BDeu / GES 骨架 / bootstrap 稳定度+可复现+
  逮伪边 / kernel_ast confidence + metadata / gap 报告显示稳定度）；
  基线 2713→**2734**
- **算法知识库重构 + GRaSP（同 followup）**：把「每算法的 run / note /
  假设违反 / auto 适用性」从散在 4 个函数收敛成**单一 `AlgorithmSpec`
  注册表 `_ALGORITHMS`** —— 加算法 = 一个 runner + 一行 entry（借
  Causal-Copilot 的算法知识库思路，但**确定性规则、无 LLM**）。
  `_select_algorithm` / `_run_resolved` / `_detect_assumption_violations`
  / `_format_note` 全改成消费注册表的薄封装。借此加 **GRaSP**（Lam-
  Andrews-Ramsey 2022,permutation/score-based,常比 PC/GES 准;连续
  BIC_from_cov / 离散 BDeu）。auto 仍只在 pc/lingam 间选（ges/grasp/fci
  显式 opt-in,priority 表达:pc 恒 eligible@1、lingam 满足条件@10),行为
  完全不变。+6 测试；基线 2734→**2740**

**8.2 Sensitivity**：
- `e_value_for_risk_ratio(rr)`：VanderWeele & Ding 2017 closed form
- `e_value_from_ate_binary(ate, baseline_rate, ci_bound)`：从 ATE
  自动转 RR 再算 E-value
- 在 `dispatch.py` 的所有 4 个 estimator 路径尾巴自动调用
  `_attach_e_value_if_binary`，仅对 bool outcome 触发
- `numeric_estimate.sensitivity_analysis` 子 schema：e_value /
  e_value_ci_bound / risk_ratio / baseline_rate / outcome_sd / path / note
  （path + baseline_rate/outcome_sd 是转换输入，供验证器独立重导）
- **kernel `verify_e_value`**：像 OVB 一样对该块做第二次独立公式转写——
  从审计过的 headline ATE + 记录的转换输入重算 risk_ratio 与两个 E-value，
  篡改 e_value（把脆弱结果伪装稳健）被拒；补上"出数无独立复核"的契约空洞
- response_rendering 加专门 disclosure section + 4 档威胁水平模板
- F22 加入失败模式 taxonomy

板块 10 敏感性 0% → 30%；板块 12 因果发现 0% → 40%。

**整体加权覆盖**：从 Phase 6 启动时的 ~20% 跃升到 **50-60%**。

**时间实际**：Phase 8 整体（2 个子 slice）约 1 天落地。

---

## 最短版本

```text
Themis 已经从识别内核演化成全栈因果系统：
- 识别（M1）：backdoor / front-door 单+多 / IV basic+conditional+ADMG / NDE-NIE-CDE
- 估计（M2+Phase14）：backdoor / front-door / IV / mediation / dose-response 都能给数字 + CI 或结构化失败
- 敏感性（M3.1）：每个 binary outcome 自动带 VanderWeele E-value
- 发现（M3.2）：用户给 DataFrame 没图时 PC/FCI/LiNGAM 自动建图建议
- 诊断（Phase10-13）：data_gap_report + bounds-first + dose-response 数据规格
- 全程 verifier 松弛 / 严格审，每步带 derivation

12 板块加权覆盖 ~65-75%。
但仍不是完整世界建模系统；
完整反事实（Layer 3 全套）、动作级时序、自动语料建模仍在后续 Phase。
```

---

### Phase 4 down-payment + 双面 bridge 打磨（2026-04-25）

把 Phase 7+8 落地后暴露的输入/输出 bridge 缺口补齐，把 Phase 4 上游层
从 prompt-only 推到端到端可跑。

**输出 bridge：response_rendering.md v3 + v3.1**
- 补 numeric_estimate 渲染（per-method 模板）/ IV trigger via numeric
  path / bidirected provenance / numerically_solved + 仍开 requests /
  schema mismatch / E-value 中英 band 对齐 / structure-group / framing_notes dedup
- 4 个 blind 子代理在 cases 25-28 输出端 blind 验证：v3 关闭 10 个 gap
- `themis/estimation/sensitivity.py` note 嵌入中文 band 与 prompt 表对齐

**Phase 4 上游层端到端**
- `merge_edge_extractions` / `merge_edges_into_program`：对称变量合并；
  ADMG cause+bidirected 共存（修了一个真 bug，refusal vs edge 互斥）；
  保留 atom 上的 `time_index`（吃下 case 14 V-set）
- `compose_program(base, vars?, edges?)` 端到端胶水
- annotation schema 加 `evidence`（A2 一直在 emit，schema 之前拒收）
- e2e blind 压测：3 个子代理跑 A1+A5+A2，合成 + run，3/3 通过：
  case 14 (temporal `cause=true`) / 16 (selection `cause=false`) /
  21 (IV ADMG `needs_investigation`)

**kernel V-set 放松**（charter-free，小修）
- `graph_projection.project()` 为带 VariableDeclaration 的 query 原子
  加孤立节点。Refusal-only 图（case 16）正确返回 `cause=false (no path)`
  而非 SemanticError；未声明的原子仍被拒，V-set 严格性 6 测全过。

**MCP server**（task #35）
- `themis/mcp/server.py` FastMCP 包装：5 个 kernel / audit 入口（run /
  apply_patch_and_run / verify / verify_data_gap_report / estimate）+ 1 个
  catalog tool；7 个 prompts + 5 个 schema 作为 resources；不调 LLM
- README + 8 个 in-process 测试

**A2 prompt 小补**：refusal `suggested_confounder` →
`pattern: confounder|collider|reverse_causation|coincidence` +
`suggested_node`（按 pattern 解释）

**DoWhy parity flake 修**：mediator 选择非确定 → 只断言 DoWhy 返回
identification，不锁选哪个

**测试**：1015 passed / 143 skipped（本轮 +28）；0 fail；0 known flake。

---

### Phase 9 §T9.1 单源转移识别（2026-04-25 落地，板块 9: 0% → 25-30%）

**真实压力来源**：W0 跑步 case 闭环后用户反问 "文献是 35-50 男性 RCT，
我是 28 女 BMI 正常，0.55 这个数字适不适用"。这是 transportability
问题——板块 9，之前 0% 覆盖。

**charter**: PHASE_9_TRANSPORT_CHARTER.md（slice 内立项 + 7 sub-slice）

**理论基础**：Bareinboim & Pearl 2014 "A General Algorithm for Deciding
Transportability" Theorem 1（充分条件）：Z is S-admissible iff Z
d-separates {S nodes} from Y in G_{\\bar{X}}.

**OSS 现状检查**：DoWhy / EconML / causal-learn 都没有 Bareinboim
selection-diagram transportability 的 production 实现；只有学术论文 +
Causal Fusion (Columbia) web demo。Themis 做这块属于 **Python OSS 内
首发**。自家写，不 vendor。

**7 sub-slice 落地状态**：

| Slice | 内容 | 状态 |
|---|---|---|
| S.T9.1.1 | schema (selectionNodeStatement / population / target_population) | ✅ |
| S.T9.1.2 | types + parser + transport_runtime_gate | ✅ |
| S.T9.1.3 | identify (s_admissibility_check / transport_formula / identify_via_transport) + scheduler dispatch hook | ✅ |
| S.T9.1.4 | verifier T9-1 / T9-2 独立审 + 字节码独立性钉死 | ✅ |
| S.T9.1.5 | eval case 29 (跑步瘦肚子 transport) + 4 e2e 测试 | ✅ |
| S.T9.1.6 | A1 §3f population mismatch + response_rendering transport disclosure | ✅ |
| S.T9.1.7 | docs sync (本节 + COVERAGE_MAP + failure_modes F25) | ✅ |

**端到端**：跑步 case 现在跑通：

```
NL: "meta-analysis 是 35-50 男性，我 28 女 BMI 正常，能套吗"
↓ (A1 §3f)
kernel_ast: 3 selection_nodes (S_age/S_sex/S_bmi) + effect query w/ target_population=user
↓ (themis.run + _dispatch_transport)
status=structurally_solved, formula=P*(belly_fat_loss|do(running)) = Σ_{age,sex,bmi} P(...|...,Z) · P*(Z)
↓ (themis.verify)
T9-1 重跑 S-admissibility ✓; T9-2 审 formula 形状 ✓
↓ (response_rendering Transport disclosure)
"结构上可识别，调整集 = {age,sex,bmi}；要给数字还需要源人群分层 P 和你的 P*(Z)"
```

**显式 out-of-scope**（charter §4 已划清，按需另立 fragment）：
- §T9.2 数值估计（IPSW / TMLE-transport）
- §T9.3 latent S（不可观测的人群差异）
- 多源 transport（Bareinboim 2014 §5）
- 自动从 dataset 检测人群差异（discovery 范畴）

**测试**：1064 passed / 143 skipped（+49 from baseline 1015）；0 fail；
0 known flake。新增：
- 15 schema/types/gate (test_phase9_transport_schema)
- 13 transport primitive (test_runtime/test_transport)
- 7 verifier (test_verifier/test_transport_rules)
- 4 case 29 e2e (test_e2e/test_case_29_transport)

**新失败模式**：F25 transport / population mismatch（failure_modes.md）

**加权覆盖跃升**：约 55-65% → **60-70%**。第一次给板块 9 一个真实的
非零数字。

### Phase 10 数据缺口诊断器（2026-04-26 落地，VISION 定位收紧的输出 (2)）

**真实压力来源**：2026-04-26 用户战略反思——"构建量化的因果关系太难
了，主要是缺乏数据"。这是因果推理学科根本天花板，不是 Themis 工程
问题。结论：把 Themis 重新定位为**因果断言验证器 + 数据缺口诊断
器**，不再追求"任何因果问题都能给数字"——卖给用户的是"告诉你这问
题能不能算 + 不能算缺什么数据"。这是 DoWhy / EconML / ChatGPT 都不
做的独占生态位。

**VISION 同步**：VISION.md 加新节"定位收紧 (2026-04-26)"——两段式
输出契约：(1) 全面检查（已有）+ (2) **数据缺口报告（新）**。
"当前原则"加第 5 条："数据缺口诊断 ≥ 数值估计"。

**charter**: PHASE_10_DATA_GAP_REPORT_CHARTER.md（7 sub-slice）

**理论基础**：不需要新理论 fragment——所有信号都在现有 derivation /
investigation_request / framing_note / extensions 里，Phase 10 只是
**结构化聚合 + 转换为 actionable 数据需求**。

**OSS 现状检查**：无同类。流行病学有 Hernan "What If" 第 II 部分讲
study design recommendation，但都是教科书，没有工程实现。Themis 做
这块属于**全 OSS 内首发**。

**7 sub-slice 落地状态**：

| Slice | 内容 | 状态 |
|---|---|---|
| S.10.1 | schema (`data_gap_report` / `dataGap` $def / 8 gap_kind / 3 severity / 4 ref_kind / derivation step `success`) | ✅ |
| S.10.2 | types (`DataGap` / `DataGapReport` dataclass + `DerivationStep.success` + result_orchestrator 序列化) | ✅ |
| S.10.3 | generator (`themis/output/data_gap_report.py` 8 + 1 classifier 分支 + severity 排序 + scheduler `_attach_data_gap_report` 挂载) | ✅ |
| S.10.4 | verifier T10-1 / T10-2 / T10-3 + byte-code 独立性钉死 (forbidden import + 独立 failure-rule 注册表) | ✅ |
| S.10.5 | 5 e2e gap_kind 全覆盖 + multi-gap 排序 + `themis.verify` round-trip | ✅ |
| S.10.6 | response_rendering v3.2 加 §"Data gap report rendering" 8 中文模板 + severity 排序 + multi-gap 措辞 + "禁止吞 gap" 硬规则 | ✅ |
| S.10.7 | docs sync（本节 + COVERAGE_MAP + failure_modes F26 + VISION 已在定位收紧节落地） | ✅ |

**端到端**：missing_parameter 案例闭环：

```
NL: "diet_control 干预下 waist_reduced 的 ATE"
↓ (themis.run)
status=needs_investigation, derivation=identify_via_backdoor (success=true),
investigation_requests=[{group=parameter, target=P(waist_reduced=True|...)}]
↓ (_attach_data_gap_report)
data_gap_report:
  summary: 缺概率分布 P(waist_reduced=True|...)
  gaps: [{kind=missing_distribution, severity=blocking, signature=conditional,
          required_data={data_type=ipd}, alternative_paths=[Balke-Pearl bounds]}]
  actionable_next_steps: [补 ... → 可给点估计, 或：接受 bounds]
↓ (themis.verify → T10-1/2/3)
T10-1 provenance ref ✓; T10-2 失败 step + 参数 request 全覆盖 ✓; T10-3 kind 一致性 ✓
↓ (response_rendering §Data gap report rendering)
"识别上没问题，但要给点估计还缺一个条件分布 P(...)，类型需要 IPD..."
```

**显式 out-of-scope**（charter §4 已划清）：
- 任何 I/O / API 调用（**绝对禁止**——生成器是纯 reasoning，需要外部
  数据是 Phase 11+ KB 接入的事）
- 样本量精确计算（statistical power）—— `min_sample_size` 字段允许
  填，但生成器自己不算
- 自动 KB 查询填补 gap → Phase 11+
- 多 gap 之间的优先级排序算法（按 severity + derivation order 已够）
- 可视化（DAG with red gap edges）

**测试**：1168 passed / 144 skipped（+104 from baseline 1064）；0 fail；
0 known flake。新增：
- 33 schema (test_output/test_phase10_data_gap_schema)
- 17 types (test_output/test_phase10_data_gap_types)
- 24 generator (test_output/test_phase10_data_gap_generator)
- 25 T10 verifier (test_verifier/test_data_gap_rules)
- 5 + 1 e2e gap_kinds (test_e2e/test_phase10_gap_kinds)

**新失败模式**：F26 silent data-gap suppression（failure_modes.md）

**加权覆盖**：板块覆盖率不变（Phase 10 不在 12 板块内），但 Themis
的产品定位重大跃迁——从"全板块编排器"扩展为"全板块编排器 + 数据
缺口诊断器"。这是 VISION 写明的**独占生态位**第一次有可交付实现。

---

## Phase 11.1 prompt-only 闭环 (2026-04-26 → 2026-04-27, S.11.1.1-3)

新增 `themis/prompts/gap_to_action.md` —— LLM 拿到 `data_gap_report` 后
按三个原则（结构可修？数据 vs 用户选？dtype 匹配？）自主决策下一步动
作（autonomous fetch / ask user / 终止），不再编造。MCP 注册 + 子 agent
真测找到并修了 transport 对偶 gap、prompt 的 schema 不匹配漏洞、
literature numeric 缺渲染模板等问题。

S.11.1.2-3 prompt elegance pass：`gap_to_action.md` / `response_rendering.md`
/ `nl_to_kernel_ast.md` 三个最累 prompt 从枚举换原则 + worked example，
2255→1652 行 (-27%)。子 agent 真测每次都找出 ~3 个真洞已立即修复。

零代码改动：所有挂 Themis MCP 的 LLM 客户端读到这份 prompt 即可。

## Phase 11.2 KB adapter 契约 (2026-04-27, S.11.2.1-7)

`themis/kb/` package 落地：

- **schemas.py**: `KBQuery` / `KBResult` / `KBProvenance` 数据类 + 7 个
  `KBQueryKind` (映射自 gap_kind) + 6 个 GRADE-style `KBConfidenceGrade`
  + JSON dict 双向转换
- **contract.py**: `KBAdapter` ABC + `KBRegistry` 客户端容器
- **translator.py**: `gap_to_kb_query()` + `kb_results_to_bundle()` 纯
  函数；3 个 gap_kind 不可 KB-fixable 时返回 None
- **cache.py**: `KBCache` (SQLite, 无 TTL, 可缓存负结果)
- **adapters/websearch_proxy.py**: reference adapter 包装客户端 search_fn
- **MCP 暴露**: 2 个 schema 资源 + 1 个新 prompt (`kb_lookup.md`)
- **关键架构边界**：Themis 自己不发任何网络请求；adapter 实例化 + 执行
  在客户端 / 第三方 repo（详见 `PHASE_11_2_KB_ADAPTER_CHARTER.md` §1）

子 agent 真测找到一个 pre-existing bug：`SelectionNode` 漏在
`_statement_to_dict` 里，让任何 transport 程序过不了 `apply_patch_and_run`
—— 已修复并加 transport 全闭环 e2e 回归测试。

**测试**：1266 passed / 144 skipped（+95 from 1171）；0 fail。

**显式 out-of-scope（已划清）**：
- ❌ 真实 PrimeKG / SciGraph / SemMedDB adapter 进 themis 主仓 → 必须
  sibling repo 形态（详见 `project_kb_adapter_invariants.md` 记忆）
- ❌ Themis 内置任何 HTTP client / 数据库 driver
- ❌ 跨 KB 冲突解决（S.11.7 元基础设施扩展）
- ❌ async adapter（先做同步契约）

## Phase 12 bounds-first (2026-04-27, S.12.1-6)

兑现 Phase 10 的"alternative_paths 接受 bounds"承诺 —— 之前是空话，
现在 kernel 真在算 bounds。

- **types + schema**: `BoundsMethod` enum (manski_natural / balke_pearl_iv /
  frontdoor_partial / manski_tamer_monotonicity) + `BoundsResult` 数据类
  + `QueryResult.bounds_result` 字段 + JSON schema $def
- **themis/output/bounds.py**: `attempt_manski_natural`（无假设，binary
  outcome 自然界限）+ `attempt_balke_pearl_iv`（Pearl 1995 §3 / BP 1997，
  binary 三元组 + IV1/IV2/IV3）
- **scheduler `_attach_bounds_result`**: identify 失败时自动尝试；BP 优先
  Manski 兜底；轻量 IV 检测（程序图里 Z→X 且无 Z→Y 且 Z 是 bool → 取
  作 IV）
- **response_rendering.md**: 新 §"Bounds rendering"（placement / per-method
  shape / uninformative-bounds 反模式 / 不要伪装界限有用）
- **subagent 真测**找到 2 真 bug，都已修：
  - `unidentifiable_no_admissible_set` 在 ADMG 不可识别 effect query 漏
    发（`query:effect_admg` prefix 不被 classifier 接 → 已扩展前缀列表）
  - BP-IV 在用户给 IV-shape 但 kernel 没跑 IV identification 时不触发
    （lightweight structural 检测补上）

测试：1335 passed / 144 skipped（+~80 Phase 12 新增）；0 fail。

### Phase 12 followup (2026-04-27 同日，9 场景真测驱动)

`themis.run` 跑 9 个真实场景（W0 跑步 / sleep+bidirected / 非 binary BP /
mediation / transport / counterfactual / conditional effect / happy path /
apply_patch_and_run）逐个查 alt_paths × bounds_result × required_data 对齐，
找出 5 真 bug + 配套 UX/sample_size 补齐。8 commits：

- `57785c7` reconcile alt_paths：算出的 method 名替换静态 "Balke-Pearl"
- `2d8e731` `GapBlocks.INTERPRETATION` 新增；framing gap 不再谎称 block
  identification
- `1557289` blocking gap 没提 bounds 时 prepend 已计算结果（让
  actionable_next_steps 看得到）
- `4845746` 非 binary outcome 时 bounds attempt 返回 None → strip 静态
  bounds 承诺，不留空头支票
- `919f1b2` response_rendering：blocking 存在时 framing 折叠成一句话
  （subagent 之前提的 UX 改进）
- `8b100ea` 移除 alt_paths 里泄给用户的内部章节号 "§T9.2"
- `8d23b00` mediation NDE/NIE sample_size（2.5× simple ATE 启发）
- `670abf7` transport sample_size（target marginal + source conditional
  按 2^k strata 缩放）

测试：1350 passed / 144 skipped（+15 followup 新增）；0 fail。

显式 out-of-scope（仍未做，按真实压力）：
- 数值 bounds estimator（symbolic 已经够用作 validator 输出）
- Frontdoor partial / Manski-Tamer monotonicity 等更高级方法
- 非 binary outcome 的 bounds
- IV 路径 sample_size（gap 是结构性"找 IV 变量"，不是分布，无 n 可算）

**followup(2026-07-11)：Balke-Pearl 数值界强重导**。此前 `_audit_numeric_bounds`
只做元数据审计(方向/容许区间/width/CI 包含),**从不重导界值**——实测:把
lower_value 从 0.60 篡成 0.30(仍在区间内、width 一致、CI 包住)verify 全放过
(伪造成"假紧"区间掩盖不确定性=最可能的恶意伪造)。iter 130 验证器 docstring 本就
标注"16 linear combinations 待未来数值审计"——BP 数值估计器早已落地(`6894988`),
此审计逾期。修法:producer 记录经验 `P(X=x,Y=y|Z=z)` 表(`sufficient_statistics.
P_xyz`,8 数=LP 消费的充分统计量),验证器**本地独立转写 response-function LP**
(不 import 生产者)从表重导 [lo,hi] 核对 + 闭式查 P 有效性(每 Z 片和=1、非负)+
Balke-Pearl 工具不等式(eq 6);篡改单界被逮。**grid oracle**:验证器 LP == 生产者 LP
@200 随机可行表钉死独立转写正确。诚实天花板:整表+界一起自洽伪造逮不住(验证器无
DataFrame 重数表)。**取舍声明:只做 BP**(其界=8 表上的非平凡 LP,重导有真价值);
Manski 自然/tamer 的界=`[P(Y,X=x), +P(X≠x)]` 已被 width/range 不变量锚定,记其
2 个平凡统计量近乎循环、边际价值低,故留元数据审计。基线 2703→**2713**。

## Phase 13 dose-response diagnostic (2026-04-28 落地)

**真实压力来源**：用户问的不是二元 ATE，而是"X 让 Y 增加多少 / 关系图 /
从 A 到 B 怎么变"。这类问题不能再被静默压成 binary effect。

**交付**：

- 新 `GapKind.DOSE_RESPONSE_DATA_REQUIRED`
- `GapRequiredData` 扩展 sampling points / sampling_point_count /
  confounders_required / time_window / sutva_concerns
- data-gap classifier 能把 dose-response 问题转成可执行数据规格
- A1 prompt 新增 `dose_response_query` ambiguity
- response rendering 明确区分"诊断清单"与"真实画曲线"

**边界**：Phase 13 不估计曲线，只告诉用户画曲线需要什么数据和假设。
真实估计由 Phase 14 接手。

## Phase 14 dose-response estimator (2026-04-28 落地)

**定位变化**：`themis.estimate(...)` 从 binary treatment ATE 扩到连续 /
多剂量 treatment 的 dose-response curve。kernel 仍保持纯 JSON；估计层走
DataFrame 旁路。

**已落地 slice**：

- slice a：EconML `LinearDML` wrapper，输出 `dose_response_curve`
- slice b：`model='auto'|'linear'|'forest'`，`CausalForestDML` explicit opt-in
- slice c：typed `EstimatorFailure` + overlap pre-check
- slice b.2：`model='drlearner'`，LinearDRLearner + T 离散化，可恢复
  T-Y 非线性；`auto` 在样本量和采样点足够时选择 drlearner
- followup：verify roundtrip 与 model-string normalization 修复
- **followup(2026-07-10)：`verify_dose_response_curve` 曲线语义审计**。
  此前曲线数组(=dose-response 的答案)只走 numeric_backdoor_estimate 松弛
  元数据审计(只看 adapter 的 headline 末点),曲线本身除 JSON 形状外零复核
  ——实测参考点 effect 篡改成 99 / 某点 effect 篡改成 1e6(远超自身 CI) /
  x 挪出采样网格,verify 全放过。补上构造不变量审计(参考点 effect=0、每点
  effect∈自身CI、x 逐一匹配采样点、点数一致、区间不倒挂)接进 kernel effect
  分支。**诚实天花板**:曲线值是 EconML 黑盒拟合、无充分统计量,不能重导
  拟合值(与所有 data-refit 估计器同);逮得住破坏构造的篡改,逮不住"effect+CI
  一致伪造"(那需重跑拟合,超范围;有专门测试钉住此限制)

**当前边界**：

- 依赖 EconML / sklearn 等估计栈；缺依赖或数据契约不满足时返回结构化失败
- CATE / 自动 hyperparameter 搜索 / 多 outcome dose-response 仍不在当前范围
- 统计有效性依赖 overlap、样本量、模型设定；Themis 只承诺显式披露方法和失败原因

**当前全量测试**：1402 passed / 144 skipped, warning-clean。

## Phase 15 world-modeling pressure harness (2026-04-30 起步)

**定位**：不新增内核语义，不接 LLM。把已有 A1/A2/A5 prompt examples、
`themis.upstream.compose_program(...)`、`themis.run(...)`、`verify` /
`verify_data_gap_report` 串成可重复压测，先暴露上游世界建模真正卡点。

**当前脚本**：

```powershell
python scripts\run_015_world_modeling_pressure.py
```

**已固定的 5 个压力用例**：

- `exercise_waist_variable_merge`：narrative framing 能缩小 `running`
  的 gap，但 target `belly_fat_loss` 仍完整欠框定，且 effect 仍缺分布数据
- `late_sleep_predicate_drift`：question 用 `stays_up_late` /
  `feels_tired_next_morning`，narrative 用 `staying_up_late` /
  `cognitive_slowness`，导致补录无法复用 —— 暴露 predicate linking 缺口
- `late_sleep_predicate_links_rewrite_edges`：同一份已确认 predicate link
  bundle 能同步改写 A2 edge endpoints，避免边把旧谓词名重新带回图里
- `coffee_latent_edge_assoc`：A2 能抽出 bidirected latent edge，ADMG
  assoc query 现在经 `m_connection_witness` 返回结构解，并可被 verifier 复核
- `ice_cream_refusal_filters_edge`：A2 refusal 能过滤 A1 question-side
  naive direct edge，最终 cause query 返回 `false`，拒绝理由保留在
  `extensions.ambiguities`

**当前 followup**：

- `themis.upstream.diagnose_predicate_links(...)`：对 narrative extraction
  里未命中 base program 的 predicate 产出候选 link 诊断；只建议、不自动重写
- `themis.upstream.diagnose_edge_predicate_links(...)`：对 A2 edge /
  refusal endpoints 做同类候选诊断；去重后只输出待确认项
- `themis.upstream.apply_predicate_links(...)`：消费已确认的
  source -> target link bundle，重写 narrative variables 后再走既有 merge；
  多个 source 合到同一 target 时复用字段冲突检查
- `themis.upstream.apply_predicate_links_to_edges(...)`：同一 confirmed
  link bundle 可重写 A2 cause / bidirected endpoints 与 refusals，保证
  变量合并和边合并使用同一套 predicate 对齐
- `themis.upstream.compose_program(..., predicate_links=...)`：把 confirmed
  link bundle 作为统一入口，同时应用到 variables 和 edges，降低调用方漏改一侧的风险；
  link target 必须已存在于 base program variables，否则抛 `PredicateLinkError`
- 0.15 压测输出现在包含 `predicate_link_diagnostic`，能把
  `staying_up_late -> stays_up_late` 这种形态漂移高分暴露出来，同时把
  `cognitive_slowness` 这种低 lexical evidence 保持为待确认项
- exercise 压测也固定了低 lexical evidence 的 target link：
  `waist_reduced -> belly_fat_loss` 只作为候选出现；确认回注后不会新增
  predicate，`belly_fat_loss` 的 framing gaps 会缩小，但
  `missing_distribution` 仍保留
- late_sleep 压测现在还证明：确认 link 后不会新增 predicate，query 侧
  `stays_up_late` / `feels_tired_next_morning` 的 framing gaps 会按已补字段缩小
- narrative edge refusal 现在由 `apply_edge_refusals(...)` 在
  `compose_program(...)` 内先执行：只删除 exact directed `cause` match，
  不删除反向边或 bidirected；拒绝理由写回 `extensions.ambiguities`
- A2 的 `narrative_ambiguities` 现在由
  `merge_narrative_ambiguities_into_program(...)` 保留到最终 program 边界；
  coffee ADMG case 会同时保留 latent-common-cause ambiguity 与 refusal
  audit trail
- Phase 2.latent S4 的窄 runtime gate 已放开 `assoc`：ADMG 程序上的
  association 查询走 m-separation；`cause` / `probability` 仍保持 gate

**当前全量测试**：1420 passed / 144 skipped, warning-clean。

## Phase 2.latent §S3.b.2 — Tian / Shpitser ID（2026-05-06 落地）

**真实压力来源**：bow-arc 形 ADMG 案例（X ↔ Y 直接 latent confounder）当
backdoor / front-door / IV 全失败时落到 needs_investigation。c-component
分解 primitive 已经在 `structural_solver` 里了，闲置；hedge witness 形态
是 ADMG 不可识别中最常见的一种。Phase 2.latent charter §4.2 记的延后条件
（"实际案例逼出"）触发。

**交付**：

- `themis/runtime/c_factor.py`：Shpitser-Pearl ID 算法在 kernel identify
  query shape 上的 restriction（单 intervention / 单 target / 空 given）。
  覆盖递归 Lines 1-6：祖先收缩、后代排除、c-component split、hedge
  witness、Q[S] 乘积形式
- 新 derivation rule family：
  - `tian_c_decomposition`：声明性 c-decomposition step
  - `identify_via_tian`：terminal rule，结果 `StructuralResult(True)` +
    c-factor 公式
  - `tian_hedge_witness`：terminal rule，结果 `StructuralResult(False)` +
    hedge graph
- scheduler dispatch：ADMG 上 backdoor / front-door / IV 全失败后回退到
  Tian
- Line 7（递归符号 substitute under Q[S'] re-factorization）返回 None；
  scheduler 落到 `needs_investigation`，**不假声 unidentifiable**

**未包含**：

- Line 7 完整 ID*（递归 Q[S'] re-factorization）
- IDC（conditional ID）/ 多 intervention / 多 target / 非空 given
- ADMG 下的 cause / assoc / probability 查询（dispatch 路径仍需 ADMG-aware）

**Done 标志**：8 个测试覆盖正例（c-decomposition）+ 反例（hedge witness）
+ Line-7 fall-through。bow-arc 之前 `needs_investigation`，现在
`structurally_solved` value=False + `tian_hedge_witness` rule。

板块 2 ADMG 80% → ~85%。

---

## Phase 5 §T runtime 强制（2026-05-06 落地）

**真实压力来源**：Phase 5 §T 标"已落地"，但 verifier 的 T1 / T2 / T3
primitive 从未被 runtime 调用——意味着 kernel 程序声明 `X@t=1 cause
Y@t=0`（因果反向跑）会被 kernel 静默接受。这是一个真实的语义漏洞。

**交付**：

- `semantic_validator` 新增 `temporal_monotonicity` 检查：parse 时拒绝
  `CauseStatement` 当 `src.time_index > dst.time_index`。无 `time_index`
  的 atemporal endpoint 旁路（处于虚拟 atemporal slice，顺序不指定）
- T2_lag_bound verifier rule：从 `|lag| ≤ 1`（一阶 Markov 脚手架）放宽
  到 `lag ≥ 0`。真实案例——1 周糖 → 蛀牙、1 月训练 → 马拉松时间、多日
  压力 → 疲劳链——都需要 `lag > 1`。T2 现在与 T1 冗余（都强制非负），
  保留在 registry 让既有 derivation 引用 T2 仍能验证

**测试**：`tests/test_temporal_enforcement.py` 7 个新测试。负例：反向时间
被拒；正例：向前 / 同时 / 部分 atemporal 接受、多日 lag 和混合 lag 链
接受。既有 T2 unit test 更新到断言放宽。

---

## Web UI mode (a) + (b)（2026-05-06 落地）

**定位**：peripheral surface——给没有 agent / MCP 的非开发者用户一个
可点的探索入口。kernel 仍纯 JSON，不被这层污染。

**Mode (b) — paste-JSON 探索**（commit `f420a70`）：

- `python -m themis.web` → FastAPI `http://127.0.0.1:8000`
- 单页 UI 把 result envelope（explanation / ⚠ caveats /
  structural_result / numeric_result / bounds / data_gap_report /
  derivation）渲染成比 raw JSON 易读的形式
- POST `/api/run` / POST `/api/verify` / GET `/api/examples`（从
  `themis/prompts/examples/` 加载 worked NL→kernel_ast pairs）
- localhost-bound 默认；`--host 0.0.0.0` 局域网共享

**Mode (a) — LLM bridge**（commit `dfdf1c7`）：

- 中文问题 → LLM emit kernel_ast → `themis.run` → LLM render 中文回复
- `themis/web/llm_bridge.py`：包装 anthropic SDK，两个函数
  (`nl_to_kernel_ast` / `render_reply`) + e2e `ask()`
- POST `/api/ask` 返回 `{nl, kernel_ast, envelope, reply}`；失败返回
  400 + `{stage, error, message}` + 中间 artifacts（让 UI 能调试
  mid-pipeline 中断）
- `LLMBridgeError` 与 kernel 异常区分开，API 能正确归因失败 stage

**未包含**：

- 公网部署（kernel 自己不发网络请求；公网部署是客户端 / sibling repo
  的事）
- 鉴权 / rate limit / billing — 当前 demo 级别
- mode (a) 的 LLM provider 切换抽象（当前固定 anthropic）

**测试**：`tests/test_web_app.py`（6）+ `tests/test_web_llm_bridge.py`（13）。

---

## 下一步候选（按真实压力等待选）

- **真人测试** — 找不熟项目的人跑一遍 MCP / web UI（一直没做，是诚实
  的 gap）
- **样本量扩展** — sample_size 接到 mediation / IV / transport 路径
- **更多 gap_kind / 更深检测** — dtype mismatch / IV 强度不足 /
  propensity overlap / SUTVA 违反
- **bounds 扩展** — frontdoor partial / Manski-Tamer monotonicity /
  非 binary outcome / 数值层
- **A1/A2/歧义识别更广** — 输入诊断更准
- **V0-V5 + T10 verifier 更深规则** — 验证器更严
- **Tian Line 7** — 完整 ID* 递归（当前案例没逼出，但延后随时可立项）

**注**：Phase 11 母 charter §3 列的 S.11.3-S.11.7（PrimeKG / SciGraph /
SemMedDB / Wikidata / 冲突解决）**已废弃** — "LLM 怎么搜资料不关我们
的事"（2026-04-27 用户校正）。adapter 在客户端，Themis 不教 LLM 怎么
找数据。详见 `project_kb_adapter_invariants.md` 记忆。