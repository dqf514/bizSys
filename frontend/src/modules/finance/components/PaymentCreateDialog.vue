<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage, type FormInstance } from 'element-plus'
import { useI18n } from 'vue-i18n'
import RemoteSelect, { type RemoteOption } from '@/components/form/RemoteSelect.vue'
import SmartInput from '@/components/form/SmartInput.vue'
import { useDictOptions } from '@/composables/useDict'
import { recordSmartHistory } from '@/composables/smartInputHistory'
import { createPayment, listSettlements } from '@/api/finance'
import type { Settlement } from '@/api/types'

const props = withDefaults(
  defineProps<{
    modelValue: boolean
    /** when set (e.g. opened from a settlement row), the settlement is fixed */
    preset?: Settlement | null
  }>(),
  { preset: null },
)

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'saved'): void
}>()

const { t } = useI18n()

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

const payTypeOpts = useDictOptions('pay_type')

const formRef = ref<FormInstance>()
const saving = ref(false)
const form = reactive({
  settlementId: null as number | null,
  payType: '',
  payerName: '',
  payerAccount: '',
  amount: undefined as number | undefined,
  bank: '',
  paidAt: '',
  remark: '',
})

watch(visible, (v) => {
  if (!v) return
  Object.assign(form, {
    settlementId: props.preset?.id ?? null,
    payType: '',
    payerName: '',
    payerAccount: '',
    amount: undefined,
    bank: '',
    paidAt: '',
    remark: '',
  })
})

// backend only allows payment registration on invoiced settlements (80001 otherwise)
async function fetchSettlements(q: string): Promise<RemoteOption[]> {
  try {
    const data = await listSettlements({ q: q || undefined, status: 'invoiced', page: 1, size: 20 })
    return (data.items ?? []).map((s) => ({
      id: s.id,
      label: `${s.settlementNo} / ${s.customerName}`,
      sub: String(s.amount ?? ''),
    }))
  } catch {
    return []
  }
}

async function save() {
  if (!formRef.value) return
  const ok = await formRef.value.validate().catch(() => false)
  if (!ok) return
  if (!form.settlementId) return
  saving.value = true
  try {
    await createPayment({
      settlementId: form.settlementId,
      payType: form.payType,
      payerName: form.payerName,
      payerAccount: form.payerAccount || undefined,
      amount: Number(form.amount),
      bank: form.bank || undefined,
      paidAt: form.paidAt,
      remark: form.remark || undefined,
    })
    recordSmartHistory('finance.payment.payerName', form.payerName)
    recordSmartHistory('finance.payment.bank', form.bank)
    ElMessage.success(t('common.message.createSuccess'))
    visible.value = false
    emit('saved')
  } catch {
    /* http notifies */
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <el-dialog v-model="visible" :title="t('finance.payment.create')" width="560px" append-to-body>
    <el-form ref="formRef" :model="form" label-width="110px">
      <el-form-item
        :label="t('finance.payment.selectSettlement')"
        prop="settlementId"
        :rules="[{ required: true, message: t('common.form.required') }]"
      >
        <el-input
          v-if="props.preset"
          :model-value="`${props.preset.settlementNo} / ${props.preset.customerName}`"
          disabled
        />
        <RemoteSelect v-else v-model="form.settlementId" :fetch="fetchSettlements" />
      </el-form-item>
      <el-form-item
        :label="t('finance.payment.payType')"
        prop="payType"
        :rules="[{ required: true, message: t('common.form.required') }]"
      >
        <el-select
          v-model="form.payType"
          clearable
          filterable
          :placeholder="t('common.form.placeholderSelect')"
          style="width: 100%"
        >
          <el-option v-for="o in payTypeOpts.opts.value" :key="o.value" :label="o.label" :value="o.value" />
        </el-select>
      </el-form-item>
      <el-form-item
        :label="t('finance.payment.payerName')"
        prop="payerName"
        :rules="[{ required: true, message: t('common.form.required') }]"
      >
        <SmartInput v-model="form.payerName" field="finance.payment.payerName" :maxlength="128" />
      </el-form-item>
      <el-form-item :label="t('finance.payment.payerAccount')">
        <el-input v-model="form.payerAccount" :maxlength="64" />
      </el-form-item>
      <el-form-item
        :label="t('finance.payment.amount')"
        prop="amount"
        :rules="[{ required: true, type: 'number', message: t('common.form.required') }]"
      >
        <el-input-number v-model="form.amount" :min="0" :precision="2" style="width: 100%" />
      </el-form-item>
      <el-form-item :label="t('finance.payment.bank')">
        <SmartInput v-model="form.bank" field="finance.payment.bank" :maxlength="128" />
      </el-form-item>
      <el-form-item
        :label="t('finance.payment.paidAt')"
        prop="paidAt"
        :rules="[{ required: true, message: t('common.form.required') }]"
      >
        <el-date-picker v-model="form.paidAt" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
      </el-form-item>
      <el-form-item :label="t('finance.payment.remark')">
        <el-input v-model="form.remark" type="textarea" :rows="2" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="saving" @click="save">{{ t('common.action.save') }}</el-button>
    </template>
  </el-dialog>
</template>
