<script setup lang="ts">
/** 样品 / 样车交接（B3）：访客带入样品的交接登记与反查。 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import { useListPage } from '@/composables/useListPage'
import { createVisitorHandover, listVisitorHandovers } from '@/api/visitor'
import type { VisitorHandover } from '@/api/types'

defineOptions({ name: 'HandoverList' })

const { t } = useI18n()

const searchModel = ref<Record<string, any>>({ q: '', sample_type: '' })
const searchFields = computed<SearchField[]>(() => [
  {
    key: 'q',
    labelKey: 'visitor.handover.searchName',
    placeholderKey: 'visitor.handover.placeholderName',
    width: 260,
  },
  {
    key: 'sample_type',
    labelKey: 'visitor.handover.sampleType',
    type: 'select',
    options: [
      { label: t('visitor.handover.typeSample'), value: 'sample' },
      { label: t('visitor.handover.typeVehicle'), value: 'vehicle' },
      { label: t('visitor.handover.typeModel'), value: 'model' },
    ],
    width: 150,
  },
])

function buildFilters(params: Record<string, unknown>) {
  return {
    ...((params.filters as Record<string, unknown>) || {}),
    sample_type: searchModel.value.sample_type || undefined,
  }
}

const list = useListPage<VisitorHandover>({
  fetch: async (params) => {
    const data = await listVisitorHandovers({
      ...params,
      q: searchModel.value.q || undefined,
      filters: buildFilters(params),
    })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  defaultStatus: 'all',
})

const columns: ListColumn[] = [
  { prop: 'handoverNo', labelKey: 'visitor.handover.handoverNo', width: 175, fixed: 'left' },
  { prop: 'sampleNo', labelKey: 'visitor.handover.sampleNo', width: 150 },
  { prop: 'sampleName', labelKey: 'visitor.handover.sampleName', minWidth: 160 },
  { prop: 'barcode', labelKey: 'visitor.handover.barcode', width: 140 },
  { prop: 'sampleType', labelKey: 'visitor.handover.sampleType', width: 100 },
  { prop: 'qty', labelKey: 'visitor.handover.qty', width: 90, align: 'center' },
  { prop: 'handoverUserName', labelKey: 'visitor.handover.handoverUserName', width: 110 },
  { prop: 'receiveUserName', labelKey: 'visitor.handover.receiveUserName', width: 110 },
  { prop: 'handoverAt', labelKey: 'visitor.handover.handoverAt', width: 165, sortable: 'handover_at' },
  { prop: 'status', labelKey: 'visitor.handover.status', width: 100 },
]

/* ---------------- 登记 ---------------- */
const createVisible = ref(false)
const form = ref<Record<string, any>>({
  visit_id: null as number | null,
  sample_no: '',
  sample_name: '',
  barcode: '',
  sample_type: 'sample',
  qty: 1,
  handover_user_name: '',
  receive_user_name: '',
  remark: '',
})

function openCreate() {
  form.value = {
    visit_id: null,
    sample_no: '',
    sample_name: '',
    barcode: '',
    sample_type: 'sample',
    qty: 1,
    handover_user_name: '',
    receive_user_name: '',
    remark: '',
  }
  createVisible.value = true
}

async function submit() {
  const f = form.value
  if (!f.sample_no) {
    ElMessage.warning(t('common.form.required'))
    return
  }
  try {
    await createVisitorHandover({
      visit_id: f.visit_id,
      sample_no: f.sample_no,
      sample_name: f.sample_name,
      barcode: f.barcode,
      sample_type: f.sample_type,
      qty: f.qty,
      handover_user_name: f.handover_user_name,
      receive_user_name: f.receive_user_name,
      remark: f.remark,
    })
    ElMessage.success(t('common.message.createSuccess'))
    createVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  }
}
</script>

<template>
  <ListPage :title="t('visitor.handover.title')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'visitor:handover:create'" type="primary" @click="openCreate">
        {{ t('visitor.handover.create') }}
      </el-button>
    </template>

    <template #searchBar>
      <SearchBar
        v-model="searchModel"
        :fields="searchFields"
        @search="list.search()"
        @reset="searchModel = { q: '', sample_type: '' }; list.reset()"
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
        <template #sampleType="{ row }">
          {{ t(`visitor.handover.type${String(row.sampleType || '').replace(/^./, (c) => c.toUpperCase())}`) }}
        </template>
        <template #status="{ row }">
          <el-tag size="small" effect="light" round>
            {{ row.status === 'returned' ? t('visitor.handover.statusReturned') : t('visitor.handover.statusDone') }}
          </el-tag>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <el-dialog v-model="createVisible" :width="'var(--bs-layout-dialog-md)'" :title="t('visitor.handover.createTitle')">
    <el-form label-position="top">
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item :label="t('visitor.handover.sampleNo')" required>
            <el-input v-model="form.sample_no" :maxlength="64" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('visitor.handover.sampleName')">
            <el-input v-model="form.sample_name" :maxlength="128" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item :label="t('visitor.handover.barcode')">
            <el-input v-model="form.barcode" :maxlength="64" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('visitor.handover.sampleType')">
            <el-select v-model="form.sample_type" style="width: 100%">
              <el-option :label="t('visitor.handover.typeSample')" value="sample" />
              <el-option :label="t('visitor.handover.typeVehicle')" value="vehicle" />
              <el-option :label="t('visitor.handover.typeModel')" value="model" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="12">
        <el-col :span="8">
          <el-form-item :label="t('visitor.handover.qty')">
            <el-input-number v-model="form.qty" :min="1" :max="9999" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('visitor.handover.handoverUserName')">
            <el-input v-model="form.handover_user_name" :maxlength="64" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('visitor.handover.receiveUserName')">
            <el-input v-model="form.receive_user_name" :maxlength="64" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item :label="t('visitor.handover.bindVisit')">
        <el-input-number v-model="form.visit_id" :min="1" style="width: 100%" />
      </el-form-item>
      <el-form-item :label="t('common.form.remark')">
        <el-input v-model="form.remark" type="textarea" :rows="2" :maxlength="2000" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="createVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" @click="submit">{{ t('common.action.submit') }}</el-button>
    </template>
  </el-dialog>
</template>
