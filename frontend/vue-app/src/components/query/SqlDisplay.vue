<template>
  <div v-if="sql" class="bg-[#1E2127] rounded shadow-sm overflow-hidden">
    <div class="flex items-center justify-between px-4 py-2 border-b border-white/6">
      <span class="font-mono text-[10px] font-medium text-white/35 uppercase tracking-wider">Generated SQL</span>
      <button @click="copySql"
        class="px-[10px] py-[3px] border border-white/8 bg-transparent text-white/50 rounded-sm text-[10px] hover:bg-white/6 hover:text-white/80 transition-all font-mono cursor-pointer">
        {{ copied ? '已复制' : '复制' }}
      </button>
    </div>
    <pre class="px-5 py-4 text-[12.5px] text-[#C8CCD4] font-mono leading-relaxed overflow-x-auto whitespace-pre-wrap">{{ sql }}</pre>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  sql: { type: String, default: '' },
})

const copied = ref(false)

function copySql() {
  navigator.clipboard.writeText(props.sql)
  copied.value = true
  setTimeout(() => copied.value = false, 2000)
}
</script>
