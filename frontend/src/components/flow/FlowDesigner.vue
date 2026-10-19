<script setup lang="ts">
/** 流程设计器：LogicFlow 画布（纵向主链）+ 右侧属性面板。
 *
 * 单一真源：节点行数组（v-model）为编辑真源；画布负责可视化与布局。
 * 保存时父组件调 exportGraph() 取回 LogicFlow 图（含拖拽布局）随节点行一并提交。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import LogicFlow from '@logicflow/core'
import '@logicflow/core/es/style/index.css'
import { Control } from '@logicflow/extension'
import '@logicflow/extension/es/index.css'
import {
  GRAPH_NODE_ID,
  buildGraphFromNodes,
  capturePositions,
  normalizeNode,
  validateFlowNodes,
  type FlowNodeRow,
} from './flowModel'
import { highlightSeqs, registerFlowNodes, resolveToken } from './flowNodes'
import type { FlowGraphData, FlowGraphEdge, FlowNodeType, FlowSignMode } from '@/api/types'

LogicFlow.use(Control)

const props = defineProps<{
  nodes: FlowNodeRow[]
  userOptions: { id: number; name: string }[]
  roleOptions: { id: number; name: string }[]
  /** 已保存的 LogicFlow 图：仅取节点坐标用于初始布局 */
  initialGraph?: FlowGraphData | null
}>()

const emit = defineEmits<{ (e: 'update:nodes', v: FlowNodeRow[]): void }>()

const { t } = useI18n()

const container = ref<HTMLElement>()
let lf: LogicFlow | null = null
let resizeObs: ResizeObserver | null = null

const selectedSeq = ref<number | null>(null)

const selectedNode = computed(() => props.nodes.find((n) => n.seq === selectedSeq.value) ?? null)

const OP_OPTIONS = ['eq', 'ne', 'gt', 'gte', 'lt', 'lte', 'in', 'contains']
const OP_LABELS: Record<string, string> = {
  eq: '==',
  ne: '!=',
  gt: '>',
  gte: '>=',
  lt: '<',
  lte: '<=',
  in: 'in',
  contains: 'contains',
}

const NODE_TYPE_ICON: Record<FlowNodeType, string> = {
  approval: '◉',
  condition: '◇',
  cc: '✉',
}

function emitChange() {
  emit('update:nodes', [...props.nodes])
}

function render(preserve = true) {
  if (!lf) return
  const positions = preserve ? capturePositions(lf.getGraphData() as FlowGraphData) : undefined
  highlightSeqs.clear()
  lf.render(buildGraphFromNodes(props.nodes, positions))
}

/** 节点行变更后同步画布文本与属性（不动布局）；文本由自定义 view 读 properties 自绘 */
function syncNodeToGraph(n: FlowNodeRow) {
  if (!lf) return
  const id = GRAPH_NODE_ID(n.seq)
  const gn = buildGraphFromNodes([n]).nodes.find((x) => x.id === id)
  if (!gn || !lf.getNodeModelById(id)) return
  lf.setProperties(id, gn.properties ?? {})
}

function reseq() {
  const byOldSeq = new Map(props.nodes.map((n) => [n.seq, n]))
  props.nodes.forEach((n, i) => {
    n.seq = i + 1
  })
  const newSeqOf = new Map(props.nodes.map((n) => [n, n.seq]))
  // 重编序号后回写分支/默认跳转目标
  for (const n of props.nodes) {
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

function addNode(nodeType: FlowNodeType) {
  const row = normalizeNode({
    seq: props.nodes.length + 1,
    nodeName: t(`admin.flow.defaultName.${nodeType}`),
    nodeType,
    approverType: 'USER',
    approverValue: '',
    branches: nodeType === 'condition' ? [] : null,
  })
  row.signMode = 'or'
  props.nodes.push(row)
  emitChange()
  render()
  selectedSeq.value = row.seq
}

function deleteSelected() {
  const n = selectedNode.value
  if (!n) return
  const idx = props.nodes.indexOf(n)
  if (idx < 0) return
  props.nodes.splice(idx, 1)
  selectedSeq.value = null
  reseq()
  emitChange()
  render()
}

function moveSelected(dir: -1 | 1) {
  const n = selectedNode.value
  if (!n) return
  const idx = props.nodes.indexOf(n)
  const target = idx + dir
  if (idx < 0 || target < 0 || target >= props.nodes.length) return
  props.nodes[idx] = props.nodes[target]!
  props.nodes[target] = n
  reseq()
  emitChange()
  render()
}

function onNodeChanged(n: FlowNodeRow) {
  emitChange()
  syncNodeToGraph(n)
}

function onApproverValueChange(n: FlowNodeRow, ids: (number | string)[]) {
  const list = n.approverType === 'ROLE' ? props.roleOptions : props.userOptions
  n.approverValue = ids.join(',')
  n.approverName = ids
    .map((id) => list.find((x) => String(x.id) === String(id))?.name ?? '')
    .filter(Boolean)
    .join(',')
  onNodeChanged(n)
}

function approverIds(n: FlowNodeRow): string[] {
  return String(n.approverValue ?? '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
}

function addBranch(n: FlowNodeRow) {
  const branches = n.branches ?? []
  branches.push({ expr: { field: '', op: 'eq', value: '' }, targetSeq: 0 })
  n.branches = branches
  onNodeChanged(n)
}

function removeBranch(n: FlowNodeRow, idx: number) {
  n.branches?.splice(idx, 1)
  onNodeChanged(n)
  render() // branch edges changed: full re-render
}

function onBranchChanged(n: FlowNodeRow) {
  onNodeChanged(n)
  render()
}

function targetOptions(excludeSeq: number) {
  return props.nodes.filter((n) => n.seq !== excludeSeq)
}

function validate(): string[] {
  return validateFlowNodes(props.nodes)
}

function exportGraph(): FlowGraphData {
  if (!lf) return buildGraphFromNodes(props.nodes)
  const raw = lf.getGraphData() as FlowGraphData
  return {
    nodes: raw.nodes.map((n) => ({
      id: n.id,
      type: n.type,
      x: Math.round(n.x),
      y: Math.round(n.y),
      text: typeof n.text === 'string' ? n.text : ((n.text as { value?: string } | undefined)?.value ?? ''),
      properties: n.properties ?? {},
    })),
    edges: raw.edges.map((e) => ({
      type: (e as FlowGraphEdge).type ?? 'polyline',
      sourceNodeId: e.sourceNodeId,
      targetNodeId: e.targetNodeId,
      properties: e.properties ?? {},
    })),
  }
}

defineExpose({ validate, exportGraph })

watch(
  () => props.nodes.length,
  () => nextTick(() => render()),
)

onMounted(() => {
  lf = new LogicFlow({
    container: container.value!,
    grid: { visible: true, size: 10, type: 'dot' },
    keyboard: { enabled: false },
    isSilentMode: false,
    edgeType: 'polyline',
    style: {
      rect: { radius: 8 },
      polyline: { stroke: resolveToken('--bs-color-fg-muted', '#8a94a3'), strokeWidth: 1.5 },
      edgeText: {
        color: resolveToken('--bs-color-fg-secondary', '#5a6472'),
        fontSize: 11,
        textWidth: 120,
        background: { fill: resolveToken('--bs-color-bg-surface', '#ffffff') },
      } as never,
    },
  })
  registerFlowNodes(lf as never)
  // 结构由节点行驱动：禁止画布上手动连线/拖出节点
  ;(lf.graphModel.editConfigModel as unknown as Record<string, boolean>).isSilentMode = false
  lf.on('node:click', ({ data }) => {
    const seq = Number((data.properties as Record<string, unknown> | undefined)?.seq)
    selectedSeq.value = Number.isFinite(seq) && seq > 0 ? seq : null
  })
  lf.on('blank:click', () => {
    selectedSeq.value = null
  })
  // 去掉撤销/重做（状态由节点行驱动，避免与画布历史栈不一致）；须在首次 render 前移除
  try {
    const control = (lf as unknown as { extension?: { control?: { removeItem: (k: string) => void } } })
      .extension?.control
    control?.removeItem('undo')
    control?.removeItem('redo')
  } catch {
    /* control 项不存在时忽略 */
  }
  const initialPositions = props.initialGraph ? capturePositions(props.initialGraph) : undefined
  lf.render(buildGraphFromNodes(props.nodes, initialPositions))
  let lastW = container.value!.clientWidth
  let lastH = container.value!.clientHeight
  resizeObs = new ResizeObserver(() => {
    if (lf && container.value) {
      const w = container.value.clientWidth
      const h = container.value.clientHeight
      if (w !== lastW || h !== lastH) {
        lastW = w
        lastH = h
        lf.resize(w, h)
      }
    }
  })
  resizeObs.observe(container.value!)
})

onBeforeUnmount(() => {
  resizeObs?.disconnect()
  resizeObs = null
  lf?.destroy()
  lf = null
})
</script>

<template>
  <div class="flow-designer">
    <div class="fd-toolbar">
      <el-button size="small" @click="addNode('approval')">
        {{ NODE_TYPE_ICON.approval }} {{ t('admin.flow.addApproval') }}
      </el-button>
      <el-button size="small" @click="addNode('condition')">
        {{ NODE_TYPE_ICON.condition }} {{ t('admin.flow.addCondition') }}
      </el-button>
      <el-button size="small" @click="addNode('cc')">
        {{ NODE_TYPE_ICON.cc }} {{ t('admin.flow.addCc') }}
      </el-button>
      <template v-if="selectedNode">
        <el-divider direction="vertical" />
        <el-button size="small" :disabled="selectedNode.seq <= 1" @click="moveSelected(-1)">
          {{ t('admin.flow.moveUp') }}
        </el-button>
        <el-button
          size="small"
          :disabled="selectedNode.seq >= props.nodes.length"
          @click="moveSelected(1)"
        >
          {{ t('admin.flow.moveDown') }}
        </el-button>
        <el-button size="small" type="danger" plain @click="deleteSelected">
          {{ t('common.action.delete') }}
        </el-button>
      </template>
    </div>

    <div class="fd-body">
      <div ref="container" class="fd-canvas" />

      <div v-if="selectedNode" class="fd-panel">
        <div class="fd-panel-title">
          {{ t(`admin.flow.nodeType.${selectedNode.nodeType}`) }}
        </div>
        <el-form label-position="top" size="small">
          <el-form-item :label="t('admin.flow.nodeName')">
            <el-input v-model="selectedNode.nodeName" @input="onNodeChanged(selectedNode)" />
          </el-form-item>

          <template v-if="selectedNode.nodeType !== 'condition'">
            <el-form-item v-if="selectedNode.nodeType === 'approval'" :label="t('admin.flow.signMode.label')">
              <el-radio-group
                :model-value="selectedNode.signMode"
                @update:model-value="selectedNode.signMode = $event as FlowSignMode; onNodeChanged(selectedNode)"
              >
                <el-radio-button value="or">{{ t('admin.flow.signMode.or') }}</el-radio-button>
                <el-radio-button value="and">{{ t('admin.flow.signMode.and') }}</el-radio-button>
                <el-radio-button value="sequential">{{ t('admin.flow.signMode.sequential') }}</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item :label="t('admin.flow.approverType')">
              <el-select
                :model-value="selectedNode.approverType"
                style="width: 100%"
                @update:model-value="selectedNode.approverType = $event as 'USER' | 'ROLE'; selectedNode.approverValue = ''; selectedNode.approverName = ''; onNodeChanged(selectedNode)"
              >
                <el-option :label="t('admin.flow.approverUser')" value="USER" />
                <el-option :label="t('admin.flow.approverRole')" value="ROLE" />
              </el-select>
            </el-form-item>
            <el-form-item
              :label="selectedNode.nodeType === 'cc' ? t('admin.flow.selectCc') : t('admin.flow.selectApprover')"
            >
              <el-select
                :model-value="approverIds(selectedNode)"
                multiple
                filterable
                collapse-tags
                collapse-tags-tooltip
                style="width: 100%"
                @update:model-value="onApproverValueChange(selectedNode, $event as (number | string)[])"
              >
                <el-option
                  v-for="opt in (selectedNode.approverType === 'ROLE' ? props.roleOptions : props.userOptions)"
                  :key="opt.id"
                  :label="opt.name"
                  :value="String(opt.id)"
                />
              </el-select>
            </el-form-item>
          </template>

          <template v-else>
            <el-form-item :label="t('admin.flow.branches')">
              <div class="branch-list">
                <div v-for="(b, i) in selectedNode.branches ?? []" :key="i" class="branch-row">
                  <el-input
                    v-model="b.expr.field"
                    :placeholder="t('admin.flow.branchField')"
                    class="branch-field"
                    @input="onNodeChanged(selectedNode)"
                  />
                  <el-select
                    v-model="b.expr.op"
                    class="branch-op"
                    @update:model-value="onNodeChanged(selectedNode)"
                  >
                    <el-option v-for="op in OP_OPTIONS" :key="op" :label="OP_LABELS[op]" :value="op" />
                  </el-select>
                  <el-input
                    :model-value="String(b.expr.value ?? '')"
                    :placeholder="t('admin.flow.branchValue')"
                    class="branch-value"
                    @update:model-value="b.expr.value = $event; onNodeChanged(selectedNode)"
                  />
                  <el-select
                    v-model="b.targetSeq"
                    :placeholder="t('admin.flow.branchTarget')"
                    class="branch-target"
                    @update:model-value="onBranchChanged(selectedNode)"
                  >
                    <el-option
                      v-for="opt in targetOptions(selectedNode.seq)"
                      :key="opt.seq"
                      :label="`${opt.seq}. ${opt.nodeName}`"
                      :value="opt.seq"
                    />
                  </el-select>
                  <el-button link type="danger" @click="removeBranch(selectedNode, i)">
                    {{ t('common.action.delete') }}
                  </el-button>
                </div>
                <el-button size="small" plain type="primary" @click="addBranch(selectedNode)">
                  {{ t('admin.flow.addBranch') }}
                </el-button>
              </div>
            </el-form-item>
            <el-form-item :label="t('admin.flow.defaultSeq')">
              <el-select
                :model-value="selectedNode.defaultSeq ?? 0"
                style="width: 100%"
                clearable
                @update:model-value="selectedNode.defaultSeq = ($event as number) || null; onBranchChanged(selectedNode)"
              >
                <el-option :label="t('admin.flow.defaultNone')" :value="0" />
                <el-option
                  v-for="opt in targetOptions(selectedNode.seq)"
                  :key="opt.seq"
                  :label="`${opt.seq}. ${opt.nodeName}`"
                  :value="opt.seq"
                />
              </el-select>
            </el-form-item>
          </template>
        </el-form>
      </div>

      <div v-else class="fd-panel fd-panel-empty">
        {{ t('admin.flow.panelHint') }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.flow-designer {
  display: flex;
  flex-direction: column;
  width: 100%;
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-lg);
  overflow: hidden;
  background: var(--bs-color-bg-default, #fff);
}

.fd-toolbar {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  padding: var(--bs-space-2) var(--bs-space-3);
  border-bottom: 1px solid var(--bs-color-border-subtle);
  background: var(--bs-color-fill-lighter);
}

.fd-body {
  display: flex;
  min-height: 460px;
}

.fd-canvas {
  flex: 1;
  min-width: 0;
  height: 460px;
  position: relative;
  overflow: hidden;
}

.fd-panel {
  width: 320px;
  flex-shrink: 0;
  border-left: 1px solid var(--bs-color-border-subtle);
  padding: var(--bs-space-3);
  overflow-y: auto;
  max-height: 460px;
}

.fd-panel-title {
  font-weight: 600;
  margin-bottom: var(--bs-space-3);
  color: var(--bs-color-fg-default);
}

.fd-panel-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-sm);
}

.branch-list {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
}

.branch-row {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-1);
  padding: var(--bs-space-2);
  border: 1px dashed var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
}

/* LogicFlow 控制条适配令牌 */
.fd-canvas :deep(.lf-control) {
  background: var(--bs-color-bg-default, #fff);
  border-radius: var(--bs-radius-md);
  box-shadow: var(--bs-shadow-elevation2);
}
</style>
