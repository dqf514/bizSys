<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import ExportButton from '@/components/list/ExportButton.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { useListPage } from '@/composables/useListPage'
import { useDictOptions } from '@/composables/useDict'
import { listContracts, deleteContract, submitContract, voidContract, exportContracts } from '@/api/contract'
import type { Contract } from '@/api/types'

defineOptions({ name: 'ContractList' })

const { t } = useI18n()
const router = useRouter()
const typeOpts = useDictOptions('contract_type')

const searchModel = ref<Record<string, any>>({ q: '' })
const searchFields: SearchField[] = [
  { key: 'q', labelKey: 'contract.contract.searchName', placeholderKey: 'contract.contract.placeholderName', width: 220 },
]

const statusTabs: StatusTabItem[] = [
  { value: 'draft', labelKey: 'contract.contract.statusDraft' },
  { value: 'approving', labelKey: 'contract.contract.statusApproving' },
  { value: 'approved', labelKey: 'contract.contract.statusApproved' },
  { value: 'rejected', labelKey: 'contract.contract.statusRejected' },
  { value: 'voided', labelKey: 'contract.contract.statusVoided' },
  { value: 'all', labelKey: 'common.action.all' },
]

const list = useListPage<Contract>({
  fetch: async (params) => {
    const data = await listContracts({ ...params, q: searchModel.value.q || undefined })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  exportFn: (params) => exportContracts({ ...params, q: searchModel.value.q || undefined }),
  defaultStatus: 'all',
})

const columns: ListColumn[] = [
  { prop: 'contractNo', labelKey: 'contract.contract.contractNo', width: 150, fixed: 'left', sortable: 'contract_no' },
  { prop: 'name', labelKey: 'contract.contract.name', minWidth: 200, fixed: 'left', sortable: 'name' },
  { prop: 'customerName', labelKey: 'contract.contract.customerName', minWidth: 150, sortable: 'customer_name' },
  { prop: 'contractType', labelKey: 'contract.contract.contractType', width: 110, sortable: 'contract_type' },
  { prop: 'amount', labelKey: 'contract.contract.amount', width: 120, sortable: 'amount' },
  { prop: 'startDate', labelKey: 'contract.contract.startDate', width: 110, sortable: 'start_date' },
  { prop: 'endDate', labelKey: 'contract.contract.endDate', width: 110, sortable: 'end_date' },
  { prop: 'handlerName', labelKey: 'contract.contract.handlerName', width: 100 },
  { prop: 'status', labelKey: 'contract.contract.status', width: 100, sortable: 'status' },
  { prop: 'createTime', labelKey: 'contract.contract.createTime', width: 160, sortable: 'create_time' },
]

/** 行内动作随状态变化；超过 3 个自动收进「更多」 */
function rowActions(row: Contract): ActionItem[] {
  const s = String(row.status)
  const acts: ActionItem[] = [{ key: 'detail', tip: 'common.action.detail' }]
  if (['draft', 'rejected'].includes(s)) acts.push({ key: 'edit', tip: 'common.action.edit', perm: 'contract:edit' })
  if (['draft', 'rejected'].includes(s)) acts.push({ key: 'submit', tip: 'contract.contract.submit', perm: 'contract:submit' })
  if (['draft', 'rejected', 'approved'].includes(s)) {
    acts.push({ key: 'void', tip: 'contract.contract.void', icon: 'FolderDelete', danger: true, perm: 'contract:edit' })
  }
  if (s === 'draft') acts.push({ key: 'delete', tip: 'common.action.delete', perm: 'contract:delete' })
  return acts
}

function onRowAction(key: string, row: Contract) {
  if (key === 'detail') openDetail(row)
  else if (key === 'edit') openEdit(row)
  else if (key === 'submit') void doSubmit(row)
  else if (key === 'void') void doVoid(row)
  else if (key === 'delete') void remove(row)
}

function openCreate() {
  router.push('/contract/contracts/new')
}

function openEdit(row: Contract) {
  router.push(`/contract/contracts/${row.id}/edit`)
}

function openDetail(row: Contract) {
  router.push(`/contract/contracts/${row.id}`)
}

async function doSubmit(row: Contract) {
  try {
    await ElMessageBox.confirm(t('contract.contract.submitConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await submitContract(row.id)
    ElMessage.success(t('common.message.submitSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

async function remove(row: Contract) {
  try {
    await ElMessageBox.confirm(t('common.message.deleteConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteContract(row.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

async function doVoid(row: Contract) {
  try {
    await ElMessageBox.confirm(t('contract.contract.voidConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await voidContract(row.id)
    ElMessage.success(t('common.message.submitSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

function fmtAmount(row: Record<string, unknown>) {
  const n = Number(row.amount ?? 0)
  return Number.isFinite(n) ? n.toLocaleString() : String(row.amount ?? '-')
}
</script>

<template>
  <ListPage :title="t('contract.contract.title')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'contract:create'" type="primary" @click="openCreate">
        {{ t('contract.contract.create') }}
      </el-button>
      <ExportButton v-permission="'contract:list:export'" :export-fn="() => list.exportList()" />
    </template>

    <template #searchBar>
      <SearchBar
        v-model="searchModel"
        :fields="searchFields"
        @search="list.search()"
        @reset="searchModel = { q: '' }; list.reset()"
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
        <template #amount="{ row }">{{ fmtAmount(row) }}</template>
        <template #contractType="{ row }">
          {{
            typeOpts.opts.value.find((x) => x.value === row.contractType)?.label || row.contractType || '-'
          }}
        </template>
        <template #status="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="contract.contract.status" />
        </template>
        <template #contractNo="{ row }">
          <el-button link type="primary" @click="openDetail(row as unknown as Contract)">{{ row.contractNo }}</el-button>
        </template>
        <template #extraColumns>
          <el-table-column :label="t('common.action.operate')" width="130" fixed="right" align="center" header-align="center">
            <template #default="{ row }">
              <ActionBar :actions="rowActions(row as unknown as Contract)" @select="(k) => onRowAction(k, row as unknown as Contract)" />
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>
</template>
