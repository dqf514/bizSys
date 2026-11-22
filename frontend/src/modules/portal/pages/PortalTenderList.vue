<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Check, Filter, Search } from '@element-plus/icons-vue'
import StatusTag from '@/components/common/StatusTag.vue'
import PortalTenderDetailPanel from './PortalTenderDetailPanel.vue'
import { listPortalTenders } from '@/api/portal'
import { getPortalToken } from '@/api/portalHttp'
import { useDeadline } from '../useDeadline'
import { useIsMobile } from '@/composables/useIsMobile'
import type { PortalTender } from '@/api/types'

defineOptions({ name: 'PortalTenderList' })

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const { deadlineText, isUrgent } = useDeadline()
const { isMobile } = useIsMobile()

const loading = ref(false)
const items = ref<PortalTender[]>([])
const loggedIn = ref(Boolean(getPortalToken()))

/* ---- 本地检索 / 状态筛选（公告为小体量全量列表，本地过滤即可） ---- */
const keyword = ref('')
const statusFilter = ref('')

const STATUS_OPTIONS = ['published', 'evaluating', 'awarding', 'awarded']

/* ---- 移动端筛选：底部弹层（桌面用筛选 chip 行） ---- */
const filterSheetVisible = ref(false)
const pendingStatus = ref('')

function openFilterSheet() {
  pendingStatus.value = statusFilter.value
  filterSheetVisible.value = true
}

function applyFilter() {
  statusFilter.value = pendingStatus.value
  filterSheetVisible.value = false
}

function resetFilter() {
  pendingStatus.value = ''
}

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return items.value.filter((it) => {
    if (statusFilter.value && it.status !== statusFilter.value) return false
    if (!kw) return true
    return (
      String(it.name ?? '').toLowerCase().includes(kw) ||
      String(it.tenderNo ?? '').toLowerCase().includes(kw)
    )
  })
})

/* ---- 选中态与路由 ?id= 同步（旧 /portal/tenders/:id 已重定向至此） ---- */
const selectedId = computed(() => {
  const raw = Number(route.query.id)
  return Number.isFinite(raw) && raw > 0 ? raw : 0
})

function select(id: number) {
  router.replace({ path: '/portal/tenders', query: id ? { id: String(id) } : {} })
}

onMounted(async () => {
  loading.value = true
  try {
    const data = await listPortalTenders()
    items.value = data.items ?? []
    // 桌面端默认选中第一条，右侧直接呈现详情
    if (!selectedId.value && !isMobile.value && items.value.length) {
      const first = items.value[0]
      if (first) select(first.id)
    }
  } catch {
    items.value = []
  } finally {
    loading.value = false
  }
})

// 筛选结果变化后，若当前选中项被过滤掉则清空选中（移动端回列表）
watch(filtered, (list) => {
  if (selectedId.value && !list.some((it) => it.id === selectedId.value)) select(0)
})
</script>

<template>
  <div v-loading="loading" class="tenders-layout" :class="{ 'show-detail': selectedId }">
    <!-- 左：公告清单 -->
    <aside class="tender-list-panel">
      <div class="list-head">
        <h2 class="bs-page-title">{{ t('portal.portal.tenders') }}</h2>
        <span class="list-count">{{ filtered.length }}</span>
      </div>
      <el-input
        v-model="keyword"
        :prefix-icon="Search"
        :placeholder="t('common.form.placeholderSearch')"
        clearable
        class="list-search"
      />
      <div v-if="isMobile" class="filter-trigger-row">
        <button type="button" class="filter-trigger" @click="openFilterSheet">
          <el-icon><Filter /></el-icon>
          <span>{{ t('portal.portal.filter') }}</span>
          <span v-if="statusFilter" class="filter-trigger-value">
            {{ t(`common.status.${statusFilter}`) }}
          </span>
        </button>
      </div>
      <div v-else class="list-filter">
        <button
          type="button"
          class="filter-chip"
          :class="{ active: !statusFilter }"
          @click="statusFilter = ''"
        >
          {{ t('common.status.all') }}
        </button>
        <button
          v-for="s in STATUS_OPTIONS"
          :key="s"
          type="button"
          class="filter-chip"
          :class="{ active: statusFilter === s }"
          @click="statusFilter = s"
        >
          {{ t(`common.status.${s}`) }}
        </button>
      </div>

      <div class="tender-cards">
        <button
          v-for="it in filtered"
          :key="it.id"
          type="button"
          class="tender-card"
          :class="{ active: it.id === selectedId }"
          @click="select(it.id)"
        >
          <div class="card-top">
            <span class="card-name">{{ it.name }}</span>
            <StatusTag :status="String(it.status)" i18n-prefix="common.status" />
          </div>
          <div class="card-no">{{ it.tenderNo }} · {{ it.tenderMethod === 'invite' ? t('portal.portal.methodInvite') : t('portal.portal.methodPublic') }}</div>
          <div class="card-meta">
            <span v-if="it.status === 'published' && deadlineText(it.regDeadline)" class="card-deadline" :class="{ urgent: isUrgent(it.regDeadline) }">
              {{ t('portal.portal.regDeadline') }} {{ deadlineText(it.regDeadline) }}
            </span>
            <span v-else-if="it.status === 'awarded' && it.winnerName" class="card-winner">
              {{ t('portal.portal.winner') }}: {{ it.winnerName }}
            </span>
            <span v-else class="card-deadline-plain">{{ it.regDeadline || '-' }}</span>
          </div>
          <div v-if="loggedIn && (it.isWinner || it.myRegistrationStatus)" class="card-mine">
            <el-tag v-if="it.isWinner" type="success" size="small" effect="dark" round>
              {{ t('portal.portal.isWinner') }}
            </el-tag>
            <StatusTag v-else :status="String(it.myRegistrationStatus)" i18n-prefix="common.status" />
          </div>
        </button>
        <div v-if="!filtered.length && !loading" class="list-empty">{{ t('portal.portal.empty') }}</div>
      </div>
    </aside>

    <!-- 右：所选公告详情 -->
    <section class="tender-detail-panel">
      <PortalTenderDetailPanel v-if="selectedId" :id="selectedId" @close="select(0)" />
      <div v-else class="detail-empty">
        <p>{{ t('portal.portal.selectHint') }}</p>
      </div>
    </section>

    <!-- 移动端：筛选底部弹层 -->
    <el-drawer
      v-model="filterSheetVisible"
      direction="btt"
      size="auto"
      append-to-body
      class="portal-filter-drawer"
      :title="t('portal.portal.filterStatus')"
    >
      <div class="sheet-options">
        <button
          type="button"
          class="sheet-option"
          :class="{ active: !pendingStatus }"
          @click="pendingStatus = ''"
        >
          <span>{{ t('common.status.all') }}</span>
          <el-icon v-if="!pendingStatus"><Check /></el-icon>
        </button>
        <button
          v-for="s in STATUS_OPTIONS"
          :key="s"
          type="button"
          class="sheet-option"
          :class="{ active: pendingStatus === s }"
          @click="pendingStatus = s"
        >
          <span>{{ t(`common.status.${s}`) }}</span>
          <el-icon v-if="pendingStatus === s"><Check /></el-icon>
        </button>
      </div>
      <div class="sheet-footer">
        <el-button @click="resetFilter">{{ t('common.action.reset') }}</el-button>
        <el-button type="primary" @click="applyFilter">{{ t('common.action.confirm') }}</el-button>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.tenders-layout {
  display: grid;
  grid-template-columns: 360px minmax(0, 1fr);
  gap: var(--bs-space-5);
  align-items: start;
}

/* ---- 左侧清单 ---- */
.tender-list-panel {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-3);
  min-width: 0;
}

.list-head {
  display: flex;
  align-items: baseline;
  gap: var(--bs-space-2);
}

.list-count {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.list-search {
  width: 100%;
}

.list-filter {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bs-space-1);
}

.filter-chip {
  padding: 2px var(--bs-space-2);
  border: 1px solid var(--bs-color-border-default);
  border-radius: var(--bs-radius-full);
  background: var(--bs-color-bg-surface);
  color: var(--bs-color-fg-secondary);
  font-size: var(--bs-typography-font-size-xs);
  cursor: pointer;
}

.filter-chip.active {
  border-color: var(--bs-color-primary);
  color: var(--bs-color-primary);
  background: var(--bs-color-brand-primary-soft);
}

.tender-cards {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
  max-height: calc(100vh - 260px);
  overflow-y: auto;
}

.tender-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: var(--bs-space-3);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-bg-surface);
  cursor: pointer;
  text-align: left;
  transition: border-color var(--bs-motion-fast) var(--bs-ease);
}

.tender-card:hover {
  border-color: var(--bs-color-border-strong);
}

.tender-card.active {
  border-color: var(--bs-color-primary);
  box-shadow: inset 2px 0 0 var(--bs-color-brand-primary);
}

.card-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--bs-space-2);
}

.card-name {
  font-size: var(--bs-typography-font-size-sm);
  font-weight: 600;
  color: var(--bs-color-fg-default);
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.card-no {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.card-meta {
  font-size: var(--bs-typography-font-size-xs);
}

.card-deadline {
  color: var(--bs-color-semantic-warning);
}

.card-deadline.urgent {
  color: var(--bs-color-semantic-danger);
  font-weight: 600;
}

.card-deadline-plain {
  color: var(--bs-color-fg-muted);
}

.card-winner {
  color: var(--bs-color-semantic-success);
}

.card-mine {
  margin-top: 2px;
}

.list-empty {
  padding: var(--bs-space-6) 0;
  text-align: center;
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-sm);
}

/* ---- 右侧详情 ---- */
.tender-detail-panel {
  min-width: 0;
  padding: var(--bs-space-5);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-lg);
  background: var(--bs-color-bg-surface);
  box-shadow: var(--bs-shadow-elevation1);
}

.detail-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 240px;
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-sm);
}

/* ---- 移动端：筛选入口 + 底部弹层 ---- */
.filter-trigger-row {
  display: flex;
  gap: var(--bs-space-2);
}

.filter-trigger {
  display: inline-flex;
  align-items: center;
  gap: var(--bs-space-2);
  min-height: 40px;
  padding: 0 var(--bs-space-3);
  border: 1px solid var(--bs-color-border-default);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-bg-surface);
  color: var(--bs-color-fg-secondary);
  font-size: var(--bs-typography-font-size-sm);
  cursor: pointer;
}

.filter-trigger-value {
  color: var(--bs-color-primary);
  font-weight: 600;
}

.sheet-options {
  display: flex;
  flex-direction: column;
}

.sheet-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--bs-space-2);
  width: 100%;
  min-height: 48px;
  padding: var(--bs-space-2) var(--bs-space-1);
  border: none;
  border-bottom: 1px solid var(--bs-color-border-subtle);
  background: transparent;
  color: var(--bs-color-fg-default);
  font-size: var(--bs-typography-font-size-md);
  text-align: left;
  cursor: pointer;
}

.sheet-option.active {
  color: var(--bs-color-primary);
  font-weight: 600;
}

.sheet-footer {
  display: flex;
  gap: var(--bs-space-2);
  padding-top: var(--bs-space-3);
}

.sheet-footer :deep(.el-button) {
  flex: 1;
  margin-left: 0;
  min-height: 44px;
}

.portal-filter-drawer :deep(.el-drawer__body) {
  padding: 0 var(--bs-space-4) calc(var(--bs-space-4) + env(safe-area-inset-bottom));
}

.portal-filter-drawer :deep(.el-drawer__header) {
  margin-bottom: 0;
  padding: var(--bs-space-4) var(--bs-space-4) var(--bs-space-2);
}

/* ---- 移动端：清单 → 详情单栏切换 ---- */
@media (max-width: 767px) {
  .tenders-layout {
    grid-template-columns: 1fr;
  }

  .tender-cards {
    max-height: none;
  }

  .tender-detail-panel {
    display: none;
    padding: var(--bs-space-3);
  }

  .tenders-layout.show-detail .tender-list-panel {
    display: none;
  }

  .tenders-layout.show-detail .tender-detail-panel {
    display: block;
  }
}
</style>
