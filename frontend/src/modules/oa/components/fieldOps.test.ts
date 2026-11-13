import { describe, expect, it } from 'vitest'
import type { OaField } from '@/api/types'
import {
  duplicateField,
  insertFieldAt,
  moveFieldTo,
  nextFieldKey,
  removeField,
  swapField,
} from './fieldOps'

function makeFields(): OaField[] {
  return [
    { key: 'text_1', label: 'A', type: 'text', required: false },
    { key: 'select_2', label: 'B', type: 'select', required: true, options: ['x', 'y'] },
    { key: 'date_3', label: 'C', type: 'date', required: false },
  ]
}

/** v-model 语义：props 数组归父级所有，结构操作不得原地修改 */
describe('fieldOps (FormDesigner v-model:fields semantics)', () => {
  it('nextFieldKey avoids collisions', () => {
    const fields = makeFields()
    expect(nextFieldKey(fields, 'text')).toBe('text_4')
    fields.push({ key: 'text_4', label: '', type: 'text', required: false })
    expect(nextFieldKey(fields, 'text')).toBe('text_5')
  })

  it('insertFieldAt appends by default and inserts at index without mutating input', () => {
    const fields = Object.freeze(makeFields()) as OaField[]
    const field: OaField = { key: 'money_4', label: 'D', type: 'money', required: false }

    const appended = insertFieldAt(fields, field)
    expect(appended).toHaveLength(4)
    expect(appended[3]).toBe(field)
    expect(appended).not.toBe(fields)
    expect(fields).toHaveLength(3)

    const inserted = insertFieldAt(fields, field, 1)
    expect(inserted.map((f) => f.key)).toEqual(['text_1', 'money_4', 'select_2', 'date_3'])
    expect(fields).toHaveLength(3)
  })

  it('swapField moves a field up/down, returns a new array, null on edges', () => {
    const fields = Object.freeze(makeFields()) as OaField[]

    const up = swapField(fields, 'select_2', -1)
    expect(up?.map((f) => f.key)).toEqual(['select_2', 'text_1', 'date_3'])
    expect(up).not.toBe(fields)
    expect(fields.map((f) => f.key)).toEqual(['text_1', 'select_2', 'date_3'])

    const down = swapField(fields, 'select_2', 1)
    expect(down?.map((f) => f.key)).toEqual(['text_1', 'date_3', 'select_2'])

    expect(swapField(fields, 'text_1', -1)).toBeNull()
    expect(swapField(fields, 'date_3', 1)).toBeNull()
    expect(swapField(fields, 'missing', 1)).toBeNull()
  })

  it('removeField filters by key without mutating input, null when absent', () => {
    const fields = Object.freeze(makeFields()) as OaField[]
    const next = removeField(fields, 'select_2')
    expect(next?.map((f) => f.key)).toEqual(['text_1', 'date_3'])
    expect(next).not.toBe(fields)
    expect(fields).toHaveLength(3)
    expect(removeField(fields, 'missing')).toBeNull()
  })

  it('duplicateField deep-copies nested config, dedups key, inserts after source', () => {
    const fields = makeFields()
    const res = duplicateField(fields, 'select_2')
    expect(res).not.toBeNull()
    expect(res!.next.map((f) => f.key)).toEqual(['text_1', 'select_2', 'select_2_copy', 'date_3'])
    expect(res!.next).not.toBe(fields)
    expect(fields).toHaveLength(3)

    // nested config is copied, not shared
    expect(res!.copy.options).toEqual(['x', 'y'])
    expect(res!.copy.options).not.toBe(fields[1]!.options)

    // second duplicate gets _copy2
    const res2 = duplicateField(res!.next, 'select_2')
    expect(res2!.copy.key).toBe('select_2_copy2')

    expect(duplicateField(fields, 'missing')).toBeNull()
  })

  it('moveFieldTo reorders by drop index without mutating input', () => {
    const fields = Object.freeze(makeFields()) as OaField[]

    // drop "text_1" at index 2 (index counted before removal)
    const res = moveFieldTo(fields, 'text_1', 2)
    expect(res!.next.map((f) => f.key)).toEqual(['select_2', 'text_1', 'date_3'])
    expect(res!.item.key).toBe('text_1')
    expect(fields.map((f) => f.key)).toEqual(['text_1', 'select_2', 'date_3'])

    // moving forward past the drop point
    const res2 = moveFieldTo(fields, 'text_1', 3)
    expect(res2!.next.map((f) => f.key)).toEqual(['select_2', 'date_3', 'text_1'])

    expect(moveFieldTo(fields, 'missing', 1)).toBeNull()
  })
})
