<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ActionBar from '@/components/list/ActionBar.vue'
import ExportButton from '@/components/list/ExportButton.vue'
import { useListPage } from '@/composables/useListPage'
import {
  createAuditAnchor,
  exportAuditLogs,
  getAuditEvidence,
  listAuditLogs,
  verifyAuditChain,
} from '@/api/admin'
import type { AuditChainVerifyResult, AuditEvidenceDetail, AuditLog } from '@/api/types'

defineOptions({ name: 'AuditLogList' })

const { t } = useI18n()

const searchModel = ref<Record<string, any>>({ q: '' })
const searchFields: SearchField[] = [
  { key: 'q', labelKey: 'admin.audit.username', width: 180 },
  { key: 'module', labelKey: 'admin.audit.module', width: 140 },
]

const list = useListPage<AuditLog>({
  fetch: async (params) => {
    const data = await listAuditLogs({
      ...params,
      q: searchModel.value.q || undefined,
      filters: { module: searchModel.value.module || undefined },
    })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
})

const columns: ListColumn[] = [
  { prop: 'chainSeq', labelKey: 'admin.audit.chainSeq', width: 90 },
  { prop: 'username', labelKey: 'admin.audit.username', width: 110 },
  { prop: 'module', labelKey: 'admin.audit.module', width: 100, sortable: 'module' },
  { prop: 'action', labelKey: 'admin.audit.action', width: 140, sortable: 'action' },
  { prop: 'bizType', labelKey: 'admin.audit.bizType', width: 100 },
  { prop: 'bizId', labelKey: 'admin.audit.bizId', width: 90 },
  { prop: 'fieldName', labelKey: 'admin.audit.fieldName', width: 120 },
  { prop: 'oldValue', labelKey: 'admin.audit.oldValue', minWidth: 140 },
  { prop: 'newValue', labelKey: 'admin.audit.newValue', minWidth: 140 },
  { prop: 'reason', labelKey: 'admin.audit.reason', minWidth: 140 },
  { prop: 'ip', labelKey: 'admin.audit.ip', width: 120 },
  { prop: 'createTime', labelKey: 'admin.audit.createTime', width: 160, sortable: 'create_time' },
]

/* ---------------- 详情（字段级证据） ---------------- */

const detailVisible = ref(false)
const detailRow = ref<AuditLog | null>(null)
const evidence = ref<AuditEvidenceDetail | null>(null)
const evidenceLoading = ref(false)

async function viewDetail(row: AuditLog) {
  detailRow.value = row
  detailVisible.value = true
  evidence.value = null
  evidenceLoading.value = true
  try {
    evidence.value = await getAuditEvidence(row.id)
  } catch {
    evidence.value = null
  } finally {
    evidenceLoading.value = false
  }
}

/* ---------------- 链校验面板 ---------------- */

const chainVisible = ref(false)
const chainLoading = ref(false)
const chain = ref<AuditChainVerifyResult | null>(null)
const chainMode = ref<'full' | 'since_anchor'>('full')

async function runVerify(mode: 'full' | 'since_anchor' = chainMode.value) {
  chainMode.value = mode
  chainLoading.value = true
  try {
    chain.value = await verifyAuditChain({ mode })
    if (chain.value?.ok) ElMessage.success(t('admin.audit.chainOk'))
    else ElMessage.warning(t('admin.audit.chainBroken'))
  } catch {
    chain.value = null
  } finally {
    chainLoading.value = false
  }
}

async function doAnchor() {
  try {
    await ElMessageBox.confirm(t('admin.audit.anchorConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await createAuditAnchor()
    ElMessage.success(t('admin.audit.anchorDone'))
    void runVerify(chainMode.value)
  } catch {
    /* http notifies */
  }
}

function brokenReasonLabel(reason: string) {
  const map: Record<string, string> = {
    seq_gap: 'admin.audit.reasonSeqGap',
    prev_hash_mismatch: 'admin.audit.reasonPrevMismatch',
    row_hash_mismatch: 'admin.audit.reasonRowMismatch',
    head_mismatch: 'admin.audit.reasonHeadMismatch',
  }
  return map[reason] ? t(map[reason]) : reason
}
</script>

<template>
  <ListPage :title="t('admin.audit.title')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'admin:audit:list'" @click="chainVisible = true">
        {{ t('admin.audit.chainPanel') }}
      </el-button>
      <ExportButton
        v-permission="'admin:audit:list'"
        :export-fn="() =>
          exportAuditLogs({ q: searchModel.q || undefined, filters: { module: searchModel.module || undefined } })
        "
      />
      <el-button @click="list.refresh()">{{ t('common.action.refresh') }}</el-button>
    </template>

    <template #searchBar>
      <SearchBar
        v-model="searchModel"
        :fields="searchFields"
        @search="list.search()"
        @reset="searchModel = { q: '', module: '' }; list.reset()"
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
        @update:page="list.setPage"
        @update:size="list.setSize"
        @sort-change="list.onSortChange"
      >
        <template #chainSeq="{ row }">
          <span v-if="row.chainSeq">#{{ row.chainSeq }}</span>
          <span v-else class="legacy-mark">{{ t('admin.audit.legacyRow') }}</span>
        </template>
        <template #oldValue="{ row }">
          <span class="value-old">{{ row.oldValue || '-' }}</span>
        </template>
        <template #newValue="{ row }">
          <span class="value-new">{{ row.newValue || '-' }}</span>
        </template>
        <template #extraColumns>
          <el-table-column :label="t('common.action.operate')" width="90" fixed="right" align="center" header-align="center">
            <template #default="{ row }">
              <ActionBar :actions="[{ key: 'view', tip: 'admin.audit.viewDetail' }]" @select="viewDetail(row as unknown as AuditLog)" />
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <!-- 证据详情 -->
  <el-drawer v-model="detailVisible" size="var(--bs-layout-drawer-md)">
    <template #header>
      <span class="drawer-title">{{ t('admin.audit.viewDetail') }}</span>
    </template>
    <div v-loading="evidenceLoading" class="drawer-body">
      <el-descriptions v-if="detailRow" :column="1" border size="small">
        <el-descriptions-item :label="t('admin.audit.username')">{{ detailRow.username }}</el-descriptions-item>
        <el-descriptions-item :label="t('admin.audit.module')">{{ detailRow.module }}</el-descriptions-item>
        <el-descriptions-item :label="t('admin.audit.action')">{{ detailRow.action }}</el-descriptions-item>
        <el-descriptions-item :label="t('admin.audit.fieldName')">
          {{ detailRow.fieldName || '-' }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('admin.audit.oldValue')">
          {{ detailRow.oldValue || '-' }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('admin.audit.newValue')">
          {{ detailRow.newValue || '-' }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('admin.audit.reason')">
          {{ detailRow.reason || '-' }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('admin.audit.userAgent')">
          {{ detailRow.userAgent || '-' }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('admin.audit.traceId')">{{ detailRow.traceId || '-' }}</el-descriptions-item>
        <el-descriptions-item :label="t('admin.audit.ip')">{{ detailRow.ip }}</el-descriptions-item>
        <el-descriptions-item :label="t('admin.audit.detail')">
          <pre class="detail-pre">{{ detailRow.detail }}</pre>
        </el-descriptions-item>
      </el-descriptions>

      <section v-if="evidence" class="drawer-section">
        <h4 class="section-title">{{ t('admin.audit.chainEvidence') }}</h4>
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item :label="t('admin.audit.chainSeq')">
            {{ evidence.chainSeq ?? '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('admin.audit.hashAlg')">
            {{ evidence.hashAlg || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('admin.audit.prevHash')">
            <span class="hash-text">{{ evidence.prevHash || '-' }}</span>
          </el-descriptions-item>
          <el-descriptions-item :label="t('admin.audit.rowHash')">
            <span class="hash-text">{{ evidence.rowHash || '-' }}</span>
          </el-descriptions-item>
          <el-descriptions-item :label="t('admin.audit.recalculatedHash')">
            <span class="hash-text">{{ evidence.recalculatedHash || '-' }}</span>
          </el-descriptions-item>
          <el-descriptions-item :label="t('admin.audit.hashValid')">
            <el-tag
              v-if="evidence.chainSeq"
              :type="evidence.hashValid ? 'success' : 'danger'"
              size="small"
              effect="light"
              round
            >
              {{ evidence.hashValid ? t('admin.audit.hashValidYes') : t('admin.audit.hashValidNo') }}
            </el-tag>
            <span v-else class="legacy-mark">{{ t('admin.audit.legacyRow') }}</span>
          </el-descriptions-item>
        </el-descriptions>
      </section>
    </div>
  </el-drawer>

  <!-- 链校验面板 -->
  <el-dialog v-model="chainVisible" :title="t('admin.audit.chainPanel')" width="var(--bs-layout-dialog-lg)" append-to-body>
    <div class="chain-toolbar">
      <el-radio-group v-model="chainMode" size="small">
        <el-radio-button value="full">{{ t('admin.audit.chainModeFull') }}</el-radio-button>
        <el-radio-button value="since_anchor">{{ t('admin.audit.chainModeSinceAnchor') }}</el-radio-button>
      </el-radio-group>
      <el-button type="primary" :loading="chainLoading" @click="runVerify()">
        {{ t('admin.audit.chainVerify') }}
      </el-button>
      <el-button @click="doAnchor">{{ t('admin.audit.anchor') }}</el-button>
    </div>

    <div v-loading="chainLoading" class="chain-body">
      <template v-if="chain">
        <el-alert
          :type="chain.ok ? 'success' : 'error'"
          :title="chain.ok ? t('admin.audit.chainOk') : t('admin.audit.chainBroken')"
          :closable="false"
          show-icon
        />
        <el-descriptions :column="2" border size="small" class="chain-desc">
          <el-descriptions-item :label="t('admin.audit.chainChecked')">{{ chain.checked }}</el-descriptions-item>
          <el-descriptions-item :label="t('admin.audit.chainRange')">
            {{ chain.firstSeq ?? '-' }} → {{ chain.lastSeq ?? '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('admin.audit.headSeq')">{{ chain.headSeq }}</el-descriptions-item>
          <el-descriptions-item :label="t('admin.audit.hashAlg')">{{ chain.hashAlg }}</el-descriptions-item>
          <el-descriptions-item :label="t('admin.audit.legacyRowCount')">{{ chain.legacyRows }}</el-descriptions-item>
          <el-descriptions-item :label="t('admin.audit.writeFailures')">{{ chain.writeFailures }}</el-descriptions-item>
        </el-descriptions>

        <section v-if="chain.brokenAt" class="chain-section">
          <h4 class="section-title">{{ t('admin.audit.brokenAt') }}</h4>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item :label="t('admin.audit.chainSeq')">
              {{ chain.brokenAt.seq ?? '-' }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('admin.audit.bizId')">
              {{ chain.brokenAt.rowId ?? '-' }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('admin.audit.brokenReason')">
              {{ brokenReasonLabel(chain.brokenAt.reason) }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('admin.audit.expected')">
              <span class="hash-text">{{ chain.brokenAt.expected || '-' }}</span>
            </el-descriptions-item>
            <el-descriptions-item :label="t('admin.audit.actual')">
              <span class="hash-text">{{ chain.brokenAt.actual || '-' }}</span>
            </el-descriptions-item>
          </el-descriptions>
        </section>

        <section v-if="chain.anchor" class="chain-section">
          <h4 class="section-title">{{ t('admin.audit.anchorInfo') }}</h4>
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item :label="t('admin.audit.chainSeq')">{{ chain.anchor.seq }}</el-descriptions-item>
            <el-descriptions-item :label="t('admin.audit.anchorAt')">{{ chain.anchor.at }}</el-descriptions-item>
            <el-descriptions-item :label="t('admin.audit.anchorMatch')">
              <el-tag
                v-if="chain.anchor.match !== null"
                :type="chain.anchor.match ? 'success' : 'danger'"
                size="small"
                effect="light"
                round
              >
                {{ chain.anchor.match ? t('admin.audit.hashValidYes') : t('admin.audit.hashValidNo') }}
              </el-tag>
              <span v-else>-</span>
            </el-descriptions-item>
            <el-descriptions-item :label="t('admin.audit.anchorTruncated')">
              {{ chain.anchor.truncated ? t('common.action.yes') : t('common.action.no') }}
            </el-descriptions-item>
          </el-descriptions>
        </section>
      </template>
      <el-empty v-else :description="t('admin.audit.chainNotRun')" :image-size="60" />
    </div>
  </el-dialog>
</template>

<style scoped>
.legacy-mark {
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs);
}

.value-old {
  color: var(--bs-color-fg-muted);
  text-decoration: line-through;
}

.value-new {
  color: var(--bs-color-fg-default);
  font-weight: 600;
}

.drawer-title {
  font-size: var(--bs-typography-font-size-lg);
  font-weight: 600;
}

.drawer-body {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-3);
}

.drawer-section,
.chain-section {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
}

.section-title {
  margin: 0;
  font-size: var(--bs-typography-font-size-md);
  font-weight: 600;
}

.detail-pre {
  margin: 0;
  max-height: 240px;
  overflow: auto;
  font-family: var(--bs-typography-font-family-mono);
  font-size: var(--bs-typography-font-size-xs);
  white-space: pre-wrap;
  word-break: break-all;
}

.hash-text {
  font-family: var(--bs-typography-font-family-mono);
  font-size: var(--bs-typography-font-size-xs);
  word-break: break-all;
}

.chain-toolbar {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  flex-wrap: wrap;
  margin-bottom: var(--bs-space-3);
}

.chain-body {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-3);
}

.chain-desc {
  margin-top: var(--bs-space-2);
}
</style>
