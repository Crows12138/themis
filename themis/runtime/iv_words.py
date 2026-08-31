"""What an instrument's answer discloses about itself.

Two fields on ``extensions.iv_identification``, and both were typed
``string``. What that costs is written down twice already, in this
repository's own words and by two different authors.

The first is the rule that measures it. ``late_caveat`` is the case
:mod:`tests.test_no_sentence_reaches_the_reader_in_the_wrong_language`
opens with — "a whole paragraph of English prose printed verbatim into a
Chinese report, and every check still green". It was translated, and the
paragraph is now Chinese prose printed verbatim into whatever report the
reader asked for. Translating a sentence written at its site moves which
reader it fails.

The second is a producer refusing to join in. The feedback-loop route
writes a TOKEN into ``required_assumption`` and says why beside it:
"every other producer writes prose here and the report renders it
verbatim, which is exactly why this one does not". So the field's own
contract was contested between its four producers, and one of them had
written that down. A token where three siblings hold prose is not a
disagreement about wording — it is the field having no shape.

Here rather than in :mod:`themis.ledger` because only one of these is an
assumption. The other is a disclosure about which estimand the number
IS, which is a different question from what it rests on, and the two
travel in different fields for that reason.
"""
from __future__ import annotations

from enum import unique

from .. import language


@unique
class Premise(language.Word, vocabulary="iv_required_assumption",
              between=language.BETWEEN_STATEMENTS):
    """What point identification through an instrument still needs.

    Structural identification through an instrument stops one step short:
    the graph says the effect is reachable, and reaching a number takes a
    premise the graph cannot supply. Which premise depends on which
    estimator will answer, so the member names the estimator too — a
    reader told "monotonicity" without being told it buys a LATE has been
    told half of it.
    """

    MONOTONICITY_OR_LINEARITY = ("monotonicity_or_linearity", {
        "zh": "单调性（走 LATE/Wald）或线性（走 2SLS/ATE）",
        "en": "monotonicity (for LATE/Wald) or linearity (for 2SLS/ATE)",
    })
    MONOTONICITY_AS_DECLARED = ("monotonicity_as_declared", {
        "zh": "单调性：{direction}——由此走 Wald LATE 估计量",
        "en": "monotonicity: {direction} — and so the Wald LATE estimator",
    })
    LINEAR_SIMULTANEOUS_SYSTEM = ("linear_simultaneous_system", {
        "zh": "线性联立方程组——而且报出来的数是其中一个方程的系数，"
              "不是总效应",
        "en": "a linear simultaneous system — and the number reported is "
              "one equation's coefficient rather than a total effect",
    })


@unique
class Complier(language.Word, vocabulary="late_caveat",
               between=language.BETWEEN_SENTENCES):
    """Whose effect the Wald ratio is, said before the number is read.

    Two members and the second is conditional, which is why the field
    holds a LIST. It was one string built by ``+=``, so the two halves
    could only ever be joined in the language its author was thinking in
    — and the join between two sentences is itself a fact about the
    language, which is what :func:`themis.language.spoken` knows and a
    ``+=`` does not.
    """

    LATE_IS_NOT_THE_ATE = ("late_is_not_the_ate", {
        "zh": "LATE = E[Y(X=treated) − Y(X=control) | 依从者]，也就是"
              "**只在依从者身上**的平均效应（依从者 = 被工具变量推动了处理"
              "状态的那部分人），**不是**总体的 ATE。把 LATE 当成 ATE 是"
              "工具变量最常见的误用——报答案之前要先把这句说清楚。"
              "`treatment_shift` 就是在声明的单调性下，这部分人占总体的比例。",
        "en": "LATE = E[Y(X=treated) − Y(X=control) | compliers] — the "
              "average effect **among compliers only** (the compliers "
              "being those whose treatment status the instrument moved), "
              "**not** the population ATE. Reading a LATE as an ATE is the "
              "commonest way an instrument is misused, so this has to be "
              "said before the number is. `treatment_shift` is that "
              "subpopulation's share under the declared monotonicity.",
    })
    STRATA_WEIGHTED_BY_COMPLIER_SHARE = (
        "strata_weighted_by_complier_share", {
            "zh": "这个工具只有在 {variables} 固定住的前提下才成立，所以报出来"
                  "的数是把 `strata` 里各层的 LATE 按**各层自己的依从者比例**"
                  "加权汇总的——**不是**按各层的人口比例。工具在不同层里推动"
                  "处理的力度不一样时，两者就不相等，而只有前者才是依从者上的"
                  "效应。",
            "en": "this instrument holds only with {variables} fixed, so "
                  "the number reported aggregates the per-stratum LATEs in "
                  "`strata` weighted by **each stratum's own complier "
                  "share** — **not** by its share of the population. Where "
                  "the instrument moves treatment harder in one stratum "
                  "than another the two differ, and only the first is an "
                  "effect among compliers.",
        })
