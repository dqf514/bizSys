<script setup lang="ts">
/** 客户自助账号管理（B2）：门户注册的客户账号审核（绑定往来单位 / 客户经理 / 权限范围）与启停。 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import CustomerSelect from '@/components/form/CustomerSelect.vue'
import { useListPage } from '@/composables/useListPage'
import { customerAccountCounts, listCustomerAccounts, reviewCustomerAccount, toggleCustomerAccount } from '@/api/crm'
import type { CustomerAccount } from '@/api/types'

defineOptions({ name: 'CustomerAccountList' })

const { t } = useI18n()

const searchModel = ref<Record<string, any>>({ q: '' })
const searchFields: SearchField[] = [
  {
    key: 'q',
    labelKey: 'crm.customerAccount.searchName',
    placeholderKey: 'crm.customerAccount.placeholderName',
    width: 240,
  },
]

const statusTabs = ref<StatusTabItem[]>([
  { value: 'all', labelKey: 'common.action.all', count: 0 },
  { value: 'pending', labelKey: 'crm.customerAccount.statusPending', count: 0 },
  { value: 'enabled', labelKey: 'crm.customerAccount.statusEnabled', count: 0 },
  { value: 'rejected', labelKey: 'crm.customerAccount.statusRejected', count: 0 },
  { value: 'disabled', labelKey: 'crm.customerAccount.statusDisabled', count: 0 },
])

const counts = ref<Record<string, number>>({})

async function loadCounts() {
  try {
    counts.value = (await customerAccountCounts()) ?? {}
    let all = 0
    for (const tab of statusTabs.value) {
      if (tab.value === 'all') continue
      tab.count = counts.value[tab.value] ?? 0
      all += tab.count
    }
    const allTab = statusTabs.value.find((x) => x.value === 'all')
    if (allTab) allTab.count = all
  } catch {
    /* counts optional */
  }
}

onMounted(() => void loadCounts())

const list = useListPage<CustomerAccount>({
  fetch: async (params) => {
    const data = await listCustomerAccounts({ ...params, q: searchModel.value.q || undefined })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  defaultStatus: 'all',
  onLoaded: () => {
    void loadCounts()
  },
})

const columns: ListColumn[] = [
  { prop: 'username', labelKey: 'crm.customerAccount.username', width: 150, fixed: 'left', sortable: 'username' },
  { prop: 'companyName', labelKey: 'crm.customerAccount.companyName', minWidth: 180, sortable: 'company_name' },
  { prop: 'contactName', labelKey: 'crm.customerAccount.contactName', width: 110 },
  { prop: 'phone', labelKey: 'crm.customerAccount.phone', width: 140 },
  { prop: 'customerId', labelKey: 'crm.customerAccount.customerId', width: 110, align: 'center' },
  { prop: 'managerName', labelKey: 'crm.customerAccount.managerName', width: 110 },
  { prop: 'permScope', labelKey: 'crm.customerAccount.permScope', width: 160 },
  { prop: 'staffLimit', labelKey: 'crm.customerAccount.staffLimit', width: 110, align: 'center' },
  { prop: 'status', labelKey: 'crm.customerAccount.status', width: 110, sortable: 'status' },
  { prop: 'lastLoginAt', labelKey: 'crm.customerAccount.lastLoginAt', width: 160, sortable: 'last_login_at' },
  { prop: 'createTime', labelKey: 'crm.customerAccount.createTime', width: 160, sortable: 'create_time' },
]

function rowActions(row: CustomerAccount): ActionItem[] {
  const s = String(row.status)
  const acts: ActionItem[] = []
  if (s === 'pending' || s === 'rejected') {
    acts.push({ key: 'approve', tip: 'crm.customerAccount.approve', perm: 'crm:account:review' })
    acts.push({ key: 'reject', tip: 'crm.customerAccount.reject', perm: 'crm:account:review' })
  }
  if (s === 'enabled') {
    acts.push({ key: 'disable', tip: 'crm.customerAccount.disable', icon: 'Close', danger: true, perm: 'crm:account:edit' })
  }
  if (s === 'disabled') {
    acts.push({ key: 'enable', tip: 'crm.customerAccount.enable', perm: 'crm:account:edit' })
  }
  return acts
}

/* ---------------- 审核 ---------------- */
const reviewVisible = ref(false)
const reviewTarget = ref<CustomerAccount | null>(null)
const reviewForm = ref<{
  action: 'approve' | 'reject'
  comment: string
  customer_id: number | null
  manager_name: string
  perm_scope: string[]
  staff_limit: number
}>({
  action: 'approve',
  comment: '',
  customer_id: null,
  manager_name: '',
  perm_scope: ['entrust', 'staff'],
  staff_limit: 5,
})

const scopeOptions = computed(() => [
  { label: t('crm.customerAccount.scopeEntrust'), value: 'entrust' },
  { label: t('crm.customerAccount.scopeStaff'), value: 'staff' },
  { label: t('crm.customerAccount.scopeTender'), value: 'tender' },
  { label: t('crm.customerAccount.scopeVisit'), value: 'visit' },
])

function openReview(row: CustomerAccount, action: 'approve' | 'reject') {
  reviewTarget.value = row
  reviewForm.value = {
    action,
    comment: '',
    customer_id: row.customerId,
    manager_name: row.managerName || '',
    perm_scope: row.permScopeList?.length ? [...row.permScopeList] : ['entrust', 'staff'],
    staff_limit: row.staffLimit ?? 5,
  }
  reviewVisible.value = true
}

async function submitReview() {
  const target = reviewTarget.value
  if (!target) return
  try {
    await reviewCustomerAccount(target.id, {
      action: reviewForm.value.action,
      comment: reviewForm.value.comment,
      customerId: reviewForm.value.customer_id,
      managerName: reviewForm.value.manager_name || undefined,
      permScope: reviewForm.value.perm_scope.join(','),
      staffLimit: reviewForm.value.staff_limit,
    })
    ElMessage.success(t('common.message.submitSuccess'))
    reviewVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  }
}

async function doToggle(row: CustomerAccount, status: 'enabled' | 'disabled') {
  try {
    await toggleCustomerAccount(row.id, status)
    ElMessage.success(t('common.message.submitSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

function onRowAction(key: string, row: CustomerAccount) {
  if (key === 'approve') openReview(row, 'approve')
  else if (key === 'reject') openReview(row, 'reject')
  else if (key === 'disable') void doToggle(row, 'disabled')
  else if (key === 'enable') void doToggle(row, 'enabled')
}
</script>

<template>
  <ListPage :title="t('crm.customerAccount.title')" :loading="list.loading.value">
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
        <template #permScope="{ row }">
          <el-tag
            v-for="s in (row.permScopeList || [])"
            :key="s"
            size="small"
            effect="light"
            round
            class="scope-tag"
          >
            {{ scopeOptions.find((o) => o.value === s)?.label || s }}
          </el-tag>
          <span v-if="!(row.permScopeList || []).length">-</span>
        </template>
        <template #status="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="crm.customerAccount.status" />
        </template>
        <template #customerId="{ row }">
          <span v-if="row.customerId">#{{ row.customerId }}</span>
          <span v-else>-</span>
        </template>
        <template #extraColumns>
          <el-table-column
            :label="t('common.action.operate')"
            width="130"
            fixed="right"
            align="center"
            header-align="center"
          >
            <template #default="{ row }">
              <ActionBar
                :actions="rowActions(row as unknown as CustomerAccount)"
                @select="(k) => onRowAction(k, row as unknown as CustomerAccount)"
              />
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <el-dialog v-model="reviewVisible" :width="'var(--bs-layout-dialog-sm)'" :title="t('crm.customerAccount.reviewTitle')">
    <el-form label-position="top">
      <el-form-item :label="t('crm.customerAccount.comment')">
        <el-input v-model="reviewForm.comment" type="textarea" :rows="2" :maxlength="500" show-word-limit />
      </el-form-item>
      <template v-if="reviewForm.action === 'approve'">
        <el-form-item :label="t('crm.customerAccount.customerId')">
          <CustomerSelect v-model="reviewForm.customer_id" :placeholder="t('crm.customerAccount.customerPlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('crm.customerAccount.managerName')">
          <el-input v-model="reviewForm.manager_name" :maxlength="64" />
        </el-form-item>
        <el-form-item :label="t('crm.customerAccount.permScope')">
          <el-checkbox-group v-model="reviewForm.perm_scope">
            <el-checkbox v-for="o in scopeOptions" :key="o.value" :value="o.value" :label="o.label" />
          </el-checkbox-group>
        </el-form-item>
        <el-form-item :label="t('crm.customerAccount.staffLimit')">
          <el-input-number v-model="reviewForm.staff_limit" :min="0" :max="200" />
        </el-form-item>
      </template>
    </el-form>
    <template #footer>
      <el-button @click="reviewVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" @click="submitReview">{{ t('common.action.confirm') }}</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.scope-tag {
  margin-right: var(--bs-space-1);
}
</style>
