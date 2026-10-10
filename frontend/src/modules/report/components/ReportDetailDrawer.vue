<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import StatusTag from '@/components/common/StatusTag.vue'
import ApprovalTimeline from '@/components/approval/ApprovalTimeline.vue'
import { getReport } from '@/api/report'
import type { ReportDetail } from '@/api/types'

defineOptions({ name: 'ReportDetailDrawer' })

const props = defineProps<{
  modelValue: boolean
  reportId: number | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
}>()

const { t } = useI18n()

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

const loading = ref(false)
const detail = ref<ReportDetail | null>(null)

async function load(id: number) {
  loading.value = true
  try {
    detail.value = await getReport(id)
  } catch {
    detail.value = null
  } finally {
    loading.value = false
  }
}

watch(
  [() => props.modelValue, () => props.reportId],
  ([v, id]) => {
    detail.value = null
    if (v && id) void load(id)
  },
  { immediate: true },
)
</script>

<template>
  <el-drawer v-model="visible" :title="t('report.report.detail')" size="640px" append-to-body>
    <div v-loading="loading" class="drawer-body">
      <template v-if="detail">
        <el-descriptions :column="2" border>
          <el-descriptions-item :label="t('report.report.reportNo')">{{ detail.reportNo }}</el-descriptions-item>
          <el-descriptions-item :label="t('report.report.taskNo')">{{ detail.taskNo }}</el-descriptions-item>
          <el-descriptions-item :label="t('report.report.contractNo')">{{ detail.contractNo || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('report.report.itemName')">{{ detail.itemName }}</el-descriptions-item>
          <el-descriptions-item :label="t('report.report.customerName')">{{ detail.customerName }}</el-descriptions-item>
          <el-descriptions-item :label="t('report.report.fileName')">{{ detail.fileName }}</el-descriptions-item>
          <el-descriptions-item :label="t('common.form.status')">
            <StatusTag :status="detail.status" i18n-prefix="report.report.status" />
          </el-descriptions-item>
          <el-descriptions-item :label="t('report.report.createBy')">{{ detail.createBy || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('report.report.createTime')">{{ detail.createTime || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('report.report.sealBy')">{{ detail.sealBy || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('report.report.sealTime')">{{ detail.sealTime || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('report.report.remark')" :span="2">{{ detail.remark || '-' }}</el-descriptions-item>
        </el-descriptions>

        <div class="section-title">{{ t('report.report.timeline') }}</div>
        <ApprovalTimeline :records="detail.timeline ?? []" />
      </template>
    </div>
  </el-drawer>
</template>

<style scoped>
.drawer-body {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-3);
}

.section-title {
  font-weight: 600;
  color: var(--bs-color-fg-default);
}
</style>
