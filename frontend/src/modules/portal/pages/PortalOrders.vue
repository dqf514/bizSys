<script setup lang="ts">
/** 在线任务委托（B2）：客户基于已审批合同在线提交委托（仿真 / 模型 / 试验 / 委外），并跟踪受理进度。 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import StatusTag from '@/components/common/StatusTag.vue'
import {
  myPortalContracts,
  myPortalEntrusts,
  portalCancelEntrust,
  portalCreateEntrust,
} from '@/api/portal'
import type { PortalContract, PortalEntrust } from '@/api/types'

defineOptions({ name: 'PortalOrders' })

const { t } = useI18n()

const activeTab = ref<'create' | 'mine'>('create')
const loading = ref(false)
const contracts = ref<PortalContract[]>([])
const entrusts = ref<PortalEntrust[]>([])

/** 委托类型：仿真 / 模型 / 试验 / 委外（与后端字典 entrust_type 对齐） */
const typeOptions = computed(() => [
  { label: t('portal.portal.entrust.typeSim'), value: 'sim' },
  { label: t('portal.portal.entrust.typeModel'), value: 'model' },
  { label: t('portal.portal.entrust.typeTest'), value: 'test' },
  { label: t('portal.portal.entrust.typeOutsource'), value: 'outsource' },
])

const form = ref<{
  title: string
  entrust_type: string
  contract_id: number | null
  requirement: string
  sample_desc: string
  plan_start_date: string
  plan_end_date: string
  priority: string
  items: { itemCode: string; name: string; std: string; qty: number; needReport: boolean }[]
}>({
  title: '',
  entrust_type: 'test',
  contract_id: null,
  requirement: '',
  sample_desc: '',
  plan_start_date: '',
  plan_end_date: '',
  priority: 'normal',
  items: [{ itemCode: '01', name: '', std: '', qty: 1, needReport: true }],
})

async function loadAll() {
  loading.value = true
  try {
    const [c, e] = await Promise.all([myPortalContracts(), myPortalEntrusts()])
    contracts.value = c.items ?? []
    entrusts.value = e.items ?? []
  } catch {
    /* portalHttp notifies */
  } finally {
    loading.value = false
  }
}

onMounted(loadAll)

function addItem() {
  form.value.items.push({
    itemCode: String(form.value.items.length + 1).padStart(2, '0'),
    name: '',
    std: '',
    qty: 1,
    needReport: true,
  })
}

function removeItem(index: number) {
  form.value.items.splice(index, 1)
}

async function submit() {
  const f = form.value
  if (!f.title.trim()) {
    ElMessage.warning(t('portal.portal.entrust.titleRequired'))
    return
  }
  if (!f.contract_id) {
    ElMessage.warning(t('portal.portal.entrust.contractRequired'))
    return
  }
  loading.value = true
  try {
    await portalCreateEntrust({
      title: f.title.trim(),
      entrustType: f.entrust_type,
      contractId: f.contract_id,
      requirement: f.requirement,
      sampleDesc: f.sample_desc,
      planStartDate: f.plan_start_date || null,
      planEndDate: f.plan_end_date || null,
      priority: f.priority,
      items: f.items.map((i) => ({
        itemCode: i.itemCode,
        name: i.name,
        std: i.std,
        qty: i.qty,
        needReport: i.needReport ? 1 : 0,
      })),
    } as unknown as Partial<PortalEntrust>)
    ElMessage.success(t('portal.portal.entrust.submitSuccess'))
    resetForm()
    await loadAll()
    activeTab.value = 'mine'
  } catch {
    /* portalHttp notifies */
  } finally {
    loading.value = false
  }
}

function resetForm() {
  form.value = {
    title: '',
    entrust_type: 'test',
    contract_id: null,
    requirement: '',
    sample_desc: '',
    plan_start_date: '',
    plan_end_date: '',
    priority: 'normal',
    items: [{ itemCode: '01', name: '', std: '', qty: 1, needReport: true }],
  }
}

async function cancel(row: PortalEntrust) {
  try {
    await portalCancelEntrust(row.id)
    ElMessage.success(t('portal.portal.entrust.cancelSuccess'))
    await loadAll()
  } catch {
    /* portalHttp notifies */
  }
}

/** 尚未受理（待受理 / 已驳回）可撤回 */
function canCancel(row: PortalEntrust) {
  return row.status === 'submitted' || row.status === 'rejected'
}

function typeLabel(v: string) {
  return typeOptions.value.find((o) => o.value === v)?.label || v || '-'
}
</script>

<template>
  <div class="portal-orders">
    <h2 class="bs-page-title">{{ t('portal.portal.entrust.title') }}</h2>

    <el-tabs v-model="activeTab">
      <el-tab-pane :label="t('portal.portal.entrust.createTab')" name="create">
        <el-alert
          type="info"
          :closable="false"
          show-icon
          :title="t('portal.portal.entrust.tip')"
          class="entrust-tip"
        />
        <el-form label-position="top" class="entrust-form">
          <el-form-item :label="t('portal.portal.entrust.contract')" required>
            <el-select v-model="form.contract_id" style="width: 100%" :placeholder="t('portal.portal.entrust.contractPlaceholder')">
              <el-option
                v-for="c in contracts"
                :key="c.id"
                :label="`${c.contractNo} ${c.name}`"
                :value="c.id"
              />
            </el-select>
            <div v-if="!contracts.length" class="entrust-hint">{{ t('portal.portal.entrust.noContract') }}</div>
          </el-form-item>
          <el-form-item :label="t('portal.portal.entrust.titleLabel')" required>
            <el-input v-model="form.title" :maxlength="255" :placeholder="t('portal.portal.entrust.titlePlaceholder')" />
          </el-form-item>
          <el-row :gutter="12">
            <el-col :span="12">
              <el-form-item :label="t('portal.portal.entrust.typeLabel')">
                <el-select v-model="form.entrust_type" style="width: 100%">
                  <el-option v-for="o in typeOptions" :key="o.value" :label="o.label" :value="o.value" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item :label="t('portal.portal.entrust.priority')">
                <el-radio-group v-model="form.priority">
                  <el-radio value="normal">{{ t('portal.portal.entrust.priorityNormal') }}</el-radio>
                  <el-radio value="urgent">{{ t('portal.portal.entrust.priorityUrgent') }}</el-radio>
                </el-radio-group>
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="12">
            <el-col :span="12">
              <el-form-item :label="t('portal.portal.entrust.planStartDate')">
                <el-date-picker v-model="form.plan_start_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item :label="t('portal.portal.entrust.planEndDate')">
                <el-date-picker v-model="form.plan_end_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item :label="t('portal.portal.entrust.sampleDesc')">
            <el-input v-model="form.sample_desc" :maxlength="500" :placeholder="t('portal.portal.entrust.sampleDescPlaceholder')" />
          </el-form-item>
          <el-form-item :label="t('portal.portal.entrust.requirement')">
            <el-input
              v-model="form.requirement"
              type="textarea"
              :rows="4"
              :maxlength="4000"
              show-word-limit
              :placeholder="t('portal.portal.entrust.requirementPlaceholder')"
            />
          </el-form-item>
          <el-form-item :label="t('portal.portal.entrust.items')">
            <div class="item-editor">
              <div v-for="(item, idx) in form.items" :key="idx" class="item-row">
                <el-input v-model="item.itemCode" class="item-code" :placeholder="t('portal.portal.entrust.itemCode')" />
                <el-input v-model="item.name" class="item-name" :placeholder="t('portal.portal.entrust.itemName')" />
                <el-input v-model="item.std" class="item-std" :placeholder="t('portal.portal.entrust.itemStd')" />
                <el-input-number v-model="item.qty" :min="0" :controls="false" class="item-qty" />
                <el-checkbox v-model="item.needReport" :label="t('portal.portal.entrust.needReport')" />
                <el-button link type="danger" @click="removeItem(idx)">{{ t('common.action.delete') }}</el-button>
              </div>
              <el-button size="small" @click="addItem">{{ t('portal.portal.entrust.addItem') }}</el-button>
            </div>
          </el-form-item>
          <el-button type="primary" :loading="loading" @click="submit">
            {{ t('portal.portal.entrust.submit') }}
          </el-button>
        </el-form>
      </el-tab-pane>

      <el-tab-pane :label="t('portal.portal.entrust.myTab')" name="mine">
        <el-table v-loading="loading" :data="entrusts" border stripe>
          <el-table-column :label="t('portal.portal.entrust.entrustNo')" prop="entrustNo" width="150">
            <template #default="{ row }">{{ row.entrustNo || '-' }}</template>
          </el-table-column>
          <el-table-column :label="t('portal.portal.entrust.titleLabel')" prop="title" min-width="180" />
          <el-table-column :label="t('portal.portal.entrust.typeLabel')" width="110">
            <template #default="{ row }">{{ typeLabel(row.entrustType) }}</template>
          </el-table-column>
          <el-table-column :label="t('portal.portal.entrust.contract')" prop="contractNo" width="150" />
          <el-table-column :label="t('portal.portal.entrust.planEndDate')" prop="planEndDate" width="120" />
          <el-table-column :label="t('portal.portal.entrust.taskNo')" prop="taskNo" width="150">
            <template #default="{ row }">{{ row.taskNo || '-' }}</template>
          </el-table-column>
          <el-table-column :label="t('portal.portal.status')" width="110" align="center">
            <template #default="{ row }">
              <StatusTag :status="String(row.status)" i18n-prefix="portal.portal.entrust.status" />
            </template>
          </el-table-column>
          <el-table-column :label="t('portal.portal.reviewComment')" prop="reviewComment" min-width="140">
            <template #default="{ row }">{{ row.reviewComment || '-' }}</template>
          </el-table-column>
          <el-table-column :label="t('portal.portal.entrust.createTime')" prop="createTime" width="160" />
          <el-table-column :label="t('common.action.operate')" width="100" align="center">
            <template #default="{ row }">
              <el-button v-if="canCancel(row)" link type="danger" @click="cancel(row)">
                {{ t('portal.portal.entrust.cancel') }}
              </el-button>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <template #empty>{{ t('portal.portal.empty') }}</template>
        </el-table>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.portal-orders {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-4);
}

.entrust-tip {
  margin-bottom: var(--bs-space-4);
}

.entrust-form {
  display: flex;
  flex-direction: column;
  max-width: var(--bs-layout-form-max-width);
}

.entrust-hint {
  margin-top: var(--bs-space-1);
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.item-editor {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
  width: 100%;
}

.item-row {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
}

.item-code {
  width: 70px;
}

.item-name {
  flex: 1;
}

.item-std {
  flex: 1;
}

.item-qty {
  width: 80px;
}
</style>
