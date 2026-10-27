<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import StatusTag from '@/components/common/StatusTag.vue'
import { listPortalTenders } from '@/api/portal'
import type { PortalTender } from '@/api/types'

defineOptions({ name: 'PortalTenderList' })

const { t } = useI18n()
const router = useRouter()

const loading = ref(false)
const items = ref<PortalTender[]>([])

onMounted(async () => {
  loading.value = true
  try {
    const data = await listPortalTenders()
    items.value = data.items ?? []
  } catch {
    items.value = []
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
  <div v-loading="loading" class="portal-tenders">
    <h2 class="page-title">{{ t('portal.portal.tenders') }}</h2>
    <el-table :data="items" border stripe>
      <el-table-column :label="t('portal.portal.tenderNo')" prop="tenderNo" width="150" />
      <el-table-column :label="t('portal.portal.name')" prop="name" min-width="200" />
      <el-table-column :label="t('portal.portal.tenderMethod')" width="110" align="center">
        <template #default="{ row }">
          {{ row.tenderMethod === 'invite' ? t('portal.portal.methodInvite') : t('portal.portal.methodPublic') }}
        </template>
      </el-table-column>
      <el-table-column :label="t('portal.portal.budgetAmount')" width="120" align="right">
        <template #default="{ row }">{{ fmtAmount(row.budgetAmount) }}</template>
      </el-table-column>
      <el-table-column :label="t('portal.portal.regDeadline')" prop="regDeadline" width="160" />
      <el-table-column :label="t('portal.portal.bidDeadline')" prop="bidDeadline" width="160" />
      <el-table-column :label="t('portal.portal.status')" width="110" align="center">
        <template #default="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="common.status" />
        </template>
      </el-table-column>
      <el-table-column :label="t('portal.portal.my')" width="120" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.isWinner" type="success" size="small" effect="dark" round>{{ t('portal.portal.isWinner') }}</el-tag>
          <StatusTag v-else-if="row.myRegistrationStatus" :status="String(row.myRegistrationStatus)" i18n-prefix="common.status" />
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column :label="t('common.action.operate')" width="110" fixed="right" align="center">
        <template #default="{ row }">
          <el-button link type="primary" @click="router.push(`/portal/tenders/${row.id}`)">
            {{ t('portal.portal.viewDetail') }}
          </el-button>
        </template>
      </el-table-column>
      <template #empty>{{ t('portal.portal.empty') }}</template>
    </el-table>
  </div>
</template>

<style scoped>
.portal-tenders {
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
