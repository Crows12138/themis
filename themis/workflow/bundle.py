"""What a bundle envelope is, and what it says when it is not one.

A bundle is how a surface hands work back: a version, a kind, and one list
of records under a key the kind decides. Two kinds exist — filled parameter
skeletons and variable patches — and the envelope around them is the same
envelope, so the four checks that read it are the same four checks.

**They were written twice, line for line.** Each of the two modules had its
own ``_validate_bundle_shape`` differing only in a constant and a key name,
its own ``BUNDLE_VERSION = "0.1"``, and — this is the part that made the
copy cheap — **its own exception class, both called
``MalformedBundleError``**. A shared check has to raise a shared exception,
and there was none to raise, so the shape was checked where each module
could reach a class of its own. The knowledge that the envelope is one
shape parameterised by ``(kind, key)`` was never missing: ``kernel`` holds
exactly that pair, for exactly these two kinds, in a table it uses to wrap
loose records.

So the pair is the argument here, the class is one class, and what each
module keeps is the part that is genuinely its own — for a patch bundle, an
item-by-item check that only it has a vocabulary of legal fields for.

The species live here too rather than in a table of their own. Every one of
them is about a bundle: the envelope, an item in it, or a field of an item
the program cannot accept. A second module holding only the words would
split one subject across two files to satisfy a naming convention.
"""
from __future__ import annotations

from enum import unique

from .. import language
from ..shape_words import Shape

#: The one version of the bundle envelope this build reads and writes.
#:
#: Three modules declared it and a fourth wrote the literal into a bundle it
#: builds — four places for a constant whose whole job is that both ends
#: agree about it.
VERSION = "0.1"


@unique
class Refuses(language.Word, vocabulary="workflow_refusal"):
    """Why a bundle handed back to this build was not usable.

    Its reader is whoever built the bundle — a surface, an LLM copying a
    skeleton it was given, the person who wrote the fixture — and it
    reaches them as an exception, because a bundle that cannot be read
    produces no result to put an envelope on.

    The path is a slot at every one of these, which is what makes nineteen
    sites nine species: what differed between them was almost always where
    in the bundle the trouble was, and where is not the sentence. The shape
    is a slot too, and its words are :class:`themis.shape_words.Shape` —
    the same nouns the LLM-side front door interpolates, because "must be a
    dict" is the same sentence whichever door says it.

    Where these END is where an exception message ends: nowhere.
    """

    # --- the bundle is not the shape it claims ---------------------------
    IS_NOT = ("is_not", {
        "zh": "{where} 必须是{shape}",
        "en": "{where} must be {shape}",
    })
    KIND_IS_LIMITED_TO = ("kind_is_limited_to", {
        "zh": "{where} 的 kind 只能是 {kinds}，收到的是 {got}",
        "en": "{where}.kind is limited to {kinds}; got {got}",
    })
    VERSION_IS_LIMITED_TO = ("version_is_limited_to", {
        "zh": "{where} 的 version 只能是 {versions}，收到的是 {got}",
        "en": "{where}.version is limited to {versions}; got {got}",
    })

    # --- the bundle is well-shaped and names something it may not --------
    FIELD_IS_NOT_PATCHABLE = ("field_is_not_patchable", {
        "zh": "{where} 里有 {field}，补丁改不了这个字段；能改的是 {legal}",
        "en": "{where} holds {field}, which a patch cannot set; the fields "
              "it can set are {legal}",
    })
    NO_STANDARD_TO_TAKE = ("no_standard_to_take", {
        "zh": "{where} 把 {named} 列成了「取标准操作化」，可这些字段没有标准"
              "可取——填不上的地方，一个默认值就是一个猜测穿着答案的衣服。"
              "有标准可取的是 {legal}",
        "en": "{where} lists {named} as answered by the standard "
              "operationalisation, and those fields have no standard to "
              "take — where there is none, a default is a guess wearing the "
              "same word as an answer. The ones that have one are {legal}",
    })

    # --- the bundle is well-shaped and the program will not take it ------
    SKELETONS_ARE_STILL_EMPTY = ("skeletons_are_still_empty", {
        "zh": "还有 {count} 个骨架的 value 是 null（第 {indices} 个）；"
              "空着的骨架合并进去就是一个没人填的参数被当成填过了",
        "en": "{count} skeleton(s) still have value=null (at {indices}); "
              "merging one in is a parameter nobody filled being taken as "
              "filled",
    })
    NO_DECLARATION_TO_PATCH = ("no_declaration_to_patch", {
        "zh": "补丁要改 {predicate}，可程序里没有这个谓词的 variableDeclaration。"
              "补丁是补丁不是声明——要引入一个新谓词，先写一条 "
              "variableDeclaration",
        "en": "the patch is for {predicate}, and the program has no "
              "variableDeclaration for it. A patch is a patch and not a "
              "declaration — introduce a new predicate by writing a "
              "variableDeclaration first",
    })
    FIELD_IS_ALREADY_SET_DIFFERENTLY = (
        "field_is_already_set_differently", {
            "zh": "{predicate} 的 {field} 已经是 {existing}，补丁要把它改成 "
                  "{incoming}。框架化是填空不是改写——真要改，改声明本身",
            "en": "{predicate}'s {field} is already {existing} and the patch "
                  "sets it to {incoming}. Framing fills gaps rather than "
                  "rewriting them — to change it, change the declaration",
        })
    FIELD_IS_ANSWERED_TWICE = ("field_is_answered_twice", {
        "zh": "{predicate} 的 {field} 一边给了值、一边列进了 defaulted。"
              "这是对同一个问题的两个回答：一个字段要么由值回答，要么由标准"
              "操作化回答",
        "en": "{predicate}'s {field} both carries a value and is listed as "
              "defaulted. Those are two answers to one question: a field is "
              "answered by a value or by the standard operationalisation",
    })


class MalformedBundleError(language.Voiced, ValueError):
    """The bundle does not have the shape a bundle has.

    One class for both bundle kinds. There were two, one per module, with
    the same name and the same job — and nothing ever caught one and let
    the other through, which is what a second class would have been for.
    ``kernel``'s own docstring already named a single
    ``MalformedBundleError`` for both.

    A :class:`themis.language.Voiced`, so a caller catches this to learn
    THAT the bundle was unusable and reads :attr:`species` to learn what
    about it.
    """


def envelope(bundle, *, kind: str, key: str) -> list:
    """The records inside one bundle, having checked it is one.

    ``kind`` names which bundle this is meant to be and ``key`` the field
    its records live under — the pair that is all the two kinds differ by.
    """
    if not isinstance(bundle, dict):
        raise MalformedBundleError(Refuses.IS_NOT, where="bundle",
                                   shape=Shape.DICT)
    if bundle.get("kind") != kind:
        raise MalformedBundleError(Refuses.KIND_IS_LIMITED_TO, where="bundle",
                                   kinds=[kind], got=bundle.get("kind"))
    if bundle.get("version") != VERSION:
        raise MalformedBundleError(Refuses.VERSION_IS_LIMITED_TO,
                                   where="bundle", versions=[VERSION],
                                   got=bundle.get("version"))
    records = bundle.get(key)
    if not isinstance(records, list):
        raise MalformedBundleError(Refuses.IS_NOT, where=f"bundle.{key}",
                                   shape=Shape.LIST)
    return records
