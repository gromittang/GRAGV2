<template>
  <button
    @click="handleExport"
    :disabled="disabled || exporting"
    class="px-4 h-9 border border-grid text-[12px] font-medium text-primary/60 hover:text-accent-orange hover:border-accent-orange/40 transition-colors disabled:opacity-40 disabled:cursor-not-allowed inline-flex items-center gap-2"
  >
    <Icon icon="lucide:download" class="text-sm" />
    <span v-if="!exporting">导出 Excel</span>
    <span v-else class="inline-flex items-center gap-1.5">
      <span class="w-1.5 h-1.5 bg-accent-orange animate-pulse-dot"></span>
      导出中
    </span>
  </button>
</template>

<script setup>
import { ref } from 'vue'
import { Icon } from '@iconify/vue'
import reportsApi from '../../api/reports'

const props = defineProps({
  sql: { type: String, default: '' },
  title: { type: String, default: '查询结果' },
  disabled: Boolean,
})

const exporting = ref(false)

async function handleExport() {
  if (!props.sql || exporting.value) return
  exporting.value = true
  try {
    const res = await reportsApi.generateFromQuery(props.sql, props.title)
    const blob = new Blob([res.data], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${props.title}_${new Date().toISOString().slice(0, 10)}.xlsx`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    console.error('Export failed:', e)
  } finally {
    exporting.value = false
  }
}
</script>
