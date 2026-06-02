<template>
  <div v-if="insight && (insight.insights?.length || insight.follow_ups?.length)"
       class="border border-accent-orange/30 bg-accent-orange/5 p-4 mt-4">
    <div class="flex items-center gap-2 mb-3">
      <Icon icon="lucide:lightbulb" class="text-accent-orange" />
      <span class="font-mono text-[11px] font-bold text-accent-orange uppercase tracking-wider">AI 分析</span>
    </div>

    <!-- 关键结论 -->
    <ul v-if="insight.insights?.length" class="space-y-2 mb-3">
      <li v-for="(item, i) in insight.insights" :key="i"
          class="text-[13px] text-primary/70 flex items-start gap-2">
        <span class="text-accent-orange mt-1">•</span>
        <span>{{ item }}</span>
      </li>
    </ul>

    <!-- 追问建议 -->
    <div v-if="insight.follow_ups?.length" class="pt-3 border-t border-grid">
      <span class="text-[11px] text-primary/40 mb-2 block">你可以继续问：</span>
      <div class="flex flex-wrap gap-2">
        <button v-for="(q, i) in insight.follow_ups" :key="i"
                @click="$emit('followUp', q)"
                class="px-3 py-1.5 text-[12px] text-accent-orange border border-accent-orange/30
                       hover:bg-accent-orange/10 transition-colors">
          {{ q }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { Icon } from '@iconify/vue'

defineProps({
  insight: {
    type: Object,
    default: null
  }
})

defineEmits(['followUp'])
</script>