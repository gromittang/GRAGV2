<template>
  <div class="p-8 border-t border-white/10">
    <div class="flex items-center gap-3">
      <div
        class="w-2.5 h-2.5 rounded-full pulse-dot"
        :class="online ? 'bg-accent-green' : 'bg-amber'"
      ></div>
      <span class="text-[13px] font-medium text-white/50">
        系统状态: {{ online ? '正常运行' : '异常' }}
      </span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useAppStore } from '../../stores/app'

const store = useAppStore()
const online = computed(() => store.systemOnline)
</script>
