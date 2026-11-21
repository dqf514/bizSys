<script setup lang="ts">
/** 区域分级管控（B3）：区域编码 / 类型 / 安全等级 / 陪同与 NDA 等管控要求。 */
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
import { useDictOptions } from '@/composables/useDict'
import {
  createVisitorZone,
  listVisitorZones,
  toggleVisitorZone,
  updateVisitorZone,
  visitorZoneCounts,
} from '@/api/visitor'
import type { VisitorZone } from '@/api/types'

defineOptions({ name: 'ZoneList' })

const { t } = useI18n()
const typeOpts = useDictOptions('visitor_zone_type')

const searchModel = ref<Record<string, any>>({ q: '', zone_type: '' })
const searchFields = computed<SearchField[]>(() => [
  {
    key: 'q',
    labelKey: 'visitor.zone.searchName',
    placeholderKey: 'visitor.zone.placeholderName',
    width: 240,
  },
  {
    key: 'zone_type',
    labelKey: 'visitor.zone.zoneType',
    type: 'select',
    options: typeOpts.opts.value,
    width: 180,
  },
])

const statusTabs = ref<StatusTabItem[]>([
  { value: 'all', labelKey: 'common.action.all', count: 0 },
  { value: 'enabled', labelKey: 'visitor.zone.statusEnabled', count: 0 },
  { value: 'disabled', labelKey: 'visitor.zone.statusDisabled', count: 0 },
])

const counts = ref<Record<string, number>>({})

async function loadCounts() {
  try {
    counts.value = (await visitorZoneCounts()) ?? {}
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

function buildFilters(params: Record<string, unknown>) {
  return {
    ...((params.filters as Record<string, unknown>) || {}),
    zone_type: searchModel.value.zone_type || undefined,
  }
}

const list = useListPage<VisitorZone>({
  fetch: async (params) => {
    const data = await listVisitorZones({
      ...params,
      q: searchModel.value.q || undefined,
      filters: buildFilters(params),
    })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  defaultStatus: 'all',
  onLoaded: () => {
    void loadCounts()
  },
})

const columns: ListColumn[] = [
  { prop: 'code', labelKey: 'visitor.zone.code', width: 130, fixed: 'left', sortable: 'code' },
  { prop: 'name', labelKey: 'visitor.zone.name', minWidth: 160, sortable: 'name' },
  { prop: 'zoneTypeText', labelKey: 'visitor.zone.zoneType', width: 130, sortable: 'zone_type' },
  { prop: 'securityLevel', labelKey: 'visitor.zone.securityLevel', width: 110, align: 'center', sortable: 'security_level' },
  { prop: 'needExtraApproval', labelKey: 'visitor.zone.needExtraApproval', width: 110, align: 'center' },
  { prop: 'needEscort', labelKey: 'visitor.zone.needEscort', width: 100, align: 'center' },
  { prop: 'needNda', labelKey: 'visitor.zone.needNda', width: 110, align: 'center' },
  { prop: 'capacity', labelKey: 'visitor.zone.capacity', width: 100, align: 'center' },
  { prop: 'status', labelKey: 'visitor.zone.status', width: 100, sortable: 'status' },
  { prop: 'createTime', labelKey: 'visitor.zone.createTime', width: 160, sortable: 'create_time' },
]

function rowActions(row: VisitorZone): ActionItem[] {
  const acts: ActionItem[] = [{ key: 'edit', tip: 'common.action.edit', perm: 'visitor:zone:edit' }]
  if (row.status === 'enabled') {
    acts.push({ key: 'disable', tip: 'visitor.zone.disabled', icon: 'TurnOff', danger: true, perm: 'visitor:zone:edit' })
  } else {
    acts.push({ key: 'enable', tip: 'visitor.zone.enabled', icon: 'CircleCheck', perm: 'visitor:zone:edit' })
  }
  return acts
}

/* ---------------- 编辑 ---------------- */
const editVisible = ref(false)
const editTarget = ref<VisitorZone | null>(null)
const form = ref<Record<string, any>>({
  code: '',
  name: '',
  zone_type: 'public',
  security_level: 1,
  need_extra_approval: false,
  need_escort: false,
  need_nda: false,
  need_dual_person: false,
  camera_control: false,
  device_binding: '',
  capacity: 0,
  status: 'enabled',
  remark: '',
})

function resetForm() {
  form.value = {
    code: '',
    name: '',
    zone_type: 'public',
    security_level: 1,
    need_extra_approval: false,
    need_escort: false,
    need_nda: false,
    need_dual_person: false,
    camera_control: false,
    device_binding: '',
    capacity: 0,
    status: 'enabled',
    remark: '',
  }
}

function openCreate() {
  editTarget.value = null
  resetForm()
  editVisible.value = true
}

function openEdit(row: VisitorZone) {
  editTarget.value = row
  form.value = {
    code: row.code,
    name: row.name,
    zone_type: row.zoneType,
    security_level: row.securityLevel,
    need_extra_approval: row.needExtraApproval,
    need_escort: row.needEscort,
    need_nda: row.needNda,
    need_dual_person: row.needDualPerson,
    camera_control: row.cameraControl,
    device_binding: row.deviceBinding || '',
    capacity: row.capacity,
    status: row.status,
    remark: row.remark || '',
  }
  editVisible.value = true
}

async function submit() {
  const f = form.value
  if (!f.code || !f.name) {
    ElMessage.warning(t('common.form.required'))
    return
  }
  const payload = {
    code: f.code,
    name: f.name,
    zone_type: f.zone_type,
    security_level: f.security_level,
    need_extra_approval: f.need_extra_approval,
    need_escort: f.need_escort,
    need_nda: f.need_nda,
    need_dual_person: f.need_dual_person,
    camera_control: f.camera_control,
    device_binding: f.device_binding,
    capacity: f.capacity,
    status: f.status,
    remark: f.remark,
  }
  try {
    if (editTarget.value) {
      await updateVisitorZone(editTarget.value.id, payload)
      ElMessage.success(t('common.message.updateSuccess'))
    } else {
      await createVisitorZone(payload)
      ElMessage.success(t('common.message.createSuccess'))
    }
    editVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  }
}

async function doToggle(row: VisitorZone) {
  const next = row.status === 'enabled' ? 'disabled' : 'enabled'
  try {
    await toggleVisitorZone(row.id, next)
    ElMessage.success(t('common.message.submitSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

function onRowAction(key: string, row: VisitorZone) {
  if (key === 'edit') openEdit(row)
  else if (key === 'enable' || key === 'disable') void doToggle(row)
}
</script>

<template>
  <ListPage :title="t('visitor.zone.title')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'visitor:zone:edit'" type="primary" @click="openCreate">
        {{ t('visitor.zone.create') }}
      </el-button>
    </template>

    <template #searchBar>
      <SearchBar
        v-model="searchModel"
        :fields="searchFields"
        @search="list.search()"
        @reset="searchModel = { q: '', zone_type: '' }; list.reset()"
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
        <template #zoneTypeText="{ row }">
          {{ row.zoneTypeText || row.zoneType || '-' }}
        </template>
        <template #securityLevel="{ row }">
          {{ t('visitor.zone.levelLabel', { level: row.securityLevel }) }}
        </template>
        <template #needExtraApproval="{ row }">
          {{ row.needExtraApproval ? t('common.action.yes') : t('common.action.no') }}
        </template>
        <template #needEscort="{ row }">
          {{ row.needEscort ? t('common.action.yes') : t('common.action.no') }}
        </template>
        <template #needNda="{ row }">
          {{ row.needNda ? t('common.action.yes') : t('common.action.no') }}
        </template>
        <template #capacity="{ row }">
          {{ row.capacity > 0 ? row.capacity : '-' }}
        </template>
        <template #status="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="visitor.zone.status" />
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
                :actions="rowActions(row as unknown as VisitorZone)"
                @select="(k) => onRowAction(k, row as unknown as VisitorZone)"
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
    :title="editTarget ? t('visitor.zone.editTitle') : t('visitor.zone.createTitle')"
  >
    <el-form label-position="top">
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item :label="t('visitor.zone.code')" required>
            <el-input v-model="form.code" :maxlength="32" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('visitor.zone.name')" required>
            <el-input v-model="form.name" :maxlength="64" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item :label="t('visitor.zone.zoneType')">
            <el-select v-model="form.zone_type" style="width: 100%" clearable>
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
          <el-form-item :label="t('visitor.zone.securityLevel')">
            <el-input-number v-model="form.security_level" :min="1" :max="4" style="width: 100%" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="12">
        <el-col :span="8">
          <el-form-item :label="t('visitor.zone.needExtraApproval')">
            <el-switch v-model="form.need_extra_approval" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('visitor.zone.needEscort')">
            <el-switch v-model="form.need_escort" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('visitor.zone.needNda')">
            <el-switch v-model="form.need_nda" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="12">
        <el-col :span="8">
          <el-form-item :label="t('visitor.zone.needDualPerson')">
            <el-switch v-model="form.need_dual_person" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('visitor.zone.cameraControl')">
            <el-switch v-model="form.camera_control" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('visitor.zone.capacity')">
            <el-input-number v-model="form.capacity" :min="0" :max="9999" style="width: 100%" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item :label="t('visitor.zone.deviceBinding')">
            <el-input v-model="form.device_binding" :maxlength="255" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('visitor.zone.status')">
            <el-select v-model="form.status" style="width: 100%">
              <el-option :label="t('visitor.zone.statusEnabled')" value="enabled" />
              <el-option :label="t('visitor.zone.statusDisabled')" value="disabled" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item :label="t('visitor.zone.remark')">
        <el-input v-model="form.remark" type="textarea" :rows="2" :maxlength="2000" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="editVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" @click="submit">{{ t('common.action.submit') }}</el-button>
    </template>
  </el-dialog>
</template>
