<script setup lang="ts">
/** 流程图只读渲染：实例详情内嵌，highlightSeqs 高亮当前节点。 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import LogicFlow from '@logicflow/core'
import '@logicflow/core/es/style/index.css'
import { highlightSeqs, registerFlowNodes, resolveToken } from './flowNodes'
import { watchChartTheme } from '@/utils/chartTheme'
import { useIsMobile } from '@/composables/useIsMobile'
import type { FlowGraphData } from '@/api/types'

const props = defineProps<{
  graph: FlowGraphData | null
  currentSeqs?: number[]
  height?: string
}>()

const { t } = useI18n()
const { isMobile } = useIsMobile()

const container = ref<HTMLElement>()
let lf: LogicFlow | null = null

/** 窄屏默认折叠画布：LogicFlow 画布在小屏不可用（需横向拖拽），改为点击展开 */
const expanded = ref(false)
const showCanvas = computed(() => !isMobile.value || expanded.value)

function render() {
  if (!lf || !props.graph?.nodes?.length) return
  highlightSeqs.clear()
  for (const s of props.currentSeqs ?? []) highlightSeqs.add(Number(s))
  lf.render(props.graph)
  lf.fitView(40, 40)
}

function init() {
  if (!container.value) return
  lf = new LogicFlow({
    container: container.value,
    isSilentMode: true,
    grid: false,
    edgeType: 'polyline',
    style: {
      polyline: { stroke: resolveToken('--bs-color-fg-muted', '#8a94a3'), strokeWidth: 1.5 },
      edgeText: { color: resolveToken('--bs-color-fg-secondary', '#5a6472'), fontSize: 11, textWidth: 120 },
    } as never,
  })
  registerFlowNodes(lf as never)
  render()
}

function destroy() {
  lf?.destroy()
  lf = null
}

onMounted(() => init())

// 主题/明暗/accent 切换：边/节点色取字面值，销毁重建以重算样式
watchChartTheme(() => {
  destroy()
  init()
})

// 窄屏展开后才创建画布（隐藏容器尺寸为 0，fitView 会失效）
watch(showCanvas, (visible) => {
  if (visible && !lf) init()
  if (!visible) destroy()
})

watch(
  () => [props.graph, props.currentSeqs],
  () => render(),
  { deep: true },
)

onBeforeUnmount(() => {
  destroy()
})
</script>

<template>
  <div class="flow-graph-viewer">
    <button
      v-if="isMobile && !expanded"
      type="button"
      class="flow-expand-btn"
      @click="expanded = true"
    >
      <span class="flow-expand-label">{{ t('common.action.expand') }}</span>
      <span class="flow-expand-hint">{{ t('approval.approval.flowGraphMobileHint') }}</span>
    </button>
    <div
      v-show="showCanvas"
      ref="container"
      class="flow-graph-canvas"
      :style="{ height: props.height ?? '320px' }"
    />
  </div>
</template>

<style scoped>
.flow-graph-viewer {
  width: 100%;
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-lg);
  background: var(--bs-color-fill-lighter);
  overflow: hidden;
}

.flow-graph-canvas {
  width: 100%;
}

.flow-expand-btn {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--bs-space-1);
  width: 100%;
  padding: var(--bs-space-3);
  border: none;
  background: transparent;
  text-align: left;
  cursor: pointer;
  min-height: 44px;
}

.flow-expand-label {
  font-size: var(--bs-typography-font-size-sm);
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.flow-expand-hint {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}
</style>
