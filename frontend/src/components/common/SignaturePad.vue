<script setup lang="ts">
/**
 * 手写签名板（canvas）：鼠标 / 触摸 / 手写笔通用（Pointer Events）。
 * 输出为 PNG dataURL base64，交给后端存证（访客 NDA、门户签署等）。
 */
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { resolveToken } from '@/utils/chartTheme'

const props = withDefaults(
  defineProps<{
    /** PNG dataURL base64 */
    modelValue?: string
    height?: number
    placeholder?: string
  }>(),
  { modelValue: '', height: 180, placeholder: '' },
)

const emit = defineEmits<{
  (e: 'update:modelValue', v: string): void
}>()

const { t } = useI18n()

const canvasRef = ref<HTMLCanvasElement>()
const drawing = ref(false)
const hasInk = ref(false)
let ctx: CanvasRenderingContext2D | null = null
let observer: ResizeObserver | null = null

function pos(e: PointerEvent) {
  const rect = canvasRef.value?.getBoundingClientRect()
  return { x: e.clientX - (rect?.left ?? 0), y: e.clientY - (rect?.top ?? 0) }
}

function drawImage(dataUrl: string) {
  const canvas = canvasRef.value
  if (!canvas || !ctx) return
  const img = new Image()
  img.onload = () => {
    const rect = canvas.getBoundingClientRect()
    const scale = Math.min(rect.width / img.width, (props.height - 8) / img.height, 1)
    const w = img.width * scale
    const h = img.height * scale
    ctx?.drawImage(img, (rect.width - w) / 2, (props.height - h) / 2, w, h)
    hasInk.value = true
  }
  img.src = dataUrl
}

function setupCanvas() {
  const canvas = canvasRef.value
  if (!canvas) return
  const dpr = window.devicePixelRatio || 1
  const rect = canvas.getBoundingClientRect()
  const w = Math.max(rect.width, 200)
  canvas.width = w * dpr
  canvas.height = props.height * dpr
  ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.scale(dpr, dpr)
  ctx.lineWidth = 2.2
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'
  ctx.strokeStyle = resolveToken('--bs-color-fg-default', '#1f2937')
  if (props.modelValue) drawImage(props.modelValue)
}

function onPointerDown(e: PointerEvent) {
  const canvas = canvasRef.value
  if (!canvas || !ctx) return
  e.preventDefault()
  canvas.setPointerCapture(e.pointerId)
  drawing.value = true
  const p = pos(e)
  ctx.beginPath()
  ctx.moveTo(p.x, p.y)
  ctx.stroke()
}

function onPointerMove(e: PointerEvent) {
  if (!drawing.value || !ctx) return
  e.preventDefault()
  const p = pos(e)
  ctx.lineTo(p.x, p.y)
  ctx.stroke()
  hasInk.value = true
}

function onPointerUp() {
  if (!drawing.value) return
  drawing.value = false
  emitValue()
}

function emitValue() {
  const canvas = canvasRef.value
  if (!canvas) return
  emit('update:modelValue', hasInk.value ? canvas.toDataURL('image/png') : '')
}

function clear() {
  const canvas = canvasRef.value
  if (!canvas || !ctx) return
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  hasInk.value = false
  emit('update:modelValue', '')
}

onMounted(() => {
  setupCanvas()
  const canvas = canvasRef.value
  if (canvas && typeof ResizeObserver !== 'undefined') {
    observer = new ResizeObserver(() => {
      const current = hasInk.value ? canvas.toDataURL('image/png') : ''
      setupCanvas()
      if (current) drawImage(current)
    })
    observer.observe(canvas)
  }
})

watch(
  () => props.modelValue,
  (v) => {
    if (v && v !== (canvasRef.value?.toDataURL('image/png') ?? '')) drawImage(v)
  },
)

onBeforeUnmount(() => {
  observer?.disconnect()
  observer = null
})
</script>

<template>
  <div class="signature-pad">
    <div class="signature-canvas-wrap">
      <canvas
        ref="canvasRef"
        class="signature-canvas"
        :style="{ height: `${props.height}px` }"
        @pointerdown="onPointerDown"
        @pointermove="onPointerMove"
        @pointerup="onPointerUp"
        @pointerleave="onPointerUp"
        @pointercancel="onPointerUp"
      />
      <div v-if="!hasInk" class="signature-placeholder">
        {{ props.placeholder || t('common.signature.hint') }}
      </div>
    </div>
    <div class="signature-actions">
      <el-button size="small" @click="clear">{{ t('common.signature.clear') }}</el-button>
    </div>
  </div>
</template>

<style scoped>
.signature-pad {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
  width: 100%;
}

.signature-canvas-wrap {
  position: relative;
  width: 100%;
  border: 1px dashed var(--bs-color-border-default);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-bg-surface);
  overflow: hidden;
}

.signature-canvas {
  display: block;
  width: 100%;
  /* 绘制时禁止页面滚动（否则手指会带动页面） */
  touch-action: none;
}

.signature-placeholder {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-sm);
}

.signature-actions {
  display: flex;
  justify-content: flex-end;
}
</style>
