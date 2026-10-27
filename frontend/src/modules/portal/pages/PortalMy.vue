<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import StatusTag from '@/components/common/StatusTag.vue'
import { myPortalRegistrations, myPortalBids, downloadMyRegistrationAttachment, downloadMyBidProposal } from '@/api/portal'
import type { PortalBid, PortalRegistration } from '@/api/types'

defineOptions({ name: 'PortalMy' })

const { t } = useI18n()

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

function fmtAmount(v: unknown) {
  const n = Number(v ?? 0)
  return Number.isFinite(n) && v !== null && v !== '' ? n.toLocaleString() : '-'
}
</script>

<template>
  <div v-loading="loading" class="portal-my">
    <h2 class="page-title">{{ t('portal.portal.myRegistrations') }}</h2>
    <el-table :data="registrations" border stripe>
      <el-table-column :label="t('portal.portal.tenderNo')" prop="tenderNo" width="150" />
      <el-table-column :label="t('portal.portal.tenderName')" prop="tenderName" min-width="200" />
      <el-table-column :label="t('portal.portal.status')" width="100" align="center">
        <template #default="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="common.status" />
        </template>
      </el-table-column>
      <el-table-column :label="t('portal.portal.reviewComment')" prop="reviewComment" min-width="140">
        <template #default="{ row }">{{ row.reviewComment || '-' }}</template>
      </el-table-column>
      <el-table-column :label="t('portal.portal.qualification')" width="140" align="center">
        <template #default="{ row }">
          <el-button v-if="row.qualificationName" link type="primary" @click="downloadMyRegistrationAttachment(row.id)">
            {{ t('portal.portal.download') }}
          </el-button>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column :label="t('portal.portal.createTime')" prop="createTime" width="160" />
      <template #empty>{{ t('portal.portal.empty') }}</template>
    </el-table>

    <h2 class="page-title">{{ t('portal.portal.myBids') }}</h2>
    <el-table :data="bids" border stripe>
      <el-table-column :label="t('portal.portal.tenderNo')" prop="tenderNo" width="150" />
      <el-table-column :label="t('portal.portal.tenderName')" prop="tenderName" min-width="200" />
      <el-table-column :label="t('portal.portal.myPrice')" width="120" align="right">
        <template #default="{ row }">{{ fmtAmount(row.price) }}</template>
      </el-table-column>
      <el-table-column :label="t('portal.portal.proposal')" width="140" align="center">
        <template #default="{ row }">
          <el-button v-if="row.proposalName" link type="primary" @click="downloadMyBidProposal(row.id)">
            {{ t('portal.portal.download') }}
          </el-button>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column :label="t('portal.portal.status')" width="120" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.isWinner" type="success" effect="dark" round>{{ t('portal.portal.isWinner') }}</el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column :label="t('portal.portal.submitAt')" prop="submitAt" width="160" />
      <template #empty>{{ t('portal.portal.empty') }}</template>
    </el-table>
  </div>
</template>

<style scoped>
.portal-my {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-4);
}

.page-title {
  font-size: var(--bs-typography-font-size-lg);
  font-weight: 600;
  color: var(--bs-color-fg-default);
  margin: 0;
}
</style>
