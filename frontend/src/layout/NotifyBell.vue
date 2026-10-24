<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElBadge, ElIcon, ElPopover } from 'element-plus'
import { Bell } from '@element-plus/icons-vue'
import { listNotifies, markAllNotifiesRead, markNotifyRead, notifyUnreadCount } from '@/api/workbench'
import type { NotifyItem } from '@/api/types'

const { t } = useI18n()
const router = useRouter()

const items = ref<NotifyItem[]>([])
const unread = ref(0)
const loading = ref(false)
const visible = ref(false)
let timer: ReturnType<typeof setInterval> | null = null

async function loadList() {
  loading.value = true
  try {
    const d = await listNotifies({ page: 1, size: 6 })
    items.value = d.items ?? []
  } catch {
    items.value = []
  } finally {
    loading.value = false
  }
}

async function loadUnread() {
  try {
    unread.value = (await notifyUnreadCount()).count ?? 0
  } catch {
    /* badge best effort */
  }
}

onMounted(() => {
  void loadUnread()
  timer = setInterval(() => void loadUnread(), 60_000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})

function onOpen(v: boolean) {
  visible.value = v
  if (v) {
    void loadList()
    void loadUnread()
  }
}

async function openItem(n: NotifyItem) {
  if (!n.readFlag) {
    n.readFlag = true
    unread.value = Math.max(0, unread.value - 1)
    markNotifyRead(n.id).catch(() => {
      /* best effort */
    })
  }
  if (n.link && n.link.startsWith('/')) {
    visible.value = false
    router.push(n.link)
  }
}

async function readAll() {
  items.value.forEach((n) => (n.readFlag = true))
  unread.value = 0
  try {
    await markAllNotifiesRead()
  } catch {
    /* best effort */
  }
}
</script>

<template>
  <ElPopover
    :visible="visible"
    trigger="click"
    placement="bottom-end"
    :width="360"
    popper-class="notify-pop"
    @update:visible="onOpen"
  >
    <template #reference>
      <button class="icon-btn notify-btn" type="button" :title="t('workbench.widget.notify')">
        <ElBadge :value="unread" :hidden="!unread" :max="99">
          <ElIcon :size="16"><Bell /></ElIcon>
        </ElBadge>
      </button>
    </template>

    <div class="notify-panel">
      <div class="notify-head">
        <span class="notify-head-title">{{ t('workbench.widget.notify') }}</span>
        <el-button v-if="unread" link type="primary" size="small" @click="readAll">
          {{ t('workbench.markAllRead') }}
        </el-button>
      </div>
      <div v-loading="loading" class="notify-body">
        <div v-if="!items.length" class="notify-empty">{{ t('workbench.emptyNotify') }}</div>
        <ul v-else class="notify-list">
          <li
            v-for="n in items"
            :key="n.id"
            class="notify-item"
            :class="{ unread: !n.readFlag }"
            @click="openItem(n)"
          >
            <span class="notify-dot" :class="{ on: !n.readFlag }" aria-hidden="true"></span>
            <span class="notify-main">
              <span class="notify-title" :title="n.title">{{ n.title }}</span>
              <span v-if="n.content" class="notify-content" :title="n.content">{{ n.content }}</span>
            </span>
            <span class="notify-time">{{ n.createTime }}</span>
          </li>
        </ul>
      </div>
    </div>
  </ElPopover>
</template>

<style scoped>
.notify-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: var(--bs-radius-sm);
  background: transparent;
  color: var(--bs-color-fg-secondary);
  cursor: pointer;
}

.notify-btn:hover {
  background: var(--bs-color-fill-hover);
  color: var(--bs-color-fg-default);
}

.notify-panel {
  display: flex;
  flex-direction: column;
  max-height: 420px;
}

.notify-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: var(--bs-space-2);
  border-bottom: 1px solid var(--bs-color-border-subtle);
}

.notify-head-title {
  font-weight: 600;
  font-size: var(--bs-typography-font-size-sm);
}

.notify-body {
  min-height: 80px;
  overflow-y: auto;
}

.notify-empty {
  padding: var(--bs-space-5) 0;
  text-align: center;
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-sm);
}

.notify-list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.notify-item {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  padding: var(--bs-space-2) var(--bs-space-1);
  border-radius: var(--bs-radius-sm);
  cursor: pointer;
  font-size: var(--bs-typography-font-size-sm);
}

.notify-item:hover {
  background: var(--bs-color-fill-hover);
}

.notify-dot {
  flex: none;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: transparent;
}

.notify-dot.on {
  background: var(--bs-color-semantic-danger);
}

.notify-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.notify-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--bs-color-fg-default);
}

.notify-item.unread .notify-title {
  font-weight: 600;
}

.notify-content {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs);
}

.notify-time {
  flex: none;
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs);
}
</style>
