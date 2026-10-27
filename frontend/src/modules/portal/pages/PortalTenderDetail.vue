<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import StatusTag from '@/components/common/StatusTag.vue'
import BackButton from '@/components/common/BackButton.vue'
import {
  portalTenderDetail,
  portalRegisterTender,
  portalSubmitBid,
  downloadMyRegistrationAttachment,
  downloadMyBidProposal,
} from '@/api/portal'
import { getPortalToken } from '@/api/portalHttp'
import { useDeadline } from '../useDeadline'
import type { PortalTenderDetail } from '@/api/types'

defineOptions({ name: 'PortalTenderDetail' })

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const { deadlineText, isUrgent } = useDeadline()

const loading = ref(false)
const detail = ref<PortalTenderDetail | null>(null)
const loggedIn = ref(Boolean(getPortalToken()))

const tenderId = computed(() => Number(route.params.id))

function goLogin() {
  router.push({ path: '/portal/login', query: { redirect: route.fullPath } })
}

function goRegister() {
  router.push('/portal/register')
}

async function load() {
  loading.value = true
  try {
    detail.value = await portalTenderDetail(tenderId.value)
  } catch {
    detail.value = null
  } finally {
    loading.value = false
  }
}

onMounted(() => void load())

/* ---- 报名 ---- */
const regForm = reactive({ contactName: '', contactPhone: '', file: null as File | null })
const regSaving = ref(false)

function onRegFile(e: Event) {
  const input = e.target as HTMLInputElement
  regForm.file = input.files?.[0] ?? null
}

async function doRegister() {
  if (!detail.value) return
  regSaving.value = true
  try {
    const fd = new FormData()
    fd.append('contact_name', regForm.contactName)
    fd.append('contact_phone', regForm.contactPhone)
    if (regForm.file) fd.append('file', regForm.file)
    await portalRegisterTender(detail.value.id, fd)
    ElMessage.success(t('common.message.submitSuccess'))
    await load()
  } catch {
    /* portalHttp notifies */
  } finally {
    regSaving.value = false
  }
}

/* ---- 投标 ---- */
const bidForm = reactive({ price: null as number | null, comment: '', file: null as File | null })
const bidSaving = ref(false)

function onBidFile(e: Event) {
  const input = e.target as HTMLInputElement
  bidForm.file = input.files?.[0] ?? null
}

const canRegister = computed(
  () => detail.value?.status === 'published' && !detail.value.myRegistration,
)
const canBid = computed(
  () => detail.value?.status === 'published' && detail.value.myRegistration?.status === 'approved',
)

async function doBid() {
  if (!detail.value || !bidForm.price) return
  bidSaving.value = true
  try {
    const fd = new FormData()
    fd.append('price', String(bidForm.price))
    fd.append('comment', bidForm.comment)
    if (bidForm.file) fd.append('file', bidForm.file)
    await portalSubmitBid(detail.value.id, fd)
    ElMessage.success(t('common.message.submitSuccess'))
    await load()
  } catch {
    /* portalHttp notifies */
  } finally {
    bidSaving.value = false
  }
}

function fmtAmount(v: unknown) {
  const n = Number(v ?? 0)
  return Number.isFinite(n) && v !== null && v !== '' ? n.toLocaleString() : '-'
}
</script>

<template>
  <div v-loading="loading" class="portal-detail">
    <div class="detail-head">
      <h2 class="page-title">{{ detail?.name || '' }}</h2>
      <BackButton to="/portal/tenders" />
    </div>
    <template v-if="detail">
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item :label="t('portal.portal.tenderNo')">{{ detail.tenderNo }}</el-descriptions-item>
        <el-descriptions-item :label="t('portal.portal.status')">
          <StatusTag :status="detail.status" i18n-prefix="common.status" />
        </el-descriptions-item>
        <el-descriptions-item :label="t('portal.portal.tenderMethod')">
          {{ detail.tenderMethod === 'invite' ? t('portal.portal.methodInvite') : t('portal.portal.methodPublic') }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('portal.portal.budgetAmount')">{{ fmtAmount(detail.budgetAmount) }}</el-descriptions-item>
        <el-descriptions-item :label="t('portal.portal.regDeadline')">
          <span>{{ detail.regDeadline || '-' }}</span>
          <span
            v-if="detail.status === 'published' && deadlineText(detail.regDeadline)"
            class="deadline"
            :class="{ urgent: isUrgent(detail.regDeadline) }"
          >
            （{{ deadlineText(detail.regDeadline) }}）
          </span>
        </el-descriptions-item>
        <el-descriptions-item :label="t('portal.portal.bidDeadline')">
          <span>{{ detail.bidDeadline || '-' }}</span>
          <span
            v-if="detail.status === 'published' && deadlineText(detail.bidDeadline)"
            class="deadline"
            :class="{ urgent: isUrgent(detail.bidDeadline) }"
          >
            （{{ deadlineText(detail.bidDeadline) }}）
          </span>
        </el-descriptions-item>
        <el-descriptions-item :label="t('portal.portal.announcement')" :span="2">
          <span class="pre-wrap">{{ detail.announcement || '-' }}</span>
        </el-descriptions-item>
      </el-descriptions>

      <el-alert
        v-if="detail.status === 'awarded'"
        type="success"
        :closable="false"
        show-icon
        :title="`${t('portal.portal.winner')}: ${detail.winnerName} · ${t('portal.portal.winnerAmount')}: ${fmtAmount(detail.winnerAmount)}`"
      />

      <!-- 未登录：引导登录/注册（公告本身公开可见） -->
      <div v-if="!loggedIn" class="guide-card">
        <p class="guide-title">{{ t('portal.portal.loginGuideTitle') }}</p>
        <p class="muted">{{ t('portal.portal.loginGuideTip') }}</p>
        <div class="guide-actions">
          <el-button type="primary" @click="goLogin">{{ t('portal.portal.goLogin') }}</el-button>
          <el-button @click="goRegister">{{ t('portal.portal.goRegister') }}</el-button>
        </div>
      </div>

      <template v-else>
      <!-- 我的报名 -->
      <div class="section-title">{{ t('portal.portal.myRegistrations') }}</div>
      <template v-if="detail.myRegistration">
        <div class="info-row">
          <StatusTag :status="detail.myRegistration.status" i18n-prefix="common.status" />
          <span v-if="detail.myRegistration.reviewComment" class="muted">
            {{ t('portal.portal.reviewComment') }}: {{ detail.myRegistration.reviewComment }}
          </span>
          <el-button
            v-if="detail.myRegistration.qualificationName"
            link
            type="primary"
            @click="downloadMyRegistrationAttachment(detail.myRegistration.id)"
          >
            {{ detail.myRegistration.qualificationName }}
          </el-button>
        </div>
      </template>
      <el-form v-else-if="canRegister" class="action-form" label-width="90px">
        <el-form-item :label="t('portal.portal.contactName')">
          <el-input v-model="regForm.contactName" :maxlength="64" style="width: 220px" />
        </el-form-item>
        <el-form-item :label="t('portal.portal.phone')">
          <el-input v-model="regForm.contactPhone" :maxlength="32" style="width: 220px" />
        </el-form-item>
        <el-form-item :label="t('portal.portal.qualification')">
          <input type="file" accept=".pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png,.zip" @change="onRegFile" />
          <span class="muted file-tip">{{ t('portal.portal.fileTip') }}</span>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="regSaving" @click="doRegister">{{ t('portal.portal.submitRegister') }}</el-button>
        </el-form-item>
      </el-form>
      <div v-else class="muted">{{ t('portal.portal.regClosed') }}</div>

      <!-- 我的投标 -->
      <div class="section-title">{{ t('portal.portal.myBids') }}</div>
      <template v-if="detail.myBid">
        <div class="info-row">
          <span>{{ t('portal.portal.myPrice') }}: <b>{{ fmtAmount(detail.myBid.price) }}</b></span>
          <span class="muted">{{ detail.myBid.submitAt }}</span>
          <el-button
            v-if="detail.myBid.proposalName"
            link
            type="primary"
            @click="downloadMyBidProposal(detail.myBid.id)"
          >
            {{ detail.myBid.proposalName }}
          </el-button>
          <el-tag v-if="detail.myBid.isWinner" type="success" effect="dark" round>{{ t('portal.portal.isWinner') }}</el-tag>
          <el-tag v-else-if="detail.status === 'awarded'" type="info" round>{{ t('portal.portal.notWinner') }}</el-tag>
        </div>
        <div v-if="detail.myBid.comment" class="muted">{{ detail.myBid.comment }}</div>
      </template>
      <div v-else-if="!detail.myRegistration || detail.myRegistration.status !== 'approved'" class="muted">
        {{ t('portal.portal.needRegister') }}
      </div>
      <div v-else-if="detail.status !== 'published'" class="muted">{{ t('portal.portal.bidClosed') }}</div>

      <el-form v-if="canBid" class="action-form" label-width="90px">
        <el-form-item :label="t('portal.portal.price')" required>
          <el-input-number v-model="bidForm.price" :min="0.01" :precision="2" :controls="false" style="width: 220px" />
        </el-form-item>
        <el-form-item :label="t('portal.portal.bidComment')">
          <el-input v-model="bidForm.comment" :maxlength="500" style="width: 360px" />
        </el-form-item>
        <el-form-item :label="t('portal.portal.proposal')">
          <input type="file" accept=".pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png,.zip" @change="onBidFile" />
          <span class="muted file-tip">{{ t('portal.portal.fileTip') }}</span>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="bidSaving" :disabled="!bidForm.price" @click="doBid">
            {{ detail.myBid ? t('portal.portal.updateBid') : t('portal.portal.submitBid') }}
          </el-button>
        </el-form-item>
      </el-form>
      </template>
    </template>
  </div>
</template>

<style scoped>
.portal-detail {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-4);
}

.detail-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.page-title {
  font-size: var(--bs-typography-font-size-lg);
  font-weight: 600;
  color: var(--bs-color-fg-default);
  margin: 0;
}

.section-title {
  font-weight: 600;
  color: var(--bs-color-fg-default);
  margin-top: var(--bs-space-2);
}

.info-row {
  display: flex;
  align-items: center;
  gap: var(--bs-space-3);
  flex-wrap: wrap;
}

.action-form {
  max-width: 560px;
}

.muted {
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-sm);
}

.file-tip {
  margin-left: var(--bs-space-2);
}

.pre-wrap {
  white-space: pre-wrap;
}

.deadline {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.deadline.urgent {
  color: var(--bs-color-semantic-danger);
  font-weight: 600;
}

.guide-card {
  padding: var(--bs-space-5);
  border: 1px dashed var(--bs-color-border-default);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-bg-inset);
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
}

.guide-title {
  margin: 0;
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.guide-actions {
  display: flex;
  gap: var(--bs-space-2);
}
</style>
