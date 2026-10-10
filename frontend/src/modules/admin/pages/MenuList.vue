<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import ListPage from '@/components/list/ListPage.vue'
import MenuNavPreview from '@/modules/admin/components/MenuNavPreview.vue'
import { menuTree, createMenu, updateMenu, deleteMenu } from '@/api/admin'
import { useAuthStore } from '@/stores/auth'
import type { MenuNode } from '@/api/types'

defineOptions({ name: 'MenuList' })

const { t, te } = useI18n()
const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const treeData = ref<MenuNode[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    treeData.value = await menuTree(true)
  } catch {
    treeData.value = []
  } finally {
    loading.value = false
  }
}

/** re-pull session menus + re-register dynamic routes; bail to workbench if current route vanished */
async function refreshNav() {
  await auth.refreshMenus()
  const resolved = router.resolve(route.fullPath)
  if (resolved.name === 'NotFound') router.replace('/workbench')
}

onMounted(() => void load())

/** localized display title (name is an English identifier, titleKey drives the real label) */
function displayTitle(row: MenuNode) {
  return row.titleKey && te(row.titleKey) ? t(row.titleKey) : row.name
}

// ---- nav preview + staged sibling ordering ----
/** parentKey → ordered child ids; 'root' for top level. Only sibling groups touched by drag are staged. */
const staged = ref<Record<string, number[]>>({})
const orderSaving = ref(false)
const orderDirty = computed(() => Object.keys(staged.value).length > 0)

const byId = computed(() => {
  const map = new Map<number, MenuNode>()
  const walk = (nodes: MenuNode[]) => {
    for (const n of nodes) {
      map.set(n.id, n)
      if (n.children?.length) walk(n.children)
    }
  }
  walk(treeData.value)
  return map
})

/** dir/menu siblings of one group (buttons excluded from the preview), sorted by stored sort */
function groupNodes(parentKey: string): MenuNode[] {
  const list = parentKey === 'root' ? treeData.value : (byId.value.get(Number(parentKey))?.children ?? [])
  return list.filter((n) => n.menuType === 'dir' || n.menuType === 'menu')
}

function groupOrder(parentKey: string): number[] {
  return (
    staged.value[parentKey] ??
    [...groupNodes(parentKey)].sort((a, b) => (a.sort ?? 0) - (b.sort ?? 0)).map((n) => n.id)
  )
}

function buildPreview(nodes: MenuNode[], parentKey: string): MenuNode[] {
  const list = nodes.filter((n) => n.menuType === 'dir' || n.menuType === 'menu')
  let sorted: MenuNode[]
  const order = staged.value[parentKey]
  if (order) {
    const picked = order
      .map((id) => list.find((n) => n.id === id))
      .filter((n): n is MenuNode => Boolean(n))
    // nodes created after staging keep their stored order at the end
    const rest = list
      .filter((n) => !order.includes(n.id))
      .sort((a, b) => (a.sort ?? 0) - (b.sort ?? 0))
    sorted = [...picked, ...rest]
  } else {
    sorted = [...list].sort((a, b) => (a.sort ?? 0) - (b.sort ?? 0))
  }
  return sorted.map((n) => ({ ...n, children: buildPreview(n.children ?? [], String(n.id)) }))
}

const previewTree = computed(() => buildPreview(treeData.value, 'root'))

function onMove(parentKey: string, from: number, to: number) {
  const order = [...groupOrder(parentKey)]
  const [item] = order.splice(from, 1)
  if (item === undefined) return
  order.splice(to, 0, item)
  staged.value = { ...staged.value, [parentKey]: order }
}

async function saveOrder() {
  orderSaving.value = true
  try {
    const updates: Promise<unknown>[] = []
    for (const [key, order] of Object.entries(staged.value)) {
      const group = groupNodes(key)
      order.forEach((id, i) => {
        const node = group.find((n) => n.id === id)
        if (node && (node.sort ?? 0) !== i) {
          // 后端更新接口是全量 schema（name 必填），排序保存也要带上完整字段
          updates.push(
            updateMenu(id, {
              parentId: node.parentId,
              name: node.name,
              titleKey: node.titleKey,
              path: node.path,
              componentKey: node.componentKey,
              icon: node.icon,
              permission: node.permission,
              menuType: node.menuType,
              sort: i,
              visible: node.visible,
            }),
          )
        }
      })
    }
    await Promise.all(updates)
    ElMessage.success(t('common.message.saveSuccess'))
    staged.value = {}
    await load()
    await refreshNav()
  } catch {
    /* http notifies */
  } finally {
    orderSaving.value = false
  }
}

function resetOrder() {
  staged.value = {}
}

// ---- create / edit / delete ----
const dialogVisible = ref(false)
const dialogTitle = ref('')
const formRef = ref<FormInstance>()
const saving = ref(false)
const editingId = ref<number | null>(null)
const form = reactive({
  parentId: null as number | null,
  name: '',
  titleKey: '',
  path: '',
  componentKey: '',
  icon: '',
  permission: '',
  menuType: 'menu' as 'dir' | 'menu' | 'button',
  sort: 0,
  visible: 1,
})

function openCreate(parent?: MenuNode) {
  editingId.value = null
  dialogTitle.value = t('admin.menu.create')
  Object.assign(form, {
    parentId: parent?.id ?? null,
    name: '',
    titleKey: '',
    path: '',
    componentKey: '',
    icon: '',
    permission: '',
    menuType: 'menu',
    sort: 0,
    visible: 1,
  })
  dialogVisible.value = true
}

function openEdit(row: MenuNode) {
  editingId.value = row.id
  dialogTitle.value = t('admin.menu.edit')
  Object.assign(form, {
    parentId: row.parentId,
    name: row.name,
    titleKey: row.titleKey,
    path: row.path,
    componentKey: row.componentKey,
    icon: row.icon,
    permission: row.permission,
    menuType: row.menuType,
    sort: row.sort,
    visible: row.visible,
  })
  dialogVisible.value = true
}

async function save() {
  if (!formRef.value) return
  const ok = await formRef.value.validate().catch(() => false)
  if (!ok) return
  saving.value = true
  try {
    if (editingId.value) await updateMenu(editingId.value, { ...form })
    else await createMenu({ ...form })
    ElMessage.success(t('common.message.saveSuccess'))
    dialogVisible.value = false
    await load()
    await refreshNav()
  } catch {
    /* http notifies */
  } finally {
    saving.value = false
  }
}

async function remove(row: MenuNode) {
  try {
    await ElMessageBox.confirm(t('common.message.deleteConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteMenu(row.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    await load()
    await refreshNav()
  } catch {
    /* http notifies */
  }
}

function typeLabel(type: string) {
  if (type === 'dir') return t('admin.menu.typeDir')
  if (type === 'button') return t('admin.menu.typeButton')
  return t('admin.menu.typeMenu')
}
</script>

<template>
  <ListPage :title="t('admin.menu.title')" :loading="loading">
    <template #actions>
      <el-button v-permission="'admin:menu:create'" type="primary" @click="openCreate()">
        {{ t('admin.menu.create') }}
      </el-button>
      <el-button @click="load()">{{ t('common.action.refresh') }}</el-button>
    </template>

    <template #table>
      <div class="menu-editor">
        <div class="menu-table">
          <el-table :data="treeData" row-key="id" border stripe default-expand-all height="100%">
            <el-table-column :label="t('admin.menu.displayName')" min-width="200">
              <template #default="{ row }">
                <div class="menu-name">
                  <span class="menu-name-title">{{ displayTitle(row as MenuNode) }}</span>
                  <span class="menu-name-raw">{{ row.name }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column :label="t('admin.menu.titleKey')" prop="titleKey" min-width="140" />
            <el-table-column :label="t('admin.menu.path')" prop="path" min-width="140" />
            <el-table-column :label="t('admin.menu.componentKey')" prop="componentKey" min-width="160" />
            <el-table-column :label="t('admin.menu.permission')" prop="permission" min-width="140" />
            <el-table-column :label="t('admin.menu.menuType')" width="90">
              <template #default="{ row }">
                <el-tag size="small">{{ typeLabel(row.menuType) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="t('admin.menu.sort')" prop="sort" width="70" />
            <el-table-column :label="t('common.action.operate')" width="220" fixed="right">
              <template #default="{ row }">
                <el-button v-permission="'admin:menu:create'" link type="primary" @click="openCreate(row as MenuNode)">
                  {{ t('common.action.create') }}
                </el-button>
                <el-button v-permission="'admin:menu:edit'" link type="primary" @click="openEdit(row as MenuNode)">
                  {{ t('common.action.edit') }}
                </el-button>
                <el-button v-permission="'admin:menu:delete'" link type="danger" @click="remove(row as MenuNode)">
                  {{ t('common.action.delete') }}
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <aside class="menu-preview">
          <div class="menu-preview-header">
            <span class="menu-preview-title">{{ t('admin.menu.preview') }}</span>
            <div v-if="orderDirty" class="menu-preview-actions">
              <el-button size="small" :disabled="orderSaving" @click="resetOrder">
                {{ t('admin.menu.resetOrder') }}
              </el-button>
              <el-button size="small" type="primary" :loading="orderSaving" @click="saveOrder">
                {{ t('admin.menu.saveOrder') }}
              </el-button>
            </div>
          </div>
          <p class="menu-preview-hint">{{ t('admin.menu.dragHint') }}</p>
          <div class="menu-preview-body">
            <MenuNavPreview :nodes="previewTree" parent-key="root" @move="onMove" />
          </div>
        </aside>
      </div>
    </template>
  </ListPage>

  <el-dialog v-model="dialogVisible" :title="dialogTitle" width="560px" append-to-body>
    <el-form ref="formRef" :model="form" label-width="120px">
      <el-form-item :label="t('admin.menu.menuType')">
        <el-radio-group v-model="form.menuType">
          <el-radio value="dir">{{ t('admin.menu.typeDir') }}</el-radio>
          <el-radio value="menu">{{ t('admin.menu.typeMenu') }}</el-radio>
          <el-radio value="button">{{ t('admin.menu.typeButton') }}</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item :label="t('admin.menu.name')" prop="name" :rules="[{ required: true, message: t('common.form.required') }]">
        <el-input v-model="form.name" />
      </el-form-item>
      <el-form-item :label="t('admin.menu.titleKey')">
        <el-input v-model="form.titleKey" placeholder="menu.xxx" />
      </el-form-item>
      <el-form-item :label="t('admin.menu.path')">
        <el-input v-model="form.path" />
      </el-form-item>
      <el-form-item v-if="form.menuType === 'menu'" :label="t('admin.menu.componentKey')">
        <el-input v-model="form.componentKey" placeholder="crm/CustomerList" />
      </el-form-item>
      <el-form-item :label="t('admin.menu.icon')">
        <el-input v-model="form.icon" />
      </el-form-item>
      <el-form-item :label="t('admin.menu.permission')">
        <el-input v-model="form.permission" />
      </el-form-item>
      <el-form-item :label="t('admin.menu.sort')">
        <el-input-number v-model="form.sort" :min="0" />
      </el-form-item>
      <el-form-item :label="t('admin.menu.visible')">
        <el-switch v-model="form.visible" :active-value="1" :inactive-value="0" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="saving" @click="save">{{ t('common.action.save') }}</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.menu-editor {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: var(--bs-space-3);
}

.menu-table {
  flex: 1;
  min-width: 0;
  min-height: 0;
}

.menu-preview {
  flex: none;
  width: 320px;
  min-height: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-bg-surface);
  padding: var(--bs-space-2);
}

.menu-preview-header {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--bs-space-2);
}

.menu-preview-title {
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.menu-preview-actions {
  display: flex;
  align-items: center;
  gap: var(--bs-space-1);
}

.menu-preview-hint {
  flex: none;
  margin: var(--bs-space-1) 0 var(--bs-space-2);
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.menu-preview-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.menu-name {
  display: flex;
  flex-direction: column;
  line-height: 1.3;
}

.menu-name-raw {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}
</style>
