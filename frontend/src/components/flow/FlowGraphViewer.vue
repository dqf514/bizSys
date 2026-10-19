<script setup lang="ts">
/** 流程图只读渲染：实例详情内嵌，highlightSeqs 高亮当前节点。 */
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import LogicFlow from '@logicflow/core'
import '@logicflow/core/es/style/index.css'
import { highlightSeqs, registerFlowNodes, resolveToken } from './flowNodes'
import type { FlowGraphData } from '@/api/types'

const props = defineProps<{
  graph: FlowGraphData | null
  currentSeqs?: number[]
  height?: string
}>()

const container = ref<HTMLElement>()
let lf: LogicFlow | null = null

function render() {
  if (!lf || !props.graph?.nodes?.length) return
  highlightSeqs.clear()
  for (const s of props.currentSeqs ?? []) highlightSeqs.add(Number(s))
  lf.render(props.graph)
  lf.fitView(40, 40)
}

onMounted(() => {
  lf = new LogicFlow({
    container: container.value!,
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
})

watch(
  () => [props.graph, props.currentSeqs],
  () => render(),
  { deep: true },
)

onBeforeUnmount(() => {
  lf?.destroy()
  lf = null
})
</script>

<template>
  <div
    ref="container"
    class="flow-graph-viewer"
    :style="{ height: props.height ?? '320px' }"
  />
</template>

<style scoped>
.flow-graph-viewer {
  width: 100%;
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-lg);
  background: var(--bs-color-fill-lighter);
  overflow: hidden;
}
</style>
