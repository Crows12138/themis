"""D.1 — concept_translator: L1 normalize, L2 morphological, L3 WordNet.

WordNet (L3) tests are skipped when the corpus is not available, so the
suite stays green on a bare install. L1+L2 must always work — stdlib only.
"""
from __future__ import annotations

import pytest

from themis.kb.concept_translator import (
    ConceptVariants,
    morphological_variants,
    normalize_concept,
    translate_concept,
    wordnet_synonyms,
)


# ============================================ L1 normalize


def test_normalize_lowercases() -> None:
    assert normalize_concept("Lung Cancer") == "lung_cancer"


def test_normalize_strips_outer_whitespace() -> None:
    assert normalize_concept("  smoking  ") == "smoking"


def test_normalize_collapses_internal_whitespace() -> None:
    assert normalize_concept("heart   attack") == "heart_attack"


def test_normalize_dashes_to_underscores() -> None:
    assert normalize_concept("ACE-inhibitor") == "ace_inhibitor"


def test_normalize_idempotent() -> None:
    once = normalize_concept("Heart - Disease")
    twice = normalize_concept(once)
    assert once == twice == "heart_disease"  # spaced dash collapses cleanly


def test_normalize_already_normalized() -> None:
    assert normalize_concept("lung_cancer") == "lung_cancer"


# ============================================ L2 morphological


def test_morphological_regular_plural_drop_s() -> None:
    out = morphological_variants("vaccines")
    assert "vaccine" in out


def test_morphological_irregular_plural() -> None:
    out = morphological_variants("children")
    assert "child" in out


def test_morphological_ies_to_y() -> None:
    out = morphological_variants("therapies")
    assert "therapy" in out


def test_morphological_singular_to_plural() -> None:
    out = morphological_variants("vaccine")
    assert "vaccines" in out


def test_morphological_y_to_ies() -> None:
    out = morphological_variants("therapy")
    assert "therapies" in out


def test_morphological_gerund_to_base() -> None:
    out = morphological_variants("vaccinating")
    # 'vaccinat' or 'vaccinate' — both produced; the 'e'-version is the
    # one that matches CauseNet
    assert "vaccinate" in out


def test_morphological_base_to_gerund() -> None:
    out = morphological_variants("smoke")
    assert "smoking" in out


def test_morphological_excludes_input() -> None:
    """Variants must not include the input verbatim."""
    out = morphological_variants("smoking")
    assert "smoking" not in out


def test_morphological_only_last_word() -> None:
    """Multi-word concept: only last token swapped."""
    out = morphological_variants("heart_attacks")
    assert "heart_attack" in out
    # 'heart' itself untouched
    assert all(v.startswith("heart_") for v in out)


def test_morphological_empty_safe() -> None:
    assert morphological_variants("") == ()


def test_morphological_ss_word_not_stripped() -> None:
    """'stress' should NOT be reduced to 'stres' (ss is not plural-s)."""
    out = morphological_variants("stress")
    assert "stres" not in out


# ============================================ L3 WordNet (optional)


def _wordnet_available() -> bool:
    try:
        from nltk.corpus import wordnet  # type: ignore[import-not-found]
        wordnet.synsets("test")
        return True
    except (ImportError, LookupError):
        return False


@pytest.mark.skipif(not _wordnet_available(), reason="nltk wordnet not installed")
def test_wordnet_returns_synonyms_when_available() -> None:
    out = wordnet_synonyms("cancer")
    # 'cancer' has well-known synsets including 'malignancy', 'crab'
    # (the zodiac sign). We don't pin specifics — just non-empty.
    assert len(out) > 0


def test_wordnet_graceful_when_unavailable() -> None:
    """When nltk is missing OR corpus not downloaded, returns ()
    rather than raising. Crucial for bare-install graceful fallback."""
    # We can't easily simulate missing nltk in a clean way, but the
    # function MUST not raise for any input.
    result = wordnet_synonyms("this_is_almost_certainly_not_a_wordnet_concept_xyz")
    assert isinstance(result, tuple)


# ============================================ translate_concept (top-level)


def test_translate_l1_only_when_no_morphology() -> None:
    """A single-letter or non-decomposable string: L1 only."""
    out = translate_concept("x", use_wordnet=False)
    assert "L1" in out.layers_used
    # 'x' may still get a plural 'xs' or 'xes' from L2, that's OK


def test_translate_l1_and_l2() -> None:
    out = translate_concept("vaccinating", use_wordnet=False)
    assert "L1" in out.layers_used
    assert "L2" in out.layers_used
    assert out.variants[0] == "vaccinating"  # L1 first
    assert "vaccinate" in out.variants


def test_translate_dedupes_across_layers() -> None:
    """If L2 happens to produce L1's output, no duplicates."""
    out = translate_concept("vaccine", use_wordnet=False)
    assert len(out.variants) == len(set(out.variants))


def test_translate_l1_first_in_order() -> None:
    """L1 variant must always be the first entry (highest confidence)."""
    out = translate_concept("Smoking", use_wordnet=False)
    assert out.variants[0] == "smoking"


def test_translate_original_preserved() -> None:
    out = translate_concept("  Heart  Attack  ", use_wordnet=False)
    assert out.original == "  Heart  Attack  "
    assert out.variants[0] == "heart_attack"


def test_translate_use_wordnet_false_skips_l3() -> None:
    out = translate_concept("cancer", use_wordnet=False)
    assert "L3" not in out.layers_used


@pytest.mark.skipif(not _wordnet_available(), reason="nltk wordnet not installed")
def test_translate_includes_l3_when_available() -> None:
    out = translate_concept("cancer", use_wordnet=True)
    assert "L3" in out.layers_used
    assert len(out.variants) > 1


def test_translate_returns_concept_variants_dataclass() -> None:
    out = translate_concept("foo", use_wordnet=False)
    assert isinstance(out, ConceptVariants)
    assert isinstance(out.variants, tuple)
    assert isinstance(out.layers_used, tuple)
