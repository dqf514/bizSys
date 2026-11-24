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

function evalBetween(actual: unknown, expected: unknown): boolean {
  let lo: unknown
  let hi: unknown
  if (Array.isArray(expected) && expected.length === 2) {
    ;[lo, hi] = expected
  } else if (expected && typeof expected === 'object') {
    const e = expected as Record<string, unknown>
    lo = e.min ?? e.lo
    hi = e.max ?? e.hi
  } else {
    return false
  }
  const a = toNum(actual)
  if (a === null) return false
  if (lo !== undefined && lo !== null) {
    const b = toNum(lo)
    if (b === null || a < b) return false
  }
  if (hi !== undefined && hi !== null) {
    const b = toNum(hi)
    if (b === null || a > b) return false
  }
  return true
}

/**
 * 单条条件求值：与后端 app/modules/oa/service.py::_eval_rule 同语义。
 * 多选控件（实际值为数组）按「包含任一」判定 eq/ne/contains。
 */
function evalRule(rule: OaConditionRule, data: OaFormData): boolean {
  if (rule.rules?.length) return evalRuleList(rule.rules, rule.logic ?? 'and', data)
  const actual = data[rule.field ?? '']
  const expected = rule.value
  if (rule.op === 'empty') return isEmptyValue(actual)
  if (rule.op === 'not_empty') return !isEmptyValue(actual)
  if (rule.op === 'between') return evalBetween(actual, expected)
  if (isEmptyValue(actual)) return false
  if (rule.op === 'gt' || rule.op === 'gte' || rule.op === 'lt' || rule.op === 'lte') {
    const a = toNum(actual)
    const b = toNum(expected)
    if (a === null || b === null) return false
    if (rule.op === 'gt') return a > b
    if (rule.op === 'gte') return a >= b
    if (rule.op === 'lt') return a < b
    return a <= b
  }
  if (Array.isArray(actual)) {
    // checkbox 多选：eq/contains=包含任一值，ne=不含该值
    const values = actual.map(String)
    if (rule.op === 'ne') return !values.includes(String(expected))
    if (rule.op === 'in') {
      const options = Array.isArray(expected) ? expected.map(String) : [String(expected)]
      return values.some((v) => options.includes(v))
    }
    return values.includes(String(expected))
  }
  if (rule.op === 'in') {
    const options = Array.isArray(expected) ? expected.map(String) : [String(expected)]
    return options.includes(String(actual))
  }
  const s = String(actual)
  if (rule.op === 'eq') return s === String(expected)
  if (rule.op === 'ne') return s !== String(expected)
  if (rule.op === 'contains') return s.includes(String(expected))
  return false
}

function evalRuleList(rules: OaConditionRule[], logic: 'and' | 'or', data: OaFormData): boolean {
  if (!rules.length) return true
  const results = rules.map((r) => evalRule(r, data))
  return logic === 'or' ? results.some(Boolean) : results.every(Boolean)
}

/** 条件组求值：无规则视为恒真（未配置条件）。 */
export function evalConditionGroup(group: OaConditionGroup | null | undefined, data: OaFormData): boolean {
  if (!group || !group.rules?.length) return true
  return evalRuleList(group.rules, group.logic ?? 'and', data)
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

/* ---------- 公式表达式（type=formula） ---------- */

/** 企业微信公式写法形如「Money-a + Money-b」：控件类型前缀 + 控件标识 */
const FORMULA_PREFIX_RE = /\b(?:Money|Number|money|number)-/g
const FORMULA_IDENT_RE = /[A-Za-z_][A-Za-z0-9_]*/g

/** 公式引用的控件标识（去重，保持出现顺序） */
export function formulaRefs(expr: string | undefined): string[] {
  if (!expr) return []
  const src = expr.replace(FORMULA_PREFIX_RE, '')
  const refs: string[] = []
  for (const m of src.matchAll(FORMULA_IDENT_RE)) {
    const name = m[0]
    if (!refs.includes(name)) refs.push(name)
  }
  return refs
}

type Token = { kind: 'num'; value: number } | { kind: 'ident'; value: string } | { kind: 'op'; value: string }

function tokenize(src: string): Token[] | null {
  const tokens: Token[] = []
  let i = 0
  while (i < src.length) {
    const ch = src[i]!
    if (/\s/.test(ch)) {
      i += 1
      continue
    }
    if (/[0-9]/.test(ch)) {
      const m = /^[0-9]*\.?[0-9]+/.exec(src.slice(i))
      if (!m) return null
      tokens.push({ kind: 'num', value: Number(m[0]) })
      i += m[0].length
      continue
    }
    if (/[A-Za-z_]/.test(ch)) {
      const m = /^[A-Za-z_][A-Za-z0-9_]*/.exec(src.slice(i))
      if (!m) return null
      tokens.push({ kind: 'ident', value: m[0] })
      i += m[0].length
      continue
    }
    if ('+-*/()'.includes(ch)) {
      tokens.push({ kind: 'op', value: ch })
      i += 1
      continue
    }
    return null
  }
  return tokens
}

/**
 * 公式求值：只允许 + - * /、括号、数字与本表字段引用。
 * 语义与后端 app/modules/oa/service.py::_eval_formula 一致：
 * 引用字段不存在 → 整体不可求值（null）；字段值非数字 → 按 0 计。
 */
export function evalFormula(expr: string | undefined, data: OaFormData): number | null {
  if (!expr || !expr.trim()) return null
  const src = expr.replace(FORMULA_PREFIX_RE, '').replace(/[×÷]/g, (c) => (c === '×' ? '*' : '/'))
  const tokens = tokenize(src)
  if (!tokens || !tokens.length) return null
  let pos = 0

  const peek = () => tokens[pos]
  const eat = (value: string) => {
    const tk = tokens[pos]
    if (tk && tk.kind === 'op' && tk.value === value) {
      pos += 1
      return true
    }
    return false
  }

  function parseExpr(): number | null {
    let left = parseTerm()
    if (left === null) return null
    for (;;) {
      if (eat('+')) {
        const right = parseTerm()
        if (right === null) return null
        left += right
      } else if (eat('-')) {
        const right = parseTerm()
        if (right === null) return null
        left -= right
      } else break
    }
    return left
  }

  function parseTerm(): number | null {
    let left = parseFactor()
    if (left === null) return null
    for (;;) {
      if (eat('*')) {
        const right = parseFactor()
        if (right === null) return null
        left *= right
      } else if (eat('/')) {
        const right = parseFactor()
        if (right === null) return null
        if (right === 0) return null
        left /= right
      } else break
    }
    return left
  }

  function parseFactor(): number | null {
    if (eat('-')) {
      const v = parseFactor()
      return v === null ? null : -v
    }
    if (eat('+')) return parseFactor()
    return parsePrimary()
  }

  function parsePrimary(): number | null {
    const tk = peek()
    if (!tk) return null
    if (tk.kind === 'num') {
      pos += 1
      return tk.value
    }
    if (tk.kind === 'ident') {
      pos += 1
      if (!(tk.value in data)) return null
      const raw = data[tk.value]
      if (typeof raw === 'boolean') return 0
      const n = Number(raw)
      return Number.isFinite(n) ? n : 0
    }
    if (tk.kind === 'op' && tk.value === '(') {
      pos += 1
      const v = parseExpr()
      if (v === null) return null
      if (!eat(')')) return null
      return v
    }
    return null
  }

  const result = parseExpr()
  if (result === null) return null
  if (pos !== tokens.length) return null
  return Number.isFinite(result) ? result : null
}
