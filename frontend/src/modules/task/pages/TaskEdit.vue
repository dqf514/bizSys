<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, type FormInstance } from 'element-plus'
import { useI18n } from 'vue-i18n'
import ContractSelect from '@/components/form/ContractSelect.vue'
import { useDictOptions } from '@/composables/useDict'
import { getTask, createTask, updateTask, taskAction } from '@/api/task'
import { listDepts } from '@/api/admin'
import type { Dept, TaskItem, TaskSample } from '@/api/types'

defineOptions({ name: 'TaskEdit' })

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const step = ref(0)
const savingDraft = ref(false)
const savingSubmit = ref(false)
const loading = ref(false)
const isEdit = ref(false)
const taskId = ref<number | null>(null)
const basicFormRef = ref<FormInstance>()

const form = reactive({
  taskName: '',
  taskType: '',
  contractId: null as number | null,
  contractNo: '',
  content: '',
  receiver: '',
  receiverUnit: '',
  bizBlock: '',
  deptId: null as number | null,
  planFinishDate: '',
  partySystem: '',
})

// display only — the server binds the customer from the chosen contract
const customerName = ref('')

const items = ref<TaskItem[]>([])
const samples = ref<TaskSample[]>([])
const deptTree = ref<Dept[]>([])

const typeOpts = useDictOptions('task_type')
const blockOpts = useDictOptions('biz_block')

function newItem(): TaskItem {
  return {
    itemCode: '',
    name: '',
    std: '',
    dept: '',
    inspector: '',
    qty: 1,
    settleType: '',
    needReport: false,
    reportNo: '',
    reportStatus: '',
  }
}

function newSample(): TaskSample {
  return {
    sampleNo: '',
    name: '',
    model: '',
    vin: '',
    vehicleType: '',
    sampleDate: '',
    inStock: 'in',
  }
}

async function load() {
  const idParam = route.params.id
  try {
    const depts = await listDepts()
    deptTree.value = Array.isArray(depts) ? depts : (depts.items ?? [])
  } catch {
    deptTree.value = []
  }
  if (!idParam) {
    items.value = [newItem()]
    samples.value = [newSample()]
    return
  }
  isEdit.value = true
  taskId.value = Number(idParam)
  loading.value = true
  try {
    const data = await getTask(taskId.value)
    customerName.value = data.customerName ?? ''
    Object.assign(form, {
      taskName: data.taskName ?? '',
      taskType: data.taskType ?? '',
      contractId: data.contractId ?? null,
      contractNo: data.contractNo ?? '',
      content: data.content ?? '',
      receiver: data.receiver ?? '',
      receiverUnit: data.receiverUnit ?? '',
      bizBlock: data.bizBlock ?? '',
      deptId: data.deptId ?? null,
      planFinishDate: data.planFinishDate ?? '',
      partySystem: data.partySystem ?? '',
    })
    items.value = (data.items ?? []).map((x) => ({ ...x }))
    samples.value = (data.samples ?? []).map((x) => ({ ...x }))
    if (!items.value.length) items.value = [newItem()]
    if (!samples.value.length) samples.value = [newSample()]
    if (!['draft', 'rejected'].includes(data.status)) {
      ElMessage.warning(t('task.task.editOnlyDraft'))
      router.replace(`/task/tasks/${taskId.value}`)
    }
  } catch {
    /* http notifies */
  } finally {
    loading.value = false
  }
}

onMounted(() => void load())

const stepTitles = [
  'task.task.stepBasic',
  'task.task.stepAssign',
  'task.task.stepItems',
  'task.task.stepSubmit',
]

/** 选中合同后自动带出关联信息：客户名、付款/接收单位（仍可手改） */
function onContractChange(v: number | string | null, opt?: { label?: string; customerName?: string; paymentOrg?: string }) {
  form.contractId = (v as number) ?? null
  form.contractNo = opt?.label ?? ''
  customerName.value = opt?.customerName ?? ''
  if (!form.receiverUnit) form.receiverUnit = opt?.paymentOrg || opt?.customerName || ''
}

async function next() {
  if (step.value === 0 && basicFormRef.value) {
    const ok = await basicFormRef.value.validate().catch(() => false)
    if (!ok) return
  }
  if (step.value < 3) step.value += 1
}

function prev() {
  if (step.value > 0) step.value -= 1
}

/** 落库（新建/更新），返回任务 id；失败返回 null */
async function persist(): Promise<number | null> {
  try {
    const payload = {
      ...form,
      planFinishDate: form.planFinishDate || null,
      items: items.value.filter((x) => x.name || x.itemCode),
      samples: samples.value
        .filter((x) => x.name || x.sampleNo)
        .map((x) => ({ ...x, sampleDate: x.sampleDate || null })),
    }
    if (isEdit.value && taskId.value) {
      await updateTask(taskId.value, payload as never)
    } else {
      const created = await createTask(payload as never)
      taskId.value = created?.id ?? null
      isEdit.value = true
    }
    return taskId.value
  } catch {
    /* http notifies */
    return null
  }
}

/** 保存草稿：仅校验任务名称（草稿宽容），不发编号、不进流程 */
async function saveDraft() {
  if (!basicFormRef.value) return
  const ok = await basicFormRef.value
    .validateField(['taskName'])
    .then(() => true)
    .catch(() => false)
  if (!ok) {
    step.value = 0
    return
  }
  savingDraft.value = true
  try {
    if ((await persist()) === null) return
    ElMessage.success(t('common.message.saveSuccess'))
    router.push('/task/tasks')
  } finally {
    savingDraft.value = false
  }
}

/** 提交审批：完整校验 → 落库 → 提交（发编号、进入流程） */
async function saveAndSubmit() {
  if (!basicFormRef.value) return
  const ok = await basicFormRef.value.validate().catch(() => false)
  if (!ok) {
    step.value = 0
    return
  }
  savingSubmit.value = true
  try {
    const id = await persist()
    if (id === null) return
    await taskAction(id, 'submit')
    ElMessage.success(t('common.message.submitSuccess'))
    router.push('/task/tasks')
  } catch {
    /* http notifies */
  } finally {
    savingSubmit.value = false
  }
}
</script>

<template>
  <div class="task-edit" v-loading="loading">
    <div class="edit-header">
      <h2 class="edit-title">{{ isEdit ? t('task.task.edit') : t('task.task.create') }}</h2>
      <div>
        <el-button @click="router.push('/task/tasks')">{{ t('common.action.cancel') }}</el-button>
      </div>
    </div>

    <el-steps :active="step" align-center class="steps">
      <el-step v-for="s in stepTitles" :key="s" :title="t(s)" />
    </el-steps>

    <div class="step-body">
      <!-- step 0: basic + contract（合并页：选合同自动带出客户/接收单位） -->
      <el-form v-show="step === 0" ref="basicFormRef" :model="form" label-width="130px">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item :label="t('task.task.taskName')" prop="taskName" :rules="[{ required: true, message: t('common.form.required') }]">
              <el-input v-model="form.taskName" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('task.task.taskType')" prop="taskType" :rules="[{ required: true, message: t('common.form.required') }]">
              <el-select v-model="form.taskType" style="width: 100%">
                <el-option v-for="o in typeOpts.opts.value" :key="o.value" :label="o.label" :value="o.value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('task.task.contractId')">
              <ContractSelect
                :model-value="form.contractId"
                :placeholder="t('contract.contract.onlyApproved')"
                @change="onContractChange"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('task.task.customerName')">
              <el-input :model-value="customerName" disabled :placeholder="t('task.task.customerFromContract')" />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item :label="t('task.task.content')">
              <el-input v-model="form.content" type="textarea" :rows="3" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('task.task.partySystem')">
              <el-input v-model="form.partySystem" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('task.task.planFinishDate')">
              <el-date-picker v-model="form.planFinishDate" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>

      <!-- step 1: assignment -->
      <el-form v-show="step === 1" label-width="130px">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item :label="t('task.task.bizBlock')">
              <el-select v-model="form.bizBlock" clearable style="width: 100%">
                <el-option v-for="o in blockOpts.opts.value" :key="o.value" :label="o.label" :value="o.value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('task.task.deptId')">
              <el-tree-select
                v-model="form.deptId"
                :data="deptTree"
                :props="{ label: 'name', value: 'id', children: 'children' }"
                check-strictly
                clearable
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('task.task.receiver')">
              <el-input v-model="form.receiver" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('task.task.receiverUnit')">
              <el-input v-model="form.receiverUnit" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>

      <!-- step 2: items & samples -->
      <div v-show="step === 2" class="dyn-section">
        <div class="dyn-title">
          {{ t('task.task.items') }}
          <el-button size="small" type="primary" plain @click="items.push(newItem())">
            {{ t('task.task.addItem') }}
          </el-button>
        </div>
        <el-table :data="items" border size="small">
          <el-table-column :label="t('task.task.itemCode')" min-width="110">
            <template #default="{ row }"><el-input v-model="row.itemCode" size="small" /></template>
          </el-table-column>
          <el-table-column :label="t('task.task.itemName')" min-width="130">
            <template #default="{ row }"><el-input v-model="row.name" size="small" /></template>
          </el-table-column>
          <el-table-column :label="t('task.task.itemStd')" min-width="110">
            <template #default="{ row }"><el-input v-model="row.std" size="small" /></template>
          </el-table-column>
          <el-table-column :label="t('task.task.itemDept')" min-width="130">
            <template #default="{ row }">
              <el-select v-model="row.dept" size="small" clearable filterable style="width: 100%">
                <el-option v-for="o in blockOpts.opts.value" :key="o.value" :label="o.label" :value="o.label" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column :label="t('task.task.itemInspector')" min-width="100">
            <template #default="{ row }"><el-input v-model="row.inspector" size="small" /></template>
          </el-table-column>
          <el-table-column :label="t('task.task.itemQty')" width="90">
            <template #default="{ row }"><el-input-number v-model="row.qty" size="small" :min="0" controls-position="right" /></template>
          </el-table-column>
          <el-table-column :label="t('task.task.itemNeedReport')" width="90">
            <template #default="{ row }"><el-switch v-model="row.needReport" /></template>
          </el-table-column>
          <el-table-column width="80" fixed="right">
            <template #default="{ $index }">
              <el-button link type="danger" @click="items.splice($index, 1)">{{ t('common.action.delete') }}</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="dyn-title" style="margin-top: 16px">
          {{ t('task.task.samples') }}
          <el-button size="small" type="primary" plain @click="samples.push(newSample())">
            {{ t('task.task.addSample') }}
          </el-button>
        </div>
        <el-table :data="samples" border size="small">
          <el-table-column :label="t('task.task.sampleName')" min-width="130">
            <template #default="{ row }"><el-input v-model="row.name" size="small" /></template>
          </el-table-column>
          <el-table-column :label="t('task.task.sampleModel')" min-width="110">
            <template #default="{ row }"><el-input v-model="row.model" size="small" /></template>
          </el-table-column>
          <el-table-column min-width="130">
            <template #header>
              <el-tooltip :content="t('task.task.sampleVinTip')" placement="top">
                <span>{{ t('task.task.sampleVin') }}</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <el-input v-model="row.vin" size="small" :placeholder="t('task.task.sampleVinPlaceholder')" />
            </template>
          </el-table-column>
          <el-table-column :label="t('task.task.sampleVehicleType')" min-width="110">
            <template #default="{ row }"><el-input v-model="row.vehicleType" size="small" /></template>
          </el-table-column>
          <el-table-column :label="t('task.task.sampleDate')" min-width="130">
            <template #default="{ row }">
              <el-date-picker v-model="row.sampleDate" type="date" value-format="YYYY-MM-DD" size="small" />
            </template>
          </el-table-column>
          <el-table-column width="80" fixed="right">
            <template #default="{ $index }">
              <el-button link type="danger" @click="samples.splice($index, 1)">{{ t('common.action.delete') }}</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- step 3: submit -->
      <div v-show="step === 3" class="submit-summary">
        <el-descriptions :column="2" border>
          <el-descriptions-item :label="t('task.task.taskName')">{{ form.taskName }}</el-descriptions-item>
          <el-descriptions-item :label="t('task.task.taskType')">{{ form.taskType }}</el-descriptions-item>
          <el-descriptions-item :label="t('task.task.contractNo')">{{ form.contractNo || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('task.task.bizBlock')">{{ form.bizBlock || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('task.task.items')">{{ items.filter((x) => x.name).length }}</el-descriptions-item>
          <el-descriptions-item :label="t('task.task.samples')">{{ samples.filter((x) => x.name).length }}</el-descriptions-item>
        </el-descriptions>
      </div>
    </div>

    <div class="step-footer">
      <el-button :disabled="step === 0" @click="prev">{{ t('task.task.stepPrev') }}</el-button>
      <el-button v-if="step < 3" type="primary" plain @click="next">{{ t('task.task.stepNext') }}</el-button>
      <el-button :loading="savingDraft" @click="saveDraft">{{ t('common.action.saveDraft') }}</el-button>
      <el-button type="primary" :loading="savingSubmit" @click="saveAndSubmit">{{ t('common.action.submitApproval') }}</el-button>
    </div>
  </div>
</template>

<style scoped>
.task-edit {
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

.steps {
  max-width: 800px;
  margin: 0 auto;
}

.step-body {
  flex: 1;
  min-height: 200px;
}

.dyn-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--bs-space-2);
  font-weight: 600;
}

.step-footer {
  display: flex;
  justify-content: center;
  gap: var(--bs-space-2);
  padding: var(--bs-space-3) 0;
}
</style>
