"""What a value handed to this build was supposed to be.

A vocabulary of NOUNS, not of sentences. Each member goes in a HOLE — "{where}
must be {shape}" — and that hole is why it is a :class:`themis.language.Word`
rather than a token: stringifying ``DICT`` into a Chinese sentence puts an
English word in it, which is the one thing the sentence tables exist to stop.
The alternative is one species per shape, which is seven near-identical
sentences differing by a noun, and an eighth on the day an eighth shape is
checked.

**Here rather than in the package that first needed it.** These were written
for the LLM-side front door and named after it (``extraction_shape``). Then a
second front door — the one that takes a filled bundle back from a surface —
turned out to check the same three: a dict, a list, a non-empty string. A
noun set that two doors read is not either door's, and copying three words
into a second table would have made the two tables free to drift into two
Chinese renderings of "a dict".

Nobody MATCHES on a member of this set, which is what makes it shareable
where a species table is not. A caller reads ``exc.species`` and switches on
it, and a switch wants one closed enum per channel; a word in a slot is only
ever read, so one table for the whole build is the smaller thing.
"""
from __future__ import annotations

from enum import unique

from . import language


@unique
class Shape(language.Word, vocabulary="shape",
            between=language.BETWEEN_ITEMS):
    """What a field was supposed to be."""

    DICT = ("dict", {"zh": "一个字典", "en": "a dict"})
    LIST = ("list", {"zh": "一个列表", "en": "a list"})
    STRING = ("string", {"zh": "一个字符串", "en": "a string"})
    NON_EMPTY_STRING = ("non_empty_string",
                        {"zh": "一个非空字符串", "en": "a non-empty string"})
    NAME_AND_VALUE = ("name_and_value", {
        "zh": "一个带 name 和 value 的字典",
        "en": "a dict with a name and a value",
    })
    FROM_TO_PAIR = ("from_to_pair", {
        "zh": "一个 [起点, 终点] 的二元组",
        "en": "a [from, to] pair",
    })
    NON_EMPTY_LIST_OF_NAMES = ("non_empty_list_of_names", {
        "zh": "一个非空的名字列表",
        "en": "a non-empty list of names",
    })
    LIST_OF_FIELD_NAMES = ("list_of_field_names", {
        "zh": "一个字段名的列表",
        "en": "a list of field names",
    })
