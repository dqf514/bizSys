<script setup lang="ts">
/** 合作方账号重置密码对话框：自动生成或指定；成功后的新密码仅展示一次，提供复制。 */
import { reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { resetPartnerAccountPassword } from '@/api/crm'
import type { PartnerAccount } from '@/api/types'

defineOptions({ name: 'PartnerAccountResetDialog' })

const props = defineProps<{ modelValue: boolean; account: PartnerAccount | null }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void; (e: 'saved'): void }>()

const { t } = useI18n()
const saving = ref(false)
const formRef = ref()
const form = reactive({ mode: 'auto' as 'auto' | 'manual', password: '' })
const result = ref('')

watch(
  () => props.modelValue,
  (v) => {
    if (!v) return
    Object.assign(form, { mode: 'auto', password: '' })
    result.value = ''
  },
)

const rules = {
  password: [{ min: 8, max: 64, message: t('crm.account.passwordRule'), trigger: 'blur' }],
}

async function submit() {
  if (!props.account) return
  if (form.mode === 'manual') {
    const ok = await formRef.value?.validate().catch(() => false)
    if (!ok) return
  }
  saving.value = true
  try {
    const data = await resetPartnerAccountPassword(
      props.account.id,
      form.mode === 'manual' ? form.password : undefined,
    )
    result.value = data?.password ?? ''
    emit('saved')
  } catch {
    /* http notifies */
  } finally {
    saving.value = false
  }
}

async function copyResult() {
  try {
    await navigator.clipboard.writeText(result.value)
    ElMessage.success(t('common.message.copySuccess'))
  } catch {
    ElMessage.warning(t('common.message.copyFail'))
  }
}

function close() {
  emit('update:modelValue', false)
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    :title="t('crm.account.resetPwd')"
    width="480px"
    append-to-body
    @update:model-value="emit('update:modelValue', $event)"
  >
    <template v-if="!result">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="110px">
        <el-form-item :label="t('crm.account.username')">
          <span>{{ account?.username }}</span>
        </el-form-item>
        <el-form-item :label="t('crm.account.resetMode')">
          <el-radio-group v-model="form.mode">
            <el-radio value="auto">{{ t('crm.account.resetAuto') }}</el-radio>
            <el-radio value="manual">{{ t('crm.account.resetManual') }}</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="form.mode === 'manual'" :label="t('crm.account.newPassword')" prop="password">
          <el-input v-model="form.password" type="password" show-password :maxlength="64" />
        </el-form-item>
      </el-form>
      <p class="muted reset-tip">{{ t('crm.account.resetOnceTip') }}</p>
    </template>
    <template v-else>
      <p class="muted reset-tip">{{ t('crm.account.resetDoneTip') }}</p>
      <div class="pwd-result">
        <code class="pwd-text">{{ result }}</code>
        <el-button size="small" @click="copyResult">{{ t('common.action.copy') }}</el-button>
      </div>
    </template>
    <template #footer>
      <el-button v-if="!result" @click="close">{{ t('common.action.cancel') }}</el-button>
      <el-button v-if="!result" type="primary" :loading="saving" @click="submit">
        {{ t('common.action.confirm') }}
      </el-button>
      <el-button v-else type="primary" @click="close">{{ t('common.action.confirm') }}</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.muted {
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-sm);
}

.reset-tip {
  margin: 0 0 var(--bs-space-2);
}

.pwd-result {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
}

.pwd-text {
  flex: 1;
  padding: var(--bs-space-2);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-bg-inset);
  font-size: var(--bs-typography-font-size-md);
  user-select: all;
}
</style>
