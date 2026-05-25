# Coverage probe — precision vs full

Date: 2026-05-25
Build: precision 197,806 edges (602MB) + full 11,609,890 edges (11GB)

## Headline

| Tier | Hit rate on 20-query benchmark |
|---|---|
| Tier 1 (precision, ~83% precision) | **60%** (12/20) |
| Tier 2 (full, ~60-70% est.) — additional | **+5%** (1/20) |
| Combined | **65%** (13/20) |
| Not found | 35% (7/20) |

## Per-query result

| cause | effect | precision hits | full hits | tier |
|---|---|---|---|---|
| aspirin | bleeding | 111 | 111 | high_confidence |
| smoking | lung_cancer | 1690 | 1690 | high_confidence |
| exercise | weight_loss | 84 | 84 | high_confidence |
| medication | heart_condition | — | — | not_found |
| food_sharing | workplace_warmth | — | — | not_found |
| minimum_wage | unemployment | 75 | 75 | high_confidence |
| class_size | test_scores | — | — | not_found |
| caffeine | productivity | — | — | not_found |
| obesity | diabetes | 585 | 585 | high_confidence |
| alcohol | liver_disease | 113 | 113 | high_confidence |
| vaccine | immunity | — | — | not_found |
| inflation | unemployment | 26 | 26 | high_confidence |
| trade_war | recession | — | — | not_found |
| automation | job_loss | 3 | 3 | high_confidence |
| deforestation | climate_change | 35 | 35 | high_confidence |
| pollution | asthma | 35 | 35 | high_confidence |
| homework | learning | — | — | not_found |
| overtime | burnout | — | 1 | **extracted (full only)** |
| rain | flood | 33 | 33 | high_confidence |
| stress | insomnia | 338 | 338 | high_confidence |

## Key finding — translator > KB size for ROI

**Going from 197K (precision) to 11M (full) only buys +5% coverage** on
this 20-query benchmark. The remaining 35% miss rate is bottlenecked by
**translator / synonym / composite-concept** handling, NOT by KB size.

Concrete examples of likely-translator misses:

| Query | Likely CauseNet representation |
|---|---|
| `vaccine → immunity` | almost-certainly present as `vaccination → immune_response` or similar |
| `caffeine → productivity` | almost-certainly present as `caffeine → alertness` |
| `medication → heart_condition` | `medication` is too abstract — drug-level concepts (`aspirin`, `statin`) are how CauseNet indexes |
| `food_sharing → workplace_warmth` | composite concepts NOT in CauseNet's linguistic-pattern extraction scope |
| `class_size → test_scores` | education-domain coverage gap, likely won't help even with synonyms |
| `trade_war → recession` | event-level (vs. mechanism-level) concept, also a coverage gap |
| `homework → learning` | education-domain gap |

## Implication for Phase D (Themis-side adapter)

`themis/kb/translator.py` is the high-ROI investment, not "get a bigger
KG". Concrete priorities for Phase D:

1. **Lemmatization / stemming** — `vaccines` → `vaccine`, `vaccinating` → `vaccinate`
2. **WordNet synonym expansion** — query `aspirin` → also try
   `acetylsalicylic_acid`, query `cancer` → also try `malignancy`
3. **Light morphological variations** — singular/plural, gerund/noun
4. **Fallback strategy on miss** — try variant strings, report which
   variant matched (provenance for the match)

Estimated coverage lift from translator work: +15-25 percentage points
(vs. only +5pp from going to 11M).

## Recommendation for default tier configuration

Given how marginal the full-version lift is on real queries (+5% on this
benchmark), recommend that:

- **Default deployment**: precision DB only (smaller footprint, 83%
  precision, gets most of the value)
- **Full DB**: optional opt-in for users who need maximum recall and
  can tolerate the larger storage (11GB SQLite) + lower precision
  (~60-70% extracted tier)

`build_server` already supports either or both — no code change needed.

## Build artifacts (gitignored)

- `data/causenet-precision.jsonl.bz2` (132 MB compressed)
- `data/causenet-precision.sqlite` (602 MB)
- `data/causenet-full.jsonl.bz2` (536 MB compressed)
- `data/causenet-full.sqlite` (11 GB)

Total disk: ~12 GB. Most users will only need the 602 MB precision DB.
