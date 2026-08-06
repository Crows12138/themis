# -*- coding: utf-8 -*-
"""What an estimate is worth, said on both surfaces or on neither.

The report has one function for the lines every answer shape shares —
how it was computed, how precise it is, and what would overturn it — put
in one place so a shape bound later cannot ship without them. The browser
had three of those lines and not the other three, and the two it was
missing are the pair that only means anything together: the precision
hint says how many more subjects halve the interval, and the
measurement-error line says which part of that interval no number of
subjects removes. A reader given only the first goes and buys the wrong
thing.

Counting one surface says a discipline exists. Counting both says it was
applied, and those look identical from inside either one.
"""
from __future__ import annotations

import inspect
import re

from . import web_source
from themis.output import analysis_report


#: Envelope fields the report's shared estimate lines read. Written out
#: rather than only derived, so a field dropped from the report shows up
#: here as a disagreement instead of quietly shrinking what is required
#: of the browser.
REPORT_READS: frozenset[str] = frozenset({
    "method", "sample_size", "adjustment",
    "precision_budget", "se_inflation", "noise_share",
    "sensitivity_analysis",
})

#: Read by the browser somewhere other than its estimate-metadata rows,
#: because they belong to a different part of the answer there. Each is
#: named with where it went, so "the browser reads it" stays checkable.
ELSEWHERE_ON_THE_BROWSER: dict[str, str] = {
    "method": "printed in the figure caption beside the number",
    "adjustment": "printed under the number with the interval",
    "sensitivity_analysis": "its own E-value block in the foldout",
}


def _report_reads() -> set[str]:
    """The keys ``_estimate_meta`` pulls out of the envelope."""
    src = inspect.getsource(analysis_report._estimate_meta)
    return set(re.findall(r"""\.get\(["'](\w+)["']""", src)) | set(
        re.findall(r"""\[["'](\w+)["']\]""", src)
    )


def test_the_report_still_reads_what_this_module_says_it_does():
    """The pin above is only worth having while it matches."""
    actual = _report_reads()
    missing = REPORT_READS - actual
    assert not missing, (
        f"_estimate_meta no longer reads {sorted(missing)}; if a line was "
        f"removed from the report, remove it here too — silently shrinking "
        f"this set relaxes what the browser is held to"
    )


def test_the_browser_says_everything_the_report_says_about_an_estimate():
    """Each field either appears in the browser's own metadata rows or is
    named in the exemption list with where it went instead."""
    meta_src = web_source.read(web_source.VERDICT)
    body = meta_src.split("export function estimateMeta", 1)
    assert len(body) == 2, "verdict.ts declares no estimateMeta"
    # Up to the next top-level export, which is where the function ends.
    fn = re.split(r"\n(?:export |// The shapes)", body[1], maxsplit=1)[0]

    for field in sorted(REPORT_READS):
        if field in ELSEWHERE_ON_THE_BROWSER:
            continue
        assert field in fn, (
            f"the report's estimate lines read {field!r} and the browser's "
            f"do not; either render it or say in ELSEWHERE_ON_THE_BROWSER "
            f"which part of this surface carries it"
        )


def test_the_exemptions_name_a_place_and_are_true():
    """An exemption that points nowhere is the list growing instead of
    the surface. Each field has to be read somewhere in the web source."""
    src = "\n".join(
        p.read_text(encoding="utf-8")
        for p in web_source.SRC.rglob("*.ts*")
    )
    for field, where in ELSEWHERE_ON_THE_BROWSER.items():
        assert where.strip(), f"{field} is exempt for no stated reason"
        assert field in src, (
            f"{field} is exempt as {where!r}, and the browser source never "
            f"names it"
        )


def test_the_two_lines_that_only_mean_anything_together_are_not_separable():
    """The report prints the measurement-error line next to the precision
    hint on purpose, and says so. This holds the browser to the same
    adjacency rather than to merely having both somewhere."""
    fn = web_source.read(web_source.VERDICT).split(
        "export function estimateMeta", 1)[1]
    precision = fn.find("precision_budget")
    inflation = fn.find("se_inflation")
    assert precision > 0 and inflation > 0
    assert precision < inflation, (
        "the measurement-error line comes before the precision hint; the "
        "hint says what more subjects buy, and this says which part of the "
        "width they cannot — reading them in that order is the point"
    )
    between = fn[precision:inflation]
    assert "rows.push" in between and between.count("rows.push") == 1, (
        "something was inserted between the precision hint and the "
        "measurement-error line"
    )
