import type { AnswerTier, Band, NumericEstimate } from '../types'

export const TIER_META: Record<AnswerTier, { label: string; gloss: string }> = {
  point: { label: '点估计', gloss: '可以算出一个具体数字——补齐数据即可' },
  interval: { label: '区间', gloss: '给不了确切数字,但能给一个诚实的范围' },
  none: { label: '无', gloss: '光凭图和数据给不了数,需要额外假设' },
}

// One entry per status, label required and blurb optional — two tables keyed
// by the same vocabulary are two chances to hold half of it, and this one
// held a status the kernel does not emit (`unidentifiable`) while missing one
// it does (`outside_language`, six results in one suite run, which reached
// the reader as its own identifier).
const STATUS_META: Record<string, { label: string; blurb?: string }> = {
  structurally_solved: {
    label: '已识别(结构上)',
    blurb: '因果结构本身成立;是否有数值取决于是否提供数据。',
  },
  numerically_solved: {
    label: '已算出数值',
    blurb: '提供了数据,内核完成识别并算出了数值。',
  },
  needs_investigation: {
    label: '可识别,但缺数据',
    blurb: '结构上可识别(给出识别公式),但缺数据——内核拒绝编数字,并列出还缺什么。',
  },
  outside_language: {
    label: '超出可表达范围',
    blurb: '这个问题超出 Themis 能表达 / 能识别的范围——不是数据不够,是问题的形式本身还没有对应的表示。',
  },
  counterfactual_solved: {
    label: '反事实已解',
    blurb: '反事实的那一格解出来了。',
  },
  counterfactual_bounded: {
    label: '反事实(区间)',
    blurb: '反事实只能给区间,要点估计需补单调性等假设。',
  },
  needs_assumption: {
    label: '需要额外假设',
    blurb: '当前信息下无法回答,需要你显式补一个假设(认识论选择,内核不替你拍板)。',
  },
}
export function statusLabel(status: string): string {
  return STATUS_META[status]?.label ?? status
}
export function statusBlurb(status: string): string | undefined {
  return STATUS_META[status]?.blurb
}

// How much a MISSING INPUT blocks an answer.
const SEVERITY_LABEL: Record<string, string> = {
  blocking: '阻断',
  important: '重要',
  informational: '提示',
}
export function severityLabel(sev: string): string {
  return SEVERITY_LABEL[sev] ?? sev
}

// How the conclusion dies if an ASSUMPTION is false. A different question
// from the one above, a disjoint set of values, and the same field name —
// which is how the table above came to be read as the whole of `severity`
// and the assumption ledger's three values reached 688 readers as
// `invalidating` / `distorting` / `confidence_only`.
const ASSUMPTION_SEVERITY_ZH: Record<string, string> = {
  invalidating: '作废级',
  distorting: '扭曲级',
  confidence_only: '仅影响置信',
}
export function assumptionSeverityLabel(sev: string): string {
  return ASSUMPTION_SEVERITY_ZH[sev] ?? sev
}

// Which part of the answer stops being true if an assumption is false —
// the third field of the same ledger line, and a partition of the answer
// rather than a list of topics. A sixth value named `assumption` used to
// sit here saying nothing; it was identification, since without it the
// quantity is bounded rather than point-identified.
const LEDGER_LAYER_ZH: Record<string, string> = {
  identification: '识别',
  functional_form: '函数形式',
  structural_edge: '图上的边',
  parameter: '参数取值',
  confidence: '区间',
}
export function ledgerLayerLabel(layer: string): string {
  return LEDGER_LAYER_ZH[layer] ?? layer
}

// What the reader can do about this line: who can overrule it, and what they
// get back if they do. Five of the six name someone other than the method,
// and those are the lines a reader can actually overrule — which is the whole
// reason this field is worth the room it takes.
const LEDGER_PROVENANCE_ZH: Record<string, string> = {
  inherent: '方法本身要求',
  caller_asserted: '你在问题里断言的',
  default: '估计器默认选择',
  llm_proposal: '上游 LLM 提议',
  discovery: '因果发现算法学出',
  llm_prior: 'LLM 常识 prior',
}
export function ledgerProvenanceLabel(prov: string): string {
  return LEDGER_PROVENANCE_ZH[prov] ?? prov
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

const REFUSAL_KIND_ZH: Record<string, Refusal> = {
  graph: {
    lead: '没有给出数值',
    head: '这是关于因果图的结论',
    tail: '再多同样的数据也不会改变它;要改变的是图或问题本身。',
  },
  data: {
    lead: '没有给出数值',
    head: '这批数据支撑不住',
    tail: '结构上是可识别的,缺的是数据本身能提供的支持。',
  },
  unbuilt: {
    lead: '没有给出数值',
    head: 'Themis 还没有建这个情形',
    tail: '问题成立、也已被识别,这是工具的边界,不是问题或数据的毛病。',
  },
  request: {
    lead: '没有给出数值',
    head: '需要你改一处输入',
    tail: '改掉之后重跑即可。',
  },
  backend: {
    lead: '没有算出数值',
    head: '数值例程没有返回结果',
    tail: '这没有对问题或数据设计做出任何判定。',
  },
}
export function refusalKind(kind: unknown): Refusal | null {
  return REFUSAL_KIND_ZH[String(kind)] ?? null
}

// gap kind -> short plain-language title. The rigorous kind stays as a
// quiet mono annotation; this is the translation the reader leads with.
const GAP_TITLE: Record<string, string> = {
  unidentifiable_no_admissible_set: '找不到能消除混杂的调整集',
  missing_distribution: '缺一个概率分布',
  missing_population_distribution: '缺目标人群的分布',
  missing_assumption: '缺一条识别假设',
  missing_unit_observation: '缺这个个体自己的观测值',
  missing_structural_input: '缺一项结构输入(方程系数 / 声明)',
  missing_iv_candidate: '缺一个有效的工具变量',
  missing_mediator_data: '缺中介变量的数据',
  transport_target_distribution_unknown: '目标人群分布未知',
  transport_source_conditional_unknown: '源人群的分层分布未知',
  ambiguous_variable_definition: '变量定义不够清楚',
  dose_response_data_required: '剂量-反应曲线需要数据',
  unverified_proposal_edge_on_query_path: '路径上有一条未经验证的边',
  iv_identification_assumption_required: '工具变量识别需要假设',
  mediation_identification_assumption_required: '中介分解需要假设',
  transport_identification_assumption_required: '跨人群迁移需要假设',
  llm_declared_ambiguity: '上游标记了不确定性',
  answer_is_bounds_not_point_estimate: '答案是区间,不是点',
  low_confidence_input_data: '输入数据可信度偏低',
  unattempted_layer_due_to_dispatch_conflict: '还有一层没跑(两种分析同时被要求)',
  weak_iv_instrument: '工具变量偏弱',
  iv_estimand_fallback_to_linear: '按分层求不了,退回到整体的线性估计',
  overidentification_rejected: '过度识别检验否决了这组工具',
  propensity_overlap_violation: '两组人重叠不够(倾向得分越界)',
  outcome_model_quasi_separation: '结果模型近乎完全分离',
  front_door_identification_assumption_required: '前门识别需要假设',
  counterfactual_identification_assumption_required: '反事实推理需要假设',
  graph_learned_from_data: '因果图是从数据学出来的',
  collider_conditioning_opens_backdoor: '条件在对撞点上会打开后门',
  unmeasured_confounder_risk: '可能残留未测量的混杂',
  measurement_error_concern: '测量误差风险',
  selection_on_collider_opens_path: '样本选择打开了偏倚路径',
  ill_defined_intervention_versions: '干预没定义清楚',
  graph_theta_independence_mismatch: '图与提供的分布不一致',
  dichotomized_continuous_measure: '连续变量被二分了',
  declared_type_data_mismatch: '声明的变量类型与数据不符',
}
export function gapTitle(kind: string): string {
  return GAP_TITLE[kind] ?? kind.replace(/_/g, ' ')
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
type Reading = { answersIt: boolean; holds: { label: string; gloss: string }; failsTo: { label: string; gloss: string } }

const QUESTION_READINGS: Record<string, Reading> = {
  cause: { answersIt: true, holds: { label: '是', gloss: '存在因果影响' }, failsTo: { label: '否', gloss: '不存在因果影响' } },
  assoc: { answersIt: true, holds: { label: '有关联', gloss: '两者相关联' }, failsTo: { label: '无关联', gloss: '两者不相关联' } },
  identify: { answersIt: true, holds: { label: '可识别', gloss: '可从观测数据非参数识别' }, failsTo: { label: '不可识别', gloss: '无法从这张图非参数识别' } },
  effect: { answersIt: false, holds: { label: '可识别', gloss: '该效应可识别 —— 数值还没算出来' }, failsTo: { label: '不可识别', gloss: '该效应无法从这张图识别' } },
  probability: { answersIt: false, holds: { label: '可识别', gloss: '该概率可识别 —— 数值还没算出来' }, failsTo: { label: '不可识别', gloss: '该概率无法从这张图识别' } },
  counterfactual: { answersIt: false, holds: { label: '可识别', gloss: '该反事实格可识别（点或界）' }, failsTo: { label: '不可识别', gloss: '该反事实格无法识别' } },
  causation: { answersIt: false, holds: { label: '可识别', gloss: '归因概率可识别' }, failsTo: { label: '不可识别', gloss: '归因概率无法识别' } },
  scm_counterfactual: { answersIt: false, holds: { label: '可解出', gloss: '该个体的反事实值可解出' }, failsTo: { label: '解不出', gloss: '该个体的反事实值解不出' } },
  counterfactual_conjunction: { answersIt: false, holds: { label: '可识别', gloss: '联合反事实可识别' }, failsTo: { label: '不可识别', gloss: 'ID* 返回 hedge —— 不可识别' } },
  proximal_effect: { answersIt: false, holds: { label: '可识别', gloss: '近端识别条件成立，效应可识别' }, failsTo: { label: '不成立', gloss: '近端识别条件不成立' } },
}

// `cap` is what the chip is labelled: 结论 only where the boolean IS the
// answer. Calling an identifiability precondition a 结论 is the same
// substitution in one word.
export function structuralReadout(
  queryKind: string,
  value: boolean,
): { cap: string; label: string; gloss: string; tone: 'point' | 'none' } | null {
  const reading = QUESTION_READINGS[queryKind]
  if (!reading) return null
  const side = value ? reading.holds : reading.failsTo
  return {
    cap: reading.answersIt ? '结论' : '识别',
    label: side.label,
    gloss: side.gloss,
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

// The routes an answer can arrive by — the family themis/blocks.py declares,
// in ITS declaration order, which is the order both surfaces state them in.
// A test parses this array and holds it equal to blocks.rendered_in(ROUTE),
// and holds every name in it to having a renderer below: the foldout named
// itself "怎么算出来的" while saying only the formula and the paths, and the
// ten blocks that answer that question exactly reached no reader at all.
const ROUTE_ORDER = [
  'identification',
  'iv_identification',
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
// never calls an estimator, so there is no shape for answerRows to find.
const ANSWER_ORDER = ['causation', 'scm_counterfactual'] as const

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

const PATTERN_ZH: Record<string, string> = {
  backdoor: '后门调整',
  front_door: '前门调整',
  c_factor: 'ID 算法的一般解 (c-factor)',
  instrumental_variable: '工具变量',
}

// One arm of a decomposition — identifiable, and on what.
const arm = (info: Blk | undefined, label: string) => ({
  label,
  value: info?.identifiable
    ? `可识别${info.adjustment?.length ? ` · 调整 ${varset(info.adjustment)}` : ''}`
    : `不可识别${info?.failed_condition ? ` · ${info.failed_condition}` : ''}`,
})

// A renderer takes the whole extensions map so it can decline to repeat what
// a block above it already said, and may return null when that leaves it with
// nothing — a heading over no rows is worse than no heading.
const ROUTE_RENDERERS: Record<string, (b: Blk, ext: Record<string, any>) => Section | null> = {
  identification: (b) => {
    const rows = [{ label: '模式', value: PATTERN_ZH[b.pattern] ?? String(b.pattern ?? '?') }]
    if (b.pattern === 'backdoor') {
      rows.push({ label: '调整集', value: b.adjustment_set?.length ? varset(b.adjustment_set) : '无需调整——没有开放的后门路径' })
    } else if (b.pattern === 'front_door') {
      rows.push({ label: '中介集', value: varset(b.mediator_set) })
    } else if (b.pattern === 'instrumental_variable') {
      rows.push({ label: '工具', value: String(b.instrument ?? '?') })
    }
    if (b.conditioned_on?.length) rows.push({ label: '问题条件于', value: varset(b.conditioned_on) })
    if (b.required_assumption) rows.push({ label: '点识别另需', value: String(b.required_assumption) })
    return { cap: '识别模式', rows }
  },
  // strategy / instrument / conditioning / required_assumption are copied
  // into `identification` by the producer, which calls that copy the human
  // surface — so state them here only when no pattern line will.
  iv_identification: (b, ext) => {
    const rows: { label: string; value: string }[] = []
    if (ext.identification?.pattern !== 'instrumental_variable') {
      rows.push({ label: '工具', value: String(b.instrument ?? '?') })
      if (b.conditioning?.length) rows.push({ label: '条件于', value: varset(b.conditioning) })
    }
    if (typeof b.alternatives_count === 'number' && b.alternatives_count > 1) {
      rows.push({ label: '候选工具', value: `共 ${b.alternatives_count} 个，取其一` })
    }
    if (b.late_caveat) rows.push({ label: '注意', value: String(b.late_caveat) })
    return rows.length ? { cap: '工具变量', rows } : null
  },
  transport_identification: (b) => {
    const rows = [{ label: '从 → 到', value: `${b.source_population ?? '源总体'} → ${b.target_population ?? '目标总体'}` }]
    const s = (b.s_nodes ?? []).map((n: any) => n?.affects?.predicate ?? '?')
    if (s.length) rows.push({ label: '两地分布不同', value: varset(s) })
    if (b.adjustment_set?.length) rows.push({ label: '重加权于', value: preds(b.adjustment_set) })
    return { cap: '跨总体迁移', rows }
  },
  joint_identification: (b) => {
    const rows = [{ label: '同时干预', value: varset(b.treatments) }]
    rows.push(b.pattern === 'joint_general_id'
      ? { label: '识别', value: '无可用调整集，由集合版 ID 算法识别' }
      : { label: '联合后门调整集', value: b.adjustment_set?.length ? varset(b.adjustment_set) : '无需调整' })
    if (b.interaction) rows.push({ label: '交互', value: '差值尺度——逐个单独干预再相加拿不到' })
    return { cap: '联合干预', rows }
  },
  longitudinal_identification: (b) => {
    const rows = [{ label: '处理序列', value: (b.treatments ?? []).join(' → ') || '（空）' }]
    rows.push({ label: '结局', value: String(b.outcome ?? '?') })
    if (b.confounders_by_time?.length) {
      rows.push({ label: '各时点已测混杂', value: b.confounders_by_time.map(varset).join('、') })
    }
    rows.push({
      label: '序贯可交换性',
      value: b.identified
        ? '成立——每个时点的后门路径都被此前的历史挡住'
        : '不成立——g-formula 会给出有偏的数',
    })
    return { cap: '时变处理 (g-formula)', rows }
  },
  mediation_decomposition: (b) => ({
    cap: '中介分解',
    rows: b.mediator_valid === false
      ? [{ label: '中介', value: `${b.mediator ?? '?'} 不在任何 X→…→M→…→Y 有向路径上` }]
      : [{ label: '中介', value: String(b.mediator ?? '?') },
         arm(b.nde_nie, 'NDE / NIE'), arm(b.cde, 'CDE')],
  }),
  mediation_joint_decomposition: (b) => ({
    cap: '中介集分解',
    rows: b.mediator_set_valid === false
      ? [{ label: '中介集', value: `${varset(b.mediators)} 不是有效中介集` }]
      : [{ label: '中介集', value: `${varset(b.mediators)}（整体当一个块，不需内部排序）` },
         arm(b.nde_nie, 'NDE / NIE'), arm(b.cde, 'CDE')],
  }),
  proximal_estimand: (b) => {
    const rows = [{ label: '未测混杂', value: `${b.latent ?? '?'}${b.latent_cardinality != null ? ` (取 ${b.latent_cardinality} 个值)` : ''}` }]
    rows.push({ label: '代理', value: `处理侧 ${b.treatment_proxy ?? '?'} · 结局侧 ${b.outcome_proxy ?? '?'}` })
    if (b.data_conditions) rows.push({ label: '数据须满足', value: String(b.data_conditions) })
    return { cap: '近端识别', rows }
  },
  selection_recovery: (b) => {
    const rows = [{ label: '样本被限制于', value: varset(b.selection_nodes) }]
    rows.push({
      label: '无偏效应',
      value: b.recoverable
        ? `可从这份有偏样本恢复${b.adjustment_set?.length ? ` · 选择后门调整 ${varset(b.adjustment_set)}` : ''}`
        : `无法只从这份样本恢复${b.failure_reason ? ` · ${b.failure_reason}` : ''}`,
    })
    if (b.external_data_needed?.length) rows.push({ label: '还需外部数据', value: b.external_data_needed.join('、') })
    return { cap: '选择偏倚', rows }
  },
  missing_data_recovery: (b) => {
    const rows = [{ label: '机制', value: String(b.mechanism ?? '?') }]
    if (b.partially_observed?.length) rows.push({ label: '部分观测', value: varset(b.partially_observed) })
    const est = b.estimand ?? {}
    rows.push({
      label: '整条估计量',
      value: est.recoverable
        ? `可从缺失数据恢复${est.requires?.length ? ` · 需 ${est.requires.join('、')}` : ''}`
        : `不可恢复${est.failure_reason ?? b.failure_reason ? ` · ${est.failure_reason ?? b.failure_reason}` : ''}`,
    })
    return { cap: '缺失数据', rows }
  },
}

// --- the answer, when a block rather than an estimate carries it -------------

const POC_LABELS = [
  ['pn', '必要性 PN(归因)'],
  ['ps', '充分性 PS'],
  ['pns', '必要且充分 PNS'],
] as const

// Where P(Y|do X) came from. The keys are extensions.causation's own enum in
// query_result.schema.json and a test holds them equal to it, because the
// alternative to a translation here is printing the identifier — and whether
// the two risks were derived from the graph or measured in an experiment is
// not a detail this surface can drop: nothing else on it says so.
const RISK_PROVENANCE_ZH: Record<string, string> = {
  derived_identification: '干预风险由识别层从图上导出',
  exogenous: '原因到结果没有后门路径,干预风险即条件概率',
  backdoor_adjustment: '干预风险经后门标准化(g-formula)识别',
  user_experimental: '干预风险来自调用方提供的随机实验数据',
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
  status: STATUS_META,
  answer_tier: TIER_META,
  query_kind: QUESTION_READINGS,
  gap_kind: GAP_TITLE,
  gap_severity: SEVERITY_LABEL,
  assumption_severity: ASSUMPTION_SEVERITY_ZH,
  assumption_layer: LEDGER_LAYER_ZH,
  assumption_provenance: LEDGER_PROVENANCE_ZH,
  identification_pattern: PATTERN_ZH,
  interventional_risk_provenance: RISK_PROVENANCE_ZH,
  refusal_kind: REFUSAL_KIND_ZH,
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
  'RENDERED_BLOCKS',
  'VOCABULARIES',
] as const

type BlockRenderer = (b: Blk, ext: Record<string, any>, ciLevel?: number) => Section | null

const ANSWER_RENDERERS: Record<string, BlockRenderer> = {
  // Three quantities, each said by name. The point/interval split is per
  // quantity rather than per block: monotonicity does not make the block
  // appear, it collapses what is inside each of the three.
  causation: (b, _ext, ciLevel) => {
    const rows: { label: string; value: string }[] = []
    for (const [key, label] of POC_LABELS) {
      const q = b[key] as Blk | undefined
      if (!q) continue
      const bounded = q.lower != null && q.upper != null
      const head = q.point != null ? fmtNum(q.point)
        : bounded ? `[${fmtNum(q.lower)}, ${fmtNum(q.upper)}]` : null
      if (head === null) continue
      // One pair of CI keys, two meanings, settled by the same thing that
      // settles the head: a point's sampling interval when there is a point,
      // the outer band on the identified set when there is not.
      const aside: string[] = []
      if (q.ci_lower != null && q.ci_upper != null) {
        const pct = `${Math.round((ciLevel ?? 0.95) * 100)}% `
        aside.push(`${pct}${q.point != null ? 'CI' : '外带'} [${fmtNum(q.ci_lower)}, ${fmtNum(q.ci_upper)}]`)
      }
      // Tian-Pearl bounds assume no monotonicity, so when both are present
      // this is exactly what the assumption bought.
      if (q.point != null && bounded) {
        aside.push(`无单调性假设时只能给到 [${fmtNum(q.lower)}, ${fmtNum(q.upper)}]`)
      }
      rows.push({ label, value: head + (aside.length ? ` · ${aside.join(' · ')}` : '') })
    }
    if (!rows.length) return null
    if (b.p_y_do_x1 != null && b.p_y_do_x0 != null) {
      const how = RISK_PROVENANCE_ZH[b.interventional_risk_provenance]
      const adj = Array.isArray(b.adjustment) && b.adjustment.length
        ? ` · 调整集 {${b.adjustment.join(', ')}}` : ''
      rows.push({
        label: '干预风险',
        value: `P(Y|do X)=${fmtNum(b.p_y_do_x1)} · P(Y|do ¬X)=${fmtNum(b.p_y_do_x0)}`
          + (how ? ` · ${how}${adj}` : ''),
      })
    }
    // Whether monotonicity was assumed decides which of two questions the
    // three numbers answer, so it belongs in the caption, not a footnote.
    return {
      cap: b.monotonic ? '因果概率 · 单调性下点识别' : '因果概率 · 未假设单调性,只能给界',
      rows,
    }
  },
  // The value is also in numeric_result and the figure above prints it. What
  // only this block has is the abduction: the exogenous noise recovered from
  // what this unit actually did is what makes the number a counterfactual for
  // THEM rather than a prediction for an average unit.
  scm_counterfactual: (b) => {
    if (b.target_value == null) return null
    const rows = [{
      label: String(b.target ?? '反事实值'),
      value: `${fmtNum(b.target_value)}(该个体自身的外生扰动下)`,
    }]
    const noise = (b.abducted_noise ?? {}) as Record<string, number>
    const names = Object.keys(noise).sort()
    if (names.length) {
      rows.push({
        label: '反推出的个体扰动',
        value: names.map((n) => `U_${n}=${fmtNum(noise[n])}`).join(' · '),
      })
    }
    const cf = (b.counterfactual_values ?? {}) as Record<string, number>
    const others = Object.keys(cf).filter((k) => k !== b.target).sort()
    if (others.length) {
      rows.push({
        label: '同一反事实世界下的其他变量',
        value: others.map((k) => `${k}=${fmtNum(cf[k])}`).join(' · '),
      })
    }
    return { cap: '线性 SCM 反事实', rows }
  },
}

// One family's blocks, in registry order, each rendered once. Empty when the
// envelope states none — a heading over nothing is a promise it did not make.
function blockRows(
  order: readonly string[],
  renderers: Record<string, BlockRenderer>,
  extensions: Record<string, unknown> | undefined,
): Section[] {
  if (!extensions) return []
  const out: Section[] = []
  for (const name of order) {
    const block = extensions[name] as Blk | undefined
    if (!block || typeof block !== 'object') continue
    const section = renderers[name](block, extensions as Record<string, any>)
    if (section) out.push(section)
  }
  return out
}

/** How the answer was arrived at. */
export function routeRows(extensions: Record<string, unknown> | undefined): Section[] {
  return blockRows(ROUTE_ORDER, ROUTE_RENDERERS, extensions)
}

/** The answer itself, on the paths that carry it as a block. */
export function answerBlockRows(extensions: Record<string, unknown> | undefined): Section[] {
  return blockRows(ANSWER_ORDER, ANSWER_RENDERERS, extensions)
}

// The shapes an estimate can answer in — the vocabulary themis/answers.py
// declares, bound here to this surface's rows. This surface used to read only
// `point`, so a curve, a decomposition, a joint contrast and a bounded cell
// each rendered as a single em-dash while their numbers sat in the same block.
// A test pins that every declared shape is read here.
export function answerRows(num: NumericEstimate): Section | null {
  // Above the early return, because `point` is the headline for ONE estimand
  // and this one holds three: what the figure would lead with is PN printed
  // without its name, under a question line that asks for all three by name.
  // Same renderer as the block — the data path and the theta path put the
  // same three quantities in the same shape, in two different containers.
  const poc = num.probabilities_of_causation
  if (poc) return ANSWER_RENDERERS.causation(poc as Blk, {}, num.ci_level)

  if (num.point != null) return null // the point figure already leads with it

  const curve = num.dose_response_curve
  if (curve?.length) {
    return {
      cap: '剂量-反应曲线',
      rows: curve.slice(0, 6).map((p) => ({
        label: `x=${fmtNum(p.x)}`,
        value: band({ point: p.effect, ci_lower: p.ci_lower, ci_upper: p.ci_upper }),
      })),
    }
  }

  const d = num.decomposition
  if (d) {
    return {
      cap: '效应分解',
      rows: ([
        ['总效应 TE', d.te], ['直接效应 NDE', d.nde], ['间接效应 NIE', d.nie],
        ['中介占比', d.proportion_mediated],
      ] as const)
        .filter(([, b]) => band(b))
        .map(([label, b]) => ({ label, value: band(b) })),
    }
  }

  const joint = num.joint_effect
  if (joint) {
    const rows = [{
      label: `对比 ${corner(joint.treated)} vs ${corner(joint.control)}`.trim(),
      value: band(joint),
    }]
    if (num.interaction?.point != null) {
      rows.push({ label: `${num.interaction.order ?? ''} 阶交互`, value: band(num.interaction) })
    }
    return { cap: '联合干预', rows }
  }

  const cell = num.counterfactual_cell
  if (cell && cell.lower != null && cell.upper != null) {
    return {
      cap: '反事实格(区间)',
      rows: [{ label: '区间', value: `[${fmtNum(cell.lower)}, ${fmtNum(cell.upper)}]` }],
    }
  }

  return null
}

// ---- framing gap filling (补缺口) ----

export const FRAMING_FIELDS: { key: string; label: string; placeholder: string; def: string }[] = [
  { key: 'time_window', label: '时间窗', placeholder: '如「≥6 个月」', def: '未指定（默认：研究随访期）' },
  { key: 'measurement', label: '测量方式', placeholder: '如「自报告」/「仪器」', def: '未指定（默认：标准测量）' },
  { key: 'threshold', label: '阈值/切点', placeholder: '如「BMI≥30」', def: '未指定（默认：任意可测变化）' },
  { key: 'observability', label: '可观测性', placeholder: 'observable / self-reported / latent', def: 'observable' },
  { key: 'direction', label: '方向', placeholder: 'up / down / mixed', def: 'up' },
  { key: 'baseline', label: '基线', placeholder: '如「当前状态」', def: '未指定（默认：当前状态）' },
  { key: 'state_vs_event', label: '状态/事件', placeholder: 'state / event', def: 'state' },
]

const _FIELD_NAMES = new Set(FRAMING_FIELDS.map((f) => f.key))
const FRAMING_GAP_KINDS = new Set(['ambiguous_variable_definition', 'ill_defined_intervention_versions'])

function pickVar(desc: string): string | null {
  const re = /[`「]([A-Za-z_]\w*)[`」]/g
  let m: RegExpExecArray | null
  while ((m = re.exec(desc))) {
    if (!_FIELD_NAMES.has(m[1])) return m[1]
  }
  return null
}

/** Variables that carry a framing (操作化未定义) gap — one per variable. */
export function framingVariables(gaps: { kind: string; description: string }[]): string[] {
  const out: string[] = []
  const seen = new Set<string>()
  for (const g of gaps) {
    if (!FRAMING_GAP_KINDS.has(g.kind)) continue
    const v = pickVar(g.description)
    if (v && !seen.has(v)) {
      seen.add(v)
      out.push(v)
    }
  }
  return out
}

// The text fields whose default value ("未指定（默认：…）") a user would never
// type — so a variable carrying one was operationalised by the blank-fill
// default, not confirmed by the user. (Categorical defaults like up/observable
// equal real choices, so they can't be told apart and aren't flagged.)
const _MARKER_DEFAULTS = FRAMING_FIELDS.filter((f) => f.def.includes('未指定'))

/**
 * Variables whose operationalization is an unconfirmed blank-fill default.
 * Clearing a framing gap by leaving the fields blank is convenient but means
 * the answer rests on default definitions the user never confirmed — this lets
 * the result surface that honestly instead of hiding it in the merged JSON.
 */
export function framingDefaultsInProgram(
  program: Record<string, unknown> | undefined,
): { predicate: string; fields: string[] }[] {
  const stmts = (program?.statements as Record<string, unknown>[] | undefined) ?? []
  const out: { predicate: string; fields: string[] }[] = []
  for (const s of stmts) {
    if (s.kind !== 'variable' || typeof s.predicate !== 'string') continue
    const fields = _MARKER_DEFAULTS.filter((f) => s[f.key] === f.def).map((f) => f.label)
    if (fields.length) out.push({ predicate: s.predicate, fields })
  }
  return out
}
