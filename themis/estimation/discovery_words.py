"""What a discovery run says about itself, as a table rather than as prose.

Every sentence the discovery layer owes a reader used to be written where
it was produced — an f-string in a violation check, a clause on an
algorithm's registry row, a rationale assembled by the selector. That made
the kernel the author of a reader's prose, and it made the kernel the
chooser of its language: the sentences were Chinese because whoever wrote
them was thinking in Chinese, and there was nowhere for the other language
to go. Six algorithms' notes and eight precondition failures sat in slots
typed ``str``, and a ``str`` has no room for a second language — so the
missing translations were not missing work, they were a missing slot.

So the sentences live here, keyed by a token, and a producer states WHICH
one plus this occasion's facts (:func:`themis.language.spelt`). The surface
that knows who is reading assembles it. That is the door
``query_result.schema.json``'s ``statedSentence`` describes and the reason
it exists: *prose is what a producer writes when structuring a sentence has
no door*.

Slots are named, never positional, because the two languages do not put the
same facts in the same order — which is the whole reason a sentence cannot
be an f-string.
"""
from __future__ import annotations

from enum import unique

from .. import language

#: The name this set answers to on an envelope.
VOCABULARY = "discovery_note"

NOTES: dict[str, language.Words] = {
    # --- what the run found ------------------------------------------------
    "found_this_many_edges": {
        "zh": "{source} {algorithm} 找到 {directed} 条有向边、"
              "{bidirected} 条双向边、{ambiguous} 条方向待定的边",
        "en": "{source} {algorithm} found {directed} directed, "
              "{bidirected} bidirected and {ambiguous} ambiguous edges",
    },
    "some_edges_have_no_direction": {
        "zh": "有 {count} 条边光靠观测数据定不了向"
              "——需要领域知识来给它们指方向",
        "en": "{count} edges cannot be oriented from observational data "
              "alone — domain knowledge has to point them",
    },

    # --- what the data looks like -----------------------------------------
    "the_sample_is_small_for_a_test": {
        "zh": "样本量 {n} 偏小；条件独立性检验的功效不足，"
              "给出的结构建议也相应地不那么可靠",
        "en": "a sample of {n} is small; conditional independence tests "
              "have little power here, so the suggested structure is "
              "correspondingly less reliable",
    },
    "no_column_is_continuous": {
        "zh": "没有连续列——LiNGAM 用不上；条件独立性检验"
              "应当用卡方而不是 Fisher-Z",
        "en": "no column is continuous, so LiNGAM does not apply and the "
              "independence test should be chi-square rather than Fisher-Z",
    },

    # --- preconditions measured and found wanting -------------------------
    "a_test_of_independence_needs_more_rows": {
        "zh": "样本量 {n} < 200——条件独立性检验的功效不足，"
              "既会多出伪边也会漏掉真边",
        "en": "a sample of {n} is under 200 — conditional independence "
              "tests have low power; expect both spurious edges and missed "
              "ones",
    },
    "a_score_needs_more_rows": {
        "zh": "样本量 {n} < 200——小样本下 BIC / BDeu 评分不稳定，"
              "返回的图不可靠",
        "en": "a sample of {n} is under 200 — BIC / BDeu scores are "
              "unstable that small, and the returned graph is unreliable",
    },
    "least_squares_needs_more_rows": {
        "zh": "样本量 {n} < 200——最小二乘的 Gram 矩阵噪声大，"
              "阈值上下的边基本是随机的",
        "en": "a sample of {n} is under 200 — the least-squares Gram matrix "
              "is noisy that small, and which edges land either side of the "
              "threshold is close to arbitrary",
    },
    "lingam_was_given_level_codes": {
        "zh": "列 {columns} 是水平编码的（布尔 / 离散），不是连续的"
              "——LiNGAM 靠的是连续 SEM 噪声项的非高斯性来定向，"
              "而水平编码没有这种噪声；返回的方向不带任何证据",
        "en": "the columns {columns} are level-coded (bool / discrete) "
              "rather than continuous — LiNGAM orients edges by the "
              "non-Gaussianity of a continuous SEM's noise, and a level code "
              "has no such noise, so the directions it returns carry no "
              "evidence",
    },
    "lingam_was_given_gaussian_data": {
        "zh": "数据看起来是高斯的（最大 |偏度| = {skew} < 0.5）；"
              "LiNGAM 的可识别性要求噪声非高斯——"
              "在高斯数据上，边的方向基本是任意的",
        "en": "the data look Gaussian (largest |skew| = {skew}, under 0.5); "
              "LiNGAM's identifiability needs non-Gaussian noise, and on "
              "Gaussian data an edge's direction is close to arbitrary",
    },
    "notears_was_given_level_codes": {
        "zh": "列 {columns} 是水平编码的（布尔 / 离散），不是连续的"
              "——NOTEARS 拟合的是线性 SCM 的最小二乘残差，"
              "水平编码上这个残差不对应任何机制；返回的权重不可解读",
        "en": "the columns {columns} are level-coded (bool / discrete) "
              "rather than continuous — NOTEARS fits the least-squares "
              "residual of a linear SCM, and on a level code that residual "
              "corresponds to no mechanism, so the weights cannot be read",
    },
    "notears_reads_the_variance_order": {
        "zh": "各列的边际方差相差 {spread} 倍——NOTEARS 会利用方差顺序"
              "（Reisach 等 2021）：方差恰好沿因果序上升时，"
              "光按方差排序就能复现这张图，而搜索会把功劳记在自己头上。"
              "请看每条边的尺度稳健性，不要只看边本身",
        "en": "the marginal variances differ by a factor of {spread} — "
              "NOTEARS exploits the variance order (Reisach et al. 2021): "
              "where the variances happen to rise along the causal order, "
              "sorting by variance alone reproduces the graph and the search "
              "takes the credit. Read the per-edge scale robustness, not "
              "only the edges",
    },

    # --- what each algorithm is, said once beside its registry row --------
    "pc_assumes_no_latent_confounder": {
        "zh": "PC 假设不存在潜混杂；若这一点不成立，考虑改用 FCI",
        "en": "PC assumes no latent confounder; where that fails, consider "
              "FCI instead",
    },
    "fci_allows_latent_confounders": {
        "zh": "FCI 容许潜混杂；圆端点表示方向待定",
        "en": "FCI allows latent confounders; a circle endpoint means the "
              "orientation is undetermined",
    },
    "ges_scores_an_equivalence_class": {
        "zh": "GES 是基于评分的（BIC/BDeu）；返回 CPDAG"
              "——定向只在等价类内部有效",
        "en": "GES is score-based (BIC / BDeu) and returns a CPDAG — an "
              "orientation holds only within the equivalence class",
    },
    "grasp_permutes_to_an_equivalence_class": {
        "zh": "GRaSP 是基于排列的（评分引导）；返回 CPDAG，"
              "在同一份数据上通常比 PC/GES 更准",
        "en": "GRaSP is permutation-based (score-guided) and returns a "
              "CPDAG, usually more accurate than PC / GES on the same data",
    },
    "lingam_orients_by_non_gaussian_noise": {
        "zh": "LiNGAM 假设线性非高斯噪声；数据接近高斯时信号很弱",
        "en": "LiNGAM assumes linear non-Gaussian noise; the signal is weak "
              "where the data are close to Gaussian",
    },
    "notears_optimises_a_smooth_constraint": {
        "zh": "NOTEARS 把无环性写成一条光滑等式来做连续优化；"
              "返回的是有权 DAG，每条边都有方向——这比 CPDAG 强，"
              "代价是假设线性 SCM。证书能重算，全局最优不能",
        "en": "NOTEARS writes acyclicity as one smooth equality and searches "
              "by continuous optimisation; it returns a weighted DAG with "
              "every edge oriented, which is a stronger claim than a CPDAG "
              "resting on the stronger assumption of a linear SCM. The "
              "certificate can be recomputed; global optimality cannot",
    },

    # --- why this algorithm and this test ---------------------------------
    "auto_chose_pc_because_everything_is_categorical": {
        "zh": "auto→PC：所有变量都是分类 / 离散的，"
              "所以用卡方条件独立性检验",
        "en": "auto → PC: every variable is categorical / discrete, so the "
              "chi-square independence test is used",
    },
    "auto_chose_pc_for_the_fewest_assumptions": {
        "zh": "auto→PC：数据是连续的，且非高斯性不明显"
              "（或者 N 低于 LiNGAM 的门槛）；PC 配 Fisher-Z 所需的"
              "参数假设最少",
        "en": "auto → PC: the data are continuous and not clearly "
              "non-Gaussian (or N is below LiNGAM's threshold); PC with "
              "Fisher-Z makes the fewest parametric assumptions",
    },
    "auto_chose_lingam": {
        "zh": "auto→LiNGAM：有 {fraction} 的连续变量通不过正态性检验，"
              "且 N={n}≥500，所以非高斯噪声足以把边完全定向",
        "en": "auto → LiNGAM: {fraction} of the continuous variables fail a "
              "normality test and N={n} is at least 500, so the "
              "non-Gaussian noise is enough to orient every edge",
    },
    "auto_fell_back_to_pc": {
        "zh": "auto→PC：没有算法声明自己适用，退回假设最少的那个",
        "en": "auto → PC: no algorithm declared itself applicable, so the "
              "one making the fewest assumptions is used",
    },
    "you_chose_this_algorithm": {
        "zh": "{algorithm} 是你指定的",
        "en": "{algorithm} was chosen by you",
    },
    "chi_square_because_the_data_are_categorical": {
        "zh": "分类数据，所以条件独立性检验用卡方",
        "en": "the data are categorical, so the chi-square independence test "
              "is used",
    },
    "bdeu_because_the_data_are_categorical": {
        "zh": "分类数据，所以评分函数用 BDeu",
        "en": "the data are categorical, so the BDeu score is used",
    },
}

language.declare(VOCABULARY, NOTES, language.BETWEEN_STATEMENTS,
                 tokens_are_ours=True)


def said(token: str, **facts) -> language.Statement:
    """One of the sentences above, with this occasion's facts for its holes.

    A thin name over :func:`themis.language.spelt` so that every producer in
    the discovery layer names the same vocabulary — the alternative is the
    vocabulary's name written out at twenty call sites, which is twenty
    places for it to be written wrong.
    """
    return language.spelt(VOCABULARY, token, **facts)


# ==============================================================================
# The two local searches beside the whole-graph ones, each a standalone
# artifact with a ``note`` of its own.
#
# A member rather than a row in the table above, and the difference is where
# the token comes from. ``NOTES`` is keyed on tokens an algorithm's registry
# row carries, so a producer holds the token and never the name; these are
# named at the site that states them, and a name written at a site is worth
# having. :class:`themis.language.Word` is the registry's other door for
# exactly that split.
#
# Both sets keep the sentence that says WHICH SEARCH RAN and WHICH TEST — not
# because the artifact lacks those fields, but because it has them without a
# gloss, and `test_vocabulary_reach` excuses them on the grounds that "the
# note gives a person the test by its published name". A published name is
# language-neutral the way a paper title is, so it travels as a fact; what is
# in a language is the sentence around it.
#
# **These members END, and the ones in NOTES above do not.** The two are the
# two seams :func:`themis.language.listed` and :func:`themis.language.spoken`
# already draw between them. A ``NOTES`` member goes into a SLOT of a larger
# sentence — the gap report puts every violation in one — and is joined by
# the item separator, where a full stop would land inside a comma-separated
# list. These are the whole sentences of a ``note`` array, joined by the gap
# that FOLLOWS a sentence's mark, so a member without its mark runs into the
# next one. The mark belongs to the sentence and the gap to the language,
# which is what ``FULL_STOP`` says about itself.
# ==============================================================================


@unique
class Blanket(language.Word, vocabulary="markov_blanket_says",
              between=language.BETWEEN_SENTENCES):
    """What a Markov-blanket run says about itself.

    Two members, and only the first is a summary. The second is the one
    thing about a blanket that nothing else on the artifact records and that
    a reader can act wrongly on: it is a screening set, and the children and
    spouses in it are exactly what must NOT be conditioned on afterwards.
    """

    FOUND_THIS_BLANKET = ("found_this_blanket", {
        "zh": "{target} 的马尔可夫毯是 {members}——{pool} 个候选里的 {size} 个，"
              "由 {search} 搜索得到，用 {test} 条件独立性检验，α={alpha}。",
        "en": "the Markov blanket of {target} is {members} — {size} of "
              "{pool} candidates, found by a {search} search using the "
              "{test} conditional-independence test at α={alpha}.",
    })
    A_SCREEN_AND_NOT_AN_ADJUSTMENT_SET = (
        "a_screen_and_not_an_adjustment_set", {
            "zh": "毯是局部屏障：父节点、子节点，以及子节点的另一些父节点"
                  "（配偶）。它是把变量筛到局部相关的那一小撮，用来建图；"
                  "它不是调整集——估计效应时拿子节点或配偶做条件会打开对撞"
                  "路径，把一个原本无偏的估计弄偏。",
            "en": "a blanket is a local screen: the parents, the children, "
                  "and the children's other parents (spouses). It narrows a "
                  "search down to what is locally relevant, and it is not an "
                  "adjustment set — conditioning on a child or a spouse when "
                  "estimating an effect opens a collider path, and biases an "
                  "estimate that was unbiased without it.",
        })


@unique
class Asked(language.Word, vocabulary="discovery_asks",
            between=language.BETWEEN_SENTENCES):
    """The one thing a discovery run puts TO a person rather than tells them.

    It sat in ``NOTES`` above, whose paragraph says in so many words that a
    member there does not END — it goes into a slot of a larger sentence.
    This one is a whole question and ends with a mark, so the table it was
    in held two kinds of thing and could declare only one seam for both.

    Its own sibling channel already had this right: the latent-lagged search
    asks the same question of the same reader and keeps it in a set whose
    members are whole sentences. What made the difference is that this one
    was written when the table was the only door.
    """

    WHICH_WAY_BETWEEN_THESE_TWO = ("which_way_between_these_two", {
        "zh": "{algorithm} 找到 {one} 和 {other} 之间存在因果关联，"
              "但从数据无法判定方向。你能根据领域知识告诉我方向吗？",
        "en": "{algorithm} found a causal association between {one} and "
              "{other} but cannot tell from the data which way it runs. "
              "Can domain knowledge settle the direction?",
    })


@unique
class Lagged(language.Word, vocabulary="lagged_discovery_says",
             between=language.BETWEEN_SENTENCES):
    """What a lagged-graph run says about itself.

    One summary and three facts about the procedure, none of which is on the
    artifact: what makes stage one's output checkable, what stage two
    conditions on and why that is what makes a p-value trustworthy under
    autocorrelation, and what the search did not look for at all.

    The last is the load-bearing one. A contemporaneous cause is neither
    searched for nor representable here, and where the data has one it can
    surface as a spurious lagged link — so a reader who does not know the
    scope can read a real finding out of a shape the method cannot express.
    """

    FOUND_THIS_MANY_LINKS = ("found_this_many_links", {
        "zh": "PCMCI（Runge 等 2019）在 {series} 条序列上找到 {detected} 条"
              "滞后因果链接，候选 {candidates} 条，τmax={max_lag}，α={alpha}。",
        "en": "PCMCI (Runge et al. 2019) found {detected} lagged causal "
              "links among {series} series out of {candidates} candidates, "
              "at τmax={max_lag} and α={alpha}.",
    })
    THE_CONDITION_SETS_ARE_CHECKABLE = (
        "the_condition_sets_are_checkable", {
            "zh": "第一阶段用 grow-shrink 跑到不动点来选条件集，它的输出本身"
                  "是可核的：任何非父节点在给定父集后都独立，任何父节点在"
                  "给定其余父节点后都相依。",
            "en": "stage one selects the conditioning sets by running "
                  "grow-shrink to a fixpoint, and what it returns is "
                  "checkable on its own terms: every non-parent is "
                  "independent given the parent set, and every parent "
                  "dependent given the rest of it.",
        })
    MCI_CONDITIONS_ON_BOTH_PARENT_SETS = (
        "mci_conditions_on_both_parent_sets", {
            "zh": "第二阶段是 MCI：检验一条链接时，同时以目标的父集**和驱动"
                  "变量自己的父集（按滞后平移）**为条件——这是自相关之下 p 值"
                  "还能被信任的原因。",
            "en": "stage two is MCI: a link is tested conditioning both on "
                  "the target's parents **and on the driver's own parents, "
                  "shifted by the lag** — which is what makes the p-value "
                  "trustworthy under autocorrelation.",
        })
    ONLY_LAGGED_LINKS = ("only_lagged_links", {
        "zh": "**只找滞后链接**：同期因果既不寻找也不表示。数据里若有同期"
              "因果，它可能以一条虚假的滞后链接出现。",
        "en": "**lagged links only**: contemporaneous causation is neither "
              "searched for nor representable. Where the data has one, it "
              "can surface here as a spurious lagged link.",
    })


@unique
class Confounded(language.Word, vocabulary="latent_lagged_discovery_says",
                 between=language.BETWEEN_SENTENCES):
    """What a lagged run that did NOT assume causal sufficiency says.

    Its sibling above learns the same graph under the assumption that every
    common cause was recorded, and says so in its scope. This one drops the
    assumption, so the sentences it owes a reader are different ones: what a
    mark that says nothing MEANS, why the search is over subsets, what makes
    an orientation checkable, and where the answer stops being as informative
    as it could be.

    The third and fourth are the two halves of one honesty. A reader shown a
    circle has to be able to tell "the data did not settle this" from "we did
    not look", and those read identically unless the second is written down.
    """

    FOUND_THIS_MANY_EDGES = ("found_this_many_edges", {
        "zh": "在 {series} 条序列上找到 {edges} 条滞后边：{causal} 条判定为"
              "因果、{confounded} 条判定为共有未观测成因、{unresolved} 条"
              "两者都可能。τmax={max_lag}，α={alpha}。",
        "en": "found {edges} lagged edges among {series} series: {causal} "
              "settled as causal, {confounded} as sharing an unrecorded "
              "cause, and {unresolved} that could be either. τmax={max_lag}, "
              "α={alpha}.",
    })
    A_CIRCLE_IS_THE_ANSWER = ("a_circle_is_the_answer", {
        "zh": "`X@t-τ o→ Y@t` 里那个圈**就是答案**，不是缺了一步："
              "它说的是「X 要么导致 Y，要么和 Y 共有一个没被记录下来的成因，"
              "这批数据分不出是哪一种」。假设所有共因都被记录下来，就是把"
              "第二种可能删掉——那正是它对面那个方法会凭空给出一条因果边的"
              "地方。",
        "en": "the circle in `X@t-τ o→ Y@t` **is** the answer rather than a "
              "step that is missing: it says X either causes Y or shares "
              "with Y a cause that was never recorded, and this data does "
              "not separate the two. Assuming every common cause WAS "
              "recorded deletes the second reading, which is exactly where "
              "the method next door produces a causal edge out of nothing.",
    })
    SUBSETS_RATHER_THAN_THE_WHOLE_SET = (
        "subsets_rather_than_the_whole_set", {
            "zh": "分离集是在**子集**里搜出来的，不是拿邻居全集去条件一次。"
                  "有未观测混杂时，条件集越大不等于检验越好——条件在一个对撞"
                  "结点上会**制造**出本来没有的相依。",
            "en": "a separating set is SEARCHED for among subsets rather "
                  "than taken to be the whole neighbourhood. With an "
                  "unrecorded confounder in play a larger conditioning set "
                  "is not a better test: conditioning on a collider CREATES "
                  "a dependence that was not there.",
        })
    EVERY_MARK_CARRIES_ITS_TRIPLE = ("every_mark_carries_its_triple", {
        "zh": "每一个不是圈的端点标记都由**一个三元组**定下来，而那个三元组"
              "就记在它旁边：核对一条定向是去看三条边，不是把搜索再跑一遍。",
        "en": "every endpoint mark that is not a circle was written by ONE "
              "triple, and that triple is recorded beside it: checking an "
              "orientation means looking at three edges, not re-running the "
              "search.",
    })
    SOUND_BUT_NOT_MAXIMALLY_INFORMATIVE = (
        "sound_but_not_maximally_informative", {
            "zh": "用到的是碰撞子、非碰撞子、祖先三条**局部**规则。Zhang 2008 "
                  "里那些依赖**路径**的规则没有用上，所以写下来的每个标记都是"
                  "对的，但有些圈在完整规则集下本可以定下来。**「没定下来」和"
                  "「没去看」在读者眼里长得一样，所以这里明说是后者。**",
            "en": "the collider, non-collider and ancestry rules used here "
                  "are the LOCAL ones. Zhang 2008's path-based rules are not "
                  "applied, so every mark written down is correct while some "
                  "circle would have been settled under the complete set. "
                  "**\"could not be settled\" and \"was not looked for\" "
                  "read the same to a reader, so this says which it is.**",
        })
    ONLY_LAGGED_LINKS = ("only_lagged_links", {
        "zh": "**只找滞后链接**：同期因果既不寻找也不表示——这同时也是每条边"
              "都能按时间定出一个箭头、上面那些定向才立得住的原因。",
        "en": "**lagged links only**: contemporaneous causation is neither "
              "searched for nor representable — which is also what makes "
              "every edge time-ordered, and therefore what the orientations "
              "above rest on.",
    })
    THE_TRIPLES_DID_NOT_AGREE = ("the_triples_did_not_agree", {
        "zh": "有 {count} 处，两个三元组对同一个端点给出了相反的标记。在总体"
              "上这不可能发生，所以它是这批样本在说本方法的某条前提没有成立"
              "——同期因果、因果平稳性、线性高斯、忠实性，任意一条。先写下来"
              "的那个标记留着（结果因此是确定的），另一个记在 `conflicts` 里。",
        "en": "in {count} places two triples asked for opposite marks on one "
              "endpoint. That cannot happen in the population, so it is this "
              "sample saying one of the method's premises did not hold — no "
              "contemporaneous causation, causal stationarity, "
              "linear-Gaussian, faithfulness, any of them. The mark written "
              "first is kept, which is what makes the answer deterministic, "
              "and the other is recorded under `conflicts`.",
    })
    WHICH_OF_THE_TWO_IS_IT = ("which_of_the_two_is_it", {
        "zh": "{driver} 和 {target} 之间有一条边，但这批数据分不出它是"
              "「{driver} 导致 {target}」还是「两者共有一个没被记录的成因」。"
              "领域知识能定下来吗？",
        "en": "there is an edge between {driver} and {target}, and this data "
              "cannot tell whether {driver} causes {target} or the two share "
              "a cause that was never recorded. Can domain knowledge settle "
              "it?",
    })
