<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, type FormInstance } from 'element-plus'
import { useI18n } from 'vue-i18n'
import CustomerSelect from '@/components/form/CustomerSelect.vue'
import UploadFiles from '@/components/form/UploadFiles.vue'
import { useDictOptions } from '@/composables/useDict'
import {
  getContract,
  createContract,
  updateContract,
  uploadContractAttachment,
  downloadAttachment,
} from '@/api/contract'
import type { Attachment, Contract } from '@/api/types'

defineOptions({ name: 'ContractEdit' })

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const formRef = ref<FormInstance>()
const saving = ref(false)
const loading = ref(false)
const isEdit = ref(false)
const contractId = ref<number | null>(null)

const form = reactive({
  name: '',
  customerId: undefined as number | undefined,
  customerName: '',
  contractType: '',
  subjectType: '',
  amount: 0 as number | string,
  startDate: '',
  endDate: '',
  payCycle: '',
  delivery: '',
  sealType: '',
  handlerName: '',
  frameworkNo: '',
  paymentOrg: '',
  remark: '',
})

const attachments = ref<Attachment[]>([])

const typeOpts = useDictOptions('contract_type')
const payCycleOpts = useDictOptions('pay_cycle')
const deliveryOpts = useDictOptions('delivery_way')

async function load() {
  const idParam = route.params.id
  if (!idParam) return
  isEdit.value = true
  contractId.value = Number(idParam)
  loading.value = true
  try {
    const data: Contract = await getContract(contractId.value)
    Object.assign(form, {
      name: data.name ?? '',
      customerId: data.customerId ?? undefined,
      customerName: data.customerName ?? '',
      contractType: data.contractType ?? '',
      subjectType: data.subjectType ?? '',
      amount: data.amount ?? 0,
      startDate: data.startDate ?? '',
      endDate: data.endDate ?? '',
      payCycle: data.payCycle ?? '',
      delivery: data.delivery ?? '',
      sealType: data.sealType ?? '',
      handlerName: data.handlerName ?? '',
      frameworkNo: data.frameworkNo ?? '',
      paymentOrg: data.paymentOrg ?? '',
      remark: data.remark ?? '',
    })
    attachments.value = data.attachments ?? []
    if (data.status !== 'draft' && data.status !== 'rejected') {
      ElMessage.warning(t('contract.contract.statusApproving'))
      router.replace(`/contract/contracts/${contractId.value}`)
    }
  } catch {
    /* http notifies */
  } finally {
    loading.value = false
  }
}

onMounted(() => void load())

async function save() {
  if (!formRef.value) return
  const ok = await formRef.value.validate().catch(() => false)
  if (!ok) return
  saving.value = true
  try {
    const payload = {
      ...form,
      amount: Number(form.amount) || 0,
      attachments: attachments.value,
    }
    if (isEdit.value && contractId.value) {
      await updateContract(contractId.value, payload)
    } else {
      const created = await createContract(payload)
      contractId.value = created?.id ?? null
      isEdit.value = true
    }
    ElMessage.success(t('common.message.saveSuccess'))
    router.push('/contract/contracts')
  } catch {
    /* http notifies */
  } finally {
    saving.value = false
  }
}

async function upload(file: File) {
  if (!contractId.value) {
    // hold locally until saved
    return { id: Date.now(), fileName: file.name, size: file.size }
  }
  return uploadContractAttachment(contractId.value, file)
}

function cancel() {
  router.push('/contract/contracts')
}
</script>

<template>
  <div class="contract-edit" v-loading="loading">
    <div class="edit-header">
      <h2 class="edit-title">{{ isEdit ? t('contract.contract.edit') : t('contract.contract.create') }}</h2>
      <div>
        <el-button @click="cancel">{{ t('common.action.cancel') }}</el-button>
        <el-button type="primary" :loading="saving" @click="save">{{ t('common.action.save') }}</el-button>
      </div>
    </div>

    <el-form ref="formRef" :model="form" label-width="130px" class="edit-form">
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item :label="t('contract.contract.name')" prop="name" :rules="[{ required: true, message: t('common.form.required') }]">
            <el-input v-model="form.name" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('contract.contract.customer')" prop="customerId" :rules="[{ required: true, message: t('common.form.required') }]">
            <CustomerSelect
              :model-value="form.customerId"
              @change="
                (v, opt) => {
                  form.customerId = v as number
                  form.customerName = opt?.label ?? ''
                }
              "
            />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('contract.contract.contractType')">
            <el-select v-model="form.contractType" clearable style="width: 100%">
              <el-option v-for="o in typeOpts.opts.value" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('contract.contract.amount')" prop="amount">
            <el-input-number v-model="form.amount" :min="0" :precision="2" :step="1000" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('contract.contract.startDate')" prop="startDate" :rules="[{ required: true, message: t('common.form.required') }]">
            <el-date-picker v-model="form.startDate" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('contract.contract.endDate')" prop="endDate" :rules="[{ required: true, message: t('common.form.required') }]">
            <el-date-picker v-model="form.endDate" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('contract.contract.payCycle')">
            <el-select v-model="form.payCycle" clearable style="width: 100%">
              <el-option v-for="o in payCycleOpts.opts.value" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('contract.contract.delivery')">
            <el-select v-model="form.delivery" clearable style="width: 100%">
              <el-option v-for="o in deliveryOpts.opts.value" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('contract.contract.sealType')">
            <el-input v-model="form.sealType" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('contract.contract.handlerName')">
            <el-input v-model="form.handlerName" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('contract.contract.frameworkNo')">
            <el-input v-model="form.frameworkNo" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('contract.contract.paymentOrg')">
            <el-input v-model="form.paymentOrg" />
          </el-form-item>
        </el-col>
        <el-col :span="24">
          <el-form-item :label="t('contract.contract.remark')">
            <el-input v-model="form.remark" type="textarea" :rows="3" />
          </el-form-item>
        </el-col>
        <el-col :span="24">
          <el-form-item :label="t('contract.contract.attachments')">
            <UploadFiles
              :files="attachments"
              :upload="upload"
              :download="downloadAttachment"
              @update:files="attachments = $event"
            />
          </el-form-item>
        </el-col>
      </el-row>
    </el-form>
  </div>
</template>

<style scoped>
.contract-edit {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-3);
  padding: var(--bs-space-4);
  height: 100%;
  overflow: auto;
  background: var(--bs-color-bg-surface);
}

.edit-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.edit-title {
  font-size: var(--bs-typography-font-size-lg);
  font-weight: 600;
}

.edit-form {
  max-width: 960px;
}
</style>
