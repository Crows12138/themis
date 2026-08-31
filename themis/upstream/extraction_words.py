"""Why the front door refused, as a table rather than as prose.

Everything this package raises is addressed to whoever produced the
extraction — an LLM asked for structured output, the agent driving it, or
the person who wrote the fixture. Until this table existed, every one of
those sentences was an f-string at its own raise site, forty-nine of them,
in English. A raise site that writes its own wording is the author of it,
and an author writes in the language they are thinking in.

**The occasion was already split off; the sentence was not.** Every helper
here takes a ``what`` — ``extraction.variables[3].predicate`` — and
interpolates it, so the path has been a SLOT for as long as the module has
existed and only the wording stayed welded to the site. That is why forty-
nine sites are sixteen species: what differed between them was almost
always the path, and the path was never the sentence.

Two vocabularies rather than one, because a shape is a WORD inside the
sentence and not a sentence of its own. Seven of the species were "{where}
must be a dict / a list / a non-empty string / …", which is one sentence
with a hole for which shape — and a hole a token cannot fill was the exact
gap :class:`themis.language.Word` was built to close, since stringifying
``DICT`` into a Chinese sentence puts an English token in it. That second
vocabulary is :mod:`themis.shape_words` now: the bundle door checks the
same three nouns, and a noun set two doors read belongs to neither.

Where these END is where an exception message ends: nowhere. They are
rendered alone into ``str(exc)`` rather than joined into a paragraph, so
they carry no terminal mark — the opposite of an artifact's ``note``, and
the same convention ``themis.input.semantic_validator.Malformed`` follows
one layer down.
"""
from __future__ import annotations

from enum import unique

from .. import language
# Named here as well as at its home, because this is where the species
# that interpolate it are and every site in this package imports the
# two together.
from ..shape_words import Shape  # noqa: F401


@unique
class Refuses(language.Word, vocabulary="extraction_refusal",
              between=language.BETWEEN_STATEMENTS):
    """Why an extraction was not usable.

    Two families under one name, because they reach one reader through one
    door. A SHAPE refusal says the input is not the thing it claimed to be;
    a CONFLICT says two inputs that were meant to be merged disagree. Both
    are answered the same way — go back and fix what was handed in — and
    splitting them by which exception class carries them would key the
    vocabulary on the catch channel rather than on the question.
    """

    # --- the input is not the shape it claimed --------------------------
    IS_NOT = ("is_not", {
        "zh": "{where} 必须是{shape}",
        "en": "{where} must be {shape}",
    })
    IS_NOT_WHEN_PRESENT = ("is_not_when_present", {
        "zh": "{where} 可以不写，写了就必须是{shape}",
        "en": "{where} is optional, but must be {shape} when present",
    })
    IS_REQUIRED = ("is_required", {
        "zh": "{where} 是必填的",
        "en": "{where} is required",
    })
    KIND_IS_LIMITED_TO = ("kind_is_limited_to", {
        "zh": "{where} 的 kind 只能取 {kinds}",
        "en": "{where}.kind is limited to {kinds}",
    })
    ONLY_BOOLEAN_VALUES_HERE = ("only_boolean_values_here", {
        "zh": "{where} 必须是布尔值——这个构建器只支持布尔域；收到的是 {got}",
        "en": "{where} must be a bool — this builder supports bool-only "
              "domains; got {got}",
    })
    BELOW_THE_MINIMUM = ("below_the_minimum", {
        "zh": "{where} 至少要是 {minimum}，收到的是 {got}",
        "en": "{where} must be at least {minimum}; got {got}",
    })

    # --- the input is well-shaped and names something that is not there --
    NOT_A_DECLARED_PREDICATE = ("not_a_declared_predicate", {
        "zh": "{where} 指的是 {name}，而它不在声明过的谓词集合里",
        "en": "{where} names {name}, which is not in the declared predicate "
              "set",
    })
    AN_EDGE_NAMES_SOMETHING_UNDECLARED = (
        "an_edge_names_something_undeclared", {
            "zh": "{where} 是 {tail}→{head}，其中有一端不在声明过的谓词集合里",
            "en": "{where} is {tail}→{head}, and one end of it is not in the "
                  "declared predicate set",
        })
    PREDICATE_DECLARED_TWICE = ("predicate_declared_twice", {
        "zh": "{where} 里 {name} 出现了两次",
        "en": "{where} declares {name} twice",
    })
    QUERY_KIND_NOT_SUPPORTED = ("query_kind_not_supported", {
        "zh": "这个构建器不认识 query_kind={kind}；它接受的是 {accepted}",
        "en": "this builder does not support query_kind={kind}; it accepts "
              "{accepted}",
    })
    SELF_LOOP = ("self_loop", {
        "zh": "{where} 是一条自环（{name}→{name}），一个变量不会是自己的原因",
        "en": "{where} is a self-loop ({name}→{name}), and nothing is its "
              "own cause",
    })
    TARGET_IS_NOT_IN_THE_BASE = ("target_is_not_in_the_base", {
        "zh": "谓词链接要改写成 {targets}，而基础程序里没有声明它们",
        "en": "the predicate links rewrite onto {targets}, which the base "
              "program does not declare",
    })

    # --- two inputs that were to be merged disagree ---------------------
    ONE_SOURCE_TWO_TARGETS = ("one_source_two_targets", {
        "zh": "谓词 {source} 被同时链接到 {first} 和 {second}，"
              "改写没有唯一的落点",
        "en": "the predicate {source} is linked to both {first} and "
              "{second}, so the rewrite has no single destination",
    })
    TWO_DOMAINS = ("two_domains", {
        "zh": "谓词 {predicate} 的 domain 两边不一致：{first} 对 {second}",
        "en": "the two declarations of {predicate} disagree on its domain: "
              "{first} against {second}",
    })
    TWO_VALUES_FOR_ONE_FIELD = ("two_values_for_one_field", {
        "zh": "谓词 {predicate} 的 {field} 两边不一致：{first} 对 {second}",
        "en": "the two declarations of {predicate} disagree on {field}: "
              "{first} against {second}",
    })
    A_REFUSAL_MEETS_AN_EDGE = ("a_refusal_meets_an_edge", {
        "zh": "{pair} 这一对，一边拒绝直接连边，另一边已经断言了 {existing}",
        "en": "on the pair {pair}, one side refuses a direct edge and the "
              "other has already asserted {existing}",
    })
    AN_EDGE_MEETS_A_REFUSAL = ("an_edge_meets_a_refusal", {
        "zh": "{pair} 这一对，一边断言 {incoming}，另一边已经拒绝了直接连边",
        "en": "on the pair {pair}, one side asserts {incoming} and the other "
              "has already refused a direct edge",
    })


class ExtractionRefusal(language.Voiced, ValueError):
    """What this package raises, whichever door it comes out of.

    A :class:`themis.language.Voiced`, which is where the body of this
    class went: it was written out here and again in
    ``themis.input.semantic_validator``, identical line for line, and the
    argument for writing it once — four exception classes in one package
    would otherwise be four copies — turned out not to stop at the package
    boundary.

    ``ValueError`` as well, because that is what a caller of this package
    has always been able to catch and the species is not a reason to take
    it away.

    The subclasses stay, and they are not decoration: a caller catches the
    CHANNEL — a malformed shape, a merge conflict, a broken link bundle —
    and reads the SPECIES off the exception. The two are different
    questions and were one string before.
    """


def edge(tail: str, head: str) -> str:
    """A pair, as an expression rather than as a list.

    ``a–b`` is written the same way for every reader, which is what
    :func:`themis.language.within` says about a conditioning set: the
    kernel builds the expression, and an expression takes no language.
    """
    return f"{tail}–{head}"
