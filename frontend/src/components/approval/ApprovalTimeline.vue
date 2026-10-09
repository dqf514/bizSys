<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { TimelineRecord } from '@/api/types'

const props = defineProps<{
  records: TimelineRecord[]
  loading?: boolean
}>()

const { t } = useI18n()

const actionKey: Record<string, string> = {
  start: 'approval.approval.timelineStart',
  agree: 'approval.approval.timelineAgree',
  reject: 'approval.approval.timelineReject',
  withdraw: 'approval.approval.timelineWithdraw',
  add_sign: 'approval.approval.timelineAddSign',
  transfer: 'approval.approval.timelineTransfer',
}

function actionLabel(action: string) {
  const key = actionKey[action]
  return key ? t(key) : action
}
</script>

<template>
  <div v-loading="props.loading" class="approval-timeline">
    <el-timeline v-if="props.records.length">
      <el-timeline-item
        v-for="(rec, i) in props.records"
        :key="i"
        :timestamp="rec.at"
        :type="rec.action === 'reject' ? 'danger' : rec.action === 'agree' ? 'success' : 'primary'"
        placement="top"
      >
        <div class="tl-head">
          <span class="tl-action">{{ actionLabel(rec.action) }}</span>
          <span class="tl-operator">{{ rec.operatorName }}</span>
          <span v-if="rec.nodeName" class="tl-node">{{ rec.nodeName }}</span>
        </div>
        <div v-if="rec.comment" class="tl-comment">{{ rec.comment }}</div>
      </el-timeline-item>
    </el-timeline>
    <el-empty v-else :description="t('common.table.empty')" :image-size="60" />
  </div>
</template>

<style scoped>
.approval-timeline {
  min-height: 80px;
}

.tl-head {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  font-size: var(--bs-typography-font-size-sm);
}

.tl-action {
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.tl-operator {
  color: var(--bs-color-fg-secondary);
}

.tl-node {
  padding: 0 6px;
  border-radius: var(--bs-radius-full);
  background: var(--bs-color-fill-light);
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs);
}

.tl-comment {
  margin-top: 4px;
  padding: 6px 8px;
  border-radius: var(--bs-radius-sm);
  background: var(--bs-color-fill-lighter);
  color: var(--bs-color-fg-secondary);
  font-size: var(--bs-typography-font-size-sm);
}
</style>
