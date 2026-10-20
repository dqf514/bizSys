/** 流程图模型：节点行（后端路由真源）↔ LogicFlow 图（设计器真源，含布局）双向转换。
 *
 * 与后端 app/modules/approval/graph.py 同构：
 * - 图节点 id：start / end / n{seq}；
 * - 主链边：无 properties.expr/default；条件分支边带 expr；默认跳转边带 default=true；
 * - derive 时按主链行走重新编 seq，分支 targetSeq 以新序号回写。
 */
import type {
  FlowApproverType,
  FlowBranch,
  FlowGraphData,
  FlowGraphEdge,
  FlowGraphNode,
  FlowNode,
  FlowNodeType,
  FlowSignMode,
} from '@/api/types'

export const GRAPH_NODE_ID = (seq: number) => `n${seq}`

/** 组织审批人类型：approverValue 可空（作为兜底角色 code），审批人按发起人部门任职解析 */
export const ORG_APPROVER_TYPES: FlowApproverType[] = ['DEPT_LEADER', 'PARENT_DEPT_LEADER', 'SUPERVISOR_CHAIN']

export function isOrgApproverType(t?: string): boolean {
  return ORG_APPROVER_TYPES.includes(t as FlowApproverType)
}

export interface FlowNodeRow extends FlowNode {
  nodeType: FlowNodeType
  signMode: FlowSignMode
}

export function normalizeNode(n: FlowNode): FlowNodeRow {
  return {
    ...n,
    nodeType: n.nodeType ?? 'approval',
    signMode: n.signMode ?? 'or',
    chainLevels: n.chainLevels ?? null,
    branches: n.branches ?? null,
    defaultSeq: n.defaultSeq ?? null,
  }
}

function nodeSubtitle(n: FlowNodeRow): string {
  if (n.nodeType === 'condition') return `${n.branches?.length ?? 0}`
  return n.approverName || String(n.approverValue || '')
}

export function toGraphNode(n: FlowNodeRow, x: number, y: number): FlowGraphNode {
  return {
    id: GRAPH_NODE_ID(n.seq),
    type: n.nodeType,
    x,
    y,
    // 不写 text：自定义 view 自绘双行文本，默认 text 会与之叠影
    properties: {
      seq: n.seq,
      nodeName: n.nodeName,
      nodeType: n.nodeType,
      signMode: n.signMode,
      approverType: n.approverType,
      approverValue: n.approverValue,
      approverName: n.approverName ?? '',
      chainLevels: n.chainLevels ?? null,
      subtitle: nodeSubtitle(n),
    },
  }
}

/** 节点行 → LogicFlow 图（纵向布局；positions 可传入既有坐标保留拖拽布局） */
export function buildGraphFromNodes(
  nodes: FlowNode[],
  positions?: Record<string, { x: number; y: number }>,
): FlowGraphData {
  const rows = nodes.map(normalizeNode).sort((a, b) => a.seq - b.seq)
  const pos = (id: string, dx: number, dy: number) => positions?.[id] ?? { x: dx, y: dy }
  // start/end 始终按链长计算位置，避免增删节点后与主链节点重叠
  const graphNodes: FlowGraphNode[] = [
    { id: 'start', type: 'start', x: 320, y: 60, text: 'start', properties: {} },
  ]
  rows.forEach((n, i) => {
    const p = pos(GRAPH_NODE_ID(n.seq), 320, 170 + i * 120)
    graphNodes.push({ ...toGraphNode(n, p.x, p.y) })
  })
  graphNodes.push({ id: 'end', type: 'end', x: 320, y: 170 + rows.length * 120, text: 'end', properties: {} })

  const edges: FlowGraphEdge[] = []
  const chainIds = ['start', ...rows.map((n) => GRAPH_NODE_ID(n.seq)), 'end']
  for (let i = 0; i < chainIds.length - 1; i++) {
    // 必须带 type：LogicFlow 按 model.type 查视图，缺省会落到空字符串导致边不渲染
    edges.push({ type: 'polyline', sourceNodeId: chainIds[i]!, targetNodeId: chainIds[i + 1]!, properties: {} })
  }
  // 条件节点：主链边即"未命中 fall-through"，分支/显式默认边附加
  for (const n of rows) {
    if (n.nodeType !== 'condition') continue
    const nid = GRAPH_NODE_ID(n.seq)
    for (const b of n.branches ?? []) {
      edges.push({
        type: 'polyline',
        sourceNodeId: nid,
        targetNodeId: GRAPH_NODE_ID(b.targetSeq),
        properties: { expr: b.expr },
        // 边文本展示表达式摘要
        ...({ text: `${b.expr.field} ${b.expr.op} ${String(b.expr.value)}` } as Record<string, unknown>),
      })
    }
    if (n.defaultSeq) {
      edges.push({
        type: 'polyline',
        sourceNodeId: nid,
        targetNodeId: GRAPH_NODE_ID(n.defaultSeq),
        properties: { default: true },
      })
    }
  }
  return { nodes: graphNodes, edges }
}

function edgeKind(e: FlowGraphEdge): 'branch' | 'default' | 'chain' {
  if (e.properties?.expr) return 'branch'
  if (e.properties?.default) return 'default'
  return 'chain'
}

/** LogicFlow 图 → 节点行：从 start 沿主链行走重编 seq，分支/默认目标回写新序号。 */
export function deriveNodesFromGraph(graph: FlowGraphData): FlowNodeRow[] {
  const byId = new Map(graph.nodes.map((n) => [n.id, n]))
  const outgoing = new Map<string, FlowGraphEdge[]>()
  for (const e of graph.edges) {
    const list = outgoing.get(e.sourceNodeId) ?? []
    list.push(e)
    outgoing.set(e.sourceNodeId, list)
  }
  const chainEdge = (id: string) => (outgoing.get(id) ?? []).find((e) => edgeKind(e) === 'chain')

  // 主链行走
  const chain: FlowGraphNode[] = []
  let cur = chainEdge('start')?.targetNodeId
  let guard = 0
  while (cur && cur !== 'end' && guard < 200) {
    guard++
    const node = byId.get(cur)
    if (!node) break
    chain.push(node)
    cur = chainEdge(cur)?.targetNodeId
  }
  // 不在主链上的游离业务节点（分支侧挂）按 id 顺序追加，保证不丢配置
  const onChain = new Set(chain.map((n) => n.id))
  const loose = graph.nodes.filter(
    (n) => !onChain.has(n.id) && !['start', 'end'].includes(n.id) && ['approval', 'condition', 'cc'].includes(n.type),
  )

  const seqOf = new Map<string, number>()
  ;[...chain, ...loose].forEach((n, i) => seqOf.set(n.id, i + 1))

  const rows: FlowNodeRow[] = []
  for (const node of [...chain, ...loose]) {
    const p = (node.properties ?? {}) as Record<string, unknown>
    const nodeType = (p.nodeType as FlowNodeType) || (node.type as FlowNodeType) || 'approval'
    const row: FlowNodeRow = {
      seq: seqOf.get(node.id)!,
      nodeName: (p.nodeName as string) || (typeof node.text === 'string' ? node.text : '') || '',
      nodeType,
      signMode: (p.signMode as FlowSignMode) || 'or',
      approverType: (p.approverType as FlowNodeRow['approverType']) || 'USER',
      approverValue: (p.approverValue as string | number) ?? '',
      approverName: (p.approverName as string) || '',
      chainLevels: (p.chainLevels as number | null) ?? null,
      branches: null,
      defaultSeq: null,
    }
    if (nodeType === 'condition') {
      const branches: FlowBranch[] = []
      for (const e of outgoing.get(node.id) ?? []) {
        const kind = edgeKind(e)
        const targetSeq = seqOf.get(e.targetNodeId)
        if (kind === 'branch' && targetSeq) {
          branches.push({ expr: e.properties!.expr as FlowBranch['expr'], targetSeq })
        } else if (kind === 'default' && targetSeq) {
          row.defaultSeq = targetSeq
        }
      }
      row.branches = branches
    }
    rows.push(row)
  }
  return rows
}

/** 增删/移动后重编 seq，并把分支/默认跳转目标回写为新序号 */
export function reseqNodes(nodes: FlowNodeRow[]) {
  const byOldSeq = new Map(nodes.map((n) => [n.seq, n]))
  nodes.forEach((n, i) => {
    n.seq = i + 1
  })
  const newSeqOf = new Map(nodes.map((n) => [n, n.seq]))
  for (const n of nodes) {
    for (const b of n.branches ?? []) {
      const target = byOldSeq.get(b.targetSeq)
      if (target) b.targetSeq = newSeqOf.get(target) ?? b.targetSeq
    }
    if (n.defaultSeq) {
      const target = byOldSeq.get(n.defaultSeq)
      n.defaultSeq = target ? (newSeqOf.get(target) ?? null) : null
    }
  }
}

/** 保存前校验，返回 i18n key 列表（空 = 通过） */
export function validateFlowNodes(nodes: FlowNodeRow[]): string[] {
  const errors: string[] = []
  if (!nodes.length) {
    errors.push('admin.flow.errNoNode')
    return errors
  }
  if (!nodes.some((n) => n.nodeType === 'approval')) errors.push('admin.flow.errNeedApproval')
  const seqs = new Set(nodes.map((n) => n.seq))
  for (const n of nodes) {
    if (!n.nodeName.trim()) errors.push('admin.flow.errNodeName')
    // 组织类型审批人按发起人部门任职解析，approverValue 仅作兜底角色，可空
    if (
      (n.nodeType === 'approval' || n.nodeType === 'cc') &&
      !isOrgApproverType(n.approverType) &&
      !String(n.approverValue ?? '').trim()
    ) {
      errors.push('admin.flow.errApprover')
    }
    if (n.nodeType === 'condition') {
      if (!n.branches?.length) errors.push('admin.flow.errBranch')
      for (const b of n.branches ?? []) {
        if (!b.expr?.field || !seqs.has(b.targetSeq)) errors.push('admin.flow.errBranchTarget')
      }
      if (n.defaultSeq && !seqs.has(n.defaultSeq)) errors.push('admin.flow.errBranchTarget')
    }
  }
  return [...new Set(errors)]
}

/** 从 LogicFlow getGraphData() 提取当前节点坐标，供重渲染保留布局 */
export function capturePositions(graph: FlowGraphData): Record<string, { x: number; y: number }> {
  const out: Record<string, { x: number; y: number }> = {}
  for (const n of graph.nodes) out[n.id] = { x: n.x, y: n.y }
  return out
}
