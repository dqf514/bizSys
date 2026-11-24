import { describe, expect, it } from 'vitest'
import { evalFormula, formulaRefs, hoursOf, sumOfColumn } from './formLogic'

describe('formulaRefs', () => {
  it('collects field refs and dedups', () => {
    expect(formulaRefs('a + b * a')).toEqual(['a', 'b'])
  })

  it('strips wecom type prefixes', () => {
    expect(formulaRefs('Money-a + Number-b')).toEqual(['a', 'b'])
  })

  it('aggregate call args are not counted as refs', () => {
    expect(formulaRefs('SUM(t1.c1) + HOURS(d1)')).toEqual([])
    expect(formulaRefs('SUM(t1.c1) + x')).toEqual(['x'])
  })

  it('empty expression returns empty array', () => {
    expect(formulaRefs('')).toEqual([])
    expect(formulaRefs(undefined)).toEqual([])
  })
})

describe('sumOfColumn', () => {
  it('sums a detail table column', () => {
    const data = { t1: [{ c1: 10 }, { c1: 5 }, { c1: '3' }] }
    expect(sumOfColumn(data, 't1', 'c1')).toBe(18)
  })

  it('skips empty and boolean cells', () => {
    const data = { t1: [{ c1: 10 }, { c1: null }, { c1: '' }, { c1: true }] }
    expect(sumOfColumn(data, 't1', 'c1')).toBe(10)
  })

  it('missing table returns null', () => {
    expect(sumOfColumn({ t1: [] }, 't2', 'c1')).toBeNull()
  })

  it('empty table returns 0', () => {
    expect(sumOfColumn({ t1: [] }, 't1', 'c1')).toBe(0)
  })
})

describe('hoursOf', () => {
  it('plain number', () => {
    expect(hoursOf(8)).toBe(8)
  })

  it('object with hours field', () => {
    expect(hoursOf({ hours: 4.5 })).toBe(4.5)
  })

  it('start/end difference in hours', () => {
    expect(hoursOf({ start: '2026-11-24 09:00', end: '2026-11-24 17:30' })).toBe(8.5)
  })

  it('start/end array', () => {
    expect(hoursOf(['2026-11-24 09:00', '2026-11-24 12:00'])).toBe(3)
  })

  it('end before start returns null', () => {
    expect(hoursOf({ start: '2026-11-24 17:00', end: '2026-11-24 09:00' })).toBeNull()
  })

  it('empty value returns null', () => {
    expect(hoursOf(null)).toBeNull()
    expect(hoursOf(undefined)).toBeNull()
    expect(hoursOf('')).toBeNull()
  })
})

describe('evalFormula', () => {
  it('arithmetic with field refs', () => {
    expect(evalFormula('a + b * 2', { a: 1, b: 3 })).toBe(7)
    expect(evalFormula('(a + b) * 2', { a: 1, b: 3 })).toBe(8)
  })

  it('wecom prefixed notation', () => {
    expect(evalFormula('Money-qty * Money-price', { qty: 3, price: 9.5 })).toBe(28.5)
  })

  it('unknown field makes the whole expression unevaluable', () => {
    expect(evalFormula('a + missing', { a: 1 })).toBeNull()
  })

  it('non numeric field value counts as 0', () => {
    expect(evalFormula('a + b', { a: 'x', b: 2 })).toBe(2)
  })

  it('SUM aggregates a detail table column', () => {
    const data = { t1: [{ c1: 10 }, { c1: 5 }], x: 1 }
    expect(evalFormula('SUM(t1.c1)', data)).toBe(15)
    expect(evalFormula('SUM(t1.c1) + x', data)).toBe(16)
  })

  it('HOURS reads duration', () => {
    const data = { d1: { start: '2026-11-24 09:00', end: '2026-11-24 17:00' } }
    expect(evalFormula('HOURS(d1)', data)).toBe(8)
    expect(evalFormula('HOURS(d1) * 2', data)).toBe(16)
  })

  it('aggregates mixed with plain fields', () => {
    const data = { t1: [{ c1: 10 }], rate: 0.5, d1: 4 }
    expect(evalFormula('SUM(t1.c1) * rate + HOURS(d1)', data)).toBe(9)
  })

  it('division by zero returns null', () => {
    expect(evalFormula('a / b', { a: 1, b: 0 })).toBeNull()
  })

  it('empty expression returns null', () => {
    expect(evalFormula('', {})).toBeNull()
    expect(evalFormula(undefined, {})).toBeNull()
  })
})
