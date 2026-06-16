import type { AnswerTier } from '../types'

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
