<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'

defineOptions({ name: 'CountUp' })

const props = withDefaults(
  defineProps<{
    value: number
    /** animation length in ms */
    duration?: number
    decimals?: number
    /** custom display formatter; defaults to toLocaleString with `decimals` */
    formatter?: (n: number) => string
  }>(),
  { duration: 600, decimals: 0 },
)

const displayed = ref(0)
let rafId = 0

const text = computed(() => {
  if (props.formatter) return props.formatter(displayed.value)
  return displayed.value.toLocaleString(undefined, {
    minimumFractionDigits: props.decimals,
    maximumFractionDigits: props.decimals,
  })
})

function prefersReducedMotion() {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function animateTo(target: number) {
  cancelAnimationFrame(rafId)
  const from = displayed.value
  if (from === target || props.duration <= 0 || prefersReducedMotion()) {
    displayed.value = target
    return
  }
  const start = performance.now()
  const tick = (now: number) => {
    const p = Math.min(1, (now - start) / props.duration)
    const eased = 1 - Math.pow(1 - p, 3)
    displayed.value = from + (target - from) * eased
    if (p < 1) {
      rafId = requestAnimationFrame(tick)
    } else {
      displayed.value = target
    }
  }
  rafId = requestAnimationFrame(tick)
}

watch(
  () => props.value,
  (v) => {
    const target = Number(v)
    animateTo(Number.isFinite(target) ? target : 0)
  },
  { immediate: true },
)

onUnmounted(() => cancelAnimationFrame(rafId))
</script>

<template>
  <span class="bs-count-up">{{ text }}</span>
</template>
