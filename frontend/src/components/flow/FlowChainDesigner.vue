<script setup lang="ts">
/** 竖链流程设计器（复刻 TPCworkflow WorkflowVerticalDesigner 交互形态，数据模型保持 bizSys 节点行）。
 *
 * 开始卡片 → 节点卡片竖链（审批/条件/抄送）→ 结束；节点间 "+" 插入菜单；
 * 条件节点下方分支泳道（条件 N / 默认，显示跳转目标）；点卡片开右侧配置抽屉。
 * 单一真源：节点行数组（v-model）；保存时 exportGraph() 由节点行自动生成
 * LogicFlow 兼容图（自动纵向布局），process_graph 双写语义与旧图形模式一致。
 */
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import FlowChainNode from './FlowChainNode.vue'
import FlowChainConnector from './FlowChainConnector.vue'
import {
  buildGraphFromNodes,
  isOrgApproverType,
  normalizeNode,
  reseqNodes,
  validateFlowNodes,
  type FlowNodeRow,
} from './flowModel'
import type {
  FlowApproverType,
  FlowGraphData,
  FlowNodeType,
} from '@/api/types'

const props = defineProps<{
  nodes: FlowNodeRow[]
  userOptions: { id: number; name: string }[]
  roleOptions: { id: number; name: string; code?: string }[]
}>()

const emit = defineEmits<{ (e: 'update:nodes', v: FlowNodeRow[]): void }>()

const { t } = useI18n()

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

const APPROVER_TYPES: FlowApproverType[] = ['USER', 'ROLE', 'DEPT_LEADER', 'PARENT_DEPT_LEADER', 'SUPERVISOR_CHAIN']
const APPROVER_TYPE_KEYS: Record<FlowApproverType, string> = {
  USER: 'admin.flow.approverUser',
  ROLE: 'admin.flow.approverRole',
  DEPT_LEADER: 'admin.flow.approverDeptLeader',
  PARENT_DEPT_LEADER: 'admin.flow.approverParentDeptLeader',
  SUPERVISOR_CHAIN: 'admin.flow.approverSupervisorChain',
}

/* ---------- 结构操作 ---------- */

function emitChange() {
  emit('update:nodes', [...props.nodes])
}

function insertAt(index: number, nodeType: FlowNodeType) {
  const row = normalizeNode({
    seq: index + 1,
    nodeName: t(`admin.flow.defaultName.${nodeType}`),
    nodeType,
    approverType: 'USER',
    approverValue: '',
    branches: nodeType === 'condition' ? [] : null,
  })
  row.signMode = 'or'
  props.nodes.splice(index, 0, row)
  reseqNodes(props.nodes)
  emitChange()
  openConfig(row)
}

function removeNode(n: FlowNodeRow) {
  const idx = props.nodes.indexOf(n)
  if (idx < 0) return
  props.nodes.splice(idx, 1)
  reseqNodes(props.nodes)
  emitChange()
  if (current.value === n) drawerVisible.value = false
}

/* ---------- 配置抽屉 ---------- */

const drawerVisible = ref(false)
const current = ref<FlowNodeRow | null>(null)

function openConfig(n: FlowNodeRow) {
  current.value = n
  drawerVisible.value = true
}

function onApproverTypeChange(n: FlowNodeRow, v: FlowApproverType) {
  n.approverType = v
  n.approverValue = ''
  n.approverName = ''
  if (v === 'SUPERVISOR_CHAIN' && n.chainLevels == null) n.chainLevels = 0
}

function onApproverValueChange(n: FlowNodeRow, ids: (number | string)[]) {
  const list = n.approverType === 'ROLE' ? props.roleOptions : props.userOptions
  n.approverValue = ids.join(',')
  n.approverName = ids
    .map((id) => list.find((x) => String(x.id) === String(id))?.name ?? '')
    .filter(Boolean)
    .join(',')
}

/** 组织类型兜底角色：存角色 code（后端按 code 解析，见 engine._resolve_role_users） */
function onFallbackRoleChange(n: FlowNodeRow, codes: string[]) {
  n.approverValue = codes.join(',')
  n.approverName = codes
    .map((c) => props.roleOptions.find((x) => (x.code ?? String(x.id)) === c)?.name ?? '')
    .filter(Boolean)
    .join(',')
}

function approverIds(n: FlowNodeRow): string[] {
  return String(n.approverValue ?? '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
}

/* ---------- 条件分支 ---------- */

function addBranch(n: FlowNodeRow) {
  const branches = n.branches ?? []
  branches.push({
    expr: { field: '', op: 'eq', value: '' },
    targetSeq: n.seq < props.nodes.length ? n.seq + 1 : 0,
  })
  n.branches = branches
  emitChange()
}

function removeBranch(n: FlowNodeRow, idx: number) {
  n.branches?.splice(idx, 1)
  emitChange()
}

function targetOptions(excludeSeq: number) {
  return props.nodes.filter((n) => n.seq !== excludeSeq)
}

function targetName(seq: number): string {
  const hit = props.nodes.find((n) => n.seq === seq)
  return hit ? `${hit.seq}. ${hit.nodeName}` : ''
}

/* ---------- 保存出口 ---------- */

function validate(): string[] {
  return validateFlowNodes(props.nodes)
}

function exportGraph(): FlowGraphData {
  return buildGraphFromNodes(props.nodes)
}

defineExpose({ validate, exportGraph })
</script>

<template>
  <div class="chain-designer">
    <div class="chain-hint">{{ t('admin.flow.chainHint') }}</div>
    <div class="chain-scroll">
      <div class="chain-canvas">
        <div class="chain-terminal">{{ t('admin.flow.start') }}</div>
        <FlowChainConnector @add="insertAt(0, $event)" />

        <template v-for="(n, i) in props.nodes" :key="i">
          <FlowChainNode :node="n" @edit="openConfig(n)" @remove="removeNode(n)" />

          <div v-if="n.nodeType === 'condition'" class="branch-lanes">
            <div
              v-for="(b, bi) in n.branches ?? []"
              :key="bi"
              class="lane"
              @click="openConfig(n)"
            >
              <span class="lane-badge">{{ t('admin.flow.branchN', { n: bi + 1 }) }}</span>
              <span class="lane-expr">{{ b.expr.field || '?' }} {{ OP_LABELS[b.expr.op] ?? b.expr.op }} {{ String(b.expr.value ?? '') || '?' }}</span>
              <span class="lane-arrow">→</span>
              <span class="lane-target" :class="{ unset: !targetName(b.targetSeq) }">
                {{ targetName(b.targetSeq) || t('admin.flow.targetUnset') }}
              </span>
              <el-popconfirm
                :title="t('admin.flow.deleteBranchConfirm')"
                :confirm-button-text="t('common.action.confirm')"
                :cancel-button-text="t('common.action.cancel')"
                width="200"
                @confirm="removeBranch(n, bi)"
              >
                <template #reference>
                  <button type="button" class="lane-del" @click.stop>×</button>
                </template>
              </el-popconfirm>
            </div>
            <div class="lane is-default" @click="openConfig(n)">
              <span class="lane-badge is-default">{{ t('admin.flow.defaultBranch') }}</span>
              <span class="lane-arrow">→</span>
              <span class="lane-target" :class="{ unset: !n.defaultSeq }">
                {{ n.defaultSeq ? targetName(n.defaultSeq) : t('admin.flow.defaultNone') }}
              </span>
            </div>
            <el-button size="small" plain type="primary" class="lane-add" @click="addBranch(n)">
              {{ t('admin.flow.addBranch') }}
            </el-button>
          </div>

          <FlowChainConnector @add="insertAt(i + 1, $event)" />
        </template>

        <div class="chain-terminal">{{ t('admin.flow.end') }}</div>
      </div>
    </div>

    <el-drawer
      v-model="drawerVisible"
      :title="current ? t(`admin.flow.nodeType.${current.nodeType}`) : ''"
      size="460px"
      append-to-body
      destroy-on-close
    >
      <template v-if="current">
        <el-form label-position="top" size="default" class="node-config">
          <el-form-item :label="t('admin.flow.nodeName')">
            <el-input v-model="current.nodeName" />
          </el-form-item>

          <template v-if="current.nodeType !== 'condition'">
            <el-form-item v-if="current.nodeType === 'approval'" :label="t('admin.flow.signMode.label')">
              <el-radio-group v-model="current.signMode">
                <el-radio-button value="or">{{ t('admin.flow.signMode.or') }}</el-radio-button>
                <el-radio-button value="and">{{ t('admin.flow.signMode.and') }}</el-radio-button>
                <el-radio-button value="sequential">{{ t('admin.flow.signMode.sequential') }}</el-radio-button>
              </el-radio-group>
            </el-form-item>

            <el-form-item :label="t('admin.flow.approverType')">
              <el-radio-group
                :model-value="current.approverType"
                class="approver-type-group"
                @update:model-value="onApproverTypeChange(current, $event as FlowApproverType)"
              >
                <el-radio v-for="at in APPROVER_TYPES" :key="at" :value="at">{{ t(APPROVER_TYPE_KEYS[at]) }}</el-radio>
              </el-radio-group>
            </el-form-item>

            <el-form-item v-if="current.approverType === 'SUPERVISOR_CHAIN'" :label="t('admin.flow.chainLevels')">
              <el-input-number
                :model-value="current.chainLevels ?? 0"
                :min="0"
                :max="20"
                @update:model-value="current.chainLevels = Number($event ?? 0)"
              />
              <div class="field-tip">{{ t('admin.flow.chainLevelsTip') }}</div>
            </el-form-item>

            <el-form-item v-if="isOrgApproverType(current.approverType)" :label="t('admin.flow.orgFallbackRole')">
              <el-select
                :model-value="approverIds(current)"
                multiple
                filterable
                clearable
                collapse-tags
                collapse-tags-tooltip
                style="width: 100%"
                @update:model-value="onFallbackRoleChange(current, $event as string[])"
              >
                <el-option
                  v-for="opt in props.roleOptions"
                  :key="opt.id"
                  :label="opt.name"
                  :value="opt.code ?? String(opt.id)"
                />
              </el-select>
              <div class="field-tip">{{ t('admin.flow.orgFallbackTip') }}</div>
            </el-form-item>
            <el-form-item
              v-else
              :label="current.nodeType === 'cc' ? t('admin.flow.selectCc') : t('admin.flow.selectApprover')"
            >
              <el-select
                :model-value="approverIds(current)"
                multiple
                filterable
                collapse-tags
                collapse-tags-tooltip
                style="width: 100%"
                @update:model-value="onApproverValueChange(current, $event as (number | string)[])"
              >
                <el-option
                  v-for="opt in (current.approverType === 'ROLE' ? props.roleOptions : props.userOptions)"
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
                <div v-for="(b, i) in current.branches ?? []" :key="i" class="branch-row">
                  <div class="branch-row-head">
                    <span>{{ t('admin.flow.branchN', { n: i + 1 }) }}</span>
                    <el-button link type="danger" size="small" @click="removeBranch(current, i)">
                      {{ t('common.action.delete') }}
                    </el-button>
                  </div>
                  <div class="branch-expr-row">
                    <el-input v-model="b.expr.field" :placeholder="t('admin.flow.branchField')" class="branch-field" />
                    <el-select v-model="b.expr.op" class="branch-op">
                      <el-option v-for="op in OP_OPTIONS" :key="op" :label="OP_LABELS[op]" :value="op" />
                    </el-select>
                    <el-input
                      :model-value="String(b.expr.value ?? '')"
                      :placeholder="t('admin.flow.branchValue')"
                      class="branch-value"
                      @update:model-value="b.expr.value = $event"
                    />
                  </div>
                  <el-select v-model="b.targetSeq" :placeholder="t('admin.flow.branchTarget')" style="width: 100%">
                    <el-option
                      v-for="opt in targetOptions(current.seq)"
                      :key="opt.seq"
                      :label="`${opt.seq}. ${opt.nodeName}`"
                      :value="opt.seq"
                    />
                  </el-select>
                </div>
                <el-button size="small" plain type="primary" @click="addBranch(current)">
                  {{ t('admin.flow.addBranch') }}
                </el-button>
              </div>
            </el-form-item>
            <el-form-item :label="t('admin.flow.defaultSeq')">
              <el-select
                :model-value="current.defaultSeq ?? 0"
                style="width: 100%"
                clearable
                @update:model-value="current.defaultSeq = ($event as number) || null"
              >
                <el-option :label="t('admin.flow.defaultNone')" :value="0" />
                <el-option
                  v-for="opt in targetOptions(current.seq)"
                  :key="opt.seq"
                  :label="`${opt.seq}. ${opt.nodeName}`"
                  :value="opt.seq"
                />
              </el-select>
            </el-form-item>
          </template>
        </el-form>
      </template>
      <template #footer>
        <div class="drawer-footer">
          <el-popconfirm
            :title="t('admin.flow.deleteNodeConfirm')"
            :confirm-button-text="t('common.action.confirm')"
            :cancel-button-text="t('common.action.cancel')"
            width="200"
            @confirm="current && removeNode(current)"
          >
            <template #reference>
              <el-button type="danger" plain>{{ t('admin.flow.deleteNode') }}</el-button>
            </template>
          </el-popconfirm>
          <el-button type="primary" @click="drawerVisible = false">{{ t('common.action.ok') }}</el-button>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<style scoped>
.chain-designer {
  display: flex;
  flex-direction: column;
  width: 100%;
  gap: var(--bs-space-2);
}

.chain-hint {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.chain-scroll {
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-lg);
  background: var(--bs-color-fill-lighter);
  overflow: auto;
  max-height: 56vh;
  min-height: 420px;
}

.chain-canvas {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--bs-space-4) var(--bs-space-4) var(--bs-space-6, 24px);
  min-width: min-content;
}

.chain-terminal {
  width: 220px;
  padding: var(--bs-space-2) 0;
  text-align: center;
  border-radius: var(--bs-radius-lg);
  border: 1px dashed var(--bs-color-border-strong);
  background: var(--bs-color-fill-light);
  color: var(--bs-color-fg-secondary);
  font-size: var(--bs-typography-font-size-sm);
  font-weight: 600;
  flex-shrink: 0;
}

.branch-lanes {
  width: 100%;
  max-width: 560px;
  margin: var(--bs-space-2) 0;
  padding: var(--bs-space-3);
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-lg);
  background: var(--bs-color-bg-surface);
}

.lane {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  padding: var(--bs-space-2) var(--bs-space-3);
  border: 1px solid var(--bs-color-border-subtle);
  border-left: 3px solid var(--bs-color-semantic-warning);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-fill-lighter);
  cursor: pointer;
  font-size: var(--bs-typography-font-size-xs);
}

.lane:hover {
  border-color: var(--bs-color-brand-primary);
}

.lane.is-default {
  border-left-color: var(--bs-color-brand-primary);
}

.lane-badge {
  flex-shrink: 0;
  padding: 1px 8px;
  border-radius: var(--bs-radius-sm);
  background: var(--bs-color-semantic-warning);
  color: #fff;
  font-weight: 700;
  font-size: var(--bs-typography-font-size-xs);
}

.lane-badge.is-default {
  background: var(--bs-color-brand-primary);
}

.lane-expr {
  color: var(--bs-color-fg-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.lane-arrow {
  color: var(--bs-color-fg-muted);
  flex-shrink: 0;
}

.lane-target {
  color: var(--bs-color-fg-default);
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.lane-target.unset {
  color: var(--bs-color-semantic-danger);
  font-weight: 400;
}

.lane-del {
  margin-left: auto;
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  border: none;
  border-radius: var(--bs-radius-sm);
  background: transparent;
  color: var(--bs-color-fg-muted);
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
}

.lane-del:hover {
  background: var(--bs-color-semantic-danger-soft);
  color: var(--bs-color-semantic-danger);
}

.lane-add {
  align-self: flex-start;
}

.node-config {
  padding-right: var(--bs-space-1);
}

.approver-type-group {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
}

.field-tip {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
  line-height: 1.4;
  width: 100%;
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
  gap: var(--bs-space-2);
  padding: var(--bs-space-2);
  border: 1px dashed var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
}

.branch-row-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: var(--bs-typography-font-size-xs);
  font-weight: 600;
  color: var(--bs-color-fg-secondary);
}

.branch-expr-row {
  display: flex;
  gap: var(--bs-space-1);
}

.branch-field {
  flex: 1.2;
}

.branch-op {
  width: 76px;
  flex-shrink: 0;
}

.branch-value {
  flex: 1;
}

.drawer-footer {
  display: flex;
  justify-content: space-between;
}
</style>
