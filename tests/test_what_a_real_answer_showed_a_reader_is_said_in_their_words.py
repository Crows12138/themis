"""What three real answers showed a reader, said in the reader's words.

#816. #815 gave variables names and showed them wherever its author knew a
variable was printed. Three questions were then asked of the live site and
each answer opened on the page, with everything a reader is shown outside
the raw JSON searched for what is not a reader's word. It found 115 places
a variable was still printed by its identifier, and 301 internal tokens.

This holds the first of those to none, and takes the three tokens the page
printed beside every result out of the reader's way:

- the rows a name never reached — an interval's two bound expressions, the
  rows of the "how this was worked out" fold, the lines under a gap, and
  the plain-language reading the model writes;
- three things about how the kernel writes a variable, which a name alone
  did not undo: the objects an atom is about (``sleep(me)``), a sum's index
  (``Σ_sleep``, one token to a tokeniser), and a yes-or-no value written as
  a Python literal beside a Chinese name;
- the status token, the gap-kind token and the refusal's species, which
  were printed in monospace beside their own reader's words on every
  result. They are an address for somebody reading the JSON, and are kept
  on hover.

The browser cannot be imported, so what is pinned is its source. The
behaviour was measured on the page: after this, the same three answers
show no variable by its identifier.
"""
from __future__ import annotations

import pytest

from tests import web_source

SRC = web_source.SRC


def _code(*parts: str) -> str:
    return web_source.without_comments(web_source.read(SRC.joinpath(*parts)))


# ------------------------------------------------- how a variable is written

def test_the_objects_an_atom_is_about_go_with_its_identifier():
    names = _code("lib", "names.ts")
    # Constants only between the brackets, so P(y) and do(x=True) are not atoms.
    assert (r"const ATOM = /([A-Za-z_][A-Za-z0-9_]*)\(([A-Za-z0-9_]+"
            r"(?:,\s*[A-Za-z0-9_]+)*)\)/g") in names
    named = web_source.chunks(names)["named"]
    # And only for a variable that has a name: an atom nobody named is left.
    assert (".replace(ATOM, (whole, token: string) => "
            "(names.has(token) ? token : whole))") in named


def test_a_sums_index_is_the_variable_after_the_underscore():
    named = web_source.chunks(_code("lib", "names.ts"))["named"]
    assert "const bare = token.replace(/^_+/, '')" in named
    assert "token.slice(0, token.length - bare.length) + under" in named


def test_a_yes_or_no_is_said_in_the_readers_language_beside_a_name():
    names = _code("lib", "names.ts")
    assert "zh: { yes: '是', no: '否' }" in names
    assert "en: { yes: 'yes', no: 'no' }" in names
    named = web_source.chunks(names)["named"]
    # Only in a string a name was found in, and only for the names in force:
    # a string nobody named anything in comes back untouched.
    assert "if (!changed) return text" in named
    assert "if (!inLang || names !== inForce) return out" in named
    # The language is said with the names.
    assert "showNames(names, lang)" in _code("components", "ResultView.tsx")


# -------------------------------------------------- the rows a name missed

@pytest.mark.parametrize("component, printed", [
    ("Verdict.tsx", "{named(b.lower_expression)}"),
    ("Verdict.tsx", "{named(b.upper_expression)}"),
    ("Verdict.tsx", '<dd className="estmeta__v">{shown(r.value)}</dd>'),
    ("Verdict.tsx", '<span className="boundsexpr__v">{shown(said)}</span>'),
    ("GapReport.tsx", "{named(line.text)}"),
    ("ResultView.tsx", '<p className="reply__body">{named(reply)}</p>'),
])
def test_a_row_a_real_answer_printed_an_identifier_in_is_said_by_name(
        component, printed):
    assert printed in _code("components", component)


def test_every_row_of_the_worked_out_fold_is_said_by_name():
    verdict = _code("components", "Verdict.tsx")
    assert verdict.count(
        '<span className="boundsexpr__v">{shown(row.value)}</span>') == 3
    assert "{row.value}" not in verdict


# ------------------------------------------------ the three printed tokens

def test_the_status_token_is_kept_on_hover_and_not_printed():
    verdict = _code("components", "Verdict.tsx")
    assert '<span className="statuschip" title={result.status}>' in verdict
    assert '<span className="mono">{result.status}</span>' not in verdict


def test_the_gap_kind_token_is_kept_on_hover_and_not_printed():
    gaps = _code("components", "GapReport.tsx")
    assert ('<span className="gap__kindtitle" title={g.kind}>'
            "{gapTitle(g.kind, lang)}</span>") in gaps
    assert 'className="gap__kind"' not in gaps
    assert ".gap__kind {" not in web_source.read(SRC / "styles.css")


def test_the_refusals_species_is_kept_on_hover_and_not_printed():
    verdict = _code("components", "Verdict.tsx")
    assert ('<span className="boundsexpr__v" '
            "title={result.estimator_failure.failure_type}>") in verdict
    assert "{result.estimator_failure.failure_type}</span>" not in verdict
