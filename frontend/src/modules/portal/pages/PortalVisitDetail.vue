<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import {
  portalCancelVisit,
  portalVisitCheckIn,
  portalVisitCheckOut,
  portalVisitCredential,
  portalVisitDetail,
  portalVisitQr,
} from '@/api/portal'
import BackButton from '@/components/common/BackButton.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import type { PortalVisitDetail } from '@/api/types'

defineOptions({ name: 'PortalVisitDetail' })

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const visit = ref<PortalVisitDetail | null>(null)
const loading = ref(false)
const qrUrl = ref('')
const credential = ref<{ credentialNo: string; code: string; expireAt: string; zoneNames: string[] } | null>(
  null,
)

const visitId = computed(() => Number(route.params.id))
const canCancel = computed(() => visit.value?.status === 'pending' || visit.value?.status === 'approving')
const canCheckIn = computed(() => visit.value?.status === 'approved')
const canCheckOut = computed(() => visit.value?.status === 'visiting')

async function load() {
  loading.value = true
  try {
    visit.value = await portalVisitDetail(visitId.value)
    await loadQr()
  } finally {
    loading.value = false
  }
}

async function loadQr() {
  if (visit.value?.status !== 'approved' && visit.value?.status !== 'visiting') return
  try {
    credential.value = await portalVisitCredential(visitId.value)
    const blob = await portalVisitQr(visitId.value)
    if (qrUrl.value) URL.revokeObjectURL(qrUrl.value)
    qrUrl.value = URL.createObjectURL(blob)
  } catch {
    /* 凭证尚未下发或已过期 */
  }
}

async function doCheckIn() {
  await portalVisitCheckIn(visitId.value)
  ElMessage.success(t('portal.portal.visits.checkinSuccess'))
  await load()
}

async function doCheckOut() {
  await portalVisitCheckOut(visitId.value)
  ElMessage.success(t('portal.portal.visits.checkoutSuccess'))
  await load()
}

async function doCancel() {
  await portalCancelVisit(visitId.value)
  ElMessage.success(t('portal.portal.visits.cancelSuccess'))
  await load()
}

onMounted(load)
onBeforeUnmount(() => {
  if (qrUrl.value) URL.revokeObjectURL(qrUrl.value)
})
</script>

<template>
  <div v-loading="loading" class="bs-page bs-page--narrow portal-visit-detail">
    <div class="bs-page-header">
      <h2 class="bs-page-title">{{ t('portal.portal.visits.detail.title') }}</h2>
      <div class="bs-page-actions">
        <BackButton @click="router.back()" />
      </div>
    </div>

    <div v-if="visit" class="bs-page-card portal-detail-card">
      <div class="portal-detail-row">
        <span class="portal-detail-label">{{ t('portal.portal.visits.field.visitorName') }}</span>
        <span class="portal-detail-value">{{ visit.visitorName }}</span>
      </div>
      <div class="portal-detail-row">
        <span class="portal-detail-label">{{ t('portal.portal.visits.field.visitorCompany') }}</span>
        <span class="portal-detail-value">{{ visit.visitorCompany || '-' }}</span>
      </div>
      <div class="portal-detail-row">
        <span class="portal-detail-label">{{ t('portal.portal.visits.field.host') }}</span>
        <span class="portal-detail-value">{{ visit.hostName || '-' }}</span>
      </div>
      <div class="portal-detail-row">
        <span class="portal-detail-label">{{ t('portal.portal.visits.field.plan') }}</span>
        <span class="portal-detail-value">{{ visit.planStart }} ~ {{ visit.planEnd }}</span>
      </div>
      <div class="portal-detail-row">
        <span class="portal-detail-label">{{ t('portal.portal.visits.field.zones') }}</span>
        <span class="portal-detail-value">{{ visit.zoneNames?.join('、') || '-' }}</span>
      </div>
      <div class="portal-detail-row">
        <span class="portal-detail-label">{{ t('portal.portal.visits.field.purpose') }}</span>
        <span class="portal-detail-value">{{ visit.purpose || '-' }}</span>
      </div>
      <div class="portal-detail-row">
        <span class="portal-detail-label">{{ t('portal.portal.status') }}</span>
        <span class="portal-detail-value">
          <StatusTag :status="visit.status" i18n-prefix="portal.portal.visits.status" />
        </span>
      </div>
      <div class="portal-detail-row">
        <span class="portal-detail-label">{{ t('portal.portal.visits.field.visitNo') }}</span>
        <span class="portal-detail-value">{{ visit.visitNo }}</span>
      </div>
    </div>

    <div v-if="qrUrl" class="bs-page-card portal-qr-card">
      <div class="portal-qr-title">{{ t('portal.portal.visits.qr.title') }}</div>
      <img :src="qrUrl" class="portal-qr-image" :alt="t('portal.portal.visits.qr.title')" />
      <div class="portal-qr-meta">
        <span>{{ t('portal.portal.visits.field.credentialNo') }}：{{ credential?.credentialNo }}</span>
        <span>{{ t('portal.portal.visits.field.expireAt') }}：{{ credential?.expireAt }}</span>
      </div>
    </div>

    <div v-if="visit?.timeline?.length" class="bs-page-card">
      <div class="portal-section-title">{{ t('portal.portal.visits.timeline.title') }}</div>
      <el-timeline>
        <el-timeline-item
          v-for="(item, idx) in visit.timeline"
          :key="idx"
          :timestamp="item.at"
          placement="top"
        >
          <div class="portal-timeline-node">{{ item.nodeName }}</div>
          <div class="portal-timeline-meta">
            <span>{{ item.operatorName }}</span>
            <span v-if="item.comment">{{ item.comment }}</span>
          </div>
        </el-timeline-item>
      </el-timeline>
    </div>

    <div class="portal-detail-actions">
      <el-button
        v-if="canCheckIn"
        type="primary"
        size="large"
        class="portal-action-btn"
        @click="doCheckIn"
      >
        {{ t('portal.portal.visits.checkin') }}
      </el-button>
      <el-button
        v-if="canCheckOut"
        type="primary"
        size="large"
        class="portal-action-btn"
        @click="doCheckOut"
      >
        {{ t('portal.portal.visits.checkout') }}
      </el-button>
      <el-button
        v-if="canCancel"
        size="large"
        class="portal-action-btn"
        @click="doCancel"
      >
        {{ t('portal.portal.visits.cancelAction') }}
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.portal-visit-detail {
  gap: var(--bs-space-4);
}

.portal-detail-card {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
}

.portal-detail-row {
  display: flex;
  gap: var(--bs-space-3);
  align-items: baseline;
}

.portal-detail-label {
  flex: none;
  width: 92px;
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-sm);
}

.portal-detail-value {
  color: var(--bs-color-fg-default);
  word-break: break-all;
}

.portal-qr-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--bs-space-3);
}

.portal-qr-title {
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.portal-qr-image {
  width: 200px;
  height: 200px;
  background: var(--bs-color-bg-surface);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
}

.portal-qr-meta {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--bs-space-1);
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.portal-section-title {
  font-weight: 600;
  color: var(--bs-color-fg-default);
  margin-bottom: var(--bs-space-3);
}

.portal-timeline-node {
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.portal-timeline-meta {
  display: flex;
  gap: var(--bs-space-3);
  font-size: var(--bs-typography-font-size-sm);
  color: var(--bs-color-fg-secondary);
}

.portal-detail-actions {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
}

.portal-action-btn {
  width: 100%;
  min-height: 44px;
}

@media (max-width: 767px) {
  .portal-detail-label {
    width: 76px;
  }
}
</style>
