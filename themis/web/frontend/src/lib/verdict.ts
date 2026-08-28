import type { AnswerTier, ArConfidenceSet, Band, Derivation, FourWayDifference, FourWayRatio, LongitudinalRoute, MeasurementCorrection, GapSentence, NumericEstimate, Occasion, QueryResult, RecoveredAte, RegressionCalibration, SelectionRecovery, StratifiedWald } from '../types'
import type { Lang, Words } from './language'
import { DEFAULT_LANG, absent, fill, gloss, holes, say } from './language'
// The vocabularies this file restates from the kernel. Generated
// from themis/output/reader_words.py and checked in: the browser
// cannot import Python, and a copy somebody types is a copy that
// drifts — two of them had, one silently, before it was pinned.
import * as generated from './kernelWords.generated'

type OutcomeError = NonNullable<QueryResult['outcome_error']>
type EstimationContext = NonNullable<QueryResult['estimation_context']>

// Every table below maps a member of a kernel vocabulary to that member's
// text BY LANGUAGE, and every accessor takes the language as its last
// argument. Fourteen of them used to spell it into the name instead
// (`PATTERN_ZH`), which is a name and takes no argument — so "show this
// reader English" was not a request this file could be asked.
//
// The argument is passed a literal today, because the page has no chooser
// yet and a page that switched its vocabulary while every sentence around it
// stayed put would hand a reader half of each language. The chooser is what
// arrives last, after the sentences.

type TierMeta = { label: string; gloss: string }

export const TIER_META: Record<AnswerTier, Words<TierMeta>> = {
  point: {
     zh: { label: '点估计', gloss: '可以算出一个具体数字——补齐数据即可' },
     en: {
       label: 'point estimate',
       gloss: 'a specific number can be produced — supply the data and it will be',
     },
   },
  interval: {
    zh: { label: '区间', gloss: '给不了确切数字，但能给一个诚实的范围' },
    en: {
      label: 'interval',
      gloss: 'no exact number, but an honest range',
    },
  },
  none: {
    zh: { label: '无', gloss: '光凭图和数据给不了数，需要额外假设' },
    en: {
      label: 'none',
      gloss: 'the graph and the data alone give no number; this needs an extra assumption',
    },
  },
}
export function tierMeta(tier: AnswerTier, lang: Lang = DEFAULT_LANG): TierMeta {
  return say(TIER_META[tier], lang, {
    label: absent('no_word_for_this_token', lang, { token: String(tier) }),
    gloss: '',
  })
}

// One entry per status, label required and blurb optional — two tables keyed
// by the same vocabulary are two chances to hold half of it, and this one
// held a status the kernel does not emit (`unidentifiable`) while missing one
// it does (`outside_language`, six results in one suite run, which reached
// the reader as its own identifier).
type StatusMeta = { label: string; blurb?: string }

const STATUS_META: Record<string, Words<StatusMeta>> = {
  structurally_solved: {
     zh: {
      label: '已识别(结构上)',
      blurb: '因果结构本身成立；是否有数值取决于是否提供数据。',
    },
     en: {
       label: 'identified (structurally)',
       blurb: 'The causal structure itself holds; whether there is a number depends on whether data was supplied.',
     },
   },
  numerically_solved: {
    zh: {
      label: '已算出数值',
      blurb: '提供了数据，内核完成识别并算出了数值。',
    },
    en: {
      label: 'estimated',
      blurb: 'Data was supplied, and the kernel completed identification and computed a number.',
    },
  },
  needs_investigation: {
    zh: {
      label: '可识别，但缺数据',
      blurb: '结构上可识别(给出识别公式)，但缺数据——内核拒绝编数字，并列出还缺什么。',
    },
    en: {
      label: 'identifiable, but data is missing',
      blurb: 'Identifiable structurally (an identification formula is given), but the data is missing — the kernel refuses to invent a number and lists what is still needed.',
    },
  },
  outside_language: {
    zh: {
      label: '超出可表达范围',
      blurb: '这个问题超出 Themis 能表达 / 能识别的范围——不是数据不够，是问题的形式本身还没有对应的表示。',
    },
    en: {
      label: 'outside what can be expressed',
      blurb: 'This question is outside what Themis can express or identify — not a shortage of data, but a form of question that has no representation here yet.',
    },
  },
  counterfactual_solved: {
    zh: {
      label: '反事实已解',
      blurb: '反事实的那一格解出来了。',
    },
    en: {
      label: 'counterfactual solved',
      blurb: 'The counterfactual cell was solved.',
    },
  },
  counterfactual_bounded: {
    zh: {
      label: '反事实(区间)',
      blurb: '反事实只能给区间，要点估计需补单调性等假设。',
    },
    en: {
      label: 'counterfactual (interval)',
      blurb: 'The counterfactual gives only an interval; a point estimate would need an extra assumption such as monotonicity.',
    },
  },
  needs_assumption: {
    zh: {
      label: '需要额外假设',
      blurb: '当前信息下无法回答，需要你显式补一个假设(认识论选择，内核不替你拍板)。',
    },
    en: {
      label: 'needs an extra assumption',
      blurb: 'Unanswerable on the current information; you have to state an assumption explicitly (an epistemic choice the kernel will not make for you).',
    },
  },
}
// One stand-in for both readers of the table below: a label and a blurb
// are two halves of one row, and two spellings of "this build has no word
// for it" is how the halves come apart.
function statusStandIn(status: string, lang: Lang): string {
  return absent('no_word_for_this_token', lang, { token: status })
}
export function statusLabel(status: string, lang: Lang = DEFAULT_LANG): string {
  return say(STATUS_META[status], lang, { label: statusStandIn(status, lang) }).label
}
export function statusBlurb(status: string, lang: Lang = DEFAULT_LANG): string | undefined {
  return say(STATUS_META[status], lang, { label: statusStandIn(status, lang) }).blurb
}

// How much a MISSING INPUT blocks an answer.
const SEVERITY_LABEL = generated.SEVERITY_LABEL
export function severityLabel(sev: string, lang: Lang = DEFAULT_LANG): string {
  return gloss(SEVERITY_LABEL, sev, lang)
}

// How the conclusion dies if an ASSUMPTION is false. A different question
// from the one above, a disjoint set of values, and the same field name —
// which is how the table above came to be read as the whole of `severity`
// and the assumption ledger's three values reached 688 readers as
// `invalidating` / `distorting` / `confidence_only`.
const ASSUMPTION_SEVERITY_WORDS = generated.ASSUMPTION_SEVERITY_WORDS
export function assumptionSeverityLabel(sev: string, lang: Lang = DEFAULT_LANG): string {
  return gloss(ASSUMPTION_SEVERITY_WORDS, sev, lang)
}

// Which part of the answer stops being true if an assumption is false —
// the third field of the same ledger line, and a partition of the answer
// rather than a list of topics. A sixth value named `assumption` used to
// sit here saying nothing; it was identification, since without it the
// quantity is bounded rather than point-identified.
const LEDGER_LAYER_WORDS = generated.LEDGER_LAYER_WORDS
export function ledgerLayerLabel(layer: string, lang: Lang = DEFAULT_LANG): string {
  return gloss(LEDGER_LAYER_WORDS, layer, lang)
}

// What the reader can do about this line: who can overrule it, and what they
// get back if they do. Five of the six name someone other than the method,
// and those are the lines a reader can actually overrule — which is the whole
// reason this field is worth the room it takes.
const LEDGER_PROVENANCE_WORDS = generated.LEDGER_PROVENANCE_WORDS
export function ledgerProvenanceLabel(prov: string, lang: Lang = DEFAULT_LANG): string {
  return gloss(LEDGER_PROVENANCE_WORDS, prov, lang)
}

// What a partial-identification interval brackets. Two numbers about the
// wrong quantity read exactly like two numbers about the right one, and this
// surface used to print neither the numbers nor their name — only the method
// that produced them, while one method was bracketing the difference between
// two arms under a question about one of them.
const BOUNDS_ESTIMAND_WORDS = generated.BOUNDS_ESTIMAND_WORDS
export function boundsEstimandLabel(estimand: string, lang: Lang = DEFAULT_LANG): string {
  return gloss(BOUNDS_ESTIMAND_WORDS, estimand, lang)
}

// The second quantity the same identified set can be read through: a
// contrast between two arms rather than one arm's level.
const BOUNDS_CONTRAST_WORDS = generated.BOUNDS_CONTRAST_WORDS
export function boundsContrastLabel(kind: string, lang: Lang = DEFAULT_LANG): string {
  return gloss(BOUNDS_CONTRAST_WORDS, kind, lang)
}

// Which of the five answers to "what now" a refusal gives — themis/refusals.py
// hangs one on every species, and the report has said it in words all along.
// The species itself stays an identifier here for the reason it does there:
// with sixty-nine of them it is the developer's handle, and the reader's
// sentence is this line plus the occasion's own `reason`.
// `lead` is per kind and not a constant caption because the report's is not:
// four of the five say 给出 and the backend one says 算出, the difference
// being that there the routine ran. Writing one caption over all five would
// be this surface deciding, in a word, something the other one had decided
// the other way.
type Refusal = { lead: string; head: string; tail: string }

const REFUSAL_KIND_WORDS: Record<string, Words<Refusal>> = {
  graph: {
     zh: {
      lead: '没有给出数值',
      head: '这是关于因果图的结论',
      tail: '再多同样的数据也不会改变它；要改变的是图或问题本身。',
    },
     en: {
       lead: 'No number',
       head: 'this is a conclusion about the causal graph',
       tail: 'More of the same data will not change it; what would is the graph, or the question.',
     },
   },
  data: {
    zh: {
      lead: '没有给出数值',
      head: '这批数据支撑不住',
      tail: '结构上是可识别的，缺的是数据本身能提供的支持。',
    },
    en: {
      lead: 'No number',
      head: 'these data cannot support one',
      tail: 'It is identifiable structurally; what is missing is the support the data themselves would have to provide.',
    },
  },
  unbuilt: {
    zh: {
      lead: '没有给出数值',
      head: 'Themis 还没有建这个情形',
      tail: '问题成立、也已被识别，这是工具的边界，不是问题或数据的毛病。',
    },
    en: {
      lead: 'No number',
      head: 'Themis has not built this case',
      tail: 'The question is well posed and has been identified; this is the tool\'s boundary, not a fault in the question or the data.',
    },
  },
  request: {
    zh: {
      lead: '没有给出数值',
      head: '需要你改一处输入',
      tail: '改掉之后重跑即可。',
    },
    en: {
      lead: 'No number',
      head: 'one of your inputs has to change',
      tail: 'Change it and run again.',
    },
  },
  backend: {
    zh: {
      lead: '没有算出数值',
      head: '数值例程没有返回结果',
      tail: '这没有对问题或数据设计做出任何判定。',
    },
    en: {
      lead: 'No number was produced',
      head: 'the numeric routine returned nothing',
      tail: 'This decides nothing about the question or about the data design.',
    },
  },
}
// Null for a kind this build has never heard of, and null is what the
// caller draws no refusal box from. A kind it knows with no sentence in
// this language is the other fact, and it renders as the identifier —
// a box saying nothing beats no box where a refusal happened.
export function refusalKind(kind: unknown, lang: Lang = DEFAULT_LANG): Refusal | null {
  const words = REFUSAL_KIND_WORDS[String(kind)]
  if (!words) return null
  const token = absent('no_word_for_this_token', lang, { token: String(kind) })
  return say(words, lang, { lead: token, head: token, tail: '' })
}

// The way past THIS refusal, as opposed to the kind above, which answers
// "what now" per species. Same shapes as themis/refusals.py::Remedy — one
// more verbatim restatement of a kernel table, which is the standing debt
// #399 names for all sixteen of them at once rather than a new one here.
//
// `{subject}` is filled from the envelope, never from this file: it is the
// occasion's own name for a column, a parameter, an estimator, and it is in
// no language, which is exactly why it travels beside the token instead of
// inside a sentence somebody wrote at the raise site.
const REMEDY_WORDS = generated.REMEDY_WORDS

// A route this build has never heard of is dropped rather than printed as a
// token, which is the opposite of what `refusalKind` does with a kind — and
// deliberately: a kind it cannot read still means a refusal happened and the
// box has to appear, while a route it cannot read is advice it cannot give.
export function remedyRoutes(remedies: unknown, lang: Lang = DEFAULT_LANG): string[] {
  if (!Array.isArray(remedies)) return []
  const said: string[] = []
  for (const row of remedies) {
    const words = REMEDY_WORDS[String((row as { remedy?: unknown })?.remedy)]
    if (!words) continue
    const subject = (row as { subject?: unknown })?.subject
    said.push(fill(words, lang, { subject: subject == null ? '' : String(subject) }))
  }
  return said
}

// WHY there is no number, assembled here because here is where the reader's
// language is known. The kernel used to send a finished sentence and the
// language was therefore chosen while refusing, with no reader in front of
// it; what it sends now are the sentence's parts (#411).
//
// `said` holds the holes that read the same in every language — a count, a
// column name, a stratum, a sampled list. They arrive rendered, because the
// rule that renders them is a computation (six significant figures, a
// sampling cutoff, quotation marks) and a twin of it here would be a second
// implementation with no test on the kernel's side able to reach it.
//
// `words` holds the holes that do NOT: each is a member of a closed set
// whose text IS the language, so it travels as the set and the token and is
// looked up in the tables below — which the kernel generates, like every
// other table in this file.
const REFUSAL_SAYS = generated.REFUSAL_SAYS
const QUERY_ROLE_WORDS = generated.QUERY_ROLE_WORDS
const REFUTATION_WORDS = generated.REFUTATION_WORDS
const RECOVERY_WORDS = generated.RECOVERY_WORDS
const SINGULAR_MATRIX_WORDS = generated.SINGULAR_MATRIX_WORDS
const OUTCOME_ERROR_PREMISE_WORDS = generated.OUTCOME_ERROR_PREMISE_WORDS

// One species' sentence, assembled. Written once because the two channels
// that carry a sentence this way — a refusal and a shortfall — differ only
// in which table names the species. Two copies of the assembly would be two
// chances for one channel's sentence to gain a rule the other's did not.
function assembled(
  species: string,
  block: Occasion,
  says: Record<string, Words>,
  lang: Lang,
): string {
  const template = says[species]
  // A species this build has never heard of keeps its own token, and a hole
  // nothing was sent for says so — for the reason an unlisted gloss does: a
  // reader who can see WHAT is missing still beats a line that says
  // something went wrong and then nothing. Both are reachable only from an
  // envelope some other build wrote, which is the reader who must not be
  // handed a thrown error instead of an answer.
  //
  // Said as absences (`absent`), which is what changed: all three of these
  // used to be a backticked identifier, and so is a name the sentence is
  // legitimately about, so a reader could not tell them apart.
  if (!template) {
    return species ? absent('no_word_for_this_token', lang, { token: species }) : ''
  }
  const slots: Record<string, string> = {}
  for (const name of holes(template)) {
    slots[name] = absent('no_fact_for_this_slot', lang, { name })
  }
  for (const [key, value] of Object.entries(block.said ?? {})) {
    slots[key] = String(value)
  }
  // A hole holds a word, a whole STATEMENT, or a list of them — all three
  // through `stated`, because a statement is a word whose text has holes and
  // so the lookup that turns a token into text is one lookup. A list is
  // joined here, in this reader's punctuation: the kernel used to assemble
  // these where it built them, which put an ASCII comma between Chinese
  // items and named a field in English inside a Chinese sentence.
  for (const [key, word] of Object.entries(block.words ?? {})) {
    slots[key] = Array.isArray(word)
      ? listing(word.map((one) => stated(one, lang)), lang)
      : stated(word, lang)
  }
  return fill(template, lang, slots)
}

// Several things named in a row, in the reader's punctuation.
//
// The kernel has had this since a seam became a fact about the language
// rather than about the code doing the joining. This surface writes the
// separator into about ten call sites of its own, every one of them wrong
// the moment the reader is not Chinese (#447); this is the door they go
// through, and the two above are the first two.
// Several names inside one expression, as the expression writes them.
//
// `listing` is a list a READER reads and takes their punctuation; this is
// not one. The conditioning set in `P(y | x, z)` is part of the
// mathematics, the same reason the kernel gives for not translating a Σ,
// and the kernel writes it this way wherever it builds the expression.
//
// It takes no language, and that is the whole statement it makes. While
// the two were one idea, this surface spelled the separator with a Chinese
// comma by hand and the report borrowed the reader's — so one Chinese
// report showed `P(y | x、z)` and `P(y | x, z)` on adjacent lines.
export function within(items: readonly unknown[]): string {
  return items.map(String).join(', ')
}

export function listing(items: readonly string[], lang: Lang = DEFAULT_LANG): string {
  return items.join(fill(generated.BETWEEN_ITEMS, lang))
}

// Several sentences in a row, with this language's gap between them — the
// twin of the above, one punctuation mark over. It was one surface's own
// wording while one surface joined a paragraph, and it read correctly there
// for the reason a missing gap always does in Chinese: Chinese needs none.
// A ledger line is the second such paragraph, which is what makes the gap
// the language's rather than the layout's.
//
// Empty parts are dropped rather than joined around, exactly as the
// kernel's own door does it: a line with nothing to say is one sentence
// fewer, not a sentence-shaped gap.
export function sentences(parts: readonly string[], lang: Lang = DEFAULT_LANG): string {
  return parts.filter(Boolean).join(fill(generated.BETWEEN_SENTENCES, lang))
}

export function refusalSaid(failure: unknown, lang: Lang = DEFAULT_LANG): string {
  const block = (failure ?? {}) as Occasion & { failure_type?: unknown }
  return assembled(String(block.failure_type ?? ''), block, REFUSAL_SAYS, lang)
}

// What a query was short of, in the reader's words — the twin of the above
// for the other channel. themis/gaps.py holds the species and its sentence,
// and a missing item, an investigation item and a request's note all carry
// the same three fields, so all three arrive here.
//
// An entry with no species says nothing rather than saying so, which is
// what lets a caller fall back on the item's own name.
const GAP_SAYS = generated.GAP_SAYS
const QUERY_PART_WORDS = generated.QUERY_PART_WORDS
const UNNAMED_WORDS = generated.UNNAMED_WORDS
const MEASUREMENT_SCALE_WORDS = generated.MEASUREMENT_SCALE_WORDS

export function gapSaid(entry: unknown, lang: Lang = DEFAULT_LANG): string {
  const block = (entry ?? {}) as Occasion & { need?: unknown }
  const species = String(block.need ?? '')
  return species ? assembled(species, block, GAP_SAYS, lang) : ''
}

// What a gap says about itself, one statement at a time. The paragraph
// used to arrive assembled, in one language; the gap now carries the
// statements it is made of, and the seam between two of them belongs to
// whoever is joining them for a reader — so this returns the list and the
// component that shows it supplies the seam, exactly as it does for a list
// of anything else.
const GAP_DESCRIBES = generated.GAP_DESCRIBES
export function gapDescribes(gap: unknown, lang: Lang = DEFAULT_LANG): string[] {
  const block = (gap ?? {}) as { describes?: unknown }
  const said = Array.isArray(block.describes) ? block.describes : []
  return said.map((entry) => {
    const one = (entry ?? {}) as Occasion & { sentence?: unknown }
    return assembled(String(one.sentence ?? ''), one, GAP_DESCRIBES, lang)
  })
}

// Every closed set the kernel declares, by the name it answers to on an
// envelope. ONE map, and it is one because a word and a statement are one
// thing: a statement is a word whose text has holes, so what turns a token
// into text is the same lookup either way, and a hole is free to name a set
// from any channel — which set a slot names is the slot's fact and not the
// sentence's. This was four maps: two indexes of word tables, one per
// channel, plus a third for the sentences a carrier may name and a fourth
// that was the union of the first two.
const E_VALUE_UNDEFINED_WORDS = generated.E_VALUE_UNDEFINED_WORDS
const MEASUREMENT_NOTE_WORDS = generated.MEASUREMENT_NOTE_WORDS
const PRECISION_TARGET_WORDS = generated.PRECISION_TARGET_WORDS
const TIME_WINDOW_WORDS = generated.TIME_WINDOW_WORDS
const SUTVA_CONCERN_WORDS = generated.SUTVA_CONCERN_WORDS
const BOUNDS_NOTE_WORDS = generated.BOUNDS_NOTE_WORDS
const OBSERVABLE_REQUIRED_WORDS = generated.OBSERVABLE_REQUIRED_WORDS
const BOUND_SIDE_WORDS = generated.BOUND_SIDE_WORDS
const MONOTONICITY_WORDS = generated.MONOTONICITY_WORDS
const ASSUMPTION_CLAIM_WORDS = generated.ASSUMPTION_CLAIM_WORDS
const THETA_PRIOR_CLAIM_WORDS = generated.THETA_PRIOR_CLAIM_WORDS
// And the four the two recovery verdicts are made of. Each block could
// name the theorem that carried a POSITIVE verdict and had nothing to name
// what a negative came back empty on, so the whole of a negative was one
// sentence — which is why two of these are shortfalls and two are the
// labels that used to be an English role word glued onto a symbolic
// expression.
const SELECTION_SHORTFALL_WORDS = generated.SELECTION_SHORTFALL_WORDS
const UNBIASED_DISTRIBUTION_WORDS = generated.UNBIASED_DISTRIBUTION_WORDS
const MISSING_DATA_SHORTFALL_WORDS = generated.MISSING_DATA_SHORTFALL_WORDS
const RECOVERY_FACTOR_WORDS = generated.RECOVERY_FACTOR_WORDS
const WORDS: Record<string, Record<string, Words>> = {
  query_role: QUERY_ROLE_WORDS,
  monotonicity_refutation: REFUTATION_WORDS,
  recovery_mechanism: RECOVERY_WORDS,
  singular_matrix: SINGULAR_MATRIX_WORDS,
  outcome_error_premise: OUTCOME_ERROR_PREMISE_WORDS,
  query_part: QUERY_PART_WORDS,
  measurement_scale: MEASUREMENT_SCALE_WORDS,
  unnamed_thing: UNNAMED_WORDS,
  e_value_undefined: E_VALUE_UNDEFINED_WORDS,
  measurement_note: MEASUREMENT_NOTE_WORDS,
  precision_target: PRECISION_TARGET_WORDS,
  time_window: TIME_WINDOW_WORDS,
  sutva_concern: SUTVA_CONCERN_WORDS,
  bounds_note: BOUNDS_NOTE_WORDS,
  observable_required: OBSERVABLE_REQUIRED_WORDS,
  bound_side: BOUND_SIDE_WORDS,
  monotonicity: MONOTONICITY_WORDS,
  // What a ledger line says the answer rests on. Three vocabularies for one
  // field, which is what a statement carrying its own set is for: the
  // glossary words the assumptions an estimator declares, a gap's own
  // statements word an unverified edge, and a number the model supplied
  // words itself. The field used to arrive as text, so this surface printed
  // whatever language the kernel had been asked for.
  assumption_claim: ASSUMPTION_CLAIM_WORDS,
  theta_prior_claim: THETA_PRIOR_CLAIM_WORDS,
  gap_describes: GAP_DESCRIBES,
  // And the sentence a gap's own sentence puts in a hole: five of them say
  // that a route failed and name a shortfall as the why, which is a
  // statement inside a statement.
  gap_says: GAP_SAYS,
  // The four a recovery verdict is made of.
  selection_recovery_shortfall: SELECTION_SHORTFALL_WORDS,
  unbiased_distribution: UNBIASED_DISTRIBUTION_WORDS,
  missing_data_shortfall: MISSING_DATA_SHORTFALL_WORDS,
  recovery_factor: RECOVERY_FACTOR_WORDS,
}

// One statement any producer owed a reader. The channels above name their
// vocabulary by the field it arrives in; this one carries it, which is what
// lets a producer with no channel of its own state a sentence instead of
// writing one — and what lets a hole inside any of them hold one.
//
// A set this build has never heard of keeps its token, as the kernel's own
// reader does: a name to look up beats silence where a sentence was
// promised.
export function stated(entry: unknown, lang: Lang = DEFAULT_LANG): string {
  const block = (entry ?? {}) as Occasion & { vocabulary?: unknown; token?: unknown }
  const token = String(block.token ?? '')
  return token
    ? assembled(token, block, WORDS[String(block.vocabulary ?? '')] ?? {}, lang)
    : ''
}

// One way past a gap. The same arrangement as above and for the same
// reason: the route leaves the kernel as a token plus this occasion's
// facts, and this surface fills the sentence it already holds.
const GAP_ROUTES = generated.GAP_ROUTES
export function gapWent(entry: unknown, lang: Lang = DEFAULT_LANG): string {
  const block = (entry ?? {}) as Occasion & { route?: unknown }
  const route = String(block.route ?? '')
  return route
    ? assembled(route, block, GAP_ROUTES, lang)
    : ''
}

// What would close a gap, as the noun phrase a next-steps line is built
// out of. That line used to arrive finished on the envelope, in one
// language; it is assembled here now, out of the gaps this surface is
// already showing. The frame around this phrase ("补 {}") is the surface's
// own sentence and stays with the surface, exactly as a refusal's
// head/lead/tail do.
const GAP_WANTED = generated.GAP_WANTED
export function gapWanted(kind: string, lang: Lang = DEFAULT_LANG): string {
  return gloss(GAP_WANTED, kind, lang)
}

// And what having it would buy — the third sentence a gap is made of,
// assembled the same way and from the same halves. It used to arrive
// finished on the envelope, where 21 producers wrote it from 17 templates
// and no two species disagreed about theirs, which is what made it a table
// the kernel already had rather than an occasion's fact.
//
// Empty is an ANSWER here, not a failure: for the species listed in
// `themis.gaps.NOTHING_FILLS` there is nothing a reader could go and get
// that changes the gap, and the reader learns that by being shown no such
// line. So this doubles as the predicate for the next-steps tail — the
// same one the kernel's own tail uses.
const GAP_IF_PROVIDED = generated.GAP_IF_PROVIDED
export function gapIfProvided(gap: unknown, lang: Lang = DEFAULT_LANG): string {
  const block = (gap ?? {}) as Occasion & { kind?: unknown }
  const species = String(block.kind ?? '')
  return GAP_IF_PROVIDED[species]
    ? assembled(species, block, GAP_IF_PROVIDED, lang)
    : ''
}

// gap kind -> short plain-language title. The rigorous kind stays as a
// quiet mono annotation; this is the translation the reader leads with.
const GAP_TITLE: Record<string, Words> = {
  unidentifiable_no_admissible_set: {
     zh: '找不到能消除混杂的调整集',
     en: 'no adjustment set removes the confounding',
   },
  missing_distribution: {
    zh: '缺一个概率分布',
    en: 'a probability distribution is missing',
  },
  missing_population_distribution: {
    zh: '缺目标人群的分布',
    en: 'the target population\'s distribution is missing',
  },
  missing_assumption: {
    zh: '缺一条识别假设',
    en: 'an identification assumption is missing',
  },
  missing_unit_observation: {
    zh: '缺这个个体自己的观测值',
    en: 'this unit\'s own observation is missing',
  },
  missing_structural_input: {
    zh: '缺一项结构输入(方程系数 / 声明)',
    en: 'a structural input is missing (an equation coefficient or a declaration)',
  },
  missing_iv_candidate: {
    zh: '缺一个有效的工具变量',
    en: 'no valid instrument',
  },
  missing_mediator_data: {
    zh: '缺中介变量的数据',
    en: 'the mediator\'s data is missing',
  },
  transport_target_distribution_unknown: {
    zh: '目标人群分布未知',
    en: 'the target population\'s distribution is unknown',
  },
  transport_sources_disagree: {
    zh: '几个源人群互相矛盾',
    en: 'the source populations contradict each other',
  },
  transport_source_conditional_unknown: {
    zh: '源人群的分层分布未知',
    en: 'the source population\'s stratified distribution is unknown',
  },
  ambiguous_variable_definition: {
    zh: '变量定义不够清楚',
    en: 'the variable is not defined clearly enough',
  },
  dose_response_data_required: {
    zh: '剂量-反应曲线需要数据',
    en: 'the dose-response curve needs data',
  },
  unverified_proposal_edge_on_query_path: {
    zh: '路径上有一条未经验证的边',
    en: 'an unverified edge lies on the path',
  },
  iv_identification_assumption_required: {
    zh: '工具变量识别需要假设',
    en: 'instrumental-variable identification needs an assumption',
  },
  mediation_identification_assumption_required: {
    zh: '中介分解需要假设',
    en: 'the mediation decomposition needs an assumption',
  },
  transport_identification_assumption_required: {
    zh: '跨人群迁移需要假设',
    en: 'transporting across populations needs an assumption',
  },
  llm_declared_ambiguity: {
    zh: '上游标记了不确定性',
    en: 'the upstream flagged an uncertainty',
  },
  answer_is_bounds_not_point_estimate: {
    zh: '答案是区间，不是点',
    en: 'the answer is an interval, not a point',
  },
  low_confidence_input_data: {
    zh: '输入数据可信度偏低',
    en: 'the input data is of low confidence',
  },
  unattempted_layer_due_to_dispatch_conflict: {
    zh: '还有一层没跑(两种分析同时被要求)',
    en: 'one layer was not run (two analyses were asked for at once)',
  },
  weak_iv_instrument: {
    zh: '工具变量偏弱',
    en: 'the instrument is weak',
  },
  iv_estimand_fallback_to_linear: {
    zh: '按分层求不了，退回到整体的线性估计',
    en: 'the stratified form is unavailable, so this fell back to the overall linear estimate',
  },
  overidentification_rejected: {
    zh: '过度识别检验否决了这组工具',
    en: 'the overidentification test rejected this set of instruments',
  },
  propensity_overlap_violation: {
    zh: '两组人重叠不够(倾向得分越界)',
    en: 'the two groups overlap too little (the propensity score goes out of range)',
  },
  outcome_model_quasi_separation: {
    zh: '结果模型近乎完全分离',
    en: 'the outcome model is quasi-completely separated',
  },
  front_door_identification_assumption_required: {
    zh: '前门识别需要假设',
    en: 'front-door identification needs an assumption',
  },
  counterfactual_identification_assumption_required: {
    zh: '反事实推理需要假设',
    en: 'counterfactual reasoning needs an assumption',
  },
  graph_learned_from_data: {
    zh: '因果图是从数据学出来的',
    en: 'the causal graph was learned from the data',
  },
  collider_conditioning_opens_backdoor: {
    zh: '条件在对撞点上会打开后门',
    en: 'conditioning on a collider opens a back-door',
  },
  unmeasured_confounder_risk: {
    zh: '可能残留未测量的混杂',
    en: 'unmeasured confounding may remain',
  },
  measurement_error_concern: {
    zh: '测量误差风险',
    en: 'measurement error is a risk here',
  },
  selection_on_collider_opens_path: {
    zh: '样本选择打开了偏倚路径',
    en: 'the sample selection opened a biasing path',
  },
  ill_defined_intervention_versions: {
    zh: '干预没定义清楚',
    en: 'the intervention is not well defined',
  },
  graph_theta_independence_mismatch: {
    zh: '图与提供的分布不一致',
    en: 'the graph and the supplied distribution disagree',
  },
  dichotomized_continuous_measure: {
    zh: '连续变量被二分了',
    en: 'a continuous variable was split in two',
  },
  declared_type_data_mismatch: {
    zh: '声明的变量类型与数据不符',
    en: 'the declared variable type does not match the data',
  },
  proxy_coarsening_undeclared: {
    zh: '代理的层级比 U 的状态数多，还没说哪些层级归一组',
    en: 'the proxies have more levels than U has states, and no grouping is declared',
  },
}
export function gapTitle(kind: string, lang: Lang = DEFAULT_LANG): string {
  return gloss(GAP_TITLE, kind, lang)
}

// What the structural boolean asserts, per kind of question — the table
// themis/questions.py declares, mirrored here because the browser cannot
// import it. A test parses this object and holds its keys and its
// `answersIt` flags equal to the Python vocabulary.
//
// This used to special-case cause / assoc / identify and answer the other
// seven with 成立 / 不成立. Those seven asked for a number, and 81 results
// in one suite run were answered that way — the boolean says the estimand
// is identifiable, which is worth stating and is not what was asked. The
// fallback was the shape of "this kind has no reading", and a fallback
// reads exactly like coverage, which is why binding replaces it.
// `answersIt` sits OUTSIDE the language axis. Whether the boolean is the
// answer to the question asked or a precondition for one is a fact about the
// question, the same for every reader; inside `words` it would be a second
// record of itself, free to say 结论 to one reader and identification to the
// next about the very same result.
type Side = { label: string; gloss: string }
type ReadingWords = { holds: Side; failsTo: Side }
type Reading = { answersIt: boolean; words: Words<ReadingWords> }

// The propositions themselves, restated here because the browser cannot
// import Python — and held to themis/questions.py (`settles` / `fails`)
// STRING BY STRING, not only key by key. Two authors of one proposition is
// what this table was: the report kept a second hand-written copy, and the
// copy dropped the scope the original carried, so a `cause` verdict reached
// a reader as 存在因果影响 — a sentence about the world, where the kernel
// had checked reachability over the edges the caller drew. Nothing required
// the two to agree, because only one of them had a reader. Nothing here may
// be a paraphrase; a build-time generator replaces the transcription later,
// and until it does the equality is what stands in for it.
const QUESTION_READINGS: Record<string, Reading> = {
  probability: {
    answersIt: false,
    words: {
      zh: { holds: { label: '可识别', gloss: '这张图上，该概率可识别' }, failsTo: { label: '不可识别', gloss: '这张图上，该概率不可识别' } },
      en: { holds: { label: 'identifiable', gloss: 'on this graph the probability is identifiable' }, failsTo: { label: 'not identifiable', gloss: 'on this graph the probability is not identifiable' } },
    },
  },
  identify: {
    answersIt: true,
    words: {
      zh: { holds: { label: '可识别', gloss: '这张图上，该效应可从观测数据非参数识别' }, failsTo: { label: '不可识别', gloss: '这张图上，该效应无法非参数识别' } },
      en: { holds: { label: 'identifiable', gloss: 'on this graph the effect is nonparametrically identifiable from observational data' }, failsTo: { label: 'not identifiable', gloss: 'on this graph the effect is not nonparametrically identifiable' } },
    },
  },
  cause: {
    answersIt: true,
    words: {
      zh: { holds: { label: '是', gloss: '图里存在一条从原因到结果的有向路径' }, failsTo: { label: '否', gloss: '图里不存在从原因到结果的有向路径' } },
      en: { holds: { label: 'yes', gloss: 'a directed path runs from the source to the target in this graph' }, failsTo: { label: 'no', gloss: 'no directed path runs from the source to the target in this graph' } },
    },
  },
  assoc: {
    answersIt: true,
    words: {
      zh: { holds: { label: '有关联', gloss: '在给定的条件集下，两者在图里是 d-连通的' }, failsTo: { label: '无关联', gloss: '在给定的条件集下，两者在图里是 d-分离的' } },
      en: { holds: { label: 'associated', gloss: 'the two are d-connected in this graph given the conditioning set' }, failsTo: { label: 'not associated', gloss: 'the two are d-separated in this graph given the conditioning set' } },
    },
  },
  effect: {
    answersIt: false,
    words: {
      zh: { holds: { label: '可识别', gloss: '这张图上，该效应的估计量可识别' }, failsTo: { label: '不可识别', gloss: '这张图上，该效应的估计量不可识别' } },
      en: { holds: { label: 'identifiable', gloss: 'on this graph the estimand is identifiable' }, failsTo: { label: 'not identifiable', gloss: 'on this graph the estimand is not identifiable' } },
    },
  },
  scm_counterfactual: {
    answersIt: false,
    words: {
      zh: { holds: { label: '可解出', gloss: '按你声明的结构方程，能解出该个体的反事实值' }, failsTo: { label: '解不出', gloss: '按你声明的结构方程，该个体的反事实值解不出' } },
      en: { holds: { label: 'solvable', gloss: 'under the structural equations as declared, this unit\'s counterfactual value is determined' }, failsTo: { label: 'not solvable', gloss: 'under the structural equations as declared, this unit\'s counterfactual value is not determined' } },
    },
  },
  counterfactual: {
    answersIt: false,
    words: {
      zh: { holds: { label: '可识别', gloss: '这张图上，该反事实格可识别（点或界）' }, failsTo: { label: '不可识别', gloss: '这张图上，该反事实格不可识别' } },
      en: { holds: { label: 'identifiable', gloss: 'on this graph the cell is identifiable, as a point or as bounds' }, failsTo: { label: 'not identifiable', gloss: 'on this graph the cell is not identifiable' } },
    },
  },
  proximal_effect: {
    answersIt: false,
    words: {
      zh: { holds: { label: '可识别', gloss: '这张图上，近端识别条件成立，效应可识别' }, failsTo: { label: '不成立', gloss: '这张图上，近端识别条件不成立' } },
      en: { holds: { label: 'identifiable', gloss: 'on this graph the proximal criterion holds, so the effect is identifiable' }, failsTo: { label: 'conditions fail', gloss: 'on this graph the proximal criterion does not hold' } },
    },
  },
  causation: {
    answersIt: false,
    words: {
      zh: { holds: { label: '可识别', gloss: '这张图上，归因概率可识别' }, failsTo: { label: '不可识别', gloss: '这张图上，归因概率不可识别' } },
      en: { holds: { label: 'identifiable', gloss: 'on this graph the probabilities of causation are identifiable' }, failsTo: { label: 'not identifiable', gloss: 'on this graph the probabilities of causation are not identifiable' } },
    },
  },
  counterfactual_conjunction: {
    answersIt: false,
    words: {
      zh: { holds: { label: '可识别', gloss: '这张图上，ID* / IDC* 识别出了这个联合反事实' }, failsTo: { label: '不可识别', gloss: '这张图上，ID* 返回 hedge——不可识别' } },
      en: { holds: { label: 'identifiable', gloss: 'on this graph ID* / IDC* identifies the conjunction' }, failsTo: { label: 'not identifiable', gloss: 'on this graph ID* returns a hedge — not identifiable' } },
    },
  },
}

// `cap` is what the chip is labelled: 结论 only where the boolean IS the
// answer. Calling an identifiability precondition a 结论 is the same
// substitution in one word. It is this surface's own caption rather than a
// gloss of a kernel vocabulary, so it is written here in one language still.
// What the chip over a structural answer is called: `结论` only where the
// boolean IS the reader's question, `识别` where it is a step toward one.
const READOUT_CAP = {
  conclusion: { zh: '结论', en: 'Conclusion' },
  identification: { zh: '识别', en: 'Identification' },
} satisfies Record<string, Words>

// What this surface adds after a precondition that HOLDS: the boolean says
// the estimand is identifiable and the reader is looking at a chip because
// no number came. That is a fact about this render, not about the question,
// so it sits outside the table above rather than inside two of its ten
// entries — which is where it was, true of all eight and written on two.
const NO_NUMBER_YET: Words = {
  zh: ' —— 数值还没算出来',
  en: ' — no number has been computed yet',
}

export function structuralReadout(
  queryKind: string,
  value: boolean,
  lang: Lang = DEFAULT_LANG,
): { cap: string; label: string; gloss: string; tone: 'point' | 'none' } | null {
  const reading = QUESTION_READINGS[queryKind]
  if (!reading) return null
  const token = absent('no_word_for_this_token', lang, { token: queryKind })
  const said = say(reading.words, lang, {
    holds: { label: token, gloss: '' }, failsTo: { label: token, gloss: '' },
  })
  const side = value ? said.holds : said.failsTo
  const yet = side.gloss && value && !reading.answersIt
    ? fill(NO_NUMBER_YET, lang) : ''
  return {
    cap: fill(reading.answersIt ? READOUT_CAP.conclusion : READOUT_CAP.identification,
      lang),
    label: side.label,
    gloss: side.gloss + yet,
    tone: value ? 'point' : 'none',
  }
}

// "stays_up_late(me)@t-1" -> "stays_up_late@t-1" (drop the object args,
// keep the temporal annotation that carries causal-order meaning).
export function cleanPathNode(s: string): string {
  return s.replace(/\([^)]*\)/g, '')
}

export function fmtNum(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—'
  return Number.isInteger(n) ? String(n) : n.toFixed(3)
}

function band(b: Band | null | undefined): string {
  if (!b || b.point === null || b.point === undefined) return ''
  const ci = b.ci_lower != null && b.ci_upper != null
    ? ` · CI [${fmtNum(b.ci_lower)}, ${fmtNum(b.ci_upper)}]` : ''
  return `${fmtNum(b.point)}${ci}`
}

function corner(c: Record<string, unknown> | undefined): string {
  if (!c) return ''
  return '{' + Object.keys(c).sort().map((k) => `${k}=${String(c[k])}`).join(', ') + '}'
}

// Z is not one kind of thing. Only Z⁺ — the part not descended from the
// treatment — is checked for blocking, and blocking is what "back-door
// adjustment" means; Z⁻ is downstream of the treatment and cannot shut a
// confounding path. It is conditioned on so the selection nodes come out
// independent of the outcome, at the cost of an inner reweighting. One row
// naming their union as the selection back-door set tells a reader that a
// descendant of the treatment is holding a confounding path closed.
function selectionAdjustment(b: Record<string, any>, lang: Lang):
{ label: string; value: string }[] {
  const zp: string[] = b.z_plus ?? [], zm: string[] = b.z_minus ?? []
  if (!zp.length && !zm.length) {
    return b.adjustment_set?.length
      ? [{
        label: fill(SELECTION_SAYS.backdoor_for_selection, lang),
        value: varset(b.adjustment_set),
      }]
      : []
  }
  const rows: { label: string; value: string }[] = []
  if (zp.length) {
    rows.push({
      label: 'Z⁺',
      value: fill(SELECTION_SAYS.z_plus, lang, { vars: varset(zp) }),
    })
  }
  if (zm.length) {
    rows.push({
      label: 'Z⁻',
      value: fill(SELECTION_SAYS.z_minus, lang, { vars: varset(zm) }),
    })
  }
  return rows
}

// The routes an answer can arrive by — the family themis/blocks.py declares,
// in ITS declaration order, which is the order both surfaces state them in.
// A test parses this array and holds it equal to blocks.rendered_in(ROUTE),
// and holds every name in it to having a renderer below: the foldout named
// itself "怎么算出来的" while saying only the formula and the paths, and the
// ten blocks that answer that question exactly reached no reader at all.
const ROUTE_ORDER = [
  'identification',
  'iv_identification',
  'vector_iv_identification',
  'transport_identification',
  'joint_identification',
  'longitudinal_identification',
  'mediation_decomposition',
  'mediation_joint_decomposition',
  'proximal_estimand',
  'selection_recovery',
  'missing_data_recovery',
] as const

// The answer itself, on the paths that state it as a block rather than as a
// numeric_estimate — the theta path answers from the joint distribution and
// never calls an estimator, so there is no shape for answerRows to find. The
// region is here for the other reason a block can be: it is beside an
// estimate rather than instead of one, because what numeric_estimate promises
// is one estimand with one number and one interval, and a confidence region
// over k coefficients is none of those.
const ANSWER_ORDER = [
  'anderson_rubin_region', 'causation', 'scm_counterfactual'] as const

// Every block themis/blocks.py says a SURFACE has to render (rendered_in),
// and this surface's answer to that demand, family by family. It exists
// because the guarantee blocks.bind gives the report cannot cross a language
// boundary: BOUND is keyed by the importing Python module, so a .ts file can
// never appear in it, and "carried_by is None" was checked against one
// surface only. Route had this list and the answer family did not, which is
// exactly how two blocks holding the whole answer reached the browser as one
// unnamed number and, when it was an interval, as nothing.
//
// A test holds each entry equal to the registry, so a block added there fails
// here until something reads it. Two mechanisms are accepted because
// carried_by itself is two-valued: a name-indexed renderer in this file, or a
// definitional read in the component — the ledger's rows carry severity and
// are JSX, and flattening them to label/value pairs to satisfy a list would
// make the surface worse to make the check uniform.
export const RENDERED_BLOCKS: Record<string, readonly string[]> = {
  route: ROUTE_ORDER,
  answer: ANSWER_ORDER,
  assumption: ['assumption_ledger'],
  gap: [],
}

export interface Section {
  cap: string
  rows: { label: string; value: string }[]
}

type Blk = Record<string, any>

const varset = (xs: unknown): string =>
  '{' + (Array.isArray(xs) ? xs.map(String) : []).join(', ') + '}'

const preds = (xs: unknown): string =>
  varset(Array.isArray(xs) ? xs.map((e: any) => e?.predicate ?? '?') : [])

// The ordered factors a recovery is assembled from, and its formula when
// there are none. Mirrors the report's `_recovery_factorization`.
function recoveryFactors(part: any, what: string, lang: Lang):
{ label: string; value: string }[] {
  const factors: any[] = part?.factorization ?? []
  if (factors.length) {
    const product = factors
      .map((f) => `P(${f.factor}${f.conditioned_on?.length ? ` | ${within(f.conditioned_on)}` : ''})`)
      .join(' × ')
    return [{
      label: fill(FACTORS_SAYS.split_into, lang, { what, n: factors.length }),
      value: fill(FACTORS_SAYS.each_on_its_own_rows, lang, { product }),
    }]
  }
  return part?.recovery_formula
    ? [{
      label: fill(FACTORS_SAYS.recovery_formula_of, lang, { what }),
      value: String(part.recovery_formula),
    }]
    : []
}

const PATTERN_WORDS = generated.PATTERN_WORDS

// Pearl 2001's four conditions for the natural decomposition, and the two
// back-door conditions for the controlled one. Two tables because the two
// arms fail different theorems and the labels are drawn from disjoint sets.
const NDE_NIE_CONDITION_WORDS = generated.NDE_NIE_CONDITION_WORDS
const CDE_CONDITION_WORDS = generated.CDE_CONDITION_WORDS

// The shape a weak-instrument-robust confidence set came out in. One table
// for all three producers, because the shape means the same thing whichever
// moment was inverted. The word carries the consequence and not only the
// geometry: an unbounded set is not a wide interval, it is the statement
// that the data cannot bound the effect, and the bootstrap CI beside it
// looks finite and reassuring.
const AR_SET_KIND_WORDS = generated.AR_SET_KIND_WORDS

// The set itself. Only the heteroskedasticity-robust producer can return
// more than two pieces, so reading `segments` first and the endpoints second
// is one renderer rather than a branch per producer.
function arInterval(ar: ArConfidenceSet): string {
  if (ar.segments?.length) {
    return ar.segments
      .map((s) => `[${s.lower != null ? fmtNum(s.lower) : '−∞'}, ${s.upper != null ? fmtNum(s.upper) : '+∞'}]`)
      .join(' ∪ ')
  }
  if (ar.kind === 'empty') return '∅'
  if (ar.kind === 'whole_line') return '(−∞, +∞)'
  if (ar.kind === 'disconnected') {
    return `(−∞, ${fmtNum(ar.lower)}] ∪ [${fmtNum(ar.upper)}, +∞)`
  }
  return `[${ar.lower != null ? fmtNum(ar.lower) : '−∞'}, ${ar.upper != null ? fmtNum(ar.upper) : '+∞'}]`
}

// Which margin a misclassification correction inverted. The word says which
// variable was mismeasured rather than translating the token: a correction
// applied to the wrong margin is not a smaller correction, it is a different
// one, and that is what a reader checks against their own study.
const MEASUREMENT_SIDE_WORDS = generated.MEASUREMENT_SIDE_WORDS

// Which VanderWeele closed form the ratio-scale split was evaluated at. Same
// two tokens as a column's measurement scale and not the same vocabulary:
// there the word describes a variable, here it names a formula, and a reader
// checking the split against the paper needs the section number.
const FOUR_WAY_MEDIATOR_SCALE_WORDS = generated.FOUR_WAY_MEDIATOR_SCALE_WORDS

// Which design's residual a declared outcome measurement error was priced
// against. The sentence STATES the number rather than standing beside it,
// because what the number means is a fact about the design: on two of the
// three it is the precision cost, on the third the variance splits across
// terms only one of which carries the outcome residual, so the same
// arithmetic returns a CEILING. A reader who meets the figure first and the
// qualification second has already read it as the cost. Nothing on the
// envelope says which — a field for it would be a second record of the
// design name, free to disagree with it — so this table is where it is said.
// What the error does to the POINT is here for the same reason: nothing on
// the first two, and on the front door nothing only while the error is
// unrelated to the confounder that graph posits, which nobody measured.
const OUTCOME_ERROR_DESIGN_WORDS = generated.OUTCOME_ERROR_DESIGN_WORDS

// An envelope that never said which design. Not silently read as the
// back-door one: which residual the factor was taken around is exactly what
// decides whether it is the cost or a ceiling on it, and an older build's
// envelope is not evidence about a question that build never asked.
const OUTCOME_ERROR_DESIGN_UNSTATED: Words = {
  zh: '区间比结局测准时宽 {factor} 倍 —— 但这份信封没有说这个倍数是围绕哪个设计的残差算出来的，也就无从判断它是精度代价本身还是代价的上界',  en: 'the interval is {factor} times wider than it would be with the outcome measured exactly —— but this envelope does not say which design\'s residual the factor was taken around, so there is no telling whether it is the precision cost itself or a ceiling on it',
}

// The ` · ` that hangs a reason off a verdict. A constant rather than a
// `Words`: the separator is the same glyph in both languages, and what
// follows it is the envelope's own text, which no surface translates.
const aside = (said: unknown): string =>
  said == null || said === '' ? '' : ` · ${said}`

// One arm of a decomposition — identifiable, and on what. The condition
// table comes in rather than being picked here, so an arm cannot be given
// the other arm's theorem.
const arm = (info: Blk | undefined, label: string,
  conditions: Record<string, Words>, lang: Lang = DEFAULT_LANG) => ({
  label,
  value: info?.identifiable
    ? fill(ARM_SAYS.identifiable, lang) + (info.adjustment?.length
      ? aside(fill(ARM_SAYS.adjusting_on, lang, { vars: varset(info.adjustment) }))
      : '')
    : fill(ARM_SAYS.not_identifiable, lang) + (info?.failed_condition
      ? aside(`${info.failed_condition}——`
        + gloss(conditions, info.failed_condition, lang, ''))
      : ''),
})

// The words each route renderer says around the values it reads off its
// block. One table per renderer rather than one constant per string, so a
// renderer and what it says sit together and neither can be read without the
// other.
//
// A variable name, a number, a formula stays bare: those are DATA, and the
// only thing a second language changes about `${b.instrument}` is nothing.
// What becomes a `Words` is the text around them — which is also what makes
// the count of this tier honest.
const IDENTIFICATION_SAYS = {
  cap: { zh: '识别模式', en: 'Identification pattern' },
  pattern: { zh: '模式', en: 'Pattern' },
  adjustment_set: { zh: '调整集', en: 'Adjustment set' },
  no_open_backdoor: {
    zh: '无需调整——没有开放的后门路径',
    en: 'none needed — there is no open back-door path',
  },
  mediator_set: { zh: '中介集', en: 'Mediator set' },
  instrument: { zh: '工具', en: 'Instrument' },
  conditioned_on: { zh: '问题条件于', en: 'The question conditions on' },
  point_id_also_needs: {
    zh: '点识别另需', en: 'Point identification also needs',
  },
} satisfies Record<string, Words>

const IV_SAYS = {
  cap: { zh: '工具变量', en: 'Instrumental variable' },
  instrument: { zh: '工具', en: 'Instrument' },
  conditioning: { zh: '条件于', en: 'Conditioning on' },
  candidates: { zh: '候选工具', en: 'Candidate instruments' },
  one_of_n: { zh: '共 {n} 个，取其一', en: '{n} of them; one was taken' },
  caveat: { zh: '注意', en: 'Note' },
} satisfies Record<string, Words>

// Instruments for a treatment VECTOR. A separate table from IV_SAYS rather
// than a plural of it: exclusion is read on the treatment SET here, so an
// instrument that reaches the outcome through ANOTHER of the treatments is
// valid — that path is inside the intervention — and the same instrument
// would be rejected for a single-treatment query. Sharing the words would
// tell a reader the two conditions are one condition counted twice.
const VECTOR_IV_SAYS = {
  cap: { zh: '多内生工具变量', en: 'Instruments for a treatment vector' },
  treatments: { zh: '同时干预', en: 'Intervened on together' },
  instruments: { zh: '工具', en: 'Instruments' },
  conditioning: { zh: '在给定之后有效', en: 'Valid given' },
  moves: { zh: '`{instrument}` 移动的是', en: '`{instrument}` moves' },
  moves_nothing: {
    zh: '哪个处理都不移动——仍是有效工具，但给检验添一个自由度而不添信息',
    en: 'none of the treatments — still a valid instrument, but it costs the test a degree of freedom and contributes nothing',
  },
  under_identified: { zh: '点识别不了', en: 'Not point-identified' },
  fewer_than_treatments: {
    zh: '工具数（{q}）少于处理数（{k}），所以答案是一个置信域而不是一组数——域在数据约束不了的方向上无界，那是如实的回答',
    en: 'fewer instruments ({q}) than treatments ({k}), so the answer is a confidence region rather than a set of numbers — unbounded in the directions the data cannot constrain, which is the honest answer',
  },
  coverage: { zh: '覆盖率', en: 'Coverage' },
  weak_ok: {
    zh: '与第一阶段强弱无关——工具弱让域变大，不让它变错',
    en: 'does not depend on first-stage strength — weak instruments make the region larger, not wrong',
  },
} satisfies Record<string, Words>

// A transport question has one target population and any number of source
// domains, each its own selection diagram. One row per domain, because what
// shifts against the target — and so what has to be re-weighted, or why
// nothing suffices — is that domain's own fact.
const TRANSPORT_SAYS = {
  cap: { zh: '跨总体迁移', en: 'Transport across populations' },
  target_is: { zh: '目标总体', en: 'Target population' },
  from: { zh: '从 {source} 迁', en: 'From {source}' },
  source: { zh: '源总体', en: 'the source population' },
  target: { zh: '目标总体', en: 'the target population' },
  differs: {
    zh: '与目标分布不同的是 {variables}；',
    en: 'differs from the target on {variables}; ',
  },
  reweighted_on: {
    zh: '靠 {variables} 上的重加权抹平',
    en: 'evened out by reweighting on {variables}',
  },
  no_reweight: {
    zh: '不必重加权，效应原样搬得过来',
    en: 'no reweighting needed — the effect carries over unchanged',
  },
  // Said per domain, not only once at the end: when the domains disagree no
  // single number is reported at all, and these are the whole of the evidence.
  route_value: { zh: '，算出来是 {value}', en: ', which comes to {value}' },
} satisfies Record<string, Words>

const JOINT_SAYS = {
  cap: { zh: '联合干预', en: 'Joint intervention' },
  treatments: { zh: '同时干预', en: 'Intervened on together' },
  identification: { zh: '识别', en: 'Identification' },
  by_set_valued_id: {
    zh: '无可用调整集，由集合版 ID 算法识别',
    en: 'no adjustment set is available; identified by the set-valued ID algorithm',
  },
  joint_adjustment_set: {
    zh: '联合后门调整集', en: 'Joint back-door adjustment set',
  },
  no_adjustment: { zh: '无需调整', en: 'none needed' },
  interaction: { zh: '交互', en: 'Interaction' },
  not_additive: {
    zh: '差值尺度——逐个单独干预再相加拿不到',
    en: 'on the difference scale — intervening on each one separately and adding up does not reach it',
  },
} satisfies Record<string, Words>

const LONGITUDINAL_SAYS = {
  cap: { zh: '时变处理 (g-formula)', en: 'Time-varying treatment (g-formula)' },
  treatments: { zh: '处理序列', en: 'Treatment sequence' },
  empty: { zh: '（空）', en: '(empty)' },
  outcome: { zh: '结局', en: 'Outcome' },
  confounders_by_time: {
    zh: '各时点已测混杂', en: 'Measured confounders at each time point',
  },
  sequential_exchangeability: {
    zh: '序贯可交换性', en: 'Sequential exchangeability',
  },
  holds: {
    zh: '成立——每个时点的后门路径都被此前的历史挡住',
    en: 'holds — at every time point the back-door paths are blocked by the history before it',
  },
  fails: {
    zh: '不成立——g-formula 会给出有偏的数',
    en: 'fails — the g-formula would return a biased number',
  },
} satisfies Record<string, Words>

const MEDIATION_SAYS = {
  cap: { zh: '中介分解', en: 'Mediation decomposition' },
  mediator: { zh: '中介', en: 'Mediator' },
  on_no_path: {
    zh: '{mediator} 不在任何 X→…→M→…→Y 有向路径上',
    en: '{mediator} lies on no directed X→…→M→…→Y path',
  },
} satisfies Record<string, Words>

const MEDIATION_SET_SAYS = {
  cap: { zh: '中介集分解', en: 'Mediator-set decomposition' },
  mediators: { zh: '中介集', en: 'Mediator set' },
  invalid: {
    zh: '{mediators} 不是有效中介集',
    en: '{mediators} is not a valid mediator set',
  },
  as_one_block: {
    zh: '{mediators}（整体当一个块，不需内部排序）',
    en: '{mediators} — taken as one block, with no ordering needed inside it',
  },
} satisfies Record<string, Words>

const PROXIMAL_SAYS = {
  cap: { zh: '近端识别', en: 'Proximal identification' },
  latent: { zh: '未测混杂', en: 'Unmeasured confounder' },
  latent_taking_k: {
    zh: '{latent}（取 {k} 个值）', en: '{latent}, taking {k} values',
  },
  proxies: { zh: '代理', en: 'Proxies' },
  two_sides: {
    zh: '处理侧 {treatment} · 结局侧 {outcome}',
    en: 'treatment side {treatment} · outcome side {outcome}',
  },
  data_conditions: { zh: '数据须满足', en: 'The data has to satisfy' },
} satisfies Record<string, Words>

// Both recovery searches enumerate candidate sets by size and stop at a
// bound, so a negative verdict is a claim about the sets they looked at and
// not about every set there is. The bound is the quantifier on that claim,
// and a reader handed "not recoverable" without it is handed a stronger
// statement than the one that was checked. Said only on the negative
// branch: a positive verdict exhibits the set it found.
const SEARCH_RANGE: Words = {
  zh: '（搜索范围：最多 {n} 个变量的集合）',
  en: ' (search range: sets of at most {n} variables)',
}

function searchRange(b: { search_budget?: number }, lang: Lang): string {
  return Number.isInteger(b.search_budget)
    ? fill(SEARCH_RANGE, lang, { n: String(b.search_budget) })
    : ''
}


// The other half of what a negative verdict owes its reader. Its neighbour
// above gives the range the search covered; this says whether the test
// that produced the verdict is necessary as well as sufficient, because
// "none was found" and "none exists" are different claims and a reader
// shown the first will read the second. It was a clause the kernel wrote
// into its own sentence, in whichever branch remembered to write it.
const NOT_A_PROOF: Words = {
  zh: '（这个判据是充分条件，不是必要条件——「没找到」不等于「证明了恢复不出来」）',
  en: ' (the criterion is sufficient, not necessary — "none was found" is not "none exists")',
}

function notAProof(b: { complete_criterion?: boolean }, lang: Lang): string {
  return b.complete_criterion ? '' : fill(NOT_A_PROOF, lang)
}

const SELECTION_SAYS = {
  cap: { zh: '选择偏倚', en: 'Selection bias' },
  restricted_to: { zh: '样本被限制于', en: 'The sample is restricted to' },
  unbiased_effect: { zh: '无偏效应', en: 'The unbiased effect' },
  recoverable: {
    zh: '可从这份有偏样本恢复',
    en: 'can be recovered from this biased sample',
  },
  not_recoverable: {
    zh: '无法只从这份样本恢复',
    en: 'cannot be recovered from this sample alone',
  },
  external_data_needed: {
    zh: '还需外部数据', en: 'Also needs data from outside',
  },
  recovery_formula: { zh: '恢复式', en: 'Recovery formula' },
  backdoor_for_selection: {
    zh: '选择后门调整集', en: 'Back-door adjustment set for selection',
  },
  z_plus: {
    zh: '{vars} —— 不是处理的后代，挡后门路径的是它',
    en: '{vars} — not descendants of the treatment, and what blocks the back-door paths',
  },
  z_minus: {
    zh: '{vars} —— 是处理的后代，挡不了后门；条件在它上面是为了让选择节点与结局条件独立，代价是恢复式里多一层 P(Z⁻ | 处理, Z⁺) 的重加权',
    en: '{vars} — descendants of the treatment, so they block no back-door path; conditioning on them makes the selection node independent of the outcome, at the cost of one more reweighting by P(Z⁻ | treatment, Z⁺) in the recovery formula',
  },
} satisfies Record<string, Words>

const MISSING_SAYS = {
  cap: { zh: '缺失数据', en: 'Missing data' },
  mechanism: { zh: '机制', en: 'Mechanism' },
  partially_observed: { zh: '部分观测', en: 'Partially observed' },
  whole_estimand: { zh: '整条估计量', en: 'The estimand as a whole' },
  recoverable: {
    zh: '可从缺失数据恢复',
    en: 'can be recovered from the incomplete data',
  },
  not_recoverable: { zh: '不可恢复', en: 'cannot be recovered' },
  requires: { zh: '需 {what}', en: 'requires {what}' },
  conditional_layer: { zh: '条件概率这一层', en: 'The conditional layer' },
  covariate_margin: {
    zh: '协变量边缘 {target}', en: 'The covariate margin {target}',
  },
  whole_recovery_formula: {
    zh: '整条估计量的恢复式',
    en: 'Recovery formula for the estimand as a whole',
  },
} satisfies Record<string, Words>

const FACTORS_SAYS = {
  split_into: {
    zh: '{what}拆成 {n} 个因子', en: '{what}, split into {n} factors',
  },
  each_on_its_own_rows: {
    zh: '{product} —— 每个因子各在自己那些变量都被观测到的行上估',
    en: '{product} — each factor is estimated on the rows where its own variables were observed',
  },
  recovery_formula_of: {
    zh: '{what}的恢复式', en: 'Recovery formula for {what}',
  },
} satisfies Record<string, Words>

const ARM_SAYS = {
  identifiable: { zh: '可识别', en: 'identifiable' },
  adjusting_on: { zh: '调整 {vars}', en: 'adjusting on {vars}' },
  not_identifiable: { zh: '不可识别', en: 'not identifiable' },
} satisfies Record<string, Words>

// What a block renderer is given besides the block. Named rather than
// positional, and one type rather than two: the route table wrote this
// contract inline while the answer table wrote it as `BlockRenderer`, which
// left the inline one a parameter short and made a fourth — the reader's
// language — a choice between three unused positional arguments and a second
// contract. `ciLevel` is optional because it is genuinely per-path: the two
// containers that carry a probability of causation have DIFFERENT shapes, and
// the one reached through `blockRows` cannot hold a sampling band at all
// (`causationQuantity` is `{lower, upper, point}` with additionalProperties
// false, and says in the schema why). A path with no CI level to give says so
// by not giving one.
interface RenderCtx {
  ext: Record<string, any>
  lang: Lang
  ciLevel?: number
}

type BlockRenderer = (b: Blk, ctx: RenderCtx) => Section | null

// A renderer takes the whole extensions map so it can decline to repeat what
// a block above it already said, and may return null when that leaves it with
// nothing — a heading over no rows is worse than no heading.
const ROUTE_RENDERERS: Record<string, BlockRenderer> = {
  identification: (b, { lang }) => {
    const w = IDENTIFICATION_SAYS
    const rows = [{
      label: fill(w.pattern, lang),
      value: gloss(PATTERN_WORDS, b.pattern, lang),
    }]
    if (b.pattern === 'backdoor') {
      rows.push({
        label: fill(w.adjustment_set, lang),
        value: b.adjustment_set?.length
          ? varset(b.adjustment_set) : fill(w.no_open_backdoor, lang),
      })
    } else if (b.pattern === 'front_door') {
      rows.push({ label: fill(w.mediator_set, lang), value: varset(b.mediator_set) })
    } else if (b.pattern === 'instrumental_variable') {
      rows.push({ label: fill(w.instrument, lang), value: String(b.instrument ?? '?') })
    }
    if (b.conditioned_on?.length) {
      rows.push({ label: fill(w.conditioned_on, lang), value: varset(b.conditioned_on) })
    }
    if (b.required_assumption) {
      rows.push({
        label: fill(w.point_id_also_needs, lang),
        value: String(b.required_assumption),
      })
    }
    return { cap: fill(w.cap, lang), rows }
  },
  // strategy / instrument / conditioning / required_assumption are copied
  // into `identification` by the producer, which calls that copy the human
  // surface — so state them here only when no pattern line will.
  iv_identification: (b, { ext, lang }) => {
    const w = IV_SAYS
    const rows: { label: string; value: string }[] = []
    if (ext.identification?.pattern !== 'instrumental_variable') {
      rows.push({ label: fill(w.instrument, lang), value: String(b.instrument ?? '?') })
      if (b.conditioning?.length) {
        rows.push({ label: fill(w.conditioning, lang), value: varset(b.conditioning) })
      }
    }
    if (typeof b.alternatives_count === 'number' && b.alternatives_count > 1) {
      rows.push({
        label: fill(w.candidates, lang),
        value: fill(w.one_of_n, lang, { n: b.alternatives_count }),
      })
    }
    if (b.late_caveat) {
      rows.push({ label: fill(w.caveat, lang), value: String(b.late_caveat) })
    }
    return rows.length ? { cap: fill(w.cap, lang), rows } : null
  },
  // What each instrument MOVES is the fact no other block carries, and it is
  // reported rather than required: relevance is no part of what makes the
  // region valid, and what it predicts is whether the region came back
  // bounded. An instrument that moves nothing is therefore a row and not an
  // omission.
  vector_iv_identification: (b, { lang }) => {
    const w = VECTOR_IV_SAYS
    const treatments: string[] = b.treatments ?? []
    const instruments: string[] = b.instruments ?? []
    const rows = [
      { label: fill(w.treatments, lang), value: varset(treatments) },
      { label: fill(w.instruments, lang), value: varset(instruments) },
    ]
    for (const row of (b.relevance ?? []) as Blk[]) {
      const moves: string[] = row.moves ?? []
      rows.push({
        label: fill(w.moves, lang, { instrument: String(row.instrument ?? '?') }),
        value: moves.length ? varset(moves) : fill(w.moves_nothing, lang),
      })
    }
    if (b.conditioning?.length) {
      rows.push({
        label: fill(w.conditioning, lang),
        value: varset(b.conditioning),
      })
    }
    if (instruments.length < treatments.length) {
      rows.push({
        label: fill(w.under_identified, lang),
        value: fill(w.fewer_than_treatments, lang,
          { q: instruments.length, k: treatments.length }),
      })
    }
    rows.push({ label: fill(w.coverage, lang), value: fill(w.weak_ok, lang) })
    return { cap: fill(w.cap, lang), rows }
  },
  transport_identification: (b, { lang }) => {
    const w = TRANSPORT_SAYS
    const rows = [{
      label: fill(w.target_is, lang),
      value: String(b.target_population ?? fill(w.target, lang)),
    }]
    // Which variable a selection node sits on is declared once, on the node;
    // a route names its nodes by id, so the shift is looked up rather than
    // carried twice.
    const shifts = new Map<string, string>(
      (b.s_nodes ?? []).map((n: any) => [String(n?.id ?? ''),
        String(n?.affects?.predicate ?? '?')]))
    for (const route of b.sources ?? []) {
      const shifted = (route.s_nodes ?? [])
        .map((id: any) => shifts.get(String(id)))
        .filter((p: string | undefined): p is string => p != null)
      const lead = shifted.length
        ? fill(w.differs, lang, { variables: varset(shifted) }) : ''
      let value: string
      if (!route.transportable) {
        const words = TRANSPORT_BLOCKED_WORDS[String(route.blocked_by ?? '')]
        value = words
          ? fill(words, lang)
          : gloss(TRANSPORT_BLOCKED_WORDS, route.blocked_by, lang)
      } else {
        value = route.adjustment_set?.length
          ? fill(w.reweighted_on, lang, { variables: preds(route.adjustment_set) })
          : fill(w.no_reweight, lang)
        if (route.numeric) {
          value += fill(w.route_value, lang, { value: fmtNum(route.numeric.value) })
        }
      }
      rows.push({
        label: fill(w.from, lang, { source: route.source_population ?? fill(w.source, lang) }),
        value: lead + value,
      })
    }
    return { cap: fill(w.cap, lang), rows }
  },
  joint_identification: (b, { lang }) => {
    const w = JOINT_SAYS
    const rows = [{ label: fill(w.treatments, lang), value: varset(b.treatments) }]
    rows.push(b.pattern === 'joint_general_id'
      ? { label: fill(w.identification, lang), value: fill(w.by_set_valued_id, lang) }
      : {
        label: fill(w.joint_adjustment_set, lang),
        value: b.adjustment_set?.length
          ? varset(b.adjustment_set) : fill(w.no_adjustment, lang),
      })
    if (b.interaction) {
      rows.push({ label: fill(w.interaction, lang), value: fill(w.not_additive, lang) })
    }
    return { cap: fill(w.cap, lang), rows }
  },
  longitudinal_identification: (b, { lang }) => {
    const w = LONGITUDINAL_SAYS
    const rows = [{
      label: fill(w.treatments, lang),
      value: (b.treatments ?? []).join(' → ') || fill(w.empty, lang),
    }]
    rows.push({ label: fill(w.outcome, lang), value: String(b.outcome ?? '?') })
    if (b.confounders_by_time?.length) {
      rows.push({
        label: fill(w.confounders_by_time, lang),
        value: listing(b.confounders_by_time.map(varset), lang),
      })
    }
    rows.push({
      label: fill(w.sequential_exchangeability, lang),
      value: fill(b.identified ? w.holds : w.fails, lang),
    })
    return { cap: fill(w.cap, lang), rows }
  },
  mediation_decomposition: (b, { lang }) => ({
    cap: fill(MEDIATION_SAYS.cap, lang),
    rows: b.mediator_valid === false
      ? [{
        label: fill(MEDIATION_SAYS.mediator, lang),
        value: fill(MEDIATION_SAYS.on_no_path, lang,
          { mediator: String(b.mediator ?? '?') }),
      }]
      : [{ label: fill(MEDIATION_SAYS.mediator, lang), value: String(b.mediator ?? '?') },
         arm(b.nde_nie, 'NDE / NIE', NDE_NIE_CONDITION_WORDS, lang),
         arm(b.cde, 'CDE', CDE_CONDITION_WORDS, lang)],
  }),
  mediation_joint_decomposition: (b, { lang }) => ({
    cap: fill(MEDIATION_SET_SAYS.cap, lang),
    rows: b.mediator_set_valid === false
      ? [{
        label: fill(MEDIATION_SET_SAYS.mediators, lang),
        value: fill(MEDIATION_SET_SAYS.invalid, lang,
          { mediators: varset(b.mediators) }),
      }]
      : [{
        label: fill(MEDIATION_SET_SAYS.mediators, lang),
        value: fill(MEDIATION_SET_SAYS.as_one_block, lang,
          { mediators: varset(b.mediators) }),
      },
         arm(b.nde_nie, 'NDE / NIE', NDE_NIE_CONDITION_WORDS, lang),
         arm(b.cde, 'CDE', CDE_CONDITION_WORDS, lang)],
  }),
  proximal_estimand: (b, { lang }) => {
    const w = PROXIMAL_SAYS
    const latent = String(b.latent ?? '?')
    const rows = [{
      label: fill(w.latent, lang),
      value: b.latent_cardinality != null
        ? fill(w.latent_taking_k, lang, { latent, k: b.latent_cardinality })
        : latent,
    }]
    rows.push({
      label: fill(w.proxies, lang),
      value: fill(w.two_sides, lang, {
        treatment: String(b.treatment_proxy ?? '?'),
        outcome: String(b.outcome_proxy ?? '?'),
      }),
    })
    if (b.data_conditions) {
      rows.push({ label: fill(w.data_conditions, lang), value: String(b.data_conditions) })
    }
    return { cap: fill(w.cap, lang), rows }
  },
  selection_recovery: (b, { lang }) => {
    const w = SELECTION_SAYS
    const rows = [{ label: fill(w.restricted_to, lang), value: varset(b.selection_nodes) }]
    rows.push({
      label: fill(w.unbiased_effect, lang),
      value: b.recoverable
        ? fill(w.recoverable, lang)
        : fill(w.not_recoverable, lang) + aside(stated(b.failure_reason, lang))
          + searchRange(b, lang) + notAProof(b, lang),
    })
    if (b.recoverable) rows.push(...selectionAdjustment(b, lang))
    if (b.external_data_needed?.length) {
      rows.push({
        label: fill(w.external_data_needed, lang),
        value: listing(
          b.external_data_needed.map((one: unknown) => stated(one, lang)), lang),
      })
    }
    // "Recoverable" is a verdict; this is what it licenses you to compute.
    // Every other route's estimand is stated from `result.formula`, and a
    // recovery route writes its own instead, so that line never reaches it.
    if (b.recovery_formula) {
      rows.push({ label: fill(w.recovery_formula, lang), value: String(b.recovery_formula) })
    }
    return { cap: fill(w.cap, lang), rows }
  },
  missing_data_recovery: (b, { lang }) => {
    const w = MISSING_SAYS
    const rows = [{ label: fill(w.mechanism, lang), value: String(b.mechanism ?? '?') }]
    if (b.partially_observed?.length) {
      rows.push({ label: fill(w.partially_observed, lang), value: varset(b.partially_observed) })
    }
    const est = b.estimand ?? {}
    rows.push({
      label: fill(w.whole_estimand, lang),
      value: est.recoverable
        ? fill(w.recoverable, lang) + (est.requires?.length
          ? aside(fill(w.requires, lang, {
            what: listing(est.requires.map((one: unknown) => stated(one, lang)), lang),
          })) : '')
        : fill(w.not_recoverable, lang)
          + aside(stated(est.failure_reason ?? b.failure_reason, lang))
          + searchRange(b, lang) + notAProof(b, lang),
    })
    // Recoverability under missingness is a claim about an ORDER: each factor
    // has to be estimable on the rows where its own variables were observed,
    // and which order works is the content of the theorem. A verdict without
    // the factorization says that it worked and not what worked.
    rows.push(...recoveryFactors(b, fill(w.conditional_layer, lang), lang))
    if (b.covariate_recovery) {
      rows.push(...recoveryFactors(
        b.covariate_recovery,
        fill(w.covariate_margin, lang,
          { target: b.covariate_recovery.target ?? 'P(Z)' }),
        lang))
    }
    if (est.recovery_formula) {
      rows.push({
        label: fill(w.whole_recovery_formula, lang),
        value: String(est.recovery_formula),
      })
    }
    return { cap: fill(w.cap, lang), rows }
  },
}

// --- the answer, when a block rather than an estimate carries it -------------

const POC_LABELS: readonly (readonly [string, Words])[] = [
  ['pn', { zh: '必要性 PN(归因)', en: 'Necessity, PN (attribution)' }],
  ['ps', { zh: '充分性 PS', en: 'Sufficiency, PS' }],
  ['pns', { zh: '必要且充分 PNS', en: 'Necessity and sufficiency, PNS' }],
]

// What an interval's width is a fact about, and how tight the set is — the
// two vocabularies themis/intervals.py declares, restated here because the
// browser cannot import Python and held to it STRING BY STRING by a test.
//
// This surface used to derive the first of them from `point != null`, in a
// two-member table of its own, while the report derived it again and
// types.ts stated it a third time in prose. The envelope carries
// `ci_width_is` now: one pair of keys, two objects, and the estimator that
// saw which came out is the one that says (#419). `advice` is the half a
// pair of numbers cannot carry — whether collecting more data is the move.
const INTERVAL_WIDTH_WORDS = generated.INTERVAL_WIDTH_WORDS
export function intervalWidthLabel(width: unknown, lang: Lang = DEFAULT_LANG): string {
  return gloss(INTERVAL_WIDTH_WORDS, width, lang)
}

// The band beside an answer, said the same way wherever the answer is. Its
// own table rather than one estimand's, because the sentence is about the
// SHAPE — how wide, around what — and the two objects that wear this shape
// are a probability of causation and a counterfactual cell.
const INTERVAL_SAYS = {
  band: {
    zh: '{pct}% {kind} [{lower}, {upper}]',
    en: '{pct}% {kind} [{lower}, {upper}]',
  },
} satisfies Record<string, Words>

/** An answer that is a point or a set, and the interval beside it.
 *
 * This surface had one interval renderer, `band`, and it is built around a
 * POINT — it returns nothing at all when there is none. An answer whose shape
 * is a SET with a band around the set had no renderer, so the rows for it had
 * to be written by hand at each site, and that made writing them optional:
 * probabilities of causation got them and the counterfactual cell did not,
 * which is two reader surfaces disagreeing about what is in one envelope.
 *
 * `ci_width_is` travels beside the pair because one pair of key names holds
 * two different objects — the point's confidence interval where the answer
 * collapsed, and the outer band on the set where it did not (#419). Which one
 * came out is a fact about the RUN, so the estimator that saw it says it and
 * nothing here re-derives it from whether `point` is null.
 */
function pointOrSet(q: Blk, ciLevel: number | null | undefined, lang: Lang):
{ head: string; bounded: boolean; band: string } | null {
  const bounded = q.lower != null && q.upper != null
  const head = q.point != null ? fmtNum(q.point)
    : bounded ? `[${fmtNum(q.lower)}, ${fmtNum(q.upper)}]` : null
  if (head === null) return null
  const band = q.ci_lower != null && q.ci_upper != null
    ? fill(INTERVAL_SAYS.band, lang, {
      pct: Math.round((ciLevel ?? 0.95) * 100),
      kind: intervalWidthLabel(q.ci_width_is, lang),
      lower: fmtNum(q.ci_lower),
      upper: fmtNum(q.ci_upper),
    })
    : ''
  return { head, bounded, band }
}

const INTERVAL_WIDTH_ADVICE: Record<string, Words> = {
  sampling: {
     zh: '再收数据会变窄——宽度是这批样本的事',
     en: 'more data narrows this — the width is a fact about this sample',
   },
  identification: {
    zh: '再收数据不会变窄——宽度是这套假设的事，要窄得再加一条假设',
    en: 'more data does not narrow this — the width is a fact about the assumptions, and only a further assumption narrows it',
  },
  outer_band: {
    zh: '再收数据会收到识别区间那么窄为止，再窄要加假设',
    en: 'more data narrows this as far as the identified interval and no further; past that it takes a further assumption',
  },
}
export function intervalWidthAdvice(width: unknown, lang: Lang = DEFAULT_LANG): string {
  return gloss(INTERVAL_WIDTH_ADVICE, width, lang, '')
}

const TIGHTNESS_WORDS = generated.TIGHTNESS_WORDS
export function tightnessLabel(tight: unknown, lang: Lang = DEFAULT_LANG): string {
  return gloss(TIGHTNESS_WORDS, tight, lang)
}

const TIGHTNESS_ADVICE: Record<string, Words> = {
  sharp: {
     zh: '这已经是这套假设下最窄的区间了——没有更好的算法能收得更紧',
     en: 'this is the narrowest interval these assumptions allow — no better procedure tightens it',
   },
  outer: {
    zh: '真实的识别区间可能比这窄——这里报的是一个有效上界，不加假设也可能还有收紧的余地',
    en: 'the identified interval may be narrower than this — what is reported is a valid outer bound, and there may be room to tighten it without any further assumption',
  },
}
export function tightnessAdvice(tight: unknown, lang: Lang = DEFAULT_LANG): string {
  return gloss(TIGHTNESS_ADVICE, tight, lang, '')
}

// What the region says about the vector as a whole — the kernel's own words,
// generated like every other restatement. It leads the block because it is
// what decides how to read everything after it: a projected interval reported
// without it looks like an ordinary confidence interval, and for an unbounded
// region that reading is wrong in the direction that matters.
const REGION_SHAPE_WORDS = generated.REGION_SHAPE_WORDS

// Which way a K-way interaction went missing. Both members leave the joint
// contrast standing, so a row that simply vanished said nothing about a
// number the reader had been shown beside the contrast everywhere else.
const INTERACTION_UNAVAILABLE_WORDS = generated.INTERACTION_UNAVAILABLE_WORDS

// Why one source domain's effect does not reach the target, on a block whose
// sibling domains may be transporting fine. The two members differ in what a
// reader can do about them, so a route that simply went quiet would read as
// one that transports.
const TRANSPORT_BLOCKED_WORDS = generated.TRANSPORT_BLOCKED_WORDS

const REGION_SAYS = {
  cap: {
    zh: 'Anderson-Rubin 置信域（一组系数）',
    en: 'Anderson-Rubin confidence region for a coefficient vector',
  },
  head: {
    zh: '{pct}% 置信域 · {variables}', en: '{pct}% region · {variables}',
  },
  projection_note: {
    zh: '每行是把整个域投到那一个系数上——单看一行是保守的（覆盖率不低于名义水平），域本身才是这些系数的联合陈述',
    en: 'Each line is the whole region projected onto that one coefficient — read alone it is conservative (it covers at least as often as the nominal level), and the region is the joint statement',
  },
  projections: { zh: '逐系数区间', en: 'Per-coefficient intervals' },
  point: { zh: '两阶段最小二乘点', en: 'Two-stage least-squares point' },
  point_note: {
    zh: '{items}（它不必落在域内，落不进去说明过度识别约束被数据拉紧了）',
    en: '{items} (it need not lie inside the region, and when it does not the over-identifying restrictions are strained)',
  },
  coverage: { zh: '覆盖率', en: 'Coverage' },
  weak_ok: {
    zh: '与第一阶段强弱无关——工具弱让域变大，不让它变错',
    en: 'does not depend on first-stage strength — weak instruments make the region larger, not wrong',
  },
  empty_interval: { zh: '空（无解）', en: 'empty (no value survives)' },
} satisfies Record<string, Words>

// One coordinate's projection, in the notation this surface reads intervals
// in. The same six shapes `arInterval` renders one dimension down, and the
// same spelling of an open end, so a reader meeting both meets one notation.
function projectionInterval(p: Blk, lang: Lang): string {
  const lo = p.lower != null ? fmtNum(p.lower) : '−∞'
  const hi = p.upper != null ? fmtNum(p.upper) : '+∞'
  if (p.kind === 'empty') return fill(REGION_SAYS.empty_interval, lang)
  if (p.kind === 'whole_line') return '(−∞, +∞)'
  if (p.kind === 'disconnected') return `(−∞, ${lo}] ∪ [${hi}, +∞)`
  return `[${lo}, ${hi}]`
}

const CAUSATION_SAYS = {
  assumption_free: {
    zh: '无单调性假设时只能给到 [{lower}, {upper}]',
    en: 'with no monotonicity assumed, only [{lower}, {upper}] is reachable',
  },
  where_from: { zh: '这三个数怎么来的', en: 'Where the three numbers come from' },
  risks: {
    zh: 'P(Y|do X)={one} · P(Y|do ¬X)={zero} · ',
    en: 'P(Y|do X)={one} · P(Y|do ¬X)={zero} · ',
  },
  adjustment: { zh: '调整集 {vars}', en: 'adjustment set {vars}' },
  instrument: { zh: '工具变量 `{name}`', en: 'instrument `{name}`' },
  cap_pinned: {
    zh: '因果概率 · 单调性下点识别',
    en: 'Probabilities of causation · point-identified under monotonicity',
  },
  cap_monotone_bounded: {
    zh: '因果概率 · 已假设单调性，但仍只能给界',
    en: 'Probabilities of causation · monotonicity assumed, and still only bounds',
  },
  cap_bounded: {
    zh: '因果概率 · 未假设单调性，只能给界',
    en: 'Probabilities of causation · no monotonicity assumed, so bounds only',
  },
} satisfies Record<string, Words>

const SCM_COUNTERFACTUAL_SAYS = {
  cap: { zh: '线性 SCM 反事实', en: 'Linear SCM counterfactual' },
  target: { zh: '反事实值', en: 'Counterfactual value' },
  under_own_noise: {
    zh: '{value}（该个体自身的外生扰动下）',
    en: '{value}, under this unit\'s own exogenous noise',
  },
  abducted: { zh: '反推出的个体扰动', en: 'The unit\'s noise, recovered by abduction' },
  others: {
    zh: '同一反事实世界下的其他变量',
    en: 'Other variables in the same counterfactual world',
  },
} satisfies Record<string, Words>

// Where P(Y|do X) came from. The keys are extensions.causation's own enum in
// query_result.schema.json and a test holds them equal to it, because the
// alternative to a translation here is printing the identifier — and whether
// the two risks were derived from the graph or measured in an experiment is
// not a detail this surface can drop: nothing else on it says so.
// One vocabulary, two containers. The causation block and the counterfactual
// cell carry DIFFERENT subsets of the same licences, because the admissible
// set depends on which derivation rule wrote it — so this table states the
// whole vocabulary rather than either projection of it. Pinned against the
// kernel module for that reason; pinning it against one schema enum is how
// the other container's licences reached the reader as their own identifiers.
const RISK_PROVENANCE_WORDS = generated.RISK_PROVENANCE_WORDS

// What each step of the derivation did, in the reader's words. Mirrored from
// the kernel's derivation_glossary sentence for sentence — a test compares
// them with plain equality, which is the strongest pin available and costs
// nothing when the copy is exact.
//
// The chain is what every answered result has, whatever route it took: a
// d-separation verdict, the Tian-Pearl formulas, abduction-action-prediction.
// The blocks below it only exist when an identification PATTERN was
// recognised, so binding this foldout to them left it saying nothing about
// how the answer was reached for most of what arrives here.
//
// An unglossed rule surfaces as its own id rather than vanishing, the same
// default the report takes: on a disclosure surface, dropping a step the
// answer rests on is worse than printing a name the reader has to look up.
const DERIVATION_SAYS = generated.DERIVATION_SAYS


// How much unmeasured confounding a result could absorb. The word carries
// the consequence rather than the rank: "substantial" alone is a position in
// a scale the reader was never shown, and what they can act on is what it
// would take to explain the result away.
const EVALUE_BAND_WORDS = generated.EVALUE_BAND_WORDS
export function evalueBandLabel(band: string, lang: Lang = DEFAULT_LANG): string {
  return gloss(EVALUE_BAND_WORDS, band, lang)
}

// Which of the two E-values the reading was taken off. Printed beside it
// rather than kept for an audit trail: the two answer different questions,
// and a reader given only the verdict has to know which one was asked before
// they can tell whether it was the one they meant.
const EVALUE_BAND_BASIS_WORDS = generated.EVALUE_BAND_BASIS_WORDS
export function evalueBandBasisLabel(basis: string, lang: Lang = DEFAULT_LANG): string {
  return gloss(EVALUE_BAND_BASIS_WORDS, basis, lang)
}

// Every closed vocabulary this surface states to a reader, and the table it
// states it with. It exists for the reason RENDERED_BLOCKS does: the kernel
// declares these vocabularies once, the browser cannot import them, and a
// mirror nobody holds equal is a mirror that drifts silently. Eight tables
// were here before this list; three were pinned by a test, and of the five
// that were not, TWO had already drifted — one status the kernel emits was
// missing and one it does not emit was present, and eight of the thirty-six
// gap kinds had no title and reached readers as their own ids with the
// underscores swapped for spaces.
//
// A test holds each entry's key set equal to the kernel's own vocabulary,
// and holds this list equal to the translation tables declared in this file:
// a table added without a pin fails, and a vocabulary the kernel grows
// without a table fails too. What it cannot see is a vocabulary stated with
// no table at all — that is the hole this narrows rather than closes, and it
// is why the entries are named for vocabularies rather than for tables.
//
// Declared here rather than beside `Section` because every table it names
// has to exist first; a const referenced above its own initializer is a
// runtime error, not a lint.
export const VOCABULARIES: Record<string, Record<string, unknown>> = {
  result_status: STATUS_META,
  answer_tier: TIER_META,
  query_kind: QUESTION_READINGS,
  gap_kind: GAP_TITLE,
  gap_severity: SEVERITY_LABEL,
  assumption_severity: ASSUMPTION_SEVERITY_WORDS,
  assumption_layer: LEDGER_LAYER_WORDS,
  assumption_provenance: LEDGER_PROVENANCE_WORDS,
  identification_pattern: PATTERN_WORDS,
  interventional_risk_provenance: RISK_PROVENANCE_WORDS,
  refusal_kind: REFUSAL_KIND_WORDS,
  remedy: REMEDY_WORDS,
  derivation_rule: DERIVATION_SAYS,
  bounds_estimand: BOUNDS_ESTIMAND_WORDS,
  bounds_contrast_kind: BOUNDS_CONTRAST_WORDS,
  nde_nie_failed_condition: NDE_NIE_CONDITION_WORDS,
  cde_failed_condition: CDE_CONDITION_WORDS,
  anderson_rubin_set_kind: AR_SET_KIND_WORDS,
  anderson_rubin_region_shape: REGION_SHAPE_WORDS,
  interaction_unavailable_kind: INTERACTION_UNAVAILABLE_WORDS,
  transport_blocked_kind: TRANSPORT_BLOCKED_WORDS,
  measurement_correction_side: MEASUREMENT_SIDE_WORDS,
  four_way_mediator_scale: FOUR_WAY_MEDIATOR_SCALE_WORDS,
  outcome_error_design: OUTCOME_ERROR_DESIGN_WORDS,
  evalue_interpretation_band: EVALUE_BAND_WORDS,
  evalue_band_basis: EVALUE_BAND_BASIS_WORDS,
  interval_width: INTERVAL_WIDTH_WORDS,
  interval_tightness: TIGHTNESS_WORDS,
  // The six a refusal's sentence is assembled from (#411): the species'
  // templates, and the five closed sets its word-shaped holes are filled
  // from. Pinned like every other vocabulary here, and for a sharper
  // reason than most — this surface does not show these words beside a
  // value, it builds a sentence out of them, so a missing member is a
  // hole INSIDE the reader's sentence rather than one identifier next to
  // it.
  refusal_sentence: REFUSAL_SAYS,
  query_role: QUERY_ROLE_WORDS,
  monotonicity_refutation: REFUTATION_WORDS,
  recovery_mechanism: RECOVERY_WORDS,
  singular_matrix: SINGULAR_MATRIX_WORDS,
  outcome_error_premise: OUTCOME_ERROR_PREMISE_WORDS,
  // And the two a SHORTFALL's sentence is assembled from — the same
  // arrangement one channel over, for the same reason: what reaches the
  // reader here is a sentence built out of these, not a label beside a
  // value.
  gap_says: GAP_SAYS,
  unnamed_thing: UNNAMED_WORDS,
  gap_describes: GAP_DESCRIBES,
  query_part: QUERY_PART_WORDS,
  gap_wanted: GAP_WANTED,
  gap_route: GAP_ROUTES,
  gap_if_provided: GAP_IF_PROVIDED,
  measurement_scale: MEASUREMENT_SCALE_WORDS,
  // And one that belongs to no channel at all: it arrives through the
  // generic carrier, which names its own vocabulary. That is the point of
  // the carrier — a producer with a few values and a sentence to say no
  // longer needs a channel of its own, and so no longer writes the
  // sentence itself.
  e_value_undefined: E_VALUE_UNDEFINED_WORDS,
  // And one that arrives through the carrier one level further in: a gap's
  // sentence holds a LIST of these in a single hole, so a member missing
  // here is a hole inside a hole inside the reader's sentence.
  measurement_note: MEASUREMENT_NOTE_WORDS,
  // The three a gap's `required_data` STATES rather than values: what a
  // sample of the size beside it would buy, when the measurements would
  // have to be taken, and how the design could break SUTVA.
  precision_target: PRECISION_TARGET_WORDS,
  time_window: TIME_WINDOW_WORDS,
  sutva_concern: SUTVA_CONCERN_WORDS,
  // And the three a symbolic bound STATES rather than values: what is true
  // of the interval that no other field on its row carries, which
  // distribution a client must supply and how big its table is, and which
  // end of an interval an assumption moved — that last one inside the
  // first, a hole in a hole.
  bounds_note: BOUNDS_NOTE_WORDS,
  observable_required: OBSERVABLE_REQUIRED_WORDS,
  bound_side: BOUND_SIDE_WORDS,
  // And the four a RECOVERY verdict is made of: which condition a
  // negative came back empty on, in each of the two modules, and the two
  // labels — what an unbiased sample has to carry, and which factor of a
  // product this is — that used to be an English role word glued onto a
  // symbolic expression.
  selection_recovery_shortfall: SELECTION_SHORTFALL_WORDS,
  unbiased_distribution: UNBIASED_DISTRIBUTION_WORDS,
  missing_data_shortfall: MISSING_DATA_SHORTFALL_WORDS,
  recovery_factor: RECOVERY_FACTOR_WORDS,

  // And the two the ASSUMPTION LEDGER's line is made of. The third is
  // `gap_describes` above: one channel's line is the statements the gap it
  // came from is made of, which is why the field is a list.
  assumption_claim: ASSUMPTION_CLAIM_WORDS,
  theta_prior_claim: THETA_PRIOR_CLAIM_WORDS,
  // Which way the treatment may move the outcome. It reached
  // a reader only through the ledger's own line before; a
  // bounds note holds it in a hole now, so this surface has
  // to resolve it as well.
  monotonicity: MONOTONICITY_WORDS,
}

// The other keyed tables in this file, each saying why it is not one of the
// above. They are keyed by a kernel vocabulary too, but what they hold is
// renderers rather than the reader's words, so what has to be checked about
// them is that every block reaches a renderer — which RENDERED_BLOCKS and
// blocks.bind already check, from the other end. The list is here rather
// than in the test because the decision belongs beside the table: a new
// table has to answer "is this a vocabulary" somewhere, and answering it in
// a file the writer never opens is how the five unpinned tables happened.
export const NOT_VOCABULARIES = [
  'ROUTE_RENDERERS',
  'ANSWER_RENDERERS',
  // An index OF vocabularies rather than a vocabulary: it maps a
  // vocabulary's NAME to the table above that states it, so a sentence's
  // word-shaped hole can be looked up by the set it came from. Its members
  // are already pinned, one table each, in VOCABULARIES. It was four such
  // indexes — one per channel, one for the sentences a carrier may name, and
  // one that was the union of the first two — until a hole could hold a
  // whole sentence and the distinction between the four stopped existing.
  'WORDS',
  // Keyed by the schema's own property names for numeric_estimate rather than
  // by a kernel vocabulary, and holding renderers rather than words. What has
  // to be checked about it is that every composite part reaches a renderer,
  // which tests/test_the_answer_has_no_silent_parts.py checks from the schema.
  'NUMERIC_DETAIL_RENDERERS',
  'RENDERED_BLOCKS',
  'VOCABULARIES',
  // The second half of two vocabularies above: not the reader's NAME for a
  // member but what the reader can do about it, which is one string per
  // member either way. Not in VOCABULARIES because that table is one per
  // vocabulary and the name is what a member is pinned by; both are held to
  // the kernel string by string in
  // tests/test_an_interval_says_what_its_width_is_a_fact_about.py.
  'INTERVAL_WIDTH_ADVICE',
  'TIGHTNESS_ADVICE',
] as const

const ANSWER_RENDERERS: Record<string, BlockRenderer> = {
  // The shape first, then one interval per coefficient. Not folded into the
  // numeric answer above: the region is a statement about k coefficients
  // jointly, and the intervals below it are its shadows — each valid on its
  // own and none of them the region.
  anderson_rubin_region: (b, { lang }) => {
    const w = REGION_SAYS
    const region = (b.region ?? {}) as Blk
    if (!region.shape) return null
    const rows = [{
      label: fill(w.head, lang, {
        pct: Math.round((region.ci_level ?? 0.95) * 100),
        variables: varset(region.treatments),
      }),
      value: gloss(REGION_SHAPE_WORDS, region.shape, lang),
    }]
    const projections = (region.projections ?? []) as Blk[]
    for (const p of projections) {
      rows.push({
        label: String(p.treatment ?? '?'),
        value: projectionInterval(p, lang),
      })
    }
    if (projections.length) {
      rows.push({
        label: fill(w.projections, lang),
        value: fill(w.projection_note, lang),
      })
    }
    const point = region.point as number[] | null | undefined
    if (point?.length) {
      const names: string[] = region.treatments ?? []
      rows.push({
        label: fill(w.point, lang),
        value: fill(w.point_note, lang, {
          items: point.map((v, i) => `${names[i] ?? i}=${fmtNum(v)}`).join(' · '),
        }),
      })
    }
    rows.push({ label: fill(w.coverage, lang), value: fill(w.weak_ok, lang) })
    return { cap: fill(w.cap, lang), rows }
  },
  // Three quantities, each said by name. The point/interval split is per
  // quantity rather than per block: monotonicity does not make the block
  // appear, it collapses what is inside each of the three.
  causation: (b, { ciLevel, lang }) => {
    const w = CAUSATION_SAYS
    const rows: { label: string; value: string }[] = []
    // A declared monotonicity reaches the two solvers at different places, so
    // it buys different things and the caption cannot be read off the flag
    // alone. Tian-Pearl takes it as a second theorem: the interval stays
    // assumption-free and a point appears beside it. The response-function
    // program takes it as a restriction of the model: it narrows the interval
    // and, in practice, never pins it. So what is said here is read off what
    // actually came back.
    const foldedIn = b.interventional_risk_provenance === 'instrument_response_polytope'
    const pinned = POC_LABELS.some(([key]) => (b[key] as Blk | undefined)?.point != null)
    for (const [key, said] of POC_LABELS) {
      const q = b[key] as Blk | undefined
      if (!q) continue
      // Point-or-set, and the band beside it, through the renderer the shape
      // has rather than written out here: this site used to be the only one,
      // and being the only one is what let the other site skip it.
      const shown = pointOrSet(q, ciLevel, lang)
      if (shown === null) continue
      const { head, bounded } = shown
      const beside: string[] = shown.band ? [shown.band] : []
      // Tian-Pearl bounds assume no monotonicity, so when both are present
      // this is exactly what the assumption bought. Not sayable on the route
      // that folds the assumption into the interval — there the pair IS the
      // post-assumption answer, and calling it the assumption-free one would
      // invert the sentence.
      if (q.point != null && bounded && !foldedIn) {
        beside.push(fill(w.assumption_free, lang,
          { lower: fmtNum(q.lower), upper: fmtNum(q.upper) }))
      }
      rows.push({
        label: fill(said, lang),
        value: head + (beside.length ? aside(beside.join(' · ')) : ''),
      })
    }
    if (!rows.length) return null
    // WHICH route produced the three numbers — on every route, not only the
    // ones that end with a pair of risks to print. One route reaches them
    // without any: the response-function program on an instrument. Hanging
    // this row off the risks being present meant that route said nothing at
    // all about where its intervals came from.
    const licence = RISK_PROVENANCE_WORDS[String(b.interventional_risk_provenance ?? '')]
    if (licence) {
      const how = say(licence, lang, absent('no_word_for_this_token', lang,
        { token: String(b.interventional_risk_provenance) }))
      const adj = Array.isArray(b.adjustment) && b.adjustment.length
        ? aside(fill(w.adjustment, lang, { vars: `{${b.adjustment.join(', ')}}` }))
        : ''
      const risks = b.p_y_do_x1 != null && b.p_y_do_x0 != null
        ? fill(w.risks, lang,
          { one: fmtNum(b.p_y_do_x1), zero: fmtNum(b.p_y_do_x0) })
        : ''
      rows.push({
        label: fill(w.where_from, lang),
        value: risks + how + adj
          + (b.instrument
            ? aside(fill(w.instrument, lang, { name: String(b.instrument) }))
            : ''),
      })
    }
    // Whether monotonicity was assumed decides which of two questions the
    // three numbers answer, so it belongs in the caption, not a footnote.
    return {
      cap: fill(pinned ? w.cap_pinned
        : b.monotonic ? w.cap_monotone_bounded : w.cap_bounded, lang),
      rows,
    }
  },
  // The value is also in numeric_result and the figure above prints it. What
  // only this block has is the abduction: the exogenous noise recovered from
  // what this unit actually did is what makes the number a counterfactual for
  // THEM rather than a prediction for an average unit.
  scm_counterfactual: (b, { lang }) => {
    if (b.target_value == null) return null
    const w = SCM_COUNTERFACTUAL_SAYS
    const rows = [{
      label: b.target != null ? String(b.target) : fill(w.target, lang),
      value: fill(w.under_own_noise, lang, { value: fmtNum(b.target_value) }),
    }]
    const noise = (b.abducted_noise ?? {}) as Record<string, number>
    const names = Object.keys(noise).sort()
    if (names.length) {
      rows.push({
        label: fill(w.abducted, lang),
        value: names.map((n) => `U_${n}=${fmtNum(noise[n])}`).join(' · '),
      })
    }
    const cf = (b.counterfactual_values ?? {}) as Record<string, number>
    const others = Object.keys(cf).filter((k) => k !== b.target).sort()
    if (others.length) {
      rows.push({
        label: fill(w.others, lang),
        value: others.map((k) => `${k}=${fmtNum(cf[k])}`).join(' · '),
      })
    }
    return { cap: fill(w.cap, lang), rows }
  },
}

// One family's blocks, in registry order, each rendered once. Empty when the
// envelope states none — a heading over nothing is a promise it did not make.
function blockRows(
  order: readonly string[],
  renderers: Record<string, BlockRenderer>,
  extensions: Record<string, unknown> | undefined,
  lang: Lang,
): Section[] {
  if (!extensions) return []
  const out: Section[] = []
  for (const name of order) {
    const block = extensions[name] as Blk | undefined
    if (!block || typeof block !== 'object') continue
    const section = renderers[name](
      block, { ext: extensions as Record<string, any>, lang })
    if (section) out.push(section)
  }
  return out
}

/** How the answer was arrived at. */
export function routeRows(extensions: Record<string, unknown> | undefined,
  lang: Lang = DEFAULT_LANG): Section[] {
  return blockRows(ROUTE_ORDER, ROUTE_RENDERERS, extensions, lang)
}

/** The answer itself, on the paths that carry it as a block. */
export function answerBlockRows(extensions: Record<string, unknown> | undefined,
  lang: Lang = DEFAULT_LANG): Section[] {
  return blockRows(ANSWER_ORDER, ANSWER_RENDERERS, extensions, lang)
}

// The paper each part of an answer implements. Six containers on the envelope
// write a citation — three extension blocks and three parts of
// numeric_estimate — and none of them reached a reader on either surface.
// Every table in this file is keyed by what ONE container holds, so in each of
// the six the citation was some other table's subject, and six independent
// decisions dropped it without an exception anywhere. Hence the walk: a
// version of this that listed today's containers would render the same six and
// lose the seventh in exactly the same way.

/** Every citation the envelope carries, in the order first met. */
export function citations(result: QueryResult): string[] {
  const found: string[] = []
  const walk = (node: unknown): void => {
    if (Array.isArray(node)) { node.forEach(walk); return }
    if (node === null || typeof node !== 'object') return
    const said = (node as Record<string, unknown>)['reference']
    if (typeof said === 'string' && !found.includes(said)) found.push(said)
    Object.values(node as Record<string, unknown>).forEach(walk)
  }
  walk(result)
  return found
}

/** The steps, in the order they ran, each said in words.
 *
 * Rendered whenever there is a chain, not as a fallback for when the blocks
 * said nothing: a fallback would hide the case this exists for, where the
 * blocks say a little and the foldout keeps looking answered.
 */
const DERIVATION_ROWS_SAYS = {
  cap: {
    zh: '推导链 · 每一步都可被独立重导',
    en: 'The derivation chain · every step can be re-derived on its own',
  },
  step: { zh: '第 {i} 步', en: 'Step {i}' },
} satisfies Record<string, Words>

export function derivationRows(derivation: Derivation | undefined,
  lang: Lang = DEFAULT_LANG): Section | null {
  const steps = derivation?.steps ?? []
  if (!steps.length) return null
  return {
    cap: fill(DERIVATION_ROWS_SAYS.cap, lang),
    rows: steps.map((step, i) => {
      // A rule can have more than one route through it — the counterfactual
      // cell reaches an interval by a consistency identity or over an
      // instrument's response polytope under the same rule name. Which one
      // ran is the step's licence, and a rule-keyed sentence cannot say it.
      const said = gloss(DERIVATION_SAYS, step.rule, lang)
      const licence = RISK_PROVENANCE_WORDS[
        String(step.inputs?.interventional_risk_provenance ?? '')
      ]
      const how = licence
        ? say(licence, lang, absent('no_word_for_this_token', lang,
            { token: String(step.inputs?.interventional_risk_provenance) }))
        : ''
      return {
        label: fill(DERIVATION_ROWS_SAYS.step, lang, { i: i + 1 }),
        value: said + aside(how),
      }
    }),
  }
}

// --- how the NUMBER was computed ---------------------------------------------
//
// The routes above answer "how was the estimand identified" from the
// `extensions` map. The other half of that foldout's question — what the
// estimator then did with the data — is recorded on `numeric_estimate`, which
// that binding does not reach. This foldout has been caught by the same gap
// twice, and both times it was patched by appending one item: the formula is a
// field rather than a block, and the derivation chain lives under `derivation`.
// The third instance is ten blocks, and at ten, appending stops being a repair.
//
// Mirrored from the report's `_NUMERIC_DETAIL_RENDERERS` block for block, so a
// reader comparing the two surfaces is not reconciling two accounts of one
// computation.

const FOUR_WAY_PARTS: readonly (readonly [string, Words, Words])[] = [
  ['cde',
   { zh: '纯直接（CDE）', en: 'Pure direct (CDE)' },
   { zh: '既不经中介、也没借助处理与中介的交互',
     en: 'neither through the mediator nor by way of any treatment-mediator interaction' }],
  ['intref',
   { zh: '仅交互（INTref）', en: 'Interaction only (INTref)' },
   { zh: '靠处理与中介的交互，但中介本身没有被处理改变',
     en: 'by way of the treatment-mediator interaction, with the mediator itself unchanged by the treatment' }],
  ['intmed',
   { zh: '交互且经中介（INTmed）', en: 'Interaction and mediation (INTmed)' },
   { zh: '既靠交互，又靠处理确实改变了中介',
     en: 'both by way of the interaction and because the treatment did change the mediator' }],
  ['pie',
   { zh: '纯中介（PIE）', en: 'Pure indirect (PIE)' },
   { zh: '完全经由中介，不涉及交互',
     en: 'entirely through the mediator, with no interaction involved' }],
]

const LONGITUDINAL_COMMON_SAYS = {
  strategies: { zh: '策略对比', en: 'The two strategies' },
  contrast: {
    zh: '全程 {treated} 下 E[{outcome}]={ey1}，全程 {control} 下 E[{outcome}]={ey0}，上面那个数是两者之差',
    en: 'under {treated} throughout, E[{outcome}]={ey1}; under {control} throughout, E[{outcome}]={ey0}; the number above is the difference',
  },
  treatments: { zh: '各时点的处理', en: 'Treatment at each time point' },
  adjusted_at: { zh: '第 {i} 时点调整', en: 'Adjusted at time point {i}' },
} satisfies Record<string, Words>

const THETA_ARM_SAYS = {
  unstated: { zh: '未说明', en: 'not stated' },
  missing_key: { zh: '；缺的是 {key}', en: '; what is missing is {key}' },
  over_cap: {
    zh: '（中介参考点有 {found} 个，超过上限 {cap}）',
    en: ' (there are {found} mediator reference points, over the cap of {cap})',
  },
  no_numbers: { zh: '{arm} 没能算出数', en: '{arm} produced no numbers' },
  at_mediator: {
    zh: '{arm} 没能算出数（中介固定在 {value} 时）',
    en: '{arm} produced no numbers with the mediator fixed at {value}',
  },
} satisfies Record<string, Words>

const THETA_MEDIATION_SAYS = {
  cap: {
    zh: '中介分解的数 · 对着声明的概率直接算，不是从数据估的',
    en: 'The mediation decomposition as numbers · computed against the declared probabilities rather than estimated from data',
  },
  te: { zh: '总效应 TE', en: 'Total effect TE' },
  te_value: {
    zh: '{te}（E[Y|全处理]={ey1} − E[Y|全对照]={ey0}）',
    en: '{te} (E[Y|treated throughout]={ey1} − E[Y|control throughout]={ey0})',
  },
  at_control: { zh: '以对照为参照', en: 'Referenced against control' },
  at_treated: { zh: '以处理为参照', en: 'Referenced against treatment' },
  split: {
    zh: '直接效应 NDE={nde} ＋ 经中介的间接效应 NIE={nie}（跨世界量 {cross}）',
    en: 'direct effect NDE={nde} ＋ indirect effect through the mediator NIE={nie} (cross-world quantity {cross})',
  },
  opposite_ways: {
    zh: '　—— 两条通路方向相反：一条在推高、另一条在压低，总效应是相互抵消之后剩下的那点',
    en: '　— the two paths point opposite ways: one pushes up and the other pulls down, and the total effect is what is left after they cancel',
  },
  cde_at: {
    zh: '中介固定在 {at} 时的 CDE', en: 'CDE with the mediator fixed at {at}',
  },
  cde_flips: { zh: 'CDE 随中介取值变号', en: 'The CDE changes sign with the mediator' },
  cde_flips_why: {
    zh: '处理与中介之间存在交互，「直接效应」这句话本身要看中介被固定在哪里才成立',
    en: 'the treatment and the mediator interact, so "the direct effect" is only a well-formed phrase once the mediator is fixed somewhere',
  },
  nde_nie_arm: { zh: '自然直接/间接效应 NDE / NIE', en: 'Natural direct / indirect effects, NDE / NIE' },
  cde_arm: { zh: '受控直接效应 CDE', en: 'Controlled direct effect, CDE' },
} satisfies Record<string, Words>

// The lines both longitudinal routes state, in the same words: they contrast
// the same two strategies over the same times and differ only in how they got
// there, so a reader comparing them should not have to reconcile the wording.
function longitudinalCommon(b: LongitudinalRoute, lang: Lang):
{ label: string; value: string }[] {
  const w = LONGITUDINAL_COMMON_SAYS
  const rows = [{
    label: fill(w.strategies, lang),
    value: fill(w.contrast, lang, {
      treated: fmtNum(b.strategy_treated),
      control: fmtNum(b.strategy_control),
      outcome: String(b.outcome),
      ey1: fmtNum(b.e_y_treated),
      ey0: fmtNum(b.e_y_control),
    }),
  }]
  if (b.treatments?.length) {
    rows.push({ label: fill(w.treatments, lang), value: varset(b.treatments) })
  }
  ;(b.confounders_by_time ?? []).forEach((names, i) => {
    rows.push({
      label: fill(w.adjusted_at, lang, { i: i + 1 }),
      value: varset(names),
    })
  })
  return rows
}

// Why one arm of a theta mediation produced no numbers. An arm the graph
// calls identifiable and the distribution cannot answer is a different
// situation from one the graph refuses, and the route block above states
// only the second.
function thetaArmStatus(status: any, arm: string, lang: Lang):
{ label: string; value: string } {
  const w = THETA_ARM_SAYS
  let value = gapSaid(status, lang)
    || String(status.status ?? fill(w.unstated, lang))
  if (status.missing_key) {
    value += fill(w.missing_key, lang, { key: status.missing_key })
  }
  if (status.reference_point_count != null && status.cap != null) {
    value += fill(w.over_cap, lang,
      { found: status.reference_point_count, cap: status.cap })
  }
  return {
    label: status.mediator_value
      ? fill(w.at_mediator, lang, { arm, value: status.mediator_value })
      : fill(w.no_numbers, lang, { arm }),
    value,
  }
}

// The decomposition itself, evaluated against a declared joint distribution.
// Mirrors the report's `_detail_theta_mediation`.
function thetaMediation(b: Record<string, any>, lang: Lang): Section {
  const w = THETA_MEDIATION_SAYS
  const nm = b.numeric
  const rows: { label: string; value: string }[] = []
  if (nm.te != null) {
    rows.push({
      label: fill(w.te, lang),
      value: fill(w.te_value, lang, {
        te: fmtNum(nm.te),
        ey1: fmtNum(nm.e_y_treated),
        ey0: fmtNum(nm.e_y_control),
      }),
    })
  }
  for (const [direct, indirect, said, cross] of [
    ['nde_at_control', 'nie_at_treated', w.at_control, 'e_y_cross_treated_outer'],
    ['nde_at_treated', 'nie_at_control', w.at_treated, 'e_y_cross_control_outer'],
  ] as const) {
    const nde = nm[direct], nie = nm[indirect]
    if (nde == null || nie == null) continue
    let value = fill(w.split, lang, {
      nde: fmtNum(nde), nie: fmtNum(nie), cross: fmtNum(nm[cross]),
    })
    // Not legible from the pair unless it is said: the headline is their sum
    // and reads as a single direction.
    if (nde * nie < 0) value += fill(w.opposite_ways, lang)
    rows.push({ label: fill(said, lang), value })
  }
  const cde: Record<string, number> = nm.cde ?? {}
  const values = Object.keys(cde).sort()
  for (const at of values) {
    rows.push({ label: fill(w.cde_at, lang, { at }), value: fmtNum(cde[at]) })
  }
  if (values.length > 1) {
    const nums = values.map((k) => cde[k])
    if (Math.min(...nums) * Math.max(...nums) < 0) {
      rows.push({
        label: fill(w.cde_flips, lang),
        value: fill(w.cde_flips_why, lang),
      })
    }
  }
  if (nm.nde_nie_status) {
    rows.push(thetaArmStatus(nm.nde_nie_status, fill(w.nde_nie_arm, lang), lang))
  }
  if (nm.cde_status) {
    rows.push(thetaArmStatus(nm.cde_status, fill(w.cde_arm, lang), lang))
  }
  return { cap: fill(w.cap, lang), rows }
}

// The container the part hangs off, not the whole result: the table below is
// keyed by a PATH, and the dispatcher walks all but the last step, so each
// renderer still reads its own key by name the way it always did.
// Two required parameters rather than the block renderers' named object: a
// detail renderer is handed its own container and the reader's language and
// nothing else, and a one-field object is a wrapper around nothing. What
// made the object right over there is that a fourth thing was arriving into
// a signature that already carried an optional third.
type DetailRenderer = (holder: Record<string, any>, lang: Lang) => Section | null

const STRATIFIED_WALD_SAYS = {
  aggregation: { zh: '聚合方式', en: 'How the cells were aggregated' },
  ratio_of_sums: {
    zh: '加权结局差 {outcome} ÷ 加权处理差 {treatment}，聚合的是两个加权和之比，不是各格比值的平均，所以单格没有自己的 Wald 估计',
    en: 'weighted outcome shift {outcome} ÷ weighted treatment shift {treatment}. What is aggregated is a ratio of two weighted sums, not an average of per-cell ratios, so no cell has a Wald estimate of its own',
  },
  unconditional: { zh: '（无条件）', en: '(unconditional)' },
  cell: {
    zh: '权重 {weight}，n={n}（工具高 {high} / 低 {low}），结局差 {outcome}，处理差 {treatment}',
    en: 'weight {weight}, n={n} ({high} with the instrument high / {low} low), outcome shift {outcome}, treatment shift {treatment}',
  },
  cap: {
    zh: '分层 Wald 的逐格明细 · {n} 格，按 {order} 依次切',
    en: 'Stratified Wald, cell by cell · {n} cells, cut by {order} in that order',
  },
} satisfies Record<string, Words>

const RECOVERED_ATE_SAYS = {
  cap: { zh: '从有缺失的数据里恢复', en: 'Recovered from data with missing values' },
  recovered: { zh: '恢复值', en: 'The recovered value' },
  against_listwise: {
    zh: '{point}；直接丢掉不完整的行（列表删除法）会得到 {naive} —— 两者之差就是这套方法全部的作用，也是判断它值不值得用的依据',
    en: '{point}; dropping the incomplete rows outright (listwise deletion) gives {naive} — the difference between the two is everything this method does, and the basis for judging whether it was worth using',
  },
  no_comparison: {
    zh: '{point}（这次没有算出列表删除法的对照值，无从判断恢复挪动了多少）',
    en: '{point} (no listwise-deletion comparison was computed this time, so there is no telling how far the recovery moved it)',
  },
  rows_used: { zh: '用了多少行', en: 'How many rows were used' },
  rows_detail: {
    zh: '共 {total} 行，完全没有缺失的只有 {complete} 行；条件概率那一层用了 {conditional} 行、边缘分布那一层用了 {marginal} 行 —— 每个因子各用自己的完整行估计，这正是它与列表删除法的差别所在',
    en: '{total} rows in all, of which only {complete} have nothing missing; the conditional layer used {conditional} rows and the marginal layer {marginal} — each factor is estimated on its own complete rows, which is exactly where this differs from listwise deletion',
  },
  missing_columns: { zh: '有缺失的列', en: 'Columns with missing values' },
  adjustment: { zh: '调整集', en: 'Adjustment set' },
  adjustment_detail: {
    zh: '{vars}，分 {strata} 层，bootstrap {boot} 次',
    en: '{vars}, over {strata} strata, {boot} bootstrap resamples',
  },
} satisfies Record<string, Words>

const SELECTION_NUMERIC_SAYS = {
  cap: { zh: '从选择偏倚里恢复', en: 'Recovered from selection bias' },
  two_arms: { zh: '两臂均值', en: 'The two arm means' },
  two_arms_value: {
    zh: '处理臂 {treated}，对照臂 {control}，上面那个数是两者之差',
    en: 'treated arm {treated}, control arm {control}; the number above is the difference',
  },
  reference_sample: { zh: '外部参照样本', en: 'External reference sample' },
  reference_value: {
    zh: 'N={n} —— 恢复出的数只在「这份样本代表未被筛过的人群」这句话成立时才成立',
    en: 'N={n} — the recovered number holds only insofar as this sample represents the unselected population',
  },
  restricted_to: { zh: '样本被限制在', en: 'The sample is restricted to' },
} satisfies Record<string, Words>

const MEASUREMENT_SAYS = {
  moved_by: { zh: '校正挪了多少', en: 'How far the correction moved it' },
  moved_value: {
    zh: '未校正 {naive} → 校正后 {corrected}，校正把这个数挪了 {delta}',
    en: 'uncorrected {naive} → corrected {corrected}; the correction moved it by {delta}',
  },
  differential: { zh: '差分性误分类', en: 'Differential misclassification' },
  differential_by: {
    zh: '错分概率随 {by} 而变，所以每一档各用自己的混淆矩阵求逆',
    en: 'the misclassification probabilities vary with {by}, so each level inverts its own confusion matrix',
  },
  differential_by_something: {
    zh: '错分概率随另一个变量而变，所以每一档各用自己的混淆矩阵求逆',
    en: 'the misclassification probabilities vary with another variable, so each level inverts its own confusion matrix',
  },
  determinant: { zh: '混淆矩阵行列式', en: 'Determinant of the confusion matrix' },
  determinant_value: {
    zh: 'det={det} —— 越接近 0，求逆越不稳定，校正后的数对矩阵本身的误差越敏感',
    en: 'det={det} — the closer to 0, the less stable the inversion and the more sensitive the corrected number is to error in the matrix itself',
  },
  det_exposure: { zh: '暴露通道', en: 'Exposure channel' },
  det_outcome: { zh: '结局通道', en: 'Outcome channel' },
  det_joint: { zh: '联合', en: 'Joint' },
  out_of_simplex: {
    zh: '求逆的结果落到了概率单纯形之外',
    en: 'The inversion landed outside the probability simplex',
  },
  out_of_simplex_why: {
    zh: '说明声明的混淆矩阵与这批数据对不上，校正后的数不该照单全收',
    en: 'the declared confusion matrix and this data do not fit together, so the corrected number should not be taken at face value',
  },
  cap: {
    zh: '误分类校正 · {side}', en: 'Misclassification correction · {side}',
  },
} satisfies Record<string, Words>

const CALIBRATION_SAYS = {
  moved_by: { zh: '校正挪了多少', en: 'How far the correction moved it' },
  moved_value: {
    zh: '未校正斜率 {naive} → 校正后 {corrected}，校正把这个数挪了 {delta}',
    en: 'uncorrected slope {naive} → corrected {corrected}; the correction moved it by {delta}',
  },
  reliability: { zh: '可靠度 λ', en: 'Reliability λ' },
  reliability_value: {
    zh: '{lambda} —— λ=1 表示这个变量测得完全准，λ 越小衰减越重；校正做的就是把衰减除回去',
    en: '{lambda} — λ=1 means the variable is measured exactly; the smaller λ, the heavier the attenuation, and the correction is dividing that attenuation back out',
  },
  declared_variances: {
    zh: '声明的测量误差方差', en: 'Declared measurement-error variances',
  },
  from_outside: {
    zh: '{list}（这是外部知识，不是从数据里估的）',
    en: '{list} — external knowledge, not estimated from the data',
  },
  design_vars: { zh: '设计矩阵列序', en: 'Design-matrix column order' },
  cap: {
    zh: '回归校准（连续变量的经典加性测量误差） · 暴露 {exposure}',
    en: 'Regression calibration (classical additive error on a continuous variable) · exposure {exposure}',
  },
} satisfies Record<string, Words>

const LONGITUDINAL_SAYS_G = {
  cap: { zh: '纵向 g-公式（g-computation）', en: 'Longitudinal g-formula (g-computation)' },
  how: { zh: '做法', en: 'How it was done' },
  how_value: {
    zh: '按时间顺序模拟每个时点的处理与协变量，再把结局在模拟出的人群上平均',
    en: 'simulate treatment and covariates forward through each time point, then average the outcome over the simulated population',
  },
  budget: { zh: '预算', en: 'Budget' },
  budget_value: {
    zh: '蒙特卡洛模拟 {sim} 次，bootstrap {boot} 次',
    en: '{sim} Monte Carlo draws, {boot} bootstrap resamples',
  },
  other_route: { zh: '另一条独立路线', en: 'The other, independent route' },
  ipw_not_run: {
    zh: 'IPW 边缘结构模型这次没有跑：它靠加权而不是靠模拟，两条算出来的数一致与否本身就是一个发现，这里没有这个发现',
    en: 'the IPW marginal structural model was not run this time. It works by weighting rather than by simulation, and whether the two agree is itself a finding — one this result does not carry',
  },
} satisfies Record<string, Words>

const LONGITUDINAL_SAYS_IPW = {
  cap: { zh: '纵向 IPW 边缘结构模型', en: 'Longitudinal IPW marginal structural model' },
  how: { zh: '做法', en: 'How it was done' },
  how_value: {
    zh: '按每个时点接受该处理的概率给个体加权，在加权后的人群上拟合一个边缘模型',
    en: 'weight each subject by the probability of the treatment they received at each time point, then fit a marginal model on the reweighted population',
  },
  stabilized: { zh: '稳定化权重', en: 'Stabilized weights' },
  unstabilized: { zh: '未稳定化权重', en: 'Unstabilized weights' },
  weight_value: {
    zh: '均值 {mean}，最大 {max} —— 最大值远高于均值，说明少数个体在主导这个数',
    en: 'mean {mean}, maximum {max} — a maximum far above the mean means a handful of subjects carry this number',
  },
  msm_coefficients: {
    zh: '边缘结构模型系数', en: 'Marginal structural model coefficients',
  },
  budget: { zh: '预算', en: 'Budget' },
  budget_value: { zh: 'bootstrap {boot} 次', en: '{boot} bootstrap resamples' },
  other_route: { zh: '另一条独立路线', en: 'The other, independent route' },
  gformula_not_run: {
    zh: 'g-公式这次没有跑：它靠模拟而不是靠加权，两条算出来的数一致与否本身就是一个发现，这里没有这个发现',
    en: 'the g-formula was not run this time. It works by simulation rather than by weighting, and whether the two agree is itself a finding — one this result does not carry',
  },
} satisfies Record<string, Words>

const FOUR_WAY_SAYS = {
  prop_mediated: { zh: '经中介的比例', en: 'Proportion mediated' },
  prop_interaction: { zh: '涉及交互的比例', en: 'Proportion involving interaction' },
  prop_eliminated: {
    zh: '把中介固定住能消掉的比例', en: 'Proportion eliminated by fixing the mediator',
  },
  part_value: { zh: '{value} —— {gloss}', en: '{value} — {gloss}' },
  additive_interaction: { zh: '相加交互', en: 'Additive interaction' },
  additive_value: {
    zh: '{value} —— 处理与中介同时在场时，比两者各自贡献相加多出来的部分',
    en: '{value} — how much more there is when treatment and mediator are both present than the sum of what each contributes alone',
  },
  why_split: { zh: '为什么值得拆', en: 'Why the split is worth having' },
  why_split_value: {
    zh: '能靠改中介去掉的只有经中介那两块，交互那部分改中介去不掉',
    en: 'only the two mediated parts can be removed by acting on the mediator; the interaction part cannot',
  },
  which_closed_form: { zh: '用的哪个闭式', en: 'Which closed form was used' },
  cap_difference: {
    zh: '四分解（VanderWeele，差分尺度）· 总效应 {te} 拆成四块，四块相加等于总效应',
    en: 'Four-way decomposition (VanderWeele, difference scale) · total effect {te} split into four parts that sum back to it',
  },
  cap_ratio: {
    zh: '四分解（VanderWeele，比值尺度／超额相对风险）· 总相对风险 {rr}，超额部分 {err} 拆成四块',
    en: 'Four-way decomposition (VanderWeele, ratio scale / excess relative risk) · total relative risk {rr}, with the excess {err} split into four parts',
  },
  unavailable: { zh: '四分解没有给出', en: 'No four-way decomposition' },
  reason: { zh: '原因', en: 'Reason' },
  reason_unstated: { zh: '未说明原因', en: 'no reason stated' },
  reason_value: {
    zh: '{reason} —— 是算过之后判定在这种数据形状下不成立，不是没算',
    en: '{reason} — this was computed and then judged not to hold for data of this shape; it is not that nobody tried',
  },
} satisfies Record<string, Words>

const IV_NUMERIC_SAYS = {
  aggregation: { zh: '聚合方式', en: 'How the cells were aggregated' },
  ratio_of_sums: {
    zh: '加权结局差 {outcome} ÷ 加权处理差 {treatment} = {late}；分母就是依从者（会被工具推动的那部分人）占比，聚合的是两个加权和之比，不是各格比值的平均',
    en: 'weighted outcome shift {outcome} ÷ weighted treatment shift {treatment} = {late}. The denominator IS the share of compliers — the people the instrument moves — and what is aggregated is a ratio of two weighted sums, not an average of per-cell ratios',
  },
  unconditional: { zh: '（无条件）', en: '(unconditional)' },
  cell: {
    zh: '权重 {weight}；工具取高时 P(结局)={py1}、P(处理)={px1}，取低时 P(结局)={py0}、P(处理)={px0}',
    en: 'weight {weight}; with the instrument high, P(outcome)={py1} and P(treatment)={px1}; with it low, P(outcome)={py0} and P(treatment)={px0}',
  },
  cap_conditional: {
    zh: 'Wald 比值的逐格明细 · {n} 格，按 {order} 依次切',
    en: 'The Wald ratio, cell by cell · {n} cells, cut by {order} in that order',
  },
  cap_unconditional: {
    zh: 'Wald 比值的逐格明细 · {n} 格，工具无条件',
    en: 'The Wald ratio, cell by cell · {n} cells, with the instrument unconditional',
  },
} satisfies Record<string, Words>

const TRANSPORT_NUMERIC_SAYS = {
  cap: { zh: '迁移后的数', en: 'The transported number' },
  value: {
    zh: '{value}（用前者的数据，算的是后者的效应）',
    en: '{value} — computed from the first population\'s data, for the second population\'s effect',
  },
  // Several transporting domains are several estimands of the one quantity,
  // so their agreement is a restriction that could have failed and did not.
  agreed: { zh: '通过了的检验', en: 'A test that passed' },
  agreed_value: {
    zh: '另外 {others} 个源总体各自算出同一个数',
    en: '{others} further source populations each arrive at the same number',
  },
} satisfies Record<string, Words>

const NUMERIC_DETAIL_RENDERERS: Record<string, DetailRenderer> = {
  // The aggregate is a ratio of two weighted sums and not an average of
  // per-stratum ratios, so no cell has a Wald estimate of its own to print.
  'numeric_estimate.stratified_wald': (ne, lang) => {
    const w = STRATIFIED_WALD_SAYS
    const sw = ne.stratified_wald as StratifiedWald
    const order = sw.conditioning_order ?? []
    const strata = sw.strata ?? []
    const rows = [{
      label: fill(w.aggregation, lang),
      value: fill(w.ratio_of_sums, lang, {
        outcome: fmtNum(sw.outcome_shift),
        treatment: fmtNum(sw.treatment_shift),
      }),
    }]
    for (const s of strata) {
      const cell = listing(
        (s.values ?? []).map((v, i) => `${order[i] ?? '?'}=${String(v)}`), lang)
        || fill(w.unconditional, lang)
      rows.push({
        label: cell,
        // `?? '?'` rather than letting the slot take undefined: a template
        // literal printed the word `undefined` at the reader here, and this
        // file already spells a missing name `?`.
        value: fill(w.cell, lang, {
          weight: fmtNum(s.weight),
          n: s.n_obs ?? '?',
          high: s.n_instrument_high ?? '?',
          low: s.n_instrument_low ?? '?',
          outcome: fmtNum(s.outcome_shift),
          treatment: fmtNum(s.treatment_shift),
        }),
      })
    }
    // Ordered rather than as a variable set: the cell labels are read
    // positionally against this, so braces would say the order does not
    // matter when it is the whole content of the field.
    return {
      cap: fill(w.cap, lang, { n: strata.length, order: listing(order, lang) }),
      rows,
    }
  },

  // The comparison is the method: recovering an effect from data with missing
  // values is worth doing exactly insofar as it differs from dropping the
  // incomplete rows.
  'numeric_estimate.recovered_ate': (ne, lang) => {
    const w = RECOVERED_ATE_SAYS
    const ra = ne.recovered_ate as RecoveredAte
    const rows = [{
      label: fill(w.recovered, lang),
      value: ra.naive_listwise_ate != null
        ? fill(w.against_listwise, lang, {
          point: fmtNum(ra.point), naive: fmtNum(ra.naive_listwise_ate),
        })
        : fill(w.no_comparison, lang, { point: fmtNum(ra.point) }),
    }, {
      label: fill(w.rows_used, lang),
      value: fill(w.rows_detail, lang, {
        total: ra.n_total ?? '?',
        complete: ra.n_complete_case ?? '?',
        conditional: ra.n_conditional_rows ?? '?',
        marginal: ra.n_marginal_rows ?? '?',
      }),
    }]
    if (ra.missing_columns?.length) {
      rows.push({ label: fill(w.missing_columns, lang), value: varset(ra.missing_columns) })
    }
    rows.push({
      label: fill(w.adjustment, lang),
      value: fill(w.adjustment_detail, lang, {
        vars: varset(ra.adjustment),
        strata: ra.n_strata ?? '?',
        boot: ra.n_bootstrap ?? '?',
      }),
    })
    return { cap: fill(w.cap, lang), rows }
  },

  // Which half of Z needs an unselected sample is not a property of the half:
  // when Z is independent of the selection nodes nothing comes from outside,
  // and when it is not, what is needed is Z⁺'s marginal or the joint over the
  // treatment and both halves. So the split is stated for what it is, and
  // `external_data_needed` beside it answers the other question.
  'numeric_estimate.selection_recovery_numeric': (ne, lang) => {
    const w = SELECTION_NUMERIC_SAYS
    const sr = ne.selection_recovery_numeric as SelectionRecovery
    const rows = [{
      label: fill(w.two_arms, lang),
      value: fill(w.two_arms_value, lang, {
        treated: fmtNum(sr.mu_treated), control: fmtNum(sr.mu_control),
      }),
    }, ...selectionAdjustment(sr, lang)]
    if (sr.reference_sample_size != null) {
      rows.push({
        label: fill(w.reference_sample, lang),
        value: fill(w.reference_value, lang, { n: sr.reference_sample_size }),
      })
    }
    const selected = sr.selected_values ?? {}
    if (Object.keys(selected).length) {
      rows.push({
        label: fill(w.restricted_to, lang),
        value: listing(
          Object.keys(selected).map((k) => `${k}=${String(selected[k])}`), lang),
      })
    }
    return { cap: fill(w.cap, lang), rows }
  },

  // `det` is what makes the correction unstable: a near-singular matrix
  // inverts into a large move the data does not support, and the corrected
  // point alone cannot be told apart from a large real correction.
  'numeric_estimate.measurement_correction': (ne, lang) => {
    const w = MEASUREMENT_SAYS
    const mc = ne.measurement_correction as MeasurementCorrection
    const rows: { label: string; value: string }[] = []
    if (mc.naive_point != null && ne.point != null) {
      rows.push({
        label: fill(w.moved_by, lang),
        value: fill(w.moved_value, lang, {
          naive: fmtNum(mc.naive_point),
          corrected: fmtNum(ne.point),
          delta: fmtNum(ne.point - mc.naive_point),
        }),
      })
    }
    if (mc.differential) {
      rows.push({
        label: fill(w.differential, lang),
        value: mc.differential_by
          ? fill(w.differential_by, lang, { by: mc.differential_by })
          : fill(w.differential_by_something, lang),
      })
    }
    if (mc.det != null) {
      rows.push({
        label: fill(w.determinant, lang),
        value: fill(w.determinant_value, lang, { det: fmtNum(mc.det) }),
      })
    }
    for (const [key, said] of [
      ['det_exposure', w.det_exposure],
      ['det_outcome', w.det_outcome],
      ['det_joint', w.det_joint],
    ] as const) {
      const v = mc[key]
      if (v != null) rows.push({ label: fill(said, lang), value: `det=${fmtNum(v)}` })
    }
    if (mc.out_of_simplex) {
      rows.push({
        label: fill(w.out_of_simplex, lang),
        value: fill(w.out_of_simplex_why, lang),
      })
    }
    const side = gloss(MEASUREMENT_SIDE_WORDS, mc.side ?? 'outcome', lang)
    return rows.length ? { cap: fill(w.cap, lang, { side }), rows } : null
  },

  // λ is the whole correction — the corrected slope is the naive one divided
  // through by it — so the corrected number alone cannot tell a small
  // measurement problem from a large one.
  'numeric_estimate.regression_calibration': (ne, lang) => {
    const w = CALIBRATION_SAYS
    const rc = ne.regression_calibration as RegressionCalibration
    const rows: { label: string; value: string }[] = []
    if (rc.naive_point != null && ne.point != null) {
      rows.push({
        label: fill(w.moved_by, lang),
        value: fill(w.moved_value, lang, {
          naive: fmtNum(rc.naive_point),
          corrected: fmtNum(ne.point),
          delta: fmtNum(ne.point - rc.naive_point),
        }),
      })
    }
    if (rc.reliability != null) {
      rows.push({
        label: fill(w.reliability, lang),
        value: fill(w.reliability_value, lang, { lambda: fmtNum(rc.reliability) }),
      })
    }
    const variances = rc.error_variances ?? {}
    if (Object.keys(variances).length) {
      rows.push({
        label: fill(w.declared_variances, lang),
        value: fill(w.from_outside, lang, {
          list: listing(Object.keys(variances)
            .map((k) => `${k} σ²_u=${fmtNum(variances[k])}`), lang),
        }),
      })
    }
    if (rc.design_vars?.length) {
      rows.push({ label: fill(w.design_vars, lang), value: varset(rc.design_vars) })
    }
    return rows.length
      ? { cap: fill(w.cap, lang, { exposure: String(rc.exposure) }), rows }
      : null
  },

  // Only one of the two longitudinal routes runs per query, so whether they
  // agree — which is itself a finding — is not available. Saying so is the
  // difference between a check that was not run and one that passed.
  'numeric_estimate.longitudinal_gformula': (ne, lang) => {
    const w = LONGITUDINAL_SAYS_G
    const b = ne.longitudinal_gformula as LongitudinalRoute & { n_sim?: number }
    const rows = [{
      label: fill(w.how, lang), value: fill(w.how_value, lang),
    }, ...longitudinalCommon(b, lang), {
      label: fill(w.budget, lang),
      value: fill(w.budget_value, lang,
        { sim: b.n_sim ?? '?', boot: b.n_bootstrap ?? '?' }),
    }, {
      label: fill(w.other_route, lang), value: fill(w.ipw_not_run, lang),
    }]
    return { cap: fill(w.cap, lang), rows }
  },

  // The weight summary is the diagnostic that matters: a maximum far above the
  // mean means a handful of subjects carry the estimate, which no interval
  // built from those same weights will say.
  'numeric_estimate.longitudinal_ipw_msm': (ne, lang) => {
    const w = LONGITUDINAL_SAYS_IPW
    const b = ne.longitudinal_ipw_msm as LongitudinalRoute & {
      stabilized?: boolean; msm_coefficients?: number[]
      weight_mean?: number; weight_max?: number
    }
    const rows = [{
      label: fill(w.how, lang), value: fill(w.how_value, lang),
    }, ...longitudinalCommon(b, lang)]
    if (b.weight_mean != null) {
      rows.push({
        label: fill(b.stabilized ? w.stabilized : w.unstabilized, lang),
        value: fill(w.weight_value, lang, {
          mean: fmtNum(b.weight_mean), max: fmtNum(b.weight_max),
        }),
      })
    }
    if (b.msm_coefficients?.length) {
      rows.push({
        label: fill(w.msm_coefficients, lang),
        value: b.msm_coefficients.map((c) => fmtNum(c)).join(', '),
      })
    }
    rows.push({
      label: fill(w.budget, lang),
      value: fill(w.budget_value, lang, { boot: b.n_bootstrap ?? '?' }),
    })
    rows.push({
      label: fill(w.other_route, lang), value: fill(w.gformula_not_run, lang),
    })
    return { cap: fill(w.cap, lang), rows }
  },

  // Four numbers that sum to the total, worth separating because they point at
  // different interventions: what is mediated can be attacked at the mediator,
  // what is interaction cannot.
  'numeric_estimate.four_way_decomposition': (ne, lang) => {
    const w = FOUR_WAY_SAYS
    const fw = ne.four_way_decomposition as FourWayDifference
    const rows: { label: string; value: string }[] = []
    for (const [key, label, why] of FOUR_WAY_PARTS) {
      const said = band(fw[key as keyof FourWayDifference] as Band | undefined)
      if (said) {
        rows.push({
          label: fill(label, lang),
          value: fill(w.part_value, lang, { value: said, gloss: fill(why, lang) }),
        })
      }
    }
    for (const [key, label] of [
      ['prop_mediated', w.prop_mediated],
      ['prop_interaction', w.prop_interaction],
    ] as const) {
      const said = band(fw[key])
      if (said) rows.push({ label: fill(label, lang), value: said })
    }
    if (fw.additive_interaction != null) {
      rows.push({
        label: fill(w.additive_interaction, lang),
        value: fill(w.additive_value, lang,
          { value: fmtNum(fw.additive_interaction) }),
      })
    }
    rows.push({
      label: fill(w.why_split, lang), value: fill(w.why_split_value, lang),
    })
    return {
      cap: fill(w.cap_difference, lang, { te: band(fw.te) || '—' }),
      rows,
    }
  },

  // A binary outcome makes the multiplicative scale the natural one, and the
  // difference-scale block beside it is a different decomposition rather than
  // the same numbers rescaled.
  'numeric_estimate.four_way_ratio': (ne, lang) => {
    const w = FOUR_WAY_SAYS
    const fr = ne.four_way_ratio as FourWayRatio
    const rows: { label: string; value: string }[] = []
    for (const [key, label, why] of FOUR_WAY_PARTS) {
      const said = band(fr[`err_${key}` as keyof FourWayRatio] as Band | undefined)
      if (said) {
        rows.push({
          label: fill(label, lang),
          value: fill(w.part_value, lang, { value: said, gloss: fill(why, lang) }),
        })
      }
    }
    for (const [key, label] of [
      ['prop_mediated', w.prop_mediated],
      ['prop_interaction', w.prop_interaction],
      ['prop_eliminated', w.prop_eliminated],
    ] as const) {
      const said = band(fr[key])
      if (said) rows.push({ label: fill(label, lang), value: said })
    }
    rows.push({
      label: fill(w.which_closed_form, lang),
      value: gloss(FOUR_WAY_MEDIATOR_SCALE_WORDS, fr.mediator_scale, lang),
    })
    return {
      cap: fill(w.cap_ratio, lang, {
        rr: band(fr.total_rr) || '—', err: band(fr.total_err) || '—',
      }),
      rows,
    }
  },

  // A reader shown no decomposition cannot tell "not applicable here" from
  // "nobody tried", and those call for different next steps.
  'numeric_estimate.four_way_unavailable': (ne, lang) => ({
    cap: fill(FOUR_WAY_SAYS.unavailable, lang),
    rows: [{
      label: fill(FOUR_WAY_SAYS.reason, lang),
      value: fill(FOUR_WAY_SAYS.reason_value, lang, {
        reason: ne.four_way_unavailable?.reason
          ?? fill(FOUR_WAY_SAYS.reason_unstated, lang),
      }),
    }],
  }),

  // The same table the data path states above, from a declared joint
  // distribution instead of from rows. The block's own late_caveat is printed
  // at the reader and says the value "aggregates the per-stratum LATEs in
  // strata" — two fields the reader was then given no way to see.
  'extensions.iv_identification.numeric': (b, lang) => {
    const w = IV_NUMERIC_SAYS
    const nm = b.numeric
    const order: string[] = nm.conditioning_order ?? []
    const strata: any[] = nm.strata ?? []
    const rows = [{
      label: fill(w.aggregation, lang),
      value: fill(w.ratio_of_sums, lang, {
        outcome: fmtNum(nm.outcome_shift),
        treatment: fmtNum(nm.treatment_shift),
        late: fmtNum(nm.late),
      }),
    }]
    for (const s of strata) {
      const cell = listing((s.values ?? [])
        .map((v: unknown, i: number) => `${order[i] ?? '?'}=${String(v)}`),
      lang) || fill(w.unconditional, lang)
      rows.push({
        label: cell,
        value: fill(w.cell, lang, {
          weight: fmtNum(s.weight),
          py1: fmtNum(s.p_y_given_z_treated),
          px1: fmtNum(s.p_x_given_z_treated),
          py0: fmtNum(s.p_y_given_z_control),
          px0: fmtNum(s.p_x_given_z_control),
        }),
      })
    }
    return {
      cap: order.length
        ? fill(w.cap_conditional, lang,
          { n: strata.length, order: listing(order, lang) })
        : fill(w.cap_unconditional, lang, { n: strata.length }),
      rows,
    }
  },

  // A mediation analysis is not one number: the two Pearl decompositions can
  // disagree, and the direct and indirect arms can point opposite ways, which
  // is the finding it exists to produce. The headline carries TE alone.
  'extensions.mediation_decomposition.numeric': (b, lang) => thetaMediation(b, lang),
  // One renderer, two paths: the joint block's `numeric` is a $ref to the
  // single-mediator one and is filled by the same evaluator.
  'extensions.mediation_joint_decomposition.numeric': (b, lang) => thetaMediation(b, lang),

  // The value means nothing without the two population labels: it is an
  // estimate FOR one population FROM another.
  'extensions.transport_identification.numeric': (b, lang) => {
    const rows = [{
      label: `${b.numeric.source_population ?? '?'} → ${b.numeric.target_population ?? '?'}`,
      value: fill(TRANSPORT_NUMERIC_SAYS.value, lang,
        { value: fmtNum(b.numeric.value) }),
    }]
    const others = Number(b.numeric.agreeing_sources ?? 1) - 1
    if (others > 0) {
      rows.push({
        label: fill(TRANSPORT_NUMERIC_SAYS.agreed, lang),
        value: fill(TRANSPORT_NUMERIC_SAYS.agreed_value, lang, { others }),
      })
    }
    return { cap: fill(TRANSPORT_NUMERIC_SAYS.cap, lang), rows }
  },
}

// The order a reader meets them in: what was aggregated, what was recovered,
// what was corrected, what was contrasted over time, what was decomposed, and
// last what the theta path evaluated instead of estimating. Held equal to the
// report's order by a test.
//
// Keyed by a PATH rather than by a property of `numeric_estimate`. A table
// keyed by one container's property names is a table about that container,
// and this foldout has now been caught by that three times — the formula is a
// field, the chain is under `derivation`, the details are on numeric_estimate.
// The fourth was four route blocks each carrying a `numeric` holding what the
// theta path computed, none of it reaching a reader while the data path's
// identical breakdown was stated in full.
const NUMERIC_DETAIL_ORDER = [
  'numeric_estimate.stratified_wald',
  'numeric_estimate.recovered_ate',
  'numeric_estimate.selection_recovery_numeric',
  'numeric_estimate.measurement_correction',
  'numeric_estimate.regression_calibration',
  'numeric_estimate.longitudinal_gformula',
  'numeric_estimate.longitudinal_ipw_msm',
  'numeric_estimate.four_way_decomposition',
  'numeric_estimate.four_way_ratio',
  'numeric_estimate.four_way_unavailable',
  'extensions.iv_identification.numeric',
  'extensions.mediation_decomposition.numeric',
  'extensions.mediation_joint_decomposition.numeric',
  'extensions.transport_identification.numeric',
] as const

/** What produced the number, for whichever parts are present. */
export function numericDetailRows(result: QueryResult | undefined,
  lang: Lang = DEFAULT_LANG): Section[] {
  if (!result) return []
  const out: Section[] = []
  for (const path of NUMERIC_DETAIL_ORDER) {
    const steps = path.split('.')
    let node: any = result
    for (const step of steps.slice(0, -1)) node = node?.[step] ?? {}
    if (!node?.[steps[steps.length - 1]]) continue
    const section = NUMERIC_DETAIL_RENDERERS[path](node, lang)
    if (section) out.push(section)
  }
  return out
}

/** The lines every answer shape shares: how it was computed, how precise it
 * is, and what more data cannot fix.
 *
 * The report has said all of this for a while; this surface said the method
 * and the adjustment set and stopped. What it was missing is the pair that
 * has to be read together — the precision hint says how many more subjects
 * would halve the interval, and the measurement-error line says which part
 * of that interval no number of subjects removes. Either alone points the
 * reader at the wrong purchase.
 *
 * Sample size is taken from the estimate, not the contract: on every one of
 * the 528 envelopes carrying both, the two agreed.
 */
const ESTIMATE_META_SAYS = {
  sample_size: { zh: '样本量', en: 'Sample size' },
  clustered_by: { zh: '按 {column} 分簇', en: 'clustered by {column}' },
  ar_label: {
    zh: '弱工具稳健区间（AR {pct}%）',
    en: 'Weak-instrument-robust interval (AR {pct}%)',
  },
  ar_value: { zh: '{interval} —— {kind}', en: '{interval} — {kind}' },
  overid_hansen: {
    zh: '工具联合有效性（Hansen J，异方差稳健）',
    en: 'Joint validity of the instruments (Hansen J, heteroskedasticity-robust)',
  },
  overid_sargan: {
    zh: '工具联合有效性（Sargan）',
    en: 'Joint validity of the instruments (Sargan)',
  },
  overid_rejected: {
    zh: 'p={p} —— 数据否定了这组工具：至少有一个工具的排除限制不成立，上面这个数建立在一个被自己的数据驳倒的前提上',
    en: 'p={p} — the data reject this set of instruments: at least one exclusion restriction fails, and the number above rests on a premise its own data contradicts',
  },
  overid_not_rejected: {
    zh: 'p={p} —— 数据没有否定这组工具（不通过不等于成立，只是这批数据看不出矛盾）',
    en: 'p={p} — the data do not reject this set of instruments (not rejecting is not establishing; it only means this data shows no contradiction)',
  },
  overlap: { zh: '重叠（正性）', en: 'Overlap (positivity)' },
  raw_span: {
    zh: '倾向分原始范围 [{min}, {max}]',
    en: 'raw propensity range [{min}, {max}]',
  },
  trimmed: {
    zh: '{span}，其中 {n} 个个体被截到 [{floor}, {ceiling}] 之内权重才有限 —— 截掉的越多，说明处理组与对照组越难找到可比的人，这个数越依赖模型往数据外推',
    en: '{span}, of which {n} units had to be clipped into [{floor}, {ceiling}] for their weights to stay finite — the more that are clipped, the harder it is to find comparable people across the two arms, and the more this number leans on the model extrapolating past the data',
  },
  none_trimmed: {
    zh: '{span}，没有个体需要截断',
    en: '{span}; no unit needed clipping',
  },
  robustness: { zh: '稳健性（未测混杂）', en: 'Robustness (unmeasured confounding)' },
  robustness_value: {
    zh: '一个未测混杂要同时解释掉处理与结局各 {q}% 的残差变异，才能把这个效应抹平',
    en: 'an unmeasured confounder would have to explain {q}% of the residual variation in both treatment and outcome to wipe this effect out',
  },
  robustness_alpha: {
    zh: '；解释掉 {qa}% 就足以让它不再显著（α={alpha}）',
    en: '; explaining {qa}% is already enough to make it non-significant (α={alpha})',
  },
  precision: { zh: '精度', en: 'Precision' },
  precision_value: {
    zh: '当前区间半宽 ±{half}；要减半需要 N≈{n}',
    en: 'the interval is ±{half} wide at present; halving that needs N≈{n}',
  },
  precision_wide: {
    zh: '（半宽已超过点估计的 30%，这个数还很松）',
    en: ' (the half-width is already over 30% of the point estimate, so this number is still loose)',
  },
  outcome_error: { zh: '结局测量误差', en: 'Outcome measurement error' },
  noise_share: {
    zh: '。未解释变异里 {pct}% 是测量噪声，',
    en: '. {pct}% of the unexplained variation is measurement noise, and ',
  },
  full_stop: { zh: '。', en: '. ' },
  only_measure_better: {
    zh: '这部分宽度只能靠把结局测准，加样本量消不掉',
    en: 'this part of the width can only be removed by measuring the outcome better; more sample size will not touch it',
  },
  data_contract: { zh: '数据契约', en: 'Data contract' },
} satisfies Record<string, Words>

export function estimateMeta(
  num: NumericEstimate | undefined,
  outcomeError: OutcomeError | undefined,
  ctx: EstimationContext | undefined,
  lang: Lang = DEFAULT_LANG,
): { label: string; value: string }[] {
  const w = ESTIMATE_META_SAYS
  const rows: { label: string; value: string }[] = []

  const n = num?.sample_size ?? ctx?.sample_size
  if (n != null) {
    rows.push({
      label: fill(w.sample_size, lang),
      value: `N=${n}`
        + (ctx?.cluster
          ? aside(fill(w.clustered_by, lang, { column: ctx.cluster }))
          : ''),
    })
  }

  // Before the precision row, because it qualifies the interval printed
  // above both of them. A reader who takes the bootstrap CI at face value
  // and stops has been told the effect is bounded when the honest answer
  // from this data is that it is not.
  // Robust first where both are present, and they can be: it is valid under
  // weak identification AND heteroskedasticity, so the homoskedastic one
  // beside it is the same set computed under an assumption the data may not
  // support. The stratified set answers for a different estimand and is
  // never present with either.
  const ar = num?.robust_anderson_rubin_confidence_set
    ?? num?.stratified_anderson_rubin_confidence_set
    ?? num?.anderson_rubin_confidence_set
  if (ar?.kind) {
    rows.push({
      label: fill(w.ar_label, lang, { pct: fmtNum((ar.ci_level ?? 0.95) * 100) }),
      value: fill(w.ar_value, lang, {
        interval: arInterval(ar),
        kind: gloss(AR_SET_KIND_WORDS, ar.kind, lang),
      }),
    })
  }

  // Hansen when it exists: it is the one that survives heteroskedasticity,
  // and printing the homoskedastic Sargan beside it would offer the reader a
  // choice between a test and its own weaker version.
  const oid = num?.over_identification
  const oidP = oid?.hansen_p_value ?? oid?.sargan_p_value
  if (oidP != null) {
    rows.push({
      label: fill(oid?.hansen_p_value != null ? w.overid_hansen : w.overid_sargan,
        lang),
      value: fill(oidP < 0.05 ? w.overid_rejected : w.overid_not_rejected, lang,
        { p: fmtNum(oidP) }),
    })
  }

  const ps = num?.propensity_summary
  if (ps?.raw_min != null) {
    const span = fill(w.raw_span, lang,
      { min: fmtNum(ps.raw_min), max: fmtNum(ps.raw_max) })
    rows.push({
      label: fill(w.overlap, lang),
      value: ps.n_trimmed && ps.floor != null
        ? fill(w.trimmed, lang, {
          span,
          n: ps.n_trimmed,
          floor: fmtNum(ps.floor),
          ceiling: fmtNum(1 - ps.floor),
        })
        : fill(w.none_trimmed, lang, { span }),
    })
  }

  const ovb = num?.ovb_sensitivity
  if (ovb?.robustness_value_q != null) {
    rows.push({
      label: fill(w.robustness, lang),
      value: fill(w.robustness_value, lang,
        { q: (ovb.robustness_value_q * 100).toFixed(1) })
        + (ovb.robustness_value_qa != null
          ? fill(w.robustness_alpha, lang, {
            qa: (ovb.robustness_value_qa * 100).toFixed(1),
            alpha: fmtNum(ovb.alpha ?? 0.05),
          })
          : ''),
    })
  }

  // Built from the three numbers rather than from the sentence beside them,
  // which is assembled in English for a single Python reader.
  const pb = num?.precision_budget
  if (pb?.current_ci_half_width != null && pb?.n_to_halve_ci != null) {
    const wide = pb.relative_width != null && pb.relative_width > 0.3
    rows.push({
      label: fill(w.precision, lang),
      value: fill(w.precision_value, lang, {
        half: fmtNum(pb.current_ci_half_width),
        n: pb.n_to_halve_ci,
      }) + (wide ? fill(w.precision_wide, lang) : ''),
    })
  }

  // Next to the precision hint on purpose, and only there.
  if (outcomeError?.se_inflation != null) {
    const share = outcomeError.noise_share
    const said = fill(
      OUTCOME_ERROR_DESIGN_WORDS[String(outcomeError.design_kind ?? '')]
        ?? OUTCOME_ERROR_DESIGN_UNSTATED,
      lang, { factor: fmtNum(outcomeError.se_inflation) })
    rows.push({
      label: fill(w.outcome_error, lang),
      value: said
        + (share != null
          ? fill(w.noise_share, lang, { pct: Math.round(share * 100) })
          : fill(w.full_stop, lang))
        + fill(w.only_measure_better, lang),
    })
  }

  for (const warning of ctx?.data_contract_warnings ?? []) {
    rows.push({ label: fill(w.data_contract, lang), value: warning })
  }

  return rows
}

// The shapes an estimate can answer in — the vocabulary themis/answers.py
// declares, bound here to this surface's rows. This surface used to read only
// `point`, so a curve, a decomposition, a joint contrast and a bounded cell
// each rendered as a single em-dash while their numbers sat in the same block.
// A test pins that every declared shape is read here.
const ANSWER_ROWS_SAYS = {
  dose_response: { zh: '剂量-反应曲线', en: 'Dose-response curve' },
  decomposition: { zh: '效应分解', en: 'Effect decomposition' },
  te: { zh: '总效应 TE', en: 'Total effect TE' },
  nde: { zh: '直接效应 NDE', en: 'Direct effect NDE' },
  nie: { zh: '间接效应 NIE', en: 'Indirect effect NIE' },
  proportion_mediated: { zh: '中介占比', en: 'Proportion mediated' },
  joint: { zh: '联合干预', en: 'Joint intervention' },
  contrast: { zh: '对比 {treated} vs {control}', en: '{treated} vs {control}' },
  interaction: { zh: '{order} 阶交互', en: 'Order-{order} interaction' },
  // The interaction can be withheld while the contrast stands, and a row
  // that simply vanished left this surface saying nothing about it while
  // the report said why. What goes in the value is the kernel's species,
  // glossed — the two of them ask the reader for different things.
  interaction_missing: { zh: '{order} 阶交互给不出', en: 'Order-{order} interaction unavailable' },
  cell_cap: { zh: '反事实格(区间)', en: 'Counterfactual cell (interval)' },
  cell_from: { zh: '这一格怎么来的', en: 'Where this cell comes from' },
  cell_adjustment: {
    zh: '干预风险经哪个后门调整集识别',
    en: 'The back-door set the interventional risk is identified through',
  },
  cell_if_monotone: { zh: '什么能收紧它', en: 'What would narrow it' },
  cell_if_monotone_value: {
    zh: '若可假设单调性（X 从不阻止 Y），这一格会被收紧——在干预风险已知时收紧成一个点',
    en: 'if monotonicity can be assumed (X never prevents Y) this cell narrows — to a point, where the interventional risk is known',
  },
  instrument: { zh: '工具变量 `{name}`', en: 'instrument `{name}`' },
  risk_used: {
    zh: '用到的干预风险 P(结局 | do(处理))',
    en: 'The interventional risk it leans on, P(outcome | do(treatment))',
  },
  monotonicity_refuted: {
    zh: '所声明的单调性被这份数据推翻的比例',
    en: 'How often this data refutes the declared monotonicity',
  },
  monotonicity_refuted_value: {
    zh: '{pct}% 的重抽样在该假设下无解 —— 比例越高，上面那个区间越不该照单全收',
    en: '{pct}% of the resamples have no feasible solution under it — the higher the share, the less the interval above should be taken at face value',
  },
} satisfies Record<string, Words>

export function answerRows(num: NumericEstimate,
  lang: Lang = DEFAULT_LANG): Section | null {
  const w = ANSWER_ROWS_SAYS
  // Above the early return, because `point` is the headline for ONE estimand
  // and this one holds three: what the figure would lead with is PN printed
  // without its name, under a question line that asks for all three by name.
  // Same renderer as the block — the data path and the theta path put the
  // same three quantities in the same shape, in two different containers.
  const poc = num.probabilities_of_causation
  if (poc) {
    return ANSWER_RENDERERS.causation(
      poc as Blk, { ext: {}, lang, ciLevel: num.ci_level })
  }

  if (num.point != null) return null // the point figure already leads with it

  const curve = num.dose_response_curve
  if (curve?.length) {
    return {
      cap: fill(w.dose_response, lang),
      rows: curve.slice(0, 6).map((p) => ({
        label: `x=${fmtNum(p.x)}`,
        value: band({ point: p.effect, ci_lower: p.ci_lower, ci_upper: p.ci_upper }),
      })),
    }
  }

  const d = num.decomposition
  if (d) {
    return {
      cap: fill(w.decomposition, lang),
      rows: ([
        [w.te, d.te], [w.nde, d.nde], [w.nie, d.nie],
        [w.proportion_mediated, d.proportion_mediated],
      ] as const)
        .filter(([, b]) => band(b))
        .map(([said, b]) => ({ label: fill(said, lang), value: band(b) })),
    }
  }

  const joint = num.joint_effect
  if (joint) {
    const rows = [{
      label: fill(w.contrast, lang, {
        treated: corner(joint.treated), control: corner(joint.control),
      }).trim(),
      value: band(joint),
    }]
    if (num.interaction?.point != null) {
      rows.push({
        label: fill(w.interaction, lang, { order: num.interaction.order ?? '' }),
        value: band(num.interaction),
      })
    }
    const missing = num.interaction_unavailable
    if (missing) {
      const words = INTERACTION_UNAVAILABLE_WORDS[String(missing.kind ?? '')]
      rows.push({
        label: fill(w.interaction_missing, lang, { order: missing.order ?? '' }),
        value: words
          ? fill(words, lang, {
            // Language-neutral, like every other cell list on this surface:
            // a separator is not a sentence, and picking one per language
            // here would be a second place to decide it.
            cells: (missing.unsupported_cells ?? []).map(corner).join(' · '),
            cap: missing.cap ?? '',
          })
          : gloss(INTERACTION_UNAVAILABLE_WORDS, missing.kind, lang),
      })
    }
    return { cap: fill(w.joint, lang), rows }
  }

  const cell = num.counterfactual_cell
  const shownCell = cell ? pointOrSet(cell, num.ci_level, lang) : null
  if (cell && shownCell) {
    // WHICH cell. Four booleans say it, and the heading said "反事实格",
    // which names none of them: an interval on an unnamed quantity is not
    // something a reader can check against the question they asked.
    //
    // The head is the point where a declared monotonicity, the consistency
    // identity, or an absent factual outcome collapsed the set, and the set
    // itself where none of them did — and the band beside it is around
    // whichever of the two, which is why it names its own width (#419). All
    // of it used to be a bare `[lower, upper]`: the resampling this surface's
    // own route description promises ("with a bootstrap sampling interval")
    // reached the report and stopped here.
    const rows = [
      {
        label: counterfactualCellQuestion(cell, lang),
        value: shownCell.head + (shownCell.band ? aside(shownCell.band) : ''),
      },
    ]
    // WHICH solver produced it. Two of them can fill the same two numbers —
    // the consistency identity on a point-identified risk, and the
    // response-function program on an instrument when no risk is
    // point-identified — and they rest on different assumptions. An interval
    // that does not say which reads as one method that always applies.
    const licence = RISK_PROVENANCE_WORDS[String(cell.interventional_risk_provenance ?? '')]
    if (licence) {
      const how = say(licence, lang, absent('no_word_for_this_token', lang,
        { token: String(cell.interventional_risk_provenance) }))
      rows.push({
        label: fill(w.cell_from, lang),
        value: how + (cell.instrument
          ? aside(fill(w.instrument, lang, { name: String(cell.instrument) }))
          : ''),
      })
    }
    // WHICH columns the back-door route standardised over. Empty on every
    // other route, and a route that names one is a route whose answer rests
    // on that set being sufficient — which the reader is the only one who
    // can dispute.
    if (cell.adjustment?.length) {
      rows.push({
        label: fill(w.cell_adjustment, lang),
        value: varset(cell.adjustment),
      })
    }
    // The one interventional arm the cell leans on, when it leans on one.
    if (cell.p_y_do_x_cf != null) {
      rows.push({
        label: fill(w.risk_used, lang), value: fmtNum(cell.p_y_do_x_cf),
      })
    }
    // What would narrow it, when nothing narrowed it. An interval with no
    // way out reads as the end of the road; this one has a way out, and it
    // is an assumption the reader is the one entitled to make.
    if (!cell.monotonicity) {
      rows.push({
        label: fill(w.cell_if_monotone, lang),
        value: fill(w.cell_if_monotone_value, lang),
      })
    }
    // Not a diagnostic. A share of the resamples with no feasible solution
    // under the declared monotonicity is a finite-sample measure of how close
    // that assumption is to being refuted by this data, and monotonicity is
    // the one usually called untestable. Only the detachable explainer said it.
    const refuted = cell.bootstrap_draws_infeasible ?? 0
    const used = cell.bootstrap_draws_used ?? 0
    if (refuted && used + refuted) {
      rows.push({
        label: fill(w.monotonicity_refuted, lang),
        value: fill(w.monotonicity_refuted_value, lang,
          { pct: fmtNum((100 * refuted) / (used + refuted)) }),
      })
    }
    return { cap: fill(w.cell_cap, lang), rows }
  }

  return null
}

/** Which counterfactual an interval is an interval ON. */
const CELL_QUESTION_SAYS = {
  took_it: { zh: '实际接受了处理', en: 'did take the treatment' },
  did_not: { zh: '实际没接受处理', en: 'did not take the treatment' },
  and_outcome: { zh: '、且结局发生了', en: ' and had the outcome' },
  and_no_outcome: { zh: '、且结局没发生', en: ' and did not have the outcome' },
  had_taken_it: { zh: '若当初接受了处理', en: 'had they taken the treatment' },
  had_not: { zh: '若当初没接受处理', en: 'had they not taken the treatment' },
  outcome_would: { zh: '结局会发生', en: 'the outcome would have happened' },
  outcome_would_not: { zh: '结局不会发生', en: 'the outcome would not have happened' },
  question: {
    zh: '在{was}的那些个体里，{instead}，{then}的概率',
    en: 'Among the units that {was}: the probability that, {instead}, {then}',
  },
} satisfies Record<string, Words>

function counterfactualCellQuestion(cell: Record<string, any>,
  lang: Lang = DEFAULT_LANG): string {
  const w = CELL_QUESTION_SAYS
  let was = fill(cell.observed_x ? w.took_it : w.did_not, lang)
  if (cell.factual_y != null) {
    was += fill(cell.factual_y ? w.and_outcome : w.and_no_outcome, lang)
  }
  return fill(w.question, lang, {
    was,
    instead: fill(cell.counterfactual_x ? w.had_taken_it : w.had_not, lang),
    then: fill(cell.target_y ? w.outcome_would : w.outcome_would_not, lang),
  })
}

// ---- framing gap filling (补缺口) ----

// The seven fields a reader can name to say what a variable means. `label` and
// `placeholder` are what a reader is handed, so they are `Words` like every
// other text here; the value that goes into the program when a field is left
// blank is not among them, and used to be. A `def` sat beside these, holding
// the sentence the server wrote into the program for a blank field — a second
// copy of `themis/web/app.py`'s table with nothing keeping the two equal, kept
// only so this surface could recognise those sentences again afterwards. The
// program now says which fields were left to the default (`defaulted`), so
// there is no value here to copy and nothing to recognise by its wording.
export const FRAMING_FIELDS: { key: string; label: Words; placeholder: Words }[] = [
  { key: 'time_window', label: { zh: '时间窗', en: 'Time window' }, placeholder: { zh: '如「≥6 个月」', en: 'e.g. "≥6 months"' } },
  { key: 'measurement', label: { zh: '测量方式', en: 'How it is measured' }, placeholder: { zh: '如「自报告」/「仪器」', en: 'e.g. "self-reported" / "instrument"' } },
  { key: 'threshold', label: { zh: '阈值/切点', en: 'Threshold / cutpoint' }, placeholder: { zh: '如「BMI≥30」', en: 'e.g. "BMI≥30"' } },
  { key: 'observability', label: { zh: '可观测性', en: 'Observability' }, placeholder: { zh: 'observable / self-reported / latent', en: 'observable / self-reported / latent' } },
  { key: 'direction', label: { zh: '方向', en: 'Direction' }, placeholder: { zh: 'up / down / mixed', en: 'up / down / mixed' } },
  { key: 'baseline', label: { zh: '基线', en: 'Baseline' }, placeholder: { zh: '如「当前状态」', en: 'e.g. "the current state"' } },
  { key: 'state_vs_event', label: { zh: '状态/事件', en: 'State or event' }, placeholder: { zh: 'state / event', en: 'state / event' } },
]

const _FIELD_NAMES = new Set(FRAMING_FIELDS.map((f) => f.key))
const FRAMING_GAP_KINDS = new Set(['ambiguous_variable_definition', 'ill_defined_intervention_versions'])

// Which slot of a framing gap's statements names the thing it is about.
// It used to be found by scanning the rendered paragraph for the first
// backticked identifier that was not a framing field name — a reader of
// prose, and one that would have found nothing the first time the reader
// was English. The name is a slot the statement fills; these are the two
// it is filled under.
const FRAMING_SUBJECT_SLOTS = ['variable', 'intervention']

function pickVar(gap: { describes?: GapSentence[] }): string | null {
  for (const entry of gap.describes ?? []) {
    for (const slot of FRAMING_SUBJECT_SLOTS) {
      const named = entry.said?.[slot]
      if (named && !_FIELD_NAMES.has(named)) return named
    }
  }
  return null
}

/** Variables that carry a framing (操作化未定义) gap — one per variable. */
export function framingVariables(
  gaps: { kind: string; describes?: GapSentence[] }[],
): string[] {
  const out: string[] = []
  const seen = new Set<string>()
  for (const g of gaps) {
    if (!FRAMING_GAP_KINDS.has(g.kind)) continue
    const v = pickVar(g)
    if (v && !seen.has(v)) {
      seen.add(v)
      out.push(v)
    }
  }
  return out
}

/**
 * Variables whose operationalization was left to the standard one.
 * Clearing a framing gap by leaving the fields blank is convenient but means
 * the answer rests on definitions the user never named — this lets the result
 * surface that honestly instead of hiding it in the merged JSON.
 *
 * The program says so itself, in `defaulted`. It used to be worked out here
 * instead, by comparing each field against the sentence the server writes for
 * a blank one — which needed a copy of that sentence on this side, could only
 * ever match one language, and could not be done at all for the three fields
 * whose default is a value a user might genuinely have picked. Those three
 * are in the list now for the same reason the other four are: because the
 * program was asked rather than read.
 */
export function framingDefaultsInProgram(
  program: Record<string, unknown> | undefined,
): { predicate: string; fields: string[] }[] {
  const known = new Set(FRAMING_FIELDS.map((f) => f.key))
  const stmts = (program?.statements as Record<string, unknown>[] | undefined) ?? []
  const out: { predicate: string; fields: string[] }[] = []
  for (const s of stmts) {
    if (s.kind !== 'variable' || typeof s.predicate !== 'string') continue
    const named = Array.isArray(s.defaulted) ? (s.defaulted as unknown[]) : []
    const fields = named.filter((f): f is string => typeof f === 'string' && known.has(f))
    if (fields.length) out.push({ predicate: s.predicate, fields })
  }
  return out
}

/** What to call one framing field, in the reader's language. */
export function framingFieldLabel(key: string, lang: Lang): string {
  const field = FRAMING_FIELDS.find((f) => f.key === key)
  return field ? fill(field.label, lang) : key
}
