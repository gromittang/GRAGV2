<template>
  <div class="flex items-center justify-between px-4 h-[40px] bg-accent-orange/5 border-b border-accent-orange/20">
    <span class="font-mono text-[11px] uppercase tracking-widest text-accent-orange font-bold">
      {{ selectedCount }} SELECTED
    </span>
    <div class="flex items-center gap-1">
      <button @click="$emit('tag')" class="px-3 h-[28px] text-[11px] font-medium text-primary/60 border border-grid hover:bg-warm-gray transition-colors">
        添加标签
      </button>
      <button @click="$emit('refresh')" class="px-3 h-[28px] text-[11px] font-medium text-primary/60 border border-grid hover:bg-warm-gray transition-colors">
        重新向量化
      </button>
      <button @click="$emit('delete')" class="px-3 h-[28px] text-[11px] font-medium text-red-600 border border-red-200 hover:bg-red-50 transition-colors">
        删除
      </button>
      <button @click="$emit('clear')" class="w-6 h-6 flex items-center justify-center text-primary/30 hover:text-primary ml-1">
        <Icon icon="lucide:x" class="text-[14px]" />
      </button>
    </div>
  </div>
</template>

<script setup>
import { Icon } from '@iconify/vue'

defineProps({
  selectedCount: { type: Number, default: 0 },
})
defineEmits(['delete', 'refresh', 'tag', 'clear'])
</script>
