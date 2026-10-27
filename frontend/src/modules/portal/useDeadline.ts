/** 门户截止时间工具：距截止 N 天 / 已截止（≤3 天为紧急） */
import { useI18n } from 'vue-i18n'

export function useDeadline() {
  const { t } = useI18n()

  function daysLeft(deadline?: string): number | null {
    if (!deadline) return null
    const ms = new Date(deadline.replace(' ', 'T')).getTime() - Date.now()
    return Math.ceil(ms / 86400000)
  }

  function deadlineText(deadline?: string): string {
    const d = daysLeft(deadline)
    if (d === null) return ''
    if (d < 0) return t('portal.portal.deadlinePassed')
    return t('portal.portal.daysLeft', { n: d })
  }

  /** 已截止或 ≤3 天视为紧急（标红） */
  function isUrgent(deadline?: string): boolean {
    const d = daysLeft(deadline)
    return d !== null && d <= 3
  }

  return { daysLeft, deadlineText, isUrgent }
}
