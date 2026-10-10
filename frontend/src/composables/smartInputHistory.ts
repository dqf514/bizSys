/**
 * localStorage-backed input history for SmartInput.
 * One bucket per field key (e.g. "finance.payment.bank"), most-recent-first,
 * deduped and capped at SMART_INPUT_MAX entries.
 */

const PREFIX = 'smartInput:'
export const SMART_INPUT_MAX = 20

export function getSmartHistory(field: string): string[] {
  try {
    const raw = localStorage.getItem(PREFIX + field)
    const list: unknown = raw ? JSON.parse(raw) : []
    return Array.isArray(list) ? list.filter((x): x is string => typeof x === 'string') : []
  } catch {
    return []
  }
}

/** call after a form submits successfully to remember the value */
export function recordSmartHistory(field: string, value: string) {
  const v = value.trim()
  if (!field || !v) return
  const list = [v, ...getSmartHistory(field).filter((x) => x !== v)].slice(0, SMART_INPUT_MAX)
  try {
    localStorage.setItem(PREFIX + field, JSON.stringify(list))
  } catch {
    /* storage full or unavailable — history is best-effort */
  }
}
