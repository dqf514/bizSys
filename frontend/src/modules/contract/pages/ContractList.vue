<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ExportButton from '@/components/list/ExportButton.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { useListPage } from '@/composables/useListPage'
import { listContracts, deleteContract, submitContract, exportContracts } from '@/api/contract'
import type { Contract } from '@/api/types'

defineOptions({ name: 'ContractList' })

const { t } = useI18n()
const router = useRouter()

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
  { prop: 'contractNo', labelKey: 'contract.contract.contractNo', width: 150, fixed: 'left' },
  { prop: 'name', labelKey: 'contract.contract.name', minWidth: 200, fixed: 'left' },
  { prop: 'customerName', labelKey: 'contract.contract.customerName', minWidth: 150 },
  { prop: 'contractType', labelKey: 'contract.contract.contractType', width: 110 },
  { prop: 'amount', labelKey: 'contract.contract.amount', width: 120 },
  { prop: 'startDate', labelKey: 'contract.contract.startDate', width: 110 },
  { prop: 'endDate', labelKey: 'contract.contract.endDate', width: 110 },
  { prop: 'handlerName', labelKey: 'contract.contract.handlerName', width: 100 },
  { prop: 'status', labelKey: 'contract.contract.status', width: 100 },
  { prop: 'createTime', labelKey: 'contract.contract.createTime', width: 160 },
]

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
      >
        <template #amount="{ row }">{{ fmtAmount(row) }}</template>
        <template #status="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="contract.contract.status" />
        </template>
        <template #contractNo="{ row }">
          <el-button link type="primary" @click="openDetail(row as unknown as Contract)">{{ row.contractNo }}</el-button>
        </template>
        <template #extraColumns>
          <el-table-column :label="t('common.action.operate')" width="230" fixed="right">
            <template #default="{ row }">
              <el-button
                v-if="['draft', 'rejected'].includes(String(row.status))"
                v-permission="'contract:edit'"
                link
                type="primary"
                @click="openEdit(row as unknown as Contract)"
              >
                {{ t('common.action.edit') }}
              </el-button>
              <el-button
                v-if="['draft', 'rejected'].includes(String(row.status))"
                v-permission="'contract:submit'"
                link
                type="warning"
                @click="doSubmit(row as unknown as Contract)"
              >
                {{ t('contract.contract.submit') }}
              </el-button>
              <el-button link type="primary" @click="openDetail(row as unknown as Contract)">
                {{ t('common.action.detail') }}
              </el-button>
              <el-button
                v-if="row.status === 'draft'"
                v-permission="'contract:create'"
                link
                type="danger"
                @click="remove(row as unknown as Contract)"
              >
                {{ t('common.action.delete') }}
              </el-button>
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>
</template>
