<script setup lang="ts">
/** 外来人员自助登记（B2）：客户登记来访试验 / 跟踪支持人员，客户经理审核备案后生效。 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import StatusTag from '@/components/common/StatusTag.vue'
import ResponsiveTable from '@/components/common/ResponsiveTable.vue'
import type { ListColumn } from '@/components/list/types'
import { myPortalStaffs, portalRegisterStaff } from '@/api/portal'
import type { PortalStaff } from '@/api/types'

defineOptions({ name: 'PortalStaff' })

const { t } = useI18n()

const loading = ref(false)
const staffs = ref<PortalStaff[]>([])

const staffColumns: ListColumn[] = [
  { prop: 'name', labelKey: 'portal.portal.staff.name', width: 120 },
  { prop: 'staffType', labelKey: 'portal.portal.staff.typeLabel', width: 120 },
  { prop: 'position', labelKey: 'portal.portal.staff.position', width: 130 },
  { prop: 'phone', labelKey: 'portal.portal.staff.phone', width: 140 },
  { prop: 'plateNo', labelKey: 'portal.portal.staff.plateNo', width: 120 },
  { prop: 'planVisitDate', labelKey: 'portal.portal.staff.planVisitDate', width: 120 },
  { prop: 'ndaSigned', labelKey: 'portal.portal.staff.ndaSigned', width: 90, align: 'center' },
  { prop: 'status', labelKey: 'portal.portal.status', width: 110, align: 'center' },
  { prop: 'reviewComment', labelKey: 'portal.portal.reviewComment', minWidth: 140 },
]

/** 人员类型：试验人员 / 支持人员 / 见证专家 / 厂商工程师（与后端字典 partner_staff_type 对齐） */
const typeOptions = computed(() => [
  { label: t('portal.portal.staff.typeTester'), value: 'tester' },
  { label: t('portal.portal.staff.typeSupport'), value: 'support' },
  { label: t('portal.portal.staff.typeWitness'), value: 'witness' },
  { label: t('portal.portal.staff.typeVendor'), value: 'vendor' },
])

const form = ref<{
  name: string
  gender: string
  id_no: string
  position: string
  phone: string
  email: string
  plate_no: string
  staff_type: string
  visit_purpose: string
  plan_visit_date: string
  nda_signed: boolean
}>({
  name: '',
  gender: '',
  id_no: '',
  position: '',
  phone: '',
  email: '',
  plate_no: '',
  staff_type: 'tester',
  visit_purpose: '',
  plan_visit_date: '',
  nda_signed: false,
})

async function load() {
  loading.value = true
  try {
    const data = await myPortalStaffs()
    staffs.value = data.items ?? []
  } catch {
    /* portalHttp notifies */
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function submit() {
  const f = form.value
  if (!f.name.trim()) {
    ElMessage.warning(t('portal.portal.staff.nameRequired'))
    return
  }
  loading.value = true
  try {
    await portalRegisterStaff({
      name: f.name.trim(),
      gender: f.gender,
      idNo: f.id_no,
      position: f.position,
      phone: f.phone,
      email: f.email,
      plateNo: f.plate_no,
      staffType: f.staff_type,
      visitPurpose: f.visit_purpose,
      planVisitDate: f.plan_visit_date || null,
      ndaSigned: f.nda_signed,
    } as unknown as Partial<PortalStaff>)
    ElMessage.success(t('portal.portal.staff.submitSuccess'))
    form.value = {
      name: '',
      gender: '',
      id_no: '',
      position: '',
      phone: '',
      email: '',
      plate_no: '',
      staff_type: 'tester',
      visit_purpose: '',
      plan_visit_date: '',
      nda_signed: false,
    }
    await load()
  } catch {
    /* portalHttp notifies */
  } finally {
    loading.value = false
  }
}

function typeLabel(v: string) {
  return typeOptions.value.find((o) => o.value === v)?.label || v || '-'
}
</script>

<template>
  <div class="portal-staff">
    <h2 class="bs-page-title">{{ t('portal.portal.staff.title') }}</h2>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      :title="t('portal.portal.staff.tip')"
      class="staff-tip"
    />

    <el-form label-position="top" class="staff-form">
      <el-row :gutter="12">
        <el-col :xs="24" :sm="12">
          <el-form-item :label="t('portal.portal.staff.name')" required>
            <el-input v-model="form.name" :maxlength="64" />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="12">
          <el-form-item :label="t('portal.portal.staff.gender')">
            <el-select v-model="form.gender" style="width: 100%" clearable>
              <el-option :label="t('portal.portal.staff.genderMale')" value="male" />
              <el-option :label="t('portal.portal.staff.genderFemale')" value="female" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="12">
        <el-col :xs="24" :sm="12">
          <el-form-item :label="t('portal.portal.staff.position')">
            <el-input v-model="form.position" :maxlength="64" />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="12">
          <el-form-item :label="t('portal.portal.staff.phone')">
            <el-input v-model="form.phone" :maxlength="32" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="12">
        <el-col :xs="24" :sm="12">
          <el-form-item :label="t('portal.portal.staff.idNo')">
            <el-input v-model="form.id_no" :maxlength="64" />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="12">
          <el-form-item :label="t('portal.portal.staff.plateNo')">
            <el-input v-model="form.plate_no" :maxlength="32" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="12">
        <el-col :xs="24" :sm="12">
          <el-form-item :label="t('portal.portal.staff.typeLabel')">
            <el-select v-model="form.staff_type" style="width: 100%">
              <el-option v-for="o in typeOptions" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="12">
          <el-form-item :label="t('portal.portal.staff.planVisitDate')">
            <el-date-picker v-model="form.plan_visit_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item :label="t('portal.portal.staff.visitPurpose')">
        <el-input v-model="form.visit_purpose" :maxlength="255" />
      </el-form-item>
      <el-form-item :label="t('portal.portal.staff.ndaSigned')">
        <el-switch v-model="form.nda_signed" />
      </el-form-item>
      <el-button type="primary" :loading="loading" @click="submit">
        {{ t('portal.portal.staff.submit') }}
      </el-button>
    </el-form>

    <h3 class="bs-page-title staff-sub-title">{{ t('portal.portal.staff.myList') }}</h3>
    <ResponsiveTable
      v-loading="loading"
      :columns="staffColumns"
      :data="staffs as unknown as Record<string, unknown>[]"
      :show-pagination="false"
    >
      <template #cell="{ row, col }">
        <span v-if="col.prop === 'staffType'">{{ typeLabel(String(row.staffType)) }}</span>
        <span v-else-if="col.prop === 'ndaSigned'">
          {{ row.ndaSigned ? t('common.action.yes') : t('common.action.no') }}
        </span>
        <StatusTag
          v-else-if="col.prop === 'status'"
          :status="String(row.status)"
          i18n-prefix="portal.portal.staff.status"
        />
        <span v-else>{{ row[col.prop] ?? '-' }}</span>
      </template>
    </ResponsiveTable>
  </div>
</template>

<style scoped>
.portal-staff {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-4);
}

.staff-tip {
  margin-bottom: var(--bs-space-2);
}

.staff-form {
  display: flex;
  flex-direction: column;
  max-width: var(--bs-layout-form-max-width);
}

.staff-sub-title {
  margin-top: var(--bs-space-4);
}
</style>
