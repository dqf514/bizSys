/** 门户截止时间工具：距截止 N 天 / 已截止（≤3 天为紧急） */
import { useI18n } from 'vue-i18n'

/** 紧急阈值：剩余 ≤3 天即标红 */
export const URGENT_DAYS = 3

/**
 * 解析截止时间为毫秒时间戳；无法解析返回 null。
 *
 * 后端返回的格式是 `YYYY-MM-DD HH:mm:ss`（无时区），按**本地时间**解释；
 * 纯日期（`YYYY-MM-DD`）补成当地 00:00，避免 `Date.parse` 把纯日期当成 UTC。
 */
export function parseDeadlineMs(deadline?: string | null): number | null {
  if (!deadline) return null
  const raw = String(deadline).trim()
  if (!raw) return null
  const normalized = /^\d{4}-\d{2}-\d{2}$/.test(raw)
    ? `${raw}T00:00:00`
    : raw.replace(' ', 'T')
  const ts = Date.parse(normalized)
  return Number.isNaN(ts) ? null : ts
}

/** 距截止的天数（向上取整）；无有效截止时间返回 null */
export function daysBetween(deadline?: string | null, now: number = Date.now()): number | null {
  const ts = parseDeadlineMs(deadline)
  if (ts === null) return null
  return Math.ceil((ts - now) / 86400000)
}

/** 剩余天数是否紧急（≤3 天） */
export function isUrgentDays(days: number | null): boolean {
  return days !== null && days <= URGENT_DAYS
}

export function useDeadline() {
  const { t } = useI18n()

  function daysLeft(deadline?: string): number | null {
    return daysBetween(deadline)
  }

  function deadlineText(deadline?: string): string {
    const d = daysLeft(deadline)
    if (d === null) return ''
    if (d < 0) return t('portal.portal.deadlinePassed')
    return t('portal.portal.daysLeft', { n: d })
  }

  /** 已截止或 ≤3 天视为紧急（标红） */
  function isUrgent(deadline?: string): boolean {
    return isUrgentDays(daysLeft(deadline))
  }

  return { daysLeft, deadlineText, isUrgent }
}
