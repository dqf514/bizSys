<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import * as authApi from '@/api/auth'
import type { MenuNode } from '@/api/types'

interface Shortcut {
  path: string
  color: string
}

const MAX_SHORTCUTS = 12
const PALETTE = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']
const DEFAULT_COLOR = 'a'
// sentinel for "user removed every shortcut" — distinguishes from "never customized"
const EMPTY_CSV = '-'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const { t } = useI18n()

function findMenuNode(nodes: MenuNode[], path: string): MenuNode | null {
  for (const node of nodes) {
    if (node.menuType === 'menu' && node.path === path) return node
    const hit = node.children?.length ? findMenuNode(node.children, path) : null
    if (hit) return hit
  }
  return null
}

/** resolved per render so locale switches re-translate automatically */
function titleFor(path: string): string {
  const node = findMenuNode(auth.menus, path)
  if (node) return node.titleKey ? t(node.titleKey) : node.name
  const meta = router.resolve(path).meta
  const titleKey = meta?.titleKey as string | undefined
  if (titleKey) return t(titleKey)
  return (meta?.title as string) || path
}

function parseCsv(csv: string): Shortcut[] {
  return csv
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
    .map((pair) => {
      const idx = pair.lastIndexOf(':')
      const path = idx > 0 ? pair.slice(0, idx) : pair
      const color = idx > 0 ? pair.slice(idx + 1) : DEFAULT_COLOR
      return { path, color: PALETTE.includes(color) ? color : DEFAULT_COLOR }
    })
    .filter((s) => s.path.startsWith('/'))
    .slice(0, MAX_SHORTCUTS)
}

const savedCsv = computed(() => {
  const raw = auth.user?.prefs?.navShortcuts
  return typeof raw === 'string' ? raw : undefined
})

const shortcuts = computed(() => {
  const raw = savedCsv.value
  const list = raw === undefined ? seedDefaults() : parseCsv(raw)
  return list.map((s) => ({ ...s, title: titleFor(s.path) }))
})

/** in-memory defaults until the user customizes once */
function seedDefaults(): Shortcut[] {
  const seeds: Shortcut[] = []
  for (const path of ['/workbench', '/approval']) {
    if (findMenuNode(auth.menus, path)) seeds.push({ path, color: DEFAULT_COLOR })
  }
  return seeds
}

function persist(list: Shortcut[]) {
  const csv = list.length ? list.map((s) => `${s.path}:${s.color}`).join(',') : EMPTY_CSV
  if (auth.user) auth.user.prefs = { ...(auth.user.prefs ?? {}), navShortcuts: csv }
  authApi.updatePrefs({ navShortcuts: csv }).catch(() => {
    /* keep local state; server sync best-effort */
  })
}

function mutate(fn: (list: Shortcut[]) => void) {
  const list = shortcuts.value.map(({ path, color }) => ({ path, color }))
  fn(list)
  persist(list.slice(0, MAX_SHORTCUTS))
}

const canAdd = computed(() => {
  if (route.name === 'NotFound' || route.meta?.tabless || route.path.startsWith('/login')) return false
  if (shortcuts.value.length >= MAX_SHORTCUTS) return false
  return !shortcuts.value.some((s) => s.path === route.path)
})

function addCurrent() {
  if (shortcuts.value.length >= MAX_SHORTCUTS) {
    ElMessage.warning(t('common.shortcut.limitTip'))
    return
  }
  if (!canAdd.value) return
  mutate((list) => {
    list.push({ path: route.path, color: DEFAULT_COLOR })
  })
}

function remove(path: string) {
  mutate((list) => {
    const i = list.findIndex((s) => s.path === path)
    if (i >= 0) list.splice(i, 1)
  })
}

function go(shortcut: Shortcut) {
  if (route.path !== shortcut.path) router.push(shortcut.path)
}

// ---- drag to reorder (same hand-rolled pattern as SideNav sort dialog) ----
const dragIndex = ref(-1)

function onDragStart(i: number) {
  dragIndex.value = i
}

function onDrop(i: number) {
  const from = dragIndex.value
  dragIndex.value = -1
  if (from < 0 || from === i) return
  mutate((list) => {
    const [item] = list.splice(from, 1)
    if (item) list.splice(i, 0, item)
  })
}

// ---- color palette popover ----
const paletteFor = ref<string | null>(null)
const palettePos = ref({ x: 0, y: 0 })

function openPalette(e: MouseEvent, path: string) {
  e.preventDefault()
  paletteFor.value = path
  palettePos.value = { x: e.clientX, y: e.clientY + 6 }
}

function setColor(color: string) {
  const path = paletteFor.value
  paletteFor.value = null
  if (!path) return
  mutate((list) => {
    const target = list.find((s) => s.path === path)
    if (target) target.color = color
  })
}

function hidePalette() {
  paletteFor.value = null
}

onMounted(() => {
  document.addEventListener('click', hidePalette)
})

onUnmounted(() => {
  document.removeEventListener('click', hidePalette)
})
</script>

<template>
  <div class="shortcut-bar">
    <div class="chip-list">
      <div
        v-for="(s, i) in shortcuts"
        :key="s.path"
        class="chip"
        :class="[`c-${s.color}`, { active: s.path === route.path, dragging: dragIndex === i }]"
        draggable="true"
        :title="s.path"
        @click="go(s)"
        @contextmenu="openPalette($event, s.path)"
        @dragstart="onDragStart(i)"
        @dragover.prevent
        @drop="onDrop(i)"
        @dragend="dragIndex = -1"
      >
        <span class="chip-title">{{ s.title }}</span>
        <button
          class="chip-close"
          type="button"
          :title="t('common.shortcut.remove')"
          @click.stop="remove(s.path)"
        >
          ×
        </button>
      </div>
      <span v-if="!shortcuts.length" class="empty-hint">{{ t('common.shortcut.emptyHint') }}</span>
    </div>
    <button
      v-if="canAdd"
      class="add-btn"
      type="button"
      :title="t('common.shortcut.add')"
      @click="addCurrent"
    >
      +
    </button>

    <teleport to="body">
      <Transition name="pop">
        <div
          v-if="paletteFor"
          class="palette-pop"
          :style="{ left: palettePos.x + 'px', top: palettePos.y + 'px' }"
          @click.stop
        >
          <button
            v-for="c in PALETTE"
            :key="c"
            class="swatch"
            :class="`c-${c}`"
            type="button"
            :title="t('common.shortcut.color')"
            @click="setColor(c)"
          />
        </div>
      </Transition>
    </teleport>
  </div>
</template>

<style scoped>
.shortcut-bar {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  height: var(--bs-layout-tabbar-height);
  flex-shrink: 0;
  padding: 0 var(--bs-space-2);
  border-bottom: 1px solid var(--bs-color-border-default);
  background: var(--bs-color-bg-surface);
}

.chip-list {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  flex: 1;
  min-width: 0;
  height: 100%;
  overflow-x: auto;
  overflow-y: hidden;
}

.chip {
  --chip-c: var(--bs-color-fg-muted);
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 24px;
  max-width: 180px;
  padding: 0 10px;
  border-radius: var(--bs-radius-full);
  background: color-mix(in srgb, var(--chip-c) 14%, transparent);
  color: color-mix(in srgb, var(--chip-c) 65%, var(--bs-color-fg-default));
  font-size: var(--bs-typography-font-size-sm);
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
}

.chip:hover {
  background: color-mix(in srgb, var(--chip-c) 22%, transparent);
}

.chip.active {
  box-shadow: inset 0 0 0 1.5px color-mix(in srgb, var(--chip-c) 75%, transparent);
  font-weight: 600;
}

.chip.dragging {
  opacity: 0.5;
}

.chip-title {
  overflow: hidden;
  text-overflow: ellipsis;
}

.chip-close {
  flex: none;
  width: 14px;
  height: 14px;
  border: none;
  border-radius: var(--bs-radius-full);
  background: transparent;
  color: inherit;
  font-size: 11px;
  line-height: 1;
  cursor: pointer;
  opacity: 0;
}

.chip:hover .chip-close {
  opacity: 1;
}

.chip-close:hover {
  background: color-mix(in srgb, var(--chip-c) 30%, transparent);
}

.empty-hint {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
  white-space: nowrap;
}

.add-btn {
  flex: none;
  width: 24px;
  height: 24px;
  border: 1px dashed var(--bs-color-border-strong);
  border-radius: var(--bs-radius-full);
  background: transparent;
  color: var(--bs-color-fg-muted);
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
}

.add-btn:hover {
  border-color: var(--bs-color-primary);
  color: var(--bs-color-primary);
}

.palette-pop {
  position: fixed;
  z-index: 3000;
  display: flex;
  gap: 6px;
  padding: 6px 8px;
  border: 1px solid var(--bs-color-border-default);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-bg-elevated);
  box-shadow: var(--bs-shadow-elevation3);
}

.swatch {
  --chip-c: var(--bs-color-fg-muted);
  width: 18px;
  height: 18px;
  padding: 0;
  border: 2px solid transparent;
  border-radius: var(--bs-radius-full);
  background: color-mix(in srgb, var(--chip-c) 55%, var(--bs-color-bg-elevated));
  cursor: pointer;
}

.swatch:hover {
  border-color: color-mix(in srgb, var(--chip-c) 80%, transparent);
}

/* preset palette: hue only — backgrounds/text derive via color-mix so both themes stay readable */
.c-a {
  --chip-c: #3b82f6;
}

.c-b {
  --chip-c: #06b6d4;
}

.c-c {
  --chip-c: #22c55e;
}

.c-d {
  --chip-c: #eab308;
}

.c-e {
  --chip-c: #f97316;
}

.c-f {
  --chip-c: #ef4444;
}

.c-g {
  --chip-c: #8b5cf6;
}

.c-h {
  --chip-c: #ec4899;
}
</style>
