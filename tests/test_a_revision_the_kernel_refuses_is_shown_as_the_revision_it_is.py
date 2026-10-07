"""A revision the kernel refuses is shown as the revision it is.

#824. The reader typed a correction under a twenty-variable result and
pressed the button, and saw one red line appear and nothing else: the
same graph, the same result. The revision had been made — a model revised
the program as asked and the kernel refused to run it, for asking more
cells than it lists — but the page had no way to show "a program and no
result": the refused program came back with the refusal and was dropped,
and the sentence sat under the input with nothing saying what it was
about.

Now a refused revision is shown the way a revision that ran is: what the
reader said, what it changed (computed from the program before and the
refused one), why the kernel would not run it, and what to do. The
refused program goes on the canvas, so the result below is the old one
and says so, and the reader can go on editing there and re-run, or
restore the original.
"""
from __future__ import annotations

from tests import web_source

CORRECTION = web_source.read(web_source.SRC / "components" / "Correction.tsx")
RESULT_VIEW = web_source.read(web_source.SRC / "components" / "ResultView.tsx")
RESULT_GRAPH = web_source.read(web_source.SRC / "components" / "ResultGraph.tsx")
STYLES = web_source.read(web_source.SRC / "styles.css")


def test_a_refusal_that_carries_the_revised_program_is_kept_as_a_revision():
    assert "const after = (e as KernelError)?.program" in CORRECTION
    assert "setRefused({ said: text, before: program, after, why: errorText(e, lang) })" in CORRECTION
    assert "onRefused?.(after)" in CORRECTION
    # One with no program is still the one line it was.
    assert "} else setError(errorText(e, lang))" in CORRECTION


def test_it_is_said_like_a_revision_that_ran_with_why_it_did_not():
    words = web_source.words_map("SAYS", CORRECTION)
    for key in ("refused", "onCanvas"):
        assert set(words[key]) == {"zh", "en"}, key
    block = CORRECTION.split("{refused ? (", 1)[1].split(") : null}", 1)[0]
    assert "whatChanged(refused.before, refused.after, lang)" in block
    assert "fill(SAYS.refused, lang)" in block and "{refused.why}" in block
    assert "fill(SAYS.onCanvas, lang)" in block
    assert 'role="alert"' in block


def test_what_a_revision_changed_is_computed_once_for_both():
    assert CORRECTION.count("whatChanged(") == 3  # the definition, the revision that ran, the refused one
    assert "whatChanged(revision.before, revision.after, lang)" in CORRECTION


def test_the_refused_program_goes_on_the_canvas_and_a_new_result_clears_it():
    assert "onRefused={setDraft}" in RESULT_VIEW
    assert "draft={draft}" in RESULT_VIEW
    reset = RESULT_VIEW.split("useEffect(() => {\n    setResult(payload.result)", 1)[1].split("}, [payload])", 1)[0]
    assert "setDraft(undefined)" in reset
    assert "useEffect(() => { if (draft) ref.current?.reseed(draft) }, [draft])" in RESULT_GRAPH


def test_the_refused_revision_is_marked_as_such():
    assert ".correction__refused" in STYLES
