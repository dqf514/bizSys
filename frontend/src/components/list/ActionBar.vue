<script setup lang="ts">
/**
 * 列表操作列统一组件：图标 + tooltip，超出 maxInline 个动作收进「更多」下拉。
 * 同一动作全站同一图标/颜色语义（ACTION_META）；perm 走 auth.hasPerm，confirm 走二次确认。
 */
import { computed, resolveComponent } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'

export interface ActionItem {
  key: string
  /** tooltip 文案 i18n key */
  tip: string
  /** 覆盖默认图标（@element-plus/icons-vue 组件名） */
  icon?: string
  /** 危险动作（danger 色，默认 delete 系自动危险） */
  danger?: boolean
  disabled?: boolean
  /** 权限码，无权限则隐藏 */
  perm?: string
  /** 二次确认文案 i18n key；确认后才派发 select */
  confirm?: string
}

interface ActionMeta {
  icon: string
  danger?: boolean
}

/** 全站动作 → 图标/颜色语义映射 */
const ACTION_META: Record<string, ActionMeta> = {
  view: { icon: 'View' },
  detail: { icon: 'View' },
  preview: { icon: 'View' },
  edit: { icon: 'Edit' },
  delete: { icon: 'Delete', danger: true },
  remove: { icon: 'Delete', danger: true },
  submit: { icon: 'Promotion' },
  approve: { icon: 'CircleCheck' },
  reject: { icon: 'CircleClose', danger: true },
  withdraw: { icon: 'RefreshLeft' },
  transfer: { icon: 'Position' },
  addSign: { icon: 'CirclePlus' },
  assign: { icon: 'User' },
  export: { icon: 'Download' },
  download: { icon: 'Download' },
  upload: { icon: 'Upload' },
  seal: { icon: 'Stamp' },
  invoice: { icon: 'Tickets' },
  enable: { icon: 'Open' },
  disable: { icon: 'TurnOff' },
  add: { icon: 'Plus' },
}

const props = withDefaults(
  defineProps<{
    actions: ActionItem[]
    maxInline?: number
  }>(),
  { maxInline: 3 },
)

const emit = defineEmits<{
  (e: 'select', key: string, action: ActionItem): void
}>()

const { t } = useI18n()
const auth = useAuthStore()

const visible = computed(() => props.actions.filter((a) => !a.perm || auth.hasPerm(a.perm)))
const inline = computed(() =>
  visible.value.length <= props.maxInline ? visible.value : visible.value.slice(0, props.maxInline - 1),
)
const overflow = computed(() => visible.value.slice(inline.value.length))

function iconOf(a: ActionItem) {
  const name = a.icon || ACTION_META[a.key]?.icon || 'Document'
  return resolveComponent(name) as never
}

function isDanger(a: ActionItem) {
  return a.danger ?? ACTION_META[a.key]?.danger ?? false
}

async function onClick(a: ActionItem) {
  if (a.disabled) return
  if (a.confirm) {
    try {
      await ElMessageBox.confirm(t(a.confirm), {
        type: 'warning',
        confirmButtonText: t('common.action.confirm'),
        cancelButtonText: t('common.action.cancel'),
      })
    } catch {
      return
    }
  }
  emit('select', a.key, a)
}
</script>

<template>
  <div class="action-bar">
    <el-tooltip v-for="a in inline" :key="a.key" :content="t(a.tip)" placement="top" :show-after="200">
      <el-button
        link
        :type="isDanger(a) ? 'danger' : 'primary'"
        :disabled="a.disabled"
        class="action-btn"
        :aria-label="t(a.tip)"
        @click="onClick(a)"
      >
        <el-icon :size="15"><component :is="iconOf(a)" /></el-icon>
      </el-button>
    </el-tooltip>
    <el-dropdown
v-if="overflow.length" trigger="click" @command="(k: string) => {
      const a = overflow.find((x) => x.key === k)
      if (a) void onClick(a)
    }">
      <el-button link type="primary" class="action-btn" :aria-label="t('common.action.more')">
        <el-icon :size="15"><component :is="resolveComponent('MoreFilled') as never" /></el-icon>
      </el-button>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item v-for="a in overflow" :key="a.key" :command="a.key" :disabled="a.disabled">
            <span :class="{ 'is-danger': isDanger(a) }">{{ t(a.tip) }}</span>
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
  </div>
</template>

<style scoped>
.action-bar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--bs-space-1);
  vertical-align: middle;
}

.action-btn {
  padding: 2px;
  height: auto;
}

.action-btn + .action-btn {
  margin-left: 0;
}

.is-danger {
  color: var(--bs-color-semantic-danger);
}
</style>
