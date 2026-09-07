"""Which independent re-check applies to a given artifact, and what it redoes.

Themis's public ``verify_*`` entry points share a parameter name
(``result: dict``), a naming prefix, and a module, and they are not audits
of the same thing: some audit a ``query_result`` envelope, others audit a
standalone artifact — a Markov blanket, a lagged discovery, a NOTEARS fit,
the four phases of interactive orientation — whose own docstrings say so and
whose dicts carry a ``kind``. Nothing said it anywhere a caller could read.
(The split is what matters and the tally is not, so the tally is not written
down: it was written down once, and went stale three entry points later.)

What that cost, measured over 139 results:

- ``verify_markov_blanket`` and the four ``verify_orientation_*`` raised
  ``VerificationError`` on **every one of them**, because the artifact they
  were handed was not theirs. To a caller working the only way there was —
  call it, catch the exception — "this audit is not about your result" and
  "your result failed its audit" are the same event.
- ``verify_outcome_error`` returned quietly on all 139, none of which
  carried an ``outcome_error``. A pass that checked nothing reads as a pass.
- Four surfaces each hand-rolled a subset: the ``themis/__init__`` docstring
  named six, the MCP server exposes six, the browser used two, the agent
  prompt names two. The two sixes overlap in three.

So a row per entry point, saying what it is an audit **of**, when it applies
within that, what it re-derives, and whether that thing is the answer or a
fact beside it. ``applicable`` answers the question once; ``audit`` runs what
applies and reports per audit, so that a caller never has to tell the two
failures apart — it is never handed the first one.

The table also answers a question asked from inside. ``verify`` reruns the
envelope's one-sided surfaces in the course of its own pass, because a
caller who called only ``verify`` would otherwise be told nothing about a
surface that discloses nothing; ``bind_rerun`` is what makes that list the
family rather than a copy of it, and what a copy loses is stated there.

The applicability is declared as data rather than as a predicate because it
is a claim about the artifact ("audits the chain, so it needs one"), and a
claim can be read back, printed, and compared with the docstring it came
from. A lambda can only be run.

**The verifiers do not import this.** Each standalone auditor keeps its own
``kind`` literal and rejects a foreign artifact on its own authority; a test
pins the two sets equal. Selecting an audit from a table the audit itself
wrote would make the selection self-certifying, which is the same reason
:mod:`themis.risk_provenance` is re-declared on the verifier side.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import unique
from typing import TypeVar

from .language import Words
from .types import EnvelopeName

T = TypeVar("T")


@unique
class Artifact(EnvelopeName):
    """The kind of thing an audit is an audit of.

    The five standalone values are verbatim the ``kind`` their artifacts
    carry, which is how one is recognised. An envelope carries no ``kind``
    — it has ``query_kind``, which says what was asked, not what this dict
    is — so ``query_result`` is what anything else resolves to. That
    asymmetry is deliberate: the envelope is the artifact the kernel
    returns by default, and a new standalone artifact has to say its name
    to be treated as one.
    """

    QUERY_RESULT = "query_result"
    MARKOV_BLANKET = "markov_blanket"
    LAGGED_DISCOVERY = "lagged_discovery"
    LATENT_LAGGED_DISCOVERY = "latent_lagged_discovery"
    NOTEARS_FIT = "notears_fit"
    ORIENTATION_PROPAGATION = "orientation_propagation"
    ORIENTATION_QUESTION_SET = "orientation_question_set"
    ORIENTATION_SESSION = "orientation_session"
    ORIENTATION_LEDGER_EXPORT = "orientation_ledger_export"

    @property
    def schema(self) -> str:
        """The document in ``themis/schemas`` that declares this shape.

        Derived rather than tabled: the value already IS the name, and a
        second table would be one that could disagree with the first. What
        the derivation buys is that being an artifact and having a declared
        shape stop being two facts — for a long time they were, and five of
        the six went undescribed with nothing able to say so. Every
        structural gate reads a schema as its denominator, so an artifact
        outside the directory is one no gate can reach; ``markov_blanket``
        shipped a ``data_hash`` past the rule built to pair every digest
        with its denominator, not because it broke the rule but because
        nothing declared it existed.
        """
        return f"{self.value}.schema.json"


@dataclass(frozen=True)
class Audit:
    """One public entry point, and the conditions under which it says
    anything at all."""

    name: str
    """The attribute on ``themis``. This is the id that travels out to a
    caller, so it is the name the caller already had."""

    artifact: Artifact

    needs_program: bool
    """Whether re-deriving needs the source program. Two do: a reasoning
    chain and a bounds pair are both claims about a graph, and re-deriving
    them from the answer alone would be reading the answer back."""

    words: Words
    """What this re-derives, by language, said to whoever is deciding
    whether to trust the answer. Not "the verifier checked X" — what was
    recomputed, and from what. Required: an audit whose result nobody can
    read is an audit that ran for the machine only, and that is what this
    table replaces.

    Every language this build has, not the one a caller wanted. A row is
    an artifact rather than a rendering, and an artifact that had already
    chosen would make two readers of one audit need two runs."""

    needs_field: str | None = None
    """A top-level field the audit is the audit of. Absent field, nothing
    was claimed, and nothing claimed is not something that passed."""

    needs_method: str | None = None
    """A ``numeric_estimate.method`` this audit re-derives. Two recovery
    estimators have their own auditors because their results carry no
    derivation, so the chain audit cannot reach them."""

    re_derives_answer: bool = False
    """Whether what this audit recomputes IS the answer, rather than a fact
    standing beside it.

    The envelope rows that recompute the answer are the chain, the interval
    and the two recovery numbers; the rest audit something standing beside
    it — the gap list, the assumption ledger, the cluster declaration, the
    outcome-error variance split, the agreement of the fingerprints. The
    distinction cannot be read off the other fields, since
    ``verify_outcome_error`` also names a field it needs and still is not
    the answer.

    A surface that reports auditability without it says "nothing here can
    be re-checked" to a reader holding an interval that one of these rows
    recomputes from the graph — the presence of a chain is a different
    question, and on an envelope whose answer came from a recovery
    estimator or from partial identification the two give opposite
    answers.

    Read through :meth:`re_derives_the_answer_of`, never on its own: the
    flag is half of a fact whose other half is the envelope."""

    def re_derives_the_answer_of(self, obj: dict) -> bool:
        """Whether this row recomputes the answer of THIS envelope.

        Recomputing the answer is a fact about the audit and the envelope
        together, and on four of the five rows the halves coincide: each is
        gated on the very thing it re-derives — a chain, a bounds pair, a
        recovery method — so a row that applies at all applies to something
        that IS an answer, and the flag can be read alone.

        The fifth is the door for an answer with no chain, and it is gated
        on nothing, because an answer may consist of nothing but its
        claims. Where such an answer carries a number the door recomputes
        it — the price of its interval, the identities its own figures
        satisfy, the level its run states. Where it carries none there is
        nothing to recompute, and saying otherwise would tell a reader that
        a conclusion they were never given can be re-checked.
        """
        if not self.re_derives_answer:
            return False
        if self.needs_field or self.needs_method:
            return True
        return bool(obj.get("numeric_estimate") or obj.get("bounds_results"))


AUDITS: tuple[Audit, ...] = (
    # --- the query_result envelope ------------------------------------------
    Audit(
        "verify", Artifact.QUERY_RESULT, True, needs_field="derivation",
        words={"zh": "按因果图把推导链一步步重走，确认每一步都站得住、最后一步给出的正是这个答案",
               "en": "Walk the derivation chain step by step against the "
                     "causal graph, confirming that each step holds and that "
                     "the last one yields exactly this answer"},
        re_derives_answer=True,
    ),
    Audit(
        "verify_answer_claims", Artifact.QUERY_RESULT, True,
        words={"zh": "不要推导链，把答案说出口的每一句话对着图和问题重算："
                     "估计量、走的哪条路、缺哪些数据、让读者去补什么、拟合的是什么；"
                     "连同信封自己算得出的那些数——区间的价格、由自身数字推出的等式、"
                     "这次运行声明的置信水平、每个块说它是关于什么的",
               "en": "Without needing the chain, recompute everything the "
                     "answer SAYS against the graph and the question: the "
                     "estimand, which route it took, what data is missing, "
                     "what the reader is asked to supply, and what shape "
                     "was fitted — together with the figures the envelope "
                     "works out from its own: an interval's price, the "
                     "identities its numbers satisfy, the level this run "
                     "states its confidence at, and what each block says "
                     "it is about"},
        re_derives_answer=True,
    ),
    Audit(
        "verify_bounds_results", Artifact.QUERY_RESULT, True,
        needs_field="bounds_results",
        words={"zh": "不看已给出的上下界，按图和记录下来的分布把这两个端点重新算一遍",
               "en": "Ignore the endpoints already given and recompute both of "
                     "them from the graph and the recorded distribution"},
        re_derives_answer=True,
    ),
    Audit(
        # Takes the program because what it audits is a claim ABOUT the
        # program. Its neighbour below asks whether the gap list agrees with
        # the envelope around it, which is a different question and gives the
        # same answer for an honest refusal and for one lifted onto a query
        # the same graph identifies.
        "verify_refusal", Artifact.QUERY_RESULT, True,
        needs_field="data_gap_report",
        words={"zh": "拿程序自己的图重走这次拒答：报告说识别不了的估计量，图里是不是其实存在一个可调整集或一条前门路径",
               "en": "Walk this refusal again against the program's own "
                     "graph: for the estimand the report says nothing "
                     "identifies, does an adjustment set or a front-door "
                     "route in fact exist"},
    ),
    Audit(
        "verify_data_gap_report", Artifact.QUERY_RESULT, False,
        words={"zh": "重算缺口清单：还差哪些量、每一条挡住的是什么、有没有别的路可走",
               "en": "Recompute the gap list: which quantities are still "
                     "missing, what each one blocks, and whether another route "
                     "exists"},
    ),
    Audit(
        "verify_assumption_ledger", Artifact.QUERY_RESULT, False,
        words={"zh": "把信封各处声明过的假设重新收一遍，确认台账一条都没漏——漏掉的假设读起来像没人做过这个假设",
               "en": "Collect again every assumption declared anywhere on the "
                     "envelope and confirm the ledger missed none — an "
                     "assumption left out reads as one nobody made"},
    ),
    Audit(
        "verify_cluster_inference", Artifact.QUERY_RESULT, False,
        words={"zh": "重查区间的独立性单位：按簇跑出来的结果有没有把簇说清楚，"
                     "两处记录说的是不是同一件事",
               "en": "Re-examine the interval's unit of independence: whether "
                     "a clustered run said so about its clusters, and whether "
                     "its two records of that say the same thing"},
    ),
    Audit(
        # The other half of the same block, and it declares no field for the
        # same reason its neighbour does not: a bootstrap record rides on
        # whichever of the estimate, its decomposition tables and the bounds
        # rows reported an interval, and no one top-level field means one is
        # there. The bounds case is why this is reachable without a chain —
        # bounds attach where point identification failed, so ``verify`` is
        # dormant on exactly the results whose draws nobody else audits.
        "verify_bootstrap_draws", Artifact.QUERY_RESULT, False,
        words={"zh": "重算每个区间到底站在多少次重抽样上：抽了多少次是不是这次运行要的那个数，"
                     "丢掉的抽样有没有说清各自是被什么吃掉的，"
                     "报出来的区间背后是不是不止一次抽样——只剩一次时分位数原样返回那个值，"
                     "两个端点会是同一个数印了两遍",
               "en": "Recompute how many resamples each interval actually "
                     "rests on: whether that is the number this run asked "
                     "for, whether the discarded draws say what ate each "
                     "of them, and whether a reported interval rests on more "
                     "than one draw — a quantile of a single value returns "
                     "that value, so the two endpoints would be one number "
                     "printed twice"},
    ),
    Audit(
        "verify_outcome_error", Artifact.QUERY_RESULT, False,
        needs_field="outcome_error",
        words={"zh": "重算结局测量误差那一段的方差分解，并确认它赖以成立的前提确实进了估计声明的假设里",
               "en": "Recompute the variance decomposition behind the outcome "
                     "measurement error, and confirm that the premises it "
                     "rests on did reach the assumptions the estimate declares"},
    ),
    Audit(
        "verify_fingerprints_agree", Artifact.QUERY_RESULT, False,
        needs_field="estimation_context",
        words={"zh": "核对这份答案里每一个数据指纹说的都是同一份表——界、点估计、推导链各自记的指纹，覆盖的列不同时本就该不同，但它们必须都是这一次运行的",
               "en": "Check that every data fingerprint on this answer speaks "
                     "of the same table — the bounds, the point estimate and "
                     "the derivation chain each record their own, and they "
                     "should differ when they cover different columns, but all "
                     "of them have to be of this run"},
    ),
    Audit(
        "verify_one_row_count", Artifact.QUERY_RESULT, False,
        needs_field="estimation_context",
        words={"zh": "核对这份答案里每一处「用了多少行」说的都是同一个数——运行在任何估计量跑之前记下一次，点估计、每一条界、结局误差那块、推导链每一步的输入各自又抄了一份，而读者读到的精度就是从其中某一个数上来的",
               "en": "Check that every record of how many rows this answer "
                     "was computed on is the same number — the run writes it "
                     "down once before any estimator runs, and the point "
                     "estimate, each bounds row, the outcome-error block and "
                     "every derivation step's inputs each carry a copy, while "
                     "the precision a reader reads is taken off one of them"},
    ),
    Audit(
        "verify_selection_recovery_numeric", Artifact.QUERY_RESULT, False,
        needs_method="selection_backdoor_recovery",
        words={"zh": "按记录下来的分层计数与外部权重表，把选择偏倚恢复的那个平均因果效应重跑一遍",
               "en": "Rerun the selection-bias-recovered average causal effect "
                     "from the recorded stratum counts and the external weight "
                     "table"},
        re_derives_answer=True,
    ),
    Audit(
        "verify_missing_data_numeric", Artifact.QUERY_RESULT, False,
        needs_method="missing_data_recovery_gformula",
        words={"zh": "按记录下来的分层充分统计量，把缺失数据恢复用的 g-formula 重跑一遍",
               "en": "Rerun the missing-data recovery g-formula from the "
                     "recorded per-stratum sufficient statistics"},
        re_derives_answer=True,
    ),

    # --- standalone artifacts, each named by its own ``kind`` ----------------
    Audit(
        "verify_markov_blanket", Artifact.MARKOV_BLANKET, False,
        words={"zh": "从记录下来的相关矩阵或列联计数重做每一次条件独立检验，再核对这个马尔可夫毯是否既完备又最小",
               "en": "Redo every conditional independence test from the "
                     "recorded correlation matrix or contingency counts, then "
                     "check that this Markov blanket is both complete and "
                     "minimal"},
    ),
    Audit(
        "verify_lagged_discovery", Artifact.LAGGED_DISCOVERY, False,
        words={"zh": "从记录下来的相关矩阵重做两个阶段的每一次条件独立检验："
                     "父集是不是它自称的那个不动点，以及每一次 MCI 检验是不是"
                     "真的同时以目标的父集和驱动变量自己的父集为条件",
               "en": "Redo every conditional independence test of both stages "
                     "from the recorded correlation matrix: whether each "
                     "parent set is the fixpoint it claims to be, and whether "
                     "each MCI test really conditioned on the driver's own "
                     "parents as well as the target's"},
    ),
    Audit(
        "verify_latent_lagged_discovery", Artifact.LATENT_LAGGED_DISCOVERY,
        False,
        words={"zh": "从记录下来的相关矩阵把子集搜索整个重跑一遍——筛选集是不是"
                     "它自称的那个不动点，每一对的判定是不是搜索真会给出的那个"
                     "——再用另一份独立誊写的定向规则把每个端点标记重新推一次，"
                     "核对每一个「导致」都真有一个三元组撑着",
               "en": "Re-run the whole subset search from the recorded "
                     "correlation matrix — whether the screen is the fixpoint "
                     "it claims and whether each pair's verdict is the one "
                     "the search returns — then re-derive every endpoint mark "
                     "with a second independent transcription of the "
                     "orientation rules, checking that each `causes` really "
                     "has a triple holding it up"},
    ),
    Audit(
        "verify_notears_fit", Artifact.NOTEARS_FIT, False,
        words={"zh": "只拿记录下来的 Gram 矩阵和这组权重，把无环性残差、目标函数值"
                     "和一阶最优性残差各自重算一遍，再按声明的阈值重读一次边——"
                     "全局最优不在其中，这份证书也没有声称过",
               "en": "Recompute the acyclicity residual, the objective value and "
                     "the first-order residual from the recorded Gram matrix and "
                     "these weights alone, then re-read the edges at the declared "
                     "threshold — global optimality is not among them, and this "
                     "certificate never claimed it"},
    ),
    Audit(
        "verify_orientation_propagation", Artifact.ORIENTATION_PROPAGATION, False,
        words={"zh": "用另一份独立誊写的 Meek 规则 R1-R4，从记录下来的 CPDAG 与约束重新求一遍定向闭包",
               "en": "Recompute the orientation closure from the recorded "
                     "CPDAG and constraints, using a second independent "
                     "transcription of Meek's rules R1-R4"},
    ),
    Audit(
        "verify_orientation_questions", Artifact.ORIENTATION_QUESTION_SET, False,
        words={"zh": "重新枚举等价类，核对每个冲突问题都对应一个真冲突、每个杠杆数都等于重算出来的覆盖增益",
               "en": "Re-enumerate the equivalence class and check that every "
                     "conflict question corresponds to a real conflict and "
                     "every leverage figure equals the recomputed coverage "
                     "gain"},
    ),
    Audit(
        "verify_orientation_session", Artifact.ORIENTATION_SESSION, False,
        words={"zh": "从答案重新投影出约束，核对待定项恰好是仍未决的那些、来源链把每条已采纳的答案都记在了它真正蕴含的边上",
               "en": "Re-project the constraints from the answers and check "
                     "that the undecided items are exactly those still open, "
                     "and that the provenance chain records each accepted "
                     "answer on the edge it actually implies"},
    ),
    Audit(
        "verify_orientation_ledger_export", Artifact.ORIENTATION_LEDGER_EXPORT, False,
        words={"zh": "沿 Meek 闭包重新传播「这条边来自 LLM 提议」的污染，核对每条定向边在台账里写的来源",
               "en": "Re-propagate the taint \"this edge came from an LLM "
                     "proposal\" along the Meek closure, and check the "
                     "provenance the ledger records for each oriented edge"},
    ),
)


def artifact_of(obj: dict) -> Artifact:
    """Which artifact this dict is."""
    kind = obj.get("kind") if isinstance(obj, dict) else None
    for candidate in Artifact:
        if candidate != Artifact.QUERY_RESULT and candidate == kind:
            return candidate
    return Artifact.QUERY_RESULT


def _applies(row: Audit, obj: dict) -> bool:
    if row.artifact is not artifact_of(obj):
        return False
    if row.needs_field and not obj.get(row.needs_field):
        return False
    if row.needs_method:
        estimate = obj.get("numeric_estimate")
        if not isinstance(estimate, dict):
            return False
        if estimate.get("method") != row.needs_method:
            return False
    return True


def applicable(obj: dict) -> tuple[Audit, ...]:
    """Every audit that would say something about this artifact.

    An audit left out here is not one that passed. That is the whole point
    of asking before calling.
    """
    return tuple(row for row in AUDITS if _applies(row, obj))


def audit(program: dict | str | bytes | None, obj: dict) -> list[dict]:
    """Run every applicable audit and report each one.

    Returns one row per applicable audit: ``{"audit", "zh", "ok",
    "refusal"}``. No audit's own failure escapes — a caller asking "was
    this independently re-checked" gets an answer rather than an exception
    it has to classify. A malformed call still raises, because that is the
    caller's mistake and not a verdict about the artifact.
    """
    from . import kernel

    rows = applicable(obj)
    if program is None and any(row.needs_program for row in rows):
        raise ValueError(
            "audit() needs the source program to re-derive "
            + ", ".join(row.name for row in rows if row.needs_program)
        )

    out: list[dict] = []
    for row in rows:
        fn = getattr(kernel, row.name)
        try:
            fn(program, obj) if row.needs_program else fn(obj)
        except Exception as exc:  # every audit reports; none of them escapes
            out.append({"audit": row.name, "words": dict(row.words),
                        "ok": False,
                        "refusal": f"{type(exc).__name__}: {exc}"})
        else:
            out.append({"audit": row.name, "words": dict(row.words),
                        "ok": True, "refusal": None})
    return out


def bind_rerun(reruns: Mapping[str, T]) -> dict[str, T]:
    """Every envelope audit the full door has to carry out itself, and what
    carries it out.

    The sibling of :func:`bind`, and the denominator is the whole of the
    difference. ``bind`` asks which audits exist. This asks which of them
    ``verify`` must run in the course of its own pass, and the answer is
    every ``query_result`` row that does not need the program. What needing
    the program marks is an audit OF THE ANSWER — the chain and the bounds
    pair are both claims about a graph — and ``verify`` is one of those two
    and performs the other on its own terms, non-strictly, because a bounds
    method whose verifier does not exist yet is not its business. What is
    left is the surfaces standing beside the answer, whose failure mode is
    one-sided: a surface that under-discloses reads exactly like one with
    nothing to disclose, so a caller who called only ``verify`` would never
    learn of it, and running them is the whole reason ``verify`` touches
    anything outside the chain.

    The binding exists because the alternative is a hand-copied list, and
    what gets copied is a rule rather than a door. A public door is free to
    grow a second rule; the copy inside ``verify`` does not grow with it,
    and the divergence runs the one way that cannot be noticed from
    outside — the full door gets weaker while every narrow door keeps its
    strength. A tampered ``type_reconciliation`` block passed ``verify``
    and was refused by ``verify_data_gap_report`` for eight weeks on
    exactly that arithmetic.
    """
    owed = {row.name for row in AUDITS
            if row.artifact == Artifact.QUERY_RESULT and not row.needs_program}
    missing = sorted(owed - set(reruns))
    if missing:
        raise RuntimeError(
            f"themis.verify does not rerun envelope audit(s) {missing}; a "
            f"surface audited only by the door that names it is one a "
            f"caller has to know to ask for")
    extra = sorted(set(reruns) - owed)
    if extra:
        raise RuntimeError(
            f"rerun bound for {extra}, which is not an envelope surface "
            f"verify owes; an audit of the answer itself, or of a "
            f"standalone artifact, is not verify's to repeat")
    return dict(reruns)


def bind(public_names: Iterable[str]) -> None:
    """Every public ``verify_*`` has exactly one row here, and vice versa.

    Called from ``themis/__init__`` with its own ``__all__``, because that
    list is what a caller can reach and this table is a claim about all of
    it. An entry point that forgets to declare what it audits is an
    ImportError rather than a surface that quietly answers for the rest.
    """
    declared = {row.name for row in AUDITS}
    public = {name for name in public_names if name.startswith("verify")}
    if declared != public:
        missing = sorted(public - declared)
        extra = sorted(declared - public)
        raise RuntimeError(
            "themis.audits does not account for every public verifier"
            + (f"; undeclared: {missing}" if missing else "")
            + (f"; declared but not public: {extra}" if extra else "")
        )
