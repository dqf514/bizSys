<script setup lang="ts">
/** 竖链流程设计器：节点卡片（复刻 TPCworkflow FlowNodeCard 形态）。
 * 彩色头部 = 节点类型；正文 = 节点名 + 配置摘要。点击卡片打开配置，× 删除。
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Close } from '@element-plus/icons-vue'
import { isOrgApproverType, type FlowNodeRow } from './flowModel'

const props = defineProps<{ node: FlowNodeRow }>()
const emit = defineEmits<{ (e: 'edit'): void; (e: 'remove'): void }>()

const { t } = useI18n()

const typeLabel = computed(() => t(`admin.flow.nodeType.${props.node.nodeType}`))

const summary = computed(() => {
  const n = props.node
  if (n.nodeType === 'condition') {
    return t('admin.flow.branchCount', { n: n.branches?.length ?? 0 })
  }
  const who = n.approverName || String(n.approverValue || '') || t(`admin.flow.approverTypeShort.${n.approverType}`)
  if (n.nodeType === 'cc') return who
  const sign = t(`admin.flow.signMode.${n.signMode}`)
  if (n.approverType === 'SUPERVISOR_CHAIN') {
    return `${who} · ${t('admin.flow.chainLevelsShort', { n: n.chainLevels ?? 0 })} · ${sign}`
  }
  if (isOrgApproverType(n.approverType)) return `${who} · ${sign}`
  return `${who} · ${sign}`
})
</script>

<template>
  <div class="chain-node-card" :class="`type-${node.nodeType}`" @click="emit('edit')">
    <div class="card-header">
      <span class="card-type">{{ typeLabel }}</span>
      <el-popconfirm
        :title="t('admin.flow.deleteNodeConfirm')"
        :confirm-button-text="t('common.action.confirm')"
        :cancel-button-text="t('common.action.cancel')"
        width="200"
        @confirm="emit('remove')"
      >
        <template #reference>
          <button type="button" class="card-del" @click.stop>
            <el-icon><Close /></el-icon>
          </button>
        </template>
      </el-popconfirm>
    </div>
    <div class="card-body">
      <div class="card-title">{{ node.nodeName || '-' }}</div>
      <div class="card-sub">{{ summary }}</div>
    </div>
  </div>
</template>

<style scoped>
.chain-node-card {
  width: 220px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  border-radius: var(--bs-radius-lg);
  overflow: hidden;
  border: 1px solid var(--bs-color-border-subtle);
  background: var(--bs-color-bg-surface);
  box-shadow: var(--bs-shadow-elevation1, 0 1px 4px rgba(15, 23, 42, 0.06));
  cursor: pointer;
  transition:
    box-shadow 0.2s,
    border-color 0.2s;
}

.chain-node-card:hover {
  border-color: var(--bs-color-brand-primary);
  box-shadow: var(--bs-shadow-elevation2);
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 6px 4px var(--bs-space-3);
  color: #fff;
  font-size: var(--bs-typography-font-size-xs);
  font-weight: 600;
}

.type-approval .card-header {
  background: var(--bs-color-brand-primary);
}

.type-condition .card-header {
  background: var(--bs-color-semantic-warning);
}

.type-cc .card-header {
  background: var(--bs-color-semantic-success);
}

.card-del {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border: none;
  border-radius: var(--bs-radius-sm);
  background: transparent;
  color: rgba(255, 255, 255, 0.85);
  cursor: pointer;
  font-size: 12px;
}

.card-del:hover {
  background: rgba(255, 255, 255, 0.2);
  color: #fff;
}

.card-body {
  padding: var(--bs-space-2) var(--bs-space-3);
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-height: 54px;
  justify-content: center;
}

.card-title {
  font-size: var(--bs-typography-font-size-sm);
  font-weight: 600;
  color: var(--bs-color-fg-default);
  line-height: 1.35;
  word-break: break-word;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-sub {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
