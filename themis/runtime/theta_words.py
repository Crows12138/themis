"""Why a program's probability statements do not compile into a theta.

Everything raised here is addressed to whoever handed the program in — an
LLM asked for structured output, the agent driving it, the person who
wrote the fixture. ``build_theta`` is called at the top of ``kernel.run``
and nothing between there and the caller catches these, so the caller IS
the reader, and until this table existed each of the three sentences was
an f-string at its own raise site, in English.

**The occasion was already split off; the sentence was not.** The
non-literal check takes a ``role`` — "target" or "given atom" — and
interpolates it, so which half of the statement went wrong has been a
SLOT for as long as the check has existed and only the wording stayed
welded to the site. A slot whose text IS the language is what
:class:`themis.language.Word` is for; interpolating ``"given atom"`` into
a Chinese sentence puts an English phrase in it, which is why the half is
:class:`Half` below rather than a string the site passes.

**Three species, two classes, and that is not a mismatch.** A caller
catches the CHANNEL and reads the SPECIES off the exception, which are
different questions: ``ConflictingThetaEntry`` is one channel and carries
two species — two statements that disagree about one key, and a group
whose supplied mass leaves no room for the complement. Both are "your
numbers cannot all be true at once"; only one of them is a duplicate.
Keying the vocabulary on the catch channel would have made those one
sentence with a hole for which kind of contradiction, which is a hole no
reader can be told the meaning of.

Where these END is where an exception message ends: nowhere. They are
rendered alone into ``str(exc)`` rather than joined into a paragraph, so
they carry no terminal mark — the convention
:mod:`themis.upstream.extraction_words` follows one layer up.
"""
from __future__ import annotations

from enum import unique

from .. import language


@unique
class Half(language.Word, vocabulary="probability_statement_half",
           between=language.BETWEEN_ITEMS):
    """Which side of a probability statement an atom sits on.

    ``P(target | given)`` has two, and a check that runs over both needs
    to say which one it was looking at. The site had this as a ``role=``
    string already — the fact was split off and the two English spellings
    of it were what stayed.
    """

    TARGET = ("target", {"zh": "目标", "en": "target"})
    GIVEN = ("given", {"zh": "条件", "en": "given"})


@unique
class Refuses(language.Word, vocabulary="theta_refusal",
              between=language.BETWEEN_STATEMENTS):
    """Why the statements handed in do not make a parameter store.

    Each says what is wrong with the PROGRAM rather than with the data:
    theta is the caller's declared joint, so every one of these is
    answered by going back and editing what was written down.
    """

    A_VALUE_IS_NOT_A_LITERAL = ("a_value_is_not_a_literal", {
        "zh": "概率语句的{half}原子 `{predicate}` 带的是 {value}，不是一个具体的"
              "字面值；一条概率语句描述的是一个完全定死的 CPT 条目",
        "en": "the {half} atom `{predicate}` of a probability statement "
              "carries {value} instead of a concrete literal value; a "
              "probability statement describes one fully-specified CPT entry",
    })
    TWO_STATEMENTS_DISAGREE_ABOUT_ONE_KEY = (
        "two_statements_disagree_about_one_key", {
            "zh": "两条概率语句给了同一个键 {key} 两个不同的值（{first} 与 "
                  "{second}）",
            "en": "two probability statements give the same key {key} two "
                  "different values ({first} and {second})",
        })
    THE_SUPPLIED_MASS_LEAVES_NO_COMPLEMENT = (
        "the_supplied_mass_leaves_no_complement", {
            "zh": "给出的 P({predicate}=*|...) 加起来是 {total}，落在 [0, 1] 之外；"
                  "那样推出来的 P({predicate}={missing}|...) 不会是一个概率",
            "en": "the supplied P({predicate}=*|...) sum to {total}, which is "
                  "outside [0, 1]; the P({predicate}={missing}|...) implied by "
                  "that would not be a probability",
        })
