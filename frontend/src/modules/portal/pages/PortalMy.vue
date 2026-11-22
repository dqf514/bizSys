<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import StatusTag from '@/components/common/StatusTag.vue'
import ResponsiveTable from '@/components/common/ResponsiveTable.vue'
import type { ListColumn } from '@/components/list/types'
import { myPortalRegistrations, myPortalBids, downloadMyRegistrationAttachment, downloadMyBidProposal } from '@/api/portal'
import { useDeadline } from '../useDeadline'
import type { PortalBid, PortalRegistration } from '@/api/types'

defineOptions({ name: 'PortalMy' })

const { t } = useI18n()
const router = useRouter()
const { deadlineText, isUrgent } = useDeadline()

const loading = ref(false)
const registrations = ref<PortalRegistration[]>([])
const bids = ref<PortalBid[]>([])

onMounted(async () => {
  loading.value = true
  try {
    const [r, b] = await Promise.all([myPortalRegistrations(), myPortalBids()])
    registrations.value = r.items ?? []
    bids.value = b.items ?? []
  } catch {
    /* portalHttp notifies */
  } finally {
    loading.value = false
  }
})

/** 中标结果：已定标项目中的本人投标（中标/未中标） */
const results = computed(() => bids.value.filter((b) => b.tenderStatus === 'awarded'))

const regColumns: ListColumn[] = [
  { prop: 'tenderNo', labelKey: 'portal.portal.tenderNo', width: 150 },
  { prop: 'tenderName', labelKey: 'portal.portal.tenderName', minWidth: 180 },
  { prop: 'status', labelKey: 'portal.portal.status', width: 100, align: 'center' },
  { prop: 'reviewComment', labelKey: 'portal.portal.reviewComment', minWidth: 140 },
  { prop: 'bidDeadline', labelKey: 'portal.portal.bidDeadline', width: 180 },
  { prop: 'qualificationName', labelKey: 'portal.portal.qualification', width: 140, align: 'center' },
  { prop: 'createTime', labelKey: 'portal.portal.createTime', width: 160 },
]

const bidColumns: ListColumn[] = [
  { prop: 'tenderNo', labelKey: 'portal.portal.tenderNo', width: 150 },
  { prop: 'tenderName', labelKey: 'portal.portal.tenderName', minWidth: 180 },
  { prop: 'price', labelKey: 'portal.portal.myPrice', width: 120, align: 'right' },
  { prop: 'bidDeadline', labelKey: 'portal.portal.bidDeadline', width: 180 },
  { prop: 'proposalName', labelKey: 'portal.portal.proposal', width: 140, align: 'center' },
  { prop: 'isWinner', labelKey: 'portal.portal.status', width: 120, align: 'center' },
  { prop: 'submitAt', labelKey: 'portal.portal.submitAt', width: 160 },
]

const resultColumns: ListColumn[] = [
  { prop: 'tenderNo', labelKey: 'portal.portal.tenderNo', width: 150 },
  { prop: 'tenderName', labelKey: 'portal.portal.tenderName', minWidth: 180 },
  { prop: 'price', labelKey: 'portal.portal.myPrice', width: 120, align: 'right' },
  { prop: 'isWinner', labelKey: 'portal.portal.myResults', width: 140, align: 'center' },
  { prop: 'submitAt', labelKey: 'portal.portal.submitAt', width: 160 },
]

function fmtAmount(v: unknown) {
  const n = Number(v ?? 0)
  return Number.isFinite(n) && v !== null && v !== '' ? n.toLocaleString() : '-'
}
</script>

<template>
  <div v-loading="loading" class="portal-my">
    <h2 class="bs-page-title">{{ t('portal.portal.myRegistrations') }}</h2>
    <ResponsiveTable
      :columns="regColumns"
      :data="registrations as unknown as Record<string, unknown>[]"
      :show-pagination="false"
    >
      <template #cell="{ row, col }">
        <el-button
          v-if="col.prop === 'tenderName'"
          link
          type="primary"
          @click="router.push(`/portal/tenders/${row.tenderId}`)"
        >
          {{ row.tenderName }}
        </el-button>
        <StatusTag v-else-if="col.prop === 'status'" :status="String(row.status)" i18n-prefix="common.status" />
        <div v-else-if="col.prop === 'bidDeadline'">
          <div>{{ row.bidDeadline || '-' }}</div>
          <div
            v-if="row.tenderStatus === 'published' && deadlineText(row.bidDeadline)"
            class="deadline"
            :class="{ urgent: isUrgent(row.bidDeadline) }"
          >
            {{ deadlineText(row.bidDeadline) }}
          </div>
        </div>
        <el-button
          v-else-if="col.prop === 'qualificationName'"
          :disabled="!row.qualificationName"
          link
          type="primary"
          @click="downloadMyRegistrationAttachment(row.id)"
        >
          {{ row.qualificationName ? t('portal.portal.download') : '-' }}
        </el-button>
        <span v-else>{{ row[col.prop] ?? '-' }}</span>
      </template>
    </ResponsiveTable>

    <h2 class="bs-page-title">{{ t('portal.portal.myBids') }}</h2>
    <ResponsiveTable
      :columns="bidColumns"
      :data="bids as unknown as Record<string, unknown>[]"
      :show-pagination="false"
    >
      <template #cell="{ row, col }">
        <el-button
          v-if="col.prop === 'tenderName'"
          link
          type="primary"
          @click="router.push(`/portal/tenders/${row.tenderId}`)"
        >
          {{ row.tenderName }}
        </el-button>
        <span v-else-if="col.prop === 'price'">{{ fmtAmount(row.price) }}</span>
        <div v-else-if="col.prop === 'bidDeadline'">
          <div>{{ row.bidDeadline || '-' }}</div>
          <div
            v-if="row.tenderStatus === 'published' && deadlineText(row.bidDeadline)"
            class="deadline"
            :class="{ urgent: isUrgent(row.bidDeadline) }"
          >
            {{ deadlineText(row.bidDeadline) }}
          </div>
        </div>
        <el-button
          v-else-if="col.prop === 'proposalName'"
          :disabled="!row.proposalName"
          link
          type="primary"
          @click="downloadMyBidProposal(row.id)"
        >
          {{ row.proposalName ? t('portal.portal.download') : '-' }}
        </el-button>
        <el-tag v-else-if="col.prop === 'isWinner'" type="success" effect="dark" round>
          {{ t('portal.portal.isWinner') }}
        </el-tag>
        <span v-else>{{ row[col.prop] ?? '-' }}</span>
      </template>
    </ResponsiveTable>

    <h2 class="bs-page-title">{{ t('portal.portal.myResults') }}</h2>
    <ResponsiveTable
      :columns="resultColumns"
      :data="results as unknown as Record<string, unknown>[]"
      :show-pagination="false"
    >
      <template #cell="{ row, col }">
        <el-button
          v-if="col.prop === 'tenderName'"
          link
          type="primary"
          @click="router.push(`/portal/tenders/${row.tenderId}`)"
        >
          {{ row.tenderName }}
        </el-button>
        <span v-else-if="col.prop === 'price'">{{ fmtAmount(row.price) }}</span>
        <template v-else-if="col.prop === 'isWinner'">
          <el-tag v-if="row.isWinner" type="success" effect="dark" round>{{ t('portal.portal.isWinner') }}</el-tag>
          <el-tag v-else type="info" round>{{ t('portal.portal.notWinner') }}</el-tag>
        </template>
        <span v-else>{{ row[col.prop] ?? '-' }}</span>
      </template>
    </ResponsiveTable>
  </div>
</template>

<style scoped>
.portal-my {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-4);
}

.deadline {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.deadline.urgent {
  color: var(--bs-color-semantic-danger);
  font-weight: 600;
}
</style>
