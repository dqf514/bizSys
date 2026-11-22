<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import {
  listPortalHosts,
  listPortalZones,
  myPortalVisits,
  portalCancelVisit,
  portalCreateVisit,
} from '@/api/portal'
import StatusTag from '@/components/common/StatusTag.vue'
import type { PortalHostOption, PortalVisit, PortalZoneOption } from '@/api/types'

defineOptions({ name: 'PortalVisits' })

const { t } = useI18n()
const router = useRouter()

const visits = ref<PortalVisit[]>([])
const hosts = ref<PortalHostOption[]>([])
const zones = ref<PortalZoneOption[]>([])
const loading = ref(false)
const submitting = ref(false)
const dialogVisible = ref(false)

const form = reactive({
  visitorName: '',
  visitorCompany: '',
  phone: '',
  idNo: '',
  plateNo: '',
  hostUserId: undefined as number | undefined,
  zoneIds: [] as number[],
  purpose: '',
  planStart: '',
  planEnd: '',
  escortNames: '',
  ndaSigned: false,
  remark: '',
})

const rules = {
  visitorName: [{ required: true, message: t('portal.portal.visits.field.visitorNameRequired'), trigger: 'blur' }],
  hostUserId: [{ required: true, message: t('portal.portal.visits.field.hostRequired'), trigger: 'change' }],
  zoneIds: [{ required: true, message: t('portal.portal.visits.field.zonesRequired'), trigger: 'change' }],
}

const formRef = ref()

/** 敏感区域必须先确认保密协议 */
const needNda = computed(() =>
  zones.value.some((z) => form.zoneIds.includes(z.id) && z.needNda),
)

const canCancel = (v: PortalVisit) => v.status === 'pending' || v.status === 'approving'

async function load() {
  loading.value = true
  try {
    const res = await myPortalVisits()
    visits.value = res.items || []
  } finally {
    loading.value = false
  }
}

async function loadOptions() {
  const [h, z] = await Promise.all([listPortalHosts(), listPortalZones()])
  hosts.value = h.items || []
  zones.value = z.items || []
}

function openDialog() {
  dialogVisible.value = true
}

function resetForm() {
  Object.assign(form, {
    visitorName: '',
    visitorCompany: '',
    phone: '',
    idNo: '',
    plateNo: '',
    hostUserId: undefined,
    zoneIds: [],
    purpose: '',
    planStart: '',
    planEnd: '',
    escortNames: '',
    ndaSigned: false,
    remark: '',
  })
  formRef.value?.clearValidate()
}

async function submit() {
  const ok = await formRef.value?.validate().catch(() => false)
  if (!ok) return
  if (needNda.value && !form.ndaSigned) {
    ElMessage.warning(t('portal.portal.visits.field.ndaRequired'))
    return
  }
  submitting.value = true
  try {
    await portalCreateVisit({
      visitorName: form.visitorName,
      visitorCompany: form.visitorCompany,
      phone: form.phone,
      idNo: form.idNo,
      plateNo: form.plateNo,
      hostUserId: form.hostUserId as number,
      zoneIds: form.zoneIds,
      purpose: form.purpose,
      planStart: form.planStart,
      planEnd: form.planEnd,
      escortNames: form.escortNames,
      ndaSigned: form.ndaSigned,
      remark: form.remark,
    })
    ElMessage.success(t('portal.portal.visits.submitSuccess'))
    dialogVisible.value = false
    resetForm()
    await load()
  } finally {
    submitting.value = false
  }
}

async function cancelVisit(v: PortalVisit) {
  await portalCancelVisit(v.id)
  ElMessage.success(t('portal.portal.visits.cancelSuccess'))
  await load()
}

onMounted(async () => {
  await Promise.all([load(), loadOptions()])
})
</script>

<template>
  <div class="bs-page portal-visits">
    <div class="bs-page-header">
      <h2 class="bs-page-title">{{ t('portal.portal.visits.title') }}</h2>
      <div class="bs-page-actions">
        <el-button type="primary" @click="openDialog">{{ t('portal.portal.visits.newBooking') }}</el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" :title="t('portal.portal.visits.tip')" show-icon />

    <div v-loading="loading" class="portal-visit-list">
      <el-empty v-if="!loading && !visits.length" :description="t('portal.portal.empty')" />
      <article
        v-for="v in visits"
        :key="v.id"
        class="portal-visit-card"
        @click="router.push(`/portal/visits/${v.id}`)"
      >
        <header class="portal-visit-head">
          <span class="portal-visit-name">{{ v.visitorName }}</span>
          <StatusTag status="v.status" i18n-prefix="portal.portal.visits.status" />
        </header>
        <div class="portal-visit-meta">
          <span>{{ t('portal.portal.visits.field.host') }}：{{ v.hostName || '-' }}</span>
          <span>{{ v.visitNo }}</span>
        </div>
        <div class="portal-visit-meta">
          <span>{{ t('portal.portal.visits.field.plan') }}：{{ v.planStart }} ~ {{ v.planEnd }}</span>
        </div>
        <div v-if="v.zoneNames?.length" class="portal-visit-meta">
          <span>{{ t('portal.portal.visits.field.zones') }}：{{ v.zoneNames.join('、') }}</span>
        </div>
        <footer class="portal-visit-actions">
          <el-button link type="primary" @click.stop="router.push(`/portal/visits/${v.id}`)">
            {{ t('portal.portal.visits.viewDetail') }}
          </el-button>
          <el-button
            v-if="canCancel(v)"
            link
            type="danger"
            @click.stop="cancelVisit(v)"
          >
            {{ t('portal.portal.visits.cancelAction') }}
          </el-button>
        </footer>
      </article>
    </div>

    <el-dialog
      v-model="dialogVisible"
      :title="t('portal.portal.visits.form.title')"
      width="var(--bs-layout-dialog-md)"
      destroy-on-close
      @closed="resetForm"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <el-form-item :label="t('portal.portal.visits.field.visitorName')" prop="visitorName">
          <el-input v-model="form.visitorName" :placeholder="t('portal.portal.visits.field.visitorName')" />
        </el-form-item>
        <el-form-item :label="t('portal.portal.visits.field.visitorCompany')" prop="visitorCompany">
          <el-input v-model="form.visitorCompany" />
        </el-form-item>
        <el-form-item :label="t('portal.portal.visits.field.phone')" prop="phone">
          <el-input v-model="form.phone" inputmode="tel" />
        </el-form-item>
        <el-form-item :label="t('portal.portal.visits.field.idNo')" prop="idNo">
          <el-input v-model="form.idNo" />
        </el-form-item>
        <el-form-item :label="t('portal.portal.visits.field.plateNo')" prop="plateNo">
          <el-input v-model="form.plateNo" />
        </el-form-item>
        <el-form-item :label="t('portal.portal.visits.field.host')" prop="hostUserId">
          <el-select v-model="form.hostUserId" filterable :placeholder="t('portal.portal.visits.field.host')">
            <el-option
              v-for="h in hosts"
              :key="h.id"
              :label="h.deptName ? `${h.name}（${h.deptName}）` : h.name"
              :value="h.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('portal.portal.visits.field.zones')" prop="zoneIds">
          <el-select
            v-model="form.zoneIds"
            multiple
            collapse-tags
            :placeholder="t('portal.portal.visits.field.zones')"
          >
            <el-option
              v-for="z in zones"
              :key="z.id"
              :label="z.name"
              :value="z.id"
            >
              <span>{{ z.name }}</span>
              <span class="portal-zone-hint">{{ z.zoneTypeText }}</span>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item :label="t('portal.portal.visits.field.purpose')" prop="purpose">
          <el-input v-model="form.purpose" type="textarea" :rows="2" />
        </el-form-item>
        <div class="portal-form-row">
          <el-form-item :label="t('portal.portal.visits.field.planStart')" prop="planStart">
            <el-date-picker
              v-model="form.planStart"
              type="datetime"
              value-format="YYYY-MM-DD HH:mm:ss"
              :placeholder="t('portal.portal.visits.field.planStart')"
            />
          </el-form-item>
          <el-form-item :label="t('portal.portal.visits.field.planEnd')" prop="planEnd">
            <el-date-picker
              v-model="form.planEnd"
              type="datetime"
              value-format="YYYY-MM-DD HH:mm:ss"
              :placeholder="t('portal.portal.visits.field.planEnd')"
            />
          </el-form-item>
        </div>
        <el-form-item :label="t('portal.portal.visits.field.escort')" prop="escortNames">
          <el-input v-model="form.escortNames" />
        </el-form-item>
        <el-form-item :label="t('portal.portal.visits.field.remark')" prop="remark">
          <el-input v-model="form.remark" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item v-if="needNda" prop="ndaSigned">
          <el-checkbox v-model="form.ndaSigned">
            {{ t('portal.portal.visits.field.nda') }}
          </el-checkbox>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ t('common.action.cancel') }}</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">
          {{ t('portal.portal.visits.form.submit') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.portal-visits {
  gap: var(--bs-space-4);
}

.portal-visit-list {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-3);
}

.portal-visit-card {
  background: var(--bs-color-bg-surface);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  padding: var(--bs-space-4);
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
  cursor: pointer;
}

.portal-visit-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--bs-space-2);
}

.portal-visit-name {
  font-size: var(--bs-typography-font-size-lg);
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.portal-visit-meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bs-space-3);
  font-size: var(--bs-typography-font-size-sm);
  color: var(--bs-color-fg-secondary);
}

.portal-visit-actions {
  display: flex;
  gap: var(--bs-space-2);
  justify-content: flex-end;
}

.portal-zone-hint {
  float: right;
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs);
  margin-left: var(--bs-space-3);
}

.portal-form-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--bs-space-3);
}

@media (max-width: 767px) {
  .portal-form-row {
    grid-template-columns: 1fr;
    gap: 0;
  }

  .portal-visit-card {
    padding: var(--bs-space-3);
  }
}
</style>
