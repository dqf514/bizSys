<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import WidgetShell from './WidgetShell.vue'
import { listNotifies, markAllNotifiesRead, markNotifyRead, notifyUnreadCount } from '@/api/workbench'
import type { NotifyItem } from '@/api/types'

defineOptions({ name: 'NotifyCard' })

const { t } = useI18n()
const router = useRouter()

const items = ref<NotifyItem[]>([])
const loading = ref(false)

const unreadCount = ref(0)

async function load() {
  loading.value = true
  try {
    const d = await listNotifies({ page: 1, size: 8 })
    items.value = d.items ?? []
  } catch {
    items.value = []
  }
  try {
    unreadCount.value = (await notifyUnreadCount()).count ?? 0
  } catch {
    unreadCount.value = 0
  }
  loading.value = false
}

onMounted(() => {
  void load()
})

async function openItem(n: NotifyItem) {
  if (!n.readFlag) {
    n.readFlag = true
    unreadCount.value = Math.max(0, unreadCount.value - 1)
    markNotifyRead(n.id).catch(() => {
      /* best effort */
    })
  }
  if (n.link && n.link.startsWith('/')) {
    router.push(n.link)
  }
}

async function readAll() {
  items.value.forEach((n) => (n.readFlag = true))
  unreadCount.value = 0
  try {
    await markAllNotifiesRead()
  } catch {
    /* best effort */
  }
}
</script>

<template>
  <WidgetShell :title="t('workbench.widget.notify')" :badge="unreadCount" :loading="loading">
    <template #actions>
      <el-button v-if="unreadCount" link type="primary" size="small" @click="readAll">
        {{ t('workbench.markAllRead') }}
      </el-button>
    </template>

    <div v-if="!items.length" class="empty">{{ t('workbench.emptyNotify') }}</div>
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
  </WidgetShell>
</template>

<style scoped>
.empty {
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
