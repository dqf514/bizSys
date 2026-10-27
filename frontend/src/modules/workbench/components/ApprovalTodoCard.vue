<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import WidgetShell from './WidgetShell.vue'
import { approveTask, listApprovalTasks, rejectTask } from '@/api/approval'
import type { ApprovalTask } from '@/api/types'

defineOptions({ name: 'ApprovalTodoCard' })

const emit = defineEmits<{ (e: 'acted'): void }>()

const { t } = useI18n()
const router = useRouter()

const items = ref<ApprovalTask[]>([])
const total = ref(0)
const loading = ref(false)
const actingId = ref(0)

async function load() {
  loading.value = true
  try {
    const d = await listApprovalTasks('todo', { page: 1, size: 5 })
    items.value = d.items ?? []
    total.value = d.total ?? 0
  } catch {
    items.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void load()
})

function bizTypeLabel(bt: string) {
  if (bt === 'contract') return t('approval.approval.bizContract')
  if (bt === 'task') return t('approval.approval.bizTask')
  if (bt === 'report') return t('approval.approval.bizReport')
  if (bt === 'invoice') return t('approval.approval.bizInvoice')
  if (bt === 'oa') return t('approval.approval.bizOa')
  if (bt === 'purchase_request') return t('approval.approval.bizPurchaseRequest')
  if (bt === 'purchase_contract') return t('approval.approval.bizPurchaseContract')
  if (bt === 'tender_award') return t('approval.approval.bizTenderAward')
  return bt
}

/** 行内快速审批：同意直提，驳回弹窗必填意见 */
async function quickAct(it: ApprovalTask, kind: 'agree' | 'reject') {
  let comment = ''
  if (kind === 'reject') {
    try {
      const r = await ElMessageBox.prompt(t('approval.approval.commentPlaceholder'), t('approval.approval.reject'), {
        confirmButtonText: t('common.action.confirm'),
        cancelButtonText: t('common.action.cancel'),
        inputValidator: (v: string) => Boolean(v?.trim()) || t('approval.approval.commentRequired'),
      })
      comment = r.value.trim()
    } catch {
      return
    }
  }
  actingId.value = it.id
  try {
    if (kind === 'agree') await approveTask(it.id, comment)
    else await rejectTask(it.id, comment)
    ElMessage.success(t('common.message.submitSuccess'))
    await load()
    emit('acted')
  } catch {
    /* http notifies */
  } finally {
    actingId.value = 0
  }
}

function goCenter() {
  router.push('/approval')
}

function goDetail() {
  router.push({ path: '/approval', query: { tab: 'todo' } })
}
</script>

<template>
  <WidgetShell :title="t('workbench.widget.approvalTodo')" :badge="total" :loading="loading">
    <template #actions>
      <el-button link type="primary" size="small" @click="goCenter">{{ t('workbench.viewAll') }}</el-button>
    </template>

    <div v-if="!items.length" class="empty">{{ t('workbench.emptyApproval') }}</div>
    <ul v-else class="todo-list">
      <li v-for="it in items" :key="it.id" class="todo-item" @click="goDetail">
        <span class="todo-dot" aria-hidden="true"></span>
        <span class="todo-biz">{{ bizTypeLabel(it.bizType) }}</span>
        <span class="todo-title" :title="it.title">{{ it.title }}</span>
        <span class="todo-initiator">{{ it.initiatorName }}</span>
        <span class="todo-ops" @click.stop>
          <el-button
            link
            type="success"
            size="small"
            :loading="actingId === it.id"
            @click="quickAct(it, 'agree')"
          >
            {{ t('approval.approval.agree') }}
          </el-button>
          <el-button
            link
            type="danger"
            size="small"
            :loading="actingId === it.id"
            @click="quickAct(it, 'reject')"
          >
            {{ t('approval.approval.reject') }}
          </el-button>
        </span>
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

.todo-list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.todo-item {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  padding: var(--bs-space-2) var(--bs-space-1);
  border-radius: var(--bs-radius-sm);
  cursor: pointer;
  font-size: var(--bs-typography-font-size-sm);
}

.todo-item:hover {
  background: var(--bs-color-fill-hover);
}

.todo-dot {
  flex: none;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--bs-color-semantic-danger);
}

.todo-biz {
  flex: none;
  padding: 0 var(--bs-space-1);
  border-radius: var(--bs-radius-sm);
  background: var(--bs-color-semantic-warning-soft);
  color: var(--bs-color-semantic-warning);
  font-size: var(--bs-typography-font-size-xs);
}

.todo-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--bs-color-fg-default);
}

.todo-initiator {
  flex: none;
  color: var(--bs-color-fg-secondary);
}

.todo-ops {
  flex: none;
  display: inline-flex;
  gap: var(--bs-space-1);
}
</style>
