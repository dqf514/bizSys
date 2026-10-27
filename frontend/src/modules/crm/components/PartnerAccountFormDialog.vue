<script setup lang="ts">
/** 合作方账号新建/编辑对话框：新建含登录名与初始密码（直接启用）；编辑支持改绑/解绑往来单位（清空即解绑）。 */
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import RemoteSelect, { type RemoteOption } from '@/components/form/RemoteSelect.vue'
import { createPartnerAccount, customerOptions, updatePartnerAccount } from '@/api/crm'
import type { PartnerAccount } from '@/api/types'

defineOptions({ name: 'PartnerAccountFormDialog' })

const props = defineProps<{ modelValue: boolean; account: PartnerAccount | null }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void; (e: 'saved'): void }>()

const { t } = useI18n()
const isEdit = computed(() => !!props.account)
const saving = ref(false)
const formRef = ref()

const form = reactive({
  username: '',
  password: '',
  companyName: '',
  contactName: '',
  phone: '',
  email: '',
  customerId: null as number | null,
})
/** 编辑回显：当前绑定单位名称（仅展示用） */
const bindLabel = ref('')

watch(
  () => props.modelValue,
  (v) => {
    if (!v) return
    const a = props.account
    Object.assign(form, {
      username: a?.username ?? '',
      password: '',
      companyName: a?.companyName ?? '',
      contactName: a?.contactName ?? '',
      phone: a?.phone ?? '',
      email: a?.email ?? '',
      customerId: a?.customerId ?? null,
    })
    bindLabel.value = a?.customerName ?? ''
  },
)

async function fetchSuppliers(q: string): Promise<RemoteOption[]> {
  try {
    const list = ((await customerOptions(q, 20, 'supplier')) ?? []) as RemoteOption[]
    // 编辑回显：当前绑定单位不在首屏结果时补一条，保证名称正常显示
    if (!q && form.customerId && bindLabel.value && !list.some((o) => String(o.id) === String(form.customerId))) {
      list.unshift({ id: form.customerId, label: bindLabel.value })
    }
    return list
  } catch {
    return []
  }
}

const rules = computed(() => ({
  username: [
    { required: true, message: t('common.form.required'), trigger: 'blur' },
    { pattern: /^[a-zA-Z0-9_.-]{4,64}$/, message: t('crm.account.usernameRule'), trigger: 'blur' },
  ],
  password: [
    { required: true, message: t('common.form.required'), trigger: 'blur' },
    { min: 8, max: 64, message: t('crm.account.passwordRule'), trigger: 'blur' },
  ],
  companyName: [
    { required: true, message: t('common.form.required'), trigger: 'blur' },
    { min: 2, max: 255, message: t('crm.account.companyRule'), trigger: 'blur' },
  ],
}))

async function submit() {
  if (!formRef.value) return
  const ok = await formRef.value.validate().catch(() => false)
  if (!ok) return
  saving.value = true
  try {
    if (isEdit.value && props.account) {
      // customerId 始终显式发送：选中=改绑，清空(null)=解绑
      await updatePartnerAccount(props.account.id, {
        companyName: form.companyName,
        contactName: form.contactName,
        phone: form.phone,
        email: form.email,
        customerId: form.customerId,
      })
    } else {
      await createPartnerAccount({
        username: form.username,
        password: form.password,
        companyName: form.companyName,
        contactName: form.contactName,
        phone: form.phone,
        email: form.email,
        customerId: form.customerId ?? undefined,
      })
    }
    ElMessage.success(t('common.message.saveSuccess'))
    emit('update:modelValue', false)
    emit('saved')
  } catch {
    /* http notifies */
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    :title="t(isEdit ? 'crm.account.edit' : 'crm.account.create')"
    width="560px"
    append-to-body
    @update:model-value="emit('update:modelValue', $event)"
  >
    <p v-if="isEdit" class="muted form-tip">{{ t('crm.account.unbindTip') }}</p>
    <el-form ref="formRef" :model="form" :rules="rules" label-width="110px">
      <el-form-item v-if="!isEdit" :label="t('crm.account.username')" prop="username">
        <el-input v-model="form.username" :maxlength="64" :placeholder="t('crm.account.usernameRule')" />
      </el-form-item>
      <el-form-item v-if="!isEdit" :label="t('crm.account.initPassword')" prop="password">
        <el-input v-model="form.password" type="password" show-password :maxlength="64" />
      </el-form-item>
      <el-form-item :label="t('crm.account.companyName')" prop="companyName">
        <el-input v-model="form.companyName" :maxlength="255" />
      </el-form-item>
      <el-form-item :label="t('crm.account.contactName')">
        <el-input v-model="form.contactName" :maxlength="64" />
      </el-form-item>
      <el-form-item :label="t('crm.account.phone')">
        <el-input v-model="form.phone" :maxlength="32" />
      </el-form-item>
      <el-form-item :label="t('crm.account.email')">
        <el-input v-model="form.email" :maxlength="128" />
      </el-form-item>
      <el-form-item :label="t('crm.account.bindPartner')">
        <RemoteSelect
          v-model="form.customerId"
          :fetch="fetchSuppliers"
          :placeholder="t('procurement.contract.supplierPlaceholder')"
          clearable
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="emit('update:modelValue', false)">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="saving" @click="submit">{{ t('common.action.save') }}</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.muted {
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-sm);
}

.form-tip {
  margin: 0 0 var(--bs-space-3);
}
</style>
