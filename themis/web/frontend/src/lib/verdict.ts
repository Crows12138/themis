import type { AnswerTier, Band, NumericEstimate } from '../types'

export const TIER_META: Record<AnswerTier, { label: string; gloss: string }> = {
  point: { label: '点估计', gloss: '可以算出一个具体数字——补齐数据即可' },
  interval: { label: '区间', gloss: '给不了确切数字,但能给一个诚实的范围' },
  none: { label: '无', gloss: '光凭图和数据给不了数,需要额外假设' },
}

// status -> human one-liner
const STATUS_LABEL: Record<string, string> = {
  numerically_solved: '已算出数值',
  structurally_solved: '已识别(结构上)',
  needs_investigation: '可识别,但缺数据',
  needs_assumption: '需要额外假设',
  unidentifiable: '不可识别',
  counterfactual_solved: '反事实已解',
  counterfactual_bounded: '反事实(区间)',
}
export function statusLabel(status: string): string {
  return STATUS_LABEL[status] ?? status
}

const STATUS_BLURB: Record<string, string> = {
  needs_investigation: '结构上可识别(给出识别公式),但缺数据——内核拒绝编数字,并列出还缺什么。',
  structurally_solved: '因果结构本身成立;是否有数值取决于是否提供数据。',
  needs_assumption: '当前信息下无法回答,需要你显式补一个假设(认识论选择,内核不替你拍板)。',
  numerically_solved: '提供了数据,内核完成识别并算出了数值。',
  counterfactual_bounded: '反事实只能给区间,要点估计需补单调性等假设。',
}
export function statusBlurb(status: string): string | undefined {
  return STATUS_BLURB[status]
}

const SEVERITY_LABEL: Record<string, string> = {
  blocking: '阻断',
  important: '重要',
  informational: '提示',
}
export function severityLabel(sev: string): string {
  return SEVERITY_LABEL[sev] ?? sev
}

// gap kind -> short plain-language title. The rigorous kind stays as a
// quiet mono annotation; this is the translation the reader leads with.
const GAP_TITLE: Record<string, string> = {
  unidentifiable_no_admissible_set: '找不到能消除混杂的调整集',
  missing_distribution: '缺一个概率分布',
  missing_population_distribution: '缺目标人群的分布',
  missing_assumption: '缺一条识别假设',
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

// Structural-result verdict for cause / assoc / identify queries — the
// yes/no answer the kernel actually returns (value + supporting_paths).
export function structuralReadout(
  queryKind: string,
  value: boolean,
): { label: string; gloss: string; tone: 'point' | 'none' } {
  if (queryKind === 'cause') return value ? { label: '是', gloss: '存在因果关系', tone: 'point' } : { label: '否', gloss: '没有因果关系', tone: 'none' }
  if (queryKind === 'assoc') return value ? { label: '有关联', gloss: '两者存在统计关联', tone: 'point' } : { label: '无关联', gloss: '两者没有统计关联', tone: 'none' }
  if (queryKind === 'identify') return value ? { label: '可识别', gloss: '图 + 数据足以识别' , tone: 'point' } : { label: '不可识别', gloss: '需要更强假设', tone: 'none' }
  return value ? { label: '成立', gloss: '', tone: 'point' } : { label: '不成立', gloss: '', tone: 'none' }
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
// A test parses this array and holds it equal to blocks.declared_as(ROUTE),
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

export interface Route {
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
const ROUTE_RENDERERS: Record<string, (b: Blk, ext: Record<string, any>) => Route | null> = {
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

// How the answer was arrived at, in registry order. Empty when the envelope
// states no route — a heading over nothing is a promise it did not make.
export function routeRows(extensions: Record<string, unknown> | undefined): Route[] {
  if (!extensions) return []
  const out: Route[] = []
  for (const name of ROUTE_ORDER) {
    const block = extensions[name] as Blk | undefined
    if (!block || typeof block !== 'object') continue
    const route = ROUTE_RENDERERS[name](block, extensions as Record<string, any>)
    if (route) out.push(route)
  }
  return out
}

// The shapes an estimate can answer in — the vocabulary themis/answers.py
// declares, bound here to this surface's rows. This surface used to read only
// `point`, so a curve, a decomposition, a joint contrast and a bounded cell
// each rendered as a single em-dash while their numbers sat in the same block.
// A test pins that every declared shape is read here.
export function answerRows(
  num: NumericEstimate,
): { cap: string; rows: { label: string; value: string }[] } | null {
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

  const poc = num.probabilities_of_causation
  if (poc) {
    return {
      cap: '因果概率(区间)',
      rows: ([['必要性 PN', poc.pn], ['充分性 PS', poc.ps], ['必要且充分 PNS', poc.pns]] as const)
        .filter(([, q]) => q && q.lower != null && q.upper != null)
        .map(([label, q]) => ({ label, value: `[${fmtNum(q!.lower)}, ${fmtNum(q!.upper)}]` })),
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
