<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { useTabsStore } from '@/stores/tabs'
import { useThemeStore } from '@/stores/theme'
import type { MenuNode } from '@/api/types'

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{ (e: 'update:visible', v: boolean): void }>()

const router = useRouter()
const auth = useAuthStore()
const tabsStore = useTabsStore()
const theme = useThemeStore()
const { t } = useI18n()
const keyword = ref('')
const inputRef = ref<HTMLInputElement>()
const activeIndex = ref(0)

interface CommandItem {
  id: string
  label: string
  group: string
  run: () => void
}

function flattenMenus(nodes: MenuNode[], out: MenuNode[] = []): MenuNode[] {
  for (const n of nodes) {
    if (n.menuType === 'menu' && n.path) out.push(n)
    if (n.children?.length) flattenMenus(n.children, out)
  }
  return out
}

const items = computed<CommandItem[]>(() => {
  const kw = keyword.value.trim().toLowerCase()
  const list: CommandItem[] = []

  for (const m of flattenMenus(auth.menus)) {
    const label = m.titleKey ? t(m.titleKey) : m.name
    if (!kw || label.toLowerCase().includes(kw) || m.path.toLowerCase().includes(kw)) {
      list.push({
        id: `menu-${m.id}`,
        label,
        group: t('common.command.groupMenu'),
        run: () => router.push(m.path),
      })
    }
  }

  for (const tab of tabsStore.tabs) {
    const label = tab.titleKey ? t(tab.titleKey) : tab.title
    if (!kw || label.toLowerCase().includes(kw) || tab.path.toLowerCase().includes(kw)) {
      list.push({
        id: `tab-${tab.key}`,
        label,
        group: t('common.command.groupTab'),
        run: () => {
          tabsStore.setActive(tab.key)
          router.push(tab.fullPath || tab.path)
        },
      })
    }
  }

  if (!kw || t('common.command.toggleTheme').toLowerCase().includes(kw)) {
    list.push({
      id: 'action-theme',
      label: t('common.command.toggleTheme'),
      group: t('common.command.groupAction'),
      run: () => theme.toggleTheme(),
    })
  }
  if (!kw || t('common.command.toggleLocale').toLowerCase().includes(kw)) {
    list.push({
      id: 'action-locale',
      label: t('common.command.toggleLocale'),
      group: t('common.command.groupAction'),
      run: () => theme.setAppLocale(theme.locale === 'zh-CN' ? 'en-US' : 'zh-CN'),
    })
  }

  return list.slice(0, 50)
})

const grouped = computed(() => {
  const map = new Map<string, CommandItem[]>()
  for (const item of items.value) {
    const arr = map.get(item.group) ?? []
    arr.push(item)
    map.set(item.group, arr)
  }
  return [...map.entries()]
})

const flatItems = computed(() => items.value)

watch(
  () => props.visible,
  (v) => {
    if (v) {
      keyword.value = ''
      activeIndex.value = 0
      nextTick(() => inputRef.value?.focus())
    }
  },
)

function run(item: CommandItem) {
  item.run()
  emit('update:visible', false)
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    activeIndex.value = Math.min(activeIndex.value + 1, flatItems.value.length - 1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    activeIndex.value = Math.max(activeIndex.value - 1, 0)
  } else if (e.key === 'Enter') {
    e.preventDefault()
    const item = flatItems.value[activeIndex.value]
    if (item) run(item)
  } else if (e.key === 'Escape') {
    emit('update:visible', false)
  }
}

function itemIndex(item: CommandItem) {
  return flatItems.value.findIndex((x) => x.id === item.id)
}

watch(keyword, () => {
  activeIndex.value = 0
})
</script>

<template>
  <el-dialog
    :model-value="props.visible"
    :title="t('common.command.title')"
    width="560px"
    append-to-body
    class="cmd-dialog"
    @update:model-value="emit('update:visible', $event)"
  >
    <div class="cmd-box">
      <input
        ref="inputRef"
        v-model="keyword"
        class="cmd-input"
        :placeholder="t('common.command.placeholder')"
        @keydown="onKey"
      />
      <div class="cmd-list">
        <template v-for="[group, groupItems] in grouped" :key="group">
          <div class="cmd-group">{{ group }}</div>
          <div
            v-for="item in groupItems"
            :key="item.id"
            class="cmd-item"
            :class="{ active: itemIndex(item) === activeIndex }"
            @click="run(item)"
            @mouseenter="activeIndex = itemIndex(item)"
          >
            {{ item.label }}
          </div>
        </template>
        <div v-if="!flatItems.length" class="cmd-empty">{{ t('common.command.empty') }}</div>
      </div>
    </div>
  </el-dialog>
</template>

<style scoped>
.cmd-box {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
}

.cmd-input {
  height: 36px;
  padding: 0 var(--bs-space-3);
  border: 1px solid var(--bs-color-border-default);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-bg-surface);
  color: var(--bs-color-fg-default);
  outline: none;
}

.cmd-input:focus {
  border-color: var(--bs-color-primary);
}

.cmd-list {
  max-height: 360px;
  overflow: auto;
}

.cmd-group {
  padding: 6px 8px;
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.cmd-item {
  padding: 8px 10px;
  border-radius: var(--bs-radius-sm);
  cursor: pointer;
  color: var(--bs-color-fg-default);
  font-size: var(--bs-typography-font-size-sm);
}

.cmd-item.active {
  background: var(--bs-color-brand-primary-soft);
  color: var(--bs-color-primary);
}

.cmd-empty {
  padding: var(--bs-space-4);
  text-align: center;
  color: var(--bs-color-fg-muted);
}
</style>
