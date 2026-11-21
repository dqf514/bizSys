<script setup lang="ts">
/** 通行凭证（B3）：门禁 / 闸机 / 梯控核验（放行与否 + 审计留痕）+ 凭证作废。 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { useListPage } from '@/composables/useListPage'
import { listVisitorCredentials, revokeVisitorCredential, verifyVisitorCredential } from '@/api/visitor'
import type { VisitorCredential } from '@/api/types'

defineOptions({ name: 'CredentialList' })

const { t } = useI18n()

const searchModel = ref<Record<string, any>>({ q: '' })
const searchFields = computed<SearchField[]>(() => [
  {
    key: 'q',
    labelKey: 'visitor.credential.searchName',
    placeholderKey: 'visitor.credential.placeholderName',
    width: 260,
  },
])

const list = useListPage<VisitorCredential>({
  fetch: async (params) => {
    const data = await listVisitorCredentials({ ...params, q: searchModel.value.q || undefined })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
})

const columns: ListColumn[] = [
  { prop: 'credentialNo', labelKey: 'visitor.credential.credentialNo', width: 175, fixed: 'left' },
  { prop: 'visitorName', labelKey: 'visitor.credential.visitorName', width: 120 },
  { prop: 'credentialTypeText', labelKey: 'visitor.credential.credentialType', width: 110 },
  { prop: 'zoneNames', labelKey: 'visitor.credential.zoneNames', minWidth: 150 },
  { prop: 'validFrom', labelKey: 'visitor.credential.validFrom', width: 160 },
  { prop: 'validTo', labelKey: 'visitor.credential.validTo', width: 160 },
  { prop: 'usedCount', labelKey: 'visitor.credential.usedCount', width: 100, align: 'center' },
  { prop: 'status', labelKey: 'visitor.credential.status', width: 100, sortable: 'status' },
]

function rowActions(row: VisitorCredential): ActionItem[] {
  const acts: ActionItem[] = []
  if (row.status === 'issued' || row.status === 'used') {
    acts.push({ key: 'revoke', tip: 'visitor.credential.revoke', icon: 'TurnOff', danger: true, perm: 'visitor:credential:edit' })
  }
  return acts
}

/* ---------------- 核验 ---------------- */
const verifyVisible = ref(false)
const form = ref<Record<string, any>>({
  credential_no: '',
  zone_id: null as number | null,
  method: 'qrcode',
  device_id: '',
  direction: 'in',
})
const result = ref<{ pass: boolean; reason: string } | null>(null)

function openVerify(row?: VisitorCredential) {
  form.value = {
    credential_no: row?.credentialNo || '',
    zone_id: null,
    method: 'qrcode',
    device_id: '',
    direction: 'in',
  }
  result.value = null
  verifyVisible.value = true
}

async function submitVerify() {
  if (!form.value.credential_no) {
    ElMessage.warning(t('common.form.required'))
    return
  }
  try {
    const r = await verifyVisitorCredential({
      credential_no: form.value.credential_no,
      zone_id: form.value.zone_id,
      method: form.value.method,
      device_id: form.value.device_id,
      direction: form.value.direction,
    })
    result.value = { pass: r.pass, reason: r.reason }
    list.refresh()
  } catch {
    /* http notifies */
  }
}

async function doRevoke(row: VisitorCredential) {
  try {
    await revokeVisitorCredential(row.id)
    ElMessage.success(t('common.message.submitSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

function onRowAction(key: string, row: VisitorCredential) {
  if (key === 'revoke') void doRevoke(row)
}
</script>

<template>
  <ListPage :title="t('visitor.credential.title')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'visitor:credential:verify'" type="primary" @click="openVerify()">
        {{ t('visitor.credential.verify') }}
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
        <template #credentialTypeText="{ row }">
          {{ row.credentialTypeText || row.credentialType || '-' }}
        </template>
        <template #status="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="visitor.credential.status" />
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
                :actions="rowActions(row as unknown as VisitorCredential)"
                @select="(k) => onRowAction(k, row as unknown as VisitorCredential)"
              />
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <el-dialog v-model="verifyVisible" :width="'var(--bs-layout-dialog-sm)'" :title="t('visitor.credential.verifyTitle')">
    <el-form label-position="top">
      <el-form-item :label="t('visitor.credential.credentialNo')" required>
        <el-input v-model="form.credential_no" :maxlength="32" />
      </el-form-item>
      <el-form-item :label="t('visitor.zone.name')">
        <el-input-number v-model="form.zone_id" :min="1" style="width: 100%" />
      </el-form-item>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item :label="t('visitor.credential.method')">
            <el-select v-model="form.method" style="width: 100%">
              <el-option label="QR Code" value="qrcode" />
              <el-option label="Face" value="face" />
              <el-option label="IC Card" value="ic" />
              <el-option label="Plate" value="plate" />
              <el-option label="Manual" value="manual" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('visitor.credential.direction')">
            <el-select v-model="form.direction" style="width: 100%">
              <el-option :label="t('visitor.credential.directionIn')" value="in" />
              <el-option :label="t('visitor.credential.directionOut')" value="out" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item :label="t('visitor.credential.deviceId')">
        <el-input v-model="form.device_id" :maxlength="64" />
      </el-form-item>
    </el-form>
    <el-alert
      v-if="result"
      :type="result.pass ? 'success' : 'error'"
      :closable="false"
      show-icon
      :title="result.pass ? t('visitor.credential.resultPass') : t('visitor.credential.resultDeny')"
      :description="result.reason"
    />
    <template #footer>
      <el-button @click="verifyVisible = false">{{ t('common.action.close') }}</el-button>
      <el-button type="primary" @click="submitVerify">{{ t('common.action.confirm') }}</el-button>
    </template>
  </el-dialog>
</template>
