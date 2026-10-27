<script setup lang="ts">
/**
 * 合作方账号管理面板：嵌在往来单位列表页"合作方账号"视图（原采购管理 PartnerAccountList 迁入）。
 * 后端端点沿用 /procurement/partners，权限沿用 procurement:partner:list / procurement:partner:review。
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import PartnerAccountFormDialog from './PartnerAccountFormDialog.vue'
import PartnerAccountResetDialog from './PartnerAccountResetDialog.vue'
import { useListPage } from '@/composables/useListPage'
import {
  deletePartnerAccount,
  listPartnerAccounts,
  partnerAccountCounts,
  reviewPartnerAccount,
  customerOptions,
} from '@/api/crm'
import type { CustomerOption, PartnerAccount } from '@/api/types'

defineOptions({ name: 'PartnerAccountPanel' })

const emit = defineEmits<{ (e: 'changed'): void }>()

const { t } = useI18n()

const searchModel = ref<Record<string, any>>({ q: '' })
const searchFields: SearchField[] = [
  { key: 'q', labelKey: 'crm.account.search', placeholderKey: 'crm.account.placeholder', width: 240 },
]

const statusTabs = ref<StatusTabItem[]>([
  { value: 'all', labelKey: 'common.action.all', count: 0 },
  { value: 'pending', labelKey: 'common.status.pending', count: 0 },
  { value: 'enabled', labelKey: 'common.status.enabled', count: 0 },
  { value: 'rejected', labelKey: 'common.status.rejected', count: 0 },
  { value: 'disabled', labelKey: 'common.status.disabled', count: 0 },
])

const counts = ref<Record<string, number>>({})

async function loadCounts() {
  try {
    counts.value = (await partnerAccountCounts()) ?? {}
    for (const tab of statusTabs.value) {
      tab.count = counts.value[tab.value] ?? 0
    }
  } catch {
    /* counts optional */
  }
}

onMounted(() => void loadCounts())

const list = useListPage<PartnerAccount>({
  fetch: async (params) => {
    const data = await listPartnerAccounts({ ...params, q: searchModel.value.q || undefined })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  defaultStatus: 'all',
  onLoaded: () => {
    void loadCounts()
  },
})

const columns: ListColumn[] = [
  { prop: 'username', labelKey: 'crm.account.username', width: 150, fixed: 'left', sortable: 'username' },
  { prop: 'companyName', labelKey: 'crm.account.companyName', minWidth: 200, sortable: 'company_name' },
  { prop: 'contactName', labelKey: 'crm.account.contactName', width: 100 },
  { prop: 'phone', labelKey: 'crm.account.phone', width: 130 },
  { prop: 'email', labelKey: 'crm.account.email', minWidth: 160 },
  { prop: 'customerName', labelKey: 'crm.account.boundCustomer', minWidth: 160 },
  { prop: 'status', labelKey: 'crm.account.status', width: 100, sortable: 'status' },
  { prop: 'reviewName', labelKey: 'crm.account.reviewName', width: 100 },
  { prop: 'lastLoginAt', labelKey: 'crm.account.lastLoginAt', width: 160 },
  { prop: 'createTime', labelKey: 'crm.account.createTime', width: 160, sortable: 'create_time' },
]

function rowActions(row: PartnerAccount): ActionItem[] {
  const acts: ActionItem[] = []
  if (row.status === 'pending' || row.status === 'rejected' || row.status === 'disabled') {
    acts.push({ key: 'approve', tip: 'crm.account.approve', icon: 'CircleCheck', perm: 'procurement:partner:review' })
  }
  if (row.status === 'pending') {
    acts.push({ key: 'reject', tip: 'crm.account.reject', icon: 'CircleClose', danger: true, perm: 'procurement:partner:review' })
  }
  if (row.status === 'enabled') {
    acts.push({ key: 'disable', tip: 'crm.account.disable', icon: 'CircleClose', danger: true, perm: 'procurement:partner:review' })
  }
  acts.push({ key: 'edit', tip: 'crm.account.edit', icon: 'EditPen', perm: 'procurement:partner:edit' })
  acts.push({ key: 'resetPwd', tip: 'crm.account.resetPwd', icon: 'Key', perm: 'procurement:partner:edit' })
  acts.push({ key: 'delete', tip: 'crm.account.delete', icon: 'Delete', danger: true, perm: 'procurement:partner:delete' })
  return acts
}

function onRowAction(key: string, row: PartnerAccount) {
  if (key === 'approve') openReview(row)
  else if (key === 'reject') void doReject(row)
  else if (key === 'disable') void doDisable(row)
  else if (key === 'edit') openForm(row)
  else if (key === 'resetPwd') openReset(row)
  else if (key === 'delete') void doDelete(row)
}

function afterMutation() {
  list.refresh()
  emit('changed')
}

/* ---------- 新建/编辑/重置密码/删除 ---------- */
const formVisible = ref(false)
const formTarget = ref<PartnerAccount | null>(null)
const resetVisible = ref(false)
const resetTarget = ref<PartnerAccount | null>(null)

function openForm(row: PartnerAccount | null) {
  formTarget.value = row
  formVisible.value = true
}

function openReset(row: PartnerAccount) {
  resetTarget.value = row
  resetVisible.value = true
}

async function doDelete(row: PartnerAccount) {
  try {
    await ElMessageBox.confirm(
      t('crm.account.deleteConfirm', { name: row.companyName || row.username }),
      t('common.action.confirm'),
      { type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await deletePartnerAccount(row.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    afterMutation()
  } catch {
    /* http notifies */
  }
}

/* ---------- review dialog（通过 + 绑定供应商往来单位） ---------- */
const reviewVisible = ref(false)
const reviewSaving = ref(false)
const reviewTarget = ref<PartnerAccount | null>(null)
const reviewForm = reactive({ customerId: null as number | null, comment: '' })
const supplierOpts = ref<CustomerOption[]>([])
const supplierLoading = ref(false)

async function searchSuppliers(q: string) {
  supplierLoading.value = true
  try {
    supplierOpts.value = await customerOptions(q, 20, 'supplier')
  } catch {
    supplierOpts.value = []
  } finally {
    supplierLoading.value = false
  }
}

function openReview(row: PartnerAccount) {
  reviewTarget.value = row
  Object.assign(reviewForm, { customerId: row.customerId ?? null, comment: '' })
  supplierOpts.value = []
  reviewVisible.value = true
}

async function doApprove() {
  if (!reviewTarget.value) return
  reviewSaving.value = true
  try {
    await reviewPartnerAccount(reviewTarget.value.id, {
      approve: true,
      comment: reviewForm.comment,
      customerId: reviewForm.customerId,
    })
    ElMessage.success(t('common.message.saveSuccess'))
    reviewVisible.value = false
    afterMutation()
  } catch {
    /* http notifies */
  } finally {
    reviewSaving.value = false
  }
}

async function doReject(row: PartnerAccount) {
  let comment = ''
  try {
    const { value } = await ElMessageBox.prompt(
      t('crm.account.rejectConfirm'),
      t('crm.account.reject'),
      { inputPlaceholder: t('crm.account.reviewComment'), confirmButtonText: t('common.action.confirm'), cancelButtonText: t('common.action.cancel') },
    )
    comment = value ?? ''
  } catch {
    return
  }
  try {
    await reviewPartnerAccount(row.id, { approve: false, comment })
    ElMessage.success(t('common.message.saveSuccess'))
    afterMutation()
  } catch {
    /* http notifies */
  }
}

async function doDisable(row: PartnerAccount) {
  try {
    await ElMessageBox.confirm(t('crm.account.disableConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await reviewPartnerAccount(row.id, { approve: false })
    ElMessage.success(t('common.message.saveSuccess'))
    afterMutation()
  } catch {
    /* http notifies */
  }
}
</script>

<template>
  <div class="partner-account-panel">
    <div class="panel-search">
      <SearchBar
        v-model="searchModel"
        :fields="searchFields"
        @search="list.search()"
        @reset="searchModel = { q: '' }; list.reset()"
      >
        <el-button v-permission="'procurement:partner:create'" type="primary" @click="openForm(null)">
          {{ t('crm.account.create') }}
        </el-button>
      </SearchBar>
    </div>

    <StatusTabs
      :tabs="statusTabs"
      :model-value="String(list.query.status)"
      @update:model-value="list.setStatus($event)"
    />

    <div class="panel-table">
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
        <template #lastLoginAt="{ row }">{{ row.lastLoginAt || '-' }}</template>
        <template #reviewName="{ row }">{{ row.reviewName || '-' }}</template>
        <template #customerName="{ row }">{{ row.customerName || '-' }}</template>
        <template #extraColumns>
          <el-table-column :label="t('common.action.operate')" width="140" fixed="right" align="center" header-align="center">
            <template #default="{ row }">
              <ActionBar :actions="rowActions(row as unknown as PartnerAccount)" @select="(k) => onRowAction(k, row as unknown as PartnerAccount)" />
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </div>
  </div>

  <el-dialog v-model="reviewVisible" :title="t('crm.account.review')" width="520px" append-to-body>
    <p class="muted review-tip">{{ t('crm.account.bindPartnerTip') }}</p>
    <el-form :model="reviewForm" label-width="100px">
      <el-form-item :label="t('crm.account.companyName')">
        <span>{{ reviewTarget?.companyName }}</span>
      </el-form-item>
      <el-form-item :label="t('crm.account.bindPartner')">
        <el-select
          v-model="reviewForm.customerId"
          clearable
          filterable
          remote
          :remote-method="searchSuppliers"
          :loading="supplierLoading"
          :placeholder="t('procurement.contract.supplierPlaceholder')"
          style="width: 100%"
          @focus="!supplierOpts.length && searchSuppliers('')"
        >
          <el-option v-for="o in supplierOpts" :key="o.id" :label="o.label" :value="Number(o.id)" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('crm.account.reviewComment')">
        <el-input v-model="reviewForm.comment" :maxlength="500" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="reviewVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="reviewSaving" @click="doApprove">{{ t('crm.account.approve') }}</el-button>
    </template>
  </el-dialog>

  <PartnerAccountFormDialog v-model="formVisible" :account="formTarget" @saved="afterMutation" />
  <PartnerAccountResetDialog v-model="resetVisible" :account="resetTarget" @saved="afterMutation" />
</template>

<style scoped>
.partner-account-panel {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
  height: 100%;
  min-height: 0;
}

.panel-search {
  flex-shrink: 0;
  padding: var(--bs-space-2) var(--bs-space-3);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-bg-surface);
}

.panel-table {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.muted {
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-sm);
}

.review-tip {
  margin: 0 0 var(--bs-space-3);
}
</style>
