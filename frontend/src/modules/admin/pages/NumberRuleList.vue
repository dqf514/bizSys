<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, type FormInstance } from 'element-plus'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import { listNumberRules, createNumberRule, updateNumberRule } from '@/api/admin'
import type { NumberRule } from '@/api/types'

defineOptions({ name: 'NumberRuleList' })

const { t } = useI18n()

const items = ref<NumberRule[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const data = await listNumberRules()
    items.value = Array.isArray(data) ? data : (data.items ?? [])
  } catch {
    items.value = []
  } finally {
    loading.value = false
  }
}

onMounted(() => void load())

const dialogVisible = ref(false)
const dialogTitle = ref('')
const formRef = ref<FormInstance>()
const saving = ref(false)
const editingId = ref<number | null>(null)
const form = reactive({
  bizType: 'customer',
  prefix: '',
  dateFormat: '',
  seqLen: 5,
  resetCycle: 'none',
  enabled: 1 as number,
})

function cycleLabel(c: string) {
  if (c === 'daily') return t('admin.numbering.cycleDaily')
  if (c === 'monthly') return t('admin.numbering.cycleMonthly')
  if (c === 'yearly') return t('admin.numbering.cycleYearly')
  return t('admin.numbering.cycleNone')
}

function bizLabel(b: string) {
  if (b === 'customer') return t('admin.numbering.bizCustomer')
  if (b === 'contract') return t('admin.numbering.bizContract')
  if (b === 'task') return t('admin.numbering.bizTask')
  if (b === 'report') return t('admin.numbering.bizReport')
  return b
}

function openCreate() {
  editingId.value = null
  dialogTitle.value = t('admin.numbering.create')
  Object.assign(form, {
    bizType: 'customer',
    prefix: '',
    dateFormat: '',
    seqLen: 5,
    resetCycle: 'none',
    enabled: 1,
  })
  dialogVisible.value = true
}

function openEdit(row: NumberRule) {
  editingId.value = row.id
  dialogTitle.value = t('admin.numbering.edit')
  Object.assign(form, {
    bizType: row.bizType,
    prefix: row.prefix,
    dateFormat: row.dateFormat ?? '',
    seqLen: row.seqLen,
    resetCycle: row.resetCycle,
    enabled: Number(row.enabled),
  })
  dialogVisible.value = true
}

async function save() {
  if (!formRef.value) return
  const ok = await formRef.value.validate().catch(() => false)
  if (!ok) return
  saving.value = true
  try {
    if (editingId.value) await updateNumberRule(editingId.value, { ...form })
    else await createNumberRule({ ...form })
    ElMessage.success(t('common.message.saveSuccess'))
    dialogVisible.value = false
    void load()
  } catch {
    /* http notifies */
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <ListPage :title="t('admin.numbering.title')" :loading="loading">
    <template #actions>
      <el-button v-permission="'admin:numbering:edit'" type="primary" @click="openCreate">
        {{ t('admin.numbering.create') }}
      </el-button>
      <el-button @click="load()">{{ t('common.action.refresh') }}</el-button>
    </template>

    <template #table>
      <el-table :data="items" row-key="id" border stripe height="100%">
        <el-table-column :label="t('admin.numbering.bizType')" min-width="110">
          <template #default="{ row }">{{ bizLabel(row.bizType) }}</template>
        </el-table-column>
        <el-table-column :label="t('admin.numbering.prefix')" prop="prefix" width="100" />
        <el-table-column :label="t('admin.numbering.dateFormat')" prop="dateFormat" width="120">
          <template #default="{ row }">{{ row.dateFormat || '-' }}</template>
        </el-table-column>
        <el-table-column :label="t('admin.numbering.seqLen')" prop="seqLen" width="100" />
        <el-table-column :label="t('admin.numbering.resetCycle')" width="110">
          <template #default="{ row }">{{ cycleLabel(row.resetCycle) }}</template>
        </el-table-column>
        <el-table-column :label="t('admin.numbering.enabled')" width="90">
          <template #default="{ row }">
            <el-tag :type="Number(row.enabled) ? 'success' : 'info'" size="small">
              {{ Number(row.enabled) ? t('common.form.enabled') : t('common.form.disabled') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('admin.numbering.preview')" min-width="140">
          <template #default="{ row }">
            <code class="preview-code">{{ row.preview || row.example || '-' }}</code>
          </template>
        </el-table-column>
        <el-table-column :label="t('common.action.operate')" width="110" fixed="right">
          <template #default="{ row }">
            <el-button v-permission="'admin:numbering:edit'" link type="primary" @click="openEdit(row as NumberRule)">
              {{ t('common.action.edit') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </template>
  </ListPage>

  <el-dialog v-model="dialogVisible" :title="dialogTitle" width="520px" append-to-body>
    <el-form ref="formRef" :model="form" label-width="120px">
      <el-form-item :label="t('admin.numbering.bizType')" prop="bizType" :rules="[{ required: true, message: t('common.form.required') }]">
        <el-select v-model="form.bizType" style="width: 100%">
          <el-option :label="t('admin.numbering.bizCustomer')" value="customer" />
          <el-option :label="t('admin.numbering.bizContract')" value="contract" />
          <el-option :label="t('admin.numbering.bizTask')" value="task" />
          <el-option :label="t('admin.numbering.bizReport')" value="report" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('admin.numbering.prefix')" prop="prefix" :rules="[{ required: true, message: t('common.form.required') }]">
        <el-input v-model="form.prefix" />
      </el-form-item>
      <el-form-item :label="t('admin.numbering.dateFormat')">
        <el-input v-model="form.dateFormat" placeholder="%Y%m%d" />
      </el-form-item>
      <el-form-item :label="t('admin.numbering.seqLen')">
        <el-input-number v-model="form.seqLen" :min="1" :max="10" />
      </el-form-item>
      <el-form-item :label="t('admin.numbering.resetCycle')">
        <el-select v-model="form.resetCycle" style="width: 100%">
          <el-option :label="t('admin.numbering.cycleNone')" value="none" />
          <el-option :label="t('admin.numbering.cycleDaily')" value="daily" />
          <el-option :label="t('admin.numbering.cycleMonthly')" value="monthly" />
          <el-option :label="t('admin.numbering.cycleYearly')" value="yearly" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('admin.numbering.enabled')">
        <el-switch v-model="form.enabled" :active-value="1" :inactive-value="0" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="saving" @click="save">{{ t('common.action.save') }}</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.preview-code {
  padding: 2px 6px;
  border-radius: var(--bs-radius-sm);
  background: var(--bs-color-fill-lighter);
  font-family: var(--bs-typography-font-family-mono);
  font-size: var(--bs-typography-font-size-xs);
}
</style>
