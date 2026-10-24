<script setup lang="ts">
import { computed, ref, watch, type Component } from 'vue'
import { useI18n } from 'vue-i18n'
import { Setting } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { updatePrefs } from '@/api/auth'
import type { DashboardPrefs, DashboardWidgetPref } from '@/api/types'
import StatCards from '../components/StatCards.vue'
import ApprovalTodoCard from '../components/ApprovalTodoCard.vue'
import MyInitiatedCard from '../components/MyInitiatedCard.vue'
import CcInboxCard from '../components/CcInboxCard.vue'
import NotifyCard from '../components/NotifyCard.vue'
import MyTasksCard from '../components/MyTasksCard.vue'
import MonthCalendar from '../components/MonthCalendar.vue'
import QuickLinks from '../components/QuickLinks.vue'
import OaQuickApply from '../components/OaQuickApply.vue'
import FinanceOverview from '../components/FinanceOverview.vue'
import CustomizeDialog from '../components/CustomizeDialog.vue'

defineOptions({ name: 'Dashboard' })

const { t } = useI18n()
const auth = useAuthStore()

interface WidgetMeta {
  key: string
  labelKey: string
  component: Component
  /** grid columns out of 12 on wide screens */
  span: 6 | 12
  /** 无该权限时整个 widget 隐藏（其接口必然 403） */
  perm?: string
  /** 任一权限满足即可（财务概览聚合多个列表接口） */
  anyPerm?: string[]
}

const WIDGET_META: WidgetMeta[] = [
  { key: 'stats', labelKey: 'workbench.widget.stats', component: StatCards, span: 12 },
  { key: 'approvalTodo', labelKey: 'workbench.widget.approvalTodo', component: ApprovalTodoCard, span: 6 },
  { key: 'myInitiated', labelKey: 'workbench.widget.myInitiated', component: MyInitiatedCard, span: 6 },
  { key: 'ccInbox', labelKey: 'workbench.widget.ccInbox', component: CcInboxCard, span: 6 },
  { key: 'notify', labelKey: 'workbench.widget.notify', component: NotifyCard, span: 6 },
  { key: 'oaQuickApply', labelKey: 'workbench.widget.oaQuickApply', component: OaQuickApply, span: 6, perm: 'oa:apply' },
  {
    key: 'financeOverview',
    labelKey: 'workbench.widget.financeOverview',
    component: FinanceOverview,
    span: 6,
    anyPerm: ['finance:settlement:list', 'finance:invoice:list', 'finance:payment:list'],
  },
  { key: 'myTasks', labelKey: 'workbench.widget.myTasks', component: MyTasksCard, span: 6, perm: 'task:list' },
  { key: 'calendar', labelKey: 'workbench.widget.calendar', component: MonthCalendar, span: 6, perm: 'task:list' },
  { key: 'quickLinks', labelKey: 'workbench.widget.quickLinks', component: QuickLinks, span: 12 },
]

const WIDGET_LABEL_KEYS: Record<string, string> = Object.fromEntries(
  WIDGET_META.map((w) => [w.key, w.labelKey]),
)

const DEFAULT_WIDGETS: DashboardWidgetPref[] = WIDGET_META.map((w) => ({ key: w.key, visible: true }))

function readPrefWidgets(): DashboardWidgetPref[] {
  const raw = auth.user?.prefs?.dashboard
  if (typeof raw !== 'string' || !raw) return DEFAULT_WIDGETS.map((w) => ({ ...w }))
  try {
    const parsed = JSON.parse(raw) as DashboardPrefs
    const saved = Array.isArray(parsed?.widgets) ? parsed.widgets : []
    const known = new Set(WIDGET_META.map((w) => w.key))
    const ordered = saved
      .filter((w) => w && typeof w.key === 'string' && known.has(w.key))
      .map((w) => ({ key: w.key, visible: w.visible !== false }))
    // append widgets added after the pref was saved
    for (const d of DEFAULT_WIDGETS) {
      if (!ordered.some((w) => w.key === d.key)) ordered.push({ ...d })
    }
    return ordered.length ? ordered : DEFAULT_WIDGETS.map((w) => ({ ...w }))
  } catch {
    return DEFAULT_WIDGETS.map((w) => ({ ...w }))
  }
}

const widgets = ref<DashboardWidgetPref[]>(readPrefWidgets())
const customizeVisible = ref(false)

function permitted(m: WidgetMeta): boolean {
  if (m.perm && !auth.hasPerm(m.perm)) return false
  if (m.anyPerm?.length && !m.anyPerm.some((p) => auth.hasPerm(p))) return false
  return true
}

const visibleWidgets = computed(() =>
  widgets.value
    .filter((w) => w.visible)
    .map((w) => WIDGET_META.find((m) => m.key === w.key))
    .filter((m): m is WidgetMeta => Boolean(m))
    .filter(permitted),
)

/** 自定义弹窗只列出当前用户有权使用的 widget */
const customizableWidgets = computed(() =>
  widgets.value.filter((w) => {
    const meta = WIDGET_META.find((m) => m.key === w.key)
    return meta && permitted(meta)
  }),
)

function persist() {
  const payload = JSON.stringify({ widgets: widgets.value } satisfies DashboardPrefs)
  if (auth.user?.prefs) auth.user.prefs.dashboard = payload
  void updatePrefs({ dashboard: payload }).catch(() => {
    /* prefs sync optional */
  })
}

function onCustomizeSave(next: DashboardWidgetPref[]) {
  // 弹窗只包含有权 widget，保存时保留无权限 widget 的原有偏好
  const shown = new Set(next.map((w) => w.key))
  widgets.value = [...next, ...widgets.value.filter((w) => !shown.has(w.key))]
  persist()
}

// re-read prefs when the profile (re)loads, e.g. after login on this page
watch(
  () => auth.user?.prefs?.dashboard,
  (val) => {
    if (typeof val === 'string' && val !== JSON.stringify({ widgets: widgets.value })) {
      widgets.value = readPrefWidgets()
    }
  },
)
</script>

<template>
  <div class="dashboard">
    <div class="page-header">
      <div class="welcome">
        <h2 class="welcome-title">
          {{ t('workbench.welcome', { name: auth.user?.name || auth.user?.username || '' }) }}
        </h2>
        <p class="welcome-sub">{{ t('workbench.title') }}</p>
      </div>
      <el-button :icon="Setting" @click="customizeVisible = true">
        {{ t('workbench.customize') }}
      </el-button>
    </div>

    <div class="widget-grid bs-stagger">
      <div
        v-for="w in visibleWidgets"
        :key="w.key"
        class="widget-cell"
        :class="`span-${w.span}`"
      >
        <component :is="w.component" />
      </div>
    </div>

    <CustomizeDialog
      v-model="customizeVisible"
      :widgets="customizableWidgets"
      :label-keys="WIDGET_LABEL_KEYS"
      @save="onCustomizeSave"
    />
  </div>
</template>

<style scoped>
.dashboard {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-4);
  padding: var(--bs-space-5);
  height: 100%;
  overflow: auto;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--bs-space-3);
}

.welcome-title {
  font-size: var(--bs-typography-font-size-xl);
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.welcome-sub {
  margin-top: 4px;
  color: var(--bs-color-fg-muted);
}

.widget-grid {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  gap: var(--bs-space-4);
  align-items: stretch;
}

.widget-cell {
  min-width: 0;
  grid-column: span 12;
}

@media (min-width: 960px) {
  .widget-cell.span-6 {
    grid-column: span 6;
  }
}
</style>
