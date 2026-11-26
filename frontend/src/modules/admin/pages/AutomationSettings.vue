<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { getAutomation, updateAutomation } from '@/api/settings'
import type { AutomationEvent, AutomationFlow } from '@/api/settings'
import { useAuthStore } from '@/stores/auth'
import PageHeader from '@/components/common/PageHeader.vue'

defineOptions({ name: 'AutomationSettings' })

const { t, te } = useI18n()
const auth = useAuthStore()

/** 只读用户：能看到开关状态但不能改 */
const canEdit = computed(() => auth.hasPerm('admin:automation:edit'))

const loading = ref(false)
const saving = ref(false)
const flows = ref<AutomationFlow[]>([])
const events = ref<AutomationEvent[]>([])

/** 单据类型：优先取 i18n，未登记的新类型回落到后端给的名称 */
function flowLabel(row: AutomationFlow) {
  const key = `admin.automation.flow.${row.bizType}`
  return te(key) ? t(key) : row.label
}

function eventLabel(row: AutomationEvent) {
  const key = `admin.automation.event.${row.event}`
  return te(key) ? t(key) : row.label
}

async function load() {
  loading.value = true
  try {
    const data = await getAutomation()
    flows.value = data.flows ?? []
    events.value = data.events ?? []
  } catch {
    /* http layer already notified */
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  try {
    const payload = {
      flows: flows.value.map((f) => ({ bizType: f.bizType, enabled: f.enabled })),
      events: events.value.flatMap((e) =>
        (e.switches ?? []).map((s) => ({ key: s.key, enabled: s.enabled })),
      ),
    }
    const data = await updateAutomation(payload)
    flows.value = data.flows ?? []
    events.value = data.events ?? []
    ElMessage.success(t('admin.automation.savedTip'))
  } catch {
    /* http layer already notified */
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="bs-page bs-page--scroll" v-loading="loading">
    <PageHeader :title="t('admin.automation.title')" />

    <el-alert type="info" :closable="false" :title="t('admin.automation.intro')" class="intro-alert" />

    <el-card shadow="never" class="section-card">
      <template #header>
        <span class="card-title">{{ t('admin.automation.flowSection') }}</span>
      </template>
      <div class="field-tip">{{ t('admin.automation.flowTip') }}</div>
      <el-table :data="flows" size="small">
        <el-table-column :label="t('admin.automation.bizType')" min-width="130">
          <template #default="{ row }">
            <div class="flow-name">{{ flowLabel(row) }}</div>
            <div class="flow-code">{{ row.bizType }}</div>
          </template>
        </el-table-column>
        <el-table-column :label="t('admin.automation.modeManaged')" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.managed ? 'primary' : 'info'" size="small" disable-transitions>
              {{ row.managed ? t('admin.automation.modeManaged') : t('admin.automation.modeManual') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('admin.automation.definition')" min-width="150">
          <template #default="{ row }">
            <div>{{ row.definitionName || row.definitionCode || '-' }}</div>
            <div class="flow-code">
              {{
                row.definitionReady
                  ? t('admin.automation.definitionReady')
                  : t('admin.automation.definitionMissing')
              }}
            </div>
          </template>
        </el-table-column>
        <el-table-column :label="t('admin.automation.submitFrom')" min-width="140">
          <template #default="{ row }">
            <span class="flow-code">{{ (row.submitFrom ?? []).join(' / ') || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('admin.automation.statusMapping')" min-width="180">
          <template #default="{ row }">
            <div class="status-line">
              <span class="flow-code">{{ t('admin.automation.statusApproving') }}</span>
              <span class="flow-code">→</span>
              <span class="flow-code">{{ row.statuses?.approved || '-' }}</span>
            </div>
            <div class="flow-code">
              {{ t('admin.automation.statusRejected') }} → {{ row.statuses?.rejected || '-' }}
            </div>
          </template>
        </el-table-column>
        <el-table-column :label="t('admin.automation.switchKey')" min-width="150">
          <template #default="{ row }">
            <span class="flow-code">{{ row.switchKey }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('common.form.enabled')" width="90" align="center">
          <template #default="{ row }">
            <el-switch v-model="row.enabled" :disabled="!canEdit" />
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="section-card">
      <template #header>
        <span class="card-title">{{ t('admin.automation.eventSection') }}</span>
      </template>
      <div class="field-tip">{{ t('admin.automation.eventTip') }}</div>
      <div v-for="ev in events" :key="ev.event" class="event-group">
        <div class="event-head">
          <span class="event-name">{{ eventLabel(ev) }}</span>
          <span class="flow-code">{{ ev.event }}</span>
        </div>
        <div class="event-desc">{{ ev.description }}</div>
        <el-table v-if="ev.switches && ev.switches.length" :data="ev.switches" size="small">
          <el-table-column :label="t('admin.automation.handler')" min-width="180">
            <template #default="{ row }">
              <div>{{ row.name }}</div>
              <div class="flow-code">{{ row.key }}</div>
            </template>
          </el-table-column>
          <el-table-column :label="t('admin.automation.critical')" width="110" align="center">
            <template #default="{ row }">
              <el-tag :type="row.critical ? 'warning' : 'info'" size="small" disable-transitions>
                {{ row.critical ? t('admin.automation.critical') : t('admin.automation.nonCritical') }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="t('common.form.enabled')" width="90" align="center">
            <template #default="{ row }">
              <el-switch v-model="row.enabled" :disabled="!canEdit" />
            </template>
          </el-table-column>
        </el-table>
        <div v-else class="field-tip">{{ t('admin.automation.noSwitches') }}</div>
      </div>
    </el-card>

    <div class="save-bar">
      <el-button v-permission="'admin:automation:edit'" type="primary" :loading="saving" @click="save">
        {{ t('admin.automation.save') }}
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.intro-alert {
  margin-bottom: var(--bs-space-3);
}

.card-title {
  font-weight: 600;
}

.section-card {
  margin-bottom: var(--bs-space-3);
}

.field-tip {
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs, 12px);
  line-height: 1.6;
  margin-bottom: var(--bs-space-2);
}

.flow-name {
  font-weight: 600;
}

.flow-code {
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs, 12px);
  line-height: 1.5;
  word-break: break-all;
}

.status-line {
  display: flex;
  align-items: center;
  gap: var(--bs-space-1);
}

.event-group {
  margin-bottom: var(--bs-space-4);
}

.event-head {
  display: flex;
  align-items: baseline;
  gap: var(--bs-space-2);
}

.event-name {
  font-weight: 600;
}

.event-desc {
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs, 12px);
  line-height: 1.6;
  margin-bottom: var(--bs-space-2);
}

.save-bar {
  display: flex;
  justify-content: flex-end;
}
</style>
