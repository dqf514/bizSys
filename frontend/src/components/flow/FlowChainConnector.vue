<script setup lang="ts">
/** 竖链流程设计器：节点间连接件（复刻 TPCworkflow FlowConnector + FlowAddMenu）。
 * 竖线中段一个 "+" 圆钮，点开为节点类型选择菜单（审批/条件/抄送）。
 */
import { useI18n } from 'vue-i18n'
import type { FlowNodeType } from '@/api/types'

const emit = defineEmits<{ (e: 'add', type: FlowNodeType): void }>()

const { t } = useI18n()

const MENU: FlowNodeType[] = ['approval', 'condition', 'cc']

function pick(type: FlowNodeType, close: () => void) {
  emit('add', type)
  close()
}
</script>

<template>
  <div class="chain-connector">
    <div class="chain-line" />
    <el-popover placement="right" trigger="click" :width="230">
      <template #reference>
        <button type="button" class="chain-add-btn" :title="t('admin.flow.insertNode')">+</button>
      </template>
      <template #default="{ hide }">
        <div class="add-menu">
          <button
            v-for="m in MENU"
            :key="m"
            type="button"
            class="add-item"
            :class="`add-${m}`"
            @click="pick(m, hide)"
          >
            <span class="add-icon">{{ t(`admin.flow.nodeType.${m}`).slice(0, 1) }}</span>
            <span class="add-label">{{ t(`admin.flow.nodeType.${m}`) }}</span>
          </button>
        </div>
      </template>
    </el-popover>
    <div class="chain-line" />
  </div>
</template>

<style scoped>
.chain-connector {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
}

.chain-line {
  width: 2px;
  height: 14px;
  background: var(--bs-color-border-strong);
}

.chain-add-btn {
  width: 26px;
  height: 26px;
  border-radius: var(--bs-radius-full);
  border: 1px solid var(--bs-color-border-strong);
  background: var(--bs-color-bg-surface);
  color: var(--bs-color-fg-secondary);
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
  box-shadow: var(--bs-shadow-elevation1, 0 1px 4px rgba(15, 23, 42, 0.08));
  transition:
    border-color 0.15s,
    color 0.15s,
    transform 0.15s;
}

.chain-add-btn:hover {
  border-color: var(--bs-color-brand-primary);
  color: var(--bs-color-brand-primary);
  transform: scale(1.08);
}

.add-menu {
  display: flex;
  gap: var(--bs-space-2);
}

.add-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: var(--bs-space-2) var(--bs-space-1);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-bg-surface);
  cursor: pointer;
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-default);
}

.add-item:hover {
  border-color: var(--bs-color-brand-primary);
  background: var(--bs-color-fill-light);
}

.add-icon {
  width: 30px;
  height: 30px;
  border-radius: var(--bs-radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--bs-typography-font-size-sm);
  font-weight: 600;
  color: #fff;
}

.add-approval .add-icon {
  background: var(--bs-color-brand-primary);
}

.add-condition .add-icon {
  background: var(--bs-color-semantic-warning);
}

.add-cc .add-icon {
  background: var(--bs-color-semantic-success);
}

.add-label {
  white-space: nowrap;
}
</style>
