<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import StatusTag from '@/components/common/StatusTag.vue'
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
      <el-table-column :label="t('portal.portal.tenderName')" min-width="180">
        <template #default="{ row }">
          <el-button link type="primary" @click="router.push(`/portal/tenders/${row.tenderId}`)">
            {{ row.tenderName }}
          </el-button>
        </template>
      </el-table-column>
      <el-table-column :label="t('portal.portal.status')" width="100" align="center">
        <template #default="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="common.status" />
        </template>
      </el-table-column>
      <el-table-column :label="t('portal.portal.reviewComment')" prop="reviewComment" min-width="140">
        <template #default="{ row }">{{ row.reviewComment || '-' }}</template>
      </el-table-column>
      <el-table-column :label="t('portal.portal.bidDeadline')" width="180">
        <template #default="{ row }">
          <div>{{ row.bidDeadline || '-' }}</div>
          <div
            v-if="row.tenderStatus === 'published' && deadlineText(row.bidDeadline)"
            class="deadline"
            :class="{ urgent: isUrgent(row.bidDeadline) }"
          >
            {{ deadlineText(row.bidDeadline) }}
          </div>
        </template>
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
      <el-table-column :label="t('portal.portal.tenderName')" min-width="180">
        <template #default="{ row }">
          <el-button link type="primary" @click="router.push(`/portal/tenders/${row.tenderId}`)">
            {{ row.tenderName }}
          </el-button>
        </template>
      </el-table-column>
      <el-table-column :label="t('portal.portal.myPrice')" width="120" align="right">
        <template #default="{ row }">{{ fmtAmount(row.price) }}</template>
      </el-table-column>
      <el-table-column :label="t('portal.portal.bidDeadline')" width="180">
        <template #default="{ row }">
          <div>{{ row.bidDeadline || '-' }}</div>
          <div
            v-if="row.tenderStatus === 'published' && deadlineText(row.bidDeadline)"
            class="deadline"
            :class="{ urgent: isUrgent(row.bidDeadline) }"
          >
            {{ deadlineText(row.bidDeadline) }}
          </div>
        </template>
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

    <h2 class="page-title">{{ t('portal.portal.myResults') }}</h2>
    <el-table :data="results" border stripe>
      <el-table-column :label="t('portal.portal.tenderNo')" prop="tenderNo" width="150" />
      <el-table-column :label="t('portal.portal.tenderName')" min-width="180">
        <template #default="{ row }">
          <el-button link type="primary" @click="router.push(`/portal/tenders/${row.tenderId}`)">
            {{ row.tenderName }}
          </el-button>
        </template>
      </el-table-column>
      <el-table-column :label="t('portal.portal.myPrice')" width="120" align="right">
        <template #default="{ row }">{{ fmtAmount(row.price) }}</template>
      </el-table-column>
      <el-table-column :label="t('portal.portal.myResults')" width="140" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.isWinner" type="success" effect="dark" round>{{ t('portal.portal.isWinner') }}</el-tag>
          <el-tag v-else type="info" round>{{ t('portal.portal.notWinner') }}</el-tag>
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

.deadline {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.deadline.urgent {
  color: var(--bs-color-semantic-danger);
  font-weight: 600;
}
</style>
