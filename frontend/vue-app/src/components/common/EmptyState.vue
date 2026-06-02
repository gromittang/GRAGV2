<template>
  <div class="flex flex-col items-center justify-center py-16 text-center">
    <Icon :icon="icon" class="text-5xl mb-3" :class="colorClass" />
    <p class="font-mono text-[11px] uppercase tracking-widest mb-2" :class="colorClass">{{ title }}</p>
    <p v-if="description" class="text-[13px] text-primary/40 mb-4">{{ description }}</p>
    <button
      v-if="ctaText"
      @click="$emit('cta')"
      class="px-6 h-9 bg-primary text-white text-[13px] font-medium hover:bg-primary/90 transition-colors"
    >{{ ctaText }}</button>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Icon } from '@iconify/vue'

const props = defineProps({
  icon: { type: String, default: 'lucide:database' },
  title: { type: String, default: '暂无数据' },
  description: { type: String, default: '' },
  ctaText: { type: String, default: '' },
  color: { type: String, default: 'primary/30' },
})

defineEmits(['cta'])

const colorClass = computed(() => `text-${props.color}`)
</script>
