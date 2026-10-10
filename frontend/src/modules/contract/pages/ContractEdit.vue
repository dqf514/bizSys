<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, type FormInstance } from 'element-plus'
import { useI18n } from 'vue-i18n'
import CustomerSelect from '@/components/form/CustomerSelect.vue'
import SmartInput from '@/components/form/SmartInput.vue'
import UploadFiles from '@/components/form/UploadFiles.vue'
import { useDictOptions } from '@/composables/useDict'
import { recordSmartHistory } from '@/composables/smartInputHistory'
import {
  getContract,
  createContract,
  updateContract,
  uploadContractAttachment,
  downloadAttachment,
  deleteAttachment,
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
// files chosen before the contract is saved — uploaded for real after create
const pendingFiles = ref<{ localId: string; file: File }[]>([])

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
      // never submit locally-staged attachments (their ids are placeholders)
      attachments: attachments.value.filter((a) => !pendingFiles.value.some((p) => p.localId === a.id)),
    }
    if (isEdit.value && contractId.value) {
      await updateContract(contractId.value, payload)
    } else {
      const created = await createContract(payload)
      contractId.value = created?.id ?? null
      isEdit.value = true
    }
    if (contractId.value && pendingFiles.value.length) {
      await flushPending(contractId.value)
    }
    recordSmartHistory('contract.sealType', form.sealType)
    recordSmartHistory('contract.handlerName', form.handlerName)
    recordSmartHistory('contract.frameworkNo', form.frameworkNo)
    recordSmartHistory('contract.paymentOrg', form.paymentOrg)
    ElMessage.success(t('common.message.saveSuccess'))
    router.push('/contract/contracts')
  } catch {
    /* http notifies */
  } finally {
    saving.value = false
  }
}

function onFilesUpdate(files: Attachment[]) {
  attachments.value = files
  // dropping a staged file in the list must also drop it from the upload queue
  pendingFiles.value = pendingFiles.value.filter((p) => files.some((f) => f.id === p.localId))
}

async function upload(file: File) {
  if (!contractId.value) {
    // stage locally; uploaded for real once the contract exists
    const localId = `local-${Date.now()}-${pendingFiles.value.length}`
    pendingFiles.value.push({ localId, file })
    return { id: localId, fileName: file.name, size: file.size }
  }
  return uploadContractAttachment(contractId.value, file)
}

async function flushPending(id: number) {
  for (const p of [...pendingFiles.value]) {
    const real = await uploadContractAttachment(id, p.file)
    attachments.value = attachments.value.map((a) => (a.id === p.localId ? real : a))
    pendingFiles.value = pendingFiles.value.filter((x) => x.localId !== p.localId)
  }
}

async function removeAttachment(fileId: number) {
  await deleteAttachment(fileId)
  ElMessage.success(t('common.message.deleteSuccess'))
}

async function download(fileId: number | string, fileName: string) {
  const pending = pendingFiles.value.find((p) => p.localId === fileId)
  if (pending) {
    const url = URL.createObjectURL(pending.file)
    const a = document.createElement('a')
    a.href = url
    a.download = fileName
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
    return
  }
  return downloadAttachment(fileId, fileName)
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
            <el-select
              v-model="form.contractType"
              clearable
              filterable
              :placeholder="t('common.form.placeholderSelect')"
              style="width: 100%"
            >
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
            <el-select
              v-model="form.payCycle"
              clearable
              filterable
              :placeholder="t('common.form.placeholderSelect')"
              style="width: 100%"
            >
              <el-option v-for="o in payCycleOpts.opts.value" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('contract.contract.delivery')">
            <el-select
              v-model="form.delivery"
              clearable
              filterable
              :placeholder="t('common.form.placeholderSelect')"
              style="width: 100%"
            >
              <el-option v-for="o in deliveryOpts.opts.value" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('contract.contract.sealType')">
            <SmartInput v-model="form.sealType" field="contract.sealType" :maxlength="32" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('contract.contract.handlerName')">
            <SmartInput v-model="form.handlerName" field="contract.handlerName" :maxlength="64" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('contract.contract.frameworkNo')">
            <SmartInput v-model="form.frameworkNo" field="contract.frameworkNo" :maxlength="64" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('contract.contract.paymentOrg')">
            <SmartInput v-model="form.paymentOrg" field="contract.paymentOrg" :maxlength="128" />
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
              :download="download"
              :remove-fn="removeAttachment"
              @update:files="onFilesUpdate"
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
