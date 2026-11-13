/**
 * Element Plus 按需引入（UI-B 包体瘦身）：替代 app.use(ElementPlus) 全量注册与 dist/index.css 全量样式。
 * 组件清单 = 全站模板扫描并集（scripts 无扫描器，新增 el-* 组件时手工同步两处）：
 * 1) components 数组里加组件（模板 kebab-case 标签依赖全局注册；<ElXxx> 显式 import 不受影响）；
 * 2) 下方补一行 `element-plus/es/components/<kebab>/style/css`（内部依赖样式由 EP 自动携带）。
 * ElMessage / ElMessageBox 经函数调用使用，仅引入样式；v-loading 注册为指令。
 */
import type { App, Component } from 'vue'
import {
  ElAlert,
  ElAutocomplete,
  ElBadge,
  ElBreadcrumb,
  ElBreadcrumbItem,
  ElButton,
  ElCard,
  ElCheckbox,
  ElCheckboxGroup,
  ElCol,
  ElCollapse,
  ElCollapseItem,
  ElConfigProvider,
  ElDatePicker,
  ElDescriptions,
  ElDescriptionsItem,
  ElDialog,
  ElDivider,
  ElDrawer,
  ElDropdown,
  ElDropdownItem,
  ElDropdownMenu,
  ElEmpty,
  ElForm,
  ElFormItem,
  ElIcon,
  ElInput,
  ElInputNumber,
  ElLink,
  ElLoading,
  ElMenu,
  ElMenuItem,
  ElOption,
  ElPagination,
  ElPopconfirm,
  ElPopover,
  ElRadio,
  ElRadioButton,
  ElRadioGroup,
  ElRow,
  ElSegmented,
  ElSelect,
  ElSubMenu,
  ElSwitch,
  ElTabPane,
  ElTable,
  ElTableColumn,
  ElTabs,
  ElTag,
  ElTimeline,
  ElTimelineItem,
  ElTooltip,
  ElTree,
  ElTreeSelect,
  ElUpload,
} from 'element-plus'

import 'element-plus/es/components/alert/style/css'
import 'element-plus/es/components/autocomplete/style/css'
import 'element-plus/es/components/badge/style/css'
import 'element-plus/es/components/breadcrumb/style/css'
import 'element-plus/es/components/breadcrumb-item/style/css'
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/card/style/css'
import 'element-plus/es/components/checkbox/style/css'
import 'element-plus/es/components/checkbox-group/style/css'
import 'element-plus/es/components/col/style/css'
import 'element-plus/es/components/collapse/style/css'
import 'element-plus/es/components/collapse-item/style/css'
import 'element-plus/es/components/config-provider/style/css'
import 'element-plus/es/components/date-picker/style/css'
import 'element-plus/es/components/descriptions/style/css'
import 'element-plus/es/components/descriptions-item/style/css'
import 'element-plus/es/components/dialog/style/css'
import 'element-plus/es/components/divider/style/css'
import 'element-plus/es/components/drawer/style/css'
import 'element-plus/es/components/dropdown/style/css'
import 'element-plus/es/components/dropdown-item/style/css'
import 'element-plus/es/components/dropdown-menu/style/css'
import 'element-plus/es/components/empty/style/css'
import 'element-plus/es/components/form/style/css'
import 'element-plus/es/components/form-item/style/css'
import 'element-plus/es/components/icon/style/css'
import 'element-plus/es/components/input/style/css'
import 'element-plus/es/components/input-number/style/css'
import 'element-plus/es/components/link/style/css'
import 'element-plus/es/components/menu/style/css'
import 'element-plus/es/components/menu-item/style/css'
import 'element-plus/es/components/option/style/css'
import 'element-plus/es/components/pagination/style/css'
import 'element-plus/es/components/popconfirm/style/css'
import 'element-plus/es/components/popover/style/css'
import 'element-plus/es/components/radio/style/css'
import 'element-plus/es/components/radio-button/style/css'
import 'element-plus/es/components/radio-group/style/css'
import 'element-plus/es/components/row/style/css'
import 'element-plus/es/components/segmented/style/css'
import 'element-plus/es/components/select/style/css'
import 'element-plus/es/components/sub-menu/style/css'
import 'element-plus/es/components/switch/style/css'
import 'element-plus/es/components/tab-pane/style/css'
import 'element-plus/es/components/table/style/css'
import 'element-plus/es/components/table-column/style/css'
import 'element-plus/es/components/tabs/style/css'
import 'element-plus/es/components/tag/style/css'
import 'element-plus/es/components/timeline/style/css'
import 'element-plus/es/components/timeline-item/style/css'
import 'element-plus/es/components/tooltip/style/css'
import 'element-plus/es/components/tree/style/css'
import 'element-plus/es/components/tree-select/style/css'
import 'element-plus/es/components/upload/style/css'
// 函数式服务与指令样式
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'
import 'element-plus/es/components/loading/style/css'

const components: Component[] = [
  ElAlert,
  ElAutocomplete,
  ElBadge,
  ElBreadcrumb,
  ElBreadcrumbItem,
  ElButton,
  ElCard,
  ElCheckbox,
  ElCheckboxGroup,
  ElCol,
  ElCollapse,
  ElCollapseItem,
  ElConfigProvider,
  ElDatePicker,
  ElDescriptions,
  ElDescriptionsItem,
  ElDialog,
  ElDivider,
  ElDrawer,
  ElDropdown,
  ElDropdownItem,
  ElDropdownMenu,
  ElEmpty,
  ElForm,
  ElFormItem,
  ElIcon,
  ElInput,
  ElInputNumber,
  ElLink,
  ElMenu,
  ElMenuItem,
  ElOption,
  ElPagination,
  ElPopconfirm,
  ElPopover,
  ElRadio,
  ElRadioButton,
  ElRadioGroup,
  ElRow,
  ElSegmented,
  ElSelect,
  ElSubMenu,
  ElSwitch,
  ElTabPane,
  ElTable,
  ElTableColumn,
  ElTabs,
  ElTag,
  ElTimeline,
  ElTimelineItem,
  ElTooltip,
  ElTree,
  ElTreeSelect,
  ElUpload,
]

export function setupElementPlus(app: App) {
  for (const comp of components) app.component((comp as { name: string }).name, comp)
  app.use(ElLoading) // registers the v-loading directive
}
