<script setup lang="ts">
/** OA 流程统计（管理侧）：/oa/admin/stats，统计面板 + 各模板积压表。 */
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import StatsPanel from '@/modules/oa/components/StatsPanel.vue'
import { getOaAdminStats } from '@/api/oa'
import type { OaStats } from '@/api/types'

defineOptions({ name: 'AdminStats' })

const { t } = useI18n()
const stats = ref<OaStats | null>(null)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    stats.value = await getOaAdminStats()
  } catch {
    /* http notifies */
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <ListPage :title="t('oa.adminStats.title')" :loading="loading">
    <template #actions>
      <el-button @click="load">{{ t('common.action.refresh') }}</el-button>
    </template>
    <StatsPanel :stats="stats">
      <div v-if="stats?.backlog?.length" class="backlog-card">
        <div class="chart-title">{{ t('oa.adminStats.backlog') }}</div>
        <el-table :data="stats.backlog" border>
          <el-table-column prop="formName" :label="t('oa.my.formName')" min-width="160" sortable />
          <el-table-column prop="instances" :label="t('oa.adminStats.instances')" width="120" align="right" sortable />
          <el-table-column prop="pendingTasks" :label="t('oa.adminStats.pendingTasks')" width="120" align="right" sortable />
        </el-table>
      </div>
    </StatsPanel>
  </ListPage>
</template>

<style scoped>
.backlog-card {
  background: var(--bs-color-bg-surface);
  border-radius: var(--bs-radius-md);
  box-shadow: var(--bs-shadow-elevation1);
  padding: var(--bs-space-3);
}

.chart-title {
  font-weight: 600;
  color: var(--bs-color-fg-default);
  margin-bottom: var(--bs-space-2);
}
</style>
