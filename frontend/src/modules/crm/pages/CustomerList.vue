<script setup lang="ts">
import { reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type UploadFile } from 'element-plus'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ExportButton from '@/components/list/ExportButton.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { useListPage } from '@/composables/useListPage'
import { useDictOptions } from '@/composables/useDict'
import {
  listCustomers,
  createCustomer,
  updateCustomer,
  deleteCustomer,
  exportCustomers,
  downloadCustomerTemplate,
  importCustomers,
} from '@/api/crm'
import type { Customer } from '@/api/types'

defineOptions({ name: 'CustomerList' })

const { t } = useI18n()

const searchModel = ref<Record<string, any>>({ q: '' })
const searchFields: SearchField[] = [
  { key: 'q', labelKey: 'crm.customer.searchName', placeholderKey: 'crm.customer.placeholderName', width: 220 },
  { key: 'taxNo', labelKey: 'crm.customer.searchTaxNo', placeholderKey: 'crm.customer.placeholderTaxNo', width: 200 },
]

const statusTabs: StatusTabItem[] = [
  { value: 'enabled', labelKey: 'crm.customer.enabled' },
  { value: 'disabled', labelKey: 'crm.customer.disabled' },
  { value: 'all', labelKey: 'common.action.all' },
]

const list = useListPage<Customer>({
  fetch: async (params) => {
    const data = await listCustomers({
      ...params,
      q: searchModel.value.q || undefined,
      filters: { taxNo: searchModel.value.taxNo || undefined },
    })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  exportFn: (params) =>
    exportCustomers({
      ...params,
      q: searchModel.value.q || undefined,
      filters: { taxNo: searchModel.value.taxNo || undefined },
    }),
  defaultStatus: 'enabled',
})

const columns: ListColumn[] = [
  { prop: 'customerNo', labelKey: 'crm.customer.customerNo', width: 130, fixed: 'left' },
  { prop: 'name', labelKey: 'crm.customer.name', minWidth: 180, fixed: 'left' },
  { prop: 'customerType', labelKey: 'crm.customer.customerType', width: 110 },
  { prop: 'taxNo', labelKey: 'crm.customer.taxNo', width: 170 },
  { prop: 'grade', labelKey: 'crm.customer.grade', width: 80 },
  { prop: 'status', labelKey: 'crm.customer.status', width: 90 },
  { prop: 'province', labelKey: 'crm.customer.province', width: 100 },
  { prop: 'city', labelKey: 'crm.customer.city', width: 100 },
  { prop: 'payOrg', labelKey: 'crm.customer.payOrg', minWidth: 140 },
  { prop: 'createTime', labelKey: 'crm.customer.createTime', width: 160 },
]

const typeOpts = useDictOptions('customer_type')
const gradeOpts = useDictOptions('customer_grade')

const dialogVisible = ref(false)
const dialogTitle = ref('')
const formRef = ref<FormInstance>()
const saving = ref(false)
const editingId = ref<number | null>(null)
const form = reactive({
  name: '',
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
  remark: '',
})

const importVisible = ref(false)
const importFile = ref<File | null>(null)

function openCreate() {
  editingId.value = null
  dialogTitle.value = t('crm.customer.create')
  Object.assign(form, {
    name: '',
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
    remark: '',
  })
  dialogVisible.value = true
}

function openEdit(row: Customer) {
  editingId.value = row.id
  dialogTitle.value = t('crm.customer.edit')
  Object.assign(form, {
    name: row.name,
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
  <ListPage :title="t('crm.customer.title')" :loading="list.loading.value">
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
        @reset="searchModel = { q: '', taxNo: '' }; list.reset()"
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
      >
        <template #status="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="common.status" />
        </template>
        <template #customerType="{ row }">
          {{ typeOpts.opts.value.find((x) => x.value === row.customerType)?.label || row.customerType || '-' }}
        </template>
        <template #grade="{ row }">
          {{ gradeOpts.opts.value.find((x) => x.value === row.grade)?.label || row.grade || '-' }}
        </template>
        <template #extraColumns>
          <el-table-column :label="t('common.action.operate')" width="180" fixed="right">
            <template #default="{ row }">
              <el-button v-permission="'crm:customer:edit'" link type="primary" @click="openEdit(row as unknown as Customer)">
                {{ t('common.action.edit') }}
              </el-button>
              <el-button v-permission="'crm:customer:delete'" link type="danger" @click="remove(row as unknown as Customer)">
                {{ t('common.action.delete') }}
              </el-button>
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <el-dialog v-model="dialogVisible" :title="dialogTitle" width="640px" append-to-body>
    <el-form ref="formRef" :model="form" label-width="120px">
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item :label="t('crm.customer.name')" prop="name" :rules="[{ required: true, message: t('common.form.required') }]">
            <el-input v-model="form.name" :placeholder="t('crm.customer.placeholderName')" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('crm.customer.code')">
            <el-input v-model="form.code" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('crm.customer.customerType')">
            <el-select v-model="form.customerType" clearable style="width: 100%">
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
            <el-select v-model="form.grade" clearable style="width: 100%">
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
            <el-input v-model="form.country" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('crm.customer.province')">
            <el-input v-model="form.province" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('crm.customer.city')">
            <el-input v-model="form.city" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('crm.customer.bankName')">
            <el-input v-model="form.bankName" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('crm.customer.bankAccount')">
            <el-input v-model="form.bankAccount" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('crm.customer.payOrg')">
            <el-input v-model="form.payOrg" />
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
.import-tip {
  margin-bottom: var(--bs-space-2);
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-sm);
}
</style>
