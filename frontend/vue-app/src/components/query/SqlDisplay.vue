<template>
  <div v-if="sql" class="border border-grid bg-surface">
    <div class="h-8 hairline-b flex items-center px-4">
      <span class="font-mono text-[10px] uppercase text-primary/40 tracking-wider">Generated SQL</span>
    </div>
    <pre class="p-4 text-[13px] text-primary/80 font-mono leading-relaxed overflow-x-auto whitespace-pre-wrap">{{ sql }}</pre>
  </div>
</template>

<script setup>
defineProps({
  sql: { type: String, default: '' },
})
</script>
