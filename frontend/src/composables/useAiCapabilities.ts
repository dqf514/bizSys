/** AI 能力探测（/ai/capabilities）：模块级缓存，各 AI 入口据此决定显隐/提示。 */
import { ref } from 'vue'
import { getAiCapabilities } from '@/api/ai'
import type { AiCapabilities, AiFeatureKey } from '@/api/types'

const EMPTY: AiCapabilities = {
  enabled: false,
  visionModel: '',
  features: {
    quote: false,
    contract_ocr: false,
    task_photo: false,
    report_summary: false,
    approval_assist: false,
    contract_risk: false,
    report_assist: false,
    nl_query: false,
    hr_prefill: false,
    oa_prefill: false,
    flow_route: false,
    flow_anomaly: false,
    tender_assist: false,
    sample_ocr: false,
    invoice_ocr: false,
    price_ref: false,
    assistant: false,
    daily_digest: false,
    knowledge: false,
  },
}

const caps = ref<AiCapabilities>({ ...EMPTY, features: { ...EMPTY.features } })
const loaded = ref(false)
let pending: Promise<void> | null = null

export function useAiCapabilities() {
  async function refresh() {
    try {
      caps.value = await getAiCapabilities()
    } catch {
      caps.value = { ...EMPTY, features: { ...EMPTY.features } }
    } finally {
      loaded.value = true
    }
  }

  function ensureLoaded() {
    if (loaded.value || pending) return pending ?? Promise.resolve()
    pending = refresh().finally(() => {
      pending = null
    })
    return pending
  }

  /** 某功能是否可用（全局启用 + 功能未停用） */
  function featureOn(feature: AiFeatureKey): boolean {
    return Boolean(caps.value.enabled && caps.value.features[feature])
  }

  return { caps, loaded, ensureLoaded, refresh, featureOn }
}
