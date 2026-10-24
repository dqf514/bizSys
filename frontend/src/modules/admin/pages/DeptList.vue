<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, type FormInstance } from 'element-plus'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import ExportButton from '@/components/list/ExportButton.vue'
import {
  listDepts,
  createDept,
  updateDept,
  listDeptMembers,
  setDeptMembers,
  listUsers,
  exportDepts,
  type DeptMember,
} from '@/api/admin'
import type { AdminUser, Dept } from '@/api/types'

defineOptions({ name: 'DeptList' })

const { t } = useI18n()

const treeData = ref<Dept[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const data = await listDepts()
    treeData.value = Array.isArray(data) ? data : (data.items ?? [])
  } catch {
    treeData.value = []
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
const form = reactive({ parentId: null as number | null, name: '', code: '', sort: 0 })

function openCreate(parent?: Dept) {
  editingId.value = null
  dialogTitle.value = t('admin.dept.create')
  Object.assign(form, { parentId: parent?.id ?? null, name: '', code: '', sort: 0 })
  dialogVisible.value = true
}

function openEdit(row: Dept) {
  editingId.value = row.id
  dialogTitle.value = t('admin.dept.edit')
  Object.assign(form, { parentId: row.parentId, name: row.name, code: row.code, sort: row.sort ?? 0 })
  dialogVisible.value = true
}

async function save() {
  if (!formRef.value) return
  const ok = await formRef.value.validate().catch(() => false)
  if (!ok) return
  saving.value = true
  try {
    if (editingId.value) await updateDept(editingId.value, { ...form })
    else await createDept({ ...form })
    ElMessage.success(t('common.message.saveSuccess'))
    dialogVisible.value = false
    void load()
  } catch {
    /* http notifies */
  } finally {
    saving.value = false
  }
}

/* ---------- 成员与负责人 ---------- */
interface MemberRow {
  userId: number | null
  isLeader: boolean
  isPrimary: boolean
}

const membersVisible = ref(false)
const membersDept = ref<Dept | null>(null)
const members = ref<MemberRow[]>([])
const membersSaving = ref(false)
const allUsers = ref<AdminUser[]>([])

async function openMembers(row: Dept) {
  membersDept.value = row
  membersVisible.value = true
  members.value = []
  try {
    const [ms, us] = await Promise.all([
      listDeptMembers(row.id),
      allUsers.value.length ? Promise.resolve({ items: allUsers.value }) : listUsers({ page: 1, size: 200 }),
    ])
    allUsers.value = us.items
    members.value = ms.map((m: DeptMember) => ({
      userId: m.userId,
      isLeader: Boolean(m.isLeader),
      isPrimary: Boolean(m.isPrimary),
    }))
  } catch {
    /* http notifies */
  }
}

function addMemberRow() {
  members.value.push({ userId: null, isLeader: false, isPrimary: false })
}

function removeMemberRow(idx: number) {
  members.value.splice(idx, 1)
}

async function saveMembers() {
  if (!membersDept.value) return
  const rows = members.value.filter((m) => m.userId)
  membersSaving.value = true
  try {
    await setDeptMembers(
      membersDept.value.id,
      rows.map((m) => ({ userId: m.userId!, isPrimary: m.isPrimary ? 1 : 0, isLeader: m.isLeader ? 1 : 0 })),
    )
    ElMessage.success(t('admin.dept.membersSaved'))
    membersVisible.value = false
  } catch {
    /* http notifies */
  } finally {
    membersSaving.value = false
  }
}

const DEPT_PERM = 'admin:dept:edit'

const deptActions: ActionItem[] = [
  { key: 'add', tip: 'common.action.create', perm: DEPT_PERM },
  { key: 'edit', tip: 'common.action.edit', perm: DEPT_PERM },
  { key: 'members', tip: 'admin.dept.members', icon: 'User', perm: DEPT_PERM },
]

function onDeptAction(key: string, row: Dept) {
  if (key === 'add') openCreate(row)
  else if (key === 'edit') openEdit(row)
  else if (key === 'members') void openMembers(row)
}

const memberRowActions: ActionItem[] = [{ key: 'remove', tip: 'common.action.delete' }]
</script>

<template>
  <ListPage :title="t('admin.dept.title')" :loading="loading">
    <template #actions>
      <el-button v-permission="'admin:dept:edit'" type="primary" @click="openCreate()">
        {{ t('admin.dept.create') }}
      </el-button>
      <ExportButton v-permission="'admin:dept:list'" :export-fn="() => exportDepts()" />
      <el-button @click="load()">{{ t('common.action.refresh') }}</el-button>
    </template>

    <template #table>
      <el-table :data="treeData" row-key="id" border stripe default-expand-all height="100%">
        <el-table-column :label="t('admin.dept.name')" min-width="180">
          <template #default="{ row }">{{ row.name }}</template>
        </el-table-column>
        <el-table-column :label="t('admin.dept.code')" prop="code" min-width="120" />
        <el-table-column :label="t('admin.dept.sort')" prop="sort" width="80" />
        <el-table-column :label="t('common.action.operate')" width="130" fixed="right" align="center" header-align="center">
          <template #default="{ row }">
            <ActionBar :actions="deptActions" @select="(key: string) => onDeptAction(key, row as Dept)" />
          </template>
        </el-table-column>
      </el-table>
    </template>
  </ListPage>

  <el-dialog v-model="dialogVisible" :title="dialogTitle" width="480px" append-to-body>
    <el-form ref="formRef" :model="form" label-width="110px">
      <el-form-item :label="t('admin.dept.name')" prop="name" :rules="[{ required: true, message: t('common.form.required') }]">
        <el-input v-model="form.name" />
      </el-form-item>
      <el-form-item :label="t('admin.dept.code')" prop="code" :rules="[{ required: true, message: t('common.form.required') }]">
        <el-input v-model="form.code" />
      </el-form-item>
      <el-form-item :label="t('admin.dept.parent')">
        <el-tree-select
          v-model="form.parentId"
          :data="treeData"
          :props="{ label: 'name', value: 'id', children: 'children' }"
          check-strictly
          clearable
          style="width: 100%"
        />
      </el-form-item>
      <el-form-item :label="t('admin.dept.sort')">
        <el-input-number v-model="form.sort" :min="0" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="saving" @click="save">{{ t('common.action.save') }}</el-button>
    </template>
  </el-dialog>

  <el-dialog
    v-model="membersVisible"
    :title="`${t('admin.dept.membersTitle')} - ${membersDept?.name ?? ''}`"
    width="640px"
    append-to-body
  >
    <el-alert type="info" :closable="false" :title="t('admin.dept.leaderHint')" class="members-hint" />
    <el-table :data="members" border>
      <el-table-column :label="t('admin.dept.memberUser')" min-width="200">
        <template #default="{ row }">
          <el-select v-model="row.userId" filterable style="width: 100%">
            <el-option
              v-for="u in allUsers"
              :key="u.id"
              :value="u.id"
              :label="`${u.name || u.username} (${u.username})`"
              :disabled="members.some((m) => m !== row && m.userId === u.id)"
            />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column :label="t('admin.dept.memberIsLeader')" width="90" align="center">
        <template #default="{ row }">
          <el-switch v-model="row.isLeader" />
        </template>
      </el-table-column>
      <el-table-column :label="t('admin.dept.memberIsPrimary')" width="90" align="center">
        <template #default="{ row }">
          <el-switch v-model="row.isPrimary" />
        </template>
      </el-table-column>
      <el-table-column :label="t('common.action.operate')" width="70" align="center">
        <template #default="{ $index }">
          <ActionBar :actions="memberRowActions" @select="removeMemberRow($index)" />
        </template>
      </el-table-column>
    </el-table>
    <el-button class="members-add" plain type="primary" size="small" @click="addMemberRow">
      {{ t('admin.dept.addMember') }}
    </el-button>
    <template #footer>
      <el-button @click="membersVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="membersSaving" @click="saveMembers">{{ t('common.action.save') }}</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.members-hint {
  margin-bottom: var(--bs-space-2);
}

.members-add {
  margin-top: var(--bs-space-2);
}
</style>
