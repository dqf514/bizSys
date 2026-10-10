<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowLeft, ArrowRight } from '@element-plus/icons-vue'
import WidgetShell from './WidgetShell.vue'
import { useThemeStore } from '@/stores/theme'
import { listTasks } from '@/api/task'
import type { Task } from '@/api/types'

defineOptions({ name: 'MonthCalendar' })

interface DayEvent {
  kind: 'created' | 'due'
  task: Task
}

interface DayCell {
  /** YYYY-MM-DD */
  key: string
  day: number
  inMonth: boolean
  isToday: boolean
  events: DayEvent[]
}

const { t } = useI18n()
const router = useRouter()
const theme = useThemeStore()

const today = new Date()
const cursor = ref(new Date(today.getFullYear(), today.getMonth(), 1))
const loading = ref(false)
const eventMap = ref<Map<string, DayEvent[]>>(new Map())

function pad(n: number) {
  return String(n).padStart(2, '0')
}

function dayKey(d: Date) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

const monthLabel = computed(() =>
  cursor.value.toLocaleDateString(theme.locale, { year: 'numeric', month: 'long' }),
)

const weekdays = computed(() => {
  // 2024-01-01 was a Monday — generate Mon..Sun labels from Intl
  return Array.from({ length: 7 }, (_, i) =>
    new Date(2024, 0, 1 + i).toLocaleDateString(theme.locale, { weekday: 'short' }),
  )
})

const cells = computed<DayCell[]>(() => {
  const first = cursor.value
  // Monday-first offset
  const offset = (first.getDay() + 6) % 7
  const start = new Date(first)
  start.setDate(first.getDate() - offset)
  const todayKey = dayKey(today)
  const map = eventMap.value
  return Array.from({ length: 42 }, (_, i) => {
    const d = new Date(start)
    d.setDate(start.getDate() + i)
    const key = dayKey(d)
    return {
      key,
      day: d.getDate(),
      inMonth: d.getMonth() === first.getMonth(),
      isToday: key === todayKey,
      events: map.get(key) ?? [],
    }
  })
})

async function load() {
  loading.value = true
  const y = cursor.value.getFullYear()
  const m = cursor.value.getMonth()
  const rangeStart = `${y}-${pad(m + 1)}-01`
  const rangeEnd = dayKey(new Date(y, m + 1, 0))
  const range = `${rangeStart}|${rangeEnd}`
  const map = new Map<string, DayEvent[]>()
  const push = (task: Task, kind: DayEvent['kind'], raw: string) => {
    const key = (raw || '').slice(0, 10)
    if (!key) return
    const list = map.get(key) ?? []
    list.push({ kind, task })
    map.set(key, list)
  }
  const safe = async (fn: () => Promise<void>) => {
    try {
      await fn()
    } catch {
      /* widget tolerates partial failure */
    }
  }
  await Promise.all([
    safe(async () => {
      const d = await listTasks({ page: 1, size: 200, range: { create_time: range } })
      for (const task of d.items ?? []) push(task, 'created', task.createTime)
    }),
    safe(async () => {
      const d = await listTasks({ page: 1, size: 200, range: { plan_finish_date: range } })
      for (const task of d.items ?? []) push(task, 'due', task.planFinishDate)
    }),
  ])
  eventMap.value = map
  loading.value = false
}

function shiftMonth(delta: number) {
  cursor.value = new Date(cursor.value.getFullYear(), cursor.value.getMonth() + delta, 1)
  void load()
}

function goTasks() {
  router.push('/task/tasks')
}

onMounted(() => {
  void load()
})
</script>

<template>
  <WidgetShell :title="t('workbench.widget.calendar')" :loading="loading">
    <template #actions>
      <el-button link size="small" :icon="ArrowLeft" @click="shiftMonth(-1)" />
      <span class="month-label">{{ monthLabel }}</span>
      <el-button link size="small" :icon="ArrowRight" @click="shiftMonth(1)" />
    </template>

    <div class="calendar">
      <div class="weekday" v-for="w in weekdays" :key="w">{{ w }}</div>
      <el-tooltip
        v-for="cell in cells"
        :key="cell.key"
        :disabled="!cell.events.length"
        placement="top"
        effect="light"
      >
        <template #content>
          <div class="tip-list">
            <div v-for="(ev, i) in cell.events.slice(0, 6)" :key="i" class="tip-item">
              <span class="tip-dot" :class="ev.kind"></span>
              {{ ev.task.taskNo }} {{ ev.task.taskName }}
            </div>
            <div v-if="cell.events.length > 6" class="tip-more">
              +{{ cell.events.length - 6 }}
            </div>
          </div>
        </template>
        <div
          class="day"
          :class="{ dim: !cell.inMonth, today: cell.isToday, clickable: cell.events.length }"
          @click="cell.events.length && goTasks()"
        >
          <span class="day-num">{{ cell.day }}</span>
          <span class="day-dots">
            <span
              v-for="(ev, i) in cell.events.slice(0, 3)"
              :key="i"
              class="dot"
              :class="ev.kind"
            ></span>
          </span>
        </div>
      </el-tooltip>
    </div>

    <div class="legend">
      <span class="legend-item"><span class="dot created"></span>{{ t('workbench.calendar.created') }}</span>
      <span class="legend-item"><span class="dot due"></span>{{ t('workbench.calendar.due') }}</span>
    </div>
  </WidgetShell>
</template>

<style scoped>
.month-label {
  font-size: var(--bs-typography-font-size-sm);
  color: var(--bs-color-fg-secondary);
  min-width: 72px;
  text-align: center;
}

.calendar {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 2px;
}

.weekday {
  padding: var(--bs-space-1) 0;
  text-align: center;
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.day {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: var(--bs-space-1) 0;
  border-radius: var(--bs-radius-sm);
  font-size: var(--bs-typography-font-size-sm);
  color: var(--bs-color-fg-default);
}

.day.dim {
  color: var(--bs-color-fg-muted);
  opacity: 0.5;
}

.day.today .day-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--bs-color-primary);
  color: var(--bs-color-fg-inverse);
}

.day.clickable {
  cursor: pointer;
}

.day.clickable:hover {
  background: var(--bs-color-fill-hover);
}

.day-dots {
  display: inline-flex;
  gap: 2px;
  height: 4px;
}

.dot {
  width: 4px;
  height: 4px;
  border-radius: 50%;
}

.dot.created {
  background: var(--bs-color-primary);
}

.dot.due {
  background: var(--bs-color-semantic-warning);
}

.legend {
  display: flex;
  gap: var(--bs-space-3);
  margin-top: var(--bs-space-2);
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: var(--bs-space-1);
}

.tip-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: var(--bs-typography-font-size-xs);
}

.tip-item {
  display: inline-flex;
  align-items: center;
  gap: var(--bs-space-1);
}

.tip-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
}

.tip-dot.created {
  background: var(--bs-color-primary);
}

.tip-dot.due {
  background: var(--bs-color-semantic-warning);
}

.tip-more {
  color: var(--bs-color-fg-muted);
}
</style>
