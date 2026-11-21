<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useTabsStore } from '@/stores/tabs'
import { useThemeStore } from '@/stores/theme'
import { useNavZones } from './useNavZones'
import type { MenuNode } from '@/api/types'

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{ (e: 'update:visible', v: boolean): void }>()

const router = useRouter()
const tabsStore = useTabsStore()
const theme = useThemeStore()
const { t } = useI18n()
const { topMenus, zones, systemZone, menuTitle } = useNavZones()
const keyword = ref('')
const inputRef = ref<HTMLInputElement>()
const activeIndex = ref(0)

interface CommandItem {
  id: string
  label: string
  group: string
  run: () => void
}

/** 收集节点下的全部可见叶子菜单（递归目录） */
function collectLeaves(node: MenuNode, out: MenuNode[] = []): MenuNode[] {
  for (const c of node.children ?? []) {
    if (c.visible === 0) continue
    if (c.menuType === 'menu') out.push(c)
    else if (c.menuType === 'dir') collectLeaves(c, out)
  }
  return out
}

/** 菜单条目 + 所属分区名（分区名可参与检索，搜分区名即列出其下页面） */
const menuEntries = computed(() => {
  const out: { node: MenuNode; zone: string }[] = []
  for (const n of topMenus.value) out.push({ node: n, zone: '' })
  for (const zone of zones.value) {
    const title = menuTitle(zone)
    for (const leaf of collectLeaves(zone)) out.push({ node: leaf, zone: title })
  }
  if (systemZone.value) {
    const title = menuTitle(systemZone.value)
    for (const leaf of collectLeaves(systemZone.value)) out.push({ node: leaf, zone: title })
  }
  return out
})

const items = computed<CommandItem[]>(() => {
  const kw = keyword.value.trim().toLowerCase()
  const list: CommandItem[] = []

  for (const entry of menuEntries.value) {
    const m = entry.node
    const label = m.titleKey ? t(m.titleKey) : m.name
    const zone = entry.zone
    const display = zone ? `${zone} / ${label}` : label
    const hit =
      !kw ||
      label.toLowerCase().includes(kw) ||
      m.path.toLowerCase().includes(kw) ||
      (!!zone && zone.toLowerCase().includes(kw))
    if (hit) {
      list.push({
        id: `menu-${m.id}`,
        label: display,
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
    width="var(--bs-layout-dialog-md)"
    append-to-body
    class="cmd-dialog"
    @update:model-value="emit('update:visible', $event)"
  >
    <div class="cmd-box">
      <input
        ref="inputRef"
        v-model="keyword"
        class="cmd-input"
        role="combobox"
        aria-expanded="true"
        aria-controls="cmd-list"
        :aria-label="t('common.command.placeholder')"
        :placeholder="t('common.command.placeholder')"
        @keydown="onKey"
      />
      <div id="cmd-list" class="cmd-list" role="listbox">
        <template v-for="[group, groupItems] in grouped" :key="group">
          <div class="cmd-group">{{ group }}</div>
          <div
            v-for="item in groupItems"
            :key="item.id"
            class="cmd-item"
            :class="{ active: itemIndex(item) === activeIndex }"
            role="option"
            :aria-selected="itemIndex(item) === activeIndex"
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
