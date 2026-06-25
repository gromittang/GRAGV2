<template>
  <div v-if="insight && (insight.insights?.length || insight.follow_ups?.length)"
       class="insight-card bg-surface border border-grid rounded shadow-card overflow-hidden">
    <!-- Gradient header -->
    <div class="flex items-center gap-2 px-4 py-3 border-b border-grid"
         style="background: linear-gradient(135deg, rgba(199,91,42,0.03), rgba(184,138,68,0.04));">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>
      </svg>
      <span class="font-display text-[13px] font-bold text-primary">AI 数据洞察</span>
    </div>

    <!-- Body: 摘要 + 编号洞察 -->
    <div class="p-4 space-y-0">
      <!-- 摘要 -->
      <div v-if="insight.summary" class="flex gap-3 py-3 border-b border-grid/50">
        <div class="insight-marker info">1</div>
        <div class="text-[13px] text-primary leading-relaxed" v-html="highlightText(insight.summary)"></div>
      </div>

      <!-- 洞察点 -->
      <div v-for="(item, i) in insight.insights" :key="'ins-'+i"
           class="flex gap-3 py-3 border-b border-grid/50 last:border-b-0">
        <div class="insight-marker" :class="markerTypes[i % 3]">{{ (insight.summary ? 1 : 0) + i + 1 }}</div>
        <div class="text-[13px] text-primary leading-relaxed" v-html="highlightText(item)"></div>
      </div>
    </div>

    <!-- 追问建议 (保留原有功能) -->
    <div v-if="insight.follow_ups?.length" class="px-4 pb-4 pt-3 border-t border-grid">
      <span class="text-[11px] text-tertiary mb-2 block">你可以继续问：</span>
      <div class="flex flex-wrap gap-2">
        <button v-for="(q, i) in insight.follow_ups" :key="'fu-'+i"
                @click="$emit('followUp', q)"
                class="px-3 py-1.5 text-[12px] text-accent-orange border border-accent-orange/30 rounded
                       hover:bg-accent-soft transition-colors">
          {{ q }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  insight: { type: Object, default: null }
})

defineEmits(['followUp'])

const markerTypes = ['info', 'warn', 'good']

function highlightText(text) {
  if (!text) return ''
  return text.replace(
    /(\d+\.?\d*%?)/g,
    '<span class="insight-highlight">$1</span>'
  )
}
</script>

<style scoped>
.insight-marker {
  width: 20px; height: 20px;
  border-radius: 9999px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 700;
  margin-top: 1px;
}
.insight-marker.info { background: rgba(199,91,42,0.1); color: var(--color-accent); }
.insight-marker.warn { background: rgba(184,138,68,0.12); color: var(--color-accent-gold); }
.insight-marker.good { background: rgba(61,122,110,0.1); color: var(--color-accent-green); }
.insight-highlight { font-weight: 700; color: var(--color-accent); }
</style>
