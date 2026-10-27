<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { useListPage } from '@/composables/useListPage'
import { listPartnerAccounts, partnerAccountCounts, reviewPartnerAccount } from '@/api/procurement'
import { customerOptions } from '@/api/crm'
import type { CustomerOption, PartnerAccount } from '@/api/types'

defineOptions({ name: 'PartnerAccountList' })

const { t } = useI18n()

const searchModel = ref<Record<string, any>>({ q: '' })
const searchFields: SearchField[] = [
  { key: 'q', labelKey: 'procurement.partner.search', placeholderKey: 'procurement.partner.placeholder', width: 240 },
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
  { prop: 'username', labelKey: 'procurement.partner.username', width: 150, fixed: 'left', sortable: 'username' },
  { prop: 'companyName', labelKey: 'procurement.partner.companyName', minWidth: 200, sortable: 'company_name' },
  { prop: 'contactName', labelKey: 'procurement.partner.contactName', width: 100 },
  { prop: 'phone', labelKey: 'procurement.partner.phone', width: 130 },
  { prop: 'email', labelKey: 'procurement.partner.email', minWidth: 160 },
  { prop: 'status', labelKey: 'procurement.partner.status', width: 100, sortable: 'status' },
  { prop: 'reviewName', labelKey: 'procurement.partner.reviewName', width: 100 },
  { prop: 'lastLoginAt', labelKey: 'procurement.partner.lastLoginAt', width: 160 },
  { prop: 'createTime', labelKey: 'procurement.partner.createTime', width: 160, sortable: 'create_time' },
]

function rowActions(row: PartnerAccount): ActionItem[] {
  const acts: ActionItem[] = []
  if (row.status === 'pending' || row.status === 'rejected' || row.status === 'disabled') {
    acts.push({ key: 'approve', tip: 'procurement.partner.approve', icon: 'CircleCheck', perm: 'procurement:partner:review' })
  }
  if (row.status === 'pending') {
    acts.push({ key: 'reject', tip: 'procurement.partner.reject', icon: 'CircleClose', danger: true, perm: 'procurement:partner:review' })
  }
  if (row.status === 'enabled') {
    acts.push({ key: 'disable', tip: 'procurement.partner.disable', icon: 'CircleClose', danger: true, perm: 'procurement:partner:review' })
  }
  return acts
}

function onRowAction(key: string, row: PartnerAccount) {
  if (key === 'approve') openReview(row)
  else if (key === 'reject') void doReject(row)
  else if (key === 'disable') void doDisable(row)
}

/* ---------- review dialog（通过 + 绑定供应商） ---------- */
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
    list.refresh()
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
      t('procurement.partner.rejectConfirm'),
      t('procurement.partner.reject'),
      { inputPlaceholder: t('procurement.partner.reviewComment'), confirmButtonText: t('common.action.confirm'), cancelButtonText: t('common.action.cancel') },
    )
    comment = value ?? ''
  } catch {
    return
  }
  try {
    await reviewPartnerAccount(row.id, { approve: false, comment })
    ElMessage.success(t('common.message.saveSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

async function doDisable(row: PartnerAccount) {
  try {
    await ElMessageBox.confirm(t('procurement.partner.disableConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await reviewPartnerAccount(row.id, { approve: false })
    ElMessage.success(t('common.message.saveSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}
</script>

<template>
  <ListPage :title="t('procurement.partner.title')" :loading="list.loading.value">
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
        <template #status="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="common.status" />
        </template>
        <template #lastLoginAt="{ row }">{{ row.lastLoginAt || '-' }}</template>
        <template #reviewName="{ row }">{{ row.reviewName || '-' }}</template>
        <template #extraColumns>
          <el-table-column :label="t('common.action.operate')" width="140" fixed="right" align="center" header-align="center">
            <template #default="{ row }">
              <ActionBar :actions="rowActions(row as unknown as PartnerAccount)" @select="(k) => onRowAction(k, row as unknown as PartnerAccount)" />
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <el-dialog v-model="reviewVisible" :title="t('procurement.partner.review')" width="520px" append-to-body>
    <p class="muted review-tip">{{ t('procurement.partner.bindSupplierTip') }}</p>
    <el-form :model="reviewForm" label-width="100px">
      <el-form-item :label="t('procurement.partner.companyName')">
        <span>{{ reviewTarget?.companyName }}</span>
      </el-form-item>
      <el-form-item :label="t('procurement.partner.bindSupplier')">
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
      <el-form-item :label="t('procurement.partner.reviewComment')">
        <el-input v-model="reviewForm.comment" :maxlength="500" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="reviewVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="reviewSaving" @click="doApprove">{{ t('procurement.partner.approve') }}</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.muted {
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-sm);
}

.review-tip {
  margin: 0 0 var(--bs-space-3);
}
</style>
