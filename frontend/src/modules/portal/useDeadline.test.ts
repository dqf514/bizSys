import { describe, expect, it } from 'vitest'
import { daysBetween, isUrgentDays, parseDeadlineMs, URGENT_DAYS } from './useDeadline'

const DAY = 86400000

describe('portal deadline pure helpers', () => {
  it('parseDeadlineMs returns null for empty / invalid input', () => {
    expect(parseDeadlineMs(undefined)).toBeNull()
    expect(parseDeadlineMs(null)).toBeNull()
    expect(parseDeadlineMs('')).toBeNull()
    expect(parseDeadlineMs('   ')).toBeNull()
    expect(parseDeadlineMs('not-a-date')).toBeNull()
  })

  it('parseDeadlineMs treats a pure date as local midnight (not UTC)', () => {
    const ts = parseDeadlineMs('2026-11-22')
    expect(ts).not.toBeNull()
    const d = new Date(ts as number)
    expect(d.getFullYear()).toBe(2026)
    expect(d.getMonth()).toBe(10)
    expect(d.getDate()).toBe(22)
    expect(d.getHours()).toBe(0)
    expect(d.getMinutes()).toBe(0)
  })

  it('parseDeadlineMs accepts the backend "YYYY-MM-DD HH:mm:ss" format', () => {
    const ts = parseDeadlineMs('2026-11-22 08:30:00')
    expect(ts).not.toBeNull()
    const d = new Date(ts as number)
    expect(d.getHours()).toBe(8)
    expect(d.getMinutes()).toBe(30)
  })

  it('daysBetween counts whole days up (ceil)', () => {
    const now = parseDeadlineMs('2026-11-22 00:00:00') as number
    expect(daysBetween('2026-11-22 00:00:00', now)).toBe(0)
    expect(daysBetween('2026-11-23 00:00:00', now)).toBe(1)
    // 剩余不足一天也按 1 天算（向上取整）
    expect(daysBetween('2026-11-22 12:00:00', now)).toBe(1)
    // 已过期为负数
    expect(daysBetween('2026-11-21 00:00:00', now)).toBe(-1)
  })

  it('daysBetween returns null when there is no parsable deadline', () => {
    expect(daysBetween(undefined, Date.now())).toBeNull()
    expect(daysBetween('bad', Date.now())).toBeNull()
  })

  it('isUrgentDays flags ≤3 days (including overdue and empty-day boundary)', () => {
    expect(URGENT_DAYS).toBe(3)
    expect(isUrgentDays(0)).toBe(true)
    expect(isUrgentDays(3)).toBe(true)
    expect(isUrgentDays(4)).toBe(false)
    expect(isUrgentDays(-1)).toBe(true)
    expect(isUrgentDays(null)).toBe(false)
  })

  it('a deadline exactly 3 days out is urgent, 4 days is not', () => {
    const now = parseDeadlineMs('2026-11-22 00:00:00') as number
    expect(isUrgentDays(daysBetween('2026-11-25 00:00:00', now))).toBe(true)
    expect(isUrgentDays(daysBetween('2026-11-26 00:00:00', now))).toBe(false)
    expect(DAY).toBe(86400000)
  })
})
