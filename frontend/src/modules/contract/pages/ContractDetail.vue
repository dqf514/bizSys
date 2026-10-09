<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import StatusTag from '@/components/common/StatusTag.vue'
import ApprovalTimeline from '@/components/approval/ApprovalTimeline.vue'
import { getContract, downloadAttachment } from '@/api/contract'
import { getTimeline } from '@/api/approval'
import type { Attachment, Contract, TimelineRecord } from '@/api/types'

defineOptions({ name: 'ContractDetail' })

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const detail = ref<Contract | null>(null)
const attachments = ref<Attachment[]>([])
const records = ref<TimelineRecord[]>([])
const loading = ref(false)
const timelineLoading = ref(false)
const activeTab = ref('basic')

async function load() {
  const id = Number(route.params.id)
  if (!id) return
  loading.value = true
  try {
    const data = await getContract(id)
    detail.value = data
    attachments.value = data.attachments ?? []
    if (data.flowInstanceId || data.status === 'approving' || data.status === 'approved') {
      timelineLoading.value = true
      try {
        const tl = await getTimeline('contract', id)
        records.value = tl.records ?? []
      } catch {
        records.value = []
      } finally {
        timelineLoading.value = false
      }
    }
  } catch {
    detail.value = null
  } finally {
    loading.value = false
  }
}

onMounted(() => void load())
</script>

<template>
  <div class="contract-detail" v-loading="loading">
    <div class="detail-header">
      <h2 class="detail-title">
        {{ detail?.name || t('contract.contract.detail') }}
        <StatusTag v-if="detail" :status="detail.status" i18n-prefix="contract.contract.status" />
      </h2>
      <el-button @click="router.push('/contract/contracts')">{{ t('common.action.back') }}</el-button>
    </div>

    <el-tabs v-model="activeTab">
      <el-tab-pane :label="t('contract.contract.tabBasic')" name="basic">
        <el-descriptions v-if="detail" :column="2" border>
          <el-descriptions-item :label="t('contract.contract.contractNo')">{{ detail.contractNo }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.name')">{{ detail.name }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.customerName')">{{ detail.customerName }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.contractType')">{{ detail.contractType || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.amount')">{{ detail.amount }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.subjectType')">{{ detail.subjectType || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.startDate')">{{ detail.startDate }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.endDate')">{{ detail.endDate }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.payCycle')">{{ detail.payCycle || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.delivery')">{{ detail.delivery || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.sealType')">{{ detail.sealType || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.handlerName')">{{ detail.handlerName || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.frameworkNo')">{{ detail.frameworkNo || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.paymentOrg')">{{ detail.paymentOrg || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.remark')" :span="2">{{ detail.remark || '-' }}</el-descriptions-item>
        </el-descriptions>
      </el-tab-pane>

      <el-tab-pane :label="t('contract.contract.tabAttachments')" name="attachments">
        <div class="file-list">
          <div v-for="f in attachments" :key="String(f.id)" class="file-row">
            <span>{{ f.fileName }}</span>
            <el-button link type="primary" @click="downloadAttachment(f.id, f.fileName)">
              {{ t('common.action.download') }}
            </el-button>
          </div>
          <el-empty v-if="!attachments.length" :description="t('common.table.empty')" :image-size="60" />
        </div>
      </el-tab-pane>

      <el-tab-pane :label="t('contract.contract.tabTimeline')" name="timeline">
        <ApprovalTimeline :records="records" :loading="timelineLoading" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.contract-detail {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-3);
  padding: var(--bs-space-4);
  height: 100%;
  overflow: auto;
  background: var(--bs-color-bg-surface);
}

.detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.detail-title {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  font-size: var(--bs-typography-font-size-lg);
  font-weight: 600;
}

.file-list {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
}

.file-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-sm);
}
</style>
