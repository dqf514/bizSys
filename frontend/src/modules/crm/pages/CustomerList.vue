<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox, type FormInstance, type UploadFile } from 'element-plus'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import ExportButton from '@/components/list/ExportButton.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import SmartInput from '@/components/form/SmartInput.vue'
import CustomerDetailDrawer from '../components/CustomerDetailDrawer.vue'
import PartnerAccountPanel from '../components/PartnerAccountPanel.vue'
import { useListPage } from '@/composables/useListPage'
import { useDictOptions } from '@/composables/useDict'
import { recordSmartHistory } from '@/composables/smartInputHistory'
import { useAuthStore } from '@/stores/auth'
import {
  listCustomers,
  customerCounts,
  createCustomer,
  updateCustomer,
  deleteCustomer,
  exportCustomers,
  downloadCustomerTemplate,
  importCustomers,
  partnerAccountCounts,
} from '@/api/crm'
import type { Customer } from '@/api/types'

defineOptions({ name: 'CustomerList' })

const { t } = useI18n()
const auth = useAuthStore()

/* ---------- 页面级视图：往来单位 / 合作方账号（原采购管理合作方账号并入） ---------- */
const route = useRoute()
const router = useRouter()
const canViewAccounts = computed(() => auth.hasPerm('procurement:partner:list'))
const view = ref<'units' | 'accounts'>(
  route.query.tab === 'accounts' && canViewAccounts.value ? 'accounts' : 'units',
)
const accountTotal = ref(0)

async function loadAccountCount() {
  if (!canViewAccounts.value) return
  try {
    const data = await partnerAccountCounts()
    accountTotal.value = data?.all ?? 0
  } catch {
    /* badge optional */
  }
}

onMounted(() => void loadAccountCount())

const unitAll = ref(0)
const viewTabs = computed<StatusTabItem[]>(() => {
  const tabs: StatusTabItem[] = [{ value: 'units', labelKey: 'crm.customer.viewUnits', count: unitAll.value }]
  if (canViewAccounts.value) {
    tabs.push({ value: 'accounts', labelKey: 'crm.customer.viewAccounts', count: accountTotal.value })
  }
  return tabs
})

function switchView(v: string) {
  view.value = v as 'units' | 'accounts'
  router.replace({ query: { ...route.query, tab: v === 'units' ? undefined : v } })
}

// 深链（含旧 /procurement/partners 重定向）：keep-alive 下同一组件复用，需响应 query.tab 变化
watch(
  () => route.query.tab,
  (v) => {
    if (v === 'accounts' && canViewAccounts.value) view.value = 'accounts'
    else if (!v) view.value = 'units'
  },
)

const searchModel = ref<Record<string, any>>({ q: '', taxNo: '', partnerType: '' })
const searchFields = computed<SearchField[]>(() => [
  { key: 'q', labelKey: 'crm.customer.searchName', placeholderKey: 'crm.customer.placeholderName', width: 220 },
  { key: 'taxNo', labelKey: 'crm.customer.searchTaxNo', placeholderKey: 'crm.customer.placeholderTaxNo', width: 200 },
  {
    key: 'partnerType',
    labelKey: 'crm.customer.partnerType',
    type: 'select',
    width: 150,
    options: [
      { label: t('crm.customer.partnerTypeCustomer'), value: 'customer' },
      { label: t('crm.customer.partnerTypeSupplier'), value: 'supplier' },
      { label: t('crm.customer.partnerTypeBoth'), value: 'both' },
    ],
  },
])

const statusTabs = ref<StatusTabItem[]>([
  { value: 'all', labelKey: 'common.action.all', count: 0 },
  { value: 'enabled', labelKey: 'crm.customer.enabled', count: 0 },
  { value: 'disabled', labelKey: 'crm.customer.disabled', count: 0 },
])

const counts = ref<Record<string, number>>({})

async function loadCounts() {
  try {
    counts.value = (await customerCounts()) ?? {}
    let all = 0
    for (const tab of statusTabs.value) {
      if (tab.value === 'all') continue
      tab.count = counts.value[tab.value] ?? 0
      all += tab.count
    }
    const allTab = statusTabs.value.find((x) => x.value === 'all')
    if (allTab) allTab.count = all
    unitAll.value = all
  } catch {
    /* counts optional */
  }
}

onMounted(() => void loadCounts())

const list = useListPage<Customer>({
  fetch: async (params) => {
    const data = await listCustomers({
      ...params,
      q: searchModel.value.q || undefined,
      filters: {
        taxNo: searchModel.value.taxNo || undefined,
        partner_type: searchModel.value.partnerType || undefined,
      },
    })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  exportFn: (params) =>
    exportCustomers({
      ...params,
      q: searchModel.value.q || undefined,
      filters: {
        taxNo: searchModel.value.taxNo || undefined,
        partner_type: searchModel.value.partnerType || undefined,
      },
    }),
  defaultStatus: 'enabled',
  onLoaded: () => {
    void loadCounts()
  },
})

const columns: ListColumn[] = [
  { prop: 'customerNo', labelKey: 'crm.customer.customerNo', width: 130, fixed: 'left', sortable: 'customer_no' },
  { prop: 'name', labelKey: 'crm.customer.name', minWidth: 180, fixed: 'left', sortable: 'name' },
  { prop: 'partnerType', labelKey: 'crm.customer.partnerType', width: 110, sortable: 'partner_type' },
  { prop: 'customerType', labelKey: 'crm.customer.customerType', width: 110, sortable: 'customer_type' },
  { prop: 'contactPerson', labelKey: 'crm.customer.contactPerson', width: 110 },
  { prop: 'taxNo', labelKey: 'crm.customer.taxNo', width: 170 },
  { prop: 'grade', labelKey: 'crm.customer.grade', width: 80, sortable: 'grade' },
  { prop: 'status', labelKey: 'crm.customer.status', width: 90, sortable: 'status' },
  { prop: 'province', labelKey: 'crm.customer.province', width: 100 },
  { prop: 'city', labelKey: 'crm.customer.city', width: 100 },
  { prop: 'payOrg', labelKey: 'crm.customer.payOrg', minWidth: 140 },
  { prop: 'createTime', labelKey: 'crm.customer.createTime', width: 160, sortable: 'create_time' },
]

const rowActions: ActionItem[] = [
  { key: 'detail', tip: 'common.action.detail' },
  { key: 'edit', tip: 'common.action.edit', perm: 'crm:customer:edit' },
  { key: 'delete', tip: 'common.action.delete', perm: 'crm:customer:delete' },
]

function onRowAction(key: string, row: Customer) {
  if (key === 'detail') openDetail(row)
  else if (key === 'edit') openEdit(row)
  else if (key === 'delete') void remove(row)
}

const typeOpts = useDictOptions('customer_type')
const gradeOpts = useDictOptions('customer_grade')
const supplyOpts = useDictOptions('supply_category')

const dialogVisible = ref(false)
const dialogTitle = ref('')
const formRef = ref<FormInstance>()
const saving = ref(false)
const editingId = ref<number | null>(null)
const form = reactive({
  name: '',
  partnerType: 'customer' as 'customer' | 'supplier' | 'both',
  code: '',
  customerType: '',
  taxNo: '',
  grade: '',
  status: 'enabled' as 'enabled' | 'disabled',
  address: '',
  country: '',
  province: '',
  city: '',
  bankName: '',
  bankAccount: '',
  payOrg: '',
  contactPerson: '',
  contactPhone: '',
  supplyCategory: '',
  supplierRating: '',
  remark: '',
})

const detailVisible = ref(false)
const detailId = ref<number | null>(null)

function openDetail(row: Customer) {
  detailId.value = row.id
  detailVisible.value = true
}

// 从任务/合同等详情的"关联客户"链接跳入：/crm/customers?detail=<id> 直接打开详情抽屉
watch(
  () => route.query.detail,
  (v) => {
    const id = Number(v)
    if (!id) return
    detailId.value = id
    detailVisible.value = true
    router.replace({ query: { ...route.query, detail: undefined } })
  },
  { immediate: true },
)

const importVisible = ref(false)
const importFile = ref<File | null>(null)

function openCreate() {
  editingId.value = null
  dialogTitle.value = t('crm.customer.create')
  Object.assign(form, {
    name: '',
    partnerType: 'customer',
    code: '',
    customerType: '',
    taxNo: '',
    grade: '',
    status: 'enabled',
    address: '',
    country: '',
    province: '',
    city: '',
    bankName: '',
    bankAccount: '',
    payOrg: '',
    contactPerson: '',
    contactPhone: '',
    supplyCategory: '',
    supplierRating: '',
    remark: '',
  })
  dialogVisible.value = true
}

function openEdit(row: Customer) {
  editingId.value = row.id
  dialogTitle.value = t('crm.customer.edit')
  Object.assign(form, {
    name: row.name,
    partnerType: row.partnerType ?? 'customer',
    code: row.code ?? '',
    customerType: row.customerType ?? '',
    taxNo: row.taxNo ?? '',
    grade: row.grade ?? '',
    status: row.status,
    address: row.address ?? '',
    country: row.country ?? '',
    province: row.province ?? '',
    city: row.city ?? '',
    bankName: row.bankName ?? '',
    bankAccount: row.bankAccount ?? '',
    payOrg: row.payOrg ?? '',
    contactPerson: row.contactPerson ?? '',
    contactPhone: row.contactPhone ?? '',
    supplyCategory: row.supplyCategory ?? '',
    supplierRating: row.supplierRating ?? '',
    remark: row.remark ?? '',
  })
  dialogVisible.value = true
}

async function save() {
  if (!formRef.value) return
  const ok = await formRef.value.validate().catch(() => false)
  if (!ok) return
  saving.value = true
  try {
    if (editingId.value) await updateCustomer(editingId.value, { ...form })
    else await createCustomer({ ...form })
    recordSmartHistory('crm.customer.country', form.country)
    recordSmartHistory('crm.customer.province', form.province)
    recordSmartHistory('crm.customer.city', form.city)
    recordSmartHistory('crm.customer.bankName', form.bankName)
    recordSmartHistory('crm.customer.payOrg', form.payOrg)
    ElMessage.success(t('common.message.saveSuccess'))
    dialogVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  } finally {
    saving.value = false
  }
}

async function remove(row: Customer) {
  try {
    await ElMessageBox.confirm(t('common.message.deleteConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteCustomer(row.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

function onImportFile(file: UploadFile) {
  importFile.value = file.raw ?? null
}

async function doImport() {
  if (!importFile.value) return
  try {
    await importCustomers(importFile.value)
    ElMessage.success(t('common.message.importSuccess'))
    importVisible.value = false
    importFile.value = null
    list.refresh()
  } catch {
    /* http notifies */
  }
}
</script>

<template>
  <div class="customer-page">
    <div class="view-tabs-row">
      <StatusTabs :tabs="viewTabs" :model-value="view" @update:model-value="switchView" />
    </div>

    <ListPage v-if="view === 'units'" class="page-body" :title="t('crm.customer.title')" :loading="list.loading.value">
      <template #actions>
        <el-button v-permission="'crm:customer:create'" type="primary" @click="openCreate">
          {{ t('crm.customer.create') }}
        </el-button>
        <ExportButton v-permission="'crm:customer:list:export'" :export-fn="() => list.exportList()" />
        <el-button v-permission="'crm:customer:import'" @click="importVisible = true">
          {{ t('common.action.import') }}
        </el-button>
        <el-button v-permission="'crm:customer:import'" @click="downloadCustomerTemplate()">
          {{ t('common.action.downloadTemplate') }}
        </el-button>
      </template>

      <template #searchBar>
        <SearchBar
          v-model="searchModel"
          :fields="searchFields"
          @search="list.search()"
          @reset="searchModel = { q: '', taxNo: '', partnerType: '' }; list.reset()"
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
          <template #status="{ row }">
            <StatusTag :status="String(row.status)" i18n-prefix="common.status" />
          </template>
          <template #name="{ row }">
            <el-button link type="primary" @click="openDetail(row as unknown as Customer)">{{ row.name }}</el-button>
          </template>
          <template #customerType="{ row }">
            {{ typeOpts.opts.value.find((x) => x.value === row.customerType)?.label || row.customerType || '-' }}
          </template>
          <template #partnerType="{ row }">
            <el-tag size="small" effect="plain">{{ t(`crm.customer.partnerType${String(row.partnerType || 'customer').charAt(0).toUpperCase()}${String(row.partnerType || 'customer').slice(1)}`) }}</el-tag>
          </template>
          <template #grade="{ row }">
            {{ gradeOpts.opts.value.find((x) => x.value === row.grade)?.label || row.grade || '-' }}
          </template>
          <template #extraColumns>
            <el-table-column :label="t('common.action.operate')" width="130" fixed="right" align="center" header-align="center">
              <template #default="{ row }">
                <ActionBar :actions="rowActions" @select="(k) => onRowAction(k, row as unknown as Customer)" />
              </template>
            </el-table-column>
          </template>
        </ListTable>
      </template>
    </ListPage>

    <PartnerAccountPanel v-else class="page-body account-body" @changed="loadAccountCount" />
  </div>

  <el-dialog v-model="dialogVisible" :title="dialogTitle" width="640px" append-to-body>
    <el-form ref="formRef" :model="form" label-width="120px">
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item :label="t('crm.customer.name')" prop="name" :rules="[{ required: true, message: t('common.form.required') }]">
            <el-input v-model="form.name" :placeholder="t('crm.customer.placeholderName')" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('crm.customer.partnerType')" prop="partnerType" :rules="[{ required: true, message: t('common.form.required') }]">
            <el-radio-group v-model="form.partnerType">
              <el-radio value="customer">{{ t('crm.customer.partnerTypeCustomer') }}</el-radio>
              <el-radio value="supplier">{{ t('crm.customer.partnerTypeSupplier') }}</el-radio>
              <el-radio value="both">{{ t('crm.customer.partnerTypeBoth') }}</el-radio>
            </el-radio-group>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('crm.customer.code')">
            <el-input v-model="form.code" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('crm.customer.customerType')">
            <el-select
              v-model="form.customerType"
              clearable
              filterable
              :placeholder="t('common.form.placeholderSelect')"
              style="width: 100%"
            >
              <el-option v-for="o in typeOpts.opts.value" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('crm.customer.taxNo')">
            <el-input v-model="form.taxNo" :placeholder="t('crm.customer.placeholderTaxNo')" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('crm.customer.grade')">
            <el-select
              v-model="form.grade"
              clearable
              filterable
              :placeholder="t('common.form.placeholderSelect')"
              style="width: 100%"
            >
              <el-option v-for="o in gradeOpts.opts.value" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('crm.customer.status')">
            <el-radio-group v-model="form.status">
              <el-radio value="enabled">{{ t('crm.customer.enabled') }}</el-radio>
              <el-radio value="disabled">{{ t('crm.customer.disabled') }}</el-radio>
            </el-radio-group>
          </el-form-item>
        </el-col>
        <el-col :span="24">
          <el-form-item :label="t('crm.customer.address')">
            <el-input v-model="form.address" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('crm.customer.country')">
            <SmartInput v-model="form.country" field="crm.customer.country" :maxlength="64" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('crm.customer.province')">
            <SmartInput v-model="form.province" field="crm.customer.province" :maxlength="64" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('crm.customer.city')">
            <SmartInput v-model="form.city" field="crm.customer.city" :maxlength="64" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('crm.customer.bankName')">
            <SmartInput v-model="form.bankName" field="crm.customer.bankName" :maxlength="128" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('crm.customer.bankAccount')">
            <el-input v-model="form.bankAccount" :maxlength="64" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('crm.customer.payOrg')">
            <SmartInput v-model="form.payOrg" field="crm.customer.payOrg" :maxlength="128" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('crm.customer.contactPerson')">
            <el-input v-model="form.contactPerson" :maxlength="64" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('crm.customer.contactPhone')">
            <el-input v-model="form.contactPhone" :maxlength="32" />
          </el-form-item>
        </el-col>
        <el-col :span="12" v-if="form.partnerType !== 'customer'">
          <el-form-item :label="t('crm.customer.supplyCategory')">
            <el-select
              v-model="form.supplyCategory"
              clearable
              filterable
              :placeholder="t('common.form.placeholderSelect')"
              style="width: 100%"
            >
              <el-option v-for="o in supplyOpts.opts.value" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12" v-if="form.partnerType !== 'customer'">
          <el-form-item :label="t('crm.customer.supplierRating')">
            <el-select
              v-model="form.supplierRating"
              clearable
              :placeholder="t('common.form.placeholderSelect')"
              style="width: 100%"
            >
              <el-option v-for="o in gradeOpts.opts.value" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="24">
          <el-form-item :label="t('crm.customer.remark')">
            <el-input v-model="form.remark" type="textarea" :rows="2" />
          </el-form-item>
        </el-col>
      </el-row>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="saving" @click="save">{{ t('common.action.save') }}</el-button>
    </template>
  </el-dialog>

  <CustomerDetailDrawer v-model="detailVisible" :customer-id="detailId" />

  <el-dialog v-model="importVisible" :title="t('crm.customer.importTitle')" width="440px" append-to-body>
    <p class="import-tip">{{ t('crm.customer.importTip') }}</p>
    <el-upload :auto-upload="false" :limit="1" accept=".xlsx,.xls" :on-change="onImportFile">
      <el-button>{{ t('common.action.select') }}</el-button>
    </el-upload>
    <template #footer>
      <el-button @click="importVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" @click="doImport">{{ t('common.action.import') }}</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.customer-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.view-tabs-row {
  flex-shrink: 0;
  padding: var(--bs-space-3) var(--bs-space-3) 0;
}

.page-body {
  flex: 1;
  min-height: 0;
}

.page-body.list-page {
  height: auto;
}

.account-body {
  padding: var(--bs-space-2) var(--bs-space-3) var(--bs-space-3);
}

.import-tip {
  margin-bottom: var(--bs-space-2);
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-sm);
}
</style>
