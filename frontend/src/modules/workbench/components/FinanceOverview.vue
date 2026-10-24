<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import WidgetShell from './WidgetShell.vue'
import CountUp from '@/components/common/CountUp.vue'
import { listInvoices, listPayments, listSettlements } from '@/api/finance'
import { useAuthStore } from '@/stores/auth'

defineOptions({ name: 'FinanceOverview' })

const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()

interface StatDef {
  key: string
  labelKey: string
  path: string
  perm: string
  color: string
}

const DEFS: StatDef[] = [
  {
    key: 'settlementPending',
    labelKey: 'workbench.finance.settlementPending',
    path: '/finance/settlements',
    perm: 'finance:settlement:list',
    color: 'var(--bs-color-semantic-warning)',
  },
  {
    key: 'invoiceApproving',
    labelKey: 'workbench.finance.invoiceApproving',
    path: '/finance/invoices',
    perm: 'finance:invoice:list',
    color: 'var(--bs-color-semantic-info)',
  },
  {
    key: 'paymentTotal',
    labelKey: 'workbench.finance.paymentTotal',
    path: '/finance/payments',
    perm: 'finance:payment:list',
    color: 'var(--bs-color-semantic-success)',
  },
]

const visibleDefs = computed(() => DEFS.filter((d) => auth.hasPerm(d.perm)))

const values = ref<Record<string, number>>({})
const loading = ref(false)

async function load() {
  loading.value = true
  const safeTotal = async (fn: () => Promise<{ total?: number }>) => {
    try {
      return (await fn()).total ?? 0
    } catch {
      return 0
    }
  }
  const tasks: Record<string, () => Promise<number>> = {
    settlementPending: () => safeTotal(() => listSettlements({ page: 1, size: 1, status: 'pending' })),
    invoiceApproving: () => safeTotal(() => listInvoices({ page: 1, size: 1, status: 'approving' })),
    paymentTotal: () => safeTotal(() => listPayments({ page: 1, size: 1 })),
  }
  const out: Record<string, number> = {}
  await Promise.all(
    visibleDefs.value.map(async (d) => {
      out[d.key] = (await tasks[d.key]?.()) ?? 0
    }),
  )
  values.value = out
  loading.value = false
}

onMounted(() => {
  void load()
})
</script>

<template>
  <WidgetShell :title="t('workbench.widget.financeOverview')" :loading="loading">
    <div class="fin-grid">
      <div v-for="d in visibleDefs" :key="d.key" class="fin-card" @click="router.push(d.path)">
        <div class="fin-label">{{ t(d.labelKey) }}</div>
        <div class="fin-value" :style="{ color: d.color }">
          <CountUp :value="values[d.key] ?? 0" />
        </div>
      </div>
    </div>
  </WidgetShell>
</template>

<style scoped>
.fin-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: var(--bs-space-3);
}

.fin-card {
  padding: var(--bs-space-3) var(--bs-space-4);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-bg-app);
  cursor: pointer;
}

.fin-card:hover {
  border-color: var(--bs-color-primary);
}

.fin-label {
  font-size: var(--bs-typography-font-size-sm);
  color: var(--bs-color-fg-secondary);
}

.fin-value {
  margin-top: var(--bs-space-1);
  font-size: var(--bs-typography-font-size-xxl);
  font-weight: 700;
  line-height: 1.2;
}
</style>
