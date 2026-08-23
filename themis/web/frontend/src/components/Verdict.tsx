import type { QueryResult } from '../types'
import { tierMeta, statusLabel, statusBlurb, fmtNum, structuralReadout, cleanPathNode, answerRows, answerBlockRows, routeRows, derivationRows, numericDetailRows, citations, refusalKind, remedyRoutes, assumptionSeverityLabel, ledgerLayerLabel, ledgerProvenanceLabel, estimateMeta, boundsEstimandLabel, boundsContrastLabel, tightnessLabel, tightnessAdvice, intervalWidthAdvice, evalueBandLabel, evalueBandBasisLabel } from '../lib/verdict'
import { fmtFormula } from '../lib/formula'
import { fill, say, useLang, type Words } from '../lib/language'
import { Foldout } from './Foldout'

const SEGS = [0, 1, 2]

const SAYS = {
  region: { zh: '判决', en: 'Verdict' },
  strongest: { zh: '能给的最强答案', en: 'The strongest answer available' },
  naiveTag: { zh: '✕ 未调整 · 粗相关', en: '✕ Unadjusted · raw association' },
  naiveNote: { zh: '直接对比两组——被混杂带偏', en: 'The two groups compared directly — confounding pulls it off' },
  adjustedTag: { zh: '✓ Themis 调整后', en: '✓ Adjusted by Themis' },
  // The braces stay in the slot value, not in the sentence: they are set
  // notation, the same mark in both languages, and `fill` has no escape for
  // a literal brace because a sentence has no reason to want one.
  adjustedFor: { zh: ' · 调整 {vars}', en: ' · adjusted for {vars}' },
  tightness: { zh: '紧度', en: 'Tightness' },
  widthIs: {
    zh: '这几条区间的宽度：{advice}。',
    en: 'About the width of these intervals: {advice}.',
  },
  compareLesson: {
    zh: '两个数明显不同 —— 混杂在作怪。这就是为什么要做因果调整，而不是直接对比。',
    en: 'The two numbers differ — that is the confounding. It is why the adjustment exists, rather than comparing the groups directly.',
  },
  numericEstimate: { zh: '数值估计', en: 'Numeric estimate' },
  pointEstimate: { zh: '点估计', en: 'Point estimate' },
  partialInterval: { zh: '区间（部分识别）', en: 'Interval (partially identified)' },
  alsoMissing: { zh: '另有一项没能给出', en: 'Something else could not be produced' },
  noNumber: { zh: '没有给出数值', en: 'No number was produced' },
  estimatorRefused: { zh: '估计器拒绝了', en: 'The estimator refused' },
  howSummary: { zh: '怎么算出来的 · 识别路线 / 公式 / 路径 / 假设', en: 'How it was computed · route / formula / paths / assumptions' },
  causalPaths: { zh: '因果路径', en: 'Causal paths' },
  supportingPaths: { zh: '支持路径', en: 'Supporting paths' },
  idFormula: { zh: '识别公式', en: 'Identification formula' },
  sources: { zh: '依据文献', en: 'Sources' },
  boundedThing: { zh: '界的对象', en: 'What is bounded' },
  interval: { zh: '区间', en: 'Interval' },
  contrastNote: {
    zh: ' · 与 {ref} 那一档相比，是另一个量而非上面两端相减',
    en: ' · against the {ref} level — a different quantity, not the two ends above subtracted',
  },
  method: { zh: '方法', en: 'Method' },
  restsOn: { zh: '靠的假设', en: 'Rests on' },
  none: { zh: '无', en: 'none' },
  lower: { zh: '下界', en: 'Lower bound' },
  upper: { zh: '上界', en: 'Upper bound' },
  uninformative: {
    zh: '⚠ 这个区间退化到 [0,1] / [-1,1]，诚实但无实际辨别力——需要更强假设或数据才能收窄。',
    en: '⚠ This interval collapses to [0,1] / [-1,1]: honest, but it separates nothing. A stronger assumption or more data is what narrows it.',
  },
  symbolic: { zh: '符号区间：把可观测分布代入即可得到数值区间。', en: 'A symbolic interval: substitute the observable distribution to get numbers.' },
  manyBounds: {
    zh: '上面 {n} 条界的是同一个量，差别只在各自允许假设什么。按你接受哪一组来读，不要取交：两条都成立时交集确实含真值，但它不是二者合取下的锐界。',
    en: 'The {n} intervals above bound the same quantity and differ only in what each was allowed to assume. Read the one whose assumptions you accept; do not intersect them — the intersection does contain the truth when both hold, but it is not the sharp bound under their conjunction.',
  },
  eValueCi: { zh: ' · CI 界 {bound}', en: ' · CI bound {bound}' },
  // What the E-value printed beside it MEANS. It stops at the definition:
  // the verdict is the line above and is read off the interval's near end,
  // which is a different question, so ending this one in "larger is more
  // robust" would be the verdict said twice and said about the wrong number.
  eValueNote: {
    zh: '敏感性：未测混杂要同时把处理与结局的风险比拉到 ≥ {e}，才能把这个点估计推到零。',
    en: 'Sensitivity: unmeasured confounding would have to move the risk ratio on both the treatment and the outcome to ≥ {e} to push this point estimate to zero.',
  },
  eValueBand: { zh: '解读：{band}（{basis}）', en: 'Reading: {band} ({basis})' },
  ledgerCap: { zh: '假设台账', en: 'Assumption ledger' },
  provenance: { zh: '来源 {who}', en: 'from {who}' },
  untestable: { zh: '不可检验', en: 'not testable' },
} satisfies Record<string, Words>

export function Verdict({ result, naive }: { result: QueryResult; naive?: number | null }) {
  const lang = useLang()
  const report = result.data_gap_report
  const tier = report?.answer_tier
  const summary = report?.summary?.trim()
  const num = result.numeric_estimate
  // Structural-layer answer (plug-in identification once θ is supplied, incl.
  // via AI priors). Only shown when there's no data-backed estimate.
  const runNum = !num && result.numeric_result?.value != null ? result.numeric_result.value : null
  // Bounded rather than pinned: `value` is null and the interval IS the
  // answer. This slot read only `value`, so a bounded counterfactual arrived
  // with its answer slot empty and its interval in the same object.
  const runInterval = !num && runNum == null ? result.numeric_result?.interval ?? null : null
  // The answer stated as a BLOCK. The theta path answers from the joint
  // distribution without ever calling an estimator, so there is no shape for
  // answerRows to find; what these paths put in numeric_result is one of the
  // block's own quantities, printed with none of their names.
  const answerBlocks = num ? [] : answerBlockRows(result.extensions, lang)
  const bounds = result.bounds_results ?? []
  const struct = result.structural_result
  const sr = !tier && struct ? structuralReadout(result.query_kind, struct.value, lang) : null
  const paths = struct?.supporting_paths?.filter((p) => p.length > 0) ?? []
  const formula = result.formula ? fmtFormula(result.formula) : null
  const sens = num?.sensitivity_analysis
  const ledger = result.extensions?.assumption_ledger
  const showCompare = num != null && num.point != null && naive != null
  const shaped = num ? answerRows(num, lang) : null
  const refusal = refusalKind(result.estimator_failure?.kind, lang)
  const remedies = remedyRoutes(result.estimator_failure?.remedies, lang)
  // Whether a number is on screen above the refusal. `estimator_failure`
  // carries two different things — why there is no number, and why something
  // SUPPLEMENTARY to the number was not produced — and every lead in the kind
  // table opens with 没有给出数值, which is a claim about the envelope that
  // only the envelope can settle. Printed above an answer that stands, it
  // contradicts the figure directly over it.
  const answerShown = showCompare || num != null || answerBlocks.length > 0
    || runNum != null || runInterval != null
  // How the estimand was identified. This foldout has been called
  // "怎么算出来的" all along while saying only the formula and the paths; the
  // ten blocks that answer that question are read here now.
  const routes = routeRows(result.extensions, lang)
  // The chain, which is the one answer to this foldout's question that every
  // answered result has. A route is written as a block only when a pattern was
  // recognised; 570 of 1627 envelopes in one suite run carried a chain and
  // this surface read none of them.
  const chain = derivationRows(result.derivation, lang)
  // The numeric half of this foldout's question. The routes above say which
  // pattern identified the estimand; these say what the estimator then did
  // with the data — a stratum table, an uncorrected number beside a corrected
  // one, two independent longitudinal routes. They live on numeric_estimate,
  // which the block binding above does not reach, so none of them had a reader.
  // Keyed by envelope path now, and taking the whole result: four route blocks
  // carry a `numeric` the theta path fills, and a table keyed by one
  // container's properties could not see any of them.
  const detail = numericDetailRows(result, lang)
  // The sources. Six containers carry a citation and no table on either
  // surface was ever about citations, so all six were dropped; this walks
  // the envelope for the same reason the report does.
  // No `lang`: a citation is the envelope's own text, quoted rather than
  // said. Translating a paper's title would be a different claim about it.
  const cites = citations(result)
  // How it was computed, how precise it is, and what more data cannot fix.
  // Visible rather than folded: two of these three say what the number is
  // worth, and a reader who never opens the foldout is exactly the reader
  // who would otherwise read the interval as tighter than it is.
  const meta = estimateMeta(num, result.outcome_error, result.estimation_context, lang)
  // The "how it was computed" detail — machine artifacts a lay reader rarely
  // needs. Folded by default; nothing removed.
  const hasDetail = routes.length > 0 || !!chain || detail.length > 0 || cites.length > 0 || paths.length > 0 || !!formula || bounds.length > 0 || sens?.e_value != null || !!ledger?.assumptions?.length

  return (
    <section className="verdict" aria-label={say(SAYS.region, lang, 'region')}>
      <div className="verdict__head">
        {tier ? (
          <div className={`readout readout--${tier}`}>
            <span className="readout__cap">{say(SAYS.strongest, lang, 'strongest')}</span>
            <span className="readout__value">
              <span className="readout__tier">{tierMeta(tier, lang).label}</span>
            </span>
            <span className="readout__bar" aria-hidden>
              {SEGS.map((i) => (
                <span key={i} className="readout__seg" />
              ))}
            </span>
            <span className="readout__gloss">{tierMeta(tier, lang).gloss}</span>
          </div>
        ) : sr ? (
          <div className={`readout readout--${sr.tone}`}>
            <span className="readout__cap">{sr.cap}</span>
            <span className="readout__value">
              <span className="readout__tier">{sr.label}</span>
            </span>
            {sr.gloss ? <span className="readout__gloss">{sr.gloss}</span> : null}
          </div>
        ) : null}

        <div className="verdict__status">
          <span className="statuschip">
            {statusLabel(result.status, lang)}
            <span className="mono">{result.status}</span>
          </span>
          {summary ? <p className="verdict__summary">{summary}</p> : null}
          {statusBlurb(result.status, lang) ? <p className="verdict__blurb">{statusBlurb(result.status, lang)}</p> : null}
        </div>
      </div>

      {/* `meta` is in this list because reading a field is not the same as
          reaching a branch: 55 envelopes in one suite run recorded a data
          contract and got no estimate, and without it every one of them
          would have computed its rows and rendered none. */}
      {showCompare || num || answerBlocks.length || runNum != null || runInterval || result.estimator_failure || meta.length || hasDetail ? (
        <div className="verdict__body">
          {/* The number IS the answer — always visible. */}
          {showCompare ? (
            <div className="compare">
              <div className="compare__col compare__col--bad">
                <span className="compare__tag">{say(SAYS.naiveTag, lang, 'naiveTag')}</span>
                <span className="compare__num mono">{fmtNum(naive)}</span>
                <span className="compare__note">{say(SAYS.naiveNote, lang, 'naiveNote')}</span>
              </div>
              <div className="compare__col compare__col--good">
                <span className="compare__tag">{say(SAYS.adjustedTag, lang, 'adjustedTag')}</span>
                <span className="compare__num mono">{fmtNum(num!.point)}</span>
                <span className="compare__note">
                  {num!.ci_lower != null && num!.ci_upper != null
                    ? `${Math.round((num!.ci_level ?? 0.95) * 100)}% CI [${fmtNum(num!.ci_lower)}, ${fmtNum(num!.ci_upper)}]`
                    : ''}
                  {num!.adjustment?.length
                    ? fill(SAYS.adjustedFor, lang, { vars: `{${num!.adjustment.join(', ')}}` })
                    : ''}
                </span>
              </div>
              <p className="compare__lesson">{say(SAYS.compareLesson, lang, 'compareLesson')}</p>
            </div>
          ) : num && shaped ? (
            /* An estimate whose estimand has no single number — a curve, a
               decomposition, a joint contrast, a bounded cell. Read through
               the same shape vocabulary the report uses; this branch used to
               not exist, so all of them rendered as one em-dash. */
            <div className="figure">
              <span className="figure__cap">{shaped.cap}{num.method ? ` · ${num.method}` : ''}</span>
              <div className="pathlist">
                {shaped.rows.map((r, i) => (
                  <div className="boundsexpr__row" key={i}>
                    <span className="boundsexpr__k">{r.label}</span>
                    <span className="boundsexpr__v mono">{r.value}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : num ? (
            <div className="figure">
              <span className="figure__cap">{say(SAYS.numericEstimate, lang, 'numericEstimate')}{num.method ? ` · ${num.method}` : ''}</span>
              <span className="figure__point mono">{fmtNum(num.point)}</span>
              {num.ci_lower != null && num.ci_upper != null ? (
                <span className="figure__ci mono">
                  {Math.round((num.ci_level ?? 0.95) * 100)}% CI · [{fmtNum(num.ci_lower)}, {fmtNum(num.ci_upper)}]
                  {num.adjustment?.length
                    ? fill(SAYS.adjustedFor, lang, { vars: `{${num.adjustment.join(', ')}}` })
                    : ''}
                </span>
              ) : null}
            </div>
          ) : answerBlocks.length ? (
            /* The answer as the envelope states it, each quantity by name.
               Above the bare figure below, which for these paths prints one
               of these same numbers with its name left off. */
            <>
              {answerBlocks.map((s, i) => (
                <div className="figure" key={`ans-${i}`}>
                  <span className="figure__cap">{s.cap}</span>
                  <div className="pathlist">
                    {s.rows.map((r, j) => (
                      <div className="boundsexpr__row" key={j}>
                        <span className="boundsexpr__k">{r.label}</span>
                        <span className="boundsexpr__v mono">{r.value}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </>
          ) : runNum != null ? (
            <div className="figure">
              <span className="figure__cap">{say(SAYS.pointEstimate, lang, 'pointEstimate')}</span>
              <span className="figure__point mono">{fmtNum(runNum)}</span>
            </div>
          ) : runInterval ? (
            <div className="figure">
              <span className="figure__cap">{say(SAYS.partialInterval, lang, 'partialInterval')}</span>
              <span className="figure__point mono">[{fmtNum(runInterval.low)}, {fmtNum(runInterval.high)}]</span>
            </div>
          ) : null}

          {meta.length ? (
            <dl className="estmeta">
              {meta.map((r, i) => (
                <div className="estmeta__row" key={i}>
                  <dt className="estmeta__k">{r.label}</dt>
                  <dd className="estmeta__v">{r.value}</dd>
                </div>
              ))}
            </dl>
          ) : null}

          {/* A refusal, which is an answer. What the reader needs first is
              not WHY no number came out but what to do about it, and that is
              the kind — five of them, and this row used to print the species
              instead: one identifier standing in for five different
              instructions. The species stays as the quiet mono annotation
              the status chip and the gap list already use. */}
          {result.estimator_failure ? (
            <div className="boundsexpr">
              <div className="boundsexpr__row">
                <span className="boundsexpr__k">
                  {answerShown
                    ? say(SAYS.alsoMissing, lang, 'alsoMissing')
                    : refusal ? refusal.lead : say(SAYS.noNumber, lang, 'noNumber')}
                </span>
                <span className="boundsexpr__v">
                  {refusal ? refusal.head : say(SAYS.estimatorRefused, lang, 'estimatorRefused')}
                  <span className="mono"> {result.estimator_failure.failure_type}</span>
                </span>
              </div>
              <p className="boundsexpr__note">
                {result.estimator_failure.reason}
                {refusal ? ` ${refusal.tail}` : ''}
              </p>
              {/* The way past THIS refusal. A separate list rather than more
                  of the note above, because the note says what happened and
                  these say what to do, and a reader acting on the second
                  should not have to find it inside the first. */}
              {remedies.length > 0 ? (
                <ul className="boundsexpr__note">
                  {remedies.map((r, i) => <li key={`remedy-${i}`}>{r}</li>)}
                </ul>
              ) : null}
            </div>
          ) : null}

          {/* How it was computed — formula / paths / bounds / ledger. Machine
              artifacts a lay reader rarely needs; folded, nothing removed. */}
          {hasDetail ? (
            <Foldout summary={say(SAYS.howSummary, lang, 'howSummary')}>
              {routes.map((r, i) => (
                <div className="boundsexpr" key={`route-${i}`}>
                  <span className="figure__cap">{r.cap}</span>
                  {r.rows.map((row, j) => (
                    <div className="boundsexpr__row" key={j}>
                      <span className="boundsexpr__k">{row.label}</span>
                      <span className="boundsexpr__v">{row.value}</span>
                    </div>
                  ))}
                </div>
              ))}

              {paths.length ? (
                <div className="figure">
                  <span className="figure__cap">
                    {say(result.query_kind === 'cause' ? SAYS.causalPaths : SAYS.supportingPaths, lang,
                      result.query_kind === 'cause' ? 'causalPaths' : 'supportingPaths')}
                  </span>
                  <div className="pathlist">
                    {paths.map((p, i) => (
                      <div className="pathchain" key={i}>
                        {p.map((node, j) => (
                          <span className="pathchain__seg" key={j}>
                            <span className="pathnode mono">{cleanPathNode(node)}</span>
                            {j < p.length - 1 ? <span className="pathchain__arrow" aria-hidden>→</span> : null}
                          </span>
                        ))}
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              {formula ? (
                <div className="figure">
                  <span className="figure__cap">{say(SAYS.idFormula, lang, 'idFormula')}</span>
                  <span className="formula mono">{formula}</span>
                </div>
              ) : null}

              {/* After the expression and before the skeleton: the routes say
                  which pattern identified the estimand, these say what the
                  estimator then did with the data. Same position as in the
                  report, so the two surfaces read as one account. */}
              {detail.map((d, i) => (
                <div className="boundsexpr" key={`detail-${i}`}>
                  <span className="figure__cap">{d.cap}</span>
                  {d.rows.map((row, j) => (
                    <div className="boundsexpr__row" key={j}>
                      <span className="boundsexpr__k">{row.label}</span>
                      <span className="boundsexpr__v">{row.value}</span>
                    </div>
                  ))}
                </div>
              ))}

              {/* After the pattern and the expression, because it is the
                  skeleton and they are the detail — the same order the
                  report states this section in, so a reader comparing the
                  two does not have to reconcile them. */}
              {chain ? (
                <div className="boundsexpr">
                  <span className="figure__cap">{chain.cap}</span>
                  {chain.rows.map((row, i) => (
                    <div className="boundsexpr__row" key={`chain-${i}`}>
                      <span className="boundsexpr__k">{row.label}</span>
                      <span className="boundsexpr__v">{row.value}</span>
                    </div>
                  ))}
                </div>
              ) : null}

              {/* Last, and about none of the lines above in particular: the
                  sources, for a reader who wants to check the method against
                  the literature rather than against us. Same position as in
                  the report. */}
              {cites.length ? (
                <div className="boundsexpr">
                  <span className="figure__cap">{say(SAYS.sources, lang, 'sources')}</span>
                  {cites.map((said, i) => (
                    <div className="boundsexpr__row" key={`cite-${i}`}>
                      <span className="boundsexpr__v">{said}</span>
                    </div>
                  ))}
                </div>
              ) : null}

              {bounds.map((b, i) => (
                <div className="boundsexpr" key={`bounds-${i}`}>
                  <div className="boundsexpr__row">
                    <span className="boundsexpr__k">{say(SAYS.boundedThing, lang, 'boundedThing')}</span>
                    <span className="boundsexpr__v">{boundsEstimandLabel(b.estimand, lang)}</span>
                  </div>
                  {b.lower_value != null && b.upper_value != null ? (
                    <div className="boundsexpr__row">
                      <span className="boundsexpr__k">{say(SAYS.interval, lang, 'interval')}</span>
                      <span className="boundsexpr__v">[{fmtNum(b.lower_value)}, {fmtNum(b.upper_value)}]</span>
                    </div>
                  ) : null}
                  {b.contrast ? (
                    <div className="boundsexpr__row">
                      <span className="boundsexpr__k">{boundsContrastLabel(b.contrast.kind, lang)}</span>
                      <span className="boundsexpr__v">
                        [{fmtNum(b.contrast.lower_value)}, {fmtNum(b.contrast.upper_value)}]
                        {fill(SAYS.contrastNote, lang, { ref: String(b.contrast.reference_value) })}
                      </span>
                    </div>
                  ) : null}
                  <div className="boundsexpr__row">
                    <span className="boundsexpr__k">{say(SAYS.method, lang, 'method')}</span>
                    <span className="boundsexpr__v">{b.method}</span>
                  </div>
                  {/* Without this row several intervals over one estimand are
                      unreadable: what separates them is only what each was
                      allowed to assume. */}
                  <div className="boundsexpr__row">
                    <span className="boundsexpr__k">{say(SAYS.restsOn, lang, 'restsOn')}</span>
                    <span className="boundsexpr__v">{b.assumptions?.length ? b.assumptions.join(', ') : say(SAYS.none, lang, 'none')}</span>
                  </div>
                  {/* Whether a narrower set is consistent with the same
                      assumptions — a different offer from a wide sharp
                      interval, and one the reader would otherwise have to
                      infer from the method's reputation (#419). */}
                  {b.tightness ? (
                    <div className="boundsexpr__row">
                      <span className="boundsexpr__k">{say(SAYS.tightness, lang, 'tightness')}</span>
                      <span className="boundsexpr__v">
                        {tightnessLabel(b.tightness, lang)}
                        {' — '}
                        {tightnessAdvice(b.tightness, lang)}
                      </span>
                    </div>
                  ) : null}
                  <div className="boundsexpr__row">
                    <span className="boundsexpr__k">{say(SAYS.lower, lang, 'lower')}</span>
                    <span className="boundsexpr__v">{b.lower_expression}</span>
                  </div>
                  <div className="boundsexpr__row">
                    <span className="boundsexpr__k">{say(SAYS.upper, lang, 'upper')}</span>
                    <span className="boundsexpr__v">{b.upper_expression}</span>
                  </div>
                  {b.width_when_uninformative ? (
                    <p className="boundsexpr__note">{say(SAYS.uninformative, lang, 'uninformative')}</p>
                  ) : (
                    <p className="boundsexpr__note">{say(SAYS.symbolic, lang, 'symbolic')}</p>
                  )}
                </div>
              ))}
              {bounds.length > 1 ? (
                <p className="boundsexpr__note">{fill(SAYS.manyBounds, lang, { n: bounds.length })}</p>
              ) : null}
              {/* Rows differing in width by a factor of two on one result is
                  a fact about which of them assumed what. Without this it
                  reads as a fact about precision (#419). */}
              {bounds.length ? (
                <p className="boundsexpr__note">
                  {fill(SAYS.widthIs, lang, {
                    advice: intervalWidthAdvice('identification', lang),
                  })}
                </p>
              ) : null}

              {sens?.e_value != null ? (
                <div className="boundsexpr">
                  <div className="boundsexpr__row">
                    <span className="boundsexpr__k">E-value</span>
                    <span className="boundsexpr__v">
                      {fmtNum(sens.e_value)}
                      {sens.e_value_ci_bound != null
                        ? fill(SAYS.eValueCi, lang, { bound: fmtNum(sens.e_value_ci_bound) })
                        : ''}
                    </span>
                  </div>
                  {sens.interpretation_band ? (
                    <p className="boundsexpr__note">
                      {fill(SAYS.eValueBand, lang, {
                        band: evalueBandLabel(sens.interpretation_band, lang),
                        basis: evalueBandBasisLabel(sens.band_basis ?? 'point', lang),
                      })}
                    </p>
                  ) : null}
                  <p className="boundsexpr__note">{fill(SAYS.eValueNote, lang, { e: fmtNum(sens.e_value) })}</p>
                </div>
              ) : null}

              {ledger?.assumptions?.length ? (
                <div className="ledger">
                  <span className="figure__cap">{say(SAYS.ledgerCap, lang, 'ledgerCap')}{ledger.summary ? ` · ${ledger.summary}` : ''}</span>
                  <ul className="ledger__list">
                    {ledger.assumptions.map((a, i) => (
                      // Three closed vocabularies on one line: how badly it
                      // dies, which part of the answer it holds up, and who
                      // put it there. The last two were dropped on this
                      // surface and printed raw on the other, which is two
                      // ways of not deciding what they are for.
                      <li className="ledger__item" key={i}>
                        <span className={`ledger__sev ledger__sev--${a.severity ?? 'info'}`}>
                          {a.severity ? assumptionSeverityLabel(a.severity, lang) : ''}
                        </span>
                        <span className="ledger__claim">{a.claim}</span>
                        {a.layer ? <span className="ledger__tag">{ledgerLayerLabel(a.layer, lang)}</span> : null}
                        {a.provenance ? (
                          <span className="ledger__tag">{fill(SAYS.provenance, lang, { who: ledgerProvenanceLabel(a.provenance, lang) })}</span>
                        ) : null}
                        {a.testable === false ? <span className="ledger__tag">{say(SAYS.untestable, lang, 'untestable')}</span> : null}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </Foldout>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}
