<template>
  <div class="grid grid-cols-2 md:grid-cols-4 border border-grid mb-10">
    <div
      v-for="(card, i) in cards"
      :key="i"
      class="bg-warm-gray p-8"
      :class="[i < 3 ? 'border-r border-grid' : '']"
      :style="{ borderLeft: `3px solid ${card.color}` }"
    >
      <div class="font-space text-4xl font-bold text-primary mb-1 count-up">
        {{ card.displayValue }}
      </div>
      <div class="font-mono text-[11px] uppercase tracking-widest text-primary/50">
        {{ card.label }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch, onMounted } from 'vue'
import { useKnowledgeStore } from '../../stores/knowledge'

const store = useKnowledgeStore()

function formatNumber(n) {
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'K'
  return String(n)
}

const displayValues = ref({})

// Animate numbers on mount
function animateValue(key, target) {
  if (!target || target === 0) {
    displayValues.value[key] = '0'
    return
  }
  const duration = 300
  const start = performance.now()
  const from = 0
  function step(ts) {
    const elapsed = ts - start
    const progress = Math.min(elapsed / duration, 1)
    const eased = 1 - Math.pow(1 - progress, 3) // ease-out cubic
    const current = Math.round(from + (target - from) * eased)
    displayValues.value[key] = formatNumber(current)
    if (progress < 1) {
      requestAnimationFrame(step)
    }
  }
  requestAnimationFrame(step)
}

// 从kbList计算统计数据
const computedStats = computed(() => {
  const kbList = store.kbList || []
  return {
    uploaded_count: kbList.reduce((sum, kb) => sum + (kb.document_count || 0), 0),
    indexed_count: kbList.reduce((sum, kb) => sum + (kb.document_count || 0), 0), // 已索引文档数
    chunks: kbList.reduce((sum, kb) => sum + (kb.paragraph_count || 0), 0),
    chars: kbList.reduce((sum, kb) => sum + (kb.char_length || 0), 0),
  }
})

onMounted(() => {
  // 先获取kbList数据
  store.fetchKBList()
})

watch(() => computedStats.value, (s) => {
  animateValue('uploaded', s.uploaded_count || 0)
  animateValue('indexed', s.indexed_count || 0)
  animateValue('chunks', s.chunks || 0)
  animateValue('chars', s.chars || 0)
}, { immediate: true, deep: true })

const cards = computed(() => [
  {
    label: 'Total Documents',
    displayValue: displayValues.value.uploaded || '0',
    color: '#059669',
  },
  {
    label: 'Indexed Docs',
    displayValue: displayValues.value.indexed || '0',
    color: '#3B82F6',
  },
  {
    label: 'Total Chunks',
    displayValue: displayValues.value.chunks || '0',
    color: '#7C3AED',
  },
  {
    label: 'Total Characters',
    displayValue: displayValues.value.chars || '0',
    color: '#EA580C',
  },
])
</script>
