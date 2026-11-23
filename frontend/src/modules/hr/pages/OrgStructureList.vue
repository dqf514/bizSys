<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, type FormInstance } from 'element-plus'
import { useI18n } from 'vue-i18n'
import PageHeader from '@/components/common/PageHeader.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { createDept, listDepts, updateDept, userOptions } from '@/api/admin'
import { listOrgChanges, listPositions } from '@/api/hr'
import type { Dept, HrOrgChange, HrPosition } from '@/api/types'

defineOptions({ name: 'OrgStructureList' })

const { t } = useI18n()

const DEPT_TYPES = ['site', 'company', 'division', 'dept', 'lab', 'team']
const OBJECT_TYPES = ['dept', 'position', 'employee']
const CHANGE_TYPES = ['create', 'update', 'move', 'disable', 'enable']

const deptTypeOptions = computed(() =>
  DEPT_TYPES.map((v) => ({ label: t(`hr.org.deptTypeType.${v}`), value: v })),
)

function deptTypeLabel(v: unknown) {
  const key = String(v ?? '')
  return DEPT_TYPES.includes(key) ? t(`hr.org.deptTypeType.${key}`) : key || '-'
}

function objectTypeLabel(v: unknown) {
  const key = String(v ?? '')
  return OBJECT_TYPES.includes(key) ? t(`hr.org.objectTypeType.${key}`) : key || '-'
}

function changeTypeLabel(v: unknown) {
  const key = String(v ?? '')
  return CHANGE_TYPES.includes(key) ? t(`hr.org.changeTypeType.${key}`) : key || '-'
}

/* ---------------- 部门数据 ---------------- */

const depts = ref<Dept[]>([])
const loading = ref(false)
const selectedId = ref<number | null>(null)

const current = computed<Dept | null>(() => depts.value.find((d) => d.id === selectedId.value) ?? null)

/** 按 parentId 组装树；parentId 指向不存在节点时提升为根 */
const treeData = computed(() => {
  const map = new Map<number, Dept & { children: (Dept & { children: unknown[] })[] }>()
  for (const d of depts.value) map.set(d.id, { ...d, children: [] })
  const roots: unknown[] = []
  for (const d of depts.value) {
    const node = map.get(d.id)!
    const parent = d.parentId ? map.get(d.parentId) : undefined
    if (parent) parent.children.push(node)
    else roots.push(node)
  }
  return roots
})

async function loadDepts() {
  loading.value = true
  try {
    const res = await listDepts()
    const rows = Array.isArray(res) ? res : (res?.items ?? [])
    depts.value = rows as Dept[]
    if (selectedId.value && !depts.value.some((d) => d.id === selectedId.value)) {
      selectedId.value = null
    }
  } catch {
    depts.value = []
  } finally {
    loading.value = false
  }
}

function onNodeClick(node: Dept) {
  selectedId.value = node.id
  void loadPositions()
  void loadChanges()
}

/* ---------------- 岗位清单 ---------------- */

const positionLoading = ref(false)
const positions = ref<HrPosition[]>([])
const positionTotal = ref(0)
const positionPage = ref(1)
const positionSize = ref(10)

const positionColumns: ListColumn[] = [
  { prop: 'code', labelKey: 'hr.position.code', width: 140 },
  { prop: 'name', labelKey: 'hr.position.name', minWidth: 160 },
  { prop: 'positionTypeText', labelKey: 'hr.position.positionType', width: 110 },
  { prop: 'keyRoleText', labelKey: 'hr.position.keyRole', width: 130 },
  { prop: 'primaryUserName', labelKey: 'hr.position.primaryUser', width: 120 },
  { prop: 'backupUserName', labelKey: 'hr.position.backupUser', width: 120 },
  { prop: 'statusText', labelKey: 'hr.position.status', width: 90 },
]

async function loadPositions() {
  positionLoading.value = true
  try {
    const res = await listPositions({
      page: positionPage.value,
      size: positionSize.value,
      filters: selectedId.value ? { dept_id: selectedId.value } : {},
    })
    positions.value = res?.items ?? []
    positionTotal.value = res?.total ?? 0
  } catch {
    positions.value = []
    positionTotal.value = 0
  } finally {
    positionLoading.value = false
  }
}

/* ---------------- 变更轨迹 ---------------- */

const changeLoading = ref(false)
const changes = ref<HrOrgChange[]>([])

async function loadChanges() {
  changeLoading.value = true
  try {
    const res = await listOrgChanges({
      page: 1,
      size: 30,
      filters: selectedId.value
        ? { object_type: 'dept', object_id: selectedId.value }
        : {},
    })
    changes.value = res?.items ?? []
  } catch {
    changes.value = []
  } finally {
    changeLoading.value = false
  }
}

/* ---------------- 部门表单 ---------------- */

const dialogVisible = ref(false)
const dialogTitle = ref('')
const formRef = ref<FormInstance>()
const saving = ref(false)
const editingId = ref<number | null>(null)

const userOptionsList = ref<{ value: number; label: string; sub?: string }[]>([])

async function loadUserOptions() {
  try {
    const users = (await userOptions()) ?? []
    userOptionsList.value = users.map((u) => ({ value: u.id, label: u.label, sub: u.sub }))
  } catch {
    userOptionsList.value = []
  }
}

const form = reactive({
  parentId: null as number | null,
  name: '',
  code: '',
  sort: 0,
  status: 'enabled',
  deptType: 'dept',
  siteCode: '',
  address: '',
  managerId: null as number | null,
  effectiveFrom: null as string | null,
  effectiveTo: null as string | null,
})

function resetForm() {
  Object.assign(form, {
    parentId: null,
    name: '',
    code: '',
    sort: 0,
    status: 'enabled',
    deptType: 'dept',
    siteCode: '',
    address: '',
    managerId: null,
    effectiveFrom: null,
    effectiveTo: null,
  })
}

function openDeptCreate() {
  editingId.value = null
  dialogTitle.value = t('hr.org.createDept')
  resetForm()
  form.parentId = selectedId.value
  dialogVisible.value = true
}

function openDeptEdit() {
  const d = current.value
  if (!d) return
  editingId.value = d.id
  dialogTitle.value = t('hr.org.editDept')
  Object.assign(form, {
    parentId: d.parentId ?? null,
    name: d.name || '',
    code: d.code || '',
    sort: d.sort ?? 0,
    status: d.status || 'enabled',
    deptType: d.deptType || 'dept',
    siteCode: d.siteCode || '',
    address: d.address || '',
    managerId: d.managerId ?? null,
    effectiveFrom: d.effectiveFrom || null,
    effectiveTo: d.effectiveTo || null,
  })
  dialogVisible.value = true
}

async function saveDept() {
  if (!formRef.value) return
  const ok = await formRef.value.validate().catch(() => false)
  if (!ok) return
  saving.value = true
  try {
    if (editingId.value) await updateDept(editingId.value, { ...form })
    else await createDept({ ...form })
    ElMessage.success(t('common.message.saveSuccess'))
    dialogVisible.value = false
    await loadDepts()
    if (editingId.value) selectedId.value = editingId.value
    await loadPositions()
    await loadChanges()
  } catch {
    /* http notifies */
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  void loadDepts()
  void loadUserOptions()
  void loadPositions()
  void loadChanges()
})
</script>

<template>
  <div class="bs-page bs-page--scroll org-page">
    <PageHeader :title="t('hr.org.title')">
      <template #actions>
        <el-button v-permission="'admin:dept:edit'" @click="openDeptCreate">
          {{ t('hr.org.createDept') }}
        </el-button>
        <el-button
          v-permission="'admin:dept:edit'"
          type="primary"
          :disabled="!current"
          @click="openDeptEdit"
        >
          {{ t('hr.org.editDept') }}
        </el-button>
      </template>
    </PageHeader>

    <div class="org-grid">
      <!-- 左：组织树 -->
      <section class="bs-page-card org-tree-card">
        <div class="card-head">
          <h3 class="card-title">{{ t('hr.org.tree') }}</h3>
          <span class="card-count">{{ depts.length }}</span>
        </div>
        <el-alert :title="t('hr.org.deptTip')" type="info" :closable="false" show-icon />
        <el-tree
          v-loading="loading"
          class="org-tree"
          :data="treeData"
          node-key="id"
          :props="{ label: 'name', children: 'children' }"
          :default-expanded-keys="depts.map((d) => d.id)"
          highlight-current
          @node-click="onNodeClick"
        >
          <template #default="{ data }">
            <span class="tree-node">
              <span class="tree-node-name">{{ data.name }}</span>
              <el-tag size="small" effect="plain" round>{{ data.deptTypeText || deptTypeLabel(data.deptType) }}</el-tag>
              <span v-if="data.positionCount" class="tree-node-count">{{ data.positionCount }}</span>
            </span>
          </template>
        </el-tree>
      </section>

      <!-- 右：部门详情 + 岗位清单 + 变更轨迹 -->
      <div class="org-main">
        <section class="bs-page-card">
          <template v-if="current">
            <div class="card-head">
              <h3 class="card-title">{{ current.name }}</h3>
              <StatusTag :status="current.status || 'enabled'" i18n-prefix="common.form" />
            </div>
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item :label="t('hr.org.deptCode')">{{ current.code || '-' }}</el-descriptions-item>
              <el-descriptions-item :label="t('hr.org.deptType')">
                {{ current.deptTypeText || deptTypeLabel(current.deptType) }}
              </el-descriptions-item>
              <el-descriptions-item :label="t('hr.org.siteCode')">
                {{ current.siteCode || '-' }}
              </el-descriptions-item>
              <el-descriptions-item :label="t('hr.org.manager')">
                {{ current.managerName || '-' }}
              </el-descriptions-item>
              <el-descriptions-item :label="t('hr.org.memberCount')">
                {{ current.memberCount ?? 0 }}
              </el-descriptions-item>
              <el-descriptions-item :label="t('hr.org.positionCount')">
                {{ current.positionCount ?? 0 }}
              </el-descriptions-item>
              <el-descriptions-item :label="t('hr.org.effectiveFrom')">
                {{ current.effectiveFrom || '-' }}
              </el-descriptions-item>
              <el-descriptions-item :label="t('hr.org.effectiveTo')">
                {{ current.effectiveTo || '-' }}
              </el-descriptions-item>
              <el-descriptions-item :label="t('hr.org.address')" :span="2">
                {{ current.address || '-' }}
              </el-descriptions-item>
            </el-descriptions>
          </template>
          <el-empty v-else :description="t('hr.org.noSelection')" :image-size="70" />
        </section>

        <section class="bs-page-card">
          <div class="card-head">
            <h3 class="card-title">{{ t('hr.org.positionsTitle') }}</h3>
          </div>
          <ListTable
            :columns="positionColumns"
            :data="positions as unknown as Record<string, unknown>[]"
            :loading="positionLoading"
            :total="positionTotal"
            :page="positionPage"
            :size="positionSize"
            row-key="id"
            @update:page="(v: number) => { positionPage = v; loadPositions() }"
            @update:size="(v: number) => { positionSize = v; positionPage = 1; loadPositions() }"
          >
            <template #positionTypeText="{ row }">
              {{ t(`hr.position.type.${row.positionType}`) }}
            </template>
            <template #keyRoleText="{ row }">
              {{ row.keyRole ? t(`hr.position.keyRoleType.${row.keyRole}`) : '-' }}
            </template>
            <template #statusText="{ row }">
              <StatusTag :status="String(row.status)" i18n-prefix="hr.position.statusType" />
            </template>
          </ListTable>
        </section>

        <section class="bs-page-card">
          <div class="card-head">
            <h3 class="card-title">
              {{ selectedId ? t('hr.org.changeTrail') : t('hr.org.allChanges') }}
            </h3>
          </div>
          <div v-loading="changeLoading" class="org-changes">
            <el-timeline v-if="changes.length">
              <el-timeline-item
                v-for="c in changes"
                :key="c.id"
                :timestamp="c.effectiveAt || c.createTime"
                placement="top"
              >
                <div class="change-head">
                  <el-tag size="small" effect="light" round>{{ objectTypeLabel(c.objectType) }}</el-tag>
                  <span class="change-title">{{ c.objectName || '-' }}</span>
                  <el-tag size="small" type="info" effect="plain" round>
                    {{ changeTypeLabel(c.changeType) }}
                  </el-tag>
                </div>
                <div class="change-meta">
                  {{ t('hr.org.operator') }}: {{ c.operatorName || '-' }}
                  <span v-if="c.reason"> · {{ c.reason }}</span>
                </div>
              </el-timeline-item>
            </el-timeline>
            <el-empty v-else :description="t('hr.org.changeTrailEmpty')" :image-size="60" />
          </div>
        </section>
      </div>
    </div>

    <!-- 部门表单 -->
    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="var(--bs-layout-dialog-lg)" append-to-body>
      <el-form ref="formRef" :model="form" label-width="110px" class="org-form">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item :label="t('hr.org.parentDept')">
              <el-select v-model="form.parentId" clearable filterable style="width: 100%">
                <el-option
                  v-for="d in depts.filter((x) => x.id !== editingId)"
                  :key="d.id"
                  :label="d.name"
                  :value="d.id"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item
              :label="t('hr.org.deptName')"
              prop="name"
              :rules="[{ required: true, message: t('common.form.required') }]"
            >
              <el-input v-model="form.name" :maxlength="64" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('hr.org.deptCode')">
              <el-input v-model="form.code" :maxlength="64" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('hr.org.deptType')">
              <el-select v-model="form.deptType" style="width: 100%">
                <el-option
                  v-for="o in deptTypeOptions"
                  :key="o.value"
                  :label="o.label"
                  :value="o.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('hr.org.siteCode')">
              <el-input v-model="form.siteCode" :maxlength="32" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('hr.org.manager')">
              <el-select v-model="form.managerId" clearable filterable style="width: 100%">
                <el-option
                  v-for="o in userOptionsList"
                  :key="o.value"
                  :label="o.label"
                  :value="o.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('common.form.sort')">
              <el-input-number v-model="form.sort" :min="0" :max="9999" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('common.form.status')">
              <el-select v-model="form.status" style="width: 100%">
                <el-option :label="t('common.form.enabled')" value="enabled" />
                <el-option :label="t('common.form.disabled')" value="disabled" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('hr.org.effectiveFrom')">
              <el-date-picker
                v-model="form.effectiveFrom"
                type="date"
                value-format="YYYY-MM-DD"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('hr.org.effectiveTo')">
              <el-date-picker
                v-model="form.effectiveTo"
                type="date"
                value-format="YYYY-MM-DD"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item :label="t('hr.org.address')">
          <el-input v-model="form.address" :maxlength="255" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ t('common.action.cancel') }}</el-button>
        <el-button type="primary" :loading="saving" @click="saveDept">
          {{ t('common.action.save') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.org-page {
  display: flex;
  flex-direction: column;
  gap: var(--bs-layout-section-gap);
}

.org-grid {
  display: grid;
  grid-template-columns: minmax(260px, 320px) minmax(0, 1fr);
  gap: var(--bs-layout-section-gap);
  align-items: start;
}

.org-main {
  display: flex;
  flex-direction: column;
  gap: var(--bs-layout-section-gap);
  min-width: 0;
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--bs-space-2);
  margin-bottom: var(--bs-space-2);
}

.card-title {
  margin: 0;
  font-size: var(--bs-typography-font-size-md);
  font-weight: 600;
}

.card-count {
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-sm);
}

.org-tree-card {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
}

.org-tree {
  max-height: 60vh;
  overflow: auto;
}

.tree-node {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  width: 100%;
}

.tree-node-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tree-node-count {
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs);
}

.org-changes {
  min-height: 80px;
}

.change-head {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
}

.change-title {
  font-weight: 600;
}

.change-meta {
  margin-top: var(--bs-space-1);
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-sm);
}

.org-form {
  margin-top: var(--bs-space-2);
}

@media (max-width: 767px) {
  .org-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .org-tree {
    max-height: 40vh;
  }
}
</style>
