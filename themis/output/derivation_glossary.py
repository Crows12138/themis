"""What each derivation step did, in the reader's words.

Every answered result carries a derivation: an ordered list of steps, each
naming the rule that produced it, each independently re-checkable. That
list is the complete answer to "how was this arrived at" — it is the only
channel that has one for every path, and until now no surface read it.

The report's 「怎么算出来的」 section was bound to the ROUTE block family,
and a route is written as a block only by the identification patterns that
produce one. Everything else — a d-separation verdict, the Tian-Pearl
formulas, abduction-action-prediction — records what it did in
``step.rule`` and nowhere else, so for six query kinds the section that
exists to say how the answer was reached said nothing at all. The
verification section made it plainer: it told the reader the derivation has
N steps and never said what they were.

This is the sibling of :mod:`themis.output.assumption_glossary`, and it is
here for the same reason and with the same shape: the kernel emits
snake_case ids, the reader needs sentences, and the translation is data
rather than a chain of ``if``\\ s. It has the same default too — a rule
nobody has glossed surfaces as its own name rather than vanishing, because
on a surface whose whole job is disclosure the safe direction of error is
to over-report.

The entries say what the step DID, not what the verifier re-checks about
it: the reader is following a recipe, not auditing an audit. Where a step
touched the data rather than only the graph or θ, the sentence says so —
that distinction is load-bearing and no other line of the report carries
it. The linear-SCM pair is the clearest case: one path uses coefficients
the caller declared and the other fits them by per-node OLS, and which one
happened was previously recorded only in an ``estimated_from_data`` flag
that nothing read.

A test holds this table equal to the rules producers actually write, found
by walking every ``DerivationStep(rule=...)`` in the package — so a new
step cannot be added without saying what it does.
"""
from __future__ import annotations

#: Rule id → what that step did. Ordered roughly as a derivation runs:
#: graph checks, identification terminals, symbolic formulas, then the
#: numeric evaluations that touch data.
SAYS: dict[str, str] = {
    # --- reading the graph ----------------------------------------------------
    "graph_is_dag": "确认因果图无环",
    "d_separated": "在图上确认两者在给定条件集下 d-分离（无关联通路）",
    "d_connected_via_open_path": "在图上找出一条打开的路径，两者因此相关",
    "cause_via_directed_path": "在图上找出一条从原因到结果的有向路径",
    "no_directed_path": "在图上确认不存在从原因到结果的有向路径",

    # --- recognising a pattern ------------------------------------------------
    "backdoor_criterion": "在图上验证调整集满足后门准则：阻断全部后门路径，且不含处理的后代",
    "joint_backdoor_criterion": "在图上验证这一组处理的联合调整集有效（广义调整准则）",
    "front_door_criterion": "在图上验证中介集满足前门准则",
    "iv_criterion_check": "在图上验证所选工具变量满足 IV 准则",
    "proximal_criterion": "在图上验证近端识别条件（Miao model f：两个 proxy 与未测混杂的关系）",
    "general_id_criterion": "用 general ID（Tian–Shpitser c-factor 分解）判定效应在 ADMG 上可点识别",
    "ctf_conjunction_criterion": "用 ID*/IDC* 判定这个反事实合取在图上可点识别",
    "s_admissibility_check": "重导 S-可容许性（Bareinboim 定理 1）：选择节点在给定集合下与结果无关",
    "longitudinal_sequential_exchangeability_check":
        "逐个时点重查顺序可交换性：每一步的处理在既往历史给定后可视为随机",
    "mediation_nde_nie_check": "验证 Pearl 2001 的四个条件，自然直接/间接效应可识别",
    "mediation_nde_nie_joint_check":
        "对整个中介集验证那四个条件（VanderWeele–Vansteelandt 2014 的向量版）",
    "mediation_cde_check": "验证受控直接效应 CDE(m) 的后门识别条件",
    "mediation_cde_joint_check": "验证把整个中介块固定住的联合 CDE 识别条件",
    "tian_c_decomposition": "在图上做 c-分解，把联合分布拆成各 c-分量的乘积",
    "tian_hedge_witness": "在图上找到一个 hedge —— 该效应非参数不可点识别",
    "idc_rule2_exchange": "做 IDC 规则 2 的观测-干预交换，把条件项挪进 do 里",

    # --- concluding identification --------------------------------------------
    "identify_via_backdoor": "据后门准则与相应公式，判定效应可识别",
    "identify_via_joint_backdoor": "据联合后门准则，判定这一组处理的联合效应可识别",
    "identify_via_front_door": "据前门准则与相应公式，判定效应可识别",
    "identify_via_iv": "据 IV 准则，判定效应可由工具变量识别",
    "identify_via_general_id": "据 general ID 的判定，效应可点识别",
    "identify_via_tian": "重导 ADMG 的 c-分量，把目标写成 c-factor 乘积（Tian）",
    "identify_via_idc": "独立重导条件效应 P(Y|do(X), Z) 的识别",
    "identify_via_gformula": "据顺序可交换性，判定时变策略对比可由 g-formula 识别",
    "identify_via_mediation": "判定至少一种中介分解（NDE/NIE 或 CDE）可识别",
    "identify_via_mediation_joint": "判定中介集的联合分解可识别",
    "identify_via_transport": "据 S-可容许性与迁移公式，判定结论可迁移到目标总体",
    "id_star_identification": "用 ID* 导出这个反事实量的识别式",

    # --- writing the estimand down --------------------------------------------
    "backdoor_adjustment_formula": "写下后门调整公式：在调整集的每一层内算效应，再按各层占比加权",
    "front_door_adjustment_formula": "写下前门调整公式：处理→中介与中介→结果两段相乘，再对处理求和",
    "tian_formula_ast": "写下 Tian 分解导出的识别式",
    "idc_formula_ast": "写下 IDC 导出的条件效应识别式",
    "transport_formula": "写下 Bareinboim 迁移公式：源总体的条件效应，按目标总体的协变量分布重新加权",
    "transport_formula_ast": "写下迁移公式的具体表达式",

    # --- putting numbers in ---------------------------------------------------
    "formula_evaluation": "把 θ 代入识别公式求值",
    "causation_probability_bounds":
        "从 θ 求 PN/PS/PNS：两个干预风险都拿得到时用 Tian-Pearl(2000) 公式，"
        "拿不到而图上有工具变量时改在响应函数多面体上求解",
    "counterfactual_cell_bounds":
        "从 θ 解出这一格反事实的可识别区间：干预风险拿得到时用一条一致性恒等式，"
        "拿不到而图上有工具变量时改在响应函数多面体上求解",
    "scm_abduction_action_prediction":
        "按你声明的结构方程系数：从该个体的观测值反推它自己的外生扰动（abduction）、"
        "施加干预（action）、再沿方程重算目标（prediction）",
    "iv_wald_numeric_evaluate": "按工具变量的条件集分层，逐层求 Wald 比",
    "mediation_numeric_evaluate": "求出各条中介分解量（NDE / NIE / CDE）",
    "numeric_result": "把上一步算出的数收成本次查询的答案",

    # --- estimating from data -------------------------------------------------
    "numeric_backdoor_estimate": "在数据上按后门公式求平均因果效应",
    "numeric_joint_backdoor_estimate": "在数据上求这一组处理的联合效应，以及它们之间的交互",
    "numeric_frontdoor_estimate": "在数据上按前门公式求平均因果效应",
    "numeric_iv_estimate": "在数据上求工具变量估计（Wald 比 / 两阶段最小二乘）",
    "numeric_iv_overid_estimate": "在数据上做过度识别的 2SLS 估计（工具多于内生变量）",
    "numeric_general_id_estimate": "在数据上按 general ID 导出的估计量逐层求值",
    "numeric_proximal_estimate": "在数据上用近端矩阵求逆（Miao 2018）求效应",
    "numeric_measurement_correction_estimate": "先用混淆矩阵校正测量误差，再求效应",
    "numeric_causation_estimate": "在数据上按 Tian-Pearl 公式求 PN/PS/PNS",
    # Two solvers stand behind this one rule — the consistency identity, and
    # the response-function program when an instrument is all there is — so
    # the sentence names what the rule does and leaves which route to the
    # licence that exists to say it.
    "numeric_counterfactual_cell_estimate":
        "在数据上重算这一格反事实（并用自助法给出抽样区间）",
    "numeric_ctf_conjunction_estimate": "在数据上按 ID*/IDC* 导出的式子求这个反事实合取",
    "numeric_scm_counterfactual_estimate":
        "结构方程的系数没有声明，改由每个节点的 OLS 从数据拟合，再做"
        "反推扰动-施加干预-沿方程重算",
}


def describe(rule) -> str:
    """What that step did, or the rule's own name.

    An unglossed rule surfaces as its id rather than as silence: this is a
    disclosure surface, and dropping a step the answer actually rests on is
    worse than printing a name the reader has to look up. The default is a
    safety net for a rule added after this file, not a place to leave one —
    a test refuses a producer-written rule that has no sentence here.
    """
    said = SAYS.get(str(rule))
    return said if said is not None else f"`{rule}`"
