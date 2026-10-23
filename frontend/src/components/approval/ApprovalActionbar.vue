<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import {
  approveTask,
  rejectTask,
  transferTask,
  addSignTask,
  withdrawInstance,
} from '@/api/approval'
import { userOptions as fetchUserOptions } from '@/api/admin'
import type { ApprovalTask } from '@/api/types'

const props = defineProps<{
  task: ApprovalTask
  canAct?: boolean
  canWithdraw?: boolean
}>()

const emit = defineEmits<{
  (e: 'done'): void
}>()

const { t } = useI18n()
const comment = ref('')
const loading = ref(false)
const transferVisible = ref(false)
const addSignVisible = ref(false)
const targetUserId = ref<number | null>(null)
const userOptions = ref<{ id: number; name: string }[]>([])

const canAct = computed(() => props.canAct !== false)

async function loadUsers() {
  if (userOptions.value.length) return
  try {
    // 轻量选人端点（登录可用）：非管理员审批人也能转办/加签
    const data = await fetchUserOptions()
    userOptions.value = (data ?? []).map((u) => ({ id: u.id, name: u.label }))
  } catch {
    userOptions.value = []
  }
}

async function act(kind: 'agree' | 'reject') {
  if (kind === 'reject' && !comment.value.trim()) {
    ElMessage.warning(t('approval.approval.commentRequired'))
    return
  }
  loading.value = true
  try {
    if (kind === 'agree') await approveTask(props.task.id, comment.value)
    else await rejectTask(props.task.id, comment.value)
    ElMessage.success(t('common.message.submitSuccess'))
    comment.value = ''
    emit('done')
  } catch {
    /* http notifies */
  } finally {
    loading.value = false
  }
}

async function doTransfer() {
  if (!targetUserId.value) return
  if (!comment.value.trim()) {
    ElMessage.warning(t('approval.approval.commentRequired'))
    return
  }
  loading.value = true
  try {
    await transferTask(props.task.id, targetUserId.value, comment.value)
    ElMessage.success(t('common.message.submitSuccess'))
    transferVisible.value = false
    comment.value = ''
    emit('done')
  } catch {
    /* http notifies */
  } finally {
    loading.value = false
  }
}

async function doAddSign() {
  if (!targetUserId.value) return
  if (!comment.value.trim()) {
    ElMessage.warning(t('approval.approval.commentRequired'))
    return
  }
  loading.value = true
  try {
    await addSignTask(props.task.id, targetUserId.value, comment.value)
    ElMessage.success(t('common.message.submitSuccess'))
    addSignVisible.value = false
    comment.value = ''
    emit('done')
  } catch {
    /* http notifies */
  } finally {
    loading.value = false
  }
}

async function doWithdraw() {
  try {
    await ElMessageBox.confirm(t('approval.approval.withdrawConfirm'), t('common.action.confirm'), {
      type: 'warning',
    })
  } catch {
    return
  }
  loading.value = true
  try {
    await withdrawInstance(props.task.instanceId)
    ElMessage.success(t('common.message.submitSuccess'))
    emit('done')
  } catch {
    /* http notifies */
  } finally {
    loading.value = false
  }
}

async function openTransfer() {
  await loadUsers()
  targetUserId.value = null
  transferVisible.value = true
}

async function openAddSign() {
  await loadUsers()
  targetUserId.value = null
  addSignVisible.value = true
}
</script>

<template>
  <div class="approval-actionbar">
    <el-input
      v-model="comment"
      type="textarea"
      :rows="2"
      :placeholder="t('approval.approval.commentPlaceholder')"
      class="comment-input"
    />
    <div class="action-btns">
      <template v-if="canAct">
        <el-button type="primary" :loading="loading" @click="act('agree')">
          {{ t('approval.approval.agree') }}
        </el-button>
        <el-button type="danger" :loading="loading" @click="act('reject')">
          {{ t('approval.approval.reject') }}
        </el-button>
        <el-button @click="openTransfer">{{ t('approval.approval.transfer') }}</el-button>
        <el-button @click="openAddSign">{{ t('approval.approval.addSign') }}</el-button>
      </template>
      <el-button v-if="props.canWithdraw" :loading="loading" @click="doWithdraw">
        {{ t('approval.approval.withdraw') }}
      </el-button>
    </div>

    <el-dialog v-model="transferVisible" :title="t('approval.approval.transferTo')" width="420px" append-to-body>
      <el-select v-model="targetUserId" :placeholder="t('approval.approval.selectUser')" filterable style="width: 100%">
        <el-option v-for="u in userOptions" :key="u.id" :label="u.name" :value="u.id" />
      </el-select>
      <template #footer>
        <el-button @click="transferVisible = false">{{ t('common.action.cancel') }}</el-button>
        <el-button type="primary" :loading="loading" @click="doTransfer">{{ t('common.action.confirm') }}</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="addSignVisible" :title="t('approval.approval.addSignTo')" width="420px" append-to-body>
      <el-select v-model="targetUserId" :placeholder="t('approval.approval.selectUser')" filterable style="width: 100%">
        <el-option v-for="u in userOptions" :key="u.id" :label="u.name" :value="u.id" />
      </el-select>
      <template #footer>
        <el-button @click="addSignVisible = false">{{ t('common.action.cancel') }}</el-button>
        <el-button type="primary" :loading="loading" @click="doAddSign">{{ t('common.action.confirm') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.approval-actionbar {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
}

.action-btns {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bs-space-2);
}
</style>
