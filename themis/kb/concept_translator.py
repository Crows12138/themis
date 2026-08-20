"""Concept-string translation for edge-verification KB lookup.

Distinct from ``translator.py`` (which handles ``DataGap -> KBQuery``
for probability-filling). This module handles ``atom_predicate ->
concept_variants`` for matching against string-keyed KGs like CauseNet.

Three tiered layers, in decreasing-confidence order:

- **L1 normalize** (always on): deterministic surface normalization —
  lowercase / strip / dash-to-underscore / whitespace-to-underscore.
  Variants from L1 are equivalent up to formatting.
- **L2 morphological** (always on): plural/singular and gerund/noun
  variants of the last word. Stdlib only — no external corpus.
- **L3 WordNet synonyms** (optional): true synonyms via nltk WordNet.
  Returns empty tuple if ``nltk`` or the WordNet corpus is unavailable
  (graceful fallback — caller still gets L1+L2).

L4 (semantic embedding suggest) is intentionally NOT implemented here:
the design contract (decided with user 2026-05-25) is that semantic
matches must NEVER silently substitute — they are suggest-only and
belong in a separate API surface in the adapter layer.

Caller flow (in the CauseNet-MCP adapter)::

    variants = translate_concept("vaccinating").variants
    for v in variants:
        hit = kb.query_edge(v, effect_concept)
        if hit:
            return hit  # first match wins (L1 > L2 > L3 by ordering)
    return None
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConceptVariants:
    """Ordered variants of a concept string.

    ``variants`` is deduplicated and ordered: L1 normalized form first,
    then L2 morphological derivatives, then L3 WordNet synonyms.
    Callers try them in order and stop at the first KB hit.

    ``layers_used`` records which layers contributed (e.g. ``('L1',)``
    when nothing beyond normalization applied). Useful for the adapter
    to surface "matched_via" provenance.
    """

    original: str
    variants: tuple[str, ...]
    layers_used: tuple[str, ...]


# ---------------------------------------------------------------------------
# L1 — normalize
# ---------------------------------------------------------------------------


def normalize_concept(s: str) -> str:
    """L1 normalization — deterministic, lossless equivalence class.

    Strategy: lowercase, treat dashes as whitespace, collapse all
    whitespace runs to a single space, replace remaining spaces with
    underscores. Order matters — dashes go to whitespace first so a
    spaced dash ("heart - disease") collapses correctly. Idempotent.

    Examples::

        normalize_concept("  Lung   Cancer  ")   -> "lung_cancer"
        normalize_concept("ACE-inhibitor")       -> "ace_inhibitor"
        normalize_concept("Heart - Disease")     -> "heart_disease"
        normalize_concept("Vaccine")             -> "vaccine"
    """
    s = s.strip().lower()
    s = s.replace("-", " ")   # dash acts like whitespace separator
    s = " ".join(s.split())   # collapse runs of whitespace
    s = s.replace(" ", "_")
    return s


# ---------------------------------------------------------------------------
# L2 — morphological
# ---------------------------------------------------------------------------


_IRREGULAR_PLURAL_TO_SINGULAR: dict[str, str] = {
    "children": "child",
    "men": "man",
    "women": "woman",
    "mice": "mouse",
    "feet": "foot",
    "teeth": "tooth",
    "people": "person",
    "geese": "goose",
}


def morphological_variants(normalized: str) -> tuple[str, ...]:
    """L2 — heuristic plural/singular and gerund/noun forms of the
    last word in the underscore-joined concept string.

    Operates on the last token only (e.g. ``"heart_attacks"`` -> swap
    ``attacks``, leave ``heart``). Stdlib only; no external lemmatizer.
    Returns deduplicated tuple, excluding the input itself.

    Examples::

        morphological_variants("vaccines")    includes "vaccine"
        morphological_variants("vaccinating") includes "vaccinate"
        morphological_variants("smoke")       includes "smoking", "smokes"
    """
    parts = normalized.split("_")
    if not parts:
        return ()
    last = parts[-1]
    if not last:
        return ()
    prefix = parts[:-1]

    out: list[str] = []
    seen: set[str] = {normalized}

    def add(new_last: str) -> None:
        if not new_last:
            return
        candidate = "_".join(prefix + [new_last])
        if candidate not in seen:
            seen.add(candidate)
            out.append(candidate)

    # Irregular plural -> singular
    if last in _IRREGULAR_PLURAL_TO_SINGULAR:
        add(_IRREGULAR_PLURAL_TO_SINGULAR[last])

    # Regular plural -> singular
    if last.endswith("ies") and len(last) > 3:
        add(last[:-3] + "y")
    if last.endswith("es") and len(last) > 2:
        add(last[:-2])
    if last.endswith("s") and len(last) > 1 and not last.endswith("ss"):
        add(last[:-1])

    # Singular -> plural
    if not last.endswith("s"):
        if last.endswith("y") and len(last) > 1 and last[-2] not in "aeiou":
            add(last[:-1] + "ies")
        elif last.endswith(("x", "z", "sh", "ch")):
            add(last + "es")
        else:
            add(last + "s")

    # Gerund (X-ing) -> base + variant ending in 'e'
    if last.endswith("ing") and len(last) > 4:
        stem = last[:-3]
        add(stem)
        add(stem + "e")

    # Base -> gerund (best-effort, no double-consonant rule)
    if not last.endswith("ing"):
        if last.endswith("e") and len(last) > 1:
            add(last[:-1] + "ing")
        else:
            add(last + "ing")

    return tuple(out)


# ---------------------------------------------------------------------------
# L3 — WordNet synonyms (optional)
# ---------------------------------------------------------------------------


def wordnet_synonyms(normalized: str) -> tuple[str, ...]:
    """L3 — synonyms via nltk WordNet.

    Returns empty tuple if nltk is not installed or the WordNet corpus
    is not downloaded — graceful fallback so the L1+L2 path still works
    on a bare install.

    Sense-collapsed: all synsets are unioned together (we don't know
    which sense the user means). Downstream callers should treat L3
    variants as weaker matches and lean on the structural disambiguation
    surface (source_title distribution) when resolving.
    """
    try:
        from nltk.corpus import wordnet
    except ImportError:
        return ()

    word_with_spaces = normalized.replace("_", " ")
    try:
        synsets = wordnet.synsets(word_with_spaces)
    except LookupError:
        # corpus not downloaded
        return ()

    seen: set[str] = {normalized}
    out: list[str] = []
    for synset in synsets:
        for lemma in synset.lemmas():
            name = lemma.name().lower()
            name = name.replace(" ", "_")  # WordNet returns underscores already
            if name and name not in seen:
                seen.add(name)
                out.append(name)
    return tuple(out)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def translate_concept(
    concept: str,
    *,
    use_wordnet: bool = True,
) -> ConceptVariants:
    """Generate ordered variant list for KB lookup.

    Ordering: L1 normalized first, then L2 morphological, then L3
    WordNet synonyms (if available and ``use_wordnet`` is True).
    Duplicates removed. Caller tries variants in order, stopping at
    the first KB hit.

    Args:
        concept: raw concept string (typically ``atom.predicate``).
        use_wordnet: enable L3. Defaults True. Set False to keep
            queries purely structural (e.g. for byte-deterministic tests).
    """
    ordered: list[str] = []
    seen: set[str] = set()
    layers: list[str] = []

    # L1
    l1 = normalize_concept(concept)
    ordered.append(l1)
    seen.add(l1)
    layers.append("L1")

    # L2
    l2_added = False
    for v in morphological_variants(l1):
        if v not in seen:
            seen.add(v)
            ordered.append(v)
            l2_added = True
    if l2_added:
        layers.append("L2")

    # L3
    if use_wordnet:
        l3_added = False
        for v in wordnet_synonyms(l1):
            if v not in seen:
                seen.add(v)
                ordered.append(v)
                l3_added = True
        if l3_added:
            layers.append("L3")

    return ConceptVariants(
        original=concept,
        variants=tuple(ordered),
        layers_used=tuple(layers),
    )
