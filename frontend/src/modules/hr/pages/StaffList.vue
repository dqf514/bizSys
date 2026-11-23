<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance } from 'element-plus'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import ExportButton from '@/components/list/ExportButton.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { useListPage } from '@/composables/useListPage'
import {
  createEmployee,
  createEmployeeControl,
  deleteEmployee,
  employeeCounts,
  exportEmployees,
  getEmployee,
  getEmployeeIdNo,
  getOrgOptions,
  listEmployees,
  updateEmployee,
  type EmployeeControlPayload,
  type EmployeePayload,
} from '@/api/hr'
import type { HrEmployee, HrEmployeeDetail } from '@/api/types'

defineOptions({ name: 'StaffList' })

const { t } = useI18n()

/* ---------------- 枚举 ---------------- */

const EMPLOY_TYPES = ['labor', 'engage', 'part_time', 'intern']
const EMPLOY_STATUSES = ['probation', 'regular', 'idle', 'resigned', 'retired']
const CONTROL_TYPES = ['blacklist', 'whitelist']
const GENDERS = ['male', 'female']
const ID_TYPES = ['id_card', 'passport', 'other']
const EDUCATIONS = ['college', 'bachelor', 'master', 'doctor', 'high_school', 'other']

const employTypeOptions = computed(() =>
  EMPLOY_TYPES.map((v) => ({ label: t(`hr.staff.employTypeType.${v}`), value: v })),
)
const employStatusOptions = computed(() =>
  EMPLOY_STATUSES.map((v) => ({ label: t(`hr.staff.employStatusType.${v}`), value: v })),
)
const controlTypeOptions = computed(() =>
  CONTROL_TYPES.map((v) => ({ label: t(`hr.staff.controlTypeType.${v}`), value: v })),
)
const genderOptions = computed(() => GENDERS.map((v) => ({ label: t(`hr.staff.genderType.${v}`), value: v })))
const idTypeOptions = computed(() => ID_TYPES.map((v) => ({ label: t(`hr.staff.idTypeType.${v}`), value: v })))
const educationOptions = computed(() =>
  EDUCATIONS.map((v) => ({ label: t(`hr.staff.educationType.${v}`), value: v })),
)

function employTypeLabel(v: unknown) {
  const key = String(v ?? '')
  return EMPLOY_TYPES.includes(key) ? t(`hr.staff.employTypeType.${key}`) : key || '-'
}

function employStatusLabel(v: unknown) {
  const key = String(v ?? '')
  return EMPLOY_STATUSES.includes(key) ? t(`hr.staff.employStatusType.${key}`) : key || '-'
}

function genderLabel(v: unknown) {
  const key = String(v ?? '')
  return GENDERS.includes(key) ? t(`hr.staff.genderType.${key}`) : '-'
}

/* ---------------- 选项 ---------------- */

const deptOptions = ref<{ value: number; label: string }[]>([])
const positionOptions = ref<{ value: number; label: string }[]>([])

async function loadOptions() {
  try {
    const opts = await getOrgOptions()
    deptOptions.value = (opts?.depts ?? []).map((d) => ({ value: d.value, label: d.label }))
    positionOptions.value = (opts?.positions ?? []).map((p) => ({ value: p.value, label: p.label }))
  } catch {
    deptOptions.value = []
    positionOptions.value = []
  }
}

onMounted(() => {
  void loadOptions()
})

/* ---------------- 检索 ---------------- */

const searchModel = ref<Record<string, any>>({ q: '', employType: '', deptId: '', positionId: '' })
const searchFields = computed<SearchField[]>(() => [
  { key: 'q', labelKey: 'hr.staff.keyword', placeholderKey: 'common.form.placeholderSearch', width: 220 },
  { key: 'employType', labelKey: 'hr.staff.employType', type: 'select', width: 140, options: employTypeOptions.value },
  { key: 'deptId', labelKey: 'hr.staff.deptName', type: 'select', width: 170, options: deptOptions.value },
  { key: 'positionId', labelKey: 'hr.staff.positionName', type: 'select', width: 170, options: positionOptions.value },
])

/* ---------------- 状态页签（在职状态） ---------------- */

const statusTabs = ref<StatusTabItem[]>([
  { value: 'all', labelKey: 'common.action.all', count: 0 },
  ...EMPLOY_STATUSES.map((s) => ({ value: s, labelKey: `hr.staff.employStatusType.${s}`, count: 0 })),
])

async function loadCounts() {
  try {
    const data = (await employeeCounts()) ?? {}
    for (const tab of statusTabs.value) tab.count = data[tab.value] ?? 0
  } catch {
    /* counts optional */
  }
}

onMounted(() => {
  void loadCounts()
})

/** 在职状态页签走 `filters[employ_status]`（模型 status 列是记录有效性，不是业务维度） */
function buildParams(params: Record<string, unknown>) {
  const status = String(params.status ?? 'all')
  return {
    page: Number(params.page ?? 1),
    size: Number(params.size ?? 20),
    q: searchModel.value.q || undefined,
    filters: {
      employ_type: searchModel.value.employType || undefined,
      employ_status: status !== 'all' ? status : undefined,
      dept_id: searchModel.value.deptId || undefined,
      position_id: searchModel.value.positionId || undefined,
    },
  }
}

const list = useListPage<HrEmployee>({
  fetch: async (params) => {
    const data = await listEmployees(buildParams(params))
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  exportFn: (params) => exportEmployees(buildParams(params)),
  defaultStatus: 'all',
  onLoaded: () => {
    void loadCounts()
  },
})

/* ---------------- 列 ---------------- */

const columns: ListColumn[] = [
  { prop: 'employeeNo', labelKey: 'hr.staff.employeeNo', width: 110, fixed: 'left', sortable: 'employee_no' },
  { prop: 'name', labelKey: 'hr.staff.name', width: 110, sortable: 'name' },
  { prop: 'employTypeText', labelKey: 'hr.staff.employType', width: 100 },
  { prop: 'employStatusText', labelKey: 'hr.staff.employStatus', width: 90, sortable: 'employ_status' },
  { prop: 'deptName', labelKey: 'hr.staff.deptName', width: 150 },
  { prop: 'positionName', labelKey: 'hr.staff.positionName', width: 150 },
  { prop: 'gender', labelKey: 'hr.staff.gender', width: 70 },
  { prop: 'mobile', labelKey: 'hr.staff.mobile', width: 120 },
  { prop: 'idNo', labelKey: 'hr.staff.idNo', width: 190 },
  { prop: 'hireDate', labelKey: 'hr.staff.hireDate', width: 110, sortable: 'hire_date' },
  { prop: 'remark', labelKey: 'common.form.remark', minWidth: 140 },
]

/* ---------------- 行操作 ---------------- */

function rowActions(): ActionItem[] {
  return [
    { key: 'detail', tip: 'common.action.detail' },
    { key: 'edit', tip: 'common.action.edit', perm: 'hr:staff:edit' },
    { key: 'control', tip: 'hr.staff.control', perm: 'hr:staff:edit' },
    { key: 'idno', tip: 'hr.staff.viewIdNo', perm: 'hr:staff:idno' },
    { key: 'delete', tip: 'common.action.delete', perm: 'hr:staff:edit' },
  ]
}

function onRowAction(key: string, row: HrEmployee) {
  if (key === 'detail') void openDetail(row.id)
  else if (key === 'edit') openEdit(row)
  else if (key === 'control') openControl(row)
  else if (key === 'idno') void showIdNo(row)
  else if (key === 'delete') void doDelete(row)
}

async function doDelete(row: HrEmployee) {
  try {
    await ElMessageBox.confirm(t('hr.staff.deleteConfirm'), t('common.action.delete'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteEmployee(row.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

/* ---------------- 档案表单 ---------------- */

const dialogVisible = ref(false)
const dialogTitle = ref('')
const formRef = ref<FormInstance>()
const saving = ref(false)
const editingId = ref<number | null>(null)

const form = reactive({
  employeeNo: '',
  name: '',
  idNo: '',
  idType: 'id_card',
  gender: '',
  birthDate: null as string | null,
  education: '',
  major: '',
  mobile: '',
  email: '',
  employType: 'labor',
  employStatus: 'probation',
  deptId: null as number | null,
  positionId: null as number | null,
  hireDate: null as string | null,
  leaveDate: null as string | null,
  contractNo: '',
  contractStart: null as string | null,
  contractEnd: null as string | null,
  emergencyContact: '',
  emergencyMobile: '',
  remark: '',
})

function resetForm() {
  Object.assign(form, {
    employeeNo: '',
    name: '',
    idNo: '',
    idType: 'id_card',
    gender: '',
    birthDate: null,
    education: '',
    major: '',
    mobile: '',
    email: '',
    employType: 'labor',
    employStatus: 'probation',
    deptId: null,
    positionId: null,
    hireDate: null,
    leaveDate: null,
    contractNo: '',
    contractStart: null,
    contractEnd: null,
    emergencyContact: '',
    emergencyMobile: '',
    remark: '',
  })
}

function openCreate() {
  editingId.value = null
  dialogTitle.value = t('hr.staff.create')
  resetForm()
  dialogVisible.value = true
}

function openEdit(row: HrEmployee) {
  editingId.value = row.id
  dialogTitle.value = t('hr.staff.edit')
  Object.assign(form, {
    employeeNo: row.employeeNo || '',
    name: row.name || '',
    idNo: '',
    idType: row.idType || 'id_card',
    gender: row.gender || '',
    birthDate: row.birthDate || null,
    education: row.education || '',
    major: row.major || '',
    mobile: row.mobile || '',
    email: row.email || '',
    employType: row.employType || 'labor',
    employStatus: row.employStatus || 'probation',
    deptId: row.deptId ?? null,
    positionId: row.positionId ?? null,
    hireDate: row.hireDate || null,
    leaveDate: row.leaveDate || null,
    contractNo: row.contractNo || '',
    contractStart: row.contractStart || null,
    contractEnd: row.contractEnd || null,
    emergencyContact: row.emergencyContact || '',
    emergencyMobile: row.emergencyMobile || '',
    remark: row.remark || '',
  })
  dialogVisible.value = true
}

async function save() {
  if (!formRef.value) return
  const ok = await formRef.value.validate().catch(() => false)
  if (!ok) return
  saving.value = true
  try {
    const payload: EmployeePayload = {
      employeeNo: form.employeeNo.trim(),
      name: form.name.trim(),
      idNo: form.idNo.trim(),
      idType: form.idType,
      gender: form.gender,
      birthDate: form.birthDate || null,
      education: form.education,
      major: form.major,
      mobile: form.mobile,
      email: form.email,
      employType: form.employType,
      employStatus: form.employStatus,
      deptId: form.deptId,
      positionId: form.positionId,
      hireDate: form.hireDate || null,
      leaveDate: form.leaveDate || null,
      contractNo: form.contractNo,
      contractStart: form.contractStart || null,
      contractEnd: form.contractEnd || null,
      emergencyContact: form.emergencyContact,
      emergencyMobile: form.emergencyMobile,
      remark: form.remark,
    }
    if (editingId.value) await updateEmployee(editingId.value, payload)
    else await createEmployee(payload)
    ElMessage.success(t('common.message.saveSuccess'))
    dialogVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  } finally {
    saving.value = false
  }
}

/* ---------------- 名单管控 ---------------- */

const controlVisible = ref(false)
const controlSaving = ref(false)
const controlTarget = ref<HrEmployee | null>(null)
const controlForm = reactive({
  controlType: 'blacklist',
  reason: '',
  effectiveFrom: null as string | null,
  effectiveTo: null as string | null,
  remark: '',
})

function openControl(row: HrEmployee) {
  controlTarget.value = row
  Object.assign(controlForm, {
    controlType: 'blacklist',
    reason: '',
    effectiveFrom: null,
    effectiveTo: null,
    remark: '',
  })
  controlVisible.value = true
}

async function saveControl() {
  if (!controlTarget.value) return
  if (!controlForm.reason.trim()) {
    ElMessage.warning(t('hr.staff.controlReason'))
    return
  }
  controlSaving.value = true
  try {
    const payload: EmployeeControlPayload = {
      controlType: controlForm.controlType,
      reason: controlForm.reason.trim(),
      effectiveFrom: controlForm.effectiveFrom || null,
      effectiveTo: controlForm.effectiveTo || null,
      status: 'enabled',
      remark: controlForm.remark,
    }
    await createEmployeeControl(controlTarget.value.id, payload)
    ElMessage.success(t('common.message.saveSuccess'))
    controlVisible.value = false
    list.refresh()
    if (detailVisible.value && detail.value?.id === controlTarget.value.id) void openDetail(detail.value.id)
  } catch {
    /* http notifies */
  } finally {
    controlSaving.value = false
  }
}

/* ---------------- 证件号明文 ---------------- */

const idNoVisible = ref(false)
const idNoPlain = ref('')
const idNoMasked = ref('')

async function showIdNo(row: HrEmployee) {
  try {
    const data = await getEmployeeIdNo(row.id)
    idNoPlain.value = data?.idNo || ''
    idNoMasked.value = data?.masked || ''
    idNoVisible.value = true
  } catch {
    /* http notifies */
  }
}

/* ---------------- 详情抽屉 ---------------- */

const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref<HrEmployeeDetail | null>(null)

async function openDetail(id: number) {
  detailVisible.value = true
  detailLoading.value = true
  try {
    detail.value = await getEmployee(id)
  } catch {
    detail.value = null
  } finally {
    detailLoading.value = false
  }
}

function timelineLabel(item: { kind: string; eventType: string }) {
  if (item.kind === 'org') return t('hr.employment.eventLabel.other')
  const map: Record<string, string> = {
    create: 'hr.employment.eventLabel.create',
    update: 'hr.employment.eventLabel.update',
    submit: 'hr.employment.eventLabel.submit',
    approve: 'hr.employment.eventLabel.approve',
    reject: 'hr.employment.eventLabel.reject',
    withdraw: 'hr.employment.eventLabel.withdraw',
    effect: 'hr.employment.eventLabel.effect',
  }
  return t(map[item.eventType] ?? 'hr.employment.eventLabel.other')
}
</script>

<template>
  <ListPage :title="t('hr.staff.title')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'hr:staff:create'" type="primary" @click="openCreate">
        {{ t('hr.staff.create') }}
      </el-button>
      <ExportButton v-permission="'hr:staff:export'" :export-fn="() => list.exportList()" />
    </template>

    <template #searchBar>
      <SearchBar
        v-model="searchModel"
        :fields="searchFields"
        @search="list.search()"
        @reset="searchModel = { q: '', employType: '', deptId: '', positionId: '' }; list.reset()"
      />
    </template>

    <template #statusTabs>
      <StatusTabs
        :tabs="statusTabs"
        :model-value="String(list.query.status)"
        @update:model-value="list.setStatus($event)"
      />
    </template>

    <template #table>
      <ListTable
        :columns="columns"
        :data="list.items.value as unknown as Record<string, unknown>[]"
        :loading="list.loading.value"
        :total="list.total.value"
        :page="Number(list.query.page)"
        :size="Number(list.query.size)"
        row-key="id"
        @update:page="list.setPage"
        @update:size="list.setSize"
        @sort-change="list.onSortChange"
      >
        <template #employeeNo="{ row }">
          <el-button link type="primary" @click="openDetail(row.id)">{{ row.employeeNo }}</el-button>
        </template>
        <template #employTypeText="{ row }">{{ employTypeLabel(row.employType) }}</template>
        <template #employStatusText="{ row }">{{ employStatusLabel(row.employStatus) }}</template>
        <template #gender="{ row }">{{ genderLabel(row.gender) }}</template>
        <template #extraColumns>
          <el-table-column
            :label="t('common.action.operate')"
            width="190"
            fixed="right"
            align="center"
            header-align="center"
          >
            <template #default="{ row }">
              <ActionBar
                :actions="rowActions()"
                @select="(k) => onRowAction(k, row as unknown as HrEmployee)"
              />
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <!-- 新建 / 编辑档案 -->
  <el-dialog v-model="dialogVisible" :title="dialogTitle" width="var(--bs-layout-dialog-lg)" append-to-body>
    <el-alert :title="t('hr.staff.idNoTip')" type="info" :closable="false" show-icon />
    <el-form ref="formRef" :model="form" label-width="110px" class="staff-form">
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item
            :label="t('hr.staff.employeeNo')"
            prop="employeeNo"
            :rules="[{ required: true, message: t('common.form.required') }]"
          >
            <el-input v-model="form.employeeNo" :maxlength="32" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item
            :label="t('hr.staff.name')"
            prop="name"
            :rules="[{ required: true, message: t('common.form.required') }]"
          >
            <el-input v-model="form.name" :maxlength="64" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('hr.staff.idType')">
            <el-select v-model="form.idType" style="width: 100%">
              <el-option v-for="o in idTypeOptions" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('hr.staff.idNo')">
            <el-input v-model="form.idNo" :maxlength="64" placeholder="----" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('hr.staff.gender')">
            <el-select v-model="form.gender" clearable style="width: 100%">
              <el-option v-for="o in genderOptions" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('hr.staff.birthDate')">
            <el-date-picker v-model="form.birthDate" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('hr.staff.education')">
            <el-select v-model="form.education" clearable style="width: 100%">
              <el-option v-for="o in educationOptions" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('hr.staff.major')">
            <el-input v-model="form.major" :maxlength="64" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('hr.staff.mobile')">
            <el-input v-model="form.mobile" :maxlength="32" inputmode="tel" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('hr.staff.email')">
            <el-input v-model="form.email" :maxlength="128" inputmode="email" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('hr.staff.employType')">
            <el-select v-model="form.employType" style="width: 100%">
              <el-option v-for="o in employTypeOptions" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('hr.staff.employStatus')">
            <el-select v-model="form.employStatus" style="width: 100%">
              <el-option v-for="o in employStatusOptions" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('hr.staff.deptName')">
            <el-select v-model="form.deptId" clearable filterable style="width: 100%">
              <el-option v-for="o in deptOptions" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('hr.staff.positionName')">
            <el-select v-model="form.positionId" clearable filterable style="width: 100%">
              <el-option v-for="o in positionOptions" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('hr.staff.hireDate')">
            <el-date-picker v-model="form.hireDate" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('hr.staff.contractEnd')">
            <el-date-picker v-model="form.contractEnd" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('hr.staff.contractNo')">
            <el-input v-model="form.contractNo" :maxlength="64" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('hr.staff.emergencyContact')">
            <el-input v-model="form.emergencyContact" :maxlength="64" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('hr.staff.emergencyMobile')">
            <el-input v-model="form.emergencyMobile" :maxlength="32" inputmode="tel" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item :label="t('common.form.remark')">
        <el-input v-model="form.remark" type="textarea" :rows="2" :maxlength="500" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="saving" @click="save">{{ t('common.action.save') }}</el-button>
    </template>
  </el-dialog>

  <!-- 名单管控 -->
  <el-dialog v-model="controlVisible" :title="t('hr.staff.control')" width="var(--bs-layout-dialog-md)" append-to-body>
    <el-alert :title="t('hr.staff.controlTip')" type="info" :closable="false" show-icon />
    <el-form :model="controlForm" label-width="110px" class="staff-form">
      <el-form-item :label="t('hr.staff.controlType')">
        <el-select v-model="controlForm.controlType" style="width: 100%">
          <el-option
            v-for="o in controlTypeOptions"
            :key="o.value"
            :label="o.label"
            :value="o.value"
          />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('hr.staff.controlReason')">
        <el-input v-model="controlForm.reason" type="textarea" :rows="2" :maxlength="500" />
      </el-form-item>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item :label="t('hr.staff.controlFrom')">
            <el-date-picker
              v-model="controlForm.effectiveFrom"
              type="date"
              value-format="YYYY-MM-DD"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('hr.staff.controlTo')">
            <el-date-picker
              v-model="controlForm.effectiveTo"
              type="date"
              value-format="YYYY-MM-DD"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item :label="t('common.form.remark')">
        <el-input v-model="controlForm.remark" type="textarea" :rows="2" :maxlength="500" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="controlVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="controlSaving" @click="saveControl">
        {{ t('common.action.save') }}
      </el-button>
    </template>
  </el-dialog>

  <!-- 证件号明文 -->
  <el-dialog v-model="idNoVisible" :title="t('hr.staff.viewIdNo')" width="var(--bs-layout-dialog-xs)" append-to-body>
    <el-alert :title="t('hr.staff.idNoTip')" type="warning" :closable="false" show-icon />
    <p class="idno-plain">{{ idNoPlain || t('hr.staff.idNoEmpty') }}</p>
    <p class="idno-mask">{{ idNoMasked }}</p>
    <template #footer>
      <el-button @click="idNoVisible = false">{{ t('common.action.close') }}</el-button>
    </template>
  </el-dialog>

  <!-- 档案详情 -->
  <el-drawer v-model="detailVisible" size="var(--bs-layout-drawer-lg)">
    <template #header>
      <div class="drawer-header">
        <span class="drawer-title">{{ detail?.name || t('hr.staff.detail') }}</span>
        <StatusTag
          v-if="detail"
          :status="detail.employStatus"
          i18n-prefix="hr.staff.employStatusType"
        />
      </div>
    </template>
    <div v-loading="detailLoading" class="drawer-body">
      <template v-if="detail">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item :label="t('hr.staff.employeeNo')">
            {{ detail.employeeNo || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('hr.staff.userAccount')">
            {{ detail.userName || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('hr.staff.idNo')">
            {{ detail.idNo || t('hr.staff.idNoEmpty') }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('hr.staff.employType')">
            {{ employTypeLabel(detail.employType) }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('hr.staff.deptName')">
            {{ detail.deptName || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('hr.staff.positionName')">
            {{ detail.positionName || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('hr.staff.gender')">
            {{ genderLabel(detail.gender) }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('hr.staff.education')">
            {{ detail.education || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('hr.staff.mobile')">
            {{ detail.mobile || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('hr.staff.email')">
            {{ detail.email || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('hr.staff.hireDate')">
            {{ detail.hireDate || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('hr.staff.leaveDate')">
            {{ detail.leaveDate || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('hr.staff.contractNo')">
            {{ detail.contractNo || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('hr.staff.contractEnd')">
            {{ detail.contractEnd || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('hr.staff.emergencyContact')">
            {{ detail.emergencyContact || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('hr.staff.emergencyMobile')">
            {{ detail.emergencyMobile || '-' }}
          </el-descriptions-item>
        </el-descriptions>

        <!-- 名单管控 -->
        <section v-if="detail.controls?.length" class="drawer-section">
          <h4 class="section-title">{{ t('hr.staff.controls') }}</h4>
          <el-table :data="detail.controls" size="small" border>
            <el-table-column :label="t('hr.staff.controlType')" prop="controlTypeText" width="100" />
            <el-table-column :label="t('hr.staff.controlReason')" prop="reason" min-width="180" />
            <el-table-column :label="t('hr.staff.hireDate')" prop="effectiveFrom" width="110" />
            <el-table-column :label="t('hr.staff.leaveDate')" prop="effectiveTo" width="110" />
          </el-table>
        </section>

        <!-- 任职 -->
        <section class="drawer-section">
          <h4 class="section-title">{{ t('hr.staff.memberships') }}</h4>
          <el-table v-if="detail.memberships?.length" :data="detail.memberships" size="small" border>
            <el-table-column :label="t('hr.staff.deptName')" prop="deptName" min-width="140" />
            <el-table-column :label="t('common.form.status')" width="140">
              <template #default="{ row }">
                <el-tag v-if="row.isPrimary" size="small" type="primary">
                  {{ t('hr.staff.membershipPrimary') }}
                </el-tag>
                <el-tag v-if="row.isLeader" size="small" type="success">
                  {{ t('hr.staff.membershipLeader') }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-else :description="t('hr.staff.timelineEmpty')" :image-size="60" />
        </section>

        <!-- 授权 / 代理 / 人事事务 -->
        <section class="drawer-section">
          <h4 class="section-title">{{ t('hr.staff.authorizations') }}</h4>
          <el-table v-if="detail.authorizations?.length" :data="detail.authorizations" size="small" border>
            <el-table-column :label="t('hr.staff.employeeNo')" prop="authNo" width="140" />
            <el-table-column :label="t('hr.staff.positionName')" prop="authTypeText" width="120" />
            <el-table-column :label="t('common.form.status')" prop="statusText" width="100" />
          </el-table>
          <el-empty v-else :description="t('hr.staff.timelineEmpty')" :image-size="60" />
        </section>

        <section class="drawer-section">
          <h4 class="section-title">{{ t('hr.staff.delegates') }}</h4>
          <el-table v-if="detail.delegates?.length" :data="detail.delegates" size="small" border>
            <el-table-column :label="t('hr.delegate.principal')" prop="principalName" width="120" />
            <el-table-column :label="t('hr.delegate.agent')" prop="agentName" width="120" />
            <el-table-column :label="t('hr.delegate.scope')" prop="scope" width="100" />
            <el-table-column :label="t('common.form.status')" prop="status" width="100" />
          </el-table>
          <el-empty v-else :description="t('hr.staff.timelineEmpty')" :image-size="60" />
        </section>

        <section class="drawer-section">
          <h4 class="section-title">{{ t('hr.staff.employments') }}</h4>
          <el-table v-if="detail.employments?.length" :data="detail.employments" size="small" border>
            <el-table-column :label="t('hr.employment.empNo')" prop="empNo" width="140" />
            <el-table-column :label="t('hr.employment.eventType')" prop="eventType" width="100" />
            <el-table-column :label="t('hr.employment.effectiveDate')" prop="effectiveDate" width="110" />
            <el-table-column :label="t('common.form.status')" prop="status" width="100" />
          </el-table>
          <el-empty v-else :description="t('hr.staff.timelineEmpty')" :image-size="60" />
        </section>

        <!-- 变更轨迹 -->
        <section class="drawer-section">
          <h4 class="section-title">{{ t('hr.staff.timeline') }}</h4>
          <el-timeline v-if="detail.timeline?.length" class="staff-timeline">
            <el-timeline-item
              v-for="item in detail.timeline"
              :key="`${item.kind}-${item.id}`"
              :timestamp="item.effectiveAt"
              :type="item.kind === 'org' ? 'primary' : 'info'"
            >
              <div class="timeline-head">
                <el-tag size="small" effect="light" round>{{ timelineLabel(item) }}</el-tag>
                <span class="timeline-operator">{{ item.operatorName || '-' }}</span>
              </div>
              <div v-if="item.reason" class="timeline-reason">{{ item.reason }}</div>
            </el-timeline-item>
          </el-timeline>
          <el-empty v-else :description="t('hr.staff.timelineEmpty')" :image-size="60" />
        </section>
      </template>
    </div>
  </el-drawer>
</template>

<style scoped>
.staff-form {
  margin-top: var(--bs-space-2);
}

.idno-plain {
  margin: var(--bs-space-3) 0 var(--bs-space-1);
  font-size: var(--bs-typography-font-size-lg);
  font-weight: 600;
  word-break: break-all;
}

.idno-mask {
  margin: 0;
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs);
}

.drawer-header {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
}

.drawer-title {
  font-size: var(--bs-typography-font-size-lg);
  font-weight: 600;
}

.drawer-body {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-3);
}

.drawer-section {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
}

.section-title {
  margin: 0;
  font-size: var(--bs-typography-font-size-md);
  font-weight: 600;
}

.staff-timeline {
  padding-left: var(--bs-space-1);
}

.timeline-head {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
}

.timeline-operator {
  color: var(--bs-color-fg-secondary);
  font-size: var(--bs-typography-font-size-sm);
}

.timeline-reason {
  margin-top: var(--bs-space-1);
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs);
}
</style>
