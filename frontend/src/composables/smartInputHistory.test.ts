import { beforeEach, describe, expect, it } from 'vitest'
import { getSmartHistory, recordSmartHistory, SMART_INPUT_MAX } from './smartInputHistory'

describe('smartInputHistory', () => {
  beforeEach(() => localStorage.clear())

  it('returns empty list for an unknown field', () => {
    expect(getSmartHistory('nope')).toEqual([])
  })

  it('records most recent first and dedupes', () => {
    recordSmartHistory('bank', 'ICBC')
    recordSmartHistory('bank', 'CCB')
    recordSmartHistory('bank', 'ICBC')
    expect(getSmartHistory('bank')).toEqual(['ICBC', 'CCB'])
  })

  it('trims values and skips blank ones', () => {
    recordSmartHistory('bank', '   ')
    recordSmartHistory('bank', '  ABC  ')
    expect(getSmartHistory('bank')).toEqual(['ABC'])
  })

  it('caps history at SMART_INPUT_MAX entries', () => {
    for (let i = 0; i < SMART_INPUT_MAX + 5; i++) recordSmartHistory('bank', `b${i}`)
    const list = getSmartHistory('bank')
    expect(list).toHaveLength(SMART_INPUT_MAX)
    expect(list[0]).toBe(`b${SMART_INPUT_MAX + 4}`)
  })

  it('tolerates corrupted storage', () => {
    localStorage.setItem('smartInput:bank', '{bad json')
    expect(getSmartHistory('bank')).toEqual([])
  })

  it('keeps buckets isolated per field key', () => {
    recordSmartHistory('bank', 'ICBC')
    recordSmartHistory('payer', 'Acme')
    expect(getSmartHistory('bank')).toEqual(['ICBC'])
    expect(getSmartHistory('payer')).toEqual(['Acme'])
  })
})
