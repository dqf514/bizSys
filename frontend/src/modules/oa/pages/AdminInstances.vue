<script setup lang="ts">
/** OA 流程处理（管理侧）：全量单据检索（关键字/状态/滞留天数）+ 强制结束 / 改派审批人 / 拉回节点。 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { useListPage } from '@/composables/useListPage'
import {
  listOaAdminInstances,
  reassignOaInstance,
  restartOaInstance,
  terminateOaInstance,
} from '@/api/oa'
import { listUsers } from '@/api/admin'
import type { AdminUser, OaInstanceItem } from '@/api/types'

defineOptions({ name: 'AdminInstances' })

const { t } = useI18n()

const searchModel = ref<Record<string, any>>({ keyword: '', stuckDays: undefined })
const searchFields: SearchField[] = [
  { key: 'keyword', labelKey: 'oa.handle.keyword', width: 220 },
  { key: 'stuckDays', labelKey: 'oa.handle.stuckDays', width: 140 },
]

const activeStatus = ref('all')
const statusTabs = computed<StatusTabItem[]>(() => [
  { value: 'all', labelKey: 'common.action.all' },
  { value: 'running', label: t('oa.status.running') },
  { value: 'approved', label: t('oa.status.approved') },
  { value: 'rejected', label: t('oa.status.rejected') },
  { value: 'withdrawn', label: t('oa.status.withdrawn') },
  { value: 'terminated', label: t('oa.status.terminated') },
])

const list = useListPage<OaInstanceItem>({
  fetch: async (params) => {
    const data = await listOaAdminInstances({
      ...params,
      status: activeStatus.value === 'all' ? '' : activeStatus.value,
      keyword: searchModel.value.keyword || undefined,
      stuckDays: Number(searchModel.value.stuckDays) > 0 ? Number(searchModel.value.stuckDays) : undefined,
    })
    return { items: data.items, total: data.total ?? 0 }
  },
  defaultStatus: 'all',
})

const columns: ListColumn[] = [
  { prop: 'displayNo', labelKey: 'oa.my.displayNo', width: 150, fixed: 'left' },
  { prop: 'formName', labelKey: 'oa.my.formName', minWidth: 120 },
  { prop: 'applicantName', labelKey: 'approval.approval.initiatorName', width: 100 },
  { prop: 'status', labelKey: 'oa.my.status', width: 96 },
  { prop: 'pendingNames', labelKey: 'oa.my.pendingNames', minWidth: 120 },
  { prop: 'createTime', labelKey: 'oa.my.createTime', width: 165 },
  { prop: 'finishedAt', labelKey: 'oa.my.finishedAt', width: 165 },
]

function switchStatus(v: string) {
  activeStatus.value = v
  list.query.page = 1
  list.refresh()
}

/* ---------- 强制结束 ---------- */
async function doTerminate(row: OaInstanceItem) {
  let comment = ''
  try {
    const r = await ElMessageBox.prompt(t('oa.handle.terminatePrompt'), t('oa.handle.terminateTitle'), {
      inputPlaceholder: t('oa.handle.comment'),
      inputValidator: (v: string) => Boolean(v?.trim()) || t('oa.handle.comment'),
    })
    comment = r.value.trim()
  } catch {
    return
  }
  try {
    await terminateOaInstance(row.id, comment)
    ElMessage.success(t('oa.handle.terminateDone'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

/* ---------- 改派 ---------- */
const reassignVisible = ref(false)
const reassignRow = ref<OaInstanceItem | null>(null)
const reassignTaskId = ref<number | null>(null)
const reassignUserId = ref<number | null>(null)
const reassignComment = ref('')
const reassignLoading = ref(false)
const userOptions = ref<AdminUser[]>([])

async function openReassign(row: OaInstanceItem) {
  reassignRow.value = row
  reassignTaskId.value = row.pendingTasks[0]?.id ?? null
  reassignUserId.value = null
  reassignComment.value = ''
  reassignVisible.value = true
  if (!userOptions.value.length) {
    try {
      const data = await listUsers({ page: 1, size: 200, status: 'enabled' })
      userOptions.value = data.items
    } catch {
      /* http notifies */
    }
  }
}

async function doReassign() {
  if (!reassignRow.value || !reassignTaskId.value || !reassignUserId.value) return
  reassignLoading.value = true
  try {
    await reassignOaInstance(reassignRow.value.id, reassignTaskId.value, reassignUserId.value, reassignComment.value)
    ElMessage.success(t('oa.handle.reassignDone'))
    reassignVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  } finally {
    reassignLoading.value = false
  }
}

/* ---------- 拉回节点 ---------- */
const restartVisible = ref(false)
const restartRow = ref<OaInstanceItem | null>(null)
const restartSeq = ref(1)
const restartComment = ref('')
const restartLoading = ref(false)

function openRestart(row: OaInstanceItem) {
  restartRow.value = row
  restartSeq.value = 1
  restartComment.value = ''
  restartVisible.value = true
}

async function doRestart() {
  if (!restartRow.value) return
  restartLoading.value = true
  try {
    await restartOaInstance(restartRow.value.id, restartSeq.value, restartComment.value)
    ElMessage.success(t('oa.handle.restartDone'))
    restartVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  } finally {
    restartLoading.value = false
  }
}

const canIntervene = (row: OaInstanceItem) => row.status === 'running' && row.flowInstanceId > 0

onMounted(() => list.refresh())
</script>

<template>
  <ListPage :title="t('oa.handle.title')" :loading="list.loading.value">
    <template #actions>
      <el-button @click="list.refresh()">{{ t('common.action.refresh') }}</el-button>
    </template>

    <template #searchBar>
      <SearchBar
        v-model="searchModel"
        :fields="searchFields"
        @search="list.search()"
        @reset="searchModel = { keyword: '', stuckDays: undefined }; list.reset()"
      />
    </template>

    <template #statusTabs>
      <StatusTabs :tabs="statusTabs" :model-value="activeStatus" @update:model-value="switchStatus" />
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
        <template #status="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="oa.status" />
        </template>
        <template #pendingNames="{ row }">{{ row.pendingNames || '-' }}</template>
        <template #extraColumns>
          <el-table-column :label="t('common.action.operate')" width="220" fixed="right">
            <template #default="{ row }">
              <template v-if="canIntervene(row as OaInstanceItem)">
                <el-button link type="danger" @click="doTerminate(row as OaInstanceItem)">{{ t('oa.handle.terminate') }}</el-button>
                <el-button link type="primary" :disabled="!(row as OaInstanceItem).pendingTasks?.length" @click="openReassign(row as OaInstanceItem)">
                  {{ t('oa.handle.reassign') }}
                </el-button>
                <el-button link type="warning" @click="openRestart(row as OaInstanceItem)">{{ t('oa.handle.restart') }}</el-button>
              </template>
              <span v-else class="no-op">-</span>
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <el-dialog v-model="reassignVisible" :title="t('oa.handle.reassignTitle')" width="440px">
    <el-form label-width="110px">
      <el-form-item :label="t('oa.handle.reassignTask')">
        <el-select v-model="reassignTaskId" style="width: 100%">
          <el-option
            v-for="tk in reassignRow?.pendingTasks ?? []"
            :key="tk.id"
            :value="tk.id"
            :label="`${tk.nodeName} / ${tk.assigneeName}`"
          />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('oa.handle.reassignTo')">
        <el-select v-model="reassignUserId" filterable style="width: 100%">
          <el-option v-for="u in userOptions" :key="u.id" :value="u.id" :label="`${u.name || u.username} (${u.username})`" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('oa.handle.comment')">
        <el-input v-model="reassignComment" type="textarea" :rows="2" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="reassignVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="reassignLoading" :disabled="!reassignTaskId || !reassignUserId" @click="doReassign">
        {{ t('common.action.confirm') }}
      </el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="restartVisible" :title="t('oa.handle.restartTitle')" width="440px">
    <el-form label-width="110px">
      <el-form-item :label="t('oa.handle.restartSeq')">
        <el-input-number v-model="restartSeq" :min="1" :max="99" />
      </el-form-item>
      <el-form-item :label="t('oa.handle.comment')">
        <el-input v-model="restartComment" type="textarea" :rows="2" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="restartVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="restartLoading" @click="doRestart">{{ t('common.action.confirm') }}</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.no-op {
  color: var(--bs-color-fg-muted);
}
</style>
