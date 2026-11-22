<script setup lang="ts">
/** 保密协议（NDA）电子签（B3）：签署留证（存证哈希防篡改）+ 作废。 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import SignaturePad from '@/components/common/SignaturePad.vue'
import { useListPage } from '@/composables/useListPage'
import { listVisitorNdas, revokeVisitorNda, signVisitorNda, visitorNdaCounts } from '@/api/visitor'
import type { VisitorNda } from '@/api/types'

defineOptions({ name: 'NdaList' })

const { t } = useI18n()

const searchModel = ref<Record<string, any>>({ q: '' })
const searchFields = computed<SearchField[]>(() => [
  {
    key: 'q',
    labelKey: 'visitor.nda.searchName',
    placeholderKey: 'visitor.nda.placeholderName',
    width: 260,
  },
])

const statusTabs = ref<StatusTabItem[]>([
  { value: 'all', labelKey: 'common.action.all', count: 0 },
  { value: 'signed', labelKey: 'visitor.nda.statusSigned', count: 0 },
  { value: 'expired', labelKey: 'visitor.nda.statusExpired', count: 0 },
  { value: 'revoked', labelKey: 'visitor.nda.statusRevoked', count: 0 },
])

const counts = ref<Record<string, number>>({})

async function loadCounts() {
  try {
    counts.value = (await visitorNdaCounts()) ?? {}
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

const list = useListPage<VisitorNda>({
  fetch: async (params) => {
    const data = await listVisitorNdas({ ...params, q: searchModel.value.q || undefined })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  defaultStatus: 'all',
  onLoaded: () => {
    void loadCounts()
  },
})

const columns: ListColumn[] = [
  { prop: 'ndaNo', labelKey: 'visitor.nda.ndaNo', width: 170, fixed: 'left' },
  { prop: 'title', labelKey: 'visitor.nda.title2', minWidth: 170 },
  { prop: 'visitorName', labelKey: 'visitor.nda.visitorName', width: 110 },
  { prop: 'visitorCompany', labelKey: 'visitor.nda.visitorCompany', minWidth: 150 },
  { prop: 'signerTitle', labelKey: 'visitor.nda.signerTitle', width: 110 },
  { prop: 'signedAt', labelKey: 'visitor.nda.signedAt', width: 160, sortable: 'signed_at' },
  { prop: 'validTo', labelKey: 'visitor.nda.validTo', width: 160 },
  { prop: 'status', labelKey: 'visitor.nda.status', width: 100, sortable: 'status' },
]

function rowActions(row: VisitorNda): ActionItem[] {
  const acts: ActionItem[] = []
  if (row.status === 'signed') {
    acts.push({ key: 'revoke', tip: 'visitor.nda.revoke', icon: 'TurnOff', danger: true, perm: 'visitor:nda:sign' })
  }
  return acts
}

/* ---------------- 签署 ---------------- */
const signVisible = ref(false)
const form = ref<Record<string, any>>({
  title: '',
  template: 'standard',
  visitor_name: '',
  visitor_company: '',
  signer_title: '',
  id_no: '',
  signature_data: '',
  visit_id: null as number | null,
  remark: '',
})

function openSign() {
  form.value = {
    title: '',
    template: 'standard',
    visitor_name: '',
    visitor_company: '',
    signer_title: '',
    id_no: '',
    signature_data: '',
    visit_id: null,
    remark: '',
  }
  signVisible.value = true
}

async function submitSign() {
  const f = form.value
  if (!f.visitor_name) {
    ElMessage.warning(t('common.form.required'))
    return
  }
  if (!f.signature_data) {
    ElMessage.warning(t('visitor.nda.signatureRequired'))
    return
  }
  try {
    await signVisitorNda({
      title: f.title,
      template: f.template,
      visitor_name: f.visitor_name,
      visitor_company: f.visitor_company,
      signer_title: f.signer_title,
      id_no: f.id_no,
      signature_data: f.signature_data,
      visit_id: f.visit_id,
      remark: f.remark,
    })
    ElMessage.success(t('common.message.createSuccess'))
    signVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  }
}

async function doRevoke(row: VisitorNda) {
  try {
    await revokeVisitorNda(row.id)
    ElMessage.success(t('common.message.submitSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

function onRowAction(key: string, row: VisitorNda) {
  if (key === 'revoke') void doRevoke(row)
}
</script>

<template>
  <ListPage :title="t('visitor.nda.title')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'visitor:nda:sign'" type="primary" @click="openSign">
        {{ t('visitor.nda.sign') }}
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
          <StatusTag :status="String(row.status)" i18n-prefix="visitor.nda.status" />
        </template>
        <template #extraColumns>
          <el-table-column
            :label="t('common.action.operate')"
            width="110"
            fixed="right"
            align="center"
            header-align="center"
          >
            <template #default="{ row }">
              <ActionBar
                :actions="rowActions(row as unknown as VisitorNda)"
                @select="(k) => onRowAction(k, row as unknown as VisitorNda)"
              />
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <el-dialog v-model="signVisible" :width="'var(--bs-layout-dialog-md)'" :title="t('visitor.nda.signTitle')">
    <el-form label-position="top">
      <el-form-item :label="t('visitor.nda.title2')">
        <el-input v-model="form.title" :maxlength="128" />
      </el-form-item>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item :label="t('visitor.nda.visitorName')" required>
            <el-input v-model="form.visitor_name" :maxlength="64" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('visitor.nda.visitorCompany')">
            <el-input v-model="form.visitor_company" :maxlength="128" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item :label="t('visitor.nda.signerTitle')">
            <el-input v-model="form.signer_title" :maxlength="64" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('visitor.nda.idNo')">
            <el-input v-model="form.id_no" :maxlength="64" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item :label="t('visitor.nda.signature')" required>
        <SignaturePad v-model="form.signature_data" :height="180" />
      </el-form-item>
      <el-form-item :label="t('visitor.nda.bindVisit')">
        <el-input-number v-model="form.visit_id" :min="1" style="width: 100%" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="signVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" @click="submitSign">{{ t('common.action.submit') }}</el-button>
    </template>
  </el-dialog>
</template>
