# Themis Core Status

> 更新时间：2026-05-07

这份文档只回答一件事：

**当前 Themis 核心到底完成到了什么程度。**

它不是愿景文档，也不是长期路线图。  
长期目标看 [VISION.md](VISION.md)，阶段路线看
[ROADMAP.md](ROADMAP.md)，上游建模层看
[WORLD_MODELING.md](WORLD_MODELING.md)。

---

## 当前快照（2026-05-07）

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
3156 passed / 144 skipped, warning-clean
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
（单调包络）与 Balke-Pearl（16 型响应函数）仍是二值处理构造故推迟·多层**对比**界
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
X+Y 都给→`combined_misclassification_deferred` 拒；发 measurement_correction 块
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
