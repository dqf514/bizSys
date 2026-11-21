<script setup lang="ts">
/** 访客黑名单（B3）：闯入 / 尾随 / 失信人员禁止入内。 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { useListPage } from '@/composables/useListPage'
import {
  createVisitorBlacklist,
  listVisitorBlacklist,
  toggleVisitorBlacklist,
  updateVisitorBlacklist,
  visitorBlacklistCounts,
} from '@/api/visitor'
import type { VisitorBlacklist } from '@/api/types'

defineOptions({ name: 'BlacklistList' })

const { t } = useI18n()

const searchModel = ref<Record<string, any>>({ q: '' })
const searchFields = computed<SearchField[]>(() => [
  {
    key: 'q',
    labelKey: 'visitor.blacklist.searchName',
    placeholderKey: 'visitor.blacklist.placeholderName',
    width: 260,
  },
])

const statusTabs = ref<StatusTabItem[]>([
  { value: 'all', labelKey: 'common.action.all', count: 0 },
  { value: 'enabled', labelKey: 'visitor.blacklist.statusEnabled', count: 0 },
  { value: 'disabled', labelKey: 'visitor.blacklist.statusDisabled', count: 0 },
])

const counts = ref<Record<string, number>>({})

async function loadCounts() {
  try {
    counts.value = (await visitorBlacklistCounts()) ?? {}
    for (const tab of statusTabs.value) {
      if (tab.value === 'all') continue
      tab.count = counts.value[tab.value] ?? 0
    }
    const allTab = statusTabs.value.find((x) => x.value === 'all')
    if (allTab) allTab.count = counts.value.all ?? 0
  } catch {
    /* counts optional */
  }
}

onMounted(() => void loadCounts())

const list = useListPage<VisitorBlacklist>({
  fetch: async (params) => {
    const data = await listVisitorBlacklist({ ...params, q: searchModel.value.q || undefined })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  defaultStatus: 'all',
  onLoaded: () => {
    void loadCounts()
  },
})

const columns: ListColumn[] = [
  { prop: 'visitorName', labelKey: 'visitor.blacklist.visitorName', width: 120, fixed: 'left' },
  { prop: 'idNo', labelKey: 'visitor.blacklist.idNo', width: 170 },
  { prop: 'phone', labelKey: 'visitor.blacklist.phone', width: 140 },
  { prop: 'company', labelKey: 'visitor.blacklist.company', minWidth: 160 },
  { prop: 'reason', labelKey: 'visitor.blacklist.reason', minWidth: 170 },
  { prop: 'effectiveFrom', labelKey: 'visitor.blacklist.effectiveFrom', width: 160 },
  { prop: 'effectiveTo', labelKey: 'visitor.blacklist.effectiveTo', width: 160 },
  { prop: 'status', labelKey: 'visitor.blacklist.status', width: 100, sortable: 'status' },
  { prop: 'createTime', labelKey: 'visitor.blacklist.createTime', width: 160, sortable: 'create_time' },
]

function rowActions(row: VisitorBlacklist): ActionItem[] {
  const acts: ActionItem[] = [{ key: 'edit', tip: 'common.action.edit', perm: 'visitor:blacklist:edit' }]
  if (row.status === 'enabled') {
    acts.push({ key: 'disable', tip: 'common.action.disable', icon: 'TurnOff', danger: true, perm: 'visitor:blacklist:edit' })
  } else {
    acts.push({ key: 'enable', tip: 'common.action.enable', icon: 'CircleCheck', perm: 'visitor:blacklist:edit' })
  }
  return acts
}

/* ---------------- 编辑 ---------------- */
const editVisible = ref(false)
const editTarget = ref<VisitorBlacklist | null>(null)
const form = ref<Record<string, any>>({
  visitor_name: '',
  id_no: '',
  phone: '',
  company: '',
  reason: '',
  effective_from: '',
  effective_to: '',
  source: 'manual',
  status: 'enabled',
  remark: '',
})

function resetForm() {
  form.value = {
    visitor_name: '',
    id_no: '',
    phone: '',
    company: '',
    reason: '',
    effective_from: '',
    effective_to: '',
    source: 'manual',
    status: 'enabled',
    remark: '',
  }
}

function openCreate() {
  editTarget.value = null
  resetForm()
  editVisible.value = true
}

function openEdit(row: VisitorBlacklist) {
  editTarget.value = row
  form.value = {
    visitor_name: row.visitorName,
    id_no: row.idNo,
    phone: row.phone,
    company: row.company,
    reason: row.reason,
    effective_from: row.effectiveFrom ? row.effectiveFrom.slice(0, 10) : '',
    effective_to: row.effectiveTo ? row.effectiveTo.slice(0, 10) : '',
    source: row.source,
    status: row.status,
    remark: row.remark || '',
  }
  editVisible.value = true
}

async function submit() {
  const f = form.value
  if (!f.visitor_name) {
    ElMessage.warning(t('common.form.required'))
    return
  }
  const payload = {
    visitor_name: f.visitor_name,
    id_no: f.id_no,
    phone: f.phone,
    company: f.company,
    reason: f.reason,
    effective_from: f.effective_from ? `${f.effective_from} 00:00:00` : null,
    effective_to: f.effective_to ? `${f.effective_to} 23:59:59` : null,
    source: f.source,
    status: f.status,
    remark: f.remark,
  }
  try {
    if (editTarget.value) {
      await updateVisitorBlacklist(editTarget.value.id, payload)
      ElMessage.success(t('common.message.updateSuccess'))
    } else {
      await createVisitorBlacklist(payload)
      ElMessage.success(t('common.message.createSuccess'))
    }
    editVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  }
}

async function doToggle(row: VisitorBlacklist) {
  const next = row.status === 'enabled' ? 'disabled' : 'enabled'
  try {
    await toggleVisitorBlacklist(row.id, next)
    ElMessage.success(t('common.message.submitSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

function onRowAction(key: string, row: VisitorBlacklist) {
  if (key === 'edit') openEdit(row)
  else if (key === 'enable' || key === 'disable') void doToggle(row)
}
</script>

<template>
  <ListPage :title="t('visitor.blacklist.title')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'visitor:blacklist:edit'" type="primary" @click="openCreate">
        {{ t('visitor.blacklist.create') }}
      </el-button>
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
        <template #status="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="visitor.blacklist.status" />
        </template>
        <template #extraColumns>
          <el-table-column
            :label="t('common.action.operate')"
            width="120"
            fixed="right"
            align="center"
            header-align="center"
          >
            <template #default="{ row }">
              <ActionBar
                :actions="rowActions(row as unknown as VisitorBlacklist)"
                @select="(k) => onRowAction(k, row as unknown as VisitorBlacklist)"
              />
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <el-dialog
    v-model="editVisible"
    :width="'var(--bs-layout-dialog-md)'"
    :title="editTarget ? t('visitor.blacklist.editTitle') : t('visitor.blacklist.createTitle')"
  >
    <el-form label-position="top">
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item :label="t('visitor.blacklist.visitorName')" required>
            <el-input v-model="form.visitor_name" :maxlength="64" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('visitor.blacklist.idNo')">
            <el-input v-model="form.id_no" :maxlength="64" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item :label="t('visitor.blacklist.phone')">
            <el-input v-model="form.phone" :maxlength="32" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('visitor.blacklist.company')">
            <el-input v-model="form.company" :maxlength="128" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item :label="t('visitor.blacklist.reason')">
        <el-input v-model="form.reason" :maxlength="255" />
      </el-form-item>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item :label="t('visitor.blacklist.effectiveFrom')">
            <el-date-picker v-model="form.effective_from" type="date" value-format="YYYY-MM-DD" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('visitor.blacklist.effectiveTo')">
            <el-date-picker v-model="form.effective_to" type="date" value-format="YYYY-MM-DD" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item :label="t('visitor.blacklist.remark')">
        <el-input v-model="form.remark" type="textarea" :rows="2" :maxlength="2000" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="editVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" @click="submit">{{ t('common.action.submit') }}</el-button>
    </template>
  </el-dialog>
</template>
