"""Why the estimation layer refused a REQUEST, as a table rather than as prose.

Five modules here answer a caller who handed in something the layer cannot
work with — a frame, a graph, an answer to a question it asked, a panel
with a time column. That is a different channel from
:mod:`themis.refusals`, which is about a quantity the DATA does not
identify and reaches the reader through the envelope; these never get an
envelope, because there is no result to put one on. They leave as
exceptions, and until this table existed every one of the thirty-three was
an f-string at its own raise site, in English.

**The cost of having a table was a third copy of the carrier.** Both
packages that already refuse this way wrote out the same twenty-line
exception class, and the second one's docstring gives the argument for
writing it once — four exception classes in one package would otherwise be
four copies. A layer with five exception classes was looking at a fifth
through eighth copy, and writing the sentence at the site is what that
made cheapest. The carrier is :class:`themis.language.Voiced` now, and
what is left here is the part that was always this layer's: the sentences.

**One vocabulary, five doors.** A caller catches the CHANNEL — the data
contract, the orientation compiler, the lagged design — and reads the
SPECIES off the exception, which is the arrangement ``themis.upstream``
already has. Keying the vocabulary on the catch channel instead would put
"this name is not a column in the data" in two tables, said twice, once
for the Markov blanket and once for the panel; it is one sentence and the
path is the slot.

Where these END is where an exception message ends: nowhere. They are
rendered alone into ``str(exc)`` rather than joined into a paragraph, so
they carry no terminal mark — the same convention the two vocabularies on
this channel one layer up and one layer down follow.
"""
from __future__ import annotations

from enum import unique

from .. import language


@unique
class Refuses(language.Word, vocabulary="estimation_refusal"):
    """What was wrong with the request.

    Grouped by what the caller handed in rather than by which module
    caught it: the frame, a name that is not in it, a set of columns the
    statistic cannot take, a graph, an answer, a panel. Two of the groups
    are read by more than one module, which is the whole reason for one
    table.
    """

    # --- the frame itself -----------------------------------------------
    DATA_IS_NOT_A_FRAME = ("data_is_not_a_frame", {
        "zh": "数值估计要的是一个 pandas DataFrame，收到的是 {got}",
        "en": "numerical estimation takes a pandas DataFrame; got {got}",
    })
    COLUMNS_ARE_MISSING = ("columns_are_missing", {
        "zh": "这次估计要用的列 {columns} 不在数据里",
        "en": "the columns this estimate needs, {columns}, are not in the "
              "data",
    })
    SAMPLE_IS_TOO_SMALL = ("sample_is_too_small", {
        "zh": "只有 {rows} 行，低于数值估计的下限 {minimum} 行——低于这个数，"
              "算出来的不是一个估计，是这几行的算术",
        "en": "{rows} rows is below the {minimum} numerical estimation "
              "needs — under that, what comes out is not an estimate but "
              "the arithmetic of those rows",
    })

    # --- one column of it -----------------------------------------------
    COLUMN_HAS_GAPS = ("column_has_gaps", {
        "zh": "列 {column} 有缺失值；这一版契约不接受缺失——先决定那些行是"
              "删掉还是填补，那是一个因果判断，不该由估计量替你做",
        "en": "column {column} has missing values, and this version of the "
              "contract does not take them — decide whether those rows are "
              "dropped or filled first, which is a causal judgement and not "
              "the estimator's to make for you",
    })
    PRESENCE_COLUMN_HAS_GAPS = ("presence_column_has_gaps", {
        "zh": "列 {column} 是用来分组的（比如簇 id），可它有缺失值；"
              "缺一个 id 的行不属于任何一组，也不能自成一组",
        "en": "column {column} groups the rows (a cluster id, say) and has "
              "missing values; a row with no id belongs to no group and "
              "cannot be a group of its own",
    })
    DECLARED_BOOL_HAS_OTHER_VALUES = ("declared_bool_has_other_values", {
        "zh": "列 {column} 声明为二值，但它还有 {values} 这些值",
        "en": "column {column} is declared boolean and also holds {values}",
    })
    DECLARED_CONTINUOUS_IS_NOT_NUMERIC = (
        "declared_continuous_is_not_numeric", {
            "zh": "列 {column} 声明为连续，而它的 dtype 是 {dtype}，不是数值",
            "en": "column {column} is declared continuous and its dtype is "
                  "{dtype}, which is not numeric",
        })
    LABELS_WITH_NO_DECLARED_ORDER = ("labels_with_no_declared_order", {
        "zh": "列 {column} 装的是标签（{dtype}），而程序没有为它声明 domain，"
              "所以没有一个顺序可以把这些标签放上去。把这个变量的 `domain` "
              "（它的档位，按你要的顺序）写出来，这一列原样就能用",
        "en": "column {column} holds labels ({dtype}) and the program "
              "declares no domain for it, so there is no order to place "
              "them on. Declare the variable's `domain` — its levels, in "
              "the order you mean — and the column is usable as it stands",
    })
    LEVEL_COLUMN_READ_AS_A_NUMBER = ("level_column_read_as_a_number", {
        "zh": "列 {column} 声明为 nominal（{levels} 这几档之间没有大小之分），"
              "而这个估计量要把它当成一个数来读：处理列、结局列、工具变量都"
              "必须是能比大小的量。没有大小之分的列只能进调整集。如果它本来"
              "就有大小（比如剂量档），把 scale 改成 discrete；如果它确实是"
              "分类而你要比的是其中两档，把那两档做成一个二值列，其余行不参与"
              "这次对比",
        "en": "column {column} is declared nominal — its levels {levels} "
              "have no greater and lesser — and this estimator reads it as "
              "a number: a treatment, an outcome and an instrument all have "
              "to be quantities. A column with no order can only enter an "
              "adjustment set. If it does have an order (dose bands, say), "
              "declare `scale: \"discrete\"`; if it really is categorical "
              "and the contrast you want is between two of its levels, make "
              "those two a binary column and leave the other rows out of it",
    })

    OUTSIDE_DECLARED_DOMAIN = ("outside_declared_domain", {
        "zh": "列 {column} 里出现了 {extra}，而程序给它声明的取值范围 {domain} "
              "里没有这些值；带标签的列只能落在它声明过的那些档上",
        "en": "column {column} holds {extra}, which the program's declared "
              "domain {domain} does not list; a labelled column can only be "
              "placed on the levels it was declared with",
    })
    LEVEL_NAMED_BY_LABEL = ("level_named_by_label", {
        "zh": "列 {column} 带的是标签，要放进模型必须先编码成声明域 {domain} "
              "里的位置；而程序又在用标签 {named} 称呼它的档（比如查询里的"
              "干预值）。编码之后数据说的是位置、程序说的还是标签，两边对"
              "不上，每一条臂都会是空的——那看起来会像数据不够，而不是像"
              "编码不一致。改法：把这一列按 {domain} 的顺序自己编成 {codes}，"
              "domain 也声明成 {codes}，程序里那些档改用对应的数",
        "en": "column {column} carries labels, so entering a model means "
              "coding it to positions in the declared domain {domain} — and "
              "the program also names its levels by label ({named}), an "
              "intervention value for instance. Coded, the data would speak "
              "positions while the programme still speaks labels; no arm "
              "would match, and that reads as too little data rather than as "
              "two encodings disagreeing. Supply the column already coded to "
              "{codes} in the order {domain} declares, declare the domain as "
              "{codes}, and name those numbers in the programme",
    })

    # --- a column that is not there --------------------------------------
    NOT_A_COLUMN = ("not_a_column", {
        "zh": "{where} 指的是 {name}，而数据里没有这一列",
        "en": "{where} names {name}, which is not a column in the data",
    })
    NO_USABLE_COLUMNS = ("no_usable_columns", {
        "zh": "数据里没有一列是这次搜索用得上的——图上的每个节点都得是一列，"
              "而一列要用得上就得是数值或二值的",
        "en": "no column in the data is usable by this search — every "
              "node of a graph is a column, and a column is usable when "
              "it is numeric or boolean",
    })
    NO_CANDIDATE_COLUMNS = ("no_candidate_columns", {
        "zh": "除了目标列以外没有任何候选列可搜，马尔可夫毯只能是空的，"
              "而空的毯子说的不是「没有邻居」而是「没有找过」",
        "en": "there is no candidate column besides the target to search, so "
              "the Markov blanket can only come back empty — and an empty "
              "blanket would say "
              "\"no neighbours\" where the truth is \"nothing was looked at\"",
    })

    # --- a set of columns the statistic cannot take ---------------------
    DECLARED_BOOL_HAS_MORE_LEVELS = ("declared_bool_has_more_levels", {
        "zh": "{columns} 被声明为二值，而数据里它们的取值多于两个。先明确地"
              "离散化（中位数切分 / 阈值）再来发现，或者把它们从二值声明里"
              "拿掉、给生成的程序一个显式的多档 domain",
        "en": "{columns} are declared boolean and the data holds more than "
              "two values for them. Discretise explicitly (a median split, a "
              "threshold) before discovering, or drop them from the boolean "
              "declaration and give the resulting program an explicit "
              "multi-level domain",
    })
    THE_CELLS_LEAVE_NO_SPREAD_TO_POOL = (
        "the_cells_leave_no_spread_to_pool", {
            "zh": "离散列把样本切成了 {cells} 个格，而连续列有 {continuous} 列——"
                  "把每个格自己的均值减掉之后，剩下的自由度不够估一个公用的"
                  "协方差，检验立在那个协方差上。要么合并层数太多的那些离散列，"
                  "要么给更多数据；这不是「检验没建」，是这批数据把它撑不起来",
            "en": "the discrete columns cut the sample into {cells} cells and "
                  "there are {continuous} continuous columns — once each "
                  "cell's own mean is removed there are not enough degrees of "
                  "freedom left to estimate the one covariance they share, "
                  "and the test rests on that covariance. Collapse the "
                  "discrete columns that carry the most levels, or bring more "
                  "data; this is the sample failing to support the test "
                  "rather than the test being unbuilt",
        })
    SERIES_ARE_NOT_CONTINUOUS = ("series_are_not_continuous", {
        "zh": "{columns} 不是连续的，而这里记录统计量用的 Fisher-Z 偏相关检验"
              "只适用于连续序列。离散的滞后检验要的统计量是列联计数，没有建",
        "en": "{columns} are not continuous, and the Fisher-Z "
              "partial-correlation test this records its statistic for "
              "applies to continuous series. A discrete lagged test needs "
              "contingency counts as its statistic and is not built",
    })
    THE_SEARCH_DID_NOT_SETTLE = ("the_search_did_not_settle", {
        "zh": "邻域搜索走了 {rounds} 轮还没稳定下来——这批数据可能违反忠实性，"
              "也可能共线到让邻域没有一个稳定的答案",
        "en": "the neighbourhood search had not settled after {rounds} "
              "rounds — the data may violate faithfulness, or be collinear "
              "enough that no neighbourhood is stable",
    })
    CONDITION_SELECTION_DID_NOT_SETTLE = (
        "condition_selection_did_not_settle", {
            "zh": "为 {target} 挑条件集的搜索没有稳定下来——这批数据可能违反"
                  "忠实性，也可能共线到让条件集没有一个稳定的答案",
            "en": "the search for {target}'s condition set did not settle — "
                  "the data may violate faithfulness, or be collinear enough "
                  "that no condition set is stable",
        })
    METHOD_IS_LIMITED_TO = ("method_is_limited_to", {
        "zh": "method={given} 不认识；这里实现的是 {offered}",
        "en": "method={given} is not one this builds; what is implemented is "
              "{offered}",
    })

    # --- an artifact handed to something that does not fit it ------------
    ARTIFACT_HAS_NO_CERTIFICATE = ("artifact_has_no_certificate", {
        "zh": "这份结果来自 {algorithm}，它不产出证书；只有 NOTEARS 的结果"
              "带着一份能重算的证书",
        "en": "this result came from {algorithm}, which computes no "
              "certificate; a NOTEARS result is the one that carries one",
    })

    # --- a graph the caller stated --------------------------------------
    EDGE_NAMES_AN_UNKNOWN_NODE = ("edge_names_an_unknown_node", {
        "zh": "{where} 里的 {edge} 有一端不在节点集合里",
        "en": "{edge} in {where} has an end that is not among the nodes",
    })
    PAIR_IS_ORIENTED_BOTH_WAYS = ("pair_is_oriented_both_ways", {
        "zh": "{pair} 这一对在输入里被同时定成了两个方向",
        "en": "the pair {pair} is oriented both ways in the input",
    })
    PAIR_IS_DIRECTED_AND_UNDIRECTED = ("pair_is_directed_and_undirected", {
        "zh": "{pair} 这一对既被定了方向又被留成无向的",
        "en": "the pair {pair} is both directed and left undirected",
    })
    THE_STATED_EDGES_CYCLE = ("the_stated_edges_cycle", {
        "zh": "已定向的边经 {tail}→{head} 构成一个环；没有哪个 DAG 同时"
              "含有它们",
        "en": "the directed edges cycle through {tail}→{head}; no DAG holds "
              "all of them",
    })
    SELF_LOOP = ("self_loop", {
        "zh": "{where} 里的 {edge} 是一条自环，一个变量不会是自己的原因",
        "en": "{edge} in {where} is a self-loop, and nothing is its own "
              "cause",
    })

    # --- an answer to a question this layer asked ------------------------
    ANSWER_IS_NOT_AN_ANSWER = ("answer_is_not_an_answer", {
        "zh": "收到的 {got} 既不是一个字典也不是一个 OrientationAnswer",
        "en": "{got} is neither a dict nor an OrientationAnswer",
    })
    AN_ANSWER_MUST_NAME_ITS_EDGE = ("an_answer_must_name_its_edge", {
        "zh": "不给方向的回答必须说出它答的是哪条边",
        "en": "an answer that states no direction has to name the edge it "
              "answers",
    })
    DIRECTION_IS_NOT_OF_THIS_EDGE = ("direction_is_not_of_this_edge", {
        "zh": "{direction} 不是边 {edge} 的一个方向",
        "en": "{direction} is not an orientation of the edge {edge}",
    })
    AN_ANSWER_STATES_ONE_OR_THE_OTHER = (
        "an_answer_states_one_or_the_other", {
            "zh": "一次回答要么说方向，要么说这条边在不在，不能两个都说",
            "en": "one answer states a direction or states whether the edge "
                  "is there, not both",
        })
    ADJACENCY_IS_LIMITED_TO = ("adjacency_is_limited_to", {
        "zh": "这条边在不在只能答 {accepted}，收到的是 {got}",
        "en": "whether the edge is there is answered with {accepted}; got "
              "{got}",
    })

    # --- a panel and the design it makes ---------------------------------
    BELOW_THE_MINIMUM = ("below_the_minimum", {
        "zh": "{where} 至少要是 {minimum}，收到的是 {got}",
        "en": "{where} must be at least {minimum}; got {got}",
    })
    OUTSIDE_THE_RANGE = ("outside_the_range", {
        "zh": "{where} 必须落在 {range} 里，收到的是 {got}",
        "en": "{where} must lie in {range}; got {got}",
    })
    TOO_FEW_SERIES = ("too_few_series", {
        "zh": "滞后图至少要两条序列，这里找到的是 {found}。如果默认挑错了，"
              "用 columns=(...) 点名",
        "en": "a lagged graph needs at least two series, and what was found "
              "is {found}. Name them with columns=(...) if the defaults "
              "picked the wrong ones",
    })
    THE_DESIGN_IS_TOO_WIDE = ("the_design_is_too_wide", {
        "zh": "{series} 条序列在 max_lag={max_lag} 下做出的设计有 {width} 列，"
              "超过了 {cap}——相关矩阵要跟着答案一起走，超过这个宽度就走不动。"
              "把 max_lag 调小，或者少点几条序列：统计量必须能随答案发出去，"
              "因为「每个检验都能从它重算」正是这个答案的价值所在",
        "en": "{series} series at max_lag={max_lag} make a design {width} "
              "columns wide, past the {cap} whose correlation matrix can "
              "travel with the answer. Lower max_lag or name fewer series — "
              "the statistic has to ship, because re-deriving every test "
              "from it is what the answer is worth",
    })
    TOO_FEW_ALIGNED_ROWS = ("too_few_aligned_rows", {
        "zh": "只有 {rows} 行在同一个单位里凑齐了到 {depth} 为止的每一个滞后，"
              "撑不起一个最多要条件在 {width} 列上的检验。序列更长、序列更少，"
              "或者 max_lag 更小",
        "en": "only {rows} rows have every lag up to {depth} present in the "
              "same unit, which cannot support a test conditioning on up to "
              "{width} columns. A longer series, fewer series, or a smaller "
              "max_lag",
    })
    TIME_COLUMN_HAS_A_HOLE = ("time_column_has_a_hole", {
        "zh": "时间列 {column} 里有缺失值或无穷值",
        "en": "the time column {column} holds a missing or infinite value",
    })
    TIME_COLUMN_IS_NOT_STEPS = ("time_column_is_not_steps", {
        "zh": "时间列 {column} 不是整数值。一个滞后是若干个步长，而一步是"
              "多长只有你知道，所以先把日期或时间戳换算成步号",
        "en": "the time column {column} is not integer-valued. A lag is a "
              "number of steps and only you know what one step is, so "
              "convert a date or a timestamp into a step index first",
    })
    TWO_ROWS_SHARE_A_STEP = ("two_rows_share_a_step", {
        "zh": "有两行的 {column}={step}；一个步号只能对应每条序列上的"
              "一次观测",
        "en": "two rows share {column}={step}; a step has to name one "
              "observation per series",
    })
    TWO_ROWS_SHARE_A_STEP_IN_ONE_UNIT = (
        "two_rows_share_a_step_in_one_unit", {
            "zh": "在 {unit}={id} 里有两行的 {column}={step}；一个步号只能"
                  "对应每条序列上的一次观测",
            "en": "two rows share {column}={step} within {unit}={id}; a step "
                  "has to name one observation per series",
        })
