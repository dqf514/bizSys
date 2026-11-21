<script setup lang="ts">
/** 客户方人员备案（B2）：客户自助登记的外来试验人员 / 跟踪支持人员，客户经理审核后生效。 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import ExportButton from '@/components/list/ExportButton.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import CustomerSelect from '@/components/form/CustomerSelect.vue'
import { useListPage } from '@/composables/useListPage'
import { useDictOptions } from '@/composables/useDict'
import {
  createPartnerStaff,
  exportPartnerStaffs,
  getPartnerStaff,
  listPartnerStaffs,
  partnerStaffCounts,
  reviewPartnerStaff,
  togglePartnerStaff,
} from '@/api/crm'
import type { PartnerStaff } from '@/api/types'

defineOptions({ name: 'PartnerStaffList' })

const { t } = useI18n()
const typeOpts = useDictOptions('partner_staff_type')

const searchModel = ref<Record<string, any>>({ q: '', staff_type: '', source: '' })
const searchFields = computed<SearchField[]>(() => [
  {
    key: 'q',
    labelKey: 'crm.staff.searchName',
    placeholderKey: 'crm.staff.placeholderName',
    width: 240,
  },
  {
    key: 'staff_type',
    labelKey: 'crm.staff.staffType',
    type: 'select',
    options: typeOpts.opts.value,
    width: 170,
  },
  {
    key: 'source',
    labelKey: 'crm.staff.source',
    type: 'select',
    options: [
      { label: t('crm.staff.sourcePortal'), value: 'portal' },
      { label: t('crm.staff.sourceInternal'), value: 'internal' },
    ],
    width: 160,
  },
])

const statusTabs = ref<StatusTabItem[]>([
  { value: 'all', labelKey: 'common.action.all', count: 0 },
  { value: 'pending', labelKey: 'crm.staff.statusPending', count: 0 },
  { value: 'approved', labelKey: 'crm.staff.statusApproved', count: 0 },
  { value: 'rejected', labelKey: 'crm.staff.statusRejected', count: 0 },
  { value: 'disabled', labelKey: 'crm.staff.statusDisabled', count: 0 },
])

const counts = ref<Record<string, number>>({})

async function loadCounts() {
  try {
    counts.value = (await partnerStaffCounts()) ?? {}
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

function buildFilters(params: Record<string, unknown>) {
  return {
    ...((params.filters as Record<string, unknown>) || {}),
    staff_type: searchModel.value.staff_type || undefined,
    source: searchModel.value.source || undefined,
  }
}

const list = useListPage<PartnerStaff>({
  fetch: async (params) => {
    const data = await listPartnerStaffs({
      ...params,
      q: searchModel.value.q || undefined,
      filters: buildFilters(params),
    })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  exportFn: (params) =>
    exportPartnerStaffs({
      ...params,
      q: searchModel.value.q || undefined,
      filters: buildFilters(params),
    }),
  defaultStatus: 'all',
  onLoaded: () => {
    void loadCounts()
  },
})

const columns: ListColumn[] = [
  { prop: 'name', labelKey: 'crm.staff.name', width: 110, fixed: 'left', sortable: 'name' },
  { prop: 'customerName', labelKey: 'crm.staff.customerName', minWidth: 160, sortable: 'customer_name' },
  { prop: 'staffType', labelKey: 'crm.staff.staffType', width: 130, sortable: 'staff_type' },
  { prop: 'position', labelKey: 'crm.staff.position', width: 120 },
  { prop: 'phone', labelKey: 'crm.staff.phone', width: 140 },
  { prop: 'plateNo', labelKey: 'crm.staff.plateNo', width: 120 },
  { prop: 'planVisitDate', labelKey: 'crm.staff.planVisitDate', width: 120, sortable: 'plan_visit_date' },
  { prop: 'ndaSigned', labelKey: 'crm.staff.ndaSigned', width: 90, align: 'center' },
  { prop: 'source', labelKey: 'crm.staff.source', width: 120 },
  { prop: 'status', labelKey: 'crm.staff.status', width: 110, sortable: 'status' },
  { prop: 'createTime', labelKey: 'crm.staff.createTime', width: 160, sortable: 'create_time' },
]

function rowActions(row: PartnerStaff): ActionItem[] {
  const s = String(row.status)
  const acts: ActionItem[] = [{ key: 'detail', tip: 'common.action.detail' }]
  if (s === 'pending' || s === 'rejected') {
    acts.push({ key: 'approve', tip: 'crm.staff.approve', perm: 'crm:staff:review' })
    acts.push({ key: 'reject', tip: 'crm.staff.reject', perm: 'crm:staff:review' })
  }
  if (s === 'approved') {
    acts.push({ key: 'disable', tip: 'crm.staff.disable', icon: 'Close', danger: true, perm: 'crm:staff:edit' })
  }
  if (s === 'disabled') {
    acts.push({ key: 'enable', tip: 'crm.staff.enable', perm: 'crm:staff:edit' })
  }
  return acts
}

/* ---------------- 详情 ---------------- */
const detailVisible = ref(false)
const detail = ref<PartnerStaff | null>(null)

async function openDetail(row: PartnerStaff) {
  try {
    detail.value = await getPartnerStaff(row.id)
    detailVisible.value = true
  } catch {
    /* http notifies */
  }
}

/* ---------------- 审核 ---------------- */
const reviewVisible = ref(false)
const reviewTarget = ref<PartnerStaff | null>(null)
const reviewForm = ref<{ action: 'approve' | 'reject'; comment: string; bizOwnerName: string; visitPerm: string; ndaSigned: boolean }>({
  action: 'approve',
  comment: '',
  bizOwnerName: '',
  visitPerm: '',
  ndaSigned: true,
})

function openReview(row: PartnerStaff, action: 'approve' | 'reject') {
  reviewTarget.value = row
  reviewForm.value = {
    action,
    comment: '',
    bizOwnerName: row.bizOwnerName || '',
    visitPerm: row.visitPerm || '',
    ndaSigned: row.ndaSigned,
  }
  reviewVisible.value = true
}

async function submitReview() {
  const target = reviewTarget.value
  if (!target) return
  try {
    await reviewPartnerStaff(target.id, {
      action: reviewForm.value.action,
      comment: reviewForm.value.comment,
      bizOwnerName: reviewForm.value.bizOwnerName || undefined,
      visitPerm: reviewForm.value.visitPerm || null,
      ndaSigned: reviewForm.value.ndaSigned,
    })
    ElMessage.success(t('common.message.submitSuccess'))
    reviewVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  }
}

/* ---------------- 内部代登记 ---------------- */
const createVisible = ref(false)
const createForm = ref<Record<string, any>>({
  name: '',
  customer_id: null,
  customer_name: '',
  gender: '',
  id_no: '',
  position: '',
  phone: '',
  email: '',
  plate_no: '',
  staff_type: '',
  visit_purpose: '',
  plan_visit_date: '',
  nda_signed: false,
  remark: '',
})

function openCreate() {
  createForm.value = {
    name: '',
    customer_id: null,
    customer_name: '',
    gender: '',
    id_no: '',
    position: '',
    phone: '',
    email: '',
    plate_no: '',
    staff_type: '',
    visit_purpose: '',
    plan_visit_date: '',
    nda_signed: false,
    remark: '',
  }
  createVisible.value = true
}

async function submitCreate() {
  const f = createForm.value
  if (!f.name) {
    ElMessage.warning(t('common.form.required'))
    return
  }
  try {
    await createPartnerStaff(f)
    ElMessage.success(t('common.message.createSuccess'))
    createVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  }
}

async function doToggle(row: PartnerStaff, status: 'approved' | 'disabled') {
  try {
    await togglePartnerStaff(row.id, status)
    ElMessage.success(t('common.message.submitSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

function onRowAction(key: string, row: PartnerStaff) {
  if (key === 'detail') void openDetail(row)
  else if (key === 'approve') openReview(row, 'approve')
  else if (key === 'reject') openReview(row, 'reject')
  else if (key === 'disable') void doToggle(row, 'disabled')
  else if (key === 'enable') void doToggle(row, 'approved')
}
</script>

<template>
  <ListPage :title="t('crm.staff.title')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'crm:staff:create'" type="primary" @click="openCreate">
        {{ t('crm.staff.create') }}
      </el-button>
      <ExportButton v-permission="'crm:staff:export'" :export-fn="() => list.exportList()" />
    </template>

    <template #searchBar>
      <SearchBar
        v-model="searchModel"
        :fields="searchFields"
        @search="list.search()"
        @reset="searchModel = { q: '', staff_type: '', source: '' }; list.reset()"
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
        <template #staffType="{ row }">
          {{ typeOpts.opts.value.find((x) => x.value === row.staffType)?.label || row.staffType || '-' }}
        </template>
        <template #ndaSigned="{ row }">
          {{ row.ndaSigned ? t('common.action.yes') : t('common.action.no') }}
        </template>
        <template #source="{ row }">
          {{ row.source === 'portal' ? t('crm.staff.sourcePortal') : t('crm.staff.sourceInternal') }}
        </template>
        <template #status="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="crm.staff.status" />
        </template>
        <template #name="{ row }">
          <el-button link type="primary" @click="openDetail(row as unknown as PartnerStaff)">
            {{ row.name }}
          </el-button>
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
                :actions="rowActions(row as unknown as PartnerStaff)"
                @select="(k) => onRowAction(k, row as unknown as PartnerStaff)"
              />
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <el-drawer v-model="detailVisible" :size="'var(--bs-layout-drawer-md)'" :title="t('crm.staff.detail')">
    <el-descriptions v-if="detail" :column="2" border>
      <el-descriptions-item :label="t('crm.staff.name')">{{ detail.name }}</el-descriptions-item>
      <el-descriptions-item :label="t('crm.staff.status')">
        <StatusTag :status="detail.status" i18n-prefix="crm.staff.status" />
      </el-descriptions-item>
      <el-descriptions-item :label="t('crm.staff.customerName')">{{ detail.customerName || '-' }}</el-descriptions-item>
      <el-descriptions-item :label="t('crm.staff.staffType')">
        {{ detail.staffTypeLabel || detail.staffType || '-' }}
      </el-descriptions-item>
      <el-descriptions-item :label="t('crm.staff.position')">{{ detail.position || '-' }}</el-descriptions-item>
      <el-descriptions-item :label="t('crm.staff.phone')">{{ detail.phone || '-' }}</el-descriptions-item>
      <el-descriptions-item :label="t('crm.staff.email')">{{ detail.email || '-' }}</el-descriptions-item>
      <el-descriptions-item :label="t('crm.staff.plateNo')">{{ detail.plateNo || '-' }}</el-descriptions-item>
      <el-descriptions-item :label="t('crm.staff.planVisitDate')">{{ detail.planVisitDate || '-' }}</el-descriptions-item>
      <el-descriptions-item :label="t('crm.staff.ndaSigned')">
        {{ detail.ndaSigned ? t('common.action.yes') : t('common.action.no') }}
      </el-descriptions-item>
      <el-descriptions-item :label="t('crm.staff.visitPurpose')" :span="2">
        {{ detail.visitPurpose || '-' }}
      </el-descriptions-item>
      <el-descriptions-item :label="t('crm.staff.bizOwnerName')">{{ detail.bizOwnerName || '-' }}</el-descriptions-item>
      <el-descriptions-item :label="t('crm.staff.visitPerm')">{{ detail.visitPerm || '-' }}</el-descriptions-item>
      <el-descriptions-item :label="t('crm.staff.reviewName')">{{ detail.reviewName || '-' }}</el-descriptions-item>
      <el-descriptions-item :label="t('crm.staff.reviewComment')">{{ detail.reviewComment || '-' }}</el-descriptions-item>
    </el-descriptions>
  </el-drawer>

  <el-dialog v-model="reviewVisible" :width="'var(--bs-layout-dialog-sm)'" :title="t('crm.staff.reviewTitle')">
    <el-form label-position="top">
      <el-form-item :label="t('crm.staff.comment')">
        <el-input v-model="reviewForm.comment" type="textarea" :rows="3" :maxlength="500" show-word-limit />
      </el-form-item>
      <el-form-item v-if="reviewForm.action === 'approve'" :label="t('crm.staff.bizOwnerName')">
        <el-input v-model="reviewForm.bizOwnerName" :maxlength="64" />
      </el-form-item>
      <el-form-item v-if="reviewForm.action === 'approve'" :label="t('crm.staff.visitPerm')">
        <el-input v-model="reviewForm.visitPerm" :maxlength="255" :placeholder="t('crm.staff.visitPermPlaceholder')" />
      </el-form-item>
      <el-form-item v-if="reviewForm.action === 'approve'" :label="t('crm.staff.ndaSigned')">
        <el-switch v-model="reviewForm.ndaSigned" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="reviewVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" @click="submitReview">{{ t('common.action.confirm') }}</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="createVisible" :width="'var(--bs-layout-dialog-md)'" :title="t('crm.staff.createTitle')">
    <el-form label-position="top">
      <el-form-item :label="t('crm.staff.name')" required>
        <el-input v-model="createForm.name" :maxlength="64" />
      </el-form-item>
      <el-form-item :label="t('crm.staff.customerName')">
        <CustomerSelect v-model="createForm.customer_id" :placeholder="t('crm.staff.customerPlaceholder')" />
      </el-form-item>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item :label="t('crm.staff.staffType')">
            <el-select v-model="createForm.staff_type" style="width: 100%" clearable>
              <el-option
                v-for="o in typeOpts.opts.value"
                :key="o.value"
                :label="o.label"
                :value="o.value"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('crm.staff.position')">
            <el-input v-model="createForm.position" :maxlength="64" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item :label="t('crm.staff.phone')">
            <el-input v-model="createForm.phone" :maxlength="32" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('crm.staff.plateNo')">
            <el-input v-model="createForm.plate_no" :maxlength="32" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item :label="t('crm.staff.planVisitDate')">
        <el-date-picker v-model="createForm.plan_visit_date" type="date" value-format="YYYY-MM-DD" />
      </el-form-item>
      <el-form-item :label="t('crm.staff.visitPurpose')">
        <el-input v-model="createForm.visit_purpose" :maxlength="255" />
      </el-form-item>
      <el-form-item :label="t('crm.staff.ndaSigned')">
        <el-switch v-model="createForm.nda_signed" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="createVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" @click="submitCreate">{{ t('common.action.submit') }}</el-button>
    </template>
  </el-dialog>
</template>
