/**
 * OA 表单运行时求值：条件逻辑（显隐/必填/只读）、级联选项过滤。
 * 语义与后端 app/modules/oa/service.py 的 eval_condition / _allowed_options 保持一致。
 */
import type { OaConditionGroup, OaConditionRule, OaField } from '@/api/types'

export type OaFormData = Record<string, unknown>

export function isEmptyValue(v: unknown): boolean {
  return v === null || v === undefined || v === '' || (Array.isArray(v) && v.length === 0)
}

function toNum(v: unknown): number | null {
  if (typeof v === 'boolean') return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

function evalRule(rule: OaConditionRule, data: OaFormData): boolean {
  const actual = data[rule.field]
  if (rule.op === 'empty') return isEmptyValue(actual)
  if (rule.op === 'not_empty') return !isEmptyValue(actual)
  if (isEmptyValue(actual)) return false
  if (rule.op === 'gt' || rule.op === 'gte' || rule.op === 'lt' || rule.op === 'lte') {
    const a = toNum(actual)
    const b = toNum(rule.value)
    if (a === null || b === null) return false
    if (rule.op === 'gt') return a > b
    if (rule.op === 'gte') return a >= b
    if (rule.op === 'lt') return a < b
    return a <= b
  }
  if (Array.isArray(actual)) {
    // checkbox 多选：eq/contains=包含任一值，ne=不含该值
    const values = actual.map(String)
    if (rule.op === 'ne') return !values.includes(rule.value)
    return values.includes(rule.value)
  }
  const s = String(actual)
  if (rule.op === 'eq') return s === rule.value
  if (rule.op === 'ne') return s !== rule.value
  if (rule.op === 'contains') return s.includes(rule.value)
  return false
}

/** 条件组求值：无规则视为恒真（未配置条件）。 */
export function evalConditionGroup(group: OaConditionGroup | null | undefined, data: OaFormData): boolean {
  if (!group || !group.rules?.length) return true
  const results = group.rules.map((r) => evalRule(r, data))
  return group.logic === 'or' ? results.some(Boolean) : results.every(Boolean)
}

/** showWhen 不满足 → 隐藏（提交时忽略该字段）。 */
export function isFieldVisible(field: OaField, data: OaFormData): boolean {
  return evalConditionGroup(field.showWhen, data)
}

export function isFieldRequired(field: OaField, data: OaFormData): boolean {
  if (field.required) return true
  if (field.requiredWhen?.rules?.length) return evalConditionGroup(field.requiredWhen, data)
  return false
}

/** 条件只读：仅前端禁用编辑。 */
export function isFieldReadonly(field: OaField, data: OaFormData): boolean {
  if (!field.readonlyWhen?.rules?.length) return false
  return evalConditionGroup(field.readonlyWhen, data)
}

/**
 * 当前可选选项：dict 源用传入的字典选项；cascade 按父值过滤（父值不在 map 回退全选项）。
 */
export function fieldOptions(field: OaField, data: OaFormData, dictOptions?: string[]): string[] {
  let base: string[]
  if (field.optionsSource === 'dict') base = dictOptions ?? []
  else base = field.options ?? []
  const cascade = field.cascade
  if (cascade?.parent && cascade.map) {
    const parentVal = data[cascade.parent]
    const key = parentVal === null || parentVal === undefined ? '' : String(parentVal)
    const allowed = cascade.map[key]
    if (Array.isArray(allowed)) return allowed
  }
  return base
}
