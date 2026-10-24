<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { stepUp } from '@/api/auth'
import type { StepUpResult } from '@/api/types'

defineOptions({ name: 'StepUpDialog' })

const { t } = useI18n()

const visible = ref(false)
const password = ref('')
const loading = ref(false)
let resolver: ((r: StepUpResult) => void) | null = null
let rejecter: ((e: Error) => void) | null = null
let settled = false

/** 打开密码重验弹窗；成功 resolve(StepUpResult)，取消 reject */
function open(): Promise<StepUpResult> {
  password.value = ''
  settled = false
  visible.value = true
  return new Promise((resolve, reject) => {
    resolver = resolve
    rejecter = reject
  })
}

async function confirm() {
  if (!password.value || loading.value) return
  loading.value = true
  try {
    const r = await stepUp(password.value)
    settled = true
    visible.value = false
    resolver?.(r)
  } catch {
    /* http 层已提示 */
  } finally {
    loading.value = false
  }
}

function onClosed() {
  if (!settled) rejecter?.(new Error('cancelled'))
  resolver = null
  rejecter = null
}

defineExpose({ open })
</script>

<template>
  <el-dialog
    v-model="visible"
    :title="t('auth.profile.stepUpTitle')"
    width="400px"
    append-to-body
    @closed="onClosed"
  >
    <p class="stepup-tip">{{ t('auth.profile.stepUpTip') }}</p>
    <el-input
      v-model="password"
      type="password"
      show-password
      :placeholder="t('auth.profile.stepUpPasswordPlaceholder')"
      @keyup.enter="confirm"
    />
    <template #footer>
      <el-button @click="visible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="loading" :disabled="!password" @click="confirm">
        {{ t('auth.profile.verify') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.stepup-tip {
  margin: 0 0 var(--bs-space-3);
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-sm);
}
</style>
