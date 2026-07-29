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
3645 passed / 144 skipped, warning-clean
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