# Themis Core Status

> 更新时间：2026-08-12

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
4514 passed / 144 skipped, warning-clean
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
全量实测 `_explain_causation_zh` **零次调用**（`explain()` 只在 `run_trial_pack.py`
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