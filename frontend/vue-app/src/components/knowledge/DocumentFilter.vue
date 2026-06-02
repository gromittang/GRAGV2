<template>
  <div class="flex items-center gap-3 mb-2">
    <div class="relative flex-1 max-w-[280px]">
      <Icon icon="lucide:search" class="absolute left-2 top-1/2 -translate-y-1/2 text-primary/30 text-[14px]" />
      <input
        v-model="searchText"
        placeholder="搜索文件名..."
        class="w-full h-[32px] pl-8 pr-2 border border-grid text-[13px] text-primary bg-surface focus:outline-none focus:border-primary/30"
        @input="emitFilter"
      />
    </div>
    <select
      v-model="statusFilter"
      class="h-[32px] px-2 border border-grid text-[12px] text-primary/60 bg-surface focus:outline-none"
      @change="emitFilter"
    >
      <option value="">全部状态</option>
      <option value="2">已完成</option>
      <option value="1">处理中</option>
      <option value="0">待处理</option>
      <option value="9">失败</option>
    </select>
    <span class="font-mono text-[10px] text-primary/30 uppercase tracking-widest">
      {{ total }} DOCUMENTS
    </span>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { Icon } from '@iconify/vue'

const props = defineProps({
  total: { type: Number, default: 0 },
})

const emit = defineEmits(['filter'])

const searchText = ref('')
const statusFilter = ref('')

function emitFilter() {
  emit('filter', {
    name: searchText.value || undefined,
    status: statusFilter.value || undefined,
  })
}
</script>
