import { describe, expect, it } from 'vitest'
import { insertNodeAt, normalizeNode, removeNodeRow, type FlowNodeRow } from './flowModel'

function makeNode(seq: number, nodeType: FlowNodeRow['nodeType'] = 'approval'): FlowNodeRow {
  return normalizeNode({
    seq,
    nodeName: `N${seq}`,
    nodeType,
    approverType: 'USER',
    approverValue: '',
    branches: nodeType === 'condition' ? [] : null,
  })
}

/** v-model 语义：props 数组归父级所有，结构操作不得原地修改 */
describe('flowModel structural ops (FlowChainDesigner v-model:nodes semantics)', () => {
  it('insertNodeAt returns a resequenced new array without mutating input', () => {
    const nodes = Object.freeze([makeNode(1), makeNode(2)]) as FlowNodeRow[]
    const row = makeNode(99, 'cc')

    const next = insertNodeAt(nodes, 1, row)
    expect(next).not.toBe(nodes)
    expect(next).toHaveLength(3)
    expect(next.map((n) => n.seq)).toEqual([1, 2, 3])
    expect(next[1]).toBe(row)
    // 输入数组结构不变（长度/顺序/引用）；行对象与父级共享，seq 由 reseq 原地重编
    expect(nodes).toHaveLength(2)
    expect(nodes[0]).toBe(next[0])
  })

  it('insertNodeAt rewrites branch targets to the new seq numbering', () => {
    const cond = makeNode(1, 'condition')
    cond.branches = [{ expr: { field: 'a', op: 'eq', value: '1' }, targetSeq: 2 }]
    const tail = makeNode(2)
    const nodes = [cond, tail]

    // insert a node between cond and tail: tail seq 2 -> 3, branch target follows
    const next = insertNodeAt(nodes, 1, makeNode(99, 'cc'))
    expect(next.map((n) => n.seq)).toEqual([1, 2, 3])
    expect(next[0]!.branches![0]!.targetSeq).toBe(3)
  })

  it('removeNodeRow returns a resequenced new array, null when row absent', () => {
    const a = makeNode(1)
    const b = makeNode(2)
    const c = makeNode(3)
    const nodes = Object.freeze([a, b, c]) as FlowNodeRow[]

    const next = removeNodeRow(nodes, b)
    expect(next).not.toBe(nodes)
    expect(next?.map((n) => n.seq)).toEqual([1, 2])
    expect(next?.includes(b)).toBe(false)
    // 输入数组结构不变（长度/顺序/引用）；行对象与父级共享，seq 由 reseq 原地重编
    expect(nodes).toHaveLength(3)
    expect(nodes[0]).toBe(a)
    expect(nodes[2]).toBe(c)

    expect(removeNodeRow(nodes, makeNode(9))).toBeNull()
  })

  it('removeNodeRow clears default jump pointing at the removed node', () => {
    const cond = makeNode(1, 'condition')
    cond.defaultSeq = 2
    const tail = makeNode(2)

    const next = removeNodeRow([cond, tail], tail)
    expect(next).toHaveLength(1)
    expect(next![0]!.defaultSeq).toBeNull()
  })
})
