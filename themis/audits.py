"""Which independent re-check applies to a given artifact, and what it redoes.

Themis ships thirteen public ``verify_*`` entry points. They share a
parameter name (``result: dict``), a naming prefix, and a module, and they
are not audits of the same thing: eight audit a ``query_result`` envelope
and five audit a standalone artifact — a Markov blanket, the four phases of
interactive orientation — whose own docstrings say so and whose dicts carry
a ``kind``. Nothing said it anywhere a caller could read.

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

from collections.abc import Iterable
from dataclasses import dataclass
from enum import unique

from .types import EnvelopeName


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
    ORIENTATION_PROPAGATION = "orientation_propagation"
    ORIENTATION_QUESTION_SET = "orientation_question_set"
    ORIENTATION_SESSION = "orientation_session"
    ORIENTATION_LEDGER_EXPORT = "orientation_ledger_export"


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

    zh: str
    """What this re-derives, said to whoever is deciding whether to trust
    the answer. Not "the verifier checked X" — what was recomputed, and
    from what. Required: an audit whose result nobody can read is an audit
    that ran for the machine only, and that is what this table replaces."""

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

    Four of the eight envelope rows recompute the answer — the chain, the
    interval, and the two recovery numbers. Four audit something else: the
    gap list, the assumption ledger, the cluster declaration, the
    outcome-error variance split. The distinction cannot be read off the
    other fields, since ``verify_outcome_error`` also names a field it
    needs and still is not the answer.

    A surface that reports auditability without it says "nothing here can
    be re-checked" to a reader holding an interval that one of these rows
    recomputes from the graph — the presence of a chain is a different
    question, and on an envelope whose answer came from a recovery
    estimator or from partial identification the two give opposite
    answers."""


AUDITS: tuple[Audit, ...] = (
    # --- the query_result envelope ------------------------------------------
    Audit(
        "verify", Artifact.QUERY_RESULT, True, needs_field="derivation",
        zh="按因果图把推导链一步步重走，确认每一步都站得住、最后一步给出的正是这个答案",
        re_derives_answer=True,
    ),
    Audit(
        "verify_bounds_results", Artifact.QUERY_RESULT, True,
        needs_field="bounds_results",
        zh="不看已给出的上下界，按图和记录下来的分布把这两个端点重新算一遍",
        re_derives_answer=True,
    ),
    Audit(
        "verify_data_gap_report", Artifact.QUERY_RESULT, False,
        zh="重算缺口清单：还差哪些量、每一条挡住的是什么、有没有别的路可走",
    ),
    Audit(
        "verify_assumption_ledger", Artifact.QUERY_RESULT, False,
        zh="把信封各处声明过的假设重新收一遍，确认台账一条都没漏——漏掉的假设读起来像没人做过这个假设",
    ),
    Audit(
        "verify_cluster_inference", Artifact.QUERY_RESULT, False,
        zh="重查区间的独立性单位：按簇跑出来的结果有没有把簇说清楚",
    ),
    Audit(
        "verify_outcome_error", Artifact.QUERY_RESULT, False,
        needs_field="outcome_error",
        zh="重算结局测量误差那一段的方差分解，并确认它赖以成立的前提确实进了估计声明的假设里",
    ),
    Audit(
        "verify_selection_recovery_numeric", Artifact.QUERY_RESULT, False,
        needs_method="selection_backdoor_recovery",
        zh="按记录下来的分层计数与外部权重表，把选择偏倚恢复的那个平均因果效应重跑一遍",
        re_derives_answer=True,
    ),
    Audit(
        "verify_missing_data_numeric", Artifact.QUERY_RESULT, False,
        needs_method="missing_data_recovery_gformula",
        zh="按记录下来的分层充分统计量，把缺失数据恢复用的 g-formula 重跑一遍",
        re_derives_answer=True,
    ),

    # --- standalone artifacts, each named by its own ``kind`` ----------------
    Audit(
        "verify_markov_blanket", Artifact.MARKOV_BLANKET, False,
        zh="从记录下来的相关矩阵或列联计数重做每一次条件独立检验，再核对这个马尔可夫毯是否既完备又最小",
    ),
    Audit(
        "verify_orientation_propagation", Artifact.ORIENTATION_PROPAGATION, False,
        zh="用另一份独立誊写的 Meek 规则 R1-R4，从记录下来的 CPDAG 与约束重新求一遍定向闭包",
    ),
    Audit(
        "verify_orientation_questions", Artifact.ORIENTATION_QUESTION_SET, False,
        zh="重新枚举等价类，核对每个冲突问题都对应一个真冲突、每个杠杆数都等于重算出来的覆盖增益",
    ),
    Audit(
        "verify_orientation_session", Artifact.ORIENTATION_SESSION, False,
        zh="从答案重新投影出约束，核对待定项恰好是仍未决的那些、来源链把每条已采纳的答案都记在了它真正蕴含的边上",
    ),
    Audit(
        "verify_orientation_ledger_export", Artifact.ORIENTATION_LEDGER_EXPORT, False,
        zh="沿 Meek 闭包重新传播「这条边来自 LLM 提议」的污染，核对每条定向边在台账里写的来源",
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
            out.append({"audit": row.name, "zh": row.zh, "ok": False,
                        "refusal": f"{type(exc).__name__}: {exc}"})
        else:
            out.append({"audit": row.name, "zh": row.zh, "ok": True,
                        "refusal": None})
    return out


def bind(public_names: Iterable[str]) -> None:
    """Every public ``verify_*`` has exactly one row here, and vice versa.

    Called from ``themis/__init__`` with its own ``__all__``, because that
    list is what a caller can reach and this table is a claim about all of
    it. A fourteenth entry point that forgets to declare what it audits is
    an ImportError rather than a surface that quietly answers for twelve.
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
