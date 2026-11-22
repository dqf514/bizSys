import { ref } from 'vue'
import { getFlowCapabilities, type FlowCapability } from '@/api/approval'

/**
 * 流程能力清单（F5）。
 *
 * 单据页据此决定展示「提交审批」还是「人工直通」：
 * - `flowEnabled('report_seal') === false` → 报告可直接签章，无需用章申请；
 * - `flowEnabled('project') === true`      → 项目必须提交立项审批。
 *
 * 全站共享一份请求结果（模块级缓存），切换页面不重复拉取。
 */
const caps = ref<Record<string, FlowCapability>>({})
const loaded = ref(false)
let pending: Promise<void> | null = null

export function useFlowCapability() {
  /** 首次调用拉取清单，之后命中缓存 */
  async function load() {
    if (loaded.value) return
    if (!pending) {
      pending = getFlowCapabilities()
        .then((data) => {
          for (const item of data.items ?? []) caps.value[item.bizType] = item
          loaded.value = true
        })
        .catch(() => {
          /* http 层已提示；保持默认（流程启用）由后端兜底拦截 */
        })
        .finally(() => {
          pending = null
        })
    }
    await pending
  }

  /** 流程是否启用。未加载时按启用处理：宁可多显示提交入口，后端会拦截 */
  function flowEnabled(bizType: string) {
    return caps.value[bizType]?.enabled ?? true
  }

  /** 允许提交审批的前置状态 */
  function submitFrom(bizType: string): string[] {
    return caps.value[bizType]?.submitFrom ?? []
  }

  /** 单据当前状态是否允许提交审批 */
  function canSubmit(bizType: string, status: string) {
    const from = submitFrom(bizType)
    if (!from.length) return false
    return from.includes(status)
  }

  // 首次使用即拉取（模块级缓存 + 单飞，重复调用不会重复请求）
  void load()

  return { caps, loaded, load, flowEnabled, submitFrom, canSubmit }
}
